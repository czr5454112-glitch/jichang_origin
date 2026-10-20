#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace czr005::ics {

// This contract deliberately has no Graph, reservation-table, A*/CIE, model
// loader, or event-runtime dependency.  The caller materialises one bounded
// local decision context and the supervisor either preserves frozen F2 or
// authorises one explicitly represented selective action.
inline constexpr bool kG4IRSF16FullAstarFallbackAllowed = false;

inline constexpr const char* kG4IRSF16SelectiveModelSchema =
    "czr005.g4irsf16.selective_linear_ensemble.v1";
inline constexpr std::size_t kG4IRSF16DeploymentFeatureCount = 29;

inline const std::array<const char*, kG4IRSF16DeploymentFeatureCount>&
g4irsf16_deployment_feature_names() {
  static const std::array<const char*, kG4IRSF16DeploymentFeatureCount>
      names = {
          "deadline_slack_seconds",
          "wait_age_seconds",
          "current_queue_length",
          "target_queue_length",
          "target_scheduled_incoming",
          "current_next_available_wait_seconds",
          "target_next_available_wait_seconds",
          "alternative_action_count",
          "total_legal_action_count",
          "current_node_out_degree",
          "current_node_type",
          "current_node_service_seconds",
          "baseline_edge_travel_seconds",
          "intervention_edge_travel_seconds",
          "static_remaining_current_seconds",
          "static_remaining_baseline_seconds",
          "static_remaining_intervention_seconds",
          "static_potential_delta_seconds",
          "f2_model_margin",
          "f2_raw_score",
          "recent_visit_count",
          "short_history_repeat_count",
          "storage_in_leg",
          "storage_out_leg",
          "direct_leg",
          "event_hour_sin",
          "event_hour_cos",
          "baseline_release",
          "advertised_fault",
      };
  return names;
}

struct G4IRSF16SelectiveLinearModelConfig {
  bool authorized = false;
  bool self_sha256_verified = false;
  std::string schema;
  std::string kind;
  std::string action;
  std::string artifact_sha256;
  std::vector<std::string> feature_names;
  std::vector<double> mean;
  std::vector<double> scale;
  std::vector<double> feature_min;
  std::vector<double> feature_max;
  std::vector<std::vector<double>> benefit_logit;
  std::vector<std::vector<double>> harmful_logit;
  std::vector<std::vector<double>> risk_adjusted_utility_seconds;
  double benefit_probability_lcb_threshold = 1.0;
  double harmful_probability_ucb_budget = 0.0;
  double utility_lcb_margin_seconds = 0.0;

  [[nodiscard]] bool configured() const noexcept {
    return !schema.empty() || !kind.empty() || !feature_names.empty() ||
           !benefit_logit.empty() || !harmful_logit.empty() ||
           !risk_adjusted_utility_seconds.empty();
  }

  void validate() const {
    if (!authorized || !self_sha256_verified) {
      throw std::invalid_argument(
          "G4IRSF16 selective model requires authorization and verified self SHA256");
    }
    if (schema != kG4IRSF16SelectiveModelSchema ||
        (kind != "I3" && kind != "I4") || action.empty() ||
        artifact_sha256.empty()) {
      throw std::invalid_argument(
          "G4IRSF16 selective model identity/schema is invalid");
    }
    const auto& expected_names = g4irsf16_deployment_feature_names();
    if (feature_names.size() != expected_names.size()) {
      throw std::invalid_argument(
          "G4IRSF16 selective model feature count mismatch");
    }
    for (std::size_t index = 0; index < expected_names.size(); ++index) {
      if (feature_names[index] != expected_names[index]) {
        throw std::invalid_argument(
            "G4IRSF16 selective model feature schema/order mismatch");
      }
    }
    const auto finite_vector = [](const std::vector<double>& values) {
      return std::all_of(values.begin(), values.end(), [](double value) {
        return std::isfinite(value);
      });
    };
    if (mean.size() != expected_names.size() ||
        scale.size() != expected_names.size() ||
        feature_min.size() != expected_names.size() ||
        feature_max.size() != expected_names.size() ||
        !finite_vector(mean) || !finite_vector(scale) ||
        !finite_vector(feature_min) || !finite_vector(feature_max)) {
      throw std::invalid_argument(
          "G4IRSF16 selective model normalization/bounds mismatch");
    }
    for (std::size_t index = 0; index < expected_names.size(); ++index) {
      if (scale[index] <= 0.0 || feature_min[index] > feature_max[index]) {
        throw std::invalid_argument(
            "G4IRSF16 selective model scale/bounds are invalid");
      }
    }
    const auto valid_head = [&](const std::vector<std::vector<double>>& head) {
      return !head.empty() &&
             std::all_of(head.begin(), head.end(), [&](const auto& row) {
               return row.size() == expected_names.size() + 1U &&
                      finite_vector(row);
             });
    };
    if (!valid_head(benefit_logit) || !valid_head(harmful_logit) ||
        !valid_head(risk_adjusted_utility_seconds)) {
      throw std::invalid_argument(
          "G4IRSF16 selective model head is empty/malformed");
    }
    if (!std::isfinite(benefit_probability_lcb_threshold) ||
        benefit_probability_lcb_threshold < 0.0 ||
        benefit_probability_lcb_threshold > 1.0 ||
        !std::isfinite(harmful_probability_ucb_budget) ||
        harmful_probability_ucb_budget < 0.0 ||
        harmful_probability_ucb_budget > 1.0 ||
        !std::isfinite(utility_lcb_margin_seconds)) {
      throw std::invalid_argument(
          "G4IRSF16 selective model thresholds are invalid");
    }
  }
};

