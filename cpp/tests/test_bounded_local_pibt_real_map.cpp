#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"
#include "ics_core/io/canonical_map2_reader.hpp"
#include "ics_core/runtime/bounded_local_pibt.hpp"

#ifndef CZR005_SOURCE_DIR
#error "CZR005_SOURCE_DIR must identify the repository root"
#endif

namespace {

using czr005::ics::BoundedLocalPIBTAction;
using czr005::ics::BoundedLocalPIBTCallbacks;
using czr005::ics::BoundedLocalPIBTCandidate;
using czr005::ics::BoundedLocalPIBTConfig;
using czr005::ics::BoundedLocalPIBTMode;
using czr005::ics::BoundedLocalPIBTOutcome;
using czr005::ics::BoundedLocalPIBTReadyBag;
using czr005::ics::BoundedLocalPIBTResolver;
using czr005::ics::BoundedLocalPIBTResourceOwner;
using czr005::ics::Graph;
using czr005::ics::LocalPIBTFaultSnapshot;
using czr005::ics::LocalPIBTResourceKey;
using czr005::ics::local_pibt_directed_edge_resource;
using czr005::ics::local_pibt_node_resource;

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

BoundedLocalPIBTCandidate candidate(int from,
                                    int next,
                                    double score = 0.0,
                                    std::uint64_t generation = 0) {
  BoundedLocalPIBTCandidate value;
  value.next_node = next;
  value.edge_resource = local_pibt_directed_edge_resource(from, next);
  value.required_resources = {
      value.edge_resource,
      local_pibt_node_resource(next),
  };
  value.local_score = score;
  value.expected_fault_generation = generation;
  return value;
}

BoundedLocalPIBTReadyBag ready_bag(
    int bag_id,
    int current,
    int goal,
    double deadline,
    std::vector<BoundedLocalPIBTCandidate> candidates,
    std::vector<LocalPIBTResourceKey> held_resources = {}) {
  BoundedLocalPIBTReadyBag bag;
  bag.bag_id = bag_id;
  bag.current_node = current;
  bag.goal_node = goal;
  bag.deadline = deadline;
  bag.ready_time = 10.0;
  bag.accumulated_wait = 5.0;
  bag.held_resources = std::move(held_resources);
  bag.candidates = std::move(candidates);
  return bag;
}

BoundedLocalPIBTResourceOwner owner(LocalPIBTResourceKey resource,
                                    int bag_id,
                                    bool movable = true,
                                    bool in_transit = false) {
  BoundedLocalPIBTResourceOwner result;
  result.resource = resource;
  result.bag_id = bag_id;
  result.movable = movable;
  result.in_transit = in_transit;
  return result;
}

struct CallbackState {
  std::map<LocalPIBTResourceKey, LocalPIBTFaultSnapshot> faults;
  std::vector<BoundedLocalPIBTAction> staged;
  std::vector<BoundedLocalPIBTAction> published;
  bool prepare_accept = true;
  bool commit_accept = true;
  bool mutate_fault_after_prepare = false;
  LocalPIBTResourceKey mutate_resource = 0;
  int prepare_calls = 0;
  int commit_calls = 0;
  int rollback_calls = 0;
};

BoundedLocalPIBTCallbacks callbacks(CallbackState& state) {
  BoundedLocalPIBTCallbacks value;
  value.read_fault = [&](LocalPIBTResourceKey resource) {
    const auto found = state.faults.find(resource);
    return found == state.faults.end() ? LocalPIBTFaultSnapshot{} : found->second;
  };
  value.prepare = [&](const std::vector<BoundedLocalPIBTAction>& actions) {
    ++state.prepare_calls;
    state.staged = actions;
    if (state.mutate_fault_after_prepare) {
      ++state.faults[state.mutate_resource].generation;
    }
    return state.prepare_accept;
  };
  value.commit = [&](const std::vector<BoundedLocalPIBTAction>& actions) {
    ++state.commit_calls;
    if (!state.commit_accept) {
      return false;
    }
    state.published = actions;
    state.staged.clear();
    return true;
  };
  value.rollback = [&](const std::vector<BoundedLocalPIBTAction>&) {
    ++state.rollback_calls;
    state.staged.clear();
  };
  return value;
}

BoundedLocalPIBTConfig config(BoundedLocalPIBTMode mode) {
  BoundedLocalPIBTConfig value;
  value.mode = mode;
  value.decision_time = 10.0;
  return value;
}

bool has_action(const std::vector<BoundedLocalPIBTAction>& actions, int bag_id) {
  return std::any_of(actions.begin(), actions.end(), [&](const auto& action) {
    return action.bag_id == bag_id;
  });
}

const BoundedLocalPIBTAction* find_action(
    const std::vector<BoundedLocalPIBTAction>& actions,
    int bag_id) {
  const auto found =
      std::find_if(actions.begin(), actions.end(), [&](const auto& action) {
        return action.bag_id == bag_id;
      });
  return found == actions.end() ? nullptr : &*found;
}

void test_p0_to_p4_depth_ladder(Checks& checks) {
  std::vector<BoundedLocalPIBTReadyBag> bags;
  std::vector<BoundedLocalPIBTResourceOwner> owners;
  for (int index = 0; index < 5; ++index) {
    const int bag_id = 10 + index;
    const int current = 100 + index;
    const int next = 101 + index;
    const auto held = local_pibt_node_resource(current);
    bags.push_back(ready_bag(
        bag_id,
        current,
        999,
        100.0 + static_cast<double>(index),
        {candidate(current, next)},
        {held}));
    owners.push_back(owner(held, bag_id));
  }

  for (int depth = 0; depth <= 4; ++depth) {
    CallbackState state;
    const auto result = BoundedLocalPIBTResolver().resolve(
        bags,
        owners,
        config(static_cast<BoundedLocalPIBTMode>(depth)),
        callbacks(state));
    checks.require(result.outcome == BoundedLocalPIBTOutcome::kCommitted,
                   "every P0-P4 chain slice should commit its feasible subset");
    checks.require(has_action(result.actions, 10) == (depth == 4),
                   "the highest-priority four-blocker chain must require P4");
    checks.require(result.classical_pibt_completeness_claimed == false,
                   "bounded local resolver must never claim classical PIBT completeness");
    checks.require(result.prepare_call_count == 1 &&
                       result.commit_call_count == 1 &&
                       result.rollback_call_count == 0,
                   "successful chain must use one batch prepare and one atomic commit");
    checks.require(state.published.size() == result.actions.size(),
                   "callback must publish the same complete action batch");
  }
}

void test_deterministic_unique_priority(Checks& checks) {
  std::vector<BoundedLocalPIBTReadyBag> forward;
  for (const int bag_id : {3, 1, 2}) {
    forward.push_back(
        ready_bag(bag_id, 200 + bag_id, 999, 100.0,
                  {candidate(200 + bag_id, 300 + bag_id)}));
  }
  auto reverse = forward;
  std::reverse(reverse.begin(), reverse.end());

  CallbackState left_state;
  CallbackState right_state;
  const auto left = BoundedLocalPIBTResolver().resolve(
      forward, {}, config(BoundedLocalPIBTMode::kP0), callbacks(left_state));
  const auto right = BoundedLocalPIBTResolver().resolve(
      reverse, {}, config(BoundedLocalPIBTMode::kP0), callbacks(right_state));
  checks.require(left.priority_order == std::vector<int>({1, 2, 3}) &&
                     right.priority_order == left.priority_order,
                 "bag ID must make otherwise tied priority globally unique and deterministic");
  checks.require(left.actions.size() == 3 && right.actions.size() == 3,
                 "independent tied bags should each receive one action");
  for (std::size_t index = 0; index < left.actions.size(); ++index) {
    checks.require(left.actions[index].priority_rank == static_cast<int>(index),
                   "action priority rank must match deterministic order");
  }
}

void test_priority_components_are_local_and_explainable(Checks& checks) {
  auto deadline = ready_bag(
      1, 310, 999, 40.0, {candidate(310, 311)});
  auto aged = ready_bag(
      2, 320, 999, 40.0, {candidate(320, 321)});
  aged.accumulated_wait = 8.0;
  aged.retry_age = 4.0;
  aged.source_release_age = 9.0;
  auto emergency = ready_bag(
      3, 330, 999, 400.0, {candidate(330, 331)});
  emergency.physical_fault_emergency = true;

  CallbackState state;
  const auto result = BoundedLocalPIBTResolver().resolve(
      {deadline, emergency, aged},
      {},
      config(BoundedLocalPIBTMode::kP0),
      callbacks(state));
  checks.require(result.priority_order == std::vector<int>({3, 2, 1}),
                 "local emergency, deadline and aging fields must form an explainable "
                 "deterministic priority");
  checks.require(result.local_message_count == 0,
                 "independent local actions must not emit inheritance messages");
}

void test_visiting_guard_and_candidate_backtracking(Checks& checks) {
  const auto resource_a = local_pibt_node_resource(401);
  const auto resource_b = local_pibt_node_resource(402);

  auto a_to_b = candidate(401, 402, 0.0);
  auto a_alternative = candidate(401, 403, 1.0);
  auto b_to_a = candidate(402, 401, 0.0);
  std::vector<BoundedLocalPIBTReadyBag> bags{
      ready_bag(1, 401, 999, 100.0, {a_to_b, a_alternative}, {resource_a}),
      ready_bag(2, 402, 999, 200.0, {b_to_a}, {resource_b}),
  };
  std::vector<BoundedLocalPIBTResourceOwner> owners{
      owner(resource_a, 1),
      owner(resource_b, 2),
  };

  CallbackState state;
  const auto result = BoundedLocalPIBTResolver().resolve(
      bags, owners, config(BoundedLocalPIBTMode::kP2), callbacks(state));
  const auto* action_a = find_action(result.actions, 1);
  checks.require(result.outcome == BoundedLocalPIBTOutcome::kCommitted,
                 "cycle slice should backtrack to a safe alternative");
  checks.require(result.visiting_cycle_guard_count > 0,
                 "local ownership cycle must trigger the visiting guard");
  checks.require(result.backtrack_count > 0,
                 "failed cyclic proposal must leave explicit backtracking evidence");
  checks.require(action_a != nullptr && action_a->next_node == 403,
                 "higher-priority bag must use its deterministic non-cyclic alternative");
}

void test_cross_blocker_combination_backtracking(Checks& checks) {
  const auto blocker_one_resource = local_pibt_node_resource(710);
  const auto blocker_two_resource = local_pibt_node_resource(720);
  const auto shared_escape_resource = local_pibt_node_resource(800);

  auto parent_move = candidate(700, 701);
  parent_move.required_resources.push_back(blocker_one_resource);
  parent_move.required_resources.push_back(blocker_two_resource);

  auto blocker_one_preferred = candidate(710, 711, 0.0);
  blocker_one_preferred.required_resources.push_back(shared_escape_resource);
  auto blocker_one_alternative = candidate(710, 712, 1.0);
  auto blocker_two_move = candidate(720, 721, 0.0);
  blocker_two_move.required_resources.push_back(shared_escape_resource);

  CallbackState state;
  const auto result = BoundedLocalPIBTResolver().resolve(
      {
          ready_bag(1, 700, 999, 100.0, {parent_move}),
          ready_bag(2,
                    710,
                    999,
                    200.0,
                    {blocker_one_preferred, blocker_one_alternative}),
          ready_bag(3, 720, 999, 300.0, {blocker_two_move}),
      },
      {
          owner(blocker_one_resource, 2),
          owner(blocker_two_resource, 3),
      },
      config(BoundedLocalPIBTMode::kP1),
      callbacks(state));
  const auto* blocker_one_action = find_action(result.actions, 2);
  checks.require(result.outcome == BoundedLocalPIBTOutcome::kCommitted &&
                     result.actions.size() == 3,
                 "P1 must form one compatible action set across two sibling blockers");
  checks.require(blocker_one_action != nullptr &&
                     blocker_one_action->next_node == 712,
                 "a later sibling conflict must backtrack the earlier blocker to its "
                 "next deterministic candidate");
  checks.require(result.backtrack_count > 0,
                 "cross-blocker candidate combination search must record backtracking");
}

void test_two_phase_rollback_and_fault_revalidation(Checks& checks) {
  const auto move = candidate(500, 501, 0.0, 7);
  const std::vector<BoundedLocalPIBTReadyBag> bags{
      ready_bag(1, 500, 999, 100.0, {move}),
  };

  CallbackState prepare_reject;
  prepare_reject.faults[move.edge_resource] = {7, false};
  prepare_reject.prepare_accept = false;
  const auto rejected_prepare = BoundedLocalPIBTResolver().resolve(
      bags,
      {},
      config(BoundedLocalPIBTMode::kP0),
      callbacks(prepare_reject));
  checks.require(
      rejected_prepare.outcome == BoundedLocalPIBTOutcome::kPrepareRejected &&
          rejected_prepare.rollback_call_count == 1 &&
          prepare_reject.staged.empty() && prepare_reject.published.empty(),
      "prepare rejection must roll back the complete staged batch");

  CallbackState commit_reject;
  commit_reject.faults[move.edge_resource] = {7, false};
  commit_reject.commit_accept = false;
  const auto rejected_commit = BoundedLocalPIBTResolver().resolve(
      bags,
      {},
      config(BoundedLocalPIBTMode::kP0),
      callbacks(commit_reject));
  checks.require(
      rejected_commit.outcome == BoundedLocalPIBTOutcome::kCommitRejected &&
          rejected_commit.prepare_call_count == 1 &&
          rejected_commit.commit_call_count == 1 &&
          rejected_commit.rollback_call_count == 1 &&
          commit_reject.staged.empty() && commit_reject.published.empty(),
      "commit rejection must roll back every prepared action atomically");

  CallbackState changed_fault;
  changed_fault.faults[move.edge_resource] = {7, false};
  changed_fault.mutate_fault_after_prepare = true;
  changed_fault.mutate_resource = move.edge_resource;
  const auto stale = BoundedLocalPIBTResolver().resolve(
      bags,
      {},
      config(BoundedLocalPIBTMode::kP0),
      callbacks(changed_fault));
  checks.require(
      stale.outcome == BoundedLocalPIBTOutcome::kFaultGenerationChanged &&
          stale.prepare_call_count == 1 && stale.commit_call_count == 0 &&
          stale.rollback_call_count == 1 && changed_fault.published.empty(),
      "fault generation change after prepare must invalidate and roll back the whole batch");
  checks.require(stale.fault_state_read_count >= 3 &&
                     stale.fault_revalidation_count == 2,
                 "selected edge must be read during propose and both validation barriers");
}

std::vector<int> canonical_node_locations(const Graph& graph) {
  std::vector<int> result;
  result.reserve(graph.node_count());
  for (std::size_t index = 0; index < graph.node_count(); ++index) {
    const int location = static_cast<int>(index);
    (void)graph.node(location);
    result.push_back(location);
  }
  return result;
}

std::map<int, std::vector<int>> incoming_nodes(const Graph& graph) {
  const auto nodes = canonical_node_locations(graph);
  std::map<int, std::vector<int>> incoming;
  for (const int node : nodes) {
    incoming[node];
  }
  for (const int start : nodes) {
    for (const int end : graph.outgoing(start)) {
      incoming[end].push_back(start);
    }
  }
  for (auto& entry : incoming) {
    std::sort(entry.second.begin(), entry.second.end());
  }
  return incoming;
}

std::set<std::pair<int, int>> weak_projection_bridges(const Graph& graph) {
  const auto nodes = canonical_node_locations(graph);
  std::map<int, std::set<int>> adjacency;
  for (const int node : nodes) {
    adjacency[node];
  }
  for (const int start : nodes) {
    for (const int end : graph.outgoing(start)) {
      adjacency[start].insert(end);
      adjacency[end].insert(start);
    }
  }

  std::map<int, int> discovered;
  std::map<int, int> low;
  std::map<int, int> parent;
  std::set<std::pair<int, int>> bridges;
  int clock = 0;
  std::function<void(int)> visit = [&](int node) {
    discovered[node] = clock;
    low[node] = clock;
    ++clock;
    for (const int neighbour : adjacency[node]) {
      if (discovered.find(neighbour) == discovered.end()) {
        parent[neighbour] = node;
        visit(neighbour);
        low[node] = std::min(low[node], low[neighbour]);
        if (low[neighbour] > discovered[node]) {
          bridges.emplace(std::min(node, neighbour), std::max(node, neighbour));
        }
      } else if (parent.find(node) == parent.end() ||
                 neighbour != parent[node]) {
        low[node] = std::min(low[node], discovered[neighbour]);
      }
    }
  };
  for (const int node : nodes) {
    if (discovered.find(node) == discovered.end()) {
      visit(node);
    }
  }
  return bridges;
}

void test_real_map_merge_split_and_bridge_motifs(Checks& checks) {
  const auto& graph = canonical_graph();
  const auto incoming = incoming_nodes(graph);

  int merge = -1;
  std::vector<int> merge_parents;
  for (const auto& entry : incoming) {
    if (entry.second.size() > 1) {
      merge = entry.first;
      merge_parents = entry.second;
      break;
    }
  }
  checks.require(merge >= 0 && merge_parents.size() > 1,
                 "canonical map2 must provide an automatically selected real merge");
  if (merge >= 0 && merge_parents.size() > 1) {
    const int left = merge_parents[0];
    const int right = merge_parents[1];
    checks.require(graph.has_edge(left, merge) && graph.has_edge(right, merge),
                   "selected merge entries must be real directed map2 edges");
    CallbackState state;
    const auto result = BoundedLocalPIBTResolver().resolve(
        {
            ready_bag(1, left, 47, 100.0, {candidate(left, merge)}),
            ready_bag(2, right, 47, 200.0, {candidate(right, merge)}),
        },
        {},
        config(BoundedLocalPIBTMode::kP4),
        callbacks(state));
    checks.require(result.outcome == BoundedLocalPIBTOutcome::kCommitted &&
                       result.actions.size() == 1 &&
                       result.actions.front().bag_id == 1,
                   "real merge arbitration must grant the shared node to one priority winner");
  }

  int split = -1;
  int occupied_target = -1;
  int alternate_target = -1;
  int blocker_next = -1;
  for (const int node : canonical_node_locations(graph)) {
    if (graph.outgoing(node).size() < 2) {
      continue;
    }
    for (const int target : graph.outgoing(node)) {
      for (const int next : graph.outgoing(target)) {
        if (next != node) {
          split = node;
          occupied_target = target;
          for (const int alternative : graph.outgoing(node)) {
            if (alternative != occupied_target) {
              alternate_target = alternative;
              break;
            }
          }
          blocker_next = next;
          break;
        }
      }
      if (split >= 0) {
        break;
      }
    }
    if (split >= 0) {
      break;
    }
  }
  checks.require(split >= 0 && graph.has_edge(split, occupied_target) &&
                     graph.has_edge(split, alternate_target) &&
                     graph.has_edge(occupied_target, blocker_next),
                 "canonical map2 must provide a real split with a movable local blocker");
  if (split >= 0) {
    const auto held_target = local_pibt_node_resource(occupied_target);
    CallbackState state;
    const auto result = BoundedLocalPIBTResolver().resolve(
        {
            ready_bag(10, split, 47, 100.0,
                      {candidate(split, occupied_target, 0.0),
                       candidate(split, alternate_target, 1.0)}),
            ready_bag(11, occupied_target, 47, 200.0,
                      {candidate(occupied_target, blocker_next)},
                      {held_target}),
        },
        {owner(held_target, 11)},
        config(BoundedLocalPIBTMode::kP1),
        callbacks(state));
    checks.require(result.outcome == BoundedLocalPIBTOutcome::kCommitted &&
                       has_action(result.actions, 10) &&
                       has_action(result.actions, 11) &&
                       result.inherited_action_count == 1,
                   "P1 must move one ready blocker before granting the real split edge");
    const auto* split_action = find_action(result.actions, 10);
    checks.require(split_action != nullptr &&
                       split_action->next_node == occupied_target,
                   "P1 must retain the preferred real split branch after moving its blocker");
  }

  const auto bridges = weak_projection_bridges(graph);
  checks.require(!bridges.empty(),
                 "canonical map2 must expose at least one weak-projection bridge");
  if (!bridges.empty()) {
    const auto bridge = *bridges.begin();
    const int start = graph.has_edge(bridge.first, bridge.second)
                          ? bridge.first
                          : bridge.second;
    const int end = start == bridge.first ? bridge.second : bridge.first;
    checks.require(graph.has_edge(start, end),
                   "automatically selected bridge must have a real directed orientation");
    const auto edge_resource = local_pibt_directed_edge_resource(start, end);
    CallbackState state;
    const auto result = BoundedLocalPIBTResolver().resolve(
        {ready_bag(20, start, 47, 100.0, {candidate(start, end)})},
        {owner(edge_resource, 999, true, true)},
        config(BoundedLocalPIBTMode::kP4),
        callbacks(state));
    checks.require(result.outcome == BoundedLocalPIBTOutcome::kNoFeasibleAction &&
                       result.actions.empty() &&
                       result.immovable_blocker_count > 0 &&
                       result.prepare_call_count == 0,
                   "an in-transit bridge owner must remain immovable at every P depth");
    checks.require(result.classical_pibt_completeness_claimed == false,
                   "directed map with bridges cannot inherit a classic PIBT completeness claim");
  }
}

void test_fail_closed_slice_contract(Checks& checks) {
  auto valid = ready_bag(1, 600, 999, 100.0, {candidate(600, 601)});
  CallbackState state;
  try {
    auto in_transit = valid;
    in_transit.in_transit = true;
    (void)BoundedLocalPIBTResolver().resolve(
        {in_transit}, {}, config(BoundedLocalPIBTMode::kP0), callbacks(state));
    checks.require(false, "in-transit bag must not enter the ready arbitration slice");
  } catch (const std::invalid_argument&) {
  }

  try {
    auto small = config(BoundedLocalPIBTMode::kP0);
    small.max_ready_bags = 1;
    (void)BoundedLocalPIBTResolver().resolve(
        {valid, ready_bag(2, 602, 999, 200.0, {candidate(602, 603)})},
        {},
        small,
        callbacks(state));
    checks.require(false, "configured local slice bound must fail closed");
  } catch (const std::invalid_argument&) {
  }

  try {
    auto small = config(BoundedLocalPIBTMode::kP0);
    small.max_local_resources = 1;
    (void)BoundedLocalPIBTResolver().resolve(
        {valid}, {}, small, callbacks(state));
    checks.require(false, "all touched free and owned resources must count toward the slice bound");
  } catch (const std::invalid_argument&) {
  }

  try {
    auto forged = valid;
    forged.candidates.front().edge_resource = local_pibt_node_resource(601);
    forged.candidates.front().required_resources = {
        forged.candidates.front().edge_resource,
    };
    (void)BoundedLocalPIBTResolver().resolve(
        {forged}, {}, config(BoundedLocalPIBTMode::kP0), callbacks(state));
    checks.require(false, "a one-edge proposal must use its exact directed edge resource");
  } catch (const std::invalid_argument&) {
  }

  try {
    auto future = valid;
    future.ready_time = 10.5;
    (void)BoundedLocalPIBTResolver().resolve(
        {future}, {}, config(BoundedLocalPIBTMode::kP0), callbacks(state));
    checks.require(false, "future bags must not enter a simultaneously-ready slice");
  } catch (const std::invalid_argument&) {
  }
}

}  // namespace

int main() {
  Checks checks;
  test_p0_to_p4_depth_ladder(checks);
  test_deterministic_unique_priority(checks);
  test_priority_components_are_local_and_explainable(checks);
  test_visiting_guard_and_candidate_backtracking(checks);
  test_cross_blocker_combination_backtracking(checks);
  test_two_phase_rollback_and_fault_revalidation(checks);
  test_real_map_merge_split_and_bridge_motifs(checks);
  test_fail_closed_slice_contract(checks);
  if (checks.failures != 0) {
    std::cerr << checks.failures
              << " bounded-local PIBT checks failed\n";
    return 1;
  }
  std::cout << "bounded-local PIBT checks passed\n";
  return 0;
}
