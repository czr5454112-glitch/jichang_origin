#pragma once

#include <algorithm>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar.hpp"
#include "ics_core/shield/junction_shield.hpp"

namespace czr005::ics {

struct PIBTAgentState {
  int task_id = -1;
  int current = -1;
  int goal = -1;
  double ready_time = 0.0;
  double deadline = 0.0;
  double waiting_time = 0.0;

  [[nodiscard]] double slack() const { return deadline - ready_time; }
};

struct PIBTResolvedAction {
  int task_id = -1;
  std::string action;
  int current = -1;
  int next_node = -1;
  double edge_start = 0.0;
  double edge_end = 0.0;
  double node_start = 0.0;
  double node_end = 0.0;
  std::string reason;
  int priority_rank = -1;

  [[nodiscard]] bool is_hold() const { return action == "hold"; }
};

class PIBTStyleOneStepResolver {
 public:
  explicit PIBTStyleOneStepResolver(const Graph& graph, double hold_seconds = 1.0)
      : graph_(graph), hold_seconds_(hold_seconds), astar_(graph) {
    if (hold_seconds <= 0.0) {
      throw std::invalid_argument("hold_seconds must be positive");
    }
  }

  [[nodiscard]] std::vector<PIBTResolvedAction> resolve(
      std::vector<PIBTAgentState> agents,
      const ReservationTable* reservations = nullptr,
      const std::set<std::pair<int, int>>& fault_edges = {},
      const EdgeReservationTable* edge_reservations = nullptr,
      int edge_capacity = 1,
      double edge_headway_seconds = 0.0,
      const std::unordered_map<int, int>& node_capacities = {},
      const std::vector<MergeGroupEdge>& merge_groups = {},
      int merge_capacity = 1,
      double merge_headway_seconds = 0.0) const {
    if (edge_capacity <= 0) {
      throw std::invalid_argument("edge_capacity must be positive");
    }
    if (merge_capacity <= 0) {
      throw std::invalid_argument("merge_capacity must be positive");
    }
    const ReservationTable empty_reservations;
    const ReservationTable& node_reservations =
        reservations == nullptr ? empty_reservations : *reservations;
    const EdgeReservationTable empty_edge_reservations;
    const EdgeReservationTable& edge_table =
        edge_reservations == nullptr ? empty_edge_reservations : *edge_reservations;

    std::sort(agents.begin(), agents.end(), [](const PIBTAgentState& left,
                                               const PIBTAgentState& right) {
      if (left.slack() != right.slack()) {
        return left.slack() < right.slack();
      }
      if (left.waiting_time != right.waiting_time) {
        return left.waiting_time > right.waiting_time;
      }
      if (left.ready_time != right.ready_time) {
        return left.ready_time < right.ready_time;
      }
      return left.task_id < right.task_id;
    });

    std::unordered_map<int, int> priority_ranks;
    std::unordered_map<int, PIBTAgentState> agents_by_task;
    std::unordered_map<int, int> current_owner;
    for (std::size_t index = 0; index < agents.size(); ++index) {
      priority_ranks[agents[index].task_id] = static_cast<int>(index);
      agents_by_task[agents[index].task_id] = agents[index];
      current_owner.emplace(agents[index].current, agents[index].task_id);
    }

    std::unordered_map<int, PIBTResolvedAction> chosen_by_task;
    std::vector<LocalNodeWindow> local_node_windows;
    local_node_windows.reserve(agents.size());
    std::vector<LocalEdgeWindow> local_edge_windows;
    local_edge_windows.reserve(agents.size());
    std::set<std::pair<int, int>> local_edges;

    for (const auto& agent : agents) {
      if (chosen_by_task.find(agent.task_id) != chosen_by_task.end()) {
        continue;
      }
      std::unordered_set<int> blocked_targets;
      std::unordered_set<int> visiting;
      const bool assigned = assign_recursive(agent,
                                             priority_ranks.at(agent.task_id),
                                             node_reservations,
                                             edge_table,
                                             edge_capacity,
                                             edge_headway_seconds,
                                             node_capacities,
                                             merge_groups,
                                             merge_capacity,
                                             merge_headway_seconds,
                                             fault_edges,
                                             agents_by_task,
                                             current_owner,
                                             priority_ranks,
                                             chosen_by_task,
                                             local_node_windows,
                                             local_edge_windows,
                                             local_edges,
                                             blocked_targets,
                                             false,
                                             visiting);
      if (!assigned) {
        throw std::logic_error("top-level PIBT assignment failed");
      }
    }

    std::vector<PIBTResolvedAction> chosen;
    chosen.reserve(agents.size());
    for (const auto& agent : agents) {
      chosen.push_back(chosen_by_task.at(agent.task_id));
    }
    return chosen;
  }

 private:
  struct LocalNodeWindow {
    int node = -1;
    double start = 0.0;
    double end = 0.0;
    int task_id = -1;
  };

  struct LocalEdgeWindow {
    int start_node = -1;
    int end_node = -1;
    double start = 0.0;
    double end = 0.0;
    int task_id = -1;
  };

