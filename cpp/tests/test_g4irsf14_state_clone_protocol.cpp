#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"
#include "ics_core/runtime/g4irsf14_state_clone.hpp"

#ifndef CZR005_SOURCE_DIR
#error "CZR005_SOURCE_DIR must identify the repository root"
#endif

#ifndef CZR005_EVENT_RUNTIME_TESTING
#error "state-clone protocol tests require native fail-closed test hooks"
#endif

namespace {

using namespace czr005::ics;

void require(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

template <typename Callable>
void require_invalid(Callable&& callable, const std::string& message) {
  bool rejected = false;
  try {
    callable();
  } catch (const std::invalid_argument&) {
    rejected = true;
  }
  require(rejected, message);
}

template <typename Callable>
void require_logic_error(Callable&& callable,
                         const std::string& message) {
  bool rejected = false;
  try {
    callable();
  } catch (const std::logic_error&) {
    rejected = true;
  }
  require(rejected, message);
}

std::string digest(char byte) {
  return std::string(64U, byte);
}

G4IRSF14RuntimeStateDigests golden_state_digests() {
  return {
      digest('0'), digest('1'), digest('2'), digest('3'), digest('4'),
      digest('5'), digest('6'), digest('7'), digest('8'), digest('9'),
      digest('a'), digest('b'), digest('c'), digest('d'), digest('e'),
      digest('f'), digest('0'), digest('1')};
}

G4IRSF14CloneBoundary golden_boundary() {
  G4IRSF14CloneBoundary value;
  value.kind = G4IRSF14CloneBoundaryKind::kSourceArbitration;
  value.time = 21600.125;
  value.event_seq = 42;
  value.node = 52;
  value.runtime_bag_id = 101;
  value.baseline_next_node = 53;
  value.baseline_release = true;
  value.baseline_pibt_enabled = false;
  value.pibt_owner_runtime_bag_id = 101;
  value.source_ready_order = {101, 102, 103};
  value.pending_merge_request_order = {9001, 9002, 9003};
  value.legal_next_edges = {51, 53};
  value.state = golden_state_digests();
  value.runtime_state_sha256 = value.state.aggregate_sha256();
  value.queue_top_not_popped = true;
  value.staged_event_sink_empty = true;
  value.reservation_depth = 1;
  value.max_selected_edges_per_bag = 1;
  value.clone_group_id = value.expected_clone_group_id();
  return value;
}

void test_cross_language_v2_golden_vectors() {
  auto boundary = golden_boundary();
  require(
      boundary.runtime_state_sha256 ==
          "9f0b94609fe67626b80f2f7af88d895f"
          "daccbf69ef8baf807fd34da1074b5aac",
      "C++ state inventory must match the Python v2 binary golden");
  require(
      boundary.clone_group_id ==
          "6651d8a2f2d69c967f163185899b7257"
          "03318c23ed16219929c659f259cfd575",
      "C++ clone-group content address must match Python");
  require(
      boundary.boundary_sha256() ==
          "0d798e3b0d42088b7d25c0e1d699f139"
          "947bd96d2d193dc4e9b50e2fed20c946",
      "C++ boundary digest must match Python");

  G4IRSF14CloneIntervention intervention;
  intervention.kind =
      G4IRSF14CloneInterventionKind::kSourceOrderSwap;
  intervention.horizon = G4IRSF14CloneHorizon::kAffectedBag;
  intervention.runtime_bag_id = 101;
  intervention.peer_runtime_bag_id = 102;
  require(
      intervention.intervention_sha256(boundary) ==
          "8bc39b5db5c37ceb9996054fc8d22fe5"
          "8f623a939e06cae9686e6c794f565cea",
      "C++ intervention digest must match Python");

  boundary.clone_group_id = digest('f');
  require_invalid(
      [&] { boundary.validate(); },
      "self-declared non-content-addressed clone groups must fail");
}

void test_campaign_gate_cannot_be_lowered() {
  G4IRSF14CloneCampaignAudit audit;
  audit.fidelity_clone_count = 1999;
  audit.fidelity_exact_match_count = 1999;
  audit.matched_intervention_count = 1999;
  audit.complete_label_count = 1999;
  audit.selected_system_horizon_count = 1;
  audit.full_runtime_state_clone_used = true;
  require_invalid(
      [&] { audit.validate_for_training_labels(); },
      "native campaign gate must remain fixed at 2000 interventions");
  audit.fidelity_clone_count = 2000;
  audit.fidelity_exact_match_count = 2000;
  audit.matched_intervention_count = 2000;
  audit.complete_label_count = 2000;
  audit.validate_for_training_labels();
}

void test_credit_checkpoint_binds_derived_indices() {
  // NON_FORMAL_UNIT_INTEGRATION_FIXTURE: exact codec/index continuation only.
  ExpiringFirstEdgeCreditLedger ledger(32);
  FirstEdgeCreditIssueRequest request;
  request.from_node = 1;
  request.to_node = 2;
  request.goal = 3;
  request.earliest = 0.0;
  request.latest = 10.0;
  request.generation = 7;
  request.expiry = 10.0;
  request.capacity = 1;
  request.owner_or_unbound = 101;
  request.fault_generation = 4;
  request.now = 0.0;
  request.snapshot_received_at = 0.0;
  request.max_snapshot_age = 1.0;
  request.edge_capacity = 2;
  const auto first = ledger.issue(request);
  request.owner_or_unbound = 102;
  const auto second = ledger.issue(request);
  require(first.accepted && second.accepted,
          "credit codec fixture must create equal-expiry credits");

  const auto checkpoint = ledger.capture_exact_checkpoint();
  auto restored =
      ExpiringFirstEdgeCreditLedger::restore_exact_checkpoint(
          checkpoint);
  require(restored.exact_state_sha256() ==
              ledger.exact_state_sha256(),
          "credit codec must bind every derived index and next id");
  require(ledger.expire_due(11.0) == 2 &&
              restored.expire_due(11.0) == 2 &&
              restored.exact_state_sha256() ==
                  ledger.exact_state_sha256(),
          "equal-expiry continuation order must survive exact restore");

  auto tampered = checkpoint;
  require(!tampered.active_by_owner.empty(),
          "credit checkpoint must expose its owner index");
  ++tampered.active_by_owner.front().second;
  require_invalid(
      [&] {
        (void)ExpiringFirstEdgeCreditLedger::
            restore_exact_checkpoint(tampered);
      },
      "tampered derived credit index must fail closed");
}

const CanonicalMap2ReadResult& canonical_map2() {
  static const auto map = read_canonical_map2_json(
      std::filesystem::path(CZR005_SOURCE_DIR) / "data" / "processed" /
      "maps" / "map2.json");
  return map;
}

struct MergeMotif {
  int destination = -1;
  int upstream_a = -1;
  int upstream_b = -1;
  int goal = -1;
};

MergeMotif discover_real_merge() {
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
        const auto left_time =
            graph.edge(incoming[left], destination).travel_time();
        const auto right_time =
            graph.edge(incoming[right], destination).travel_time();
        if (std::abs(left_time - right_time) <= 1.0e-9) {
          return {destination, incoming[left], incoming[right],
                  graph.outgoing(destination).front()};
        }
      }
    }
  }
  throw std::runtime_error("canonical map2 lacks a real merge fixture");
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
  cursor =
      static_cast<std::size_t>(end - text.c_str());
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

