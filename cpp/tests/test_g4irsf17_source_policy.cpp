#include <algorithm>
#include <array>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"
#include "ics_core/runtime/g4irsf17_source_policy.hpp"

#ifndef CZR005_SOURCE_DIR
#error "CZR005_SOURCE_DIR must identify the repository root"
#endif

namespace {

using czr005::ics::EventDrivenJunctionConfig;
using czr005::ics::EventDrivenJunctionRuntime;
using czr005::ics::EventRuntimeBagRequest;
using czr005::ics::G4IRSF17SourceCandidateObservation;
using czr005::ics::G4IRSF17SourceContextObservation;
using czr005::ics::G4IRSF17SourcePolicyConfig;

struct Checks {
  int failures = 0;
  void require(bool value, const std::string& message) {
    if (!value) {
      ++failures;
      std::cerr << "FAIL: " << message << '\n';
    }
  }
};

const czr005::ics::Graph& canonical_graph() {
  static const auto fixture = [] {
    const auto path = std::filesystem::path(CZR005_SOURCE_DIR) /
                      "data" / "processed" / "maps" / "map2.json";
    return czr005::ics::read_canonical_map2_json(path);
  }();
  return fixture.graph;
}

G4IRSF17SourcePolicyConfig rule_config(const std::string& mode) {
  G4IRSF17SourcePolicyConfig config;
  config.mode = mode;
  config.schema = czr005::ics::kG4IRSF17SourcePolicySchema;
  config.kind = "localized_thesis_rule";
  config.authorized = true;
  config.supervisor_authorized = true;
  config.top_k = 2;
  return config;
}

G4IRSF17SourcePolicyConfig learned_config() {
  G4IRSF17SourcePolicyConfig config;
  config.mode = "closed_loop";
  config.schema = czr005::ics::kG4IRSF17SourcePolicySchema;
  config.kind = "pairwise_ensemble_selective";
  config.artifact_set_id = "g4irsf17-i1-native-test-set";
  config.authorized = true;
  config.runtime_closed_loop_authorized = true;
  config.supervisor_authorized = true;
  config.top_k = 2;
  const auto names = czr005::ics::g4irsf17_source_pairwise_feature_names();
  config.feature_names.assign(names.begin(), names.end());
  config.feature_lower.assign(names.size(), -1.0e6);
  config.feature_upper.assign(names.size(), 1.0e6);
  config.calibration_ece = 0.01;
  for (int index = 0; index < 3; ++index) {
    czr005::ics::G4IRSF17StandardizedLinearMember benefit;
    benefit.family = "pairwise_linear_logistic";
    benefit.objective = "logistic";
    benefit.feature_names.assign(names.begin(), names.end());
    benefit.mean.assign(names.size(), 0.0);
    benefit.scale.assign(names.size(), 1.0);
    benefit.weights.assign(names.size(), 0.0);
    benefit.bias = 2.0;
    auto harmful = benefit;
    harmful.bias = -5.0;
    auto utility = benefit;
    utility.family = "linear_ridge_utility";
    utility.objective.clear();
    utility.bias = 1.0;
    config.benefit_members.push_back(std::move(benefit));
    config.harmful_members.push_back(std::move(harmful));
    config.utility_members.push_back(std::move(utility));
    config.benefit_calibrators.push_back({1.0, 0.0});
    config.harmful_calibrators.push_back({1.0, 0.0});
  }
  return config;
}

void check_exact_feature_order(Checks& checks) {
  constexpr std::array<const char*, 39> expected{{
      "delta_candidate_local_rank",
      "delta_candidate_deadline_slack_seconds",
      "delta_candidate_wait_age_seconds",
      "delta_candidate_leg_priority",
      "delta_candidate_repair_priority",
      "delta_deadline_slack_delta_to_baseline_seconds",
      "delta_wait_age_delta_to_baseline_seconds",
      "delta_leg_priority_delta_to_baseline",
      "delta_urgency_delta_to_granted_seconds",
      "delta_wait_delta_to_granted_seconds",
      "source_queue_length",
      "source_queue_capacity",
      "source_queue_utilization",
      "source_queue_generation_delta",
      "release_count_10s",
      "release_count_30s",
      "release_count_60s",
      "admission_count_10s",
      "admission_count_30s",
      "admission_count_60s",
      "queue_slope_10s",
      "queue_slope_30s",
      "queue_slope_60s",
      "first_edge_credit_slack_seconds",
      "target_queue_length",
      "target_queue_capacity",
      "target_queue_utilization",
      "target_scheduled_incoming",
      "estimated_service_rate_60s",
      "drain_slope_60s",
      "service_weighted_pressure",
      "one_hop_ttl_pressure",
      "two_hop_ttl_pressure",
      "merge_pending_count",
      "merge_oldest_request_age_seconds",
      "merge_token_generation_delta",
      "time_to_next_service_opportunity_seconds",
      "recent_incoming_grants_60s",
      "incoming_grant_imbalance_60s",
  }};
  const auto observed =
      czr005::ics::g4irsf17_source_pairwise_feature_names();
  for (std::size_t index = 0; index < expected.size(); ++index) {
    checks.require(std::string(observed[index]) == expected[index],
                   "native 39-feature order must match the Python schema");
  }

  G4IRSF17SourceCandidateObservation baseline;
  baseline.local_rank = 0;
  baseline.deadline_slack_seconds = 20.0;
  baseline.wait_age_seconds = 2.0;
  G4IRSF17SourceCandidateObservation alternative;
  alternative.local_rank = 1;
  alternative.deadline_slack_seconds = 5.0;
  alternative.wait_age_seconds = 8.0;
  alternative.leg_priority = 2;
  alternative.repair_priority = true;
  G4IRSF17SourceContextObservation context;
  context.source_queue_length = 2.0;
  context.incoming_grant_imbalance_60s = 7.0;
  const auto values = czr005::ics::g4irsf17_pairwise_features(
      alternative, baseline, context);
  checks.require(values[0] == 1.0 && values[1] == -15.0 &&
                     values[2] == 6.0 && values[4] == 1.0,
                 "candidate deltas must occupy the first ten exact slots");
  checks.require(values[10] == 2.0 && values[38] == 7.0,
                 "shared local context must occupy the final 29 slots");
}

void check_rule_and_selective_gates(Checks& checks) {
  G4IRSF17SourceCandidateObservation baseline;
  baseline.local_rank = 0;
  baseline.deadline_slack_seconds = 100.0;
  baseline.wait_age_seconds = 1.0;
  G4IRSF17SourceCandidateObservation alternative;
  alternative.local_rank = 1;
  alternative.deadline_slack_seconds = 10.0;
  alternative.wait_age_seconds = 20.0;
  G4IRSF17SourceContextObservation context;
  context.source_queue_capacity = 8.0;
  context.target_queue_capacity = 8.0;

  const auto rule = czr005::ics::g4irsf17_decide_source_front(
      rule_config("closed_loop"), {baseline, alternative}, context, true);
  checks.require(rule.activated && rule.chosen_index == 1 &&
                     rule.reason == "ACTIVATE_LOCALIZED_RULE",
                 "localized thesis rule must change only the source winner");

  auto learned = learned_config();
  const auto activated = czr005::ics::g4irsf17_decide_source_front(
      learned, {baseline, alternative}, context, true);
  checks.require(activated.activated && activated.chosen_index == 1 &&
                     activated.reason == "ACTIVATE_PAIRWISE_ENSEMBLE" &&
                     activated.benefit_probability_lcb > 0.8 &&
                     activated.harmful_probability_ucb < 0.01,
                 "authorized in-envelope learned policy must activate");

  learned.feature_upper[2] = 1.0;
  const auto ood = czr005::ics::g4irsf17_decide_source_front(
      learned, {baseline, alternative}, context, true);
  checks.require(!ood.activated && ood.chosen_index == 0 &&
                     ood.out_of_distribution && ood.reason == "OOD_GATE",
                 "learned OOD state must fail closed to the baseline");

  learned = learned_config();
  const auto supervisor = czr005::ics::g4irsf17_decide_source_front(
      learned, {baseline, alternative}, context, false);
  checks.require(!supervisor.activated && supervisor.chosen_index == 0 &&
                     supervisor.reason == "SUPERVISOR_GATE",
                 "supervisor veto must fail closed to the baseline");

  learned = learned_config();
  for (auto& member : learned.benefit_members) {
    member.bias = -2.0;
  }
  learned.authorized = false;
  learned.runtime_closed_loop_authorized = false;
  const auto unauthorized_baseline =
      czr005::ics::g4irsf17_decide_source_front(
          learned, {baseline, alternative}, context, true);
  checks.require(
      !unauthorized_baseline.activated &&
          unauthorized_baseline.proposed_index == 0 &&
          unauthorized_baseline.treatment_index == 1 &&
          unauthorized_baseline.chosen_index == 0 &&
          unauthorized_baseline.reason == "ARTIFACT_NOT_AUTHORIZED" &&
          unauthorized_baseline.pairwise_features[0] != 0.0,
      "artifact authorization must be the first learned gate while the "
      "pairwise treatment remains the evaluated non-baseline alternative");
}

EventDrivenJunctionConfig runtime_config() {
  EventDrivenJunctionConfig config;
  config.queue_discipline = "fifo";
  config.event_semantics = "E1";
  config.retry_interval = 0.05;
  config.minimum_service_seconds = 0.25;
  config.max_events = 2000000;
  config.max_simulation_time = 10000.0;
  config.trace_limit = 2000;
  config.local_queue_capacity = 8;
  config.enable_source_admission = false;
  config.admission_mode = "off";
  return config;
}

std::vector<EventRuntimeBagRequest> competitive_pair() {
  return {
      EventRuntimeBagRequest{"g17-a:direct", 1, 0.0, 1000.0, 3, 47,
                             "typed-direct"},
      EventRuntimeBagRequest{"g17-b:storage_out", 2, 0.0, 10.0, 3, 47,
                             "typed-storage"},
  };
}

void check_runtime_source_only_and_off(Checks& checks) {
  auto off_config = runtime_config();
  EventDrivenJunctionRuntime off(canonical_graph(), off_config);
  const auto off_result = off.run(competitive_pair());
  checks.require(off_result.g4irsf17_source_policy_decisions.empty() &&
                     off_result.summary.g4irsf17_source_policy_mode.empty(),
                 "default-off runtime must omit all policy telemetry");

  auto shadow_config = runtime_config();
  shadow_config.g4irsf17_source_policy = rule_config("shadow");
  EventDrivenJunctionRuntime shadow(canonical_graph(), shadow_config);
  const auto shadow_result = shadow.run(competitive_pair());
  checks.require(shadow_result.bags.size() == off_result.bags.size(),
                 "shadow must preserve bag cardinality");
  for (std::size_t index = 0; index < off_result.bags.size(); ++index) {
    const auto& left = off_result.bags[index];
    const auto& right = shadow_result.bags[index];
    checks.require(left.task_id == right.task_id &&
                       left.admitted_time == right.admitted_time &&
                       left.finish_time == right.finish_time &&
                       left.source_queue_delay == right.source_queue_delay &&
                       left.completed == right.completed &&
                       left.failure_reason == right.failure_reason,
                   "shadow must be field-compatible for every bag outcome");
  }
  checks.require(!shadow_result.g4irsf17_source_policy_decisions.empty() &&
                     shadow_result.summary
                             .g4irsf17_source_policy_activation_count == 0,
                 "shadow must observe but never activate");

  auto closed_config = runtime_config();
  closed_config.g4irsf17_source_policy = rule_config("closed_loop");
  EventDrivenJunctionRuntime closed(canonical_graph(), closed_config);
  const auto closed_result = closed.run(competitive_pair());
  checks.require(!closed_result.g4irsf17_source_policy_decisions.empty(),
                 "closed loop must emit a real source-front observation");
  const auto& first = closed_result.g4irsf17_source_policy_decisions.front();
  checks.require(first.activated && first.baseline_queue_index !=
                                         first.chosen_queue_index,
                 "closed-loop rule must change the source queue winner");
  checks.require(first.candidate_features.size() == 2U &&
                     first.context_features.size() == 29U &&
                     first.pairwise_features.size() == 39U,
                 "runtime telemetry must expose paired candidate/context state");
  checks.require(
      closed_result.summary.g4irsf17_source_policy_runtime_global_scan_count ==
              0 &&
          closed_result.summary
                  .g4irsf17_source_policy_future_route_input_count == 0 &&
          closed_result.summary
                  .g4irsf17_source_policy_future_schedule_input_count == 0 &&
          closed_result.summary.g4irsf17_source_policy_full_astar_call_count ==
              0 &&
          closed_result.summary.runtime_full_astar_calls == 0,
      "source control must use zero global/future/A* inputs");
}

}  // namespace

int main() {
  Checks checks;
  check_exact_feature_order(checks);
  check_rule_and_selective_gates(checks);
  check_runtime_source_only_and_off(checks);
  if (checks.failures != 0) {
    std::cerr << checks.failures << " G4IRSF17 source-policy checks failed\n";
    return 1;
  }
  std::cout << "G4IRSF17 source-policy checks passed\n";
  return 0;
}
