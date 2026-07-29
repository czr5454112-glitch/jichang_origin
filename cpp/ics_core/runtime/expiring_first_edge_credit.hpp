#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <deque>
#include <limits>
#include <map>
#include <set>
#include <string>
#include <string_view>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "ics_core/io/canonical_map2_reader.hpp"

namespace czr005::ics {

// A credit is deliberately limited to one real, immediately adjacent edge.
// It is not a route, a path prefix, or a reservation beyond that edge.
enum class FirstEdgeCreditState {
  kIssued,
  kBound,
  kConsumed,
  kExpired,
  kRevoked,
};

inline const char* first_edge_credit_state_name(FirstEdgeCreditState state) {
  switch (state) {
    case FirstEdgeCreditState::kIssued:
      return "issued";
    case FirstEdgeCreditState::kBound:
      return "bound";
    case FirstEdgeCreditState::kConsumed:
      return "consumed";
    case FirstEdgeCreditState::kExpired:
      return "expired";
    case FirstEdgeCreditState::kRevoked:
      return "revoked";
  }
  return "unknown";
}

struct FirstEdgeCredit {
  std::uint64_t credit_id = 0;
  int from_node = -1;
  int to_node = -1;
  int goal = -1;
  double earliest = 0.0;
  double latest = 0.0;
  std::uint64_t generation = 0;
  double expiry = 0.0;
  int capacity = 0;
  int owner_or_unbound = -1;
  int fault_generation = 0;
  FirstEdgeCreditState state = FirstEdgeCreditState::kIssued;
  std::string terminal_reason;
};

struct FirstEdgeCreditIssueRequest {
  int from_node = -1;
  int to_node = -1;
  int goal = -1;
  double earliest = 0.0;
  double latest = 0.0;
  std::uint64_t generation = 0;
  double expiry = 0.0;
  int capacity = 1;
  int owner_or_unbound = -1;
  int fault_generation = 0;
  double now = 0.0;
  double snapshot_received_at = 0.0;
  double max_snapshot_age = 0.0;
  int edge_capacity = 1;
  bool physical_fault_active = false;
};

struct FirstEdgeCreditUseContext {
  int owner = -1;
  int from_node = -1;
  int to_node = -1;
  int goal = -1;
  double now = 0.0;
  std::uint64_t generation = 0;
  int fault_generation = 0;
  bool physical_fault_active = false;
};

struct FirstEdgeCreditOperation {
  bool accepted = false;
  std::string reason;
  FirstEdgeCredit credit;
};

struct FirstEdgeCreditBatchEntry {
  std::uint64_t credit_id = 0;
  FirstEdgeCreditUseContext context;
};

struct FirstEdgeCreditBatchOperation {
  bool accepted = false;
  std::string reason;
  std::size_t entry_count = 0;
};

static_assert(
    std::is_nothrow_move_constructible_v<
        FirstEdgeCreditBatchOperation>,
    "committed batch results must be returnable without allocation or throw");

struct FirstEdgeCreditLifecycleEvent {
  double time = 0.0;
  std::string action;
  std::string reason;
  FirstEdgeCredit credit;
};

struct FirstEdgeCreditCounters {
  std::uint64_t issue_attempt_count = 0;
  std::uint64_t issued_count = 0;
  std::uint64_t validation_attempt_count = 0;
  std::uint64_t validation_success_count = 0;
  std::uint64_t bind_attempt_count = 0;
  std::uint64_t bound_count = 0;
  std::uint64_t consume_attempt_count = 0;
  std::uint64_t consumed_count = 0;
  std::uint64_t expired_count = 0;
  std::uint64_t fault_revocation_count = 0;
  std::uint64_t generation_revocation_count = 0;
  std::uint64_t invalid_revocation_count = 0;
  std::uint64_t duplicate_rejection_count = 0;
  std::uint64_t capacity_rejection_count = 0;
  std::uint64_t stale_snapshot_rejection_count = 0;
  std::uint64_t physical_fault_rejection_count = 0;
  std::uint64_t too_early_rejection_count = 0;
  std::uint64_t unknown_credit_rejection_count = 0;
  std::uint64_t invalid_request_rejection_count = 0;
  std::uint64_t lifecycle_dropped_count = 0;
  int active_count = 0;
  int peak_active_count = 0;
};

struct FirstEdgeCreditIndexCheckpoint {
  long long key = 0;
  std::vector<std::uint64_t> credit_ids;
};

struct FirstEdgeCreditExpiryCheckpoint {
  double expiry = 0.0;
  std::uint64_t credit_id = 0;
};

struct ExpiringFirstEdgeCreditCheckpoint {
  std::uint64_t next_credit_id = 1;
  FirstEdgeCreditCounters counters;
  std::vector<FirstEdgeCredit> active_credits;
  std::vector<FirstEdgeCreditIndexCheckpoint> active_by_edge;
  std::vector<FirstEdgeCreditIndexCheckpoint> active_by_destination;
  std::vector<std::pair<long long, int>> active_capacity_by_edge;
  std::vector<std::pair<int, std::uint64_t>> active_by_owner;
  std::vector<FirstEdgeCreditExpiryCheckpoint> expiry_order;
  std::size_t lifecycle_limit = 0;
  std::deque<FirstEdgeCreditLifecycleEvent> lifecycle;
  std::string canonical_sha256;
};

class ExpiringFirstEdgeCreditLedger {
 public:
  explicit ExpiringFirstEdgeCreditLedger(std::size_t lifecycle_limit = 256)
      : lifecycle_limit_(lifecycle_limit) {}

  ExpiringFirstEdgeCreditLedger(const ExpiringFirstEdgeCreditLedger& other)
      : next_credit_id_(other.next_credit_id_),
        counters_(other.counters_),
        credits_(other.credits_),
        active_by_edge_(other.active_by_edge_),
        active_by_destination_(other.active_by_destination_),
        active_capacity_by_edge_(other.active_capacity_by_edge_),
        active_by_owner_(other.active_by_owner_),
        lifecycle_limit_(other.lifecycle_limit_),
        lifecycle_(other.lifecycle_) {
    rebuild_expiry_index();
  }

