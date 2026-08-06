#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iterator>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/runtime/g4irsf17_source_policy.hpp"

namespace czr005::ics {

inline constexpr std::string_view kG4IRSF14StateCloneSchema =
    "czr005.g4irsf14.matched_runtime_state_clone.v2";

namespace g4irsf14_clone_detail {

inline bool is_lower_sha256(std::string_view value) noexcept {
  if (value.size() != 64U) {
    return false;
  }
  return std::all_of(value.begin(), value.end(), [](const char byte) {
    return (byte >= '0' && byte <= '9') || (byte >= 'a' && byte <= 'f');
  });
}

inline void require_sha256(std::string_view name, std::string_view value) {
  if (!is_lower_sha256(value)) {
    throw std::invalid_argument(std::string(name) +
                                " must be a 64-character lower-case SHA-256");
  }
}

class CanonicalFields {
 public:
  // Cross-language v2 wire format:
  //   magic "CZR005-CANONICAL-FIELDS\x02";
  //   repeated {u32be name_size, name bytes, u8 type, typed payload}.
  // Strings/vectors start with u64be element count; signed integers use
  // two's-complement u64be; doubles use their IEEE-754 binary64 bits u64be.
  // Field order is schema order.  No locale, host endian, text formatting, or
  // unordered-container iteration participates in the encoding.
  CanonicalFields()
      : payload_("CZR005-CANONICAL-FIELDS\x02", 24U) {}

  void string(std::string_view name, std::string_view value) {
    begin(name, 's');
    append_u64(static_cast<std::uint64_t>(value.size()));
    payload_.append(value);
  }

  void integer(std::string_view name, std::int64_t value) {
    begin(name, 'i');
    append_u64(static_cast<std::uint64_t>(value));
  }

  void unsigned_integer(std::string_view name, std::uint64_t value) {
    begin(name, 'u');
    append_u64(value);
  }

  void boolean(std::string_view name, bool value) {
    begin(name, 'b');
    payload_.push_back(value ? '\x01' : '\x00');
  }

  void floating(std::string_view name, double value) {
    if (!std::isfinite(value)) {
      throw std::invalid_argument(std::string(name) +
                                  " must be finite for canonical encoding");
    }
    static_assert(sizeof(double) == sizeof(std::uint64_t),
                  "G4IRSF14 canonical encoding requires binary64 doubles");
    std::uint64_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    begin(name, 'd');
    append_u64(bits);
  }

  void integers(std::string_view name, const std::vector<int>& values) {
    begin(name, 'I');
    append_u64(static_cast<std::uint64_t>(values.size()));
    for (const int value : values) {
      append_u64(static_cast<std::uint64_t>(
          static_cast<std::int64_t>(value)));
    }
  }

  void unsigned_integers(std::string_view name,
                         const std::vector<std::uint64_t>& values) {
    begin(name, 'U');
    append_u64(static_cast<std::uint64_t>(values.size()));
    for (const std::uint64_t value : values) {
      append_u64(value);
    }
  }

  void signed_integers(
      std::string_view name,
      const std::vector<std::int64_t>& values) {
    begin(name, 'L');
    append_u64(static_cast<std::uint64_t>(values.size()));
    for (const std::int64_t value : values) {
      append_u64(static_cast<std::uint64_t>(value));
    }
  }

  [[nodiscard]] const std::string& payload() const noexcept { return payload_; }

 private:
  void begin(std::string_view name, char type) {
    if (name.size() >
        static_cast<std::size_t>(
            std::numeric_limits<std::uint32_t>::max())) {
      throw std::length_error("canonical field name is too long");
    }
    append_u32(static_cast<std::uint32_t>(name.size()));
    payload_.append(name);
    payload_.push_back(type);
  }

  void append_u32(std::uint32_t value) {
    for (int shift = 24; shift >= 0; shift -= 8) {
      payload_.push_back(
          static_cast<char>((value >> shift) & 0xffU));
    }
  }

  void append_u64(std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
      payload_.push_back(
          static_cast<char>((value >> shift) & 0xffU));
    }
  }

  std::string payload_;
};

template <typename Value>
inline bool contains(const std::vector<Value>& values, const Value& target) {
  return std::find(values.begin(), values.end(), target) != values.end();
}

template <typename Value>
inline bool all_unique(const std::vector<Value>& values) {
  return std::set<Value>(values.begin(), values.end()).size() == values.size();
}

}  // namespace g4irsf14_clone_detail

