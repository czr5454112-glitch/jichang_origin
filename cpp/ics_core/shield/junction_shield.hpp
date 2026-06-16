#pragma once

#include <algorithm>
#include <set>
#include <unordered_map>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar.hpp"

namespace czr005::ics {

enum class SafetyStatus {
  kAllowed,
  kMissingEdge,
  kFaultedEdge,
  kNodeReservationConflict,
  kEdgeCapacityConflict,
  kEdgeHeadwayConflict,
  kUnreachableGoal,
};

struct ShieldDecision {
  SafetyStatus status = SafetyStatus::kAllowed;
  double edge_start = 0.0;
  double edge_end = 0.0;
  double node_start = 0.0;
  double node_end = 0.0;

  [[nodiscard]] bool allowed() const { return status == SafetyStatus::kAllowed; }
};

struct EdgeReservation {
  int task_id = -1;
  int start_node = -1;
  int end_node = -1;
  double start = 0.0;
  double end = 0.0;

  [[nodiscard]] bool overlaps(double candidate_start, double candidate_end) const {
    return !(candidate_start >= end || candidate_end <= start);
  }
};

class EdgeReservationTable {
 public:
  void reserve(int task_id, int start_node, int end_node, double start, double end) {
    auto& intervals = by_edge_[edge_key(start_node, end_node)];
    intervals.erase(std::remove_if(intervals.begin(), intervals.end(),
                                   [task_id](const EdgeReservation& item) {
                                     return item.task_id == task_id;
                                   }),
                    intervals.end());
    intervals.push_back(EdgeReservation{task_id, start_node, end_node, start, end});
    std::sort(intervals.begin(), intervals.end(),
              [](const EdgeReservation& left, const EdgeReservation& right) {
                if (left.start != right.start) {
                  return left.start < right.start;
                }
                if (left.end != right.end) {
                  return left.end < right.end;
                }
                return left.task_id < right.task_id;
              });
  }

  [[nodiscard]] bool has_capacity_conflict(int start_node,
                                           int end_node,
                                           double start,
                                           double end,
                                           int capacity,
                                           int task_id = -1) const {
    if (capacity <= 0) {
      return true;
    }
    const auto found = by_edge_.find(edge_key(start_node, end_node));
    if (found == by_edge_.end()) {
      return false;
    }
    int overlapping = 0;
    for (const auto& interval : found->second) {
      if (task_id >= 0 && interval.task_id == task_id) {
        continue;
      }
      if (interval.overlaps(start, end)) {
        ++overlapping;
      }
    }
    return overlapping >= capacity;
  }

  [[nodiscard]] bool has_headway_conflict(int start_node,
                                          int end_node,
                                          double start,
                                          double headway_seconds,
                                          int task_id = -1) const {
    if (headway_seconds <= 0.0) {
      return false;
    }
    const auto found = by_edge_.find(edge_key(start_node, end_node));
    if (found == by_edge_.end()) {
      return false;
    }
    for (const auto& interval : found->second) {
      if (task_id >= 0 && interval.task_id == task_id) {
        continue;
      }
      const double gap = interval.start > start ? interval.start - start : start - interval.start;
      if (gap < headway_seconds) {
        return true;
      }
    }
    return false;
  }

 private:
  static long long edge_key(int start_node, int end_node) {
    return (static_cast<long long>(start_node) << 32) ^ static_cast<unsigned int>(end_node);
  }

  std::unordered_map<long long, std::vector<EdgeReservation>> by_edge_;
};

struct JunctionShieldConfig {
  int edge_capacity = 1;
  double edge_headway_seconds = 0.0;
  bool require_reachable_goal = true;
};

class JunctionShield {
 public:
  JunctionShield(const Graph& graph, JunctionShieldConfig config = {})
      : graph_(graph), config_(config) {}

  [[nodiscard]] ShieldDecision validate_edge_action(
      int task_id,
      int current,
      int next,
      int goal,
      double ready_time,
      const ReservationTable& node_reservations,
      const EdgeReservationTable& edge_reservations,
      const std::set<std::pair<int, int>>& fault_edges = {}) const {
    if (!graph_.has_edge(current, next)) {
      return ShieldDecision{SafetyStatus::kMissingEdge};
    }
    if (fault_edges.find({current, next}) != fault_edges.end()) {
      return ShieldDecision{SafetyStatus::kFaultedEdge};
    }

    const auto& edge = graph_.edge(current, next);
    const double edge_start = ready_time;
    const double edge_end = ready_time + edge.travel_time();
    const double node_start = edge_end;
    const double node_end = node_start + graph_.service_time(next);

    if (edge_reservations.has_capacity_conflict(current,
                                                next,
                                                edge_start,
                                                edge_end,
                                                config_.edge_capacity,
                                                task_id)) {
      return ShieldDecision{SafetyStatus::kEdgeCapacityConflict,
                            edge_start,
                            edge_end,
                            node_start,
                            node_end};
    }
    if (edge_reservations.has_headway_conflict(current,
                                               next,
                                               edge_start,
                                               config_.edge_headway_seconds,
                                               task_id)) {
      return ShieldDecision{SafetyStatus::kEdgeHeadwayConflict,
                            edge_start,
                            edge_end,
                            node_start,
                            node_end};
    }
    if (next != goal && node_reservations.has_conflict(next, node_start, node_end, task_id)) {
      return ShieldDecision{SafetyStatus::kNodeReservationConflict,
                            edge_start,
                            edge_end,
                            node_start,
                            node_end};
    }
    if (config_.require_reachable_goal && next != goal && !has_route_to_goal(next, goal, fault_edges)) {
      return ShieldDecision{SafetyStatus::kUnreachableGoal,
                            edge_start,
                            edge_end,
                            node_start,
                            node_end};
    }
    return ShieldDecision{SafetyStatus::kAllowed, edge_start, edge_end, node_start, node_end};
  }

 private:
  [[nodiscard]] bool has_route_to_goal(int start,
                                       int goal,
                                       const std::set<std::pair<int, int>>& fault_edges) const {
    AStarPlanner planner(graph_);
    return !planner.plan(start, goal, 0.0, nullptr, fault_edges).empty();
  }

  const Graph& graph_;
  JunctionShieldConfig config_;
};

}  // namespace czr005::ics
