#include <chrono>
#include <algorithm>
#include <cctype>
#include <cmath>
#include <deque>
#include <fstream>
#include <functional>
#include <limits>
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
#include "ics_core/legacy/legacy_window.hpp"
#include "ics_core/models/edge_score.hpp"
#include "ics_core/models/edge_score_io.hpp"
#include "ics_core/routing/astar.hpp"
#include "ics_core/routing/sipp.hpp"
#include "ics_core/runtime/edge_score_replay.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"
#include "ics_core/bindings/g4irsf15_causal_campaign_binding.hpp"

namespace py = pybind11;

namespace {

using EdgeFaultWindowTuple = std::tuple<int, int, double, double>;
using EdgeRecordTuple = std::tuple<int, int, double, double>;
using EdgeReservationTuple = std::tuple<int, int, int, double, double>;
using EventRuntimeBagTuple = std::tuple<std::string, int, double, double, int, int, std::string>;
using EventRuntimeFaultTuple = std::tuple<int, int, double, double, double>;
using EventRuntimeRegretPriorTuple = std::tuple<int, int, int, double>;
using G4IFallbackRuleTuple = std::tuple<int, int, std::vector<int>, int>;
using G4IHistoricalRiskRuleTuple = std::tuple<int, std::vector<int>, int>;
using G4IRouteRecordTuple = std::tuple<std::string,
                                       std::string,
                                       int,
                                       std::string,
                                       int,
                                       int,
                                       double,
                                       double,
                                       double>;
using G4IWindowTuple = std::tuple<std::string,
                                  int,
                                  int,
                                  std::string,
                                  std::string,
                                  std::vector<std::pair<int, int>>,
                                  std::vector<EdgeFaultWindowTuple>>;
using LegacyWindowFaultEventTuple = std::tuple<int, int, int, bool>;
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

czr005::ics::Graph graph_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time);

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

py::list legacy_window_planned_route_rows(
    const std::vector<czr005::ics::LegacyWindowPlannedRoute>& routes) {
  py::list rows;
  for (const auto& route : routes) {
    py::dict row;
    row["ordinal"] = route.ordinal;
    row["task_id"] = route.task_id;
    row["start"] = route.start;
    row["goal"] = route.goal;
    row["epoch"] = route.epoch;
    row["finish_time"] = route.finish_time;
    row["path"] = route.path;
    rows.append(row);
  }
  return rows;
}

py::dict legacy_no_fault_window_result_row(
    const czr005::ics::LegacyNoFaultWindowResult& window,
    double elapsed_seconds,
    bool include_routes) {
  py::dict result;
  result["start_epoch"] = window.start_epoch;
  result["max_epochs"] = window.max_epochs;
  result["max_new_tasks"] = window.max_new_tasks;
  result["epochs_run"] = window.epochs_run;
  result["generated_count"] = window.generated_count;
  result["planned_count"] = window.planned_count;
  result["completed_count"] = window.completed_count;
  result["fault_event_count"] = window.fault_event_count;
  result["repair_event_count"] = window.repair_event_count;
  result["generated_fault_edge_count"] = window.generated_fault_edge_count;
  result["generated_repair_edge_count"] = window.generated_repair_edge_count;
  result["active_fault_count"] = window.active_fault_count;
  result["unplanned_retry_count"] = window.unplanned_retry_count;
  result["active_route_count"] = window.active_route_count;
  result["unfinished_count"] = window.unfinished_count;
  result["route_size_checksum"] = window.route_size_checksum;
  result["route_location_checksum"] = window.route_location_checksum;
  result["last_epoch"] = window.last_epoch;
  result["elapsed_seconds"] = elapsed_seconds;
  if (include_routes) {
    result["planned_routes"] = legacy_window_planned_route_rows(window.planned_routes);
  }
  return result;
}

std::vector<czr005::ics::LegacyWindowFaultEvent> legacy_window_fault_events_from_tuples(
    const std::vector<LegacyWindowFaultEventTuple>& events) {
  std::vector<czr005::ics::LegacyWindowFaultEvent> result;
  result.reserve(events.size());
  for (const auto& event : events) {
    result.push_back(czr005::ics::LegacyWindowFaultEvent{std::get<0>(event),
                                                         std::get<1>(event),
                                                         std::get<2>(event),
                                                         std::get<3>(event)});
  }
  return result;
}

py::dict legacy_no_fault_window_summary(const std::string& map_path,
                                        const std::string& task_path,
                                        int start_epoch,
                                        int max_epochs,
                                        int max_new_tasks,
                                        bool include_routes,
                                        double fault_probability = 0.0,
                                        double repair_probability = 0.0,
                                        bool allow_ragged_heuristic = false) {
  const auto start_time = std::chrono::steady_clock::now();
  const auto legacy_map = czr005::ics::read_legacy_map2(map_path, 2.5, allow_ragged_heuristic);
  const auto window = czr005::ics::run_legacy_no_fault_window_from_files(
      legacy_map.graph,
      task_path,
      start_epoch,
      max_epochs,
      max_new_tasks,
      {},
      fault_probability,
      repair_probability);
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;
  return legacy_no_fault_window_result_row(window, elapsed.count(), include_routes);
}