enum class G4IRSF14CloneBoundaryKind {
  kSourceArbitration,
  kMergeGrantArbitration,
  kJunctionRouteArbitration,
  kHoldReleaseOpportunity,
  kPIBTReadySlice,
};

inline const char* g4irsf14_clone_boundary_kind_name(
    G4IRSF14CloneBoundaryKind value) {
  switch (value) {
    case G4IRSF14CloneBoundaryKind::kSourceArbitration:
      return "source_arbitration";
    case G4IRSF14CloneBoundaryKind::kMergeGrantArbitration:
      return "merge_grant_arbitration";
    case G4IRSF14CloneBoundaryKind::kJunctionRouteArbitration:
      return "junction_route_arbitration";
    case G4IRSF14CloneBoundaryKind::kHoldReleaseOpportunity:
      return "hold_release_opportunity";
    case G4IRSF14CloneBoundaryKind::kPIBTReadySlice:
      return "pibt_ready_slice";
  }
  throw std::logic_error("unknown G4IRSF14 clone boundary kind");
}

enum class G4IRSF14CloneInterventionKind {
  kNoOp,
  kSourceOrderSwap,
  kMergeRequestOrderSwap,
  kNextEdge,
  kHoldRelease,
  kPIBTTrigger,
};

inline const char* g4irsf14_clone_intervention_kind_name(
    G4IRSF14CloneInterventionKind value) {
  switch (value) {
    case G4IRSF14CloneInterventionKind::kNoOp:
      return "I0_no_op";
    case G4IRSF14CloneInterventionKind::kSourceOrderSwap:
      return "I1_source_order_swap";
    case G4IRSF14CloneInterventionKind::kMergeRequestOrderSwap:
      return "I2_merge_request_order_swap";
    case G4IRSF14CloneInterventionKind::kNextEdge:
      return "I3_next_edge";
    case G4IRSF14CloneInterventionKind::kHoldRelease:
      return "I4_hold_release";
    case G4IRSF14CloneInterventionKind::kPIBTTrigger:
      return "I5_pibt_trigger";
  }
  throw std::logic_error("unknown G4IRSF14 clone intervention kind");
}

enum class G4IRSF14CloneHorizon {
  kLocal,
  kAffectedBag,
  kSelectedSystem,
};

inline const char* g4irsf14_clone_horizon_name(G4IRSF14CloneHorizon value) {
  switch (value) {
    case G4IRSF14CloneHorizon::kLocal:
      return "H_local";
    case G4IRSF14CloneHorizon::kAffectedBag:
      return "H_bag";
    case G4IRSF14CloneHorizon::kSelectedSystem:
      return "H_system";
  }
  throw std::logic_error("unknown G4IRSF14 clone horizon");
}

// Each field is the canonical SHA-256 of an actual owned runtime-state
// component.  The list is intentionally fixed instead of map-shaped so a new
// harness cannot silently omit a required component.
struct G4IRSF14RuntimeStateDigests {
  std::string event_queue_sha256;
  std::string current_time_sha256;
  std::string bags_sha256;
  std::string source_queues_sha256;
  std::string junction_queues_sha256;
  std::string local_service_calendars_sha256;
  std::string corridor_state_sha256;
  std::string scheduled_incoming_sha256;
  std::string credits_sha256;
  std::string merge_grants_sha256;
  std::string fault_state_sha256;
  std::string pibt_owner_state_sha256;
  std::string deterministic_counters_sha256;
  std::string scorer_state_sha256;
  std::string result_accumulator_sha256;
  std::string current_runtime_hashes_sha256;
  std::string congestion_beacons_sha256;
  std::string microphase_state_sha256;

  void validate() const {
    using g4irsf14_clone_detail::require_sha256;
    require_sha256("event_queue_sha256", event_queue_sha256);
    require_sha256("current_time_sha256", current_time_sha256);
    require_sha256("bags_sha256", bags_sha256);
    require_sha256("source_queues_sha256", source_queues_sha256);
    require_sha256("junction_queues_sha256", junction_queues_sha256);
    require_sha256("local_service_calendars_sha256",
                   local_service_calendars_sha256);
    require_sha256("corridor_state_sha256", corridor_state_sha256);
    require_sha256("scheduled_incoming_sha256", scheduled_incoming_sha256);
    require_sha256("credits_sha256", credits_sha256);
    require_sha256("merge_grants_sha256", merge_grants_sha256);
    require_sha256("fault_state_sha256", fault_state_sha256);
    require_sha256("pibt_owner_state_sha256", pibt_owner_state_sha256);
    require_sha256("deterministic_counters_sha256",
                   deterministic_counters_sha256);
    require_sha256("scorer_state_sha256", scorer_state_sha256);
    require_sha256("result_accumulator_sha256", result_accumulator_sha256);
    require_sha256("current_runtime_hashes_sha256",
                   current_runtime_hashes_sha256);
    require_sha256("congestion_beacons_sha256", congestion_beacons_sha256);
    require_sha256("microphase_state_sha256", microphase_state_sha256);
  }

