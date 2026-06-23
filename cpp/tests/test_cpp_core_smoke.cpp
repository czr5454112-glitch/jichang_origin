#include <cmath>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <vector>

#include "ics_core/baselines/pibt.hpp"
#include "ics_core/baselines/pibt_replay.hpp"
#include "ics_core/baselines/periodic_replanning.hpp"
#include "ics_core/baselines/rolling_horizon.hpp"
#include "ics_core/graph/graph.hpp"
#include "ics_core/io/legacy_map_reader.hpp"
#include "ics_core/io/legacy_task_reader.hpp"
#include "ics_core/metrics/metrics.hpp"
#include "ics_core/models/edge_score.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar.hpp"
#include "ics_core/routing/sipp.hpp"
#include "ics_core/runtime/edge_score_replay.hpp"
#include "ics_core/shield/junction_shield.hpp"

using czr005::ics::AStarPlanner;
using czr005::ics::Edge;
using czr005::ics::EdgeFaultWindow;
using czr005::ics::EdgeScoreModel;
using czr005::ics::EdgeScoreReplayConfig;
using czr005::ics::EdgeReservationTable;
using czr005::ics::Graph;
using czr005::ics::JunctionShield;
using czr005::ics::JunctionShieldConfig;
using czr005::ics::Node;
using czr005::ics::PIBTAgentState;
using czr005::ics::PIBTActiveBagReplayConfig;
using czr005::ics::PIBTStyleOneStepResolver;
using czr005::ics::PeriodicReplanningConfig;
using czr005::ics::ReservationTable;
using czr005::ics::RollingHorizonConfig;
using czr005::ics::RollingHorizonFaultWindow;
using czr005::ics::SafetyStatus;
using czr005::ics::SIPPPlanner;
using czr005::ics::compute_episode_metrics;
using czr005::ics::read_legacy_inputdata;
using czr005::ics::read_legacy_map2;
using czr005::ics::run_edge_score_fallback_replay;
using czr005::ics::run_edge_score_event_fallback_replay;
using czr005::ics::run_edge_score_event_replay;
using czr005::ics::run_edge_score_replay;
using czr005::ics::run_pibt_active_bag_replay;
using czr005::ics::run_rolling_horizon_sipp;
using czr005::ics::run_periodic_replanning_sipp;
using czr005::ics::TaskLeg;
using czr005::ics::TaskStream;

namespace {

Graph make_graph() {
  Graph graph;
  graph.add_node(Node{0, 1, 0.0, 0, 0, {}});
  graph.add_node(Node{1, 4, 1.0, 1, 0, {}});
  graph.add_node(Node{2, 2, 0.0, 2, 0, {}});
  graph.set_heuristic({{0.0, 2.0, 4.0}, {4.0, 0.0, 2.0}, {4.0, 2.0, 0.0}});
  graph.add_edge(Edge{0, 1, 5.0, 2.5});
  graph.add_edge(Edge{1, 2, 5.0, 2.5});
  return graph;
}

Graph make_merge_graph() {
  Graph graph;
  graph.add_node(Node{0, 1, 0.0, 0, 0, {2}});
  graph.add_node(Node{1, 1, 0.0, 0, 1, {2}});
  graph.add_node(Node{2, 4, 1.0, 1, 0, {3}});
  graph.add_node(Node{3, 2, 0.0, 2, 0, {}});
  graph.set_heuristic({{0.0, 4.0, 2.0, 4.0},
                       {4.0, 0.0, 2.0, 4.0},
                       {4.0, 4.0, 0.0, 2.0},
                       {4.0, 4.0, 2.0, 0.0}});
  graph.add_edge(Edge{0, 2, 5.0, 2.5});
  graph.add_edge(Edge{1, 2, 5.0, 2.5});
  graph.add_edge(Edge{2, 3, 5.0, 2.5});
  return graph;
}

Graph make_branch_graph() {
  Graph graph;
  graph.add_node(Node{0, 1, 0.0, 0, 0, {1, 2}});
  graph.add_node(Node{1, 4, 0.0, 1, 0, {3}});
  graph.add_node(Node{2, 4, 0.0, 1, 1, {3}});
  graph.add_node(Node{3, 2, 0.0, 2, 0, {}});
  graph.set_heuristic({{0.0, 2.0, 3.0, 4.0},
                       {4.0, 0.0, 4.0, 2.0},
                       {4.0, 4.0, 0.0, 3.0},
                       {4.0, 2.0, 3.0, 0.0}});
  graph.add_edge(Edge{0, 1, 5.0, 2.5});
  graph.add_edge(Edge{0, 2, 5.0, 2.5});
  graph.add_edge(Edge{1, 3, 5.0, 2.5});
  graph.add_edge(Edge{2, 3, 7.5, 2.5});
  return graph;
}

Graph make_handoff_graph() {
  Graph graph;
  graph.add_node(Node{0, 1, 0.0, 0, 0, {1, 2}});
  graph.add_node(Node{1, 4, 0.0, 1, 0, {0, 3}});
  graph.add_node(Node{2, 4, 0.0, 1, 1, {3}});
  graph.add_node(Node{3, 2, 0.0, 2, 0, {}});
  graph.set_heuristic({{0.0, 2.0, 3.0, 4.0},
                       {2.0, 0.0, 5.0, 2.0},
                       {999.0, 999.0, 0.0, 2.0},
                       {999.0, 999.0, 999.0, 0.0}});
  graph.add_edge(Edge{0, 1, 5.0, 2.5});
  graph.add_edge(Edge{0, 2, 7.5, 2.5});
  graph.add_edge(Edge{1, 0, 5.0, 2.5});
  graph.add_edge(Edge{1, 3, 5.0, 2.5});
  graph.add_edge(Edge{2, 3, 5.0, 2.5});
  return graph;
}

bool near(double left, double right) { return std::fabs(left - right) < 1e-9; }

struct TestContext {
  int failures = 0;

