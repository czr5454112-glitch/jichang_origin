#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include "ics_core/runtime/destination_merge_grant.hpp"

namespace czr005::ics {

inline constexpr std::size_t kG4IRSF18MergeFeatureCount = 18;
inline constexpr const char* kG4IRSF18MergeFeatureContract =
    "MERGE_TRACE_LOCAL_V1";
inline constexpr const char* kG4IRSF18MergeLinearPolicySchema =
    "czr005.g4irsf18.teacher_counterfactual_linear_merge.v1";
inline constexpr const char* kG4IRSF18MergeLinearPolicyFamily =
    "teacher_warm_start_counterfactual_advantage_affine";

inline const std::array<const char*, kG4IRSF18MergeFeatureCount>&
g4irsf18_merge_feature_names() {
  static const std::array<const char*, kG4IRSF18MergeFeatureCount> names{{
      "arrival_lag_seconds",
      "arrival_lead_seconds",
      "deadline_slack_seconds",
      "wait_age_seconds",
      "destination_service_seconds",
      "downstream_queue_pressure",
      "local_route_score",
      "static_remaining_seconds",
      "task_class_code",
      "task_class_priority",
      "storage_leg",
      "local_candidate_count",
      "wait_age_minus_set_mean_seconds",
      "deadline_slack_minus_set_mean_seconds",
      "service_minus_set_mean_seconds",
      "pressure_minus_set_mean",
      "route_score_minus_set_mean",
      "arrival_lag_minus_set_mean_seconds",
  }};
  return names;
}

inline const std::array<double, kG4IRSF18MergeFeatureCount>&
g4irsf18_merge_feature_lower() {
  static const std::array<double, kG4IRSF18MergeFeatureCount> lower{{
      0.0,
      0.0,
      -86400.0,
      0.0,
      0.0,
      0.0,
      -1000000.0,
      0.0,
      -64.0,
      -64.0,
      0.0,
      2.0,
      -86400.0,
      -172800.0,
      -3600.0,
      -4096.0,
      -2000000.0,
      -86400.0,
  }};
  return lower;
}

inline const std::array<double, kG4IRSF18MergeFeatureCount>&
g4irsf18_merge_feature_upper() {
  static const std::array<double, kG4IRSF18MergeFeatureCount> upper{{
      86400.0,
      86400.0,
      86400.0,
      86400.0,
      3600.0,
      4096.0,
      1000000.0,
      86400.0,
      64.0,
      64.0,
      1.0,
      16.0,
      86400.0,
      172800.0,
      3600.0,
      4096.0,
      2000000.0,
      86400.0,
  }};
  return upper;
}

inline double g4irsf18_clip(double value,
                            double lower,
                            double upper) noexcept {
  return std::min(std::max(value, lower), upper);
}

struct G4IRSF18MergeLinearPolicyConfig {
  std::string mode = "off";
  std::string schema;
  std::string family;
  std::string feature_contract;
  std::string score_direction;
  std::string tie_break;
  std::string tie_break_scope;
  std::string ood_fallback;
  std::string authorization;
  std::vector<std::string> feature_names;
  std::vector<double> mean;
  std::vector<double> scale;
  std::vector<double> weights;
  std::vector<double> feature_lower;
  std::vector<double> feature_upper;
  double bias = 0.0;
  double starvation_threshold_seconds = 120.0;
  bool identity_features_used = false;
  bool outcome_features_used = false;
  bool artifact_production_closed_loop_authorized = false;

  // Runtime grants are deliberately separate from the learned artifact.
  bool research_closed_loop_authorized = false;
  bool fixed_research_workload = false;
  bool production_closed_loop_authorized = false;
  bool offline_gate_passed = false;
  double coverage_cap = 0.05;
  int max_overrides_per_segment = 2;
  bool kill_switch = false;

  [[nodiscard]] bool enabled() const noexcept {
    return mode != "off";
  }

  [[nodiscard]] bool shadow() const noexcept {
    return mode == "shadow";
  }

  [[nodiscard]] bool research_closed_loop() const noexcept {
    return mode == "research_closed_loop";
  }

  [[nodiscard]] bool production_closed_loop() const noexcept {
    return mode == "production_closed_loop";
  }

