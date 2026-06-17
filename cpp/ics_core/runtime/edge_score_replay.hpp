#pragma once

#include <algorithm>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/models/edge_score.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar_types.hpp"
#include "ics_core/shield/junction_shield.hpp"
#include "ics_core/task_stream/task_stream.hpp"

namespace czr005::ics {

struct EdgeScoreReplayConfig {
  std::size_t max_tasks = 8;
  int max_decisions_per_task = 128;
  double hold_seconds = 1.0;
  int edge_capacity = 1;
  double edge_headway_seconds = 0.0;
  bool allow_goal_node_overlap = false;
};

struct EdgeScoreReplayResult {
  int planned_count = 0;
  int unplanned_count = 0;
  int decision_count = 0;
  int shield_blocks = 0;
  int unsafe_proposals = 0;
  int post_shield_conflicts = 0;
  double mean_travel_time = 0.0;
  double makespan = 0.0;
  std::vector<std::vector<PathNode>> routes;
};

namespace detail {

struct RuntimeCandidate {
  int index = -1;
  bool is_hold = false;
  bool safe = false;
  int current = -1;
  int next = -1;
  double edge_start = 0.0;
  double edge_end = 0.0;
  double node_start = 0.0;
  double node_end = 0.0;
  double travel_time = 0.0;
  double service_time = 0.0;
  double heuristic_to_goal = 0.0;
  int blocked_reason_count = 0;
};

inline double clip_scale(double value, double scale, double limit) {
  const double scaled = value / scale;
  return std::max(-limit, std::min(limit, scaled));
}

inline std::vector<double> candidate_features(const TaskLeg& task,
                                              const RuntimeCandidate& candidate,
                                              int goal,
                                              double ready_time,
                                              double waiting_time,
                                              int out_degree) {
  return {
      candidate.is_hold ? 0.0 : 1.0,
      candidate.is_hold ? 1.0 : 0.0,
      candidate.safe ? 1.0 : 0.0,
      clip_scale(candidate.travel_time, 100.0, 50.0),
      clip_scale(candidate.service_time, 10.0, 20.0),
      clip_scale(candidate.heuristic_to_goal, 100.0, 50.0),
      candidate.next == goal ? 1.0 : 0.0,
      clip_scale(task.std - ready_time, 10000.0, 20.0),
      clip_scale(waiting_time, 100.0, 50.0),
      clip_scale(static_cast<double>(out_degree), 10.0, 10.0),
      std::min(candidate.blocked_reason_count, 4) / 4.0,
      clip_scale(candidate.edge_start - ready_time, 100.0, 50.0),
      clip_scale(candidate.node_end - ready_time, 100.0, 50.0),
  };
}

inline RuntimeCandidate make_move_candidate(const Graph& graph,
                                            const JunctionShield& shield,
                                            const TaskLeg& task,
                                            int index,
                                            int current,
                                            int next,
                                            double ready_time,
                                            const ReservationTable& node_reservations,
                                            const EdgeReservationTable& edge_reservations,
                                            const std::set<std::pair<int, int>>& fault_edges) {
  const auto& edge = graph.edge(current, next);
  const double edge_start = ready_time;
  const double edge_end = edge_start + edge.travel_time();
  const double node_start = edge_end;
  const double service_time = graph.service_time(next);
  const double node_end = node_start + service_time;
  const auto decision = shield.validate_edge_action(task.task_id,
                                                    current,
                                                    next,
                                                    task.goal,
                                                    ready_time,
                                                    node_reservations,
                                                    edge_reservations,
                                                    fault_edges);
  return RuntimeCandidate{index,
                          false,
                          decision.allowed(),
                          current,
                          next,
                          edge_start,
                          edge_end,
                          node_start,
                          node_end,
                          edge.travel_time(),
                          service_time,
                          graph.heuristic(next, task.goal),
                          decision.allowed() ? 0 : 1};
}

inline RuntimeCandidate make_hold_candidate(const Graph& graph,
                                            const TaskLeg& task,
                                            int index,
                                            int current,
                                            double ready_time,
                                            double hold_seconds,
                                            const ReservationTable& node_reservations) {
  const bool safe = !node_reservations.has_conflict(current,
                                                    ready_time,
                                                    ready_time + hold_seconds,
                                                    task.task_id);
  return RuntimeCandidate{index,
                          true,
                          safe,
                          current,
                          current,
                          ready_time,
                          ready_time,
                          ready_time,
                          ready_time + hold_seconds,
                          0.0,
                          hold_seconds,
                          graph.heuristic(current, task.goal),
                          safe ? 0 : 1};
}

inline std::vector<RuntimeCandidate> build_candidates(
    const Graph& graph,
    const JunctionShield& shield,
    const TaskLeg& task,
    int current,
    double ready_time,
    const ReservationTable& node_reservations,
    const EdgeReservationTable& edge_reservations,
    const std::set<std::pair<int, int>>& fault_edges,
    double hold_seconds) {
  std::vector<RuntimeCandidate> candidates;
  int index = 0;
  for (const int next : graph.outgoing(current)) {
    candidates.push_back(make_move_candidate(graph,
                                             shield,
                                             task,
                                             index,
                                             current,
                                             next,
                                             ready_time,
                                             node_reservations,
                                             edge_reservations,
                                             fault_edges));
    ++index;
  }
  candidates.push_back(make_hold_candidate(graph,
                                           task,
                                           index,
                                           current,
                                           ready_time,
                                           hold_seconds,
                                           node_reservations));
  return candidates;
}

inline int fallback_candidate_index(const std::vector<RuntimeCandidate>& candidates, int goal) {
  int best = -1;
  for (const auto& candidate : candidates) {
    if (!candidate.safe || candidate.is_hold) {
      continue;
    }
    const auto rank = std::make_pair(candidate.next == goal ? 0 : 1,
                                     std::make_pair(candidate.heuristic_to_goal,
                                                    candidate.travel_time));
    const auto best_rank =
        best < 0 ? std::make_pair(2, std::make_pair(0.0, 0.0))
                 : std::make_pair(candidates[static_cast<std::size_t>(best)].next == goal ? 0 : 1,
                                  std::make_pair(candidates[static_cast<std::size_t>(best)].heuristic_to_goal,
                                                 candidates[static_cast<std::size_t>(best)].travel_time));
    if (best < 0 || rank < best_rank) {
      best = candidate.index;
    }
  }
  if (best >= 0) {
    return best;
  }
  for (const auto& candidate : candidates) {
    if (candidate.safe) {
      return candidate.index;
    }
  }
  return -1;
}

inline double earliest_safe_node_start(const ReservationTable& reservations,
                                       int task_id,
                                       int node,
                                       double earliest_start,
                                       double duration,
                                       double step_seconds) {
  double candidate = earliest_start;
  for (int attempt = 0; attempt < 10000; ++attempt) {
    if (!reservations.has_conflict(node, candidate, candidate + duration, task_id)) {
      return candidate;
    }
    candidate += step_seconds;
  }
  throw std::runtime_error("failed to find safe node start");
}

}  // namespace detail

inline EdgeScoreReplayResult run_edge_score_replay_with_optional_model(
    const Graph& graph,
    const TaskStream& tasks,
    const EdgeScoreModel* model,
    const EdgeScoreReplayConfig& config = {},
    const std::set<std::pair<int, int>>& fault_edges = {}) {
  if (config.hold_seconds <= 0.0) {
    throw std::invalid_argument("hold_seconds must be positive");
  }
  if (config.edge_capacity <= 0) {
    throw std::invalid_argument("edge_capacity must be positive");
  }
  if (config.max_decisions_per_task <= 0) {
    throw std::invalid_argument("max_decisions_per_task must be positive");
  }

  ReservationTable node_reservations;
  EdgeReservationTable edge_reservations;
  JunctionShieldConfig shield_config;
  shield_config.edge_capacity = config.edge_capacity;
  shield_config.edge_headway_seconds = config.edge_headway_seconds;
  shield_config.allow_goal_node_overlap = config.allow_goal_node_overlap;
  const JunctionShield shield(graph, shield_config);

  EdgeScoreReplayResult result;
  const std::size_t limit = std::min(config.max_tasks, tasks.size());
  for (std::size_t task_index = 0; task_index < limit; ++task_index) {
    const auto& task = tasks.tasks()[task_index];
    const double start_duration = graph.service_time(task.start);
    const double start_time = detail::earliest_safe_node_start(node_reservations,
                                                              task.task_id,
                                                              task.start,
                                                              task.pass_time,
                                                              start_duration,
                                                              config.hold_seconds);
    std::vector<PathNode> route;
    route.push_back(PathNode{task.start,
                             start_time,
                             start_time + start_duration,
                             start_time,
                             graph.heuristic(task.start, task.goal),
                             start_time + graph.heuristic(task.start, task.goal)});
    node_reservations.reserve(task.task_id, task.start, route.back().t1, route.back().t2);

    int current = task.start;
    double ready_time = route.back().t2;
    double waiting_time = std::max(0.0, start_time - task.pass_time);
    bool planned = current == task.goal;
    bool counted_unplanned = false;

    for (int decision = 0; decision < config.max_decisions_per_task && !planned; ++decision) {
      const auto candidates = detail::build_candidates(graph,
                                                       shield,
                                                       task,
                                                       current,
                                                       ready_time,
                                                       node_reservations,
                                                       edge_reservations,
                                                       fault_edges,
                                                       config.hold_seconds);
      std::vector<std::vector<double>> features;
      std::vector<bool> mask;
      features.reserve(candidates.size());
      mask.reserve(candidates.size());
      for (const auto& candidate : candidates) {
        features.push_back(detail::candidate_features(task,
                                                      candidate,
                                                      task.goal,
                                                      ready_time,
                                                      waiting_time,
                                                      static_cast<int>(graph.outgoing(current).size())));
        mask.push_back(candidate.safe);
      }

      int chosen_position = -1;
      if (model == nullptr) {
        chosen_position = detail::fallback_candidate_index(candidates, task.goal);
      } else {
        try {
          chosen_position = model->predict(features, mask);
        } catch (const std::invalid_argument&) {
          chosen_position = detail::fallback_candidate_index(candidates, task.goal);
        }
      }
      if (chosen_position < 0 || static_cast<std::size_t>(chosen_position) >= candidates.size()) {
        ++result.unplanned_count;
        counted_unplanned = true;
        break;
      }

      const auto& chosen = candidates[static_cast<std::size_t>(chosen_position)];
      if (!chosen.safe) {
        ++result.unsafe_proposals;
        chosen_position = detail::fallback_candidate_index(candidates, task.goal);
        if (chosen_position < 0) {
          ++result.unplanned_count;
          counted_unplanned = true;
          break;
        }
      }

      const auto& executed = candidates[static_cast<std::size_t>(chosen_position)];
      if (chosen_position != executed.index) {
        ++result.shield_blocks;
      }
      ++result.decision_count;

      if (executed.is_hold) {
        waiting_time += executed.node_end - ready_time;
        route.back().t2 = executed.node_end;
        route.back().gcost = executed.node_end;
        route.back().fcost = route.back().gcost + route.back().hcost;
        node_reservations.reserve(task.task_id, current, route.back().t1, route.back().t2);
        ready_time = executed.node_end;
        continue;
      }

      edge_reservations.reserve(task.task_id,
                                current,
                                executed.next,
                                executed.edge_start,
                                executed.edge_end);
      node_reservations.reserve(task.task_id,
                                executed.next,
                                executed.node_start,
                                executed.node_end);
      route.push_back(PathNode{executed.next,
                               executed.node_start,
                               executed.node_end,
                               executed.node_start,
                               executed.heuristic_to_goal,
                               executed.node_start + executed.heuristic_to_goal});
      current = executed.next;
      ready_time = executed.node_end;
      planned = current == task.goal;
    }

    if (planned) {
      ++result.planned_count;
      result.routes.push_back(route);
      result.makespan = std::max(result.makespan, route.back().t2);
      result.mean_travel_time += route.back().t2 - route.front().t1;
    } else if (!counted_unplanned) {
      ++result.unplanned_count;
    }
  }

  if (result.planned_count > 0) {
    result.mean_travel_time /= static_cast<double>(result.planned_count);
  }
  result.post_shield_conflicts =
      node_reservations.conflict_count() +
      edge_reservations.conflict_count(config.edge_capacity, config.edge_headway_seconds);
  return result;
}

inline EdgeScoreReplayResult run_edge_score_replay(
    const Graph& graph,
    const TaskStream& tasks,
    const EdgeScoreModel& model,
    const EdgeScoreReplayConfig& config = {},
    const std::set<std::pair<int, int>>& fault_edges = {}) {
  return run_edge_score_replay_with_optional_model(graph, tasks, &model, config, fault_edges);
}

inline EdgeScoreReplayResult run_edge_score_fallback_replay(
    const Graph& graph,
    const TaskStream& tasks,
    const EdgeScoreReplayConfig& config = {},
    const std::set<std::pair<int, int>>& fault_edges = {}) {
  return run_edge_score_replay_with_optional_model(graph, tasks, nullptr, config, fault_edges);
}

}  // namespace czr005::ics