  ExpiringFirstEdgeCreditLedger& operator=(
      const ExpiringFirstEdgeCreditLedger& other) {
    if (this == &other) {
      return *this;
    }
    ExpiringFirstEdgeCreditLedger copy(other);
    swap(copy);
    return *this;
  }

  ExpiringFirstEdgeCreditLedger(ExpiringFirstEdgeCreditLedger&&) noexcept =
      default;
  ExpiringFirstEdgeCreditLedger& operator=(
      ExpiringFirstEdgeCreditLedger&&) noexcept = default;

  FirstEdgeCreditOperation issue(const FirstEdgeCreditIssueRequest& request) {
    ++counters_.issue_attempt_count;
    expire_due(request.now);

    FirstEdgeCredit attempted;
    attempted.from_node = request.from_node;
    attempted.to_node = request.to_node;
    attempted.goal = request.goal;
    attempted.earliest = request.earliest;
    attempted.latest = request.latest;
    attempted.generation = request.generation;
    attempted.expiry = request.expiry;
    attempted.capacity = request.capacity;
    attempted.owner_or_unbound = request.owner_or_unbound;
    attempted.fault_generation = request.fault_generation;

    if (!valid_issue_request(request)) {
      ++counters_.invalid_request_rejection_count;
      append_lifecycle(request.now, "issue_rejected", "invalid_request", attempted);
      return {false, "invalid_request", attempted};
    }
    if (request.physical_fault_active) {
      ++counters_.physical_fault_rejection_count;
      append_lifecycle(request.now, "issue_rejected", "physical_fault", attempted);
      return {false, "physical_fault", attempted};
    }
    if (request.generation == 0 ||
        request.snapshot_received_at > request.now + kEpsilon ||
        request.now - request.snapshot_received_at >
            request.max_snapshot_age + kEpsilon) {
      ++counters_.stale_snapshot_rejection_count;
      append_lifecycle(request.now, "issue_rejected", "stale_snapshot", attempted);
      return {false, "stale_snapshot", attempted};
    }
    if (request.owner_or_unbound >= 0 &&
        active_by_owner_.find(request.owner_or_unbound) != active_by_owner_.end()) {
      ++counters_.duplicate_rejection_count;
      append_lifecycle(request.now, "issue_rejected", "duplicate_owner", attempted);
      return {false, "duplicate_owner", attempted};
    }

    const long long edge = directed_key(request.from_node, request.to_node);
    const int active_units =
        active_capacity_by_edge_.find(edge) == active_capacity_by_edge_.end()
            ? 0
            : active_capacity_by_edge_.at(edge);
    if (active_units + request.capacity > request.edge_capacity) {
      ++counters_.capacity_rejection_count;
      append_lifecycle(request.now, "issue_rejected", "capacity_exhausted", attempted);
      return {false, "capacity_exhausted", attempted};
    }

    attempted.credit_id = next_credit_id_++;
    credits_.emplace(attempted.credit_id, attempted);
    active_by_edge_[edge].insert(attempted.credit_id);
    active_by_destination_[attempted.to_node].insert(attempted.credit_id);
    active_capacity_by_edge_[edge] += attempted.capacity;
    if (attempted.owner_or_unbound >= 0) {
      active_by_owner_[attempted.owner_or_unbound] = attempted.credit_id;
    }
    expiry_by_credit_[attempted.credit_id] =
        expiry_index_.emplace(std::min(attempted.latest, attempted.expiry),
                              attempted.credit_id);
    ++counters_.issued_count;
    ++counters_.active_count;
    counters_.peak_active_count =
        std::max(counters_.peak_active_count, counters_.active_count);
    append_lifecycle(request.now, "issued", "issued", attempted);
    return {true, "issued", attempted};
  }

  FirstEdgeCreditOperation validate(std::uint64_t credit_id,
                                    const FirstEdgeCreditUseContext& context) {
    ++counters_.validation_attempt_count;
    auto* credit = mutable_credit(credit_id);
    if (credit == nullptr) {
      ++counters_.unknown_credit_rejection_count;
      return {false, "unknown_credit", {}};
    }
    const auto validity = validate_active(*credit, context, "validate");
    if (validity.accepted) {
      ++counters_.validation_success_count;
    }
    return validity;
  }

  FirstEdgeCreditOperation bind(std::uint64_t credit_id,
                                const FirstEdgeCreditUseContext& context) {
    ++counters_.bind_attempt_count;
    auto* credit = mutable_credit(credit_id);
    if (credit == nullptr) {
      ++counters_.unknown_credit_rejection_count;
      return {false, "unknown_credit", {}};
    }
    if (credit->state != FirstEdgeCreditState::kIssued) {
      ++counters_.duplicate_rejection_count;
      append_lifecycle(context.now, "bind_rejected", "duplicate_or_terminal", *credit);
      return {false, "duplicate_or_terminal", *credit};
    }
    const auto validity = validate_active(*credit, context, "bind");
    if (!validity.accepted) {
      return validity;
    }
    credit = mutable_credit(credit_id);
    if (credit == nullptr) {
      return {false, "unknown_credit", {}};
    }
    if (credit->owner_or_unbound < 0) {
      if (context.owner < 0 ||
          active_by_owner_.find(context.owner) != active_by_owner_.end()) {
        ++counters_.duplicate_rejection_count;
        append_lifecycle(context.now, "bind_rejected", "duplicate_owner", *credit);
        return {false, "duplicate_owner", *credit};
      }
      credit->owner_or_unbound = context.owner;
      active_by_owner_[context.owner] = credit_id;
    }
    credit->state = FirstEdgeCreditState::kBound;
    ++counters_.bound_count;
    append_lifecycle(context.now, "bound", "selected_first_edge", *credit);
    return {true, "bound", *credit};
  }

