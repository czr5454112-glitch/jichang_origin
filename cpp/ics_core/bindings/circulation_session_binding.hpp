#pragma once

// Included inside the binding translation unit's private namespace.
class NativeSession {
 public:
  explicit NativeSession(const py::dict& data) {
    auto host=parse_host(data,"circulation");
    graph_=std::move(host.graph);config_=std::move(host.config);
    // A session default is public and independent of the future arrival tape.
    if(config_.max_simulation_time<0) config_.max_simulation_time=1.0e9;
    runtime_=std::make_unique<EventDrivenJunctionRuntime>(graph_,config_);
    runtime_->initialize_circulation(read_input(data),host.faults);
    rebuild_observation_owners();
  }
  NativeSession(const Graph& graph,const EventDrivenJunctionConfig& config)
      :graph_(graph),config_(config),runtime_(std::make_unique<EventDrivenJunctionRuntime>(graph_,config_)) {}
  double physical_time() const {return runtime_->progress_snapshot().simulated_time;}
  bool step() {return runtime_->process_one_event();}
  py::dict owner_notifications(const std::vector<std::string>& owners) const {
    if(!runtime_->circulation_state().input.owner_notifications_enabled)
      throw py::value_error("circulation:owner_notifications_not_enabled");
    if(owners.empty()) throw py::value_error("circulation:empty_notification_owners");
    const auto next=runtime_->next_physical_event_time();
    if(next && *next<=physical_time()) throw py::value_error("circulation:notification_timestamp_incomplete");
    py::dict out;
    for(const auto& owner:owners) {
      require_observation_owner(owner);
      if(out.contains(py::str(owner))) throw py::value_error("circulation:duplicate_notification_owner");
      const auto& notice=runtime_->circulation_state().owner_notifications.at(owner);
      py::dict row;row["sequence"]=notice.sequence;row["observed_at"]=notice.observed_at;row["change_mask"]=notice.change_mask;
      out[py::str(owner)]=row;
    }
    return out;
  }
  py::dict advance_until_owner_notification(const std::vector<std::string>& owners,
      const std::map<std::string,std::uint64_t>& after,double horizon,int budget=1000000) {
    std::set<std::string> unique;
    for(const auto& owner:owners) {
      require_observation_owner(owner);
      if(!unique.insert(owner).second) throw py::value_error("circulation:duplicate_notification_owner");
      if(after.find(owner)==after.end()) throw py::value_error("circulation:notification_cursor_keys_mismatch");
    }
    if(unique.size()!=after.size()) throw py::value_error("circulation:notification_cursor_keys_mismatch");
    const auto progress=runtime_->advance_circulation_until_owner_notification(after,horizon,budget);
    py::dict out;out["status"]=progress.status;out["physical_time"]=physical_time();
    out["timestamp_complete"]=progress.timestamp_complete;out["horizon_complete"]=progress.horizon_complete;
    py::dict changed;
    if(progress.timestamp_complete) {
      auto notices=owner_notifications(owners);
      for(const auto& owner:owners)
        if(runtime_->circulation_state().owner_notifications.at(owner).sequence>after.at(owner))
          changed[py::str(owner)]=notices[py::str(owner)];
    }
    out["notifications"]=changed;
    return out;
  }
  py::dict advance_to(double time,int budget=1000000) {
    const auto start=std::chrono::steady_clock::now();
    const int count=runtime_->advance_circulation_to(time,budget);
    py::dict out;out["physical_time"]=physical_time();out["processed_events"]=count;
    // Reaching the numeric clock is insufficient: a budget may stop between
    // same-timestamp native microphases. Consult only inside the scheduler;
    // the next private event time never becomes an online policy feature.
    const auto next=runtime_->next_physical_event_time();
    const bool complete=physical_time()>=time && (!next || *next>time);
    out["status"]=complete ? "reached" : "budget_exhausted";
    out["horizon_complete"]=complete;
    out["wall_seconds"]=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    return out;
  }
  EventDrivenJunctionRuntime::StateCheckpoint checkpoint() const {return runtime_->capture_state_checkpoint();}
  void restore(const EventDrivenJunctionRuntime::StateCheckpoint& state) {
    runtime_->restore_state_checkpoint(state);rebuild_observation_owners();
  }
  std::shared_ptr<NativeSession> fork() const {
    auto branch=std::make_shared<NativeSession>(graph_,config_);
    branch->restore(checkpoint());
    return branch;
  }
  std::string offline_state_sha256() const {return runtime_->circulation_state_sha256();}
  py::dict result_at(double horizon) {
    auto progress=advance_to(horizon);
    auto out=render_result(*runtime_,"circulation",{},false);
    out["schema"]="g31.circulation.live_result.v1";
    out["horizon"]=horizon;out["advance"]=progress;
    out["scope"]="offline result; contains offered population, never an online observation";
    const auto& s=runtime_->circulation_state();
    int offered=0,observed=0,loaded=0,completed=0;
    for(std::size_t i=0;i<s.jobs.size();++i) {
      offered+=s.input.jobs[i].arrival<=horizon;
      observed+=s.jobs[i].status!="unreleased";
      loaded+=s.jobs[i].loaded_at>=0;
      completed+=s.jobs[i].completed_at>=0;
    }
    py::dict totals;totals["offered_by_horizon"]=offered;totals["observed"]=observed;
    totals["loaded"]=loaded;totals["completed"]=completed;out["population"]=totals;
    return out;
  }
  py::dict observe(const std::string& owner) const {require_legacy_control_endpoint();return observe_impl(owner,false);}
  py::dict observe_control(const std::string& owner) const {require_legacy_control_endpoint();return observe_impl(owner,true);}
  py::dict demand_signature(const std::string& owner) const {
    require_legacy_control_endpoint();
    return demand_signature_impl(owner);
  }
  py::dict protocol_demand_signature(const std::string& owner) const {
    require_protocol_endpoint();return demand_signature_impl(owner);
  }
  py::dict demand_signature_impl(const std::string& owner) const {
    require_observation_owner(owner);
    const auto& s=runtime_->circulation_state();
    std::vector<const CirculationJob*> rows;
    const auto found=signature_job_order_.find(owner);
    if(found!=signature_job_order_.end()) for(const auto i:found->second)
      if(s.jobs[i].status=="waiting_for_tray") rows.push_back(&s.input.jobs[i]);
    return canonical_demand_signature(std::move(rows),true);
  }
  template <typename Job>
  static py::dict canonical_demand_signature(std::vector<const Job*> rows,bool already_sorted=false) {
    if(!already_sorted) std::sort(rows.begin(),rows.end(),[](const auto* a,const auto* b) {
      return std::tie(a->business_bag_id,a->origin,a->arrival,a->deadline)<
             std::tie(b->business_bag_id,b->origin,b->arrival,b->deadline);
    });
    // This hashes the exact formerly published Python sorted queue signature.
    // It is a read-only content signature, not an owner-event/global counter.
    std::string payload="g31.demand_signature.v1\n";
    const auto integer=[&](std::uint64_t value) {
      for(int shift=56;shift>=0;shift-=8) payload.push_back(static_cast<char>((value>>shift)&0xffU));
    };
    const auto floating=[&](double value) {
      if(value==0) value=0; // Python equality does not distinguish signed zero.
      std::uint64_t bits=0;std::memcpy(&bits,&value,sizeof(bits));integer(bits);
    };
    integer(rows.size());
    for(const auto* job:rows) {
      integer(job->business_bag_id.size());payload+=job->business_bag_id;
      integer(static_cast<std::uint64_t>(job->origin));floating(job->arrival);floating(job->deadline);
    }
    py::dict out;out["schema"]="g31.demand_signature.v1";
    // Identical canonical bytes and SHA-256 contract; CPython's mature digest
    // implementation avoids the scalar checkpoint serializer's per-call cost.
    out["sha256"]=py::module_::import("hashlib").attr("sha256")(py::bytes(payload)).attr("hexdigest")();
    out["waiting_count"]=rows.size();return out;
  }
  py::dict observe_impl(const std::string& owner,bool compact,bool protocol=false) const {
    if(runtime_->phase()==EventDrivenJunctionRuntimePhase::kIdle)
      throw py::value_error("circulation:live_session_required");
    const auto& s=runtime_->circulation_state();
    bool exists=false;
    for(const auto& n:s.input.nodes) exists=exists||observation_owner(n.node)==owner;
    if(!exists) throw py::value_error("circulation:unknown_observation_owner");
    py::dict out;out["schema"]="g31.regional_observation.v1";out["now"]=physical_time();out["owner_id"]=owner;
    out["version"]=owner_version(owner);
    py::list nodes,edges,contracts,edge_contracts,trays,jobs,transfers,messages,faults,routes,recoveries;
    for(int id:graph_.node_locations()) {
      const auto& n=graph_.node(id);
      nodes.append(py::make_tuple(n.location,n.node_type,n.service_time,n.x,n.y,n.outgoing));
    }
    for(const auto& e:s.input.edges) {
      const auto& physical=graph_.edge(e.from,e.to);
      edges.append(py::make_tuple(e.from,e.to,physical.length,physical.speed));
      py::dict d;d["from"]=e.from;d["to"]=e.to;d["capacity"]=e.capacity;d["entry_headway"]=e.entry_headway;
      edge_contracts.append(d);
    }
    for(const auto& n:s.input.nodes) {
      py::dict d;d["node"]=n.node;d["zone"]=n.zone;d["logistics_zone"]=n.zone;
      d["control_partition"]=s.partition(n.node);d["resource_owner"]=observation_owner(n.node);
      d["capacity"]=n.capacity;d["export_min_stock"]=n.export_min_stock;
      d["allow_export"]=n.allow_export;d["allow_receive"]=n.allow_receive;
      if(observation_owner(n.node)==owner) {d["occupancy"]=s.occupancy(n.node);d["actual_available"]=s.empty_stock(n.node,physical_time());}
      contracts.append(d);
    }
    std::set<int> visible_jobs;
    for(const auto& t:s.trays) {
      if(observation_owner(t.node)!=owner) continue;
      py::dict d;d["tray_id"]=t.tray_id;d["node"]=t.node;d["mode"]=t.mode;
      d["edge_from"]=t.edge_from;d["edge_to"]=t.edge_to;d["available_at"]=t.available_at;
      d["reception_node"]=t.reception_node;d["generation"]=t.generation;d["traversal_id"]=t.public_traversal_version;
      d["business_bag_id"]=t.job>=0 ? s.input.jobs[t.job].business_bag_id : "";
      py::list prefix;
      if(t.active_leg>=0) {
        const auto& leg=s.legs[t.active_leg];
        for(const auto& r:s.receipts) {
          if(r.transport_leg_id!=leg.transport_leg_id) continue;
          if(r.event=="LEG_START") prefix.append(r.from);
          else if(r.event=="EDGE_EXIT") prefix.append(r.to);
        }
      }
      if(py::len(prefix)==0) prefix.append(t.node);
      d["committed_prefix"]=prefix;
      if(t.job>=0) visible_jobs.insert(t.job);
      // Known deterministic operation durations come from observed starts, not
      // inspection of queued future completion events.
      for(auto it=s.receipts.rbegin();it!=s.receipts.rend();++it) {
        if(it->tray_id!=t.tray_id) continue;
        if(t.edge_to>=0 && it->event=="EDGE_ENTER" && it->traversal_id==t.traversal_id) {
          d["edge_exit_at"]=it->time+std::max(graph_.edge(it->from,it->to).travel_time(),runtime_->circulation_minimum_service_seconds());
          break;
        }
        if(t.job>=0 && t.mode=="loading" && it->event=="LOAD_START") {
          d["available_at"]=it->time+s.input.jobs[t.job].load_seconds;break;
        }
        if(t.job>=0 && t.mode=="unloading" && it->event=="UNLOAD_START") {
          d["available_at"]=it->time+s.input.jobs[t.job].unload_seconds;break;
        }
      }
      trays.append(d);
    }
    for(std::size_t i=0;i<s.jobs.size();++i) {
      const auto& j=s.input.jobs[i];const auto& state=s.jobs[i];
      if(state.status=="unreleased") continue;
      if(observation_owner(j.origin)!=owner && !visible_jobs.count(static_cast<int>(i))) continue;
      // The compact control projection retains the full contracts of actual
      // visible trays. Historical origin contracts and long waiting queues
      // are accounted for natively below, without Python object expansion.
      if(compact && !visible_jobs.count(static_cast<int>(i))) continue;
      py::dict d;
#define JFIELD(name) d[#name]=j.name
      JFIELD(business_bag_id);JFIELD(origin);JFIELD(destination);JFIELD(arrival);JFIELD(deadline);
      JFIELD(storage_node);JFIELD(storage_release_at);JFIELD(storage_min_dwell);JFIELD(load_seconds);
      JFIELD(unload_seconds);JFIELD(hold_seconds);JFIELD(protected_service);JFIELD(allow_suffix_reroute);
#undef JFIELD
      d["status"]=state.status;d["storage_entered_at"]=state.storage_entered_at;
      d["storage_released_at"]=state.storage_released_at;d["loaded_at"]=state.loaded_at;
      // Origin may retain its published contract, but not remote live progress.
      if(!visible_jobs.count(static_cast<int>(i)) && state.tray>=0 && observation_owner(s.trays[state.tray].node)!=owner) {
        d["status"]="handed_off";d["storage_entered_at"]=-1;d["storage_released_at"]=-1;
      }
      jobs.append(d);
    }
    for(std::size_t i=0;i<s.transfers.size();++i) {
      const auto& request=s.input.transfers[i];const auto& state=s.transfers[i];
      // No preloaded future transfer is visible before issue or delivery.
      if(request.issued_at>physical_time() ||
          (observation_owner(request.source)!=owner && !(state.delivered_at>=0 && observation_owner(request.destination)==owner))) continue;
      py::dict d;
#define TFIELD(name) d[#name]=request.name
      TFIELD(request_id);TFIELD(tray_id);TFIELD(source);TFIELD(destination);TFIELD(issued_at);
      TFIELD(earliest_departure);TFIELD(expiry);
#undef TFIELD
      d["status"]=state.status;d["reason"]=state.reason;
      d["delivered_at"]=state.delivered_at;d["departed_at"]=state.departed_at;d["received_at"]=state.received_at;
      transfers.append(d);
    }
    // A demand publication replaces its channel snapshot. Keep the complete
    // out-of-order delivery history offline, not in every online observation.
    std::map<std::string,const CirculationDemandMessage*> latest_demand;
    for(const auto& message:s.demand_messages) {
      if(!message.delivered || message.target_owner!=owner) continue;
      auto& latest=latest_demand[message.source_owner];
      if(!latest || std::tie(message.observed_at,message.publication_sequence)>
                    std::tie(latest->observed_at,latest->publication_sequence)) latest=&message;
    }
    for(const auto& [source,latest]:latest_demand) {
      const auto& message=*latest;
      py::dict d;d["kind"]="demand";d["message_id"]=message.message_id;
      d["source_owner"]=message.source_owner;d["target_owner"]=message.target_owner;
      d["publication_sequence"]=message.publication_sequence;
      d["observed_at"]=message.observed_at;d["delivered_at"]=message.delivered_at;
      py::list queue;
      if(!compact) for(const auto& j:message.jobs) {
        py::dict item;item["business_bag_id"]=j.business_bag_id;item["origin"]=j.origin;
        item["arrival"]=j.arrival;item["deadline"]=j.deadline;item["status"]="waiting_for_tray";queue.append(item);
      }
      d["jobs"]=queue;
      if(compact) {d["projection_jobs_omitted"]=true;d["snapshot_waiting_count"]=message.jobs.size();}
      messages.append(d);
    }
    for(const auto& message:s.service_forecasts) {
      if(!message.delivered || message.target_owner!=owner) continue;
      py::dict d;d["kind"]="service_forecast";
#define SFIELD(name) d[#name]=message.name
      SFIELD(message_id);SFIELD(source_owner);SFIELD(target_owner);SFIELD(business_bag_id);SFIELD(tray_id);
      SFIELD(from);SFIELD(next);SFIELD(generation);SFIELD(traversal_id);SFIELD(observed_at);SFIELD(delivered_at);
      SFIELD(entry_estimate);SFIELD(release_estimate);SFIELD(status);
      SFIELD(publication_sequence);SFIELD(supersedes);
#undef SFIELD
      d["estimate_scope"]="next_node_service_completion";
      messages.append(d);
    }
    for(const auto& [from,to,active,received]:runtime_->circulation_known_faults(owner)) {
      py::dict d;d["from"]=from;d["to"]=to;d["active"]=active;d["received_at"]=received;faults.append(d);
    }
    for(const auto& request:s.route_intents) {
      if(request.owner_id!=owner) continue;
      py::dict d;d["request_id"]=request.request_id;d["status"]=request.status;d["reason"]=request.reason;
      routes.append(d);
    }
    for(const auto& request:s.recovery_intents) {
      if(request.owner_id!=owner) continue;
      py::dict d;d["request_id"]=request.request_id;d["status"]=request.status;d["reason"]=request.reason;
      recoveries.append(d);
    }
    out["node_records"]=nodes;out["edge_records"]=edges;out["node_contracts"]=contracts;
    out["edge_contracts"]=edge_contracts;out["trays"]=trays;out["jobs"]=jobs;
    out["transfers"]=transfers;out["delivered_messages"]=messages;out["known_faults"]=faults;out["route_requests"]=routes;
    out["recovery_requests"]=recoveries;
    if(compact) out["control_projection"]=control_projection(owner,visible_jobs,latest_demand,protocol);
    return out;
  }
  py::dict submit_transfer(const py::dict& d) {
    require_legacy_control_endpoint();
    const auto owner=required<std::string>(d,"owner_id");
    if(d.contains("expected_version") && required<std::uint64_t>(d,"expected_version")!=owner_version(owner))
      return reply("rejected:stale_observation");
    CirculationTransfer request;
    request.request_id=required<std::string>(d,"request_id");request.tray_id=required<std::string>(d,"tray_id");
    request.source=required<int>(d,"source");request.destination=required<int>(d,"destination");
    request.message_delay=field<double>(d,"message_delay",0);
    request.earliest_departure=field<double>(d,"earliest_departure",physical_time());
    request.expiry=required<double>(d,"expiry");
    return reply(runtime_->submit_circulation_transfer(request,owner));
  }
  py::dict submit_route(const py::dict& d) {
    require_legacy_control_endpoint();
    CirculationRouteIntent request;
    request.request_id=required<std::string>(d,"request_id");request.owner_id=required<std::string>(d,"owner_id");
    request.business_bag_id=required<std::string>(d,"business_bag_id");request.tray_id=required<std::string>(d,"tray_id");
    request.from=required<int>(d,"from");request.next=required<int>(d,"next");
    request.expected_generation=required<std::uint64_t>(d,"expected_generation");
    request.expected_traversal=field<std::uint64_t>(d,"expected_traversal",0);request.expiry=required<double>(d,"expiry");
    return reply(runtime_->submit_circulation_route(request,field<double>(d,"message_delay",0)));
  }
  py::dict cancel_transfer(const std::string& id,const std::string& owner) {
    require_legacy_control_endpoint();return reply(runtime_->cancel_circulation_transfer(id,owner));
  }
  py::dict recover_empty(const std::string& id,const std::string& owner,const std::string& tray,double delay) {
    require_legacy_control_endpoint();
    CirculationRecoveryIntent request;request.request_id=id;request.owner_id=owner;request.tray_id=tray;
    return reply(runtime_->request_circulation_empty_recovery(request,delay));
  }
  py::dict publish_demand(const std::string& from,const std::string& to,double delay) {
    require_legacy_control_endpoint();return reply(runtime_->publish_circulation_demand(from,to,delay));
  }
  py::dict publish_service_forecast(const std::string& from,const std::string& to,
                                   const std::string& tray,int next,double delay) {
    require_legacy_control_endpoint();
    auto result=reply(runtime_->publish_circulation_service_forecast(from,to,tray,next,delay));
    if(py::cast<std::string>(result["status"])=="pending")
      result["message_id"]=runtime_->circulation_state().service_forecasts.back().message_id;
    return result;
  }
  py::dict withdraw_service_forecast(const std::string& source,const std::string& id,double delay) {
    require_legacy_control_endpoint();
    auto result=reply(runtime_->withdraw_circulation_service_forecast(source,id,delay));
    if(py::cast<std::string>(result["status"])=="pending")
      result["message_id"]=runtime_->circulation_state().service_forecasts.back().message_id;
    return result;
  }
  py::dict submit_protocol_transfer(const py::dict& d) {
    if(d.contains("expected_version")) throw py::value_error("circulation:protocol_uses_owner_delivery_revalidation");
    CirculationTransfer request;request.request_id=required<std::string>(d,"request_id");
    request.tray_id=required<std::string>(d,"tray_id");request.source=required<int>(d,"source");
    request.destination=required<int>(d,"destination");request.message_delay=field<double>(d,"message_delay",0);
    request.earliest_departure=required<double>(d,"earliest_departure");request.expiry=required<double>(d,"expiry");
    return reply(runtime_->submit_circulation_protocol_transfer(request,required<std::string>(d,"owner_id")));
  }
  py::dict submit_protocol_command(const py::dict& d) {
    if(d.contains("expected_version")) throw py::value_error("circulation:protocol_uses_owner_delivery_revalidation");
    CirculationProtocolCommandInput p;
    p.request_id=required<std::string>(d,"request_id");p.owner=required<std::string>(d,"owner_id");
    p.kind=required<std::string>(d,"kind");p.message_delay=field<double>(d,"message_delay",0);
    p.publication_delay=field<double>(d,"publication_delay",0);p.expiry=field<double>(d,"expiry",1e9);
    p.target_owner=field<std::string>(d,"target_owner","");p.tray_id=field<std::string>(d,"tray_id","");
    p.business_bag_id=field<std::string>(d,"business_bag_id","");p.from=field<int>(d,"from",-1);p.next=field<int>(d,"next",-1);
    p.expected_generation=field<std::uint64_t>(d,"expected_generation",0);
    p.expected_traversal=field<std::uint64_t>(d,"expected_traversal",0);
    p.reference_id=field<std::string>(d,p.kind=="cancel_transfer" ? "transfer_request_id" : "original_message_id","");
    p.reference_request_id=field<std::string>(d,"forecast_request_id","");
    return reply(runtime_->submit_circulation_protocol_command(std::move(p)));
  }
  py::dict protocol_command(const std::string& owner,const std::string& id) const {
    require_protocol_endpoint();require_observation_owner(owner);
    const auto& s=runtime_->circulation_state();
    for(const auto& command:s.protocol_commands)
      if(command.input.owner==owner && command.input.request_id==id)
        return render_protocol_command(command);
    py::dict missing;missing["request_id"]=id;missing["status"]="unknown_request";return missing;
  }
  py::dict protocol_request(const std::string& owner,const std::string& id) const {
    require_protocol_endpoint();require_observation_owner(owner);
    const auto& s=runtime_->circulation_state();
    for(const auto& client:s.protocol_requests) {
      const auto& request=s.input.transfers[client.transfer];
      if(client.owner!=owner || request.request_id!=id) continue;
      py::dict row;row["request_id"]=id;row["status"]=client.client_status;row["attempt"]=client.attempt;
      row["physical_resolution"]="unknown_without_a_delivered_ack";
      if(client.latest_ack>=0) {
        const auto& ack=s.protocol_acks.at(client.latest_ack);
        py::dict receipt;receipt["sequence"]=ack.sequence;receipt["attempt"]=ack.attempt;
        receipt["observed_at"]=ack.observed_at;receipt["delivered_at"]=ack.delivered_at;
        receipt["status"]=ack.status;receipt["reason"]=ack.reason;
        receipt["received_at"]=ack.received_at;
        row["last_delivered_ack"]=receipt;
        row["physical_resolution"]="immutable_delivered_snapshot_not_current_truth";
      }
      return row;
    }
    py::dict missing;missing["request_id"]=id;missing["status"]="unknown_request";return missing;
  }
  py::dict observe_protocol(const std::string& owner) const {
    return observe_protocol_impl(owner,false);
  }
  py::dict observe_protocol_control(const std::string& owner) const {
    return observe_protocol_impl(owner,true);
  }
  py::dict observe_protocol_impl(const std::string& owner,bool compact) const {
    require_protocol_endpoint();
    auto out=observe_impl(owner,compact,true);
    out["schema"]="g31.owner_protocol_observation.v1";
    // Local physical sensors remain current and lawful. Remote transfer truth,
    // owner uptime and unreceived ACKs are not controller observations.
    out.attr("pop")("transfers");
    // The legacy owner version includes module-processing receipts. Even when
    // no physical sensor changes, it would reveal unacknowledged handling or
    // remote owner availability. This endpoint has no truth-derived version.
    out.attr("pop")("version");
    out.attr("pop")("route_requests");out.attr("pop")("recovery_requests");
    out["scope"]="local physical sensors, client-owned payloads and immutable delivered messages/ACKs; offline methods are diagnostic capabilities";
    py::list requests,acks,commands,command_acks,ledger;
    const auto& s=runtime_->circulation_state();
    for(const auto& client:s.protocol_requests) if(client.owner==owner) {
      const auto& input=s.input.transfers[client.transfer];
      requests.append(protocol_request(owner,input.request_id));
      py::dict row;
#define PFIELD(name) row[#name]=input.name
      PFIELD(request_id);PFIELD(tray_id);PFIELD(source);PFIELD(destination);PFIELD(issued_at);
      PFIELD(earliest_departure);PFIELD(expiry);PFIELD(message_delay);
#undef PFIELD
      row["status"]="pending";row["received_at"]=-1.;row["reason"]="awaiting_delivered_resolution";
      row["status_scope"]="own_payload_and_last_delivered_ack_only";
      if(client.latest_ack>=0) {
        const auto& ack=s.protocol_acks[client.latest_ack];row["status"]=ack.status;
        row["received_at"]=ack.received_at;row["reason"]=ack.reason;
      }
      if(delivered_cancelled(input.request_id,owner)) {row["status"]="cancelled";row["reason"]="delivered_cancel_ack";}
      ledger.append(row);
    }
    for(const auto& ack:s.protocol_acks) {
      const auto& client=s.protocol_requests[ack.request];
      if(client.owner!=owner || ack.delivered_copies==0) continue;
      py::dict row;row["request_id"]=s.input.transfers[client.transfer].request_id;
      row["sequence"]=ack.sequence;row["attempt"]=ack.attempt;row["observed_at"]=ack.observed_at;
      row["delivered_at"]=ack.delivered_at;row["status"]=ack.status;row["reason"]=ack.reason;
      row["received_at"]=ack.received_at;
      row["delivered_copies"]=ack.delivered_copies;acks.append(row);
    }
    for(const auto& command:s.protocol_commands) if(command.input.owner==owner)
      commands.append(render_protocol_command(command));
    for(const auto& ack:s.protocol_command_acks) {
      const auto& command=s.protocol_commands[ack.command];
      if(command.input.owner!=owner || ack.delivered_copies==0) continue;
      auto row=command_ack(ack);row["request_id"]=command.input.request_id;row["kind"]=command.input.kind;
      row["delivered_copies"]=ack.delivered_copies;command_acks.append(row);
    }
    out["client_requests"]=requests;out["delivered_transfer_acks"]=acks;out["client_transfer_ledger"]=ledger;
    out["client_commands"]=commands;out["delivered_command_acks"]=command_acks;return out;
  }
  py::dict offline_diagnostics() const {
    py::list junctions,waits,trays,legs;
    // The runtime method rejects Idle and staged transactions before reading.
    for(const auto& row:runtime_->circulation_offline_junctions()) {
      py::dict d;d["node"]=row.node;d["queue"]=row.queue;d["source_queue"]=row.source_queue;
      d["scheduled_incoming"]=row.scheduled_incoming;d["next_dispatch_time"]=row.next_dispatch_time;
      junctions.append(d);
    }
    const auto& s=runtime_->circulation_state();
    for(const auto& [id,w]:s.resource_waits) {
      py::dict d;d["runtime_id"]=id;d["node"]=w.node;d["generation"]=w.generation;
      d["edge_indices"]=w.edge_indices;d["receiving_nodes"]=w.receiving_nodes;
      d["ranking_nodes"]=w.ranking_nodes;d["static_blocked"]=w.static_blocked;waits.append(d);
    }
    for(const auto& t:s.trays) {
      py::dict d;d["tray_id"]=t.tray_id;d["node"]=t.node;d["mode"]=t.mode;
      d["active_leg"]=t.active_leg;d["job_index"]=t.job;d["transfer_index"]=t.transfer;
      d["edge_from"]=t.edge_from;d["edge_to"]=t.edge_to;d["reception_node"]=t.reception_node;
      d["internal_traversal_id"]=t.traversal_id;d["public_traversal_version"]=t.public_traversal_version;
      trays.append(d);
    }
    for(const auto& leg:s.legs) {
      py::dict d;d["runtime_id"]=leg.runtime_id;d["transport_leg_id"]=leg.transport_leg_id;
      d["tray_index"]=leg.tray;d["job_index"]=leg.job;d["kind"]=leg.kind;legs.append(d);
    }
    py::dict out;out["schema"]="g31.circulation.offline_diagnostics.v1";
    out["scope"]="offline audit only; contains remote current state and internal IDs, never online policy features";
    out["now"]=physical_time();out["junctions"]=junctions;out["resource_waits"]=waits;
    out["edge_waiters"]=s.edge_waiters;out["receiving_waiters"]=s.receiving_waiters;
    out["ranking_waiters"]=s.ranking_waiters;out["trays"]=trays;out["legs"]=legs;
    return out;
  }
 private:
  // Batch observation already owns the exact command reference. Reusing its
  // serialization must not re-scan the entire command history for each row.
  // Single-request queries retain the same owner/identity lookup and both
  // paths expose only the same last actually delivered immutable ACK.
  py::dict render_protocol_command(const CirculationProtocolCommand& command) const {
    py::dict row;row["request_id"]=command.input.request_id;row["status"]=command.client_status;
    row["attempt"]=command.attempt;row["kind"]=command.input.kind;
    if(command.latest_ack>=0)
      row["last_delivered_ack"]=command_ack(runtime_->circulation_state().protocol_command_acks.at(command.latest_ack));
    return row;
  }
  bool delivered_cancelled(const std::string& id,const std::string& owner) const {
    const auto& s=runtime_->circulation_state();
    for(const auto& c:s.protocol_commands) if(c.input.owner==owner && c.input.kind=="cancel_transfer" &&
        c.input.reference_id==id && c.latest_ack>=0 && s.protocol_command_acks[c.latest_ack].status=="cancelled") return true;
    return false;
  }
  py::dict command_ack(const CirculationProtocolCommandAck& ack) const {
    if(ack.delivered_copies<=0 || ack.delivered_at<0)
      throw py::value_error("circulation:undelivered_command_ack_projection");
    py::dict row;row["sequence"]=ack.sequence;row["attempt"]=ack.attempt;row["observed_at"]=ack.observed_at;
    row["delivered_at"]=ack.delivered_at;row["executed_at"]=ack.executed_at;row["completed_at"]=ack.completed_at;
    row["status"]=ack.status;row["reason"]=ack.reason;row["result_id"]=ack.result_id;
    const auto& s=runtime_->circulation_state();const auto& command=s.protocol_commands.at(ack.command);
    // Only a delivered final ACK authorizes this derived field. An older
    // pending ACK must never acquire a snapshot created/completed afterwards.
    if(command.input.kind=="demand" && ack.status=="delivered") {
      const int index=command.native_index;
      if(index<0 || static_cast<std::size_t>(index)>=s.demand_messages.size())
        throw py::value_error("circulation:invalid_delivered_demand_ack_reference");
      const auto& message=s.demand_messages[index];
      if(ack.result_id.empty() || message.message_id!=ack.result_id ||
          message.source_owner!=command.input.owner || message.target_owner!=command.input.target_owner ||
          !message.delivered || message.observed_at!=ack.executed_at || message.delivered_at!=ack.completed_at)
        throw py::value_error("circulation:invalid_delivered_demand_ack_reference");
      // Jobs in the referenced message are immutable and already sealed in
      // the native checkpoint. This is not a fresh read of the source queue.
      // Memoize only the digest string, returning new Python dicts each time.
      auto found=captured_demand_digests_.find(index);
      if(found==captured_demand_digests_.end()) {
        std::vector<const CirculationDemandItem*> rows;rows.reserve(message.jobs.size());
        for(const auto& job:message.jobs) rows.push_back(&job);
        const auto signature=canonical_demand_signature(std::move(rows));
        found=captured_demand_digests_.emplace(index,py::cast<std::string>(signature["sha256"])).first;
      }
      py::dict signature;signature["schema"]="g31.demand_signature.v1";
      signature["sha256"]=found->second;signature["waiting_count"]=message.jobs.size();
      row["captured_demand_signature"]=signature;
      row["captured_demand_observed_at"]=message.observed_at;
      row["captured_demand_publication_sequence"]=message.publication_sequence;
    }
    return row;
  }
  std::map<int,std::string> observation_owners_;
  mutable std::map<int,std::string> captured_demand_digests_;
  // Derived, immutable contract order only. Every query still filters actual
  // released status, so future jobs do not enter signatures or observations.
  std::map<std::string,std::vector<std::size_t>> signature_job_order_;
  void rebuild_observation_owners() {
    observation_owners_.clear();
    captured_demand_digests_.clear();
    for(const auto& node:runtime_->circulation_state().input.nodes)
      observation_owners_.emplace(node.node,node.resource_owner.empty() ? node.zone : node.resource_owner);
    signature_job_order_.clear();const auto& input=runtime_->circulation_state().input;
    for(std::size_t i=0;i<input.jobs.size();++i) signature_job_order_[observation_owner(input.jobs[i].origin)].push_back(i);
    for(auto& [owner,indices]:signature_job_order_) std::sort(indices.begin(),indices.end(),[&](auto a,auto b) {
      const auto& x=input.jobs[a];const auto& y=input.jobs[b];
      return std::tie(x.business_bag_id,x.origin,x.arrival,x.deadline)<std::tie(y.business_bag_id,y.origin,y.arrival,y.deadline);
    });
  }
  const std::string& observation_owner(int node) const {
    const auto found=observation_owners_.find(node);
    if(found==observation_owners_.end()) throw std::invalid_argument("circulation:missing_node_contract");
    return found->second;
  }
  void require_legacy_control_endpoint() const {
    if(runtime_->circulation_state().input.owner_protocol.enabled)
      throw py::value_error("circulation:owner_protocol_endpoint_required");
  }
  void require_protocol_endpoint() const {
    if(!runtime_->circulation_state().input.owner_protocol.enabled)
      throw py::value_error("circulation:owner_protocol_not_enabled");
  }
  void require_observation_owner(const std::string& owner) const {
    if(runtime_->phase()==EventDrivenJunctionRuntimePhase::kIdle)
      throw py::value_error("circulation:live_session_required");
    const auto& s=runtime_->circulation_state();
    for(const auto& node:s.input.nodes) if(observation_owner(node.node)==owner) return;
    throw py::value_error("circulation:unknown_observation_owner");
  }
  py::dict control_projection(const std::string& owner,const std::set<int>& visible_jobs,
                             const std::map<std::string,const CirculationDemandMessage*>& latest_demand,bool protocol=false) const {
    const auto& s=runtime_->circulation_state();const double now=physical_time();
    struct Waiting {
      const std::string* id;int origin;double arrival,deadline,observed_at;
      int local_index;std::size_t global_index=0;
    };
    std::vector<Waiting> waiting;
    std::unordered_set<std::string> visible_ids;
    std::set<int> known_ports;
    for(std::size_t i=0;i<s.jobs.size();++i) {
      const auto& j=s.input.jobs[i];const auto& state=s.jobs[i];
      if(state.status=="unreleased" || (observation_owner(j.origin)!=owner && !visible_jobs.count(static_cast<int>(i)))) continue;
      // Local contracts shadow an older delivered remote waiting snapshot,
      // including a currently loaded tray that has crossed the boundary.
      visible_ids.insert(j.business_bag_id);known_ports.insert(j.origin);
      if(state.status=="waiting_for_tray")
        waiting.push_back({&j.business_bag_id,j.origin,j.arrival,j.deadline,now,static_cast<int>(i)});
    }
    for(const auto& [source,message]:latest_demand) for(const auto& j:message->jobs) {
      if(!visible_ids.insert(j.business_bag_id).second) continue;
      known_ports.insert(j.origin);
      waiting.push_back({&j.business_bag_id,j.origin,j.arrival,j.deadline,message->observed_at,-1});
    }
    std::sort(waiting.begin(),waiting.end(),[](const auto& a,const auto& b) {
      return std::tie(a.arrival,*a.id)<std::tie(b.arrival,*b.id);
    });
    std::map<int,std::vector<const Waiting*>> groups;
    for(std::size_t i=0;i<waiting.size();++i) {waiting[i].global_index=i;groups[waiting[i].origin].push_back(&waiting[i]);}
    // Every forecast contributes at most one future availability per real
    // visible tray. Keeping even pledged trays only enlarges this lawful
    // upper bound; it neither grants export nor materializes predictions.
    std::size_t limit=0;
    for(const auto& tray:s.trays) if(observation_owner(tray.node)==owner && tray.mode!="quarantined") ++limit;
    std::map<int,std::size_t> incoming;
    for(std::size_t i=0;i<s.transfers.size();++i) {
      const auto& request=s.input.transfers[i];const auto& state=s.transfers[i];
      std::string status=state.status;double received_at=state.received_at;
      if(protocol) {
        const auto client=std::find_if(s.protocol_requests.begin(),s.protocol_requests.end(),[&](const auto& p) {
          return p.transfer==static_cast<int>(i) && p.owner==owner;
        });
        if(client==s.protocol_requests.end()) continue;
        status=client->latest_ack>=0 ? s.protocol_acks[client->latest_ack].status : "pending";
        received_at=client->latest_ack>=0 ? s.protocol_acks[client->latest_ack].received_at : -1;
        if(delivered_cancelled(request.request_id,owner)) status="cancelled";
      }
      if(request.issued_at>now || (observation_owner(request.source)!=owner &&
          !(state.delivered_at>=0 && observation_owner(request.destination)==owner))) continue;
      const bool active=status=="pending" || status=="granted" || status=="in_transit" ||
                        status=="requested" || status=="delivered" || status=="undelivered" ||
                        status=="dispatching" || status=="departed";
      auto group=groups.find(request.destination);
      // Exact legacy timestamp semantics: the last globally FIFO-sorted
      // waiting row at this origin, not a hidden receiver's current state.
      if(active || (status=="received" && group!=groups.end() &&
                    received_at>=group->second.back()->observed_at)) ++incoming[request.destination];
    }
    py::list output_groups;
    for(const auto& [origin,rows]:groups) {
      const auto covered_upper=incoming[origin]+limit;
      const auto head_limit=limit ? covered_upper+limit : 0;
      py::dict group;group["origin"]=origin;group["count"]=rows.size();
      group["demand_observed_at"]=rows.back()->observed_at;
      group["covered_upper_bound"]=covered_upper;group["head_limit"]=head_limit;
      py::list heads;
      for(std::size_t i=0;i<std::min(rows.size(),head_limit);++i) {
        const auto& row=*rows[i];py::dict job;
        job["business_bag_id"]=*row.id;job["origin"]=row.origin;job["arrival"]=row.arrival;
        job["deadline"]=row.deadline;job["status"]="waiting_for_tray";
        job["demand_observed_at"]=row.observed_at;job["fifo_index"]=i;job["global_fifo_index"]=row.global_index;
        heads.append(job);
      }
      group["jobs"]=heads;output_groups.append(group);
    }
    py::dict projection;projection["schema"]="g31.analytic_control_projection.v1";
    projection["waiting_groups"]=output_groups;
    projection["known_origin_nodes"]=std::vector<int>(known_ports.begin(),known_ports.end());
    projection["candidate_limit"]=limit;projection["exact_waiting_count"]=waiting.size();
    projection["waiting_selection"]="fifo_prefix_cover_upper_plus_finite_tray_bound";
    projection["scope"]="exact representation for current equal-column ETA assignment; not general job-feature truncation";
    return projection;
  }
  Graph graph_;
  EventDrivenJunctionConfig config_;
  std::unique_ptr<EventDrivenJunctionRuntime> runtime_;
  std::uint64_t owner_version(const std::string& owner) const {
    const auto& s=runtime_->circulation_state();std::uint64_t version=0;
    for(const auto& r:s.receipts)
      if((r.node>=0 && observation_owner(r.node)==owner) || (r.from>=0 && observation_owner(r.from)==owner)) ++version;
    for(const auto& m:s.demand_messages) if(m.delivered && m.target_owner==owner) ++version;
    for(const auto& m:s.service_forecasts) if(m.delivered && m.target_owner==owner) ++version;
    return version;
  }
  static py::dict reply(const std::string& response) {
    const auto separator=response.find(':');py::dict d;
    d["status"]=response.substr(0,separator);d["reason"]=separator==std::string::npos ? "" : response.substr(separator+1);
    return d;
  }
};

