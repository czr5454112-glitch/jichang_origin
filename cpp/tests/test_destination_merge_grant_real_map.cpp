#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <queue>
#include <set>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/runtime/destination_merge_grant.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"

#ifndef CZR005_SOURCE_DIR
#error "CZR005_SOURCE_DIR must identify the repository root"
#endif

namespace {

using czr005::ics::DestinationMergeGrantBoundary;
using czr005::ics::DestinationMergeGrantController;
using czr005::ics::DestinationMergeGrantLifecycleRow;
using czr005::ics::DestinationMergeGrantRule;
using czr005::ics::DestinationMergeRequest;
using czr005::ics::EventDrivenJunctionConfig;
using czr005::ics::EventDrivenJunctionResult;
using czr005::ics::EventDrivenJunctionRuntime;
using czr005::ics::EventRuntimeBagRequest;
using czr005::ics::EventRuntimeFaultWindow;
using czr005::ics::Graph;
using czr005::ics::MergeGrantCapability;
using czr005::ics::MergeGrantReason;
using czr005::ics::MergeGrantState;
using czr005::ics::Node;
using czr005::ics::Edge;
using czr005::ics::destination_merge_request_less;
using czr005::ics::event_runtime_detail::LocalCalendar;

static_assert(DestinationMergeGrantBoundary::kReservationDepth == 1);
static_assert(DestinationMergeGrantBoundary::kDirectedEdgesPerGrant == 1);
static_assert(DestinationMergeGrantBoundary::kDestinationSlotsPerGrant == 1);
static_assert(!DestinationMergeGrantBoundary::kReadsFutureRoute);
static_assert(!DestinationMergeGrantBoundary::kReadsGlobalTaskList);
static_assert(!DestinationMergeGrantBoundary::kReadsGlobalReservationTable);
static_assert(!DestinationMergeGrantBoundary::kReadsAllAirportQueues);
static_assert(!DestinationMergeGrantBoundary::kUsesTeacherPath);
static_assert(
    !DestinationMergeGrantBoundary::kStoresPostHocOutcomeInRequest);
static_assert(!std::is_default_constructible_v<MergeGrantCapability>);
static_assert(!std::is_copy_constructible_v<MergeGrantCapability>);
static_assert(!std::is_copy_assignable_v<MergeGrantCapability>);
static_assert(std::is_nothrow_move_constructible_v<MergeGrantCapability>);
static_assert(std::is_nothrow_move_assignable_v<MergeGrantCapability>);

constexpr double kTolerance = 1.0e-9;

struct Checks {
  int failures = 0;

  void require(bool condition, const std::string& message) {
    if (!condition) {
      ++failures;
      std::cerr << "FAIL: " << message << '\n';
    }
  }
};

const czr005::ics::CanonicalMap2ReadResult& canonical_map2() {
  static const auto fixture = [] {
    const auto path = std::filesystem::path(CZR005_SOURCE_DIR) /
                      "data" / "processed" / "maps" / "map2.json";
    return czr005::ics::read_canonical_map2_json(path);
  }();
  return fixture;
}

struct RealEqualTravelMerge {
  int destination = -1;
  int upstream_a = -1;
  int upstream_b = -1;
  int goal = -1;
  double travel = 0.0;
};

struct RealUnequalTravelMerge {
  int destination = -1;
  int short_upstream = -1;
  int long_upstream = -1;
  int goal = -1;
  double short_travel = 0.0;
  double long_travel = 0.0;
};

RealEqualTravelMerge discover_equal_travel_merge() {
  const auto& graph = canonical_map2().graph;
  for (const int destination : graph.node_locations()) {
    if (graph.incoming_degree(destination) < 2 ||
        graph.outgoing(destination).empty() ||
        graph.service_time(destination) <= 0.0) {
      continue;
    }
    std::vector<int> incoming;
    for (const int upstream : graph.node_locations()) {
      if (graph.has_edge(upstream, destination)) {
        incoming.push_back(upstream);
      }
    }
    std::sort(incoming.begin(), incoming.end());
    for (std::size_t left = 0; left < incoming.size(); ++left) {
      for (std::size_t right = left + 1; right < incoming.size();
           ++right) {
        const double left_travel =
            graph.edge(incoming[left], destination).travel_time();
        const double right_travel =
            graph.edge(incoming[right], destination).travel_time();
        if (std::abs(left_travel - right_travel) <= kTolerance) {
          return {destination,
                  incoming[left],
                  incoming[right],
                  graph.outgoing(destination).front(),
                  left_travel};
        }
      }
    }
  }
  throw std::runtime_error(
      "map2 has no real equal-travel cross-upstream merge");
}

RealUnequalTravelMerge discover_unequal_travel_merge() {
  const auto& graph = canonical_map2().graph;
  for (const int destination : graph.node_locations()) {
    if (graph.incoming_degree(destination) < 2 ||
        graph.outgoing(destination).empty() ||
        graph.service_time(destination) <= 0.0) {
      continue;
    }
    std::vector<int> incoming;
    for (const int upstream : graph.node_locations()) {
      if (graph.has_edge(upstream, destination)) {
        incoming.push_back(upstream);
      }
    }
    std::sort(incoming.begin(), incoming.end());
    for (std::size_t left = 0; left < incoming.size(); ++left) {
      for (std::size_t right = left + 1; right < incoming.size();
           ++right) {
        const double left_travel =
            graph.edge(incoming[left], destination).travel_time();
        const double right_travel =
            graph.edge(incoming[right], destination).travel_time();
        if (std::abs(left_travel - right_travel) <= kTolerance) {
          continue;
        }
        if (left_travel < right_travel) {
          return {destination,
                  incoming[left],
                  incoming[right],
                  graph.outgoing(destination).front(),
                  left_travel,
                  right_travel};
        }
        return {destination,
                incoming[right],
                incoming[left],
                graph.outgoing(destination).front(),
                right_travel,
                left_travel};
      }
    }
  }
  throw std::runtime_error(
      "map2 has no real unequal-travel cross-upstream merge");
}

struct FrozenS1Model {
  std::vector<std::vector<double>> w1;
  std::vector<double> b1;
  std::vector<double> w2;
  double b2 = 0.0;
};

void skip_json_space(const std::string& text,
                     std::size_t& cursor) {
  while (cursor < text.size() &&
         std::isspace(
             static_cast<unsigned char>(text[cursor]))) {
    ++cursor;
  }
}

std::size_t json_value_cursor(const std::string& text,
                              const std::string& key) {
  const auto key_position =
      text.find("\"" + key + "\"");
  if (key_position == std::string::npos) {
    throw std::runtime_error(
        "frozen S1 model is missing key " + key);
  }
  const auto colon = text.find(':', key_position);
  if (colon == std::string::npos) {
    throw std::runtime_error(
        "frozen S1 model key has no value " + key);
  }
  std::size_t cursor = colon + 1;
  skip_json_space(text, cursor);
  return cursor;
}

double parse_json_number(const std::string& text,
                         std::size_t& cursor) {
  skip_json_space(text, cursor);
  char* end = nullptr;
  const double value =
      std::strtod(text.c_str() + cursor, &end);
  if (end == text.c_str() + cursor ||
      !std::isfinite(value)) {
    throw std::runtime_error(
        "frozen S1 model contains an invalid number");
  }
  cursor = static_cast<std::size_t>(
      end - text.c_str());
  return value;
}

std::vector<double> parse_json_number_vector(
    const std::string& text,
    std::size_t& cursor) {
  skip_json_space(text, cursor);
  if (cursor >= text.size() || text[cursor] != '[') {
    throw std::runtime_error(
        "frozen S1 model vector must start with [");
  }
  ++cursor;
  std::vector<double> values;
  while (true) {
    skip_json_space(text, cursor);
    if (cursor >= text.size()) {
      throw std::runtime_error(
          "unterminated frozen S1 vector");
    }
    if (text[cursor] == ']') {
      ++cursor;
      return values;
    }
    values.push_back(parse_json_number(text, cursor));
    skip_json_space(text, cursor);
    if (cursor < text.size() && text[cursor] == ',') {
      ++cursor;
    }
  }
}

std::vector<std::vector<double>>
parse_json_number_matrix(const std::string& text,
                         std::size_t& cursor) {
  skip_json_space(text, cursor);
  if (cursor >= text.size() || text[cursor] != '[') {
    throw std::runtime_error(
        "frozen S1 model matrix must start with [");
  }
  ++cursor;
  std::vector<std::vector<double>> rows;
  while (true) {
    skip_json_space(text, cursor);
    if (cursor >= text.size()) {
      throw std::runtime_error(
          "unterminated frozen S1 matrix");
    }
    if (text[cursor] == ']') {
      ++cursor;
      return rows;
    }
    rows.push_back(
        parse_json_number_vector(text, cursor));
    skip_json_space(text, cursor);
    if (cursor < text.size() && text[cursor] == ',') {
      ++cursor;
    }
  }
}

const FrozenS1Model& frozen_s1_model() {
  static const auto model = [] {
    const auto path =
        std::filesystem::path(CZR005_SOURCE_DIR) /
        "artifacts" / "models" /
        "g4e_risk_calibrated_policy.json";
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
      throw std::runtime_error(
          "cannot open frozen G4E S1 model");
    }
    const std::string text{
        std::istreambuf_iterator<char>{stream},
        std::istreambuf_iterator<char>{}};
    FrozenS1Model parsed;
    auto b1_cursor = json_value_cursor(text, "b1");
    parsed.b1 =
        parse_json_number_vector(text, b1_cursor);
    auto b2_cursor = json_value_cursor(text, "b2");
    parsed.b2 = parse_json_number(text, b2_cursor);
    auto w1_cursor = json_value_cursor(text, "w1");
    parsed.w1 =
        parse_json_number_matrix(text, w1_cursor);
    auto w2_cursor = json_value_cursor(text, "w2");
    parsed.w2 =
        parse_json_number_vector(text, w2_cursor);
    return parsed;
  }();
  return model;
}

