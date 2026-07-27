#include <array>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
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
using czr005::ics::Graph;

struct Checks {
  int failures = 0;

  void require(bool condition, const std::string& message) {
    if (!condition) {
      ++failures;
      std::cerr << "FAIL: " << message << '\n';
    }
  }
};

const Graph& canonical_graph() {
  static const auto fixture = [] {
    const auto path = std::filesystem::path(CZR005_SOURCE_DIR) /
                      "data" / "processed" / "maps" / "map2.json";
    return czr005::ics::read_canonical_map2_json(path);
  }();
  return fixture.graph;
}

std::vector<EventRuntimeBagRequest> inheritance_motif() {
  // map2 contains the real adjacent chain 6 -> 8 -> 11.  The owner waits at
  // node 8 for the physical 8 -> 11 repair.  At t=1.55 the higher-priority
  // trigger becomes ready at node 6, so the finite-capacity node-8 queue can
  // accept it only if the owner moves to node 11 in the same local batch.
  return {
      EventRuntimeBagRequest{"owner", 1, 0.0, 100.0, 8, 11, "canonical-map2"},
      EventRuntimeBagRequest{"trigger", 2, 0.55, 50.0, 6, 11, "canonical-map2"},
  };
}

std::vector<EventRuntimeFaultWindow> inheritance_fault() {
  return {EventRuntimeFaultWindow{8, 11, 0.0, 1.55, 0.0, false}};
}

EventDrivenJunctionConfig pibt_config(const std::string& mode) {
  EventDrivenJunctionConfig config;
  config.pibt_mode = mode;
  config.pibt_max_ready_bags = 8;
  config.pibt_max_local_resources = 32;
  config.pibt_max_candidates_per_bag = 8;
  config.local_queue_capacity = 1;
  config.retry_interval = 0.1;
  config.minimum_service_seconds = 0.001;
  config.dispatch_headway_seconds = 0.001;
  config.max_decisions_per_bag = 1000;
  config.max_events = 100000;
  config.max_simulation_time = 100.0;
  config.trace_limit = 1000;
  config.enable_source_admission = false;
  config.enable_backpressure = false;
  config.enable_pibt_lite = false;
  return config;
}

EventDrivenJunctionResult run_motif(EventDrivenJunctionConfig config) {
  return EventDrivenJunctionRuntime(canonical_graph(), std::move(config))
      .run(inheritance_motif(), inheritance_fault());
}

void require_safe_boundary(
    Checks& checks,
    const EventDrivenJunctionResult& result,
    const std::string& label,
    int expected_completed_count = 2);

void test_root_only_safe_alternative_is_not_mislabeled_as_pibt(
    Checks& checks) {
  // The owner fills preferred node 12 but cannot leave while 12->13 is
  // physically faulted.  The trigger at node 6 has an already-materialized
  // safe alternative 6->8.  Moving only the trigger is not true PIBT because
  // no blocker moves, but discarding that local alternative creates a retry
  // storm at original scale.
  auto config = pibt_config("P2");
  const auto result =
      EventDrivenJunctionRuntime(canonical_graph(), std::move(config))
          .run(
              {
                  EventRuntimeBagRequest{
                      "blocked-owner",
                      11,
                      0.0,
                      100.0,
                      12,
                      47,
                      "canonical-map2"},
                  EventRuntimeBagRequest{
                      "safe-alternative-trigger",
                      12,
                      0.55,
                      100.0,
                      6,
                      47,
                      "canonical-map2"},
              },
              {EventRuntimeFaultWindow{
                  12, 13, 0.0, 10.0, 0.0, false}});
  require_safe_boundary(checks, result, "P2 same-bag safe fallback");
  checks.require(
      result.summary.bounded_local_pibt_prepare_rejection_count > 0 &&
          result.summary.bounded_local_pibt_same_bag_fallback_count > 0,
      "root-only proposal must remain a rejected PIBT batch but commit via "
      "the separately counted one-bag fallback");
  checks.require(
      result.summary.pibt_lite_handoff_count == 0 &&
          result.summary.same_bag_alternative_edge_scan_handoff_count == 0,
      "bounded P2 fallback must not masquerade as legacy pibt-lite");
  checks.require(
      result.summary.bounded_local_pibt_commit_count == 0 &&
          result.summary.bounded_local_pibt_committed_batch_count == 0 &&
          result.summary.bounded_local_pibt_committed_action_count == 0 &&
          result.summary.max_actions_committed_per_pibt_batch == 0 &&
          result.summary.bounded_local_pibt_inherited_action_count == 0 &&
          result.summary.bounded_local_pibt_handoff_count == 0,
      "root-only fallback must not increment any true PIBT commit or "
      "inheritance counter");
  bool saw_fallback = false;
  for (const auto& decision : result.decisions) {
    saw_fallback =
        saw_fallback ||
        (decision.task_id == 12 && decision.current_node == 6 &&
         decision.selected_next == 8 &&
         decision.fallback_selected_next == 8 &&
         decision.decision_source ==
             "bounded_local_pibt_same_bag_safe_fallback");
  }
  checks.require(
      saw_fallback,
      "decision audit must name the bounded one-bag fallback explicitly");
}

