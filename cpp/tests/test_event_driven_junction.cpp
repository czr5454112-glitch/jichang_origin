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

#ifndef CZR005_G4IRSF32_BUILD_HEAD
#define CZR005_G4IRSF32_BUILD_HEAD "UNBOUND"
#endif

#include "ics_core/io/canonical_map2_reader.hpp"
#define CZR005_EVENT_RUNTIME_TESTING 1
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

struct V3R2NativeProof {
  bool pure_calendar_helper = false;
  bool generic_storage_role_validation = false;
  bool direct_unique_publish = false;
  bool j2_unique_publish = false;
  bool j2_direct_duplicate_suppressed = false;
  bool direct_after_stage_rollback_exact = false;
  bool j2_after_stage_rollback_exact = false;
  bool trace_limit_fail_before_commit = false;
  bool action_inert_invariants = false;
};

V3R2NativeProof v3r2_proof;

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

EventDrivenJunctionConfig v3r2_shadow_config() {
  EventDrivenJunctionConfig config;
  config.queue_discipline = "fifo";
  config.retry_interval = 0.25;
  config.minimum_service_seconds = 0.001;
  config.dispatch_headway_seconds = 0.001;
  config.history_limit = 8;
  config.max_decisions_per_bag = 512;
  config.max_events = 2000000;
  config.max_simulation_time = -1.0;
  config.trace_limit = 200000;
  config.event_trace_limit = 200000;
  config.local_queue_capacity = 0;
  config.deadlock_retry_threshold = 8;
  config.diagnostic_hops = 2;
  config.enable_source_admission = false;
  config.enable_backpressure = false;
  config.enable_pibt_lite = false;
  config.enable_deadlock_escape = true;
  config.enable_fault_policy = true;
  config.resource_semantics = "R3_java_node_window_compatible";
  config.entry_headway_seconds = 0.001;
  config.pressure_mode = "off";
  config.admission_mode = "off";
  config.pibt_mode = "P2";
  config.priority_mode = "Q0";
  config.pibt_preference_mode = "current";
  config.scorer_mode = "S4_queue_aware_rule_only";
  config.framework_mode = "event_loop_one_step";
  config.event_semantics = "E4_batch_plus_destination_merge_request";
  config.merge_grant_rule = "M3";
  config.merge_grant_timing_mode = "jit_fair_aging_deadline";
  config.merge_grant_max_pending_requests = 256;
  config.merge_grant_lifecycle_limit = 8192;
  config.g4irsf20_event_hotpath_policy = "E2";
  config.enable_opportunity_telemetry = false;
  config.opportunity_trace_limit = 0;
  config.enable_s4_local_potential_descent_guard = true;
  config.enable_s4_direct_neighbor_merge_calendar_visibility = true;
  config.complete_on_goal_arrival = true;
  config.storage_source_nodes = {0};
  config.source_aware_destination_service_mode = "shadow";
  config.source_aware_destination_service_trace_limit = 200000;
  return config;
}

Graph v3r2_slot_pair_graph(bool j2) {
  Graph graph;
  graph.add_node(czr005::ics::Node{0, 7, 0.0, 0, 0, {1}});
  graph.add_node(czr005::ics::Node{1, 1, 1.0, 1, 0, {2}});
  graph.add_node(czr005::ics::Node{2, 4, 0.0, 2, 0, {3}});
  graph.add_node(czr005::ics::Node{3, 2, 0.0, 3, 0, {}});
  if (j2) {
    graph.add_node(czr005::ics::Node{4, 7, 0.0, 0, 1, {1}});
  }
  graph.add_edge(czr005::ics::Edge{0, 1, 0.05, 1.0});
  graph.add_edge(czr005::ics::Edge{1, 2, 0.05, 1.0});
  graph.add_edge(czr005::ics::Edge{2, 3, 0.05, 1.0});
  if (j2) {
    graph.add_edge(czr005::ics::Edge{4, 1, 0.05, 1.0});
  }
  const int size = j2 ? 5 : 4;
  std::vector<std::vector<double>> heuristic(
      size, std::vector<double>(size, 1000.0));
  for (int node = 0; node < size; ++node) {
    heuristic[node][node] = 0.0;
  }
  heuristic[0][3] = 1.15;
  heuristic[1][3] = 0.10;
  heuristic[2][3] = 0.05;
  if (j2) {
    heuristic[4][3] = 1.15;
  }
  graph.set_heuristic(std::move(heuristic));
  return graph;
}

std::vector<EventRuntimeBagRequest> v3r2_slot_pair_requests() {
  return {
      {"v3r2-local-first", 32032001, 0.0, 100.0, 1, 3, "local"},
      {"v3r2-local-winner", 32032002, 0.0, 100.0, 1, 3, "local"},
      {"v3r2-external", 32032000, 0.699, 100.0, 0, 3, "external"},
  };
}

bool v3r2_census_is_zero(const czr005::ics::EventRuntimeSummary& summary) {
  return summary
                 .source_aware_destination_service_external_commit_considered_count ==
             0 &&
         summary.source_aware_destination_service_observation_stored_count == 0 &&
         summary.source_aware_destination_service_observation_dropped_count == 0 &&
         summary.source_aware_destination_service_direct_external_commit_count == 0 &&
         summary.source_aware_destination_service_j2_exact_commit_count == 0 &&
         summary.source_aware_destination_service_no_local_count == 0 &&
         summary.source_aware_destination_service_local_guard_fail_count == 0 &&
         summary.source_aware_destination_service_non_overlap_count == 0 &&
         summary.source_aware_destination_service_staged_rollback_count == 0 &&
         summary.source_aware_destination_service_action_change_count == 0 &&
         summary.source_aware_destination_service_calendar_mutation_count == 0 &&
         summary.source_aware_destination_service_future_release_read_count == 0 &&
         summary.source_aware_destination_service_global_scan_count == 0;
}

bool v3r2_resource_fields_are_zero(
    const czr005::ics::EventRuntimeSummary& summary) {
  return summary
                 .source_aware_destination_service_incremental_local_state_bytes ==
             0 &&
         summary
                 .source_aware_destination_service_runtime_internal_accounted_bytes ==
             0 &&
         summary
                 .source_aware_destination_service_trace_sidecar_accounted_bytes ==
             0 &&
         summary.source_aware_destination_service_total_accounted_bytes == 0;
}

bool v3r4_local_telemetry_is_exact(
    const czr005::ics::EventRuntimeSourceAwareDestinationServiceShadowRow& row) {
  return row.local_source_ready_count > 0 &&
         row.local_choose_bag_index < row.local_source_ready_count &&
         std::abs(row.local_source_uncovered_service_work_seconds -
                  static_cast<double>(row.local_source_ready_count) *
                      row.local_service_seconds) < 1.0e-12 &&
         row.external_scheduled_incoming_count >= 0 &&
         std::isfinite(row.oldest_local_wait_age_seconds) &&
         row.oldest_local_wait_age_seconds >= 0.0 &&
         std::isfinite(row.oldest_external_wait_age_seconds) &&
         row.oldest_external_wait_age_seconds >= 0.0 &&
         (row.destination_pending_count != 0 ||
          row.oldest_external_wait_age_seconds == 0.0) &&
         std::abs(row.service_calendar_next_free_seconds - row.L0) <
             1.0e-12 &&
         std::abs(row.existing_calendar_wait_seconds -
                  (row.L0 - row.event_time)) < 1.0e-12 &&
         row.selected_action_from_node == row.external_upstream_node &&
         row.selected_action_to_node == row.node &&
         row.selected_action_kind_code == row.seam_kind_code &&
         row.local_origin_code == 1U && row.external_origin_code == 2U;
}

void test_v3r2_pure_helper_and_storage_roles(Checks& checks) {
  czr005::ics::event_runtime_detail::LocalCalendar calendar;
  calendar.reserve(1, 2.0, 3.0);
  calendar.reserve(2, 5.0, 6.0);
  const auto generation = calendar.generation();
  const auto size = calendar.size();
  const bool pure =
      calendar.earliest_start(0.0, 1.0) == 0.0 &&
      calendar.earliest_start_with_hypothetical(0.0, 1.0, 0.5, 1.5) ==
          3.0 &&
      calendar.generation() == generation && calendar.size() == size;
  checks.require(pure, "V3R2 pure L1 helper must not mutate or copy C");
  v3r2_proof.pure_calendar_helper = pure;

  const auto graph = v3r2_slot_pair_graph(true);
  const auto rejects = [&](std::string mode, std::vector<int> storage) {
    auto config = v3r2_shadow_config();
    config.source_aware_destination_service_mode = std::move(mode);
    config.storage_source_nodes = std::move(storage);
    try {
      EventDrivenJunctionRuntime runtime(graph, config);
      (void)runtime;
      return false;
    } catch (const std::invalid_argument&) {
      return true;
    }
  };
  const bool roles = rejects("enabled", {0, 4}) &&
                     rejects("shadow", {}) &&
                     rejects("shadow", {0, 0}) &&
                     !rejects("shadow", {1}) &&
                     rejects("shadow", {2});
  checks.require(
      roles,
      "V3R2 must fail closed on mode and generic storage-role violations");
  v3r2_proof.generic_storage_role_validation = roles;
}

