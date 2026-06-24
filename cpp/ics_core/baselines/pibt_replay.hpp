#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "ics_core/baselines/pibt.hpp"
#include "ics_core/baselines/periodic_replanning.hpp"
#include "ics_core/graph/graph.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar_types.hpp"
#include "ics_core/shield/junction_shield.hpp"
#include "ics_core/task_stream/task_stream.hpp"

namespace czr005::ics {

struct PIBTActiveBagReplayConfig {
  double interval_seconds = 5.0;
  double hold_seconds = 5.0;
  std::size_t max_tasks = 8;
  int max_ticks = 2048;
  int edge_capacity = 1;
  double edge_headway_seconds = 0.0;
  std::unordered_map<int, int> node_capacities;
  std::vector<MergeGroupEdge> merge_groups;
  int merge_capacity = 1;
  double merge_headway_seconds = 0.0;
};

struct PIBTActiveBagReplayEvent {
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
  int decision_count = 0;
  bool reached_goal = false;
  std::string reason;
  std::vector<int> path;
};

struct PIBTActiveBagReplayResult {
  int planned_count = 0;
  int unplanned_count = 0;
  int decision_count = 0;
  int tick_count = 0;
  int peak_active_bags = 0;
  int move_count = 0;
  int hold_count = 0;
  int reservation_conflicts = 0;
  int edge_reservation_conflicts = 0;
  int post_shield_conflicts = 0;
  double mean_travel_time = 0.0;
  double makespan = 0.0;
  std::vector<std::vector<PathNode>> routes;
  std::vector<PIBTActiveBagReplayEvent> events;
};

namespace pibt_replay_detail {

inline constexpr double kEpsilon = 1e-9;

inline int node_capacity(const PIBTActiveBagReplayConfig& config, int node) {
  const auto found = config.node_capacities.find(node);
  return found == config.node_capacities.end() ? 1 : found->second;
}

inline double next_decision_time(double tick_time, double ready_time, double interval_seconds) {
  if (ready_time <= tick_time + kEpsilon) {
    return tick_time;
  }
  const double steps = std::ceil(std::max(0.0, ready_time - tick_time - kEpsilon) /
                                 interval_seconds);
  return tick_time + steps * interval_seconds;
}

inline double earliest_safe_node_start(const ReservationTable& reservations,
                                       int task_id,
                                       int node,
                                       double earliest_start,
                                       double duration,
                                       int capacity) {
  double candidate = earliest_start;
  for (const auto& interval : reservations.intervals(node)) {
    if (interval.task_id == task_id) {
      continue;
    }
    if (!interval.overlaps(candidate, candidate + duration)) {
      continue;
    }
    if (reservations.has_capacity_conflict(node, candidate, candidate + duration, capacity, task_id)) {
      candidate = interval.end + kEpsilon;
    }
  }
  return candidate;
}

inline std::vector<int> route_locations(const std::vector<PathNode>& route) {
  std::vector<int> path;
  path.reserve(route.size());
  for (const auto& node : route) {
    path.push_back(node.location);
  }
  return path;
}

inline periodic_detail::ActiveBag admit_bag(const Graph& graph,
                                            const PIBTActiveBagReplayConfig& config,
                                            ReservationTable& reservations,
                                            const TaskLeg& task,
                                            double tick_time,
                                            std::vector<PIBTActiveBagReplayEvent>& events) {
  const double service_time = graph.service_time(task.start);
  const double occupancy_duration =
      task.start == task.goal ? service_time : std::max(service_time, config.hold_seconds);
  const double start_time = earliest_safe_node_start(reservations,
                                                     task.task_id,
                                                     task.start,
                                                     std::max(task.pass_time, tick_time),
                                                     occupancy_duration,
                                                     node_capacity(config, task.start));
  const double service_end = start_time + service_time;
  const double ready_time = task.start == task.goal
                                ? service_end
                                : next_decision_time(tick_time, service_end, config.interval_seconds);
  const double reservation_end =
      task.start == task.goal ? service_end : kPIBTOccupiedUntilRelease;
  PathNode start_node{task.start,
                      start_time,
                      reservation_end,
                      reservation_end,
                      graph.heuristic(task.start, task.goal),
                      reservation_end + graph.heuristic(task.start, task.goal)};
  reservations.reserve(task.task_id, task.start, start_node.t1, start_node.t2);
  events.push_back(PIBTActiveBagReplayEvent{"arrival",
                                            task.segment_id,
                                            task.task_id,
                                            task.start,
                                            -1,
                                            -1,
                                            task.goal,
                                            task.pass_time,
                                            0.0,
                                            tick_time,
                                            ready_time,
                                            -1,
                                            0,
                                            false,
                                            "",
                                            {}});
  periodic_detail::ActiveBag bag;
  bag.task = task;
  bag.route.push_back(start_node);
  bag.current = task.start;
  bag.ready_time = ready_time;
  bag.waiting_time = std::max(0.0, start_time - task.pass_time);
  return bag;
}

inline void close_planned(PIBTActiveBagReplayResult& result,
                          periodic_detail::ActiveBag& bag,
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
  result.events.push_back(PIBTActiveBagReplayEvent{"planned",
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
                                                   route_locations(bag.route)});
}

inline void apply_hold(const PIBTResolvedAction& action,
                       ReservationTable& node_reservations,
                       periodic_detail::ActiveBag& bag,
                       double tick_time,
                       std::vector<PIBTActiveBagReplayEvent>& events) {
  bag.waiting_time += std::max(0.0, action.node_end - bag.ready_time);
  bag.ready_time = action.node_end;
  auto& current_node = bag.route.back();
  current_node.t2 = kPIBTOccupiedUntilRelease;
  current_node.gcost = current_node.t2;
  current_node.fcost = current_node.gcost + current_node.hcost;
  node_reservations.reserve(bag.task.task_id, bag.current, current_node.t1, current_node.t2);
  events.push_back(PIBTActiveBagReplayEvent{"pibt_hold",
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
                                            action.priority_rank,
                                            bag.replan_count,
                                            false,
                                            action.reason,
                                            {}});
}

inline void apply_move(const Graph& graph,
                       const PIBTResolvedAction& action,
                       ReservationTable& node_reservations,
                       EdgeReservationTable& edge_reservations,
                       periodic_detail::ActiveBag& bag,
                       double tick_time,
                       double interval_seconds,
                       std::vector<PIBTActiveBagReplayEvent>& events) {
  const int previous = bag.current;
  bag.waiting_time += std::max(0.0, action.edge_start - bag.ready_time);
  auto& current_node = bag.route.back();
  current_node.t2 = action.edge_start;
  current_node.gcost = action.edge_start;
  current_node.fcost = current_node.gcost + current_node.hcost;
  node_reservations.reserve(bag.task.task_id, previous, current_node.t1, current_node.t2);
  edge_reservations.reserve(bag.task.task_id,
                            previous,
                            action.next_node,
                            action.edge_start,
                            action.edge_end);
  const bool reached_goal = action.next_node == bag.task.goal;
  const double occupancy_end = reached_goal ? action.node_end : kPIBTOccupiedUntilRelease;
  node_reservations.reserve(bag.task.task_id,
                            action.next_node,
                            action.node_start,
                            occupancy_end);
  bag.route.push_back(PathNode{action.next_node,
                               action.node_start,
                               occupancy_end,
                               occupancy_end,
                               graph.heuristic(action.next_node, bag.task.goal),
                               occupancy_end + graph.heuristic(action.next_node, bag.task.goal)});
  bag.current = action.next_node;
  bag.ready_time = reached_goal
                       ? action.node_end
                       : next_decision_time(tick_time, action.node_end, interval_seconds);
  events.push_back(PIBTActiveBagReplayEvent{"pibt_move",
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
                                            action.priority_rank,
                                            bag.replan_count,
                                            reached_goal,
                                            action.reason,
                                            {}});
}

}  // namespace pibt_replay_detail

inline PIBTActiveBagReplayResult run_pibt_active_bag_replay(
    const Graph& graph,
    const TaskStream& tasks,
    const PIBTActiveBagReplayConfig& config = {},
    const std::set<std::pair<int, int>>& fault_edges = {},
    const std::vector<PeriodicFaultWindow>& fault_windows = {}) {
  if (config.interval_seconds <= 0.0) {
    throw std::invalid_argument("interval_seconds must be positive");
  }
  if (config.hold_seconds <= 0.0) {
    throw std::invalid_argument("hold_seconds must be positive");
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
  PIBTStyleOneStepResolver resolver(graph, config.hold_seconds);
  PIBTActiveBagReplayResult result;
  std::vector<periodic_detail::ActiveBag> active;
  std::size_t next_task_index = 0;
  double tick_time = selected.empty() ? 0.0 : selected.front().pass_time;

  auto has_open_active = [&active]() {
    return std::any_of(active.begin(), active.end(), [](const auto& bag) { return !bag.closed; });
  };
  auto admit_due_tasks = [&]() {
    while (next_task_index < selected.size() &&
           selected[next_task_index].pass_time <= tick_time + pibt_replay_detail::kEpsilon) {
      const auto& next_task = selected[next_task_index];
      int active_at_start = 0;
      for (const auto& bag : active) {
        if (!bag.closed && bag.current == next_task.start) {
          ++active_at_start;
        }
      }
      if (active_at_start >= pibt_replay_detail::node_capacity(config, next_task.start)) {
        break;
      }
      active.push_back(pibt_replay_detail::admit_bag(graph,
                                                     config,
                                                     node_reservations,
                                                     next_task,
                                                     tick_time,
                                                     result.events));
      ++next_task_index;
    }
  };

  while ((next_task_index < selected.size() || has_open_active()) &&
         result.tick_count < config.max_ticks) {
    if (!has_open_active() && next_task_index < selected.size()) {
      tick_time = std::max(tick_time, selected[next_task_index].pass_time);
      admit_due_tasks();
    }

    int open_count = 0;
    for (auto& bag : active) {
      if (bag.closed) {
        continue;
      }
      ++open_count;
      if (bag.current == bag.task.goal) {
        pibt_replay_detail::close_planned(result, bag, tick_time, -1);
      }
    }
    result.peak_active_bags = std::max(result.peak_active_bags, open_count);

    std::vector<PIBTAgentState> agents;
    std::unordered_map<int, std::size_t> ready_by_task;
    for (std::size_t index = 0; index < active.size(); ++index) {
      const auto& bag = active[index];
      if (bag.closed || bag.current == bag.task.goal ||
          bag.ready_time > tick_time + pibt_replay_detail::kEpsilon) {
        continue;
      }
      agents.push_back(PIBTAgentState{bag.task.task_id,
                                      bag.current,
                                      bag.task.goal,
                                      std::max(tick_time, bag.ready_time),
                                      bag.task.std,
                                      bag.waiting_time});
      ready_by_task[bag.task.task_id] = index;
    }

    if (!agents.empty()) {
      const auto active_faults =
          periodic_detail::active_fault_edges(fault_edges, fault_windows, tick_time);
      const auto actions = resolver.resolve(agents,
                                            &node_reservations,
                                            active_faults,
                                            &edge_reservations,
                                            config.edge_capacity,
                                            config.edge_headway_seconds,
                                            config.node_capacities,
                                            config.merge_groups,
                                            config.merge_capacity,
                                            config.merge_headway_seconds);
      for (const auto& action : actions) {
        auto& bag = active[ready_by_task.at(action.task_id)];
        ++bag.replan_count;
        ++result.decision_count;
        if (action.is_hold()) {
          ++result.hold_count;
          pibt_replay_detail::apply_hold(action,
                                         node_reservations,
                                         bag,
                                         tick_time,
                                         result.events);
        } else {
          ++result.move_count;
          pibt_replay_detail::apply_move(graph,
                                         action,
                                         node_reservations,
                                         edge_reservations,
                                         bag,
                                         tick_time,
                                         config.interval_seconds,
                                         result.events);
          if (bag.current == bag.task.goal) {
            pibt_replay_detail::close_planned(result, bag, tick_time, action.priority_rank);
          }
        }
        if (bag.replan_count >= config.max_ticks && !bag.closed) {
          node_reservations.remove_task(bag.task.task_id);
          edge_reservations.remove_task(bag.task.task_id);
          bag.closed = true;
          ++result.unplanned_count;
        }
      }
    }

    admit_due_tasks();
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
    result.events.push_back(PIBTActiveBagReplayEvent{"unplanned",
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
