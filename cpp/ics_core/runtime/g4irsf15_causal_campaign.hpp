#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include "ics_core/runtime/g4irsf14_causal_intervention.hpp"

namespace czr005::ics {

struct G4IRSF15CausalPrepopStrata {
  double event_time = 0.0;
  std::uint64_t event_seq = 0;
  int node = -1;
  int active_merge_capability_count = 0;
  int pending_merge_request_count = 0;
  int active_physical_fault_edge_count = 0;
  int queued_bag_count = 0;
};

// Outcome-free opportunity description used for the scalable first-pass
// census.  It intentionally carries no runtime-state digest, outcome, future
// route, or global planner state.
struct G4IRSF15CausalOpportunitySkeleton {
  G4IRSF14CloneBoundaryKind kind =
      G4IRSF14CloneBoundaryKind::kSourceArbitration;
  double time = 0.0;
  std::uint64_t event_seq = 0;
  int node = -1;
  int runtime_bag_id = -1;
  int baseline_next_node = -1;
  bool baseline_release = false;
  std::vector<int> source_ready_order;
  bool g4irsf17_i1_observation_available = false;
  int g4irsf17_i1_observation_peer_runtime_bag_id = -1;
  std::array<double, kG4IRSF17SourcePairwiseFeatureCount>
      g4irsf17_i1_baseline_observation{};
  std::array<double, kG4IRSF17SourcePairwiseFeatureCount>
      g4irsf17_i1_treatment_observation{};
  std::array<double, kG4IRSF17SourcePairwiseFeatureCount>
      g4irsf17_i1_pairwise_features{};
  bool g4irsf23_source_observation_available = false;
  std::array<double, kG4IRSF17SourcePairwiseFeatureCount>
      g4irsf23_source_observation{};
  bool g4irsf20_route_observation_available = false;
  bool g4irsf20_route_normal_flow = false;
  int g4irsf20_route_baseline_candidate_index = -1;
  std::vector<int> g4irsf20_route_candidate_next_nodes;
  std::vector<std::vector<double>>
      g4irsf20_route_candidate_features;
  std::vector<int> legal_next_edges;
};

// The action rank is deliberately numeric and local.  In particular, neither
// the offline population strata nor an airport-wide event ordinal/sequence can
// affect which peer/edge is selected for a causal treatment.
struct G4IRSF15PrimaryLocalAction {
  int peer_runtime_bag_id = -1;
  int selected_next_node = -1;
  bool selected_boolean = false;
  int candidate_action_count = 0;
};

inline std::optional<G4IRSF15PrimaryLocalAction>
g4irsf15_primary_local_action(
    const G4IRSF15CausalOpportunitySkeleton& skeleton) {
  G4IRSF15PrimaryLocalAction selected;
  std::vector<int> alternatives;
  if (skeleton.kind ==
      G4IRSF14CloneBoundaryKind::kSourceArbitration) {
    if (skeleton.g4irsf23_source_observation_available) {
      return std::nullopt;
    }
    for (const int peer : skeleton.source_ready_order) {
      if (peer != skeleton.runtime_bag_id) {
        alternatives.push_back(peer);
      }
    }
    std::sort(alternatives.begin(), alternatives.end());
    alternatives.erase(
        std::unique(alternatives.begin(), alternatives.end()),
        alternatives.end());
    if (alternatives.empty()) {
      return std::nullopt;
    }
    selected.peer_runtime_bag_id = alternatives.front();
  } else if (
      skeleton.kind ==
      G4IRSF14CloneBoundaryKind::kJunctionRouteArbitration) {
    for (const int next : skeleton.legal_next_edges) {
      if (next != skeleton.baseline_next_node) {
        alternatives.push_back(next);
      }
    }
    std::sort(alternatives.begin(), alternatives.end());
    alternatives.erase(
        std::unique(alternatives.begin(), alternatives.end()),
        alternatives.end());
    if (alternatives.empty()) {
      return std::nullopt;
    }
    selected.selected_next_node = alternatives.front();
  } else if (
      skeleton.kind ==
          G4IRSF14CloneBoundaryKind::kHoldReleaseOpportunity &&
      skeleton.baseline_release) {
    alternatives.push_back(0);
    selected.selected_boolean = false;
  } else {
    return std::nullopt;
  }
  selected.candidate_action_count =
      static_cast<int>(alternatives.size());
  return selected;
}

// These whole-runtime counts exist only to define offline sampling strata.
// Keeping their digest in a separate projection makes it mechanically
// impossible for them to participate in the local primary-action rank above.
inline std::string g4irsf15_offline_population_group_sha256(
    const G4IRSF15CausalOpportunitySkeleton& skeleton,
    const G4IRSF15CausalPrepopStrata& strata,
    std::uint64_t event_ordinal,
    bool pibt_prefilter_candidate_event) {
  if (skeleton.event_seq != strata.event_seq ||
      skeleton.time != strata.event_time ||
      skeleton.node != strata.node) {
    throw std::invalid_argument(
        "population skeleton and pre-pop strata disagree");
  }
  g4irsf14_clone_detail::CanonicalFields fields;
  const char* kind = nullptr;
  if (skeleton.kind ==
      G4IRSF14CloneBoundaryKind::kSourceArbitration) {
    kind = "I1";
  } else if (
      skeleton.kind ==
      G4IRSF14CloneBoundaryKind::kJunctionRouteArbitration) {
    kind = "I3";
  } else if (
      skeleton.kind ==
      G4IRSF14CloneBoundaryKind::kHoldReleaseOpportunity) {
    kind = "I4";
  } else {
    throw std::invalid_argument(
        "offline population group kind is outside I1/I3/I4");
  }
  fields.string("schema",
                "czr005.g4irsf15.causal_skeleton.v1");
  fields.string("kind", kind);
  fields.unsigned_integer("event_ordinal", event_ordinal);
  fields.floating("event_time", skeleton.time);
  fields.unsigned_integer("event_seq", skeleton.event_seq);
  fields.integer("node", skeleton.node);
  fields.integer("runtime_bag_id", skeleton.runtime_bag_id);
  fields.integer("baseline_next_node",
                 skeleton.baseline_next_node);
  fields.boolean("baseline_release",
                 skeleton.baseline_release);
  fields.integers("source_ready_order",
                  skeleton.source_ready_order);
  fields.integers("legal_next_edges",
                  skeleton.legal_next_edges);
  fields.integer("active_merge_capability_count",
                 strata.active_merge_capability_count);
  fields.integer("pending_merge_request_count",
                 strata.pending_merge_request_count);
  fields.integer("active_physical_fault_edge_count",
                 strata.active_physical_fault_edge_count);
  fields.integer("queued_bag_count",
                 strata.queued_bag_count);
  fields.boolean("pibt_prefilter_candidate_event",
                 pibt_prefilter_candidate_event);
  return canonical_map2_detail::sha256_hex(fields.payload());
}

inline std::string
g4irsf15_population_selection_evidence_sha256(
    const std::string& population_group_sha256,
    const G4IRSF15PrimaryLocalAction& primary) {
  g4irsf14_clone_detail::require_sha256(
      "population_group_sha256", population_group_sha256);
  g4irsf14_clone_detail::CanonicalFields fields;
  fields.string(
      "schema",
      "czr005.g4irsf15.causal_skeleton_action.v1");
  fields.string("population_group_sha256",
                population_group_sha256);
  fields.integer("peer_runtime_bag_id",
                 primary.peer_runtime_bag_id);
  fields.integer("selected_next_node",
                 primary.selected_next_node);
  fields.boolean("selected_boolean",
                 primary.selected_boolean);
  return canonical_map2_detail::sha256_hex(fields.payload());
}

struct G4IRSF15OfflinePopulationProjection {
  std::string population_group_sha256;
  std::string population_selection_evidence_sha256;
  G4IRSF15PrimaryLocalAction primary_local_action;
};

inline std::optional<G4IRSF15OfflinePopulationProjection>
g4irsf15_project_offline_population(
    const G4IRSF15CausalOpportunitySkeleton& skeleton,
    const G4IRSF15CausalPrepopStrata& strata,
    std::uint64_t event_ordinal,
    bool pibt_prefilter_candidate_event) {
  const auto primary = g4irsf15_primary_local_action(skeleton);
  if (!primary.has_value()) {
    return std::nullopt;
  }
  const auto population_group_sha256 =
      g4irsf15_offline_population_group_sha256(
          skeleton, strata, event_ordinal,
          pibt_prefilter_candidate_event);
  return G4IRSF15OfflinePopulationProjection{
      population_group_sha256,
      g4irsf15_population_selection_evidence_sha256(
          population_group_sha256, *primary),
      *primary};
}

struct G4IRSF15CausalSkeletonStepResult {
  bool event_processed = false;
  std::string frozen_tuple = kG4IRSF14CausalFrozenTuple;
  std::string application_reason =
      "SKELETON_PROBE_ONLY_NO_ACTION_CHANGED";
  G4IRSF15CausalPrepopStrata prepop;
  bool pibt_prefilter_candidate_event = false;
  std::vector<G4IRSF15CausalOpportunitySkeleton>
      observed_opportunities;