  [[nodiscard]] bool assign_recursive(
      const PIBTAgentState& agent,
      int priority_rank,
      const ReservationTable& reservations,
      const EdgeReservationTable& edge_reservations,
      int edge_capacity,
      double edge_headway_seconds,
      const std::unordered_map<int, int>& node_capacities,
      const std::vector<MergeGroupEdge>& merge_groups,
      int merge_capacity,
      double merge_headway_seconds,
      const std::set<std::pair<int, int>>& fault_edges,
      const std::unordered_map<int, PIBTAgentState>& agents_by_task,
      const std::unordered_map<int, int>& current_owner,
      const std::unordered_map<int, int>& priority_ranks,
      std::unordered_map<int, PIBTResolvedAction>& chosen_by_task,
      std::vector<LocalNodeWindow>& local_node_windows,
      std::vector<LocalEdgeWindow>& local_edge_windows,
      std::set<std::pair<int, int>>& local_edges,
      const std::unordered_set<int>& blocked_targets,
      bool inherited,
      std::unordered_set<int>& visiting) const {
    const auto assigned = chosen_by_task.find(agent.task_id);
    if (assigned != chosen_by_task.end()) {
      return assigned->second.action == "move";
    }
    if (visiting.find(agent.task_id) != visiting.end()) {
      return false;
    }

    visiting.insert(agent.task_id);
    for (const int next_node : candidate_edges(agent)) {
      if (blocked_targets.find(next_node) != blocked_targets.end()) {
        continue;
      }
      if (fault_edges.find({agent.current, next_node}) != fault_edges.end()) {
        continue;
      }
      if (local_edges.find({agent.current, next_node}) != local_edges.end()) {
        continue;
      }
      if (!reachable_after_step(next_node, agent.goal, fault_edges)) {
        continue;
      }

      const auto& edge = graph_.edge(agent.current, next_node);
      const double edge_start = agent.ready_time;
      const double edge_end = edge_start + edge.travel_time();
      const double node_start = edge_end;
      const double node_end = node_start + graph_.service_time(next_node);

      if (edge_reservations.has_capacity_conflict(agent.current,
                                                  next_node,
                                                  edge_start,
                                                  edge_end,
                                                  edge_capacity,
                                                  agent.task_id)) {
        continue;
      }
      if (edge_reservations.has_headway_conflict(agent.current,
                                                 next_node,
                                                 edge_start,
                                                 edge_headway_seconds,
                                                 agent.task_id)) {
        continue;
      }
      if (edge_reservations.has_merge_group_conflict(agent.current,
                                                     next_node,
                                                     edge_start,
                                                     edge_end,
                                                     merge_groups,
                                                     merge_capacity,
                                                     merge_headway_seconds,
                                                     agent.task_id)) {
        continue;
      }
      if (local_merge_group_conflict(agent.current,
                                     next_node,
                                     edge_start,
                                     edge_end,
                                     agent.task_id,
                                     local_edge_windows,
                                     merge_groups,
                                     merge_capacity,
                                     merge_headway_seconds)) {
        continue;
      }

      if (next_node != agent.goal &&
          reservations.has_capacity_conflict(next_node,
                                             node_start,
                                             node_end,
                                             node_capacity(node_capacities, next_node),
                                             agent.task_id)) {
        continue;
      }
      if (local_node_conflict(next_node,
                              node_start,
                              node_end,
                              agent.task_id,
                              local_node_windows)) {
        continue;
      }

      bool inherited_move = false;
      const auto blocker_found = current_owner.find(next_node);
      if (blocker_found != current_owner.end() && blocker_found->second != agent.task_id) {
        const int blocker_id = blocker_found->second;
        auto blocker_action = chosen_by_task.find(blocker_id);
        if (blocker_action == chosen_by_task.end()) {
          const auto blocker = agents_by_task.at(blocker_id);
          const std::unordered_set<int> blocker_blocked_targets{agent.current, next_node};
          if (!assign_recursive(blocker,
                                priority_ranks.at(blocker.task_id),
                                reservations,
                                edge_reservations,
                                edge_capacity,
                                edge_headway_seconds,
                                node_capacities,
                                merge_groups,
                                merge_capacity,
                                merge_headway_seconds,
                                fault_edges,
                                agents_by_task,
                                current_owner,
                                priority_ranks,
                                chosen_by_task,
                                local_node_windows,
                                local_edge_windows,
                                local_edges,
                                blocker_blocked_targets,
                                true,
                                visiting)) {
            continue;
          }
          blocker_action = chosen_by_task.find(blocker_id);
          inherited_move = true;
        }
        if (blocker_action == chosen_by_task.end() ||
            blocker_action->second.is_hold() ||
            blocker_action->second.next_node == next_node ||
            blocker_action->second.edge_start > node_start) {
          continue;
        }
        if (local_edges.find({agent.current, next_node}) != local_edges.end()) {
          continue;
        }
        if (local_merge_group_conflict(agent.current,
                                       next_node,
                                       edge_start,
                                       edge_end,
                                       agent.task_id,
                                       local_edge_windows,
                                       merge_groups,
                                       merge_capacity,
                                       merge_headway_seconds)) {
          continue;
        }
        if (local_node_conflict(next_node,
                                node_start,
                                node_end,
                                agent.task_id,
                                local_node_windows)) {
          continue;
        }
      }

      const std::string reason =
          inherited_move ? "priority_inheritance" : (inherited ? "inherited_move" : "best_safe_edge");
      chosen_by_task[agent.task_id] = PIBTResolvedAction{agent.task_id,
                                                         "move",
                                                         agent.current,
                                                         next_node,
                                                         edge_start,
                                                         edge_end,
                                                         node_start,
                                                         node_end,
                                                         reason,
                                                         priority_rank};
      local_node_windows.push_back(LocalNodeWindow{next_node, node_start, node_end, agent.task_id});
      local_edge_windows.push_back(LocalEdgeWindow{agent.current,
                                                   next_node,
                                                   edge_start,
                                                   edge_end,
                                                   agent.task_id});
      local_edges.insert({agent.current, next_node});
      visiting.erase(agent.task_id);
      return true;
    }

    visiting.erase(agent.task_id);
    if (inherited) {
      return false;
    }
    chosen_by_task[agent.task_id] = PIBTResolvedAction{agent.task_id,
                                                       "hold",
                                                       agent.current,
                                                       agent.current,
                                                       agent.ready_time,
                                                       agent.ready_time,
                                                       agent.ready_time,
                                                       agent.ready_time + hold_seconds_,
                                                       "no_safe_edge",
                                                       priority_rank};
    local_node_windows.push_back(LocalNodeWindow{
        agent.current, agent.ready_time, agent.ready_time + hold_seconds_, agent.task_id});
    return true;
  }

