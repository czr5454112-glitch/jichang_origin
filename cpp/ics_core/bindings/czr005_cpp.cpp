#include <chrono>
#include <map>
#include <string>
#include <utility>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "ics_core/io/legacy_map_reader.hpp"
#include "ics_core/io/legacy_task_reader.hpp"
#include "ics_core/models/edge_score.hpp"
#include "ics_core/models/edge_score_io.hpp"
#include "ics_core/routing/astar.hpp"

namespace py = pybind11;

namespace {

std::vector<int> route_locations(const std::vector<czr005::ics::PathNode>& route) {
  std::vector<int> locations;
  locations.reserve(route.size());
  for (const auto& node : route) {
    locations.push_back(node.location);
  }
  return locations;
}

py::dict read_legacy_map_summary(const std::string& path) {
  const auto legacy = czr005::ics::read_legacy_map2(path);
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

std::vector<int> plan_legacy_map_path(const std::string& map_path, int start, int goal) {
  const auto legacy = czr005::ics::read_legacy_map2(map_path);
  const czr005::ics::AStarPlanner planner(legacy.graph);
  return route_locations(planner.plan(start, goal));
}

std::vector<std::vector<int>> plan_legacy_map_paths(
    const std::string& map_path,
    const std::vector<std::pair<int, int>>& cases) {
  const auto legacy = czr005::ics::read_legacy_map2(map_path);
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
                                    int repeats) {
  const auto legacy = czr005::ics::read_legacy_map2(map_path);
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
      .def_property_readonly("feature_dim", &czr005::ics::EdgeScoreModel::feature_dim)
      .def_property_readonly("hidden_dim", &czr005::ics::EdgeScoreModel::hidden_dim);

  module.def("read_legacy_map_summary", &read_legacy_map_summary, py::arg("path"));
  module.def("read_legacy_task_summary", &read_legacy_task_summary, py::arg("path"));
  module.def("plan_legacy_map_path",
             &plan_legacy_map_path,
             py::arg("map_path"),
             py::arg("start"),
             py::arg("goal"));
  module.def("plan_legacy_map_paths",
             &plan_legacy_map_paths,
             py::arg("map_path"),
             py::arg("cases"));
  module.def("benchmark_legacy_map_paths",
             &benchmark_legacy_map_paths,
             py::arg("map_path"),
             py::arg("cases"),
             py::arg("repeats") = 100);
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
}
