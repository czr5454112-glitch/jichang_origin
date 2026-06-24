#include <chrono>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "ics_core/baselines/pibt.hpp"
#include "ics_core/baselines/pibt_replay.hpp"
#include "ics_core/baselines/periodic_replanning.hpp"
#include "ics_core/baselines/rolling_horizon.hpp"
#include "ics_core/event_sim/event_sim.hpp"
#include "ics_core/io/legacy_map_reader.hpp"
#include "ics_core/io/legacy_task_reader.hpp"
#include "ics_core/models/edge_score.hpp"
#include "ics_core/models/edge_score_io.hpp"
#include "ics_core/routing/astar.hpp"
#include "ics_core/routing/sipp.hpp"
#include "ics_core/runtime/edge_score_replay.hpp"

namespace py = pybind11;

namespace {

using EdgeFaultWindowTuple = std::tuple<int, int, double, double>;
using EdgeRecordTuple = std::tuple<int, int, double, double>;
using EdgeReservationTuple = std::tuple<int, int, int, double, double>;
using MergeGroupTuple = std::tuple<int, int, int>;
using NodeRecordTuple = std::tuple<int, int, double, int, int, std::vector<int>>;
using NodeCapacityTuple = std::tuple<int, int>;
using NodeReservationTuple = std::tuple<int, int, double, double>;
using PIBTAgentStateTuple = std::tuple<int, int, int, double, double, double>;
using TaskRecordTuple = std::tuple<std::string,
                                   int,
                                   int,
                                   double,
                                   double,
                                   int,
                                   int,
                                   int,
                                   int,
                                   double,
                                   std::string,
                                   bool,
                                   int>;

std::vector<int> route_locations(const std::vector<czr005::ics::PathNode>& route) {
  std::vector<int> locations;
  locations.reserve(route.size());
  for (const auto& node : route) {
    locations.push_back(node.location);
  }
  return locations;
}

py::list path_node_rows(const std::vector<czr005::ics::PathNode>& route) {
  py::list rows;
  for (const auto& node : route) {
    py::dict row;
    row["location"] = node.location;
    row["t1"] = node.t1;
    row["t2"] = node.t2;
    row["gcost"] = node.gcost;
    row["hcost"] = node.hcost;
    row["fcost"] = node.fcost;
    rows.append(row);
  }
  return rows;
}

py::dict read_legacy_map_summary(const std::string& path,
                                 bool allow_ragged_heuristic = false) {
  const auto legacy = czr005::ics::read_legacy_map2(path, 2.5, allow_ragged_heuristic);
  py::dict summary;
  summary["declared_node_count"] = legacy.declared_node_count;
  summary["node_count"] = legacy.graph.node_count();
  summary["heuristic_rows"] = legacy.heuristic_rows;
  summary["edge_rows"] = legacy.edge_rows;
  summary["edge_count"] = legacy.graph.edge_count();
  summary["type_1_count"] = legacy.graph.node_type_count(1);
  summary["type_2_count"] = legacy.graph.node_type_count(2);
  summary["agv_length"] = legacy.agv_length;
  summary["safe_length"] = legacy.safe_length;
  summary["fault_threshold"] = legacy.fault_threshold;
  return summary;
}

py::dict read_legacy_task_summary(const std::string& path) {
  const auto legacy = czr005::ics::read_legacy_inputdata(path);
  py::dict by_start;
  for (const auto& entry : legacy.expanded_by_start) {
    by_start[py::int_(entry.first)] = entry.second;
  }

  py::dict summary;
  summary["header"] = legacy.header;
  summary["raw_task_count"] = legacy.raw_task_count;
  summary["direct_raw_task_count"] = legacy.direct_raw_task_count;
  summary["early_split_raw_task_count"] = legacy.early_split_raw_task_count;
  summary["expanded_task_count"] = legacy.stream.size();
  summary["expanded_by_start"] = by_start;
  return summary;
}

std::vector<int> plan_legacy_map_path(const std::string& map_path,
                                      int start,
                                      int goal,
                                      bool allow_ragged_heuristic = false) {
  const auto legacy = czr005::ics::read_legacy_map2(map_path, 2.5, allow_ragged_heuristic);
  const czr005::ics::AStarPlanner planner(legacy.graph);
  return route_locations(planner.plan(start, goal));
}

std::vector<std::vector<int>> plan_legacy_map_paths(
    const std::string& map_path,
    const std::vector<std::pair<int, int>>& cases,
    bool allow_ragged_heuristic = false) {
  const auto legacy = czr005::ics::read_legacy_map2(map_path, 2.5, allow_ragged_heuristic);
  const czr005::ics::AStarPlanner planner(legacy.graph);

  std::vector<std::vector<int>> routes;
  routes.reserve(cases.size());
  for (const auto& path_case : cases) {
    routes.push_back(route_locations(planner.plan(path_case.first, path_case.second)));
  }
  return routes;
}

py::dict benchmark_legacy_map_paths(const std::string& map_path,
                                    const std::vector<std::pair<int, int>>& cases,
                                    int repeats,
                                    bool allow_ragged_heuristic = false) {
  const auto legacy = czr005::ics::read_legacy_map2(map_path, 2.5, allow_ragged_heuristic);
  const czr005::ics::AStarPlanner planner(legacy.graph);

  int checksum = 0;
  const auto start_time = std::chrono::steady_clock::now();
  for (int repeat = 0; repeat < repeats; ++repeat) {
    for (const auto& path_case : cases) {
      checksum += static_cast<int>(planner.plan(path_case.first, path_case.second).size());
    }
  }
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;

  py::dict result;
  result["case_count"] = cases.size();
  result["repeats"] = repeats;
  result["total_plans"] = static_cast<int>(cases.size()) * repeats;
  result["elapsed_seconds"] = elapsed.count();
  result["plans_per_second"] =
      elapsed.count() > 0.0 ? (static_cast<double>(cases.size()) * repeats) / elapsed.count() : 0.0;
  result["checksum"] = checksum;
  return result;
}

std::vector<double> edge_score_scores(const std::vector<std::vector<double>>& w1,
                                      const std::vector<double>& b1,
                                      const std::vector<double>& w2,
                                      double b2,
                                      const std::vector<std::vector<double>>& features) {
  const czr005::ics::EdgeScoreModel model(w1, b1, w2, b2);
  return model.scores(features);
}

int edge_score_predict(const std::vector<std::vector<double>>& w1,
                       const std::vector<double>& b1,
                       const std::vector<double>& w2,
                       double b2,
                       const std::vector<std::vector<double>>& features,
                       const std::vector<bool>& action_mask) {
  const czr005::ics::EdgeScoreModel model(w1, b1, w2, b2);
  return model.predict(features, action_mask);
}

py::dict edge_score_load_summary(const std::string& path) {
  const auto model = czr005::ics::load_edge_score_model_text(path);
  py::dict summary;
  summary["feature_dim"] = model.feature_dim();
  summary["hidden_dim"] = model.hidden_dim();
  return summary;
}

py::dict edge_score_replay_result_summary(const czr005::ics::EdgeScoreReplayResult& result,
                                          int max_tasks,
                                          double elapsed_seconds) {
  py::dict summary;
  summary["max_tasks"] = max_tasks;
  summary["planned_count"] = result.planned_count;
  summary["unplanned_count"] = result.unplanned_count;
  summary["decision_count"] = result.decision_count;
  summary["shield_blocks"] = result.shield_blocks;
  summary["unsafe_proposals"] = result.unsafe_proposals;
  summary["post_shield_conflicts"] = result.post_shield_conflicts;
  summary["mean_travel_time"] = result.mean_travel_time;
  summary["makespan"] = result.makespan;
  summary["elapsed_seconds"] = elapsed_seconds;
  summary["decisions_per_second"] =
      elapsed_seconds > 0.0 ? static_cast<double>(result.decision_count) / elapsed_seconds : 0.0;
  return summary;
}

py::dict edge_score_decision_trace_row(const czr005::ics::EdgeScoreDecisionTrace& trace) {
  py::dict row;
  row["decision_ordinal"] = trace.decision_ordinal;
  row["task_decision_ordinal"] = trace.task_decision_ordinal;
  row["event"] = trace.event;
  row["terminal_reason"] = trace.terminal_reason;
  row["task_index"] = trace.task_index;
  row["segment_id"] = trace.segment_id;
  row["task_id"] = trace.task_id;
  row["current"] = trace.current;
  row["goal"] = trace.goal;
  row["ready_time"] = trace.ready_time;
  row["waiting_time"] = trace.waiting_time;
  row["proposed_position"] = trace.proposed_position;
  row["executed_index"] = trace.executed_index;
  row["executed_next"] = trace.executed_next;
  row["executed_kind"] = trace.executed_kind;
  row["executed_safe"] = trace.executed_safe;
  row["unsafe_proposal"] = trace.unsafe_proposal;
  row["fallback_used"] = trace.fallback_used;
  row["reached_goal"] = trace.reached_goal;
  row["candidate_count"] = trace.candidate_count;
  row["safe_candidate_count"] = trace.safe_candidate_count;
  row["route_size_after"] = trace.route_size_after;
  return row;
}

py::list edge_score_decision_trace_rows(const czr005::ics::EdgeScoreReplayResult& result) {
  py::list rows;
  for (const auto& trace : result.trace) {
    rows.append(edge_score_decision_trace_row(trace));
  }
  return rows;
}

std::vector<czr005::ics::EdgeFaultWindow> edge_fault_windows_from_tuples(
    const std::vector<EdgeFaultWindowTuple>& fault_windows) {
  std::vector<czr005::ics::EdgeFaultWindow> windows;
  windows.reserve(fault_windows.size());
  for (const auto& [start, end, fault_start, repair_time] : fault_windows) {
    windows.push_back(czr005::ics::EdgeFaultWindow{start, end, fault_start, repair_time});
  }
  return windows;
}

std::unordered_map<int, int> node_capacities_from_tuples(
    const std::vector<NodeCapacityTuple>& node_capacities) {
  std::unordered_map<int, int> capacities;
  for (const auto& [node, capacity] : node_capacities) {
    capacities[node] = capacity;
  }
  return capacities;
}

std::vector<czr005::ics::MergeGroupEdge> merge_groups_from_tuples(
    const std::vector<MergeGroupTuple>& merge_groups) {
  std::vector<czr005::ics::MergeGroupEdge> groups;
  groups.reserve(merge_groups.size());
  for (const auto& [start_node, end_node, group] : merge_groups) {
    groups.push_back(czr005::ics::MergeGroupEdge{start_node, end_node, group});
  }
  return groups;
}

std::vector<czr005::ics::PeriodicFaultWindow> periodic_fault_windows_from_tuples(
    const std::vector<EdgeFaultWindowTuple>& fault_windows) {
  std::vector<czr005::ics::PeriodicFaultWindow> windows;
  windows.reserve(fault_windows.size());
  for (const auto& [start, end, fault_start, repair_time] : fault_windows) {
    windows.push_back(czr005::ics::PeriodicFaultWindow{start, end, fault_start, repair_time});
  }
  return windows;
}

std::vector<czr005::ics::RollingHorizonFaultWindow> rolling_horizon_fault_windows_from_tuples(
    const std::vector<EdgeFaultWindowTuple>& fault_windows) {
  std::vector<czr005::ics::RollingHorizonFaultWindow> windows;
  windows.reserve(fault_windows.size());
  for (const auto& [start, end, fault_start, repair_time] : fault_windows) {
    windows.push_back(czr005::ics::RollingHorizonFaultWindow{start, end, fault_start, repair_time});
  }
  return windows;
}

czr005::ics::Graph graph_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time) {
  czr005::ics::Graph graph;
  for (const auto& [location, node_type, service_time, x, y, outgoing] : node_records) {
    graph.add_node(czr005::ics::Node{location, node_type, service_time, x, y, outgoing});
  }
  graph.set_heuristic(heuristic_time);
  for (const auto& [start, end, length, speed] : edge_records) {
    graph.add_edge(czr005::ics::Edge{start, end, length, speed});
  }
  return graph;
}