void test_v3r2_direct_and_action_inert(Checks& checks) {
  const auto graph = v3r2_slot_pair_graph(false);
  const auto requests = v3r2_slot_pair_requests();
  auto off_config = v3r2_shadow_config();
  off_config.source_aware_destination_service_mode = "off";
  EventDrivenJunctionRuntime off_runtime(graph, off_config);
  const auto off = off_runtime.run(requests);
  EventDrivenJunctionRuntime shadow_runtime(graph, v3r2_shadow_config());
  const auto shadow = shadow_runtime.run(requests);
  const auto direct_count = std::count_if(
      shadow.source_aware_destination_service_shadow.begin(),
      shadow.source_aware_destination_service_shadow.end(),
      [](const auto& row) { return row.seam_kind_code == 1U; });
  const auto direct = std::find_if(
      shadow.source_aware_destination_service_shadow.begin(),
      shadow.source_aware_destination_service_shadow.end(),
      [](const auto& row) { return row.seam_kind_code == 1U; });
  const bool row_valid =
      direct_count == 1 &&
      direct != shadow.source_aware_destination_service_shadow.end() &&
      direct->external_path_code == 1U &&
      direct->has_direct_episode_identity && !direct->has_j2_identity &&
      direct->external_direct_episode_event_seq == direct->event_seq &&
      direct->local_guards_passed && direct->local_task_id == 32032002 &&
      direct->local_runtime_bag_id == 1 &&
      direct->local_choose_bag_index == 0 &&
      direct->local_escape_token_runtime_bag_id == -1 &&
      v3r4_local_telemetry_is_exact(*direct) &&
      direct->local_source_ready_count == 1 &&
      direct->destination_pending_count == 0 &&
      direct->oldest_external_wait_age_seconds == 0.0 &&
      std::abs(direct->oldest_local_wait_age_seconds -
               (direct->event_time - direct->local_source_enqueued_at)) <
          1.0e-12 &&
      std::abs(direct->local_release) < 1.0e-12 &&
      std::abs(direct->local_deadline - 100.0) < 1.0e-12 &&
      std::abs(direct->local_source_enqueued_at) < 1.0e-12 &&
      std::abs(direct->L0 - 1.0) < 1.0e-12 &&
      std::abs(direct->L1 - 2.0) < 1.0e-12 && direct->X_insert > 0.0 &&
      direct->overlap_seconds > 0.0 &&
      std::abs(direct->X_insert - (direct->L1 - direct->L0)) < 1.0e-12 &&
      std::abs(direct->H_gap -
               (direct->L1 - direct->external_slot_start_seconds)) <
          1.0e-12;
  checks.require(row_valid, "V3R2 DIRECT must publish one exact algebra row");
  v3r2_proof.direct_unique_publish = row_valid;

  const auto off_replay = off_runtime.deterministic_replay_hashes();
  const auto shadow_replay = shadow_runtime.deterministic_replay_hashes();
  const bool inert =
      off_replay.segment_result_sha256 == shadow_replay.segment_result_sha256 &&
      off_replay.junction_state_sha256 == shadow_replay.junction_state_sha256 &&
      off_replay.deterministic_result_sha256 ==
          shadow_replay.deterministic_result_sha256 &&
      off.events.size() == shadow.events.size() &&
      off.decisions.size() == shadow.decisions.size() &&
      direct != shadow.source_aware_destination_service_shadow.end() &&
      !direct->action_changed && direct->future_release_read_count == 0 &&
      direct->global_scan_count == 0 && direct->calendar_mutation_count == 0 &&
      shadow.summary.source_aware_destination_service_action_change_count == 0 &&
      shadow.summary.source_aware_destination_service_calendar_mutation_count == 0;
  checks.require(inert, "V3R2 shadow must preserve ordinary state and replay hashes");
  v3r2_proof.action_inert_invariants = inert;
}

void test_v3r13_candidate_a_closed_loop(Checks& checks) {
  const auto run_case = [](bool j2,
                           double local_deadline,
                           double pending_deadline) {
    auto config = v3r2_shadow_config();
    config.queue_discipline = "deadline";
    config.source_aware_destination_service_mode = "closed_loop";
    config.storage_source_nodes = j2 ? std::vector<int>{0, 4}
                                     : std::vector<int>{0};
    std::vector<EventRuntimeBagRequest> requests = {
        {"v3r13-external-committed", 32033001, 0.0, 100.0, 0, 3,
         "external"},
        {"v3r13-local", 32033002, 0.1, local_deadline, 1, 3, "local"},
        {"v3r13-external-contender", 32033003, j2 ? 0.05 : 0.2,
         pending_deadline, j2 ? 4 : 0, 3, "external"},
    };
    const auto graph = v3r2_slot_pair_graph(j2);
    EventDrivenJunctionRuntime runtime(graph, config);
    return runtime.run(requests);
  };
  const auto direct = run_case(false, 10.0, 100.0);
  const auto j2_local = run_case(true, 10.0, 100.0);
  const auto j2_external = run_case(true, 100.0, 1.0);

  const auto action_is_exact = [](const auto& result) {
    const auto local = std::find_if(
        result.bags.begin(), result.bags.end(), [](const auto& bag) {
          return bag.segment_id == "v3r13-local";
        });
    const auto action = std::find_if(
        result.events.begin(), result.events.end(), [](const auto& event) {
          return event.segment_id == "v3r13-local" &&
                 event.reason == "source_closed_loop_future_slot";
        });
    return result.summary.completed_count == 3 &&
           result.summary.reservation_conflicts == 0 &&
           result.summary
                   .source_aware_destination_service_action_change_count ==
               1 &&
           result.summary
                   .source_aware_destination_service_calendar_mutation_count ==
               1 &&
           result.summary
                   .source_aware_destination_service_future_release_read_count ==
               0 &&
           result.summary
                   .source_aware_destination_service_global_scan_count == 0 &&
           result.source_aware_destination_service_shadow.empty() &&
           local != result.bags.end() && local->completed &&
           local->admitted_time > local->release_time &&
           action != result.events.end() &&
           std::abs(action->time - local->admitted_time) < 1.0e-12;
  };
  checks.require(action_is_exact(direct),
                 "V3R13 DIRECT must commit one future local owner");
  checks.require(action_is_exact(j2_local),
                 "V3R13 J2 must commit one strictly-prior local owner");
  const auto reverse_local = std::find_if(
      j2_external.bags.begin(), j2_external.bags.end(), [](const auto& bag) {
        return bag.segment_id == "v3r13-local";
      });
  const auto reverse_external = std::find_if(
      j2_external.bags.begin(), j2_external.bags.end(), [](const auto& bag) {
        return bag.segment_id == "v3r13-external-contender";
      });
  checks.require(
      j2_external.summary.completed_count == 3 &&
          j2_external.summary.reservation_conflicts == 0 &&
          reverse_local != j2_external.bags.end() &&
          reverse_external != j2_external.bags.end() &&
          reverse_external->finish_time < reverse_local->finish_time,
      "V3R13 J2 must preserve an earlier-deadline external winner");

  auto bounded_config = v3r2_shadow_config();
  bounded_config.queue_discipline = "deadline";
  bounded_config.local_queue_capacity = 1;
  bounded_config.source_aware_destination_service_mode = "closed_loop";
  const auto bounded_graph = v3r2_slot_pair_graph(false);
  EventDrivenJunctionRuntime bounded_runtime(bounded_graph, bounded_config);
  const auto bounded = bounded_runtime.run(
      {{"v3r13-bounded-external", 32033005, 0.0, 100.0, 0, 3,
        "external"},
       {"v3r13-bounded-local", 32033006, 0.1, 10.0, 1, 3, "local"}});
  checks.require(
      bounded.summary.completed_count == 2 &&
          bounded.summary
                  .source_aware_destination_service_action_change_count == 0,
      "V3R13 finite-capacity configuration must keep ordinary admission");

  auto no_external_config = v3r2_shadow_config();
  no_external_config.source_aware_destination_service_mode = "closed_loop";
  const auto no_external_graph = v3r2_slot_pair_graph(false);
  EventDrivenJunctionRuntime no_external_runtime(
      no_external_graph, no_external_config);
  const auto no_external = no_external_runtime.run(
      {{"v3r13-local-only", 32033004, 0.0, 10.0, 1, 3, "local"}});
  checks.require(
      no_external.summary.completed_count == 1 &&
          no_external.summary
                  .source_aware_destination_service_action_change_count == 0,
      "V3R13 local-only control must remain a no-op");
}

Graph v3r15_commit_recheck_graph(bool j2) {
  Graph graph;
  graph.add_node(czr005::ics::Node{0, 7, 0.0, 0, 0, {1}});
  graph.add_node(czr005::ics::Node{1, 1, 1.0, 1, 0, {2}});
  graph.add_node(czr005::ics::Node{2, 4, 0.0, 2, 0, {3}});
  graph.add_node(czr005::ics::Node{3, 2, 0.0, 3, 0, {}});
  if (j2) {
    graph.add_node(czr005::ics::Node{4, 7, 0.0, 0, 1, {1}});
  }
  graph.add_edge(czr005::ics::Edge{0, 1, 0.799, 1.0});
  graph.add_edge(czr005::ics::Edge{1, 2, 0.05, 1.0});
  graph.add_edge(czr005::ics::Edge{2, 3, 0.05, 1.0});
  if (j2) {
    graph.add_edge(czr005::ics::Edge{4, 1, 1.699, 1.0});
  }
  const int size = j2 ? 5 : 4;
  std::vector<std::vector<double>> heuristic(
      size, std::vector<double>(size, 1000.0));
  for (int node = 0; node < size; ++node) {
    heuristic[node][node] = 0.0;
  }
  heuristic[0][3] = 1.899;
  heuristic[1][3] = 0.10;
  heuristic[2][3] = 0.05;
  if (j2) {
    heuristic[4][3] = 2.799;
  }
  graph.set_heuristic(std::move(heuristic));
  return graph;
}

