#pragma once

#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "ics_core/models/edge_score.hpp"

namespace czr005::ics {

inline void expect_token(std::istream& input, const std::string& expected) {
  std::string actual;
  if (!(input >> actual) || actual != expected) {
    throw std::runtime_error("expected token: " + expected);
  }
}

inline EdgeScoreModel load_edge_score_model_text(const std::string& path) {
  std::ifstream input(path);
  if (!input) {
    throw std::runtime_error("failed to open edge-score model: " + path);
  }

  expect_token(input, "czr005_edge_score_v1");
  expect_token(input, "feature_dim");
  std::size_t feature_dim = 0;
  if (!(input >> feature_dim)) {
    throw std::runtime_error("failed to read feature_dim");
  }
  expect_token(input, "hidden_dim");
  std::size_t hidden_dim = 0;
  if (!(input >> hidden_dim)) {
    throw std::runtime_error("failed to read hidden_dim");
  }
  if (feature_dim == 0 || hidden_dim == 0) {
    throw std::runtime_error("feature_dim and hidden_dim must be positive");
  }

  expect_token(input, "b2");
  double b2 = 0.0;
  if (!(input >> b2)) {
    throw std::runtime_error("failed to read b2");
  }

  expect_token(input, "w1");
  std::vector<std::vector<double>> w1(feature_dim, std::vector<double>(hidden_dim, 0.0));
  for (std::size_t feature = 0; feature < feature_dim; ++feature) {
    for (std::size_t hidden = 0; hidden < hidden_dim; ++hidden) {
      if (!(input >> w1[feature][hidden])) {
        throw std::runtime_error("failed to read w1 values");
      }
    }
  }

  expect_token(input, "b1");
  std::vector<double> b1(hidden_dim, 0.0);
  for (double& value : b1) {
    if (!(input >> value)) {
      throw std::runtime_error("failed to read b1 values");
    }
  }

  expect_token(input, "w2");
  std::vector<double> w2(hidden_dim, 0.0);
  for (double& value : w2) {
    if (!(input >> value)) {
      throw std::runtime_error("failed to read w2 values");
    }
  }

  return EdgeScoreModel(std::move(w1), std::move(b1), std::move(w2), b2);
}

}  // namespace czr005::ics
