#pragma once

namespace czr005::ics {

inline std::string EventDrivenJunctionRuntime::publish_circulation_planning_snapshot(
    const std::string& source,const std::string& target,double delay,double valid_until,bool version2,bool version3) {
  if(!circulation_.enabled || !circulation_.input.owner_protocol.enabled ||
      runtime_phase_==EventDrivenJunctionRuntimePhase::kIdle ||
      runtime_phase_==EventDrivenJunctionRuntimePhase::kFinalized)
    throw std::logic_error("circulation:live_protocol_session_required");
  if(!std::isfinite(delay) || delay<0 || !std::isfinite(now_+delay) || !std::isfinite(valid_until))
    return "rejected:invalid_planning_snapshot_time";
  bool source_known=false,target_known=false;
  for(const auto& node:circulation_.input.nodes) {
    source_known=source_known || circulation_.owner(node.node)==source;
    target_known=target_known || circulation_.owner(node.node)==target;
  }
  if(!source_known || !target_known) return "rejected:unknown_owner";
  if(now_>=valid_until) return "expired:planning_capture_expired";

  // Deliberately enumerate only public static contracts. Never hash the full
  // input/checkpoint: they include unreleased jobs and private fault schedules.
  StateFingerprintWriter contract("g31.planning_static_contract.v1");
  contract.string(config_.queue_discipline);contract.string(config_.resource_semantics);
  contract.string(config_.event_semantics);contract.string(config_.scorer_mode);
  contract.string(config_.merge_grant_rule);contract.string(config_.merge_grant_timing_mode);
  contract.floating(config_.minimum_service_seconds);contract.i64(config_.max_decisions_per_bag);
  const auto node_ids=graph_.node_locations();contract.u64(node_ids.size());
  for(int id:node_ids) {
    const auto& n=graph_.node(id);
    contract.i64(n.location);contract.i64(n.node_type);contract.floating(n.service_time);
    contract.floating(n.x);contract.floating(n.y);contract.u64(n.outgoing.size());
    for(int next:n.outgoing) contract.i64(next);
  }
  contract.u64(circulation_.input.nodes.size());
  for(const auto& n:circulation_.input.nodes) {
    contract.i64(n.node);contract.string(n.zone);contract.string(circulation_.partition(n.node));
    contract.string(circulation_.owner(n.node));contract.i64(n.capacity);contract.i64(n.export_min_stock);
    contract.boolean(n.allow_export);contract.boolean(n.allow_receive);
  }
  contract.u64(circulation_.input.edges.size());
  for(const auto& e:circulation_.input.edges) {
    const auto& physical=graph_.edge(e.from,e.to);
    contract.i64(e.from);contract.i64(e.to);contract.i64(e.capacity);contract.floating(e.entry_headway);
    contract.floating(physical.length);contract.floating(physical.speed);
  }

  CirculationPlanningSnapshot message;
  message.source_owner=source;message.target_owner=target;message.captured_at=now_;message.valid_until=valid_until;
  message.static_contract_sha256=contract.sha256();message.queue_discipline=config_.queue_discipline;
  message.resource_semantics=config_.resource_semantics;message.event_semantics=config_.event_semantics;
  message.scorer_mode=config_.scorer_mode;message.merge_grant_rule=config_.merge_grant_rule;
  message.merge_grant_timing_mode=config_.merge_grant_timing_mode;
  message.minimum_service_seconds=config_.minimum_service_seconds;
  std::set<int> visible_jobs;
  for(const auto& t:circulation_.trays) {
    if(circulation_.owner(t.node)!=source) continue;
    CirculationPlanningTray row;
    row.tray_id=t.tray_id;row.node=t.node;row.mode=t.mode;row.edge_from=t.edge_from;row.edge_to=t.edge_to;
    row.reception_node=t.reception_node;row.generation=t.generation;row.traversal_id=t.public_traversal_version;
    row.available_at=t.available_at;
    if(t.job>=0) {
      visible_jobs.insert(t.job);row.business_bag_id=circulation_.input.jobs.at(t.job).business_bag_id;
    }
    if(t.active_leg>=0) {
      const auto& leg=circulation_.legs.at(t.active_leg);
      for(const auto& receipt:circulation_.receipts) if(receipt.transport_leg_id==leg.transport_leg_id) {
        if(receipt.event=="LEG_START") row.committed_prefix.push_back(receipt.from);
        else if(receipt.event=="EDGE_EXIT") row.committed_prefix.push_back(receipt.to);
      }
    }
    if(row.committed_prefix.empty()) row.committed_prefix.push_back(t.node);
    if(t.edge_to<0) {
      if(t.mode=="empty" && t.active_leg<0) {
        row.service_ready_known=true;row.service_ready_at=t.available_at;row.ready_kind="empty_available_at";
      } else if(t.mode=="hold") {
        row.service_ready_known=true;row.service_ready_at=t.available_at;row.ready_kind="observed_hold_completion";
      } else if(t.job>=0 && t.mode=="storage") {
        const auto& job=circulation_.input.jobs.at(t.job);
        row.service_ready_at=std::max({now_,job.storage_release_at,t.storage_arrived_at+job.storage_min_dwell});
        row.service_ready_known=true;row.ready_kind="observed_storage_release_bound";
      } else if(t.job>=0 && (t.mode=="loading" || t.mode=="unloading")) {
        const auto& job=circulation_.input.jobs.at(t.job);
        const std::string start=t.mode=="loading" ? "LOAD_START" : "UNLOAD_START";
        for(auto it=circulation_.receipts.rbegin();it!=circulation_.receipts.rend();++it) {
          if(it->tray_id!=t.tray_id || it->business_bag_id!=job.business_bag_id || it->event!=start) continue;
          row.service_ready_at=it->time+(t.mode=="loading" ? job.load_seconds : job.unload_seconds);
          row.available_at=row.service_ready_at;row.service_ready_known=true;
          row.ready_kind=t.mode=="loading" ? "observed_load_completion" : "observed_unload_completion";
          if(t.mode=="loading") row.load_complete_at=row.service_ready_at;
          break;
        }
      } else if(t.mode=="loaded" && t.active_leg>=0) {
        const auto bag=bags_.find(t.active_leg);
        if(bag!=bags_.end() && bag->second.current==t.node && bag->second.status==BagStatus::kInService) {
          row.service_ready_at=junctions_.at(t.node).service_calendar.task_service_end(t.active_leg,now_);
          row.service_ready_known=true;row.ready_kind="committed_local_service_end";
        }
        // A queue entry alone gives no exact committed departure/clearance.
      }
    }
    if(!std::isfinite(row.service_ready_at)) {
      row.service_ready_at=-1;row.service_ready_known=false;row.ready_kind="unknown";
    }
    message.trays.push_back(std::move(row));
  }
  for(std::size_t i=0;i<circulation_.jobs.size();++i) {
    const auto& state=circulation_.jobs[i];const auto& job=circulation_.input.jobs[i];
    if(state.status=="unreleased") continue;
    if(!visible_jobs.count(static_cast<int>(i)) &&
        !(state.status=="waiting_for_tray" && circulation_.owner(job.origin)==source)) continue;
    message.jobs.push_back({job,state.status,state.loaded_at,state.storage_entered_at,state.storage_released_at});
  }
  for(const auto& n:circulation_.input.nodes) if(circulation_.owner(n.node)==source) {
    int represented=0;
    for(const auto& t:message.trays)
      if((t.edge_to<0 && t.node==n.node) || t.edge_to==n.node || t.reception_node==n.node) ++represented;
    const int occupancy=circulation_.occupancy(n.node);
    message.nodes.push_back({n.node,occupancy,circulation_.empty_stock(n.node,now_),occupancy-represented});
  }
  for(const auto& [from,to,active,received]:circulation_known_faults(source))
    message.known_faults.push_back({from,to,active,received});
  auto& channel=circulation_.next_channel_message_id[{source,target}];
  message.publication_sequence=++channel;
  message.message_id=std::string(version3 ? "planning-v3:" : version2 ? "planning-v2:" : "planning:")+std::to_string(source.size())+":"+source+":"+
      std::to_string(target.size())+":"+target+":"+std::to_string(channel);
  if(version2 || version3) {
    CirculationPlanningSnapshotV2 extended;
    static_cast<CirculationPlanningSnapshot&>(extended)=std::move(message);
    // Source-owned physical completion facts remain observable after the
    // carrier leaves. Assign identities only after filtering local events;
    // never expose global receipt/traversal indices or future job state.
    std::set<std::string> completed;
    for(const auto& receipt:circulation_.receipts) {
      if(receipt.event!="UNLOAD_COMPLETE" || receipt.time>now_ || circulation_.owner(receipt.node)!=source) continue;
      const auto job=std::find_if(circulation_.input.jobs.begin(),circulation_.input.jobs.end(),
          [&](const auto& j){return j.business_bag_id==receipt.business_bag_id;});
      if(job==circulation_.input.jobs.end() || job->destination!=receipt.node || receipt.time<job->arrival ||
          !completed.insert(receipt.business_bag_id).second)
        throw std::logic_error("circulation:invalid_local_completion_receipt");
      CirculationPlanningCompletion row;
      row.source_owner=source;row.business_bag_id=receipt.business_bag_id;row.tray_id=receipt.tray_id;
      row.destination=receipt.node;row.completed_at=receipt.time;
      row.source_local_sequence=extended.terminal_receipts.size()+1;
      row.receipt_id="completion:"+std::to_string(source.size())+":"+source+":"+std::to_string(row.source_local_sequence);
      extended.terminal_receipts.push_back(std::move(row));
    }
    const auto resolved=[](const std::string& kind,const std::string& status) {
      if(status=="rejected" || status=="failed" || status=="expired") return true;
      if(kind=="transfer") return status=="received" || status=="cancelled";
      if(kind=="route") return status=="updated";
      if(kind=="cancel_transfer") return status=="cancelled";
      return false;
    };
    for(const auto& request:circulation_.protocol_requests) {
      if(request.owner!=source) continue;
      CirculationPlanningAction row;row.source_owner=source;row.kind="transfer";
      row.request_id=circulation_.input.transfers.at(request.transfer).request_id;
      if(request.latest_ack>=0) {
        const auto& ack=circulation_.protocol_acks.at(request.latest_ack);
        if(ack.delivered_copies<=0 || ack.delivered_at<0 || ack.delivered_at>now_)
          throw std::logic_error("circulation:undelivered_planning_action_ack");
        row.has_delivered_ack=true;row.ack_sequence=ack.sequence;row.ack_delivered_at=ack.delivered_at;
        row.ack_status=ack.status;row.terminal=resolved(row.kind,row.ack_status);
      }
      extended.submitted_physical_actions.push_back(std::move(row));
    }
    for(const auto& command:circulation_.protocol_commands) {
      if(command.input.owner!=source) continue;
      const auto& kind=command.input.kind;
      if(kind=="demand" || kind=="service_forecast" || kind=="withdraw_service_forecast" ||
          kind=="planning_snapshot" || kind=="planning_snapshot_v2" || kind=="planning_snapshot_v3") continue;
      // Future unclassified command kinds remain unresolved, not silently
      // excluded from a complete physical-action coverage claim.
      CirculationPlanningAction row;row.source_owner=source;row.kind=kind;row.request_id=command.input.request_id;
      if(command.latest_ack>=0) {
        const auto& ack=circulation_.protocol_command_acks.at(command.latest_ack);
        if(ack.delivered_copies<=0 || ack.delivered_at<0 || ack.delivered_at>now_)
          throw std::logic_error("circulation:undelivered_planning_action_ack");
        row.has_delivered_ack=true;row.ack_sequence=ack.sequence;row.ack_delivered_at=ack.delivered_at;
        row.ack_status=ack.status;row.terminal=resolved(row.kind,row.ack_status);
      }
      extended.submitted_physical_actions.push_back(std::move(row));
    }
    std::sort(extended.submitted_physical_actions.begin(),extended.submitted_physical_actions.end(),
        [](const auto& a,const auto& b){return std::tie(a.request_id,a.kind)<std::tie(b.request_id,b.kind);});
    if(version3) {
      CirculationPlanningSnapshotV3 observed;
      static_cast<CirculationPlanningSnapshotV2&>(observed)=std::move(extended);
      // Capture only current source-owned commitments, using actual source
      // receipts. Reservation publication alone can precede future entry.
      for(std::size_t ti=0;ti<circulation_.trays.size();++ti) {
        const auto& tray=circulation_.trays[ti];
        if(circulation_.owner(tray.node)!=source || tray.edge_to<0) continue;
        const CirculationReceipt* entry=nullptr;
        const std::string job=tray.job>=0 ? circulation_.input.jobs.at(tray.job).business_bag_id : "";
        if(tray.edge_entry_observed && tray.node==tray.edge_from && tray.public_traversal_version>0 &&
            tray.active_leg>=0 && static_cast<std::size_t>(tray.active_leg)<circulation_.legs.size()) {
          const auto& leg=circulation_.legs[tray.active_leg];
          if(leg.tray==static_cast<int>(ti) && leg.job==tray.job)
          for(auto it=circulation_.receipts.rbegin();it!=circulation_.receipts.rend();++it) {
            if(it->event=="EDGE_ENTER" && it->tray_id==tray.tray_id && it->business_bag_id==job &&
                it->transport_leg_id==leg.transport_leg_id && it->traversal_id==tray.traversal_id &&
                it->node==tray.node && it->from==tray.edge_from && it->to==tray.edge_to &&
                std::isfinite(it->time) && it->time>=0 && it->time<=now_) {entry=&*it;break;}
          }
        }
        if(!entry) {observed.unmatched_inflight_tray_ids.push_back(tray.tray_id);continue;}
        CirculationPlanningInflight row;
        row.source_owner=source;row.tray_id=tray.tray_id;row.business_bag_id=job;
        // Private active-leg/traversal keys are matching evidence only. Never
        // serialize them into an owner-visible body or source-local digest.
        row.generation=tray.generation;row.traversal_id=tray.public_traversal_version;
        row.edge_from=tray.edge_from;row.edge_to=tray.edge_to;row.entered_at=entry->time;
        row.static_edge_travel_seconds=std::max(graph_.edge(tray.edge_from,tray.edge_to).travel_time(),config_.minimum_service_seconds);
        row.derived_edge_exit_at=row.entered_at+row.static_edge_travel_seconds;
        if(!std::isfinite(row.static_edge_travel_seconds) || row.static_edge_travel_seconds<=0 ||
            !std::isfinite(row.derived_edge_exit_at)) {
          observed.unmatched_inflight_tray_ids.push_back(tray.tray_id);continue;
        }
        observed.source_observed_inflight.push_back(std::move(row));
      }
      StateFingerprintWriter payload("g31.planning_capture_digest.v3");
      fingerprint_planning_capture_v3(payload,observed);observed.payload_sha256=payload.sha256();
      const int index=static_cast<int>(circulation_.planning_snapshots_v3.size());
      circulation_.planning_snapshots_v3.push_back(std::move(observed));
      circulation_schedule("control_planning_snapshot_v3",now_+delay,index);
      ++circulation_.next_control_id;runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;
      return "pending";
    }
    StateFingerprintWriter payload("g31.planning_capture_digest.v2");
    fingerprint_planning_capture_v2(payload,extended);extended.payload_sha256=payload.sha256();
    const int index=static_cast<int>(circulation_.planning_snapshots_v2.size());
    circulation_.planning_snapshots_v2.push_back(std::move(extended));
    circulation_schedule("control_planning_snapshot_v2",now_+delay,index);
    ++circulation_.next_control_id;runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;
    return "pending";
  }
  StateFingerprintWriter payload("g31.planning_capture_digest.v1");
  fingerprint_planning_capture(payload,message);message.payload_sha256=payload.sha256();
  const int index=static_cast<int>(circulation_.planning_snapshots.size());
  circulation_.planning_snapshots.push_back(std::move(message));
  circulation_schedule("control_planning_snapshot",now_+delay,index);
  ++circulation_.next_control_id;runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;
  return "pending";
}

} // namespace czr005::ics