struct G4IRSF16SelectiveLinearScore {
  bool activation = false;
  std::string abstention_reason = "FEATURE_SCHEMA_FAIL_CLOSED";
  double benefit_probability_mean = 0.0;
  double benefit_probability_lcb = 0.0;
  double harmful_probability_mean = 1.0;
  double harmful_probability_ucb = 1.0;
  double utility_mean_seconds = -std::numeric_limits<double>::infinity();
  double utility_lcb_seconds = -std::numeric_limits<double>::infinity();
  bool ood = true;
};

class G4IRSF16SelectiveLinearModel {
 public:
  explicit G4IRSF16SelectiveLinearModel(
      G4IRSF16SelectiveLinearModelConfig config)
      : config_(std::move(config)) {
    config_.validate();
  }

  [[nodiscard]] const G4IRSF16SelectiveLinearModelConfig& config() const {
    return config_;
  }

  [[nodiscard]] G4IRSF16SelectiveLinearScore score(
      const std::vector<double>& raw) const {
    G4IRSF16SelectiveLinearScore result;
    if (raw.size() != kG4IRSF16DeploymentFeatureCount ||
        !std::all_of(raw.begin(), raw.end(), [](double value) {
          return std::isfinite(value);
        })) {
      return result;
    }
    result.ood = false;
    std::vector<double> normalized(raw.size(), 0.0);
    for (std::size_t index = 0; index < raw.size(); ++index) {
      result.ood = result.ood || raw[index] < config_.feature_min[index] ||
                   raw[index] > config_.feature_max[index];
      normalized[index] =
          (raw[index] - config_.mean[index]) / config_.scale[index];
    }
    const auto evaluate_head = [&](const auto& rows, bool probability) {
      std::vector<double> values;
      values.reserve(rows.size());
      for (const auto& row : rows) {
        long double value = static_cast<long double>(row.front());
        for (std::size_t index = 0; index < normalized.size(); ++index) {
          value += static_cast<long double>(row[index + 1U]) *
                   static_cast<long double>(normalized[index]);
        }
        double projected = static_cast<double>(value);
        if (probability) {
          if (projected >= 0.0) {
            const double exponent = std::exp(-std::min(projected, 700.0));
            projected = 1.0 / (1.0 + exponent);
          } else {
            const double exponent = std::exp(std::max(projected, -700.0));
            projected = exponent / (1.0 + exponent);
          }
        }
        values.push_back(projected);
      }
      return values;
    };
    const auto mean = [](const std::vector<double>& values) {
      long double total = 0.0L;
      for (const double value : values) {
        total += static_cast<long double>(value);
      }
      return static_cast<double>(total /
                                 static_cast<long double>(values.size()));
    };
    const auto quantile = [](std::vector<double> values, double probability) {
      std::sort(values.begin(), values.end());
      if (values.size() == 1U) {
        return values.front();
      }
      const double position =
          static_cast<double>(values.size() - 1U) * probability;
      const auto lower = static_cast<std::size_t>(std::floor(position));
      const auto upper = static_cast<std::size_t>(std::ceil(position));
      if (lower == upper) {
        return values[lower];
      }
      const double fraction = position - static_cast<double>(lower);
      return values[lower] * (1.0 - fraction) + values[upper] * fraction;
    };
    const auto benefit = evaluate_head(config_.benefit_logit, true);
    const auto harmful = evaluate_head(config_.harmful_logit, true);
    const auto utility =
        evaluate_head(config_.risk_adjusted_utility_seconds, false);
    result.benefit_probability_mean = mean(benefit);
    result.benefit_probability_lcb = quantile(benefit, 0.05);
    result.harmful_probability_mean = mean(harmful);
    result.harmful_probability_ucb = quantile(harmful, 0.95);
    result.utility_mean_seconds = mean(utility);
    result.utility_lcb_seconds = quantile(utility, 0.05);
    result.activation = true;
    result.abstention_reason = "ACTIVATE";
    if (result.ood) {
      result.activation = false;
      result.abstention_reason = "OOD_ABSTAIN";
    } else if (result.benefit_probability_lcb <
               config_.benefit_probability_lcb_threshold) {
      result.activation = false;
      result.abstention_reason = "BENEFIT_CONFIDENCE_ABSTAIN";
    } else if (result.harmful_probability_ucb >
               config_.harmful_probability_ucb_budget) {
      result.activation = false;
      result.abstention_reason = "HARMFUL_RISK_ABSTAIN";
    } else if (result.utility_lcb_seconds <=
               config_.utility_lcb_margin_seconds) {
      result.activation = false;
      result.abstention_reason = "UTILITY_LCB_ABSTAIN";
    }
    return result;
  }

 private:
  G4IRSF16SelectiveLinearModelConfig config_;
};

struct G4IRSF16I4DiagnosticRuleConfig {
  bool authorized = false;
  std::string schema;
  std::string rule;
  std::string authorization;
  std::string artifact_sha256;
  double f2_model_margin_max = 0.0;
  double target_queue_length_min = 0.0;
  double target_scheduled_incoming_min = 0.0;

  [[nodiscard]] bool configured() const noexcept {
    return authorized || !schema.empty() || !rule.empty();
  }