  [[nodiscard]] std::vector<int> candidate_edges(const PIBTAgentState& agent) const {
    std::vector<int> candidates = graph_.outgoing(agent.current);
    std::sort(candidates.begin(), candidates.end(), [this, &agent](int left, int right) {
      const double left_heuristic = graph_.heuristic(left, agent.goal);
      const double right_heuristic = graph_.heuristic(right, agent.goal);
      if (left_heuristic != right_heuristic) {
        return left_heuristic < right_heuristic;
      }
      const double left_travel_time = graph_.edge(agent.current, left).travel_time();
      const double right_travel_time = graph_.edge(agent.current, right).travel_time();
      if (left_travel_time != right_travel_time) {
        return left_travel_time < right_travel_time;
      }
      return left < right;
    });
    return candidates;
  }

  [[nodiscard]] bool reachable_after_step(
      int next_node,
      int goal,
      const std::set<std::pair<int, int>>& fault_edges) const {
    if (next_node == goal) {
      return true;
    }
    return !astar_.plan(next_node, goal, 0.0, nullptr, fault_edges).empty();
  }

  [[nodiscard]] static int node_capacity(
      const std::unordered_map<int, int>& node_capacities,
      int node) {
    const auto found = node_capacities.find(node);
    return found == node_capacities.end() ? 1 : found->second;
  }

  [[nodiscard]] static bool local_node_conflict(
      int node,
      double start,
      double end,
      int task_id,
      const std::vector<LocalNodeWindow>& local_windows) {
    for (const auto& window : local_windows) {
      if (window.node != node || window.task_id == task_id) {
        continue;
      }
      if (!(start > window.end || end < window.start)) {
        return true;
      }
    }
    return false;
  }

  [[nodiscard]] static int merge_group(
      int start_node,
      int end_node,
      const std::vector<MergeGroupEdge>& merge_groups) {
    for (const auto& edge : merge_groups) {
      if (edge.start_node == start_node && edge.end_node == end_node) {
        return edge.group;
      }
    }
    return -1;
  }

  [[nodiscard]] static bool local_merge_group_conflict(
      int start_node,
      int end_node,
      double start,
      double end,
      int task_id,
      const std::vector<LocalEdgeWindow>& local_windows,
      const std::vector<MergeGroupEdge>& merge_groups,
      int merge_capacity,
      double merge_headway_seconds) {
    const int group = merge_group(start_node, end_node, merge_groups);
    if (group < 0) {
      return false;
    }
    int overlapping = 0;
    for (const auto& window : local_windows) {
      if (window.task_id == task_id) {
        continue;
      }
      if (merge_group(window.start_node, window.end_node, merge_groups) != group) {
        continue;
      }
      if (!(start >= window.end - 1.0e-9 || end <= window.start + 1.0e-9)) {
        ++overlapping;
      }
      const double gap = window.start > start ? window.start - start : start - window.start;
      if (merge_headway_seconds > 0.0 && gap < merge_headway_seconds) {
        return true;
      }
    }
    return overlapping >= merge_capacity;
  }

  const Graph& graph_;
  double hold_seconds_;
  AStarPlanner astar_;
};

}  // namespace czr005::ics
