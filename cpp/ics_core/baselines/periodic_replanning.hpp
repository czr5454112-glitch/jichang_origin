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

struct PeriodicReplanningConfig {
  double interval_seconds = 5.0;
  std::size_t max_tasks = 8;
  int max_ticks = 2048;
  int edge_capacity = 1;
  double edge_headway_seconds = 0.0;
  std::unordered_map<int, int> node_capacities;
  std::vector<MergeGroupEdge> merge_groups;
  int merge_capacity = 1;
  double merge_headway_seconds = 0.0;
};

struct PeriodicFaultWindow {
  int start = -1;
  int end = -1;
  double fault_start = 0.0;
  double repair_time = 0.0;
};

struct PeriodicReplanningEvent {
  std::string event;
  std::string segment_id;
  int task_id = -1;
  int current = -1;
  int next_node = -1;
  int start = -1;
  int goal = -1;
  double entry_time = 0.0;
  double finish_time = 0.0;
  double tick_time = 0.0;
  double ready_time = 0.0;
  int priority_rank = -1;
  int replan_count = 0;
  bool reached_goal = false;
  std::string reason;
  std::vector<int> path;
  std::vector<int> planned_path;
};

struct PeriodicReplanningResult {
  int planned_count = 0;
  int unplanned_count = 0;
  int replan_count = 0;
  int tick_count = 0;
  int peak_active_bags = 0;
  int reservation_conflicts = 0;
  int edge_reservation_conflicts = 0;
  int post_shield_conflicts = 0;
  double mean_travel_time = 0.0;
  double makespan = 0.0;
  std::vector<std::vector<PathNode>> routes;
  std::vector<PeriodicReplanningEvent> events;
};