  void validate() const {
    constexpr const char* kAuthorizedSelfSha256 =
        "865aabd4115b84361e2c73780a8c77f3fb464b0b41bc0c950b2ce05c0a99c96b";
    constexpr double kF2ModelMarginMax = 1.518316644839415;
    constexpr double kTargetQueueLengthMin = 0.0;
    constexpr double kTargetScheduledIncomingMin = 5.0;
    if (!authorized ||
        schema != "czr005.g4irsf16.rule_bundle.v1" ||
        rule != "H5" ||
        authorization != "8192_DIAGNOSTIC_ONLY_NOT_PROMOTED" ||
        artifact_sha256 != kAuthorizedSelfSha256 ||
        !std::isfinite(f2_model_margin_max) ||
        !std::isfinite(target_queue_length_min) ||
        !std::isfinite(target_scheduled_incoming_min) ||
        target_queue_length_min < 0.0 ||
        target_scheduled_incoming_min < 0.0 ||
        f2_model_margin_max != kF2ModelMarginMax ||
        target_queue_length_min != kTargetQueueLengthMin ||
        target_scheduled_incoming_min !=
            kTargetScheduledIncomingMin) {
      throw std::invalid_argument(
          "G4IRSF16 H5 requires the explicit diagnostic-only rule bundle");
    }
  }

  [[nodiscard]] bool activates(double f2_model_margin,
                               int target_queue_length,
                               int target_scheduled_incoming) const {
    return std::isfinite(f2_model_margin) &&
           f2_model_margin <= f2_model_margin_max &&
           static_cast<double>(target_queue_length) >=
               target_queue_length_min &&
           static_cast<double>(target_scheduled_incoming) >=
               target_scheduled_incoming_min;
  }
};

enum class G4IRSF16SupervisorState {
  kF2Normal,
  kI4SelectiveHold,
  kI3RareOverride,
  kPibtRecovery,
  kSafeHold,
  kFaultRecovery,
};

inline const char* g4irsf16_supervisor_state_name(
    G4IRSF16SupervisorState state) {
  switch (state) {
    case G4IRSF16SupervisorState::kF2Normal:
      return "F2_NORMAL";
    case G4IRSF16SupervisorState::kI4SelectiveHold:
      return "I4_SELECTIVE_HOLD";
    case G4IRSF16SupervisorState::kI3RareOverride:
      return "I3_RARE_OVERRIDE";
    case G4IRSF16SupervisorState::kPibtRecovery:
      return "PIBT_RECOVERY";
    case G4IRSF16SupervisorState::kSafeHold:
      return "SAFE_HOLD";
    case G4IRSF16SupervisorState::kFaultRecovery:
      return "FAULT_RECOVERY";
  }
  return "UNKNOWN";
}

enum class G4IRSF16ActionKind {
  kMoveOneEdge,
  kHoldOneNaturalOpportunity,
  kAtomicOneStepBatch,
  kSafeHold,
  kFaultHold,
};

inline const char* g4irsf16_action_kind_name(
    G4IRSF16ActionKind action) {
  switch (action) {
    case G4IRSF16ActionKind::kMoveOneEdge:
      return "MOVE_ONE_EDGE";
    case G4IRSF16ActionKind::kHoldOneNaturalOpportunity:
      return "HOLD_ONE_NATURAL_OPPORTUNITY";
    case G4IRSF16ActionKind::kAtomicOneStepBatch:
      return "ATOMIC_ONE_STEP_BATCH";
    case G4IRSF16ActionKind::kSafeHold:
      return "SAFE_HOLD";
    case G4IRSF16ActionKind::kFaultHold:
      return "FAULT_HOLD";
  }
  return "UNKNOWN";
}

enum class G4IRSF16ActionSource {
  kFrozenF2,
  kI4Model,
  kI4DiagnosticRule,
  kI3Model,
  kStrictLocalPibt,
  kLocalSafety,
  kPhysicalFaultShield,
};

inline const char* g4irsf16_action_source_name(
    G4IRSF16ActionSource source) {
  switch (source) {
    case G4IRSF16ActionSource::kFrozenF2:
      return "FROZEN_F2";
    case G4IRSF16ActionSource::kI4Model:
      return "I4_MODEL";
    case G4IRSF16ActionSource::kI4DiagnosticRule:
      return "I4_DIAGNOSTIC_RULE";
    case G4IRSF16ActionSource::kI3Model:
      return "I3_MODEL";
    case G4IRSF16ActionSource::kStrictLocalPibt:
      return "STRICT_LOCAL_PIBT";
    case G4IRSF16ActionSource::kLocalSafety:
      return "LOCAL_SAFETY";
    case G4IRSF16ActionSource::kPhysicalFaultShield:
      return "PHYSICAL_FAULT_SHIELD";
  }
  return "UNKNOWN";
}

enum class G4IRSF16PibtRequestSource {
  kNone,
  kLocalBlocker,
  kModelAbstention,
  kUnknown,
};

struct G4IRSF16SupervisorConfig {
  double i4_min_confidence = 0.90;
  double i4_max_risk = 0.005;
  double i3_min_confidence = 0.95;
  double i3_max_risk = 0.0025;

  void validate() const {
    const double values[] = {i4_min_confidence, i4_max_risk,
                             i3_min_confidence, i3_max_risk};
    for (const double value : values) {
      if (!std::isfinite(value) || value < 0.0 || value > 1.0) {
        throw std::invalid_argument(
            "G4IRSF16 thresholds must be finite and in [0, 1]");
      }
    }
  }
};

struct G4IRSF16PibtMove {
  std::string owner_bag_id;
  std::string segment_id;
  int from_node = -1;
  int to_node = -1;
  std::uint64_t generation = 0;
  std::uint64_t physical_fault_generation = 0;
  bool legal = false;
  bool shield_safe = false;

  [[nodiscard]] bool structurally_valid(
      std::uint64_t expected_fault_generation) const {
    return !owner_bag_id.empty() && !segment_id.empty() && from_node >= 0 &&
           to_node >= 0 && from_node != to_node && legal && shield_safe &&
           physical_fault_generation == expected_fault_generation;
  }
};