  FirstEdgeCreditOperation consume(std::uint64_t credit_id,
                                   const FirstEdgeCreditUseContext& context) {
    ++counters_.consume_attempt_count;
    auto* credit = mutable_credit(credit_id);
    if (credit == nullptr) {
      ++counters_.unknown_credit_rejection_count;
      return {false, "unknown_credit", {}};
    }
    if (credit->state != FirstEdgeCreditState::kBound) {
      ++counters_.duplicate_rejection_count;
      append_lifecycle(context.now, "consume_rejected", "not_bound", *credit);
      return {false, "not_bound", *credit};
    }
    const auto validity = validate_active(*credit, context, "consume");
    if (!validity.accepted) {
      return validity;
    }
    credit = mutable_credit(credit_id);
    if (credit == nullptr) {
      return {false, "unknown_credit", {}};
    }
    const auto terminal = terminate(*credit,
                                    FirstEdgeCreditState::kConsumed,
                                    context.now,
                                    "consumed",
                                    "selected_first_edge_committed");
    ++counters_.consumed_count;
    return {true, "consumed", terminal};
  }

  // Closes a caller-bounded set of first-edge credits atomically.  Every
  // credit/context and all cross-entry owner constraints are checked before
  // mutation.  Bound/consumed lifecycle snapshots are then fully constructed
  // off-ledger and appended with a strong exception guarantee.  The remaining
  // publish phase only removes already-found active entries and updates scalar
  // counters, so allocator exceptions cannot expose a partially closed batch.
  FirstEdgeCreditBatchOperation bind_and_consume_bounded_batch(
      const std::vector<FirstEdgeCreditBatchEntry>& entries,
      std::size_t max_entries) {
    if (entries.empty() || max_entries == 0 ||
        entries.size() > max_entries) {
      return {false, "empty_or_oversized_batch", entries.size()};
    }

    std::unordered_set<std::uint64_t> seen_credit_ids;
    std::unordered_set<int> staged_unbound_owners;
    seen_credit_ids.reserve(entries.size());
    staged_unbound_owners.reserve(entries.size());
    for (const auto& entry : entries) {
      if (entry.credit_id == 0 ||
          !seen_credit_ids.insert(entry.credit_id).second) {
        return {false, "invalid_or_duplicate_credit", entries.size()};
      }
      const auto found = credits_.find(entry.credit_id);
      if (found == credits_.end()) {
        return {false, "unknown_credit", entries.size()};
      }
      const auto& credit = found->second;
      if (credit.state != FirstEdgeCreditState::kIssued) {
        return {false, "duplicate_or_terminal", entries.size()};
      }
      const std::string invalid =
          validate_active_without_mutation(credit, entry.context);
      if (!invalid.empty()) {
        return {false, invalid, entries.size()};
      }
      if (credit.owner_or_unbound < 0) {
        if (active_by_owner_.find(entry.context.owner) !=
                active_by_owner_.end() ||
            !staged_unbound_owners.insert(entry.context.owner).second) {
          return {false, "duplicate_owner", entries.size()};
        }
      }
    }

    // Construct the complete success result before append_lifecycle_batch
    // performs the first ledger mutation.  Returning this named local uses
    // the statically enforced noexcept move above, so no allocation or
    // exception remains possible after the active indexes are erased.
    FirstEdgeCreditBatchOperation success{
        true, "consumed", entries.size()};

    std::vector<FirstEdgeCreditLifecycleEvent> staged_lifecycle;
    staged_lifecycle.reserve(entries.size() * 2);
    for (const auto& entry : entries) {
      FirstEdgeCredit bound = credits_.at(entry.credit_id);
      if (bound.owner_or_unbound < 0) {
        bound.owner_or_unbound = entry.context.owner;
      }
      bound.state = FirstEdgeCreditState::kBound;
      staged_lifecycle.push_back(FirstEdgeCreditLifecycleEvent{
          entry.context.now,
          "bound",
          "selected_first_edge",
          bound});
      FirstEdgeCredit consumed = std::move(bound);
      consumed.state = FirstEdgeCreditState::kConsumed;
      consumed.terminal_reason =
          "selected_first_edge_committed";
      staged_lifecycle.push_back(FirstEdgeCreditLifecycleEvent{
          entry.context.now,
          "consumed",
          "selected_first_edge_committed",
          std::move(consumed)});
    }

    // This append is itself strong-exception-safe: it retains all original
    // lifecycle rows until every staged row has been appended successfully.
    append_lifecycle_batch(std::move(staged_lifecycle));

    // No operation below allocates or has a logical rejection path.  A bound
    // owner mapping need not be materialized between the two states because
    // the complete bounded batch is published as one atomic consume.
    for (const auto& entry : entries) {
      const auto found = credits_.find(entry.credit_id);
      const auto& credit = found->second;
      erase_active_indexes(credit);
      credits_.erase(found);
      ++counters_.bind_attempt_count;
      ++counters_.bound_count;
      ++counters_.consume_attempt_count;
      ++counters_.consumed_count;
      counters_.active_count =
          std::max(0, counters_.active_count - 1);
    }
    return success;
  }

  std::size_t revoke_edge_fault_generation(int from_node,
                                           int to_node,
                                           int current_fault_generation,
                                           bool physical_fault_active,
                                           double now) {
    const long long edge = directed_key(from_node, to_node);
    const auto found = active_by_edge_.find(edge);
    if (found == active_by_edge_.end()) {
      return 0;
    }
    const std::vector<std::uint64_t> credit_ids(found->second.begin(),
                                                 found->second.end());
    std::size_t revoked = 0;
    for (const auto credit_id : credit_ids) {
      auto* credit = mutable_credit(credit_id);
      if (credit == nullptr || !is_active(*credit)) {
        continue;
      }
      if (physical_fault_active ||
          credit->fault_generation != current_fault_generation) {
        terminate(*credit,
                  FirstEdgeCreditState::kRevoked,
                  now,
                  "revoked",
                  physical_fault_active ? "physical_fault"
                                        : "fault_generation_changed");
        ++counters_.fault_revocation_count;
        ++revoked;
      }
    }
    return revoked;
  }