void test_same_bag_fallback_revalidates_physical_fault_shield(
    Checks& checks) {
  auto config = pibt_config("P2");
  const auto result =
      EventDrivenJunctionRuntime(canonical_graph(), std::move(config))
          .run(
              {
                  EventRuntimeBagRequest{
                      "blocked-owner",
                      11,
                      0.0,
                      100.0,
                      12,
                      47,
                      "canonical-map2"},
                  EventRuntimeBagRequest{
                      "faulted-alternative-trigger",
                      12,
                      0.55,
                      100.0,
                      6,
                      47,
                      "canonical-map2"},
              },
              {
                  EventRuntimeFaultWindow{
                      12, 13, 0.0, 10.0, 0.0, false},
                  EventRuntimeFaultWindow{
                      6, 8, 0.0, 10.0, 0.0, false},
              });
  require_safe_boundary(
      checks, result, "P2 physically blocked same-bag fallback");
  bool selected_faulted_fallback = false;
  for (const auto& decision : result.decisions) {
    selected_faulted_fallback =
        selected_faulted_fallback ||
        (decision.task_id == 12 && decision.current_node == 6 &&
         decision.event_time < 10.0 &&
         decision.fallback_selected_next == 8);
  }
  checks.require(
      !selected_faulted_fallback &&
          result.summary.physical_fault_edge_entry_violation_count == 0,
      "same-bag fallback must revalidate and reject a physically faulted "
      "alternative edge");
}

void test_higher_priority_blocker_owner_move_is_a_real_atomic_batch(
    Checks& checks) {
  // The owner has higher priority than the trigger, so the resolver selects
  // its move before visiting the trigger rather than marking it as an
  // inherited action.  It still vacates the exact node resource claimed by
  // the trigger in the same prevalidated atomic transaction.
  auto config = pibt_config("P2");
  const auto result =
      EventDrivenJunctionRuntime(canonical_graph(), std::move(config))
          .run(
              {
                  EventRuntimeBagRequest{
                      "higher-priority-owner",
                      1,
                      0.0,
                      50.0,
                      8,
                      11,
                      "canonical-map2"},
                  EventRuntimeBagRequest{
                      "lower-priority-trigger",
                      2,
                      0.55,
                      100.0,
                      6,
                      11,
                      "canonical-map2"},
              },
              inheritance_fault());
  require_safe_boundary(
      checks, result, "P2 higher-priority blocker-owner batch");
  checks.require(
      result.summary.bounded_local_pibt_commit_count > 0 &&
          result.summary.bounded_local_pibt_rollback_count == 0 &&
          result.summary.bounded_local_pibt_committed_action_count >= 2 &&
          result.summary.max_actions_committed_per_pibt_batch == 2 &&
          result.summary.bounded_local_pibt_inherited_action_count == 0 &&
          result.summary.bounded_local_pibt_handoff_count == 0,
      "a higher-priority owner-first move must commit atomically without "
      "being mislabeled as inherited priority");
  bool saw_owner_action = false;
  bool saw_trigger_action = false;
  for (const auto& decision : result.decisions) {
    saw_owner_action =
        saw_owner_action ||
        (decision.task_id == 1 && decision.current_node == 8 &&
         decision.selected_next == 11 &&
         decision.decision_source ==
             "bounded_local_pibt_blocker_owner_action");
    saw_trigger_action =
        saw_trigger_action ||
        (decision.task_id == 2 && decision.current_node == 6 &&
         decision.selected_next == 8 &&
         decision.decision_source ==
             "bounded_local_pibt_trigger_action");
  }
  checks.require(
      saw_owner_action && saw_trigger_action,
      "decision audit must distinguish blocker-owner and trigger actions");
}