inline bool operator==(const G4IRSF16PibtMove& left,
                       const G4IRSF16PibtMove& right) {
  return std::tie(left.owner_bag_id, left.segment_id, left.from_node,
                  left.to_node, left.generation,
                  left.physical_fault_generation, left.legal,
                  left.shield_safe) ==
         std::tie(right.owner_bag_id, right.segment_id, right.from_node,
                  right.to_node, right.generation,
                  right.physical_fault_generation, right.legal,
                  right.shield_safe);
}

inline bool operator!=(const G4IRSF16PibtMove& left,
                       const G4IRSF16PibtMove& right) {
  return !(left == right);
}

struct G4IRSF16DecisionContext {
  std::string runtime_bag_id;
  std::string segment_id;
  int node = -1;
  std::uint64_t generation = 0;
  std::uint64_t physical_fault_generation = 0;
  int f2_action = -1;
  std::vector<int> legal_alternatives;
  bool service_opportunity_available = false;
  bool shield_safe = false;

  bool i4_proposed = false;
  bool i4_model_authorized = false;
  bool i4_diagnostic_rule = false;
  double i4_confidence = std::numeric_limits<double>::quiet_NaN();
  double i4_risk = std::numeric_limits<double>::quiet_NaN();

  int i3_action = -1;
  bool i3_model_authorized = false;
  double i3_confidence = std::numeric_limits<double>::quiet_NaN();
  double i3_risk = std::numeric_limits<double>::quiet_NaN();

  bool pibt_requested = false;
  G4IRSF16PibtRequestSource pibt_request_source =
      G4IRSF16PibtRequestSource::kNone;
  bool pibt_applicable = false;
  bool pibt_owner_movable = false;
  bool pibt_safe_alternative = false;
  bool pibt_atomic_possible = false;
  std::vector<G4IRSF16PibtMove> pibt_batch;

  bool fault_active = false;
  bool astar_fallback_requested = false;

  void validate() const {
    if (runtime_bag_id.empty() || segment_id.empty() || node < 0 ||
        f2_action < -1 || i3_action < -1 ||
        std::any_of(legal_alternatives.begin(), legal_alternatives.end(),
                    [](int candidate) { return candidate < 0; })) {
      throw std::invalid_argument(
          "invalid G4IRSF16 local decision context identity/action");
    }
  }
};

struct G4IRSF16LatchCounters {
  std::uint64_t decision_count = 0;
  std::uint64_t transition_count = 0;
  std::uint64_t activation_count = 0;
  std::uint64_t hold_count = 0;
  std::uint64_t override_count = 0;
  std::uint64_t pibt_count = 0;
  std::uint64_t safe_hold_count = 0;
  std::uint64_t fault_recovery_count = 0;
  std::uint64_t stale_generation_rejection_count = 0;
  std::uint64_t revoked_token_count = 0;
  std::uint64_t repair_reentry_count = 0;
};

struct G4IRSF16ActionToken {
  std::uint64_t token_id = 0;
  std::string runtime_bag_id;
  std::string segment_id;
  int node = -1;
  std::uint64_t generation = 0;
  std::uint64_t physical_fault_generation = 0;
  std::uint64_t state_generation = 0;
  G4IRSF16ActionKind action = G4IRSF16ActionKind::kSafeHold;
  G4IRSF16ActionSource source = G4IRSF16ActionSource::kLocalSafety;
  int selected_next_node = -1;
  std::vector<G4IRSF16PibtMove> atomic_batch;
};

inline bool operator==(const G4IRSF16ActionToken& left,
                       const G4IRSF16ActionToken& right) {
  return std::tie(left.token_id, left.runtime_bag_id, left.segment_id,
                  left.node, left.generation,
                  left.physical_fault_generation, left.state_generation,
                  left.action, left.source, left.selected_next_node,
                  left.atomic_batch) ==
         std::tie(right.token_id, right.runtime_bag_id, right.segment_id,
                  right.node, right.generation,
                  right.physical_fault_generation, right.state_generation,
                  right.action, right.source, right.selected_next_node,
                  right.atomic_batch);
}

struct G4IRSF16SupervisorDecision {
  G4IRSF16SupervisorState state = G4IRSF16SupervisorState::kF2Normal;
  G4IRSF16ActionKind action = G4IRSF16ActionKind::kSafeHold;
  G4IRSF16ActionSource source = G4IRSF16ActionSource::kLocalSafety;
  std::string reason;
  int selected_next_node = -1;
  std::vector<G4IRSF16PibtMove> atomic_batch;
  bool has_token = false;
  G4IRSF16ActionToken token;
  std::uint64_t state_generation = 0;
  G4IRSF16LatchCounters counters;
  bool reevaluation_required = false;
  bool stale_generation_rejected = false;
  bool repair_reentry = false;
  bool used_full_astar = false;

  [[nodiscard]] bool atomic() const {
    return action == G4IRSF16ActionKind::kAtomicOneStepBatch;
  }
};

struct G4IRSF16TransitionRecord {
  std::uint64_t sequence = 0;
  std::string runtime_bag_id;
  std::string segment_id;
  int node = -1;
  std::uint64_t node_generation = 0;
  std::uint64_t physical_fault_generation = 0;
  G4IRSF16SupervisorState from_state =
      G4IRSF16SupervisorState::kF2Normal;
  G4IRSF16SupervisorState to_state =
      G4IRSF16SupervisorState::kF2Normal;
  std::uint64_t state_generation = 0;
  G4IRSF16ActionKind action = G4IRSF16ActionKind::kSafeHold;
  G4IRSF16ActionSource source = G4IRSF16ActionSource::kLocalSafety;
  std::string reason;
  G4IRSF16LatchCounters counters;
};

