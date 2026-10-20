#pragma once

#include <functional>
#include <limits>
#include <queue>
#include <utility>
#include "ics_core/graph/graph.hpp"
#include "ics_core/runtime/circulation.hpp"

namespace czr005::ics {

// The static physical contract may close an existing directed edge without
// deleting/changing the source topology. All circulation algorithms use this
// same known domain. Dynamic faults, future arrivals and reservations are not
// consulted; this is topology preprocessing, never a clairvoyant rollout.
inline void initialize_circulation_static_domain(
    CirculationState& state, const Graph& graph, double minimum_service) {
  const bool closed = std::any_of(state.input.edges.begin(), state.input.edges.end(),
                                 [](const auto& edge) { return edge.capacity == 0; }) ||
      std::any_of(state.input.nodes.begin(),state.input.nodes.end(),
                  [](const auto& node) { return node.capacity == 0; });
  if (closed) state.static_domain_version = "capacity_positive_service_potential.v1";
  const auto count = graph.node_count();
  std::vector<std::vector<std::pair<int,double>>> incoming(count);
  double unreachable = 1.0;
  for (int node : graph.node_locations())
    unreachable += std::max(graph.service_time(node), minimum_service);
  for (const auto& edge : state.input.edges) {
    if (edge.capacity == 0 || state.node_contract(edge.from).capacity == 0 ||
        state.node_contract(edge.to).capacity == 0) continue;
    const double travel=std::max(graph.edge(edge.from,edge.to).travel_time(),minimum_service);
    incoming[edge.to].push_back({edge.from,travel}); unreachable += travel;
  }
  if (!std::isfinite(unreachable))
    throw std::invalid_argument("circulation:nonfinite_static_domain_bound");
  for (auto& predecessors : incoming) std::sort(predecessors.begin(),predecessors.end());
  if(closed) state.static_route_potential.assign(count,std::vector<double>(count,unreachable));
  state.static_route_reachable.assign(count,std::vector<bool>(count,false));
  for (std::size_t goal=0; goal<count; ++goal) {
    using Entry=std::pair<double,int>;
    std::priority_queue<Entry,std::vector<Entry>,std::greater<Entry>> pending;
    std::vector<double> distance(count,std::numeric_limits<double>::infinity());
    distance[goal]=0; pending.push({0,static_cast<int>(goal)});
    while(!pending.empty()) {
      const auto [cost,node]=pending.top(); pending.pop();
      if(cost>distance[node]) continue;
      for(const auto& [previous,travel]:incoming[node]) {
        const double next=cost+travel+std::max(graph.service_time(previous),minimum_service);
        if(next<distance[previous]) { distance[previous]=next; pending.push({next,previous}); }
      }
    }
    for(std::size_t from=0;from<count;++from) {
      state.static_route_reachable[from][goal]=std::isfinite(distance[from]);
      if(closed && state.static_route_reachable[from][goal])
        state.static_route_potential[from][goal]=distance[from];
    }
  }
}

} // namespace czr005::ics
