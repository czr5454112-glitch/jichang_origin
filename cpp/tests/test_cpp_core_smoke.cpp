#include <cassert>
#include <cmath>
#include <set>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/metrics/metrics.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar.hpp"

using czr005::ics::AStarPlanner;
using czr005::ics::Edge;
using czr005::ics::Graph;
using czr005::ics::Node;
using czr005::ics::ReservationTable;
using czr005::ics::compute_episode_metrics;

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

}  // namespace

int main() {
  const Graph graph = make_graph();
  assert(graph.node_count() == 3);
  assert(graph.edge_count() == 2);

  const AStarPlanner planner(graph);
  ReservationTable reservations;
  const auto route = planner.plan(0, 2, 0.0, &reservations, {}, 1);
  assert(route.size() == 3);
  assert(route[0].location == 0);
  assert(route[1].location == 1);
  assert(route[2].location == 2);
  assert(near(route[1].t1, 2.0));
  assert(near(route[1].t2, 3.0));
  assert(near(route[2].t1, 5.0));

  reservations.add_route(1, route);
  assert(reservations.conflict_count() == 0);

  const auto blocked = planner.plan(0, 2, 0.0, &reservations, {}, 2);
  assert(blocked.empty());

  const auto later = planner.plan(0, 2, 6.0, &reservations, {}, 3);
  assert(later.size() == 3);
  reservations.add_route(3, later);
  assert(reservations.conflict_count() == 0);

  const std::set<std::pair<int, int>> fault_edges{{1, 2}};
  const auto fault_blocked = planner.plan(0, 2, 10.0, &reservations, fault_edges, 4);
  assert(fault_blocked.empty());

  const auto metrics = compute_episode_metrics(std::vector<std::vector<czr005::ics::PathNode>>{route, later},
                                               1,
                                               reservations);
  assert(metrics.planned_count == 2);
  assert(metrics.unplanned_count == 1);
  assert(metrics.reservation_conflicts == 0);
  assert(metrics.makespan > 0.0);

  return 0;
}

