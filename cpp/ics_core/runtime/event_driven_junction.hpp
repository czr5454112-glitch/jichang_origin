#pragma once

#include <algorithm>
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
#include "ics_core/runtime/expiring_first_edge_credit.hpp"

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
};

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
#ifdef CZR005_EVENT_RUNTIME_TESTING
  // Native-only fault injection used to verify transaction rollback after
  // multiple action rows have been staged. It is absent from production
  // builds and bindings.
  int test_pibt_logical_failure_after_staged_actions = -1;
  bool test_pibt_logical_failure_after_followup_scheduling = false;
  bool test_verify_pibt_rollback_logical_state = false;
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
  int bounded_local_pibt_max_inheritance_depth = 0;
  int bounded_local_pibt_max_slice_bags = 0;
  int bounded_local_pibt_max_slice_resources = 0;
  int bounded_local_pibt_max_candidates_per_bag = 0;
  int bounded_local_pibt_max_transaction_credit_entries = 0;
  int bounded_local_pibt_max_transaction_bag_entries = 0;
  int bounded_local_pibt_max_transaction_junction_scalar_entries = 0;
  int bounded_local_pibt_max_transaction_action_deltas = 0;
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
  std::vector<EventRuntimeJunctionOpportunityRow> junction_arbitration_opportunities;
  std::vector<EventRuntimeMergeVisibilityRow> merge_request_visibility;
  std::vector<EventRuntimeEventSeqAuditRow> event_seq_ordering_audit;
  std::vector<EventRuntimeArbitrationBatchRow> arbitration_batch_cardinality;
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
  void purge(double now) {
    intervals_.erase(
        std::remove_if(intervals_.begin(), intervals_.end(), [now](const CalendarInterval& item) {
          return item.end <= now + kEpsilon;
        }),
        intervals_.end());
  }

  [[nodiscard]] bool available(double start, double end, int ignore_task = -1) const {
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
    intervals_.push_back(CalendarInterval{task_id, start, end});
    std::sort(intervals_.begin(), intervals_.end(), [](const auto& left, const auto& right) {
      return std::tie(left.start, left.end, left.task_id) <
             std::tie(right.start, right.end, right.task_id);
    });
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
    return true;
  }

  [[nodiscard]] int size() const { return static_cast<int>(intervals_.size()); }

  [[nodiscard]] std::uint64_t logical_state_fingerprint() const noexcept {
    std::uint64_t hash = 1469598103934665603ULL;
    const auto mix = [&](std::uint64_t value) {
      hash ^= value;
      hash *= 1099511628211ULL;
    };
    mix(static_cast<std::uint64_t>(intervals_.size()));
    for (const auto& interval : intervals_) {
      mix(static_cast<std::uint64_t>(
          static_cast<std::uint32_t>(interval.task_id)));
      mix(timestamp_bits(interval.start));
      mix(timestamp_bits(interval.end));
    }
    return hash;
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
  std::vector<CalendarInterval> intervals_;
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

  [[nodiscard]] std::size_t current_local_state_accounted_bytes() const noexcept {
    // std::deque does not expose retained block capacity, so live element
    // payload is the strongest portable lower bound available here.
    return sizeof(JunctionState) + source_queue.size() * sizeof(int) +
           queue.size() * sizeof(int) +
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
};

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
  if (event.type == JunctionEventType::kEdgeEnter) {
    return 9;
  }
  return 10;  // LOCAL_QUEUE_UPDATE
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

struct G4IRSF14RuntimeState {
  std::unordered_map<int, LocalArbitrationState> local;
  std::uint64_t current_event_seq = 0;
  bool microphase_floor_active = false;
  double microphase_floor_time = 0.0;
  int microphase_floor_priority = -1;
  int current_pibt_slice_bag_count = 0;
  int current_pibt_owner_count = 0;
};

static_assert(std::is_nothrow_move_constructible_v<RuntimeEvent>);
static_assert(std::is_nothrow_move_assignable_v<RuntimeEvent>);

}  // namespace event_runtime_detail