void test_blocker_owner_label_uses_only_the_selected_trigger_resource(
    Checks& checks) {
  auto config = pibt_config("P2");
  const auto result =
      EventDrivenJunctionRuntime(canonical_graph(), std::move(config))
          .run(
              {
                  EventRuntimeBagRequest{
                      "owner8",
                      1,
                      0.0,
                      50.0,
                      8,
                      11,
                      "canonical-map2"},
                  EventRuntimeBagRequest{
                      "owner12",
                      3,
                      0.0,
                      60.0,
                      12,
                      13,
                      "canonical-map2"},
                  EventRuntimeBagRequest{
                      "trigger",
                      2,
                      0.55,
                      100.0,
                      6,
                      47,
                      "canonical-map2"},
              },
              {
                  EventRuntimeFaultWindow{
                      8, 11, 0.0, 1.55, 0.0, false},
                  EventRuntimeFaultWindow{
                      12, 13, 0.0, 1.55, 0.0, false},
              });
  require_safe_boundary(
      checks,
      result,
      "P2 selected-resource blocker-owner labels",
      3);
  checks.require(
      result.summary.bounded_local_pibt_commit_count == 1 &&
          result.summary.bounded_local_pibt_committed_action_count == 3 &&
          result.summary.bounded_local_pibt_rollback_count == 0 &&
          result.summary.bounded_local_pibt_inherited_action_count == 0 &&
          result.summary.bounded_local_pibt_handoff_count == 0,
      "three-action owner-first transaction must commit once without "
      "inventing inherited handoffs");
  bool saw_trigger = false;
  bool saw_direct_owner = false;
  bool saw_independent_owner = false;
  for (const auto& decision : result.decisions) {
    saw_trigger =
        saw_trigger ||
        (decision.task_id == 2 && decision.current_node == 6 &&
         decision.selected_next == 12 &&
         decision.decision_source ==
             "bounded_local_pibt_trigger_action");
    saw_direct_owner =
        saw_direct_owner ||
        (decision.task_id == 3 && decision.current_node == 12 &&
         decision.selected_next == 13 &&
         decision.decision_source ==
             "bounded_local_pibt_blocker_owner_action");
    saw_independent_owner =
        saw_independent_owner ||
        (decision.task_id == 1 && decision.current_node == 8 &&
         decision.selected_next == 11 &&
         decision.decision_source ==
             "bounded_local_pibt_independent_ready_action");
  }
  checks.require(
      saw_trigger && saw_direct_owner && saw_independent_owner,
      "only the owner of the trigger's selected resource may receive the "
      "blocker-owner audit label");
}

void require_safe_boundary(Checks& checks,
                           const EventDrivenJunctionResult& result,
                           const std::string& label,
                           int expected_completed_count) {
  checks.require(result.summary.completed_count ==
                         expected_completed_count &&
                     result.summary.failed_count == 0,
                 label + " must complete every real-map bag");
  checks.require(result.summary.reservation_conflicts == 0,
                 label + " must retain zero reservation conflicts");
  checks.require(result.summary.runtime_full_astar_calls == 0 &&
                     result.summary.global_reservation_scan_count == 0 &&
                     result.summary.max_edges_selected_per_arrive <= 1,
                 label + " must retain the no-A*, no-global-scan, one-edge boundary");
  checks.require(!result.summary.bounded_local_pibt_classical_completeness_claimed,
                 label + " must not claim classical PIBT completeness");
  checks.require(result.summary.declared_max_events == 100000 &&
                     result.summary.local_queue_capacity ==
                         (label == "P1 unlimited-capacity sensitivity"
                              ? 0
                              : 1),
                 label + " must echo the actual event and queue configuration");
  for (const auto& bag : result.bags) {
    checks.require(
        bag.source_queue_delay >= 0.0 &&
            bag.junction_queue_wait_seconds >= 0.0 &&
            bag.edge_travel_time_seconds >= 0.0 &&
            bag.node_service_time_seconds >= 0.0 &&
            bag.loop_extra_time_seconds >= 0.0 &&
            bag.goal_completion_time_seconds >= 0.0,
        label + " must expose non-negative Stage-B timing components");
    if (!bag.completed) {
      continue;
    }
    const double elapsed = bag.finish_time - bag.release_time;
    const double reconstructed =
        bag.source_queue_delay +
        bag.junction_queue_wait_seconds +
        bag.edge_travel_time_seconds +
        bag.node_service_time_seconds;
    checks.require(
        std::abs(reconstructed - elapsed) <= 1.0e-7 &&
            std::abs(bag.goal_completion_time_seconds - elapsed) <=
                1.0e-7,
        label + " atomic PIBT execution must preserve the exact "
                "release-to-finish timing decomposition");
    checks.require(
        bag.loop_extra_time_seconds <=
            bag.edge_travel_time_seconds + 1.0e-12,
        label + " loop-extra travel must be a subset of committed travel");
  }
}

