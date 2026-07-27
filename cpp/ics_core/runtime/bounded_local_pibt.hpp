#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <functional>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace czr005::ics {

// This is a bounded local priority-inheritance/backtracking protocol.  It is
// intentionally independent of Graph, A*/CIE, ReservationTable and every
// global runtime index.  The caller must construct a finite local arbitration
// slice containing only simultaneously ready bags, their one-edge candidates
// and the owners of resources touched by those candidates.

using LocalPIBTResourceKey = std::int64_t;

inline LocalPIBTResourceKey local_pibt_node_resource(int node) {
  if (node < 0) {
    throw std::invalid_argument("local PIBT node resource requires a non-negative node");
  }
  return static_cast<LocalPIBTResourceKey>(0x1000000000000000LL) |
         static_cast<std::uint32_t>(node);
}

inline LocalPIBTResourceKey local_pibt_directed_edge_resource(int start, int end) {
  if (start < 0 || end < 0 || start >= (1 << 28) || end >= (1 << 28)) {
    throw std::invalid_argument(
        "local PIBT edge resource endpoints must be in [0, 2^28)");
  }
  return static_cast<LocalPIBTResourceKey>(0x2000000000000000LL) |
         (static_cast<LocalPIBTResourceKey>(static_cast<std::uint32_t>(start)) << 28) |
         static_cast<std::uint32_t>(end);
}

enum class BoundedLocalPIBTMode {
  kP0 = 0,
  kP1 = 1,
  kP2 = 2,
  kP3 = 3,
  kP4 = 4,
};

// Priority and preference are deliberately orthogonal to inheritance depth.
// Q0/current preserve the sealed G4IRSF12 ordering and candidate comparator.
// The opt-in variants consume only fields materialised in the bounded local
// slice; they never query Graph, a route planner, or a reservation table.
enum class BoundedLocalPIBTPriorityMode {
  kQ0Current = 0,
  kQ1ThesisLocalProjection = 1,
  kQ2TypeSlackAging = 2,
  kQ3FaultSlackAgeStableId = 3,
};

enum class BoundedLocalPIBTPreferenceMode {
  kCurrent = 0,
  kDodge = 1,
  kLocalRegret = 2,
  kDodgeRegret = 3,
};

inline int bounded_local_pibt_depth(BoundedLocalPIBTMode mode) {
  switch (mode) {
    case BoundedLocalPIBTMode::kP0:
      return 0;
    case BoundedLocalPIBTMode::kP1:
      return 1;
    case BoundedLocalPIBTMode::kP2:
      return 2;
    case BoundedLocalPIBTMode::kP3:
      return 3;
    case BoundedLocalPIBTMode::kP4:
      return 4;
  }
  throw std::invalid_argument("bounded local PIBT mode must be P0..P4");
}

inline const char* bounded_local_pibt_mode_name(BoundedLocalPIBTMode mode) {
  switch (mode) {
    case BoundedLocalPIBTMode::kP0:
      return "P0";
    case BoundedLocalPIBTMode::kP1:
      return "P1";
    case BoundedLocalPIBTMode::kP2:
      return "P2";
    case BoundedLocalPIBTMode::kP3:
      return "P3";
    case BoundedLocalPIBTMode::kP4:
      return "P4";
  }
  throw std::invalid_argument("bounded local PIBT mode must be P0..P4");
}

struct LocalPIBTFaultSnapshot {
  std::uint64_t generation = 0;
  bool physically_blocked = false;
};

struct BoundedLocalPIBTCandidate {
  int next_node = -1;
  LocalPIBTResourceKey edge_resource = 0;
  std::vector<LocalPIBTResourceKey> required_resources;
  double local_score = 0.0;
  std::uint64_t expected_fault_generation = 0;
  bool physically_blocked_at_snapshot = false;
  // These diagnostics are computed from the same one-hop local slice as the
  // candidate.  They are consulted only when static_potential ties exactly.
  double static_potential = 0.0;
  bool blocks_higher_priority_exit = false;
  bool occupies_unique_exit = false;
  bool enters_wait_for_cycle = false;
  bool is_local_backtrack = false;
  double local_regret_prior = 0.0;
};

