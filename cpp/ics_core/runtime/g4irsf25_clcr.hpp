#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace czr005::ics {

// CLCR deliberately keeps a fixed, small feature contract.  Every entry is
// available at the current junction or on one already-materialised legal
// candidate; no route suffix, global queue scan, or future task information is
// part of this vector.
inline constexpr std::size_t kG4IRSF25CLCRFeatureCount = 21U;

inline constexpr const char* kG4IRSF25CLCRFeatureNames[] = {
    "s4_score_delta",
    "travel_time_delta",
    "static_potential_delta",
    "target_queue_delta",
    "target_scheduled_incoming_delta",
    "corridor_wait_delta",
    "target_wait_delta",
    "goal_conditioned_differential_delta",
    "estimated_service_rate_delta",
    "service_weighted_pressure_delta",
    "two_hop_pressure_delta",
    "recent_visit_delta",
    "current_bag_age_seconds",
    "deadline_headroom_seconds",
    "recent_corridor_short_ewma_seconds",
    "recent_corridor_long_ewma_seconds",
    "recent_corridor_trend_seconds",
    "recent_corridor_feedback_age_seconds",
    "recent_corridor_feedback_sample_log1p",
    "recent_corridor_timeout_rate",
    "arm_support_log1p",
};

struct G4IRSF25CLCRArm {
  int branch_node = -1;
  int first_edge = -1;
  int rejoin_node = -1;
  std::vector<int> corridor_nodes;
  int support = 0;           // historic S4 arm evidence; feature only
  int training_support = 0;  // completed paired labels; runtime guard
  double static_duration_seconds = 0.0;
  double t0_system_delta_seconds = 0.0;
  double t0_private_delta_seconds = 0.0;
  double system_intercept = 0.0;
  double private_intercept = 0.0;

  void validate() const {
    if (branch_node < 0 || first_edge < 0 || rejoin_node < 0 ||
        corridor_nodes.empty() || corridor_nodes.size() > 32U || support < 0 ||
        training_support < 0 ||
        !std::isfinite(static_duration_seconds) ||
        static_duration_seconds < 0.0 ||
        !std::isfinite(t0_system_delta_seconds) ||
        !std::isfinite(t0_private_delta_seconds) ||
        !std::isfinite(system_intercept) ||
        !std::isfinite(private_intercept)) {
      throw std::invalid_argument("invalid G4IRSF25 CLCR arm");
    }
    if (std::find(corridor_nodes.begin(), corridor_nodes.end(),
                  branch_node) == corridor_nodes.end() ||
        std::find(corridor_nodes.begin(), corridor_nodes.end(),
                  first_edge) == corridor_nodes.end() ||
        std::find(corridor_nodes.begin(), corridor_nodes.end(),
                  rejoin_node) == corridor_nodes.end()) {
      throw std::invalid_argument(
          "G4IRSF25 corridor_nodes must include branch, first edge, and rejoin");
    }
  }
};

struct G4IRSF25CLCRConfig {
  // off is byte/semantic compatible. observe records real corridor
  // trajectories without changing S4. t0, l1, l2, and l3 may re-rank only
  // registered split/rejoin arms.
  std::string mode = "off";
  bool record_trajectories = false;
  int min_support = 8;
  double margin_seconds = 0.5;
  double private_cap_seconds = 60.0;
  std::string t0_metric = "target_queue_plus_incoming";
  double t0_enter_pressure = std::numeric_limits<double>::infinity();
  double t0_exit_pressure = std::numeric_limits<double>::infinity();
  double l3_short_alpha = 0.20;
  double l3_long_alpha = 0.02;
  double l3_bias_cap_seconds = 30.0;
  double trajectory_max_seconds = 600.0;
  int trajectory_trace_limit = 200000;
  std::vector<double> feature_mean;
  std::vector<double> feature_scale;
  std::vector<double> feature_min;
  std::vector<double> feature_max;
  std::vector<double> system_weights;
  std::vector<double> private_weights;
  std::vector<std::vector<double>> hidden_weights;
  std::vector<double> hidden_bias;
  std::vector<double> hidden_system_weights;
  std::vector<double> hidden_private_weights;
  double hidden_system_bias = 0.0;
  double hidden_private_bias = 0.0;
  std::vector<G4IRSF25CLCRArm> arms;

  [[nodiscard]] bool active() const noexcept {
    return mode == "t0" || mode == "l1" || mode == "l2" || mode == "l3";
  }

  [[nodiscard]] bool observes() const noexcept {
    // L1/L2/T0 use the zero-history snapshot they were trained on and pay no
    // recorder cost.  Only observe runs, explicitly requested traces, and L3
    // need online corridor feedback.
    return mode == "observe" || mode == "l3" || record_trajectories;
  }

  [[nodiscard]] static std::uint64_t key(int branch, int first_edge) noexcept {
    return (static_cast<std::uint64_t>(
                static_cast<std::uint32_t>(branch))
            << 32U) |
           static_cast<std::uint32_t>(first_edge);
  }

