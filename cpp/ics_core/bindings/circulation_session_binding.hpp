#pragma once

// Included inside the binding translation unit's private namespace.
class NativeSession {
 public:
  using TimingPhase = czr005::ics::diagnostic::RequestTimingPhase;
  using TimingMethod = czr005::ics::diagnostic::RequestTimingMethod;
  using TimingIdentity = czr005::ics::diagnostic::RequestTimingIdentity;
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
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::advance_notification);
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
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::advance_to);
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
    branch->indexed_control_projection_=indexed_control_projection_;
    branch->indexed_message_selection_=indexed_message_selection_;
    return branch;
  }
  // Runtime diagnostic comparison switch: not policy input or checkpoint state.
  void set_indexed_control_projection(bool enabled) {indexed_control_projection_=enabled;}
  void set_indexed_message_selection(bool enabled) {indexed_message_selection_=enabled;}
  std::string offline_state_sha256() const {return runtime_->circulation_state_sha256();}
  py::dict result_at(double horizon) {
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::result_at);
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
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::demand_signature);
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
  py::dict observe_impl(const std::string& owner,bool compact,bool protocol=false,
      const std::set<std::size_t>* forecast_selection=nullptr) const {
    if(runtime_->phase()==EventDrivenJunctionRuntimePhase::kIdle)
      throw py::value_error("circulation:live_session_required");
    const auto& s=runtime_->circulation_state();
    bool exists=false;
    for(const auto& n:s.input.nodes) exists=exists||observation_owner(n.node)==owner;
    if(!exists) throw py::value_error("circulation:unknown_observation_owner");
    py::dict out;out["schema"]="g31.regional_observation.v1";out["now"]=physical_time();out["owner_id"]=owner;
    // Protocol callers never receive the legacy truth-derived version.
    // Do not scan historical receipts to construct a field then discard it.
    if(!protocol) out["version"]=owner_version(owner);
    sync_binding_indexes();
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
        const auto found=prefix_receipts_.find(leg.transport_leg_id);
        if(found!=prefix_receipts_.end()) for(const auto index:found->second) {
          const auto& r=s.receipts[index];
          if(r.event=="LEG_START") prefix.append(r.from);
          else if(r.event=="EDGE_EXIT") prefix.append(r.to);
        }
      }
      if(py::len(prefix)==0) prefix.append(t.node);
      d["committed_prefix"]=prefix;
      if(t.job>=0) visible_jobs.insert(t.job);
      // Known deterministic operation durations come from observed starts, not
      // inspection of queued future completion events.
      const auto tray_receipts=receipts_by_tray_.find(t.tray_id);
      if(tray_receipts!=receipts_by_tray_.end() &&
          (!indexed_message_selection_ || t.edge_to>=0 ||
           (t.job>=0 && (t.mode=="loading" || t.mode=="unloading"))))
      for(auto ri=tray_receipts->second.rbegin();ri!=tray_receipts->second.rend();++ri) {
        const auto it=s.receipts.begin()+*ri;
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
    const auto job_indices=compact ? std::vector<std::size_t>(visible_jobs.begin(),visible_jobs.end())
                                   : local_job_indices(owner,visible_jobs);
    for(const auto i:job_indices) {
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
    if(!protocol) for(std::size_t i=0;i<s.transfers.size();++i) {
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
    if(indexed_message_selection_ && observation_index_.sync(s,runtime_->circulation_publication_journal())) {
      for(const auto& [source,index]:observation_index_.latest_demand(owner))
        latest_demand.emplace(source,&s.demand_messages[index]);
    } else for(const auto& message:s.demand_messages) {
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
      if(!compact) for(const auto index:message.jobs) {
        const auto& j=s.input.jobs.at(index);
        py::dict item;item["business_bag_id"]=j.business_bag_id;item["origin"]=j.origin;
        item["arrival"]=j.arrival;item["deadline"]=j.deadline;item["status"]="waiting_for_tray";queue.append(item);
      }
      d["jobs"]=queue;
      if(compact) {d["projection_jobs_omitted"]=true;d["snapshot_waiting_count"]=message.jobs.size();}
      messages.append(d);
    }
    const auto append_forecast=[&](const auto& message) {
      if(!message.delivered || message.target_owner!=owner) return;
      py::dict d;d["kind"]="service_forecast";
#define SFIELD(name) d[#name]=message.name
      SFIELD(message_id);SFIELD(source_owner);SFIELD(target_owner);SFIELD(business_bag_id);SFIELD(tray_id);
      SFIELD(from);SFIELD(next);SFIELD(generation);SFIELD(traversal_id);SFIELD(observed_at);SFIELD(delivered_at);
      SFIELD(entry_estimate);SFIELD(release_estimate);SFIELD(status);
      SFIELD(publication_sequence);SFIELD(supersedes);
#undef SFIELD
      d["estimate_scope"]="next_node_service_completion";
      messages.append(d);
    };
    if(forecast_selection) {
      for(const auto index:*forecast_selection) append_forecast(s.service_forecasts.at(index));
    } else for(const auto& message:s.service_forecasts) append_forecast(message);
    for(const auto& [from,to,active,received]:runtime_->circulation_known_faults(owner)) {
      py::dict d;d["from"]=from;d["to"]=to;d["active"]=active;d["received_at"]=received;faults.append(d);
    }
    if(!protocol) for(const auto& request:s.route_intents) {
      if(request.owner_id!=owner) continue;
      py::dict d;d["request_id"]=request.request_id;d["status"]=request.status;d["reason"]=request.reason;
      routes.append(d);
    }
    if(!protocol) for(const auto& request:s.recovery_intents) {
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
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call,
        {TimingIdentity::binding_submission, -1}, TimingMethod::submit_transfer);
    if(d.contains("expected_version")) throw py::value_error("circulation:protocol_uses_owner_delivery_revalidation");
    CirculationTransfer request;request.request_id=required<std::string>(d,"request_id");
    request.tray_id=required<std::string>(d,"tray_id");request.source=required<int>(d,"source");
    request.destination=required<int>(d,"destination");request.message_delay=field<double>(d,"message_delay",0);
    request.earliest_departure=required<double>(d,"earliest_departure");request.expiry=required<double>(d,"expiry");
    return reply(runtime_->submit_circulation_protocol_transfer(request,required<std::string>(d,"owner_id")));
  }
  py::dict submit_protocol_command(const py::dict& d) {
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call,
        {TimingIdentity::binding_submission, -1}, TimingMethod::submit_command);
    if(d.contains("expected_version")) throw py::value_error("circulation:protocol_uses_owner_delivery_revalidation");
    CirculationProtocolCommandInput p;
    p.request_id=required<std::string>(d,"request_id");p.owner=required<std::string>(d,"owner_id");
    p.kind=required<std::string>(d,"kind");p.message_delay=field<double>(d,"message_delay",0);
    if(p.kind=="planning_snapshot" || p.kind=="planning_snapshot_v2" || p.kind=="planning_snapshot_v3") {
      const std::set<std::string> allowed={"request_id","owner_id","kind","target_owner",
          "message_delay","publication_delay","expiry"};
      for(const auto item:d) if(!allowed.count(py::cast<std::string>(item.first)))
        throw py::value_error("circulation:planning_snapshot_payload_is_native_captured");
      if(!d.contains("expiry")) throw py::value_error("circulation:planning_snapshot_requires_expiry");
    }
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
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::query_command);
    require_protocol_endpoint();require_observation_owner(owner);
    const auto& s=runtime_->circulation_state();
    sync_binding_indexes();
    const auto found=command_identity_index_.find({owner,id});
    if(found!=command_identity_index_.end()) return render_protocol_command(s.protocol_commands[found->second]);
    py::dict missing;missing["request_id"]=id;missing["status"]="unknown_request";return missing;
  }
  py::dict protocol_request(const std::string& owner,const std::string& id) const {
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::query_transfer);
    require_protocol_endpoint();require_observation_owner(owner);
    const auto& s=runtime_->circulation_state();
    sync_binding_indexes();
    const auto found=request_identity_index_.find({owner,id});
    if(found!=request_identity_index_.end()) return render_protocol_request(s.protocol_requests[found->second]);
    py::dict missing;missing["request_id"]=id;missing["status"]="unknown_request";return missing;
  }
  py::dict observe_protocol(const std::string& owner) const {
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::observe_protocol);
    return observe_protocol_impl(owner,false);
  }
  py::dict observe_protocol_control(const std::string& owner) const {
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::observe_control);
    return observe_protocol_impl(owner,true);
  }
  py::dict observe_protocol_control_policy(const std::string& owner) const {
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::observe_policy);
    return observe_protocol_impl(owner,true,false);
  }
  py::dict observe_protocol_control_policy_recent(const std::string& owner,double forecast_validity) const {
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::observe_policy_recent);
    require_protocol_endpoint();require_observation_owner(owner);
    if(!std::isfinite(forecast_validity) || forecast_validity<=0)
      throw py::value_error("circulation:invalid_forecast_validity");
    const auto selection=policy_forecast_selection(owner,forecast_validity);
    return observe_protocol_impl(owner,true,false,&selection);
  }
  py::list protocol_planning_snapshots(const std::string& owner) const {
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::planning_snapshots);
    require_protocol_endpoint();require_observation_owner(owner);
    std::map<std::string,const CirculationPlanningSnapshot*> latest;
    for(const auto& message:runtime_->circulation_state().planning_snapshots) {
      if(!message.delivered || message.target_owner!=owner) continue;
      auto& old=latest[message.source_owner];
      if(!old || std::tie(message.captured_at,message.publication_sequence)>
                 std::tie(old->captured_at,old->publication_sequence)) old=&message;
    }
    py::list out;
    // Select the newest delivered revision BEFORE testing expiry. Its expired
    // envelope is a tombstone, not permission to resurrect an older snapshot.
    for(const auto& [source,message]:latest) out.append(render_planning_snapshot(*message,physical_time()));
    return out;
  }
  py::list protocol_planning_snapshots_v2(const std::string& owner) const {
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::planning_snapshots);
    require_protocol_endpoint();require_observation_owner(owner);
    std::map<std::string,const CirculationPlanningSnapshotV2*> latest;
    for(const auto& message:runtime_->circulation_state().planning_snapshots_v2) {
      if(!message.delivered || message.target_owner!=owner) continue;
      auto& old=latest[message.source_owner];
      if(!old || std::tie(message.captured_at,message.publication_sequence)>
                 std::tie(old->captured_at,old->publication_sequence)) old=&message;
    }
    py::list out;
    for(const auto& [source,message]:latest) out.append(render_planning_snapshot_v2(*message,physical_time()));
    return out;
  }
  py::list protocol_planning_snapshots_v3(const std::string& owner) const {
    auto timing = runtime_->request_timing().scoped(TimingPhase::native_call, {}, TimingMethod::planning_snapshots);
    require_protocol_endpoint();require_observation_owner(owner);
    std::map<std::string,const CirculationPlanningSnapshotV3*> latest;
    for(const auto& message:runtime_->circulation_state().planning_snapshots_v3) {
      if(!message.delivered || message.target_owner!=owner) continue;
      auto& old=latest[message.source_owner];
      if(!old || std::tie(message.captured_at,message.publication_sequence)>
                 std::tie(old->captured_at,old->publication_sequence)) old=&message;
    }
    py::list out;
    // Latest delivered revision first, including an expired tombstone.
    for(const auto& [source,message]:latest) out.append(render_planning_snapshot_v3(*message,physical_time()));
    return out;
  }
  py::dict observe_protocol_impl(const std::string& owner,bool compact,bool client_history=true,
      const std::set<std::size_t>* forecast_selection=nullptr) const {
    require_protocol_endpoint();
    auto out=observe_impl(owner,compact,true,forecast_selection);
    out["schema"]="g31.owner_protocol_observation.v1";
    // Local physical sensors remain current and lawful. Remote transfer truth,
    // owner uptime and unreceived ACKs are not controller observations.
    out.attr("pop")("transfers");
    // The legacy owner version includes module-processing receipts. Even when
    // no physical sensor changes, it would reveal unacknowledged handling or
    // remote owner availability. This endpoint has no truth-derived version.
    out.attr("pop")("route_requests");out.attr("pop")("recovery_requests");
    out["scope"]="local physical sensors, client-owned payloads and immutable delivered messages/ACKs; offline methods are diagnostic capabilities";
    py::list requests,acks,commands,command_acks,ledger;
    const auto& s=runtime_->circulation_state();
    for(const auto& client:s.protocol_requests) if(client.owner==owner) {
      const auto& input=s.input.transfers[client.transfer];
      if(client_history) requests.append(render_protocol_request(client));
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
    if(client_history) for(const auto& ack:s.protocol_acks) {
      const auto& client=s.protocol_requests[ack.request];
      if(client.owner!=owner || ack.delivered_copies==0) continue;
      py::dict row;row["request_id"]=s.input.transfers[client.transfer].request_id;
      row["sequence"]=ack.sequence;row["attempt"]=ack.attempt;row["observed_at"]=ack.observed_at;
      row["delivered_at"]=ack.delivered_at;row["status"]=ack.status;row["reason"]=ack.reason;
      row["received_at"]=ack.received_at;
      row["delivered_copies"]=ack.delivered_copies;acks.append(row);
    }
    if(client_history) for(const auto& command:s.protocol_commands) if(command.input.owner==owner)
      commands.append(render_protocol_command(command));
    if(client_history) for(const auto& ack:s.protocol_command_acks) {
      const auto& command=s.protocol_commands[ack.command];
      if(command.input.owner!=owner || ack.delivered_copies==0) continue;
      auto row=command_ack(ack);row["request_id"]=command.input.request_id;row["kind"]=command.input.kind;
      row["delivered_copies"]=ack.delivered_copies;command_acks.append(row);
    }
    if(client_history) {
      out["client_requests"]=requests;out["delivered_transfer_acks"]=acks;out["client_transfer_ledger"]=ledger;
      out["client_commands"]=commands;out["delivered_command_acks"]=command_acks;
    } else {
      // Policy callers refresh their immutable outbox through individual lawful
      // getters. Audit/C1 callers retain the complete observation endpoints.
      out["client_transfer_ledger"]=ledger;
      out["observation_scope"]="controller_policy";
    }
    return out;
  }
  void offline_request_timing_start(std::size_t capacity, std::uint64_t session_identity) {
    runtime_->start_request_timing(capacity, session_identity);
  }
  void offline_request_timing_stop() { runtime_->stop_request_timing(); }
  py::dict offline_request_timing_take() {
    const auto batch = runtime_->take_request_timing();
    py::dict out;out["schema"]="g31.native_request_timing.v1";
    out["session_identity"]=batch.session_identity;out["trace_epoch"]=batch.trace_epoch;
    out["completed_outer_calls"]=batch.completed_outer_calls;out["errors"]=batch.errors;
    out["emitted_span_count"]=batch.emitted_span_count;
    out["enabled"]=batch.enabled;out["clock"]="steady_clock_relative_nanoseconds";
    out["coverage"]="known_control_phases_and_unclassified_remainder";
    out["physics_subtraction_authorized"]=false;
    out["scope"]="offline diagnostic only; never an online policy observation";
    py::list rows;
    for(const auto& r:batch.rows) {
      py::dict row;
      row["trace_epoch"]=r.trace_epoch;row["call_ordinal"]=r.call_ordinal;
      row["span_id"]=r.span_id;row["parent_span_id"]=r.parent_span_id;
      row["start_ns"]=r.start_ns;row["end_ns"]=r.end_ns;
      row["event_sequence"]=r.event_sequence;row["logical_time"]=r.logical_time;
      row["phase"]=static_cast<int>(r.phase);row["method"]=static_cast<int>(r.method);
      row["identity_kind"]=static_cast<int>(r.association.kind);row["identity_index"]=r.association.index;
      row["attempt"]=r.association.attempt;
      row["related_identity_kind"]=static_cast<int>(r.association.related_kind);
      row["related_identity_index"]=r.association.related_index;
      row["ended"]=r.ended;row["exception_exit"]=r.exception_exit;rows.append(row);
    }
    out["rows"]=rows;
    // Resolve numeric associations only outside all measured spans. Keeping
    // these IDs out of commit hooks avoids allocations at irreversible publish.
    const auto& s=runtime_->circulation_state();
    py::list transfers,commands,legs,jobs;
    for(std::size_t i=0;i<s.input.transfers.size();++i) {
      py::dict r;r["index"]=i;r["request_id"]=s.input.transfers[i].request_id;transfers.append(r);
    }
    for(std::size_t i=0;i<s.protocol_commands.size();++i) {
      const auto& c=s.protocol_commands[i];py::dict r;r["index"]=i;r["request_id"]=c.input.request_id;
      r["kind"]=c.input.kind;r["native_index"]=c.native_index;
      r["reference_id"]=c.input.reference_id;r["reference_request_id"]=c.input.reference_request_id;commands.append(r);
    }
    for(std::size_t i=0;i<s.legs.size();++i) {
      const auto& l=s.legs[i];py::dict r;r["index"]=i;r["transport_leg_id"]=l.transport_leg_id;
      r["tray_index"]=l.tray;r["job_index"]=l.job;r["kind"]=l.kind;legs.append(r);
    }
    for(std::size_t i=0;i<s.input.jobs.size();++i) {
      py::dict r;r["index"]=i;r["business_bag_id"]=s.input.jobs[i].business_bag_id;jobs.append(r);
    }
    out["transfer_identities"]=transfers;out["command_identities"]=commands;
    out["leg_identities"]=legs;out["job_identities"]=jobs;
    return out;
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
  std::set<std::size_t> policy_forecast_selection(const std::string& owner,double validity) const {
    const auto& state=runtime_->circulation_state();
    const auto& messages=state.service_forecasts;
    if(indexed_message_selection_ && observation_index_.sync(state,runtime_->circulation_publication_journal()))
      return observation_index_.select_forecasts(owner,physical_time(),validity,messages);
    using Key=std::pair<std::string,std::string>;
    std::map<Key,std::size_t> first,latest;
    std::map<Key,std::vector<std::size_t>> tied_latest;
    std::set<std::size_t> selected;
    const auto revision=[](const auto& m) {
      return std::tie(m.observed_at,m.generation,m.publication_sequence);
    };
    for(std::size_t i=0;i<messages.size();++i) {
      const auto& m=messages[i];
      if(!m.delivered || m.target_owner!=owner || m.status=="withdrawn") continue;
      const Key key{m.source_owner,m.tray_id};
      first.emplace(key,i);
      const auto found=latest.find(key);
      if(found==latest.end() || revision(m)>revision(messages[found->second])) {
        latest[key]=i;tied_latest[key]={i};
      } else if(revision(m)==revision(messages[found->second])) tied_latest[key].push_back(i);
      // Every live revision owns a receiver expiry timer, including a revision
      // already superseded or named by a delivered withdrawal. Keep all of it.
      if(m.status=="conditional" && physical_time()<m.observed_at+validity) selected.insert(i);
    }
    for(const auto& [key,i]:first) selected.insert(i); // historical key insertion order
    for(const auto& [key,indices]:tied_latest) selected.insert(indices.begin(),indices.end());
    std::set<Key> referenced;
    for(const auto i:selected) referenced.emplace(messages[i].source_owner,messages[i].message_id);
    for(std::size_t i=0;i<messages.size();++i) {
      const auto& m=messages[i];
      if(m.delivered && m.target_owner==owner && m.status=="withdrawn" &&
          referenced.count({m.source_owner,m.supersedes})) selected.insert(i);
    }
    // Selection is derived afresh: delayed/out-of-order delivery, restore and
    // a different explicit validity cannot resurrect a pruned native entry.
    // Native history is retained; only Python serialization is bounded here.
    return selected;
  }
  py::dict render_planning_snapshot(const CirculationPlanningSnapshot& m,double read_at) const {
    py::dict body;body["schema"]="g31.planning_capture.v1";
#define PCFIELD(name) body[#name]=m.name
    PCFIELD(message_id);PCFIELD(source_owner);PCFIELD(target_owner);PCFIELD(publication_sequence);
    PCFIELD(captured_at);PCFIELD(valid_until);PCFIELD(static_contract_sha256);
#undef PCFIELD
    py::dict semantics;
#define PSFIELD(name) semantics[#name]=m.name
    PSFIELD(queue_discipline);PSFIELD(resource_semantics);PSFIELD(event_semantics);PSFIELD(scorer_mode);
    PSFIELD(merge_grant_rule);PSFIELD(merge_grant_timing_mode);PSFIELD(minimum_service_seconds);
#undef PSFIELD
    body["semantics"]=semantics;
    py::list jobs,trays,nodes,faults,job_ids,tray_ids,node_ids;
    for(const auto& captured:m.jobs) {
      const auto& j=captured.contract;py::dict row;
#define PJFIELD(name) row[#name]=j.name
      PJFIELD(business_bag_id);PJFIELD(origin);PJFIELD(destination);PJFIELD(arrival);PJFIELD(deadline);
      PJFIELD(storage_node);PJFIELD(storage_release_at);PJFIELD(storage_min_dwell);PJFIELD(load_seconds);
      PJFIELD(unload_seconds);PJFIELD(hold_seconds);PJFIELD(protected_service);PJFIELD(allow_suffix_reroute);
#undef PJFIELD
      row["status"]=captured.status;row["loaded_at"]=captured.loaded_at;
      row["storage_entered_at"]=captured.storage_entered_at;row["storage_released_at"]=captured.storage_released_at;
      jobs.append(row);job_ids.append(j.business_bag_id);
    }
    for(const auto& t:m.trays) {
      py::dict row;
#define PTFIELD(name) row[#name]=t.name
      PTFIELD(tray_id);PTFIELD(business_bag_id);PTFIELD(mode);PTFIELD(ready_kind);PTFIELD(node);PTFIELD(edge_from);
      PTFIELD(edge_to);PTFIELD(reception_node);PTFIELD(generation);PTFIELD(traversal_id);PTFIELD(available_at);
      PTFIELD(service_ready_at);PTFIELD(service_ready_known);PTFIELD(load_complete_at);PTFIELD(committed_prefix);
#undef PTFIELD
      trays.append(row);tray_ids.append(t.tray_id);
    }
    int unrepresented=0;
    for(const auto& n:m.nodes) {
      py::dict row;row["node"]=n.node;row["occupancy"]=n.occupancy;row["actual_available"]=n.actual_available;
      row["unrepresented_occupancy"]=n.unrepresented_occupancy;unrepresented+=n.unrepresented_occupancy;
      nodes.append(row);node_ids.append(n.node);
    }
    for(const auto& f:m.known_faults) {
      py::dict row;row["from"]=f.from;row["to"]=f.to;row["active"]=f.active;row["received_at"]=f.received_at;
      faults.append(row);
    }
    body["jobs"]=jobs;body["trays"]=trays;body["nodes"]=nodes;body["known_faults"]=faults;
    py::dict coverage;coverage["scope"]="source_waiting_or_locally_carried_released_jobs_and_local_trays";
    coverage["complete_for_declared_local_scope"]=true;coverage["local_node_ids"]=node_ids;
    coverage["tray_ids"]=tray_ids;coverage["business_bag_ids"]=job_ids;
    coverage["unrepresented_occupancy"]=unrepresented;coverage["future_arrivals_included"]=false;
    body["coverage"]=coverage;
    py::dict out;out["schema"]="g31.planning_snapshot.v1";out["kind"]="planning_snapshot";
    out["capture"]=body;out["payload_sha256"]=m.payload_sha256;
    out["digest_format"]="g31.planning_capture_digest.v1";out["delivered_at"]=m.delivered_at;
    out["status"]=read_at>=m.valid_until ? "expired" : "conditional";
    return out;
  }
  py::dict render_planning_snapshot_v2(const CirculationPlanningSnapshotV2& m,double read_at) const {
    auto out=render_planning_snapshot(m,read_at);
    py::dict body;body["schema"]="g31.planning_capture.v2";body["local_capture"]=out["capture"];
    py::dict extension;extension["schema"]="g31.planning_extension.v2";
    extension["source_owner"]=m.source_owner;extension["captured_at"]=m.captured_at;
    py::list receipts,completed_ids,node_ids,actions,request_ids,unresolved_ids;
    for(const auto& r:m.terminal_receipts) {
      py::dict row;row["receipt_id"]=r.receipt_id;row["source_local_sequence"]=r.source_local_sequence;
      row["source_owner"]=r.source_owner;row["event"]="UNLOAD_COMPLETE";row["status"]="completed";
      row["business_bag_id"]=r.business_bag_id;row["destination"]=r.destination;
      row["tray_id"]=r.tray_id;row["completed_at"]=r.completed_at;
      receipts.append(row);completed_ids.append(r.business_bag_id);
    }
    for(const auto& n:m.nodes) node_ids.append(n.node);
    py::dict completion;completion["scope"]="all_source_owned_destination_unload_completions_through_capture";
    completion["complete_for_declared_scope"]=true;completion["through"]=m.captured_at;
    completion["source_owned_destination_nodes"]=node_ids;completion["future_events_included"]=false;
    completion["completed_business_bag_ids"]=completed_ids;
    for(const auto& a:m.submitted_physical_actions) {
      py::dict row;row["request_id"]=a.request_id;row["kind"]=a.kind;row["source_owner"]=a.source_owner;
      row["last_delivered_ack"]=py::none();
      if(a.has_delivered_ack) {
        py::dict ack;ack["sequence"]=a.ack_sequence;ack["delivered_at"]=a.ack_delivered_at;ack["status"]=a.ack_status;
        row["last_delivered_ack"]=ack;
      }
      actions.append(row);request_ids.append(a.request_id);if(!a.terminal) unresolved_ids.append(a.request_id);
    }
    py::dict coverage;coverage["scope"]="all_source_submitted_physical_operations_last_delivered_ack";
    coverage["through"]=m.captured_at;coverage["complete_for_declared_scope"]=true;
    coverage["includes_unsubmitted_python_plans"]=false;coverage["uses_hidden_execution_truth"]=false;
    coverage["submitted_request_ids"]=request_ids;coverage["unresolved_request_ids"]=unresolved_ids;
    extension["terminal_receipts"]=receipts;extension["completion_coverage"]=completion;
    extension["submitted_physical_actions"]=actions;extension["action_coverage"]=coverage;
    body["extension"]=extension;out["capture"]=body;out["schema"]="g31.planning_snapshot.v2";
    out["kind"]="planning_snapshot_v2";out["digest_format"]="g31.planning_capture_digest.v2";
    return out;
  }
  py::dict render_planning_snapshot_v3(const CirculationPlanningSnapshotV3& m,double read_at) const {
    auto out=render_planning_snapshot_v2(m,read_at);
    py::dict body;body["schema"]="g31.planning_capture.v3";body["capture_v2"]=out["capture"];
    py::dict extension;extension["schema"]="g31.planning_inflight_receipts.v1";
    extension["source_owner"]=m.source_owner;extension["captured_at"]=m.captured_at;
    py::list entries,inflight_ids,unmatched_ids;
    for(const auto& r:m.source_observed_inflight) {
      py::dict row;row["source_owner"]=r.source_owner;row["receipt_event"]="EDGE_ENTER";
      row["tray_id"]=r.tray_id;row["business_bag_id"]=r.business_bag_id;
      row["generation"]=r.generation;row["traversal_id"]=r.traversal_id;
      row["edge_from"]=r.edge_from;row["edge_to"]=r.edge_to;row["entered_at"]=r.entered_at;
      row["static_edge_travel_seconds"]=r.static_edge_travel_seconds;
      row["derived_edge_exit_at"]=r.derived_edge_exit_at;entries.append(row);
    }
    for(const auto& tray:m.trays) if(tray.edge_to>=0) inflight_ids.append(tray.tray_id);
    for(const auto& id:m.unmatched_inflight_tray_ids) unmatched_ids.append(id);
    py::dict coverage;
    coverage["scope"]="all_current_source_owned_committed_edges_with_matching_observed_entries";
    coverage["source_owned_inflight_tray_ids"]=inflight_ids;coverage["capture_cutoff"]=m.captured_at;
    coverage["complete_for_declared_source_inflight"]=m.unmatched_inflight_tray_ids.empty();
    coverage["unmatched_tray_ids"]=unmatched_ids;coverage["uses_future_event_heap"]=false;
    extension["source_observed_inflight"]=entries;extension["coverage"]=coverage;
    body["extension"]=extension;out["capture"]=body;out["schema"]="g31.planning_snapshot.v3";
    out["kind"]="planning_snapshot_v3";out["digest_format"]="g31.planning_capture_digest.v3";
    return out;
  }
  py::dict render_protocol_request(const CirculationProtocolRequest& client) const {
    const auto& s=runtime_->circulation_state();
    py::dict row;row["request_id"]=s.input.transfers[client.transfer].request_id;
    row["status"]=client.client_status;row["attempt"]=client.attempt;
    row["physical_resolution"]="unknown_without_a_delivered_ack";
    if(client.latest_ack>=0) {
      const auto& ack=s.protocol_acks.at(client.latest_ack);
      py::dict receipt;receipt["sequence"]=ack.sequence;receipt["attempt"]=ack.attempt;
      receipt["observed_at"]=ack.observed_at;receipt["delivered_at"]=ack.delivered_at;
      receipt["status"]=ack.status;receipt["reason"]=ack.reason;receipt["received_at"]=ack.received_at;
      row["last_delivered_ack"]=receipt;
      row["physical_resolution"]="immutable_delivered_snapshot_not_current_truth";
    }
    return row;
  }
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
    sync_binding_indexes();
    const auto found=cancel_identity_index_.find({owner,id});
    if(found!=cancel_identity_index_.end()) for(const auto index:found->second) {
      const auto& c=s.protocol_commands[index];
      if(c.latest_ack>=0 && s.protocol_command_acks[c.latest_ack].status=="cancelled") return true;
    }
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
        std::vector<const CirculationJob*> rows;rows.reserve(message.jobs.size());
        for(const auto index:message.jobs) rows.push_back(&s.input.jobs.at(index));
        const auto signature=canonical_demand_signature(std::move(rows));
        found=captured_demand_digests_.emplace(index,py::cast<std::string>(signature["sha256"])).first;
      }
      py::dict signature;signature["schema"]="g31.demand_signature.v1";
      signature["sha256"]=found->second;signature["waiting_count"]=message.jobs.size();
      row["captured_demand_signature"]=signature;
      row["captured_demand_observed_at"]=message.observed_at;
      row["captured_demand_publication_sequence"]=message.publication_sequence;
    }
    if(command.input.kind=="planning_snapshot" && !ack.result_id.empty() &&
        (ack.status=="delivered" || ack.status=="expired")) {
      const int index=command.native_index;
      if(index<0 || static_cast<std::size_t>(index)>=s.planning_snapshots.size())
        throw py::value_error("circulation:invalid_delivered_planning_ack_reference");
      const auto& message=s.planning_snapshots[index];
      if(message.message_id!=ack.result_id || message.source_owner!=command.input.owner ||
          message.target_owner!=command.input.target_owner || !message.delivered ||
          message.captured_at!=ack.executed_at || message.delivered_at!=ack.completed_at)
        throw py::value_error("circulation:invalid_delivered_planning_ack_reference");
      // A final ACK exposes its immutable captured body, not today's source
      // state; a pending ACK never acquires a later completion's payload.
      row["planning_snapshot"]=render_planning_snapshot(message,ack.completed_at);
    }
    if(command.input.kind=="planning_snapshot_v2" && !ack.result_id.empty() &&
        (ack.status=="delivered" || ack.status=="expired")) {
      const int index=command.native_index;
      if(index<0 || static_cast<std::size_t>(index)>=s.planning_snapshots_v2.size())
        throw py::value_error("circulation:invalid_delivered_planning_v2_ack_reference");
      const auto& message=s.planning_snapshots_v2[index];
      if(message.message_id!=ack.result_id || message.source_owner!=command.input.owner ||
          message.target_owner!=command.input.target_owner || !message.delivered ||
          message.captured_at!=ack.executed_at || message.delivered_at!=ack.completed_at)
        throw py::value_error("circulation:invalid_delivered_planning_v2_ack_reference");
      row["planning_snapshot_v2"]=render_planning_snapshot_v2(message,ack.completed_at);
    }
    if(command.input.kind=="planning_snapshot_v3" && !ack.result_id.empty() &&
        (ack.status=="delivered" || ack.status=="expired")) {
      const int index=command.native_index;
      if(index<0 || static_cast<std::size_t>(index)>=s.planning_snapshots_v3.size())
        throw py::value_error("circulation:invalid_delivered_planning_v3_ack_reference");
      const auto& message=s.planning_snapshots_v3[index];
      if(message.message_id!=ack.result_id || message.source_owner!=command.input.owner ||
          message.target_owner!=command.input.target_owner || !message.delivered ||
          message.captured_at!=ack.executed_at || message.delivered_at!=ack.completed_at)
        throw py::value_error("circulation:invalid_delivered_planning_v3_ack_reference");
      row["planning_snapshot_v3"]=render_planning_snapshot_v3(message,ack.completed_at);
    }
    return row;
  }
  std::map<int,std::string> observation_owners_;
  mutable std::map<int,std::string> captured_demand_digests_;
  // Derived, immutable contract order only. Every query still filters actual
  // released status, so future jobs do not enter signatures or observations.
  std::map<std::string,std::vector<std::size_t>> signature_job_order_;
  std::map<std::string,std::vector<std::size_t>> local_job_order_;
  std::vector<std::size_t> global_fifo_job_order_;
  bool indexed_control_projection_=true;
  bool indexed_message_selection_=true;
  mutable CirculationObservationIndex observation_index_;
  // Derived indexes contain native vector offsets, never Python objects or
  // cached dynamic truth. Append-only identities/receipt facts are indexed;
  // ACK state is read afresh and all indexes are discarded on restore/fork.
  mutable std::size_t indexed_commands_=0,indexed_requests_=0,indexed_receipts_=0;
  mutable std::map<std::pair<std::string,std::string>,std::size_t> command_identity_index_,request_identity_index_;
  mutable std::map<int,std::size_t> transfer_client_index_;
  mutable std::map<std::pair<std::string,std::string>,std::vector<std::size_t>> cancel_identity_index_;
  mutable std::map<std::string,std::vector<std::size_t>> prefix_receipts_,receipts_by_tray_;
  void sync_binding_indexes() const {
    const auto& s=runtime_->circulation_state();
    for(;indexed_commands_<s.protocol_commands.size();++indexed_commands_) {
      const auto& input=s.protocol_commands[indexed_commands_].input;
      command_identity_index_.emplace(std::make_pair(input.owner,input.request_id),indexed_commands_);
      if(input.kind=="cancel_transfer") cancel_identity_index_[{input.owner,input.reference_id}].push_back(indexed_commands_);
    }
    for(;indexed_requests_<s.protocol_requests.size();++indexed_requests_) {
      const auto& client=s.protocol_requests[indexed_requests_];
      request_identity_index_.emplace(std::make_pair(client.owner,s.input.transfers[client.transfer].request_id),indexed_requests_);
      transfer_client_index_.emplace(client.transfer,indexed_requests_);
    }
    for(;indexed_receipts_<s.receipts.size();++indexed_receipts_) {
      const auto& receipt=s.receipts[indexed_receipts_];
      receipts_by_tray_[receipt.tray_id].push_back(indexed_receipts_);
      if(receipt.event=="LEG_START" || receipt.event=="EDGE_EXIT")
        prefix_receipts_[receipt.transport_leg_id].push_back(indexed_receipts_);
    }
  }
  std::vector<std::size_t> local_job_indices(const std::string& owner,const std::set<int>& visible) const {
    std::vector<std::size_t> result;
    const auto found=local_job_order_.find(owner);
    if(found!=local_job_order_.end()) result=found->second;
    bool added=false;
    for(const auto i:visible) if(observation_owner(runtime_->circulation_state().input.jobs[i].origin)!=owner) {
      result.push_back(i);added=true;
    }
    if(added) std::sort(result.begin(),result.end());
    return result;
  }
  void rebuild_observation_owners() {
    observation_index_.clear();
    observation_owners_.clear();
    captured_demand_digests_.clear();
    indexed_commands_=indexed_requests_=indexed_receipts_=0;
    command_identity_index_.clear();request_identity_index_.clear();transfer_client_index_.clear();
    cancel_identity_index_.clear();prefix_receipts_.clear();receipts_by_tray_.clear();local_job_order_.clear();
    for(const auto& node:runtime_->circulation_state().input.nodes)
      observation_owners_.emplace(node.node,node.resource_owner.empty() ? node.zone : node.resource_owner);
    signature_job_order_.clear();global_fifo_job_order_.clear();
    const auto& input=runtime_->circulation_state().input;
    for(std::size_t i=0;i<input.jobs.size();++i) {
      const auto& owner=observation_owner(input.jobs[i].origin);
      signature_job_order_[owner].push_back(i);local_job_order_[owner].push_back(i);
      global_fifo_job_order_.push_back(i);
    }
    // Input validation guarantees unique IDs and finite arrivals. This is
    // the exact former per-query comparator, including UTF-8 byte ordering
    // and equal/signed-zero arrival ties. Future membership is still filtered
    // using only the current lawful local view or a delivered capture.
    std::sort(global_fifo_job_order_.begin(),global_fifo_job_order_.end(),[&](auto a,auto b) {
      const auto& x=input.jobs[a];const auto& y=input.jobs[b];
      return std::tie(x.arrival,x.business_bag_id)<std::tie(y.arrival,y.business_bag_id);
    });
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
    std::set<int> known_ports;
    if(indexed_control_projection_) {
      // Dense offsets refer to immutable validated job contracts, never to
      // current remote state. All visibility and observation times below are
      // recomputed within this call. 1=local shadow, 2=local waiting, 3=remote.
      std::vector<unsigned char> selected(s.input.jobs.size(),0);
      std::vector<double> observed_at(s.input.jobs.size(),0.);
      for(const auto i:local_job_indices(owner,visible_jobs)) {
        const auto& j=s.input.jobs[i];const auto& state=s.jobs[i];
        if(state.status=="unreleased" || (observation_owner(j.origin)!=owner && !visible_jobs.count(static_cast<int>(i)))) continue;
        selected[i]=state.status=="waiting_for_tray" ? 2 : 1;
        observed_at[i]=now;known_ports.insert(j.origin);
      }
      // Keep the exact source-map iteration precedence for overlapping old
      // captures. A local loaded/completed contract still shadows remote FIFO.
      for(const auto& [source,message]:latest_demand) for(const auto index:message->jobs) {
        const auto& j=s.input.jobs.at(index);
        if(selected[index]) continue;
        selected[index]=3;observed_at[index]=message->observed_at;
        known_ports.insert(j.origin);
      }
      for(const auto index:global_fifo_job_order_) if(selected[index]>=2) {
        const auto& j=s.input.jobs[index];
        waiting.push_back({&j.business_bag_id,j.origin,j.arrival,j.deadline,observed_at[index],
            selected[index]==2 ? static_cast<int>(index) : -1});
      }
    } else {
      std::unordered_set<std::string> visible_ids;
      for(const auto i:local_job_indices(owner,visible_jobs)) {
        const auto& j=s.input.jobs[i];const auto& state=s.jobs[i];
        if(state.status=="unreleased" || (observation_owner(j.origin)!=owner && !visible_jobs.count(static_cast<int>(i)))) continue;
        // Local contracts shadow an older delivered remote waiting snapshot,
        // including a currently loaded tray that has crossed the boundary.
        visible_ids.insert(j.business_bag_id);known_ports.insert(j.origin);
        if(state.status=="waiting_for_tray")
          waiting.push_back({&j.business_bag_id,j.origin,j.arrival,j.deadline,now,static_cast<int>(i)});
      }
      for(const auto& [source,message]:latest_demand) for(const auto index:message->jobs) {
        const auto& j=s.input.jobs.at(index);
        if(!visible_ids.insert(j.business_bag_id).second) continue;
        known_ports.insert(j.origin);
        waiting.push_back({&j.business_bag_id,j.origin,j.arrival,j.deadline,message->observed_at,-1});
      }
      std::sort(waiting.begin(),waiting.end(),[](const auto& a,const auto& b) {
        return std::tie(a.arrival,*a.id)<std::tie(b.arrival,*b.id);
      });
    }
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
        const auto found=transfer_client_index_.find(static_cast<int>(i));
        if(found==transfer_client_index_.end()) continue;
        const auto& client=s.protocol_requests[found->second];
        if(client.owner!=owner) continue;
        status=client.latest_ack>=0 ? s.protocol_acks[client.latest_ack].status : "pending";
        received_at=client.latest_ack>=0 ? s.protocol_acks[client.latest_ack].received_at : -1;
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
    .def("observe_protocol_control_policy",&NativeSession::observe_protocol_control_policy,py::arg("owner_id"))
    .def("observe_protocol_control_policy_recent",&NativeSession::observe_protocol_control_policy_recent,
         py::arg("owner_id"),py::arg("forecast_validity"))
    .def("protocol_planning_snapshots",&NativeSession::protocol_planning_snapshots,py::arg("owner_id"))
    .def("protocol_planning_snapshots_v2",&NativeSession::protocol_planning_snapshots_v2,py::arg("owner_id"))
    .def("protocol_planning_snapshots_v3",&NativeSession::protocol_planning_snapshots_v3,py::arg("owner_id"))
    .def("protocol_demand_signature",&NativeSession::protocol_demand_signature,py::arg("owner_id"))
    .def("submit_protocol_command",&NativeSession::submit_protocol_command,py::arg("request"))
    .def("protocol_command",&NativeSession::protocol_command,py::arg("owner_id"),py::arg("request_id"))
    .def("protocol_request",&NativeSession::protocol_request,py::arg("owner_id"),py::arg("request_id"))
    .def("submit_protocol_transfer",&NativeSession::submit_protocol_transfer,py::arg("request"))
    .def("demand_signature",&NativeSession::demand_signature,py::arg("owner_id"))
    .def("_set_indexed_control_projection",&NativeSession::set_indexed_control_projection,py::arg("enabled"))
    .def("_set_indexed_message_selection",&NativeSession::set_indexed_message_selection,py::arg("enabled"))
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
    .def("offline_request_timing_start",&NativeSession::offline_request_timing_start,
         py::arg("capacity"),py::arg("session_identity"))
    .def("offline_request_timing_take",&NativeSession::offline_request_timing_take)
    .def("offline_request_timing_stop",&NativeSession::offline_request_timing_stop)
    .def("result_at",&NativeSession::result_at);
}
