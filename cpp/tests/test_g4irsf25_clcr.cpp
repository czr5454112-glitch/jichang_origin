#include <algorithm>
#include <cmath>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"

namespace {

using czr005::ics::Edge;
using czr005::ics::EventDecisionTraceRow;
using czr005::ics::EventDrivenJunctionConfig;
using czr005::ics::EventDrivenJunctionResult;
using czr005::ics::EventDrivenJunctionRuntime;
using czr005::ics::EventRuntimeBagRequest;
using czr005::ics::EventRuntimeFaultWindow;
using czr005::ics::G4IRSF25CLCRArm;
using czr005::ics::G4IRSF25CLCRConfig;
using czr005::ics::G4IRSF25CorridorTrajectoryRow;
using czr005::ics::Graph;
using czr005::ics::Node;
using czr005::ics::kG4IRSF25CLCRFeatureCount;

struct Checks {
  int failures = 0;

  void require(bool condition, const std::string& message) {
    if (!condition) {
      ++failures;
      std::cerr << "FAIL: " << message << '\n';
    }
  }
};

Graph branch_graph() {
  Graph graph;
  graph.add_node(Node{0, 1, 0.05, 0, 0, {}});
  graph.add_node(Node{1, 4, 0.05, 1, 0, {}});
  graph.add_node(Node{2, 4, 0.05, 1, 1, {}});
  graph.add_node(Node{3, 2, 0.0, 2, 0, {}});
  graph.add_edge(Edge{0, 1, 1.0, 1.0});
  graph.add_edge(Edge{0, 2, 1.0, 1.0});
  graph.add_edge(Edge{1, 3, 1.0, 1.0});
  graph.add_edge(Edge{2, 3, 1.0, 1.0});
  graph.set_heuristic({
      {0.0, 1.0, 1.0, 2.0},
      {1.0, 0.0, 1.0, 1.0},
      {1.0, 1.0, 0.0, 1.5},
      {2.0, 1.0, 1.5, 0.0},
  });
  return graph;
}

Graph nested_branch_graph() {
  Graph graph;
  for (int node = 0; node <= 7; ++node) {
    graph.add_node(Node{node, 4, 0.05, node / 4, node % 4, {}});
  }
  graph.add_edge(Edge{0, 1, 1.0, 1.0});
  graph.add_edge(Edge{0, 6, 5.0, 1.0});
  graph.add_edge(Edge{1, 2, 1.0, 1.0});
  graph.add_edge(Edge{1, 3, 1.0, 1.0});
  graph.add_edge(Edge{1, 5, 10.0, 1.0});
  graph.add_edge(Edge{2, 4, 1.0, 1.0});
  graph.add_edge(Edge{3, 4, 1.0, 1.0});
  graph.add_edge(Edge{4, 7, 1.0, 1.0});
  graph.add_edge(Edge{5, 7, 1.0, 1.0});
  graph.add_edge(Edge{6, 5, 1.0, 1.0});
  graph.set_heuristic(std::vector<std::vector<double>>(
      8U, std::vector<double>(8U, 0.0)));
  return graph;
}

EventDrivenJunctionConfig base_config() {
  EventDrivenJunctionConfig config;
  config.scorer_mode = "S4";
  config.enable_source_admission = false;
  config.enable_backpressure = false;
  config.enable_pibt_lite = false;
  config.enable_deadlock_escape = false;
  config.pibt_mode = "P0";
  config.retry_interval = 0.05;
  config.trace_limit = 100;
  config.max_events = 10000;
  config.max_simulation_time = 100.0;
  return config;
}

G4IRSF25CLCRConfig clcr_config(const std::string& mode) {
  G4IRSF25CLCRConfig config;
  config.mode = mode;
  config.record_trajectories = true;
  config.min_support = 2;
  config.margin_seconds = 0.5;
  config.private_cap_seconds = 60.0;
  config.trajectory_max_seconds = 20.0;
  G4IRSF25CLCRArm first;
  first.branch_node = 0;
  first.first_edge = 1;
  first.rejoin_node = 3;
  first.corridor_nodes = {0, 1, 3};
  first.support = 8;
  first.training_support = 8;
  first.static_duration_seconds = 2.0;
  G4IRSF25CLCRArm second = first;
  second.first_edge = 2;
  second.corridor_nodes = {0, 2, 3};
  second.static_duration_seconds = 2.5;
  second.system_intercept = -2.0;
  config.arms = {first, second};
  if (mode == "l1" || mode == "l3") {
    config.system_weights.assign(kG4IRSF25CLCRFeatureCount, 0.0);
    config.private_weights.assign(kG4IRSF25CLCRFeatureCount, 0.0);
  }
  return config;
}

G4IRSF25CLCRConfig nested_clcr_config() {
  auto config = clcr_config("observe");
  config.arms.clear();
  const auto arm = [](int branch,
                      int first_edge,
                      int rejoin,
                      std::vector<int> corridor,
                      double static_duration) {
    G4IRSF25CLCRArm value;
    value.branch_node = branch;
    value.first_edge = first_edge;
    value.rejoin_node = rejoin;
    value.corridor_nodes = std::move(corridor);
    value.support = 8;
    value.training_support = 8;
    value.static_duration_seconds = static_duration;
    return value;
  };
  config.arms = {
      arm(0, 1, 5, {0, 1, 5}, 12.0),
      arm(0, 6, 5, {0, 6, 5}, 6.0),
      arm(1, 2, 4, {1, 2, 4}, 2.0),
      arm(1, 3, 4, {1, 3, 4}, 2.0),
  };
  return config;
}

EventDrivenJunctionResult run(
    EventDrivenJunctionConfig config,
    const std::vector<EventRuntimeFaultWindow>& faults = {}) {
  return EventDrivenJunctionRuntime(branch_graph(), std::move(config))
      .run({EventRuntimeBagRequest{
                "unit", 1, 0.0, 100.0, 0, 3, "g25-test"}},
           faults);
}

EventDrivenJunctionResult run_requests(
    const Graph& graph,
    EventDrivenJunctionConfig config,
    const std::vector<EventRuntimeBagRequest>& requests) {
  return EventDrivenJunctionRuntime(graph, std::move(config)).run(requests);
}

bool near(double left, double right, double tolerance = 1.0e-9) {
  return std::abs(left - right) <= tolerance;
}

const EventDecisionTraceRow* branch_decision(
    const EventDrivenJunctionResult& result) {
  for (const auto& decision : result.decisions) {
    if (decision.current_node == 0) {
      return &decision;
    }
  }
  return nullptr;
}

void require_safe(Checks& checks,
                  const EventDrivenJunctionResult& result,
                  const std::string& label) {
  checks.require(result.summary.completed_count == 1,
                 label + ": bag must complete");
  checks.require(result.summary.failed_count == 0,
                 label + ": no bag may fail");
  checks.require(
      result.summary.physical_fault_edge_entry_violation_count == 0 &&
          result.summary.runtime_full_astar_calls == 0 &&
          result.summary.global_reservation_scan_count == 0,
      label + ": CLCR must remain shielded, one-hop, and scan-free");
}

void test_off_and_observe_trajectory(Checks& checks) {
  const auto off = run(base_config());
  auto observe_config = base_config();
  observe_config.g4irsf25_clcr = clcr_config("observe");
  const auto observe = run(std::move(observe_config));
  require_safe(checks, off, "off");
  require_safe(checks, observe, "observe");
  const auto* off_decision = branch_decision(off);
  const auto* observed_decision = branch_decision(observe);
  checks.require(off_decision != nullptr && observed_decision != nullptr &&
                     off_decision->selected_next ==
                         observed_decision->selected_next,
                 "observe mode must preserve the exact S4 branch action");
  checks.require(off.summary.g4irsf25_clcr_route_evaluation_count == 0 &&
                     off.summary.g4irsf25_clcr_mode.empty(),
                 "empty artifact must keep the G25 path entirely off");
  checks.require(observe.g4irsf25_corridor_trajectories.size() == 1,
                 "observe mode must emit one real branch-to-rejoin row");
  if (observe.g4irsf25_corridor_trajectories.size() == 1) {
    const auto& row = observe.g4irsf25_corridor_trajectories.front();
    checks.require(row.completed_rejoin && !row.timeout && row.safe &&
                       row.actual_corridor_duration > 0.0 &&
                       row.private_bag_cost_seconds ==
                           row.actual_corridor_duration,
                   "trajectory must close on the actual rejoin arrival");
    checks.require(row.actual_path == std::vector<int>({0, 1, 3}) &&
                       row.actual_path.size() <= 11,
                   "trajectory path must be real and locally bounded");
    checks.require(row.feedback_sample_count == 1,
                   "rejoin must publish exactly one feedback sample");
  }
}

void test_overlapping_trajectory_integrals(Checks& checks) {
  const auto graph = branch_graph();
  auto config = base_config();
  config.g4irsf25_clcr = clcr_config("observe");
  const auto result = run_requests(
      graph, std::move(config),
      {
          EventRuntimeBagRequest{
              "overlap-a", 11, 0.0, 100.0, 0, 3, "g25-test"},
          EventRuntimeBagRequest{
              "overlap-b", 12, 0.0, 100.0, 0, 3, "g25-test"},
      });
  checks.require(result.summary.completed_count == 2 &&
                     result.summary.failed_count == 0,
                 "overlap fixture must complete both bags safely");
  checks.require(
      result.summary.g4irsf25_corridor_trajectory_started_count == 2 &&
          result.summary.g4irsf25_corridor_trajectory_completed_count == 2 &&
          result.summary.g4irsf25_corridor_trajectory_timeout_count == 0 &&
          result.g4irsf25_corridor_trajectories.size() == 2,
      "two overlapping decisions must close exactly two trajectories");
  if (result.g4irsf25_corridor_trajectories.size() != 2) {
    return;
  }

  const auto* first = &result.g4irsf25_corridor_trajectories[0];
  const auto* second = &result.g4irsf25_corridor_trajectories[1];
  if (second->decision_time < first->decision_time) {
    std::swap(first, second);
  }
  checks.require(
      std::max(first->decision_time, second->decision_time) + 1.0e-9 <
          std::min(first->arrival_time, second->arrival_time),
      "fixture must exercise genuinely overlapping accumulator windows");
  for (const auto* row : {first, second}) {
    const double active_bag_bound = 2.0 * row->actual_corridor_duration;
    checks.require(row->completed_rejoin && !row->timeout && !row->censored &&
                       row->actual_corridor_duration > 0.0,
                   "each overlapping trajectory must complete, not censor");
    checks.require(row->local_queue_area_bag_seconds >= 0.0 &&
                       row->scheduled_incoming_area_bag_seconds >= 0.0 &&
                       row->local_queue_area_bag_seconds +
                               row->scheduled_incoming_area_bag_seconds <=
                           active_bag_bound + 1.0e-8,
                   "shared cumulative differences must not double-count the "
                   "two-bag local occupancy");
  }
  checks.require(
      first->local_queue_area_bag_seconds +
              first->scheduled_incoming_area_bag_seconds >
          0.0 &&
          second->local_queue_area_bag_seconds +
                  second->scheduled_incoming_area_bag_seconds >
              0.0,
      "both overlapping windows must receive non-zero integrated evidence");
}

void test_pending_checkpoint_restore_equivalence(Checks& checks) {
  const auto graph = branch_graph();
  auto config = base_config();
  config.g4irsf25_clcr = clcr_config("l3");
  const std::vector<EventRuntimeBagRequest> requests = {
      EventRuntimeBagRequest{
          "checkpoint-a", 21, 0.0, 100.0, 0, 3, "g25-test"},
      EventRuntimeBagRequest{
          "checkpoint-b", 22, 6.0, 100.0, 0, 3, "g25-test"},
  };

  EventDrivenJunctionRuntime source(graph, config);
  source.initialize(requests);
  std::optional<EventDrivenJunctionRuntime::StateCheckpoint> checkpoint;
  while (source.process_one_event()) {
    const auto& partial = source.current_result();
    if (partial.summary.g4irsf25_corridor_trajectory_started_count == 1 &&
        partial.summary.g4irsf25_corridor_trajectory_completed_count == 0) {
      checks.require(partial.g4irsf25_corridor_trajectories.empty(),
                     "checkpoint fixture must capture a still-pending row");
      checkpoint = source.capture_state_checkpoint();
      break;
    }
  }
  checks.require(checkpoint.has_value(),
                 "checkpoint fixture must find one live G25 trajectory");
  if (!checkpoint.has_value()) {
    return;
  }

  EventDrivenJunctionRuntime restored(graph, config);
  restored.restore_state_checkpoint(*checkpoint);
  source.drain();
  restored.drain();
  const auto& uninterrupted = source.finalize();
  const auto& resumed = restored.finalize();

  const auto& left_summary = uninterrupted.summary;
  const auto& right_summary = resumed.summary;
  checks.require(left_summary.completed_count == right_summary.completed_count &&
                     left_summary.failed_count == right_summary.failed_count &&
                     left_summary.event_count == right_summary.event_count &&
                     near(left_summary.end_time, right_summary.end_time),
                 "restore must preserve terminal runtime counts and time");
  checks.require(
      left_summary.g4irsf25_clcr_route_evaluation_count ==
              right_summary.g4irsf25_clcr_route_evaluation_count &&
          left_summary.g4irsf25_clcr_proposal_count ==
              right_summary.g4irsf25_clcr_proposal_count &&
          left_summary.g4irsf25_clcr_committed_mutation_count ==
              right_summary.g4irsf25_clcr_committed_mutation_count &&
          left_summary.g4irsf25_clcr_feedback_count ==
              right_summary.g4irsf25_clcr_feedback_count &&
          left_summary.g4irsf25_clcr_online_bias_update_count ==
              right_summary.g4irsf25_clcr_online_bias_update_count &&
          left_summary.g4irsf25_corridor_trajectory_started_count ==
              right_summary.g4irsf25_corridor_trajectory_started_count &&
          left_summary.g4irsf25_corridor_trajectory_completed_count ==
              right_summary.g4irsf25_corridor_trajectory_completed_count &&
          left_summary.g4irsf25_corridor_trajectory_timeout_count ==
              right_summary.g4irsf25_corridor_trajectory_timeout_count,
      "restore must preserve all G25 lifecycle and feedback counters");
  checks.require(
      uninterrupted.g4irsf25_corridor_trajectories.size() ==
          resumed.g4irsf25_corridor_trajectories.size(),
      "restore must emit the same number of G25 trajectory rows");
  if (uninterrupted.g4irsf25_corridor_trajectories.size() ==
      resumed.g4irsf25_corridor_trajectories.size()) {
    for (std::size_t index = 0;
         index < uninterrupted.g4irsf25_corridor_trajectories.size();
         ++index) {
      const auto& left = uninterrupted.g4irsf25_corridor_trajectories[index];
      const auto& right = resumed.g4irsf25_corridor_trajectories[index];
      checks.require(
          left.runtime_bag_id == right.runtime_bag_id &&
              left.branch_node == right.branch_node &&
              left.s4_first_edge == right.s4_first_edge &&
              left.selected_first_edge == right.selected_first_edge &&
              left.rejoin_node == right.rejoin_node &&
              near(left.decision_time, right.decision_time) &&
              near(left.arrival_time, right.arrival_time) &&
              near(left.actual_corridor_duration,
                   right.actual_corridor_duration) &&
              near(left.local_queue_area_bag_seconds,
                   right.local_queue_area_bag_seconds) &&
              near(left.scheduled_incoming_area_bag_seconds,
                   right.scheduled_incoming_area_bag_seconds) &&
              left.peak_local_queue == right.peak_local_queue &&
              left.actual_path == right.actual_path &&
              left.selected_features == right.selected_features &&
              left.feedback_sample_count == right.feedback_sample_count &&
              near(left.feedback_short_ewma_seconds,
                   right.feedback_short_ewma_seconds) &&
              near(left.feedback_long_ewma_seconds,
                   right.feedback_long_ewma_seconds) &&
              near(left.feedback_short_local_system_cost,
                   right.feedback_short_local_system_cost) &&
              near(left.feedback_long_local_system_cost,
                   right.feedback_long_local_system_cost) &&
              near(left.applied_online_bias, right.applied_online_bias) &&
              left.completed_rejoin == right.completed_rejoin &&
              left.timeout == right.timeout &&
              left.censored == right.censored &&
              left.censor_reason == right.censor_reason,
          "pending checkpoint restore must reproduce every trajectory field");
    }
  }

  checks.require(uninterrupted.decisions.size() == resumed.decisions.size(),
                 "restore must preserve the decision trace cardinality");
  if (uninterrupted.decisions.size() == resumed.decisions.size()) {
    for (std::size_t index = 0; index < uninterrupted.decisions.size();
         ++index) {
      const auto& left = uninterrupted.decisions[index];
      const auto& right = resumed.decisions[index];
      checks.require(
          left.runtime_bag_id == right.runtime_bag_id &&
              left.current_node == right.current_node &&
              near(left.event_time, right.event_time) &&
              left.selected_next == right.selected_next &&
              left.g4irsf25_clcr_s4_next == right.g4irsf25_clcr_s4_next &&
              left.g4irsf25_clcr_proposed_next ==
                  right.g4irsf25_clcr_proposed_next &&
              near(left.g4irsf25_clcr_predicted_system_delta_seconds,
                   right.g4irsf25_clcr_predicted_system_delta_seconds) &&
              near(left.g4irsf25_clcr_predicted_private_delta_seconds,
                   right.g4irsf25_clcr_predicted_private_delta_seconds) &&
              left.g4irsf25_clcr_fallback_reason ==
                  right.g4irsf25_clcr_fallback_reason &&
              left.g4irsf25_clcr_committed_mutation ==
                  right.g4irsf25_clcr_committed_mutation,
          "restore must preserve the G25 decision stream exactly");
    }
  }
}

void test_registered_split_supersedes_without_feedback_or_timeout(
    Checks& checks) {
  const auto graph = nested_branch_graph();
  auto config = base_config();
  config.g4irsf25_clcr = nested_clcr_config();
  const auto result = run_requests(
      graph, std::move(config),
      {
          EventRuntimeBagRequest{
              "supersede-main", 31, 0.0, 100.0, 0, 7, "g25-test"},
          EventRuntimeBagRequest{
              "advance-clock", 32, 30.0, 100.0, 4, 7, "g25-test"},
      });

  checks.require(result.summary.completed_count == 2 &&
                     result.summary.failed_count == 0,
                 "supersede fixture must complete both physical bags");
  checks.require(
      result.summary.g4irsf25_corridor_trajectory_started_count == 2 &&
          result.summary.g4irsf25_corridor_trajectory_completed_count == 1 &&
          result.summary.g4irsf25_corridor_trajectory_timeout_count == 0 &&
          result.summary.g4irsf25_clcr_feedback_count == 1 &&
          result.g4irsf25_corridor_trajectories.size() == 2,
      "supersede must yield one censored prefix and one feedback-eligible "
      "inner completion");

  const G4IRSF25CorridorTrajectoryRow* outer = nullptr;
  const G4IRSF25CorridorTrajectoryRow* inner = nullptr;
  for (const auto& row : result.g4irsf25_corridor_trajectories) {
    if (row.branch_node == 0) {
      outer = &row;
    } else if (row.branch_node == 1) {
      inner = &row;
    }
  }
  checks.require(outer != nullptr && inner != nullptr,
                 "nested fixture must emit both registered split rows");
  if (outer == nullptr || inner == nullptr) {
    return;
  }
  checks.require(
      outer->selected_first_edge == 1 && !outer->completed_rejoin &&
          !outer->timeout && outer->censored &&
          outer->censor_reason == "SUPERSEDED_BY_REGISTERED_SPLIT" &&
          outer->feedback_sample_count == 0,
      "superseded outer prefix must be censored and publish no feedback");
  checks.require(
      inner->selected_first_edge == 2 && inner->completed_rejoin &&
          !inner->timeout && !inner->censored &&
          inner->feedback_sample_count == 1,
      "inner registered corridor must own the sole completion feedback");
  checks.require(
      result.summary.end_time >
              outer->decision_time +
                  nested_clcr_config().trajectory_max_seconds &&
          result.summary.g4irsf25_corridor_trajectory_timeout_count == 0,
      "advancing beyond the erased outer deadline must not create a stale "
      "timeout");
}

void test_l1_mutation_and_fairness(Checks& checks) {
  auto config = base_config();
  config.g4irsf25_clcr = clcr_config("l1");
  const auto result = run(std::move(config));
  require_safe(checks, result, "L1 mutation");
  const auto* decision = branch_decision(result);
  checks.require(
      decision != nullptr && decision->g4irsf25_clcr_s4_next == 1 &&
          decision->g4irsf25_clcr_proposed_next == 2 &&
          decision->selected_next == 2 &&
          decision->g4irsf25_clcr_committed_mutation,
      "supported L1 prediction must commit one real first-edge mutation");
  checks.require(result.summary.g4irsf25_clcr_proposal_count == 1 &&
                     result.summary.g4irsf25_clcr_committed_mutation_count == 1 &&
                     result.summary
                             .g4irsf25_clcr_committed_mutations_by_branch.at(0) ==
                         1,
                 "proposal, commit, and branch counters must stay distinct");

  auto fairness_config = base_config();
  fairness_config.g4irsf25_clcr = clcr_config("l1");
  fairness_config.g4irsf25_clcr.arms[1].private_intercept = 100.0;
  const auto fairness = run(std::move(fairness_config));
  const auto* fallback = branch_decision(fairness);
  checks.require(fallback != nullptr && fallback->selected_next == 1 &&
                     !fallback->g4irsf25_clcr_committed_mutation &&
                     fairness.summary.g4irsf25_clcr_fairness_fallback_count > 0,
                 "private-cost cap must fall back to the exact S4 action");
}

void test_t0_support_ood_and_fault_fallbacks(Checks& checks) {
  auto closed = base_config();
  closed.g4irsf25_clcr = clcr_config("t0");
  closed.g4irsf25_clcr.t0_enter_pressure = 1.0;
  closed.g4irsf25_clcr.t0_exit_pressure = 0.5;
  closed.g4irsf25_clcr.arms[1].t0_system_delta_seconds = -2.0;
  const auto threshold = run(std::move(closed));
  checks.require(branch_decision(threshold)->selected_next == 1 &&
                     threshold.summary
                             .g4irsf25_clcr_threshold_fallback_count > 0,
                 "T0 must abstain below its single local pressure threshold");

  auto low_support = base_config();
  low_support.g4irsf25_clcr = clcr_config("l1");
  low_support.g4irsf25_clcr.arms[1].training_support = 1;
  const auto low = run(std::move(low_support));
  checks.require(branch_decision(low)->selected_next == 1 &&
                     low.summary.g4irsf25_clcr_low_support_fallback_count > 0,
                 "low-support alternate arm must preserve S4");

  auto ood_config = base_config();
  ood_config.g4irsf25_clcr = clcr_config("l1");
  ood_config.g4irsf25_clcr.feature_min.assign(
      kG4IRSF25CLCRFeatureCount, 0.0);
  ood_config.g4irsf25_clcr.feature_max.assign(
      kG4IRSF25CLCRFeatureCount, 0.0);
  const auto ood = run(std::move(ood_config));
  checks.require(branch_decision(ood)->selected_next == 1 &&
                     ood.summary.g4irsf25_clcr_ood_fallback_count > 0,
                 "out-of-domain context must preserve S4");

  auto fault_config = base_config();
  fault_config.g4irsf25_clcr = clcr_config("l1");
  fault_config.g4irsf25_clcr.arms[1].system_intercept = -100.0;
  const auto fault = run(
      std::move(fault_config),
      {EventRuntimeFaultWindow{0, 2, 0.0, 10.0, 0.0, false}});
  require_safe(checks, fault, "fault fallback");
  checks.require(branch_decision(fault)->selected_next == 1 &&
                     fault.summary
                             .g4irsf25_clcr_fault_shield_fallback_count > 0,
                 "faulted alternate arm must remain owned by the shield");
}

void test_validation_and_l3_feedback(Checks& checks) {
  bool rejected = false;
  try {
    auto malformed = base_config();
    malformed.g4irsf25_clcr = clcr_config("l1");
    malformed.g4irsf25_clcr.feature_mean.assign(
        kG4IRSF25CLCRFeatureCount, 0.0);
    EventDrivenJunctionRuntime runtime(branch_graph(), std::move(malformed));
    (void)runtime;
  } catch (const std::invalid_argument&) {
    rejected = true;
  }
  checks.require(rejected,
                 "normalization vectors must be supplied as complete pairs");

  auto l3 = base_config();
  l3.g4irsf25_clcr = clcr_config("l3");
  const auto result = run(std::move(l3));
  require_safe(checks, result, "L3 feedback");
  checks.require(result.summary.g4irsf25_clcr_feedback_count == 1 &&
                     result.summary.g4irsf25_clcr_online_bias_update_count == 1 &&
                     result.summary
                             .g4irsf25_corridor_trajectory_completed_count == 1,
                 "L3 must update one bounded arm bias only at rejoin");
}

}  // namespace

int main() {
  Checks checks;
  test_off_and_observe_trajectory(checks);
  test_overlapping_trajectory_integrals(checks);
  test_pending_checkpoint_restore_equivalence(checks);
  test_registered_split_supersedes_without_feedback_or_timeout(checks);
  test_l1_mutation_and_fairness(checks);
  test_t0_support_ood_and_fault_fallbacks(checks);
  test_validation_and_l3_feedback(checks);
  if (checks.failures != 0) {
    std::cerr << checks.failures << " G4IRSF25 CLCR checks failed\n";
    return 1;
  }
  std::cout << "G4IRSF25 CLCR checks passed\n";
  return 0;
}