EventDrivenJunctionConfig clone_config() {
  EventDrivenJunctionConfig config;
  config.resource_semantics = "R3";
  config.event_semantics =
      "E4_batch_plus_destination_merge_request";
  config.enable_source_admission = false;
  config.admission_mode = "off";
  config.enable_backpressure = false;
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
  return config;
}

std::vector<EventRuntimeBagRequest> contested_requests(
    const MergeMotif& motif) {
  const auto& graph = canonical_map2().graph;
  const double common_request_time = 2.0;
  const auto make_request = [&](int upstream, int task_id,
                                std::string segment) {
    EventRuntimeBagRequest request;
    request.segment_id = std::move(segment);
    request.task_id = task_id;
    request.release_time =
        common_request_time -
        std::max(graph.service_time(upstream), 1.0e-3);
    request.deadline = 100.0;
    request.start = upstream;
    request.goal = motif.goal;
    request.source = "real-map-clone-fixture";
    return request;
  };
  return {
      make_request(motif.upstream_a, 51001, "clone-real-a"),
      make_request(motif.upstream_b, 51002, "clone-real-b")};
}

EventRuntimeFaultWindow unrelated_long_fault(
    const MergeMotif& motif) {
  const auto& graph = canonical_map2().graph;
  for (const int from : graph.node_locations()) {
    for (const int to : graph.outgoing(from)) {
      if ((from == motif.upstream_a || from == motif.upstream_b) &&
          to == motif.destination) {
        continue;
      }
      if (from == motif.destination && to == motif.goal) {
        continue;
      }
      return {from, to, 0.0, 150.0, 0.1, false};
    }
  }
  throw std::runtime_error("map2 lacks an unrelated fault edge");
}

