#include <cmath>
#include <iostream>
#include <set>
#include <string>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/io/legacy_map_reader.hpp"
#include "ics_core/metrics/metrics.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar.hpp"

using czr005::ics::AStarPlanner;
using czr005::ics::Edge;
using czr005::ics::Graph;
using czr005::ics::Node;
using czr005::ics::ReservationTable;
using czr005::ics::compute_episode_metrics;
using czr005::ics::read_legacy_map2;

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

  void check(bool condition, const char* message) {
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

  const auto metrics = compute_episode_metrics(std::vector<std::vector<czr005::ics::PathNode>>{route, later},
                                               1,
                                               reservations);
  test.check(metrics.planned_count == 2, "metrics planned count should be 2");
  test.check(metrics.unplanned_count == 1, "metrics unplanned count should be 1");
  test.check(metrics.reservation_conflicts == 0, "metrics reservation conflicts should be 0");
  test.check(metrics.makespan > 0.0, "metrics makespan should be positive");

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
  const auto legacy_route = legacy_planner.plan(0, 47);
  const std::vector<int> expected_path{0, 6, 12, 13, 23, 24, 27, 28, 47};
  test.check(legacy_route.size() == expected_path.size(), "legacy 0->47 route size should match Python reference");
  if (legacy_route.size() == expected_path.size()) {
    for (std::size_t i = 0; i < expected_path.size(); ++i) {
      if (legacy_route[i].location != expected_path[i]) {
        std::cerr << "FAIL: legacy 0->47 route differs at index " << i << ", expected "
                  << expected_path[i] << ", got " << legacy_route[i].location << '\n';
        ++test.failures;
      }
    }
  }
  if (legacy_route.size() != expected_path.size() || test.failures > 0) {
    print_route(legacy_route);
  }

  return test.failures == 0 ? 0 : 1;
}