czr005::ics::TaskStream task_stream_from_records(const std::vector<TaskRecordTuple>& task_records) {
  czr005::ics::TaskStream stream;
  for (const auto& [segment_id,
                    task_id,
                    pallet_id,
                    pass_time,
                    std_time,
                    start,
                    goal,
                    original_start,
                    original_goal,
                    original_entry_time,
                    leg,
                    early_bag_split,
                    source_line] : task_records) {
    stream.add(czr005::ics::TaskLeg{segment_id,
                                    task_id,
                                    pallet_id,
                                    pass_time,
                                    std_time,
                                    start,
                                    goal,
                                    original_start,
                                    original_goal,
                                    original_entry_time,
                                    leg,
                                    early_bag_split,
                                    source_line});
  }
  stream.sort_by_pass_time();
  return stream;
}

py::dict episode_metrics_row(const czr005::ics::EpisodeMetrics& metrics) {
  py::dict row;
  row["planned_count"] = metrics.planned_count;
  row["unplanned_count"] = metrics.unplanned_count;
  row["mean_travel_time"] = metrics.mean_travel_time;
  row["makespan"] = metrics.makespan;
  row["reservation_conflicts"] = metrics.reservation_conflicts;
  return row;
}

py::dict reference_event_row(const czr005::ics::ReferenceSimEvent& event) {
  py::dict row;
  row["event"] = event.event;
  row["segment_id"] = event.segment_id;
  row["task_id"] = event.task_id;
  row["start"] = event.start;
  row["goal"] = event.goal;
  row["entry_time"] = event.entry_time;
  if (event.event == "planned") {
    row["finish_time"] = event.finish_time;
    row["path"] = event.path;
  }
  return row;
}

