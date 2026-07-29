#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <numeric>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"
#include "ics_core/runtime/g4irsf14_causal_intervention.hpp"

#ifndef CZR005_SOURCE_DIR
#error "CZR005_SOURCE_DIR must identify the repository root"
#endif

namespace {

using namespace czr005::ics;

void require(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

template <typename Callable>
void require_invalid(Callable&& callable,
                     const std::string& message) {
  bool rejected = false;
  try {
    callable();
  } catch (const std::invalid_argument&) {
    rejected = true;
  }
  require(rejected, message);
}

const CanonicalMap2ReadResult& canonical_map2() {
  static const auto map = read_canonical_map2_json(
      std::filesystem::path(CZR005_SOURCE_DIR) / "data" /
      "processed" / "maps" / "map2.json");
  require(
      map.normalized_sha256 ==
          "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63",
      "causal fixture must use canonical map2");
  return map;
}

void skip_space(const std::string& text, std::size_t& cursor) {
  while (cursor < text.size() &&
         std::isspace(
             static_cast<unsigned char>(text[cursor]))) {
    ++cursor;
  }
}

std::size_t value_cursor(const std::string& text,
                         const std::string& key) {
  const auto key_position = text.find("\"" + key + "\"");
  require(key_position != std::string::npos,
          "frozen S1 model key is missing");
  const auto colon = text.find(':', key_position);
  require(colon != std::string::npos,
          "frozen S1 model key has no value");
  std::size_t cursor = colon + 1;
  skip_space(text, cursor);
  return cursor;
}

double parse_number(const std::string& text,
                    std::size_t& cursor) {
  skip_space(text, cursor);
  char* end = nullptr;
  const double value =
      std::strtod(text.c_str() + cursor, &end);
  require(end != text.c_str() + cursor &&
              std::isfinite(value),
          "frozen S1 model contains an invalid number");
  cursor = static_cast<std::size_t>(
      end - text.c_str());
  return value;
}

std::vector<double> parse_vector(
    const std::string& text, std::size_t& cursor) {
  skip_space(text, cursor);
  require(cursor < text.size() && text[cursor] == '[',
          "frozen S1 vector must start with [");
  ++cursor;
  std::vector<double> values;
  while (true) {
    skip_space(text, cursor);
    require(cursor < text.size(),
            "unterminated frozen S1 vector");
    if (text[cursor] == ']') {
      ++cursor;
      return values;
    }
    values.push_back(parse_number(text, cursor));
    skip_space(text, cursor);
    if (cursor < text.size() && text[cursor] == ',') {
      ++cursor;
    }
  }
}

std::vector<std::vector<double>> parse_matrix(
    const std::string& text, std::size_t& cursor) {
  skip_space(text, cursor);
  require(cursor < text.size() && text[cursor] == '[',
          "frozen S1 matrix must start with [");
  ++cursor;
  std::vector<std::vector<double>> rows;
  while (true) {
    skip_space(text, cursor);
    require(cursor < text.size(),
            "unterminated frozen S1 matrix");
    if (text[cursor] == ']') {
      ++cursor;
      return rows;
    }
    rows.push_back(parse_vector(text, cursor));
    skip_space(text, cursor);
    if (cursor < text.size() && text[cursor] == ',') {
      ++cursor;
    }
  }
}

EventDrivenJunctionConfig frozen_config() {
  static const auto model_text = [] {
    std::ifstream stream(
        std::filesystem::path(CZR005_SOURCE_DIR) / "artifacts" /
            "models" / "g4e_risk_calibrated_policy.json",
        std::ios::binary);
    require(static_cast<bool>(stream),
            "cannot open frozen S1 model");
    return std::string{
        std::istreambuf_iterator<char>{stream},
        std::istreambuf_iterator<char>{}};
  }();
  EventDrivenJunctionConfig config;
  config.resource_semantics = "R3";
  config.event_semantics = "E4";
  config.merge_grant_rule = "M0";
  config.enable_backpressure = false;
  config.pressure_mode = "C0";
  config.enable_source_admission = false;
  config.admission_mode = "off";
  config.pibt_mode = "P2";
  config.priority_mode = "Q0";
  config.scorer_mode = "S1";
  auto w1 = value_cursor(model_text, "w1");
  config.scorer_w1 = parse_matrix(model_text, w1);
  auto b1 = value_cursor(model_text, "b1");
  config.scorer_b1 = parse_vector(model_text, b1);
  auto w2 = value_cursor(model_text, "w2");
  config.scorer_w2 = parse_vector(model_text, w2);
  auto b2 = value_cursor(model_text, "b2");
  config.scorer_b2 = parse_number(model_text, b2);
  config.scorer_model_sha256 =
      "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca";
  config.trace_limit = -1;
  config.event_trace_limit = -1;
  config.max_events = 200000;
  config.max_simulation_time = 500.0;
  config.retry_interval = 0.25;
  config.merge_grant_max_pending_requests = 16;
  config.merge_grant_lifecycle_limit = 4096;
  return config;
}

double service_duration(int node,
                        const EventDrivenJunctionConfig& config) {
  return std::max(canonical_map2().graph.service_time(node),
                  config.minimum_service_seconds);
}

EventRuntimeBagRequest request(int task_id,
                               int start,
                               int goal,
                               double ready_time,
                               std::string segment) {
  EventRuntimeBagRequest value;
  value.segment_id = std::move(segment);
  value.task_id = task_id;
  value.release_time =
      ready_time - service_duration(start, frozen_config());
  value.deadline = 1000.0;
  value.start = start;
  value.goal = goal;
  value.source = "NON_FORMAL_CAUSAL_RUNTIME_FIXTURE";
  return value;
}

EventRuntimeBagRequest raw_sidecar_request(
    int task_id, std::string segment_id, double release_time,
    double deadline) {
  EventRuntimeBagRequest value;
  value.task_id = task_id;
  value.segment_id = std::move(segment_id);
  value.release_time = release_time;
  value.deadline = deadline;
  value.start = 46;
  value.goal = 51;
  value.source = "NON_FORMAL_RAW_SIDECAR_FIXTURE";
  return value;
}

G4IRSF15CausalBagOutcome raw_sidecar_outcome(
    int runtime_bag_id,
    const EventRuntimeBagRequest& request,
    double admitted_time, double finish_time,
    double source_wait_seconds) {
  G4IRSF15CausalBagOutcome value;
  value.runtime_bag_id = runtime_bag_id;
  value.task_id = request.task_id;
  value.segment_id = request.segment_id;
  value.start = request.start;
  value.goal = request.goal;
  value.current_node = request.goal;
  value.known = true;
  value.completed = true;
  value.failed = false;
  value.release_time = request.release_time;
  value.deadline = request.deadline;
  value.admitted_time = admitted_time;
  value.finish_time = finish_time;
  value.source_wait_seconds = source_wait_seconds;
  value.completion_seconds =
      finish_time - request.release_time;
  value.status = "COMPLETED";
  return value;
}

struct CapturedOpportunity {
  EventDrivenJunctionRuntime::StateCheckpoint checkpoint;
  G4IRSF14CloneBoundary boundary;
};

std::uint32_t mask_for(
    G4IRSF14CloneBoundaryKind kind) {
  switch (kind) {
    case G4IRSF14CloneBoundaryKind::kSourceArbitration:
      return kG4IRSF14CausalCandidateI1;
    case G4IRSF14CloneBoundaryKind::kMergeGrantArbitration:
      return kG4IRSF14CausalCandidateI2;
    case G4IRSF14CloneBoundaryKind::kJunctionRouteArbitration:
      return kG4IRSF14CausalCandidateI3;
    case G4IRSF14CloneBoundaryKind::kHoldReleaseOpportunity:
      return kG4IRSF14CausalCandidateI4;
    case G4IRSF14CloneBoundaryKind::kPIBTReadySlice:
      return kG4IRSF14CausalCandidateI5;
  }
  throw std::logic_error("unknown causal boundary kind");
}

CapturedOpportunity capture_opportunity(
    EventDrivenJunctionRuntime& runtime,
    G4IRSF14CloneBoundaryKind kind,
    std::uint32_t mask) {
  for (int event = 0; event < 200000; ++event) {
    const auto hint =
        runtime.peek_causal_candidate_kind_mask();
    if ((hint & mask) == 0U) {
      require(runtime.process_one_event(),
              "runtime stopped before causal opportunity kind=" +
                  std::to_string(static_cast<int>(kind)));
      continue;
    }
    auto checkpoint = runtime.capture_state_checkpoint();
    const auto probe =
        runtime.probe_one_event_for_causal_opportunities();
    require(probe.application_reason ==
                "PROBE_ONLY_NO_ACTION_CHANGED" &&
                probe.changed_action_count == 0,
            "opportunity census must remain action-free");
    for (const auto& observed :
         probe.observed_opportunities) {
      require((hint & mask_for(observed.kind)) != 0U,
              "cheap candidate mask must cover every observed opportunity");
    }
    const auto found = std::find_if(
        probe.observed_opportunities.begin(),
        probe.observed_opportunities.end(),
        [&](const auto& opportunity) {
          return opportunity.kind == kind;
        });
    if (found != probe.observed_opportunities.end()) {
      require(checkpoint.state_sha256() ==
                  found->runtime_state_sha256,
              "opportunity must bind the pre-pop checkpoint");
      return {std::move(checkpoint), *found};
    }
  }
  throw std::runtime_error(
      "requested causal opportunity was not discovered");
}

G4IRSF14CausalInterventionDirective make_directive(
    const G4IRSF14CloneBoundary& boundary) {
  G4IRSF14CausalInterventionDirective directive;
  directive.boundary = boundary;
  directive.intervention.horizon =
      G4IRSF14CloneHorizon::kAffectedBag;
  switch (boundary.kind) {
    case G4IRSF14CloneBoundaryKind::kSourceArbitration:
      directive.intervention.kind =
          G4IRSF14CloneInterventionKind::kSourceOrderSwap;
      directive.intervention.runtime_bag_id =
          boundary.runtime_bag_id;
      directive.intervention.peer_runtime_bag_id =
          *std::find_if(
              boundary.source_ready_order.begin(),
              boundary.source_ready_order.end(),
              [&](int bag) {
                return bag != boundary.runtime_bag_id;
              });
      break;
    case G4IRSF14CloneBoundaryKind::kMergeGrantArbitration:
      directive.intervention.kind =
          G4IRSF14CloneInterventionKind::
              kMergeRequestOrderSwap;
      directive.intervention.merge_request_id =
          boundary.pending_merge_request_order.at(0);
      directive.intervention.peer_merge_request_id =
          boundary.pending_merge_request_order.at(1);
      break;
    case G4IRSF14CloneBoundaryKind::kJunctionRouteArbitration:
      directive.intervention.kind =
          G4IRSF14CloneInterventionKind::kNextEdge;
      directive.intervention.runtime_bag_id =
          boundary.runtime_bag_id;
      directive.intervention.selected_next_node =
          *std::find_if(
              boundary.legal_next_edges.begin(),
              boundary.legal_next_edges.end(),
              [&](int next) {
                return next != boundary.baseline_next_node;
              });
      break;
    case G4IRSF14CloneBoundaryKind::kHoldReleaseOpportunity:
      directive.intervention.kind =
          G4IRSF14CloneInterventionKind::kHoldRelease;
      directive.intervention.runtime_bag_id =
          boundary.runtime_bag_id;
      directive.intervention.selected_boolean = false;
      break;
    case G4IRSF14CloneBoundaryKind::kPIBTReadySlice:
      directive.intervention.kind =
          G4IRSF14CloneInterventionKind::kPIBTTrigger;
      directive.intervention.runtime_bag_id =
          boundary.runtime_bag_id;
      directive.intervention.selected_boolean = false;
      break;
  }
  directive.validate();
  return directive;
}

void apply_and_finish(
    const EventDrivenJunctionConfig& config,
    const CapturedOpportunity& captured) {
  EventDrivenJunctionRuntime treatment(
      canonical_map2().graph, config);
  treatment.restore_state_checkpoint(captured.checkpoint);
  require(treatment.deterministic_state_sha256() ==
              captured.boundary.runtime_state_sha256,
          "treatment restore must be exact");
  const auto applied =
      treatment.process_one_event_with_causal_intervention(
          make_directive(captured.boundary));
  require(applied.intervention_applied &&
              applied.changed_action_count == 1 &&
              applied.target_opportunity_observed &&
              !applied.affected_runtime_bag_ids.empty(),
          "content-addressed treatment must change exactly one action");
  treatment.drain();
  treatment.finalize();
  const auto horizon = treatment.causal_horizon_state(
      applied.affected_runtime_bag_ids);
  require(horizon.all_completed && horizon.failed_count == 0,
          "H_bag requires every affected bag to complete");
  const auto h_bag = treatment.causal_horizon_stop_state(
      G4IRSF14CloneHorizon::kAffectedBag,
      applied.affected_runtime_bag_ids,
      captured.boundary.node,
      0,
      1);
  std::vector<int> selected_system_bag_ids =
      applied.affected_runtime_bag_ids;
  for (const auto& bag : treatment.current_result().bags) {
    if (std::find(selected_system_bag_ids.begin(),
                  selected_system_bag_ids.end(),
                  bag.runtime_bag_id) ==
        selected_system_bag_ids.end()) {
      selected_system_bag_ids.push_back(bag.runtime_bag_id);
      break;
    }
  }
  require(
      selected_system_bag_ids.size() >
          applied.affected_runtime_bag_ids.size(),
      "H_system fixture must contain an unaffected selected bag");
  const auto h_system = treatment.causal_horizon_stop_state(
      G4IRSF14CloneHorizon::kSelectedSystem,
      selected_system_bag_ids,
      captured.boundary.node,
      0,
      1);
  require(h_bag.should_stop && h_bag.horizon_complete &&
              !h_bag.blocked &&
              h_system.should_stop &&
              h_system.horizon_complete &&
              !h_system.blocked,
          "H_bag/H_system must stop only on all-completed cohorts");
  const auto& summary = treatment.current_result().summary;
  require(summary.reservation_conflicts == 0 &&
              summary.physical_fault_edge_entry_violation_count == 0 &&
              summary.max_edges_selected_per_bag_per_decision <= 1 &&
              summary.completed_count == summary.requested_count &&
              summary.failed_count == 0 &&
              summary.runtime_full_astar_calls == 0 &&
              summary.global_reservation_scan_count == 0 &&
              summary.priority_future_route_input_count == 0 &&
              summary.priority_global_scan_count == 0 &&
              summary.scorer_future_route_input_count == 0 &&
              summary.scorer_future_schedule_input_count == 0 &&
              summary.scorer_runtime_global_scan_count == 0 &&
              summary.microphase_runtime_global_scan_count == 0 &&
              summary.first_edge_credit_future_route_count == 0 &&
              summary.first_edge_credit_global_scan_count == 0 &&
              summary.priority_teacher_input_count == 0 &&
              summary.scorer_teacher_input_count == 0 &&
              summary.two_step_reservation_count == 0 &&
              summary.unresolved_deadlock_count == 0 &&
              !summary.event_limit_reached &&
              !summary.time_limit_reached &&
              summary.merge_grant_stale_arbitration_count == 0 &&
              summary.stale_arbitration_event_count == 0 &&
              summary.artificial_batch_delay_seconds == 0.0 &&
              summary.merge_grant_conservation_holds &&
              summary.merge_grant_active_bijection_holds &&
              summary.merge_grant_runtime_owned_capability &&
              summary.merge_grant_exact_slot_no_future_shift &&
              summary.merge_grant_final_active_unconsumed == 0 &&
              summary.merge_grant_outstanding_request_count == 0,
          "one-shot treatment must preserve runtime hard safety gates");
}

void test_i1_source_swap() {
  auto config = frozen_config();
  EventDrivenJunctionRuntime runtime(canonical_map2().graph,
                                     config);
  runtime.initialize({
      request(61001, 46, 51, 2.0, "causal-i1-a"),
      request(61002, 46, 51, 2.0, "causal-i1-b"),
      request(61003, 3, 47, 100.0, "causal-i1-system")});
  const auto captured = capture_opportunity(
      runtime, G4IRSF14CloneBoundaryKind::kSourceArbitration,
      kG4IRSF14CausalCandidateI1);
  apply_and_finish(config, captured);
}

void test_i2_merge_swap() {
  auto config = frozen_config();
  const int goal =
      canonical_map2().graph.outgoing(17).front();
  EventDrivenJunctionRuntime runtime(canonical_map2().graph,
                                     config);
  runtime.initialize({
      request(62001, 4, goal, 2.0, "causal-i2-a"),
      request(62002, 16, goal, 2.0, "causal-i2-b"),
      request(62003, 3, 47, 100.0, "causal-i2-system")});
  const auto captured = capture_opportunity(
      runtime,
      G4IRSF14CloneBoundaryKind::kMergeGrantArbitration,
      kG4IRSF14CausalCandidateI2);
  apply_and_finish(config, captured);
}

CapturedOpportunity branch_opportunity(
    G4IRSF14CloneBoundaryKind kind,
    std::uint32_t mask,
    const EventDrivenJunctionConfig& config) {
  EventDrivenJunctionRuntime runtime(canonical_map2().graph,
                                     config);
  runtime.initialize(
      {
          request(63001, 46, 51, 2.0, "causal-branch"),
          request(63002, 3, 47, 100.0, "causal-branch-system"),
      });
  return capture_opportunity(runtime, kind, mask);
}

void test_i3_and_i4_local_actions() {
  const auto config = frozen_config();
  const auto route = branch_opportunity(
          G4IRSF14CloneBoundaryKind::kJunctionRouteArbitration,
          kG4IRSF14CausalCandidateI3, config);
  const auto hold = branch_opportunity(
      G4IRSF14CloneBoundaryKind::kHoldReleaseOpportunity,
      kG4IRSF14CausalCandidateI4, config);
  require(route.boundary.runtime_state_sha256 ==
              hold.boundary.runtime_state_sha256 &&
              route.boundary.clone_group_id ==
                  hold.boundary.clone_group_id &&
              route.boundary.boundary_sha256() !=
                  hold.boundary.boundary_sha256(),
          "I3/I4 from one checkpoint must share clone_group_id but "
          "retain distinct action boundaries");
  apply_and_finish(config, route);
  auto unsafe_reverse = make_directive(hold.boundary);
  unsafe_reverse.intervention.selected_boolean = true;
  require_invalid(
      [&] { unsafe_reverse.validate(); },
      "I4 must reject unsafe hold/release direction");
  apply_and_finish(config, hold);
}

struct I4NaturalHoldEvidence {
  double action_time = -1.0;
  double wakeup_time = -1.0;
  std::uint64_t wakeup_generation = 0;
  std::string application_reason;
};

I4NaturalHoldEvidence apply_i4_natural_hold_once(
    const EventDrivenJunctionConfig& config) {
  const auto captured = branch_opportunity(
      G4IRSF14CloneBoundaryKind::kHoldReleaseOpportunity,
      kG4IRSF14CausalCandidateI4, config);
  EventDrivenJunctionRuntime treatment(
      canonical_map2().graph, config);
  treatment.restore_state_checkpoint(captured.checkpoint);
  const auto applied =
      treatment.process_one_event_with_causal_intervention(
          make_directive(captured.boundary));
  require(
      applied.intervention_applied &&
          applied.changed_action_count == 1 &&
          applied.application_reason ==
              "APPLIED_I4_SAFE_HOLD_UNTIL_NEXT_JUNCTION_SERVICE_OPPORTUNITY",
      "I4 must certify one committed natural local hold");
  const auto snapshot = treatment.g4irsf15_local_action_snapshot(
      captured.boundary.runtime_bag_id);
  require(
      snapshot.known && snapshot.queued_at_current_node &&
          snapshot.junction_wakeup_pending &&
          snapshot.junction_wakeup_generation > 0 &&
          snapshot.junction_wakeup_time >
              captured.boundary.time,
      "I4 certificate must expose a queued bag and a live future wakeup");
  const double expected_wakeup =
      captured.boundary.time +
      std::max(service_duration(captured.boundary.node, config),
               config.dispatch_headway_seconds);
  require(
      std::abs(snapshot.junction_wakeup_time -
               expected_wakeup) <= 1.0e-12,
      "I4 must wait exactly one natural local service opportunity");
  return I4NaturalHoldEvidence{
      captured.boundary.time,
      snapshot.junction_wakeup_time,
      snapshot.junction_wakeup_generation,
      applied.application_reason};
}

void test_i4_natural_hold_is_retry_interval_independent() {
  auto short_retry = frozen_config();
  short_retry.retry_interval = 0.01;
  auto long_retry = frozen_config();
  long_retry.retry_interval = 7.0;
  const auto short_evidence =
      apply_i4_natural_hold_once(short_retry);
  const auto long_evidence =
      apply_i4_natural_hold_once(long_retry);
  require(
      std::abs(
          (short_evidence.wakeup_time -
           short_evidence.action_time) -
          (long_evidence.wakeup_time -
           long_evidence.action_time)) <= 1.0e-12 &&
          short_evidence.application_reason ==
              long_evidence.application_reason,
      "I4 committed action must not depend on the generic retry interval");
}

void test_i1_blocked_admission_is_not_action_changing() {
  auto config = frozen_config();
  const int source = 46;
  const double duration = service_duration(source, config);
  EventDrivenJunctionRuntime runtime(
      canonical_map2().graph, config);
  runtime.initialize(
      {
          request(63501, source, 51, 2.0, "i1-resource-owner"),
          request(63502, source, 51, 2.0 + duration * 0.5,
                  "i1-blocked-a"),
          request(63503, source, 51, 2.0 + duration * 0.5,
                  "i1-blocked-b"),
      });
  const auto captured = capture_opportunity(
      runtime,
      G4IRSF14CloneBoundaryKind::kSourceArbitration,
      kG4IRSF14CausalCandidateI1);
  EventDrivenJunctionRuntime treatment(
      canonical_map2().graph, config);
  treatment.restore_state_checkpoint(captured.checkpoint);
  const auto attempted =
      treatment.process_one_event_with_causal_intervention(
          make_directive(captured.boundary));
  require(
      attempted.target_opportunity_observed &&
          !attempted.intervention_applied &&
          attempted.changed_action_count == 0,
      "I1 source-order intent must not be labelled action-changing when "
      "the selected peer cannot reserve source service");
}

void test_i5_same_ready_slice_disable() {
  auto config = frozen_config();
  config.local_queue_capacity = 1;
  config.enable_pibt_lite = false;
  config.enable_fault_policy = false;
  EventRuntimeFaultWindow fault;
  fault.start = 46;
  fault.end = 35;
  fault.fault_time = 0.0;
  fault.repair_time = 8.0;
  EventDrivenJunctionRuntime runtime(canonical_map2().graph,
                                     config);
  runtime.initialize(
      {
          request(64001, 46, 51, 2.0, "causal-i5-downstream"),
          request(64002, 14, 51, 2.0, "causal-i5-destination"),
          request(64003, 11, 51, 2.0, "causal-i5-trigger"),
          request(64004, 3, 47, 100.0, "causal-i5-system"),
      },
      {fault});
  const auto captured = capture_opportunity(
      runtime, G4IRSF14CloneBoundaryKind::kPIBTReadySlice,
      kG4IRSF14CausalCandidateI5);
  require(captured.boundary.source_ready_order.empty() &&
              captured.boundary.pibt_ready_bag_ids.size() >= 2U &&
              !captured.boundary.pibt_owner_resources.empty() &&
              captured.boundary.pibt_owner_resources.size() ==
                  captured.boundary.pibt_owner_bag_ids.size() &&
              !captured.boundary.pibt_candidate_bag_ids.empty() &&
              captured.boundary
                      .pibt_candidate_required_resource_offsets
                      .size() ==
                  captured.boundary.pibt_candidate_bag_ids.size() + 1U,
          "I5 must content-address the actual recursive PIBT slice");
  apply_and_finish(config, captured);
}

void test_exhaustive_candidate_mask_soundness() {
  auto config = frozen_config();
  config.local_queue_capacity = 1;
  config.enable_pibt_lite = false;
  config.enable_fault_policy = false;
  EventRuntimeFaultWindow fault;
  fault.start = 46;
  fault.end = 35;
  fault.fault_time = 0.0;
  fault.repair_time = 8.0;
  EventDrivenJunctionRuntime runtime(canonical_map2().graph,
                                     config);
  runtime.initialize(
      {
          request(65001, 46, 51, 2.0, "mask-downstream"),
          request(65002, 14, 51, 2.0, "mask-destination"),
          request(65003, 11, 51, 2.0, "mask-trigger"),
      },
      {fault});
  bool saw_zero_mask_event = false;
  bool saw_i5 = false;
  std::uint64_t observed_i2 = 0;
  std::uint64_t observed_i5 = 0;
  for (int event = 0; event < 1024; ++event) {
    if (!runtime.peek_safe_boundary().has_value()) {
      break;
    }
    const auto mask =
        runtime.peek_causal_candidate_kind_mask();
    saw_zero_mask_event =
        saw_zero_mask_event ||
        mask == kG4IRSF14CausalCandidateNone;
    const auto probe =
        runtime.probe_one_event_for_causal_opportunities();
    for (const auto& opportunity :
         probe.observed_opportunities) {
      require((mask & mask_for(opportunity.kind)) != 0U,
              "candidate mask produced a false negative");
      saw_i5 = saw_i5 ||
               opportunity.kind ==
                   G4IRSF14CloneBoundaryKind::kPIBTReadySlice;
      observed_i2 +=
          opportunity.kind ==
                  G4IRSF14CloneBoundaryKind::kMergeGrantArbitration
              ? 1U
              : 0U;
      observed_i5 +=
          opportunity.kind ==
                  G4IRSF14CloneBoundaryKind::kPIBTReadySlice
              ? 1U
              : 0U;
    }
    if (!probe.event_processed) {
      break;
    }
  }
  require(saw_zero_mask_event && saw_i5,
          "bounded exhaustive fixture must cover zero-mask and I5 events");
  const auto& summary = runtime.current_result().summary;
  require(
      observed_i2 ==
              summary
                  .g4irsf14_i2_live_eligible_multi_request_boundary_count &&
          observed_i5 ==
              summary
                  .g4irsf14_i5_applicable_ready_slice_boundary_count &&
          summary.g4irsf14_i5_prefilter_candidate_count >=
              summary
                  .g4irsf14_i5_applicable_ready_slice_boundary_count,
      "native I2/I5 counters must equal exhaustive probe observations");
}

void test_i2_native_counter_matches_observed_boundaries() {
  auto config = frozen_config();
  const int goal =
      canonical_map2().graph.outgoing(17).front();
  EventDrivenJunctionRuntime runtime(canonical_map2().graph,
                                     config);
  runtime.initialize({
      request(65201, 4, goal, 2.0, "i2-count-a"),
      request(65202, 16, goal, 2.0, "i2-count-b")});
  std::uint64_t observed_i2 = 0;
  bool checkpoint_verified = false;
  for (int event = 0; event < 1024; ++event) {
    if (!runtime.peek_safe_boundary().has_value()) {
      break;
    }
    const auto probe =
        runtime.probe_one_event_for_causal_opportunities();
    observed_i2 += static_cast<std::uint64_t>(
        std::count_if(
            probe.observed_opportunities.begin(),
            probe.observed_opportunities.end(),
            [](const auto& opportunity) {
              return opportunity.kind ==
                     G4IRSF14CloneBoundaryKind::
                         kMergeGrantArbitration;
            }));
    if (!checkpoint_verified && observed_i2 > 0U &&
        runtime.peek_safe_boundary().has_value()) {
      const auto checkpoint =
          runtime.capture_state_checkpoint();
      EventDrivenJunctionRuntime restored(
          canonical_map2().graph, config);
      restored.restore_state_checkpoint(checkpoint);
      require(
          restored.current_result()
                  .summary
                  .g4irsf14_i2_live_eligible_multi_request_boundary_count ==
              observed_i2 &&
              restored.deterministic_state_sha256() ==
                  checkpoint.state_sha256(),
          "native causal counters must survive checkpoint restore and seal");
      checkpoint_verified = true;
    }
    if (!probe.event_processed) {
      break;
    }
  }
  require(
      observed_i2 > 0U && checkpoint_verified &&
          observed_i2 ==
              runtime.current_result()
                  .summary
                  .g4irsf14_i2_live_eligible_multi_request_boundary_count,
      "native I2 counter must equal exhaustive I2 observations");
}

void test_i5_non_applicable_slice_is_not_actionable() {
  auto config = frozen_config();
  config.local_queue_capacity = 1;
  config.enable_pibt_lite = false;
  config.enable_fault_policy = false;
  std::vector<EventRuntimeFaultWindow> faults;
  for (const int next :
       canonical_map2().graph.outgoing(46)) {
    EventRuntimeFaultWindow fault;
    fault.start = 46;
    fault.end = next;
    fault.fault_time = 0.0;
    fault.repair_time = 8.0;
    faults.push_back(fault);
  }
  EventDrivenJunctionRuntime runtime(canonical_map2().graph,
                                     config);
  runtime.initialize(
      {
          request(65501, 46, 51, 2.0,
                  "i5-negative-downstream"),
          request(65502, 14, 51, 2.0,
                  "i5-negative-destination"),
          request(65503, 11, 51, 2.0,
                  "i5-negative-trigger"),
      },
      faults);

  bool saw_i5_prefilter_candidate = false;
  bool saw_non_applicable_slice = false;
  for (int event = 0; event < 1024; ++event) {
    const auto next = runtime.peek_safe_boundary();
    if (!next.has_value() ||
        next->next_event_time >=
            8.0 - 1e-12) {
      break;
    }
    const auto mask =
        runtime.peek_causal_candidate_kind_mask();
    if ((mask & kG4IRSF14CausalCandidateI5) == 0U) {
      require(runtime.process_one_event(),
              "negative I5 fixture stopped before repair");
      continue;
    }
    saw_i5_prefilter_candidate = true;
    const auto before_not_applicable =
        runtime.current_result()
            .summary
            .bounded_local_pibt_not_applicable_count;
    const auto before_prefilter =
        runtime.current_result()
            .summary
            .g4irsf14_i5_prefilter_candidate_count;
    const auto before_applicable =
        runtime.current_result()
            .summary
            .g4irsf14_i5_applicable_ready_slice_boundary_count;
    const auto probe =
        runtime.probe_one_event_for_causal_opportunities();
    require(
        std::none_of(
            probe.observed_opportunities.begin(),
            probe.observed_opportunities.end(),
            [](const auto& opportunity) {
              return opportunity.kind ==
                     G4IRSF14CloneBoundaryKind::kPIBTReadySlice;
            }),
        "non-applicable recursive PIBT slice must not expose I5");
    require(
        runtime.current_result()
                .summary
                .g4irsf14_i5_prefilter_candidate_count ==
                before_prefilter + 1U &&
            runtime.current_result()
                    .summary
                    .g4irsf14_i5_applicable_ready_slice_boundary_count ==
                before_applicable,
        "negative I5 slice must increment only the native prefilter counter");
    saw_non_applicable_slice =
        saw_non_applicable_slice ||
        runtime.current_result()
                .summary
                .bounded_local_pibt_not_applicable_count >
            before_not_applicable;
  }
  require(
      saw_i5_prefilter_candidate && saw_non_applicable_slice,
      "negative I5 fixture must exercise a conservative prefilter "
      "false positive and reject the non-applicable exact slice");
}

void test_explicit_horizon_stop_semantics() {
  {
    auto config = frozen_config();
    EventDrivenJunctionRuntime runtime(canonical_map2().graph,
                                       config);
    runtime.initialize(
        {request(66001, 46, 51, 2.0, "h-local")});
    const auto before = runtime.causal_horizon_stop_state(
        G4IRSF14CloneHorizon::kLocal, {0}, -1, 0, 1);
    require(!before.should_stop &&
                before.stop_reason == "CONTINUE",
            "H_local must continue before its bounded event count");
    require(runtime.process_one_event(),
            "H_local fixture must process one event");
    const auto bounded = runtime.causal_horizon_stop_state(
        G4IRSF14CloneHorizon::kLocal, {0}, -1, 0, 1);
    require(bounded.should_stop &&
                bounded.horizon_complete &&
                bounded.stop_reason ==
                    "H_LOCAL_BOUNDED_EVENT_COUNT_REACHED",
            "H_local must stop at its explicit event bound");
    const auto empty_merge =
        runtime.causal_horizon_stop_state(
            G4IRSF14CloneHorizon::kLocal,
            {0}, 999999, 0, 100);
    require(empty_merge.should_stop &&
                empty_merge.horizon_complete &&
                empty_merge.stop_reason ==
                    "H_LOCAL_MERGE_QUEUE_EMPTY",
            "H_local must stop when its selected merge queue is empty");
  }
  {
    auto config = frozen_config();
    config.max_simulation_time = 0.0;
    EventDrivenJunctionRuntime runtime(canonical_map2().graph,
                                       config);
    runtime.initialize(
        {request(66002, 46, 51, 2.0, "h-failed")});
    runtime.drain();
    runtime.finalize();
    const auto failed = runtime.causal_horizon_stop_state(
        G4IRSF14CloneHorizon::kAffectedBag,
        {0}, -1, 0, 1);
    require(failed.should_stop && failed.blocked &&
                !failed.horizon_complete &&
                failed.stop_reason ==
                    "H_BAG_AFFECTED_BAG_FAILED",
            "failed/terminal bag must never satisfy H_bag completion");
  }
}

void test_g4irsf15_skeleton_probe_exact_post_state() {
  const auto config = frozen_config();
  const auto captured = branch_opportunity(
      G4IRSF14CloneBoundaryKind::kJunctionRouteArbitration,
      kG4IRSF14CausalCandidateI3, config);
  EventDrivenJunctionRuntime full(canonical_map2().graph,
                                  config);
  EventDrivenJunctionRuntime skeleton(canonical_map2().graph,
                                      config);
  full.restore_state_checkpoint(captured.checkpoint);
  skeleton.restore_state_checkpoint(captured.checkpoint);
  const auto full_step =
      full.probe_one_event_for_causal_opportunities();
  const auto skeleton_step =
      skeleton.probe_one_event_for_causal_skeletons();
  require(
      full_step.event_processed &&
          skeleton_step.event_processed &&
          skeleton_step.application_reason ==
              "SKELETON_PROBE_ONLY_NO_ACTION_CHANGED",
      "full and skeleton probes must consume one no-op event");
  std::size_t expected_skeleton_count = 0;
  for (const auto& boundary :
       full_step.observed_opportunities) {
    if (boundary.kind !=
            G4IRSF14CloneBoundaryKind::kSourceArbitration &&
        boundary.kind !=
            G4IRSF14CloneBoundaryKind::
                kJunctionRouteArbitration &&
        boundary.kind !=
            G4IRSF14CloneBoundaryKind::
                kHoldReleaseOpportunity) {
      continue;
    }
    ++expected_skeleton_count;
    const auto found = std::find_if(
        skeleton_step.observed_opportunities.begin(),
        skeleton_step.observed_opportunities.end(),
        [&](const auto& row) {
          return row.kind == boundary.kind &&
                 row.event_seq == boundary.event_seq &&
                 event_runtime_detail::same_timestamp(
                     row.time, boundary.time) &&
                 row.node == boundary.node &&
                 row.runtime_bag_id ==
                     boundary.runtime_bag_id &&
                 row.baseline_next_node ==
                     boundary.baseline_next_node &&
                 row.baseline_release ==
                     boundary.baseline_release &&
                 row.source_ready_order ==
                     boundary.source_ready_order &&
                 row.legal_next_edges ==
                     boundary.legal_next_edges;
        });
    require(
        found != skeleton_step.observed_opportunities.end(),
        "lightweight skeleton must exactly match the sealed "
        "local opportunity");
  }
  require(
      skeleton_step.observed_opportunities.size() ==
          expected_skeleton_count,
      "skeleton probe must expose exactly the I1/I3/I4 subset");
  require(
      full.deterministic_state_sha256() ==
          skeleton.deterministic_state_sha256(),
      "full and lightweight no-op probes must produce the exact "
      "same post-event runtime state and counters");
}

void test_g4irsf15_i3_zero_to_pending_certificate() {
  const auto config = frozen_config();
  EventDrivenJunctionRuntime source(canonical_map2().graph,
                                    config);
  source.initialize({
      request(66501, 6, 51, 2.0, "i3-pending"),
      request(66502, 3, 47, 100.0,
              "i3-pending-system")});
  const auto captured = capture_opportunity(
      source,
      G4IRSF14CloneBoundaryKind::kJunctionRouteArbitration,
      kG4IRSF14CausalCandidateI3);
  const auto selected = std::find_if(
      captured.boundary.legal_next_edges.begin(),
      captured.boundary.legal_next_edges.end(),
      [&](int next) {
        return next !=
                   captured.boundary.baseline_next_node &&
               canonical_map2().graph.incoming_degree(next) > 1;
      });
  require(
      selected != captured.boundary.legal_next_edges.end(),
      "I3 certificate fixture needs an alternative destination "
      "merge edge");
  auto directive = make_directive(captured.boundary);
  directive.intervention.selected_next_node = *selected;
  directive.validate();
  EventDrivenJunctionRuntime treatment(
      canonical_map2().graph, config);
  treatment.restore_state_checkpoint(captured.checkpoint);
  const auto before =
      treatment.g4irsf15_local_action_snapshot(
          captured.boundary.runtime_bag_id);
  const auto step =
      treatment.process_one_event_with_causal_intervention(
          directive);
  const auto after =
      treatment.g4irsf15_local_action_snapshot(
          captured.boundary.runtime_bag_id);
  require(
      before.pending_merge_request_id == 0U &&
          before.pending_merge_lineage == 0U &&
          after.pending_merge_request_id != 0U &&
          after.pending_merge_lineage != 0U &&
          after.pending_merge_destination == *selected &&
          step.intervention_applied &&
          step.changed_action_count == 1 &&
          step.application_reason ==
              "APPLIED_I3_MERGE_REQUEST_ENQUEUED_ONE_ACTION",
      "I3 merge-request action certificate must require a real "
      "0-to-pending commit");
  require(
      g4irsf15_i3_committed_new_pending_request(
          0U, 0U, after.pending_merge_request_id,
          after.pending_merge_lineage, true),
      "I3 0-to-pending predicate must accept the committed request");
  require(
      !g4irsf15_i3_committed_new_pending_request(
          after.pending_merge_request_id,
          after.pending_merge_lineage,
          after.pending_merge_request_id,
          after.pending_merge_lineage, true),
      "an already-pending request must never be certified as a "
      "new I3 action");
  require(
      !g4irsf15_i3_committed_new_pending_request(
          0U, 0U, after.pending_merge_request_id,
          after.pending_merge_lineage, false),
      "I3 certificate must bind the pending dispatch to the "
      "selected local action");
}

void test_g4irsf15_primary_action_is_remote_strata_independent() {
  G4IRSF15CausalOpportunitySkeleton i1;
  i1.kind = G4IRSF14CloneBoundaryKind::kSourceArbitration;
  i1.time = 17.0;
  i1.event_seq = 91;
  i1.node = 52;
  i1.runtime_bag_id = 42;
  i1.source_ready_order = {42, 19, 7};

  G4IRSF15CausalPrepopStrata quiet;
  quiet.event_time = i1.time;
  quiet.event_seq = i1.event_seq;
  quiet.node = i1.node;
  quiet.queued_bag_count = 3;

  auto remote_contention = quiet;
  remote_contention.active_merge_capability_count = 11;
  remote_contention.pending_merge_request_count = 23;
  remote_contention.active_physical_fault_edge_count = 5;
  remote_contention.queued_bag_count = 307;

  const auto quiet_projection =
      g4irsf15_project_offline_population(
          i1, quiet, 1001, false);
  const auto contended_projection =
      g4irsf15_project_offline_population(
          i1, remote_contention, 1001, false);
  require(
      quiet_projection.has_value() &&
          contended_projection.has_value(),
      "same local I1 boundary must remain actionable under remote "
      "strata changes");
  require(
      quiet_projection->population_group_sha256 !=
          contended_projection->population_group_sha256,
      "offline population group must retain remote strata for "
      "sampling coverage");
  require(
      quiet_projection
              ->population_selection_evidence_sha256 !=
          contended_projection
              ->population_selection_evidence_sha256,
      "content-addressed selection evidence may retain its offline "
      "population-group binding");
  require(
      quiet_projection->primary_local_action.peer_runtime_bag_id ==
              7 &&
          contended_projection->primary_local_action
                  .peer_runtime_bag_id ==
              7 &&
          quiet_projection->primary_local_action
                  .candidate_action_count ==
              2 &&
          contended_projection->primary_local_action
                  .candidate_action_count ==
              2,
      "remote queue/fault/merge strata must not change the local "
      "numeric-min I1 peer");

  G4IRSF15CausalOpportunitySkeleton i3;
  i3.kind =
      G4IRSF14CloneBoundaryKind::kJunctionRouteArbitration;
  i3.time = 29.0;
  i3.event_seq = 103;
  i3.node = 12;
  i3.runtime_bag_id = 88;
  i3.baseline_next_node = 3;
  i3.legal_next_edges = {9, 3, 6};
  quiet.event_time = i3.time;
  quiet.event_seq = i3.event_seq;
  quiet.node = i3.node;
  remote_contention.event_time = i3.time;
  remote_contention.event_seq = i3.event_seq;
  remote_contention.node = i3.node;

  const auto quiet_i3 =
      g4irsf15_project_offline_population(
          i3, quiet, 2002, false);
  const auto contended_i3 =
      g4irsf15_project_offline_population(
          i3, remote_contention, 2002, false);
  require(
      quiet_i3.has_value() && contended_i3.has_value() &&
          quiet_i3->population_group_sha256 !=
              contended_i3->population_group_sha256 &&
          quiet_i3->population_selection_evidence_sha256 !=
              contended_i3
                  ->population_selection_evidence_sha256 &&
          quiet_i3->primary_local_action.selected_next_node == 6 &&
          contended_i3->primary_local_action.selected_next_node ==
              6,
      "remote strata may change offline I3 grouping but never its "
      "local numeric-min alternative edge");
}

void test_g4irsf15_raw_bag_sufficient_statistics_sidecar() {
  const std::vector<EventRuntimeBagRequest> requests = {
      raw_sidecar_request(20, "raw-20-a", 5.0, 20.0),
      raw_sidecar_request(10, "raw-10-a", 4.0, 8.0),
      raw_sidecar_request(20, "raw-20-b", 6.0, 17.0),
  };
  const std::vector<double> original_entry_times = {
      0.0, 2.0, 0.0};
  std::vector<G4IRSF15CausalBagOutcome> outcomes = {
      raw_sidecar_outcome(0, requests[0], 7.0, 15.0, 2.0),
      raw_sidecar_outcome(1, requests[1], 5.0, 9.0, 1.0),
      raw_sidecar_outcome(2, requests[2], 8.0, 18.0, 2.0),
  };

  const auto sufficient =
      g4irsf15_build_raw_bag_sufficient_statistics(
          outcomes, requests, original_entry_times);
  require(
      sufficient.complete_coverage &&
          sufficient.selected_segment_count == 3 &&
          sufficient.rows.size() == 2U,
      "raw-bag sidecar must cover every runtime segment exactly once");
  const auto& task10 = sufficient.rows.at(0);
  const auto& task20 = sufficient.rows.at(1);
  require(
      task10.task_id == 10 &&
          task20.task_id == 20 &&
          task10.runtime_bag_ids == std::vector<int>{1} &&
          task20.runtime_bag_ids == std::vector<int>({0, 2}),
      "raw-bag sidecar rows must use strict ascending task_id order "
      "while preserving protected runtime-ID order");
  require(
      task10.completed_segment_count == 1 &&
          task10.complete && !task10.failed &&
          task10.deadline_miss &&
          task10.original_entry_total_seconds == 7.0 &&
          task10.java_release_total_seconds == 5.0 &&
          task10.scheduled_pre_release_wait_total_seconds == 2.0 &&
          task10.source_wait_total_seconds == 1.0 &&
          task10.network_time_total_seconds == 4.0 &&
          task10.total_system_time_total_seconds == 7.0,
      "single-segment raw-task sufficient statistics drifted");
  require(
      task20.completed_segment_count == 2 &&
          task20.complete && !task20.failed &&
          task20.deadline_miss &&
          task20.original_entry_total_seconds == 33.0 &&
          task20.java_release_total_seconds == 22.0 &&
          task20.scheduled_pre_release_wait_total_seconds == 11.0 &&
          task20.source_wait_total_seconds == 4.0 &&
          task20.network_time_total_seconds == 18.0 &&
          task20.total_system_time_total_seconds == 33.0,
      "multi-segment raw-task sufficient statistics drifted");

  int completed_segment_count = 0;
  int complete_raw_bag_count = 0;
  int failed_raw_bag_count = 0;
  int deadline_miss_raw_bag_count = 0;
  std::vector<double> original_entry_totals;
  std::vector<double> java_release_totals;
  std::vector<double> scheduled_totals;
  std::vector<double> source_wait_totals;
  std::vector<double> network_totals;
  std::vector<double> total_system_totals;
  for (const auto& row : sufficient.rows) {
    completed_segment_count += row.completed_segment_count;
    failed_raw_bag_count += row.failed ? 1 : 0;
    if (!row.complete) {
      continue;
    }
    ++complete_raw_bag_count;
    deadline_miss_raw_bag_count +=
        row.deadline_miss ? 1 : 0;
    original_entry_totals.push_back(
        row.original_entry_total_seconds);
    java_release_totals.push_back(
        row.java_release_total_seconds);
    scheduled_totals.push_back(
        row.scheduled_pre_release_wait_total_seconds);
    source_wait_totals.push_back(
        row.source_wait_total_seconds);
    network_totals.push_back(
        row.network_time_total_seconds);
    total_system_totals.push_back(
        row.total_system_time_total_seconds);
  }
  const auto mean = [](const std::vector<double>& values) {
    return std::accumulate(values.begin(), values.end(), 0.0) /
           static_cast<double>(values.size());
  };
  const auto linear_quantile = [](
      std::vector<double> values, double probability) {
    std::sort(values.begin(), values.end());
    const double position =
        probability * static_cast<double>(values.size() - 1U);
    const auto lower =
        static_cast<std::size_t>(std::floor(position));
    const auto upper =
        static_cast<std::size_t>(std::ceil(position));
    const double fraction =
        position - static_cast<double>(lower);
    return values[lower] * (1.0 - fraction) +
           values[upper] * fraction;
  };
  require(
      completed_segment_count == 3 &&
          complete_raw_bag_count == 2 &&
          failed_raw_bag_count == 0 &&
          deadline_miss_raw_bag_count == 2 &&
          mean(original_entry_totals) == 20.0 &&
          linear_quantile(original_entry_totals, 0.5) == 20.0 &&
          std::abs(
              linear_quantile(original_entry_totals, 0.95) -
              31.7) <= 1.0e-12 &&
          std::abs(
              linear_quantile(original_entry_totals, 0.99) -
              32.74) <= 1.0e-12 &&
          *std::max_element(original_entry_totals.begin(),
                            original_entry_totals.end()) == 33.0 &&
          mean(java_release_totals) == 13.5 &&
          mean(scheduled_totals) == 6.5 &&
          mean(source_wait_totals) == 2.5 &&
          mean(network_totals) == 11.0 &&
          mean(total_system_totals) == 20.0,
      "serialized raw-task rows must exactly recompute every "
      "raw_bag_cohort_metrics sufficient statistic");

  const auto is_sha256 = [](const std::string& value) {
    return value.size() == 64U &&
           std::all_of(value.begin(), value.end(), [](char ch) {
             return (ch >= '0' && ch <= '9') ||
                    (ch >= 'a' && ch <= 'f');
           });
  };
  const std::string runtime_mapping_sha256(64U, '1');
  const std::string raw_mapping_sha256(64U, '2');
  const std::string original_entry_mapping_sha256(64U, '3');
  const auto content_sha256 = sufficient.content_sha256(
      runtime_mapping_sha256, raw_mapping_sha256,
      original_entry_mapping_sha256);
  require(
      is_sha256(task10.runtime_id_mapping_sha256()) &&
          is_sha256(task10.row_sha256()) &&
          is_sha256(content_sha256) &&
          sufficient.content_sha256(
              runtime_mapping_sha256, raw_mapping_sha256,
              original_entry_mapping_sha256) == content_sha256,
      "raw-bag sidecar row/content hashes must be canonical and stable");
  auto tampered = sufficient;
  tampered.rows[0].java_release_total_seconds += 1.0;
  require(
      tampered.rows[0].runtime_id_mapping_sha256() ==
              task10.runtime_id_mapping_sha256() &&
          tampered.rows[0].row_sha256() != task10.row_sha256() &&
          tampered.content_sha256(
              runtime_mapping_sha256, raw_mapping_sha256,
              original_entry_mapping_sha256) != content_sha256,
      "raw-bag row/content hashes must bind every sufficient statistic "
      "without changing the runtime-ID mapping identity");

  auto failed_outcomes = outcomes;
  failed_outcomes[0].completed = false;
  failed_outcomes[0].failed = true;
  failed_outcomes[0].finish_time = -1.0;
  failed_outcomes[0].admitted_time = -1.0;
  failed_outcomes[0].source_wait_seconds = 0.0;
  failed_outcomes[0].status = "FAILED";
  const auto partial =
      g4irsf15_build_raw_bag_sufficient_statistics(
          failed_outcomes, requests, original_entry_times);
  require(
      partial.complete_coverage &&
          partial.rows.size() == 2U &&
          partial.rows[1].task_id == 20 &&
          !partial.rows[1].complete &&
          partial.rows[1].failed &&
          partial.rows[1].completed_segment_count == 1 &&
          partial.rows[1].original_entry_total_seconds == 18.0,
      "sidecar coverage/order must remain complete when a raw task "
      "is outcome-incomplete");

  auto misordered_outcomes = outcomes;
  misordered_outcomes[0].runtime_bag_id = 2;
  require_invalid(
      [&] {
        (void)g4irsf15_build_raw_bag_sufficient_statistics(
            misordered_outcomes, requests,
            original_entry_times);
      },
      "runtime-ID mapping drift must fail closed");
}

void test_g4irsf15_full_skeleton_census_matches_plain_drain() {
  const auto config = frozen_config();
  const std::vector<EventRuntimeBagRequest> requests = {
      request(66501, 46, 51, 2.0, "census-exact-a"),
      request(66502, 46, 51, 2.0, "census-exact-b"),
      request(66503, 3, 47, 100.0, "census-exact-system"),
  };
  EventDrivenJunctionRuntime plain(canonical_map2().graph, config);
  EventDrivenJunctionRuntime census(canonical_map2().graph, config);
  plain.initialize(requests);
  census.initialize(requests);

  plain.drain();
  plain.finalize();

  std::uint64_t probed_candidate_event_count = 0;
  while (census.peek_safe_boundary().has_value()) {
    const auto mask =
        census.peek_causal_candidate_kind_mask() &
        (kG4IRSF14CausalCandidateI1 |
         kG4IRSF14CausalCandidateI3 |
         kG4IRSF14CausalCandidateI4);
    if (mask == 0U) {
      if (!census.process_one_event()) {
        break;
      }
      continue;
    }
    const auto step =
        census.probe_one_event_for_causal_skeletons();
    require(
        step.event_processed &&
            step.application_reason ==
                "SKELETON_PROBE_ONLY_NO_ACTION_CHANGED",
        "full skeleton census must consume each candidate event "
        "without changing an action");
    ++probed_candidate_event_count;
  }
  census.finalize();

  const auto plain_hashes = plain.deterministic_replay_hashes();
  const auto census_hashes = census.deterministic_replay_hashes();
  require(
      probed_candidate_event_count > 0 &&
          census_hashes.exactly_matches(plain_hashes) &&
          census.current_result().summary.event_count ==
              plain.current_result().summary.event_count &&
          census.current_result().summary.completed_count ==
              plain.current_result().summary.completed_count &&
          census.current_result().summary.failed_count ==
              plain.current_result().summary.failed_count,
      "a complete lightweight skeleton census must have the exact "
      "terminal replay hashes and counts of an ordinary no-probe drain");
}

void test_g4irsf15_truncated_census_is_detectable() {
  const std::vector<EventRuntimeBagRequest> requests = {
      request(67001, 46, 51, 2.0, "census-cap-a"),
      request(67002, 46, 51, 2.0, "census-cap-b"),
  };
  const auto candidate_mask =
      kG4IRSF14CausalCandidateI1 |
      kG4IRSF14CausalCandidateI3 |
      kG4IRSF14CausalCandidateI4;

  auto discovery_config = frozen_config();
  EventDrivenJunctionRuntime discovery(
      canonical_map2().graph, discovery_config);
  discovery.initialize(requests);
  while ((discovery.peek_causal_candidate_kind_mask() &
          candidate_mask) == 0U) {
    require(
        discovery.process_one_event(),
        "candidate-boundary cap fixture stopped before a causal mask");
  }
  const int events_before_candidate =
      discovery.current_result().summary.event_count;
  require(
      events_before_candidate > 0 &&
          (discovery.peek_causal_candidate_kind_mask() &
           candidate_mask) != 0U,
      "event-cap regression requires a live nonzero candidate mask");

  auto capped_config = frozen_config();
  capped_config.max_events = events_before_candidate;
  EventDrivenJunctionRuntime runtime(
      canonical_map2().graph, capped_config);
  runtime.initialize(requests);
  while (runtime.current_result().summary.event_count <
         events_before_candidate) {
    require(
        runtime.process_one_event(),
        "capped census failed before the intended candidate boundary");
  }
  const auto capped_top_mask =
      runtime.peek_causal_candidate_kind_mask() &
        (kG4IRSF14CausalCandidateI1 |
         kG4IRSF14CausalCandidateI3 |
         kG4IRSF14CausalCandidateI4);
  require(
      capped_top_mask != 0U,
      "event cap must land exactly on a nonzero candidate-mask top");
  const auto skipped =
      runtime.probe_one_event_for_causal_skeletons();
  require(
      !skipped.event_processed &&
          skipped.observed_opportunities.empty() &&
          skipped.application_reason ==
              "SKELETON_PROBE_SKIPPED_RUNTIME_LIMIT" &&
          runtime.current_result().summary.event_count ==
              events_before_candidate,
      "an unprocessed candidate top must be excluded from census counts");
  runtime.finalize();
  const auto& summary = runtime.current_result().summary;
  const bool census_complete =
      !summary.event_limit_reached &&
      !summary.time_limit_reached &&
      summary.completed_count == summary.requested_count &&
      summary.failed_count == 0;
  require(
      !census_complete &&
          summary.event_limit_reached &&
          !summary.time_limit_reached &&
          (summary.completed_count != summary.requested_count ||
           summary.failed_count != 0),
      "a candidate-boundary event cap must report explicit event-limit "
      "evidence and census_complete=false");
}

}  // namespace

int main() {
  try {
    // NON_FORMAL_UNIT_INTEGRATION_FIXTURE: these constructed requests prove
    // mechanism and safety only; they are not original-task causal labels.
    test_i1_source_swap();
    test_i2_merge_swap();
    test_i3_and_i4_local_actions();
    test_i4_natural_hold_is_retry_interval_independent();
    test_i1_blocked_admission_is_not_action_changing();
    test_i5_same_ready_slice_disable();
    test_exhaustive_candidate_mask_soundness();
    test_i2_native_counter_matches_observed_boundaries();
    test_i5_non_applicable_slice_is_not_actionable();
    test_explicit_horizon_stop_semantics();
    test_g4irsf15_skeleton_probe_exact_post_state();
    test_g4irsf15_i3_zero_to_pending_certificate();
    test_g4irsf15_primary_action_is_remote_strata_independent();
    test_g4irsf15_raw_bag_sufficient_statistics_sidecar();
    test_g4irsf15_full_skeleton_census_matches_plain_drain();
    test_g4irsf15_truncated_census_is_detectable();
  } catch (const std::exception& error) {
    std::cerr << "G4IRSF14 causal intervention test failed: "
              << error.what() << '\n';
    return EXIT_FAILURE;
  }
  std::cout
      << "G4IRSF14 I1-I5 one-shot runtime tests passed "
         "(NON_FORMAL_UNIT_INTEGRATION_FIXTURE)\n";
  return EXIT_SUCCESS;
}
