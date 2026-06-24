#pragma once

#include <algorithm>
#include <cstddef>
#include <limits>
#include <queue>
#include <set>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar_types.hpp"
#include "ics_core/shield/junction_shield.hpp"

namespace czr005::ics {

class SIPPPlanner {
 public:
  explicit SIPPPlanner(const Graph& graph, double max_time = 86400.0)
      : graph_(graph), max_time_(max_time) {}

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
    if (merge_capacity <= 0) {
      throw std::invalid_argument("merge_capacity must be positive");
    }
    const ReservationTable empty_reservations;
    const EdgeReservationTable empty_edge_reservations;
    const auto& node_table = reservations == nullptr ? empty_reservations : *reservations;
    const auto& edge_table =
        edge_reservations == nullptr ? empty_edge_reservations : *edge_reservations;

    std::vector<Record> records;
    std::priority_queue<OpenEntry, std::vector<OpenEntry>, OpenEntryCompare> open;
    std::unordered_map<int, double> best_t2;
    long long sequence = 0;

    PathNode start_node{start,
                        start_time,
                        start_time + graph_.service_time(start),
                        start_time,
                        graph_.heuristic(start, goal),
                        start_time + graph_.heuristic(start, goal)};
    records.push_back(Record{start_node, -1});
    open.push(OpenEntry{start_node.fcost, sequence++, 0});
    best_t2[start] = start_node.t2;

    while (!open.empty()) {
      const auto entry = open.top();
      open.pop();
      const auto current_index = static_cast<std::size_t>(entry.record_index);
      const auto current = records.at(current_index).node;
      const auto best_found = best_t2.find(current.location);
      if (best_found != best_t2.end() && current.t2 > best_found->second + kEpsilon) {
        continue;
      }
      if (current.location == goal) {
        return reconstruct(records, entry.record_index);
      }

      for (const int next_location : graph_.outgoing(current.location)) {
        if (fault_edges.find({current.location, next_location}) != fault_edges.end()) {
          continue;
        }
        const auto& edge = graph_.edge(current.location, next_location);
        const double travel_time = edge.travel_time();
        const double service_time = graph_.service_time(next_location);
        const auto transition = earliest_safe_transition(current,
                                                         next_location,
                                                         goal,
                                                         travel_time,
                                                         service_time,
                                                         node_table,
                                                         edge_table,
                                                         edge_capacity,
                                                         edge_headway_seconds,
                                                         task_id,
                                                         node_capacities,
                                                         merge_groups,
                                                         merge_capacity,
                                                         merge_headway_seconds);
        if (!transition.valid) {
          continue;
        }

        const double node_end = transition.node_start + service_time;
        const auto best_next = best_t2.find(next_location);
        const double previous_best =
            best_next == best_t2.end() ? std::numeric_limits<double>::infinity()
                                       : best_next->second;
        if (node_end >= previous_best - kEpsilon) {
          continue;
        }

        const double hcost = graph_.heuristic(next_location, goal);
        PathNode child{next_location,
                       transition.node_start,
                       node_end,
                       transition.node_start,
                       hcost,
                       transition.node_start + hcost};
        records.push_back(Record{child, entry.record_index});
        const int child_index = static_cast<int>(records.size()) - 1;
        best_t2[next_location] = node_end;
        open.push(OpenEntry{child.fcost, sequence++, child_index});
      }
    }

    return {};
  }

 private:
  struct Record {
    PathNode node;
    int parent = -1;
  };

  struct OpenEntry {
    double fcost = 0.0;
    long long sequence = 0;
    int record_index = -1;
  };

  struct OpenEntryCompare {
    bool operator()(const OpenEntry& left, const OpenEntry& right) const {
      if (left.fcost != right.fcost) {
        return left.fcost > right.fcost;
      }
      return left.sequence > right.sequence;
    }
  };

  struct Transition {
    bool valid = false;
    double edge_start = 0.0;
    double node_start = 0.0;
  };