  [[nodiscard]] std::string canonical_payload() const {
    validate();
    g4irsf14_clone_detail::CanonicalFields fields;
    fields.string("schema", kG4IRSF14StateCloneSchema);
    fields.string("event_queue", event_queue_sha256);
    fields.string("current_time", current_time_sha256);
    fields.string("bags", bags_sha256);
    fields.string("source_queues", source_queues_sha256);
    fields.string("junction_queues", junction_queues_sha256);
    fields.string("local_service_calendars", local_service_calendars_sha256);
    fields.string("corridor_state", corridor_state_sha256);
    fields.string("scheduled_incoming", scheduled_incoming_sha256);
    fields.string("credits", credits_sha256);
    fields.string("merge_grants", merge_grants_sha256);
    fields.string("fault_state", fault_state_sha256);
    fields.string("pibt_owner_state", pibt_owner_state_sha256);
    fields.string("deterministic_counters", deterministic_counters_sha256);
    fields.string("scorer_state", scorer_state_sha256);
    fields.string("result_accumulator", result_accumulator_sha256);
    fields.string("current_runtime_hashes", current_runtime_hashes_sha256);
    fields.string("congestion_beacons", congestion_beacons_sha256);
    fields.string("microphase_state", microphase_state_sha256);
    return fields.payload();
  }

  [[nodiscard]] std::string aggregate_sha256() const {
    return canonical_map2_detail::sha256_hex(canonical_payload());
  }
};

struct G4IRSF14CloneBoundary {
  std::string clone_group_id;
  G4IRSF14CloneBoundaryKind kind =
      G4IRSF14CloneBoundaryKind::kSourceArbitration;
  double time = 0.0;
  std::uint64_t event_seq = 0;
  int node = -1;
  int runtime_bag_id = -1;
  int baseline_next_node = -1;
  bool baseline_release = false;
  bool baseline_pibt_enabled = false;
  int pibt_owner_runtime_bag_id = -1;
  std::vector<int> source_ready_order;
  // Outcome-free G17 sidecar for the exact G15 I1 baseline/primary-peer
  // action.  It is intentionally excluded from the content address: these
  // observations are training inputs, never action identity.
  bool g4irsf17_i1_observation_available = false;
  int g4irsf17_i1_observation_peer_runtime_bag_id = -1;
  std::array<double, kG4IRSF17SourcePairwiseFeatureCount>
      g4irsf17_i1_baseline_observation{};
  std::array<double, kG4IRSF17SourcePairwiseFeatureCount>
      g4irsf17_i1_treatment_observation{};
  std::array<double, kG4IRSF17SourcePairwiseFeatureCount>
      g4irsf17_i1_pairwise_features{};
  std::vector<std::uint64_t> pending_merge_request_order;
  std::vector<int> legal_next_edges;
  std::vector<int> pibt_ready_bag_ids;
  std::vector<int> pibt_ready_current_nodes;
  std::vector<std::int64_t> pibt_owner_resources;
  std::vector<int> pibt_owner_bag_ids;
  std::vector<int> pibt_candidate_bag_ids;
  std::vector<int> pibt_candidate_next_nodes;
  std::vector<std::int64_t> pibt_candidate_edge_resources;
  std::vector<std::uint64_t>
      pibt_candidate_expected_fault_generations;
  std::vector<std::uint64_t>
      pibt_candidate_required_resource_offsets;
  std::vector<std::int64_t>
      pibt_candidate_required_resources;
  G4IRSF14RuntimeStateDigests state;
  std::string runtime_state_sha256;

  // A valid freeze happens before pop/process, while no transactional event
  // staging is active.  These are audited facts, not tunable switches.
  bool queue_top_not_popped = false;
  bool staged_event_sink_empty = false;
  int runtime_global_scan_count = 0;
  int runtime_future_route_read_count = 0;
  int runtime_future_schedule_read_count = 0;
  int reservation_depth = 1;
  int max_selected_edges_per_bag = 1;

