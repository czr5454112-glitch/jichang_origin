#include <cassert>
#include <cmath>
#include <iostream>
#include <new>
#include <numeric>
#include <random>
#include "ics_core/runtime/circulation_observation_index.hpp"
using namespace czr005::ics;

// Standalone derived-data test only: no runtime, event heap or NativeSession.
bool fail_allocation=false;
template<class T> struct FailingAllocator {
  using value_type=T;
  FailingAllocator()=default;
  template<class U> FailingAllocator(const FailingAllocator<U>&) {}
  T* allocate(std::size_t n) {
    if(fail_allocation) throw std::bad_alloc();
    return std::allocator<T>{}.allocate(n);
  }
  void deallocate(T* p,std::size_t n) {std::allocator<T>{}.deallocate(p,n);}
};
template<class T,class U> bool operator==(FailingAllocator<T>,FailingAllocator<U>) {return true;}
template<class T,class U> bool operator!=(FailingAllocator<T>,FailingAllocator<U>) {return false;}

std::set<std::size_t> reference(const CirculationState& state,const std::string& owner,double now,double validity) {
  using Key=std::pair<std::string,std::string>;
  const auto& rows=state.service_forecasts;
  std::map<Key,std::vector<std::size_t>> groups;
  for(std::size_t i=0;i<rows.size();++i)
    if(rows[i].delivered && rows[i].target_owner==owner && rows[i].status!="withdrawn")
      groups[{rows[i].source_owner,rows[i].tray_id}].push_back(i);
  std::set<std::size_t> result;
  const auto revision=[](const auto& x){return std::tie(x.observed_at,x.generation,x.publication_sequence);};
  for(const auto& [key,indices]:groups) {
    const auto maximum=*std::max_element(indices.begin(),indices.end(),[&](auto a,auto b){return revision(rows[a])<revision(rows[b]);});
    result.insert(indices.front());
    for(auto i:indices) if(revision(rows[i])==revision(rows[maximum]) ||
        (rows[i].status=="conditional" && now<rows[i].observed_at+validity)) result.insert(i);
  }
  const auto selected=result;
  for(std::size_t i=0;i<rows.size();++i) if(rows[i].delivered && rows[i].target_owner==owner && rows[i].status=="withdrawn")
    for(auto j:selected) if(rows[i].source_owner==rows[j].source_owner && rows[i].supersedes==rows[j].message_id) result.insert(i);
  return result;
}
std::map<std::string,std::size_t> demands(const CirculationState& state,const std::string& owner) {
  std::map<std::string,std::size_t> result;
  for(std::size_t i=0;i<state.demand_messages.size();++i) {
    const auto& x=state.demand_messages[i];if(!x.delivered || x.target_owner!=owner) continue;
    auto f=result.find(x.source_owner);
    if(f==result.end() || std::tie(x.observed_at,x.publication_sequence)>
        std::tie(state.demand_messages[f->second].observed_at,state.demand_messages[f->second].publication_sequence)) result[x.source_owner]=i;
  }
  return result;
}
void check(CirculationObservationIndex& index,const CirculationPublicationJournal& journal,const CirculationState& state,double now,double validity) {
  assert(index.sync(state,journal));
  for(const auto owner:{"A","B","C","missing"}) {
    assert(index.latest_demand(owner)==demands(state,owner));
    assert(index.select_forecasts(owner,now,validity,state.service_forecasts)==reference(state,owner,now,validity));
  }
}
int main() {
  static_assert(noexcept(std::declval<CirculationPublicationJournal&>().record_demand(0)));
  static_assert(noexcept(std::declval<CirculationPublicationJournal&>().record_forecast(0)));
  CirculationState state;
  state.demand_messages.resize(2);state.demand_messages[0].delivered=true;
  BasicCirculationPublicationJournal<FailingAllocator<std::size_t>> failing;
  fail_allocation=true;failing.record_demand(0);assert(!failing.valid());
  failing.record_forecast(1);assert(failing.forecasts().empty());
  CirculationObservationIndex fallback_index;
  assert(!fallback_index.sync(state,failing));
  fail_allocation=false;failing.record_demand(1);
  assert(!failing.valid() && !fallback_index.sync(state,failing));
  // Binding's false result selects the untouched canonical history scan.
  auto canonical_fallback=fallback_index.sync(state,failing) ? fallback_index.latest_demand("") : demands(state,"");
  assert(canonical_fallback==demands(state,""));
  fail_allocation=true;
  failing.rebuild(state);assert(!failing.valid());
  fail_allocation=false;failing.rebuild(state);assert(failing.valid() && failing.demands()==decltype(failing)::Indices{0});
  failing.clear();assert(failing.valid() && failing.demands().empty());

  // Journal order may be reversed relative to native-vector order. Equal
  // demand/forecast revisions still prefer/retain exactly the vector oracle.
  state={};state.demand_messages.resize(2);state.service_forecasts.resize(2);
  for(std::size_t i=0;i<2;++i) {
    auto& d=state.demand_messages[i];d.source_owner="A";d.target_owner="B";d.delivered=true;
    auto& f=state.service_forecasts[i];f.source_owner="A";f.target_owner="B";f.tray_id="T";f.delivered=true;
  }
  CirculationPublicationJournal tied;CirculationObservationIndex tied_index;
  tied.record_demand(1);tied.record_forecast(1);tied_index.sync(state,tied);
  assert(tied_index.latest_demand("B").at("A")==1);
  tied.record_demand(0);tied.record_forecast(0);tied_index.sync(state,tied);
  assert(tied_index.latest_demand("B").at("A")==0);
  assert((tied_index.select_forecasts("B",100.,.1,state.service_forecasts)==std::set<std::size_t>{0,1}));

  // Fixed randomized delivery order covers earlier arrivals after newer ones,
  // tied revisions, multiple owners, withdrawal-before-original and TTL changes.
  state={};std::mt19937 random(260014);
  for(std::size_t i=0;i<180;++i) {
    CirculationServiceForecast x;x.message_id="m"+std::to_string(i);
    x.source_owner=std::string(1,'A'+random()%3);x.target_owner=std::string(1,'A'+random()%3);
    x.tray_id="t"+std::to_string(random()%5);x.observed_at=(random()%8)*.1;
    x.generation=random()%3;x.publication_sequence=random()%4;
    if(i%4==0) {x.status="withdrawn";x.supersedes="m"+std::to_string(random()%180);}
    else if(i%11==0) x.status="expired";
    state.service_forecasts.push_back(x);
    CirculationDemandMessage d;d.source_owner=x.source_owner;d.target_owner=x.target_owner;
    d.observed_at=x.observed_at;d.publication_sequence=x.publication_sequence;
    state.demand_messages.push_back(d);
  }
  CirculationPublicationJournal journal;CirculationObservationIndex index;
  std::vector<std::size_t> order(180);std::iota(order.begin(),order.end(),0);
  std::shuffle(order.begin(),order.end(),random);
  for(const auto i:order) {
    state.service_forecasts[i].delivered=true;state.demand_messages[i].delivered=true;
    journal.record_forecast(i);journal.record_demand(i);
    check(index,journal,state,.6,.3);
    check(index,journal,state,100.,.3);
    check(index,journal,state,100.,200.); // expired candidates return on new TTL
    check(index,journal,state,.01,.2); // backwards time requires expiry rebuild
  }
  const auto saved=state;
  journal.rebuild(saved);index.clear();check(index,journal,saved,.9,.3);
  // Equal-size restore must discard old identity, even with identical cursors.
  state.service_forecasts[0].target_owner="missing";state.demand_messages[0].source_owner="new";
  journal.rebuild(state);index.clear();check(index,journal,state,.9,.3);

  // Non-associative floating point boundary, exact old observed_at + validity.
  for(const double now:{std::nextafter(.1+.2,0.),.1+.2,std::nextafter(.1+.2,1.)}) {
    journal.rebuild(saved);index.clear();check(index,journal,saved,now,.2);
  }
  std::cout<<"derived journal allocation, ordering, owner, expiry and restore checks passed\n";
}