  void check(bool condition, const std::string& message) {
    if (!condition) {
      std::cerr << "FAIL: " << message << '\n';
      ++failures;
    }
  }
};

void print_route(const std::vector<czr005::ics::PathNode>& route) {
  std::cerr << "actual route:";
  for (const auto& node : route) {
    std::cerr << ' ' << node.location;
  }
  std::cerr << '\n';
}

void check_route_locations(TestContext& test,
                           const std::vector<czr005::ics::PathNode>& route,
                           const std::vector<int>& expected,
                           const std::string& label) {
  bool route_ok = true;
  if (route.size() != expected.size()) {
    test.check(false, label + " route size should match Python reference");
    route_ok = false;
  } else {
    for (std::size_t i = 0; i < expected.size(); ++i) {
      if (route[i].location != expected[i]) {
        std::cerr << "FAIL: " << label << " route differs at index " << i << ", expected "
                  << expected[i] << ", got " << route[i].location << '\n';
        ++test.failures;
        route_ok = false;
      }
    }
  }
  if (!route_ok) {
    print_route(route);
  }
}

int map_value_or(const std::map<int, int>& values, int key, int fallback = -1) {
  const auto found = values.find(key);
  return found == values.end() ? fallback : found->second;
}

}  // namespace

int main() {
  TestContext test;
  const Graph graph = make_graph();
  test.check(graph.node_count() == 3, "sample graph node count should be 3");
  test.check(graph.edge_count() == 2, "sample graph edge count should be 2");

  const AStarPlanner planner(graph);
  ReservationTable reservations;
  const auto route = planner.plan(0, 2, 0.0, &reservations, {}, 1);
  test.check(route.size() == 3, "sample route should have 3 nodes");
  if (route.size() == 3) {
    test.check(route[0].location == 0, "sample route starts at 0");
    test.check(route[1].location == 1, "sample route middle is 1");
    test.check(route[2].location == 2, "sample route ends at 2");
    test.check(near(route[1].t1, 2.0), "sample route node 1 t1 is 2.0");
    test.check(near(route[1].t2, 3.0), "sample route node 1 t2 is 3.0");
    test.check(near(route[2].t1, 5.0), "sample route node 2 t1 is 5.0");
  } else {
    print_route(route);
  }

  reservations.add_route(1, route);
  test.check(reservations.conflict_count() == 0, "sample reservation should have no conflicts");

  ReservationTable zero_duration_reservations;
  zero_duration_reservations.reserve(1, 47, 10.0, 10.0);
  zero_duration_reservations.reserve(2, 47, 10.0, 10.0);
  test.check(zero_duration_reservations.conflict_count() == 0,
             "zero-duration node reservations should not count as occupancy conflicts");
  test.check(!zero_duration_reservations.has_conflict(47, 10.0, 10.0, 3),
             "zero-duration node reservations should not block another zero-duration visit");

  const auto blocked = planner.plan(0, 2, 0.0, &reservations, {}, 2);
  test.check(blocked.empty(), "sample conflicting route should be blocked");

  ReservationTable sipp_node_reservations;
  sipp_node_reservations.reserve(99, 1, 2.0, 3.0);
  const SIPPPlanner sipp_planner(graph);
  const auto sipp_wait = sipp_planner.plan(0, 2, 0.0, &sipp_node_reservations, nullptr, 1, 0.0, {}, 2);
  test.check(sipp_wait.size() == 3, "SIPP should wait around a node reservation");
  if (sipp_wait.size() == 3) {
    test.check(near(sipp_wait[1].t1, 3.000000001), "SIPP node wait should start after reserved node interval");
    test.check(near(sipp_wait[2].t1, 6.000000001), "SIPP node wait should preserve downstream timing");
  }

  EdgeReservationTable sipp_edge_reservations;
  sipp_edge_reservations.reserve(99, 0, 1, 0.0, 2.0);
  const auto sipp_edge_wait = sipp_planner.plan(
      0,
      2,
      0.0,
      nullptr,
      &sipp_edge_reservations,
      1,
      0.0,
      {},
      3);
  test.check(sipp_edge_wait.size() == 3, "SIPP should wait around an edge capacity reservation");
  if (sipp_edge_wait.size() == 3) {
    test.check(near(sipp_edge_wait[1].t1, 4.0), "SIPP edge wait should delay target node arrival");
  }

  const auto sipp_fault_blocked = sipp_planner.plan(0, 2, 0.0, nullptr, nullptr, 1, 0.0, {{1, 2}}, 4);
  test.check(sipp_fault_blocked.empty(), "SIPP should reject a faulted only edge");

  TaskStream rolling_tasks;
  rolling_tasks.add(TaskLeg{"loose", 401, 401, 0.1, 100.0, 0, 2, 0, 2, 0.1, "direct", false, 1});
  rolling_tasks.add(TaskLeg{"urgent", 402, 402, 0.0, 20.0, 0, 2, 0, 2, 0.0, "direct", false, 2});
  rolling_tasks.sort_by_pass_time();
  RollingHorizonConfig rolling_config;
  rolling_config.max_tasks = 2;
  rolling_config.horizon_seconds = 60.0;
  const auto rolling_result = run_rolling_horizon_sipp(graph, rolling_tasks, rolling_config);
  test.check(rolling_result.planned_count == 2, "rolling-horizon SIPP should plan two sample tasks");
  test.check(rolling_result.unplanned_count == 0, "rolling-horizon SIPP should not leave sample tasks unplanned");
  test.check(rolling_result.reservation_conflicts == 0, "rolling-horizon SIPP should avoid node conflicts");
  test.check(rolling_result.edge_reservation_conflicts == 0, "rolling-horizon SIPP should avoid edge conflicts");
  test.check(rolling_result.events.size() == 2, "rolling-horizon SIPP should record two events");
  if (rolling_result.events.size() == 2) {
    test.check(rolling_result.events[0].segment_id == "urgent",
               "rolling-horizon SIPP should prioritize tighter deadline slack");
    test.check(rolling_result.events[1].segment_id == "loose",
               "rolling-horizon SIPP should plan the looser task second");
  }

  TaskStream rolling_repair_active_tasks;
  rolling_repair_active_tasks.add(
      TaskLeg{"repair-active", 403, 403, 5.0, 40.0, 0, 2, 0, 2, 5.0, "direct", false, 3});
  rolling_repair_active_tasks.sort_by_pass_time();
  RollingHorizonConfig rolling_repair_config;
  rolling_repair_config.max_tasks = 1;
  rolling_repair_config.horizon_seconds = 60.0;
  const auto rolling_repair_active_result = run_rolling_horizon_sipp(
      graph,
      rolling_repair_active_tasks,
      rolling_repair_config,
      {},
      {RollingHorizonFaultWindow{1, 2, 0.0, 10.0}});
  test.check(rolling_repair_active_result.planned_count == 0,
             "rolling-horizon active repair window should block planning-time faulted edge");
  test.check(rolling_repair_active_result.unplanned_count == 1,
             "rolling-horizon active repair window should mark the sample task unplanned");

  TaskStream rolling_repaired_tasks;
  rolling_repaired_tasks.add(
      TaskLeg{"repair-after", 404, 404, 12.0, 40.0, 0, 2, 0, 2, 12.0, "direct", false, 4});
  rolling_repaired_tasks.sort_by_pass_time();
  const auto rolling_repaired_result = run_rolling_horizon_sipp(
      graph,
      rolling_repaired_tasks,
      rolling_repair_config,
      {},
      {RollingHorizonFaultWindow{1, 2, 0.0, 10.0}});
  test.check(rolling_repaired_result.planned_count == 1,
             "rolling-horizon repaired window should allow planning after repair");
  test.check(rolling_repaired_result.unplanned_count == 0,
             "rolling-horizon repaired window should not leave the sample task unplanned");

  PeriodicReplanningConfig periodic_config;
  periodic_config.max_tasks = 2;
  periodic_config.interval_seconds = 2.0;
  periodic_config.max_ticks = 16;
  const auto periodic_result = run_periodic_replanning_sipp(graph, rolling_tasks, periodic_config);
  test.check(periodic_result.planned_count == 2,
             "periodic replanning SIPP should plan two sample tasks");
  test.check(periodic_result.unplanned_count == 0,
             "periodic replanning SIPP should not leave sample tasks unplanned");
  test.check(periodic_result.replan_count >= 2,
             "periodic replanning SIPP should record active-bag replans");
  test.check(periodic_result.peak_active_bags >= 1,
             "periodic replanning SIPP should report active-bag pressure");
  test.check(periodic_result.post_shield_conflicts == 0,
             "periodic replanning SIPP should stay conflict-free");

  TaskStream periodic_repair_tasks;
  periodic_repair_tasks.add(TaskLeg{"repair-wait", 403, 403, 0.0, 30.0, 0, 2, 0, 2, 0.0, "direct", false, 3});
  periodic_repair_tasks.sort_by_pass_time();
  PeriodicReplanningConfig periodic_repair_config = periodic_config;
  periodic_repair_config.max_tasks = 1;
  const auto periodic_repair_result = run_periodic_replanning_sipp(
      graph,
      periodic_repair_tasks,
      periodic_repair_config,
      {},
      {czr005::ics::PeriodicFaultWindow{0, 1, 0.0, 10.0}});
  test.check(periodic_repair_result.planned_count == 1,
             "periodic replanning repair window should plan the sample task after repair");
  test.check(periodic_repair_result.unplanned_count == 0,
             "periodic replanning repair window should not leave the sample task unplanned");
  test.check(periodic_repair_result.post_shield_conflicts == 0,
             "periodic replanning repair window should stay conflict-free");

  const Graph pibt_merge_graph = make_merge_graph();
  const PIBTStyleOneStepResolver pibt_merge_resolver(pibt_merge_graph);
  const auto pibt_merge_actions = pibt_merge_resolver.resolve({
      PIBTAgentState{1, 0, 3, 0.0, 100.0, 0.0},
      PIBTAgentState{2, 1, 3, 0.0, 20.0, 0.0},
  });
  test.check(pibt_merge_actions.size() == 2, "PIBT resolver should produce two merge actions");
  if (pibt_merge_actions.size() == 2) {
    test.check(pibt_merge_actions[0].task_id == 2, "PIBT resolver should prioritize tighter slack");
    test.check(pibt_merge_actions[0].action == "move", "PIBT resolver first merge action should move");
    test.check(pibt_merge_actions[0].next_node == 2, "PIBT resolver first merge action should target node 2");
    test.check(pibt_merge_actions[1].task_id == 1, "PIBT resolver should process loose task second");
    test.check(pibt_merge_actions[1].action == "hold", "PIBT resolver loose merge action should hold");
    test.check(pibt_merge_actions[1].reason == "no_safe_edge",
               "PIBT resolver loose merge action should explain blocked edge");
  }

  const Graph pibt_branch_graph = make_branch_graph();
  const PIBTStyleOneStepResolver pibt_branch_resolver(pibt_branch_graph);
  const auto pibt_branch_actions = pibt_branch_resolver.resolve(
      {PIBTAgentState{3, 0, 3, 0.0, 20.0, 0.0}},
      nullptr,
      {{0, 1}});
  test.check(pibt_branch_actions.size() == 1, "PIBT resolver should produce one branch action");
  if (pibt_branch_actions.size() == 1) {
    test.check(pibt_branch_actions[0].action == "move",
               "PIBT resolver should move on the safe branch edge");
    test.check(pibt_branch_actions[0].next_node == 2,
               "PIBT resolver should choose the non-faulted branch");
  }

  const Graph pibt_handoff_graph = make_handoff_graph();
  const PIBTStyleOneStepResolver pibt_handoff_resolver(pibt_handoff_graph);
  const auto pibt_handoff_actions = pibt_handoff_resolver.resolve({
      PIBTAgentState{1, 0, 3, 0.0, 10.0, 0.0},
      PIBTAgentState{2, 1, 3, 0.0, 100.0, 0.0},
  });
  test.check(pibt_handoff_actions.size() == 2,
             "PIBT resolver should produce two handoff actions");
  if (pibt_handoff_actions.size() == 2) {
    test.check(pibt_handoff_actions[0].task_id == 1,
               "PIBT handoff should keep high-priority task first");
    test.check(pibt_handoff_actions[0].next_node == 1,
               "PIBT handoff should move high-priority task into the vacated node");
    test.check(pibt_handoff_actions[0].reason == "priority_inheritance",
               "PIBT handoff should label the inherited move");
    test.check(pibt_handoff_actions[1].task_id == 2,
               "PIBT handoff should return the inherited blocker second");
    test.check(pibt_handoff_actions[1].next_node == 3,
               "PIBT handoff should move the blocker toward its goal");
    test.check(pibt_handoff_actions[1].reason == "inherited_move",
               "PIBT handoff should label the blocker move");
  }

  const auto pibt_handoff_blocked_actions = pibt_handoff_resolver.resolve({
      PIBTAgentState{1, 0, 3, 0.0, 10.0, 0.0},
      PIBTAgentState{2, 1, 0, 0.0, 100.0, 0.0},
  });
  test.check(pibt_handoff_blocked_actions.size() == 2,
             "PIBT blocked handoff should still produce two actions");
  if (pibt_handoff_blocked_actions.size() == 2) {
    test.check(pibt_handoff_blocked_actions[0].next_node == 2,
               "PIBT blocked handoff should use the high-priority alternative");
    test.check(pibt_handoff_blocked_actions[0].reason == "best_safe_edge",
               "PIBT blocked handoff should label the alternative normally");
    test.check(pibt_handoff_blocked_actions[1].next_node == 0,
               "PIBT blocked handoff should let the blocker move after the high-priority task reroutes");
  }

  TaskStream pibt_replay_tasks;
  pibt_replay_tasks.add(TaskLeg{"handoff-high", 501, 501, 0.0, 20.0, 0, 3, 0, 3, 0.0, "direct", false, 1});
  pibt_replay_tasks.add(TaskLeg{"handoff-blocker", 502, 502, 0.0, 100.0, 1, 3, 1, 3, 0.0, "direct", false, 2});
  pibt_replay_tasks.sort_by_pass_time();
  PIBTActiveBagReplayConfig pibt_replay_config;
  pibt_replay_config.max_tasks = 2;
  pibt_replay_config.interval_seconds = 2.0;
  pibt_replay_config.hold_seconds = 2.0;
  pibt_replay_config.max_ticks = 16;
  const auto pibt_replay_result =
      run_pibt_active_bag_replay(pibt_handoff_graph, pibt_replay_tasks, pibt_replay_config);
  test.check(pibt_replay_result.planned_count == 2,
             "PIBT active-bag replay should plan both handoff tasks");
  test.check(pibt_replay_result.post_shield_conflicts == 0,
             "PIBT active-bag replay should stay conflict-free");
  test.check(pibt_replay_result.decision_count >= 2,
             "PIBT active-bag replay should record active decisions");
  test.check(pibt_replay_result.events.size() >= 4,
             "PIBT active-bag replay should emit replay events");

  const auto later = planner.plan(0, 2, 6.0, &reservations, {}, 3);
  test.check(later.size() == 3, "sample later route should have 3 nodes");
  reservations.add_route(3, later);
  test.check(reservations.conflict_count() == 0, "sample later reservation should have no conflicts");

  const std::set<std::pair<int, int>> fault_edges{{1, 2}};
  const auto fault_blocked = planner.plan(0, 2, 10.0, &reservations, fault_edges, 4);
  test.check(fault_blocked.empty(), "sample faulted edge should block the route");

  JunctionShieldConfig shield_config;
  shield_config.edge_capacity = 1;
  shield_config.edge_headway_seconds = 2.0;
  const JunctionShield shield(graph, shield_config);
  const ReservationTable empty_node_reservations;
  const EdgeReservationTable empty_edge_reservations;
  auto decision = shield.validate_edge_action(10,
                                              0,
                                              1,
                                              2,
                                              0.0,
                                              empty_node_reservations,
                                              empty_edge_reservations);
  test.check(decision.allowed(), "shield should allow a safe sample edge action");
  test.check(near(decision.edge_start, 0.0), "shield allowed edge start should be 0.0");
  test.check(near(decision.edge_end, 2.0), "shield allowed edge end should be 2.0");

  decision = shield.validate_edge_action(10,
                                         1,
                                         0,
                                         2,
                                         0.0,
                                         empty_node_reservations,
                                         empty_edge_reservations);
  test.check(decision.status == SafetyStatus::kMissingEdge, "shield should reject missing edges");

  decision = shield.validate_edge_action(10,
                                         0,
                                         1,
                                         2,
                                         0.0,
                                         empty_node_reservations,
                                         empty_edge_reservations,
                                         {{0, 1}});
  test.check(decision.status == SafetyStatus::kFaultedEdge, "shield should reject faulted edges");

  ReservationTable node_conflicts;
  node_conflicts.reserve(99, 1, 2.0, 3.0);
  decision = shield.validate_edge_action(10,
                                         0,
                                         1,
                                         2,
                                         0.0,
                                         node_conflicts,
                                         empty_edge_reservations);
  test.check(decision.status == SafetyStatus::kNodeReservationConflict,
             "shield should reject node reservation conflicts");

  JunctionShieldConfig buffer_shield_config = shield_config;
  buffer_shield_config.node_capacities[1] = 2;
  const JunctionShield buffer_shield(graph, buffer_shield_config);
  decision = buffer_shield.validate_edge_action(10,
                                                0,
                                                1,
                                                2,
                                                0.0,
                                                node_conflicts,
                                                empty_edge_reservations);
  test.check(decision.allowed(),
             "shield should allow a target node overlap below explicit buffer capacity");
  node_conflicts.reserve(98, 1, 2.0, 3.0);
  decision = buffer_shield.validate_edge_action(10,
                                                0,
                                                1,
                                                2,
                                                0.0,
                                                node_conflicts,
                                                empty_edge_reservations);
  test.check(decision.status == SafetyStatus::kNodeReservationConflict,
             "shield should reject target node overlap once buffer capacity is full");

  EdgeReservationTable edge_capacity_conflicts;
  edge_capacity_conflicts.reserve(99, 0, 1, 0.0, 2.0);
  decision = shield.validate_edge_action(10,
                                         0,
                                         1,
                                         2,
                                         0.0,
                                         empty_node_reservations,
                                         edge_capacity_conflicts);
  test.check(decision.status == SafetyStatus::kEdgeCapacityConflict,
             "shield should reject edge capacity conflicts");
  edge_capacity_conflicts.remove_task(99);
  decision = shield.validate_edge_action(10,
                                         0,
                                         1,
                                         2,
                                         0.0,
                                         empty_node_reservations,
                                         edge_capacity_conflicts);
  test.check(decision.allowed(), "edge reservation remove_task should clear capacity conflicts");

  EdgeReservationTable edge_headway_conflicts;
  edge_headway_conflicts.reserve(99, 0, 1, 0.0, 0.5);
  decision = shield.validate_edge_action(10,
                                         0,
                                         1,
                                         2,
                                         1.0,
                                         empty_node_reservations,
                                         edge_headway_conflicts);
  test.check(decision.status == SafetyStatus::kEdgeHeadwayConflict,
             "shield should reject edge headway conflicts");

  EdgeReservationTable merge_group_conflicts;
  merge_group_conflicts.reserve(99, 1, 2, 0.0, 2.0);
  JunctionShieldConfig merge_shield_config = shield_config;
  merge_shield_config.merge_groups.push_back(czr005::ics::MergeGroupEdge{0, 1, 7});
  merge_shield_config.merge_groups.push_back(czr005::ics::MergeGroupEdge{1, 2, 7});
  const JunctionShield merge_shield(graph, merge_shield_config);
  decision = merge_shield.validate_edge_action(10,
                                               0,
                                               1,
                                               2,
                                               0.0,
                                               empty_node_reservations,
                                               merge_group_conflicts);
  test.check(decision.status == SafetyStatus::kMergeGroupConflict,
             "shield should reject shared merge-group conflicts across different edges");
  JunctionShieldConfig independent_merge_config = shield_config;
  independent_merge_config.merge_groups.push_back(czr005::ics::MergeGroupEdge{0, 1, 7});
  const JunctionShield independent_merge_shield(graph, independent_merge_config);
  decision = independent_merge_shield.validate_edge_action(10,
                                                           0,
                                                           1,
                                                           2,
                                                           0.0,
                                                           empty_node_reservations,
                                                           merge_group_conflicts);
  test.check(decision.allowed(),
             "shield should ignore reservations outside the candidate merge group");

  decision = shield.validate_edge_action(10,
                                         0,
                                         1,
                                         2,
                                         8.0,
                                         empty_node_reservations,
                                         empty_edge_reservations,
                                         {{1, 2}});
  test.check(decision.status == SafetyStatus::kUnreachableGoal,
             "shield should reject actions that make the goal unreachable");

  const auto metrics = compute_episode_metrics(std::vector<std::vector<czr005::ics::PathNode>>{route, later},
                                               1,
                                               reservations);
  test.check(metrics.planned_count == 2, "metrics planned count should be 2");
  test.check(metrics.unplanned_count == 1, "metrics unplanned count should be 1");
  test.check(metrics.reservation_conflicts == 0, "metrics reservation conflicts should be 0");
  test.check(metrics.makespan > 0.0, "metrics makespan should be positive");

  const EdgeScoreModel edge_score_model(
      {{0.1, -0.2}, {0.3, 0.4}, {-0.5, 0.25}},
      {0.01, -0.02},
      {0.7, -0.6},
      0.05);
  const std::vector<std::vector<double>> edge_features{{1.0, 0.5, -0.25}, {0.0, 1.0, 0.5}};
  const auto edge_scores = edge_score_model.scores(edge_features);
  test.check(edge_scores.size() == 2, "edge score model should return two scores");
  test.check(near(edge_scores[0],
                  std::tanh(0.1 + 0.15 + 0.125 + 0.01) * 0.7 +
                      std::tanh(-0.2 + 0.2 - 0.0625 - 0.02) * -0.6 + 0.05),
             "edge score first row should match manual tanh MLP");
  test.check(edge_score_model.predict(edge_features, {false, true}) == 1,
             "edge score masked prediction should choose the only safe action");

  std::vector<std::vector<double>> replay_w1(13, std::vector<double>{0.0});
  replay_w1[0][0] = 2.0;
  replay_w1[1][0] = -2.0;
  replay_w1[5][0] = -0.5;
  replay_w1[6][0] = 1.0;
  const EdgeScoreModel replay_model(replay_w1, {0.0}, {1.0}, 0.0);
  TaskStream replay_tasks;
  replay_tasks.add(TaskLeg{"cpp-replay-1", 101, 101, 0.0, 20.0, 0, 2, 0, 2, 0.0, "direct", false, 1});
  replay_tasks.add(TaskLeg{"cpp-replay-2", 102, 102, 0.5, 20.5, 0, 2, 0, 2, 0.5, "direct", false, 2});
  EdgeScoreReplayConfig replay_config;
  replay_config.max_tasks = 2;
  replay_config.max_decisions_per_task = 16;
  replay_config.edge_capacity = 1;
  replay_config.edge_headway_seconds = 0.0;
  const auto replay_result = run_edge_score_replay(graph, replay_tasks, replay_model, replay_config);
  test.check(replay_result.planned_count == 2, "native edge-score replay should plan both sample tasks");
  test.check(replay_result.unplanned_count == 0, "native edge-score replay should not leave sample tasks unplanned");
  test.check(replay_result.decision_count >= 4, "native edge-score replay should execute sample decisions");
  test.check(replay_result.post_shield_conflicts == 0, "native edge-score replay should stay conflict-free");
  const auto fallback_replay_result = run_edge_score_fallback_replay(graph, replay_tasks, replay_config);
  test.check(fallback_replay_result.planned_count == 2,
             "native fallback replay should plan both sample tasks without a model");
  test.check(fallback_replay_result.post_shield_conflicts == 0,
             "native fallback replay should stay conflict-free without a model");
  const auto event_replay_result = run_edge_score_event_replay(graph, replay_tasks, replay_model, replay_config);
  test.check(event_replay_result.planned_count == 2,
             "native event replay should plan both sample tasks");
  test.check(event_replay_result.unplanned_count == 0,
             "native event replay should not leave sample tasks unplanned");
  test.check(event_replay_result.post_shield_conflicts == 0,
             "native event replay should stay conflict-free");
  const auto event_fallback_replay_result = run_edge_score_event_fallback_replay(graph, replay_tasks, replay_config);
  test.check(event_fallback_replay_result.planned_count == 2,
             "native event fallback replay should plan both sample tasks without a model");
  test.check(event_fallback_replay_result.post_shield_conflicts == 0,
             "native event fallback replay should stay conflict-free without a model");

  TaskStream repair_tasks;
  repair_tasks.add(TaskLeg{"cpp-repair-active", 201, 201, 0.0, 20.0, 0, 2, 0, 2, 0.0, "direct", false, 1});
  repair_tasks.add(TaskLeg{"cpp-repair-after", 202, 202, 12.0, 32.0, 0, 2, 0, 2, 12.0, "direct", false, 2});
  EdgeScoreReplayConfig repair_config;
  repair_config.max_tasks = 2;
  repair_config.max_decisions_per_task = 4;
  const std::set<std::pair<int, int>> no_static_faults;
  const std::vector<EdgeFaultWindow> repair_windows{{0, 1, 0.0, 10.0}};
  const auto repair_replay_result = run_edge_score_fallback_replay(
      graph,
      repair_tasks,
      repair_config,
      no_static_faults,
      repair_windows);
  test.check(repair_replay_result.planned_count == 1,
             "repair-window fallback replay should plan the post-repair task");
  test.check(repair_replay_result.unplanned_count == 1,
             "repair-window fallback replay should fail the task trapped during active fault");
  test.check(repair_replay_result.post_shield_conflicts == 0,
             "repair-window fallback replay should stay conflict-free");

  const auto legacy = read_legacy_map2(std::string(CZR005_SOURCE_DIR) +
                                       "/legacy/jichang_origin_readonly/map2.txt");
  test.check(legacy.declared_node_count == 54, "legacy map declared node count should be 54");
  test.check(legacy.graph.node_count() == 54, "legacy map graph node count should be 54");
  test.check(legacy.heuristic_rows == 54, "legacy map heuristic row count should be 54");
  test.check(legacy.edge_rows == 69, "legacy map edge row count should be 69");
  test.check(legacy.graph.edge_count() == 69, "legacy map graph edge count should be 69");
  test.check(legacy.graph.node_type_count(1) == 8, "legacy map type-1 node count should be 8");
  test.check(legacy.graph.node_type_count(2) == 5, "legacy map type-2 node count should be 5");

  const AStarPlanner legacy_planner(legacy.graph);
  check_route_locations(test,
                        legacy_planner.plan(0, 47),
                        {0, 6, 12, 13, 23, 24, 27, 28, 47},
                        "legacy 0->47");
  check_route_locations(test,
                        legacy_planner.plan(52, 49),
                        {52, 29, 30, 31, 32, 37, 49},
                        "legacy 52->49");
  check_route_locations(test,
                        legacy_planner.plan(53, 50),
                        {53, 20, 10, 15, 14, 46, 36, 44, 50},
                        "legacy 53->50");

  const auto structural_route = legacy_planner.plan(3, 49);
  test.check(!structural_route.empty(), "legacy 3->49 structural route should not be empty");
  if (!structural_route.empty()) {
    test.check(structural_route.front().location == 3, "legacy 3->49 structural route should start at 3");
    test.check(structural_route.back().location == 49, "legacy 3->49 structural route should end at 49");
  }

  const auto legacy_tasks = read_legacy_inputdata(std::string(CZR005_SOURCE_DIR) +
                                                  "/legacy/jichang_origin_readonly/inputdata.txt");
  test.check(legacy_tasks.header == "ID EntryTime(s) STD(s) star end Unloader Loader",
             "legacy inputdata header should match Java file");
  test.check(legacy_tasks.raw_task_count == 28506, "legacy raw task count should be 28506");
  test.check(legacy_tasks.direct_raw_task_count == 13409, "legacy direct raw task count should be 13409");
  test.check(legacy_tasks.early_split_raw_task_count == 15097,
             "legacy early split raw task count should be 15097");
  test.check(legacy_tasks.stream.size() == 43603, "legacy expanded task count should be 43603");
  test.check(map_value_or(legacy_tasks.expanded_by_start, 0) == 3200,
             "legacy expanded start 0 count should be 3200");
  test.check(map_value_or(legacy_tasks.expanded_by_start, 1) == 3193,
             "legacy expanded start 1 count should be 3193");
  test.check(map_value_or(legacy_tasks.expanded_by_start, 2) == 3199,
             "legacy expanded start 2 count should be 3199");
  test.check(map_value_or(legacy_tasks.expanded_by_start, 3) == 4887,
             "legacy expanded start 3 count should be 4887");
  test.check(map_value_or(legacy_tasks.expanded_by_start, 4) == 4887,
             "legacy expanded start 4 count should be 4887");
  test.check(map_value_or(legacy_tasks.expanded_by_start, 5) == 4886,
             "legacy expanded start 5 count should be 4886");
  test.check(map_value_or(legacy_tasks.expanded_by_start, 52) == 15097,
             "legacy expanded start 52 count should be 15097");
  test.check(map_value_or(legacy_tasks.expanded_by_start, 53) == 4254,
             "legacy expanded start 53 count should be 4254");

  const auto& task_list = legacy_tasks.stream.tasks();
  test.check(!task_list.empty(), "legacy task stream should not be empty");
  if (!task_list.empty()) {
    const auto& first = task_list.front();
    test.check(first.segment_id == "0:storage_in", "legacy first sorted segment id should match Python");
    test.check(near(first.pass_time, 8267.845453), "legacy first sorted pass time should match Python");
    test.check(first.start == 3, "legacy first sorted start should match Python");
    test.check(first.goal == 47, "legacy first sorted goal should match Python");
    test.check(first.leg == "storage_in", "legacy first sorted leg should match Python");
    test.check(first.early_bag_split, "legacy first sorted task should be marked early split");
    test.check(first.source_line == 2, "legacy first sorted source line should match Python");
  }

  return test.failures == 0 ? 0 : 1;
}