  void validate_controls() const {
    if (mode != "off" && mode != "shadow" &&
        mode != "research_closed_loop" &&
        mode != "production_closed_loop") {
      throw std::invalid_argument(
          "G4IRSF18 merge policy mode must be off, shadow, "
          "research_closed_loop, or production_closed_loop");
    }
    if (!std::isfinite(coverage_cap) || coverage_cap < 0.0 ||
        coverage_cap > 1.0 || max_overrides_per_segment < 0) {
      throw std::invalid_argument(
          "G4IRSF18 merge coverage cap must be in [0,1] and override cap "
          "must be non-negative");
    }
    if (!enabled() &&
        (!schema.empty() || !family.empty() || !feature_contract.empty() ||
         !score_direction.empty() || !tie_break.empty() ||
         !tie_break_scope.empty() || !ood_fallback.empty() ||
         !authorization.empty() || identity_features_used ||
         outcome_features_used ||
         artifact_production_closed_loop_authorized || bias != 0.0 ||
         !feature_names.empty() || !mean.empty() || !scale.empty() ||
         !weights.empty() || !feature_lower.empty() ||
         !feature_upper.empty() || research_closed_loop_authorized ||
         fixed_research_workload || production_closed_loop_authorized ||
         offline_gate_passed || kill_switch)) {
      throw std::invalid_argument(
          "G4IRSF18 merge artifact and runtime grants require an enabled "
          "policy mode");
    }
  }

  [[nodiscard]] bool artifact_valid() const noexcept {
    if (!enabled() || schema != kG4IRSF18MergeLinearPolicySchema ||
        family != kG4IRSF18MergeLinearPolicyFamily ||
        feature_contract != kG4IRSF18MergeFeatureContract ||
        score_direction != "higher_is_better" || tie_break != "fifo" ||
        tie_break_scope != "finite_in_contract_equal_score_only" ||
        ood_fallback != "J2" ||
        authorization !=
            "RESEARCH_FIXED_WORKLOAD_CANDIDATE_NATIVE_PARITY_REQUIRED" ||
        identity_features_used || outcome_features_used ||
        !std::isfinite(starvation_threshold_seconds) ||
        std::abs(starvation_threshold_seconds - 120.0) > 1.0e-12 ||
        feature_names.size() != kG4IRSF18MergeFeatureCount ||
        mean.size() != kG4IRSF18MergeFeatureCount ||
        scale.size() != kG4IRSF18MergeFeatureCount ||
        weights.size() != kG4IRSF18MergeFeatureCount ||
        feature_lower.size() != kG4IRSF18MergeFeatureCount ||
        feature_upper.size() != kG4IRSF18MergeFeatureCount ||
        !std::isfinite(bias)) {
      return false;
    }
    const auto& expected_names = g4irsf18_merge_feature_names();
    const auto& expected_lower = g4irsf18_merge_feature_lower();
    const auto& expected_upper = g4irsf18_merge_feature_upper();
    for (std::size_t index = 0;
         index < kG4IRSF18MergeFeatureCount; ++index) {
      if (feature_names[index] != expected_names[index] ||
          !std::isfinite(mean[index]) || !std::isfinite(scale[index]) ||
          !std::isfinite(weights[index]) || scale[index] <= 1.0e-12 ||
          !std::isfinite(feature_lower[index]) ||
          !std::isfinite(feature_upper[index]) ||
          std::abs(feature_lower[index] - expected_lower[index]) > 1.0e-12 ||
          std::abs(feature_upper[index] - expected_upper[index]) > 1.0e-12) {
        return false;
      }
    }
    return true;
  }