py::dict reference_episode_result_row(const czr005::ics::ReferenceEpisodeResult& result) {
  py::dict row;
  py::dict routes;
  for (const auto& route_entry : result.routes) {
    routes[py::str(route_entry.first)] = path_node_rows(route_entry.second);
  }
  py::list unplanned;
  for (const auto& task : result.unplanned) {
    py::dict task_row;
    task_row["segment_id"] = task.segment_id;
    task_row["task_id"] = task.task_id;
    task_row["start"] = task.start;
    task_row["goal"] = task.goal;
    task_row["pass_time"] = task.pass_time;
    task_row["std"] = task.std;
    unplanned.append(task_row);
  }
  py::list events;
  for (const auto& event : result.events) {
    events.append(reference_event_row(event));
  }
  row["routes"] = routes;
  row["unplanned"] = unplanned;
  row["events"] = events;
  row["metrics"] = episode_metrics_row(result.metrics);
  return row;
}

py::dict reference_simulator_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<TaskRecordTuple>& task_records,
    int max_tasks,
    double end_time,
    const std::vector<std::pair<int, int>>& fault_edges) {
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto stream = task_stream_from_records(task_records);
  std::optional<int> max_tasks_opt;
  if (max_tasks >= 0) {
    max_tasks_opt = max_tasks;
  }
  std::optional<double> end_time_opt;
  if (end_time >= 0.0) {
    end_time_opt = end_time;
  }
  const std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  czr005::ics::ReferenceSimulator simulator(graph);
  return reference_episode_result_row(
      simulator.run_episode(stream, max_tasks_opt, end_time_opt, faults));
}

czr005::ics::ReservationTable node_reservations_from_tuples(
    const std::vector<NodeReservationTuple>& reservations) {
  czr005::ics::ReservationTable table;
  for (const auto& [task_id, node, start, end] : reservations) {
    table.reserve(task_id, node, start, end);
  }
  return table;
}

czr005::ics::EdgeReservationTable edge_reservations_from_tuples(
    const std::vector<EdgeReservationTuple>& reservations) {
  czr005::ics::EdgeReservationTable table;
  for (const auto& [task_id, start_node, end_node, start, end] : reservations) {
    table.reserve(task_id, start_node, end_node, start, end);
  }
  return table;
}

std::vector<czr005::ics::PIBTAgentState> pibt_agents_from_tuples(
    const std::vector<PIBTAgentStateTuple>& agent_records) {
  std::vector<czr005::ics::PIBTAgentState> agents;
  agents.reserve(agent_records.size());
  for (const auto& [task_id, current, goal, ready_time, deadline, waiting_time] : agent_records) {
    agents.push_back(czr005::ics::PIBTAgentState{
        task_id, current, goal, ready_time, deadline, waiting_time});
  }
  return agents;
}

py::list pibt_action_rows(const std::vector<czr005::ics::PIBTResolvedAction>& actions) {
  py::list rows;
  for (const auto& action : actions) {
    py::dict row;
    row["task_id"] = action.task_id;
    row["action"] = action.action;
    row["current"] = action.current;
    row["next_node"] = action.next_node;
    row["edge_start"] = action.edge_start;
    row["edge_end"] = action.edge_end;
    row["node_start"] = action.node_start;
    row["node_end"] = action.node_end;
    row["reason"] = action.reason;
    row["priority_rank"] = action.priority_rank;
    rows.append(row);
  }
  return rows;
}

czr005::ics::EdgeScoreReplayConfig make_replay_config(
    int max_tasks,
    int max_decisions_per_task,
    int task_offset,
    const std::vector<NodeCapacityTuple>& node_capacities = {},
    const std::vector<MergeGroupTuple>& merge_groups = {},
    int merge_capacity = 1,
    double merge_headway_seconds = 0.0) {
  if (max_tasks <= 0) {
    throw std::invalid_argument("max_tasks must be positive");
  }
  if (max_decisions_per_task <= 0) {
    throw std::invalid_argument("max_decisions_per_task must be positive");
  }
  if (task_offset < 0) {
    throw std::invalid_argument("task_offset must be non-negative");
  }
  if (merge_capacity <= 0) {
    throw std::invalid_argument("merge_capacity must be positive");
  }
  czr005::ics::EdgeScoreReplayConfig config;
  config.task_offset = static_cast<std::size_t>(task_offset);
  config.max_tasks = static_cast<std::size_t>(max_tasks);
  config.max_decisions_per_task = max_decisions_per_task;
  config.node_capacities = node_capacities_from_tuples(node_capacities);
  config.merge_groups = merge_groups_from_tuples(merge_groups);
  config.merge_capacity = merge_capacity;
  config.merge_headway_seconds = merge_headway_seconds;
  return config;
}

py::dict edge_score_native_replay_summary(const std::string& map_path,
                                          const std::string& task_path,
                                          const std::string& model_path,
                                          int max_tasks,
                                          const std::vector<std::pair<int, int>>& fault_edges,
                                          int max_decisions_per_task,
                                          int task_offset,
                                          const std::vector<EdgeFaultWindowTuple>& fault_windows,
                                          const std::vector<NodeCapacityTuple>& node_capacities,
                                          const std::vector<MergeGroupTuple>& merge_groups,
                                          int merge_capacity,
                                          double merge_headway_seconds) {
  const auto legacy_map = czr005::ics::read_legacy_map2(map_path);
  const auto legacy_tasks = czr005::ics::read_legacy_inputdata(task_path);
  const auto model = czr005::ics::load_edge_score_model_text(model_path);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = edge_fault_windows_from_tuples(fault_windows);
  const auto config = make_replay_config(max_tasks,
                                         max_decisions_per_task,
                                         task_offset,
                                         node_capacities,
                                         merge_groups,
                                         merge_capacity,
                                         merge_headway_seconds);

  const auto start_time = std::chrono::steady_clock::now();
  const auto result = czr005::ics::run_edge_score_replay(
      legacy_map.graph,
      legacy_tasks.stream,
      model,
      config,
      faults,
      windows);
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;

  return edge_score_replay_result_summary(result, max_tasks, elapsed.count());
}