struct BoundedLocalPIBTReadyBag {
  int bag_id = -1;
  int current_node = -1;
  int goal_node = -1;
  bool physical_fault_emergency = false;
  double deadline = -1.0;
  double ready_time = 0.0;
  double accumulated_wait = 0.0;
  double retry_age = 0.0;
  double source_release_age = 0.0;
  bool movable = true;
  bool in_transit = false;
  std::vector<LocalPIBTResourceKey> held_resources;
  std::vector<BoundedLocalPIBTCandidate> candidates;
  // Lower task_class_rank runs first.  The event runtime supplies a unique,
  // local-only ordering key; bag_id remains the final stable tie-break.
  int task_class_rank = 0;
  std::uint64_t fault_priority_generation = 0;
  int local_contention = 0;
  std::uint64_t enqueue_sequence = 0;
};

struct BoundedLocalPIBTResourceOwner {
  LocalPIBTResourceKey resource = 0;
  int bag_id = -1;
  bool movable = true;
  bool in_transit = false;
};

struct BoundedLocalPIBTAction {
  int bag_id = -1;
  int from_node = -1;
  int next_node = -1;
  LocalPIBTResourceKey edge_resource = 0;
  std::vector<LocalPIBTResourceKey> claimed_resources;
  std::uint64_t expected_fault_generation = 0;
  int priority_rank = -1;
  int inheritance_depth = 0;
  bool inherited = false;
  double local_score = 0.0;
};

struct BoundedLocalPIBTCallbacks {
  // Must return the physical state of the selected directed edge without
  // scanning a global fault/reservation structure.
  std::function<LocalPIBTFaultSnapshot(LocalPIBTResourceKey)> read_fault;

  // prepare receives the complete action batch once.  It may stage local
  // claims, but must not publish a partial batch.
  std::function<bool(const std::vector<BoundedLocalPIBTAction>&)> prepare;

  // commit must publish the complete prepared batch atomically.  Returning
  // false requests rollback of every staged local claim.
  std::function<bool(const std::vector<BoundedLocalPIBTAction>&)> commit;

  // rollback must undo all staging performed by prepare/commit for this batch.
  std::function<void(const std::vector<BoundedLocalPIBTAction>&)> rollback;
};

struct BoundedLocalPIBTConfig {
  BoundedLocalPIBTMode mode = BoundedLocalPIBTMode::kP0;
  double decision_time = 0.0;
  int max_ready_bags = 32;
  int max_local_resources = 128;
  int max_candidates_per_bag = 16;
  BoundedLocalPIBTPriorityMode priority_mode =
      BoundedLocalPIBTPriorityMode::kQ0Current;
  BoundedLocalPIBTPreferenceMode preference_mode =
      BoundedLocalPIBTPreferenceMode::kCurrent;
};

enum class BoundedLocalPIBTOutcome {
  kCommitted,
  kNoFeasibleAction,
  kFaultGenerationChanged,
  kPrepareRejected,
  kCommitRejected,
};

inline const char* bounded_local_pibt_outcome_name(BoundedLocalPIBTOutcome outcome) {
  switch (outcome) {
    case BoundedLocalPIBTOutcome::kCommitted:
      return "COMMITTED";
    case BoundedLocalPIBTOutcome::kNoFeasibleAction:
      return "NO_FEASIBLE_ACTION";
    case BoundedLocalPIBTOutcome::kFaultGenerationChanged:
      return "FAULT_GENERATION_CHANGED";
    case BoundedLocalPIBTOutcome::kPrepareRejected:
      return "PREPARE_REJECTED";
    case BoundedLocalPIBTOutcome::kCommitRejected:
      return "COMMIT_REJECTED";
  }
  return "UNKNOWN";
}

struct BoundedLocalPIBTResult {
  BoundedLocalPIBTOutcome outcome = BoundedLocalPIBTOutcome::kNoFeasibleAction;
  std::string mode;
  std::vector<int> priority_order;
  std::vector<BoundedLocalPIBTAction> actions;
  std::vector<int> held_bag_ids;
  int candidate_attempt_count = 0;
  int blocker_move_attempt_count = 0;
  int inherited_action_count = 0;
  int max_inheritance_depth_observed = 0;
  int visiting_cycle_guard_count = 0;
  int backtrack_count = 0;
  int immovable_blocker_count = 0;
  int stale_fault_candidate_count = 0;
  int fault_revalidation_count = 0;
  int proposal_validation_count = 0;
  int fault_state_read_count = 0;
  int local_owner_read_count = 0;
  int local_message_count = 0;
  int prepare_call_count = 0;
  int commit_call_count = 0;
  int rollback_call_count = 0;
  bool prepared = false;
  bool committed = false;
  bool rolled_back = false;
  bool rollback_failed = false;
  bool classical_pibt_completeness_claimed = false;
  std::string blocker;
};