EventDrivenJunctionConfig e4_config(bool inject_prepare_failure = false) {
  EventDrivenJunctionConfig config;
  config.resource_semantics = "R3";
  config.event_semantics =
      "E4_batch_plus_destination_merge_request";
  config.enable_backpressure = false;
  config.pressure_mode = "C0";
  config.enable_source_admission = false;
  config.admission_mode = "off";
  config.pibt_mode = "P2";
  config.priority_mode = "Q0";
  config.scorer_mode =
      "S1_frozen_g4e_legal_local_adapter";
  const auto& scorer = frozen_s1_model();
  config.scorer_w1 = scorer.w1;
  config.scorer_b1 = scorer.b1;
  config.scorer_w2 = scorer.w2;
  config.scorer_b2 = scorer.b2;
  config.scorer_model_sha256 =
      "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca";
  config.trace_limit = -1;
  config.event_trace_limit = -1;
  config.enable_opportunity_telemetry = true;
  config.opportunity_trace_limit = 10000;
  config.max_events = 200000;
  config.max_simulation_time = 200.0;
  config.retry_interval = 0.25;
  config.merge_grant_max_pending_requests = 16;
  config.merge_grant_lifecycle_limit = 4096;
#ifdef CZR005_EVENT_RUNTIME_TESTING
  config.test_merge_grant_fail_after_calendar_prepare =
      inject_prepare_failure;
#else
  (void)inject_prepare_failure;
#endif
  return config;
}

double service_duration(int node) {
  return std::max(
      canonical_map2().graph.service_time(node),
      e4_config().minimum_service_seconds);
}

std::vector<EventRuntimeBagRequest> contested_requests(
    const RealEqualTravelMerge& motif,
    bool reverse_input) {
  const double common_request_time = 2.0;
  EventRuntimeBagRequest first;
  first.segment_id = "map2-e4-stable-a";
  first.task_id = 41001;
  first.release_time =
      common_request_time - service_duration(motif.upstream_a);
  first.deadline = 100.0;
  first.start = motif.upstream_a;
  first.goal = motif.goal;
  first.source = "real-map-upstream-a";

  EventRuntimeBagRequest second;
  second.segment_id = "map2-e4-stable-b";
  second.task_id = 41002;
  second.release_time =
      common_request_time - service_duration(motif.upstream_b);
  second.deadline = 100.0;
  second.start = motif.upstream_b;
  second.goal = motif.goal;
  second.source = "real-map-upstream-b";

  std::vector<EventRuntimeBagRequest> requests{
      first, second};
  if (reverse_input) {
    std::reverse(requests.begin(), requests.end());
  }
  return requests;
}

const DestinationMergeGrantLifecycleRow* first_commit_at(
    const EventDrivenJunctionResult& result,
    int destination) {
  const DestinationMergeGrantLifecycleRow* selected = nullptr;
  for (const auto& row : result.merge_grant_lifecycle) {
    if (row.destination_node != destination ||
        row.state != MergeGrantState::kCommitted) {
      continue;
    }
    if (selected == nullptr || row.time < selected->time) {
      selected = &row;
    }
  }
  return selected;
}

int task_for_runtime_bag(const EventDrivenJunctionResult& result,
                         int runtime_bag_id) {
  const auto found = std::find_if(
      result.bags.begin(),
      result.bags.end(),
      [&](const auto& bag) {
        return bag.runtime_bag_id == runtime_bag_id;
      });
  return found == result.bags.end() ? -1 : found->task_id;
}

void check_runtime_hard_gates(Checks& checks,
                              const EventDrivenJunctionResult& result,
                              int expected_bags) {
  checks.require(result.summary.requested_count == expected_bags,
                 "runtime denominator must match");
  checks.require(result.summary.completed_count == expected_bags &&
                     result.summary.failed_count == 0,
                 "all selected real-map bags must drain");
  checks.require(result.summary.reservation_conflicts == 0,
                 "merge protocol must not create reservation conflicts");
  checks.require(
      result.summary.physical_fault_edge_entry_violation_count == 0,
      "physical unsafe entry must remain zero");
  checks.require(result.summary.runtime_full_astar_calls == 0 &&
                     result.summary.global_reservation_scan_count == 0 &&
                     result.summary.two_step_reservation_count == 0,
                 "runtime must remain one-edge/local with no A* or scan");
  checks.require(!result.summary.event_limit_reached &&
                     !result.summary.time_limit_reached,
                 "test must drain without event/time ceiling");
  checks.require(result.summary.stale_arbitration_event_count == 0,
                 "normal merge wakeup cancellation must not create stale arbitration");
  checks.require(result.summary.merge_grant_conservation_holds,
                 "request/grant lifecycle conservation must hold");
  checks.require(
      result.summary.merge_grant_active_bijection_holds,
      "active controller records, bag capabilities, in-transit owners, "
      "and exact calendar intervals must form a bijection");
  checks.require(
      result.summary.merge_grant_request_count ==
          result.summary.merge_grant_committed_count +
              result.summary.merge_grant_terminal_request_count +
              result.summary.merge_grant_outstanding_request_count,
      "request = committed + terminal + outstanding");
  checks.require(
      result.summary.merge_grant_issued_count ==
              result.summary.merge_grant_prepared_count &&
          result.summary.merge_grant_prepared_count ==
              result.summary.merge_grant_committed_count,
      "issued/prepared/committed conservation must hold");
  checks.require(
      result.summary
                  .merge_grant_issued_transition_count ==
              result.summary
                  .merge_grant_prepared_transition_count &&
          result.summary
                  .merge_grant_prepared_transition_count ==
              result.summary
                  .merge_grant_committed_transition_count &&
          result.summary
                  .merge_grant_committed_transition_count ==
              result.summary.merge_grant_committed_count +
                  result.summary
                      .merge_grant_post_commit_revoked_count +
                  result.summary
                      .merge_grant_post_commit_expired_count +
                  result.summary
                      .merge_grant_post_commit_rollback_count,
      "monotone grant transition counters must distinguish live/consumed "
      "commits from post-commit terminal compensation");
  checks.require(
      result.summary.merge_grant_committed_count ==
          result.summary.merge_grant_consumed_count,
      "every drained committed capability must be consumed");
  checks.require(
      result.summary.merge_grant_final_active_unconsumed == 0,
      "a drained runtime must retain no active merge grant");
  checks.require(
      result.summary.merge_grant_lifecycle_stored_count ==
              result.merge_grant_lifecycle.size() &&
          result.summary
                  .merge_grant_lifecycle_transition_count ==
              result.summary
                      .merge_grant_lifecycle_stored_count +
                  result.summary
                      .merge_grant_lifecycle_dropped_count &&
          result.summary.merge_grant_lifecycle_dropped_count == 0,
      "lifecycle transitions must equal stored plus dropped telemetry");
  checks.require(
      result.summary.merge_grant_peak_active_unconsumed <=
          e4_config().merge_grant_max_pending_requests,
      "active capability storage must respect the configured hard bound");
  checks.require(
      result.summary.merge_grant_peak_pending_requests <=
          e4_config().merge_grant_max_pending_requests,
      "pending request storage must respect the configured hard bound");
  std::vector<int> lifecycle_destinations;
  lifecycle_destinations.reserve(
      result.merge_grant_lifecycle.size());
  for (const auto& row :
       result.merge_grant_lifecycle) {
    lifecycle_destinations.push_back(
        row.destination_node);
  }
  std::sort(lifecycle_destinations.begin(),
            lifecycle_destinations.end());
  lifecycle_destinations.erase(
      std::unique(lifecycle_destinations.begin(),
                  lifecycle_destinations.end()),
      lifecycle_destinations.end());
  checks.require(
      result.merge_grant_lifecycle.size() <=
          lifecycle_destinations.size() *
              static_cast<std::size_t>(
                  e4_config()
                      .merge_grant_lifecycle_limit),
      "stored lifecycle rows must respect the per-destination hard bound");
  checks.require(
      result.summary.cpp_internal_accounted_bytes > 0,
      "E4 protocol-owned containers must contribute to accounted memory");
}

void test_exact_calendar_lease(Checks& checks) {
  LocalCalendar calendar;
  calendar.reserve(1, 10.0, 11.0);
  const auto generation = calendar.generation();
  const auto fingerprint =
      calendar.logical_state_fingerprint();
  auto overlapping =
      calendar.prepare_exact_reservation(2, 10.5, 11.5);
  checks.require(!overlapping.has_value(),
                 "busy exact interval must reject instead of shifting");
  checks.require(calendar.generation() == generation,
                 "rejected exact prepare must be a no-op");
  auto exact =
      calendar.prepare_exact_reservation(2, 11.0, 12.0);
  checks.require(exact.has_value(),
                 "non-overlap exact interval must prepare");
  checks.require(
      exact.has_value() &&
          calendar.commit_exact_reservation(std::move(*exact)) &&
          calendar.generation() == generation + 1,
      "prepared exact lease must commit once with monotone generation");
  checks.require(
      calendar.rollback_exact_reservation(
          2, 11.0, 12.0, generation) &&
          calendar.generation() == generation &&
          calendar.logical_state_fingerprint() ==
              fingerprint &&
          !calendar.contains_exact(2, 11.0, 12.0),
      "pre-publication compensation must restore the exact calendar "
      "fingerprint, generation, and interval set");
}

EventDrivenJunctionResult run_contested(
    const RealEqualTravelMerge& motif,
    bool reverse_input,
    bool inject_prepare_failure = false) {
  EventDrivenJunctionRuntime runtime(
      canonical_map2().graph,
      e4_config(inject_prepare_failure));
  return runtime.run(
      contested_requests(motif, reverse_input));
}

