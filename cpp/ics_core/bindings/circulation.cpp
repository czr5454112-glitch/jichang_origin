#include <chrono>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "ics_core/runtime/event_driven_junction.hpp"

namespace py = pybind11;
using namespace czr005::ics;

namespace {
template<class T> T field(const py::dict& d, const char* k, T fallback) {
  return d.contains(k) ? py::cast<T>(d[k]) : fallback;
}
template<class T> T required(const py::dict& d, const char* k) { return py::cast<T>(d[k]); }

EventDrivenJunctionConfig g31_config(const py::dict& options) {
  EventDrivenJunctionConfig c;
  // Mature build_s4_request + its frozen G14 controls, without a learned scorer.
  c.queue_discipline = "fifo";
  c.resource_semantics = "R3_java_node_window_compatible";
  c.event_semantics = "E4_batch_plus_destination_merge_request";
  c.enable_source_admission = false;
  c.enable_backpressure = false;
  c.enable_pibt_lite = false;
  c.enable_deadlock_escape = true;
  c.enable_fault_policy = true;
  c.pressure_mode = "off";
  c.admission_mode = "off";
  c.pibt_mode = "P2";
  c.priority_mode = "Q0";
  c.scorer_mode = field<std::string>(options, "scorer_mode", "S4_queue_aware_rule_only");
  if (c.scorer_mode != "S4_queue_aware_rule_only" && c.scorer_mode != "S3_shortest_potential_only")
    throw py::value_error("circulation binding supports S4 or S3 same-model reference only");
  c.merge_grant_rule = "M3";
  c.merge_grant_timing_mode = "jit_fair_aging_deadline";
  c.merge_grant_max_pending_requests = 256;
  c.merge_grant_lifecycle_limit = 8192;
  c.g4irsf20_event_hotpath_policy = "E2";
  c.g4irsf16_supervisor_mode = "off";
  c.local_queue_capacity = 0;
  c.max_simulation_time = field<double>(options,"max_simulation_time",-1.0);
  c.max_events = field<int>(options,"max_events",1000000);
  c.max_decisions_per_bag = field<int>(options,"max_decisions_per_bag",512);
  c.trace_limit = field<int>(options,"trace_limit",100000);
  c.event_trace_limit = c.trace_limit;
  return c;
}
CirculationInput read_input(const py::dict& data) {
  CirculationInput in;
  if(data.contains("owner_notifications"))
    in.owner_notifications_enabled=field<bool>(py::cast<py::dict>(data["owner_notifications"]),"enabled",false);
  if(data.contains("owner_protocol")) {
    const auto d=py::cast<py::dict>(data["owner_protocol"]);
    auto& p=in.owner_protocol;
    p.enabled=field<bool>(d,"enabled",false);p.ack_delay=field<double>(d,"ack_delay",0);
    p.timeout=field<double>(d,"timeout",1);p.drop_ack_packets=field<int>(d,"drop_ack_packets",0);
    p.duplicate_acks=field<bool>(d,"duplicate_acks",false);
    p.duplicate_ack_delay=field<double>(d,"duplicate_ack_delay",0);
    if(d.contains("owner_outages")) for(auto h:d["owner_outages"]) {
      const auto outage=py::cast<py::dict>(h);
      p.outages.push_back({required<std::string>(outage,"owner"),required<double>(outage,"start"),required<double>(outage,"end")});
    }
  }
  for (auto h : data["node_contracts"]) {
    auto d=py::cast<py::dict>(h);
    in.nodes.push_back({required<int>(d,"node"),required<std::string>(d,"zone"),
      required<int>(d,"capacity"),field<int>(d,"export_min_stock",0),
      field<bool>(d,"allow_export",true),field<bool>(d,"allow_receive",true),
      field<std::string>(d,"control_partition",""),field<std::string>(d,"resource_owner","")});
  }
  for (auto h : data["edge_contracts"]) {
    auto d=py::cast<py::dict>(h);
    in.edges.push_back({required<int>(d,"from"),required<int>(d,"to"),
      required<int>(d,"capacity"),required<double>(d,"entry_headway")});
  }
  for (auto h : data["trays"]) {
    auto d=py::cast<py::dict>(h);
    in.trays.push_back({required<std::string>(d,"tray_id"),required<int>(d,"node")});
  }
  for (auto h : data["jobs"]) {
    auto d=py::cast<py::dict>(h); CirculationJob j;
    j.business_bag_id=required<std::string>(d,"business_bag_id");
    j.origin=required<int>(d,"origin"); j.destination=required<int>(d,"destination");
    j.arrival=required<double>(d,"arrival"); j.deadline=required<double>(d,"deadline");
    j.storage_node=field<int>(d,"storage_node",-1);
    j.storage_release_at=field<double>(d,"storage_release_at",0);
    j.storage_min_dwell=field<double>(d,"storage_min_dwell",0);
    j.load_seconds=field<double>(d,"load_seconds",0);
    j.unload_seconds=required<double>(d,"unload_seconds");
    j.hold_seconds=required<double>(d,"hold_seconds");
    j.protected_service=field<bool>(d,"protected_service",true);
    j.allow_suffix_reroute=field<bool>(d,"allow_suffix_reroute",false); in.jobs.push_back(j);
  }
  for (auto h : data["transfers"]) {
    auto d=py::cast<py::dict>(h); CirculationTransfer t;
    t.request_id=required<std::string>(d,"request_id"); t.tray_id=required<std::string>(d,"tray_id");
    if(t.request_id.rfind("live:",0)==0)
      throw std::invalid_argument("circulation:reserved_live_request_namespace");
    t.source=required<int>(d,"source"); t.destination=required<int>(d,"destination");
    t.issued_at=required<double>(d,"issued_at"); t.message_delay=required<double>(d,"message_delay");
    t.earliest_departure=required<double>(d,"earliest_departure"); t.expiry=required<double>(d,"expiry");
    in.transfers.push_back(t);
  }
  return in;
}
struct HostDefinition { Graph graph; EventDrivenJunctionConfig config; std::vector<EventRuntimeFaultWindow> faults; };
HostDefinition parse_host(const py::dict& data, const std::string& mode) {
  if (mode != "circulation" && mode != "legacy_g31") throw py::value_error("unknown host mode");
  Graph graph;
  std::set<int> declared_nodes;
  std::set<std::pair<int,int>> declared_edges;
  for (auto h : data["node_records"]) {
    auto r=py::cast<py::sequence>(h);
    if (mode == "circulation" && (py::len(r) != 6 || py::cast<int>(r[0]) < 0 ||
        !declared_nodes.insert(py::cast<int>(r[0])).second))
      throw py::value_error("circulation:invalid_graph_node_record");
    graph.add_node(Node{py::cast<int>(r[0]),py::cast<int>(r[1]),py::cast<double>(r[2]),
      py::cast<int>(r[3]),py::cast<int>(r[4]),py::cast<std::vector<int>>(r[5])});
  }
  for (auto h : data["edge_records"]) {
    auto r=py::cast<py::sequence>(h);
    if (mode == "circulation" && (py::len(r) != 4 ||
        !declared_edges.emplace(py::cast<int>(r[0]),py::cast<int>(r[1])).second))
      throw py::value_error("circulation:invalid_graph_edge_record");
    graph.add_edge(Edge{py::cast<int>(r[0]),py::cast<int>(r[1]),py::cast<double>(r[2]),py::cast<double>(r[3])});
  }
  auto heuristic=required<std::vector<std::vector<double>>>(data,"heuristic_time");
  if(mode == "circulation") {
    if(declared_nodes.empty()) throw py::value_error("circulation:empty_graph");
    const auto dimension=static_cast<std::size_t>(*declared_nodes.rbegin())+1;
    if(heuristic.size()!=dimension) throw py::value_error("circulation:invalid_heuristic_shape");
    for(const auto& row:heuristic) {
      if(row.size()!=dimension) throw py::value_error("circulation:invalid_heuristic_shape");
      for(double value:row)
        if(!std::isfinite(value) || value < 0) throw py::value_error("circulation:invalid_heuristic_value");
    }
  }
  graph.set_heuristic(std::move(heuristic));
  auto options=field<py::dict>(data,"options",py::dict());
  auto config=g31_config(options);
  std::vector<EventRuntimeFaultWindow> faults;
  for (auto h : field<py::list>(data,"faults",py::list())) {
    auto d=py::cast<py::dict>(h);
    faults.push_back({required<int>(d,"from"),required<int>(d,"to"),required<double>(d,"start"),
      required<double>(d,"end"),field<double>(d,"message_delay",0),field<bool>(d,"drop_notification",false)});
  }
  return {std::move(graph),std::move(config),std::move(faults)};
}
py::dict render_result(EventDrivenJunctionRuntime& runtime, const std::string& mode,
                       const std::vector<double>& event_ms, bool finish) {
  const auto& result=finish ? runtime.finalize() : runtime.current_result();
  py::dict out; out["schema"]="g31.circulation.execution.v1"; out["mode"]=mode;
  out["optimality"]="unknown"; out["native_event_ms"]=event_ms;
  py::dict summary;
#define SUMMARY(name) summary[#name]=result.summary.name
  SUMMARY(event_count); SUMMARY(completed_count); SUMMARY(failed_count); SUMMARY(runtime_seconds);
  SUMMARY(edge_enter_event_count); SUMMARY(edge_exit_event_count); SUMMARY(reservation_conflicts);
  SUMMARY(physical_fault_edge_entry_violation_count); SUMMARY(merge_grant_timing_mode);
  SUMMARY(g4irsf20_event_hotpath_policy); SUMMARY(local_queue_capacity);
#undef SUMMARY
  out["native_summary"]=summary;
  py::list transport;
  for(const auto& b:result.bags) {
    py::dict d;
#define FIELD(name) d[#name]=b.name
    FIELD(segment_id);FIELD(runtime_bag_id);FIELD(task_id);FIELD(start);FIELD(goal);FIELD(final_node);
    FIELD(release_time);FIELD(finish_time);FIELD(completed);FIELD(failure_reason);
    FIELD(edge_travel_time_seconds);FIELD(node_service_time_seconds);FIELD(decision_count);
#undef FIELD
    transport.append(d);
  } out["transport_legs"]=transport;
  py::list events;
  for(const auto& e:result.events) {
    py::dict d;
#define FIELD(name) d[#name]=e.name
    FIELD(seq);FIELD(event);FIELD(time);FIELD(runtime_bag_id);FIELD(segment_id);FIELD(node);
    FIELD(from_node);FIELD(to_node);FIELD(reason);
#undef FIELD
    events.append(d);
  } out["native_events"]=events;
  py::list decisions;
  for(const auto& e:result.decisions) {
    py::dict d;
#define FIELD(name) d[#name]=e.name
    FIELD(event_time);FIELD(runtime_bag_id);FIELD(current_node);FIELD(goal_node);FIELD(selected_next);
    FIELD(scorer_id);FIELD(scorer_effective_id);FIELD(full_astar_used);FIELD(decision_source);
#undef FIELD
    py::list candidates;
    for(const auto& c:e.candidates) {
      py::dict row; row["next_node"]=c.next_node; row["shield_allowed"]=c.shield_allowed;
      row["shield_reason"]=c.shield_reason; row["model_score"]=c.model_score; candidates.append(row);
    } d["candidates"]=candidates; decisions.append(d);
  } out["decisions"]=decisions;
  if(mode == "circulation") {
    const auto& state=runtime.circulation_state();
    py::list receipts,jobs,trays,transfers,identities;
    for(const auto& r:state.receipts) {
      py::dict d;
#define FIELD(name) d[#name]=r.name
      FIELD(time);FIELD(event);FIELD(business_bag_id);FIELD(transport_leg_id);FIELD(tray_id);
      FIELD(traversal_id);FIELD(node);FIELD(from);FIELD(to);FIELD(reason);
#undef FIELD
      receipts.append(d);
    }
    for(std::size_t i=0;i<state.jobs.size();++i) {
      const auto& r=state.jobs[i]; py::dict d; d["business_bag_id"]=state.input.jobs[i].business_bag_id;
#define FIELD(name) d[#name]=r.name
      FIELD(status);FIELD(tray);FIELD(loaded_at);FIELD(storage_entered_at);FIELD(storage_released_at);
      FIELD(completed_at);FIELD(deadline_met);
#undef FIELD
      jobs.append(d);
    }
    for(const auto& r:state.trays) {
      py::dict d;
#define FIELD(name) d[#name]=r.name
      FIELD(tray_id);FIELD(node);FIELD(mode);FIELD(job);FIELD(active_leg);FIELD(edge_from);FIELD(edge_to);
      FIELD(reception_node);FIELD(available_at);FIELD(traversal_id);
#undef FIELD
      trays.append(d);
    }
    for(std::size_t i=0;i<state.transfers.size();++i) {
      const auto& r=state.transfers[i]; py::dict d; d["request_id"]=state.input.transfers[i].request_id;
#define FIELD(name) d[#name]=r.name
      FIELD(status);FIELD(reason);FIELD(tray);FIELD(delivered_at);FIELD(departed_at);FIELD(received_at);
#undef FIELD
      transfers.append(d);
    }
    for(const auto& r:state.legs) {
      py::dict d;
#define FIELD(name) d[#name]=r.name
      FIELD(runtime_id);FIELD(transport_leg_id);FIELD(tray);FIELD(job);FIELD(kind);
#undef FIELD
      identities.append(d);
    }
    out["receipts"]=receipts;out["jobs"]=jobs;out["trays"]=trays;out["transfers"]=transfers;
    out["leg_identities"]=identities;out["physical_clock"]=runtime.progress_snapshot().simulated_time;
  }
  return out;
}
py::dict run(const py::dict& data, const std::string& mode) {
  auto host=parse_host(data,mode);
  EventDrivenJunctionRuntime runtime(host.graph,host.config);
  const auto& faults=host.faults;
  if (mode == "circulation") runtime.initialize_circulation(read_input(data),faults);
  else {
    std::vector<EventRuntimeBagRequest> requests;
    for(auto h : data["bag_records"]) {
      auto r=py::cast<py::sequence>(h);
      requests.push_back({py::cast<std::string>(r[0]),py::cast<int>(r[1]),py::cast<double>(r[2]),
        py::cast<double>(r[3]),py::cast<int>(r[4]),py::cast<int>(r[5]),py::cast<std::string>(r[6])});
    }
    runtime.initialize(requests,faults);
  }
  std::vector<double> event_ms;
  while(runtime.phase()==EventDrivenJunctionRuntimePhase::kReady) {
    const auto start=std::chrono::steady_clock::now(); runtime.process_one_event();
    event_ms.push_back(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());
  }
  return render_result(runtime,mode,event_ms,true);
}

#include "circulation_session_binding.hpp"

} // namespace

PYBIND11_MODULE(czr005_circulation,module) {
  module.doc()="Finite tray lifecycle on the mature G31 native event runtime";
  module.def("run",&run,py::arg("input"),py::arg("mode")="circulation");
  bind_session(module);
}
