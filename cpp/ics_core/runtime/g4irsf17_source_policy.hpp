#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace czr005::ics {

// This seam owns source-front ordering only.  It has no graph, route planner,
// reservation table, task registry, or airport-wide queue input.  The runtime
// supplies at most K=4 candidates and one bounded local context snapshot.
inline constexpr const char* kG4IRSF17SourcePolicySchema =
    "czr005.g4irsf17.source_policy.v1";
inline constexpr const char* kG4IRSF17PairwiseEnsembleSchema =
    "czr005.g4irsf17.i1_pairwise_ensemble.v1";
inline constexpr const char* kG4IRSF17SelectiveGateSchema =
    "czr005.g4irsf17.i1_selective_gate.v1";
inline constexpr std::size_t kG4IRSF17SourceCandidateFeatureCount = 10;
inline constexpr std::size_t kG4IRSF17SourceContextFeatureCount = 29;
inline constexpr std::size_t kG4IRSF17SourcePairwiseFeatureCount =
    kG4IRSF17SourceCandidateFeatureCount +
    kG4IRSF17SourceContextFeatureCount;
inline constexpr std::size_t kG4IRSF17TemporalCounterCapacity = 512;

inline constexpr std::array<const char*,
                            kG4IRSF17SourceCandidateFeatureCount>
    g4irsf17_source_candidate_feature_names() noexcept {
  return {{
      "candidate_local_rank",
      "candidate_deadline_slack_seconds",
      "candidate_wait_age_seconds",
      "candidate_leg_priority",
      "candidate_repair_priority",
      "deadline_slack_delta_to_baseline_seconds",
      "wait_age_delta_to_baseline_seconds",
      "leg_priority_delta_to_baseline",
      "urgency_delta_to_granted_seconds",
      "wait_delta_to_granted_seconds",
  }};
}

