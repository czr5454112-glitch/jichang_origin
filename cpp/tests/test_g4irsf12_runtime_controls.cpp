#include <cmath>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"

#ifndef CZR005_SOURCE_DIR
#error "CZR005_SOURCE_DIR must identify the repository root"
#endif

namespace {

using czr005::ics::EventDrivenJunctionConfig;
using czr005::ics::EventDrivenJunctionResult;
using czr005::ics::EventDrivenJunctionRuntime;
using czr005::ics::EventRuntimeBagRequest;
using czr005::ics::Graph;

struct Checks {
  int failures = 0;

  void require(bool condition, const std::string& message) {
    if (!condition) {
      ++failures;
      std::cerr << "FAIL: " << message << '\n';
    }
  }
};

const Graph& canonical_graph() {
  static const auto fixture = [] {
    const auto path = std::filesystem::path(CZR005_SOURCE_DIR) /
                      "data" / "processed" / "maps" / "map2.json";
    return czr005::ics::read_canonical_map2_json(path);
  }();
  return fixture.graph;
}

std::vector<EventRuntimeBagRequest> burst(int count) {
  std::vector<EventRuntimeBagRequest> rows;
  rows.reserve(static_cast<std::size_t>(count));
  for (int index = 0; index < count; ++index) {
    rows.push_back(EventRuntimeBagRequest{"g4irsf12-burst-" + std::to_string(index),
                                          index,
                                          0.0,
                                          10000.0,
                                          3,
                                          47,
                                          "canonical-map2"});
  }
  return rows;
}

EventDrivenJunctionConfig config_for(const std::string& resource,
                                     const std::string& pressure = "C0") {
  EventDrivenJunctionConfig config;
  config.resource_semantics = resource;
  config.pressure_mode = pressure;
  config.entry_headway_seconds = 0.001;
  config.retry_interval = 0.05;
  config.dispatch_headway_seconds = 0.001;
  config.max_events = 2000000;
  config.max_simulation_time = 10000.0;
  config.max_decisions_per_bag = 1000;
  config.trace_limit = 100000;
  config.enable_backpressure = pressure != "C0" && pressure != "off";
  return config;
}

EventDrivenJunctionResult run(const std::string& resource,
                              const std::string& pressure = "C0") {
  return EventDrivenJunctionRuntime(canonical_graph(),
                                    config_for(resource, pressure))
      .run(burst(20));
}

void require_safe_complete(Checks& checks,
                           const EventDrivenJunctionResult& result,
                           const std::string& label) {
  checks.require(result.summary.completed_count == 20,
                 label + " must complete the canonical burst");
  checks.require(result.summary.failed_count == 0,
                 label + " must have no failed bags");
  checks.require(result.summary.reservation_conflicts == 0,
                 label + " must retain zero resource conflicts");
  checks.require(result.summary.runtime_full_astar_calls == 0 &&
                     result.summary.global_reservation_scan_count == 0 &&
                     result.summary.max_edges_selected_per_arrive <= 1,
                 label + " must retain the one-step no-A* boundary");
}

void test_resource_semantics_isolation(Checks& checks) {
  const auto r0 = run("R0");
  const auto r1 = run("R1");
  const auto r2 = run("R2");
  const auto r3 = run("R3");
  const auto r4 = run("R4");
  for (const auto* result : {&r0, &r1, &r2, &r3, &r4}) {
    require_safe_complete(checks, *result, result->summary.resource_semantics_id);
  }

  checks.require(std::abs(r0.summary.end_time - r1.summary.end_time) < 1.0e-9,
                 "R0 and R1 must be identical on map2 because it has no reverse pairs");
  checks.require(r0.summary.max_same_directed_edge_inflight == 1 &&
                     r1.summary.max_same_directed_edge_inflight == 1,
                 "full-travel-exclusive controls must admit one in-flight bag per edge");
  checks.require(r2.summary.max_same_directed_edge_inflight > 1 &&
                     r3.summary.max_same_directed_edge_inflight > 1 &&
                     r4.summary.max_same_directed_edge_inflight > 1,
                 "headway/node-window modes must allow multiple safe in-flight bags");
  checks.require(r2.summary.end_time < r0.summary.end_time &&
                     r3.summary.end_time < r0.summary.end_time &&
                     r4.summary.end_time < r0.summary.end_time,
                 "controlled non-full-travel modes should remove the burst bottleneck");
}

const czr005::ics::EventRuntimeJunctionResult* find_junction(
    const EventDrivenJunctionResult& result,
    int node) {
  const auto found =
      std::find_if(result.junctions.begin(),
                   result.junctions.end(),
                   [&](const auto& row) {
                     return row.node == node;
                   });
  return found == result.junctions.end() ? nullptr : &*found;
}

EventDrivenJunctionResult run_same_goal_pair(
    const std::string& resource) {
  auto config = config_for(resource);
  config.enable_source_admission = false;
  config.enable_backpressure = false;
  return EventDrivenJunctionRuntime(canonical_graph(),
                                    std::move(config))
      .run({
          EventRuntimeBagRequest{
              "same-goal-a",
              1001,
              0.0,
              100.0,
              6,
              8,
              "canonical-map2"},
          EventRuntimeBagRequest{
              "same-goal-b",
              1002,
              0.0,
              100.0,
              7,
              8,
              "canonical-map2"},
      });
}

void test_r3_goal_exempts_destination_window(
    Checks& checks) {
  const auto r3 = run_same_goal_pair("R3");
  checks.require(
      r3.summary.completed_count == 2 &&
          r3.summary.failed_count == 0 &&
          r3.summary.reservation_conflicts == 0,
      "R3 same-goal pair must complete without a resource conflict");
  const auto* r3_goal = find_junction(r3, 8);
  checks.require(
      r3_goal != nullptr &&
          r3_goal->service_reservation_count == 0 &&
          r3_goal->cumulative_service_reserved_seconds == 0.0,
      "R3 java-compatible semantics must exempt the actual goal from its destination window");

  for (const std::string resource :
       {"R0", "R1", "R2", "R4"}) {
    const auto control = run_same_goal_pair(resource);
    checks.require(
        control.summary.completed_count == 2 &&
            control.summary.failed_count == 0 &&
            control.summary.reservation_conflicts == 0,
        resource +
            " same-goal control must complete without a resource conflict"
            " (completed=" +
            std::to_string(control.summary.completed_count) +
            ", failed=" +
            std::to_string(control.summary.failed_count) +
            ", conflicts=" +
            std::to_string(control.summary.reservation_conflicts) +
            ")");
    const auto* goal = find_junction(control, 8);
    checks.require(
        goal != nullptr &&
            goal->service_reservation_count == 2 &&
            goal->cumulative_service_reserved_seconds > 0.0,
        resource +
            " must retain its declared destination/merge calendar at the same real-map goal"
            " (reservation_count=" +
            std::to_string(
                goal == nullptr ? 0
                                : goal->service_reservation_count) +
            ")");
  }
}

void test_goal_conditioned_pressure_modes(Checks& checks) {
  for (const std::string mode : {"C1", "C2", "C3"}) {
    const auto result = run("R3", mode);
    require_safe_complete(checks, result, mode);
    checks.require(!result.summary.pressure_mode.empty(),
                   mode + " must expose a canonical pressure identifier");
    bool saw_finite_goal_state = false;
    for (const auto& decision : result.decisions) {
      for (const auto& candidate : decision.candidates) {
        saw_finite_goal_state = saw_finite_goal_state ||
                                (candidate.current_goal_queue_length >= 0 &&
                                 candidate.target_goal_queue_length >= 0 &&
                                 std::isfinite(candidate.goal_conditioned_differential) &&
                                 candidate.estimated_service_rate > 0.0 &&
                                 std::isfinite(candidate.service_weighted_pressure));
      }
    }
    checks.require(saw_finite_goal_state,
                   mode + " must expose auditable goal-conditioned local features");
  }
}

void test_invalid_modes_fail_closed(Checks& checks) {
  try {
    auto config = config_for("not-a-resource-mode");
    EventDrivenJunctionRuntime ignored(canonical_graph(), config);
    (void)ignored;
    checks.require(false, "unknown resource semantics must fail closed");
  } catch (const std::invalid_argument&) {
  }
  try {
    auto config = config_for("R3", "not-a-pressure-mode");
    config.enable_backpressure = true;
    EventDrivenJunctionRuntime ignored(canonical_graph(), config);
    (void)ignored;
    checks.require(false, "unknown pressure mode must fail closed");
  } catch (const std::invalid_argument&) {
  }
}

}  // namespace

int main() {
  Checks checks;
  test_resource_semantics_isolation(checks);
  test_r3_goal_exempts_destination_window(checks);
  test_goal_conditioned_pressure_modes(checks);
  test_invalid_modes_fail_closed(checks);
  if (checks.failures != 0) {
    std::cerr << checks.failures << " G4IRSF12 runtime-control checks failed\n";
    return 1;
  }
  std::cout << "G4IRSF12 runtime-control checks passed\n";
  return 0;
}
