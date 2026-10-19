// Compile this identical fixture against the pinned mature and updated headers.
// Runtime timings are excluded by G31's five deterministic replay projections.
#include <iostream>
#include "ics_core/runtime/event_driven_junction.hpp"
using namespace czr005::ics;
int main() {
  Graph g;
  for(int i=0;i<5;++i) g.add_node(Node{i,0,0.1,0,0,{}});
  for(auto edge:std::vector<std::pair<int,int>>{{0,2},{1,2},{2,3},{2,4},{4,3},{3,0}})
    g.add_edge(Edge{edge.first,edge.second,1,1});
  std::vector<std::vector<double>> h(5,std::vector<double>(5,100));
  for(int i=0;i<5;++i) { h[i][i]=0; for(int j:g.outgoing(i)) h[i][j]=1.1; }
  for(int k=0;k<5;++k) for(int i=0;i<5;++i) for(int j=0;j<5;++j)
    h[i][j]=std::min(h[i][j],h[i][k]+h[k][j]);
  g.set_heuristic(h);
  EventDrivenJunctionConfig c;
  c.queue_discipline="fifo"; c.resource_semantics="R3";
  c.event_semantics="E4_batch_plus_destination_merge_request";
  c.enable_source_admission=false; c.enable_backpressure=false;
  c.enable_pibt_lite=false; c.pressure_mode="off"; c.admission_mode="off";
  c.pibt_mode="P2"; c.priority_mode="Q0"; c.scorer_mode="S4";
  c.merge_grant_rule="M3"; c.merge_grant_timing_mode="J2";
  c.g4irsf20_event_hotpath_policy="E2"; c.local_queue_capacity=0;
  c.max_events=100000; c.max_simulation_time=100; c.trace_limit=10000;
  c.event_trace_limit=10000;
  const std::vector<EventRuntimeBagRequest> requests={
    {"a:direct",1,0,20,0,3,"normal"},
    {"b:direct",2,0,15,1,3,"normal"},
    {"c:storage_out",3,0.05,18,1,3,"storage"},
    {"d:direct",4,0.3,30,0,3,"normal"}};
  std::cout << "[";
  for(int scenario=0;scenario<2;++scenario) {
    EventDrivenJunctionRuntime runtime(g,c);
    std::vector<EventRuntimeFaultWindow> faults;
    if(scenario) faults.push_back({2,3,1,5,0.2,false});
    auto result=runtime.run(requests,faults);
    auto hash=runtime.deterministic_replay_hashes();
    if(scenario) std::cout<<",";
    std::cout<<"{\"scenario\":"<<scenario
      <<",\"completed\":"<<result.summary.completed_count
      <<",\"failed\":"<<result.summary.failed_count
      <<",\"complete_bags_sha256\":\""<<hash.complete_bags_sha256
      <<"\",\"segment_result_sha256\":\""<<hash.segment_result_sha256
      <<"\",\"junction_state_sha256\":\""<<hash.junction_state_sha256
      <<"\",\"algorithm_summary_sha256\":\""<<hash.algorithm_summary_sha256
      <<"\",\"deterministic_result_sha256\":\""<<hash.deterministic_result_sha256<<"\"}";
  }
  std::cout<<"]\n";
}
