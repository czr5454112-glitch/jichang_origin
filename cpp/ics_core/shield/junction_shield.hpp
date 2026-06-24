#pragma once

#include <algorithm>
#include <set>
#include <stdexcept>
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
  kMergeGroupConflict,
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
    constexpr double epsilon = 1.0e-9;
    return !(candidate_start >= end - epsilon || candidate_end <= start + epsilon);
  }
};

struct MergeGroupEdge {
  int start_node = -1;
  int end_node = -1;
  int group = -1;
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

  void remove_task(int task_id) {
    for (auto iter = by_edge_.begin(); iter != by_edge_.end();) {
      auto& intervals = iter->second;
      intervals.erase(std::remove_if(intervals.begin(), intervals.end(),
                                     [task_id](const EdgeReservation& item) {
                                       return item.task_id == task_id;
                                     }),
                      intervals.end());
      if (intervals.empty()) {
        iter = by_edge_.erase(iter);
      } else {
        ++iter;
      }
    }
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

  [[nodiscard]] bool has_merge_group_conflict(
      int start_node,
      int end_node,
      double start,
      double end,
      const std::vector<MergeGroupEdge>& merge_groups,
      int merge_capacity,
      double merge_headway_seconds,
      int task_id = -1) const {
    if (merge_capacity <= 0) {
      return true;
    }
    const int group = merge_group(start_node, end_node, merge_groups);
    if (group < 0) {
      return false;
    }
    int overlapping = 0;
    for (const auto& interval : all_intervals()) {
      if (task_id >= 0 && interval.task_id == task_id) {
        continue;
      }
      if (merge_group(interval.start_node, interval.end_node, merge_groups) != group) {
        continue;
      }
      if (interval.overlaps(start, end)) {
        ++overlapping;
      }
      const double gap = interval.start > start ? interval.start - start : start - interval.start;
      if (merge_headway_seconds > 0.0 && gap < merge_headway_seconds) {
        return true;
      }
    }
    return overlapping >= merge_capacity;
  }

  [[nodiscard]] const std::vector<EdgeReservation>& intervals(int start_node,
                                                              int end_node) const {
    static const std::vector<EdgeReservation> empty;
    const auto found = by_edge_.find(edge_key(start_node, end_node));
    return found == by_edge_.end() ? empty : found->second;
  }

  [[nodiscard]] std::vector<EdgeReservation> all_intervals() const {
    std::vector<EdgeReservation> values;
    for (const auto& entry : by_edge_) {
      values.insert(values.end(), entry.second.begin(), entry.second.end());
    }
    return values;
  }

  [[nodiscard]] double earliest_start(int start_node,
                                      int end_node,
                                      double earliest,
                                      double duration,
                                      int capacity,
                                      double headway_seconds = 0.0,
                                      int task_id = -1) const {
    double candidate = earliest;
    const auto& edge_intervals = intervals(start_node, end_node);
    for (std::size_t attempt = 0; attempt < edge_intervals.size() * 2 + 2; ++attempt) {
      bool moved = false;
      for (const auto& interval : edge_intervals) {
        if (task_id >= 0 && interval.task_id == task_id) {
          continue;
        }
        const double candidate_end = candidate + duration;
        if (capacity <= 0 || interval.overlaps(candidate, candidate_end)) {
          if (has_capacity_conflict(start_node,
                                    end_node,
                                    candidate,
                                    candidate_end,
                                    capacity,
                                    task_id)) {
            candidate = std::max(candidate, interval.end);
            moved = true;
            break;
          }
        }
        const double gap = interval.start > candidate ? interval.start - candidate
                                                      : candidate - interval.start;
        if (headway_seconds > 0.0 && gap < headway_seconds) {
          candidate = interval.start + headway_seconds;
          moved = true;
          break;
        }
      }
      if (!moved) {
        return candidate;
      }
    }
    return candidate;
  }

  [[nodiscard]] double earliest_merge_group_start(
      int start_node,
      int end_node,
      double earliest,
      double duration,
      const std::vector<MergeGroupEdge>& merge_groups,
      int merge_capacity,
      double merge_headway_seconds = 0.0,
      int task_id = -1) const {
    if (merge_capacity <= 0) {
      throw std::invalid_argument("merge_capacity must be positive");
    }
    const int group = merge_group(start_node, end_node, merge_groups);
    if (group < 0) {
      return earliest;
    }
    const auto intervals = all_intervals();
    std::vector<EdgeReservation> relevant;
    relevant.reserve(intervals.size());
    for (const auto& interval : intervals) {
      if (task_id >= 0 && interval.task_id == task_id) {
        continue;
      }
      if (merge_group(interval.start_node, interval.end_node, merge_groups) == group) {
        relevant.push_back(interval);
      }
    }

    double candidate = earliest;
    for (std::size_t attempt = 0; attempt < relevant.size() * 3 + 4; ++attempt) {
      const double candidate_end = candidate + duration;
      if (!has_merge_group_conflict(start_node,
                                    end_node,
                                    candidate,
                                    candidate_end,
                                    merge_groups,
                                    merge_capacity,
                                    merge_headway_seconds,
                                    task_id)) {
        return candidate;
      }

      bool moved = false;
      double next_candidate = candidate;
      for (const auto& interval : relevant) {
        if (interval.overlaps(candidate, candidate_end)) {
          const double interval_candidate = interval.end;
          if (!moved || interval_candidate < next_candidate) {
            next_candidate = interval_candidate;
          }
          moved = true;
        }
        const double gap = interval.start > candidate ? interval.start - candidate
                                                      : candidate - interval.start;
        if (merge_headway_seconds > 0.0 && gap < merge_headway_seconds) {
          const double headway_candidate = interval.start + merge_headway_seconds;
          if (!moved || headway_candidate < next_candidate) {
            next_candidate = headway_candidate;
          }
          moved = true;
        }
      }
      if (!moved) {
        return candidate;
      }
      if (next_candidate <= candidate) {
        next_candidate = candidate + 1.0e-9;
      }
      candidate = next_candidate;
    }
    return candidate;
  }

  [[nodiscard]] int conflict_count(int capacity, double headway_seconds) const {
    int conflicts = 0;
    for (const auto& entry : by_edge_) {
      const auto& intervals = entry.second;
      for (std::size_t i = 0; i < intervals.size(); ++i) {
        for (std::size_t j = i + 1; j < intervals.size(); ++j) {
          if (intervals[j].start >= intervals[i].end &&
              intervals[j].start - intervals[i].start >= headway_seconds) {
            break;
          }
          if (intervals[i].overlaps(intervals[j].start, intervals[j].end) && capacity <= 1) {
            ++conflicts;
          } else {
            const double gap = intervals[i].start > intervals[j].start
                                   ? intervals[i].start - intervals[j].start
                                   : intervals[j].start - intervals[i].start;
            if (headway_seconds > 0.0 && gap < headway_seconds) {
              ++conflicts;
            }
          }
        }
      }
    }
    return conflicts;
  }

  [[nodiscard]] int merge_group_conflict_count(
      const std::vector<MergeGroupEdge>& merge_groups,
      int merge_capacity,
      double merge_headway_seconds) const {
    if (merge_groups.empty()) {
      return 0;
    }
    std::unordered_map<int, std::vector<EdgeReservation>> grouped;
    for (const auto& interval : all_intervals()) {
      const int group = merge_group(interval.start_node, interval.end_node, merge_groups);
      if (group >= 0) {
        grouped[group].push_back(interval);
      }
    }

    int conflicts = 0;
    for (auto& entry : grouped) {
      auto& intervals = entry.second;
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
      if (merge_capacity > 1) {
        std::vector<double> points;
        points.reserve(intervals.size() * 2);
        for (const auto& interval : intervals) {
          points.push_back(interval.start);
          points.push_back(interval.end);
        }
        std::sort(points.begin(), points.end());
        points.erase(std::unique(points.begin(), points.end()), points.end());
        for (const double point : points) {
          int active = 0;
          for (const auto& interval : intervals) {
            if (interval.start <= point && point <= interval.end) {
              ++active;
            }
          }
          if (active > merge_capacity) {
            conflicts += active - merge_capacity;
          }
        }
      }
      for (std::size_t i = 0; i < intervals.size(); ++i) {
        for (std::size_t j = i + 1; j < intervals.size(); ++j) {
          if (intervals[i].task_id == intervals[j].task_id) {
            continue;
          }
          if (intervals[j].start >= intervals[i].end &&
              intervals[j].start - intervals[i].start >= merge_headway_seconds) {
            break;
          }
          if (merge_capacity <= 1 && intervals[i].overlaps(intervals[j].start, intervals[j].end)) {
            ++conflicts;
          } else {
            const double gap = intervals[i].start > intervals[j].start
                                   ? intervals[i].start - intervals[j].start
                                   : intervals[j].start - intervals[i].start;
            if (merge_headway_seconds > 0.0 && gap < merge_headway_seconds) {
              ++conflicts;
            }
          }
        }
      }
    }
    return conflicts;
  }

 private:
  [[nodiscard]] static int merge_group(int start_node,
                                       int end_node,
                                       const std::vector<MergeGroupEdge>& merge_groups) {
    for (const auto& edge : merge_groups) {
      if (edge.start_node == start_node && edge.end_node == end_node) {
        return edge.group;
      }
    }
    return -1;
  }

  static long long edge_key(int start_node, int end_node) {
    return (static_cast<long long>(start_node) << 32) ^ static_cast<unsigned int>(end_node);
  }

  std::unordered_map<long long, std::vector<EdgeReservation>> by_edge_;
};

struct JunctionShieldConfig {
  int edge_capacity = 1;
  double edge_headway_seconds = 0.0;
  std::unordered_map<int, int> node_capacities;
  std::vector<MergeGroupEdge> merge_groups;
  int merge_capacity = 1;
  double merge_headway_seconds = 0.0;
  bool require_reachable_goal = true;
  bool allow_goal_node_overlap = true;
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
    if (has_merge_group_conflict(current, next, edge_start, edge_end, task_id, edge_reservations)) {
      return ShieldDecision{SafetyStatus::kMergeGroupConflict,
                            edge_start,
                            edge_end,
                            node_start,
                            node_end};
    }
    if ((!config_.allow_goal_node_overlap || next != goal) &&
        node_reservations.has_capacity_conflict(next,
                                                node_start,
                                                node_end,
                                                node_capacity(next),
                                                task_id)) {
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

  [[nodiscard]] int node_capacity(int node) const {
    const auto found = config_.node_capacities.find(node);
    return found == config_.node_capacities.end() ? 1 : found->second;
  }

  [[nodiscard]] int merge_group(int start_node, int end_node) const {
    for (const auto& edge : config_.merge_groups) {
      if (edge.start_node == start_node && edge.end_node == end_node) {
        return edge.group;
      }
    }
    return -1;
  }

  [[nodiscard]] bool has_merge_group_conflict(
      int start_node,
      int end_node,
      double start,
      double end,
      int task_id,
      const EdgeReservationTable& edge_reservations) const {
    if (config_.merge_capacity <= 0) {
      return true;
    }
    const int group = merge_group(start_node, end_node);
    if (group < 0) {
      return false;
    }
    int overlapping = 0;
    for (const auto& interval : edge_reservations.all_intervals()) {
      if (interval.task_id == task_id) {
        continue;
      }
      if (merge_group(interval.start_node, interval.end_node) != group) {
        continue;
      }
      if (interval.overlaps(start, end)) {
        ++overlapping;
      }
      const double gap = interval.start > start ? interval.start - start : start - interval.start;
      if (config_.merge_headway_seconds > 0.0 && gap < config_.merge_headway_seconds) {
        return true;
      }
    }
    return overlapping >= config_.merge_capacity;
  }

  const Graph& graph_;
  JunctionShieldConfig config_;
};

}  // namespace czr005::ics