void test_v3r15_candidate_a_commit_recheck(Checks& checks) {
  const auto run = [](bool j2,
                      const std::string& mode,
                      std::vector<EventRuntimeBagRequest> requests) {
    auto config = v3r2_shadow_config();
    config.queue_discipline = "deadline";
    config.source_aware_destination_service_mode = mode;
    config.storage_source_nodes =
        j2 ? std::vector<int>{0, 4} : std::vector<int>{0};
    const auto graph = v3r15_commit_recheck_graph(j2);
    EventDrivenJunctionRuntime runtime(graph, config);
    return runtime.run(requests);
  };
  const auto direct_requests =
      std::vector<EventRuntimeBagRequest>{
          {"v3r15-direct-owner", 32035001, 0.0, 100.0, 1, 3,
           "local"},
          {"v3r15-direct-local", 32035002, 0.1, 10.0, 1, 3,
           "local"},
          {"v3r15-direct-external", 32035003, 0.2, 100.0, 0, 3,
           "external"},
      };
  const auto direct_old = run(false, "closed_loop", direct_requests);
  const auto direct_recheck =
      run(false, "closed_loop_commit_recheck", direct_requests);
  const auto source_arbitration_time = [](const auto& result,
                                          const std::string& segment_id) {
    const auto event = std::find_if(
        result.events.begin(), result.events.end(),
        [&](const auto& row) {
          return row.segment_id == segment_id &&
                 row.reason == "same_timestamp_source_arbitration";
        });
    return event == result.events.end()
               ? std::numeric_limits<double>::infinity()
               : event->time;
  };
  checks.require(
      direct_old.summary.completed_count == 3 &&
          direct_recheck.summary.completed_count == 3 &&
          direct_old.summary.reservation_conflicts == 0 &&
          direct_recheck.summary.reservation_conflicts == 0 &&
          direct_old.summary
                  .source_aware_destination_service_action_change_count ==
              1 &&
          direct_recheck.summary
                  .source_aware_destination_service_action_change_count ==
              1 &&
          direct_recheck.summary
                  .source_aware_destination_service_calendar_mutation_count ==
              1 &&
          direct_old.summary
                  .superseded_arbitration_event_rejected_count == 0 &&
          direct_recheck.summary
                  .superseded_arbitration_event_rejected_count == 1 &&
          std::abs(source_arbitration_time(
                       direct_old, "v3r15-direct-local") -
                   1.0) < 1.0e-12 &&
          std::abs(source_arbitration_time(
                       direct_recheck, "v3r15-direct-local") -
                   0.201) < 1.0e-12,
      "V3R15 DIRECT commit must retime exactly one pending source wake");

  const auto no_source = run(
      false,
      "closed_loop_commit_recheck",
      {{"v3r15-no-source-external", 32035008, 0.2, 100.0, 0, 3,
        "external"}});
  checks.require(
      no_source.summary.completed_count == 1 &&
          no_source.summary
                  .source_aware_destination_service_action_change_count == 0 &&
          no_source.summary
                  .source_aware_destination_service_calendar_mutation_count ==
              0 &&
          no_source.summary
                  .superseded_arbitration_event_rejected_count == 0,
      "V3R15 commit recheck must be inert without a ready source queue");

  const auto j2_requests =
      std::vector<EventRuntimeBagRequest>{
          {"v3r15-j2-owner", 32035004, 0.0, 100.0, 1, 3, "local"},
          {"v3r15-j2-local", 32035005, 0.1, 10.0, 1, 3, "local"},
          {"v3r15-j2-first", 32035006, 0.2, 50.0, 0, 3,
           "external"},
          {"v3r15-j2-later", 32035007, 0.3, 100.0, 4, 3,
           "external"},
      };
  const auto j2_old = run(true, "closed_loop", j2_requests);
  const auto j2_recheck =
      run(true, "closed_loop_commit_recheck", j2_requests);
  const auto find_bag = [](const auto& result,
                           const std::string& segment_id) {
    return std::find_if(
        result.bags.begin(), result.bags.end(),
        [&](const auto& bag) { return bag.segment_id == segment_id; });
  };
  const auto old_local = find_bag(j2_old, "v3r15-j2-local");
  const auto new_local = find_bag(j2_recheck, "v3r15-j2-local");
  const auto old_first = find_bag(j2_old, "v3r15-j2-first");
  const auto new_first = find_bag(j2_recheck, "v3r15-j2-first");
  const auto new_later = find_bag(j2_recheck, "v3r15-j2-later");
  checks.require(
      j2_old.summary.completed_count == 4 &&
          j2_recheck.summary.completed_count == 4 &&
          j2_old.summary.reservation_conflicts == 0 &&
          j2_recheck.summary.reservation_conflicts == 0 &&
          j2_recheck.summary
                  .source_aware_destination_service_action_change_count ==
              1 &&
          j2_recheck.summary
                  .source_aware_destination_service_calendar_mutation_count ==
              1 &&
          j2_recheck.summary
                  .source_aware_destination_service_future_release_read_count ==
              0 &&
          j2_recheck.summary
                  .source_aware_destination_service_global_scan_count == 0 &&
          old_local != j2_old.bags.end() &&
          new_local != j2_recheck.bags.end() &&
          old_first != j2_old.bags.end() &&
          new_first != j2_recheck.bags.end() &&
          new_later != j2_recheck.bags.end() &&
          std::abs(old_local->admitted_time - 3.0) < 1.0e-12 &&
          std::abs(new_local->admitted_time - 2.0) < 1.0e-12 &&
          std::abs(old_first->finish_time - new_first->finish_time) <
              1.0e-12 &&
          new_first->finish_time < new_local->finish_time &&
          new_local->finish_time < new_later->finish_time,
      "V3R15 J2 recheck must preserve the committed winner and one local owner");
}

void test_v3r14_uncovered_local_work_helper(Checks& checks) {
  const auto work =
      czr005::ics::event_runtime_detail::uncovered_local_work_seconds;
  checks.require(
      work(0, 1.0, true) == 0.0 &&
          work(1, 1.0, true) == 1.0 &&
          work(2, 1.0, true) == 2.0 &&
          work(0, 3.0, true) == 0.0 &&
          work(1, 3.0, true) == 3.0 &&
          work(2, 3.0, true) == 6.0 &&
          work(2, 3.0, false) == 0.0,
      "V3R14 uncovered-work helper must be exact and resource-gated");
}

Graph v3r14_uncovered_work_graph() {
  Graph graph;
  for (int node = 0; node < 4; ++node) {
    graph.add_node(czr005::ics::Node{
        node, 0, node == 1 ? 3.0 : 0.001, 0, 0, {}});
  }
  for (const auto [start, end] :
       std::vector<std::pair<int, int>>{
           {0, 1}, {0, 2}, {1, 3}, {2, 3}}) {
    graph.add_edge(czr005::ics::Edge{start, end, 1.0, 1.0});
  }
  std::vector<std::vector<double>> heuristic(
      4, std::vector<double>(4, 0.0));
  heuristic[0][3] = 4.0;
  heuristic[1][3] = 0.1;
  heuristic[2][3] = 2.5;
  graph.set_heuristic(std::move(heuristic));
  return graph;
}

void test_v3r14_candidate_b_score_and_ranking(Checks& checks) {
  const auto graph = v3r14_uncovered_work_graph();
  const auto run = [&](const std::string& scorer_mode,
                       bool include_future_release) {
    auto config = v3r2_shadow_config();
    config.scorer_mode = scorer_mode;
    config.source_aware_destination_service_mode = "off";
    config.queue_discipline = "fifo";
    config.storage_source_nodes = {1};
    std::vector<EventRuntimeBagRequest> requests = {
        {"v3r14-local-owner", 32034001, 0.0, 1000.0, 1, 3,
         "synthetic"},
        {"v3r14-local-uncovered", 32034002, 0.0, 1000.0, 1, 3,
         "synthetic"},
        {"v3r14-probe", 32034003, 0.1, 1000.0, 0, 3,
         "synthetic"},
    };
    if (include_future_release) {
      requests.push_back(
          {"v3r14-future-local", 32034004, 100.0, 1000.0, 1, 3,
           "synthetic"});
    }
    EventDrivenJunctionRuntime runtime(graph, config);
    return runtime.run(requests);
  };
  const auto old_s4 = run("S4_queue_aware_rule_only", false);
  const auto candidate_b = run(
      "S4_uncovered_local_work_seconds_rule_only", false);
  const auto candidate_b_with_future = run(
      "S4_uncovered_local_work_seconds_rule_only", true);

  const auto probe = [](const auto& result) {
    return std::find_if(
        result.decisions.begin(), result.decisions.end(), [](const auto& row) {
          return row.segment_id == "v3r14-probe" && row.current_node == 0;
        });
  };
  const auto candidate = [](const auto& decision, int next_node) {
    return std::find_if(
        decision.candidates.begin(), decision.candidates.end(),
        [next_node](const auto& row) { return row.next_node == next_node; });
  };
  const auto old_probe = probe(old_s4);
  const auto new_probe = probe(candidate_b);
  const auto future_probe = probe(candidate_b_with_future);
  checks.require(
      old_probe != old_s4.decisions.end() &&
          new_probe != candidate_b.decisions.end() &&
          future_probe != candidate_b_with_future.decisions.end(),
      "V3R14 score fixture must expose the probe decision");
  if (old_probe == old_s4.decisions.end() ||
      new_probe == candidate_b.decisions.end() ||
      future_probe == candidate_b_with_future.decisions.end()) {
    return;
  }

  const auto old_one = candidate(*old_probe, 1);
  const auto new_one = candidate(*new_probe, 1);
  const auto new_two = candidate(*new_probe, 2);
  const auto future_one = candidate(*future_probe, 1);
  checks.require(
      old_one != old_probe->candidates.end() &&
          new_one != new_probe->candidates.end() &&
          new_two != new_probe->candidates.end() &&
          future_one != future_probe->candidates.end(),
      "V3R14 score fixture must retain both legal direct neighbours");
  if (old_one == old_probe->candidates.end() ||
      new_one == new_probe->candidates.end() ||
      new_two == new_probe->candidates.end() ||
      future_one == future_probe->candidates.end()) {
    return;
  }

  const auto calendar_wait = [](const auto& decision, const auto& row) {
    return std::max(
               0.0, row.corridor_next_available - decision.event_time) +
           std::max(0.0,
                    row.target_next_available -
                        (decision.event_time + row.travel_time));
  };
  const double old_expected =
      old_one->travel_time + old_one->static_potential +
      static_cast<double>(old_one->target_queue_length +
                          old_one->target_scheduled_incoming) +
      calendar_wait(*old_probe, *old_one);
  const double new_expected =
      new_one->travel_time + new_one->static_potential +
      czr005::ics::event_runtime_detail::uncovered_local_work_seconds(
          1, 3.0, true) +
      calendar_wait(*new_probe, *new_one);
  checks.require(
      std::abs(old_one->scorer_raw_score - old_expected) < 1.0e-12,
      "old S4 raw score must retain its exact frozen formula");
  checks.require(
      std::abs(new_one->scorer_raw_score - new_expected) < 1.0e-12 &&
          new_one->target_queue_length == 0 &&
          new_one->target_scheduled_incoming == 0 &&
          calendar_wait(*new_probe, *new_one) > 0.0,
      "Candidate B must add only ready uncovered work beside calendar wait");
  checks.require(
      old_probe->selected_next == 1 && new_probe->selected_next == 2 &&
          old_probe->scorer_raw_prediction == 1 &&
          new_probe->scorer_raw_prediction == 2,
      "Candidate B must change ranking when only uncovered work differs");
  checks.require(
      std::abs(future_one->scorer_raw_score -
               new_one->scorer_raw_score) < 1.0e-12,
      "a future-release local bag must not contribute before release");
  checks.require(
      candidate_b.summary.scorer_id ==
              "S4_uncovered_local_work_seconds_rule_only" &&
          new_probe->scorer_id ==
              "S4_uncovered_local_work_seconds_rule_only" &&
          candidate_b.summary.completed_count == 3 &&
          candidate_b.summary.failed_count == 0 &&
          candidate_b.summary.reservation_conflicts == 0 &&
          candidate_b.summary.runtime_full_astar_calls == 0 &&
          candidate_b.summary.global_reservation_scan_count == 0 &&
          candidate_b.summary.two_step_reservation_count == 0 &&
          candidate_b.summary.max_edges_selected_per_arrive <= 1,
      "Candidate B must remain the safe one-hop S4 family");
}