void test_real_runtime_checkpoint_and_noop_fidelity() {
  // NON_FORMAL_UNIT_INTEGRATION_FIXTURE: the topology is canonical map2 and
  // the runtime path is production E4, but these two constructed requests
  // are mechanism/codec coverage only.  They are never original-task causal
  // evidence and must not be cited by a campaign manifest or report.
  const auto motif = discover_real_merge();
  const auto config = clone_config();
  EventDrivenJunctionRuntime source(canonical_map2().graph, config);
  source.initialize(contested_requests(motif),
                    {unrelated_long_fault(motif)});

  std::optional<EventDrivenJunctionRuntime::StateCheckpoint> checkpoint;
  EventDrivenJunctionSafeBoundary captured_boundary;
  for (int event = 0; event < config.max_events; ++event) {
    const auto boundary = source.peek_safe_boundary();
    if (!boundary.has_value()) {
      break;
    }
    if (boundary->active_merge_capability_count > 0 &&
        boundary->active_physical_fault_edge_count > 0 &&
        boundary->queued_bag_count > 0) {
      captured_boundary = *boundary;
      checkpoint = source.capture_state_checkpoint();
      break;
    }
    require(source.process_one_event(),
            "real-map checkpoint discovery stopped early");
  }
  require(checkpoint.has_value(),
          "real-map checkpoint must contain a live grant, fault, and queue");
  require(captured_boundary.queue_top_not_popped &&
              captured_boundary.staged_event_sink_empty,
          "checkpoint must be captured before pop with no staged sink");
  require(checkpoint->state_sha256() ==
              captured_boundary.state_sha256,
          "peek and checkpoint must bind identical production state");
  const auto public_digests =
      source.deterministic_state_digests();
  public_digests.validate();
  require(public_digests.aggregate_sha256() ==
              checkpoint->state_sha256(),
          "public 18-item state inventory must bind the checkpoint seal");
  require_logic_error(
      [&] {
        (void)source.deterministic_replay_hashes();
      },
      "replay hashes must remain finalized-horizon only");

  EventDrivenJunctionRuntime baseline(canonical_map2().graph, config);
  EventDrivenJunctionRuntime treatment(canonical_map2().graph, config);
  G4IRSF14MatchedRuntimeFork<EventDrivenJunctionRuntime> fork(
      baseline, treatment, *checkpoint);
  require(fork.source_state_sha256() ==
              captured_boundary.state_sha256,
          "both matched branches must restore the captured state");

  source.drain();
  baseline.drain();
  treatment.drain();
  source.finalize();
  baseline.finalize();
  treatment.finalize();
  const auto original_hashes = source.deterministic_replay_hashes();
  const auto baseline_hashes = baseline.deterministic_replay_hashes();
  const auto treatment_hashes =
      treatment.deterministic_replay_hashes();
  require(original_hashes.exactly_matches(baseline_hashes) &&
              original_hashes.exactly_matches(treatment_hashes),
          "original and two no-op restores must match all five hashes");
  require(source.current_result().summary.reservation_conflicts == 0 &&
              baseline.current_result()
                      .summary.physical_fault_edge_entry_violation_count ==
                  0 &&
              treatment.current_result()
                  .summary.merge_grant_conservation_holds,
          "restored branches must preserve production safety invariants");

  std::string previous_hash =
      treatment_hashes.deterministic_result_sha256;
  for (const std::string family : {
           "summary", "decision", "fault", "pibt",
           "source_opportunity", "junction_opportunity",
           "merge_visibility", "event_seq",
           "arbitration_batch", "merge_lifecycle"}) {
    treatment.test_mutate_final_result_hash_field(family);
    const auto changed =
        treatment.deterministic_replay_hashes()
            .deterministic_result_sha256;
    require(changed != previous_hash,
            "deterministic result hash must bind " + family);
    previous_hash = changed;
  }

  auto corrupted = *checkpoint;
  corrupted.test_corrupt_seal();
  EventDrivenJunctionRuntime rejected(canonical_map2().graph, config);
  rejected.initialize(contested_requests(motif),
                      {unrelated_long_fault(motif)});
  require(rejected.phase() ==
              EventDrivenJunctionRuntimePhase::kReady,
          "fail-closed fixture must begin with a processable target");
  require_invalid(
      [&] { rejected.restore_state_checkpoint(corrupted); },
      "tampered checkpoint seal must fail closed");
  require(rejected.phase() == EventDrivenJunctionRuntimePhase::kIdle,
          "failed restore must not leave a processable runtime");
  require_logic_error(
      [&] { (void)rejected.process_one_event(); },
      "failed restore must reject event processing");
  require_logic_error(
      [&] {
        (void)rejected.deterministic_state_digests();
      },
      "failed restore must not expose a live state inventory");

  Graph wrong_graph = canonical_map2().graph;
  EventDrivenJunctionRuntime wrong_runtime(wrong_graph, config);
  // Construct against the audited graph so S1 validation succeeds, then
  // mutate the referenced graph to exercise restore's graph-identity check.
  wrong_graph.node(wrong_graph.node_locations().front()).x += 1;
  require_invalid(
      [&] { wrong_runtime.restore_state_checkpoint(*checkpoint); },
      "checkpoint must reject a different graph identity");
  require(wrong_runtime.phase() ==
              EventDrivenJunctionRuntimePhase::kIdle,
          "graph mismatch must remain fail closed");
}

}  // namespace

int main() {
  try {
    test_cross_language_v2_golden_vectors();
    test_campaign_gate_cannot_be_lowered();
    test_credit_checkpoint_binds_derived_indices();
    test_real_runtime_checkpoint_and_noop_fidelity();
  } catch (const std::exception& error) {
    std::cerr << "G4IRSF14 state-clone protocol test failed: "
              << error.what() << '\n';
    return EXIT_FAILURE;
  }
  std::cout
      << "G4IRSF14 production state-clone tests passed "
         "(NON_FORMAL_UNIT_INTEGRATION_FIXTURE)\n";
  return EXIT_SUCCESS;
}