py::dict edge_score_native_replay_trace(const std::string& map_path,
                                        const std::string& task_path,
                                        const std::string& model_path,
                                        int max_tasks,
                                        const std::vector<std::pair<int, int>>& fault_edges,
                                        int max_decisions_per_task,
                                        int task_offset,
                                        const std::vector<EdgeFaultWindowTuple>& fault_windows,
                                        const std::vector<NodeCapacityTuple>& node_capacities,
                                        const std::vector<MergeGroupTuple>& merge_groups,
                                        int merge_capacity,
                                        double merge_headway_seconds) {
  const auto legacy_map = czr005::ics::read_legacy_map2(map_path);
  const auto legacy_tasks = czr005::ics::read_legacy_inputdata(task_path);
  const auto model = czr005::ics::load_edge_score_model_text(model_path);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = edge_fault_windows_from_tuples(fault_windows);
  const auto config = make_replay_config(max_tasks,
                                         max_decisions_per_task,
                                         task_offset,
                                         node_capacities,
                                         merge_groups,
                                         merge_capacity,
                                         merge_headway_seconds);

  const auto start_time = std::chrono::steady_clock::now();
  const auto result = czr005::ics::run_edge_score_replay(
      legacy_map.graph,
      legacy_tasks.stream,
      model,
      config,
      faults,
      windows);
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;

  py::dict payload;
  payload["summary"] = edge_score_replay_result_summary(result, max_tasks, elapsed.count());
  payload["trace"] = edge_score_decision_trace_rows(result);
  return payload;
}

py::dict edge_score_native_fallback_replay_summary(const std::string& map_path,
                                                   const std::string& task_path,
                                                   int max_tasks,
                                                   const std::vector<std::pair<int, int>>& fault_edges,
                                                   int max_decisions_per_task,
                                                   int task_offset,
                                                   const std::vector<EdgeFaultWindowTuple>& fault_windows,
                                                   const std::vector<NodeCapacityTuple>& node_capacities,
                                                   const std::vector<MergeGroupTuple>& merge_groups,
                                                   int merge_capacity,
                                                   double merge_headway_seconds) {
  const auto legacy_map = czr005::ics::read_legacy_map2(map_path);
  const auto legacy_tasks = czr005::ics::read_legacy_inputdata(task_path);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = edge_fault_windows_from_tuples(fault_windows);
  const auto config = make_replay_config(max_tasks,
                                         max_decisions_per_task,
                                         task_offset,
                                         node_capacities,
                                         merge_groups,
                                         merge_capacity,
                                         merge_headway_seconds);

  const auto start_time = std::chrono::steady_clock::now();
  const auto result = czr005::ics::run_edge_score_fallback_replay(
      legacy_map.graph,
      legacy_tasks.stream,
      config,
      faults,
      windows);
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;
  return edge_score_replay_result_summary(result, max_tasks, elapsed.count());
}

py::list sipp_plan_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    int start,
    int goal,
    double start_time,
    const std::vector<NodeReservationTuple>& node_reservations,
    const std::vector<EdgeReservationTuple>& edge_reservations,
    int edge_capacity,
    double edge_headway_seconds,
    const std::vector<std::pair<int, int>>& fault_edges,
    int task_id,
    double max_time,
    const std::vector<NodeCapacityTuple>& node_capacities,
    const std::vector<MergeGroupTuple>& merge_groups,
    int merge_capacity,
    double merge_headway_seconds) {
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto node_table = node_reservations_from_tuples(node_reservations);
  const auto edge_table = edge_reservations_from_tuples(edge_reservations);
  const auto capacities = node_capacities_from_tuples(node_capacities);
  const auto groups = merge_groups_from_tuples(merge_groups);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const czr005::ics::SIPPPlanner planner(graph, max_time);
  return path_node_rows(planner.plan(start,
                                     goal,
                                     start_time,
                                     &node_table,
                                     &edge_table,
                                     edge_capacity,
                                     edge_headway_seconds,
                                     faults,
                                     task_id,
                                     capacities,
                                     groups,
                                     merge_capacity,
                                     merge_headway_seconds));
}

py::list pibt_resolve_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<PIBTAgentStateTuple>& agent_records,
    const std::vector<NodeReservationTuple>& node_reservations,
    const std::vector<std::pair<int, int>>& fault_edges,
    double hold_seconds,
    const std::vector<EdgeReservationTuple>& edge_reservations,
    int edge_capacity,
    double edge_headway_seconds,
    const std::vector<NodeCapacityTuple>& node_capacities,
    const std::vector<MergeGroupTuple>& merge_groups,
    int merge_capacity,
    double merge_headway_seconds) {
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto agents = pibt_agents_from_tuples(agent_records);
  const auto node_table = node_reservations_from_tuples(node_reservations);
  const auto edge_table = edge_reservations_from_tuples(edge_reservations);
  const auto capacities = node_capacities_from_tuples(node_capacities);
  const auto groups = merge_groups_from_tuples(merge_groups);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const czr005::ics::PIBTStyleOneStepResolver resolver(graph, hold_seconds);
  return pibt_action_rows(resolver.resolve(agents,
                                           &node_table,
                                           faults,
                                           &edge_table,
                                           edge_capacity,
                                           edge_headway_seconds,
                                           capacities,
                                           groups,
                                           merge_capacity,
                                           merge_headway_seconds));
}

py::dict rolling_horizon_summary(const czr005::ics::RollingHorizonResult& result,
                                 int max_tasks) {
  py::dict summary;
  summary["max_tasks"] = max_tasks;
  summary["planned_count"] = result.planned_count;
  summary["unplanned_count"] = result.unplanned_count;
  summary["decision_count"] = static_cast<int>(result.events.size());
  summary["reservation_conflicts"] = result.reservation_conflicts;
  summary["edge_reservation_conflicts"] = result.edge_reservation_conflicts;
  summary["post_shield_conflicts"] = result.reservation_conflicts + result.edge_reservation_conflicts;
  summary["mean_travel_time"] = result.mean_travel_time;
  summary["makespan"] = result.makespan;
  return summary;
}

