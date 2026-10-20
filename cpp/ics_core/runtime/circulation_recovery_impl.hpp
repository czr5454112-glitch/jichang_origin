#pragma once

namespace czr005::ics {

inline void EventDrivenJunctionRuntime::circulation_remove_failed_from_queues(int id, double time) {
  // An asynchronous terminal dequeue is itself an arbitration trigger. The
  // successor has never necessarily been selected, so it may have no resource
  // subscription to wake when a downstream berth later becomes free.
  for (auto& pair : junctions_) {
    const int node = pair.first;
    auto& controller = pair.second;
    const auto q_before = controller.queue.size(), s_before = controller.source_queue.size();
    auto& q = controller.queue;
    auto& sq = controller.source_queue;
    q.erase(std::remove(q.begin(), q.end(), id), q.end());
    sq.erase(std::remove(sq.begin(), sq.end(), id), sq.end());
    const bool junction_changed = q.size() != q_before, source_changed = sq.size() != s_before;
    if (!junction_changed && !source_changed) continue;
    if (junction_changed && uses_destination_merge_grants())
      ++destination_merge_bag_state(id).junction_queue_generation;
    if (controller.escape_token_task == id) controller.escape_token_task = -1;
    if (controller.source_natural_hold_runtime_bag_id == id) {
      controller.source_natural_hold_runtime_bag_id = -1;
      controller.source_natural_hold_until = 0.;
    }
    controller.observe_local_state();
    schedule_passive(JunctionEventType::kLocalQueueUpdate, time, id, node, node, -1,
                     "expired_empty_terminal_dequeue");
    const auto& local = g4irsf14_local_state(node);
    if (junction_changed && !q.empty()) {
      double ready = time;
      if (local.has_last_junction_arbitration &&
          event_runtime_detail::same_timestamp(local.last_junction_arbitration_time, time))
        ready += std::max(config_.minimum_service_seconds, config_.dispatch_headway_seconds);
      schedule_junction_wakeup(node, ready);
    }
    if (source_changed && !sq.empty()) {
      double ready = time;
      if (local.has_last_source_arbitration &&
          event_runtime_detail::same_timestamp(local.last_source_arbitration_time, time))
        ready += std::max(config_.minimum_service_seconds, config_.dispatch_headway_seconds);
      schedule_source_wakeup(node, ready);
    }
    circulation_receipt(time, "TERMINAL_DEQUEUE_REARBITRATION", circulation_.legs.at(id).tray,
                        id, node, -1, "departure_lease_expired_before_physical_entry");
  }
}

inline std::string EventDrivenJunctionRuntime::circulation_recover_failed_empty(
    const CirculationProtocolCommandInput& input, double time) {
  auto found = std::find_if(circulation_.trays.begin(), circulation_.trays.end(),
                           [&](const auto& tray) { return tray.tray_id == input.tray_id; });
  std::string reason;
  if (time >= input.expiry) reason = "recovery_expired";
  else if (found == circulation_.trays.end()) reason = "unknown_recovery_tray";
  else if (circulation_.owner(found->node) != input.owner) reason = "resource_owner_mismatch";
  else if (found->node != input.from) reason = "recovery_node_mismatch";
  else if (found->generation != input.expected_generation) reason = "stale_recovery_generation";
  else if (found->job >= 0) reason = "loaded_recovery_not_allowed";
  else if (found->edge_to >= 0 || found->edge_from >= 0 || found->reception_node >= 0)
    reason = "inflight_or_receiving_obligation";
  else if (found->mode != "quarantined") reason = "not_quarantined";
  else if (found->active_leg < 0 || found->transfer < 0) reason = "missing_failed_empty_binding";
  else {
    const auto& leg = circulation_.legs.at(found->active_leg);
    const auto& failed = circulation_.transfers.at(found->transfer);
    const auto& request = circulation_.input.transfers.at(found->transfer);
    if (leg.transport_leg_id != input.reference_request_id || request.request_id != input.reference_id ||
        leg.tray != static_cast<int>(found - circulation_.trays.begin()) || leg.job >= 0)
      reason = "failed_empty_binding_mismatch";
    else if (failed.status != "failed" || bags_.at(found->active_leg).status != BagStatus::kFailed ||
             failed.reason != "departure_lease_expired_before_physical_entry")
      reason = "failure_not_recoverable";
    else if (failed.departed_at >= 0 || failed.received_at >= 0 || request.source != found->node)
      reason = "prior_physical_entry_or_node_mismatch";
    else {
      // No outstanding transport may be silently superseded by this recovery.
      for (std::size_t i = 0; i < circulation_.transfers.size(); ++i) {
        const auto& other = circulation_.transfers[i];
        if (static_cast<int>(i) != found->transfer && other.tray == failed.tray &&
            (other.status == "dispatching" || other.status == "departed"))
          reason = "other_transport_obligation";
      }
      for (const auto& other : circulation_.legs)
        if (other.tray == failed.tray && other.runtime_id != found->active_leg &&
            bags_.at(other.runtime_id).status != BagStatus::kCompleted &&
            bags_.at(other.runtime_id).status != BagStatus::kFailed)
          reason = "other_transport_obligation";
      for (const auto& pair : junctions_)
        if (std::find(pair.second.queue.begin(), pair.second.queue.end(), found->active_leg) != pair.second.queue.end() ||
            std::find(pair.second.source_queue.begin(), pair.second.source_queue.end(), found->active_leg) != pair.second.source_queue.end())
          reason = "failed_leg_still_queued";
    }
  }
  const int tray_index = found == circulation_.trays.end() ? -1 : static_cast<int>(found - circulation_.trays.begin());
  const int leg_index = tray_index < 0 ? -1 : found->active_leg;
  if (reason.empty()) {
    circulation_forget_resource_wait(leg_index);
    found->active_leg = -1; found->transfer = -1; found->mode = "empty";
    found->available_at = time; ++found->generation;
    circulation_receipt(time, "EMPTY_RECOVERY_GRANTED", tray_index, leg_index, input.from, input.from,
                        input.request_id + ":owner_failed_empty_recovery");
    circulation_.notify_node(input.from, time, 1);
    circulation_progress(time);
    return "recovered";
  }
  circulation_receipt(time, "RECOVERY_REJECTED", tray_index, leg_index, input.from, input.from,
                      input.request_id + ":" + reason);
  return "rejected:" + reason;
}

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