  void validate() const {
    if (!std::isfinite(time) || time < 0.0 || event_seq == 0U || node < 0) {
      throw std::invalid_argument(
          "clone boundary requires finite non-negative time, event_seq, and node");
    }
    if (!queue_top_not_popped || !staged_event_sink_empty) {
      throw std::invalid_argument(
          "clone boundary must be queue-top pre-pop with no staged event sink");
    }
    if (runtime_global_scan_count != 0 ||
        runtime_future_route_read_count != 0 ||
        runtime_future_schedule_read_count != 0) {
      throw std::invalid_argument(
          "clone boundary leaked global or future runtime state");
    }
    if (reservation_depth != 1 || max_selected_edges_per_bag > 1) {
      throw std::invalid_argument(
          "clone boundary violates one-edge reservation semantics");
    }
    if (!g4irsf14_clone_detail::all_unique(source_ready_order) ||
        !g4irsf14_clone_detail::all_unique(pending_merge_request_order) ||
        !g4irsf14_clone_detail::all_unique(legal_next_edges)) {
      throw std::invalid_argument("clone boundary local ready sets must be unique");
    }
    if (g4irsf17_i1_observation_available) {
      const auto all_finite = [](const auto& values) {
        return std::all_of(values.begin(), values.end(),
                           [](double value) {
                             return std::isfinite(value);
                           });
      };
      if (kind != G4IRSF14CloneBoundaryKind::kSourceArbitration ||
          runtime_bag_id < 0 ||
          g4irsf17_i1_observation_peer_runtime_bag_id < 0 ||
          g4irsf17_i1_observation_peer_runtime_bag_id == runtime_bag_id ||
          !g4irsf14_clone_detail::contains(
              source_ready_order,
              g4irsf17_i1_observation_peer_runtime_bag_id) ||
          !all_finite(g4irsf17_i1_baseline_observation) ||
          !all_finite(g4irsf17_i1_treatment_observation) ||
          !all_finite(g4irsf17_i1_pairwise_features)) {
        throw std::invalid_argument(
            "G17 I1 observation sidecar is not a valid local pair");
      }
      for (std::size_t index = 0;
           index < kG4IRSF17SourceCandidateFeatureCount; ++index) {
        if (std::abs(g4irsf17_i1_pairwise_features[index] -
                     (g4irsf17_i1_treatment_observation[index] -
                      g4irsf17_i1_baseline_observation[index])) >
            1.0e-9) {
          throw std::invalid_argument(
              "G17 I1 pairwise candidate delta drifted");
        }
      }
      for (std::size_t index = kG4IRSF17SourceCandidateFeatureCount;
           index < kG4IRSF17SourcePairwiseFeatureCount; ++index) {
        if (std::abs(g4irsf17_i1_baseline_observation[index] -
                     g4irsf17_i1_treatment_observation[index]) >
                1.0e-9 ||
            std::abs(g4irsf17_i1_pairwise_features[index] -
                     g4irsf17_i1_baseline_observation[index]) >
                1.0e-9) {
          throw std::invalid_argument(
              "G17 I1 shared local context drifted");
        }
      }
    } else if (g4irsf17_i1_observation_peer_runtime_bag_id != -1) {
      throw std::invalid_argument(
          "G17 I1 observation peer exists without an observation");
    }
    const bool pibt_vectors_empty =
        pibt_ready_bag_ids.empty() &&
        pibt_ready_current_nodes.empty() &&
        pibt_owner_resources.empty() &&
        pibt_owner_bag_ids.empty() &&
        pibt_candidate_bag_ids.empty() &&
        pibt_candidate_next_nodes.empty() &&
        pibt_candidate_edge_resources.empty() &&
        pibt_candidate_expected_fault_generations.empty() &&
        pibt_candidate_required_resource_offsets.empty() &&
        pibt_candidate_required_resources.empty();
    if (kind == G4IRSF14CloneBoundaryKind::kPIBTReadySlice) {
      if (!baseline_pibt_enabled || runtime_bag_id < 0 ||
          pibt_owner_runtime_bag_id != runtime_bag_id ||
          pibt_ready_bag_ids.empty() ||
          pibt_owner_resources.empty() ||
          pibt_candidate_bag_ids.empty() ||
          pibt_ready_current_nodes.size() !=
              pibt_ready_bag_ids.size() ||
          pibt_owner_resources.size() !=
              pibt_owner_bag_ids.size() ||
          pibt_candidate_next_nodes.size() !=
              pibt_candidate_bag_ids.size() ||
          pibt_candidate_edge_resources.size() !=
              pibt_candidate_bag_ids.size() ||
          pibt_candidate_expected_fault_generations.size() !=
              pibt_candidate_bag_ids.size() ||
          pibt_candidate_required_resource_offsets.size() !=
              pibt_candidate_bag_ids.size() + 1U ||
          pibt_candidate_required_resource_offsets.front() != 0U ||
          pibt_candidate_required_resource_offsets.back() !=
              pibt_candidate_required_resources.size() ||
          !g4irsf14_clone_detail::all_unique(
              pibt_ready_bag_ids) ||
          !g4irsf14_clone_detail::all_unique(
              pibt_owner_resources) ||
          !g4irsf14_clone_detail::contains(
              pibt_ready_bag_ids,
              pibt_owner_runtime_bag_id)) {
        throw std::invalid_argument(
            "I5 boundary must bind one complete applicable PIBT slice");
      }
      for (const int owner : pibt_owner_bag_ids) {
        if (!g4irsf14_clone_detail::contains(
                pibt_ready_bag_ids, owner)) {
          throw std::invalid_argument(
              "PIBT owner map references a bag outside the ready slice");
        }
      }
      for (std::size_t index = 0;
           index < pibt_candidate_bag_ids.size(); ++index) {
        const auto begin =
            pibt_candidate_required_resource_offsets[index];
        const auto end =
            pibt_candidate_required_resource_offsets[index + 1U];
        if (pibt_candidate_next_nodes[index] < 0 ||
            !g4irsf14_clone_detail::contains(
                pibt_ready_bag_ids,
                pibt_candidate_bag_ids[index]) ||
            begin >= end ||
            end > pibt_candidate_required_resources.size() ||
            std::find(
                pibt_candidate_required_resources.begin() +
                    static_cast<std::ptrdiff_t>(begin),
                pibt_candidate_required_resources.begin() +
                    static_cast<std::ptrdiff_t>(end),
                pibt_candidate_edge_resources[index]) ==
                pibt_candidate_required_resources.begin() +
                    static_cast<std::ptrdiff_t>(end)) {
          throw std::invalid_argument(
              "PIBT candidate set is not a valid ordered slice");
        }
      }
    } else if (!pibt_vectors_empty) {
      throw std::invalid_argument(
          "non-I5 boundary cannot carry PIBT slice state");
    }
    state.validate();
    g4irsf14_clone_detail::require_sha256("runtime_state_sha256",
                                         runtime_state_sha256);
    if (runtime_state_sha256 != state.aggregate_sha256()) {
      throw std::invalid_argument(
          "runtime_state_sha256 does not bind all required state components");
    }
    g4irsf14_clone_detail::require_sha256(
        "clone_group_id", clone_group_id);
    if (clone_group_id != expected_clone_group_id()) {
      throw std::invalid_argument(
          "clone_group_id is not the pre-outcome boundary content address");
    }
  }

