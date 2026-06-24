#pragma once

#include <algorithm>
#include <cstddef>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar_types.hpp"
#include "ics_core/routing/sipp.hpp"
#include "ics_core/shield/junction_shield.hpp"
#include "ics_core/task_stream/task_stream.hpp"

namespace czr005::ics {

struct RollingHorizonConfig {
  double horizon_seconds = 300.0;
  std::size_t max_tasks = 8;
  int edge_capacity = 1;
  double edge_headway_seconds = 0.0;
  std::unordered_map<int, int> node_capacities;
  std::vector<MergeGroupEdge> merge_groups;
  int merge_capacity = 1;
  double merge_headway_seconds = 0.0;
};

struct RollingHorizonEvent {
  std::string event;
  std::string segment_id;
  int task_id = -1;
  int start = -1;
  int goal = -1;
  double entry_time = 0.0;
  double finish_time = 0.0;
  double horizon_start = 0.0;
  double horizon_end = 0.0;
  int priority_rank = -1;
  std::vector<int> path;
};

struct RollingHorizonFaultWindow {
  int start = -1;
  int end = -1;
  double fault_start = 0.0;
  double repair_time = 0.0;
};

struct RollingHorizonResult {
  int planned_count = 0;
  int unplanned_count = 0;
  int reservation_conflicts = 0;
  int edge_reservation_conflicts = 0;
  double mean_travel_time = 0.0;
  double makespan = 0.0;
  std::vector<std::vector<PathNode>> routes;
  std::vector<RollingHorizonEvent> events;
};

namespace detail {

struct HorizonBatch {
  double start_time = 0.0;
  double end_time = 0.0;
  std::vector<TaskLeg> tasks;
};

inline std::vector<HorizonBatch> make_horizon_batches(const std::vector<TaskLeg>& tasks,
                                                      double horizon_seconds) {
  std::vector<HorizonBatch> batches;
  if (tasks.empty()) {
    return batches;
  }
  double current_start = tasks.front().pass_time;
  double current_end = current_start + horizon_seconds;
  std::vector<TaskLeg> current;
  for (const auto& task : tasks) {
    while (task.pass_time > current_end) {
      if (!current.empty()) {
        batches.push_back(HorizonBatch{current_start, current_end, current});
        current.clear();
      }
      current_start = current_end;
      current_end = current_start + horizon_seconds;
    }
    current.push_back(task);
  }
  if (!current.empty()) {
    batches.push_back(HorizonBatch{current_start, current_end, current});
  }
  return batches;
}

inline std::vector<int> route_locations(const std::vector<PathNode>& route) {
  std::vector<int> path;
  path.reserve(route.size());
  for (const auto& node : route) {
    path.push_back(node.location);
  }
  return path;
}

inline void validate_fault_windows(const std::vector<RollingHorizonFaultWindow>& fault_windows) {
  for (const auto& window : fault_windows) {
    if (window.repair_time < window.fault_start) {
      throw std::invalid_argument("repair_time must be >= fault_start");
    }
  }
}

inline std::set<std::pair<int, int>> active_fault_edges(
    const std::set<std::pair<int, int>>& fault_edges,
    const std::vector<RollingHorizonFaultWindow>& fault_windows,
    double decision_time) {
  std::set<std::pair<int, int>> active = fault_edges;
  for (const auto& window : fault_windows) {
    if (window.fault_start <= decision_time && decision_time < window.repair_time) {
      active.insert({window.start, window.end});
    }
  }
  return active;
}

inline void reserve_route_edges(const Graph& graph,
                                EdgeReservationTable& edge_reservations,
                                int task_id,
                                const std::vector<PathNode>& route) {
  for (std::size_t index = 1; index < route.size(); ++index) {
    const auto& left = route[index - 1];
    const auto& right = route[index];
    if (left.location == right.location) {
      continue;
    }
    const double edge_start = right.t1 - graph.edge(left.location, right.location).travel_time();
    edge_reservations.reserve(task_id, left.location, right.location, edge_start, right.t1);
  }
}

}  // namespace detail

inline RollingHorizonResult run_rolling_horizon_sipp(
    const Graph& graph,
    const TaskStream& tasks,
    const RollingHorizonConfig& config = {},
    const std::set<std::pair<int, int>>& fault_edges = {},
    const std::vector<RollingHorizonFaultWindow>& fault_windows = {}) {
  if (config.horizon_seconds <= 0.0) {
    throw std::invalid_argument("horizon_seconds must be positive");
  }
  if (config.max_tasks == 0) {
    throw std::invalid_argument("max_tasks must be positive");
  }
  if (config.edge_capacity <= 0) {
    throw std::invalid_argument("edge_capacity must be positive");
  }
  if (config.merge_capacity <= 0) {
    throw std::invalid_argument("merge_capacity must be positive");
  }
  detail::validate_fault_windows(fault_windows);

  const std::size_t limit = std::min(config.max_tasks, tasks.size());
  std::vector<TaskLeg> selected;
  selected.reserve(limit);
  for (std::size_t index = 0; index < limit; ++index) {
    selected.push_back(tasks.tasks()[index]);
  }

  ReservationTable node_reservations;
  EdgeReservationTable edge_reservations;
  SIPPPlanner planner(graph);
  RollingHorizonResult result;
  double travel_time_sum = 0.0;

  for (auto batch : detail::make_horizon_batches(selected, config.horizon_seconds)) {
    std::stable_sort(batch.tasks.begin(), batch.tasks.end(), [](const TaskLeg& left,
                                                                const TaskLeg& right) {
      const double left_slack = left.std - left.pass_time;
      const double right_slack = right.std - right.pass_time;
      if (left_slack != right_slack) {
        return left_slack < right_slack;
      }
      if (left.pass_time != right.pass_time) {
        return left.pass_time < right.pass_time;
      }
      if (left.task_id != right.task_id) {
        return left.task_id < right.task_id;
      }
      return left.leg < right.leg;
    });

    for (std::size_t priority_rank = 0; priority_rank < batch.tasks.size(); ++priority_rank) {
      const auto& task = batch.tasks[priority_rank];
      const auto planning_faults =
          detail::active_fault_edges(fault_edges, fault_windows, task.pass_time);
      const auto route = planner.plan(task.start,
                                      task.goal,
                                      task.pass_time,
                                      &node_reservations,
                                      &edge_reservations,
                                      config.edge_capacity,
                                      config.edge_headway_seconds,
                                      planning_faults,
                                      task.task_id,
                                      config.node_capacities,
                                      config.merge_groups,
                                      config.merge_capacity,
                                      config.merge_headway_seconds);
      if (route.empty()) {
        ++result.unplanned_count;
        result.events.push_back(RollingHorizonEvent{"unplanned",
                                                    task.segment_id,
                                                    task.task_id,
                                                    task.start,
                                                    task.goal,
                                                    task.pass_time,
                                                    0.0,
                                                    batch.start_time,
                                                    batch.end_time,
                                                    static_cast<int>(priority_rank),
                                                    {}});
        continue;
      }

      node_reservations.add_route(task.task_id, route);
      detail::reserve_route_edges(graph, edge_reservations, task.task_id, route);
      ++result.planned_count;
      result.routes.push_back(route);
      result.makespan = std::max(result.makespan, route.back().t2);
      travel_time_sum += route.back().t2 - task.pass_time;
      result.events.push_back(RollingHorizonEvent{"planned",
                                                  task.segment_id,
                                                  task.task_id,
                                                  task.start,
                                                  task.goal,
                                                  task.pass_time,
                                                  route.back().t2,
                                                  batch.start_time,
                                                  batch.end_time,
                                                  static_cast<int>(priority_rank),
                                                  detail::route_locations(route)});
    }
  }

  result.mean_travel_time =
      result.planned_count == 0 ? 0.0 : travel_time_sum / static_cast<double>(result.planned_count);
  result.reservation_conflicts = node_reservations.conflict_count(config.node_capacities);
  result.edge_reservation_conflicts =
      edge_reservations.conflict_count(config.edge_capacity, config.edge_headway_seconds) +
      edge_reservations.merge_group_conflict_count(config.merge_groups,
                                                   config.merge_capacity,
                                                   config.merge_headway_seconds);
  return result;
}

}  // namespace czr005::ics
