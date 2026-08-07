#pragma once

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cctype>
#include <cstring>
#include <deque>
#include <limits>
#include <map>
#include <memory>
#include <numeric>
#include <optional>
#include <queue>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <type_traits>
#include <typeinfo>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/models/edge_score.hpp"
#include "ics_core/runtime/bounded_local_pibt.hpp"
#include "ics_core/runtime/destination_merge_grant.hpp"
#include "ics_core/runtime/expiring_first_edge_credit.hpp"
#include "ics_core/runtime/g4irsf14_causal_intervention.hpp"
#include "ics_core/runtime/g4irsf14_state_clone.hpp"
#include "ics_core/runtime/g4irsf15_causal_campaign.hpp"
#include "ics_core/runtime/g4irsf16_supervisor.hpp"
#include "ics_core/runtime/g4irsf17_source_policy.hpp"
#include "ics_core/runtime/g4irsf18_merge_policy.hpp"

namespace czr005::ics {

// G4IRSF11's runtime deliberately owns no A* planner and no global reservation
// table.  A decision reads one junction, its outgoing corridors, and (when
// enabled) a diagnostic summary of the next junction.  Reservations are made
// only for the selected corridor and its destination junction.

enum class JunctionEventType {
  kBagRelease,
  kArriveJunction,
  kJunctionServiceComplete,
  kEdgeEnter,
  kEdgeExit,
  kFault,
  kRepair,
  kLocalQueueUpdate,
  kCongestionBeaconUpdate,
  kSourceArbitration,
  kJunctionArbitration,
  kDestinationMergeArbitration,
};

// G4IRSF17 source-wait attribution is deliberately a small canonical enum,
// rather than a free-form policy label.  The enum is used only for causal
// telemetry; it is never exposed to the scorer as an ID/codebook feature.
enum class G4IRSF17SourceWaitReason : std::uint8_t {
  kSourceServiceNotReady = 0,
  kFirstEdgeCreditUnavailable = 1,
  kDestinationQueueCapacity = 2,
  kDestinationMergeToken = 3,
  kPhysicalFaultOrGeneration = 4,
  kSupervisorHold = 5,
  kPIBTOrRecoveryTransaction = 6,
  kOtherExplicitReason = 7,
};

inline constexpr std::size_t kG4IRSF17SourceWaitReasonCount = 8;

inline const char* g4irsf17_source_wait_reason_name(
    G4IRSF17SourceWaitReason reason) noexcept {
  switch (reason) {
    case G4IRSF17SourceWaitReason::kSourceServiceNotReady:
      return "SOURCE_SERVICE_NOT_READY";
    case G4IRSF17SourceWaitReason::kFirstEdgeCreditUnavailable:
      return "FIRST_EDGE_CREDIT_UNAVAILABLE";
    case G4IRSF17SourceWaitReason::kDestinationQueueCapacity:
      return "DESTINATION_QUEUE_CAPACITY";
    case G4IRSF17SourceWaitReason::kDestinationMergeToken:
      return "DESTINATION_MERGE_TOKEN";
    case G4IRSF17SourceWaitReason::kPhysicalFaultOrGeneration:
      return "PHYSICAL_FAULT_OR_GENERATION";
    case G4IRSF17SourceWaitReason::kSupervisorHold:
      return "SUPERVISOR_HOLD";
    case G4IRSF17SourceWaitReason::kPIBTOrRecoveryTransaction:
      return "PIBT_OR_RECOVERY_TRANSACTION";
    case G4IRSF17SourceWaitReason::kOtherExplicitReason:
      return "OTHER_EXPLICIT_REASON";
  }
  return "OTHER_EXPLICIT_REASON";
}

// Lower ranks win whenever one bounded local observation exposes several
// blockers.  Concrete safety/root causes precede wrapper capabilities; source
// service is evaluated first by the real admission path and therefore never
// competes with downstream observations in this function.
inline constexpr int g4irsf17_source_wait_reason_precedence(
    G4IRSF17SourceWaitReason reason) noexcept {
  switch (reason) {
    case G4IRSF17SourceWaitReason::kPhysicalFaultOrGeneration:
      return 0;
    case G4IRSF17SourceWaitReason::kSupervisorHold:
      return 1;
    case G4IRSF17SourceWaitReason::kPIBTOrRecoveryTransaction:
      return 2;
    case G4IRSF17SourceWaitReason::kDestinationQueueCapacity:
      return 3;
    case G4IRSF17SourceWaitReason::kDestinationMergeToken:
      return 4;
    case G4IRSF17SourceWaitReason::kFirstEdgeCreditUnavailable:
      return 5;
    case G4IRSF17SourceWaitReason::kSourceServiceNotReady:
      return 6;
    case G4IRSF17SourceWaitReason::kOtherExplicitReason:
      return 7;
  }
  return 7;
}

inline const char* junction_event_name(JunctionEventType type) {
  switch (type) {
    case JunctionEventType::kBagRelease:
      return "BAG_RELEASE";
    case JunctionEventType::kArriveJunction:
      return "ARRIVE_JUNCTION";
    case JunctionEventType::kJunctionServiceComplete:
      return "JUNCTION_SERVICE_COMPLETE";
    case JunctionEventType::kEdgeEnter:
      return "EDGE_ENTER";
    case JunctionEventType::kEdgeExit:
      return "EDGE_EXIT";
    case JunctionEventType::kFault:
      return "FAULT";
    case JunctionEventType::kRepair:
      return "REPAIR";
    case JunctionEventType::kLocalQueueUpdate:
      return "LOCAL_QUEUE_UPDATE";
    case JunctionEventType::kCongestionBeaconUpdate:
      return "CONGESTION_BEACON_UPDATE";
    case JunctionEventType::kSourceArbitration:
      return "SOURCE_ARBITRATION";
    case JunctionEventType::kJunctionArbitration:
      return "JUNCTION_ARBITRATION";
    case JunctionEventType::kDestinationMergeArbitration:
      return "DESTINATION_MERGE_ARBITRATION";
  }
  return "UNKNOWN";
}

struct EventRuntimeBagRequest {
  std::string segment_id;
  int task_id = -1;
  double release_time = 0.0;
  double deadline = -1.0;
  int start = -1;
  int goal = -1;
  std::string source;
  int runtime_bag_id = -1;  // assigned by run(); original task_id is never rewritten
};

struct G4IRSF15RawBagSufficientStatisticsRow {
  int task_id = -1;
  std::vector<int> runtime_bag_ids;
  int completed_segment_count = 0;
  bool complete = false;
  bool failed = false;
  bool deadline_miss = false;
  double original_entry_total_seconds = 0.0;
  double java_release_total_seconds = 0.0;
  double scheduled_pre_release_wait_total_seconds = 0.0;
  double source_wait_total_seconds = 0.0;
  double network_time_total_seconds = 0.0;
  double total_system_time_total_seconds = 0.0;

  void validate() const {
    const auto finite_non_negative = [](double value) {
      return std::isfinite(value) && value >= 0.0;
    };
    if (task_id < 0 || runtime_bag_ids.empty() ||
        !std::is_sorted(runtime_bag_ids.begin(),
                        runtime_bag_ids.end()) ||
        std::adjacent_find(runtime_bag_ids.begin(),
                           runtime_bag_ids.end()) !=
            runtime_bag_ids.end() ||
        completed_segment_count < 0 ||
        completed_segment_count >
            static_cast<int>(runtime_bag_ids.size()) ||
        (complete &&
         (failed ||
          completed_segment_count !=
              static_cast<int>(runtime_bag_ids.size()))) ||
        !finite_non_negative(original_entry_total_seconds) ||
        !finite_non_negative(java_release_total_seconds) ||
        !finite_non_negative(
            scheduled_pre_release_wait_total_seconds) ||
        !finite_non_negative(source_wait_total_seconds) ||
        !finite_non_negative(network_time_total_seconds) ||
        !finite_non_negative(total_system_time_total_seconds)) {
      throw std::invalid_argument(
          "invalid G4IRSF15 raw-bag sufficient-statistics row");
    }
    const double decomposed =
        scheduled_pre_release_wait_total_seconds +
        source_wait_total_seconds + network_time_total_seconds;
    if (complete &&
        std::abs(decomposed - original_entry_total_seconds) >
            1.0e-7) {
      throw std::invalid_argument(
          "complete raw-bag timing decomposition drifted");
    }
    if (std::abs(decomposed - total_system_time_total_seconds) >
        1.0e-7) {
      throw std::invalid_argument(
          "raw-bag total-system sufficient statistic drifted");
    }
  }

  [[nodiscard]] std::string runtime_id_mapping_payload() const {
    validate();
    g4irsf14_clone_detail::CanonicalFields fields;
    fields.string(
        "schema",
        "czr005.g4irsf15.raw_bag_runtime_id_mapping_row.v1");
    fields.integer("task_id", task_id);
    fields.integers("runtime_bag_ids", runtime_bag_ids);
    return fields.payload();
  }

  [[nodiscard]] std::string runtime_id_mapping_sha256() const {
    return canonical_map2_detail::sha256_hex(
        runtime_id_mapping_payload());
  }

  [[nodiscard]] std::string canonical_payload() const {
    validate();
    g4irsf14_clone_detail::CanonicalFields fields;
    fields.string(
        "schema",
        "czr005.g4irsf15.raw_bag_sufficient_statistics_row.v1");
    fields.integer("task_id", task_id);
    fields.integers("runtime_bag_ids", runtime_bag_ids);
    fields.integer(
        "runtime_segment_count",
        static_cast<int>(runtime_bag_ids.size()));
    fields.integer("completed_segment_count",
                   completed_segment_count);
    fields.boolean("complete", complete);
    fields.boolean("failed", failed);
    fields.boolean("deadline_miss", deadline_miss);
    fields.floating("original_entry_total_seconds",
                    original_entry_total_seconds);
    fields.floating("java_release_total_seconds",
                    java_release_total_seconds);
    fields.floating(
        "scheduled_pre_release_wait_total_seconds",
        scheduled_pre_release_wait_total_seconds);
    fields.floating("source_wait_total_seconds",
                    source_wait_total_seconds);
    fields.floating("network_time_total_seconds",
                    network_time_total_seconds);
    fields.floating("total_system_time_total_seconds",
                    total_system_time_total_seconds);
    fields.string("runtime_id_mapping_sha256",
                  runtime_id_mapping_sha256());
    return fields.payload();
  }

  [[nodiscard]] std::string row_sha256() const {
    return canonical_map2_detail::sha256_hex(canonical_payload());
  }
};

struct G4IRSF15RawBagSufficientStatistics {
  int selected_segment_count = 0;
  bool complete_coverage = false;
  std::vector<G4IRSF15RawBagSufficientStatisticsRow> rows;

  void validate() const {
    if (selected_segment_count < 0 ||
        static_cast<int>(rows.size()) >
            selected_segment_count) {
      throw std::invalid_argument(
          "invalid G4IRSF15 raw-bag sufficient-statistics inventory");
    }
    int previous_task_id = -1;
    std::vector<int> covered_runtime_ids;
    covered_runtime_ids.reserve(
        static_cast<std::size_t>(selected_segment_count));
    for (const auto& row : rows) {
      row.validate();
      if (row.task_id <= previous_task_id) {
        throw std::invalid_argument(
            "raw-bag sufficient statistics are not in strict "
            "ascending task_id order");
      }
      previous_task_id = row.task_id;
      covered_runtime_ids.insert(covered_runtime_ids.end(),
                                 row.runtime_bag_ids.begin(),
                                 row.runtime_bag_ids.end());
    }
    std::sort(covered_runtime_ids.begin(),
              covered_runtime_ids.end());
    bool exact_coverage =
        covered_runtime_ids.size() ==
        static_cast<std::size_t>(selected_segment_count);
    for (int runtime_id = 0;
         exact_coverage &&
         runtime_id < selected_segment_count;
         ++runtime_id) {
      exact_coverage =
          covered_runtime_ids[static_cast<std::size_t>(runtime_id)] ==
          runtime_id;
    }
    if (complete_coverage != exact_coverage) {
      throw std::invalid_argument(
          "raw-bag sufficient-statistics coverage flag drifted");
    }
  }

  [[nodiscard]] std::string canonical_payload(
      const std::string& runtime_segment_mapping_sha256,
      const std::string& raw_bag_mapping_sha256,
      const std::string&
          raw_bag_original_entry_mapping_sha256) const {
    validate();
    g4irsf14_clone_detail::require_sha256(
        "runtime_segment_mapping_sha256",
        runtime_segment_mapping_sha256);
    g4irsf14_clone_detail::require_sha256(
        "raw_bag_mapping_sha256",
        raw_bag_mapping_sha256);
    g4irsf14_clone_detail::require_sha256(
        "raw_bag_original_entry_mapping_sha256",
        raw_bag_original_entry_mapping_sha256);
    g4irsf14_clone_detail::CanonicalFields fields;
    fields.string(
        "schema",
        "czr005.g4irsf15.raw_bag_sufficient_statistics.v1");
    fields.integer("row_count",
                   static_cast<int>(rows.size()));
    fields.integer("expected_raw_bag_count",
                   static_cast<int>(rows.size()));
    fields.integer("selected_segment_count",
                   selected_segment_count);
    fields.boolean("complete_coverage", complete_coverage);
    fields.string("task_id_order",
                  "STRICT_ASCENDING_NUMERIC");
    fields.string("runtime_segment_mapping_sha256",
                  runtime_segment_mapping_sha256);
    fields.string("raw_bag_mapping_sha256",
                  raw_bag_mapping_sha256);
    fields.string(
        "raw_bag_original_entry_mapping_sha256",
        raw_bag_original_entry_mapping_sha256);
    for (const auto& row : rows) {
      fields.string("row_sha256", row.row_sha256());
    }
    return fields.payload();
  }

  [[nodiscard]] std::string content_sha256(
      const std::string& runtime_segment_mapping_sha256,
      const std::string& raw_bag_mapping_sha256,
      const std::string&
          raw_bag_original_entry_mapping_sha256) const {
    return canonical_map2_detail::sha256_hex(
        canonical_payload(
            runtime_segment_mapping_sha256,
            raw_bag_mapping_sha256,
            raw_bag_original_entry_mapping_sha256));
  }
};

inline G4IRSF15RawBagSufficientStatistics
g4irsf15_build_raw_bag_sufficient_statistics(
    const std::vector<G4IRSF15CausalBagOutcome>& outcomes,
    const std::vector<EventRuntimeBagRequest>& requests,
    const std::vector<double>& original_entry_times) {
  if (outcomes.size() != requests.size() ||
      original_entry_times.size() != requests.size()) {
    throw std::invalid_argument(
        "raw-bag sufficient statistics require a full aligned cohort");
  }
  std::map<int, std::vector<std::size_t>> mapping;
  std::map<int, std::uint64_t> original_entry_bits;
  for (std::size_t index = 0; index < requests.size(); ++index) {
    const auto& request = requests[index];
    const auto& outcome = outcomes[index];
    const double original_entry = original_entry_times[index];
    if (request.task_id < 0 ||
        outcome.runtime_bag_id != static_cast<int>(index) ||
        outcome.task_id != request.task_id ||
        outcome.segment_id != request.segment_id ||
        !std::isfinite(original_entry) ||
        original_entry < 0.0 ||
        original_entry > request.release_time + 1.0e-9) {
      throw std::invalid_argument(
          "raw-bag sufficient-statistics cohort alignment drifted");
    }
    std::uint64_t bits = 0;
    static_assert(sizeof(bits) == sizeof(original_entry));
    std::memcpy(&bits, &original_entry, sizeof(bits));
    const auto [found, inserted] =
        original_entry_bits.emplace(request.task_id, bits);
    if (!inserted && found->second != bits) {
      throw std::invalid_argument(
          "one raw task has inconsistent original-entry times");
    }
    mapping[request.task_id].push_back(index);
  }

  G4IRSF15RawBagSufficientStatistics result;
  result.selected_segment_count =
      static_cast<int>(requests.size());
  result.rows.reserve(mapping.size());
  for (const auto& [task_id, runtime_ids] : mapping) {
    G4IRSF15RawBagSufficientStatisticsRow row;
    row.task_id = task_id;
    row.complete = true;
    for (const auto runtime_id : runtime_ids) {
      const auto& outcome = outcomes[runtime_id];
      const auto& request = requests[runtime_id];
      row.runtime_bag_ids.push_back(
          static_cast<int>(runtime_id));
      row.complete =
          row.complete && outcome.known && outcome.completed &&
          !outcome.failed && outcome.finish_time >= 0.0 &&
          outcome.admitted_time >= request.release_time - 1.0e-9;
      row.failed = row.failed || outcome.failed;
      if (!outcome.completed) {
        continue;
      }
      ++row.completed_segment_count;
      row.deadline_miss =
          row.deadline_miss ||
          (request.deadline >= 0.0 &&
           outcome.finish_time > request.deadline);
      row.original_entry_total_seconds +=
          outcome.finish_time -
          original_entry_times[runtime_id];
      row.java_release_total_seconds +=
          outcome.finish_time - request.release_time;
      row.scheduled_pre_release_wait_total_seconds +=
          request.release_time -
          original_entry_times[runtime_id];
      row.source_wait_total_seconds +=
          outcome.source_wait_seconds;
      row.network_time_total_seconds +=
          outcome.finish_time - outcome.admitted_time;
    }
    row.total_system_time_total_seconds =
        row.scheduled_pre_release_wait_total_seconds +
        row.source_wait_total_seconds +
        row.network_time_total_seconds;
    row.validate();
    result.rows.push_back(std::move(row));
  }
  result.complete_coverage = true;
  result.validate();
  return result;
}

struct EventRuntimeFaultWindow {
  int start = -1;
  int end = -1;
  double fault_time = 0.0;
  double repair_time = 0.0;
  double message_delay = 0.0;
  bool drop_notification = false;
};

struct EventRuntimeRegretPriorRecord {
  int from_node = -1;
  int to_node = -1;
  int goal_node = -1;  // -1 is a goal-agnostic local edge prior
  double penalty = 0.0;
};

struct EventDrivenJunctionConfig {
  std::string queue_discipline = "aging";  // fifo, deadline, aging
  // R0 preserves the frozen G4IRSF11 negative control.  R1-R4 isolate one
  // resource-semantic change at a time without changing the event loop.
  std::string resource_semantics =
      "R0_current_undirected_full_travel_exclusive";
  // This is a sensitivity parameter unless an audited physical value is
  // supplied by the original project or airport evidence.
  double entry_headway_seconds = 1.0e-3;
  // "absolute_downstream_queue_penalty" is the legacy G4IRSF11 signal.  It
  // must not be called theoretical backpressure.  The differential modes use
  // only the current junction and one advertised/local neighbour.
  std::string pressure_mode = "absolute_downstream_queue_penalty";
  double retry_interval = 0.25;
  double minimum_service_seconds = 1.0e-3;
  double dispatch_headway_seconds = 1.0e-3;
  double pressure_weight = 2.0;
  double pressure_age_weight = 0.05;
  double pressure_distance_bias = 0.25;
  double calendar_wait_weight = 1.0;
  double history_penalty = 20.0;
  double backtrack_penalty = 40.0;
  double aging_weight = 1.0;
  double starvation_threshold = 120.0;
  int history_limit = 8;
  int max_decisions_per_bag = 512;
  int max_events = 2000000;
  double max_simulation_time = -1.0;
  int trace_limit = 20000;
  // When unset, event rows retain the historical shared trace_limit cap.
  // Set independently (including zero) to suppress or bound only event rows
  // while leaving decision/fault/credit/PIBT audit limits unchanged.
  std::optional<int> event_trace_limit;
  int trace_shard_count = 1;
  int trace_shard_index = 0;
  int local_queue_capacity = 0;  // zero means no configured queue cap
  int deadlock_retry_threshold = 8;
  int diagnostic_hops = 2;  // read-only; reservation depth remains exactly one
  // "legacy_unbound" preserves the frozen G4IRSF11 admission behavior.
  // "expiring_first_edge_credit" is opt-in and owns exactly one adjacent edge
  // credit between source admission and the first selected-edge commit.
  std::string admission_mode = "legacy_unbound";
  double credit_validity_seconds = 1.0;
  double credit_snapshot_max_age_seconds = 1.0;
  int credit_capacity_per_edge = 1;
  int credit_lifecycle_limit = 512;
  int selective_credit_contention_threshold = 1;
  bool enable_source_admission = true;
  bool enable_backpressure = true;
  // P0 preserves the frozen event-runtime dispatch path exactly. P1-P4 opt
  // into bounded, multi-bag local priority inheritance with matching depth.
  // The legacy enable_pibt_lite flag below remains only the same-bag
  // alternative-edge scan and is never counted as bounded local PIBT.
  std::string pibt_mode = "P0";
  int pibt_max_ready_bags = 8;
  int pibt_max_local_resources = 32;
  int pibt_max_candidates_per_bag = 8;
  // Q0/current are exact compatibility defaults.  Q1-Q3 translate the
  // thesis task ordering into unique local queue/PIBT keys without reading a
  // future route or a global task list.
  std::string priority_mode = "Q0";
  // Preference variants are used only by bounded-local PIBT when two
  // candidates have the same static potential.
  std::string pibt_preference_mode = "current";
  std::vector<EventRuntimeRegretPriorRecord> pibt_regret_prior_records;
  // S0 is the exact historical handwritten score. S1/S2 use the immutable
  // G4E diagnostic MLP supplied by the verified Python artifact loader. S3
  // and S4 are deterministic no-model ablations.
  std::string scorer_mode =
      "S0_current_handwritten_static_score";
  std::vector<std::vector<double>> scorer_w1;
  std::vector<double> scorer_b1;
  std::vector<double> scorer_w2;
  double scorer_b2 = 0.0;
  double scorer_risk_margin_threshold = 1.0;
  double scorer_risk_bottleneck_threshold = 5.0;
  std::string scorer_model_sha256;
  std::string framework_mode = "event_loop_one_step";
  bool enable_pibt_lite = true;
  bool enable_deadlock_escape = true;
  // Controls proactive use of locally advertised fault state.  The physical
  // edge-entry interlock is independent and cannot be disabled.
  bool enable_fault_policy = true;
  // G4IRSF14 event modes are append-only. E0 is the exact historical
  // immediate-dispatch path; E1/E2/E3 defer only the named local arbitration
  // boundary to an exact-timestamp, generation-stamped event.
  std::string event_semantics = "E0_immediate_dispatch_f2";
  bool enable_opportunity_telemetry = false;
  int opportunity_trace_limit = 200000;
  // E4 owns a bounded request queue at each real destination merge. Request
  // expiry reuses the existing retry interval; no new physical headway or
  // future service-window parameter is introduced.
  // M7 is diagnostic-only and M8/M9 are fail-closed until a validated model
  // artifact is explicitly wired into this runtime.
  std::string merge_grant_rule = "M1";
  // G18 timing is append-only. "eager" preserves the exact G17/E4 request-
  // arrival arbitration path. JIT modes retain a bounded local pending set
  // and arbitrate only when the destination exposes a natural service slot.
  std::string merge_grant_timing_mode = "eager";
  int merge_grant_max_pending_requests = 64;
  int merge_grant_lifecycle_limit = 1024;
  // G4IRSF16 is append-only and exact-off by default.  Shadow evaluates the
  // same native local model but never changes an action.  Closed loop may
  // replace one frozen-F2 edge (I3) or consume one natural service
  // opportunity (I4); both artifacts must be explicitly authorized.
  std::string g4irsf16_supervisor_mode = "off";  // off, shadow, closed_loop
  G4IRSF16SelectiveLinearModelConfig g4irsf16_i3_model;
  G4IRSF16SelectiveLinearModelConfig g4irsf16_i4_model;
  G4IRSF16I4DiagnosticRuleConfig g4irsf16_i4_diagnostic_rule;
  // Append-only G17 diagnostics.  Disabled is the exact G16 payload/runtime
  // path; enabling records only real source-admission holds and bounded
  // one-hop causal state.
  bool enable_g4irsf17_source_wait_telemetry = false;
  int g4irsf17_source_wait_trace_limit = 200000;
  // Independent source-front control. Off is the exact compatibility path;
  // shadow/closed_loop inspect only a fixed K=2/4 local candidate set.
  G4IRSF17SourcePolicyConfig g4irsf17_source_policy;
  int g4irsf17_source_policy_trace_limit = 200000;
  // G18 learned merge control is restricted to E4/J2's already legal local
  // candidate set.  The artifact can propose an ordering, while these
  // independent runtime grants decide whether it may own an action.
  G4IRSF18MergeLinearPolicyConfig g4irsf18_merge_policy;
  // Internal causal-data sidecar capture.  The production default is exact
  // off; G15's frozen census enables it without changing any runtime action.
  bool enable_g4irsf17_causal_source_features = false;
#ifdef CZR005_EVENT_RUNTIME_TESTING
  // Native-only fault injection used to verify transaction rollback after
  // multiple action rows have been staged. It is absent from production
  // builds and bindings.
  int test_pibt_logical_failure_after_staged_actions = -1;
  bool test_pibt_logical_failure_after_followup_scheduling = false;
  bool test_verify_pibt_rollback_logical_state = false;
  bool test_merge_grant_fail_after_calendar_prepare = false;
  bool test_merge_grant_flip_advertised_generation_before_commit = false;
  bool test_merge_grant_flip_physical_generation_before_commit = false;
  bool test_merge_grant_flip_calendar_generation_before_commit = false;
  bool test_merge_grant_flip_queue_generation_before_commit = false;
  bool test_merge_grant_drop_capability_before_edge_exit = false;
  bool test_merge_grant_flip_physical_generation_before_edge_exit = false;
  bool test_merge_grant_flip_advertised_generation_before_edge_exit = false;
  bool test_merge_grant_remove_calendar_before_edge_exit = false;
  bool test_merge_grant_expire_before_edge_exit = false;
  bool test_merge_grant_wrong_owner_before_edge_exit = false;
  bool test_merge_grant_wrong_edge_before_edge_exit = false;
  bool test_merge_grant_wrong_destination_before_edge_exit = false;
  bool test_merge_grant_tamper_claimed_request_generation_before_edge_exit =
      false;
  bool test_merge_grant_tamper_claimed_queue_generation_before_edge_exit =
      false;
  bool test_merge_grant_tamper_claimed_calendar_generation_before_edge_exit =
      false;
  bool test_merge_grant_advance_live_queue_generation_before_edge_exit =
      false;
  bool test_merge_grant_advance_live_calendar_generation_before_edge_exit =
      false;
  bool test_pibt_fail_after_commit_before_publication = false;
#endif
};

struct EventCandidateRecord {
  int next_node = -1;
  double static_potential = 0.0;
  double travel_time = 0.0;
  int target_queue_length = 0;
  int target_scheduled_incoming = 0;
  double corridor_next_available = 0.0;
  double target_next_available = 0.0;
  bool advertised_fault = false;
  double fault_message_age_seconds = 0.0;
  int recent_visit_count = 0;
  int two_hop_queue_pressure = 0;
  int current_goal_queue_length = 0;
  int target_goal_queue_length = 0;
  int target_goal_scheduled_incoming = 0;
  double current_goal_max_wait = 0.0;
  double goal_conditioned_differential = 0.0;
  double estimated_service_rate = 0.0;
  double service_weighted_pressure = 0.0;
  bool first_edge_credit_required = false;
  bool first_edge_credit_matches = false;
  bool first_edge_credit_valid = false;
  double first_edge_credit_slack_seconds = 0.0;
  double model_score = 0.0;
  double pre_fault_policy_score = 0.0;
  double scorer_raw_score = 0.0;
  double scorer_raw_bottleneck = 0.0;
  bool scorer_raw_score_available = false;
  bool shield_allowed = false;
  std::string shield_reason;
};

struct EventDecisionTraceRow {
  std::uint64_t decision_id = 0;
  std::uint64_t arrive_event_seq = 0;
  double event_time = 0.0;
  int task_id = -1;
  int runtime_bag_id = -1;
  std::string segment_id;
  int current_node = -1;
  int goal_node = -1;
  std::vector<EventCandidateRecord> candidates;
  int model_prediction = -1;
  double model_margin = 0.0;
  bool risk_gate_triggered = false;
  bool scorer_risk_abstain = false;
  std::vector<std::string> scorer_risk_reasons;
  std::string scorer_id;
  std::string scorer_effective_id;
  int scorer_raw_prediction = -1;
  double scorer_raw_margin = 0.0;
  int fallback_selected_next = -1;
  int selected_next = -1;
  std::string decision_source;
  std::string rule_reason;
  int junction_queue_length = 0;
  double junction_next_dispatch_time = 0.0;
  int advertised_faulted_outgoing_count = 0;
  double max_fault_message_age_seconds = 0.0;
  std::vector<int> short_history;
  bool full_astar_used = false;
  std::string priority_mode;
  std::string task_class;
  double priority_slack_seconds = 0.0;
  double priority_age_seconds = 0.0;
  int priority_local_contention = 0;
  std::uint64_t priority_fault_generation = 0;
  std::uint64_t priority_enqueue_sequence = 0;
  std::string pibt_preference_mode;
  // Emitted by the Python binding only when G4IRSF16 is not off.
  bool g4irsf16_evaluated = false;
  std::string g4irsf16_mode;
  int g4irsf16_baseline_next = -1;
  int g4irsf16_proposed_next = -1;
  bool g4irsf16_proposed_hold = false;
  bool g4irsf16_action_changed = false;
  std::string g4irsf16_state;
  std::string g4irsf16_action;
  std::string g4irsf16_source;
  std::string g4irsf16_reason;
  std::uint64_t g4irsf16_node_generation = 0;
  std::uint64_t g4irsf16_state_generation = 0;
  int g4irsf16_i3_candidate = -1;
  bool g4irsf16_i3_activation = false;
  double g4irsf16_i3_benefit_lcb = 0.0;
  double g4irsf16_i3_harmful_ucb = 1.0;
  double g4irsf16_i3_utility_lcb_seconds =
      -std::numeric_limits<double>::infinity();
  bool g4irsf16_i3_ood = true;
  std::string g4irsf16_i3_model_reason;
  bool g4irsf16_i4_activation = false;
  bool g4irsf16_i4_diagnostic_only = false;
  std::string g4irsf16_i4_policy_id;
  double g4irsf16_i4_benefit_lcb = 0.0;
  double g4irsf16_i4_harmful_ucb = 1.0;
  double g4irsf16_i4_utility_lcb_seconds =
      -std::numeric_limits<double>::infinity();
  bool g4irsf16_i4_ood = true;
  std::string g4irsf16_i4_model_reason;
};

struct EventRuntimeTraceRow {
  std::uint64_t seq = 0;
  std::string event;
  double time = 0.0;
  int task_id = -1;
  int runtime_bag_id = -1;
  std::string segment_id;
  int node = -1;
  int from_node = -1;
  int to_node = -1;
  std::string reason;
  int selected_edge_count = 0;
};

struct EventRuntimeBagResult {
  std::string segment_id;
  int task_id = -1;
  int runtime_bag_id = -1;
  int start = -1;
  int goal = -1;
  int final_node = -1;
  double release_time = 0.0;
  double arrival_time = 0.0;
  double deadline = -1.0;
  std::string source;
  double admitted_time = -1.0;
  double finish_time = -1.0;
  double source_queue_delay = 0.0;
  double total_local_wait = 0.0;
  double junction_queue_wait_seconds = 0.0;
  double merge_grant_wait_seconds = 0.0;
  double edge_travel_time_seconds = 0.0;
  double node_service_time_seconds = 0.0;
  // Diagnostic subset of edge_travel_time_seconds: travel on a committed
  // edge whose destination was already present in the bounded recent history.
  double loop_extra_time_seconds = 0.0;
  // Elapsed release-to-goal duration. It remains zero for an incomplete bag;
  // completion/failure state is carried separately below.
  double goal_completion_time_seconds = 0.0;
  int decision_count = 0;
  int retry_count = 0;
  int loop_count = 0;
  bool completed = false;
  bool starved = false;
  std::string failure_reason;
  std::vector<int> short_history;
};

struct EventRuntimeSummary {
  std::string resource_semantics_id;
  std::string resource_semantics_echo;
  std::string pressure_mode;
  std::string pressure_mode_echo;
  std::string admission_mode;
  std::string admission_mode_echo;
  std::string framework_mode;
  std::string framework_mode_echo;
  std::string pibt_mode;
  std::string pibt_mode_echo;
  std::string priority_mode;
  std::string priority_mode_echo;
  std::string pibt_preference_mode;
  std::string pibt_preference_mode_echo;
  std::string credit_mode;
  std::string priority_claim_boundary;
  std::string scorer_mode;
  std::string scorer_mode_echo;
  std::string scorer_id;
  std::string scorer_model_sha256;
  std::string scorer_score_direction;
  std::string scorer_claim_boundary;
  bool scorer_out_of_distribution_diagnostic = false;
  bool scorer_promotion_eligible = false;
  bool scorer_absolute_node_ids_enabled = false;
  bool scorer_static_precompute_only = false;
  int scorer_feature_dim = 0;
  int scorer_explicit_default_feature_count = 0;
  std::uint64_t scorer_decision_evaluation_count = 0;
  std::uint64_t scorer_candidate_evaluation_count = 0;
  std::uint64_t scorer_risk_abstain_count = 0;
  int scorer_teacher_input_count = 0;
  int scorer_future_route_input_count = 0;
  int scorer_future_schedule_input_count = 0;
  int scorer_posthoc_input_count = 0;
  int scorer_runtime_global_scan_count = 0;
  int pibt_max_depth = 0;
  bool pibt_mode_diagnostic_only = false;
  bool framework_diagnostic_only = false;
  std::string bounded_local_pibt_claim_boundary;
  std::string first_edge_credit_claim_boundary;
  double entry_headway_seconds = 0.0;
  double pressure_weight = 0.0;
  double pressure_age_weight = 0.0;
  double pressure_distance_bias = 0.0;
  double credit_validity_seconds = 0.0;
  double credit_snapshot_max_age_seconds = 0.0;
  int credit_capacity_per_edge = 0;
  int credit_lifecycle_limit = 0;
  int selective_credit_contention_threshold = 0;
  int pibt_regret_prior_record_count = 0;
  int declared_max_events = 0;
  double declared_max_simulation_time = 0.0;
  int local_queue_capacity = 0;
  int pibt_max_ready_bags = 0;
  int pibt_max_local_resources = 0;
  int pibt_max_candidates_per_bag = 0;
  int requested_count = 0;
  int completed_count = 0;
  int failed_count = 0;
  int peak_active_bag_count = 0;
  int final_active_bag_count = 0;
  int decision_count = 0;
  int event_count = 0;
  int bag_release_event_count = 0;
  int arrive_junction_event_count = 0;
  int junction_service_complete_event_count = 0;
  int edge_enter_event_count = 0;
  int edge_exit_event_count = 0;
  int fault_event_count = 0;
  int repair_event_count = 0;
  int local_queue_update_event_count = 0;
  int congestion_beacon_update_event_count = 0;
  std::uint64_t source_admission_attempt_count = 0;
  std::uint64_t source_admission_admitted_count = 0;
  std::uint64_t source_admission_local_resource_hold_count = 0;
  std::uint64_t source_admission_downstream_pressure_hold_count = 0;
  std::uint64_t source_admission_beacon_read_count = 0;
  int source_admission_max_observed_downstream_pressure = 0;
  std::uint64_t first_edge_credit_issue_attempt_count = 0;
  std::uint64_t first_edge_credit_issued_count = 0;
  std::uint64_t first_edge_credit_validation_attempt_count = 0;
  std::uint64_t first_edge_credit_validation_success_count = 0;
  std::uint64_t first_edge_credit_bind_attempt_count = 0;
  std::uint64_t first_edge_credit_bound_count = 0;
  std::uint64_t first_edge_credit_consume_attempt_count = 0;
  std::uint64_t first_edge_credit_consumed_count = 0;
  std::uint64_t first_edge_credit_expired_count = 0;
  std::uint64_t first_edge_credit_fault_revocation_count = 0;
  std::uint64_t first_edge_credit_generation_revocation_count = 0;
  std::uint64_t first_edge_credit_invalid_revocation_count = 0;
  std::uint64_t first_edge_credit_duplicate_rejection_count = 0;
  std::uint64_t first_edge_credit_capacity_rejection_count = 0;
  std::uint64_t first_edge_credit_stale_snapshot_rejection_count = 0;
  std::uint64_t first_edge_credit_physical_fault_rejection_count = 0;
  std::uint64_t first_edge_credit_too_early_rejection_count = 0;
  std::uint64_t first_edge_credit_unknown_rejection_count = 0;
  std::uint64_t first_edge_credit_invalid_request_rejection_count = 0;
  std::uint64_t first_edge_credit_lifecycle_dropped_count = 0;
  std::uint64_t first_edge_credit_local_hold_count = 0;
  std::uint64_t first_edge_credit_reissue_count = 0;
  std::uint64_t selective_credit_trigger_count = 0;
  std::uint64_t selective_credit_low_load_bypass_count = 0;
  std::uint64_t selective_credit_merge_trigger_count = 0;
  std::uint64_t selective_credit_contention_trigger_count = 0;
  int first_edge_credit_active_count = 0;
  int first_edge_credit_peak_active_count = 0;
  int first_edge_credit_stored_active_count = 0;
  int first_edge_credit_stored_lifecycle_count = 0;
  int first_edge_credit_lifecycle_limit = 0;
  int first_edge_credit_future_route_count = 0;
  int first_edge_credit_global_scan_count = 0;
  bool first_edge_credit_physical_interlock_bypass = false;
  int fault_notification_drop_count = 0;
  // Bags already inside an edge when a fault activates are grandfathered:
  // they are audited, but are not an unsafe-entry violation.
  int physical_fault_window_traversal_count = 0;
  // A true safety violation is a new EDGE_ENTER while the directed edge's
  // physical fault state is active.  The physical shield should keep this 0.
  int physical_fault_edge_entry_violation_count = 0;
  int fault_affected_bag_count = 0;
  int fault_target_edge_candidate_exposure_count = 0;
  int fault_target_edge_attempt_count = 0;
  int physical_fault_interlock_rejection_count = 0;
  int physical_fault_interlock_hold_count = 0;
  int physical_fault_interlock_reroute_count = 0;
  int local_fault_policy_action_count = 0;
  int local_fault_policy_hold_count = 0;
  int local_fault_policy_reroute_count = 0;
  int fault_affected_completed_count = 0;
  double fault_recovery_seconds = 0.0;
  double repair_backlog_slope = 0.0;
  bool fault_recovery_seconds_available = false;
  bool repair_backlog_slope_available = false;
  std::string fault_recovery_metric_semantics;
  std::string repair_backlog_slope_semantics;
  int reservation_conflicts = 0;
  int shield_rejection_count = 0;
  int stale_fault_shield_rejection_count = 0;
  int pibt_lite_handoff_count = 0;
  int same_bag_alternative_edge_scan_handoff_count = 0;
  std::uint64_t bounded_local_pibt_activation_count = 0;
  std::uint64_t bounded_local_pibt_attempt_count = 0;
  std::uint64_t bounded_local_pibt_prepare_count = 0;
  std::uint64_t bounded_local_pibt_validate_count = 0;
  std::uint64_t bounded_local_pibt_commit_count = 0;
  std::uint64_t bounded_local_pibt_wait_for_cycle_count = 0;
  std::uint64_t bounded_local_pibt_handoff_count = 0;
  std::uint64_t bounded_local_pibt_candidate_bound_rejection_count = 0;
  std::uint64_t bounded_local_pibt_candidate_materialization_count = 0;
  std::uint64_t bounded_local_pibt_not_applicable_count = 0;
  std::uint64_t bounded_local_pibt_same_bag_fallback_count = 0;
  std::uint64_t bounded_local_pibt_proposal_batch_count = 0;
  std::uint64_t bounded_local_pibt_proposed_action_count = 0;
  std::uint64_t bounded_local_pibt_committed_batch_count = 0;
  std::uint64_t bounded_local_pibt_committed_action_count = 0;
  std::uint64_t bounded_local_pibt_inherited_action_count = 0;
  std::uint64_t bounded_local_pibt_blocker_move_attempt_count = 0;
  std::uint64_t bounded_local_pibt_backtrack_count = 0;
  std::uint64_t bounded_local_pibt_cycle_guard_count = 0;
  std::uint64_t bounded_local_pibt_rollback_count = 0;
  std::uint64_t bounded_local_pibt_fault_rejection_count = 0;
  std::uint64_t bounded_local_pibt_prepare_rejection_count = 0;
  std::uint64_t bounded_local_pibt_commit_rejection_count = 0;
  std::uint64_t
      bounded_local_pibt_post_commit_failure_injection_count = 0;
  std::uint64_t
      bounded_local_pibt_rollback_fingerprint_match_count = 0;
  std::uint64_t
      bounded_local_pibt_rollback_calendar_generation_match_count = 0;
  int bounded_local_pibt_max_inheritance_depth = 0;
  int bounded_local_pibt_max_slice_bags = 0;
  int bounded_local_pibt_max_slice_resources = 0;
  int bounded_local_pibt_max_candidates_per_bag = 0;
  int bounded_local_pibt_max_transaction_credit_entries = 0;
  int bounded_local_pibt_max_transaction_bag_entries = 0;
  int bounded_local_pibt_max_transaction_junction_scalar_entries = 0;
  int bounded_local_pibt_max_transaction_action_deltas = 0;
  int bounded_local_pibt_max_transaction_calendar_generation_entries = 0;
  bool bounded_local_pibt_classical_completeness_claimed = false;
  int deadlock_count = 0;
  int resolved_deadlock_count = 0;
  int unresolved_deadlock_count = 0;
  int deadlock_escape_activation_count = 0;
  int starvation_count = 0;
  int loop_count = 0;
  int runtime_full_astar_calls = 0;
  int global_reservation_scan_count = 0;
  int max_edges_selected_per_arrive = 0;
  int max_edges_selected_per_bag_per_decision = 0;
  int max_actions_committed_per_pibt_batch = 0;
  int release_selected_edge_count = 0;
  int max_history_observed = 0;
  int max_junction_queue_length = 0;
  int max_source_queue_length = 0;
  int max_local_calendar_intervals = 0;
  int max_corridor_calendar_intervals = 0;
  int max_same_directed_edge_inflight = 0;
  int max_candidate_count = 0;
  int two_step_reservation_count = 0;
  int diagnostic_hops = 0;
  int decision_trace_seen_count = 0;
  int decision_trace_shard_seen_count = 0;
  int decision_trace_stored_count = 0;
  int hold_trace_stored_count = 0;
  int trace_limit = 0;
  int event_trace_limit = 0;
  bool event_trace_limit_inherited = true;
  int trace_shard_count = 1;
  int trace_shard_index = 0;
  std::size_t cpp_internal_accounted_bytes = 0;
  double max_individual_wait = 0.0;
  double max_source_queue_delay = 0.0;
  double fairness_jain = 1.0;
  double max_deadlock_duration = 0.0;
  double end_time = 0.0;
  double runtime_seconds = 0.0;
  double decision_latency_us_p50 = 0.0;
  double decision_latency_us_p95 = 0.0;
  double decision_latency_us_p99 = 0.0;
  double event_throughput_per_second = 0.0;
  bool event_limit_reached = false;
  bool time_limit_reached = false;
  bool sensor_loss_mode_used = false;
  bool source_admission_enabled = true;
  bool fault_policy_enabled = true;
  bool legacy_pibt_lite_enabled = true;
  bool decision_trace_truncated = false;
  bool event_trace_truncated = false;
  std::uint64_t repaired_task_reentry_count = 0;
  std::uint64_t repaired_task_reentry_boost_cleared_count = 0;
  int priority_teacher_input_count = 0;
  int priority_future_route_input_count = 0;
  int priority_global_scan_count = 0;
  std::uint64_t pibt_preference_candidate_count = 0;
  std::uint64_t pibt_preference_unique_exit_penalty_count = 0;
  std::uint64_t pibt_preference_wait_cycle_penalty_count = 0;
  std::uint64_t pibt_preference_backtrack_penalty_count = 0;
  std::uint64_t pibt_preference_regret_prior_hit_count = 0;
  // G4IRSF14 append-only event-semantics diagnostics. The Python binding
  // omits these keys for the exact E0/telemetry-off compatibility path.
  std::string event_semantics;
  std::string event_semantics_echo;
  bool opportunity_telemetry_enabled = false;
  std::uint64_t source_arbitration_event_count = 0;
  std::uint64_t junction_arbitration_event_count = 0;
  std::uint64_t stale_arbitration_event_count = 0;
  std::uint64_t superseded_arbitration_event_rejected_count = 0;
  std::uint64_t duplicate_same_time_arbitration_prevented_count = 0;
  std::uint64_t source_same_timestamp_batch_count = 0;
  std::uint64_t junction_same_timestamp_batch_count = 0;
  int max_source_arbitration_batch_size = 0;
  int max_junction_arbitration_batch_size = 0;
  std::uint64_t opportunity_event_queue_inspection_count = 0;
  std::uint64_t source_opportunity_total_count = 0;
  std::uint64_t source_opportunity_stored_count = 0;
  std::uint64_t source_opportunity_dropped_count = 0;
  std::uint64_t junction_opportunity_total_count = 0;
  std::uint64_t junction_opportunity_stored_count = 0;
  std::uint64_t junction_opportunity_dropped_count = 0;
  std::uint64_t merge_visibility_total_count = 0;
  std::uint64_t merge_visibility_stored_count = 0;
  std::uint64_t merge_visibility_dropped_count = 0;
  std::uint64_t event_seq_audit_total_count = 0;
  std::uint64_t event_seq_audit_stored_count = 0;
  std::uint64_t event_seq_audit_dropped_count = 0;
  std::uint64_t arbitration_batch_total_count = 0;
  std::uint64_t arbitration_batch_stored_count = 0;
  std::uint64_t arbitration_batch_dropped_count = 0;
  std::uint64_t fault_generation_commit_recheck_count = 0;
  int microphase_runtime_global_scan_count = 0;
  double artificial_batch_delay_seconds = 0.0;
  std::uint64_t destination_merge_arbitration_event_count = 0;
  std::uint64_t
      g4irsf14_i2_live_eligible_multi_request_boundary_count = 0;
  std::uint64_t
      g4irsf14_i5_prefilter_candidate_count = 0;
  std::uint64_t
      g4irsf14_i5_applicable_ready_slice_boundary_count = 0;
  std::uint64_t merge_grant_request_count = 0;
  std::uint64_t merge_grant_issued_count = 0;
  std::uint64_t merge_grant_prepared_count = 0;
  std::uint64_t merge_grant_committed_count = 0;
  std::uint64_t
      merge_grant_issued_transition_count = 0;
  std::uint64_t
      merge_grant_prepared_transition_count = 0;
  std::uint64_t
      merge_grant_committed_transition_count = 0;
  std::uint64_t merge_grant_consumed_count = 0;
  // Strict subset of consumed grants: the exact lease was retained for a
  // physically in-flight bag after a post-entry fault generation change.
  std::uint64_t
      merge_grant_inflight_fault_generation_recovery_count = 0;
  std::uint64_t merge_grant_expired_count = 0;
  std::uint64_t merge_grant_request_expired_count = 0;
  std::uint64_t merge_grant_grant_expired_count = 0;
  std::uint64_t merge_grant_revoked_count = 0;
  std::uint64_t merge_grant_revoked_fault_count = 0;
  std::uint64_t merge_grant_revoked_stale_state_count = 0;
  std::uint64_t
      merge_grant_revoked_replan_current_edge_count = 0;
  std::uint64_t merge_grant_rolled_back_count = 0;
  std::uint64_t
      merge_grant_post_commit_revoked_count = 0;
  std::uint64_t
      merge_grant_post_commit_expired_count = 0;
  std::uint64_t
      merge_grant_post_commit_rollback_count = 0;
  std::uint64_t merge_grant_exact_slot_busy_count = 0;
  std::uint64_t
      merge_grant_active_grant_rejection_count = 0;
  std::uint64_t merge_grant_queue_capacity_block_count = 0;
  std::uint64_t merge_grant_contended_loser_retry_count = 0;
  std::uint64_t merge_grant_lifecycle_transition_count = 0;
  std::uint64_t merge_grant_lifecycle_stored_count = 0;
  std::uint64_t merge_grant_lifecycle_dropped_count = 0;
  std::uint64_t merge_grant_terminal_request_count = 0;
  std::uint64_t merge_grant_outstanding_request_count = 0;
  std::uint64_t merge_grant_goal_exempt_bypass_count = 0;
  std::uint64_t merge_grant_stale_arbitration_count = 0;
  std::uint64_t merge_grant_duplicate_wakeup_prevented_count = 0;
  std::string merge_grant_timing_mode;
  std::uint64_t merge_grant_service_opportunity_count = 0;
  std::uint64_t merge_grant_multi_candidate_opportunity_count = 0;
  std::uint64_t merge_grant_true_competition_count = 0;
  std::uint64_t merge_grant_order_mutation_count = 0;
  std::uint64_t merge_grant_candidate_total_count = 0;
  std::uint64_t merge_grant_wakeup_scheduled_count = 0;
  std::uint64_t merge_grant_wakeup_coalesced_count = 0;
  std::uint64_t merge_grant_stale_wakeup_count = 0;
  std::uint64_t merge_grant_opportunity_trace_total_count = 0;
  std::uint64_t merge_grant_opportunity_trace_stored_count = 0;
  std::uint64_t merge_grant_opportunity_trace_dropped_count = 0;
  int merge_grant_peak_pending_requests = 0;
  int merge_grant_peak_active_unconsumed = 0;
  int merge_grant_final_active_unconsumed = 0;
  bool merge_grant_conservation_holds = true;
  bool merge_grant_active_bijection_holds = true;
  bool merge_grant_runtime_owned_capability = false;
  bool merge_grant_exact_slot_no_future_shift = false;
  // G4IRSF16 append-only deployment/audit counters.  Bindings omit them in
  // exact-off mode so historical payloads stay byte-for-byte compatible.
  std::string g4irsf16_supervisor_mode;
  std::string g4irsf16_i3_model_sha256;
  std::string g4irsf16_i4_model_sha256;
  std::string g4irsf16_policy_kind;
  std::string g4irsf16_i4_policy_id;
  std::string g4irsf16_i4_policy_authorization;
  bool g4irsf16_diagnostic_only = false;
  bool g4irsf16_promotion_authorized = false;
  std::uint64_t g4irsf16_supervisor_evaluation_count = 0;
  std::uint64_t g4irsf16_i3_candidate_evaluation_count = 0;
  std::uint64_t g4irsf16_i4_evaluation_count = 0;
  std::uint64_t g4irsf16_i3_activation_count = 0;
  std::uint64_t g4irsf16_i4_activation_count = 0;
  std::uint64_t g4irsf16_i3_applied_count = 0;
  std::uint64_t g4irsf16_i4_applied_count = 0;
  std::uint64_t g4irsf16_shadow_proposal_count = 0;
  std::uint64_t g4irsf16_action_change_count = 0;
  std::uint64_t g4irsf16_safe_hold_count = 0;
  std::uint64_t g4irsf16_fault_recovery_count = 0;
  int g4irsf16_runtime_global_scan_count = 0;
  int g4irsf16_future_route_input_count = 0;
  int g4irsf16_future_schedule_input_count = 0;
  int g4irsf16_posthoc_input_count = 0;
  int g4irsf16_full_astar_call_count = 0;
  // G4IRSF17 fields are omitted by the Python binding while telemetry is off.
  bool g4irsf17_source_wait_telemetry_enabled = false;
  std::uint64_t g4irsf17_source_wait_interval_total_count = 0;
  std::uint64_t g4irsf17_source_wait_interval_stored_count = 0;
  std::uint64_t g4irsf17_source_wait_interval_dropped_count = 0;
  double g4irsf17_source_wait_seconds = 0.0;
  double g4irsf17_source_wait_bag_seconds = 0.0;
  std::array<std::uint64_t, kG4IRSF17SourceWaitReasonCount>
      g4irsf17_source_wait_reason_interval_counts{};
  std::array<double, kG4IRSF17SourceWaitReasonCount>
      g4irsf17_source_wait_reason_seconds{};
  std::array<double, kG4IRSF17SourceWaitReasonCount>
      g4irsf17_source_wait_reason_bag_seconds{};
  int g4irsf17_source_wait_runtime_global_scan_count = 0;
  std::string g4irsf17_source_policy_mode;
  std::string g4irsf17_source_policy_kind;
  std::string g4irsf17_source_policy_artifact_set_id;
  bool g4irsf17_source_policy_authorized = false;
  bool g4irsf17_source_policy_runtime_closed_loop_authorized = false;
  int g4irsf17_source_policy_top_k = 0;
  std::uint64_t g4irsf17_source_policy_evaluation_count = 0;
  std::uint64_t g4irsf17_source_policy_change_proposal_count = 0;
  std::uint64_t g4irsf17_source_policy_activation_count = 0;
  std::uint64_t g4irsf17_source_policy_abstention_count = 0;
  std::uint64_t g4irsf17_source_policy_ood_abstention_count = 0;
  std::uint64_t g4irsf17_source_policy_supervisor_abstention_count = 0;
  std::uint64_t g4irsf17_source_policy_trace_total_count = 0;
  std::uint64_t g4irsf17_source_policy_trace_stored_count = 0;
  std::uint64_t g4irsf17_source_policy_trace_dropped_count = 0;
  int g4irsf17_source_policy_runtime_global_scan_count = 0;
  int g4irsf17_source_policy_future_route_input_count = 0;
  int g4irsf17_source_policy_future_schedule_input_count = 0;
  int g4irsf17_source_policy_full_astar_call_count = 0;
  // G4IRSF18 fields are emitted only while the learned merge policy is on.
  std::string g4irsf18_merge_policy_mode;
  std::string g4irsf18_merge_policy_schema;
  std::string g4irsf18_merge_policy_family;
  std::string g4irsf18_merge_feature_contract;
  bool g4irsf18_merge_artifact_valid = false;
  bool g4irsf18_merge_artifact_production_closed_loop_authorized = false;
  bool g4irsf18_merge_research_closed_loop_authorized = false;
  bool g4irsf18_merge_fixed_research_workload = false;
  bool g4irsf18_merge_production_closed_loop_authorized = false;
  bool g4irsf18_merge_offline_gate_passed = false;
  double g4irsf18_merge_coverage_cap = 0.0;
  int g4irsf18_merge_max_overrides_per_segment = 0;
  bool g4irsf18_merge_kill_switch_configured = false;
  bool g4irsf18_merge_kill_switch_tripped = false;
  std::string g4irsf18_merge_kill_switch_reason;
  std::uint64_t g4irsf18_merge_model_opportunity_count = 0;
  std::uint64_t g4irsf18_merge_model_eligible_count = 0;
  std::uint64_t g4irsf18_merge_model_proposal_count = 0;
  std::uint64_t g4irsf18_merge_model_applied_count = 0;
  std::uint64_t g4irsf18_merge_distinct_action_mutation_count = 0;
  std::uint64_t g4irsf18_merge_model_ood_count = 0;
  std::uint64_t g4irsf18_merge_model_invalid_count = 0;
  std::uint64_t g4irsf18_merge_model_fallback_count = 0;
  std::uint64_t g4irsf18_merge_j2_fallback_count = 0;
  std::uint64_t g4irsf18_merge_tie_fifo_fallback_count = 0;
  std::uint64_t g4irsf18_merge_shadow_fallback_count = 0;
  std::uint64_t g4irsf18_merge_authorization_fallback_count = 0;
  std::uint64_t g4irsf18_merge_coverage_cap_fallback_count = 0;
  std::uint64_t g4irsf18_merge_override_cap_fallback_count = 0;
  std::uint64_t g4irsf18_merge_starvation_guard_fallback_count = 0;
  std::uint64_t g4irsf18_merge_kill_switch_trip_count = 0;
  std::uint64_t g4irsf18_merge_kill_switch_fallback_count = 0;
  std::uint64_t g4irsf18_merge_model_ownership_count = 0;
  std::uint64_t g4irsf18_merge_coverage_eligible_seen_count = 0;
  int g4irsf18_merge_runtime_global_scan_count = 0;
  int g4irsf18_merge_future_route_input_count = 0;
  int g4irsf18_merge_future_schedule_input_count = 0;
  int g4irsf18_merge_full_astar_call_count = 0;
};

struct EventRuntimeJunctionResult {
  int node = -1;
  int final_source_queue_length = 0;
  int peak_source_queue_length = 0;
  int final_junction_queue_length = 0;
  int peak_junction_queue_length = 0;
  int final_service_calendar_intervals = 0;
  int peak_service_calendar_intervals = 0;
  // These are conservative C++ storage lower bounds: object bytes, live deque
  // element payloads, and reserved LocalCalendar interval payload capacity.  They
  // deliberately exclude allocator, deque block, and unordered-map node overhead.
  std::size_t final_local_state_accounted_bytes = 0;
  std::size_t peak_local_state_accounted_bytes = 0;
  std::uint64_t service_reservation_count = 0;
  double cumulative_service_reserved_seconds = 0.0;
  double first_service_reservation_start_time = -1.0;
  double last_service_reservation_end_time = -1.0;
  int scheduled_incoming = 0;
  double next_dispatch_time = 0.0;
};

struct EventRuntimeFaultAuditRow {
  std::uint64_t seq = 0;
  std::string event;
  std::string phase;
  double time = 0.0;
  int from_node = -1;
  int to_node = -1;
  int physical_active_count = 0;
  int physical_generation = 0;
  int inflight_traversal_count = 0;
  bool notification_dropped = false;
  int task_id = -1;
  int runtime_bag_id = -1;
  std::string segment_id;
  int current_node = -1;
  int intended_next_node = -1;
  int selected_next_node = -1;
  bool fault_policy_enabled = true;
};

struct EventRuntimeCreditAuditRow {
  double time = 0.0;
  std::string action;
  std::string reason;
  std::uint64_t credit_id = 0;
  int from_node = -1;
  int to_node = -1;
  int goal = -1;
  double earliest = 0.0;
  double latest = 0.0;
  std::uint64_t generation = 0;
  double expiry = 0.0;
  int capacity = 0;
  int owner_or_unbound = -1;
  int fault_generation = 0;
  std::string state;
  int task_id = -1;
  std::string segment_id;
};

struct EventRuntimePIBTAuditRow {
  std::uint64_t activation_id = 0;
  double time = 0.0;
  int trigger_node = -1;
  int trigger_runtime_bag_id = -1;
  std::string mode;
  std::string outcome;
  std::string blocker;
  int local_slice_bag_count = 0;
  int local_slice_resource_count = 0;
  int local_slice_candidate_count = 0;
  int proposed_action_count = 0;
  int committed_action_count = 0;
  int inherited_action_count = 0;
  int max_inheritance_depth = 0;
  int backtrack_count = 0;
  int cycle_guard_count = 0;
  int rollback_count = 0;
  int transaction_credit_entry_count = 0;
  int transaction_bag_entry_count = 0;
  int transaction_junction_scalar_entry_count = 0;
  int transaction_action_delta_count = 0;
  std::vector<BoundedLocalPIBTAction> actions;
};

struct EventRuntimeSourceOpportunityRow {
  double event_time = 0.0;
  std::uint64_t timestamp_bits = 0;
  int source_node = -1;
  int queue_length_before_enqueue = 0;
  int queue_length_after_enqueue = 0;
  int queue_length_before_arbitration = 0;
  int queue_length_after_arbitration = 0;
  int same_timestamp_release_batch_size = 0;
  int same_time_pending_source_releases = 0;
  int same_time_pending_shared_merge_releases = 0;
  int ready_set_size = 0;
  int priority_comparison_count = 0;
  int chosen_task_id = -1;
  int chosen_runtime_bag_id = -1;
  std::string chosen_segment_id;
  std::string queue_discipline;
  std::uint64_t event_seq = 0;
  std::uint64_t arbitration_generation = 0;
  bool batched_arbitration = false;
};

// A row closes one actual interval between two source-admission evaluations
// (or between the final evaluation and runtime stop).  affected_bag_count is
// constant over the interval because every source enqueue/dequeue itself
// triggers another evaluation; wait_bag_seconds is therefore additive.
struct EventRuntimeSourceWaitBlockerRow {
  std::uint64_t interval_ordinal = 0;
  std::string reason;
  int reason_precedence = 0;
  int source_node = -1;
  int blocker_node = -1;
  std::string blocker_resource;
  int blocker_resource_from_node = -1;
  int blocker_resource_to_node = -1;
  std::uint64_t source_generation = 0;
  std::uint64_t blocker_generation = 0;
  double wait_start_time = 0.0;
  double wait_end_time = 0.0;
  double wait_seconds = 0.0;
  int affected_bag_count = 0;
  double wait_bag_seconds = 0.0;
  // Identity is trace-only and is never consumed by admission/scoring.
  int selected_task_id = -1;
  int selected_runtime_bag_id = -1;
  std::string selected_segment_id;
};

struct EventRuntimeG4IRSF17SourcePolicyRow {
  std::uint64_t decision_ordinal = 0;
  double event_time = 0.0;
  int source_node = -1;
  std::string mode;
  std::string kind;
  std::string artifact_set_id;
  int top_k = 0;
  int source_queue_length = 0;
  std::uint64_t source_generation = 0;
  std::vector<int> candidate_queue_indices;
  // Identity is trace-only and is never part of the numeric observation.
  std::vector<int> candidate_task_ids;
  std::vector<int> candidate_runtime_bag_ids;
  std::vector<std::string> candidate_segment_ids;
  std::vector<std::array<double,
                         kG4IRSF17SourceCandidateFeatureCount>>
      candidate_features;
  std::array<double, kG4IRSF17SourceContextFeatureCount>
      context_features{};
  std::array<double, kG4IRSF17SourcePairwiseFeatureCount>
      pairwise_features{};
  int baseline_candidate_index = 0;
  int treatment_candidate_index = 0;
  int proposed_candidate_index = 0;
  int chosen_candidate_index = 0;
  int baseline_queue_index = 0;
  int treatment_queue_index = 0;
  int proposed_queue_index = 0;
  int chosen_queue_index = 0;
  bool activated = false;
  bool out_of_distribution = false;
  bool supervisor_authorized = false;
  std::string reason;
  double model_score = 0.0;
  double benefit_probability_lcb = 0.0;
  double harmful_probability_ucb = 1.0;
  double utility_lcb_seconds = 0.0;
  double calibration_ece = 1.0;
};

struct EventRuntimeJunctionOpportunityRow {
  double event_time = 0.0;
  std::uint64_t timestamp_bits = 0;
  int junction_node = -1;
  int queue_length_before_enqueue = 0;
  int queue_length_after_enqueue = 0;
  int queue_length_before_arbitration = 0;
  int queue_length_after_arbitration = 0;
  int same_timestamp_arrival_batch_size = 0;
  int same_time_pending_arrivals = 0;
  int same_time_pending_shared_merge_requests = 0;
  int ready_set_size = 0;
  int priority_comparison_count = 0;
  int pibt_slice_bag_count = 0;
  int pibt_owner_count = 0;
  int chosen_task_id = -1;
  int chosen_runtime_bag_id = -1;
  std::string chosen_segment_id;
  std::uint64_t event_seq = 0;
  std::uint64_t arbitration_generation = 0;
  bool batched_arbitration = false;
};

struct EventRuntimeMergeVisibilityRow {
  double event_time = 0.0;
  std::uint64_t timestamp_bits = 0;
  int destination_node = -1;
  int upstream_node = -1;
  int incoming_edge_start = -1;
  int incoming_edge_end = -1;
  int requesting_task_id = -1;
  int requesting_runtime_bag_id = -1;
  std::string requesting_segment_id;
  double earliest_arrival = 0.0;
  double slot_start = 0.0;
  double slot_end = 0.0;
  int known_competing_request_count = 0;
  int later_same_time_competitor_count = 0;
  bool later_same_time_competitor_exists = false;
  bool seq_determined_order = false;
  std::uint64_t event_seq = 0;
};

// One bounded row per candidate at a real G18 JIT service opportunity.  IDs
// are trace identity only; every scored value is captured from the same
// destination-local one-hop pending request and contains no outcome, route
// suffix, global task scan, or future schedule.
struct EventRuntimeMergeServiceOpportunityRow {
  std::uint64_t opportunity_id = 0;
  double event_time = 0.0;
  int destination_node = -1;
  std::uint64_t controller_generation = 0;
  std::string timing_mode;
  int candidate_count = 0;
  std::uint64_t baseline_winner_request_id = 0;
  std::uint64_t chosen_winner_request_id = 0;
  std::uint64_t candidate_request_id = 0;
  int upstream_node = -1;
  double projected_arrival = 0.0;
  double deadline_slack = 0.0;
  double wait_age = 0.0;
  double destination_service_seconds = 0.0;
  int downstream_queue_pressure = 0;
  double route_score = 0.0;
  double static_remaining = 0.0;
  int task_class_code = 4;
  int task_class = 0;
  bool storage_leg = false;
  bool baseline_winner = false;
  bool chosen_winner = false;
  std::string model_policy_mode;
  std::string model_feature_contract;
  std::string model_reason;
  bool model_evaluated = false;
  bool model_score_available = false;
  double model_score = 0.0;
  bool model_proposed = false;
  bool model_applied = false;
  bool model_chosen = false;
  bool model_out_of_distribution = false;
  bool model_invalid = false;
  bool model_fallback = false;
  std::uint64_t model_baseline_request_id = 0;
  std::uint64_t model_proposed_request_id = 0;
  std::array<double, kG4IRSF18MergeFeatureCount> model_features{};
};

struct EventRuntimeEventSeqAuditRow {
  double event_time = 0.0;
  std::uint64_t timestamp_bits = 0;
  std::string boundary;
  int node = -1;
  int destination_node = -1;
  int ready_set_size = 0;
  int priority_comparison_count = 0;
  int later_same_time_competitor_count = 0;
  int chosen_runtime_bag_id = -1;
  std::uint64_t chosen_enqueue_sequence = 0;
  std::uint64_t event_seq = 0;
  bool seq_determined_order = false;
  std::string reason;
};

struct EventRuntimeArbitrationBatchRow {
  double event_time = 0.0;
  std::uint64_t timestamp_bits = 0;
  std::string boundary;
  int node = -1;
  int enqueue_count = 0;
  int ready_set_size = 0;
  int pending_same_time_event_count = 0;
  int chosen_runtime_bag_id = -1;
  std::uint64_t event_seq = 0;
  std::uint64_t arbitration_generation = 0;
};

struct EventDrivenJunctionResult {
  EventRuntimeSummary summary;
  std::vector<EventRuntimeBagResult> bags;
  std::vector<EventRuntimeTraceRow> events;
  std::vector<EventDecisionTraceRow> decisions;
  std::vector<EventDecisionTraceRow> hold_attempts;
  std::vector<EventRuntimeJunctionResult> junctions;
  std::vector<EventRuntimeFaultAuditRow> fault_events;
  std::vector<EventRuntimeCreditAuditRow> credit_events;
  std::vector<EventRuntimePIBTAuditRow> pibt_events;
  std::vector<EventRuntimeSourceOpportunityRow> source_admission_opportunities;
  std::vector<EventRuntimeSourceWaitBlockerRow>
      g4irsf17_source_wait_blockers;
  std::vector<EventRuntimeG4IRSF17SourcePolicyRow>
      g4irsf17_source_policy_decisions;
  std::vector<EventRuntimeJunctionOpportunityRow> junction_arbitration_opportunities;
  std::vector<EventRuntimeMergeVisibilityRow> merge_request_visibility;
  std::vector<EventRuntimeMergeServiceOpportunityRow>
      merge_service_opportunities;
  std::vector<EventRuntimeEventSeqAuditRow> event_seq_ordering_audit;
  std::vector<EventRuntimeArbitrationBatchRow> arbitration_batch_cardinality;
  std::vector<DestinationMergeGrantLifecycleRow> merge_grant_lifecycle;
};

enum class EventDrivenJunctionRuntimePhase {
  kIdle,
  kReady,
  kStopped,
  kFinalized,
};

struct EventDrivenJunctionSafeBoundary {
  JunctionEventType next_event_type =
      JunctionEventType::kBagRelease;
  double next_event_time = 0.0;
  std::uint64_t next_event_seq = 0;
  int runtime_bag_id = -1;
  int node = -1;
  int from_node = -1;
  int to_node = -1;
  int active_merge_capability_count = 0;
  int pending_merge_request_count = 0;
  int active_physical_fault_edge_count = 0;
  int queued_bag_count = 0;
  std::string state_sha256;
  bool queue_top_not_popped = true;
  bool staged_event_sink_empty = true;
};

namespace event_runtime_detail {

constexpr double kEpsilon = 1.0e-9;

inline std::uint64_t timestamp_bits(double value) noexcept {
  std::uint64_t bits = 0;
  static_assert(sizeof(bits) == sizeof(value));
  std::memcpy(&bits, &value, sizeof(bits));
  return bits;
}

inline bool same_timestamp(double left, double right) noexcept {
  return timestamp_bits(left) == timestamp_bits(right) ||
         std::abs(left - right) <= kEpsilon;
}

inline long long directed_key(int start, int end) {
  return (static_cast<long long>(start) << 32) ^ static_cast<unsigned int>(end);
}

inline long long corridor_key(int left, int right) {
  const int low = std::min(left, right);
  const int high = std::max(left, right);
  return directed_key(low, high);
}

struct CalendarInterval {
  int task_id = -1;
  double start = 0.0;
  double end = 0.0;
};

class LocalCalendar {
 public:
  class PreparedExactReservation {
   public:
    PreparedExactReservation(const PreparedExactReservation&) = delete;
    PreparedExactReservation& operator=(const PreparedExactReservation&) =
        delete;
    PreparedExactReservation(PreparedExactReservation&& other) noexcept
        : owner_(other.owner_),
          task_id_(other.task_id_),
          start_(other.start_),
          end_(other.end_),
          generation_(other.generation_) {
      other.owner_ = nullptr;
    }
    PreparedExactReservation& operator=(
        PreparedExactReservation&& other) noexcept {
      if (this != &other) {
        owner_ = other.owner_;
        task_id_ = other.task_id_;
        start_ = other.start_;
        end_ = other.end_;
        generation_ = other.generation_;
        other.owner_ = nullptr;
      }
      return *this;
    }

   private:
    friend class LocalCalendar;
    PreparedExactReservation(LocalCalendar* owner,
                             int task_id,
                             double start,
                             double end,
                             std::uint64_t generation) noexcept
        : owner_(owner),
          task_id_(task_id),
          start_(start),
          end_(end),
          generation_(generation) {}

    LocalCalendar* owner_ = nullptr;
    int task_id_ = -1;
    double start_ = 0.0;
    double end_ = 0.0;
    std::uint64_t generation_ = 0;
  };

  void purge(double now) {
    const auto previous_size = intervals_.size();
    intervals_.erase(
        std::remove_if(intervals_.begin(), intervals_.end(), [now](const CalendarInterval& item) {
          return item.end <= now + kEpsilon;
        }),
        intervals_.end());
    if (intervals_.size() != previous_size) {
      ++generation_;
    }
  }

  [[nodiscard]] bool available(double start,
                               double end,
                               int ignore_task = -1) const noexcept {
    if (end <= start) {
      return true;
    }
    for (const auto& item : intervals_) {
      if (ignore_task >= 0 && item.task_id == ignore_task) {
        continue;
      }
      if (start < item.end - kEpsilon && item.start < end - kEpsilon) {
        return false;
      }
    }
    return true;
  }

  [[nodiscard]] double earliest_start(double earliest, double duration) const {
    double candidate = earliest;
    for (const auto& item : intervals_) {
      if (candidate + duration <= item.start + kEpsilon) {
        break;
      }
      if (candidate < item.end - kEpsilon && item.start < candidate + duration - kEpsilon) {
        candidate = item.end;
      }
    }
    return candidate;
  }

  [[nodiscard]] double reserved_until(double now) const noexcept {
    double value = now;
    for (const auto& item : intervals_) {
      value = std::max(value, item.end);
    }
    return value;
  }

  void reserve(int task_id, double start, double end) {
    if (end <= start) {
      return;
    }
    intervals_.reserve(intervals_.size() + 1);
    append_sorted_noexcept(CalendarInterval{task_id, start, end});
    ++generation_;
  }

  [[nodiscard]] std::optional<PreparedExactReservation>
  prepare_exact_reservation(int task_id,
                            double start,
                            double end) {
    if (end <= start || !available(start, end, task_id)) {
      return std::nullopt;
    }
    // Any allocation is completed before the runtime mutates a bag, queue,
    // incoming counter, event queue, or grant lifecycle.
    intervals_.reserve(intervals_.size() + 1);
    return PreparedExactReservation(
        this, task_id, start, end, generation_);
  }

  bool commit_exact_reservation(
      PreparedExactReservation&& prepared) noexcept {
    if (prepared.owner_ != this ||
        prepared.generation_ != generation_ ||
        prepared.end_ <= prepared.start_ ||
        !available(prepared.start_,
                   prepared.end_,
                   prepared.task_id_)) {
      return false;
    }
    append_sorted_noexcept(
        CalendarInterval{prepared.task_id_,
                         prepared.start_,
                         prepared.end_});
    ++generation_;
    prepared.owner_ = nullptr;
    return true;
  }

  bool erase_exact(int task_id, double start, double end) noexcept {
    const auto found = std::find_if(
        intervals_.begin(),
        intervals_.end(),
        [&](const CalendarInterval& item) {
          return item.task_id == task_id &&
                 std::abs(item.start - start) <= kEpsilon &&
                 std::abs(item.end - end) <= kEpsilon;
        });
    if (found == intervals_.end()) {
      return false;
    }
    intervals_.erase(found);
    ++generation_;
    return true;
  }

  [[nodiscard]] bool contains_exact(
      int task_id,
      double start,
      double end) const noexcept {
    return std::any_of(
        intervals_.begin(),
        intervals_.end(),
        [&](const CalendarInterval& item) {
          return item.task_id == task_id &&
                 std::abs(item.start - start) <= kEpsilon &&
                 std::abs(item.end - end) <= kEpsilon;
        });
  }

  bool restore_exact_reservation_noexcept(
      int task_id,
      double start,
      double end,
      std::uint64_t restore_generation) noexcept {
    if (generation_ != restore_generation + 1) {
      return false;
    }
    const auto found = std::find_if(
        intervals_.begin(),
        intervals_.end(),
        [&](const CalendarInterval& item) {
          return item.task_id == task_id &&
                 std::abs(item.start - start) <= kEpsilon &&
                 std::abs(item.end - end) <= kEpsilon;
        });
    if (found == intervals_.end()) {
      return false;
    }
    intervals_.erase(found);
    generation_ = restore_generation;
    return true;
  }

  bool rollback_exact_reservation(
      int task_id,
      double start,
      double end,
      std::uint64_t restore_generation) noexcept {
    return restore_exact_reservation_noexcept(
        task_id, start, end, restore_generation);
  }

  [[nodiscard]] int size() const { return static_cast<int>(intervals_.size()); }
  [[nodiscard]] std::uint64_t generation() const noexcept {
    return generation_;
  }

#ifdef CZR005_EVENT_RUNTIME_TESTING
  void test_advance_generation() noexcept {
    ++generation_;
  }
#endif

  [[nodiscard]] std::uint64_t logical_state_fingerprint() const noexcept {
    std::uint64_t hash = 1469598103934665603ULL;
    const auto mix = [&](std::uint64_t value) {
      hash ^= value;
      hash *= 1099511628211ULL;
    };
    mix(generation_);
    mix(static_cast<std::uint64_t>(intervals_.size()));
    for (const auto& interval : intervals_) {
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(interval.task_id)));
      mix(timestamp_bits(interval.start));
      mix(timestamp_bits(interval.end));
    }
    return hash;
  }

  template <typename Visitor>
  void inspect(Visitor&& visitor) const {
    for (const auto& interval : intervals_) {
      visitor(interval);
    }
  }

  // Payload lower bound for intervals that are logically active right now.
  [[nodiscard]] std::size_t dynamic_interval_lower_bound_bytes() const noexcept {
    return intervals_.size() * sizeof(CalendarInterval);
  }

  // Payload lower bound for the interval storage retained by std::vector.
  [[nodiscard]] std::size_t dynamic_interval_capacity_accounted_bytes() const noexcept {
    return intervals_.capacity() * sizeof(CalendarInterval);
  }

 private:
  void append_sorted_noexcept(CalendarInterval interval) noexcept {
    intervals_.push_back(interval);
    std::size_t index = intervals_.size() - 1;
    while (index > 0) {
      const auto& left = intervals_[index];
      const auto& right = intervals_[index - 1];
      if (std::tie(right.start, right.end, right.task_id) <=
          std::tie(left.start, left.end, left.task_id)) {
        break;
      }
      std::swap(intervals_[index], intervals_[index - 1]);
      --index;
    }
  }

  std::vector<CalendarInterval> intervals_;
  std::uint64_t generation_ = 0;
};

static_assert(
    !std::is_default_constructible_v<
        LocalCalendar::PreparedExactReservation>);
static_assert(
    !std::is_copy_constructible_v<
        LocalCalendar::PreparedExactReservation>);
static_assert(
    std::is_nothrow_move_constructible_v<
        LocalCalendar::PreparedExactReservation>);

enum class G4IRSF17SourceWaitResource : std::uint8_t {
  kSourceServiceCalendar,
  kSourceLocalQueue,
  kFirstEdgeCredit,
  kDestinationQueue,
  kDestinationMergeToken,
  kPhysicalEdge,
  kSupervisorState,
  kPIBTOrRecoveryTransaction,
  kOtherLocalResource,
};

inline const char* g4irsf17_source_wait_resource_name(
    G4IRSF17SourceWaitResource resource) noexcept {
  switch (resource) {
    case G4IRSF17SourceWaitResource::kSourceServiceCalendar:
      return "SOURCE_SERVICE_CALENDAR";
    case G4IRSF17SourceWaitResource::kSourceLocalQueue:
      return "SOURCE_LOCAL_QUEUE";
    case G4IRSF17SourceWaitResource::kFirstEdgeCredit:
      return "FIRST_EDGE_CREDIT";
    case G4IRSF17SourceWaitResource::kDestinationQueue:
      return "DESTINATION_QUEUE";
    case G4IRSF17SourceWaitResource::kDestinationMergeToken:
      return "DESTINATION_MERGE_TOKEN";
    case G4IRSF17SourceWaitResource::kPhysicalEdge:
      return "PHYSICAL_DIRECTED_EDGE";
    case G4IRSF17SourceWaitResource::kSupervisorState:
      return "LOCAL_SUPERVISOR_STATE";
    case G4IRSF17SourceWaitResource::kPIBTOrRecoveryTransaction:
      return "LOCAL_PIBT_OR_RECOVERY_TRANSACTION";
    case G4IRSF17SourceWaitResource::kOtherLocalResource:
      return "OTHER_BOUNDED_LOCAL_RESOURCE";
  }
  return "OTHER_BOUNDED_LOCAL_RESOURCE";
}

struct G4IRSF17SourceBlockerObservation {
  bool valid = false;
  G4IRSF17SourceWaitReason reason =
      G4IRSF17SourceWaitReason::kOtherExplicitReason;
  G4IRSF17SourceWaitResource resource =
      G4IRSF17SourceWaitResource::kOtherLocalResource;
  int blocker_node = -1;
  int resource_from_node = -1;
  int resource_to_node = -1;
  std::uint64_t blocker_generation = 0;

  void consider(G4IRSF17SourceWaitReason candidate_reason,
                G4IRSF17SourceWaitResource candidate_resource,
                int candidate_blocker_node,
                int candidate_resource_from_node,
                int candidate_resource_to_node,
                std::uint64_t candidate_generation) noexcept {
    const auto candidate_key = std::make_tuple(
        g4irsf17_source_wait_reason_precedence(candidate_reason),
        candidate_blocker_node,
        static_cast<int>(candidate_resource),
        candidate_resource_from_node,
        candidate_resource_to_node,
        candidate_generation);
    const auto current_key = std::make_tuple(
        g4irsf17_source_wait_reason_precedence(reason),
        blocker_node,
        static_cast<int>(resource),
        resource_from_node,
        resource_to_node,
        blocker_generation);
    if (!valid || candidate_key < current_key) {
      valid = true;
      reason = candidate_reason;
      resource = candidate_resource;
      blocker_node = candidate_blocker_node;
      resource_from_node = candidate_resource_from_node;
      resource_to_node = candidate_resource_to_node;
      blocker_generation = candidate_generation;
    }
  }
};

struct G4IRSF17ActiveSourceWait {
  G4IRSF17SourceBlockerObservation blocker;
  double started_at = 0.0;
  std::uint64_t source_generation = 0;
  int affected_bag_count = 0;
  int selected_runtime_bag_id = -1;
};

struct G4IRSF17LocalBlockerState {
  bool valid = false;
  G4IRSF17SourceBlockerObservation blocker;
  std::uint64_t generation = 0;
};

enum class BagStatus {
  kPendingRelease,
  kSourceQueue,
  kInService,
  kJunctionQueue,
  kInTransit,
  kCompleted,
  kFailed,
};

struct BagState {
  EventRuntimeBagRequest request;
  BagStatus status = BagStatus::kPendingRelease;
  bool active_in_runtime = false;
  int current = -1;
  int transit_from = -1;
  int transit_to = -1;
  DestinationMergeGrantExpectation
      transit_merge_grant;
  double admitted_time = -1.0;
  double finish_time = -1.0;
  double source_enqueued_at = -1.0;
  double junction_enqueued_at = -1.0;
  double total_wait = 0.0;
  double junction_queue_wait_seconds = 0.0;
  double edge_travel_time_seconds = 0.0;
  double node_service_time_seconds = 0.0;
  double loop_extra_time_seconds = 0.0;
  double goal_completion_time_seconds = 0.0;
  int decision_count = 0;
  int retry_count = 0;
  int loop_count = 0;
  std::uint64_t first_edge_credit_id = 0;
  bool first_edge_credit_consumed = false;
  double deadlock_started_at = -1.0;
  std::string failure_reason;
  std::deque<int> history;
  std::uint64_t local_enqueue_sequence = 0;
  std::uint64_t fault_priority_generation = 0;
  bool repaired_task_reentry = false;
};

struct JunctionState {
  std::deque<int> source_queue;
  std::deque<int> queue;
  LocalCalendar service_calendar;
  int peak_source_queue_length = 0;
  int peak_junction_queue_length = 0;
  int peak_service_calendar_intervals = 0;
  std::size_t peak_local_state_accounted_bytes = 0;
  std::uint64_t service_reservation_count = 0;
  double cumulative_service_reserved_seconds = 0.0;
  double first_service_reservation_start_time = -1.0;
  double last_service_reservation_end_time = -1.0;
  double next_dispatch_time = 0.0;
  int scheduled_incoming = 0;
  std::unordered_map<int, int> scheduled_incoming_by_goal;
  std::uint64_t source_wakeup_generation = 0;
  std::uint64_t junction_wakeup_generation = 0;
  bool source_wakeup_pending = false;
  bool junction_wakeup_pending = false;
  int escape_token_task = -1;
  std::uint64_t g4irsf17_source_generation = 0;
  std::optional<G4IRSF17ActiveSourceWait>
      g4irsf17_active_source_wait;
  G4IRSF17LocalBlockerState g4irsf17_local_blocker;
  G4IRSF17SourceTemporalState g4irsf17_source_temporal;

  [[nodiscard]] std::size_t current_local_state_accounted_bytes() const noexcept {
    // std::deque does not expose retained block capacity, so live element
    // payload is the strongest portable lower bound available here.
    return sizeof(JunctionState) + source_queue.size() * sizeof(int) +
           queue.size() * sizeof(int) +
           (g4irsf17_source_temporal.releases.timestamps.size() +
            g4irsf17_source_temporal.admissions.timestamps.size() +
            g4irsf17_source_temporal.service_completions.timestamps.size()) *
               sizeof(double) +
           service_calendar.dynamic_interval_capacity_accounted_bytes();
  }

  void observe_local_state() noexcept {
    peak_source_queue_length =
        std::max(peak_source_queue_length, static_cast<int>(source_queue.size()));
    peak_junction_queue_length =
        std::max(peak_junction_queue_length, static_cast<int>(queue.size()));
    peak_service_calendar_intervals =
        std::max(peak_service_calendar_intervals, service_calendar.size());
    peak_local_state_accounted_bytes =
        std::max(peak_local_state_accounted_bytes, current_local_state_accounted_bytes());
  }

  void record_service_reservation(double start_time, double end_time) noexcept {
    if (service_reservation_count == 0) {
      first_service_reservation_start_time = start_time;
      last_service_reservation_end_time = end_time;
    } else {
      first_service_reservation_start_time =
          std::min(first_service_reservation_start_time, start_time);
      last_service_reservation_end_time =
          std::max(last_service_reservation_end_time, end_time);
    }
    ++service_reservation_count;
    cumulative_service_reserved_seconds += end_time - start_time;
  }
};

struct FaultState {
  int active_count = 0;
  int physical_generation = 0;
};

struct AdvertisedFaultState {
  bool faulted = false;
  int generation = 0;
  double received_at = 0.0;
};

// A bounded, one-hop congestion advertisement.  Source admission never reads
// a downstream JunctionState or LocalCalendar directly: it consumes only this
// scalar snapshot for each real outgoing neighbour plus the physical state of
// its own outgoing edges.
struct CongestionBeaconState {
  int queue_length = 0;
  int scheduled_incoming = 0;
  std::unordered_map<int, int> queue_length_by_goal;
  std::unordered_map<int, int> scheduled_incoming_by_goal;
  double service_calendar_reserved_until = 0.0;
  double received_at = 0.0;
  std::uint64_t generation = 0;
  G4IRSF17LocalBlockerState g4irsf17_local_blocker;
  int g4irsf17_merge_pending_request_count = 0;
  int g4irsf17_merge_active_grant_count = 0;
  std::uint64_t g4irsf17_merge_generation = 0;
  double g4irsf17_estimated_service_rate_60s = 0.0;
  double g4irsf17_drain_slope_60s = 0.0;
  double g4irsf17_one_hop_ttl_pressure = 0.0;
  double g4irsf17_merge_oldest_request_age_seconds = 0.0;
  double g4irsf17_recent_incoming_grants_60s = 0.0;
  double g4irsf17_incoming_grant_imbalance_60s = 0.0;
};

constexpr std::size_t align_accounted_size(std::size_t value,
                                           std::size_t alignment) noexcept {
  return ((value + alignment - 1U) / alignment) * alignment;
}

// The accounted-byte scalar is part of the frozen telemetry-off payload.
// These offsets recover the pre-G17 object footprints even though the new
// state is append-only in the live C++ layouts.
inline constexpr std::size_t kPreG4IRSF17JunctionStateBytes =
    align_accounted_size(
        offsetof(JunctionState, g4irsf17_source_generation),
        alignof(JunctionState));
inline constexpr std::size_t kPreG4IRSF17CongestionBeaconStateBytes =
    align_accounted_size(
        offsetof(CongestionBeaconState, g4irsf17_local_blocker),
        alignof(CongestionBeaconState));
inline constexpr std::size_t kG4IRSF17JunctionStateExtensionBytes =
    sizeof(JunctionState) - kPreG4IRSF17JunctionStateBytes;
inline constexpr std::size_t kPreG4IRSF17SummaryBytes =
    align_accounted_size(
        offsetof(EventRuntimeSummary,
                 g4irsf17_source_wait_telemetry_enabled),
        alignof(EventRuntimeSummary));
inline constexpr std::size_t kG4IRSF17SummaryExtensionBytes =
    sizeof(EventRuntimeSummary) - kPreG4IRSF17SummaryBytes;
inline constexpr std::size_t kG4IRSF17ConfigExtensionBytes =
    sizeof(bool) + (alignof(int) - sizeof(bool)) + sizeof(int) +
    sizeof(G4IRSF17SourcePolicyConfig) + sizeof(int)
#ifndef CZR005_EVENT_RUNTIME_TESTING
    + (alignof(G4IRSF17SourcePolicyConfig) - sizeof(int))
#endif
    ;
inline constexpr std::size_t kG4IRSF17ResultExtensionBytes =
    kG4IRSF17SummaryExtensionBytes +
    sizeof(std::vector<EventRuntimeSourceWaitBlockerRow>) +
    sizeof(std::vector<EventRuntimeG4IRSF17SourcePolicyRow>);
inline constexpr std::size_t kG4IRSF17RuntimeExtensionBytes =
    kG4IRSF17ConfigExtensionBytes + kG4IRSF17ResultExtensionBytes;

struct RuntimeEvent {
  JunctionEventType type = JunctionEventType::kBagRelease;
  double time = 0.0;
  std::uint64_t seq = 0;
  int task_id = -1;
  int node = -1;
  int from_node = -1;
  int to_node = -1;
  double service_end = 0.0;
  double message_delay = 0.0;
  int message_generation = 0;
  std::uint64_t wakeup_generation = 0;
  bool notification = false;
  bool drop_notification = false;
  bool retry = false;
  std::string reason;
  // Negative preserves the frozen comparator. Opt-in G4IRSF14 modes assign
  // an explicit deterministic microphase rank at publication time.
  int microphase_priority = -1;
};

inline int event_priority(const RuntimeEvent& event) {
  if ((event.type == JunctionEventType::kFault || event.type == JunctionEventType::kRepair) &&
      !event.notification) {
    return 0;
  }
  if (event.type == JunctionEventType::kFault || event.type == JunctionEventType::kRepair) {
    return 1;
  }
  if (event.type == JunctionEventType::kEdgeExit) {
    return 2;
  }
  if (event.type == JunctionEventType::kJunctionServiceComplete) {
    return 3;
  }
  if (event.type == JunctionEventType::kArriveJunction) {
    return 4;
  }
  if (event.type == JunctionEventType::kCongestionBeaconUpdate) {
    return 5;
  }
  if (event.type == JunctionEventType::kBagRelease) {
    return 6;
  }
  if (event.type == JunctionEventType::kSourceArbitration) {
    return 7;
  }
  if (event.type == JunctionEventType::kJunctionArbitration) {
    return 8;
  }
  if (event.type == JunctionEventType::kDestinationMergeArbitration) {
    return 9;
  }
  if (event.type == JunctionEventType::kEdgeEnter) {
    return 10;
  }
  return 11;  // LOCAL_QUEUE_UPDATE
}

struct RuntimeEventLater {
  bool operator()(const RuntimeEvent& left, const RuntimeEvent& right) const {
    if (std::abs(left.time - right.time) > kEpsilon) {
      return left.time > right.time;
    }
    const int left_priority = left.microphase_priority >= 0
                                  ? left.microphase_priority
                                  : event_priority(left);
    const int right_priority = right.microphase_priority >= 0
                                   ? right.microphase_priority
                                   : event_priority(right);
    if (left_priority != right_priority) {
      return left_priority > right_priority;
    }
    return left.seq > right.seq;
  }
};

class RuntimeEventQueue
    : public std::priority_queue<RuntimeEvent,
                                 std::vector<RuntimeEvent>,
                                 RuntimeEventLater> {
 public:
  void reserve(std::size_t capacity) {
    this->c.reserve(capacity);
  }

  [[nodiscard]] std::size_t
  dynamic_storage_accounted_bytes() const noexcept {
    std::size_t accounted =
        this->c.capacity() * sizeof(RuntimeEvent);
    for (const auto& event : this->c) {
      accounted += event.reason.capacity();
    }
    return accounted;
  }

  template <typename Visitor>
  void inspect(Visitor&& visitor) const {
    for (const auto& event : this->c) {
      visitor(event);
    }
  }
};

struct LocalArbitrationState {
  double source_wakeup_time = std::numeric_limits<double>::infinity();
  double junction_wakeup_time = std::numeric_limits<double>::infinity();
  bool has_last_source_arbitration = false;
  bool has_last_junction_arbitration = false;
  double last_source_arbitration_time = 0.0;
  double last_junction_arbitration_time = 0.0;
  std::uint64_t last_source_arbitration_generation = 0;
  std::uint64_t last_junction_arbitration_generation = 0;
  bool source_batch_open = false;
  bool junction_batch_open = false;
  double source_batch_time = 0.0;
  double junction_batch_time = 0.0;
  int source_queue_before_enqueue = 0;
  int source_queue_after_enqueue = 0;
  int junction_queue_before_enqueue = 0;
  int junction_queue_after_enqueue = 0;
  int source_enqueue_count = 0;
  int junction_enqueue_count = 0;
};

struct DestinationMergeArbitrationState {
  double wakeup_time = std::numeric_limits<double>::infinity();
  std::uint64_t wakeup_generation = 0;
  bool wakeup_pending = false;
};

struct DestinationMergeBagState {
  std::uint64_t junction_queue_generation = 0;
  std::uint64_t request_generation = 0;
  std::uint64_t pending_request_id = 0;
  std::uint64_t pending_lineage = 0;
  double pending_request_time = -1.0;
  double first_contention_time = -1.0;
  double grant_wait_seconds = 0.0;
  int g4irsf18_merge_override_count = 0;
  // Minted only by a valid EDGE_ENTER that observes the exact committed
  // capability at its original fault generations while the edge is healthy.
  bool exact_grant_edge_entry_observed = false;
  std::optional<MergeGrantCapability> capability;
};

struct DestinationMergeBagStateCheckpoint {
  std::uint64_t junction_queue_generation = 0;
  std::uint64_t request_generation = 0;
  std::uint64_t pending_request_id = 0;
  std::uint64_t pending_lineage = 0;
  double pending_request_time = -1.0;
  double first_contention_time = -1.0;
  double grant_wait_seconds = 0.0;
  int g4irsf18_merge_override_count = 0;
  bool exact_grant_edge_entry_observed = false;
  std::optional<MergeGrantCapabilityCheckpoint> capability;
};

struct G4IRSF14RuntimeState {
  std::unordered_map<int, LocalArbitrationState> local;
  std::unordered_map<int, DestinationMergeArbitrationState>
      destination_merge;
  std::unordered_map<int, DestinationMergeBagState>
      destination_merge_bags;
  std::uint64_t current_event_seq = 0;
  bool microphase_floor_active = false;
  double microphase_floor_time = 0.0;
  int microphase_floor_priority = -1;
  int current_pibt_slice_bag_count = 0;
  int current_pibt_owner_count = 0;
};

struct G4IRSF14RuntimeStateCheckpoint {
  std::unordered_map<int, LocalArbitrationState> local;
  std::unordered_map<int, DestinationMergeArbitrationState>
      destination_merge;
  std::unordered_map<int, DestinationMergeBagStateCheckpoint>
      destination_merge_bags;
  std::uint64_t current_event_seq = 0;
  bool microphase_floor_active = false;
  double microphase_floor_time = 0.0;
  int microphase_floor_priority = -1;
  int current_pibt_slice_bag_count = 0;
  int current_pibt_owner_count = 0;
};

struct PendingMergeDispatch {
  std::uint64_t request_id = 0;
  std::uint64_t lineage = 0;
  int runtime_bag_id = -1;
  int upstream_node = -1;
  int destination_node = -1;
  EventDecisionTraceRow trace;
};

static_assert(std::is_nothrow_move_constructible_v<RuntimeEvent>);
static_assert(std::is_nothrow_move_assignable_v<RuntimeEvent>);

}  // namespace event_runtime_detail

class EventDrivenJunctionRuntime {
 private:
  struct CheckpointStorage {
    const Graph* graph_identity = nullptr;
    std::string graph_sha256;
    EventDrivenJunctionConfig config;
    std::optional<EdgeScoreModel> scorer_model;
    std::map<std::pair<int, int>, int> scorer_static_hops;
    std::map<std::tuple<int, int, int>, double>
        pibt_regret_prior;
    EventDrivenJunctionResult result;
    std::unordered_map<int, event_runtime_detail::BagState> bags;
    std::unordered_map<std::string, int> segment_runtime_ids;
    std::unordered_map<int, event_runtime_detail::JunctionState>
        junctions;
    std::unordered_map<long long, event_runtime_detail::LocalCalendar>
        corridors;
    std::unordered_map<long long, event_runtime_detail::FaultState>
        physical_faults;
    std::unordered_map<long long,
                       event_runtime_detail::AdvertisedFaultState>
        advertised_faults;
    std::unordered_map<int,
                       event_runtime_detail::CongestionBeaconState>
        congestion_beacons;
    std::unordered_map<int,
        DestinationMergeGrantControllerCheckpoint>
        destination_merge_controllers;
    std::unordered_map<std::uint64_t,
                       event_runtime_detail::PendingMergeDispatch>
        pending_merge_dispatches;
    ExpiringFirstEdgeCreditCheckpoint credit_ledger;
    std::unordered_map<long long, int> directed_inflight_counts;
    std::unordered_set<int> fault_affected_bags;
    std::unordered_map<long long, std::set<int>>
        fault_affected_bags_by_edge;
    std::unordered_map<int, std::set<std::pair<long long, int>>>
        fault_instances_by_bag;
    std::unordered_map<long long, int>
        active_fault_instance_by_edge;
    std::map<std::pair<long long, int>, double>
        repair_time_by_fault_instance;
    event_runtime_detail::RuntimeEventQueue events;
    std::optional<
        event_runtime_detail::G4IRSF14RuntimeStateCheckpoint>
        g4irsf14_state;
#ifdef CZR005_EVENT_RUNTIME_TESTING
    bool test_pibt_logical_failure_injected = false;
    bool test_merge_grant_prepare_failure_injected = false;
    bool test_merge_grant_advertised_flip_injected = false;
    bool test_merge_grant_physical_flip_injected = false;
    bool test_merge_grant_calendar_flip_injected = false;
    bool test_merge_grant_queue_flip_injected = false;
    bool test_merge_grant_edge_exit_capability_drop_injected = false;
    bool test_merge_grant_edge_exit_physical_flip_injected = false;
    bool test_merge_grant_edge_exit_advertised_flip_injected = false;
    bool test_merge_grant_edge_exit_calendar_remove_injected = false;
    bool test_merge_grant_edge_exit_expiry_injected = false;
    bool test_merge_grant_edge_exit_wrong_owner_injected = false;
    bool test_merge_grant_edge_exit_wrong_edge_injected = false;
    bool test_merge_grant_edge_exit_wrong_destination_injected = false;
    bool
        test_merge_grant_edge_exit_claimed_request_generation_tamper_injected =
            false;
    bool
        test_merge_grant_edge_exit_claimed_queue_generation_tamper_injected =
            false;
    bool
        test_merge_grant_edge_exit_claimed_calendar_generation_tamper_injected =
            false;
    bool
        test_merge_grant_edge_exit_live_queue_generation_advance_injected =
            false;
    bool
        test_merge_grant_edge_exit_live_calendar_generation_advance_injected =
            false;
    bool test_pibt_post_commit_failure_injected = false;
#endif
    std::uint64_t next_event_seq = 1;
    std::uint64_t next_decision_id = 1;
    std::uint64_t next_pibt_activation_id = 1;
    std::uint64_t next_local_enqueue_sequence = 1;
    std::uint64_t next_merge_request_lineage = 1;
    double now = 0.0;
    double time_limit = 0.0;
    int active_bag_count = 0;
    double last_physical_repair_time = -1.0;
    int active_backlog_at_last_repair = -1;
    int active_backlog_at_runtime_stop = -1;
    std::vector<double> waits;
    std::vector<double> decision_latencies_us;
    EventDrivenJunctionRuntimePhase phase =
        EventDrivenJunctionRuntimePhase::kIdle;
    G4IRSF14RuntimeStateDigests state_digests;
    std::string state_sha256;
  };

 public:
  class StateCheckpoint {
   public:
    StateCheckpoint(const StateCheckpoint&) = default;
    StateCheckpoint& operator=(const StateCheckpoint&) = default;
    StateCheckpoint(StateCheckpoint&&) noexcept = default;
    StateCheckpoint& operator=(StateCheckpoint&&) noexcept = default;

    [[nodiscard]] const std::string& state_sha256() const {
      if (storage_ == nullptr) {
        throw std::logic_error("empty runtime state checkpoint");
      }
      return sealed_state_sha256_;
    }

#ifdef CZR005_EVENT_RUNTIME_TESTING
    void test_corrupt_seal() {
      if (sealed_state_sha256_.empty()) {
        sealed_state_sha256_ = "0";
      } else {
        sealed_state_sha256_[0] =
            sealed_state_sha256_[0] == '0' ? '1' : '0';
      }
    }
#endif

   private:
    friend class EventDrivenJunctionRuntime;
    StateCheckpoint(
        std::shared_ptr<const CheckpointStorage> storage,
        std::string sealed_state_sha256)
        : storage_(std::move(storage)),
          sealed_state_sha256_(
              std::move(sealed_state_sha256)) {}

    std::shared_ptr<const CheckpointStorage> storage_;
    std::string sealed_state_sha256_;
  };

  explicit EventDrivenJunctionRuntime(const Graph& graph, EventDrivenJunctionConfig config = {})
      : graph_(graph), config_(std::move(config)) {
    validate_config();
    if (g4irsf14_extensions_enabled()) {
      g4irsf14_state_ =
          std::make_unique<event_runtime_detail::G4IRSF14RuntimeState>();
    }
    initialize_regret_prior();
    initialize_scorer();
    if (g4irsf16_enabled()) {
      if (!g4irsf16_uses_diagnostic_rule()) {
        g4irsf16_i3_model_ =
            std::make_unique<G4IRSF16SelectiveLinearModel>(
                config_.g4irsf16_i3_model);
        g4irsf16_i4_model_ =
            std::make_unique<G4IRSF16SelectiveLinearModel>(
                config_.g4irsf16_i4_model);
      }
      g4irsf16_supervisor_ =
          std::make_unique<G4IRSF16Supervisor>(
              g4irsf16_supervisor_config());
    }
  }

  void initialize(
      const std::vector<EventRuntimeBagRequest>& requests,
      const std::vector<EventRuntimeFaultWindow>& fault_windows = {}) {
    if (runtime_phase_ != EventDrivenJunctionRuntimePhase::kIdle &&
        runtime_phase_ != EventDrivenJunctionRuntimePhase::kFinalized) {
      throw std::logic_error(
          "event runtime initialize called while a run is active");
    }
    runtime_started_ = std::chrono::steady_clock::now();
    reset();
    result_.summary.requested_count = static_cast<int>(requests.size());
    // Initialization publishes one release event per request before the
    // runtime starts draining.  Reserve that known lower bound once so the
    // priority queue does not repeatedly relocate RuntimeEvent strings while
    // loading large fixed-map scale inputs.  Capacity never affects ordering.
    events_.reserve(requests.size() + 2 * fault_windows.size());
    result_.summary.diagnostic_hops = config_.diagnostic_hops;
    result_.summary.trace_limit = config_.trace_limit;
    result_.summary.event_trace_limit = effective_event_trace_limit();
    result_.summary.event_trace_limit_inherited =
        !config_.event_trace_limit.has_value();
    result_.summary.trace_shard_count = config_.trace_shard_count;
    result_.summary.trace_shard_index = config_.trace_shard_index;
    result_.summary.event_semantics = canonical_event_semantics();
    result_.summary.event_semantics_echo = config_.event_semantics;
    result_.summary.opportunity_telemetry_enabled =
        config_.enable_opportunity_telemetry;
    result_.summary.g4irsf17_source_wait_telemetry_enabled =
        config_.enable_g4irsf17_source_wait_telemetry;
    if (g4irsf17_source_policy_enabled()) {
      result_.summary.g4irsf17_source_policy_mode =
          config_.g4irsf17_source_policy.mode;
      result_.summary.g4irsf17_source_policy_kind =
          config_.g4irsf17_source_policy.kind;
      result_.summary.g4irsf17_source_policy_artifact_set_id =
          config_.g4irsf17_source_policy.artifact_set_id;
      result_.summary.g4irsf17_source_policy_authorized =
          config_.g4irsf17_source_policy.authorized;
      result_.summary
          .g4irsf17_source_policy_runtime_closed_loop_authorized =
          config_.g4irsf17_source_policy.runtime_closed_loop_authorized;
      result_.summary.g4irsf17_source_policy_top_k =
          config_.g4irsf17_source_policy.top_k;
    }
    result_.summary.merge_grant_runtime_owned_capability =
        uses_destination_merge_grants();
    result_.summary.merge_grant_exact_slot_no_future_shift =
        uses_destination_merge_grants();
    result_.summary.merge_grant_timing_mode =
        destination_merge_grant_timing_mode_name(
            canonical_merge_grant_timing_mode());
    if (g4irsf18_merge_policy_enabled()) {
      const auto& policy = config_.g4irsf18_merge_policy;
      result_.summary.g4irsf18_merge_policy_mode = policy.mode;
      result_.summary.g4irsf18_merge_policy_schema = policy.schema;
      result_.summary.g4irsf18_merge_policy_family = policy.family;
      result_.summary.g4irsf18_merge_feature_contract =
          kG4IRSF18MergeFeatureContract;
      result_.summary.g4irsf18_merge_artifact_valid =
          policy.artifact_valid();
      result_.summary
          .g4irsf18_merge_artifact_production_closed_loop_authorized =
          policy.artifact_production_closed_loop_authorized;
      result_.summary
          .g4irsf18_merge_research_closed_loop_authorized =
          policy.research_closed_loop_authorized;
      result_.summary.g4irsf18_merge_fixed_research_workload =
          policy.fixed_research_workload;
      result_.summary
          .g4irsf18_merge_production_closed_loop_authorized =
          policy.production_closed_loop_authorized;
      result_.summary.g4irsf18_merge_offline_gate_passed =
          policy.offline_gate_passed;
      result_.summary.g4irsf18_merge_coverage_cap =
          policy.coverage_cap;
      result_.summary.g4irsf18_merge_max_overrides_per_segment =
          policy.max_overrides_per_segment;
      result_.summary.g4irsf18_merge_kill_switch_configured =
          policy.kill_switch;
      if (policy.kill_switch) {
        result_.summary.g4irsf18_merge_kill_switch_tripped = true;
        result_.summary.g4irsf18_merge_kill_switch_reason =
            "EXPLICIT_RUNTIME_KILL_SWITCH";
        result_.summary.g4irsf18_merge_kill_switch_trip_count = 1;
      }
    }
    if (g4irsf16_enabled()) {
      result_.summary.g4irsf16_supervisor_mode =
          canonical_g4irsf16_supervisor_mode();
      result_.summary.g4irsf16_i3_model_sha256 =
          config_.g4irsf16_i3_model.artifact_sha256;
      result_.summary.g4irsf16_i4_model_sha256 =
          config_.g4irsf16_i4_model.artifact_sha256;
      if (g4irsf16_uses_diagnostic_rule()) {
        result_.summary.g4irsf16_policy_kind =
            "diagnostic_rule";
        result_.summary.g4irsf16_i4_policy_id =
            config_.g4irsf16_i4_diagnostic_rule.rule;
        result_.summary.g4irsf16_i4_policy_authorization =
            config_.g4irsf16_i4_diagnostic_rule.authorization;
        result_.summary.g4irsf16_diagnostic_only = true;
        result_.summary.g4irsf16_promotion_authorized = false;
        result_.summary.g4irsf16_i4_model_sha256 =
            config_.g4irsf16_i4_diagnostic_rule.artifact_sha256;
      } else {
        result_.summary.g4irsf16_policy_kind =
            "unpromoted_model_shadow";
        result_.summary.g4irsf16_diagnostic_only = true;
        result_.summary.g4irsf16_promotion_authorized = false;
      }
    }
    result_.summary.admission_mode = canonical_admission_mode();
    result_.summary.admission_mode_echo = config_.admission_mode;
    result_.summary.source_admission_enabled =
        result_.summary.admission_mode != "off";
    result_.summary.pibt_mode = canonical_pibt_mode_name();
    result_.summary.pibt_mode_echo = config_.pibt_mode;
    result_.summary.priority_mode = canonical_priority_mode_name();
    result_.summary.priority_mode_echo = config_.priority_mode;
    result_.summary.pibt_preference_mode =
        config_.pibt_preference_mode;
    result_.summary.pibt_preference_mode_echo =
        config_.pibt_preference_mode;
    result_.summary.credit_mode = canonical_credit_mode();
    result_.summary.scorer_mode = config_.scorer_mode;
    result_.summary.scorer_mode_echo = config_.scorer_mode;
    result_.summary.framework_mode = canonical_framework_mode();
    result_.summary.framework_mode_echo = config_.framework_mode;
    result_.summary.framework_diagnostic_only =
        canonical_framework_mode() ==
        "legacy_order_one_step_diagnostic";
    result_.summary.pibt_mode_diagnostic_only =
        canonical_pibt_mode() == BoundedLocalPIBTMode::kP4;
    result_.summary.priority_claim_boundary =
        "current_local_queue_and_simultaneously_ready_pibt_slice_only;"
        "fault_class_current_slack_age_enqueue_sequence_stable_id;"
        "no_teacher_input;no_future_route_or_schedule;no_global_task_scan;"
        "Q1_is_ordinal_local_projection_not_invented_numeric_thesis_weights";
    result_.summary.scorer_id = canonical_scorer_id();
    result_.summary.scorer_model_sha256 =
        config_.scorer_model_sha256;
    result_.summary.scorer_score_direction =
        canonical_scorer_mode() == "S1" ||
                canonical_scorer_mode() == "S2"
            ? "raw_frozen_mlp_score_is_higher_is_better;"
              "effective_model_score_is_lower_is_better_negated_raw_"
              "unless_risk_gate_restores_exact_s0_cost"
            : "raw_and_effective_scores_are_lower_is_better_cost";
    result_.summary.scorer_claim_boundary =
        "current_event_real_outgoing_candidates_only;"
        "static_map_attributes_and_current_local_candidate_snapshot;"
        "no_teacher_next_or_path;no_future_route_or_schedule;"
        "no_posthoc_outcome_or_label_source;"
        "S1_S2_are_out_of_distribution_not_promotion_eligible_but_"
        "drive_ablation_selection_when_the_risk_gate_allows";
    result_.summary.scorer_out_of_distribution_diagnostic =
        canonical_scorer_mode() == "S1" ||
        canonical_scorer_mode() == "S2";
    result_.summary.scorer_promotion_eligible = false;
    result_.summary.scorer_absolute_node_ids_enabled =
        canonical_scorer_mode() == "S1";
    result_.summary.scorer_static_precompute_only =
        canonical_scorer_mode() == "S1" ||
        canonical_scorer_mode() == "S2";
    result_.summary.scorer_feature_dim =
        result_.summary.scorer_out_of_distribution_diagnostic
            ? 22
            : 0;
    result_.summary.scorer_explicit_default_feature_count =
        canonical_scorer_mode() == "S1"
            ? 8
            : (canonical_scorer_mode() == "S2" ? 10 : 0);
    result_.summary.pibt_max_depth =
        bounded_local_pibt_depth(canonical_pibt_mode());
    result_.summary.bounded_local_pibt_claim_boundary =
        "finite_configured_local_queue_capacity_only;"
        "simultaneously_ready_one_owner_per_node;"
        "real_adjacent_one_edge_candidates;"
        "bounded_bags_resources_candidates;"
        "credit_transaction_scoped_to_selected_action_ids;" +
        std::string(
            canonical_event_semantics() ==
                    "E0_immediate_dispatch_f2"
                ? "transaction_deltas_O_selected_actions_no_queue_or_calendar_copy;"
                : "transaction_state_bounded_by_selected_bags_nodes_and_corridors;") +
        "two_phase_local_prevalidation_and_logical_failure_atomic_publish;"
        "one_edge_per_bag_per_decision;multi_bag_batch_action_count_reported_separately;"
        "no_astar;no_global_reservation_scan;no_future_route;"
        "pibt_inspired_no_classical_completeness_claim";
    result_.summary.first_edge_credit_claim_boundary =
        "source_local_state_plus_bounded_one_hop_target_state_or_beacon;"
        "one_adjacent_selected_edge;"
        "active_only_ledger;bounded_recent_lifecycle;no_future_route;"
        "no_global_scan;physical_interlock_not_bypassable";
    result_.summary.fault_policy_enabled = config_.enable_fault_policy;
    result_.summary.legacy_pibt_lite_enabled =
        config_.enable_pibt_lite;
    result_.summary.resource_semantics_id = canonical_resource_semantics();
    result_.summary.resource_semantics_echo =
        config_.resource_semantics;
    result_.summary.pressure_mode = canonical_pressure_mode();
    result_.summary.pressure_mode_echo = config_.pressure_mode;
    result_.summary.entry_headway_seconds = config_.entry_headway_seconds;
    result_.summary.pressure_weight = config_.pressure_weight;
    result_.summary.pressure_age_weight =
        config_.pressure_age_weight;
    result_.summary.pressure_distance_bias =
        config_.pressure_distance_bias;
    result_.summary.credit_validity_seconds =
        config_.credit_validity_seconds;
    result_.summary.credit_snapshot_max_age_seconds =
        config_.credit_snapshot_max_age_seconds;
    result_.summary.credit_capacity_per_edge =
        config_.credit_capacity_per_edge;
    result_.summary.credit_lifecycle_limit =
        config_.credit_lifecycle_limit;
    result_.summary.selective_credit_contention_threshold =
        config_.selective_credit_contention_threshold;
    result_.summary.pibt_regret_prior_record_count =
        static_cast<int>(pibt_regret_prior_.size());
    result_.summary.declared_max_events = config_.max_events;
    result_.summary.declared_max_simulation_time =
        config_.max_simulation_time;
    result_.summary.local_queue_capacity =
        config_.local_queue_capacity;
    result_.summary.pibt_max_ready_bags =
        config_.pibt_max_ready_bags;
    result_.summary.pibt_max_local_resources =
        config_.pibt_max_local_resources;
    result_.summary.pibt_max_candidates_per_bag =
        config_.pibt_max_candidates_per_bag;

    double latest_release = 0.0;
    int next_runtime_bag_id = 0;
    std::unordered_map<int, double> initial_beacon_times;
    for (const auto& request : requests) {
      validate_request(request);
      if (segment_runtime_ids_.find(request.segment_id) != segment_runtime_ids_.end()) {
        throw std::invalid_argument("event runtime segment_id values must be unique");
      }
      event_runtime_detail::BagState state;
      state.request = request;
      state.request.runtime_bag_id = next_runtime_bag_id;
      state.current = request.start;
      segment_runtime_ids_.emplace(request.segment_id, next_runtime_bag_id);
      bags_.emplace(next_runtime_bag_id, std::move(state));
      schedule(JunctionEventType::kBagRelease,
               request.release_time,
               next_runtime_bag_id,
               request.start,
               -1,
               -1);
      for (const int downstream : graph_.outgoing(request.start)) {
        const auto inserted = initial_beacon_times.emplace(downstream, request.release_time);
        if (!inserted.second) {
          inserted.first->second = std::min(inserted.first->second, request.release_time);
        }
      }
      ++next_runtime_bag_id;
      latest_release = std::max(latest_release, request.release_time);
    }

    std::vector<int> ordered_initial_beacons;
    ordered_initial_beacons.reserve(initial_beacon_times.size());
    for (const auto& entry : initial_beacon_times) {
      ordered_initial_beacons.push_back(entry.first);
    }
    std::sort(ordered_initial_beacons.begin(), ordered_initial_beacons.end());
    for (const int node : ordered_initial_beacons) {
      schedule_passive(JunctionEventType::kCongestionBeaconUpdate,
                       initial_beacon_times.at(node),
                       -1,
                       node,
                       -1,
                       node,
                       "initial_one_hop_snapshot");
    }

    for (const auto& window : fault_windows) {
      validate_fault_window(window);
      event_runtime_detail::RuntimeEvent fault;
      fault.type = JunctionEventType::kFault;
      fault.time = window.fault_time;
      fault.from_node = window.start;
      fault.to_node = window.end;
      fault.message_delay = window.message_delay;
      fault.drop_notification = window.drop_notification;
      push_event(std::move(fault));

      event_runtime_detail::RuntimeEvent repair;
      repair.type = JunctionEventType::kRepair;
      repair.time = window.repair_time;
      repair.from_node = window.start;
      repair.to_node = window.end;
      repair.message_delay = window.message_delay;
      repair.drop_notification = window.drop_notification;
      push_event(std::move(repair));
    }

    time_limit_ = config_.max_simulation_time >= 0.0
                      ? config_.max_simulation_time
                      : latest_release + 86400.0;
    runtime_phase_ = events_.empty()
                         ? EventDrivenJunctionRuntimePhase::kStopped
                         : EventDrivenJunctionRuntimePhase::kReady;
  }

  [[nodiscard]] std::optional<EventDrivenJunctionSafeBoundary>
  peek_safe_boundary() const {
    if (runtime_phase_ != EventDrivenJunctionRuntimePhase::kReady ||
        events_.empty()) {
      return std::nullopt;
    }
    require_checkpoint_safe_boundary();
    const auto& event = events_.top();
    EventDrivenJunctionSafeBoundary boundary;
    boundary.next_event_type = event.type;
    boundary.next_event_time = event.time;
    boundary.next_event_seq = event.seq;
    boundary.runtime_bag_id = event.task_id;
    boundary.node = event.node;
    boundary.from_node = event.from_node;
    boundary.to_node = event.to_node;
    for (const auto& entry : destination_merge_controllers_) {
      boundary.active_merge_capability_count +=
          static_cast<int>(
              entry.second.active_unconsumed_count());
      boundary.pending_merge_request_count +=
          static_cast<int>(entry.second.pending_count());
    }
    for (const auto& entry : physical_faults_) {
      if (entry.second.active_count > 0) {
        ++boundary.active_physical_fault_edge_count;
      }
    }
    for (const auto& entry : junctions_) {
      boundary.queued_bag_count +=
          static_cast<int>(entry.second.source_queue.size() +
                           entry.second.queue.size());
    }
    boundary.state_sha256 = deterministic_state_sha256();
    return boundary;
  }

  bool process_one_event() {
    if (runtime_phase_ == EventDrivenJunctionRuntimePhase::kStopped ||
        runtime_phase_ == EventDrivenJunctionRuntimePhase::kFinalized) {
      return false;
    }
    if (runtime_phase_ != EventDrivenJunctionRuntimePhase::kReady) {
      throw std::logic_error(
          "process_one_event requires an initialized runtime");
    }
    require_checkpoint_safe_boundary();
    if (events_.empty()) {
      runtime_phase_ = EventDrivenJunctionRuntimePhase::kStopped;
      return false;
    }
    if (result_.summary.event_count >= config_.max_events) {
      result_.summary.event_limit_reached = true;
      runtime_phase_ = EventDrivenJunctionRuntimePhase::kStopped;
      return false;
    }
    auto event = events_.top();
    events_.pop();
    if (event.time >
        time_limit_ + event_runtime_detail::kEpsilon) {
      result_.summary.time_limit_reached = true;
      runtime_phase_ = EventDrivenJunctionRuntimePhase::kStopped;
      return false;
    }
    now_ = event.time;
    ++result_.summary.event_count;
    process_event(event);
    if (events_.empty()) {
      runtime_phase_ = EventDrivenJunctionRuntimePhase::kStopped;
    }
    return true;
  }

  // Probe one live queue-top event.  The returned opportunities are bound to
  // the exact pre-pop state and can be replayed only after restoring that
  // checkpoint into an independently constructed runtime.
  G4IRSF14CausalStepResult
  probe_one_event_for_causal_opportunities() {
    return process_one_event_causal_impl(nullptr);
  }

  // Lightweight, outcome-free census transition.  Unlike the sealed causal
  // probe above, this path never computes the 18-component runtime digest.
  // It observes the same local opportunities and consumes the same one event.
  [[nodiscard]] G4IRSF15CausalPrepopStrata
  g4irsf15_causal_prepop_strata() const {
    if (runtime_phase_ != EventDrivenJunctionRuntimePhase::kReady ||
        events_.empty()) {
      throw std::logic_error(
          "G4IRSF15 pre-pop strata require a live queue-top event");
    }
    require_checkpoint_safe_boundary();
    const auto& event = events_.top();
    G4IRSF15CausalPrepopStrata strata;
    strata.event_time = event.time;
    strata.event_seq = event.seq;
    strata.node = event.node;
    for (const auto& entry : destination_merge_controllers_) {
      strata.active_merge_capability_count +=
          static_cast<int>(
              entry.second.active_unconsumed_count());
      strata.pending_merge_request_count +=
          static_cast<int>(entry.second.pending_count());
    }
    for (const auto& entry : physical_faults_) {
      strata.active_physical_fault_edge_count +=
          entry.second.active_count > 0 ? 1 : 0;
    }
    for (const auto& entry : junctions_) {
      strata.queued_bag_count +=
          static_cast<int>(entry.second.source_queue.size() +
                           entry.second.queue.size());
    }
    return strata;
  }

  G4IRSF15CausalSkeletonStepResult
  probe_one_event_for_causal_skeletons() {
    return process_one_event_causal_skeleton_impl();
  }

  // Apply one content-addressed action treatment while consuming the same
  // queue-top event.  The directive lives only on this call's stack and is
  // never copied into config, the event queue, or a runtime checkpoint.
  G4IRSF14CausalStepResult
  process_one_event_with_causal_intervention(
      const G4IRSF14CausalInterventionDirective& directive) {
    return process_one_event_causal_impl(&directive);
  }

  // O(1) / one-local-owner prefilter for a multi-million-event census.  A
  // zero mask means callers can safely use process_one_event() and avoid the
  // full 18-component checkpoint hash.  Nonzero is intentionally a
  // conservative candidate hint; the causal probe remains the authority.
  [[nodiscard]] std::uint32_t
  peek_causal_candidate_kind_mask() const noexcept {
    if (runtime_phase_ != EventDrivenJunctionRuntimePhase::kReady ||
        events_.empty()) {
      return kG4IRSF14CausalCandidateNone;
    }
    const auto& event = events_.top();
    if (event.type == JunctionEventType::kSourceArbitration) {
      const auto local = junctions_.find(event.node);
      return local != junctions_.end() &&
                     local->second.source_queue.size() >= 2U
                 ? kG4IRSF14CausalCandidateI1
                 : kG4IRSF14CausalCandidateNone;
    }
    if (event.type == JunctionEventType::kJunctionArbitration) {
      const auto local = junctions_.find(event.node);
      return local != junctions_.end() &&
                     !local->second.queue.empty()
                 ? kG4IRSF14CausalCandidateI3 |
                       kG4IRSF14CausalCandidateI4
                 : kG4IRSF14CausalCandidateNone;
    }
    if (event.type ==
        JunctionEventType::kDestinationMergeArbitration) {
      const auto controller =
          destination_merge_controllers_.find(event.node);
      if (controller ==
              destination_merge_controllers_.end() ||
          controller->second.pending_count() == 0U) {
        return kG4IRSF14CausalCandidateNone;
      }
      std::uint32_t mask =
          controller->second.pending_count() >= 2U
              ? kG4IRSF14CausalCandidateI2
              : kG4IRSF14CausalCandidateNone;
      const auto destination = junctions_.find(event.node);
      if (config_.local_queue_capacity > 0 &&
          destination != junctions_.end() &&
          static_cast<int>(destination->second.queue.size()) +
                  destination->second.scheduled_incoming >=
              config_.local_queue_capacity) {
        mask |= kG4IRSF14CausalCandidateI5;
      }
      return mask;
    }
    return kG4IRSF14CausalCandidateNone;
  }

  [[nodiscard]] G4IRSF14CausalHorizonState
  causal_horizon_state(
      const std::vector<int>& runtime_bag_ids) const {
    if (runtime_bag_ids.empty() ||
        std::set<int>(runtime_bag_ids.begin(),
                      runtime_bag_ids.end())
                .size() != runtime_bag_ids.size()) {
      throw std::invalid_argument(
          "causal horizon ids must be non-empty and unique");
    }
    G4IRSF14CausalHorizonState horizon;
    horizon.bags.reserve(runtime_bag_ids.size());
    for (const int runtime_bag_id : runtime_bag_ids) {
      if (runtime_bag_id < 0) {
        throw std::invalid_argument(
            "causal horizon runtime bag id must be non-negative");
      }
      G4IRSF14CausalBagHorizonRow row;
      row.runtime_bag_id = runtime_bag_id;
      const auto found = bags_.find(runtime_bag_id);
      if (found != bags_.end()) {
        row.known = true;
        row.completed =
            found->second.status ==
            event_runtime_detail::BagStatus::kCompleted;
        row.failed =
            found->second.status ==
            event_runtime_detail::BagStatus::kFailed;
        row.terminal = row.completed || row.failed;
        row.finish_time = found->second.finish_time;
        row.total_wait = found->second.total_wait;
        row.decision_count = found->second.decision_count;
        row.retry_count = found->second.retry_count;
      }
      horizon.terminal_count += row.terminal ? 1 : 0;
      horizon.completed_count += row.completed ? 1 : 0;
      horizon.failed_count += row.failed ? 1 : 0;
      horizon.bags.push_back(row);
    }
    horizon.all_terminal =
        horizon.terminal_count ==
        static_cast<int>(horizon.bags.size());
    horizon.all_completed =
        horizon.completed_count ==
        static_cast<int>(horizon.bags.size());
    horizon.validate();
    return horizon;
  }

  [[nodiscard]] G4IRSF14CausalHorizonStopState
  causal_horizon_stop_state(
      G4IRSF14CloneHorizon horizon,
      const std::vector<int>& selected_runtime_bag_ids,
      int merge_node,
      std::uint64_t start_event_count,
      std::uint64_t max_local_event_count) const {
    G4IRSF14CausalHorizonStopState state;
    state.horizon = horizon;
    state.cohort =
        causal_horizon_state(selected_runtime_bag_ids);
    const std::uint64_t current_event_count =
        result_.summary.event_count < 0
            ? 0U
            : static_cast<std::uint64_t>(
                  result_.summary.event_count);
    if (start_event_count > current_event_count) {
      throw std::invalid_argument(
          "causal horizon start event exceeds current event count");
    }
    state.elapsed_event_count =
        current_event_count - start_event_count;

    const bool runtime_stopped =
        runtime_phase_ ==
            EventDrivenJunctionRuntimePhase::kStopped ||
        runtime_phase_ ==
            EventDrivenJunctionRuntimePhase::kFinalized;
    if (horizon == G4IRSF14CloneHorizon::kLocal) {
      if (max_local_event_count == 0U) {
        throw std::invalid_argument(
            "H_local requires a positive bounded event count");
      }
      if (merge_node >= 0) {
        const auto controller =
            destination_merge_controllers_.find(merge_node);
        state.merge_pending_request_count =
            controller ==
                    destination_merge_controllers_.end()
                ? 0
                : static_cast<int>(
                      controller->second.pending_count());
      }
      if (state.merge_pending_request_count == 0) {
        state.should_stop = true;
        state.horizon_complete = true;
        state.stop_reason =
            "H_LOCAL_MERGE_QUEUE_EMPTY";
      } else if (state.elapsed_event_count >=
                 max_local_event_count) {
        state.should_stop = true;
        state.horizon_complete = true;
        state.stop_reason =
            "H_LOCAL_BOUNDED_EVENT_COUNT_REACHED";
      } else if (runtime_stopped) {
        state.should_stop = true;
        state.blocked = true;
        state.stop_reason =
            "H_LOCAL_RUNTIME_STOPPED_BEFORE_BOUND";
      }
    } else if (state.cohort.all_completed) {
      state.should_stop = true;
      state.horizon_complete = true;
      state.stop_reason =
          horizon ==
                  G4IRSF14CloneHorizon::kAffectedBag
              ? "H_BAG_ALL_AFFECTED_COMPLETED"
              : "H_SYSTEM_SELECTED_COHORT_COMPLETED";
    } else if (state.cohort.failed_count > 0) {
      state.should_stop = true;
      state.blocked = true;
      state.stop_reason =
          horizon ==
                  G4IRSF14CloneHorizon::kAffectedBag
              ? "H_BAG_AFFECTED_BAG_FAILED"
              : "H_SYSTEM_SELECTED_COHORT_BAG_FAILED";
    } else if (runtime_stopped) {
      state.should_stop = true;
      state.blocked = true;
      state.stop_reason =
          horizon ==
                  G4IRSF14CloneHorizon::kAffectedBag
              ? "H_BAG_RUNTIME_STOPPED_BEFORE_COMPLETION"
              : "H_SYSTEM_RUNTIME_STOPPED_BEFORE_COMPLETION";
    }
    state.validate();
    return state;
  }

  void drain() {
    while (process_one_event()) {
    }
  }

  const EventDrivenJunctionResult& finalize() {
    if (runtime_phase_ == EventDrivenJunctionRuntimePhase::kFinalized) {
      return result_;
    }
    if (runtime_phase_ == EventDrivenJunctionRuntimePhase::kIdle) {
      throw std::logic_error(
          "event runtime finalize called before initialize");
    }
    if (runtime_phase_ == EventDrivenJunctionRuntimePhase::kReady) {
      throw std::logic_error(
          "event runtime finalize requires drain or a hard runtime limit");
    }
    require_checkpoint_safe_boundary();
    active_backlog_at_runtime_stop_ = active_bag_count_;
    finalize_incomplete();
    build_bag_results();
    build_junction_results();
    build_credit_results();
    finish_summary();
    const std::chrono::duration<double> runtime_elapsed =
        std::chrono::steady_clock::now() - runtime_started_;
    result_.summary.runtime_seconds = runtime_elapsed.count();
    result_.summary.event_throughput_per_second =
        runtime_elapsed.count() > 0.0
            ? static_cast<double>(result_.summary.event_count) /
                  runtime_elapsed.count()
            : 0.0;
    runtime_phase_ = EventDrivenJunctionRuntimePhase::kFinalized;
    return result_;
  }

  EventDrivenJunctionResult run(
      const std::vector<EventRuntimeBagRequest>& requests,
      const std::vector<EventRuntimeFaultWindow>& fault_windows = {}) {
    initialize(requests, fault_windows);
    drain();
    return finalize();
  }

  [[nodiscard]] EventDrivenJunctionRuntimePhase phase() const noexcept {
    return runtime_phase_;
  }

  [[nodiscard]] const EventDrivenJunctionResult& current_result() const
      noexcept {
    return result_;
  }

  [[nodiscard]] G4IRSF15CausalBagOutcome
  g4irsf15_causal_bag_outcome(int runtime_bag_id) const {
    G4IRSF15CausalBagOutcome row;
    row.runtime_bag_id = runtime_bag_id;
    const auto found = bags_.find(runtime_bag_id);
    if (found == bags_.end()) {
      return row;
    }
    const auto& bag = found->second;
    row.known = true;
    row.task_id = bag.request.task_id;
    row.segment_id = bag.request.segment_id;
    row.start = bag.request.start;
    row.goal = bag.request.goal;
    row.current_node = bag.current;
    row.completed = bag.status == BagStatus::kCompleted;
    row.failed = bag.status == BagStatus::kFailed;
    row.release_time = bag.request.release_time;
    row.deadline = bag.request.deadline;
    row.admitted_time = bag.admitted_time;
    row.finish_time = bag.finish_time;
    row.source_wait_seconds =
        bag.admitted_time >= 0.0
            ? std::max(0.0,
                       bag.admitted_time - bag.request.release_time)
            : std::max(0.0, now_ - bag.request.release_time);
    row.total_local_wait_seconds = bag.total_wait;
    row.junction_wait_seconds =
        bag.junction_queue_wait_seconds;
    if (uses_destination_merge_grants() &&
        g4irsf14_state_ != nullptr) {
      const auto merge =
          g4irsf14_state_->destination_merge_bags.find(
              runtime_bag_id);
      if (merge !=
          g4irsf14_state_->destination_merge_bags.end()) {
        row.merge_wait_seconds =
            merge->second.grant_wait_seconds;
      }
    }
    row.edge_travel_seconds =
        bag.edge_travel_time_seconds;
    row.node_service_seconds =
        bag.node_service_time_seconds;
    row.loop_extra_seconds =
        bag.loop_extra_time_seconds;
    row.completion_seconds =
        bag.goal_completion_time_seconds;
    row.decision_count = bag.decision_count;
    row.retry_count = bag.retry_count;
    row.loop_count = bag.loop_count;
    row.failure_reason = bag.failure_reason;
    switch (bag.status) {
      case BagStatus::kPendingRelease:
        row.status = "PENDING_RELEASE";
        break;
      case BagStatus::kSourceQueue:
        row.status = "SOURCE_QUEUE";
        break;
      case BagStatus::kInService:
        row.status = "IN_SERVICE";
        break;
      case BagStatus::kJunctionQueue:
        row.status = "JUNCTION_QUEUE";
        break;
      case BagStatus::kInTransit:
        row.status = "IN_TRANSIT";
        break;
      case BagStatus::kCompleted:
        row.status = "COMPLETED";
        break;
      case BagStatus::kFailed:
        row.status = "FAILED";
        break;
    }
    return row;
  }

  [[nodiscard]] G4IRSF15LocalActionSnapshot
  g4irsf15_local_action_snapshot(int runtime_bag_id) const {
    G4IRSF15LocalActionSnapshot row;
    row.runtime_bag_id = runtime_bag_id;
    const auto found = bags_.find(runtime_bag_id);
    if (found == bags_.end()) {
      return row;
    }
    const auto& bag = found->second;
    row.known = true;
    row.current_node = bag.current;
    row.transit_from = bag.transit_from;
    row.transit_to = bag.transit_to;
    row.admitted_time = bag.admitted_time;
    row.decision_count = bag.decision_count;
    row.retry_count = bag.retry_count;
    switch (bag.status) {
      case BagStatus::kPendingRelease:
        row.status = "PENDING_RELEASE";
        break;
      case BagStatus::kSourceQueue:
        row.status = "SOURCE_QUEUE";
        break;
      case BagStatus::kInService:
        row.status = "IN_SERVICE";
        break;
      case BagStatus::kJunctionQueue:
        row.status = "JUNCTION_QUEUE";
        break;
      case BagStatus::kInTransit:
        row.status = "IN_TRANSIT";
        break;
      case BagStatus::kCompleted:
        row.status = "COMPLETED";
        break;
      case BagStatus::kFailed:
        row.status = "FAILED";
        break;
    }
    const auto controller = junctions_.find(bag.current);
    if (controller != junctions_.end()) {
      row.queued_at_current_node =
          std::find(controller->second.queue.begin(),
                    controller->second.queue.end(),
                    runtime_bag_id) !=
          controller->second.queue.end();
      row.source_queued_at_current_node =
          std::find(controller->second.source_queue.begin(),
                    controller->second.source_queue.end(),
                    runtime_bag_id) !=
          controller->second.source_queue.end();
      row.junction_wakeup_pending =
          controller->second.junction_wakeup_pending;
      row.junction_wakeup_generation =
          controller->second.junction_wakeup_generation;
    }
    if (g4irsf14_state_ != nullptr) {
      const auto local =
          g4irsf14_state_->local.find(bag.current);
      if (local != g4irsf14_state_->local.end() &&
          std::isfinite(local->second.junction_wakeup_time)) {
        row.junction_wakeup_time =
            local->second.junction_wakeup_time;
      }
      const auto merge =
          g4irsf14_state_->destination_merge_bags.find(
              runtime_bag_id);
      if (merge !=
          g4irsf14_state_->destination_merge_bags.end()) {
        row.pending_merge_request_id =
            merge->second.pending_request_id;
        row.pending_merge_lineage =
            merge->second.pending_lineage;
        const auto pending =
            pending_merge_dispatches_.find(
                merge->second.pending_request_id);
        if (pending != pending_merge_dispatches_.end()) {
          row.pending_merge_upstream =
              pending->second.upstream_node;
          row.pending_merge_destination =
              pending->second.destination_node;
        }
      }
    }
    return row;
  }

#ifdef CZR005_EVENT_RUNTIME_TESTING
  void test_mutate_final_result_hash_field(
      std::string_view family) {
    if (runtime_phase_ !=
        EventDrivenJunctionRuntimePhase::kFinalized) {
      throw std::logic_error(
          "result-hash mutation hook requires finalized runtime");
    }
    if (family == "summary") {
      ++result_.summary.source_admission_attempt_count;
    } else if (family == "decision") {
      if (result_.decisions.empty()) {
        result_.decisions.emplace_back();
      }
      result_.decisions.front().scorer_risk_reasons.push_back(
          "hash-coverage");
    } else if (family == "fault") {
      if (result_.fault_events.empty()) {
        result_.fault_events.emplace_back();
      }
      result_.fault_events.front().segment_id += "x";
    } else if (family == "pibt") {
      if (result_.pibt_events.empty()) {
        result_.pibt_events.emplace_back();
      }
      ++result_.pibt_events.front()
            .transaction_action_delta_count;
    } else if (family == "source_opportunity") {
      if (result_.source_admission_opportunities.empty()) {
        result_.source_admission_opportunities.emplace_back();
      }
      ++result_.source_admission_opportunities.front()
            .priority_comparison_count;
    } else if (family == "junction_opportunity") {
      if (result_.junction_arbitration_opportunities.empty()) {
        result_.junction_arbitration_opportunities.emplace_back();
      }
      ++result_.junction_arbitration_opportunities.front()
            .same_time_pending_arrivals;
    } else if (family == "merge_visibility") {
      if (result_.merge_request_visibility.empty()) {
        result_.merge_request_visibility.emplace_back();
      }
      result_.merge_request_visibility.front()
          .later_same_time_competitor_exists =
          !result_.merge_request_visibility.front()
               .later_same_time_competitor_exists;
    } else if (family == "event_seq") {
      if (result_.event_seq_ordering_audit.empty()) {
        result_.event_seq_ordering_audit.emplace_back();
      }
      result_.event_seq_ordering_audit.front().reason += "x";
    } else if (family == "arbitration_batch") {
      if (result_.arbitration_batch_cardinality.empty()) {
        result_.arbitration_batch_cardinality.emplace_back();
      }
      ++result_.arbitration_batch_cardinality.front()
            .pending_same_time_event_count;
    } else if (family == "merge_lifecycle") {
      if (result_.merge_grant_lifecycle.empty()) {
        result_.merge_grant_lifecycle.emplace_back();
      }
      result_.merge_grant_lifecycle.front().wait_age += 1.0;
    } else {
      throw std::invalid_argument(
          "unknown deterministic-result hash family");
    }
  }
#endif

  [[nodiscard]] StateCheckpoint capture_state_checkpoint() const;
  void restore_state_checkpoint(const StateCheckpoint& checkpoint);
  [[nodiscard]] G4IRSF14RuntimeStateDigests
  deterministic_state_digests() const;
  [[nodiscard]] std::string deterministic_state_sha256() const;
  [[nodiscard]] G4IRSF14CloneReplayHashes
  deterministic_replay_hashes() const;

 private:
  using BagState = event_runtime_detail::BagState;
  using BagStatus = event_runtime_detail::BagStatus;
  using CalendarInterval = event_runtime_detail::CalendarInterval;
  using JunctionState = event_runtime_detail::JunctionState;
  using LocalCalendar = event_runtime_detail::LocalCalendar;
  using RuntimeEvent = event_runtime_detail::RuntimeEvent;

  struct ActiveCausalStep {
    G4IRSF14CausalStepResult* result = nullptr;
    G4IRSF15CausalSkeletonStepResult* skeleton_result =
        nullptr;
    const G4IRSF14CausalInterventionDirective* directive =
        nullptr;
    RuntimeEvent prepop_event;
    G4IRSF14RuntimeStateDigests prepop_state;
    std::string prepop_state_sha256;
  };

  void require_g4irsf14_causal_frozen_tuple() const {
    if (canonical_resource_semantics() !=
            "R3_java_node_window_compatible" ||
        canonical_scorer_mode() != "S1" ||
        canonical_pibt_mode() != BoundedLocalPIBTMode::kP2 ||
        canonical_pressure_mode() != "C0_off" ||
        canonical_priority_mode() !=
            BoundedLocalPIBTPriorityMode::kQ0Current ||
         canonical_event_semantics() !=
             "E4_batch_plus_destination_merge_request" ||
        canonical_merge_grant_timing_mode() !=
            DestinationMergeGrantTimingMode::kEager ||
        canonical_merge_grant_rule() !=
            DestinationMergeGrantRule::kM0EarliestKnown ||
        canonical_admission_mode() != "off") {
      throw std::logic_error(
          "Stage 14E causal intervention requires frozen "
          "R3/S1/P2/C0/Q0/E4/M0");
    }
  }

  G4IRSF15CausalSkeletonStepResult
  process_one_event_causal_skeleton_impl() {
    require_g4irsf14_causal_frozen_tuple();
    if (active_causal_step_ != nullptr) {
      throw std::logic_error(
          "nested G4IRSF15 causal skeleton processing is forbidden");
    }
    if (runtime_phase_ != EventDrivenJunctionRuntimePhase::kReady ||
        events_.empty()) {
      throw std::logic_error(
          "causal skeleton probe requires a live queue-top pre-pop event");
    }
    require_checkpoint_safe_boundary();

    G4IRSF15CausalSkeletonStepResult result;
    result.prepop = g4irsf15_causal_prepop_strata();
    const auto pibt_prefilter_before =
        result_.summary.g4irsf14_i5_prefilter_candidate_count;
    ActiveCausalStep frame;
    frame.skeleton_result = &result;
    frame.prepop_event = events_.top();
    active_causal_step_ = &frame;
    try {
      result.event_processed = process_one_event();
    } catch (...) {
      active_causal_step_ = nullptr;
      throw;
    }
    active_causal_step_ = nullptr;
    result.pibt_prefilter_candidate_event =
        result_.summary.g4irsf14_i5_prefilter_candidate_count >
        pibt_prefilter_before;
    if (!result.event_processed) {
      if (!result_.summary.event_limit_reached &&
          !result_.summary.time_limit_reached) {
        throw std::logic_error(
            "causal skeleton probe stopped without a hard runtime limit");
      }
      result.application_reason =
          "SKELETON_PROBE_SKIPPED_RUNTIME_LIMIT";
    }
    result.validate();
    return result;
  }

  G4IRSF14CausalStepResult process_one_event_causal_impl(
      const G4IRSF14CausalInterventionDirective* directive) {
    require_g4irsf14_causal_frozen_tuple();
    if (active_causal_step_ != nullptr) {
      throw std::logic_error(
          "nested G4IRSF14 causal event processing is forbidden");
    }
    if (runtime_phase_ != EventDrivenJunctionRuntimePhase::kReady ||
        events_.empty()) {
      throw std::logic_error(
          "causal intervention requires a live queue-top pre-pop event");
    }
    require_checkpoint_safe_boundary();

    G4IRSF14CausalStepResult result;
    result.treatment_requested = directive != nullptr;
    const auto state = deterministic_state_digests();
    const auto state_sha256 = state.aggregate_sha256();
    result.source_state_sha256 = state_sha256;
    if (directive != nullptr) {
      directive->validate();
      result.requested_boundary_sha256 =
          directive->boundary.boundary_sha256();
      result.requested_intervention_sha256 =
          directive->intervention.intervention_sha256(
              directive->boundary);
      const auto& target = directive->boundary;
      const auto& next = events_.top();
      if (target.runtime_state_sha256 != state_sha256 ||
          target.event_seq != next.seq ||
          !event_runtime_detail::same_timestamp(
              target.time, next.time) ||
          target.node != next.node) {
        throw std::invalid_argument(
            "causal directive does not address the current queue-top "
            "pre-pop state");
      }
    }

    ActiveCausalStep frame;
    frame.result = &result;
    frame.directive = directive;
    frame.prepop_event = events_.top();
    frame.prepop_state = state;
    frame.prepop_state_sha256 = state_sha256;
    active_causal_step_ = &frame;
    try {
      result.event_processed = process_one_event();
    } catch (...) {
      active_causal_step_ = nullptr;
      throw;
    }
    active_causal_step_ = nullptr;

    if (directive == nullptr) {
      result.application_reason =
          "PROBE_ONLY_NO_ACTION_CHANGED";
    } else if (!result.intervention_applied) {
      result.application_reason =
          result.target_opportunity_observed
              ? "NOT_APPLICABLE_ACTION_PRECONDITION_FAILED"
              : "NOT_APPLICABLE_CONTENT_ADDRESSED_OPPORTUNITY_NOT_OBSERVED";
    }
    result.validate();
    return result;
  }

  G4IRSF14CloneBoundary seal_causal_boundary(
      G4IRSF14CloneBoundary boundary) const {
    if (active_causal_step_ == nullptr) {
      throw std::logic_error(
          "causal boundary observed outside an active event step");
    }
    boundary.time =
        active_causal_step_->prepop_event.time;
    boundary.event_seq =
        active_causal_step_->prepop_event.seq;
    boundary.state =
        active_causal_step_->prepop_state;
    boundary.runtime_state_sha256 =
        active_causal_step_->prepop_state_sha256;
    boundary.queue_top_not_popped = true;
    boundary.staged_event_sink_empty = true;
    boundary.runtime_global_scan_count = 0;
    boundary.runtime_future_route_read_count = 0;
    boundary.runtime_future_schedule_read_count = 0;
    boundary.reservation_depth = 1;
    boundary.max_selected_edges_per_bag = 1;
    boundary.clone_group_id =
        boundary.expected_clone_group_id();
    boundary.validate();
    return boundary;
  }

  const G4IRSF14CloneIntervention*
  observe_causal_boundary(
      G4IRSF14CloneBoundary boundary) {
    if (active_causal_step_ == nullptr) {
      return nullptr;
    }
    if (active_causal_step_->skeleton_result != nullptr) {
      if (boundary.kind !=
              G4IRSF14CloneBoundaryKind::kSourceArbitration &&
          boundary.kind !=
              G4IRSF14CloneBoundaryKind::kJunctionRouteArbitration &&
          boundary.kind !=
              G4IRSF14CloneBoundaryKind::kHoldReleaseOpportunity) {
        return nullptr;
      }
      G4IRSF15CausalOpportunitySkeleton skeleton;
      skeleton.kind = boundary.kind;
      skeleton.time =
          active_causal_step_->prepop_event.time;
      skeleton.event_seq =
          active_causal_step_->prepop_event.seq;
      skeleton.node = boundary.node;
      skeleton.runtime_bag_id = boundary.runtime_bag_id;
      skeleton.baseline_next_node =
          boundary.baseline_next_node;
      skeleton.baseline_release =
          boundary.baseline_release;
      skeleton.source_ready_order =
          std::move(boundary.source_ready_order);
      skeleton.g4irsf17_i1_observation_available =
          boundary.g4irsf17_i1_observation_available;
      skeleton.g4irsf17_i1_observation_peer_runtime_bag_id =
          boundary.g4irsf17_i1_observation_peer_runtime_bag_id;
      skeleton.g4irsf17_i1_baseline_observation =
          boundary.g4irsf17_i1_baseline_observation;
      skeleton.g4irsf17_i1_treatment_observation =
          boundary.g4irsf17_i1_treatment_observation;
      skeleton.g4irsf17_i1_pairwise_features =
          boundary.g4irsf17_i1_pairwise_features;
      skeleton.legal_next_edges =
          std::move(boundary.legal_next_edges);
      active_causal_step_->skeleton_result
          ->observed_opportunities.push_back(
              std::move(skeleton));
      return nullptr;
    }
    boundary = seal_causal_boundary(
        std::move(boundary));
    auto& result = *active_causal_step_->result;
    const std::string boundary_sha256 =
        boundary.boundary_sha256();
    result.observed_opportunities.push_back(boundary);
    if (active_causal_step_->directive == nullptr ||
        result.intervention_applied ||
        boundary_sha256 !=
            result.requested_boundary_sha256) {
      return nullptr;
    }
    result.target_opportunity_observed = true;
    return &active_causal_step_->directive->intervention;
  }

  void mark_causal_action_applied(
      std::string reason,
      std::vector<int> affected_runtime_bag_ids) {
    if (active_causal_step_ == nullptr ||
        active_causal_step_->directive == nullptr) {
      throw std::logic_error(
          "causal action applied without a treatment directive");
    }
    auto& result = *active_causal_step_->result;
    if (result.intervention_applied ||
        result.changed_action_count != 0) {
      throw std::logic_error(
          "content-addressed causal directive is not one-shot");
    }
    result.intervention_applied = true;
    result.changed_action_count = 1;
    result.application_reason = std::move(reason);
    std::sort(affected_runtime_bag_ids.begin(),
              affected_runtime_bag_ids.end());
    affected_runtime_bag_ids.erase(
        std::unique(affected_runtime_bag_ids.begin(),
                    affected_runtime_bag_ids.end()),
        affected_runtime_bag_ids.end());
    result.affected_runtime_bag_ids =
        std::move(affected_runtime_bag_ids);
  }

  class StateFingerprintWriter {
   public:
    explicit StateFingerprintWriter(std::string_view component) {
      string("czr005.g4irsf14.runtime-state-component.v2");
      string(component);
    }

    void boolean(bool value) {
      payload_.push_back(value ? '\x01' : '\x00');
    }

    void u64(std::uint64_t value) {
      for (int shift = 56; shift >= 0; shift -= 8) {
        payload_.push_back(
            static_cast<char>((value >> shift) & 0xffU));
      }
    }

    void i64(std::int64_t value) {
      u64(static_cast<std::uint64_t>(value));
    }

    void floating(double value) {
      static_assert(sizeof(double) == sizeof(std::uint64_t));
      std::uint64_t bits = 0;
      std::memcpy(&bits, &value, sizeof(bits));
      u64(bits);
    }

    void string(std::string_view value) {
      u64(static_cast<std::uint64_t>(value.size()));
      payload_.append(value);
    }

    [[nodiscard]] std::string sha256() const {
      return canonical_map2_detail::sha256_hex(payload_);
    }

   private:
    std::string payload_;
  };

  void require_checkpoint_safe_boundary() const {
    if (staged_event_sink_ != nullptr ||
        staged_merge_visibility_sink_ != nullptr ||
        staged_destination_known_competitor_counts_ != nullptr) {
      throw std::logic_error(
          "runtime checkpoint requires an empty transactional event sink");
    }
  }

  static void fingerprint_event(
      StateFingerprintWriter& writer,
      const RuntimeEvent& event) {
    writer.i64(static_cast<int>(event.type));
    writer.floating(event.time);
    writer.u64(event.seq);
    writer.i64(event.task_id);
    writer.i64(event.node);
    writer.i64(event.from_node);
    writer.i64(event.to_node);
    writer.floating(event.service_end);
    writer.floating(event.message_delay);
    writer.i64(event.message_generation);
    writer.u64(event.wakeup_generation);
    writer.boolean(event.notification);
    writer.boolean(event.drop_notification);
    writer.boolean(event.retry);
    writer.string(event.reason);
    writer.i64(event.microphase_priority);
  }

  static void fingerprint_request(
      StateFingerprintWriter& writer,
      const EventRuntimeBagRequest& request) {
    writer.string(request.segment_id);
    writer.i64(request.task_id);
    writer.floating(request.release_time);
    writer.floating(request.deadline);
    writer.i64(request.start);
    writer.i64(request.goal);
    writer.string(request.source);
    writer.i64(request.runtime_bag_id);
  }

  static void fingerprint_merge_request(
      StateFingerprintWriter& writer,
      const DestinationMergeRequest& request,
      bool include_identity_snapshot = true) {
    writer.u64(request.request_id);
    writer.u64(request.lineage);
    writer.u64(request.request_generation);
    writer.u64(request.junction_queue_generation);
    writer.i64(request.runtime_bag_id);
    writer.i64(request.task_id);
    writer.string(request.segment_id);
    writer.i64(request.upstream_node);
    writer.i64(request.destination_merge_node);
    writer.i64(request.requested_directed_edge.from_node);
    writer.i64(request.requested_directed_edge.to_node);
    writer.floating(request.request_time);
    writer.floating(request.fifo_request_time);
    writer.floating(request.earliest_edge_entry);
    writer.floating(request.exact_edge_travel_seconds);
    writer.floating(request.projected_arrival);
    writer.i64(request.goal);
    writer.floating(request.route_score);
    writer.floating(request.static_remaining);
    writer.floating(request.destination_service_seconds);
    writer.i64(request.downstream_queue_pressure);
    writer.floating(request.deadline_slack);
    writer.floating(request.wait_age);
    writer.i64(request.task_class_code);
    writer.i64(request.task_class);
    writer.boolean(request.storage_leg);
    writer.floating(request.source_release_age);
    writer.floating(request.local_queue_age);
    writer.i64(request.advertised_fault_generation);
    writer.i64(request.physical_fault_generation);
    writer.u64(request.destination_calendar_generation);
    writer.u64(request.enqueue_sequence);
    writer.floating(request.expiry);
    writer.boolean(request.lifecycle_segment_id != nullptr);
    if (request.lifecycle_segment_id != nullptr) {
      writer.string(*request.lifecycle_segment_id);
    }
    writer.boolean(
        request.lifecycle_request_snapshot != nullptr);
    if (include_identity_snapshot &&
        request.lifecycle_request_snapshot != nullptr) {
      fingerprint_merge_request(
          writer, *request.lifecycle_request_snapshot, false);
    }
  }

  static void fingerprint_capability(
      StateFingerprintWriter& writer,
      const MergeGrantCapabilityCheckpoint& capability) {
    writer.u64(capability.grant_id);
    writer.u64(capability.request_id);
    writer.u64(capability.lineage);
    writer.u64(capability.request_generation);
    writer.i64(capability.owner_runtime_bag_id);
    writer.i64(capability.exact_directed_edge.from_node);
    writer.i64(capability.exact_directed_edge.to_node);
    writer.i64(capability.destination_node);
    writer.floating(capability.slot_start);
    writer.floating(capability.slot_end);
    writer.floating(capability.issue_time);
    writer.floating(capability.request_time);
    writer.floating(capability.expiry);
    writer.u64(capability.calendar_generation);
    writer.i64(capability.fault_generation);
    writer.i64(capability.advertised_fault_generation);
    writer.i64(static_cast<int>(capability.state));
    fingerprint_merge_request(writer, capability.request_snapshot);
  }

  static void fingerprint_deterministic_summary(
      StateFingerprintWriter& writer,
      const EventRuntimeSummary& summary);

  G4IRSF14RuntimeStateDigests compute_runtime_state_digests() const;
  G4IRSF14CloneReplayHashes
  compute_replay_hashes_projection() const;
  static event_runtime_detail::G4IRSF14RuntimeStateCheckpoint
  capture_g4irsf14_state(
      const event_runtime_detail::G4IRSF14RuntimeState& state);
  static std::unique_ptr<
      event_runtime_detail::G4IRSF14RuntimeState>
  restore_g4irsf14_state(
      const event_runtime_detail::G4IRSF14RuntimeStateCheckpoint&
          checkpoint);
  void validate_merge_capability_bijection() const;

  static bool mode_is(const std::string& actual,
                      const std::string& short_name,
                      const std::string& full_name) {
    return actual == short_name || actual == full_name;
  }

  std::string canonical_g4irsf16_supervisor_mode() const {
    if (config_.g4irsf16_supervisor_mode == "off") {
      return "off";
    }
    if (config_.g4irsf16_supervisor_mode == "shadow") {
      return "shadow";
    }
    if (config_.g4irsf16_supervisor_mode == "closed_loop") {
      return "closed_loop";
    }
    throw std::invalid_argument(
        "g4irsf16_supervisor_mode must be off, shadow, or closed_loop");
  }

  bool g4irsf16_enabled() const {
    return canonical_g4irsf16_supervisor_mode() != "off";
  }

  bool g4irsf16_closed_loop() const {
    return canonical_g4irsf16_supervisor_mode() == "closed_loop";
  }

  bool g4irsf17_source_policy_enabled() const noexcept {
    return config_.g4irsf17_source_policy.enabled();
  }

  bool g4irsf17_extensions_enabled() const noexcept {
    return config_.enable_g4irsf17_source_wait_telemetry ||
           g4irsf17_source_policy_enabled() ||
           config_.enable_g4irsf17_causal_source_features;
  }

  bool g4irsf16_uses_diagnostic_rule() const noexcept {
    return config_.g4irsf16_i4_diagnostic_rule.configured();
  }

  G4IRSF16SupervisorConfig g4irsf16_supervisor_config() const {
    G4IRSF16SupervisorConfig supervisor;
    if (!g4irsf16_uses_diagnostic_rule()) {
      supervisor.i3_min_confidence =
          config_.g4irsf16_i3_model.benefit_probability_lcb_threshold;
      supervisor.i3_max_risk =
          config_.g4irsf16_i3_model.harmful_probability_ucb_budget;
      supervisor.i4_min_confidence =
          config_.g4irsf16_i4_model.benefit_probability_lcb_threshold;
      supervisor.i4_max_risk =
          config_.g4irsf16_i4_model.harmful_probability_ucb_budget;
    }
    supervisor.validate();
    return supervisor;
  }

  std::string canonical_event_semantics() const {
    if (mode_is(config_.event_semantics,
                "E0",
                "E0_immediate_dispatch_f2")) {
      return "E0_immediate_dispatch_f2";
    }
    if (mode_is(config_.event_semantics,
                "E1",
                "E1_batch_source_same_timestamp")) {
      return "E1_batch_source_same_timestamp";
    }
    if (mode_is(config_.event_semantics,
                "E2",
                "E2_batch_junction_same_timestamp")) {
      return "E2_batch_junction_same_timestamp";
    }
    if (mode_is(config_.event_semantics,
                "E3",
                "E3_batch_source_and_junction_same_timestamp")) {
      return "E3_batch_source_and_junction_same_timestamp";
    }
    if (mode_is(config_.event_semantics,
                "E4",
                "E4_batch_plus_destination_merge_request")) {
      return "E4_batch_plus_destination_merge_request";
    }
    throw std::invalid_argument(
        "event_semantics must be E0, E1, E2, E3, or E4");
  }

  bool batches_source_same_timestamp() const {
    const auto mode = canonical_event_semantics();
    return mode == "E1_batch_source_same_timestamp" ||
           mode == "E3_batch_source_and_junction_same_timestamp" ||
           mode == "E4_batch_plus_destination_merge_request";
  }

  bool batches_junction_same_timestamp() const {
    const auto mode = canonical_event_semantics();
    return mode == "E2_batch_junction_same_timestamp" ||
           mode == "E3_batch_source_and_junction_same_timestamp" ||
           mode == "E4_batch_plus_destination_merge_request";
  }

  bool uses_destination_merge_grants() const {
    return canonical_event_semantics() ==
           "E4_batch_plus_destination_merge_request";
  }

  bool g4irsf18_merge_policy_enabled() const noexcept {
    return config_.g4irsf18_merge_policy.enabled();
  }

  DestinationMergeGrantTimingMode
  canonical_merge_grant_timing_mode() const {
    if (config_.merge_grant_timing_mode == "eager" ||
        config_.merge_grant_timing_mode == "J0" ||
        config_.merge_grant_timing_mode == "J0_F2_EAGER") {
      return DestinationMergeGrantTimingMode::kEager;
    }
    if (config_.merge_grant_timing_mode == "jit_fifo" ||
        config_.merge_grant_timing_mode == "J1" ||
        config_.merge_grant_timing_mode == "J1_F2_JIT_FIFO") {
      return DestinationMergeGrantTimingMode::kJitFifo;
    }
    if (config_.merge_grant_timing_mode ==
            "jit_fair_aging_deadline" ||
        config_.merge_grant_timing_mode == "J2" ||
        config_.merge_grant_timing_mode ==
            "J2_F2_JIT_FAIR_AGING_DEADLINE") {
      return DestinationMergeGrantTimingMode::
          kJitFairAgingDeadline;
    }
    throw std::invalid_argument(
        "merge_grant_timing_mode must be eager, jit_fifo, or "
        "jit_fair_aging_deadline");
  }

  bool uses_jit_destination_merge_grants() const {
    return uses_destination_merge_grants() &&
           canonical_merge_grant_timing_mode() !=
               DestinationMergeGrantTimingMode::kEager;
  }

  DestinationMergeGrantRule effective_merge_grant_rule() const {
    return destination_merge_grant_rule_for_timing(
        canonical_merge_grant_timing_mode(),
        canonical_merge_grant_rule());
  }

  DestinationMergeGrantRule canonical_merge_grant_rule() const {
    if (config_.merge_grant_rule == "M0" ||
        config_.merge_grant_rule ==
            "M0_current_event_seq_earliest_known") {
      return DestinationMergeGrantRule::kM0EarliestKnown;
    }
    if (config_.merge_grant_rule == "M1" ||
        config_.merge_grant_rule == "M1_fifo") {
      return DestinationMergeGrantRule::kM1Fifo;
    }
    if (config_.merge_grant_rule == "M2" ||
        config_.merge_grant_rule ==
            "M2_earliest_projected_arrival") {
      return DestinationMergeGrantRule::
          kM2EarliestProjectedArrival;
    }
    if (config_.merge_grant_rule == "M3" ||
        config_.merge_grant_rule ==
            "M3_deadline_aging") {
      return DestinationMergeGrantRule::kM3DeadlineAging;
    }
    if (config_.merge_grant_rule == "M4" ||
        config_.merge_grant_rule ==
            "M4_fairness_progress") {
      return DestinationMergeGrantRule::
          kM4FairnessProgress;
    }
    if (config_.merge_grant_rule == "M5" ||
        config_.merge_grant_rule ==
            "M5_local_externality") {
      return DestinationMergeGrantRule::kM5LocalExternality;
    }
    if (config_.merge_grant_rule == "M6" ||
        config_.merge_grant_rule ==
            "M6_thesis_local") {
      return DestinationMergeGrantRule::kM6ThesisLocal;
    }
    if (config_.merge_grant_rule == "M7") {
      throw std::invalid_argument(
          "merge_grant_rule M7 is diagnostic-only and cannot run online");
    }
    if (config_.merge_grant_rule == "M8" ||
        config_.merge_grant_rule == "M9") {
      throw std::invalid_argument(
          "merge_grant_rule M8/M9 require a validated model artifact; "
          "runtime selection fails closed");
    }
    throw std::invalid_argument(
        "merge_grant_rule must be M0..M9");
  }

  bool g4irsf14_extensions_enabled() const {
    return canonical_event_semantics() !=
               "E0_immediate_dispatch_f2" ||
           config_.enable_opportunity_telemetry;
  }

  std::string canonical_resource_semantics() const {
    if (mode_is(config_.resource_semantics,
                "R0",
                "R0_current_undirected_full_travel_exclusive")) {
      return "R0_current_undirected_full_travel_exclusive";
    }
    if (mode_is(config_.resource_semantics,
                "R1",
                "R1_directed_full_travel_exclusive")) {
      return "R1_directed_full_travel_exclusive";
    }
    if (mode_is(config_.resource_semantics,
                "R2",
                "R2_directed_entry_headway")) {
      return "R2_directed_entry_headway";
    }
    if (mode_is(config_.resource_semantics,
                "R3",
                "R3_java_node_window_compatible")) {
      return "R3_java_node_window_compatible";
    }
    if (mode_is(config_.resource_semantics,
                "R4",
                "R4_directed_headway_plus_merge_service_calendar")) {
      return "R4_directed_headway_plus_merge_service_calendar";
    }
    throw std::invalid_argument("unknown G4IRSF12 resource_semantics mode");
  }

  std::string canonical_pressure_mode() const {
    if (!config_.enable_backpressure) {
      return "C0_off";
    }
    if (config_.pressure_mode == "off" || config_.pressure_mode == "C0") {
      return "C0_off";
    }
    if (config_.pressure_mode == "absolute_downstream_queue_penalty" ||
        config_.pressure_mode == "C1") {
      return "C1_absolute_downstream_queue_penalty";
    }
    if (config_.pressure_mode == "goal_conditioned_differential" ||
        config_.pressure_mode == "C2") {
      return "C2_goal_conditioned_differential";
    }
    if (config_.pressure_mode == "distance_biased_differential" ||
        config_.pressure_mode == "C3") {
      return "C3_distance_biased_differential";
    }
    throw std::invalid_argument("unknown G4IRSF12 pressure_mode");
  }

  std::string canonical_admission_mode() const {
    if (config_.admission_mode != "off" &&
        config_.admission_mode != "legacy_unbound" &&
        config_.admission_mode != "expiring_first_edge_credit" &&
        config_.admission_mode != "merge_only_first_edge_credit" &&
        config_.admission_mode !=
            "contention_triggered_first_edge_credit") {
      throw std::invalid_argument("unknown event-runtime admission_mode");
    }
    // Preserve the historical boolean API: false always means the original
    // admission-off ablation, regardless of the otherwise valid mode string.
    if (!config_.enable_source_admission || config_.admission_mode == "off") {
      return "off";
    }
    return config_.admission_mode;
  }

  bool uses_first_edge_credit() const {
    const auto mode = canonical_admission_mode();
    return mode == "expiring_first_edge_credit" ||
           mode == "merge_only_first_edge_credit" ||
           mode == "contention_triggered_first_edge_credit";
  }

  std::string canonical_credit_mode() const {
    const auto mode = canonical_admission_mode();
    if (mode == "merge_only_first_edge_credit") {
      return "C7";
    }
    if (mode == "contention_triggered_first_edge_credit") {
      return "C8";
    }
    if (mode == "expiring_first_edge_credit") {
      return "C4_C5_C6";
    }
    return "C0";
  }

  BoundedLocalPIBTPriorityMode canonical_priority_mode() const {
    if (config_.priority_mode == "Q0" ||
        config_.priority_mode == "current_f2") {
      return BoundedLocalPIBTPriorityMode::kQ0Current;
    }
    if (config_.priority_mode == "Q1" ||
        config_.priority_mode == "thesis_exact_local_projection") {
      return BoundedLocalPIBTPriorityMode::kQ1ThesisLocalProjection;
    }
    if (config_.priority_mode == "Q2" ||
        config_.priority_mode == "thesis_type_slack_aging") {
      return BoundedLocalPIBTPriorityMode::kQ2TypeSlackAging;
    }
    if (config_.priority_mode == "Q3" ||
        config_.priority_mode == "fault_slack_age_stable_id") {
      return BoundedLocalPIBTPriorityMode::kQ3FaultSlackAgeStableId;
    }
    throw std::invalid_argument(
        "priority_mode must be one of Q0, Q1, Q2, Q3");
  }

  std::string canonical_priority_mode_name() const {
    switch (canonical_priority_mode()) {
      case BoundedLocalPIBTPriorityMode::kQ0Current:
        return "Q0";
      case BoundedLocalPIBTPriorityMode::kQ1ThesisLocalProjection:
        return "Q1";
      case BoundedLocalPIBTPriorityMode::kQ2TypeSlackAging:
        return "Q2";
      case BoundedLocalPIBTPriorityMode::kQ3FaultSlackAgeStableId:
        return "Q3";
    }
    throw std::invalid_argument("priority_mode must be Q0..Q3");
  }

  BoundedLocalPIBTPreferenceMode canonical_pibt_preference_mode() const {
    if (config_.pibt_preference_mode == "current") {
      return BoundedLocalPIBTPreferenceMode::kCurrent;
    }
    if (config_.pibt_preference_mode == "dodge") {
      return BoundedLocalPIBTPreferenceMode::kDodge;
    }
    if (config_.pibt_preference_mode == "local_regret") {
      return BoundedLocalPIBTPreferenceMode::kLocalRegret;
    }
    if (config_.pibt_preference_mode == "dodge_regret") {
      return BoundedLocalPIBTPreferenceMode::kDodgeRegret;
    }
    throw std::invalid_argument(
        "pibt_preference_mode must be current, dodge, local_regret, or "
        "dodge_regret");
  }

  std::string canonical_framework_mode() const {
    if (config_.framework_mode == "event_loop_one_step") {
      return "event_loop_one_step";
    }
    if (config_.framework_mode ==
            "legacy_order_one_step_diagnostic" ||
        config_.framework_mode ==
            "old_scheduling_order_reservation_horizon_one") {
      return "legacy_order_one_step_diagnostic";
    }
    throw std::invalid_argument(
        "framework_mode must be event_loop_one_step or "
        "legacy_order_one_step_diagnostic");
  }

  BoundedLocalPIBTMode canonical_pibt_mode() const {
    if (config_.pibt_mode == "P0") {
      return BoundedLocalPIBTMode::kP0;
    }
    if (config_.pibt_mode == "P1") {
      return BoundedLocalPIBTMode::kP1;
    }
    if (config_.pibt_mode == "P2") {
      return BoundedLocalPIBTMode::kP2;
    }
    if (config_.pibt_mode == "P3") {
      return BoundedLocalPIBTMode::kP3;
    }
    if (config_.pibt_mode == "P4") {
      return BoundedLocalPIBTMode::kP4;
    }
    throw std::invalid_argument("unknown G4IRSF12 pibt_mode; expected P0..P4");
  }

  std::string canonical_pibt_mode_name() const {
    return bounded_local_pibt_mode_name(canonical_pibt_mode());
  }

  std::string canonical_scorer_mode() const {
    if (config_.scorer_mode == "S0" ||
        config_.scorer_mode == "S0_current_handwritten" ||
        config_.scorer_mode ==
            "S0_current_handwritten_static_score") {
      return "S0";
    }
    if (mode_is(config_.scorer_mode,
                "S1",
                "S1_frozen_g4e_legal_local_adapter")) {
      return "S1";
    }
    if (mode_is(config_.scorer_mode,
                "S2",
                "S2_frozen_g4e_without_absolute_node_ids")) {
      return "S2";
    }
    if (mode_is(config_.scorer_mode,
                "S3",
                "S3_shortest_potential_only")) {
      return "S3";
    }
    if (mode_is(config_.scorer_mode,
                "S4",
                "S4_queue_aware_rule_only")) {
      return "S4";
    }
    throw std::invalid_argument(
        "unknown G4IRSF12 scorer_mode; expected S0..S4");
  }

  std::string canonical_scorer_id() const {
    const auto mode = canonical_scorer_mode();
    if (mode == "S0") {
      return "S0_current_handwritten_static_score";
    }
    if (mode == "S1") {
      return "S1_frozen_g4e_legal_local_adapter";
    }
    if (mode == "S2") {
      return "S2_frozen_g4e_without_absolute_node_ids";
    }
    if (mode == "S3") {
      return "S3_shortest_potential_only";
    }
    return "S4_queue_aware_rule_only";
  }

  static void scorer_fingerprint_u64(std::string& payload,
                                     std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
      payload.push_back(static_cast<char>(value >> shift));
    }
  }

  static void scorer_fingerprint_i64(std::string& payload,
                                     std::int64_t value) {
    scorer_fingerprint_u64(
        payload, static_cast<std::uint64_t>(value));
  }

  static void scorer_fingerprint_double(std::string& payload,
                                        double value) {
    static_assert(sizeof(double) == sizeof(std::uint64_t));
    std::uint64_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    scorer_fingerprint_u64(payload, bits);
  }

  std::string scorer_model_fingerprint() const {
    std::string payload =
        "czr005_g4irsf12_frozen_g4e_runtime_weights_v1";
    scorer_fingerprint_u64(payload, config_.scorer_w1.size());
    scorer_fingerprint_u64(payload, config_.scorer_b1.size());
    for (const auto& row : config_.scorer_w1) {
      scorer_fingerprint_u64(payload, row.size());
      for (const double value : row) {
        scorer_fingerprint_double(payload, value);
      }
    }
    for (const double value : config_.scorer_b1) {
      scorer_fingerprint_double(payload, value);
    }
    for (const double value : config_.scorer_w2) {
      scorer_fingerprint_double(payload, value);
    }
    scorer_fingerprint_double(payload, config_.scorer_b2);
    return canonical_map2_detail::sha256_hex(payload);
  }

  std::string scorer_graph_fingerprint() const {
    std::string payload =
        "czr005_g4irsf12_runtime_graph_v1";
    const auto nodes = graph_.node_locations();
    scorer_fingerprint_u64(payload, nodes.size());
    scorer_fingerprint_u64(payload, graph_.edge_count());
    for (const int location : nodes) {
      const auto& node = graph_.node(location);
      scorer_fingerprint_i64(payload, node.location);
      scorer_fingerprint_i64(payload, node.node_type);
      scorer_fingerprint_double(payload, node.service_time);
      scorer_fingerprint_i64(payload, node.x);
      scorer_fingerprint_i64(payload, node.y);
      std::vector<int> outgoing = node.outgoing;
      std::sort(outgoing.begin(), outgoing.end());
      scorer_fingerprint_u64(payload, outgoing.size());
      for (const int next : outgoing) {
        scorer_fingerprint_i64(payload, next);
        const auto& edge = graph_.edge(location, next);
        scorer_fingerprint_double(payload, edge.length);
        scorer_fingerprint_double(payload, edge.speed);
      }
    }
    for (const int start : nodes) {
      for (const int goal : nodes) {
        scorer_fingerprint_double(
            payload, graph_.heuristic(start, goal));
      }
    }
    return canonical_map2_detail::sha256_hex(payload);
  }

  void initialize_regret_prior() {
    for (const auto& record : config_.pibt_regret_prior_records) {
      const auto key =
          std::make_tuple(record.from_node,
                          record.to_node,
                          record.goal_node);
      if (!pibt_regret_prior_.emplace(key, record.penalty).second) {
        throw std::invalid_argument(
            "pibt_regret_prior_records must have unique from/to/goal keys");
      }
    }
  }

  void initialize_scorer() {
    const auto mode = canonical_scorer_mode();
    if (mode != "S1" && mode != "S2") {
      return;
    }
    scorer_model_.emplace(config_.scorer_w1,
                          config_.scorer_b1,
                          config_.scorer_w2,
                          config_.scorer_b2);

    std::map<int, std::vector<int>> reverse_edges;
    const auto nodes = graph_.node_locations();
    for (const int node : nodes) {
      reverse_edges.emplace(node, std::vector<int>{});
    }
    for (const int node : nodes) {
      for (const int next : graph_.outgoing(node)) {
        reverse_edges[next].push_back(node);
      }
    }
    for (const int goal : nodes) {
      std::map<int, int> distances;
      std::deque<int> pending;
      distances[goal] = 0;
      pending.push_back(goal);
      while (!pending.empty()) {
        const int node = pending.front();
        pending.pop_front();
        const int next_distance = distances.at(node) + 1;
        for (const int predecessor : reverse_edges.at(node)) {
          if (distances.emplace(predecessor, next_distance).second) {
            pending.push_back(predecessor);
          }
        }
      }
      for (const int node : nodes) {
        const auto found = distances.find(node);
        scorer_static_hops_[{node, goal}] =
            found == distances.end() ? 999 : found->second;
      }
    }
  }

  bool uses_corridor_calendar() const {
    return canonical_resource_semantics() != "R3_java_node_window_compatible";
  }

  bool uses_directed_corridor() const {
    return canonical_resource_semantics() !=
           "R0_current_undirected_full_travel_exclusive";
  }

  bool uses_entry_headway() const {
    const auto semantics = canonical_resource_semantics();
    return semantics == "R2_directed_entry_headway" ||
           semantics == "R4_directed_headway_plus_merge_service_calendar";
  }

  bool uses_destination_calendar(int node, int goal) const {
    const auto semantics = canonical_resource_semantics();
    if (semantics == "R3_java_node_window_compatible") {
      return node != goal;
    }
    if (semantics == "R4_directed_headway_plus_merge_service_calendar") {
      return graph_.incoming_degree(node) > 1;
    }
    return true;
  }

  long long resource_corridor_key(int start, int end) const {
    return uses_directed_corridor()
               ? event_runtime_detail::directed_key(start, end)
               : event_runtime_detail::corridor_key(start, end);
  }

  double corridor_reservation_duration(double travel_time) const {
    return uses_entry_headway()
               ? std::max(config_.entry_headway_seconds,
                          config_.minimum_service_seconds)
               : travel_time;
  }

  std::pair<int, double> goal_queue_state(const JunctionState& controller,
                                          int goal,
                                          double time) const {
    int count = 0;
    double max_wait = 0.0;
    for (const int runtime_bag_id : controller.queue) {
      const auto found = bags_.find(runtime_bag_id);
      if (found == bags_.end() || found->second.request.goal != goal) {
        continue;
      }
      ++count;
      max_wait = std::max(max_wait,
                          std::max(0.0, time - found->second.junction_enqueued_at));
    }
    return {count, max_wait};
  }

  void validate_config() const {
    if (config_.queue_discipline != "fifo" && config_.queue_discipline != "deadline" &&
        config_.queue_discipline != "aging") {
      throw std::invalid_argument("queue_discipline must be fifo, deadline, or aging");
    }
    (void)canonical_resource_semantics();
    (void)canonical_pressure_mode();
    (void)canonical_admission_mode();
    (void)canonical_pibt_mode();
    (void)canonical_priority_mode();
    (void)canonical_pibt_preference_mode();
    (void)canonical_framework_mode();
    (void)canonical_event_semantics();
    (void)canonical_merge_grant_timing_mode();
    (void)canonical_merge_grant_rule();
    config_.g4irsf18_merge_policy.validate_controls();
    if (g4irsf18_merge_policy_enabled() &&
        (!uses_destination_merge_grants() ||
         canonical_merge_grant_timing_mode() !=
             DestinationMergeGrantTimingMode::kJitFairAgingDeadline)) {
      throw std::invalid_argument(
          "G4IRSF18 learned merge policy requires E4 destination merge "
          "grants with jit_fair_aging_deadline (J2) timing");
    }
    if (g4irsf18_merge_policy_enabled() &&
        std::abs(config_.starvation_threshold - 120.0) > 1.0e-12) {
      throw std::invalid_argument(
          "G4IRSF18 J7 merge artifact requires the authoritative 120-second "
          "J2 starvation guard");
    }
    const auto g4irsf16_mode =
        canonical_g4irsf16_supervisor_mode();
    if (g4irsf16_mode == "off") {
      if (config_.g4irsf16_i3_model.configured() ||
          config_.g4irsf16_i4_model.configured() ||
          config_.g4irsf16_i3_model.authorized ||
          config_.g4irsf16_i4_model.authorized ||
          config_.g4irsf16_i4_diagnostic_rule.configured()) {
        throw std::invalid_argument(
            "G4IRSF16 model artifacts require shadow or closed_loop mode");
      }
    } else {
      if (g4irsf16_uses_diagnostic_rule()) {
        config_.g4irsf16_i4_diagnostic_rule.validate();
        if (config_.g4irsf16_i3_model.configured() ||
            config_.g4irsf16_i4_model.configured() ||
            config_.g4irsf16_i3_model.authorized ||
            config_.g4irsf16_i4_model.authorized) {
          throw std::invalid_argument(
              "G4IRSF16 diagnostic H5 and model artifacts are mutually exclusive");
        }
      } else {
        if (g4irsf16_mode == "closed_loop") {
          throw std::invalid_argument(
              "G4IRSF16 learned-model closed_loop is fail-closed: the "
              "offline promotion gate is NO_GO; use shadow or the exact "
              "diagnostic-only H5 bundle");
        }
        config_.g4irsf16_i3_model.validate();
        config_.g4irsf16_i4_model.validate();
        if (config_.g4irsf16_i3_model.kind != "I3" ||
            config_.g4irsf16_i4_model.kind != "I4") {
          throw std::invalid_argument(
              "G4IRSF16 I3/I4 artifacts are bound to the wrong hook");
        }
      }
      (void)g4irsf16_supervisor_config();
    }
    const auto scorer_mode = canonical_scorer_mode();
    if (!std::isfinite(config_.retry_interval) ||
        !std::isfinite(config_.minimum_service_seconds) ||
        !std::isfinite(config_.dispatch_headway_seconds) ||
        !std::isfinite(config_.entry_headway_seconds) ||
        !std::isfinite(config_.max_simulation_time) ||
        config_.retry_interval <= 0.0 || config_.minimum_service_seconds <= 0.0 ||
        config_.dispatch_headway_seconds < 0.0 ||
        config_.entry_headway_seconds <= 0.0) {
      throw std::invalid_argument("event runtime time constants must be positive");
    }
    if (!std::isfinite(config_.pressure_weight) ||
        !std::isfinite(config_.pressure_age_weight) ||
        !std::isfinite(config_.pressure_distance_bias) ||
        config_.pressure_weight < 0.0 || config_.pressure_age_weight < 0.0 ||
        config_.pressure_distance_bias < 0.0) {
      throw std::invalid_argument("event runtime pressure weights must be non-negative");
    }
    if (config_.g4irsf17_source_wait_trace_limit < 0) {
      throw std::invalid_argument(
          "g4irsf17_source_wait_trace_limit must be non-negative");
    }
    config_.g4irsf17_source_policy.validate();
    if (config_.g4irsf17_source_policy_trace_limit < 0) {
      throw std::invalid_argument(
          "g4irsf17_source_policy_trace_limit must be non-negative");
    }
    if (!std::isfinite(config_.credit_validity_seconds) ||
        !std::isfinite(config_.credit_snapshot_max_age_seconds) ||
        config_.credit_validity_seconds <= 0.0 ||
        config_.credit_snapshot_max_age_seconds < 0.0 ||
        config_.credit_capacity_per_edge <= 0 ||
        config_.credit_lifecycle_limit < 0 ||
        config_.selective_credit_contention_threshold <= 0) {
      throw std::invalid_argument(
          "credit validity/capacity/contention threshold must be positive "
          "and snapshot age/lifecycle limit non-negative");
    }
    std::set<std::tuple<int, int, int>> regret_keys;
    const auto graph_nodes = graph_.node_locations();
    for (const auto& record : config_.pibt_regret_prior_records) {
      if (!graph_.has_edge(record.from_node, record.to_node) ||
          (record.goal_node >= 0 &&
           std::find(graph_nodes.begin(),
                     graph_nodes.end(),
                     record.goal_node) == graph_nodes.end()) ||
          !std::isfinite(record.penalty) || record.penalty < 0.0 ||
          !regret_keys.insert(std::make_tuple(record.from_node,
                                              record.to_node,
                                              record.goal_node))
               .second) {
        throw std::invalid_argument(
            "pibt_regret_prior_records require unique real edges, a real or "
            "-1 goal, and finite non-negative penalties");
      }
    }
    if (config_.history_limit <= 0 || config_.history_limit > 8 ||
        config_.max_decisions_per_bag <= 0 ||
        config_.max_events <= 0 || config_.deadlock_retry_threshold <= 0) {
      throw std::invalid_argument(
          "event runtime integer limits must be positive and history_limit must be <= 8");
    }
    if (config_.pibt_max_ready_bags <= 0 ||
        config_.pibt_max_local_resources <= 0 ||
        config_.pibt_max_candidates_per_bag <= 0) {
      throw std::invalid_argument(
          "bounded local PIBT bag/resource/candidate limits must be positive");
    }
    if (!std::isfinite(config_.scorer_b2) ||
        !std::isfinite(config_.scorer_risk_margin_threshold) ||
        !std::isfinite(config_.scorer_risk_bottleneck_threshold) ||
        config_.scorer_risk_margin_threshold < 0.0 ||
        config_.scorer_risk_bottleneck_threshold < 0.0) {
      throw std::invalid_argument(
          "scorer bias and risk thresholds must be finite and thresholds non-negative");
    }
    if (scorer_mode == "S1" || scorer_mode == "S2") {
      constexpr const char* kFrozenModelSha256 =
          "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca";
      constexpr const char* kFrozenWeightsFingerprint =
          "6d8444b394687559bc8070c650aefbc9019df69406d30b20c65a9aa903dde108";
      constexpr const char* kCanonicalRuntimeGraphFingerprint =
          "d4e7f065b082e1b73b983e492f460ded1dabab66f62ffd47e74b1f5f071abe73";
      if (config_.scorer_model_sha256 != kFrozenModelSha256) {
        throw std::invalid_argument(
            "S1/S2 require the audited frozen G4E model SHA256");
      }
      if (config_.scorer_w1.size() != 22 ||
          config_.scorer_b1.size() != 22 ||
          config_.scorer_w2.size() != 22) {
        throw std::invalid_argument(
            "S1/S2 frozen G4E model must be 22x22 with 22 hidden/output weights");
      }
      for (const auto& row : config_.scorer_w1) {
        if (row.size() != 22) {
          throw std::invalid_argument(
              "S1/S2 frozen G4E w1 rows must each have 22 values");
        }
        if (!std::all_of(row.begin(), row.end(), [](double value) {
              return std::isfinite(value);
            })) {
          throw std::invalid_argument(
              "S1/S2 frozen G4E w1 values must be finite");
        }
      }
      if (!std::all_of(config_.scorer_b1.begin(),
                       config_.scorer_b1.end(),
                       [](double value) {
                         return std::isfinite(value);
                       }) ||
          !std::all_of(config_.scorer_w2.begin(),
                       config_.scorer_w2.end(),
                       [](double value) {
                         return std::isfinite(value);
                       })) {
        throw std::invalid_argument(
            "S1/S2 frozen G4E weights must be finite");
      }
      if (config_.scorer_risk_margin_threshold != 1.0 ||
          config_.scorer_risk_bottleneck_threshold != 5.0) {
        throw std::invalid_argument(
            "S1/S2 risk thresholds must match the audited frozen artifact");
      }
      if (scorer_model_fingerprint() !=
          kFrozenWeightsFingerprint) {
        throw std::invalid_argument(
            "S1/S2 frozen G4E weights do not match the audited artifact");
      }
      if (scorer_graph_fingerprint() !=
          kCanonicalRuntimeGraphFingerprint) {
        throw std::invalid_argument(
            "S1/S2 require the audited canonical map2 runtime graph identity");
      }
    }
    if (config_.diagnostic_hops < 0 || config_.diagnostic_hops > 2) {
      throw std::invalid_argument("diagnostic_hops must be in [0, 2]");
    }
    if (config_.trace_shard_count <= 0 || config_.trace_shard_index < 0 ||
        config_.trace_shard_index >= config_.trace_shard_count) {
      throw std::invalid_argument(
          "trace_shard_count must be positive and trace_shard_index must be in range");
    }
    if (config_.opportunity_trace_limit < 0) {
      throw std::invalid_argument(
          "opportunity_trace_limit must be non-negative");
    }
    if (config_.merge_grant_max_pending_requests <= 0 ||
        config_.merge_grant_lifecycle_limit < 0) {
      throw std::invalid_argument(
          "merge grant pending bound must be positive and lifecycle bound "
          "must be non-negative");
    }
    if (!uses_destination_merge_grants() &&
        canonical_merge_grant_timing_mode() !=
            DestinationMergeGrantTimingMode::kEager) {
      throw std::invalid_argument(
          "JIT merge timing is only valid with E4 destination merge grants");
    }
    if (uses_destination_merge_grants() &&
        canonical_resource_semantics() !=
            "R3_java_node_window_compatible") {
      throw std::invalid_argument(
          "E4 destination merge grants require frozen R3 node-window "
          "semantics");
    }
    if (uses_destination_merge_grants() &&
        uses_first_edge_credit()) {
      throw std::invalid_argument(
          "E4 vertical slice requires frozen C0 admission; first-edge "
          "credits are not destination merge capabilities");
    }
  }

  void validate_request(const EventRuntimeBagRequest& request) const {
    if (request.task_id < 0 || request.start < 0 || request.goal < 0) {
      throw std::invalid_argument("event runtime bag identifiers/nodes must be non-negative");
    }
    if (!std::isfinite(request.release_time) ||
        !std::isfinite(request.deadline) ||
        request.release_time < 0.0) {
      throw std::invalid_argument(
          "event runtime release_time/deadline must be finite and release_time non-negative");
    }
    (void)graph_.node(request.start);
    (void)graph_.node(request.goal);
  }

  void validate_fault_window(const EventRuntimeFaultWindow& window) const {
    if (!graph_.has_edge(window.start, window.end)) {
      throw std::invalid_argument("fault window references a missing directed edge");
    }
    if (!std::isfinite(window.fault_time) ||
        !std::isfinite(window.repair_time) ||
        !std::isfinite(window.message_delay) ||
        window.fault_time < 0.0 ||
        window.repair_time < window.fault_time ||
        window.message_delay < 0.0) {
      throw std::invalid_argument("fault window times are invalid");
    }
  }

  void reset() {
    runtime_phase_ = EventDrivenJunctionRuntimePhase::kIdle;
    time_limit_ = 0.0;
    result_ = {};
    bags_.clear();
    segment_runtime_ids_.clear();
    junctions_.clear();
    corridors_.clear();
    physical_faults_.clear();
    advertised_faults_.clear();
    congestion_beacons_.clear();
    destination_merge_controllers_.clear();
    pending_merge_dispatches_.clear();
    credit_ledger_ = ExpiringFirstEdgeCreditLedger(
        static_cast<std::size_t>(config_.credit_lifecycle_limit));
    directed_inflight_counts_.clear();
    fault_affected_bags_.clear();
    fault_affected_bags_by_edge_.clear();
    fault_instances_by_bag_.clear();
    active_fault_instance_by_edge_.clear();
    repair_time_by_fault_instance_.clear();
    g4irsf16_physical_fault_generation_by_bag_.clear();
    events_ = {};
    next_event_seq_ = 1;
    next_decision_id_ = 1;
    next_pibt_activation_id_ = 1;
    next_local_enqueue_sequence_ = 1;
    next_merge_request_lineage_ = 1;
    staged_event_sink_ = nullptr;
    staged_merge_visibility_sink_ = nullptr;
    staged_destination_known_competitor_counts_ =
        nullptr;
#ifdef CZR005_EVENT_RUNTIME_TESTING
    test_pibt_logical_failure_injected_ = false;
    test_merge_grant_prepare_failure_injected_ = false;
    test_merge_grant_advertised_flip_injected_ = false;
    test_merge_grant_physical_flip_injected_ = false;
    test_merge_grant_calendar_flip_injected_ = false;
    test_merge_grant_queue_flip_injected_ = false;
    test_merge_grant_edge_exit_capability_drop_injected_ = false;
    test_merge_grant_edge_exit_physical_flip_injected_ = false;
    test_merge_grant_edge_exit_advertised_flip_injected_ = false;
    test_merge_grant_edge_exit_calendar_remove_injected_ = false;
    test_merge_grant_edge_exit_expiry_injected_ = false;
    test_merge_grant_edge_exit_wrong_owner_injected_ = false;
    test_merge_grant_edge_exit_wrong_edge_injected_ = false;
    test_merge_grant_edge_exit_wrong_destination_injected_ = false;
    test_merge_grant_edge_exit_claimed_request_generation_tamper_injected_ =
        false;
    test_merge_grant_edge_exit_claimed_queue_generation_tamper_injected_ =
        false;
    test_merge_grant_edge_exit_claimed_calendar_generation_tamper_injected_ =
        false;
    test_merge_grant_edge_exit_live_queue_generation_advance_injected_ =
        false;
    test_merge_grant_edge_exit_live_calendar_generation_advance_injected_ =
        false;
    test_pibt_post_commit_failure_injected_ = false;
#endif
    if (g4irsf14_state_ != nullptr) {
      *g4irsf14_state_ =
          event_runtime_detail::G4IRSF14RuntimeState{};
    }
    if (g4irsf16_enabled()) {
      g4irsf16_supervisor_ =
          std::make_unique<G4IRSF16Supervisor>(
              g4irsf16_supervisor_config());
    }
    now_ = 0.0;
    active_bag_count_ = 0;
    last_physical_repair_time_ = -1.0;
    active_backlog_at_last_repair_ = -1;
    active_backlog_at_runtime_stop_ = -1;
    waits_.clear();
    decision_latencies_us_.clear();
  }

  void schedule(JunctionEventType type,
                double time,
                int task_id,
                int node,
                int from_node,
                int to_node,
                bool retry = false,
                std::uint64_t wakeup_generation = 0,
                double service_end = 0.0) {
    RuntimeEvent event;
    event.type = type;
    event.time = time;
    event.task_id = task_id;
    event.node = node;
    event.from_node = from_node;
    event.to_node = to_node;
    event.retry = retry;
    event.wakeup_generation = wakeup_generation;
    event.service_end = service_end;
    push_event(std::move(event));
  }

  void push_event(RuntimeEvent event) {
    if (staged_event_sink_ != nullptr) {
      staged_event_sink_->push_back(std::move(event));
      return;
    }
    publish_event(std::move(event));
  }

  int g4irsf14_microphase_priority(
      const RuntimeEvent& event) const {
    const auto mode = canonical_event_semantics();
    if (mode == "E0_immediate_dispatch_f2") {
      return -1;
    }
    if (mode == "E3_batch_source_and_junction_same_timestamp" ||
        mode == "E4_batch_plus_destination_merge_request") {
      if ((event.type == JunctionEventType::kFault ||
           event.type == JunctionEventType::kRepair) &&
          event.notification) {
        return 3;
      }
      if (event.type == JunctionEventType::kFault ||
          event.type == JunctionEventType::kRepair) {
        return 0;
      }
      if (event.type == JunctionEventType::kEdgeExit ||
          event.type ==
              JunctionEventType::kJunctionServiceComplete) {
        return 1;
      }
      if (event.type == JunctionEventType::kArriveJunction ||
          event.type == JunctionEventType::kBagRelease) {
        return 2;
      }
      if (event.type ==
              JunctionEventType::kCongestionBeaconUpdate ||
          event.type == JunctionEventType::kLocalQueueUpdate) {
        return 3;
      }
      if (event.type == JunctionEventType::kSourceArbitration) {
        return 4;
      }
      if (event.type ==
          JunctionEventType::kJunctionArbitration) {
        return 5;
      }
      if (event.type ==
          JunctionEventType::kDestinationMergeArbitration) {
        return 6;
      }
      if (event.type == JunctionEventType::kEdgeEnter) {
        return mode == "E4_batch_plus_destination_merge_request"
                   ? 7
                   : 6;
      }
      return mode == "E4_batch_plus_destination_merge_request"
                 ? 8
                 : 7;
    }
    // E1/E2 preserve the untouched immediate boundary's legacy ordering and
    // insert only the selected exact-time arbitration after queue/beacon
    // publication. Values are deliberately between BAG_RELEASE and passive
    // EDGE_ENTER/trace processing in the legacy priority space.
    if (event.type == JunctionEventType::kLocalQueueUpdate) {
      return 7;
    }
    if (event.type == JunctionEventType::kSourceArbitration) {
      return 8;
    }
    if (event.type ==
        JunctionEventType::kJunctionArbitration) {
      return 8;
    }
    if (event.type == JunctionEventType::kEdgeEnter) {
      return 9;
    }
    return -1;
  }

  void prepare_event_for_publication(
      RuntimeEvent& event) {
    const int base_priority =
        g4irsf14_microphase_priority(event);
    event.microphase_priority = base_priority;
    if (g4irsf14_state_ != nullptr &&
        canonical_event_semantics() !=
            "E0_immediate_dispatch_f2" &&
        g4irsf14_state_->microphase_floor_active &&
        event_runtime_detail::same_timestamp(
            event.time,
            g4irsf14_state_->microphase_floor_time)) {
      const int effective_base =
          base_priority >= 0
              ? base_priority
              : event_runtime_detail::event_priority(event);
      event.microphase_priority =
          std::max(
              effective_base,
              g4irsf14_state_->microphase_floor_priority);
    }
  }

  void publish_prepared_event(RuntimeEvent event) {
    event.seq = next_event_seq_++;
    events_.push(std::move(event));
  }

  void publish_prepared_reserved_event(
      RuntimeEvent event) noexcept {
    event.seq = next_event_seq_++;
    events_.push(std::move(event));
  }

  void publish_event(RuntimeEvent event) {
    prepare_event_for_publication(event);
    publish_prepared_event(std::move(event));
  }

  void process_event(const RuntimeEvent& event) {
    if (g4irsf14_state_ != nullptr) {
      g4irsf14_state_->current_event_seq = event.seq;
      if (canonical_event_semantics() !=
          "E0_immediate_dispatch_f2") {
        const int effective_priority =
            event.microphase_priority >= 0
                ? event.microphase_priority
                : event_runtime_detail::event_priority(event);
        if (!g4irsf14_state_->microphase_floor_active ||
            !event_runtime_detail::same_timestamp(
                event.time,
                g4irsf14_state_->microphase_floor_time)) {
          g4irsf14_state_->microphase_floor_active = true;
          g4irsf14_state_->microphase_floor_time = event.time;
          g4irsf14_state_->microphase_floor_priority =
              effective_priority;
        } else {
          g4irsf14_state_->microphase_floor_priority =
              std::max(
                  g4irsf14_state_->microphase_floor_priority,
                  effective_priority);
        }
      }
    }
    switch (event.type) {
      case JunctionEventType::kBagRelease:
        ++result_.summary.bag_release_event_count;
        process_release(event);
        break;
      case JunctionEventType::kArriveJunction:
        ++result_.summary.arrive_junction_event_count;
        process_arrive(event);
        break;
      case JunctionEventType::kJunctionServiceComplete:
        ++result_.summary.junction_service_complete_event_count;
        process_service_complete(event);
        break;
      case JunctionEventType::kEdgeEnter:
        ++result_.summary.edge_enter_event_count;
        process_edge_enter(event);
        break;
      case JunctionEventType::kEdgeExit:
        ++result_.summary.edge_exit_event_count;
        process_edge_exit(event);
        break;
      case JunctionEventType::kFault:
        ++result_.summary.fault_event_count;
        process_fault_message(event);
        break;
      case JunctionEventType::kRepair:
        ++result_.summary.repair_event_count;
        process_fault_message(event);
        break;
      case JunctionEventType::kLocalQueueUpdate:
        ++result_.summary.local_queue_update_event_count;
        process_local_queue_update(event);
        break;
      case JunctionEventType::kCongestionBeaconUpdate:
        ++result_.summary.congestion_beacon_update_event_count;
        process_congestion_beacon_update(event);
        break;
      case JunctionEventType::kSourceArbitration:
        ++result_.summary.source_arbitration_event_count;
        process_source_arbitration(event);
        break;
      case JunctionEventType::kJunctionArbitration:
        ++result_.summary.junction_arbitration_event_count;
        process_junction_arbitration(event);
        break;
      case JunctionEventType::kDestinationMergeArbitration:
        ++result_.summary.destination_merge_arbitration_event_count;
        process_destination_merge_arbitration(event);
        break;
    }
  }

  void process_release(const RuntimeEvent& event) {
    auto& controller = junctions_[event.node];
    if (event.retry) {
      if (!controller.source_wakeup_pending ||
          controller.source_wakeup_generation != event.wakeup_generation) {
        return;
      }
      controller.source_wakeup_pending = false;
    } else {
      auto found = bags_.find(event.task_id);
      if (found == bags_.end() || found->second.status != BagStatus::kPendingRelease) {
        return;
      }
      auto& bag = found->second;
      bag.status = BagStatus::kSourceQueue;
      bag.active_in_runtime = true;
      ++active_bag_count_;
      result_.summary.peak_active_bag_count =
          std::max(result_.summary.peak_active_bag_count, active_bag_count_);
      bag.source_enqueued_at = event.time;
      bag.local_enqueue_sequence = next_local_enqueue_sequence_++;
      controller.source_queue.push_back(event.task_id);
      if (g4irsf17_source_policy_enabled() ||
          config_.enable_g4irsf17_causal_source_features) {
        controller.g4irsf17_source_temporal.releases.record(event.time);
      }
      update_queue_maxima(controller);
      observe_source_enqueue(event.node, event.time);
      schedule_passive(JunctionEventType::kLocalQueueUpdate,
                       event.time,
                       event.task_id,
                       event.node,
                       -1,
                       event.node,
                       "source_enqueue");
    }

    if (batches_source_same_timestamp()) {
      schedule_source_wakeup(event.node, event.time);
      append_event_trace(event,
                         event.task_id,
                         event.node,
                         -1,
                         -1,
                         "source_release_enqueue",
                         0);
      return;
    }

    const int ready_set_size =
        static_cast<int>(controller.source_queue.size());
    int priority_comparison_count = 0;
    int chosen_task = -1;
    int* comparison_counter =
        config_.enable_opportunity_telemetry
            ? &priority_comparison_count
            : nullptr;
    const int admitted_task =
        try_admit_source(event.node,
                         event.time,
                         config_.enable_opportunity_telemetry
                             ? &chosen_task
                             : nullptr,
                         comparison_counter);
    append_source_opportunity(event,
                              ready_set_size,
                              chosen_task,
                              priority_comparison_count,
                              false);
    append_event_trace(event,
                       admitted_task,
                       event.node,
                       -1,
                       -1,
                       event.retry ? "source_admission_retry" : "source_release",
                       0);
    if (!controller.source_queue.empty()) {
      const double duration = service_duration(event.node);
      const double calendar_ready = controller.service_calendar.earliest_start(event.time, duration);
      schedule_source_wakeup(event.node,
                             std::max(event.time + config_.retry_interval, calendar_ready));
    }
  }

  void process_source_arbitration(const RuntimeEvent& event) {
    if (!consume_source_arbitration_wakeup(event)) {
      return;
    }
    auto& controller = junctions_[event.node];
    if (controller.source_queue.empty()) {
      ++result_.summary.stale_arbitration_event_count;
      return;
    }
    const int ready_set_size =
        static_cast<int>(controller.source_queue.size());
    int priority_comparison_count = 0;
    int chosen_task = -1;
    int* comparison_counter =
        config_.enable_opportunity_telemetry
            ? &priority_comparison_count
            : nullptr;
    const int admitted_task =
        try_admit_source(event.node,
                         event.time,
                         config_.enable_opportunity_telemetry
                             ? &chosen_task
                             : nullptr,
                         comparison_counter);
    append_source_opportunity(event,
                              ready_set_size,
                              chosen_task,
                              priority_comparison_count,
                              true);
    append_event_trace(event,
                       admitted_task,
                       event.node,
                       -1,
                       -1,
                       "same_timestamp_source_arbitration",
                       0);
    if (!controller.source_queue.empty()) {
      const double duration = service_duration(event.node);
      const double calendar_ready =
          controller.service_calendar.earliest_start(event.time,
                                                     duration);
      schedule_source_wakeup(
          event.node,
          std::max(event.time + config_.retry_interval,
                   calendar_ready));
    }
  }

  void g4irsf17_close_source_wait_interval(int source_node,
                                           double end_time) {
    if (!config_.enable_g4irsf17_source_wait_telemetry) {
      return;
    }
    auto found = junctions_.find(source_node);
    if (found == junctions_.end() ||
        !found->second.g4irsf17_active_source_wait.has_value()) {
      return;
    }
    const auto active =
        *found->second.g4irsf17_active_source_wait;
    found->second.g4irsf17_active_source_wait.reset();
    const double seconds =
        std::max(0.0, end_time - active.started_at);
    if (seconds <= event_runtime_detail::kEpsilon) {
      return;
    }

    EventRuntimeSourceWaitBlockerRow row;
    row.interval_ordinal =
        result_.summary.g4irsf17_source_wait_interval_total_count + 1;
    row.reason =
        g4irsf17_source_wait_reason_name(active.blocker.reason);
    row.reason_precedence =
        g4irsf17_source_wait_reason_precedence(active.blocker.reason);
    row.source_node = source_node;
    row.blocker_node = active.blocker.blocker_node;
    row.blocker_resource = g4irsf17_source_wait_resource_name(
        active.blocker.resource);
    row.blocker_resource_from_node =
        active.blocker.resource_from_node;
    row.blocker_resource_to_node =
        active.blocker.resource_to_node;
    row.source_generation = active.source_generation;
    row.blocker_generation =
        active.blocker.blocker_generation;
    row.wait_start_time = active.started_at;
    row.wait_end_time = end_time;
    row.wait_seconds = seconds;
    row.affected_bag_count = active.affected_bag_count;
    row.wait_bag_seconds =
        seconds * static_cast<double>(active.affected_bag_count);
    row.selected_runtime_bag_id =
        active.selected_runtime_bag_id;
    const auto bag = bags_.find(active.selected_runtime_bag_id);
    if (bag != bags_.end()) {
      row.selected_task_id = bag->second.request.task_id;
      row.selected_segment_id = bag->second.request.segment_id;
    }

    ++result_.summary.g4irsf17_source_wait_interval_total_count;
    result_.summary.g4irsf17_source_wait_seconds += seconds;
    result_.summary.g4irsf17_source_wait_bag_seconds +=
        row.wait_bag_seconds;
    const auto reason_index =
        static_cast<std::size_t>(active.blocker.reason);
    ++result_.summary
          .g4irsf17_source_wait_reason_interval_counts[reason_index];
    result_.summary.g4irsf17_source_wait_reason_seconds[reason_index] +=
        seconds;
    result_.summary
        .g4irsf17_source_wait_reason_bag_seconds[reason_index] +=
        row.wait_bag_seconds;
    if (result_.g4irsf17_source_wait_blockers.size() <
        static_cast<std::size_t>(
            config_.g4irsf17_source_wait_trace_limit)) {
      ++result_.summary.g4irsf17_source_wait_interval_stored_count;
      result_.g4irsf17_source_wait_blockers.push_back(
          std::move(row));
    } else {
      ++result_.summary.g4irsf17_source_wait_interval_dropped_count;
    }
  }

  void g4irsf17_open_source_wait_interval(
      int source_node,
      double start_time,
      std::uint64_t source_generation,
      int selected_runtime_bag_id,
      const event_runtime_detail::G4IRSF17SourceBlockerObservation& blocker) {
    if (!config_.enable_g4irsf17_source_wait_telemetry) {
      return;
    }
    auto& controller = junctions_[source_node];
    event_runtime_detail::G4IRSF17ActiveSourceWait active;
    active.blocker = blocker;
    if (!active.blocker.valid) {
      active.blocker.consider(
          G4IRSF17SourceWaitReason::kOtherExplicitReason,
          event_runtime_detail::G4IRSF17SourceWaitResource::
              kOtherLocalResource,
          source_node,
          source_node,
          source_node,
          source_generation);
    }
    active.started_at = start_time;
    active.source_generation = source_generation;
    active.affected_bag_count =
        static_cast<int>(controller.source_queue.size());
    active.selected_runtime_bag_id = selected_runtime_bag_id;
    controller.g4irsf17_active_source_wait = std::move(active);
  }

  void g4irsf17_set_local_blocker(
      int node,
      event_runtime_detail::G4IRSF17SourceBlockerObservation blocker) {
    if (!g4irsf17_extensions_enabled()) {
      return;
    }
    auto& state = junctions_[node].g4irsf17_local_blocker;
    ++state.generation;
    state.valid = true;
    blocker.valid = true;
    state.blocker = std::move(blocker);
  }

  void g4irsf17_clear_local_blocker(int node) noexcept {
    if (!g4irsf17_extensions_enabled()) {
      return;
    }
    const auto found = junctions_.find(node);
    if (found == junctions_.end()) {
      return;
    }
    auto& state = found->second.g4irsf17_local_blocker;
    ++state.generation;
    state.valid = false;
    state.blocker = {};
  }

  int g4irsf17_source_leg_priority(const BagState& bag) const noexcept {
    const auto has_suffix = [&](const char* suffix) {
      const std::string value(suffix);
      return bag.request.segment_id.size() >= value.size() &&
             bag.request.segment_id.compare(
                 bag.request.segment_id.size() - value.size(),
                 value.size(), value) == 0;
    };
    // Only a fixed semantic suffix is decoded.  The segment identity itself
    // is never supplied to the model and cannot become a codebook.
    if (has_suffix(":direct")) {
      return 2;
    }
    if (has_suffix(":storage_out")) {
      return 1;
    }
    if (has_suffix(":storage_in")) {
      return -1;
    }
    return 0;
  }

  G4IRSF17SourceCandidateObservation
  g4irsf17_source_candidate_observation(
      const BagState& bag, int local_rank, double time) const noexcept {
    G4IRSF17SourceCandidateObservation observation;
    observation.local_rank = local_rank;
    observation.deadline_slack_seconds = g4irsf17_finite_clip(
        bag.request.deadline >= 0.0
            ? bag.request.deadline - time
            : 86400.0,
        -86400.0,
        86400.0);
    observation.wait_age_seconds = g4irsf17_finite_clip(
        std::max(0.0, time - bag.source_enqueued_at),
        0.0,
        86400.0);
    observation.leg_priority = g4irsf17_source_leg_priority(bag);
    observation.repair_priority = bag.repaired_task_reentry;
    return observation;
  }

  G4IRSF17SourceContextObservation
  g4irsf17_source_context_observation(
      int node,
      double time,
      std::uint64_t source_generation,
      const BagState& baseline_bag,
      event_runtime_detail::JunctionState& controller) {
    G4IRSF17SourceContextObservation context;
    const double queue_length =
        static_cast<double>(controller.source_queue.size());
    const double source_capacity =
        static_cast<double>(
            config_.local_queue_capacity > 0
                ? config_.local_queue_capacity
                : std::max<std::size_t>(1U,
                                        controller.source_queue.size()));
    context.source_queue_length = queue_length;
    context.source_queue_capacity = source_capacity;
    context.source_queue_utilization =
        std::min(1.0, queue_length / source_capacity);
    auto& temporal = controller.g4irsf17_source_temporal;
    context.source_queue_generation_delta =
        static_cast<double>(std::min<std::uint64_t>(
            4096U,
            source_generation >= temporal.last_observed_source_generation
                ? source_generation -
                      temporal.last_observed_source_generation
                : 0U));
    temporal.last_observed_source_generation = source_generation;
    context.release_count_10s = temporal.releases.count(time, 10.0);
    context.release_count_30s = temporal.releases.count(time, 30.0);
    context.release_count_60s = temporal.releases.count(time, 60.0);
    context.admission_count_10s = temporal.admissions.count(time, 10.0);
    context.admission_count_30s = temporal.admissions.count(time, 30.0);
    context.admission_count_60s = temporal.admissions.count(time, 60.0);
    context.queue_slope_10s =
        (context.release_count_10s - context.admission_count_10s) / 10.0;
    context.queue_slope_30s =
        (context.release_count_30s - context.admission_count_30s) / 30.0;
    context.queue_slope_60s =
        (context.release_count_60s - context.admission_count_60s) / 60.0;

    if (baseline_bag.first_edge_credit_id != 0) {
      const auto* credit =
          credit_ledger_.find(baseline_bag.first_edge_credit_id);
      if (credit != nullptr) {
        context.first_edge_credit_slack_seconds =
            g4irsf17_finite_clip(
                std::min(credit->latest, credit->expiry) - time,
                -3600.0,
                3600.0);
      }
    }

    auto outgoing = graph_.outgoing(node);
    std::sort(outgoing.begin(), outgoing.end());
    if (outgoing.size() > 4U) {
      outgoing.resize(4U);
    }
    const event_runtime_detail::CongestionBeaconState* selected = nullptr;
    int selected_pressure = -1;
    std::uint64_t merge_generation = 0;
    for (const int downstream : outgoing) {
      const auto found = congestion_beacons_.find(downstream);
      if (found == congestion_beacons_.end() ||
          time - found->second.received_at >
              60.0 + event_runtime_detail::kEpsilon) {
        continue;
      }
      const int pressure = found->second.queue_length +
                           found->second.scheduled_incoming;
      context.one_hop_ttl_pressure = std::max(
          context.one_hop_ttl_pressure,
          static_cast<double>(pressure));
      context.two_hop_ttl_pressure = std::max(
          context.two_hop_ttl_pressure,
          found->second.g4irsf17_one_hop_ttl_pressure);
      context.merge_pending_count = std::max(
          context.merge_pending_count,
          static_cast<double>(
              found->second.g4irsf17_merge_pending_request_count));
      context.merge_oldest_request_age_seconds = std::max(
          context.merge_oldest_request_age_seconds,
          found->second.g4irsf17_merge_oldest_request_age_seconds);
      context.recent_incoming_grants_60s = std::max(
          context.recent_incoming_grants_60s,
          found->second.g4irsf17_recent_incoming_grants_60s);
      context.incoming_grant_imbalance_60s = std::max(
          context.incoming_grant_imbalance_60s,
          found->second.g4irsf17_incoming_grant_imbalance_60s);
      merge_generation = std::max(
          merge_generation, found->second.g4irsf17_merge_generation);
      if (pressure > selected_pressure) {
        selected_pressure = pressure;
        selected = &found->second;
      }
    }
    context.merge_token_generation_delta =
        static_cast<double>(std::min<std::uint64_t>(
            4096U,
            merge_generation >= temporal.last_observed_merge_generation
                ? merge_generation - temporal.last_observed_merge_generation
                : 0U));
    temporal.last_observed_merge_generation = merge_generation;
    if (selected != nullptr) {
      context.target_queue_length = selected->queue_length;
      const double target_capacity =
          static_cast<double>(
              config_.local_queue_capacity > 0
                  ? config_.local_queue_capacity
                  : std::max(1, selected_pressure));
      context.target_queue_capacity = target_capacity;
      context.target_queue_utilization = std::min(
          1.0, static_cast<double>(selected_pressure) / target_capacity);
      context.target_scheduled_incoming = selected->scheduled_incoming;
      context.estimated_service_rate_60s =
          selected->g4irsf17_estimated_service_rate_60s;
      context.drain_slope_60s = selected->g4irsf17_drain_slope_60s;
      context.service_weighted_pressure =
          static_cast<double>(selected_pressure) /
          std::max(1.0 / 60.0,
                   context.estimated_service_rate_60s);
      context.time_to_next_service_opportunity_seconds =
          std::max(0.0,
                   selected->service_calendar_reserved_until - time);
    }
    return context;
  }

  bool g4irsf17_source_supervisor_authorized(
      const event_runtime_detail::JunctionState& controller) const noexcept {
    if (active_causal_step_ != nullptr || controller.escape_token_task >= 0) {
      return false;
    }
    if (!controller.g4irsf17_local_blocker.valid) {
      return true;
    }
    const auto reason = controller.g4irsf17_local_blocker.blocker.reason;
    return reason != G4IRSF17SourceWaitReason::kPhysicalFaultOrGeneration &&
           reason != G4IRSF17SourceWaitReason::kSupervisorHold &&
           reason !=
               G4IRSF17SourceWaitReason::kPIBTOrRecoveryTransaction;
  }

  std::size_t g4irsf17_apply_source_policy(
      int node,
      double time,
      std::uint64_t source_generation,
      std::size_t baseline_queue_index,
      event_runtime_detail::JunctionState& controller,
      const G4IRSF17SourceContextObservation& context) {
    if (!g4irsf17_source_policy_enabled() ||
        controller.source_queue.size() < 2U) {
      return baseline_queue_index;
    }
    const auto& policy = config_.g4irsf17_source_policy;
    std::vector<std::size_t> queue_indices;
    queue_indices.reserve(static_cast<std::size_t>(policy.top_k));
    queue_indices.push_back(baseline_queue_index);
    for (std::size_t index = 0;
         index < controller.source_queue.size() &&
         queue_indices.size() < static_cast<std::size_t>(policy.top_k);
         ++index) {
      if (index != baseline_queue_index) {
        queue_indices.push_back(index);
      }
    }

    std::vector<G4IRSF17SourceCandidateObservation> candidates;
    candidates.reserve(queue_indices.size());
    for (std::size_t rank = 0; rank < queue_indices.size(); ++rank) {
      candidates.push_back(g4irsf17_source_candidate_observation(
          bags_.at(controller.source_queue[queue_indices[rank]]),
          static_cast<int>(rank),
          time));
    }
    const auto decision = g4irsf17_decide_source_front(
        policy,
        candidates,
        context,
        g4irsf17_source_supervisor_authorized(controller));

    ++result_.summary.g4irsf17_source_policy_evaluation_count;
    if (decision.proposed_index != 0) {
      ++result_.summary.g4irsf17_source_policy_change_proposal_count;
    }
    if (decision.activated) {
      ++result_.summary.g4irsf17_source_policy_activation_count;
    } else {
      ++result_.summary.g4irsf17_source_policy_abstention_count;
    }
    if (decision.out_of_distribution) {
      ++result_.summary.g4irsf17_source_policy_ood_abstention_count;
    }
    if (decision.reason == "SUPERVISOR_GATE") {
      ++result_.summary
            .g4irsf17_source_policy_supervisor_abstention_count;
    }

    EventRuntimeG4IRSF17SourcePolicyRow row;
    row.decision_ordinal =
        ++result_.summary.g4irsf17_source_policy_trace_total_count;
    row.event_time = time;
    row.source_node = node;
    row.mode = policy.mode;
    row.kind = policy.kind;
    row.artifact_set_id = policy.artifact_set_id;
    row.top_k = policy.top_k;
    row.source_queue_length =
        static_cast<int>(controller.source_queue.size());
    row.source_generation = source_generation;
    row.baseline_candidate_index = 0;
    row.treatment_candidate_index = decision.treatment_index;
    row.proposed_candidate_index = decision.proposed_index;
    row.chosen_candidate_index = decision.chosen_index;
    row.baseline_queue_index =
        static_cast<int>(queue_indices[0]);
    row.treatment_queue_index = static_cast<int>(
        queue_indices[static_cast<std::size_t>(decision.treatment_index)]);
    row.proposed_queue_index = static_cast<int>(
        queue_indices[static_cast<std::size_t>(decision.proposed_index)]);
    row.chosen_queue_index = static_cast<int>(
        queue_indices[static_cast<std::size_t>(decision.chosen_index)]);
    row.activated = decision.activated;
    row.out_of_distribution = decision.out_of_distribution;
    row.supervisor_authorized = decision.supervisor_authorized;
    row.reason = decision.reason;
    row.model_score = decision.model_score;
    row.benefit_probability_lcb =
        decision.benefit_probability_lcb;
    row.harmful_probability_ucb =
        decision.harmful_probability_ucb;
    row.utility_lcb_seconds = decision.utility_lcb_seconds;
    row.calibration_ece = decision.calibration_ece;
    row.context_features = context.values();
    row.pairwise_features = decision.pairwise_features;
    const auto& baseline = candidates[0];
    for (std::size_t index = 0; index < candidates.size(); ++index) {
      const auto queue_index = queue_indices[index];
      const auto& bag =
          bags_.at(controller.source_queue[queue_index]);
      row.candidate_queue_indices.push_back(
          static_cast<int>(queue_index));
      row.candidate_task_ids.push_back(bag.request.task_id);
      row.candidate_runtime_bag_ids.push_back(
          bag.request.runtime_bag_id);
      row.candidate_segment_ids.push_back(bag.request.segment_id);
      row.candidate_features.push_back(
          candidates[index].features_relative_to(baseline));
    }
    if (result_.g4irsf17_source_policy_decisions.size() <
        static_cast<std::size_t>(
            config_.g4irsf17_source_policy_trace_limit)) {
      ++result_.summary.g4irsf17_source_policy_trace_stored_count;
      result_.g4irsf17_source_policy_decisions.push_back(
          std::move(row));
    } else {
      ++result_.summary.g4irsf17_source_policy_trace_dropped_count;
    }
    return queue_indices[static_cast<std::size_t>(decision.chosen_index)];
  }

  int try_admit_source(
      int node,
      double time,
      int* chosen_task = nullptr,
      int* priority_comparison_count = nullptr) {
    auto& controller = junctions_[node];
    g4irsf17_close_source_wait_interval(node, time);
    controller.service_calendar.purge(time);
    controller.observe_local_state();
    if (controller.source_queue.empty()) {
      return -1;
    }
    const std::uint64_t source_generation =
        g4irsf17_extensions_enabled()
            ? ++controller.g4irsf17_source_generation
            : 0;
    std::size_t queue_index =
        choose_bag(controller.source_queue,
                   time,
                   controller.escape_token_task,
                   priority_comparison_count);
    std::optional<G4IRSF17SourceContextObservation>
        g4irsf17_pre_action_context;
    if (controller.source_queue.size() >= 2U &&
        (g4irsf17_source_policy_enabled() ||
         config_.enable_g4irsf17_causal_source_features)) {
      g4irsf17_pre_action_context.emplace(
          g4irsf17_source_context_observation(
              node, time, source_generation,
              bags_.at(controller.source_queue[queue_index]),
              controller));
    }
    if (g4irsf17_source_policy_enabled() &&
        g4irsf17_pre_action_context.has_value()) {
      queue_index = g4irsf17_apply_source_policy(
          node, time, source_generation, queue_index, controller,
          *g4irsf17_pre_action_context);
    }
    bool causal_i1_swap_selected = false;
    int causal_i1_baseline_runtime_bag_id = -1;
    int causal_i1_peer_runtime_bag_id = -1;
    if (active_causal_step_ != nullptr &&
        controller.source_queue.size() >= 2U) {
      G4IRSF14CloneBoundary boundary;
      boundary.kind =
          G4IRSF14CloneBoundaryKind::kSourceArbitration;
      boundary.node = node;
      boundary.runtime_bag_id =
          controller.source_queue[queue_index];
      boundary.source_ready_order.assign(
          controller.source_queue.begin(),
          controller.source_queue.end());
      if (config_.enable_g4irsf17_causal_source_features &&
          g4irsf17_pre_action_context.has_value()) {
        const int baseline_runtime_bag_id =
            controller.source_queue[queue_index];
        int peer_runtime_bag_id =
            std::numeric_limits<int>::max();
        for (const int candidate_runtime_bag_id :
             controller.source_queue) {
          if (candidate_runtime_bag_id != baseline_runtime_bag_id) {
            peer_runtime_bag_id = std::min(
                peer_runtime_bag_id,
                candidate_runtime_bag_id);
          }
        }
        if (peer_runtime_bag_id !=
            std::numeric_limits<int>::max()) {
          const auto baseline_observation =
              g4irsf17_source_candidate_observation(
                  bags_.at(baseline_runtime_bag_id), 0, time);
          const auto treatment_observation =
              g4irsf17_source_candidate_observation(
                  bags_.at(peer_runtime_bag_id), 1, time);
          boundary.g4irsf17_i1_observation_available = true;
          boundary.g4irsf17_i1_observation_peer_runtime_bag_id =
              peer_runtime_bag_id;
          boundary.g4irsf17_i1_baseline_observation =
              g4irsf17_canonical_source_observation(
                  baseline_observation, baseline_observation,
                  *g4irsf17_pre_action_context);
          boundary.g4irsf17_i1_treatment_observation =
              g4irsf17_canonical_source_observation(
                  treatment_observation, baseline_observation,
                  *g4irsf17_pre_action_context);
          boundary.g4irsf17_i1_pairwise_features =
              g4irsf17_pairwise_features(
                  treatment_observation, baseline_observation,
                  *g4irsf17_pre_action_context);
        }
      }
      if (const auto* intervention =
              observe_causal_boundary(std::move(boundary));
          intervention != nullptr) {
        if (intervention->kind !=
                G4IRSF14CloneInterventionKind::kSourceOrderSwap ||
            intervention->runtime_bag_id !=
                controller.source_queue[queue_index]) {
          throw std::logic_error(
              "I1 directive does not swap the baseline source winner");
        }
        const auto peer = std::find(
            controller.source_queue.begin(),
            controller.source_queue.end(),
            intervention->peer_runtime_bag_id);
        if (peer == controller.source_queue.end()) {
          throw std::logic_error(
              "I1 peer disappeared from the identical source ready set");
        }
        queue_index = static_cast<std::size_t>(
            std::distance(controller.source_queue.begin(),
                          peer));
        causal_i1_swap_selected = true;
        causal_i1_baseline_runtime_bag_id =
            intervention->runtime_bag_id;
        causal_i1_peer_runtime_bag_id =
            intervention->peer_runtime_bag_id;
      }
    }
    const int task_id = controller.source_queue[queue_index];
    if (chosen_task != nullptr) {
      *chosen_task = task_id;
    }
    auto& bag = bags_.at(task_id);
    const double duration = service_duration(node);
    ++result_.summary.source_admission_attempt_count;
    const bool queue_has_room = config_.local_queue_capacity <= 0 ||
                                 static_cast<int>(controller.queue.size()) < config_.local_queue_capacity;
    if (!queue_has_room) {
      event_runtime_detail::G4IRSF17SourceBlockerObservation blocker;
      if (controller.g4irsf17_local_blocker.valid) {
        blocker = controller.g4irsf17_local_blocker.blocker;
        blocker.blocker_generation =
            controller.g4irsf17_local_blocker.generation;
      } else {
        blocker.consider(
            G4IRSF17SourceWaitReason::kOtherExplicitReason,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kSourceLocalQueue,
            node,
            node,
            node,
            controller.service_calendar.generation());
      }
      ++result_.summary.source_admission_local_resource_hold_count;
      g4irsf17_open_source_wait_interval(
          node, time, source_generation, task_id, blocker);
      return -1;
    }
    if (!controller.service_calendar.available(
            time, time + duration, task_id)) {
      event_runtime_detail::G4IRSF17SourceBlockerObservation blocker;
      blocker.consider(
          G4IRSF17SourceWaitReason::kSourceServiceNotReady,
          event_runtime_detail::G4IRSF17SourceWaitResource::
              kSourceServiceCalendar,
          node,
          node,
          node,
          controller.service_calendar.generation());
      ++result_.summary.source_admission_local_resource_hold_count;
      g4irsf17_open_source_wait_interval(
          node, time, source_generation, task_id, blocker);
      return -1;
    }
    const auto admission_mode = canonical_admission_mode();
    event_runtime_detail::G4IRSF17SourceBlockerObservation blocker;
    if (admission_mode == "legacy_unbound" &&
        !downstream_admission_ready(
            bag, node, time, duration, &blocker)) {
      ++result_.summary.source_admission_downstream_pressure_hold_count;
      g4irsf17_open_source_wait_interval(
          node, time, source_generation, task_id, blocker);
      return -1;
    }
    const bool first_edge_credit_required =
        uses_first_edge_credit() &&
        observe_first_edge_credit_requirement(bag, node);
    if (first_edge_credit_required &&
        !ensure_first_edge_credit(bag,
                                  node,
                                  time,
                                  time + duration,
                                  false,
                                  &blocker)) {
      ++result_.summary.source_admission_downstream_pressure_hold_count;
      ++result_.summary.first_edge_credit_local_hold_count;
      request_one_hop_credit_snapshot_refresh(node, time);
      g4irsf17_open_source_wait_interval(
          node, time, source_generation, task_id, blocker);
      return -1;
    }
    if (node == bag.request.goal) {
      bag.first_edge_credit_consumed = true;
    }

    controller.service_calendar.reserve(task_id, time, time + duration);
    controller.record_service_reservation(time, time + duration);
    update_calendar_maxima(controller, nullptr);
    controller.source_queue.erase(controller.source_queue.begin() + static_cast<std::ptrdiff_t>(queue_index));
    if (g4irsf17_source_policy_enabled() ||
        config_.enable_g4irsf17_causal_source_features) {
      controller.g4irsf17_source_temporal.admissions.record(time);
    }
    controller.observe_local_state();
    if (!controller.source_queue.empty()) {
      event_runtime_detail::G4IRSF17SourceBlockerObservation service_blocker;
      service_blocker.consider(
          G4IRSF17SourceWaitReason::kSourceServiceNotReady,
          event_runtime_detail::G4IRSF17SourceWaitResource::
              kSourceServiceCalendar,
          node,
          node,
          node,
          controller.service_calendar.generation());
      g4irsf17_open_source_wait_interval(
          node, time, source_generation, -1, service_blocker);
    }
    bag.status = BagStatus::kInService;
    bag.current = node;
    bag.admitted_time = time;
    bag.total_wait += std::max(0.0, time - bag.source_enqueued_at);
    schedule(JunctionEventType::kJunctionServiceComplete,
             time + duration,
             task_id,
             node,
             -1,
             node);
    schedule_passive(JunctionEventType::kLocalQueueUpdate,
                     time,
                     task_id,
                     node,
                     -1,
                     node,
                     "source_dequeue");
    schedule_passive(JunctionEventType::kCongestionBeaconUpdate,
                     time,
                     task_id,
                     node,
                     node,
                     node,
                     "source_service_reservation_snapshot");
    ++result_.summary.source_admission_admitted_count;
    if (causal_i1_swap_selected) {
      mark_causal_action_applied(
          "APPLIED_I1_SOURCE_ADMIT_COMMITTED_ONE_ACTION",
          {causal_i1_baseline_runtime_bag_id,
           causal_i1_peer_runtime_bag_id});
    }
    return task_id;
  }

  bool downstream_admission_ready(const BagState& bag,
                                  int node,
                                  double time,
                                  double source_service_duration,
                                  event_runtime_detail::
                                      G4IRSF17SourceBlockerObservation*
                                          blocker = nullptr) {
    if (node == bag.request.goal) {
      return true;
    }
    std::vector<int> outgoing = graph_.outgoing(node);
    std::sort(outgoing.begin(), outgoing.end());
    bool ready = false;
    event_runtime_detail::G4IRSF17SourceBlockerObservation observed;
    for (const int downstream : outgoing) {
      ++result_.summary.source_admission_beacon_read_count;
      const auto snapshot = congestion_beacons_.find(downstream);
      if (snapshot == congestion_beacons_.end()) {
        observed.consider(
            G4IRSF17SourceWaitReason::kPhysicalFaultOrGeneration,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kPhysicalEdge,
            downstream,
            node,
            downstream,
            0);
        continue;
      }
      int pressure = snapshot->second.queue_length +
                     snapshot->second.scheduled_incoming;
      const auto pressure_mode = canonical_pressure_mode();
      if (pressure_mode == "C2_goal_conditioned_differential" ||
          pressure_mode == "C3_distance_biased_differential") {
        const auto queue = snapshot->second.queue_length_by_goal.find(bag.request.goal);
        const auto incoming =
            snapshot->second.scheduled_incoming_by_goal.find(bag.request.goal);
        pressure = (queue == snapshot->second.queue_length_by_goal.end() ? 0
                                                                         : queue->second) +
                   (incoming == snapshot->second.scheduled_incoming_by_goal.end()
                        ? 0
                        : incoming->second);
      }
      result_.summary.source_admission_max_observed_downstream_pressure =
          std::max(result_.summary.source_admission_max_observed_downstream_pressure,
                   pressure);

      const long long directed = event_runtime_detail::directed_key(node, downstream);
      const auto physical = physical_faults_.find(directed);
      const bool physical_edge_ready =
          physical == physical_faults_.end() || physical->second.active_count == 0;
      const double projected_departure = time + source_service_duration;
      const double travel =
          std::max(graph_.edge(node, downstream).travel_time(),
                   config_.minimum_service_seconds);
      const double projected_arrival = projected_departure + travel;
      bool local_corridor_ready = true;
      if (uses_corridor_calendar()) {
        auto& corridor = corridors_[resource_corridor_key(node, downstream)];
        corridor.purge(time);
        const double reservation_duration = corridor_reservation_duration(travel);
        local_corridor_ready = corridor.available(
            projected_departure,
            projected_departure + reservation_duration,
            bag.request.runtime_bag_id);
      }
      const bool downstream_calendar_ready =
          !uses_destination_calendar(downstream,
                                     bag.request.goal) ||
          snapshot->second.service_calendar_reserved_until <=
              projected_arrival + event_runtime_detail::kEpsilon;
      const bool downstream_queue_ready =
          config_.local_queue_capacity <= 0 ||
          pressure < config_.local_queue_capacity;
      const bool edge_ready =
          physical_edge_ready && local_corridor_ready &&
          downstream_calendar_ready && downstream_queue_ready;
      ready = ready || edge_ready;
      if (edge_ready) {
        continue;
      }
      if (!physical_edge_ready) {
        observed.consider(
            G4IRSF17SourceWaitReason::kPhysicalFaultOrGeneration,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kPhysicalEdge,
            downstream,
            node,
            downstream,
            static_cast<std::uint64_t>(
                physical->second.physical_generation));
      }
      if (snapshot->second.g4irsf17_local_blocker.valid) {
        const auto& local =
            snapshot->second.g4irsf17_local_blocker;
        observed.consider(
            local.blocker.reason,
            local.blocker.resource,
            local.blocker.blocker_node,
            local.blocker.resource_from_node,
            local.blocker.resource_to_node,
            local.generation);
      }
      if (!downstream_queue_ready) {
        observed.consider(
            G4IRSF17SourceWaitReason::kDestinationQueueCapacity,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kDestinationQueue,
            downstream,
            node,
            downstream,
            snapshot->second.generation);
      }
      if (!downstream_calendar_ready) {
        const bool merge_token =
            graph_.incoming_degree(downstream) > 1 ||
            snapshot->second.g4irsf17_merge_pending_request_count > 0 ||
            snapshot->second.g4irsf17_merge_active_grant_count > 0;
        observed.consider(
            merge_token
                ? G4IRSF17SourceWaitReason::kDestinationMergeToken
                : G4IRSF17SourceWaitReason::kOtherExplicitReason,
            merge_token
                ? event_runtime_detail::G4IRSF17SourceWaitResource::
                      kDestinationMergeToken
                : event_runtime_detail::G4IRSF17SourceWaitResource::
                      kOtherLocalResource,
            downstream,
            node,
            downstream,
            merge_token
                ? snapshot->second.g4irsf17_merge_generation
                : snapshot->second.generation);
      }
      if (!local_corridor_ready) {
        observed.consider(
            G4IRSF17SourceWaitReason::kOtherExplicitReason,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kOtherLocalResource,
            downstream,
            node,
            downstream,
            corridors_[resource_corridor_key(node, downstream)]
                .generation());
      }
    }
    if (!ready && blocker != nullptr) {
      if (!observed.valid) {
        observed.consider(
            G4IRSF17SourceWaitReason::kOtherExplicitReason,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kOtherLocalResource,
            node,
            node,
            node,
            0);
      }
      *blocker = observed;
    }
    return ready;
  }

  bool merge_credit_triggered(int node) const {
    for (const int target : graph_.outgoing(node)) {
      if (graph_.incoming_degree(target) <= 1) {
        continue;
      }
      const auto beacon = congestion_beacons_.find(target);
      int pressure =
          beacon == congestion_beacons_.end()
              ? 0
              : beacon->second.queue_length +
                    beacon->second.scheduled_incoming;
      const auto target_state = junctions_.find(target);
      if (target_state != junctions_.end()) {
        pressure = std::max(
            pressure,
            static_cast<int>(target_state->second.queue.size()) +
                target_state->second.scheduled_incoming);
      }
      if (pressure >=
          config_.selective_credit_contention_threshold) {
        return true;
      }
    }
    return false;
  }

  bool contention_credit_triggered(int node) const {
    const auto local = junctions_.find(node);
    if (local != junctions_.end() &&
        static_cast<int>(local->second.queue.size()) >
            config_.selective_credit_contention_threshold) {
      return true;
    }
    for (const int target : graph_.outgoing(node)) {
      const auto beacon = congestion_beacons_.find(target);
      const int queue_length =
          beacon == congestion_beacons_.end()
              ? 0
              : beacon->second.queue_length;
      const int scheduled =
          beacon == congestion_beacons_.end()
              ? 0
              : beacon->second.scheduled_incoming;
      const auto target_state = junctions_.find(target);
      const int current_queue =
          target_state == junctions_.end()
              ? queue_length
              : std::max(
                    queue_length,
                    static_cast<int>(
                        target_state->second.queue.size()));
      const int current_scheduled =
          target_state == junctions_.end()
              ? scheduled
              : std::max(
                    scheduled,
                    target_state->second.scheduled_incoming);
      if (current_scheduled >=
              config_.selective_credit_contention_threshold ||
          (graph_.incoming_degree(target) > 1 &&
           current_queue >=
               config_.selective_credit_contention_threshold) ||
          (config_.local_queue_capacity > 0 &&
           current_queue + current_scheduled >=
               config_.local_queue_capacity)) {
        return true;
      }
      const auto physical = physical_faults_.find(
          event_runtime_detail::directed_key(node, target));
      if (physical != physical_faults_.end() &&
          physical->second.physical_generation > 0) {
        // A non-zero generation is a bounded local fault/recovery trigger.
        // The ledger still validates the exact current generation at bind.
        return true;
      }
    }
    return false;
  }

  bool first_edge_credit_required_for_bag(const BagState& bag,
                                          int node) const {
    if (bag.first_edge_credit_consumed ||
        node == bag.request.goal) {
      return false;
    }
    const auto mode = canonical_admission_mode();
    if (mode == "expiring_first_edge_credit") {
      return true;
    }
    if (mode == "merge_only_first_edge_credit") {
      return merge_credit_triggered(node);
    }
    if (mode ==
        "contention_triggered_first_edge_credit") {
      return contention_credit_triggered(node);
    }
    return false;
  }

  bool observe_first_edge_credit_requirement(const BagState& bag,
                                             int node) {
    const bool required =
        first_edge_credit_required_for_bag(bag, node);
    const auto mode = canonical_admission_mode();
    if (mode == "merge_only_first_edge_credit" ||
        mode == "contention_triggered_first_edge_credit") {
      if (required) {
        ++result_.summary.selective_credit_trigger_count;
        if (mode == "merge_only_first_edge_credit") {
          ++result_.summary.selective_credit_merge_trigger_count;
        } else {
          ++result_.summary
                .selective_credit_contention_trigger_count;
        }
      } else {
        ++result_.summary
              .selective_credit_low_load_bypass_count;
      }
    }
    return required;
  }

  FirstEdgeCreditUseContext credit_use_context(const BagState& bag,
                                               int from_node,
                                               int to_node,
                                               double time) const {
    FirstEdgeCreditUseContext context;
    context.owner = bag.request.runtime_bag_id;
    context.from_node = from_node;
    context.to_node = to_node;
    context.goal = bag.request.goal;
    context.now = time;
    const auto snapshot = congestion_beacons_.find(to_node);
    context.generation =
        snapshot == congestion_beacons_.end() ? 0 : snapshot->second.generation;
    const long long directed =
        event_runtime_detail::directed_key(from_node, to_node);
    const auto physical = physical_faults_.find(directed);
    context.fault_generation =
        physical == physical_faults_.end() ? 0 : physical->second.physical_generation;
    context.physical_fault_active =
        physical != physical_faults_.end() && physical->second.active_count > 0;
    return context;
  }

  bool ensure_first_edge_credit(BagState& bag,
                                int node,
                                double time,
                                double earliest_entry,
                                bool dispatch_retry,
                                event_runtime_detail::
                                    G4IRSF17SourceBlockerObservation*
                                        blocker = nullptr) {
    if (bag.first_edge_credit_consumed || node == bag.request.goal) {
      return true;
    }

    bool replacing_invalid_credit = false;
    if (bag.first_edge_credit_id != 0) {
      const auto* existing = credit_ledger_.find(bag.first_edge_credit_id);
      if (existing != nullptr) {
        const auto validation = credit_ledger_.validate(
            bag.first_edge_credit_id,
            credit_use_context(bag, node, existing->to_node, time));
        if (validation.accepted) {
          return true;
        }
      }
      bag.first_edge_credit_id = 0;
      replacing_invalid_credit = true;
    }

    struct CandidateOffer {
      int downstream = -1;
      double score = 0.0;
      FirstEdgeCreditIssueRequest request;
    };
    event_runtime_detail::G4IRSF17SourceBlockerObservation observed;
    observed.consider(
        G4IRSF17SourceWaitReason::kFirstEdgeCreditUnavailable,
        event_runtime_detail::G4IRSF17SourceWaitResource::
            kFirstEdgeCredit,
        node,
        node,
        node,
        credit_ledger_.counters().issue_attempt_count);
    std::vector<CandidateOffer> offers;
    std::vector<int> outgoing = graph_.outgoing(node);
    std::sort(outgoing.begin(), outgoing.end());
    for (const int downstream : outgoing) {
      ++result_.summary.source_admission_beacon_read_count;
      const auto snapshot = congestion_beacons_.find(downstream);
      const long long directed =
          event_runtime_detail::directed_key(node, downstream);
      const auto physical = physical_faults_.find(directed);
      const bool physical_active =
          physical != physical_faults_.end() && physical->second.active_count > 0;
      const int fault_generation =
          physical == physical_faults_.end() ? 0 : physical->second.physical_generation;
      const double travel =
          std::max(graph_.edge(node, downstream).travel_time(),
                   config_.minimum_service_seconds);
      const double projected_arrival = earliest_entry + travel;

      int pressure = 0;
      bool downstream_calendar_ready = false;
      bool downstream_queue_ready = false;
      if (snapshot != congestion_beacons_.end()) {
        pressure = snapshot->second.queue_length +
                   snapshot->second.scheduled_incoming;
        const auto pressure_mode = canonical_pressure_mode();
        if (pressure_mode == "C2_goal_conditioned_differential" ||
            pressure_mode == "C3_distance_biased_differential") {
          const auto queue =
              snapshot->second.queue_length_by_goal.find(bag.request.goal);
          const auto incoming =
              snapshot->second.scheduled_incoming_by_goal.find(bag.request.goal);
          pressure =
              (queue == snapshot->second.queue_length_by_goal.end()
                   ? 0
                   : queue->second) +
              (incoming ==
                       snapshot->second.scheduled_incoming_by_goal.end()
                   ? 0
                   : incoming->second);
        }
        downstream_calendar_ready =
            !uses_destination_calendar(downstream,
                                       bag.request.goal) ||
            snapshot->second.service_calendar_reserved_until <=
                projected_arrival + event_runtime_detail::kEpsilon;
        downstream_queue_ready =
            config_.local_queue_capacity <= 0 ||
            pressure < config_.local_queue_capacity;
      }
      if (canonical_admission_mode() ==
              "merge_only_first_edge_credit" ||
          canonical_admission_mode() ==
              "contention_triggered_first_edge_credit") {
        const auto target_state = junctions_.find(downstream);
        if (target_state != junctions_.end()) {
          pressure = std::max(
              pressure,
              static_cast<int>(target_state->second.queue.size()) +
                  target_state->second.scheduled_incoming);
          downstream_queue_ready =
              config_.local_queue_capacity <= 0 ||
              pressure < config_.local_queue_capacity;
        }
      }
      result_.summary.source_admission_max_observed_downstream_pressure =
          std::max(result_.summary.source_admission_max_observed_downstream_pressure,
                   pressure);
      if (canonical_admission_mode() ==
              "merge_only_first_edge_credit" &&
          (graph_.incoming_degree(downstream) <= 1 ||
           pressure <
               config_.selective_credit_contention_threshold)) {
        continue;
      }

      bool local_corridor_ready = true;
      if (uses_corridor_calendar()) {
        auto& corridor = corridors_[resource_corridor_key(node, downstream)];
        corridor.purge(time);
        const double reservation_duration =
            corridor_reservation_duration(travel);
        local_corridor_ready = corridor.available(
            earliest_entry,
            earliest_entry + reservation_duration,
            bag.request.runtime_bag_id);
      }

      FirstEdgeCreditIssueRequest request;
      request.from_node = node;
      request.to_node = downstream;
      request.goal = bag.request.goal;
      request.earliest = earliest_entry;
      request.latest = earliest_entry + config_.credit_validity_seconds;
      request.generation =
          snapshot == congestion_beacons_.end() ? 0 : snapshot->second.generation;
      request.expiry = request.latest;
      request.capacity = 1;
      request.owner_or_unbound = bag.request.runtime_bag_id;
      request.fault_generation = fault_generation;
      request.now = time;
      request.snapshot_received_at =
          snapshot == congestion_beacons_.end() ? 0.0 : snapshot->second.received_at;
      request.max_snapshot_age = config_.credit_snapshot_max_age_seconds;
      request.edge_capacity = config_.credit_capacity_per_edge;
      request.physical_fault_active = physical_active;

      // Missing/stale/faulted snapshots are still passed to the ledger so
      // their fail-closed reason is counted.  Ordinary resource unavailability
      // remains a local hold and never creates a speculative offer.
      const bool snapshot_usable =
          snapshot != congestion_beacons_.end() &&
          time - snapshot->second.received_at <=
              config_.credit_snapshot_max_age_seconds +
                  event_runtime_detail::kEpsilon;
      if (!snapshot_usable || physical_active) {
        observed.consider(
            G4IRSF17SourceWaitReason::kPhysicalFaultOrGeneration,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kPhysicalEdge,
            downstream,
            node,
            downstream,
            physical_active
                ? static_cast<std::uint64_t>(fault_generation)
                : (snapshot == congestion_beacons_.end()
                       ? 0
                       : snapshot->second.generation));
        const auto rejected = credit_ledger_.issue(request);
        (void)rejected;
        continue;
      }
      if (!local_corridor_ready || !downstream_calendar_ready ||
          !downstream_queue_ready) {
        if (snapshot != congestion_beacons_.end() &&
            snapshot->second.g4irsf17_local_blocker.valid) {
          const auto& local =
              snapshot->second.g4irsf17_local_blocker;
          observed.consider(
              local.blocker.reason,
              local.blocker.resource,
              local.blocker.blocker_node,
              local.blocker.resource_from_node,
              local.blocker.resource_to_node,
              local.generation);
        }
        if (!downstream_queue_ready) {
          observed.consider(
              G4IRSF17SourceWaitReason::kDestinationQueueCapacity,
              event_runtime_detail::G4IRSF17SourceWaitResource::
                  kDestinationQueue,
              downstream,
              node,
              downstream,
              snapshot == congestion_beacons_.end()
                  ? 0
                  : snapshot->second.generation);
        }
        if (!downstream_calendar_ready) {
          const bool merge_token =
              graph_.incoming_degree(downstream) > 1 ||
              (snapshot != congestion_beacons_.end() &&
               (snapshot->second
                        .g4irsf17_merge_pending_request_count > 0 ||
                snapshot->second.g4irsf17_merge_active_grant_count > 0));
          observed.consider(
              merge_token
                  ? G4IRSF17SourceWaitReason::kDestinationMergeToken
                  : G4IRSF17SourceWaitReason::kOtherExplicitReason,
              merge_token
                  ? event_runtime_detail::G4IRSF17SourceWaitResource::
                        kDestinationMergeToken
                  : event_runtime_detail::G4IRSF17SourceWaitResource::
                        kOtherLocalResource,
              downstream,
              node,
              downstream,
              snapshot == congestion_beacons_.end()
                  ? 0
                  : (merge_token
                         ? snapshot->second.g4irsf17_merge_generation
                         : snapshot->second.generation));
        }
        continue;
      }

      double score = static_potential(downstream, bag.request.goal) + travel;
      const auto pressure_mode = canonical_pressure_mode();
      if (pressure_mode == "C1_absolute_downstream_queue_penalty") {
        score += config_.pressure_weight * static_cast<double>(pressure);
      } else if (pressure_mode == "C2_goal_conditioned_differential" ||
                 pressure_mode == "C3_distance_biased_differential") {
        const int local_goal_count = static_cast<int>(std::count_if(
            junctions_[node].source_queue.begin(),
            junctions_[node].source_queue.end(),
            [&](int runtime_bag_id) {
              const auto found = bags_.find(runtime_bag_id);
              return found != bags_.end() &&
                     found->second.request.goal == bag.request.goal;
            }));
        const double differential =
            static_cast<double>(local_goal_count - pressure);
        const double estimated_service_rate =
            1.0 / std::max(config_.minimum_service_seconds,
                           uses_corridor_calendar()
                               ? corridor_reservation_duration(travel)
                               : config_.minimum_service_seconds);
        score -= config_.pressure_weight *
                 std::max(0.0, differential * estimated_service_rate);
        if (pressure_mode == "C3_distance_biased_differential") {
          score += config_.pressure_distance_bias *
                   static_potential(downstream, bag.request.goal);
        }
      }
      offers.push_back(CandidateOffer{downstream, score, request});
    }

    std::sort(offers.begin(), offers.end(), [](const auto& left, const auto& right) {
      if (left.score != right.score) {
        return left.score < right.score;
      }
      return left.downstream < right.downstream;
    });
    for (const auto& offer : offers) {
      const auto issued = credit_ledger_.issue(offer.request);
      if (!issued.accepted) {
        continue;
      }
      bag.first_edge_credit_id = issued.credit.credit_id;
      if (replacing_invalid_credit || dispatch_retry) {
        ++result_.summary.first_edge_credit_reissue_count;
      }
      return true;
    }
    if (blocker != nullptr) {
      *blocker = observed;
    }
    return false;
  }

  void request_one_hop_credit_snapshot_refresh(int node, double time) {
    for (const int downstream : graph_.outgoing(node)) {
      const auto snapshot = congestion_beacons_.find(downstream);
      if (snapshot != congestion_beacons_.end() &&
          time - snapshot->second.received_at <=
              config_.credit_snapshot_max_age_seconds +
                  event_runtime_detail::kEpsilon) {
        continue;
      }
      schedule_passive(JunctionEventType::kCongestionBeaconUpdate,
                       time,
                       -1,
                       downstream,
                       node,
                       downstream,
                       "credit_one_hop_snapshot_refresh");
    }
  }

  void process_service_complete(const RuntimeEvent& event) {
    auto found = bags_.find(event.task_id);
    if (found == bags_.end() || found->second.status != BagStatus::kInService) {
      return;
    }
    // Count only service that reached its actual completion event. Merely
    // reserving or preparing service (including a rolled-back PIBT batch)
    // never contributes simulated service time.
    found->second.node_service_time_seconds +=
        service_duration(event.node);
    if (g4irsf17_source_policy_enabled() ||
        config_.enable_g4irsf17_causal_source_features) {
      junctions_[event.node]
          .g4irsf17_source_temporal.service_completions.record(event.time);
    }
    schedule(JunctionEventType::kArriveJunction,
             event.time,
             event.task_id,
             event.node,
             event.from_node,
             event.to_node);
    schedule_passive(JunctionEventType::kCongestionBeaconUpdate,
                     event.time,
                     event.task_id,
                     event.node,
                     event.from_node,
                     event.to_node,
                     "service_completion_snapshot");
    append_event_trace(event,
                       event.task_id,
                       event.node,
                       event.from_node,
                       event.to_node,
                       "junction_service_complete",
                       0);
  }

  void process_arrive(const RuntimeEvent& event) {
    auto& controller = junctions_[event.node];
    if (event.retry) {
      if (!controller.junction_wakeup_pending ||
          controller.junction_wakeup_generation != event.wakeup_generation) {
        return;
      }
      controller.junction_wakeup_pending = false;
    } else {
      auto found = bags_.find(event.task_id);
      if (found == bags_.end() || found->second.status != BagStatus::kInService) {
        return;
      }
      auto& bag = found->second;
      if (controller.scheduled_incoming > 0 && event.from_node >= 0) {
        --controller.scheduled_incoming;
        auto incoming =
            controller.scheduled_incoming_by_goal.find(bag.request.goal);
        if (incoming != controller.scheduled_incoming_by_goal.end()) {
          incoming->second = std::max(0, incoming->second - 1);
          if (incoming->second == 0) {
            controller.scheduled_incoming_by_goal.erase(incoming);
          }
        }
      }
      bag.current = event.node;
      remember_node(bag, event.node);
      if (event.node == bag.request.goal) {
        complete_bag(bag, event.time);
        schedule_passive(JunctionEventType::kCongestionBeaconUpdate,
                         event.time,
                         event.task_id,
                         event.node,
                         event.from_node,
                         event.node,
                         "goal_service_release_snapshot");
        append_event_trace(event,
                           bag.request.runtime_bag_id,
                           event.node,
                           event.from_node,
                           event.node,
                           "goal_reached",
                           0);
        if (!controller.queue.empty()) {
          schedule_junction_wakeup(event.node, event.time);
        }
        return;
      }
      bag.status = BagStatus::kJunctionQueue;
      bag.junction_enqueued_at = event.time;
      bag.local_enqueue_sequence = next_local_enqueue_sequence_++;
      if (uses_destination_merge_grants()) {
        ++destination_merge_bag_state(
              bag.request.runtime_bag_id)
              .junction_queue_generation;
      }
      controller.queue.push_back(event.task_id);
      update_queue_maxima(controller);
      observe_junction_enqueue(event.node, event.time);
      schedule_passive(JunctionEventType::kLocalQueueUpdate,
                       event.time,
                       event.task_id,
                       event.node,
                       event.from_node,
                       event.node,
                       "junction_enqueue");
    }

    if (batches_junction_same_timestamp()) {
      schedule_junction_wakeup(event.node, event.time);
      append_event_trace(event,
                         event.task_id,
                         event.node,
                         event.from_node,
                         event.node,
                         "junction_arrival_enqueue",
                         0);
      return;
    }

    dispatch_junction_once(event, false);
  }

  void process_junction_arbitration(const RuntimeEvent& event) {
    if (!consume_junction_arbitration_wakeup(event)) {
      return;
    }
    if (junctions_[event.node].queue.empty()) {
      ++result_.summary.stale_arbitration_event_count;
      return;
    }
    dispatch_junction_once(event, true);
  }

  DestinationMergeGrantController& destination_merge_controller(
      int destination_node) {
    auto found =
        destination_merge_controllers_.find(destination_node);
    if (found != destination_merge_controllers_.end()) {
      return found->second;
    }
    return destination_merge_controllers_
        .try_emplace(
            destination_node,
            destination_node,
            static_cast<std::size_t>(
                config_.merge_grant_max_pending_requests),
            static_cast<std::size_t>(
                config_.merge_grant_lifecycle_limit))
        .first->second;
  }

  [[nodiscard]] double jit_destination_merge_ready_time(
      const DestinationMergeRequest& request,
      double now) const {
    const auto destination =
        junctions_.find(request.destination_merge_node);
    if (destination == junctions_.end()) {
      return std::numeric_limits<double>::infinity();
    }
    const double arrival =
        now + request.exact_edge_travel_seconds;
    const double service_start =
        destination->second.service_calendar.earliest_start(
            arrival, request.destination_service_seconds);
    return std::max(
        now,
        service_start - request.exact_edge_travel_seconds);
  }

  [[nodiscard]] double next_jit_destination_merge_ready_time(
      const DestinationMergeGrantController& controller,
      double now) const {
    double ready = std::numeric_limits<double>::infinity();
    for (const auto& pending : controller.pending_) {
      ready = std::min(
          ready,
          jit_destination_merge_ready_time(pending.request, now));
    }
    return ready;
  }

  void refresh_jit_destination_merge_pending(
      DestinationMergeGrantController& controller,
      double now) {
    if (!uses_jit_destination_merge_grants()) {
      return;
    }
    auto destination = junctions_.find(controller.destination_node());
    if (destination == junctions_.end()) {
      return;
    }
    const auto calendar_generation =
        destination->second.service_calendar.generation();
    const int pressure =
        static_cast<int>(destination->second.queue.size()) +
        destination->second.scheduled_incoming;
    bool changed = false;
    for (auto& pending : controller.pending_) {
      auto& request = pending.request;
      const auto bag = bags_.find(request.runtime_bag_id);
      const double ready =
          jit_destination_merge_ready_time(request, now);
      request.request_time = now;
      request.earliest_edge_entry = now;
      request.projected_arrival =
          now + request.exact_edge_travel_seconds;
      request.destination_calendar_generation =
          calendar_generation;
      request.downstream_queue_pressure = pressure;
      request.wait_age = destination_merge_request_age(request, now);
      if (bag != bags_.end()) {
        request.deadline_slack =
            bag->second.request.deadline >= 0.0
                ? bag->second.request.deadline - now
                : std::numeric_limits<double>::max();
        request.source_release_age =
            std::max(0.0, now - bag->second.request.release_time);
        request.local_queue_age =
            std::max(0.0, now - bag->second.junction_enqueued_at);
      }
      request.expiry = std::max(
          now + config_.retry_interval,
          std::isfinite(ready)
              ? ready + config_.retry_interval
              : now + config_.retry_interval);
      DestinationMergeRequest identity = request;
      identity.lifecycle_request_snapshot.reset();
      request.lifecycle_request_snapshot =
          std::make_shared<const DestinationMergeRequest>(
              std::move(identity));
      changed = true;
    }
    if (changed) {
      ++controller.generation_;
    }
  }

  void schedule_next_jit_destination_merge_opportunity(
      DestinationMergeGrantController& controller,
      double now,
      bool allow_immediate) {
    if (!uses_jit_destination_merge_grants() ||
        controller.pending_.empty()) {
      return;
    }
    refresh_jit_destination_merge_pending(controller, now);
    const double ready =
        next_jit_destination_merge_ready_time(controller, now);
    if (!std::isfinite(ready) ||
        (!allow_immediate &&
         ready <= now + event_runtime_detail::kEpsilon)) {
      return;
    }
    schedule_destination_merge_wakeup(
        controller.destination_node(), ready);
  }

  struct G4IRSF18MergeRuntimeDecision {
    DestinationMergeGrantController::PendingRecord* j2_baseline = nullptr;
    DestinationMergeGrantController::PendingRecord* proposed = nullptr;
    DestinationMergeGrantController::PendingRecord* chosen = nullptr;
    G4IRSF18MergeFeatureBatch feature_batch;
    std::vector<double> scores;
    std::string reason = "OFF";
    bool evaluated = false;
    bool proposal_available = false;
    bool applied = false;
    bool out_of_distribution = false;
    bool invalid = false;
    bool fallback = false;
  };

  G4IRSF18MergeRuntimeDecision decide_g4irsf18_merge_policy(
      const std::vector<
          DestinationMergeGrantController::PendingRecord*>& candidates,
      DestinationMergeGrantController::PendingRecord* fifo_baseline,
      DestinationMergeGrantController::PendingRecord* j2_baseline,
      double event_time) {
    G4IRSF18MergeRuntimeDecision decision;
    decision.j2_baseline = j2_baseline;
    decision.chosen = j2_baseline;
    if (!g4irsf18_merge_policy_enabled()) {
      return decision;
    }

    auto& summary = result_.summary;
    const auto& policy = config_.g4irsf18_merge_policy;
    ++summary.g4irsf18_merge_model_opportunity_count;
    if (candidates.size() < 2U) {
      decision.reason = "SINGLETON_J2_NO_MODEL";
      return decision;
    }
    ++summary.g4irsf18_merge_model_eligible_count;

    std::vector<const DestinationMergeRequest*> requests;
    requests.reserve(candidates.size());
    for (const auto* candidate : candidates) {
      requests.push_back(&candidate->request);
    }
    decision.feature_batch =
        g4irsf18_merge_feature_batch(requests, event_time);
    decision.out_of_distribution =
        decision.feature_batch.out_of_distribution;
    decision.invalid = decision.feature_batch.invalid;

    if (!summary.g4irsf18_merge_kill_switch_tripped &&
        (summary.reservation_conflicts > 0 ||
         summary.physical_fault_edge_entry_violation_count > 0)) {
      summary.g4irsf18_merge_kill_switch_tripped = true;
      summary.g4irsf18_merge_kill_switch_reason =
          "RUNTIME_SAFETY_COUNTER_TRIP";
      ++summary.g4irsf18_merge_kill_switch_trip_count;
    }
    const auto j2_fallback =
        [&](const char* reason, std::uint64_t* reason_counter) {
          decision.chosen = j2_baseline;
          decision.fallback = true;
          decision.reason = reason;
          ++summary.g4irsf18_merge_model_fallback_count;
          ++summary.g4irsf18_merge_j2_fallback_count;
          if (reason_counter != nullptr) {
            ++*reason_counter;
          }
        };
    if (summary.g4irsf18_merge_kill_switch_tripped) {
      j2_fallback(
          "KILL_SWITCH_J2_FALLBACK",
          &summary.g4irsf18_merge_kill_switch_fallback_count);
      return decision;
    }
    const bool starvation_guard =
        std::any_of(
            candidates.begin(), candidates.end(),
            [&](const auto* candidate) {
              return destination_merge_request_age(
                         candidate->request, event_time) +
                         event_runtime_detail::kEpsilon >=
                     config_.starvation_threshold;
            });
    if (starvation_guard) {
      j2_fallback(
          "STARVATION_GUARD_J2_FALLBACK",
          &summary.g4irsf18_merge_starvation_guard_fallback_count);
      return decision;
    }
    if (!policy.artifact_valid()) {
      decision.invalid = true;
      ++summary.g4irsf18_merge_model_invalid_count;
      j2_fallback(
          "INVALID_ARTIFACT_J2_FALLBACK",
          nullptr);
      return decision;
    }
    if (decision.feature_batch.invalid) {
      ++summary.g4irsf18_merge_model_invalid_count;
      if (decision.feature_batch.out_of_distribution) {
        ++summary.g4irsf18_merge_model_ood_count;
      }
      j2_fallback(
          "INVALID_LOCAL_FEATURE_J2_FALLBACK",
          nullptr);
      return decision;
    }
    if (decision.feature_batch.out_of_distribution) {
      ++summary.g4irsf18_merge_model_ood_count;
      j2_fallback(
          "OOD_LOCAL_FEATURE_J2_FALLBACK",
          nullptr);
      return decision;
    }

    decision.scores.reserve(candidates.size());
    for (const auto& row : decision.feature_batch.rows) {
      const double score = policy.score(row.values);
      if (!std::isfinite(score)) {
        decision.invalid = true;
        ++summary.g4irsf18_merge_model_invalid_count;
        j2_fallback(
            "NONFINITE_SCORE_J2_FALLBACK",
            nullptr);
        return decision;
      }
      decision.scores.push_back(score);
    }
    decision.evaluated = true;
    const auto best_score = std::max_element(
        decision.scores.begin(), decision.scores.end());
    const std::size_t best_index = static_cast<std::size_t>(
        std::distance(decision.scores.begin(), best_score));
    const bool score_tie =
        std::count_if(
            decision.scores.begin(), decision.scores.end(),
            [&](double score) {
              return std::abs(score - *best_score) <= 1.0e-12;
            }) > 1;
    decision.proposed = score_tie ? fifo_baseline : candidates[best_index];
    decision.proposal_available = true;
    ++summary.g4irsf18_merge_model_proposal_count;

    if (policy.shadow()) {
      j2_fallback(
          "SHADOW_J2_FALLBACK",
          &summary.g4irsf18_merge_shadow_fallback_count);
      return decision;
    }
    const bool authorized =
        (policy.research_closed_loop() &&
         policy.research_closed_loop_authorized &&
         policy.fixed_research_workload) ||
        (policy.production_closed_loop() &&
         policy.artifact_production_closed_loop_authorized &&
         policy.production_closed_loop_authorized &&
         policy.offline_gate_passed);
    if (!authorized) {
      j2_fallback(
          "RUNTIME_AUTHORIZATION_J2_FALLBACK",
          &summary.g4irsf18_merge_authorization_fallback_count);
      return decision;
    }
    if (score_tie) {
      decision.chosen = fifo_baseline;
      decision.fallback = true;
      decision.reason = "MODEL_SCORE_TIE_FIFO_FALLBACK";
      ++summary.g4irsf18_merge_model_fallback_count;
      ++summary.g4irsf18_merge_tie_fifo_fallback_count;
      return decision;
    }

    ++summary.g4irsf18_merge_coverage_eligible_seen_count;
    const auto coverage_allowance = static_cast<std::uint64_t>(std::floor(
        static_cast<double>(
            summary.g4irsf18_merge_coverage_eligible_seen_count) *
            policy.coverage_cap +
        1.0e-12));
    if (summary.g4irsf18_merge_model_applied_count >=
        coverage_allowance) {
      j2_fallback(
          "COVERAGE_CAP_J2_FALLBACK",
          &summary.g4irsf18_merge_coverage_cap_fallback_count);
      return decision;
    }

    const bool action_mutation =
        decision.proposed->request.request_id !=
        j2_baseline->request.request_id;
    auto bag_state =
        g4irsf14_state_->destination_merge_bags.find(
            decision.proposed->request.runtime_bag_id);
    if (bag_state == g4irsf14_state_->destination_merge_bags.end()) {
      decision.invalid = true;
      ++summary.g4irsf18_merge_model_invalid_count;
      j2_fallback(
          "MISSING_LOCAL_OWNER_STATE_J2_FALLBACK",
          nullptr);
      return decision;
    }
    if (action_mutation &&
        bag_state->second.g4irsf18_merge_override_count >=
            policy.max_overrides_per_segment) {
      j2_fallback(
          "SEGMENT_OVERRIDE_CAP_J2_FALLBACK",
          &summary.g4irsf18_merge_override_cap_fallback_count);
      return decision;
    }

    decision.chosen = decision.proposed;
    decision.applied = true;
    decision.reason = action_mutation
                          ? "MODEL_APPLIED_OVERRIDE"
                          : "MODEL_APPLIED_SAME_AS_J2";
    ++summary.g4irsf18_merge_model_applied_count;
    ++summary.g4irsf18_merge_model_ownership_count;
    if (action_mutation) {
      ++summary.g4irsf18_merge_distinct_action_mutation_count;
      ++bag_state->second.g4irsf18_merge_override_count;
    }
    return decision;
  }

  void append_jit_merge_service_opportunity(
      std::uint64_t opportunity_id,
      double event_time,
      int destination_node,
      std::uint64_t controller_generation,
      const std::vector<
          DestinationMergeGrantController::PendingRecord*>& candidates,
      const DestinationMergeRequest& baseline,
      const DestinationMergeRequest& chosen,
      const G4IRSF18MergeRuntimeDecision* model_decision) {
    if (!config_.enable_opportunity_telemetry &&
        !g4irsf18_merge_policy_enabled()) {
      return;
    }
    const auto timing = destination_merge_grant_timing_mode_name(
        canonical_merge_grant_timing_mode());
    const auto limit = static_cast<std::size_t>(
        config_.opportunity_trace_limit);
    const std::size_t remaining =
        result_.merge_service_opportunities.size() < limit
            ? limit - result_.merge_service_opportunities.size()
            : 0;
    result_.merge_service_opportunities.reserve(
        result_.merge_service_opportunities.size() +
        std::min(remaining, candidates.size()));
    for (std::size_t candidate_index = 0;
         candidate_index < candidates.size(); ++candidate_index) {
      const auto* candidate = candidates[candidate_index];
      ++result_.summary
            .merge_grant_opportunity_trace_total_count;
      if (result_.merge_service_opportunities.size() >= limit) {
        ++result_.summary
              .merge_grant_opportunity_trace_dropped_count;
        continue;
      }
      const auto& request = candidate->request;
      EventRuntimeMergeServiceOpportunityRow row;
      row.opportunity_id = opportunity_id;
      row.event_time = event_time;
      row.destination_node = destination_node;
      row.controller_generation = controller_generation;
      row.timing_mode = timing;
      row.candidate_count = static_cast<int>(candidates.size());
      row.baseline_winner_request_id = baseline.request_id;
      row.chosen_winner_request_id = chosen.request_id;
      row.candidate_request_id = request.request_id;
      row.upstream_node = request.upstream_node;
      row.projected_arrival = request.projected_arrival;
      row.deadline_slack = request.deadline_slack;
      row.wait_age = destination_merge_request_age(
          request, event_time);
      row.destination_service_seconds =
          request.destination_service_seconds;
      row.downstream_queue_pressure =
          request.downstream_queue_pressure;
      row.route_score = request.route_score;
      row.static_remaining = request.static_remaining;
      row.task_class_code = request.task_class_code;
      row.task_class = request.task_class;
      row.storage_leg = request.storage_leg;
      row.baseline_winner =
          request.request_id == baseline.request_id;
      row.chosen_winner =
          request.request_id == chosen.request_id;
      if (model_decision != nullptr) {
        row.model_policy_mode =
            config_.g4irsf18_merge_policy.mode;
        row.model_feature_contract = kG4IRSF18MergeFeatureContract;
        row.model_reason = model_decision->reason;
        row.model_evaluated = model_decision->evaluated;
        row.model_score_available =
            candidate_index < model_decision->scores.size();
        if (row.model_score_available) {
          row.model_score = model_decision->scores[candidate_index];
        }
        row.model_proposed =
            model_decision->proposed != nullptr &&
            request.request_id ==
                model_decision->proposed->request.request_id;
        row.model_applied =
            model_decision->applied && row.model_proposed;
        row.model_chosen =
            model_decision->chosen != nullptr &&
            request.request_id ==
                model_decision->chosen->request.request_id;
        row.model_out_of_distribution =
            model_decision->out_of_distribution;
        row.model_invalid = model_decision->invalid;
        row.model_fallback = model_decision->fallback;
        row.model_baseline_request_id =
            model_decision->j2_baseline == nullptr
                ? 0
                : model_decision->j2_baseline->request.request_id;
        row.model_proposed_request_id =
            model_decision->proposed == nullptr
                ? 0
                : model_decision->proposed->request.request_id;
        if (candidate_index <
            model_decision->feature_batch.rows.size()) {
          row.model_features =
              model_decision->feature_batch.rows[candidate_index].values;
        }
      }
      result_.merge_service_opportunities.push_back(
          std::move(row));
      ++result_.summary
            .merge_grant_opportunity_trace_stored_count;
    }
  }

  [[nodiscard]] bool junction_has_unrepresented_merge_work(
      const JunctionState& junction) const noexcept {
    if (!uses_jit_destination_merge_grants() ||
        g4irsf14_state_ == nullptr) {
      return !junction.queue.empty();
    }
    for (const int runtime_bag_id : junction.queue) {
      const auto state =
          g4irsf14_state_->destination_merge_bags.find(
              runtime_bag_id);
      if (state ==
              g4irsf14_state_->destination_merge_bags.end() ||
          state->second.pending_request_id == 0) {
        return true;
      }
    }
    return false;
  }

  bool submit_destination_merge_request(
      BagState& bag,
      int upstream_node,
      int destination_node,
      double time,
      EventDecisionTraceRow& trace) {
    auto& bag_merge =
        destination_merge_bag_state(
            bag.request.runtime_bag_id);
    if (bag_merge.pending_request_id != 0) {
      return true;
    }
    const auto& edge =
        graph_.edge(upstream_node, destination_node);
    const double travel =
        std::max(edge.travel_time(),
                 config_.minimum_service_seconds);
    const long long directed =
        event_runtime_detail::directed_key(
            upstream_node, destination_node);
    const auto physical = physical_faults_.find(directed);
    const auto advertised =
        advertised_faults_.find(directed);

    DestinationMergeRequest request;
    request.lineage = next_merge_request_lineage_;
    request.request_id = request.lineage;
    request.request_generation =
        bag_merge.request_generation + 1;
    request.junction_queue_generation =
        bag_merge.junction_queue_generation;
    request.runtime_bag_id =
        bag.request.runtime_bag_id;
    request.task_id = bag.request.task_id;
    request.segment_id = bag.request.segment_id;
    request.upstream_node = upstream_node;
    request.destination_merge_node = destination_node;
    request.requested_directed_edge =
        MergeDirectedEdge{upstream_node, destination_node};
    request.request_time = time;
    request.fifo_request_time =
        bag_merge.first_contention_time < 0.0
            ? time
            : bag_merge.first_contention_time;
    request.earliest_edge_entry = time;
    request.exact_edge_travel_seconds = travel;
    request.projected_arrival = time + travel;
    request.goal = bag.request.goal;
    const auto selected_candidate = std::find_if(
        trace.candidates.begin(),
        trace.candidates.end(),
        [&](const EventCandidateRecord& candidate) {
          return candidate.next_node == destination_node;
        });
    if (selected_candidate != trace.candidates.end()) {
      request.route_score =
          selected_candidate->model_score;
      request.static_remaining =
          selected_candidate->static_potential;
    }
    request.destination_service_seconds =
        service_duration(destination_node);
    request.downstream_queue_pressure =
        static_cast<int>(
            junctions_[destination_node].queue.size()) +
        junctions_[destination_node].scheduled_incoming;
    request.deadline_slack =
        bag.request.deadline >= 0.0
            ? bag.request.deadline - time
            : std::numeric_limits<double>::max();
    request.wait_age =
        std::max(0.0, time - bag.junction_enqueued_at);
    request.task_class_code =
        local_task_class_code(bag);
    request.task_class = local_task_class_rank(bag);
    request.storage_leg = is_storage_out_task(bag);
    request.source_release_age =
        std::max(0.0, time - bag.request.release_time);
    request.local_queue_age =
        std::max(0.0, time - bag.junction_enqueued_at);
    request.advertised_fault_generation =
        advertised == advertised_faults_.end()
            ? 0
            : advertised->second.generation;
    request.physical_fault_generation =
        physical == physical_faults_.end()
            ? 0
            : physical->second.physical_generation;
    request.destination_calendar_generation =
        junctions_[destination_node]
            .service_calendar.generation();
    request.enqueue_sequence =
        bag.local_enqueue_sequence;
    request.expiry = time + config_.retry_interval;
    if (uses_jit_destination_merge_grants()) {
      const double ready =
          jit_destination_merge_ready_time(request, time);
      if (std::isfinite(ready)) {
        request.expiry = std::max(
            request.expiry,
            ready + config_.retry_interval);
      }
    }

    auto& controller =
        destination_merge_controller(destination_node);
    if (controller.pending_count() >=
        static_cast<std::size_t>(
            config_.merge_grant_max_pending_requests)) {
      return false;
    }
    controller.reserve_lifecycle_for_transaction(1);
    events_.reserve(events_.size() + 1);
    // Materialize both map nodes and the full trace before controller.submit
    // mutates protocol counters/generation/pending state.
    g4irsf14_state_->destination_merge.try_emplace(
        destination_node);
    PendingMergeDispatch pending;
    pending.request_id = request.request_id;
    pending.lineage = request.lineage;
    pending.runtime_bag_id =
        bag.request.runtime_bag_id;
    pending.upstream_node = upstream_node;
    pending.destination_node = destination_node;
    pending.trace = trace;
    const auto inserted =
        pending_merge_dispatches_.emplace(
        request.lineage, std::move(pending));
    if (!inserted.second) {
      return false;
    }
    const std::uint64_t request_id =
        request.request_id;
    const std::uint64_t lineage =
        request.lineage;
    const std::uint64_t request_generation =
        request.request_generation;
    const auto submitted =
        controller.submit(std::move(request));
    if (!submitted.accepted ||
        submitted.request_id != request_id) {
      pending_merge_dispatches_.erase(inserted.first);
      return false;
    }
    ++next_merge_request_lineage_;
    bag_merge.request_generation =
        request_generation;
    bag_merge.pending_request_id =
        request_id;
    bag_merge.pending_lineage = lineage;
    bag_merge.pending_request_time = time;
    if (bag_merge.first_contention_time < 0.0) {
      bag_merge.first_contention_time = time;
    }
    if (uses_jit_destination_merge_grants()) {
      schedule_next_jit_destination_merge_opportunity(
          controller, time, true);
    } else {
      schedule_destination_merge_wakeup(
          destination_node, time);
    }
    return true;
  }

  DestinationMergeGrantObservedState
  observe_destination_merge_request(
      const DestinationMergeRequest& request) const noexcept {
    DestinationMergeGrantObservedState observed;
    observed.claimed_request_generation =
        request.request_generation;
    observed.claimed_junction_queue_generation =
        request.junction_queue_generation;
    observed.claimed_calendar_generation =
        request.destination_calendar_generation;
    observed.claimed_owner_runtime_bag_id =
        request.runtime_bag_id;
    observed.claimed_edge =
        request.requested_directed_edge;
    observed.claimed_destination_node =
        request.destination_merge_node;
    observed.event_owner_runtime_bag_id =
        request.runtime_bag_id;
    observed.event_edge =
        request.requested_directed_edge;
    observed.event_destination_node =
        request.destination_merge_node;
    if (g4irsf14_state_ != nullptr) {
      const auto bag_state =
          g4irsf14_state_
              ->destination_merge_bags.find(
                  request.runtime_bag_id);
      if (bag_state !=
          g4irsf14_state_
              ->destination_merge_bags.end()) {
        observed.junction_queue_generation =
            bag_state->second
                .junction_queue_generation;
      }
    }
    const auto destination =
        junctions_.find(
            request.destination_merge_node);
    if (destination != junctions_.end()) {
      observed.calendar_generation =
          destination->second
              .service_calendar.generation();
      observed.exact_calendar_reservation_present =
          destination->second.service_calendar
              .contains_exact(
                  request.runtime_bag_id,
                  request.projected_arrival,
                  request.projected_arrival +
                      request
                          .destination_service_seconds);
    }
    const long long directed =
        event_runtime_detail::directed_key(
            request.requested_directed_edge.from_node,
            request.requested_directed_edge.to_node);
    const auto physical =
        physical_faults_.find(directed);
    if (physical != physical_faults_.end()) {
      observed.physical_fault_generation =
          physical->second.physical_generation;
      observed.physical_fault_active =
          physical->second.active_count > 0;
    }
    const auto advertised =
        advertised_faults_.find(directed);
    if (advertised != advertised_faults_.end()) {
      observed.advertised_fault_generation =
          advertised->second.generation;
    }
    return observed;
  }

  void reject_destination_merge_request(
      DestinationMergeGrantController& controller,
      const DestinationMergeRequest& request,
      MergeGrantState state,
      MergeGrantReason reason,
      double time) {
    const auto pending =
        pending_merge_dispatches_.find(request.lineage);
    if (pending != pending_merge_dispatches_.end()) {
      pending->second.trace.selected_next = -1;
      pending->second.trace.decision_source =
          "destination_merge_grant_hold";
      pending->second.trace.rule_reason =
          merge_grant_reason_name(reason);
    }
    const auto observed =
        observe_destination_merge_request(request);
    controller.reject_noexcept(
        request.request_id,
        state,
        reason,
        time,
        &observed);
    const auto bag_found =
        bags_.find(request.runtime_bag_id);
    if (bag_found != bags_.end()) {
      auto& bag_merge =
          destination_merge_bag_state(
              request.runtime_bag_id);
      if (bag_merge.pending_request_id ==
              request.request_id &&
          bag_merge.pending_lineage ==
              request.lineage) {
        bag_merge.pending_request_id = 0;
        bag_merge.pending_lineage = 0;
        bag_merge.pending_request_time = -1.0;
      }
      ++bag_found->second.retry_count;
    }
    if (pending != pending_merge_dispatches_.end()) {
      publish_prepared_decision_trace_noexcept(
          std::move(pending->second.trace), false);
      pending_merge_dispatches_.erase(pending);
    }
    if (uses_jit_destination_merge_grants() &&
        bag_found != bags_.end()) {
      schedule_junction_wakeup(
          request.upstream_node,
          time + config_.retry_interval);
    }
  }

  void reject_all_destination_merge_requests(
      DestinationMergeGrantController& controller,
      MergeGrantState selected_state,
      MergeGrantReason selected_reason,
      double time) {
    std::vector<DestinationMergeRequest> requests;
    requests.reserve(controller.pending_.size());
    for (const auto& pending : controller.pending_) {
      requests.push_back(pending.request);
    }
    for (const auto& request : requests) {
      reject_destination_merge_request(
          controller,
          request,
          selected_state,
          selected_reason,
          time);
    }
  }

  void reject_prepared_destination_merge_request_noexcept(
      DestinationMergeGrantController& controller,
      const DestinationMergeRequest& request,
      MergeGrantState state,
      MergeGrantReason reason,
      double time) noexcept {
    const auto observed =
        observe_destination_merge_request(request);
    controller.reject_noexcept(
        request.request_id,
        state,
        reason,
        time,
        &observed);
    const auto bag_found =
        bags_.find(request.runtime_bag_id);
    if (bag_found != bags_.end()) {
      auto& bag_merge =
          destination_merge_bag_state(
              request.runtime_bag_id);
      if (bag_merge.pending_request_id ==
              request.request_id &&
          bag_merge.pending_lineage ==
              request.lineage) {
        bag_merge.pending_request_id = 0;
        bag_merge.pending_lineage = 0;
        bag_merge.pending_request_time = -1.0;
      }
      ++bag_found->second.retry_count;
    }
    const auto pending =
        pending_merge_dispatches_.find(request.lineage);
    if (pending != pending_merge_dispatches_.end()) {
      publish_prepared_decision_trace_noexcept(
          std::move(pending->second.trace), false);
      pending_merge_dispatches_.erase(pending);
    }
    if (uses_jit_destination_merge_grants() &&
        bag_found != bags_.end()) {
      schedule_junction_wakeup(
          request.upstream_node,
          time + config_.retry_interval);
    }
  }

  void process_destination_merge_arbitration(
      const RuntimeEvent& event) {
    if (!uses_destination_merge_grants() ||
        g4irsf14_state_ == nullptr) {
      ++result_.summary
            .merge_grant_stale_arbitration_count;
      ++result_.summary.merge_grant_stale_wakeup_count;
      return;
    }
    auto state_found =
        g4irsf14_state_->destination_merge.find(
            event.node);
    if (state_found ==
            g4irsf14_state_->destination_merge.end() ||
        !state_found->second.wakeup_pending ||
        state_found->second.wakeup_generation !=
            event.wakeup_generation ||
        !event_runtime_detail::same_timestamp(
            state_found->second.wakeup_time,
            event.time)) {
      ++result_.summary
            .merge_grant_stale_arbitration_count;
      ++result_.summary.merge_grant_stale_wakeup_count;
      return;
    }
    state_found->second.wakeup_pending = false;

    auto controller_found =
        destination_merge_controllers_.find(event.node);
    if (controller_found ==
            destination_merge_controllers_.end() ||
        controller_found->second.pending_.empty()) {
      ++result_.summary
            .merge_grant_stale_arbitration_count;
      ++result_.summary.merge_grant_stale_wakeup_count;
      return;
    }
    auto& controller = controller_found->second;
    const bool jit_timing = uses_jit_destination_merge_grants();
    const auto reschedule_destination_merge_after_rejection =
        [&](bool wait_for_resource_change) {
          if (controller.pending_count() == 0) {
            return;
          }
          if (jit_timing) {
            schedule_next_jit_destination_merge_opportunity(
                controller,
                event.time,
                !wait_for_resource_change);
          } else {
            schedule_destination_merge_wakeup(
                event.node, event.time);
          }
        };
    if (jit_timing) {
      auto& destination = junctions_[event.node];
      destination.service_calendar.purge(event.time);
      refresh_jit_destination_merge_pending(
          controller, event.time);
    }
    const std::size_t pending_count =
        controller.pending_.size();

    // Complete every potentially throwing allocation before any real
    // calendar, bag, queue, incoming counter, or grant capability changes.
    controller.reserve_lifecycle_for_transaction(
        pending_count + 4);
    events_.reserve(events_.size() +
                    pending_count + 4);
    result_.decisions.reserve(
        result_.decisions.size() + 1);
    result_.hold_attempts.reserve(
        result_.hold_attempts.size() +
        pending_count);
    if (config_.enable_opportunity_telemetry ||
        g4irsf18_merge_policy_enabled()) {
      result_.merge_request_visibility.reserve(
          result_.merge_request_visibility.size() + 1);
      result_.event_seq_ordering_audit.reserve(
          result_.event_seq_ordering_audit.size() + 1);
    }

    std::vector<DestinationMergeRequest>
        expired_requests;
    expired_requests.reserve(pending_count);
    struct InvalidJitPendingRequest {
      DestinationMergeRequest request;
      MergeGrantState state =
          MergeGrantState::kRevokedStaleState;
      MergeGrantReason reason =
          MergeGrantReason::kOwnerStateChanged;
    };
    std::vector<InvalidJitPendingRequest>
        invalid_jit_requests;
    if (jit_timing) {
      invalid_jit_requests.reserve(pending_count);
    }
    for (const auto& pending :
         controller.pending_) {
      if (pending.request.expiry +
              event_runtime_detail::kEpsilon <
          event.time) {
        expired_requests.push_back(
            pending.request);
        continue;
      }
      if (!jit_timing) {
        continue;
      }
      const auto& request = pending.request;
      const auto bag = bags_.find(request.runtime_bag_id);
      if (bag == bags_.end() ||
          bag->second.status != BagStatus::kJunctionQueue ||
          bag->second.current != request.upstream_node) {
        invalid_jit_requests.push_back(
            InvalidJitPendingRequest{
                request,
                MergeGrantState::kRevokedStaleState,
                MergeGrantReason::kOwnerStateChanged});
        continue;
      }
      const auto bag_merge =
          g4irsf14_state_->destination_merge_bags.find(
              request.runtime_bag_id);
      const auto& upstream =
          junctions_.at(request.upstream_node);
      if (bag_merge ==
              g4irsf14_state_->destination_merge_bags.end() ||
          bag_merge->second.pending_request_id !=
              request.request_id ||
          bag_merge->second.pending_lineage !=
              request.lineage ||
          bag_merge->second.request_generation !=
              request.request_generation ||
          bag_merge->second.junction_queue_generation !=
              request.junction_queue_generation ||
          std::find(upstream.queue.begin(),
                    upstream.queue.end(),
                    request.runtime_bag_id) ==
              upstream.queue.end()) {
        invalid_jit_requests.push_back(
            InvalidJitPendingRequest{
                request,
                MergeGrantState::kRevokedStaleState,
                MergeGrantReason::kQueueGenerationChanged});
        continue;
      }
      const long long directed =
          event_runtime_detail::directed_key(
              request.upstream_node,
              request.destination_merge_node);
      const auto physical = physical_faults_.find(directed);
      const auto advertised = advertised_faults_.find(directed);
      const int physical_generation =
          physical == physical_faults_.end()
              ? 0
              : physical->second.physical_generation;
      const bool physical_active =
          physical != physical_faults_.end() &&
          physical->second.active_count > 0;
      const int advertised_generation =
          advertised == advertised_faults_.end()
              ? 0
              : advertised->second.generation;
      if (physical_active ||
          physical_generation !=
              request.physical_fault_generation ||
          advertised_generation !=
              request.advertised_fault_generation) {
        invalid_jit_requests.push_back(
            InvalidJitPendingRequest{
                request,
                MergeGrantState::kRevokedFault,
                MergeGrantReason::kFaultGenerationChanged});
      }
    }
    for (const auto& expired :
         expired_requests) {
      reject_destination_merge_request(
          controller,
          expired,
          MergeGrantState::kExpired,
          MergeGrantReason::kRequestExpired,
          event.time);
    }
    for (const auto& invalid : invalid_jit_requests) {
      reject_destination_merge_request(
          controller,
          invalid.request,
          invalid.state,
          invalid.reason,
          event.time);
    }
    if (controller.pending_.size() >= 2U) {
      ++result_.summary
            .g4irsf14_i2_live_eligible_multi_request_boundary_count;
    }
    if (controller.pending_.empty()) {
      return;
    }

    std::vector<DestinationMergeGrantController::PendingRecord*>
        jit_candidates;
    DestinationMergeGrantController::PendingRecord*
        jit_fifo_baseline = nullptr;
    G4IRSF18MergeRuntimeDecision g4irsf18_model_decision;
    const G4IRSF18MergeRuntimeDecision*
        g4irsf18_model_decision_ptr = nullptr;
    DestinationMergeGrantController::PendingRecord* selected = nullptr;
    if (jit_timing) {
      auto& destination = junctions_[event.node];
      const bool queue_has_room =
          config_.local_queue_capacity <= 0 ||
          static_cast<int>(destination.queue.size()) +
                  destination.scheduled_incoming <
              config_.local_queue_capacity;
      if (queue_has_room && controller.active_capacity_available()) {
        jit_candidates.reserve(controller.pending_.size());
        for (auto& pending : controller.pending_) {
          const double slot_start =
              event.time +
              pending.request.exact_edge_travel_seconds;
          const double slot_end =
              slot_start +
              pending.request.destination_service_seconds;
          if (destination.service_calendar.available(
                  slot_start,
                  slot_end,
                  pending.request.runtime_bag_id) &&
              !controller.has_overlapping_active_slot(
                  slot_start, slot_end)) {
            jit_candidates.push_back(&pending);
          }
        }
      }
      if (jit_candidates.empty()) {
        schedule_next_jit_destination_merge_opportunity(
            controller, event.time, false);
        return;
      }
      const auto choose =
          [&](DestinationMergeGrantRule rule) {
            DestinationMergeGrantController::PendingRecord* best = nullptr;
            for (auto* candidate : jit_candidates) {
              if (best == nullptr ||
                  destination_merge_request_less(
                      rule,
                      candidate->request,
                      best->request,
                      event.time,
                      config_.starvation_threshold)) {
                best = candidate;
              }
            }
            return best;
          };
      jit_fifo_baseline =
          choose(DestinationMergeGrantRule::kM1Fifo);
      selected = choose(effective_merge_grant_rule());
      if (g4irsf18_merge_policy_enabled()) {
        auto* jit_j2_baseline =
            choose(DestinationMergeGrantRule::kM3DeadlineAging);
        g4irsf18_model_decision =
            decide_g4irsf18_merge_policy(
                jit_candidates,
                jit_fifo_baseline,
                jit_j2_baseline,
                event.time);
        g4irsf18_model_decision_ptr =
            &g4irsf18_model_decision;
        selected = g4irsf18_model_decision.chosen;
      }
      const auto opportunity_id =
          ++result_.summary
                .merge_grant_service_opportunity_count;
      result_.summary.merge_grant_candidate_total_count +=
          jit_candidates.size();
      if (jit_candidates.size() > 1U) {
        ++result_.summary
              .merge_grant_multi_candidate_opportunity_count;
      }
      const double selected_slot_start =
          event.time +
          selected->request.exact_edge_travel_seconds;
      const double selected_slot_end =
          selected_slot_start +
          selected->request.destination_service_seconds;
      std::size_t overlapping_candidate_count = 0;
      for (const auto* candidate : jit_candidates) {
        const double candidate_start =
            event.time +
            candidate->request.exact_edge_travel_seconds;
        const double candidate_end =
            candidate_start +
            candidate->request.destination_service_seconds;
        if (candidate_start <
                    selected_slot_end -
                        event_runtime_detail::kEpsilon &&
            selected_slot_start <
                    candidate_end -
                        event_runtime_detail::kEpsilon) {
          ++overlapping_candidate_count;
        }
      }
      if (overlapping_candidate_count > 1U) {
        ++result_.summary.merge_grant_true_competition_count;
      }
      if (jit_candidates.size() > 1U &&
          selected->request.request_id !=
          jit_fifo_baseline->request.request_id) {
        ++result_.summary.merge_grant_order_mutation_count;
      }
      append_jit_merge_service_opportunity(
          opportunity_id,
          event.time,
          event.node,
          controller.generation(),
          jit_candidates,
          jit_fifo_baseline->request,
          selected->request,
          g4irsf18_model_decision_ptr);
    } else {
      selected =
          controller.select(canonical_merge_grant_rule(),
                            event.time,
                            config_.starvation_threshold);
    }
    if (selected == nullptr) {
      reject_all_destination_merge_requests(
          controller,
          MergeGrantState::kExpired,
          MergeGrantReason::kRequestExpired,
          event.time);
      return;
    }
    if (active_causal_step_ != nullptr &&
        controller.pending_.size() >= 2U) {
      G4IRSF14CloneBoundary boundary;
      boundary.kind =
          G4IRSF14CloneBoundaryKind::kMergeGrantArbitration;
      boundary.node = event.node;
      boundary.runtime_bag_id =
          selected->request.runtime_bag_id;
      boundary.pending_merge_request_order.push_back(
          selected->request.request_id);
      for (const auto& pending : controller.pending_) {
        if (pending.request.request_id !=
            selected->request.request_id) {
          boundary.pending_merge_request_order.push_back(
              pending.request.request_id);
        }
      }
      if (const auto* intervention =
              observe_causal_boundary(std::move(boundary));
          intervention != nullptr) {
        if (intervention->kind !=
                G4IRSF14CloneInterventionKind::
                    kMergeRequestOrderSwap ||
            intervention->merge_request_id !=
                selected->request.request_id) {
          throw std::logic_error(
              "I2 directive does not swap the baseline merge winner");
        }
        const auto peer = std::find_if(
            controller.pending_.begin(),
            controller.pending_.end(),
            [&](const auto& pending) {
              return pending.request.request_id ==
                     intervention->peer_merge_request_id;
            });
        if (peer == controller.pending_.end()) {
          throw std::logic_error(
              "I2 peer disappeared from the identical merge ready set");
        }
        const int baseline_runtime_bag_id =
            selected->request.runtime_bag_id;
        const int peer_runtime_bag_id =
            peer->request.runtime_bag_id;
        selected = &*peer;
        mark_causal_action_applied(
            "APPLIED_I2_MERGE_REQUEST_ORDER_SWAP_ONE_ACTION",
            {baseline_runtime_bag_id,
             peer_runtime_bag_id});
      }
    }
    const DestinationMergeRequest request =
        selected->request;

    auto bag_found = bags_.find(request.runtime_bag_id);
    if (bag_found == bags_.end() ||
        bag_found->second.status !=
            BagStatus::kJunctionQueue ||
        bag_found->second.current !=
            request.upstream_node) {
      reject_destination_merge_request(
          controller,
          request,
          MergeGrantState::kRevokedStaleState,
          MergeGrantReason::kOwnerStateChanged,
          event.time);
      reschedule_destination_merge_after_rejection(false);
      return;
    }
    auto& bag = bag_found->second;
    auto& bag_merge =
        destination_merge_bag_state(
            request.runtime_bag_id);
    if (bag_merge.pending_request_id !=
            request.request_id ||
        bag_merge.pending_lineage != request.lineage ||
        bag_merge.request_generation !=
            request.request_generation ||
        bag_merge.junction_queue_generation !=
            request.junction_queue_generation ||
        std::find(
            junctions_[request.upstream_node].queue.begin(),
            junctions_[request.upstream_node].queue.end(),
            request.runtime_bag_id) ==
            junctions_[request.upstream_node].queue.end()) {
      reject_destination_merge_request(
          controller,
          request,
          MergeGrantState::kRevokedStaleState,
          MergeGrantReason::kQueueGenerationChanged,
          event.time);
      reschedule_destination_merge_after_rejection(false);
      return;
    }

    const long long directed =
        event_runtime_detail::directed_key(
            request.upstream_node,
            request.destination_merge_node);
#ifdef CZR005_EVENT_RUNTIME_TESTING
    if (config_
            .test_merge_grant_flip_advertised_generation_before_commit &&
        !test_merge_grant_advertised_flip_injected_) {
      // Materialise the map node before the transaction so the failpoint
      // itself changes only a scalar generation.
      advertised_faults_.try_emplace(directed);
    }
    if (config_
            .test_merge_grant_flip_physical_generation_before_commit &&
        !test_merge_grant_physical_flip_injected_) {
      physical_faults_.try_emplace(directed);
    }
#endif
    const auto physical = physical_faults_.find(directed);
    const auto advertised =
        advertised_faults_.find(directed);
    const int physical_generation =
        physical == physical_faults_.end()
            ? 0
            : physical->second.physical_generation;
    const bool physical_active =
        physical != physical_faults_.end() &&
        physical->second.active_count > 0;
    const int advertised_generation =
        advertised == advertised_faults_.end()
            ? 0
            : advertised->second.generation;
    if (physical_active ||
        physical_generation !=
            request.physical_fault_generation ||
        advertised_generation !=
            request.advertised_fault_generation) {
      reject_destination_merge_request(
          controller,
          request,
          MergeGrantState::kRevokedFault,
          MergeGrantReason::kFaultGenerationChanged,
          event.time);
      reschedule_destination_merge_after_rejection(false);
      return;
    }

    auto& destination =
        junctions_[request.destination_merge_node];
    destination.service_calendar.purge(event.time);
    if (destination.service_calendar.generation() !=
        request.destination_calendar_generation) {
      reject_destination_merge_request(
          controller,
          request,
          MergeGrantState::kRevokedStaleState,
          MergeGrantReason::kCalendarGenerationChanged,
          event.time);
      reschedule_destination_merge_after_rejection(false);
      return;
    }
    const bool queue_capacity_blocked =
        config_.local_queue_capacity > 0 &&
        static_cast<int>(destination.queue.size()) +
                destination.scheduled_incoming >=
            config_.local_queue_capacity;
    if (queue_capacity_blocked &&
        canonical_pibt_mode() ==
            BoundedLocalPIBTMode::kP0) {
      reject_destination_merge_request(
          controller,
          request,
          MergeGrantState::kRolledBack,
          MergeGrantReason::kQueueCapacityBlock,
          event.time);
      reschedule_destination_merge_after_rejection(true);
      return;
    }

    const double slot_start =
        request.request_time +
        request.exact_edge_travel_seconds;
    const double slot_end =
        slot_start +
        service_duration(
            request.destination_merge_node);
    if (!controller.active_capacity_available() ||
        controller.has_overlapping_active_slot(
            slot_start, slot_end)) {
      reject_destination_merge_request(
          controller,
          request,
          MergeGrantState::kRolledBack,
          MergeGrantReason::kActiveGrantExists,
          event.time);
      reschedule_destination_merge_after_rejection(true);
      return;
    }
    auto prepared =
        destination.service_calendar
            .prepare_exact_reservation(
                request.runtime_bag_id,
                slot_start,
                slot_end);
    if (!prepared.has_value()) {
      reject_destination_merge_request(
          controller,
          request,
          MergeGrantState::kRolledBack,
          MergeGrantReason::kExactSlotBusy,
          event.time);
      reschedule_destination_merge_after_rejection(true);
      return;
    }

    auto winner_pending =
        pending_merge_dispatches_.find(request.lineage);
    if (winner_pending ==
        pending_merge_dispatches_.end()) {
      reject_destination_merge_request(
          controller,
          request,
          MergeGrantState::kRevokedStaleState,
          MergeGrantReason::kOwnerStateChanged,
          event.time);
      reschedule_destination_merge_after_rejection(false);
      return;
    }

    // Fully materialize every string/vector/event/telemetry object and loser
    // copy before the exact calendar commit. The tail below the commit is
    // allocation-free and uses only noexcept moves/scalar mutations.
    winner_pending->second.trace.selected_next =
        request.destination_merge_node;
    winner_pending->second.trace.decision_source =
        "destination_owned_merge_grant";
    winner_pending->second.trace.rule_reason =
        std::string(
            destination_merge_grant_rule_name(
                jit_timing
                    ? effective_merge_grant_rule()
                    : canonical_merge_grant_rule())) +
        "_exact_R3_slot_runtime_owned_capability";

    std::vector<DestinationMergeRequest> losers;
    losers.reserve(
        controller.pending_.size() > 0
            ? controller.pending_.size() - 1
            : 0);
    for (const auto& remaining : controller.pending_) {
      if (remaining.request.request_id ==
          request.request_id) {
        continue;
      }
      if (jit_timing) {
        continue;
      }
      losers.push_back(remaining.request);
      const auto loser_pending =
          pending_merge_dispatches_.find(
              remaining.request.lineage);
      if (loser_pending !=
          pending_merge_dispatches_.end()) {
        loser_pending->second.trace.selected_next = -1;
        loser_pending->second.trace.decision_source =
            "destination_merge_grant_hold";
        loser_pending->second.trace.rule_reason =
            merge_grant_reason_name(
                MergeGrantReason::kContendedLoserRetry);
      }
    }

    std::vector<RuntimeEvent> staged_events;
    staged_events.reserve(4);
    const auto stage_event =
        [&](JunctionEventType type,
            double time,
            int task_id,
            int node,
            int from_node,
            int to_node,
            double service_end,
            std::string reason) {
          RuntimeEvent staged;
          staged.type = type;
          staged.time = time;
          staged.task_id = task_id;
          staged.node = node;
          staged.from_node = from_node;
          staged.to_node = to_node;
          staged.service_end = service_end;
          staged.reason = std::move(reason);
          prepare_event_for_publication(staged);
          staged_events.push_back(std::move(staged));
        };
    stage_event(
        JunctionEventType::kCongestionBeaconUpdate,
        event.time,
        request.runtime_bag_id,
        request.destination_merge_node,
        request.upstream_node,
        request.destination_merge_node,
        0.0,
        "incoming_reservation_snapshot");
    stage_event(
        JunctionEventType::kEdgeEnter,
        event.time,
        request.runtime_bag_id,
        request.upstream_node,
        request.upstream_node,
        request.destination_merge_node,
        0.0,
        "one_step_merge_grant_committed");
    stage_event(
        JunctionEventType::kEdgeExit,
        slot_start,
        request.runtime_bag_id,
        request.destination_merge_node,
        request.upstream_node,
        request.destination_merge_node,
        slot_end,
        {});
    stage_event(
        JunctionEventType::kLocalQueueUpdate,
        event.time,
        request.runtime_bag_id,
        request.upstream_node,
        request.upstream_node,
        request.destination_merge_node,
        0.0,
        "merge_grant_junction_dequeue");
    events_.reserve(events_.size() +
                    staged_events.size());

    std::vector<PIBTStagedMergeVisibility>
        staged_visibility;
    std::map<int, int> staged_known_competitors;
    if (config_.enable_opportunity_telemetry) {
      staged_visibility.reserve(1);
      staged_known_competitors.emplace(
          request.destination_merge_node,
          std::max(
              0,
              static_cast<int>(
                  controller.pending_.size()) -
                  1));
      staged_merge_visibility_sink_ =
          &staged_visibility;
      staged_destination_known_competitor_counts_ =
          &staged_known_competitors;
      try {
        append_merge_visibility(
            bag,
            request.upstream_node,
            request.destination_merge_node,
            event.time,
            slot_start,
            slot_end);
      } catch (...) {
        staged_merge_visibility_sink_ = nullptr;
        staged_destination_known_competitor_counts_ =
            nullptr;
        throw;
      }
      staged_merge_visibility_sink_ = nullptr;
      staged_destination_known_competitor_counts_ =
          nullptr;
    }

    destination.scheduled_incoming_by_goal.reserve(
        destination.scheduled_incoming_by_goal.size() +
        1);
    const auto goal_entry =
        destination.scheduled_incoming_by_goal.try_emplace(
            bag.request.goal, 0);
    const bool inserted_goal_entry =
        goal_entry.second;

#ifdef CZR005_EVENT_RUNTIME_TESTING
    if (config_
            .test_merge_grant_fail_after_calendar_prepare &&
        !test_merge_grant_prepare_failure_injected_) {
      test_merge_grant_prepare_failure_injected_ = true;
      if (inserted_goal_entry) {
        destination.scheduled_incoming_by_goal.erase(
            goal_entry.first);
      }
      reject_all_destination_merge_requests(
          controller,
          MergeGrantState::kRolledBack,
          MergeGrantReason::kInjectedPrepareRollback,
          event.time);
      return;
    }
    if (config_
            .test_merge_grant_flip_advertised_generation_before_commit &&
        !test_merge_grant_advertised_flip_injected_) {
      test_merge_grant_advertised_flip_injected_ = true;
      ++advertised_faults_.at(directed).generation;
    }
    if (config_
            .test_merge_grant_flip_physical_generation_before_commit &&
        !test_merge_grant_physical_flip_injected_) {
      test_merge_grant_physical_flip_injected_ = true;
      ++physical_faults_.at(directed).physical_generation;
    }
    if (config_
            .test_merge_grant_flip_calendar_generation_before_commit &&
        !test_merge_grant_calendar_flip_injected_) {
      test_merge_grant_calendar_flip_injected_ = true;
      destination.service_calendar.test_advance_generation();
    }
    if (config_
            .test_merge_grant_flip_queue_generation_before_commit &&
        !test_merge_grant_queue_flip_injected_) {
      test_merge_grant_queue_flip_injected_ = true;
      ++bag_merge.junction_queue_generation;
    }
#endif

    const auto physical_commit =
        physical_faults_.find(directed);
    const auto advertised_commit =
        advertised_faults_.find(directed);
    const int physical_generation_commit =
        physical_commit == physical_faults_.end()
            ? 0
            : physical_commit->second.physical_generation;
    const bool physical_active_commit =
        physical_commit != physical_faults_.end() &&
        physical_commit->second.active_count > 0;
    const int advertised_generation_commit =
        advertised_commit == advertised_faults_.end()
            ? 0
            : advertised_commit->second.generation;
    ++result_.summary
          .fault_generation_commit_recheck_count;
    if (physical_active_commit ||
        physical_generation_commit !=
            request.physical_fault_generation ||
        advertised_generation_commit !=
            request.advertised_fault_generation ||
        bag_merge.junction_queue_generation !=
            request.junction_queue_generation) {
      if (inserted_goal_entry) {
        destination.scheduled_incoming_by_goal.erase(
            goal_entry.first);
      }
      reject_destination_merge_request(
          controller,
          request,
          physical_active_commit ||
                  physical_generation_commit !=
                      request.physical_fault_generation ||
                  advertised_generation_commit !=
                      request.advertised_fault_generation
              ? MergeGrantState::kRevokedFault
              : MergeGrantState::kRevokedStaleState,
          physical_active_commit ||
                  physical_generation_commit !=
                      request.physical_fault_generation ||
                  advertised_generation_commit !=
                      request.advertised_fault_generation
              ? MergeGrantReason::kFaultGenerationChanged
              : MergeGrantReason::kQueueGenerationChanged,
          event.time);
      reschedule_destination_merge_after_rejection(false);
      return;
    }
    if (destination.service_calendar.generation() !=
        request.destination_calendar_generation) {
      if (inserted_goal_entry) {
        destination.scheduled_incoming_by_goal.erase(
            goal_entry.first);
      }
      reject_destination_merge_request(
          controller,
          request,
          MergeGrantState::kRevokedStaleState,
          MergeGrantReason::kCalendarGenerationChanged,
          event.time);
      reschedule_destination_merge_after_rejection(false);
      return;
    }

    if (!destination.service_calendar
             .commit_exact_reservation(
                 std::move(*prepared))) {
      if (inserted_goal_entry) {
        destination.scheduled_incoming_by_goal.erase(
            goal_entry.first);
      }
      reject_destination_merge_request(
          controller,
          request,
          MergeGrantState::kRevokedStaleState,
          MergeGrantReason::kCalendarGenerationChanged,
          event.time);
      reschedule_destination_merge_after_rejection(false);
      return;
    }

    // Point of no return. Capacity, strings, traces, lifecycle rows, calendar
    // storage, goal-map node, and event storage were all prepared above.
    auto capability =
        controller.commit_selected_noexcept(
            request.request_id,
            slot_start,
            slot_end,
            event.time,
            destination.service_calendar.generation(),
            physical_generation);
    bag_merge.capability.emplace(
        std::move(capability));
    bag_merge.exact_grant_edge_entry_observed = false;

    if (queue_capacity_blocked) {
      const auto rollback_grant_and_calendar =
          [&]() {
            const bool grant_rolled_back =
                bag_merge.capability.has_value() &&
                controller.rollback_committed_noexcept(
                    *bag_merge.capability,
                    request,
                    event.time,
                    MergeGrantReason::kQueueCapacityBlock);
            const bool calendar_rolled_back =
                destination.service_calendar
                    .restore_exact_reservation_noexcept(
                        request.runtime_bag_id,
                        slot_start,
                        slot_end,
                        request.destination_calendar_generation);
            bag_merge.capability.reset();
            if (!grant_rolled_back ||
                !calendar_rolled_back) {
              throw std::logic_error(
                  "post-grant PIBT compensation failed");
            }
      };

      DispatchResult pibt_dispatch;
      try {
        ++result_.summary
              .g4irsf14_i5_prefilter_candidate_count;
        pibt_dispatch =
            try_dispatch_bounded_local_pibt(
                request.upstream_node,
                event.time,
                event.seq,
                nullptr,
                &*bag_merge.capability);
      } catch (...) {
        if (inserted_goal_entry &&
            goal_entry.first->second == 0) {
          destination
              .scheduled_incoming_by_goal.erase(
                  goal_entry.first);
        }
        rollback_grant_and_calendar();
        throw;
      }
      if (!pibt_dispatch.handled) {
        if (inserted_goal_entry &&
            goal_entry.first->second == 0) {
          destination
              .scheduled_incoming_by_goal.erase(
                  goal_entry.first);
        }
        rollback_grant_and_calendar();
        winner_pending->second.trace.selected_next = -1;
        winner_pending->second.trace.decision_source =
            "destination_merge_grant_hold";
        winner_pending->second.trace.rule_reason =
            merge_grant_reason_name(
                MergeGrantReason::kQueueCapacityBlock);
        bag_merge.pending_request_id = 0;
        bag_merge.pending_lineage = 0;
        bag_merge.pending_request_time = -1.0;
        ++bag.retry_count;
        publish_prepared_decision_trace_noexcept(
            std::move(winner_pending->second.trace), false);
        pending_merge_dispatches_.erase(winner_pending);
        if (jit_timing) {
          schedule_junction_wakeup(
              request.upstream_node,
              event.time + config_.retry_interval);
        }
        if (controller.pending_count() > 0) {
          if (jit_timing) {
            schedule_next_jit_destination_merge_opportunity(
                controller, event.time, false);
          } else {
            schedule_destination_merge_wakeup(
                event.node, event.time);
          }
        }
        return;
      }
      bag_merge.grant_wait_seconds +=
          std::max(
              0.0,
              event.time -
                  bag_merge.first_contention_time);
      bag_merge.pending_request_id = 0;
      bag_merge.pending_lineage = 0;
      bag_merge.pending_request_time = -1.0;
      bag_merge.first_contention_time = -1.0;
      clear_consumed_repair_reentry_boost(bag);
      publish_prepared_decision_trace_noexcept(
          std::move(winner_pending->second.trace), true);
      pending_merge_dispatches_.erase(winner_pending);
      for (const auto& loser : losers) {
        reject_prepared_destination_merge_request_noexcept(
            controller,
            loser,
            MergeGrantState::kRolledBack,
            MergeGrantReason::kContendedLoserRetry,
            event.time);
      }
      if (jit_timing && controller.pending_count() > 0) {
        schedule_next_jit_destination_merge_opportunity(
            controller, event.time, true);
      }
      return;
    }

    bag_merge.grant_wait_seconds +=
        std::max(
            0.0,
            event.time -
                bag_merge.first_contention_time);
    bag_merge.pending_request_id = 0;
    bag_merge.pending_lineage = 0;
    bag_merge.pending_request_time = -1.0;
    bag_merge.first_contention_time = -1.0;

    destination.record_service_reservation(
        slot_start, slot_end);
    ++destination.scheduled_incoming;
    ++goal_entry.first->second;
    update_calendar_maxima(destination, nullptr);

    const double queue_wait =
        std::max(
            0.0,
            event.time - bag.junction_enqueued_at);
    bag.total_wait += queue_wait;
    bag.junction_queue_wait_seconds += queue_wait;
    bag.status = BagStatus::kInTransit;
    bag.transit_from = request.upstream_node;
    bag.transit_to =
        request.destination_merge_node;
    bag.transit_merge_grant =
        bag_merge.capability->expectation();
    for (auto& staged : staged_events) {
      publish_prepared_reserved_event(
          std::move(staged));
    }

    ++bag.decision_count;
    ++result_.summary.decision_count;
    result_.summary.max_edges_selected_per_arrive =
        std::max(
            result_.summary
                .max_edges_selected_per_arrive,
            1);
    result_.summary
        .max_edges_selected_per_bag_per_decision =
        std::max(
            result_.summary
                .max_edges_selected_per_bag_per_decision,
            1);
    auto& upstream =
        junctions_[request.upstream_node];
    const auto queue_owner = std::find(
        upstream.queue.begin(),
        upstream.queue.end(),
        request.runtime_bag_id);
    upstream.queue.erase(queue_owner);
    ++bag_merge.junction_queue_generation;
    upstream.observe_local_state();
    g4irsf17_clear_local_blocker(request.upstream_node);
    upstream.next_dispatch_time =
        event.time +
        config_.dispatch_headway_seconds;
    if (upstream.queue.empty() &&
        upstream.junction_wakeup_pending) {
      upstream.junction_wakeup_pending = false;
      ++upstream.junction_wakeup_generation;
      auto local =
          g4irsf14_state_->local.find(
              request.upstream_node);
      if (local != g4irsf14_state_->local.end()) {
        local->second.junction_wakeup_time =
            std::numeric_limits<double>::infinity();
      }
    }
    clear_consumed_repair_reentry_boost(bag);

    publish_prepared_decision_trace_noexcept(
        std::move(winner_pending->second.trace), true);
    pending_merge_dispatches_.erase(winner_pending);
    for (auto& visibility : staged_visibility) {
      publish_prepared_merge_visibility_noexcept(
          std::move(visibility));
    }
    for (const auto& loser : losers) {
      reject_prepared_destination_merge_request_noexcept(
          controller,
          loser,
          MergeGrantState::kRolledBack,
          MergeGrantReason::kContendedLoserRetry,
          event.time);
    }
    if (jit_timing && controller.pending_count() > 0) {
      schedule_next_jit_destination_merge_opportunity(
          controller, event.time, true);
    }
  }

  void dispatch_junction_once(const RuntimeEvent& event,
                              bool batched_arbitration) {
    auto& controller = junctions_[event.node];
    const int ready_set_size =
        static_cast<int>(controller.queue.size());
    if (g4irsf14_state_ != nullptr) {
      g4irsf14_state_->current_pibt_slice_bag_count = 0;
      g4irsf14_state_->current_pibt_owner_count = 0;
    }
    DispatchResult dispatch;
    int priority_comparison_count = 0;
    int* comparison_counter =
        config_.enable_opportunity_telemetry
            ? &priority_comparison_count
            : nullptr;
    int bounded_local_same_bag_fallback_next = -1;
    bool bounded_local_pibt_attempted = false;
    // E4 phase 5a is ordinary destination-merge request publication. PIBT
    // must not pre-emptively order that queue; it remains available only
    // after a destination-owned winner/capability exists and an exceptional
    // local blocker requires an atomic handoff.
    if (!uses_destination_merge_grants() &&
        canonical_pibt_mode() != BoundedLocalPIBTMode::kP0) {
      const auto activation_count_before =
          result_.summary.bounded_local_pibt_activation_count;
      dispatch =
          try_dispatch_bounded_local_pibt(
              event.node,
              event.time,
              event.seq,
              comparison_counter);
      bounded_local_pibt_attempted =
          result_.summary.bounded_local_pibt_activation_count >
          activation_count_before;
      bounded_local_same_bag_fallback_next =
          dispatch.same_bag_fallback_next;
    }
    if (!dispatch.handled) {
      dispatch = try_dispatch_one(
          event.node,
          event.time,
          event.seq,
          bounded_local_same_bag_fallback_next,
          comparison_counter,
          bounded_local_pibt_attempted);
    }
    const int pibt_slice_bag_count =
        g4irsf14_state_ == nullptr
            ? 0
            : g4irsf14_state_->current_pibt_slice_bag_count;
    const int pibt_owner_count =
        g4irsf14_state_ == nullptr
            ? 0
            : g4irsf14_state_->current_pibt_owner_count;
    append_junction_opportunity(event,
                                ready_set_size,
                                dispatch.task_id,
                                pibt_slice_bag_count,
                                pibt_owner_count,
                                priority_comparison_count,
                                batched_arbitration);
    if (dispatch.selected_edge_count > 0) {
      g4irsf17_clear_local_blocker(event.node);
    }
    schedule_passive(JunctionEventType::kCongestionBeaconUpdate,
                     event.time,
                     dispatch.task_id >= 0 ? dispatch.task_id : event.task_id,
                     event.node,
                     event.from_node,
                     dispatch.selected_next,
                     "junction_dispatch_snapshot");
    result_.summary.max_edges_selected_per_arrive =
        std::max(result_.summary.max_edges_selected_per_arrive, dispatch.selected_edge_count);
    result_.summary.max_edges_selected_per_bag_per_decision =
        std::max(
            result_.summary.max_edges_selected_per_bag_per_decision,
            dispatch.selected_edge_count);
    append_event_trace(event,
                       dispatch.task_id >= 0 ? dispatch.task_id : event.task_id,
                       event.node,
                       event.from_node,
                       dispatch.selected_next,
                       batched_arbitration
                           ? "same_timestamp_junction_arbitration"
                           : (event.retry ? "junction_retry"
                                          : "junction_arrival"),
                       dispatch.selected_edge_count);
    if (junction_has_unrepresented_merge_work(controller) &&
        !controller.junction_wakeup_pending) {
      schedule_junction_wakeup(event.node, event.time + config_.retry_interval);
    }
  }

  struct DispatchResult {
    int task_id = -1;
    int selected_next = -1;
    int selected_edge_count = 0;
    bool handled = false;
    int same_bag_fallback_next = -1;
  };

  using PendingMergeDispatch =
      event_runtime_detail::PendingMergeDispatch;

  struct PIBTCreditView {
    bool required = false;
    bool ready = true;
    int to_node = -1;
  };

  struct PIBTLocalSlice {
    bool applicable = false;
    std::string blocker;
    int trigger_runtime_bag_id = -1;
    int candidate_count = 0;
    int resource_count = 0;
    std::vector<BoundedLocalPIBTReadyBag> ready_bags;
    std::vector<BoundedLocalPIBTResourceOwner> owners;
    std::map<LocalPIBTResourceKey, std::pair<int, int>> edge_by_resource;
    std::map<int, EventDecisionTraceRow> traces_by_bag;
  };

  struct PIBTBagSnapshot {
    int bag_id = -1;
    BagStatus status = BagStatus::kPendingRelease;
    double total_wait = 0.0;
    double junction_queue_wait_seconds = 0.0;
    int transit_from = -1;
    int transit_to = -1;
    DestinationMergeGrantExpectation
        transit_merge_grant;
    int decision_count = 0;
    double deadlock_started_at = -1.0;
    std::uint64_t first_edge_credit_id = 0;
    bool first_edge_credit_consumed = false;
  };

  struct PIBTJunctionSnapshot {
    int node = -1;
    std::uint64_t service_calendar_generation = 0;
    std::deque<int> queue;
    int peak_source_queue_length = 0;
    int peak_junction_queue_length = 0;
    int peak_service_calendar_intervals = 0;
    std::size_t peak_local_state_accounted_bytes = 0;
    std::uint64_t service_reservation_count = 0;
    double cumulative_service_reserved_seconds = 0.0;
    double first_service_reservation_start_time = -1.0;
    double last_service_reservation_end_time = -1.0;
    double next_dispatch_time = 0.0;
    int scheduled_incoming = 0;
    std::unordered_map<int, int>
        scheduled_incoming_by_goal;
    std::uint64_t source_wakeup_generation = 0;
    std::uint64_t junction_wakeup_generation = 0;
    bool source_wakeup_pending = false;
    bool junction_wakeup_pending = false;
    int escape_token_task = -1;
    bool g4irsf14_local_state_existed = false;
    event_runtime_detail::LocalArbitrationState
        g4irsf14_local_state;
#ifdef CZR005_EVENT_RUNTIME_TESTING
    std::uint64_t logical_state_fingerprint = 0;
#endif
  };

  struct PIBTMergeBagSnapshot {
    std::uint64_t junction_queue_generation = 0;
    std::uint64_t request_generation = 0;
    std::uint64_t pending_request_id = 0;
    std::uint64_t pending_lineage = 0;
    double pending_request_time = -1.0;
    double first_contention_time = -1.0;
    double grant_wait_seconds = 0.0;
    bool exact_grant_edge_entry_observed = false;
    bool capability_present = false;
    DestinationMergeGrantExpectation
        capability_identity;
  };

  struct PIBTActionDelta {
    int bag_id = -1;
    int from_node = -1;
    int next_node = -1;
    std::size_t queue_index = 0;
    JunctionState* source_junction = nullptr;
    std::deque<int>::const_iterator source_queue_iterator;
    bool corridor_reservation_inserted = false;
    bool corridor_existed = false;
    long long corridor_key = 0;
    double corridor_start = 0.0;
    double corridor_end = 0.0;
    std::uint64_t corridor_generation_before = 0;
    bool destination_reservation_inserted = false;
    double destination_start = 0.0;
    double destination_end = 0.0;
    std::uint64_t destination_generation_before = 0;
    int destination_goal = -1;
    bool destination_goal_existed = false;
    int destination_goal_value = 0;
    bool destination_goal_incremented = false;
  };

  struct PIBTStagedMergeVisibility {
    EventRuntimeMergeVisibilityRow merge;
    EventRuntimeEventSeqAuditRow audit;
  };

  struct PIBTCorridorSnapshot {
    bool existed = false;
    std::uint64_t generation = 0;
    std::uint64_t logical_state_fingerprint = 0;
  };

  struct PIBTTransactionSnapshot {
    bool captured = false;
    bool mutated = false;
    bool differential_rollback = false;
    int credit_entry_count = 0;
    std::size_t applied_action_count = 0;
    EventRuntimeSummary summary;
    std::map<int, PIBTBagSnapshot> bags;
    std::map<int, PIBTMergeBagSnapshot>
        destination_merge_bags;
    std::map<int, PIBTJunctionSnapshot> junctions;
    std::map<long long, PIBTCorridorSnapshot> corridors;
    std::vector<PIBTActionDelta> action_deltas;
    std::vector<RuntimeEvent> staged_events;
    std::vector<PIBTStagedMergeVisibility>
        staged_merge_visibility;
    std::map<int, int>
        staged_destination_known_competitor_counts;
    std::uint64_t next_event_seq = 0;
#ifdef CZR005_EVENT_RUNTIME_TESTING
    bool calendar_logical_state_restored = true;
    bool calendar_generation_restored = true;
    std::size_t event_queue_size = 0;
    std::uint64_t event_queue_logical_fingerprint = 0;
    std::size_t merge_visibility_size = 0;
    std::size_t event_seq_audit_size = 0;
    FirstEdgeCreditCounters credit_counters;
    std::size_t credit_active_count = 0;
    std::size_t credit_lifecycle_count = 0;
    std::map<int, std::uint64_t>
        destination_merge_controller_fingerprints;
    std::uint64_t
        pending_merge_dispatches_logical_fingerprint = 0;
#endif
  };

  class PIBTLogicalCommitFailure : public std::runtime_error {
   public:
    explicit PIBTLogicalCommitFailure(const std::string& message)
        : std::runtime_error(message) {}
  };

#ifdef CZR005_EVENT_RUNTIME_TESTING
  class PIBTPostCommitFailureInjection final {};
#endif

  static LocalPIBTResourceKey pibt_runtime_corridor_resource(int start,
                                                              int end,
                                                              bool directed) {
    if (start < 0 || end < 0 || start >= (1 << 28) || end >= (1 << 28)) {
      throw std::invalid_argument(
          "bounded local PIBT corridor endpoints must be in [0, 2^28)");
    }
    const int left = directed ? start : std::min(start, end);
    const int right = directed ? end : std::max(start, end);
    return static_cast<LocalPIBTResourceKey>(0x3000000000000000LL) |
           (static_cast<LocalPIBTResourceKey>(
                static_cast<std::uint32_t>(left))
            << 28) |
           static_cast<std::uint32_t>(right);
  }

  PIBTCreditView pibt_credit_view(const BagState& bag,
                                  int node,
                                  double time) const {
    PIBTCreditView view;
    view.required =
        first_edge_credit_required_for_bag(bag, node);
    if (!view.required) {
      return view;
    }
    view.ready = false;
    if (bag.first_edge_credit_id == 0) {
      return view;
    }
    const auto* credit = credit_ledger_.find(bag.first_edge_credit_id);
    if (credit == nullptr || credit->state != FirstEdgeCreditState::kIssued ||
        credit->from_node != node || credit->goal != bag.request.goal ||
        (credit->owner_or_unbound >= 0 &&
         credit->owner_or_unbound != bag.request.runtime_bag_id) ||
        time + event_runtime_detail::kEpsilon < credit->earliest ||
        time > credit->latest + event_runtime_detail::kEpsilon ||
        time > credit->expiry + event_runtime_detail::kEpsilon) {
      return view;
    }
    const auto context =
        credit_use_context(bag, node, credit->to_node, time);
    if (context.physical_fault_active ||
        context.generation != credit->generation ||
        context.fault_generation != credit->fault_generation) {
      return view;
    }
    view.ready = true;
    view.to_node = credit->to_node;
    return view;
  }

  static double scorer_scale(double value, double denominator) {
    return std::clamp(value / denominator, -20.0, 20.0);
  }

  int scorer_static_hop_distance(int start, int goal) const {
    const auto found = scorer_static_hops_.find({start, goal});
    if (found == scorer_static_hops_.end()) {
      throw std::logic_error(
          "frozen scorer static hop table is incomplete");
    }
    return found->second;
  }

  void apply_scorer(EventDecisionTraceRow& trace) {
    trace.scorer_id = canonical_scorer_id();
    trace.scorer_effective_id = trace.scorer_id;
    ++result_.summary.scorer_decision_evaluation_count;
    result_.summary.scorer_candidate_evaluation_count +=
        trace.candidates.size();
    const auto mode = canonical_scorer_mode();
    if (mode == "S0") {
      // Deliberate no-op: this branch must preserve the exact historical
      // candidate scores, tie breaks, and selected actions.
      for (auto& candidate : trace.candidates) {
        // Keep the scorer layer free of the separately-audited advertised
        // fault policy penalty, matching the raw S1-S4 convention.
        candidate.scorer_raw_score =
            candidate.pre_fault_policy_score;
        candidate.scorer_raw_score_available = true;
      }
      std::vector<std::size_t> raw_ranking(
          trace.candidates.size());
      for (std::size_t index = 0;
           index < raw_ranking.size();
           ++index) {
        raw_ranking[index] = index;
      }
      std::sort(
          raw_ranking.begin(),
          raw_ranking.end(),
          [&](std::size_t left, std::size_t right) {
            const auto& left_record = trace.candidates[left];
            const auto& right_record = trace.candidates[right];
            return std::tie(left_record.scorer_raw_score,
                            left_record.next_node) <
                   std::tie(right_record.scorer_raw_score,
                            right_record.next_node);
          });
      if (!raw_ranking.empty()) {
        const auto& best =
            trace.candidates[raw_ranking.front()];
        trace.scorer_raw_prediction = best.next_node;
        trace.scorer_raw_margin =
            raw_ranking.size() > 1
                ? trace.candidates[raw_ranking[1]]
                          .scorer_raw_score -
                      best.scorer_raw_score
                : 999.0;
      }
      return;
    }

    // The risk gate is an actual abstention contract, not only a diagnostic.
    // Preserve the complete historical S0 score pair before evaluating a
    // frozen adapter so an abstention can restore the exact S0 ranking on
    // every candidate, including the advertised-fault policy penalty.
    std::vector<std::pair<double, double>> s0_scores;
    s0_scores.reserve(trace.candidates.size());
    for (const auto& candidate : trace.candidates) {
      s0_scores.emplace_back(candidate.pre_fault_policy_score,
                             candidate.model_score);
    }

    if (mode == "S3" || mode == "S4") {
      for (auto& candidate : trace.candidates) {
        double score =
            candidate.travel_time + candidate.static_potential;
        if (mode == "S4") {
          score +=
              static_cast<double>(
                  candidate.target_queue_length +
                  candidate.target_scheduled_incoming) +
              std::max(0.0,
                       candidate.corridor_next_available -
                           trace.event_time) +
              std::max(
                  0.0,
                  candidate.target_next_available -
                      (trace.event_time + candidate.travel_time));
        }
        candidate.pre_fault_policy_score = score;
        candidate.model_score =
            score +
            (config_.enable_fault_policy &&
                     candidate.advertised_fault
                 ? 1.0e12
                 : 0.0);
        candidate.scorer_raw_score = score;
        candidate.scorer_raw_score_available = true;
      }
    } else {
      if (!scorer_model_.has_value()) {
        throw std::logic_error(
            "frozen scorer model was not initialized");
      }
      std::vector<std::vector<double>> feature_rows;
      feature_rows.reserve(trace.candidates.size());
      double best_static_cost =
          std::numeric_limits<double>::infinity();
      for (const auto& candidate : trace.candidates) {
        best_static_cost =
            std::min(best_static_cost,
                     candidate.travel_time +
                         candidate.static_potential);
      }
      const double current_potential =
          static_potential(trace.current_node, trace.goal_node);
      for (auto& candidate : trace.candidates) {
        const int candidate_out_degree =
            static_cast<int>(
                graph_.outgoing(candidate.next_node).size());
        double raw_bottleneck =
            std::max(0.0,
                     2.0 -
                         static_cast<double>(
                             candidate_out_degree));
        if (candidate.advertised_fault) {
          raw_bottleneck += 5.0;
        }
        candidate.scorer_raw_bottleneck = raw_bottleneck;
        const double static_cost =
            candidate.travel_time +
            candidate.static_potential;
        feature_rows.push_back({
            scorer_scale(candidate.static_potential, 100.0),
            scorer_scale(candidate.travel_time, 50.0),
            scorer_scale(
                graph_.service_time(candidate.next_node), 10.0),
            scorer_scale(
                static_cast<double>(
                    graph_.node(candidate.next_node).node_type),
                10.0),
            candidate.advertised_fault ? 1.0 : 0.0,
            candidate.next_node == trace.goal_node ? 1.0 : 0.0,
            0.0,
            mode == "S1"
                ? scorer_scale(
                      static_cast<double>(trace.current_node),
                      100.0)
                : 0.0,
            mode == "S1"
                ? scorer_scale(
                      static_cast<double>(trace.goal_node), 100.0)
                : 0.0,
            scorer_scale(
                static_cast<double>(trace.candidates.size()),
                10.0),
            trace.candidates.size() > 1 ? 1.0 : 0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            scorer_scale(
                static_cast<double>(
                    scorer_static_hop_distance(
                        candidate.next_node, trace.goal_node)),
                20.0),
            scorer_scale(
                static_cost - best_static_cost, 50.0),
            scorer_scale(raw_bottleneck, 10.0),
            scorer_scale(
                current_potential -
                    candidate.static_potential,
                100.0),
            0.0,
            0.0,
            0.0,
        });
      }
      const auto raw_scores =
          scorer_model_->scores(feature_rows);
      for (std::size_t index = 0;
           index < trace.candidates.size();
           ++index) {
        auto& candidate = trace.candidates[index];
        candidate.scorer_raw_score = raw_scores[index];
        candidate.scorer_raw_score_available = true;
        candidate.pre_fault_policy_score = -raw_scores[index];
        candidate.model_score =
            -raw_scores[index] +
            (config_.enable_fault_policy &&
                     candidate.advertised_fault
                 ? 1.0e12
                 : 0.0);
      }
    }

    std::vector<std::size_t> raw_ranking(
        trace.candidates.size());
    for (std::size_t index = 0;
         index < raw_ranking.size();
         ++index) {
      raw_ranking[index] = index;
    }
    std::sort(
        raw_ranking.begin(),
        raw_ranking.end(),
        [&](std::size_t left, std::size_t right) {
          const auto& left_record = trace.candidates[left];
          const auto& right_record = trace.candidates[right];
          if (mode == "S1" || mode == "S2") {
            if (left_record.scorer_raw_score !=
                right_record.scorer_raw_score) {
              return left_record.scorer_raw_score >
                     right_record.scorer_raw_score;
            }
            return left_record.next_node <
                   right_record.next_node;
          }
          return std::tie(left_record.scorer_raw_score,
                          left_record.next_node) <
                 std::tie(right_record.scorer_raw_score,
                          right_record.next_node);
        });
    if (raw_ranking.empty()) {
      return;
    }
    const auto& best = trace.candidates[raw_ranking.front()];
    trace.scorer_raw_prediction = best.next_node;
    if (raw_ranking.size() == 1) {
      trace.scorer_raw_margin = 999.0;
    } else {
      const auto& second = trace.candidates[raw_ranking[1]];
      trace.scorer_raw_margin =
          mode == "S1" || mode == "S2"
              ? best.scorer_raw_score -
                    second.scorer_raw_score
              : second.scorer_raw_score -
                    best.scorer_raw_score;
    }
    if (mode == "S1" || mode == "S2") {
      if (trace.scorer_raw_margin <
          config_.scorer_risk_margin_threshold) {
        trace.scorer_risk_reasons.push_back(
            "frozen_margin_below_threshold");
      }
      if (best.scorer_raw_bottleneck >=
          config_.scorer_risk_bottleneck_threshold) {
        trace.scorer_risk_reasons.push_back(
            "legal_local_bottleneck_at_or_above_threshold");
      }
      trace.scorer_risk_abstain =
          !trace.scorer_risk_reasons.empty();
      if (trace.scorer_risk_abstain) {
        trace.risk_gate_triggered = true;
        ++result_.summary.scorer_risk_abstain_count;
        trace.scorer_effective_id =
            "S0_current_handwritten_static_score";
        for (std::size_t index = 0;
             index < trace.candidates.size();
             ++index) {
          trace.candidates[index].pre_fault_policy_score =
              s0_scores[index].first;
          trace.candidates[index].model_score =
              s0_scores[index].second;
        }
      }
    }
  }

  std::optional<EventDecisionTraceRow> pibt_trace_for_bag(
      const BagState& bag,
      int node,
      double time,
      std::uint64_t arrive_event_seq,
      const PIBTCreditView& credit) {
    const auto& bounded_outgoing = graph_.outgoing(node);
    if (static_cast<int>(bounded_outgoing.size()) >
        config_.pibt_max_candidates_per_bag) {
      ++result_.summary
            .bounded_local_pibt_candidate_bound_rejection_count;
      return std::nullopt;
    }
    result_.summary
        .bounded_local_pibt_candidate_materialization_count +=
        bounded_outgoing.size();
    EventDecisionTraceRow trace;
    trace.decision_id = next_decision_id_++;
    trace.arrive_event_seq = arrive_event_seq;
    trace.event_time = time;
    trace.task_id = bag.request.task_id;
    trace.runtime_bag_id = bag.request.runtime_bag_id;
    trace.segment_id = bag.request.segment_id;
    trace.current_node = node;
    trace.goal_node = bag.request.goal;
    const auto& controller = junctions_.at(node);
    trace.junction_queue_length = static_cast<int>(controller.queue.size());
    trace.junction_next_dispatch_time = controller.next_dispatch_time;
    trace.short_history.assign(bag.history.begin(), bag.history.end());
    trace.full_astar_used = false;
    populate_priority_trace(trace, bag, time);
    const bool escape_active =
        config_.enable_deadlock_escape &&
        controller.escape_token_task == bag.request.runtime_bag_id;
    std::vector<int> outgoing = bounded_outgoing;
    std::sort(outgoing.begin(), outgoing.end());
    result_.summary.max_candidate_count =
        std::max(result_.summary.max_candidate_count,
                 static_cast<int>(outgoing.size()));
    for (const int candidate : outgoing) {
      trace.candidates.push_back(candidate_record(
          bag,
          node,
          candidate,
          time,
          escape_active,
          credit.required,
          credit.ready,
          credit.to_node));
      const auto& record = trace.candidates.back();
      if (record.advertised_fault) {
        ++trace.advertised_faulted_outgoing_count;
      }
      trace.max_fault_message_age_seconds =
          std::max(trace.max_fault_message_age_seconds,
                   record.fault_message_age_seconds);
    }
    apply_scorer(trace);
    std::vector<std::size_t> ranking(trace.candidates.size());
    for (std::size_t index = 0; index < ranking.size(); ++index) {
      ranking[index] = index;
    }
    std::sort(ranking.begin(), ranking.end(), [&](std::size_t left,
                                                   std::size_t right) {
      const auto& left_record = trace.candidates[left];
      const auto& right_record = trace.candidates[right];
      return std::tie(left_record.model_score, left_record.next_node) <
             std::tie(right_record.model_score, right_record.next_node);
    });
    // model_prediction describes the scorer over the emitted candidate set.
    // Admission credit constrains the selected action, not the model output.
    if (!ranking.empty()) {
      trace.model_prediction =
          trace.candidates[ranking.front()].next_node;
      trace.model_margin =
          ranking.size() > 1
              ? trace.candidates[ranking[1]].model_score -
                    trace.candidates[ranking[0]].model_score
              : 999.0;
    }
    if (credit.required) {
      ranking.erase(
          std::remove_if(ranking.begin(),
                         ranking.end(),
                         [&](std::size_t index) {
                           return !credit.ready ||
                                  trace.candidates[index].next_node !=
                                      credit.to_node;
                         }),
          ranking.end());
    }
    return trace;
  }

  void mark_fault_exposure(BagState& bag,
                           long long physical_key,
                           int physical_generation,
                           std::optional<int> exact_fault_instance =
                               std::nullopt) {
    bag.fault_priority_generation =
        std::max(
            bag.fault_priority_generation,
            static_cast<std::uint64_t>(
                std::max(0, physical_generation)));
    if (g4irsf16_enabled()) {
      auto& generation =
          g4irsf16_physical_fault_generation_by_bag_[
              bag.request.runtime_bag_id];
      generation = std::max(
          generation,
          static_cast<std::uint64_t>(
              std::max(0, physical_generation)));
    }
    bag.repaired_task_reentry = false;
    fault_affected_bags_.insert(bag.request.runtime_bag_id);
    fault_affected_bags_by_edge_[physical_key].insert(
        bag.request.runtime_bag_id);
    const auto active_instance =
        active_fault_instance_by_edge_.find(physical_key);
    if (exact_fault_instance.has_value()) {
      fault_instances_by_bag_[bag.request.runtime_bag_id].insert(
          {physical_key, *exact_fault_instance});
    } else if (active_instance != active_fault_instance_by_edge_.end()) {
      fault_instances_by_bag_[bag.request.runtime_bag_id].insert(
          {physical_key, active_instance->second});
    }
    result_.summary.fault_affected_bag_count =
        static_cast<int>(fault_affected_bags_.size());
  }

  [[nodiscard]] bool local_inflight_fault_instance_observed(
      long long physical_key,
      int entry_physical_generation,
      int current_physical_generation) const noexcept {
    if (entry_physical_generation < 0 ||
        current_physical_generation <= entry_physical_generation ||
        entry_physical_generation == std::numeric_limits<int>::max()) {
      return false;
    }
    const auto active = active_fault_instance_by_edge_.find(physical_key);
    if (active != active_fault_instance_by_edge_.end() &&
        active->second > entry_physical_generation &&
        active->second <= current_physical_generation) {
      return true;
    }
    const auto repaired = repair_time_by_fault_instance_.lower_bound(
        {physical_key, entry_physical_generation + 1});
    return repaired != repair_time_by_fault_instance_.end() &&
           repaired->first.first == physical_key &&
           repaired->first.second <= current_physical_generation;
  }

  void mark_inflight_fault_generation_recovery(
      BagState& bag,
      long long physical_key,
      int entry_physical_generation,
      int current_physical_generation,
      bool physical_fault_active) {
    bool repaired_instance_observed = false;
    if (entry_physical_generation != std::numeric_limits<int>::max()) {
      for (auto repaired = repair_time_by_fault_instance_.lower_bound(
               {physical_key, entry_physical_generation + 1});
           repaired != repair_time_by_fault_instance_.end() &&
           repaired->first.first == physical_key &&
           repaired->first.second <= current_physical_generation;
           ++repaired) {
        mark_fault_exposure(
            bag,
            physical_key,
            current_physical_generation,
            repaired->first.second);
        repaired_instance_observed = true;
      }
    }
    const auto active = active_fault_instance_by_edge_.find(physical_key);
    if (active != active_fault_instance_by_edge_.end() &&
        active->second > entry_physical_generation &&
        active->second <= current_physical_generation) {
      mark_fault_exposure(
          bag,
          physical_key,
          current_physical_generation,
          active->second);
    }
    // A fault repaired before edge exit was not yet associated with this bag
    // at repair-message time.  Mint the same one-edge repaired priority token
    // now that the exact in-flight exposure has been proven.
    if (!physical_fault_active && repaired_instance_observed &&
        !bag.repaired_task_reentry) {
      bag.repaired_task_reentry = true;
      bag.fault_priority_generation = std::max(
          bag.fault_priority_generation,
          static_cast<std::uint64_t>(
              std::max(0, current_physical_generation)));
      if (g4irsf16_enabled()) {
        auto& generation = g4irsf16_physical_fault_generation_by_bag_[
            bag.request.runtime_bag_id];
        generation = std::max(
            generation,
            static_cast<std::uint64_t>(
                std::max(0, current_physical_generation)));
      }
      bag.local_enqueue_sequence = next_local_enqueue_sequence_++;
      ++result_.summary.repaired_task_reentry_count;
    }
  }

  void clear_consumed_repair_reentry_boost(
      BagState& bag) noexcept {
    if (!bag.repaired_task_reentry) {
      return;
    }
    // The repair boost is deliberately a one-successful-re-entry token.
    // Keep it through holds so the recovered bag receives the intended
    // local priority once, then revoke both the marker and generation after
    // its next committed one-edge action.
    bag.repaired_task_reentry = false;
    bag.fault_priority_generation = 0;
    ++result_.summary.repaired_task_reentry_boost_cleared_count;
  }

  void record_committed_pibt_fault_accounting(
      EventDecisionTraceRow& trace,
      BagState& bag,
      int selected_next) {
    for (const auto& record : trace.candidates) {
      const long long physical_key =
          event_runtime_detail::directed_key(trace.current_node,
                                             record.next_node);
      const auto physical = physical_faults_.find(physical_key);
      if (physical == physical_faults_.end() ||
          physical->second.active_count <= 0) {
        continue;
      }
      ++result_.summary.fault_target_edge_candidate_exposure_count;
      mark_fault_exposure(
          bag,
          physical_key,
          physical->second.physical_generation);
      append_fault_decision_audit(
          trace.arrive_event_seq,
          "target_edge_candidate_exposure",
          trace.event_time,
          bag,
          trace.current_node,
          record.next_node,
          -1);
    }

    std::vector<std::size_t> pre_policy_ranking;
    pre_policy_ranking.reserve(trace.candidates.size());
    for (std::size_t index = 0;
         index < trace.candidates.size();
         ++index) {
      const auto& record = trace.candidates[index];
      if (!record.first_edge_credit_required ||
          record.first_edge_credit_valid) {
        pre_policy_ranking.push_back(index);
      }
    }
    std::sort(
        pre_policy_ranking.begin(),
        pre_policy_ranking.end(),
        [&](std::size_t left, std::size_t right) {
          const auto& left_record = trace.candidates[left];
          const auto& right_record = trace.candidates[right];
          return std::tie(left_record.pre_fault_policy_score,
                          left_record.next_node) <
                 std::tie(right_record.pre_fault_policy_score,
                          right_record.next_node);
        });
    if (!pre_policy_ranking.empty()) {
      const auto& intended =
          trace.candidates[pre_policy_ranking.front()];
      const long long intended_key =
          event_runtime_detail::directed_key(trace.current_node,
                                             intended.next_node);
      const auto physical = physical_faults_.find(intended_key);
      if (physical != physical_faults_.end() &&
          physical->second.active_count > 0) {
        ++result_.summary.fault_target_edge_attempt_count;
        append_fault_decision_audit(
            trace.arrive_event_seq,
            "target_edge_attempt",
            trace.event_time,
            bag,
            trace.current_node,
            intended.next_node,
            -1);
      }
      if (config_.enable_fault_policy && intended.advertised_fault &&
          selected_next != intended.next_node) {
        ++result_.summary.local_fault_policy_action_count;
        if (selected_next >= 0) {
          ++result_.summary.local_fault_policy_reroute_count;
          append_fault_decision_audit(
              trace.arrive_event_seq,
              "local_fault_policy_reroute",
              trace.event_time,
              bag,
              trace.current_node,
              intended.next_node,
              selected_next);
        } else {
          ++result_.summary.local_fault_policy_hold_count;
          append_fault_decision_audit(
              trace.arrive_event_seq,
              "local_fault_policy_hold",
              trace.event_time,
              bag,
              trace.current_node,
              intended.next_node,
              -1);
        }
      }
    }

    if (trace.model_prediction >= 0 &&
        selected_next != trace.model_prediction) {
      const long long predicted_key =
          event_runtime_detail::directed_key(trace.current_node,
                                             trace.model_prediction);
      const auto physical = physical_faults_.find(predicted_key);
      if (physical != physical_faults_.end() &&
          physical->second.active_count > 0) {
        const auto predicted = std::find_if(
            trace.candidates.begin(),
            trace.candidates.end(),
            [&](const EventCandidateRecord& record) {
              return record.next_node == trace.model_prediction;
            });
        ++result_.summary.shield_rejection_count;
        if (predicted != trace.candidates.end() &&
            !predicted->advertised_fault) {
          ++result_.summary.stale_fault_shield_rejection_count;
        }
        ++result_.summary.physical_fault_interlock_rejection_count;
        append_fault_decision_audit(
            trace.arrive_event_seq,
            "physical_fault_interlock_rejection",
            trace.event_time,
            bag,
            trace.current_node,
            trace.model_prediction,
            -1);
        if (selected_next >= 0) {
          ++result_.summary.physical_fault_interlock_reroute_count;
          append_fault_decision_audit(
              trace.arrive_event_seq,
              "physical_fault_interlock_reroute",
              trace.event_time,
              bag,
              trace.current_node,
              trace.model_prediction,
              selected_next);
        } else {
          ++result_.summary.physical_fault_interlock_hold_count;
          append_fault_decision_audit(
              trace.arrive_event_seq,
              "physical_fault_interlock_hold",
              trace.event_time,
              bag,
              trace.current_node,
              trace.model_prediction,
              -1);
        }
      }
    }
  }

  std::optional<int> pibt_ready_owner_at_node(
      int node,
      double time,
      int* priority_comparison_count) const {
    const auto controller = junctions_.find(node);
    if (controller == junctions_.end() || controller->second.queue.empty() ||
        time + event_runtime_detail::kEpsilon <
            controller->second.next_dispatch_time) {
      return std::nullopt;
    }
    const std::size_t index = choose_bag(controller->second.queue,
                                         time,
                                         controller->second.escape_token_task,
                                         priority_comparison_count);
    const int runtime_bag_id = controller->second.queue[index];
    const auto bag = bags_.find(runtime_bag_id);
    if (bag == bags_.end() ||
        bag->second.status != BagStatus::kJunctionQueue ||
        bag->second.current != node ||
        bag->second.junction_enqueued_at >
            time + event_runtime_detail::kEpsilon ||
        bag->second.decision_count >= config_.max_decisions_per_bag) {
      return std::nullopt;
    }
    return runtime_bag_id;
  }

  bool merge_grant_authority_is_commit_ready(
      const MergeGrantCapability* authority,
      int trigger_runtime_bag_id,
      double time,
      std::string& blocker) const {
    if (authority == nullptr || authority->grant_id() == 0) {
      blocker = "CREDIT_OR_GRANT_MISSING";
      return false;
    }
    if (authority->state() != MergeGrantState::kCommitted ||
        authority->owner_runtime_bag_id() !=
            trigger_runtime_bag_id ||
        authority->exact_directed_edge().to_node !=
            authority->destination_node() ||
        time > authority->expiry() +
                   event_runtime_detail::kEpsilon) {
      blocker = "CREDIT_OR_GRANT_STALE";
      return false;
    }
    const auto bag = bags_.find(trigger_runtime_bag_id);
    if (bag == bags_.end() ||
        bag->second.status != BagStatus::kJunctionQueue ||
        bag->second.current !=
            authority->exact_directed_edge().from_node ||
        bag->second.request.runtime_bag_id !=
            trigger_runtime_bag_id ||
        !graph_.has_edge(
            authority->exact_directed_edge().from_node,
            authority->exact_directed_edge().to_node)) {
      blocker = "CREDIT_OR_GRANT_STALE";
      return false;
    }
    if (g4irsf14_state_ == nullptr) {
      blocker = "CREDIT_OR_GRANT_STALE";
      return false;
    }
    const auto merge_state =
        g4irsf14_state_->destination_merge_bags.find(
            trigger_runtime_bag_id);
    if (merge_state ==
            g4irsf14_state_->destination_merge_bags.end() ||
        !merge_state->second.capability.has_value() ||
        &*merge_state->second.capability != authority ||
        merge_state->second.request_generation !=
            authority->request_generation() ||
        merge_state->second.pending_request_id !=
            authority->request_id() ||
        merge_state->second.pending_lineage !=
            authority->lineage()) {
      blocker = "CREDIT_OR_GRANT_STALE";
      return false;
    }
    const auto controller =
        destination_merge_controllers_.find(
            authority->destination_node());
    if (controller ==
            destination_merge_controllers_.end() ||
        !controller->second.validates_active_capability(
            *authority)) {
      blocker = "CREDIT_OR_GRANT_STALE";
      return false;
    }
    const auto& destination =
        junctions_.at(authority->destination_node());
    if (!destination.service_calendar.contains_exact(
            trigger_runtime_bag_id,
            authority->slot_start(),
            authority->slot_end())) {
      blocker = "CREDIT_OR_GRANT_STALE";
      return false;
    }
    const long long directed =
        event_runtime_detail::directed_key(
            authority->exact_directed_edge().from_node,
            authority->exact_directed_edge().to_node);
    const auto physical = physical_faults_.find(directed);
    const auto advertised =
        advertised_faults_.find(directed);
    const int physical_generation =
        physical == physical_faults_.end()
            ? 0
            : physical->second.physical_generation;
    const int advertised_generation =
        advertised == advertised_faults_.end()
            ? 0
            : advertised->second.generation;
    if ((physical != physical_faults_.end() &&
         physical->second.active_count > 0) ||
        physical_generation != authority->fault_generation() ||
        advertised_generation !=
            authority->advertised_fault_generation()) {
      blocker = "FAULT_GENERATION_CHANGED";
      return false;
    }
    const auto& edge = graph_.edge(
        authority->exact_directed_edge().from_node,
        authority->exact_directed_edge().to_node);
    const double exact_start =
        authority->request_time() +
        std::max(edge.travel_time(),
                 config_.minimum_service_seconds);
    if (std::abs(exact_start - authority->slot_start()) >
            event_runtime_detail::kEpsilon ||
        std::abs(
            authority->slot_end() -
            authority->slot_start() -
            service_duration(authority->destination_node())) >
            event_runtime_detail::kEpsilon) {
      blocker = "CREDIT_OR_GRANT_STALE";
      return false;
    }
    return true;
  }

  PIBTLocalSlice build_pibt_local_slice(int trigger_node,
                                        int trigger_runtime_bag_id,
                                        double time,
                                        std::uint64_t arrive_event_seq,
                                        int* priority_comparison_count,
                                        const MergeGrantCapability*
                                            merge_grant_authority = nullptr) {
    PIBTLocalSlice slice;
    slice.trigger_runtime_bag_id = trigger_runtime_bag_id;
    if (merge_grant_authority != nullptr &&
        !merge_grant_authority_is_commit_ready(
            merge_grant_authority,
            trigger_runtime_bag_id,
            time,
            slice.blocker)) {
      return slice;
    }

    const auto trigger_bag = bags_.find(trigger_runtime_bag_id);
    if (trigger_bag == bags_.end() ||
        trigger_bag->second.status != BagStatus::kJunctionQueue ||
        trigger_bag->second.current != trigger_node) {
      slice.blocker = "trigger_bag_not_simultaneously_ready";
      return slice;
    }
    const auto trigger_credit =
        pibt_credit_view(trigger_bag->second, trigger_node, time);
    auto trigger_trace_result =
        pibt_trace_for_bag(trigger_bag->second,
                           trigger_node,
                           time,
                           arrive_event_seq,
                           trigger_credit);
    if (!trigger_trace_result.has_value()) {
      slice.blocker = "local_slice_candidate_bound_exceeded";
      return slice;
    }
    auto trigger_trace = std::move(*trigger_trace_result);
    const EventCandidateRecord* preferred = nullptr;
    for (const auto& candidate : trigger_trace.candidates) {
      if (merge_grant_authority != nullptr &&
          candidate.next_node !=
              merge_grant_authority
                  ->exact_directed_edge()
                  .to_node) {
        continue;
      }
      if (trigger_credit.required &&
          (!trigger_credit.ready ||
           candidate.next_node != trigger_credit.to_node)) {
        continue;
      }
      if (preferred == nullptr ||
          std::tie(candidate.model_score, candidate.next_node) <
              std::tie(preferred->model_score, preferred->next_node)) {
        preferred = &candidate;
      }
    }
    if (preferred == nullptr ||
        (merge_grant_authority == nullptr &&
         preferred->shield_reason != "destination_queue_full") ||
        (config_.enable_fault_policy && preferred->advertised_fault)) {
      slice.blocker = "trigger_preferred_edge_has_no_finite_queue_blocker";
      return slice;
    }
    slice.applicable = true;

    std::vector<int> pending{trigger_runtime_bag_id};
    std::set<int> inserted_bags;
    std::map<int, int> ready_owner_by_node;
    std::map<LocalPIBTResourceKey, int> owner_by_resource;
    std::set<LocalPIBTResourceKey> touched_resources;
    for (std::size_t pending_index = 0;
         pending_index < pending.size();
         ++pending_index) {
      const int runtime_bag_id = pending[pending_index];
      if (!inserted_bags.insert(runtime_bag_id).second) {
        continue;
      }
      if (static_cast<int>(inserted_bags.size()) >
          config_.pibt_max_ready_bags) {
        slice.applicable = false;
        slice.blocker = "local_slice_bag_bound_exceeded";
        return slice;
      }
      const auto found = bags_.find(runtime_bag_id);
      if (found == bags_.end() ||
          found->second.status != BagStatus::kJunctionQueue ||
          found->second.junction_enqueued_at >
              time + event_runtime_detail::kEpsilon) {
        slice.applicable = false;
        slice.blocker = "local_slice_contains_nonready_bag";
        return slice;
      }
      const auto& bag = found->second;
      const int node = bag.current;
      const auto existing_node_owner = ready_owner_by_node.find(node);
      if (existing_node_owner != ready_owner_by_node.end() &&
          existing_node_owner->second != runtime_bag_id) {
        slice.applicable = false;
        slice.blocker = "more_than_one_ready_owner_for_node";
        return slice;
      }
      ready_owner_by_node[node] = runtime_bag_id;
      const auto controller = junctions_.find(node);
      if (controller == junctions_.end() ||
          time + event_runtime_detail::kEpsilon <
              controller->second.next_dispatch_time) {
        slice.applicable = false;
        slice.blocker = "local_owner_dispatch_resource_not_ready";
        return slice;
      }

      const auto credit = pibt_credit_view(bag, node, time);
      EventDecisionTraceRow trace;
      if (runtime_bag_id == trigger_runtime_bag_id) {
        trace = std::move(trigger_trace);
      } else {
        auto trace_result = pibt_trace_for_bag(
            bag, node, time, arrive_event_seq, credit);
        if (!trace_result.has_value()) {
          slice.applicable = false;
          slice.blocker = "local_slice_candidate_bound_exceeded";
          return slice;
        }
        trace = std::move(*trace_result);
      }

      BoundedLocalPIBTReadyBag ready;
      ready.bag_id = runtime_bag_id;
      ready.current_node = node;
      ready.goal_node = bag.request.goal;
      ready.physical_fault_emergency =
          canonical_priority_mode() !=
                  BoundedLocalPIBTPriorityMode::kQ0Current &&
              bag.fault_priority_generation > 0;
      ready.deadline = bag.request.deadline;
      ready.ready_time = bag.junction_enqueued_at;
      ready.accumulated_wait =
          bag.total_wait + std::max(0.0, time - bag.junction_enqueued_at);
      ready.retry_age =
          std::max(0.0, time - bag.junction_enqueued_at);
      ready.source_release_age =
          std::max(0.0, time - bag.request.release_time);
      ready.movable = true;
      ready.in_transit = false;
      ready.task_class_rank =
          local_task_class_rank(bag);
      ready.fault_priority_generation =
          bag.fault_priority_generation;
      ready.local_contention =
          local_priority_contention(bag);
      ready.enqueue_sequence =
          bag.local_enqueue_sequence;
      bool filtered_missing_merge_grant = false;

      for (const auto& record : trace.candidates) {
        if (merge_grant_authority != nullptr &&
            runtime_bag_id == trigger_runtime_bag_id &&
            record.next_node !=
                merge_grant_authority
                    ->exact_directed_edge()
                    .to_node) {
          continue;
        }
        if (credit.required &&
            (!credit.ready || record.next_node != credit.to_node)) {
          continue;
        }
        if (config_.enable_fault_policy && record.advertised_fault) {
          continue;
        }
        if (!record.shield_allowed &&
            record.shield_reason != "destination_queue_full") {
          continue;
        }
        const int target = record.next_node;
        const auto& target_controller = junctions_[target];
        const int occupancy =
            static_cast<int>(target_controller.queue.size()) +
            target_controller.scheduled_incoming;
        std::optional<int> blocker_owner;
        if (target != bag.request.goal &&
            config_.local_queue_capacity > 0 &&
            occupancy >= config_.local_queue_capacity) {
          blocker_owner = pibt_ready_owner_at_node(
              target,
              time,
              priority_comparison_count);
          if (!blocker_owner.has_value()) {
            continue;
          }
          if (uses_destination_merge_grants() &&
              *blocker_owner != trigger_runtime_bag_id) {
            const auto blocker_merge =
                g4irsf14_state_
                    ->destination_merge_bags.find(
                        *blocker_owner);
            if (blocker_merge !=
                    g4irsf14_state_
                        ->destination_merge_bags.end() &&
                blocker_merge->second.pending_request_id !=
                    0) {
              continue;
            }
          }
          const auto node_resource = local_pibt_node_resource(target);
          const auto existing_owner = owner_by_resource.find(node_resource);
          if (existing_owner != owner_by_resource.end() &&
              existing_owner->second != *blocker_owner) {
            slice.applicable = false;
            slice.blocker = "ambiguous_local_node_owner";
            return slice;
          }
          owner_by_resource[node_resource] = *blocker_owner;
          pending.push_back(*blocker_owner);
        }
        const bool destination_merge_edge =
            uses_destination_merge_grants() &&
            graph_.incoming_degree(target) > 1 &&
            target != bag.request.goal;
        const bool exact_authorized_trigger =
            destination_merge_edge &&
            merge_grant_authority != nullptr &&
            runtime_bag_id == trigger_runtime_bag_id &&
            node ==
                merge_grant_authority
                    ->exact_directed_edge()
                    .from_node &&
            target ==
                merge_grant_authority
                    ->exact_directed_edge()
                    .to_node;
        if (destination_merge_edge &&
            !exact_authorized_trigger) {
          filtered_missing_merge_grant = true;
          continue;
        }

        BoundedLocalPIBTCandidate candidate;
        candidate.next_node = target;
        candidate.edge_resource =
            local_pibt_directed_edge_resource(node, target);
        candidate.required_resources = {
            candidate.edge_resource,
        };
        if (uses_destination_calendar(target,
                                      bag.request.goal) ||
            (target != bag.request.goal &&
             config_.local_queue_capacity > 0)) {
          candidate.required_resources.push_back(
              local_pibt_node_resource(target));
        }
        if (uses_corridor_calendar()) {
          candidate.required_resources.push_back(
              pibt_runtime_corridor_resource(
                  node, target, uses_directed_corridor()));
        }
        std::sort(candidate.required_resources.begin(),
                  candidate.required_resources.end());
        candidate.required_resources.erase(
            std::unique(candidate.required_resources.begin(),
                        candidate.required_resources.end()),
            candidate.required_resources.end());
        candidate.local_score = record.model_score;
        candidate.static_potential =
            record.static_potential;
        candidate.is_local_backtrack =
            record.recent_visit_count > 0;
        candidate.local_regret_prior =
            local_regret_prior(node, target, bag.request.goal);
        const double candidate_travel =
            std::max(
                graph_.edge(node, target).travel_time(),
                config_.minimum_service_seconds);
        const double candidate_slot_start =
            time + candidate_travel;
        const double candidate_slot_end =
            candidate_slot_start +
            service_duration(target);
        if (uses_destination_calendar(
                target, bag.request.goal) &&
            !junctions_[target]
                 .service_calendar.available(
                     candidate_slot_start,
                     candidate_slot_end,
                     runtime_bag_id)) {
          continue;
        }
        if (target != bag.request.goal &&
            config_.local_queue_capacity > 0 &&
            occupancy >= config_.local_queue_capacity &&
            !blocker_owner.has_value()) {
          continue;
        }
        const long long edge_key =
            event_runtime_detail::directed_key(node, target);
        const auto fault = physical_faults_.find(edge_key);
        candidate.expected_fault_generation =
            fault == physical_faults_.end()
                ? 0
                : static_cast<std::uint64_t>(
                      fault->second.physical_generation);
        candidate.physically_blocked_at_snapshot =
            fault != physical_faults_.end() &&
            fault->second.active_count > 0;
        ready.candidates.push_back(std::move(candidate));
        for (const auto resource :
             ready.candidates.back().required_resources) {
          touched_resources.insert(resource);
        }
        slice.edge_by_resource[ready.candidates.back().edge_resource] =
            {node, target};
      }
      slice.candidate_count += static_cast<int>(ready.candidates.size());
      if (merge_grant_authority != nullptr &&
          ready.candidates.empty()) {
        slice.applicable = false;
        slice.blocker =
            filtered_missing_merge_grant
                ? "CREDIT_OR_GRANT_MISSING"
                : "NO_ALTERNATIVE_EDGE";
        return slice;
      }
      slice.traces_by_bag.emplace(runtime_bag_id, std::move(trace));
      slice.ready_bags.push_back(std::move(ready));
    }

    for (const auto& entry : owner_by_resource) {
      BoundedLocalPIBTResourceOwner owner;
      owner.resource = entry.first;
      owner.bag_id = entry.second;
      owner.movable = true;
      owner.in_transit = false;
      slice.owners.push_back(owner);
      auto bag = std::find_if(
          slice.ready_bags.begin(),
          slice.ready_bags.end(),
          [&](const BoundedLocalPIBTReadyBag& ready) {
            return ready.bag_id == entry.second;
          });
      if (bag == slice.ready_bags.end()) {
        slice.applicable = false;
        slice.blocker = "local_owner_missing_from_ready_slice";
        return slice;
      }
      if (merge_grant_authority != nullptr &&
          bag->candidates.empty()) {
        slice.applicable = false;
        slice.blocker = "NO_ALTERNATIVE_EDGE";
        return slice;
      }
      bag->held_resources.push_back(entry.first);
      touched_resources.insert(entry.first);
    }
    for (auto& ready : slice.ready_bags) {
      std::sort(ready.held_resources.begin(), ready.held_resources.end());
      ready.held_resources.erase(
          std::unique(ready.held_resources.begin(),
                      ready.held_resources.end()),
          ready.held_resources.end());
    }
    if (canonical_pibt_preference_mode() !=
        BoundedLocalPIBTPreferenceMode::kCurrent) {
      std::map<int, BoundedLocalPIBTReadyBag*> ready_by_node;
      for (auto& ready : slice.ready_bags) {
        ready_by_node.emplace(ready.current_node, &ready);
      }
      for (auto& ready : slice.ready_bags) {
        const auto current_bag = bags_.find(ready.bag_id);
        for (auto& candidate : ready.candidates) {
          ++result_.summary.pibt_preference_candidate_count;
          if (candidate.is_local_backtrack) {
            ++result_.summary
                  .pibt_preference_backtrack_penalty_count;
          }
          if (candidate.local_regret_prior > 0.0) {
            ++result_.summary
                  .pibt_preference_regret_prior_hit_count;
          }
          const auto owner =
              ready_by_node.find(candidate.next_node);
          if (owner == ready_by_node.end() ||
              owner->second->bag_id == ready.bag_id) {
            continue;
          }
          candidate.occupies_unique_exit =
              owner->second->candidates.size() == 1;
          if (candidate.occupies_unique_exit) {
            ++result_.summary
                  .pibt_preference_unique_exit_penalty_count;
          }
          const auto owner_bag =
              bags_.find(owner->second->bag_id);
          candidate.blocks_higher_priority_exit =
              current_bag != bags_.end() &&
              owner_bag != bags_.end() &&
              local_priority_less(owner_bag->second,
                                  current_bag->second,
                                  time);
          candidate.enters_wait_for_cycle =
              std::any_of(
                  owner->second->candidates.begin(),
                  owner->second->candidates.end(),
                  [&](const BoundedLocalPIBTCandidate& owner_candidate) {
                    return owner_candidate.next_node ==
                           ready.current_node;
                  });
          if (candidate.enters_wait_for_cycle) {
            ++result_.summary
                  .pibt_preference_wait_cycle_penalty_count;
          }
        }
      }
    }
    slice.resource_count = static_cast<int>(touched_resources.size());
    if (slice.resource_count > config_.pibt_max_local_resources) {
      slice.applicable = false;
      slice.blocker = "local_slice_resource_bound_exceeded";
      return slice;
    }
    if (slice.ready_bags.empty() || slice.owners.empty()) {
      slice.applicable = false;
      slice.blocker = "no_real_finite_capacity_blocker_owner";
    }
    return slice;
  }

  bool pibt_credit_is_commit_ready(const BagState& bag,
                                   int from_node,
                                   int to_node,
                                   double time) const {
    if (!uses_first_edge_credit() ||
        !first_edge_credit_required_for_bag(bag, from_node)) {
      return true;
    }
    if (bag.first_edge_credit_id == 0) {
      return false;
    }
    const auto* credit = credit_ledger_.find(bag.first_edge_credit_id);
    if (credit == nullptr || credit->state != FirstEdgeCreditState::kIssued ||
        credit->from_node != from_node || credit->to_node != to_node ||
        credit->goal != bag.request.goal ||
        (credit->owner_or_unbound >= 0 &&
         credit->owner_or_unbound != bag.request.runtime_bag_id) ||
        time + event_runtime_detail::kEpsilon < credit->earliest ||
        time > credit->latest + event_runtime_detail::kEpsilon ||
        time > credit->expiry + event_runtime_detail::kEpsilon) {
      return false;
    }
    const auto context =
        credit_use_context(bag, from_node, to_node, time);
    return !context.physical_fault_active &&
           context.generation == credit->generation &&
           context.fault_generation == credit->fault_generation;
  }

  bool prevalidate_pibt_batch(
      const std::vector<BoundedLocalPIBTAction>& actions,
      double time,
      std::string& blocker,
      const MergeGrantCapability*
          merge_grant_authority = nullptr,
      int merge_grant_trigger_bag_id = -1) const {
    if (actions.empty() ||
        static_cast<int>(actions.size()) > config_.pibt_max_ready_bags) {
      blocker = "empty_or_oversized_action_batch";
      return false;
    }
    if (merge_grant_authority != nullptr &&
        !merge_grant_authority_is_commit_ready(
            merge_grant_authority,
            merge_grant_trigger_bag_id,
            time,
            blocker)) {
      return false;
    }
    bool authorized_trigger_action_seen = false;
    std::set<int> action_bags;
    std::set<int> action_from_nodes;
    std::map<int, int> leaving_by_node;
    std::map<int, int> entering_nonterminal_by_node;
    std::map<long long, std::vector<CalendarInterval>>
        staged_corridor_intervals;
    std::map<int, std::vector<CalendarInterval>>
        staged_destination_intervals;

    const auto overlaps_staged =
        [](const std::vector<CalendarInterval>& intervals,
           double start,
           double end,
           int ignore_task) {
          return std::any_of(
              intervals.begin(),
              intervals.end(),
              [&](const CalendarInterval& item) {
                return item.task_id != ignore_task &&
                       start < item.end -
                                   event_runtime_detail::kEpsilon &&
                       item.start <
                           end - event_runtime_detail::kEpsilon;
              });
        };

    for (const auto& action : actions) {
      if (!action_bags.insert(action.bag_id).second ||
          !action_from_nodes.insert(action.from_node).second) {
        blocker = "duplicate_bag_or_ready_owner_node";
        return false;
      }
      const auto bag_found = bags_.find(action.bag_id);
      const auto controller_found = junctions_.find(action.from_node);
      if (bag_found == bags_.end() ||
          controller_found == junctions_.end() ||
          bag_found->second.status != BagStatus::kJunctionQueue ||
          bag_found->second.current != action.from_node ||
          !graph_.has_edge(action.from_node, action.next_node) ||
          std::count(controller_found->second.queue.begin(),
                     controller_found->second.queue.end(),
                     action.bag_id) != 1 ||
          time + event_runtime_detail::kEpsilon <
              controller_found->second.next_dispatch_time) {
        blocker = "action_bag_or_local_dispatch_state_changed";
        return false;
      }
      const auto& bag = bag_found->second;
      const bool destination_merge_edge =
          uses_destination_merge_grants() &&
          graph_.incoming_degree(action.next_node) > 1 &&
          action.next_node != bag.request.goal;
      if (destination_merge_edge) {
        const bool exact_authorized_trigger =
            merge_grant_authority != nullptr &&
            action.bag_id == merge_grant_trigger_bag_id &&
            action.from_node ==
                merge_grant_authority
                    ->exact_directed_edge()
                    .from_node &&
            action.next_node ==
                merge_grant_authority
                    ->exact_directed_edge()
                    .to_node;
        if (!exact_authorized_trigger) {
          blocker = "CREDIT_OR_GRANT_MISSING";
          return false;
        }
        authorized_trigger_action_seen = true;
      } else if (merge_grant_authority != nullptr &&
                 action.bag_id ==
                     merge_grant_trigger_bag_id) {
        blocker = "CREDIT_OR_GRANT_STALE";
        return false;
      }
      if (!pibt_credit_is_commit_ready(
              bag, action.from_node, action.next_node, time)) {
        blocker = "first_edge_credit_not_commit_ready";
        return false;
      }
      const long long directed = event_runtime_detail::directed_key(
          action.from_node, action.next_node);
      const auto fault = physical_faults_.find(directed);
      const std::uint64_t generation =
          fault == physical_faults_.end()
              ? 0
              : static_cast<std::uint64_t>(
                    fault->second.physical_generation);
      if ((fault != physical_faults_.end() &&
           fault->second.active_count > 0) ||
          generation != action.expected_fault_generation) {
        blocker = "physical_fault_generation_changed";
        return false;
      }
      ++leaving_by_node[action.from_node];
      if (action.next_node != bag.request.goal) {
        ++entering_nonterminal_by_node[action.next_node];
      }

      const auto& edge =
          graph_.edge(action.from_node, action.next_node);
      const double travel =
          std::max(edge.travel_time(), config_.minimum_service_seconds);
      const double corridor_end =
          time + corridor_reservation_duration(travel);
      if (uses_corridor_calendar()) {
        const long long key =
            resource_corridor_key(action.from_node, action.next_node);
        const auto existing = corridors_.find(key);
        if ((existing != corridors_.end() &&
             !existing->second.available(
                 time, corridor_end, action.bag_id)) ||
            overlaps_staged(staged_corridor_intervals[key],
                            time,
                            corridor_end,
                            action.bag_id)) {
          blocker = "corridor_calendar_changed";
          return false;
        }
        staged_corridor_intervals[key].push_back(
            CalendarInterval{
                action.bag_id, time, corridor_end});
      }

      if (uses_destination_calendar(action.next_node,
                                    bag.request.goal)) {
        const double service_start = time + travel;
        const double service_end =
            service_start + service_duration(action.next_node);
        const auto existing = junctions_.find(action.next_node);
        if ((existing != junctions_.end() &&
             !existing->second.service_calendar.available(
                 service_start, service_end, action.bag_id)) ||
            overlaps_staged(
                staged_destination_intervals[action.next_node],
                service_start,
                service_end,
                action.bag_id)) {
          blocker = "destination_calendar_changed";
          return false;
        }
        staged_destination_intervals[action.next_node].push_back(
            CalendarInterval{
                action.bag_id, service_start, service_end});
      }
    }

    std::set<int> capacity_nodes;
    for (const auto& entry : leaving_by_node) {
      capacity_nodes.insert(entry.first);
    }
    for (const auto& entry : entering_nonterminal_by_node) {
      capacity_nodes.insert(entry.first);
    }
    for (const int node : capacity_nodes) {
      const auto controller = junctions_.find(node);
      const int queue_size =
          controller == junctions_.end()
              ? 0
              : static_cast<int>(controller->second.queue.size());
      const int scheduled =
          controller == junctions_.end()
              ? 0
              : controller->second.scheduled_incoming;
      const int leaving = leaving_by_node[node];
      const int entering = entering_nonterminal_by_node[node];
      if (config_.local_queue_capacity > 0 &&
          queue_size - leaving + scheduled + entering >
              config_.local_queue_capacity) {
        blocker = "finite_local_queue_capacity_prevalidation_failed";
        return false;
      }
    }
    if (merge_grant_authority != nullptr &&
        !authorized_trigger_action_seen) {
      blocker = "CREDIT_OR_GRANT_MISSING";
      return false;
    }
    return true;
  }

  bool build_pibt_credit_batch(
      const std::vector<BoundedLocalPIBTAction>& actions,
      double time,
      std::vector<FirstEdgeCreditBatchEntry>& entries,
      std::string& blocker) const {
    entries.clear();
    entries.reserve(actions.size());
    for (const auto& action : actions) {
      const auto bag_found = bags_.find(action.bag_id);
      if (bag_found == bags_.end()) {
        blocker = "credit_batch_bag_missing";
        return false;
      }
      const auto& bag = bag_found->second;
      if (!uses_first_edge_credit() ||
          !first_edge_credit_required_for_bag(
              bag, action.from_node)) {
        continue;
      }
      if (!pibt_credit_is_commit_ready(
              bag, action.from_node, action.next_node, time)) {
        blocker = "first_edge_credit_not_commit_ready";
        return false;
      }
      entries.push_back(FirstEdgeCreditBatchEntry{
          bag.first_edge_credit_id,
          credit_use_context(
              bag, action.from_node, action.next_node, time)});
    }
    if (entries.size() > actions.size() ||
        static_cast<int>(entries.size()) >
            config_.pibt_max_ready_bags) {
      blocker = "credit_transaction_bound_exceeded";
      return false;
    }
    return true;
  }

#ifdef CZR005_EVENT_RUNTIME_TESTING
  std::uint64_t test_junction_logical_fingerprint(
      const JunctionState& junction) const {
    std::uint64_t hash = 1469598103934665603ULL;
    const auto mix = [&](std::uint64_t value) {
      hash ^= value;
      hash *= 1099511628211ULL;
    };
    for (const int bag_id : junction.source_queue) {
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(bag_id)));
    }
    mix(0x51ceULL);
    for (const int bag_id : junction.queue) {
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(bag_id)));
    }
    mix(junction.service_calendar
            .logical_state_fingerprint());
    mix(static_cast<std::uint64_t>(
        junction.scheduled_incoming));
    std::vector<std::pair<int, int>> goals(
        junction.scheduled_incoming_by_goal.begin(),
        junction.scheduled_incoming_by_goal.end());
    std::sort(goals.begin(), goals.end());
    mix(static_cast<std::uint64_t>(goals.size()));
    for (const auto& goal : goals) {
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(goal.first)));
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(goal.second)));
    }
    mix(static_cast<std::uint64_t>(
        junction.peak_source_queue_length));
    mix(static_cast<std::uint64_t>(
        junction.peak_junction_queue_length));
    mix(static_cast<std::uint64_t>(
        junction.peak_service_calendar_intervals));
    mix(static_cast<std::uint64_t>(
        junction.peak_local_state_accounted_bytes));
    mix(junction.service_reservation_count);
    mix(event_runtime_detail::timestamp_bits(
        junction.cumulative_service_reserved_seconds));
    mix(event_runtime_detail::timestamp_bits(
        junction.first_service_reservation_start_time));
    mix(event_runtime_detail::timestamp_bits(
        junction.last_service_reservation_end_time));
    mix(junction.source_wakeup_generation);
    mix(junction.junction_wakeup_generation);
    mix(junction.source_wakeup_pending ? 1 : 0);
    mix(junction.junction_wakeup_pending ? 1 : 0);
    mix(event_runtime_detail::timestamp_bits(
        junction.next_dispatch_time));
    mix(static_cast<std::uint64_t>(
        static_cast<std::uint32_t>(
            junction.escape_token_task)));
    return hash;
  }

  std::uint64_t test_event_queue_logical_fingerprint()
      const noexcept {
    std::uint64_t hash = 1469598103934665603ULL;
    const auto mix = [&](std::uint64_t value) {
      hash ^= value;
      hash *= 1099511628211ULL;
    };
    events_.inspect([&](const RuntimeEvent& event) {
      mix(static_cast<std::uint64_t>(event.type));
      mix(event_runtime_detail::timestamp_bits(event.time));
      mix(event.seq);
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(event.task_id)));
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(event.node)));
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(event.from_node)));
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(event.to_node)));
      mix(event.retry ? 1 : 0);
      mix(event.wakeup_generation);
      mix(event.notification ? 1 : 0);
      mix(event.message_generation);
      mix(event_runtime_detail::timestamp_bits(
          event.service_end));
      mix(event_runtime_detail::timestamp_bits(
          event.message_delay));
      mix(event.drop_notification ? 1 : 0);
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(
              event.microphase_priority)));
      mix(static_cast<std::uint64_t>(
          std::hash<std::string>{}(event.reason)));
    });
    return hash;
  }

  std::uint64_t
  test_destination_merge_controller_fingerprint(
      const DestinationMergeGrantController& controller)
      const noexcept {
    std::uint64_t hash = 1469598103934665603ULL;
    const auto mix = [&](std::uint64_t value) {
      hash ^= value;
      hash *= 1099511628211ULL;
    };
    mix(static_cast<std::uint64_t>(
        static_cast<std::uint32_t>(
            controller.destination_node_)));
    mix(controller.generation_);
    mix(controller.next_request_id_);
    mix(controller.next_grant_id_);
    mix(controller.pending_.size());
    for (const auto& pending : controller.pending_) {
      mix(pending.request.request_id);
      mix(pending.request.lineage);
      mix(pending.request.request_generation);
      mix(pending.request.junction_queue_generation);
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(
              pending.request.runtime_bag_id)));
      mix(event_runtime_detail::timestamp_bits(
          pending.request.request_time));
      mix(event_runtime_detail::timestamp_bits(
          pending.request.expiry));
    }
    mix(controller.active_.size());
    for (const auto& active : controller.active_) {
      mix(active.grant_id);
      mix(active.request_id);
      mix(active.lineage);
      mix(active.request_generation);
      mix(active.junction_queue_generation);
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(
              active.owner_runtime_bag_id)));
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(
              active.edge.from_node)));
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(
              active.edge.to_node)));
      mix(event_runtime_detail::timestamp_bits(
          active.slot_start));
      mix(event_runtime_detail::timestamp_bits(
          active.slot_end));
      mix(event_runtime_detail::timestamp_bits(
          active.issue_time));
      mix(event_runtime_detail::timestamp_bits(
          active.grant_expiry));
      mix(active.calendar_generation);
      mix(static_cast<std::uint64_t>(
          active.physical_fault_generation));
      mix(static_cast<std::uint64_t>(
          active.advertised_fault_generation));
    }
    const auto& counters = controller.counters_;
    mix(counters.request_count);
    mix(counters.issued_count);
    mix(counters.prepared_count);
    mix(counters.committed_count);
    mix(counters.issued_transition_count);
    mix(counters.prepared_transition_count);
    mix(counters.committed_transition_count);
    mix(counters.consumed_count);
    mix(counters.inflight_fault_generation_recovery_count);
    mix(counters.expired_count);
    mix(counters.request_expired_count);
    mix(counters.grant_expired_count);
    mix(counters.revoked_count);
    mix(counters.revoked_fault_count);
    mix(counters.revoked_stale_state_count);
    mix(counters.revoked_replan_current_edge_count);
    mix(counters.rolled_back_count);
    mix(counters.post_commit_revoked_count);
    mix(counters.post_commit_expired_count);
    mix(counters.post_commit_rollback_count);
    mix(counters.lifecycle_transition_count);
    mix(counters.lifecycle_stored_count);
    mix(counters.lifecycle_dropped_count);
    mix(controller.lifecycle_.size());
    if (!controller.lifecycle_.empty()) {
      const auto& tail = controller.lifecycle_.back();
      mix(tail.request_id);
      mix(tail.grant_id);
      mix(static_cast<std::uint64_t>(tail.state));
      mix(static_cast<std::uint64_t>(tail.reason));
      mix(event_runtime_detail::timestamp_bits(
          tail.time));
    }
    return hash;
  }

  std::uint64_t
  test_pending_merge_dispatches_logical_fingerprint()
      const {
    std::vector<std::pair<std::uint64_t, std::uint64_t>>
        rows;
    rows.reserve(pending_merge_dispatches_.size());
    for (const auto& entry :
         pending_merge_dispatches_) {
      std::uint64_t value = 1469598103934665603ULL;
      const auto mix = [&](std::uint64_t item) {
        value ^= item;
        value *= 1099511628211ULL;
      };
      mix(entry.second.request_id);
      mix(entry.second.lineage);
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(
              entry.second.runtime_bag_id)));
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(
              entry.second.upstream_node)));
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(
              entry.second.destination_node)));
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(
              entry.second.trace.selected_next)));
      mix(static_cast<std::uint64_t>(
          std::hash<std::string>{}(
              entry.second.trace.decision_source)));
      mix(static_cast<std::uint64_t>(
          std::hash<std::string>{}(
              entry.second.trace.rule_reason)));
      mix(entry.second.trace.candidates.size());
      rows.emplace_back(entry.first, value);
    }
    std::sort(rows.begin(), rows.end());
    std::uint64_t hash = 1469598103934665603ULL;
    for (const auto& row : rows) {
      hash ^= row.first;
      hash *= 1099511628211ULL;
      hash ^= row.second;
      hash *= 1099511628211ULL;
    }
    return hash;
  }

  static bool test_credit_counters_equal(
      const FirstEdgeCreditCounters& left,
      const FirstEdgeCreditCounters& right) noexcept {
    return left.issue_attempt_count ==
               right.issue_attempt_count &&
           left.issued_count == right.issued_count &&
           left.validation_attempt_count ==
               right.validation_attempt_count &&
           left.validation_success_count ==
               right.validation_success_count &&
           left.bind_attempt_count ==
               right.bind_attempt_count &&
           left.bound_count == right.bound_count &&
           left.consume_attempt_count ==
               right.consume_attempt_count &&
           left.consumed_count == right.consumed_count &&
           left.expired_count == right.expired_count &&
           left.fault_revocation_count ==
               right.fault_revocation_count &&
           left.generation_revocation_count ==
               right.generation_revocation_count &&
           left.invalid_revocation_count ==
               right.invalid_revocation_count &&
           left.duplicate_rejection_count ==
               right.duplicate_rejection_count &&
           left.capacity_rejection_count ==
               right.capacity_rejection_count &&
           left.stale_snapshot_rejection_count ==
               right.stale_snapshot_rejection_count &&
           left.physical_fault_rejection_count ==
               right.physical_fault_rejection_count &&
           left.too_early_rejection_count ==
               right.too_early_rejection_count &&
           left.unknown_credit_rejection_count ==
               right.unknown_credit_rejection_count &&
           left.invalid_request_rejection_count ==
               right.invalid_request_rejection_count &&
           left.lifecycle_dropped_count ==
               right.lifecycle_dropped_count &&
           left.active_count == right.active_count &&
           left.peak_active_count ==
               right.peak_active_count;
  }

  static bool test_transaction_summary_equal(
      const EventRuntimeSummary& left,
      const EventRuntimeSummary& right) noexcept {
    return left.reservation_conflicts ==
               right.reservation_conflicts &&
           left.decision_count == right.decision_count &&
           left.resolved_deadlock_count ==
               right.resolved_deadlock_count &&
           left.max_deadlock_duration ==
               right.max_deadlock_duration &&
           left.max_local_calendar_intervals ==
               right.max_local_calendar_intervals &&
           left.max_corridor_calendar_intervals ==
               right.max_corridor_calendar_intervals &&
           left.fault_generation_commit_recheck_count ==
               right.fault_generation_commit_recheck_count &&
           left.opportunity_event_queue_inspection_count ==
               right.opportunity_event_queue_inspection_count &&
           left.merge_visibility_total_count ==
               right.merge_visibility_total_count &&
           left.merge_visibility_stored_count ==
               right.merge_visibility_stored_count &&
           left.merge_visibility_dropped_count ==
               right.merge_visibility_dropped_count &&
           left.event_seq_audit_total_count ==
               right.event_seq_audit_total_count &&
           left.event_seq_audit_stored_count ==
               right.event_seq_audit_stored_count &&
           left.event_seq_audit_dropped_count ==
               right.event_seq_audit_dropped_count &&
           left.duplicate_same_time_arbitration_prevented_count ==
               right.duplicate_same_time_arbitration_prevented_count &&
           left.bounded_local_pibt_max_transaction_credit_entries ==
               right.bounded_local_pibt_max_transaction_credit_entries &&
           left.bounded_local_pibt_max_transaction_bag_entries ==
               right.bounded_local_pibt_max_transaction_bag_entries &&
           left.bounded_local_pibt_max_transaction_junction_scalar_entries ==
               right.bounded_local_pibt_max_transaction_junction_scalar_entries &&
           left.bounded_local_pibt_max_transaction_action_deltas ==
               right.bounded_local_pibt_max_transaction_action_deltas &&
           left.bounded_local_pibt_max_transaction_calendar_generation_entries ==
               right.bounded_local_pibt_max_transaction_calendar_generation_entries;
  }
#endif

  void capture_pibt_transaction(
      const std::vector<BoundedLocalPIBTAction>& actions,
      double time,
      PIBTTransactionSnapshot& snapshot) {
    snapshot.differential_rollback =
        canonical_event_semantics() ==
        "E0_immediate_dispatch_f2";
    snapshot.summary = result_.summary;
    snapshot.action_deltas.reserve(actions.size());

    const auto capture_junction =
        [&](int node) -> PIBTJunctionSnapshot& {
      const auto inserted =
          snapshot.junctions.emplace(
              node, PIBTJunctionSnapshot{});
      auto& saved = inserted.first->second;
      if (inserted.second) {
        const auto& junction = junctions_.at(node);
        saved.node = node;
        saved.service_calendar_generation =
            junction.service_calendar.generation();
        if (!snapshot.differential_rollback) {
          saved.queue = junction.queue;
        }
        saved.peak_source_queue_length =
            junction.peak_source_queue_length;
        saved.peak_junction_queue_length =
            junction.peak_junction_queue_length;
        saved.peak_service_calendar_intervals =
            junction.peak_service_calendar_intervals;
        saved.peak_local_state_accounted_bytes =
            junction.peak_local_state_accounted_bytes;
        saved.service_reservation_count =
            junction.service_reservation_count;
        saved.cumulative_service_reserved_seconds =
            junction.cumulative_service_reserved_seconds;
        saved.first_service_reservation_start_time =
            junction.first_service_reservation_start_time;
        saved.last_service_reservation_end_time =
            junction.last_service_reservation_end_time;
        saved.next_dispatch_time = junction.next_dispatch_time;
        saved.scheduled_incoming = junction.scheduled_incoming;
        if (!snapshot.differential_rollback) {
          saved.scheduled_incoming_by_goal =
              junction.scheduled_incoming_by_goal;
        }
        saved.source_wakeup_generation =
            junction.source_wakeup_generation;
        saved.junction_wakeup_generation =
            junction.junction_wakeup_generation;
        saved.source_wakeup_pending =
            junction.source_wakeup_pending;
        saved.junction_wakeup_pending =
            junction.junction_wakeup_pending;
        saved.escape_token_task = junction.escape_token_task;
        if (g4irsf14_state_ != nullptr) {
          const auto local =
              g4irsf14_state_->local.find(node);
          saved.g4irsf14_local_state_existed =
              local != g4irsf14_state_->local.end();
          if (saved.g4irsf14_local_state_existed) {
            saved.g4irsf14_local_state = local->second;
          }
        }
#ifdef CZR005_EVENT_RUNTIME_TESTING
        saved.logical_state_fingerprint =
            test_junction_logical_fingerprint(junction);
#endif
      }
      return saved;
    };

    for (const auto& action : actions) {
      const auto& bag = bags_.at(action.bag_id);
      snapshot.bags.emplace(
          action.bag_id,
          PIBTBagSnapshot{
              action.bag_id,
              bag.status,
              bag.total_wait,
              bag.junction_queue_wait_seconds,
              bag.transit_from,
              bag.transit_to,
              bag.transit_merge_grant,
              bag.decision_count,
              bag.deadlock_started_at,
              bag.first_edge_credit_id,
              bag.first_edge_credit_consumed});
      if (uses_destination_merge_grants() &&
          g4irsf14_state_ != nullptr) {
        const auto merge =
            g4irsf14_state_
                ->destination_merge_bags.find(
                    action.bag_id);
        if (merge !=
            g4irsf14_state_
                ->destination_merge_bags.end()) {
          PIBTMergeBagSnapshot saved_merge;
          saved_merge.junction_queue_generation =
              merge->second
                  .junction_queue_generation;
          saved_merge.request_generation =
              merge->second.request_generation;
          saved_merge.pending_request_id =
              merge->second.pending_request_id;
          saved_merge.pending_lineage =
              merge->second.pending_lineage;
          saved_merge.pending_request_time =
              merge->second.pending_request_time;
          saved_merge.first_contention_time =
              merge->second.first_contention_time;
          saved_merge.grant_wait_seconds =
              merge->second.grant_wait_seconds;
          saved_merge.exact_grant_edge_entry_observed =
              merge->second.exact_grant_edge_entry_observed;
          saved_merge.capability_present =
              merge->second.capability.has_value();
          if (saved_merge.capability_present) {
            saved_merge.capability_identity =
                merge->second.capability
                    ->expectation();
          }
          snapshot.destination_merge_bags.emplace(
              action.bag_id,
              std::move(saved_merge));
        }
      }
      auto& from_saved = capture_junction(action.from_node);
      (void)capture_junction(action.next_node);

      auto& from = junctions_.at(action.from_node);
      const auto queued =
          std::find(from.queue.begin(), from.queue.end(), action.bag_id);
      if (queued == from.queue.end()) {
        throw std::logic_error(
            "PIBT transaction capture lost ready queue owner");
      }
      const auto& edge =
          graph_.edge(action.from_node, action.next_node);
      const double travel =
          std::max(edge.travel_time(), config_.minimum_service_seconds);
      PIBTActionDelta delta;
      delta.bag_id = action.bag_id;
      delta.from_node = action.from_node;
      delta.next_node = action.next_node;
      delta.queue_index = static_cast<std::size_t>(
          std::distance(from.queue.begin(), queued));
      delta.source_junction = &from;
      delta.source_queue_iterator = queued;
      const auto& destination = junctions_.at(action.next_node);
      delta.destination_goal = bag.request.goal;
      const auto destination_goal =
          destination.scheduled_incoming_by_goal.find(
              delta.destination_goal);
      delta.destination_goal_existed =
          destination_goal !=
          destination.scheduled_incoming_by_goal.end();
      if (delta.destination_goal_existed) {
        delta.destination_goal_value =
            destination_goal->second;
      }
      if (uses_corridor_calendar()) {
        delta.corridor_key =
            resource_corridor_key(action.from_node, action.next_node);
        const auto inserted =
            snapshot.corridors.emplace(
                delta.corridor_key,
                PIBTCorridorSnapshot{});
        if (inserted.second) {
          const auto corridor =
              corridors_.find(delta.corridor_key);
          inserted.first->second.existed =
              corridor != corridors_.end();
          delta.corridor_existed =
              inserted.first->second.existed;
          if (inserted.first->second.existed) {
            inserted.first->second.generation =
                corridor->second.generation();
            inserted.first->second
                .logical_state_fingerprint =
                corridor->second
                    .logical_state_fingerprint();
          }
        } else {
          delta.corridor_existed =
              inserted.first->second.existed;
        }
        delta.corridor_start = time;
        delta.corridor_end =
            time + corridor_reservation_duration(travel);
      }
      if (uses_destination_calendar(action.next_node,
                                    bag.request.goal)) {
        delta.destination_start = time + travel;
        delta.destination_end =
            delta.destination_start +
            service_duration(action.next_node);
      }
      snapshot.action_deltas.push_back(std::move(delta));
      (void)from_saved;
    }
    if (snapshot.bags.size() > actions.size() ||
        snapshot.junctions.size() > actions.size() * 2 ||
        snapshot.corridors.size() > actions.size() ||
        snapshot.junctions.size() + snapshot.corridors.size() >
            actions.size() * 3 ||
        snapshot.action_deltas.size() != actions.size() ||
        static_cast<int>(snapshot.action_deltas.size()) >
            config_.pibt_max_ready_bags) {
      throw std::logic_error(
          "PIBT transaction delta bound exceeded");
    }
    result_.summary.bounded_local_pibt_max_transaction_bag_entries =
        std::max(
            result_.summary
                .bounded_local_pibt_max_transaction_bag_entries,
            static_cast<int>(snapshot.bags.size()));
    result_.summary
        .bounded_local_pibt_max_transaction_junction_scalar_entries =
        std::max(
            result_.summary
                .bounded_local_pibt_max_transaction_junction_scalar_entries,
            static_cast<int>(snapshot.junctions.size()));
    result_.summary.bounded_local_pibt_max_transaction_action_deltas =
        std::max(
            result_.summary
                .bounded_local_pibt_max_transaction_action_deltas,
            static_cast<int>(snapshot.action_deltas.size()));
    result_.summary
        .bounded_local_pibt_max_transaction_calendar_generation_entries =
        std::max(
            result_.summary
                .bounded_local_pibt_max_transaction_calendar_generation_entries,
            static_cast<int>(
                snapshot.junctions.size() +
                snapshot.corridors.size()));
    snapshot.summary = result_.summary;
    snapshot.next_event_seq = next_event_seq_;
#ifdef CZR005_EVENT_RUNTIME_TESTING
    snapshot.event_queue_size = events_.size();
    snapshot.event_queue_logical_fingerprint =
        test_event_queue_logical_fingerprint();
    snapshot.merge_visibility_size =
        result_.merge_request_visibility.size();
    snapshot.event_seq_audit_size =
        result_.event_seq_ordering_audit.size();
    snapshot.credit_counters =
        credit_ledger_.counters();
    snapshot.credit_active_count =
        credit_ledger_.stored_active_count();
    snapshot.credit_lifecycle_count =
        credit_ledger_.stored_lifecycle_count();
    for (const auto& controller :
         destination_merge_controllers_) {
      snapshot
          .destination_merge_controller_fingerprints
          .emplace(
              controller.first,
              test_destination_merge_controller_fingerprint(
                  controller.second));
    }
    snapshot
        .pending_merge_dispatches_logical_fingerprint =
        test_pending_merge_dispatches_logical_fingerprint();
#endif
    snapshot.captured = true;
  }

  void restore_pibt_transaction(PIBTTransactionSnapshot& snapshot) {
    staged_event_sink_ = nullptr;
    staged_merge_visibility_sink_ = nullptr;
    staged_destination_known_competitor_counts_ =
        nullptr;
    snapshot.staged_events.clear();
    snapshot.staged_merge_visibility.clear();
    snapshot.staged_destination_known_competitor_counts
        .clear();
    if (!snapshot.captured || !snapshot.mutated) {
      return;
    }
    result_.summary = snapshot.summary;
    next_event_seq_ = snapshot.next_event_seq;
    bool exact_calendar_restore_succeeded = true;
    for (std::size_t index = snapshot.applied_action_count;
         index > 0;
         --index) {
      const auto& delta =
          snapshot.action_deltas[index - 1];
      if (delta.destination_reservation_inserted) {
        exact_calendar_restore_succeeded =
            junctions_.at(delta.next_node)
                    .service_calendar
                    .restore_exact_reservation_noexcept(
                        delta.bag_id,
                        delta.destination_start,
                        delta.destination_end,
                        delta.destination_generation_before) &&
            exact_calendar_restore_succeeded;
      }
      if (delta.corridor_reservation_inserted) {
        const auto corridor =
            corridors_.find(delta.corridor_key);
        exact_calendar_restore_succeeded =
            corridor != corridors_.end() &&
            corridor->second
                .restore_exact_reservation_noexcept(
                    delta.bag_id,
                    delta.corridor_start,
                    delta.corridor_end,
                    delta.corridor_generation_before) &&
            exact_calendar_restore_succeeded;
      }
    }
    if (snapshot.differential_rollback) {
      for (std::size_t index = snapshot.applied_action_count;
           index > 0;
           --index) {
        const auto& delta =
            snapshot.action_deltas[index - 1];
        if (!delta.destination_goal_incremented) {
          continue;
        }
        auto& by_goal =
            junctions_.at(delta.next_node)
                .scheduled_incoming_by_goal;
        if (delta.destination_goal_existed) {
          const auto current =
              by_goal.find(delta.destination_goal);
          if (current == by_goal.end()) {
            throw std::logic_error(
                "PIBT rollback lost an existing destination goal counter");
          }
          current->second = delta.destination_goal_value;
        } else {
          by_goal.erase(delta.destination_goal);
        }
      }
    }
    for (auto& entry : snapshot.corridors) {
      auto corridor = corridors_.find(entry.first);
      if (!entry.second.existed) {
        if (corridor != corridors_.end()) {
          corridors_.erase(corridor);
        }
#ifdef CZR005_EVENT_RUNTIME_TESTING
        snapshot.calendar_logical_state_restored =
            snapshot.calendar_logical_state_restored &&
            corridors_.find(entry.first) ==
                corridors_.end();
#endif
        continue;
      }
      if (corridor == corridors_.end()) {
        throw std::logic_error(
            "PIBT rollback lost an existing corridor calendar");
      }
      exact_calendar_restore_succeeded =
          exact_calendar_restore_succeeded &&
          corridor->second.generation() ==
              entry.second.generation;
#ifdef CZR005_EVENT_RUNTIME_TESTING
      snapshot.calendar_logical_state_restored =
          snapshot.calendar_logical_state_restored &&
          corridor->second.logical_state_fingerprint() ==
              entry.second.logical_state_fingerprint;
      snapshot.calendar_generation_restored =
          snapshot.calendar_generation_restored &&
          corridor->second.generation() ==
              entry.second.generation;
#endif
    }
    for (const auto& entry : snapshot.bags) {
      auto& bag = bags_.at(entry.first);
      const auto& saved = entry.second;
      bag.status = saved.status;
      bag.total_wait = saved.total_wait;
      bag.junction_queue_wait_seconds =
          saved.junction_queue_wait_seconds;
      bag.transit_from = saved.transit_from;
      bag.transit_to = saved.transit_to;
      bag.transit_merge_grant =
          saved.transit_merge_grant;
      bag.decision_count = saved.decision_count;
      bag.deadlock_started_at = saved.deadlock_started_at;
      bag.first_edge_credit_id = saved.first_edge_credit_id;
      bag.first_edge_credit_consumed =
          saved.first_edge_credit_consumed;
    }
    if (g4irsf14_state_ != nullptr) {
      for (const auto& entry :
           snapshot.destination_merge_bags) {
        const auto merge =
            g4irsf14_state_
                ->destination_merge_bags.find(
                    entry.first);
        if (merge !=
            g4irsf14_state_
                ->destination_merge_bags.end()) {
          merge->second.junction_queue_generation =
              entry.second
                  .junction_queue_generation;
        }
      }
    }
    for (auto& entry : snapshot.junctions) {
      auto& junction = junctions_.at(entry.first);
      auto& saved = entry.second;
      exact_calendar_restore_succeeded =
          exact_calendar_restore_succeeded &&
          junction.service_calendar.generation() ==
              saved.service_calendar_generation;
#ifdef CZR005_EVENT_RUNTIME_TESTING
      snapshot.calendar_generation_restored =
          snapshot.calendar_generation_restored &&
          junction.service_calendar.generation() ==
              saved.service_calendar_generation;
#endif
      if (!snapshot.differential_rollback) {
        junction.queue.swap(saved.queue);
      }
      junction.peak_source_queue_length =
          saved.peak_source_queue_length;
      junction.peak_junction_queue_length =
          saved.peak_junction_queue_length;
      junction.peak_service_calendar_intervals =
          saved.peak_service_calendar_intervals;
      junction.peak_local_state_accounted_bytes =
          saved.peak_local_state_accounted_bytes;
      junction.service_reservation_count =
          saved.service_reservation_count;
      junction.cumulative_service_reserved_seconds =
          saved.cumulative_service_reserved_seconds;
      junction.first_service_reservation_start_time =
          saved.first_service_reservation_start_time;
      junction.last_service_reservation_end_time =
          saved.last_service_reservation_end_time;
      junction.next_dispatch_time = saved.next_dispatch_time;
      junction.scheduled_incoming = saved.scheduled_incoming;
      if (!snapshot.differential_rollback) {
        junction.scheduled_incoming_by_goal.swap(
            saved.scheduled_incoming_by_goal);
      }
      junction.source_wakeup_generation =
          saved.source_wakeup_generation;
      junction.junction_wakeup_generation =
          saved.junction_wakeup_generation;
      junction.source_wakeup_pending =
          saved.source_wakeup_pending;
      junction.junction_wakeup_pending =
          saved.junction_wakeup_pending;
      junction.escape_token_task = saved.escape_token_task;
      if (g4irsf14_state_ != nullptr) {
        if (saved.g4irsf14_local_state_existed) {
          g4irsf14_state_->local[entry.first] =
              saved.g4irsf14_local_state;
        } else {
          g4irsf14_state_->local.erase(entry.first);
        }
      }
    }
    if (!exact_calendar_restore_succeeded) {
      throw std::logic_error(
          "PIBT rollback failed exact calendar generation restore");
    }
    snapshot.applied_action_count = 0;
    snapshot.mutated = false;
  }

#ifdef CZR005_EVENT_RUNTIME_TESTING
  bool pibt_logical_state_matches_snapshot(
      const PIBTTransactionSnapshot& snapshot) const {
    if (!snapshot.calendar_logical_state_restored ||
        !snapshot.calendar_generation_restored) {
      return false;
    }
    if (staged_event_sink_ != nullptr ||
        staged_merge_visibility_sink_ != nullptr ||
        staged_destination_known_competitor_counts_ !=
            nullptr ||
        !snapshot.staged_events.empty() ||
        !snapshot.staged_merge_visibility.empty() ||
        !snapshot
             .staged_destination_known_competitor_counts
             .empty() ||
        events_.size() != snapshot.event_queue_size ||
        test_event_queue_logical_fingerprint() !=
            snapshot.event_queue_logical_fingerprint ||
        next_event_seq_ != snapshot.next_event_seq) {
      return false;
    }
    if (result_.merge_request_visibility.size() !=
            snapshot.merge_visibility_size ||
        result_.event_seq_ordering_audit.size() !=
            snapshot.event_seq_audit_size) {
      return false;
    }
    const auto& current_credit =
        credit_ledger_.counters();
    if (!test_credit_counters_equal(
            current_credit,
            snapshot.credit_counters) ||
        credit_ledger_.stored_active_count() !=
            snapshot.credit_active_count ||
        credit_ledger_.stored_lifecycle_count() !=
            snapshot.credit_lifecycle_count) {
      return false;
    }
    if (!test_transaction_summary_equal(
            result_.summary,
            snapshot.summary)) {
      return false;
    }
    if (destination_merge_controllers_.size() !=
            snapshot
                .destination_merge_controller_fingerprints
                .size() ||
        test_pending_merge_dispatches_logical_fingerprint() !=
            snapshot
                .pending_merge_dispatches_logical_fingerprint) {
      return false;
    }
    for (const auto& expected :
         snapshot
             .destination_merge_controller_fingerprints) {
      const auto controller =
          destination_merge_controllers_.find(
              expected.first);
      if (controller ==
              destination_merge_controllers_.end() ||
          test_destination_merge_controller_fingerprint(
              controller->second) != expected.second) {
        return false;
      }
    }
    for (const auto& entry : snapshot.bags) {
      const auto bag = bags_.find(entry.first);
      if (bag == bags_.end()) {
        return false;
      }
      const auto& current = bag->second;
      const auto& saved = entry.second;
      if (current.status != saved.status ||
          current.total_wait != saved.total_wait ||
          current.junction_queue_wait_seconds !=
              saved.junction_queue_wait_seconds ||
          current.transit_from != saved.transit_from ||
          current.transit_to != saved.transit_to ||
          current.transit_merge_grant !=
              saved.transit_merge_grant ||
          current.decision_count != saved.decision_count ||
          current.deadlock_started_at !=
              saved.deadlock_started_at ||
          current.first_edge_credit_id !=
              saved.first_edge_credit_id ||
          current.first_edge_credit_consumed !=
              saved.first_edge_credit_consumed) {
        return false;
      }
    }
    if (g4irsf14_state_ != nullptr) {
      for (const auto& entry :
           snapshot.destination_merge_bags) {
        const auto merge =
            g4irsf14_state_
                ->destination_merge_bags.find(
                    entry.first);
        if (merge ==
                g4irsf14_state_
                    ->destination_merge_bags.end() ||
            merge->second.junction_queue_generation !=
                entry.second
                    .junction_queue_generation ||
            merge->second.request_generation !=
                entry.second.request_generation ||
            merge->second.pending_request_id !=
                entry.second.pending_request_id ||
            merge->second.pending_lineage !=
                entry.second.pending_lineage ||
            merge->second.pending_request_time !=
                entry.second.pending_request_time ||
            merge->second.first_contention_time !=
                entry.second.first_contention_time ||
            merge->second.grant_wait_seconds !=
                entry.second.grant_wait_seconds ||
            merge->second.exact_grant_edge_entry_observed !=
                entry.second.exact_grant_edge_entry_observed ||
            merge->second.capability.has_value() !=
                entry.second.capability_present ||
            (entry.second.capability_present &&
             merge->second.capability
                     ->expectation() !=
                 entry.second
                     .capability_identity)) {
          return false;
        }
      }
    }
    for (const auto& entry : snapshot.junctions) {
      const auto junction =
          junctions_.find(entry.first);
      if (junction == junctions_.end() ||
          test_junction_logical_fingerprint(
              junction->second) !=
              entry.second.logical_state_fingerprint) {
        return false;
      }
    }
    if (g4irsf14_state_ == nullptr) {
      return true;
    }
    const auto same =
        [](const event_runtime_detail::LocalArbitrationState& left,
           const event_runtime_detail::LocalArbitrationState& right) {
          return left.source_wakeup_time == right.source_wakeup_time &&
                 left.junction_wakeup_time ==
                     right.junction_wakeup_time &&
                 left.has_last_source_arbitration ==
                     right.has_last_source_arbitration &&
                 left.has_last_junction_arbitration ==
                     right.has_last_junction_arbitration &&
                 left.last_source_arbitration_time ==
                     right.last_source_arbitration_time &&
                 left.last_junction_arbitration_time ==
                     right.last_junction_arbitration_time &&
                 left.last_source_arbitration_generation ==
                     right.last_source_arbitration_generation &&
                 left.last_junction_arbitration_generation ==
                     right.last_junction_arbitration_generation &&
                 left.source_batch_open ==
                     right.source_batch_open &&
                 left.junction_batch_open ==
                     right.junction_batch_open &&
                 left.source_batch_time ==
                     right.source_batch_time &&
                 left.junction_batch_time ==
                     right.junction_batch_time &&
                 left.source_queue_before_enqueue ==
                     right.source_queue_before_enqueue &&
                 left.source_queue_after_enqueue ==
                     right.source_queue_after_enqueue &&
                 left.junction_queue_before_enqueue ==
                     right.junction_queue_before_enqueue &&
                 left.junction_queue_after_enqueue ==
                     right.junction_queue_after_enqueue &&
                 left.source_enqueue_count ==
                     right.source_enqueue_count &&
                 left.junction_enqueue_count ==
                     right.junction_enqueue_count;
        };
    for (const auto& entry : snapshot.junctions) {
      const auto local =
          g4irsf14_state_->local.find(entry.first);
      if (entry.second.g4irsf14_local_state_existed) {
        if (local == g4irsf14_state_->local.end() ||
            !same(local->second,
                  entry.second.g4irsf14_local_state)) {
          return false;
        }
      } else if (local != g4irsf14_state_->local.end()) {
        return false;
      }
    }
    return true;
  }
#endif

  bool commit_pibt_batch(
      const std::vector<BoundedLocalPIBTAction>& actions,
      double time,
      PIBTTransactionSnapshot& snapshot,
      std::string& blocker,
      const MergeGrantCapability*
          merge_grant_authority = nullptr,
      int merge_grant_trigger_bag_id = -1) {
    if (!prevalidate_pibt_batch(
            actions,
            time,
            blocker,
            merge_grant_authority,
            merge_grant_trigger_bag_id)) {
      return false;
    }
    const bool first_edge_credit_mode =
        uses_first_edge_credit();
    std::vector<FirstEdgeCreditBatchEntry> credit_entries;
    if (!build_pibt_credit_batch(
            actions, time, credit_entries, blocker)) {
      return false;
    }
    snapshot.credit_entry_count =
        static_cast<int>(credit_entries.size());
    result_.summary
        .bounded_local_pibt_max_transaction_credit_entries =
        std::max(
            result_.summary
                .bounded_local_pibt_max_transaction_credit_entries,
            snapshot.credit_entry_count);
    // Each selected action stages exactly three edge/reservation events, one
    // local-queue update, and at most one follow-up wakeup.  Reserve both
    // containers before the first logical mutation so the final heap publish
    // cannot allocate after the credit batch has committed.
    const std::size_t max_staged_events =
        actions.size() * 5;
    snapshot.staged_events.reserve(max_staged_events);
    snapshot.staged_merge_visibility.reserve(
        actions.size());
    events_.reserve(events_.size() +
                    max_staged_events);
    result_.decisions.reserve(
        result_.decisions.size() + actions.size());
    if (config_.enable_opportunity_telemetry) {
      result_.merge_request_visibility.reserve(
          result_.merge_request_visibility.size() +
          actions.size());
      result_.event_seq_ordering_audit.reserve(
          result_.event_seq_ordering_audit.size() +
          actions.size());
    }
    std::vector<int> action_source_nodes;
    action_source_nodes.reserve(actions.size());
    for (const auto& action : actions) {
      action_source_nodes.push_back(action.from_node);
    }
    std::sort(action_source_nodes.begin(),
              action_source_nodes.end());
    action_source_nodes.erase(
        std::unique(action_source_nodes.begin(),
                    action_source_nodes.end()),
        action_source_nodes.end());
    std::set<long long> maintained_corridors;
    std::set<int> maintained_destination_calendars;
    for (const auto& action : actions) {
      if (uses_corridor_calendar()) {
        const auto key = resource_corridor_key(
            action.from_node, action.next_node);
        if (maintained_corridors.insert(key).second) {
          const auto corridor = corridors_.find(key);
          if (corridor != corridors_.end()) {
            corridor->second.purge(time);
          }
        }
      }
      const auto& bag = bags_.at(action.bag_id);
      if (uses_destination_calendar(
              action.next_node,
              bag.request.goal) &&
          maintained_destination_calendars
              .insert(action.next_node)
              .second) {
        junctions_.at(action.next_node)
            .service_calendar.purge(time);
      }
    }
    capture_pibt_transaction(actions, time, snapshot);
    for (const auto& action : actions) {
      ++snapshot
            .staged_destination_known_competitor_counts[
                action.next_node];
    }
    for (auto& entry :
         snapshot
             .staged_destination_known_competitor_counts) {
      const auto destination =
          junctions_.find(entry.first);
      const int baseline =
          destination == junctions_.end()
              ? 0
              : destination->second.scheduled_incoming +
                    static_cast<int>(
                        destination->second.queue.size());
      entry.second = baseline +
                     std::max(0, entry.second - 1);
    }
    snapshot.mutated = true;
    staged_event_sink_ = &snapshot.staged_events;
    staged_merge_visibility_sink_ =
        &snapshot.staged_merge_visibility;
    staged_destination_known_competitor_counts_ =
        &snapshot
             .staged_destination_known_competitor_counts;
    try {
      // An atomic PIBT batch can dequeue an owner at a different junction
      // from the arbitration that triggered it.  Invalidate that junction's
      // already-published wakeup before mutating its queue; any remaining
      // queue is rescheduled below with a fresh generation.
      if (batches_junction_same_timestamp()) {
        for (const int source_node : action_source_nodes) {
          auto& controller = junctions_.at(source_node);
          if (!controller.junction_wakeup_pending) {
            continue;
          }
          controller.junction_wakeup_pending = false;
          ++controller.junction_wakeup_generation;
          if (g4irsf14_state_ != nullptr) {
            g4irsf14_local_state(source_node)
                .junction_wakeup_time =
                std::numeric_limits<double>::infinity();
          }
        }
      }
      for (const auto& action : actions) {
        auto& bag = bags_.at(action.bag_id);
        auto& controller = junctions_.at(action.from_node);
        auto& transaction_delta =
            snapshot.action_deltas[
                snapshot.applied_action_count];
        // Arm the current differential rollback entry before the first
        // mutation.  dispatch_selected_edge may have inserted one calendar
        // interval or staged one event before an exception is raised.
        ++snapshot.applied_action_count;
        try {
          dispatch_selected_edge(
              bag,
              action.from_node,
              action.next_node,
              time,
              &transaction_delta,
              merge_grant_authority != nullptr &&
                  action.bag_id ==
                      merge_grant_trigger_bag_id
                  ? merge_grant_authority
                  : nullptr);
        } catch (const std::logic_error& error) {
          // dispatch_selected_edge uses an exact std::logic_error for a
          // revalidated local reservation race. Derived logic errors such as
          // out_of_range are programming/state-corruption failures and must
          // propagate after rollback.
          if (typeid(error) != typeid(std::logic_error)) {
            throw;
          }
          blocker = "local_reservation_state_changed";
          throw PIBTLogicalCommitFailure(blocker);
        }
        const auto queued =
            snapshot.differential_rollback
                ? (transaction_delta.queue_index <
                           controller.queue.size() &&
                       controller.queue[
                           transaction_delta.queue_index] ==
                           action.bag_id
                       ? std::next(
                             controller.queue.begin(),
                             static_cast<std::ptrdiff_t>(
                                 transaction_delta.queue_index))
                       : controller.queue.end())
                : std::find(controller.queue.begin(),
                            controller.queue.end(),
                            action.bag_id);
        if (queued == controller.queue.end()) {
          blocker = "ready_owner_disappeared_during_commit";
          throw PIBTLogicalCommitFailure(blocker);
        }
        if (!snapshot.differential_rollback) {
          controller.queue.erase(queued);
          controller.observe_local_state();
        }
        if (uses_destination_merge_grants() &&
            g4irsf14_state_ != nullptr) {
          ++destination_merge_bag_state(
                action.bag_id)
                .junction_queue_generation;
        }
        schedule_passive(JunctionEventType::kLocalQueueUpdate,
                         time,
                         action.bag_id,
                         action.from_node,
                         action.from_node,
                         action.next_node,
                         "bounded_local_pibt_atomic_dequeue");
        controller.next_dispatch_time =
            time + config_.dispatch_headway_seconds;
        ++bag.decision_count;
        ++result_.summary.decision_count;
        if (bag.deadlock_started_at >= 0.0) {
          ++result_.summary.resolved_deadlock_count;
          result_.summary.max_deadlock_duration =
              std::max(result_.summary.max_deadlock_duration,
                       time - bag.deadlock_started_at);
          bag.deadlock_started_at = -1.0;
        }
        if (controller.escape_token_task == action.bag_id) {
          controller.escape_token_task = -1;
        }
#ifdef CZR005_EVENT_RUNTIME_TESTING
        if (config_
                .test_pibt_logical_failure_after_staged_actions > 0 &&
            !test_pibt_logical_failure_injected_ &&
            snapshot.applied_action_count ==
                static_cast<std::size_t>(
                    config_
                        .test_pibt_logical_failure_after_staged_actions)) {
          test_pibt_logical_failure_injected_ = true;
          blocker = "test_injected_post_stage_logical_failure";
          throw PIBTLogicalCommitFailure(blocker);
        }
#endif
      }

      for (const auto& action : actions) {
        auto& controller = junctions_.at(action.from_node);
        const bool queue_remains_after_commit =
            snapshot.differential_rollback
                ? controller.queue.size() > 1
                : !controller.queue.empty();
        if (queue_remains_after_commit &&
            !controller.junction_wakeup_pending) {
          schedule_junction_wakeup(
              action.from_node, controller.next_dispatch_time);
        }
      }
      for (auto& staged_event :
           snapshot.staged_events) {
        prepare_event_for_publication(staged_event);
      }
#ifdef CZR005_EVENT_RUNTIME_TESTING
      if (config_
              .test_pibt_logical_failure_after_followup_scheduling &&
          !test_pibt_logical_failure_injected_) {
        test_pibt_logical_failure_injected_ = true;
        blocker =
            "test_injected_post_followup_logical_failure";
        throw PIBTLogicalCommitFailure(blocker);
      }
#endif
      if (!credit_entries.empty()) {
        const auto closed =
            credit_ledger_.bind_and_consume_bounded_batch(
                credit_entries,
                static_cast<std::size_t>(
                    config_.pibt_max_ready_bags));
        if (!closed.accepted) {
          blocker = "first_edge_credit_batch_" + closed.reason;
          throw PIBTLogicalCommitFailure(blocker);
        }
        for (const auto& action : actions) {
          auto& bag = bags_.at(action.bag_id);
          if (!bag.first_edge_credit_consumed &&
              bag.first_edge_credit_id != 0) {
            bag.first_edge_credit_id = 0;
            bag.first_edge_credit_consumed = true;
          }
        }
      }
      if (first_edge_credit_mode) {
        for (const auto& action : actions) {
          auto& bag = bags_.at(action.bag_id);
          if (!bag.first_edge_credit_consumed) {
            bag.first_edge_credit_id = 0;
            bag.first_edge_credit_consumed = true;
          }
        }
      }
      if (snapshot.differential_rollback) {
        // The exact owner/index pair was revalidated above, and prevalidation
        // guarantees at most one action per source queue.  Credit is now
        // irrevocably committed, so this is the allocation-free tail: erase
        // each int owner and perform only noexcept observation afterwards.
        for (std::size_t index = 0;
             index < snapshot.action_deltas.size();
             ++index) {
          auto& delta = snapshot.action_deltas[index];
          delta.source_junction->queue.erase(
              delta.source_queue_iterator);
          delta.source_junction->observe_local_state();
        }
      }
    } catch (const PIBTLogicalCommitFailure&) {
      staged_event_sink_ = nullptr;
      staged_merge_visibility_sink_ = nullptr;
      staged_destination_known_competitor_counts_ =
          nullptr;
      restore_pibt_transaction(snapshot);
#ifdef CZR005_EVENT_RUNTIME_TESTING
      if (config_
              .test_verify_pibt_rollback_logical_state &&
          !pibt_logical_state_matches_snapshot(snapshot)) {
        throw std::logic_error(
            "PIBT rollback did not restore complete logical state");
      }
#endif
      if (blocker.empty()) {
        blocker = "logical_atomic_commit_state_mutation_failed";
      }
      return false;
    } catch (...) {
      staged_event_sink_ = nullptr;
      staged_merge_visibility_sink_ = nullptr;
      staged_destination_known_competitor_counts_ =
          nullptr;
      restore_pibt_transaction(snapshot);
      throw;
    }
    staged_event_sink_ = nullptr;
    staged_merge_visibility_sink_ = nullptr;
    staged_destination_known_competitor_counts_ =
        nullptr;
    // Keep the transaction rollbackable after the resolver callback returns.
    // The caller still has to materialize audit/decision rows and may fail.
    // Publication and the final no-throw commit point therefore live in
    // try_dispatch_bounded_local_pibt().
    return true;
  }

  DispatchResult try_dispatch_bounded_local_pibt(
      int node,
      double time,
      std::uint64_t arrive_event_seq,
      int* priority_comparison_count,
      const MergeGrantCapability*
          merge_grant_authority = nullptr) {
    auto& controller = junctions_[node];
    if (controller.queue.empty() ||
        time + event_runtime_detail::kEpsilon <
            controller.next_dispatch_time) {
      return {};
    }
    std::size_t root_index = 0;
    if (merge_grant_authority != nullptr) {
      const auto root = std::find(
          controller.queue.begin(),
          controller.queue.end(),
          merge_grant_authority
              ->owner_runtime_bag_id());
      if (root == controller.queue.end()) {
        return {};
      }
      root_index = static_cast<std::size_t>(
          std::distance(controller.queue.begin(), root));
    } else {
      root_index =
          choose_bag(controller.queue,
                     time,
                     controller.escape_token_task,
                     priority_comparison_count);
    }
    const int trigger_runtime_bag_id = controller.queue[root_index];
    const auto decision_started = std::chrono::steady_clock::now();
    PIBTLocalSlice slice = build_pibt_local_slice(
        node,
        trigger_runtime_bag_id,
        time,
        arrive_event_seq,
        priority_comparison_count,
        merge_grant_authority);
    if (g4irsf14_state_ != nullptr) {
      g4irsf14_state_->current_pibt_slice_bag_count =
          static_cast<int>(slice.ready_bags.size());
      g4irsf14_state_->current_pibt_owner_count =
          static_cast<int>(slice.owners.size());
    }
    if (!slice.applicable) {
      ++result_.summary.bounded_local_pibt_not_applicable_count;
      return {};
    }
    if (merge_grant_authority != nullptr) {
      ++result_.summary
            .g4irsf14_i5_applicable_ready_slice_boundary_count;
    }
    if (active_causal_step_ != nullptr &&
        merge_grant_authority != nullptr) {
      G4IRSF14CloneBoundary boundary;
      boundary.kind =
          G4IRSF14CloneBoundaryKind::kPIBTReadySlice;
      boundary.node =
          active_causal_step_->prepop_event.node;
      boundary.runtime_bag_id =
          trigger_runtime_bag_id;
      boundary.baseline_pibt_enabled = true;
      boundary.pibt_owner_runtime_bag_id =
          trigger_runtime_bag_id;
      boundary.pibt_candidate_required_resource_offsets
          .push_back(0U);
      for (const auto& ready : slice.ready_bags) {
        boundary.pibt_ready_bag_ids.push_back(
            ready.bag_id);
        boundary.pibt_ready_current_nodes.push_back(
            ready.current_node);
        for (const auto& candidate : ready.candidates) {
          boundary.pibt_candidate_bag_ids.push_back(
              ready.bag_id);
          boundary.pibt_candidate_next_nodes.push_back(
              candidate.next_node);
          boundary.pibt_candidate_edge_resources.push_back(
              candidate.edge_resource);
          boundary
              .pibt_candidate_expected_fault_generations
              .push_back(
                  candidate.expected_fault_generation);
          boundary.pibt_candidate_required_resources.insert(
              boundary.pibt_candidate_required_resources.end(),
              candidate.required_resources.begin(),
              candidate.required_resources.end());
          boundary
              .pibt_candidate_required_resource_offsets
              .push_back(static_cast<std::uint64_t>(
                  boundary
                      .pibt_candidate_required_resources
                      .size()));
        }
      }
      for (const auto& owner : slice.owners) {
        boundary.pibt_owner_resources.push_back(
            owner.resource);
        boundary.pibt_owner_bag_ids.push_back(
            owner.bag_id);
      }
      const std::vector<int> affected_slice_bags =
          boundary.pibt_ready_bag_ids;
      if (const auto* intervention =
              observe_causal_boundary(std::move(boundary));
          intervention != nullptr) {
        if (intervention->kind !=
                G4IRSF14CloneInterventionKind::kPIBTTrigger ||
            intervention->runtime_bag_id !=
                trigger_runtime_bag_id ||
            intervention->selected_boolean) {
          throw std::logic_error(
              "I5 directive must disable P2 for the exact "
              "applicable recursive ready slice");
        }
        mark_causal_action_applied(
            "APPLIED_I5_DISABLE_P2_FOR_ONE_EXACT_READY_SLICE",
            affected_slice_bags);
        return {};
      }
    }
    if (config_.trace_limit != 0 &&
        (config_.trace_limit < 0 ||
         static_cast<int>(result_.pibt_events.size()) <
             config_.trace_limit)) {
      result_.pibt_events.reserve(
          result_.pibt_events.size() + 1);
    }
    decision_latencies_us_.reserve(
        decision_latencies_us_.size() + 1);
    ++result_.summary.bounded_local_pibt_activation_count;
    result_.summary.bounded_local_pibt_max_slice_bags =
        std::max(result_.summary.bounded_local_pibt_max_slice_bags,
                 static_cast<int>(slice.ready_bags.size()));
    result_.summary.bounded_local_pibt_max_slice_resources =
        std::max(result_.summary.bounded_local_pibt_max_slice_resources,
                 slice.resource_count);
    std::map<LocalPIBTResourceKey, int>
        real_blocker_owner_by_resource;
    for (const auto& owner : slice.owners) {
      if (owner.bag_id != trigger_runtime_bag_id) {
        real_blocker_owner_by_resource[owner.resource] =
            owner.bag_id;
      }
    }
    for (const auto& ready : slice.ready_bags) {
      result_.summary.bounded_local_pibt_max_candidates_per_bag =
          std::max(
              result_.summary
                  .bounded_local_pibt_max_candidates_per_bag,
              static_cast<int>(ready.candidates.size()));
    }

    PIBTTransactionSnapshot transaction;
    std::string callback_blocker;
    BoundedLocalPIBTCallbacks callbacks;
    const auto required_trigger_blocker_bag_ids =
        [&](const std::vector<BoundedLocalPIBTAction>& actions) {
          std::set<int> required;
          const auto trigger_action = std::find_if(
              actions.begin(),
              actions.end(),
              [&](const BoundedLocalPIBTAction& action) {
                return action.bag_id == trigger_runtime_bag_id;
              });
          if (trigger_action == actions.end()) {
            return required;
          }
          for (const auto resource :
               trigger_action->claimed_resources) {
            const auto owner =
                real_blocker_owner_by_resource.find(resource);
            if (owner != real_blocker_owner_by_resource.end()) {
              required.insert(owner->second);
            }
          }
          return required;
        };
    callbacks.read_fault =
        [&](LocalPIBTResourceKey edge_resource) {
          const auto edge = slice.edge_by_resource.find(edge_resource);
          if (edge == slice.edge_by_resource.end()) {
            return LocalPIBTFaultSnapshot{
                std::numeric_limits<std::uint64_t>::max(), true};
          }
          const long long key = event_runtime_detail::directed_key(
              edge->second.first, edge->second.second);
          const auto fault = physical_faults_.find(key);
          return LocalPIBTFaultSnapshot{
              fault == physical_faults_.end()
                  ? 0
                  : static_cast<std::uint64_t>(
                        fault->second.physical_generation),
              fault != physical_faults_.end() &&
                  fault->second.active_count > 0};
        };
    callbacks.prepare =
        [&](const std::vector<BoundedLocalPIBTAction>& actions) {
          const auto trigger_action = std::find_if(
              actions.begin(),
              actions.end(),
              [&](const BoundedLocalPIBTAction& action) {
                return action.bag_id == trigger_runtime_bag_id;
              });
          const auto required_blocker_bag_ids =
              required_trigger_blocker_bag_ids(actions);
          const bool includes_real_blocker_move =
              !required_blocker_bag_ids.empty() &&
              std::all_of(
                  required_blocker_bag_ids.begin(),
                  required_blocker_bag_ids.end(),
                  [&](int blocker_bag_id) {
                    return std::any_of(
                        actions.begin(),
                        actions.end(),
                        [&](const BoundedLocalPIBTAction& action) {
                          return action.bag_id == blocker_bag_id;
                        });
                  });
          const bool includes_trigger =
              trigger_action != actions.end();
          if (!includes_trigger || !includes_real_blocker_move) {
            callback_blocker =
                "proposal_lacks_trigger_or_real_blocker_owner_move";
            return false;
          }
          return prevalidate_pibt_batch(
              actions,
              time,
              callback_blocker,
              merge_grant_authority,
              trigger_runtime_bag_id);
        };
    callbacks.commit =
        [&](const std::vector<BoundedLocalPIBTAction>& actions) {
          return commit_pibt_batch(
              actions,
              time,
              transaction,
              callback_blocker,
              merge_grant_authority,
              trigger_runtime_bag_id);
        };
    callbacks.rollback =
        [&](const std::vector<BoundedLocalPIBTAction>&) {
          restore_pibt_transaction(transaction);
        };
    const auto rollback_post_commit_transaction =
        [&]() {
          const bool was_mutated = transaction.mutated;
          restore_pibt_transaction(transaction);
#ifdef CZR005_EVENT_RUNTIME_TESTING
          if (was_mutated &&
              config_.test_verify_pibt_rollback_logical_state) {
            if (!pibt_logical_state_matches_snapshot(
                    transaction)) {
              throw std::logic_error(
                  "PIBT post-commit rollback did not restore "
                  "the exact logical fingerprint");
            }
            ++result_.summary
                  .bounded_local_pibt_rollback_fingerprint_match_count;
            if (!transaction.calendar_generation_restored) {
              throw std::logic_error(
                  "PIBT post-commit rollback did not restore "
                  "the exact calendar generations");
            }
            ++result_.summary
                  .bounded_local_pibt_rollback_calendar_generation_match_count;
          }
#else
          (void)was_mutated;
#endif
        };

    BoundedLocalPIBTConfig resolver_config;
    resolver_config.mode = canonical_pibt_mode();
    resolver_config.decision_time = time;
    resolver_config.max_ready_bags = config_.pibt_max_ready_bags;
    resolver_config.max_local_resources =
        config_.pibt_max_local_resources;
    resolver_config.max_candidates_per_bag =
        config_.pibt_max_candidates_per_bag;
    resolver_config.priority_mode =
        canonical_priority_mode();
    resolver_config.preference_mode =
        canonical_pibt_preference_mode();
    BoundedLocalPIBTResult resolved;
    try {
      resolved = BoundedLocalPIBTResolver().resolve(
          std::move(slice.ready_bags),
          std::move(slice.owners),
          resolver_config,
          callbacks);
    } catch (const std::invalid_argument& error) {
      rollback_post_commit_transaction();
      ++result_.summary.bounded_local_pibt_not_applicable_count;
      callback_blocker =
          std::string("resolver_slice_validation_failed:") + error.what();
      return {};
    } catch (...) {
      rollback_post_commit_transaction();
      throw;
    }

    if (!resolved.actions.empty()) {
      ++result_.summary.bounded_local_pibt_proposal_batch_count;
      result_.summary.bounded_local_pibt_proposed_action_count +=
          resolved.actions.size();
    }
    result_.summary.bounded_local_pibt_inherited_action_count +=
        resolved.inherited_action_count;
    result_.summary.bounded_local_pibt_attempt_count +=
        resolved.candidate_attempt_count;
    result_.summary.bounded_local_pibt_prepare_count +=
        resolved.prepare_call_count;
    result_.summary.bounded_local_pibt_validate_count +=
        resolved.proposal_validation_count +
        resolved.fault_revalidation_count;
    result_.summary.bounded_local_pibt_commit_count +=
        resolved.commit_call_count;
    result_.summary.bounded_local_pibt_wait_for_cycle_count +=
        resolved.visiting_cycle_guard_count;
    result_.summary.bounded_local_pibt_blocker_move_attempt_count +=
        resolved.blocker_move_attempt_count;
    result_.summary.bounded_local_pibt_backtrack_count +=
        resolved.backtrack_count;
    result_.summary.bounded_local_pibt_cycle_guard_count +=
        resolved.visiting_cycle_guard_count;
    result_.summary.bounded_local_pibt_rollback_count +=
        resolved.rollback_call_count;
    result_.summary.bounded_local_pibt_max_inheritance_depth =
        std::max(
            result_.summary.bounded_local_pibt_max_inheritance_depth,
            resolved.max_inheritance_depth_observed);
    if (resolved.outcome ==
        BoundedLocalPIBTOutcome::kFaultGenerationChanged) {
      ++result_.summary.bounded_local_pibt_fault_rejection_count;
    } else if (resolved.outcome ==
               BoundedLocalPIBTOutcome::kPrepareRejected) {
      ++result_.summary.bounded_local_pibt_prepare_rejection_count;
    } else if (resolved.outcome ==
               BoundedLocalPIBTOutcome::kCommitRejected) {
      ++result_.summary.bounded_local_pibt_commit_rejection_count;
    }

    try {
      EventRuntimePIBTAuditRow audit;
      audit.activation_id = next_pibt_activation_id_;
      audit.time = time;
      audit.trigger_node = node;
      audit.trigger_runtime_bag_id = trigger_runtime_bag_id;
      audit.mode = canonical_pibt_mode_name();
      audit.outcome =
          bounded_local_pibt_outcome_name(resolved.outcome);
      audit.blocker = callback_blocker.empty()
                          ? resolved.blocker
                          : callback_blocker;
      audit.local_slice_bag_count =
          static_cast<int>(slice.traces_by_bag.size());
      audit.local_slice_resource_count = slice.resource_count;
      audit.local_slice_candidate_count = slice.candidate_count;
      audit.proposed_action_count =
          static_cast<int>(resolved.actions.size());
      audit.committed_action_count =
          resolved.committed
              ? static_cast<int>(resolved.actions.size())
              : 0;
      audit.inherited_action_count =
          resolved.inherited_action_count;
      audit.max_inheritance_depth =
          resolved.max_inheritance_depth_observed;
      audit.backtrack_count = resolved.backtrack_count;
      audit.cycle_guard_count =
          resolved.visiting_cycle_guard_count;
      audit.rollback_count = resolved.rollback_call_count;
      audit.transaction_credit_entry_count =
          transaction.credit_entry_count;
      audit.transaction_bag_entry_count =
          static_cast<int>(transaction.bags.size());
      audit.transaction_junction_scalar_entry_count =
          static_cast<int>(transaction.junctions.size());
      audit.transaction_action_delta_count =
          static_cast<int>(transaction.action_deltas.size());
      audit.actions = resolved.actions;
      const bool publish_audit =
          config_.trace_limit != 0 &&
          (config_.trace_limit < 0 ||
           static_cast<int>(result_.pibt_events.size()) <
               config_.trace_limit);

      if (!resolved.committed) {
        ++result_.summary
              .bounded_local_pibt_not_applicable_count;
        int same_bag_fallback_next = -1;
        if (resolved.outcome ==
                BoundedLocalPIBTOutcome::kPrepareRejected &&
            callback_blocker ==
                "proposal_lacks_trigger_or_real_blocker_owner_move" &&
            resolved.inherited_action_count == 0 &&
            resolved.actions.size() == 1) {
          const auto& action = resolved.actions.front();
          if (action.bag_id == trigger_runtime_bag_id &&
              action.from_node == node &&
              !action.inherited &&
              graph_.has_edge(action.from_node,
                              action.next_node)) {
            // This root-only proposal is not a true PIBT commit because no
            // blocker moved. Keep its adjacent edge only as an ordinary
            // one-bag fallback candidate.
            same_bag_fallback_next = action.next_node;
          }
        }
        if (publish_audit) {
          ++next_pibt_activation_id_;
          result_.pibt_events.push_back(std::move(audit));
        }
        record_decision_latency(decision_started);
        return DispatchResult{
            trigger_runtime_bag_id,
            -1,
            0,
            false,
            same_bag_fallback_next};
      }

      const auto selected_trigger_blocker_bag_ids =
          required_trigger_blocker_bag_ids(
              resolved.actions);
      std::vector<
          std::pair<EventDecisionTraceRow, bool>>
          prepared_traces;
      prepared_traces.reserve(resolved.actions.size());
      int trigger_next = -1;
      for (const auto& action : resolved.actions) {
        auto trace =
            slice.traces_by_bag.at(action.bag_id);
        trace.selected_next = action.next_node;
        trace.fallback_selected_next =
            action.inherited ? action.next_node : -1;
        trace.decision_source =
            action.bag_id == trigger_runtime_bag_id
                ? "bounded_local_pibt_trigger_action"
            : action.inherited
                ? "bounded_local_pibt_inherited_action"
            : selected_trigger_blocker_bag_ids.find(
                      action.bag_id) !=
                      selected_trigger_blocker_bag_ids.end()
                ? "bounded_local_pibt_blocker_owner_action"
                : "bounded_local_pibt_independent_ready_action";
        trace.rule_reason =
            (trace.scorer_risk_abstain
                 ? "frozen_scorer_risk_abstain_exact_s0_fallback;"
                 : "") +
            std::string(
                "bounded_local_pibt_logical_failure_atomic_one_edge_batch");
        const bool publish_trace =
            merge_grant_authority == nullptr ||
            action.bag_id != trigger_runtime_bag_id;
        prepared_traces.emplace_back(
            std::move(trace), publish_trace);
        if (action.bag_id ==
            trigger_runtime_bag_id) {
          trigger_next = action.next_node;
        }
      }

      if (merge_grant_authority != nullptr) {
        const auto expected =
            merge_grant_authority->expectation();
        const auto trigger_action = std::find_if(
            resolved.actions.begin(),
            resolved.actions.end(),
            [&](const BoundedLocalPIBTAction& action) {
              return action.bag_id ==
                  trigger_runtime_bag_id;
            });
        const auto trigger_bag =
            bags_.find(trigger_runtime_bag_id);
        if (trigger_action == resolved.actions.end() ||
            trigger_bag == bags_.end() ||
            expected.owner_runtime_bag_id !=
                trigger_runtime_bag_id ||
            expected.edge.from_node != node ||
            expected.edge.to_node != trigger_next ||
            expected.destination_node != trigger_next ||
            trigger_action->from_node !=
                expected.edge.from_node ||
            trigger_action->next_node !=
                expected.edge.to_node ||
            trigger_bag->second.status !=
                BagStatus::kInTransit ||
            trigger_bag->second.transit_from !=
                expected.edge.from_node ||
            trigger_bag->second.transit_to !=
                expected.edge.to_node ||
            trigger_bag->second.transit_merge_grant !=
                expected) {
          throw std::logic_error(
              "post-grant PIBT committed without the exact "
              "authorized trigger action");
        }
      }

#ifdef CZR005_EVENT_RUNTIME_TESTING
      if (config_
              .test_pibt_fail_after_commit_before_publication &&
          !test_pibt_post_commit_failure_injected_) {
        test_pibt_post_commit_failure_injected_ = true;
        throw PIBTPostCommitFailureInjection{};
      }
#endif

      ++result_.summary
            .bounded_local_pibt_committed_batch_count;
      result_.summary.bounded_local_pibt_handoff_count +=
          resolved.inherited_action_count;
      result_.summary
          .bounded_local_pibt_committed_action_count +=
          resolved.actions.size();
      result_.summary
          .max_edges_selected_per_bag_per_decision =
          std::max(
              result_.summary
                  .max_edges_selected_per_bag_per_decision,
              resolved.actions.empty() ? 0 : 1);
      result_.summary
          .max_actions_committed_per_pibt_batch =
          std::max(
              result_.summary
                  .max_actions_committed_per_pibt_batch,
              static_cast<int>(resolved.actions.size()));
      record_decision_latency(decision_started);

      // Point of no return for the complete PIBT transaction. Everything
      // below is capacity-backed noexcept publication or best-effort
      // telemetry that cannot escape.
      transaction.applied_action_count = 0;
      transaction.mutated = false;
      [&]() noexcept {
        for (auto& event : transaction.staged_events) {
          publish_prepared_reserved_event(
              std::move(event));
        }
        transaction.staged_events.clear();
        for (auto& visibility :
             transaction.staged_merge_visibility) {
          publish_prepared_merge_visibility_noexcept(
              std::move(visibility));
        }
        transaction.staged_merge_visibility.clear();
        for (std::size_t index = 0;
             index < resolved.actions.size();
             ++index) {
          auto& prepared = prepared_traces[index];
          const auto bag =
              bags_.find(resolved.actions[index].bag_id);
          try {
            if (bag != bags_.end()) {
              record_committed_pibt_fault_accounting(
                  prepared.first,
                  bag->second,
                  resolved.actions[index].next_node);
            }
          } catch (...) {
            // Fault accounting is telemetry only. Logical action
            // publication remains non-throwing after commit.
          }
          if (prepared.second) {
            publish_prepared_decision_trace_noexcept(
                std::move(prepared.first), true);
          }
        }
        if (publish_audit) {
          ++next_pibt_activation_id_;
          result_.pibt_events.push_back(std::move(audit));
        }
        for (const auto& action : resolved.actions) {
          const auto bag = bags_.find(action.bag_id);
          if (bag != bags_.end()) {
            clear_consumed_repair_reentry_boost(
                bag->second);
          }
          g4irsf17_clear_local_blocker(action.from_node);
        }
      }();
      return DispatchResult{
          trigger_runtime_bag_id,
          trigger_next,
          1,
          true};
#ifdef CZR005_EVENT_RUNTIME_TESTING
    } catch (const PIBTPostCommitFailureInjection&) {
      rollback_post_commit_transaction();
      ++result_.summary
            .bounded_local_pibt_post_commit_failure_injection_count;
      ++result_.summary
            .bounded_local_pibt_not_applicable_count;
      record_decision_latency(decision_started);
      return {};
#endif
    } catch (...) {
      rollback_post_commit_transaction();
      throw;
    }
  }

  DispatchResult try_dispatch_one(
      int node,
      double time,
      std::uint64_t arrive_event_seq,
      int bounded_local_same_bag_fallback_next = -1,
      int* priority_comparison_count = nullptr,
      bool bounded_local_pibt_attempted = false) {
    auto& controller = junctions_[node];
    if (controller.queue.empty()) {
      return {};
    }
    if (time + event_runtime_detail::kEpsilon < controller.next_dispatch_time) {
      schedule_junction_wakeup(node, controller.next_dispatch_time);
      return {};
    }

    const std::size_t queue_index =
        choose_bag(controller.queue,
                   time,
                   controller.escape_token_task,
                   priority_comparison_count);
    const auto decision_started = std::chrono::steady_clock::now();
    const int task_id = controller.queue[queue_index];
    auto& bag = bags_.at(task_id);
    bool causal_i3_override_selected = false;
    bool causal_i4_natural_hold_selected = false;
    bool g4irsf16_i3_override_selected = false;
    bool g4irsf16_i4_natural_hold_selected = false;
    bool g4irsf16_supervisor_safety_hold_selected = false;
    std::optional<G4IRSF16DecisionContext> g4irsf16_context;
    std::optional<G4IRSF16SupervisorDecision> g4irsf16_decision;
    if (bag.decision_count >= config_.max_decisions_per_bag) {
      fail_bag(bag, "max_decisions_exceeded", time);
      controller.queue.erase(controller.queue.begin() + static_cast<std::ptrdiff_t>(queue_index));
      if (uses_destination_merge_grants()) {
        ++destination_merge_bag_state(
              bag.request.runtime_bag_id)
              .junction_queue_generation;
      }
      controller.observe_local_state();
      schedule_passive(JunctionEventType::kLocalQueueUpdate,
                       time,
                       task_id,
                       node,
                       node,
                       -1,
                       "junction_failure_dequeue");
      if (controller.escape_token_task == task_id) {
        controller.escape_token_task = -1;
      }
      record_decision_latency(decision_started);
      return DispatchResult{task_id, -1, 0, true};
    }

    controller.service_calendar.purge(time);
    controller.observe_local_state();
    std::vector<int> outgoing = graph_.outgoing(node);
    std::sort(outgoing.begin(), outgoing.end());
    result_.summary.max_candidate_count =
        std::max(result_.summary.max_candidate_count, static_cast<int>(outgoing.size()));

    const bool first_edge_credit_required =
        uses_first_edge_credit() &&
        observe_first_edge_credit_requirement(bag, node);
    bool first_edge_credit_ready = true;
    int first_edge_credit_to = -1;
    if (first_edge_credit_required) {
      first_edge_credit_ready =
          ensure_first_edge_credit(bag, node, time, time, true);
      const auto* credit = credit_ledger_.find(bag.first_edge_credit_id);
      if (first_edge_credit_ready && credit != nullptr) {
        first_edge_credit_to = credit->to_node;
      } else {
        first_edge_credit_ready = false;
        ++result_.summary.first_edge_credit_local_hold_count;
        request_one_hop_credit_snapshot_refresh(node, time);
      }
    }

    EventDecisionTraceRow trace;
    trace.decision_id = next_decision_id_++;
    trace.arrive_event_seq = arrive_event_seq;
    trace.event_time = time;
    trace.task_id = bag.request.task_id;
    trace.runtime_bag_id = bag.request.runtime_bag_id;
    trace.segment_id = bag.request.segment_id;
    trace.current_node = node;
    trace.goal_node = bag.request.goal;
    trace.junction_queue_length = static_cast<int>(controller.queue.size());
    trace.junction_next_dispatch_time = controller.next_dispatch_time;
    trace.short_history.assign(bag.history.begin(), bag.history.end());
    trace.full_astar_used = false;
    populate_priority_trace(trace, bag, time);

    const bool escape_active = config_.enable_deadlock_escape &&
                               controller.escape_token_task == task_id;
    for (const int candidate : outgoing) {
      trace.candidates.push_back(candidate_record(bag,
                                                  node,
                                                  candidate,
                                                  time,
                                                  escape_active,
                                                  first_edge_credit_required,
                                                  first_edge_credit_ready,
                                                  first_edge_credit_to));
      const auto& record = trace.candidates.back();
      if (record.advertised_fault) {
        ++trace.advertised_faulted_outgoing_count;
      }
      trace.max_fault_message_age_seconds =
          std::max(trace.max_fault_message_age_seconds, record.fault_message_age_seconds);
      const long long physical_key = event_runtime_detail::directed_key(node, candidate);
      const auto physical = physical_faults_.find(physical_key);
      if (physical != physical_faults_.end() && physical->second.active_count > 0) {
        ++result_.summary.fault_target_edge_candidate_exposure_count;
        mark_fault_exposure(
            bag,
            physical_key,
            physical->second.physical_generation);
        append_fault_decision_audit(arrive_event_seq,
                                    "target_edge_candidate_exposure",
                                    time,
                                    bag,
                                    node,
                                    candidate,
                                    -1);
      }
    }
    apply_scorer(trace);

    std::vector<std::size_t> ranking(trace.candidates.size());
    for (std::size_t index = 0; index < ranking.size(); ++index) {
      ranking[index] = index;
    }
    std::sort(ranking.begin(), ranking.end(), [&](std::size_t left, std::size_t right) {
      const auto& left_record = trace.candidates[left];
      const auto& right_record = trace.candidates[right];
      if (left_record.model_score != right_record.model_score) {
        return left_record.model_score < right_record.model_score;
      }
      return left_record.next_node < right_record.next_node;
    });
    // Report the scorer's prediction over all emitted candidates before
    // applying the first-edge admission credit constraint.
    if (!ranking.empty()) {
      trace.model_prediction = trace.candidates[ranking.front()].next_node;
      if (ranking.size() > 1) {
        trace.model_margin = trace.candidates[ranking[1]].model_score -
                             trace.candidates[ranking[0]].model_score;
      } else {
        trace.model_margin = 999.0;
      }
    }
    if (first_edge_credit_required) {
      ranking.erase(
          std::remove_if(ranking.begin(),
                         ranking.end(),
                         [&](std::size_t index) {
                           return !first_edge_credit_ready ||
                                  trace.candidates[index].next_node !=
                                      first_edge_credit_to;
                         }),
          ranking.end());
    }

    std::vector<std::size_t> pre_policy_ranking = ranking;
    std::sort(pre_policy_ranking.begin(),
              pre_policy_ranking.end(),
              [&](std::size_t left, std::size_t right) {
                const auto& left_record = trace.candidates[left];
                const auto& right_record = trace.candidates[right];
                if (left_record.pre_fault_policy_score !=
                    right_record.pre_fault_policy_score) {
                  return left_record.pre_fault_policy_score <
                         right_record.pre_fault_policy_score;
                }
                return left_record.next_node < right_record.next_node;
              });
    int pre_policy_prediction = -1;
    std::size_t pre_policy_prediction_index = 0;
    if (!pre_policy_ranking.empty()) {
      pre_policy_prediction_index = pre_policy_ranking.front();
      pre_policy_prediction =
          trace.candidates[pre_policy_prediction_index].next_node;
      const long long intended_key =
          event_runtime_detail::directed_key(node, pre_policy_prediction);
      const auto physical = physical_faults_.find(intended_key);
      if (physical != physical_faults_.end() && physical->second.active_count > 0) {
        ++result_.summary.fault_target_edge_attempt_count;
        append_fault_decision_audit(arrive_event_seq,
                                    "target_edge_attempt",
                                    time,
                                    bag,
                                    node,
                                    pre_policy_prediction,
                                    -1);
      }
    }

    int selected = -1;
    std::string selected_reason =
        first_edge_credit_required && !first_edge_credit_ready
            ? "first_edge_credit_unavailable"
            : "no_outgoing_candidate";
    bool physical_interlock_rejected = false;
    int physical_interlock_intended_next = -1;
    bool local_fault_policy_acted = false;
    bool bounded_local_same_bag_fallback_selected = false;
    if (!ranking.empty()) {
      const auto& predicted = trace.candidates[ranking.front()];
      const bool advertised_policy_block =
          config_.enable_fault_policy && predicted.advertised_fault;
      if (predicted.shield_allowed && !advertised_policy_block) {
        selected = predicted.next_node;
        selected_reason = "predicted_candidate_allowed";
      } else {
        trace.risk_gate_triggered = true;
        if (!predicted.shield_allowed) {
          ++result_.summary.shield_rejection_count;
          if (predicted.shield_reason == "physical_fault" && !predicted.advertised_fault) {
            ++result_.summary.stale_fault_shield_rejection_count;
          }
        }
        if (predicted.shield_reason == "physical_fault") {
          physical_interlock_rejected = true;
          physical_interlock_intended_next = predicted.next_node;
          ++result_.summary.physical_fault_interlock_rejection_count;
          append_fault_decision_audit(arrive_event_seq,
                                      "physical_fault_interlock_rejection",
                                      time,
                                      bag,
                                      node,
                                      predicted.next_node,
                                      -1);
          selected_reason = "physical_fault_interlock_hold";
        } else {
          selected_reason = advertised_policy_block ? "advertised_fault_hold"
                                                    : predicted.shield_reason;
        }
        // The physical interlock owns safety even when the advertised fault
        // message is lost.  If the recovery policy is enabled, let it choose
        // one already-materialized local alternative after that interlock
        // rejects the preferred edge.  This is deliberately independent of
        // the legacy same-bag ``enable_pibt_lite`` switch: P1--P4 disable that
        // legacy scan, but lost-notification recovery must still be able to
        // re-arbitrate one next edge locally.  No future route or non-local
        // state is inspected here.
        const bool physical_fault_local_handoff =
            physical_interlock_rejected && config_.enable_fault_policy;
        const bool legacy_same_bag_handoff =
            !physical_interlock_rejected && config_.enable_pibt_lite;
        const bool bounded_local_same_bag_handoff =
            !physical_interlock_rejected &&
            predicted.shield_reason == "destination_queue_full" &&
            canonical_pibt_mode() != BoundedLocalPIBTMode::kP0 &&
            bounded_local_same_bag_fallback_next >= 0;
        if (bounded_local_same_bag_handoff) {
          for (std::size_t rank = 1; rank < ranking.size(); ++rank) {
            const auto& alternative = trace.candidates[ranking[rank]];
            const bool alternative_advertised_block =
                config_.enable_fault_policy && alternative.advertised_fault;
            if (alternative.next_node ==
                    bounded_local_same_bag_fallback_next &&
                alternative.shield_allowed &&
                !alternative_advertised_block) {
              selected = alternative.next_node;
              trace.fallback_selected_next = selected;
              selected_reason =
                  "bounded_local_pibt_same_bag_safe_fallback";
              bounded_local_same_bag_fallback_selected = true;
              break;
            }
          }
        }
        if (selected < 0 &&
            (physical_fault_local_handoff || legacy_same_bag_handoff)) {
          for (std::size_t rank = 1; rank < ranking.size(); ++rank) {
            const auto& alternative = trace.candidates[ranking[rank]];
            const bool alternative_advertised_block =
                config_.enable_fault_policy && alternative.advertised_fault;
            if (alternative.shield_allowed && !alternative_advertised_block) {
              selected = alternative.next_node;
              trace.fallback_selected_next = selected;
              selected_reason = physical_interlock_rejected
                                    ? "physical_fault_interlock_local_handoff"
                                    : "same_bag_alternative_edge_scan_handoff";
              if (config_.enable_pibt_lite) {
                ++result_.summary.pibt_lite_handoff_count;
                ++result_.summary
                      .same_bag_alternative_edge_scan_handoff_count;
              }
              break;
            }
          }
        }
      }
    }

    if (active_causal_step_ != nullptr && g4irsf16_enabled()) {
      throw std::logic_error(
          "G4IRSF16 online supervisor cannot share a G4IRSF14 causal-probe "
          "runtime; run the causal clone with supervisor mode off");
    }
    std::vector<int> causal_legal_next_edges;
    if ((active_causal_step_ != nullptr || g4irsf16_enabled()) &&
        selected >= 0) {
      causal_legal_next_edges.reserve(ranking.size());
      for (const std::size_t candidate_index : ranking) {
        const auto& candidate =
            trace.candidates[candidate_index];
        const bool advertised_policy_block =
            config_.enable_fault_policy &&
            candidate.advertised_fault;
        if (candidate.shield_allowed &&
            !advertised_policy_block) {
          causal_legal_next_edges.push_back(
              candidate.next_node);
        }
      }
      std::sort(causal_legal_next_edges.begin(),
                causal_legal_next_edges.end());
      causal_legal_next_edges.erase(
          std::unique(causal_legal_next_edges.begin(),
                      causal_legal_next_edges.end()),
          causal_legal_next_edges.end());
    }

    if (active_causal_step_ != nullptr &&
        selected >= 0 &&
        causal_legal_next_edges.size() >= 2U &&
        std::find(causal_legal_next_edges.begin(),
                  causal_legal_next_edges.end(),
                  selected) !=
            causal_legal_next_edges.end()) {
      G4IRSF14CloneBoundary boundary;
      boundary.kind =
          G4IRSF14CloneBoundaryKind::
              kJunctionRouteArbitration;
      boundary.node = node;
      boundary.runtime_bag_id = task_id;
      boundary.baseline_next_node = selected;
      boundary.legal_next_edges =
          causal_legal_next_edges;
      if (const auto* intervention =
              observe_causal_boundary(std::move(boundary));
          intervention != nullptr) {
        if (intervention->kind !=
                G4IRSF14CloneInterventionKind::kNextEdge ||
            intervention->runtime_bag_id != task_id ||
            std::find(causal_legal_next_edges.begin(),
                      causal_legal_next_edges.end(),
                      intervention->selected_next_node) ==
                causal_legal_next_edges.end()) {
          throw std::logic_error(
              "I3 directive did not select one legal adjacent edge");
        }
        selected = intervention->selected_next_node;
        selected_reason =
            "g4irsf14_I3_content_addressed_legal_next_edge";
        bounded_local_same_bag_fallback_selected = false;
        causal_i3_override_selected = true;
      }
    }

    if (active_causal_step_ != nullptr && selected >= 0) {
      G4IRSF14CloneBoundary boundary;
      boundary.kind =
          G4IRSF14CloneBoundaryKind::
              kHoldReleaseOpportunity;
      boundary.node = node;
      boundary.runtime_bag_id = task_id;
      boundary.baseline_next_node = selected;
      boundary.baseline_release = true;
      boundary.legal_next_edges =
          causal_legal_next_edges;
      if (const auto* intervention =
              observe_causal_boundary(std::move(boundary));
          intervention != nullptr) {
        if (intervention->kind !=
                G4IRSF14CloneInterventionKind::kHoldRelease ||
            intervention->runtime_bag_id != task_id ||
            intervention->selected_boolean) {
          throw std::logic_error(
              "I4 directive may only convert release into hold");
        }
        selected = -1;
        selected_reason =
            "g4irsf14_I4_content_addressed_safe_hold";
        bounded_local_same_bag_fallback_selected = false;
        causal_i4_natural_hold_selected = true;
      }
    }

    if (g4irsf16_enabled()) {
      if (g4irsf16_supervisor_ == nullptr ||
          (!g4irsf16_uses_diagnostic_rule() &&
           (g4irsf16_i3_model_ == nullptr ||
            g4irsf16_i4_model_ == nullptr))) {
        throw std::logic_error(
            "G4IRSF16 enabled without native model/supervisor state");
      }
      trace.g4irsf16_evaluated = true;
      trace.g4irsf16_mode =
          canonical_g4irsf16_supervisor_mode();
      trace.g4irsf16_baseline_next = selected;
      trace.g4irsf16_node_generation =
          static_cast<std::uint64_t>(bag.decision_count);

      G4IRSF16DecisionContext context;
      context.runtime_bag_id =
          std::to_string(bag.request.runtime_bag_id);
      context.segment_id = bag.request.segment_id;
      context.node = node;
      // A natural hold does not increment decision_count, so the same
      // node-generation is consumed on the very next re-evaluation.  A move
      // increments it, allowing a fresh opportunity only after real progress.
      context.generation = trace.g4irsf16_node_generation;
      const auto g4irsf16_fault_generation =
          g4irsf16_physical_fault_generation_by_bag_.find(
              bag.request.runtime_bag_id);
      context.physical_fault_generation =
          g4irsf16_fault_generation ==
                  g4irsf16_physical_fault_generation_by_bag_.end()
              ? 0U
              : g4irsf16_fault_generation->second;
      context.f2_action = selected;
      context.legal_alternatives = causal_legal_next_edges;
      context.service_opportunity_available = selected >= 0;
      context.shield_safe = selected >= 0;
      context.fault_active =
          selected < 0 && physical_interlock_rejected;
      context.astar_fallback_requested = false;

      const EventCandidateRecord* baseline = nullptr;
      if (selected >= 0) {
        const auto found = std::find_if(
            trace.candidates.begin(), trace.candidates.end(),
            [&](const EventCandidateRecord& candidate) {
              return candidate.next_node == selected;
            });
        if (found == trace.candidates.end()) {
          throw std::logic_error(
              "G4IRSF16 F2 baseline is absent from local candidates");
        }
        baseline = &*found;
      }

      if (baseline == nullptr) {
        trace.g4irsf16_i4_model_reason = "NO_F2_BASELINE";
        trace.g4irsf16_i3_model_reason = "NO_F2_BASELINE";
      } else if (g4irsf16_uses_diagnostic_rule()) {
        const auto& rule = config_.g4irsf16_i4_diagnostic_rule;
        const bool activates = rule.activates(
            trace.model_margin,
            baseline->target_queue_length,
            baseline->target_scheduled_incoming);
        ++result_.summary.g4irsf16_i4_evaluation_count;
        trace.g4irsf16_i4_activation = activates;
        trace.g4irsf16_i4_diagnostic_only = true;
        trace.g4irsf16_i4_policy_id = rule.rule;
        trace.g4irsf16_i4_ood = false;
        trace.g4irsf16_i4_model_reason =
            activates ? "H5_DIAGNOSTIC_RULE_ACTIVATE"
                      : "H5_DIAGNOSTIC_RULE_ABSTAIN";
        trace.g4irsf16_i3_model_reason =
            "I3_H0_NOT_PROMOTED";
        context.i4_proposed = activates;
        context.i4_model_authorized = rule.authorized;
        context.i4_diagnostic_rule = true;
        // These are supervisor authorization sentinels, not estimated model
        // probabilities.  Trace telemetry labels the source diagnostic-only.
        context.i4_confidence = activates ? 1.0 : 0.0;
        context.i4_risk = activates ? 0.0 : 1.0;
        if (activates) {
          ++result_.summary.g4irsf16_i4_activation_count;
        }
      } else {
        const auto i4_score = g4irsf16_i4_model_->score(
            g4irsf16_local_features(
                bag, node, time, trace, *baseline, *baseline,
                2, true));
        ++result_.summary.g4irsf16_i4_evaluation_count;
        trace.g4irsf16_i4_activation = i4_score.activation;
        trace.g4irsf16_i4_benefit_lcb =
            i4_score.benefit_probability_lcb;
        trace.g4irsf16_i4_harmful_ucb =
            i4_score.harmful_probability_ucb;
        trace.g4irsf16_i4_utility_lcb_seconds =
            i4_score.utility_lcb_seconds;
        trace.g4irsf16_i4_ood = i4_score.ood;
        trace.g4irsf16_i4_model_reason =
            i4_score.abstention_reason;
        context.i4_proposed = i4_score.activation;
        context.i4_model_authorized =
            config_.g4irsf16_i4_model.authorized;
        context.i4_confidence =
            i4_score.benefit_probability_lcb;
        context.i4_risk = i4_score.harmful_probability_ucb;
        if (i4_score.activation) {
          ++result_.summary.g4irsf16_i4_activation_count;
          trace.g4irsf16_i3_model_reason =
              "I4_PRECEDENCE_NOT_EVALUATED";
        } else {
          bool have_audit_candidate = false;
          bool have_activated_candidate = false;
          int audit_candidate = -1;
          int activated_candidate = -1;
          G4IRSF16SelectiveLinearScore audit_score;
          G4IRSF16SelectiveLinearScore activated_score;
          const auto better = [](const G4IRSF16SelectiveLinearScore& left,
                                 int left_node,
                                 const G4IRSF16SelectiveLinearScore& right,
                                 int right_node) {
            return std::tie(left.utility_lcb_seconds,
                            left.benefit_probability_lcb,
                            right.harmful_probability_ucb,
                            right_node) >
                   std::tie(right.utility_lcb_seconds,
                            right.benefit_probability_lcb,
                            left.harmful_probability_ucb,
                            left_node);
          };
          for (const int alternative : causal_legal_next_edges) {
            if (alternative == selected) {
              continue;
            }
            const auto found = std::find_if(
                trace.candidates.begin(), trace.candidates.end(),
                [&](const EventCandidateRecord& candidate) {
                  return candidate.next_node == alternative;
                });
            if (found == trace.candidates.end()) {
              throw std::logic_error(
                  "G4IRSF16 legal alternative is absent from candidates");
            }
            const auto score = g4irsf16_i3_model_->score(
                g4irsf16_local_features(
                    bag, node, time, trace, *baseline, *found,
                    static_cast<int>(causal_legal_next_edges.size()),
                    false));
            ++result_.summary.g4irsf16_i3_candidate_evaluation_count;
            if (!have_audit_candidate ||
                better(score, alternative,
                       audit_score, audit_candidate)) {
              have_audit_candidate = true;
              audit_candidate = alternative;
              audit_score = score;
            }
            if (score.activation &&
                (!have_activated_candidate ||
                 better(score, alternative,
                        activated_score, activated_candidate))) {
              have_activated_candidate = true;
              activated_candidate = alternative;
              activated_score = score;
            }
          }
          if (have_activated_candidate) {
            audit_candidate = activated_candidate;
            audit_score = activated_score;
            context.i3_action = activated_candidate;
            context.i3_model_authorized =
                config_.g4irsf16_i3_model.authorized;
            context.i3_confidence =
                activated_score.benefit_probability_lcb;
            context.i3_risk =
                activated_score.harmful_probability_ucb;
            ++result_.summary.g4irsf16_i3_activation_count;
          }
          if (have_audit_candidate) {
            trace.g4irsf16_i3_candidate = audit_candidate;
            trace.g4irsf16_i3_activation = audit_score.activation;
            trace.g4irsf16_i3_benefit_lcb =
                audit_score.benefit_probability_lcb;
            trace.g4irsf16_i3_harmful_ucb =
                audit_score.harmful_probability_ucb;
            trace.g4irsf16_i3_utility_lcb_seconds =
                audit_score.utility_lcb_seconds;
            trace.g4irsf16_i3_ood = audit_score.ood;
            trace.g4irsf16_i3_model_reason =
                audit_score.abstention_reason;
          } else {
            trace.g4irsf16_i3_model_reason =
                "NO_LEGAL_I3_ALTERNATIVE";
          }
        }
      }

      auto decision = g4irsf16_supervisor_->evaluate(context);
      ++result_.summary.g4irsf16_supervisor_evaluation_count;
      trace.g4irsf16_state =
          g4irsf16_supervisor_state_name(decision.state);
      trace.g4irsf16_action =
          g4irsf16_action_kind_name(decision.action);
      trace.g4irsf16_source =
          g4irsf16_action_source_name(decision.source);
      trace.g4irsf16_reason = decision.reason;
      trace.g4irsf16_state_generation =
          decision.state_generation;
      trace.g4irsf16_proposed_next =
          decision.selected_next_node;
      trace.g4irsf16_proposed_hold =
          decision.state ==
          G4IRSF16SupervisorState::kI4SelectiveHold;
      if (decision.state == G4IRSF16SupervisorState::kSafeHold) {
        ++result_.summary.g4irsf16_safe_hold_count;
      } else if (decision.state ==
                 G4IRSF16SupervisorState::kFaultRecovery) {
        ++result_.summary.g4irsf16_fault_recovery_count;
      }

      if (!g4irsf16_closed_loop()) {
        if (decision.state ==
                G4IRSF16SupervisorState::kI3RareOverride ||
            decision.state ==
                G4IRSF16SupervisorState::kI4SelectiveHold) {
          ++result_.summary.g4irsf16_shadow_proposal_count;
        }
      } else if (decision.state ==
                 G4IRSF16SupervisorState::kI4SelectiveHold) {
        selected = -1;
        selected_reason =
            "g4irsf16_I4_native_selective_natural_hold";
        bounded_local_same_bag_fallback_selected = false;
        g4irsf16_i4_natural_hold_selected = true;
        trace.g4irsf16_action_changed = true;
      } else if (decision.state ==
                 G4IRSF16SupervisorState::kI3RareOverride) {
        if (decision.selected_next_node < 0 ||
            std::find(causal_legal_next_edges.begin(),
                      causal_legal_next_edges.end(),
                      decision.selected_next_node) ==
                causal_legal_next_edges.end()) {
          throw std::logic_error(
              "G4IRSF16 supervisor emitted a non-local I3 edge");
        }
        selected = decision.selected_next_node;
        selected_reason =
            "g4irsf16_I3_native_rare_legal_next_edge";
        bounded_local_same_bag_fallback_selected = false;
        g4irsf16_i3_override_selected = true;
        trace.g4irsf16_action_changed =
            selected != trace.g4irsf16_baseline_next;
      } else if (decision.action ==
                     G4IRSF16ActionKind::kFaultHold ||
                 decision.action ==
                     G4IRSF16ActionKind::kSafeHold) {
        trace.g4irsf16_action_changed = selected >= 0;
        selected = -1;
        selected_reason =
            decision.action == G4IRSF16ActionKind::kFaultHold
                ? "g4irsf16_supervisor_fault_hold"
                : "g4irsf16_supervisor_safe_hold";
        bounded_local_same_bag_fallback_selected = false;
        g4irsf16_supervisor_safety_hold_selected = true;
      }
      g4irsf16_context = std::move(context);
      g4irsf16_decision = std::move(decision);
    }

    if (physical_interlock_rejected) {
      if (selected >= 0) {
        ++result_.summary.physical_fault_interlock_reroute_count;
        append_fault_decision_audit(arrive_event_seq,
                                    "physical_fault_interlock_reroute",
                                    time,
                                    bag,
                                    node,
                                    physical_interlock_intended_next,
                                    selected);
      } else {
        ++result_.summary.physical_fault_interlock_hold_count;
        append_fault_decision_audit(arrive_event_seq,
                                    "physical_fault_interlock_hold",
                                    time,
                                    bag,
                                    node,
                                    physical_interlock_intended_next,
                                    -1);
      }
    }

    if (config_.enable_fault_policy && pre_policy_prediction >= 0) {
      const auto& pre_policy_candidate =
          trace.candidates[pre_policy_prediction_index];
      if (pre_policy_candidate.advertised_fault && selected != pre_policy_prediction) {
        local_fault_policy_acted = true;
        ++result_.summary.local_fault_policy_action_count;
        if (selected >= 0) {
          ++result_.summary.local_fault_policy_reroute_count;
          append_fault_decision_audit(arrive_event_seq,
                                      "local_fault_policy_reroute",
                                      time,
                                      bag,
                                      node,
                                      pre_policy_prediction,
                                      selected);
        } else {
          ++result_.summary.local_fault_policy_hold_count;
          append_fault_decision_audit(arrive_event_seq,
                                      "local_fault_policy_hold",
                                      time,
                                      bag,
                                      node,
                                      pre_policy_prediction,
                                      -1);
        }
      }
    }

    if (selected >= 0 && uses_destination_merge_grants() &&
        graph_.incoming_degree(selected) > 1 &&
        selected != bag.request.goal) {
      trace.selected_next = selected;
      trace.decision_source = "destination_merge_request_pending";
      trace.rule_reason =
          (trace.scorer_risk_abstain
               ? "frozen_scorer_risk_abstain_exact_s0_fallback;"
               : "") +
          selected_reason +
          ";phase5a_destination_request_no_edge_commit";
      const auto& pre_request_state =
          destination_merge_bag_state(
              bag.request.runtime_bag_id);
      const std::uint64_t pre_request_id =
          pre_request_state.pending_request_id;
      const std::uint64_t pre_request_lineage =
          pre_request_state.pending_lineage;
      if (submit_destination_merge_request(
              bag, node, selected, time, trace)) {
        const auto& post_request_state =
            destination_merge_bag_state(
                bag.request.runtime_bag_id);
        const auto pending =
            pending_merge_dispatches_.find(
                post_request_state.pending_request_id);
        const bool newly_committed =
            g4irsf15_i3_committed_new_pending_request(
                pre_request_id,
                pre_request_lineage,
                post_request_state.pending_request_id,
                post_request_state.pending_lineage,
                pending != pending_merge_dispatches_.end() &&
                    pending->second.runtime_bag_id ==
                        task_id &&
                    pending->second.upstream_node ==
                        node &&
                    pending->second.destination_node ==
                        selected);
        if (g4irsf16_i3_override_selected &&
            newly_committed) {
          if (!g4irsf16_context.has_value() ||
              !g4irsf16_decision.has_value() ||
              !g4irsf16_decision->has_token ||
              !g4irsf16_supervisor_->consume_token(
                  g4irsf16_decision->token,
                  *g4irsf16_context)) {
            throw std::logic_error(
                "G4IRSF16 I3 merge request lost its action token");
          }
          ++result_.summary.g4irsf16_i3_applied_count;
          ++result_.summary.g4irsf16_action_change_count;
        } else if (g4irsf16_i3_override_selected) {
          trace.g4irsf16_action_changed = false;
        }
        if (causal_i3_override_selected) {
          if (newly_committed) {
            mark_causal_action_applied(
                "APPLIED_I3_MERGE_REQUEST_ENQUEUED_ONE_ACTION",
                {task_id});
          }
        }
        event_runtime_detail::G4IRSF17SourceBlockerObservation
            merge_blocker;
        const auto destination_controller =
            destination_merge_controllers_.find(selected);
        merge_blocker.consider(
            G4IRSF17SourceWaitReason::kDestinationMergeToken,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kDestinationMergeToken,
            selected,
            node,
            selected,
            destination_controller ==
                    destination_merge_controllers_.end()
                ? 0
                : destination_controller->second.generation());
        g4irsf17_set_local_blocker(node, std::move(merge_blocker));
        record_decision_latency(decision_started);
        return DispatchResult{task_id, selected, 0, true};
      }
      if (g4irsf16_i3_override_selected) {
        trace.g4irsf16_action_changed = false;
      }
      selected = -1;
      selected_reason = "destination_merge_request_rejected";
    } else if (selected >= 0 && uses_destination_merge_grants() &&
               selected == bag.request.goal &&
               graph_.incoming_degree(selected) > 1) {
      // Frozen R3 exempts a bag's actual goal from destination service
      // reservation. E4 preserves that semantic rather than fabricating a
      // terminal slot/grant.
      ++result_.summary.merge_grant_goal_exempt_bypass_count;
    }

    bool first_edge_credit_bound = false;
    if (selected >= 0 && first_edge_credit_required) {
      const auto bound = credit_ledger_.bind(
          bag.first_edge_credit_id,
          credit_use_context(bag, node, selected, time));
      if (!bound.accepted) {
        if (g4irsf16_i3_override_selected) {
          trace.g4irsf16_action_changed = false;
        }
        selected = -1;
        selected_reason = "first_edge_credit_bind_" + bound.reason;
        bag.first_edge_credit_id = 0;
        ++result_.summary.first_edge_credit_local_hold_count;
      } else {
        first_edge_credit_bound = true;
      }
    }
    trace.selected_next = selected;
    if (selected >= 0) {
      trace.decision_source = local_fault_policy_acted
                                  ? "local_fault_policy"
                              : g4irsf16_i3_override_selected
                                  ? "g4irsf16_i3_rare_override"
                              : physical_interlock_rejected
                                  ? "physical_fault_interlock"
                              : bounded_local_same_bag_fallback_selected
                                  ? "bounded_local_pibt_same_bag_safe_fallback"
                              : first_edge_credit_bound
                                  ? "expiring_first_edge_credit"
                              : escape_active
                                  ? "deadlock_escape"
                              : selected != trace.model_prediction
                                  ? "local_pibt_lite_shield"
                              : trace.scorer_risk_abstain
                                  ? "scorer_risk_s0_fallback"
                              : trace.scorer_effective_id ==
                                        "S0_current_handwritten_static_score"
                                  ? "local_static_potential"
                                  : trace.scorer_effective_id;
      trace.rule_reason =
          (trace.scorer_risk_abstain
               ? "frozen_scorer_risk_abstain_exact_s0_fallback;"
               : "") +
          selected_reason;
      if (g4irsf16_i3_override_selected) {
        if (!g4irsf16_context.has_value() ||
            !g4irsf16_decision.has_value() ||
            !g4irsf16_decision->has_token ||
            !g4irsf16_supervisor_->consume_token(
                g4irsf16_decision->token,
                *g4irsf16_context)) {
          throw std::logic_error(
              "G4IRSF16 I3 edge commit lost its action token");
        }
        ++result_.summary.g4irsf16_i3_applied_count;
        ++result_.summary.g4irsf16_action_change_count;
      }
      dispatch_selected_edge(bag, node, selected, time);
      if (causal_i3_override_selected) {
        mark_causal_action_applied(
            "APPLIED_I3_ONE_EDGE_COMMIT_ONE_ACTION",
            {task_id});
      }
      if (first_edge_credit_bound) {
        const auto consumed = credit_ledger_.consume(
            bag.first_edge_credit_id,
            credit_use_context(bag, node, selected, time));
        if (!consumed.accepted) {
          throw std::logic_error(
              "first-edge credit changed during atomic selected-edge commit");
        }
        bag.first_edge_credit_id = 0;
        bag.first_edge_credit_consumed = true;
      }
      if (uses_first_edge_credit() &&
          !bag.first_edge_credit_consumed) {
        bag.first_edge_credit_id = 0;
        bag.first_edge_credit_consumed = true;
      }
      if (bounded_local_same_bag_fallback_selected) {
        ++result_.summary
              .bounded_local_pibt_same_bag_fallback_count;
      }
      // A blocked local retry is a wait, not a route decision.  Counting
      // holds against max_decisions_per_bag used to fail healthy bags after
      // 512 quarter-second congestion retries at original scale.  The
      // retry/deadlock counters and global event/time ceilings already bound
      // liveness; this counter bounds only committed one-next-edge actions,
      // matching the atomic PIBT commit path above.
      ++bag.decision_count;
      ++result_.summary.decision_count;
      controller.queue.erase(controller.queue.begin() + static_cast<std::ptrdiff_t>(queue_index));
      if (uses_destination_merge_grants()) {
        ++destination_merge_bag_state(
              bag.request.runtime_bag_id)
              .junction_queue_generation;
      }
      controller.observe_local_state();
      schedule_passive(JunctionEventType::kLocalQueueUpdate,
                       time,
                       task_id,
                       node,
                       node,
                       selected,
                       "junction_dequeue");
      controller.next_dispatch_time = time + config_.dispatch_headway_seconds;
      if (bag.deadlock_started_at >= 0.0) {
        ++result_.summary.resolved_deadlock_count;
        result_.summary.max_deadlock_duration =
            std::max(result_.summary.max_deadlock_duration, time - bag.deadlock_started_at);
        bag.deadlock_started_at = -1.0;
      }
      if (controller.escape_token_task == task_id) {
        controller.escape_token_task = -1;
      }
      clear_consumed_repair_reentry_boost(bag);
    } else {
      ++bag.retry_count;
      trace.decision_source = local_fault_policy_acted
                                  ? "local_fault_policy_hold"
                              : g4irsf16_i4_natural_hold_selected
                                  ? "g4irsf16_i4_selective_hold"
                              : g4irsf16_supervisor_safety_hold_selected
                                  ? "g4irsf16_supervisor_safety_hold"
                              : physical_interlock_rejected
                                  ? "physical_fault_interlock_hold"
                              : escape_active ? "deadlock_escape_hold" : "local_hold";
      trace.rule_reason =
          (trace.scorer_risk_abstain
               ? "frozen_scorer_risk_abstain_exact_s0_fallback;"
               : "") +
          selected_reason;
      if (bag.retry_count >= config_.deadlock_retry_threshold && bag.deadlock_started_at < 0.0) {
        bag.deadlock_started_at = time;
        ++result_.summary.deadlock_count;
        if (config_.enable_deadlock_escape) {
          controller.escape_token_task = task_id;
          ++result_.summary.deadlock_escape_activation_count;
        }
      }
      double earliest_resource_retry = std::numeric_limits<double>::infinity();
      for (const auto& candidate : trace.candidates) {
        const double corridor_ready = candidate.corridor_next_available;
        const double target_departure_ready = candidate.target_next_available - candidate.travel_time;
        const double resource_ready = std::max(corridor_ready, target_departure_ready);
        if (resource_ready > time + event_runtime_detail::kEpsilon) {
          earliest_resource_retry = std::min(earliest_resource_retry, resource_ready);
        }
      }
      const double retry_time =
          (causal_i4_natural_hold_selected ||
           g4irsf16_i4_natural_hold_selected)
              ? time + std::max(service_duration(node),
                                config_.dispatch_headway_seconds)
          : std::isfinite(earliest_resource_retry)
              ? std::max(time + config_.retry_interval,
                         earliest_resource_retry)
              : time + config_.retry_interval;
      schedule_junction_wakeup(node, retry_time);
      if (g4irsf16_i4_natural_hold_selected) {
        if (!g4irsf16_context.has_value() ||
            !g4irsf16_decision.has_value() ||
            !g4irsf16_decision->has_token ||
            !g4irsf16_supervisor_->consume_token(
                g4irsf16_decision->token,
                *g4irsf16_context)) {
          throw std::logic_error(
              "G4IRSF16 I4 natural hold lost its action token");
        }
        ++result_.summary.g4irsf16_i4_applied_count;
        ++result_.summary.g4irsf16_action_change_count;
      }
      if (g4irsf16_supervisor_safety_hold_selected) {
        if (!g4irsf16_decision.has_value() ||
            !g4irsf16_context.has_value()) {
          throw std::logic_error(
              "G4IRSF16 safety hold lost its decision context");
        }
        if (g4irsf16_decision->has_token) {
          if (!g4irsf16_supervisor_->consume_token(
                  g4irsf16_decision->token,
                  *g4irsf16_context)) {
            throw std::logic_error(
                "G4IRSF16 safety hold lost its action token");
          }
        } else if (g4irsf16_decision->action !=
                   G4IRSF16ActionKind::kFaultHold) {
          throw std::logic_error(
              "G4IRSF16 non-fault safety hold lacked an action token");
        }
        if (trace.g4irsf16_action_changed) {
          ++result_.summary.g4irsf16_action_change_count;
        }
      }
      if (causal_i4_natural_hold_selected) {
        const auto& local = g4irsf14_local_state(node);
        if (!controller.junction_wakeup_pending ||
            !event_runtime_detail::same_timestamp(
                local.junction_wakeup_time, retry_time)) {
          throw std::logic_error(
              "I4 natural hold did not commit its next local service "
              "opportunity");
        }
        mark_causal_action_applied(
            "APPLIED_I4_SAFE_HOLD_UNTIL_NEXT_JUNCTION_SERVICE_OPPORTUNITY",
            {task_id});
      }

      event_runtime_detail::G4IRSF17SourceBlockerObservation local_blocker;
      const int predicted_blocker_node =
          physical_interlock_intended_next >= 0
              ? physical_interlock_intended_next
          : pre_policy_prediction >= 0
              ? pre_policy_prediction
              : trace.model_prediction;
      if (physical_interlock_rejected ||
          (local_fault_policy_acted && selected < 0) ||
          selected_reason == "advertised_fault_hold") {
        std::uint64_t generation = 0;
        if (predicted_blocker_node >= 0) {
          const auto physical = physical_faults_.find(
              event_runtime_detail::directed_key(
                  node, predicted_blocker_node));
          if (physical != physical_faults_.end()) {
            generation = static_cast<std::uint64_t>(
                physical->second.physical_generation);
          }
        }
        local_blocker.consider(
            G4IRSF17SourceWaitReason::kPhysicalFaultOrGeneration,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kPhysicalEdge,
            predicted_blocker_node >= 0 ? predicted_blocker_node : node,
            node,
            predicted_blocker_node,
            generation);
      }
      if (causal_i4_natural_hold_selected ||
          g4irsf16_i4_natural_hold_selected ||
          g4irsf16_supervisor_safety_hold_selected) {
        local_blocker.consider(
            G4IRSF17SourceWaitReason::kSupervisorHold,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kSupervisorState,
            node,
            node,
            node,
            static_cast<std::uint64_t>(bag.decision_count));
      }
      if (bounded_local_pibt_attempted || escape_active) {
        local_blocker.consider(
            G4IRSF17SourceWaitReason::kPIBTOrRecoveryTransaction,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kPIBTOrRecoveryTransaction,
            node,
            node,
            node,
            static_cast<std::uint64_t>(bag.retry_count));
      }
      if (selected_reason == "destination_queue_full") {
        local_blocker.consider(
            G4IRSF17SourceWaitReason::kDestinationQueueCapacity,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kDestinationQueue,
            predicted_blocker_node >= 0 ? predicted_blocker_node : node,
            node,
            predicted_blocker_node,
            static_cast<std::uint64_t>(bag.retry_count));
      }
      if (selected_reason == "destination_merge_request_rejected") {
        local_blocker.consider(
            G4IRSF17SourceWaitReason::kDestinationMergeToken,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kDestinationMergeToken,
            predicted_blocker_node >= 0 ? predicted_blocker_node : node,
            node,
            predicted_blocker_node,
            static_cast<std::uint64_t>(bag.retry_count));
      }
      if (first_edge_credit_required && !first_edge_credit_ready) {
        local_blocker.consider(
            G4IRSF17SourceWaitReason::kFirstEdgeCreditUnavailable,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kFirstEdgeCredit,
            node,
            node,
            first_edge_credit_to,
            static_cast<std::uint64_t>(bag.retry_count));
      }
      if (!local_blocker.valid) {
        local_blocker.consider(
            G4IRSF17SourceWaitReason::kOtherExplicitReason,
            event_runtime_detail::G4IRSF17SourceWaitResource::
                kOtherLocalResource,
            node,
            node,
            predicted_blocker_node,
            static_cast<std::uint64_t>(bag.retry_count));
      }
      g4irsf17_set_local_blocker(node, std::move(local_blocker));
    }

    append_decision_trace(std::move(trace), selected >= 0);
    record_decision_latency(decision_started);
    return DispatchResult{task_id, selected, selected >= 0 ? 1 : 0, true};
  }

  std::vector<double> g4irsf16_local_features(
      const BagState& bag,
      int current,
      double time,
      const EventDecisionTraceRow& trace,
      const EventCandidateRecord& baseline,
      const EventCandidateRecord& intervention,
      int legal_action_count,
      bool intervention_is_hold) const {
    // Keep this vector in the exact order frozen by model.py.  Every value is
    // current-node, one-hop candidate, bounded history, or static map data.
    // In particular, this function owns no route search and never scans a
    // global queue/reservation structure.
    std::vector<double> features;
    features.reserve(kG4IRSF16DeploymentFeatureCount);
    const double deadline_slack = bag.request.deadline - time;
    const double wait_age = std::max(0.0, time - bag.request.release_time);
    const double current_calendar_wait =
        std::max(0.0, trace.junction_next_dispatch_time - time);
    const double target_calendar_wait =
        std::max(0.0,
                 intervention.target_next_available - time -
                     intervention.travel_time);
    const double current_remaining =
        static_potential(current, bag.request.goal);
    const double baseline_remaining =
        baseline.travel_time + baseline.static_potential;
    const double intervention_travel =
        intervention_is_hold ? 0.0 : intervention.travel_time;
    const double intervention_remaining =
        intervention_is_hold
            ? current_remaining
            : intervention.travel_time + intervention.static_potential;
    std::set<int> unique_history;
    for (const int location : bag.history) {
      unique_history.insert(location);
    }
    const double repeat_count =
        static_cast<double>(bag.history.size() - unique_history.size());
    const auto has_segment_suffix = [&](const std::string& suffix) {
      return bag.request.segment_id.size() >= suffix.size() &&
             bag.request.segment_id.compare(
                 bag.request.segment_id.size() - suffix.size(),
                 suffix.size(), suffix) == 0;
    };
    const bool storage_in = has_segment_suffix(":storage_in");
    const bool storage_out = has_segment_suffix(":storage_out");
    const bool direct = has_segment_suffix(":direct");
    constexpr double kPi = 3.141592653589793238462643383279502884;
    const double day_seconds = 24.0 * 3600.0;
    double day_time = std::fmod(time, day_seconds);
    if (day_time < 0.0) {
      day_time += day_seconds;
    }
    const double radians = 2.0 * kPi * day_time / day_seconds;
    features.push_back(deadline_slack);
    features.push_back(wait_age);
    features.push_back(static_cast<double>(trace.junction_queue_length));
    features.push_back(
        static_cast<double>(intervention.target_queue_length));
    features.push_back(
        static_cast<double>(intervention.target_scheduled_incoming));
    features.push_back(current_calendar_wait);
    features.push_back(target_calendar_wait);
    features.push_back(
        static_cast<double>(std::max(0, legal_action_count - 1)));
    features.push_back(static_cast<double>(legal_action_count));
    features.push_back(static_cast<double>(trace.candidates.size()));
    features.push_back(
        static_cast<double>(graph_.node(current).node_type));
    features.push_back(service_duration(current));
    features.push_back(baseline.travel_time);
    features.push_back(intervention_travel);
    features.push_back(current_remaining);
    features.push_back(baseline_remaining);
    features.push_back(intervention_remaining);
    features.push_back(baseline_remaining - intervention_remaining);
    features.push_back(trace.model_margin);
    features.push_back(baseline.scorer_raw_score);
    features.push_back(
        static_cast<double>(recent_visit_count(bag,
                                               intervention.next_node)));
    features.push_back(repeat_count);
    features.push_back(storage_in ? 1.0 : 0.0);
    features.push_back(storage_out ? 1.0 : 0.0);
    features.push_back(direct ? 1.0 : 0.0);
    features.push_back(std::sin(radians));
    features.push_back(std::cos(radians));
    features.push_back(1.0);  // frozen F2 baseline releases at this boundary
    features.push_back(intervention.advertised_fault ? 1.0 : 0.0);
    if (features.size() != kG4IRSF16DeploymentFeatureCount) {
      throw std::logic_error("G4IRSF16 deployment feature order drifted");
    }
    return features;
  }

  EventCandidateRecord candidate_record(const BagState& bag,
                                        int current,
                                        int candidate,
                                        double time,
                                        bool escape_active,
                                        bool first_edge_credit_required,
                                        bool first_edge_credit_ready,
                                        int first_edge_credit_to) {
    EventCandidateRecord record;
    record.next_node = candidate;
    const auto& edge = graph_.edge(current, candidate);
    record.travel_time = std::max(edge.travel_time(), config_.minimum_service_seconds);
    record.static_potential = static_potential(candidate, bag.request.goal);

    auto& current_controller = junctions_[current];
    auto& target = junctions_[candidate];
    target.service_calendar.purge(time);
    target.observe_local_state();
    record.target_queue_length = static_cast<int>(target.queue.size());
    record.target_scheduled_incoming = target.scheduled_incoming;
    record.corridor_next_available = time;
    if (uses_corridor_calendar()) {
      auto& corridor = corridors_[resource_corridor_key(current, candidate)];
      corridor.purge(time);
      record.corridor_next_available =
          corridor.earliest_start(time,
                                  corridor_reservation_duration(record.travel_time));
    }
    const double service = service_duration(candidate);
    record.target_next_available = time + record.travel_time;
    if (uses_destination_calendar(candidate,
                                  bag.request.goal) &&
        !(uses_destination_merge_grants() &&
          graph_.incoming_degree(candidate) > 1 &&
          candidate != bag.request.goal)) {
      record.target_next_available =
          target.service_calendar.earliest_start(time + record.travel_time, service);
    }

    const auto current_goal = goal_queue_state(current_controller,
                                               bag.request.goal,
                                               time);
    const auto target_goal = goal_queue_state(target, bag.request.goal, time);
    record.current_goal_queue_length = current_goal.first;
    record.current_goal_max_wait = current_goal.second;
    record.target_goal_queue_length = target_goal.first;
    const auto target_incoming =
        target.scheduled_incoming_by_goal.find(bag.request.goal);
    record.target_goal_scheduled_incoming =
        target_incoming == target.scheduled_incoming_by_goal.end()
            ? 0
            : target_incoming->second;
    const double age_term = config_.pressure_age_weight *
                            record.current_goal_max_wait;
    record.goal_conditioned_differential =
        static_cast<double>(record.current_goal_queue_length) + age_term -
        static_cast<double>(record.target_goal_queue_length +
                            record.target_goal_scheduled_incoming);
    const double corridor_service =
        uses_corridor_calendar()
            ? corridor_reservation_duration(record.travel_time)
            : config_.minimum_service_seconds;
    const double destination_service =
        uses_destination_calendar(candidate,
                                  bag.request.goal)
            ? service
            : config_.minimum_service_seconds;
    record.estimated_service_rate =
        1.0 / std::max({config_.minimum_service_seconds,
                        corridor_service,
                        destination_service});
    record.service_weighted_pressure =
        record.goal_conditioned_differential * record.estimated_service_rate;
    record.first_edge_credit_required = first_edge_credit_required;
    record.first_edge_credit_matches =
        first_edge_credit_required && candidate == first_edge_credit_to;
    record.first_edge_credit_valid =
        record.first_edge_credit_matches && first_edge_credit_ready;
    if (record.first_edge_credit_valid) {
      const auto* credit = credit_ledger_.find(bag.first_edge_credit_id);
      if (credit != nullptr) {
        record.first_edge_credit_slack_seconds =
            std::max(0.0, std::min(credit->latest, credit->expiry) - time);
      }
    }

    const long long edge_key = event_runtime_detail::directed_key(current, candidate);
    const auto advertised = advertised_faults_.find(edge_key);
    if (config_.enable_fault_policy && advertised != advertised_faults_.end()) {
      record.advertised_fault = advertised->second.faulted;
      record.fault_message_age_seconds = std::max(0.0, time - advertised->second.received_at);
    }
    record.recent_visit_count = recent_visit_count(bag, candidate);
    if (config_.diagnostic_hops >= 2) {
      for (const int downstream : graph_.outgoing(candidate)) {
        const auto found = junctions_.find(downstream);
        if (found != junctions_.end()) {
          record.two_hop_queue_pressure += static_cast<int>(found->second.queue.size()) +
                                           found->second.scheduled_incoming;
        }
      }
    }

    const double corridor_wait = std::max(0.0, record.corridor_next_available - time);
    const double target_wait =
        std::max(0.0, record.target_next_available - (time + record.travel_time));
    const double absolute_pressure =
        static_cast<double>(record.target_queue_length +
                            record.target_scheduled_incoming);
    double pressure_cost = 0.0;
    const auto pressure_mode = canonical_pressure_mode();
    if (pressure_mode == "C1_absolute_downstream_queue_penalty") {
      pressure_cost = config_.pressure_weight * absolute_pressure;
    } else if (pressure_mode == "C2_goal_conditioned_differential" ||
               pressure_mode == "C3_distance_biased_differential") {
      pressure_cost = -config_.pressure_weight *
                      std::max(0.0, record.service_weighted_pressure);
      if (pressure_mode == "C3_distance_biased_differential") {
        pressure_cost += config_.pressure_distance_bias *
                         record.static_potential;
      }
    }
    record.pre_fault_policy_score =
        record.static_potential + record.travel_time +
        config_.calendar_wait_weight * (corridor_wait + target_wait) +
        pressure_cost +
        config_.history_penalty * static_cast<double>(record.recent_visit_count);
    if (bag.history.size() >= 2 && candidate == bag.history[bag.history.size() - 2]) {
      record.pre_fault_policy_score += config_.backtrack_penalty;
    }
    if (escape_active) {
      // The escape token changes only local priority.  It never bypasses the
      // physical shield or reserves more than one edge.
      record.pre_fault_policy_score -= 0.5 * config_.history_penalty;
    }
    record.model_score = record.pre_fault_policy_score;
    if (config_.enable_fault_policy && record.advertised_fault) {
      record.model_score += 1.0e12;
    }

    record.shield_reason = shield_reason(bag,
                                         current,
                                         candidate,
                                         time,
                                         first_edge_credit_required,
                                         first_edge_credit_ready,
                                         first_edge_credit_to);
    record.shield_allowed = record.shield_reason == "allowed";
    return record;
  }

  std::string shield_reason(const BagState& bag,
                            int current,
                            int candidate,
                            double time,
                            bool first_edge_credit_required,
                            bool first_edge_credit_ready,
                            int first_edge_credit_to) {
    // A terminal node is safe only when it is this bag's actual goal.  This
    // is a one-hop topology check on the candidate itself: it needs neither
    // a future route nor a global search, and prevents local backpressure from
    // diverting traffic into another terminal sink under high concurrency.
    if (candidate != bag.request.goal && graph_.outgoing(candidate).empty()) {
      return "dead_end_not_goal";
    }
    const auto& candidate_outgoing = graph_.outgoing(candidate);
    if (candidate != bag.request.goal && !candidate_outgoing.empty() &&
        std::all_of(candidate_outgoing.begin(),
                    candidate_outgoing.end(),
                    [&](int successor) {
                      return successor != bag.request.goal &&
                             graph_.outgoing(successor).empty();
                    })) {
      return "terminal_successor_trap_not_goal";
    }

    const long long directed = event_runtime_detail::directed_key(current, candidate);
    const auto physical = physical_faults_.find(directed);
    if (physical != physical_faults_.end() && physical->second.active_count > 0) {
      return "physical_fault";
    }

    if (first_edge_credit_required) {
      if (!first_edge_credit_ready) {
        return "first_edge_credit_unavailable";
      }
      if (candidate != first_edge_credit_to) {
        return "first_edge_credit_mismatch";
      }
    }

    const auto& edge = graph_.edge(current, candidate);
    const double travel = std::max(edge.travel_time(), config_.minimum_service_seconds);
    if (uses_corridor_calendar()) {
      auto& corridor = corridors_[resource_corridor_key(current, candidate)];
      corridor.purge(time);
      if (!corridor.available(
              time,
              time + corridor_reservation_duration(travel),
              bag.request.runtime_bag_id)) {
        return "corridor_busy";
      }
    }

    if (uses_destination_merge_grants() &&
        graph_.incoming_degree(candidate) > 1 &&
        candidate != bag.request.goal) {
      // E4 route selection publishes a request for the exact current slot.
      // Calendar/queue contention is decided by the destination in phase 5b,
      // never converted into an upstream alternate-edge/PIBT handoff.
      return "allowed";
    }

    auto& target = junctions_[candidate];
    target.service_calendar.purge(time);
    target.observe_local_state();
    const double service_start = time + travel;
    const double service_end = service_start + service_duration(candidate);
    if (uses_destination_calendar(candidate,
                                  bag.request.goal) &&
        !target.service_calendar.available(service_start,
                                            service_end,
                                            bag.request.runtime_bag_id)) {
      return "destination_calendar_busy";
    }
    if (config_.local_queue_capacity > 0 && candidate != bag.request.goal &&
        static_cast<int>(target.queue.size()) + target.scheduled_incoming >=
            config_.local_queue_capacity) {
      return "destination_queue_full";
    }
    return "allowed";
  }

  void dispatch_selected_edge(
      BagState& bag,
      int current,
      int selected,
      double time,
      PIBTActionDelta* transaction_delta = nullptr,
      const MergeGrantCapability*
          destination_merge_grant_authority = nullptr) {
    const auto& edge = graph_.edge(current, selected);
    const double travel = std::max(edge.travel_time(), config_.minimum_service_seconds);
    const double exit_time = time + travel;
    const double service_end = exit_time + service_duration(selected);
    auto& target = junctions_[selected];
    LocalCalendar* corridor = nullptr;
    const double corridor_end =
        time + corridor_reservation_duration(travel);
    if (uses_corridor_calendar()) {
      corridor = &corridors_[resource_corridor_key(current, selected)];
      corridor->purge(time);
    }
    const bool corridor_available =
        corridor == nullptr ||
        corridor->available(time, corridor_end, bag.request.runtime_bag_id);
    const bool destination_available =
        !uses_destination_calendar(selected,
                                   bag.request.goal) ||
        target.service_calendar.available(exit_time,
                                           service_end,
                                           bag.request.runtime_bag_id);
    const long long physical_key =
        event_runtime_detail::directed_key(current, selected);
    const auto physical_before =
        physical_faults_.find(physical_key);
    const int physical_generation_before =
        physical_before == physical_faults_.end()
            ? 0
            : physical_before->second.physical_generation;
    const bool physically_faulted_before =
        physical_before != physical_faults_.end() &&
        physical_before->second.active_count > 0;
    const auto physical_commit =
        physical_faults_.find(physical_key);
    const int physical_generation_commit =
        physical_commit == physical_faults_.end()
            ? 0
            : physical_commit->second.physical_generation;
    const bool physically_faulted_commit =
        physical_commit != physical_faults_.end() &&
        physical_commit->second.active_count > 0;
    if (g4irsf14_extensions_enabled()) {
      ++result_.summary
            .fault_generation_commit_recheck_count;
    }
    if (!corridor_available || !destination_available ||
        physically_faulted_before ||
        physically_faulted_commit ||
        physical_generation_before !=
            physical_generation_commit) {
      ++result_.summary.reservation_conflicts;
      throw std::logic_error("local shield/reservation state diverged");
    }
    append_merge_visibility(bag,
                            current,
                            selected,
                            time,
                            exit_time,
                            service_end);
    if (corridor != nullptr) {
      if (transaction_delta != nullptr) {
        transaction_delta->corridor_generation_before =
            corridor->generation();
      }
      corridor->reserve(bag.request.runtime_bag_id, time, corridor_end);
      if (transaction_delta != nullptr) {
        transaction_delta->corridor_reservation_inserted =
            true;
      }
    }
    if (uses_destination_calendar(selected,
                                  bag.request.goal)) {
      if (destination_merge_grant_authority == nullptr) {
        if (transaction_delta != nullptr) {
          transaction_delta
              ->destination_generation_before =
              target.service_calendar.generation();
        }
        target.service_calendar.reserve(bag.request.runtime_bag_id, exit_time, service_end);
        if (transaction_delta != nullptr) {
          transaction_delta->destination_reservation_inserted =
              true;
        }
      }
      target.record_service_reservation(exit_time, service_end);
    }
    ++target.scheduled_incoming;
    ++target.scheduled_incoming_by_goal[bag.request.goal];
    if (transaction_delta != nullptr) {
      transaction_delta->destination_goal_incremented =
          true;
    }
    update_calendar_maxima(target, corridor);
    schedule_passive(JunctionEventType::kCongestionBeaconUpdate,
                     time,
                     bag.request.runtime_bag_id,
                     selected,
                     current,
                     selected,
                     "incoming_reservation_snapshot");

    // Keep the legacy total_wait update byte-for-byte equivalent because it
    // is an existing PIBT-priority input. The new accumulator is observational
    // only and repeats the same dequeue interval independently.
    bag.total_wait += std::max(0.0, time - bag.junction_enqueued_at);
    bag.junction_queue_wait_seconds +=
        std::max(0.0, time - bag.junction_enqueued_at);
    bag.status = BagStatus::kInTransit;
    bag.transit_from = current;
    bag.transit_to = selected;
    bag.transit_merge_grant =
        destination_merge_grant_authority == nullptr
            ? DestinationMergeGrantExpectation{}
            : destination_merge_grant_authority
                  ->expectation();
    schedule_passive(JunctionEventType::kEdgeEnter,
                     time,
                     bag.request.runtime_bag_id,
                     current,
                     current,
                     selected,
                     "one_step_reservation_committed");
    schedule(JunctionEventType::kEdgeExit,
             exit_time,
             bag.request.runtime_bag_id,
             selected,
             current,
             selected,
             false,
             0,
             service_end);
  }

  void process_edge_enter(const RuntimeEvent& event) {
    const auto found = bags_.find(event.task_id);
    const bool valid_entry =
        found != bags_.end() && found->second.status == BagStatus::kInTransit &&
        found->second.transit_from == event.from_node &&
        found->second.transit_to == event.to_node;
    if (valid_entry) {
      const long long key =
          event_runtime_detail::directed_key(event.from_node, event.to_node);
      const int inflight = ++directed_inflight_counts_[key];
      result_.summary.max_same_directed_edge_inflight =
          std::max(result_.summary.max_same_directed_edge_inflight, inflight);
      const auto physical = physical_faults_.find(key);
      if (physical != physical_faults_.end() && physical->second.active_count > 0) {
        ++result_.summary.physical_fault_edge_entry_violation_count;
        append_fault_audit(event,
                           "unsafe_edge_entry",
                           physical->second.active_count,
                           physical->second.physical_generation,
                           0,
                           false);
      }
      if (uses_destination_merge_grants() &&
          found->second.transit_merge_grant.required) {
        auto& merge_state = destination_merge_bag_state(
            found->second.request.runtime_bag_id);
        const auto& expected = found->second.transit_merge_grant;
        const auto advertised = advertised_faults_.find(key);
        const int physical_generation =
            physical == physical_faults_.end()
                ? 0
                : physical->second.physical_generation;
        const int advertised_generation =
            advertised == advertised_faults_.end()
                ? 0
                : advertised->second.generation;
        const auto controller =
            destination_merge_controllers_.find(expected.destination_node);
        // This is the only minting point for the recovery proof.  It binds
        // the real in-transit bag, exact edge, live unique capability,
        // controller record, healthy physical entry, and both original fault
        // generations before any later fault can occur.
        merge_state.exact_grant_edge_entry_observed =
            (physical == physical_faults_.end() ||
             physical->second.active_count == 0) &&
            physical_generation == expected.physical_fault_generation &&
            advertised_generation == expected.advertised_fault_generation &&
            merge_state.capability.has_value() &&
            merge_state.capability->expectation() == expected &&
            controller != destination_merge_controllers_.end() &&
            controller->second.validates_active_capability(
                *merge_state.capability);
      }
    }
    process_passive_event(event, "one_step_corridor_entry");
  }

  void process_edge_exit(const RuntimeEvent& event) {
    auto found = bags_.find(event.task_id);
    if (found == bags_.end() || found->second.status != BagStatus::kInTransit ||
        found->second.transit_from != event.from_node ||
        found->second.transit_to != event.to_node) {
      return;
    }
    auto& bag = found->second;
    bool inflight_fault_generation_recovered = false;
    const long long directed =
        event_runtime_detail::directed_key(event.from_node, event.to_node);
    const auto inflight = directed_inflight_counts_.find(directed);
    if (inflight != directed_inflight_counts_.end()) {
      inflight->second = std::max(0, inflight->second - 1);
      if (inflight->second == 0) {
        directed_inflight_counts_.erase(inflight);
      }
    }
    if (uses_destination_merge_grants()) {
      auto& merge_state =
          destination_merge_bag_state(
              bag.request.runtime_bag_id);
      const auto stored_expected =
          bag.transit_merge_grant;
      auto expected = stored_expected;
#ifdef CZR005_EVENT_RUNTIME_TESTING
      if (expected.required &&
          config_
              .test_merge_grant_drop_capability_before_edge_exit &&
          !test_merge_grant_edge_exit_capability_drop_injected_) {
        test_merge_grant_edge_exit_capability_drop_injected_ =
            true;
        merge_state.capability.reset();
      }
      if (expected.required &&
          config_
              .test_merge_grant_flip_physical_generation_before_edge_exit &&
          !test_merge_grant_edge_exit_physical_flip_injected_) {
        test_merge_grant_edge_exit_physical_flip_injected_ =
            true;
        ++physical_faults_
              .try_emplace(directed)
              .first->second.physical_generation;
      }
      if (expected.required &&
          config_
              .test_merge_grant_flip_advertised_generation_before_edge_exit &&
          !test_merge_grant_edge_exit_advertised_flip_injected_) {
        test_merge_grant_edge_exit_advertised_flip_injected_ =
            true;
        ++advertised_faults_
              .try_emplace(directed)
              .first->second.generation;
      }
      if (expected.required &&
          config_
              .test_merge_grant_remove_calendar_before_edge_exit &&
          !test_merge_grant_edge_exit_calendar_remove_injected_) {
        test_merge_grant_edge_exit_calendar_remove_injected_ =
            true;
        auto destination =
            junctions_.find(expected.destination_node);
        if (destination != junctions_.end()) {
          destination->second.service_calendar.erase_exact(
              expected.owner_runtime_bag_id,
              expected.slot_start,
              expected.slot_end);
        }
      }
      if (expected.required &&
          config_
              .test_merge_grant_wrong_owner_before_edge_exit &&
          !test_merge_grant_edge_exit_wrong_owner_injected_) {
        test_merge_grant_edge_exit_wrong_owner_injected_ =
            true;
        ++expected.owner_runtime_bag_id;
      }
      if (expected.required &&
          config_
              .test_merge_grant_wrong_edge_before_edge_exit &&
          !test_merge_grant_edge_exit_wrong_edge_injected_) {
        test_merge_grant_edge_exit_wrong_edge_injected_ =
            true;
        ++expected.edge.from_node;
      }
      if (expected.required &&
          config_
              .test_merge_grant_wrong_destination_before_edge_exit &&
          !test_merge_grant_edge_exit_wrong_destination_injected_) {
        test_merge_grant_edge_exit_wrong_destination_injected_ =
            true;
        (void)destination_merge_controller(
            expected.destination_node + 1);
        ++expected.destination_node;
      }
      if (expected.required &&
          config_
              .test_merge_grant_tamper_claimed_request_generation_before_edge_exit &&
          !test_merge_grant_edge_exit_claimed_request_generation_tamper_injected_) {
        test_merge_grant_edge_exit_claimed_request_generation_tamper_injected_ =
            true;
        ++expected.request_generation;
      }
      if (expected.required &&
          config_
              .test_merge_grant_tamper_claimed_queue_generation_before_edge_exit &&
          !test_merge_grant_edge_exit_claimed_queue_generation_tamper_injected_) {
        test_merge_grant_edge_exit_claimed_queue_generation_tamper_injected_ =
            true;
        ++expected.junction_queue_generation;
      }
      if (expected.required &&
          config_
              .test_merge_grant_tamper_claimed_calendar_generation_before_edge_exit &&
          !test_merge_grant_edge_exit_claimed_calendar_generation_tamper_injected_) {
        test_merge_grant_edge_exit_claimed_calendar_generation_tamper_injected_ =
            true;
        ++expected.calendar_generation;
      }
      if (expected.required &&
          config_
              .test_merge_grant_advance_live_queue_generation_before_edge_exit &&
          !test_merge_grant_edge_exit_live_queue_generation_advance_injected_) {
        test_merge_grant_edge_exit_live_queue_generation_advance_injected_ =
            true;
        ++merge_state.junction_queue_generation;
      }
      if (expected.required &&
          config_
              .test_merge_grant_advance_live_calendar_generation_before_edge_exit &&
          !test_merge_grant_edge_exit_live_calendar_generation_advance_injected_) {
        test_merge_grant_edge_exit_live_calendar_generation_advance_injected_ =
            true;
        auto destination =
            junctions_.find(expected.destination_node);
        if (destination != junctions_.end()) {
          // Simulate an unrelated aggregate-calendar epoch advance without
          // disturbing the stable exact(owner, slot) lease.
          destination->second.service_calendar
              .test_advance_generation();
        }
      }
#endif
      const bool unexpected_capability =
          !expected.required &&
          merge_state.capability.has_value();
      if (expected.required || unexpected_capability) {
        auto cleanup_expected = stored_expected;
        if (unexpected_capability) {
          cleanup_expected =
              merge_state.capability->expectation();
          expected =
              cleanup_expected;
          expected.required = false;
        }
        DestinationMergeGrantConsumeContext context;
        context.expected = expected;
        context.event_owner_runtime_bag_id =
            bag.request.runtime_bag_id;
        context.event_edge =
            MergeDirectedEdge{event.from_node,
                              event.to_node};
        context.event_destination_node =
            event.to_node;
        context.current_junction_queue_generation =
            merge_state.junction_queue_generation;
#ifdef CZR005_EVENT_RUNTIME_TESTING
        context.now =
            expected.required &&
                    config_
                        .test_merge_grant_expire_before_edge_exit &&
                    !test_merge_grant_edge_exit_expiry_injected_
                ? (test_merge_grant_edge_exit_expiry_injected_ =
                       true,
                   expected.expiry +
                       2.0 *
                           event_runtime_detail::kEpsilon)
                : event.time;
#else
        context.now = event.time;
#endif
        const auto physical =
            physical_faults_.find(directed);
        context.physical_fault_active =
            physical != physical_faults_.end() &&
            physical->second.active_count > 0;
        context.current_physical_fault_generation =
            physical == physical_faults_.end()
                ? 0
                : physical->second.physical_generation;
        const auto advertised =
            advertised_faults_.find(directed);
        context.current_advertised_fault_generation =
            advertised == advertised_faults_.end()
                ? 0
                : advertised->second.generation;
        context.exact_grant_edge_entry_observed =
            merge_state.exact_grant_edge_entry_observed;
        context.local_inflight_fault_instance_observed =
            local_inflight_fault_instance_observed(
                directed,
                expected.physical_fault_generation,
                context.current_physical_fault_generation);
        const auto destination =
            junctions_.find(expected.destination_node);
        context.current_calendar_generation =
            destination == junctions_.end()
                ? 0
                : destination->second
                      .service_calendar.generation();
        context
            .exact_destination_calendar_reservation_present =
            destination != junctions_.end() &&
            destination->second.service_calendar.contains_exact(
                expected.owner_runtime_bag_id,
                expected.slot_start,
                expected.slot_end);
        auto controller =
            destination_merge_controllers_.find(
                cleanup_expected.destination_node);
        const auto consumed =
            controller ==
                    destination_merge_controllers_.end()
                ? DestinationMergeGrantConsumeResult::
                      kActiveGrantMissing
                : controller->second.consume_noexcept(
                      merge_state.capability.has_value()
                          ? &*merge_state.capability
                          : nullptr,
                      context);
        inflight_fault_generation_recovered =
            consumed == DestinationMergeGrantConsumeResult::
                            kConsumedAfterInflightFaultGenerationChange;
        if (inflight_fault_generation_recovered) {
          mark_inflight_fault_generation_recovery(
              bag,
              directed,
              expected.physical_fault_generation,
              context.current_physical_fault_generation,
              context.physical_fault_active);
          append_fault_audit(
              event,
              "destination_merge_inflight_fault_generation_recovered",
              physical == physical_faults_.end()
                  ? 0
                  : physical->second.active_count,
              context.current_physical_fault_generation,
              1,
              false);
        }
        merge_state.capability.reset();
        merge_state.exact_grant_edge_entry_observed = false;
        bag.transit_merge_grant = {};
        if (consumed !=
                DestinationMergeGrantConsumeResult::kConsumed &&
            !inflight_fault_generation_recovered) {
          auto target = junctions_.find(event.to_node);
          if (target != junctions_.end()) {
            target->second.service_calendar.erase_exact(
                bag.request.runtime_bag_id,
                cleanup_expected.slot_start,
                cleanup_expected.slot_end);
            if (target->second.scheduled_incoming > 0) {
              --target->second.scheduled_incoming;
            }
            auto by_goal =
                target->second
                    .scheduled_incoming_by_goal.find(
                        bag.request.goal);
            if (by_goal !=
                target->second
                    .scheduled_incoming_by_goal.end()) {
              by_goal->second =
                  std::max(0, by_goal->second - 1);
              if (by_goal->second == 0) {
                target->second
                    .scheduled_incoming_by_goal.erase(
                        by_goal);
              }
            }
          }
          bag.current = event.to_node;
          const double executed_travel =
              std::max(
                  graph_
                      .edge(event.from_node,
                            event.to_node)
                      .travel_time(),
                  config_.minimum_service_seconds);
          bag.edge_travel_time_seconds +=
              executed_travel;
          bag.transit_from = -1;
          bag.transit_to = -1;
          fail_bag(
              bag,
              "destination_merge_grant_rejected_at_edge_exit",
              event.time);
          schedule_junction_wakeup(
              event.from_node, event.time);
          schedule_passive(
              JunctionEventType::kCongestionBeaconUpdate,
              event.time,
              event.task_id,
              event.to_node,
              event.from_node,
              event.to_node,
              "merge_grant_edge_exit_rejected");
          append_event_trace(
              event,
              event.task_id,
              event.to_node,
              event.from_node,
              event.to_node,
              "merge_grant_edge_exit_rejected",
              0);
          return;
        }
      }
    }
    bag.transit_merge_grant = {};
    bag.current = event.to_node;
    const double executed_travel =
        std::max(graph_.edge(event.from_node, event.to_node).travel_time(),
                 config_.minimum_service_seconds);
    bag.edge_travel_time_seconds += executed_travel;
    if (recent_visit_count(bag, event.to_node) > 0) {
      // This is deliberately a subset of travel rather than a second
      // additive duration component. The destination must have been observed
      // before this valid EDGE_EXIT in the bounded runtime history.
      bag.loop_extra_time_seconds += executed_travel;
    }
    bag.status = BagStatus::kInService;
    schedule(JunctionEventType::kJunctionServiceComplete,
             event.service_end,
             event.task_id,
             event.to_node,
             event.from_node,
             event.to_node);
    schedule_junction_wakeup(event.from_node, event.time);
    append_event_trace(event,
                       event.task_id,
                       event.to_node,
                       event.from_node,
                       event.to_node,
                       inflight_fault_generation_recovered
                           ? "edge_traversal_complete_after_inflight_fault_generation_recovery"
                           : "edge_traversal_complete",
                       0);
  }

  void process_local_queue_update(const RuntimeEvent& event) {
    append_event_trace(event,
                       event.task_id,
                       event.node,
                       event.from_node,
                       event.to_node,
                       event.reason.empty() ? "local_queue_change" : event.reason,
                       0);
    schedule_passive(JunctionEventType::kCongestionBeaconUpdate,
                     event.time,
                     event.task_id,
                     event.node,
                     event.from_node,
                     event.to_node,
                     "queue_change_beacon");
  }

  void process_congestion_beacon_update(const RuntimeEvent& event) {
    auto& controller = junctions_[event.node];
    controller.service_calendar.purge(event.time);
    controller.observe_local_state();
    auto& beacon = congestion_beacons_[event.node];
    const int previous_pressure =
        beacon.queue_length + beacon.scheduled_incoming;
    const double previous_received_at = beacon.received_at;
    const bool had_previous_snapshot = beacon.generation > 0;
    beacon.queue_length = static_cast<int>(controller.queue.size());
    beacon.scheduled_incoming = controller.scheduled_incoming;
    beacon.queue_length_by_goal.clear();
    for (const int runtime_bag_id : controller.queue) {
      const auto found = bags_.find(runtime_bag_id);
      if (found != bags_.end()) {
        ++beacon.queue_length_by_goal[found->second.request.goal];
      }
    }
    beacon.scheduled_incoming_by_goal =
        controller.scheduled_incoming_by_goal;
    beacon.service_calendar_reserved_until =
        controller.service_calendar.reserved_until(event.time);
    if (g4irsf17_extensions_enabled()) {
      beacon.g4irsf17_local_blocker =
          controller.g4irsf17_local_blocker;
      beacon.g4irsf17_estimated_service_rate_60s =
          static_cast<double>(
              controller.g4irsf17_source_temporal
                  .service_completions.count(event.time, 60.0)) /
          60.0;
      const int current_pressure =
          beacon.queue_length + beacon.scheduled_incoming;
      const double elapsed = event.time - previous_received_at;
      beacon.g4irsf17_drain_slope_60s =
          had_previous_snapshot && elapsed > event_runtime_detail::kEpsilon &&
                  elapsed <= 60.0 + event_runtime_detail::kEpsilon
              ? static_cast<double>(previous_pressure - current_pressure) /
                    elapsed
              : 0.0;
      beacon.g4irsf17_one_hop_ttl_pressure = 0.0;
      auto outgoing = graph_.outgoing(event.node);
      std::sort(outgoing.begin(), outgoing.end());
      if (outgoing.size() > 4U) {
        outgoing.resize(4U);
      }
      for (const int downstream : outgoing) {
        const auto local = congestion_beacons_.find(downstream);
        if (local == congestion_beacons_.end() ||
            event.time - local->second.received_at >
                60.0 + event_runtime_detail::kEpsilon) {
          continue;
        }
        beacon.g4irsf17_one_hop_ttl_pressure = std::max(
            beacon.g4irsf17_one_hop_ttl_pressure,
            static_cast<double>(local->second.queue_length +
                                local->second.scheduled_incoming));
      }
      const auto merge =
          destination_merge_controllers_.find(event.node);
      if (merge == destination_merge_controllers_.end()) {
        beacon.g4irsf17_merge_pending_request_count = 0;
        beacon.g4irsf17_merge_active_grant_count = 0;
        beacon.g4irsf17_merge_generation = 0;
        beacon.g4irsf17_merge_oldest_request_age_seconds = 0.0;
        beacon.g4irsf17_recent_incoming_grants_60s = 0.0;
        beacon.g4irsf17_incoming_grant_imbalance_60s = 0.0;
      } else {
        beacon.g4irsf17_merge_pending_request_count =
            static_cast<int>(merge->second.pending_count());
        beacon.g4irsf17_merge_active_grant_count =
            static_cast<int>(
                merge->second.active_unconsumed_count());
        beacon.g4irsf17_merge_generation =
            merge->second.generation();
        beacon.g4irsf17_merge_oldest_request_age_seconds =
            merge->second.oldest_pending_age(event.time);
        beacon.g4irsf17_recent_incoming_grants_60s =
            static_cast<double>(
                merge->second.recent_incoming_grants(event.time));
        beacon.g4irsf17_incoming_grant_imbalance_60s =
            static_cast<double>(
                merge->second.recent_incoming_grant_imbalance(event.time));
      }
    }
    beacon.received_at = event.time;
    ++beacon.generation;
    if (uses_first_edge_credit()) {
      credit_ledger_.revoke_destination_generation(event.node,
                                                   beacon.generation,
                                                   event.time);
    }
    append_event_trace(event,
                       event.task_id,
                       event.node,
                       event.from_node,
                       event.to_node,
                       event.reason.empty() ? "bounded_local_congestion_summary"
                                             : event.reason,
                       0);
    if (uses_jit_destination_merge_grants()) {
      const auto merge =
          destination_merge_controllers_.find(event.node);
      if (merge != destination_merge_controllers_.end() &&
          merge->second.pending_count() > 0) {
        schedule_next_jit_destination_merge_opportunity(
            merge->second, event.time, true);
      }
    }
  }

  void process_passive_event(const RuntimeEvent& event, const std::string& default_reason) {
    append_event_trace(event,
                       event.task_id,
                       event.node,
                       event.from_node,
                       event.to_node,
                       event.reason.empty() ? default_reason : event.reason,
                       0);
  }

  void schedule_passive(JunctionEventType type,
                        double time,
                        int task_id,
                        int node,
                        int from_node,
                        int to_node,
                        const std::string& reason) {
    RuntimeEvent event;
    event.type = type;
    event.time = time;
    event.task_id = task_id;
    event.node = node;
    event.from_node = from_node;
    event.to_node = to_node;
    event.reason = reason;
    push_event(std::move(event));
  }

  void process_fault_message(const RuntimeEvent& event) {
    const long long key = event_runtime_detail::directed_key(event.from_node, event.to_node);
    if (event.notification) {
      if (config_.enable_fault_policy) {
        auto& advertised = advertised_faults_[key];
        if (event.message_generation >= advertised.generation) {
          advertised.generation = event.message_generation;
          advertised.faulted = event.type == JunctionEventType::kFault;
          advertised.received_at = event.time;
        }
        schedule_junction_wakeup(event.from_node, event.time);
      }
      append_event_trace(event,
                         -1,
                         event.from_node,
                         event.from_node,
                         event.to_node,
                         "local_message_delivery",
                         0);
      const auto physical = physical_faults_.find(key);
      append_fault_audit(event,
                         "local_message_delivery",
                         physical == physical_faults_.end() ? 0 : physical->second.active_count,
                         event.message_generation,
                         0,
                         false);
      if (uses_jit_destination_merge_grants()) {
        const auto merge =
            destination_merge_controllers_.find(event.to_node);
        if (merge != destination_merge_controllers_.end() &&
            merge->second.pending_count() > 0) {
          schedule_destination_merge_wakeup(
              event.to_node, event.time);
        }
      }
      return;
    }

    auto& physical = physical_faults_[key];
    const bool starts_new_fault_instance =
        event.type == JunctionEventType::kFault &&
        physical.active_count == 0;
    if (event.type == JunctionEventType::kFault) {
      ++physical.active_count;
    } else {
      physical.active_count = std::max(0, physical.active_count - 1);
    }
    ++physical.physical_generation;
    if (starts_new_fault_instance) {
      active_fault_instance_by_edge_[key] =
          physical.physical_generation;
      // A new unresolved fault window invalidates any older repair-to-stop
      // backlog baseline.
      last_physical_repair_time_ = -1.0;
      active_backlog_at_last_repair_ = -1;
    }
    if (event.type == JunctionEventType::kRepair &&
        physical.active_count == 0) {
      const auto instance = active_fault_instance_by_edge_.find(key);
      if (instance != active_fault_instance_by_edge_.end()) {
        repair_time_by_fault_instance_[
            {key, instance->second}] = event.time;
        active_fault_instance_by_edge_.erase(instance);
      }
      last_physical_repair_time_ = event.time;
      active_backlog_at_last_repair_ = active_bag_count_;
      const auto affected =
          fault_affected_bags_by_edge_.find(key);
      if (affected != fault_affected_bags_by_edge_.end()) {
        for (const int runtime_bag_id : affected->second) {
          auto bag = bags_.find(runtime_bag_id);
          if (bag == bags_.end() ||
              bag->second.status == BagStatus::kCompleted ||
              bag->second.status == BagStatus::kFailed ||
              bag->second.repaired_task_reentry) {
            continue;
          }
          bag->second.repaired_task_reentry = true;
          bag->second.fault_priority_generation =
              std::max(
                  bag->second.fault_priority_generation,
                  static_cast<std::uint64_t>(
                      physical.physical_generation));
          if (g4irsf16_enabled()) {
            auto& generation =
                g4irsf16_physical_fault_generation_by_bag_[
                    bag->second.request.runtime_bag_id];
            generation = std::max(
                generation,
                static_cast<std::uint64_t>(
                    std::max(0, physical.physical_generation)));
          }
          bag->second.local_enqueue_sequence =
              next_local_enqueue_sequence_++;
          ++result_.summary.repaired_task_reentry_count;
          if (bag->second.status == BagStatus::kJunctionQueue) {
            schedule_junction_wakeup(
                bag->second.current, event.time);
          } else if (bag->second.status ==
                     BagStatus::kSourceQueue) {
            schedule_source_wakeup(
                bag->second.request.start, event.time);
          }
        }
      }
    }
    if (uses_first_edge_credit()) {
      credit_ledger_.revoke_edge_fault_generation(
          event.from_node,
          event.to_node,
          physical.physical_generation,
          physical.active_count > 0,
          event.time);
    }
    int inflight_traversals = 0;
    if (event.type == JunctionEventType::kFault) {
      const auto inflight = directed_inflight_counts_.find(key);
      if (inflight != directed_inflight_counts_.end()) {
        inflight_traversals = inflight->second;
      }
      result_.summary.physical_fault_window_traversal_count += inflight_traversals;
    }
    append_fault_audit(event,
                       "physical_state_change",
                       physical.active_count,
                       physical.physical_generation,
                       inflight_traversals,
                       event.drop_notification);
    if (event.drop_notification) {
      ++result_.summary.fault_notification_drop_count;
      result_.summary.sensor_loss_mode_used = true;
      append_fault_audit(event,
                         "notification_dropped",
                         physical.active_count,
                         physical.physical_generation,
                         0,
                         true);
    } else if (
        event.message_delay <= event_runtime_detail::kEpsilon &&
        canonical_event_semantics() !=
            "E3_batch_source_and_junction_same_timestamp") {
      if (config_.enable_fault_policy) {
        auto& advertised = advertised_faults_[key];
        advertised.generation = physical.physical_generation;
        advertised.faulted = physical.active_count > 0;
        advertised.received_at = event.time;
      }
      append_fault_audit(event,
                         "local_message_delivery",
                         physical.active_count,
                         physical.physical_generation,
                         0,
                         false);
    } else {
      RuntimeEvent notification = event;
      notification.time =
          event.message_delay <= event_runtime_detail::kEpsilon
              ? event.time
              : event.time + event.message_delay;
      notification.notification = true;
      notification.message_generation = physical.physical_generation;
      notification.type = physical.active_count > 0 ? JunctionEventType::kFault
                                                     : JunctionEventType::kRepair;
      push_event(std::move(notification));
    }
    schedule_junction_wakeup(event.from_node, event.time);
    if (uses_jit_destination_merge_grants()) {
      const auto merge =
          destination_merge_controllers_.find(event.to_node);
      if (merge != destination_merge_controllers_.end() &&
          merge->second.pending_count() > 0) {
        schedule_destination_merge_wakeup(
            event.to_node, event.time);
      }
    }
    append_event_trace(event,
                       -1,
                       event.from_node,
                       event.from_node,
                       event.to_node,
                       "physical_state_change",
                       0);
  }

  void append_fault_audit(const RuntimeEvent& event,
                          const std::string& phase,
                          int physical_active_count,
                          int physical_generation,
                          int inflight_traversal_count,
                          bool notification_dropped) {
    if (config_.trace_limit == 0 ||
        (config_.trace_limit > 0 &&
         static_cast<int>(result_.fault_events.size()) >=
             config_.trace_limit)) {
      return;
    }
    EventRuntimeFaultAuditRow row;
    row.seq = event.seq;
    row.event = junction_event_name(event.type);
    row.phase = phase;
    row.time = event.time;
    row.from_node = event.from_node;
    row.to_node = event.to_node;
    row.physical_active_count = physical_active_count;
    row.physical_generation = physical_generation;
    row.inflight_traversal_count = inflight_traversal_count;
    row.notification_dropped = notification_dropped;
    row.current_node = event.node;
    row.intended_next_node = event.to_node;
    row.fault_policy_enabled = config_.enable_fault_policy;
    const auto bag = bags_.find(event.task_id);
    if (bag != bags_.end()) {
      row.task_id = bag->second.request.task_id;
      row.runtime_bag_id = bag->second.request.runtime_bag_id;
      row.segment_id = bag->second.request.segment_id;
    }
    result_.fault_events.push_back(std::move(row));
  }

  void append_fault_decision_audit(std::uint64_t arrive_event_seq,
                                   const std::string& phase,
                                   double time,
                                   const BagState& bag,
                                   int current,
                                   int intended_next,
                                   int selected_next) {
    if (config_.trace_limit == 0 ||
        (config_.trace_limit > 0 &&
         static_cast<int>(result_.fault_events.size()) >=
             config_.trace_limit)) {
      return;
    }
    const long long key = event_runtime_detail::directed_key(current, intended_next);
    const auto physical = physical_faults_.find(key);
    EventRuntimeFaultAuditRow row;
    row.seq = arrive_event_seq;
    row.event = "ARRIVE_JUNCTION";
    row.phase = phase;
    row.time = time;
    row.from_node = current;
    row.to_node = intended_next;
    row.physical_active_count =
        physical == physical_faults_.end() ? 0 : physical->second.active_count;
    row.physical_generation =
        physical == physical_faults_.end() ? 0 : physical->second.physical_generation;
    row.task_id = bag.request.task_id;
    row.runtime_bag_id = bag.request.runtime_bag_id;
    row.segment_id = bag.request.segment_id;
    row.current_node = current;
    row.intended_next_node = intended_next;
    row.selected_next_node = selected_next;
    row.fault_policy_enabled = config_.enable_fault_policy;
    result_.fault_events.push_back(std::move(row));
  }

  struct PendingOpportunityCounts {
    int same_node = 0;
    int shared_merge = 0;
  };

  bool sources_share_downstream_merge(int left_node,
                                      int right_node) const {
    for (const int left_target : graph_.outgoing(left_node)) {
      if (graph_.incoming_degree(left_target) <= 1) {
        continue;
      }
      const auto& right_targets = graph_.outgoing(right_node);
      if (std::find(right_targets.begin(),
                    right_targets.end(),
                    left_target) != right_targets.end()) {
        return true;
      }
    }
    return false;
  }

  bool valid_source_dispatch_event(
      const RuntimeEvent& pending) const {
    if (pending.type != JunctionEventType::kBagRelease &&
        pending.type !=
            JunctionEventType::kSourceArbitration) {
      return false;
    }
    if (pending.type == JunctionEventType::kBagRelease &&
        !pending.retry) {
      return true;
    }
    const auto controller =
        junctions_.find(pending.node);
    return controller != junctions_.end() &&
           controller->second.source_wakeup_pending &&
           controller->second.source_wakeup_generation ==
               pending.wakeup_generation;
  }

  bool valid_junction_dispatch_event(
      const RuntimeEvent& pending) const {
    if (pending.type !=
            JunctionEventType::kArriveJunction &&
        pending.type !=
            JunctionEventType::kJunctionArbitration) {
      return false;
    }
    if (pending.type ==
            JunctionEventType::kArriveJunction &&
        !pending.retry) {
      return true;
    }
    const auto controller =
        junctions_.find(pending.node);
    return controller != junctions_.end() &&
           controller->second.junction_wakeup_pending &&
           controller->second.junction_wakeup_generation ==
               pending.wakeup_generation;
  }

  PendingOpportunityCounts pending_source_opportunities(
      int source_node, double time) {
    PendingOpportunityCounts counts;
    if (!config_.enable_opportunity_telemetry) {
      return counts;
    }
    ++result_.summary.opportunity_event_queue_inspection_count;
    events_.inspect([&](const RuntimeEvent& pending) {
      if (!valid_source_dispatch_event(pending) ||
          !event_runtime_detail::same_timestamp(pending.time,
                                                time)) {
        return;
      }
      const bool pending_release =
          pending.type == JunctionEventType::kBagRelease &&
          !pending.retry;
      if (pending_release &&
          pending.node == source_node) {
        ++counts.same_node;
      }
      if (pending.node >= 0 &&
          pending.node != source_node &&
          sources_share_downstream_merge(source_node,
                                         pending.node)) {
        ++counts.shared_merge;
      }
    });
    return counts;
  }

  PendingOpportunityCounts pending_junction_opportunities(
      int junction_node, double time) {
    PendingOpportunityCounts counts;
    if (!config_.enable_opportunity_telemetry) {
      return counts;
    }
    ++result_.summary.opportunity_event_queue_inspection_count;
    events_.inspect([&](const RuntimeEvent& pending) {
      const bool pending_arrival =
          pending.type == JunctionEventType::kArriveJunction &&
          !pending.retry;
      if (!valid_junction_dispatch_event(pending) ||
          !event_runtime_detail::same_timestamp(pending.time,
                                                time)) {
        return;
      }
      if (pending_arrival && pending.node == junction_node) {
        ++counts.same_node;
      }
      if (pending.node >= 0 &&
          pending.node != junction_node &&
          sources_share_downstream_merge(junction_node,
                                         pending.node)) {
        ++counts.shared_merge;
      }
    });
    return counts;
  }

  int pending_destination_competitors(int upstream_node,
                                      int destination_node,
                                      double time) {
    if (!config_.enable_opportunity_telemetry) {
      return 0;
    }
    int count = 0;
    ++result_.summary.opportunity_event_queue_inspection_count;
    events_.inspect([&](const RuntimeEvent& pending) {
      if (!event_runtime_detail::same_timestamp(pending.time,
                                                time) ||
          pending.node < 0 ||
          pending.node == upstream_node) {
        return;
      }
      const bool can_dispatch =
          valid_source_dispatch_event(pending) ||
          valid_junction_dispatch_event(pending);
      if (!can_dispatch) {
        return;
      }
      const auto& outgoing = graph_.outgoing(pending.node);
      if (std::find(outgoing.begin(),
                    outgoing.end(),
                    destination_node) != outgoing.end()) {
        ++count;
      }
    });
    return count;
  }

  bool account_opportunity_trace_row(
      std::size_t stored_size,
      std::uint64_t& total_count,
      std::uint64_t& stored_count,
      std::uint64_t& dropped_count) {
    if (!config_.enable_opportunity_telemetry) {
      return false;
    }
    ++total_count;
    if (stored_size <
        static_cast<std::size_t>(
            config_.opportunity_trace_limit)) {
      ++stored_count;
      return true;
    }
    ++dropped_count;
    return false;
  }

  void append_source_opportunity(const RuntimeEvent& event,
                                 int ready_set_size,
                                 int chosen_runtime_bag_id,
                                 int priority_comparison_count,
                                 bool batched_arbitration) {
    int queue_before_enqueue = ready_set_size;
    int queue_after_enqueue = ready_set_size;
    int enqueue_count = 0;
    std::uint64_t generation = 0;
    if (g4irsf14_state_ != nullptr) {
      auto& local = g4irsf14_local_state(event.node);
      generation = event.wakeup_generation;
      if (local.source_batch_open &&
          event_runtime_detail::same_timestamp(
              local.source_batch_time, event.time)) {
        queue_before_enqueue =
            local.source_queue_before_enqueue;
        queue_after_enqueue =
            local.source_queue_after_enqueue;
        enqueue_count = local.source_enqueue_count;
        local.source_batch_open = false;
        local.source_enqueue_count = 0;
      }
    }
    result_.summary.max_source_arbitration_batch_size =
        std::max(result_.summary.max_source_arbitration_batch_size,
                 enqueue_count);
    if (batched_arbitration && enqueue_count > 1) {
      ++result_.summary.source_same_timestamp_batch_count;
    }
    if (!config_.enable_opportunity_telemetry) {
      return;
    }
    const auto pending =
        pending_source_opportunities(event.node, event.time);
    EventRuntimeSourceOpportunityRow row;
    row.event_time = event.time;
    row.timestamp_bits =
        event_runtime_detail::timestamp_bits(event.time);
    row.source_node = event.node;
    row.queue_length_before_enqueue = queue_before_enqueue;
    row.queue_length_after_enqueue = queue_after_enqueue;
    row.queue_length_before_arbitration = ready_set_size;
    row.queue_length_after_arbitration =
        static_cast<int>(
            junctions_[event.node].source_queue.size());
    row.same_timestamp_release_batch_size = enqueue_count;
    row.same_time_pending_source_releases = pending.same_node;
    row.same_time_pending_shared_merge_releases =
        pending.shared_merge;
    row.ready_set_size = ready_set_size;
    row.priority_comparison_count =
        priority_comparison_count;
    row.queue_discipline = config_.queue_discipline;
    row.event_seq = event.seq;
    row.arbitration_generation = generation;
    row.batched_arbitration = batched_arbitration;
    const auto chosen = bags_.find(chosen_runtime_bag_id);
    if (chosen != bags_.end()) {
      row.chosen_task_id = chosen->second.request.task_id;
      row.chosen_runtime_bag_id =
          chosen->second.request.runtime_bag_id;
      row.chosen_segment_id =
          chosen->second.request.segment_id;
    }
    if (account_opportunity_trace_row(
            result_.source_admission_opportunities.size(),
            result_.summary.source_opportunity_total_count,
            result_.summary.source_opportunity_stored_count,
            result_.summary.source_opportunity_dropped_count)) {
      result_.source_admission_opportunities.push_back(row);
    }
    if (account_opportunity_trace_row(
            result_.arbitration_batch_cardinality.size(),
            result_.summary.arbitration_batch_total_count,
            result_.summary.arbitration_batch_stored_count,
            result_.summary.arbitration_batch_dropped_count)) {
      EventRuntimeArbitrationBatchRow batch;
      batch.event_time = event.time;
      batch.timestamp_bits = row.timestamp_bits;
      batch.boundary = "source";
      batch.node = event.node;
      batch.enqueue_count = enqueue_count;
      batch.ready_set_size = ready_set_size;
      batch.pending_same_time_event_count =
          pending.same_node;
      batch.chosen_runtime_bag_id =
          row.chosen_runtime_bag_id;
      batch.event_seq = event.seq;
      batch.arbitration_generation = generation;
      result_.arbitration_batch_cardinality.push_back(
          std::move(batch));
    }
    if (account_opportunity_trace_row(
            result_.event_seq_ordering_audit.size(),
            result_.summary.event_seq_audit_total_count,
            result_.summary.event_seq_audit_stored_count,
            result_.summary.event_seq_audit_dropped_count)) {
      EventRuntimeEventSeqAuditRow audit;
      audit.event_time = event.time;
      audit.timestamp_bits = row.timestamp_bits;
      audit.boundary = "source_admission";
      audit.node = event.node;
      audit.ready_set_size = ready_set_size;
      audit.priority_comparison_count =
          row.priority_comparison_count;
      audit.later_same_time_competitor_count =
          pending.same_node;
      audit.chosen_runtime_bag_id =
          row.chosen_runtime_bag_id;
      if (chosen != bags_.end()) {
        audit.chosen_enqueue_sequence =
            chosen->second.local_enqueue_sequence;
      }
      audit.event_seq = event.seq;
      audit.seq_determined_order =
          pending.same_node > 0;
      audit.reason = audit.seq_determined_order
                         ? "later_same_time_release_unseen_at_arbitration"
                         : "no_later_same_time_release";
      result_.event_seq_ordering_audit.push_back(
          std::move(audit));
    }
  }

  void append_junction_opportunity(
      const RuntimeEvent& event,
      int ready_set_size,
      int chosen_runtime_bag_id,
      int pibt_slice_bag_count,
      int pibt_owner_count,
      int priority_comparison_count,
      bool batched_arbitration) {
    int queue_before_enqueue = ready_set_size;
    int queue_after_enqueue = ready_set_size;
    int enqueue_count = 0;
    std::uint64_t generation = 0;
    if (g4irsf14_state_ != nullptr) {
      auto& local = g4irsf14_local_state(event.node);
      generation = event.wakeup_generation;
      if (local.junction_batch_open &&
          event_runtime_detail::same_timestamp(
              local.junction_batch_time, event.time)) {
        queue_before_enqueue =
            local.junction_queue_before_enqueue;
        queue_after_enqueue =
            local.junction_queue_after_enqueue;
        enqueue_count = local.junction_enqueue_count;
        local.junction_batch_open = false;
        local.junction_enqueue_count = 0;
      }
    }
    result_.summary.max_junction_arbitration_batch_size =
        std::max(
            result_.summary.max_junction_arbitration_batch_size,
            enqueue_count);
    if (batched_arbitration && enqueue_count > 1) {
      ++result_.summary.junction_same_timestamp_batch_count;
    }
    if (!config_.enable_opportunity_telemetry) {
      return;
    }
    const auto pending =
        pending_junction_opportunities(event.node, event.time);
    EventRuntimeJunctionOpportunityRow row;
    row.event_time = event.time;
    row.timestamp_bits =
        event_runtime_detail::timestamp_bits(event.time);
    row.junction_node = event.node;
    row.queue_length_before_enqueue = queue_before_enqueue;
    row.queue_length_after_enqueue = queue_after_enqueue;
    row.queue_length_before_arbitration = ready_set_size;
    row.queue_length_after_arbitration =
        static_cast<int>(junctions_[event.node].queue.size());
    row.same_timestamp_arrival_batch_size = enqueue_count;
    row.same_time_pending_arrivals = pending.same_node;
    row.same_time_pending_shared_merge_requests =
        pending.shared_merge;
    row.ready_set_size = ready_set_size;
    row.priority_comparison_count =
        priority_comparison_count;
    row.pibt_slice_bag_count = pibt_slice_bag_count;
    row.pibt_owner_count = pibt_owner_count;
    row.event_seq = event.seq;
    row.arbitration_generation = generation;
    row.batched_arbitration = batched_arbitration;
    const auto chosen = bags_.find(chosen_runtime_bag_id);
    if (chosen != bags_.end()) {
      row.chosen_task_id = chosen->second.request.task_id;
      row.chosen_runtime_bag_id =
          chosen->second.request.runtime_bag_id;
      row.chosen_segment_id =
          chosen->second.request.segment_id;
    }
    if (account_opportunity_trace_row(
            result_.junction_arbitration_opportunities.size(),
            result_.summary.junction_opportunity_total_count,
            result_.summary.junction_opportunity_stored_count,
            result_.summary.junction_opportunity_dropped_count)) {
      result_.junction_arbitration_opportunities.push_back(row);
    }
    if (account_opportunity_trace_row(
            result_.arbitration_batch_cardinality.size(),
            result_.summary.arbitration_batch_total_count,
            result_.summary.arbitration_batch_stored_count,
            result_.summary.arbitration_batch_dropped_count)) {
      EventRuntimeArbitrationBatchRow batch;
      batch.event_time = event.time;
      batch.timestamp_bits = row.timestamp_bits;
      batch.boundary = "junction";
      batch.node = event.node;
      batch.enqueue_count = enqueue_count;
      batch.ready_set_size = ready_set_size;
      batch.pending_same_time_event_count =
          pending.same_node;
      batch.chosen_runtime_bag_id =
          row.chosen_runtime_bag_id;
      batch.event_seq = event.seq;
      batch.arbitration_generation = generation;
      result_.arbitration_batch_cardinality.push_back(
          std::move(batch));
    }
    if (account_opportunity_trace_row(
            result_.event_seq_ordering_audit.size(),
            result_.summary.event_seq_audit_total_count,
            result_.summary.event_seq_audit_stored_count,
            result_.summary.event_seq_audit_dropped_count)) {
      EventRuntimeEventSeqAuditRow audit;
      audit.event_time = event.time;
      audit.timestamp_bits = row.timestamp_bits;
      audit.boundary = "junction_arbitration";
      audit.node = event.node;
      audit.ready_set_size = ready_set_size;
      audit.priority_comparison_count =
          row.priority_comparison_count;
      audit.later_same_time_competitor_count =
          pending.same_node;
      audit.chosen_runtime_bag_id =
          row.chosen_runtime_bag_id;
      if (chosen != bags_.end()) {
        audit.chosen_enqueue_sequence =
            chosen->second.local_enqueue_sequence;
      }
      audit.event_seq = event.seq;
      audit.seq_determined_order =
          pending.same_node > 0;
      audit.reason = audit.seq_determined_order
                         ? "later_same_time_arrival_unseen_at_arbitration"
                         : "no_later_same_time_arrival";
      result_.event_seq_ordering_audit.push_back(
          std::move(audit));
    }
  }

  void append_merge_visibility(const BagState& bag,
                               int upstream_node,
                               int destination_node,
                               double time,
                               double slot_start,
                               double slot_end) {
    if (!config_.enable_opportunity_telemetry) {
      return;
    }
    auto& destination = junctions_[destination_node];
    const int later_competitors =
        pending_destination_competitors(upstream_node,
                                        destination_node,
                                        time);
    EventRuntimeMergeVisibilityRow row;
    row.event_time = time;
    row.timestamp_bits =
        event_runtime_detail::timestamp_bits(time);
    row.destination_node = destination_node;
    row.upstream_node = upstream_node;
    row.incoming_edge_start = upstream_node;
    row.incoming_edge_end = destination_node;
    row.requesting_task_id = bag.request.task_id;
    row.requesting_runtime_bag_id =
        bag.request.runtime_bag_id;
    row.requesting_segment_id = bag.request.segment_id;
    row.earliest_arrival = slot_start;
    row.slot_start = slot_start;
    row.slot_end = slot_end;
    const auto staged_known =
        staged_destination_known_competitor_counts_ ==
                nullptr
            ? std::map<int, int>::const_iterator{}
            : staged_destination_known_competitor_counts_
                  ->find(destination_node);
    row.known_competing_request_count =
        staged_destination_known_competitor_counts_ !=
                    nullptr &&
                staged_known !=
                    staged_destination_known_competitor_counts_
                        ->end()
            ? staged_known->second
            : destination.scheduled_incoming +
                  static_cast<int>(destination.queue.size());
    const bool destination_owned_arbitration =
        uses_destination_merge_grants() &&
        staged_destination_known_competitor_counts_ !=
            nullptr;
    row.later_same_time_competitor_count =
        destination_owned_arbitration
            ? 0
            : later_competitors;
    row.later_same_time_competitor_exists =
        row.later_same_time_competitor_count > 0;
    row.seq_determined_order =
        !destination_owned_arbitration &&
        row.later_same_time_competitor_exists;
    row.event_seq =
        g4irsf14_state_ == nullptr
            ? 0
            : g4irsf14_state_->current_event_seq;
    EventRuntimeEventSeqAuditRow audit;
    audit.event_time = time;
    audit.timestamp_bits = row.timestamp_bits;
    audit.boundary = "destination_slot_reservation";
    audit.node = upstream_node;
    audit.destination_node = destination_node;
    audit.ready_set_size =
        1 + row.known_competing_request_count;
    audit.later_same_time_competitor_count =
        row.later_same_time_competitor_count;
    audit.chosen_runtime_bag_id =
        bag.request.runtime_bag_id;
    audit.chosen_enqueue_sequence =
        bag.local_enqueue_sequence;
    audit.event_seq = row.event_seq;
    audit.seq_determined_order =
        row.seq_determined_order;
    audit.reason =
        destination_owned_arbitration
            ? std::string(
                  destination_merge_grant_rule_name(
                      canonical_merge_grant_rule())) +
                  "_stable_rule_not_event_seq"
            : (row.seq_determined_order
                   ? "later_same_time_competitor_not_yet_reserved"
                   : "no_later_same_time_destination_competitor");
    PIBTStagedMergeVisibility visibility{
        std::move(row), std::move(audit)};
    if (staged_merge_visibility_sink_ != nullptr) {
      staged_merge_visibility_sink_->push_back(
          std::move(visibility));
      return;
    }
    publish_merge_visibility(std::move(visibility));
  }

  void publish_merge_visibility(
      PIBTStagedMergeVisibility visibility) {
    if (account_opportunity_trace_row(
            result_.merge_request_visibility.size(),
            result_.summary.merge_visibility_total_count,
            result_.summary.merge_visibility_stored_count,
            result_.summary.merge_visibility_dropped_count)) {
      result_.merge_request_visibility.push_back(
          std::move(visibility.merge));
    }
    if (account_opportunity_trace_row(
            result_.event_seq_ordering_audit.size(),
            result_.summary.event_seq_audit_total_count,
            result_.summary.event_seq_audit_stored_count,
            result_.summary.event_seq_audit_dropped_count)) {
      result_.event_seq_ordering_audit.push_back(
          std::move(visibility.audit));
    }
  }

  event_runtime_detail::LocalArbitrationState&
  g4irsf14_local_state(int node) {
    if (g4irsf14_state_ == nullptr) {
      throw std::logic_error(
          "G4IRSF14 local arbitration state is unavailable");
    }
    return g4irsf14_state_->local[node];
  }

  event_runtime_detail::DestinationMergeBagState&
  destination_merge_bag_state(int runtime_bag_id) {
    if (!uses_destination_merge_grants() ||
        g4irsf14_state_ == nullptr) {
      throw std::logic_error(
          "destination merge bag state is unavailable outside E4");
    }
    return g4irsf14_state_
        ->destination_merge_bags[runtime_bag_id];
  }

  void observe_source_enqueue(int node, double time) {
    if (g4irsf14_state_ == nullptr) {
      return;
    }
    auto& local = g4irsf14_local_state(node);
    const int after =
        static_cast<int>(junctions_[node].source_queue.size());
    if (!local.source_batch_open ||
        !event_runtime_detail::same_timestamp(
            local.source_batch_time, time)) {
      local.source_batch_open = true;
      local.source_batch_time = time;
      local.source_queue_before_enqueue =
          std::max(0, after - 1);
      local.source_enqueue_count = 0;
    }
    local.source_queue_after_enqueue = after;
    ++local.source_enqueue_count;
  }

  void observe_junction_enqueue(int node, double time) {
    if (g4irsf14_state_ == nullptr) {
      return;
    }
    auto& local = g4irsf14_local_state(node);
    const int after =
        static_cast<int>(junctions_[node].queue.size());
    if (!local.junction_batch_open ||
        !event_runtime_detail::same_timestamp(
            local.junction_batch_time, time)) {
      local.junction_batch_open = true;
      local.junction_batch_time = time;
      local.junction_queue_before_enqueue =
          std::max(0, after - 1);
      local.junction_enqueue_count = 0;
    }
    local.junction_queue_after_enqueue = after;
    ++local.junction_enqueue_count;
  }

  bool consume_source_arbitration_wakeup(
      const RuntimeEvent& event) {
    auto& controller = junctions_[event.node];
    auto& local = g4irsf14_local_state(event.node);
    if (!controller.source_wakeup_pending ||
        controller.source_wakeup_generation !=
            event.wakeup_generation) {
      ++result_.summary
            .superseded_arbitration_event_rejected_count;
      return false;
    }
    controller.source_wakeup_pending = false;
    local.source_wakeup_time =
        std::numeric_limits<double>::infinity();
    if (local.has_last_source_arbitration &&
        event_runtime_detail::same_timestamp(
            local.last_source_arbitration_time,
            event.time)) {
      ++result_.summary
            .duplicate_same_time_arbitration_prevented_count;
      return false;
    }
    local.has_last_source_arbitration = true;
    local.last_source_arbitration_time = event.time;
    local.last_source_arbitration_generation =
        event.wakeup_generation;
    return true;
  }

  bool consume_junction_arbitration_wakeup(
      const RuntimeEvent& event) {
    auto& controller = junctions_[event.node];
    auto& local = g4irsf14_local_state(event.node);
    if (!controller.junction_wakeup_pending ||
        controller.junction_wakeup_generation !=
            event.wakeup_generation) {
      ++result_.summary
            .superseded_arbitration_event_rejected_count;
      return false;
    }
    controller.junction_wakeup_pending = false;
    local.junction_wakeup_time =
        std::numeric_limits<double>::infinity();
    if (local.has_last_junction_arbitration &&
        event_runtime_detail::same_timestamp(
            local.last_junction_arbitration_time,
            event.time)) {
      ++result_.summary
            .duplicate_same_time_arbitration_prevented_count;
      return false;
    }
    local.has_last_junction_arbitration = true;
    local.last_junction_arbitration_time = event.time;
    local.last_junction_arbitration_generation =
        event.wakeup_generation;
    return true;
  }

  void schedule_source_wakeup(int node, double time) {
    auto& controller = junctions_[node];
    if (batches_source_same_timestamp()) {
      auto& local = g4irsf14_local_state(node);
      if (controller.source_wakeup_pending) {
        if (time <
            local.source_wakeup_time -
                event_runtime_detail::kEpsilon) {
          local.source_wakeup_time = time;
          const auto generation =
              ++controller.source_wakeup_generation;
          schedule(JunctionEventType::kSourceArbitration,
                   time,
                   -1,
                   node,
                   -1,
                   -1,
                   true,
                   generation);
        } else if (event_runtime_detail::same_timestamp(
                       time, local.source_wakeup_time)) {
          ++result_.summary
                .duplicate_same_time_arbitration_prevented_count;
        }
        return;
      }
      controller.source_wakeup_pending = true;
      local.source_wakeup_time = time;
      const auto generation =
          ++controller.source_wakeup_generation;
      schedule(JunctionEventType::kSourceArbitration,
               time,
               -1,
               node,
               -1,
               -1,
               true,
               generation);
      return;
    }
    if (controller.source_wakeup_pending) {
      return;
    }
    controller.source_wakeup_pending = true;
    const auto generation = ++controller.source_wakeup_generation;
    schedule(JunctionEventType::kBagRelease,
             time,
             -1,
             node,
             -1,
             -1,
             true,
             generation);
  }

  void schedule_junction_wakeup(int node, double time) {
    auto& controller = junctions_[node];
    if (controller.queue.empty()) {
      return;
    }
    if (batches_junction_same_timestamp()) {
      auto& local = g4irsf14_local_state(node);
      if (controller.junction_wakeup_pending) {
        if (time <
            local.junction_wakeup_time -
                event_runtime_detail::kEpsilon) {
          local.junction_wakeup_time = time;
          const auto generation =
              ++controller.junction_wakeup_generation;
          schedule(JunctionEventType::kJunctionArbitration,
                   time,
                   -1,
                   node,
                   -1,
                   node,
                   true,
                   generation);
        } else if (event_runtime_detail::same_timestamp(
                       time, local.junction_wakeup_time)) {
          ++result_.summary
                .duplicate_same_time_arbitration_prevented_count;
        }
        return;
      }
      controller.junction_wakeup_pending = true;
      local.junction_wakeup_time = time;
      const auto generation =
          ++controller.junction_wakeup_generation;
      schedule(JunctionEventType::kJunctionArbitration,
               time,
               -1,
               node,
               -1,
               node,
               true,
               generation);
      return;
    }
    if (controller.junction_wakeup_pending) {
      return;
    }
    controller.junction_wakeup_pending = true;
    const auto generation =
        ++controller.junction_wakeup_generation;
    schedule(JunctionEventType::kArriveJunction,
             time,
             -1,
             node,
             -1,
             node,
             true,
             generation);
  }

  void schedule_destination_merge_wakeup(
      int destination_node,
      double time) {
    if (!uses_destination_merge_grants() ||
        g4irsf14_state_ == nullptr) {
      return;
    }
    auto& state =
        g4irsf14_state_
            ->destination_merge[destination_node];
    if (state.wakeup_pending) {
      if (event_runtime_detail::same_timestamp(
              state.wakeup_time, time)) {
        ++result_.summary
              .merge_grant_duplicate_wakeup_prevented_count;
        ++result_.summary.merge_grant_wakeup_coalesced_count;
        return;
      }
      if (time >
          state.wakeup_time -
              event_runtime_detail::kEpsilon) {
        ++result_.summary.merge_grant_wakeup_coalesced_count;
        return;
      }
    }
    state.wakeup_pending = true;
    state.wakeup_time = time;
    const auto generation =
        ++state.wakeup_generation;
    ++result_.summary.merge_grant_wakeup_scheduled_count;
    schedule(
        JunctionEventType::kDestinationMergeArbitration,
        time,
        -1,
        destination_node,
        -1,
        destination_node,
        true,
        generation);
  }

  std::size_t choose_bag(const std::deque<int>& queue,
                         double time,
                         int escape_token_task,
                         int* priority_comparison_count =
                             nullptr) const {
    if (queue.empty()) {
      throw std::logic_error("cannot choose from an empty local queue");
    }
    for (std::size_t index = 0; index < queue.size(); ++index) {
      if (queue[index] == escape_token_task) {
        return index;
      }
    }

    if (canonical_framework_mode() ==
        "legacy_order_one_step_diagnostic") {
      // The legacy Java comparator is `(int)(left.pass_time-right.pass_time)`.
      // Scanning the stable local deque with that exact truncation preserves
      // sub-second ties without importing its A* or reservation table.
      std::size_t best = 0;
      for (std::size_t index = 1; index < queue.size(); ++index) {
        if (priority_comparison_count != nullptr) {
          ++*priority_comparison_count;
        }
        const auto& candidate = bags_.at(queue[index]);
        const auto& incumbent = bags_.at(queue[best]);
        const int coarse_difference = static_cast<int>(
            candidate.request.release_time -
            incumbent.request.release_time);
        if (coarse_difference < 0) {
          best = index;
        }
      }
      return best;
    }

    if (canonical_priority_mode() !=
        BoundedLocalPIBTPriorityMode::kQ0Current) {
      std::size_t best = 0;
      for (std::size_t index = 1; index < queue.size(); ++index) {
        if (priority_comparison_count != nullptr) {
          ++*priority_comparison_count;
        }
        if (local_priority_less(bags_.at(queue[index]),
                                bags_.at(queue[best]),
                                time)) {
          best = index;
        }
      }
      return best;
    }

    std::size_t best = 0;
    for (std::size_t index = 1; index < queue.size(); ++index) {
      if (priority_comparison_count != nullptr) {
        ++*priority_comparison_count;
      }
      if (bag_priority(bags_.at(queue[index]), time) < bag_priority(bags_.at(queue[best]), time)) {
        best = index;
      } else if (bag_priority(bags_.at(queue[index]), time) ==
                     bag_priority(bags_.at(queue[best]), time) &&
                 queue[index] < queue[best]) {
        best = index;
      }
    }
    return best;
  }

  double local_priority_slack(const BagState& bag, double time) const {
    return bag.request.deadline >= 0.0
               ? bag.request.deadline - time
               : std::numeric_limits<double>::infinity();
  }

  double local_priority_age(const BagState& bag, double time) const {
    return std::max(0.0, time - bag.request.release_time);
  }

  int local_priority_contention(const BagState& bag) const {
    const int node = bag.current >= 0 ? bag.current : bag.request.start;
    int contention = 0;
    const auto local = junctions_.find(node);
    if (local != junctions_.end()) {
      contention = static_cast<int>(local->second.queue.size()) +
                   local->second.scheduled_incoming;
    }
    for (const int target : graph_.outgoing(node)) {
      const auto beacon = congestion_beacons_.find(target);
      if (beacon != congestion_beacons_.end()) {
        contention = std::max(
            contention,
            beacon->second.queue_length +
                beacon->second.scheduled_incoming);
      }
    }
    return contention;
  }

  bool is_storage_out_task(const BagState& bag) const {
    if (bag.request.start == 52) {
      return true;
    }
    std::string source = bag.request.source;
    std::transform(source.begin(),
                   source.end(),
                   source.begin(),
                   [](unsigned char value) {
                     return static_cast<char>(std::tolower(value));
                   });
    return source.find("storage") != std::string::npos ||
           source.find("ebs") != std::string::npos;
  }

  std::string local_task_class(const BagState& bag) const {
    if (bag.repaired_task_reentry) {
      return "repaired_fault_affected";
    }
    if (bag.fault_priority_generation > 0) {
      return "fault_affected";
    }
    if (is_storage_out_task(bag)) {
      return "storage_out";
    }
    if (bag.status == BagStatus::kSourceQueue ||
        bag.status == BagStatus::kPendingRelease) {
      return "new";
    }
    return "on_path";
  }

  int local_task_class_code(const BagState& bag) const {
    return destination_merge_task_class_code(
        bag.repaired_task_reentry,
        bag.fault_priority_generation > 0,
        is_storage_out_task(bag),
        bag.status == BagStatus::kSourceQueue ||
            bag.status == BagStatus::kPendingRelease);
  }

  int local_task_class_rank(const BagState& bag) const {
    const auto task_class = local_task_class(bag);
    if (task_class == "repaired_fault_affected" ||
        task_class == "fault_affected") {
      return 0;
    }
    if (task_class == "storage_out") {
      return 1;
    }
    if (task_class == "on_path") {
      return 2;
    }
    return 3;
  }

  bool local_priority_less(const BagState& left,
                           const BagState& right,
                           double time) const {
    const auto mode = canonical_priority_mode();
    const bool left_fault = left.fault_priority_generation > 0;
    const bool right_fault = right.fault_priority_generation > 0;
    const double left_slack = local_priority_slack(left, time);
    const double right_slack = local_priority_slack(right, time);
    const double left_age = local_priority_age(left, time);
    const double right_age = local_priority_age(right, time);
    const int left_contention = local_priority_contention(left);
    const int right_contention = local_priority_contention(right);
    switch (mode) {
      case BoundedLocalPIBTPriorityMode::kQ0Current:
        break;
      case BoundedLocalPIBTPriorityMode::kQ1ThesisLocalProjection:
        return std::make_tuple(!left_fault,
                               left_slack,
                               -left_contention,
                               left.local_enqueue_sequence,
                               left.request.runtime_bag_id) <
               std::make_tuple(!right_fault,
                               right_slack,
                               -right_contention,
                               right.local_enqueue_sequence,
                               right.request.runtime_bag_id);
      case BoundedLocalPIBTPriorityMode::kQ2TypeSlackAging:
        return std::make_tuple(local_task_class_rank(left),
                               left_slack,
                               -left_age,
                               -left_contention,
                               left.request.runtime_bag_id) <
               std::make_tuple(local_task_class_rank(right),
                               right_slack,
                               -right_age,
                               -right_contention,
                               right.request.runtime_bag_id);
      case BoundedLocalPIBTPriorityMode::kQ3FaultSlackAgeStableId:
        return std::make_tuple(
                   -static_cast<long long>(
                       left.fault_priority_generation),
                   left_slack,
                   -left_age,
                   left.request.runtime_bag_id) <
               std::make_tuple(
                   -static_cast<long long>(
                       right.fault_priority_generation),
                   right_slack,
                   -right_age,
                   right.request.runtime_bag_id);
    }
    return std::tie(left.request.runtime_bag_id) <
           std::tie(right.request.runtime_bag_id);
  }

  void populate_priority_trace(EventDecisionTraceRow& trace,
                               const BagState& bag,
                               double time) const {
    trace.priority_mode = canonical_priority_mode_name();
    trace.task_class = local_task_class(bag);
    trace.priority_slack_seconds =
        local_priority_slack(bag, time);
    trace.priority_age_seconds =
        local_priority_age(bag, time);
    trace.priority_local_contention =
        local_priority_contention(bag);
    trace.priority_fault_generation =
        bag.fault_priority_generation;
    trace.priority_enqueue_sequence =
        bag.local_enqueue_sequence;
    trace.pibt_preference_mode =
        config_.pibt_preference_mode;
  }

  double bag_priority(const BagState& bag, double time) const {
    const double enqueued = bag.status == BagStatus::kSourceQueue ? bag.source_enqueued_at
                                                                 : bag.junction_enqueued_at;
    if (config_.queue_discipline == "fifo") {
      return enqueued;
    }
    const double deadline = bag.request.deadline >= 0.0
                                ? bag.request.deadline
                                : std::numeric_limits<double>::max() / 4.0;
    if (config_.queue_discipline == "deadline") {
      return deadline;
    }
    return deadline - config_.aging_weight * std::max(0.0, time - enqueued);
  }

  double service_duration(int node) const {
    return std::max(graph_.service_time(node), config_.minimum_service_seconds);
  }

  double static_potential(int node, int goal) const {
    // Legacy map2 uses a large sentinel on sink-node diagonal cells.  Reaching
    // the actual goal is nevertheless zero remaining cost by definition; not
    // normalising this cell makes a local policy walk past the sink and loop.
    if (node == goal) {
      return 0.0;
    }
    const double value = graph_.heuristic(node, goal);
    if (!std::isfinite(value)) {
      throw std::logic_error("event runtime requires a finite canonical heuristic value");
    }
    return value;
  }

  double local_regret_prior(int from_node,
                            int to_node,
                            int goal_node) const {
    const auto exact = pibt_regret_prior_.find(
        std::make_tuple(from_node, to_node, goal_node));
    if (exact != pibt_regret_prior_.end()) {
      return exact->second;
    }
    const auto goal_agnostic = pibt_regret_prior_.find(
        std::make_tuple(from_node, to_node, -1));
    return goal_agnostic == pibt_regret_prior_.end()
               ? 0.0
               : goal_agnostic->second;
  }

  int recent_visit_count(const BagState& bag, int node) const {
    return static_cast<int>(std::count(bag.history.begin(), bag.history.end(), node));
  }

  void remember_node(BagState& bag, int node) {
    if (recent_visit_count(bag, node) > 0) {
      ++bag.loop_count;
      ++result_.summary.loop_count;
    }
    bag.history.push_back(node);
    while (static_cast<int>(bag.history.size()) > config_.history_limit) {
      bag.history.pop_front();
    }
    result_.summary.max_history_observed =
        std::max(result_.summary.max_history_observed, static_cast<int>(bag.history.size()));
  }

  void complete_bag(BagState& bag, double time) {
    deactivate_bag(bag);
    bag.status = BagStatus::kCompleted;
    bag.finish_time = time;
    bag.goal_completion_time_seconds =
        std::max(0.0, time - bag.request.release_time);
    record_wait_outcome(bag, time);
  }

  void fail_bag(BagState& bag, const std::string& reason, double time) {
    if (bag.status == BagStatus::kSourceQueue && bag.source_enqueued_at >= 0.0) {
      bag.total_wait += std::max(0.0, time - bag.source_enqueued_at);
    } else if (bag.status == BagStatus::kJunctionQueue && bag.junction_enqueued_at >= 0.0) {
      bag.total_wait += std::max(0.0, time - bag.junction_enqueued_at);
      bag.junction_queue_wait_seconds +=
          std::max(0.0, time - bag.junction_enqueued_at);
    }
    deactivate_bag(bag);
    bag.status = BagStatus::kFailed;
    bag.failure_reason = reason;
    if (bag.deadlock_started_at >= 0.0) {
      ++result_.summary.unresolved_deadlock_count;
      result_.summary.max_deadlock_duration =
          std::max(result_.summary.max_deadlock_duration, time - bag.deadlock_started_at);
    }
    record_wait_outcome(bag, time);
  }

  void record_wait_outcome(BagState& bag, double time) {
    const double current_queue_wait = bag.status == BagStatus::kSourceQueue && bag.source_enqueued_at >= 0.0
                                          ? std::max(0.0, time - bag.source_enqueued_at)
                                          : (bag.status == BagStatus::kJunctionQueue &&
                                                     bag.junction_enqueued_at >= 0.0
                                                 ? std::max(0.0, time - bag.junction_enqueued_at)
                                                 : 0.0);
    const double wait = bag.total_wait + current_queue_wait;
    waits_.push_back(wait);
    result_.summary.max_individual_wait = std::max(result_.summary.max_individual_wait, wait);
    if (wait > config_.starvation_threshold) {
      ++result_.summary.starvation_count;
    }
  }

  void deactivate_bag(BagState& bag) noexcept {
    if (!bag.active_in_runtime) {
      return;
    }
    bag.active_in_runtime = false;
    --active_bag_count_;
  }

  void finalize_incomplete() {
    for (auto& entry : bags_) {
      auto& bag = entry.second;
      if (bag.status == BagStatus::kCompleted || bag.status == BagStatus::kFailed) {
        continue;
      }
      const std::string reason = result_.summary.event_limit_reached
                                     ? "event_limit_reached"
                                     : (result_.summary.time_limit_reached ? "time_limit_reached"
                                                                          : "event_queue_exhausted");
      fail_bag(bag, reason, now_);
    }
  }

  void build_bag_results() {
    std::vector<int> task_ids;
    task_ids.reserve(bags_.size());
    for (const auto& entry : bags_) {
      task_ids.push_back(entry.first);
    }
    std::sort(task_ids.begin(), task_ids.end());
    for (const int task_id : task_ids) {
      const auto& bag = bags_.at(task_id);
      EventRuntimeBagResult row;
      row.segment_id = bag.request.segment_id;
      row.task_id = bag.request.task_id;
      row.runtime_bag_id = bag.request.runtime_bag_id;
      row.start = bag.request.start;
      row.goal = bag.request.goal;
      row.final_node = bag.current;
      row.release_time = bag.request.release_time;
      row.arrival_time = bag.request.release_time;
      row.deadline = bag.request.deadline;
      row.source = bag.request.source;
      row.admitted_time = bag.admitted_time;
      row.finish_time = bag.finish_time;
      row.source_queue_delay = bag.admitted_time >= 0.0
                                   ? bag.admitted_time - bag.request.release_time
                                   : std::max(0.0, now_ - bag.request.release_time);
      row.total_local_wait = bag.total_wait;
      row.junction_queue_wait_seconds =
          bag.junction_queue_wait_seconds;
      if (uses_destination_merge_grants() &&
          g4irsf14_state_ != nullptr) {
        const auto merge =
            g4irsf14_state_
                ->destination_merge_bags.find(task_id);
        if (merge !=
            g4irsf14_state_
                ->destination_merge_bags.end()) {
          row.merge_grant_wait_seconds =
              merge->second.grant_wait_seconds;
        }
      }
      row.edge_travel_time_seconds =
          bag.edge_travel_time_seconds;
      row.node_service_time_seconds =
          bag.node_service_time_seconds;
      row.loop_extra_time_seconds =
          bag.loop_extra_time_seconds;
      row.goal_completion_time_seconds =
          bag.goal_completion_time_seconds;
      row.decision_count = bag.decision_count;
      row.retry_count = bag.retry_count;
      row.loop_count = bag.loop_count;
      row.completed = bag.status == BagStatus::kCompleted;
      row.starved = bag.total_wait > config_.starvation_threshold;
      row.failure_reason = bag.failure_reason;
      row.short_history.assign(bag.history.begin(), bag.history.end());
      result_.summary.max_source_queue_delay =
          std::max(result_.summary.max_source_queue_delay, row.source_queue_delay);
      result_.bags.push_back(std::move(row));
    }
  }

  void build_junction_results() {
    std::vector<int> nodes;
    nodes.reserve(junctions_.size());
    for (const auto& entry : junctions_) {
      nodes.push_back(entry.first);
    }
    std::sort(nodes.begin(), nodes.end());
    for (const int node : nodes) {
      // Reuse the already-required final junction walk: this closes an
      // outstanding real source-admission interval at runtime stop without
      // introducing a telemetry-only global scan.
      g4irsf17_close_source_wait_interval(node, now_);
      auto& controller = junctions_.at(node);
      controller.service_calendar.purge(now_);
      controller.observe_local_state();
      EventRuntimeJunctionResult row;
      row.node = node;
      row.final_source_queue_length = static_cast<int>(controller.source_queue.size());
      row.peak_source_queue_length = controller.peak_source_queue_length;
      row.final_junction_queue_length = static_cast<int>(controller.queue.size());
      row.peak_junction_queue_length = controller.peak_junction_queue_length;
      row.final_service_calendar_intervals = controller.service_calendar.size();
      row.peak_service_calendar_intervals = controller.peak_service_calendar_intervals;
      row.final_local_state_accounted_bytes =
          controller.current_local_state_accounted_bytes();
      row.peak_local_state_accounted_bytes = controller.peak_local_state_accounted_bytes;
      row.service_reservation_count = controller.service_reservation_count;
      row.cumulative_service_reserved_seconds =
          controller.cumulative_service_reserved_seconds;
      row.first_service_reservation_start_time =
          controller.first_service_reservation_start_time;
      row.last_service_reservation_end_time =
          controller.last_service_reservation_end_time;
      row.scheduled_incoming = controller.scheduled_incoming;
      row.next_dispatch_time = controller.next_dispatch_time;
      result_.junctions.push_back(std::move(row));
    }
  }

  void build_credit_results() {
    credit_ledger_.expire_due(now_);
    if (config_.trace_limit == 0) {
      return;
    }
    for (const auto& event : credit_ledger_.lifecycle()) {
      if (config_.trace_limit >= 0 &&
          static_cast<int>(result_.credit_events.size()) >=
              config_.trace_limit) {
        break;
      }
      EventRuntimeCreditAuditRow row;
      row.time = event.time;
      row.action = event.action;
      row.reason = event.reason;
      row.credit_id = event.credit.credit_id;
      row.from_node = event.credit.from_node;
      row.to_node = event.credit.to_node;
      row.goal = event.credit.goal;
      row.earliest = event.credit.earliest;
      row.latest = event.credit.latest;
      row.generation = event.credit.generation;
      row.expiry = event.credit.expiry;
      row.capacity = event.credit.capacity;
      row.owner_or_unbound = event.credit.owner_or_unbound;
      row.fault_generation = event.credit.fault_generation;
      row.state = first_edge_credit_state_name(event.credit.state);
      const auto bag = bags_.find(event.credit.owner_or_unbound);
      if (bag != bags_.end()) {
        row.task_id = bag->second.request.task_id;
        row.segment_id = bag->second.request.segment_id;
      }
      result_.credit_events.push_back(std::move(row));
    }
  }

  void finish_summary() {
    result_.summary.final_active_bag_count = active_bag_count_;
    for (const auto& entry : bags_) {
      if (entry.second.status == BagStatus::kCompleted) {
        ++result_.summary.completed_count;
      } else {
        ++result_.summary.failed_count;
      }
    }
    if (!waits_.empty()) {
      double sum = 0.0;
      double squared_sum = 0.0;
      for (const double wait : waits_) {
        sum += wait;
        squared_sum += wait * wait;
      }
      result_.summary.fairness_jain = squared_sum <= event_runtime_detail::kEpsilon
                                          ? 1.0
                                          : (sum * sum) /
                                                (static_cast<double>(waits_.size()) * squared_sum);
    }
    result_.summary.end_time = now_;
    result_.summary.fault_affected_completed_count = 0;
    bool recovery_available = !fault_affected_bags_.empty();
    double maximum_recovery_seconds = 0.0;
    for (const int runtime_bag_id : fault_affected_bags_) {
      const auto bag = bags_.find(runtime_bag_id);
      if (bag == bags_.end() ||
          bag->second.status != BagStatus::kCompleted ||
          bag->second.finish_time < 0.0) {
        recovery_available = false;
        continue;
      }
      ++result_.summary.fault_affected_completed_count;
      const auto exposed_instances =
          fault_instances_by_bag_.find(runtime_bag_id);
      if (exposed_instances == fault_instances_by_bag_.end() ||
          exposed_instances->second.empty()) {
        recovery_available = false;
        continue;
      }
      double relevant_repair_time = -1.0;
      for (const auto& instance : exposed_instances->second) {
        const auto repaired =
            repair_time_by_fault_instance_.find(instance);
        if (repaired == repair_time_by_fault_instance_.end()) {
          recovery_available = false;
          relevant_repair_time = -1.0;
          break;
        }
        relevant_repair_time =
            std::max(relevant_repair_time, repaired->second);
      }
      if (relevant_repair_time >= 0.0) {
        maximum_recovery_seconds =
            std::max(maximum_recovery_seconds,
                     std::max(0.0,
                              bag->second.finish_time -
                                  relevant_repair_time));
      }
    }
    if (recovery_available &&
        result_.summary.fault_affected_completed_count ==
            result_.summary.fault_affected_bag_count) {
      result_.summary.fault_recovery_seconds_available = true;
      result_.summary.fault_recovery_seconds =
          maximum_recovery_seconds;
    }
    result_.summary.fault_recovery_metric_semantics =
        "max_over_completed_physically_exposed_bags_of_"
        "max(0,finish_time-latest_repair_of_exposed_fault_instances);"
        "exposure_is_keyed_by_edge_and_fault_instance_generation;"
        "unavailable_if_any_affected_bag_or_matching_repair_is_missing";
    if (active_fault_instance_by_edge_.empty() &&
        last_physical_repair_time_ >= 0.0 &&
        active_backlog_at_last_repair_ >= 0 &&
        active_backlog_at_runtime_stop_ >= 0 &&
        now_ > last_physical_repair_time_ +
                   event_runtime_detail::kEpsilon) {
      result_.summary.repair_backlog_slope_available = true;
      result_.summary.repair_backlog_slope =
          static_cast<double>(active_backlog_at_runtime_stop_ -
                              active_backlog_at_last_repair_) /
          (now_ - last_physical_repair_time_);
    }
    result_.summary.repair_backlog_slope_semantics =
        "two_point_runtime_active_bag_backlog_slope_from_latest_"
        "physical_repair_to_event_loop_stop_before_incomplete_finalization;"
        "available_only_if_no_active_fault_instance_and_latest_physical_"
        "repair_and_backlog_baseline_exist_and_event_loop_stop_is_after_"
        "repair";
    if (!decision_latencies_us_.empty()) {
      std::sort(decision_latencies_us_.begin(), decision_latencies_us_.end());
      result_.summary.decision_latency_us_p50 = percentile(decision_latencies_us_, 0.50);
      result_.summary.decision_latency_us_p95 = percentile(decision_latencies_us_, 0.95);
      result_.summary.decision_latency_us_p99 = percentile(decision_latencies_us_, 0.99);
    }
    const auto& credit = credit_ledger_.counters();
    result_.summary.first_edge_credit_issue_attempt_count =
        credit.issue_attempt_count;
    result_.summary.first_edge_credit_issued_count = credit.issued_count;
    result_.summary.first_edge_credit_validation_attempt_count =
        credit.validation_attempt_count;
    result_.summary.first_edge_credit_validation_success_count =
        credit.validation_success_count;
    result_.summary.first_edge_credit_bind_attempt_count =
        credit.bind_attempt_count;
    result_.summary.first_edge_credit_bound_count = credit.bound_count;
    result_.summary.first_edge_credit_consume_attempt_count =
        credit.consume_attempt_count;
    result_.summary.first_edge_credit_consumed_count = credit.consumed_count;
    result_.summary.first_edge_credit_expired_count = credit.expired_count;
    result_.summary.first_edge_credit_fault_revocation_count =
        credit.fault_revocation_count;
    result_.summary.first_edge_credit_generation_revocation_count =
        credit.generation_revocation_count;
    result_.summary.first_edge_credit_invalid_revocation_count =
        credit.invalid_revocation_count;
    result_.summary.first_edge_credit_duplicate_rejection_count =
        credit.duplicate_rejection_count;
    result_.summary.first_edge_credit_capacity_rejection_count =
        credit.capacity_rejection_count;
    result_.summary.first_edge_credit_stale_snapshot_rejection_count =
        credit.stale_snapshot_rejection_count;
    result_.summary.first_edge_credit_physical_fault_rejection_count =
        credit.physical_fault_rejection_count;
    result_.summary.first_edge_credit_too_early_rejection_count =
        credit.too_early_rejection_count;
    result_.summary.first_edge_credit_unknown_rejection_count =
        credit.unknown_credit_rejection_count;
    result_.summary.first_edge_credit_invalid_request_rejection_count =
        credit.invalid_request_rejection_count;
    result_.summary.first_edge_credit_lifecycle_dropped_count =
        credit.lifecycle_dropped_count;
    result_.summary.first_edge_credit_active_count = credit.active_count;
    result_.summary.first_edge_credit_peak_active_count =
        credit.peak_active_count;
    result_.summary.first_edge_credit_stored_active_count =
        static_cast<int>(credit_ledger_.stored_active_count());
    result_.summary.first_edge_credit_stored_lifecycle_count =
        static_cast<int>(credit_ledger_.stored_lifecycle_count());
    result_.summary.first_edge_credit_lifecycle_limit =
        static_cast<int>(credit_ledger_.lifecycle_limit());
    if (uses_destination_merge_grants()) {
      std::size_t lifecycle_rows = 0;
      for (const auto& entry :
           destination_merge_controllers_) {
        lifecycle_rows +=
            entry.second.lifecycle().size();
      }
      result_.merge_grant_lifecycle.reserve(
          lifecycle_rows);
      std::size_t active_record_count = 0;
      for (const auto& entry :
           destination_merge_controllers_) {
        const auto& controller = entry.second;
        active_record_count += controller.active_.size();
        for (const auto& active : controller.active_) {
          const auto bag = bags_.find(
              active.owner_runtime_bag_id);
          const auto merge =
              g4irsf14_state_
                  ->destination_merge_bags.find(
                      active.owner_runtime_bag_id);
          const bool capability_matches =
              merge !=
                      g4irsf14_state_
                          ->destination_merge_bags.end() &&
              merge->second.capability.has_value() &&
              merge->second.capability->grant_id() ==
                  active.grant_id &&
              controller.validates_active_capability(
                  *merge->second.capability);
          const auto destination =
              junctions_.find(entry.first);
          result_.summary
              .merge_grant_active_bijection_holds =
              result_.summary
                      .merge_grant_active_bijection_holds &&
              bag != bags_.end() &&
              bag->second.status == BagStatus::kInTransit &&
              bag->second.transit_from ==
                  active.edge.from_node &&
              bag->second.transit_to ==
                  active.edge.to_node &&
              bag->second.transit_merge_grant.required &&
              bag->second
                      .transit_merge_grant.grant_id ==
                  active.grant_id &&
              bag->second
                      .transit_merge_grant.request_id ==
                  active.request_id &&
              bag->second
                      .transit_merge_grant.lineage ==
                  active.lineage &&
              bag->second
                      .transit_merge_grant.edge ==
                  active.edge &&
              capability_matches &&
              destination != junctions_.end() &&
              destination->second
                  .service_calendar.contains_exact(
                      active.owner_runtime_bag_id,
                      active.slot_start,
                      active.slot_end);
        }
      }
      std::size_t stored_capability_count = 0;
      for (const auto& entry :
           g4irsf14_state_->destination_merge_bags) {
        if (!entry.second.capability.has_value()) {
          continue;
        }
        ++stored_capability_count;
        const auto& capability =
            *entry.second.capability;
        const auto controller =
            destination_merge_controllers_.find(
                capability.destination_node());
        result_.summary
            .merge_grant_active_bijection_holds =
            result_.summary
                    .merge_grant_active_bijection_holds &&
            capability.owner_runtime_bag_id() ==
                entry.first &&
            controller !=
                destination_merge_controllers_.end() &&
            controller->second
                .validates_active_capability(capability);
      }
      result_.summary
          .merge_grant_active_bijection_holds =
          result_.summary
                  .merge_grant_active_bijection_holds &&
          active_record_count ==
              stored_capability_count;
      for (const auto& entry :
           destination_merge_controllers_) {
        const auto& controller = entry.second;
        const auto& counters = controller.counters();
        result_.summary.merge_grant_request_count +=
            counters.request_count;
        result_.summary.merge_grant_issued_count +=
            counters.issued_count;
        result_.summary.merge_grant_prepared_count +=
            counters.prepared_count;
        result_.summary.merge_grant_committed_count +=
            counters.committed_count;
        result_.summary
            .merge_grant_issued_transition_count +=
            counters.issued_transition_count;
        result_.summary
            .merge_grant_prepared_transition_count +=
            counters.prepared_transition_count;
        result_.summary
            .merge_grant_committed_transition_count +=
            counters.committed_transition_count;
        result_.summary.merge_grant_consumed_count +=
            counters.consumed_count;
        result_.summary
            .merge_grant_inflight_fault_generation_recovery_count +=
            counters.inflight_fault_generation_recovery_count;
        result_.summary.merge_grant_expired_count +=
            counters.expired_count;
        result_.summary
            .merge_grant_request_expired_count +=
            counters.request_expired_count;
        result_.summary
            .merge_grant_grant_expired_count +=
            counters.grant_expired_count;
        result_.summary.merge_grant_revoked_count +=
            counters.revoked_count;
        result_.summary
            .merge_grant_revoked_fault_count +=
            counters.revoked_fault_count;
        result_.summary
            .merge_grant_revoked_stale_state_count +=
            counters.revoked_stale_state_count;
        result_.summary
            .merge_grant_revoked_replan_current_edge_count +=
            counters
                .revoked_replan_current_edge_count;
        result_.summary.merge_grant_rolled_back_count +=
            counters.rolled_back_count;
        result_.summary
            .merge_grant_post_commit_revoked_count +=
            counters.post_commit_revoked_count;
        result_.summary
            .merge_grant_post_commit_expired_count +=
            counters.post_commit_expired_count;
        result_.summary
            .merge_grant_post_commit_rollback_count +=
            counters.post_commit_rollback_count;
        result_.summary.merge_grant_exact_slot_busy_count +=
            counters.exact_slot_busy_count;
        result_.summary
            .merge_grant_active_grant_rejection_count +=
            counters.active_grant_rejection_count;
        result_.summary
            .merge_grant_queue_capacity_block_count +=
            counters.queue_capacity_block_count;
        result_.summary
            .merge_grant_contended_loser_retry_count +=
            counters.contended_loser_retry_count;
        result_.summary
            .merge_grant_lifecycle_transition_count +=
            counters.lifecycle_transition_count;
        result_.summary
            .merge_grant_lifecycle_stored_count +=
            counters.lifecycle_stored_count;
        result_.summary
            .merge_grant_lifecycle_dropped_count +=
            counters.lifecycle_dropped_count;
        result_.summary
            .merge_grant_peak_pending_requests =
            std::max(
                result_.summary
                    .merge_grant_peak_pending_requests,
                static_cast<int>(
                    counters.peak_pending_count));
        result_.summary
            .merge_grant_peak_active_unconsumed =
            std::max(
                result_.summary
                    .merge_grant_peak_active_unconsumed,
                static_cast<int>(
                    counters
                        .peak_active_unconsumed_count));
        result_.summary
            .merge_grant_conservation_holds =
            result_.summary
                .merge_grant_conservation_holds &&
            controller.conservation_holds();
        result_.summary
            .merge_grant_outstanding_request_count +=
            controller.pending_count();
        result_.summary
            .merge_grant_final_active_unconsumed +=
            static_cast<int>(
                controller.active_unconsumed_count());
        result_.merge_grant_lifecycle.insert(
            result_.merge_grant_lifecycle.end(),
            controller.lifecycle().begin(),
            controller.lifecycle().end());
      }
      std::sort(
          result_.merge_grant_lifecycle.begin(),
          result_.merge_grant_lifecycle.end(),
          [](const auto& left, const auto& right) {
            return std::tie(
                       left.time,
                       left.destination_node,
                       left.request_id,
                       left.grant_id,
                       left.state) <
                   std::tie(
                       right.time,
                       right.destination_node,
                       right.request_id,
                       right.grant_id,
                       right.state);
          });
      result_.summary
          .merge_grant_terminal_request_count =
          result_.summary.merge_grant_expired_count +
          result_.summary.merge_grant_revoked_count +
          result_.summary.merge_grant_rolled_back_count;
      result_.summary.merge_grant_conservation_holds =
          result_.summary
              .merge_grant_conservation_holds &&
          result_.summary.merge_grant_request_count ==
              result_.summary
                      .merge_grant_committed_count +
                  result_.summary
                      .merge_grant_terminal_request_count +
                  result_.summary
                      .merge_grant_outstanding_request_count &&
          result_.summary
                  .merge_grant_inflight_fault_generation_recovery_count <=
              result_.summary.merge_grant_consumed_count &&
          result_.summary.merge_grant_issued_count ==
              result_.summary
                  .merge_grant_prepared_count &&
          result_.summary.merge_grant_prepared_count ==
              result_.summary
                  .merge_grant_committed_count &&
          result_.summary
                  .merge_grant_issued_transition_count ==
              result_.summary
                  .merge_grant_prepared_transition_count &&
          result_.summary
                  .merge_grant_prepared_transition_count ==
              result_.summary
                  .merge_grant_committed_transition_count &&
          result_.summary
                  .merge_grant_committed_transition_count ==
              result_.summary
                      .merge_grant_committed_count +
                  result_.summary
                      .merge_grant_post_commit_revoked_count +
                  result_.summary
                      .merge_grant_post_commit_expired_count +
                  result_.summary
                      .merge_grant_post_commit_rollback_count &&
          result_.summary.merge_grant_committed_count ==
              result_.summary
                  .merge_grant_consumed_count +
                  static_cast<std::uint64_t>(
                      std::accumulate(
                          destination_merge_controllers_
                              .begin(),
                          destination_merge_controllers_
                              .end(),
                          std::size_t{0},
                          [](std::size_t count,
                             const auto& item) {
                            return count +
                                   item.second
                                       .active_unconsumed_count();
                          })) &&
          result_.summary
                  .merge_grant_lifecycle_transition_count ==
              result_.summary
                      .merge_grant_lifecycle_stored_count +
                  result_.summary
                      .merge_grant_lifecycle_dropped_count;
    }
    // Keep the frozen Win64 E0 accounted-byte scalar exact. The append-only
    // config/result/state holders are inactive there and must not perturb a
    // deterministic compatibility hash merely because their empty C++
    // container objects exist in the class layout.
    std::size_t runtime_object_bytes = sizeof(*this);
#if defined(_MSC_VER) && defined(_WIN64)
    if (!g4irsf14_extensions_enabled() &&
        !g4irsf17_extensions_enabled()) {
      runtime_object_bytes = 4496;
    }
#endif
    if (!g4irsf17_extensions_enabled() &&
        g4irsf14_extensions_enabled()) {
      runtime_object_bytes -=
          event_runtime_detail::kG4IRSF17RuntimeExtensionBytes;
    }
    std::size_t accounted = runtime_object_bytes;
    accounted += bags_.size() * sizeof(BagState);
    const std::size_t calendar_extension_bytes =
        sizeof(LocalCalendar) -
        sizeof(std::vector<CalendarInterval>);
    for (const auto& entry : junctions_) {
      accounted +=
          entry.second.current_local_state_accounted_bytes() -
          (!g4irsf17_extensions_enabled()
               ? event_runtime_detail::
                     kG4IRSF17JunctionStateExtensionBytes
               : 0) -
          (!g4irsf14_extensions_enabled()
               ? calendar_extension_bytes
               : 0);
    }
    for (const auto& entry : corridors_) {
      accounted +=
                   (!g4irsf14_extensions_enabled()
                        ? sizeof(std::vector<CalendarInterval>)
                        : sizeof(LocalCalendar)) +
                   entry.second.dynamic_interval_capacity_accounted_bytes();
    }
    accounted += physical_faults_.size() * sizeof(event_runtime_detail::FaultState);
    accounted += advertised_faults_.size() * sizeof(event_runtime_detail::AdvertisedFaultState);
    accounted += congestion_beacons_.size() *
                 (g4irsf17_extensions_enabled()
                      ? sizeof(event_runtime_detail::CongestionBeaconState)
                      : event_runtime_detail::
                            kPreG4IRSF17CongestionBeaconStateBytes);
    accounted += pibt_regret_prior_.size() *
                 sizeof(std::pair<const std::tuple<int, int, int>, double>);
    accounted += fault_affected_bags_.size() * sizeof(int);
    for (const auto& entry : fault_instances_by_bag_) {
      accounted += sizeof(entry) +
                   entry.second.size() *
                       sizeof(std::pair<long long, int>);
    }
    accounted +=
        active_fault_instance_by_edge_.size() *
        sizeof(std::pair<const long long, int>);
    accounted +=
        repair_time_by_fault_instance_.size() *
        sizeof(std::pair<const std::pair<long long, int>, double>);
    accounted += credit_ledger_.accounted_bytes();
    accounted +=
        result_.bags.capacity() *
        (!g4irsf14_extensions_enabled()
             ? sizeof(EventRuntimeBagResult) - sizeof(double)
             : sizeof(EventRuntimeBagResult));
    accounted += result_.events.capacity() * sizeof(EventRuntimeTraceRow);
    accounted += result_.decisions.capacity() * sizeof(EventDecisionTraceRow);
    accounted += result_.hold_attempts.capacity() * sizeof(EventDecisionTraceRow);
    accounted += result_.junctions.capacity() * sizeof(EventRuntimeJunctionResult);
    accounted += result_.fault_events.capacity() * sizeof(EventRuntimeFaultAuditRow);
    accounted += result_.credit_events.capacity() *
                 sizeof(EventRuntimeCreditAuditRow);
    accounted += result_.pibt_events.capacity() *
                 sizeof(EventRuntimePIBTAuditRow);
    accounted +=
        result_.source_admission_opportunities.capacity() *
        sizeof(EventRuntimeSourceOpportunityRow);
    accounted +=
        result_.g4irsf17_source_wait_blockers.capacity() *
        sizeof(EventRuntimeSourceWaitBlockerRow);
    accounted +=
        result_.g4irsf17_source_policy_decisions.capacity() *
        sizeof(EventRuntimeG4IRSF17SourcePolicyRow);
    for (const auto& row : result_.g4irsf17_source_policy_decisions) {
      accounted += row.candidate_queue_indices.capacity() * sizeof(int);
      accounted += row.candidate_task_ids.capacity() * sizeof(int);
      accounted += row.candidate_runtime_bag_ids.capacity() * sizeof(int);
      accounted += row.candidate_segment_ids.capacity() * sizeof(std::string);
      accounted += row.candidate_features.capacity() *
                   sizeof(std::array<
                       double, kG4IRSF17SourceCandidateFeatureCount>);
      for (const auto& segment : row.candidate_segment_ids) {
        accounted += segment.capacity() * sizeof(char);
      }
    }
    accounted +=
        result_.junction_arbitration_opportunities.capacity() *
        sizeof(EventRuntimeJunctionOpportunityRow);
    accounted += result_.merge_request_visibility.capacity() *
                 sizeof(EventRuntimeMergeVisibilityRow);
    accounted += result_.merge_service_opportunities.capacity() *
                 sizeof(EventRuntimeMergeServiceOpportunityRow);
    for (const auto& row : result_.merge_service_opportunities) {
      accounted += row.timing_mode.capacity() * sizeof(char);
      accounted += row.model_policy_mode.capacity() * sizeof(char);
      accounted += row.model_feature_contract.capacity() * sizeof(char);
      accounted += row.model_reason.capacity() * sizeof(char);
    }
    accounted += result_.event_seq_ordering_audit.capacity() *
                 sizeof(EventRuntimeEventSeqAuditRow);
    accounted +=
        result_.arbitration_batch_cardinality.capacity() *
        sizeof(EventRuntimeArbitrationBatchRow);
    accounted +=
        result_.merge_grant_lifecycle.capacity() *
        sizeof(DestinationMergeGrantLifecycleRow);
    if (g4irsf14_state_ != nullptr) {
      accounted +=
          sizeof(event_runtime_detail::G4IRSF14RuntimeState);
      accounted +=
          g4irsf14_state_->local.size() *
          sizeof(std::pair<const int,
                           event_runtime_detail::
                               LocalArbitrationState>);
      accounted +=
          g4irsf14_state_->destination_merge.size() *
          sizeof(std::pair<
                 const int,
                 event_runtime_detail::
                     DestinationMergeArbitrationState>);
      accounted +=
          g4irsf14_state_->destination_merge_bags.size() *
          sizeof(std::pair<
                 const int,
                 event_runtime_detail::
                     DestinationMergeBagState>);
    }
    if (uses_destination_merge_grants()) {
      accounted +=
          destination_merge_controllers_.size() *
          sizeof(std::pair<
                 const int,
                 DestinationMergeGrantController>);
      for (const auto& entry :
           destination_merge_controllers_) {
        accounted +=
            entry.second
                .dynamic_storage_accounted_bytes();
      }
      accounted +=
          pending_merge_dispatches_.size() *
          sizeof(std::pair<
                 const std::uint64_t,
                 PendingMergeDispatch>);
      for (const auto& entry :
           pending_merge_dispatches_) {
        const auto& trace = entry.second.trace;
        accounted += trace.segment_id.capacity();
        accounted +=
            trace.candidates.capacity() *
            sizeof(EventCandidateRecord);
        for (const auto& candidate :
             trace.candidates) {
          accounted +=
              candidate.shield_reason.capacity();
        }
        accounted +=
            trace.scorer_risk_reasons.capacity() *
            sizeof(std::string);
        for (const auto& reason :
             trace.scorer_risk_reasons) {
          accounted += reason.capacity();
        }
        accounted += trace.scorer_id.capacity();
        accounted +=
            trace.scorer_effective_id.capacity();
        accounted +=
            trace.decision_source.capacity();
        accounted += trace.rule_reason.capacity();
        accounted +=
            trace.short_history.capacity() *
            sizeof(int);
        accounted += trace.priority_mode.capacity();
        accounted += trace.task_class.capacity();
        accounted +=
            trace.pibt_preference_mode.capacity();
      }
      accounted +=
          events_.dynamic_storage_accounted_bytes();
    }
    result_.summary.cpp_internal_accounted_bytes = accounted;
  }

  void record_decision_latency(std::chrono::steady_clock::time_point started) {
    const std::chrono::duration<double, std::micro> elapsed =
        std::chrono::steady_clock::now() - started;
    decision_latencies_us_.push_back(elapsed.count());
  }

  static double percentile(const std::vector<double>& sorted_values, double quantile) {
    if (sorted_values.empty()) {
      return 0.0;
    }
    const double position = quantile * static_cast<double>(sorted_values.size() - 1);
    const auto lower = static_cast<std::size_t>(std::floor(position));
    const auto upper = static_cast<std::size_t>(std::ceil(position));
    const double fraction = position - static_cast<double>(lower);
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction;
  }

  void append_event_trace(const RuntimeEvent& event,
                          int task_id,
                          int node,
                          int from,
                          int to,
                          const std::string& reason,
                          int selected_edges) {
    if (!event_trace_available(result_.events.size())) {
      result_.summary.event_trace_truncated = true;
      return;
    }
    EventRuntimeTraceRow row;
    row.seq = event.seq;
    row.event = junction_event_name(event.type);
    row.time = event.time;
    row.task_id = -1;
    row.runtime_bag_id = task_id;
    const auto bag = bags_.find(task_id);
    if (bag != bags_.end()) {
      row.task_id = bag->second.request.task_id;
      row.segment_id = bag->second.request.segment_id;
    }
    row.node = node;
    row.from_node = from;
    row.to_node = to;
    row.reason = reason;
    row.selected_edge_count = selected_edges;
    result_.events.push_back(std::move(row));
  }

  void append_decision_trace(EventDecisionTraceRow row, bool selected_edge) {
    ++result_.summary.decision_trace_seen_count;
    const int shard = ((row.task_id % config_.trace_shard_count) + config_.trace_shard_count) %
                      config_.trace_shard_count;
    if (shard != config_.trace_shard_index) {
      return;
    }
    ++result_.summary.decision_trace_shard_seen_count;
    const std::size_t total_rows = result_.decisions.size() + result_.hold_attempts.size();
    if (!trace_available(total_rows)) {
      result_.summary.decision_trace_truncated = true;
      return;
    }
    if (selected_edge) {
      result_.decisions.push_back(std::move(row));
      ++result_.summary.decision_trace_stored_count;
    } else {
      result_.hold_attempts.push_back(std::move(row));
      ++result_.summary.hold_trace_stored_count;
    }
  }

  void publish_prepared_decision_trace_noexcept(
      EventDecisionTraceRow row,
      bool selected_edge) noexcept {
    ++result_.summary.decision_trace_seen_count;
    const int shard =
        ((row.task_id % config_.trace_shard_count) +
         config_.trace_shard_count) %
        config_.trace_shard_count;
    if (shard != config_.trace_shard_index) {
      return;
    }
    ++result_.summary.decision_trace_shard_seen_count;
    const std::size_t total_rows =
        result_.decisions.size() +
        result_.hold_attempts.size();
    if (!trace_available(total_rows)) {
      result_.summary.decision_trace_truncated = true;
      return;
    }
    if (selected_edge) {
      result_.decisions.push_back(std::move(row));
      ++result_.summary.decision_trace_stored_count;
    } else {
      result_.hold_attempts.push_back(std::move(row));
      ++result_.summary.hold_trace_stored_count;
    }
  }

  void publish_prepared_merge_visibility_noexcept(
      PIBTStagedMergeVisibility visibility) noexcept {
    if (!config_.enable_opportunity_telemetry) {
      return;
    }
    ++result_.summary.merge_visibility_total_count;
    if (result_.merge_request_visibility.size() <
        static_cast<std::size_t>(
            config_.opportunity_trace_limit)) {
      ++result_.summary.merge_visibility_stored_count;
      result_.merge_request_visibility.push_back(
          std::move(visibility.merge));
    } else {
      ++result_.summary.merge_visibility_dropped_count;
    }
    ++result_.summary.event_seq_audit_total_count;
    if (result_.event_seq_ordering_audit.size() <
        static_cast<std::size_t>(
            config_.opportunity_trace_limit)) {
      ++result_.summary.event_seq_audit_stored_count;
      result_.event_seq_ordering_audit.push_back(
          std::move(visibility.audit));
    } else {
      ++result_.summary.event_seq_audit_dropped_count;
    }
  }

  bool trace_available(std::size_t current_size) const {
    return config_.trace_limit < 0 || static_cast<int>(current_size) < config_.trace_limit;
  }

  int effective_event_trace_limit() const {
    return config_.event_trace_limit.value_or(config_.trace_limit);
  }

  bool event_trace_available(std::size_t current_size) const {
    const int limit = effective_event_trace_limit();
    return limit < 0 || static_cast<int>(current_size) < limit;
  }

  void update_queue_maxima(JunctionState& controller) {
    controller.observe_local_state();
    result_.summary.max_junction_queue_length =
        std::max(result_.summary.max_junction_queue_length,
                 static_cast<int>(controller.queue.size()));
    result_.summary.max_source_queue_length =
        std::max(result_.summary.max_source_queue_length,
                 static_cast<int>(controller.source_queue.size()));
  }

  void update_calendar_maxima(JunctionState& controller, const LocalCalendar* corridor) {
    controller.observe_local_state();
    result_.summary.max_local_calendar_intervals =
        std::max(result_.summary.max_local_calendar_intervals,
                 controller.service_calendar.size());
    if (corridor != nullptr) {
      result_.summary.max_corridor_calendar_intervals =
          std::max(result_.summary.max_corridor_calendar_intervals, corridor->size());
    }
  }

  const Graph& graph_;
  EventDrivenJunctionConfig config_;
  std::optional<EdgeScoreModel> scorer_model_;
  std::unique_ptr<G4IRSF16SelectiveLinearModel>
      g4irsf16_i3_model_;
  std::unique_ptr<G4IRSF16SelectiveLinearModel>
      g4irsf16_i4_model_;
  std::unique_ptr<G4IRSF16Supervisor>
      g4irsf16_supervisor_;
  // This is deliberately separate from BagState::fault_priority_generation:
  // the priority boost is a one-edge repair token and resets after use,
  // whereas a supervisor generation must never decrease.
  std::unordered_map<int, std::uint64_t>
      g4irsf16_physical_fault_generation_by_bag_;
  std::map<std::pair<int, int>, int> scorer_static_hops_;
  std::map<std::tuple<int, int, int>, double>
      pibt_regret_prior_;
  EventDrivenJunctionResult result_;
  std::unordered_map<int, BagState> bags_;
  std::unordered_map<std::string, int> segment_runtime_ids_;
  std::unordered_map<int, JunctionState> junctions_;
  std::unordered_map<long long, LocalCalendar> corridors_;
  std::unordered_map<long long, event_runtime_detail::FaultState> physical_faults_;
  std::unordered_map<long long, event_runtime_detail::AdvertisedFaultState> advertised_faults_;
  std::unordered_map<int, event_runtime_detail::CongestionBeaconState> congestion_beacons_;
  std::unordered_map<int, DestinationMergeGrantController>
      destination_merge_controllers_;
  std::unordered_map<std::uint64_t, PendingMergeDispatch>
      pending_merge_dispatches_;
  ExpiringFirstEdgeCreditLedger credit_ledger_;
  std::unordered_map<long long, int> directed_inflight_counts_;
  std::unordered_set<int> fault_affected_bags_;
  std::unordered_map<long long, std::set<int>>
      fault_affected_bags_by_edge_;
  std::unordered_map<int, std::set<std::pair<long long, int>>>
      fault_instances_by_bag_;
  std::unordered_map<long long, int>
      active_fault_instance_by_edge_;
  std::map<std::pair<long long, int>, double>
      repair_time_by_fault_instance_;
  event_runtime_detail::RuntimeEventQueue events_;
  std::vector<RuntimeEvent>* staged_event_sink_ = nullptr;
  std::vector<PIBTStagedMergeVisibility>*
      staged_merge_visibility_sink_ = nullptr;
  const std::map<int, int>*
      staged_destination_known_competitor_counts_ =
          nullptr;
  // Ephemeral stack-owned treatment frame.  It is intentionally omitted from
  // CheckpointStorage and every deterministic state digest.
  ActiveCausalStep* active_causal_step_ = nullptr;
#ifdef CZR005_EVENT_RUNTIME_TESTING
  bool test_pibt_logical_failure_injected_ = false;
  bool test_merge_grant_prepare_failure_injected_ = false;
  bool test_merge_grant_advertised_flip_injected_ = false;
  bool test_merge_grant_physical_flip_injected_ = false;
  bool test_merge_grant_calendar_flip_injected_ = false;
  bool test_merge_grant_queue_flip_injected_ = false;
  bool test_merge_grant_edge_exit_capability_drop_injected_ = false;
  bool test_merge_grant_edge_exit_physical_flip_injected_ = false;
  bool test_merge_grant_edge_exit_advertised_flip_injected_ = false;
  bool test_merge_grant_edge_exit_calendar_remove_injected_ = false;
  bool test_merge_grant_edge_exit_expiry_injected_ = false;
  bool test_merge_grant_edge_exit_wrong_owner_injected_ = false;
  bool test_merge_grant_edge_exit_wrong_edge_injected_ = false;
  bool test_merge_grant_edge_exit_wrong_destination_injected_ = false;
  bool
      test_merge_grant_edge_exit_claimed_request_generation_tamper_injected_ =
          false;
  bool
      test_merge_grant_edge_exit_claimed_queue_generation_tamper_injected_ =
          false;
  bool
      test_merge_grant_edge_exit_claimed_calendar_generation_tamper_injected_ =
          false;
  bool test_merge_grant_edge_exit_live_queue_generation_advance_injected_ =
      false;
  bool test_merge_grant_edge_exit_live_calendar_generation_advance_injected_ =
      false;
  bool test_pibt_post_commit_failure_injected_ = false;
#endif
  std::uint64_t next_event_seq_ = 1;
  std::uint64_t next_decision_id_ = 1;
  std::uint64_t next_pibt_activation_id_ = 1;
  std::uint64_t next_local_enqueue_sequence_ = 1;
  std::uint64_t next_merge_request_lineage_ = 1;
  double now_ = 0.0;
  double time_limit_ = 0.0;
  int active_bag_count_ = 0;
  double last_physical_repair_time_ = -1.0;
  int active_backlog_at_last_repair_ = -1;
  int active_backlog_at_runtime_stop_ = -1;
  std::vector<double> waits_;
  std::vector<double> decision_latencies_us_;
  std::unique_ptr<event_runtime_detail::G4IRSF14RuntimeState>
      g4irsf14_state_;
  EventDrivenJunctionRuntimePhase runtime_phase_ =
      EventDrivenJunctionRuntimePhase::kIdle;
  std::chrono::steady_clock::time_point runtime_started_ =
      std::chrono::steady_clock::now();
};

inline event_runtime_detail::G4IRSF14RuntimeStateCheckpoint
EventDrivenJunctionRuntime::capture_g4irsf14_state(
    const event_runtime_detail::G4IRSF14RuntimeState& state) {
  event_runtime_detail::G4IRSF14RuntimeStateCheckpoint checkpoint;
  checkpoint.local = state.local;
  checkpoint.destination_merge = state.destination_merge;
  checkpoint.destination_merge_bags.reserve(
      state.destination_merge_bags.size());
  for (const auto& entry : state.destination_merge_bags) {
    event_runtime_detail::DestinationMergeBagStateCheckpoint item;
    item.junction_queue_generation =
        entry.second.junction_queue_generation;
    item.request_generation = entry.second.request_generation;
    item.pending_request_id = entry.second.pending_request_id;
    item.pending_lineage = entry.second.pending_lineage;
    item.pending_request_time = entry.second.pending_request_time;
    item.first_contention_time =
        entry.second.first_contention_time;
    item.grant_wait_seconds = entry.second.grant_wait_seconds;
    item.g4irsf18_merge_override_count =
        entry.second.g4irsf18_merge_override_count;
    item.exact_grant_edge_entry_observed =
        entry.second.exact_grant_edge_entry_observed;
    if (entry.second.capability.has_value()) {
      item.capability =
          DestinationMergeGrantCheckpointCodec::capture(
              *entry.second.capability);
    }
    checkpoint.destination_merge_bags.emplace(
        entry.first, std::move(item));
  }
  checkpoint.current_event_seq = state.current_event_seq;
  checkpoint.microphase_floor_active =
      state.microphase_floor_active;
  checkpoint.microphase_floor_time = state.microphase_floor_time;
  checkpoint.microphase_floor_priority =
      state.microphase_floor_priority;
  checkpoint.current_pibt_slice_bag_count =
      state.current_pibt_slice_bag_count;
  checkpoint.current_pibt_owner_count =
      state.current_pibt_owner_count;
  return checkpoint;
}

inline std::unique_ptr<
    event_runtime_detail::G4IRSF14RuntimeState>
EventDrivenJunctionRuntime::restore_g4irsf14_state(
    const event_runtime_detail::G4IRSF14RuntimeStateCheckpoint&
        checkpoint) {
  auto state = std::make_unique<
      event_runtime_detail::G4IRSF14RuntimeState>();
  state->local = checkpoint.local;
  state->destination_merge = checkpoint.destination_merge;
  state->destination_merge_bags.reserve(
      checkpoint.destination_merge_bags.size());
  for (const auto& entry : checkpoint.destination_merge_bags) {
    event_runtime_detail::DestinationMergeBagState item;
    item.junction_queue_generation =
        entry.second.junction_queue_generation;
    item.request_generation = entry.second.request_generation;
    item.pending_request_id = entry.second.pending_request_id;
    item.pending_lineage = entry.second.pending_lineage;
    item.pending_request_time = entry.second.pending_request_time;
    item.first_contention_time =
        entry.second.first_contention_time;
    item.grant_wait_seconds = entry.second.grant_wait_seconds;
    item.g4irsf18_merge_override_count =
        entry.second.g4irsf18_merge_override_count;
    item.exact_grant_edge_entry_observed =
        entry.second.exact_grant_edge_entry_observed;
    if (entry.second.capability.has_value()) {
      item.capability.emplace(
          DestinationMergeGrantCheckpointCodec::restore(
              *entry.second.capability));
    }
    state->destination_merge_bags.emplace(
        entry.first, std::move(item));
  }
  state->current_event_seq = checkpoint.current_event_seq;
  state->microphase_floor_active =
      checkpoint.microphase_floor_active;
  state->microphase_floor_time = checkpoint.microphase_floor_time;
  state->microphase_floor_priority =
      checkpoint.microphase_floor_priority;
  state->current_pibt_slice_bag_count =
      checkpoint.current_pibt_slice_bag_count;
  state->current_pibt_owner_count =
      checkpoint.current_pibt_owner_count;
  return state;
}

inline EventDrivenJunctionRuntime::StateCheckpoint
EventDrivenJunctionRuntime::capture_state_checkpoint() const {
  if (g4irsf16_enabled()) {
    throw std::logic_error(
        "G4IRSF16 online supervisor state is not a G4IRSF14 causal-clone "
        "checkpoint payload; use a separate exact-off causal runtime");
  }
  if (runtime_phase_ != EventDrivenJunctionRuntimePhase::kReady ||
      events_.empty()) {
    throw std::logic_error(
        "runtime checkpoint requires a live pre-pop event boundary");
  }
  require_checkpoint_safe_boundary();
  auto storage = std::make_shared<CheckpointStorage>();
  storage->graph_identity = &graph_;
  storage->graph_sha256 = scorer_graph_fingerprint();
  storage->config = config_;
  storage->scorer_model = scorer_model_;
  storage->scorer_static_hops = scorer_static_hops_;
  storage->pibt_regret_prior = pibt_regret_prior_;
  storage->result = result_;
  storage->bags = bags_;
  storage->segment_runtime_ids = segment_runtime_ids_;
  storage->junctions = junctions_;
  storage->corridors = corridors_;
  storage->physical_faults = physical_faults_;
  storage->advertised_faults = advertised_faults_;
  storage->congestion_beacons = congestion_beacons_;
  storage->destination_merge_controllers.reserve(
      destination_merge_controllers_.size());
  for (const auto& entry : destination_merge_controllers_) {
    storage->destination_merge_controllers.emplace(
        entry.first,
        DestinationMergeGrantCheckpointCodec::capture(
            entry.second));
  }
  storage->pending_merge_dispatches =
      pending_merge_dispatches_;
  storage->credit_ledger =
      credit_ledger_.capture_exact_checkpoint();
  storage->directed_inflight_counts = directed_inflight_counts_;
  storage->fault_affected_bags = fault_affected_bags_;
  storage->fault_affected_bags_by_edge =
      fault_affected_bags_by_edge_;
  storage->fault_instances_by_bag = fault_instances_by_bag_;
  storage->active_fault_instance_by_edge =
      active_fault_instance_by_edge_;
  storage->repair_time_by_fault_instance =
      repair_time_by_fault_instance_;
  storage->events = events_;
  if (g4irsf14_state_ != nullptr) {
    storage->g4irsf14_state =
        capture_g4irsf14_state(*g4irsf14_state_);
  }
#ifdef CZR005_EVENT_RUNTIME_TESTING
  storage->test_pibt_logical_failure_injected =
      test_pibt_logical_failure_injected_;
  storage->test_merge_grant_prepare_failure_injected =
      test_merge_grant_prepare_failure_injected_;
  storage->test_merge_grant_advertised_flip_injected =
      test_merge_grant_advertised_flip_injected_;
  storage->test_merge_grant_physical_flip_injected =
      test_merge_grant_physical_flip_injected_;
  storage->test_merge_grant_calendar_flip_injected =
      test_merge_grant_calendar_flip_injected_;
  storage->test_merge_grant_queue_flip_injected =
      test_merge_grant_queue_flip_injected_;
  storage->test_merge_grant_edge_exit_capability_drop_injected =
      test_merge_grant_edge_exit_capability_drop_injected_;
  storage->test_merge_grant_edge_exit_physical_flip_injected =
      test_merge_grant_edge_exit_physical_flip_injected_;
  storage->test_merge_grant_edge_exit_advertised_flip_injected =
      test_merge_grant_edge_exit_advertised_flip_injected_;
  storage->test_merge_grant_edge_exit_calendar_remove_injected =
      test_merge_grant_edge_exit_calendar_remove_injected_;
  storage->test_merge_grant_edge_exit_expiry_injected =
      test_merge_grant_edge_exit_expiry_injected_;
  storage->test_merge_grant_edge_exit_wrong_owner_injected =
      test_merge_grant_edge_exit_wrong_owner_injected_;
  storage->test_merge_grant_edge_exit_wrong_edge_injected =
      test_merge_grant_edge_exit_wrong_edge_injected_;
  storage->test_merge_grant_edge_exit_wrong_destination_injected =
      test_merge_grant_edge_exit_wrong_destination_injected_;
  storage
      ->test_merge_grant_edge_exit_claimed_request_generation_tamper_injected =
      test_merge_grant_edge_exit_claimed_request_generation_tamper_injected_;
  storage
      ->test_merge_grant_edge_exit_claimed_queue_generation_tamper_injected =
      test_merge_grant_edge_exit_claimed_queue_generation_tamper_injected_;
  storage
      ->test_merge_grant_edge_exit_claimed_calendar_generation_tamper_injected =
      test_merge_grant_edge_exit_claimed_calendar_generation_tamper_injected_;
  storage
      ->test_merge_grant_edge_exit_live_queue_generation_advance_injected =
      test_merge_grant_edge_exit_live_queue_generation_advance_injected_;
  storage
      ->test_merge_grant_edge_exit_live_calendar_generation_advance_injected =
      test_merge_grant_edge_exit_live_calendar_generation_advance_injected_;
  storage->test_pibt_post_commit_failure_injected =
      test_pibt_post_commit_failure_injected_;
#endif
  storage->next_event_seq = next_event_seq_;
  storage->next_decision_id = next_decision_id_;
  storage->next_pibt_activation_id = next_pibt_activation_id_;
  storage->next_local_enqueue_sequence =
      next_local_enqueue_sequence_;
  storage->next_merge_request_lineage =
      next_merge_request_lineage_;
  storage->now = now_;
  storage->time_limit = time_limit_;
  storage->active_bag_count = active_bag_count_;
  storage->last_physical_repair_time =
      last_physical_repair_time_;
  storage->active_backlog_at_last_repair =
      active_backlog_at_last_repair_;
  storage->active_backlog_at_runtime_stop =
      active_backlog_at_runtime_stop_;
  storage->waits = waits_;
  // Kept for exact continuation of in-process diagnostics, but deliberately
  // excluded from deterministic state/result hashes as wall-clock telemetry.
  storage->decision_latencies_us = decision_latencies_us_;
  storage->phase = runtime_phase_;
  storage->state_digests = compute_runtime_state_digests();
  storage->state_sha256 =
      storage->state_digests.aggregate_sha256();
  return StateCheckpoint(storage, storage->state_sha256);
}

inline void EventDrivenJunctionRuntime::
restore_state_checkpoint(const StateCheckpoint& checkpoint) {
  // A restore attempt is itself a phase boundary.  Fail closed before even
  // inspecting the supplied checkpoint so a bad seal/graph/phase cannot
  // leave an already-Ready target able to process its previous event queue.
  runtime_phase_ = EventDrivenJunctionRuntimePhase::kIdle;
  staged_event_sink_ = nullptr;
  staged_merge_visibility_sink_ = nullptr;
  staged_destination_known_competitor_counts_ = nullptr;
  try {
  if (checkpoint.storage_ == nullptr) {
    throw std::invalid_argument(
        "cannot restore an empty runtime checkpoint");
  }
  const auto& storage = *checkpoint.storage_;
  g4irsf14_clone_detail::require_sha256(
      "checkpoint seal", checkpoint.sealed_state_sha256_);
  storage.state_digests.validate();
  if (checkpoint.sealed_state_sha256_ != storage.state_sha256 ||
      storage.state_sha256 !=
          storage.state_digests.aggregate_sha256()) {
    throw std::invalid_argument(
        "runtime checkpoint seal does not bind its state inventory");
  }
  if (storage.phase != EventDrivenJunctionRuntimePhase::kReady ||
      storage.events.empty()) {
    throw std::invalid_argument(
        "runtime checkpoint is not a live pre-pop boundary");
  }
  if (scorer_graph_fingerprint() != storage.graph_sha256) {
    throw std::invalid_argument(
        "runtime checkpoint graph identity mismatch");
  }
  config_ = storage.config;
  validate_config();
  scorer_model_.reset();
  scorer_static_hops_.clear();
  pibt_regret_prior_.clear();
  initialize_regret_prior();
  initialize_scorer();
  if (scorer_model_.has_value() !=
          storage.scorer_model.has_value() ||
      scorer_static_hops_ != storage.scorer_static_hops ||
      pibt_regret_prior_ != storage.pibt_regret_prior) {
    throw std::invalid_argument(
        "runtime checkpoint scorer derivation mismatch");
  }
  result_ = storage.result;
  bags_ = storage.bags;
  segment_runtime_ids_ = storage.segment_runtime_ids;
  junctions_ = storage.junctions;
  corridors_ = storage.corridors;
  physical_faults_ = storage.physical_faults;
  advertised_faults_ = storage.advertised_faults;
  congestion_beacons_ = storage.congestion_beacons;
  destination_merge_controllers_.clear();
  destination_merge_controllers_.reserve(
      storage.destination_merge_controllers.size());
  for (const auto& entry :
       storage.destination_merge_controllers) {
    destination_merge_controllers_.emplace(
        entry.first,
        DestinationMergeGrantCheckpointCodec::restore(
            entry.second));
  }
  pending_merge_dispatches_ =
      storage.pending_merge_dispatches;
  credit_ledger_ =
      ExpiringFirstEdgeCreditLedger::restore_exact_checkpoint(
          storage.credit_ledger);
  directed_inflight_counts_ =
      storage.directed_inflight_counts;
  fault_affected_bags_ = storage.fault_affected_bags;
  fault_affected_bags_by_edge_ =
      storage.fault_affected_bags_by_edge;
  fault_instances_by_bag_ = storage.fault_instances_by_bag;
  active_fault_instance_by_edge_ =
      storage.active_fault_instance_by_edge;
  repair_time_by_fault_instance_ =
      storage.repair_time_by_fault_instance;
  events_ = storage.events;
  staged_event_sink_ = nullptr;
  staged_merge_visibility_sink_ = nullptr;
  staged_destination_known_competitor_counts_ = nullptr;
  if (storage.g4irsf14_state.has_value()) {
    g4irsf14_state_ =
        restore_g4irsf14_state(*storage.g4irsf14_state);
  } else {
    g4irsf14_state_.reset();
  }
#ifdef CZR005_EVENT_RUNTIME_TESTING
  test_pibt_logical_failure_injected_ =
      storage.test_pibt_logical_failure_injected;
  test_merge_grant_prepare_failure_injected_ =
      storage.test_merge_grant_prepare_failure_injected;
  test_merge_grant_advertised_flip_injected_ =
      storage.test_merge_grant_advertised_flip_injected;
  test_merge_grant_physical_flip_injected_ =
      storage.test_merge_grant_physical_flip_injected;
  test_merge_grant_calendar_flip_injected_ =
      storage.test_merge_grant_calendar_flip_injected;
  test_merge_grant_queue_flip_injected_ =
      storage.test_merge_grant_queue_flip_injected;
  test_merge_grant_edge_exit_capability_drop_injected_ =
      storage.test_merge_grant_edge_exit_capability_drop_injected;
  test_merge_grant_edge_exit_physical_flip_injected_ =
      storage.test_merge_grant_edge_exit_physical_flip_injected;
  test_merge_grant_edge_exit_advertised_flip_injected_ =
      storage.test_merge_grant_edge_exit_advertised_flip_injected;
  test_merge_grant_edge_exit_calendar_remove_injected_ =
      storage.test_merge_grant_edge_exit_calendar_remove_injected;
  test_merge_grant_edge_exit_expiry_injected_ =
      storage.test_merge_grant_edge_exit_expiry_injected;
  test_merge_grant_edge_exit_wrong_owner_injected_ =
      storage.test_merge_grant_edge_exit_wrong_owner_injected;
  test_merge_grant_edge_exit_wrong_edge_injected_ =
      storage.test_merge_grant_edge_exit_wrong_edge_injected;
  test_merge_grant_edge_exit_wrong_destination_injected_ =
      storage.test_merge_grant_edge_exit_wrong_destination_injected;
  test_merge_grant_edge_exit_claimed_request_generation_tamper_injected_ =
      storage
          .test_merge_grant_edge_exit_claimed_request_generation_tamper_injected;
  test_merge_grant_edge_exit_claimed_queue_generation_tamper_injected_ =
      storage
          .test_merge_grant_edge_exit_claimed_queue_generation_tamper_injected;
  test_merge_grant_edge_exit_claimed_calendar_generation_tamper_injected_ =
      storage
          .test_merge_grant_edge_exit_claimed_calendar_generation_tamper_injected;
  test_merge_grant_edge_exit_live_queue_generation_advance_injected_ =
      storage
          .test_merge_grant_edge_exit_live_queue_generation_advance_injected;
  test_merge_grant_edge_exit_live_calendar_generation_advance_injected_ =
      storage
          .test_merge_grant_edge_exit_live_calendar_generation_advance_injected;
  test_pibt_post_commit_failure_injected_ =
      storage.test_pibt_post_commit_failure_injected;
#endif
  next_event_seq_ = storage.next_event_seq;
  next_decision_id_ = storage.next_decision_id;
  next_pibt_activation_id_ = storage.next_pibt_activation_id;
  next_local_enqueue_sequence_ =
      storage.next_local_enqueue_sequence;
  next_merge_request_lineage_ =
      storage.next_merge_request_lineage;
  now_ = storage.now;
  time_limit_ = storage.time_limit;
  active_bag_count_ = storage.active_bag_count;
  last_physical_repair_time_ =
      storage.last_physical_repair_time;
  active_backlog_at_last_repair_ =
      storage.active_backlog_at_last_repair;
  active_backlog_at_runtime_stop_ =
      storage.active_backlog_at_runtime_stop;
  waits_ = storage.waits;
  decision_latencies_us_ = storage.decision_latencies_us;
  runtime_phase_ = storage.phase;
  runtime_started_ = std::chrono::steady_clock::now();
  require_checkpoint_safe_boundary();
  validate_merge_capability_bijection();
  const auto restored_digests = compute_runtime_state_digests();
  if (restored_digests.aggregate_sha256() !=
          storage.state_sha256 ||
      restored_digests.canonical_payload() !=
          storage.state_digests.canonical_payload()) {
    throw std::invalid_argument(
        "runtime checkpoint restore changed deterministic state");
  }
  } catch (...) {
    runtime_phase_ = EventDrivenJunctionRuntimePhase::kIdle;
    staged_event_sink_ = nullptr;
    staged_merge_visibility_sink_ = nullptr;
    staged_destination_known_competitor_counts_ = nullptr;
    throw;
  }
}

inline void EventDrivenJunctionRuntime::
validate_merge_capability_bijection() const {
  std::size_t active_controller_grants = 0;
  for (const auto& entry : destination_merge_controllers_) {
    active_controller_grants +=
        entry.second.active_unconsumed_count();
    for (const auto& active : entry.second.active_) {
      const auto bag = bags_.find(active.owner_runtime_bag_id);
      if (bag == bags_.end() ||
          g4irsf14_state_ == nullptr) {
        throw std::invalid_argument(
            "restored active merge grant lacks its bag capability");
      }
      const auto merge =
          g4irsf14_state_->destination_merge_bags.find(
              active.owner_runtime_bag_id);
      if (merge ==
              g4irsf14_state_->destination_merge_bags.end() ||
          !merge->second.capability.has_value()) {
        throw std::invalid_argument(
            "restored active merge grant lacks its bag capability");
      }
      const auto& capability = *merge->second.capability;
      const auto destination =
          junctions_.find(active.edge.to_node);
      if (bag->second.status != BagStatus::kInTransit ||
          bag->second.transit_from != active.edge.from_node ||
          bag->second.transit_to != active.edge.to_node ||
          bag->second.transit_merge_grant !=
              capability.expectation() ||
          !entry.second.validates_active_capability(capability) ||
          destination == junctions_.end() ||
          !destination->second.service_calendar.contains_exact(
              active.owner_runtime_bag_id,
              active.slot_start,
              active.slot_end)) {
        throw std::invalid_argument(
            "restored merge grant bag/capability/calendar mismatch");
      }
    }
  }
  std::size_t bag_capabilities = 0;
  if (g4irsf14_state_ != nullptr) {
    for (const auto& entry :
         g4irsf14_state_->destination_merge_bags) {
      if (!entry.second.capability.has_value()) {
        continue;
      }
      ++bag_capabilities;
      const auto& capability = *entry.second.capability;
      if (capability.owner_runtime_bag_id() != entry.first) {
        throw std::invalid_argument(
            "restored merge capability owner/bag mismatch");
      }
      const auto controller =
          destination_merge_controllers_.find(
              capability.destination_node());
      if (controller == destination_merge_controllers_.end() ||
          !controller->second.validates_active_capability(
              capability)) {
        throw std::invalid_argument(
            "restored merge capability lacks its active controller record");
      }
    }
  }
  if (bag_capabilities != active_controller_grants) {
    throw std::invalid_argument(
        "restored merge controller/capability bijection failed");
  }
  std::size_t bag_expectations = 0;
  for (const auto& entry : bags_) {
    const auto& bag = entry.second;
    if (!bag.transit_merge_grant.required) {
      continue;
    }
    ++bag_expectations;
    if (bag.status != BagStatus::kInTransit ||
        bag.transit_merge_grant.owner_runtime_bag_id !=
            entry.first ||
        bag.transit_from !=
            bag.transit_merge_grant.edge.from_node ||
        bag.transit_to !=
            bag.transit_merge_grant.edge.to_node ||
        g4irsf14_state_ == nullptr) {
      throw std::invalid_argument(
          "restored merge expectation is not an exact in-transit bag");
    }
    const auto merge =
        g4irsf14_state_->destination_merge_bags.find(
            entry.first);
    if (merge ==
            g4irsf14_state_->destination_merge_bags.end() ||
        !merge->second.capability.has_value() ||
        merge->second.capability->expectation() !=
            bag.transit_merge_grant) {
      throw std::invalid_argument(
          "restored merge expectation lacks its exact capability");
    }
    const auto controller =
        destination_merge_controllers_.find(
            bag.transit_merge_grant.destination_node);
    const auto destination =
        junctions_.find(
            bag.transit_merge_grant.destination_node);
    if (controller ==
            destination_merge_controllers_.end() ||
        !controller->second.validates_active_capability(
            *merge->second.capability) ||
        destination == junctions_.end() ||
        !destination->second.service_calendar.contains_exact(
            entry.first,
            bag.transit_merge_grant.slot_start,
            bag.transit_merge_grant.slot_end)) {
      throw std::invalid_argument(
          "restored merge expectation lacks controller/calendar authority");
    }
  }
  if (bag_expectations != bag_capabilities) {
    throw std::invalid_argument(
        "restored merge bag expectation/capability bijection failed");
  }
}

inline void EventDrivenJunctionRuntime::
fingerprint_deterministic_summary(
    StateFingerprintWriter& writer,
    const EventRuntimeSummary& summary) {
  writer.string(summary.resource_semantics_id);
  writer.string(summary.resource_semantics_echo);
  writer.string(summary.pressure_mode);
  writer.string(summary.pressure_mode_echo);
  writer.string(summary.admission_mode);
  writer.string(summary.admission_mode_echo);
  writer.string(summary.framework_mode);
  writer.string(summary.framework_mode_echo);
  writer.string(summary.pibt_mode);
  writer.string(summary.pibt_mode_echo);
  writer.string(summary.priority_mode);
  writer.string(summary.priority_mode_echo);
  writer.string(summary.pibt_preference_mode);
  writer.string(summary.pibt_preference_mode_echo);
  writer.string(summary.credit_mode);
  writer.string(summary.priority_claim_boundary);
  writer.string(summary.scorer_mode);
  writer.string(summary.scorer_mode_echo);
  writer.string(summary.scorer_id);
  writer.string(summary.scorer_model_sha256);
  writer.string(summary.scorer_score_direction);
  writer.string(summary.scorer_claim_boundary);
  writer.boolean(summary.scorer_out_of_distribution_diagnostic);
  writer.boolean(summary.scorer_promotion_eligible);
  writer.boolean(summary.scorer_absolute_node_ids_enabled);
  writer.boolean(summary.scorer_static_precompute_only);
  writer.i64(summary.scorer_feature_dim);
  writer.i64(summary.scorer_explicit_default_feature_count);
  writer.u64(summary.scorer_decision_evaluation_count);
  writer.u64(summary.scorer_candidate_evaluation_count);
  writer.u64(summary.scorer_risk_abstain_count);
  writer.i64(summary.scorer_teacher_input_count);
  writer.i64(summary.scorer_future_route_input_count);
  writer.i64(summary.scorer_future_schedule_input_count);
  writer.i64(summary.scorer_posthoc_input_count);
  writer.i64(summary.scorer_runtime_global_scan_count);
  writer.i64(summary.pibt_max_depth);
  writer.boolean(summary.pibt_mode_diagnostic_only);
  writer.boolean(summary.framework_diagnostic_only);
  writer.string(summary.bounded_local_pibt_claim_boundary);
  writer.string(summary.first_edge_credit_claim_boundary);
  writer.floating(summary.entry_headway_seconds);
  writer.floating(summary.pressure_weight);
  writer.floating(summary.pressure_age_weight);
  writer.floating(summary.pressure_distance_bias);
  writer.floating(summary.credit_validity_seconds);
  writer.floating(summary.credit_snapshot_max_age_seconds);
  writer.i64(summary.credit_capacity_per_edge);
  writer.i64(summary.credit_lifecycle_limit);
  writer.i64(summary.selective_credit_contention_threshold);
  writer.i64(summary.pibt_regret_prior_record_count);
  writer.i64(summary.declared_max_events);
  writer.floating(summary.declared_max_simulation_time);
  writer.i64(summary.local_queue_capacity);
  writer.i64(summary.pibt_max_ready_bags);
  writer.i64(summary.pibt_max_local_resources);
  writer.i64(summary.pibt_max_candidates_per_bag);
  writer.i64(summary.requested_count);
  writer.i64(summary.completed_count);
  writer.i64(summary.failed_count);
  writer.i64(summary.peak_active_bag_count);
  writer.i64(summary.final_active_bag_count);
  writer.i64(summary.decision_count);
  writer.i64(summary.event_count);
  writer.i64(summary.bag_release_event_count);
  writer.i64(summary.arrive_junction_event_count);
  writer.i64(summary.junction_service_complete_event_count);
  writer.i64(summary.edge_enter_event_count);
  writer.i64(summary.edge_exit_event_count);
  writer.i64(summary.fault_event_count);
  writer.i64(summary.repair_event_count);
  writer.i64(summary.local_queue_update_event_count);
  writer.i64(summary.congestion_beacon_update_event_count);
  writer.u64(summary.source_admission_attempt_count);
  writer.u64(summary.source_admission_admitted_count);
  writer.u64(summary.source_admission_local_resource_hold_count);
  writer.u64(summary.source_admission_downstream_pressure_hold_count);
  writer.u64(summary.source_admission_beacon_read_count);
  writer.i64(summary.source_admission_max_observed_downstream_pressure);
  writer.u64(summary.first_edge_credit_issue_attempt_count);
  writer.u64(summary.first_edge_credit_issued_count);
  writer.u64(summary.first_edge_credit_validation_attempt_count);
  writer.u64(summary.first_edge_credit_validation_success_count);
  writer.u64(summary.first_edge_credit_bind_attempt_count);
  writer.u64(summary.first_edge_credit_bound_count);
  writer.u64(summary.first_edge_credit_consume_attempt_count);
  writer.u64(summary.first_edge_credit_consumed_count);
  writer.u64(summary.first_edge_credit_expired_count);
  writer.u64(summary.first_edge_credit_fault_revocation_count);
  writer.u64(summary.first_edge_credit_generation_revocation_count);
  writer.u64(summary.first_edge_credit_invalid_revocation_count);
  writer.u64(summary.first_edge_credit_duplicate_rejection_count);
  writer.u64(summary.first_edge_credit_capacity_rejection_count);
  writer.u64(summary.first_edge_credit_stale_snapshot_rejection_count);
  writer.u64(summary.first_edge_credit_physical_fault_rejection_count);
  writer.u64(summary.first_edge_credit_too_early_rejection_count);
  writer.u64(summary.first_edge_credit_unknown_rejection_count);
  writer.u64(summary.first_edge_credit_invalid_request_rejection_count);
  writer.u64(summary.first_edge_credit_lifecycle_dropped_count);
  writer.u64(summary.first_edge_credit_local_hold_count);
  writer.u64(summary.first_edge_credit_reissue_count);
  writer.u64(summary.selective_credit_trigger_count);
  writer.u64(summary.selective_credit_low_load_bypass_count);
  writer.u64(summary.selective_credit_merge_trigger_count);
  writer.u64(summary.selective_credit_contention_trigger_count);
  writer.i64(summary.first_edge_credit_active_count);
  writer.i64(summary.first_edge_credit_peak_active_count);
  writer.i64(summary.first_edge_credit_stored_active_count);
  writer.i64(summary.first_edge_credit_stored_lifecycle_count);
  writer.i64(summary.first_edge_credit_lifecycle_limit);
  writer.i64(summary.first_edge_credit_future_route_count);
  writer.i64(summary.first_edge_credit_global_scan_count);
  writer.boolean(summary.first_edge_credit_physical_interlock_bypass);
  writer.i64(summary.fault_notification_drop_count);
  writer.i64(summary.physical_fault_window_traversal_count);
  writer.i64(summary.physical_fault_edge_entry_violation_count);
  writer.i64(summary.fault_affected_bag_count);
  writer.i64(summary.fault_target_edge_candidate_exposure_count);
  writer.i64(summary.fault_target_edge_attempt_count);
  writer.i64(summary.physical_fault_interlock_rejection_count);
  writer.i64(summary.physical_fault_interlock_hold_count);
  writer.i64(summary.physical_fault_interlock_reroute_count);
  writer.i64(summary.local_fault_policy_action_count);
  writer.i64(summary.local_fault_policy_hold_count);
  writer.i64(summary.local_fault_policy_reroute_count);
  writer.i64(summary.fault_affected_completed_count);
  writer.floating(summary.fault_recovery_seconds);
  writer.floating(summary.repair_backlog_slope);
  writer.boolean(summary.fault_recovery_seconds_available);
  writer.boolean(summary.repair_backlog_slope_available);
  writer.string(summary.fault_recovery_metric_semantics);
  writer.string(summary.repair_backlog_slope_semantics);
  writer.i64(summary.reservation_conflicts);
  writer.i64(summary.shield_rejection_count);
  writer.i64(summary.stale_fault_shield_rejection_count);
  writer.i64(summary.pibt_lite_handoff_count);
  writer.i64(summary.same_bag_alternative_edge_scan_handoff_count);
  writer.u64(summary.bounded_local_pibt_activation_count);
  writer.u64(summary.bounded_local_pibt_attempt_count);
  writer.u64(summary.bounded_local_pibt_prepare_count);
  writer.u64(summary.bounded_local_pibt_validate_count);
  writer.u64(summary.bounded_local_pibt_commit_count);
  writer.u64(summary.bounded_local_pibt_wait_for_cycle_count);
  writer.u64(summary.bounded_local_pibt_handoff_count);
  writer.u64(summary.bounded_local_pibt_candidate_bound_rejection_count);
  writer.u64(summary.bounded_local_pibt_candidate_materialization_count);
  writer.u64(summary.bounded_local_pibt_not_applicable_count);
  writer.u64(summary.bounded_local_pibt_same_bag_fallback_count);
  writer.u64(summary.bounded_local_pibt_proposal_batch_count);
  writer.u64(summary.bounded_local_pibt_proposed_action_count);
  writer.u64(summary.bounded_local_pibt_committed_batch_count);
  writer.u64(summary.bounded_local_pibt_committed_action_count);
  writer.u64(summary.bounded_local_pibt_inherited_action_count);
  writer.u64(summary.bounded_local_pibt_blocker_move_attempt_count);
  writer.u64(summary.bounded_local_pibt_backtrack_count);
  writer.u64(summary.bounded_local_pibt_cycle_guard_count);
  writer.u64(summary.bounded_local_pibt_rollback_count);
  writer.u64(summary.bounded_local_pibt_fault_rejection_count);
  writer.u64(summary.bounded_local_pibt_prepare_rejection_count);
  writer.u64(summary.bounded_local_pibt_commit_rejection_count);
  writer.u64(summary.bounded_local_pibt_post_commit_failure_injection_count);
  writer.u64(summary.bounded_local_pibt_rollback_fingerprint_match_count);
  writer.u64(
      summary.bounded_local_pibt_rollback_calendar_generation_match_count);
  writer.i64(summary.bounded_local_pibt_max_inheritance_depth);
  writer.i64(summary.bounded_local_pibt_max_slice_bags);
  writer.i64(summary.bounded_local_pibt_max_slice_resources);
  writer.i64(summary.bounded_local_pibt_max_candidates_per_bag);
  writer.i64(summary.bounded_local_pibt_max_transaction_credit_entries);
  writer.i64(summary.bounded_local_pibt_max_transaction_bag_entries);
  writer.i64(
      summary.bounded_local_pibt_max_transaction_junction_scalar_entries);
  writer.i64(summary.bounded_local_pibt_max_transaction_action_deltas);
  writer.i64(
      summary.bounded_local_pibt_max_transaction_calendar_generation_entries);
  writer.boolean(summary.bounded_local_pibt_classical_completeness_claimed);
  writer.i64(summary.deadlock_count);
  writer.i64(summary.resolved_deadlock_count);
  writer.i64(summary.unresolved_deadlock_count);
  writer.i64(summary.deadlock_escape_activation_count);
  writer.i64(summary.starvation_count);
  writer.i64(summary.loop_count);
  writer.i64(summary.runtime_full_astar_calls);
  writer.i64(summary.global_reservation_scan_count);
  writer.i64(summary.max_edges_selected_per_arrive);
  writer.i64(summary.max_edges_selected_per_bag_per_decision);
  writer.i64(summary.max_actions_committed_per_pibt_batch);
  writer.i64(summary.release_selected_edge_count);
  writer.i64(summary.max_history_observed);
  writer.i64(summary.max_junction_queue_length);
  writer.i64(summary.max_source_queue_length);
  writer.i64(summary.max_local_calendar_intervals);
  writer.i64(summary.max_corridor_calendar_intervals);
  writer.i64(summary.max_same_directed_edge_inflight);
  writer.i64(summary.max_candidate_count);
  writer.i64(summary.two_step_reservation_count);
  writer.i64(summary.diagnostic_hops);
  writer.i64(summary.decision_trace_seen_count);
  writer.i64(summary.decision_trace_shard_seen_count);
  writer.i64(summary.decision_trace_stored_count);
  writer.i64(summary.hold_trace_stored_count);
  writer.i64(summary.trace_limit);
  writer.i64(summary.event_trace_limit);
  writer.boolean(summary.event_trace_limit_inherited);
  writer.i64(summary.trace_shard_count);
  writer.i64(summary.trace_shard_index);
  writer.floating(summary.max_individual_wait);
  writer.floating(summary.max_source_queue_delay);
  writer.floating(summary.fairness_jain);
  writer.floating(summary.max_deadlock_duration);
  writer.floating(summary.end_time);
  writer.boolean(summary.event_limit_reached);
  writer.boolean(summary.time_limit_reached);
  writer.boolean(summary.sensor_loss_mode_used);
  writer.boolean(summary.source_admission_enabled);
  writer.boolean(summary.fault_policy_enabled);
  writer.boolean(summary.legacy_pibt_lite_enabled);
  writer.boolean(summary.decision_trace_truncated);
  writer.boolean(summary.event_trace_truncated);
  writer.u64(summary.repaired_task_reentry_count);
  writer.u64(summary.repaired_task_reentry_boost_cleared_count);
  writer.i64(summary.priority_teacher_input_count);
  writer.i64(summary.priority_future_route_input_count);
  writer.i64(summary.priority_global_scan_count);
  writer.u64(summary.pibt_preference_candidate_count);
  writer.u64(summary.pibt_preference_unique_exit_penalty_count);
  writer.u64(summary.pibt_preference_wait_cycle_penalty_count);
  writer.u64(summary.pibt_preference_backtrack_penalty_count);
  writer.u64(summary.pibt_preference_regret_prior_hit_count);
  writer.string(summary.event_semantics);
  writer.string(summary.event_semantics_echo);
  writer.boolean(summary.opportunity_telemetry_enabled);
  writer.u64(summary.source_arbitration_event_count);
  writer.u64(summary.junction_arbitration_event_count);
  writer.u64(summary.stale_arbitration_event_count);
  writer.u64(summary.superseded_arbitration_event_rejected_count);
  writer.u64(summary.duplicate_same_time_arbitration_prevented_count);
  writer.u64(summary.source_same_timestamp_batch_count);
  writer.u64(summary.junction_same_timestamp_batch_count);
  writer.i64(summary.max_source_arbitration_batch_size);
  writer.i64(summary.max_junction_arbitration_batch_size);
  writer.u64(summary.opportunity_event_queue_inspection_count);
  writer.u64(summary.source_opportunity_total_count);
  writer.u64(summary.source_opportunity_stored_count);
  writer.u64(summary.source_opportunity_dropped_count);
  writer.u64(summary.junction_opportunity_total_count);
  writer.u64(summary.junction_opportunity_stored_count);
  writer.u64(summary.junction_opportunity_dropped_count);
  writer.u64(summary.merge_visibility_total_count);
  writer.u64(summary.merge_visibility_stored_count);
  writer.u64(summary.merge_visibility_dropped_count);
  writer.u64(summary.event_seq_audit_total_count);
  writer.u64(summary.event_seq_audit_stored_count);
  writer.u64(summary.event_seq_audit_dropped_count);
  writer.u64(summary.arbitration_batch_total_count);
  writer.u64(summary.arbitration_batch_stored_count);
  writer.u64(summary.arbitration_batch_dropped_count);
  writer.u64(summary.fault_generation_commit_recheck_count);
  writer.i64(summary.microphase_runtime_global_scan_count);
  writer.floating(summary.artificial_batch_delay_seconds);
  writer.u64(summary.destination_merge_arbitration_event_count);
  writer.u64(
      summary.g4irsf14_i2_live_eligible_multi_request_boundary_count);
  writer.u64(summary.g4irsf14_i5_prefilter_candidate_count);
  writer.u64(
      summary.g4irsf14_i5_applicable_ready_slice_boundary_count);
  writer.u64(summary.merge_grant_request_count);
  writer.u64(summary.merge_grant_issued_count);
  writer.u64(summary.merge_grant_prepared_count);
  writer.u64(summary.merge_grant_committed_count);
  writer.u64(summary.merge_grant_issued_transition_count);
  writer.u64(summary.merge_grant_prepared_transition_count);
  writer.u64(summary.merge_grant_committed_transition_count);
  writer.u64(summary.merge_grant_consumed_count);
  writer.u64(
      summary.merge_grant_inflight_fault_generation_recovery_count);
  writer.u64(summary.merge_grant_expired_count);
  writer.u64(summary.merge_grant_request_expired_count);
  writer.u64(summary.merge_grant_grant_expired_count);
  writer.u64(summary.merge_grant_revoked_count);
  writer.u64(summary.merge_grant_revoked_fault_count);
  writer.u64(summary.merge_grant_revoked_stale_state_count);
  writer.u64(summary.merge_grant_revoked_replan_current_edge_count);
  writer.u64(summary.merge_grant_rolled_back_count);
  writer.u64(summary.merge_grant_post_commit_revoked_count);
  writer.u64(summary.merge_grant_post_commit_expired_count);
  writer.u64(summary.merge_grant_post_commit_rollback_count);
  writer.u64(summary.merge_grant_exact_slot_busy_count);
  writer.u64(summary.merge_grant_active_grant_rejection_count);
  writer.u64(summary.merge_grant_queue_capacity_block_count);
  writer.u64(summary.merge_grant_contended_loser_retry_count);
  writer.u64(summary.merge_grant_lifecycle_transition_count);
  writer.u64(summary.merge_grant_lifecycle_stored_count);
  writer.u64(summary.merge_grant_lifecycle_dropped_count);
  writer.u64(summary.merge_grant_terminal_request_count);
  writer.u64(summary.merge_grant_outstanding_request_count);
  writer.u64(summary.merge_grant_goal_exempt_bypass_count);
  writer.u64(summary.merge_grant_stale_arbitration_count);
  writer.u64(summary.merge_grant_duplicate_wakeup_prevented_count);
  writer.string(summary.merge_grant_timing_mode);
  writer.u64(summary.merge_grant_service_opportunity_count);
  writer.u64(summary.merge_grant_multi_candidate_opportunity_count);
  writer.u64(summary.merge_grant_true_competition_count);
  writer.u64(summary.merge_grant_order_mutation_count);
  writer.u64(summary.merge_grant_candidate_total_count);
  writer.u64(summary.merge_grant_wakeup_scheduled_count);
  writer.u64(summary.merge_grant_wakeup_coalesced_count);
  writer.u64(summary.merge_grant_stale_wakeup_count);
  writer.u64(summary.merge_grant_opportunity_trace_total_count);
  writer.u64(summary.merge_grant_opportunity_trace_stored_count);
  writer.u64(summary.merge_grant_opportunity_trace_dropped_count);
  writer.i64(summary.merge_grant_peak_pending_requests);
  writer.i64(summary.merge_grant_peak_active_unconsumed);
  writer.i64(summary.merge_grant_final_active_unconsumed);
  writer.boolean(summary.merge_grant_conservation_holds);
  writer.boolean(summary.merge_grant_active_bijection_holds);
  writer.boolean(summary.merge_grant_runtime_owned_capability);
  writer.boolean(summary.merge_grant_exact_slot_no_future_shift);
  if (!summary.g4irsf18_merge_policy_mode.empty()) {
    writer.string(summary.g4irsf18_merge_policy_mode);
    writer.string(summary.g4irsf18_merge_policy_schema);
    writer.string(summary.g4irsf18_merge_policy_family);
    writer.string(summary.g4irsf18_merge_feature_contract);
    writer.boolean(summary.g4irsf18_merge_artifact_valid);
    writer.boolean(
        summary
            .g4irsf18_merge_artifact_production_closed_loop_authorized);
    writer.boolean(
        summary.g4irsf18_merge_research_closed_loop_authorized);
    writer.boolean(summary.g4irsf18_merge_fixed_research_workload);
    writer.boolean(
        summary.g4irsf18_merge_production_closed_loop_authorized);
    writer.boolean(summary.g4irsf18_merge_offline_gate_passed);
    writer.floating(summary.g4irsf18_merge_coverage_cap);
    writer.i64(summary.g4irsf18_merge_max_overrides_per_segment);
    writer.boolean(summary.g4irsf18_merge_kill_switch_configured);
    writer.boolean(summary.g4irsf18_merge_kill_switch_tripped);
    writer.string(summary.g4irsf18_merge_kill_switch_reason);
    writer.u64(summary.g4irsf18_merge_model_opportunity_count);
    writer.u64(summary.g4irsf18_merge_model_eligible_count);
    writer.u64(summary.g4irsf18_merge_model_proposal_count);
    writer.u64(summary.g4irsf18_merge_model_applied_count);
    writer.u64(summary.g4irsf18_merge_distinct_action_mutation_count);
    writer.u64(summary.g4irsf18_merge_model_ood_count);
    writer.u64(summary.g4irsf18_merge_model_invalid_count);
    writer.u64(summary.g4irsf18_merge_model_fallback_count);
    writer.u64(summary.g4irsf18_merge_j2_fallback_count);
    writer.u64(summary.g4irsf18_merge_tie_fifo_fallback_count);
    writer.u64(summary.g4irsf18_merge_shadow_fallback_count);
    writer.u64(summary.g4irsf18_merge_authorization_fallback_count);
    writer.u64(summary.g4irsf18_merge_coverage_cap_fallback_count);
    writer.u64(summary.g4irsf18_merge_override_cap_fallback_count);
    writer.u64(summary.g4irsf18_merge_starvation_guard_fallback_count);
    writer.u64(summary.g4irsf18_merge_kill_switch_trip_count);
    writer.u64(summary.g4irsf18_merge_kill_switch_fallback_count);
    writer.u64(summary.g4irsf18_merge_model_ownership_count);
    writer.u64(summary.g4irsf18_merge_coverage_eligible_seen_count);
    writer.i64(summary.g4irsf18_merge_runtime_global_scan_count);
    writer.i64(summary.g4irsf18_merge_future_route_input_count);
    writer.i64(summary.g4irsf18_merge_future_schedule_input_count);
    writer.i64(summary.g4irsf18_merge_full_astar_call_count);
  }
}

inline G4IRSF14CloneReplayHashes
EventDrivenJunctionRuntime::compute_replay_hashes_projection() const {
  StateFingerprintWriter complete("complete_bags");
  std::vector<const EventRuntimeBagResult*> ordered_bags;
  ordered_bags.reserve(result_.bags.size());
  for (const auto& bag : result_.bags) {
    ordered_bags.push_back(&bag);
  }
  std::sort(
      ordered_bags.begin(), ordered_bags.end(),
      [](const auto* left, const auto* right) {
        return std::tie(left->runtime_bag_id, left->segment_id) <
               std::tie(right->runtime_bag_id, right->segment_id);
      });
  complete.u64(ordered_bags.size());
  for (const auto* bag : ordered_bags) {
    complete.string(bag->segment_id);
    complete.i64(bag->task_id);
    complete.i64(bag->runtime_bag_id);
    complete.i64(bag->start);
    complete.i64(bag->goal);
    complete.i64(bag->final_node);
    complete.floating(bag->release_time);
    complete.floating(bag->arrival_time);
    complete.floating(bag->deadline);
    complete.string(bag->source);
    complete.floating(bag->admitted_time);
    complete.floating(bag->finish_time);
    complete.floating(bag->source_queue_delay);
    complete.floating(bag->total_local_wait);
    complete.floating(bag->junction_queue_wait_seconds);
    complete.floating(bag->merge_grant_wait_seconds);
    complete.floating(bag->edge_travel_time_seconds);
    complete.floating(bag->node_service_time_seconds);
    complete.floating(bag->loop_extra_time_seconds);
    complete.floating(bag->goal_completion_time_seconds);
    complete.i64(bag->decision_count);
    complete.i64(bag->retry_count);
    complete.i64(bag->loop_count);
    complete.boolean(bag->completed);
    complete.boolean(bag->starved);
    complete.string(bag->failure_reason);
    complete.u64(bag->short_history.size());
    for (const int node : bag->short_history) {
      complete.i64(node);
    }
  }

  StateFingerprintWriter segments("segment_result");
  std::vector<const EventRuntimeBagResult*> ordered_segments =
      ordered_bags;
  std::sort(
      ordered_segments.begin(), ordered_segments.end(),
      [](const auto* left, const auto* right) {
        return std::tie(left->segment_id, left->runtime_bag_id) <
               std::tie(right->segment_id, right->runtime_bag_id);
      });
  segments.u64(ordered_segments.size());
  for (const auto* bag : ordered_segments) {
    segments.string(bag->segment_id);
    segments.i64(bag->task_id);
    segments.i64(bag->runtime_bag_id);
    segments.boolean(bag->completed);
    segments.boolean(bag->starved);
    segments.i64(bag->final_node);
    segments.floating(bag->finish_time);
    segments.floating(bag->goal_completion_time_seconds);
    segments.floating(bag->source_queue_delay);
    segments.floating(bag->total_local_wait);
    segments.floating(bag->junction_queue_wait_seconds);
    segments.floating(bag->merge_grant_wait_seconds);
    segments.i64(bag->decision_count);
    segments.i64(bag->retry_count);
    segments.i64(bag->loop_count);
    segments.string(bag->failure_reason);
  }

  StateFingerprintWriter junctions("junction_state");
  std::vector<const EventRuntimeJunctionResult*> ordered_junctions;
  ordered_junctions.reserve(result_.junctions.size());
  for (const auto& junction : result_.junctions) {
    ordered_junctions.push_back(&junction);
  }
  std::sort(
      ordered_junctions.begin(), ordered_junctions.end(),
      [](const auto* left, const auto* right) {
        return left->node < right->node;
      });
  junctions.u64(ordered_junctions.size());
  for (const auto* junction : ordered_junctions) {
    junctions.i64(junction->node);
    junctions.i64(junction->final_source_queue_length);
    junctions.i64(junction->peak_source_queue_length);
    junctions.i64(junction->final_junction_queue_length);
    junctions.i64(junction->peak_junction_queue_length);
    junctions.i64(
        junction->final_service_calendar_intervals);
    junctions.i64(
        junction->peak_service_calendar_intervals);
    // final/peak accounted bytes are allocator/layout diagnostics and are
    // intentionally absent from the deterministic projection.
    junctions.u64(junction->service_reservation_count);
    junctions.floating(
        junction->cumulative_service_reserved_seconds);
    junctions.floating(
        junction->first_service_reservation_start_time);
    junctions.floating(
        junction->last_service_reservation_end_time);
    junctions.i64(junction->scheduled_incoming);
    junctions.floating(junction->next_dispatch_time);
  }

  const auto& summary = result_.summary;
  StateFingerprintWriter algorithm("algorithm_summary");
  fingerprint_deterministic_summary(algorithm, summary);
  // The following compact legacy projection is retained as an append-only
  // v2 compatibility suffix; the exhaustive projection above is normative.
  algorithm.string(summary.resource_semantics_id);
  algorithm.string(summary.pressure_mode);
  algorithm.string(summary.admission_mode);
  algorithm.string(summary.framework_mode);
  algorithm.string(summary.pibt_mode);
  algorithm.string(summary.priority_mode);
  algorithm.string(summary.pibt_preference_mode);
  algorithm.string(summary.credit_mode);
  algorithm.string(summary.scorer_mode);
  algorithm.string(summary.scorer_id);
  algorithm.string(summary.scorer_model_sha256);
  algorithm.string(summary.event_semantics);
  algorithm.i64(summary.requested_count);
  algorithm.i64(summary.completed_count);
  algorithm.i64(summary.failed_count);
  algorithm.i64(summary.peak_active_bag_count);
  algorithm.i64(summary.final_active_bag_count);
  algorithm.i64(summary.decision_count);
  algorithm.i64(summary.event_count);
  algorithm.i64(summary.bag_release_event_count);
  algorithm.i64(summary.arrive_junction_event_count);
  algorithm.i64(summary.junction_service_complete_event_count);
  algorithm.i64(summary.edge_enter_event_count);
  algorithm.i64(summary.edge_exit_event_count);
  algorithm.i64(summary.fault_event_count);
  algorithm.i64(summary.repair_event_count);
  algorithm.i64(summary.local_queue_update_event_count);
  algorithm.i64(summary.congestion_beacon_update_event_count);
  algorithm.u64(summary.source_arbitration_event_count);
  algorithm.u64(summary.junction_arbitration_event_count);
  algorithm.u64(summary.destination_merge_arbitration_event_count);
  algorithm.u64(
      summary.g4irsf14_i2_live_eligible_multi_request_boundary_count);
  algorithm.u64(summary.g4irsf14_i5_prefilter_candidate_count);
  algorithm.u64(
      summary.g4irsf14_i5_applicable_ready_slice_boundary_count);
  algorithm.i64(summary.reservation_conflicts);
  algorithm.i64(summary.physical_fault_edge_entry_violation_count);
  algorithm.i64(summary.runtime_full_astar_calls);
  algorithm.i64(summary.global_reservation_scan_count);
  algorithm.i64(summary.priority_future_route_input_count);
  algorithm.i64(summary.priority_global_scan_count);
  algorithm.i64(summary.scorer_future_route_input_count);
  algorithm.i64(summary.scorer_future_schedule_input_count);
  algorithm.i64(summary.scorer_runtime_global_scan_count);
  algorithm.i64(summary.microphase_runtime_global_scan_count);
  algorithm.i64(summary.deadlock_count);
  algorithm.i64(summary.resolved_deadlock_count);
  algorithm.i64(summary.unresolved_deadlock_count);
  algorithm.i64(summary.starvation_count);
  algorithm.i64(summary.loop_count);
  algorithm.i64(summary.max_edges_selected_per_arrive);
  algorithm.i64(
      summary.max_edges_selected_per_bag_per_decision);
  algorithm.i64(summary.max_actions_committed_per_pibt_batch);
  algorithm.u64(summary.bounded_local_pibt_activation_count);
  algorithm.u64(summary.bounded_local_pibt_attempt_count);
  algorithm.u64(summary.bounded_local_pibt_commit_count);
  algorithm.u64(summary.bounded_local_pibt_rollback_count);
  algorithm.u64(summary.first_edge_credit_issued_count);
  algorithm.u64(summary.first_edge_credit_consumed_count);
  algorithm.u64(summary.first_edge_credit_expired_count);
  algorithm.u64(summary.first_edge_credit_fault_revocation_count);
  algorithm.u64(
      summary.first_edge_credit_generation_revocation_count);
  algorithm.u64(summary.merge_grant_request_count);
  algorithm.u64(summary.merge_grant_issued_count);
  algorithm.u64(summary.merge_grant_prepared_count);
  algorithm.u64(summary.merge_grant_committed_count);
  algorithm.u64(summary.merge_grant_consumed_count);
  algorithm.u64(
      summary.merge_grant_inflight_fault_generation_recovery_count);
  algorithm.u64(summary.merge_grant_expired_count);
  algorithm.u64(summary.merge_grant_revoked_count);
  algorithm.u64(summary.merge_grant_rolled_back_count);
  algorithm.u64(summary.merge_grant_outstanding_request_count);
  algorithm.boolean(summary.merge_grant_conservation_holds);
  algorithm.boolean(summary.merge_grant_active_bijection_holds);
  algorithm.i64(summary.max_junction_queue_length);
  algorithm.i64(summary.max_source_queue_length);
  algorithm.i64(summary.max_local_calendar_intervals);
  algorithm.i64(summary.max_corridor_calendar_intervals);
  algorithm.i64(summary.max_same_directed_edge_inflight);
  algorithm.floating(summary.max_individual_wait);
  algorithm.floating(summary.max_source_queue_delay);
  algorithm.floating(summary.fairness_jain);
  algorithm.floating(summary.max_deadlock_duration);
  algorithm.floating(summary.end_time);
  algorithm.boolean(summary.event_limit_reached);
  algorithm.boolean(summary.time_limit_reached);
  algorithm.boolean(summary.decision_trace_truncated);
  algorithm.boolean(summary.event_trace_truncated);

  StateFingerprintWriter deterministic("deterministic_result");
  deterministic.string(complete.sha256());
  deterministic.string(segments.sha256());
  deterministic.string(junctions.sha256());
  deterministic.string(algorithm.sha256());
  deterministic.u64(result_.events.size());
  for (const auto& event : result_.events) {
    deterministic.u64(event.seq);
    deterministic.string(event.event);
    deterministic.floating(event.time);
    deterministic.i64(event.task_id);
    deterministic.i64(event.runtime_bag_id);
    deterministic.string(event.segment_id);
    deterministic.i64(event.node);
    deterministic.i64(event.from_node);
    deterministic.i64(event.to_node);
    deterministic.string(event.reason);
    deterministic.i64(event.selected_edge_count);
  }
  const auto fingerprint_decisions =
      [&](const std::vector<EventDecisionTraceRow>& rows) {
        deterministic.u64(rows.size());
        for (const auto& row : rows) {
          deterministic.u64(row.decision_id);
          deterministic.u64(row.arrive_event_seq);
          deterministic.floating(row.event_time);
          deterministic.i64(row.task_id);
          deterministic.i64(row.runtime_bag_id);
          deterministic.string(row.segment_id);
          deterministic.i64(row.current_node);
          deterministic.i64(row.goal_node);
          deterministic.i64(row.model_prediction);
          deterministic.floating(row.model_margin);
          deterministic.boolean(row.risk_gate_triggered);
          deterministic.boolean(row.scorer_risk_abstain);
          deterministic.u64(row.scorer_risk_reasons.size());
          for (const auto& reason : row.scorer_risk_reasons) {
            deterministic.string(reason);
          }
          deterministic.string(row.scorer_id);
          deterministic.string(row.scorer_effective_id);
          deterministic.i64(row.scorer_raw_prediction);
          deterministic.floating(row.scorer_raw_margin);
          deterministic.i64(row.fallback_selected_next);
          deterministic.i64(row.selected_next);
          deterministic.string(row.decision_source);
          deterministic.string(row.rule_reason);
          deterministic.i64(row.junction_queue_length);
          deterministic.floating(
              row.junction_next_dispatch_time);
          deterministic.i64(
              row.advertised_faulted_outgoing_count);
          deterministic.floating(
              row.max_fault_message_age_seconds);
          deterministic.u64(row.short_history.size());
          for (const int node : row.short_history) {
            deterministic.i64(node);
          }
          deterministic.boolean(row.full_astar_used);
          deterministic.string(row.priority_mode);
          deterministic.string(row.task_class);
          deterministic.floating(row.priority_slack_seconds);
          deterministic.floating(row.priority_age_seconds);
          deterministic.i64(row.priority_local_contention);
          deterministic.u64(row.priority_fault_generation);
          deterministic.u64(row.priority_enqueue_sequence);
          deterministic.string(row.pibt_preference_mode);
          deterministic.u64(row.candidates.size());
          for (const auto& candidate : row.candidates) {
            deterministic.i64(candidate.next_node);
            deterministic.floating(candidate.static_potential);
            deterministic.floating(candidate.travel_time);
            deterministic.i64(candidate.target_queue_length);
            deterministic.i64(
                candidate.target_scheduled_incoming);
            deterministic.floating(
                candidate.corridor_next_available);
            deterministic.floating(
                candidate.target_next_available);
            deterministic.boolean(candidate.advertised_fault);
            deterministic.floating(
                candidate.fault_message_age_seconds);
            deterministic.i64(candidate.recent_visit_count);
            deterministic.i64(candidate.two_hop_queue_pressure);
            deterministic.i64(
                candidate.current_goal_queue_length);
            deterministic.i64(
                candidate.target_goal_queue_length);
            deterministic.i64(
                candidate.target_goal_scheduled_incoming);
            deterministic.floating(
                candidate.current_goal_max_wait);
            deterministic.floating(
                candidate.goal_conditioned_differential);
            deterministic.floating(
                candidate.estimated_service_rate);
            deterministic.floating(
                candidate.service_weighted_pressure);
            deterministic.boolean(
                candidate.first_edge_credit_required);
            deterministic.boolean(
                candidate.first_edge_credit_matches);
            deterministic.boolean(
                candidate.first_edge_credit_valid);
            deterministic.floating(
                candidate.first_edge_credit_slack_seconds);
            deterministic.floating(candidate.model_score);
            deterministic.floating(
                candidate.pre_fault_policy_score);
            deterministic.floating(candidate.scorer_raw_score);
            deterministic.floating(
                candidate.scorer_raw_bottleneck);
            deterministic.boolean(
                candidate.scorer_raw_score_available);
            deterministic.boolean(candidate.shield_allowed);
            deterministic.string(candidate.shield_reason);
          }
        }
      };
  fingerprint_decisions(result_.decisions);
  fingerprint_decisions(result_.hold_attempts);
  deterministic.u64(result_.fault_events.size());
  for (const auto& row : result_.fault_events) {
    deterministic.u64(row.seq);
    deterministic.string(row.event);
    deterministic.string(row.phase);
    deterministic.floating(row.time);
    deterministic.i64(row.from_node);
    deterministic.i64(row.to_node);
    deterministic.i64(row.physical_active_count);
    deterministic.i64(row.physical_generation);
    deterministic.i64(row.inflight_traversal_count);
    deterministic.boolean(row.notification_dropped);
    deterministic.i64(row.task_id);
    deterministic.i64(row.runtime_bag_id);
    deterministic.string(row.segment_id);
    deterministic.i64(row.current_node);
    deterministic.i64(row.intended_next_node);
    deterministic.i64(row.selected_next_node);
    deterministic.boolean(row.fault_policy_enabled);
  }
  deterministic.u64(result_.credit_events.size());
  for (const auto& row : result_.credit_events) {
    deterministic.floating(row.time);
    deterministic.string(row.action);
    deterministic.string(row.reason);
    deterministic.u64(row.credit_id);
    deterministic.i64(row.from_node);
    deterministic.i64(row.to_node);
    deterministic.i64(row.goal);
    deterministic.floating(row.earliest);
    deterministic.floating(row.latest);
    deterministic.u64(row.generation);
    deterministic.floating(row.expiry);
    deterministic.i64(row.capacity);
    deterministic.i64(row.owner_or_unbound);
    deterministic.i64(row.fault_generation);
    deterministic.string(row.state);
    deterministic.i64(row.task_id);
    deterministic.string(row.segment_id);
  }
  deterministic.u64(result_.pibt_events.size());
  for (const auto& row : result_.pibt_events) {
    deterministic.u64(row.activation_id);
    deterministic.floating(row.time);
    deterministic.i64(row.trigger_node);
    deterministic.i64(row.trigger_runtime_bag_id);
    deterministic.string(row.mode);
    deterministic.string(row.outcome);
    deterministic.string(row.blocker);
    deterministic.i64(row.local_slice_bag_count);
    deterministic.i64(row.local_slice_resource_count);
    deterministic.i64(row.local_slice_candidate_count);
    deterministic.i64(row.proposed_action_count);
    deterministic.i64(row.committed_action_count);
    deterministic.i64(row.inherited_action_count);
    deterministic.i64(row.max_inheritance_depth);
    deterministic.i64(row.backtrack_count);
    deterministic.i64(row.cycle_guard_count);
    deterministic.i64(row.rollback_count);
    deterministic.i64(row.transaction_credit_entry_count);
    deterministic.i64(row.transaction_bag_entry_count);
    deterministic.i64(
        row.transaction_junction_scalar_entry_count);
    deterministic.i64(row.transaction_action_delta_count);
    deterministic.u64(row.actions.size());
    for (const auto& action : row.actions) {
      deterministic.i64(action.bag_id);
      deterministic.i64(action.from_node);
      deterministic.i64(action.next_node);
      deterministic.u64(action.edge_resource);
      deterministic.u64(action.claimed_resources.size());
      for (const auto resource : action.claimed_resources) {
        deterministic.u64(resource);
      }
      deterministic.u64(action.expected_fault_generation);
      deterministic.i64(action.priority_rank);
      deterministic.i64(action.inheritance_depth);
      deterministic.boolean(action.inherited);
      deterministic.floating(action.local_score);
    }
  }
  deterministic.u64(
      result_.source_admission_opportunities.size());
  for (const auto& row :
       result_.source_admission_opportunities) {
    deterministic.floating(row.event_time);
    deterministic.u64(row.timestamp_bits);
    deterministic.i64(row.source_node);
    deterministic.i64(row.queue_length_before_enqueue);
    deterministic.i64(row.queue_length_after_enqueue);
    deterministic.i64(row.queue_length_before_arbitration);
    deterministic.i64(row.queue_length_after_arbitration);
    deterministic.i64(row.same_timestamp_release_batch_size);
    deterministic.i64(
        row.same_time_pending_source_releases);
    deterministic.i64(
        row.same_time_pending_shared_merge_releases);
    deterministic.i64(row.ready_set_size);
    deterministic.i64(row.priority_comparison_count);
    deterministic.i64(row.chosen_task_id);
    deterministic.i64(row.chosen_runtime_bag_id);
    deterministic.string(row.chosen_segment_id);
    deterministic.string(row.queue_discipline);
    deterministic.u64(row.event_seq);
    deterministic.u64(row.arbitration_generation);
    deterministic.boolean(row.batched_arbitration);
  }
  deterministic.u64(
      result_.junction_arbitration_opportunities.size());
  for (const auto& row :
       result_.junction_arbitration_opportunities) {
    deterministic.floating(row.event_time);
    deterministic.u64(row.timestamp_bits);
    deterministic.i64(row.junction_node);
    deterministic.i64(row.queue_length_before_enqueue);
    deterministic.i64(row.queue_length_after_enqueue);
    deterministic.i64(row.queue_length_before_arbitration);
    deterministic.i64(row.queue_length_after_arbitration);
    deterministic.i64(
        row.same_timestamp_arrival_batch_size);
    deterministic.i64(row.same_time_pending_arrivals);
    deterministic.i64(
        row.same_time_pending_shared_merge_requests);
    deterministic.i64(row.ready_set_size);
    deterministic.i64(row.priority_comparison_count);
    deterministic.i64(row.pibt_slice_bag_count);
    deterministic.i64(row.pibt_owner_count);
    deterministic.i64(row.chosen_task_id);
    deterministic.i64(row.chosen_runtime_bag_id);
    deterministic.string(row.chosen_segment_id);
    deterministic.u64(row.event_seq);
    deterministic.u64(row.arbitration_generation);
    deterministic.boolean(row.batched_arbitration);
  }
  deterministic.u64(result_.merge_request_visibility.size());
  for (const auto& row : result_.merge_request_visibility) {
    deterministic.floating(row.event_time);
    deterministic.u64(row.timestamp_bits);
    deterministic.i64(row.destination_node);
    deterministic.i64(row.upstream_node);
    deterministic.i64(row.incoming_edge_start);
    deterministic.i64(row.incoming_edge_end);
    deterministic.i64(row.requesting_task_id);
    deterministic.i64(row.requesting_runtime_bag_id);
    deterministic.string(row.requesting_segment_id);
    deterministic.floating(row.earliest_arrival);
    deterministic.floating(row.slot_start);
    deterministic.floating(row.slot_end);
    deterministic.i64(row.known_competing_request_count);
    deterministic.i64(row.later_same_time_competitor_count);
    deterministic.boolean(
        row.later_same_time_competitor_exists);
    deterministic.boolean(row.seq_determined_order);
    deterministic.u64(row.event_seq);
  }
  deterministic.u64(result_.merge_service_opportunities.size());
  for (const auto& row : result_.merge_service_opportunities) {
    deterministic.u64(row.opportunity_id);
    deterministic.floating(row.event_time);
    deterministic.i64(row.destination_node);
    deterministic.u64(row.controller_generation);
    deterministic.string(row.timing_mode);
    deterministic.i64(row.candidate_count);
    deterministic.u64(row.baseline_winner_request_id);
    deterministic.u64(row.chosen_winner_request_id);
    deterministic.u64(row.candidate_request_id);
    deterministic.i64(row.upstream_node);
    deterministic.floating(row.projected_arrival);
    deterministic.floating(row.deadline_slack);
    deterministic.floating(row.wait_age);
    deterministic.floating(row.destination_service_seconds);
    deterministic.i64(row.downstream_queue_pressure);
    deterministic.floating(row.route_score);
    deterministic.floating(row.static_remaining);
    deterministic.i64(row.task_class_code);
    deterministic.i64(row.task_class);
    deterministic.boolean(row.storage_leg);
    deterministic.boolean(row.baseline_winner);
    deterministic.boolean(row.chosen_winner);
    if (!row.model_policy_mode.empty()) {
      deterministic.string(row.model_policy_mode);
      deterministic.string(row.model_feature_contract);
      deterministic.string(row.model_reason);
      deterministic.boolean(row.model_evaluated);
      deterministic.boolean(row.model_score_available);
      deterministic.floating(row.model_score);
      deterministic.boolean(row.model_proposed);
      deterministic.boolean(row.model_applied);
      deterministic.boolean(row.model_chosen);
      deterministic.boolean(row.model_out_of_distribution);
      deterministic.boolean(row.model_invalid);
      deterministic.boolean(row.model_fallback);
      deterministic.u64(row.model_baseline_request_id);
      deterministic.u64(row.model_proposed_request_id);
      for (const double feature : row.model_features) {
        deterministic.floating(feature);
      }
    }
  }
  deterministic.u64(result_.event_seq_ordering_audit.size());
  for (const auto& row : result_.event_seq_ordering_audit) {
    deterministic.floating(row.event_time);
    deterministic.u64(row.timestamp_bits);
    deterministic.string(row.boundary);
    deterministic.i64(row.node);
    deterministic.i64(row.destination_node);
    deterministic.i64(row.ready_set_size);
    deterministic.i64(row.priority_comparison_count);
    deterministic.i64(row.later_same_time_competitor_count);
    deterministic.i64(row.chosen_runtime_bag_id);
    deterministic.u64(row.chosen_enqueue_sequence);
    deterministic.u64(row.event_seq);
    deterministic.boolean(row.seq_determined_order);
    deterministic.string(row.reason);
  }
  deterministic.u64(
      result_.arbitration_batch_cardinality.size());
  for (const auto& row :
       result_.arbitration_batch_cardinality) {
    deterministic.floating(row.event_time);
    deterministic.u64(row.timestamp_bits);
    deterministic.string(row.boundary);
    deterministic.i64(row.node);
    deterministic.i64(row.enqueue_count);
    deterministic.i64(row.ready_set_size);
    deterministic.i64(row.pending_same_time_event_count);
    deterministic.i64(row.chosen_runtime_bag_id);
    deterministic.u64(row.event_seq);
    deterministic.u64(row.arbitration_generation);
  }
  deterministic.u64(result_.merge_grant_lifecycle.size());
  for (const auto& row : result_.merge_grant_lifecycle) {
    deterministic.floating(row.time);
    deterministic.u64(row.request_id);
    deterministic.u64(row.grant_id);
    deterministic.u64(row.lineage);
    deterministic.u64(row.request_generation);
    deterministic.u64(row.junction_queue_generation);
    deterministic.i64(row.runtime_bag_id);
    deterministic.i64(row.task_id);
    deterministic.string(
        row.segment_id == nullptr ? std::string_view{}
                                  : std::string_view(*row.segment_id));
    deterministic.i64(row.upstream_node);
    deterministic.i64(row.destination_node);
    deterministic.i64(row.edge.from_node);
    deterministic.i64(row.edge.to_node);
    deterministic.floating(row.request_time);
    deterministic.floating(row.fifo_request_time);
    deterministic.floating(row.earliest_edge_entry);
    deterministic.floating(row.exact_edge_travel_seconds);
    deterministic.floating(row.projected_arrival);
    deterministic.i64(row.goal);
    deterministic.floating(row.route_score);
    deterministic.floating(row.static_remaining);
    deterministic.floating(
        row.destination_service_seconds);
    deterministic.i64(row.downstream_queue_pressure);
    deterministic.floating(row.deadline_slack);
    deterministic.floating(row.wait_age);
    deterministic.i64(row.task_class_code);
    deterministic.i64(row.task_class);
    deterministic.boolean(row.storage_leg);
    deterministic.floating(row.source_release_age);
    deterministic.floating(row.local_queue_age);
    deterministic.u64(row.enqueue_sequence);
    deterministic.floating(row.request_expiry);
    deterministic.floating(row.slot_start);
    deterministic.floating(row.slot_end);
    deterministic.floating(row.issue_time);
    deterministic.floating(row.grant_expiry);
    deterministic.u64(row.calendar_generation);
    deterministic.i64(row.fault_generation);
    deterministic.i64(row.advertised_fault_generation);
    deterministic.u64(
        row.observed_claimed_request_generation);
    deterministic.u64(
        row.observed_claimed_junction_queue_generation);
    deterministic.u64(
        row.observed_claimed_calendar_generation);
    deterministic.i64(
        row.observed_claimed_owner_runtime_bag_id);
    deterministic.i64(row.observed_claimed_edge.from_node);
    deterministic.i64(row.observed_claimed_edge.to_node);
    deterministic.i64(
        row.observed_claimed_destination_node);
    deterministic.i64(
        row.observed_event_owner_runtime_bag_id);
    deterministic.i64(row.observed_event_edge.from_node);
    deterministic.i64(row.observed_event_edge.to_node);
    deterministic.i64(row.observed_event_destination_node);
    deterministic.u64(
        row.observed_junction_queue_generation);
    deterministic.u64(row.observed_calendar_generation);
    deterministic.i64(
        row.observed_physical_fault_generation);
    deterministic.i64(
        row.observed_advertised_fault_generation);
    deterministic.boolean(row.observed_physical_fault_active);
    deterministic.boolean(
        row.observed_exact_calendar_reservation_present);
    deterministic.i64(static_cast<int>(row.state));
    deterministic.i64(static_cast<int>(row.reason));
  }

  return G4IRSF14CloneReplayHashes{
      complete.sha256(),
      segments.sha256(),
      junctions.sha256(),
      algorithm.sha256(),
      deterministic.sha256()};
}

inline G4IRSF14CloneReplayHashes
EventDrivenJunctionRuntime::deterministic_replay_hashes() const {
  if (runtime_phase_ !=
      EventDrivenJunctionRuntimePhase::kFinalized) {
    throw std::logic_error(
        "deterministic replay hashes require a finalized horizon");
  }
  return compute_replay_hashes_projection();
}

inline G4IRSF14RuntimeStateDigests
EventDrivenJunctionRuntime::compute_runtime_state_digests() const {
  StateFingerprintWriter event_queue("event_queue");
  auto ordered_events = events_;
  event_queue.u64(ordered_events.size());
  while (!ordered_events.empty()) {
    fingerprint_event(event_queue, ordered_events.top());
    ordered_events.pop();
  }

  StateFingerprintWriter current_time("current_time");
  current_time.i64(static_cast<int>(runtime_phase_));
  current_time.floating(now_);
  current_time.floating(time_limit_);
  current_time.i64(active_bag_count_);
  current_time.floating(last_physical_repair_time_);
  current_time.i64(active_backlog_at_last_repair_);
  current_time.i64(active_backlog_at_runtime_stop_);

  std::vector<int> bag_ids;
  bag_ids.reserve(bags_.size());
  for (const auto& entry : bags_) {
    bag_ids.push_back(entry.first);
  }
  std::sort(bag_ids.begin(), bag_ids.end());
  StateFingerprintWriter bags("bags");
  bags.u64(bag_ids.size());
  for (const int id : bag_ids) {
    const auto& bag = bags_.at(id);
    bags.i64(id);
    fingerprint_request(bags, bag.request);
    bags.i64(static_cast<int>(bag.status));
    bags.boolean(bag.active_in_runtime);
    bags.i64(bag.current);
    bags.i64(bag.transit_from);
    bags.i64(bag.transit_to);
    const auto& expected = bag.transit_merge_grant;
    bags.boolean(expected.required);
    bags.u64(expected.grant_id);
    bags.u64(expected.request_id);
    bags.u64(expected.lineage);
    bags.u64(expected.request_generation);
    bags.u64(expected.junction_queue_generation);
    bags.i64(expected.owner_runtime_bag_id);
    bags.i64(expected.edge.from_node);
    bags.i64(expected.edge.to_node);
    bags.i64(expected.destination_node);
    bags.floating(expected.slot_start);
    bags.floating(expected.slot_end);
    bags.floating(expected.expiry);
    bags.u64(expected.calendar_generation);
    bags.i64(expected.physical_fault_generation);
    bags.i64(expected.advertised_fault_generation);
    bags.floating(bag.admitted_time);
    bags.floating(bag.finish_time);
    bags.floating(bag.source_enqueued_at);
    bags.floating(bag.junction_enqueued_at);
    bags.floating(bag.total_wait);
    bags.floating(bag.junction_queue_wait_seconds);
    bags.floating(bag.edge_travel_time_seconds);
    bags.floating(bag.node_service_time_seconds);
    bags.floating(bag.loop_extra_time_seconds);
    bags.floating(bag.goal_completion_time_seconds);
    bags.i64(bag.decision_count);
    bags.i64(bag.retry_count);
    bags.i64(bag.loop_count);
    bags.u64(bag.first_edge_credit_id);
    bags.boolean(bag.first_edge_credit_consumed);
    bags.floating(bag.deadlock_started_at);
    bags.string(bag.failure_reason);
    bags.u64(bag.history.size());
    for (const int node : bag.history) {
      bags.i64(node);
    }
    bags.u64(bag.local_enqueue_sequence);
    bags.u64(bag.fault_priority_generation);
    bags.boolean(bag.repaired_task_reentry);
  }

  std::vector<int> junction_ids;
  junction_ids.reserve(junctions_.size());
  for (const auto& entry : junctions_) {
    junction_ids.push_back(entry.first);
  }
  std::sort(junction_ids.begin(), junction_ids.end());
  StateFingerprintWriter source_queues("source_queues");
  StateFingerprintWriter junction_queues("junction_queues");
  StateFingerprintWriter local_calendars(
      "local_service_calendars");
  StateFingerprintWriter scheduled_incoming(
      "scheduled_incoming");
  source_queues.u64(junction_ids.size());
  junction_queues.u64(junction_ids.size());
  local_calendars.u64(junction_ids.size());
  scheduled_incoming.u64(junction_ids.size());
  for (const int node : junction_ids) {
    const auto& junction = junctions_.at(node);
    source_queues.i64(node);
    source_queues.u64(junction.source_queue.size());
    for (const int id : junction.source_queue) {
      source_queues.i64(id);
    }
    source_queues.u64(junction.source_wakeup_generation);
    source_queues.boolean(junction.source_wakeup_pending);

    junction_queues.i64(node);
    junction_queues.u64(junction.queue.size());
    for (const int id : junction.queue) {
      junction_queues.i64(id);
    }
    junction_queues.i64(junction.peak_source_queue_length);
    junction_queues.i64(junction.peak_junction_queue_length);
    junction_queues.i64(
        junction.peak_service_calendar_intervals);
    junction_queues.u64(junction.service_reservation_count);
    junction_queues.floating(
        junction.cumulative_service_reserved_seconds);
    junction_queues.floating(
        junction.first_service_reservation_start_time);
    junction_queues.floating(
        junction.last_service_reservation_end_time);
    junction_queues.floating(junction.next_dispatch_time);
    junction_queues.u64(junction.junction_wakeup_generation);
    junction_queues.boolean(junction.junction_wakeup_pending);
    junction_queues.i64(junction.escape_token_task);

    local_calendars.i64(node);
    local_calendars.u64(
        junction.service_calendar.generation());
    local_calendars.u64(junction.service_calendar.size());
    junction.service_calendar.inspect(
        [&](const auto& interval) {
          local_calendars.i64(interval.task_id);
          local_calendars.floating(interval.start);
          local_calendars.floating(interval.end);
        });

    scheduled_incoming.i64(node);
    scheduled_incoming.i64(junction.scheduled_incoming);
    std::vector<int> goals;
    goals.reserve(
        junction.scheduled_incoming_by_goal.size());
    for (const auto& item :
         junction.scheduled_incoming_by_goal) {
      goals.push_back(item.first);
    }
    std::sort(goals.begin(), goals.end());
    scheduled_incoming.u64(goals.size());
    for (const int goal : goals) {
      scheduled_incoming.i64(goal);
      scheduled_incoming.i64(
          junction.scheduled_incoming_by_goal.at(goal));
    }
  }

  std::vector<long long> corridor_ids;
  corridor_ids.reserve(corridors_.size());
  for (const auto& entry : corridors_) {
    corridor_ids.push_back(entry.first);
  }
  std::sort(corridor_ids.begin(), corridor_ids.end());
  StateFingerprintWriter corridors("corridor_state");
  corridors.u64(corridor_ids.size());
  for (const auto edge : corridor_ids) {
    const auto& calendar = corridors_.at(edge);
    corridors.i64(edge);
    corridors.u64(calendar.generation());
    corridors.u64(calendar.size());
    calendar.inspect([&](const auto& interval) {
      corridors.i64(interval.task_id);
      corridors.floating(interval.start);
      corridors.floating(interval.end);
    });
  }
  std::vector<long long> inflight_edges;
  inflight_edges.reserve(directed_inflight_counts_.size());
  for (const auto& entry : directed_inflight_counts_) {
    inflight_edges.push_back(entry.first);
  }
  std::sort(inflight_edges.begin(), inflight_edges.end());
  scheduled_incoming.u64(inflight_edges.size());
  for (const auto edge : inflight_edges) {
    scheduled_incoming.i64(edge);
    scheduled_incoming.i64(
        directed_inflight_counts_.at(edge));
  }

  StateFingerprintWriter credits("credits");
  // This exact ledger checkpoint binds next_credit_id, active credits,
  // every derived lookup/expiry index (including equal-expiry order),
  // counters, lifecycle bound, and lifecycle rows.
  credits.string(credit_ledger_.exact_state_sha256());
  const auto& credit_counters = credit_ledger_.counters();
  credits.u64(credit_counters.issue_attempt_count);
  credits.u64(credit_counters.issued_count);
  credits.u64(credit_counters.validation_attempt_count);
  credits.u64(credit_counters.validation_success_count);
  credits.u64(credit_counters.bind_attempt_count);
  credits.u64(credit_counters.bound_count);
  credits.u64(credit_counters.consume_attempt_count);
  credits.u64(credit_counters.consumed_count);
  credits.u64(credit_counters.expired_count);
  credits.u64(credit_counters.fault_revocation_count);
  credits.u64(credit_counters.generation_revocation_count);
  credits.u64(credit_counters.invalid_revocation_count);
  credits.u64(credit_counters.duplicate_rejection_count);
  credits.u64(credit_counters.capacity_rejection_count);
  credits.u64(credit_counters.stale_snapshot_rejection_count);
  credits.u64(credit_counters.physical_fault_rejection_count);
  credits.u64(credit_counters.too_early_rejection_count);
  credits.u64(credit_counters.unknown_credit_rejection_count);
  credits.u64(credit_counters.invalid_request_rejection_count);
  credits.u64(credit_counters.lifecycle_dropped_count);
  credits.i64(credit_counters.active_count);
  credits.i64(credit_counters.peak_active_count);
  const auto fingerprint_credit =
      [&](const FirstEdgeCredit& credit) {
        credits.u64(credit.credit_id);
        credits.i64(credit.from_node);
        credits.i64(credit.to_node);
        credits.i64(credit.goal);
        credits.floating(credit.earliest);
        credits.floating(credit.latest);
        credits.u64(credit.generation);
        credits.floating(credit.expiry);
        credits.i64(credit.capacity);
        credits.i64(credit.owner_or_unbound);
        credits.i64(credit.fault_generation);
        credits.i64(static_cast<int>(credit.state));
        credits.string(credit.terminal_reason);
      };
  credits.u64(credit_ledger_.stored_active_count());
  for (std::uint64_t id = 1;
       id <= credit_counters.issued_count; ++id) {
    const auto* credit = credit_ledger_.find(id);
    if (credit != nullptr) {
      fingerprint_credit(*credit);
    }
  }
  credits.u64(credit_ledger_.lifecycle_limit());
  credits.u64(credit_ledger_.lifecycle().size());
  for (const auto& row : credit_ledger_.lifecycle()) {
    credits.floating(row.time);
    credits.string(row.action);
    credits.string(row.reason);
    fingerprint_credit(row.credit);
  }

  StateFingerprintWriter merge_grants("merge_grants");
  std::vector<int> merge_nodes;
  merge_nodes.reserve(destination_merge_controllers_.size());
  for (const auto& entry : destination_merge_controllers_) {
    merge_nodes.push_back(entry.first);
  }
  std::sort(merge_nodes.begin(), merge_nodes.end());
  merge_grants.u64(merge_nodes.size());
  for (const int node : merge_nodes) {
    const auto checkpoint =
        DestinationMergeGrantCheckpointCodec::capture(
            destination_merge_controllers_.at(node));
    merge_grants.i64(node);
    merge_grants.i64(checkpoint.destination_node);
    merge_grants.u64(checkpoint.max_pending_requests);
    merge_grants.u64(checkpoint.lifecycle_limit);
    merge_grants.u64(checkpoint.next_request_id);
    merge_grants.u64(checkpoint.next_grant_id);
    merge_grants.u64(checkpoint.generation);
    merge_grants.u64(checkpoint.pending.size());
    for (const auto& request : checkpoint.pending) {
      fingerprint_merge_request(merge_grants, request);
    }
    merge_grants.u64(checkpoint.active.size());
    for (const auto& active : checkpoint.active) {
      merge_grants.u64(active.grant_id);
      merge_grants.u64(active.request_id);
      merge_grants.u64(active.lineage);
      merge_grants.u64(active.request_generation);
      merge_grants.u64(active.junction_queue_generation);
      merge_grants.i64(active.owner_runtime_bag_id);
      merge_grants.i64(active.edge.from_node);
      merge_grants.i64(active.edge.to_node);
      merge_grants.floating(active.slot_start);
      merge_grants.floating(active.slot_end);
      merge_grants.floating(active.issue_time);
      merge_grants.floating(active.grant_expiry);
      merge_grants.u64(active.calendar_generation);
      merge_grants.i64(active.physical_fault_generation);
      merge_grants.i64(
          active.advertised_fault_generation);
      fingerprint_merge_request(
          merge_grants, active.request_snapshot);
    }
    const auto& counters = checkpoint.counters;
    merge_grants.u64(counters.request_count);
    merge_grants.u64(counters.issued_count);
    merge_grants.u64(counters.prepared_count);
    merge_grants.u64(counters.committed_count);
    merge_grants.u64(counters.issued_transition_count);
    merge_grants.u64(counters.prepared_transition_count);
    merge_grants.u64(counters.committed_transition_count);
    merge_grants.u64(counters.consumed_count);
    merge_grants.u64(
        counters.inflight_fault_generation_recovery_count);
    merge_grants.u64(counters.expired_count);
    merge_grants.u64(counters.request_expired_count);
    merge_grants.u64(counters.grant_expired_count);
    merge_grants.u64(counters.revoked_count);
    merge_grants.u64(counters.revoked_fault_count);
    merge_grants.u64(counters.revoked_stale_state_count);
    merge_grants.u64(
        counters.revoked_replan_current_edge_count);
    merge_grants.u64(counters.rolled_back_count);
    merge_grants.u64(counters.post_commit_revoked_count);
    merge_grants.u64(counters.post_commit_expired_count);
    merge_grants.u64(counters.post_commit_rollback_count);
    merge_grants.u64(counters.exact_slot_busy_count);
    merge_grants.u64(counters.active_grant_rejection_count);
    merge_grants.u64(counters.queue_capacity_block_count);
    merge_grants.u64(counters.contended_loser_retry_count);
    merge_grants.u64(counters.lifecycle_transition_count);
    merge_grants.u64(counters.lifecycle_stored_count);
    merge_grants.u64(counters.lifecycle_dropped_count);
    merge_grants.u64(counters.peak_pending_count);
    merge_grants.u64(counters.peak_active_unconsumed_count);
    merge_grants.u64(checkpoint.lifecycle.size());
    for (const auto& row : checkpoint.lifecycle) {
      merge_grants.floating(row.time);
      merge_grants.u64(row.request_id);
      merge_grants.u64(row.grant_id);
      merge_grants.u64(row.lineage);
      merge_grants.u64(row.request_generation);
      merge_grants.u64(row.junction_queue_generation);
      merge_grants.i64(row.runtime_bag_id);
      merge_grants.i64(row.task_id);
      merge_grants.string(
          row.segment_id == nullptr
              ? std::string_view{}
              : std::string_view(*row.segment_id));
      merge_grants.i64(row.upstream_node);
      merge_grants.i64(row.destination_node);
      merge_grants.i64(row.edge.from_node);
      merge_grants.i64(row.edge.to_node);
      merge_grants.floating(row.request_time);
      merge_grants.floating(row.fifo_request_time);
      merge_grants.floating(row.earliest_edge_entry);
      merge_grants.floating(row.exact_edge_travel_seconds);
      merge_grants.floating(row.projected_arrival);
      merge_grants.i64(row.goal);
      merge_grants.floating(row.route_score);
      merge_grants.floating(row.static_remaining);
      merge_grants.floating(
          row.destination_service_seconds);
      merge_grants.i64(row.downstream_queue_pressure);
      merge_grants.floating(row.deadline_slack);
      merge_grants.floating(row.wait_age);
      merge_grants.i64(row.task_class_code);
      merge_grants.i64(row.task_class);
      merge_grants.boolean(row.storage_leg);
      merge_grants.floating(row.source_release_age);
      merge_grants.floating(row.local_queue_age);
      merge_grants.u64(row.enqueue_sequence);
      merge_grants.floating(row.request_expiry);
      merge_grants.floating(row.slot_start);
      merge_grants.floating(row.slot_end);
      merge_grants.floating(row.issue_time);
      merge_grants.floating(row.grant_expiry);
      merge_grants.u64(row.calendar_generation);
      merge_grants.i64(row.fault_generation);
      merge_grants.i64(row.advertised_fault_generation);
      merge_grants.u64(
          row.observed_claimed_request_generation);
      merge_grants.u64(
          row.observed_claimed_junction_queue_generation);
      merge_grants.u64(
          row.observed_claimed_calendar_generation);
      merge_grants.i64(
          row.observed_claimed_owner_runtime_bag_id);
      merge_grants.i64(
          row.observed_claimed_edge.from_node);
      merge_grants.i64(
          row.observed_claimed_edge.to_node);
      merge_grants.i64(
          row.observed_claimed_destination_node);
      merge_grants.i64(
          row.observed_event_owner_runtime_bag_id);
      merge_grants.i64(row.observed_event_edge.from_node);
      merge_grants.i64(row.observed_event_edge.to_node);
      merge_grants.i64(
          row.observed_event_destination_node);
      merge_grants.u64(
          row.observed_junction_queue_generation);
      merge_grants.u64(row.observed_calendar_generation);
      merge_grants.i64(
          row.observed_physical_fault_generation);
      merge_grants.i64(
          row.observed_advertised_fault_generation);
      merge_grants.boolean(
          row.observed_physical_fault_active);
      merge_grants.boolean(
          row.observed_exact_calendar_reservation_present);
      merge_grants.i64(static_cast<int>(row.state));
      merge_grants.i64(static_cast<int>(row.reason));
    }
  }
  std::vector<std::uint64_t> dispatch_ids;
  dispatch_ids.reserve(pending_merge_dispatches_.size());
  for (const auto& entry : pending_merge_dispatches_) {
    dispatch_ids.push_back(entry.first);
  }
  std::sort(dispatch_ids.begin(), dispatch_ids.end());
  merge_grants.u64(dispatch_ids.size());
  for (const auto id : dispatch_ids) {
    const auto& dispatch = pending_merge_dispatches_.at(id);
    merge_grants.u64(id);
    merge_grants.u64(dispatch.request_id);
    merge_grants.u64(dispatch.lineage);
    merge_grants.i64(dispatch.runtime_bag_id);
    merge_grants.i64(dispatch.upstream_node);
    merge_grants.i64(dispatch.destination_node);
    const auto& trace = dispatch.trace;
    merge_grants.u64(trace.decision_id);
    merge_grants.u64(trace.arrive_event_seq);
    merge_grants.floating(trace.event_time);
    merge_grants.i64(trace.task_id);
    merge_grants.i64(trace.runtime_bag_id);
    merge_grants.string(trace.segment_id);
    merge_grants.i64(trace.current_node);
    merge_grants.i64(trace.goal_node);
    merge_grants.i64(trace.model_prediction);
    merge_grants.floating(trace.model_margin);
    merge_grants.boolean(trace.risk_gate_triggered);
    merge_grants.boolean(trace.scorer_risk_abstain);
    merge_grants.u64(trace.scorer_risk_reasons.size());
    for (const auto& reason : trace.scorer_risk_reasons) {
      merge_grants.string(reason);
    }
    merge_grants.string(trace.scorer_id);
    merge_grants.string(trace.scorer_effective_id);
    merge_grants.i64(trace.scorer_raw_prediction);
    merge_grants.floating(trace.scorer_raw_margin);
    merge_grants.i64(trace.fallback_selected_next);
    merge_grants.i64(trace.selected_next);
    merge_grants.string(trace.decision_source);
    merge_grants.string(trace.rule_reason);
    merge_grants.i64(trace.junction_queue_length);
    merge_grants.floating(
        trace.junction_next_dispatch_time);
    merge_grants.i64(
        trace.advertised_faulted_outgoing_count);
    merge_grants.floating(
        trace.max_fault_message_age_seconds);
    merge_grants.u64(trace.short_history.size());
    for (const int node : trace.short_history) {
      merge_grants.i64(node);
    }
    merge_grants.boolean(trace.full_astar_used);
    merge_grants.string(trace.priority_mode);
    merge_grants.string(trace.task_class);
    merge_grants.floating(trace.priority_slack_seconds);
    merge_grants.floating(trace.priority_age_seconds);
    merge_grants.i64(trace.priority_local_contention);
    merge_grants.u64(trace.priority_fault_generation);
    merge_grants.u64(trace.priority_enqueue_sequence);
    merge_grants.string(trace.pibt_preference_mode);
    merge_grants.u64(trace.candidates.size());
    for (const auto& candidate : trace.candidates) {
      merge_grants.i64(candidate.next_node);
      merge_grants.floating(candidate.static_potential);
      merge_grants.floating(candidate.travel_time);
      merge_grants.i64(candidate.target_queue_length);
      merge_grants.i64(
          candidate.target_scheduled_incoming);
      merge_grants.floating(
          candidate.corridor_next_available);
      merge_grants.floating(
          candidate.target_next_available);
      merge_grants.boolean(candidate.advertised_fault);
      merge_grants.floating(
          candidate.fault_message_age_seconds);
      merge_grants.i64(candidate.recent_visit_count);
      merge_grants.i64(candidate.two_hop_queue_pressure);
      merge_grants.i64(
          candidate.current_goal_queue_length);
      merge_grants.i64(
          candidate.target_goal_queue_length);
      merge_grants.i64(
          candidate.target_goal_scheduled_incoming);
      merge_grants.floating(
          candidate.current_goal_max_wait);
      merge_grants.floating(
          candidate.goal_conditioned_differential);
      merge_grants.floating(
          candidate.estimated_service_rate);
      merge_grants.floating(
          candidate.service_weighted_pressure);
      merge_grants.boolean(
          candidate.first_edge_credit_required);
      merge_grants.boolean(
          candidate.first_edge_credit_matches);
      merge_grants.boolean(
          candidate.first_edge_credit_valid);
      merge_grants.floating(
          candidate.first_edge_credit_slack_seconds);
      merge_grants.floating(candidate.model_score);
      merge_grants.floating(
          candidate.pre_fault_policy_score);
      merge_grants.floating(candidate.scorer_raw_score);
      merge_grants.floating(
          candidate.scorer_raw_bottleneck);
      merge_grants.boolean(
          candidate.scorer_raw_score_available);
      merge_grants.boolean(candidate.shield_allowed);
      merge_grants.string(candidate.shield_reason);
    }
  }

  StateFingerprintWriter faults("fault_state");
  std::vector<long long> fault_edges;
  fault_edges.reserve(physical_faults_.size());
  for (const auto& entry : physical_faults_) {
    fault_edges.push_back(entry.first);
  }
  std::sort(fault_edges.begin(), fault_edges.end());
  faults.u64(fault_edges.size());
  for (const auto edge : fault_edges) {
    const auto& state = physical_faults_.at(edge);
    faults.i64(edge);
    faults.i64(state.active_count);
    faults.i64(state.physical_generation);
  }
  fault_edges.clear();
  for (const auto& entry : advertised_faults_) {
    fault_edges.push_back(entry.first);
  }
  std::sort(fault_edges.begin(), fault_edges.end());
  faults.u64(fault_edges.size());
  for (const auto edge : fault_edges) {
    const auto& state = advertised_faults_.at(edge);
    faults.i64(edge);
    faults.boolean(state.faulted);
    faults.i64(state.generation);
    faults.floating(state.received_at);
  }
  std::vector<int> affected(
      fault_affected_bags_.begin(), fault_affected_bags_.end());
  std::sort(affected.begin(), affected.end());
  faults.u64(affected.size());
  for (const int id : affected) {
    faults.i64(id);
  }
  fault_edges.clear();
  for (const auto& entry : fault_affected_bags_by_edge_) {
    fault_edges.push_back(entry.first);
  }
  std::sort(fault_edges.begin(), fault_edges.end());
  faults.u64(fault_edges.size());
  for (const auto edge : fault_edges) {
    faults.i64(edge);
    const auto& ids = fault_affected_bags_by_edge_.at(edge);
    faults.u64(ids.size());
    for (const int id : ids) {
      faults.i64(id);
    }
  }
  std::vector<int> fault_bag_ids;
  for (const auto& entry : fault_instances_by_bag_) {
    fault_bag_ids.push_back(entry.first);
  }
  std::sort(fault_bag_ids.begin(), fault_bag_ids.end());
  faults.u64(fault_bag_ids.size());
  for (const int id : fault_bag_ids) {
    faults.i64(id);
    const auto& instances = fault_instances_by_bag_.at(id);
    faults.u64(instances.size());
    for (const auto& instance : instances) {
      faults.i64(instance.first);
      faults.i64(instance.second);
    }
  }
  fault_edges.clear();
  for (const auto& entry : active_fault_instance_by_edge_) {
    fault_edges.push_back(entry.first);
  }
  std::sort(fault_edges.begin(), fault_edges.end());
  faults.u64(fault_edges.size());
  for (const auto edge : fault_edges) {
    faults.i64(edge);
    faults.i64(active_fault_instance_by_edge_.at(edge));
  }
  faults.u64(repair_time_by_fault_instance_.size());
  for (const auto& entry : repair_time_by_fault_instance_) {
    faults.i64(entry.first.first);
    faults.i64(entry.first.second);
    faults.floating(entry.second);
  }

  StateFingerprintWriter pibt("pibt_owner_state");
  pibt.boolean(g4irsf14_state_ != nullptr);
  if (g4irsf14_state_ != nullptr) {
    pibt.i64(g4irsf14_state_->current_pibt_slice_bag_count);
    pibt.i64(g4irsf14_state_->current_pibt_owner_count);
    std::vector<int> merge_bag_ids;
    for (const auto& entry :
         g4irsf14_state_->destination_merge_bags) {
      merge_bag_ids.push_back(entry.first);
    }
    std::sort(merge_bag_ids.begin(), merge_bag_ids.end());
    pibt.u64(merge_bag_ids.size());
    for (const int id : merge_bag_ids) {
      const auto& item =
          g4irsf14_state_->destination_merge_bags.at(id);
      pibt.i64(id);
      pibt.u64(item.junction_queue_generation);
      pibt.u64(item.request_generation);
      pibt.u64(item.pending_request_id);
      pibt.u64(item.pending_lineage);
      pibt.floating(item.pending_request_time);
      pibt.floating(item.first_contention_time);
      pibt.floating(item.grant_wait_seconds);
      if (g4irsf18_merge_policy_enabled()) {
        pibt.i64(item.g4irsf18_merge_override_count);
      }
      pibt.boolean(item.exact_grant_edge_entry_observed);
      pibt.boolean(item.capability.has_value());
      if (item.capability.has_value()) {
        fingerprint_capability(
            pibt,
            DestinationMergeGrantCheckpointCodec::capture(
                *item.capability));
      }
    }
  }

  StateFingerprintWriter counters("deterministic_counters");
  counters.u64(next_event_seq_);
  counters.u64(next_decision_id_);
  counters.u64(next_pibt_activation_id_);
  counters.u64(next_local_enqueue_sequence_);
  counters.u64(next_merge_request_lineage_);
  counters.i64(active_bag_count_);
  counters.u64(segment_runtime_ids_.size());
  std::vector<std::string> segments;
  segments.reserve(segment_runtime_ids_.size());
  for (const auto& entry : segment_runtime_ids_) {
    segments.push_back(entry.first);
  }
  std::sort(segments.begin(), segments.end());
  for (const auto& segment : segments) {
    counters.string(segment);
    counters.i64(segment_runtime_ids_.at(segment));
  }
  counters.u64(waits_.size());
  for (const double wait : waits_) {
    counters.floating(wait);
  }
#ifdef CZR005_EVENT_RUNTIME_TESTING
  counters.boolean(test_pibt_logical_failure_injected_);
  counters.boolean(test_merge_grant_prepare_failure_injected_);
  counters.boolean(test_merge_grant_advertised_flip_injected_);
  counters.boolean(test_merge_grant_physical_flip_injected_);
  counters.boolean(test_merge_grant_calendar_flip_injected_);
  counters.boolean(test_merge_grant_queue_flip_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_capability_drop_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_physical_flip_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_advertised_flip_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_calendar_remove_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_expiry_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_wrong_owner_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_wrong_edge_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_wrong_destination_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_claimed_request_generation_tamper_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_claimed_queue_generation_tamper_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_claimed_calendar_generation_tamper_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_live_queue_generation_advance_injected_);
  counters.boolean(
      test_merge_grant_edge_exit_live_calendar_generation_advance_injected_);
  counters.boolean(test_pibt_post_commit_failure_injected_);
#endif

  StateFingerprintWriter scorer("scorer_state");
  scorer.string(config_.queue_discipline);
  scorer.string(config_.resource_semantics);
  scorer.floating(config_.entry_headway_seconds);
  scorer.string(config_.pressure_mode);
  scorer.floating(config_.retry_interval);
  scorer.floating(config_.minimum_service_seconds);
  scorer.floating(config_.dispatch_headway_seconds);
  scorer.floating(config_.pressure_weight);
  scorer.floating(config_.pressure_age_weight);
  scorer.floating(config_.pressure_distance_bias);
  scorer.floating(config_.calendar_wait_weight);
  scorer.floating(config_.history_penalty);
  scorer.floating(config_.backtrack_penalty);
  scorer.floating(config_.aging_weight);
  scorer.floating(config_.starvation_threshold);
  scorer.i64(config_.history_limit);
  scorer.i64(config_.max_decisions_per_bag);
  scorer.i64(config_.max_events);
  scorer.floating(config_.max_simulation_time);
  scorer.i64(config_.trace_limit);
  scorer.boolean(config_.event_trace_limit.has_value());
  scorer.i64(config_.event_trace_limit.value_or(0));
  scorer.i64(config_.trace_shard_count);
  scorer.i64(config_.trace_shard_index);
  scorer.i64(config_.local_queue_capacity);
  scorer.i64(config_.deadlock_retry_threshold);
  scorer.i64(config_.diagnostic_hops);
  scorer.string(config_.admission_mode);
  scorer.floating(config_.credit_validity_seconds);
  scorer.floating(config_.credit_snapshot_max_age_seconds);
  scorer.i64(config_.credit_capacity_per_edge);
  scorer.i64(config_.credit_lifecycle_limit);
  scorer.i64(config_.selective_credit_contention_threshold);
  scorer.boolean(config_.enable_source_admission);
  scorer.boolean(config_.enable_backpressure);
  scorer.string(config_.pibt_mode);
  scorer.i64(config_.pibt_max_ready_bags);
  scorer.i64(config_.pibt_max_local_resources);
  scorer.i64(config_.pibt_max_candidates_per_bag);
  scorer.string(config_.priority_mode);
  scorer.string(config_.pibt_preference_mode);
  scorer.string(config_.scorer_mode);
  scorer.floating(config_.scorer_b2);
  scorer.floating(config_.scorer_risk_margin_threshold);
  scorer.floating(config_.scorer_risk_bottleneck_threshold);
  scorer.string(config_.scorer_model_sha256);
  scorer.string(config_.framework_mode);
  scorer.boolean(config_.enable_pibt_lite);
  scorer.boolean(config_.enable_deadlock_escape);
  scorer.boolean(config_.enable_fault_policy);
  scorer.string(config_.event_semantics);
  scorer.boolean(config_.enable_opportunity_telemetry);
  scorer.i64(config_.opportunity_trace_limit);
  scorer.string(config_.merge_grant_rule);
  scorer.string(config_.merge_grant_timing_mode);
  scorer.i64(config_.merge_grant_max_pending_requests);
  scorer.i64(config_.merge_grant_lifecycle_limit);
  if (config_.g4irsf18_merge_policy.enabled()) {
    const auto& policy = config_.g4irsf18_merge_policy;
    scorer.string(policy.mode);
    scorer.string(policy.schema);
    scorer.string(policy.family);
    scorer.string(policy.feature_contract);
    scorer.string(policy.score_direction);
    scorer.string(policy.tie_break);
    scorer.string(policy.tie_break_scope);
    scorer.string(policy.ood_fallback);
    scorer.string(policy.authorization);
    scorer.u64(policy.feature_names.size());
    for (const auto& name : policy.feature_names) {
      scorer.string(name);
    }
    const auto write_values = [&](const std::vector<double>& values) {
      scorer.u64(values.size());
      for (const double value : values) {
        scorer.floating(value);
      }
    };
    write_values(policy.mean);
    write_values(policy.scale);
    write_values(policy.weights);
    write_values(policy.feature_lower);
    write_values(policy.feature_upper);
    scorer.floating(policy.bias);
    scorer.floating(policy.starvation_threshold_seconds);
    scorer.boolean(policy.identity_features_used);
    scorer.boolean(policy.outcome_features_used);
    scorer.boolean(
        policy.artifact_production_closed_loop_authorized);
    scorer.boolean(policy.research_closed_loop_authorized);
    scorer.boolean(policy.fixed_research_workload);
    scorer.boolean(policy.production_closed_loop_authorized);
    scorer.boolean(policy.offline_gate_passed);
    scorer.floating(policy.coverage_cap);
    scorer.i64(policy.max_overrides_per_segment);
    scorer.boolean(policy.kill_switch);
  }
#ifdef CZR005_EVENT_RUNTIME_TESTING
  // Test-build fault switches alter deterministic continuation and therefore
  // belong to the checkpoint seal even though production builds omit them.
  scorer.i64(
      config_.test_pibt_logical_failure_after_staged_actions);
  scorer.boolean(
      config_.test_pibt_logical_failure_after_followup_scheduling);
  scorer.boolean(
      config_.test_merge_grant_fail_after_calendar_prepare);
  scorer.boolean(
      config_.test_merge_grant_flip_advertised_generation_before_commit);
  scorer.boolean(
      config_.test_merge_grant_flip_physical_generation_before_commit);
  scorer.boolean(
      config_.test_merge_grant_flip_calendar_generation_before_commit);
  scorer.boolean(
      config_.test_merge_grant_flip_queue_generation_before_commit);
  scorer.boolean(
      config_.test_merge_grant_drop_capability_before_edge_exit);
  scorer.boolean(
      config_.test_merge_grant_flip_physical_generation_before_edge_exit);
  scorer.boolean(
      config_.test_merge_grant_flip_advertised_generation_before_edge_exit);
  scorer.boolean(
      config_.test_merge_grant_remove_calendar_before_edge_exit);
  scorer.boolean(
      config_.test_merge_grant_expire_before_edge_exit);
  scorer.boolean(
      config_.test_merge_grant_wrong_owner_before_edge_exit);
  scorer.boolean(
      config_.test_merge_grant_wrong_edge_before_edge_exit);
  scorer.boolean(
      config_.test_merge_grant_wrong_destination_before_edge_exit);
  scorer.boolean(
      config_.test_merge_grant_tamper_claimed_request_generation_before_edge_exit);
  scorer.boolean(
      config_.test_merge_grant_tamper_claimed_queue_generation_before_edge_exit);
  scorer.boolean(
      config_.test_merge_grant_tamper_claimed_calendar_generation_before_edge_exit);
  scorer.boolean(
      config_.test_merge_grant_advance_live_queue_generation_before_edge_exit);
  scorer.boolean(
      config_.test_merge_grant_advance_live_calendar_generation_before_edge_exit);
  scorer.boolean(
      config_.test_pibt_fail_after_commit_before_publication);
#endif
  scorer.u64(config_.scorer_w1.size());
  for (const auto& row : config_.scorer_w1) {
    scorer.u64(row.size());
    for (const double value : row) {
      scorer.floating(value);
    }
  }
  scorer.u64(config_.scorer_b1.size());
  for (const double value : config_.scorer_b1) {
    scorer.floating(value);
  }
  scorer.u64(config_.scorer_w2.size());
  for (const double value : config_.scorer_w2) {
    scorer.floating(value);
  }
  scorer.u64(pibt_regret_prior_.size());
  for (const auto& entry : pibt_regret_prior_) {
    scorer.i64(std::get<0>(entry.first));
    scorer.i64(std::get<1>(entry.first));
    scorer.i64(std::get<2>(entry.first));
    scorer.floating(entry.second);
  }
  scorer.u64(scorer_static_hops_.size());
  for (const auto& entry : scorer_static_hops_) {
    scorer.i64(entry.first.first);
    scorer.i64(entry.first.second);
    scorer.i64(entry.second);
  }
  scorer.boolean(scorer_model_.has_value());

  const auto replay = compute_replay_hashes_projection();
  StateFingerprintWriter result_accumulator(
      "result_accumulator");
  result_accumulator.string(replay.complete_bags_sha256);
  result_accumulator.string(replay.segment_result_sha256);
  result_accumulator.string(replay.junction_state_sha256);
  result_accumulator.string(replay.algorithm_summary_sha256);
  result_accumulator.string(replay.deterministic_result_sha256);

  StateFingerprintWriter runtime_hashes(
      "current_runtime_hashes");
  runtime_hashes.string(kG4IRSF14StateCloneSchema);
  runtime_hashes.string(scorer_graph_fingerprint());
  runtime_hashes.string(canonical_event_semantics());
  runtime_hashes.string(canonical_resource_semantics());
  runtime_hashes.string(canonical_admission_mode());
  runtime_hashes.string(canonical_pibt_mode_name());
  runtime_hashes.string(canonical_priority_mode_name());
  runtime_hashes.string(canonical_scorer_mode());
  runtime_hashes.string(canonical_framework_mode());

  std::vector<int> beacon_nodes;
  beacon_nodes.reserve(congestion_beacons_.size());
  for (const auto& entry : congestion_beacons_) {
    beacon_nodes.push_back(entry.first);
  }
  std::sort(beacon_nodes.begin(), beacon_nodes.end());
  StateFingerprintWriter beacons("congestion_beacons");
  beacons.u64(beacon_nodes.size());
  for (const int node : beacon_nodes) {
    const auto& beacon = congestion_beacons_.at(node);
    beacons.i64(node);
    beacons.i64(beacon.queue_length);
    beacons.i64(beacon.scheduled_incoming);
    beacons.floating(beacon.service_calendar_reserved_until);
    beacons.floating(beacon.received_at);
    beacons.u64(beacon.generation);
    std::vector<int> goals;
    for (const auto& entry : beacon.queue_length_by_goal) {
      goals.push_back(entry.first);
    }
    for (const auto& entry :
         beacon.scheduled_incoming_by_goal) {
      goals.push_back(entry.first);
    }
    std::sort(goals.begin(), goals.end());
    goals.erase(std::unique(goals.begin(), goals.end()),
                goals.end());
    beacons.u64(goals.size());
    for (const int goal : goals) {
      beacons.i64(goal);
      const auto queue =
          beacon.queue_length_by_goal.find(goal);
      const auto incoming =
          beacon.scheduled_incoming_by_goal.find(goal);
      beacons.i64(
          queue == beacon.queue_length_by_goal.end()
              ? 0
              : queue->second);
      beacons.i64(
          incoming ==
                  beacon.scheduled_incoming_by_goal.end()
              ? 0
              : incoming->second);
    }
  }

  StateFingerprintWriter microphase("microphase_state");
  microphase.boolean(g4irsf14_state_ != nullptr);
  if (g4irsf14_state_ != nullptr) {
    microphase.u64(g4irsf14_state_->current_event_seq);
    microphase.boolean(
        g4irsf14_state_->microphase_floor_active);
    microphase.floating(
        g4irsf14_state_->microphase_floor_time);
    microphase.i64(
        g4irsf14_state_->microphase_floor_priority);
    std::vector<int> nodes;
    for (const auto& entry : g4irsf14_state_->local) {
      nodes.push_back(entry.first);
    }
    std::sort(nodes.begin(), nodes.end());
    microphase.u64(nodes.size());
    for (const int node : nodes) {
      const auto& local = g4irsf14_state_->local.at(node);
      microphase.i64(node);
      microphase.floating(local.source_wakeup_time);
      microphase.floating(local.junction_wakeup_time);
      microphase.boolean(local.has_last_source_arbitration);
      microphase.boolean(
          local.has_last_junction_arbitration);
      microphase.floating(local.last_source_arbitration_time);
      microphase.floating(
          local.last_junction_arbitration_time);
      microphase.u64(
          local.last_source_arbitration_generation);
      microphase.u64(
          local.last_junction_arbitration_generation);
      microphase.boolean(local.source_batch_open);
      microphase.boolean(local.junction_batch_open);
      microphase.floating(local.source_batch_time);
      microphase.floating(local.junction_batch_time);
      microphase.i64(local.source_queue_before_enqueue);
      microphase.i64(local.source_queue_after_enqueue);
      microphase.i64(local.junction_queue_before_enqueue);
      microphase.i64(local.junction_queue_after_enqueue);
      microphase.i64(local.source_enqueue_count);
      microphase.i64(local.junction_enqueue_count);
    }
    nodes.clear();
    for (const auto& entry :
         g4irsf14_state_->destination_merge) {
      nodes.push_back(entry.first);
    }
    std::sort(nodes.begin(), nodes.end());
    microphase.u64(nodes.size());
    for (const int node : nodes) {
      const auto& state =
          g4irsf14_state_->destination_merge.at(node);
      microphase.i64(node);
      microphase.floating(state.wakeup_time);
      microphase.u64(state.wakeup_generation);
      microphase.boolean(state.wakeup_pending);
    }
  }

  return G4IRSF14RuntimeStateDigests{
      event_queue.sha256(),
      current_time.sha256(),
      bags.sha256(),
      source_queues.sha256(),
      junction_queues.sha256(),
      local_calendars.sha256(),
      corridors.sha256(),
      scheduled_incoming.sha256(),
      credits.sha256(),
      merge_grants.sha256(),
      faults.sha256(),
      pibt.sha256(),
      counters.sha256(),
      scorer.sha256(),
      result_accumulator.sha256(),
      runtime_hashes.sha256(),
      beacons.sha256(),
      microphase.sha256()};
}

inline G4IRSF14RuntimeStateDigests
EventDrivenJunctionRuntime::deterministic_state_digests() const {
  if (runtime_phase_ != EventDrivenJunctionRuntimePhase::kReady ||
      events_.empty()) {
    throw std::logic_error(
        "deterministic state digests require a live pre-pop boundary");
  }
  require_checkpoint_safe_boundary();
  auto digests = compute_runtime_state_digests();
  digests.validate();
  return digests;
}

inline std::string
EventDrivenJunctionRuntime::deterministic_state_sha256() const {
  return deterministic_state_digests().aggregate_sha256();
}

}  // namespace czr005::ics