  [[nodiscard]] std::string pre_outcome_identity_payload() const {
    state.validate();
    g4irsf14_clone_detail::require_sha256(
        "runtime_state_sha256", runtime_state_sha256);
    if (runtime_state_sha256 != state.aggregate_sha256()) {
      throw std::invalid_argument(
          "clone identity state hash does not bind the inventory");
    }
    g4irsf14_clone_detail::CanonicalFields fields;
    fields.string("schema", kG4IRSF14StateCloneSchema);
    fields.string("runtime_state_sha256", runtime_state_sha256);
    return fields.payload();
  }

  [[nodiscard]] std::string expected_clone_group_id() const {
    return canonical_map2_detail::sha256_hex(
        pre_outcome_identity_payload());
  }

  [[nodiscard]] std::string canonical_payload() const {
    validate();
    g4irsf14_clone_detail::CanonicalFields fields;
    fields.string("schema", kG4IRSF14StateCloneSchema);
    fields.string("clone_group_id", clone_group_id);
    fields.string("kind", g4irsf14_clone_boundary_kind_name(kind));
    fields.floating("time", time);
    fields.unsigned_integer("event_seq", event_seq);
    fields.integer("node", node);
    fields.integer("runtime_bag_id", runtime_bag_id);
    fields.integer("baseline_next_node", baseline_next_node);
    fields.boolean("baseline_release", baseline_release);
    fields.boolean("baseline_pibt_enabled", baseline_pibt_enabled);
    fields.integer("pibt_owner_runtime_bag_id", pibt_owner_runtime_bag_id);
    fields.integers("source_ready_order", source_ready_order);
    fields.unsigned_integers("pending_merge_request_order",
                             pending_merge_request_order);
    fields.integers("legal_next_edges", legal_next_edges);
    fields.integers("pibt_ready_bag_ids", pibt_ready_bag_ids);
    fields.integers("pibt_ready_current_nodes",
                    pibt_ready_current_nodes);
    fields.signed_integers("pibt_owner_resources",
                           pibt_owner_resources);
    fields.integers("pibt_owner_bag_ids",
                    pibt_owner_bag_ids);
    fields.integers("pibt_candidate_bag_ids",
                    pibt_candidate_bag_ids);
    fields.integers("pibt_candidate_next_nodes",
                    pibt_candidate_next_nodes);
    fields.signed_integers(
        "pibt_candidate_edge_resources",
        pibt_candidate_edge_resources);
    fields.unsigned_integers(
        "pibt_candidate_expected_fault_generations",
        pibt_candidate_expected_fault_generations);
    fields.unsigned_integers(
        "pibt_candidate_required_resource_offsets",
        pibt_candidate_required_resource_offsets);
    fields.signed_integers(
        "pibt_candidate_required_resources",
        pibt_candidate_required_resources);
    fields.string("runtime_state_sha256", runtime_state_sha256);
    fields.boolean("queue_top_not_popped", queue_top_not_popped);
    fields.boolean("staged_event_sink_empty", staged_event_sink_empty);
    fields.integer("runtime_global_scan_count", runtime_global_scan_count);
    fields.integer("runtime_future_route_read_count",
                   runtime_future_route_read_count);
    fields.integer("runtime_future_schedule_read_count",
                   runtime_future_schedule_read_count);
    fields.integer("reservation_depth", reservation_depth);
    fields.integer("max_selected_edges_per_bag",
                   max_selected_edges_per_bag);
    return fields.payload();
  }