  std::size_t revoke_destination_generation(int to_node,
                                            std::uint64_t current_generation,
                                            double now) {
    const auto found = active_by_destination_.find(to_node);
    if (found == active_by_destination_.end()) {
      return 0;
    }
    const std::vector<std::uint64_t> credit_ids(found->second.begin(),
                                                 found->second.end());
    std::size_t revoked = 0;
    for (const auto credit_id : credit_ids) {
      auto* credit = mutable_credit(credit_id);
      if (credit == nullptr || !is_active(*credit)) {
        continue;
      }
      if (credit->generation != current_generation) {
        terminate(*credit,
                  FirstEdgeCreditState::kRevoked,
                  now,
                  "revoked",
                  "credit_generation_changed");
        ++counters_.generation_revocation_count;
        ++revoked;
      }
    }
    return revoked;
  }

  std::size_t expire_due(double now) {
    std::size_t expired = 0;
    while (!expiry_index_.empty() &&
           expiry_index_.begin()->first < now - kEpsilon) {
      const auto credit_id = expiry_index_.begin()->second;
      auto* credit = mutable_credit(credit_id);
      if (credit == nullptr || !is_active(*credit)) {
        expiry_by_credit_.erase(credit_id);
        expiry_index_.erase(expiry_index_.begin());
        continue;
      }
      terminate(*credit,
                FirstEdgeCreditState::kExpired,
                now,
                "expired",
                "validity_window_elapsed");
      ++counters_.expired_count;
      ++expired;
    }
    return expired;
  }

  [[nodiscard]] const FirstEdgeCredit* find(std::uint64_t credit_id) const {
    const auto found = credits_.find(credit_id);
    return found == credits_.end() ? nullptr : &found->second;
  }

  [[nodiscard]] const FirstEdgeCreditCounters& counters() const noexcept {
    return counters_;
  }

  [[nodiscard]] const std::deque<FirstEdgeCreditLifecycleEvent>& lifecycle() const noexcept {
    return lifecycle_;
  }

  [[nodiscard]] std::size_t stored_active_count() const noexcept {
    return credits_.size();
  }

  [[nodiscard]] std::size_t stored_lifecycle_count() const noexcept {
    return lifecycle_.size();
  }

  [[nodiscard]] std::size_t lifecycle_limit() const noexcept {
    return lifecycle_limit_;
  }

  [[nodiscard]] std::size_t accounted_bytes() const noexcept {
    return sizeof(*this) + credits_.size() * sizeof(FirstEdgeCredit) +
           lifecycle_.size() * sizeof(FirstEdgeCreditLifecycleEvent);
  }

  [[nodiscard]] ExpiringFirstEdgeCreditCheckpoint
  capture_exact_checkpoint() const;

  [[nodiscard]] static ExpiringFirstEdgeCreditLedger
  restore_exact_checkpoint(
      const ExpiringFirstEdgeCreditCheckpoint& checkpoint);

  [[nodiscard]] std::string exact_state_sha256() const {
    return capture_exact_checkpoint().canonical_sha256;
  }

 private:
  static constexpr double kEpsilon = 1.0e-9;

  static long long directed_key(int from_node, int to_node) {
    return (static_cast<long long>(from_node) << 32) ^
           static_cast<unsigned int>(to_node);
  }

  [[nodiscard]] static std::string checkpoint_sha256(
      const ExpiringFirstEdgeCreditCheckpoint& checkpoint);
  static void validate_checkpoint(
      const ExpiringFirstEdgeCreditCheckpoint& checkpoint);

  static bool finite(double value) {
    return std::isfinite(value);
  }

  static bool is_active(const FirstEdgeCredit& credit) {
    return credit.state == FirstEdgeCreditState::kIssued ||
           credit.state == FirstEdgeCreditState::kBound;
  }

  static bool valid_issue_request(const FirstEdgeCreditIssueRequest& request) {
    return request.from_node >= 0 && request.to_node >= 0 && request.goal >= 0 &&
           request.owner_or_unbound >= -1 && request.fault_generation >= 0 &&
           request.capacity > 0 && request.edge_capacity > 0 &&
           finite(request.now) && finite(request.earliest) &&
           finite(request.latest) && finite(request.expiry) &&
           finite(request.snapshot_received_at) &&
           finite(request.max_snapshot_age) && request.now >= 0.0 &&
           request.earliest + kEpsilon >= request.now &&
           request.latest + kEpsilon >= request.earliest &&
           request.expiry + kEpsilon >= request.earliest &&
           request.max_snapshot_age >= 0.0;
  }

  static std::string validate_active_without_mutation(
      const FirstEdgeCredit& credit,
      const FirstEdgeCreditUseContext& context) {
    if (!is_active(credit)) {
      return "terminal_credit";
    }
    if (!finite(context.now) || context.now < 0.0 ||
        context.owner < 0 || context.from_node < 0 ||
        context.to_node < 0 || context.goal < 0 ||
        context.fault_generation < 0 || context.generation == 0) {
      return "invalid_use_context";
    }
    if (context.now > credit.expiry + kEpsilon ||
        context.now > credit.latest + kEpsilon) {
      return "expired";
    }
    if (context.generation != credit.generation) {
      return "credit_generation_changed";
    }
    if (context.physical_fault_active ||
        context.fault_generation != credit.fault_generation) {
      return context.physical_fault_active
                 ? "physical_fault"
                 : "fault_generation_changed";
    }
    if (credit.from_node != context.from_node ||
        credit.to_node != context.to_node ||
        credit.goal != context.goal ||
        (credit.owner_or_unbound >= 0 &&
         credit.owner_or_unbound != context.owner)) {
      return "identity_mismatch";
    }
    if (context.now + kEpsilon < credit.earliest) {
      return "too_early";
    }
    return {};
  }

  void rebuild_expiry_index() {
    expiry_index_.clear();
    expiry_by_credit_.clear();
    std::vector<std::pair<double, std::uint64_t>> expiries;
    expiries.reserve(credits_.size());
    for (const auto& item : credits_) {
      if (is_active(item.second)) {
        expiries.emplace_back(std::min(item.second.latest, item.second.expiry),
                              item.first);
      }
    }
    std::sort(expiries.begin(), expiries.end());
    for (const auto& expiry : expiries) {
      expiry_by_credit_[expiry.second] =
          expiry_index_.emplace(expiry.first, expiry.second);
    }
  }

