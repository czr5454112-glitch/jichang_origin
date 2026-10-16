#pragma once

// Definitions are included after the mature runtime class. Every lifecycle
// transition is consumed by that runtime's existing native priority queue.
namespace czr005::ics {

inline void EventDrivenJunctionRuntime::initialize_circulation(
    const CirculationInput& input,
    const std::vector<EventRuntimeFaultWindow>& faults) {
  if (config_.complete_on_goal_arrival)
    throw std::invalid_argument("circulation:goal_arrival_completion_unsupported");
  if ((canonical_scorer_mode() != "S4" && canonical_scorer_mode() != "S3") ||
      !uses_jit_destination_merge_grants() ||
      canonical_merge_grant_timing_mode() != DestinationMergeGrantTimingMode::kJitFairAgingDeadline ||
      config_.queue_discipline != "fifo" ||
      config_.g4irsf20_event_hotpath_policy != "E2" ||
      config_.g4irsf24_dlp.mode != "off" || g4irsf16_enabled()) {
    throw std::invalid_argument("circulation:requires_S4_or_S3_FIFO_J2_E2_learning_off");
  }
  if (input.trays.empty()) throw std::invalid_argument("circulation:empty_fleet");
  const auto nonnegative = [](double x) { return std::isfinite(x) && x >= 0; };
  const auto finite_sum = [](std::initializer_list<double> values) {
    double sum = 0;
    for (double value : values) {
      sum += value;
      if (!std::isfinite(sum))
        throw std::invalid_argument("circulation:nonfinite_derived_time");
    }
    return sum;
  };
  const auto locations = graph_.node_locations();
  for (std::size_t i = 0; i < locations.size(); ++i) {
    const int node = locations[i];
    if (!nonnegative(graph_.service_time(node)))
      throw std::invalid_argument("circulation:invalid_node_service");
    if (node != static_cast<int>(i))
      throw std::invalid_argument("circulation:invalid_heuristic_matrix");
    for (int next : graph_.outgoing(node)) {
      const auto& edge = graph_.edge(node, next);
      if (!nonnegative(edge.length) || !std::isfinite(edge.speed) || edge.speed <= 0)
        throw std::invalid_argument("circulation:invalid_edge_geometry");
      if (!std::isfinite(edge.travel_time()))
        throw std::invalid_argument("circulation:invalid_edge_travel");
    }
    for (int goal : locations) {
      try {
        if (!nonnegative(graph_.heuristic(node, goal)))
          throw std::invalid_argument("circulation:invalid_heuristic_matrix");
      } catch (const std::out_of_range&) {
        throw std::invalid_argument("circulation:invalid_heuristic_matrix");
      }
    }
  }
  std::set<int> nodes;
  for (const auto& n : input.nodes) {
    (void)graph_.node(n.node);
    if (!nodes.insert(n.node).second || n.capacity <= 0 ||
        n.export_min_stock < 0 || n.export_min_stock > n.capacity || n.zone.empty())
      throw std::invalid_argument("circulation:invalid_node_contract");
  }
  if (nodes.size() != graph_.node_count())
    throw std::invalid_argument("circulation:node_contract_coverage");
  const auto& protocol=input.owner_protocol;
  if(protocol.enabled) {
    if(!input.transfers.empty()) throw std::invalid_argument("circulation:protocol_disallows_preloaded_transfers");
    if(!nonnegative(protocol.ack_delay) || !nonnegative(protocol.duplicate_ack_delay) ||
       !std::isfinite(protocol.timeout) || protocol.timeout<=0 || protocol.drop_ack_packets<0)
      throw std::invalid_argument("circulation:invalid_owner_protocol");
    (void)finite_sum({protocol.ack_delay,protocol.duplicate_ack_delay});
    for(const auto& outage:protocol.outages) {
      bool known=false;for(const auto& node:input.nodes)
        known=known || (node.resource_owner.empty() ? node.zone : node.resource_owner)==outage.owner;
      if(!known || !nonnegative(outage.start) || !std::isfinite(outage.end) || outage.end<=outage.start)
        throw std::invalid_argument("circulation:invalid_owner_outage");
    }
  } else if(!protocol.outages.empty()) throw std::invalid_argument("circulation:owner_outage_requires_protocol");
  std::set<std::pair<int,int>> edges;
  for (const auto& e : input.edges) {
    if (!graph_.has_edge(e.from, e.to) || !edges.emplace(e.from,e.to).second ||
        e.capacity < 0 || !nonnegative(e.entry_headway))
      throw std::invalid_argument("circulation:invalid_edge_contract");
  }
  if (edges.size() != graph_.edge_count())
    throw std::invalid_argument("circulation:edge_contract_coverage");
  std::set<std::string> tray_ids, job_ids, request_ids;
  for (const auto& t : input.trays) {
    if (t.tray_id.empty() || !tray_ids.insert(t.tray_id).second || !nodes.count(t.node))
      throw std::invalid_argument("circulation:invalid_tray");
  }
  for (const auto& j : input.jobs) {
    if (j.business_bag_id.empty() || !job_ids.insert(j.business_bag_id).second ||
        !nodes.count(j.origin) || !nodes.count(j.destination) ||
        (j.storage_node >= 0 && !nodes.count(j.storage_node)) ||
        !nonnegative(j.arrival) || !std::isfinite(j.deadline) ||
        !nonnegative(j.storage_release_at) || !nonnegative(j.storage_min_dwell) ||
        !nonnegative(j.load_seconds) || !nonnegative(j.unload_seconds) ||
        !nonnegative(j.hold_seconds))
      throw std::invalid_argument("circulation:invalid_job");
    (void)finite_sum({j.arrival, j.load_seconds, j.storage_min_dwell,
                      j.unload_seconds, j.hold_seconds});
    (void)finite_sum({j.storage_release_at, j.unload_seconds, j.hold_seconds});
    // Zero-hop contracts require explicit handling of source service and are
    // rejected rather than counted as a physical movement in this first slice.
    if (j.origin == j.destination || j.storage_node == j.origin ||
        j.storage_node == j.destination)
      throw std::invalid_argument("circulation:zero_hop_contract_unsupported");
  }
  for (const auto& t : input.transfers) {
    if (t.request_id.rfind("live:",0)==0)
      throw std::invalid_argument("circulation:reserved_live_request_namespace");
    if (t.request_id.empty() || !request_ids.insert(t.request_id).second ||
        !tray_ids.count(t.tray_id) || !nodes.count(t.source) ||
        !nodes.count(t.destination) || t.source == t.destination ||
        !nonnegative(t.issued_at) || !nonnegative(t.message_delay) ||
        !nonnegative(t.earliest_departure) || !nonnegative(t.expiry))
      throw std::invalid_argument("circulation:invalid_transfer");
    (void)finite_sum({t.issued_at, t.message_delay});
  }
  // Fault notifications are queued by initialize before the circulation flag
  // becomes active, so validate their derived delivery times here as well.
  for (const auto& fault : faults) {
    validate_fault_window(fault);
    (void)finite_sum({fault.fault_time, fault.message_delay});
    (void)finite_sum({fault.repair_time, fault.message_delay});
  }
  initialize({}, faults);
  circulation_.enabled = true;
  // Mature legacy keeps its frozen comparator. All circulation policies use
  // exact time ordering, regardless of notification/control activation mode.
  // initialize() may already have queued faults, hence the explicit reheap.
  events_.set_exact_time_order(true);
  circulation_.input = input;
  if(input.owner_notifications_enabled) {
    if(!input.owner_protocol.enabled)
      throw std::invalid_argument("circulation:notifications_require_owner_protocol");
    for(const auto& node:input.nodes)
      circulation_.owner_notifications.emplace(circulation_.owner(node.node),CirculationOwnerNotification{});
  }
  initialize_circulation_static_domain(circulation_,graph_,config_.minimum_service_seconds);
  if (config_.max_simulation_time < 0) {
    double latest = 0;
    for (const auto& job : input.jobs)
      latest = std::max({latest, job.storage_release_at,
          job.arrival + job.load_seconds + job.storage_min_dwell +
              job.unload_seconds + job.hold_seconds});
    for (const auto& request : input.transfers)
      latest = std::max({latest, request.issued_at + request.message_delay,
                         request.earliest_departure});
    for (const auto& fault : faults)
      latest = std::max(latest, fault.repair_time + fault.message_delay);
    time_limit_ = finite_sum({latest, 86400.0});
  }
  // Every processed protocol event is inside this runtime bound; validate
  // derived ACK delivery times before a session becomes externally usable.
  if(input.owner_protocol.enabled)
    (void)finite_sum({time_limit_,input.owner_protocol.ack_delay,input.owner_protocol.duplicate_ack_delay});
  circulation_.next_entry.assign(input.edges.size(), 0.0);
  circulation_.jobs.resize(input.jobs.size());
  circulation_.transfers.resize(input.transfers.size());
  for (const auto& t : input.trays) {
    CirculationTrayState state;
    state.tray_id = t.tray_id;
    state.node = t.node;
    circulation_.trays.push_back(std::move(state));
  }
  for (const auto& n : input.nodes) {
    if (circulation_.occupancy(n.node) > n.capacity)
      throw std::invalid_argument("circulation:initial_receiving_full");
  }
  for (std::size_t i = 0; i < input.jobs.size(); ++i)
    circulation_schedule("job_arrival", input.jobs[i].arrival, static_cast<int>(i));
  for (std::size_t i = 0; i < input.transfers.size(); ++i) {
    const auto& request = input.transfers[i];
    circulation_schedule("module_message", request.issued_at + request.message_delay,
                          static_cast<int>(i));
  }
  if(input.owner_protocol.enabled) for(std::size_t i=0;i<input.owner_protocol.outages.size();++i) {
    const auto& outage=input.owner_protocol.outages[i];
    circulation_schedule("protocol_owner_down",outage.start,static_cast<int>(i));
    circulation_schedule("protocol_owner_up",outage.end,static_cast<int>(i));
  }
  runtime_phase_ = events_.empty() ? EventDrivenJunctionRuntimePhase::kStopped
                                 : EventDrivenJunctionRuntimePhase::kReady;
}

inline void EventDrivenJunctionRuntime::circulation_schedule(
    const std::string& reason, double time, int index, std::uint64_t generation) {
  if (!std::isfinite(time))
    throw std::invalid_argument("circulation:nonfinite_event_time");
  RuntimeEvent event;
  event.type = JunctionEventType::kCirculation;
  event.time = time;
  event.task_id = index;
  event.wakeup_generation = generation;
  event.reason = reason;
  push_event(std::move(event));
}

inline void EventDrivenJunctionRuntime::circulation_receipt(
    double time, const std::string& event, int tray, int leg, int from, int to,
    const std::string& reason) {
  CirculationReceipt row;
  row.time = time; row.event = event; row.from = from; row.to = to; row.reason = reason;
  const bool local_physical=event=="LOAD_START" || event=="LOAD_COMPLETE" ||
      event=="STORAGE_ENTER" || event=="STORAGE_RELEASE" || event=="UNLOAD_START" ||
      event=="UNLOAD_COMPLETE" || event=="HOLD_START" || event=="HOLD_COMPLETE" ||
      event=="EDGE_ENTER" || event=="EDGE_EXIT" || event=="EMPTY_RECEIVED" ||
      event=="LEG_FAILED" || event=="EXPORT_GRANTED" || event=="UNUSED_RECEIVING_RELEASED";
  if (tray >= 0) {
    const auto& t = circulation_.trays.at(tray);
    row.tray_id = t.tray_id; row.node = t.node; row.traversal_id = t.traversal_id;
    if(local_physical) circulation_.notify_node(t.node,now_,2);
    if (t.job >= 0) row.business_bag_id = circulation_.input.jobs.at(t.job).business_bag_id;
  }
  if (leg >= 0) {
    const auto& l = circulation_.legs.at(leg);
    row.transport_leg_id = l.transport_leg_id;
    if (l.job >= 0) row.business_bag_id = circulation_.input.jobs.at(l.job).business_bag_id;
  }
  circulation_.receipts.push_back(std::move(row));
  if(local_physical) {
    circulation_.notify_node(from,now_,2);
    circulation_.notify_node(to,now_,2);
  }
}

inline void EventDrivenJunctionRuntime::circulation_create_leg(
    int tray_index, int job_index, int destination, const std::string& kind, double time) {
  auto& tray = circulation_.trays.at(tray_index);
  if (tray.active_leg >= 0 || tray.edge_to >= 0 || tray.node == destination)
    throw std::logic_error("circulation:invalid_leg_activation");
  const int id = static_cast<int>(circulation_.legs.size());
  TimingAssociation timing_identity{TimingIdentity::leg, id};
  if (kind == "empty_return" && tray.transfer >= 0) {
    timing_identity.related_kind = TimingIdentity::transfer;
    timing_identity.related_index = tray.transfer;
  } else if (job_index >= 0) {
    timing_identity.related_kind = TimingIdentity::job;
    timing_identity.related_index = job_index;
  }
  // Immutable creation-time relation survives a reused tray and stale old-leg
  // events. No later reconstruction from the tray or transport ID text.
  auto timing_leg = request_timing_.scoped(TimingPhase::leg_creation, timing_identity,
      TimingMethod::none, 0, time);
  CirculationLeg leg;
  leg.runtime_id = id; leg.tray = tray_index; leg.job = job_index; leg.kind = kind;
  const std::string owner = job_index >= 0
      ? circulation_.input.jobs[job_index].business_bag_id
      : circulation_.input.transfers.at(tray.transfer).request_id;
  leg.transport_leg_id = owner + ":" + kind + ":" + std::to_string(id);
  EventRuntimeBagRequest request;
  request.segment_id = leg.transport_leg_id;
  request.task_id = job_index >= 0 ? job_index : static_cast<int>(circulation_.jobs.size()) + tray.transfer;
  request.runtime_bag_id = id; request.release_time = time;
  request.deadline = job_index >= 0 ? circulation_.input.jobs[job_index].deadline : -1;
  request.start = tray.node; request.goal = destination;
  request.source = kind == "storage_out" ? "storage" : "circulation";
  validate_request(request);
  BagState bag; bag.request = request; bag.current = tray.node;
  bags_.emplace(id, std::move(bag));
  segment_runtime_ids_.emplace(request.segment_id, id);
  circulation_.legs.push_back(std::move(leg));
  tray.active_leg = id;
  ++result_.summary.requested_count;
  circulation_receipt(time, "LEG_START", tray_index, id, tray.node, destination, kind);
  schedule(JunctionEventType::kBagRelease, time, id, tray.node, -1, -1);
  for (const int downstream : graph_.outgoing(tray.node))
    schedule_passive(JunctionEventType::kCongestionBeaconUpdate, time, -1,
                     downstream, -1, downstream, "circulation_leg_initial_snapshot");
}

inline void EventDrivenJunctionRuntime::circulation_publish_event(RuntimeEvent& event) noexcept {
  if (!circulation_.enabled || event.task_id < 0 ||
      event.task_id >= static_cast<int>(circulation_.legs.size())) return;
  auto& tray = circulation_.trays[circulation_.legs[event.task_id].tray];
  if (event.type == JunctionEventType::kEdgeEnter) {
    // event.seq is assigned only AFTER this callback. The enclosing dispatch
    // scope supplies the causative event; do not report this unpublished seq.
    auto timing_commit = request_timing_.scoped(TimingPhase::reservation_commit,
        request_timing_leg(event.task_id), TimingMethod::none, 0, now_);
    circulation_.reserve_enter(event.task_id, event.from_node, event.to_node, event.time);
    // Reservation changes visible capacity at commit, not future EdgeEnter.
    circulation_.notify_node(event.from_node,now_,2);
    circulation_.notify_node(event.to_node,now_,2);
    event.traversal_id = tray.traversal_id;
  } else if (event.type == JunctionEventType::kEdgeExit) {
    event.traversal_id = tray.traversal_id;
  }
}

inline bool EventDrivenJunctionRuntime::circulation_edge_enter(const RuntimeEvent& event) {
  if (!circulation_.enabled) return true;
  if (event.task_id < 0 || event.task_id >= static_cast<int>(circulation_.legs.size())) return false;
  const int ti = circulation_.legs[event.task_id].tray;
  auto& tray = circulation_.trays[ti];
  if (tray.active_leg != event.task_id || tray.traversal_id != event.traversal_id ||
      tray.edge_from != event.from_node || tray.edge_to != event.to_node || tray.edge_entry_observed) {
    circulation_receipt(event.time, "STALE_TRAVERSAL_REJECTED", ti, event.task_id,
                         event.from_node, event.to_node, "entry_identity_mismatch");
    return false;
  }
  tray.edge_entry_observed = true;
  if (tray.transfer >= 0) {
    auto& transfer = circulation_.transfers[tray.transfer];
    if (transfer.status == "dispatching") {
      transfer.status = "departed";
      transfer.departed_at = event.time;
    }
  }
  circulation_receipt(event.time, "EDGE_ENTER", ti, event.task_id, event.from_node, event.to_node);
  circulation_forget_resource_wait(event.task_id);
  circulation_notify_resource(true, event.from_node, event.time, "source_berth_departed");
  return true;
}

inline bool EventDrivenJunctionRuntime::circulation_edge_exit(const RuntimeEvent& event) {
  if (!circulation_.enabled) return true;
  if (event.task_id < 0 || event.task_id >= static_cast<int>(circulation_.legs.size())) return false;
  const int ti = circulation_.legs[event.task_id].tray;
  auto& tray = circulation_.trays[ti];
  if (tray.active_leg != event.task_id || tray.traversal_id != event.traversal_id ||
      tray.edge_from != event.from_node || tray.edge_to != event.to_node || !tray.edge_entry_observed) {
    circulation_receipt(event.time, "STALE_TRAVERSAL_REJECTED", ti, event.task_id,
                         event.from_node, event.to_node, "exit_identity_mismatch");
    return false;
  }
  tray.node = event.to_node; tray.edge_from = -1; tray.edge_to = -1;
  circulation_receipt(event.time, "EDGE_EXIT", ti, event.task_id, event.from_node, event.to_node);
  circulation_notify_resource(false, circulation_.edge_index(event.from_node, event.to_node),
                               event.time, "edge_capacity_released");
  return true;
}

inline void EventDrivenJunctionRuntime::circulation_leg_completed(int runtime_id, double time) {
  // Capture transfer association before the successful empty return clears it.
  auto timing_complete = request_timing_.scoped(TimingPhase::outcome_update,
      request_timing_leg(runtime_id), TimingMethod::none, 0, time);
  if (!circulation_.enabled) return;
  circulation_forget_resource_wait(runtime_id);
  const auto leg = circulation_.legs.at(runtime_id);
  auto& tray = circulation_.trays.at(leg.tray);
  if (tray.active_leg != runtime_id || tray.edge_to >= 0)
    throw std::logic_error("circulation:completion_without_physical_arrival");
  circulation_receipt(time, "LEG_COMPLETE", leg.tray, runtime_id, -1, tray.node, leg.kind);
  tray.active_leg = -1;
  ++tray.generation;
  if (leg.kind == "storage_in") {
    const auto& job = circulation_.input.jobs.at(leg.job);
    auto& state = circulation_.jobs.at(leg.job);
    tray.mode = "storage"; tray.storage_arrived_at = time;
    state.status = "storage"; state.storage_entered_at = time;
    const double ready = std::max({time, job.storage_release_at, time + job.storage_min_dwell});
    circulation_receipt(time, "STORAGE_ENTER", leg.tray, runtime_id);
    circulation_schedule("storage_ready", ready, leg.tray, tray.generation);
  } else if (leg.kind == "empty_return") {
    auto& transfer = circulation_.transfers.at(tray.transfer);
    transfer.status = "received"; transfer.received_at = time;
    tray.mode = "empty"; tray.reception_node = -1; tray.available_at = time;
    circulation_receipt(time, "EMPTY_RECEIVED", leg.tray, runtime_id, -1, tray.node,
                         circulation_.input.transfers[tray.transfer].request_id);
    tray.transfer = -1;
    circulation_progress(time);
  } else {
    tray.mode = "unloading";
    circulation_.jobs.at(leg.job).status = "unloading";
    circulation_receipt(time, "UNLOAD_START", leg.tray, runtime_id);
    circulation_schedule("unload_complete", time + circulation_.input.jobs[leg.job].unload_seconds,
                          leg.tray, tray.generation);
  }
}

inline void EventDrivenJunctionRuntime::circulation_leg_failed(
    int runtime_id, const std::string& reason, double time) {
  auto timing_failed = request_timing_.scoped(TimingPhase::outcome_update,
      request_timing_leg(runtime_id), TimingMethod::none, 0, time);
  if (!circulation_.enabled || runtime_id < 0 || runtime_id >= static_cast<int>(circulation_.legs.size())) return;
  circulation_forget_resource_wait(runtime_id);
  const auto& leg = circulation_.legs[runtime_id];
  auto& tray = circulation_.trays[leg.tray];
  tray.mode = "quarantined";
  if (leg.job >= 0) circulation_.jobs[leg.job].status = "failed";
  if (tray.transfer >= 0) {
    auto& transfer = circulation_.transfers[tray.transfer];
    transfer.status = "failed";
    transfer.reason = reason;
    if (transfer.departed_at < 0 && tray.edge_to < 0 && tray.reception_node >= 0) {
      const int released = tray.reception_node;
      tray.reception_node = -1;
      circulation_receipt(time, "UNUSED_RECEIVING_RELEASED", leg.tray, runtime_id,
                           tray.node, released, reason);
      circulation_notify_resource(true, released, time, "unused_receiving_lease_released");
    }
  }
  // Preserve the real carrier and any in-flight/receiving occupancy. A failed
  // operation cannot manufacture an available tray or erase a physical load.
  circulation_receipt(time, "LEG_FAILED", leg.tray, runtime_id,
                       -1, tray.node, reason);
}

inline void EventDrivenJunctionRuntime::circulation_progress(double time) {
  auto timing_scan = request_timing_.scoped(TimingPhase::shared_scan, {}, TimingMethod::none, 0, time);
  // Owner-local load permission is consumed before discretionary empty export.
  std::vector<std::size_t> waiting;
  for (std::size_t ji = 0; ji < circulation_.jobs.size(); ++ji)
    if (circulation_.jobs[ji].status == "waiting_for_tray") waiting.push_back(ji);
  std::sort(waiting.begin(), waiting.end(), [&](std::size_t a, std::size_t b) {
    const auto& left = circulation_.input.jobs[a];
    const auto& right = circulation_.input.jobs[b];
    return std::tie(left.arrival, left.business_bag_id) <
           std::tie(right.arrival, right.business_bag_id);
  });
  for (const std::size_t ji : waiting) {
    auto& state = circulation_.jobs[ji];
    if (state.status != "waiting_for_tray") continue;
    const auto& job = circulation_.input.jobs[ji];
    for (std::size_t ti = 0; ti < circulation_.trays.size(); ++ti) {
      auto& tray = circulation_.trays[ti];
      if (tray.node != job.origin || tray.mode != "empty" || tray.active_leg >= 0 ||
          tray.edge_to >= 0 || tray.available_at > time + 1e-9) continue;
      tray.mode = "loading"; tray.job = static_cast<int>(ji); ++tray.generation;
      state.status = "loading"; state.tray = static_cast<int>(ti);
      circulation_receipt(time, "LOAD_START", static_cast<int>(ti));
      circulation_schedule("load_complete", time + job.load_seconds,
                            static_cast<int>(ti), tray.generation);
      break;
    }
  }
  for (std::size_t xi = 0; xi < circulation_.transfers.size(); ++xi) {
    auto& state = circulation_.transfers[xi];
    if (state.status != "pending") continue;
    const TimingAssociation timing_identity{TimingIdentity::transfer, static_cast<std::int64_t>(xi)};
    auto timing_transfer = request_timing_.scoped(TimingPhase::transfer_progress, timing_identity,
        TimingMethod::none, 0, time);
    auto timing_source = request_timing_.scoped(TimingPhase::source_validate, timing_identity,
        TimingMethod::none, 0, time);
    if(!circulation_protocol_transfer_available(static_cast<int>(xi))) continue;
    const auto& request = circulation_.input.transfers[xi];
    auto& tray = circulation_.trays.at(state.tray);
    const auto reject = [&](const std::string& reason) {
      state.status = "rejected"; state.reason = reason;
      circulation_receipt(time, "TRANSFER_REJECTED", state.tray, -1,
                           request.source, request.destination, reason);
    };
    if (time > request.expiry + 1e-9) { reject("departure_lease_expired"); continue; }
    if (time + 1e-9 < request.earliest_departure) continue;
    if (tray.mode != "empty" || tray.active_leg >= 0 || tray.edge_to >= 0 ||
        tray.available_at > time + 1e-9) continue;
    if (tray.node != request.source) { reject("carrier_not_at_export_port"); continue; }
    const auto& source = circulation_.node_contract(request.source);
    const auto& destination = circulation_.node_contract(request.destination);
    if (source.zone == destination.zone) {
      reject("same_zone_transfer_not_authorized"); continue;
    }
    if (!source.allow_export) { reject("source_module_refused"); continue; }
    timing_source.finish();
    auto timing_receive_permission = request_timing_.scoped(TimingPhase::receiver_validate, timing_identity,
        TimingMethod::none, 0, time);
    if (!destination.allow_receive) { reject("destination_module_refused"); continue; }
    timing_receive_permission.finish();
    auto timing_stock = request_timing_.scoped(TimingPhase::source_validate, timing_identity,
        TimingMethod::none, 0, time);
    if (circulation_.empty_stock(request.source, time) <= source.export_min_stock) {
      reject("source_module_min_stock"); continue;
    }
    timing_stock.finish();
    auto timing_receiving_capacity = request_timing_.scoped(TimingPhase::receiver_validate, timing_identity,
        TimingMethod::none, 0, time);
    if (circulation_.occupancy(request.destination, state.tray) >= destination.capacity) {
      reject("receiving_full"); continue;
    }
    timing_receiving_capacity.finish();
    auto timing_grant = request_timing_.scoped(TimingPhase::reservation_commit, timing_identity,
        TimingMethod::none, 0, time);
    tray.reception_node = request.destination; tray.transfer = static_cast<int>(xi);
    tray.mode = "empty_transit"; state.status = "dispatching";
    circulation_receipt(time, "EXPORT_GRANTED", state.tray, -1,
                         request.source, request.destination, request.request_id);
    circulation_create_leg(state.tray, -1, request.destination, "empty_return", time);
  }
}

inline void EventDrivenJunctionRuntime::process_circulation_event(const RuntimeEvent& event) {
  if (!circulation_.enabled) throw std::logic_error("circulation:event_in_legacy_mode");
  const double time = event.time;
  if(circulation_.input.owner_protocol.enabled && process_circulation_protocol_event(event)) return;
  if (event.reason == "resource_headway_ready") {
    circulation_wake_resource_wait(event.task_id, event.wakeup_generation, time,
                                    "committed_headway_expired");
    return;
  }
  if (event.reason == "control_route") {
    auto timing_route = request_timing_.scoped(TimingPhase::permission_validate,
        {TimingIdentity::route, event.task_id}, TimingMethod::none, event.seq, time);
    auto& request = circulation_.route_intents.at(event.task_id);
    if (request.status != "pending") return;
    if(!circulation_protocol_publication_available("route",event.task_id)) return;
    auto tray = std::find_if(circulation_.trays.begin(), circulation_.trays.end(),
                            [&](const auto& t) { return t.tray_id == request.tray_id; });
    request.reason = "allowed";
    if (request.expiry < time) request.reason = "request_expired";
    else if (tray == circulation_.trays.end() || tray->generation != request.expected_generation ||
             tray->public_traversal_version != request.expected_traversal ||
             tray->node != request.from || tray->edge_to >= 0 || tray->active_leg < 0)
      request.reason = "stale_executed_prefix";
    else if (circulation_.owner(request.from) != request.owner_id)
      request.reason = "resource_owner_mismatch";
    else if (tray->job < 0 || circulation_.input.jobs[tray->job].business_bag_id != request.business_bag_id)
      request.reason = "business_identity_mismatch";
    else if (!circulation_.input.jobs[tray->job].allow_suffix_reroute)
      request.reason = "service_obligation_disallows_reroute";
    else if (!graph_.has_edge(request.from, request.next)) request.reason = "not_a_directed_edge";
    else {
      const auto& leg = circulation_.legs[tray->active_leg];
      const int goal = bags_.at(leg.runtime_id).request.goal;
      const auto& job = circulation_.input.jobs[tray->job];
      const double optimistic = time + graph_.edge(request.from,request.next).travel_time() +
          static_potential(request.next,goal) + job.unload_seconds;
      const auto known_fault = advertised_faults_.find(
          event_runtime_detail::directed_key(request.from,request.next));
      // Receiving a preference is not a hard reservation, but must not report
      // an already known impossible suffix as an installed valid update. Use
      // the active stage goal so Storage cannot be bypassed, and only delivered
      // fault knowledge; unannounced physical changes remain executor checks.
      if (!circulation_static_reachable(request.next,goal))
        request.reason = "no_static_legal_suffix";
      else if (known_fault != advertised_faults_.end() && known_fault->second.faulted)
        request.reason = "advertised_fault";
      else if (job.deadline >= 0 && optimistic > job.deadline)
        request.reason = "service_deadline_necessary_bound";
      else if (circulation_.can_enter(tray->active_leg,request.from,request.next,time) != "allowed")
        request.reason = circulation_.can_enter(tray->active_leg,request.from,request.next,time);
    }
    request.status = request.reason == "allowed" ? "updated" : "rejected";
    CirculationReceipt row; row.time=time; row.event="ROUTE_INTENT_"+request.status;
    row.business_bag_id=request.business_bag_id; row.tray_id=request.tray_id;
    row.node=request.from; row.from=request.from; row.to=request.next; row.reason=request.reason;
    circulation_.receipts.push_back(std::move(row));
    if(request.status=="updated") {
      const auto waiting=circulation_.resource_waits.find(tray->active_leg);
      if(waiting!=circulation_.resource_waits.end())
        circulation_wake_resource_wait(tray->active_leg,waiting->second.generation,time,"route_intent_updated");
    }
    circulation_protocol_command_complete("route",event.task_id,request.status,request.reason,request.request_id,time);
    return;
  }
  if (event.reason == "control_demand") {
    auto timing_delivery = request_timing_.scoped(TimingPhase::publication_delivery,
        {TimingIdentity::demand, event.task_id}, TimingMethod::none, event.seq, time);
    if(!circulation_protocol_publication_available("demand",event.task_id)) return;
    auto& message=circulation_.demand_messages.at(event.task_id);
    const bool first_delivery=!message.delivered;
    message.delivered = true;
    if(first_delivery) circulation_publication_journal_.record_demand(event.task_id);
    if(circulation_.input.owner_protocol.enabled) message.delivered_at=time;
    circulation_protocol_command_complete("demand",event.task_id,"delivered","",message.message_id,time);
    circulation_.notify_owner(message.target_owner,now_,4);
    return;
  }
  if (event.reason == "control_service_forecast") {
    auto timing_delivery = request_timing_.scoped(TimingPhase::publication_delivery,
        {TimingIdentity::service_forecast, event.task_id}, TimingMethod::none, event.seq, time);
    // Delivery never recomputes the sender's old snapshot from remote state.
    if(!circulation_protocol_publication_available("service_forecast",event.task_id)) return;
    auto& message=circulation_.service_forecasts.at(event.task_id);
    const bool first_delivery=!message.delivered;
    message.delivered = true;
    if(first_delivery) circulation_publication_journal_.record_forecast(event.task_id);
    if(circulation_.input.owner_protocol.enabled) message.delivered_at=time;
    circulation_protocol_command_complete("service_forecast",event.task_id,"delivered","",message.message_id,time);
    circulation_.notify_owner(message.target_owner,now_,8);
    return;
  }
  if (event.reason == "control_planning_snapshot") {
    auto timing_delivery = request_timing_.scoped(TimingPhase::publication_delivery,
        {TimingIdentity::planning_snapshot, event.task_id}, TimingMethod::none, event.seq, time);
    if(!circulation_protocol_publication_available("planning_snapshot",event.task_id)) return;
    auto& message=circulation_.planning_snapshots.at(event.task_id);
    if(message.delivered) return;
    message.delivered=true;message.delivered_at=time;
    const bool expired=time>=message.valid_until;
    circulation_protocol_command_complete("planning_snapshot",event.task_id,expired ? "expired" : "delivered",
        expired ? "planning_snapshot_expired" : "",message.message_id,time);
    circulation_.notify_owner(message.target_owner,now_,128);
    return;
  }
  if (event.reason == "control_clock") return;
  if (event.reason == "control_planning_snapshot_v2") {
    auto timing_delivery = request_timing_.scoped(TimingPhase::publication_delivery,
        {TimingIdentity::planning_snapshot_v2, event.task_id}, TimingMethod::none, event.seq, time);
    if(!circulation_protocol_publication_available("planning_snapshot_v2",event.task_id)) return;
    auto& message=circulation_.planning_snapshots_v2.at(event.task_id);
    if(message.delivered) return;
    message.delivered=true;message.delivered_at=time;
    const bool expired=time>=message.valid_until;
    circulation_protocol_command_complete("planning_snapshot_v2",event.task_id,expired ? "expired" : "delivered",
        expired ? "planning_snapshot_expired" : "",message.message_id,time);
    circulation_.notify_owner(message.target_owner,now_,128);
    return;
  }
  if (event.reason == "control_planning_snapshot_v3") {
    auto timing_delivery = request_timing_.scoped(TimingPhase::publication_delivery,
        {TimingIdentity::planning_snapshot_v3, event.task_id}, TimingMethod::none, event.seq, time);
    if(!circulation_protocol_publication_available("planning_snapshot_v3",event.task_id)) return;
    auto& message=circulation_.planning_snapshots_v3.at(event.task_id);
    if(message.delivered) return;
    message.delivered=true;message.delivered_at=time;
    const bool expired=time>=message.valid_until;
    circulation_protocol_command_complete("planning_snapshot_v3",event.task_id,expired ? "expired" : "delivered",
        expired ? "planning_snapshot_expired" : "",message.message_id,time);
    circulation_.notify_owner(message.target_owner,now_,128);
    return;
  }
  if (event.reason == "control_recover_empty") {
    auto& request=circulation_.recovery_intents.at(event.task_id);
    if(request.status!="pending") return;
    auto tray=std::find_if(circulation_.trays.begin(),circulation_.trays.end(),
        [&](const auto& t){return t.tray_id==request.tray_id;});
    request.reason="allowed";
    if(tray==circulation_.trays.end() || circulation_.owner(tray->node)!=request.owner_id)
      request.reason="resource_owner_mismatch";
    else if(tray->generation!=request.expected_generation) request.reason="stale_recovery_generation";
    else if(tray->mode!="quarantined") request.reason="not_quarantined";
    else if(tray->job>=0) request.reason="loaded_recovery_requires_service_continuation";
    else if(tray->edge_to>=0 || tray->reception_node>=0) request.reason="inflight_or_receiving_obligation";
    else if(tray->active_leg<0 || bags_.at(tray->active_leg).status!=BagStatus::kFailed)
      request.reason="prior_attempt_not_failed";
    request.status=request.reason=="allowed" ? "recovered" : "rejected";
    if(request.status=="recovered") {
      const int prior=tray->active_leg;
      for(auto& pair:junctions_) {
        auto& q=pair.second.queue; q.erase(std::remove(q.begin(),q.end(),prior),q.end());
        auto& sq=pair.second.source_queue; sq.erase(std::remove(sq.begin(),sq.end(),prior),sq.end());
      }
      tray->active_leg=-1;tray->transfer=-1;tray->mode="empty";tray->available_at=time;++tray->generation;
    }
    CirculationReceipt row;row.time=time;row.event=request.status=="recovered" ? "EMPTY_RECOVERY_GRANTED" : "RECOVERY_REJECTED";
    row.tray_id=request.tray_id;row.reason=request.request_id+":"+request.reason;
    if(tray!=circulation_.trays.end()) row.node=tray->node;
    circulation_.receipts.push_back(std::move(row));
    if(request.status=="recovered") circulation_progress(time);
    return;
  }
  if (event.reason == "job_arrival") {
    auto& state = circulation_.jobs.at(event.task_id);
    if (state.status != "unreleased") return;
    state.status = "waiting_for_tray";
    circulation_.notify_node(circulation_.input.jobs[event.task_id].origin,now_,1);
    CirculationReceipt row; row.time = time; row.event = "BAG_ARRIVAL";
    row.business_bag_id = circulation_.input.jobs[event.task_id].business_bag_id;
    row.node = circulation_.input.jobs[event.task_id].origin;
    circulation_.receipts.push_back(std::move(row));
    circulation_progress(time);
    return;
  }
  if (event.reason == "module_message") {
    auto timing_delivery = request_timing_.scoped(TimingPhase::source_execution,
        {TimingIdentity::transfer, event.task_id, event.wakeup_generation}, TimingMethod::none, event.seq, time);
    auto& state = circulation_.transfers.at(event.task_id);
    int protocol_index=-1;
    if(circulation_.input.owner_protocol.enabled) {
      for(std::size_t i=0;i<circulation_.protocol_requests.size();++i)
        if(circulation_.protocol_requests[i].transfer==event.task_id) protocol_index=static_cast<int>(i);
      if(protocol_index<0) throw std::logic_error("circulation:protocol_transfer_missing_client");
      if(!circulation_protocol_transfer_available(event.task_id)) {
        auto& waiting=circulation_.protocol_requests[protocol_index];waiting.waiting_for_owner=true;
        waiting.waiting_attempt=std::max(waiting.waiting_attempt,event.wakeup_generation ? event.wakeup_generation : 1);
        return;
      }
    }
    if(state.status!="undelivered") {
      // Several real duplicate wire deliveries may have queued at one native
      // recovery boundary. Each may ACK its immutable identity/attempt, but
      // only the first is allowed to enter physical transfer processing.
      if(protocol_index>=0) circulation_protocol_send_ack(protocol_index,time,event.wakeup_generation ? event.wakeup_generation : 1);
      return;
    }
    const auto& request = circulation_.input.transfers[event.task_id];
    state.delivered_at = time;
    for (std::size_t i = 0; i < circulation_.trays.size(); ++i)
      if (circulation_.trays[i].tray_id == request.tray_id) state.tray = static_cast<int>(i);
    circulation_receipt(time, "MODULE_REQUEST_DELIVERED", state.tray, -1,
                         request.source, request.destination, request.request_id);
    state.status = "pending";
    if (request.earliest_departure > time && request.earliest_departure <= time_limit_)
      circulation_schedule("transfer_wakeup", request.earliest_departure, event.task_id);
    if (request.expiry >= time && request.expiry + 1e-8 <= time_limit_)
      circulation_schedule("transfer_expiry", request.expiry + 1e-8, event.task_id);
    circulation_progress(time);
    if(protocol_index>=0) circulation_protocol_send_ack(protocol_index,time,event.wakeup_generation ? event.wakeup_generation : 1);
    return;
  }
  if (event.reason == "transfer_wakeup" || event.reason == "transfer_expiry") {
    auto timing_deferred = request_timing_.scoped(TimingPhase::transfer_progress,
        {TimingIdentity::transfer, event.task_id}, TimingMethod::none, event.seq, time);
    auto& state = circulation_.transfers.at(event.task_id);
    if (event.reason == "transfer_expiry" && state.status == "dispatching") {
      const int tray_index = state.tray;
      auto& tray = circulation_.trays.at(tray_index);
      const int id = tray.active_leg;
      if (id >= 0 && tray.edge_to < 0) {
        auto& bag = bags_.at(id);
        for (auto& pair : junctions_) {
          auto& q = pair.second.queue;
          q.erase(std::remove(q.begin(), q.end(), id), q.end());
          auto& sq = pair.second.source_queue;
          sq.erase(std::remove(sq.begin(), sq.end(), id), sq.end());
        }
        fail_bag(bag, "departure_lease_expired_before_physical_entry", time);
      }
    }
    circulation_progress(time);
    return;
  }
  auto& tray = circulation_.trays.at(event.task_id);
  if (tray.generation != event.wakeup_generation) {
    circulation_receipt(time, "STALE_LIFECYCLE_REJECTED", event.task_id, -1, -1, -1, event.reason);
    return;
  }
  const int job_index = tray.job;
  if (job_index < 0) throw std::logic_error("circulation:lifecycle_without_load");
  auto& state = circulation_.jobs.at(job_index);
  const auto& job = circulation_.input.jobs.at(job_index);
  if (event.reason == "load_complete" && tray.mode == "loading") {
    tray.mode = "loaded"; state.status = "in_transit"; state.loaded_at = time;
    circulation_receipt(time, "LOAD_COMPLETE", event.task_id);
    circulation_create_leg(event.task_id, job_index,
        job.storage_node >= 0 ? job.storage_node : job.destination,
        job.storage_node >= 0 ? "storage_in" : "direct", time);
  } else if (event.reason == "storage_ready" && tray.mode == "storage") {
    if (time + 1e-9 < job.storage_release_at ||
        time + 1e-9 < tray.storage_arrived_at + job.storage_min_dwell)
      throw std::logic_error("circulation:premature_storage_release");
    tray.mode = "loaded"; state.status = "in_transit"; state.storage_released_at = time;
    circulation_receipt(time, "STORAGE_RELEASE", event.task_id);
    circulation_create_leg(event.task_id, job_index, job.destination, "storage_out", time);
  } else if (event.reason == "unload_complete" && tray.mode == "unloading") {
    state.status = "completed"; state.completed_at = time;
    state.deadline_met = job.deadline < 0 || time <= job.deadline + 1e-9;
    tray.mode = "hold"; tray.available_at = time + job.hold_seconds;
    circulation_receipt(time, "UNLOAD_COMPLETE", event.task_id);
    circulation_receipt(time, "HOLD_START", event.task_id);
    circulation_schedule("hold_complete", tray.available_at, event.task_id, tray.generation);
  } else if (event.reason == "hold_complete" && tray.mode == "hold") {
    circulation_receipt(time, "HOLD_COMPLETE", event.task_id);
    tray.mode = "empty"; tray.job = -1;
    circulation_progress(time);
  } else {
    throw std::logic_error("circulation:invalid_lifecycle_transition:" + event.reason);
  }
}

} // namespace czr005::ics