py::dict legacy_scheduled_fault_window_summary(
    const std::string& map_path,
    const std::string& task_path,
    int start_epoch,
    int max_epochs,
    int max_new_tasks,
    const std::vector<LegacyWindowFaultEventTuple>& fault_schedule,
    bool include_routes,
    double fault_probability = 0.0,
    double repair_probability = 0.0,
    bool allow_ragged_heuristic = false) {
  const auto schedule = legacy_window_fault_events_from_tuples(fault_schedule);
  const auto start_time = std::chrono::steady_clock::now();
  const auto legacy_map = czr005::ics::read_legacy_map2(map_path, 2.5, allow_ragged_heuristic);
  const auto window = czr005::ics::run_legacy_no_fault_window_from_files(
      legacy_map.graph,
      task_path,
      start_epoch,
      max_epochs,
      max_new_tasks,
      schedule,
      fault_probability,
      repair_probability);
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;
  return legacy_no_fault_window_result_row(window, elapsed.count(), include_routes);
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

struct G4HFallbackWeights {
  double static_weight = 1.0;
  double wait_weight = 0.0;
  double pressure_weight = 0.0;
  double loop_weight = 12.0;
  double backtrack_weight = 6.0;
  double traffic_weight = 0.0;
  double progress_weight = 0.0;
  double slack_wait_multiplier = 0.0;
  double fault_penalty = 1.0e9;
};

G4HFallbackWeights g4h_fallback_weights(const std::string& fallback_name) {
  G4HFallbackWeights weights;
  if (fallback_name == "static_distance") {
    weights.progress_weight = 0.1;
  } else if (fallback_name == "node_window_aware") {
    weights.wait_weight = 1.4;
    weights.pressure_weight = 4.0;
    weights.progress_weight = 0.2;
  } else if (fallback_name == "node_window_pibt_lite") {
    weights.wait_weight = 1.8;
    weights.pressure_weight = 6.0;
    weights.loop_weight = 18.0;
    weights.backtrack_weight = 10.0;
    weights.progress_weight = 0.35;
    weights.slack_wait_multiplier = 0.4;
  } else if (fallback_name == "fault_aware_node_window_pibt_lite") {
    weights.wait_weight = 1.8;
    weights.pressure_weight = 6.0;
    weights.loop_weight = 24.0;
    weights.backtrack_weight = 12.0;
    weights.progress_weight = 0.45;
    weights.slack_wait_multiplier = 0.4;
  } else if (fallback_name == "cycle_memory_penalty_low") {
    weights.wait_weight = 1.8;
    weights.pressure_weight = 6.0;
    weights.loop_weight = 30.0;
    weights.backtrack_weight = 10.0;
    weights.progress_weight = 0.35;
    weights.slack_wait_multiplier = 0.4;
  } else if (fallback_name == "cycle_memory_penalty_mid") {
    weights.wait_weight = 1.8;
    weights.pressure_weight = 6.0;
    weights.loop_weight = 60.0;
    weights.backtrack_weight = 12.0;
    weights.progress_weight = 0.45;
    weights.slack_wait_multiplier = 0.4;
  } else if (fallback_name == "cycle_memory_penalty_high" || fallback_name == "fallback_no_repeat_ring") {
    weights.wait_weight = 1.8;
    weights.pressure_weight = 6.0;
    weights.loop_weight = 120.0;
    weights.backtrack_weight = 20.0;
    weights.progress_weight = 0.5;
    weights.slack_wait_multiplier = 0.4;
  } else if (fallback_name == "tabu_recent_nodes_8" || fallback_name == "tabu_recent_nodes_16") {
    weights.wait_weight = 1.8;
    weights.pressure_weight = 6.0;
    weights.loop_weight = 90.0;
    weights.backtrack_weight = 20.0;
    weights.progress_weight = 0.45;
    weights.slack_wait_multiplier = 0.4;
  } else if (fallback_name == "goal_progress_guard" || fallback_name == "model_margin_plus_cycle_guard") {
    weights.wait_weight = 1.8;
    weights.pressure_weight = 6.0;
    weights.loop_weight = 60.0;
    weights.backtrack_weight = 12.0;
    weights.progress_weight = 1.2;
    weights.slack_wait_multiplier = 0.4;
  } else if (fallback_name == "escape_cycle_depth2" || fallback_name == "escape_cycle_depth3") {
    weights.wait_weight = 1.6;
    weights.pressure_weight = 6.0;
    weights.loop_weight = 70.0;
    weights.backtrack_weight = 15.0;
    weights.traffic_weight = 4.0;
    weights.progress_weight = 0.45;
  } else if (fallback_name == "bounded_local_search") {
    weights.wait_weight = 1.6;
    weights.pressure_weight = 6.0;
    weights.loop_weight = 22.0;
    weights.backtrack_weight = 12.0;
    weights.traffic_weight = 4.0;
    weights.progress_weight = 0.35;
  } else if (fallback_name != "none") {
    throw std::invalid_argument("unknown G4H fallback: " + fallback_name);
  }
  return weights;
}

void g4h_expect_size(const std::vector<double>& values,
                     std::size_t expected,
                     const std::string& name) {
  if (values.size() != expected) {
    throw std::invalid_argument(name + " size must match candidates");
  }
}

void g4h_expect_size_bool(const std::vector<bool>& values,
                          std::size_t expected,
                          const std::string& name) {
  if (values.size() != expected) {
    throw std::invalid_argument(name + " size must match candidates");
  }
}

py::dict g4h_no_astar_policy_decision(
    const std::vector<std::vector<double>>& w1,
    const std::vector<double>& b1,
    const std::vector<double>& w2,
    double b2,
    const std::vector<std::vector<double>>& features,
    const std::vector<int>& candidates,
    const std::vector<double>& historical_risk,
    const std::vector<double>& bottleneck_score,
    double risk_margin_threshold,
    double risk_historical_threshold,
    double risk_bottleneck_threshold,
    const std::string& fallback_name,
    const std::vector<double>& static_cost,
    const std::vector<double>& wait_seconds,
    const std::vector<double>& pressure,
    const std::vector<double>& progress,
    const std::vector<double>& loop_penalty,
    const std::vector<double>& backtrack,
    const std::vector<double>& traffic_penalty,
    const std::vector<double>& slack_pressure,
    const std::vector<double>& lookahead_cost,
    const std::vector<bool>& faulted) {
  if (features.empty() || candidates.empty()) {
    throw std::invalid_argument("G4H candidates/features must not be empty");
  }
  if (features.size() != candidates.size()) {
    throw std::invalid_argument("features size must match candidates");
  }
  const std::size_t count = candidates.size();
  g4h_expect_size(historical_risk, count, "historical_risk");
  g4h_expect_size(bottleneck_score, count, "bottleneck_score");
  g4h_expect_size(static_cost, count, "static_cost");
  g4h_expect_size(wait_seconds, count, "wait_seconds");
  g4h_expect_size(pressure, count, "pressure");
  g4h_expect_size(progress, count, "progress");
  g4h_expect_size(loop_penalty, count, "loop_penalty");
  g4h_expect_size(backtrack, count, "backtrack");
  g4h_expect_size(traffic_penalty, count, "traffic_penalty");
  g4h_expect_size(slack_pressure, count, "slack_pressure");
  g4h_expect_size(lookahead_cost, count, "lookahead_cost");
  g4h_expect_size_bool(faulted, count, "faulted");

  const czr005::ics::EdgeScoreModel model(w1, b1, w2, b2);
  const auto scores = model.scores(features);
  int predicted_index = 0;
  for (std::size_t index = 1; index < scores.size(); ++index) {
    if (scores[index] > scores[static_cast<std::size_t>(predicted_index)]) {
      predicted_index = static_cast<int>(index);
    }
  }
  std::vector<double> sorted_scores = scores;
  std::sort(sorted_scores.begin(), sorted_scores.end(), std::greater<double>());
  const double margin = sorted_scores.size() > 1 ? sorted_scores[0] - sorted_scores[1] : 999.0;
  const bool should_fallback =
      margin < risk_margin_threshold ||
      historical_risk[static_cast<std::size_t>(predicted_index)] >= risk_historical_threshold ||
      bottleneck_score[static_cast<std::size_t>(predicted_index)] >= risk_bottleneck_threshold;

  int selected_index = predicted_index;
  std::string decision_source = "model";
  std::vector<double> fallback_scores(count, 0.0);
  if (should_fallback && fallback_name != "none") {
    const auto weights = g4h_fallback_weights(fallback_name);
    double best_score = weights.fault_penalty;
    selected_index = -1;
    for (std::size_t index = 0; index < count; ++index) {
      double value = weights.fault_penalty;
      if (!faulted[index]) {
        value = weights.static_weight * static_cost[index] +
                weights.wait_weight * wait_seconds[index] +
                weights.pressure_weight * pressure[index] +
                weights.loop_weight * loop_penalty[index] +
                weights.backtrack_weight * backtrack[index] +
                weights.traffic_weight * traffic_penalty[index] -
                weights.progress_weight * progress[index] +
                weights.slack_wait_multiplier * slack_pressure[index] +
                lookahead_cost[index];
      }
      fallback_scores[index] = value;
      if (selected_index < 0 || value < best_score ||
          (value == best_score && candidates[index] < candidates[static_cast<std::size_t>(selected_index)])) {
        best_score = value;
        selected_index = static_cast<int>(index);
      }
    }
    if (selected_index < 0) {
      throw std::invalid_argument("no fallback candidate selected");
    }
    decision_source = fallback_name;
  }

  py::dict result;
  result["predicted_index"] = predicted_index;
  result["predicted_next"] = candidates[static_cast<std::size_t>(predicted_index)];
  result["margin"] = margin;
  result["model_scores"] = scores;
  result["should_fallback"] = should_fallback;
  result["selected_index"] = selected_index;
  result["selected_next"] = candidates[static_cast<std::size_t>(selected_index)];
  result["decision_source"] = decision_source;
  result["fallback_scores"] = fallback_scores;
  result["runtime_full_cie_astar_calls"] = 0;
  return result;
}

constexpr double G4I_EPSILON = 1.0e-6;
constexpr double G4I_UNREACHABLE = 1.0e9;

struct G4IWindow {
  std::string name;
  int task_offset = 0;
  int max_tasks = 0;
  std::string context;
  std::string source;
  std::set<std::pair<int, int>> fault_edges;
  std::vector<EdgeFaultWindowTuple> fault_windows;
};

struct G4IRouteRecord {
  std::string experiment_scope;
  std::string window_name;
  int task_id = 0;
  std::string segment_id;
  int start = 0;
  int goal = 0;
  double entry_time = 0.0;
  double attempt_time = 0.0;
  double std_time = 0.0;
};

struct G4ITrafficMemory {
  std::map<int, int> node_visits;
  std::map<std::pair<int, int>, int> edge_visits;
  std::map<int, double> node_wait_seconds;

  void update(int current, int selected, double wait_seconds) {
    node_visits[selected] += 1;
    edge_visits[{current, selected}] += 1;
    node_wait_seconds[selected] += std::max(0.0, wait_seconds);
  }

  [[nodiscard]] double penalty(int current, int selected) const {
    const auto node_found = node_visits.find(selected);
    const auto edge_found = edge_visits.find({current, selected});
    const auto wait_found = node_wait_seconds.find(selected);
    const double node_load = std::log1p(node_found == node_visits.end() ? 0.0 : node_found->second);
    const double edge_load = std::log1p(edge_found == edge_visits.end() ? 0.0 : edge_found->second);
    const double wait_load = std::log1p(wait_found == node_wait_seconds.end() ? 0.0 : wait_found->second);
    return node_load + edge_load + 0.1 * wait_load;
  }
};

struct G4IFallbackDecision {
  int selected_index = -1;
  std::string decision_source = "model";
  std::string reason;
  std::vector<double> scores;
  std::vector<double> static_cost;
  std::vector<double> wait_seconds;
  std::vector<double> pressure;
  std::vector<double> progress;
  std::vector<double> loop_penalty;
  std::vector<double> backtrack;
  std::vector<double> traffic_penalty;
  std::vector<double> slack_pressure;
  std::vector<double> lookahead_cost;
  std::vector<bool> faulted;
};

struct G4ITaskResult {
  std::string policy;
  std::string experiment_scope;
  std::string window_name;
  int task_id = 0;
  std::string segment_id;
  double attempt_time = 0.0;
  bool goal_reached = false;
  std::string failed_reason;
  std::vector<int> path;
  int steps = 0;
  double finish_time = 0.0;
  double wait_seconds = 0.0;
  int wait_events = 0;
  double source_wait_seconds = 0.0;
  int source_retry_count = 0;
  int loop_count = 0;
  int nonprogress_steps = 0;
  int model_inference_count = 0;
  int model_selected_decision_count = 0;
  int rule_fallback_calls = 0;
  int bounded_local_search_calls = 0;
  int full_cie_astar_fallback_calls = 0;
  int node_window_conflicts = 0;
  int edge_overlap_diagnostic_count = 0;
};

std::vector<G4IWindow> g4i_windows_from_tuples(const std::vector<G4IWindowTuple>& window_records) {
  std::vector<G4IWindow> windows;
  windows.reserve(window_records.size());
  for (const auto& [name, task_offset, max_tasks, context, source, fault_edges, fault_windows] : window_records) {
    G4IWindow window;
    window.name = name;
    window.task_offset = task_offset;
    window.max_tasks = max_tasks;
    window.context = context;
    window.source = source;
    window.fault_edges.insert(fault_edges.begin(), fault_edges.end());
    window.fault_windows = fault_windows;
    windows.push_back(window);
  }
  return windows;
}

std::vector<G4IRouteRecord> g4i_routes_from_tuples(const std::vector<G4IRouteRecordTuple>& route_records) {
  std::vector<G4IRouteRecord> routes;
  routes.reserve(route_records.size());
  for (const auto& [experiment_scope,
                    window_name,
                    task_id,
                    segment_id,
                    start,
                    goal,
                    entry_time,
                    attempt_time,
                    std_time] : route_records) {
    routes.push_back(G4IRouteRecord{
        experiment_scope, window_name, task_id, segment_id, start, goal, entry_time, attempt_time, std_time});
  }
  return routes;
}

double g4i_scale(double value, double denominator) {
  return std::max(-20.0, std::min(20.0, value / denominator));
}

int g4i_overlap_count(const std::vector<std::pair<double, double>>& intervals,
                      double start,
                      double end) {
  int count = 0;
  auto iter = std::lower_bound(
      intervals.begin(), intervals.end(), std::make_pair(start, -std::numeric_limits<double>::infinity()));
  if (iter != intervals.begin()) {
    --iter;
  }
  for (; iter != intervals.end(); ++iter) {
    const auto [left, right] = *iter;
    if (right < start) {
      continue;
    }
    if (left > end) {
      break;
    }
    if (!(end < left || start > right)) {
      ++count;
    }
  }
  return count;
}

void g4i_insert_interval_sorted(std::map<int, std::vector<std::pair<double, double>>>& reservations,
                                int node,
                                std::pair<double, double> interval) {
  auto& intervals = reservations[node];
  const auto pos = std::upper_bound(
      intervals.begin(), intervals.end(), interval, [](const auto& left, const auto& right) {
        return std::make_tuple(left.first, left.second) < std::make_tuple(right.first, right.second);
      });
  intervals.insert(pos, interval);
}

struct G4IReservationSemantics {
  std::string name = "baseline";
  bool open_end_boundary = false;
  bool skip_source_lookup = false;
  bool reserve_source_node = true;
};

G4IReservationSemantics g4i_reservation_semantics_from_name(const std::string& name) {
  G4IReservationSemantics semantics;
  semantics.name = name.empty() ? "baseline" : name;
  if (semantics.name == "baseline") {
    return semantics;
  }
  if (semantics.name == "reservation_open_end_boundary" ||
      semantics.name == "entry_node_open_interval") {
    semantics.open_end_boundary = true;
    return semantics;
  }
  if (semantics.name == "source_node_no_reservation") {
    semantics.open_end_boundary = true;
    semantics.skip_source_lookup = true;
    semantics.reserve_source_node = false;
    return semantics;
  }
  if (semantics.name == "storage_segment_independent_reservation") {
    semantics.open_end_boundary = true;
    return semantics;
  }
  if (semantics.name == "source_node_zero_service" ||
      semantics.name == "java_service_time_parity") {
    return semantics;
  }
  throw std::invalid_argument("unknown G4I reservation semantics: " + name);
}

bool g4i_interval_blocks(const G4IReservationSemantics& semantics,
                         double left,
                         double right,
                         double start,
                         double end) {
  if (semantics.open_end_boundary) {
    if (right <= left || end <= start) {
      return false;
    }
    return start < right && end > left;
  }
  return !(end < left || start > right);
}

double g4i_earliest_safe(const std::map<int, std::vector<std::pair<double, double>>>& reservations,
                         int node,
                         double start,
                         double service,
                         const G4IReservationSemantics& semantics,
                         int* scan_count = nullptr) {
  double current = start;
  const auto found = reservations.find(node);
  if (found == reservations.end()) {
    return current;
  }
  const auto& intervals = found->second;
  auto iter = std::lower_bound(
      intervals.begin(), intervals.end(), std::make_pair(start, -std::numeric_limits<double>::infinity()));
  if (iter != intervals.begin()) {
    --iter;
  }
  for (; iter != intervals.end(); ++iter) {
    const auto [left, right] = *iter;
    if (scan_count != nullptr) {
      *scan_count += 1;
    }
    const double end = current + service;
    if (right < current) {
      continue;
    }
    if (semantics.open_end_boundary ? end <= left : end < left) {
      return current;
    }
    if (g4i_interval_blocks(semantics, left, right, current, end)) {
      current = semantics.open_end_boundary ? right : right + G4I_EPSILON;
    }
  }
  return current;
}

bool g4i_edge_faulted(const G4IWindow& window, int current, int next, double ready_time) {
  if (window.fault_edges.find({current, next}) != window.fault_edges.end()) {
    return true;
  }
  for (const auto& [start, end, fault_start, repair_time] : window.fault_windows) {
    if (start == current && end == next && fault_start <= ready_time && ready_time < repair_time) {
      return true;
    }
  }
  return false;
}

bool g4i_fault_dead_end_within_depth(const czr005::ics::Graph& graph,
                                     const G4IWindow& window,
                                     int node,
                                     double ready_time,
                                     int depth,
                                     std::set<int>& visiting) {
  if (depth < 0) {
    return false;
  }
  if (!visiting.insert(node).second) {
    return false;
  }
  const auto outgoing = graph.outgoing(node);
  if (outgoing.empty()) {
    visiting.erase(node);
    return false;
  }
  std::vector<int> available;
  for (const int next : outgoing) {
    const auto& edge = graph.edge(node, next);
    if (!g4i_edge_faulted(window, node, next, ready_time + edge.travel_time())) {
      available.push_back(next);
    }
  }
  if (available.empty()) {
    visiting.erase(node);
    return true;
  }
  for (const int next : available) {
    const auto& edge = graph.edge(node, next);
    if (!g4i_fault_dead_end_within_depth(graph,
                                         window,
                                         next,
                                         ready_time + edge.travel_time() + graph.service_time(next),
                                         depth - 1,
                                         visiting)) {
      visiting.erase(node);
      return false;
    }
  }
  visiting.erase(node);
  return true;
}

bool g4i_fault_dead_end_within_depth(const czr005::ics::Graph& graph,
                                     const G4IWindow& window,
                                     int node,
                                     double ready_time,
                                     int depth) {
  std::set<int> visiting;
  return g4i_fault_dead_end_within_depth(graph, window, node, ready_time, depth, visiting);
}

int g4i_hop_distance(const czr005::ics::Graph& graph,
                     int start,
                     int goal,
                     std::map<std::pair<int, int>, int>& cache) {
  const auto key = std::make_pair(start, goal);
  const auto found = cache.find(key);
  if (found != cache.end()) {
    return found->second;
  }
  if (start == goal) {
    cache[key] = 0;
    return 0;
  }
  std::deque<std::pair<int, int>> queue;
  std::set<int> seen;
  queue.push_back({start, 0});
  seen.insert(start);
  while (!queue.empty()) {
    const auto [node, depth] = queue.front();
    queue.pop_front();
    for (const int next : graph.outgoing(node)) {
      if (next == goal) {
        cache[key] = depth + 1;
        return depth + 1;
      }
      if (seen.insert(next).second) {
        queue.push_back({next, depth + 1});
      }
    }
  }
  cache[key] = 999;
  return 999;
}

int g4i_downstream_pressure(const czr005::ics::Graph& graph,
                            const std::map<int, std::vector<std::pair<double, double>>>& reservations,
                            int candidate,
                            int goal,
                            double arrival_time,
                            int depth) {
  if (depth <= 0) {
    return 0;
  }
  const double service_end = arrival_time + graph.service_time(candidate);
  const auto found = reservations.find(candidate);
  int total = found == reservations.end() ? 0 : g4i_overlap_count(found->second, arrival_time, service_end);
  if (candidate == goal) {
    return total;
  }
  for (const int next : graph.outgoing(candidate)) {
    const auto& edge = graph.edge(candidate, next);
    total += g4i_downstream_pressure(graph, reservations, next, goal, service_end + edge.travel_time(), depth - 1);
  }
  return total;
}

bool g4i_vector_equal(const std::vector<int>& left, const std::vector<int>& right) {
  return left.size() == right.size() && std::equal(left.begin(), left.end(), right.begin());
}

double g4i_historical_risk(const std::vector<G4IHistoricalRiskRuleTuple>& rules,
                           int current,
                           const std::vector<int>& candidates,
                           int candidate) {
  for (const auto& [rule_current, rule_candidates, predicted_next] : rules) {
    if (rule_current == current && predicted_next == candidate && g4i_vector_equal(rule_candidates, candidates)) {
      return 1.0;
    }
  }
  return 0.0;
}

bool g4i_rule_override(const std::vector<G4IFallbackRuleTuple>& rules,
                       int current,
                       int goal,
                       const std::vector<int>& candidates,
                       int predicted_next) {
  for (const auto& [rule_current, rule_goal, rule_candidates, rule_predicted] : rules) {
    if (rule_current == current && rule_goal == goal && rule_predicted == predicted_next &&
        g4i_vector_equal(rule_candidates, candidates)) {
      return true;
    }
  }
  return false;
}

std::vector<double> g4i_feature_row(const czr005::ics::Graph& graph,
                                    const G4IWindow& window,
                                    const std::map<int, std::vector<std::pair<double, double>>>& reservations,
                                    const std::vector<G4IHistoricalRiskRuleTuple>& historical_rules,
                                    std::map<std::pair<int, int>, int>& hop_cache,
                                    int current,
                                    int goal,
                                    int candidate,
                                    const std::vector<int>& candidates,
                                    double ready_time,
                                    double std_time) {
  const auto& edge = graph.edge(current, candidate);
  const double arrival = ready_time + edge.travel_time();
  const double service = graph.service_time(candidate);
  const auto current_found = reservations.find(current);
  const auto candidate_found = reservations.find(candidate);
  const int local_pressure = current_found == reservations.end()
                                 ? 0
                                 : g4i_overlap_count(current_found->second,
                                                     ready_time,
                                                     ready_time + graph.service_time(current));
  const int candidate_pressure = candidate_found == reservations.end()
                                     ? 0
                                     : g4i_overlap_count(candidate_found->second, arrival, arrival + service);
  std::map<int, double> static_costs;
  double best_cost = G4I_UNREACHABLE;
  for (const int node : candidates) {
    const double cost = graph.edge(current, node).travel_time() + graph.heuristic(node, goal);
    static_costs[node] = cost;
    best_cost = std::min(best_cost, cost);
  }
  const int out_degree = static_cast<int>(graph.outgoing(candidate).size());
  double bottleneck = std::max(0.0, 2.0 - static_cast<double>(out_degree));
  if (g4i_edge_faulted(window, current, candidate, ready_time)) {
    bottleneck += 5.0;
  }
  const double current_heuristic = graph.heuristic(current, goal);
  const double goal_direction = current_heuristic - graph.heuristic(candidate, goal);
  const double time_slack = std_time - ready_time;
  return {
      g4i_scale(graph.heuristic(candidate, goal), 100.0),
      g4i_scale(edge.travel_time(), 50.0),
      g4i_scale(service, 10.0),
      g4i_scale(static_cast<double>(graph.node(candidate).node_type), 10.0),
      g4i_edge_faulted(window, current, candidate, ready_time) ? 1.0 : 0.0,
      candidate == goal ? 1.0 : 0.0,
      g4i_scale(time_slack, 10000.0),
      g4i_scale(static_cast<double>(current), 100.0),
      g4i_scale(static_cast<double>(goal), 100.0),
      g4i_scale(static_cast<double>(candidates.size()), 10.0),
      candidates.size() > 1 ? 1.0 : 0.0,
      g4i_scale(static_cast<double>(local_pressure), 10.0),
      g4i_scale(static_cast<double>(candidate_pressure), 10.0),
      g4i_scale(static_cast<double>(g4i_downstream_pressure(graph, reservations, candidate, goal, arrival, 2)), 20.0),
      g4i_scale(static_cast<double>(g4i_downstream_pressure(graph, reservations, candidate, goal, arrival, 3)), 30.0),
      g4i_scale(static_cast<double>(g4i_hop_distance(graph, candidate, goal, hop_cache)), 20.0),
      g4i_scale(static_costs[candidate] - best_cost, 50.0),
      g4i_scale(bottleneck, 10.0),
      g4i_scale(goal_direction, 100.0),
      g4i_scale(g4i_historical_risk(historical_rules, current, candidates, candidate), 1.0),
      0.0,
      0.0,
  };
}

double g4i_lookahead_cost(const czr005::ics::Graph& graph,
                          const G4IWindow& window,
                          const G4HFallbackWeights& weights,
                          const std::map<int, std::vector<std::pair<double, double>>>& reservations,
                          int current,
                          int goal,
                          double ready_time,
                          const std::vector<int>& path,
                          int depth) {
  if (current == goal) {
    return 0.0;
  }
  if (depth <= 0) {
    return 0.15 * graph.heuristic(current, goal);
  }
  std::vector<int> outgoing = graph.outgoing(current);
  outgoing.erase(std::remove_if(outgoing.begin(),
                                outgoing.end(),
                                [&](int next) { return g4i_edge_faulted(window, current, next, ready_time); }),
                 outgoing.end());
  std::sort(outgoing.begin(), outgoing.end(), [&](int left, int right) {
    const double left_cost = graph.edge(current, left).travel_time() + graph.heuristic(left, goal);
    const double right_cost = graph.edge(current, right).travel_time() + graph.heuristic(right, goal);
    return std::make_pair(left_cost, left) < std::make_pair(right_cost, right);
  });
  double best = G4I_UNREACHABLE;
  const std::size_t limit = std::min<std::size_t>(3, outgoing.size());
  for (std::size_t index = 0; index < limit; ++index) {
    const int next = outgoing[index];
    const auto& edge = graph.edge(current, next);
    const double arrival = ready_time + edge.travel_time();
    const double service = graph.service_time(next);
    const auto found = reservations.find(next);
    const int pressure =
        found == reservations.end() ? 0 : g4i_overlap_count(found->second, arrival, arrival + service);
    const double wait = static_cast<double>(pressure) * std::min(service, 1.0);
    const double loop = static_cast<double>(std::count(path.begin(), path.end(), next));
    double cost = 0.35 * edge.travel_time() + 0.2 * graph.heuristic(next, goal) +
                  weights.wait_weight * wait + 0.5 * weights.loop_weight * loop;
    auto next_path = path;
    next_path.push_back(next);
    cost += g4i_lookahead_cost(
        graph, window, weights, reservations, next, goal, arrival + wait + service, next_path, depth - 1);
    best = std::min(best, cost);
  }
  return best >= G4I_UNREACHABLE ? 0.5 * G4I_UNREACHABLE : best;
}

G4IFallbackDecision g4i_fallback_decision(
    const czr005::ics::Graph& graph,
    const G4IWindow& window,
    const std::map<int, std::vector<std::pair<double, double>>>& reservations,
    const G4IReservationSemantics& reservation_semantics,
    const G4ITrafficMemory& traffic,
    const std::vector<int>& path,
    const std::vector<int>& candidates,
    int current,
    int goal,
    double ready_time,
    double std_time,
    const std::string& fallback_name,
    int bounded_depth) {
  G4IFallbackDecision decision;
  decision.decision_source = fallback_name;
  const auto weights = g4h_fallback_weights(fallback_name);
  int depth = 1;
  if (fallback_name == "bounded_local_search") {
    depth = std::max(2, bounded_depth);
  } else if (fallback_name == "escape_cycle_depth2") {
    depth = 2;
  } else if (fallback_name == "escape_cycle_depth3") {
    depth = 3;
  }
  const bool fault_aware = fallback_name == "fault_aware_node_window_pibt_lite";
  const bool no_repeat_ring = fallback_name == "fallback_no_repeat_ring" ||
                              fallback_name == "model_margin_plus_cycle_guard";
  const bool progress_guard = fallback_name == "goal_progress_guard" ||
                              fallback_name == "model_margin_plus_cycle_guard";
  int tabu_window = 0;
  if (fallback_name == "tabu_recent_nodes_8") {
    tabu_window = 8;
  } else if (fallback_name == "tabu_recent_nodes_16") {
    tabu_window = 16;
  }
  auto recently_seen = [&](int candidate) {
    if (tabu_window <= 0) {
      return false;
    }
    int inspected = 0;
    for (auto iter = path.rbegin(); iter != path.rend() && inspected < tabu_window; ++iter, ++inspected) {
      if (*iter == candidate) {
        return true;
      }
    }
    return false;
  };
  bool has_tabu_escape = false;
  bool has_nonrepeat_escape = false;
  bool has_progress_escape = false;
  for (const int candidate : candidates) {
    if (g4i_edge_faulted(window, current, candidate, ready_time)) {
      continue;
    }
    if (!recently_seen(candidate)) {
      has_tabu_escape = true;
    }
    if (std::find(path.begin(), path.end(), candidate) == path.end()) {
      has_nonrepeat_escape = true;
    }
    if (graph.heuristic(current, goal) - graph.heuristic(candidate, goal) > 0.0) {
      has_progress_escape = true;
    }
  }
  decision.scores.assign(candidates.size(), G4I_UNREACHABLE);
  decision.static_cost.assign(candidates.size(), 0.0);
  decision.wait_seconds.assign(candidates.size(), 0.0);
  decision.pressure.assign(candidates.size(), 0.0);
  decision.progress.assign(candidates.size(), 0.0);
  decision.loop_penalty.assign(candidates.size(), 0.0);
  decision.backtrack.assign(candidates.size(), 0.0);
  decision.traffic_penalty.assign(candidates.size(), 0.0);
  decision.slack_pressure.assign(candidates.size(), 0.0);
  decision.lookahead_cost.assign(candidates.size(), 0.0);
  decision.faulted.assign(candidates.size(), false);
  double best_score = G4I_UNREACHABLE;
  for (std::size_t index = 0; index < candidates.size(); ++index) {
    const int candidate = candidates[index];
    const bool faulted = g4i_edge_faulted(window, current, candidate, ready_time);
    const auto& edge = graph.edge(current, candidate);
    const double arrival = ready_time + edge.travel_time();
    const double service = graph.service_time(candidate);
    const double service_start =
        g4i_earliest_safe(reservations, candidate, arrival, service, reservation_semantics);
    const auto found = reservations.find(candidate);
    const double pressure = found == reservations.end() ? 0.0 : static_cast<double>(g4i_overlap_count(found->second, arrival, arrival + service));
    const double wait = std::max(0.0, service_start - arrival);
    const double static_cost = edge.travel_time() + graph.heuristic(candidate, goal);
    const double progress = graph.heuristic(current, goal) - graph.heuristic(candidate, goal);
    const double loop_penalty = static_cast<double>(std::count(path.begin(), path.end(), candidate));
    const double backtrack = path.size() >= 2 && candidate == path[path.size() - 2] ? 1.0 : 0.0;
    const double traffic_penalty = traffic.penalty(current, candidate);
    const double slack = std::max(0.0, std_time - ready_time);
    const double slack_pressure = slack > 0.0 ? wait / std::max(1.0, slack) : wait;
    const double lookahead = depth > 1 ? g4i_lookahead_cost(graph,
                                                            window,
                                                            weights,
                                                            reservations,
                                                            candidate,
                                                            goal,
                                                            service_start + service,
                                                            [&]() {
                                                              auto next_path = path;
                                                              next_path.push_back(candidate);
                                                              return next_path;
                                                            }(),
                                                            depth - 1)
                                       : 0.0;
    double score = G4I_UNREACHABLE;
    if (!faulted) {
      double guard_penalty = 0.0;
      if (fault_aware && g4i_fault_dead_end_within_depth(graph, window, candidate, service_start + service, 3)) {
        guard_penalty += 5.0e8;
      }
      if (tabu_window > 0 && has_tabu_escape && recently_seen(candidate)) {
        guard_penalty += 5.0e8;
      }
      if (no_repeat_ring && has_nonrepeat_escape && loop_penalty > 0.0) {
        guard_penalty += 5.0e8;
      }
      if (progress_guard && has_progress_escape && progress <= 0.0) {
        guard_penalty += 1.0e6;
      }
      score = weights.static_weight * static_cost + weights.wait_weight * wait +
              weights.pressure_weight * pressure + weights.loop_weight * loop_penalty +
              weights.backtrack_weight * backtrack + weights.traffic_weight * traffic_penalty -
              weights.progress_weight * progress + weights.slack_wait_multiplier * slack_pressure + lookahead +
              guard_penalty;
    }
    decision.faulted[index] = faulted;
    decision.static_cost[index] = static_cost;
    decision.wait_seconds[index] = wait;
    decision.pressure[index] = pressure;
    decision.progress[index] = progress;
    decision.loop_penalty[index] = loop_penalty;
    decision.backtrack[index] = backtrack;
    decision.traffic_penalty[index] = traffic_penalty;
    decision.slack_pressure[index] = slack_pressure;
    decision.lookahead_cost[index] = lookahead;
    decision.scores[index] = score;
    if (decision.selected_index < 0 || score < best_score ||
        (score == best_score && candidate < candidates[static_cast<std::size_t>(decision.selected_index)])) {
      best_score = score;
      decision.selected_index = static_cast<int>(index);
    }
  }
  if (decision.selected_index < 0 || best_score >= G4I_UNREACHABLE) {
    decision.selected_index = -1;
    decision.reason = "all_candidates_faulted";
  } else {
    decision.reason = "selected_lowest_local_score";
  }
  return decision;
}

int g4i_node_window_conflicts(const std::map<int, std::vector<std::pair<double, double>>>& reservations,
                              const G4IReservationSemantics& reservation_semantics) {
  int conflicts = 0;
  for (const auto& [node, intervals] : reservations) {
    (void)node;
    for (std::size_t left_index = 0; left_index < intervals.size(); ++left_index) {
      for (std::size_t right_index = left_index + 1; right_index < intervals.size(); ++right_index) {
        const auto [left_start, left_end] = intervals[left_index];
        const auto [right_start, right_end] = intervals[right_index];
        if (g4i_interval_blocks(reservation_semantics, left_start, left_end, right_start, right_end)) {
          ++conflicts;
        }
      }
    }
  }
  return conflicts;
}

std::string g4irsf4_json_raw_value(const std::string& line, const std::string& key) {
  const std::string pattern = "\"" + key + "\"";
  const auto key_pos = line.find(pattern);
  if (key_pos == std::string::npos) {
    throw std::invalid_argument("missing JSONL task field: " + key);
  }
  const auto colon_pos = line.find(':', key_pos + pattern.size());
  if (colon_pos == std::string::npos) {
    throw std::invalid_argument("malformed JSONL task field: " + key);
  }
  std::size_t pos = colon_pos + 1;
  while (pos < line.size() && std::isspace(static_cast<unsigned char>(line[pos]))) {
    ++pos;
  }
  if (pos >= line.size()) {
    throw std::invalid_argument("empty JSONL task field: " + key);
  }
  if (line[pos] == '"') {
    std::string value;
    ++pos;
    bool escaped = false;
    for (; pos < line.size(); ++pos) {
      const char ch = line[pos];
      if (escaped) {
        value.push_back(ch);
        escaped = false;
        continue;
      }
      if (ch == '\\') {
        escaped = true;
        continue;
      }
      if (ch == '"') {
        return value;
      }
      value.push_back(ch);
    }
    throw std::invalid_argument("unterminated JSONL string field: " + key);
  }
  const std::size_t start = pos;
  while (pos < line.size() && line[pos] != ',' && line[pos] != '}') {
    ++pos;
  }
  std::size_t end = pos;
  while (end > start && std::isspace(static_cast<unsigned char>(line[end - 1]))) {
    --end;
  }
  return line.substr(start, end - start);
}

int g4irsf4_json_int_value(const std::string& line, const std::string& key) {
  return std::stoi(g4irsf4_json_raw_value(line, key));
}

double g4irsf4_json_double_value(const std::string& line, const std::string& key) {
  return std::stod(g4irsf4_json_raw_value(line, key));
}

std::vector<G4IRouteRecordTuple> g4irsf4_routes_from_jsonl(const std::string& task_jsonl_path,
                                                           const std::string& experiment_scope,
                                                           const std::string& window_name,
                                                           int max_tasks,
                                                           int* line_count,
                                                           int* order_violation_count) {
  std::ifstream input(task_jsonl_path);
  if (!input) {
    throw std::invalid_argument("failed to open G4IRSF4 task JSONL: " + task_jsonl_path);
  }
  std::vector<G4IRouteRecordTuple> routes;
  if (max_tasks > 0) {
    routes.reserve(static_cast<std::size_t>(max_tasks));
  }
  std::string line;
  std::tuple<double, int, std::string> previous_key{
      -std::numeric_limits<double>::infinity(), -1, ""};
  while (std::getline(input, line)) {
    if (line.empty()) {
      continue;
    }
    const int task_id = g4irsf4_json_int_value(line, "task_id");
    const std::string segment_id = g4irsf4_json_raw_value(line, "segment_id");
    const int start = g4irsf4_json_int_value(line, "start");
    const int goal = g4irsf4_json_int_value(line, "goal");
    const double pass_time = g4irsf4_json_double_value(line, "pass_time");
    const double std_time = g4irsf4_json_double_value(line, "std");
    const auto current_key = std::make_tuple(pass_time, task_id, segment_id);
    if (current_key < previous_key && order_violation_count != nullptr) {
      *order_violation_count += 1;
    }
    previous_key = current_key;
    routes.push_back(G4IRouteRecordTuple{
        experiment_scope, window_name, task_id, segment_id, start, goal, pass_time, pass_time, std_time});
    if (line_count != nullptr) {
      *line_count += 1;
    }
    if (max_tasks > 0 && static_cast<int>(routes.size()) >= max_tasks) {
      break;
    }
  }
  return routes;
}

using G4IClock = std::chrono::steady_clock;

void g4i_add_stage(std::map<std::string, double>& stage_seconds,
                   const std::string& stage,
                   const G4IClock::time_point& start_time,
                   bool enabled) {
  if (!enabled) {
    return;
  }
  const std::chrono::duration<double> elapsed = G4IClock::now() - start_time;
  stage_seconds[stage] += elapsed.count();
}

void g4i_add_count(std::map<std::string, double>& counters,
                   const std::string& name,
                   double value,
                   bool enabled) {
  if (enabled) {
    counters[name] += value;
  }
}

py::dict g4i_profile_dict(const std::map<std::string, double>& values) {
  py::dict row;
  for (const auto& [key, value] : values) {
    row[py::str(key)] = value;
  }
  return row;
}

py::dict g4i_no_astar_batch_replay(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<G4IWindowTuple>& window_records,
    const std::vector<G4IRouteRecordTuple>& route_records,
    const std::vector<std::vector<double>>& w1,
    const std::vector<double>& b1,
    const std::vector<double>& w2,
    double b2,
    double risk_margin_threshold,
    double risk_historical_threshold,
    double risk_bottleneck_threshold,
    const std::vector<G4IHistoricalRiskRuleTuple>& historical_risk_rules,
    const std::vector<G4IFallbackRuleTuple>& fallback_rules,
    const std::string& policy_name,
    bool use_model,
    bool rule_only,
    bool risk_gated_rule,
    const std::string& fallback_name,
    int bounded_depth,
    int max_steps,
    int trace_limit,
    bool summary_only,
    bool profile_enabled,
    bool enable_edge_overlap_diagnostic,
    bool audit_final_conflicts,
    const std::string& reservation_semantics_name = "baseline") {
  std::map<std::string, double> stage_seconds;
  std::map<std::string, double> profile_counters;

  auto stage_start = G4IClock::now();
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  const auto reservation_semantics = g4i_reservation_semantics_from_name(reservation_semantics_name);
  g4i_add_stage(stage_seconds, "graph_construction", stage_start, profile_enabled);

  stage_start = G4IClock::now();
  const czr005::ics::EdgeScoreModel model(w1, b1, w2, b2);
  g4i_add_stage(stage_seconds, "model_construction", stage_start, profile_enabled);

  stage_start = G4IClock::now();
  const auto windows = g4i_windows_from_tuples(window_records);
  const auto routes = g4i_routes_from_tuples(route_records);
  std::map<std::string, G4IWindow> window_by_name;
  for (const auto& window : windows) {
    window_by_name[window.name] = window;
  }
  std::map<std::string, std::vector<G4IRouteRecord>> routes_by_window;
  for (const auto& route : routes) {
    routes_by_window[route.window_name].push_back(route);
  }
  for (auto& [window_name, items] : routes_by_window) {
    (void)window_name;
    std::sort(items.begin(), items.end(), [](const G4IRouteRecord& left, const G4IRouteRecord& right) {
      return std::make_tuple(left.attempt_time, left.task_id, left.segment_id) <
             std::make_tuple(right.attempt_time, right.task_id, right.segment_id);
    });
  }
  g4i_add_stage(stage_seconds, "window_route_grouping", stage_start, profile_enabled);

  std::vector<G4ITaskResult> task_results;
  py::list trace_rows;
  int total_edge_overlap_diagnostic = 0;
  int peak_reservation_entries = 0;
  int peak_edge_interval_entries = 0;
  const auto start_time = G4IClock::now();
  for (const auto& [window_name, items] : routes_by_window) {
    const auto window_found = window_by_name.find(window_name);
    if (window_found == window_by_name.end()) {
      throw std::invalid_argument("missing G4I window: " + window_name);
    }
    const auto& window = window_found->second;
    std::map<int, std::vector<std::pair<double, double>>> reservations;
    std::map<std::pair<int, int>, std::vector<std::pair<double, double>>> edge_intervals;
    std::map<std::pair<int, int>, int> hop_cache;
    G4ITrafficMemory traffic;
    int current_reservation_entries = 0;
    int current_edge_interval_entries = 0;
    for (const auto& route : items) {
      G4ITaskResult result;
      result.policy = policy_name;
      result.experiment_scope = route.experiment_scope;
      result.window_name = window_name;
      result.task_id = route.task_id;
      result.segment_id = route.segment_id;
      result.attempt_time = route.attempt_time;
      int current = route.start;
      const int goal = route.goal;
      std::vector<int> path{current};
      std::string failed_reason;
      stage_start = G4IClock::now();
      int source_scan_count = 0;
      const double start_t1 =
          reservation_semantics.skip_source_lookup
              ? route.attempt_time
              : g4i_earliest_safe(reservations,
                                  current,
                                  route.attempt_time,
                                  graph.service_time(current),
                                  reservation_semantics,
                                  &source_scan_count);
      g4i_add_stage(stage_seconds, "source_reservation_lookup", stage_start, profile_enabled);
      g4i_add_count(profile_counters, "earliest_safe_lookup_count", 1.0, profile_enabled);
      g4i_add_count(profile_counters, "earliest_safe_scan_count", source_scan_count, profile_enabled);
      const double source_wait = std::max(0.0, start_t1 - route.attempt_time);
      result.source_wait_seconds = source_wait;
      if (source_wait > G4I_EPSILON) {
        result.wait_seconds += source_wait;
        result.wait_events += 1;
        result.source_retry_count += 1;
      }
      double current_t2 = start_t1 + graph.service_time(current);
      if (reservation_semantics.reserve_source_node) {
        stage_start = G4IClock::now();
        g4i_insert_interval_sorted(reservations, current, {start_t1, current_t2});
        current_reservation_entries += 1;
        peak_reservation_entries = std::max(peak_reservation_entries, current_reservation_entries);
        g4i_add_stage(stage_seconds, "reservation_append", stage_start, profile_enabled);
      }
      const int steps_limit = rule_only ? std::min(max_steps, 24) : max_steps;
      for (int step = 0; step < steps_limit; ++step) {
        if (current == goal) {
          break;
        }
        stage_start = G4IClock::now();
        std::vector<int> candidates = graph.outgoing(current);
        g4i_add_stage(stage_seconds, "candidate_enumeration", stage_start, profile_enabled);
        if (candidates.empty()) {
          failed_reason = "no_outgoing_candidate";
          break;
        }
        std::vector<std::vector<double>> features;
        std::vector<double> historical_risk;
        std::vector<double> bottleneck_score;
        features.reserve(candidates.size());
        historical_risk.reserve(candidates.size());
        bottleneck_score.reserve(candidates.size());
        if (use_model) {
          for (const int candidate : candidates) {
            stage_start = G4IClock::now();
            features.push_back(g4i_feature_row(graph,
                                               window,
                                               reservations,
                                               historical_risk_rules,
                                               hop_cache,
                                               current,
                                               goal,
                                               candidate,
                                               candidates,
                                               current_t2,
                                               route.std_time));
            g4i_add_stage(stage_seconds, "feature_row_computation", stage_start, profile_enabled);
            stage_start = G4IClock::now();
            historical_risk.push_back(g4i_historical_risk(historical_risk_rules, current, candidates, candidate));
            g4i_add_stage(stage_seconds, "historical_risk_lookup", stage_start, profile_enabled);
            stage_start = G4IClock::now();
            double bottleneck = std::max(0.0, 2.0 - static_cast<double>(graph.outgoing(candidate).size()));
            if (g4i_edge_faulted(window, current, candidate, current_t2)) {
              bottleneck += 5.0;
            }
            bottleneck_score.push_back(bottleneck);
            g4i_add_stage(stage_seconds, "bottleneck_score_computation", stage_start, profile_enabled);
          }
        }
        int predicted_index = 0;
        double margin = 999.0;
        std::vector<double> model_scores;
        if (use_model) {
          stage_start = G4IClock::now();
          model_scores = model.scores(features);
          g4i_add_stage(stage_seconds, "model_inference", stage_start, profile_enabled);
          stage_start = G4IClock::now();
          for (std::size_t index = 1; index < model_scores.size(); ++index) {
            if (model_scores[index] > model_scores[static_cast<std::size_t>(predicted_index)]) {
              predicted_index = static_cast<int>(index);
            }
          }
          auto ordered = model_scores;
          std::sort(ordered.begin(), ordered.end(), std::greater<double>());
          margin = ordered.size() > 1 ? ordered[0] - ordered[1] : 999.0;
          g4i_add_stage(stage_seconds, "score_sort_margin", stage_start, profile_enabled);
          result.model_inference_count += 1;
        }
        const int predicted_next = candidates[static_cast<std::size_t>(predicted_index)];
        bool use_rule = rule_only;
        stage_start = G4IClock::now();
        if (risk_gated_rule && use_model) {
          use_rule = margin < risk_margin_threshold ||
                     historical_risk[static_cast<std::size_t>(predicted_index)] >= risk_historical_threshold ||
                     bottleneck_score[static_cast<std::size_t>(predicted_index)] >= risk_bottleneck_threshold ||
                     g4i_rule_override(fallback_rules, current, goal, candidates, predicted_next);
        }
        if (use_model && policy_name == "model_plus_pibt_lite_fault_aware_v1" &&
            g4i_fault_dead_end_within_depth(graph, window, predicted_next, current_t2, 3)) {
          use_rule = true;
        }
        if (use_model && fallback_name == "model_margin_plus_cycle_guard") {
          const double predicted_progress = graph.heuristic(current, goal) - graph.heuristic(predicted_next, goal);
          if (std::find(path.begin(), path.end(), predicted_next) != path.end() || predicted_progress <= 0.0) {
            use_rule = true;
          }
        }
        g4i_add_stage(stage_seconds, "risk_gate_rule_override", stage_start, profile_enabled);
        int selected = predicted_next;
        std::string decision_source = "model";
        std::string rule_reason;
        G4IFallbackDecision fallback_decision;
        if (use_rule) {
          stage_start = G4IClock::now();
          fallback_decision = g4i_fallback_decision(graph,
                                                    window,
                                                    reservations,
                                                    reservation_semantics,
                                                    traffic,
                                                    path,
                                                    candidates,
                                                    current,
                                                    goal,
                                                    current_t2,
                                                    route.std_time,
                                                    fallback_name,
                                                    bounded_depth);
          g4i_add_stage(stage_seconds, "pibt_lite_fallback_scoring", stage_start, profile_enabled);
          if (fallback_decision.selected_index < 0) {
            failed_reason = fallback_decision.reason;
            break;
          }
          selected = candidates[static_cast<std::size_t>(fallback_decision.selected_index)];
          decision_source = fallback_decision.decision_source;
          rule_reason = fallback_decision.reason;
          result.rule_fallback_calls += 1;
          if (fallback_name == "bounded_local_search") {
            result.bounded_local_search_calls += 1;
          }
        } else {
          result.model_selected_decision_count += 1;
        }
        stage_start = G4IClock::now();
        if (std::find(candidates.begin(), candidates.end(), selected) == candidates.end() ||
            g4i_edge_faulted(window, current, selected, current_t2)) {
          failed_reason = "invalid_or_faulted_runtime_selection";
          break;
        }
        g4i_add_stage(stage_seconds, "runtime_selection_validation", stage_start, profile_enabled);
        const auto& edge = graph.edge(current, selected);
        const double arrival = current_t2 + edge.travel_time();
        stage_start = G4IClock::now();
        int move_scan_count = 0;
        const double service_start = g4i_earliest_safe(reservations,
                                                       selected,
                                                       arrival,
                                                       graph.service_time(selected),
                                                       reservation_semantics,
                                                       &move_scan_count);
        g4i_add_stage(stage_seconds, "earliest_safe_reservation_lookup", stage_start, profile_enabled);
        g4i_add_count(profile_counters, "earliest_safe_lookup_count", 1.0, profile_enabled);
        g4i_add_count(profile_counters, "earliest_safe_scan_count", move_scan_count, profile_enabled);
        const double step_wait = std::max(0.0, service_start - arrival);
        const double service_end = service_start + graph.service_time(selected);
        const int visits_after = static_cast<int>(std::count(path.begin(), path.end(), selected)) + 1;
        if (step_wait > G4I_EPSILON) {
          result.wait_seconds += step_wait;
          result.wait_events += 1;
        }
        if (visits_after > 1) {
          result.loop_count += 1;
        }
        stage_start = G4IClock::now();
        const auto edge_key = std::make_pair(current, selected);
        int edge_overlap = 0;
        if (enable_edge_overlap_diagnostic) {
          edge_overlap = g4i_overlap_count(edge_intervals[edge_key], current_t2, arrival);
          result.edge_overlap_diagnostic_count += edge_overlap;
          total_edge_overlap_diagnostic += edge_overlap;
        }
        edge_intervals[edge_key].push_back({current_t2, arrival});
        current_edge_interval_entries += 1;
        peak_edge_interval_entries = std::max(peak_edge_interval_entries, current_edge_interval_entries);
        g4i_add_stage(stage_seconds, "edge_overlap_diagnostic", stage_start, profile_enabled);
        if (static_cast<int>(trace_rows.size()) < trace_limit) {
          stage_start = G4IClock::now();
          py::dict row;
          row["policy"] = policy_name;
          row["experiment_scope"] = route.experiment_scope;
          row["window_name"] = window_name;
          row["task_id"] = route.task_id;
          row["segment_id"] = route.segment_id;
          row["step_index"] = step;
          row["current_node"] = current;
          row["goal_node"] = goal;
          row["candidate_next_nodes"] = candidates;
          row["model_prediction"] = use_model ? predicted_next : -1;
          row["selected_next_node"] = selected;
          row["decision_source"] = decision_source;
          row["rule_reason"] = rule_reason;
          row["model_margin"] = use_model ? margin : 999.0;
          row["wait_seconds"] = step_wait;
          row["edge_overlap_diagnostic_only"] = edge_overlap;
          row["full_cie_astar_used"] = false;
          trace_rows.append(row);
          g4i_add_stage(stage_seconds, "trace_row_construction", stage_start, profile_enabled);
        }
        if (visits_after > 4) {
          failed_reason = "loop_detected";
          break;
        }
        stage_start = G4IClock::now();
        g4i_insert_interval_sorted(reservations, selected, {service_start, service_end});
        current_reservation_entries += 1;
        peak_reservation_entries = std::max(peak_reservation_entries, current_reservation_entries);
        g4i_add_stage(stage_seconds, "reservation_append", stage_start, profile_enabled);
        traffic.update(current, selected, step_wait);
        current = selected;
        current_t2 = service_end;
        path.push_back(current);
      }
      result.goal_reached = current == goal && failed_reason.empty();
      if (!result.goal_reached && failed_reason.empty()) {
        failed_reason = "max_steps_exhausted";
      }
      result.failed_reason = result.goal_reached ? "" : failed_reason;
      result.path = path;
      result.steps = static_cast<int>(path.size()) - 1;
      result.finish_time = result.goal_reached ? current_t2 : -1.0;
      result.nonprogress_steps = result.wait_events + result.loop_count;
      result.full_cie_astar_fallback_calls = 0;
      result.node_window_conflicts = 0;
      task_results.push_back(std::move(result));
    }
    stage_start = G4IClock::now();
    const int conflicts =
        audit_final_conflicts ? g4i_node_window_conflicts(reservations, reservation_semantics) : 0;
    g4i_add_stage(stage_seconds, "node_window_conflict_audit", stage_start, profile_enabled);
    if (conflicts > 0) {
      for (auto& task : task_results) {
        if (task.window_name == window_name) {
          task.node_window_conflicts = conflicts;
        }
      }
    }
  }
  const auto end_time = std::chrono::steady_clock::now();
  const std::chrono::duration<double> elapsed = end_time - start_time;

  py::list task_rows;
  std::map<std::string, std::vector<const G4ITaskResult*>> by_window;
  int total_planned = 0;
  int total_model_decisions = 0;
  int total_model_selected = 0;
  int total_rule_calls = 0;
  int total_bounded_calls = 0;
  int total_node_conflicts = 0;
  int total_source_retry = 0;
  int total_failed = 0;
  int total_loop_count = 0;
  int total_nonprogress_steps = 0;
  int total_wait_events = 0;
  std::map<std::string, int> failed_reason_counts;
  py::list failed_task_rows;
  constexpr int G4I_FAILED_TASK_ROW_LIMIT = 10000;
  stage_start = G4IClock::now();
  for (const auto& task : task_results) {
    by_window[task.window_name].push_back(&task);
    total_planned += task.goal_reached ? 1 : 0;
    if (!task.goal_reached) {
      total_failed += 1;
      failed_reason_counts[task.failed_reason] += 1;
    }
    total_model_decisions += task.model_inference_count;
    total_model_selected += task.model_selected_decision_count;
    total_rule_calls += task.rule_fallback_calls;
    total_bounded_calls += task.bounded_local_search_calls;
    total_node_conflicts += task.node_window_conflicts;
    total_source_retry += task.source_retry_count;
    total_loop_count += task.loop_count;
    total_nonprogress_steps += task.nonprogress_steps;
    total_wait_events += task.wait_events;
    if (!task.goal_reached && static_cast<int>(failed_task_rows.size()) < G4I_FAILED_TASK_ROW_LIMIT) {
      py::dict failed_row;
      failed_row["policy"] = task.policy;
      failed_row["experiment_scope"] = task.experiment_scope;
      failed_row["window_name"] = task.window_name;
      failed_row["task_id"] = task.task_id;
      failed_row["segment_id"] = task.segment_id;
      failed_row["attempt_time"] = task.attempt_time;
      failed_row["failed_reason"] = task.failed_reason;
      failed_row["path"] = task.path;
      failed_row["steps"] = task.steps;
      failed_row["wait_seconds"] = task.wait_seconds;
      failed_row["source_retry_count"] = task.source_retry_count;
      failed_row["loop_count"] = task.loop_count;
      failed_row["nonprogress_steps"] = task.nonprogress_steps;
      failed_row["model_inference_count"] = task.model_inference_count;
      failed_row["rule_fallback_calls"] = task.rule_fallback_calls;
      failed_row["node_window_conflicts"] = task.node_window_conflicts;
      failed_row["edge_overlap_diagnostic_only"] = task.edge_overlap_diagnostic_count;
      failed_task_rows.append(failed_row);
    }
    if (!summary_only) {
      py::dict row;
      row["policy"] = task.policy;
      row["experiment_scope"] = task.experiment_scope;
      row["window_name"] = task.window_name;
      row["task_id"] = task.task_id;
      row["segment_id"] = task.segment_id;
      row["attempt_time"] = task.attempt_time;
      row["goal_reached"] = task.goal_reached;
      row["failed_reason"] = task.failed_reason;
      row["path"] = task.path;
      row["steps"] = task.steps;
      if (task.goal_reached) {
        row["finish_time"] = task.finish_time;
      } else {
        row["finish_time"] = py::none();
      }
      row["wait_seconds"] = task.wait_seconds;
      row["wait_events"] = task.wait_events;
      row["source_wait_seconds"] = task.source_wait_seconds;
      row["source_retry_count"] = task.source_retry_count;
      row["loop_count"] = task.loop_count;
      row["nonprogress_steps"] = task.nonprogress_steps;
      row["model_inference_count"] = task.model_inference_count;
      row["model_selected_decision_count"] = task.model_selected_decision_count;
      row["rule_fallback_calls"] = task.rule_fallback_calls;
      row["bounded_local_search_calls"] = task.bounded_local_search_calls;
      row["full_cie_astar_fallback_calls"] = task.full_cie_astar_fallback_calls;
      row["node_window_conflicts"] = task.node_window_conflicts;
      row["edge_overlap_diagnostic_only"] = task.edge_overlap_diagnostic_count;
      task_rows.append(row);
    }
  }
  g4i_add_stage(stage_seconds, "task_row_construction", stage_start, profile_enabled);

  py::list per_window_rows;
  stage_start = G4IClock::now();
  for (const auto& [window_name, items] : by_window) {
    int planned = 0;
    int model_decisions = 0;
    int model_selected = 0;
    int rule_calls = 0;
    int bounded_calls = 0;
    int failures = 0;
    int loop_count = 0;
    int nonprogress = 0;
    int conflicts = 0;
    int source_retry = 0;
    int edge_overlap = 0;
    double wait_sum = 0.0;
    double transport_sum = 0.0;
    int transport_count = 0;
    for (const auto* task : items) {
      planned += task->goal_reached ? 1 : 0;
      failures += task->goal_reached ? 0 : 1;
      model_decisions += task->model_inference_count;
      model_selected += task->model_selected_decision_count;
      rule_calls += task->rule_fallback_calls;
      bounded_calls += task->bounded_local_search_calls;
      loop_count += task->loop_count;
      nonprogress += task->nonprogress_steps;
      conflicts += task->node_window_conflicts;
      source_retry += task->source_retry_count;
      edge_overlap += task->edge_overlap_diagnostic_count;
      wait_sum += task->wait_seconds;
      if (task->goal_reached) {
        transport_sum += task->finish_time - task->attempt_time;
        transport_count += 1;
      }
    }
    const auto window_found = window_by_name.find(window_name);
    py::dict row;
    row["policy"] = policy_name;
    row["window_name"] = window_name;
    row["planned_count"] = planned;
    row["scope_total"] = static_cast<int>(items.size());
    row["node_window_conflicts"] = conflicts;
    row["runtime_full_cie_astar_calls"] = 0;
    row["model_inference_count"] = model_decisions;
    row["model_selected_decision_count"] = model_selected;
    row["rule_fallback_calls"] = rule_calls;
    row["bounded_local_search_calls"] = bounded_calls;
    row["source_retry_count"] = source_retry;
    row["failed_count"] = failures;
    row["loop_count"] = loop_count;
    row["nonprogress_steps"] = nonprogress;
    row["avg_no_progress_steps_per_task"] = items.empty() ? 0.0 : static_cast<double>(nonprogress) / items.size();
    row["mean_wait_seconds"] = items.empty() ? 0.0 : wait_sum / items.size();
    row["mean_transport_time"] = transport_count > 0 ? transport_sum / transport_count : 0.0;
    row["edge_overlap_diagnostic_only"] = edge_overlap;
    row["window_offset"] = window_found == window_by_name.end() ? 0 : window_found->second.task_offset;
    row["window_size"] = window_found == window_by_name.end() ? static_cast<int>(items.size()) : window_found->second.max_tasks;
    row["context"] = window_found == window_by_name.end() ? "" : window_found->second.context;
    row["source"] = window_found == window_by_name.end() ? "" : window_found->second.source;
    row["stable"] = planned == static_cast<int>(items.size()) && conflicts == 0;
    per_window_rows.append(row);
  }
  g4i_add_stage(stage_seconds, "per_window_aggregation", stage_start, profile_enabled);

  py::dict summary;
  summary["policy"] = policy_name;
  summary["task_count"] = static_cast<int>(task_results.size());
  summary["planned_count"] = total_planned;
  summary["failed_count"] = total_failed;
  summary["unplanned_count"] = static_cast<int>(task_results.size()) - total_planned;
  summary["node_window_conflicts"] = total_node_conflicts;
  summary["runtime_full_cie_astar_calls"] = 0;
  summary["model_inference_count"] = total_model_decisions;
  summary["model_decisions"] = total_model_decisions;
  summary["model_selected_decision_count"] = total_model_selected;
  summary["rule_fallback_calls"] = total_rule_calls;
  summary["fallback_calls"] = total_rule_calls;
  summary["bounded_local_search_calls"] = total_bounded_calls;
  summary["source_retry_count"] = total_source_retry;
  summary["loop_count"] = total_loop_count;
  summary["nonprogress_steps"] = total_nonprogress_steps;
  summary["wait_events"] = total_wait_events;
  summary["edge_overlap_diagnostic_only"] = total_edge_overlap_diagnostic;
  summary["peak_reservation_entries"] = peak_reservation_entries;
  summary["peak_edge_interval_entries"] = peak_edge_interval_entries;
  summary["peak_memory_estimate_bytes"] =
      static_cast<long long>(peak_reservation_entries + peak_edge_interval_entries) *
      static_cast<long long>(sizeof(std::pair<double, double>));
  py::dict failed_counts;
  for (const auto& [reason, count] : failed_reason_counts) {
    failed_counts[py::str(reason)] = count;
  }
  summary["failed_reason_counts"] = failed_counts;
  summary["failed_task_rows_capped"] = total_failed > static_cast<int>(failed_task_rows.size());
  summary["elapsed_seconds"] = elapsed.count();
  summary["decisions_per_second"] =
      elapsed.count() > 0.0 ? static_cast<double>(total_model_decisions + total_rule_calls) / elapsed.count() : 0.0;
  summary["tasks_per_second"] =
      elapsed.count() > 0.0 ? static_cast<double>(task_results.size()) / elapsed.count() : 0.0;
  summary["zero_full_astar_task_share"] = 1.0;
  summary["runtime_loop_owner"] = "cpp";
  summary["full_cie_astar_runtime_fallback"] = false;
  summary["summary_only"] = summary_only;
  summary["profile_enabled"] = profile_enabled;
  summary["edge_overlap_diagnostic_enabled"] = enable_edge_overlap_diagnostic;
  summary["final_conflict_audit_enabled"] = audit_final_conflicts;
  summary["reservation_semantics"] = reservation_semantics.name;

  stage_start = G4IClock::now();
  py::dict payload;
  payload["summary"] = summary;
  payload["per_window"] = per_window_rows;
  payload["tasks"] = task_rows;
  payload["failed_tasks"] = failed_task_rows;
  payload["trace"] = trace_rows;
  payload["profile"] = g4i_profile_dict(stage_seconds);
  payload["profile_counters"] = g4i_profile_dict(profile_counters);
  g4i_add_stage(stage_seconds, "pybind_payload_construction", stage_start, profile_enabled);
  payload["profile"] = g4i_profile_dict(stage_seconds);
  return payload;
}

py::dict g4irsf4_no_astar_streaming_replay_from_jsonl(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::string& task_jsonl_path,
    const std::vector<std::vector<double>>& w1,
    const std::vector<double>& b1,
    const std::vector<double>& w2,
    double b2,
    double risk_margin_threshold,
    double risk_historical_threshold,
    double risk_bottleneck_threshold,
    const std::vector<G4IHistoricalRiskRuleTuple>& historical_risk_rules,
    const std::vector<G4IFallbackRuleTuple>& fallback_rules,
    const std::string& policy_name,
    bool use_model,
    bool rule_only,
    bool risk_gated_rule,
    const std::string& fallback_name,
    int bounded_depth,
    int max_steps,
    int trace_limit,
    bool summary_only,
    bool profile_enabled,
    bool enable_edge_overlap_diagnostic,
    bool audit_final_conflicts,
    const std::vector<std::pair<int, int>>& fault_edges,
    const std::vector<EdgeFaultWindowTuple>& fault_windows,
    int max_tasks,
    const std::string& reservation_semantics_name = "baseline") {
  const std::string window_name = "full_manifest_348824_continuous_state";
  const std::string experiment_scope = "g4irsf4_continuous_state_cpp_jsonl_stream";
  int line_count = 0;
  int order_violations = 0;
  auto route_records = g4irsf4_routes_from_jsonl(
      task_jsonl_path, experiment_scope, window_name, max_tasks, &line_count, &order_violations);
  const int window_size = static_cast<int>(route_records.size());
  std::vector<G4IWindowTuple> window_records;
  window_records.push_back(G4IWindowTuple{
      window_name,
      0,
      window_size,
      "continuous_full_manifest",
      "g4irsf2_high_flow_tasks_jsonl_cpp_stream",
      fault_edges,
      fault_windows});

  py::dict payload = g4i_no_astar_batch_replay(node_records,
                                               edge_records,
                                               heuristic_time,
                                               window_records,
                                               route_records,
                                               w1,
                                               b1,
                                               w2,
                                               b2,
                                               risk_margin_threshold,
                                               risk_historical_threshold,
                                               risk_bottleneck_threshold,
                                               historical_risk_rules,
                                               fallback_rules,
                                               policy_name,
                                               use_model,
                                               rule_only,
                                               risk_gated_rule,
                                               fallback_name,
                                               bounded_depth,
                                               max_steps,
                                               trace_limit,
                                               summary_only,
                                               profile_enabled,
                                               enable_edge_overlap_diagnostic,
                                               audit_final_conflicts,
                                               reservation_semantics_name);
  py::dict summary = payload["summary"].cast<py::dict>();
  summary["continuous_state"] = true;
  summary["chunk_reset_count"] = 0;
  summary["source_state_reset_between_tasks"] = false;
  summary["reservation_state_reset_between_tasks"] = false;
  summary["traffic_memory_reset_between_tasks"] = false;
  summary["reader_mode"] = "cpp_jsonl_stream_to_internal_records";
  summary["task_jsonl_path"] = task_jsonl_path;
  summary["jsonl_line_count"] = line_count;
  summary["task_order_violations"] = order_violations;
  summary["python_route_record_list_used"] = false;
  payload["summary"] = summary;
  return payload;
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

std::string canonical_merge_grant_rule_for_binding(
    const std::string& rule) {
  if (rule == "M0" ||
      rule == "M0_current_event_seq_earliest_known") {
    return "M0";
  }
  if (rule == "M1" || rule == "M1_fifo") {
    return "M1";
  }
  if (rule == "M2" ||
      rule == "M2_earliest_projected_arrival") {
    return "M2";
  }
  if (rule == "M3" || rule == "M3_deadline_aging") {
    return "M3";
  }
  if (rule == "M4" || rule == "M4_fairness_progress") {
    return "M4";
  }
  if (rule == "M5" || rule == "M5_local_externality") {
    return "M5";
  }
  if (rule == "M6" || rule == "M6_thesis_local") {
    return "M6";
  }
  throw std::invalid_argument(
      "merge_grant_rule must be M0, M1, M2, M3, M4, M5, or M6");
}

std::string canonical_merge_grant_timing_mode_for_binding(
    const std::string& timing_mode) {
  if (timing_mode == "eager" || timing_mode == "J0" ||
      timing_mode == "J0_F2_EAGER") {
    return "eager";
  }
  if (timing_mode == "jit_fifo" || timing_mode == "J1" ||
      timing_mode == "J1_F2_JIT_FIFO") {
    return "jit_fifo";
  }
  if (timing_mode == "jit_fair_aging_deadline" ||
      timing_mode == "J2" ||
      timing_mode == "J2_F2_JIT_FAIR_AGING_DEADLINE") {
    return "jit_fair_aging_deadline";
  }
  throw std::invalid_argument(
      "merge_grant_timing_mode must be eager, jit_fifo, or "
      "jit_fair_aging_deadline");
}

int strict_python_integer_argument(
    const py::handle& value,
    const char* name) {
  if (PyBool_Check(value.ptr()) ||
      !PyLong_Check(value.ptr())) {
    throw py::type_error(
        std::string(name) + " must be an integer, not bool");
  }
  const long long converted =
      PyLong_AsLongLong(value.ptr());
  if (converted == -1 && PyErr_Occurred()) {
    throw py::error_already_set();
  }
  if (converted <
          static_cast<long long>(
              std::numeric_limits<int>::min()) ||
      converted >
          static_cast<long long>(
              std::numeric_limits<int>::max())) {
    throw py::value_error(
        std::string(name) + " is outside the supported integer range");
  }
  return static_cast<int>(converted);
}

void validate_g4irsf16_self_sha256(const py::dict& artifact) {
  if (!artifact.contains("self_sha256") ||
      !py::isinstance<py::str>(artifact["self_sha256"])) {
    throw py::value_error("G4IRSF16 artifact self_sha256 missing");
  }
  py::dict payload =
      py::cast<py::dict>(artifact.attr("copy")());
  const std::string claimed =
      py::cast<std::string>(payload.attr("pop")("self_sha256"));
  const py::object json = py::module_::import("json");
  const py::tuple separators = py::make_tuple(",", ":");
  const std::string canonical = py::cast<std::string>(
      json.attr("dumps")(
          payload,
          py::arg("ensure_ascii") = false,
          py::arg("sort_keys") = true,
          py::arg("separators") = separators,
          py::arg("allow_nan") = false));
  const std::string observed =
      czr005::ics::canonical_map2_detail::sha256_hex(canonical);
  if (claimed != observed) {
    throw py::value_error("G4IRSF16 artifact self_sha256 mismatch");
  }
}

czr005::ics::G4IRSF16SelectiveLinearModelConfig
g4irsf16_model_config_from_artifact(
    const py::dict& artifact) {
  czr005::ics::G4IRSF16SelectiveLinearModelConfig config;
  if (artifact.empty()) {
    return config;
  }
  // This validation runs exactly once at binding setup. Native per-decision
  // inference performs no Python callback.
  validate_g4irsf16_self_sha256(artifact);
  const auto section = [&](const char* name) {
    if (!artifact.contains(name) ||
        !py::isinstance<py::dict>(artifact[name])) {
      throw py::value_error(
          std::string("G4IRSF16 model section missing: ") + name);
    }
    return py::reinterpret_borrow<py::dict>(artifact[name]);
  };
  const auto required_string = [&](const char* name) {
    if (!artifact.contains(name) ||
        !py::isinstance<py::str>(artifact[name])) {
      throw py::value_error(
          std::string("G4IRSF16 model string missing: ") + name);
    }
    return py::cast<std::string>(artifact[name]);
  };
  config.authorized = true;
  config.self_sha256_verified = true;
  config.schema = required_string("schema");
  config.kind = required_string("kind");
  config.action = required_string("action");
  config.artifact_sha256 = required_string("self_sha256");
  if (!artifact.contains("feature_names")) {
    throw py::value_error("G4IRSF16 feature_names missing");
  }
  config.feature_names =
      py::cast<std::vector<std::string>>(artifact["feature_names"]);
  const py::dict normalization = section("normalization");
  const py::dict bounds = section("training_bounds");
  const py::dict heads = section("heads");
  const py::dict thresholds = section("thresholds");
  config.mean =
      py::cast<std::vector<double>>(normalization["mean"]);
  config.scale =
      py::cast<std::vector<double>>(normalization["scale"]);
  config.feature_min =
      py::cast<std::vector<double>>(bounds["min"]);
  config.feature_max =
      py::cast<std::vector<double>>(bounds["max"]);
  config.benefit_logit =
      py::cast<std::vector<std::vector<double>>>(
          heads["benefit_logit"]);
  config.harmful_logit =
      py::cast<std::vector<std::vector<double>>>(
          heads["harmful_logit"]);
  config.risk_adjusted_utility_seconds =
      py::cast<std::vector<std::vector<double>>>(
          heads["risk_adjusted_utility_seconds"]);
  config.benefit_probability_lcb_threshold =
      py::cast<double>(thresholds["benefit_probability_lcb"]);
  config.harmful_probability_ucb_budget =
      py::cast<double>(thresholds["harmful_probability_ucb"]);
  config.utility_lcb_margin_seconds =
      py::cast<double>(thresholds["utility_lcb_margin_seconds"]);
  // Native validation is repeated inside EventDrivenJunctionRuntime so direct
  // pybind callers and the Python wrapper share one fail-closed authority.
  config.validate();
  return config;
}

czr005::ics::G4IRSF16I4DiagnosticRuleConfig
g4irsf16_i4_rule_config_from_bundle(const py::dict& bundle) {
  czr005::ics::G4IRSF16I4DiagnosticRuleConfig config;
  if (bundle.empty()) {
    return config;
  }
  validate_g4irsf16_self_sha256(bundle);
  const auto require_dict = [](const py::handle& owner,
                               const char* name) {
    const auto mapping =
        py::reinterpret_borrow<py::dict>(owner);
    if (!mapping.contains(name) ||
        !py::isinstance<py::dict>(mapping[name])) {
      throw py::value_error(
          std::string("G4IRSF16 rule section missing: ") + name);
    }
    return py::reinterpret_borrow<py::dict>(mapping[name]);
  };
  if (!bundle.contains("schema") ||
      !bundle.contains("self_sha256") ||
      !bundle.contains("i4")) {
    throw py::value_error("G4IRSF16 rule bundle identity missing");
  }
  const py::dict i4 = require_dict(bundle, "i4");
  if (!i4.contains("promotion_authorized") ||
      !PyBool_Check(i4["promotion_authorized"].ptr()) ||
      py::cast<bool>(i4["promotion_authorized"]) ||
      py::cast<std::string>(i4["selected_rule"]) != "H0") {
    throw py::value_error(
        "G4IRSF16 diagnostic canary must preserve H0/no-promotion");
  }
  const py::dict canary = require_dict(i4, "diagnostic_canary");
  const py::dict parameters = require_dict(canary, "parameters");
  config.authorized = true;
  config.schema = py::cast<std::string>(bundle["schema"]);
  config.artifact_sha256 =
      py::cast<std::string>(bundle["self_sha256"]);
  config.rule = py::cast<std::string>(canary["rule"]);
  config.authorization =
      py::cast<std::string>(canary["authorization"]);
  config.f2_model_margin_max =
      py::cast<double>(parameters["f2_model_margin_max"]);
  config.target_queue_length_min =
      py::cast<double>(parameters["target_queue_length_min"]);
  config.target_scheduled_incoming_min =
      py::cast<double>(parameters["target_scheduled_incoming_min"]);
  config.validate();
  return config;
}

czr005::ics::G4IRSF24DLPConfig
g4irsf24_dlp_config_from_artifact(const py::dict& artifact) {
  czr005::ics::G4IRSF24DLPConfig config;
  if (artifact.empty()) {
    return config;
  }
  const auto required = [&](const char* name) -> py::handle {
    if (!artifact.contains(name)) {
      throw py::value_error(
          std::string("G4IRSF24 DLP artifact missing ") + name);
    }
    return artifact[name];
  };
  if (py::cast<std::string>(required("schema")) !=
      "czr005.g4irsf24.dlp.v1") {
    throw py::value_error(
        "G4IRSF24 DLP artifact schema must be "
        "czr005.g4irsf24.dlp.v1");
  }
  config.mode = py::cast<std::string>(required("mode"));
  if (config.mode == "off") {
    return config;
  }
  if (config.mode != "ewma" && config.mode != "td") {
    throw py::value_error(
        "G4IRSF24 DLP artifact mode must be off, ewma, or td");
  }
  config.beta = py::cast<double>(required("beta"));
  config.min_support = py::cast<int>(required("min_support"));
  config.margin_seconds =
      py::cast<double>(required("margin_seconds"));
  config.detour_allowance_seconds =
      py::cast<double>(required("detour_allowance_seconds"));

  const auto edge_rows = py::reinterpret_borrow<py::sequence>(
      required("edge_residuals"));
  for (const py::handle item : edge_rows) {
    const auto row = py::cast<py::dict>(item);
    const int from = py::cast<int>(row["from"]);
    const int to = py::cast<int>(row["to"]);
    if (!config.insert_edge(
            from,
            to,
            py::cast<double>(row["residual_seconds"]),
            py::cast<int>(row["support"]))) {
      throw py::value_error(
          "G4IRSF24 DLP edge_residuals contains a duplicate from/to key");
    }
  }
  const auto value_rows = py::reinterpret_borrow<py::sequence>(
      required("value_residuals"));
  for (const py::handle item : value_rows) {
    const auto row = py::cast<py::dict>(item);
    const int node = py::cast<int>(row["node"]);
    const int goal = py::cast<int>(row["goal"]);
    if (!config.insert_value(
            node,
            goal,
            py::cast<double>(row["residual_seconds"]),
            py::cast<int>(row["support"]))) {
      throw py::value_error(
          "G4IRSF24 DLP value_residuals contains a duplicate node/goal key");
    }
  }
  return config;
}

py::dict g4irsf11_event_runtime_summary_row(
    const czr005::ics::EventRuntimeSummary& summary,
    bool include_destination_merge_grants,
    const std::string& merge_grant_rule,
    int merge_grant_max_pending_requests,
    int merge_grant_lifecycle_limit) {
  py::dict row;
  row["runtime_name"] = "event_driven_local_decision_runtime";
  row["runtime_loop_owner"] = "cpp_event_scheduler";
  row["resource_semantics_id"] = summary.resource_semantics_id;
  row["resource_semantics_echo"] =
      summary.resource_semantics_echo;
  row["pressure_mode"] = summary.pressure_mode;
  row["pressure_mode_echo"] = summary.pressure_mode_echo;
  row["admission_mode"] = summary.admission_mode;
  row["admission_mode_echo"] = summary.admission_mode_echo;
  row["framework_mode"] = summary.framework_mode;
  row["framework_mode_echo"] = summary.framework_mode_echo;
  row["pibt_mode"] = summary.pibt_mode;
  row["pibt_mode_echo"] = summary.pibt_mode_echo;
  row["priority_mode"] = summary.priority_mode;
  row["priority_mode_echo"] = summary.priority_mode_echo;
  row["pibt_preference_mode"] =
      summary.pibt_preference_mode;
  row["pibt_preference_mode_echo"] =
      summary.pibt_preference_mode_echo;
  row["credit_mode"] = summary.credit_mode;
  row["priority_claim_boundary"] =
      summary.priority_claim_boundary;
  row["framework_diagnostic_only"] =
      summary.framework_diagnostic_only;
  row["pibt_mode_diagnostic_only"] =
      summary.pibt_mode_diagnostic_only;
  row["scorer_mode"] = summary.scorer_mode;
  row["scorer_mode_echo"] = summary.scorer_mode_echo;
  row["scorer_id"] = summary.scorer_id;
  row["scorer_model_sha256"] =
      summary.scorer_model_sha256;
  row["scorer_score_direction"] =
      summary.scorer_score_direction;
  row["scorer_claim_boundary"] =
      summary.scorer_claim_boundary;
  row["scorer_out_of_distribution_diagnostic"] =
      summary.scorer_out_of_distribution_diagnostic;
  row["scorer_promotion_eligible"] =
      summary.scorer_promotion_eligible;
  row["scorer_absolute_node_ids_enabled"] =
      summary.scorer_absolute_node_ids_enabled;
  row["scorer_static_precompute_only"] =
      summary.scorer_static_precompute_only;
  row["scorer_feature_dim"] = summary.scorer_feature_dim;
  row["scorer_explicit_default_feature_count"] =
      summary.scorer_explicit_default_feature_count;
  row["scorer_decision_evaluation_count"] =
      py::int_(summary.scorer_decision_evaluation_count);
  row["scorer_candidate_evaluation_count"] =
      py::int_(summary.scorer_candidate_evaluation_count);
  row["scorer_risk_abstain_count"] =
      py::int_(summary.scorer_risk_abstain_count);
  row["scorer_teacher_input_count"] =
      summary.scorer_teacher_input_count;
  row["scorer_future_route_input_count"] =
      summary.scorer_future_route_input_count;
  row["scorer_future_schedule_input_count"] =
      summary.scorer_future_schedule_input_count;
  row["scorer_posthoc_input_count"] =
      summary.scorer_posthoc_input_count;
  row["scorer_runtime_global_scan_count"] =
      summary.scorer_runtime_global_scan_count;
  row["pibt_max_depth"] = summary.pibt_max_depth;
  row["bounded_local_pibt_claim_boundary"] =
      summary.bounded_local_pibt_claim_boundary;
  row["first_edge_credit_claim_boundary"] =
      summary.first_edge_credit_claim_boundary;
  row["entry_headway_seconds"] = summary.entry_headway_seconds;
  row["pressure_weight"] = summary.pressure_weight;
  row["pressure_age_weight"] = summary.pressure_age_weight;
  row["pressure_distance_bias"] =
      summary.pressure_distance_bias;
  row["credit_validity_seconds"] =
      summary.credit_validity_seconds;
  row["credit_snapshot_max_age_seconds"] =
      summary.credit_snapshot_max_age_seconds;
  row["credit_capacity_per_edge"] =
      summary.credit_capacity_per_edge;
  row["credit_lifecycle_limit"] =
      summary.credit_lifecycle_limit;
  row["selective_credit_contention_threshold"] =
      summary.selective_credit_contention_threshold;
  row["pibt_regret_prior_record_count"] =
      summary.pibt_regret_prior_record_count;
  row["declared_max_events"] = summary.declared_max_events;
  row["max_events"] = summary.declared_max_events;
  row["declared_max_simulation_time"] =
      summary.declared_max_simulation_time;
  row["local_queue_capacity"] = summary.local_queue_capacity;
  row["pibt_max_ready_bags"] = summary.pibt_max_ready_bags;
  row["pibt_max_local_resources"] =
      summary.pibt_max_local_resources;
  row["pibt_max_candidates_per_bag"] =
      summary.pibt_max_candidates_per_bag;
  row["requested_count"] = summary.requested_count;
  row["completed_count"] = summary.completed_count;
  row["failed_count"] = summary.failed_count;
  row["peak_active_bag_count"] = summary.peak_active_bag_count;
  row["final_active_bag_count"] = summary.final_active_bag_count;
  row["decision_count"] = summary.decision_count;
  row["event_count"] = summary.event_count;
  row["g4irsf14_i2_live_eligible_multi_request_boundary_count"] =
      py::int_(
          summary
              .g4irsf14_i2_live_eligible_multi_request_boundary_count);
  row["bag_release_event_count"] = summary.bag_release_event_count;
  row["arrive_junction_event_count"] = summary.arrive_junction_event_count;
  row["junction_service_complete_event_count"] = summary.junction_service_complete_event_count;
  row["edge_enter_event_count"] = summary.edge_enter_event_count;
  row["edge_exit_event_count"] = summary.edge_exit_event_count;
  row["fault_event_count"] = summary.fault_event_count;
  row["repair_event_count"] = summary.repair_event_count;
  row["local_queue_update_event_count"] = summary.local_queue_update_event_count;
  row["congestion_beacon_update_event_count"] = summary.congestion_beacon_update_event_count;
  if (summary.g4irsf20_event_hotpath_policy != "E0") {
    row["g4irsf20_event_hotpath_policy"] =
        summary.g4irsf20_event_hotpath_policy;
    row["g4irsf20_redundant_beacon_suppressed_count"] =
        py::int_(summary.g4irsf20_redundant_beacon_suppressed_count);
    row["g4irsf20_same_state_beacon_suppressed_count"] =
        py::int_(summary.g4irsf20_same_state_beacon_suppressed_count);
  }
  if (!summary.g4irsf24_dlp_mode.empty()) {
    row["g4irsf24_dlp_mode"] = summary.g4irsf24_dlp_mode;
    row["g4irsf24_dlp_claim_boundary"] =
        "shield_legal_nonfault_ordinary_s4_route_move_only";
    row["g4irsf24_dlp_edge_residual_count"] =
        summary.g4irsf24_dlp_edge_residual_count;
    row["g4irsf24_dlp_value_residual_count"] =
        summary.g4irsf24_dlp_value_residual_count;
    row["g4irsf24_dlp_route_evaluation_count"] =
        py::int_(summary.g4irsf24_dlp_route_evaluation_count);
    row["g4irsf24_dlp_eligible_candidate_count"] =
        py::int_(summary.g4irsf24_dlp_eligible_candidate_count);
    row["g4irsf24_dlp_supported_candidate_count"] =
        py::int_(summary.g4irsf24_dlp_supported_candidate_count);
    row["g4irsf24_dlp_proposal_count"] =
        py::int_(summary.g4irsf24_dlp_proposal_count);
    row["g4irsf24_dlp_committed_mutation_count"] =
        py::int_(summary.g4irsf24_dlp_committed_mutation_count);
    row["g4irsf24_dlp_fallback_s4_count"] =
        py::int_(summary.g4irsf24_dlp_fallback_s4_count);
    row["g4irsf24_dlp_same_action_count"] =
        py::int_(summary.g4irsf24_dlp_same_action_count);
    row["g4irsf24_dlp_unsupported_fallback_count"] =
        py::int_(summary.g4irsf24_dlp_unsupported_fallback_count);
    row["g4irsf24_dlp_low_support_fallback_count"] =
        py::int_(summary.g4irsf24_dlp_low_support_fallback_count);
    row["g4irsf24_dlp_margin_fallback_count"] =
        py::int_(summary.g4irsf24_dlp_margin_fallback_count);
    row["g4irsf24_dlp_detour_fallback_count"] =
        py::int_(summary.g4irsf24_dlp_detour_fallback_count);
    row["g4irsf24_dlp_shield_fault_fallback_count"] =
        py::int_(summary.g4irsf24_dlp_shield_fault_fallback_count);
  }
  row["source_admission_enabled"] = summary.source_admission_enabled;
  row["source_admission_attempt_count"] =
      py::int_(summary.source_admission_attempt_count);
  row["source_admission_admitted_count"] =
      py::int_(summary.source_admission_admitted_count);
  row["source_admission_local_resource_hold_count"] =
      py::int_(summary.source_admission_local_resource_hold_count);
  row["source_admission_downstream_pressure_hold_count"] =
      py::int_(summary.source_admission_downstream_pressure_hold_count);
  row["source_admission_beacon_read_count"] =
      py::int_(summary.source_admission_beacon_read_count);
  row["source_admission_max_observed_downstream_pressure"] =
      summary.source_admission_max_observed_downstream_pressure;
  row["first_edge_credit_issue_attempt_count"] =
      py::int_(summary.first_edge_credit_issue_attempt_count);
  row["first_edge_credit_issued_count"] =
      py::int_(summary.first_edge_credit_issued_count);
  row["first_edge_credit_validation_attempt_count"] =
      py::int_(summary.first_edge_credit_validation_attempt_count);
  row["first_edge_credit_validation_success_count"] =
      py::int_(summary.first_edge_credit_validation_success_count);
  row["first_edge_credit_bind_attempt_count"] =
      py::int_(summary.first_edge_credit_bind_attempt_count);
  row["first_edge_credit_bound_count"] =
      py::int_(summary.first_edge_credit_bound_count);
  row["first_edge_credit_consume_attempt_count"] =
      py::int_(summary.first_edge_credit_consume_attempt_count);
  row["first_edge_credit_consumed_count"] =
      py::int_(summary.first_edge_credit_consumed_count);
  row["first_edge_credit_expired_count"] =
      py::int_(summary.first_edge_credit_expired_count);
  row["first_edge_credit_fault_revocation_count"] =
      py::int_(summary.first_edge_credit_fault_revocation_count);
  row["first_edge_credit_generation_revocation_count"] =
      py::int_(summary.first_edge_credit_generation_revocation_count);
  row["first_edge_credit_invalid_revocation_count"] =
      py::int_(summary.first_edge_credit_invalid_revocation_count);
  row["first_edge_credit_duplicate_rejection_count"] =
      py::int_(summary.first_edge_credit_duplicate_rejection_count);
  row["first_edge_credit_capacity_rejection_count"] =
      py::int_(summary.first_edge_credit_capacity_rejection_count);
  row["first_edge_credit_stale_snapshot_rejection_count"] =
      py::int_(summary.first_edge_credit_stale_snapshot_rejection_count);
  row["first_edge_credit_physical_fault_rejection_count"] =
      py::int_(summary.first_edge_credit_physical_fault_rejection_count);
  row["first_edge_credit_too_early_rejection_count"] =
      py::int_(summary.first_edge_credit_too_early_rejection_count);
  row["first_edge_credit_unknown_rejection_count"] =
      py::int_(summary.first_edge_credit_unknown_rejection_count);
  row["first_edge_credit_invalid_request_rejection_count"] =
      py::int_(summary.first_edge_credit_invalid_request_rejection_count);
  row["first_edge_credit_lifecycle_dropped_count"] =
      py::int_(summary.first_edge_credit_lifecycle_dropped_count);
  row["first_edge_credit_local_hold_count"] =
      py::int_(summary.first_edge_credit_local_hold_count);
  row["first_edge_credit_reissue_count"] =
      py::int_(summary.first_edge_credit_reissue_count);
  row["selective_credit_trigger_count"] =
      py::int_(summary.selective_credit_trigger_count);
  row["selective_credit_low_load_bypass_count"] =
      py::int_(summary.selective_credit_low_load_bypass_count);
  row["selective_credit_merge_trigger_count"] =
      py::int_(summary.selective_credit_merge_trigger_count);
  row["selective_credit_contention_trigger_count"] =
      py::int_(summary.selective_credit_contention_trigger_count);
  row["first_edge_credit_active_count"] =
      summary.first_edge_credit_active_count;
  row["first_edge_credit_peak_active_count"] =
      summary.first_edge_credit_peak_active_count;
  row["first_edge_credit_stored_active_count"] =
      summary.first_edge_credit_stored_active_count;
  row["first_edge_credit_stored_lifecycle_count"] =
      summary.first_edge_credit_stored_lifecycle_count;
  row["first_edge_credit_lifecycle_limit"] =
      summary.first_edge_credit_lifecycle_limit;
  row["first_edge_credit_future_route_count"] =
      summary.first_edge_credit_future_route_count;
  row["first_edge_credit_global_scan_count"] =
      summary.first_edge_credit_global_scan_count;
  row["first_edge_credit_physical_interlock_bypass"] =
      summary.first_edge_credit_physical_interlock_bypass;
  row["fault_notification_drop_count"] = summary.fault_notification_drop_count;
  row["physical_fault_window_traversal_count"] =
      summary.physical_fault_window_traversal_count;
  row["physical_fault_edge_entry_violation_count"] =
      summary.physical_fault_edge_entry_violation_count;
  row["fault_policy_enabled"] = summary.fault_policy_enabled;
  row["legacy_pibt_lite_enabled"] =
      summary.legacy_pibt_lite_enabled;
  row["fault_affected_bag_count"] = summary.fault_affected_bag_count;
  row["fault_target_edge_candidate_exposure_count"] =
      summary.fault_target_edge_candidate_exposure_count;
  row["fault_target_edge_attempt_count"] = summary.fault_target_edge_attempt_count;
  // Keep physical-interlock recovery separate from advertised-fault policy
  // actions so the G4IRSF12 H ledger can audit lost notifications honestly.
  row["physical_fault_interlock_rejection_count"] =
      summary.physical_fault_interlock_rejection_count;
  row["physical_fault_interlock_hold_count"] =
      summary.physical_fault_interlock_hold_count;
  row["physical_fault_interlock_reroute_count"] =
      summary.physical_fault_interlock_reroute_count;
  row["local_fault_policy_action_count"] = summary.local_fault_policy_action_count;
  row["local_fault_policy_hold_count"] = summary.local_fault_policy_hold_count;
  row["local_fault_policy_reroute_count"] = summary.local_fault_policy_reroute_count;
  row["fault_affected_completed_count"] =
      summary.fault_affected_completed_count;
  row["fault_recovery_seconds_available"] =
      summary.fault_recovery_seconds_available;
  if (summary.fault_recovery_seconds_available) {
    row["fault_recovery_seconds"] =
        summary.fault_recovery_seconds;
  }
  row["repair_backlog_slope_available"] =
      summary.repair_backlog_slope_available;
  if (summary.repair_backlog_slope_available) {
    row["repair_backlog_slope"] = summary.repair_backlog_slope;
  }
  row["fault_recovery_metric_semantics"] =
      summary.fault_recovery_metric_semantics;
  row["repair_backlog_slope_semantics"] =
      summary.repair_backlog_slope_semantics;
  row["sensor_loss_mode_used"] = summary.sensor_loss_mode_used;
  row["sensor_loss_supported"] = true;
  row["reservation_conflicts"] = summary.reservation_conflicts;
  row["conflicts"] = summary.reservation_conflicts;
  row["shield_rejection_count"] = summary.shield_rejection_count;
  row["stale_fault_shield_rejection_count"] = summary.stale_fault_shield_rejection_count;
  row["pibt_lite_handoff_count"] = summary.pibt_lite_handoff_count;
  row["same_bag_alternative_edge_scan_handoff_count"] =
      summary.same_bag_alternative_edge_scan_handoff_count;
  row["bounded_local_pibt_activation_count"] =
      py::int_(summary.bounded_local_pibt_activation_count);
  row["g4irsf14_i5_prefilter_candidate_count"] =
      py::int_(summary.g4irsf14_i5_prefilter_candidate_count);
  row["g4irsf14_i5_applicable_ready_slice_boundary_count"] =
      py::int_(
          summary.g4irsf14_i5_applicable_ready_slice_boundary_count);
  row["bounded_local_pibt_applicability_count"] =
      py::int_(summary.bounded_local_pibt_activation_count);
  row["pibt_applicability_count"] =
      py::int_(summary.bounded_local_pibt_activation_count);
  row["bounded_local_pibt_attempt_count"] =
      py::int_(summary.bounded_local_pibt_attempt_count);
  row["pibt_attempt_count"] =
      py::int_(summary.bounded_local_pibt_attempt_count);
  row["bounded_local_pibt_prepare_count"] =
      py::int_(summary.bounded_local_pibt_prepare_count);
  row["pibt_prepare_count"] =
      py::int_(summary.bounded_local_pibt_prepare_count);
  row["bounded_local_pibt_validate_count"] =
      py::int_(summary.bounded_local_pibt_validate_count);
  row["pibt_validate_count"] =
      py::int_(summary.bounded_local_pibt_validate_count);
  row["bounded_local_pibt_commit_count"] =
      py::int_(summary.bounded_local_pibt_commit_count);
  row["pibt_commit_count"] =
      py::int_(summary.bounded_local_pibt_commit_count);
  row["bounded_local_pibt_wait_for_cycle_count"] =
      py::int_(summary.bounded_local_pibt_wait_for_cycle_count);
  row["pibt_wait_for_cycle_count"] =
      py::int_(summary.bounded_local_pibt_wait_for_cycle_count);
  row["bounded_local_pibt_handoff_count"] =
      py::int_(summary.bounded_local_pibt_handoff_count);
  row["pibt_handoff_count"] =
      py::int_(summary.bounded_local_pibt_handoff_count);
  row["bounded_local_pibt_candidate_bound_rejection_count"] =
      py::int_(
          summary
              .bounded_local_pibt_candidate_bound_rejection_count);
  row["bounded_local_pibt_candidate_materialization_count"] =
      py::int_(
          summary
              .bounded_local_pibt_candidate_materialization_count);
  row["bounded_local_pibt_not_applicable_count"] =
      py::int_(summary.bounded_local_pibt_not_applicable_count);
  row["bounded_local_pibt_same_bag_fallback_count"] =
      py::int_(summary.bounded_local_pibt_same_bag_fallback_count);
  row["bounded_local_pibt_proposal_batch_count"] =
      py::int_(summary.bounded_local_pibt_proposal_batch_count);
  row["bounded_local_pibt_proposed_action_count"] =
      py::int_(summary.bounded_local_pibt_proposed_action_count);
  row["bounded_local_pibt_committed_batch_count"] =
      py::int_(summary.bounded_local_pibt_committed_batch_count);
  row["bounded_local_pibt_committed_action_count"] =
      py::int_(summary.bounded_local_pibt_committed_action_count);
  row["bounded_local_pibt_inherited_action_count"] =
      py::int_(summary.bounded_local_pibt_inherited_action_count);
  row["bounded_local_pibt_blocker_move_attempt_count"] =
      py::int_(summary.bounded_local_pibt_blocker_move_attempt_count);
  row["bounded_local_pibt_backtrack_count"] =
      py::int_(summary.bounded_local_pibt_backtrack_count);
  row["bounded_local_pibt_cycle_guard_count"] =
      py::int_(summary.bounded_local_pibt_cycle_guard_count);
  row["bounded_local_pibt_rollback_count"] =
      py::int_(summary.bounded_local_pibt_rollback_count);
  row["bounded_local_pibt_fault_rejection_count"] =
      py::int_(summary.bounded_local_pibt_fault_rejection_count);
  row["bounded_local_pibt_prepare_rejection_count"] =
      py::int_(summary.bounded_local_pibt_prepare_rejection_count);
  row["bounded_local_pibt_commit_rejection_count"] =
      py::int_(summary.bounded_local_pibt_commit_rejection_count);
  row["bounded_local_pibt_max_inheritance_depth"] =
      summary.bounded_local_pibt_max_inheritance_depth;
  row["bounded_local_pibt_max_slice_bags"] =
      summary.bounded_local_pibt_max_slice_bags;
  row["bounded_local_pibt_max_slice_resources"] =
      summary.bounded_local_pibt_max_slice_resources;
  row["bounded_local_pibt_max_candidates_per_bag"] =
      summary.bounded_local_pibt_max_candidates_per_bag;
  row["bounded_local_pibt_max_transaction_credit_entries"] =
      summary.bounded_local_pibt_max_transaction_credit_entries;
  row["bounded_local_pibt_max_transaction_bag_entries"] =
      summary.bounded_local_pibt_max_transaction_bag_entries;
  row["bounded_local_pibt_max_transaction_junction_scalar_entries"] =
      summary
          .bounded_local_pibt_max_transaction_junction_scalar_entries;
  row["bounded_local_pibt_max_transaction_action_deltas"] =
      summary.bounded_local_pibt_max_transaction_action_deltas;
  row["bounded_local_pibt_classical_completeness_claimed"] =
      summary.bounded_local_pibt_classical_completeness_claimed;
  row["pibt_preference_candidate_count"] =
      py::int_(summary.pibt_preference_candidate_count);
  row["pibt_preference_unique_exit_penalty_count"] =
      py::int_(
          summary.pibt_preference_unique_exit_penalty_count);
  row["pibt_preference_wait_cycle_penalty_count"] =
      py::int_(summary.pibt_preference_wait_cycle_penalty_count);
  row["pibt_preference_backtrack_penalty_count"] =
      py::int_(summary.pibt_preference_backtrack_penalty_count);
  row["pibt_preference_regret_prior_hit_count"] =
      py::int_(summary.pibt_preference_regret_prior_hit_count);
  row["repaired_task_reentry_count"] =
      py::int_(summary.repaired_task_reentry_count);
  row["repaired_task_reentry_boost_cleared_count"] =
      py::int_(
          summary.repaired_task_reentry_boost_cleared_count);
  row["priority_teacher_input_count"] =
      summary.priority_teacher_input_count;
  row["priority_future_route_input_count"] =
      summary.priority_future_route_input_count;
  row["priority_global_scan_count"] =
      summary.priority_global_scan_count;
  row["deadlock_count"] = summary.deadlock_count;
  row["resolved_deadlock_count"] = summary.resolved_deadlock_count;
  row["unresolved_deadlock_count"] = summary.unresolved_deadlock_count;
  row["deadlock_escape_activation_count"] = summary.deadlock_escape_activation_count;
  row["starvation_count"] = summary.starvation_count;
  row["loop_count"] = summary.loop_count;
  row["runtime_full_astar_calls"] = summary.runtime_full_astar_calls;
  row["runtime_full_cie_astar_calls"] = 0;
  row["full_cie_astar_runtime_fallback"] = false;
  row["global_reservation_scan_count"] = summary.global_reservation_scan_count;
  row["max_edges_selected_per_arrive"] = summary.max_edges_selected_per_arrive;
  row["max_edges_selected_per_bag_per_decision"] =
      summary.max_edges_selected_per_bag_per_decision;
  row["max_actions_committed_per_pibt_batch"] =
      summary.max_actions_committed_per_pibt_batch;
  row["release_selected_edge_count"] = summary.release_selected_edge_count;
  row["reservation_depth"] = 1;
  row["diagnostic_hops"] = summary.diagnostic_hops;
  row["decision_trace_seen_count"] = summary.decision_trace_seen_count;
  row["decision_trace_shard_seen_count"] = summary.decision_trace_shard_seen_count;
  row["decision_trace_stored_count"] = summary.decision_trace_stored_count;
  row["hold_trace_stored_count"] = summary.hold_trace_stored_count;
  row["trace_limit"] = summary.trace_limit;
  row["event_trace_limit"] = summary.event_trace_limit;
  row["event_trace_limit_inherited"] =
      summary.event_trace_limit_inherited;
  row["trace_shard_count"] = summary.trace_shard_count;
  row["trace_shard_index"] = summary.trace_shard_index;
  row["decision_trace_truncated"] = summary.decision_trace_truncated;
  row["event_trace_truncated"] = summary.event_trace_truncated;
  row["two_step_reservation_count"] = summary.two_step_reservation_count;
  row["bag_future_path_field_present"] = false;
  row["full_future_routes_stored"] = 0;
  row["max_history_observed"] = summary.max_history_observed;
  row["max_junction_queue_length"] = summary.max_junction_queue_length;
  row["max_source_queue_length"] = summary.max_source_queue_length;
  row["max_local_calendar_intervals"] = summary.max_local_calendar_intervals;
  row["max_corridor_calendar_intervals"] = summary.max_corridor_calendar_intervals;
  row["max_same_directed_edge_inflight"] =
      summary.max_same_directed_edge_inflight;
  row["max_candidate_count"] = summary.max_candidate_count;
  row["max_individual_wait"] = summary.max_individual_wait;
  row["max_source_queue_delay"] = summary.max_source_queue_delay;
  row["fairness_jain"] = summary.fairness_jain;
  row["max_deadlock_duration"] = summary.max_deadlock_duration;
  row["end_time"] = summary.end_time;
  row["runtime_seconds"] = summary.runtime_seconds;
  row["decision_latency_us_p50"] = summary.decision_latency_us_p50;
  row["decision_latency_us_p95"] = summary.decision_latency_us_p95;
  row["decision_latency_us_p99"] = summary.decision_latency_us_p99;
  row["event_throughput_per_second"] = summary.event_throughput_per_second;
  row["cpp_internal_accounted_bytes"] = py::int_(summary.cpp_internal_accounted_bytes);
  row["internal_state_bytes"] = py::int_(summary.cpp_internal_accounted_bytes);
  row["internal_state_bytes_semantics"] = "accounted_cpp_lower_bound_not_process_rss";
  row["event_limit_reached"] = summary.event_limit_reached;
  row["time_limit_reached"] = summary.time_limit_reached;
  const bool g4irsf14_extensions_enabled =
      summary.event_semantics != "E0_immediate_dispatch_f2" ||
      summary.opportunity_telemetry_enabled;
  if (g4irsf14_extensions_enabled) {
    row["event_semantics"] = summary.event_semantics;
    row["event_semantics_echo"] =
        summary.event_semantics_echo;
    row["opportunity_telemetry_enabled"] =
        summary.opportunity_telemetry_enabled;
    row["source_arbitration_event_count"] =
        py::int_(summary.source_arbitration_event_count);
    row["junction_arbitration_event_count"] =
        py::int_(summary.junction_arbitration_event_count);
    row["stale_arbitration_event_count"] =
        py::int_(summary.stale_arbitration_event_count);
    row["superseded_arbitration_event_rejected_count"] =
        py::int_(
            summary
                .superseded_arbitration_event_rejected_count);
    row["duplicate_same_time_arbitration_prevented_count"] =
        py::int_(
            summary
                .duplicate_same_time_arbitration_prevented_count);
    row["source_same_timestamp_batch_count"] =
        py::int_(summary.source_same_timestamp_batch_count);
    row["junction_same_timestamp_batch_count"] =
        py::int_(summary.junction_same_timestamp_batch_count);
    row["max_source_arbitration_batch_size"] =
        summary.max_source_arbitration_batch_size;
    row["max_junction_arbitration_batch_size"] =
        summary.max_junction_arbitration_batch_size;
    row["opportunity_event_queue_inspection_count"] =
        py::int_(
            summary.opportunity_event_queue_inspection_count);
    row["source_opportunity_total_count"] =
        py::int_(summary.source_opportunity_total_count);
    row["source_opportunity_stored_count"] =
        py::int_(summary.source_opportunity_stored_count);
    row["source_opportunity_dropped_count"] =
        py::int_(summary.source_opportunity_dropped_count);
    row["junction_opportunity_total_count"] =
        py::int_(summary.junction_opportunity_total_count);
    row["junction_opportunity_stored_count"] =
        py::int_(summary.junction_opportunity_stored_count);
    row["junction_opportunity_dropped_count"] =
        py::int_(summary.junction_opportunity_dropped_count);
    row["merge_visibility_total_count"] =
        py::int_(summary.merge_visibility_total_count);
    row["merge_visibility_stored_count"] =
        py::int_(summary.merge_visibility_stored_count);
    row["merge_visibility_dropped_count"] =
        py::int_(summary.merge_visibility_dropped_count);
    row["event_seq_audit_total_count"] =
        py::int_(summary.event_seq_audit_total_count);
    row["event_seq_audit_stored_count"] =
        py::int_(summary.event_seq_audit_stored_count);
    row["event_seq_audit_dropped_count"] =
        py::int_(summary.event_seq_audit_dropped_count);
    row["arbitration_batch_total_count"] =
        py::int_(summary.arbitration_batch_total_count);
    row["arbitration_batch_stored_count"] =
        py::int_(summary.arbitration_batch_stored_count);
    row["arbitration_batch_dropped_count"] =
        py::int_(summary.arbitration_batch_dropped_count);
    row["fault_generation_commit_recheck_count"] =
        py::int_(summary.fault_generation_commit_recheck_count);
    row["microphase_runtime_global_scan_count"] =
        summary.microphase_runtime_global_scan_count;
    row["artificial_batch_delay_seconds"] =
        summary.artificial_batch_delay_seconds;
    if (include_destination_merge_grants) {
      row["merge_grant_rule"] =
          canonical_merge_grant_rule_for_binding(merge_grant_rule);
      row["merge_grant_rule_echo"] = merge_grant_rule;
      row["merge_grant_max_pending_requests"] =
          merge_grant_max_pending_requests;
      row["merge_grant_lifecycle_limit"] =
          merge_grant_lifecycle_limit;
      row["destination_merge_arbitration_event_count"] =
          py::int_(
              summary.destination_merge_arbitration_event_count);
      row["merge_grant_request_count"] =
          py::int_(summary.merge_grant_request_count);
      row["merge_grant_issued_count"] =
          py::int_(summary.merge_grant_issued_count);
      row["merge_grant_issued_transition_count"] =
          py::int_(
              summary.merge_grant_issued_transition_count);
      row["merge_grant_prepared_count"] =
          py::int_(summary.merge_grant_prepared_count);
      row["merge_grant_prepared_transition_count"] =
          py::int_(
              summary.merge_grant_prepared_transition_count);
      row["merge_grant_committed_count"] =
          py::int_(summary.merge_grant_committed_count);
      row["merge_grant_committed_transition_count"] =
          py::int_(
              summary.merge_grant_committed_transition_count);
      row["merge_grant_consumed_count"] =
          py::int_(summary.merge_grant_consumed_count);
      row["merge_grant_inflight_fault_generation_recovery_count"] =
          py::int_(
              summary
                  .merge_grant_inflight_fault_generation_recovery_count);
      row["merge_grant_expired_count"] =
          py::int_(summary.merge_grant_expired_count);
      row["merge_grant_request_expired_count"] =
          py::int_(summary.merge_grant_request_expired_count);
      row["merge_grant_grant_expired_count"] =
          py::int_(summary.merge_grant_grant_expired_count);
      row["merge_grant_revoked_count"] =
          py::int_(summary.merge_grant_revoked_count);
      row["merge_grant_post_commit_revoked_count"] =
          py::int_(
              summary.merge_grant_post_commit_revoked_count);
      row["merge_grant_post_commit_expired_count"] =
          py::int_(
              summary.merge_grant_post_commit_expired_count);
      row["merge_grant_post_commit_rollback_count"] =
          py::int_(
              summary.merge_grant_post_commit_rollback_count);
      row["merge_grant_revoked_fault_count"] =
          py::int_(summary.merge_grant_revoked_fault_count);
      row["merge_grant_revoked_stale_state_count"] =
          py::int_(
              summary.merge_grant_revoked_stale_state_count);
      row["merge_grant_revoked_replan_current_edge_count"] =
          py::int_(
              summary
                  .merge_grant_revoked_replan_current_edge_count);
      row["merge_grant_rolled_back_count"] =
          py::int_(summary.merge_grant_rolled_back_count);
      row["merge_grant_exact_slot_busy_count"] =
          py::int_(summary.merge_grant_exact_slot_busy_count);
      row["merge_grant_active_grant_rejection_count"] =
          py::int_(
              summary.merge_grant_active_grant_rejection_count);
      row["merge_grant_queue_capacity_block_count"] =
          py::int_(
              summary.merge_grant_queue_capacity_block_count);
      row["merge_grant_contended_loser_retry_count"] =
          py::int_(
              summary.merge_grant_contended_loser_retry_count);
      row["merge_grant_lifecycle_transition_count"] =
          py::int_(
              summary.merge_grant_lifecycle_transition_count);
      row["merge_grant_lifecycle_stored_count"] =
          py::int_(
              summary.merge_grant_lifecycle_stored_count);
      row["merge_grant_lifecycle_dropped_count"] =
          py::int_(
              summary.merge_grant_lifecycle_dropped_count);
      row["merge_grant_terminal_request_count"] =
          py::int_(
              summary.merge_grant_terminal_request_count);
      row["merge_grant_outstanding_request_count"] =
          py::int_(
              summary.merge_grant_outstanding_request_count);
      row["merge_grant_goal_exempt_bypass_count"] =
          py::int_(
              summary.merge_grant_goal_exempt_bypass_count);
      row["merge_grant_stale_arbitration_count"] =
          py::int_(
              summary.merge_grant_stale_arbitration_count);
      row["merge_grant_duplicate_wakeup_prevented_count"] =
          py::int_(
              summary
                  .merge_grant_duplicate_wakeup_prevented_count);
      row["merge_grant_timing_mode"] =
          summary.merge_grant_timing_mode;
      row["merge_grant_service_opportunity_count"] =
          py::int_(summary.merge_grant_service_opportunity_count);
      row["merge_grant_multi_candidate_opportunity_count"] =
          py::int_(
              summary.merge_grant_multi_candidate_opportunity_count);
      row["merge_grant_true_competition_count"] =
          py::int_(summary.merge_grant_true_competition_count);
      row["merge_grant_order_mutation_count"] =
          py::int_(summary.merge_grant_order_mutation_count);
      row["merge_grant_candidate_total_count"] =
          py::int_(summary.merge_grant_candidate_total_count);
      row["merge_grant_wakeup_scheduled_count"] =
          py::int_(summary.merge_grant_wakeup_scheduled_count);
      row["merge_grant_wakeup_coalesced_count"] =
          py::int_(summary.merge_grant_wakeup_coalesced_count);
      row["merge_grant_stale_wakeup_count"] =
          py::int_(summary.merge_grant_stale_wakeup_count);
      row["merge_grant_opportunity_trace_total_count"] =
          py::int_(
              summary.merge_grant_opportunity_trace_total_count);
      row["merge_grant_opportunity_trace_stored_count"] =
          py::int_(
              summary.merge_grant_opportunity_trace_stored_count);
      row["merge_grant_opportunity_trace_dropped_count"] =
          py::int_(
              summary.merge_grant_opportunity_trace_dropped_count);
      row["merge_grant_peak_pending_requests"] =
          summary.merge_grant_peak_pending_requests;
      row["merge_grant_peak_active_unconsumed"] =
          summary.merge_grant_peak_active_unconsumed;
      row["merge_grant_final_active_unconsumed"] =
          summary.merge_grant_final_active_unconsumed;
      row["merge_grant_conservation_holds"] =
          summary.merge_grant_conservation_holds;
      row["merge_grant_active_bijection_holds"] =
          summary.merge_grant_active_bijection_holds;
      row["merge_grant_runtime_owned_capability"] =
          summary.merge_grant_runtime_owned_capability;
      row["merge_grant_exact_slot_no_future_shift"] =
          summary.merge_grant_exact_slot_no_future_shift;
      row["merge_grant_lifecycle_complete"] =
          summary.merge_grant_lifecycle_dropped_count == 0;
      row["merge_grant_lifecycle_telemetry_truncated"] =
          summary.merge_grant_lifecycle_dropped_count > 0;
      row["merge_grant_active_state_integrity_pass"] =
          summary.merge_grant_conservation_holds &&
          summary.merge_grant_active_bijection_holds &&
          summary.merge_grant_runtime_owned_capability &&
          summary.merge_grant_exact_slot_no_future_shift &&
          summary.merge_grant_final_active_unconsumed == 0 &&
          summary.merge_grant_outstanding_request_count == 0;
      row["merge_grant_post_commit_capacity_compensation_pass"] =
          summary.merge_grant_post_commit_rollback_count ==
          summary.merge_grant_queue_capacity_block_count;
      row["merge_grant_protocol_integrity_pass"] =
          summary.merge_grant_conservation_holds &&
          summary.merge_grant_active_bijection_holds &&
          summary.merge_grant_runtime_owned_capability &&
          summary.merge_grant_exact_slot_no_future_shift &&
          summary.merge_grant_lifecycle_dropped_count == 0 &&
          summary.merge_grant_final_active_unconsumed == 0 &&
          summary.merge_grant_outstanding_request_count == 0;
    }
  }
  row["safe_execution_pass"] = summary.reservation_conflicts == 0 &&
                                 summary.runtime_full_astar_calls == 0 &&
                                 summary.physical_fault_edge_entry_violation_count == 0;
  if (!summary.g4irsf16_supervisor_mode.empty()) {
    row["g4irsf16_supervisor_mode"] =
        summary.g4irsf16_supervisor_mode;
    row["g4irsf16_policy_kind"] = summary.g4irsf16_policy_kind;
    row["g4irsf16_i3_model_sha256"] =
        summary.g4irsf16_i3_model_sha256;
    row["g4irsf16_i4_model_sha256"] =
        summary.g4irsf16_i4_model_sha256;
    row["g4irsf16_i4_policy_id"] =
        summary.g4irsf16_i4_policy_id;
    row["g4irsf16_i4_policy_authorization"] =
        summary.g4irsf16_i4_policy_authorization;
    row["g4irsf16_diagnostic_only"] =
        summary.g4irsf16_diagnostic_only;
    row["g4irsf16_promotion_authorized"] =
        summary.g4irsf16_promotion_authorized;
    row["g4irsf16_supervisor_evaluation_count"] = py::int_(
        summary.g4irsf16_supervisor_evaluation_count);
    row["g4irsf16_i3_candidate_evaluation_count"] = py::int_(
        summary.g4irsf16_i3_candidate_evaluation_count);
    row["g4irsf16_i4_evaluation_count"] = py::int_(
        summary.g4irsf16_i4_evaluation_count);
    row["g4irsf16_i3_activation_count"] = py::int_(
        summary.g4irsf16_i3_activation_count);
    row["g4irsf16_i4_activation_count"] = py::int_(
        summary.g4irsf16_i4_activation_count);
    row["g4irsf16_i3_applied_count"] = py::int_(
        summary.g4irsf16_i3_applied_count);
    row["g4irsf16_i4_applied_count"] = py::int_(
        summary.g4irsf16_i4_applied_count);
    row["g4irsf16_shadow_proposal_count"] = py::int_(
        summary.g4irsf16_shadow_proposal_count);
    row["g4irsf16_action_change_count"] = py::int_(
        summary.g4irsf16_action_change_count);
    row["g4irsf16_safe_hold_count"] = py::int_(
        summary.g4irsf16_safe_hold_count);
    row["g4irsf16_fault_recovery_count"] = py::int_(
        summary.g4irsf16_fault_recovery_count);
    row["g4irsf16_runtime_global_scan_count"] =
        summary.g4irsf16_runtime_global_scan_count;
    row["g4irsf16_future_route_input_count"] =
        summary.g4irsf16_future_route_input_count;
    row["g4irsf16_future_schedule_input_count"] =
        summary.g4irsf16_future_schedule_input_count;
    row["g4irsf16_posthoc_input_count"] =
        summary.g4irsf16_posthoc_input_count;
    row["g4irsf16_full_astar_call_count"] =
        summary.g4irsf16_full_astar_call_count;
    row["g4irsf16_local_feature_scope"] =
        "current_node_one_hop_candidates_bounded_history_static_potential";
  }
  if (summary.g4irsf17_source_wait_telemetry_enabled) {
    row["g4irsf17_source_wait_telemetry_enabled"] = true;
    row["g4irsf17_source_wait_interval_total_count"] = py::int_(
        summary.g4irsf17_source_wait_interval_total_count);
    row["g4irsf17_source_wait_interval_stored_count"] = py::int_(
        summary.g4irsf17_source_wait_interval_stored_count);
    row["g4irsf17_source_wait_interval_dropped_count"] = py::int_(
        summary.g4irsf17_source_wait_interval_dropped_count);
    row["g4irsf17_source_wait_seconds"] =
        summary.g4irsf17_source_wait_seconds;
    row["g4irsf17_source_wait_bag_seconds"] =
        summary.g4irsf17_source_wait_bag_seconds;
    py::dict reason_interval_counts;
    py::dict reason_seconds;
    py::dict reason_bag_seconds;
    for (std::size_t index = 0;
         index < czr005::ics::kG4IRSF17SourceWaitReasonCount;
         ++index) {
      const auto reason = static_cast<
          czr005::ics::G4IRSF17SourceWaitReason>(index);
      const char* name =
          czr005::ics::g4irsf17_source_wait_reason_name(reason);
      reason_interval_counts[name] = py::int_(
          summary.g4irsf17_source_wait_reason_interval_counts[index]);
      reason_seconds[name] =
          summary.g4irsf17_source_wait_reason_seconds[index];
      reason_bag_seconds[name] =
          summary.g4irsf17_source_wait_reason_bag_seconds[index];
    }
    row["g4irsf17_source_wait_reason_interval_counts"] =
        std::move(reason_interval_counts);
    row["g4irsf17_source_wait_reason_seconds"] =
        std::move(reason_seconds);
    row["g4irsf17_source_wait_reason_bag_seconds"] =
        std::move(reason_bag_seconds);
    row["g4irsf17_source_wait_runtime_global_scan_count"] =
        summary.g4irsf17_source_wait_runtime_global_scan_count;
  }
  if (!summary.g4irsf17_source_policy_mode.empty()) {
    row["g4irsf17_source_policy_mode"] =
        summary.g4irsf17_source_policy_mode;
    row["g4irsf17_source_policy_kind"] =
        summary.g4irsf17_source_policy_kind;
    row["g4irsf17_source_policy_artifact_set_id"] =
        summary.g4irsf17_source_policy_artifact_set_id;
    row["g4irsf17_source_policy_authorized"] =
        summary.g4irsf17_source_policy_authorized;
    row["g4irsf17_source_policy_runtime_closed_loop_authorized"] =
        summary
            .g4irsf17_source_policy_runtime_closed_loop_authorized;
    row["g4irsf17_source_policy_top_k"] =
        summary.g4irsf17_source_policy_top_k;
    row["g4irsf17_source_policy_evaluation_count"] = py::int_(
        summary.g4irsf17_source_policy_evaluation_count);
    row["g4irsf17_source_policy_change_proposal_count"] = py::int_(
        summary.g4irsf17_source_policy_change_proposal_count);
    row["g4irsf17_source_policy_activation_count"] = py::int_(
        summary.g4irsf17_source_policy_activation_count);
    row["g4irsf17_source_policy_abstention_count"] = py::int_(
        summary.g4irsf17_source_policy_abstention_count);
    row["g4irsf17_source_policy_ood_abstention_count"] = py::int_(
        summary.g4irsf17_source_policy_ood_abstention_count);
    row["g4irsf17_source_policy_supervisor_abstention_count"] = py::int_(
        summary.g4irsf17_source_policy_supervisor_abstention_count);
    row["g4irsf17_source_policy_trace_total_count"] = py::int_(
        summary.g4irsf17_source_policy_trace_total_count);
    row["g4irsf17_source_policy_trace_stored_count"] = py::int_(
        summary.g4irsf17_source_policy_trace_stored_count);
    row["g4irsf17_source_policy_trace_dropped_count"] = py::int_(
        summary.g4irsf17_source_policy_trace_dropped_count);
    row["g4irsf17_source_policy_runtime_global_scan_count"] =
        summary.g4irsf17_source_policy_runtime_global_scan_count;
    row["g4irsf17_source_policy_future_route_input_count"] =
        summary.g4irsf17_source_policy_future_route_input_count;
    row["g4irsf17_source_policy_future_schedule_input_count"] =
        summary.g4irsf17_source_policy_future_schedule_input_count;
    row["g4irsf17_source_policy_full_astar_call_count"] =
        summary.g4irsf17_source_policy_full_astar_call_count;
  }
  if (!summary.g4irsf18_merge_policy_mode.empty()) {
    row["g4irsf18_merge_policy_mode"] =
        summary.g4irsf18_merge_policy_mode;
    row["g4irsf18_merge_policy_schema"] =
        summary.g4irsf18_merge_policy_schema;
    row["g4irsf18_merge_policy_family"] =
        summary.g4irsf18_merge_policy_family;
    row["g4irsf18_merge_feature_contract"] =
        summary.g4irsf18_merge_feature_contract;
    row["g4irsf18_merge_artifact_valid"] =
        summary.g4irsf18_merge_artifact_valid;
    row["g4irsf18_merge_artifact_production_closed_loop_authorized"] =
        summary
            .g4irsf18_merge_artifact_production_closed_loop_authorized;
    row["g4irsf18_merge_research_closed_loop_authorized"] =
        summary.g4irsf18_merge_research_closed_loop_authorized;
    row["g4irsf18_merge_fixed_research_workload"] =
        summary.g4irsf18_merge_fixed_research_workload;
    row["g4irsf18_merge_production_closed_loop_authorized"] =
        summary.g4irsf18_merge_production_closed_loop_authorized;
    row["g4irsf18_merge_offline_gate_passed"] =
        summary.g4irsf18_merge_offline_gate_passed;
    row["g4irsf18_merge_coverage_cap"] =
        summary.g4irsf18_merge_coverage_cap;
    row["g4irsf18_merge_max_overrides_per_segment"] =
        summary.g4irsf18_merge_max_overrides_per_segment;
    row["g4irsf18_merge_kill_switch_configured"] =
        summary.g4irsf18_merge_kill_switch_configured;
    row["g4irsf18_merge_kill_switch_tripped"] =
        summary.g4irsf18_merge_kill_switch_tripped;
    row["g4irsf18_merge_kill_switch_reason"] =
        summary.g4irsf18_merge_kill_switch_reason;
    row["g4irsf18_merge_model_opportunity_count"] = py::int_(
        summary.g4irsf18_merge_model_opportunity_count);
    row["g4irsf18_merge_model_eligible_count"] = py::int_(
        summary.g4irsf18_merge_model_eligible_count);
    row["g4irsf18_merge_model_proposal_count"] = py::int_(
        summary.g4irsf18_merge_model_proposal_count);
    row["g4irsf18_merge_model_applied_count"] = py::int_(
        summary.g4irsf18_merge_model_applied_count);
    row["g4irsf18_merge_distinct_action_mutation_count"] = py::int_(
        summary.g4irsf18_merge_distinct_action_mutation_count);
    row["g4irsf18_merge_model_ood_count"] = py::int_(
        summary.g4irsf18_merge_model_ood_count);
    row["g4irsf18_merge_model_invalid_count"] = py::int_(
        summary.g4irsf18_merge_model_invalid_count);
    row["g4irsf18_merge_model_fallback_count"] = py::int_(
        summary.g4irsf18_merge_model_fallback_count);
    row["g4irsf18_merge_j2_fallback_count"] = py::int_(
        summary.g4irsf18_merge_j2_fallback_count);
    row["g4irsf18_merge_tie_fifo_fallback_count"] = py::int_(
        summary.g4irsf18_merge_tie_fifo_fallback_count);
    row["g4irsf18_merge_shadow_fallback_count"] = py::int_(
        summary.g4irsf18_merge_shadow_fallback_count);
    row["g4irsf18_merge_authorization_fallback_count"] = py::int_(
        summary.g4irsf18_merge_authorization_fallback_count);
    row["g4irsf18_merge_coverage_cap_fallback_count"] = py::int_(
        summary.g4irsf18_merge_coverage_cap_fallback_count);
    row["g4irsf18_merge_override_cap_fallback_count"] = py::int_(
        summary.g4irsf18_merge_override_cap_fallback_count);
    row["g4irsf18_merge_starvation_guard_fallback_count"] = py::int_(
        summary.g4irsf18_merge_starvation_guard_fallback_count);
    row["g4irsf18_merge_kill_switch_trip_count"] = py::int_(
        summary.g4irsf18_merge_kill_switch_trip_count);
    row["g4irsf18_merge_kill_switch_fallback_count"] = py::int_(
        summary.g4irsf18_merge_kill_switch_fallback_count);
    row["g4irsf18_merge_model_ownership_count"] = py::int_(
        summary.g4irsf18_merge_model_ownership_count);
    row["g4irsf18_merge_coverage_eligible_seen_count"] = py::int_(
        summary.g4irsf18_merge_coverage_eligible_seen_count);
    row["g4irsf18_merge_model_ownership_rate"] =
        summary.g4irsf18_merge_model_eligible_count == 0
            ? 0.0
            : static_cast<double>(
                  summary.g4irsf18_merge_model_ownership_count) /
                  static_cast<double>(
                      summary.g4irsf18_merge_model_eligible_count);
    row["g4irsf18_merge_runtime_global_scan_count"] =
        summary.g4irsf18_merge_runtime_global_scan_count;
    row["g4irsf18_merge_future_route_input_count"] =
        summary.g4irsf18_merge_future_route_input_count;
    row["g4irsf18_merge_future_schedule_input_count"] =
        summary.g4irsf18_merge_future_schedule_input_count;
    row["g4irsf18_merge_full_astar_call_count"] =
        summary.g4irsf18_merge_full_astar_call_count;
    row["g4irsf18_merge_production_promotion_authorized"] =
        summary
            .g4irsf18_merge_artifact_production_closed_loop_authorized &&
        summary.g4irsf18_merge_production_closed_loop_authorized &&
        summary.g4irsf18_merge_offline_gate_passed;
    row["g4irsf18_merge_deployment_status"] =
        summary
                .g4irsf18_merge_artifact_production_closed_loop_authorized
            ? "runtime_gated_not_self_authorized"
            : "research_fixed_workload_only_not_promoted";
  }
  return row;
}

czr005::ics::G4IRSF17SourcePolicyConfig
g4irsf17_source_policy_config_from_artifact(
    const std::string& mode, const py::dict& artifact) {
  czr005::ics::G4IRSF17SourcePolicyConfig config;
  config.mode = mode;
  if (artifact.empty()) {
    config.validate();
    return config;
  }
  const auto required = [&](const py::dict& owner,
                            const char* name) -> py::handle {
    if (!owner.contains(name)) {
      throw py::value_error(
          std::string("G4IRSF17 source policy field missing: ") + name);
    }
    return owner[name];
  };
  const auto required_string = [&](const py::dict& owner,
                                   const char* name) {
    const auto value = required(owner, name);
    if (!py::isinstance<py::str>(value)) {
      throw py::type_error(
          std::string("G4IRSF17 source policy field must be string: ") +
          name);
    }
    return py::cast<std::string>(value);
  };
  const auto required_bool = [&](const py::dict& owner,
                                 const char* name) {
    const auto value = required(owner, name);
    if (!py::isinstance<py::bool_>(value)) {
      throw py::type_error(
          std::string("G4IRSF17 source policy field must be bool: ") +
          name);
    }
    return py::cast<bool>(value);
  };
  const auto required_dict = [&](const py::dict& owner,
                                 const char* name) {
    const auto value = required(owner, name);
    if (!py::isinstance<py::dict>(value)) {
      throw py::type_error(
          std::string("G4IRSF17 source policy field must be object: ") +
          name);
    }
    return py::reinterpret_borrow<py::dict>(value);
  };

  // Unlike the frozen G16 artifact loader, this lightweight schema does not
  // require a self-hash.  Authorization is an explicit scientific decision,
  // and native validation is about feature order and fail-closed gates.
  config.schema = required_string(artifact, "schema");
  config.kind = required_string(artifact, "kind");
  config.authorized = required_bool(artifact, "authorized");
  if (artifact.contains("runtime_closed_loop_authorized")) {
    config.runtime_closed_loop_authorized =
        required_bool(artifact, "runtime_closed_loop_authorized");
  }
  config.supervisor_authorized =
      required_bool(artifact, "supervisor_authorized");
  config.top_k = strict_python_integer_argument(
      required(artifact, "top_k"), "g4irsf17 source policy top_k");
  if (artifact.contains("starvation_age_seconds")) {
    config.starvation_age_seconds =
        py::cast<double>(artifact["starvation_age_seconds"]);
  }
  if (artifact.contains("aging_cap_seconds")) {
    config.aging_cap_seconds =
        py::cast<double>(artifact["aging_cap_seconds"]);
  }
  if (config.kind == "pairwise_linear_selective") {
    config.feature_names = py::cast<std::vector<std::string>>(
        required(artifact, "feature_names"));
    config.weights = py::cast<std::vector<double>>(
        required(artifact, "weights"));
    config.bias = py::cast<double>(required(artifact, "bias"));
    config.feature_lower = py::cast<std::vector<double>>(
        required(artifact, "feature_lower"));
    config.feature_upper = py::cast<std::vector<double>>(
        required(artifact, "feature_upper"));
    const py::dict evidence = required_dict(artifact, "evidence");
    const py::dict thresholds = required_dict(artifact, "thresholds");
    config.benefit_probability_lcb = py::cast<double>(
        required(evidence, "benefit_probability_lcb"));
    config.harmful_probability_ucb = py::cast<double>(
        required(evidence, "harmful_probability_ucb"));
    config.utility_lcb_seconds = py::cast<double>(
        required(evidence, "utility_lcb_seconds"));
    config.calibration_ece =
        py::cast<double>(required(evidence, "calibration_ece"));
    config.benefit_probability_lcb_min = py::cast<double>(
        required(thresholds, "benefit_probability_lcb_min"));
    config.harmful_probability_ucb_max = py::cast<double>(
        required(thresholds, "harmful_probability_ucb_max"));
    config.utility_lcb_min_seconds = py::cast<double>(
        required(thresholds, "utility_lcb_min_seconds"));
    config.calibration_ece_max = py::cast<double>(
        required(thresholds, "calibration_ece_max"));
  } else if (config.kind == "pairwise_ensemble_selective") {
    const py::dict pairwise =
        required_dict(artifact, "pairwise_artifact");
    const py::dict gate = required_dict(artifact, "gate_artifact");
    if (required_string(pairwise, "schema") !=
            czr005::ics::kG4IRSF17PairwiseEnsembleSchema ||
        required_string(gate, "schema") !=
            czr005::ics::kG4IRSF17SelectiveGateSchema) {
      throw py::value_error(
          "G4IRSF17 trainer pairwise/gate schema mismatch");
    }
    config.artifact_set_id =
        required_string(artifact, "artifact_set_id");
    const std::string pairwise_artifact_set_id =
        required_string(pairwise, "artifact_set_id");
    const std::string gate_artifact_set_id =
        required_string(gate, "artifact_set_id");
    if (config.artifact_set_id.empty() ||
        config.artifact_set_id != pairwise_artifact_set_id ||
        config.artifact_set_id != gate_artifact_set_id) {
      throw py::value_error(
          "G4IRSF17 wrapper/pairwise/gate artifact_set_id mismatch");
    }
    if (required_bool(pairwise, "identity_features_used") ||
        required_bool(pairwise, "outcome_features_used") ||
        required_bool(gate, "identity_features_used")) {
      throw py::value_error(
          "G4IRSF17 runtime artifact must exclude identity/outcome inputs");
    }
    const bool gate_offline_authorized =
        required_bool(gate, "authorized");
    const bool gate_runtime_authorized =
        required_bool(gate, "runtime_closed_loop_authorized");
    if (config.authorized != gate_offline_authorized ||
        config.runtime_closed_loop_authorized !=
            gate_runtime_authorized) {
      throw py::value_error(
          "G4IRSF17 adapter authorization disagrees with gate artifact");
    }
    const py::dict calibration =
        required_dict(gate, "calibration");
    if (!required_bool(calibration, "available")) {
      throw py::value_error(
          "G4IRSF17 pairwise ensemble requires calibrated export");
    }
    config.calibration_ece = py::cast<double>(
        required(calibration, "promotion_ece"));
    const py::dict selector = required_dict(gate, "selector");
    config.benefit_probability_lcb_min = py::cast<double>(
        required(selector, "benefit_probability_lcb_min"));
    config.harmful_probability_ucb_max = py::cast<double>(
        required(selector, "harm_probability_ucb_max"));
    config.utility_lcb_min_seconds = py::cast<double>(
        required(selector, "utility_lcb_min_seconds"));
    config.calibration_ece_max = py::cast<double>(
        required(selector, "calibration_ece_max"));
    config.lower_quantile =
        py::cast<double>(required(selector, "lower_quantile"));
    config.upper_quantile =
        py::cast<double>(required(selector, "upper_quantile"));
    const int exported_ensemble_size = strict_python_integer_argument(
        required(selector, "ensemble_size"),
        "g4irsf17 selector ensemble_size");
    config.minimum_ensemble_size = 3;
    if (!required_bool(selector,
                       "supervisor_authorization_required") ||
        !required_bool(selector, "ood_abstention_required")) {
      throw py::value_error(
          "G4IRSF17 ensemble requires supervisor and OOD abstention gates");
    }

    const auto parse_linear_members =
        [&](const char* field)
        -> std::vector<
            czr005::ics::G4IRSF17StandardizedLinearMember> {
      const auto value = required(pairwise, field);
      if (!py::isinstance<py::list>(value) &&
          !py::isinstance<py::tuple>(value)) {
        throw py::type_error(
            std::string("G4IRSF17 ensemble field must be list: ") +
            field);
      }
      std::vector<
          czr005::ics::G4IRSF17StandardizedLinearMember> members;
      for (const py::handle item :
           py::reinterpret_borrow<py::sequence>(value)) {
        if (!py::isinstance<py::dict>(item)) {
          throw py::type_error(
              "G4IRSF17 ensemble member must be an object");
        }
        const auto member =
            py::reinterpret_borrow<py::dict>(item);
        if (required_bool(member, "identity_features_used")) {
          throw py::value_error(
              "G4IRSF17 ensemble member used identity features");
        }
        czr005::ics::G4IRSF17StandardizedLinearMember parsed;
        parsed.family = required_string(member, "family");
        if (member.contains("objective")) {
          parsed.objective = required_string(member, "objective");
        }
        parsed.feature_names =
            py::cast<std::vector<std::string>>(
                required(member, "feature_names"));
        parsed.mean = py::cast<std::vector<double>>(
            required(member, "mean"));
        parsed.scale = py::cast<std::vector<double>>(
            required(member, "scale"));
        parsed.weights = py::cast<std::vector<double>>(
            required(member, "weights"));
        parsed.bias = py::cast<double>(required(member, "bias"));
        members.push_back(std::move(parsed));
      }
      return members;
    };
    const auto parse_calibrators =
        [&](const char* field)
        -> std::vector<czr005::ics::G4IRSF17PlattCalibrator> {
      const auto value = required(pairwise, field);
      if (!py::isinstance<py::list>(value) &&
          !py::isinstance<py::tuple>(value)) {
        throw py::type_error(
            std::string("G4IRSF17 calibrator field must be list: ") +
            field);
      }
      std::vector<czr005::ics::G4IRSF17PlattCalibrator> calibrators;
      for (const py::handle item :
           py::reinterpret_borrow<py::sequence>(value)) {
        if (!py::isinstance<py::dict>(item)) {
          throw py::type_error(
              "G4IRSF17 calibrator must be an object");
        }
        const auto calibrator =
            py::reinterpret_borrow<py::dict>(item);
        if (required_string(calibrator, "family") !=
            "platt_logistic") {
          throw py::value_error(
              "G4IRSF17 calibrator family must be platt_logistic");
        }
        calibrators.push_back(
            czr005::ics::G4IRSF17PlattCalibrator{
                py::cast<double>(required(calibrator, "slope")),
                py::cast<double>(required(calibrator, "intercept"))});
      }
      return calibrators;
    };
    config.benefit_members =
        parse_linear_members("benefit_members");
    config.harmful_members =
        parse_linear_members("harm_members");
    config.utility_members =
        parse_linear_members("utility_members");
    config.benefit_calibrators =
        parse_calibrators("benefit_calibrators");
    config.harmful_calibrators =
        parse_calibrators("harm_calibrators");
    if (exported_ensemble_size !=
            static_cast<int>(config.benefit_members.size()) ||
        config.harmful_members.size() !=
            config.benefit_members.size() ||
        config.utility_members.size() !=
            config.benefit_members.size()) {
      throw py::value_error(
          "G4IRSF17 selector/model ensemble sizes disagree");
    }
    config.utility_residual_q05_seconds = py::cast<double>(
        required(pairwise, "utility_residual_q05_seconds"));
    const py::dict envelope =
        required_dict(pairwise, "ood_envelope");
    if (required_string(envelope, "family") !=
            "quantile_feature_envelope" ||
        required_bool(envelope, "identity_features_used")) {
      throw py::value_error(
          "G4IRSF17 OOD envelope schema/identity contract mismatch");
    }
    config.feature_names = py::cast<std::vector<std::string>>(
        required(envelope, "feature_names"));
    config.feature_lower = py::cast<std::vector<double>>(
        required(envelope, "lower"));
    config.feature_upper = py::cast<std::vector<double>>(
        required(envelope, "upper"));
  }
  config.validate();
  return config;
}

czr005::ics::G4IRSF18MergeLinearPolicyConfig
g4irsf18_merge_policy_config_from_artifact(
    const std::string& mode,
    const py::dict& artifact,
    bool research_closed_loop_authorized,
    bool fixed_research_workload,
    bool production_closed_loop_authorized,
    bool offline_gate_passed,
    double coverage_cap,
    const py::object& max_overrides_per_segment_value,
    bool kill_switch) {
  czr005::ics::G4IRSF18MergeLinearPolicyConfig config;
  config.mode = mode;
  config.research_closed_loop_authorized =
      research_closed_loop_authorized;
  config.fixed_research_workload = fixed_research_workload;
  config.production_closed_loop_authorized =
      production_closed_loop_authorized;
  config.offline_gate_passed = offline_gate_passed;
  config.coverage_cap = coverage_cap;
  config.max_overrides_per_segment = strict_python_integer_argument(
      max_overrides_per_segment_value,
      "g4irsf18_merge_max_overrides_per_segment");
  config.kill_switch = kill_switch;
  if (!artifact.empty()) {
    const auto optional_string = [&](const char* name,
                                     std::string& target) {
      if (!artifact.contains(name)) {
        return;
      }
      if (!py::isinstance<py::str>(artifact[name])) {
        throw py::type_error(
            std::string("G4IRSF18 artifact field must be string: ") + name);
      }
      target = py::cast<std::string>(artifact[name]);
    };
    const auto optional_bool = [&](const char* name, bool& target) {
      if (!artifact.contains(name)) {
        return;
      }
      if (!py::isinstance<py::bool_>(artifact[name])) {
        throw py::type_error(
            std::string("G4IRSF18 artifact field must be bool: ") + name);
      }
      target = py::cast<bool>(artifact[name]);
    };
    optional_string("schema", config.schema);
    optional_string("family", config.family);
    optional_string("feature_contract", config.feature_contract);
    optional_string("score_direction", config.score_direction);
    optional_string("tie_break", config.tie_break);
    optional_string("tie_break_scope", config.tie_break_scope);
    optional_string("ood_fallback", config.ood_fallback);
    optional_string("authorization", config.authorization);
    optional_bool("identity_features_used", config.identity_features_used);
    optional_bool("outcome_features_used", config.outcome_features_used);
    optional_bool(
        "production_closed_loop_authorized",
        config.artifact_production_closed_loop_authorized);
    if (artifact.contains("feature_names")) {
      config.feature_names = py::cast<std::vector<std::string>>(
          artifact["feature_names"]);
    }
    if (artifact.contains("mean")) {
      config.mean = py::cast<std::vector<double>>(artifact["mean"]);
    }
    if (artifact.contains("scale")) {
      config.scale = py::cast<std::vector<double>>(artifact["scale"]);
    }
    if (artifact.contains("weights")) {
      config.weights = py::cast<std::vector<double>>(artifact["weights"]);
    }
    if (artifact.contains("feature_lower")) {
      config.feature_lower = py::cast<std::vector<double>>(
          artifact["feature_lower"]);
    }
    if (artifact.contains("feature_upper")) {
      config.feature_upper = py::cast<std::vector<double>>(
          artifact["feature_upper"]);
    }
    if (artifact.contains("bias")) {
      if (PyBool_Check(artifact["bias"].ptr()) ||
          (!py::isinstance<py::float_>(artifact["bias"]) &&
           !py::isinstance<py::int_>(artifact["bias"]))) {
        throw py::type_error("G4IRSF18 artifact bias must be numeric, not bool");
      }
      config.bias = py::cast<double>(artifact["bias"]);
    }
    if (artifact.contains("starvation_policy") &&
        py::isinstance<py::dict>(artifact["starvation_policy"])) {
      const auto starvation =
          py::reinterpret_borrow<py::dict>(artifact["starvation_policy"]);
      if (starvation.contains("threshold_seconds")) {
        config.starvation_threshold_seconds =
            py::cast<double>(starvation["threshold_seconds"]);
      }
    }
  }
  // Structural/semantic artifact mismatch is deliberately not raised here:
  // native telemetry records INVALID_ARTIFACT and the action falls back to J2.
  config.validate_controls();
  return config;
}

py::list g4irsf11_event_runtime_bag_rows(
    const std::vector<czr005::ics::EventRuntimeBagResult>& bags,
    bool include_destination_merge_grants) {
  py::list rows;
  for (const auto& bag : bags) {
    py::dict row;
    row["segment_id"] = bag.segment_id;
    row["task_id"] = bag.task_id;
    row["runtime_bag_id"] = bag.runtime_bag_id;
    row["start"] = bag.start;
    row["goal"] = bag.goal;
    row["final_node"] = bag.final_node;
    row["arrival_time"] = bag.arrival_time;
    row["release_time"] = bag.release_time;
    row["deadline"] = bag.deadline;
    row["source"] = bag.source;
    row["admitted_time"] = bag.admitted_time;
    row["finish_time"] = bag.finish_time;
    row["source_queue_delay"] = bag.source_queue_delay;
    row["total_local_wait"] = bag.total_local_wait;
    row["junction_queue_wait_seconds"] =
        bag.junction_queue_wait_seconds;
    if (include_destination_merge_grants) {
      row["merge_grant_wait_seconds"] =
          bag.merge_grant_wait_seconds;
    }
    row["edge_travel_time_seconds"] =
        bag.edge_travel_time_seconds;
    row["node_service_time_seconds"] =
        bag.node_service_time_seconds;
    row["loop_extra_time_seconds"] =
        bag.loop_extra_time_seconds;
    row["goal_completion_time_seconds"] =
        bag.goal_completion_time_seconds;
    row["decision_count"] = bag.decision_count;
    row["retry_count"] = bag.retry_count;
    row["loop_count"] = bag.loop_count;
    row["completed"] = bag.completed;
    row["starved"] = bag.starved;
    row["failure_reason"] = bag.failure_reason;
    row["short_history"] = bag.short_history;
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf14_merge_grant_lifecycle_rows(
    const std::vector<
        czr005::ics::DestinationMergeGrantLifecycleRow>& lifecycle) {
  py::list rows;
  for (const auto& event : lifecycle) {
    if (event.segment_id == nullptr) {
      throw std::logic_error(
          "merge grant lifecycle row is missing immutable segment identity");
    }
    py::dict row;
    row["time"] = event.time;
    row["request_id"] = py::int_(event.request_id);
    row["grant_id"] = py::int_(event.grant_id);
    row["lineage"] = py::int_(event.lineage);
    row["request_generation"] =
        py::int_(event.request_generation);
    row["junction_queue_generation"] =
        py::int_(event.junction_queue_generation);
    row["runtime_bag_id"] = event.runtime_bag_id;
    row["task_id"] = event.task_id;
    row["segment_id"] = *event.segment_id;
    row["upstream_node"] = event.upstream_node;
    row["destination_node"] = event.destination_node;
    row["edge_from_node"] = event.edge.from_node;
    row["edge_to_node"] = event.edge.to_node;
    row["request_time"] = event.request_time;
    row["fifo_request_time"] = event.fifo_request_time;
    row["earliest_edge_entry"] = event.earliest_edge_entry;
    row["exact_edge_travel_seconds"] =
        event.exact_edge_travel_seconds;
    row["projected_arrival"] = event.projected_arrival;
    row["goal"] = event.goal;
    row["route_score"] = event.route_score;
    row["static_remaining"] = event.static_remaining;
    row["destination_service_seconds"] =
        event.destination_service_seconds;
    row["downstream_queue_pressure"] =
        event.downstream_queue_pressure;
    row["deadline_slack"] = event.deadline_slack;
    row["wait_age"] = event.wait_age;
    row["task_class_code"] = event.task_class_code;
    row["task_class"] = event.task_class;
    row["storage_leg"] = event.storage_leg;
    row["source_release_age"] = event.source_release_age;
    row["local_queue_age"] = event.local_queue_age;
    row["enqueue_sequence"] =
        py::int_(event.enqueue_sequence);
    row["request_expiry"] = event.request_expiry;
    row["slot_start"] = event.slot_start;
    row["slot_end"] = event.slot_end;
    row["issue_time"] = event.issue_time;
    row["grant_expiry"] = event.grant_expiry;
    row["calendar_generation"] =
        py::int_(event.calendar_generation);
    row["fault_generation"] = event.fault_generation;
    row["advertised_fault_generation"] =
        event.advertised_fault_generation;
    row["observed_claimed_request_generation"] =
        py::int_(event.observed_claimed_request_generation);
    row["observed_claimed_junction_queue_generation"] =
        py::int_(
            event.observed_claimed_junction_queue_generation);
    row["observed_claimed_calendar_generation"] =
        py::int_(event.observed_claimed_calendar_generation);
    row["observed_claimed_owner_runtime_bag_id"] =
        event.observed_claimed_owner_runtime_bag_id;
    row["observed_claimed_edge_from_node"] =
        event.observed_claimed_edge.from_node;
    row["observed_claimed_edge_to_node"] =
        event.observed_claimed_edge.to_node;
    row["observed_claimed_destination_node"] =
        event.observed_claimed_destination_node;
    row["observed_event_owner_runtime_bag_id"] =
        event.observed_event_owner_runtime_bag_id;
    row["observed_event_edge_from_node"] =
        event.observed_event_edge.from_node;
    row["observed_event_edge_to_node"] =
        event.observed_event_edge.to_node;
    row["observed_event_destination_node"] =
        event.observed_event_destination_node;
    row["observed_junction_queue_generation"] =
        py::int_(event.observed_junction_queue_generation);
    row["observed_calendar_generation"] =
        py::int_(event.observed_calendar_generation);
    row["observed_physical_fault_generation"] =
        event.observed_physical_fault_generation;
    row["observed_advertised_fault_generation"] =
        event.observed_advertised_fault_generation;
    row["observed_physical_fault_active"] =
        event.observed_physical_fault_active;
    row["observed_exact_calendar_reservation_present"] =
        event.observed_exact_calendar_reservation_present;
    row["state"] = czr005::ics::merge_grant_state_name(
        event.state);
    row["reason"] = czr005::ics::merge_grant_reason_name(
        event.reason);
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf11_event_runtime_event_rows(
    const std::vector<czr005::ics::EventRuntimeTraceRow>& events) {
  py::list rows;
  for (const auto& event : events) {
    py::dict row;
    row["seq"] = py::int_(event.seq);
    row["event"] = event.event;
    row["time"] = event.time;
    row["task_id"] = event.task_id;
    row["runtime_bag_id"] = event.runtime_bag_id;
    row["segment_id"] = event.segment_id;
    row["node"] = event.node;
    row["from_node"] = event.from_node;
    row["to_node"] = event.to_node;
    row["reason"] = event.reason;
    row["selected_edge_count"] = event.selected_edge_count;
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf11_event_candidate_rows(
    const std::vector<czr005::ics::EventCandidateRecord>& candidates) {
  py::list rows;
  for (const auto& candidate : candidates) {
    py::dict features;
    features["static_potential"] = candidate.static_potential;
    features["travel_time"] = candidate.travel_time;
    features["target_queue_length"] = candidate.target_queue_length;
    features["target_scheduled_incoming"] = candidate.target_scheduled_incoming;
    features["corridor_next_available"] = candidate.corridor_next_available;
    features["target_next_available"] = candidate.target_next_available;
    features["advertised_fault"] = candidate.advertised_fault;
    features["fault_message_age_seconds"] = candidate.fault_message_age_seconds;
    features["recent_visit_count"] = candidate.recent_visit_count;
    features["two_hop_queue_pressure"] = candidate.two_hop_queue_pressure;
    features["current_goal_queue_length"] =
        candidate.current_goal_queue_length;
    features["target_goal_queue_length"] =
        candidate.target_goal_queue_length;
    features["target_goal_scheduled_incoming"] =
        candidate.target_goal_scheduled_incoming;
    features["current_goal_max_wait"] = candidate.current_goal_max_wait;
    features["goal_conditioned_differential"] =
        candidate.goal_conditioned_differential;
    features["estimated_service_rate"] = candidate.estimated_service_rate;
    features["service_weighted_pressure"] =
        candidate.service_weighted_pressure;
    features["first_edge_credit_required"] =
        candidate.first_edge_credit_required;
    features["first_edge_credit_matches"] =
        candidate.first_edge_credit_matches;
    features["first_edge_credit_valid"] =
        candidate.first_edge_credit_valid;
    features["first_edge_credit_slack_seconds"] =
        candidate.first_edge_credit_slack_seconds;

    py::dict row;
    row["next_node"] = candidate.next_node;
    row["features"] = std::move(features);
    row["model_score"] = candidate.model_score;
    // These are scorer outputs, not candidate input features. Keeping them
    // outside features prevents accidental feedback into later training.
    row["scorer_raw_score"] = candidate.scorer_raw_score;
    row["scorer_raw_bottleneck"] =
        candidate.scorer_raw_bottleneck;
    row["shield_allowed"] = candidate.shield_allowed;
    row["shield_reason"] = candidate.shield_reason;
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf11_event_decision_rows(
    const std::vector<czr005::ics::EventDecisionTraceRow>& decisions,
    const std::string& scenario,
    double scale,
    bool hold_attempts) {
  py::list rows;
  for (const auto& decision : decisions) {
    py::dict local_snapshot;
    local_snapshot["junction_queue_length"] = decision.junction_queue_length;
    local_snapshot["next_available_time"] = decision.junction_next_dispatch_time;
    local_snapshot["faulted_outgoing_count"] = decision.advertised_faulted_outgoing_count;
    local_snapshot["message_age_seconds"] = decision.max_fault_message_age_seconds;
    int downstream_pressure = 0;
    std::vector<int> candidate_nodes;
    candidate_nodes.reserve(decision.candidates.size());
    for (const auto& candidate : decision.candidates) {
      candidate_nodes.push_back(candidate.next_node);
      downstream_pressure += candidate.target_queue_length + candidate.target_scheduled_incoming;
    }
    local_snapshot["downstream_pressure"] = downstream_pressure;

    py::dict metadata;
    metadata["scenario"] = scenario;
    metadata["scale"] = scale;
    metadata["decision_ordinal"] = py::int_(decision.decision_id);
    metadata["arrive_event_seq"] = py::int_(decision.arrive_event_seq);
    metadata["runtime_bag_id"] = decision.runtime_bag_id;
    metadata["model_score_semantics"] = "lower_is_better_cost";
    metadata["trace_kind"] = hold_attempts ? "hold_attempt" : "committed_edge_action";
    metadata["scorer_id"] = decision.scorer_id;
    // Requested and effective IDs differ only when the frozen scorer's risk
    // gate abstains to the exact historical S0 score.
    metadata["scorer_effective_id"] =
        decision.scorer_effective_id;
    metadata["scorer_risk_abstain"] =
        decision.scorer_risk_abstain;
    std::string scorer_risk_reasons;
    for (const auto& reason : decision.scorer_risk_reasons) {
      if (!scorer_risk_reasons.empty()) {
        scorer_risk_reasons += ";";
      }
      scorer_risk_reasons += reason;
    }
    metadata["scorer_risk_reasons"] =
        scorer_risk_reasons;
    metadata["scorer_raw_prediction"] =
        decision.scorer_raw_prediction;
    metadata["scorer_raw_margin"] =
        decision.scorer_raw_prediction >= 0
            ? py::cast(decision.scorer_raw_margin)
            : py::none();
    const bool scorer_raw_fallback_disagreement =
        decision.scorer_risk_abstain &&
        decision.scorer_raw_prediction >= 0 &&
        decision.model_prediction >= 0 &&
        decision.scorer_raw_prediction !=
            decision.model_prediction;
    metadata["scorer_raw_fallback_disagreement"] =
        scorer_raw_fallback_disagreement;
    metadata["scorer_raw_score_semantics"] =
        decision.scorer_id.rfind("S1_", 0) == 0 ||
                decision.scorer_id.rfind("S2_", 0) == 0
            ? "higher_is_better_frozen_adapter_score"
            : "lower_is_better_cost";
    metadata["priority_mode"] = decision.priority_mode;
    metadata["task_class"] = decision.task_class;
    metadata["priority_slack_seconds"] =
        decision.priority_slack_seconds;
    metadata["priority_age_seconds"] =
        decision.priority_age_seconds;
    metadata["priority_local_contention"] =
        decision.priority_local_contention;
    metadata["priority_fault_generation"] =
        py::int_(decision.priority_fault_generation);
    metadata["priority_enqueue_sequence"] =
        py::int_(decision.priority_enqueue_sequence);
    metadata["pibt_preference_mode"] =
        decision.pibt_preference_mode;

    py::dict row;
    row["schema_id"] = "czr005.g4irsf11.decision_trace.v1";
    row["schema_version"] = 1;
    row["decision_id"] = scenario + ":" + std::to_string(decision.task_id) + ":" +
                         std::to_string(decision.decision_id);
    row["task_id"] = decision.task_id;
    row["segment_id"] = decision.segment_id;
    row["event_time"] = decision.event_time;
    row["current_node"] = decision.current_node;
    row["goal_node"] = decision.goal_node;
    row["candidate_next_nodes"] = candidate_nodes;
    row["candidate_records"] = g4irsf11_event_candidate_rows(decision.candidates);
    if (decision.model_prediction >= 0) {
      row["model_prediction"] = decision.model_prediction;
    } else {
      row["model_prediction"] = py::none();
    }
    row["model_margin"] = decision.model_margin;
    row["risk_gate_triggered"] = decision.risk_gate_triggered;
    if (decision.fallback_selected_next >= 0) {
      row["fallback_selected_next"] = decision.fallback_selected_next;
    } else {
      row["fallback_selected_next"] = py::none();
    }
    if (decision.selected_next >= 0) {
      row["selected_next"] = decision.selected_next;
    } else {
      row["selected_next"] = py::none();
    }
    row["decision_source"] = decision.decision_source;
    row["rule_reason"] = decision.rule_reason;
    row["local_snapshot"] = std::move(local_snapshot);
    row["short_history"] = decision.short_history;
    row["full_astar_used"] = false;
    row["model_fallback_disagreement"] =
        decision.fallback_selected_next >= 0 &&
        decision.fallback_selected_next != decision.model_prediction;
    row["scorer_raw_fallback_disagreement"] =
        scorer_raw_fallback_disagreement;
    row["candidate_ordering"] = "next_node_ascending";
    if (decision.g4irsf24_dlp_evaluated) {
      py::dict dlp;
      dlp["mode"] = decision.g4irsf24_dlp_mode;
      dlp["s4_next"] = decision.g4irsf24_dlp_s4_next;
      dlp["proposed_next"] =
          decision.g4irsf24_dlp_proposed_next >= 0
              ? py::cast(decision.g4irsf24_dlp_proposed_next)
              : py::none();
      dlp["residual_seconds"] =
          decision.g4irsf24_dlp_residual_seconds;
      dlp["edge_support"] =
          decision.g4irsf24_dlp_edge_support;
      dlp["value_support"] =
          decision.g4irsf24_dlp_value_support;
      dlp["fallback_reason"] =
          decision.g4irsf24_dlp_fallback_reason.empty()
              ? py::none()
              : py::cast(
                    decision.g4irsf24_dlp_fallback_reason);
      dlp["committed_mutation"] =
          decision.g4irsf24_dlp_committed_mutation;
      row["g4irsf24_dlp"] = std::move(dlp);
    }
    if (decision.g4irsf16_evaluated) {
      const auto finite_or_none = [](double value) -> py::object {
        return std::isfinite(value) ? py::cast(value) : py::none();
      };
      py::dict supervisor;
      supervisor["mode"] = decision.g4irsf16_mode;
      supervisor["baseline_next"] =
          decision.g4irsf16_baseline_next >= 0
              ? py::cast(decision.g4irsf16_baseline_next)
              : py::none();
      supervisor["proposed_next"] =
          decision.g4irsf16_proposed_next >= 0
              ? py::cast(decision.g4irsf16_proposed_next)
              : py::none();
      supervisor["proposed_hold"] =
          decision.g4irsf16_proposed_hold;
      supervisor["action_changed"] =
          decision.g4irsf16_action_changed;
      supervisor["state"] = decision.g4irsf16_state;
      supervisor["action"] = decision.g4irsf16_action;
      supervisor["source"] = decision.g4irsf16_source;
      supervisor["reason"] = decision.g4irsf16_reason;
      supervisor["node_generation"] =
          py::int_(decision.g4irsf16_node_generation);
      supervisor["state_generation"] =
          py::int_(decision.g4irsf16_state_generation);
      py::dict i3;
      i3["candidate"] = decision.g4irsf16_i3_candidate >= 0
                              ? py::cast(decision.g4irsf16_i3_candidate)
                              : py::none();
      i3["activation"] = decision.g4irsf16_i3_activation;
      i3["benefit_probability_lcb"] =
          decision.g4irsf16_i3_benefit_lcb;
      i3["harmful_probability_ucb"] =
          decision.g4irsf16_i3_harmful_ucb;
      i3["utility_lcb_seconds"] = finite_or_none(
          decision.g4irsf16_i3_utility_lcb_seconds);
      i3["ood"] = decision.g4irsf16_i3_ood;
      i3["reason"] = decision.g4irsf16_i3_model_reason;
      py::dict i4;
      i4["activation"] = decision.g4irsf16_i4_activation;
      i4["diagnostic_only"] =
          decision.g4irsf16_i4_diagnostic_only;
      i4["policy_id"] = decision.g4irsf16_i4_policy_id;
      i4["benefit_probability_lcb"] =
          decision.g4irsf16_i4_benefit_lcb;
      i4["harmful_probability_ucb"] =
          decision.g4irsf16_i4_harmful_ucb;
      i4["utility_lcb_seconds"] = finite_or_none(
          decision.g4irsf16_i4_utility_lcb_seconds);
      i4["ood"] = decision.g4irsf16_i4_ood;
      i4["reason"] = decision.g4irsf16_i4_model_reason;
      supervisor["i3"] = std::move(i3);
      supervisor["i4"] = std::move(i4);
      row["g4irsf16_supervisor"] = std::move(supervisor);
    }
    row["metadata"] = std::move(metadata);
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf11_event_runtime_junction_rows(
    const std::vector<czr005::ics::EventRuntimeJunctionResult>& junctions) {
  py::list rows;
  for (const auto& junction : junctions) {
    py::dict row;
    row["node"] = junction.node;
    row["final_source_queue_length"] = junction.final_source_queue_length;
    row["peak_source_queue_length"] = junction.peak_source_queue_length;
    row["final_junction_queue_length"] = junction.final_junction_queue_length;
    row["peak_junction_queue_length"] = junction.peak_junction_queue_length;
    row["final_service_calendar_intervals"] = junction.final_service_calendar_intervals;
    row["peak_service_calendar_intervals"] = junction.peak_service_calendar_intervals;
    row["final_local_state_accounted_bytes"] =
        py::int_(junction.final_local_state_accounted_bytes);
    row["peak_local_state_accounted_bytes"] =
        py::int_(junction.peak_local_state_accounted_bytes);
    row["local_state_accounting_semantics"] =
        "cpp_object_plus_live_deque_payload_plus_calendar_capacity_lower_bound";
    row["service_reservation_count"] = py::int_(junction.service_reservation_count);
    row["cumulative_service_reserved_seconds"] =
        junction.cumulative_service_reserved_seconds;
    row["first_service_reservation_start_time"] =
        junction.first_service_reservation_start_time;
    row["last_service_reservation_end_time"] =
        junction.last_service_reservation_end_time;
    row["scheduled_incoming"] = junction.scheduled_incoming;
    row["next_dispatch_time"] = junction.next_dispatch_time;
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf11_event_runtime_fault_rows(
    const std::vector<czr005::ics::EventRuntimeFaultAuditRow>& fault_events) {
  py::list rows;
  for (const auto& event : fault_events) {
    py::dict row;
    row["seq"] = py::int_(event.seq);
    row["event"] = event.event;
    row["phase"] = event.phase;
    row["time"] = event.time;
    row["from_node"] = event.from_node;
    row["to_node"] = event.to_node;
    row["physical_active_count"] = event.physical_active_count;
    row["physical_generation"] = event.physical_generation;
    row["inflight_traversal_count"] = event.inflight_traversal_count;
    row["notification_dropped"] = event.notification_dropped;
    row["task_id"] = event.task_id;
    row["runtime_bag_id"] = event.runtime_bag_id;
    row["segment_id"] = event.segment_id;
    row["current_node"] = event.current_node;
    row["intended_next_node"] = event.intended_next_node;
    row["selected_next_node"] = event.selected_next_node;
    row["fault_policy_enabled"] = event.fault_policy_enabled;
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf12_event_runtime_credit_rows(
    const std::vector<czr005::ics::EventRuntimeCreditAuditRow>& credit_events) {
  py::list rows;
  for (const auto& event : credit_events) {
    py::dict row;
    row["time"] = event.time;
    row["action"] = event.action;
    row["reason"] = event.reason;
    row["credit_id"] = py::int_(event.credit_id);
    row["from"] = event.from_node;
    row["to"] = event.to_node;
    row["goal"] = event.goal;
    row["from_node"] = event.from_node;
    row["to_node"] = event.to_node;
    row["earliest"] = event.earliest;
    row["latest"] = event.latest;
    row["generation"] = py::int_(event.generation);
    row["expiry"] = event.expiry;
    row["capacity"] = event.capacity;
    row["owner_or_unbound"] = event.owner_or_unbound;
    row["fault_generation"] = event.fault_generation;
    row["state"] = event.state;
    row["task_id"] = event.task_id;
    row["segment_id"] = event.segment_id;
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf12_event_runtime_pibt_rows(
    const std::vector<czr005::ics::EventRuntimePIBTAuditRow>& pibt_events) {
  py::list rows;
  for (const auto& event : pibt_events) {
    py::dict row;
    row["activation_id"] = py::int_(event.activation_id);
    row["time"] = event.time;
    row["trigger_node"] = event.trigger_node;
    row["trigger_runtime_bag_id"] = event.trigger_runtime_bag_id;
    row["mode"] = event.mode;
    row["outcome"] = event.outcome;
    row["blocker"] = event.blocker;
    row["local_slice_bag_count"] = event.local_slice_bag_count;
    row["local_slice_resource_count"] =
        event.local_slice_resource_count;
    row["local_slice_candidate_count"] =
        event.local_slice_candidate_count;
    row["proposed_action_count"] = event.proposed_action_count;
    row["committed_action_count"] = event.committed_action_count;
    row["inherited_action_count"] = event.inherited_action_count;
    row["max_inheritance_depth"] = event.max_inheritance_depth;
    row["backtrack_count"] = event.backtrack_count;
    row["cycle_guard_count"] = event.cycle_guard_count;
    row["rollback_count"] = event.rollback_count;
    row["transaction_credit_entry_count"] =
        event.transaction_credit_entry_count;
    row["transaction_bag_entry_count"] =
        event.transaction_bag_entry_count;
    row["transaction_junction_scalar_entry_count"] =
        event.transaction_junction_scalar_entry_count;
    row["transaction_action_delta_count"] =
        event.transaction_action_delta_count;
    py::list actions;
    for (const auto& action : event.actions) {
      py::dict action_row;
      action_row["runtime_bag_id"] = action.bag_id;
      action_row["from_node"] = action.from_node;
      action_row["next_node"] = action.next_node;
      action_row["priority_rank"] = action.priority_rank;
      action_row["inheritance_depth"] = action.inheritance_depth;
      action_row["inherited"] = action.inherited;
      action_row["expected_fault_generation"] =
          py::int_(action.expected_fault_generation);
      action_row["claimed_resource_count"] =
          static_cast<int>(action.claimed_resources.size());
      actions.append(std::move(action_row));
    }
    row["actions"] = std::move(actions);
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf17_source_wait_blocker_rows(
    const std::vector<
        czr005::ics::EventRuntimeSourceWaitBlockerRow>& events) {
  // Identity fields below are emitted for trace correlation only.
  py::list rows;
  for (const auto& event : events) {
    py::dict row;
    row["interval_ordinal"] = py::int_(event.interval_ordinal);
    row["reason"] = event.reason;
    row["reason_precedence"] = event.reason_precedence;
    row["source_node"] = event.source_node;
    row["blocker_node"] = event.blocker_node;
    row["blocker_resource"] = event.blocker_resource;
    row["blocker_resource_from_node"] =
        event.blocker_resource_from_node;
    row["blocker_resource_to_node"] =
        event.blocker_resource_to_node;
    row["source_generation"] = py::int_(event.source_generation);
    row["blocker_generation"] = py::int_(event.blocker_generation);
    row["wait_start_time"] = event.wait_start_time;
    row["wait_end_time"] = event.wait_end_time;
    row["wait_seconds"] = event.wait_seconds;
    row["affected_bag_count"] = event.affected_bag_count;
    row["wait_bag_seconds"] = event.wait_bag_seconds;
    row["selected_task_id"] = event.selected_task_id;
    row["selected_runtime_bag_id"] =
        event.selected_runtime_bag_id;
    row["selected_segment_id"] = event.selected_segment_id;
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf17_source_policy_rows(
    const std::vector<
        czr005::ics::EventRuntimeG4IRSF17SourcePolicyRow>& events) {
  py::list rows;
  const auto candidate_names =
      czr005::ics::g4irsf17_source_candidate_feature_names();
  const auto context_names =
      czr005::ics::g4irsf17_source_context_feature_names();
  const auto pairwise_names =
      czr005::ics::g4irsf17_source_pairwise_feature_names();
  for (const auto& event : events) {
    py::dict row;
    row["schema"] = "czr005.g4irsf17.source_front_decision.v1";
    row["decision_ordinal"] = py::int_(event.decision_ordinal);
    row["event_time"] = event.event_time;
    row["source_node"] = event.source_node;
    row["mode"] = event.mode;
    row["kind"] = event.kind;
    row["artifact_set_id"] = event.artifact_set_id;
    row["top_k"] = event.top_k;
    row["source_queue_length"] = event.source_queue_length;
    row["source_generation"] = py::int_(event.source_generation);
    row["candidate_queue_indices"] = event.candidate_queue_indices;
    row["candidate_task_ids"] = event.candidate_task_ids;
    row["candidate_runtime_bag_ids"] = event.candidate_runtime_bag_ids;
    row["candidate_segment_ids"] = event.candidate_segment_ids;
    py::list candidate_feature_names;
    for (const char* name : candidate_names) {
      candidate_feature_names.append(name);
    }
    row["candidate_feature_names"] = std::move(candidate_feature_names);
    py::list context_feature_names;
    for (const char* name : context_names) {
      context_feature_names.append(name);
    }
    row["context_feature_names"] = std::move(context_feature_names);
    py::list pairwise_feature_names;
    for (const char* name : pairwise_names) {
      pairwise_feature_names.append(name);
    }
    row["pairwise_feature_names"] = std::move(pairwise_feature_names);

    py::list context_features;
    for (const double value : event.context_features) {
      context_features.append(value);
    }
    row["context_features"] = context_features;
    row["shared_context_features"] = context_features;
    py::list pairwise_features;
    for (const double value : event.pairwise_features) {
      pairwise_features.append(value);
    }
    row["pairwise_features"] = std::move(pairwise_features);

    py::list candidate_features;
    py::list canonical_candidate_observations;
    for (const auto& values : event.candidate_features) {
      py::list candidate;
      py::list canonical;
      for (const double value : values) {
        candidate.append(value);
        canonical.append(value);
      }
      for (const double value : event.context_features) {
        canonical.append(value);
      }
      candidate_features.append(std::move(candidate));
      canonical_candidate_observations.append(std::move(canonical));
    }
    row["candidate_features"] = std::move(candidate_features);
    row["canonical_candidate_observations"] =
        std::move(canonical_candidate_observations);
    row["baseline_candidate_index"] = event.baseline_candidate_index;
    row["proposed_candidate_index"] = event.proposed_candidate_index;
    row["treatment_candidate_index"] = event.treatment_candidate_index;
    row["chosen_candidate_index"] = event.chosen_candidate_index;
    row["baseline_queue_index"] = event.baseline_queue_index;
    row["treatment_queue_index"] = event.treatment_queue_index;
    row["proposed_queue_index"] = event.proposed_queue_index;
    row["chosen_queue_index"] = event.chosen_queue_index;
    row["activated"] = event.activated;
    row["out_of_distribution"] = event.out_of_distribution;
    row["supervisor_authorized"] = event.supervisor_authorized;
    row["reason"] = event.reason;
    row["model_score"] = event.model_score;
    row["benefit_probability_lcb"] =
        event.benefit_probability_lcb;
    row["harmful_probability_ucb"] =
        event.harmful_probability_ucb;
    row["utility_lcb_seconds"] = event.utility_lcb_seconds;
    row["calibration_ece"] = event.calibration_ece;
    row["identity_fields_are_trace_only"] = true;
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf14_source_opportunity_rows(
    const std::vector<
        czr005::ics::EventRuntimeSourceOpportunityRow>& events) {
  py::list rows;
  for (const auto& event : events) {
    py::dict row;
    row["event_time"] = event.event_time;
    row["timestamp_bits"] = py::int_(event.timestamp_bits);
    row["source_node"] = event.source_node;
    row["queue_length_before_enqueue"] =
        event.queue_length_before_enqueue;
    row["queue_length_after_enqueue"] =
        event.queue_length_after_enqueue;
    row["queue_length_before_arbitration"] =
        event.queue_length_before_arbitration;
    row["queue_length_after_arbitration"] =
        event.queue_length_after_arbitration;
    row["same_timestamp_release_batch_size"] =
        event.same_timestamp_release_batch_size;
    row["same_time_pending_source_releases"] =
        event.same_time_pending_source_releases;
    row["same_time_pending_shared_merge_releases"] =
        event.same_time_pending_shared_merge_releases;
    row["ready_set_size"] = event.ready_set_size;
    row["priority_comparison_count"] =
        event.priority_comparison_count;
    row["chosen_task_id"] = event.chosen_task_id;
    row["chosen_runtime_bag_id"] =
        event.chosen_runtime_bag_id;
    row["chosen_segment_id"] = event.chosen_segment_id;
    row["queue_discipline"] = event.queue_discipline;
    row["event_seq"] = py::int_(event.event_seq);
    row["arbitration_generation"] =
        py::int_(event.arbitration_generation);
    row["batched_arbitration"] =
        event.batched_arbitration;
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf14_junction_opportunity_rows(
    const std::vector<
        czr005::ics::EventRuntimeJunctionOpportunityRow>& events) {
  py::list rows;
  for (const auto& event : events) {
    py::dict row;
    row["event_time"] = event.event_time;
    row["timestamp_bits"] = py::int_(event.timestamp_bits);
    row["junction_node"] = event.junction_node;
    row["queue_length_before_enqueue"] =
        event.queue_length_before_enqueue;
    row["queue_length_after_enqueue"] =
        event.queue_length_after_enqueue;
    row["queue_length_before_arbitration"] =
        event.queue_length_before_arbitration;
    row["queue_length_after_arbitration"] =
        event.queue_length_after_arbitration;
    row["same_timestamp_arrival_batch_size"] =
        event.same_timestamp_arrival_batch_size;
    row["same_time_pending_arrivals"] =
        event.same_time_pending_arrivals;
    row["same_time_pending_shared_merge_requests"] =
        event.same_time_pending_shared_merge_requests;
    row["ready_set_size"] = event.ready_set_size;
    row["priority_comparison_count"] =
        event.priority_comparison_count;
    row["pibt_slice_bag_count"] =
        event.pibt_slice_bag_count;
    row["pibt_owner_count"] = event.pibt_owner_count;
    row["chosen_task_id"] = event.chosen_task_id;
    row["chosen_runtime_bag_id"] =
        event.chosen_runtime_bag_id;
    row["chosen_segment_id"] = event.chosen_segment_id;
    row["event_seq"] = py::int_(event.event_seq);
    row["arbitration_generation"] =
        py::int_(event.arbitration_generation);
    row["batched_arbitration"] =
        event.batched_arbitration;
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf14_merge_visibility_rows(
    const std::vector<
        czr005::ics::EventRuntimeMergeVisibilityRow>& events) {
  py::list rows;
  for (const auto& event : events) {
    py::dict row;
    row["event_time"] = event.event_time;
    row["timestamp_bits"] = py::int_(event.timestamp_bits);
    row["destination_node"] = event.destination_node;
    row["upstream_node"] = event.upstream_node;
    row["incoming_edge_start"] =
        event.incoming_edge_start;
    row["incoming_edge_end"] = event.incoming_edge_end;
    row["requesting_task_id"] =
        event.requesting_task_id;
    row["requesting_runtime_bag_id"] =
        event.requesting_runtime_bag_id;
    row["requesting_segment_id"] =
        event.requesting_segment_id;
    row["earliest_arrival"] = event.earliest_arrival;
    row["slot_start"] = event.slot_start;
    row["slot_end"] = event.slot_end;
    row["known_competing_request_count"] =
        event.known_competing_request_count;
    row["later_same_time_competitor_count"] =
        event.later_same_time_competitor_count;
    row["later_same_time_competitor_exists"] =
        event.later_same_time_competitor_exists;
    row["seq_determined_order"] =
        event.seq_determined_order;
    row["event_seq"] = py::int_(event.event_seq);
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf18_merge_service_opportunity_rows(
    const std::vector<
        czr005::ics::EventRuntimeMergeServiceOpportunityRow>& events) {
  py::list rows;
  for (const auto& event : events) {
    py::dict row;
    row["opportunity_id"] = py::int_(event.opportunity_id);
    row["event_time"] = event.event_time;
    row["destination_node"] = event.destination_node;
    row["controller_generation"] =
        py::int_(event.controller_generation);
    row["timing_mode"] = event.timing_mode;
    row["candidate_count"] = event.candidate_count;
    row["baseline_winner_request_id"] =
        py::int_(event.baseline_winner_request_id);
    row["chosen_winner_request_id"] =
        py::int_(event.chosen_winner_request_id);
    row["candidate_request_id"] =
        py::int_(event.candidate_request_id);
    row["upstream_node"] = event.upstream_node;
    row["projected_arrival"] = event.projected_arrival;
    row["deadline_slack"] = event.deadline_slack;
    row["wait_age"] = event.wait_age;
    row["destination_service_seconds"] =
        event.destination_service_seconds;
    row["downstream_queue_pressure"] =
        event.downstream_queue_pressure;
    row["route_score"] = event.route_score;
    row["static_remaining"] = event.static_remaining;
    row["task_class_code"] = event.task_class_code;
    row["task_class"] = event.task_class;
    row["storage_leg"] = event.storage_leg;
    row["baseline_winner"] = event.baseline_winner;
    row["chosen_winner"] = event.chosen_winner;
    if (!event.model_policy_mode.empty()) {
      row["model_policy_mode"] = event.model_policy_mode;
      row["model_feature_contract"] = event.model_feature_contract;
      row["model_reason"] = event.model_reason;
      row["model_evaluated"] = event.model_evaluated;
      row["model_score_available"] = event.model_score_available;
      row["model_score"] = event.model_score;
      row["model_proposed"] = event.model_proposed;
      row["model_applied"] = event.model_applied;
      row["model_chosen"] = event.model_chosen;
      row["model_out_of_distribution"] =
          event.model_out_of_distribution;
      row["model_invalid"] = event.model_invalid;
      row["model_fallback"] = event.model_fallback;
      row["model_baseline_request_id"] =
          py::int_(event.model_baseline_request_id);
      row["model_proposed_request_id"] =
          py::int_(event.model_proposed_request_id);
      py::list feature_names;
      for (const char* name :
           czr005::ics::g4irsf18_merge_feature_names()) {
        feature_names.append(name);
      }
      row["model_feature_names"] = std::move(feature_names);
      py::list features;
      for (const double value : event.model_features) {
        features.append(value);
      }
      row["model_features"] = std::move(features);
    }
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf14_event_seq_audit_rows(
    const std::vector<
        czr005::ics::EventRuntimeEventSeqAuditRow>& events) {
  py::list rows;
  for (const auto& event : events) {
    py::dict row;
    row["event_time"] = event.event_time;
    row["timestamp_bits"] = py::int_(event.timestamp_bits);
    row["boundary"] = event.boundary;
    row["node"] = event.node;
    row["destination_node"] = event.destination_node;
    row["ready_set_size"] = event.ready_set_size;
    row["priority_comparison_count"] =
        event.priority_comparison_count;
    row["later_same_time_competitor_count"] =
        event.later_same_time_competitor_count;
    row["chosen_runtime_bag_id"] =
        event.chosen_runtime_bag_id;
    row["chosen_enqueue_sequence"] =
        py::int_(event.chosen_enqueue_sequence);
    row["event_seq"] = py::int_(event.event_seq);
    row["seq_determined_order"] =
        event.seq_determined_order;
    row["reason"] = event.reason;
    rows.append(std::move(row));
  }
  return rows;
}

py::list g4irsf14_arbitration_batch_rows(
    const std::vector<
        czr005::ics::EventRuntimeArbitrationBatchRow>& events) {
  py::list rows;
  for (const auto& event : events) {
    py::dict row;
    row["event_time"] = event.event_time;
    row["timestamp_bits"] = py::int_(event.timestamp_bits);
    row["boundary"] = event.boundary;
    row["node"] = event.node;
    row["enqueue_count"] = event.enqueue_count;
    row["ready_set_size"] = event.ready_set_size;
    row["pending_same_time_event_count"] =
        event.pending_same_time_event_count;
    row["chosen_runtime_bag_id"] =
        event.chosen_runtime_bag_id;
    row["event_seq"] = py::int_(event.event_seq);
    row["arbitration_generation"] =
        py::int_(event.arbitration_generation);
    rows.append(std::move(row));
  }
  return rows;
}

py::dict g4irsf14_state_digest_row(
    const czr005::ics::G4IRSF14RuntimeStateDigests& digests) {
  digests.validate();
  py::dict row;
  row["event_queue_sha256"] = digests.event_queue_sha256;
  row["current_time_sha256"] = digests.current_time_sha256;
  row["bags_sha256"] = digests.bags_sha256;
  row["source_queues_sha256"] = digests.source_queues_sha256;
  row["junction_queues_sha256"] = digests.junction_queues_sha256;
  row["local_service_calendars_sha256"] =
      digests.local_service_calendars_sha256;
  row["corridor_state_sha256"] = digests.corridor_state_sha256;
  row["scheduled_incoming_sha256"] =
      digests.scheduled_incoming_sha256;
  row["credits_sha256"] = digests.credits_sha256;
  row["merge_grants_sha256"] = digests.merge_grants_sha256;
  row["fault_state_sha256"] = digests.fault_state_sha256;
  row["pibt_owner_state_sha256"] =
      digests.pibt_owner_state_sha256;
  row["deterministic_counters_sha256"] =
      digests.deterministic_counters_sha256;
  row["scorer_state_sha256"] = digests.scorer_state_sha256;
  row["result_accumulator_sha256"] =
      digests.result_accumulator_sha256;
  row["current_runtime_hashes_sha256"] =
      digests.current_runtime_hashes_sha256;
  row["congestion_beacons_sha256"] =
      digests.congestion_beacons_sha256;
  row["microphase_state_sha256"] =
      digests.microphase_state_sha256;
  return row;
}

py::dict g4irsf14_replay_hash_row(
    const czr005::ics::G4IRSF14CloneReplayHashes& hashes) {
  hashes.validate();
  py::dict row;
  row["complete_bags_sha256"] = hashes.complete_bags_sha256;
  row["segment_result_sha256"] = hashes.segment_result_sha256;
  row["junction_state_sha256"] = hashes.junction_state_sha256;
  row["algorithm_summary_sha256"] =
      hashes.algorithm_summary_sha256;
  row["deterministic_result_sha256"] =
      hashes.deterministic_result_sha256;
  return row;
}

py::dict g4irsf14_clone_branch_invariants(
    const czr005::ics::EventDrivenJunctionResult& result) {
  const auto& summary = result.summary;
  py::dict row;
  row["requested_count"] = summary.requested_count;
  row["completed_count"] = summary.completed_count;
  row["failed_segment_count"] = summary.failed_count;
  row["event_count"] = summary.event_count;
  row["g4irsf14_i2_live_eligible_multi_request_boundary_count"] =
      py::int_(
          summary
              .g4irsf14_i2_live_eligible_multi_request_boundary_count);
  row["g4irsf14_i5_prefilter_candidate_count"] =
      py::int_(summary.g4irsf14_i5_prefilter_candidate_count);
  row["g4irsf14_i5_applicable_ready_slice_boundary_count"] =
      py::int_(
          summary.g4irsf14_i5_applicable_ready_slice_boundary_count);
  row["unsafe_entry_count"] =
      summary.physical_fault_edge_entry_violation_count;
  row["reservation_conflict_count"] =
      summary.reservation_conflicts;
  row["runtime_full_astar_call_count"] =
      summary.runtime_full_astar_calls;
  row["runtime_global_scan_count"] =
      summary.global_reservation_scan_count +
      summary.priority_global_scan_count +
      summary.scorer_runtime_global_scan_count +
      summary.microphase_runtime_global_scan_count +
      summary.first_edge_credit_global_scan_count;
  row["runtime_future_route_read_count"] =
      summary.priority_future_route_input_count +
      summary.scorer_future_route_input_count +
      summary.first_edge_credit_future_route_count;
  row["runtime_future_schedule_read_count"] =
      summary.scorer_future_schedule_input_count;
  row["teacher_input_count"] =
      summary.priority_teacher_input_count +
      summary.scorer_teacher_input_count;
  row["priority_teacher_input_count"] =
      summary.priority_teacher_input_count;
  row["scorer_teacher_input_count"] =
      summary.scorer_teacher_input_count;
  row["full_future_routes_stored"] = 0;
  row["bag_future_path_field_present"] = false;
  row["reservation_depth"] = 1;
  row["max_selected_edges_per_bag"] =
      summary.max_edges_selected_per_bag_per_decision;
  row["two_step_reservation_count"] =
      summary.two_step_reservation_count;
  row["unresolved_deadlock_count"] =
      summary.unresolved_deadlock_count;
  row["event_limit_reached"] = summary.event_limit_reached;
  row["time_limit_reached"] = summary.time_limit_reached;
  row["merge_grant_conservation_holds"] =
      summary.merge_grant_conservation_holds;
  row["merge_grant_active_bijection_holds"] =
      summary.merge_grant_active_bijection_holds;
  row["merge_grant_final_active_unconsumed"] =
      summary.merge_grant_final_active_unconsumed;
  row["merge_grant_outstanding_request_count"] =
      py::int_(summary.merge_grant_outstanding_request_count);
  row["merge_grant_stale_arbitration_count"] =
      py::int_(summary.merge_grant_stale_arbitration_count);
  row["merge_grant_lifecycle_dropped_count"] =
      py::int_(summary.merge_grant_lifecycle_dropped_count);
  row["merge_grant_lifecycle_complete"] =
      summary.merge_grant_lifecycle_dropped_count == 0;
  row["merge_grant_runtime_owned_capability"] =
      summary.merge_grant_runtime_owned_capability;
  row["merge_grant_exact_slot_no_future_shift"] =
      summary.merge_grant_exact_slot_no_future_shift;
  const bool merge_grant_active_state_integrity =
      summary.merge_grant_conservation_holds &&
      summary.merge_grant_active_bijection_holds &&
      summary.merge_grant_runtime_owned_capability &&
      summary.merge_grant_exact_slot_no_future_shift &&
      summary.merge_grant_final_active_unconsumed == 0 &&
      summary.merge_grant_outstanding_request_count == 0;
  row["merge_grant_active_state_integrity_pass"] =
      merge_grant_active_state_integrity;
  row["merge_grant_protocol_integrity_pass"] =
      merge_grant_active_state_integrity &&
      summary.merge_grant_lifecycle_dropped_count == 0;
  row["stale_arbitration_event_count"] =
      py::int_(summary.stale_arbitration_event_count);
  row["artificial_batch_delay_seconds"] =
      summary.artificial_batch_delay_seconds;
  return row;
}

void require_g4irsf14_clone_branch_hard_gates(
    const czr005::ics::EventDrivenJunctionResult& result) {
  const auto& summary = result.summary;
  const int runtime_global_scan_count =
      summary.global_reservation_scan_count +
      summary.priority_global_scan_count +
      summary.scorer_runtime_global_scan_count +
      summary.microphase_runtime_global_scan_count +
      summary.first_edge_credit_global_scan_count;
  const int runtime_future_route_read_count =
      summary.priority_future_route_input_count +
      summary.scorer_future_route_input_count +
      summary.first_edge_credit_future_route_count;
  const int runtime_future_schedule_read_count =
      summary.scorer_future_schedule_input_count;
  const int teacher_input_count =
      summary.priority_teacher_input_count +
      summary.scorer_teacher_input_count;
  // A bounded passive lifecycle trace may be truncated on the original 1x
  // workload.  Truncation is reported and compared across all replay
  // branches, but it cannot invalidate the live protocol state: the trace is
  // not an input to arbitration, reservation, or grant consumption.
  const bool merge_active_state_integrity =
      summary.merge_grant_conservation_holds &&
      summary.merge_grant_active_bijection_holds &&
      summary.merge_grant_runtime_owned_capability &&
      summary.merge_grant_exact_slot_no_future_shift &&
      summary.merge_grant_final_active_unconsumed == 0 &&
      summary.merge_grant_outstanding_request_count == 0;
  if (summary.completed_count != summary.requested_count ||
      summary.failed_count != 0 ||
      summary.physical_fault_edge_entry_violation_count != 0 ||
      summary.reservation_conflicts != 0 ||
      summary.runtime_full_astar_calls != 0 ||
      runtime_global_scan_count != 0 ||
      runtime_future_route_read_count != 0 ||
      runtime_future_schedule_read_count != 0 ||
      teacher_input_count != 0 ||
      summary.max_edges_selected_per_bag_per_decision > 1 ||
      summary.two_step_reservation_count != 0 ||
      summary.unresolved_deadlock_count != 0 ||
      summary.event_limit_reached ||
      summary.time_limit_reached ||
      summary.merge_grant_stale_arbitration_count != 0 ||
      summary.stale_arbitration_event_count != 0 ||
      summary.artificial_batch_delay_seconds != 0.0 ||
      !merge_active_state_integrity) {
    throw std::logic_error(
        "no-op clone branch violated a production hard gate");
  }
}

py::dict g4irsf14_clone_boundary_row(
    const czr005::ics::EventDrivenJunctionSafeBoundary& boundary,
    int processed_event_count) {
  py::dict row;
  row["kind"] = "queue_top_pre_pop";
  row["next_event_type"] =
      czr005::ics::junction_event_name(boundary.next_event_type);
  row["next_event_time"] = boundary.next_event_time;
  row["next_event_time_bits"] = py::int_(
      czr005::ics::event_runtime_detail::timestamp_bits(
          boundary.next_event_time));
  row["next_event_seq"] = py::int_(boundary.next_event_seq);
  row["runtime_bag_id"] = boundary.runtime_bag_id;
  row["node"] = boundary.node;
  row["from_node"] = boundary.from_node;
  row["to_node"] = boundary.to_node;
  row["active_merge_capability_count"] =
      boundary.active_merge_capability_count;
  row["pending_merge_request_count"] =
      boundary.pending_merge_request_count;
  row["active_physical_fault_edge_count"] =
      boundary.active_physical_fault_edge_count;
  row["queued_bag_count"] = boundary.queued_bag_count;
  row["processed_event_count"] = processed_event_count;
  row["runtime_state_sha256"] = boundary.state_sha256;
  row["queue_top_not_popped"] = boundary.queue_top_not_popped;
  row["staged_event_sink_empty"] =
      boundary.staged_event_sink_empty;
  return row;
}

py::dict g4irsf14_state_clone_noop_rerun_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<EventRuntimeBagTuple>& bag_records,
    const py::object& preregistered_event_ordinal_value,
    const std::vector<std::vector<double>>& scorer_w1,
    const std::vector<double>& scorer_b1,
    const std::vector<double>& scorer_w2,
    double scorer_b2,
    double scorer_risk_margin_threshold,
    double scorer_risk_bottleneck_threshold,
    const std::string& scorer_model_sha256) {
  const int preregistered_event_ordinal =
      strict_python_integer_argument(
          preregistered_event_ordinal_value,
          "preregistered_event_ordinal");
  if (preregistered_event_ordinal < 0) {
    throw py::value_error(
        "preregistered_event_ordinal must be non-negative");
  }
  if (bag_records.empty()) {
    throw py::value_error(
        "state-clone no-op rerun requires at least one original request");
  }

  const auto graph =
      graph_from_records(node_records, edge_records, heuristic_time);
  std::vector<czr005::ics::EventRuntimeBagRequest> requests;
  requests.reserve(bag_records.size());
  for (const auto& record : bag_records) {
    requests.push_back(czr005::ics::EventRuntimeBagRequest{
        std::get<0>(record),
        std::get<1>(record),
        std::get<2>(record),
        std::get<3>(record),
        std::get<4>(record),
        std::get<5>(record),
        std::get<6>(record)});
  }

  // This is the frozen Stage-D/Stage-E control tuple.  The no-op fidelity
  // entrypoint intentionally exposes no knobs that could silently drift it.
  czr005::ics::EventDrivenJunctionConfig config;
  config.queue_discipline = "aging";
  config.retry_interval = 0.25;
  config.minimum_service_seconds = 1.0e-3;
  config.dispatch_headway_seconds = 1.0e-3;
  config.history_limit = 8;
  config.max_decisions_per_bag = 512;
  config.max_events = 20000000;
  config.max_simulation_time = -1.0;
  config.trace_limit = 0;
  config.event_trace_limit = 0;
  config.trace_shard_count = 1;
  config.trace_shard_index = 0;
  config.local_queue_capacity = 32;
  config.deadlock_retry_threshold = 8;
  config.diagnostic_hops = 2;
  config.enable_source_admission = false;
  config.enable_backpressure = false;
  config.enable_pibt_lite = false;
  config.enable_deadlock_escape = true;
  config.enable_fault_policy = true;
  config.resource_semantics =
      "R3_java_node_window_compatible";
  config.entry_headway_seconds = 1.0e-3;
  config.pressure_mode = "off";
  config.pressure_weight = 2.0;
  config.pressure_age_weight = 0.05;
  config.pressure_distance_bias = 0.25;
  config.admission_mode = "off";
  config.credit_validity_seconds = 1.0;
  config.credit_snapshot_max_age_seconds = 1.0;
  config.credit_capacity_per_edge = 1;
  config.credit_lifecycle_limit = 512;
  config.pibt_mode = "P2";
  config.pibt_max_ready_bags = 8;
  config.pibt_max_local_resources = 32;
  config.pibt_max_candidates_per_bag = 8;
  config.scorer_mode =
      "S1_frozen_g4e_legal_local_adapter";
  config.scorer_w1 = scorer_w1;
  config.scorer_b1 = scorer_b1;
  config.scorer_w2 = scorer_w2;
  config.scorer_b2 = scorer_b2;
  config.scorer_risk_margin_threshold =
      scorer_risk_margin_threshold;
  config.scorer_risk_bottleneck_threshold =
      scorer_risk_bottleneck_threshold;
  config.scorer_model_sha256 = scorer_model_sha256;
  config.framework_mode = "event_loop_one_step";
  config.priority_mode = "Q0";
  config.pibt_preference_mode = "current";
  config.selective_credit_contention_threshold = 1;
  config.event_semantics =
      "E4_batch_plus_destination_merge_request";
  config.enable_opportunity_telemetry = false;
  config.opportunity_trace_limit = 0;
  config.merge_grant_rule = "M0";
  config.merge_grant_max_pending_requests = 256;
  config.merge_grant_lifecycle_limit = 8192;

  czr005::ics::EventDrivenJunctionRuntime source(graph, config);
  source.initialize(requests);
  for (int index = 0; index < preregistered_event_ordinal;
       ++index) {
    if (!source.process_one_event()) {
      throw py::value_error(
          "preregistered_event_ordinal is not a live pre-pop "
          "boundary for this workload");
    }
  }
  const auto boundary = source.peek_safe_boundary();
  if (!boundary.has_value()) {
    throw py::value_error(
        "preregistered_event_ordinal resolves after the last "
        "live pre-pop boundary");
  }
  const auto source_inventory =
      source.deterministic_state_digests();
  const auto checkpoint = source.capture_state_checkpoint();
  if (checkpoint.state_sha256() !=
          source_inventory.aggregate_sha256() ||
      checkpoint.state_sha256() != boundary->state_sha256) {
    throw std::logic_error(
        "captured checkpoint does not bind the observed boundary inventory");
  }

  czr005::ics::EventDrivenJunctionRuntime baseline(graph, config);
  czr005::ics::EventDrivenJunctionRuntime clone(graph, config);
  czr005::ics::G4IRSF14MatchedRuntimeFork<
      czr005::ics::EventDrivenJunctionRuntime>
      matched_fork(baseline, clone, checkpoint);
  const auto baseline_inventory =
      baseline.deterministic_state_digests();
  const auto clone_inventory =
      clone.deterministic_state_digests();
  if (baseline_inventory.canonical_payload() !=
          source_inventory.canonical_payload() ||
      clone_inventory.canonical_payload() !=
          source_inventory.canonical_payload()) {
    throw std::logic_error(
        "independent no-op branches changed the native state inventory");
  }

  source.drain();
  baseline.drain();
  clone.drain();
  const auto& source_result = source.finalize();
  const auto& baseline_result = baseline.finalize();
  const auto& clone_result = clone.finalize();
  const auto source_hashes = source.deterministic_replay_hashes();
  const auto baseline_hashes =
      baseline.deterministic_replay_hashes();
  const auto clone_hashes = clone.deterministic_replay_hashes();
  const bool exact_match =
      source_hashes.exactly_matches(baseline_hashes) &&
      source_hashes.exactly_matches(clone_hashes);
  if (!exact_match) {
    throw std::logic_error(
        "exact no-op checkpoint replay fidelity is below 100%");
  }
  require_g4irsf14_clone_branch_hard_gates(source_result);
  require_g4irsf14_clone_branch_hard_gates(baseline_result);
  require_g4irsf14_clone_branch_hard_gates(clone_result);

  py::dict controls;
  controls["resource_semantics"] =
      "R3_java_node_window_compatible";
  controls["scorer_mode"] =
      "S1_frozen_g4e_legal_local_adapter";
  controls["pibt_mode"] = "P2";
  controls["admission_mode"] = "off";
  controls["pressure_mode"] = "off";
  controls["priority_mode"] = "Q0";
  controls["event_semantics"] =
      "E4_batch_plus_destination_merge_request";
  controls["merge_grant_rule"] = "M0";
  controls["scale"] = 1.0;
  controls["reservation_depth"] = 1;
  controls["max_events"] = 20000000;
  controls["max_simulation_time"] = -1.0;
  controls["trace_limit"] = 0;
  controls["event_trace_limit"] = 0;

  py::dict payload;
  payload["schema"] =
      "czr005.g4irsf14.exact_binary_noop_rerun.v1";
  payload["evidence_scope"] =
      "NOOP_FIDELITY_MECHANISM_ONLY_NOT_A_CAUSAL_LABEL";
  payload["formal_pass_claimed"] = false;
  payload["intervention_applied"] = false;
  payload["input_request_count"] =
      static_cast<int>(requests.size());
  payload["frozen_controls"] = std::move(controls);
  payload["boundary"] = g4irsf14_clone_boundary_row(
      *boundary, preregistered_event_ordinal);
  payload["runtime_state_sha256"] =
      checkpoint.state_sha256();
  payload["state_components"] =
      g4irsf14_state_digest_row(source_inventory);
  payload["baseline_start_state_sha256"] =
      baseline_inventory.aggregate_sha256();
  payload["baseline_start_state_components"] =
      g4irsf14_state_digest_row(baseline_inventory);
  payload["clone_start_state_sha256"] =
      clone_inventory.aggregate_sha256();
  payload["clone_start_state_components"] =
      g4irsf14_state_digest_row(clone_inventory);
  payload["source_replay_hashes"] =
      g4irsf14_replay_hash_row(source_hashes);
  payload["baseline_replay_hashes"] =
      g4irsf14_replay_hash_row(baseline_hashes);
  payload["clone_replay_hashes"] =
      g4irsf14_replay_hash_row(clone_hashes);
  payload["source_invariants"] =
      g4irsf14_clone_branch_invariants(source_result);
  payload["baseline_invariants"] =
      g4irsf14_clone_branch_invariants(baseline_result);
  payload["clone_invariants"] =
      g4irsf14_clone_branch_invariants(clone_result);
  payload["native_three_way_exact_match"] = exact_match;
  return payload;
}

py::dict g4irsf19_progress_row(
    const czr005::ics::EventRuntimeProgressSnapshot& snapshot,
    double wall_seconds) {
  py::dict row;
  row["schema"] = "czr005.g4irsf19.runtime_progress.v1";
  switch (snapshot.phase) {
    case czr005::ics::EventDrivenJunctionRuntimePhase::kIdle:
      row["phase"] = "IDLE";
      break;
    case czr005::ics::EventDrivenJunctionRuntimePhase::kReady:
      row["phase"] = "READY";
      break;
    case czr005::ics::EventDrivenJunctionRuntimePhase::kStopped:
      row["phase"] = "STOPPED";
      break;
    case czr005::ics::EventDrivenJunctionRuntimePhase::kFinalized:
      row["phase"] = "FINALIZED";
      break;
  }
  row["wall_seconds"] = wall_seconds;
  row["simulated_time"] = snapshot.simulated_time;
  row["requested_bags"] = snapshot.requested_count;
  row["released_bags"] = snapshot.released_count;
  row["completed_bags"] = snapshot.completed_count;
  row["failed_bags"] = snapshot.failed_count;
  row["terminal_bags"] =
      snapshot.completed_count + snapshot.failed_count;
  row["current_backlog"] = snapshot.active_bag_count;
  row["event_total"] = snapshot.event_count;
  row["heap_size"] = snapshot.event_heap_size;
  py::dict event_types;
  event_types["bag_release"] = snapshot.bag_release_event_count;
  event_types["arrive_junction"] =
      snapshot.arrive_junction_event_count;
  event_types["junction_service_complete"] =
      snapshot.junction_service_complete_event_count;
  event_types["edge_enter"] = snapshot.edge_enter_event_count;
  event_types["edge_exit"] = snapshot.edge_exit_event_count;
  event_types["fault"] = snapshot.fault_event_count;
  event_types["repair"] = snapshot.repair_event_count;
  event_types["local_queue_update"] =
      snapshot.local_queue_update_event_count;
  event_types["congestion_beacon_update"] =
      snapshot.congestion_beacon_update_event_count;
  row["event_type_counts"] = std::move(event_types);
  row["source_admission_attempt_count"] =
      snapshot.source_admission_attempt_count;
  row["source_admission_admitted_count"] =
      snapshot.source_admission_admitted_count;
  row["source_admission_hold_count"] =
      snapshot.source_admission_hold_count;
  row["stale_event_count"] =
      snapshot.stale_arbitration_event_count;
  py::dict retries;
  retries["merge_contended_loser"] = snapshot.merge_retry_count;
  row["retry_count_by_reason"] = std::move(retries);
  row["duplicate_wakeup_count"] = snapshot.duplicate_wakeup_count;
  row["coalesced_event_count"] = snapshot.coalesced_wakeup_count;
  if (snapshot.g4irsf20_event_hotpath_policy != "E0") {
    row["g4irsf20_event_hotpath_policy"] =
        snapshot.g4irsf20_event_hotpath_policy;
    row["g4irsf20_redundant_beacon_suppressed_count"] =
        py::int_(
            snapshot.g4irsf20_redundant_beacon_suppressed_count);
    row["g4irsf20_same_state_beacon_suppressed_count"] =
        py::int_(
            snapshot.g4irsf20_same_state_beacon_suppressed_count);
  }
  return row;
}

py::dict g4irsf11_event_runtime_from_records(
    const std::vector<NodeRecordTuple>& node_records,
    const std::vector<EdgeRecordTuple>& edge_records,
    const std::vector<std::vector<double>>& heuristic_time,
    const std::vector<EventRuntimeBagTuple>& bag_records,
    const py::sequence& fault_windows,
    const std::string& queue_discipline,
    double retry_interval,
    double minimum_service_seconds,
    double dispatch_headway_seconds,
    int history_limit,
    int max_decisions_per_bag,
    int max_events,
    double max_simulation_time,
    int trace_limit,
    int trace_shard_count,
    int trace_shard_index,
    int local_queue_capacity,
    int deadlock_retry_threshold,
    int diagnostic_hops,
    bool enable_source_admission,
    bool enable_backpressure,
    bool enable_pibt_lite,
    bool enable_deadlock_escape,
    bool enable_fault_policy,
    const std::string& scenario,
    double scale,
    const std::string& resource_semantics,
    double entry_headway_seconds,
    const std::string& pressure_mode,
    double pressure_weight,
    double pressure_age_weight,
    double pressure_distance_bias,
    const std::string& admission_mode,
    double credit_validity_seconds,
    double credit_snapshot_max_age_seconds,
    int credit_capacity_per_edge,
    int credit_lifecycle_limit,
    const std::string& pibt_mode,
    int pibt_max_ready_bags,
    int pibt_max_local_resources,
    int pibt_max_candidates_per_bag,
    const std::string& scorer_mode,
    const std::vector<std::vector<double>>& scorer_w1,
    const std::vector<double>& scorer_b1,
    const std::vector<double>& scorer_w2,
    double scorer_b2,
    double scorer_risk_margin_threshold,
    double scorer_risk_bottleneck_threshold,
    const std::string& scorer_model_sha256,
    const std::string& framework_mode,
    const std::optional<int>& event_trace_limit,
    const std::string& priority_mode,
    const std::string& pibt_preference_mode,
    const std::vector<EventRuntimeRegretPriorTuple>&
        pibt_regret_prior_records,
    int selective_credit_contention_threshold,
    const std::string& event_semantics,
    bool enable_opportunity_telemetry,
    int opportunity_trace_limit,
    const std::string& merge_grant_rule,
    const py::object& merge_grant_max_pending_requests_value,
    const py::object& merge_grant_lifecycle_limit_value,
    const std::string& g4irsf16_supervisor_mode,
    const py::dict& g4irsf16_i3_model_artifact,
    const py::dict& g4irsf16_i4_model_artifact,
    const py::dict& g4irsf16_rule_bundle,
    bool enable_g4irsf17_source_wait_telemetry,
    int g4irsf17_source_wait_trace_limit,
    const std::string& g4irsf17_source_policy_mode,
    const py::dict& g4irsf17_source_policy_artifact,
    int g4irsf17_source_policy_trace_limit,
    const std::string& merge_grant_timing_mode,
    const std::string& g4irsf18_merge_policy_mode,
    const py::dict& g4irsf18_merge_policy_artifact,
    bool g4irsf18_merge_research_closed_loop_authorized,
    bool g4irsf18_merge_fixed_research_workload,
    bool g4irsf18_merge_production_closed_loop_authorized,
    bool g4irsf18_merge_offline_gate_passed,
    double g4irsf18_merge_coverage_cap,
    const py::object& g4irsf18_merge_max_overrides_per_segment,
    bool g4irsf18_merge_kill_switch,
    double bounded_wall_seconds,
    int bounded_check_every_events,
    const std::string& g4irsf20_event_hotpath_policy,
    const py::dict& g4irsf24_dlp_artifact) {
  // Keep G4IRSF13/G4IRSF14 controls append-only so existing positional callers
  // retain the exact F2/Q0/P0/E0 behavior.
  const int merge_grant_max_pending_requests =
      strict_python_integer_argument(
          merge_grant_max_pending_requests_value,
          "merge_grant_max_pending_requests");
  const int merge_grant_lifecycle_limit =
      strict_python_integer_argument(
          merge_grant_lifecycle_limit_value,
          "merge_grant_lifecycle_limit");
  const bool requested_destination_merge_grants =
      event_semantics == "E4" ||
      event_semantics ==
          "E4_batch_plus_destination_merge_request";
  const std::string canonical_merge_grant_timing_mode =
      canonical_merge_grant_timing_mode_for_binding(
          merge_grant_timing_mode);
  const bool g4irsf18_merge_policy_enabled =
      g4irsf18_merge_policy_mode != "off";
  if (g4irsf18_merge_policy_enabled &&
      (!requested_destination_merge_grants ||
       canonical_merge_grant_timing_mode !=
           "jit_fair_aging_deadline")) {
    throw py::value_error(
        "G4IRSF18 learned merge policy requires E4 with "
        "jit_fair_aging_deadline (J2) timing");
  }
  if (merge_grant_max_pending_requests <= 0) {
    throw py::value_error(
        "merge_grant_max_pending_requests must be positive");
  }
  if (merge_grant_lifecycle_limit < 0) {
    throw py::value_error(
        "merge_grant_lifecycle_limit must be non-negative");
  }
  if (!requested_destination_merge_grants &&
      (merge_grant_rule != "M1" ||
       merge_grant_max_pending_requests != 64 ||
       merge_grant_lifecycle_limit != 1024 ||
       canonical_merge_grant_timing_mode != "eager")) {
    throw py::value_error(
        "merge grant controls are only valid with E4 destination "
        "merge-request semantics");
  }
  if (requested_destination_merge_grants &&
      admission_mode != "off" &&
      admission_mode != "legacy_unbound") {
    throw std::invalid_argument(
        "E4 vertical slice requires frozen C0 admission; first-edge "
        "credits are not destination merge capabilities");
  }
  if (requested_destination_merge_grants &&
      resource_semantics != "R3" &&
      resource_semantics !=
          "R3_java_node_window_compatible") {
    throw std::invalid_argument(
        "E4 destination merge grants require frozen R3 node-window "
        "semantics");
  }
  if (requested_destination_merge_grants &&
      pibt_mode != "P2") {
    throw std::invalid_argument(
        "E4 destination merge grants require the frozen P2 bounded-local "
        "PIBT mode");
  }
  const bool destination_merge_scorer_allowed =
      scorer_mode == "S1" ||
      scorer_mode == "S1_frozen_g4e_legal_local_adapter" ||
      scorer_mode == "S2" ||
      scorer_mode == "S2_frozen_g4e_without_absolute_node_ids" ||
      scorer_mode == "S3" ||
      scorer_mode == "S3_shortest_potential_only" ||
      scorer_mode == "S4" ||
      scorer_mode == "S4_queue_aware_rule_only";
  if (requested_destination_merge_grants &&
      !destination_merge_scorer_allowed) {
    throw std::invalid_argument(
        "E4 destination merge grants require an existing S1/S2/S3/S4 "
        "legal-local scorer");
  }
  if (!std::isfinite(bounded_wall_seconds) ||
      (bounded_wall_seconds != -1.0 && bounded_wall_seconds <= 0.0)) {
    throw py::value_error(
        "bounded_wall_seconds must be -1 (disabled) or positive");
  }
  if (bounded_check_every_events <= 0) {
    throw py::value_error(
        "bounded_check_every_events must be positive");
  }
  if (g4irsf20_event_hotpath_policy != "E0" &&
      g4irsf20_event_hotpath_policy != "E1" &&
      g4irsf20_event_hotpath_policy != "E2") {
    throw py::value_error(
        "g4irsf20_event_hotpath_policy must be E0, E1, or E2");
  }
  if (requested_destination_merge_grants &&
      priority_mode != "Q0" &&
      priority_mode != "current_f2") {
    throw std::invalid_argument(
        "E4 destination merge grants require the frozen Q0 priority mode");
  }
  const auto graph = graph_from_records(node_records, edge_records, heuristic_time);
  std::vector<czr005::ics::EventRuntimeBagRequest> requests;
  requests.reserve(bag_records.size());
  for (const auto& record : bag_records) {
    requests.push_back(czr005::ics::EventRuntimeBagRequest{
        std::get<0>(record),
        std::get<1>(record),
        std::get<2>(record),
        std::get<3>(record),
        std::get<4>(record),
        std::get<5>(record),
        std::get<6>(record)});
  }
  std::vector<czr005::ics::EventRuntimeFaultWindow> faults;
  faults.reserve(static_cast<std::size_t>(py::len(fault_windows)));
  for (const py::handle item : fault_windows) {
    const auto record = py::reinterpret_borrow<py::sequence>(item);
    const auto field_count = py::len(record);
    if (field_count != 5 && field_count != 6) {
      throw std::invalid_argument(
          "fault window must be (start,end,fault_time,repair_time,message_delay[,drop_notification])");
    }
    faults.push_back(czr005::ics::EventRuntimeFaultWindow{
        py::cast<int>(record[0]),
        py::cast<int>(record[1]),
        py::cast<double>(record[2]),
        py::cast<double>(record[3]),
        py::cast<double>(record[4]),
        field_count == 6 ? py::cast<bool>(record[5]) : false});
  }

  czr005::ics::EventDrivenJunctionConfig config;
  config.queue_discipline = queue_discipline;
  config.retry_interval = retry_interval;
  config.minimum_service_seconds = minimum_service_seconds;
  config.dispatch_headway_seconds = dispatch_headway_seconds;
  config.history_limit = history_limit;
  config.max_decisions_per_bag = max_decisions_per_bag;
  config.max_events = max_events;
  config.max_simulation_time = max_simulation_time;
  config.trace_limit = trace_limit;
  config.event_trace_limit = event_trace_limit;
  config.trace_shard_count = trace_shard_count;
  config.trace_shard_index = trace_shard_index;
  config.local_queue_capacity = local_queue_capacity;
  config.deadlock_retry_threshold = deadlock_retry_threshold;
  config.diagnostic_hops = diagnostic_hops;
  config.enable_source_admission = enable_source_admission;
  config.enable_backpressure = enable_backpressure;
  config.enable_pibt_lite = enable_pibt_lite;
  config.enable_deadlock_escape = enable_deadlock_escape;
  config.enable_fault_policy = enable_fault_policy;
  config.resource_semantics = resource_semantics;
  config.entry_headway_seconds = entry_headway_seconds;
  config.pressure_mode = pressure_mode;
  config.pressure_weight = pressure_weight;
  config.pressure_age_weight = pressure_age_weight;
  config.pressure_distance_bias = pressure_distance_bias;
  config.admission_mode = admission_mode;
  config.credit_validity_seconds = credit_validity_seconds;
  config.credit_snapshot_max_age_seconds =
      credit_snapshot_max_age_seconds;
  config.credit_capacity_per_edge = credit_capacity_per_edge;
  config.credit_lifecycle_limit = credit_lifecycle_limit;
  config.pibt_mode = pibt_mode;
  config.pibt_max_ready_bags = pibt_max_ready_bags;
  config.pibt_max_local_resources = pibt_max_local_resources;
  config.pibt_max_candidates_per_bag =
      pibt_max_candidates_per_bag;
  config.scorer_mode = scorer_mode;
  config.scorer_w1 = scorer_w1;
  config.scorer_b1 = scorer_b1;
  config.scorer_w2 = scorer_w2;
  config.scorer_b2 = scorer_b2;
  config.scorer_risk_margin_threshold =
      scorer_risk_margin_threshold;
  config.scorer_risk_bottleneck_threshold =
      scorer_risk_bottleneck_threshold;
  config.scorer_model_sha256 = scorer_model_sha256;
  config.framework_mode = framework_mode;
  config.priority_mode = priority_mode;
  config.pibt_preference_mode = pibt_preference_mode;
  config.selective_credit_contention_threshold =
      selective_credit_contention_threshold;
  config.event_semantics = event_semantics;
  config.enable_opportunity_telemetry =
      enable_opportunity_telemetry;
  config.opportunity_trace_limit = opportunity_trace_limit;
  config.merge_grant_rule = merge_grant_rule;
  config.merge_grant_timing_mode =
      canonical_merge_grant_timing_mode;
  config.merge_grant_max_pending_requests =
      merge_grant_max_pending_requests;
  config.merge_grant_lifecycle_limit =
      merge_grant_lifecycle_limit;
  config.g4irsf16_supervisor_mode =
      g4irsf16_supervisor_mode;
  config.g4irsf16_i3_model =
      g4irsf16_model_config_from_artifact(
          g4irsf16_i3_model_artifact);
  config.g4irsf16_i4_model =
      g4irsf16_model_config_from_artifact(
          g4irsf16_i4_model_artifact);
  config.g4irsf16_i4_diagnostic_rule =
      g4irsf16_i4_rule_config_from_bundle(
          g4irsf16_rule_bundle);
  config.enable_g4irsf17_source_wait_telemetry =
      enable_g4irsf17_source_wait_telemetry;
  config.g4irsf17_source_wait_trace_limit =
      g4irsf17_source_wait_trace_limit;
  config.g4irsf17_source_policy =
      g4irsf17_source_policy_config_from_artifact(
          g4irsf17_source_policy_mode,
          g4irsf17_source_policy_artifact);
  config.g4irsf17_source_policy_trace_limit =
      g4irsf17_source_policy_trace_limit;
  config.g4irsf18_merge_policy =
      g4irsf18_merge_policy_config_from_artifact(
          g4irsf18_merge_policy_mode,
          g4irsf18_merge_policy_artifact,
          g4irsf18_merge_research_closed_loop_authorized,
          g4irsf18_merge_fixed_research_workload,
          g4irsf18_merge_production_closed_loop_authorized,
          g4irsf18_merge_offline_gate_passed,
          g4irsf18_merge_coverage_cap,
          g4irsf18_merge_max_overrides_per_segment,
          g4irsf18_merge_kill_switch);
  config.g4irsf20_event_hotpath_policy =
      g4irsf20_event_hotpath_policy;
  config.g4irsf24_dlp =
      g4irsf24_dlp_config_from_artifact(
          g4irsf24_dlp_artifact);
  config.pibt_regret_prior_records.reserve(
      pibt_regret_prior_records.size());
  for (const auto& record : pibt_regret_prior_records) {
    config.pibt_regret_prior_records.push_back(
        czr005::ics::EventRuntimeRegretPriorRecord{
            std::get<0>(record),
            std::get<1>(record),
            std::get<2>(record),
            std::get<3>(record)});
  }

  czr005::ics::EventDrivenJunctionRuntime runtime(graph, config);
  const auto wall_started = std::chrono::steady_clock::now();
  const auto wall_elapsed = [&wall_started]() {
    return std::chrono::duration<double>(
               std::chrono::steady_clock::now() - wall_started)
        .count();
  };
  std::vector<std::pair<double, czr005::ics::EventRuntimeProgressSnapshot>>
      progress_history;
  double next_progress_wall_seconds = 5.0;
  bool bounded_progress = false;
  const czr005::ics::EventDrivenJunctionResult* finalized_result = nullptr;
  {
    // Everything above this boundary parses or owns Python objects.  The
    // runtime below is pure C++ and instance-local, so independent Python
    // callers may execute it concurrently.  Reacquire the GIL before any
    // py::dict/py::list construction in either the bounded or full result
    // path.
    py::gil_scoped_release release;
    runtime.initialize(requests, faults);
    if (bounded_wall_seconds > 0.0) {
      const double elapsed = wall_elapsed();
      progress_history.emplace_back(elapsed, runtime.progress_snapshot());
      bounded_progress = elapsed >= bounded_wall_seconds;
    }
    while (!bounded_progress && runtime.process_one_event()) {
      if (bounded_wall_seconds <= 0.0 ||
          runtime.current_result().summary.event_count %
                  bounded_check_every_events !=
              0) {
        continue;
      }
      const double elapsed = wall_elapsed();
      if (elapsed >= next_progress_wall_seconds) {
        progress_history.emplace_back(elapsed, runtime.progress_snapshot());
        next_progress_wall_seconds =
            5.0 * (std::floor(elapsed / 5.0) + 1.0);
      }
      bounded_progress = elapsed >= bounded_wall_seconds;
    }
    if (!(bounded_progress &&
          runtime.phase() ==
              czr005::ics::EventDrivenJunctionRuntimePhase::kReady)) {
      finalized_result = &runtime.finalize();
    }
  }
  if (bounded_progress &&
      runtime.phase() ==
          czr005::ics::EventDrivenJunctionRuntimePhase::kReady) {
    const double elapsed = wall_elapsed();
    const auto progress = runtime.progress_snapshot();
    if (progress_history.empty() ||
        progress_history.back().second.event_count != progress.event_count) {
      progress_history.emplace_back(elapsed, progress);
    }
    py::list history_rows;
    for (const auto& entry : progress_history) {
      history_rows.append(g4irsf19_progress_row(entry.second, entry.first));
    }
    py::dict payload;
    payload["execution_status"] = "BOUNDED_PROGRESS";
    payload["stop_reason"] = "WALL_LIMIT";
    payload["bounded_wall_seconds"] = bounded_wall_seconds;
    payload["bounded_check_every_events"] =
        bounded_check_every_events;
    payload["progress"] =
        g4irsf19_progress_row(progress, elapsed);
    payload["progress_history"] = std::move(history_rows);
    py::dict summary = g4irsf11_event_runtime_summary_row(
        runtime.current_result().summary,
        requested_destination_merge_grants,
        merge_grant_rule,
        merge_grant_max_pending_requests,
        merge_grant_lifecycle_limit);
    summary["runtime_seconds"] = elapsed;
    summary["end_time"] = progress.simulated_time;
    summary["final_active_bag_count"] = progress.active_bag_count;
    summary["bounded_progress"] = true;
    payload["summary"] = std::move(summary);
    return payload;
  }
  if (finalized_result == nullptr) {
    throw std::logic_error(
        "event runtime full result was not finalized");
  }
  const auto& result = *finalized_result;
  py::dict trace_context;
  trace_context["schema_id"] = "czr005.g4irsf11.decision_trace.v1";
  trace_context["scenario"] = scenario;
  trace_context["scale"] = scale;
  trace_context["candidate_ordering"] = "next_node_ascending";
  trace_context["model_score_semantics"] = "lower_is_better_cost";
  trace_context["scorer_id"] = result.summary.scorer_id;
  trace_context["scorer_model_sha256"] =
      result.summary.scorer_model_sha256;
  trace_context["scorer_score_direction"] =
      result.summary.scorer_score_direction;
  trace_context["scorer_claim_boundary"] =
      result.summary.scorer_claim_boundary;
  trace_context["scorer_out_of_distribution_diagnostic"] =
      result.summary.scorer_out_of_distribution_diagnostic;
  trace_context["scorer_promotion_eligible"] = false;
  trace_context["scorer_teacher_input_count"] = 0;
  trace_context["scorer_future_route_input_count"] = 0;
  trace_context["scorer_future_schedule_input_count"] = 0;
  trace_context["scorer_posthoc_input_count"] = 0;
  trace_context["scorer_runtime_global_scan_count"] = 0;
  trace_context["reservation_depth"] = 1;
  trace_context["diagnostic_hops"] = diagnostic_hops;
  trace_context["trace_limit"] = trace_limit;
  trace_context["event_trace_limit"] =
      result.summary.event_trace_limit;
  trace_context["event_trace_limit_inherited"] =
      result.summary.event_trace_limit_inherited;
  trace_context["trace_shard_count"] = trace_shard_count;
  trace_context["trace_shard_index"] = trace_shard_index;
  trace_context["trace_sampling"] = "deterministic_task_id_modulo_shard_then_limit";
  trace_context["full_astar_used"] = false;
  trace_context["global_reservation_scan_used"] = false;
  trace_context["bag_future_path_field_present"] = false;
  trace_context["hold_attempts_are_not_training_actions"] = true;
  trace_context["runtime_bag_identity"] = "input_record_ordinal";
  trace_context["original_task_id_rewritten"] = false;
  trace_context["sensor_loss_supported"] = true;
  trace_context["enable_source_admission"] = enable_source_admission;
  trace_context["admission_mode"] = result.summary.admission_mode;
  trace_context["admission_mode_echo"] =
      result.summary.admission_mode_echo;
  trace_context["source_admission_snapshot_scope"] =
      "bounded_one_hop_target_state_or_beacon_plus_local_physical_edge";
  trace_context["first_edge_credit_claim_boundary"] =
      result.summary.first_edge_credit_claim_boundary;
  trace_context["first_edge_credit_fields"] =
      "credit_id,from,to,goal,earliest,latest,generation,expiry,capacity,"
      "owner_or_unbound,fault_generation";
  trace_context["first_edge_credit_physical_interlock_bypass"] = false;
  trace_context["first_edge_credit_future_route_count"] = 0;
  trace_context["first_edge_credit_global_scan_count"] = 0;
  trace_context["credit_validity_seconds"] = credit_validity_seconds;
  trace_context["credit_snapshot_max_age_seconds"] =
      credit_snapshot_max_age_seconds;
  trace_context["credit_capacity_per_edge"] = credit_capacity_per_edge;
  trace_context["credit_lifecycle_limit"] = credit_lifecycle_limit;
  trace_context["credit_lifecycle_storage"] =
      "active_only_ledger_plus_bounded_recent_ring_with_total_counters";
  trace_context["enable_fault_policy"] = enable_fault_policy;
  trace_context["resource_semantics_id"] =
      result.summary.resource_semantics_id;
  trace_context["resource_semantics_echo"] =
      result.summary.resource_semantics_echo;
  trace_context["entry_headway_seconds"] = entry_headway_seconds;
  trace_context["entry_headway_claim_boundary"] =
      "sensitivity_only_until_authoritative_physical_evidence";
  trace_context["pressure_mode"] = result.summary.pressure_mode;
  trace_context["pressure_mode_echo"] =
      result.summary.pressure_mode_echo;
  trace_context["pibt_mode"] = result.summary.pibt_mode;
  trace_context["pibt_mode_echo"] =
      result.summary.pibt_mode_echo;
  trace_context["scorer_mode_echo"] =
      result.summary.scorer_mode_echo;
  trace_context["framework_mode_echo"] =
      result.summary.framework_mode_echo;
  trace_context["framework_mode"] =
      result.summary.framework_mode;
  trace_context["framework_diagnostic_only"] =
      result.summary.framework_diagnostic_only;
  trace_context["priority_mode"] =
      result.summary.priority_mode;
  trace_context["priority_mode_echo"] =
      result.summary.priority_mode_echo;
  trace_context["priority_claim_boundary"] =
      result.summary.priority_claim_boundary;
  trace_context["credit_mode"] =
      result.summary.credit_mode;
  trace_context["selective_credit_contention_threshold"] =
      result.summary.selective_credit_contention_threshold;
  trace_context["pibt_preference_mode"] =
      result.summary.pibt_preference_mode;
  trace_context["pibt_preference_mode_echo"] =
      result.summary.pibt_preference_mode_echo;
  trace_context["pibt_regret_prior_record_count"] =
      result.summary.pibt_regret_prior_record_count;
  trace_context["pibt_mode_diagnostic_only"] =
      result.summary.pibt_mode_diagnostic_only;
  trace_context["pibt_max_depth"] =
      result.summary.pibt_max_depth;
  trace_context["declared_max_events"] =
      result.summary.declared_max_events;
  trace_context["local_queue_capacity"] =
      result.summary.local_queue_capacity;
  trace_context["pibt_max_ready_bags"] =
      result.summary.pibt_max_ready_bags;
  trace_context["pibt_max_local_resources"] =
      result.summary.pibt_max_local_resources;
  trace_context["pibt_max_candidates_per_bag"] =
      result.summary.pibt_max_candidates_per_bag;
  trace_context["bounded_local_pibt_claim_boundary"] =
      result.summary.bounded_local_pibt_claim_boundary;
  trace_context["bounded_local_pibt_classical_completeness_claimed"] =
      false;
  trace_context["bounded_local_pibt_transaction_credit_scope"] =
      "selected_action_credit_ids_only_bounded_by_pibt_max_ready_bags";
  trace_context["bounded_local_pibt_transaction_state_scope"] =
      "scalar_and_interval_deltas_O_selected_actions_no_full_queue_calendar_or_ledger_copy";
  trace_context["enable_pibt_lite_semantics"] =
      "same_bag_alternative_edge_scan_only";
  trace_context["bounded_local_pibt_same_bag_fallback_semantics"] =
      "root_only_safe_alternative_after_true_pibt_prepare_rejection;"
      "revalidated_by_ordinary_one_bag_dispatch;not_a_pibt_commit";
  trace_context["bounded_local_pibt_handoff_semantics"] =
      "committed_inherited_actions_only;rejected_proposal_inherited_actions_"
      "remain_only_in_bounded_local_pibt_inherited_action_count";
  trace_context["physical_fault_interlock_always_enabled"] = true;
  trace_context["fault_policy_off_semantics"] =
      "ignore_advertised_fault_and_disable_fault_driven_reroute_while_interlock_holds";
  trace_context["fault_affected_cohort_semantics"] =
      "unique_runtime_bags_with_physical_target_edge_candidate_exposure";
  trace_context["fault_target_edge_attempt_semantics"] =
      "pre_advertised-policy_argmin_targets_physically_faulted_edge";
  trace_context["fault_audit_trace_cap"] =
      "shared_trace_limit;zero_means_summary_only_no_fault_rows";
  trace_context["fault_audit_global_scan_used_for_action_selection"] = false;
  trace_context["inflight_at_fault_semantics"] =
      "grandfathered_audit_not_unsafe_entry";
  trace_context["unsafe_fault_entry_semantics"] =
      "EDGE_ENTER_after_directed_physical_fault_activation";
  const bool g4irsf14_extensions_enabled =
      result.summary.event_semantics !=
          "E0_immediate_dispatch_f2" ||
      result.summary.opportunity_telemetry_enabled;
  const bool uses_destination_merge_grants =
      result.summary.event_semantics ==
      "E4_batch_plus_destination_merge_request";
  if (g4irsf14_extensions_enabled) {
    trace_context["event_semantics"] =
        result.summary.event_semantics;
    trace_context["event_semantics_echo"] =
        result.summary.event_semantics_echo;
    trace_context["opportunity_telemetry_enabled"] =
        result.summary.opportunity_telemetry_enabled;
    trace_context["event_timestamp_grouping"] =
        "exact_double_bits_or_numeric_epsilon_1e-9";
    trace_context["local_arbitration_key"] =
        "node,timestamp_bits,wakeup_generation";
    trace_context["priority_comparison_semantics"] =
        "actual_choose_bag_comparator_invocations_escape_bypass_zero";
    trace_context["stale_arbitration_event_semantics"] =
        "valid_generation_arbitration_executed_against_stale_runtime_state";
    trace_context["superseded_arbitration_event_rejected_semantics"] =
        "generation_or_pending_mismatch_rejected_before_arbitration_execution";
    trace_context["arbitration_worklist_scope"] =
        "event_triggered_active_nodes_only_no_all_node_scan";
    trace_context["event_queue_inspection_scope"] =
        "passive_opportunity_audit_only_not_runtime_feature_or_"
        "reservation_scan";
    trace_context["destination_competitor_visibility_semantics"] =
        uses_destination_merge_grants
            ? "destination_owned_pending_current_one_hop_request_set"
            : "outgoing_edge_potential_competitor_upper_bound_not_selected_"
              "route_or_grant";
    trace_context["opportunity_trace_limit"] =
        opportunity_trace_limit;
    trace_context["artificial_batch_delay_seconds"] = 0.0;
    trace_context["destination_merge_grant_enabled"] =
        uses_destination_merge_grants;
    if (uses_destination_merge_grants) {
      trace_context["merge_grant_rule"] =
          canonical_merge_grant_rule_for_binding(merge_grant_rule);
      trace_context["merge_grant_rule_echo"] =
          merge_grant_rule;
      trace_context["merge_grant_timing_mode"] =
          result.summary.merge_grant_timing_mode;
      trace_context["merge_grant_max_pending_requests"] =
          merge_grant_max_pending_requests;
      trace_context["merge_grant_lifecycle_limit"] =
          merge_grant_lifecycle_limit;
      trace_context["merge_grant_owner"] =
          "destination_local_controller";
      trace_context["merge_grant_request_scope"] =
          "current_one_hop_exact_directed_edge_only_no_future_route";
      trace_context["merge_grant_slot_semantics"] =
          "frozen_R3_destination_node_service_exact_slot_no_future_shift";
      trace_context["merge_grant_capability_semantics"] =
          "runtime_owned_move_only_consumed_at_destination_entry";
      trace_context["merge_grant_wait_seconds_semantics"] =
          "diagnostic_subset_of_junction_queue_wait_not_additive";
      trace_context["merge_grant_lifecycle_storage"] =
          "bounded_prefix_transition_rows_with_total_stored_dropped_counters";
      trace_context["merge_grant_service_opportunity_scope"] =
          "destination_local_one_hop_pending_requests_eligible_for_exact_slot";
      trace_context["merge_grant_jit_wakeup_semantics"] =
          "one_generation_checked_coalesced_timer_per_destination_merge";
    }
  }
  if (!result.summary.g4irsf16_supervisor_mode.empty()) {
    trace_context["g4irsf16_supervisor_mode"] =
        result.summary.g4irsf16_supervisor_mode;
    trace_context["g4irsf16_policy_kind"] =
        result.summary.g4irsf16_policy_kind;
    trace_context["g4irsf16_diagnostic_only"] =
        result.summary.g4irsf16_diagnostic_only;
    trace_context["g4irsf16_promotion_authorized"] =
        result.summary.g4irsf16_promotion_authorized;
    trace_context["g4irsf16_i4_policy_id"] =
        result.summary.g4irsf16_i4_policy_id;
    trace_context["g4irsf16_model_feature_count"] =
        static_cast<int>(
            czr005::ics::kG4IRSF16DeploymentFeatureCount);
    trace_context["g4irsf16_model_feature_scope"] =
        "strict_29_id_free_no_downstream_pressure_no_physical_fault";
    trace_context["g4irsf16_physical_fault_owner"] =
        "hard_shield_and_supervisor_state_only_never_model_input";
    trace_context["g4irsf16_i4_hold_semantics"] =
        "one_natural_service_opportunity_then_same_generation_reevaluation";
    trace_context["g4irsf16_runtime_global_scan_count"] = 0;
    trace_context["g4irsf16_future_route_input_count"] = 0;
  }
  if (result.summary.g4irsf17_source_wait_telemetry_enabled) {
    trace_context["g4irsf17_source_wait_schema_id"] =
        "czr005.g4irsf17.source_wait_blocker.v1";
    trace_context["g4irsf17_source_wait_interval_semantics"] =
        "between_adjacent_real_source_admission_evaluations_or_runtime_stop";
    trace_context["g4irsf17_source_wait_additive_metrics"] =
        "wait_seconds_and_queue_weighted_wait_bag_seconds";
    trace_context["g4irsf17_source_wait_identity_semantics"] =
        "selected_bag_identity_is_trace_only_never_policy_or_model_input";
    trace_context["g4irsf17_source_wait_blocker_scope"] =
        "source_local_state_plus_sorted_outgoing_one_hop_beacons";
    trace_context["g4irsf17_source_wait_reason_precedence"] =
        "PHYSICAL_FAULT_OR_GENERATION>SUPERVISOR_HOLD>"
        "PIBT_OR_RECOVERY_TRANSACTION>DESTINATION_QUEUE_CAPACITY>"
        "DESTINATION_MERGE_TOKEN>FIRST_EDGE_CREDIT_UNAVAILABLE>"
        "SOURCE_SERVICE_NOT_READY>OTHER_EXPLICIT_REASON";
    trace_context["g4irsf17_source_wait_runtime_global_scan_count"] =
        result.summary.g4irsf17_source_wait_runtime_global_scan_count;
    trace_context["g4irsf17_source_wait_trace_limit"] =
        g4irsf17_source_wait_trace_limit;
  }
  if (!result.summary.g4irsf17_source_policy_mode.empty()) {
    trace_context["g4irsf17_source_policy_schema"] =
        czr005::ics::kG4IRSF17SourcePolicySchema;
    trace_context["g4irsf17_source_decision_schema"] =
        "czr005.g4irsf17.source_front_decision.v1";
    trace_context["g4irsf17_source_policy_mode"] =
        result.summary.g4irsf17_source_policy_mode;
    trace_context["g4irsf17_source_policy_kind"] =
        result.summary.g4irsf17_source_policy_kind;
    trace_context["g4irsf17_source_policy_artifact_set_id"] =
        result.summary.g4irsf17_source_policy_artifact_set_id;
    trace_context["g4irsf17_source_policy_top_k"] =
        result.summary.g4irsf17_source_policy_top_k;
    trace_context["g4irsf17_source_policy_candidate_scope"] =
        "baseline_winner_plus_fifo_prefix_peers_fixed_K2_or_K4_same_source";
    trace_context["g4irsf17_source_policy_context_scope"] =
        "source_local_bounded_60s_counters_plus_max_four_sorted_one_hop_"
        "TTL_beacons_and_beacon_carried_two_hop_scalar";
    trace_context["g4irsf17_source_policy_identity_semantics"] =
        "task_bag_segment_and_node_identity_are_trace_only_never_model_inputs";
    trace_context["g4irsf17_source_policy_feature_count"] =
        static_cast<int>(
            czr005::ics::kG4IRSF17SourcePairwiseFeatureCount);
    py::list feature_names;
    for (const char* name :
         czr005::ics::g4irsf17_source_pairwise_feature_names()) {
      feature_names.append(name);
    }
    trace_context["g4irsf17_source_policy_feature_names"] =
        std::move(feature_names);
    trace_context["g4irsf17_source_policy_gate_order"] =
        "explicit_artifact_authorization;runtime_supervisor;OOD;calibration;"
        "benefit_LCB;harm_UCB;utility_LCB;closed_loop_else_Q0_F2";
    trace_context["g4irsf17_source_policy_runtime_global_scan_count"] = 0;
    trace_context["g4irsf17_source_policy_future_route_input_count"] = 0;
    trace_context["g4irsf17_source_policy_future_schedule_input_count"] = 0;
    trace_context["g4irsf17_source_policy_full_astar_call_count"] = 0;
    trace_context["g4irsf17_source_policy_trace_limit"] =
        g4irsf17_source_policy_trace_limit;
  }
  if (!result.summary.g4irsf18_merge_policy_mode.empty()) {
    trace_context["g4irsf18_merge_policy_schema"] =
        result.summary.g4irsf18_merge_policy_schema;
    trace_context["g4irsf18_merge_policy_family"] =
        result.summary.g4irsf18_merge_policy_family;
    trace_context["g4irsf18_merge_feature_contract"] =
        result.summary.g4irsf18_merge_feature_contract;
    trace_context["g4irsf18_merge_policy_mode"] =
        result.summary.g4irsf18_merge_policy_mode;
    trace_context["g4irsf18_merge_score_direction"] =
        "higher_is_better";
    trace_context["g4irsf18_merge_tie_break"] =
        "fifo_only_for_finite_in_contract_equal_score";
    trace_context["g4irsf18_merge_ood_fallback"] = "J2";
    trace_context["g4irsf18_merge_starvation_guard_seconds"] = 120.0;
    trace_context["g4irsf18_merge_candidate_scope"] =
        "current_destination_local_legal_exact_slot_JIT_set_2_to_16";
    trace_context["g4irsf18_merge_authorization_order"] =
        "kill_switch;starvation_guard;artifact_contract;OOD;shadow_or_"
        "runtime_grant;finite_tie_fifo;coverage_cap;segment_override_cap";
    trace_context["g4irsf18_merge_identity_semantics"] =
        "request_bag_task_segment_identity_is_trace_only_never_model_input";
    trace_context["g4irsf18_merge_research_evidence_status"] =
        "fixed_workload_candidate_native_parity_required_not_promoted";
    trace_context["g4irsf18_merge_production_promotion_authorized"] =
        result.summary
                .g4irsf18_merge_artifact_production_closed_loop_authorized &&
        result.summary
            .g4irsf18_merge_production_closed_loop_authorized &&
        result.summary.g4irsf18_merge_offline_gate_passed;
    py::list feature_names;
    for (const char* name :
         czr005::ics::g4irsf18_merge_feature_names()) {
      feature_names.append(name);
    }
    trace_context["g4irsf18_merge_feature_names"] =
        std::move(feature_names);
    trace_context["g4irsf18_merge_runtime_global_scan_count"] = 0;
    trace_context["g4irsf18_merge_future_route_input_count"] = 0;
    trace_context["g4irsf18_merge_future_schedule_input_count"] = 0;
    trace_context["g4irsf18_merge_full_astar_call_count"] = 0;
  }

  py::dict payload;
  payload["summary"] = g4irsf11_event_runtime_summary_row(
      result.summary,
      uses_destination_merge_grants,
      merge_grant_rule,
      merge_grant_max_pending_requests,
      merge_grant_lifecycle_limit);
  payload["bags"] = g4irsf11_event_runtime_bag_rows(
      result.bags,
      uses_destination_merge_grants);
  payload["events"] = g4irsf11_event_runtime_event_rows(result.events);
  payload["decisions"] =
      g4irsf11_event_decision_rows(result.decisions, scenario, scale, false);
  payload["decision_trace"] = payload["decisions"];
  payload["hold_attempts"] =
      g4irsf11_event_decision_rows(result.hold_attempts, scenario, scale, true);
  payload["junction_state"] = g4irsf11_event_runtime_junction_rows(result.junctions);
  payload["fault_events"] = g4irsf11_event_runtime_fault_rows(result.fault_events);
  payload["credit_events"] =
      g4irsf12_event_runtime_credit_rows(result.credit_events);
  payload["pibt_events"] =
      g4irsf12_event_runtime_pibt_rows(result.pibt_events);
  if (result.summary.g4irsf17_source_wait_telemetry_enabled) {
    payload["g4irsf17_source_wait_blockers"] =
        g4irsf17_source_wait_blocker_rows(
            result.g4irsf17_source_wait_blockers);
  }
  if (!result.summary.g4irsf17_source_policy_mode.empty()) {
    payload["g4irsf17_source_policy_decisions"] =
        g4irsf17_source_policy_rows(
            result.g4irsf17_source_policy_decisions);
  }
  if (g4irsf14_extensions_enabled) {
    payload["source_admission_opportunities"] =
        g4irsf14_source_opportunity_rows(
            result.source_admission_opportunities);
    payload["junction_arbitration_opportunities"] =
        g4irsf14_junction_opportunity_rows(
            result.junction_arbitration_opportunities);
    payload["merge_request_visibility"] =
        g4irsf14_merge_visibility_rows(
            result.merge_request_visibility);
    payload["event_seq_ordering_audit"] =
        g4irsf14_event_seq_audit_rows(
            result.event_seq_ordering_audit);
    payload["arbitration_batch_cardinality"] =
        g4irsf14_arbitration_batch_rows(
            result.arbitration_batch_cardinality);
    if (uses_destination_merge_grants) {
      payload["merge_grant_lifecycle"] =
          g4irsf14_merge_grant_lifecycle_rows(
              result.merge_grant_lifecycle);
      payload["merge_service_opportunities"] =
          g4irsf18_merge_service_opportunity_rows(
              result.merge_service_opportunities);
    }
  }
  payload["trace_context"] = std::move(trace_context);
  return payload;
}

}  // namespace

PYBIND11_MODULE(czr005_cpp, module) {
  module.doc() = "Minimal czr005 C++ core bindings for Phase1D parity checks.";
  czr005::bindings::g4irsf15::register_causal_campaign_bindings(
      module);
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
  module.def("legacy_no_fault_window_summary",
             &legacy_no_fault_window_summary,
             py::arg("map_path"),
             py::arg("task_path"),
             py::arg("start_epoch") = 8260,
             py::arg("max_epochs") = 512,
             py::arg("max_new_tasks") = 128,
             py::arg("include_routes") = false,
             py::arg("fault_probability") = 0.0,
             py::arg("repair_probability") = 0.0,
             py::arg("allow_ragged_heuristic") = false);
  module.def("legacy_scheduled_fault_window_summary",
             &legacy_scheduled_fault_window_summary,
             py::arg("map_path"),
             py::arg("task_path"),
             py::arg("start_epoch") = 8260,
             py::arg("max_epochs") = 512,
             py::arg("max_new_tasks") = 128,
             py::arg("fault_schedule") = std::vector<LegacyWindowFaultEventTuple>{},
             py::arg("include_routes") = false,
             py::arg("fault_probability") = 0.0,
             py::arg("repair_probability") = 0.0,
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
  module.def("g4h_no_astar_policy_decision",
             &g4h_no_astar_policy_decision,
             py::arg("w1"),
             py::arg("b1"),
             py::arg("w2"),
             py::arg("b2"),
             py::arg("features"),
             py::arg("candidates"),
             py::arg("historical_risk"),
             py::arg("bottleneck_score"),
             py::arg("risk_margin_threshold"),
             py::arg("risk_historical_threshold"),
             py::arg("risk_bottleneck_threshold"),
             py::arg("fallback_name"),
             py::arg("static_cost"),
             py::arg("wait_seconds"),
             py::arg("pressure"),
             py::arg("progress"),
             py::arg("loop_penalty"),
             py::arg("backtrack"),
             py::arg("traffic_penalty"),
             py::arg("slack_pressure"),
             py::arg("lookahead_cost"),
             py::arg("faulted"));
  module.def("g4i_no_astar_batch_replay",
             &g4i_no_astar_batch_replay,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("window_records"),
             py::arg("route_records"),
             py::arg("w1"),
             py::arg("b1"),
             py::arg("w2"),
             py::arg("b2"),
             py::arg("risk_margin_threshold"),
             py::arg("risk_historical_threshold"),
             py::arg("risk_bottleneck_threshold"),
             py::arg("historical_risk_rules"),
             py::arg("fallback_rules"),
             py::arg("policy_name"),
             py::arg("use_model"),
             py::arg("rule_only"),
             py::arg("risk_gated_rule"),
             py::arg("fallback_name"),
             py::arg("bounded_depth") = 1,
             py::arg("max_steps") = 80,
             py::arg("trace_limit") = 500,
             py::arg("summary_only") = false,
             py::arg("profile_enabled") = false,
             py::arg("enable_edge_overlap_diagnostic") = true,
             py::arg("audit_final_conflicts") = true,
             py::arg("reservation_semantics") = std::string("baseline"));
  module.def("g4irsf4_no_astar_streaming_replay_from_jsonl",
             &g4irsf4_no_astar_streaming_replay_from_jsonl,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("task_jsonl_path"),
             py::arg("w1"),
             py::arg("b1"),
             py::arg("w2"),
             py::arg("b2"),
             py::arg("risk_margin_threshold"),
             py::arg("risk_historical_threshold"),
             py::arg("risk_bottleneck_threshold"),
             py::arg("historical_risk_rules"),
             py::arg("fallback_rules"),
             py::arg("policy_name"),
             py::arg("use_model"),
             py::arg("rule_only"),
             py::arg("risk_gated_rule"),
             py::arg("fallback_name"),
             py::arg("bounded_depth") = 1,
             py::arg("max_steps") = 80,
             py::arg("trace_limit") = 500,
             py::arg("summary_only") = true,
             py::arg("profile_enabled") = false,
             py::arg("enable_edge_overlap_diagnostic") = true,
             py::arg("audit_final_conflicts") = true,
             py::arg("fault_edges") = std::vector<std::pair<int, int>>{},
             py::arg("fault_windows") = std::vector<EdgeFaultWindowTuple>{},
             py::arg("max_tasks") = -1,
             py::arg("reservation_semantics") = std::string("baseline"));
  module.def("g4irsf11_event_runtime_from_records",
             &g4irsf11_event_runtime_from_records,
             py::arg("node_records"),
             py::arg("edge_records"),
             py::arg("heuristic_time"),
             py::arg("bag_records"),
             py::arg("fault_windows") = py::list(),
             py::arg("queue_discipline") = std::string("aging"),
             py::arg("retry_interval") = 0.25,
             py::arg("minimum_service_seconds") = 1.0e-3,
             py::arg("dispatch_headway_seconds") = 1.0e-3,
             py::arg("history_limit") = 8,
             py::arg("max_decisions_per_bag") = 512,
             py::arg("max_events") = 2000000,
             py::arg("max_simulation_time") = -1.0,
             py::arg("trace_limit") = 20000,
             py::arg("trace_shard_count") = 1,
             py::arg("trace_shard_index") = 0,
             py::arg("local_queue_capacity") = 0,
             py::arg("deadlock_retry_threshold") = 8,
             py::arg("diagnostic_hops") = 2,
             py::arg("enable_source_admission") = true,
             py::arg("enable_backpressure") = true,
             py::arg("enable_pibt_lite") = true,
             py::arg("enable_deadlock_escape") = true,
             py::arg("enable_fault_policy") = true,
             py::arg("scenario") = std::string("manual"),
             py::arg("scale") = 1.0,
             py::arg("resource_semantics") =
                 std::string("R0_current_undirected_full_travel_exclusive"),
             py::arg("entry_headway_seconds") = 1.0e-3,
             py::arg("pressure_mode") =
                 std::string("absolute_downstream_queue_penalty"),
             py::arg("pressure_weight") = 2.0,
             py::arg("pressure_age_weight") = 0.05,
             py::arg("pressure_distance_bias") = 0.25,
             py::arg("admission_mode") = std::string("legacy_unbound"),
             py::arg("credit_validity_seconds") = 1.0,
             py::arg("credit_snapshot_max_age_seconds") = 1.0,
             py::arg("credit_capacity_per_edge") = 1,
             py::arg("credit_lifecycle_limit") = 512,
             py::arg("pibt_mode") = std::string("P0"),
             py::arg("pibt_max_ready_bags") = 8,
             py::arg("pibt_max_local_resources") = 32,
             py::arg("pibt_max_candidates_per_bag") = 8,
             py::arg("scorer_mode") =
                 std::string("S0_current_handwritten_static_score"),
             py::arg("scorer_w1") =
                 std::vector<std::vector<double>>{},
             py::arg("scorer_b1") = std::vector<double>{},
             py::arg("scorer_w2") = std::vector<double>{},
             py::arg("scorer_b2") = 0.0,
             py::arg("scorer_risk_margin_threshold") = 1.0,
             py::arg("scorer_risk_bottleneck_threshold") = 5.0,
             py::arg("scorer_model_sha256") =
                 std::string(),
             py::arg("framework_mode") =
                 std::string("event_loop_one_step"),
             py::arg("event_trace_limit") = py::none(),
             py::arg("priority_mode") = std::string("Q0"),
             py::arg("pibt_preference_mode") =
                 std::string("current"),
             py::arg("pibt_regret_prior_records") =
                 std::vector<EventRuntimeRegretPriorTuple>{},
             py::arg("selective_credit_contention_threshold") =
                 1,
             py::arg("event_semantics") =
                 std::string("E0_immediate_dispatch_f2"),
             py::arg("enable_opportunity_telemetry") = false,
             py::arg("opportunity_trace_limit") = 200000,
             py::arg("merge_grant_rule") =
                 std::string("M1"),
             py::arg("merge_grant_max_pending_requests") = 64,
             py::arg("merge_grant_lifecycle_limit") = 1024,
             py::arg("g4irsf16_supervisor_mode") =
                 std::string("off"),
             py::arg("g4irsf16_i3_model_artifact") = py::dict(),
             py::arg("g4irsf16_i4_model_artifact") = py::dict(),
             py::arg("g4irsf16_rule_bundle") = py::dict(),
             py::arg("enable_g4irsf17_source_wait_telemetry") = false,
             py::arg("g4irsf17_source_wait_trace_limit") = 200000,
             py::arg("g4irsf17_source_policy_mode") =
                 std::string("off"),
             py::arg("g4irsf17_source_policy_artifact") = py::dict(),
             py::arg("g4irsf17_source_policy_trace_limit") = 200000,
             py::arg("merge_grant_timing_mode") =
                 std::string("eager"),
             py::arg("g4irsf18_merge_policy_mode") =
                 std::string("off"),
             py::arg("g4irsf18_merge_policy_artifact") = py::dict(),
             py::arg(
                 "g4irsf18_merge_research_closed_loop_authorized") = false,
             py::arg("g4irsf18_merge_fixed_research_workload") = false,
             py::arg(
                 "g4irsf18_merge_production_closed_loop_authorized") = false,
             py::arg("g4irsf18_merge_offline_gate_passed") = false,
             py::arg("g4irsf18_merge_coverage_cap") = 0.05,
             py::arg("g4irsf18_merge_max_overrides_per_segment") = 2,
             py::arg("g4irsf18_merge_kill_switch") = false,
             py::arg("bounded_wall_seconds") = -1.0,
             py::arg("bounded_check_every_events") = 65536,
             py::arg("g4irsf20_event_hotpath_policy") =
                 std::string("E0"),
             py::arg("g4irsf24_dlp_artifact") = py::dict());
  module.def(
      "g4irsf14_state_clone_noop_rerun_from_records",
      &g4irsf14_state_clone_noop_rerun_from_records,
      py::arg("node_records"),
      py::arg("edge_records"),
      py::arg("heuristic_time"),
      py::arg("bag_records"),
      py::arg("preregistered_event_ordinal"),
      py::arg("scorer_w1"),
      py::arg("scorer_b1"),
      py::arg("scorer_w2"),
      py::arg("scorer_b2"),
      py::arg("scorer_risk_margin_threshold"),
      py::arg("scorer_risk_bottleneck_threshold"),
      py::arg("scorer_model_sha256"));
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