void test_real_cross_upstream_protocol(Checks& checks,
                                       const RealEqualTravelMerge& motif) {
  const auto forward = run_contested(motif, false);
  const auto reversed = run_contested(motif, true);
  check_runtime_hard_gates(checks, forward, 2);
  check_runtime_hard_gates(checks, reversed, 2);

  checks.require(
      forward.summary.merge_grant_peak_pending_requests >= 2 &&
          forward.summary.merge_grant_contended_loser_retry_count >= 1,
      "phase5a must expose both real cross-upstream requests before phase5b");
  checks.require(
      forward.summary.merge_grant_runtime_owned_capability &&
          forward.summary.merge_grant_exact_slot_no_future_shift,
      "E4 must declare the real capability/exact-slot boundary");
  checks.require(
      forward.summary.bounded_local_pibt_activation_count == 0 &&
          forward.summary.bounded_local_pibt_attempt_count == 0 &&
          forward.summary.bounded_local_pibt_commit_count == 0,
      "ordinary cross-upstream merge arbitration must not activate P2 "
      "even when P2 is configured");

  const auto* forward_winner =
      first_commit_at(forward, motif.destination);
  const auto* reverse_winner =
      first_commit_at(reversed, motif.destination);
  checks.require(forward_winner != nullptr &&
                     reverse_winner != nullptr,
                 "both insertion orders must issue a real grant");
  if (forward_winner != nullptr && reverse_winner != nullptr) {
    const int winner_task =
        task_for_runtime_bag(
            forward, forward_winner->runtime_bag_id);
    checks.require(
        winner_task ==
            task_for_runtime_bag(
                reversed, reverse_winner->runtime_bag_id),
        "M1 simultaneous tie must be independent of event/input insertion order");
    const int first_loser_task =
        winner_task == 41001 ? 41002 : 41001;
    const auto loser = std::find_if(
        forward.bags.begin(),
        forward.bags.end(),
        [&](const auto& row) {
          return row.task_id == first_loser_task;
        });
    checks.require(
        loser != forward.bags.end() &&
            loser->merge_grant_wait_seconds > 0.0 &&
            loser->merge_grant_wait_seconds <=
                loser->junction_queue_wait_seconds +
                    kTolerance,
        "loser retry grant-wait must accumulate from first contention "
        "and remain a subset of junction wait");
  }

  const auto visibility = std::find_if(
      forward.merge_request_visibility.begin(),
      forward.merge_request_visibility.end(),
      [&](const auto& row) {
        return row.destination_node == motif.destination &&
               row.known_competing_request_count > 0;
      });
  checks.require(
      visibility !=
              forward.merge_request_visibility.end() &&
          visibility->known_competing_request_count == 1 &&
          visibility->later_same_time_competitor_count == 0 &&
          !visibility->seq_determined_order,
      "phase5b visibility must expose the complete ready set and "
      "must not attribute M1 ordering to event sequence");
  const auto audit = std::find_if(
      forward.event_seq_ordering_audit.begin(),
      forward.event_seq_ordering_audit.end(),
      [&](const auto& row) {
        return row.boundary ==
                   "destination_slot_reservation" &&
               row.destination_node == motif.destination &&
               row.ready_set_size == 2;
      });
  checks.require(
      audit != forward.event_seq_ordering_audit.end() &&
          !audit->seq_determined_order &&
          audit->reason ==
              "M1_stable_rule_not_event_seq",
      "destination arbitration audit must name the stable M1 rule");

  std::map<std::uint64_t, DestinationMergeGrantLifecycleRow>
      requested;
  for (const auto& row : forward.merge_grant_lifecycle) {
    if (row.state == MergeGrantState::kRequested) {
      requested[row.request_id] = row;
    }
  }
  for (const auto& row : forward.merge_grant_lifecycle) {
    const auto request = requested.find(row.request_id);
    if (request != requested.end()) {
      const auto& original = request->second;
      checks.require(
          row.task_id == original.task_id &&
              row.segment_id &&
              original.segment_id &&
              *row.segment_id == *original.segment_id &&
              row.junction_queue_generation ==
                  original.junction_queue_generation &&
              row.request_time == original.request_time &&
              row.fifo_request_time ==
                  original.fifo_request_time &&
              row.earliest_edge_entry ==
                  original.earliest_edge_entry &&
              row.exact_edge_travel_seconds ==
                  original.exact_edge_travel_seconds &&
              row.projected_arrival ==
                  original.projected_arrival &&
              row.goal == original.goal &&
              row.route_score == original.route_score &&
              row.static_remaining ==
                  original.static_remaining &&
              row.destination_service_seconds ==
                  original.destination_service_seconds &&
              row.downstream_queue_pressure ==
                  original.downstream_queue_pressure &&
              row.deadline_slack ==
                  original.deadline_slack &&
              row.wait_age == original.wait_age &&
              row.task_class_code ==
                  original.task_class_code &&
              row.task_class == original.task_class &&
              row.storage_leg == original.storage_leg &&
              row.source_release_age ==
                  original.source_release_age &&
              row.local_queue_age ==
                  original.local_queue_age &&
              row.enqueue_sequence ==
                  original.enqueue_sequence &&
              row.request_expiry ==
                  original.request_expiry,
          "every lifecycle transition, including consume, must retain the "
          "complete immutable 8.2 request snapshot");
    }
    if (row.state != MergeGrantState::kCommitted) {
      continue;
    }
    checks.require(request != requested.end(),
                   "every commit must bind a stored request");
    if (request == requested.end()) {
      continue;
    }
    const double exact_travel =
        canonical_map2().graph
            .edge(row.edge.from_node, row.edge.to_node)
            .travel_time();
    checks.require(
        std::abs(
            row.slot_start -
            (request->second.time + exact_travel)) <=
            kTolerance,
        "slot_start must equal request_time + exact map2 edge travel");
    checks.require(
        std::abs(
            row.slot_end - row.slot_start -
            service_duration(row.destination_node)) <=
            kTolerance,
        "slot_end must use exact frozen R3 destination service");
    checks.require(
        row.issue_time == row.time &&
            row.grant_expiry == row.slot_end,
        "issued grant lifecycle must retain exact issue time and expiry");
  }
}

void test_real_unequal_travel_multi_active(
    Checks& checks,
    const RealUnequalTravelMerge& motif) {
  const double common_request_time = 2.0;
  EventRuntimeBagRequest short_request;
  short_request.segment_id = "map2-e4-short-active";
  short_request.task_id = 43001;
  short_request.release_time =
      common_request_time -
      service_duration(motif.short_upstream);
  short_request.deadline = 100.0;
  short_request.start = motif.short_upstream;
  short_request.goal = motif.goal;
  short_request.source = "real-map-short-incoming";

  EventRuntimeBagRequest long_request;
  long_request.segment_id = "map2-e4-long-active";
  long_request.task_id = 43002;
  long_request.release_time =
      common_request_time -
      service_duration(motif.long_upstream);
  long_request.deadline = 100.0;
  long_request.start = motif.long_upstream;
  long_request.goal = motif.goal;
  long_request.source = "real-map-long-incoming";

  auto config = e4_config();
#ifdef CZR005_EVENT_RUNTIME_TESTING
  config.test_merge_grant_advance_live_queue_generation_before_edge_exit =
      true;
  config.test_merge_grant_advance_live_calendar_generation_before_edge_exit =
      true;
#endif
  EventDrivenJunctionRuntime runtime(
      canonical_map2().graph, config);
  const auto result =
      runtime.run({short_request, long_request});
  check_runtime_hard_gates(checks, result, 2);

  std::vector<DestinationMergeGrantLifecycleRow> commits;
  for (const auto& row : result.merge_grant_lifecycle) {
    if (row.destination_node == motif.destination &&
        row.state == MergeGrantState::kCommitted) {
      commits.push_back(row);
    }
  }
  std::sort(
      commits.begin(),
      commits.end(),
      [](const auto& left, const auto& right) {
        return std::tie(left.time, left.grant_id) <
               std::tie(right.time, right.grant_id);
      });
  checks.require(
      commits.size() >= 2,
      "unequal real-map arrivals must both obtain exact grants");
  if (commits.size() >= 2) {
    checks.require(
        commits[0].edge.from_node == motif.short_upstream,
        "M1 stable tie must select the lower-id short-travel request first");
    checks.require(
        commits[0].slot_end <=
                commits[1].slot_start + kTolerance ||
            commits[1].slot_end <=
                commits[0].slot_start + kTolerance,
        "multiple active grants may coexist only on exact non-overlap "
        "half-open service intervals");
    checks.require(
        commits[0].grant_id != commits[1].grant_id &&
            commits[0].lineage != commits[1].lineage,
        "active capability map must retain distinct grant lineage");
  }
  checks.require(
      result.summary.merge_grant_peak_active_unconsumed >= 2,
      "non-overlapping real service intervals must not be serialized "
      "behind a single active-grant latch");
#ifdef CZR005_EVENT_RUNTIME_TESTING
  const bool live_epoch_drift_consumed =
      std::any_of(
          result.merge_grant_lifecycle.begin(),
          result.merge_grant_lifecycle.end(),
          [](const auto& row) {
            return row.state ==
                       MergeGrantState::kConsumed &&
                   row.observed_junction_queue_generation !=
                       row.junction_queue_generation &&
                   row.observed_calendar_generation !=
                       row.calendar_generation &&
                   row.observed_exact_calendar_reservation_present;
          });
  checks.require(
      result.summary.merge_grant_consumed_count == 2 &&
          live_epoch_drift_consumed,
      "live queue/calendar epoch drift must remain audit-only when the "
      "capability identity and exact owner-slot lease remain valid, even "
      "with multiple active non-overlapping grants");
#endif
}