inline constexpr std::array<const char*,
                            kG4IRSF17SourceContextFeatureCount>
    g4irsf17_source_context_feature_names() noexcept {
  return {{
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
}

inline constexpr std::array<const char*,
                            kG4IRSF17SourcePairwiseFeatureCount>
    g4irsf17_source_pairwise_feature_names() noexcept {
  std::array<const char*, kG4IRSF17SourcePairwiseFeatureCount> result{{
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
  return result;
}

inline double g4irsf17_finite_clip(double value,
                                  double lower,
                                  double upper) noexcept {
  if (!std::isfinite(value)) {
    return value < 0.0 ? lower : upper;
  }
  return std::max(lower, std::min(value, upper));
}

struct G4IRSF17SourceCandidateObservation {
  int local_rank = 0;
  double deadline_slack_seconds = 0.0;
  double wait_age_seconds = 0.0;
  int leg_priority = 0;
  bool repair_priority = false;

  [[nodiscard]] std::array<double,
                           kG4IRSF17SourceCandidateFeatureCount>
  features_relative_to(
      const G4IRSF17SourceCandidateObservation& baseline) const noexcept {
    const double slack_delta = g4irsf17_finite_clip(
        deadline_slack_seconds - baseline.deadline_slack_seconds,
        -86400.0,
        86400.0);
    const double age_delta = g4irsf17_finite_clip(
        wait_age_seconds - baseline.wait_age_seconds,
        -86400.0,
        86400.0);
    const double leg_delta = g4irsf17_finite_clip(
        static_cast<double>(leg_priority - baseline.leg_priority),
        -4.0,
        4.0);
    // Positive urgency means this candidate has less slack than the granted
    // baseline; positive wait means it has waited longer.
    return {{
        static_cast<double>(local_rank),
        deadline_slack_seconds,
        wait_age_seconds,
        static_cast<double>(leg_priority),
        repair_priority ? 1.0 : 0.0,
        slack_delta,
        age_delta,
        leg_delta,
        -slack_delta,
        age_delta,
    }};
  }
};

struct G4IRSF17SourceContextObservation {
  double source_queue_length = 0.0;
  double source_queue_capacity = 1.0;
  double source_queue_utilization = 0.0;
  double source_queue_generation_delta = 0.0;
  double release_count_10s = 0.0;
  double release_count_30s = 0.0;
  double release_count_60s = 0.0;
  double admission_count_10s = 0.0;
  double admission_count_30s = 0.0;
  double admission_count_60s = 0.0;
  double queue_slope_10s = 0.0;
  double queue_slope_30s = 0.0;
  double queue_slope_60s = 0.0;
  double first_edge_credit_slack_seconds = 0.0;
  double target_queue_length = 0.0;
  double target_queue_capacity = 1.0;
  double target_queue_utilization = 0.0;
  double target_scheduled_incoming = 0.0;
  double estimated_service_rate_60s = 0.0;
  double drain_slope_60s = 0.0;
  double service_weighted_pressure = 0.0;
  double one_hop_ttl_pressure = 0.0;
  double two_hop_ttl_pressure = 0.0;
  double merge_pending_count = 0.0;
  double merge_oldest_request_age_seconds = 0.0;
  double merge_token_generation_delta = 0.0;
  double time_to_next_service_opportunity_seconds = 0.0;
  double recent_incoming_grants_60s = 0.0;
  double incoming_grant_imbalance_60s = 0.0;

  [[nodiscard]] std::array<double, kG4IRSF17SourceContextFeatureCount>
  values() const noexcept {
    std::array<double, kG4IRSF17SourceContextFeatureCount> result{{
        source_queue_length,
        source_queue_capacity,
        source_queue_utilization,
        source_queue_generation_delta,
        release_count_10s,
        release_count_30s,
        release_count_60s,
        admission_count_10s,
        admission_count_30s,
        admission_count_60s,
        queue_slope_10s,
        queue_slope_30s,
        queue_slope_60s,
        first_edge_credit_slack_seconds,
        target_queue_length,
        target_queue_capacity,
        target_queue_utilization,
        target_scheduled_incoming,
        estimated_service_rate_60s,
        drain_slope_60s,
        service_weighted_pressure,
        one_hop_ttl_pressure,
        two_hop_ttl_pressure,
        merge_pending_count,
        merge_oldest_request_age_seconds,
        merge_token_generation_delta,
        time_to_next_service_opportunity_seconds,
        recent_incoming_grants_60s,
        incoming_grant_imbalance_60s,
    }};
    constexpr std::array<double, kG4IRSF17SourceContextFeatureCount> lower{{
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        -4096.0, -4096.0, -4096.0, -3600.0,
        0.0, 1.0, 0.0, 0.0, 0.0, -4096.0,
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -4096.0,
    }};
    constexpr std::array<double, kG4IRSF17SourceContextFeatureCount> upper{{
        4096.0, 4096.0, 1.0, 4096.0,
        4096.0, 4096.0, 4096.0, 4096.0, 4096.0, 4096.0,
        4096.0, 4096.0, 4096.0, 3600.0,
        4096.0, 4096.0, 1.0, 4096.0, 4096.0, 4096.0,
        1000000.0, 1000000.0, 1000000.0, 4096.0, 86400.0,
        4096.0, 3600.0, 4096.0, 4096.0,
    }};
    for (std::size_t index = 0; index < result.size(); ++index) {
      result[index] = g4irsf17_finite_clip(
          result[index], lower[index], upper[index]);
    }
    return result;
  }
};

inline std::array<double, kG4IRSF17SourcePairwiseFeatureCount>
g4irsf17_pairwise_features(
    const G4IRSF17SourceCandidateObservation& proposed,
    const G4IRSF17SourceCandidateObservation& baseline,
    const G4IRSF17SourceContextObservation& context) noexcept {
  const auto left = proposed.features_relative_to(baseline);
  const auto right = baseline.features_relative_to(baseline);
  const auto shared = context.values();
  std::array<double, kG4IRSF17SourcePairwiseFeatureCount> result{};
  for (std::size_t index = 0;
       index < kG4IRSF17SourceCandidateFeatureCount;
       ++index) {
    result[index] = left[index] - right[index];
  }
  for (std::size_t index = 0;
       index < kG4IRSF17SourceContextFeatureCount;
       ++index) {
    result[kG4IRSF17SourceCandidateFeatureCount + index] = shared[index];
  }
  return result;
}

inline std::array<double, kG4IRSF17SourcePairwiseFeatureCount>
g4irsf17_canonical_source_observation(
    const G4IRSF17SourceCandidateObservation& candidate,
    const G4IRSF17SourceCandidateObservation& baseline,
    const G4IRSF17SourceContextObservation& context) noexcept {
  const auto local = candidate.features_relative_to(baseline);
  const auto shared = context.values();
  std::array<double, kG4IRSF17SourcePairwiseFeatureCount> result{};
  std::copy(local.begin(), local.end(), result.begin());
  std::copy(shared.begin(), shared.end(),
            result.begin() +
                static_cast<std::ptrdiff_t>(
                    kG4IRSF17SourceCandidateFeatureCount));
  return result;
}

// Fixed-capacity timestamp history.  Every query is O(512) at worst and the
// history never reaches outside one source/junction controller.
struct G4IRSF17BoundedTimestampCounter {
  std::deque<double> timestamps;

  void record(double now) {
    while (!timestamps.empty() && timestamps.front() < now - 60.0) {
      timestamps.pop_front();
    }
    if (timestamps.size() == kG4IRSF17TemporalCounterCapacity) {
      timestamps.pop_front();
    }
    timestamps.push_back(now);
  }

  [[nodiscard]] int count(double now, double seconds) const noexcept {
    int result = 0;
    const double lower = now - seconds;
    for (auto item = timestamps.rbegin(); item != timestamps.rend(); ++item) {
      if (*item < lower) {
        break;
      }
      ++result;
    }
    return result;
  }
};

struct G4IRSF17SourceTemporalState {
  G4IRSF17BoundedTimestampCounter releases;
  G4IRSF17BoundedTimestampCounter admissions;
  G4IRSF17BoundedTimestampCounter service_completions;
  std::uint64_t last_observed_source_generation = 0;
  std::uint64_t last_observed_merge_generation = 0;
};

struct G4IRSF17StandardizedLinearMember {
  std::string family;
  std::string objective;
  std::vector<std::string> feature_names;
  std::vector<double> mean;
  std::vector<double> scale;
  std::vector<double> weights;
  double bias = 0.0;

  void validate(const char* expected_family,
                bool require_logistic_objective) const {
    const auto expected = g4irsf17_source_pairwise_feature_names();
    if (family != expected_family ||
        (require_logistic_objective && objective != "logistic") ||
        feature_names.size() != expected.size() ||
        mean.size() != expected.size() ||
        scale.size() != expected.size() ||
        weights.size() != expected.size() || !std::isfinite(bias)) {
      throw std::invalid_argument(
          "G4IRSF17 ensemble member schema or dimension mismatch");
    }
    for (std::size_t index = 0; index < expected.size(); ++index) {
      if (feature_names[index] != expected[index] ||
          !std::isfinite(mean[index]) ||
          !std::isfinite(scale[index]) || scale[index] <= 1.0e-12 ||
          !std::isfinite(weights[index])) {
        throw std::invalid_argument(
            "G4IRSF17 ensemble member feature order/normalization is invalid");
      }
    }
  }

  [[nodiscard]] double predict(
      const std::array<double,
                       kG4IRSF17SourcePairwiseFeatureCount>& features) const
      noexcept {
    double result = bias;
    for (std::size_t index = 0; index < features.size(); ++index) {
      result += ((features[index] - mean[index]) / scale[index]) *
                weights[index];
    }
    return result;
  }
};

struct G4IRSF17PlattCalibrator {
  double slope = 0.0;
  double intercept = 0.0;

  void validate() const {
    if (!std::isfinite(slope) || !std::isfinite(intercept)) {
      throw std::invalid_argument(
          "G4IRSF17 Platt calibrator coefficients must be finite");
    }
  }

  [[nodiscard]] double predict(double score) const noexcept {
    const double logit =
        g4irsf17_finite_clip(slope * score + intercept, -40.0, 40.0);
    return 1.0 / (1.0 + std::exp(-logit));
  }
};

struct G4IRSF17SourcePolicyConfig {
  std::string mode = "off";  // off, shadow, closed_loop
  std::string schema;
  std::string kind;  // localized_thesis_rule, pairwise_*_selective
  // Readable identity shared by the pairwise model, selective gate, and
  // native wrapper.  This is deliberately not a hash: it prevents accidental
  // cross-run artifact splicing without reviving heavyweight hash ceremony.
  std::string artifact_set_id;
  bool authorized = false;
  // This is deliberately distinct from the trainer's offline/shadow
  // authorization.  Only a later native/system campaign may set it true.
  bool runtime_closed_loop_authorized = false;
  bool supervisor_authorized = false;
  int top_k = 2;
  double starvation_age_seconds = 60.0;
  double aging_cap_seconds = 300.0;
  std::vector<std::string> feature_names;
  std::vector<double> weights;
  double bias = 0.0;
  std::vector<double> feature_lower;
  std::vector<double> feature_upper;
  double benefit_probability_lcb = 0.0;
  double harmful_probability_ucb = 1.0;
  double utility_lcb_seconds = 0.0;
  double calibration_ece = 1.0;
  double benefit_probability_lcb_min = 0.60;
  double harmful_probability_ucb_max = 0.05;
  double utility_lcb_min_seconds = 0.0;
  double calibration_ece_max = 0.08;
  std::vector<G4IRSF17StandardizedLinearMember> benefit_members;
  std::vector<G4IRSF17StandardizedLinearMember> harmful_members;
  std::vector<G4IRSF17StandardizedLinearMember> utility_members;
  std::vector<G4IRSF17PlattCalibrator> benefit_calibrators;
  std::vector<G4IRSF17PlattCalibrator> harmful_calibrators;
  double utility_residual_q05_seconds = 0.0;
  double lower_quantile = 0.05;
  double upper_quantile = 0.95;
  int minimum_ensemble_size = 3;

  [[nodiscard]] bool enabled() const noexcept { return mode != "off"; }
  [[nodiscard]] bool closed_loop() const noexcept {
    return mode == "closed_loop";
  }

  void validate() const {
    if (mode != "off" && mode != "shadow" && mode != "closed_loop") {
      throw std::invalid_argument(
          "G4IRSF17 source policy mode must be off, shadow, or closed_loop");
    }
    if (mode == "off") {
      if (!schema.empty() || !kind.empty() || !artifact_set_id.empty() ||
          authorized ||
          runtime_closed_loop_authorized ||
          !feature_names.empty() || !weights.empty() ||
          !feature_lower.empty() || !feature_upper.empty() ||
          !benefit_members.empty() || !harmful_members.empty() ||
          !utility_members.empty() || !benefit_calibrators.empty() ||
          !harmful_calibrators.empty()) {
        throw std::invalid_argument(
            "G4IRSF17 source policy artifact requires shadow or closed_loop mode");
      }
      return;
    }
    if (schema != kG4IRSF17SourcePolicySchema) {
      throw std::invalid_argument("G4IRSF17 source policy schema mismatch");
    }
    if (kind != "localized_thesis_rule" &&
        kind != "pairwise_linear_selective" &&
        kind != "pairwise_ensemble_selective") {
      throw std::invalid_argument("G4IRSF17 source policy kind is unsupported");
    }
    if (top_k != 2 && top_k != 4) {
      throw std::invalid_argument("G4IRSF17 source policy top_k must be 2 or 4");
    }
    if (!std::isfinite(starvation_age_seconds) ||
        !std::isfinite(aging_cap_seconds) ||
        starvation_age_seconds <= 0.0 ||
        aging_cap_seconds < starvation_age_seconds) {
      throw std::invalid_argument("G4IRSF17 source policy aging bounds are invalid");
    }
    if (kind == "localized_thesis_rule") {
      if (!artifact_set_id.empty() || !feature_names.empty() ||
          !weights.empty() ||
          !feature_lower.empty() || !feature_upper.empty() ||
          !benefit_members.empty() || !harmful_members.empty() ||
          !utility_members.empty()) {
        throw std::invalid_argument(
            "G4IRSF17 deterministic rule must not carry learned weights");
      }
      return;
    }
    if (kind == "pairwise_linear_selective" && closed_loop()) {
      throw std::invalid_argument(
          "G4IRSF17 single-linear constant-evidence artifact is shadow-only");
    }
    const auto expected = g4irsf17_source_pairwise_feature_names();
    if (feature_names.size() != expected.size() ||
        feature_lower.size() != expected.size() ||
        feature_upper.size() != expected.size() ||
        (kind == "pairwise_linear_selective" &&
         weights.size() != expected.size())) {
      throw std::invalid_argument(
          "G4IRSF17 learned source policy feature dimensions must be 39");
    }
    for (std::size_t index = 0; index < expected.size(); ++index) {
      if (feature_names[index] != expected[index]) {
        throw std::invalid_argument(
            "G4IRSF17 learned source policy feature order mismatch");
      }
      if ((kind == "pairwise_linear_selective" &&
           !std::isfinite(weights[index])) ||
          !std::isfinite(feature_lower[index]) ||
          !std::isfinite(feature_upper[index]) ||
          feature_lower[index] > feature_upper[index]) {
        throw std::invalid_argument(
            "G4IRSF17 learned source policy weights/bounds are invalid");
      }
    }
    const std::array<double, 9> scalars{{
        bias,
        benefit_probability_lcb,
        harmful_probability_ucb,
        utility_lcb_seconds,
        calibration_ece,
        benefit_probability_lcb_min,
        harmful_probability_ucb_max,
        utility_lcb_min_seconds,
        calibration_ece_max,
    }};
    if (!std::all_of(scalars.begin(), scalars.end(), [](double value) {
          return std::isfinite(value);
        }) ||
        benefit_probability_lcb < 0.0 ||
        benefit_probability_lcb > 1.0 ||
        harmful_probability_ucb < 0.0 ||
        harmful_probability_ucb > 1.0 || calibration_ece < 0.0 ||
        calibration_ece > 1.0 || benefit_probability_lcb_min < 0.0 ||
        benefit_probability_lcb_min > 1.0 ||
        harmful_probability_ucb_max < 0.0 ||
        harmful_probability_ucb_max > 1.0 || calibration_ece_max < 0.0 ||
        calibration_ece_max > 1.0) {
      throw std::invalid_argument(
          "G4IRSF17 learned source policy gates are invalid");
    }
    if (kind == "pairwise_linear_selective") {
      if (!artifact_set_id.empty() || !benefit_members.empty() ||
          !harmful_members.empty() ||
          !utility_members.empty() || !benefit_calibrators.empty() ||
          !harmful_calibrators.empty() ||
          runtime_closed_loop_authorized) {
        throw std::invalid_argument(
            "G4IRSF17 diagnostic linear policy cannot carry ensemble authorization");
      }
      return;
    }
    const std::size_t ensemble_size = benefit_members.size();
    if (artifact_set_id.empty() || artifact_set_id.size() > 160U ||
        std::any_of(artifact_set_id.begin(), artifact_set_id.end(),
                    [](char value) {
                      return static_cast<unsigned char>(value) <= 0x20U;
                    }) ||
        ensemble_size == 0U || harmful_members.size() != ensemble_size ||
        utility_members.size() != ensemble_size ||
        benefit_calibrators.size() != ensemble_size ||
        harmful_calibrators.size() != ensemble_size ||
        minimum_ensemble_size < 3 ||
        ensemble_size < static_cast<std::size_t>(minimum_ensemble_size) ||
        !std::isfinite(utility_residual_q05_seconds) ||
        !std::isfinite(lower_quantile) ||
        !std::isfinite(upper_quantile) || lower_quantile < 0.0 ||
        lower_quantile > upper_quantile || upper_quantile > 1.0 ||
        (runtime_closed_loop_authorized && !authorized)) {
      throw std::invalid_argument(
          "G4IRSF17 selective ensemble support/authorization is invalid");
    }
    for (std::size_t index = 0; index < ensemble_size; ++index) {
      benefit_members[index].validate("pairwise_linear_logistic", true);
      harmful_members[index].validate("pairwise_linear_logistic", true);
      utility_members[index].validate("linear_ridge_utility", false);
      benefit_calibrators[index].validate();
      harmful_calibrators[index].validate();
    }
  }
};

struct G4IRSF17SourcePolicyDecision {
  int baseline_index = 0;
  // The non-baseline counterfactual whose pairwise_features are exported.
  // It remains distinct from proposed/chosen when a score or gate keeps Q0.
  int treatment_index = 0;
  int proposed_index = 0;
  int chosen_index = 0;
  bool evaluated = false;
  bool activated = false;
  bool out_of_distribution = false;
  bool supervisor_authorized = false;
  std::string reason = "OFF";
  double model_score = 0.0;
  double benefit_probability_lcb = 0.0;
  double harmful_probability_ucb = 1.0;
  double utility_lcb_seconds = 0.0;
  double calibration_ece = 1.0;
  std::array<double, kG4IRSF17SourcePairwiseFeatureCount>
      pairwise_features{};
};

inline double g4irsf17_linear_quantile(std::vector<double> values,
                                      double probability) {
  if (values.empty() || !std::isfinite(probability) ||
      probability < 0.0 || probability > 1.0 ||
      !std::all_of(values.begin(), values.end(), [](double value) {
        return std::isfinite(value);
      })) {
    throw std::invalid_argument(
        "G4IRSF17 ensemble quantile input is invalid");
  }
  std::sort(values.begin(), values.end());
  const double position =
      probability * static_cast<double>(values.size() - 1U);
  const auto lower = static_cast<std::size_t>(std::floor(position));
  const auto upper = static_cast<std::size_t>(std::ceil(position));
  if (lower == upper) {
    return values[lower];
  }
  const double fraction = position - static_cast<double>(lower);
  return values[lower] + fraction * (values[upper] - values[lower]);
}

inline bool g4irsf17_localized_thesis_less(
    const G4IRSF17SourceCandidateObservation& left,
    const G4IRSF17SourceCandidateObservation& right,
    const G4IRSF17SourcePolicyConfig& config) noexcept {
  const auto key = [&](const G4IRSF17SourceCandidateObservation& item) {
    const double bounded_age =
        std::min(item.wait_age_seconds, config.aging_cap_seconds);
    return std::make_tuple(
        item.repair_priority ? 0 : 1,
        item.wait_age_seconds >= config.starvation_age_seconds ? 0 : 1,
        item.deadline_slack_seconds - bounded_age,
        -item.leg_priority,
        item.local_rank);
  };
  return key(left) < key(right);
}

inline G4IRSF17SourcePolicyDecision g4irsf17_decide_source_front(
    const G4IRSF17SourcePolicyConfig& config,
    const std::vector<G4IRSF17SourceCandidateObservation>& candidates,
    const G4IRSF17SourceContextObservation& context,
    bool runtime_supervisor_authorized) {
  G4IRSF17SourcePolicyDecision decision;
  if (!config.enabled()) {
    return decision;
  }
  decision.evaluated = true;
  decision.supervisor_authorized =
      config.supervisor_authorized && runtime_supervisor_authorized;
  if (candidates.size() < 2U) {
    decision.reason = "TOP_K_SINGLETON";
    return decision;
  }
  if (candidates.size() > static_cast<std::size_t>(config.top_k)) {
    throw std::invalid_argument(
        "G4IRSF17 source policy received more than fixed top_k candidates");
  }

  if (config.kind == "localized_thesis_rule") {
    int proposed = 0;
    for (std::size_t index = 1; index < candidates.size(); ++index) {
      if (g4irsf17_localized_thesis_less(
              candidates[index], candidates[proposed], config)) {
        proposed = static_cast<int>(index);
      }
    }
    decision.proposed_index = proposed;
    int treatment = proposed == 0 ? 1 : proposed;
    if (proposed == 0) {
      for (std::size_t index = 2; index < candidates.size(); ++index) {
        if (g4irsf17_localized_thesis_less(
                candidates[index], candidates[treatment], config)) {
          treatment = static_cast<int>(index);
        }
      }
    }
    decision.treatment_index = treatment;
    decision.pairwise_features = g4irsf17_pairwise_features(
        candidates[treatment], candidates[0], context);
    if (!config.authorized) {
      decision.reason = "ARTIFACT_NOT_AUTHORIZED";
    } else if (proposed == 0) {
      decision.reason = "BASELINE_ALREADY_SELECTED";
    } else if (!decision.supervisor_authorized) {
      decision.reason = "SUPERVISOR_GATE";
    } else if (!config.closed_loop()) {
      decision.reason = "SHADOW_ONLY";
    } else {
      decision.activated = true;
      decision.chosen_index = proposed;
      decision.reason = "ACTIVATE_LOCALIZED_RULE";
    }
    return decision;
  }

  int best = 0;
  double best_score = 0.0;
  std::array<double, kG4IRSF17SourcePairwiseFeatureCount> best_features{};
  std::vector<double> best_benefit_probabilities;
  std::vector<double> best_harmful_probabilities;
  std::vector<double> best_utility_samples;
  for (std::size_t index = 1; index < candidates.size(); ++index) {
    const auto features = g4irsf17_pairwise_features(
        candidates[index], candidates[0], context);
    double score = 0.0;
    std::vector<double> benefit_probabilities;
    std::vector<double> harmful_probabilities;
    std::vector<double> utility_samples;
    if (config.kind == "pairwise_ensemble_selective") {
      benefit_probabilities.reserve(config.benefit_members.size());
      harmful_probabilities.reserve(config.harmful_members.size());
      utility_samples.reserve(config.utility_members.size());
      for (std::size_t member = 0;
           member < config.benefit_members.size(); ++member) {
        benefit_probabilities.push_back(
            config.benefit_calibrators[member].predict(
                config.benefit_members[member].predict(features)));
        harmful_probabilities.push_back(
            config.harmful_calibrators[member].predict(
                config.harmful_members[member].predict(features)));
        utility_samples.push_back(
            config.utility_members[member].predict(features) +
            config.utility_residual_q05_seconds);
      }
      score = std::accumulate(benefit_probabilities.begin(),
                              benefit_probabilities.end(), 0.0) /
              static_cast<double>(benefit_probabilities.size());
    } else {
      score = config.bias;
      for (std::size_t feature = 0; feature < features.size(); ++feature) {
        score += config.weights[feature] * features[feature];
      }
    }
    if (best == 0 || score > best_score) {
      best = static_cast<int>(index);
      best_score = score;
      best_features = features;
      best_benefit_probabilities = std::move(benefit_probabilities);
      best_harmful_probabilities = std::move(harmful_probabilities);
      best_utility_samples = std::move(utility_samples);
    }
  }
  const bool proposes_alternative =
      config.kind == "pairwise_ensemble_selective"
          ? best_score >= 0.5
          : best_score > 0.0;
  decision.proposed_index = proposes_alternative ? best : 0;
  decision.treatment_index = best;
  decision.model_score = best_score;
  decision.pairwise_features = best_features;
  for (std::size_t feature = 0; feature < best_features.size(); ++feature) {
    if (!std::isfinite(best_features[feature]) ||
        best_features[feature] < config.feature_lower[feature] ||
        best_features[feature] > config.feature_upper[feature]) {
      decision.out_of_distribution = true;
      break;
    }
  }
  if (config.kind == "pairwise_ensemble_selective") {
    decision.benefit_probability_lcb = g4irsf17_linear_quantile(
        best_benefit_probabilities, config.lower_quantile);
    decision.harmful_probability_ucb = g4irsf17_linear_quantile(
        best_harmful_probabilities, config.upper_quantile);
    decision.utility_lcb_seconds = g4irsf17_linear_quantile(
        best_utility_samples, config.lower_quantile);
    decision.calibration_ece = config.calibration_ece;
  } else {
    decision.benefit_probability_lcb =
        config.benefit_probability_lcb;
    decision.harmful_probability_ucb =
        config.harmful_probability_ucb;
    decision.utility_lcb_seconds = config.utility_lcb_seconds;
    decision.calibration_ece = config.calibration_ece;
  }
  if (!config.authorized) {
    decision.reason = "ARTIFACT_NOT_AUTHORIZED";
  } else if (decision.proposed_index == 0) {
    decision.reason = "MODEL_KEEPS_BASELINE";
  } else if (config.kind == "pairwise_ensemble_selective" &&
             std::min({best_benefit_probabilities.size(),
                       best_harmful_probabilities.size(),
                       best_utility_samples.size()}) <
                 static_cast<std::size_t>(config.minimum_ensemble_size)) {
    decision.reason = "INSUFFICIENT_ENSEMBLE_SUPPORT";
  } else if (decision.calibration_ece > config.calibration_ece_max) {
    decision.reason = "CALIBRATION_GATE";
  } else if (decision.out_of_distribution) {
    decision.reason = "OOD_GATE";
  } else if (!decision.supervisor_authorized) {
    decision.reason = "SUPERVISOR_GATE";
  } else if (decision.benefit_probability_lcb <
             config.benefit_probability_lcb_min) {
    decision.reason = "BENEFIT_CONFIDENCE_GATE";
  } else if (decision.harmful_probability_ucb >=
             config.harmful_probability_ucb_max) {
    decision.reason = "HARM_BUDGET_GATE";
  } else if (decision.utility_lcb_seconds <=
             config.utility_lcb_min_seconds) {
    decision.reason = "UTILITY_LCB_GATE";
  } else if (!config.closed_loop()) {
    decision.reason =
        config.kind == "pairwise_ensemble_selective"
            ? "SHADOW_WOULD_ACTIVATE"
            : "LEGACY_LINEAR_SHADOW_ONLY";
  } else if (config.kind == "pairwise_ensemble_selective" &&
             !config.runtime_closed_loop_authorized) {
    decision.reason = "RUNTIME_CLOSED_LOOP_NOT_AUTHORIZED";
  } else {
    decision.activated = true;
    decision.chosen_index = decision.proposed_index;
    decision.reason = "ACTIVATE_PAIRWISE_ENSEMBLE";
  }
  return decision;
}

}  // namespace czr005::ics