namespace periodic_detail {

inline constexpr double kEpsilon = 1e-9;

struct ActiveBag {
  TaskLeg task;
  std::vector<PathNode> route;
  int current = -1;
  double ready_time = 0.0;
  double waiting_time = 0.0;
  int replan_count = 0;
  bool closed = false;
};

inline std::vector<int> route_locations(const std::vector<PathNode>& route) {
  std::vector<int> path;
  path.reserve(route.size());
  for (const auto& node : route) {
    path.push_back(node.location);
  }
  return path;
}

inline void validate_fault_windows(const std::vector<PeriodicFaultWindow>& fault_windows) {
  for (const auto& window : fault_windows) {
    if (window.repair_time <= window.fault_start) {
      throw std::invalid_argument("repair_time must be greater than fault_start");
    }
  }
}

inline std::set<std::pair<int, int>> active_fault_edges(
    const std::set<std::pair<int, int>>& fault_edges,
    const std::vector<PeriodicFaultWindow>& fault_windows,
    double ready_time) {
  std::set<std::pair<int, int>> active = fault_edges;
  for (const auto& window : fault_windows) {
    if (window.fault_start <= ready_time && ready_time < window.repair_time) {
      active.insert({window.start, window.end});
    }
  }
  return active;
}

inline double earliest_safe_node_start(const ReservationTable& reservations,
                                       int task_id,
                                       int node,
                                       double earliest_start,
                                       double duration,
                                       int capacity) {
  if (capacity <= 0) {
    throw std::invalid_argument("node capacity must be positive");
  }
  double candidate = earliest_start;
  const auto& intervals = reservations.intervals(node);
  for (std::size_t attempt = 0; attempt < intervals.size() * 2 + 2; ++attempt) {
    const double candidate_end = candidate + duration;
    if (!reservations.has_capacity_conflict(node, candidate, candidate_end, capacity, task_id)) {
      return candidate;
    }
    bool has_overlap = false;
    double next_candidate = candidate;
    for (const auto& interval : intervals) {
      if (interval.task_id == task_id) {
        continue;
      }
      if (interval.overlaps(candidate, candidate_end)) {
        has_overlap = true;
        if (next_candidate == candidate || interval.end + kEpsilon < next_candidate) {
          next_candidate = interval.end + kEpsilon;
        }
      }
    }
    if (!has_overlap || next_candidate <= candidate) {
      return candidate;
    }
    candidate = next_candidate;
  }
  return candidate;
}

inline int node_capacity(const PeriodicReplanningConfig& config, int node) {
  const auto found = config.node_capacities.find(node);
  return found == config.node_capacities.end() ? 1 : found->second;
}

inline ActiveBag admit_bag(const Graph& graph,
                           ReservationTable& reservations,
                           const PeriodicReplanningConfig& config,
                           const TaskLeg& task,
                           double tick_time,
                           std::vector<PeriodicReplanningEvent>& events) {
  const double start_time = earliest_safe_node_start(reservations,
                                                     task.task_id,
                                                     task.start,
                                                     std::max(task.pass_time, tick_time),
                                                     graph.service_time(task.start),
                                                     node_capacity(config, task.start));
  PathNode start_node{task.start,
                      start_time,
                      start_time + graph.service_time(task.start),
                      start_time,
                      graph.heuristic(task.start, task.goal),
                      start_time + graph.heuristic(task.start, task.goal)};
  reservations.reserve(task.task_id, task.start, start_node.t1, start_node.t2);
  events.push_back(PeriodicReplanningEvent{"arrival",
                                           task.segment_id,
                                           task.task_id,
                                           task.start,
                                           -1,
                                           -1,
                                           task.goal,
                                           task.pass_time,
                                           0.0,
                                           tick_time,
                                           start_node.t2,
                                           -1,
                                           0,
                                           false,
                                           "",
                                           {},
                                           {}});
  ActiveBag bag;
  bag.task = task;
  bag.route.push_back(start_node);
  bag.current = task.start;
  bag.ready_time = start_node.t2;
  bag.waiting_time = std::max(0.0, start_time - task.pass_time);
  return bag;
}

inline void close_planned(PeriodicReplanningResult& result,
                          ActiveBag& bag,
                          double tick_time,
                          int priority_rank) {
  if (bag.closed) {
    return;
  }
  bag.closed = true;
  ++result.planned_count;
  result.routes.push_back(bag.route);
  result.makespan = std::max(result.makespan, bag.route.back().t2);
  result.mean_travel_time += bag.route.back().t2 - bag.task.pass_time;
  result.events.push_back(PeriodicReplanningEvent{"planned",
                                                  bag.task.segment_id,
                                                  bag.task.task_id,
                                                  bag.current,
                                                  -1,
                                                  bag.task.start,
                                                  bag.task.goal,
                                                  bag.task.pass_time,
                                                  bag.route.back().t2,
                                                  tick_time,
                                                  bag.ready_time,
                                                  priority_rank,
                                                  bag.replan_count,
                                                  true,
                                                  "",
                                                  route_locations(bag.route),
                                                  {}});
}

inline void hold_bag(const PeriodicReplanningConfig& config,
                     ReservationTable& reservations,
                     ActiveBag& bag,
                     double tick_time,
                     int priority_rank,
                     std::vector<PeriodicReplanningEvent>& events) {
  const double hold_start = earliest_safe_node_start(reservations,
                                                     bag.task.task_id,
                                                     bag.current,
                                                     std::max(tick_time, bag.ready_time),
                                                     config.interval_seconds,
                                                     node_capacity(config, bag.current));
  const double hold_end = hold_start + config.interval_seconds;
  auto& current_node = bag.route.back();
  current_node.t2 = hold_end;
  current_node.gcost = hold_end;
  current_node.fcost = hold_end + current_node.hcost;
  bag.waiting_time += hold_end - hold_start;
  bag.ready_time = hold_end;
  reservations.reserve(bag.task.task_id, bag.current, hold_start, hold_end);
  events.push_back(PeriodicReplanningEvent{"replan_hold",
                                           bag.task.segment_id,
                                           bag.task.task_id,
                                           bag.current,
                                           bag.current,
                                           -1,
                                           bag.task.goal,
                                           bag.task.pass_time,
                                           0.0,
                                           tick_time,
                                           bag.ready_time,
                                           priority_rank,
                                           bag.replan_count,
                                           false,
                                           "no_route",
                                           {},
                                           {}});
}

}  // namespace periodic_detail