DestinationMergeRequest real_rule_request(
    int upstream,
    int destination,
    std::uint64_t request_id,
    int task_id) {
  const auto& graph = canonical_map2().graph;
  DestinationMergeRequest request;
  request.request_id = request_id;
  request.lineage = request_id;
  request.request_generation = 1;
  request.junction_queue_generation = 1;
  request.runtime_bag_id = task_id;
  request.task_id = task_id;
  request.upstream_node = upstream;
  request.destination_merge_node = destination;
  request.requested_directed_edge = {upstream, destination};
  request.request_time = 10.0;
  request.fifo_request_time = 10.0;
  request.exact_edge_travel_seconds =
      graph.edge(upstream, destination).travel_time();
  request.projected_arrival =
      request.request_time +
      request.exact_edge_travel_seconds;
  request.destination_service_seconds =
      graph.service_time(destination);
  request.deadline_slack = 50.0;
  request.expiry = 1000.0;
  request.enqueue_sequence = request_id;
  return request;
}

void test_real_map_rule_contracts(
    Checks& checks,
    const RealUnequalTravelMerge& motif) {
  const auto prefers =
      [](DestinationMergeGrantRule rule,
         const DestinationMergeRequest& left,
         const DestinationMergeRequest& right,
         double now = 20.0,
         double starvation = 120.0) {
        return destination_merge_request_less(
            rule, left, right, now, starvation);
      };

  auto left = real_rule_request(
      motif.short_upstream, motif.destination, 1, 501);
  auto right = real_rule_request(
      motif.long_upstream, motif.destination, 2, 502);

  left.enqueue_sequence = 1;
  right.enqueue_sequence = 2;
  checks.require(
      prefers(DestinationMergeGrantRule::kM0EarliestKnown,
              left,
              right),
      "M0 must preserve earliest-known/current-sequence control");

  left.fifo_request_time = 9.0;
  right.fifo_request_time = 10.0;
  checks.require(
      prefers(DestinationMergeGrantRule::kM1Fifo,
              left,
              right),
      "M1 must use persistent FIFO contention time");

  left.fifo_request_time = right.fifo_request_time = 10.0;
  checks.require(
      prefers(
          DestinationMergeGrantRule::
              kM2EarliestProjectedArrival,
          left,
          right),
      "M2 must use actual map-edge projected arrival");

  left.deadline_slack = 5.0;
  right.deadline_slack = 20.0;
  checks.require(
      prefers(DestinationMergeGrantRule::kM3DeadlineAging,
              left,
              right),
      "M3 must prefer lower current deadline slack after aging");

  left.wait_age = 20.0;
  right.wait_age = 5.0;
  left.static_remaining = 10.0;
  right.static_remaining = 1.0;
  checks.require(
      prefers(
          DestinationMergeGrantRule::kM4FairnessProgress,
          left,
          right),
      "M4 fairness age must dominate its local route-progress tie break");

  left.wait_age = right.wait_age = 1.0;
  left.downstream_queue_pressure = 0;
  right.downstream_queue_pressure = 10;
  left.route_score = right.route_score = 0.0;
  checks.require(
      prefers(
          DestinationMergeGrantRule::kM5LocalExternality,
          left,
          right),
      "M5 must minimize the one-hop service-clearance/externality proxy");

  left.task_class = right.task_class = 1;
  left.deadline_slack = right.deadline_slack = 10.0;
  left.wait_age = right.wait_age = 2.0;
  left.storage_leg = false;
  right.storage_leg = true;
  checks.require(
      prefers(DestinationMergeGrantRule::kM6ThesisLocal,
              left,
              right),
      "M6 direct/storage tie must be explicit and deterministic");

  left.task_id = 1;
  left.runtime_bag_id = 1;
  left.request_id = 1;
  right.task_id = 2;
  right.runtime_bag_id = 2;
  right.request_id = 2;
  checks.require(
      prefers(DestinationMergeGrantRule::kM1Fifo,
              left,
              right),
      "every rule must end in a unique stable task/bag/edge/request tie");

  left.task_class = 9;
  right.task_class = 0;
  left.fifo_request_time = 0.0;
  right.fifo_request_time = 19.0;
  left.wait_age = 200.0;
  right.wait_age = 1.0;
  checks.require(
      prefers(DestinationMergeGrantRule::kM6ThesisLocal,
              left,
              right,
              200.0,
              120.0),
      "the common starvation band must eventually override non-safety "
      "rule rank");
}

void test_capability_negative_matrix(
    Checks& checks,
    const RealUnequalTravelMerge& motif) {
#ifdef CZR005_EVENT_RUNTIME_TESTING
  auto request = real_rule_request(
      motif.short_upstream,
      motif.destination,
      77,
      46001);
  request.segment_id =
      "map2-capability-negative-matrix";
  request.goal = motif.goal;
  request.route_score = 12.5;
  request.static_remaining = 33.0;
  request.deadline_slack = 17.0;
  request.wait_age = 4.0;
  request.task_class = 2;
  request.storage_leg = true;
  request.source_release_age = 8.0;
  request.local_queue_age = 3.0;
  request.advertised_fault_generation = 2;
  request.physical_fault_generation = 3;
  request.destination_calendar_generation = 7;
  const double slot_start = request.projected_arrival;
  const double slot_end =
      slot_start + service_duration(motif.destination);
  DestinationMergeGrantController controller(
      motif.destination, 4, 32);
  auto capability = controller.test_issue_capability(
      request, slot_start, slot_end, 7, 3);
  const auto exact_edge =
      capability.exact_directed_edge();
  const auto valid_claim =
      [&](const MergeGrantCapability* grant,
          int owner,
          czr005::ics::MergeDirectedEdge edge,
          int destination,
          std::uint64_t request_generation,
          std::uint64_t calendar_generation,
          int physical_generation) {
        return controller.test_validates_capability_claim(
            grant,
            owner,
            edge,
            destination,
            request_generation,
            calendar_generation,
            physical_generation);
      };
  checks.require(
      valid_claim(&capability,
                  capability.owner_runtime_bag_id(),
                  exact_edge,
                  motif.destination,
                  request.request_generation,
                  7,
                  3),
      "the exact runtime-owned capability claim must validate");
  checks.require(
      !valid_claim(nullptr,
                   capability.owner_runtime_bag_id(),
                   exact_edge,
                   motif.destination,
                   request.request_generation,
                   7,
                   3),
      "missing capability must fail closed");
  checks.require(
      !valid_claim(&capability,
                   capability.owner_runtime_bag_id() + 1,
                   exact_edge,
                   motif.destination,
                   request.request_generation,
                   7,
                   3) &&
          !valid_claim(
              &capability,
              capability.owner_runtime_bag_id(),
              {motif.long_upstream, motif.destination},
              motif.destination,
              request.request_generation,
              7,
              3) &&
          !valid_claim(&capability,
                       capability.owner_runtime_bag_id(),
                       exact_edge,
                       motif.destination + 1,
                       request.request_generation,
                       7,
                       3),
      "wrong owner, exact edge, and destination claims must fail closed");
  checks.require(
      !valid_claim(&capability,
                   capability.owner_runtime_bag_id(),
                   exact_edge,
                   motif.destination,
                   request.request_generation + 1,
                   7,
                   3) &&
          !valid_claim(&capability,
                       capability.owner_runtime_bag_id(),
                       exact_edge,
                       motif.destination,
                       request.request_generation,
                       8,
                       3) &&
          !valid_claim(&capability,
                       capability.owner_runtime_bag_id(),
                       exact_edge,
                       motif.destination,
                       request.request_generation,
                       7,
                       4),
      "wrong request, calendar, and physical generations must fail closed");

  auto live_capability = std::move(capability);
  checks.require(
      !valid_claim(&capability,
                   live_capability.owner_runtime_bag_id(),
                   exact_edge,
                   motif.destination,
                   request.request_generation,
                   7,
                   3) &&
          valid_claim(&live_capability,
                      live_capability.owner_runtime_bag_id(),
                      exact_edge,
                      motif.destination,
                      request.request_generation,
                      7,
                      3),
      "a moved-from/stale token must fail while the unique live token "
      "retains authority");
  checks.require(
      controller.test_consume_capability(
          live_capability, slot_start) &&
          !valid_claim(&live_capability,
                       request.runtime_bag_id,
                       exact_edge,
                       motif.destination,
                       request.request_generation,
                       7,
                       3),
      "consumed capability must become terminal and fail re-use");
  const auto& consumed =
      controller.lifecycle().back();
  checks.require(
      consumed.state == MergeGrantState::kConsumed &&
          consumed.task_id == request.task_id &&
          consumed.segment_id &&
          *consumed.segment_id == request.segment_id &&
          consumed.junction_queue_generation ==
              request.junction_queue_generation &&
          consumed.issue_time == slot_start &&
          consumed.grant_expiry == slot_end,
      "consumed lifecycle must retain the original request and exact grant "
      "identity without reconstruction loss");
#else
  (void)checks;
  (void)motif;
#endif
}

void test_terminal_lifecycle_capacity_over_64(
    Checks& checks,
    const RealUnequalTravelMerge& motif) {
#ifdef CZR005_EVENT_RUNTIME_TESTING
  constexpr int kGrantCount = 20;
  constexpr std::size_t kLifecycleLimit = 128;
  DestinationMergeGrantController controller(
      motif.destination, 1, kLifecycleLimit);
  std::set<std::uint64_t> grant_ids;
  for (int index = 0; index < kGrantCount; ++index) {
    auto request = real_rule_request(
        motif.short_upstream,
        motif.destination,
        static_cast<std::uint64_t>(index + 1),
        48000 + index);
    request.segment_id =
        "lifecycle-over-64-" +
        std::to_string(index);
    request.goal = motif.goal;
    request.request_generation =
        static_cast<std::uint64_t>(index + 1);
    request.junction_queue_generation =
        static_cast<std::uint64_t>(index + 1);
    const double slot_start =
        request.projected_arrival +
        10.0 * index;
    const double slot_end =
        slot_start +
        service_duration(motif.destination);
    auto capability =
        controller.test_issue_capability(
            request,
            slot_start,
            slot_end,
            7 + index,
            3 + index);
    grant_ids.insert(capability.grant_id());
    checks.require(
        controller.test_consume_capability(
            capability, slot_start),
        "terminal lifecycle publication after row 64 must consume "
        "without allocation failure");
  }
  checks.require(
      controller.lifecycle().size() ==
              static_cast<std::size_t>(
                  kGrantCount * 5) &&
          controller.lifecycle().size() > 64 &&
          controller.counters()
                  .lifecycle_dropped_count ==
              0 &&
          controller.counters().consumed_count ==
              kGrantCount &&
          controller.counters()
                  .committed_transition_count ==
              kGrantCount &&
          controller.active_unconsumed_count() == 0 &&
          controller.conservation_holds() &&
          grant_ids.size() == kGrantCount,
      "the fully pre-reserved lifecycle hard bound must retain >64 "
      "REQUESTED/ISSUED/PREPARED/COMMITTED/CONSUMED transitions");
#else
  (void)checks;
  (void)motif;
#endif
}