void test_p0_is_an_actual_bypass(Checks& checks) {
  const auto result = run_motif(pibt_config("P0"));
  require_safe_boundary(checks, result, "P0");
  checks.require(result.summary.pibt_mode == "P0",
                 "P0 must be exposed as the canonical runtime mode");
  checks.require(result.summary.bounded_local_pibt_activation_count == 0 &&
                     result.summary.bounded_local_pibt_proposal_batch_count == 0 &&
                     result.summary.bounded_local_pibt_committed_batch_count == 0 &&
                     result.summary.bounded_local_pibt_committed_action_count == 0 &&
                     result.summary.bounded_local_pibt_inherited_action_count == 0,
                 "P0 must bypass the bounded resolver without synthetic counters");
  checks.require(result.pibt_events.empty(),
                 "P0 must emit no bounded-local-PIBT audit rows");
  checks.require(result.summary.pibt_lite_handoff_count == 0 &&
                     result.summary.same_bag_alternative_edge_scan_handoff_count == 0,
                 "disabled pibt-lite must remain distinct from true PIBT");
}

void test_real_map_inheritance_for_p1_through_p4(Checks& checks) {
  for (const std::string mode : {"P1", "P2", "P3", "P4"}) {
    const auto result = run_motif(pibt_config(mode));
    require_safe_boundary(checks, result, mode);
    checks.require(result.summary.pibt_mode == mode,
                   mode + " must be exposed as the canonical runtime mode");
    checks.require(
        result.summary.pibt_max_depth ==
            static_cast<int>(mode.back() - '0'),
        mode + " must echo the inheritance depth encoded by the mode");
    checks.require(result.summary.bounded_local_pibt_activation_count == 1 &&
                       result.summary.bounded_local_pibt_proposal_batch_count == 1 &&
                       result.summary.bounded_local_pibt_proposed_action_count == 2 &&
                       result.summary.bounded_local_pibt_committed_batch_count == 1 &&
                       result.summary.bounded_local_pibt_committed_action_count == 2,
                   mode + " must atomically commit the two-action local batch");
    checks.require(result.summary.bounded_local_pibt_inherited_action_count == 1 &&
                       result.summary.bounded_local_pibt_blocker_move_attempt_count == 1 &&
                       result.summary.bounded_local_pibt_max_inheritance_depth == 1,
                   mode + " must move one actual blocker at inheritance depth one");
    checks.require(
        result.summary.bounded_local_pibt_attempt_count > 0 &&
            result.summary.bounded_local_pibt_prepare_count == 1 &&
            result.summary.bounded_local_pibt_validate_count > 0 &&
            result.summary.bounded_local_pibt_commit_count == 1 &&
            result.summary.bounded_local_pibt_handoff_count == 1,
        mode + " must expose truthful resolver stage and inherited-handoff counters");
    checks.require(
        result.summary.max_edges_selected_per_bag_per_decision == 1 &&
            result.summary.max_actions_committed_per_pibt_batch == 2,
        mode + " must distinguish one edge per bag from a two-action atomic batch");
    checks.require(result.summary.bounded_local_pibt_rollback_count == 0 &&
                       result.summary.bounded_local_pibt_fault_rejection_count == 0 &&
                       result.summary.bounded_local_pibt_prepare_rejection_count == 0 &&
                       result.summary.bounded_local_pibt_commit_rejection_count == 0,
                   mode + " must complete the verified motif without rejected staging");
    checks.require(result.summary.bounded_local_pibt_max_slice_bags == 2 &&
                       result.summary.bounded_local_pibt_max_slice_resources <=
                           pibt_config(mode).pibt_max_local_resources &&
                       result.summary.bounded_local_pibt_max_candidates_per_bag <=
                           pibt_config(mode).pibt_max_candidates_per_bag,
                   mode + " must expose and respect the configured local bounds");
    checks.require(
        result.summary.bounded_local_pibt_max_transaction_credit_entries <=
            result.summary.bounded_local_pibt_max_slice_bags &&
            result.summary
                    .bounded_local_pibt_max_transaction_credit_entries <=
                pibt_config(mode).pibt_max_ready_bags,
        mode + " transaction credit state must be bounded by the action batch");
    checks.require(
        result.summary.bounded_local_pibt_max_transaction_bag_entries <= 2 &&
            result.summary
                    .bounded_local_pibt_max_transaction_junction_scalar_entries <=
                4 &&
            result.summary
                    .bounded_local_pibt_max_transaction_action_deltas ==
                2,
        mode + " rollback state must contain bounded deltas, not full queues");
    checks.require(result.pibt_events.size() == 1,
                   mode + " must emit one committed activation audit");
    if (result.pibt_events.size() != 1) {
      continue;
    }
    const auto& audit = result.pibt_events.front();
    checks.require(audit.outcome == "COMMITTED" &&
                       audit.actions.size() == 2 &&
                       audit.committed_action_count == 2 &&
                       audit.inherited_action_count == 1 &&
                       audit.transaction_credit_entry_count <=
                           audit.committed_action_count &&
                       audit.transaction_bag_entry_count <=
                           audit.committed_action_count &&
                       audit.transaction_junction_scalar_entry_count <=
                           audit.committed_action_count * 2 &&
                       audit.transaction_action_delta_count ==
                           audit.committed_action_count,
                   mode + " audit must expose the complete committed batch");
    bool saw_trigger = false;
    bool saw_owner = false;
    for (const auto& action : audit.actions) {
      checks.require(canonical_graph().has_edge(action.from_node, action.next_node),
                     mode + " actions must be real adjacent map2 edges");
      saw_trigger = saw_trigger ||
                    (action.from_node == 6 && action.next_node == 8 &&
                     !action.inherited && action.inheritance_depth == 0);
      saw_owner = saw_owner ||
                  (action.from_node == 8 && action.next_node == 11 &&
                   action.inherited && action.inheritance_depth == 1);
    }
    checks.require(saw_trigger && saw_owner,
                   mode + " must move the trigger and its actual queue owner");
  }
}