void bind_session(py::module_& module) {
  py::class_<EventDrivenJunctionRuntime::StateCheckpoint>(module,"NativeCheckpoint")
    .def_property_readonly("offline_state_sha256",&EventDrivenJunctionRuntime::StateCheckpoint::state_sha256);
  py::class_<NativeSession,std::shared_ptr<NativeSession>>(module,"NativeSession")
    .def(py::init<const py::dict&>())
    .def_property_readonly("physical_time",&NativeSession::physical_time)
    .def("step",&NativeSession::step)
    .def("advance_to",&NativeSession::advance_to,py::arg("time"),py::arg("max_events")=1000000)
    .def("owner_notifications",&NativeSession::owner_notifications,py::arg("owner_ids"))
    .def("advance_until_owner_notification",&NativeSession::advance_until_owner_notification,
         py::arg("owner_ids"),py::arg("after_sequences"),py::arg("horizon"),py::arg("max_events")=1000000)
    .def("observe",&NativeSession::observe)
    .def("observe_control",&NativeSession::observe_control,py::arg("owner_id"))
    .def("observe_protocol",&NativeSession::observe_protocol,py::arg("owner_id"))
    .def("observe_protocol_control",&NativeSession::observe_protocol_control,py::arg("owner_id"))
    .def("protocol_demand_signature",&NativeSession::protocol_demand_signature,py::arg("owner_id"))
    .def("submit_protocol_command",&NativeSession::submit_protocol_command,py::arg("request"))
    .def("protocol_command",&NativeSession::protocol_command,py::arg("owner_id"),py::arg("request_id"))
    .def("protocol_request",&NativeSession::protocol_request,py::arg("owner_id"),py::arg("request_id"))
    .def("submit_protocol_transfer",&NativeSession::submit_protocol_transfer,py::arg("request"))
    .def("demand_signature",&NativeSession::demand_signature,py::arg("owner_id"))
    .def("checkpoint",&NativeSession::checkpoint).def("restore",&NativeSession::restore)
    .def("fork",&NativeSession::fork).def("offline_state_sha256",&NativeSession::offline_state_sha256)
    .def("submit_transfer_intent",&NativeSession::submit_transfer)
    .def("submit_route_intent",&NativeSession::submit_route)
    .def("cancel_transfer_intent",&NativeSession::cancel_transfer)
    .def("recover_empty_tray",&NativeSession::recover_empty,py::arg("request_id"),py::arg("owner_id"),py::arg("tray_id"),py::arg("delay")=0)
    .def("publish_demand",&NativeSession::publish_demand,py::arg("source_owner"),py::arg("target_owner"),py::arg("delay")=0)
    .def("publish_service_forecast",&NativeSession::publish_service_forecast,
         py::arg("source_owner"),py::arg("target_owner"),py::arg("tray_id"),py::arg("next_node"),py::arg("delay")=0)
    .def("withdraw_service_forecast",&NativeSession::withdraw_service_forecast,
         py::arg("source_owner"),py::arg("original_message_id"),py::arg("delay")=0)
    .def("offline_diagnostics",&NativeSession::offline_diagnostics)
    .def("result_at",&NativeSession::result_at);
}
