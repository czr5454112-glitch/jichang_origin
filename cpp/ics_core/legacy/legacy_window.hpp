#pragma once

#include <algorithm>
#include <deque>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/reservation/reservation.hpp"
#include "ics_core/routing/astar.hpp"
#include "ics_core/routing/astar_types.hpp"
#include "ics_core/task_stream/task_stream.hpp"

namespace czr005::ics {

struct LegacyWindowPlannedRoute {
  int ordinal = 0;
  int task_id = -1;
  int start = -1;
  int goal = -1;
  double epoch = 0.0;
  double finish_time = 0.0;
  std::vector<int> path;
};

struct LegacyWindowFaultEvent {
  int epoch = 0;
  int start = -1;
  int end = -1;
  bool repair = false;
};

struct LegacyNoFaultWindowResult {
  int start_epoch = 0;
  int max_epochs = 0;
  int max_new_tasks = 0;
  int epochs_run = 0;
  int generated_count = 0;
  int planned_count = 0;
  int completed_count = 0;
  int fault_event_count = 0;
  int repair_event_count = 0;
  int generated_fault_edge_count = 0;
  int generated_repair_edge_count = 0;
  int active_fault_count = 0;
  int unplanned_retry_count = 0;
  int active_route_count = 0;
  int unfinished_count = 0;
  long long route_size_checksum = 0;
  long long route_location_checksum = 0;
  double last_epoch = 0.0;
  std::vector<LegacyWindowPlannedRoute> planned_routes;
};

namespace legacy_window_detail {

inline bool blank_line(const std::string& line) {
  return line.find_first_not_of(" \t\r\n") == std::string::npos;
}

inline TaskLeg make_window_task(int task_id,
                                double entry_time,
                                double std_time,
                                int original_start,
                                int original_goal,
                                int source_line,
                                const std::string& leg,
                                bool early_bag_split,
                                double pass_time,
                                int start,
                                int goal) {
  TaskLeg task;
  task.segment_id = std::to_string(task_id) + ":" + leg;
  task.task_id = task_id;
  task.pallet_id = task_id;
  task.pass_time = pass_time;
  task.std = std_time;
  task.start = start;
  task.goal = goal;
  task.original_start = original_start;
  task.original_goal = original_goal;
  task.original_entry_time = entry_time;
  task.leg = leg;
  task.early_bag_split = early_bag_split;
  task.source_line = source_line;
  return task;
}

inline std::map<int, std::deque<TaskLeg>> read_java_style_task_groups(
    const std::string& path,
    double early_bag_threshold = 4800.0,
    int storage_in_goal = 47,
    int storage_out_start = 52,
    double storage_out_lead_seconds = 2700.0) {
  std::ifstream input(path);
  if (!input) {
    throw std::runtime_error("failed to open legacy inputdata: " + path);
  }

  std::string line;
  if (!std::getline(input, line)) {
    throw std::runtime_error("empty legacy inputdata: " + path);
  }

  std::map<int, std::vector<TaskLeg>> grouped;
  int line_no = 1;
  while (std::getline(input, line)) {
    ++line_no;
    if (blank_line(line)) {
      continue;
    }
    std::istringstream stream(line);
    int task_id = -1;
    double entry_time = 0.0;
    double std_time = 0.0;
    int start = -1;
    int goal = -1;
    stream >> task_id >> entry_time >> std_time >> start >> goal;
    if (!stream) {
      throw std::runtime_error("invalid legacy inputdata row at line " + std::to_string(line_no));
    }

    if (std_time - entry_time < early_bag_threshold) {
      grouped[start].push_back(make_window_task(task_id,
                                                entry_time,
                                                std_time,
                                                start,
                                                goal,
                                                line_no,
                                                "direct",
                                                false,
                                                entry_time,
                                                start,
                                                goal));
    } else {
      grouped[start].push_back(make_window_task(task_id,
                                                entry_time,
                                                std_time,
                                                start,
                                                goal,
                                                line_no,
                                                "storage_in",
                                                true,
                                                entry_time,
                                                start,
                                                storage_in_goal));
      grouped[storage_out_start].push_back(make_window_task(task_id,
                                                            entry_time,
                                                            std_time,
                                                            start,
                                                            goal,
                                                            line_no,
                                                            "storage_out",
                                                            true,
                                                            std_time - storage_out_lead_seconds,
                                                            storage_out_start,
                                                            goal));
    }
  }

  std::map<int, std::deque<TaskLeg>> queues;
  for (auto& entry : grouped) {
    auto& tasks = entry.second;
    std::stable_sort(tasks.begin(), tasks.end(), [](const TaskLeg& left, const TaskLeg& right) {
      return static_cast<int>(left.pass_time - right.pass_time) < 0;
    });
    queues.emplace(entry.first, std::deque<TaskLeg>(tasks.begin(), tasks.end()));
  }
  return queues;
}

inline std::vector<int> start_nodes_from_task_groups(const std::map<int, std::deque<TaskLeg>>& groups) {
  std::vector<int> starts;
  starts.reserve(groups.size());
  for (const auto& entry : groups) {
    starts.push_back(entry.first);
  }
  return starts;
}

inline bool contains_unfinished_start(const std::deque<TaskLeg>& tasks, int start) {
  return std::any_of(tasks.begin(), tasks.end(), [start](const TaskLeg& task) {
    return task.start == start;
  });
}

inline std::vector<int> route_locations(const std::vector<PathNode>& route) {
  std::vector<int> locations;
  locations.reserve(route.size());
  for (const auto& node : route) {
    locations.push_back(node.location);
  }
  return locations;
}

inline void add_checksum(LegacyNoFaultWindowResult& result, const std::vector<PathNode>& route) {
  result.route_size_checksum += static_cast<long long>(route.size());
  for (std::size_t index = 0; index < route.size(); ++index) {
    result.route_location_checksum +=
        static_cast<long long>(index + 1) * static_cast<long long>(route[index].location + 1);
  }
}

inline bool deterministic_probability(double probability) {
  return probability == 0.0 || probability == 1.0;
}

inline std::vector<std::pair<int, int>> graph_edges(const Graph& graph) {
  std::vector<std::pair<int, int>> edges;
  for (int location = 0; location < static_cast<int>(graph.node_count()); ++location) {
    for (const int next : graph.outgoing(location)) {
      edges.push_back({location, next});
    }
  }
  return edges;
}

}  // namespace legacy_window_detail

inline LegacyNoFaultWindowResult run_legacy_no_fault_window(
    const Graph& graph,
    std::map<int, std::deque<TaskLeg>> task_groups,
    int start_epoch,
    int max_epochs,
    int max_new_tasks,
    const std::vector<LegacyWindowFaultEvent>& fault_schedule = {},
    double fault_probability = 0.0,
    double repair_probability = 0.0) {
  if (max_epochs <= 0) {
    throw std::invalid_argument("max_epochs must be positive");
  }
  if (max_new_tasks < 0) {
    throw std::invalid_argument("max_new_tasks must be non-negative");
  }
  if (!legacy_window_detail::deterministic_probability(fault_probability) ||
      !legacy_window_detail::deterministic_probability(repair_probability)) {
    throw std::invalid_argument("legacy window only supports deterministic probabilities 0.0 or 1.0");
  }

  LegacyNoFaultWindowResult result;
  result.start_epoch = start_epoch;
  result.max_epochs = max_epochs;
  result.max_new_tasks = max_new_tasks;

  const auto start_nodes = legacy_window_detail::start_nodes_from_task_groups(task_groups);
  const auto graph_edges = legacy_window_detail::graph_edges(graph);
  AStarPlanner planner(graph);
  std::map<int, std::vector<PathNode>> saved_routes;
  std::deque<TaskLeg> unfinished;
  std::set<std::pair<int, int>> active_fault_edges;
  std::set<std::pair<int, int>> auto_repair_fault_edges;

  for (int epoch_index = 0; epoch_index < max_epochs; ++epoch_index) {
    const double epoch = static_cast<double>(start_epoch + epoch_index);
    const int epoch_int = start_epoch + epoch_index;
    result.last_epoch = epoch;
    result.epochs_run = epoch_index + 1;

    std::set<std::pair<int, int>> epoch_fault_edges;
    for (const auto& event : fault_schedule) {
      if (event.epoch != epoch_int) {
        continue;
      }
      if (event.repair) {
        active_fault_edges.erase({event.start, event.end});
        auto_repair_fault_edges.erase({event.start, event.end});
        ++result.repair_event_count;
      } else {
        const auto edge = std::pair<int, int>{event.start, event.end};
        active_fault_edges.insert(edge);
        epoch_fault_edges.insert(edge);
        ++result.fault_event_count;
      }
    }

    std::set<std::pair<int, int>> probability_fault_edges;
    if (fault_probability == 1.0) {
      for (const auto& edge : graph_edges) {
        if (active_fault_edges.find(edge) == active_fault_edges.end()) {
          probability_fault_edges.insert(edge);
        }
      }
    }
    for (const auto& edge : probability_fault_edges) {
      epoch_fault_edges.insert(edge);
    }
    result.generated_fault_edge_count += static_cast<int>(epoch_fault_edges.size());

    std::set<std::pair<int, int>> epoch_repair_edges;
    if (repair_probability == 1.0) {
      epoch_repair_edges = active_fault_edges;
    } else {
      epoch_repair_edges = auto_repair_fault_edges;
    }
    result.generated_repair_edge_count += static_cast<int>(epoch_repair_edges.size());
    for (const auto& edge : epoch_repair_edges) {
      active_fault_edges.erase(edge);
      auto_repair_fault_edges.erase(edge);
    }

    struct OnPathTask {
      int task_id = -1;
      int goal = -1;
      int passed_vertex = -1;
    };
    std::vector<OnPathTask> on_path;
    std::unordered_set<int> on_path_ids;

    for (const auto& entry : saved_routes) {
      const auto& route = entry.second;
      if (route.size() < 2 || epoch < route[1].t1) {
        continue;
      }
      const int goal = route.back().location;
      const int passed = route[1].location;
      on_path.push_back(OnPathTask{entry.first, goal, passed});
      on_path_ids.insert(entry.first);
    }

    ReservationTable reservations;
    for (const auto& active : on_path) {
      auto found = saved_routes.find(active.task_id);
      if (found == saved_routes.end()) {
        continue;
      }
      if (active.passed_vertex == active.goal) {
        saved_routes.erase(found);
        ++result.completed_count;
        continue;
      }
      auto& route = found->second;
      while (!route.empty() && route.front().location != active.passed_vertex) {
        route.erase(route.begin());
      }
      if (!route.empty()) {
        reservations.add_route(active.task_id, route);
      }
    }

    for (const auto& entry : saved_routes) {
      if (on_path_ids.find(entry.first) == on_path_ids.end()) {
        reservations.add_route(entry.first, entry.second);
      }
    }

    for (const auto& edge : epoch_fault_edges) {
      active_fault_edges.insert(edge);
    }
    for (const auto& edge : probability_fault_edges) {
      auto_repair_fault_edges.insert(edge);
    }

    std::vector<int> faulted_route_ids;
    for (const auto& entry : saved_routes) {
      const auto& route = entry.second;
      if (route.size() < 2) {
        continue;
      }
      if (epoch_fault_edges.find({route[0].location, route[1].location}) !=
          epoch_fault_edges.end()) {
        faulted_route_ids.push_back(entry.first);
      }
    }
    for (const int task_id : faulted_route_ids) {
      saved_routes.erase(task_id);
      reservations.remove_task(task_id);
    }

    std::vector<TaskLeg> new_tasks;
    for (const int start : start_nodes) {
      if (legacy_window_detail::contains_unfinished_start(unfinished, start)) {
        continue;
      }
      auto found = task_groups.find(start);
      if (found == task_groups.end() || found->second.empty()) {
        continue;
      }
      const auto& next_task = found->second.front();
      if (next_task.pass_time - epoch >= 1.0) {
        continue;
      }
      new_tasks.push_back(next_task);
      found->second.pop_front();
      ++result.generated_count;
    }

    for (const auto& task : new_tasks) {
      unfinished.push_back(task);
    }

    const std::size_t attempt_count = unfinished.size();
    for (std::size_t attempt = 0; attempt < attempt_count; ++attempt) {
      TaskLeg current = unfinished.front();
      unfinished.pop_front();
      auto route = planner.plan(current.start,
                                current.goal,
                                epoch,
                                &reservations,
                                active_fault_edges,
                                current.task_id);
      if (route.empty()) {
        unfinished.push_back(current);
        ++result.unplanned_retry_count;
        continue;
      }
      reservations.add_route(current.task_id, route);
      saved_routes[current.task_id] = route;
      ++result.planned_count;
      legacy_window_detail::add_checksum(result, route);
      result.planned_routes.push_back(LegacyWindowPlannedRoute{
          result.planned_count,
          current.task_id,
          current.start,
          current.goal,
          epoch,
          route.back().t2,
          legacy_window_detail::route_locations(route)});
    }

    if (max_new_tasks > 0 && result.generated_count >= max_new_tasks) {
      break;
    }
  }

  result.active_route_count = static_cast<int>(saved_routes.size());
  result.unfinished_count = static_cast<int>(unfinished.size());
  result.active_fault_count = static_cast<int>(active_fault_edges.size());
  return result;
}

inline LegacyNoFaultWindowResult run_legacy_no_fault_window_from_files(
    const Graph& graph,
    const std::string& task_path,
    int start_epoch,
    int max_epochs,
    int max_new_tasks,
    const std::vector<LegacyWindowFaultEvent>& fault_schedule = {},
    double fault_probability = 0.0,
    double repair_probability = 0.0) {
  return run_legacy_no_fault_window(graph,
                                    legacy_window_detail::read_java_style_task_groups(task_path),
                                    start_epoch,
                                    max_epochs,
                                    max_new_tasks,
                                    fault_schedule,
                                    fault_probability,
                                    repair_probability);
}

}  // namespace czr005::ics
