#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <set>
#include <string>
#include <tuple>
#include <vector>

#define CZR005_EVENT_RUNTIME_TESTING 1
#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"

#ifndef CZR005_SOURCE_DIR
#error "CZR005_SOURCE_DIR must identify the repository root for canonical map tests"
#endif

namespace {

using czr005::ics::CanonicalMap2ReadResult;
using czr005::ics::EventDrivenJunctionConfig;
using czr005::ics::EventDrivenJunctionRuntime;
using czr005::ics::EventCandidateRecord;
using czr005::ics::EventRuntimeBagRequest;
using czr005::ics::EventRuntimeFaultWindow;
using czr005::ics::Graph;
using czr005::ics::kS4ScoreAllComponentsMask;
using czr005::ics::kS4ScoreCorridorWaitMask;
using czr005::ics::kS4ScoreTargetQueueMask;
using czr005::ics::kS4ScoreTargetServiceWaitMask;
using czr005::ics::s4_queue_aware_score;

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

void enable_g4irsf16_h5(
    EventDrivenJunctionConfig& config,
    const std::string& mode) {
  config.g4irsf16_supervisor_mode = mode;
  auto& rule = config.g4irsf16_i4_diagnostic_rule;
  rule.authorized = true;
  rule.schema = "czr005.g4irsf16.rule_bundle.v1";
  rule.rule = "H5";
  rule.authorization = "8192_DIAGNOSTIC_ONLY_NOT_PROMOTED";
  rule.artifact_sha256 =
      "865aabd4115b84361e2c73780a8c77f3fb464b0b41bc0c950b2ce05c0a99c96b";
  rule.f2_model_margin_max = 1.518316644839415;
  rule.target_queue_length_min = 0.0;
  rule.target_scheduled_incoming_min = 5.0;
}

czr005::ics::G4IRSF16SelectiveLinearModelConfig
g4irsf16_test_model(const std::string& kind) {
  czr005::ics::G4IRSF16SelectiveLinearModelConfig model;
  model.authorized = true;
  model.self_sha256_verified = true;
  model.schema = czr005::ics::kG4IRSF16SelectiveModelSchema;
  model.kind = kind;
  model.action = kind == "I3" ? "MOVE_ONE_EDGE" : "HOLD_ONE_NATURAL_OPPORTUNITY";
  model.artifact_sha256 = "self-hash-is-integrity-not-promotion";
  for (const char* name : czr005::ics::g4irsf16_deployment_feature_names()) {
    model.feature_names.emplace_back(name);
  }
  const std::size_t count = czr005::ics::kG4IRSF16DeploymentFeatureCount;
  model.mean.assign(count, 0.0);
  model.scale.assign(count, 1.0);
  model.feature_min.assign(count, -1.0e12);
  model.feature_max.assign(count, 1.0e12);
  model.benefit_logit = {std::vector<double>(count + 1U, 0.0)};
  model.harmful_logit = {std::vector<double>(count + 1U, 0.0)};
  model.risk_adjusted_utility_seconds = {
      std::vector<double>(count + 1U, 0.0)};
  model.benefit_probability_lcb_threshold = 1.0;
  model.harmful_probability_ucb_budget = 0.0;
  model.utility_lcb_margin_seconds = 0.0;
  return model;
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

  for (const auto& bag : result.bags) {
    checks.require(bag.source_queue_delay >= 0.0 &&
                       bag.junction_queue_wait_seconds >= 0.0 &&
                       bag.edge_travel_time_seconds >= 0.0 &&
                       bag.node_service_time_seconds >= 0.0 &&
                       bag.loop_extra_time_seconds >= 0.0 &&
                       bag.goal_completion_time_seconds >= 0.0,
                   "per-bag Stage-B timing components must be non-negative");
    checks.require(bag.loop_extra_time_seconds <=
                       bag.edge_travel_time_seconds + 1.0e-12,
                   "loop-extra travel must remain a diagnostic subset of "
                   "executed edge travel");
    if (bag.loop_count == 0) {
      checks.require(bag.loop_extra_time_seconds == 0.0,
                     "a bag without an actual bounded-history revisit must "
                     "not receive synthetic loop-extra time");
    }
    if (!bag.completed) {
      continue;
    }
    const double elapsed = bag.finish_time - bag.release_time;
    const double reconstructed =
        bag.source_queue_delay +
        bag.junction_queue_wait_seconds +
        bag.edge_travel_time_seconds +
        bag.node_service_time_seconds;
    checks.require(std::abs(bag.total_local_wait -
                            (bag.source_queue_delay +
                             bag.junction_queue_wait_seconds)) <= 1.0e-7,
                   "source and junction queue waits must reconstruct the "
                   "legacy total-local-wait scalar");
    checks.require(std::abs(reconstructed - elapsed) <= 1.0e-7,
                   "source+junction+travel+service must reconstruct "
                   "finish-release; fault, calendar, and retry holds remain "
                   "inside their actual source/junction queue interval");
    checks.require(std::abs(bag.goal_completion_time_seconds - elapsed) <=
                       1.0e-7,
                   "goal-completion duration must equal finish-release");
  }

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

void test_source_admission_toggle_uses_one_hop_beacon_pressure(Checks& checks) {
  const auto& graph = canonical_graph();
  checks.require(graph.outgoing(1) == std::vector<int>({7}) &&
                     graph.outgoing(9) == std::vector<int>({7, 10}),
                 "source admission test must use real map2 merge 1/9->7");
  checks.require(graph.has_edge(9, 10),
                 "source admission test must retain the real alternate 9->10 edge");

  const std::vector<EventRuntimeBagRequest> bags{
      {"admission-leading", 701, 0.0, 10000.0, 1, 47, "canonical-map2"},
      {"admission-metered", 702, 1.1, 10000.0, 9, 47, "canonical-map2"},
      {"admission-local-calendar", 703, 1.1, 10000.0, 9, 47, "canonical-map2"},
  };
  const std::vector<EventRuntimeFaultWindow> faults{{9, 10, 0.0, 8.0, 0.0}};

  auto enabled_config = test_config();
  enabled_config.minimum_service_seconds = 1.0;
  enabled_config.enable_source_admission = true;
  EventDrivenJunctionRuntime enabled_runtime(graph, enabled_config);
  const auto enabled = enabled_runtime.run(bags, faults);
  check_core_invariants(checks, enabled, 3);

  auto disabled_config = enabled_config;
  disabled_config.enable_source_admission = false;
  EventDrivenJunctionRuntime disabled_runtime(graph, disabled_config);
  const auto disabled = disabled_runtime.run(bags, faults);
  check_core_invariants(checks, disabled, 3);

  const auto partitioned = [](const auto& summary) {
    return summary.source_admission_attempt_count ==
           summary.source_admission_admitted_count +
               summary.source_admission_local_resource_hold_count +
               summary.source_admission_downstream_pressure_hold_count;
  };
  checks.require(enabled.summary.source_admission_enabled &&
                     !disabled.summary.source_admission_enabled,
                 "runtime summary must echo the C++ source-admission configuration");
  checks.require(partitioned(enabled.summary) && partitioned(disabled.summary),
                 "source admission attempts must have one auditable terminal outcome");
  checks.require(enabled.summary.source_admission_admitted_count == 3 &&
                     disabled.summary.source_admission_admitted_count == 3,
                 "both policies must admit each real-map test bag exactly once");
  checks.require(enabled.summary.source_admission_downstream_pressure_hold_count > 0 &&
                     enabled.summary.source_admission_beacon_read_count > 0 &&
                     enabled.summary.source_admission_max_observed_downstream_pressure > 0,
                 "enabled admission must meter the real merge from a one-hop beacon");
  checks.require(disabled.summary.source_admission_downstream_pressure_hold_count == 0 &&
                     disabled.summary.source_admission_beacon_read_count == 0 &&
                     disabled.summary.source_admission_max_observed_downstream_pressure == 0,
                 "disabled admission must bypass downstream state without bypassing source service");

  const auto enabled_metered = std::find_if(
      enabled.bags.begin(), enabled.bags.end(), [](const auto& row) { return row.task_id == 702; });
  const auto disabled_metered = std::find_if(
      disabled.bags.begin(), disabled.bags.end(), [](const auto& row) { return row.task_id == 702; });
  checks.require(enabled_metered != enabled.bags.end() &&
                     disabled_metered != disabled.bags.end() &&
                     enabled_metered->admitted_time > disabled_metered->admitted_time,
                 "enabled admission must delay the metered bag until the advertised calendar is ready");
  checks.require(disabled.summary.source_admission_local_resource_hold_count > 0,
                 "admission-off must still retain source-local calendar holds");
}

void test_source_admission_same_time_event_order(Checks& checks) {
  using czr005::ics::JunctionEventType;
  using czr005::ics::event_runtime_detail::RuntimeEvent;
  using czr005::ics::event_runtime_detail::event_priority;

  RuntimeEvent service;
  service.type = JunctionEventType::kJunctionServiceComplete;
  RuntimeEvent arrival;
  arrival.type = JunctionEventType::kArriveJunction;
  RuntimeEvent beacon;
  beacon.type = JunctionEventType::kCongestionBeaconUpdate;
  RuntimeEvent release;
  release.type = JunctionEventType::kBagRelease;

  checks.require(event_priority(service) < event_priority(arrival) &&
                     event_priority(arrival) < event_priority(beacon) &&
                     event_priority(beacon) < event_priority(release),
                 "same-time source retry must observe completed service, arrival, and beacon state");
}

void test_diagnostic_hops_are_read_only(Checks& checks) {
  const auto& graph = canonical_graph();
  auto one_hop_config = test_config();
  one_hop_config.minimum_service_seconds = 1.0;
  one_hop_config.diagnostic_hops = 1;
  EventDrivenJunctionRuntime one_hop_runtime(graph, one_hop_config);
  const auto one_hop = one_hop_runtime.run(burst(16));
  check_core_invariants(checks, one_hop, 16);

  auto two_hop_config = one_hop_config;
  two_hop_config.diagnostic_hops = 2;
  EventDrivenJunctionRuntime two_hop_runtime(graph, two_hop_config);
  const auto two_hop = two_hop_runtime.run(burst(16));
  check_core_invariants(checks, two_hop, 16);

  std::vector<std::tuple<int, int, int>> one_hop_actions;
  std::vector<std::tuple<int, int, int>> two_hop_actions;
  int one_hop_max_pressure = 0;
  int two_hop_max_pressure = 0;
  for (const auto& decision : one_hop.decisions) {
    one_hop_actions.emplace_back(decision.task_id,
                                 decision.current_node,
                                 decision.selected_next);
    for (const auto& candidate : decision.candidates) {
      one_hop_max_pressure =
          std::max(one_hop_max_pressure, candidate.two_hop_queue_pressure);
    }
  }
  for (const auto& decision : two_hop.decisions) {
    two_hop_actions.emplace_back(decision.task_id,
                                 decision.current_node,
                                 decision.selected_next);
    for (const auto& candidate : decision.candidates) {
      two_hop_max_pressure =
          std::max(two_hop_max_pressure, candidate.two_hop_queue_pressure);
    }
  }
  checks.require(one_hop.summary.two_step_reservation_count == 0 &&
                     two_hop.summary.two_step_reservation_count == 0,
                 "one/two-hop diagnostics must never reserve a second edge");
  checks.require(one_hop_max_pressure == 0 && two_hop_max_pressure > 0,
                 "two-hop mode must expose a real bounded pressure summary only when enabled");
  checks.require(one_hop_actions == two_hop_actions,
                 "read-only two-hop diagnostics must not change committed actions");
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

  auto feng_config = test_config();
  feng_config.scorer_mode =
      "FENG_DH_REIMPLEMENTATION_COEFFICIENTS_UNDISCLOSED";
  EventDrivenJunctionRuntime feng_runtime(graph, feng_config);
  const auto feng = feng_runtime.run(
      {{"feng-real-cross-terminal", 252, 0.0, 10000.0, 28, 49,
        "canonical-map2"}});
  check_core_invariants(checks, feng, 1);
  checks.require(
      !feng.decisions.empty() && feng.decisions.front().selected_next == 29,
      "an unreachable cross-terminal Feng-DH candidate must not abort or "
      "displace the reachable candidate");
  const auto cross_terminal = std::find_if(
      feng.decisions.front().candidates.begin(),
      feng.decisions.front().candidates.end(),
      [](const auto& candidate) { return candidate.next_node == 47; });
  checks.require(
      cross_terminal != feng.decisions.front().candidates.end() &&
          std::isinf(cross_terminal->scorer_raw_score) &&
          cross_terminal->scorer_raw_score > 0.0 &&
          !cross_terminal->shield_allowed,
      "the real map2 cross-terminal continuation must receive +infinity and "
      "remain shielded");

  auto tarau_config = test_config();
  tarau_config.scorer_mode =
      "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY";
  EventDrivenJunctionRuntime tarau_runtime(graph, tarau_config);
  const auto tarau = tarau_runtime.run(
      {{"tarau-real-cross-terminal", 253, 0.0, 10000.0, 28, 49,
        "canonical-map2"}});
  check_core_invariants(checks, tarau, 1);
  checks.require(
      !tarau.decisions.empty() &&
          tarau.decisions.front().selected_next == 29,
      "the Tarau route-only adaptation must retain the reachable real map2 "
      "candidate");
  const auto tarau_cross_terminal = std::find_if(
      tarau.decisions.front().candidates.begin(),
      tarau.decisions.front().candidates.end(),
      [](const auto& candidate) { return candidate.next_node == 47; });
  checks.require(
      tarau_cross_terminal != tarau.decisions.front().candidates.end() &&
          std::isinf(tarau_cross_terminal->scorer_raw_score) &&
          tarau_cross_terminal->scorer_raw_score > 0.0 &&
          !tarau_cross_terminal->shield_allowed,
      "the Tarau route-only score must map a real wrong terminal to "
      "+infinity without aborting");
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
  config.enable_source_admission = false;
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

void test_wait_retries_do_not_consume_route_decision_budget(Checks& checks) {
  const auto& graph = canonical_graph();
  checks.require(graph.outgoing(0) == std::vector<int>({6}) &&
                     graph.has_edge(0, 6),
                 "decision-budget wait test must use the real 0->6 edge");
  auto config = test_config();
  config.retry_interval = 0.05;
  config.max_decisions_per_bag = 1;
  config.enable_source_admission = false;
  EventDrivenJunctionRuntime runtime(graph, config);
  const auto result = runtime.run(
      {{"real-wait-not-decision", 302, 0.0, 10000.0, 0, 6,
        "canonical-map2"}},
      {{0, 6, 0.0, 1.0, 0.0}});
  check_core_invariants(checks, result, 1);
  checks.require(result.bags.size() == 1 &&
                     result.bags.front().decision_count == 1 &&
                     result.summary.decision_count == 1,
                 "only the committed 0->6 action may consume the one-decision budget");
  checks.require(result.bags.front().retry_count > 1,
                 "the bag must wait through several fault retries before repair");
  checks.require(result.bags.front().failure_reason.empty(),
                 "bounded waiting must not be misclassified as max_decisions_exceeded");
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
                 "legacy PIBT-lite shield should hand off to the real safe alternate edge");
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
  config.enable_source_admission = false;
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

void test_bounded_pibt_sensor_loss_uses_local_fault_handoff(Checks& checks) {
  const auto& graph = canonical_graph();
  checks.require(graph.has_edge(22, 24) && graph.has_edge(22, 26),
                 "sensor-loss handoff test requires the real 22 split");

  auto recovery_config = test_config();
  recovery_config.retry_interval = 0.001;
  recovery_config.max_decisions_per_bag = 512;
  recovery_config.enable_source_admission = false;
  recovery_config.enable_pibt_lite = false;
  recovery_config.pibt_mode = "P2";
  recovery_config.local_queue_capacity = 32;
  recovery_config.enable_fault_policy = true;
  EventDrivenJunctionRuntime recovery_runtime(graph, recovery_config);
  const auto recovered = recovery_runtime.run(
      {{"real-p2-sensor-loss", 602, 0.0, 10000.0, 22, 47,
        "canonical-map2"}},
      {{22, 24, 0.0, 10.0, 0.0, true}});
  check_core_invariants(checks, recovered, 1);
  checks.require(recovered.summary.sensor_loss_mode_used &&
                     recovered.summary.fault_notification_drop_count == 2,
                 "P2 recovery must retain explicit dropped-notification evidence");
  checks.require(
      recovered.summary.physical_fault_interlock_rejection_count > 0 &&
          recovered.summary.physical_fault_interlock_reroute_count > 0,
      "enabled recovery must hand off to one local alternative after the physical interlock");
  checks.require(recovered.summary.pibt_lite_handoff_count == 0,
                 "physical fault recovery must not masquerade as legacy pibt_lite");
  checks.require(!recovered.summary.legacy_pibt_lite_enabled,
                 "P2 sensor-loss evidence must echo legacy pibt_lite as disabled");
  checks.require(recovered.summary.local_fault_policy_action_count == 0,
                 "dropped notifications must not fabricate advertised-fault actions");
  checks.require(recovered.summary.physical_fault_edge_entry_violation_count == 0,
                 "P2 sensor-loss recovery must never enter the faulted edge");
  checks.require(recovered.summary.runtime_full_astar_calls == 0 &&
                     recovered.summary.global_reservation_scan_count == 0 &&
                     recovered.summary.first_edge_credit_future_route_count == 0 &&
                     recovered.summary.scorer_future_route_input_count == 0,
                 "sensor-loss handoff must remain one-step, local, and route-free");

  auto disabled_config = recovery_config;
  disabled_config.enable_fault_policy = false;
  EventDrivenJunctionRuntime disabled_runtime(graph, disabled_config);
  const auto disabled = disabled_runtime.run(
      {{"real-p2-policy-off", 603, 0.0, 10000.0, 22, 47,
        "canonical-map2"}},
      {{22, 24, 0.0, 10.0, 0.0, false}});
  checks.require(disabled.summary.completed_count == 1 &&
                     disabled.summary.failed_count == 0 &&
                     disabled.bags.size() == 1 &&
                     disabled.bags.front().finish_time >= 10.0,
                 "fault-policy-off control must wait for physical repair before completing");
  checks.require(disabled.summary.physical_fault_interlock_rejection_count > 0 &&
                     disabled.summary.physical_fault_interlock_reroute_count == 0,
                 "fault-policy-off must preserve the shield and suppress pre-repair rerouting");
  checks.require(disabled.summary.local_fault_policy_action_count == 0,
                 "fault-policy-off must not advertise or commit a recovery action");
  checks.require(!disabled.summary.legacy_pibt_lite_enabled,
                 "P2 policy-off control must echo legacy pibt_lite as disabled");
  checks.require(disabled.summary.physical_fault_edge_entry_violation_count == 0,
                 "fault-policy-off must still retain the non-configurable physical interlock");
}

void test_g4irsf16_fault_generation_survives_repair_boost_reset(
    Checks& checks) {
  const auto& graph = canonical_graph();
  auto config = test_config();
  config.retry_interval = 0.1;
  config.enable_source_admission = false;
  enable_g4irsf16_h5(config, "shadow");
  EventDrivenJunctionRuntime runtime(graph, config);
  const auto result = runtime.run(
      {{"g4irsf16-fault-repair", 701, 0.0, 10000.0, 0, 47,
        "canonical-map2"}},
      {{0, 6, 0.0, 1.0, 0.25, true}});
  check_core_invariants(checks, result, 1);
  checks.require(result.summary.g4irsf16_supervisor_evaluation_count > 0,
                 "G4IRSF16 fault regression must evaluate the native supervisor");
  checks.require(result.summary.g4irsf16_fault_recovery_count > 0,
                 "G4IRSF16 fault regression must observe physical fault recovery");
  int post_repair_non_fault_decisions = 0;
  const auto inspect = [&](const auto& rows) {
    for (const auto& row : rows) {
      if (!row.g4irsf16_evaluated) {
        continue;
      }
      checks.require(
          row.g4irsf16_reason !=
              "stale_physical_fault_generation_rejected",
          "repair-priority reset must not roll back the supervisor fault generation");
      if (row.event_time > 1.0 &&
          row.g4irsf16_state != "FAULT_RECOVERY") {
        ++post_repair_non_fault_decisions;
      }
    }
  };
  inspect(result.decisions);
  inspect(result.hold_attempts);
  checks.require(post_repair_non_fault_decisions >= 2,
                 "repaired bag must return to normal G4IRSF16 decisions across later nodes");
}

void test_g4irsf16_learned_model_closed_loop_is_not_self_authorizing(
    Checks& checks) {
  const auto& graph = canonical_graph();
  auto closed_loop = test_config();
  closed_loop.g4irsf16_supervisor_mode = "closed_loop";
  closed_loop.g4irsf16_i3_model = g4irsf16_test_model("I3");
  closed_loop.g4irsf16_i4_model = g4irsf16_test_model("I4");
  bool rejected = false;
  try {
    EventDrivenJunctionRuntime runtime(graph, closed_loop);
    (void)runtime;
  } catch (const std::invalid_argument& error) {
    rejected = std::string(error.what()).find("NO_GO") !=
               std::string::npos;
  }
  checks.require(
      rejected,
      "a self-hashed learned model must not authorize its own closed-loop promotion");

  auto shadow = closed_loop;
  shadow.g4irsf16_supervisor_mode = "shadow";
  EventDrivenJunctionRuntime shadow_runtime(graph, shadow);
  const auto result = shadow_runtime.run(
      {{"g4irsf16-model-shadow", 702, 0.0, 10000.0, 3, 47,
        "canonical-map2"}});
  check_core_invariants(checks, result, 1);
  checks.require(
      result.summary.g4irsf16_policy_kind == "unpromoted_model_shadow" &&
          result.summary.g4irsf16_diagnostic_only &&
          !result.summary.g4irsf16_promotion_authorized &&
          result.summary.g4irsf16_action_change_count == 0,
      "learned-model shadow must remain diagnostic-only and action-inert");
}

void test_legacy_observation_bias_is_local_deterministic_and_exact_off(
    Checks& checks) {
  // One bag isolates timing from contention so the chosen one-hop actions
  // must remain identical while observed arrival timestamps move.
  const auto& graph = canonical_graph();
  const std::vector<EventRuntimeBagRequest> request = {
      {"legacy-observation-bias", 801, 0.0, 10000.0, 3, 47,
       "canonical-map2"}};

  auto baseline_config = test_config();
  EventDrivenJunctionRuntime baseline_runtime(graph, baseline_config);
  const auto baseline = baseline_runtime.run(request);

  auto off_config = baseline_config;
  off_config.legacy_observation_bias_max_seconds = 0.0;
  off_config.legacy_observation_bias_seed = 12345;
  EventDrivenJunctionRuntime off_runtime(graph, off_config);
  const auto off = off_runtime.run(request);
  checks.require(
      baseline.bags.front().finish_time == off.bags.front().finish_time &&
          baseline.summary.event_count == off.summary.event_count &&
          baseline.decisions.size() == off.decisions.size(),
      "zero legacy observation bias must preserve the exact runtime result");

  auto active_config = baseline_config;
  active_config.legacy_observation_bias_max_seconds = 3.0;
  active_config.legacy_observation_bias_seed = 12345;
  EventDrivenJunctionRuntime left_runtime(graph, active_config);
  EventDrivenJunctionRuntime right_runtime(graph, active_config);
  const auto left = left_runtime.run(request);
  const auto right = right_runtime.run(request);
  checks.require(
      left.bags.front().finish_time == right.bags.front().finish_time &&
          left.summary.legacy_observation_bias_total_seconds ==
              right.summary.legacy_observation_bias_total_seconds,
      "legacy observation bias must be deterministic for a fixed seed");
  checks.require(
      left.bags.front().finish_time > baseline.bags.front().finish_time &&
          left.summary.legacy_observation_bias_sample_count > 0 &&
          left.summary.legacy_observation_bias_total_seconds > 0.0,
      "active observation bias must delay observed node-arrival time");
  checks.require(
      left.summary.physical_fault_edge_entry_violation_count == 0 &&
          left.summary.runtime_full_astar_calls == 0 &&
          left.summary.global_reservation_scan_count == 0,
      "observation bias must preserve the local safety boundary");
  checks.require(left.decisions.size() == baseline.decisions.size(),
                 "observation bias must preserve the one-hop decision count");
  if (left.decisions.size() == baseline.decisions.size()) {
    for (std::size_t index = 0; index < left.decisions.size(); ++index) {
      checks.require(
          left.decisions[index].current_node ==
                  baseline.decisions[index].current_node &&
              left.decisions[index].selected_next ==
                  baseline.decisions[index].selected_next,
          "observation bias must not introduce an illegal or different edge");
    }
  }
}

void test_storage_source_role_default_is_map2_compatible(Checks& checks) {
  const EventDrivenJunctionConfig config;
  checks.require(
      config.storage_source_nodes == std::vector<int>{52},
      "storage source role must retain the legacy map2 node-52 default");
}

void test_s4_component_mask_and_queue_time_scaling_motif(Checks& checks) {
  EventCandidateRecord candidate;
  candidate.travel_time = 2.0;
  candidate.static_potential = 3.0;
  candidate.target_queue_length = 4;
  candidate.target_scheduled_incoming = 6;
  candidate.corridor_next_available = 17.0;
  candidate.target_next_available = 20.0;
  candidate.estimated_service_rate = 2.0;
  constexpr double event_time = 10.0;
  constexpr std::array<double, 4> raw_terms = {4.0, 6.0, 7.0, 8.0};
  constexpr std::array<double, 4> normalized_terms = {2.0, 3.0, 7.0, 8.0};

  const double historical =
      candidate.travel_time + candidate.static_potential +
      static_cast<double>(candidate.target_queue_length +
                          candidate.target_scheduled_incoming) +
      (candidate.corridor_next_available - event_time) +
      (candidate.target_next_available -
       (event_time + candidate.travel_time));
  checks.require(
      s4_queue_aware_score(candidate, event_time,
                           kS4ScoreAllComponentsMask, false) == historical,
      "mask 15 with raw count-as-seconds must preserve the historical S4 "
      "expression exactly");

  for (int mask = 0; mask <= kS4ScoreAllComponentsMask; ++mask) {
    double expected_raw = 5.0;
    double expected_normalized = 5.0;
    for (int bit = 0; bit < 4; ++bit) {
      if ((mask & (1 << bit)) != 0) {
        expected_raw += raw_terms[static_cast<std::size_t>(bit)];
        expected_normalized +=
            normalized_terms[static_cast<std::size_t>(bit)];
      }
    }
    checks.require(
        s4_queue_aware_score(candidate, event_time, mask, false) ==
            expected_raw,
        "every S4 component mask must include exactly its enabled raw terms");
    checks.require(
        s4_queue_aware_score(candidate, event_time, mask, true) ==
            expected_normalized,
        "F1 must divide each enabled Q/I term by estimated service rate and "
        "leave WC/WS in seconds");
  }

  candidate.estimated_service_rate = 0.0;
  checks.require(
      s4_queue_aware_score(
          candidate, event_time,
          kS4ScoreCorridorWaitMask | kS4ScoreTargetServiceWaitMask,
          true) == 20.0,
      "F1 must not read service rate when both queue-count terms are masked");
  bool rejected_invalid_rate = false;
  try {
    (void)s4_queue_aware_score(
        candidate, event_time, kS4ScoreTargetQueueMask, true);
  } catch (const std::logic_error&) {
    rejected_invalid_rate = true;
  }
  checks.require(
      rejected_invalid_rate,
      "F1 must fail closed if an enabled queue-count term lacks a positive "
      "finite service rate");
}

Graph s4_merge_calendar_visibility_graph() {
  Graph graph;
  for (int node = 0; node < 6; ++node) {
    const double service = node == 1 ? 100.0 : 0.001;
    graph.add_node(czr005::ics::Node{node, 0, service, 0, 0, {}});
  }
  for (const auto [start, end] :
       std::vector<std::pair<int, int>>{{0, 1}, {0, 2}, {3, 1},
                                        {4, 2}, {1, 5}, {2, 5}}) {
    graph.add_edge(czr005::ics::Edge{start, end, 0.1, 1.0});
  }
  std::vector<std::vector<double>> heuristic(
      6, std::vector<double>(6, 0.0));
  heuristic[0][5] = 3.0;
  heuristic[1][5] = 0.1;
  heuristic[2][5] = 2.0;
  heuristic[3][5] = 0.2;
  heuristic[4][5] = 2.1;
  graph.set_heuristic(std::move(heuristic));
  return graph;
}

void test_s4_direct_neighbor_merge_calendar_visibility_is_exact_off_and_local(
    Checks& checks) {
  const auto graph = s4_merge_calendar_visibility_graph();
  const std::vector<EventRuntimeBagRequest> requests = {
      {"calendar-blocker", 41, 0.0, 1000.0, 1, 5, "synthetic"},
      {"calendar-probe", 42, 0.05, 1000.0, 0, 5, "synthetic"},
  };
  auto off = test_config();
  off.scorer_mode = "S4_queue_aware_rule_only";
  off.resource_semantics = "R3_java_node_window_compatible";
  off.event_semantics = "E4_batch_plus_destination_merge_request";
  off.merge_grant_rule = "M3";
  off.merge_grant_timing_mode = "jit_fair_aging_deadline";
  off.queue_discipline = "fifo";
  off.enable_source_admission = false;
  off.local_queue_capacity = 0;
  off.storage_source_nodes = {1};

  EventDrivenJunctionRuntime implicit_off_runtime(graph, off);
  const auto implicit_off = implicit_off_runtime.run(requests);
  off.enable_s4_direct_neighbor_merge_calendar_visibility = false;
  EventDrivenJunctionRuntime explicit_off_runtime(graph, off);
  const auto explicit_off = explicit_off_runtime.run(requests);
  checks.require(
      implicit_off.decisions.size() == explicit_off.decisions.size() &&
          implicit_off.bags.size() == explicit_off.bags.size(),
      "default-off merge-calendar visibility must preserve result shape");
  checks.require(
      implicit_off.summary.s4_score_component_mask ==
              kS4ScoreAllComponentsMask &&
          implicit_off.summary.queue_time_scaling ==
              "raw_count_as_seconds",
      "the S4 summary must echo the compatibility-default score controls");
  if (implicit_off.decisions.size() == explicit_off.decisions.size()) {
    for (std::size_t index = 0; index < implicit_off.decisions.size(); ++index) {
      checks.require(
          implicit_off.decisions[index].selected_next ==
                  explicit_off.decisions[index].selected_next &&
              implicit_off.decisions[index].event_time ==
                  explicit_off.decisions[index].event_time,
          "explicit false must preserve every default one-hop action");
    }
  }
  if (implicit_off.bags.size() == explicit_off.bags.size()) {
    for (std::size_t index = 0; index < implicit_off.bags.size(); ++index) {
      checks.require(
          implicit_off.bags[index].finish_time ==
              explicit_off.bags[index].finish_time,
          "explicit false must preserve every default completion time");
    }
  }

  auto visible = off;
  visible.enable_s4_direct_neighbor_merge_calendar_visibility = true;
  EventDrivenJunctionRuntime visible_runtime(graph, visible);
  const auto result = visible_runtime.run(requests);
  checks.require(result.summary.completed_count == 2 &&
                     result.summary.failed_count == 0,
                 "merge-calendar visibility fixture must drain");
  checks.require(
      result.summary.s4_direct_neighbor_merge_calendar_visibility_enabled &&
          !result.summary
               .s4_direct_neighbor_merge_calendar_visibility_learning_active &&
          result.summary
                  .s4_direct_neighbor_merge_calendar_visibility_claim_boundary ==
              "direct_outgoing_neighbor_calendar_scalar;"
              "existing_calendar_wait_weight;J2_authority_unchanged;"
              "O_outdegree;no_full_route;no_learning",
      "active visibility summary must echo local non-learning semantics");

  const auto probe_decision = [](const auto& run) {
    return std::find_if(run.decisions.begin(), run.decisions.end(),
                        [](const auto& row) {
                          return row.segment_id == "calendar-probe" &&
                                 row.current_node == 0;
                        });
  };
  const auto off_probe = probe_decision(implicit_off);
  const auto visible_probe = probe_decision(result);
  checks.require(off_probe != implicit_off.decisions.end() &&
                     off_probe->selected_next == 1,
                 "suppressed merge calendar must keep the static S4 branch");
  checks.require(visible_probe != result.decisions.end() &&
                     visible_probe->selected_next == 2,
                 "visible busy direct-neighbor calendar must switch S4 locally");
  if (off_probe != implicit_off.decisions.end() &&
      visible_probe != result.decisions.end()) {
    const auto candidate_one = [](const auto& row) {
      return std::find_if(row.candidates.begin(), row.candidates.end(),
                          [](const auto& candidate) {
                            return candidate.next_node == 1;
                          });
    };
    const auto off_candidate = candidate_one(*off_probe);
    const auto visible_candidate = candidate_one(*visible_probe);
    checks.require(
        off_candidate != off_probe->candidates.end() &&
            visible_candidate != visible_probe->candidates.end() &&
            visible_candidate->target_next_available >
                off_candidate->target_next_available + 50.0,
        "opt-in must expose the existing busy calendar scalar only");
  }
  checks.require(result.summary.merge_grant_committed_count > 0,
                 "J2 must remain the real merge grant authority");
  checks.require(result.summary.runtime_full_astar_calls == 0 &&
                     result.summary.global_reservation_scan_count == 0 &&
                     result.summary.two_step_reservation_count == 0,
                 "visibility must remain one-hop without route planning");
}

Graph local_descent_cycle_graph() {
  Graph graph;
  for (int node = 0; node < 5; ++node) {
    graph.add_node(czr005::ics::Node{
        node, 0, node == 2 ? 100.0 : 0.001, 0, 0, {}});
  }
  for (const auto [start, end] :
       std::vector<std::pair<int, int>>{{0, 1}, {1, 0}, {1, 2},
                                        {2, 3}, {4, 2}}) {
    graph.add_edge(czr005::ics::Edge{start, end, 0.1, 1.0});
  }
  std::vector<std::vector<double>> heuristic(
      5, std::vector<double>(5, 0.0));
  heuristic[0][3] = 100.302;
  heuristic[1][3] = 100.201;
  heuristic[2][3] = 100.1;
  heuristic[4][3] = 100.201;
  graph.set_heuristic(std::move(heuristic));
  return graph;
}

void test_s4_local_descent_guard_is_exact_off_and_blocks_cycle(
    Checks& checks) {
  const auto graph = local_descent_cycle_graph();
  const std::vector<EventRuntimeBagRequest> requests = {
      {"blocker", 1, 0.0, 1000.0, 4, 3, "synthetic"},
      {"probe", 2, 0.05, 1000.0, 0, 3, "synthetic"},
  };
  auto off = test_config();
  off.scorer_mode = "S4_queue_aware_rule_only";
  off.storage_source_nodes = {4};
  EventDrivenJunctionRuntime implicit_off_runtime(graph, off);
  const auto implicit_off = implicit_off_runtime.run(requests);
  off.enable_s4_local_potential_descent_guard = false;
  EventDrivenJunctionRuntime explicit_off_runtime(graph, off);
  const auto explicit_off = explicit_off_runtime.run(requests);
  checks.require(
      implicit_off.decisions.size() == explicit_off.decisions.size(),
      "the default-off descent guard must preserve the decision stream");
  if (implicit_off.decisions.size() == explicit_off.decisions.size()) {
    for (std::size_t index = 0; index < implicit_off.decisions.size(); ++index) {
      checks.require(
          implicit_off.decisions[index].selected_next ==
              explicit_off.decisions[index].selected_next,
          "explicit false must preserve every default S4 action");
    }
  }
  const bool off_backtracked = std::any_of(
      implicit_off.decisions.begin(), implicit_off.decisions.end(),
      [](const auto& row) {
        return row.segment_id == "probe" && row.current_node == 1 &&
               row.selected_next == 0;
      });
  checks.require(off_backtracked,
                 "the synthetic congestion case must expose the S4 cycle");

  auto guarded = off;
  guarded.enable_s4_local_potential_descent_guard = true;
  EventDrivenJunctionRuntime guarded_runtime(graph, guarded);
  const auto result = guarded_runtime.run(requests);
  checks.require(result.summary.completed_count == 2 &&
                     result.summary.failed_count == 0,
                 "the guarded synthetic congestion case must drain");
  checks.require(
      result.summary.s4_local_potential_descent_guard_enabled &&
          !result.summary.s4_local_potential_descent_guard_learning_active &&
          result.summary.s4_local_potential_descent_guard_claim_boundary ==
              "one_next_edge_at_current_junction;strict_H_eff_descent;"
              "O_outdegree;no_full_route;no_learning",
      "active guard summary must echo one-hop strict non-learning semantics");
  for (const auto& row : result.decisions) {
    if (row.segment_id != "probe" || row.selected_next < 0) {
      continue;
    }
    const double current =
        row.current_node == row.goal_node
            ? 0.0
            : graph.heuristic(row.current_node, row.goal_node);
    const double next =
        row.selected_next == row.goal_node
            ? 0.0
            : graph.heuristic(row.selected_next, row.goal_node);
    checks.require(next + 1.0e-9 < current,
                   "every guarded MOVE must strictly decrease H");
  }
}

Graph local_descent_fault_graph() {
  Graph graph;
  for (int node = 0; node < 5; ++node) {
    graph.add_node(czr005::ics::Node{node, 0, 0.001, 0, 0, {}});
  }
  for (const auto [start, end, length] :
       std::vector<std::tuple<int, int, double>>{
           {0, 1, 1.0}, {1, 2, 1.0}, {2, 3, 1.0},
           {1, 4, 1.0}, {4, 3, 3.0}}) {
    graph.add_edge(czr005::ics::Edge{start, end, length, 1.0});
  }
  std::vector<std::vector<double>> heuristic(
      5, std::vector<double>(5, 0.0));
  heuristic[0][3] = 3.003;
  heuristic[1][3] = 2.002;
  heuristic[2][3] = 1.001;
  heuristic[4][3] = 3.001;
  graph.set_heuristic(std::move(heuristic));
  return graph;
}

void test_s4_local_descent_guard_uses_surviving_fault_potential(
    Checks& checks) {
  const auto graph = local_descent_fault_graph();
  auto config = test_config();
  config.scorer_mode = "S4_queue_aware_rule_only";
  config.enable_s4_local_potential_descent_guard = true;
  config.storage_source_nodes = {0};
  config.g4irsf24_dlp.mode = "td";
  config.g4irsf24_dlp.beta = 0.0;
  config.g4irsf24_dlp.min_support = 1;
  config.g4irsf24_dlp.detour_allowance_seconds = 1000.0;
  config.g4irsf24_dlp.deterministic_surviving_graph_values = true;
  config.g4irsf24_dlp.insert_value(0, 3, 2.0, 1);
  config.g4irsf24_dlp.insert_value(1, 3, 2.0, 1);
  config.g4irsf24_dlp.insert_value(2, 3, 100.0, 1);
  config.g4irsf24_dlp.insert_value(4, 3, 0.0, 1);
  for (const auto [start, end] :
       std::vector<std::pair<int, int>>{{0, 1}, {1, 2}, {2, 3},
                                        {1, 4}, {4, 3}}) {
    config.g4irsf24_dlp.insert_edge(start, end, 0.0, 1);
  }
  EventDrivenJunctionRuntime runtime(graph, config);
  const auto result = runtime.run(
      {{"fault-detour", 3, 0.0, 1000.0, 0, 3, "synthetic"}},
      {{2, 3, 0.0, 1000.0, 0.0, false}});
  checks.require(result.summary.completed_count == 1 &&
                     result.summary.failed_count == 0,
                 "surviving-graph guard must complete the local fault detour");
  const bool selected_detour = std::any_of(
      result.decisions.begin(), result.decisions.end(), [](const auto& row) {
        return row.current_node == 1 && row.selected_next == 4;
      });
  checks.require(
      selected_detour,
      "fault guard must use surviving H and permit the static-uphill detour");
}

Graph feng_dh_reimplementation_graph() {
  Graph graph;
  for (int node = 0; node < 8; ++node) {
    const double service = node == 3 || node == 4 ? 1.0 : 0.001;
    graph.add_node(czr005::ics::Node{node, 0, service, 0, 0, {}});
  }
  // Insert the larger tied continuation first: the baseline must still use
  // node 3, the lower next-node ID, for its deterministic free-flow path.
  for (const auto [start, end, length] :
       std::vector<std::tuple<int, int, double>>{
           {0, 1, 0.1}, {0, 2, 0.1}, {1, 4, 0.1}, {1, 3, 0.1},
           {3, 6, 0.1}, {4, 6, 0.1}, {5, 3, 0.1}, {2, 7, 0.1},
           {7, 6, 1.899}}) {
    graph.add_edge(czr005::ics::Edge{start, end, length, 1.0});
  }
  std::vector<std::vector<double>> heuristic(
      8, std::vector<double>(8, 0.0));
  heuristic[1][6] = 1.201;
  heuristic[2][6] = 2.001;
  heuristic[3][6] = 1.1;
  heuristic[4][6] = 1.1;
  heuristic[5][6] = 1.201;
  heuristic[7][6] = 1.9;
  graph.set_heuristic(std::move(heuristic));
  return graph;
}

void test_feng_dh_reimplementation_uses_frozen_moving_stopped_weights(
    Checks& checks) {
  const auto graph = feng_dh_reimplementation_graph();
  const auto run = [&](const std::string& mode,
                       double probe_release,
                       bool stop_at_bottleneck) {
    auto config = test_config();
    config.scorer_mode = mode;
    config.enable_source_admission = false;
    config.enable_backpressure = false;
    config.enable_pibt_lite = false;
    EventDrivenJunctionRuntime runtime(graph, config);
    const std::vector<EventRuntimeBagRequest> requests = {
        {"path-blocker", 9101, 0.0, 1000.0, 5, 6, "synthetic"},
        {"path-probe", 9102, probe_release, 1000.0, 0, 6, "synthetic"},
    };
    return stop_at_bottleneck
               ? runtime.run(
                     requests,
                     {{3, 6, 0.0, 3.0, 0.0, false}})
               : runtime.run(requests);
  };

  const auto control = run("S3_shortest_potential_only", 0.05, false);
  const auto moving = run(
      "FENG_DH_REIMPLEMENTATION_COEFFICIENTS_UNDISCLOSED", 0.05, false);
  const auto stopped = run(
      "FENG_DH_REIMPLEMENTATION_COEFFICIENTS_UNDISCLOSED", 1.2, true);
  const auto probe_at_zero = [](const auto& result) {
    return std::find_if(result.decisions.begin(), result.decisions.end(),
                        [](const auto& row) {
                          return row.segment_id == "path-probe" &&
                                 row.current_node == 0;
                        });
  };
  const auto control_probe = probe_at_zero(control);
  const auto moving_probe = probe_at_zero(moving);
  const auto stopped_probe = probe_at_zero(stopped);
  checks.require(
      control_probe != control.decisions.end() &&
          control_probe->selected_next == 1,
      "static shortest potential must select the uncongested shorter branch");
  checks.require(
      moving_probe != moving.decisions.end() &&
          moving_probe->selected_next == 2 &&
          stopped_probe != stopped.decisions.end() &&
          stopped_probe->selected_next == 2,
      "Feng-DH reimplementation must divert around both moving and stopped "
      "work on its deterministic free-flow path");

  const auto raw_score = [](const auto& decision, int next) {
    const auto candidate = std::find_if(
        decision.candidates.begin(), decision.candidates.end(),
        [&](const auto& row) { return row.next_node == next; });
    return candidate == decision.candidates.end()
               ? -1.0
               : candidate->scorer_raw_score;
  };
  if (moving_probe != moving.decisions.end() &&
      stopped_probe != stopped.decisions.end()) {
    checks.require(
        std::abs(raw_score(*moving_probe, 1) - 2.301) <= 1.0e-9,
        "moving work must add exactly service_time * 1 on the lower-ID tied "
        "free-flow continuation");
    checks.require(
        std::abs(raw_score(*stopped_probe, 1) - 3.301) <= 1.0e-9,
        "stopped work must add exactly service_time * 2");
  }
  checks.require(
      moving.summary.completed_count == 2 &&
          stopped.summary.completed_count == 2 &&
          moving.summary.failed_count == 0 && stopped.summary.failed_count == 0,
      "Feng-DH moving/stopped motif must fully drain");
  checks.require(
      moving.summary.scorer_id ==
              "FENG_DH_REIMPLEMENTATION_COEFFICIENTS_UNDISCLOSED_NOT_EXACT" &&
          moving.summary.scorer_runtime_global_scan_count > 0 &&
          moving.summary.runtime_full_astar_calls == 0,
      "Feng-DH summary must disclose non-exact identity and account live "
      "path scans without claiming A*");
}

Graph tarau_route_only_motif_graph() {
  Graph graph;
  for (int node = 0; node < 8; ++node) {
    const double service = node == 0 ? 0.001 : 1.0;
    graph.add_node(czr005::ics::Node{node, 0, service, 0, 0, {}});
  }
  for (const auto [start, end] :
       std::vector<std::pair<int, int>>{
           {0, 2}, {0, 1}, {1, 3}, {2, 4},
           {3, 5}, {4, 5}, {5, 6}, {3, 7}}) {
    graph.add_edge(czr005::ics::Edge{start, end, 1.0, 1.0});
  }
  graph.set_heuristic(
      std::vector<std::vector<double>>(8, std::vector<double>(8, 0.0)));
  return graph;
}

void test_tarau_route_only_uses_only_bounded_beacons(Checks& checks) {
  const auto graph = tarau_route_only_motif_graph();
  const auto run = [&](int beacon_node,
                       int queue_length,
                       int queued_goal,
                       int queue_length_for_goal) {
    auto config = test_config();
    config.scorer_mode =
        "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY";
    config.enable_source_admission = false;
    config.enable_backpressure = false;
    config.enable_pibt_lite = false;
    EventDrivenJunctionRuntime runtime(graph, config);
    runtime.initialize(
        {{"tarau-probe", 9201, 0.0, 1000.0, 0, 6, "synthetic"}});
    while (const auto boundary = runtime.peek_safe_boundary()) {
      if (boundary->next_event_type !=
          czr005::ics::JunctionEventType::kCongestionBeaconUpdate) {
        break;
      }
      runtime.process_one_event();
    }
    if (beacon_node >= 0) {
      runtime.test_set_tarau_congestion_beacon(
          beacon_node,
          queue_length,
          queued_goal,
          queue_length_for_goal);
    }
    runtime.drain();
    checks.require(
        runtime.test_tarau_forbidden_candidate_dynamic_read_count() == 0,
        "Tarau candidate construction must bypass the common live queue, "
        "scheduled-incoming, calendar, and two-hop snapshot path");
    return runtime.finalize();
  };

  const auto zero_flow = run(-1, 0, 6, 0);
  const auto two_hop_live = run(3, 5, 6, 0);
  // These bags have another destination, but their static next hop from v=1
  // is still w=3, so they consume the same physical v->w flow capacity.
  const auto other_goal_neighbor_flow = run(1, 5, 7, 5);
  const auto radius_three_only = run(5, 100, 6, 100);
  const auto check_motif_run = [&](const auto& result) {
    checks.require(
        result.summary.completed_count == 1 &&
            result.summary.failed_count == 0 &&
            result.summary.reservation_conflicts == 0 &&
            result.summary.runtime_full_astar_calls == 0 &&
            result.summary.global_reservation_scan_count == 0,
        "Tarau bounded-beacon motif must complete without global routing or "
        "reservation conflicts");
    for (const auto& decision : result.decisions) {
      checks.require(
          graph.has_edge(decision.current_node, decision.selected_next),
          "Tarau motif must select one real outgoing synthetic edge");
      for (const auto& candidate : decision.candidates) {
        checks.require(
            candidate.target_queue_length == 0 &&
                candidate.target_scheduled_incoming == 0 &&
                candidate.corridor_next_available == 0.0 &&
                candidate.target_next_available == 0.0 &&
                candidate.two_hop_queue_pressure == 0,
            "Tarau trace candidates must not materialize forbidden common "
            "dynamic-state features");
      }
    }
  };
  check_motif_run(zero_flow);
  check_motif_run(two_hop_live);
  check_motif_run(other_goal_neighbor_flow);
  check_motif_run(radius_three_only);

  const auto first_probe = [](const auto& result) {
    return std::find_if(result.decisions.begin(), result.decisions.end(),
                        [](const auto& row) {
                          return row.segment_id == "tarau-probe" &&
                                 row.current_node == 0;
                        });
  };
  const auto zero_decision = first_probe(zero_flow);
  const auto live_decision = first_probe(two_hop_live);
  const auto other_goal_decision = first_probe(other_goal_neighbor_flow);
  const auto far_decision = first_probe(radius_three_only);
  checks.require(
      zero_decision != zero_flow.decisions.end() &&
          zero_decision->selected_next == 1,
      "zero neighbour flow must reduce to the stable local free-flow "
      "Tarau route-only action");
  checks.require(
      live_decision != two_hop_live.decisions.end() &&
          live_decision->selected_next == 2,
      "changing only the radius-two w beacon must be able to change the "
      "route-only action");
  checks.require(
      other_goal_decision != other_goal_neighbor_flow.decisions.end() &&
          other_goal_decision->selected_next == 2,
      "other-goal bags advertised at v must count when their static next "
      "hop uses the same v->w flow");
  checks.require(
      far_decision != radius_three_only.decisions.end() &&
          far_decision->selected_next == 1,
      "a radius-three-only beacon change must not affect the current Tarau "
      "route-only action");
  if (zero_decision != zero_flow.decisions.end()) {
    for (const auto& candidate : zero_decision->candidates) {
      checks.require(
          std::abs(candidate.scorer_raw_score - 4.0) <= 1.0e-9,
          "zero-flow motif must implement tau(u,v)+max(tau(v,w),1/mu_w)"
          "+H_ff(w,g) exactly");
    }
  }
  checks.require(
      zero_flow.summary.scorer_id ==
              "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY" &&
          zero_flow.summary.scorer_runtime_global_scan_count == 0 &&
          two_hop_live.summary.scorer_runtime_global_scan_count == 0 &&
          other_goal_neighbor_flow.summary.scorer_runtime_global_scan_count ==
              0 &&
          radius_three_only.summary.scorer_runtime_global_scan_count == 0 &&
          zero_flow.summary.runtime_full_astar_calls == 0,
      "Tarau route-only evaluation must disclose its canonical ID and never "
      "perform a live global scan or runtime A*");
}

Graph tarau_goal_service_inversion_graph() {
  Graph graph;
  graph.add_node(czr005::ics::Node{0, 0, 0.001, 0, 0, {}});
  graph.add_node(czr005::ics::Node{1, 0, 0.001, 0, 0, {}});
  graph.add_node(czr005::ics::Node{2, 0, 0.001, 0, 0, {}});
  // A deliberately large goal service time must be irrelevant when goal
  // arrival itself completes the bag.
  graph.add_node(czr005::ics::Node{3, 0, 10.0, 0, 0, {}});
  for (const auto [start, end, travel] :
       std::vector<std::tuple<int, int, double>>{
           {0, 1, 2.0}, {0, 2, 1.0}, {1, 3, 0.1}, {2, 3, 2.0}}) {
    graph.add_edge(czr005::ics::Edge{start, end, travel, 1.0});
  }
  graph.set_heuristic(
      std::vector<std::vector<double>>(4, std::vector<double>(4, 0.0)));
  return graph;
}

void test_tarau_two_hop_goal_skips_goal_service_and_queue(Checks& checks) {
  const auto graph = tarau_goal_service_inversion_graph();
  auto config = test_config();
  config.scorer_mode =
      "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY";
  config.complete_on_goal_arrival = true;
  config.enable_source_admission = false;
  config.enable_backpressure = false;
  config.enable_pibt_lite = false;
  EventDrivenJunctionRuntime runtime(graph, config);
  runtime.initialize(
      {{"tarau-goal-service-inversion", 9203, 0.0, 1000.0, 0, 3,
        "synthetic"}});
  while (const auto boundary = runtime.peek_safe_boundary()) {
    if (boundary->next_event_type !=
        czr005::ics::JunctionEventType::kCongestionBeaconUpdate) {
      break;
    }
    runtime.process_one_event();
  }
  runtime.test_set_tarau_congestion_beacon(3, 1000, 3, 1000);
  runtime.drain();
  const auto result = runtime.finalize();

  const auto decision = std::find_if(
      result.decisions.begin(), result.decisions.end(), [](const auto& row) {
        return row.segment_id == "tarau-goal-service-inversion" &&
               row.current_node == 0;
      });
  checks.require(
      result.summary.completed_count == 1 &&
          result.summary.failed_count == 0 &&
          decision != result.decisions.end() &&
          decision->selected_next == 1,
      "Tarau must select the physically faster 2.1-second route instead of "
      "charging nonexistent goal service and selecting the 3-second route");
  if (decision != result.decisions.end()) {
    const auto score_for = [&](int next) {
      const auto candidate = std::find_if(
          decision->candidates.begin(),
          decision->candidates.end(),
          [&](const auto& row) { return row.next_node == next; });
      return candidate == decision->candidates.end()
                 ? -1.0
                 : candidate->scorer_raw_score;
    };
    checks.require(
        std::abs(score_for(1) - 2.1) <= 1.0e-9 &&
            std::abs(score_for(2) - 3.0) <= 1.0e-9,
        "a two-hop goal continuation must be pure travel time regardless of "
        "the goal service duration or goal beacon queue");
  }
  checks.require(
      runtime.test_tarau_forbidden_candidate_dynamic_read_count() == 0 &&
          result.summary.scorer_runtime_global_scan_count == 0,
      "the goal regression must retain the Tarau information boundary");
}

Graph tarau_high_outdegree_graph() {
  Graph graph;
  graph.add_node(czr005::ics::Node{0, 0, 0.001, 0, 0, {}});
  // Reverse insertion order deliberately differs from the required stable
  // next-node tie break.
  graph.add_node(czr005::ics::Node{100, 0, 1.0, 0, 0, {}});
  for (int node = 64; node >= 1; --node) {
    graph.add_node(czr005::ics::Node{node, 0, 1.0, 0, 0, {}});
    graph.add_edge(czr005::ics::Edge{node, 100, 1.0, 1.0});
    graph.add_edge(czr005::ics::Edge{0, node, 1.0, 1.0});
  }
  graph.set_heuristic(std::vector<std::vector<double>>(
      101, std::vector<double>(101, 0.0)));
  return graph;
}

void test_tarau_route_only_high_outdegree_stable_argmin(Checks& checks) {
  const auto graph = tarau_high_outdegree_graph();
  auto config = test_config();
  config.scorer_mode =
      "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY";
  config.enable_source_admission = false;
  config.enable_backpressure = false;
  config.enable_pibt_lite = false;
  EventDrivenJunctionRuntime runtime(graph, config);
  const auto result = runtime.run(
      {{"tarau-high-degree", 9202, 0.0, 1000.0, 0, 100, "synthetic"}});
  checks.require(
      result.summary.completed_count == 1 &&
          result.summary.failed_count == 0 &&
          result.summary.runtime_full_astar_calls == 0 &&
          result.summary.scorer_runtime_global_scan_count == 0,
      "Tarau high-outdegree motif must complete without a live global scan");
  const auto decision = std::find_if(
      result.decisions.begin(), result.decisions.end(), [](const auto& row) {
        return row.segment_id == "tarau-high-degree" &&
               row.current_node == 0;
      });
  checks.require(
      decision != result.decisions.end() &&
          decision->candidates.size() == 64 &&
          decision->selected_next == 1,
      "Tarau route-only must inspect all outgoing candidates and break an "
      "equal-cost high-degree tie by stable next-node ID");
  const auto goal_decision = std::find_if(
      result.decisions.begin(), result.decisions.end(), [](const auto& row) {
        return row.segment_id == "tarau-high-degree" &&
               row.current_node == 1;
      });
  checks.require(
      goal_decision != result.decisions.end() &&
          goal_decision->candidates.size() == 1 &&
          goal_decision->candidates.front().next_node == 100 &&
          std::abs(goal_decision->candidates.front().scorer_raw_score - 1.0) <=
              1.0e-9,
      "a direct goal candidate must use tau(u,g) without a second-hop "
      "service term");
}

Graph goal_arrival_completion_graph() {
  Graph graph;
  graph.add_node(czr005::ics::Node{0, 1, 1.0, 0, 0, {}});
  graph.add_node(czr005::ics::Node{1, 1, 1.0, 0, 0, {}});
  graph.add_node(czr005::ics::Node{2, 2, 100.0, 0, 0, {}});
  graph.add_edge(czr005::ics::Edge{0, 2, 2.0, 1.0});
  graph.add_edge(czr005::ics::Edge{1, 2, 2.0, 1.0});
  std::vector<std::vector<double>> heuristic(
      3, std::vector<double>(3, 0.0));
  heuristic[0][2] = 2.0;
  heuristic[1][2] = 2.0;
  graph.set_heuristic(std::move(heuristic));
  return graph;
}

void test_goal_arrival_completion_is_exact_off_and_skips_busy_goal_service(
    Checks& checks) {
  const auto graph = goal_arrival_completion_graph();
  const std::vector<EventRuntimeBagRequest> requests = {
      {"direct-a", 1, 0.0, 1000.0, 0, 2, "synthetic"},
      {"direct-b", 2, 0.0, 1000.0, 1, 2, "synthetic"},
  };

  auto off = test_config();
  EventDrivenJunctionRuntime implicit_off_runtime(graph, off);
  const auto implicit_off = implicit_off_runtime.run(requests);
  off.complete_on_goal_arrival = false;
  EventDrivenJunctionRuntime explicit_off_runtime(graph, off);
  const auto explicit_off = explicit_off_runtime.run(requests);
  checks.require(
      implicit_off.summary.event_count == explicit_off.summary.event_count &&
          implicit_off.bags.size() == explicit_off.bags.size(),
      "explicit false goal-arrival completion must preserve result shape");
  if (implicit_off.bags.size() == explicit_off.bags.size()) {
    for (std::size_t index = 0; index < implicit_off.bags.size(); ++index) {
      checks.require(
          implicit_off.bags[index].segment_id ==
                  explicit_off.bags[index].segment_id &&
              implicit_off.bags[index].finish_time ==
                  explicit_off.bags[index].finish_time,
          "explicit false goal-arrival completion must preserve finish times");
    }
  }

  auto active = off;
  active.complete_on_goal_arrival = true;
  EventDrivenJunctionRuntime active_runtime(graph, active);
  const auto result = active_runtime.run(requests);
  checks.require(result.summary.completed_count == 2 &&
                     result.summary.failed_count == 0,
                 "goal-arrival completion must drain both direct bags");
  checks.require(
      result.summary.complete_on_goal_arrival_enabled &&
          result.summary.complete_on_goal_arrival_claim_boundary ==
              "physical_goal_edge_exit_terminal;goal_service_not_reserved;"
              "legacy_HCA_Tasks_ICS_completion_semantics",
      "goal-arrival completion summary must echo the HCA-aligned seam");
  for (const auto& bag : result.bags) {
    checks.require(
        std::abs(bag.finish_time - 3.0) <= 1.0e-9 &&
            std::abs(bag.node_service_time_seconds - 1.0) <= 1.0e-9 &&
            std::abs(bag.edge_travel_time_seconds - 2.0) <= 1.0e-9,
        "goal arrival must complete after source service and final travel only");
  }
  const auto goal = std::find_if(
      result.junctions.begin(), result.junctions.end(),
      [](const auto& row) { return row.node == 2; });
  checks.require(
      goal != result.junctions.end() && goal->service_reservation_count == 0 &&
          goal->peak_service_calendar_intervals == 0 &&
          goal->scheduled_incoming == 0,
      "busy goal service must receive no reservation and retain no incoming");
  const auto off_goal = std::find_if(
      implicit_off.junctions.begin(), implicit_off.junctions.end(),
      [](const auto& row) { return row.node == 2; });
  checks.require(
      off_goal != implicit_off.junctions.end() &&
          off_goal->service_reservation_count == 2,
      "default semantics must retain the existing busy-goal service calendar");
}

}  // namespace

int main() {
  Checks checks;
  try {
    test_canonical_map2_fixture(checks);
    test_local_calendar_dynamic_accounting(checks);
    test_burst_sizes(checks);
    test_source_admission_toggle_uses_one_hop_beacon_pressure(checks);
    test_source_admission_same_time_event_order(checks);
    test_diagnostic_hops_are_read_only(checks);
    test_real_directed_corridor_competition(checks);
    test_loop_tabu_on_real_cycle(checks);
    test_non_goal_terminal_sink_is_locally_shielded(checks);
    test_non_goal_terminal_successor_trap_is_locally_shielded(checks);
    test_fault_repair_delay_and_escape(checks);
    test_wait_retries_do_not_consume_route_decision_budget(checks);
    test_delayed_fault_policy_handoff(checks);
    test_fault_policy_toggle_keeps_physical_interlock_independent(checks);
    test_deterministic_trace_shards(checks);
    test_duplicate_original_task_segments_keep_internal_identity(checks);
    test_explicit_sensor_loss_keeps_physical_shield(checks);
    test_bounded_pibt_sensor_loss_uses_local_fault_handoff(checks);
    test_g4irsf16_fault_generation_survives_repair_boost_reset(checks);
    test_g4irsf16_learned_model_closed_loop_is_not_self_authorizing(checks);
    test_legacy_observation_bias_is_local_deterministic_and_exact_off(checks);
    test_storage_source_role_default_is_map2_compatible(checks);
    test_s4_component_mask_and_queue_time_scaling_motif(checks);
    test_s4_direct_neighbor_merge_calendar_visibility_is_exact_off_and_local(
        checks);
    test_s4_local_descent_guard_is_exact_off_and_blocks_cycle(checks);
    test_s4_local_descent_guard_uses_surviving_fault_potential(checks);
    test_feng_dh_reimplementation_uses_frozen_moving_stopped_weights(checks);
    test_tarau_route_only_uses_only_bounded_beacons(checks);
    test_tarau_two_hop_goal_skips_goal_service_and_queue(checks);
    test_tarau_route_only_high_outdegree_stable_argmin(checks);
    test_goal_arrival_completion_is_exact_off_and_skips_busy_goal_service(
        checks);
  } catch (const std::exception& error) {
    ++checks.failures;
    std::cerr << "FAIL: canonical map2 test setup/runtime exception: " << error.what() << '\n';
  }
  return checks.failures == 0 ? 0 : 1;
}