void test_v3r16_s4_plus_uncovered_local_work(Checks& checks) {
  const auto graph = v3r14_uncovered_work_graph();
  const auto run = [&](const std::string& scorer_mode,
                       int uncovered_ready_count) {
    auto config = v3r2_shadow_config();
    config.scorer_mode = scorer_mode;
    config.source_aware_destination_service_mode = "off";
    config.queue_discipline = "fifo";
    config.storage_source_nodes = {1};
    std::vector<EventRuntimeBagRequest> requests = {
        {"v3r16-local-owner", 32036001, 0.0, 1000.0, 1, 3,
         "synthetic"},
    };
    for (int index = 0; index < uncovered_ready_count; ++index) {
      requests.push_back(
          {"v3r16-local-uncovered-" + std::to_string(index),
           32036002 + index, 0.0, 1000.0, 1, 3, "synthetic"});
    }
    requests.push_back(
        {"v3r16-probe", 32036010, 0.1, 1000.0, 0, 3,
         "synthetic"});
    EventDrivenJunctionRuntime runtime(graph, config);
    return runtime.run(requests);
  };
  const auto probe = [](const auto& result) {
    return std::find_if(
        result.decisions.begin(), result.decisions.end(), [](const auto& row) {
          return row.segment_id == "v3r16-probe" && row.current_node == 0;
        });
  };
  const auto candidate = [](const auto& decision, int next_node) {
    return std::find_if(
        decision.candidates.begin(), decision.candidates.end(),
        [next_node](const auto& row) { return row.next_node == next_node; });
  };
  const auto old_zero = run("S4_queue_aware_rule_only", 0);
  const auto plus_zero = run(
      "S4_queue_aware_plus_uncovered_local_work_seconds_rule_only", 0);
  const auto old_two = run("S4_queue_aware_rule_only", 2);
  const auto plus_two = run(
      "S4_queue_aware_plus_uncovered_local_work_seconds_rule_only", 2);

  const auto old_zero_probe = probe(old_zero);
  const auto plus_zero_probe = probe(plus_zero);
  const auto old_two_probe = probe(old_two);
  const auto plus_two_probe = probe(plus_two);
  checks.require(
      old_zero_probe != old_zero.decisions.end() &&
          plus_zero_probe != plus_zero.decisions.end() &&
          old_two_probe != old_two.decisions.end() &&
          plus_two_probe != plus_two.decisions.end(),
      "V3R16 score fixture must expose every probe decision");
  if (old_zero_probe == old_zero.decisions.end() ||
      plus_zero_probe == plus_zero.decisions.end() ||
      old_two_probe == old_two.decisions.end() ||
      plus_two_probe == plus_two.decisions.end()) {
    return;
  }

  const auto old_zero_target = candidate(*old_zero_probe, 1);
  const auto plus_zero_target = candidate(*plus_zero_probe, 1);
  const auto old_two_target = candidate(*old_two_probe, 1);
  const auto plus_two_target = candidate(*plus_two_probe, 1);
  checks.require(
      old_zero_target != old_zero_probe->candidates.end() &&
          plus_zero_target != plus_zero_probe->candidates.end() &&
          old_two_target != old_two_probe->candidates.end() &&
          plus_two_target != plus_two_probe->candidates.end(),
      "V3R16 score fixture must retain the target candidate");
  if (old_zero_target == old_zero_probe->candidates.end() ||
      plus_zero_target == plus_zero_probe->candidates.end() ||
      old_two_target == old_two_probe->candidates.end() ||
      plus_two_target == plus_two_probe->candidates.end()) {
    return;
  }

  checks.require(
      plus_zero_target->scorer_raw_score ==
              old_zero_target->scorer_raw_score &&
          plus_zero_probe->selected_next == old_zero_probe->selected_next &&
          plus_zero_probe->scorer_raw_prediction ==
              old_zero_probe->scorer_raw_prediction,
      "V3R16 must be score-exact to historical S4 with no source work");
  const auto historical_s4_score = [](const auto& decision,
                                      const auto& row) {
    double score = row.travel_time + row.static_potential;
    score +=
        static_cast<double>(row.target_queue_length +
                            row.target_scheduled_incoming) +
        std::max(0.0,
                 row.corridor_next_available - decision.event_time) +
        std::max(0.0,
                 row.target_next_available -
                     (decision.event_time + row.travel_time));
    return score;
  };
  checks.require(
      plus_two_target->scorer_raw_score ==
              historical_s4_score(*plus_two_probe, *plus_two_target) +
                  czr005::ics::event_runtime_detail::
                      uncovered_local_work_seconds(2, 3.0, true),
      "V3R16 must add exactly one service quantum per ready source item");
  checks.require(
      old_two_probe->selected_next == 1 &&
          plus_two_probe->selected_next == 2,
      "V3R16 uncovered work must produce the registered ranking change");
  checks.require(
      plus_two.summary.scorer_id ==
              "S4_queue_aware_plus_uncovered_local_work_seconds_rule_only" &&
          plus_two_probe->scorer_id ==
              "S4_queue_aware_plus_uncovered_local_work_seconds_rule_only" &&
          plus_two.summary.completed_count == 4 &&
          plus_two.summary.failed_count == 0 &&
          plus_two.summary.reservation_conflicts == 0 &&
          plus_two.summary.runtime_full_astar_calls == 0 &&
          plus_two.summary.global_reservation_scan_count == 0 &&
          plus_two.summary.two_step_reservation_count == 0 &&
          plus_two.summary.max_edges_selected_per_arrive <= 1,
      "V3R16 must remain the safe one-hop S4 family");
}

Graph typed_static_dominance_graph(double type2_service,
                                   double type4_service) {
  Graph graph;
  graph.add_node(czr005::ics::Node{0, 7, 0.001, 0, 0, {}});
  graph.add_node(czr005::ics::Node{1, 2, type2_service, 1, 0, {}});
  graph.add_node(czr005::ics::Node{2, 4, type4_service, 0, 1, {}});
  graph.add_node(czr005::ics::Node{3, 3, 0.001, 1, 1, {}});
  for (const auto [start, end] :
       std::vector<std::pair<int, int>>{
           {0, 1}, {0, 2}, {1, 3}, {2, 3}}) {
    graph.add_edge(czr005::ics::Edge{start, end, 1.0, 1.0});
  }
  std::vector<std::vector<double>> heuristic(
      4, std::vector<double>(4, 0.0));
  heuristic[0][3] = 3.0;
  heuristic[1][3] = 1.0;
  heuristic[2][3] = 0.25;
  graph.set_heuristic(std::move(heuristic));
  return graph;
}

