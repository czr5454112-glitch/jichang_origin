#pragma once

#include "ics_core/runtime/circulation.hpp"

namespace czr005::ics {

// Capture-body digest excludes delivery bookkeeping and its own digest field.
// The exact same typed serializer seals the body in a native checkpoint.
template <typename Writer>
void fingerprint_planning_capture(Writer& w,const CirculationPlanningSnapshot& m) {
  w.string("g31.planning_capture.v1");
  w.string(m.message_id);w.string(m.source_owner);w.string(m.target_owner);
  w.u64(m.publication_sequence);w.floating(m.captured_at);w.floating(m.valid_until);
  w.string(m.static_contract_sha256);w.string(m.queue_discipline);w.string(m.resource_semantics);
  w.string(m.event_semantics);w.string(m.scorer_mode);w.string(m.merge_grant_rule);
  w.string(m.merge_grant_timing_mode);w.floating(m.minimum_service_seconds);
  w.u64(m.jobs.size());for(const auto& row:m.jobs) {
    const auto& j=row.contract;
    w.string(j.business_bag_id);w.i64(j.origin);w.i64(j.destination);w.floating(j.arrival);w.floating(j.deadline);
    w.i64(j.storage_node);w.floating(j.storage_release_at);w.floating(j.storage_min_dwell);
    w.floating(j.load_seconds);w.floating(j.unload_seconds);w.floating(j.hold_seconds);
    w.boolean(j.protected_service);w.boolean(j.allow_suffix_reroute);w.string(row.status);
    w.floating(row.loaded_at);w.floating(row.storage_entered_at);w.floating(row.storage_released_at);
  }
  w.u64(m.trays.size());for(const auto& t:m.trays) {
    w.string(t.tray_id);w.string(t.business_bag_id);w.string(t.mode);w.string(t.ready_kind);
    w.i64(t.node);w.i64(t.edge_from);w.i64(t.edge_to);w.i64(t.reception_node);
    w.u64(t.generation);w.u64(t.traversal_id);w.floating(t.available_at);w.floating(t.service_ready_at);
    w.floating(t.load_complete_at);w.boolean(t.service_ready_known);
    w.u64(t.committed_prefix.size());for(int node:t.committed_prefix) w.i64(node);
  }
  w.u64(m.nodes.size());for(const auto& n:m.nodes) {
    w.i64(n.node);w.i64(n.occupancy);w.i64(n.actual_available);w.i64(n.unrepresented_occupancy);
  }
  w.u64(m.known_faults.size());for(const auto& f:m.known_faults) {
    w.i64(f.from);w.i64(f.to);w.boolean(f.active);w.floating(f.received_at);
  }
  // Bind the derived coverage fields rendered to the receiver as well.
  w.string("source_waiting_or_locally_carried_released_jobs_and_local_trays");w.boolean(true);
  w.u64(m.nodes.size());int unrepresented=0;
  for(const auto& n:m.nodes) {w.i64(n.node);unrepresented+=n.unrepresented_occupancy;}
  w.u64(m.trays.size());for(const auto& t:m.trays) w.string(t.tray_id);
  w.u64(m.jobs.size());for(const auto& j:m.jobs) w.string(j.contract.business_bag_id);
  w.i64(unrepresented);w.boolean(false);
}

// V2 deliberately nests the exact v1 local-capture serializer. No v1-only
// session or capture gains an extra byte from this opt-in extension.
template <typename Writer>
void fingerprint_planning_capture_v2(Writer& w,const CirculationPlanningSnapshotV2& m) {
  w.string("g31.planning_capture.v2");fingerprint_planning_capture(w,m);
  w.string("g31.planning_extension.v2");w.string(m.source_owner);w.floating(m.captured_at);
  w.u64(m.terminal_receipts.size());for(const auto& r:m.terminal_receipts) {
    w.string(r.receipt_id);w.u64(r.source_local_sequence);w.string(r.source_owner);
    w.string("UNLOAD_COMPLETE");w.string("completed");w.string(r.business_bag_id);
    w.i64(r.destination);w.string(r.tray_id);w.floating(r.completed_at);
  }
  w.string("all_source_owned_destination_unload_completions_through_capture");w.boolean(true);
  w.floating(m.captured_at);w.u64(m.nodes.size());for(const auto& n:m.nodes) w.i64(n.node);
  w.boolean(false);w.u64(m.terminal_receipts.size());
  for(const auto& r:m.terminal_receipts) w.string(r.business_bag_id);
  w.u64(m.submitted_physical_actions.size());for(const auto& a:m.submitted_physical_actions) {
    w.string(a.request_id);w.string(a.kind);w.string(a.source_owner);w.boolean(a.has_delivered_ack);
    if(a.has_delivered_ack) {w.u64(a.ack_sequence);w.floating(a.ack_delivered_at);w.string(a.ack_status);}
  }
  w.string("all_source_submitted_physical_operations_last_delivered_ack");w.floating(m.captured_at);
  w.boolean(true);w.boolean(false);w.boolean(false);
  w.u64(m.submitted_physical_actions.size());std::size_t unresolved=0;
  for(const auto& a:m.submitted_physical_actions) {w.string(a.request_id);unresolved+=!a.terminal;}
  w.u64(unresolved);for(const auto& a:m.submitted_physical_actions) if(!a.terminal) w.string(a.request_id);
}

// V3 binds the COMPUTED unchanged v2 typed digest string, not inline v2 bytes
// or a caller-supplied cached digest. Recompute from the immutable base body
// whenever sealing, so the complete nested state is bound as well.
template <typename Writer>
void fingerprint_planning_capture_v3(Writer& w,const CirculationPlanningSnapshotV3& m) {
  w.string("g31.planning_capture.v3");
  Writer nested("g31.planning_capture_digest.v2");fingerprint_planning_capture_v2(nested,m);
  w.string("nested_unchanged_v2_typed_digest");w.string(nested.sha256());
  w.string("g31.planning_inflight_receipts.v1");w.string(m.source_owner);w.floating(m.captured_at);
  w.u64(m.source_observed_inflight.size());
  for(const auto& row:m.source_observed_inflight) {
    w.string(row.source_owner);w.string("EDGE_ENTER");w.string(row.tray_id);w.string(row.business_bag_id);
    w.u64(row.generation);w.u64(row.traversal_id);w.i64(row.edge_from);w.i64(row.edge_to);
    w.floating(row.entered_at);w.floating(row.static_edge_travel_seconds);w.floating(row.derived_edge_exit_at);
  }
  w.string("all_current_source_owned_committed_edges_with_matching_observed_entries");w.floating(m.captured_at);
  w.boolean(m.unmatched_inflight_tray_ids.empty());w.boolean(false);
  std::size_t committed=0;for(const auto& tray:m.trays) committed+=tray.edge_to>=0;
  w.u64(committed);for(const auto& tray:m.trays) if(tray.edge_to>=0) w.string(tray.tray_id);
  w.u64(m.unmatched_inflight_tray_ids.size());for(const auto& id:m.unmatched_inflight_tray_ids) w.string(id);
}

// Versioned, deterministic in-process inventory. This is not a deserialize
// interface: only immutable StateCheckpoint objects minted by the runtime may
// restore capabilities. Future environment entries belong in this seal, never
// in an online owner's observation or learned feature vector.
template <typename Writer>
void fingerprint_circulation_state(Writer& w, const CirculationState& s) {
  w.string("czr005.circulation.in_process_checkpoint.v1");
  w.boolean(s.enabled);
  w.u64(s.input.nodes.size());
  for (const auto& n : s.input.nodes) {
    w.i64(n.node); w.string(n.zone); w.i64(n.capacity);
    w.i64(n.export_min_stock); w.boolean(n.allow_export); w.boolean(n.allow_receive);
    w.string(n.control_partition); w.string(n.resource_owner);
  }
  const auto receiving_policy_count=std::count_if(s.input.nodes.begin(),s.input.nodes.end(),
      [](const auto& n){return n.empty_receive_transit_reserve != 0;});
  if(receiving_policy_count) {
    // Omitted/default-zero policy contributes no byte to the old state seal.
    w.string("g31.receiver_empty_transit_admission.v1");w.u64(receiving_policy_count);
    for(const auto& n:s.input.nodes) if(n.empty_receive_transit_reserve != 0) {
      w.i64(n.node);w.i64(n.empty_receive_transit_reserve);
    }
  }
  w.u64(s.input.edges.size());
  for (const auto& e : s.input.edges) {
    w.i64(e.from); w.i64(e.to); w.i64(e.capacity); w.floating(e.entry_headway);
  }
  w.u64(s.input.trays.size());
  for (const auto& t : s.input.trays) { w.string(t.tray_id); w.i64(t.node); }
  w.u64(s.input.jobs.size());
  for (const auto& j : s.input.jobs) {
    w.string(j.business_bag_id); w.i64(j.origin); w.i64(j.destination);
    w.floating(j.arrival); w.floating(j.deadline); w.i64(j.storage_node);
    w.floating(j.storage_release_at); w.floating(j.storage_min_dwell);
    w.floating(j.load_seconds); w.floating(j.unload_seconds); w.floating(j.hold_seconds);
    w.boolean(j.protected_service); w.boolean(j.allow_suffix_reroute);
  }
  w.u64(s.input.transfers.size());
  for (const auto& t : s.input.transfers) {
    w.string(t.request_id); w.string(t.tray_id); w.i64(t.source); w.i64(t.destination);
    w.floating(t.issued_at); w.floating(t.message_delay); w.floating(t.earliest_departure);
    w.floating(t.expiry);
  }
  // Opt-in versioned extension: old default-only checkpoints retain their seal.
  // StateCheckpoint copies the typed input, so restore never reparses or drops it.
  const auto scope_count=std::count_if(s.input.transfers.begin(),s.input.transfers.end(),
      [](const auto& t){return t.transfer_scope!="cross_zone_transfer";});
  if(!s.input.static_role_contract.schema.empty() || scope_count) {
    w.string("g31.local_empty_return_checkpoint.v1");
    w.string(s.input.static_role_contract.schema);
    w.u64(s.input.static_role_contract.loader_nodes.size());
    for(int node:s.input.static_role_contract.loader_nodes) w.i64(node);
    w.u64(scope_count);
    for(const auto& t:s.input.transfers) if(t.transfer_scope!="cross_zone_transfer") {
      w.string(t.request_id);w.string(t.transfer_scope);
    }
  }
  w.u64(s.trays.size());
  for (const auto& t : s.trays) {
    w.string(t.tray_id); w.i64(t.node); w.string(t.mode); w.i64(t.job);
    w.i64(t.active_leg); w.i64(t.edge_from); w.i64(t.edge_to); w.i64(t.reception_node);
    w.i64(t.transfer); w.floating(t.available_at); w.floating(t.storage_arrived_at);
    w.u64(t.generation); w.u64(t.traversal_id); w.u64(t.public_traversal_version); w.boolean(t.edge_entry_observed);
  }
  w.u64(s.jobs.size());
  for (const auto& j : s.jobs) {
    w.string(j.status); w.i64(j.tray); w.floating(j.loaded_at);
    w.floating(j.storage_entered_at); w.floating(j.storage_released_at);
    w.floating(j.completed_at); w.boolean(j.deadline_met);
  }
  w.u64(s.transfers.size());
  for (const auto& t : s.transfers) {
    w.string(t.status); w.string(t.reason); w.i64(t.tray);
    w.floating(t.delivered_at); w.floating(t.departed_at); w.floating(t.received_at);
  }
  w.u64(s.legs.size());
  for (const auto& l : s.legs) {
    w.i64(l.runtime_id); w.string(l.transport_leg_id); w.i64(l.tray);
    w.i64(l.job); w.string(l.kind);
  }
  w.u64(s.receipts.size());
  for (const auto& r : s.receipts) {
    w.floating(r.time); w.string(r.event); w.string(r.business_bag_id);
    w.string(r.transport_leg_id); w.string(r.tray_id); w.u64(r.traversal_id);
    w.i64(r.node); w.i64(r.from); w.i64(r.to); w.string(r.reason);
  }
  w.u64(s.next_entry.size());
  for (double t : s.next_entry) w.floating(t);
  w.u64(s.next_traversal);
  w.u64(s.route_intents.size());
  for (const auto& r : s.route_intents) {
    w.string(r.request_id); w.string(r.owner_id); w.string(r.business_bag_id); w.string(r.tray_id);
    w.i64(r.from); w.i64(r.next); w.u64(r.expected_generation); w.u64(r.expected_traversal);
    w.floating(r.delivered_at); w.floating(r.expiry); w.string(r.status); w.string(r.reason);
  }
  w.u64(s.demand_messages.size());
  for (const auto& m : s.demand_messages) {
    w.string(m.message_id); w.string(m.source_owner); w.string(m.target_owner);
    w.u64(m.publication_sequence);
    w.floating(m.observed_at); w.floating(m.delivered_at); w.boolean(m.delivered);
    w.u64(m.jobs.size());
    for (const auto index : m.jobs) {
      const auto& j=s.input.jobs.at(index);
      w.string(j.business_bag_id); w.i64(j.origin); w.floating(j.arrival); w.floating(j.deadline);
    }
  }
  w.u64(s.next_control_id);
  w.u64(s.next_channel_message_id.size());
  for(const auto& [channel,next]:s.next_channel_message_id) {
    w.string(channel.first);w.string(channel.second);w.u64(next);
  }
  w.u64(s.service_forecasts.size());
  for (const auto& m : s.service_forecasts) {
    w.string(m.message_id); w.string(m.source_owner); w.string(m.target_owner);
    w.string(m.business_bag_id); w.string(m.tray_id); w.i64(m.from); w.i64(m.next);
    w.u64(m.generation); w.u64(m.traversal_id);
    w.u64(m.publication_sequence);
    w.floating(m.observed_at); w.floating(m.delivered_at);
    w.floating(m.entry_estimate); w.floating(m.release_estimate);
    w.string(m.status); w.string(m.supersedes); w.boolean(m.delivered);
  }
  w.u64(s.recovery_intents.size());
  for(const auto& r:s.recovery_intents) {
    w.string(r.request_id); w.string(r.owner_id); w.string(r.tray_id);
    w.u64(r.expected_generation); w.floating(r.delivered_at);
    w.string(r.status); w.string(r.reason);
  }
  w.string(s.static_domain_version);
  w.u64(s.static_route_potential.size());
  for(const auto& row:s.static_route_potential) {
    w.u64(row.size()); for(double value:row) w.floating(value);
  }
  w.u64(s.static_route_reachable.size());
  for(const auto& row:s.static_route_reachable) {
    w.u64(row.size()); for(bool value:row) w.boolean(value);
  }
  w.u64(s.resource_waits.size());
  for(const auto& [id,wait]:s.resource_waits) {
    w.i64(id); w.i64(wait.runtime_id); w.i64(wait.node); w.u64(wait.generation);
    w.u64(wait.edge_indices.size()); for(int edge:wait.edge_indices) w.i64(edge);
    w.u64(wait.receiving_nodes.size()); for(int node:wait.receiving_nodes) w.i64(node);
    w.u64(wait.ranking_nodes.size()); for(int node:wait.ranking_nodes) w.i64(node);
    w.boolean(wait.static_blocked);
  }
  const auto write_wait_index=[&](const auto& index) {
    w.u64(index.size());
    for(const auto& [resource,waiters]:index) {
      w.i64(resource); w.u64(waiters.size());
      for(const auto& [id,generation]:waiters) { w.i64(id); w.u64(generation); }
    }
  };
  write_wait_index(s.edge_waiters); write_wait_index(s.receiving_waiters);
  write_wait_index(s.ranking_waiters);
  w.u64(s.next_resource_wait_generation);
  if(s.input.owner_protocol.enabled) {
    w.string("native_owner_command_protocol.v2");
    const auto& p=s.input.owner_protocol;
    w.floating(p.ack_delay);w.floating(p.timeout);w.floating(p.duplicate_ack_delay);
    w.i64(p.drop_ack_packets);w.boolean(p.duplicate_acks);
    w.u64(p.outages.size());for(const auto& outage:p.outages) {
      w.string(outage.owner);w.floating(outage.start);w.floating(outage.end);
    }
    w.u64(s.protocol_owner_down.size());for(const auto& [owner,count]:s.protocol_owner_down) {
      w.string(owner);w.i64(count);
    }
    w.u64(s.protocol_requests.size());for(const auto& r:s.protocol_requests) {
      w.i64(r.transfer);w.string(r.owner);w.string(r.client_status);w.u64(r.attempt);
      w.u64(r.next_ack_sequence);w.u64(r.delivered_ack_sequence);w.u64(r.delivered_attempt);
      w.u64(r.waiting_attempt);
      w.i64(r.latest_ack);w.i64(r.remaining_ack_drops);w.boolean(r.waiting_for_owner);
    }
    w.u64(s.protocol_acks.size());for(const auto& ack:s.protocol_acks) {
      w.i64(ack.request);w.u64(ack.sequence);w.u64(ack.attempt);
      w.floating(ack.observed_at);w.floating(ack.delivered_at);w.string(ack.status);w.string(ack.reason);
      w.floating(ack.received_at);
      w.i64(ack.delivered_copies);w.i64(ack.dropped_copies);
    }
    w.u64(s.protocol_commands.size());for(const auto& c:s.protocol_commands) {
      const auto& p=c.input;
      w.string(p.request_id);w.string(p.owner);w.string(p.kind);w.string(p.target_owner);
      w.string(p.tray_id);w.string(p.business_bag_id);w.string(p.reference_id);w.string(p.reference_request_id);
      w.i64(p.from);w.i64(p.next);w.u64(p.expected_generation);w.u64(p.expected_traversal);
      w.floating(p.message_delay);w.floating(p.publication_delay);w.floating(p.expiry);
      w.string(c.client_status);w.string(c.execution_status);w.string(c.result_status);w.string(c.reason);w.string(c.result_id);
      w.i64(c.native_index);w.i64(c.latest_ack);w.i64(c.remaining_ack_drops);w.floating(c.executed_at);w.floating(c.completed_at);
      w.u64(c.attempt);w.u64(c.arrived_attempt);w.u64(c.waiting_attempt);w.u64(c.next_ack_sequence);
      w.u64(c.delivered_ack_sequence);w.u64(c.delivered_attempt);w.boolean(c.waiting_for_owner);w.boolean(c.waiting_for_recipient);
    }
    w.u64(s.protocol_command_acks.size());for(const auto& a:s.protocol_command_acks) {
      w.i64(a.command);w.u64(a.sequence);w.u64(a.attempt);w.floating(a.observed_at);w.floating(a.delivered_at);
      w.floating(a.executed_at);w.floating(a.completed_at);w.string(a.status);w.string(a.reason);w.string(a.result_id);
      w.i64(a.delivered_copies);w.i64(a.dropped_copies);
    }
  }
  // Disabled mode appends no bytes, preserving the previous checkpoint seal.
  if(s.input.owner_notifications_enabled) {
    w.string("native_owner_notifications.v1");
    w.u64(s.owner_notifications.size());
    for(const auto& [owner,n]:s.owner_notifications) {
      w.string(owner);w.u64(n.sequence);w.floating(n.observed_at);w.u64(n.change_mask);
    }
  }
  // Existing sessions with no planning publication retain their exact seal.
  if(!s.planning_snapshots.empty()) {
    w.string("native_planning_snapshots.v1");w.u64(s.planning_snapshots.size());
    for(const auto& m:s.planning_snapshots) {
      fingerprint_planning_capture(w,m);w.string(m.payload_sha256);
      w.floating(m.delivered_at);w.boolean(m.delivered);
    }
  }
  if(!s.planning_snapshots_v2.empty()) {
    w.string("native_planning_snapshots.v2");w.u64(s.planning_snapshots_v2.size());
    for(const auto& m:s.planning_snapshots_v2) {
      fingerprint_planning_capture_v2(w,m);w.string(m.payload_sha256);
      w.floating(m.delivered_at);w.boolean(m.delivered);
    }
  }
  // Opt-in only: no extra tag/count/byte for an empty v3 history.
  if(!s.planning_snapshots_v3.empty()) {
    w.string("native_planning_snapshots.v3");w.u64(s.planning_snapshots_v3.size());
    for(const auto& m:s.planning_snapshots_v3) {
      fingerprint_planning_capture_v3(w,m);w.string(m.payload_sha256);
      w.floating(m.delivered_at);w.boolean(m.delivered);
    }
  }
}

}  // namespace czr005::ics