class EventDrivenJunctionRuntime {
 public:
  explicit EventDrivenJunctionRuntime(const Graph& graph, EventDrivenJunctionConfig config = {})
      : graph_(graph), config_(std::move(config)) {
    validate_config();
    if (g4irsf14_extensions_enabled()) {
      g4irsf14_state_ =
          std::make_unique<event_runtime_detail::G4IRSF14RuntimeState>();
    }
    initialize_regret_prior();
    initialize_scorer();
  }

  EventDrivenJunctionResult run(const std::vector<EventRuntimeBagRequest>& requests,
                                const std::vector<EventRuntimeFaultWindow>& fault_windows = {}) {
    const auto runtime_started = std::chrono::steady_clock::now();
    reset();
    result_.summary.requested_count = static_cast<int>(requests.size());
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
        "credit_transaction_scoped_to_selected_action_ids;"
        "transaction_state_bounded_by_selected_bags_nodes_and_corridors;"
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

    const double time_limit = config_.max_simulation_time >= 0.0
                                  ? config_.max_simulation_time
                                  : latest_release + 86400.0;
    while (!events_.empty()) {
      if (result_.summary.event_count >= config_.max_events) {
        result_.summary.event_limit_reached = true;
        break;
      }
      auto event = events_.top();
      events_.pop();
      if (event.time > time_limit + event_runtime_detail::kEpsilon) {
        result_.summary.time_limit_reached = true;
        break;
      }
      now_ = event.time;
      ++result_.summary.event_count;
      process_event(event);
    }

    active_backlog_at_runtime_stop_ = active_bag_count_;
    finalize_incomplete();
    build_bag_results();
    build_junction_results();
    build_credit_results();
    finish_summary();
    const std::chrono::duration<double> runtime_elapsed =
        std::chrono::steady_clock::now() - runtime_started;
    result_.summary.runtime_seconds = runtime_elapsed.count();
    result_.summary.event_throughput_per_second =
        runtime_elapsed.count() > 0.0
            ? static_cast<double>(result_.summary.event_count) / runtime_elapsed.count()
            : 0.0;
    return result_;
  }

 private:
  using BagState = event_runtime_detail::BagState;
  using BagStatus = event_runtime_detail::BagStatus;
  using CalendarInterval = event_runtime_detail::CalendarInterval;
  using JunctionState = event_runtime_detail::JunctionState;
  using LocalCalendar = event_runtime_detail::LocalCalendar;
  using RuntimeEvent = event_runtime_detail::RuntimeEvent;

  static bool mode_is(const std::string& actual,
                      const std::string& short_name,
                      const std::string& full_name) {
    return actual == short_name || actual == full_name;
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
    throw std::invalid_argument(
        "event_semantics must be E0, E1, E2, or E3");
  }

  bool batches_source_same_timestamp() const {
    const auto mode = canonical_event_semantics();
    return mode == "E1_batch_source_same_timestamp" ||
           mode == "E3_batch_source_and_junction_same_timestamp";
  }