  void swap(ExpiringFirstEdgeCreditLedger& other) noexcept {
    using std::swap;
    swap(next_credit_id_, other.next_credit_id_);
    swap(counters_, other.counters_);
    swap(credits_, other.credits_);
    swap(active_by_edge_, other.active_by_edge_);
    swap(active_by_destination_, other.active_by_destination_);
    swap(active_capacity_by_edge_, other.active_capacity_by_edge_);
    swap(active_by_owner_, other.active_by_owner_);
    swap(expiry_index_, other.expiry_index_);
    swap(expiry_by_credit_, other.expiry_by_credit_);
    swap(lifecycle_limit_, other.lifecycle_limit_);
    swap(lifecycle_, other.lifecycle_);
  }

  FirstEdgeCredit* mutable_credit(std::uint64_t credit_id) {
    const auto found = credits_.find(credit_id);
    return found == credits_.end() ? nullptr : &found->second;
  }

  FirstEdgeCreditOperation validate_active(
      FirstEdgeCredit& credit,
      const FirstEdgeCreditUseContext& context,
      const std::string& action) {
    if (!is_active(credit)) {
      ++counters_.duplicate_rejection_count;
      append_lifecycle(context.now, action + "_rejected", "terminal_credit", credit);
      return {false, "terminal_credit", credit};
    }
    if (!finite(context.now) || context.now < 0.0 || context.owner < 0 ||
        context.from_node < 0 || context.to_node < 0 || context.goal < 0 ||
        context.fault_generation < 0 || context.generation == 0) {
      const auto terminal = terminate(credit,
                                      FirstEdgeCreditState::kRevoked,
                                      context.now,
                                      "revoked",
                                      "invalid_use_context");
      ++counters_.invalid_revocation_count;
      return {false, "invalid_use_context", terminal};
    }
    if (context.now > credit.expiry + kEpsilon ||
        context.now > credit.latest + kEpsilon) {
      const auto terminal = terminate(credit,
                                      FirstEdgeCreditState::kExpired,
                                      context.now,
                                      "expired",
                                      "validity_window_elapsed");
      ++counters_.expired_count;
      return {false, "expired", terminal};
    }
    if (context.generation != credit.generation) {
      const auto terminal = terminate(credit,
                                      FirstEdgeCreditState::kRevoked,
                                      context.now,
                                      "revoked",
                                      "credit_generation_changed");
      ++counters_.generation_revocation_count;
      return {false, "credit_generation_changed", terminal};
    }
    if (context.physical_fault_active ||
        context.fault_generation != credit.fault_generation) {
      const auto terminal = terminate(
          credit,
          FirstEdgeCreditState::kRevoked,
          context.now,
          "revoked",
          context.physical_fault_active ? "physical_fault"
                                        : "fault_generation_changed");
      ++counters_.fault_revocation_count;
      return {false,
              context.physical_fault_active ? "physical_fault"
                                            : "fault_generation_changed",
              terminal};
    }
    if (credit.from_node != context.from_node ||
        credit.to_node != context.to_node || credit.goal != context.goal ||
        (credit.owner_or_unbound >= 0 &&
         credit.owner_or_unbound != context.owner)) {
      const auto terminal = terminate(credit,
                                      FirstEdgeCreditState::kRevoked,
                                      context.now,
                                      "revoked",
                                      "identity_mismatch");
      ++counters_.invalid_revocation_count;
      return {false, "identity_mismatch", terminal};
    }
    if (context.now + kEpsilon < credit.earliest) {
      ++counters_.too_early_rejection_count;
      append_lifecycle(context.now, action + "_rejected", "too_early", credit);
      return {false, "too_early", credit};
    }
    return {true, "valid", credit};
  }

  FirstEdgeCredit terminate(FirstEdgeCredit& credit,
                            FirstEdgeCreditState state,
                            double now,
                            const std::string& action,
                            const std::string& reason) {
    if (!is_active(credit)) {
      return credit;
    }
    FirstEdgeCredit terminal = credit;
    const long long edge = directed_key(credit.from_node, credit.to_node);
    const auto edge_found = active_by_edge_.find(edge);
    if (edge_found != active_by_edge_.end()) {
      edge_found->second.erase(credit.credit_id);
      if (edge_found->second.empty()) {
        active_by_edge_.erase(edge_found);
      }
    }
    const auto destination_found = active_by_destination_.find(credit.to_node);
    if (destination_found != active_by_destination_.end()) {
      destination_found->second.erase(credit.credit_id);
      if (destination_found->second.empty()) {
        active_by_destination_.erase(destination_found);
      }
    }
    const auto capacity_found = active_capacity_by_edge_.find(edge);
    if (capacity_found != active_capacity_by_edge_.end()) {
      capacity_found->second =
          std::max(0, capacity_found->second - credit.capacity);
      if (capacity_found->second == 0) {
        active_capacity_by_edge_.erase(capacity_found);
      }
    }
    if (credit.owner_or_unbound >= 0) {
      const auto owner_found = active_by_owner_.find(credit.owner_or_unbound);
      if (owner_found != active_by_owner_.end() &&
          owner_found->second == credit.credit_id) {
        active_by_owner_.erase(owner_found);
      }
    }
    const auto expiry_found = expiry_by_credit_.find(credit.credit_id);
    if (expiry_found != expiry_by_credit_.end()) {
      expiry_index_.erase(expiry_found->second);
      expiry_by_credit_.erase(expiry_found);
    }
    const auto credit_id = credit.credit_id;
    terminal.state = state;
    terminal.terminal_reason = reason;
    credits_.erase(credit_id);
    counters_.active_count = std::max(0, counters_.active_count - 1);
    append_lifecycle(now, action, reason, terminal);
    return terminal;
  }

