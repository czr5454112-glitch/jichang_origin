#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include "ics_core/runtime/event_driven_junction.hpp"

using namespace czr005::ics;
namespace {
void require(bool condition, const std::string& message) {
  if (!condition) throw std::runtime_error(message);
}
Graph graph() {
  Graph g;
  for (int i=0; i<4; ++i) g.add_node(Node{i,0,0.001,0,0,{}});
  for (auto edge : std::vector<std::pair<int,int>>{{0,1},{1,2},{2,3},{3,0},{0,2}})
    g.add_edge(Edge{edge.first,edge.second,1,1});
  std::vector<std::vector<double>> h(4,std::vector<double>(4,100));
  for (int i=0;i<4;++i) { h[i][i]=0; for(int j:g.outgoing(i)) h[i][j]=1.001; }
  for(int k=0;k<4;++k) for(int i=0;i<4;++i) for(int j=0;j<4;++j)
    h[i][j]=std::min(h[i][j],h[i][k]+h[k][j]);
  g.set_heuristic(h); return g;
}
EventDrivenJunctionConfig config() {
  EventDrivenJunctionConfig c;
  c.queue_discipline="fifo"; c.resource_semantics="R3";
  c.event_semantics="E4_batch_plus_destination_merge_request";
  c.enable_source_admission=false; c.enable_backpressure=false;
  c.enable_pibt_lite=false; c.pressure_mode="off"; c.admission_mode="off";
  c.pibt_mode="P2"; c.priority_mode="Q0"; c.scorer_mode="S4";
  c.merge_grant_rule="M3"; c.merge_grant_timing_mode="J2";
  c.g4irsf20_event_hotpath_policy="E2"; c.local_queue_capacity=0;
  c.max_events=100000; c.max_simulation_time=60; c.trace_limit=10000;
  return c;
}
CirculationInput input() {
  CirculationInput in;
  for(int i=0;i<4;++i) in.nodes.push_back({i,i==0?"A":"B",1,0,true,true});
  for(auto edge:std::vector<std::pair<int,int>>{{0,1},{1,2},{2,3},{3,0},{0,2}})
    in.edges.push_back({edge.first,edge.second,1,0.1});
  in.trays.push_back({"physical-tray",0});
  CirculationJob first;
  first.business_bag_id="bag-a"; first.origin=0; first.destination=3;
  first.storage_node=1; first.storage_release_at=3; first.storage_min_dwell=1;
  first.load_seconds=0.1; first.unload_seconds=0.2; first.hold_seconds=0.3;
  first.deadline=30;
  auto second=first; second.business_bag_id="bag-b"; second.arrival=1;
  in.jobs={first,second};
  in.transfers.push_back({"authorized-return","physical-tray",3,0,0,0.4,0,50});
  return in;
}
void all_boundaries(const std::string& name, CirculationInput in,
                    const std::vector<EventRuntimeFaultWindow>& faults={}) {
  auto g=graph(); auto cfg=config();
  EventDrivenJunctionRuntime expected(g,cfg);
  expected.initialize_circulation(in,faults); expected.drain(); expected.finalize();
  const std::string expected_sha=expected.circulation_state_sha256();
  EventDrivenJunctionRuntime source(g,cfg); source.initialize_circulation(in,faults);
  int count=0, active_capability_boundaries=0, physical_fault_boundaries=0, resource_wait_boundaries=0;
  std::set<std::string> modes, upcoming;
  // Check every actual pre-pop boundary, including siblings while commitments
  // are published but their EDGE_ENTER notifications have not been consumed.
  while (const auto boundary=source.peek_safe_boundary()) {
    if (boundary->next_event_time>cfg.max_simulation_time) break;
    ++count;
    active_capability_boundaries += boundary->active_merge_capability_count>0;
    physical_fault_boundaries += boundary->active_physical_fault_edge_count>0;
    resource_wait_boundaries += !source.circulation_state().resource_waits.empty();
    for (const auto& tray:source.circulation_state().trays) modes.insert(tray.mode);
    upcoming.insert(junction_event_name(boundary->next_event_type));
    const auto cp=source.capture_state_checkpoint();
    require(cp.state_sha256()==source.circulation_state_sha256(),"capture seal mismatch");
    auto equal_graph=graph(); // independent immutable graph, not source address
    EventDrivenJunctionRuntime a(equal_graph,cfg), b(g,cfg);
    a.restore_state_checkpoint(cp); b.restore_state_checkpoint(cp);
    const auto parent_sha=source.circulation_state_sha256();
    require(a.circulation_state_sha256()==parent_sha && b.circulation_state_sha256()==parent_sha,
            "initial sibling state differs at "+std::to_string(count));
    require(a.process_one_event(),"sibling failed to consume event");
    require(source.circulation_state_sha256()==parent_sha && b.circulation_state_sha256()==parent_sha,
            "sibling execution mutated source or immutable checkpoint payload");
    a.restore_state_checkpoint(cp);
    require(a.circulation_state_sha256()==parent_sha,"restoring into a live sibling differs");
    a.drain(); a.finalize(); b.drain(); b.finalize();
    require(a.circulation_state_sha256()==expected_sha && b.circulation_state_sha256()==expected_sha,
            "continuation mismatch "+name+" boundary "+std::to_string(count));
    require(source.process_one_event(),"source failed before expected event");
  }
  source.drain(); source.finalize();
  require(source.circulation_state_sha256()==expected_sha,"stepped source differs from drain");
  require(count>10,"fixture did not exercise live circulation");
  if(name=="cycle") {
    for(const std::string mode:{"loading","storage","unloading","hold","empty"})
      require(modes.count(mode)!=0,"missing lifecycle checkpoint mode "+mode);
    require(active_capability_boundaries>0,"J2 live capability was not checkpointed");
  }
  if(!faults.empty()) require(physical_fault_boundaries>0,"fault fixture never checkpointed actual fault");
  if(name=="headway_resource_wait") require(resource_wait_boundaries>0,
                                           "resource-wait dependency index was not exercised");
  std::cout<<"{\"scenario\":\""<<name<<"\",\"boundaries\":"<<count
           <<",\"active_capability_boundaries\":"<<active_capability_boundaries
           <<",\"physical_fault_boundaries\":"<<physical_fault_boundaries
           <<",\"resource_wait_boundaries\":"<<resource_wait_boundaries
           <<",\"final_state_sha256\":\""<<expected_sha<<"\"}\n";
}
void invalid_restore_and_identity() {
  auto g=graph(); auto cfg=config(); EventDrivenJunctionRuntime source(g,cfg);
  source.initialize_circulation(input()); const auto cp=source.capture_state_checkpoint();
  auto bad=cp; bad.test_corrupt_seal();
  EventDrivenJunctionRuntime target(g,cfg); target.initialize_circulation(input());
  bool rejected=false;
  try { target.restore_state_checkpoint(bad); } catch(const std::invalid_argument&) { rejected=true; }
  require(rejected && target.phase()==EventDrivenJunctionRuntimePhase::kIdle,"bad seal did not fail closed");
  rejected=false;
  try { (void)target.advance_circulation_to(1,1000); } catch(const std::logic_error&) { rejected=true; }
  require(rejected && target.phase()==EventDrivenJunctionRuntimePhase::kIdle,
          "control advance revived failed-checkpoint target");
  auto wrong=graph(); wrong.node(0).service_time=0.5;
  EventDrivenJunctionRuntime wrong_target(wrong,cfg); rejected=false;
  try { wrong_target.restore_state_checkpoint(cp); } catch(const std::invalid_argument&) { rejected=true; }
  require(rejected && wrong_target.phase()==EventDrivenJunctionRuntimePhase::kIdle,"different graph accepted");
  auto changed=input(); changed.edges[0].entry_headway=0.5;
  EventDrivenJunctionRuntime headway(g,cfg); headway.initialize_circulation(changed);
  require(headway.circulation_state_sha256()!=source.circulation_state_sha256(),"headway omitted from seal");
  changed=input(); changed.jobs[1].arrival=5;
  EventDrivenJunctionRuntime future(g,cfg); future.initialize_circulation(changed);
  require(future.circulation_state_sha256()!=source.circulation_state_sha256(),"future input omitted from offline seal");
  source.drain(); source.finalize(); rejected=false;
  try { (void)source.capture_state_checkpoint(); } catch(const std::logic_error&) { rejected=true; }
  require(rejected,"finalized runtime incorrectly advertised live pre-pop checkpoint");
}
void online_message_and_action_isolation() {
  auto g=graph(); auto cfg=config(); EventDrivenJunctionRuntime source(g,cfg);
  source.initialize_circulation(input());
  source.advance_circulation_to(1.0,10000);
  require(source.publish_circulation_demand("A","B",0.3)=="pending","demand publication failed");
  require(source.circulation_state().demand_messages.back().jobs.size()==1,
          "only currently waiting released demand should enter message");
  CirculationRouteIntent route;
  route.request_id="delayed-route"; route.owner_id="B"; route.business_bag_id="bag-a";
  route.tray_id="physical-tray"; route.from=1; route.next=2;
  route.expected_generation=1; route.expiry=10;
  require(source.submit_circulation_route(route,0.2)=="pending","route publication failed");
  const auto cp=source.capture_state_checkpoint();
  const auto original=source.circulation_state_sha256();
  EventDrivenJunctionRuntime a(g,cfg), b(g,cfg);
  a.restore_state_checkpoint(cp); b.restore_state_checkpoint(cp);
  require(a.cancel_circulation_transfer("authorized-return","B")=="cancelled",
          "authorized uncommitted branch treatment failed");
  require(a.circulation_state_sha256()!=original,"branch action not bound by circulation digest");
  require(source.circulation_state_sha256()==original && b.circulation_state_sha256()==original,
          "cancelling branch transfer mutated parent or sibling");
  source.drain(); source.finalize(); b.drain(); b.finalize(); a.drain(); a.finalize();
  require(b.circulation_state_sha256()==source.circulation_state_sha256(),
          "delayed message/no-op branch continuation differs");
  require(b.circulation_state().demand_messages[0].delivered &&
          b.circulation_state().jobs[1].status=="completed",
          "restored native message or transfer was lost");
  require(a.circulation_state().jobs[1].status!="completed" &&
          a.circulation_state().transfers[0].status=="cancelled",
          "different branch action failed to affect physical continuation");
}
void quiescent_control_boundary() {
  auto g=graph(); auto cfg=config(); auto in=input(); in.transfers.clear();
  EventDrivenJunctionRuntime source(g,cfg); source.initialize_circulation(in); source.drain();
  require(source.phase()==EventDrivenJunctionRuntimePhase::kStopped &&
          !source.next_physical_event_time(),"fixture must be an unfinalized physically quiescent world");
  require(source.circulation_state().jobs[1].status=="waiting_for_tray",
          "quiescence must retain offered unfinished demand");
  const auto cp=source.capture_state_checkpoint(); const auto original=source.circulation_state_sha256();
  EventDrivenJunctionRuntime a(g,cfg), b(g,cfg);
  a.restore_state_checkpoint(cp); b.restore_state_checkpoint(cp);
  auto transfer=input().transfers[0]; transfer.request_id="live:authorized-return";
  transfer.earliest_departure=20; transfer.message_delay=0;
  require(a.submit_circulation_transfer(transfer,"B")=="pending","quiescent control could not restart native events");
  require(source.circulation_state_sha256()==original && b.circulation_state_sha256()==original,
          "inserting new native messages mutated quiescent siblings");
  a.drain(); a.finalize();
  require(a.circulation_state().jobs[1].status=="completed" &&
          b.circulation_state().jobs[1].status=="waiting_for_tray",
          "quiescent treatment did not produce distinct real continuation");
}
void static_closed_domain_routes() {
  for(int closed: {0,1}) {
    Graph g;
    for(int n=0;n<4;++n) g.add_node(Node{n,0,0.05,0,0,{}});
    const std::vector<Edge> edges={{0,1,1,1},{1,3,1,1},{0,2,2,1},{2,3,2,1}};
    for(const auto& edge:edges) g.add_edge(edge);
    std::vector<std::vector<double>> h(4,std::vector<double>(4,100));
    for(int n=0;n<4;++n) h[n][n]=0;
    for(const auto& edge:edges) h[edge.start][edge.end]=edge.travel_time()+0.05;
    for(int k=0;k<4;++k) for(int i=0;i<4;++i) for(int j=0;j<4;++j)
      h[i][j]=std::min(h[i][j],h[i][k]+h[k][j]);
    g.set_heuristic(h);
    CirculationInput in;
    for(int n=0;n<4;++n) in.nodes.push_back({n,n==0?"A":"B",1,0,true,true});
    for(std::size_t i=0;i<edges.size();++i)
      in.edges.push_back({edges[i].start,edges[i].end,static_cast<int>(i)==closed?0:1,0.1});
    in.trays.push_back({"finite-tray",0});
    CirculationJob job; job.business_bag_id="direct-job";job.origin=0;job.destination=3;
    job.unload_seconds=0.1;job.deadline=30;in.jobs.push_back(job);
    const auto old_edges=g.edge_count(); const double original_h=g.heuristic(0,3);
    EventDrivenJunctionRuntime source(g,config());source.initialize_circulation(in);
    require(g.edge_count()==old_edges && g.heuristic(0,3)==original_h,
            "circulation static domain modified original graph/legacy heuristic");
    require(source.circulation_static_reachable(0,3) && source.circulation_static_reachable(2,3),
            "positive-capacity alternative omitted from static domain");
    if(closed==1) require(!source.circulation_static_reachable(1,3),
                         "closed downstream suffix falsely reachable");
    require(source.circulation_static_potential(0,3)>original_h,
            "routing still uses the shorter path through a closed edge");
    const auto cp=source.capture_state_checkpoint(); EventDrivenJunctionRuntime branch(g,config());
    branch.restore_state_checkpoint(cp);
    source.drain();source.finalize();branch.drain();branch.finalize();
    require(source.circulation_state().jobs[0].status=="completed",
            "static closed domain failed to choose existing positive-capacity path");
    require(source.circulation_state_sha256()==branch.circulation_state_sha256(),
            "static routing-domain cache did not survive exact checkpoint");
    std::vector<std::pair<int,int>> actual;
    for(const auto& r:source.circulation_state().receipts)
      if(r.event=="EDGE_ENTER") actual.push_back({r.from,r.to});
    require(actual==std::vector<std::pair<int,int>>{{0,2},{2,3}},
            "carrier entered static closed edge or unreachable suffix");
  }
}
void delayed_service_forecast() {
  auto g=graph();auto cfg=config();auto in=input();in.transfers.clear();
  EventDrivenJunctionRuntime source(g,cfg);source.initialize_circulation(in);
  require(source.publish_circulation_service_forecast("A","B","physical-tray",1,0.4)==
          "rejected:no_local_uncommitted_loaded_service","unreleased job forecast was allowed");
  source.advance_circulation_to(0.05,10000);
  require(source.publish_circulation_service_forecast("B","A","physical-tray",1,0)==
          "rejected:tray_not_visible_to_owner","foreign owner published a live tray forecast");
  const auto before=source.circulation_state_sha256();
  require(source.publish_circulation_service_forecast("A","B","physical-tray",1,0.4)=="pending",
          "observed loading forecast rejected");
  require(source.circulation_state_sha256()!=before,"forecast omitted from full checkpoint seal");
  const auto snapshot=source.circulation_state().service_forecasts.at(0);
  require(!snapshot.delivered && snapshot.observed_at==0.05 && snapshot.delivered_at==0.45 &&
          std::abs(snapshot.entry_estimate-0.101)<1e-12 &&
          std::abs(snapshot.release_estimate-1.102)<1e-12 && snapshot.generation==1 &&
          snapshot.traversal_id==0 && snapshot.status=="conditional","forecast did not use actual load start/public contract");
  const auto cp=source.capture_state_checkpoint();EventDrivenJunctionRuntime branch(g,cfg);
  branch.restore_state_checkpoint(cp);branch.advance_circulation_to(0.45,10000);
  require(!source.circulation_state().service_forecasts.at(0).delivered &&
          branch.circulation_state().service_forecasts.at(0).delivered,
          "delayed forecast was lost or delivery leaked across siblings");
  const auto& delivered=branch.circulation_state().service_forecasts.at(0);
  require(delivered.entry_estimate==snapshot.entry_estimate && delivered.release_estimate==snapshot.release_estimate &&
          delivered.traversal_id==snapshot.traversal_id && delivered.generation==snapshot.generation,
          "message delivery silently refreshed immutable forecast");
  source.advance_circulation_to(0.45,10000);
  require(source.circulation_state_sha256()==branch.circulation_state_sha256(),"forecast continuation differs after restore");
  require(source.publish_circulation_service_forecast("A","B","physical-tray",1,0)==
          "rejected:no_local_uncommitted_loaded_service","entered edge was forecast as uncommitted");
  auto future=in;future.jobs[1].arrival=40;
  EventDrivenJunctionRuntime hidden(g,cfg);hidden.initialize_circulation(future,{{2,3,30,35,1,false}});
  hidden.advance_circulation_to(0.05,10000);
  require(hidden.publish_circulation_service_forecast("A","B","physical-tray",1,0.4)=="pending","future variant rejected");
  const auto& same=hidden.circulation_state().service_forecasts.at(0);
  require(same.message_id==snapshot.message_id && same.entry_estimate==snapshot.entry_estimate &&
          same.release_estimate==snapshot.release_estimate && same.observed_at==snapshot.observed_at &&
          same.delivered_at==snapshot.delivered_at && same.business_bag_id==snapshot.business_bag_id,
          "future jobs/fault tape changed forecast payload");
}
void online_transfer_future_isolation() {
  auto g=graph();auto cfg=config();auto first=input();first.transfers.clear();
  auto second=first;auto future=input().transfers[0];future.issued_at=40;
  second.transfers.push_back(future);
  EventDrivenJunctionRuntime a(g,cfg),b(g,cfg);a.initialize_circulation(first);b.initialize_circulation(second);
  const auto a0=a.circulation_state_sha256(),b0=b.circulation_state_sha256();
  require(a.cancel_circulation_transfer(future.request_id,"B")=="rejected:unknown_request" &&
          b.cancel_circulation_transfer(future.request_id,"B")=="rejected:unknown_request",
          "cancellation disclosed or modified an unissued future request");
  require(a.submit_circulation_transfer(future,"B")=="rejected:online_request_namespace_required" &&
          b.submit_circulation_transfer(future,"B")=="rejected:online_request_namespace_required",
          "submitted identifier queried the hidden tape namespace");
  require(a.circulation_state_sha256()==a0 && b.circulation_state_sha256()==b0,
          "rejected future request lookup changed state");
  auto online=future;online.request_id="live:new-current-intent";online.source=0;online.destination=3;
  require(a.submit_circulation_transfer(online,"A")=="pending" &&
          b.submit_circulation_transfer(online,"A")=="pending","valid online namespace depends on hidden requests");
  require(a.cancel_circulation_transfer(online.request_id,"A")=="cancelled" &&
          b.cancel_circulation_transfer(online.request_id,"A")=="cancelled","live cancellation depends on hidden requests");
  auto invalid=first;invalid.transfers.push_back(online);bool rejected=false;
  try { EventDrivenJunctionRuntime wrong(g,cfg);wrong.initialize_circulation(invalid); }
  catch(const std::invalid_argument& e) { rejected=std::string(e.what())=="circulation:reserved_live_request_namespace"; }
  require(rejected,"preloaded tape occupied online request namespace");
  auto changed=cfg;changed.minimum_service_seconds=0.25;
  EventDrivenJunctionRuntime custom(g,changed);custom.initialize_circulation(first);
  a.restore_state_checkpoint(custom.capture_state_checkpoint());
  require(a.circulation_minimum_service_seconds()==0.25,"restored public operation floor still uses target constructor config");
}
void forecast_withdrawal_checkpoint() {
  auto g=graph();auto cfg=config();auto in=input();in.transfers.clear();
  EventDrivenJunctionRuntime source(g,cfg);source.initialize_circulation(in);
  source.advance_circulation_to(0.05,10000);
  require(source.publish_circulation_service_forecast("A","B","physical-tray",1,2)=="pending",
          "initial forecast failed");
  const auto original=source.circulation_state().service_forecasts[0];
  require(original.publication_sequence==1,"first channel sequence was not local");
  source.advance_circulation_to(0.5,10000);
  const auto physical=source.circulation_state().trays;
  require(source.withdraw_circulation_service_forecast("B",original.message_id,0)=="rejected:unknown_owned_forecast",
          "nonpublisher withdrew forecast");
  require(source.withdraw_circulation_service_forecast("A",original.message_id,0.1)=="pending","withdrawal failed");
  const auto state=source.circulation_state_sha256();
  require(source.withdraw_circulation_service_forecast("A",original.message_id,0.1)=="duplicate:withdrawal_pending",
          "repeated withdrawal not idempotent");
  require(source.circulation_state_sha256()==state,"duplicate withdrawal changed event heap or counters");
  require(source.circulation_state().trays[0].active_leg==physical[0].active_leg &&
          source.circulation_state().trays[0].edge_to==physical[0].edge_to,"soft withdrawal altered committed motion");
  EventDrivenJunctionRuntime branch(g,cfg);branch.restore_state_checkpoint(source.capture_state_checkpoint());
  source.advance_circulation_to(0.6,10000);
  require(!source.circulation_state().service_forecasts[0].delivered &&
          source.circulation_state().service_forecasts[1].delivered &&
          source.circulation_state().service_forecasts[1].supersedes==original.message_id &&
          source.circulation_state().service_forecasts[1].publication_sequence==2,
          "withdrawal did not arrive before its immutable original");
  source.advance_circulation_to(2.05,10000);branch.advance_circulation_to(2.05,10000);
  require(source.circulation_state_sha256()==branch.circulation_state_sha256(),"withdrawal pending checkpoint lost state");
  require(source.circulation_state().service_forecasts[0].entry_estimate==original.entry_estimate,
          "withdrawal rewrote original forecast");
}
}
int main() {
  try {
    all_boundaries("cycle",input());
    all_boundaries("delayed_fault",input(),{{3,0,5.7,7.0,0.4,false}});
    all_boundaries("lost_notification",input(),{{0,2,0.5,4.0,0.3,true}});
    auto expired=input(); expired.transfers[0].expiry=0.3;
    all_boundaries("expired_message",expired);
    auto tail=input(); tail.edges[0].entry_headway=25; tail.edges[4].capacity=0;
    all_boundaries("headway_resource_wait",tail);
    invalid_restore_and_identity();
    online_message_and_action_isolation();
    quiescent_control_boundary();
    static_closed_domain_routes();
    delayed_service_forecast();
    online_transfer_future_isolation();
    forecast_withdrawal_checkpoint();
  } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
  std::cout<<"circulation checkpoint restore, sibling isolation, graph identity and boundary coverage passed\n";
  return 0;
}
