#pragma once

namespace czr005::ics {

inline int EventDrivenJunctionRuntime::advance_circulation_to(double horizon, int budget) {
  if (!circulation_.enabled || runtime_phase_ == EventDrivenJunctionRuntimePhase::kIdle ||
      runtime_phase_ == EventDrivenJunctionRuntimePhase::kFinalized)
    throw std::logic_error("circulation:live_session_required");
  require_checkpoint_safe_boundary();
  if (!std::isfinite(horizon) || horizon < now_ || horizon > time_limit_ || budget <= 0)
    throw std::invalid_argument("circulation:invalid_control_horizon");
  int processed=0;
  while (!events_.empty() && events_.top().time <= horizon && processed < budget) {
    runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;
    if (!process_one_event()) break;
    ++processed;
  }
  // Do not advance beyond an unprocessed event on a compute/event budget stop.
  if ((events_.empty() || events_.top().time > horizon) &&
      !result_.summary.event_limit_reached) now_=horizon;
  return processed;
}

inline std::string EventDrivenJunctionRuntime::submit_circulation_transfer(
    CirculationTransfer request, const std::string& owner, bool protocol_internal) {
  if (!circulation_.enabled || runtime_phase_ == EventDrivenJunctionRuntimePhase::kIdle ||
      runtime_phase_ == EventDrivenJunctionRuntimePhase::kFinalized)
    throw std::logic_error("circulation:live_session_required");
  require_checkpoint_safe_boundary();
  if(circulation_.input.owner_protocol.enabled && !protocol_internal)
    return "rejected:protocol_transfer_endpoint_required";
  // Online identifiers cannot collide with unpublished environment-tape IDs.
  // Reject by syntax before any lookup, giving the same result on all futures.
  if(request.request_id.rfind("live:",0)!=0 || request.request_id.size()==5)
    return "rejected:online_request_namespace_required";
  if (request.request_id.empty() || request.source == request.destination ||
      !std::isfinite(request.message_delay) || request.message_delay < 0 ||
      !std::isfinite(request.earliest_departure) || request.earliest_departure < now_ ||
      !std::isfinite(request.expiry) || request.expiry < now_ ||
      !std::isfinite(now_ + request.message_delay)) return "rejected:invalid_transfer";
  if (circulation_.owner(request.source) != owner) return "rejected:resource_owner_mismatch";
  (void)circulation_.node_contract(request.destination);
  const auto visible_tray=std::find_if(circulation_.trays.begin(),circulation_.trays.end(),
                  [&](const auto& t){return t.tray_id==request.tray_id;});
  if (visible_tray==circulation_.trays.end())
    return "rejected:unknown_tray";
  if(circulation_.owner(visible_tray->node)!=owner &&
      !(visible_tray->reception_node>=0 && circulation_.owner(visible_tray->reception_node)==owner))
    return "rejected:tray_not_visible_to_owner";
  for (std::size_t i=0;i<circulation_.input.transfers.size();++i) {
    const auto& old=circulation_.input.transfers[i];
    if (old.request_id == request.request_id) {
      if (old.tray_id != request.tray_id || old.source != request.source ||
          old.destination != request.destination || old.earliest_departure != request.earliest_departure ||
          old.expiry != request.expiry || old.message_delay != request.message_delay)
        return "rejected:request_identity_conflict";
      return "duplicate:"+circulation_.transfers[i].status;
    }
  }
  request.issued_at=now_;
  const int index=static_cast<int>(circulation_.transfers.size());
  circulation_.input.transfers.push_back(std::move(request));
  circulation_.transfers.emplace_back();
  circulation_schedule("module_message",now_+circulation_.input.transfers.back().message_delay,index);
  runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;
  return "pending";
}

inline std::string EventDrivenJunctionRuntime::cancel_circulation_transfer(
    const std::string& id, const std::string& owner,bool protocol_internal) {
  if (!circulation_.enabled || runtime_phase_ == EventDrivenJunctionRuntimePhase::kIdle ||
      runtime_phase_ == EventDrivenJunctionRuntimePhase::kFinalized)
    throw std::logic_error("circulation:live_session_required");
  if(!protocol_internal) require_checkpoint_safe_boundary();
  if(circulation_.input.owner_protocol.enabled && !protocol_internal) return "rejected:owner_protocol_endpoint_required";
  for (std::size_t i=0;i<circulation_.input.transfers.size();++i) {
    const auto& request=circulation_.input.transfers[i];
    if (request.request_id!=id || request.issued_at>now_) continue;
    if(circulation_.owner(request.source)!=owner) return "rejected:resource_owner_mismatch";
    auto& state=circulation_.transfers[i];
    if(state.status=="cancelled") return "duplicate:cancelled";
    if(state.status!="undelivered" && state.status!="pending") return "rejected:already_committed";
    state.status="cancelled"; state.reason="owner_cancelled_uncommitted_intent";
    return "cancelled";
  }
  return "rejected:unknown_request";
}

inline std::string EventDrivenJunctionRuntime::submit_circulation_route(
    CirculationRouteIntent request, double delay,bool protocol_internal) {
  if (!circulation_.enabled || runtime_phase_ == EventDrivenJunctionRuntimePhase::kIdle ||
      runtime_phase_ == EventDrivenJunctionRuntimePhase::kFinalized)
    throw std::logic_error("circulation:live_session_required");
  if(!protocol_internal) require_checkpoint_safe_boundary();
  if(circulation_.input.owner_protocol.enabled && !protocol_internal) return "rejected:owner_protocol_endpoint_required";
  if(request.request_id.empty() || !std::isfinite(delay) || delay<0 ||
      !std::isfinite(request.expiry) || request.expiry<now_ || !std::isfinite(now_+delay))
    return "rejected:invalid_route_request";
  if(circulation_.owner(request.from)!=request.owner_id) return "rejected:resource_owner_mismatch";
  for(const auto& old:circulation_.route_intents)
    if(old.request_id==request.request_id) return "rejected:duplicate_route_request";
  request.status="pending";request.reason.clear();request.delivered_at=now_+delay;
  const int index=static_cast<int>(circulation_.route_intents.size());
  circulation_.route_intents.push_back(std::move(request));
  circulation_schedule("control_route",now_+delay,index);
  runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;
  return "pending";
}

inline std::string EventDrivenJunctionRuntime::publish_circulation_demand(
    const std::string& source, const std::string& target, double delay,bool protocol_internal) {
  if (!circulation_.enabled || runtime_phase_ == EventDrivenJunctionRuntimePhase::kIdle ||
      runtime_phase_ == EventDrivenJunctionRuntimePhase::kFinalized)
    throw std::logic_error("circulation:live_session_required");
  if(!protocol_internal) require_checkpoint_safe_boundary();
  if(circulation_.input.owner_protocol.enabled && !protocol_internal) return "rejected:owner_protocol_endpoint_required";
  if(!circulation_.enabled || !std::isfinite(delay) || delay<0 || !std::isfinite(now_+delay))
    return "rejected:invalid_message";
  bool known_source=false,known_target=false;
  for(const auto& node:circulation_.input.nodes) {
    known_source=known_source||circulation_.owner(node.node)==source;
    known_target=known_target||circulation_.owner(node.node)==target;
  }
  if(!known_source||!known_target) return "rejected:unknown_owner";
  CirculationDemandMessage message;
  auto& channel=circulation_.next_channel_message_id[{source,target}];
  message.message_id=source+":"+target+":"+std::to_string(++channel);
  message.publication_sequence=channel;
  ++circulation_.next_control_id;
  message.source_owner=source;message.target_owner=target;message.observed_at=now_;message.delivered_at=now_+delay;
  for(std::size_t i=0;i<circulation_.jobs.size();++i) {
    const auto& job=circulation_.input.jobs[i];
    if(circulation_.jobs[i].status=="waiting_for_tray" && circulation_.owner(job.origin)==source)
      message.jobs.push_back({job.business_bag_id,job.origin,job.arrival,job.deadline});
  }
  const int index=static_cast<int>(circulation_.demand_messages.size());
  circulation_.demand_messages.push_back(std::move(message));
  circulation_schedule("control_demand",now_+delay,index);
  runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;
  return "pending";
}

inline std::string EventDrivenJunctionRuntime::publish_circulation_service_forecast(
    const std::string& source, const std::string& target, const std::string& tray_id,
    int next_node, double delay,bool protocol_internal) {
  if (!circulation_.enabled || runtime_phase_ == EventDrivenJunctionRuntimePhase::kIdle ||
      runtime_phase_ == EventDrivenJunctionRuntimePhase::kFinalized)
    throw std::logic_error("circulation:live_session_required");
  if(!protocol_internal) require_checkpoint_safe_boundary();
  if(circulation_.input.owner_protocol.enabled && !protocol_internal) return "rejected:owner_protocol_endpoint_required";
  if (!std::isfinite(delay) || delay < 0 || !std::isfinite(now_ + delay))
    return "rejected:invalid_message";
  const auto tray=std::find_if(circulation_.trays.begin(),circulation_.trays.end(),
      [&](const auto& t){return t.tray_id==tray_id;});
  if(tray==circulation_.trays.end() || circulation_.owner(tray->node)!=source)
    return "rejected:tray_not_visible_to_owner";
  if(tray->job<0 || (tray->mode!="loading" && tray->mode!="loaded") || tray->edge_to>=0)
    return "rejected:no_local_uncommitted_loaded_service";
  const auto& job=circulation_.input.jobs.at(tray->job);
  if(circulation_.jobs.at(tray->job).status=="unreleased")
    return "rejected:job_not_observed";
  const int edge=circulation_.edge_index(tray->node,next_node);
  if(edge<0 || !graph_.has_edge(tray->node,next_node)) return "rejected:not_a_directed_edge";
  if(circulation_.owner(next_node)!=target) return "rejected:target_owner_mismatch";
  if(circulation_.input.edges[edge].capacity<=0 || circulation_.node_contract(next_node).capacity<=0)
    return "rejected:static_resource_closed";
  const auto known_fault=advertised_faults_.find(event_runtime_detail::directed_key(tray->node,next_node));
  if(known_fault!=advertised_faults_.end() && known_fault->second.faulted)
    return "rejected:advertised_fault";
  double entry=now_;
  if(tray->mode=="loading") {
    double ready=now_;
    bool observed_start=false;
    for(auto it=circulation_.receipts.rbegin();it!=circulation_.receipts.rend();++it) {
      if(it->tray_id!=tray_id || it->business_bag_id!=job.business_bag_id || it->event!="LOAD_START") continue;
      ready=it->time+job.load_seconds;
      observed_start=true;break;
    }
    if(!observed_start || ready<now_) return "rejected:no_observed_loading_start";
    entry=ready+service_duration(tray->node);
  } else {
    const auto bag=bags_.find(tray->active_leg);
    if(bag==bags_.end() || bag->second.current!=tray->node)
      return "rejected:no_local_service_state";
    if(bag->second.status==BagStatus::kInService) {
      // Source admission and destination reservations are already committed
      // local physical state. Do not add the full service again at capture.
      // Purged intervals have completed; the remaining service is then zero.
      entry=junctions_.at(tray->node).service_calendar.task_service_end(tray->active_leg,now_);
    } else if(bag->second.status!=BagStatus::kJunctionQueue) {
      return "rejected:no_committed_local_service";
    }
  }
  const double release=entry+std::max(graph_.edge(tray->node,next_node).travel_time(),
                                    config_.minimum_service_seconds)+service_duration(next_node);
  if(!std::isfinite(entry) || !std::isfinite(release)) return "rejected:nonfinite_estimate";
  CirculationServiceForecast message;
  auto& channel=circulation_.next_channel_message_id[{source,target}];
  message.message_id=source+":"+target+":service:"+std::to_string(++channel);
  message.publication_sequence=channel;
  message.source_owner=source;message.target_owner=target;message.tray_id=tray_id;
  message.business_bag_id=job.business_bag_id;message.from=tray->node;message.next=next_node;
  message.generation=tray->generation;message.traversal_id=tray->public_traversal_version;
  message.observed_at=now_;message.delivered_at=now_+delay;
  message.entry_estimate=entry;message.release_estimate=release;
  const int index=static_cast<int>(circulation_.service_forecasts.size());
  circulation_.service_forecasts.push_back(std::move(message));
  circulation_schedule("control_service_forecast",now_+delay,index);
  ++circulation_.next_control_id;
  runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;
  return "pending";
}

inline std::string EventDrivenJunctionRuntime::withdraw_circulation_service_forecast(
    const std::string& source,const std::string& original_message_id,double delay,bool protocol_internal) {
  if (!circulation_.enabled || runtime_phase_==EventDrivenJunctionRuntimePhase::kIdle ||
      runtime_phase_==EventDrivenJunctionRuntimePhase::kFinalized)
    throw std::logic_error("circulation:live_session_required");
  if(!protocol_internal) require_checkpoint_safe_boundary();
  if(circulation_.input.owner_protocol.enabled && !protocol_internal) return "rejected:owner_protocol_endpoint_required";
  if(!std::isfinite(delay) || delay<0 || !std::isfinite(now_+delay)) return "rejected:invalid_message";
  const auto original=std::find_if(circulation_.service_forecasts.begin(),circulation_.service_forecasts.end(),
      [&](const auto& m){return m.message_id==original_message_id && m.source_owner==source && m.status=="conditional";});
  if(original==circulation_.service_forecasts.end()) return "rejected:unknown_owned_forecast";
  for(const auto& m:circulation_.service_forecasts)
    if(m.source_owner==source && m.status=="withdrawn" && m.supersedes==original_message_id)
      return m.delivered ? "duplicate:withdrawal_delivered" : "duplicate:withdrawal_pending";
  // The immutable tombstone concerns a soft estimate only; no transfer, lease,
  // physical task or incoming reception commitment is changed by withdrawal.
  auto message=*original;
  auto& channel=circulation_.next_channel_message_id[{source,message.target_owner}];
  message.message_id=source+":"+message.target_owner+":service:"+std::to_string(++channel);
  message.publication_sequence=channel;
  message.observed_at=now_;message.delivered_at=now_+delay;message.delivered=false;
  message.status="withdrawn";message.supersedes=original_message_id;
  const int index=static_cast<int>(circulation_.service_forecasts.size());
  circulation_.service_forecasts.push_back(std::move(message));
  circulation_schedule("control_service_forecast",now_+delay,index);
  ++circulation_.next_control_id;
  runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;
  return "pending";
}

inline std::string EventDrivenJunctionRuntime::request_circulation_empty_recovery(
    CirculationRecoveryIntent request, double delay) {
  if (!circulation_.enabled || runtime_phase_ == EventDrivenJunctionRuntimePhase::kIdle ||
      runtime_phase_ == EventDrivenJunctionRuntimePhase::kFinalized)
    throw std::logic_error("circulation:live_session_required");
  require_checkpoint_safe_boundary();
  if(request.request_id.empty() || !std::isfinite(delay) || delay<0 || !std::isfinite(now_+delay))
    return "rejected:invalid_recovery";
  const auto tray=std::find_if(circulation_.trays.begin(),circulation_.trays.end(),
      [&](const auto& t){return t.tray_id==request.tray_id;});
  if(tray==circulation_.trays.end() || circulation_.owner(tray->node)!=request.owner_id)
    return "rejected:resource_owner_mismatch";
  for(const auto& old:circulation_.recovery_intents)
    if(old.request_id==request.request_id) return "rejected:duplicate_recovery";
  request.expected_generation=tray->generation;request.delivered_at=now_+delay;
  request.status="pending";request.reason.clear();
  const int index=static_cast<int>(circulation_.recovery_intents.size());
  circulation_.recovery_intents.push_back(std::move(request));
  circulation_schedule("control_recover_empty",now_+delay,index);
  runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;
  return "pending";
}

inline std::vector<std::tuple<int,int,bool,double>> EventDrivenJunctionRuntime::circulation_known_faults(
    const std::string& owner) const {
  std::vector<std::tuple<int,int,bool,double>> visible;
  for(const auto& edge:circulation_.input.edges) {
    if(circulation_.owner(edge.from)!=owner) continue;
    const auto it=advertised_faults_.find(event_runtime_detail::directed_key(edge.from,edge.to));
    if(it!=advertised_faults_.end()) visible.emplace_back(edge.from,edge.to,it->second.faulted,it->second.received_at);
  }
  return visible;
}

} // namespace czr005::ics
