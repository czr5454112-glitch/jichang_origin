#pragma once

#include <algorithm>
#include <cstdint>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "ics_core/runtime/g4irsf14_state_clone.hpp"

namespace czr005::ics {

inline constexpr const char* kG4IRSF14CausalFrozenTuple =
    "R3/S1/P2/C0/Q0/E4/M0";

enum G4IRSF14CausalCandidateKindMask : std::uint32_t {
  kG4IRSF14CausalCandidateNone = 0U,
  kG4IRSF14CausalCandidateI1 = 1U << 0,
  kG4IRSF14CausalCandidateI2 = 1U << 1,
  kG4IRSF14CausalCandidateI3 = 1U << 2,
  kG4IRSF14CausalCandidateI4 = 1U << 3,
  kG4IRSF14CausalCandidateI5 = 1U << 4,
};

// A treatment is addressed to the full pre-pop state and to one concrete
// action opportunity discovered while processing that event.  The directive
// itself is deliberately an ephemeral value: it is neither part of runtime
// configuration nor checkpoint state.
struct G4IRSF14CausalInterventionDirective {
  G4IRSF14CloneBoundary boundary;
  G4IRSF14CloneIntervention intervention;

  void validate() const {
    boundary.validate();
    intervention.validate_against(boundary);
    if (intervention.kind ==
        G4IRSF14CloneInterventionKind::kNoOp) {
      throw std::invalid_argument(
          "causal treatment directive cannot be a no-op");
    }
  }

  [[nodiscard]] std::string boundary_sha256() const {
    validate();
    return boundary.boundary_sha256();
  }

  [[nodiscard]] std::string intervention_sha256() const {
    validate();
    return intervention.intervention_sha256(boundary);
  }
};

// One call consumes at most one queue-top event.  A probe reports every
// eligible local opportunity it encountered.  A treatment applies at most
// one action and reports a stable reason when its content-addressed target is
// not encountered.
struct G4IRSF14CausalStepResult {
  bool event_processed = false;
  bool treatment_requested = false;
  bool target_opportunity_observed = false;
  bool intervention_applied = false;
  int changed_action_count = 0;
  std::string frozen_tuple = kG4IRSF14CausalFrozenTuple;
  std::string source_state_sha256;
  std::string requested_boundary_sha256;
  std::string requested_intervention_sha256;
  std::string application_reason;
  std::vector<int> affected_runtime_bag_ids;
  std::vector<G4IRSF14CloneBoundary> observed_opportunities;