void test_v3r17_typed_service_dominance(Checks& checks) {
  const auto config_for = [](const std::string& scorer_mode) {
    auto config = v3r2_shadow_config();
    config.scorer_mode = scorer_mode;
    config.storage_source_nodes = {2};
    config.source_aware_destination_service_mode = "off";
    return config;
  };
  const std::vector<EventRuntimeBagRequest> requests = {
      {"v3r17-blocker", 32037001, 0.0, 1000.0, 2, 3,
       "synthetic"},
      {"v3r17-probe", 32037002, 0.1, 1000.0, 0, 3,
       "synthetic"},
  };
  const std::vector<EventRuntimeFaultWindow> faults{
      {2, 3, 0.0, 1.0, 0.0}};
  const auto probe = [](const auto& result) {
    return std::find_if(
        result.decisions.begin(), result.decisions.end(), [](const auto& row) {
          return row.segment_id == "v3r17-probe" && row.current_node == 0;
        });
  };
  const auto candidate = [](const auto& decision, int next_node) {
    return std::find_if(
        decision.candidates.begin(), decision.candidates.end(),
        [next_node](const auto& row) { return row.next_node == next_node; });
  };

  const auto graph = typed_static_dominance_graph(3.0, 0.01);
  EventDrivenJunctionRuntime old_runtime(
      graph, config_for("S4_queue_aware_rule_only"));
  const auto old_result = old_runtime.run(requests, faults);
  EventDrivenJunctionRuntime dominance_runtime(
      graph, config_for("S4_typed_service_dominance_rule_only"));
  const auto dominance_result = dominance_runtime.run(requests, faults);
  const auto old_probe = probe(old_result);
  const auto dominance_probe = probe(dominance_result);
  checks.require(
      old_probe != old_result.decisions.end() &&
          dominance_probe != dominance_result.decisions.end(),
      "V3R17 typed motif must expose both probe decisions");
  if (old_probe == old_result.decisions.end() ||
      dominance_probe == dominance_result.decisions.end()) {
    return;
  }
  const auto old_type2 = candidate(*old_probe, 1);
  const auto old_type4 = candidate(*old_probe, 2);
  const auto dominance_type2 = candidate(*dominance_probe, 1);
  const auto dominance_type4 = candidate(*dominance_probe, 2);
  checks.require(
      old_type2 != old_probe->candidates.end() &&
          old_type4 != old_probe->candidates.end() &&
          dominance_type2 != dominance_probe->candidates.end() &&
          dominance_type4 != dominance_probe->candidates.end(),
      "V3R17 typed motif must retain both materialized neighbours");
  if (old_type2 == old_probe->candidates.end() ||
      old_type4 == old_probe->candidates.end() ||
      dominance_type2 == dominance_probe->candidates.end() ||
      dominance_type4 == dominance_probe->candidates.end()) {
    return;
  }
  checks.require(
      old_probe->model_prediction == 1 && old_probe->selected_next == 1 &&
          dominance_probe->scorer_raw_prediction == 1 &&
          dominance_probe->model_prediction == 2 &&
          dominance_probe->selected_next == 2 &&
          dominance_type2->shield_allowed &&
          dominance_type4->shield_allowed &&
          !dominance_type2->advertised_fault &&
          !dominance_type4->advertised_fault &&
          dominance_type4->travel_time + dominance_type4->static_potential <
              dominance_type2->travel_time +
                  dominance_type2->static_potential &&
          graph.service_time(2) < graph.service_time(1),
      "V3R17 must move the strictly base-and-service-dominating type-4 neighbour to the front");
  checks.require(
      old_type2->scorer_raw_score == dominance_type2->scorer_raw_score &&
          old_type4->scorer_raw_score == dominance_type4->scorer_raw_score &&
          dominance_result.summary.scorer_id ==
              "S4_typed_service_dominance_rule_only" &&
          dominance_probe->scorer_id ==
              "S4_typed_service_dominance_rule_only" &&
          dominance_result.summary.runtime_full_astar_calls == 0 &&
          dominance_result.summary.global_reservation_scan_count == 0 &&
          dominance_result.summary.scorer_future_route_input_count == 0 &&
          dominance_result.summary.scorer_future_schedule_input_count == 0 &&
          dominance_result.summary.max_edges_selected_per_arrive <= 1,
      "V3R17 must preserve historical S4 scores and the bounded one-hop authority");
}

void test_v3r20_service_aware_static_dominance(Checks& checks) {
  const auto config_for = [](const std::string& scorer_mode) {
    auto config = v3r2_shadow_config();
    config.scorer_mode = scorer_mode;
    config.storage_source_nodes = {2};
    config.source_aware_destination_service_mode = "off";
    return config;
  };
  const std::vector<EventRuntimeBagRequest> requests = {
      {"v3r20-blocker", 32040001, 0.0, 1000.0, 2, 3, "synthetic"},
      {"v3r20-probe", 32040002, 3.1, 1000.0, 0, 3, "synthetic"},
  };
  const std::vector<EventRuntimeFaultWindow> faults{
      {2, 3, 0.0, 4.0, 0.0}};
  const auto probe = [](const auto& result) {
    return std::find_if(
        result.decisions.begin(), result.decisions.end(), [](const auto& row) {
          return row.segment_id == "v3r20-probe" && row.current_node == 0;
        });
  };
  const auto candidate = [](const auto& decision, int next_node) {
    return std::find_if(
        decision.candidates.begin(), decision.candidates.end(),
        [next_node](const auto& row) { return row.next_node == next_node; });
  };

  const auto graph = typed_static_dominance_graph(0.01, 3.0);
  EventDrivenJunctionRuntime old_runtime(
      graph, config_for("S4_queue_aware_rule_only"));
  const auto old_result = old_runtime.run(requests, faults);
  EventDrivenJunctionRuntime dominance_runtime(
      graph, config_for("S4_service_aware_static_dominance_rule_only"));
  const auto dominance_result = dominance_runtime.run(requests, faults);
  const auto old_probe = probe(old_result);
  const auto dominance_probe = probe(dominance_result);
  checks.require(
      old_probe != old_result.decisions.end() &&
          dominance_probe != dominance_result.decisions.end(),
      "V3R20 motif must expose both probe decisions");
  if (old_probe == old_result.decisions.end() ||
      dominance_probe == dominance_result.decisions.end()) {
    return;
  }
  const auto old_type2 = candidate(*old_probe, 1);
  const auto old_type4 = candidate(*old_probe, 2);
  const auto dominance_type2 = candidate(*dominance_probe, 1);
  const auto dominance_type4 = candidate(*dominance_probe, 2);
  checks.require(
      old_type2 != old_probe->candidates.end() &&
          old_type4 != old_probe->candidates.end() &&
          dominance_type2 != dominance_probe->candidates.end() &&
          dominance_type4 != dominance_probe->candidates.end(),
      "V3R20 motif must retain both materialized neighbours");
  if (old_type2 == old_probe->candidates.end() ||
      old_type4 == old_probe->candidates.end() ||
      dominance_type2 == dominance_probe->candidates.end() ||
      dominance_type4 == dominance_probe->candidates.end()) {
    return;
  }
  checks.require(
      old_probe->model_prediction == 1 && old_probe->selected_next == 1 &&
          dominance_probe->scorer_raw_prediction == 1 &&
          dominance_probe->model_prediction == 2 &&
          dominance_probe->selected_next == 2 &&
          dominance_type2->shield_allowed &&
          dominance_type4->shield_allowed &&
          !dominance_type2->advertised_fault &&
          !dominance_type4->advertised_fault &&
          !dominance_type2->first_edge_credit_valid &&
          !dominance_type4->first_edge_credit_valid &&
          dominance_type4->travel_time + dominance_type4->static_potential <
              dominance_type2->travel_time +
                  dominance_type2->static_potential &&
          graph.service_time(2) > graph.service_time(1),
      "V3R20 must prefer the lower canonical static completion cost despite longer immediate service");
  checks.require(
      old_type2->scorer_raw_score == dominance_type2->scorer_raw_score &&
          old_type4->scorer_raw_score == dominance_type4->scorer_raw_score &&
          dominance_result.summary.scorer_id ==
              "S4_service_aware_static_dominance_rule_only" &&
          dominance_probe->scorer_id ==
              "S4_service_aware_static_dominance_rule_only" &&
          dominance_result.summary.runtime_full_astar_calls == 0 &&
          dominance_result.summary.global_reservation_scan_count == 0 &&
          dominance_result.summary.scorer_future_route_input_count == 0 &&
          dominance_result.summary.scorer_future_schedule_input_count == 0 &&
          dominance_result.summary.max_edges_selected_per_arrive <= 1,
      "V3R20 must preserve raw S4 scores and bounded one-hop authority");
}

Graph v3r18_source_release_tie_graph() {
  Graph graph;
  for (int node = 0; node < 9; ++node) {
    const double service = node == 0 || node == 6 ? 1.0 : 0.001;
    graph.add_node(czr005::ics::Node{node, 7, service, 0, 0, {}});
  }
  for (const auto [start, end] :
       std::vector<std::pair<int, int>>{
           {0, 1}, {0, 2}, {0, 3}, {4, 6}, {5, 6}, {6, 7}, {6, 8}}) {
    graph.add_edge(czr005::ics::Edge{start, end, 1.0, 1.0});
  }
  std::vector<std::vector<double>> heuristic(
      9, std::vector<double>(9, 0.0));
  heuristic[0][1] = 1.0;
  heuristic[0][2] = 10.0;
  heuristic[0][3] = 1.0;
  heuristic[2][1] = 100.0;
  heuristic[3][1] = 100.0;
  heuristic[1][2] = 100.0;
  heuristic[3][2] = 100.0;
  heuristic[1][3] = 100.0;
  heuristic[2][3] = 100.0;
  heuristic[4][7] = 2.0;
  heuristic[5][8] = 11.0;
  heuristic[6][7] = 1.0;
  heuristic[6][8] = 10.0;
  heuristic[8][7] = 100.0;
  heuristic[7][8] = 100.0;
  graph.set_heuristic(std::move(heuristic));
  return graph;
}

