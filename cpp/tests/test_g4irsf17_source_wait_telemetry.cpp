#include <array>
#include <cmath>
#include <cstddef>
#include <filesystem>
#include <iostream>
#include <numeric>
#include <string>
#include <vector>

#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"

#ifndef CZR005_SOURCE_DIR
#error "CZR005_SOURCE_DIR must identify the repository root"
#endif

namespace {

// The focused binary covers both enabled accounting and the frozen off path.

using czr005::ics::EventDrivenJunctionConfig;
using czr005::ics::EventDrivenJunctionRuntime;
using czr005::ics::EventRuntimeBagRequest;
using czr005::ics::G4IRSF17SourceWaitReason;

struct Checks {
  int failures = 0;

  void require(bool condition, const std::string& message) {
    if (!condition) {
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

std::vector<EventRuntimeBagRequest> burst(int count) {
  std::vector<EventRuntimeBagRequest> bags;
  for (int index = 0; index < count; ++index) {
    bags.push_back(EventRuntimeBagRequest{
        "g17-burst-" + std::to_string(index),
        index + 1,
        0.0,
        10000.0,
        3,
        47,
        "source-3"});
  }
  return bags;
}

EventDrivenJunctionConfig config_with_telemetry(int trace_limit) {
  EventDrivenJunctionConfig config;
  config.queue_discipline = "aging";
  config.retry_interval = 0.05;
  config.minimum_service_seconds = 0.25;
  config.dispatch_headway_seconds = 0.001;
  config.max_decisions_per_bag = 1000;
  config.max_events = 2000000;
  config.max_simulation_time = 10000.0;
  config.trace_limit = 1000;
  config.enable_source_admission = false;
  config.admission_mode = "off";
  config.enable_g4irsf17_source_wait_telemetry = true;
  config.g4irsf17_source_wait_trace_limit = trace_limit;
  return config;
}

void check_canonical_reasons_and_precedence(Checks& checks) {
  constexpr std::array<const char*, 8> expected{
      "SOURCE_SERVICE_NOT_READY",
      "FIRST_EDGE_CREDIT_UNAVAILABLE",
      "DESTINATION_QUEUE_CAPACITY",
      "DESTINATION_MERGE_TOKEN",
      "PHYSICAL_FAULT_OR_GENERATION",
      "SUPERVISOR_HOLD",
      "PIBT_OR_RECOVERY_TRANSACTION",
      "OTHER_EXPLICIT_REASON"};
  for (std::size_t index = 0; index < expected.size(); ++index) {
    const auto reason = static_cast<G4IRSF17SourceWaitReason>(index);
    checks.require(
        std::string(czr005::ics::g4irsf17_source_wait_reason_name(reason)) ==
            expected[index],
        "canonical blocker reason spelling must remain exact");
  }

  czr005::ics::event_runtime_detail::G4IRSF17SourceBlockerObservation
      observed;
  using Resource = czr005::ics::event_runtime_detail::
      G4IRSF17SourceWaitResource;
  observed.consider(G4IRSF17SourceWaitReason::kOtherExplicitReason,
                    Resource::kOtherLocalResource,
                    9,
                    3,
                    9,
                    7);
  observed.consider(G4IRSF17SourceWaitReason::kDestinationQueueCapacity,
                    Resource::kDestinationQueue,
                    8,
                    3,
                    8,
                    5);
  observed.consider(G4IRSF17SourceWaitReason::kPhysicalFaultOrGeneration,
                    Resource::kPhysicalEdge,
                    7,
                    3,
                    7,
                    2);
  observed.consider(G4IRSF17SourceWaitReason::kSupervisorHold,
                    Resource::kSupervisorState,
                    6,
                    6,
                    6,
                    1);
  checks.require(
      observed.reason ==
          G4IRSF17SourceWaitReason::kPhysicalFaultOrGeneration,
      "deterministic precedence must retain the concrete physical blocker");
  checks.require(
      czr005::ics::g4irsf17_source_wait_reason_precedence(
          observed.reason) == 0,
      "physical/generation blocker must have canonical precedence zero");
}

void check_real_source_service_intervals(Checks& checks) {
  EventDrivenJunctionRuntime runtime(
      canonical_graph(), config_with_telemetry(1000));
  const auto result = runtime.run(burst(3));
  const auto& summary = result.summary;
  checks.require(summary.completed_count == 3 && summary.failed_count == 0,
                 "telemetry must not change successful real-map execution");
  checks.require(summary.g4irsf17_source_wait_telemetry_enabled,
                 "summary must mark G17 telemetry enabled");
  checks.require(summary.g4irsf17_source_wait_interval_total_count > 0,
                 "same-source burst must produce real wait intervals");
  checks.require(
      summary.g4irsf17_source_wait_interval_stored_count ==
          result.g4irsf17_source_wait_blockers.size(),
      "stored interval counter must match stored rows");
  checks.require(summary.g4irsf17_source_wait_interval_dropped_count == 0,
                 "ample trace capacity must retain all rows");
  checks.require(summary.g4irsf17_source_wait_runtime_global_scan_count == 0,
                 "runtime attribution must not perform a global scan");

  std::uint64_t interval_count_sum = 0;
  double seconds_sum = 0.0;
  double bag_seconds_sum = 0.0;
  for (std::size_t index = 0;
       index < czr005::ics::kG4IRSF17SourceWaitReasonCount;
       ++index) {
    interval_count_sum +=
        summary.g4irsf17_source_wait_reason_interval_counts[index];
    seconds_sum += summary.g4irsf17_source_wait_reason_seconds[index];
    bag_seconds_sum +=
        summary.g4irsf17_source_wait_reason_bag_seconds[index];
  }
  checks.require(
      interval_count_sum ==
          summary.g4irsf17_source_wait_interval_total_count,
      "mutually exclusive reason counts must be additive");
  checks.require(
      std::abs(seconds_sum - summary.g4irsf17_source_wait_seconds) < 1e-9,
      "reason seconds must add to total source wait seconds");
  checks.require(
      std::abs(bag_seconds_sum -
               summary.g4irsf17_source_wait_bag_seconds) < 1e-9,
      "reason bag-seconds must add to total source wait bag-seconds");

  bool saw_selected_trace_identity = false;
  for (const auto& row : result.g4irsf17_source_wait_blockers) {
    checks.require(row.wait_end_time > row.wait_start_time,
                   "stored interval must have positive measured duration");
    checks.require(
        std::abs(row.wait_seconds -
                 (row.wait_end_time - row.wait_start_time)) < 1e-9,
        "wait delta must equal actual interval endpoints");
    checks.require(
        std::abs(row.wait_bag_seconds -
                 row.wait_seconds * row.affected_bag_count) < 1e-9,
        "bag-seconds must be queue-weighted and additive");
    checks.require(row.source_node == 3,
                   "the burst blocker must remain source-local");
    checks.require(
        row.reason == "SOURCE_SERVICE_NOT_READY",
        "serial source service is the exact blocker in admission-off mode");
    checks.require(!row.blocker_resource.empty(),
                   "every interval must identify its causal resource");
    saw_selected_trace_identity =
        saw_selected_trace_identity || row.selected_runtime_bag_id >= 0;
  }
  checks.require(saw_selected_trace_identity,
                 "at least one real attempt must retain trace-only bag identity");
}

void check_bounded_storage_and_off_path(Checks& checks) {
  EventDrivenJunctionRuntime capped(
      canonical_graph(), config_with_telemetry(0));
  const auto capped_result = capped.run(burst(3));
  checks.require(capped_result.g4irsf17_source_wait_blockers.empty(),
                 "zero row limit must keep summary-only telemetry");
  checks.require(
      capped_result.summary.g4irsf17_source_wait_interval_total_count > 0 &&
          capped_result.summary.g4irsf17_source_wait_interval_dropped_count ==
              capped_result.summary.g4irsf17_source_wait_interval_total_count,
      "bounded storage must preserve totals while counting dropped rows");

  auto off_config = config_with_telemetry(1000);
  off_config.enable_g4irsf17_source_wait_telemetry = false;
  EventDrivenJunctionRuntime off(canonical_graph(), off_config);
  const auto off_result = off.run(burst(2));
  checks.require(!off_result.summary.g4irsf17_source_wait_telemetry_enabled,
                 "telemetry-off must remain the default compatibility path");
  checks.require(off_result.g4irsf17_source_wait_blockers.empty(),
                 "telemetry-off must not materialize G17 rows");
}

}  // namespace

int main() {
  Checks checks;
  check_canonical_reasons_and_precedence(checks);
  check_real_source_service_intervals(checks);
  check_bounded_storage_and_off_path(checks);
  if (checks.failures != 0) {
    std::cerr << checks.failures << " G4IRSF17 checks failed\n";
    return 1;
  }
  std::cout << "G4IRSF17 source-wait telemetry checks passed\n";
  return 0;
}
