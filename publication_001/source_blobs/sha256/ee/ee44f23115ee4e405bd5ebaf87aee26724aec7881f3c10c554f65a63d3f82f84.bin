#pragma once

namespace czr005::ics {

inline bool EventDrivenJunctionRuntime::circulation_protocol_owner_available(const std::string& owner) const {
  // Closing a half-open outage window is effective at its native timestamp,
  // even if a same-time physical phase runs before the outage bookkeeping
  // event. Opening still requires the actual recovery event to clear the
  // down count. This prevents phase-order and adjacent-window grant gaps.
  for(const auto& outage:circulation_.input.owner_protocol.outages)
    if(outage.owner==owner && outage.start<=now_ && now_<outage.end) return false;
  const auto found=circulation_.protocol_owner_down.find(owner);
  return found==circulation_.protocol_owner_down.end() || found->second==0;
}
inline bool EventDrivenJunctionRuntime::circulation_protocol_transfer_available(int index) const {
  if(!circulation_.input.owner_protocol.enabled) return true;
  const auto& request=circulation_.input.transfers.at(index);
  return circulation_protocol_owner_available(circulation_.owner(request.source)) &&
         circulation_protocol_owner_available(circulation_.owner(request.destination));
}

inline std::string EventDrivenJunctionRuntime::submit_circulation_protocol_transfer(
    CirculationTransfer request,const std::string& owner) {
  auto timing_admission = request_timing_.scoped(TimingPhase::admission);
  if(!circulation_.input.owner_protocol.enabled) return "rejected:owner_protocol_not_enabled";
  require_checkpoint_safe_boundary();
  if(runtime_phase_==EventDrivenJunctionRuntimePhase::kIdle ||
     runtime_phase_==EventDrivenJunctionRuntimePhase::kFinalized)
    throw std::logic_error("circulation:live_session_required");
  const std::string owner_prefix="live:"+std::to_string(owner.size())+":"+owner+":";
  if(request.request_id.rfind(owner_prefix,0)!=0 || request.request_id.size()<=owner_prefix.size())
    return "rejected:owner_request_namespace_required";
  if(circulation_.owner(request.source)!=owner) return "rejected:resource_owner_mismatch";
  for(const auto& command:circulation_.protocol_commands)
    if(command.input.request_id==request.request_id) return "rejected:request_identity_conflict";
  // Match a client-owned immutable payload before time/physical-tray checks:
  // an exact retry after departure or expiry must not allocate another tray.
  for(std::size_t i=0;i<circulation_.protocol_requests.size();++i) {
    auto& known=circulation_.protocol_requests[i];
    const auto& old=circulation_.input.transfers[known.transfer];
    if(old.request_id!=request.request_id) continue;
    if(known.owner!=owner) return "rejected:request_not_owned";
    if(old.tray_id!=request.tray_id || old.source!=request.source || old.destination!=request.destination ||
       old.earliest_departure!=request.earliest_departure || old.expiry!=request.expiry ||
       old.message_delay!=request.message_delay || old.transfer_scope!=request.transfer_scope)
      return "rejected:request_identity_conflict";
    if(!std::isfinite(now_+old.message_delay) || !std::isfinite(now_+circulation_.input.owner_protocol.timeout))
      return "rejected:invalid_protocol_time";
    ++known.attempt;known.client_status="pending";
    circulation_schedule("protocol_resend",now_+old.message_delay,static_cast<int>(i),known.attempt);
    circulation_schedule("protocol_timeout",now_+circulation_.input.owner_protocol.timeout,static_cast<int>(i),known.attempt);
    runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;
    return "pending:retry_enqueued";
  }
  if(!std::isfinite(now_+circulation_.input.owner_protocol.timeout)) return "rejected:invalid_protocol_time";
  const auto visible=std::find_if(circulation_.trays.begin(),circulation_.trays.end(),[&](const auto& tray) {
    return tray.tray_id==request.tray_id && circulation_.owner(tray.node)==owner;
  });
  if(visible==circulation_.trays.end()) return "rejected:tray_not_locally_visible";
  const int physical=static_cast<int>(circulation_.transfers.size());
  const auto reply=submit_circulation_transfer(std::move(request),owner,true);
  if(reply!="pending") return reply;
  CirculationProtocolRequest client;client.transfer=physical;client.owner=owner;
  client.remaining_ack_drops=circulation_.input.owner_protocol.drop_ack_packets;
  const int index=static_cast<int>(circulation_.protocol_requests.size());
  circulation_.protocol_requests.push_back(std::move(client));
  circulation_schedule("protocol_timeout",now_+circulation_.input.owner_protocol.timeout,index,1);
  return "pending:request_enqueued";
}

inline void EventDrivenJunctionRuntime::circulation_protocol_send_ack(int index,double time,std::uint64_t attempt) {
  const auto& config=circulation_.input.owner_protocol;
  const double delivered=time+config.ack_delay;
  const double duplicated=delivered+config.duplicate_ack_delay;
  if(!std::isfinite(delivered) || !std::isfinite(duplicated))
    throw std::invalid_argument("circulation:nonfinite_protocol_ack_time");
  auto& client=circulation_.protocol_requests.at(index);
  auto timing_ack = request_timing_.scoped(TimingPhase::ack_create,
      {TimingIdentity::transfer, client.transfer, attempt ? attempt : client.attempt}, TimingMethod::none, 0, time);
  const auto& physical=circulation_.transfers.at(client.transfer);
  CirculationProtocolAck ack;ack.request=index;ack.sequence=client.next_ack_sequence++;
  ack.attempt=attempt ? attempt : client.attempt;
  ack.observed_at=time;ack.status=physical.status;ack.reason=physical.reason;
  if(physical.status=="received") ack.received_at=physical.received_at;
  const int ai=static_cast<int>(circulation_.protocol_acks.size());
  circulation_.protocol_acks.push_back(std::move(ack));
  circulation_schedule("protocol_ack",delivered,ai);
  if(config.duplicate_acks)
    circulation_schedule("protocol_ack",duplicated,ai);
}

inline bool EventDrivenJunctionRuntime::process_circulation_protocol_event(const RuntimeEvent& event) {
  const double time=event.time;
  if(event.reason=="protocol_owner_down" || event.reason=="protocol_owner_up") {
    auto timing_recovery = request_timing_.scoped(TimingPhase::recovery, {}, TimingMethod::none, event.seq, time);
    const auto& outage=circulation_.input.owner_protocol.outages.at(event.task_id);
    auto& count=circulation_.protocol_owner_down[outage.owner];
    count+=event.reason=="protocol_owner_down" ? 1 : -1;
    if(count<0) throw std::logic_error("circulation:owner_outage_generation_corrupt");
    CirculationReceipt receipt;receipt.time=time;receipt.event=event.reason=="protocol_owner_down" ?
        "PROTOCOL_OWNER_UNAVAILABLE" : "PROTOCOL_OWNER_RECOVERED";receipt.reason=outage.owner;
    circulation_.receipts.push_back(std::move(receipt));
    if(count==0) {
      for(std::size_t i=0;i<circulation_.protocol_requests.size();++i) {
        auto& request=circulation_.protocol_requests[i];
        if(request.waiting_for_owner && circulation_protocol_transfer_available(request.transfer)) {
          request.waiting_for_owner=false;
          circulation_schedule("protocol_resend",time,static_cast<int>(i),request.waiting_attempt);
        }
      }
      for(std::size_t i=0;i<circulation_.protocol_commands.size();++i) {
        auto& command=circulation_.protocol_commands[i];
        if(command.waiting_for_owner && circulation_protocol_owner_available(command.input.owner)) {
          command.waiting_for_owner=false;
          circulation_schedule("protocol_command_wire",time,static_cast<int>(i),command.waiting_attempt);
        }
        if(command.waiting_for_recipient) {
          const std::string kind=command.input.kind=="withdraw_service_forecast" ? "service_forecast" : command.input.kind;
          if(circulation_protocol_publication_available(kind,command.native_index)) {
            command.waiting_for_recipient=false;
            circulation_schedule("control_"+kind,time,command.native_index);
          }
        }
      }
      // Pending uncommitted requests can resume only at this actual recovery.
      // Existing traversals/receiving leases never depended on module uptime.
      circulation_progress(time);
    }
    return true;
  }
  if(event.reason=="protocol_timeout") {
    auto& request=circulation_.protocol_requests.at(event.task_id);
    auto timing_timeout = request_timing_.scoped(TimingPhase::timeout,
        {TimingIdentity::transfer, request.transfer, event.wakeup_generation}, TimingMethod::none, event.seq, time);
    if(event.wakeup_generation==request.attempt && request.delivered_attempt<request.attempt && request.client_status!="timeout_unknown") {
      request.client_status="timeout_unknown";
      circulation_.notify_owner(request.owner,now_,32);
    }
    return true;
  }
  if(event.reason=="protocol_resend") {
    auto& client=circulation_.protocol_requests.at(event.task_id);
    auto timing_retry = request_timing_.scoped(TimingPhase::retry,
        {TimingIdentity::transfer, client.transfer, event.wakeup_generation}, TimingMethod::none, event.seq, time);
    if(!circulation_protocol_transfer_available(client.transfer)) {
      client.waiting_for_owner=true;
      client.waiting_attempt=std::max(client.waiting_attempt,event.wakeup_generation);return true;
    }
    if(circulation_.transfers.at(client.transfer).status=="undelivered")
      circulation_schedule("module_message",time,client.transfer,event.wakeup_generation);
    else circulation_protocol_send_ack(event.task_id,time,event.wakeup_generation);
    return true;
  }
  if(event.reason=="protocol_ack") {
    auto& ack=circulation_.protocol_acks.at(event.task_id);
    auto& client=circulation_.protocol_requests.at(ack.request);
    auto timing_ack = request_timing_.scoped(TimingPhase::ack_delivery,
        {TimingIdentity::transfer, client.transfer, ack.attempt}, TimingMethod::none, event.seq, time);
    CirculationReceipt row;row.time=time;
    row.reason=circulation_.input.transfers.at(client.transfer).request_id+":"+std::to_string(ack.sequence);
    if(client.remaining_ack_drops>0) {
      --client.remaining_ack_drops;++ack.dropped_copies;row.event="PROTOCOL_ACK_DROPPED";
    } else {
      ++ack.delivered_copies;
      if(ack.delivered_at<0) ack.delivered_at=time;
      row.event="PROTOCOL_ACK_DELIVERED";
      if(ack.sequence>client.delivered_ack_sequence) {
        client.delivered_ack_sequence=ack.sequence;client.latest_ack=event.task_id;
      }
      client.delivered_attempt=std::max(client.delivered_attempt,ack.attempt);
      if(client.delivered_attempt>=client.attempt) client.client_status="acknowledged";
      circulation_.notify_owner(client.owner,now_,16);
    }
    circulation_.receipts.push_back(std::move(row));
    return true;
  }
  return process_circulation_protocol_command_event(event);
}

} // namespace czr005::ics