  bool batches_junction_same_timestamp() const {
    const auto mode = canonical_event_semantics();
    return mode == "E2_batch_junction_same_timestamp" ||
           mode == "E3_batch_source_and_junction_same_timestamp";
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
    result_ = {};
    bags_.clear();
    segment_runtime_ids_.clear();
    junctions_.clear();
    corridors_.clear();
    physical_faults_.clear();
    advertised_faults_.clear();
    congestion_beacons_.clear();
    credit_ledger_ = ExpiringFirstEdgeCreditLedger(
        static_cast<std::size_t>(config_.credit_lifecycle_limit));
    directed_inflight_counts_.clear();
    fault_affected_bags_.clear();
    fault_affected_bags_by_edge_.clear();
    fault_instances_by_bag_.clear();
    active_fault_instance_by_edge_.clear();
    repair_time_by_fault_instance_.clear();
    events_ = {};
    next_event_seq_ = 1;
    next_decision_id_ = 1;
    next_pibt_activation_id_ = 1;
    next_local_enqueue_sequence_ = 1;
    staged_event_sink_ = nullptr;
    staged_merge_visibility_sink_ = nullptr;
    staged_destination_known_competitor_counts_ =
        nullptr;
#ifdef CZR005_EVENT_RUNTIME_TESTING
    test_pibt_logical_failure_injected_ = false;
#endif
    if (g4irsf14_state_ != nullptr) {
      *g4irsf14_state_ =
          event_runtime_detail::G4IRSF14RuntimeState{};
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
    if (mode == "E3_batch_source_and_junction_same_timestamp") {
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
      if (event.type == JunctionEventType::kEdgeEnter) {
        return 6;
      }
      return 7;
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

  int try_admit_source(
      int node,
      double time,
      int* chosen_task = nullptr,
      int* priority_comparison_count = nullptr) {
    auto& controller = junctions_[node];
    controller.service_calendar.purge(time);
    controller.observe_local_state();
    if (controller.source_queue.empty()) {
      return -1;
    }
    const std::size_t queue_index =
        choose_bag(controller.source_queue,
                   time,
                   controller.escape_token_task,
                   priority_comparison_count);
    const int task_id = controller.source_queue[queue_index];
    if (chosen_task != nullptr) {
      *chosen_task = task_id;
    }
    auto& bag = bags_.at(task_id);
    const double duration = service_duration(node);
    ++result_.summary.source_admission_attempt_count;
    const bool queue_has_room = config_.local_queue_capacity <= 0 ||
                                static_cast<int>(controller.queue.size()) < config_.local_queue_capacity;
    if (!queue_has_room || !controller.service_calendar.available(time, time + duration, task_id)) {
      ++result_.summary.source_admission_local_resource_hold_count;
      return -1;
    }
    const auto admission_mode = canonical_admission_mode();
    if (admission_mode == "legacy_unbound" &&
        !downstream_admission_ready(bag, node, time, duration)) {
      ++result_.summary.source_admission_downstream_pressure_hold_count;
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
                                  false)) {
      ++result_.summary.source_admission_downstream_pressure_hold_count;
      ++result_.summary.first_edge_credit_local_hold_count;
      request_one_hop_credit_snapshot_refresh(node, time);
      return -1;
    }
    if (node == bag.request.goal) {
      bag.first_edge_credit_consumed = true;
    }

    controller.service_calendar.reserve(task_id, time, time + duration);
    controller.record_service_reservation(time, time + duration);
    update_calendar_maxima(controller, nullptr);
    controller.source_queue.erase(controller.source_queue.begin() + static_cast<std::ptrdiff_t>(queue_index));
    controller.observe_local_state();
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
    return task_id;
  }

  bool downstream_admission_ready(const BagState& bag,
                                  int node,
                                  double time,
                                  double source_service_duration) {
    if (node == bag.request.goal) {
      return true;
    }
    const auto& outgoing = graph_.outgoing(node);
    bool ready = false;
    for (const int downstream : outgoing) {
      ++result_.summary.source_admission_beacon_read_count;
      const auto snapshot = congestion_beacons_.find(downstream);
      if (snapshot == congestion_beacons_.end()) {
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
      ready = ready ||
              (physical_edge_ready && local_corridor_ready &&
               downstream_calendar_ready &&
               downstream_queue_ready);
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
                                bool dispatch_retry) {
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
        const auto rejected = credit_ledger_.issue(request);
        (void)rejected;
        continue;
      }
      if (!local_corridor_ready || !downstream_calendar_ready ||
          !downstream_queue_ready) {
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
    if (canonical_pibt_mode() != BoundedLocalPIBTMode::kP0) {
      dispatch =
          try_dispatch_bounded_local_pibt(
              event.node,
              event.time,
              event.seq,
              comparison_counter);
      bounded_local_same_bag_fallback_next =
          dispatch.same_bag_fallback_next;
    }
    if (!dispatch.handled) {
      dispatch = try_dispatch_one(
          event.node,
          event.time,
          event.seq,
          bounded_local_same_bag_fallback_next,
          comparison_counter);
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
    if (!controller.queue.empty() && !controller.junction_wakeup_pending) {
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
    int decision_count = 0;
    double deadlock_started_at = -1.0;
    std::uint64_t first_edge_credit_id = 0;
    bool first_edge_credit_consumed = false;
  };

  struct PIBTJunctionSnapshot {
    int node = -1;
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

  struct PIBTActionDelta {
    int bag_id = -1;
    int from_node = -1;
    int next_node = -1;
    std::size_t queue_index = 0;
    bool has_corridor_reservation = false;
    bool corridor_existed = false;
    long long corridor_key = 0;
    double corridor_start = 0.0;
    double corridor_end = 0.0;
    bool has_destination_reservation = false;
    double destination_start = 0.0;
    double destination_end = 0.0;
  };

  struct PIBTStagedMergeVisibility {
    EventRuntimeMergeVisibilityRow merge;
    EventRuntimeEventSeqAuditRow audit;
  };

  struct PIBTCorridorSnapshot {
    bool existed = false;
    std::uint64_t logical_state_fingerprint = 0;
  };

  struct PIBTTransactionSnapshot {
    bool captured = false;
    bool mutated = false;
    int credit_entry_count = 0;
    std::size_t applied_action_count = 0;
    EventRuntimeSummary summary;
    std::map<int, PIBTBagSnapshot> bags;
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
    std::size_t event_queue_size = 0;
    std::uint64_t event_queue_logical_fingerprint = 0;
    std::size_t merge_visibility_size = 0;
    std::size_t event_seq_audit_size = 0;
    FirstEdgeCreditCounters credit_counters;
    std::size_t credit_active_count = 0;
    std::size_t credit_lifecycle_count = 0;
#endif
  };

  class PIBTLogicalCommitFailure : public std::runtime_error {
   public:
    explicit PIBTLogicalCommitFailure(const std::string& message)
        : std::runtime_error(message) {}
  };

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
                           int physical_generation) {
    bag.fault_priority_generation =
        std::max(
            bag.fault_priority_generation,
            static_cast<std::uint64_t>(
                std::max(0, physical_generation)));
    bag.repaired_task_reentry = false;
    fault_affected_bags_.insert(bag.request.runtime_bag_id);
    fault_affected_bags_by_edge_[physical_key].insert(
        bag.request.runtime_bag_id);
    const auto active_instance =
        active_fault_instance_by_edge_.find(physical_key);
    if (active_instance != active_fault_instance_by_edge_.end()) {
      fault_instances_by_bag_[bag.request.runtime_bag_id].insert(
          {physical_key, active_instance->second});
    }
    result_.summary.fault_affected_bag_count =
        static_cast<int>(fault_affected_bags_.size());
  }

  void clear_consumed_repair_reentry_boost(BagState& bag) {
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

  PIBTLocalSlice build_pibt_local_slice(int trigger_node,
                                        int trigger_runtime_bag_id,
                                        double time,
                                        std::uint64_t arrive_event_seq,
                                        int* priority_comparison_count) {
    PIBTLocalSlice slice;
    slice.trigger_runtime_bag_id = trigger_runtime_bag_id;
    if (config_.local_queue_capacity <= 0) {
      slice.blocker = "queue_capacity_unknown_or_unlimited";
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
        preferred->shield_reason != "destination_queue_full" ||
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

      for (const auto& record : trace.candidates) {
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
            occupancy >= config_.local_queue_capacity) {
          blocker_owner = pibt_ready_owner_at_node(
              target,
              time,
              priority_comparison_count);
          if (!blocker_owner.has_value()) {
            continue;
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
      std::string& blocker) const {
    if (actions.empty() ||
        static_cast<int>(actions.size()) > config_.pibt_max_ready_bags) {
      blocker = "empty_or_oversized_action_batch";
      return false;
    }
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
      if (queue_size - leaving + scheduled + entering >
          config_.local_queue_capacity) {
        blocker = "finite_local_queue_capacity_prevalidation_failed";
        return false;
      }
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
               right.bounded_local_pibt_max_transaction_action_deltas;
  }
#endif

  void capture_pibt_transaction(
      const std::vector<BoundedLocalPIBTAction>& actions,
      double time,
      PIBTTransactionSnapshot& snapshot) {
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
        saved.queue = junction.queue;
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
        saved.scheduled_incoming_by_goal =
            junction.scheduled_incoming_by_goal;
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
              bag.decision_count,
              bag.deadlock_started_at,
              bag.first_edge_credit_id,
              bag.first_edge_credit_consumed});
      auto& from_saved = capture_junction(action.from_node);
      (void)capture_junction(action.next_node);

      const auto& from = junctions_.at(action.from_node);
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
      if (uses_corridor_calendar()) {
        delta.has_corridor_reservation = true;
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
        delta.has_destination_reservation = true;
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
    for (std::size_t index = snapshot.applied_action_count;
         index > 0;
         --index) {
      const auto& delta =
          snapshot.action_deltas[index - 1];
      if (delta.has_corridor_reservation) {
        const auto corridor =
            corridors_.find(delta.corridor_key);
        if (corridor != corridors_.end()) {
          corridor->second.erase_exact(
              delta.bag_id,
              delta.corridor_start,
              delta.corridor_end);
          if (!delta.corridor_existed &&
              corridor->second.size() == 0) {
            corridors_.erase(corridor);
          }
        }
      }
      if (delta.has_destination_reservation) {
        junctions_.at(delta.next_node)
            .service_calendar.erase_exact(
                delta.bag_id,
                delta.destination_start,
                delta.destination_end);
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
#ifdef CZR005_EVENT_RUNTIME_TESTING
      snapshot.calendar_logical_state_restored =
          snapshot.calendar_logical_state_restored &&
          corridor->second.logical_state_fingerprint() ==
              entry.second.logical_state_fingerprint;
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
      bag.decision_count = saved.decision_count;
      bag.deadlock_started_at = saved.deadlock_started_at;
      bag.first_edge_credit_id = saved.first_edge_credit_id;
      bag.first_edge_credit_consumed =
          saved.first_edge_credit_consumed;
    }
    for (auto& entry : snapshot.junctions) {
      auto& junction = junctions_.at(entry.first);
      auto& saved = entry.second;
      junction.queue.swap(saved.queue);
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
      junction.scheduled_incoming_by_goal.swap(
          saved.scheduled_incoming_by_goal);
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
    snapshot.applied_action_count = 0;
    snapshot.mutated = false;
  }

#ifdef CZR005_EVENT_RUNTIME_TESTING
  bool pibt_logical_state_matches_snapshot(
      const PIBTTransactionSnapshot& snapshot) const {
    if (!snapshot.calendar_logical_state_restored) {
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
      std::string& blocker) {
    if (!prevalidate_pibt_batch(actions, time, blocker)) {
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
        // Arm the current differential rollback entry before the first
        // mutation.  dispatch_selected_edge may have inserted one calendar
        // interval or staged one event before an exception is raised.
        ++snapshot.applied_action_count;
        try {
          dispatch_selected_edge(
              bag, action.from_node, action.next_node, time);
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
        const auto queued = std::find(controller.queue.begin(),
                                      controller.queue.end(),
                                      action.bag_id);
        if (queued == controller.queue.end()) {
          blocker = "ready_owner_disappeared_during_commit";
          throw PIBTLogicalCommitFailure(blocker);
        }
        controller.queue.erase(queued);
        controller.observe_local_state();
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
        if (!controller.queue.empty() &&
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
    for (auto& event : snapshot.staged_events) {
      publish_prepared_reserved_event(
          std::move(event));
    }
    snapshot.staged_events.clear();
    for (auto& visibility :
         snapshot.staged_merge_visibility) {
      publish_merge_visibility(std::move(visibility));
    }
    snapshot.staged_merge_visibility.clear();
    snapshot.applied_action_count = 0;
    snapshot.mutated = false;
    for (const auto& action : actions) {
      clear_consumed_repair_reentry_boost(
          bags_.at(action.bag_id));
    }
    return true;
  }

  DispatchResult try_dispatch_bounded_local_pibt(
      int node,
      double time,
      std::uint64_t arrive_event_seq,
      int* priority_comparison_count) {
    auto& controller = junctions_[node];
    if (controller.queue.empty() ||
        time + event_runtime_detail::kEpsilon <
            controller.next_dispatch_time) {
      return {};
    }
    const std::size_t root_index =
        choose_bag(controller.queue,
                   time,
                   controller.escape_token_task,
                   priority_comparison_count);
    const int trigger_runtime_bag_id = controller.queue[root_index];
    const auto decision_started = std::chrono::steady_clock::now();
    PIBTLocalSlice slice = build_pibt_local_slice(
        node,
        trigger_runtime_bag_id,
        time,
        arrive_event_seq,
        priority_comparison_count);
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
              actions, time, callback_blocker);
        };
    callbacks.commit =
        [&](const std::vector<BoundedLocalPIBTAction>& actions) {
          return commit_pibt_batch(
              actions, time, transaction, callback_blocker);
        };
    callbacks.rollback =
        [&](const std::vector<BoundedLocalPIBTAction>&) {
          restore_pibt_transaction(transaction);
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
      ++result_.summary.bounded_local_pibt_not_applicable_count;
      callback_blocker =
          std::string("resolver_slice_validation_failed:") + error.what();
      return {};
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

    EventRuntimePIBTAuditRow audit;
    audit.activation_id = next_pibt_activation_id_++;
    audit.time = time;
    audit.trigger_node = node;
    audit.trigger_runtime_bag_id = trigger_runtime_bag_id;
    audit.mode = canonical_pibt_mode_name();
    audit.outcome = bounded_local_pibt_outcome_name(resolved.outcome);
    audit.blocker =
        callback_blocker.empty() ? resolved.blocker : callback_blocker;
    audit.local_slice_bag_count =
        static_cast<int>(slice.traces_by_bag.size());
    audit.local_slice_resource_count = slice.resource_count;
    audit.local_slice_candidate_count = slice.candidate_count;
    audit.proposed_action_count =
        static_cast<int>(resolved.actions.size());
    audit.committed_action_count =
        resolved.committed ? static_cast<int>(resolved.actions.size()) : 0;
    audit.inherited_action_count = resolved.inherited_action_count;
    audit.max_inheritance_depth =
        resolved.max_inheritance_depth_observed;
    audit.backtrack_count = resolved.backtrack_count;
    audit.cycle_guard_count = resolved.visiting_cycle_guard_count;
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
    if (config_.trace_limit != 0 &&
        (config_.trace_limit < 0 ||
         static_cast<int>(result_.pibt_events.size()) <
             config_.trace_limit)) {
      result_.pibt_events.push_back(std::move(audit));
    }

    if (!resolved.committed) {
      ++result_.summary.bounded_local_pibt_not_applicable_count;
      int same_bag_fallback_next = -1;
      if (resolved.outcome ==
              BoundedLocalPIBTOutcome::kPrepareRejected &&
          callback_blocker ==
              "proposal_lacks_trigger_or_real_blocker_owner_move" &&
          resolved.inherited_action_count == 0 &&
          resolved.actions.size() == 1) {
        const auto& action = resolved.actions.front();
        if (action.bag_id == trigger_runtime_bag_id &&
            action.from_node == node && !action.inherited &&
            graph_.has_edge(action.from_node, action.next_node)) {
          // This root-only proposal is not a true PIBT commit because no
          // blocker moved.  Preserve its already-materialized adjacent edge
          // only as a candidate for the ordinary one-bag dispatch path,
          // which revalidates the current shield/credit state before commit.
          same_bag_fallback_next = action.next_node;
        }
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
        required_trigger_blocker_bag_ids(resolved.actions);
    ++result_.summary.bounded_local_pibt_committed_batch_count;
    result_.summary.bounded_local_pibt_handoff_count +=
        resolved.inherited_action_count;
    result_.summary.bounded_local_pibt_committed_action_count +=
        resolved.actions.size();
    result_.summary.max_edges_selected_per_bag_per_decision =
        std::max(
            result_.summary.max_edges_selected_per_bag_per_decision,
            resolved.actions.empty() ? 0 : 1);
    result_.summary.max_actions_committed_per_pibt_batch =
        std::max(
            result_.summary.max_actions_committed_per_pibt_batch,
            static_cast<int>(resolved.actions.size()));
    int trigger_next = -1;
    for (const auto& action : resolved.actions) {
      auto trace = slice.traces_by_bag.at(action.bag_id);
      record_committed_pibt_fault_accounting(
          trace, bags_.at(action.bag_id), action.next_node);
      trace.selected_next = action.next_node;
      trace.fallback_selected_next =
          action.inherited ? action.next_node : -1;
      trace.decision_source =
          action.bag_id == trigger_runtime_bag_id
              ? "bounded_local_pibt_trigger_action"
          : action.inherited
              ? "bounded_local_pibt_inherited_action"
          : selected_trigger_blocker_bag_ids.find(action.bag_id) !=
                    selected_trigger_blocker_bag_ids.end()
              ? "bounded_local_pibt_blocker_owner_action"
              : "bounded_local_pibt_independent_ready_action";
      trace.rule_reason =
          (trace.scorer_risk_abstain
               ? "frozen_scorer_risk_abstain_exact_s0_fallback;"
               : "") +
          std::string(
              "bounded_local_pibt_logical_failure_atomic_one_edge_batch");
      append_decision_trace(std::move(trace), true);
      if (action.bag_id == trigger_runtime_bag_id) {
        trigger_next = action.next_node;
      }
    }
    record_decision_latency(decision_started);
    return DispatchResult{
        trigger_runtime_bag_id, trigger_next, 1, true};
  }

  DispatchResult try_dispatch_one(
      int node,
      double time,
      std::uint64_t arrive_event_seq,
      int bounded_local_same_bag_fallback_next = -1,
      int* priority_comparison_count = nullptr) {
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
    if (bag.decision_count >= config_.max_decisions_per_bag) {
      fail_bag(bag, "max_decisions_exceeded", time);
      controller.queue.erase(controller.queue.begin() + static_cast<std::ptrdiff_t>(queue_index));
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

    bool first_edge_credit_bound = false;
    if (selected >= 0 && first_edge_credit_required) {
      const auto bound = credit_ledger_.bind(
          bag.first_edge_credit_id,
          credit_use_context(bag, node, selected, time));
      if (!bound.accepted) {
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
      dispatch_selected_edge(bag, node, selected, time);
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
      const double retry_time = std::isfinite(earliest_resource_retry)
                                    ? std::max(time + config_.retry_interval,
                                               earliest_resource_retry)
                                    : time + config_.retry_interval;
      schedule_junction_wakeup(node, retry_time);
    }

    append_decision_trace(std::move(trace), selected >= 0);
    record_decision_latency(decision_started);
    return DispatchResult{task_id, selected, selected >= 0 ? 1 : 0, true};
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
                                  bag.request.goal)) {
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

  void dispatch_selected_edge(BagState& bag, int current, int selected, double time) {
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
      corridor->reserve(bag.request.runtime_bag_id, time, corridor_end);
    }
    if (uses_destination_calendar(selected,
                                  bag.request.goal)) {
      target.service_calendar.reserve(bag.request.runtime_bag_id,
                                      exit_time,
                                      service_end);
      target.record_service_reservation(exit_time, service_end);
    }
    ++target.scheduled_incoming;
    ++target.scheduled_incoming_by_goal[bag.request.goal];
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
    const long long directed =
        event_runtime_detail::directed_key(event.from_node, event.to_node);
    const auto inflight = directed_inflight_counts_.find(directed);
    if (inflight != directed_inflight_counts_.end()) {
      inflight->second = std::max(0, inflight->second - 1);
      if (inflight->second == 0) {
        directed_inflight_counts_.erase(inflight);
      }
    }
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
                       "edge_traversal_complete",
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
    row.later_same_time_competitor_count =
        later_competitors;
    row.later_same_time_competitor_exists =
        later_competitors > 0;
    row.seq_determined_order =
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
        later_competitors;
    audit.chosen_runtime_bag_id =
        bag.request.runtime_bag_id;
    audit.chosen_enqueue_sequence =
        bag.local_enqueue_sequence;
    audit.event_seq = row.event_seq;
    audit.seq_determined_order =
        row.seq_determined_order;
    audit.reason = row.seq_determined_order
                       ? "later_same_time_competitor_not_yet_reserved"
                       : "no_later_same_time_destination_competitor";
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
    // Keep the frozen Win64 E0 accounted-byte scalar exact. The append-only
    // config/result/state holders are inactive there and must not perturb a
    // deterministic compatibility hash merely because their empty C++
    // container objects exist in the class layout.
    std::size_t runtime_object_bytes = sizeof(*this);
#if defined(_MSC_VER) && defined(_WIN64)
    if (!g4irsf14_extensions_enabled()) {
      runtime_object_bytes = 4496;
    }
#endif
    std::size_t accounted = runtime_object_bytes;
    accounted += bags_.size() * sizeof(BagState);
    for (const auto& entry : junctions_) {
      accounted += entry.second.current_local_state_accounted_bytes();
    }
    for (const auto& entry : corridors_) {
      accounted += sizeof(LocalCalendar) +
                   entry.second.dynamic_interval_capacity_accounted_bytes();
    }
    accounted += physical_faults_.size() * sizeof(event_runtime_detail::FaultState);
    accounted += advertised_faults_.size() * sizeof(event_runtime_detail::AdvertisedFaultState);
    accounted += congestion_beacons_.size() *
                 sizeof(event_runtime_detail::CongestionBeaconState);
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
    accounted += result_.bags.capacity() * sizeof(EventRuntimeBagResult);
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
        result_.junction_arbitration_opportunities.capacity() *
        sizeof(EventRuntimeJunctionOpportunityRow);
    accounted += result_.merge_request_visibility.capacity() *
                 sizeof(EventRuntimeMergeVisibilityRow);
    accounted += result_.event_seq_ordering_audit.capacity() *
                 sizeof(EventRuntimeEventSeqAuditRow);
    accounted +=
        result_.arbitration_batch_cardinality.capacity() *
        sizeof(EventRuntimeArbitrationBatchRow);
    if (g4irsf14_state_ != nullptr) {
      accounted +=
          sizeof(event_runtime_detail::G4IRSF14RuntimeState);
      accounted +=
          g4irsf14_state_->local.size() *
          sizeof(std::pair<const int,
                           event_runtime_detail::
                               LocalArbitrationState>);
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
#ifdef CZR005_EVENT_RUNTIME_TESTING
  bool test_pibt_logical_failure_injected_ = false;
#endif
  std::uint64_t next_event_seq_ = 1;
  std::uint64_t next_decision_id_ = 1;
  std::uint64_t next_pibt_activation_id_ = 1;
  std::uint64_t next_local_enqueue_sequence_ = 1;
  double now_ = 0.0;
  int active_bag_count_ = 0;
  double last_physical_repair_time_ = -1.0;
  int active_backlog_at_last_repair_ = -1;
  int active_backlog_at_runtime_stop_ = -1;
  std::vector<double> waits_;
  std::vector<double> decision_latencies_us_;
  std::unique_ptr<event_runtime_detail::G4IRSF14RuntimeState>
      g4irsf14_state_;
};

}  // namespace czr005::ics
