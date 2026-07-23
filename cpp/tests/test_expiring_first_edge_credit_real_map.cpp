#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/runtime/event_driven_junction.hpp"
#include "ics_core/runtime/expiring_first_edge_credit.hpp"

#ifndef CZR005_SOURCE_DIR
#error "CZR005_SOURCE_DIR must identify the repository root"
#endif

namespace {

using czr005::ics::EventDrivenJunctionConfig;
using czr005::ics::EventDrivenJunctionRuntime;
using czr005::ics::EventRuntimeBagRequest;
using czr005::ics::ExpiringFirstEdgeCreditLedger;
using czr005::ics::FirstEdgeCreditBatchEntry;
using czr005::ics::FirstEdgeCreditIssueRequest;
using czr005::ics::FirstEdgeCreditState;
using czr005::ics::FirstEdgeCreditUseContext;
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

const czr005::ics::CanonicalMap2ReadResult& canonical_map2() {
  static const auto fixture = [] {
    const auto path = std::filesystem::path(CZR005_SOURCE_DIR) /
                      "data" / "processed" / "maps" / "map2.json";
    return czr005::ics::read_canonical_map2_json(path);
  }();
  return fixture;
}

struct RealSplitMotif {
  int split = -1;
  int first = -1;
  int second = -1;
  int goal = -1;
};

RealSplitMotif choose_real_split_motif() {
  const auto& fixture = canonical_map2();
  const Graph& graph = fixture.graph;
  for (const int node : graph.node_locations()) {
    auto outgoing = graph.outgoing(node);
    if (outgoing.size() < 2) {
      continue;
    }
    std::sort(outgoing.begin(), outgoing.end());
    int best_goal = -1;
    double best_potential = std::numeric_limits<double>::infinity();
    for (const int goal : fixture.end_nodes) {
      const double potential = graph.heuristic(node, goal);
      if (std::isfinite(potential) && potential < best_potential) {
        best_potential = potential;
        best_goal = goal;
      }
    }
    if (best_goal >= 0 && graph.has_edge(node, outgoing[0]) &&
        graph.has_edge(node, outgoing[1])) {
      return RealSplitMotif{node, outgoing[0], outgoing[1], best_goal};
    }
  }
  throw std::runtime_error("canonical map2 has no real split motif");
}

FirstEdgeCreditIssueRequest issue_request(const RealSplitMotif& motif,
                                          int to_node,
                                          int owner,
                                          double now = 0.0) {
  FirstEdgeCreditIssueRequest request;
  request.from_node = motif.split;
  request.to_node = to_node;
  request.goal = motif.goal;
  request.earliest = now + 1.0;
  request.latest = now + 3.0;
  request.generation = 7;
  request.expiry = now + 3.0;
  request.capacity = 1;
  request.owner_or_unbound = owner;
  request.fault_generation = 2;
  request.now = now;
  request.snapshot_received_at = now;
  request.max_snapshot_age = 1.0;
  request.edge_capacity = 1;
  return request;
}

FirstEdgeCreditUseContext use_context(const RealSplitMotif& motif,
                                      int to_node,
                                      int owner,
                                      double now) {
  FirstEdgeCreditUseContext context;
  context.owner = owner;
  context.from_node = motif.split;
  context.to_node = to_node;
  context.goal = motif.goal;
  context.now = now;
  context.generation = 7;
  context.fault_generation = 2;
  return context;
}

void test_issue_bind_consume_duplicate_and_capacity(Checks& checks,
                                                    const RealSplitMotif& motif) {
  ExpiringFirstEdgeCreditLedger ledger;
  const auto issued = ledger.issue(issue_request(motif, motif.first, 101));
  checks.require(issued.accepted && issued.credit.credit_id != 0,
                 "a real map2 edge must receive a unique credit");
  checks.require(issued.credit.from_node == motif.split &&
                     issued.credit.to_node == motif.first &&
                     issued.credit.goal == motif.goal &&
                     issued.credit.earliest == 1.0 &&
                     issued.credit.latest == 3.0 &&
                     issued.credit.generation == 7 &&
                     issued.credit.expiry == 3.0 &&
                     issued.credit.capacity == 1 &&
                     issued.credit.owner_or_unbound == 101 &&
                     issued.credit.fault_generation == 2,
                 "issued credit must retain every required identity and validity field");

  const auto duplicate_owner =
      ledger.issue(issue_request(motif, motif.second, 101));
  checks.require(!duplicate_owner.accepted &&
                     duplicate_owner.reason == "duplicate_owner",
                 "one owner must not hold duplicate active credits");
  const auto capacity =
      ledger.issue(issue_request(motif, motif.first, 102));
  checks.require(!capacity.accepted &&
                     capacity.reason == "capacity_exhausted",
                 "edge credit capacity must be enforced without overbooking");

  const auto early =
      ledger.validate(issued.credit.credit_id,
                      use_context(motif, motif.first, 101, 0.5));
  checks.require(!early.accepted && early.reason == "too_early",
                 "credit use before earliest entry must fail closed");
  const auto bound =
      ledger.bind(issued.credit.credit_id,
                  use_context(motif, motif.first, 101, 1.0));
  checks.require(bound.accepted &&
                     bound.credit.state == FirstEdgeCreditState::kBound,
                 "credit must bind to its subsequent selected first edge");
  const auto duplicate_bind =
      ledger.bind(issued.credit.credit_id,
                  use_context(motif, motif.first, 101, 1.0));
  checks.require(!duplicate_bind.accepted,
                 "a bound credit must not bind twice");
  const auto consumed =
      ledger.consume(issued.credit.credit_id,
                     use_context(motif, motif.first, 101, 1.0));
  checks.require(consumed.accepted &&
                     consumed.credit.state == FirstEdgeCreditState::kConsumed &&
                     ledger.counters().active_count == 0,
                 "selected-edge commit must consume and clear the credit");
  checks.require(!ledger.consume(issued.credit.credit_id,
                                  use_context(motif, motif.first, 101, 1.0))
                       .accepted,
                 "a consumed credit must never be reused");
  checks.require(ledger.find(issued.credit.credit_id) == nullptr,
                 "terminal credits must not remain in the active ledger");
  checks.require(ledger.counters().issued_count == 1 &&
                     ledger.counters().bound_count == 1 &&
                     ledger.counters().consumed_count == 1 &&
                     ledger.counters().duplicate_rejection_count >= 2 &&
                     ledger.counters().unknown_credit_rejection_count >= 1 &&
                     ledger.counters().capacity_rejection_count == 1,
                 "lifecycle counters must expose issue/bind/consume and rejections");
}

void test_expiry_generation_fault_and_stale_snapshot(Checks& checks,
                                                     const RealSplitMotif& motif) {
  {
    ExpiringFirstEdgeCreditLedger ledger;
    auto request = issue_request(motif, motif.first, 201);
    request.earliest = 0.0;
    request.latest = 0.5;
    request.expiry = 0.5;
    const auto issued = ledger.issue(request);
    checks.require(issued.accepted && ledger.expire_due(1.0) == 1,
                   "unused credit must be reclaimed after expiry");
    checks.require(ledger.find(issued.credit.credit_id) == nullptr &&
                       ledger.counters().expired_count == 1 &&
                       !ledger.lifecycle().empty() &&
                       ledger.lifecycle().back().credit.state ==
                           FirstEdgeCreditState::kExpired,
                   "expiry must remove active state and leave bounded audit evidence");
  }
  {
    ExpiringFirstEdgeCreditLedger ledger;
    const auto issued = ledger.issue(issue_request(motif, motif.first, 202));
    checks.require(issued.accepted &&
                       ledger.revoke_destination_generation(motif.first, 8, 0.5) == 1,
                   "credit generation change must revoke the old offer");
    checks.require(ledger.counters().generation_revocation_count == 1,
                   "generation revocation must be counted exactly");
  }
  {
    ExpiringFirstEdgeCreditLedger ledger;
    const auto issued = ledger.issue(issue_request(motif, motif.first, 203));
    checks.require(issued.accepted &&
                       ledger.revoke_edge_fault_generation(
                           motif.split, motif.first, 3, true, 0.5) == 1,
                   "physical fault/fault generation change must revoke edge credit");
    checks.require(ledger.counters().fault_revocation_count == 1,
                   "fault revocation must be counted exactly");
  }
  {
    ExpiringFirstEdgeCreditLedger ledger;
    auto stale = issue_request(motif, motif.first, 204, 5.0);
    stale.snapshot_received_at = 0.0;
    stale.max_snapshot_age = 1.0;
    checks.require(!ledger.issue(stale).accepted &&
                       ledger.counters().stale_snapshot_rejection_count == 1,
                   "stale one-hop snapshot must fail closed");
    auto physical = issue_request(motif, motif.first, 205);
    physical.physical_fault_active = true;
    checks.require(!ledger.issue(physical).accepted &&
                       ledger.counters().physical_fault_rejection_count == 1,
                   "active physical fault must reject issuance independently of policy");
  }
}

void test_active_only_storage_and_bounded_lifecycle(Checks& checks,
                                                    const RealSplitMotif& motif) {
  constexpr std::size_t kLifecycleLimit = 8;
  constexpr int kOperations = 10000;
  ExpiringFirstEdgeCreditLedger ledger(kLifecycleLimit);
  for (int index = 0; index < kOperations; ++index) {
    const double now = static_cast<double>(index) * 4.0;
    auto request =
        issue_request(motif, motif.first, 1000 + index, now);
    const auto issued = ledger.issue(request);
    checks.require(issued.accepted,
                   "bounded stress issue must remain available");
    auto context =
        use_context(motif, motif.first, 1000 + index, now + 1.0);
    const auto bound = ledger.bind(issued.credit.credit_id, context);
    const auto consumed = ledger.consume(issued.credit.credit_id, context);
    checks.require(bound.accepted && consumed.accepted,
                   "bounded stress lifecycle must close atomically");
    checks.require(ledger.stored_active_count() == 0,
                   "terminal credit must be erased after every consume");
  }
  checks.require(ledger.counters().issued_count == kOperations &&
                     ledger.counters().consumed_count == kOperations,
                 "bounded storage must retain exact all-time counters");
  checks.require(ledger.stored_active_count() == 0 &&
                     ledger.stored_lifecycle_count() == kLifecycleLimit &&
                     ledger.lifecycle().size() == kLifecycleLimit &&
                     ledger.counters().lifecycle_dropped_count > 0,
                 "recent lifecycle storage must never exceed its explicit ring limit");
}

void test_copy_and_rollback_rebuild_expiry_iterators(
    Checks& checks,
    const RealSplitMotif& motif) {
  ExpiringFirstEdgeCreditLedger ledger(17);
  auto first_request = issue_request(motif, motif.first, 11001);
  auto second_request = issue_request(motif, motif.second, 11002);
  const auto first = ledger.issue(first_request);
  const auto second = ledger.issue(second_request);
  checks.require(first.accepted && second.accepted,
                 "copy test must begin with two independent active credits");
  const auto first_context =
      use_context(motif, motif.first, 11001, 1.0);
  checks.require(ledger.bind(first.credit.credit_id, first_context).accepted,
                 "copy test must preserve a bound credit as well as an issued credit");

  const ExpiringFirstEdgeCreditLedger snapshot(ledger);
  ExpiringFirstEdgeCreditLedger assigned(1);
  assigned = ledger;
  checks.require(snapshot.lifecycle_limit() == 17 &&
                     assigned.lifecycle_limit() == 17 &&
                     snapshot.stored_active_count() == 2 &&
                     assigned.stored_active_count() == 2,
                 "copy construction and assignment must preserve scalar and active state");

  checks.require(
      ledger.consume(first.credit.credit_id, first_context).accepted &&
          ledger.expire_due(4.0) == 1,
      "mutating the source after snapshot must close both of its own expiry indexes");
  checks.require(ledger.stored_active_count() == 0,
                 "source mutations must not leave active credits");

  auto restored = snapshot;
  checks.require(
      restored.consume(first.credit.credit_id, first_context).accepted &&
          restored.expire_due(4.0) == 1 &&
          restored.stored_active_count() == 0,
      "copy-constructed rollback state must consume and expire through rebuilt iterators");

  ledger = assigned;
  ledger = ledger;
  checks.require(
      ledger.consume(first.credit.credit_id, first_context).accepted &&
          ledger.expire_due(4.0) == 1 &&
          ledger.stored_active_count() == 0,
      "copy-assigned and self-assigned rollback state must own valid expiry iterators");
  checks.require(snapshot.stored_active_count() == 2 &&
                     assigned.stored_active_count() == 2,
                 "independent snapshots must not be mutated through another ledger's indexes");
}

void test_bounded_batch_prevalidates_before_mutation(
    Checks& checks,
    const RealSplitMotif& motif) {
  ExpiringFirstEdgeCreditLedger ledger;
  const auto first =
      ledger.issue(issue_request(motif, motif.first, 12001));
  const auto second =
      ledger.issue(issue_request(motif, motif.second, 12002));
  checks.require(first.accepted && second.accepted,
                 "batch test must issue two independent real-edge credits");
  const auto first_context =
      use_context(motif, motif.first, 12001, 1.0);
  auto wrong_second_context =
      use_context(motif, motif.second, 12002, 1.0);
  wrong_second_context.goal += 1;
  const std::vector<FirstEdgeCreditBatchEntry> invalid_batch{
      {first.credit.credit_id, first_context},
      {second.credit.credit_id, wrong_second_context},
  };
  const auto counters_before = ledger.counters();
  const auto rejected =
      ledger.bind_and_consume_bounded_batch(invalid_batch, 2);
  checks.require(!rejected.accepted &&
                     rejected.reason == "identity_mismatch",
                 "one invalid batch entry must reject the entire bounded batch");
  checks.require(ledger.find(first.credit.credit_id) != nullptr &&
                     ledger.find(second.credit.credit_id) != nullptr &&
                     ledger.find(first.credit.credit_id)->state ==
                         FirstEdgeCreditState::kIssued &&
                     ledger.find(second.credit.credit_id)->state ==
                         FirstEdgeCreditState::kIssued &&
                     ledger.counters().bind_attempt_count ==
                         counters_before.bind_attempt_count &&
                     ledger.counters().consume_attempt_count ==
                         counters_before.consume_attempt_count,
                 "batch rejection must mutate neither credits nor lifecycle counters");

  const std::vector<FirstEdgeCreditBatchEntry> valid_batch{
      {first.credit.credit_id, first_context},
      {second.credit.credit_id,
       use_context(motif, motif.second, 12002, 1.0)},
  };
  checks.require(
      !ledger.bind_and_consume_bounded_batch(valid_batch, 1).accepted,
      "the ledger must enforce the caller's explicit transaction bound");
  const auto committed =
      ledger.bind_and_consume_bounded_batch(valid_batch, 2);
  checks.require(committed.accepted && committed.entry_count == 2 &&
                     ledger.stored_active_count() == 0 &&
                     ledger.counters().bound_count == 2 &&
                     ledger.counters().consumed_count == 2,
                 "a fully prevalidated bounded batch must close all entries exactly once");
}

EventDrivenJunctionConfig runtime_config(const std::string& pressure_mode,
                                         bool enable_backpressure) {
  EventDrivenJunctionConfig config;
  config.resource_semantics = "R3";
  config.pressure_mode = pressure_mode;
  config.admission_mode = "expiring_first_edge_credit";
  config.enable_source_admission = true;
  config.enable_backpressure = enable_backpressure;
  config.enable_pibt_lite = false;
  config.retry_interval = 0.05;
  config.minimum_service_seconds = 0.1;
  config.dispatch_headway_seconds = 0.001;
  config.credit_validity_seconds = 2.0;
  config.credit_snapshot_max_age_seconds = 0.5;
  config.credit_capacity_per_edge = 2;
  config.max_decisions_per_bag = 1000;
  config.max_events = 2000000;
  config.max_simulation_time = 10000.0;
  config.trace_limit = 100000;
  return config;
}

void test_c4_c5_runtime_closed_loop(Checks& checks,
                                    const RealSplitMotif& motif) {
  const auto& graph = canonical_map2().graph;
  const std::vector<EventRuntimeBagRequest> bags{
      {"credit-real-split", 301, 0.0, 10000.0, motif.split, motif.goal,
       "canonical-map2"}};
  for (const auto& mode :
       std::vector<std::pair<std::string, bool>>{{"C0", false}, {"C2", true}}) {
    const auto result =
        EventDrivenJunctionRuntime(graph,
                                   runtime_config(mode.first, mode.second))
            .run(bags);
    const std::string label = mode.first == "C0" ? "C4" : "C5";
    checks.require(result.summary.admission_mode ==
                       "expiring_first_edge_credit",
                   label + " must explicitly enable expiring credit admission");
    checks.require(result.summary.completed_count == 1 &&
                       result.summary.failed_count == 0,
                   label + " must complete its real-map bag");
    checks.require(result.summary.first_edge_credit_issued_count >= 1 &&
                       result.summary.first_edge_credit_bound_count == 1 &&
                       result.summary.first_edge_credit_consumed_count == 1 &&
                       result.summary.first_edge_credit_active_count == 0,
                   label + " must close issue/bind/consume with no leaked credit");
    checks.require(result.summary.runtime_full_astar_calls == 0 &&
                       result.summary.global_reservation_scan_count == 0 &&
                       result.summary.first_edge_credit_future_route_count == 0 &&
                       result.summary.first_edge_credit_global_scan_count == 0 &&
                       !result.summary.first_edge_credit_physical_interlock_bypass,
                   label + " must retain zero A*, global scan, future route, and bypass");
    checks.require(result.summary.max_edges_selected_per_arrive <= 1 &&
                       result.summary.reservation_conflicts == 0 &&
                       result.summary.physical_fault_edge_entry_violation_count == 0,
                   label + " must retain one-edge and physical safety invariants");

    bool saw_bound = false;
    bool saw_consumed = false;
    for (const auto& event : result.credit_events) {
      checks.require(event.from_node >= 0 && event.to_node >= 0 &&
                         graph.has_edge(event.from_node, event.to_node) &&
                         event.goal == motif.goal && event.generation > 0 &&
                         event.latest >= event.earliest &&
                         event.expiry >= event.earliest &&
                         event.capacity > 0 && event.fault_generation >= 0,
                     label + " lifecycle rows must expose valid required fields");
      saw_bound = saw_bound || event.action == "bound";
      saw_consumed = saw_consumed || event.action == "consumed";
    }
    checks.require(saw_bound && saw_consumed,
                   label + " must expose auditable bind and consume rows");

    bool saw_credit_selected_edge = false;
    for (const auto& decision : result.decisions) {
      if (decision.decision_source != "expiring_first_edge_credit") {
        continue;
      }
      saw_credit_selected_edge = true;
      checks.require(decision.current_node == motif.split &&
                         graph.has_edge(decision.current_node,
                                        decision.selected_next),
                     label + " credit must bind one real adjacent selected edge");
      for (const auto& candidate : decision.candidates) {
        if (candidate.next_node == decision.selected_next) {
          checks.require(candidate.first_edge_credit_required &&
                             candidate.first_edge_credit_matches &&
                             candidate.first_edge_credit_valid &&
                             candidate.first_edge_credit_slack_seconds >= 0.0,
                         label + " selected candidate must expose valid credit features");
        }
      }
    }
    checks.require(saw_credit_selected_edge,
                   label + " must identify the credit-owned first-edge decision");
  }
}

void test_default_and_invalid_mode_compatibility(Checks& checks,
                                                 const RealSplitMotif& motif) {
  EventDrivenJunctionConfig defaults;
  checks.require(defaults.admission_mode == "legacy_unbound",
                 "default admission mode must preserve legacy behavior");

  auto invalid = runtime_config("C0", false);
  invalid.admission_mode = "unknown";
  try {
    EventDrivenJunctionRuntime ignored(canonical_map2().graph, invalid);
    (void)ignored;
    checks.require(false, "unknown admission mode must fail closed");
  } catch (const std::invalid_argument&) {
  }

  auto off = runtime_config("C0", false);
  off.admission_mode = "off";
  const auto result = EventDrivenJunctionRuntime(canonical_map2().graph, off).run(
      {EventRuntimeBagRequest{"credit-off", 401, 0.0, 10000.0,
                              motif.split, motif.goal, "canonical-map2"}});
  checks.require(result.summary.admission_mode == "off" &&
                     !result.summary.source_admission_enabled &&
                     result.summary.first_edge_credit_issue_attempt_count == 0,
                 "explicit off must bypass credits while preserving local service");
}

}  // namespace

int main() {
  Checks checks;
  const auto motif = choose_real_split_motif();
  checks.require(canonical_map2().graph.has_edge(motif.split, motif.first) &&
                     canonical_map2().graph.has_edge(motif.split, motif.second),
                 "test must automatically select a real canonical map2 split");
  test_issue_bind_consume_duplicate_and_capacity(checks, motif);
  test_expiry_generation_fault_and_stale_snapshot(checks, motif);
  test_active_only_storage_and_bounded_lifecycle(checks, motif);
  test_copy_and_rollback_rebuild_expiry_iterators(checks, motif);
  test_bounded_batch_prevalidates_before_mutation(checks, motif);
  test_c4_c5_runtime_closed_loop(checks, motif);
  test_default_and_invalid_mode_compatibility(checks, motif);
  if (checks.failures != 0) {
    std::cerr << checks.failures
              << " expiring first-edge credit checks failed\n";
    return 1;
  }
  std::cout << "Expiring first-edge credit real-map checks passed\n";
  return 0;
}