  [[nodiscard]] std::string boundary_sha256() const {
    return canonical_map2_detail::sha256_hex(canonical_payload());
  }
};

struct G4IRSF14CloneIntervention {
  G4IRSF14CloneInterventionKind kind =
      G4IRSF14CloneInterventionKind::kNoOp;
  G4IRSF14CloneHorizon horizon = G4IRSF14CloneHorizon::kLocal;
  int runtime_bag_id = -1;
  int peer_runtime_bag_id = -1;
  std::uint64_t merge_request_id = 0;
  std::uint64_t peer_merge_request_id = 0;
  int selected_next_node = -1;
  bool selected_boolean = false;

  void validate_against(const G4IRSF14CloneBoundary& boundary) const {
    boundary.validate();
    switch (kind) {
      case G4IRSF14CloneInterventionKind::kNoOp:
        if (runtime_bag_id != -1 || peer_runtime_bag_id != -1 ||
            merge_request_id != 0U || peer_merge_request_id != 0U ||
            selected_next_node != -1 || selected_boolean) {
          throw std::invalid_argument("no-op clone changes an action field");
        }
        return;

      case G4IRSF14CloneInterventionKind::kSourceOrderSwap:
        if (merge_request_id != 0U || peer_merge_request_id != 0U ||
            selected_next_node != -1 || selected_boolean ||
            boundary.kind != G4IRSF14CloneBoundaryKind::kSourceArbitration ||
            runtime_bag_id == peer_runtime_bag_id ||
            !g4irsf14_clone_detail::contains(boundary.source_ready_order,
                                             runtime_bag_id) ||
            !g4irsf14_clone_detail::contains(boundary.source_ready_order,
                                             peer_runtime_bag_id)) {
          throw std::invalid_argument(
              "I1 must swap two distinct bags in the same source ready set");
        }
        return;

      case G4IRSF14CloneInterventionKind::kMergeRequestOrderSwap:
        if (runtime_bag_id != -1 || peer_runtime_bag_id != -1 ||
            selected_next_node != -1 || selected_boolean ||
            boundary.kind !=
                G4IRSF14CloneBoundaryKind::kMergeGrantArbitration ||
            merge_request_id == 0U ||
            merge_request_id == peer_merge_request_id ||
            !g4irsf14_clone_detail::contains(
                boundary.pending_merge_request_order, merge_request_id) ||
            !g4irsf14_clone_detail::contains(
                boundary.pending_merge_request_order,
                peer_merge_request_id)) {
          throw std::invalid_argument(
              "I2 must swap two pending requests at one destination owner");
        }
        return;

      case G4IRSF14CloneInterventionKind::kNextEdge:
        if (peer_runtime_bag_id != -1 || merge_request_id != 0U ||
            peer_merge_request_id != 0U || selected_boolean ||
            boundary.kind !=
                G4IRSF14CloneBoundaryKind::kJunctionRouteArbitration ||
            runtime_bag_id != boundary.runtime_bag_id ||
            selected_next_node == boundary.baseline_next_node ||
            !g4irsf14_clone_detail::contains(boundary.legal_next_edges,
                                             selected_next_node)) {
          throw std::invalid_argument(
              "I3 must select one different legal adjacent next edge");
        }
        return;

      case G4IRSF14CloneInterventionKind::kHoldRelease:
        if (peer_runtime_bag_id != -1 || merge_request_id != 0U ||
            peer_merge_request_id != 0U || selected_next_node != -1 ||
            boundary.kind !=
                G4IRSF14CloneBoundaryKind::kHoldReleaseOpportunity ||
            runtime_bag_id != boundary.runtime_bag_id ||
            !boundary.baseline_release || selected_boolean) {
          throw std::invalid_argument(
              "I4 may only change one baseline release into a safe hold");
        }
        return;

      case G4IRSF14CloneInterventionKind::kPIBTTrigger:
        if (peer_runtime_bag_id != -1 || merge_request_id != 0U ||
            peer_merge_request_id != 0U || selected_next_node != -1 ||
            boundary.kind != G4IRSF14CloneBoundaryKind::kPIBTReadySlice ||
            runtime_bag_id != boundary.runtime_bag_id ||
            selected_boolean == boundary.baseline_pibt_enabled) {
          throw std::invalid_argument(
              "I5 must only flip P2 for the identical ready slice");
        }
        return;
    }
    throw std::logic_error("unknown G4IRSF14 clone intervention");
  }

