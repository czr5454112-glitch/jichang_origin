#include <cmath>
#include <iostream>
#include <set>
#include <string>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"

namespace {

using czr005::ics::Edge;
using czr005::ics::EventDrivenJunctionConfig;
using czr005::ics::EventDrivenJunctionRuntime;
using czr005::ics::EventRuntimeBagRequest;
using czr005::ics::EventRuntimeFaultWindow;
using czr005::ics::Graph;
using czr005::ics::Node;

struct Checks {
  int failures = 0;

  void require(bool condition, const std::string& message) {
    if (!condition) {
      ++failures;
      std::cerr << "FAIL: " << message << '\n';
    }
  }
};

Graph line_graph(double service_time = 1.0) {
  Graph graph;
  graph.add_node(Node{0, 1, service_time, 0, 0, {}});
  graph.add_node(Node{1, 4, service_time, 1, 0, {}});
  graph.add_node(Node{2, 2, service_time, 2, 0, {}});
  graph.add_edge(Edge{0, 1, 1.0, 1.0});
  graph.add_edge(Edge{1, 2, 1.0, 1.0});
  graph.set_heuristic({{0.0, 1.0, 2.0}, {1.0, 0.0, 1.0}, {2.0, 1.0, 0.0}});
  return graph;
}

EventDrivenJunctionConfig test_config() {
  EventDrivenJunctionConfig config;
  config.queue_discipline = "aging";
  config.retry_interval = 0.05;
  config.minimum_service_seconds = 0.001;
  config.dispatch_headway_seconds = 0.001;
  config.max_decisions_per_bag = 1000;
  config.max_events = 200000;
  config.max_simulation_time = 200.0;
  config.trace_limit = 200000;
  config.deadlock_retry_threshold = 3;
  config.starvation_threshold = 1000.0;
  return config;
}

std::vector<EventRuntimeBagRequest> burst(int count, int start = 0, int goal = 2) {
  std::vector<EventRuntimeBagRequest> bags;
  for (int index = 0; index < count; ++index) {
    bags.push_back(EventRuntimeBagRequest{
        "burst-" + std::to_string(index), index + 1, 0.0, 1000.0, start, goal, "source"});
  }
  return bags;
}

void check_core_invariants(Checks& checks,
                           const czr005::ics::EventDrivenJunctionResult& result,
                           int expected_completed) {
  checks.require(result.summary.completed_count == expected_completed,
                 "all expected bags should complete");
  checks.require(result.summary.failed_count == 0, "no bag should fail");
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
    checks.require(!decision.full_astar_used, "decision trace must mark full_astar_used=false");
    if (decision.selected_next >= 0) {
      bool found = false;
      for (const auto& candidate : decision.candidates) {
        found = found || candidate.next_node == decision.selected_next;
      }
      checks.require(found, "selected action must be a true outgoing candidate");
    }
  }
}