  [[nodiscard]] const G4IRSF25CLCRArm* arm(int branch,
                                           int first_edge) const noexcept {
    const auto found = arm_index_.find(key(branch, first_edge));
    return found == arm_index_.end() ? nullptr : &arms[found->second];
  }

  void validate_and_index() {
    if (mode != "off" && mode != "observe" && mode != "t0" &&
        mode != "l1" && mode != "l2" && mode != "l3") {
      throw std::invalid_argument(
          "G4IRSF25 CLCR mode must be off, observe, t0, l1, l2, or l3");
    }
    if (mode == "off" && record_trajectories) {
      throw std::invalid_argument(
          "G4IRSF25 trajectory recording requires observe or an active mode");
    }
    if (min_support < 0 || !std::isfinite(margin_seconds) ||
        margin_seconds < 0.0 || !std::isfinite(private_cap_seconds) ||
        private_cap_seconds < 0.0 ||
        !std::isfinite(l3_short_alpha) || l3_short_alpha <= 0.0 ||
        l3_short_alpha > 1.0 || !std::isfinite(l3_long_alpha) ||
        l3_long_alpha <= 0.0 || l3_long_alpha > 1.0 ||
        !std::isfinite(l3_bias_cap_seconds) ||
        l3_bias_cap_seconds < 0.0 ||
        !std::isfinite(trajectory_max_seconds) ||
        trajectory_max_seconds <= 0.0 || trajectory_max_seconds > 600.0 ||
        trajectory_trace_limit < 0 || trajectory_trace_limit > 1000000 ||
        (active() && min_support == 0)) {
      throw std::invalid_argument("invalid G4IRSF25 CLCR scalar control");
    }
    if (mode == "t0" &&
        (!std::isfinite(t0_enter_pressure) ||
         !std::isfinite(t0_exit_pressure) ||
         t0_exit_pressure > t0_enter_pressure)) {
      throw std::invalid_argument(
          "G4IRSF25 T0 thresholds must be finite with exit <= enter");
    }
    if (t0_metric != "target_queue_plus_incoming" &&
        t0_metric != "service_weighted_pressure" &&
        t0_metric != "corridor_trend") {
      throw std::invalid_argument(
          "G4IRSF25 T0 metric is not one of the three bounded local metrics");
    }
    const auto finite_vector = [](const std::vector<double>& values) {
      return std::all_of(values.begin(), values.end(), [](double value) {
        return std::isfinite(value);
      });
    };
    const auto feature_sized_or_empty = [](const std::vector<double>& values) {
      return values.empty() || values.size() == kG4IRSF25CLCRFeatureCount;
    };
    for (const auto* values : {&feature_mean, &feature_scale, &feature_min,
                               &feature_max, &system_weights,
                               &private_weights}) {
      if (!feature_sized_or_empty(*values) || !finite_vector(*values)) {
        throw std::invalid_argument(
            "G4IRSF25 CLCR feature vectors have the wrong shape");
      }
    }
    if (!feature_scale.empty() &&
        std::any_of(feature_scale.begin(), feature_scale.end(),
                    [](double value) { return value <= 0.0; })) {
      throw std::invalid_argument("G4IRSF25 feature scales must be positive");
    }
    if (feature_mean.empty() != feature_scale.empty() ||
        feature_min.empty() != feature_max.empty()) {
      throw std::invalid_argument(
          "G4IRSF25 normalization and OOD vectors must be supplied in pairs");
    }
    for (std::size_t index = 0; index < feature_min.size(); ++index) {
      if (feature_min[index] > feature_max[index]) {
        throw std::invalid_argument(
            "G4IRSF25 feature minimum exceeds maximum");
      }
    }
    if (mode == "l1" || mode == "l3") {
      if (system_weights.size() != kG4IRSF25CLCRFeatureCount ||
          private_weights.size() != kG4IRSF25CLCRFeatureCount) {
        throw std::invalid_argument(
            "G4IRSF25 L1/L3 require both fixed linear outputs");
      }
    }
    if (mode == "l2") {
      if (hidden_weights.empty() || hidden_weights.size() != hidden_bias.size() ||
          hidden_weights.size() != hidden_system_weights.size() ||
          hidden_weights.size() != hidden_private_weights.size() ||
          hidden_weights.size() > 32U || !finite_vector(hidden_bias) ||
          !finite_vector(hidden_system_weights) ||
          !finite_vector(hidden_private_weights) ||
          !std::isfinite(hidden_system_bias) ||
          !std::isfinite(hidden_private_bias)) {
        throw std::invalid_argument("invalid G4IRSF25 tiny MLP shape");
      }
      for (const auto& row : hidden_weights) {
        if (row.size() != kG4IRSF25CLCRFeatureCount ||
            !finite_vector(row)) {
          throw std::invalid_argument("invalid G4IRSF25 tiny MLP row");
        }
      }
    }
    arm_index_.clear();
    for (std::size_t index = 0; index < arms.size(); ++index) {
      arms[index].validate();
      if (!arm_index_.emplace(
              key(arms[index].branch_node, arms[index].first_edge), index)
               .second) {
        throw std::invalid_argument("duplicate G4IRSF25 branch/arm");
      }
    }
    if ((active() || mode == "observe" || record_trajectories) &&
        arms.empty()) {
      throw std::invalid_argument("active G4IRSF25 CLCR needs corridor arms");
    }
  }

