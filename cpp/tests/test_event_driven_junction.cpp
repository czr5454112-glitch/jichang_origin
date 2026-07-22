#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <set>
#include <string>
#include <vector>

#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"

#ifndef CZR005_SOURCE_DIR
#error "CZR005_SOURCE_DIR must identify the repository root for canonical map tests"
#endif

namespace {

using czr005::ics::CanonicalMap2ReadResult;
using czr005::ics::EventDrivenJunctionConfig;
using czr005::ics::EventDrivenJunctionRuntime;
using czr005::ics::EventRuntimeBagRequest;
using czr005::ics::EventRuntimeFaultWindow;
using czr005::ics::Graph;

struct Checks {
  int failures = 0;

  void require(bool condition, const std::string& message) {
    if (!condition) {
      ++failures;
      std::cerr << "FAIL: " << message << '\n';
    }
  }
};

const CanonicalMap2ReadResult& canonical_map2() {
  static const CanonicalMap2ReadResult fixture = [] {
    const std::filesystem::path path = std::filesystem::path(CZR005_SOURCE_DIR) /
                                       "data" / "processed" / "maps" / "map2.json";
    return czr005::ics::read_canonical_map2_json(path);
  }();
  return fixture;
}

const Graph& canonical_graph() {
  return canonical_map2().graph;
}

EventDrivenJunctionConfig test_config() {
  EventDrivenJunctionConfig config;
  config.queue_discipline = "aging";
  config.retry_interval = 0.05;
  config.minimum_service_seconds = 0.001;
  config.dispatch_headway_seconds = 0.001;
  config.max_decisions_per_bag = 1000;
  config.max_events = 2000000;
  config.max_simulation_time = 10000.0;
  config.trace_limit = 500000;
  config.deadlock_retry_threshold = 3;
  config.starvation_threshold = 1000.0;
  return config;
}

std::vector<EventRuntimeBagRequest> burst(int count, int start = 3, int goal = 47) {
  std::vector<EventRuntimeBagRequest> bags;
  for (int index = 0; index < count; ++index) {
    bags.push_back(EventRuntimeBagRequest{"burst-" + std::to_string(index),
                                          index + 1,
                                          0.0,
                                          10000.0,
                                          start,
                                          goal,
                                          "canonical-map2"});
  }
  return bags;
}

void check_core_invariants(Checks& checks,
                           const czr005::ics::EventDrivenJunctionResult& result,
                           int expected_completed) {
  checks.require(result.summary.completed_count == expected_completed,
                 "all expected bags should complete on canonical map2");
  checks.require(result.summary.failed_count == 0, "no canonical-map bag should fail");
  checks.require(result.summary.reservation_conflicts == 0,
                 "local one-step calendars should have zero conflicts");
  checks.require(result.summary.runtime_full_astar_calls == 0,
                 "event runtime must make zero full A* calls");
  checks.require(result.summary.global_reservation_scan_count == 0,
                 "action selection must make zero global reservation scans");
  checks.require(result.summary.max_edges_selected_per_arrive <= 1,
                 "each ARRIVE_JUNCTION event selects at most one edge");
  checks.require(result.summary.release_selected_edge_count == 0,
                 "BAG_RELEASE must not select an edge or loop to goal");
  checks.require(result.summary.two_step_reservation_count == 0,
                 "two-hop diagnostics must never create a reservation");
  checks.require(result.summary.max_history_observed <= 8,
                 "bag history must remain bounded");
  checks.require(result.summary.peak_active_bag_count >= 0 &&
                     result.summary.peak_active_bag_count <= result.summary.requested_count,
                 "peak active bag count must stay within the requested cohort");
  checks.require(result.summary.final_active_bag_count == 0,
                 "final active bag count must be fully drained");

  std::size_t final_junction_accounted_bytes = 0;
  std::uint64_t service_reservation_count = 0;
  double cumulative_service_reserved_seconds = 0.0;
  for (const auto& junction : result.junctions) {
    checks.require(junction.final_source_queue_length == 0 &&
                       junction.final_junction_queue_length == 0 &&
                       junction.final_service_calendar_intervals == 0 &&
                       junction.scheduled_incoming == 0,
                   "successful runtime must drain all junction-local work");
    checks.require(junction.final_source_queue_length >= 0 &&
                       junction.peak_source_queue_length >=
                           junction.final_source_queue_length,
                   "per-junction source queue peak must dominate its final length");
    checks.require(junction.final_junction_queue_length >= 0 &&
                       junction.peak_junction_queue_length >=
                           junction.final_junction_queue_length,
                   "per-junction dispatch queue peak must dominate its final length");
    checks.require(junction.final_service_calendar_intervals >= 0 &&
                       junction.peak_service_calendar_intervals >=
                           junction.final_service_calendar_intervals,
                   "per-junction service calendar peak must dominate its final size");
    checks.require(junction.final_local_state_accounted_bytes > 0 &&
                       junction.peak_local_state_accounted_bytes >=
                           junction.final_local_state_accounted_bytes,
                   "per-junction accounted byte peak must dominate its positive final lower bound");
    checks.require(junction.cumulative_service_reserved_seconds >= 0.0,
                   "per-junction cumulative reserved service seconds must be non-negative");
    if (junction.service_reservation_count == 0) {
      checks.require(junction.first_service_reservation_start_time == -1.0 &&
                         junction.last_service_reservation_end_time == -1.0 &&
                         junction.cumulative_service_reserved_seconds == 0.0,
                     "junctions without reservations must retain the explicit time sentinel");
    } else {
      const double reservation_span = junction.last_service_reservation_end_time -
                                      junction.first_service_reservation_start_time;
      checks.require(junction.first_service_reservation_start_time >= 0.0 &&
                         junction.last_service_reservation_end_time >
                             junction.first_service_reservation_start_time &&
                         junction.cumulative_service_reserved_seconds <=
                             reservation_span + 1.0e-9,
                     "reserved service load must fit its exact non-overlapping time span");
    }
    final_junction_accounted_bytes += junction.final_local_state_accounted_bytes;
    service_reservation_count += junction.service_reservation_count;
    cumulative_service_reserved_seconds += junction.cumulative_service_reserved_seconds;
  }
  checks.require(result.summary.cpp_internal_accounted_bytes >= final_junction_accounted_bytes,
                 "runtime accounted bytes must include all final junction lower bounds");
  checks.require(service_reservation_count >= static_cast<std::uint64_t>(expected_completed),
                 "completed bags must leave raw service reservation evidence");
  checks.require(cumulative_service_reserved_seconds >= 0.0,
                 "aggregate reserved service seconds must be non-negative");

  for (const auto& event : result.events) {
    if (event.event == "ARRIVE_JUNCTION") {
      checks.require(event.selected_edge_count <= 1,
                     "trace must prove one-edge-per-arrival invariant");
    }
    if (event.event == "BAG_RELEASE") {
      checks.require(event.selected_edge_count == 0,
                     "release trace must prove no route generation");
    }
  }
  for (const auto& decision : result.decisions) {
    checks.require(!decision.full_astar_used,
                   "decision trace must mark full_astar_used=false");
    checks.require(decision.selected_next >= 0 &&
                       canonical_graph().has_edge(decision.current_node,
                                                  decision.selected_next),
                   "selected action must be one real outgoing map2 edge");
    bool found = false;
    for (const auto& candidate : decision.candidates) {
      found = found || candidate.next_node == decision.selected_next;
    }
    checks.require(found, "selected action must be present in the local candidate set");
  }
}

void test_canonical_map2_fixture(Checks& checks) {
  const auto& fixture = canonical_map2();
  checks.require(
      fixture.normalized_sha256 == czr005::ics::kCanonicalMap2NormalizedSha256,
      "canonical fixture must match the frozen normalized SHA-256 digest");
  checks.require(fixture.schema == "czr005.legacy_map.v1",
                 "canonical fixture must retain the processed map schema");
  checks.require(fixture.declared_node_count == 54 && fixture.graph.node_count() == 54,
                 "canonical fixture must load all 54 map2 nodes");
  checks.require(fixture.edge_count == 69 && fixture.graph.edge_count() == 69,
                 "canonical fixture must load all 69 map2 directed edges");
  checks.require(fixture.start_nodes == std::vector<int>({0, 1, 2, 3, 4, 5, 52, 53}),
                 "canonical fixture must retain the real start-node set");
  checks.require(fixture.end_nodes == std::vector<int>({47, 48, 49, 50, 51}),
                 "canonical fixture must retain the real terminal-node set");
  for (int node = 0; node < fixture.declared_node_count; ++node) {
    checks.require(std::isfinite(fixture.graph.heuristic(node, 47)),
                   "canonical fixture must expose a complete finite heuristic matrix");
    checks.require(fixture.graph.service_time(node) <= 1.0,
                   "canonical fixture service-time assumption must match committed map2");
  }
  checks.require(fixture.graph.has_edge(3, 16) && !fixture.graph.has_edge(16, 3),
                 "the tested 3->16 corridor must retain its real directed-only boundary");
}

void test_local_calendar_dynamic_accounting(Checks& checks) {
  czr005::ics::event_runtime_detail::LocalCalendar calendar;
  checks.require(calendar.dynamic_interval_lower_bound_bytes() == 0,
                 "empty calendar must report zero live interval payload");
  calendar.reserve(1, 0.0, 1.0);
  calendar.reserve(2, 1.0, 2.0);
  const std::size_t live_bytes =
      2 * sizeof(czr005::ics::event_runtime_detail::CalendarInterval);
  checks.require(calendar.dynamic_interval_lower_bound_bytes() == live_bytes,
                 "calendar live interval accounting must use actual interval count");
  checks.require(calendar.dynamic_interval_capacity_accounted_bytes() >= live_bytes,
                 "calendar retained capacity must account for all live intervals");
  calendar.purge(3.0);
  checks.require(calendar.dynamic_interval_lower_bound_bytes() == 0 &&
                     calendar.dynamic_interval_capacity_accounted_bytes() >= live_bytes,
                 "purge must reduce live bytes without hiding retained vector capacity");
}

void test_burst_sizes(Checks& checks) {
  const auto& graph = canonical_graph();
  for (const int count : {1, 2, 4, 8, 16}) {
    auto config = test_config();
    config.minimum_service_seconds = 1.0;
    EventDrivenJunctionRuntime runtime(graph, config);
    const auto result = runtime.run(burst(count));
    check_core_invariants(checks, result, count);
    checks.require(result.summary.decision_count >= count,
                   "every canonical-map bag must make online junction decisions");
    checks.require(result.summary.max_source_queue_length >= count - 1,
                   "source burst must be represented as a real local queue");
    checks.require(result.summary.peak_active_bag_count == count,
                   "simultaneous burst must expose the exact active-bag peak");

    std::uint64_t reservation_count = 0;
    double reserved_seconds = 0.0;
    for (const auto& junction : result.junctions) {
      reservation_count += junction.service_reservation_count;
      reserved_seconds += junction.cumulative_service_reserved_seconds;
    }
    const auto edge_enters = static_cast<std::uint64_t>(std::count_if(
        result.events.begin(), result.events.end(), [](const auto& event) {
          return event.event == "EDGE_ENTER";
        }));
    checks.require(reservation_count == edge_enters + static_cast<std::uint64_t>(count),
                   "canonical run must reserve once per admission and real edge entry");
    checks.require(std::abs(reserved_seconds - static_cast<double>(reservation_count)) <=
                       1.0e-9,
                   "minimum one-second service must expose exact reservation duration");
    if (count == 16) {
      checks.require(result.summary.max_source_queue_delay >= 14.9,
                     "16-bag burst must expose source admission delay");
      checks.require(result.summary.fairness_jain > 0.0 &&
                         result.summary.fairness_jain <= 1.0,
                     "fairness metric must be in (0, 1]");
      const auto source = std::find_if(result.junctions.begin(),
                                       result.junctions.end(),
                                       [](const auto& row) { return row.node == 3; });
      checks.require(source != result.junctions.end() &&
                         source->peak_source_queue_length >= count - 1 &&
                         source->peak_local_state_accounted_bytes >
                             source->final_local_state_accounted_bytes,
                     "real source junction must retain queue-specific peak memory evidence");
    }
    if (count == 1) {
      bool service_complete = false;
      bool edge_enter = false;
      bool queue_update = false;
      bool beacon_update = false;
      for (const auto& event : result.events) {
        service_complete = service_complete || event.event == "JUNCTION_SERVICE_COMPLETE";
        edge_enter = edge_enter || event.event == "EDGE_ENTER";
        queue_update = queue_update || event.event == "LOCAL_QUEUE_UPDATE";
        beacon_update = beacon_update || event.event == "CONGESTION_BEACON_UPDATE";
      }
      checks.require(service_complete && edge_enter && queue_update && beacon_update,
                     "scheduler must expose service, edge-entry, queue, and beacon events");
    }
  }
}

void test_real_directed_corridor_competition(Checks& checks) {
  const auto& graph = canonical_graph();
  checks.require(graph.outgoing(3) == std::vector<int>({16}) && graph.has_edge(3, 16) &&
                     !graph.has_edge(16, 3),
                 "map2 supplies one real directed 3->16 corridor and no reverse edge");
  std::vector<EventRuntimeBagRequest> bags{
      {"directed-first", 101, 0.0, 10000.0, 3, 47, "canonical-map2"},
      {"directed-second", 102, 0.0, 10000.0, 3, 47, "canonical-map2"},
  };
  EventDrivenJunctionRuntime runtime(graph, test_config());
  const auto result = runtime.run(bags);
  check_core_invariants(checks, result, 2);
  checks.require(result.summary.shield_rejection_count > 0,
                 "same-direction traffic must contend on the real local corridor calendar");
  checks.require(!result.hold_attempts.empty(),
                 "directed corridor contention must be visible as a local hold");
}

void test_loop_tabu_on_real_cycle(Checks& checks) {
  const auto& graph = canonical_graph();
  const std::array<std::pair<int, int>, 12> real_cycle{{
      {12, 13}, {13, 23}, {23, 24}, {24, 27}, {27, 28}, {28, 29}, {29, 30},
      {30, 31}, {31, 32}, {32, 33}, {33, 34}, {34, 12},
  }};
  checks.require(std::all_of(real_cycle.begin(), real_cycle.end(), [&](const auto& edge) {
                   return graph.has_edge(edge.first, edge.second);
                 }),
                 "loop test must be anchored in a real committed map2 cycle");
  EventDrivenJunctionRuntime runtime(graph, test_config());
  const auto result = runtime.run(
      {{"real-cycle-loop-guard", 201, 0.0, 10000.0, 12, 47, "canonical-map2"}});
  check_core_invariants(checks, result, 1);
  checks.require(result.summary.loop_count == 0,
                 "bounded local tabu must avoid revisiting nodes on the real cyclic topology");
  checks.require(result.bags.front().short_history.size() <= 8,
                 "loop protection must retain only bounded past history");
}

void test_non_goal_terminal_sink_is_locally_shielded(Checks& checks) {
  const auto& graph = canonical_graph();
  checks.require(graph.outgoing(28) == std::vector<int>({29, 47}) &&
                     graph.outgoing(47).empty(),
                 "terminal shield test must use the real 28->{29,47} map2 branch");
  EventDrivenJunctionRuntime runtime(graph, test_config());
  const auto result = runtime.run(
      {{"real-dead-end-shield", 250, 0.0, 10000.0, 28, 49, "canonical-map2"}});
  check_core_invariants(checks, result, 1);
  checks.require(!result.decisions.empty() && result.decisions.front().current_node == 28 &&
                     result.decisions.front().selected_next == 29,
                 "local shield must keep the bag on the real path toward terminal 49");
  bool saw_dead_end_rejection = false;
  for (const auto& candidate : result.decisions.front().candidates) {
    if (candidate.next_node == 47) {
      saw_dead_end_rejection = !candidate.shield_allowed &&
                               candidate.shield_reason == "dead_end_not_goal";
    }
  }
  checks.require(saw_dead_end_rejection,
                 "candidate trace must reject real non-goal terminal 47");
}

void test_non_goal_terminal_successor_trap_is_locally_shielded(Checks& checks) {
  const auto& graph = canonical_graph();
  checks.require(graph.outgoing(27) == std::vector<int>({28, 45}) &&
                     graph.outgoing(45) == std::vector<int>({48}) &&
                     graph.outgoing(48).empty(),
                 "successor-trap test must use real map2 branch 27->45->48");
  EventDrivenJunctionRuntime runtime(graph, test_config());
  const auto result = runtime.run(
      {{"real-terminal-trap-shield", 251, 0.0, 10000.0, 27, 47, "canonical-map2"}});
  check_core_invariants(checks, result, 1);
  checks.require(!result.decisions.empty() && result.decisions.front().current_node == 27 &&
                     result.decisions.front().selected_next == 28,
                 "bounded shield must avoid the real forced wrong-terminal successor");
  bool saw_terminal_trap_rejection = false;
  for (const auto& candidate : result.decisions.front().candidates) {
    if (candidate.next_node == 45) {
      saw_terminal_trap_rejection =
          !candidate.shield_allowed &&
          candidate.shield_reason == "terminal_successor_trap_not_goal";
    }
  }
  checks.require(saw_terminal_trap_rejection,
                 "candidate trace must expose the real terminal-successor trap rejection");
}

void test_fault_repair_delay_and_escape(Checks& checks) {
  const auto& graph = canonical_graph();
  checks.require(graph.outgoing(0) == std::vector<int>({6}) && graph.has_edge(0, 6),
                 "fault wait must use the real single-exit corridor 0->6");
  auto config = test_config();
  config.retry_interval = 0.1;
  config.deadlock_retry_threshold = 2;
  EventDrivenJunctionRuntime runtime(graph, config);
  const std::vector<EventRuntimeFaultWindow> faults{{0, 6, 0.0, 1.0, 0.25}};
  const auto result = runtime.run(
      {{"real-repair-wait", 301, 0.0, 10000.0, 0, 47, "canonical-map2"}}, faults);
  check_core_invariants(checks, result, 1);
  checks.require(result.summary.stale_fault_shield_rejection_count > 0,
                 "physical shield must reject a fault before delayed local notification");
  checks.require(result.summary.deadlock_count > 0,
                 "bounded retry detector must expose the blocked local state");
  checks.require(result.summary.resolved_deadlock_count > 0 &&
                     result.summary.unresolved_deadlock_count == 0,
                 "repair must resolve the locally detected blockage");
  bool saw_fault = false;
  bool saw_repair = false;
  bool saw_message = false;
  for (const auto& event : result.events) {
    saw_fault = saw_fault || event.event == "FAULT";
    saw_repair = saw_repair || event.event == "REPAIR";
    saw_message = saw_message || event.reason == "local_message_delivery";
  }
  checks.require(saw_fault && saw_repair && saw_message,
                 "trace must retain physical fault, repair, and delayed message events");
}

void test_delayed_fault_policy_handoff(Checks& checks) {
  const auto& graph = canonical_graph();
  checks.require(graph.outgoing(6) == std::vector<int>({8, 12}) &&
                     graph.heuristic(12, 47) < graph.heuristic(8, 47),
                 "fault handoff must use the real preferred 6->12 and alternate 6->8 edges");
  EventDrivenJunctionRuntime runtime(graph, test_config());
  const auto result = runtime.run(
      {{"real-delayed-fault", 401, 0.0, 10000.0, 6, 47, "canonical-map2"}},
      {{6, 12, 0.0, 5.0, 2.0}});
  check_core_invariants(checks, result, 1);
  checks.require(result.summary.pibt_lite_handoff_count > 0,
                 "PIBT-lite shield should hand off to the real safe alternate edge");
  checks.require(!result.decisions.empty() && result.decisions.front().current_node == 6 &&
                     result.decisions.front().model_prediction == 12 &&
                     result.decisions.front().selected_next == 8,
                 "delayed fault must change only the shielded one-step action on map2");
}

void test_fault_policy_toggle_keeps_physical_interlock_independent(Checks& checks) {
  const auto& graph = canonical_graph();
  checks.require(graph.outgoing(6) == std::vector<int>({8, 12}) &&
                     graph.heuristic(12, 47) < graph.heuristic(8, 47),
                 "policy toggle must target the real preferred 6->12 map2 edge");

  auto policy_on_config = test_config();
  policy_on_config.enable_fault_policy = true;
  EventDrivenJunctionRuntime policy_on_runtime(graph, policy_on_config);
  const auto policy_on = policy_on_runtime.run(
      {{"real-fault-policy-on", 451, 0.0, 10000.0, 6, 47, "canonical-map2"}},
      {{6, 12, 0.0, 5.0, 0.0}});
  check_core_invariants(checks, policy_on, 1);
  checks.require(policy_on.summary.fault_policy_enabled,
                 "policy-on run must report its independent configuration");
  checks.require(policy_on.summary.fault_affected_bag_count == 1 &&
                     policy_on.summary.fault_target_edge_candidate_exposure_count > 0 &&
                     policy_on.summary.fault_target_edge_attempt_count > 0,
                 "policy-on run must expose a real affected cohort and target attempt");
  checks.require(policy_on.summary.local_fault_policy_reroute_count > 0 &&
                     policy_on.summary.local_fault_policy_action_count > 0,
                 "advertised policy must proactively reroute the real target action");
  checks.require(policy_on.summary.physical_fault_edge_entry_violation_count == 0,
                 "proactive policy must retain the physical edge-entry boundary");

  auto policy_off_config = test_config();
  policy_off_config.enable_fault_policy = false;
  EventDrivenJunctionRuntime policy_off_runtime(graph, policy_off_config);
  const auto policy_off = policy_off_runtime.run(
      {{"real-fault-policy-off", 452, 0.0, 10000.0, 6, 47, "canonical-map2"}},
      {{6, 12, 0.0, 5.0, 0.0}});
  check_core_invariants(checks, policy_off, 1);
  checks.require(!policy_off.summary.fault_policy_enabled,
                 "policy-off run must report its independent configuration");
  checks.require(policy_off.summary.local_fault_policy_action_count == 0 &&
                     policy_off.summary.local_fault_policy_hold_count == 0 &&
                     policy_off.summary.local_fault_policy_reroute_count == 0,
                 "policy-off must suppress every advertised-fault action");
  checks.require(policy_off.summary.physical_fault_interlock_rejection_count > 0 &&
                     policy_off.summary.physical_fault_interlock_hold_count > 0 &&
                     policy_off.summary.physical_fault_interlock_reroute_count == 0,
                 "policy-off must hold at the non-disableable physical interlock");
  checks.require(policy_off.summary.physical_fault_edge_entry_violation_count == 0,
                 "policy-off can never disable the physical edge-entry interlock");
  for (const auto& hold : policy_off.hold_attempts) {
    for (const auto& candidate : hold.candidates) {
      checks.require(!candidate.advertised_fault,
                     "policy-off candidate state must not expose advertised faults");
    }
  }
}

void test_deterministic_trace_shards(Checks& checks) {
  const auto& graph = canonical_graph();
  auto left_config = test_config();
  left_config.trace_shard_count = 2;
  left_config.trace_shard_index = 0;
  EventDrivenJunctionRuntime left_runtime(graph, left_config);
  const auto left = left_runtime.run(burst(16));

  auto right_config = left_config;
  right_config.trace_shard_index = 1;
  EventDrivenJunctionRuntime right_runtime(graph, right_config);
  const auto right = right_runtime.run(burst(16));

  std::set<int> left_tasks;
  std::set<int> right_tasks;
  for (const auto& row : left.decisions) {
    left_tasks.insert(row.task_id);
    checks.require(row.task_id % 2 == 0, "trace shard zero must contain only even task ids");
  }
  for (const auto& row : right.decisions) {
    right_tasks.insert(row.task_id);
    checks.require(row.task_id % 2 == 1, "trace shard one must contain only odd task ids");
  }
  std::vector<int> overlap;
  std::set_intersection(left_tasks.begin(),
                        left_tasks.end(),
                        right_tasks.begin(),
                        right_tasks.end(),
                        std::back_inserter(overlap));
  checks.require(overlap.empty(), "deterministic task shards must not overlap");
  left_tasks.insert(right_tasks.begin(), right_tasks.end());
  checks.require(left_tasks.size() == 16, "two shards must cover every real-map burst task");
  checks.require(left.summary.decision_trace_shard_seen_count +
                         right.summary.decision_trace_shard_seen_count ==
                     left.summary.decision_trace_seen_count,
                 "shard seen counts must reconstruct the complete decision stream");
}

void test_duplicate_original_task_segments_keep_internal_identity(Checks& checks) {
  const auto& graph = canonical_graph();
  std::vector<EventRuntimeBagRequest> bags{
      {"77:storage_in", 77, 0.0, 10000.0, 3, 47, "canonical-map2"},
      {"77:storage_out", 77, 10.0, 10000.0, 3, 47, "canonical-map2"},
  };
  EventDrivenJunctionRuntime runtime(graph, test_config());
  const auto result = runtime.run(bags);
  check_core_invariants(checks, result, 2);
  checks.require(result.bags.size() == 2,
                 "both real-map segments with one original task id must survive");
  checks.require(result.bags[0].task_id == 77 && result.bags[1].task_id == 77,
                 "original task id must never be rewritten");
  checks.require(result.bags[0].runtime_bag_id != result.bags[1].runtime_bag_id,
                 "runtime bag id must uniquely identify each segment");
}

void test_explicit_sensor_loss_keeps_physical_shield(Checks& checks) {
  const auto& graph = canonical_graph();
  checks.require(graph.outgoing(0) == std::vector<int>({6}) && graph.has_edge(0, 6),
                 "sensor-loss test must use the real single-exit corridor 0->6");
  auto config = test_config();
  config.retry_interval = 0.1;
  EventDrivenJunctionRuntime runtime(graph, config);
  const auto result = runtime.run(
      {{"real-sensor-loss", 601, 0.0, 10000.0, 0, 47, "canonical-map2"}},
      {{0, 6, 0.0, 1.0, 0.25, true}});
  check_core_invariants(checks, result, 1);
  checks.require(result.summary.sensor_loss_mode_used,
                 "explicit dropped-notification mode must be reported");
  checks.require(result.summary.fault_notification_drop_count == 2,
                 "fault and repair messages must both be explicitly dropped");
  checks.require(result.summary.stale_fault_shield_rejection_count > 0,
                 "physical shield must remain effective when the local sensor message is lost");
  checks.require(result.summary.fault_affected_bag_count == 1 &&
                     result.summary.fault_target_edge_candidate_exposure_count > 0 &&
                     result.summary.fault_target_edge_attempt_count > 0,
                 "sensor loss evidence must contain a real affected target-edge cohort");
  checks.require(result.summary.physical_fault_interlock_rejection_count > 0 &&
                     result.summary.local_fault_policy_action_count == 0,
                 "sensor loss must exercise only the physical interlock boundary");
  checks.require(result.summary.physical_fault_edge_entry_violation_count == 0,
                 "no bag may enter a directed edge after its physical fault activates");
  for (const auto& event : result.events) {
    checks.require(event.reason != "local_message_delivery",
                   "dropped notifications must not be fabricated in the event trace");
  }
}

}  // namespace

int main() {
  Checks checks;
  try {
    test_canonical_map2_fixture(checks);
    test_local_calendar_dynamic_accounting(checks);
    test_burst_sizes(checks);
    test_real_directed_corridor_competition(checks);
    test_loop_tabu_on_real_cycle(checks);
    test_non_goal_terminal_sink_is_locally_shielded(checks);
    test_non_goal_terminal_successor_trap_is_locally_shielded(checks);
    test_fault_repair_delay_and_escape(checks);
    test_delayed_fault_policy_handoff(checks);
    test_fault_policy_toggle_keeps_physical_interlock_independent(checks);
    test_deterministic_trace_shards(checks);
    test_duplicate_original_task_segments_keep_internal_identity(checks);
    test_explicit_sensor_loss_keeps_physical_shield(checks);
  } catch (const std::exception& error) {
    ++checks.failures;
    std::cerr << "FAIL: canonical map2 test setup/runtime exception: " << error.what() << '\n';
  }
  return checks.failures == 0 ? 0 : 1;
}