class G4IRSF16Supervisor {
 public:
  explicit G4IRSF16Supervisor(
      G4IRSF16SupervisorConfig config = {})
      : config_(config) {
    config_.validate();
  }

  [[nodiscard]] G4IRSF16SupervisorDecision evaluate(
      const G4IRSF16DecisionContext& context) {
    context.validate();

    auto existing = bags_.find(context.runtime_bag_id);
    if (existing != bags_.end() &&
        context.segment_id != existing->second.segment_id &&
        seen_segments_[context.runtime_bag_id].count(context.segment_id) !=
            0U) {
      BagState& bag = existing->second;
      const auto from_state = bag.state;
      revoke_tokens(bag);
      ++bag.counters.stale_generation_rejection_count;
      return finish(bag, context, from_state,
                    G4IRSF16SupervisorState::kFaultRecovery,
                    G4IRSF16ActionKind::kFaultHold,
                    G4IRSF16ActionSource::kPhysicalFaultShield,
                    "retired_segment_replay_rejected", -1, {},
                    CountKind::kNone, false, false, true, false);
    }

    BagState& bag = state_for(context);
    const auto from_state = bag.state;
    const std::string stale_reason = stale_generation_reason(bag, context);
    if (!stale_reason.empty()) {
      revoke_tokens(bag);
      ++bag.counters.stale_generation_rejection_count;
      return finish(bag, context, from_state,
                    G4IRSF16SupervisorState::kFaultRecovery,
                    G4IRSF16ActionKind::kFaultHold,
                    G4IRSF16ActionSource::kPhysicalFaultShield,
                    stale_reason, -1, {}, CountKind::kNone, false, false,
                    true, false);
    }

    const auto node_generation = bag.latest_node_generation.find(context.node);
    if (node_generation != bag.latest_node_generation.end() &&
        context.generation > node_generation->second) {
      revoke_tokens(bag);
    }
    if (context.physical_fault_generation >
        bag.physical_fault_generation) {
      revoke_tokens(bag);
      bag.physical_fault_generation = context.physical_fault_generation;
    }
    bag.latest_node_generation[context.node] = context.generation;

    if (context.fault_active) {
      revoke_tokens(bag);
      bag.fault_active = true;
      return finish(bag, context, from_state,
                    G4IRSF16SupervisorState::kFaultRecovery,
                    G4IRSF16ActionKind::kFaultHold,
                    G4IRSF16ActionSource::kPhysicalFaultShield,
                    "physical_fault_active", -1, {},
                    CountKind::kFaultRecovery, false, false, false, false);
    }

    if (bag.fault_active) {
      bag.fault_active = false;
      ++bag.counters.repair_reentry_count;
      revoke_tokens(bag);
      if (f2_executable(context)) {
        return finish(bag, context, from_state,
                      G4IRSF16SupervisorState::kF2Normal,
                      G4IRSF16ActionKind::kMoveOneEdge,
                      G4IRSF16ActionSource::kFrozenF2,
                      "fault_repair_reentry_f2", context.f2_action, {},
                      CountKind::kNone, false, false, false, true);
      }
      return finish(bag, context, from_state,
                    G4IRSF16SupervisorState::kSafeHold,
                    G4IRSF16ActionKind::kSafeHold,
                    G4IRSF16ActionSource::kLocalSafety,
                    "fault_repair_reentry_no_safe_f2", -1, {},
                    CountKind::kSafeHold, false, false, false, true);
    }

    if (context.astar_fallback_requested) {
      revoke_tokens(bag);
      return finish(bag, context, from_state,
                    G4IRSF16SupervisorState::kSafeHold,
                    G4IRSF16ActionKind::kSafeHold,
                    G4IRSF16ActionSource::kLocalSafety,
                    "full_astar_fallback_forbidden", -1, {},
                    CountKind::kSafeHold, false, false, false, false);
    }

    const bool can_run_f2 = f2_executable(context);
    std::string abstention_reason;
    if (context.i4_proposed) {
      const std::string reason = i4_rejection_reason(bag, context, can_run_f2);
      if (reason.empty()) {
        bag.consumed_i4.emplace(context.node, context.generation);
        return finish(bag, context, from_state,
                      G4IRSF16SupervisorState::kI4SelectiveHold,
                      G4IRSF16ActionKind::kHoldOneNaturalOpportunity,
                      context.i4_diagnostic_rule
                          ? G4IRSF16ActionSource::kI4DiagnosticRule
                          : G4IRSF16ActionSource::kI4Model,
                      context.i4_diagnostic_rule
                          ? "i4_diagnostic_rule_gate_pass"
                          : "i4_high_confidence_risk_pass",
                      -1, {},
                      CountKind::kHold, true, true, false, false);
      }
      abstention_reason = reason;
    }

    if (context.i3_action >= 0) {
      const std::string reason = i3_rejection_reason(bag, context, can_run_f2);
      if (reason.empty()) {
        bag.has_i3_override = true;
        bag.i3_override_edge = {context.node, context.i3_action};
        return finish(bag, context, from_state,
                      G4IRSF16SupervisorState::kI3RareOverride,
                      G4IRSF16ActionKind::kMoveOneEdge,
                      G4IRSF16ActionSource::kI3Model,
                      "i3_high_confidence_legal_risk_pass",
                      context.i3_action, {}, CountKind::kOverride, true,
                      false, false, false);
      }
      abstention_reason = reason;
    }

    if (can_run_f2) {
      return finish(bag, context, from_state,
                    G4IRSF16SupervisorState::kF2Normal,
                    G4IRSF16ActionKind::kMoveOneEdge,
                    G4IRSF16ActionSource::kFrozenF2,
                    abstention_reason.empty() ? "f2_default"
                                               : abstention_reason,
                    context.f2_action, {}, CountKind::kNone, false, false,
                    false, false);
    }

    const std::string pibt_reason = pibt_rejection_reason(context);
    if (pibt_reason.empty()) {
      return finish(bag, context, from_state,
                    G4IRSF16SupervisorState::kPibtRecovery,
                    G4IRSF16ActionKind::kAtomicOneStepBatch,
                    G4IRSF16ActionSource::kStrictLocalPibt,
                    "pibt_strict_applicable_atomic_batch", -1,
                    context.pibt_batch, CountKind::kPibt, true, false,
                    false, false);
    }

    const std::string safe_reason =
        !abstention_reason.empty()
            ? abstention_reason
            : (!pibt_reason.empty() ? pibt_reason : "no_legal_f2_action");
    return finish(bag, context, from_state,
                  G4IRSF16SupervisorState::kSafeHold,
                  G4IRSF16ActionKind::kSafeHold,
                  G4IRSF16ActionSource::kLocalSafety, safe_reason, -1, {},
                  CountKind::kSafeHold, false, false, false, false);
  }

