#include <map>
#include <string>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "ics_core/io/legacy_map_reader.hpp"
#include "ics_core/io/legacy_task_reader.hpp"
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

}  // namespace

PYBIND11_MODULE(czr005_cpp, module) {
  module.doc() = "Minimal czr005 C++ core bindings for Phase1D parity checks.";
  module.def("read_legacy_map_summary", &read_legacy_map_summary, py::arg("path"));
  module.def("read_legacy_task_summary", &read_legacy_task_summary, py::arg("path"));
  module.def("plan_legacy_map_path",
             &plan_legacy_map_path,
             py::arg("map_path"),
             py::arg("start"),
             py::arg("goal"));
}
