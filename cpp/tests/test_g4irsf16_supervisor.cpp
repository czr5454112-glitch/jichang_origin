#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include "ics_core/runtime/g4irsf16_supervisor.hpp"

namespace {

using namespace czr005::ics;

struct Checks {
  int failures = 0;

  void require(bool condition, const std::string& message) {
    if (!condition) {
      ++failures;
      std::cerr << "FAIL: " << message << '\n';
    }
  }
};

G4IRSF16DecisionContext base_context() {
  G4IRSF16DecisionContext context;
  context.runtime_bag_id = "bag-1";
  context.segment_id = "segment-1";
  context.node = 8;
  context.generation = 3;
  context.physical_fault_generation = 0;
  context.f2_action = 11;
  context.legal_alternatives = {11, 12};
  context.service_opportunity_available = true;
  context.shield_safe = true;
  return context;
}

std::vector<G4IRSF16PibtMove> pibt_batch(
    std::uint64_t fault_generation = 0) {
  return {
      {"bag-1", "segment-1", 8, 12, 3, fault_generation, true, true},
      {"blocker", "blocker-segment", 12, 15, 9, fault_generation, true,
       true},
  };
}

G4IRSF16DecisionContext strict_pibt_context() {
  auto context = base_context();
  context.f2_action = -1;
  context.legal_alternatives.clear();
  context.shield_safe = false;
  context.pibt_requested = true;
  context.pibt_request_source = G4IRSF16PibtRequestSource::kLocalBlocker;
  context.pibt_applicable = true;
  context.pibt_owner_movable = true;
  context.pibt_safe_alternative = true;
  context.pibt_atomic_possible = true;
  context.pibt_batch = pibt_batch();
  return context;
}

G4IRSF16SelectiveLinearModelConfig selective_model_config(
    const std::string& kind = "I4") {
  G4IRSF16SelectiveLinearModelConfig config;
  config.authorized = true;
  config.self_sha256_verified = true;
  config.schema = kG4IRSF16SelectiveModelSchema;
  config.kind = kind;
  config.action = kind == "I4"
                      ? "HOLD_ONE_NATURAL_SERVICE_OPPORTUNITY"
                      : "MOVE_ONE_EDGE_RARE_OVERRIDE";
  config.artifact_sha256 = "fixture-sha256";
  for (const char* name : g4irsf16_deployment_feature_names()) {
    config.feature_names.emplace_back(name);
  }
  config.mean.assign(kG4IRSF16DeploymentFeatureCount, 0.0);
  config.scale.assign(kG4IRSF16DeploymentFeatureCount, 1.0);
  config.feature_min.assign(kG4IRSF16DeploymentFeatureCount, -1.0);
  config.feature_max.assign(kG4IRSF16DeploymentFeatureCount, 1.0);
  const std::size_t width = kG4IRSF16DeploymentFeatureCount + 1U;
  config.benefit_logit = {std::vector<double>(width, 0.0)};
  config.harmful_logit = {std::vector<double>(width, 0.0)};
  config.risk_adjusted_utility_seconds = {
      std::vector<double>(width, 0.0)};
  config.benefit_logit.front().front() = 5.0;
  config.harmful_logit.front().front() = -5.0;
  config.risk_adjusted_utility_seconds.front().front() = 2.0;
  config.benefit_probability_lcb_threshold = 0.90;
  config.harmful_probability_ucb_budget = 0.10;
  config.utility_lcb_margin_seconds = 0.0;
  return config;
}

void test_selective_linear_model_contract(Checks& checks) {
  checks.require(kG4IRSF16DeploymentFeatureCount == 29,
                 "native deployment schema must be the strict 29-feature contract");
  const auto& feature_names = g4irsf16_deployment_feature_names();
  checks.require(
      std::find(feature_names.begin(), feature_names.end(),
                std::string("downstream_pressure")) == feature_names.end() &&
          std::find(feature_names.begin(), feature_names.end(),
                    std::string("has_physical_fault")) == feature_names.end(),
      "unobserved pressure/fault proxies must not remain as model inputs");
  const G4IRSF16SelectiveLinearModel model(selective_model_config());
  const std::vector<double> features(kG4IRSF16DeploymentFeatureCount, 0.0);
  const auto score = model.score(features);
  checks.require(
      score.activation && score.abstention_reason == "ACTIVATE" &&
          !score.ood &&
          std::abs(score.benefit_probability_lcb - 0.9933071490757153) <
              1.0e-12 &&
          std::abs(score.harmful_probability_ucb - 0.006692850924284856) <
              1.0e-12 &&
          score.utility_lcb_seconds == 2.0,
      "native model must mirror the deterministic Python linear ensemble");

  auto ood_features = features;
  ood_features.front() = 2.0;
  const auto ood = model.score(ood_features);
  checks.require(!ood.activation && ood.ood &&
                     ood.abstention_reason == "OOD_ABSTAIN",
                 "out-of-training-bounds input must fail closed");
  checks.require(
      !model.score(std::vector<double>{0.0}).activation &&
          model.score(std::vector<double>{0.0}).abstention_reason ==
              "FEATURE_SCHEMA_FAIL_CLOSED",
      "wrong-sized input must fail closed without partial inference");

  bool rejected = false;
  try {
    auto malformed = selective_model_config();
    malformed.feature_names[0] = "task_id";
    (void)G4IRSF16SelectiveLinearModel(std::move(malformed));
  } catch (const std::invalid_argument&) {
    rejected = true;
  }
  checks.require(rejected,
                 "identity-bearing or reordered model schema must be rejected");
}

void test_h5_diagnostic_rule_contract(Checks& checks) {
  G4IRSF16I4DiagnosticRuleConfig rule;
  rule.authorized = true;
  rule.schema = "czr005.g4irsf16.rule_bundle.v1";
  rule.rule = "H5";
  rule.authorization = "8192_DIAGNOSTIC_ONLY_NOT_PROMOTED";
  rule.artifact_sha256 =
      "865aabd4115b84361e2c73780a8c77f3fb464b0b41bc0c950b2ce05c0a99c96b";
  rule.f2_model_margin_max = 1.518316644839415;
  rule.target_queue_length_min = 0.0;
  rule.target_scheduled_incoming_min = 5.0;
  rule.validate();
  checks.require(rule.activates(1.5, 0, 5) &&
                     !rule.activates(1.6, 0, 5) &&
                     !rule.activates(1.5, 0, 4),
                 "H5 must use only its three preregistered local thresholds");

  auto context = base_context();
  context.i4_proposed = true;
  context.i4_model_authorized = true;
  context.i4_diagnostic_rule = true;
  context.i4_confidence = 1.0;
  context.i4_risk = 0.0;
  const auto decision = G4IRSF16Supervisor().evaluate(context);
  checks.require(
      decision.state == G4IRSF16SupervisorState::kI4SelectiveHold &&
          decision.source ==
              G4IRSF16ActionSource::kI4DiagnosticRule &&
          decision.reason == "i4_diagnostic_rule_gate_pass",
      "H5 action must be auditable as diagnostic rule, never promoted model");
}

void test_names_and_no_astar(Checks& checks) {
  checks.require(!kG4IRSF16FullAstarFallbackAllowed,
                 "full A* fallback must be a compile-time false contract");
  checks.require(
      std::string(g4irsf16_supervisor_state_name(
          G4IRSF16SupervisorState::kF2Normal)) == "F2_NORMAL" &&
          std::string(g4irsf16_supervisor_state_name(
              G4IRSF16SupervisorState::kI4SelectiveHold)) ==
              "I4_SELECTIVE_HOLD" &&
          std::string(g4irsf16_supervisor_state_name(
              G4IRSF16SupervisorState::kI3RareOverride)) ==
              "I3_RARE_OVERRIDE" &&
          std::string(g4irsf16_supervisor_state_name(
              G4IRSF16SupervisorState::kPibtRecovery)) ==
              "PIBT_RECOVERY" &&
          std::string(g4irsf16_supervisor_state_name(
              G4IRSF16SupervisorState::kSafeHold)) == "SAFE_HOLD" &&
          std::string(g4irsf16_supervisor_state_name(
              G4IRSF16SupervisorState::kFaultRecovery)) ==
              "FAULT_RECOVERY",
      "native contract must expose exactly the six preregistered states");

  auto context = base_context();
  context.astar_fallback_requested = true;
  const auto decision = G4IRSF16Supervisor().evaluate(context);
  checks.require(
      decision.state == G4IRSF16SupervisorState::kSafeHold &&
          decision.action == G4IRSF16ActionKind::kSafeHold &&
          decision.reason == "full_astar_fallback_forbidden" &&
          !decision.used_full_astar && decision.selected_next_node == -1,
      "an A* request must fail closed without a planner action");

  context.fault_active = true;
  const auto fault = G4IRSF16Supervisor().evaluate(context);
  checks.require(
      fault.state == G4IRSF16SupervisorState::kFaultRecovery &&
          fault.action == G4IRSF16ActionKind::kFaultHold &&
          !fault.used_full_astar,
      "physical fault recovery must dominate a forbidden A* request");
}

void test_f2_default_and_abstention(Checks& checks) {
  G4IRSF16Supervisor supervisor;
  const auto normal = supervisor.evaluate(base_context());
  checks.require(
      normal.state == G4IRSF16SupervisorState::kF2Normal &&
          normal.action == G4IRSF16ActionKind::kMoveOneEdge &&
          normal.source == G4IRSF16ActionSource::kFrozenF2 &&
          normal.selected_next_node == 11 && normal.has_token,
      "default decision must preserve the exact legal F2 edge");

  auto abstain = base_context();
  abstain.i4_proposed = true;
  abstain.i4_model_authorized = true;
  abstain.i4_confidence = std::numeric_limits<double>::quiet_NaN();
  abstain.i4_risk = 0.0;
  abstain.i3_action = 12;
  abstain.i3_model_authorized = true;
  abstain.i3_confidence = 0.90;
  abstain.i3_risk = 0.0;
  const auto low_confidence = supervisor.evaluate(abstain);
  checks.require(
      low_confidence.state == G4IRSF16SupervisorState::kF2Normal &&
          low_confidence.selected_next_node == 11 &&
          low_confidence.counters.safe_hold_count == 0 &&
          low_confidence.reason.find("confidence") != std::string::npos,
      "unknown/low confidence must abstain to F2 rather than hold");
  checks.require(!supervisor.token_is_current(normal.token, base_context()),
                 "re-evaluation must revoke a previously prepared token");
}

void test_i4_one_natural_opportunity(Checks& checks) {
  G4IRSF16Supervisor supervisor;
  auto context = base_context();
  context.i4_proposed = true;
  context.i4_model_authorized = true;
  context.i4_confidence = 0.99;
  context.i4_risk = 0.001;

  const auto first = supervisor.evaluate(context);
  checks.require(
      first.state == G4IRSF16SupervisorState::kI4SelectiveHold &&
          first.action ==
              G4IRSF16ActionKind::kHoldOneNaturalOpportunity &&
          first.reevaluation_required && first.counters.hold_count == 1,
      "I4 may consume one named natural service opportunity");

  const auto second = supervisor.evaluate(context);
  checks.require(
      second.state == G4IRSF16SupervisorState::kF2Normal &&
          second.selected_next_node == 11 && second.counters.hold_count == 1 &&
          second.reason.find("opportunity_consumed") != std::string::npos,
      "same node/generation must re-evaluate to F2, not hold again");

  ++context.generation;
  const auto next_generation = supervisor.evaluate(context);
  checks.require(
      next_generation.state ==
              G4IRSF16SupervisorState::kI4SelectiveHold &&
          next_generation.counters.hold_count == 2,
      "a new node generation may expose one new natural opportunity");

  auto unavailable = base_context();
  unavailable.i4_proposed = true;
  unavailable.i4_model_authorized = true;
  unavailable.i4_confidence = 1.0;
  unavailable.i4_risk = 0.0;
  unavailable.service_opportunity_available = false;
  const auto preserved = G4IRSF16Supervisor().evaluate(unavailable);
  checks.require(
      preserved.state == G4IRSF16SupervisorState::kF2Normal &&
          preserved.selected_next_node == 11,
      "I4 cannot invent an arbitrary-duration hold without an opportunity");
}

void test_i3_legal_once_no_oscillation(Checks& checks) {
  G4IRSF16Supervisor supervisor;
  auto context = base_context();
  context.i3_action = 12;
  context.i3_model_authorized = true;
  context.i3_confidence = 0.99;
  context.i3_risk = 0.001;
  const auto selected = supervisor.evaluate(context);
  checks.require(
      selected.state == G4IRSF16SupervisorState::kI3RareOverride &&
          selected.selected_next_node == 12 &&
          selected.counters.override_count == 1,
      "authorized high-confidence legal I3 may replace F2 once");

  context.node = 12;
  context.f2_action = 15;
  context.legal_alternatives = {8, 15};
  context.i3_action = 8;
  const auto reverse = supervisor.evaluate(context);
  checks.require(
      reverse.state == G4IRSF16SupervisorState::kF2Normal &&
          reverse.selected_next_node == 15 &&
          reverse.reason.find("oscillation") != std::string::npos &&
          reverse.counters.override_count == 1,
      "I3 latch must block a reverse A-B learned oscillation");

  auto illegal = base_context();
  illegal.i3_action = 99;
  illegal.i3_model_authorized = true;
  illegal.i3_confidence = 1.0;
  illegal.i3_risk = 0.0;
  const auto rejected = G4IRSF16Supervisor().evaluate(illegal);
  checks.require(
      rejected.state == G4IRSF16SupervisorState::kF2Normal &&
          rejected.selected_next_node == 11 &&
          rejected.reason.find("illegal") != std::string::npos,
      "an illegal I3 alternative must fail closed to F2");

  auto risky = base_context();
  risky.i3_action = 12;
  risky.i3_model_authorized = true;
  risky.i3_confidence = 1.0;
  risky.i3_risk = 0.003;
  const auto risk_rejected = G4IRSF16Supervisor().evaluate(risky);
  checks.require(
      risk_rejected.state == G4IRSF16SupervisorState::kF2Normal &&
          risk_rejected.reason.find("risk") != std::string::npos,
      "I3 externality risk above the gate must preserve F2");

  G4IRSF16Supervisor history_supervisor;
  auto prior = base_context();
  prior.f2_action = 12;
  (void)history_supervisor.evaluate(prior);
  auto history_reverse = base_context();
  history_reverse.node = 12;
  history_reverse.f2_action = 15;
  history_reverse.legal_alternatives = {8, 15};
  history_reverse.i3_action = 8;
  history_reverse.i3_model_authorized = true;
  history_reverse.i3_confidence = 1.0;
  history_reverse.i3_risk = 0.0;
  const auto blocked = history_supervisor.evaluate(history_reverse);
  checks.require(blocked.reason.find("oscillation") != std::string::npos,
                 "I3 must not reverse the previous selected edge");
}

void test_pibt_strict_atomic_contract(Checks& checks) {
  G4IRSF16Supervisor supervisor;
  const auto context = strict_pibt_context();
  const auto decision = supervisor.evaluate(context);
  checks.require(
      decision.state == G4IRSF16SupervisorState::kPibtRecovery &&
          decision.action == G4IRSF16ActionKind::kAtomicOneStepBatch &&
          decision.source == G4IRSF16ActionSource::kStrictLocalPibt &&
          decision.atomic() && decision.atomic_batch == context.pibt_batch &&
          decision.counters.pibt_count == 1,
      "strict local-blocker PIBT must return the entire one-step batch");

  auto forged = decision;
  forged.atomic_batch.front().to_node = 99;
  std::vector<G4IRSF16PibtMove> committed;
  checks.require(!supervisor.consume_atomic_batch(forged, context, &committed) &&
                     committed.empty() &&
                     supervisor.token_is_current(decision.token, context),
                 "a token must reject a modified/partial PIBT batch");
  checks.require(
      supervisor.consume_atomic_batch(decision, context, &committed) &&
          committed == context.pibt_batch &&
          !supervisor.consume_atomic_batch(decision, context, &committed),
      "the complete atomic batch may be consumed exactly once");

  auto rejected = strict_pibt_context();
  rejected.pibt_owner_movable = false;
  const auto immovable = G4IRSF16Supervisor().evaluate(rejected);
  checks.require(
      immovable.state == G4IRSF16SupervisorState::kSafeHold &&
          immovable.atomic_batch.empty() && immovable.counters.pibt_count == 0,
      "PIBT with an immovable owner must expose no partial action");

  rejected = strict_pibt_context();
  rejected.pibt_applicable = false;
  checks.require(
      G4IRSF16Supervisor().evaluate(rejected).state ==
          G4IRSF16SupervisorState::kSafeHold,
      "PIBT requires an explicitly applicable local slice");
  rejected = strict_pibt_context();
  rejected.pibt_safe_alternative = false;
  checks.require(
      G4IRSF16Supervisor().evaluate(rejected).state ==
          G4IRSF16SupervisorState::kSafeHold,
      "PIBT requires a shield-safe owner alternative");
  rejected = strict_pibt_context();
  rejected.pibt_atomic_possible = false;
  checks.require(
      G4IRSF16Supervisor().evaluate(rejected).state ==
          G4IRSF16SupervisorState::kSafeHold,
      "PIBT requires an atomic one-step transaction");
  rejected = strict_pibt_context();
  rejected.pibt_batch.clear();
  checks.require(
      G4IRSF16Supervisor().evaluate(rejected).state ==
          G4IRSF16SupervisorState::kSafeHold,
      "PIBT cannot commit an empty transaction");

  rejected = strict_pibt_context();
  rejected.pibt_batch[1].to_node = rejected.pibt_batch[0].to_node;
  const auto collision = G4IRSF16Supervisor().evaluate(rejected);
  checks.require(collision.state == G4IRSF16SupervisorState::kSafeHold &&
                     collision.atomic_batch.empty(),
                 "a colliding PIBT batch must fail atomic validation");

  rejected = strict_pibt_context();
  rejected.pibt_request_source =
      G4IRSF16PibtRequestSource::kModelAbstention;
  const auto model_trigger = G4IRSF16Supervisor().evaluate(rejected);
  checks.require(
      model_trigger.state == G4IRSF16SupervisorState::kSafeHold &&
          model_trigger.reason.find("model_abstention") != std::string::npos,
      "low-confidence/model abstention cannot directly trigger PIBT");

  G4IRSF16Supervisor faulted_transaction;
  const auto prepared = faulted_transaction.evaluate(strict_pibt_context());
  auto pibt_fault = strict_pibt_context();
  pibt_fault.physical_fault_generation = 1;
  pibt_fault.fault_active = true;
  pibt_fault.pibt_batch = pibt_batch(1);
  (void)faulted_transaction.evaluate(pibt_fault);
  committed = prepared.atomic_batch;
  checks.require(
      !faulted_transaction.consume_atomic_batch(prepared, pibt_fault,
                                                 &committed) &&
          committed.empty(),
      "fault during PIBT prepare must revoke the batch without a prefix");
}

void test_fault_stale_and_repair_reset(Checks& checks) {
  G4IRSF16Supervisor supervisor;
  auto context = base_context();
  context.i4_proposed = true;
  context.i4_model_authorized = true;
  context.i4_confidence = 1.0;
  context.i4_risk = 0.0;
  const auto held = supervisor.evaluate(context);
  checks.require(supervisor.token_is_current(held.token, context),
                 "I4 hold token must initially be generation-current");

  auto fault = context;
  fault.physical_fault_generation = 1;
  fault.fault_active = true;
  const auto during_fault = supervisor.evaluate(fault);
  checks.require(
      during_fault.state == G4IRSF16SupervisorState::kFaultRecovery &&
          during_fault.action == G4IRSF16ActionKind::kFaultHold &&
          !during_fault.has_token &&
          !supervisor.token_is_current(held.token, fault),
      "fault activation must revoke a prepared learned action");

  fault.fault_active = false;
  const auto repaired = supervisor.evaluate(fault);
  checks.require(
      repaired.state == G4IRSF16SupervisorState::kF2Normal &&
          repaired.repair_reentry && repaired.selected_next_node == 11 &&
          repaired.counters.repair_reentry_count == 1,
      "repair must re-enter through exact F2 exactly once");
  const auto after_repair = supervisor.evaluate(fault);
  checks.require(
      after_repair.state == G4IRSF16SupervisorState::kF2Normal &&
          after_repair.counters.hold_count == 1 &&
          after_repair.counters.repair_reentry_count == 1,
      "repair must not reset the consumed I4 node-generation latch");

  auto stale = fault;
  stale.physical_fault_generation = 0;
  const auto stale_fault = supervisor.evaluate(stale);
  checks.require(
      stale_fault.state == G4IRSF16SupervisorState::kFaultRecovery &&
          stale_fault.stale_generation_rejected &&
          stale_fault.reason.find("stale_physical") != std::string::npos,
      "stale fault generation must fail closed before any action");

  auto current = fault;
  current.generation = 5;
  (void)supervisor.evaluate(current);
  current.generation = 4;
  const auto stale_node = supervisor.evaluate(current);
  checks.require(
      stale_node.state == G4IRSF16SupervisorState::kFaultRecovery &&
          stale_node.reason.find("stale_node") != std::string::npos,
      "stale node generation must fail closed before any action");

  G4IRSF16Supervisor override_supervisor;
  auto override_context = base_context();
  override_context.i3_action = 12;
  override_context.i3_model_authorized = true;
  override_context.i3_confidence = 1.0;
  override_context.i3_risk = 0.0;
  const auto override_action = override_supervisor.evaluate(override_context);
  override_context.physical_fault_generation = 1;
  override_context.fault_active = true;
  const auto override_fault = override_supervisor.evaluate(override_context);
  checks.require(
      override_fault.state == G4IRSF16SupervisorState::kFaultRecovery &&
          !override_supervisor.token_is_current(override_action.token,
                                                override_context),
      "fault during I3 prepare must revoke the rare-override token");
}

void test_safe_hold_audit_and_segment_latch(Checks& checks) {
  auto no_action = base_context();
  no_action.f2_action = -1;
  no_action.legal_alternatives.clear();
  no_action.shield_safe = false;
  G4IRSF16Supervisor safe_supervisor;
  const auto safe = safe_supervisor.evaluate(no_action);
  checks.require(
      safe.state == G4IRSF16SupervisorState::kSafeHold &&
          safe.action == G4IRSF16ActionKind::kSafeHold &&
          safe.reevaluation_required && safe.counters.safe_hold_count == 1,
      "no safe F2/strict PIBT action must produce an event-driven safe hold");
  checks.require(
      safe_supervisor.audit_log().size() == 1 &&
          safe_supervisor.audit_log().front().reason == safe.reason &&
          safe_supervisor.audit_log().front().to_state == safe.state,
      "each evaluation must append an auditable state/action record");

  G4IRSF16Supervisor segment_supervisor;
  auto first = base_context();
  first.i3_action = 12;
  first.i3_model_authorized = true;
  first.i3_confidence = 1.0;
  first.i3_risk = 0.0;
  checks.require(
      segment_supervisor.evaluate(first).state ==
          G4IRSF16SupervisorState::kI3RareOverride,
      "first segment must accept its one eligible I3 override");
  auto second = first;
  second.segment_id = "segment-2";
  const auto new_segment = segment_supervisor.evaluate(second);
  checks.require(
      new_segment.state == G4IRSF16SupervisorState::kI3RareOverride &&
          new_segment.counters.override_count == 1,
      "a new segment must receive a fresh one-override latch");
  const auto replay = segment_supervisor.evaluate(first);
  checks.require(
      replay.state == G4IRSF16SupervisorState::kFaultRecovery &&
          replay.stale_generation_rejected &&
          replay.reason == "retired_segment_replay_rejected",
      "a retired segment cannot replay to reset its action latch");

  G4IRSF16Supervisor explicit_reset;
  (void)explicit_reset.evaluate(first);
  explicit_reset.reset_for_new_segment("bag-1", "segment-2", 0);
  const auto reset_decision = explicit_reset.evaluate(second);
  checks.require(
      reset_decision.state == G4IRSF16SupervisorState::kI3RareOverride &&
          reset_decision.counters.override_count == 1,
      "explicit reset may clear latches only at a new segment boundary");
  bool same_segment_rejected = false;
  try {
    explicit_reset.reset_for_new_segment("bag-1", "segment-2", 0);
  } catch (const std::invalid_argument&) {
    same_segment_rejected = true;
  }
  checks.require(same_segment_rejected,
                 "explicit reset must reject the active segment identity");
}

void test_invalid_contract_configuration(Checks& checks) {
  bool rejected = false;
  try {
    G4IRSF16SupervisorConfig config;
    config.i3_max_risk = 2.0;
    (void)G4IRSF16Supervisor(config);
  } catch (const std::invalid_argument&) {
    rejected = true;
  }
  checks.require(rejected,
                 "out-of-domain supervisor thresholds must be rejected");

  rejected = false;
  try {
    auto invalid = base_context();
    invalid.runtime_bag_id.clear();
    (void)G4IRSF16Supervisor().evaluate(invalid);
  } catch (const std::invalid_argument&) {
    rejected = true;
  }
  checks.require(rejected,
                 "structurally invalid local context must be rejected");
}

}  // namespace

int main() {
  Checks checks;
  test_selective_linear_model_contract(checks);
  test_h5_diagnostic_rule_contract(checks);
  test_names_and_no_astar(checks);
  test_f2_default_and_abstention(checks);
  test_i4_one_natural_opportunity(checks);
  test_i3_legal_once_no_oscillation(checks);
  test_pibt_strict_atomic_contract(checks);
  test_fault_stale_and_repair_reset(checks);
  test_safe_hold_audit_and_segment_latch(checks);
  test_invalid_contract_configuration(checks);
  if (checks.failures != 0) {
    std::cerr << checks.failures << " G4IRSF16 supervisor checks failed\n";
    return 1;
  }
  std::cout << "G4IRSF16 native supervisor contract passed\n";
  return 0;
}