  [[nodiscard]] Transition earliest_safe_transition(
      const PathNode& current,
      int next_location,
      int goal,
      double travel_time,
      double service_time,
      const ReservationTable& reservations,
      const EdgeReservationTable& edge_reservations,
      int edge_capacity,
      double edge_headway_seconds,
      int task_id,
      const std::unordered_map<int, int>& node_capacities,
      const std::vector<MergeGroupEdge>& merge_groups,
      int merge_capacity,
      double merge_headway_seconds) const {
    double edge_start = current.t2;
    const auto& intervals = edge_reservations.intervals(current.location, next_location);
    const auto all_intervals = edge_reservations.all_intervals();
    const std::size_t attempts = (intervals.size() + all_intervals.size()) * 3 + 8;
    for (std::size_t attempt = 0; attempt < attempts; ++attempt) {
      edge_start = edge_reservations.earliest_start(current.location,
                                                    next_location,
                                                    edge_start,
                                                    travel_time,
                                                    edge_capacity,
                                                    edge_headway_seconds,
                                                    task_id);
      edge_start = edge_reservations.earliest_merge_group_start(current.location,
                                                                next_location,
                                                                edge_start,
                                                                travel_time,
                                                                merge_groups,
                                                                merge_capacity,
                                                                merge_headway_seconds,
                                                                task_id);
      double node_start = edge_start + travel_time;
      if (next_location != goal) {
        const auto safe_node_start = earliest_safe_node_start(
            reservations,
            next_location,
            node_start,
            service_time,
            node_capacity(node_capacities, next_location),
            task_id);
        if (!safe_node_start.valid) {
          return Transition{};
        }
        if (safe_node_start.value > node_start + kEpsilon) {
          edge_start = safe_node_start.value - travel_time;
          continue;
        }
        node_start = safe_node_start.value;
      }
      if (node_start <= max_time_) {
        return Transition{true, edge_start, node_start};
      }
      return Transition{};
    }
    return Transition{};
  }

  struct SafeNodeStart {
    bool valid = false;
    double value = 0.0;
  };

  [[nodiscard]] SafeNodeStart earliest_safe_node_start(
      const ReservationTable& reservations,
      int node,
      double earliest_start,
      double duration,
      int capacity,
      int task_id) const {
    if (capacity <= 0) {
      return SafeNodeStart{};
    }
    double candidate = earliest_start;
    const auto& intervals = reservations.intervals(node);
    for (std::size_t attempt = 0; attempt < intervals.size() * 2 + 2; ++attempt) {
      const double candidate_end = candidate + duration;
      if (!reservations.has_capacity_conflict(node, candidate, candidate_end, capacity, task_id)) {
        return SafeNodeStart{true, candidate};
      }

      bool has_overlap = false;
      double next_candidate = std::numeric_limits<double>::infinity();
      for (const auto& interval : intervals) {
        if (task_id >= 0 && interval.task_id == task_id) {
          continue;
        }
        if (interval.overlaps(candidate, candidate_end)) {
          has_overlap = true;
          next_candidate = std::min(next_candidate, interval.end + kEpsilon);
        }
      }
      if (!has_overlap || next_candidate > max_time_) {
        return SafeNodeStart{};
      }
      candidate = next_candidate;
    }
    return SafeNodeStart{};
  }

  [[nodiscard]] static int node_capacity(
      const std::unordered_map<int, int>& node_capacities,
      int node) {
    const auto found = node_capacities.find(node);
    return found == node_capacities.end() ? 1 : found->second;
  }

  static std::vector<PathNode> reconstruct(const std::vector<Record>& records, int index) {
    std::vector<PathNode> route;
    while (index >= 0) {
      const auto& record = records.at(static_cast<std::size_t>(index));
      route.push_back(record.node);
      index = record.parent;
    }
    std::reverse(route.begin(), route.end());
    return route;
  }

  inline static constexpr double kEpsilon = 1e-9;

  const Graph& graph_;
  double max_time_ = 86400.0;
};

}  // namespace czr005::ics
