#pragma once

#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"

namespace czr005::ics {

struct LegacyMapReadResult {
  Graph graph;
  int declared_node_count = 0;
  int heuristic_rows = 0;
  int edge_rows = 0;
  double agv_length = 0.0;
  double safe_length = 0.0;
  double fault_threshold = 0.0;
};

inline LegacyMapReadResult read_legacy_map2(const std::string& path, double edge_speed = 2.5) {
  std::ifstream input(path);
  if (!input) {
    throw std::runtime_error("failed to open legacy map: " + path);
  }

  std::string line;
  if (!std::getline(input, line)) {
    throw std::runtime_error("empty legacy map: " + path);
  }

  LegacyMapReadResult result;
  {
    std::istringstream header(line);
    header >> result.declared_node_count >> result.agv_length >> result.safe_length >>
        result.fault_threshold;
    if (!header) {
      throw std::runtime_error("invalid legacy map header");
    }
  }

  for (int row = 0; row < result.declared_node_count; ++row) {
    if (!std::getline(input, line)) {
      throw std::runtime_error("unexpected EOF while reading nodes");
    }
    std::istringstream stream(line);
    Node node;
    stream >> node.location >> node.node_type >> node.service_time >> node.y >> node.x;
    if (!stream) {
      throw std::runtime_error("invalid node row");
    }
    int outgoing = -1;
    while (stream >> outgoing) {
      node.outgoing.push_back(outgoing);
    }
    result.graph.add_node(std::move(node));
  }

  std::vector<std::vector<double>> heuristic;
  heuristic.reserve(static_cast<std::size_t>(result.declared_node_count));
  for (int row = 0; row < result.declared_node_count; ++row) {
    if (!std::getline(input, line)) {
      throw std::runtime_error("unexpected EOF while reading heuristic rows");
    }
    std::istringstream stream(line);
    std::vector<double> values;
    values.reserve(static_cast<std::size_t>(result.declared_node_count));
    double value = 0.0;
    while (stream >> value) {
      values.push_back(value / edge_speed);
    }
    if (static_cast<int>(values.size()) != result.declared_node_count) {
      throw std::runtime_error("invalid heuristic row width");
    }
    heuristic.push_back(std::move(values));
    ++result.heuristic_rows;
  }
  result.graph.set_heuristic(std::move(heuristic));

  while (std::getline(input, line)) {
    if (line.empty()) {
      continue;
    }
    std::istringstream stream(line);
    int start = -1;
    int end = -1;
    double length = 0.0;
    stream >> start >> end >> length;
    if (!stream) {
      throw std::runtime_error("invalid edge row");
    }
    result.graph.add_edge(Edge{start, end, length, edge_speed});
    ++result.edge_rows;
  }

  return result;
}

}  // namespace czr005::ics
