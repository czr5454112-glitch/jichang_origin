#include <algorithm>
#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <limits>
#include <set>
#include <string>
#include <tuple>
#include <vector>

#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"

#ifndef CZR005_SOURCE_DIR
#error "CZR005_SOURCE_DIR must identify the repository root"
#endif

namespace {

using czr005::ics::EventDrivenJunctionConfig;
using czr005::ics::EventDrivenJunctionResult;
using czr005::ics::EventDrivenJunctionRuntime;
using czr005::ics::EventRuntimeBagRequest;
using czr005::ics::EventRuntimeFaultWindow;

struct Checks {
  int failures = 0;

  void require(bool condition, const std::string& message) {
    if (!condition) {
      ++failures;
      std::cerr << "FAIL: " << message << '\n';
    }
  }
};

const czr005::ics::Graph& canonical_graph() {
  static const auto map = czr005::ics::read_canonical_map2_json(
      std::filesystem::path(CZR005_SOURCE_DIR) / "data" / "processed" /
      "maps" / "map2.json");
  return map.graph;
}

EventDrivenJunctionConfig config_for(const std::string& mode,
                                     bool telemetry) {
  EventDrivenJunctionConfig config;
  config.event_semantics = mode;
  config.enable_opportunity_telemetry = telemetry;
  config.opportunity_trace_limit = 200000;
  config.resource_semantics = "R3_java_node_window_compatible";
  config.pressure_mode = "off";
  config.admission_mode = "off";
  config.enable_source_admission = false;
  config.enable_backpressure = false;
  config.enable_pibt_lite = false;
  config.enable_deadlock_escape = true;
  config.retry_interval = 0.05;
  config.minimum_service_seconds = 0.001;
  config.dispatch_headway_seconds = 0.001;
  config.max_decisions_per_bag = 1000;
  config.max_events = 2000000;
  config.max_simulation_time = 10000.0;
  config.trace_limit = 200000;
  return config;
}

std::vector<EventRuntimeBagRequest> e0_motif() {
  return {
      {"e0-a", 1, 0.0, 100.0, 3, 47, "source-3"},
      {"e0-b", 2, 0.1, 100.0, 6, 47, "source-6"},
  };
}

std::vector<EventRuntimeBagRequest> source_batch_motif() {
  return {
      {"batch-a", 11, 0.0, 100.0, 6, 47, "source-6"},
      {"batch-b", 12, 0.0, 100.0, 6, 47, "source-6"},
      {"batch-c", 13, 0.5, 100.0, 6, 47, "source-6"},
  };
}

auto bag_signature(const EventDrivenJunctionResult& result) {
  std::vector<std::tuple<std::string,
                         int,
                         int,
                         int,
                         double,
                         double,
                         double,
                         double,
                         int,
                         int,
                         bool,
                         std::string,
                         std::vector<int>>>
      rows;
  for (const auto& bag : result.bags) {
    rows.emplace_back(bag.segment_id,
                      bag.task_id,
                      bag.runtime_bag_id,
                      bag.final_node,
                      bag.admitted_time,
                      bag.finish_time,
                      bag.source_queue_delay,
                      bag.total_local_wait,
                      bag.decision_count,
                      bag.retry_count,
                      bag.completed,
                      bag.failure_reason,
                      bag.short_history);
  }
  return rows;
}

auto event_signature(const EventDrivenJunctionResult& result) {
  std::vector<std::tuple<std::uint64_t,
                         std::string,
                         double,
                         int,
                         int,
                         int,
                         int,
                         std::string,
                         int>>
      rows;
  for (const auto& event : result.events) {
    rows.emplace_back(event.seq,
                      event.event,
                      event.time,
                      event.task_id,
                      event.runtime_bag_id,
                      event.node,
                      event.to_node,
                      event.reason,
                      event.selected_edge_count);
  }
  return rows;
}

auto decision_signature(const EventDrivenJunctionResult& result) {
  std::vector<std::tuple<std::uint64_t,
                         std::uint64_t,
                         double,
                         int,
                         int,
                         int,
                         std::string,
                         std::string>>
      rows;
  for (const auto& decision : result.decisions) {
    rows.emplace_back(decision.decision_id,
                      decision.arrive_event_seq,
                      decision.event_time,
                      decision.runtime_bag_id,
                      decision.current_node,
                      decision.selected_next,
                      decision.decision_source,
                      decision.rule_reason);
  }
  return rows;
}

void require_hard_invariants(Checks& checks,
                             const EventDrivenJunctionResult& result,
                             int completed) {
  checks.require(result.summary.completed_count == completed &&
                     result.summary.failed_count == 0,
                 "microphase motif must complete every real-map bag");
  checks.require(result.summary.reservation_conflicts == 0,
                 "microphase mode must retain conflict-free reservations");
  checks.require(
      result.summary.physical_fault_edge_entry_violation_count == 0,
      "microphase mode must retain the physical edge-entry interlock");
  checks.require(result.summary.runtime_full_astar_calls == 0 &&
                     result.summary.global_reservation_scan_count == 0 &&
                     result.summary.microphase_runtime_global_scan_count == 0,
                 "microphase arbitration must not scan globally or call A*");
  checks.require(result.summary.two_step_reservation_count == 0 &&
                     result.summary.max_edges_selected_per_bag_per_decision <= 1,
                 "microphase mode must retain depth-one, one-edge decisions");
  checks.require(result.summary.artificial_batch_delay_seconds == 0.0,
                 "exact-timestamp batching must add no simulation delay");
  checks.require(!result.summary.event_limit_reached &&
                      !result.summary.time_limit_reached,
                  "microphase motif must not terminate at a safety limit");
  checks.require(result.summary.stale_arbitration_event_count == 0,
                 "no stale arbitration may execute");
  if (result.summary.opportunity_telemetry_enabled) {
    checks.require(
        result.summary.merge_visibility_total_count ==
            result.summary.decision_count,
        "each committed decision must publish exactly one merge visibility "
        "row");
    checks.require(
        result.summary.arbitration_batch_total_count ==
            result.summary.source_opportunity_total_count +
                result.summary.junction_opportunity_total_count,
        "arbitration batch totals must equal source plus junction "
        "opportunities");
    checks.require(
        result.summary.event_seq_audit_total_count ==
            result.summary.source_opportunity_total_count +
                result.summary.junction_opportunity_total_count +
                result.summary.merge_visibility_total_count,
        "event-seq audit totals must cover every arbitration and merge "
        "opportunity");
    checks.require(
        result.summary.opportunity_event_queue_inspection_count ==
            result.summary.event_seq_audit_total_count,
        "each event-seq audit row must correspond to one queue inspection");
  }
}

void test_e0_exact_compatibility(Checks& checks) {
  auto implicit_config = config_for("E0_immediate_dispatch_f2", false);
  EventDrivenJunctionRuntime implicit_runtime(canonical_graph(),
                                              implicit_config);
  const auto implicit = implicit_runtime.run(e0_motif());

  auto explicit_config = implicit_config;
  explicit_config.event_semantics = "E0";
  EventDrivenJunctionRuntime explicit_runtime(canonical_graph(),
                                              explicit_config);
  const auto explicit_result = explicit_runtime.run(e0_motif());

  checks.require(bag_signature(implicit) ==
                     bag_signature(explicit_result),
                 "explicit E0 must preserve every deterministic bag field");
  checks.require(event_signature(implicit) ==
                     event_signature(explicit_result),
                 "explicit E0 must preserve the complete event trace");
  checks.require(decision_signature(implicit) ==
                     decision_signature(explicit_result),
                 "explicit E0 must preserve decision ids, seqs, and actions");
  checks.require(
      implicit.summary.cpp_internal_accounted_bytes ==
          explicit_result.summary.cpp_internal_accounted_bytes,
      "explicit E0 must preserve deterministic internal byte accounting");
  checks.require(
      implicit.source_admission_opportunities.empty() &&
          implicit.junction_arbitration_opportunities.empty() &&
          implicit.merge_request_visibility.empty() &&
          implicit.event_seq_ordering_audit.empty() &&
          implicit.arbitration_batch_cardinality.empty(),
      "E0 telemetry-off must allocate no G4IRSF14 result rows");
  checks.require(implicit.summary.source_arbitration_event_count == 0 &&
                     implicit.summary.junction_arbitration_event_count == 0,
                 "E0 must schedule no new arbitration event type");
  checks.require(
      implicit.summary.bounded_local_pibt_claim_boundary.find(
          "transaction_deltas_O_selected_actions_no_queue_or_calendar_copy") !=
              std::string::npos &&
          implicit.summary.bounded_local_pibt_claim_boundary.find(
              "transaction_state_bounded_by_selected_bags_nodes_and_corridors") ==
              std::string::npos,
      "E0 must retain the frozen differential-rollback claim boundary");
}

void test_mode_isolation_and_source_batch(Checks& checks) {
  for (const auto& mode : {"E1", "E2", "E3"}) {
    EventDrivenJunctionRuntime runtime(canonical_graph(),
                                       config_for(mode, true));
    const auto result = runtime.run(source_batch_motif());
    require_hard_invariants(checks, result, 3);
    checks.require(
        result.summary.bounded_local_pibt_claim_boundary.find(
            "transaction_state_bounded_by_selected_bags_nodes_and_corridors") !=
            std::string::npos,
        std::string(mode) +
            " must report the full bounded local snapshot claim boundary");
    const bool source_expected =
        std::string(mode) == "E1" || std::string(mode) == "E3";
    const bool junction_expected =
        std::string(mode) == "E2" || std::string(mode) == "E3";
    checks.require(
        (result.summary.source_arbitration_event_count > 0) ==
            source_expected,
        std::string(mode) +
            " must isolate source arbitration exactly");
    checks.require(
        (result.summary.junction_arbitration_event_count > 0) ==
            junction_expected,
        std::string(mode) +
            " must isolate junction arbitration exactly");
    checks.require(
        result.summary.opportunity_event_queue_inspection_count > 0,
        std::string(mode) +
            " telemetry must expose passive event-queue audit reads");
  }

  EventDrivenJunctionRuntime runtime(canonical_graph(),
                                     config_for("E1", true));
  const auto result = runtime.run(source_batch_motif());
  const auto initial = std::find_if(
      result.source_admission_opportunities.begin(),
      result.source_admission_opportunities.end(),
      [](const auto& row) {
        return row.source_node == 6 && row.event_time == 0.0;
      });
  checks.require(
      initial != result.source_admission_opportunities.end() &&
          initial->same_timestamp_release_batch_size == 2 &&
          initial->ready_set_size == 2 &&
          initial->priority_comparison_count == 1 &&
          initial->batched_arbitration,
      "E1 must expose both exact-time source releases to one arbitration");
  checks.require(
      initial != result.source_admission_opportunities.end() &&
          initial->queue_length_before_enqueue == 0 &&
          initial->queue_length_after_enqueue == 2 &&
          initial->queue_length_after_arbitration == 1,
      "source opportunity telemetry must retain before/enqueue/after cardinality");
  checks.require(
      initial != result.source_admission_opportunities.end() &&
          initial->same_time_pending_shared_merge_releases == 0,
      "same-node releases must not be mislabeled as shared-merge "
      "competitors");
  checks.require(result.bags.front().admitted_time == 0.0,
                 "E1 batching must not advance simulation time");
  checks.require(
      result.summary.stale_arbitration_event_count == 0 &&
          result.summary
                  .superseded_arbitration_event_rejected_count >= 1,
      "an earlier exact-time release must reject the superseded wakeup "
      "before arbitration execution");
  checks.require(
      result.summary.duplicate_same_time_arbitration_prevented_count >= 1,
      "two same-time releases must coalesce to one node/time arbitration");

  std::set<std::tuple<std::string, int, std::uint64_t>> keys;
  bool unique = true;
  for (const auto& row : result.arbitration_batch_cardinality) {
    unique = unique &&
             keys.emplace(row.boundary,
                          row.node,
                          row.timestamp_bits)
                 .second;
  }
  checks.require(unique,
                 "generation-stamped worklists must publish at most one valid arbitration per node/time");
}

void test_e0_opportunity_audit_observes_unseen_competitor(
    Checks& checks) {
  auto config = config_for("E0", true);
  EventDrivenJunctionRuntime runtime(canonical_graph(), config);
  const auto result = runtime.run({
      {"audit-a", 21, 0.0, 100.0, 6, 47, "source-6"},
      {"audit-b", 22, 0.0, 100.0, 6, 47, "source-6"},
  });
  require_hard_invariants(checks, result, 2);
  const auto first = std::find_if(
      result.source_admission_opportunities.begin(),
      result.source_admission_opportunities.end(),
      [](const auto& row) {
        return row.source_node == 6 && row.event_time == 0.0 &&
               row.same_time_pending_source_releases > 0;
      });
  checks.require(
      first != result.source_admission_opportunities.end() &&
          !first->batched_arbitration &&
          first->ready_set_size == 1,
      "E0 audit must expose the later same-time release without changing policy");
  checks.require(
      std::any_of(result.event_seq_ordering_audit.begin(),
                  result.event_seq_ordering_audit.end(),
                  [](const auto& row) {
                    return row.boundary == "source_admission" &&
                           row.seq_determined_order;
                  }),
      "event-seq audit must label an unseen same-time admission opportunity");
}

void test_destination_visibility_includes_pending_source_dispatch(
    Checks& checks) {
  EventDrivenJunctionRuntime runtime(canonical_graph(),
                                     config_for("E0", true));
  const auto result = runtime.run({
      {"merge-source-6", 23, 0.0, 100.0, 6, 11, "source-6"},
      {"merge-source-7", 24, 0.0, 100.0, 7, 11, "source-7"},
  });
  require_hard_invariants(checks, result, 2);
  checks.require(
      std::any_of(
          result.merge_request_visibility.begin(),
          result.merge_request_visibility.end(),
          [](const auto& row) {
            return row.upstream_node == 6 &&
                   row.destination_node == 8 &&
                   row.later_same_time_competitor_exists &&
                   row.later_same_time_competitor_count >= 1;
          }),
      "destination visibility must include a pending same-time source "
      "dispatch sharing the outgoing edge");
  checks.require(
      std::any_of(
          result.source_admission_opportunities.begin(),
          result.source_admission_opportunities.end(),
          [](const auto& row) {
            return row.source_node == 6 &&
                   row.event_time == 0.0 &&
                   row.same_time_pending_shared_merge_releases >= 1;
          }),
      "source opportunity visibility must recognize a cross-source "
      "same-time shared merge");
}

void test_fault_and_generated_event_microphases(Checks& checks) {
  auto config = config_for("E3", true);
  EventDrivenJunctionRuntime runtime(canonical_graph(), config);
  const auto result = runtime.run(
      {{"fault-repair-same-time", 31, 0.0, 100.0, 3, 47,
        "source-3"}},
      {EventRuntimeFaultWindow{3, 16, 0.0, 0.0, 0.0, false}});
  require_hard_invariants(checks, result, 1);
  const auto source = std::find_if(
      result.source_admission_opportunities.begin(),
      result.source_admission_opportunities.end(),
      [](const auto& row) {
        return row.source_node == 3 && row.event_time == 0.0;
      });
  std::uint64_t latest_physical_seq = 0;
  int physical_changes = 0;
  for (const auto& row : result.fault_events) {
    if (row.time == 0.0 && row.phase == "physical_state_change") {
      latest_physical_seq = std::max(latest_physical_seq, row.seq);
      ++physical_changes;
    }
  }
  checks.require(
      source != result.source_admission_opportunities.end() &&
          physical_changes == 2 &&
          latest_physical_seq < source->event_seq,
      "same-time FAULT and REPAIR must both precede source arbitration");
  std::size_t last_physical =
      std::numeric_limits<std::size_t>::max();
  std::size_t release =
      std::numeric_limits<std::size_t>::max();
  std::size_t first_local_delivery =
      std::numeric_limits<std::size_t>::max();
  std::size_t arbitration =
      std::numeric_limits<std::size_t>::max();
  for (std::size_t index = 0;
       index < result.events.size();
       ++index) {
    const auto& row = result.events[index];
    if (row.time != 0.0) {
      continue;
    }
    if (row.reason == "physical_state_change") {
      last_physical = index;
    } else if (row.reason == "source_release_enqueue") {
      release = index;
    } else if (row.reason == "local_message_delivery" &&
               first_local_delivery ==
                   std::numeric_limits<std::size_t>::max()) {
      first_local_delivery = index;
    } else if (row.event == "SOURCE_ARBITRATION" &&
               arbitration ==
                   std::numeric_limits<std::size_t>::max()) {
      arbitration = index;
    }
  }
  checks.require(
      last_physical !=
              std::numeric_limits<std::size_t>::max() &&
          release !=
              std::numeric_limits<std::size_t>::max() &&
          first_local_delivery !=
              std::numeric_limits<std::size_t>::max() &&
          arbitration !=
              std::numeric_limits<std::size_t>::max() &&
          last_physical < release &&
          release < first_local_delivery &&
          first_local_delivery < arbitration,
      "E3 zero-delay notifications must execute as local-delivery events "
      "between enqueue and arbitration");
  checks.require(
      result.summary.fault_generation_commit_recheck_count > 0,
      "selected-edge commit must recheck the physical fault generation");

  bool generated_same_time_arrival = false;
  for (const auto& service : result.events) {
    if (service.event != "JUNCTION_SERVICE_COMPLETE") {
      continue;
    }
    generated_same_time_arrival =
        generated_same_time_arrival ||
        std::any_of(result.events.begin(),
                    result.events.end(),
                    [&](const auto& arrival) {
                      return arrival.event == "ARRIVE_JUNCTION" &&
                             arrival.runtime_bag_id ==
                                 service.runtime_bag_id &&
                             arrival.time == service.time;
                    });
  }
  checks.require(
      generated_same_time_arrival,
      "a generated same-time ARRIVE event must remain in the exact timestamp microphase");
}

void test_generated_events_respect_the_active_phase_floor(
    Checks& checks) {
  EventDrivenJunctionRuntime runtime(canonical_graph(),
                                     config_for("E3", true));
  const auto result = runtime.run({
      {"phase-floor-6", 41, 0.0, 100.0, 6, 11, "source-6"},
      {"phase-floor-7", 42, 0.0, 100.0, 7, 11, "source-7"},
  });
  require_hard_invariants(checks, result, 2);
  std::set<int> original_arbitration_nodes;
  std::size_t last_original_arbitration = 0;
  std::size_t first_generated_low_phase =
      std::numeric_limits<std::size_t>::max();
  for (std::size_t index = 0;
       index < result.events.size();
       ++index) {
    const auto& row = result.events[index];
    if (row.time != 0.0) {
      continue;
    }
    if (row.event == "SOURCE_ARBITRATION" &&
        (row.node == 6 || row.node == 7)) {
      original_arbitration_nodes.insert(row.node);
      last_original_arbitration =
          std::max(last_original_arbitration, index);
    }
    if ((row.event == "LOCAL_QUEUE_UPDATE" &&
         row.reason == "source_dequeue") ||
        (row.event == "CONGESTION_BEACON_UPDATE" &&
         row.reason ==
             "source_service_reservation_snapshot")) {
      first_generated_low_phase =
          std::min(first_generated_low_phase, index);
    }
  }
  checks.require(
      original_arbitration_nodes ==
              std::set<int>({6, 7}) &&
          first_generated_low_phase !=
              std::numeric_limits<std::size_t>::max() &&
          last_original_arbitration <
              first_generated_low_phase,
      "same-time phase-4 work from two nodes must complete before "
      "phase-3 events generated by either arbitration");
  checks.require(
      std::any_of(
          result.source_admission_opportunities.begin(),
          result.source_admission_opportunities.end(),
          [](const auto& row) {
            return row.source_node == 6 &&
                   row.event_time == 0.0 &&
                   row.same_time_pending_shared_merge_releases >= 1;
          }),
      "a valid pending cross-source SourceArbitration must count as a "
      "shared-merge opportunity");
}

void test_p2_commit_publishes_transactional_visibility(
    Checks& checks) {
  auto config = config_for("E3", true);
  config.pibt_mode = "P2";
  config.pibt_max_ready_bags = 8;
  config.pibt_max_local_resources = 32;
  config.pibt_max_candidates_per_bag = 8;
  config.local_queue_capacity = 1;
  config.retry_interval = 0.1;
  EventDrivenJunctionRuntime runtime(canonical_graph(), config);
  const auto result = runtime.run({
      // Real map2 nodes 6 and 8 both have one-second service.  Request
      // ordering gives node 6 the earlier phase-5 arbitration while all
      // phase-2 arrivals still complete first; node 8 is therefore occupied
      // by the owner when the trigger requests 6 -> 8.
      {"p2-trigger", 52, 0.0, 50.0, 6, 11, "trigger"},
      {"p2-owner", 51, 0.0, 100.0, 8, 11, "owner"},
  });
  require_hard_invariants(checks, result, 2);
  checks.require(
      result.summary.bounded_local_pibt_commit_count > 0 &&
          result.summary
                  .bounded_local_pibt_committed_action_count >= 2,
      "P2 telemetry motif must exercise a multi-action atomic commit");
  checks.require(
      std::any_of(
          result.merge_request_visibility.begin(),
          result.merge_request_visibility.end(),
          [](const auto& row) {
            return row.requesting_task_id == 51 &&
                   row.upstream_node == 8 &&
                   row.destination_node == 11;
          }) &&
          std::any_of(
              result.merge_request_visibility.begin(),
              result.merge_request_visibility.end(),
              [](const auto& row) {
                return row.requesting_task_id == 52 &&
                       row.upstream_node == 6 &&
                       row.destination_node == 8;
              }),
      "each action in a successful P2 batch must publish its staged merge "
      "visibility");
  checks.require(
      result.summary.stale_arbitration_event_count == 0 &&
          result.summary
                  .superseded_arbitration_event_rejected_count > 0,
      "cross-node P2 dequeue must supersede the old owner wakeup without "
      "executing stale arbitration");
}

void test_p2_post_stage_failure_rolls_back_complete_logical_state(
    Checks& checks) {
  auto config = config_for("E3", true);
  config.pibt_mode = "P2";
  config.pibt_max_ready_bags = 8;
  config.pibt_max_local_resources = 32;
  config.pibt_max_candidates_per_bag = 8;
  config.local_queue_capacity = 1;
  config.retry_interval = 0.1;
  config.test_pibt_logical_failure_after_followup_scheduling =
      true;
  config.test_verify_pibt_rollback_logical_state = true;
  EventDrivenJunctionRuntime runtime(canonical_graph(), config);
  const auto result = runtime.run({
      {"rollback-trigger", 62, 0.0, 50.0, 6, 11, "trigger"},
      {"rollback-owner", 61, 0.0, 100.0, 8, 11, "owner"},
  });
  require_hard_invariants(checks, result, 2);
  checks.require(
      result.summary.bounded_local_pibt_rollback_count >= 1 &&
          result.summary.bounded_local_pibt_commit_rejection_count >= 1,
      "the test-only post-stage logical failure must traverse the complete "
      "PIBT rollback path");
  checks.require(
      result.summary.merge_visibility_stored_count ==
              result.merge_request_visibility.size() &&
          result.summary.event_seq_audit_stored_count ==
              result.event_seq_ordering_audit.size(),
      "rolled-back P2 rows must not leak into stored telemetry");
  checks.require(
      result.summary.merge_visibility_total_count ==
              result.summary.decision_count &&
          result.summary.event_seq_audit_total_count ==
              result.summary.source_opportunity_total_count +
                  result.summary.junction_opportunity_total_count +
                  result.summary.merge_visibility_total_count,
      "rolled-back P2 rows must not leak into telemetry totals");
  checks.require(
      result.summary.stale_arbitration_event_count == 0,
      "restored local wakeup state must leave no stale arbitration");
}

void test_e0_differential_rollback_restores_multi_action_multigoal_transaction(
    Checks& checks) {
  auto config = config_for("E0", true);
  config.pibt_mode = "P2";
  config.pibt_max_ready_bags = 16;
  config.pibt_max_local_resources = 64;
  config.pibt_max_candidates_per_bag = 8;
  config.local_queue_capacity = 1;
  config.retry_interval = 0.1;
  config.test_pibt_logical_failure_after_followup_scheduling =
      true;
  config.test_verify_pibt_rollback_logical_state = true;

  std::vector<EventRuntimeBagRequest> requests;
  requests.reserve(9);
  for (int index = 0; index < 8; ++index) {
    requests.push_back(
        {"e0-long-owner-" + std::to_string(index),
         100 + index,
         0.0,
         50.0 + static_cast<double>(index),
         8,
         index % 2 == 0 ? 47 : 11,
         "long-multigoal-owner"});
  }
  requests.push_back(
      {"e0-long-trigger",
       200,
       0.55,
       100.0,
       6,
       11,
       "long-multigoal-trigger"});

  EventDrivenJunctionRuntime runtime(canonical_graph(), config);
  const auto result = runtime.run(
      requests,
      {EventRuntimeFaultWindow{
          8, 11, 0.0, 1.55, 0.0, false}});
  require_hard_invariants(
      checks, result, static_cast<int>(requests.size()));
  checks.require(
      result.summary.bounded_local_pibt_rollback_count >= 1 &&
          result.summary.bounded_local_pibt_commit_rejection_count >= 1,
      "E0 multi-goal motif must traverse the differential post-followup "
      "rollback path");
  checks.require(
      result.summary.bounded_local_pibt_max_transaction_action_deltas >= 2,
      "E0 multi-goal motif must roll back a real multi-action transaction");
  checks.require(
      std::any_of(
          result.decisions.begin(),
          result.decisions.end(),
          [](const auto& row) {
            return row.task_id == 100 &&
                   row.current_node == 8 &&
                   row.selected_next == 11;
          }) &&
          std::any_of(
              result.decisions.begin(),
              result.decisions.end(),
              [](const auto& row) {
                return row.task_id == 200 &&
                       row.current_node == 6 &&
                       row.selected_next == 8;
              }),
      "the committed retry must move the goal-47 owner and goal-11 trigger "
      "as the real two-action transaction");
  checks.require(
      result.summary.bounded_local_pibt_claim_boundary.find(
          "transaction_deltas_O_selected_actions_no_queue_or_calendar_copy") !=
          std::string::npos,
      "E0 multi-action rollback must expose the differential transaction "
      "boundary");
  checks.require(
      result.summary.stale_arbitration_event_count == 0,
      "E0 differential rollback must preserve wakeup generations and event "
      "sequence state");
}

void test_raw_event_queue_orders_arrivals_before_arbitration(
    Checks& checks) {
  using czr005::ics::JunctionEventType;
  using czr005::ics::event_runtime_detail::RuntimeEvent;
  using czr005::ics::event_runtime_detail::RuntimeEventQueue;

  RuntimeEvent first;
  first.type = JunctionEventType::kArriveJunction;
  first.time = 4.8;
  first.seq = 2;
  first.node = 8;
  first.microphase_priority = 2;
  RuntimeEvent second = first;
  second.seq = 1;
  RuntimeEvent arbitration = first;
  arbitration.type = JunctionEventType::kJunctionArbitration;
  arbitration.seq = 3;
  arbitration.microphase_priority = 5;

  RuntimeEventQueue queue;
  queue.push(arbitration);
  queue.push(first);
  queue.push(second);
  checks.require(
      queue.top().type == JunctionEventType::kArriveJunction &&
          queue.top().seq == 1,
      "same-time arrival enqueue must precede arbitration and remain seq deterministic");
  queue.pop();
  checks.require(
      queue.top().type == JunctionEventType::kArriveJunction,
      "all same-time arrivals must enqueue before the local arbitration event");
  queue.pop();
  checks.require(
      queue.top().type ==
          JunctionEventType::kJunctionArbitration,
      "junction arbitration must run after the complete exact-time arrival batch");
}

}  // namespace

int main() {
  // Keep all G4IRSF14 scheduler and transactional regression gates in one
  // deterministic native executable over canonical map2.
  Checks checks;
  try {
    test_e0_exact_compatibility(checks);
    test_mode_isolation_and_source_batch(checks);
    test_e0_opportunity_audit_observes_unseen_competitor(checks);
    test_destination_visibility_includes_pending_source_dispatch(checks);
    test_fault_and_generated_event_microphases(checks);
    test_generated_events_respect_the_active_phase_floor(checks);
    test_p2_commit_publishes_transactional_visibility(checks);
    test_p2_post_stage_failure_rolls_back_complete_logical_state(
        checks);
    test_e0_differential_rollback_restores_multi_action_multigoal_transaction(
        checks);
    test_raw_event_queue_orders_arrivals_before_arbitration(checks);
  } catch (const std::exception& error) {
    ++checks.failures;
    std::cerr << "FAIL: G4IRSF14 microphase exception: "
              << error.what() << '\n';
  }
  return checks.failures == 0 ? 0 : 1;
}