  void erase_active_indexes(const FirstEdgeCredit& credit) {
    const long long edge =
        directed_key(credit.from_node, credit.to_node);
    const auto edge_found = active_by_edge_.find(edge);
    if (edge_found != active_by_edge_.end()) {
      edge_found->second.erase(credit.credit_id);
      if (edge_found->second.empty()) {
        active_by_edge_.erase(edge_found);
      }
    }
    const auto destination_found =
        active_by_destination_.find(credit.to_node);
    if (destination_found != active_by_destination_.end()) {
      destination_found->second.erase(credit.credit_id);
      if (destination_found->second.empty()) {
        active_by_destination_.erase(destination_found);
      }
    }
    const auto capacity_found =
        active_capacity_by_edge_.find(edge);
    if (capacity_found != active_capacity_by_edge_.end()) {
      capacity_found->second =
          std::max(0,
                   capacity_found->second - credit.capacity);
      if (capacity_found->second == 0) {
        active_capacity_by_edge_.erase(capacity_found);
      }
    }
    if (credit.owner_or_unbound >= 0) {
      const auto owner_found =
          active_by_owner_.find(credit.owner_or_unbound);
      if (owner_found != active_by_owner_.end() &&
          owner_found->second == credit.credit_id) {
        active_by_owner_.erase(owner_found);
      }
    }
    const auto expiry_found =
        expiry_by_credit_.find(credit.credit_id);
    if (expiry_found != expiry_by_credit_.end()) {
      expiry_index_.erase(expiry_found->second);
      expiry_by_credit_.erase(expiry_found);
    }
  }

  void append_lifecycle_batch(
      std::vector<FirstEdgeCreditLifecycleEvent> events) {
    if (events.empty()) {
      return;
    }
    if (lifecycle_limit_ == 0) {
      counters_.lifecycle_dropped_count += events.size();
      return;
    }
    const std::size_t original_size = lifecycle_.size();
    try {
      for (auto& event : events) {
        lifecycle_.push_back(std::move(event));
      }
    } catch (...) {
      while (lifecycle_.size() > original_size) {
        lifecycle_.pop_back();
      }
      throw;
    }
    while (lifecycle_.size() > lifecycle_limit_) {
      lifecycle_.pop_front();
      ++counters_.lifecycle_dropped_count;
    }
  }

  void append_lifecycle(double time,
                        const std::string& action,
                        const std::string& reason,
                        const FirstEdgeCredit& credit) {
    if (lifecycle_limit_ == 0) {
      ++counters_.lifecycle_dropped_count;
      return;
    }
    FirstEdgeCreditLifecycleEvent event{
        time, action, reason, credit};
    lifecycle_.push_back(std::move(event));
    if (lifecycle_.size() > lifecycle_limit_) {
      lifecycle_.pop_front();
      ++counters_.lifecycle_dropped_count;
    }
  }

  std::uint64_t next_credit_id_ = 1;
  FirstEdgeCreditCounters counters_;
  std::unordered_map<std::uint64_t, FirstEdgeCredit> credits_;
  std::unordered_map<long long, std::unordered_set<std::uint64_t>> active_by_edge_;
  std::unordered_map<int, std::unordered_set<std::uint64_t>> active_by_destination_;
  std::unordered_map<long long, int> active_capacity_by_edge_;
  std::unordered_map<int, std::uint64_t> active_by_owner_;
  std::multimap<double, std::uint64_t> expiry_index_;
  std::unordered_map<
      std::uint64_t,
      std::multimap<double, std::uint64_t>::iterator>
      expiry_by_credit_;
  std::size_t lifecycle_limit_ = 256;
  std::deque<FirstEdgeCreditLifecycleEvent> lifecycle_;
};

namespace first_edge_credit_checkpoint_detail {

class Writer {
 public:
  Writer() {
    string("czr005.expiring_first_edge_credit.exact_checkpoint.v1");
  }

  void boolean(bool value) {
    payload_.push_back(value ? '\x01' : '\x00');
  }

  void u64(std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
      payload_.push_back(
          static_cast<char>((value >> shift) & 0xffU));
    }
  }

  void i64(std::int64_t value) {
    u64(static_cast<std::uint64_t>(value));
  }

  void floating(double value) {
    std::uint64_t bits = 0;
    static_assert(sizeof(bits) == sizeof(value));
    std::memcpy(&bits, &value, sizeof(bits));
    u64(bits);
  }

  void string(std::string_view value) {
    u64(static_cast<std::uint64_t>(value.size()));
    payload_.append(value);
  }

  [[nodiscard]] std::string sha256() const {
    return canonical_map2_detail::sha256_hex(payload_);
  }

 private:
  std::string payload_;
};

inline void fingerprint_credit(Writer& writer,
                               const FirstEdgeCredit& credit) {
  writer.u64(credit.credit_id);
  writer.i64(credit.from_node);
  writer.i64(credit.to_node);
  writer.i64(credit.goal);
  writer.floating(credit.earliest);
  writer.floating(credit.latest);
  writer.u64(credit.generation);
  writer.floating(credit.expiry);
  writer.i64(credit.capacity);
  writer.i64(credit.owner_or_unbound);
  writer.i64(credit.fault_generation);
  writer.i64(static_cast<int>(credit.state));
  writer.string(credit.terminal_reason);
}

inline void fingerprint_counters(
    Writer& writer,
    const FirstEdgeCreditCounters& counters) {
  writer.u64(counters.issue_attempt_count);
  writer.u64(counters.issued_count);
  writer.u64(counters.validation_attempt_count);
  writer.u64(counters.validation_success_count);
  writer.u64(counters.bind_attempt_count);
  writer.u64(counters.bound_count);
  writer.u64(counters.consume_attempt_count);
  writer.u64(counters.consumed_count);
  writer.u64(counters.expired_count);
  writer.u64(counters.fault_revocation_count);
  writer.u64(counters.generation_revocation_count);
  writer.u64(counters.invalid_revocation_count);
  writer.u64(counters.duplicate_rejection_count);
  writer.u64(counters.capacity_rejection_count);
  writer.u64(counters.stale_snapshot_rejection_count);
  writer.u64(counters.physical_fault_rejection_count);
  writer.u64(counters.too_early_rejection_count);
  writer.u64(counters.unknown_credit_rejection_count);
  writer.u64(counters.invalid_request_rejection_count);
  writer.u64(counters.lifecycle_dropped_count);
  writer.i64(counters.active_count);
  writer.i64(counters.peak_active_count);
}

}  // namespace first_edge_credit_checkpoint_detail