void test_burst_sizes(Checks& checks) {
  for (const int count : {1, 2, 4, 8, 16}) {
    const auto graph = line_graph();
    EventDrivenJunctionRuntime runtime(graph, test_config());
    const auto result = runtime.run(burst(count));
    check_core_invariants(checks, result, count);
    checks.require(result.summary.decision_count >= count * 2,
                   "line graph must decide independently at both junctions");
    checks.require(result.summary.max_source_queue_length >= count - 1,
                   "source burst must be represented as a real local queue");
    if (count == 16) {
      checks.require(result.summary.max_source_queue_delay >= 14.9,
                     "16-bag burst must expose source admission delay");
      checks.require(result.summary.fairness_jain > 0.0 &&
                         result.summary.fairness_jain <= 1.0,
                     "fairness metric must be in (0, 1]");
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

void test_bidirectional_corridor(Checks& checks) {
  Graph graph;
  graph.add_node(Node{0, 1, 0.001, 0, 0, {}});
  graph.add_node(Node{1, 2, 0.001, 1, 0, {}});
  graph.add_edge(Edge{0, 1, 1.0, 1.0});
  graph.add_edge(Edge{1, 0, 1.0, 1.0});
  graph.set_heuristic({{0.0, 1.0}, {1.0, 0.0}});
  std::vector<EventRuntimeBagRequest> bags{
      {"eastbound", 101, 0.0, 20.0, 0, 1, "west"},
      {"westbound", 102, 0.0, 20.0, 1, 0, "east"},
  };
  EventDrivenJunctionRuntime runtime(graph, test_config());
  const auto result = runtime.run(bags);
  check_core_invariants(checks, result, 2);
  checks.require(result.summary.shield_rejection_count > 0,
                 "opposite-direction traffic must observe the shared corridor calendar");
}

void test_loop_tabu(Checks& checks) {
  Graph graph;
  graph.add_node(Node{0, 1, 0.001, 0, 0, {}});
  graph.add_node(Node{1, 4, 0.001, 1, 0, {}});
  graph.add_node(Node{2, 2, 0.001, 2, 0, {}});
  graph.add_edge(Edge{0, 1, 1.0, 1.0});
  graph.add_edge(Edge{1, 0, 1.0, 1.0});
  graph.add_edge(Edge{1, 2, 1.0, 1.0});
  // Deliberately misleading static potential: bounded recent-history/tabu must
  // prevent the immediate 1->0 loop without searching for a full route.
  graph.set_heuristic({{0.0, 0.0, 0.0}, {0.0, 0.0, 0.0}, {0.0, 0.0, 10.0}});
  EventDrivenJunctionRuntime runtime(graph, test_config());
  const auto result = runtime.run({{"loop-guard", 201, 0.0, 20.0, 0, 2, "source"}});
  check_core_invariants(checks, result, 1);
  checks.require(result.summary.loop_count == 0,
                 "short local tabu memory should avoid the immediate loop");
  checks.require(result.bags.front().short_history.size() <= 8,
                 "loop protection must not store a future or unbounded path");
}

void test_non_goal_terminal_sink_is_locally_shielded(Checks& checks) {
  Graph graph;
  graph.add_node(Node{0, 1, 0.001, 0, 0, {}});
  graph.add_node(Node{1, 2, 0.001, 1, 0, {}});  // terminal, but not this bag's goal
  graph.add_node(Node{2, 4, 0.001, 0, 1, {}});
  graph.add_node(Node{3, 2, 0.001, 1, 1, {}});
  graph.add_edge(Edge{0, 1, 1.0, 1.0});
  graph.add_edge(Edge{0, 2, 1.0, 1.0});
  graph.add_edge(Edge{2, 3, 1.0, 1.0});
  // Make the wrong terminal sink look best to the local scorer.  The shield
  // must reject it using only its one-hop outdegree and the bag goal.
  graph.set_heuristic({
      {0.0, 0.0, 0.0, 0.0},
      {0.0, 0.0, 0.0, 0.0},
      {0.0, 0.0, 0.0, 10.0},
      {0.0, 0.0, 0.0, 0.0},
  });
  EventDrivenJunctionRuntime runtime(graph, test_config());
  const auto result = runtime.run({{"dead-end-shield", 250, 0.0, 20.0, 0, 3, "source"}});
  check_core_invariants(checks, result, 1);
  checks.require(!result.decisions.empty() && result.decisions.front().model_prediction == 1 &&
                     result.decisions.front().selected_next == 2,
                 "local shield must hand off from a non-goal terminal sink");
  bool saw_dead_end_rejection = false;
  for (const auto& candidate : result.decisions.front().candidates) {
    if (candidate.next_node == 1) {
      saw_dead_end_rejection = !candidate.shield_allowed &&
                               candidate.shield_reason == "dead_end_not_goal";
    }
  }
  checks.require(saw_dead_end_rejection,
                 "candidate trace must expose dead_end_not_goal rejection");
}

void test_non_goal_terminal_successor_trap_is_locally_shielded(Checks& checks) {
  Graph graph;
  graph.add_node(Node{0, 1, 0.001, 0, 0, {}});
  graph.add_node(Node{1, 4, 0.001, 1, 0, {}});  // leads only to wrong terminal 3
  graph.add_node(Node{2, 4, 0.001, 0, 1, {}});  // safe branch to goal 4
  graph.add_node(Node{3, 2, 0.001, 2, 0, {}});
  graph.add_node(Node{4, 2, 0.001, 1, 1, {}});
  graph.add_edge(Edge{0, 1, 1.0, 1.0});
  graph.add_edge(Edge{0, 2, 1.0, 1.0});
  graph.add_edge(Edge{1, 3, 1.0, 1.0});
  graph.add_edge(Edge{2, 4, 1.0, 1.0});
  graph.set_heuristic({
      {0.0, 0.0, 0.0, 0.0, 0.0},
      {0.0, 0.0, 0.0, 0.0, 0.0},
      {0.0, 0.0, 0.0, 0.0, 10.0},
      {0.0, 0.0, 0.0, 0.0, 0.0},
      {0.0, 0.0, 0.0, 0.0, 0.0},
  });
  EventDrivenJunctionRuntime runtime(graph, test_config());
  const auto result = runtime.run({{"terminal-trap-shield", 251, 0.0, 20.0, 0, 4, "source"}});
  check_core_invariants(checks, result, 1);
  checks.require(!result.decisions.empty() && result.decisions.front().model_prediction == 1 &&
                     result.decisions.front().selected_next == 2,
                 "bounded two-hop shield must avoid a forced non-goal terminal successor");
  bool saw_terminal_trap_rejection = false;
  for (const auto& candidate : result.decisions.front().candidates) {
    if (candidate.next_node == 1) {
      saw_terminal_trap_rejection =
          !candidate.shield_allowed &&
          candidate.shield_reason == "terminal_successor_trap_not_goal";
    }
  }
  checks.require(saw_terminal_trap_rejection,
                 "candidate trace must expose terminal_successor_trap_not_goal rejection");
}

void test_fault_repair_delay_and_escape(Checks& checks) {
  const auto graph = line_graph(0.001);
  auto config = test_config();
  config.retry_interval = 0.1;
  config.deadlock_retry_threshold = 2;
  EventDrivenJunctionRuntime runtime(graph, config);
  const std::vector<EventRuntimeFaultWindow> faults{{0, 1, 0.0, 1.0, 0.25}};
  const auto result = runtime.run({{"repair-wait", 301, 0.0, 20.0, 0, 2, "source"}}, faults);
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
  Graph graph;
  graph.add_node(Node{0, 1, 0.001, 0, 0, {}});
  graph.add_node(Node{1, 2, 0.001, 2, 0, {}});
  graph.add_node(Node{2, 4, 0.001, 1, 1, {}});
  graph.add_edge(Edge{0, 1, 1.0, 1.0});
  graph.add_edge(Edge{0, 2, 1.0, 1.0});
  graph.add_edge(Edge{2, 1, 1.0, 1.0});
  graph.set_heuristic({{0.0, 0.0, 0.0}, {1.0, 0.0, 1.0}, {1.0, 1.0, 0.0}});
  EventDrivenJunctionRuntime runtime(graph, test_config());
  const auto result = runtime.run(
      {{"delayed-fault", 401, 0.0, 20.0, 0, 1, "source"}},
      {{0, 1, 0.0, 5.0, 2.0}});
  check_core_invariants(checks, result, 1);
  checks.require(result.summary.pibt_lite_handoff_count > 0,
                 "PIBT-lite local shield should hand off to a safe alternate edge");
  checks.require(!result.decisions.empty() && result.decisions.front().model_prediction == 1 &&
                     result.decisions.front().selected_next == 2,
                 "delayed fault must change only the shielded one-step action");
}

void test_fault_policy_toggle_keeps_physical_interlock_independent(Checks& checks) {
  Graph graph;
  graph.add_node(Node{0, 1, 0.001, 0, 0, {}});
  graph.add_node(Node{1, 2, 0.001, 2, 0, {}});
  graph.add_node(Node{2, 4, 0.001, 1, 1, {}});
  graph.add_edge(Edge{0, 1, 1.0, 1.0});
  graph.add_edge(Edge{0, 2, 1.0, 1.0});
  graph.add_edge(Edge{2, 1, 1.0, 1.0});
  graph.set_heuristic({{0.0, 0.0, 0.0}, {1.0, 0.0, 1.0}, {1.0, 1.0, 0.0}});

  auto policy_on_config = test_config();
  policy_on_config.enable_fault_policy = true;
  EventDrivenJunctionRuntime policy_on_runtime(graph, policy_on_config);
  const auto policy_on = policy_on_runtime.run(
      {{"fault-policy-on", 451, 0.0, 20.0, 0, 1, "source"}},
      {{0, 1, 0.0, 1.0, 0.0}});
  check_core_invariants(checks, policy_on, 1);
  checks.require(policy_on.summary.fault_policy_enabled,
                 "policy-on run must report its independent configuration");
  checks.require(policy_on.summary.fault_affected_bag_count == 1 &&
                     policy_on.summary.fault_target_edge_candidate_exposure_count > 0 &&
                     policy_on.summary.fault_target_edge_attempt_count > 0,
                 "policy-on run must expose a real affected cohort and target attempt");
  checks.require(policy_on.summary.local_fault_policy_reroute_count > 0 &&
                     policy_on.summary.local_fault_policy_action_count > 0,
                 "advertised policy must proactively reroute the base target action");
  checks.require(policy_on.summary.physical_fault_edge_entry_violation_count == 0,
                 "proactive policy must retain the physical edge-entry boundary");

  auto policy_off_config = test_config();
  policy_off_config.enable_fault_policy = false;
  EventDrivenJunctionRuntime policy_off_runtime(graph, policy_off_config);
  const auto policy_off = policy_off_runtime.run(
      {{"fault-policy-off", 452, 0.0, 20.0, 0, 1, "source"}},
      {{0, 1, 0.0, 1.0, 0.0}});
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
  const auto graph = line_graph(0.01);
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
  std::set_intersection(left_tasks.begin(), left_tasks.end(),
                        right_tasks.begin(), right_tasks.end(),
                        std::back_inserter(overlap));
  checks.require(overlap.empty(), "deterministic task shards must not overlap");
  left_tasks.insert(right_tasks.begin(), right_tasks.end());
  checks.require(left_tasks.size() == 16, "two shards must cover every burst task");
  checks.require(left.summary.decision_trace_shard_seen_count +
                         right.summary.decision_trace_shard_seen_count ==
                     left.summary.decision_trace_seen_count,
                 "shard seen counts must reconstruct the complete decision stream");
}

void test_duplicate_original_task_segments_keep_internal_identity(Checks& checks) {
  const auto graph = line_graph(0.001);
  std::vector<EventRuntimeBagRequest> bags{
      {"77:storage_in", 77, 0.0, 100.0, 0, 2, "source"},
      {"77:storage_out", 77, 10.0, 100.0, 0, 2, "source"},
  };
  EventDrivenJunctionRuntime runtime(graph, test_config());
  const auto result = runtime.run(bags);
  check_core_invariants(checks, result, 2);
  checks.require(result.bags.size() == 2, "both segments with one original task id must survive");
  checks.require(result.bags[0].task_id == 77 && result.bags[1].task_id == 77,
                 "original task id must never be rewritten");
  checks.require(result.bags[0].runtime_bag_id != result.bags[1].runtime_bag_id,
                 "runtime bag id must uniquely identify each segment");
}

void test_explicit_sensor_loss_keeps_physical_shield(Checks& checks) {
  const auto graph = line_graph(0.001);
  auto config = test_config();
  config.retry_interval = 0.1;
  EventDrivenJunctionRuntime runtime(graph, config);
  const auto result = runtime.run(
      {{"sensor-loss", 601, 0.0, 20.0, 0, 2, "source"}},
      {{0, 1, 0.0, 1.0, 0.25, true}});
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
  test_burst_sizes(checks);
  test_bidirectional_corridor(checks);
  test_loop_tabu(checks);
  test_non_goal_terminal_sink_is_locally_shielded(checks);
  test_non_goal_terminal_successor_trap_is_locally_shielded(checks);
  test_fault_repair_delay_and_escape(checks);
  test_delayed_fault_policy_handoff(checks);
  test_fault_policy_toggle_keeps_physical_interlock_independent(checks);
  test_deterministic_trace_shards(checks);
  test_duplicate_original_task_segments_keep_internal_identity(checks);
  test_explicit_sensor_loss_keeps_physical_shield(checks);
  return checks.failures == 0 ? 0 : 1;
}