void test_capacity_and_slice_bounds_fail_closed(Checks& checks) {
  auto unlimited = pibt_config("P1");
  unlimited.local_queue_capacity = 0;
  const auto unlimited_result = run_motif(unlimited);
  require_safe_boundary(checks, unlimited_result, "P1 unlimited-capacity sensitivity");
  checks.require(unlimited_result.summary.bounded_local_pibt_activation_count == 0 &&
                     unlimited_result.summary.bounded_local_pibt_committed_action_count == 0 &&
                     unlimited_result.summary.bounded_local_pibt_not_applicable_count > 0,
                 "unknown/unlimited queue capacity must not invent a resource owner");

  auto bounded_out = pibt_config("P1");
  bounded_out.pibt_max_local_resources = 1;
  const auto bounded_out_result = run_motif(bounded_out);
  require_safe_boundary(checks, bounded_out_result, "P1 tight resource bound");
  checks.require(bounded_out_result.summary.bounded_local_pibt_activation_count == 0 &&
                     bounded_out_result.summary.bounded_local_pibt_committed_action_count == 0 &&
                     bounded_out_result.summary.bounded_local_pibt_not_applicable_count > 0,
                 "an oversized local slice must fail closed without a partial commit");
}

void test_trace_limit_and_honest_fault_metrics(Checks& checks) {
  auto config = pibt_config("P1");
  config.trace_limit = 0;
  const auto result = run_motif(config);
  require_safe_boundary(checks, result, "P1 summary-only");
  checks.require(result.summary.bounded_local_pibt_committed_action_count == 2,
                 "trace suppression must not alter true PIBT execution counters");
  checks.require(result.summary.trace_limit == 0 &&
                     result.summary.event_trace_limit == 0 &&
                     result.summary.event_trace_limit_inherited,
                 "the default event trace cap must inherit trace_limit exactly");
  checks.require(result.events.empty() && result.decisions.empty() &&
                     result.hold_attempts.empty() &&
                     result.fault_events.empty() &&
                     result.credit_events.empty() &&
                     result.pibt_events.empty(),
                 "trace_limit=0 must suppress all event, decision, fault, credit, and PIBT rows");
  checks.require(
      result.summary.bounded_local_pibt_attempt_count > 0 &&
          result.summary.bounded_local_pibt_prepare_count > 0 &&
          result.summary.bounded_local_pibt_validate_count > 0 &&
          result.summary.bounded_local_pibt_commit_count > 0,
      "summary-only mode must retain true PIBT stage counters");
  checks.require(result.summary.fault_affected_bag_count == 1 &&
                     result.summary.fault_affected_completed_count == 1,
                 "fault completion must be counted from actual affected bag state");
  checks.require(result.summary.fault_recovery_seconds_available &&
                     result.summary.fault_recovery_seconds > 0.0,
                 "fully repaired and completed exposure must expose measured recovery time");
  checks.require(result.summary.repair_backlog_slope_available &&
                     result.summary.repair_backlog_slope < 0.0,
                 "a positive post-repair observation window must expose measured drain slope");

  auto decision_only_config = pibt_config("P1");
  decision_only_config.trace_limit = -1;
  decision_only_config.event_trace_limit = 0;
  const auto decision_only = run_motif(decision_only_config);
  require_safe_boundary(checks, decision_only, "P1 decision-only trace");
  checks.require(
      decision_only.events.empty() && !decision_only.decisions.empty() &&
          !decision_only.fault_events.empty() &&
          !decision_only.pibt_events.empty(),
      "event_trace_limit=0 must suppress only event rows while the shared "
      "trace_limit still retains decisions, fault audits, and PIBT audits");
  checks.require(
      static_cast<std::uint64_t>(decision_only.decisions.size()) ==
              decision_only.summary.decision_count &&
          static_cast<int>(decision_only.decisions.size()) ==
              decision_only.summary.decision_trace_stored_count &&
          decision_only.decisions.size() +
                  decision_only.hold_attempts.size() ==
              decision_only.summary.decision_trace_seen_count,
      "an unlimited decision trace must contain every committed one-edge "
      "action and every observed hold even when event rows are disabled");
  checks.require(
      decision_only.summary.trace_limit == -1 &&
          decision_only.summary.event_trace_limit == 0 &&
          !decision_only.summary.event_trace_limit_inherited &&
          decision_only.summary.event_trace_truncated,
      "an explicit independent event cap must be echoed and report event "
      "suppression without truncating the other audit families");
  checks.require(
      decision_only.summary.bounded_local_pibt_committed_action_count ==
          result.summary.bounded_local_pibt_committed_action_count,
      "independent event trace suppression must not alter PIBT execution");

  auto no_fault_config = pibt_config("P0");
  const auto no_fault = EventDrivenJunctionRuntime(canonical_graph(), no_fault_config)
                            .run({EventRuntimeBagRequest{
                                "no-fault", 3, 0.0, 100.0, 8, 11, "canonical-map2"}});
  checks.require(no_fault.summary.fault_affected_bag_count == 0 &&
                     no_fault.summary.fault_affected_completed_count == 0 &&
                     !no_fault.summary.fault_recovery_seconds_available &&
                     !no_fault.summary.repair_backlog_slope_available,
                 "unobserved fault metrics must be unavailable, not fabricated zeroes");
}

