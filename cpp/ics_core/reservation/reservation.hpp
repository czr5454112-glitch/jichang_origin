#pragma once

#include <algorithm>
#include <unordered_map>
#include <vector>

#include "ics_core/routing/astar_types.hpp"

namespace czr005::ics {

struct NodeReservation {
  int task_id = -1;
  int node = -1;
  double start = 0.0;
  double end = 0.0;

  [[nodiscard]] bool overlaps(double candidate_start, double candidate_end) const {
    if (end <= start || candidate_end <= candidate_start) {
      return false;
    }
    return !(candidate_start > end || candidate_end < start);
  }
};

class ReservationTable {
 public:
  [[nodiscard]] bool has_conflict(int node,
                                  double start,
                                  double end,
                                  int task_id = -1) const {
    const auto found = by_node_.find(node);
    if (found == by_node_.end()) {
      return false;
    }
    for (const auto& interval : found->second) {
      if (task_id >= 0 && interval.task_id == task_id) {
        continue;
      }
      if (interval.overlaps(start, end)) {
        return true;
      }
    }
    return false;
  }

  [[nodiscard]] bool has_capacity_conflict(int node,
                                           double start,
                                           double end,
                                           int capacity = 1,
                                           int task_id = -1) const {
    if (capacity <= 0) {
      return true;
    }
    const auto found = by_node_.find(node);
    if (found == by_node_.end()) {
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

  void reserve(int task_id, int node, double start, double end) {
    auto& intervals = by_node_[node];
    intervals.erase(std::remove_if(intervals.begin(), intervals.end(),
                                   [task_id](const NodeReservation& item) {
                                     return item.task_id == task_id;
                                   }),
                    intervals.end());
    intervals.push_back(NodeReservation{task_id, node, start, end});
    std::sort(intervals.begin(), intervals.end(),
              [](const NodeReservation& left, const NodeReservation& right) {
                if (left.start != right.start) {
                  return left.start < right.start;
                }
                if (left.end != right.end) {
                  return left.end < right.end;
                }
                return left.task_id < right.task_id;
              });
  }

  void add_route(int task_id, const std::vector<PathNode>& route) {
    for (const auto& node : route) {
      reserve(task_id, node.location, node.t1, node.t2);
    }
  }

  [[nodiscard]] const std::vector<NodeReservation>& intervals(int node) const {
    static const std::vector<NodeReservation> empty;
    const auto found = by_node_.find(node);
    return found == by_node_.end() ? empty : found->second;
  }

  void remove_task(int task_id) {
    for (auto iter = by_node_.begin(); iter != by_node_.end();) {
      auto& intervals = iter->second;
      intervals.erase(std::remove_if(intervals.begin(), intervals.end(),
                                     [task_id](const NodeReservation& item) {
                                       return item.task_id == task_id;
                                     }),
                      intervals.end());
      if (intervals.empty()) {
        iter = by_node_.erase(iter);
      } else {
        ++iter;
      }
    }
  }

  [[nodiscard]] int conflict_count(
      const std::unordered_map<int, int>& node_capacities = {}) const {
    int conflicts = 0;
    for (const auto& entry : by_node_) {
      const auto capacity_found = node_capacities.find(entry.first);
      const int capacity = capacity_found == node_capacities.end() ? 1 : capacity_found->second;
      const auto& intervals = entry.second;
      if (capacity > 1) {
        std::vector<NodeReservation> active_intervals;
        active_intervals.reserve(intervals.size());
        for (const auto& interval : intervals) {
          if (interval.end > interval.start) {
            active_intervals.push_back(interval);
          }
        }
        std::vector<double> points;
        points.reserve(active_intervals.size() * 2);
        for (const auto& interval : active_intervals) {
          points.push_back(interval.start);
          points.push_back(interval.end);
        }
        std::sort(points.begin(), points.end());
        points.erase(std::unique(points.begin(), points.end()), points.end());
        for (const double point : points) {
          int active = 0;
          for (const auto& interval : active_intervals) {
            if (interval.start <= point && point <= interval.end) {
              ++active;
            }
          }
          if (active > capacity) {
            conflicts += active - capacity;
          }
        }
        continue;
      }
      for (std::size_t i = 0; i < intervals.size(); ++i) {
        for (std::size_t j = i + 1; j < intervals.size(); ++j) {
          if (intervals[j].start > intervals[i].end) {
            break;
          }
          if (intervals[i].overlaps(intervals[j].start, intervals[j].end)) {
            ++conflicts;
          }
        }
      }
    }
    return conflicts;
  }

 private:
  std::unordered_map<int, std::vector<NodeReservation>> by_node_;
};

}  // namespace czr005::ics