  [[nodiscard]] bool token_is_current(
      const G4IRSF16ActionToken& token,
      const G4IRSF16DecisionContext& context) const {
    const auto bag_it = bags_.find(token.runtime_bag_id);
    const auto token_it = tokens_.find(token.token_id);
    return bag_it != bags_.end() && token_it != tokens_.end() &&
           token_it->second == token &&
           bag_it->second.active_tokens.count(token.token_id) != 0U &&
           token.runtime_bag_id == context.runtime_bag_id &&
           token.segment_id == context.segment_id && token.node == context.node &&
           token.generation == context.generation &&
           token.physical_fault_generation ==
               context.physical_fault_generation &&
           token.state_generation == bag_it->second.state_generation &&
           !context.fault_active && !bag_it->second.fault_active;
  }

  bool consume_token(const G4IRSF16ActionToken& token,
                     const G4IRSF16DecisionContext& context) {
    if (!token_is_current(token, context)) {
      return false;
    }
    BagState& bag = bags_.at(token.runtime_bag_id);
    bag.active_tokens.erase(token.token_id);
    tokens_.erase(token.token_id);
    return true;
  }

  bool consume_atomic_batch(const G4IRSF16SupervisorDecision& decision,
                            const G4IRSF16DecisionContext& context,
                            std::vector<G4IRSF16PibtMove>* complete_batch) {
    if (complete_batch != nullptr) {
      complete_batch->clear();
    }
    if (complete_batch == nullptr || !decision.has_token ||
        decision.action != G4IRSF16ActionKind::kAtomicOneStepBatch ||
        decision.atomic_batch.empty() ||
        decision.token.action != decision.action ||
        decision.token.source != decision.source ||
        decision.token.atomic_batch != decision.atomic_batch ||
        !consume_token(decision.token, context)) {
      return false;
    }
    *complete_batch = decision.atomic_batch;
    return true;
  }

  [[nodiscard]] const std::vector<G4IRSF16TransitionRecord>& audit_log() const {
    return audit_;
  }

  [[nodiscard]] const G4IRSF16LatchCounters* counters_for(
      const std::string& runtime_bag_id) const {
    const auto found = bags_.find(runtime_bag_id);
    return found == bags_.end() ? nullptr : &found->second.counters;
  }

  void reset_for_new_segment(
      const std::string& runtime_bag_id,
      const std::string& new_segment_id,
      std::uint64_t physical_fault_generation) {
    if (runtime_bag_id.empty() || new_segment_id.empty()) {
      throw std::invalid_argument(
          "segment reset identities must be non-empty");
    }
    const auto found = bags_.find(runtime_bag_id);
    if (found != bags_.end()) {
      if (found->second.segment_id == new_segment_id) {
        throw std::invalid_argument(
            "cannot reset G4IRSF16 latches within the same segment");
      }
      if (found->second.fault_active) {
        throw std::logic_error(
            "cannot reset G4IRSF16 latches while a fault is active");
      }
      if (physical_fault_generation <
          found->second.physical_fault_generation) {
        throw std::invalid_argument(
            "cannot reset to a stale physical fault generation");
      }
      if (seen_segments_[runtime_bag_id].count(new_segment_id) != 0U) {
        throw std::invalid_argument(
            "cannot reactivate a retired G4IRSF16 segment");
      }
      revoke_tokens(found->second);
    }
    BagState bag;
    bag.segment_id = new_segment_id;
    bag.physical_fault_generation = physical_fault_generation;
    bags_[runtime_bag_id] = std::move(bag);
    seen_segments_[runtime_bag_id].insert(new_segment_id);
  }

 private:
  enum class CountKind {
    kNone,
    kHold,
    kOverride,
    kPibt,
    kSafeHold,
    kFaultRecovery,
  };

  struct BagState {
    std::string segment_id;
    G4IRSF16SupervisorState state =
        G4IRSF16SupervisorState::kF2Normal;
    std::uint64_t state_generation = 0;
    G4IRSF16LatchCounters counters;
    std::set<std::pair<int, std::uint64_t>> consumed_i4;
    bool has_i3_override = false;
    std::pair<int, int> i3_override_edge = {-1, -1};
    bool has_last_selected_edge = false;
    std::pair<int, int> last_selected_edge = {-1, -1};
    std::map<int, std::uint64_t> latest_node_generation;
    std::uint64_t physical_fault_generation = 0;
    bool fault_active = false;
    std::set<std::uint64_t> active_tokens;
  };