Graph wide_candidate_graph() {
  Graph graph;
  for (int node = 0; node < 4; ++node) {
    graph.add_node(
        czr005::ics::Node{node, node == 1 ? 2 : 4, 0.0, node, 0, {}});
  }
  for (int next = 1; next < 4; ++next) {
    graph.add_edge(czr005::ics::Edge{0, next, 1.0, 1.0});
  }
  graph.set_heuristic(
      std::vector<std::vector<double>>(
          4, std::vector<double>(4, 0.0)));
  return graph;
}

void test_candidate_bound_precedes_materialization(Checks& checks) {
  auto config = pibt_config("P1");
  config.pibt_max_candidates_per_bag = 2;
  config.local_queue_capacity = 1;
  config.max_simulation_time = 20.0;
  const auto result =
      EventDrivenJunctionRuntime(wide_candidate_graph(), config)
          .run({EventRuntimeBagRequest{
              "wide", 41, 0.0, 100.0, 0, 1, "wide-graph"}});
  checks.require(
      result.summary
              .bounded_local_pibt_candidate_bound_rejection_count >
          0 &&
          result.summary
                  .bounded_local_pibt_candidate_materialization_count ==
              0,
      "PIBT must reject an oversized outgoing set before any candidate_record materialization");
  checks.require(result.summary.completed_count == 1,
                 "the bounded PIBT refusal must safely fall back to the ordinary one-edge path");
}

