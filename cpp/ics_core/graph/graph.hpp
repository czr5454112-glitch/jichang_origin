#pragma once

#include <algorithm>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

namespace czr005::ics {

struct Node {
  int location = -1;
  int node_type = 0;
  double service_time = 0.0;
  int x = 0;
  int y = 0;
  std::vector<int> outgoing;
};

struct Edge {
  int start = -1;
  int end = -1;
  double length = 0.0;
  double speed = 2.5;

  [[nodiscard]] double travel_time() const { return length / speed; }
};

class Graph {
 public:
  void add_node(Node node) { nodes_.emplace(node.location, std::move(node)); }

  void add_edge(Edge edge) {
    const auto key = edge_key(edge.start, edge.end);
    edges_.emplace(key, edge);
    auto& outgoing = node(edge.start).outgoing;
    if (std::find(outgoing.begin(), outgoing.end(), edge.end) == outgoing.end()) {
      outgoing.push_back(edge.end);
    }
  }

  void set_heuristic(std::vector<std::vector<double>> heuristic) {
    heuristic_ = std::move(heuristic);
  }

  [[nodiscard]] const Node& node(int location) const {
    const auto found = nodes_.find(location);
    if (found == nodes_.end()) {
      throw std::out_of_range("unknown node");
    }
    return found->second;
  }

  [[nodiscard]] Node& node(int location) {
    const auto found = nodes_.find(location);
    if (found == nodes_.end()) {
      throw std::out_of_range("unknown node");
    }
    return found->second;
  }

  [[nodiscard]] const Edge& edge(int start, int end) const {
    const auto found = edges_.find(edge_key(start, end));
    if (found == edges_.end()) {
      throw std::out_of_range("unknown edge");
    }
    return found->second;
  }

  [[nodiscard]] bool has_edge(int start, int end) const {
    return edges_.find(edge_key(start, end)) != edges_.end();
  }

  [[nodiscard]] const std::vector<int>& outgoing(int location) const {
    return node(location).outgoing;
  }

  [[nodiscard]] double service_time(int location) const {
    return node(location).service_time;
  }

  [[nodiscard]] double heuristic(int start, int goal) const {
    return heuristic_.at(static_cast<std::size_t>(start)).at(static_cast<std::size_t>(goal));
  }

  [[nodiscard]] std::size_t node_count() const { return nodes_.size(); }
  [[nodiscard]] std::size_t edge_count() const { return edges_.size(); }

  [[nodiscard]] int node_type_count(int node_type) const {
    int count = 0;
    for (const auto& entry : nodes_) {
      if (entry.second.node_type == node_type) {
        ++count;
      }
    }
    return count;
  }

 private:
  static long long edge_key(int start, int end) {
    return (static_cast<long long>(start) << 32) ^ static_cast<unsigned int>(end);
  }

  std::unordered_map<int, Node> nodes_;
  std::unordered_map<long long, Edge> edges_;
  std::vector<std::vector<double>> heuristic_;
};

}  // namespace czr005::ics