namespace bounded_local_pibt_detail {

struct SearchState {
  std::map<int, BoundedLocalPIBTAction> actions_by_bag;
  std::map<LocalPIBTResourceKey, int> claimed_by_resource;
  std::set<LocalPIBTResourceKey> released_resources;
  std::set<int> holding_bags;
};

inline std::vector<LocalPIBTResourceKey> sorted_unique_resources(
    const std::vector<LocalPIBTResourceKey>& resources) {
  std::vector<LocalPIBTResourceKey> result = resources;
  std::sort(result.begin(), result.end());
  result.erase(std::unique(result.begin(), result.end()), result.end());
  return result;
}

inline double priority_slack(const BoundedLocalPIBTReadyBag& bag, double now) {
  if (bag.deadline < 0.0) {
    return std::numeric_limits<double>::infinity();
  }
  return bag.deadline - now;
}

inline bool action_matches_candidate(const BoundedLocalPIBTAction& action,
                                     const BoundedLocalPIBTReadyBag& bag) {
  for (const auto& candidate : bag.candidates) {
    if (candidate.next_node == action.next_node &&
        candidate.edge_resource == action.edge_resource &&
        candidate.expected_fault_generation == action.expected_fault_generation &&
        sorted_unique_resources(candidate.required_resources) ==
            action.claimed_resources) {
      return true;
    }
  }
  return false;
}

inline void validate_inputs(
    const std::vector<BoundedLocalPIBTReadyBag>& ready_bags,
    const std::vector<BoundedLocalPIBTResourceOwner>& owners,
    const BoundedLocalPIBTConfig& config,
    const BoundedLocalPIBTCallbacks& callbacks) {
  (void)bounded_local_pibt_depth(config.mode);
  if (!std::isfinite(config.decision_time)) {
    throw std::invalid_argument("bounded local PIBT decision_time must be finite");
  }
  if (config.max_ready_bags <= 0 || config.max_local_resources <= 0 ||
      config.max_candidates_per_bag <= 0 ||
      static_cast<int>(ready_bags.size()) > config.max_ready_bags ||
      static_cast<int>(owners.size()) > config.max_local_resources) {
    throw std::invalid_argument("bounded local PIBT slice exceeds its configured bound");
  }
  if (!callbacks.read_fault || !callbacks.prepare || !callbacks.commit ||
      !callbacks.rollback) {
    throw std::invalid_argument(
        "bounded local PIBT requires fault, prepare, commit and rollback callbacks");
  }

  std::set<int> bag_ids;
  std::map<int, const BoundedLocalPIBTReadyBag*> bags_by_id;
  std::set<LocalPIBTResourceKey> local_resources;
  for (const auto& bag : ready_bags) {
    if (bag.bag_id < 0 || bag.current_node < 0 || bag.goal_node < 0) {
      throw std::invalid_argument("bounded local PIBT bag identity is invalid");
    }
    if (!bag_ids.insert(bag.bag_id).second) {
      throw std::invalid_argument("bounded local PIBT ready bag IDs must be unique");
    }
    if (bag.in_transit) {
      throw std::invalid_argument(
          "an in-transit bag cannot appear in the simultaneously-ready slice");
    }
    if (!std::isfinite(bag.ready_time) ||
        bag.ready_time > config.decision_time ||
        !std::isfinite(bag.accumulated_wait) ||
        bag.accumulated_wait < 0.0 || !std::isfinite(bag.retry_age) ||
        bag.retry_age < 0.0 || !std::isfinite(bag.source_release_age) ||
        bag.source_release_age < 0.0 ||
        (bag.deadline >= 0.0 && !std::isfinite(bag.deadline))) {
      throw std::invalid_argument("bounded local PIBT bag timing is invalid");
    }
    if (static_cast<int>(bag.candidates.size()) > config.max_candidates_per_bag) {
      throw std::invalid_argument(
          "bounded local PIBT bag candidate count exceeds its configured bound");
    }
    const auto held = sorted_unique_resources(bag.held_resources);
    if (held.size() != bag.held_resources.size()) {
      throw std::invalid_argument("bounded local PIBT held resources must be unique");
    }
    local_resources.insert(held.begin(), held.end());
    std::set<int> next_nodes;
    for (const auto& candidate : bag.candidates) {
      if (candidate.next_node < 0 || candidate.next_node == bag.current_node ||
          candidate.edge_resource != local_pibt_directed_edge_resource(
                                         bag.current_node,
                                         candidate.next_node) ||
          !std::isfinite(candidate.local_score) ||
          !std::isfinite(candidate.static_potential) ||
          !std::isfinite(candidate.local_regret_prior) ||
          candidate.local_regret_prior < 0.0) {
        throw std::invalid_argument("bounded local PIBT candidate is invalid");
      }
      if (!next_nodes.insert(candidate.next_node).second) {
        throw std::invalid_argument(
            "bounded local PIBT permits at most one candidate per next node");
      }
      const auto claims = sorted_unique_resources(candidate.required_resources);
      if (claims.empty() || claims.size() != candidate.required_resources.size() ||
          !std::binary_search(claims.begin(), claims.end(), candidate.edge_resource)) {
        throw std::invalid_argument(
            "bounded local PIBT candidate claims must be unique and include its edge");
      }
      local_resources.insert(claims.begin(), claims.end());
    }
    bags_by_id.emplace(bag.bag_id, &bag);
  }

  std::map<LocalPIBTResourceKey, BoundedLocalPIBTResourceOwner> owners_by_resource;
  for (const auto& owner : owners) {
    if (owner.resource == 0 || owner.bag_id < 0) {
      throw std::invalid_argument("bounded local PIBT resource owner is invalid");
    }
    if (!owners_by_resource.emplace(owner.resource, owner).second) {
      throw std::invalid_argument(
          "bounded local PIBT local resources must have at most one owner");
    }
    local_resources.insert(owner.resource);
  }
  if (static_cast<int>(local_resources.size()) > config.max_local_resources) {
    throw std::invalid_argument(
        "bounded local PIBT touched resource count exceeds its configured bound");
  }
  for (const auto& bag : ready_bags) {
    for (const auto resource : bag.held_resources) {
      const auto owner = owners_by_resource.find(resource);
      if (owner == owners_by_resource.end() || owner->second.bag_id != bag.bag_id) {
        throw std::invalid_argument(
            "every ready bag held resource must have a matching local owner");
      }
      if (owner->second.in_transit) {
        throw std::invalid_argument(
            "a simultaneously-ready bag cannot own an in-transit resource");
      }
      if (owner->second.movable != bag.movable) {
        throw std::invalid_argument(
            "ready bag and local owner movable flags must agree");
      }
    }
  }
  for (const auto& entry : owners_by_resource) {
    const auto bag = bags_by_id.find(entry.second.bag_id);
    if (bag == bags_by_id.end()) {
      continue;
    }
    if (entry.second.in_transit ||
        entry.second.movable != bag->second->movable) {
      throw std::invalid_argument(
          "ready bag and local owner transit/movable states must agree");
    }
  }
}

inline bool validate_proposal(
    const std::vector<BoundedLocalPIBTAction>& actions,
    const std::map<int, const BoundedLocalPIBTReadyBag*>& bags_by_id,
    std::string& blocker) {
  std::set<int> action_bags;
  std::set<LocalPIBTResourceKey> claimed_resources;
  for (const auto& action : actions) {
    if (!action_bags.insert(action.bag_id).second) {
      blocker = "more_than_one_action_for_bag";
      return false;
    }
    const auto bag = bags_by_id.find(action.bag_id);
    if (bag == bags_by_id.end() || bag->second->in_transit ||
        action.from_node != bag->second->current_node ||
        action.next_node < 0 || action.next_node == action.from_node ||
        !action_matches_candidate(action, *bag->second)) {
      blocker = "action_not_in_ready_bag_one_edge_candidates";
      return false;
    }
    if (!std::is_sorted(action.claimed_resources.begin(),
                        action.claimed_resources.end()) ||
        std::adjacent_find(action.claimed_resources.begin(),
                           action.claimed_resources.end()) !=
            action.claimed_resources.end()) {
      blocker = "action_claims_not_unique_sorted";
      return false;
    }
    for (const auto resource : action.claimed_resources) {
      if (!claimed_resources.insert(resource).second) {
        blocker = "proposal_resource_claim_conflict";
        return false;
      }
    }
  }
  return true;
}

inline bool fault_batch_is_current(
    const std::vector<BoundedLocalPIBTAction>& actions,
    const BoundedLocalPIBTCallbacks& callbacks,
    BoundedLocalPIBTResult& result) {
  for (const auto& action : actions) {
    ++result.fault_revalidation_count;
    ++result.fault_state_read_count;
    const auto current = callbacks.read_fault(action.edge_resource);
    if (current.physically_blocked ||
        current.generation != action.expected_fault_generation) {
      result.blocker = "fault_generation_or_physical_state_changed";
      return false;
    }
  }
  return true;
}

inline void rollback_batch(const std::vector<BoundedLocalPIBTAction>& actions,
                           const BoundedLocalPIBTCallbacks& callbacks,
                           BoundedLocalPIBTResult& result) {
  ++result.rollback_call_count;
  try {
    callbacks.rollback(actions);
    result.rolled_back = true;
  } catch (...) {
    result.rollback_failed = true;
    result.blocker +=
        result.blocker.empty() ? "rollback_callback_failed" : ";rollback_callback_failed";
    // Continuing after an unknown rollback state would turn a failed atomic
    // transaction into silent partial publication.
    throw;
  }
}

}  // namespace bounded_local_pibt_detail