py::list rolling_horizon_event_rows(const czr005::ics::RollingHorizonResult& result) {
  py::list rows;
  for (const auto& event : result.events) {
    py::dict row;
    row["event"] = event.event;
    row["baseline"] = "rolling_horizon_sipp";
    row["segment_id"] = event.segment_id;
    row["task_id"] = event.task_id;
    row["start"] = event.start;
    row["goal"] = event.goal;
    row["entry_time"] = event.entry_time;
    row["finish_time"] = event.finish_time;
    row["horizon_start"] = event.horizon_start;
    row["horizon_end"] = event.horizon_end;
    row["priority_rank"] = event.priority_rank;
    row["path"] = event.path;
    rows.append(row);
  }
  return rows;
}

py::dict rolling_horizon_sipp_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<TaskRecordTuple>& task_records,
    int max_tasks,
    double horizon_seconds,
    int edge_capacity,
    double edge_headway_seconds,
    const std::vector<std::pair<int, int>>& fault_edges,
    const std::vector<EdgeFaultWindowTuple>& fault_windows,
    const std::vector<NodeCapacityTuple>& node_capacities,
    const std::vector<MergeGroupTuple>& merge_groups,
    int merge_capacity,
    double merge_headway_seconds) {
  if (max_tasks <= 0) {
    throw std::invalid_argument("max_tasks must be positive");
  }
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto tasks = task_stream_from_records(task_records);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = rolling_horizon_fault_windows_from_tuples(fault_windows);
  czr005::ics::RollingHorizonConfig config;
  config.max_tasks = static_cast<std::size_t>(max_tasks);
  config.horizon_seconds = horizon_seconds;
  config.edge_capacity = edge_capacity;
  config.edge_headway_seconds = edge_headway_seconds;
  config.node_capacities = node_capacities_from_tuples(node_capacities);
  config.merge_groups = merge_groups_from_tuples(merge_groups);
  config.merge_capacity = merge_capacity;
  config.merge_headway_seconds = merge_headway_seconds;
  const auto result = czr005::ics::run_rolling_horizon_sipp(graph, tasks, config, faults, windows);

  py::dict payload;
  payload["summary"] = rolling_horizon_summary(result, max_tasks);
  payload["events"] = rolling_horizon_event_rows(result);
  return payload;
}

py::dict periodic_replanning_summary(const czr005::ics::PeriodicReplanningResult& result,
                                     int max_tasks) {
  py::dict summary;
  summary["max_tasks"] = max_tasks;
  summary["planned_count"] = result.planned_count;
  summary["unplanned_count"] = result.unplanned_count;
  summary["replan_count"] = result.replan_count;
  summary["tick_count"] = result.tick_count;
  summary["peak_active_bags"] = result.peak_active_bags;
  summary["reservation_conflicts"] = result.reservation_conflicts;
  summary["edge_reservation_conflicts"] = result.edge_reservation_conflicts;
  summary["post_shield_conflicts"] = result.post_shield_conflicts;
  summary["mean_travel_time"] = result.mean_travel_time;
  summary["makespan"] = result.makespan;
  return summary;
}

py::list periodic_replanning_event_rows(const czr005::ics::PeriodicReplanningResult& result) {
  py::list rows;
  for (const auto& event : result.events) {
    py::dict row;
    row["event"] = event.event;
    row["baseline"] = "periodic_replanning_sipp";
    row["segment_id"] = event.segment_id;
    row["task_id"] = event.task_id;
    row["current"] = event.current;
    row["next_node"] = event.next_node;
    row["start"] = event.start;
    row["goal"] = event.goal;
    row["entry_time"] = event.entry_time;
    row["finish_time"] = event.finish_time;
    row["tick_time"] = event.tick_time;
    row["ready_time"] = event.ready_time;
    row["priority_rank"] = event.priority_rank;
    row["replan_count"] = event.replan_count;
    row["reached_goal"] = event.reached_goal;
    row["reason"] = event.reason;
    row["path"] = event.path;
    row["planned_path"] = event.planned_path;
    rows.append(row);
  }
  return rows;
}

py::dict periodic_replanning_sipp_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<TaskRecordTuple>& task_records,
    int max_tasks,
    double interval_seconds,
    int max_ticks,
    int edge_capacity,
    double edge_headway_seconds,
    const std::vector<std::pair<int, int>>& fault_edges,
    const std::vector<EdgeFaultWindowTuple>& fault_windows,
    const std::vector<NodeCapacityTuple>& node_capacities,
    const std::vector<MergeGroupTuple>& merge_groups,
    int merge_capacity,
    double merge_headway_seconds) {
  if (max_tasks <= 0) {
    throw std::invalid_argument("max_tasks must be positive");
  }
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto tasks = task_stream_from_records(task_records);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = periodic_fault_windows_from_tuples(fault_windows);
  czr005::ics::PeriodicReplanningConfig config;
  config.max_tasks = static_cast<std::size_t>(max_tasks);
  config.interval_seconds = interval_seconds;
  config.max_ticks = max_ticks;
  config.edge_capacity = edge_capacity;
  config.edge_headway_seconds = edge_headway_seconds;
  config.node_capacities = node_capacities_from_tuples(node_capacities);
  config.merge_groups = merge_groups_from_tuples(merge_groups);
  config.merge_capacity = merge_capacity;
  config.merge_headway_seconds = merge_headway_seconds;
  const auto result = czr005::ics::run_periodic_replanning_sipp(graph, tasks, config, faults, windows);

  py::dict payload;
  payload["summary"] = periodic_replanning_summary(result, max_tasks);
  payload["events"] = periodic_replanning_event_rows(result);
  return payload;
}

py::dict pibt_active_bag_replay_summary(const czr005::ics::PIBTActiveBagReplayResult& result,
                                        int max_tasks) {
  py::dict summary;
  summary["max_tasks"] = max_tasks;
  summary["planned_count"] = result.planned_count;
  summary["unplanned_count"] = result.unplanned_count;
  summary["decision_count"] = result.decision_count;
  summary["tick_count"] = result.tick_count;
  summary["peak_active_bags"] = result.peak_active_bags;
  summary["move_count"] = result.move_count;
  summary["hold_count"] = result.hold_count;
  summary["reservation_conflicts"] = result.reservation_conflicts;
  summary["edge_reservation_conflicts"] = result.edge_reservation_conflicts;
  summary["post_shield_conflicts"] = result.post_shield_conflicts;
  summary["mean_travel_time"] = result.mean_travel_time;
  summary["makespan"] = result.makespan;
  return summary;
}

