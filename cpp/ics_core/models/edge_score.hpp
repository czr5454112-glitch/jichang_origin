#pragma once

#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace czr005::ics {

class EdgeScoreModel {
 public:
  EdgeScoreModel(std::vector<std::vector<double>> w1,
                 std::vector<double> b1,
                 std::vector<double> w2,
                 double b2)
      : w1_(std::move(w1)), b1_(std::move(b1)), w2_(std::move(w2)), b2_(b2) {
    validate();
  }

  std::vector<double> scores(const std::vector<std::vector<double>>& features) const {
    std::vector<double> values;
    values.reserve(features.size());
    for (const auto& row : features) {
      values.push_back(score_one(row));
    }
    return values;
  }

  int predict(const std::vector<std::vector<double>>& features,
              const std::vector<bool>& action_mask = {}) const {
    if (!action_mask.empty() && action_mask.size() != features.size()) {
      throw std::invalid_argument("action_mask size must match feature row count");
    }
    const auto values = scores(features);
    if (values.empty()) {
      throw std::invalid_argument("features must not be empty");
    }

    int best_index = -1;
    double best_score = -std::numeric_limits<double>::infinity();
    for (std::size_t index = 0; index < values.size(); ++index) {
      if (!action_mask.empty() && !action_mask[index]) {
        continue;
      }
      if (best_index < 0 || values[index] > best_score) {
        best_index = static_cast<int>(index);
        best_score = values[index];
      }
    }
    if (best_index < 0) {
      throw std::invalid_argument("at least one action must be available");
    }
    return best_index;
  }

  std::size_t feature_dim() const { return w1_.size(); }
  std::size_t hidden_dim() const { return b1_.size(); }

 private:
  std::vector<std::vector<double>> w1_;
  std::vector<double> b1_;
  std::vector<double> w2_;
  double b2_ = 0.0;

  void validate() const {
    if (w1_.empty()) {
      throw std::invalid_argument("w1 must not be empty");
    }
    if (b1_.empty()) {
      throw std::invalid_argument("b1 must not be empty");
    }
    if (w2_.size() != b1_.size()) {
      throw std::invalid_argument("w2 size must match hidden dimension");
    }
    for (const auto& row : w1_) {
      if (row.size() != b1_.size()) {
        throw std::invalid_argument("each w1 row must match hidden dimension");
      }
    }
  }

  double score_one(const std::vector<double>& features) const {
    if (features.size() != w1_.size()) {
      throw std::invalid_argument("feature row size must match feature dimension");
    }
    double score = b2_;
    for (std::size_t hidden = 0; hidden < b1_.size(); ++hidden) {
      double value = b1_[hidden];
      for (std::size_t feature = 0; feature < features.size(); ++feature) {
        value += features[feature] * w1_[feature][hidden];
      }
      score += std::tanh(value) * w2_[hidden];
    }
    return score;
  }
};

}  // namespace czr005::ics
