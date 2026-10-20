#pragma once

namespace czr005::ics {

inline std::string EventDrivenJunctionRuntime::submit_circulation_protocol_command(CirculationProtocolCommandInput input) {
  auto timing_admission = request_timing_.scoped(TimingPhase::admission);
  if(!circulation_.input.owner_protocol.enabled) return "rejected:owner_protocol_not_enabled";
  require_checkpoint_safe_boundary();
  if(runtime_phase_==EventDrivenJunctionRuntimePhase::kIdle || runtime_phase_==EventDrivenJunctionRuntimePhase::kFinalized)
    throw std::logic_error("circulation:live_session_required");
  const auto prefix="live:"+std::to_string(input.owner.size())+":"+input.owner+":";
  if(input.request_id.rfind(prefix,0)!=0 || input.request_id.size()<=prefix.size()) return "rejected:owner_request_namespace_required";
  bool known=false,target_known=false;
  for(const auto& node:circulation_.input.nodes) {
    known=known || circulation_.owner(node.node)==input.owner;
    target_known=target_known || circulation_.owner(node.node)==input.target_owner;
  }
  if(!known) return "rejected:unknown_owner";
  const bool publication=input.kind=="demand" || input.kind=="service_forecast" || input.kind=="planning_snapshot" || input.kind=="planning_snapshot_v2" || input.kind=="planning_snapshot_v3";
  if(input.kind!="route" && !publication && input.kind!="withdraw_service_forecast" && input.kind!="cancel_transfer" &&
     input.kind!="recover_failed_empty")
    return "rejected:unknown_command_kind";
  if(publication && !target_known) return "rejected:unknown_target_owner";
  if(!std::isfinite(input.message_delay) || input.message_delay<0 || !std::isfinite(input.publication_delay) ||
     input.publication_delay<0 || !std::isfinite(input.expiry) || !std::isfinite(now_+input.message_delay) ||
     !std::isfinite(now_+circulation_.input.owner_protocol.timeout)) return "rejected:invalid_command_time";
  if(input.kind=="route" && circulation_.owner(input.from)!=input.owner) return "rejected:resource_owner_mismatch";
  if(input.kind=="withdraw_service_forecast" && input.reference_id.empty()==input.reference_request_id.empty())
    return "rejected:withdraw_requires_one_exact_reference";
  if(input.kind=="cancel_transfer" && input.reference_id.empty()) return "rejected:missing_transfer_reference";
  if(input.kind=="cancel_transfer" && input.reference_id.rfind(prefix,0)!=0)
    return "rejected:reference_not_owned";
  if(input.kind=="recover_failed_empty" &&
     (input.tray_id.empty() || input.reference_id.empty() || input.reference_request_id.empty() || input.from<0))
    return "rejected:missing_failed_empty_binding";
  if(input.kind=="recover_failed_empty" && input.reference_id.rfind(prefix,0)!=0)
    return "rejected:reference_not_owned";
  for(const auto& transfer:circulation_.protocol_requests)
    if(circulation_.input.transfers[transfer.transfer].request_id==input.request_id)
      return "rejected:request_identity_conflict";
  const auto identity=[](const auto& p) {
    return std::tie(p.request_id,p.owner,p.kind,p.target_owner,p.tray_id,p.business_bag_id,p.reference_id,
                    p.reference_request_id,p.from,p.next,p.expected_generation,p.expected_traversal,
                    p.message_delay,p.publication_delay,p.expiry);
  };
  for(std::size_t i=0;i<circulation_.protocol_commands.size();++i) {
    auto& command=circulation_.protocol_commands[i];
    if(command.input.request_id!=input.request_id) continue;
    if(identity(command.input)!=identity(input)) return "rejected:request_identity_conflict";
    ++command.attempt;command.client_status="pending";
    circulation_schedule("protocol_command_wire",now_+input.message_delay,static_cast<int>(i),command.attempt);
    circulation_schedule("protocol_command_timeout",now_+circulation_.input.owner_protocol.timeout,static_cast<int>(i),command.attempt);
    runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;return "pending:retry_enqueued";
  }
  CirculationProtocolCommand command;command.input=std::move(input);
  command.remaining_ack_drops=circulation_.input.owner_protocol.drop_ack_packets;
  const int index=static_cast<int>(circulation_.protocol_commands.size());
  circulation_.protocol_commands.push_back(std::move(command));
  circulation_schedule("protocol_command_wire",now_+circulation_.protocol_commands.back().input.message_delay,index,1);
  circulation_schedule("protocol_command_timeout",now_+circulation_.input.owner_protocol.timeout,index,1);
  runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;return "pending:command_enqueued";
}

inline void EventDrivenJunctionRuntime::circulation_protocol_command_ack(int index,double time,std::uint64_t attempt) {
  auto timing_ack = request_timing_.scoped(TimingPhase::ack_create,
      {TimingIdentity::command, index, attempt}, TimingMethod::none, 0, time);
  const auto& config=circulation_.input.owner_protocol;
  const double delivered=time+config.ack_delay,duplicate=delivered+config.duplicate_ack_delay;
  if(!std::isfinite(delivered) || !std::isfinite(duplicate)) throw std::invalid_argument("circulation:nonfinite_protocol_ack_time");
  auto& command=circulation_.protocol_commands.at(index);
  CirculationProtocolCommandAck ack;ack.command=index;ack.sequence=command.next_ack_sequence++;
  ack.attempt=attempt;ack.observed_at=time;ack.executed_at=command.executed_at;ack.completed_at=command.completed_at;
  ack.status=command.result_status;ack.reason=command.reason;ack.result_id=command.result_id;
  const int ai=static_cast<int>(circulation_.protocol_command_acks.size());
  circulation_.protocol_command_acks.push_back(std::move(ack));
  circulation_schedule("protocol_command_ack",delivered,ai);
  if(config.duplicate_acks) circulation_schedule("protocol_command_ack",duplicate,ai);
}

inline void EventDrivenJunctionRuntime::circulation_protocol_command_complete(const std::string& kind,int native_index,
    const std::string& status,const std::string& reason,const std::string& result_id,double time) {
  auto timing_scan = request_timing_.scoped(TimingPhase::shared_scan, {}, TimingMethod::none, 0, time);
  if(!circulation_.input.owner_protocol.enabled) return;
  for(std::size_t i=0;i<circulation_.protocol_commands.size();++i) {
    auto& command=circulation_.protocol_commands[i];
    const bool same_kind=command.input.kind==kind || (kind=="service_forecast" && command.input.kind=="withdraw_service_forecast");
    if(!same_kind || command.native_index!=native_index || command.execution_status!="processing") continue;
    auto timing_complete = request_timing_.scoped(TimingPhase::outcome_update,
        {TimingIdentity::command, static_cast<std::int64_t>(i), command.arrived_attempt}, TimingMethod::none, 0, time);
    command.execution_status="completed";command.result_status=status;command.reason=reason;
    command.result_id=result_id;command.completed_at=time;
    circulation_protocol_command_ack(static_cast<int>(i),time,command.arrived_attempt);
  }
}

inline bool EventDrivenJunctionRuntime::circulation_protocol_publication_available(const std::string& kind,int index) {
  if(!circulation_.input.owner_protocol.enabled) return true;
  const auto& target=kind=="route" ? circulation_.route_intents.at(index).owner_id :
      (kind=="demand" ? circulation_.demand_messages.at(index).target_owner :
       (kind=="planning_snapshot" ? circulation_.planning_snapshots.at(index).target_owner :
        (kind=="planning_snapshot_v2" ? circulation_.planning_snapshots_v2.at(index).target_owner :
         (kind=="planning_snapshot_v3" ? circulation_.planning_snapshots_v3.at(index).target_owner :
          circulation_.service_forecasts.at(index).target_owner))));
  if(circulation_protocol_owner_available(target)) return true;
  for(auto& command:circulation_.protocol_commands) {
    const bool same_kind=command.input.kind==kind || (kind=="service_forecast" && command.input.kind=="withdraw_service_forecast");
    if(same_kind && command.native_index==index && command.execution_status=="processing") command.waiting_for_recipient=true;
  }
  return false;
}

inline bool EventDrivenJunctionRuntime::process_circulation_protocol_command_event(const RuntimeEvent& event) {
  const double time=event.time;
  if(event.reason=="protocol_command_timeout") {
    auto timing_timeout = request_timing_.scoped(TimingPhase::timeout,
        {TimingIdentity::command, event.task_id, event.wakeup_generation}, TimingMethod::none, event.seq, time);
    auto& command=circulation_.protocol_commands.at(event.task_id);
    if(command.attempt==event.wakeup_generation && command.delivered_attempt<command.attempt && command.client_status!="timeout_unknown") {
      command.client_status="timeout_unknown";
      circulation_.notify_owner(command.input.owner,now_,32);
    }
    return true;
  }
  if(event.reason=="protocol_command_ack") {
    auto& ack=circulation_.protocol_command_acks.at(event.task_id);
    auto timing_ack = request_timing_.scoped(TimingPhase::ack_delivery,
        {TimingIdentity::command, ack.command, ack.attempt}, TimingMethod::none, event.seq, time);
    auto& command=circulation_.protocol_commands.at(ack.command);
    CirculationReceipt receipt;receipt.time=time;receipt.reason=command.input.request_id+":"+std::to_string(ack.sequence);
    if(command.remaining_ack_drops>0) {
      --command.remaining_ack_drops;++ack.dropped_copies;receipt.event="PROTOCOL_COMMAND_ACK_DROPPED";
    } else {
      ++ack.delivered_copies;if(ack.delivered_at<0) ack.delivered_at=time;
      receipt.event="PROTOCOL_COMMAND_ACK_DELIVERED";
      if(ack.sequence>command.delivered_ack_sequence) {command.delivered_ack_sequence=ack.sequence;command.latest_ack=event.task_id;}
      command.delivered_attempt=std::max(command.delivered_attempt,ack.attempt);
      if(command.delivered_attempt>=command.attempt) command.client_status="acknowledged";
      circulation_.notify_owner(command.input.owner,now_,16);
    }
    circulation_.receipts.push_back(std::move(receipt));return true;
  }
  if(event.reason!="protocol_command_wire") return false;
  auto timing_execute = request_timing_.scoped(TimingPhase::source_execution,
      {TimingIdentity::command, event.task_id, event.wakeup_generation}, TimingMethod::none, event.seq, time);
  auto& command=circulation_.protocol_commands.at(event.task_id);
  const auto& input=command.input;
  command.arrived_attempt=std::max(command.arrived_attempt,event.wakeup_generation);
  if(!circulation_protocol_owner_available(input.owner)) {
    command.waiting_for_owner=true;command.waiting_attempt=std::max(command.waiting_attempt,event.wakeup_generation);return true;
  }
  if(command.execution_status!="enqueued") {
    circulation_protocol_command_ack(event.task_id,time,event.wakeup_generation);return true;
  }
  command.execution_status="processing";command.executed_at=time;
  std::string response;
  if(input.kind=="route") {
    CirculationRouteIntent route;route.request_id=input.request_id;route.owner_id=input.owner;route.tray_id=input.tray_id;
    route.business_bag_id=input.business_bag_id;route.from=input.from;route.next=input.next;
    route.expected_generation=input.expected_generation;route.expected_traversal=input.expected_traversal;route.expiry=input.expiry;
    command.native_index=static_cast<int>(circulation_.route_intents.size());
    response=submit_circulation_route(std::move(route),0,true);
  } else if(input.kind=="demand") {
    command.native_index=static_cast<int>(circulation_.demand_messages.size());
    response=publish_circulation_demand(input.owner,input.target_owner,input.publication_delay,true);
    if(response=="pending") command.result_id=circulation_.demand_messages.back().message_id;
  } else if(input.kind=="service_forecast") {
    command.native_index=static_cast<int>(circulation_.service_forecasts.size());
    response=publish_circulation_service_forecast(input.owner,input.target_owner,input.tray_id,input.next,input.publication_delay,true);
    if(response=="pending") command.result_id=circulation_.service_forecasts.back().message_id;
  } else if(input.kind=="planning_snapshot") {
    command.native_index=static_cast<int>(circulation_.planning_snapshots.size());
    response=publish_circulation_planning_snapshot(input.owner,input.target_owner,input.publication_delay,input.expiry);
    if(response=="pending") command.result_id=circulation_.planning_snapshots.back().message_id;
  } else if(input.kind=="planning_snapshot_v2") {
    command.native_index=static_cast<int>(circulation_.planning_snapshots_v2.size());
    response=publish_circulation_planning_snapshot(input.owner,input.target_owner,input.publication_delay,input.expiry,true);
    if(response=="pending") command.result_id=circulation_.planning_snapshots_v2.back().message_id;
  } else if(input.kind=="planning_snapshot_v3") {
    command.native_index=static_cast<int>(circulation_.planning_snapshots_v3.size());
    response=publish_circulation_planning_snapshot(input.owner,input.target_owner,input.publication_delay,input.expiry,true,true);
    if(response=="pending") command.result_id=circulation_.planning_snapshots_v3.back().message_id;
  } else if(input.kind=="withdraw_service_forecast") {
    std::string original=input.reference_id;
    if(!input.reference_request_id.empty()) {
      for(const auto& old:circulation_.protocol_commands)
        if(old.input.request_id==input.reference_request_id && old.input.owner==input.owner && old.input.kind=="service_forecast" &&
           old.native_index>=0 && old.execution_status!="enqueued" && old.result_status!="rejected") original=old.result_id;
    }
    if(original.empty()) response="rejected:original_forecast_not_executed";
    else {
      response=withdraw_circulation_service_forecast(input.owner,original,input.publication_delay,true);
      for(std::size_t i=0;i<circulation_.service_forecasts.size();++i) {
        const auto& message=circulation_.service_forecasts[i];
        if(message.source_owner==input.owner && message.status=="withdrawn" && message.supersedes==original) {
          command.native_index=static_cast<int>(i);command.result_id=message.message_id;
          if(message.delivered) response="delivered";
          else if(response.rfind("duplicate:",0)==0) response="pending";
          break;
        }
      }
    }
  } else if(input.kind=="cancel_transfer") {
    response=cancel_circulation_transfer(input.reference_id,input.owner,true);command.result_id=input.reference_id;
    if(response=="duplicate:cancelled") response="cancelled";
  } else if(input.kind=="recover_failed_empty") {
    response=circulation_recover_failed_empty(input,time);command.result_id=input.reference_id;
  }
  if(response=="pending") {
    command.result_status=input.kind=="route" ? "pending_execution" : "pending_delivery";
    // The peer delivery or true route validation event will produce the final
    // ACK. A stable retry while waiting may return this honest pending state.
    return true;
  }
  const auto colon=response.find(':');
  command.result_status=response.substr(0,colon);
  command.reason=colon==std::string::npos ? "" : response.substr(colon+1);
  command.execution_status="completed";command.completed_at=time;
  circulation_protocol_command_ack(event.task_id,time,event.wakeup_generation);
  return true;
}

} // namespace czr005::ics