py::list pibt_active_bag_replay_event_rows(
    const czr005::ics::PIBTActiveBagReplayResult& result) {
  py::list rows;
  for (const auto& event : result.events) {
    py::dict row;
    row["event"] = event.event;
    row["baseline"] = "pibt_active_bag_replay";
    row["segment_id"] = event.segment_id;
    row["task_id"] = event.task_id;
    row["current"] = event.current;
    row["next_node"] = event.next_node;
    row["start"] = event.start;
    row["goal"] = event.goal;
    row["entry_time"] = event.entry_time;
    row["finish_time"] = event.finish_time;
    row["tick_time"] = event.tick_time;
    row["ready_time"] = event.ready_time;
    row["priority_rank"] = event.priority_rank;
    row["decision_count"] = event.decision_count;
    row["reached_goal"] = event.reached_goal;
    row["reason"] = event.reason;
    row["path"] = event.path;
    rows.append(row);
  }
  return rows;
}

py::dict pibt_active_bag_replay_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<TaskRecordTuple>& task_records,
    int max_tasks,
    double interval_seconds,
    int max_ticks,
    double hold_seconds,
    int edge_capacity,
    double edge_headway_seconds,
    const std::vector<std::pair<int, int>>& fault_edges,
    const std::vector<EdgeFaultWindowTuple>& fault_windows,
    const std::vector<NodeCapacityTuple>& node_capacities,
    const std::vector<MergeGroupTuple>& merge_groups,
    int merge_capacity,
    double merge_headway_seconds) {
  if (max_tasks <= 0) {
    throw std::invalid_argument("max_tasks must be positive");
  }
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto tasks = task_stream_from_records(task_records);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = periodic_fault_windows_from_tuples(fault_windows);
  czr005::ics::PIBTActiveBagReplayConfig config;
  config.max_tasks = static_cast<std::size_t>(max_tasks);
  config.interval_seconds = interval_seconds;
  config.max_ticks = max_ticks;
  config.hold_seconds = hold_seconds;
  config.edge_capacity = edge_capacity;
  config.edge_headway_seconds = edge_headway_seconds;
  config.node_capacities = node_capacities_from_tuples(node_capacities);
  config.merge_groups = merge_groups_from_tuples(merge_groups);
  config.merge_capacity = merge_capacity;
  config.merge_headway_seconds = merge_headway_seconds;
  const auto result = czr005::ics::run_pibt_active_bag_replay(graph, tasks, config, faults, windows);

  py::dict payload;
  payload["summary"] = pibt_active_bag_replay_summary(result, max_tasks);
  payload["events"] = pibt_active_bag_replay_event_rows(result);
  return payload;
}

py::dict edge_score_native_replay_summary_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<TaskRecordTuple>& task_records,
    const std::string& model_path,
    int max_tasks,
    const std::vector<std::pair<int, int>>& fault_edges,
    int max_decisions_per_task,
    int task_offset,
    const std::vector<EdgeFaultWindowTuple>& fault_windows,
    const std::vector<NodeCapacityTuple>& node_capacities,
    const std::vector<MergeGroupTuple>& merge_groups,
    int merge_capacity,
    double merge_headway_seconds) {
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto tasks = task_stream_from_records(task_records);
  const auto model = czr005::ics::load_edge_score_model_text(model_path);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = edge_fault_windows_from_tuples(fault_windows);
  const auto config = make_replay_config(max_tasks,
                                         max_decisions_per_task,
                                         task_offset,
                                         node_capacities,
                                         merge_groups,
                                         merge_capacity,
                                         merge_headway_seconds);

  const auto start_time = std::chrono::steady_clock::now();
  const auto result = czr005::ics::run_edge_score_replay(
      graph,
      tasks,
      model,
      config,
      faults,
      windows);
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;
  return edge_score_replay_result_summary(result, max_tasks, elapsed.count());
}

py::dict edge_score_native_event_replay_summary_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<TaskRecordTuple>& task_records,
    const std::string& model_path,
    int max_tasks,
    const std::vector<std::pair<int, int>>& fault_edges,
    int max_decisions_per_task,
    int task_offset,
    const std::vector<EdgeFaultWindowTuple>& fault_windows,
    const std::vector<NodeCapacityTuple>& node_capacities,
    const std::vector<MergeGroupTuple>& merge_groups,
    int merge_capacity,
    double merge_headway_seconds) {
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto tasks = task_stream_from_records(task_records);
  const auto model = czr005::ics::load_edge_score_model_text(model_path);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = edge_fault_windows_from_tuples(fault_windows);
  const auto config = make_replay_config(max_tasks,
                                         max_decisions_per_task,
                                         task_offset,
                                         node_capacities,
                                         merge_groups,
                                         merge_capacity,
                                         merge_headway_seconds);

  const auto start_time = std::chrono::steady_clock::now();
  const auto result = czr005::ics::run_edge_score_event_replay(
      graph,
      tasks,
      model,
      config,
      faults,
      windows);
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;
  return edge_score_replay_result_summary(result, max_tasks, elapsed.count());
}

py::dict edge_score_native_event_replay_trace_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<TaskRecordTuple>& task_records,
    const std::string& model_path,
    int max_tasks,
    const std::vector<std::pair<int, int>>& fault_edges,
    int max_decisions_per_task,
    int task_offset,
    const std::vector<EdgeFaultWindowTuple>& fault_windows,
    const std::vector<NodeCapacityTuple>& node_capacities,
    const std::vector<MergeGroupTuple>& merge_groups,
    int merge_capacity,
    double merge_headway_seconds) {
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto tasks = task_stream_from_records(task_records);
  const auto model = czr005::ics::load_edge_score_model_text(model_path);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = edge_fault_windows_from_tuples(fault_windows);
  const auto config = make_replay_config(max_tasks,
                                         max_decisions_per_task,
                                         task_offset,
                                         node_capacities,
                                         merge_groups,
                                         merge_capacity,
                                         merge_headway_seconds);

  const auto start_time = std::chrono::steady_clock::now();
  const auto result = czr005::ics::run_edge_score_event_replay(
      graph,
      tasks,
      model,
      config,
      faults,
      windows);
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;

  py::dict payload;
  payload["summary"] = edge_score_replay_result_summary(result, max_tasks, elapsed.count());
  payload["trace"] = edge_score_decision_trace_rows(result);
  return payload;
}

