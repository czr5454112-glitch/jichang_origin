#pragma once

namespace czr005::ics {

inline void EventDrivenJunctionRuntime::circulation_forget_resource_wait(int id) {
  const auto found = circulation_.resource_waits.find(id);
  if (found == circulation_.resource_waits.end()) return;
  const auto remove = [id](auto& index, const std::vector<int>& resources) {
    for (const int resource : resources) {
      const auto it = index.find(resource);
      if (it == index.end()) continue;
      it->second.erase(id);
      if (it->second.empty()) index.erase(it);
    }
  };
  remove(circulation_.edge_waiters, found->second.edge_indices);
  remove(circulation_.receiving_waiters, found->second.receiving_nodes);
  remove(circulation_.ranking_waiters, found->second.ranking_nodes);
  circulation_.resource_waits.erase(found);
}

inline bool EventDrivenJunctionRuntime::circulation_wait_for_resources(
    int id, int node, double time, const EventDecisionTraceRow* trace,
    int preferred) {
  if (!circulation_.enabled || id < 0 || id >= static_cast<int>(circulation_.legs.size())) return false;
  circulation_forget_resource_wait(id);
  const auto bag = bags_.find(id);
  if (bag == bags_.end()) return false;
  const auto& tray = circulation_.trays[circulation_.legs[id].tray];
  if (tray.active_leg != id || tray.edge_to >= 0 || tray.node != node) return false;
  CirculationResourceWait wait;
  wait.runtime_id = id; wait.node = node;
  double headway_ready = std::numeric_limits<double>::infinity();
  bool has_static_suffix = false;
  // Frozen S3/S4 without same-bag handoff may deliberately wait for its first
  // candidate even when another physical route is free. Only park that policy
  // when its time-dependent score terms have settled. Otherwise preserve the
  // native calendar retry: predicting a score crossing needs a separate proof.
  bool preferred_only = trace != nullptr && trace->candidates.size() > 1 &&
      preferred >= 0 && !config_.enable_pibt_lite;
  if (preferred_only) {
    bool preferred_resource_blocked = false;
    for (const auto& candidate : trace->candidates) {
      if (candidate.corridor_next_available > time + event_runtime_detail::kEpsilon ||
          candidate.target_next_available > time + candidate.travel_time + event_runtime_detail::kEpsilon)
        preferred_only = false;
      if (candidate.next_node == preferred)
        preferred_resource_blocked = candidate.shield_reason == "circulation:entry_headway" ||
            candidate.shield_reason == "circulation:edge_capacity" ||
            candidate.shield_reason == "circulation:receiving_full";
    }
    preferred_only = preferred_only && preferred_resource_blocked;
  }
  if (preferred_only)
    for (const auto& candidate : trace->candidates) wait.ranking_nodes.push_back(candidate.next_node);
  for (const int target : graph_.outgoing(node)) {
    if (preferred_only && target != preferred) continue;
    const int edge = circulation_.edge_index(node, target);
    if (edge < 0 || circulation_.input.edges[edge].capacity == 0 ||
        !circulation_static_reachable(target, bag->second.request.goal)) continue;
    has_static_suffix = true;
    const auto reason = circulation_.can_enter(id, node, target, time);
    if (reason == "circulation:entry_headway") {
      wait.edge_indices.push_back(edge);
      headway_ready = std::min(headway_ready, circulation_.next_entry[edge]);
    } else if (reason == "circulation:edge_capacity") {
      wait.edge_indices.push_back(edge);
    } else if (reason == "circulation:receiving_full") {
      wait.receiving_nodes.push_back(target);
    } else {
      // Some candidate is physically available, or a different native/owner
      // contract is responsible. Keep mature scheduling for that situation.
      return false;
    }
  }
  wait.static_blocked = !has_static_suffix;
  wait.generation = circulation_.next_resource_wait_generation++;
  const auto generation = wait.generation;
  for (const int edge : wait.edge_indices)
    circulation_.edge_waiters[edge][id] = generation;
  for (const int destination : wait.receiving_nodes)
    circulation_.receiving_waiters[destination][id] = generation;
  for (const int destination : wait.ranking_nodes)
    circulation_.ranking_waiters[destination][id] = generation;
  circulation_.resource_waits.emplace(id, std::move(wait));
  circulation_receipt(time, "RESOURCE_WAIT", circulation_.legs[id].tray,
      id, node, -1, has_static_suffix ? "committed_resource_change_required" : "no_static_legal_suffix");
  if (std::isfinite(headway_ready))
    circulation_schedule("resource_headway_ready", headway_ready, id, generation);
  return true;
}

inline void EventDrivenJunctionRuntime::circulation_notify_ranking_state(int node, double time) {
  if (!circulation_.enabled) return;
  const auto found = circulation_.ranking_waiters.find(node);
  if (found == circulation_.ranking_waiters.end()) return;
  const auto affected = found->second;
  for (const auto& waiter : affected)
    circulation_wake_resource_wait(waiter.first, waiter.second, time,
                                    "candidate_score_state_changed");
}

inline void EventDrivenJunctionRuntime::circulation_wake_resource_wait(
    int id, std::uint64_t generation, double time, const std::string& reason) {
  const auto found = circulation_.resource_waits.find(id);
  if (found == circulation_.resource_waits.end() || found->second.generation != generation) return;
  const int node = found->second.node;
  circulation_forget_resource_wait(id);
  if (id < 0 || id >= static_cast<int>(circulation_.legs.size())) return;
  const auto& tray = circulation_.trays[circulation_.legs[id].tray];
  if (tray.active_leg != id || tray.node != node || tray.edge_to >= 0 || tray.mode == "quarantined") return;
  double ready = time;
  const auto& local = g4irsf14_local_state(node);
  if (local.has_last_junction_arbitration &&
      event_runtime_detail::same_timestamp(local.last_junction_arbitration_time, time)) {
    // Native E4 deliberately permits one arbitration per node/timestamp. A
    // resource freed after that boundary receives one dispatch quantum, not
    // an epsilon capacity loophole or a periodic resource poll.
    ready += std::max(config_.minimum_service_seconds, config_.dispatch_headway_seconds);
  }
  circulation_receipt(time, "RESOURCE_WAKE", circulation_.legs[id].tray,
                      id, node, -1, reason);
  schedule_junction_wakeup(node, ready);
}

inline void EventDrivenJunctionRuntime::circulation_notify_resource(
    bool receiving, int resource, double time, const std::string& reason) {
  if (!circulation_.enabled) return;
  const auto& index = receiving ? circulation_.receiving_waiters : circulation_.edge_waiters;
  const auto found = index.find(resource);
  if (found == index.end()) return;
  // Copy only the affected dependency list: wake removes entries in both
  // reverse indexes and invalidates old headway events by generation.
  const auto affected = found->second;
  for (const auto& waiter : affected)
    circulation_wake_resource_wait(waiter.first, waiter.second, time, reason);
}

} // namespace czr005::ics
