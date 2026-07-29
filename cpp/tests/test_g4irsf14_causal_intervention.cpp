#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
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

}  // namespace

int main() {
  try {
    // NON_FORMAL_UNIT_INTEGRATION_FIXTURE: these constructed requests prove
    // mechanism and safety only; they are not original-task causal labels.
    test_i1_source_swap();
    test_i2_merge_swap();
    test_i3_and_i4_local_actions();
    test_i5_same_ready_slice_disable();
    test_exhaustive_candidate_mask_soundness();
    test_i2_native_counter_matches_observed_boundaries();
    test_i5_non_applicable_slice_is_not_actionable();
    test_explicit_horizon_stop_semantics();
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
