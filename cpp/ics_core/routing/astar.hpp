#pragma once

#include <algorithm>
#include <cstddef>
#include <set>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar_types.hpp"

namespace czr005::ics {

class AStarPlanner {
 public:
  explicit AStarPlanner(const Graph& graph) : graph_(graph) {}

  [[nodiscard]] std::vector<PathNode> plan(
      int start,
      int goal,
      double start_time = 0.0,
      const ReservationTable* reservations = nullptr,
      const std::set<std::pair<int, int>>& fault_edges = {},
      int task_id = -1) const {
    std::vector<Record> records;
    std::vector<int> open;
    std::set<int> closed;

    records.push_back(Record{PathNode{start, start_time,
                                      start_time + graph_.service_time(start),
                                      0.0, 0.0, 0.0},
                             -1});
    open.push_back(0);

    while (!open.empty()) {
      const int current_index = pop_min_f(open, records);
      const auto current = records.at(static_cast<std::size_t>(current_index)).node;
      closed.insert(current.location);

      if (current.location == goal) {
        return reconstruct(records, current_index);
      }

      for (const int next_location : graph_.outgoing(current.location)) {
        if (closed.find(next_location) != closed.end()) {
          continue;
        }
        if (fault_edges.find({current.location, next_location}) != fault_edges.end()) {
          continue;
        }
        const auto& edge = graph_.edge(current.location, next_location);
        const double t1 = current.t2 + edge.travel_time();
        const double t2 = t1 + graph_.service_time(next_location);
        if (next_location != goal && reservations != nullptr &&
            reservations->has_conflict(next_location, t1, t2, task_id)) {
          continue;
        }

        const double gcost = t1;
        const double hcost = graph_.heuristic(next_location, goal);
        PathNode child{next_location, t1, t2, gcost, hcost, gcost + hcost};
        const int existing_index = in_open(open, records, next_location);
        if (existing_index < 0) {
          records.push_back(Record{child, current_index});
          open.push_back(static_cast<int>(records.size()) - 1);
        } else if (gcost < records.at(static_cast<std::size_t>(existing_index)).node.gcost) {
          auto& existing = records.at(static_cast<std::size_t>(existing_index));
          existing.node = child;
          existing.parent = current_index;
        }
      }
    }

    return {};
  }

 private:
  struct Record {
    PathNode node;
    int parent = -1;
  };

  static int in_open(const std::vector<int>& open,
                     const std::vector<Record>& records,
                     int location) {
    for (const int index : open) {
      if (records.at(static_cast<std::size_t>(index)).node.location == location) {
        return index;
      }
    }
    return -1;
  }

  static int pop_min_f(std::vector<int>& open, const std::vector<Record>& records) {
    std::size_t best_pos = 0;
    for (std::size_t pos = 1; pos < open.size(); ++pos) {
      const auto diff = records.at(static_cast<std::size_t>(open[pos])).node.fcost -
                        records.at(static_cast<std::size_t>(open[best_pos])).node.fcost;
      if (static_cast<int>(diff) < 0) {
        best_pos = pos;
      }
    }
    const int value = open[best_pos];
    open.erase(open.begin() + static_cast<std::ptrdiff_t>(best_pos));
    return value;
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

  const Graph& graph_;
};

}  // namespace czr005::ics