void test_repeated_fault_instances_do_not_reuse_old_repair(
    Checks& checks) {
  auto config = pibt_config("P0");
  config.max_simulation_time = 20.0;
  config.retry_interval = 0.05;
  const auto result =
      EventDrivenJunctionRuntime(canonical_graph(), config)
          .run(
              {EventRuntimeBagRequest{
                  "second-window",
                  51,
                  0.3,
                  100.0,
                  6,
                  47,
                  "canonical-map2"}},
              {
                  EventRuntimeFaultWindow{
                      6, 12, 0.0, 0.1, 0.0, false},
                  EventRuntimeFaultWindow{
                      6, 12, 0.2, 100.0, 0.0, false},
              });
  checks.require(result.summary.fault_affected_bag_count > 0,
                 "the second same-edge fault instance must expose the bag");
  checks.require(
      !result.summary.fault_recovery_seconds_available &&
          !result.summary.repair_backlog_slope_available,
      "an unresolved second same-edge fault must not reuse the first repair timestamp");
}

void test_numeric_provenance_echoes_actual_config(
    Checks& checks) {
  auto config = pibt_config("P0");
  config.resource_semantics = "R2";
  config.pressure_mode = "C2";
  config.admission_mode = "off";
  config.scorer_mode = "S0";
  config.pressure_weight = 3.25;
  config.pressure_age_weight = 0.125;
  config.pressure_distance_bias = 0.75;
  config.credit_validity_seconds = 2.5;
  config.credit_snapshot_max_age_seconds = 0.375;
  config.credit_capacity_per_edge = 3;
  config.credit_lifecycle_limit = 17;
  const auto result =
      EventDrivenJunctionRuntime(canonical_graph(), config)
          .run({EventRuntimeBagRequest{
              "echo", 61, 0.0, 100.0, 8, 11, "canonical-map2"}});
  checks.require(
      result.summary.pressure_weight == 3.25 &&
          result.summary.pressure_age_weight == 0.125 &&
          result.summary.pressure_distance_bias == 0.75 &&
          result.summary.credit_validity_seconds == 2.5 &&
          result.summary.credit_snapshot_max_age_seconds == 0.375 &&
          result.summary.credit_capacity_per_edge == 3 &&
          result.summary.credit_lifecycle_limit == 17,
      "summary provenance must echo every actual pressure and credit numeric control");
  checks.require(
      result.summary.resource_semantics_echo == "R2" &&
          result.summary.pressure_mode_echo == "C2" &&
          result.summary.admission_mode_echo == "off" &&
          result.summary.pibt_mode_echo == "P0" &&
          result.summary.scorer_mode_echo == "S0" &&
          result.summary.framework_mode_echo ==
              "event_loop_one_step",
      "summary provenance must retain every exact requested mode separately from its canonical ID");
}

void test_s0_short_alias_preserves_exact_decision_payload(
    Checks& checks) {
  auto historical = pibt_config("P0");
  auto short_alias = historical;
  short_alias.scorer_mode = "S0";
  const std::vector<EventRuntimeBagRequest> requests{
      EventRuntimeBagRequest{
          "s0-parity", 71, 0.0, 100.0, 6, 47, "canonical-map2"},
  };
  const auto left =
      EventDrivenJunctionRuntime(canonical_graph(), historical)
          .run(requests);
  const auto right =
      EventDrivenJunctionRuntime(canonical_graph(), short_alias)
          .run(requests);
  checks.require(
      left.bags.size() == right.bags.size() &&
          left.summary.completed_count ==
              right.summary.completed_count &&
          left.summary.failed_count == right.summary.failed_count &&
          left.decisions.size() == right.decisions.size(),
      "S0 short alias must preserve historical execution cardinality");
  const std::size_t shared =
      std::min(left.decisions.size(), right.decisions.size());
  for (std::size_t decision_index = 0;
       decision_index < shared;
       ++decision_index) {
    const auto& expected = left.decisions[decision_index];
    const auto& actual = right.decisions[decision_index];
    checks.require(
        expected.model_prediction == actual.model_prediction &&
            expected.model_margin == actual.model_margin &&
            expected.selected_next == actual.selected_next &&
            expected.fallback_selected_next ==
                actual.fallback_selected_next &&
            expected.decision_source == actual.decision_source &&
            expected.rule_reason == actual.rule_reason &&
            expected.risk_gate_triggered ==
                actual.risk_gate_triggered &&
            expected.candidates.size() ==
                actual.candidates.size(),
        "S0 short alias must preserve every top-level decision output");
    const std::size_t candidate_shared =
        std::min(expected.candidates.size(),
                 actual.candidates.size());
    for (std::size_t candidate_index = 0;
         candidate_index < candidate_shared;
         ++candidate_index) {
      const auto& expected_candidate =
          expected.candidates[candidate_index];
      const auto& actual_candidate =
          actual.candidates[candidate_index];
      checks.require(
          expected_candidate.next_node ==
                  actual_candidate.next_node &&
              expected_candidate.pre_fault_policy_score ==
                  actual_candidate.pre_fault_policy_score &&
              expected_candidate.model_score ==
                  actual_candidate.model_score &&
              expected_candidate.scorer_raw_score ==
                  actual_candidate.scorer_raw_score &&
              expected_candidate.shield_allowed ==
                  actual_candidate.shield_allowed &&
              expected_candidate.shield_reason ==
                  actual_candidate.shield_reason,
          "S0 short alias must preserve every emitted candidate output");
    }
    checks.require(
        actual.decision_source == "local_static_potential" &&
            actual.scorer_effective_id ==
                "S0_current_handwritten_static_score",
        "S0 must retain its historical decision_source while exposing the canonical effective scorer ID");
  }
}