  static bool score_at_least(double value, double threshold) {
    return std::isfinite(value) && value >= 0.0 && value <= 1.0 &&
           value >= threshold;
  }

  static bool score_at_most(double value, double threshold) {
    return std::isfinite(value) && value >= 0.0 && value <= 1.0 &&
           value <= threshold;
  }

  static bool contains(const std::vector<int>& values, int value) {
    return std::find(values.begin(), values.end(), value) != values.end();
  }

  static bool f2_executable(const G4IRSF16DecisionContext& context) {
    return context.shield_safe && context.f2_action >= 0 &&
           contains(context.legal_alternatives, context.f2_action);
  }

  std::string i4_rejection_reason(
      const BagState& bag, const G4IRSF16DecisionContext& context,
      bool can_run_f2) const {
    if (!context.i4_model_authorized) {
      return "i4_model_not_authorized_f2_preserved";
    }
    if (!can_run_f2) {
      return "i4_requires_safe_legal_f2";
    }
    if (!context.service_opportunity_available) {
      return "i4_no_natural_service_opportunity_f2_preserved";
    }
    if (bag.consumed_i4.count({context.node, context.generation}) != 0U) {
      return "i4_node_generation_opportunity_consumed_f2_preserved";
    }
    if (!score_at_least(context.i4_confidence,
                        config_.i4_min_confidence)) {
      return "i4_low_or_unknown_confidence_f2_preserved";
    }
    if (!score_at_most(context.i4_risk, config_.i4_max_risk)) {
      return "i4_unknown_or_excess_risk_f2_preserved";
    }
    return {};
  }

  std::string i3_rejection_reason(
      const BagState& bag, const G4IRSF16DecisionContext& context,
      bool can_run_f2) const {
    if (!context.i3_model_authorized) {
      return "i3_model_not_authorized_f2_preserved";
    }
    if (!can_run_f2) {
      return "i3_requires_safe_legal_f2";
    }
    if (bag.has_last_selected_edge &&
        bag.last_selected_edge ==
            std::make_pair(context.i3_action, context.node)) {
      return "i3_reverse_oscillation_blocked_f2_preserved";
    }
    if (bag.has_i3_override) {
      if (bag.i3_override_edge ==
          std::make_pair(context.i3_action, context.node)) {
        return "i3_reverse_oscillation_blocked_f2_preserved";
      }
      return "i3_segment_override_consumed_f2_preserved";
    }
    if (context.i3_action == context.f2_action) {
      return "i3_not_an_alternative_f2_preserved";
    }
    if (context.i3_action == context.node) {
      return "i3_non_movement_action_rejected_f2_preserved";
    }
    if (!contains(context.legal_alternatives, context.i3_action)) {
      return "i3_illegal_alternative_f2_preserved";
    }
    if (!context.shield_safe) {
      return "i3_physical_shield_rejected";
    }
    if (!score_at_least(context.i3_confidence,
                        config_.i3_min_confidence)) {
      return "i3_low_or_unknown_confidence_f2_preserved";
    }
    if (!score_at_most(context.i3_risk, config_.i3_max_risk)) {
      return "i3_unknown_or_excess_risk_f2_preserved";
    }
    return {};
  }

  static bool atomic_batch_valid(
      const std::vector<G4IRSF16PibtMove>& batch,
      std::uint64_t expected_fault_generation) {
    if (batch.empty()) {
      return false;
    }
    std::set<std::string> owners;
    std::set<int> destinations;
    std::set<std::pair<int, int>> edges;
    for (const auto& move : batch) {
      if (!move.structurally_valid(expected_fault_generation) ||
          !owners.insert(move.owner_bag_id).second ||
          !destinations.insert(move.to_node).second) {
        return false;
      }
      edges.emplace(move.from_node, move.to_node);
    }
    return std::none_of(
        edges.begin(), edges.end(), [&](const auto& edge) {
          return edges.count({edge.second, edge.first}) != 0U;
        });
  }

  static std::string pibt_rejection_reason(
      const G4IRSF16DecisionContext& context) {
    if (!context.pibt_requested) {
      return "pibt_not_requested_safe_hold";
    }
    if (context.pibt_request_source !=
        G4IRSF16PibtRequestSource::kLocalBlocker) {
      return "pibt_model_abstention_or_unknown_trigger_rejected";
    }
    if (!context.pibt_applicable) {
      return "pibt_slice_not_applicable";
    }
    if (!context.pibt_owner_movable) {
      return "pibt_owner_not_movable";
    }
    if (!context.pibt_safe_alternative) {
      return "pibt_no_safe_alternative";
    }
    if (!context.pibt_atomic_possible) {
      return "pibt_atomic_batch_not_possible";
    }
    if (!atomic_batch_valid(context.pibt_batch,
                            context.physical_fault_generation)) {
      return "pibt_atomic_batch_validation_failed";
    }
    return {};
  }

  static std::string stale_generation_reason(
      const BagState& bag, const G4IRSF16DecisionContext& context) {
    if (context.physical_fault_generation <
        bag.physical_fault_generation) {
      return "stale_physical_fault_generation_rejected";
    }
    const auto previous = bag.latest_node_generation.find(context.node);
    if (previous != bag.latest_node_generation.end() &&
        context.generation < previous->second) {
      return "stale_node_generation_rejected";
    }
    return {};
  }

