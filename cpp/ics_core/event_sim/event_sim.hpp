#pragma once

#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/metrics/metrics.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar.hpp"
#include "ics_core/routing/astar_types.hpp"
#include "ics_core/task_stream/task_stream.hpp"

namespace czr005::ics {

struct ReferenceSimEvent {
  std::string event;
  std::string segment_id;
  int task_id = -1;
  int start = -1;
  int goal = -1;
  double entry_time = 0.0;
  double finish_time = 0.0;
  std::vector<int> path;
};

struct ReferenceEpisodeResult {
  std::vector<std::pair<std::string, std::vector<PathNode>>> routes;
  std::vector<TaskLeg> unplanned;
  std::vector<ReferenceSimEvent> events;
  EpisodeMetrics metrics;
};

class ReferenceSimulator {
 public:
  explicit ReferenceSimulator(const Graph& graph) : graph_(graph), planner_(graph) {}

  [[nodiscard]] const ReservationTable& reservations() const { return reservations_; }

  ReferenceEpisodeResult run_episode(
      const TaskStream& tasks,
      std::optional<int> max_tasks = std::nullopt,
      std::optional<double> end_time = std::nullopt,
      const std::set<std::pair<int, int>>& fault_edges = {}) {
    ReferenceEpisodeResult result;
    int considered_tasks = 0;

    for (const auto& task : tasks.tasks()) {
      if (end_time.has_value() && task.pass_time > *end_time) {
        continue;
      }
      if (max_tasks.has_value() && considered_tasks >= *max_tasks) {
        break;
      }

      auto route = planner_.plan(
          task.start,
          task.goal,
          task.pass_time,
          &reservations_,
          fault_edges,
          task.task_id);

      if (!route.empty()) {
        reservations_.add_route(task.task_id, route);
        result.events.push_back(ReferenceSimEvent{"planned",
                                                  task.segment_id,
                                                  task.task_id,
                                                  task.start,
                                                  task.goal,
                                                  task.pass_time,
                                                  route.back().t2,
                                                  route_locations(route)});
        result.routes.push_back({task.segment_id, std::move(route)});
      } else {
        result.unplanned.push_back(task);
        result.events.push_back(ReferenceSimEvent{"unplanned",
                                                  task.segment_id,
                                                  task.task_id,
                                                  task.start,
                                                  task.goal,
                                                  task.pass_time,
                                                  0.0,
                                                  {}});
      }
      ++considered_tasks;
    }

    std::vector<std::vector<PathNode>> metric_routes;
    metric_routes.reserve(result.routes.size());
    for (const auto& route_entry : result.routes) {
      metric_routes.push_back(route_entry.second);
    }
    result.metrics = compute_episode_metrics(
        metric_routes,
        static_cast<int>(result.unplanned.size()),
        reservations_);
    return result;
  }

 private:
  static std::vector<int> route_locations(const std::vector<PathNode>& route) {
    std::vector<int> locations;
    locations.reserve(route.size());
    for (const auto& node : route) {
      locations.push_back(node.location);
    }
    return locations;
  }

  const Graph& graph_;
  AStarPlanner planner_;
  ReservationTable reservations_;
};

}  // namespace czr005::ics