void test_runtime_rule_fail_closed(Checks& checks) {
  for (const std::string rule : {"M7", "M8", "M9"}) {
    auto config = e4_config();
    config.merge_grant_rule = rule;
    bool rejected = false;
    try {
      EventDrivenJunctionRuntime runtime(
          canonical_map2().graph, config);
      (void)runtime;
    } catch (const std::invalid_argument&) {
      rejected = true;
    }
    checks.require(
        rejected,
        rule +
            " must fail closed in online runtime configuration");
  }
}

void test_advertised_generation_precommit_recheck(
    Checks& checks,
    const RealEqualTravelMerge& motif) {
  const auto baseline = run_contested(motif, false);
  const auto* baseline_winner =
      first_commit_at(baseline, motif.destination);
  auto config = e4_config();
#ifdef CZR005_EVENT_RUNTIME_TESTING
  config
      .test_merge_grant_flip_advertised_generation_before_commit =
      true;
#endif
  EventDrivenJunctionRuntime runtime(
      canonical_map2().graph, config);
  const auto result =
      runtime.run(contested_requests(motif, false));
  check_runtime_hard_gates(checks, result, 2);
  const auto* first_commit =
      first_commit_at(result, motif.destination);
  const bool revoked_changed_advertisement =
      std::any_of(
          result.merge_grant_lifecycle.begin(),
          result.merge_grant_lifecycle.end(),
          [](const auto& row) {
            return row.state ==
                       MergeGrantState::kRevokedFault &&
                   row.reason ==
                       MergeGrantReason::
                           kFaultGenerationChanged;
          });
  checks.require(
      revoked_changed_advertisement,
      "advertised generation must be rechecked immediately before commit");
  checks.require(
      baseline_winner != nullptr &&
          first_commit != nullptr &&
          baseline_winner->runtime_bag_id !=
              first_commit->runtime_bag_id,
      "a stale selected request must terminate alone so the healthy "
      "competitor can win the next same-time arbitration");
}

void test_selected_request_recheck_matrix(
    Checks& checks,
    const RealEqualTravelMerge& motif) {
#ifdef CZR005_EVENT_RUNTIME_TESTING
  for (int fault_case = 0; fault_case < 3;
       ++fault_case) {
    auto config = e4_config();
    MergeGrantReason expected_reason =
        MergeGrantReason::kFaultGenerationChanged;
    std::string case_name = "physical";
    if (fault_case == 0) {
      config
          .test_merge_grant_flip_physical_generation_before_commit =
          true;
    } else if (fault_case == 1) {
      config
          .test_merge_grant_flip_calendar_generation_before_commit =
          true;
      expected_reason =
          MergeGrantReason::kCalendarGenerationChanged;
      case_name = "calendar";
    } else {
      config
          .test_merge_grant_flip_queue_generation_before_commit =
          true;
      expected_reason =
          MergeGrantReason::kQueueGenerationChanged;
      case_name = "queue";
    }
    EventDrivenJunctionRuntime runtime(
        canonical_map2().graph, config);
    const auto result =
        runtime.run(contested_requests(motif, false));
    check_runtime_hard_gates(checks, result, 2);
    const auto rejected = std::find_if(
        result.merge_grant_lifecycle.begin(),
        result.merge_grant_lifecycle.end(),
        [&](const auto& row) {
          return row.destination_node ==
                     motif.destination &&
                 row.reason == expected_reason &&
                 (row.state ==
                      MergeGrantState::kRevokedFault ||
                  row.state ==
                      MergeGrantState::kRevokedStaleState);
        });
    const auto committed = std::find_if(
        result.merge_grant_lifecycle.begin(),
        result.merge_grant_lifecycle.end(),
        [&](const auto& row) {
          return row.destination_node ==
                     motif.destination &&
                 row.state ==
                     MergeGrantState::kCommitted;
        });
    checks.require(
        rejected != result.merge_grant_lifecycle.end() &&
            committed != result.merge_grant_lifecycle.end() &&
            rejected->task_id != committed->task_id,
        case_name +
            " precommit change must revoke stale authority while a "
            "healthy real-map competitor eventually commits");
    if (fault_case != 1 &&
        rejected != result.merge_grant_lifecycle.end() &&
        committed != result.merge_grant_lifecycle.end()) {
      checks.require(
          std::abs(rejected->time - committed->time) <=
              kTolerance,
          case_name +
              " selected-only revocation must preserve the healthy "
              "competitor's same-timestamp arbitration");
    }
  }
#else
  (void)checks;
  (void)motif;
#endif
}

void test_task_class_code_mapping(Checks& checks) {
  using czr005::ics::destination_merge_task_class_code;
  checks.require(
      destination_merge_task_class_code(
          true, true, true, true) == 0 &&
          destination_merge_task_class_code(
              false, true, true, true) == 1 &&
          destination_merge_task_class_code(
              false, false, true, true) == 2 &&
          destination_merge_task_class_code(
              false, false, false, true) == 3 &&
          destination_merge_task_class_code(
              false, false, false, false) == 4,
      "merge request task_class_code must retain repaired/fault/storage/"
      "new/on-path semantics independently of the M6 rank");
}

void test_inflight_fault_generation_local_recovery(
    Checks& checks,
    const RealEqualTravelMerge& motif) {
  checks.require(
      motif.travel > 3.0 * kTolerance,
      "real-map recovery fixture must expose a nonzero in-flight window");
  auto requests = contested_requests(motif, false);
  requests.resize(1);
  requests.front().segment_id =
      "edge-exit-inflight-fault-recovery";
  requests.front().task_id = 46999;

  const double edge_entry_time = 2.0;
  const double fault_time =
      edge_entry_time + motif.travel / 3.0;
  const double repair_time =
      edge_entry_time + 2.0 * motif.travel / 3.0;
  EventRuntimeFaultWindow fault;
  fault.start = motif.upstream_a;
  fault.end = motif.destination;
  fault.fault_time = fault_time;
  fault.repair_time = repair_time;
  fault.message_delay = 0.0;
  fault.drop_notification = false;

  EventDrivenJunctionRuntime runtime(
      canonical_map2().graph, e4_config());
  const auto result = runtime.run(requests, {fault});
  check_runtime_hard_gates(checks, result, 1);

  checks.require(
      result.summary.physical_fault_window_traversal_count == 1 &&
          result.summary.physical_fault_edge_entry_violation_count == 0 &&
          result.summary.fault_affected_bag_count == 1 &&
          result.summary.fault_affected_completed_count == 1,
      "a fault beginning after exact EDGE_ENTER must be recorded as one "
      "grandfathered in-flight exposure, never an unsafe entry");
  checks.require(
      result.summary
                  .merge_grant_inflight_fault_generation_recovery_count ==
              1 &&
          result.summary.merge_grant_consumed_count == 1 &&
          result.summary.merge_grant_committed_count == 1 &&
          result.summary.merge_grant_revoked_fault_count == 0 &&
          result.summary.repaired_task_reentry_count == 1,
      "the exact already-entered bag must consume its still-valid local "
      "destination lease through the bounded in-flight recovery path");
  checks.require(
      result.summary.fault_recovery_seconds_available &&
          result.summary.runtime_full_astar_calls == 0 &&
          result.summary.global_reservation_scan_count == 0 &&
          result.summary.two_step_reservation_count == 0 &&
          result.summary.priority_future_route_input_count == 0 &&
          result.summary.priority_global_scan_count == 0,
      "in-flight recovery must retain exact fault-instance evidence without "
      "adding A*, future-route input, or global scans");

  const auto recovered = std::find_if(
      result.merge_grant_lifecycle.begin(),
      result.merge_grant_lifecycle.end(),
      [&](const auto& row) {
        return row.task_id == requests.front().task_id &&
               row.state == MergeGrantState::kConsumed &&
               row.reason ==
                   MergeGrantReason::
                       kConsumedAtDestinationEntryAfterInflightFaultGenerationChange;
      });
  checks.require(
      recovered != result.merge_grant_lifecycle.end() &&
          recovered->edge ==
              czr005::ics::MergeDirectedEdge{
                  motif.upstream_a, motif.destination} &&
          recovered->observed_exact_calendar_reservation_present &&
          recovered->observed_physical_fault_generation >
              recovered->fault_generation &&
          !recovered->observed_physical_fault_active,
      "recovery lifecycle evidence must bind the exact edge/slot and a true "
      "fault generation that was repaired before destination entry");
  const auto recovered_audit = std::find_if(
      result.fault_events.begin(),
      result.fault_events.end(),
      [&](const auto& row) {
        return row.task_id == requests.front().task_id &&
               row.from_node == motif.upstream_a &&
               row.to_node == motif.destination &&
               row.phase ==
                   "destination_merge_inflight_fault_generation_recovered";
      });
  checks.require(
      recovered_audit != result.fault_events.end() &&
          recovered_audit->physical_active_count == 0 &&
          recovered_audit->physical_generation >= 2,
      "fault audit must expose the exact repaired-before-exit recovery event");
}