py::dict edge_score_native_replay_trace_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<TaskRecordTuple>& task_records,
    const std::string& model_path,
    int max_tasks,
    const std::vector<std::pair<int, int>>& fault_edges,
    int max_decisions_per_task,
    int task_offset,
    const std::vector<EdgeFaultWindowTuple>& fault_windows,
    const std::vector<NodeCapacityTuple>& node_capacities,
    const std::vector<MergeGroupTuple>& merge_groups,
    int merge_capacity,
    double merge_headway_seconds) {
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto tasks = task_stream_from_records(task_records);
  const auto model = czr005::ics::load_edge_score_model_text(model_path);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = edge_fault_windows_from_tuples(fault_windows);
  const auto config = make_replay_config(max_tasks,
                                         max_decisions_per_task,
                                         task_offset,
                                         node_capacities,
                                         merge_groups,
                                         merge_capacity,
                                         merge_headway_seconds);

  const auto start_time = std::chrono::steady_clock::now();
  const auto result = czr005::ics::run_edge_score_replay(
      graph,
      tasks,
      model,
      config,
      faults,
      windows);
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;

  py::dict payload;
  payload["summary"] = edge_score_replay_result_summary(result, max_tasks, elapsed.count());
  payload["trace"] = edge_score_decision_trace_rows(result);
  return payload;
}

py::dict edge_score_native_fallback_replay_summary_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<TaskRecordTuple>& task_records,
    int max_tasks,
    const std::vector<std::pair<int, int>>& fault_edges,
    int max_decisions_per_task,
    int task_offset,
    const std::vector<EdgeFaultWindowTuple>& fault_windows,
    const std::vector<NodeCapacityTuple>& node_capacities,
    const std::vector<MergeGroupTuple>& merge_groups,
    int merge_capacity,
    double merge_headway_seconds) {
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto tasks = task_stream_from_records(task_records);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = edge_fault_windows_from_tuples(fault_windows);
  const auto config = make_replay_config(max_tasks,
                                         max_decisions_per_task,
                                         task_offset,
                                         node_capacities,
                                         merge_groups,
                                         merge_capacity,
                                         merge_headway_seconds);

  const auto start_time = std::chrono::steady_clock::now();
  const auto result = czr005::ics::run_edge_score_fallback_replay(
      graph,
      tasks,
      config,
      faults,
      windows);
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;
  return edge_score_replay_result_summary(result, max_tasks, elapsed.count());
}

py::dict edge_score_native_event_fallback_replay_summary_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<TaskRecordTuple>& task_records,
    int max_tasks,
    const std::vector<std::pair<int, int>>& fault_edges,
    int max_decisions_per_task,
    int task_offset,
    const std::vector<EdgeFaultWindowTuple>& fault_windows,
    const std::vector<NodeCapacityTuple>& node_capacities,
    const std::vector<MergeGroupTuple>& merge_groups,
    int merge_capacity,
    double merge_headway_seconds) {
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto tasks = task_stream_from_records(task_records);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = edge_fault_windows_from_tuples(fault_windows);
  const auto config = make_replay_config(max_tasks,
                                         max_decisions_per_task,
                                         task_offset,
                                         node_capacities,
                                         merge_groups,
                                         merge_capacity,
                                         merge_headway_seconds);

  const auto start_time = std::chrono::steady_clock::now();
  const auto result = czr005::ics::run_edge_score_event_fallback_replay(
      graph,
      tasks,
      config,
      faults,
      windows);
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;
  return edge_score_replay_result_summary(result, max_tasks, elapsed.count());
}

py::dict edge_score_native_event_fallback_replay_trace_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<TaskRecordTuple>& task_records,
    int max_tasks,
    const std::vector<std::pair<int, int>>& fault_edges,
    int max_decisions_per_task,
    int task_offset,
    const std::vector<EdgeFaultWindowTuple>& fault_windows,
    const std::vector<NodeCapacityTuple>& node_capacities,
    const std::vector<MergeGroupTuple>& merge_groups,
    int merge_capacity,
    double merge_headway_seconds) {
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto tasks = task_stream_from_records(task_records);
  std::set<std::pair<int, int>> faults(fault_edges.begin(), fault_edges.end());
  const auto windows = edge_fault_windows_from_tuples(fault_windows);
  const auto config = make_replay_config(max_tasks,
                                         max_decisions_per_task,
                                         task_offset,
                                         node_capacities,
                                         merge_groups,
                                         merge_capacity,
                                         merge_headway_seconds);

  const auto start_time = std::chrono::steady_clock::now();
  const auto result = czr005::ics::run_edge_score_event_fallback_replay(
      graph,
      tasks,
      config,
      faults,
      windows);
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;

  py::dict payload;
  payload["summary"] = edge_score_replay_result_summary(result, max_tasks, elapsed.count());
  payload["trace"] = edge_score_decision_trace_rows(result);
  return payload;
}

}  // namespace