  void validate() const {
    g4irsf14_clone_detail::require_sha256(
        "source_state_sha256", source_state_sha256);
    if (frozen_tuple != kG4IRSF14CausalFrozenTuple) {
      throw std::invalid_argument(
          "causal step did not use the frozen Stage 14E tuple");
    }
    if (!treatment_requested) {
      if (target_opportunity_observed || intervention_applied ||
          changed_action_count != 0 ||
          !affected_runtime_bag_ids.empty() ||
          !requested_boundary_sha256.empty() ||
          !requested_intervention_sha256.empty() ||
          application_reason != "PROBE_ONLY_NO_ACTION_CHANGED") {
        throw std::invalid_argument(
            "causal probe must not report a treatment action");
      }
    } else {
      g4irsf14_clone_detail::require_sha256(
          "requested_boundary_sha256",
          requested_boundary_sha256);
      g4irsf14_clone_detail::require_sha256(
          "requested_intervention_sha256",
          requested_intervention_sha256);
      if (intervention_applied != (changed_action_count == 1) ||
          changed_action_count < 0 || changed_action_count > 1) {
        throw std::invalid_argument(
            "causal treatment must change exactly one action or none");
      }
      if (intervention_applied && !target_opportunity_observed) {
        throw std::invalid_argument(
            "causal treatment cannot apply before observing its target");
      }
      if (application_reason.empty()) {
        throw std::invalid_argument(
            "causal treatment requires an applied/not-applicable reason");
      }
      if (intervention_applied &&
          affected_runtime_bag_ids.empty()) {
        throw std::invalid_argument(
            "applied treatment must identify its affected runtime bags");
      }
      if (!intervention_applied &&
          !affected_runtime_bag_ids.empty()) {
        throw std::invalid_argument(
            "non-applied treatment cannot declare affected runtime bags");
      }
      if (!std::all_of(
              affected_runtime_bag_ids.begin(),
              affected_runtime_bag_ids.end(),
              [](int runtime_bag_id) {
                return runtime_bag_id >= 0;
              }) ||
          std::set<int>(affected_runtime_bag_ids.begin(),
                        affected_runtime_bag_ids.end())
                  .size() !=
              affected_runtime_bag_ids.size()) {
        throw std::invalid_argument(
            "affected runtime bag ids must be unique and non-negative");
      }
    }
    for (const auto& opportunity : observed_opportunities) {
      opportunity.validate();
      if (opportunity.runtime_state_sha256 !=
          source_state_sha256) {
        throw std::invalid_argument(
            "opportunity is not bound to the queue-top source state");
      }
    }
  }
};

struct G4IRSF14CausalBagHorizonRow {
  int runtime_bag_id = -1;
  bool known = false;
  bool terminal = false;
  bool completed = false;
  bool failed = false;
  double finish_time = -1.0;
  double total_wait = 0.0;
  int decision_count = 0;
  int retry_count = 0;
};

// The caller supplies the affected/cohort ids, so checking H_bag/H_system is
// bounded by that explicit set and never scans all runtime bags.
struct G4IRSF14CausalHorizonState {
  std::vector<G4IRSF14CausalBagHorizonRow> bags;
  int terminal_count = 0;
  int completed_count = 0;
  int failed_count = 0;
  bool all_terminal = false;
  bool all_completed = false;

  void validate() const {
    if (bags.empty()) {
      throw std::invalid_argument(
          "causal horizon requires an explicit non-empty bag cohort");
    }
    std::set<int> ids;
    int expected_terminal = 0;
    int expected_completed = 0;
    int expected_failed = 0;
    for (const auto& bag : bags) {
      if (bag.runtime_bag_id < 0 ||
          !ids.insert(bag.runtime_bag_id).second ||
          bag.terminal != (bag.completed || bag.failed) ||
          (bag.completed && bag.failed)) {
        throw std::invalid_argument(
            "invalid causal bag horizon row");
      }
      expected_terminal += bag.terminal ? 1 : 0;
      expected_completed += bag.completed ? 1 : 0;
      expected_failed += bag.failed ? 1 : 0;
    }
    if (terminal_count != expected_terminal ||
        completed_count != expected_completed ||
        failed_count != expected_failed ||
        all_terminal !=
            (terminal_count == static_cast<int>(bags.size())) ||
        all_completed !=
            (completed_count == static_cast<int>(bags.size()))) {
      throw std::invalid_argument(
          "causal horizon aggregate does not match its rows");
    }
  }
};

struct G4IRSF14CausalHorizonStopState {
  G4IRSF14CloneHorizon horizon =
      G4IRSF14CloneHorizon::kLocal;
  bool should_stop = false;
  bool horizon_complete = false;
  bool blocked = false;
  std::string stop_reason = "CONTINUE";
  std::uint64_t elapsed_event_count = 0;
  int merge_pending_request_count = -1;
  G4IRSF14CausalHorizonState cohort;

  void validate() const {
    cohort.validate();
    if ((horizon_complete && (!should_stop || blocked)) ||
        (blocked && (!should_stop || horizon_complete)) ||
        (!should_stop && stop_reason != "CONTINUE") ||
        (should_stop && stop_reason == "CONTINUE")) {
      throw std::invalid_argument(
          "causal horizon stop flags/reason are inconsistent");
    }
    if (horizon != G4IRSF14CloneHorizon::kLocal &&
        horizon_complete && !cohort.all_completed) {
      throw std::invalid_argument(
          "H_bag/H_system complete requires every selected bag completed");
    }
  }
};

}  // namespace czr005::ics