void test_edge_exit_fail_closed_matrix(
    Checks& checks,
    const RealEqualTravelMerge& motif) {
#ifdef CZR005_EVENT_RUNTIME_TESTING
  constexpr int kCaseCount = 11;
  for (int fault_case = 0;
       fault_case < kCaseCount;
       ++fault_case) {
    auto config = e4_config();
    std::string case_name;
    MergeGrantState terminal_state =
        MergeGrantState::kRevokedStaleState;
    MergeGrantReason terminal_reason =
        MergeGrantReason::kOwnerStateChanged;
    switch (fault_case) {
      case 0:
        case_name = "missing_capability";
        config
            .test_merge_grant_drop_capability_before_edge_exit =
            true;
        break;
      case 1:
        case_name = "physical_generation";
        config
            .test_merge_grant_flip_physical_generation_before_edge_exit =
            true;
        terminal_state = MergeGrantState::kRevokedFault;
        terminal_reason =
            MergeGrantReason::kFaultGenerationChanged;
        break;
      case 2:
        case_name = "advertised_generation";
        config
            .test_merge_grant_flip_advertised_generation_before_edge_exit =
            true;
        terminal_state = MergeGrantState::kRevokedFault;
        terminal_reason =
            MergeGrantReason::kFaultGenerationChanged;
        break;
      case 3:
        case_name = "calendar_missing";
        config
            .test_merge_grant_remove_calendar_before_edge_exit =
            true;
        terminal_reason =
            MergeGrantReason::kCalendarGenerationChanged;
        break;
      case 4:
        case_name = "grant_expired";
        config
            .test_merge_grant_expire_before_edge_exit =
            true;
        terminal_state = MergeGrantState::kExpired;
        terminal_reason =
            MergeGrantReason::
                kGrantExpiredAtDestinationEntry;
        break;
      case 5:
        case_name = "wrong_owner";
        config
            .test_merge_grant_wrong_owner_before_edge_exit =
            true;
        break;
      case 6:
        case_name = "wrong_edge";
        config
            .test_merge_grant_wrong_edge_before_edge_exit =
            true;
        break;
      case 7:
        case_name = "wrong_destination";
        config
            .test_merge_grant_wrong_destination_before_edge_exit =
            true;
        break;
      case 8:
        case_name = "claimed_request_generation_tamper";
        config
            .test_merge_grant_tamper_claimed_request_generation_before_edge_exit =
            true;
        break;
      case 9:
        case_name = "claimed_queue_generation_tamper";
        config
            .test_merge_grant_tamper_claimed_queue_generation_before_edge_exit =
            true;
        break;
      case 10:
        case_name = "claimed_calendar_generation_tamper";
        config
            .test_merge_grant_tamper_claimed_calendar_generation_before_edge_exit =
            true;
        break;
      default:
        throw std::logic_error(
            "unreachable edge-exit matrix case");
    }

    auto requests = contested_requests(motif, false);
    requests.resize(1);
    requests.front().segment_id =
        "edge-exit-fail-closed-" + case_name;
    requests.front().task_id = 47000 + fault_case;
    EventDrivenJunctionRuntime runtime(
        canonical_map2().graph, config);
    const auto result = runtime.run(requests);
    checks.require(
        result.summary.requested_count == 1 &&
            result.summary.completed_count == 0 &&
            result.summary.failed_count == 1 &&
            result.bags.size() == 1 &&
            !result.bags.front().completed &&
            result.bags.front().failure_reason ==
                "destination_merge_grant_rejected_at_edge_exit",
        case_name +
            " must deterministically fail the exact in-transit bag");
    checks.require(
        result.summary.merge_grant_conservation_holds &&
            result.summary
                .merge_grant_active_bijection_holds &&
            result.summary
                    .merge_grant_final_active_unconsumed ==
                0 &&
            result.summary
                    .merge_grant_outstanding_request_count ==
                0 &&
            result.summary
                    .merge_grant_committed_transition_count ==
                1 &&
            result.summary.merge_grant_committed_count == 0 &&
            result.summary.merge_grant_consumed_count == 0 &&
            result.summary
                    .merge_grant_inflight_fault_generation_recovery_count ==
                0,
        case_name +
            " must terminalize the post-commit grant with no ghost "
            "active authority");
    const auto destination = std::find_if(
        result.junctions.begin(),
        result.junctions.end(),
        [&](const auto& row) {
          return row.node == motif.destination;
        });
    checks.require(
        destination != result.junctions.end() &&
            destination
                    ->final_service_calendar_intervals ==
                0 &&
            destination->scheduled_incoming == 0 &&
            destination->final_junction_queue_length == 0,
        case_name +
            " must erase the immutable real grant slot and all incoming "
            "accounting");

    const DestinationMergeGrantLifecycleRow* requested =
        nullptr;
    const DestinationMergeGrantLifecycleRow* committed =
        nullptr;
    const DestinationMergeGrantLifecycleRow* terminal =
        nullptr;
    for (const auto& row :
         result.merge_grant_lifecycle) {
      if (row.task_id != requests.front().task_id) {
        continue;
      }
      if (row.state == MergeGrantState::kRequested) {
        requested = &row;
      } else if (row.state ==
                 MergeGrantState::kCommitted) {
        committed = &row;
      } else if (row.state == terminal_state &&
                 row.reason == terminal_reason) {
        terminal = &row;
      }
    }
    checks.require(
        requested != nullptr &&
            committed != nullptr &&
            terminal != nullptr,
        case_name +
            " must retain REQUESTED, COMMITTED, and exact terminal "
            "audit rows");
    if (requested == nullptr ||
        committed == nullptr ||
        terminal == nullptr) {
      continue;
    }
    const auto same_request =
        [](const auto& left, const auto& right) {
          return left.request_id == right.request_id &&
                 left.lineage == right.lineage &&
                 left.request_generation ==
                     right.request_generation &&
                 left.junction_queue_generation ==
                     right.junction_queue_generation &&
                 left.runtime_bag_id ==
                     right.runtime_bag_id &&
                 left.task_id == right.task_id &&
                 left.segment_id && right.segment_id &&
                 *left.segment_id == *right.segment_id &&
                 left.edge == right.edge &&
                 left.request_time ==
                     right.request_time &&
                 left.fifo_request_time ==
                     right.fifo_request_time &&
                 left.earliest_edge_entry ==
                     right.earliest_edge_entry &&
                 left.exact_edge_travel_seconds ==
                     right.exact_edge_travel_seconds &&
                 left.projected_arrival ==
                     right.projected_arrival &&
                 left.goal == right.goal &&
                 left.route_score == right.route_score &&
                 left.static_remaining ==
                     right.static_remaining &&
                 left.destination_service_seconds ==
                     right.destination_service_seconds &&
                 left.downstream_queue_pressure ==
                     right.downstream_queue_pressure &&
                 left.deadline_slack ==
                     right.deadline_slack &&
                 left.wait_age == right.wait_age &&
                 left.task_class_code ==
                     right.task_class_code &&
                 left.task_class == right.task_class &&
                 left.storage_leg == right.storage_leg &&
                 left.source_release_age ==
                     right.source_release_age &&
                 left.local_queue_age ==
                     right.local_queue_age &&
                 left.enqueue_sequence ==
                     right.enqueue_sequence &&
                 left.request_expiry ==
                     right.request_expiry;
        };
    checks.require(
        same_request(*requested, *committed) &&
            same_request(*requested, *terminal) &&
            terminal->grant_id == committed->grant_id &&
            terminal->slot_start ==
                committed->slot_start &&
            terminal->slot_end ==
                committed->slot_end &&
            terminal->issue_time ==
                committed->issue_time &&
            terminal->grant_expiry ==
                committed->grant_expiry &&
            terminal->calendar_generation ==
                committed->calendar_generation &&
            terminal->fault_generation ==
                committed->fault_generation &&
            terminal->advertised_fault_generation ==
                committed
                    ->advertised_fault_generation,
        case_name +
            " terminal transition must retain the complete immutable "
            "request/grant identity even when the capability is missing");

    bool mismatch_audited = true;
    if (fault_case == 1) {
      mismatch_audited =
          terminal
              ->observed_physical_fault_generation !=
          terminal->fault_generation;
    } else if (fault_case == 2) {
      mismatch_audited =
          terminal
              ->observed_advertised_fault_generation !=
          terminal->advertised_fault_generation;
    } else if (fault_case == 3) {
      mismatch_audited =
          !terminal
               ->observed_exact_calendar_reservation_present;
    } else if (fault_case == 5) {
      mismatch_audited =
          terminal
              ->observed_claimed_owner_runtime_bag_id !=
          terminal->runtime_bag_id;
    } else if (fault_case == 6) {
      mismatch_audited =
          terminal->observed_claimed_edge !=
          terminal->edge;
    } else if (fault_case == 7) {
      mismatch_audited =
          terminal
              ->observed_claimed_destination_node !=
          terminal->destination_node;
    } else if (fault_case == 8) {
      mismatch_audited =
          terminal
              ->observed_claimed_request_generation !=
          terminal->request_generation;
    } else if (fault_case == 9) {
      mismatch_audited =
          terminal
              ->observed_claimed_junction_queue_generation !=
          terminal->junction_queue_generation;
    } else if (fault_case == 10) {
      mismatch_audited =
          terminal
              ->observed_claimed_calendar_generation !=
          terminal->calendar_generation;
    } else if (fault_case == 4) {
      mismatch_audited =
          terminal->reason ==
                  MergeGrantReason::
                      kGrantExpiredAtDestinationEntry &&
          terminal->request_expiry !=
              terminal->grant_expiry &&
          result.summary
                  .merge_grant_grant_expired_count ==
              1 &&
          result.summary
                  .merge_grant_request_expired_count ==
              0;
    }
    checks.require(
        mismatch_audited,
        case_name +
            " terminal audit must expose the observed mismatch, not "
            "only a generic terminal state");
  }
#else
  (void)checks;
  (void)motif;
#endif
}