PYBIND11_MODULE(czr005_cpp, module) {
  module.doc() = "Minimal czr005 C++ core bindings for Phase1D parity checks.";
  py::class_<czr005::ics::EdgeScoreModel>(module, "EdgeScoreRuntimeModel")
      .def(py::init<std::vector<std::vector<double>>, std::vector<double>, std::vector<double>, double>(),
           py::arg("w1"),
           py::arg("b1"),
           py::arg("w2"),
           py::arg("b2"))
      .def_static("from_text", &czr005::ics::load_edge_score_model_text, py::arg("path"))
      .def("scores", &czr005::ics::EdgeScoreModel::scores, py::arg("features"))
      .def("predict",
           &czr005::ics::EdgeScoreModel::predict,
           py::arg("features"),
           py::arg("action_mask") = std::vector<bool>{})
      .def("predict_many",
           &czr005::ics::EdgeScoreModel::predict_many,
           py::arg("feature_batches"),
           py::arg("action_masks") = std::vector<std::vector<bool>>{})
      .def_property_readonly("feature_dim", &czr005::ics::EdgeScoreModel::feature_dim)
      .def_property_readonly("hidden_dim", &czr005::ics::EdgeScoreModel::hidden_dim);

  module.def("read_legacy_map_summary",
             &read_legacy_map_summary,
             py::arg("path"),
             py::arg("allow_ragged_heuristic") = false);
  module.def("read_legacy_task_summary", &read_legacy_task_summary, py::arg("path"));
  module.def("plan_legacy_map_path",
             &plan_legacy_map_path,
             py::arg("map_path"),
             py::arg("start"),
             py::arg("goal"),
             py::arg("allow_ragged_heuristic") = false);
  module.def("plan_legacy_map_paths",
             &plan_legacy_map_paths,
             py::arg("map_path"),
             py::arg("cases"),
             py::arg("allow_ragged_heuristic") = false);
  module.def("benchmark_legacy_map_paths",
             &benchmark_legacy_map_paths,
             py::arg("map_path"),
             py::arg("cases"),
             py::arg("repeats") = 100,
             py::arg("allow_ragged_heuristic") = false);
  module.def("edge_score_scores",
             &edge_score_scores,
             py::arg("w1"),
             py::arg("b1"),
             py::arg("w2"),
             py::arg("b2"),
             py::arg("features"));
  module.def("edge_score_predict",
             &edge_score_predict,
             py::arg("w1"),
             py::arg("b1"),
             py::arg("w2"),
             py::arg("b2"),
             py::arg("features"),
             py::arg("action_mask"));
  module.def("edge_score_load_summary", &edge_score_load_summary, py::arg("path"));
  module.def("edge_score_native_replay_summary",
             &edge_score_native_replay_summary,
             py::arg("map_path"),
             py::arg("task_path"),
             py::arg("model_path"),
             py::arg("max_tasks") = 8,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("max_decisions_per_task") = 128,
             py::arg("task_offset") = 0,
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("edge_score_native_replay_trace",
             &edge_score_native_replay_trace,
             py::arg("map_path"),
             py::arg("task_path"),
             py::arg("model_path"),
             py::arg("max_tasks") = 8,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("max_decisions_per_task") = 128,
             py::arg("task_offset") = 0,
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("edge_score_native_fallback_replay_summary",
             &edge_score_native_fallback_replay_summary,
             py::arg("map_path"),
             py::arg("task_path"),
             py::arg("max_tasks") = 8,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("max_decisions_per_task") = 128,
             py::arg("task_offset") = 0,
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("reference_simulator_from_records",
             &reference_simulator_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("task_records"),
             py::arg("max_tasks") = -1,
             py::arg("end_time") = -1.0,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{});
  module.def("sipp_plan_from_records",
             &sipp_plan_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("start"),
             py::arg("goal"),
             py::arg("start_time") = 0.0,
             py::arg("node_reservations") = std::vector<NodeReservationTuple>{},
             py::arg("edge_reservations") = std::vector<EdgeReservationTuple>{},
             py::arg("edge_capacity") = 1,
             py::arg("edge_headway_seconds") = 0.0,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("task_id") = -1,
             py::arg("max_time") = 86400.0,
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("pibt_resolve_from_records",
             &pibt_resolve_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("agent_records"),
             py::arg("node_reservations") = std::vector<NodeReservationTuple>{},
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("hold_seconds") = 1.0,
             py::arg("edge_reservations") = std::vector<EdgeReservationTuple>{},
             py::arg("edge_capacity") = 1,
             py::arg("edge_headway_seconds") = 0.0,
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("rolling_horizon_sipp_from_records",
             &rolling_horizon_sipp_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("task_records"),
             py::arg("max_tasks") = 8,
             py::arg("horizon_seconds") = 300.0,
             py::arg("edge_capacity") = 1,
             py::arg("edge_headway_seconds") = 0.0,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("periodic_replanning_sipp_from_records",
             &periodic_replanning_sipp_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("task_records"),
             py::arg("max_tasks") = 8,
             py::arg("interval_seconds") = 5.0,
             py::arg("max_ticks") = 2048,
             py::arg("edge_capacity") = 1,
             py::arg("edge_headway_seconds") = 0.0,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("pibt_active_bag_replay_from_records",
             &pibt_active_bag_replay_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("task_records"),
             py::arg("max_tasks") = 8,
             py::arg("interval_seconds") = 5.0,
             py::arg("max_ticks") = 2048,
             py::arg("hold_seconds") = 5.0,
             py::arg("edge_capacity") = 1,
             py::arg("edge_headway_seconds") = 0.0,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("edge_score_native_replay_summary_from_records",
             &edge_score_native_replay_summary_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("task_records"),
             py::arg("model_path"),
             py::arg("max_tasks") = 8,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("max_decisions_per_task") = 128,
             py::arg("task_offset") = 0,
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("edge_score_native_event_replay_summary_from_records",
             &edge_score_native_event_replay_summary_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("task_records"),
             py::arg("model_path"),
             py::arg("max_tasks") = 8,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("max_decisions_per_task") = 128,
             py::arg("task_offset") = 0,
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("edge_score_native_event_replay_trace_from_records",
             &edge_score_native_event_replay_trace_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("task_records"),
             py::arg("model_path"),
             py::arg("max_tasks") = 8,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("max_decisions_per_task") = 128,
             py::arg("task_offset") = 0,
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("edge_score_native_replay_trace_from_records",
             &edge_score_native_replay_trace_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("task_records"),
             py::arg("model_path"),
             py::arg("max_tasks") = 8,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("max_decisions_per_task") = 128,
             py::arg("task_offset") = 0,
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("edge_score_native_fallback_replay_summary_from_records",
             &edge_score_native_fallback_replay_summary_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("task_records"),
             py::arg("max_tasks") = 8,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("max_decisions_per_task") = 128,
             py::arg("task_offset") = 0,
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("edge_score_native_event_fallback_replay_summary_from_records",
             &edge_score_native_event_fallback_replay_summary_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("task_records"),
             py::arg("max_tasks") = 8,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("max_decisions_per_task") = 128,
             py::arg("task_offset") = 0,
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
  module.def("edge_score_native_event_fallback_replay_trace_from_records",
             &edge_score_native_event_fallback_replay_trace_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("task_records"),
             py::arg("max_tasks") = 8,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("max_decisions_per_task") = 128,
             py::arg("task_offset") = 0,
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("node_capacities") = std::vector<NodeCapacityTuple>{},
             py::arg("merge_groups") = std::vector<MergeGroupTuple>{},
             py::arg("merge_capacity") = 1,
             py::arg("merge_headway_seconds") = 0.0);
}