  BagState& state_for(const G4IRSF16DecisionContext& context) {
    auto found = bags_.find(context.runtime_bag_id);
    if (found == bags_.end()) {
      BagState bag;
      bag.segment_id = context.segment_id;
      bag.physical_fault_generation = context.physical_fault_generation;
      found = bags_.emplace(context.runtime_bag_id, std::move(bag)).first;
      seen_segments_[context.runtime_bag_id].insert(context.segment_id);
    } else if (found->second.segment_id != context.segment_id) {
      const auto previous_fault_generation =
          found->second.physical_fault_generation;
      const bool previous_fault_active = found->second.fault_active;
      revoke_tokens(found->second);
      BagState bag;
      bag.segment_id = context.segment_id;
      bag.physical_fault_generation = previous_fault_generation;
      bag.fault_active = previous_fault_active;
      found->second = std::move(bag);
      seen_segments_[context.runtime_bag_id].insert(context.segment_id);
    }
    return found->second;
  }

  void revoke_tokens(BagState& bag) {
    const auto revoked = bag.active_tokens.size();
    for (const std::uint64_t token_id : bag.active_tokens) {
      tokens_.erase(token_id);
    }
    bag.active_tokens.clear();
    bag.counters.revoked_token_count += revoked;
  }

  G4IRSF16SupervisorDecision finish(
      BagState& bag, const G4IRSF16DecisionContext& context,
      G4IRSF16SupervisorState from_state,
      G4IRSF16SupervisorState state, G4IRSF16ActionKind action,
      G4IRSF16ActionSource source, std::string reason,
      int selected_next_node, std::vector<G4IRSF16PibtMove> atomic_batch,
      CountKind count_kind, bool activate, bool reevaluation_required,
      bool stale_generation_rejected, bool repair_reentry) {
    // A re-evaluation always invalidates the prior prepared action, even when
    // state/generation values happen to be unchanged.
    revoke_tokens(bag);
    const bool changed = state != bag.state;
    if (changed) {
      ++bag.state_generation;
      ++bag.counters.transition_count;
    }
    bag.state = state;
    ++bag.counters.decision_count;
    if (activate) {
      ++bag.counters.activation_count;
    }
    switch (count_kind) {
      case CountKind::kNone:
        break;
      case CountKind::kHold:
        ++bag.counters.hold_count;
        break;
      case CountKind::kOverride:
        ++bag.counters.override_count;
        break;
      case CountKind::kPibt:
        ++bag.counters.pibt_count;
        break;
      case CountKind::kSafeHold:
        ++bag.counters.safe_hold_count;
        break;
      case CountKind::kFaultRecovery:
        ++bag.counters.fault_recovery_count;
        break;
    }

    if (action == G4IRSF16ActionKind::kMoveOneEdge &&
        selected_next_node >= 0) {
      bag.has_last_selected_edge = true;
      bag.last_selected_edge = {context.node, selected_next_node};
    } else if (action == G4IRSF16ActionKind::kAtomicOneStepBatch) {
      const auto owner_move = std::find_if(
          atomic_batch.begin(), atomic_batch.end(),
          [&](const G4IRSF16PibtMove& move) {
            return move.owner_bag_id == context.runtime_bag_id &&
                   move.segment_id == context.segment_id;
          });
      if (owner_move != atomic_batch.end()) {
        bag.has_last_selected_edge = true;
        bag.last_selected_edge = {owner_move->from_node,
                                  owner_move->to_node};
      }
    }

    G4IRSF16SupervisorDecision decision;
    decision.state = state;
    decision.action = action;
    decision.source = source;
    decision.reason = std::move(reason);
    decision.selected_next_node = selected_next_node;
    decision.atomic_batch = std::move(atomic_batch);
    decision.state_generation = bag.state_generation;
    decision.counters = bag.counters;
    decision.reevaluation_required =
        reevaluation_required ||
        action == G4IRSF16ActionKind::kHoldOneNaturalOpportunity ||
        action == G4IRSF16ActionKind::kSafeHold ||
        action == G4IRSF16ActionKind::kFaultHold;
    decision.stale_generation_rejected = stale_generation_rejected;
    decision.repair_reentry = repair_reentry;
    decision.used_full_astar = false;

    if (action != G4IRSF16ActionKind::kFaultHold) {
      decision.has_token = true;
      decision.token.token_id = next_token_id_++;
      decision.token.runtime_bag_id = context.runtime_bag_id;
      decision.token.segment_id = context.segment_id;
      decision.token.node = context.node;
      decision.token.generation = context.generation;
      decision.token.physical_fault_generation =
          context.physical_fault_generation;
      decision.token.state_generation = bag.state_generation;
      decision.token.action = action;
      decision.token.source = source;
      decision.token.selected_next_node = selected_next_node;
      decision.token.atomic_batch = decision.atomic_batch;
      tokens_[decision.token.token_id] = decision.token;
      bag.active_tokens.insert(decision.token.token_id);
    }

    G4IRSF16TransitionRecord record;
    record.sequence = audit_.size() + 1U;
    record.runtime_bag_id = context.runtime_bag_id;
    record.segment_id = context.segment_id;
    record.node = context.node;
    record.node_generation = context.generation;
    record.physical_fault_generation = context.physical_fault_generation;
    record.from_state = from_state;
    record.to_state = state;
    record.state_generation = bag.state_generation;
    record.action = action;
    record.source = source;
    record.reason = decision.reason;
    record.counters = bag.counters;
    audit_.push_back(std::move(record));
    return decision;
  }

  G4IRSF16SupervisorConfig config_;
  std::map<std::string, BagState> bags_;
  std::map<std::uint64_t, G4IRSF16ActionToken> tokens_;
  std::vector<G4IRSF16TransitionRecord> audit_;
  std::map<std::string, std::set<std::string>> seen_segments_;
  std::uint64_t next_token_id_ = 1;
};

}  // namespace czr005::ics