class BoundedLocalPIBTResolver {
 public:
  [[nodiscard]] BoundedLocalPIBTResult resolve(
      std::vector<BoundedLocalPIBTReadyBag> ready_bags,
      std::vector<BoundedLocalPIBTResourceOwner> owners,
      const BoundedLocalPIBTConfig& config,
      const BoundedLocalPIBTCallbacks& callbacks) const {
    using namespace bounded_local_pibt_detail;

    validate_inputs(ready_bags, owners, config, callbacks);
    BoundedLocalPIBTResult result;
    result.mode = bounded_local_pibt_mode_name(config.mode);
    result.classical_pibt_completeness_claimed = false;

    std::vector<const BoundedLocalPIBTReadyBag*> ordered;
    ordered.reserve(ready_bags.size());
    std::map<int, const BoundedLocalPIBTReadyBag*> bags_by_id;
    for (const auto& bag : ready_bags) {
      ordered.push_back(&bag);
      bags_by_id.emplace(bag.bag_id, &bag);
    }
    std::sort(
        ordered.begin(),
        ordered.end(),
        [&](const auto* left, const auto* right) {
          switch (config.priority_mode) {
            case BoundedLocalPIBTPriorityMode::kQ0Current:
              return std::make_tuple(
                         !left->physical_fault_emergency,
                         priority_slack(*left, config.decision_time),
                         -left->accumulated_wait,
                         -left->retry_age,
                         -left->source_release_age,
                         left->bag_id) <
                     std::make_tuple(
                         !right->physical_fault_emergency,
                         priority_slack(*right, config.decision_time),
                         -right->accumulated_wait,
                         -right->retry_age,
                         -right->source_release_age,
                         right->bag_id);
            case BoundedLocalPIBTPriorityMode::kQ1ThesisLocalProjection:
              return std::make_tuple(
                         !left->physical_fault_emergency,
                         priority_slack(*left, config.decision_time),
                         -left->local_contention,
                         left->enqueue_sequence,
                         left->bag_id) <
                     std::make_tuple(
                         !right->physical_fault_emergency,
                         priority_slack(*right, config.decision_time),
                         -right->local_contention,
                         right->enqueue_sequence,
                         right->bag_id);
            case BoundedLocalPIBTPriorityMode::kQ2TypeSlackAging:
              return std::make_tuple(
                         left->task_class_rank,
                         priority_slack(*left, config.decision_time),
                         -left->source_release_age,
                         -left->local_contention,
                         left->bag_id) <
                     std::make_tuple(
                         right->task_class_rank,
                         priority_slack(*right, config.decision_time),
                         -right->source_release_age,
                         -right->local_contention,
                         right->bag_id);
            case BoundedLocalPIBTPriorityMode::kQ3FaultSlackAgeStableId:
              return std::make_tuple(
                         -static_cast<long long>(
                             left->fault_priority_generation),
                         priority_slack(*left, config.decision_time),
                         -left->source_release_age,
                         left->bag_id) <
                     std::make_tuple(
                         -static_cast<long long>(
                             right->fault_priority_generation),
                         priority_slack(*right, config.decision_time),
                         -right->source_release_age,
                         right->bag_id);
          }
          throw std::invalid_argument(
              "bounded local PIBT priority mode must be Q0..Q3");
        });

    std::map<int, int> priority_rank;
    for (std::size_t index = 0; index < ordered.size(); ++index) {
      priority_rank.emplace(ordered[index]->bag_id, static_cast<int>(index));
      result.priority_order.push_back(ordered[index]->bag_id);
    }

    std::map<LocalPIBTResourceKey, BoundedLocalPIBTResourceOwner> owners_by_resource;
    std::map<int, std::vector<LocalPIBTResourceKey>> owned_resources_by_bag;
    for (const auto& owner : owners) {
      owners_by_resource.emplace(owner.resource, owner);
      owned_resources_by_bag[owner.bag_id].push_back(owner.resource);
    }

    SearchState state;
    const int maximum_depth = bounded_local_pibt_depth(config.mode);
    using Continuation = std::function<bool()>;
    std::function<bool(int,
                       int,
                       int,
                       bool,
                       std::set<int>&,
                       const Continuation&)>
        assign;
    assign = [&](int bag_id,
                 int remaining_depth,
                 int inheritance_depth,
                 bool inherited,
                 std::set<int>& visiting,
                 const Continuation& continuation) -> bool {
      if (state.actions_by_bag.find(bag_id) != state.actions_by_bag.end()) {
        return continuation();
      }
      if (state.holding_bags.find(bag_id) != state.holding_bags.end()) {
        return false;
      }
      if (visiting.find(bag_id) != visiting.end()) {
        ++result.visiting_cycle_guard_count;
        return false;
      }
      const auto bag_found = bags_by_id.find(bag_id);
      if (bag_found == bags_by_id.end() || !bag_found->second->movable ||
          bag_found->second->in_transit) {
        ++result.immovable_blocker_count;
        return false;
      }
      const auto& bag = *bag_found->second;
      visiting.insert(bag_id);

      std::vector<const BoundedLocalPIBTCandidate*> candidates;
      candidates.reserve(bag.candidates.size());
      for (const auto& candidate : bag.candidates) {
        candidates.push_back(&candidate);
      }
      std::sort(
          candidates.begin(),
          candidates.end(),
          [&](const auto* left, const auto* right) {
            const auto left_claims =
                sorted_unique_resources(left->required_resources);
            const auto right_claims =
                sorted_unique_resources(right->required_resources);
            if (config.preference_mode !=
                    BoundedLocalPIBTPreferenceMode::kCurrent &&
                left->static_potential == right->static_potential) {
              const bool use_dodge =
                  config.preference_mode ==
                      BoundedLocalPIBTPreferenceMode::kDodge ||
                  config.preference_mode ==
                      BoundedLocalPIBTPreferenceMode::kDodgeRegret;
              const bool use_regret =
                  config.preference_mode ==
                      BoundedLocalPIBTPreferenceMode::kLocalRegret ||
                  config.preference_mode ==
                      BoundedLocalPIBTPreferenceMode::kDodgeRegret;
              const auto left_preference = std::make_tuple(
                  use_dodge && left->blocks_higher_priority_exit,
                  use_dodge && left->occupies_unique_exit,
                  use_dodge && left->is_local_backtrack,
                  use_dodge && left->enters_wait_for_cycle,
                  use_regret ? left->local_regret_prior : 0.0,
                  left->local_score,
                  left->next_node,
                  left->edge_resource,
                  left_claims);
              const auto right_preference = std::make_tuple(
                  use_dodge && right->blocks_higher_priority_exit,
                  use_dodge && right->occupies_unique_exit,
                  use_dodge && right->is_local_backtrack,
                  use_dodge && right->enters_wait_for_cycle,
                  use_regret ? right->local_regret_prior : 0.0,
                  right->local_score,
                  right->next_node,
                  right->edge_resource,
                  right_claims);
              return left_preference < right_preference;
            }
            return std::make_tuple(left->local_score,
                                   left->next_node,
                                   left->edge_resource,
                                   left_claims) <
                   std::make_tuple(right->local_score,
                                   right->next_node,
                                   right->edge_resource,
                                   right_claims);
          });

      for (const auto* candidate : candidates) {
        ++result.candidate_attempt_count;
        const SearchState checkpoint = state;
        bool feasible = !candidate->physically_blocked_at_snapshot;
        if (feasible) {
          ++result.fault_state_read_count;
          const auto fault = callbacks.read_fault(candidate->edge_resource);
          if (fault.physically_blocked ||
              fault.generation != candidate->expected_fault_generation) {
            feasible = false;
            ++result.stale_fault_candidate_count;
          }
        }

        std::set<int> blocker_ids;
        const auto claims = sorted_unique_resources(candidate->required_resources);
        if (feasible) {
          for (const auto resource : claims) {
            const auto proposed = state.claimed_by_resource.find(resource);
            if (proposed != state.claimed_by_resource.end() &&
                proposed->second != bag_id) {
              feasible = false;
              break;
            }
            ++result.local_owner_read_count;
            const auto owner = owners_by_resource.find(resource);
            if (owner == owners_by_resource.end() ||
                owner->second.bag_id == bag_id ||
                state.released_resources.find(resource) !=
                    state.released_resources.end()) {
              continue;
            }
            if (owner->second.in_transit || !owner->second.movable) {
              feasible = false;
              ++result.immovable_blocker_count;
              break;
            }
            blocker_ids.insert(owner->second.bag_id);
          }
        }

        std::vector<int> blockers(blocker_ids.begin(), blocker_ids.end());
        std::sort(blockers.begin(), blockers.end(), [&](int left, int right) {
          const auto left_rank = priority_rank.find(left);
          const auto right_rank = priority_rank.find(right);
          const int left_value =
              left_rank == priority_rank.end() ? std::numeric_limits<int>::max()
                                               : left_rank->second;
          const int right_value =
              right_rank == priority_rank.end() ? std::numeric_limits<int>::max()
                                                : right_rank->second;
          return std::tie(left_value, left) < std::tie(right_value, right);
        });

        std::function<bool(std::size_t)> assign_remaining_blockers;
        assign_remaining_blockers = [&](std::size_t blocker_index) -> bool {
          if (blocker_index < blockers.size()) {
            const int blocker_id = blockers[blocker_index];
            if (visiting.find(blocker_id) != visiting.end()) {
              ++result.visiting_cycle_guard_count;
              return false;
            }
            const auto blocker_rank = priority_rank.find(blocker_id);
            if (remaining_depth <= 0 || blocker_rank == priority_rank.end() ||
                blocker_rank->second < priority_rank.at(bag_id)) {
              return false;
            }
            ++result.blocker_move_attempt_count;
            ++result.local_message_count;
            return assign(
                blocker_id,
                remaining_depth - 1,
                inheritance_depth + 1,
                true,
                visiting,
                [&]() {
                  return assign_remaining_blockers(blocker_index + 1);
                });
          }

          for (const auto resource : claims) {
            const auto proposed = state.claimed_by_resource.find(resource);
            if (proposed != state.claimed_by_resource.end() &&
                proposed->second != bag_id) {
              return false;
            }
            ++result.local_owner_read_count;
            const auto owner = owners_by_resource.find(resource);
            if (owner != owners_by_resource.end() &&
                owner->second.bag_id != bag_id &&
                state.released_resources.find(resource) ==
                    state.released_resources.end()) {
              return false;
            }
          }

          BoundedLocalPIBTAction action;
          action.bag_id = bag.bag_id;
          action.from_node = bag.current_node;
          action.next_node = candidate->next_node;
          action.edge_resource = candidate->edge_resource;
          action.claimed_resources = claims;
          action.expected_fault_generation =
              candidate->expected_fault_generation;
          action.priority_rank = priority_rank.at(bag.bag_id);
          action.inheritance_depth = inheritance_depth;
          action.inherited = inherited;
          action.local_score = candidate->local_score;
          state.actions_by_bag.emplace(bag.bag_id, action);
          for (const auto resource : claims) {
            state.claimed_by_resource[resource] = bag.bag_id;
          }
          const auto owned = owned_resources_by_bag.find(bag.bag_id);
          if (owned != owned_resources_by_bag.end()) {
            state.released_resources.insert(owned->second.begin(),
                                            owned->second.end());
          }
          result.max_inheritance_depth_observed =
              std::max(result.max_inheritance_depth_observed,
                       inheritance_depth);
          return continuation();
        };

        if (feasible && assign_remaining_blockers(0)) {
          visiting.erase(bag_id);
          return true;
        }

        state = checkpoint;
        ++result.backtrack_count;
      }

      visiting.erase(bag_id);
      return false;
    };

    for (const auto* bag : ordered) {
      if (state.actions_by_bag.find(bag->bag_id) !=
          state.actions_by_bag.end()) {
        continue;
      }
      std::set<int> visiting;
      if (!assign(
              bag->bag_id,
              maximum_depth,
              0,
              false,
              visiting,
              []() { return true; })) {
        state.holding_bags.insert(bag->bag_id);
      }
    }

    for (const auto& entry : state.actions_by_bag) {
      result.actions.push_back(entry.second);
    }
    std::sort(result.actions.begin(), result.actions.end(), [](const auto& left, const auto& right) {
      return std::tie(left.priority_rank, left.bag_id) <
             std::tie(right.priority_rank, right.bag_id);
    });
    result.inherited_action_count = static_cast<int>(
        std::count_if(result.actions.begin(), result.actions.end(), [](const auto& action) {
          return action.inherited;
        }));
    for (const auto* bag : ordered) {
      if (state.actions_by_bag.find(bag->bag_id) ==
          state.actions_by_bag.end()) {
        result.held_bag_ids.push_back(bag->bag_id);
      }
    }

    if (result.actions.empty()) {
      result.outcome = BoundedLocalPIBTOutcome::kNoFeasibleAction;
      result.blocker = "no_locally_feasible_one_edge_action";
      return result;
    }

    ++result.proposal_validation_count;
    if (!validate_proposal(result.actions, bags_by_id, result.blocker)) {
      result.outcome = BoundedLocalPIBTOutcome::kPrepareRejected;
      return result;
    }
    if (!fault_batch_is_current(result.actions, callbacks, result)) {
      result.outcome = BoundedLocalPIBTOutcome::kFaultGenerationChanged;
      return result;
    }

    ++result.prepare_call_count;
    bool prepared = false;
    try {
      prepared = callbacks.prepare(result.actions);
    } catch (...) {
      result.blocker = "prepare_callback_threw";
      rollback_batch(result.actions, callbacks, result);
      throw;
    }
    if (!prepared) {
      if (result.blocker.empty()) {
        result.blocker = "prepare_callback_rejected_batch";
      }
      rollback_batch(result.actions, callbacks, result);
      result.outcome = BoundedLocalPIBTOutcome::kPrepareRejected;
      return result;
    }
    result.prepared = true;

    // Re-read every selected directed edge after prepare and immediately
    // before atomic publish.  A repair/fault generation change invalidates the
    // complete batch, never only one member.
    if (!fault_batch_is_current(result.actions, callbacks, result)) {
      rollback_batch(result.actions, callbacks, result);
      result.outcome = BoundedLocalPIBTOutcome::kFaultGenerationChanged;
      return result;
    }

    ++result.commit_call_count;
    bool committed = false;
    try {
      committed = callbacks.commit(result.actions);
    } catch (...) {
      result.blocker = "commit_callback_threw";
      rollback_batch(result.actions, callbacks, result);
      // A commit exception is materially different from an explicit logical
      // rejection.  Roll back the prepared batch, then preserve the exception
      // for the caller instead of silently converting it into continued
      // resolver execution.
      throw;
    }
    if (!committed) {
      if (result.blocker.empty()) {
        result.blocker = "commit_callback_rejected_batch";
      }
      rollback_batch(result.actions, callbacks, result);
      result.outcome = BoundedLocalPIBTOutcome::kCommitRejected;
      return result;
    }

    result.committed = true;
    result.outcome = BoundedLocalPIBTOutcome::kCommitted;
    result.blocker.clear();
    return result;
  }
};

}  // namespace czr005::ics