 private:
  std::unordered_map<std::uint64_t, std::size_t> arm_index_;
};

struct G4IRSF25CorridorTrajectoryRow {
  int runtime_bag_id = -1;  // trace-only; never a policy feature
  int task_id = -1;         // trace-only; never a policy feature
  std::string segment_id;   // trace-only; never a policy feature
  std::string leg;
  std::string task_class;
  int goal_node = -1;
  int branch_node = -1;
  int s4_first_edge = -1;
  int selected_first_edge = -1;
  int rejoin_node = -1;
  double decision_time = 0.0;
  double arrival_time = -1.0;
  double actual_corridor_duration = -1.0;
  double private_bag_cost_seconds = -1.0;
  double corridor_wait_seconds = 0.0;
  double local_queue_area_bag_seconds = 0.0;
  double scheduled_incoming_area_bag_seconds = 0.0;
  int peak_local_queue = 0;
  int intermediate_decision_count = 0;
  // This is bounded to the registered local corridor plus a small loop
  // diagnostic allowance.  It is never a future route or full-path cache.
  std::vector<int> actual_path;
  std::vector<double> selected_features;
  int feedback_sample_count = 0;
  double feedback_short_ewma_seconds = 0.0;
  double feedback_long_ewma_seconds = 0.0;
  double feedback_trend_seconds = 0.0;
  double feedback_timeout_rate = 0.0;
  double feedback_short_local_system_cost = 0.0;
  double feedback_long_local_system_cost = 0.0;
  double applied_online_bias = 0.0;
  bool completed_rejoin = false;
  bool timeout = false;
  bool censored = false;
  std::string censor_reason;
  bool loop = false;
  bool safe = true;
};

struct G4IRSF25CLCRPrediction {
  double system_delta_seconds = 0.0;
  double private_delta_seconds = 0.0;
  bool ood = false;
};

inline G4IRSF25CLCRPrediction g4irsf25_clcr_predict(
    const G4IRSF25CLCRConfig& config,
    const G4IRSF25CLCRArm& arm,
    const std::vector<double>& raw_features,
    double online_bias_seconds = 0.0) {
  if (raw_features.size() != kG4IRSF25CLCRFeatureCount) {
    throw std::invalid_argument("G4IRSF25 CLCR feature count mismatch");
  }
  std::vector<double> features(raw_features);
  G4IRSF25CLCRPrediction result;
  for (std::size_t index = 0; index < features.size(); ++index) {
    if (!std::isfinite(features[index])) {
      result.ood = true;
      return result;
    }
    if (!config.feature_min.empty() &&
        (features[index] < config.feature_min[index] ||
         features[index] > config.feature_max[index])) {
      result.ood = true;
    }
    if (!config.feature_mean.empty()) {
      features[index] =
          (features[index] - config.feature_mean[index]) /
          config.feature_scale[index];
    }
  }
  if (config.mode == "t0") {
    result.system_delta_seconds = arm.t0_system_delta_seconds;
    result.private_delta_seconds = arm.t0_private_delta_seconds;
    return result;
  }
  if (config.mode == "l2") {
    std::vector<double> hidden(config.hidden_weights.size(), 0.0);
    for (std::size_t unit = 0; unit < hidden.size(); ++unit) {
      double value = config.hidden_bias[unit];
      for (std::size_t feature = 0; feature < features.size(); ++feature) {
        value += config.hidden_weights[unit][feature] * features[feature];
      }
      hidden[unit] = std::max(0.0, value);
    }
    result.system_delta_seconds =
        config.hidden_system_bias + arm.system_intercept;
    result.private_delta_seconds =
        config.hidden_private_bias + arm.private_intercept;
    for (std::size_t unit = 0; unit < hidden.size(); ++unit) {
      result.system_delta_seconds +=
          config.hidden_system_weights[unit] * hidden[unit];
      result.private_delta_seconds +=
          config.hidden_private_weights[unit] * hidden[unit];
    }
  } else {
    result.system_delta_seconds = arm.system_intercept;
    result.private_delta_seconds = arm.private_intercept;
    for (std::size_t index = 0; index < features.size(); ++index) {
      result.system_delta_seconds += config.system_weights[index] * features[index];
      result.private_delta_seconds += config.private_weights[index] * features[index];
    }
  }
  if (config.mode == "l3") {
    result.system_delta_seconds += std::clamp(
        online_bias_seconds, -config.l3_bias_cap_seconds,
        config.l3_bias_cap_seconds);
  }
  return result;
}

}  // namespace czr005::ics