  [[nodiscard]] std::string canonical_payload(
      const G4IRSF14CloneBoundary& boundary) const {
    validate_against(boundary);
    g4irsf14_clone_detail::CanonicalFields fields;
    fields.string("schema", kG4IRSF14StateCloneSchema);
    fields.string("boundary_sha256", boundary.boundary_sha256());
    fields.string("kind", g4irsf14_clone_intervention_kind_name(kind));
    fields.string("horizon", g4irsf14_clone_horizon_name(horizon));
    fields.integer("runtime_bag_id", runtime_bag_id);
    fields.integer("peer_runtime_bag_id", peer_runtime_bag_id);
    fields.unsigned_integer("merge_request_id", merge_request_id);
    fields.unsigned_integer("peer_merge_request_id",
                            peer_merge_request_id);
    fields.integer("selected_next_node", selected_next_node);
    fields.boolean("selected_boolean", selected_boolean);
    return fields.payload();
  }

  [[nodiscard]] std::string intervention_sha256(
      const G4IRSF14CloneBoundary& boundary) const {
    return canonical_map2_detail::sha256_hex(canonical_payload(boundary));
  }
};

struct G4IRSF14CloneReplayHashes {
  std::string complete_bags_sha256;
  std::string segment_result_sha256;
  std::string junction_state_sha256;
  std::string algorithm_summary_sha256;
  std::string deterministic_result_sha256;

  void validate() const {
    using g4irsf14_clone_detail::require_sha256;
    require_sha256("complete_bags_sha256", complete_bags_sha256);
    require_sha256("segment_result_sha256", segment_result_sha256);
    require_sha256("junction_state_sha256", junction_state_sha256);
    require_sha256("algorithm_summary_sha256", algorithm_summary_sha256);
    require_sha256("deterministic_result_sha256",
                   deterministic_result_sha256);
  }

  [[nodiscard]] bool exactly_matches(
      const G4IRSF14CloneReplayHashes& other) const {
    validate();
    other.validate();
    return complete_bags_sha256 == other.complete_bags_sha256 &&
           segment_result_sha256 == other.segment_result_sha256 &&
           junction_state_sha256 == other.junction_state_sha256 &&
           algorithm_summary_sha256 == other.algorithm_summary_sha256 &&
           deterministic_result_sha256 ==
               other.deterministic_result_sha256;
  }
};

struct G4IRSF14CloneOutcome {
  G4IRSF14CloneHorizon horizon = G4IRSF14CloneHorizon::kLocal;
  bool horizon_complete = false;
  bool safety_equivalent = false;
  int affected_bag_count = 0;
  int completed_affected_bag_count = 0;
  int deadline_miss_delta = 0;
  int unsafe_commit_count = 0;
  int reservation_conflict_count = 0;
  int max_selected_edges_per_bag = 1;
  double affected_bag_completion_delta_seconds = 0.0;
  double local_group_delay_delta_seconds = 0.0;
  double system_mean_delta_seconds = 0.0;
  double system_p95_delta_seconds = 0.0;
  double system_p99_delta_seconds = 0.0;
  double source_wait_delta_seconds = 0.0;
  double network_wait_delta_seconds = 0.0;
  double path_length_delta = 0.0;
  double grant_wait_delta_seconds = 0.0;