void test_invalid_configuration_rejected(Checks& checks) {
  try {
    EventDrivenJunctionRuntime ignored(canonical_graph(), pibt_config("P5"));
    (void)ignored;
    checks.require(false, "unknown PIBT mode must fail closed");
  } catch (const std::invalid_argument&) {
  }

  try {
    auto invalid = pibt_config("P1");
    invalid.pibt_max_ready_bags = 0;
    EventDrivenJunctionRuntime ignored(canonical_graph(), invalid);
    (void)ignored;
    checks.require(false, "non-positive PIBT bounds must fail closed");
  } catch (const std::invalid_argument&) {
  }

  try {
    auto invalid = pibt_config("P0");
    invalid.max_simulation_time =
        std::numeric_limits<double>::quiet_NaN();
    EventDrivenJunctionRuntime ignored(canonical_graph(), invalid);
    (void)ignored;
    checks.require(false,
                   "NaN max_simulation_time must fail closed");
  } catch (const std::invalid_argument&) {
  }

  try {
    auto invalid = pibt_config("P0");
    EventDrivenJunctionRuntime runtime(canonical_graph(), invalid);
    (void)runtime.run({EventRuntimeBagRequest{
        "nan-release",
        81,
        std::numeric_limits<double>::quiet_NaN(),
        100.0,
        8,
        11,
        "canonical-map2"}});
    checks.require(false,
                   "NaN request release_time must fail closed");
  } catch (const std::invalid_argument&) {
  }

  try {
    auto invalid = pibt_config("P0");
    EventDrivenJunctionRuntime runtime(canonical_graph(), invalid);
    (void)runtime.run(
        {EventRuntimeBagRequest{
            "nan-fault",
            82,
            0.0,
            100.0,
            8,
            11,
            "canonical-map2"}},
        {EventRuntimeFaultWindow{
            8,
            11,
            std::numeric_limits<double>::quiet_NaN(),
            1.0,
            0.0,
            false}});
    checks.require(false,
                   "NaN fault window time must fail closed");
  } catch (const std::invalid_argument&) {
  }
}

}  // namespace

int main() {
  Checks checks;
  test_p0_is_an_actual_bypass(checks);
  test_root_only_safe_alternative_is_not_mislabeled_as_pibt(checks);
  test_same_bag_fallback_revalidates_physical_fault_shield(checks);
  test_higher_priority_blocker_owner_move_is_a_real_atomic_batch(checks);
  test_blocker_owner_label_uses_only_the_selected_trigger_resource(checks);
  test_real_map_inheritance_for_p1_through_p4(checks);
  test_capacity_and_slice_bounds_fail_closed(checks);
  test_trace_limit_and_honest_fault_metrics(checks);
  test_candidate_bound_precedes_materialization(checks);
  test_repeated_fault_instances_do_not_reuse_old_repair(checks);
  test_numeric_provenance_echoes_actual_config(checks);
  test_s0_short_alias_preserves_exact_decision_payload(checks);
  test_invalid_configuration_rejected(checks);
  if (checks.failures != 0) {
    std::cerr << checks.failures
              << " event-runtime bounded-local-PIBT checks failed\n";
    return 1;
  }
  std::cout << "event-runtime bounded-local-PIBT checks passed\n";
  return 0;
}
