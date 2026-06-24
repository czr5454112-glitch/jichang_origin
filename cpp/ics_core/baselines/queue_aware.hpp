#pragma once

#include <algorithm>
#include <limits>
#include <set>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar_types.hpp"
#include "ics_core/routing/sipp.hpp"
#include "ics_core/shield/junction_shield.hpp"

namespace czr005::ics {

struct QueueAwarePath {
  std::vector<PathNode> route;
  double score = std::numeric_limits<double>::infinity();
  double finish_time = std::numeric_limits<double>::infinity();
  double queue_penalty = 0.0;
};

class QueueAwareShortestPath {
 public:
  QueueAwareShortestPath(const Graph& graph,
                         double queue_weight = 1.0,
                         double edge_queue_weight = 1.0,
                         double lookahead_seconds = 300.0)
      : graph_(graph),
        planner_(graph),
        queue_weight_(queue_weight),
        edge_queue_weight_(edge_queue_weight),
        lookahead_seconds_(lookahead_seconds) {
    if (queue_weight < 0.0) {
      throw std::invalid_argument("queue_weight must be non-negative");
    }
    if (edge_queue_weight < 0.0) {
      throw std::invalid_argument("edge_queue_weight must be non-negative");
    }
    if (lookahead_seconds <= 0.0) {
      throw std::invalid_argument("lookahead_seconds must be positive");
    }
  }

  [[nodiscard]] std::vector<PathNode> plan(
      int start,
      int goal,
      double start_time = 0.0,
      const ReservationTable* reservations = nullptr,
      const EdgeReservationTable* edge_reservations = nullptr,
      int edge_capacity = 1,
      double edge_headway_seconds = 0.0,
      const std::set<std::pair<int, int>>& fault_edges = {},
      int task_id = -1,
      const std::unordered_map<int, int>& node_capacities = {},
      const std::vector<MergeGroupEdge>& merge_groups = {},
      int merge_capacity = 1,
      double merge_headway_seconds = 0.0) const {
    const auto ranked = ranked_routes(start,
                                      goal,
                                      start_time,
                                      reservations,
                                      edge_reservations,
                                      edge_capacity,
                                      edge_headway_seconds,
                                      fault_edges,
                                      task_id,
                                      node_capacities,
                                      merge_groups,
                                      merge_capacity,
                                      merge_headway_seconds);
    return ranked.empty() ? std::vector<PathNode>{} : ranked.front().route;
  }

  [[nodiscard]] std::vector<QueueAwarePath> ranked_routes(
      int start,
      int goal,
      double start_time = 0.0,
      const ReservationTable* reservations = nullptr,
      const EdgeReservationTable* edge_reservations = nullptr,
      int edge_capacity = 1,
      double edge_headway_seconds = 0.0,
      const std::set<std::pair<int, int>>& fault_edges = {},
      int task_id = -1,
      const std::unordered_map<int, int>& node_capacities = {},
      const std::vector<MergeGroupEdge>& merge_groups = {},
      int merge_capacity = 1,
      double merge_headway_seconds = 0.0) const {
    const ReservationTable empty_reservations;
    const EdgeReservationTable empty_edge_reservations;
    const auto& node_table = reservations == nullptr ? empty_reservations : *reservations;
    const auto& edge_table =
        edge_reservations == nullptr ? empty_edge_reservations : *edge_reservations;

    if (start == goal) {
      auto route = planner_.plan(start,
                                 goal,
                                 start_time,
                                 &node_table,
                                 &edge_table,
                                 edge_capacity,
                                 edge_headway_seconds,
                                 fault_edges,
                                 task_id,
                                 node_capacities,
                                 merge_groups,
                                 merge_capacity,
                                 merge_headway_seconds);
      if (route.empty()) {
        return {};
      }
      const double finish_time = route.back().t2;
      return {QueueAwarePath{std::move(route), finish_time, finish_time, 0.0}};
    }

    std::vector<QueueAwarePath> ranked;
    const auto& outgoing = graph_.outgoing(start);
    for (const int first_hop : outgoing) {
      if (fault_edges.find({start, first_hop}) != fault_edges.end()) {
        continue;
      }
      auto forced_faults = fault_edges;
      for (const int other : outgoing) {
        if (other != first_hop) {
          forced_faults.insert({start, other});
        }
      }

      auto route = planner_.plan(start,
                                 goal,
                                 start_time,
                                 &node_table,
                                 &edge_table,
                                 edge_capacity,
                                 edge_headway_seconds,
                                 forced_faults,
                                 task_id,
                                 node_capacities,
                                 merge_groups,
                                 merge_capacity,
                                 merge_headway_seconds);
      if (route.size() < 2 || route[1].location != first_hop) {
        continue;
      }

      const double queue_penalty =
          route_queue_penalty(route, node_table, edge_table, node_capacities, merge_groups, task_id);
      const double finish_time = route.back().t2;
      ranked.push_back(QueueAwarePath{
          route,
          finish_time + queue_penalty,
          finish_time,
          queue_penalty,
      });
    }

    std::sort(ranked.begin(),
              ranked.end(),
              [](const QueueAwarePath& left, const QueueAwarePath& right) {
                if (left.score != right.score) {
                  return left.score < right.score;
                }
                if (left.finish_time != right.finish_time) {
                  return left.finish_time < right.finish_time;
                }
                return route_locations(left.route) < route_locations(right.route);
              });
    return ranked;
  }

