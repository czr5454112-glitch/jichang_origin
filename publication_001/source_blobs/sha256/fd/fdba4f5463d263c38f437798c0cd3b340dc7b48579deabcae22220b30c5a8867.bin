#pragma once

namespace czr005::ics {

inline CirculationNotificationAdvance EventDrivenJunctionRuntime::advance_circulation_until_owner_notification(
    const std::map<std::string,std::uint64_t>& after,double horizon,int budget) {
  if(!circulation_.input.owner_notifications_enabled)
    throw std::invalid_argument("circulation:owner_notifications_not_enabled");
  require_checkpoint_safe_boundary();
  if(runtime_phase_==EventDrivenJunctionRuntimePhase::kIdle ||
     runtime_phase_==EventDrivenJunctionRuntimePhase::kFinalized)
    throw std::logic_error("circulation:live_session_required");
  if(!std::isfinite(horizon) || horizon<now_ || horizon>time_limit_ || budget<=0 || after.empty())
    throw std::invalid_argument("circulation:invalid_notification_horizon");
  for(const auto& [owner,sequence]:after) {
    const auto found=circulation_.owner_notifications.find(owner);
    if(found==circulation_.owner_notifications.end()) throw std::invalid_argument("circulation:unknown_notification_owner");
    if(sequence>found->second.sequence) throw std::invalid_argument("circulation:future_owner_notification_sequence");
  }
  const auto changed=[&]() {
    for(const auto& [owner,sequence]:after)
      if(circulation_.owner_notifications.at(owner).sequence>sequence) return true;
    return false;
  };
  int processed=0;
  for(;;) {
    const bool timestamp_complete=events_.empty() || events_.top().time>now_;
    // A same-time cascade includes events newly published by an earlier phase.
    // A controller command may create a second legal cascade at the same time.
    if(timestamp_complete && changed())
      return {"notified",true,now_==horizon};
    if(events_.empty() || events_.top().time>horizon) {
      if(result_.summary.event_limit_reached) return {"budget_exhausted",false,false};
      now_=horizon;
      return {"horizon_reached",true,true};
    }
    if(processed>=budget || result_.summary.event_limit_reached)
      return {"budget_exhausted",false,false};
    runtime_phase_=EventDrivenJunctionRuntimePhase::kReady;
    if(!process_one_event()) return {"budget_exhausted",false,false};
    ++processed;
  }
}

} // namespace czr005::ics