void test_v3r18_source_release_tie(Checks& checks) {
  const auto graph = v3r18_source_release_tie_graph();
  const auto run = [&](const std::string& discipline,
                       const std::vector<EventRuntimeBagRequest>& requests) {
    auto config = v3r2_shadow_config();
    config.queue_discipline = discipline;
    config.event_semantics =
        "E3_batch_source_and_junction_same_timestamp";
    config.merge_grant_rule = "M1";
    config.merge_grant_timing_mode = "eager";
    config.source_aware_destination_service_mode = "off";
    config.storage_source_nodes = {0, 4, 5};
    config.max_events = 100000;
    config.max_simulation_time = 100.0;
    EventDrivenJunctionRuntime runtime(graph, config);
    return runtime.run(requests);
  };
  const auto bag = [](const auto& result, const std::string& segment) {
    return std::find_if(
        result.bags.begin(), result.bags.end(), [&](const auto& row) {
          return row.segment_id == segment;
        });
  };

  const std::vector<EventRuntimeBagRequest> same_time = {
      {"v3r18-blocker", 32038001, 0.0, 1000.0, 0, 3, "synthetic"},
      {"v3r18-short", 32038002, 0.1, 1000.0, 0, 1, "synthetic"},
      {"v3r18-long", 32038003, 0.1, 1000.0, 0, 2, "synthetic"},
  };
  const auto fifo = run("fifo", same_time);
  const auto active =
      run("fifo_source_longest_static_tie", same_time);
  const auto fifo_short = bag(fifo, "v3r18-short");
  const auto fifo_long = bag(fifo, "v3r18-long");
  const auto active_short = bag(active, "v3r18-short");
  const auto active_long = bag(active, "v3r18-long");
  checks.require(
      fifo_short != fifo.bags.end() && fifo_long != fifo.bags.end() &&
          active_short != active.bags.end() &&
          active_long != active.bags.end() &&
          fifo_short->admitted_time < fifo_long->admitted_time &&
          active_long->admitted_time < active_short->admitted_time,
      "V3R18 must change only the same-time source FIFO ID tie to longest-static first");

  auto different_time = same_time;
  different_time[2].release_time = 0.2;
  const auto older =
      run("fifo_source_longest_static_tie", different_time);
  const auto older_short = bag(older, "v3r18-short");
  const auto later_long = bag(older, "v3r18-long");
  checks.require(
      older_short != older.bags.end() && later_long != older.bags.end() &&
          older_short->admitted_time < later_long->admitted_time,
      "V3R18 must retain FIFO across different source enqueue times");

  const std::vector<EventRuntimeBagRequest> junction_pair = {
      {"v3r18-junction-short", 32038004, 0.0, 1000.0, 4, 7,
       "synthetic"},
      {"v3r18-junction-long", 32038005, 0.0, 1000.0, 5, 8,
       "synthetic"},
  };
  const auto junction_fifo = run("fifo", junction_pair);
  const auto junction_active =
      run("fifo_source_longest_static_tie", junction_pair);
  bool junction_exact =
      junction_fifo.decisions.size() == junction_active.decisions.size();
  for (std::size_t index = 0;
       junction_exact && index < junction_fifo.decisions.size(); ++index) {
    const auto& before = junction_fifo.decisions[index];
    const auto& after = junction_active.decisions[index];
    junction_exact = before.segment_id == after.segment_id &&
                     before.event_time == after.event_time &&
                     before.current_node == after.current_node &&
                     before.selected_next == after.selected_next;
  }
  checks.require(junction_exact,
                 "V3R18 source-only spelling must leave junction FIFO exact");
  checks.require(
      active.summary.completed_count == 3 && active.summary.failed_count == 0 &&
          active.summary.runtime_full_astar_calls == 0 &&
          active.summary.global_reservation_scan_count == 0 &&
          active.summary.scorer_future_route_input_count == 0 &&
          active.summary.max_edges_selected_per_arrive <= 1,
      "V3R18 must remain a bounded one-hop source ordering rule");
}

Graph v3r22_pending_request_hol_graph() {
  Graph graph;
  for (int node = 0; node < 5; ++node) {
    const double service = node == 1 ? 10.0 : 0.001;
    graph.add_node(czr005::ics::Node{
        node, node == 1 ? 1 : 7, service, node, 0, {}});
  }
  for (const auto [start, end] :
       std::vector<std::pair<int, int>>{
           {4, 0}, {0, 1}, {3, 1}, {1, 2}}) {
    graph.add_edge(czr005::ics::Edge{start, end, 0.05, 1.0});
  }
  std::vector<std::vector<double>> heuristic(
      5, std::vector<double>(5, 1000.0));
  for (int node = 0; node < 5; ++node) {
    heuristic[node][node] = 0.0;
  }
  heuristic[4][2] = 0.15;
  heuristic[0][2] = 0.10;
  heuristic[1][2] = 0.05;
  heuristic[3][2] = 0.10;
  graph.set_heuristic(std::move(heuristic));
  return graph;
}

void test_v3r22_pending_request_hol_bypass(Checks& checks) {
  constexpr int kA = 1;
  constexpr int kB = 2;
  const auto graph = v3r22_pending_request_hol_graph();
  const std::vector<EventRuntimeBagRequest> requests = {
      {"v3r22-calendar-owner", 32042001, 0.0, 100.0, 1, 2,
       "synthetic"},
      {"v3r22-fifo-a", 32042002, 0.0, 100.0, 4, 2,
       "synthetic"},
      {"v3r22-fifo-b", 32042003, 0.0, 100.0, 4, 2,
       "synthetic"},
  };
  const auto config_for = [](const std::string& discipline) {
    auto config = v3r2_shadow_config();
    config.queue_discipline = discipline;
    config.source_aware_destination_service_mode = "off";
    config.storage_source_nodes = {1, 4};
    config.g4irsf20_event_hotpath_policy = "E0";
    config.max_simulation_time = 100.0;
    return config;
  };
  const auto junction_dispatches_at_zero = [](const auto& result) {
    std::vector<const czr005::ics::EventRuntimeTraceRow*> rows;
    for (const auto& row : result.events) {
      if (row.event == "JUNCTION_ARBITRATION" && row.node == 0) {
        rows.push_back(&row);
      }
    }
    return rows;
  };
  const auto advance_until = [](EventDrivenJunctionRuntime& runtime,
                                const auto& predicate) {
    for (int step = 0; step < 10000; ++step) {
      if (predicate()) {
        return true;
      }
      if (!runtime.process_one_event()) {
        return predicate();
      }
    }
    return false;
  };

  EventDrivenJunctionRuntime fifo_runtime(graph, config_for("fifo"));
  fifo_runtime.initialize(requests);
  const bool fifo_first_request = advance_until(fifo_runtime, [&] {
    return fifo_runtime
               .g4irsf15_local_action_snapshot(kA)
               .pending_merge_request_id != 0;
  });
  const auto fifo_a_before =
      fifo_runtime.g4irsf15_local_action_snapshot(kA);
  const auto fifo_b_before =
      fifo_runtime.g4irsf15_local_action_snapshot(kB);
  const bool fifo_duplicate_dispatch = advance_until(fifo_runtime, [&] {
    return junction_dispatches_at_zero(
               fifo_runtime.current_result()).size() >= 2U;
  });
  const auto fifo_a_after =
      fifo_runtime.g4irsf15_local_action_snapshot(kA);
  const auto fifo_b_after =
      fifo_runtime.g4irsf15_local_action_snapshot(kB);
  const auto fifo_dispatches =
      junction_dispatches_at_zero(fifo_runtime.current_result());

  EventDrivenJunctionRuntime active_runtime(
      graph,
      config_for("fifo_junction_skip_pending_merge_owner"));
  active_runtime.initialize(requests);
  const bool active_first_request = advance_until(active_runtime, [&] {
    return active_runtime
               .g4irsf15_local_action_snapshot(kA)
               .pending_merge_request_id != 0;
  });
  const auto active_a_before =
      active_runtime.g4irsf15_local_action_snapshot(kA);
  const auto active_b_before =
      active_runtime.g4irsf15_local_action_snapshot(kB);
  const auto calendar_before =
      active_runtime.g4irsf22_local_guidance_snapshot(1);
  const auto calendar_generation_before =
      active_runtime.test_service_calendar_generation(1);
  const bool active_second_request = advance_until(active_runtime, [&] {
    return active_runtime
               .g4irsf15_local_action_snapshot(kB)
               .pending_merge_request_id != 0;
  });
  const auto active_a_after =
      active_runtime.g4irsf15_local_action_snapshot(kA);
  const auto active_b_after =
      active_runtime.g4irsf15_local_action_snapshot(kB);
  const auto calendar_after =
      active_runtime.g4irsf22_local_guidance_snapshot(1);
  const auto calendar_generation_after =
      active_runtime.test_service_calendar_generation(1);
  const auto active_dispatches =
      junction_dispatches_at_zero(active_runtime.current_result());
  const auto active_boundary = active_runtime.peek_safe_boundary();
  const bool b_entered_merge_edge = std::any_of(
      active_runtime.current_result().events.begin(),
      active_runtime.current_result().events.end(),
      [=](const auto& row) {
        return row.runtime_bag_id == kB && row.event == "EDGE_ENTER" &&
               row.from_node == 0 && row.to_node == 1;
      });

  checks.require(
      fifo_first_request && fifo_duplicate_dispatch &&
          fifo_dispatches.size() >= 2U &&
          fifo_dispatches[0]->runtime_bag_id == kA &&
          fifo_dispatches[1]->runtime_bag_id == kA &&
          fifo_dispatches[1]->selected_edge_count == 0 &&
          fifo_a_before.pending_merge_request_id != 0 &&
          fifo_a_after.pending_merge_request_id ==
              fifo_a_before.pending_merge_request_id &&
          fifo_a_after.pending_merge_lineage ==
              fifo_a_before.pending_merge_lineage &&
          fifo_b_before.pending_merge_request_id == 0 &&
          fifo_b_after.pending_merge_request_id == 0,
      "V3R22 historical FIFO must reselect the represented owner and publish no second request");
  checks.require(
      active_first_request && active_second_request &&
          active_dispatches.size() >= 2U &&
          active_dispatches[0]->runtime_bag_id == kA &&
          active_dispatches[1]->runtime_bag_id == kB &&
          active_dispatches[1]->selected_edge_count == 0 &&
          active_a_before.pending_merge_request_id != 0 &&
          active_a_after.pending_merge_request_id ==
              active_a_before.pending_merge_request_id &&
          active_a_after.pending_merge_lineage ==
              active_a_before.pending_merge_lineage &&
          active_b_before.pending_merge_request_id == 0 &&
          active_b_after.pending_merge_request_id != 0 &&
          active_a_after.status == "JUNCTION_QUEUE" &&
          active_b_after.status == "JUNCTION_QUEUE" &&
          !b_entered_merge_edge,
      "V3R22 must publish B's request without cancelling A or bypassing M3 into an edge commit");
  checks.require(
      calendar_before.service_reservation_count ==
              calendar_after.service_reservation_count &&
          calendar_before.service_next_available ==
              calendar_after.service_next_available &&
          calendar_generation_before == calendar_generation_after &&
          active_boundary.has_value() &&
          active_boundary->pending_merge_request_count == 2 &&
          active_boundary->active_merge_capability_count == 0 &&
          !active_a_after.junction_wakeup_pending &&
          !active_b_after.junction_wakeup_pending &&
          active_runtime.test_choose_junction_bag_at_node(0) == kA,
      "V3R22 all-pending fallback must retain FIFO with the calendar, generation, and JIT authority unchanged");
  const auto fifo_a_outcome = fifo_runtime.g4irsf15_causal_bag_outcome(kA);
  const auto fifo_b_outcome = fifo_runtime.g4irsf15_causal_bag_outcome(kB);
  const auto active_a_outcome = active_runtime.g4irsf15_causal_bag_outcome(kA);
  const auto active_b_outcome = active_runtime.g4irsf15_causal_bag_outcome(kB);
  checks.require(
      fifo_a_outcome.admitted_time == active_a_outcome.admitted_time &&
          fifo_b_outcome.admitted_time == active_b_outcome.admitted_time &&
          active_a_outcome.admitted_time < active_b_outcome.admitted_time,
      "V3R22 junction-only spelling must leave source FIFO admission exact");

  fifo_runtime.drain();
  active_runtime.drain();
  const auto fifo_result = fifo_runtime.finalize();
  const auto active_result = active_runtime.finalize();
  checks.require(
      fifo_result.summary.completed_count == 3 &&
          active_result.summary.completed_count == 3 &&
          fifo_result.summary.failed_count == 0 &&
          active_result.summary.failed_count == 0 &&
          active_result.summary.merge_grant_conservation_holds &&
          active_result.summary.merge_grant_active_bijection_holds &&
          active_result.summary.runtime_full_astar_calls == 0 &&
          active_result.summary.global_reservation_scan_count == 0 &&
          active_result.summary.scorer_future_route_input_count == 0 &&
          active_result.summary.scorer_future_schedule_input_count == 0 &&
          active_result.summary.max_edges_selected_per_arrive <= 1 &&
          active_result.summary.max_edges_selected_per_bag_per_decision <= 1,
      "V3R22 motif must drain through unchanged M3 while retaining the bounded one-hop boundary");
}

