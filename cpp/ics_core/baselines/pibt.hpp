#pragma once

#include <algorithm>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar.hpp"

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
      const std::set<std::pair<int, int>>& fault_edges = {}) const {
    const ReservationTable empty_reservations;
    const ReservationTable& node_reservations =
        reservations == nullptr ? empty_reservations : *reservations;

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

    std::vector<PIBTResolvedAction> chosen;
    chosen.reserve(agents.size());
    std::vector<LocalNodeWindow> local_node_windows;
    local_node_windows.reserve(agents.size());
    std::set<std::pair<int, int>> local_edges;

    for (std::size_t index = 0; index < agents.size(); ++index) {
      const auto action = choose_action(agents[index],
                                        static_cast<int>(index),
                                        node_reservations,
                                        fault_edges,
                                        local_node_windows,
                                        local_edges);
      chosen.push_back(action);
      local_node_windows.push_back(LocalNodeWindow{
          action.next_node, action.node_start, action.node_end, action.task_id});
      if (action.action == "move") {
        local_edges.insert({action.current, action.next_node});
      }
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

  [[nodiscard]] PIBTResolvedAction choose_action(
      const PIBTAgentState& agent,
      int priority_rank,
      const ReservationTable& reservations,
      const std::set<std::pair<int, int>>& fault_edges,
      const std::vector<LocalNodeWindow>& local_node_windows,
      const std::set<std::pair<int, int>>& local_edges) const {
    for (const int next_node : candidate_edges(agent)) {
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

      if (next_node != agent.goal &&
          reservations.has_conflict(next_node, node_start, node_end, agent.task_id)) {
        continue;
      }
      if (local_node_conflict(next_node,
                              node_start,
                              node_end,
                              agent.task_id,
                              local_node_windows)) {
        continue;
      }

      return PIBTResolvedAction{agent.task_id,
                                "move",
                                agent.current,
                                next_node,
                                edge_start,
                                edge_end,
                                node_start,
                                node_end,
                                "best_safe_edge",
                                priority_rank};
    }

    return PIBTResolvedAction{agent.task_id,
                              "hold",
                              agent.current,
                              agent.current,
                              agent.ready_time,
                              agent.ready_time,
                              agent.ready_time,
                              agent.ready_time + hold_seconds_,
                              "no_safe_edge",
                              priority_rank};
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

  const Graph& graph_;
  double hold_seconds_;
  AStarPlanner astar_;
};

}  // namespace czr005::ics
