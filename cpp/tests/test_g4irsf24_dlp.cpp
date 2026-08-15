#include <cmath>
#include <cstddef>
#include <iostream>
#include <string>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"

namespace {

using czr005::ics::Edge;
using czr005::ics::EventDecisionTraceRow;
using czr005::ics::EventDrivenJunctionConfig;
using czr005::ics::EventDrivenJunctionResult;
using czr005::ics::EventDrivenJunctionRuntime;
using czr005::ics::EventRuntimeBagRequest;
using czr005::ics::EventRuntimeFaultWindow;
using czr005::ics::G4IRSF24DLPConfig;
using czr005::ics::Graph;
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

Graph branch_graph() {
  Graph graph;
  graph.add_node(Node{0, 1, 0.05, 0, 0, {}});
  graph.add_node(Node{1, 4, 0.05, 1, 0, {}});
  graph.add_node(Node{2, 4, 0.05, 1, 1, {}});
  graph.add_node(Node{3, 2, 0.0, 2, 0, {}});
  graph.add_edge(Edge{0, 1, 1.0, 1.0});
  graph.add_edge(Edge{0, 2, 1.0, 1.0});
  graph.add_edge(Edge{1, 3, 1.0, 1.0});
  graph.add_edge(Edge{2, 3, 1.0, 1.0});
  graph.set_heuristic({
      {0.0, 1.0, 1.0, 2.0},
      {1.0, 0.0, 1.0, 1.0},
      {1.0, 1.0, 0.0, 1.5},
      {2.0, 1.0, 1.5, 0.0},
  });
  return graph;
}

Graph merge_graph() {
  Graph graph;
  graph.add_node(Node{0, 1, 0.05, 0, 0, {}});
  graph.add_node(Node{1, 1, 0.05, 0, 1, {}});
  graph.add_node(Node{2, 4, 0.10, 1, 0, {}});
  graph.add_node(Node{3, 2, 0.0, 2, 0, {}});
  graph.add_node(Node{4, 4, 0.10, 1, 1, {}});
  graph.add_edge(Edge{0, 2, 1.0, 1.0});
  graph.add_edge(Edge{0, 4, 1.0, 1.0});
  graph.add_edge(Edge{1, 2, 1.0, 1.0});
  graph.add_edge(Edge{2, 3, 1.0, 1.0});
  graph.add_edge(Edge{4, 3, 1.0, 1.0});
  graph.set_heuristic({
      {0.0, 1.0, 1.0, 2.0, 1.0},
      {1.0, 0.0, 1.0, 2.0, 1.0},
      {1.0, 1.0, 0.0, 2.0, 1.0},
      {2.0, 2.0, 2.0, 0.0, 1.0},
      {1.0, 1.0, 1.0, 1.0, 0.0},
  });
  return graph;
}

EventDrivenJunctionConfig base_config() {
  EventDrivenJunctionConfig config;
  config.scorer_mode = "S4";
  config.enable_source_admission = false;
  config.enable_backpressure = false;
  config.enable_pibt_lite = false;
  config.enable_deadlock_escape = false;
  config.pibt_mode = "P0";
  config.retry_interval = 0.05;
  config.trace_limit = 100;
  config.max_events = 10000;
  config.max_simulation_time = 100.0;
  return config;
}

G4IRSF24DLPConfig dlp_config(
    const std::string& mode,
    double edge_01,
    double edge_02,
    int support = 8) {
  G4IRSF24DLPConfig dlp;
  dlp.mode = mode;
  dlp.beta = 1.0;
  dlp.min_support = 2;
  dlp.margin_seconds = 0.0;
  dlp.detour_allowance_seconds = 1.0;
  dlp.insert_edge(0, 1, edge_01, support);
  dlp.insert_edge(0, 2, edge_02, support);
  dlp.insert_edge(1, 3, 0.0, support);
  dlp.insert_edge(2, 3, 0.0, support);
  if (mode == "td") {
    dlp.insert_value(1, 3, 0.0, support);
    dlp.insert_value(2, 3, 0.0, support);
  }
  return dlp;
}

EventDrivenJunctionResult run(
    EventDrivenJunctionConfig config,
    const std::vector<EventRuntimeFaultWindow>& faults = {}) {
  return EventDrivenJunctionRuntime(branch_graph(), std::move(config))
      .run({EventRuntimeBagRequest{
                "unit", 1, 0.0, 100.0, 0, 3, "g24-test"}},
           faults);
}

EventDrivenJunctionResult run_j2() {
  auto config = base_config();
  config.resource_semantics = "R3";
  config.event_semantics = "E4";
  config.pibt_mode = "P2";
  config.merge_grant_timing_mode = "jit_fair_aging_deadline";
  config.g4irsf24_dlp = dlp_config("ewma", 0.0, 0.0);
  config.g4irsf24_dlp.edge_residuals.clear();
  config.g4irsf24_dlp.insert_edge(0, 4, 1.0, 8);
  config.g4irsf24_dlp.insert_edge(0, 2, -2.0, 8);
  config.g4irsf24_dlp.insert_edge(2, 3, 0.0, 8);
  config.g4irsf24_dlp.insert_edge(4, 3, 0.0, 8);
  return EventDrivenJunctionRuntime(merge_graph(), std::move(config))
      .run({EventRuntimeBagRequest{
          "j2", 2, 0.0, 100.0, 0, 3, "g24-j2"}});
}

const EventDecisionTraceRow* decision_at(
    const EventDrivenJunctionResult& result,
    int current_node) {
  for (const auto& decision : result.decisions) {
    if (decision.current_node == current_node) {
      return &decision;
    }
  }
  return nullptr;
}

void require_safe(Checks& checks,
                  const EventDrivenJunctionResult& result,
                  const std::string& label) {
  checks.require(result.summary.completed_count == 1,
                 label + ": bag must complete");
  checks.require(result.summary.failed_count == 0,
                 label + ": no bag may fail");
  checks.require(result.summary.physical_fault_edge_entry_violation_count == 0,
                 label + ": physical fault shield must hold");
  checks.require(result.summary.runtime_full_astar_calls == 0 &&
                     result.summary.global_reservation_scan_count == 0 &&
                     result.summary.two_step_reservation_count == 0,
                 label + ": DLP must remain one-hop and scan-free");
}

void test_off_and_zero_residual_are_exact_s4(Checks& checks) {
  const auto off = run(base_config());
  auto active_config = base_config();
  active_config.g4irsf24_dlp = dlp_config("ewma", 0.0, 0.0);
  const auto active = run(std::move(active_config));
  require_safe(checks, off, "DLP off");
  require_safe(checks, active, "DLP zero residual");
  checks.require(off.decisions.size() == active.decisions.size(),
                 "zero residual must preserve the number of S4 decisions");
  if (off.decisions.size() == active.decisions.size()) {
    for (std::size_t index = 0; index < off.decisions.size(); ++index) {
      const auto& lhs = off.decisions[index];
      const auto& rhs = active.decisions[index];
      checks.require(lhs.current_node == rhs.current_node &&
                         lhs.selected_next == rhs.selected_next &&
                         lhs.event_time == rhs.event_time &&
                         lhs.candidates.size() == rhs.candidates.size(),
                     "zero residual must preserve each committed S4 action");
      if (lhs.candidates.size() == rhs.candidates.size()) {
        for (std::size_t candidate = 0;
             candidate < lhs.candidates.size();
             ++candidate) {
          checks.require(
              lhs.candidates[candidate].model_score ==
                  rhs.candidates[candidate].model_score,
              "zero residual fallback must retain exact S4 candidate scores");
        }
      }
    }
  }
  checks.require(off.summary.g4irsf24_dlp_mode.empty() &&
                     off.summary.g4irsf24_dlp_route_evaluation_count == 0,
                 "empty artifact must keep the G24 path entirely off");
}

void test_supported_ewma_residual_commits_one_mutation(Checks& checks) {
  auto config = base_config();
  config.g4irsf24_dlp = dlp_config("ewma", 2.0, -2.0);
  const auto result = run(std::move(config));
  require_safe(checks, result, "EWMA mutation");
  const auto* decision = decision_at(result, 0);
  checks.require(decision != nullptr, "EWMA mutation needs the branch trace");
  if (decision != nullptr) {
    checks.require(decision->selected_next == 2 &&
                       decision->g4irsf24_dlp_s4_next == 1 &&
                       decision->g4irsf24_dlp_proposed_next == 2 &&
                       decision->g4irsf24_dlp_committed_mutation,
                   "supported EWMA residual must replace exactly the S4 branch");
    checks.require(
        std::abs(decision->g4irsf24_dlp_residual_seconds + 2.0) < 1.0e-12 &&
            decision->g4irsf24_dlp_edge_support == 8 &&
            decision->g4irsf24_dlp_value_support == 0,
        "EWMA trace must expose the chosen edge residual and support");
  }
  checks.require(result.summary.g4irsf24_dlp_proposal_count == 1 &&
                     result.summary.g4irsf24_dlp_committed_mutation_count == 1,
                 "proposal and real edge commit counters must agree");
}

void test_td_adds_edge_and_value_residual(Checks& checks) {
  auto config = base_config();
  config.g4irsf24_dlp = dlp_config("td", 0.0, -0.25);
  config.g4irsf24_dlp.value_residuals[
      G4IRSF24DLPConfig::key(2, 3)] = {-0.75, 9};
  const auto result = run(std::move(config));
  require_safe(checks, result, "TD mutation");
  const auto* decision = decision_at(result, 0);
  checks.require(decision != nullptr && decision->selected_next == 2,
                 "TD edge+value residual must switch the branch");
  if (decision != nullptr) {
    checks.require(
        std::abs(decision->g4irsf24_dlp_residual_seconds + 1.0) < 1.0e-12 &&
            decision->g4irsf24_dlp_edge_support == 8 &&
            decision->g4irsf24_dlp_value_support == 9,
        "TD trace must expose summed residual and both supports");
  }
  const auto* terminal = decision_at(result, 2);
  checks.require(
      terminal != nullptr && terminal->selected_next == 3 &&
          terminal->g4irsf24_dlp_value_support == 0 &&
          terminal->g4irsf24_dlp_fallback_reason == "same_action",
      "TD terminal MOVE must use zero downstream value without a goal/goal row");
  checks.require(
      result.summary.g4irsf24_dlp_unsupported_fallback_count == 0,
      "a supported TD terminal edge must not count as unsupported");
}

void test_support_margin_and_detour_abstain_to_exact_s4(Checks& checks) {
  auto low_support = base_config();
  low_support.g4irsf24_dlp =
      dlp_config("ewma", 2.0, -2.0, 1);
  const auto low = run(std::move(low_support));
  const auto* low_decision = decision_at(low, 0);
  checks.require(low_decision != nullptr && low_decision->selected_next == 1 &&
                     low.summary.g4irsf24_dlp_low_support_fallback_count > 0,
                 "low support must retain the exact S4 branch");

  auto margin = base_config();
  margin.g4irsf24_dlp = dlp_config("ewma", 0.0, -0.6);
  margin.g4irsf24_dlp.margin_seconds = 0.2;
  const auto margin_result = run(std::move(margin));
  const auto* margin_decision = decision_at(margin_result, 0);
  checks.require(
      margin_decision != nullptr && margin_decision->selected_next == 1 &&
          margin_result.summary.g4irsf24_dlp_margin_fallback_count > 0,
      "sub-margin residual improvement must retain the exact S4 branch");

  auto detour = base_config();
  detour.g4irsf24_dlp = dlp_config("ewma", 0.0, -10.0);
  detour.g4irsf24_dlp.detour_allowance_seconds = 0.4;
  const auto detour_result = run(std::move(detour));
  const auto* detour_decision = decision_at(detour_result, 0);
  checks.require(
      detour_decision != nullptr && detour_decision->selected_next == 1 &&
          detour_result.summary.g4irsf24_dlp_detour_fallback_count > 0,
      "over-detour candidate must retain the exact S4 branch");
}

void test_faulted_candidate_never_becomes_a_dlp_proposal(Checks& checks) {
  auto config = base_config();
  config.g4irsf24_dlp = dlp_config("ewma", 0.0, -100.0);
  const auto result = run(
      std::move(config),
      {EventRuntimeFaultWindow{0, 2, 0.0, 10.0, 0.0, false}});
  require_safe(checks, result, "fault-filtered DLP");
  const auto* decision = decision_at(result, 0);
  checks.require(
      decision != nullptr && decision->selected_next == 1 &&
          decision->g4irsf24_dlp_proposed_next != 2 &&
          !decision->g4irsf24_dlp_committed_mutation &&
          result.summary.g4irsf24_dlp_shield_fault_fallback_count > 0,
      "a faulted candidate must remain owned by the existing shield");
}

void test_j2_counts_mutation_only_after_real_grant_commit(Checks& checks) {
  const auto result = run_j2();
  require_safe(checks, result, "J2 DLP mutation");
  const auto* decision = decision_at(result, 0);
  checks.require(
      decision != nullptr && decision->selected_next == 2 &&
          decision->g4irsf24_dlp_s4_next == 4 &&
          decision->g4irsf24_dlp_proposed_next == 2 &&
          decision->g4irsf24_dlp_committed_mutation,
      "J2 trace must close the DLP mutation only after the merge grant commits");
  checks.require(
      result.summary.merge_grant_committed_count == 1 &&
          result.summary.g4irsf24_dlp_proposal_count == 1 &&
          result.summary.g4irsf24_dlp_committed_mutation_count == 1,
      "J2 proposal and committed mutation counters must follow the real grant");
}

}  // namespace

int main() {
  Checks checks;
  test_off_and_zero_residual_are_exact_s4(checks);
  test_supported_ewma_residual_commits_one_mutation(checks);
  test_td_adds_edge_and_value_residual(checks);
  test_support_margin_and_detour_abstain_to_exact_s4(checks);
  test_faulted_candidate_never_becomes_a_dlp_proposal(checks);
  test_j2_counts_mutation_only_after_real_grant_commit(checks);
  if (checks.failures != 0) {
    std::cerr << checks.failures << " G4IRSF24 DLP checks failed\n";
    return 1;
  }
  std::cout << "G4IRSF24 DLP checks passed\n";
  return 0;
}