  void validate_for_label() const {
    if (!horizon_complete || !safety_equivalent) {
      throw std::invalid_argument(
          "causal label requires a complete, safety-equivalent horizon");
    }
    if (affected_bag_count <= 0 ||
        completed_affected_bag_count != affected_bag_count) {
      throw std::invalid_argument(
          "causal label requires every affected bag to complete");
    }
    if (unsafe_commit_count != 0 || reservation_conflict_count != 0 ||
        max_selected_edges_per_bag > 1) {
      throw std::invalid_argument(
          "causal label violates safety or one-edge equivalence");
    }
    const double values[] = {
        affected_bag_completion_delta_seconds,
        local_group_delay_delta_seconds,
        system_mean_delta_seconds,
        system_p95_delta_seconds,
        system_p99_delta_seconds,
        source_wait_delta_seconds,
        network_wait_delta_seconds,
        path_length_delta,
        grant_wait_delta_seconds,
    };
    if (!std::all_of(std::begin(values), std::end(values),
                     [](double value) { return std::isfinite(value); })) {
      throw std::invalid_argument("causal label deltas must be finite");
    }
  }
};

struct G4IRSF14CloneCampaignAudit {
  int fidelity_clone_count = 0;
  int fidelity_exact_match_count = 0;
  int matched_intervention_count = 0;
  int complete_label_count = 0;
  int selected_system_horizon_count = 0;
  int non_improving_intervention_count = 0;
  int retained_non_improving_intervention_count = 0;
  int runtime_global_scan_count = 0;
  int runtime_future_route_read_count = 0;
  int runtime_future_schedule_read_count = 0;
  bool full_runtime_state_clone_used = false;
  bool level_a_projection_used_as_label = false;

  void validate_for_training_labels() const {
    if (!full_runtime_state_clone_used ||
        level_a_projection_used_as_label) {
      throw std::invalid_argument(
          "training labels require full runtime clones and prohibit Level-A labels");
    }
    if (fidelity_clone_count <= 0 ||
        fidelity_exact_match_count != fidelity_clone_count) {
      throw std::invalid_argument("clone replay fidelity must be exactly 100%");
    }
    if (matched_intervention_count < 2000 ||
        complete_label_count != matched_intervention_count ||
        selected_system_horizon_count <= 0) {
      throw std::invalid_argument(
          "clone campaign lacks complete matched/system-horizon evidence");
    }
    if (non_improving_intervention_count !=
        retained_non_improving_intervention_count) {
      throw std::invalid_argument(
          "negative or zero interventions must be retained");
    }
    if (runtime_global_scan_count != 0 ||
        runtime_future_route_read_count != 0 ||
        runtime_future_schedule_read_count != 0) {
      throw std::invalid_argument(
          "clone campaign leaked global or future runtime state");
    }
  }
};

// Production matched forks restore two independently constructed runtimes
// through the runtime's explicit offline checkpoint codec.  The live runtime,
// merge controller, and capability remain non-copyable.
template <typename Runtime>
class G4IRSF14MatchedRuntimeFork {
 public:
  using Checkpoint = typename Runtime::StateCheckpoint;

  G4IRSF14MatchedRuntimeFork(Runtime& baseline,
                            Runtime& treatment,
                            const Checkpoint& checkpoint)
      : baseline_(&baseline),
        treatment_(&treatment),
        source_state_sha256_(checkpoint.state_sha256()) {
    baseline_->restore_state_checkpoint(checkpoint);
    treatment_->restore_state_checkpoint(checkpoint);
    g4irsf14_clone_detail::require_sha256(
        "source_state_sha256", source_state_sha256_);
    if (baseline_->deterministic_state_sha256() !=
            source_state_sha256_ ||
        treatment_->deterministic_state_sha256() !=
            source_state_sha256_) {
      throw std::logic_error(
          "matched runtime fork failed exact checkpoint restore");
    }
  }

  Runtime& baseline() noexcept { return *baseline_; }
  Runtime& treatment() noexcept { return *treatment_; }
  [[nodiscard]] const std::string& source_state_sha256() const noexcept {
    return source_state_sha256_;
  }

 private:
  Runtime* baseline_ = nullptr;
  Runtime* treatment_ = nullptr;
  std::string source_state_sha256_;
};

}  // namespace czr005::ics
