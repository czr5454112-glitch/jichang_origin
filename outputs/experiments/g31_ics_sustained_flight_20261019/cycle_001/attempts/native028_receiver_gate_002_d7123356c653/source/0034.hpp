#pragma once

#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <map>
#include <memory>
#include <queue>
#include <set>
#include <string>
#include <stdexcept>
#include <tuple>
#include <utility>
#include <vector>

#include "ics_core/runtime/circulation.hpp"

namespace czr005::ics {

// Derived delivery offsets only. Not part of CirculationState, checkpoints,
// protocol observations, or canonical fingerprints. A derived allocation must
// never turn an already committed publication into a new physical failure.
template<class Allocator = std::allocator<std::size_t>>
class BasicCirculationPublicationJournal {
 public:
  using Indices = std::vector<std::size_t, Allocator>;
  bool valid() const noexcept { return valid_; }
  const Indices& demands() const noexcept { return demands_; }
  const Indices& forecasts() const noexcept { return forecasts_; }
  void clear() noexcept { demands_.clear(); forecasts_.clear(); valid_ = true; }
  void record_demand(std::size_t index) noexcept { append(demands_, index); }
  void record_forecast(std::size_t index) noexcept { append(forecasts_, index); }
  void rebuild(const CirculationState& state) noexcept {
    clear();
    for(std::size_t i=0;i<state.demand_messages.size();++i)
      if(state.demand_messages[i].delivered) record_demand(i);
    for(std::size_t i=0;i<state.service_forecasts.size();++i)
      if(state.service_forecasts[i].delivered) record_forecast(i);
  }
 private:
  void append(Indices& rows, std::size_t index) noexcept {
    if(!valid_) return;
    try { rows.push_back(index); }
    catch(...) { valid_=false; }
  }
  Indices demands_, forecasts_;
  bool valid_=true;
};
using CirculationPublicationJournal = BasicCirculationPublicationJournal<>;

// No Python objects and no live remote truth. Every entry comes exclusively
// from a publication whose canonical delivered flag is already true.
class CirculationObservationIndex {
 public:
  void clear() {
    demand_cursor_=forecast_cursor_=0;
    demand_latest_.clear();forecast_owners_.clear();
  }
  template<class Allocator>
  bool sync(const CirculationState& state, const BasicCirculationPublicationJournal<Allocator>& journal) {
    if(!journal.valid()) return false; // Canonical scan fallback, no lost rows.
    try {
      for(;demand_cursor_<journal.demands().size();++demand_cursor_) {
        const auto index=journal.demands()[demand_cursor_];
        const auto& message=state.demand_messages.at(index);
        if(!message.delivered) {clear();return false;}
        auto& sources=demand_latest_[message.target_owner];
        const auto found=sources.find(message.source_owner);
        if(found==sources.end()) sources.emplace(message.source_owner,index);
        else {
          const auto& old=state.demand_messages[found->second];
          const auto a=std::tie(message.observed_at,message.publication_sequence);
          const auto b=std::tie(old.observed_at,old.publication_sequence);
          if(a>b || (a==b && index<found->second)) found->second=index;
        }
      }
      for(;forecast_cursor_<journal.forecasts().size();++forecast_cursor_)
        add_forecast(state.service_forecasts,journal.forecasts()[forecast_cursor_]);
    } catch(...) {
      // A failed read cannot leave a partly updated derived aggregate for the
      // next read. Physical state and immutable delivered messages stay intact.
      clear();throw;
    }
    return true;
  }
  const std::map<std::string,std::size_t>& latest_demand(const std::string& owner) const {
    const auto found=demand_latest_.find(owner);
    static const std::map<std::string,std::size_t> empty;
    return found==demand_latest_.end() ? empty : found->second;
  }
  std::set<std::size_t> select_forecasts(const std::string& owner,double now,double validity,
      const std::vector<CirculationServiceForecast>& messages) {
    if(!std::isfinite(validity) || validity<=0)
      throw std::invalid_argument("circulation:invalid_forecast_validity");
    const auto found=forecast_owners_.find(owner);
    if(found==forecast_owners_.end()) return {};
    auto& state=found->second;
    try {
      if(!state.validity_initialized || validity!=state.validity || now<state.last_now) {
        state.live.clear();state.expiry=ExpiryHeap{};
        state.validity=validity;state.validity_initialized=true;
        for(const auto index:state.conditional_history) add_expiry(state,messages,index);
      }
      state.last_now=now;
      // Keep the exact old addition and strict comparison; now-validity is not
      // floating-point equivalent at an expiry boundary.
      while(!state.expiry.empty() && !(now<state.expiry.top().first)) {
        state.live.erase(state.expiry.top().second);state.expiry.pop();
      }
      std::set<std::size_t> selected=state.live;
      for(const auto& [key,group]:state.keys) {
        selected.insert(group.first);
        selected.insert(group.latest_ties.begin(),group.latest_ties.end());
      }
      const auto nonwithdrawn=selected;
      for(const auto index:nonwithdrawn) {
        const auto& message=messages[index];
        const auto withdrawals=state.withdrawals.find({message.source_owner,message.message_id});
        if(withdrawals!=state.withdrawals.end())
          selected.insert(withdrawals->second.begin(),withdrawals->second.end());
      }
      return selected; // Native vector order, independent of delivery order.
    } catch(...) {clear();throw;}
  }
 private:
  using Key=std::pair<std::string,std::string>;
  using Expiry=std::pair<double,std::size_t>;
  using ExpiryHeap=std::priority_queue<Expiry,std::vector<Expiry>,std::greater<Expiry>>;
  struct ForecastKey {
    std::size_t first=std::numeric_limits<std::size_t>::max();
    std::size_t latest=std::numeric_limits<std::size_t>::max();
    std::set<std::size_t> latest_ties;
  };
  struct ForecastOwner {
    std::map<Key,ForecastKey> keys;
    std::map<Key,std::vector<std::size_t>> withdrawals;
    std::vector<std::size_t> conditional_history;
    std::set<std::size_t> live;
    ExpiryHeap expiry;
    bool validity_initialized=false;
    double validity=0.,last_now=0.;
  };
  static void add_expiry(ForecastOwner& state,const std::vector<CirculationServiceForecast>& messages,
      std::size_t index) {
    state.live.insert(index);
    state.expiry.emplace(messages[index].observed_at+state.validity,index);
  }
  void add_forecast(const std::vector<CirculationServiceForecast>& messages,std::size_t index) {
    const auto& message=messages.at(index);
    if(!message.delivered) throw std::logic_error("circulation:undelivered_observation_index");
    auto& state=forecast_owners_[message.target_owner];
    if(message.status=="withdrawn") {
      state.withdrawals[{message.source_owner,message.supersedes}].push_back(index);
      return;
    }
    auto& group=state.keys[{message.source_owner,message.tray_id}];
    group.first=std::min(group.first,index);
    const auto revision=[](const auto& m) {return std::tie(m.observed_at,m.generation,m.publication_sequence);};
    if(group.latest==std::numeric_limits<std::size_t>::max() || revision(message)>revision(messages[group.latest])) {
      group.latest=index;group.latest_ties.clear();group.latest_ties.insert(index);
    } else if(revision(message)==revision(messages[group.latest])) group.latest_ties.insert(index);
    if(message.status=="conditional") {
      state.conditional_history.push_back(index);
      if(state.validity_initialized) add_expiry(state,messages,index);
    }
  }
  std::size_t demand_cursor_=0,forecast_cursor_=0;
  std::map<std::string,std::map<std::string,std::size_t>> demand_latest_;
  std::map<std::string,ForecastOwner> forecast_owners_;
};

} // namespace czr005::ics