inline std::string
ExpiringFirstEdgeCreditLedger::checkpoint_sha256(
    const ExpiringFirstEdgeCreditCheckpoint& checkpoint) {
  using namespace first_edge_credit_checkpoint_detail;
  Writer writer;
  writer.u64(checkpoint.next_credit_id);
  fingerprint_counters(writer, checkpoint.counters);
  writer.u64(checkpoint.active_credits.size());
  for (const auto& credit : checkpoint.active_credits) {
    fingerprint_credit(writer, credit);
  }
  const auto fingerprint_index =
      [&](const auto& index) {
        writer.u64(index.size());
        for (const auto& item : index) {
          writer.i64(item.key);
          writer.u64(item.credit_ids.size());
          for (const auto id : item.credit_ids) {
            writer.u64(id);
          }
        }
      };
  fingerprint_index(checkpoint.active_by_edge);
  fingerprint_index(checkpoint.active_by_destination);
  writer.u64(checkpoint.active_capacity_by_edge.size());
  for (const auto& item :
       checkpoint.active_capacity_by_edge) {
    writer.i64(item.first);
    writer.i64(item.second);
  }
  writer.u64(checkpoint.active_by_owner.size());
  for (const auto& item : checkpoint.active_by_owner) {
    writer.i64(item.first);
    writer.u64(item.second);
  }
  writer.u64(checkpoint.expiry_order.size());
  for (const auto& item : checkpoint.expiry_order) {
    writer.floating(item.expiry);
    writer.u64(item.credit_id);
  }
  writer.u64(checkpoint.lifecycle_limit);
  writer.u64(checkpoint.lifecycle.size());
  for (const auto& event : checkpoint.lifecycle) {
    writer.floating(event.time);
    writer.string(event.action);
    writer.string(event.reason);
    fingerprint_credit(writer, event.credit);
  }
  return writer.sha256();
}

inline ExpiringFirstEdgeCreditCheckpoint
ExpiringFirstEdgeCreditLedger::capture_exact_checkpoint() const {
  ExpiringFirstEdgeCreditCheckpoint checkpoint;
  checkpoint.next_credit_id = next_credit_id_;
  checkpoint.counters = counters_;
  checkpoint.active_credits.reserve(credits_.size());
  for (const auto& entry : credits_) {
    checkpoint.active_credits.push_back(entry.second);
  }
  std::sort(
      checkpoint.active_credits.begin(),
      checkpoint.active_credits.end(),
      [](const auto& left, const auto& right) {
        return left.credit_id < right.credit_id;
      });
  checkpoint.active_by_edge.reserve(active_by_edge_.size());
  for (const auto& entry : active_by_edge_) {
    FirstEdgeCreditIndexCheckpoint item;
    item.key = entry.first;
    item.credit_ids.assign(entry.second.begin(),
                           entry.second.end());
    std::sort(item.credit_ids.begin(), item.credit_ids.end());
    checkpoint.active_by_edge.push_back(std::move(item));
  }
  std::sort(
      checkpoint.active_by_edge.begin(),
      checkpoint.active_by_edge.end(),
      [](const auto& left, const auto& right) {
        return left.key < right.key;
      });
  checkpoint.active_by_destination.reserve(
      active_by_destination_.size());
  for (const auto& entry : active_by_destination_) {
    FirstEdgeCreditIndexCheckpoint item;
    item.key = entry.first;
    item.credit_ids.assign(entry.second.begin(),
                           entry.second.end());
    std::sort(item.credit_ids.begin(), item.credit_ids.end());
    checkpoint.active_by_destination.push_back(
        std::move(item));
  }
  std::sort(
      checkpoint.active_by_destination.begin(),
      checkpoint.active_by_destination.end(),
      [](const auto& left, const auto& right) {
        return left.key < right.key;
      });
  checkpoint.active_capacity_by_edge.assign(
      active_capacity_by_edge_.begin(),
      active_capacity_by_edge_.end());
  std::sort(checkpoint.active_capacity_by_edge.begin(),
            checkpoint.active_capacity_by_edge.end());
  checkpoint.active_by_owner.assign(active_by_owner_.begin(),
                                    active_by_owner_.end());
  std::sort(checkpoint.active_by_owner.begin(),
            checkpoint.active_by_owner.end());
  checkpoint.expiry_order.reserve(expiry_index_.size());
  for (const auto& entry : expiry_index_) {
    checkpoint.expiry_order.push_back(
        {entry.first, entry.second});
  }
  checkpoint.lifecycle_limit = lifecycle_limit_;
  checkpoint.lifecycle = lifecycle_;
  checkpoint.canonical_sha256 =
      checkpoint_sha256(checkpoint);
  return checkpoint;
}