inline PeriodicReplanningResult run_periodic_replanning_sipp(
    const Graph& graph,
    const TaskStream& tasks,
    const PeriodicReplanningConfig& config = {},
    const std::set<std::pair<int, int>>& fault_edges = {},
    const std::vector<PeriodicFaultWindow>& fault_windows = {}) {
  if (config.interval_seconds <= 0.0) {
    throw std::invalid_argument("interval_seconds must be positive");
  }
  if (config.max_tasks == 0) {
    throw std::invalid_argument("max_tasks must be positive");
  }
  if (config.max_ticks <= 0) {
    throw std::invalid_argument("max_ticks must be positive");
  }
  if (config.edge_capacity <= 0) {
    throw std::invalid_argument("edge_capacity must be positive");
  }
  if (config.merge_capacity <= 0) {
    throw std::invalid_argument("merge_capacity must be positive");
  }
  periodic_detail::validate_fault_windows(fault_windows);

  std::vector<TaskLeg> selected;
  const std::size_t limit = std::min(config.max_tasks, tasks.size());
  selected.reserve(limit);
  for (std::size_t index = 0; index < limit; ++index) {
    selected.push_back(tasks.tasks()[index]);
  }
  std::sort(selected.begin(), selected.end(), [](const TaskLeg& left, const TaskLeg& right) {
    if (left.pass_time != right.pass_time) {
      return left.pass_time < right.pass_time;
    }
    if (left.task_id != right.task_id) {
      return left.task_id < right.task_id;
    }
    return left.leg < right.leg;
  });

  ReservationTable node_reservations;
  EdgeReservationTable edge_reservations;
  SIPPPlanner planner(graph);
  PeriodicReplanningResult result;
  std::vector<periodic_detail::ActiveBag> active;
  std::size_t next_task_index = 0;
  double tick_time = selected.empty() ? 0.0 : selected.front().pass_time;

  auto has_open_active = [&active]() {
    return std::any_of(active.begin(), active.end(), [](const auto& bag) { return !bag.closed; });
  };

  while ((next_task_index < selected.size() || has_open_active()) &&
         result.tick_count < config.max_ticks) {
    if (!has_open_active() && next_task_index < selected.size()) {
      tick_time = std::max(tick_time, selected[next_task_index].pass_time);
    }

    while (next_task_index < selected.size() &&
           selected[next_task_index].pass_time <= tick_time + periodic_detail::kEpsilon) {
      active.push_back(periodic_detail::admit_bag(graph,
                                                  node_reservations,
                                                  config,
                                                  selected[next_task_index],
                                                  tick_time,
                                                  result.events));
      ++next_task_index;
    }

    std::vector<std::size_t> open_indices;
    std::vector<std::size_t> ready_indices;
    for (std::size_t index = 0; index < active.size(); ++index) {
      if (active[index].closed) {
        continue;
      }
      open_indices.push_back(index);
      if (active[index].ready_time <= tick_time + periodic_detail::kEpsilon) {
        ready_indices.push_back(index);
      }
    }
    result.peak_active_bags =
        std::max(result.peak_active_bags, static_cast<int>(open_indices.size()));
    std::sort(ready_indices.begin(), ready_indices.end(), [&active, tick_time](std::size_t left_index,
                                                                               std::size_t right_index) {
      const auto& left = active[left_index];
      const auto& right = active[right_index];
      const double left_slack = left.task.std - tick_time;
      const double right_slack = right.task.std - tick_time;
      if (left_slack != right_slack) {
        return left_slack < right_slack;
      }
      if (left.waiting_time != right.waiting_time) {
        return left.waiting_time > right.waiting_time;
      }
      if (left.ready_time != right.ready_time) {
        return left.ready_time < right.ready_time;
      }
      if (left.task.task_id != right.task.task_id) {
        return left.task.task_id < right.task.task_id;
      }
      return left.task.leg < right.task.leg;
    });

    for (std::size_t priority_rank = 0; priority_rank < ready_indices.size(); ++priority_rank) {
      auto& bag = active[ready_indices[priority_rank]];
      if (bag.closed) {
        continue;
      }
      if (bag.current == bag.task.goal) {
        periodic_detail::close_planned(result, bag, tick_time, static_cast<int>(priority_rank));
        continue;
      }
      ++result.replan_count;
      ++bag.replan_count;
      const double start_time = std::max(tick_time, bag.ready_time);
      const auto active_faults =
          periodic_detail::active_fault_edges(fault_edges, fault_windows, start_time);
      const auto planned = planner.plan(bag.current,
                                        bag.task.goal,
                                        start_time,
                                        &node_reservations,
                                        &edge_reservations,
                                        config.edge_capacity,
                                        config.edge_headway_seconds,
                                        active_faults,
                                        bag.task.task_id,
                                        config.node_capacities,
                                        config.merge_groups,
                                        config.merge_capacity,
                                        config.merge_headway_seconds);
      if (planned.size() >= 2) {
        const auto& next_node = planned[1];
        const auto& edge = graph.edge(bag.current, next_node.location);
        const double edge_start = next_node.t1 - edge.travel_time();
        edge_reservations.reserve(bag.task.task_id,
                                  bag.current,
                                  next_node.location,
                                  edge_start,
                                  next_node.t1);
        node_reservations.reserve(bag.task.task_id,
                                  next_node.location,
                                  next_node.t1,
                                  next_node.t2);
        const int previous = bag.current;
        bag.route.push_back(next_node);
        bag.current = next_node.location;
        bag.ready_time = next_node.t2;
        const bool reached_goal = bag.current == bag.task.goal;
        result.events.push_back(PeriodicReplanningEvent{"replan_move",
                                                        bag.task.segment_id,
                                                        bag.task.task_id,
                                                        previous,
                                                        bag.current,
                                                        -1,
                                                        bag.task.goal,
                                                        bag.task.pass_time,
                                                        0.0,
                                                        tick_time,
                                                        bag.ready_time,
                                                        static_cast<int>(priority_rank),
                                                        bag.replan_count,
                                                        reached_goal,
                                                        "",
                                                        {},
                                                        periodic_detail::route_locations(planned)});
        if (reached_goal) {
          periodic_detail::close_planned(result, bag, tick_time, static_cast<int>(priority_rank));
        }
        continue;
      }
      if (planned.size() == 1 && bag.current == bag.task.goal) {
        periodic_detail::close_planned(result, bag, tick_time, static_cast<int>(priority_rank));
        continue;
      }

      periodic_detail::hold_bag(config,
                                node_reservations,
                                bag,
                                tick_time,
                                static_cast<int>(priority_rank),
                                result.events);
      if (bag.replan_count >= config.max_ticks) {
        node_reservations.remove_task(bag.task.task_id);
        edge_reservations.remove_task(bag.task.task_id);
        bag.closed = true;
        ++result.unplanned_count;
      }
    }

    ++result.tick_count;
    tick_time += config.interval_seconds;
  }

  for (auto& bag : active) {
    if (bag.closed) {
      continue;
    }
    node_reservations.remove_task(bag.task.task_id);
    edge_reservations.remove_task(bag.task.task_id);
    bag.closed = true;
    ++result.unplanned_count;
    result.events.push_back(PeriodicReplanningEvent{"unplanned",
                                                    bag.task.segment_id,
                                                    bag.task.task_id,
                                                    bag.current,
                                                    -1,
                                                    -1,
                                                    bag.task.goal,
                                                    bag.task.pass_time,
                                                    0.0,
                                                    tick_time,
                                                    bag.ready_time,
                                                    -1,
                                                    bag.replan_count,
                                                    false,
                                                    "max_ticks",
                                                    {},
                                                    {}});
  }

  if (result.planned_count > 0) {
    result.mean_travel_time /= static_cast<double>(result.planned_count);
  }
  result.reservation_conflicts = node_reservations.conflict_count(config.node_capacities);
  result.edge_reservation_conflicts =
      edge_reservations.conflict_count(config.edge_capacity, config.edge_headway_seconds) +
      edge_reservations.merge_group_conflict_count(config.merge_groups,
                                                   config.merge_capacity,
                                                   config.merge_headway_seconds);
  result.post_shield_conflicts = result.reservation_conflicts + result.edge_reservation_conflicts;
  return result;
}

}  // namespace czr005::ics
