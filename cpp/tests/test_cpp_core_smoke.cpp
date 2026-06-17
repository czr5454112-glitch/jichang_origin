#include <cmath>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/io/legacy_map_reader.hpp"
#include "ics_core/io/legacy_task_reader.hpp"
#include "ics_core/metrics/metrics.hpp"
#include "ics_core/models/edge_score.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar.hpp"
#include "ics_core/runtime/edge_score_replay.hpp"
#include "ics_core/shield/junction_shield.hpp"

using czr005::ics::AStarPlanner;
using czr005::ics::Edge;
using czr005::ics::EdgeScoreModel;
using czr005::ics::EdgeScoreReplayConfig;
using czr005::ics::EdgeReservationTable;
using czr005::ics::Graph;
using czr005::ics::JunctionShield;
using czr005::ics::JunctionShieldConfig;
using czr005::ics::Node;
using czr005::ics::ReservationTable;
using czr005::ics::SafetyStatus;
using czr005::ics::compute_episode_metrics;
using czr005::ics::read_legacy_inputdata;
using czr005::ics::read_legacy_map2;
using czr005::ics::run_edge_score_replay;
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

  const auto blocked = planner.plan(0, 2, 0.0, &reservations, {}, 2);
  test.check(blocked.empty(), "sample conflicting route should be blocked");

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