void test_v3r2_j2_unique_and_rollbacks(Checks& checks) {
  const auto graph = v3r2_slot_pair_graph(true);
  auto config = v3r2_shadow_config();
  config.storage_source_nodes = {0, 4};
  EventDrivenJunctionRuntime runtime(graph, config);
  const auto result = runtime.run(v3r2_slot_pair_requests());
  const auto j2 = std::find_if(
      result.source_aware_destination_service_shadow.begin(),
      result.source_aware_destination_service_shadow.end(),
      [](const auto& row) { return row.seam_kind_code == 2U; });
  const bool j2_valid =
      j2 != result.source_aware_destination_service_shadow.end() &&
      j2->external_path_code == 2U && j2->has_j2_identity &&
      !j2->has_direct_episode_identity &&
      j2->external_direct_episode_event_seq == 0 &&
      j2->external_request_id != 0 && j2->external_request_lineage != 0 &&
      j2->local_guards_passed && j2->local_task_id == 32032002 &&
      j2->local_runtime_bag_id == 1 && j2->local_choose_bag_index == 0 &&
      j2->local_escape_token_runtime_bag_id == -1 &&
      v3r4_local_telemetry_is_exact(*j2) &&
      j2->local_source_ready_count == 1 &&
      j2->destination_pending_count >= 1 &&
      std::abs(j2->oldest_local_wait_age_seconds -
               (j2->event_time - j2->local_source_enqueued_at)) <
          1.0e-12 &&
      std::abs(j2->local_release) < 1.0e-12 &&
      std::abs(j2->local_deadline - 100.0) < 1.0e-12 &&
      std::abs(j2->local_source_enqueued_at) < 1.0e-12 &&
      std::abs(j2->L0 - 1.0) < 1.0e-12 &&
      std::abs(j2->L1 - 2.0) < 1.0e-12 && j2->X_insert > 0.0;
  checks.require(j2_valid, "V3R2 J2 must publish a real exact-request row");
  v3r2_proof.j2_unique_publish = j2_valid;
  int duplicates = 0;
  if (j2 != result.source_aware_destination_service_shadow.end()) {
    duplicates = static_cast<int>(std::count_if(
        result.source_aware_destination_service_shadow.begin(),
        result.source_aware_destination_service_shadow.end(),
        [&](const auto& row) {
          return row.external_runtime_bag_id == j2->external_runtime_bag_id &&
                 row.node == j2->node &&
                 std::abs(row.external_slot_start_seconds -
                          j2->external_slot_start_seconds) < 1.0e-12 &&
                 std::abs(row.external_slot_end_seconds -
                          j2->external_slot_end_seconds) < 1.0e-12;
        }));
  }
  const bool no_duplicate = duplicates == 1;
  checks.require(no_duplicate, "V3R2 J2 authority must suppress DIRECT duplicate");
  v3r2_proof.j2_direct_duplicate_suppressed = no_duplicate;

  auto j2_failure = config;
  j2_failure.test_merge_grant_fail_after_calendar_prepare = true;
  EventDrivenJunctionRuntime failed_j2_runtime(graph, j2_failure);
  failed_j2_runtime.initialize(v3r2_slot_pair_requests());
  bool j2_injected = false;
  try {
    while (failed_j2_runtime.process_one_event()) {
    }
  } catch (const std::logic_error& error) {
    j2_injected = std::string(error.what()) ==
                  "G4IRSF32 V3R2 injected J2 failure after staging";
  }
  const auto& failed_j2 = failed_j2_runtime.current_result();
  const bool j2_commit_published = std::any_of(
      failed_j2.events.begin(), failed_j2.events.end(), [](const auto& row) {
        return row.runtime_bag_id == 2 && row.event == "EDGE_ENTER" &&
               row.from_node == 0 && row.to_node == 1;
      });
  const bool j2_exact =
      j2_injected && !j2_commit_published &&
      failed_j2.source_aware_destination_service_shadow.empty() &&
      failed_j2.source_aware_destination_service_shadow.capacity() == 0 &&
      v3r2_census_is_zero(failed_j2.summary) &&
      v3r2_resource_fields_are_zero(failed_j2.summary);
  checks.require(
      j2_exact,
      "V3R2 J2 staged failure must restore row, capacity, resources, census, and commit");

  auto j2_rejection = config;
  j2_rejection.test_merge_grant_flip_advertised_generation_before_commit =
      true;
  EventDrivenJunctionRuntime rejected_j2_runtime(graph, j2_rejection);
  rejected_j2_runtime.initialize(v3r2_slot_pair_requests());
  bool saw_post_stage_rejection = false;
  for (int step = 0;
       step < 10000 && !saw_post_stage_rejection &&
       rejected_j2_runtime.process_one_event();
       ++step) {
    const auto& decisions =
        rejected_j2_runtime.current_result().hold_attempts;
    saw_post_stage_rejection = std::any_of(
        decisions.begin(), decisions.end(), [](const auto& row) {
          return row.runtime_bag_id == 2 &&
                 row.rule_reason == "fault_generation_changed";
        });
  }
  const auto& rejected_j2 = rejected_j2_runtime.current_result();
  const bool j2_rejection_exact =
      saw_post_stage_rejection &&
      rejected_j2.source_aware_destination_service_shadow.empty() &&
      rejected_j2.source_aware_destination_service_shadow.capacity() == 0 &&
      v3r2_census_is_zero(rejected_j2.summary) &&
      v3r2_resource_fields_are_zero(rejected_j2.summary);
  checks.require(
      j2_rejection_exact,
      "V3R2 J2 post-stage recheck rejection must restore sidecar and census "
      "saw=" + std::to_string(saw_post_stage_rejection) +
          " size=" + std::to_string(
              rejected_j2.source_aware_destination_service_shadow.size()) +
          " capacity=" + std::to_string(
              rejected_j2.source_aware_destination_service_shadow.capacity()) +
          " considered=" + std::to_string(
              rejected_j2.summary
                  .source_aware_destination_service_external_commit_considered_count));
  v3r2_proof.j2_after_stage_rollback_exact =
      j2_exact && j2_rejection_exact;
}