  void validate() const {
    const bool processed_no_action =
        event_processed &&
        application_reason ==
            "SKELETON_PROBE_ONLY_NO_ACTION_CHANGED";
    const bool skipped_runtime_limit =
        !event_processed &&
        application_reason ==
            "SKELETON_PROBE_SKIPPED_RUNTIME_LIMIT" &&
        observed_opportunities.empty();
    if ((!processed_no_action && !skipped_runtime_limit) ||
        frozen_tuple != kG4IRSF14CausalFrozenTuple ||
        !std::isfinite(prepop.event_time) ||
        prepop.event_time < 0.0 ||
        prepop.event_seq == 0U ||
        prepop.active_merge_capability_count < 0 ||
        prepop.pending_merge_request_count < 0 ||
        prepop.active_physical_fault_edge_count < 0 ||
        prepop.queued_bag_count < 0) {
      throw std::invalid_argument(
          "invalid G4IRSF15 causal skeleton step");
    }
    for (const auto& opportunity : observed_opportunities) {
      if (opportunity.event_seq != prepop.event_seq ||
          opportunity.time != prepop.event_time ||
          opportunity.node != prepop.node ||
          opportunity.runtime_bag_id < 0) {
        throw std::invalid_argument(
            "causal skeleton does not match its queue-top event");
      }
      if (opportunity.kind ==
              G4IRSF14CloneBoundaryKind::kSourceArbitration &&
          !opportunity.baseline_release &&
          opportunity.source_ready_order.size() < 2U) {
        throw std::invalid_argument(
            "I1 skeleton requires a multi-bag source ready set");
      }
      if (opportunity.g4irsf17_i1_observation_available &&
          (opportunity.kind !=
               G4IRSF14CloneBoundaryKind::kSourceArbitration ||
           opportunity.g4irsf17_i1_observation_peer_runtime_bag_id < 0 ||
           opportunity.g4irsf17_i1_observation_peer_runtime_bag_id ==
               opportunity.runtime_bag_id ||
           !g4irsf14_clone_detail::contains(
               opportunity.source_ready_order,
               opportunity.g4irsf17_i1_observation_peer_runtime_bag_id))) {
        throw std::invalid_argument(
            "G17 I1 skeleton observation does not bind its local peer");
      }
      if (opportunity.g4irsf23_source_observation_available &&
          (opportunity.kind !=
               G4IRSF14CloneBoundaryKind::kSourceArbitration ||
           !opportunity.baseline_release || opportunity.node != 52 ||
           !g4irsf14_clone_detail::contains(
               opportunity.source_ready_order,
               opportunity.runtime_bag_id) ||
           !std::all_of(
               opportunity.g4irsf23_source_observation.begin(),
               opportunity.g4irsf23_source_observation.end(),
               [](double value) { return std::isfinite(value); }))) {
        throw std::invalid_argument(
            "G23 Source skeleton observation is not local and legal");
      }
      if (opportunity.kind ==
              G4IRSF14CloneBoundaryKind::kJunctionRouteArbitration &&
          opportunity.legal_next_edges.empty()) {
        throw std::invalid_argument(
            "I3 skeleton requires legal local next edges");
      }
      if (opportunity.kind ==
              G4IRSF14CloneBoundaryKind::kHoldReleaseOpportunity &&
          !opportunity.baseline_release) {
        throw std::invalid_argument(
            "I4 skeleton requires a baseline release");
      }
    }
  }
};

inline bool g4irsf15_i3_committed_new_pending_request(
    std::uint64_t pre_request_id,
    std::uint64_t pre_request_lineage,
    std::uint64_t post_request_id,
    std::uint64_t post_request_lineage,
    bool pending_dispatch_matches_selected_action) noexcept {
  return pre_request_id == 0U &&
         pre_request_lineage == 0U &&
         post_request_id != 0U &&
         post_request_lineage != 0U &&
         pending_dispatch_matches_selected_action;
}

// Read-only snapshots used by the offline G4IRSF15 paired-intervention
// campaign. They deliberately expose only per-bag/local state: no future
// route, global queue, or planner state is available to a treatment.
struct G4IRSF15CausalBagOutcome {
  int runtime_bag_id = -1;
  int task_id = -1;
  std::string segment_id;
  int start = -1;
  int goal = -1;
  int current_node = -1;
  bool known = false;
  bool completed = false;
  bool failed = false;
  double release_time = 0.0;
  double deadline = -1.0;
  double admitted_time = -1.0;
  double finish_time = -1.0;
  double source_wait_seconds = 0.0;
  double total_local_wait_seconds = 0.0;
  double junction_wait_seconds = 0.0;
  double merge_wait_seconds = 0.0;
  double edge_travel_seconds = 0.0;
  double node_service_seconds = 0.0;
  double loop_extra_seconds = 0.0;
  double completion_seconds = 0.0;
  int decision_count = 0;
  int retry_count = 0;
  int loop_count = 0;
  std::string status = "UNKNOWN";
  std::string failure_reason;
};

struct G4IRSF15LocalActionSnapshot {
  int runtime_bag_id = -1;
  bool known = false;
  std::string status = "UNKNOWN";
  int current_node = -1;
  int transit_from = -1;
  int transit_to = -1;
  double admitted_time = -1.0;
  int decision_count = 0;
  int retry_count = 0;
  std::uint64_t pending_merge_request_id = 0;
  std::uint64_t pending_merge_lineage = 0;
  int pending_merge_upstream = -1;
  int pending_merge_destination = -1;
  bool queued_at_current_node = false;
  bool source_queued_at_current_node = false;
  bool junction_wakeup_pending = false;
  std::uint64_t junction_wakeup_generation = 0;
  double junction_wakeup_time = -1.0;
};

// Outcome-free, node-local observations for the offline G22 value-of-
// information study.  This is deliberately a summary rather than an event
// trace: the production scorer never sees it, and collecting it cannot choose
// or modify an action.
struct G4IRSF22LocalGuidanceSnapshot {
  double simulated_time = 0.0;
  int node = -1;
  bool known = false;
  int junction_queue_length = 0;
  int scheduled_incoming = 0;
  double service_next_available = 0.0;
  std::uint64_t service_reservation_count = 0;
  double queued_wait_seconds = 0.0;
};

}  // namespace czr005::ics
