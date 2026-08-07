#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

#include "ics_core/runtime/event_driven_junction.hpp"

namespace {

using czr005::ics::Edge;
using czr005::ics::EventDrivenJunctionConfig;
using czr005::ics::EventDrivenJunctionResult;
using czr005::ics::EventDrivenJunctionRuntime;
using czr005::ics::EventRuntimeBagRequest;
using czr005::ics::EventRuntimeFaultWindow;
using czr005::ics::Graph;
using czr005::ics::G4IRSF18MergeLinearPolicyConfig;
using czr005::ics::Node;

struct Checks {
  int failures = 0;

  void require(bool condition, const std::string& message) {
    if (!condition) {
      ++failures;
      std::cerr << "FAIL: " << message << '\n';
    }
  }
};

Graph busy_destination_graph() {
  Graph graph;
  graph.add_node(Node{0, 1, 0.1, 0, 0, {2}});
  graph.add_node(Node{1, 1, 0.1, 0, 1, {2}});
  graph.add_node(Node{2, 4, 5.0, 1, 0, {3}});
  graph.add_node(Node{3, 2, 0.0, 2, 0, {}});
  graph.add_edge(Edge{0, 2, 1.0, 1.0});
  graph.add_edge(Edge{1, 2, 1.0, 1.0});
  graph.add_edge(Edge{2, 3, 1.0, 1.0});
  graph.set_heuristic({
      {0.0, 1000.0, 1.0, 2.0},
      {1000.0, 0.0, 1.0, 2.0},
      {1000.0, 1000.0, 0.0, 1.0},
      {1000.0, 1000.0, 1000.0, 0.0},
  });
  return graph;
}

std::vector<EventRuntimeBagRequest> busy_destination_requests() {
  // The blocker owns node 2's [0,5] source-service window.  The two merge
  // requests appear at different timestamps, but both first become eligible
  // to enter node 2 at t=4 for the exact [5,10] destination-service slot.
  return {
      EventRuntimeBagRequest{
          "destination-blocker", 1, 0.0, 100.0, 2, 3, "g18-regression"},
      EventRuntimeBagRequest{
          "fifo-first", 2, 1.0, 100.0, 0, 3, "g18-regression"},
      EventRuntimeBagRequest{
          "urgent-second", 3, 2.0, 6.0, 1, 3, "g18-regression"},
  };
}

EventDrivenJunctionConfig e4_config() {
  EventDrivenJunctionConfig config;
  config.resource_semantics = "R3";
  config.event_semantics =
      "E4_batch_plus_destination_merge_request";
  config.enable_source_admission = false;
  config.admission_mode = "off";
  config.enable_backpressure = false;
  config.pressure_mode = "C0";
  config.pibt_mode = "P0";
  config.priority_mode = "Q0";
  config.retry_interval = 0.25;
  config.minimum_service_seconds = 0.001;
  config.dispatch_headway_seconds = 0.0;
  config.starvation_threshold = 1000.0;
  config.max_decisions_per_bag = 1000;
  config.max_events = 100000;
  config.max_simulation_time = 100.0;
  config.trace_limit = 10000;
  config.event_trace_limit = 10000;
  config.enable_opportunity_telemetry = true;
  config.opportunity_trace_limit = 1000;
  config.merge_grant_max_pending_requests = 4;
  config.merge_grant_lifecycle_limit = 1000;
  return config;
}

EventDrivenJunctionResult run_with_timing(
    const std::string& timing_mode) {
  auto config = e4_config();
  config.merge_grant_timing_mode = timing_mode;
  return EventDrivenJunctionRuntime(
             busy_destination_graph(), std::move(config))
      .run(busy_destination_requests());
}

EventDrivenJunctionResult run_default_eager() {
  return EventDrivenJunctionRuntime(
             busy_destination_graph(), e4_config())
      .run(busy_destination_requests());
}

EventDrivenJunctionResult run_jit_with_pending_fault() {
  auto config = e4_config();
  config.merge_grant_timing_mode = "jit_fifo";
  return EventDrivenJunctionRuntime(
             busy_destination_graph(), std::move(config))
      .run(
          busy_destination_requests(),
          {EventRuntimeFaultWindow{
              1, 2, 3.0, 4.5, 0.0, false}});
}

G4IRSF18MergeLinearPolicyConfig valid_test_policy(
    const std::string& mode = "research_closed_loop") {
  G4IRSF18MergeLinearPolicyConfig policy;
  policy.mode = mode;
  policy.schema = czr005::ics::kG4IRSF18MergeLinearPolicySchema;
  policy.family = czr005::ics::kG4IRSF18MergeLinearPolicyFamily;
  policy.feature_contract = czr005::ics::kG4IRSF18MergeFeatureContract;
  policy.score_direction = "higher_is_better";
  policy.tie_break = "fifo";
  policy.tie_break_scope = "finite_in_contract_equal_score_only";
  policy.ood_fallback = "J2";
  policy.authorization =
      "RESEARCH_FIXED_WORKLOAD_CANDIDATE_NATIVE_PARITY_REQUIRED";
  for (const char* name : czr005::ics::g4irsf18_merge_feature_names()) {
    policy.feature_names.emplace_back(name);
  }
  policy.mean.assign(czr005::ics::kG4IRSF18MergeFeatureCount, 0.0);
  policy.scale.assign(czr005::ics::kG4IRSF18MergeFeatureCount, 1.0);
  policy.weights.assign(czr005::ics::kG4IRSF18MergeFeatureCount, 0.0);
  policy.feature_lower.assign(
      czr005::ics::g4irsf18_merge_feature_lower().begin(),
      czr005::ics::g4irsf18_merge_feature_lower().end());
  policy.feature_upper.assign(
      czr005::ics::g4irsf18_merge_feature_upper().begin(),
      czr005::ics::g4irsf18_merge_feature_upper().end());
  // A positive deadline-slack coefficient chooses the FIFO/high-slack peer,
  // making the model's action observably distinct from J2 in this fixture.
  policy.weights[2] = 1.0;
  policy.research_closed_loop_authorized = true;
  policy.fixed_research_workload = true;
  policy.coverage_cap = 1.0;
  policy.max_overrides_per_segment = 2;
  return policy;
}

EventDrivenJunctionResult run_with_policy(
    G4IRSF18MergeLinearPolicyConfig policy) {
  auto config = e4_config();
  config.merge_grant_timing_mode = "jit_fair_aging_deadline";
  config.starvation_threshold = 120.0;
  config.g4irsf18_merge_policy = std::move(policy);
  return EventDrivenJunctionRuntime(
             busy_destination_graph(), std::move(config))
      .run(busy_destination_requests());
}

void require_safe_complete(Checks& checks,
                           const EventDrivenJunctionResult& result,
                           const std::string& label) {
  checks.require(result.summary.completed_count == 3 &&
                     result.summary.failed_count == 0,
                 label + ": every bag must drain");
  checks.require(!result.summary.event_limit_reached &&
                     !result.summary.time_limit_reached,
                 label + ": bounded run must terminate naturally");
  checks.require(result.summary.reservation_conflicts == 0 &&
                     result.summary
                             .physical_fault_edge_entry_violation_count ==
                         0,
                 label + ": safety counters must stay clean");
  checks.require(result.summary.merge_grant_conservation_holds &&
                     result.summary.merge_grant_active_bijection_holds &&
                     result.summary.merge_grant_runtime_owned_capability &&
                     result.summary.merge_grant_exact_slot_no_future_shift &&
                     result.summary.merge_grant_outstanding_request_count ==
                         0 &&
                     result.summary.merge_grant_final_active_unconsumed == 0,
                 label + ": grant protocol must close cleanly");
}

std::vector<const czr005::ics::EventRuntimeMergeServiceOpportunityRow*>
first_opportunity_rows(const EventDrivenJunctionResult& result) {
  std::vector<
      const czr005::ics::EventRuntimeMergeServiceOpportunityRow*> rows;
  if (result.merge_service_opportunities.empty()) {
    return rows;
  }
  const auto first_id =
      result.merge_service_opportunities.front().opportunity_id;
  for (const auto& row : result.merge_service_opportunities) {
    if (row.opportunity_id == first_id) {
      rows.push_back(&row);
    }
  }
  return rows;
}

void test_jit_fifo_retains_loser(Checks& checks) {
  const auto result = run_with_timing("jit_fifo");
  require_safe_complete(checks, result, "J1");
  checks.require(result.summary.merge_grant_timing_mode == "jit_fifo",
                 "J1 must report its canonical timing mode");
  checks.require(result.summary.merge_grant_peak_pending_requests >= 2 &&
                     result.summary
                             .merge_grant_multi_candidate_opportunity_count >=
                         1 &&
                     result.summary.merge_grant_true_competition_count >= 1,
                 "J1 must expose both staggered requests at one real service opportunity");
  checks.require(result.summary.merge_grant_wakeup_coalesced_count >= 1,
                 "J1 must coalesce the second request onto the existing destination wakeup");
  checks.require(
      result.summary.merge_grant_contended_loser_retry_count == 0,
      "J1 must retain a non-winning pending request instead of terminalizing it");

  const auto first = first_opportunity_rows(result);
  checks.require(first.size() == 2,
                 "J1 first service opportunity must store exactly two candidates");
  std::uint64_t retained_request_id = 0;
  for (const auto* row : first) {
    if (!row->chosen_winner) {
      retained_request_id = row->candidate_request_id;
    }
  }
  const bool retained_loser_later_wins =
      retained_request_id != 0 &&
      std::any_of(
          result.merge_service_opportunities.begin(),
          result.merge_service_opportunities.end(),
          [&](const auto& row) {
            return row.opportunity_id > first.front()->opportunity_id &&
                   row.candidate_request_id == retained_request_id &&
                   row.chosen_winner;
          });
  checks.require(retained_loser_later_wins,
                 "J1 first loser must remain pending and win a later natural opportunity");
  checks.require(result.summary.merge_grant_order_mutation_count == 0,
                 "J1 FIFO must not report a policy order mutation");
}

void test_jit_deadline_aging_mutates_real_choice(Checks& checks) {
  const auto result = run_with_timing("jit_fair_aging_deadline");
  require_safe_complete(checks, result, "J2");
  const auto first = first_opportunity_rows(result);
  checks.require(first.size() == 2 &&
                     result.summary.merge_grant_order_mutation_count >= 1,
                 "J2 must mutate a genuine two-candidate FIFO choice");
  if (!first.empty()) {
    checks.require(
        first.front()->baseline_winner_request_id !=
            first.front()->chosen_winner_request_id,
        "J2 trace must identify distinct FIFO and deadline-aging winners");
    const auto chosen = std::find_if(
        first.begin(), first.end(), [](const auto* row) {
          return row->chosen_winner;
        });
    checks.require(chosen != first.end() &&
                       (*chosen)->upstream_node == 1,
                   "J2 must choose the later but urgent upstream request");
  }
}

void test_pending_fault_revalidates_generation(Checks& checks) {
  const auto result = run_jit_with_pending_fault();
  require_safe_complete(checks, result, "J1 pending fault");
  checks.require(result.summary.merge_grant_revoked_fault_count >= 1,
                 "a faulted pending edge must be revoked at the state-change wakeup");
  checks.require(result.summary.merge_grant_stale_wakeup_count >= 1,
                 "the superseded natural timer must become a lazy stale-generation event");
  checks.require(
      std::any_of(
          result.merge_grant_lifecycle.begin(),
          result.merge_grant_lifecycle.end(),
          [](const auto& row) {
            return row.state ==
                       czr005::ics::MergeGrantState::kRevokedFault &&
                   row.reason ==
                       czr005::ics::MergeGrantReason::kFaultGenerationChanged &&
                   row.upstream_node == 1 &&
                   std::abs(row.time - 3.0) < 1.0e-9;
          }),
      "pending fault revocation must occur at the real native fault timestamp");
}

void test_default_eager_compatibility(Checks& checks) {
  const auto implicit = run_default_eager();
  const auto explicit_mode = run_with_timing("eager");
  require_safe_complete(checks, implicit, "implicit eager");
  require_safe_complete(checks, explicit_mode, "explicit eager");
  checks.require(implicit.summary.merge_grant_timing_mode == "eager" &&
                     implicit.summary
                             .merge_grant_service_opportunity_count == 0 &&
                     implicit.merge_service_opportunities.empty(),
                 "default eager mode must not execute or emit JIT opportunities");
  checks.require(
      implicit.summary.event_count == explicit_mode.summary.event_count &&
          implicit.summary.decision_count ==
              explicit_mode.summary.decision_count &&
          implicit.summary.merge_grant_request_count ==
              explicit_mode.summary.merge_grant_request_count &&
          implicit.summary.merge_grant_committed_count ==
              explicit_mode.summary.merge_grant_committed_count &&
          implicit.summary.merge_grant_contended_loser_retry_count ==
              explicit_mode.summary.merge_grant_contended_loser_retry_count &&
          implicit.merge_grant_lifecycle.size() ==
              explicit_mode.merge_grant_lifecycle.size(),
      "implicit and explicit eager controls must preserve the historical path");
  checks.require(implicit.bags.size() == explicit_mode.bags.size(),
                 "eager comparison must have identical bag cardinality");
  if (implicit.bags.size() == explicit_mode.bags.size()) {
    for (std::size_t index = 0; index < implicit.bags.size(); ++index) {
      checks.require(
          implicit.bags[index].runtime_bag_id ==
                  explicit_mode.bags[index].runtime_bag_id &&
              implicit.bags[index].completed ==
                  explicit_mode.bags[index].completed &&
              std::abs(implicit.bags[index].arrival_time -
                       explicit_mode.bags[index].arrival_time) < 1.0e-9,
          "implicit and explicit eager bag results must match exactly");
    }
  }
}

void test_learned_policy_research_closed_loop_and_feature_parity(
    Checks& checks) {
  const auto policy = valid_test_policy();
  const auto result = run_with_policy(policy);
  require_safe_complete(checks, result, "G18 research closed loop");
  const auto first = first_opportunity_rows(result);
  checks.require(result.summary.g4irsf18_merge_artifact_valid &&
                     result.summary.g4irsf18_merge_model_applied_count >= 1 &&
                     result.summary
                             .g4irsf18_merge_distinct_action_mutation_count >=
                         1 &&
                     result.summary.g4irsf18_merge_model_ownership_count >= 1,
                 "authorized research policy must own a bounded distinct action");
  checks.require(first.size() == 2,
                 "research parity opportunity must contain two candidates");
  if (first.size() == 2) {
    const auto proposed = std::find_if(
        first.begin(), first.end(), [](const auto* row) {
          return row->model_proposed;
        });
    checks.require(proposed != first.end() &&
                       (*proposed)->model_applied &&
                       (*proposed)->model_chosen &&
                       (*proposed)->upstream_node == 0,
                   "positive slack model must replace urgent J2 with FIFO peer");

    double mean_age = 0.0;
    double mean_slack = 0.0;
    double mean_service = 0.0;
    double mean_pressure = 0.0;
    double mean_route = 0.0;
    double mean_lag = 0.0;
    for (const auto* row : first) {
      mean_age += row->wait_age;
      mean_slack += row->deadline_slack;
      mean_service += row->destination_service_seconds;
      mean_pressure += row->downstream_queue_pressure;
      mean_route += row->route_score;
      mean_lag += std::max(0.0, row->event_time - row->projected_arrival);
    }
    mean_age /= 2.0;
    mean_slack /= 2.0;
    mean_service /= 2.0;
    mean_pressure /= 2.0;
    mean_route /= 2.0;
    mean_lag /= 2.0;
    for (const auto* row : first) {
      const auto& feature = row->model_features;
      const double lag =
          std::max(0.0, row->event_time - row->projected_arrival);
      const double lead =
          std::max(0.0, row->projected_arrival - row->event_time);
      checks.require(
          row->model_feature_contract == "MERGE_TRACE_LOCAL_V1" &&
              std::abs(feature[0] - lag) < 1.0e-12 &&
              std::abs(feature[1] - lead) < 1.0e-12 &&
              std::abs(feature[2] - row->deadline_slack) < 1.0e-12 &&
              std::abs(feature[3] - row->wait_age) < 1.0e-12 &&
              std::abs(feature[4] - row->destination_service_seconds) <
                  1.0e-12 &&
              std::abs(feature[5] - row->downstream_queue_pressure) <
                  1.0e-12 &&
              std::abs(feature[6] - row->route_score) < 1.0e-12 &&
              std::abs(feature[7] - row->static_remaining) < 1.0e-12 &&
              std::abs(feature[8] - row->task_class_code) < 1.0e-12 &&
              std::abs(feature[9] - row->task_class) < 1.0e-12 &&
              feature[10] == (row->storage_leg ? 1.0 : 0.0) &&
              feature[11] == 2.0 &&
              std::abs(feature[12] - (row->wait_age - mean_age)) <
                  1.0e-12 &&
              std::abs(feature[13] -
                       (row->deadline_slack - mean_slack)) < 1.0e-12 &&
              std::abs(feature[14] -
                       (row->destination_service_seconds - mean_service)) <
                  1.0e-12 &&
              std::abs(feature[15] -
                       (row->downstream_queue_pressure - mean_pressure)) <
                  1.0e-12 &&
              std::abs(feature[16] - (row->route_score - mean_route)) <
                  1.0e-12 &&
              std::abs(feature[17] - (lag - mean_lag)) < 1.0e-12 &&
              row->model_score_available &&
              std::abs(row->model_score - policy.score(feature)) < 1.0e-12,
          "native trace must exactly expose the frozen 18D row and affine score");
    }
  }
}

void test_learned_policy_fail_closed_gates(Checks& checks) {
  auto shadow = valid_test_policy("shadow");
  const auto shadow_result = run_with_policy(shadow);
  const auto shadow_first = first_opportunity_rows(shadow_result);
  checks.require(
      shadow_result.summary.g4irsf18_merge_model_applied_count == 0 &&
          shadow_result.summary.g4irsf18_merge_shadow_fallback_count >= 1 &&
          !shadow_first.empty() &&
          shadow_first.front()->chosen_winner_request_id ==
              shadow_first.front()->model_baseline_request_id,
      "shadow must score and propose without changing J2");

  auto invalid = valid_test_policy();
  invalid.schema = "wrong";
  const auto invalid_result = run_with_policy(invalid);
  checks.require(
      !invalid_result.summary.g4irsf18_merge_artifact_valid &&
          invalid_result.summary.g4irsf18_merge_model_invalid_count >= 1 &&
          invalid_result.summary.g4irsf18_merge_j2_fallback_count >= 1,
      "semantic artifact mismatch must be observable and fall back to J2");

  auto killed = valid_test_policy();
  killed.kill_switch = true;
  const auto killed_result = run_with_policy(killed);
  checks.require(
      killed_result.summary.g4irsf18_merge_kill_switch_tripped &&
          killed_result.summary.g4irsf18_merge_kill_switch_trip_count == 1 &&
          killed_result.summary.g4irsf18_merge_kill_switch_fallback_count >= 1 &&
          killed_result.summary.g4irsf18_merge_model_applied_count == 0,
      "explicit kill switch must immediately and persistently restore J2");

  auto no_coverage = valid_test_policy();
  no_coverage.coverage_cap = 0.0;
  const auto no_coverage_result = run_with_policy(no_coverage);
  checks.require(
      no_coverage_result.summary.g4irsf18_merge_coverage_cap_fallback_count >=
              1 &&
          no_coverage_result.summary.g4irsf18_merge_model_applied_count == 0,
      "zero deterministic coverage must prevent every model action");

  auto no_overrides = valid_test_policy();
  no_overrides.max_overrides_per_segment = 0;
  const auto no_overrides_result = run_with_policy(no_overrides);
  checks.require(
      no_overrides_result.summary.g4irsf18_merge_override_cap_fallback_count >=
              1 &&
          no_overrides_result.summary.g4irsf18_merge_model_applied_count == 0,
      "zero per-segment override cap must preserve J2");

  auto production = valid_test_policy("production_closed_loop");
  production.research_closed_loop_authorized = false;
  production.fixed_research_workload = false;
  production.production_closed_loop_authorized = true;
  production.offline_gate_passed = true;
  const auto production_result = run_with_policy(production);
  checks.require(
      production_result.summary.g4irsf18_merge_model_applied_count == 0 &&
          production_result.summary
                  .g4irsf18_merge_authorization_fallback_count >= 1 &&
          !production_result.summary
               .g4irsf18_merge_artifact_production_closed_loop_authorized,
      "research-only artifact must not self-promote even with runtime grants");

  auto tie = valid_test_policy();
  std::fill(tie.weights.begin(), tie.weights.end(), 0.0);
  const auto tie_result = run_with_policy(tie);
  const auto tie_first = first_opportunity_rows(tie_result);
  checks.require(
      tie_result.summary.g4irsf18_merge_tie_fifo_fallback_count >= 1 &&
          tie_result.summary.g4irsf18_merge_model_applied_count == 0 &&
          !tie_first.empty() &&
          tie_first.front()->chosen_winner_request_id ==
              tie_first.front()->baseline_winner_request_id,
      "finite in-contract score equality must abstain to FIFO only");
}

void test_feature_batch_marks_ood_and_invalid(Checks& checks) {
  std::vector<czr005::ics::DestinationMergeRequest> requests(17);
  std::vector<const czr005::ics::DestinationMergeRequest*> candidates;
  for (std::size_t index = 0; index < requests.size(); ++index) {
    auto& request = requests[index];
    request.projected_arrival = 1.0;
    request.deadline_slack = 10.0;
    request.destination_service_seconds = 1.0;
    request.route_score = 0.0;
    request.static_remaining = 1.0;
    candidates.push_back(&request);
  }
  const auto ood =
      czr005::ics::g4irsf18_merge_feature_batch(candidates, 0.0);
  checks.require(ood.out_of_distribution && !ood.invalid,
                 "candidate cardinality above 16 must be OOD");
  requests.front().projected_arrival =
      std::numeric_limits<double>::quiet_NaN();
  const auto invalid =
      czr005::ics::g4irsf18_merge_feature_batch(candidates, 0.0);
  checks.require(invalid.invalid,
                 "non-finite raw local feature must be invalid");
}

}  // namespace

int main() {
  Checks checks;
  test_jit_fifo_retains_loser(checks);
  test_jit_deadline_aging_mutates_real_choice(checks);
  test_pending_fault_revalidates_generation(checks);
  test_default_eager_compatibility(checks);
  test_learned_policy_research_closed_loop_and_feature_parity(checks);
  test_learned_policy_fail_closed_gates(checks);
  test_feature_batch_marks_ood_and_invalid(checks);
  if (checks.failures != 0) {
    std::cerr << checks.failures << " G4IRSF18 JIT merge checks failed\n";
    return 1;
  }
  std::cout << "G4IRSF18 JIT destination merge checks passed\n";
  return 0;
}