void test_v3r2_direct_rollback_and_trace_limit(Checks& checks) {
  const auto graph = v3r2_slot_pair_graph(false);
  auto fail_config = v3r2_shadow_config();
  fail_config.test_source_aware_destination_service_fail_direct_after_stage =
      true;
  fail_config.test_verify_pibt_rollback_logical_state = true;
  EventDrivenJunctionRuntime failed_runtime(graph, fail_config);
  failed_runtime.initialize(v3r2_slot_pair_requests());
  bool injected = false;
  try {
    while (failed_runtime.process_one_event()) {
    }
  } catch (const std::logic_error& error) {
    injected = std::string(error.what()) ==
               "G4IRSF32 V3R2 injected DIRECT failure after staging";
  }
  const auto& failed = failed_runtime.current_result();
  const bool external_enter_published = std::any_of(
      failed.events.begin(), failed.events.end(), [](const auto& row) {
        return row.runtime_bag_id == 2 && row.event == "EDGE_ENTER" &&
               row.from_node == 0 && row.to_node == 1;
      });
  const bool direct_exact =
      injected && !external_enter_published &&
      failed.source_aware_destination_service_shadow.empty() &&
      failed.source_aware_destination_service_shadow.capacity() == 0 &&
      v3r2_census_is_zero(failed.summary) &&
      v3r2_resource_fields_are_zero(failed.summary);
  checks.require(
      direct_exact,
      "V3R2 DIRECT staged exception must restore row, capacity, resources, census, and publication");

  auto pibt_failure = v3r2_shadow_config();
  pibt_failure.local_queue_capacity = 1;
  pibt_failure.event_semantics =
      "E3_batch_source_and_junction_same_timestamp";
  pibt_failure.merge_grant_rule = "M1";
  pibt_failure.merge_grant_timing_mode = "eager";
  pibt_failure.merge_grant_max_pending_requests = 64;
  pibt_failure.merge_grant_lifecycle_limit = 1024;
  pibt_failure.test_pibt_fail_after_commit_before_publication = true;
  pibt_failure.test_verify_pibt_rollback_logical_state = true;
  EventDrivenJunctionRuntime failed_pibt_runtime(graph, pibt_failure);
  auto pibt_requests = v3r2_slot_pair_requests();
  pibt_requests[2].release_time = 0.749;
  failed_pibt_runtime.initialize(pibt_requests);
  for (int step = 0;
       step < 10000 &&
       failed_pibt_runtime.current_result().summary
               .bounded_local_pibt_post_commit_failure_injection_count == 0 &&
       failed_pibt_runtime.process_one_event();
       ++step) {
  }
  const auto& failed_pibt = failed_pibt_runtime.current_result();
  const bool pibt_publish_rollback_exact =
      failed_pibt.summary
              .bounded_local_pibt_post_commit_failure_injection_count == 1 &&
      failed_pibt.summary
              .bounded_local_pibt_rollback_fingerprint_match_count == 1 &&
      failed_pibt.source_aware_destination_service_shadow.empty() &&
      failed_pibt.source_aware_destination_service_shadow.capacity() > 0 &&
      failed_pibt.source_aware_destination_service_shadow.capacity() <=
          static_cast<std::size_t>(
              pibt_failure.source_aware_destination_service_trace_limit) &&
      v3r2_census_is_zero(failed_pibt.summary) &&
      v3r2_resource_fields_are_zero(failed_pibt.summary);
  checks.require(
      pibt_publish_rollback_exact,
      "V3R2 PIBT post-commit injection must retain only bounded preflight "
      "capacity and precede DIRECT sidecar publication "
      "injected=" + std::to_string(
          failed_pibt.summary
              .bounded_local_pibt_post_commit_failure_injection_count) +
          " rollback=" + std::to_string(
              failed_pibt.summary
                  .bounded_local_pibt_rollback_fingerprint_match_count) +
          " rows=" + std::to_string(
              failed_pibt.source_aware_destination_service_shadow.size()) +
          " capacity=" + std::to_string(
              failed_pibt.source_aware_destination_service_shadow.capacity()) +
          " considered=" + std::to_string(
              failed_pibt.summary
                  .source_aware_destination_service_external_commit_considered_count));
  v3r2_proof.direct_after_stage_rollback_exact =
      direct_exact && pibt_publish_rollback_exact;

  auto bounded = v3r2_shadow_config();
  bounded.source_aware_destination_service_trace_limit = 1;
  std::vector<EventRuntimeBagRequest> requests = {
      {"v3r2-local-a", 32032101, 0.0, 100.0, 1, 3, "local"},
      {"v3r2-local-b", 32032102, 0.0, 100.0, 1, 3, "local"},
      {"v3r2-local-c", 32032103, 0.0, 100.0, 1, 3, "local"},
      {"v3r2-external-a", 32032104, 0.699, 100.0, 0, 3, "external"},
      {"v3r2-external-b", 32032105, 0.700, 100.0, 0, 3, "external"},
  };
  EventDrivenJunctionRuntime bounded_runtime(graph, bounded);
  bounded_runtime.initialize(requests);
  bool exhausted = false;
  try {
    while (bounded_runtime.process_one_event()) {
    }
  } catch (const std::runtime_error& error) {
    exhausted = std::string(error.what()) ==
                "G4IRSF32 V3R2 shadow trace limit exhausted before commit";
  }
  const auto& bounded_result = bounded_runtime.current_result();
  const std::uint64_t partition_total =
      bounded_result.summary.source_aware_destination_service_no_local_count +
      bounded_result.summary
          .source_aware_destination_service_local_guard_fail_count +
      bounded_result.summary.source_aware_destination_service_non_overlap_count +
      bounded_result.summary
          .source_aware_destination_service_observation_stored_count;
  const bool second_external_commit_published = std::any_of(
      bounded_result.events.begin(),
      bounded_result.events.end(),
      [](const auto& row) {
        return row.runtime_bag_id == 4 && row.event == "EDGE_ENTER" &&
               row.from_node == 0 && row.to_node == 1;
      });
  const bool trace_exact =
      exhausted &&
      bounded_result.source_aware_destination_service_shadow.size() == 1 &&
      bounded_result.source_aware_destination_service_shadow.capacity() == 1 &&
      bounded_result.summary
              .source_aware_destination_service_external_commit_considered_count ==
          partition_total &&
      bounded_result.summary
              .source_aware_destination_service_observation_stored_count == 1 &&
      bounded_result.summary
              .source_aware_destination_service_observation_dropped_count == 0 &&
      bounded_result.summary
              .source_aware_destination_service_staged_rollback_count == 0 &&
      !second_external_commit_published;
  checks.require(trace_exact, "V3R2 trace exhaustion must fail before commit");
  v3r2_proof.trace_limit_fail_before_commit = trace_exact;
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
    test_s4_direct_neighbor_merge_calendar_visibility_is_exact_off_and_local(
        checks);
    test_s4_local_descent_guard_is_exact_off_and_blocks_cycle(checks);
    test_s4_local_descent_guard_uses_surviving_fault_potential(checks);
    test_goal_arrival_completion_is_exact_off_and_skips_busy_goal_service(
        checks);
    test_v3r2_pure_helper_and_storage_roles(checks);
    test_v3r2_direct_and_action_inert(checks);
    test_v3r13_candidate_a_closed_loop(checks);
    test_v3r15_candidate_a_commit_recheck(checks);
    test_v3r14_uncovered_local_work_helper(checks);
    test_v3r14_candidate_b_score_and_ranking(checks);
    test_v3r16_s4_plus_uncovered_local_work(checks);
    test_v3r17_typed_service_dominance(checks);
    test_v3r20_service_aware_static_dominance(checks);
    test_v3r18_source_release_tie(checks);
    test_v3r22_pending_request_hol_bypass(checks);
    test_v3r2_j2_unique_and_rollbacks(checks);
    test_v3r2_direct_rollback_and_trace_limit(checks);
  } catch (const std::exception& error) {
    ++checks.failures;
    std::cerr << "FAIL: canonical map2 test setup/runtime exception: " << error.what() << '\n';
  }
  const bool proof_complete =
      v3r2_proof.pure_calendar_helper &&
      v3r2_proof.generic_storage_role_validation &&
      v3r2_proof.direct_unique_publish &&
      v3r2_proof.j2_unique_publish &&
      v3r2_proof.j2_direct_duplicate_suppressed &&
      v3r2_proof.direct_after_stage_rollback_exact &&
      v3r2_proof.j2_after_stage_rollback_exact &&
      v3r2_proof.trace_limit_fail_before_commit &&
      v3r2_proof.action_inert_invariants;
  if (checks.failures == 0 && !proof_complete) {
    ++checks.failures;
    std::cerr << "FAIL: V3R2 native proof is incomplete\n";
  }
  if (checks.failures == 0) {
    std::cout
        << "G4IRSF32_V3R2_NATIVE_PROOF_JSON="
           "{\"action_inert_invariants\":true,"
           "\"build_head\":\"" CZR005_G4IRSF32_BUILD_HEAD "\","
           "\"direct_after_stage_rollback_exact\":true,"
           "\"direct_unique_publish\":true,"
           "\"generic_storage_role_validation\":true,"
           "\"j2_after_stage_rollback_exact\":true,"
           "\"j2_direct_duplicate_suppressed\":true,"
           "\"j2_unique_publish\":true,"
           "\"pure_calendar_helper\":true,"
           "\"schema_id\":\"czr005.g4irsf32.native_proof.v3r2\","
           "\"test_id\":\"g4irsf32_v3r2_focused_native\","
           "\"trace_limit_fail_before_commit\":true}\n";
  }
  return checks.failures == 0 ? 0 : 1;
}
