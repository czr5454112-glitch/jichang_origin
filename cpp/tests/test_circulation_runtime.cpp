#include <iostream>
#include <stdexcept>
#include <string>
#include "ics_core/runtime/event_driven_junction.hpp"

using namespace czr005::ics;

namespace {
void require(bool ok, const std::string& message) {
  if (!ok) throw std::runtime_error(message);
}
Graph graph() {
  Graph g;
  for (int i=0;i<4;++i) g.add_node(Node{i,0,0.001,0,0,{}});
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
  c.max_events=100000; c.max_simulation_time=100; c.trace_limit=10000;
  return c;
}
CirculationInput input(double offset=0) {
  CirculationInput in;
  for(int i=0;i<4;++i) in.nodes.push_back({i,i==0?"A":"B",1,0,true,true});
  for(auto edge:std::vector<std::pair<int,int>>{{0,1},{1,2},{2,3},{3,0},{0,2}})
    in.edges.push_back({edge.first,edge.second,1,0.1});
  in.trays.push_back({"physical-tray",0});
  CirculationJob first;
  first.business_bag_id="bag-a"; first.origin=0; first.destination=3;
  first.arrival=offset; first.storage_node=1; first.storage_release_at=offset+3;
  first.storage_min_dwell=1; first.load_seconds=0.1;
  first.unload_seconds=0.2; first.hold_seconds=0.3; first.deadline=offset+30;
  auto second=first; second.business_bag_id="bag-b"; second.arrival=offset+1;
  in.jobs={first,second};
  in.transfers.push_back({"authorized-return","physical-tray",3,0,offset,0,offset,offset+50});
  return in;
}
void cycle(bool injected) {
  auto g=graph(); auto c=config();
  c.test_merge_grant_fail_after_calendar_prepare=injected;
  EventDrivenJunctionRuntime runtime(g,c);
  runtime.initialize_circulation(input());
  runtime.drain(); const auto& result=runtime.finalize(); const auto& s=runtime.circulation_state();
  require(result.summary.failed_count==0,"native failed transport");
  require(s.jobs[0].status=="completed" && s.jobs[1].status=="completed","both bags must unload");
  require(s.trays.size()==1 && s.jobs[0].tray==s.jobs[1].tray,"same finite tray");
  require(s.transfers[0].status=="received","authorized physical empty return");
  require(s.jobs[1].loaded_at>=s.transfers[0].received_at,"no predicted tray creation");
  require(s.jobs[0].storage_released_at>=3,"actual storage gate");
  std::map<std::uint64_t,std::pair<int,int>> traversals;
  for(const auto& r:s.receipts) {
    if(r.event=="EDGE_ENTER") ++traversals[r.traversal_id].first;
    if(r.event=="EDGE_EXIT") ++traversals[r.traversal_id].second;
  }
  require(!traversals.empty(),"actual edge events absent");
  for(const auto& item:traversals)
    require(item.first>0 && item.second==std::make_pair(1,1),"phantom or duplicate traversal");
  for(const auto& tray:s.trays) require(tray.edge_to<0,"resource ledger leaked in-flight capacity");
  if(injected) require(result.summary.merge_grant_rolled_back_count>0,"prepare failure not exercised");
}
void default_horizon_and_checkpoint() {
  auto g=graph(); auto c=config(); c.max_simulation_time=-1;
  EventDrivenJunctionRuntime runtime(g,c);
  runtime.initialize_circulation(input(90000));
  const auto checkpoint=runtime.capture_state_checkpoint();
  require(checkpoint.state_sha256()==runtime.deterministic_state_sha256(),
          "circulation checkpoint must seal the complete live state");
  EventDrivenJunctionRuntime restored(g,c);
  restored.restore_state_checkpoint(checkpoint);
  require(restored.deterministic_state_sha256()==runtime.deterministic_state_sha256(),
          "circulation clone changed the initial physical/environment state");
  runtime.drain(); const auto& result=runtime.finalize();
  require(!result.summary.time_limit_reached,"default circulation horizon truncated late input");
  require(runtime.circulation_state().jobs[1].status=="completed","late physical cycle incomplete");
  restored.drain(); restored.finalize();
  require(restored.circulation_state_sha256()==runtime.circulation_state_sha256(),
          "restored circulation diverged at the late-input final horizon");
  bool replay_rejected=false;
  try { (void)runtime.deterministic_replay_hashes(); }
  catch(const std::logic_error& e) {
    replay_rejected=std::string(e.what())=="circulation:replay_projection_not_implemented";
  }
  require(replay_rejected,"legacy leg-only hash must not masquerade as circulation replay identity");
  auto delayed=input(); delayed.transfers[0].earliest_departure=200000;
  delayed.transfers[0].expiry=250000;
  EventDrivenJunctionRuntime delayed_runtime(g,c);
  delayed_runtime.initialize_circulation(delayed); delayed_runtime.drain();
  const auto& delayed_result=delayed_runtime.finalize();
  require(!delayed_result.summary.time_limit_reached &&
      delayed_runtime.circulation_state().jobs[1].status=="completed",
      "explicit future module departure was omitted from default horizon");
}
void departure_lease_boundary() {
  CirculationState state; state.enabled=true; state.input=input();
  state.next_entry.assign(state.input.edges.size(),0);
  CirculationTrayState tray; tray.tray_id="physical-tray"; tray.node=3;
  tray.active_leg=0; tray.transfer=0; tray.reception_node=0;
  state.trays.push_back(tray); state.legs.push_back({0,"empty-leg",0,-1,"empty_return"});
  state.transfers.resize(1); state.transfers[0].status="dispatching";
  require(state.can_enter(0,3,0,50+5e-9)=="circulation:departure_lease_expired",
          "edge commit slipped between expiry and expiry wakeup");
  state.transfers[0].status="departed";
  require(state.can_enter(0,3,0,50+5e-9)=="allowed","departure lease wrongly cancels in-flight continuation");
}
void simultaneous_terminal_capacity_and_tail_headway() {
  Graph g; g.add_node(Node{0,0,0.001,0,0,{}}); g.add_node(Node{1,0,0.001,0,0,{}});
  g.add_edge(Edge{0,1,1,1}); g.set_heuristic({{0,1},{100,0}});
  auto c=config(); CirculationInput in;
  in.nodes={{0,"A",2,0,true,true},{1,"B",2,0,true,true}};
  in.edges={{0,1,1,2.5}};
  in.trays={{"physical-tray",0},{"second-physical-tray",0}};
  in.jobs=input().jobs;
  for(auto& job:in.jobs) {
    job.storage_node=-1; job.destination=1; job.arrival=0;
    job.load_seconds=0; job.unload_seconds=0; job.hold_seconds=0;
  }
  EventDrivenJunctionRuntime runtime(g,c);
  runtime.initialize_circulation(in); runtime.drain(); runtime.finalize();
  std::vector<double> entries, exits;
  for(const auto& receipt:runtime.circulation_state().receipts) {
    if(receipt.from==0 && receipt.to==1 && receipt.event=="EDGE_ENTER") entries.push_back(receipt.time);
    if(receipt.from==0 && receipt.to==1 && receipt.event=="EDGE_EXIT") exits.push_back(receipt.time);
  }
  require(entries.size()==2 && exits.size()==2,"both carriers must use real direct terminal edge");
  require(entries[1]+1e-9>=entries[0]+2.5,"entry headway tail vanished after first exit");
  require(entries[1]+1e-9>=exits[0],"finite in-transit capacity exceeded");
}
void explicit_goal_service_contract() {
  auto g=graph(); auto c=config(); c.complete_on_goal_arrival=true;
  auto in=input(); in.trays[0].node=3; in.jobs.resize(1);
  in.jobs[0].arrival=1.001; in.jobs[0].storage_node=-1;
  in.transfers.push_back({"second-export","physical-tray",0,3,0,0,0,50});
  EventDrivenJunctionRuntime runtime(g,c); bool rejected=false;
  try { runtime.initialize_circulation(in); }
  catch(const std::invalid_argument& e) {
    rejected=std::string(e.what())=="circulation:goal_arrival_completion_unsupported";
  }
  if(!rejected) {
    runtime.drain(); runtime.finalize();
    for(const auto& r:runtime.circulation_state().receipts)
      std::cout<<"contract_probe "<<r.time<<" "<<r.event<<" "<<r.business_bag_id<<"\n";
  }
  require(rejected,"circulation must reject bypassing declared goal service");
}
}
int main() {
  try { cycle(false); cycle(true); default_horizon_and_checkpoint(); departure_lease_boundary();
        simultaneous_terminal_capacity_and_tail_headway(); explicit_goal_service_contract(); }
  catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
  std::cout<<"native circulation cycle, rollback, horizon, clone and departure lease checks passed\n";
  return 0;
}