  [[nodiscard]] double score(
      const std::array<double, kG4IRSF18MergeFeatureCount>& features) const
      noexcept {
    double value = bias;
    for (std::size_t index = 0;
         index < kG4IRSF18MergeFeatureCount; ++index) {
      const double clipped = g4irsf18_clip(
          features[index], feature_lower[index], feature_upper[index]);
      value += weights[index] *
               ((clipped - mean[index]) / scale[index]);
    }
    return value;
  }
};

struct G4IRSF18MergeFeatureRow {
  std::array<double, kG4IRSF18MergeFeatureCount> values{};
  bool out_of_distribution = false;
  bool invalid = false;
};

struct G4IRSF18MergeFeatureBatch {
  std::vector<G4IRSF18MergeFeatureRow> rows;
  bool out_of_distribution = false;
  bool invalid = false;
};

inline G4IRSF18MergeFeatureBatch g4irsf18_merge_feature_batch(
    const std::vector<const DestinationMergeRequest*>& candidates,
    double event_time) {
  G4IRSF18MergeFeatureBatch batch;
  batch.rows.resize(candidates.size());
  const auto& lower = g4irsf18_merge_feature_lower();
  const auto& upper = g4irsf18_merge_feature_upper();
  const auto bounded_base = [&](G4IRSF18MergeFeatureRow& row,
                                std::size_t index,
                                double raw,
                                bool valid_deadline_sentinel = false) {
    if (valid_deadline_sentinel) {
      row.values[index] = upper[index];
      return;
    }
    if (!std::isfinite(raw)) {
      row.invalid = true;
      row.values[index] = 0.0;
      return;
    }
    if (raw < lower[index] || raw > upper[index]) {
      row.out_of_distribution = true;
    }
    row.values[index] = g4irsf18_clip(raw, lower[index], upper[index]);
  };

  for (std::size_t candidate_index = 0;
       candidate_index < candidates.size(); ++candidate_index) {
    auto& row = batch.rows[candidate_index];
    const auto& request = *candidates[candidate_index];
    if (!std::isfinite(event_time) ||
        !std::isfinite(request.projected_arrival)) {
      row.invalid = true;
      row.values[0] = 0.0;
      row.values[1] = 0.0;
    } else {
      bounded_base(row, 0,
                   std::max(0.0, event_time - request.projected_arrival));
      bounded_base(row, 1,
                   std::max(0.0, request.projected_arrival - event_time));
    }
    const bool no_deadline =
        request.deadline_slack == std::numeric_limits<double>::max();
    bounded_base(row, 2, request.deadline_slack, no_deadline);
    bounded_base(row, 3,
                 destination_merge_request_age(request, event_time));
    bounded_base(row, 4, request.destination_service_seconds);
    bounded_base(row, 5,
                 static_cast<double>(request.downstream_queue_pressure));
    bounded_base(row, 6, request.route_score);
    bounded_base(row, 7, request.static_remaining);
    bounded_base(row, 8, static_cast<double>(request.task_class_code));
    bounded_base(row, 9, static_cast<double>(request.task_class));
    bounded_base(row, 10, request.storage_leg ? 1.0 : 0.0);
    bounded_base(row, 11, static_cast<double>(candidates.size()));
  }

  std::array<double, 6> means{};
  constexpr std::array<std::size_t, 6> mean_source{{3, 2, 4, 5, 6, 0}};
  if (!batch.rows.empty()) {
    for (const auto& row : batch.rows) {
      for (std::size_t index = 0; index < mean_source.size(); ++index) {
        means[index] += row.values[mean_source[index]];
      }
    }
    for (double& mean : means) {
      mean /= static_cast<double>(batch.rows.size());
    }
  }
  for (auto& row : batch.rows) {
    row.values[12] = row.values[3] - means[0];
    row.values[13] = row.values[2] - means[1];
    row.values[14] = row.values[4] - means[2];
    row.values[15] = row.values[5] - means[3];
    row.values[16] = row.values[6] - means[4];
    row.values[17] = row.values[0] - means[5];
    for (std::size_t index = 12;
         index < kG4IRSF18MergeFeatureCount; ++index) {
      if (!std::isfinite(row.values[index])) {
        row.invalid = true;
        row.values[index] = 0.0;
      } else if (row.values[index] < lower[index] ||
                 row.values[index] > upper[index]) {
        row.out_of_distribution = true;
        row.values[index] = g4irsf18_clip(
            row.values[index], lower[index], upper[index]);
      }
    }
    batch.invalid = batch.invalid || row.invalid;
    batch.out_of_distribution =
        batch.out_of_distribution || row.out_of_distribution;
  }
  return batch;
}

}  // namespace czr005::ics