inline void ExpiringFirstEdgeCreditLedger::validate_checkpoint(
    const ExpiringFirstEdgeCreditCheckpoint& checkpoint) {
  const bool valid_sha256 =
      checkpoint.canonical_sha256.size() == 64U &&
      std::all_of(
          checkpoint.canonical_sha256.begin(),
          checkpoint.canonical_sha256.end(),
          [](char byte) {
            return (byte >= '0' && byte <= '9') ||
                   (byte >= 'a' && byte <= 'f');
          });
  if (!valid_sha256 ||
      checkpoint.canonical_sha256 !=
          checkpoint_sha256(checkpoint) ||
      checkpoint.next_credit_id == 0 ||
      checkpoint.lifecycle.size() >
          checkpoint.lifecycle_limit ||
      checkpoint.counters.active_count !=
          static_cast<int>(
              checkpoint.active_credits.size()) ||
      checkpoint.next_credit_id !=
          checkpoint.counters.issued_count + 1) {
    throw std::invalid_argument(
        "first-edge credit checkpoint header is inconsistent");
  }
  std::map<long long, std::vector<std::uint64_t>>
      expected_edges;
  std::map<long long, std::vector<std::uint64_t>>
      expected_destinations;
  std::map<long long, int> expected_capacities;
  std::map<int, std::uint64_t> expected_owners;
  std::map<std::uint64_t, double> expected_expiry;
  std::uint64_t previous_id = 0;
  for (const auto& credit : checkpoint.active_credits) {
    if (credit.credit_id == 0 ||
        credit.credit_id <= previous_id ||
        credit.credit_id >= checkpoint.next_credit_id ||
        (credit.state != FirstEdgeCreditState::kIssued &&
         credit.state != FirstEdgeCreditState::kBound) ||
        credit.capacity <= 0 ||
        !std::isfinite(credit.latest) ||
        !std::isfinite(credit.expiry)) {
      throw std::invalid_argument(
          "first-edge credit checkpoint contains invalid active credit");
    }
    previous_id = credit.credit_id;
    const auto edge =
        directed_key(credit.from_node, credit.to_node);
    expected_edges[edge].push_back(credit.credit_id);
    expected_destinations[credit.to_node].push_back(
        credit.credit_id);
    expected_capacities[edge] += credit.capacity;
    if (credit.owner_or_unbound >= 0 &&
        !expected_owners
             .emplace(credit.owner_or_unbound,
                      credit.credit_id)
             .second) {
      throw std::invalid_argument(
          "first-edge credit checkpoint duplicates an owner");
    }
    expected_expiry.emplace(
        credit.credit_id,
        std::min(credit.latest, credit.expiry));
  }
  const auto validate_index =
      [&](const auto& actual, const auto& expected,
          const char* name) {
        if (actual.size() != expected.size()) {
          throw std::invalid_argument(
              std::string(name) + " index size mismatch");
        }
        std::size_t position = 0;
        for (const auto& expected_item : expected) {
          if (actual[position].key != expected_item.first ||
              actual[position].credit_ids !=
                  expected_item.second) {
            throw std::invalid_argument(
                std::string(name) + " index content mismatch");
          }
          ++position;
        }
      };
  validate_index(checkpoint.active_by_edge,
                 expected_edges, "edge");
  validate_index(checkpoint.active_by_destination,
                 expected_destinations, "destination");
  if (checkpoint.active_capacity_by_edge.size() !=
      expected_capacities.size()) {
    throw std::invalid_argument(
        "credit capacity index size mismatch");
  }
  {
    std::size_t position = 0;
    for (const auto& expected : expected_capacities) {
      if (checkpoint.active_capacity_by_edge[position] !=
          expected) {
        throw std::invalid_argument(
            "credit capacity index content mismatch");
      }
      ++position;
    }
  }
  if (checkpoint.active_by_owner.size() !=
      expected_owners.size()) {
    throw std::invalid_argument(
        "credit owner index size mismatch");
  }
  {
    std::size_t position = 0;
    for (const auto& expected : expected_owners) {
      if (checkpoint.active_by_owner[position] != expected) {
        throw std::invalid_argument(
            "credit owner index content mismatch");
      }
      ++position;
    }
  }
  if (checkpoint.expiry_order.size() !=
      expected_expiry.size()) {
    throw std::invalid_argument(
        "credit expiry index size mismatch");
  }
  std::set<std::uint64_t> expiry_ids;
  double previous_expiry =
      -std::numeric_limits<double>::infinity();
  for (const auto& item : checkpoint.expiry_order) {
    const auto expected = expected_expiry.find(item.credit_id);
    if (expected == expected_expiry.end() ||
        item.expiry != expected->second ||
        item.expiry < previous_expiry ||
        !expiry_ids.insert(item.credit_id).second) {
      throw std::invalid_argument(
          "credit expiry index content mismatch");
    }
    previous_expiry = item.expiry;
  }
}

inline ExpiringFirstEdgeCreditLedger
ExpiringFirstEdgeCreditLedger::restore_exact_checkpoint(
    const ExpiringFirstEdgeCreditCheckpoint& checkpoint) {
  validate_checkpoint(checkpoint);
  ExpiringFirstEdgeCreditLedger ledger(
      checkpoint.lifecycle_limit);
  ledger.next_credit_id_ = checkpoint.next_credit_id;
  ledger.counters_ = checkpoint.counters;
  ledger.lifecycle_ = checkpoint.lifecycle;
  for (const auto& credit : checkpoint.active_credits) {
    ledger.credits_.emplace(credit.credit_id, credit);
  }
  for (const auto& item : checkpoint.active_by_edge) {
    ledger.active_by_edge_.emplace(
        item.key,
        std::unordered_set<std::uint64_t>(
            item.credit_ids.begin(), item.credit_ids.end()));
  }
  for (const auto& item :
       checkpoint.active_by_destination) {
    ledger.active_by_destination_.emplace(
        static_cast<int>(item.key),
        std::unordered_set<std::uint64_t>(
            item.credit_ids.begin(), item.credit_ids.end()));
  }
  ledger.active_capacity_by_edge_.insert(
      checkpoint.active_capacity_by_edge.begin(),
      checkpoint.active_capacity_by_edge.end());
  ledger.active_by_owner_.insert(
      checkpoint.active_by_owner.begin(),
      checkpoint.active_by_owner.end());
  for (const auto& item : checkpoint.expiry_order) {
    const auto iterator = ledger.expiry_index_.emplace(
        item.expiry, item.credit_id);
    ledger.expiry_by_credit_.emplace(item.credit_id,
                                     iterator);
  }
  const auto restored = ledger.capture_exact_checkpoint();
  if (restored.canonical_sha256 !=
      checkpoint.canonical_sha256) {
    throw std::invalid_argument(
        "first-edge credit checkpoint failed exact restore");
  }
  return ledger;
}

}  // namespace czr005::ics