 private:
  [[nodiscard]] double route_queue_penalty(
      const std::vector<PathNode>& route,
      const ReservationTable& reservations,
      const EdgeReservationTable& edge_reservations,
      const std::unordered_map<int, int>& node_capacities,
      const std::vector<MergeGroupEdge>& merge_groups,
      int task_id) const {
    double node_penalty = 0.0;
    for (std::size_t index = 1; index < route.size(); ++index) {
      const int node = route[index].location;
      node_penalty += node_queue_pressure(
          node, route[index].t1, reservations, node_capacity(node_capacities, node), task_id);
    }

    double edge_penalty = 0.0;
    for (std::size_t index = 1; index < route.size(); ++index) {
      const auto& left = route[index - 1];
      const auto& right = route[index];
      if (left.location == right.location) {
        continue;
      }
      const auto& edge = graph_.edge(left.location, right.location);
      edge_penalty += edge_queue_pressure(left.location,
                                          right.location,
                                          right.t1 - edge.travel_time(),
                                          edge_reservations,
                                          merge_groups,
                                          task_id);
    }
    return queue_weight_ * node_penalty + edge_queue_weight_ * edge_penalty;
  }

  [[nodiscard]] double node_queue_pressure(const int node,
                                           const double start,
                                           const ReservationTable& reservations,
                                           const int capacity,
                                           const int task_id) const {
    if (capacity <= 0) {
      return std::numeric_limits<double>::infinity();
    }
    const double window_end = start + lookahead_seconds_;
    double pressure = 0.0;
    for (const auto& interval : reservations.intervals(node)) {
      if (task_id >= 0 && interval.task_id == task_id) {
        continue;
      }
      if (interval.end <= start + kEpsilon || interval.start >= window_end - kEpsilon) {
        continue;
      }
      pressure += time_decay(std::max(interval.start, start), start) / capacity;
    }
    return pressure;
  }

  [[nodiscard]] double edge_queue_pressure(
      const int start_node,
      const int end_node,
      const double start,
      const EdgeReservationTable& edge_reservations,
      const std::vector<MergeGroupEdge>& merge_groups,
      const int task_id) const {
    const double window_end = start + lookahead_seconds_;
    double pressure = 0.0;
    for (const auto& interval : edge_reservations.intervals(start_node, end_node)) {
      if (task_id >= 0 && interval.task_id == task_id) {
        continue;
      }
      if (interval.end <= start + kEpsilon || interval.start >= window_end - kEpsilon) {
        continue;
      }
      pressure += time_decay(std::max(interval.start, start), start);
    }

    const int group = merge_group(start_node, end_node, merge_groups);
    if (group < 0) {
      return pressure;
    }
    for (const auto& interval : edge_reservations.all_intervals()) {
      if (interval.start_node == start_node && interval.end_node == end_node) {
        continue;
      }
      if (task_id >= 0 && interval.task_id == task_id) {
        continue;
      }
      if (merge_group(interval.start_node, interval.end_node, merge_groups) != group) {
        continue;
      }
      if (interval.end <= start + kEpsilon || interval.start >= window_end - kEpsilon) {
        continue;
      }
      pressure += time_decay(std::max(interval.start, start), start);
    }
    return pressure;
  }

  [[nodiscard]] double time_decay(const double interval_start, const double reference) const {
    const double distance = std::max(0.0, interval_start - reference);
    return std::max(0.0, 1.0 - distance / lookahead_seconds_);
  }

  [[nodiscard]] static int node_capacity(
      const std::unordered_map<int, int>& node_capacities,
      int node) {
    const auto found = node_capacities.find(node);
    return found == node_capacities.end() ? 1 : found->second;
  }

  [[nodiscard]] static int merge_group(
      const int start_node,
      const int end_node,
      const std::vector<MergeGroupEdge>& merge_groups) {
    for (const auto& edge : merge_groups) {
      if (edge.start_node == start_node && edge.end_node == end_node) {
        return edge.group;
      }
    }
    return -1;
  }

  [[nodiscard]] static std::vector<int> route_locations(const std::vector<PathNode>& route) {
    std::vector<int> locations;
    locations.reserve(route.size());
    for (const auto& node : route) {
      locations.push_back(node.location);
    }
    return locations;
  }

  inline static constexpr double kEpsilon = 1.0e-9;

  const Graph& graph_;
  SIPPPlanner planner_;
  double queue_weight_ = 1.0;
  double edge_queue_weight_ = 1.0;
  double lookahead_seconds_ = 300.0;
};

}  // namespace czr005::ics