bool real_map_reaches(int start, int goal) {
  const auto& graph = canonical_map2().graph;
  std::queue<int> pending;
  std::set<int> visited;
  pending.push(start);
  visited.insert(start);
  while (!pending.empty()) {
    const int node = pending.front();
    pending.pop();
    if (node == goal) {
      return true;
    }
    for (const int next : graph.outgoing(node)) {
      if (visited.insert(next).second) {
        pending.push(next);
      }
    }
  }
  return false;
}

int probe_frozen_s1_first_choice(int start, int goal) {
  auto config = e4_config();
  config.pibt_mode = "P0";
  config.enable_pibt_lite = false;
  config.enable_fault_policy = false;
  config.max_simulation_time = 500.0;
  EventRuntimeBagRequest probe;
  probe.segment_id =
      "map2-auto-discovery-s1-probe-" +
      std::to_string(start) + "-" +
      std::to_string(goal);
  probe.task_id = 43900 + start;
  probe.release_time = 0.0;
  probe.deadline = 1000.0;
  probe.start = start;
  probe.goal = goal;
  probe.source = "map2-auto-discovery";
  EventDrivenJunctionRuntime runtime(
      canonical_map2().graph, config);
  const auto result = runtime.run({probe});
  const auto choice = std::find_if(
      result.decisions.begin(),
      result.decisions.end(),
      [&](const auto& row) {
        return row.current_node == start &&
               row.selected_next >= 0;
      });
  return choice == result.decisions.end()
             ? -1
             : choice->selected_next;
}

struct RealPostGrantPIBTMotif {
  int destination_merge = -1;
  int trigger_upstream = -1;
  int downstream_split = -1;
  int frozen_s1_preferred = -1;
  int safe_alternate = -1;
  int goal = -1;
};

RealPostGrantPIBTMotif
discover_real_post_grant_pibt_motif() {
  const auto& fixture = canonical_map2();
  const auto& graph = fixture.graph;
  for (const int destination :
       graph.node_locations()) {
    if (graph.incoming_degree(destination) < 2 ||
        graph.outgoing(destination).size() != 1) {
      continue;
    }
    const int split =
        graph.outgoing(destination).front();
    if (graph.outgoing(split).size() < 2) {
      continue;
    }
    std::vector<int> incoming;
    for (const int node : graph.node_locations()) {
      if (graph.has_edge(node, destination)) {
        incoming.push_back(node);
      }
    }
    for (const int goal : fixture.end_nodes) {
      const int preferred =
          probe_frozen_s1_first_choice(split, goal);
      if (!graph.has_edge(split, preferred) ||
          !real_map_reaches(preferred, goal)) {
        continue;
      }
      int alternate = -1;
      for (const int candidate :
           graph.outgoing(split)) {
        if (candidate != preferred &&
            graph.incoming_degree(candidate) <= 1 &&
            real_map_reaches(candidate, goal)) {
          alternate = candidate;
          break;
        }
      }
      if (alternate < 0) {
        continue;
      }
      for (const int upstream : incoming) {
        if (graph.outgoing(upstream).size() == 1 ||
            probe_frozen_s1_first_choice(
                upstream, goal) == destination) {
          return {destination,
                  upstream,
                  split,
                  preferred,
                  alternate,
                  goal};
        }
      }
    }
  }
  throw std::runtime_error(
      "map2 has no auto-discovered depth-2 post-grant P2 motif");
}

std::vector<EventRuntimeBagRequest>
post_grant_pibt_requests(
    const RealPostGrantPIBTMotif& motif) {
  const double common_ready_time = 2.0;
  EventRuntimeBagRequest downstream_blocker;
  downstream_blocker.segment_id =
      "map2-post-grant-downstream-blocker";
  downstream_blocker.task_id = 44001;
  downstream_blocker.release_time =
      common_ready_time -
      service_duration(motif.downstream_split);
  downstream_blocker.deadline = 1000.0;
  downstream_blocker.start = motif.downstream_split;
  downstream_blocker.goal = motif.goal;
  downstream_blocker.source =
      "real-map-downstream-blocker";

  EventRuntimeBagRequest destination_blocker;
  destination_blocker.segment_id =
      "map2-post-grant-destination-blocker";
  destination_blocker.task_id = 44002;
  destination_blocker.release_time =
      common_ready_time -
      service_duration(motif.destination_merge);
  destination_blocker.deadline = 1000.0;
  destination_blocker.start =
      motif.destination_merge;
  destination_blocker.goal = motif.goal;
  destination_blocker.source =
      "real-map-destination-blocker";

  EventRuntimeBagRequest trigger;
  trigger.segment_id =
      "map2-post-grant-authorized-trigger";
  trigger.task_id = 44003;
  trigger.release_time =
      common_ready_time -
      service_duration(motif.trigger_upstream);
  trigger.deadline = 1000.0;
  trigger.start = motif.trigger_upstream;
  trigger.goal = motif.goal;
  trigger.source = "real-map-authorized-trigger";
  return {downstream_blocker,
          destination_blocker,
          trigger};
}

std::vector<EventRuntimeFaultWindow>
post_grant_pibt_faults(
    const RealPostGrantPIBTMotif& motif,
    bool block_all_split_edges) {
  std::vector<EventRuntimeFaultWindow> faults;
  for (const int next :
       canonical_map2().graph.outgoing(
           motif.downstream_split)) {
    if (!block_all_split_edges &&
        next != motif.frozen_s1_preferred) {
      continue;
    }
    EventRuntimeFaultWindow fault;
    fault.start = motif.downstream_split;
    fault.end = next;
    fault.fault_time = 0.0;
    fault.repair_time = 8.0;
    fault.message_delay = 0.0;
    fault.drop_notification = false;
    faults.push_back(fault);
  }
  return faults;
}

EventDrivenJunctionResult run_post_grant_pibt(
    const RealPostGrantPIBTMotif& motif,
    bool block_all_split_edges,
    bool fail_after_commit = false) {
  auto config = e4_config();
  config.local_queue_capacity = 1;
  config.enable_pibt_lite = false;
  config.enable_fault_policy = false;
  config.max_simulation_time = 500.0;
#ifdef CZR005_EVENT_RUNTIME_TESTING
  config.test_pibt_fail_after_commit_before_publication =
      fail_after_commit;
  config.test_verify_pibt_rollback_logical_state =
      fail_after_commit;
#else
  (void)fail_after_commit;
#endif
  EventDrivenJunctionRuntime runtime(
      canonical_map2().graph, config);
  return runtime.run(
      post_grant_pibt_requests(motif),
      post_grant_pibt_faults(
          motif, block_all_split_edges));
}

void test_post_grant_pibt_no_alternative_prefilter(
    Checks& checks,
    const RealPostGrantPIBTMotif& motif) {
  const auto result =
      run_post_grant_pibt(motif, true);
  check_runtime_hard_gates(checks, result, 3);
  const bool committed_before_repair =
      std::any_of(
          result.pibt_events.begin(),
          result.pibt_events.end(),
          [](const auto& row) {
            return row.time < 8.0 - kTolerance &&
                   row.committed_action_count > 0;
          });
  checks.require(
      !committed_before_repair,
      "a blocker without a safe alternate must be rejected by the "
      "feasibility prefilter before any pre-repair P2 commit");
  checks.require(
      result.summary.merge_grant_queue_capacity_block_count > 0 &&
          result.summary.merge_grant_rolled_back_count > 0 &&
          std::any_of(
              result.merge_grant_lifecycle.begin(),
              result.merge_grant_lifecycle.end(),
              [](const auto& row) {
                return row.task_id == 44003 &&
                       row.time <
                           8.0 - kTolerance &&
                       row.state ==
                           MergeGrantState::kRolledBack &&
                       row.reason ==
                           MergeGrantReason::
                               kQueueCapacityBlock;
              }),
      "a speculative capability must be terminally compensated when "
      "the real blocker has no pre-repair safe alternate");
  const auto destination = std::find_if(
      result.junctions.begin(),
      result.junctions.end(),
      [&](const auto& row) {
        return row.node ==
               motif.destination_merge;
      });
  checks.require(
      destination != result.junctions.end() &&
          destination->final_service_calendar_intervals == 0 &&
          destination->scheduled_incoming == 0,
      "failed post-grant P2 compensation must leave no ghost service "
      "calendar reservation");
}

void test_post_grant_pibt_authority(
    Checks& checks,
    const RealPostGrantPIBTMotif& motif) {
  const auto result =
      run_post_grant_pibt(motif, false);
  check_runtime_hard_gates(checks, result, 3);
  const bool real_chain_committed =
      result.summary.bounded_local_pibt_activation_count >= 1 &&
          result.summary
                  .bounded_local_pibt_committed_batch_count >=
              1 &&
          result.summary
                  .bounded_local_pibt_committed_action_count >=
              3 &&
          result.summary
                  .pibt_max_depth ==
              2;
  if (!real_chain_committed) {
    std::cerr
        << "P2 motif diagnostic merge="
        << motif.destination_merge
        << " upstream=" << motif.trigger_upstream
        << " split=" << motif.downstream_split
        << " faulted=" << motif.frozen_s1_preferred
        << " alternate=" << motif.safe_alternate
        << " goal=" << motif.goal
        << " activations="
        << result.summary.bounded_local_pibt_activation_count
        << " commits="
        << result.summary
               .bounded_local_pibt_committed_batch_count
        << " actions="
        << result.summary
               .bounded_local_pibt_committed_action_count
        << " depth="
        << result.summary.pibt_max_depth
        << '\n';
    for (const auto& audit : result.pibt_events) {
      std::cerr << "  audit time=" << audit.time
                << " outcome=" << audit.outcome
                << " blocker=" << audit.blocker
                << " actions="
                << audit.committed_action_count << '\n';
    }
  }
  checks.require(
      real_chain_committed,
      "the auto-discovered map2 chain must commit the trigger plus two "
      "real blocker moves through the formal P2 resolver");
  const auto grant_commit = std::find_if(
      result.merge_grant_lifecycle.begin(),
      result.merge_grant_lifecycle.end(),
      [](const auto& row) {
        return row.task_id == 44003 &&
               row.state == MergeGrantState::kCommitted;
      });
  const auto pibt_commit = std::find_if(
      result.pibt_events.begin(),
      result.pibt_events.end(),
      [](const auto& row) {
        return row.committed_action_count >= 3;
      });
  checks.require(
      grant_commit != result.merge_grant_lifecycle.end() &&
          pibt_commit != result.pibt_events.end() &&
          grant_commit->time <=
              pibt_commit->time + kTolerance,
      "P2 publication must be causally downstream of a committed "
      "destination grant");
  if (pibt_commit != result.pibt_events.end()) {
    const auto has_action =
        [&](int from, int to) {
          return std::any_of(
              pibt_commit->actions.begin(),
              pibt_commit->actions.end(),
              [&](const auto& action) {
                return action.from_node == from &&
                       action.next_node == to;
              });
        };
    checks.require(
        has_action(motif.trigger_upstream,
                   motif.destination_merge) &&
            has_action(motif.destination_merge,
                       motif.downstream_split) &&
            has_action(motif.downstream_split,
                       motif.safe_alternate),
        "the committed resolver batch must contain the exact grant edge "
        "and both auto-discovered real map2 blocker handoffs");
  }
  checks.require(
      result.summary.physical_fault_edge_entry_violation_count == 0,
      "the blocker alternate and exact grant action must preserve the "
      "physical interlock");
}

void test_post_commit_pibt_rollback_fingerprint(
    Checks& checks,
    const RealPostGrantPIBTMotif& motif) {
  const auto result =
      run_post_grant_pibt(motif, false, true);
  check_runtime_hard_gates(checks, result, 3);
  checks.require(
      result.summary
              .bounded_local_pibt_post_commit_failure_injection_count ==
              1 &&
          result.summary
                  .bounded_local_pibt_rollback_fingerprint_match_count ==
              1 &&
          result.summary
                  .bounded_local_pibt_rollback_calendar_generation_match_count ==
              1,
      "the post-commit exception must pass through the rollback catch only "
      "after a real resolver commit and restore the exact batch fingerprint "
      "and every touched calendar generation");
  checks.require(
      result.summary
              .bounded_local_pibt_max_transaction_calendar_generation_entries >
              0 &&
          result.summary
                  .bounded_local_pibt_max_transaction_calendar_generation_entries <=
              result.summary
                      .bounded_local_pibt_max_transaction_action_deltas *
                  3,
      "calendar rollback snapshots must retain only O(actions) generation "
      "scalars, never full calendar vectors");
  const bool compensated =
      std::any_of(
          result.merge_grant_lifecycle.begin(),
          result.merge_grant_lifecycle.end(),
          [](const auto& row) {
            return row.task_id == 44003 &&
                   row.state ==
                       MergeGrantState::kRolledBack &&
                   row.reason ==
                       MergeGrantReason::kQueueCapacityBlock;
          });
  checks.require(
      compensated &&
          result.summary.merge_grant_active_bijection_holds,
      "post-commit batch rollback must be followed by exact grant/calendar "
      "compensation with no ghost authority");
}

void test_prepare_rollback_is_logical_noop(
    Checks& checks,
    const RealEqualTravelMerge& motif) {
  const auto result = run_contested(motif, false, true);
  check_runtime_hard_gates(checks, result, 2);
  const bool injected = std::any_of(
      result.merge_grant_lifecycle.begin(),
      result.merge_grant_lifecycle.end(),
      [](const auto& row) {
        return row.state == MergeGrantState::kRolledBack &&
               row.reason ==
                   MergeGrantReason::kInjectedPrepareRollback;
      });
  checks.require(injected,
                 "native throwpoint must exercise prepared rollback");

  std::uint64_t destination_commits = 0;
  for (const auto& row : result.merge_grant_lifecycle) {
    if (row.destination_node == motif.destination &&
        row.state == MergeGrantState::kCommitted) {
      ++destination_commits;
    }
  }
  const auto junction = std::find_if(
      result.junctions.begin(),
      result.junctions.end(),
      [&](const auto& row) {
        return row.node == motif.destination;
      });
  checks.require(
      junction != result.junctions.end() &&
          junction->service_reservation_count ==
              destination_commits,
      "prepare rollback must leave no ghost calendar reservation");
}

void test_tiny_protocol_limits(
    Checks& checks,
    const RealEqualTravelMerge& motif) {
  for (const int lifecycle_limit : {0, 1, 4}) {
    auto config = e4_config();
    config.merge_grant_max_pending_requests = 1;
    config.merge_grant_lifecycle_limit =
        lifecycle_limit;
    EventRuntimeBagRequest request;
    request.segment_id =
        "tiny-merge-lifecycle-" +
        std::to_string(lifecycle_limit);
    request.task_id = 45000 + lifecycle_limit;
    request.release_time = 0.0;
    request.deadline = 100.0;
    request.start = motif.upstream_a;
    request.goal = motif.goal;
    request.source = "tiny-protocol-limit";
    EventDrivenJunctionRuntime runtime(
        canonical_map2().graph, config);
    const auto result = runtime.run({request});
    checks.require(
        result.summary.completed_count == 1 &&
            result.summary.failed_count == 0 &&
            result.summary
                    .merge_grant_outstanding_request_count ==
                0 &&
            result.summary.merge_grant_committed_count ==
                result.summary.merge_grant_consumed_count &&
            result.summary.merge_grant_conservation_holds &&
            result.summary
                .merge_grant_active_bijection_holds,
        "tiny bounded protocol configurations must drain pending and "
        "active capability state");
    checks.require(
        result.merge_grant_lifecycle.size() <=
                static_cast<std::size_t>(
                    lifecycle_limit) &&
            result.summary
                    .merge_grant_lifecycle_transition_count ==
                result.summary
                        .merge_grant_lifecycle_stored_count +
                    result.summary
                        .merge_grant_lifecycle_dropped_count &&
            result.summary.merge_grant_peak_pending_requests <=
                1,
        "lifecycle limits 0/1/small and pending bound 1 must be "
        "strictly enforced");
  }
}

void test_r3_goal_exempt_bypass(Checks& checks) {
  const auto& graph = canonical_map2().graph;
  int goal = -1;
  int upstream = -1;
  for (const int candidate : graph.node_locations()) {
    if (graph.incoming_degree(candidate) < 2) {
      continue;
    }
    for (const int source : graph.node_locations()) {
      if (graph.has_edge(source, candidate)) {
        goal = candidate;
        upstream = source;
        break;
      }
    }
    if (goal >= 0) {
      break;
    }
  }
  checks.require(goal >= 0 && upstream >= 0,
                 "map2 must expose a real merge-goal edge");
  EventRuntimeBagRequest request;
  request.segment_id = "map2-e4-goal-exempt";
  request.task_id = 42001;
  request.release_time = 0.0;
  request.deadline = 100.0;
  request.start = upstream;
  request.goal = goal;
  request.source = "real-map-goal-exempt";
  EventDrivenJunctionRuntime runtime(graph, e4_config());
  const auto result = runtime.run({request});
  check_runtime_hard_gates(checks, result, 1);
  checks.require(
      result.summary.merge_grant_goal_exempt_bypass_count >= 1 &&
          result.summary.merge_grant_request_count == 0,
      "R3 actual-goal edge must bypass merge grant/calendar");
}

}  // namespace

int main() {
  Checks checks;
  const auto motif = discover_equal_travel_merge();
  const auto unequal_motif = discover_unequal_travel_merge();
  const auto pibt_motif =
      discover_real_post_grant_pibt_motif();
  test_exact_calendar_lease(checks);
  test_real_cross_upstream_protocol(checks, motif);
  test_real_unequal_travel_multi_active(
      checks, unequal_motif);
  test_real_map_rule_contracts(
      checks, unequal_motif);
  test_capability_negative_matrix(
      checks, unequal_motif);
  test_terminal_lifecycle_capacity_over_64(
      checks, unequal_motif);
  test_task_class_code_mapping(checks);
  test_runtime_rule_fail_closed(checks);
  test_advertised_generation_precommit_recheck(
      checks, motif);
  test_selected_request_recheck_matrix(
      checks, motif);
  test_inflight_fault_generation_local_recovery(
      checks, motif);
  test_edge_exit_fail_closed_matrix(
      checks, motif);
  test_post_grant_pibt_authority(
      checks, pibt_motif);
  test_post_grant_pibt_no_alternative_prefilter(
      checks, pibt_motif);
  test_post_commit_pibt_rollback_fingerprint(
      checks, pibt_motif);
  test_prepare_rollback_is_logical_noop(checks, motif);
  test_tiny_protocol_limits(checks, motif);
  test_r3_goal_exempt_bypass(checks);
  if (checks.failures != 0) {
    std::cerr << checks.failures
              << " destination merge runtime checks failed\n";
    return 1;
  }
  std::cout
      << "Destination-owned E4 real-map runtime checks passed"
      << " destination=" << motif.destination
      << " upstream_a=" << motif.upstream_a
      << " upstream_b=" << motif.upstream_b
      << " exact_travel=" << motif.travel
      << " unequal_destination="
      << unequal_motif.destination
      << " short_travel="
      << unequal_motif.short_travel
      << " long_travel="
      << unequal_motif.long_travel
      << " pibt_merge="
      << pibt_motif.destination_merge
      << " pibt_trigger_upstream="
      << pibt_motif.trigger_upstream
      << " pibt_downstream_split="
      << pibt_motif.downstream_split
      << " pibt_faulted_preferred="
      << pibt_motif.frozen_s1_preferred
      << " pibt_safe_alternate="
      << pibt_motif.safe_alternate
      << " pibt_goal=" << pibt_motif.goal
      << " scorer_model_sha256="
      << "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
      << " scorer_feature_count=22"
      << " map_sha256="
      << canonical_map2().normalized_sha256
      << '\n';
  return 0;
}
