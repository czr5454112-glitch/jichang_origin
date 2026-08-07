#pragma once

#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <tuple>
#include <type_traits>
#include <utility>
#include <vector>

namespace czr005::ics {

class EventDrivenJunctionRuntime;
class DestinationMergeGrantController;
class DestinationMergeGrantCheckpointCodec;

// The merge protocol is intentionally one-hop. It owns no route suffix,
// global task list, global reservation table, or airport-wide queue view.
struct DestinationMergeGrantBoundary {
  static constexpr int kReservationDepth = 1;
  static constexpr int kDirectedEdgesPerGrant = 1;
  static constexpr int kDestinationSlotsPerGrant = 1;
  static constexpr bool kReadsFutureRoute = false;
  static constexpr bool kReadsGlobalTaskList = false;
  static constexpr bool kReadsGlobalReservationTable = false;
  static constexpr bool kReadsAllAirportQueues = false;
  static constexpr bool kUsesTeacherPath = false;
  static constexpr bool kStoresPostHocOutcomeInRequest = false;
};

enum class DestinationMergeTaskClassCode {
  kRepairedFaultAffected = 0,
  kFaultAffected = 1,
  kStorageOut = 2,
  kNew = 3,
  kOnPath = 4,
};

inline int destination_merge_task_class_code(
    bool repaired_fault_affected,
    bool fault_affected,
    bool storage_out,
    bool is_new) noexcept {
  if (repaired_fault_affected) {
    return static_cast<int>(
        DestinationMergeTaskClassCode::
            kRepairedFaultAffected);
  }
  if (fault_affected) {
    return static_cast<int>(
        DestinationMergeTaskClassCode::kFaultAffected);
  }
  if (storage_out) {
    return static_cast<int>(
        DestinationMergeTaskClassCode::kStorageOut);
  }
  if (is_new) {
    return static_cast<int>(
        DestinationMergeTaskClassCode::kNew);
  }
  return static_cast<int>(
      DestinationMergeTaskClassCode::kOnPath);
}

struct MergeDirectedEdge {
  int from_node = -1;
  int to_node = -1;
};

inline bool operator==(const MergeDirectedEdge& left,
                       const MergeDirectedEdge& right) noexcept {
  return left.from_node == right.from_node &&
         left.to_node == right.to_node;
}

inline bool operator!=(const MergeDirectedEdge& left,
                       const MergeDirectedEdge& right) noexcept {
  return !(left == right);
}

enum class MergeGrantState {
  kRequested,
  kIssued,
  kPrepared,
  kCommitted,
  kConsumed,
  kExpired,
  kRevokedFault,
  kRevokedStaleState,
  kRevokedReplanCurrentEdge,
  kRolledBack,
};

inline const char* merge_grant_state_name(MergeGrantState state) noexcept {
  switch (state) {
    case MergeGrantState::kRequested:
      return "REQUESTED";
    case MergeGrantState::kIssued:
      return "ISSUED";
    case MergeGrantState::kPrepared:
      return "PREPARED";
    case MergeGrantState::kCommitted:
      return "COMMITTED";
    case MergeGrantState::kConsumed:
      return "CONSUMED";
    case MergeGrantState::kExpired:
      return "EXPIRED";
    case MergeGrantState::kRevokedFault:
      return "REVOKED_FAULT";
    case MergeGrantState::kRevokedStaleState:
      return "REVOKED_STALE_STATE";
    case MergeGrantState::kRevokedReplanCurrentEdge:
      return "REVOKED_REPLAN_CURRENT_EDGE";
    case MergeGrantState::kRolledBack:
      return "ROLLED_BACK";
  }
  return "UNKNOWN";
}

enum class MergeGrantReason {
  kSubmitted,
  kExactSlotCommitted,
  kExactSlotBusy,
  kRequestExpired,
  kGrantExpiredAtDestinationEntry,
  kFaultGenerationChanged,
  kCalendarGenerationChanged,
  kQueueCapacityBlock,
  kQueueGenerationChanged,
  kCurrentEdgeChanged,
  kOwnerStateChanged,
  kActiveGrantExists,
  kInjectedPrepareRollback,
  kContendedLoserRetry,
  kConsumedAtDestinationEntry,
  kConsumedAtDestinationEntryAfterInflightFaultGenerationChange,
};

inline const char* merge_grant_reason_name(
    MergeGrantReason reason) noexcept {
  switch (reason) {
    case MergeGrantReason::kSubmitted:
      return "submitted";
    case MergeGrantReason::kExactSlotCommitted:
      return "exact_slot_committed";
    case MergeGrantReason::kExactSlotBusy:
      return "exact_slot_busy_no_future_shift";
    case MergeGrantReason::kRequestExpired:
      return "request_expired";
    case MergeGrantReason::kGrantExpiredAtDestinationEntry:
      return "grant_expired_at_destination_entry";
    case MergeGrantReason::kFaultGenerationChanged:
      return "fault_generation_changed";
    case MergeGrantReason::kCalendarGenerationChanged:
      return "calendar_generation_changed";
    case MergeGrantReason::kQueueCapacityBlock:
      return "destination_queue_capacity_block";
    case MergeGrantReason::kQueueGenerationChanged:
      return "junction_queue_generation_changed";
    case MergeGrantReason::kCurrentEdgeChanged:
      return "current_edge_changed";
    case MergeGrantReason::kOwnerStateChanged:
      return "owner_state_changed";
    case MergeGrantReason::kActiveGrantExists:
      return "active_unconsumed_grant_exists";
    case MergeGrantReason::kInjectedPrepareRollback:
      return "injected_prepare_rollback";
    case MergeGrantReason::kContendedLoserRetry:
      return "contended_loser_retry";
    case MergeGrantReason::kConsumedAtDestinationEntry:
      return "consumed_at_destination_entry";
    case MergeGrantReason::
        kConsumedAtDestinationEntryAfterInflightFaultGenerationChange:
      return "consumed_at_destination_entry_after_inflight_fault_generation_change";
  }
  return "unknown";
}

// All fields are current-local observations captured at the phase-5a request
// boundary. In particular, this record contains no future route/schedule or
// post-hoc outcome.
struct DestinationMergeRequest {
  std::uint64_t request_id = 0;  // assigned by the destination controller
  std::uint64_t lineage = 0;
  std::uint64_t request_generation = 0;
  std::uint64_t junction_queue_generation = 0;
  int runtime_bag_id = -1;
  int task_id = -1;
  std::string segment_id;
  int upstream_node = -1;
  int destination_merge_node = -1;
  MergeDirectedEdge requested_directed_edge;
  double request_time = 0.0;
  // Stable first contention time for M1 fairness. Exact slot arithmetic
  // continues to use request_time from the current publication attempt.
  double fifo_request_time = 0.0;
  double earliest_edge_entry = 0.0;
  double exact_edge_travel_seconds = 0.0;
  double projected_arrival = 0.0;
  int goal = -1;
  double route_score = 0.0;
  double static_remaining = 0.0;
  double destination_service_seconds = 0.0;
  int downstream_queue_pressure = 0;
  double deadline_slack = 0.0;
  double wait_age = 0.0;
  // Stable semantic class code: 0 repaired-fault, 1 fault-affected,
  // 2 storage-out, 3 new, 4 on-path. task_class remains the M6 priority rank.
  int task_class_code = 4;
  int task_class = 0;
  bool storage_leg = false;
  double source_release_age = 0.0;
  double local_queue_age = 0.0;
  int advertised_fault_generation = 0;
  int physical_fault_generation = 0;
  std::uint64_t destination_calendar_generation = 0;
  std::uint64_t enqueue_sequence = 0;
  double expiry = 0.0;
  // Allocated once, before any grant/calendar point of no return. Lifecycle
  // rows share this immutable identity so terminal transitions can retain the
  // exact segment without allocating in their noexcept publication tail.
  std::shared_ptr<const std::string> lifecycle_segment_id;
  // The controller retains this immutable, preallocated request identity
  // alongside every active grant. It is intentionally created before the
  // calendar/grant point of no return so a missing or corrupted move-only
  // capability can still be revoked and audited without allocation.
  std::shared_ptr<const DestinationMergeRequest>
      lifecycle_request_snapshot;
};

static_assert(
    std::is_nothrow_move_constructible_v<
        DestinationMergeRequest>);

// Stored on the in-transit bag independently of the move-only capability.
// This makes "a grant was required for this exact transit" explicit, so a
// missing capability cannot silently turn an E4 merge into an ordinary edge
// exit. Goal exemptions and non-merge edges keep required=false.
struct DestinationMergeGrantExpectation {
  bool required = false;
  std::uint64_t grant_id = 0;
  std::uint64_t request_id = 0;
  std::uint64_t lineage = 0;
  std::uint64_t request_generation = 0;
  std::uint64_t junction_queue_generation = 0;
  int owner_runtime_bag_id = -1;
  MergeDirectedEdge edge;
  int destination_node = -1;
  double slot_start = 0.0;
  double slot_end = 0.0;
  double expiry = 0.0;
  std::uint64_t calendar_generation = 0;
  int physical_fault_generation = 0;
  int advertised_fault_generation = 0;
};

inline bool operator==(
    const DestinationMergeGrantExpectation& left,
    const DestinationMergeGrantExpectation& right) noexcept {
  return left.required == right.required &&
         left.grant_id == right.grant_id &&
         left.request_id == right.request_id &&
         left.lineage == right.lineage &&
         left.request_generation == right.request_generation &&
         left.junction_queue_generation ==
             right.junction_queue_generation &&
         left.owner_runtime_bag_id ==
             right.owner_runtime_bag_id &&
         left.edge == right.edge &&
         left.destination_node == right.destination_node &&
         left.slot_start == right.slot_start &&
         left.slot_end == right.slot_end &&
         left.expiry == right.expiry &&
         left.calendar_generation == right.calendar_generation &&
         left.physical_fault_generation ==
             right.physical_fault_generation &&
         left.advertised_fault_generation ==
             right.advertised_fault_generation;
}

inline bool operator!=(
    const DestinationMergeGrantExpectation& left,
    const DestinationMergeGrantExpectation& right) noexcept {
  return !(left == right);
}

struct DestinationMergeGrantConsumeContext {
  DestinationMergeGrantExpectation expected;
  int event_owner_runtime_bag_id = -1;
  MergeDirectedEdge event_edge;
  int event_destination_node = -1;
  double now = 0.0;
  std::uint64_t current_junction_queue_generation = 0;
  std::uint64_t current_calendar_generation = 0;
  bool physical_fault_active = false;
  int current_physical_fault_generation = 0;
  int current_advertised_fault_generation = 0;
  bool exact_destination_calendar_reservation_present = false;
  // This proof is minted only by the EDGE_ENTER handler after it observes the
  // exact committed capability at the same physical/advertised generations
  // and an inactive physical edge.  A synthetic generation mutation at exit
  // cannot create either proof bit.
  bool exact_grant_edge_entry_observed = false;
  bool local_inflight_fault_instance_observed = false;
};

struct DestinationMergeGrantObservedState {
  std::uint64_t claimed_request_generation = 0;
  std::uint64_t claimed_junction_queue_generation = 0;
  std::uint64_t claimed_calendar_generation = 0;
  int claimed_owner_runtime_bag_id = -1;
  MergeDirectedEdge claimed_edge;
  int claimed_destination_node = -1;
  int event_owner_runtime_bag_id = -1;
  MergeDirectedEdge event_edge;
  int event_destination_node = -1;
  std::uint64_t junction_queue_generation = 0;
  std::uint64_t calendar_generation = 0;
  int physical_fault_generation = 0;
  int advertised_fault_generation = 0;
  bool physical_fault_active = false;
  bool exact_calendar_reservation_present = false;
};

enum class DestinationMergeGrantConsumeResult {
  kConsumed,
  kConsumedAfterInflightFaultGenerationChange,
  kActiveGrantMissing,
  kCapabilityMissing,
  kIdentityMismatch,
  kOwnerMismatch,
  kEdgeMismatch,
  kDestinationMismatch,
  kExpired,
  kFaultGenerationChanged,
  kCalendarReservationMissing,
};

enum class DestinationMergeGrantRule {
  kM0EarliestKnown,
  kM1Fifo,
  kM2EarliestProjectedArrival,
  kM3DeadlineAging,
  kM4FairnessProgress,
  kM5LocalExternality,
  kM6ThesisLocal,
};

// G18 separates *when* a destination merge arbitrates from the local rule
// used to rank a ready set.  Eager is the exact G17/E4 compatibility path.
// The two JIT modes retain requests in the bounded destination-owned pending
// set until a real one-hop service opportunity exists.
enum class DestinationMergeGrantTimingMode {
  kEager,
  kJitFifo,
  kJitFairAgingDeadline,
};

inline const char* destination_merge_grant_timing_mode_name(
    DestinationMergeGrantTimingMode mode) noexcept {
  switch (mode) {
    case DestinationMergeGrantTimingMode::kEager:
      return "eager";
    case DestinationMergeGrantTimingMode::kJitFifo:
      return "jit_fifo";
    case DestinationMergeGrantTimingMode::kJitFairAgingDeadline:
      return "jit_fair_aging_deadline";
  }
  return "eager";
}

inline DestinationMergeGrantRule destination_merge_grant_rule_for_timing(
    DestinationMergeGrantTimingMode mode,
    DestinationMergeGrantRule eager_rule) noexcept {
  switch (mode) {
    case DestinationMergeGrantTimingMode::kEager:
      return eager_rule;
    case DestinationMergeGrantTimingMode::kJitFifo:
      return DestinationMergeGrantRule::kM1Fifo;
    case DestinationMergeGrantTimingMode::kJitFairAgingDeadline:
      return DestinationMergeGrantRule::kM3DeadlineAging;
  }
  return eager_rule;
}

inline const char* destination_merge_grant_rule_name(
    DestinationMergeGrantRule rule) noexcept {
  switch (rule) {
    case DestinationMergeGrantRule::kM0EarliestKnown:
      return "M0";
    case DestinationMergeGrantRule::kM1Fifo:
      return "M1";
    case DestinationMergeGrantRule::kM2EarliestProjectedArrival:
      return "M2";
    case DestinationMergeGrantRule::kM3DeadlineAging:
      return "M3";
    case DestinationMergeGrantRule::kM4FairnessProgress:
      return "M4";
    case DestinationMergeGrantRule::kM5LocalExternality:
      return "M5";
    case DestinationMergeGrantRule::kM6ThesisLocal:
      return "M6";
  }
  return "M1";
}

inline double destination_merge_request_age(
    const DestinationMergeRequest& request,
    double now) noexcept {
  return std::max(
      request.wait_age,
      std::max(0.0, now - request.fifo_request_time));
}

inline bool destination_merge_unique_tie_less(
    const DestinationMergeRequest& left,
    const DestinationMergeRequest& right) noexcept {
  return std::tie(left.task_id,
                  left.runtime_bag_id,
                  left.upstream_node,
                  left.request_id) <
         std::tie(right.task_id,
                  right.runtime_bag_id,
                  right.upstream_node,
                  right.request_id);
}

// This comparator uses only fields captured at the current one-hop request
// boundary. The starvation band is common to every rule so an otherwise
// lower-ranked request eventually reaches the front without weakening any
// safety or capacity check.
inline bool destination_merge_request_less(
    DestinationMergeGrantRule rule,
    const DestinationMergeRequest& left,
    const DestinationMergeRequest& right,
    double now,
    double starvation_threshold) noexcept {
  const double left_age =
      destination_merge_request_age(left, now);
  const double right_age =
      destination_merge_request_age(right, now);
  if (std::isfinite(starvation_threshold) &&
      starvation_threshold >= 0.0) {
    const bool left_starving =
        left_age + 1.0e-9 >= starvation_threshold;
    const bool right_starving =
        right_age + 1.0e-9 >= starvation_threshold;
    if (left_starving != right_starving) {
      return left_starving;
    }
    if (left_starving &&
        std::abs(left_age - right_age) > 1.0e-9) {
      return left_age > right_age;
    }
  }

  switch (rule) {
    case DestinationMergeGrantRule::kM0EarliestKnown:
      if (left.enqueue_sequence != right.enqueue_sequence) {
        return left.enqueue_sequence < right.enqueue_sequence;
      }
      break;
    case DestinationMergeGrantRule::kM1Fifo:
      if (std::abs(left.fifo_request_time -
                   right.fifo_request_time) > 1.0e-9) {
        return left.fifo_request_time <
               right.fifo_request_time;
      }
      break;
    case DestinationMergeGrantRule::kM2EarliestProjectedArrival:
      if (std::abs(left.projected_arrival -
                   right.projected_arrival) > 1.0e-9) {
        return left.projected_arrival <
               right.projected_arrival;
      }
      break;
    case DestinationMergeGrantRule::kM3DeadlineAging: {
      const double left_key =
          left.deadline_slack - left_age;
      const double right_key =
          right.deadline_slack - right_age;
      if (std::abs(left_key - right_key) > 1.0e-9) {
        return left_key < right_key;
      }
      break;
    }
    case DestinationMergeGrantRule::kM4FairnessProgress:
      if (std::abs(left_age - right_age) > 1.0e-9) {
        return left_age > right_age;
      }
      if (std::abs(left.static_remaining -
                   right.static_remaining) > 1.0e-9) {
        return left.static_remaining <
               right.static_remaining;
      }
      if (std::abs(left.route_score -
                   right.route_score) > 1.0e-9) {
        return left.route_score < right.route_score;
      }
      break;
    case DestinationMergeGrantRule::kM5LocalExternality: {
      const double left_key =
          left.projected_arrival +
          left.destination_service_seconds *
              (1.0 +
               std::max(0, left.downstream_queue_pressure)) +
          std::max(0.0, left.route_score);
      const double right_key =
          right.projected_arrival +
          right.destination_service_seconds *
              (1.0 +
               std::max(0, right.downstream_queue_pressure)) +
          std::max(0.0, right.route_score);
      if (std::abs(left_key - right_key) > 1.0e-9) {
        return left_key < right_key;
      }
      if (std::abs(left_age - right_age) > 1.0e-9) {
        return left_age > right_age;
      }
      break;
    }
    case DestinationMergeGrantRule::kM6ThesisLocal:
      if (left.task_class != right.task_class) {
        return left.task_class < right.task_class;
      }
      if (std::abs(left.deadline_slack -
                   right.deadline_slack) > 1.0e-9) {
        return left.deadline_slack <
               right.deadline_slack;
      }
      if (std::abs(left_age - right_age) > 1.0e-9) {
        return left_age > right_age;
      }
      if (left.storage_leg != right.storage_leg) {
        return !left.storage_leg;
      }
      break;
  }
  return destination_merge_unique_tie_less(left, right);
}

// A grant is a runtime-owned capability, not a public mutable record. It is
// move-only, cannot be default-constructed, and can only be minted by the
// destination controller on behalf of EventDrivenJunctionRuntime.
class MergeGrantCapability {
 public:
  MergeGrantCapability(const MergeGrantCapability&) = delete;
  MergeGrantCapability& operator=(const MergeGrantCapability&) = delete;
  MergeGrantCapability(MergeGrantCapability&& other) noexcept {
    move_from(other);
  }
  MergeGrantCapability& operator=(MergeGrantCapability&& other) noexcept {
    if (this != &other) {
      move_from(other);
    }
    return *this;
  }

  [[nodiscard]] std::uint64_t grant_id() const noexcept {
    return grant_id_;
  }
  [[nodiscard]] std::uint64_t request_id() const noexcept {
    return request_id_;
  }
  [[nodiscard]] std::uint64_t lineage() const noexcept {
    return lineage_;
  }
  [[nodiscard]] std::uint64_t request_generation() const noexcept {
    return request_generation_;
  }
  [[nodiscard]] int owner_runtime_bag_id() const noexcept {
    return owner_runtime_bag_id_;
  }
  [[nodiscard]] MergeDirectedEdge exact_directed_edge() const noexcept {
    return exact_directed_edge_;
  }
  [[nodiscard]] int destination_node() const noexcept {
    return destination_node_;
  }
  [[nodiscard]] double slot_start() const noexcept {
    return slot_start_;
  }
  [[nodiscard]] double slot_end() const noexcept {
    return slot_end_;
  }
  [[nodiscard]] double issue_time() const noexcept {
    return issue_time_;
  }
  [[nodiscard]] double request_time() const noexcept {
    return request_time_;
  }
  [[nodiscard]] double expiry() const noexcept {
    return expiry_;
  }
  [[nodiscard]] std::uint64_t calendar_generation() const noexcept {
    return calendar_generation_;
  }
  [[nodiscard]] int fault_generation() const noexcept {
    return fault_generation_;
  }
  [[nodiscard]] int advertised_fault_generation() const noexcept {
    return advertised_fault_generation_;
  }
  [[nodiscard]] MergeGrantState state() const noexcept {
    return state_;
  }
  [[nodiscard]] const DestinationMergeRequest&
  request_snapshot() const noexcept {
    return request_snapshot_;
  }
  [[nodiscard]] DestinationMergeGrantExpectation
  expectation() const noexcept {
    DestinationMergeGrantExpectation expected;
    expected.required = true;
    expected.grant_id = grant_id_;
    expected.request_id = request_id_;
    expected.lineage = lineage_;
    expected.request_generation = request_generation_;
    expected.junction_queue_generation =
        request_snapshot_.junction_queue_generation;
    expected.owner_runtime_bag_id = owner_runtime_bag_id_;
    expected.edge = exact_directed_edge_;
    expected.destination_node = destination_node_;
    expected.slot_start = slot_start_;
    expected.slot_end = slot_end_;
    expected.expiry = expiry_;
    expected.calendar_generation = calendar_generation_;
    expected.physical_fault_generation = fault_generation_;
    expected.advertised_fault_generation =
        advertised_fault_generation_;
    return expected;
  }

 private:
  friend class DestinationMergeGrantController;
  friend class DestinationMergeGrantCheckpointCodec;
  friend class EventDrivenJunctionRuntime;

  MergeGrantCapability(std::uint64_t grant_id,
                       DestinationMergeRequest request,
                       double slot_start,
                       double slot_end,
                       double issue_time,
                       std::uint64_t calendar_generation,
                       int fault_generation) noexcept
      : grant_id_(grant_id),
        request_id_(request.request_id),
        lineage_(request.lineage),
        request_generation_(request.request_generation),
        owner_runtime_bag_id_(request.runtime_bag_id),
        exact_directed_edge_(request.requested_directed_edge),
        destination_node_(request.destination_merge_node),
        slot_start_(slot_start),
        slot_end_(slot_end),
        issue_time_(issue_time),
        request_time_(request.request_time),
        expiry_(slot_end),
        calendar_generation_(calendar_generation),
        fault_generation_(fault_generation),
        advertised_fault_generation_(
            request.advertised_fault_generation),
        state_(MergeGrantState::kCommitted),
        request_snapshot_(std::move(request)) {}

  void move_from(MergeGrantCapability& other) noexcept {
    grant_id_ = other.grant_id_;
    request_id_ = other.request_id_;
    lineage_ = other.lineage_;
    request_generation_ = other.request_generation_;
    owner_runtime_bag_id_ = other.owner_runtime_bag_id_;
    exact_directed_edge_ = other.exact_directed_edge_;
    destination_node_ = other.destination_node_;
    slot_start_ = other.slot_start_;
    slot_end_ = other.slot_end_;
    issue_time_ = other.issue_time_;
    request_time_ = other.request_time_;
    expiry_ = other.expiry_;
    calendar_generation_ = other.calendar_generation_;
    fault_generation_ = other.fault_generation_;
    advertised_fault_generation_ =
        other.advertised_fault_generation_;
    state_ = other.state_;
    request_snapshot_ = std::move(other.request_snapshot_);
    other.grant_id_ = 0;
    other.request_id_ = 0;
    other.lineage_ = 0;
    other.request_generation_ = 0;
    other.owner_runtime_bag_id_ = -1;
    other.exact_directed_edge_ = {};
    other.destination_node_ = -1;
    other.slot_start_ = 0.0;
    other.slot_end_ = 0.0;
    other.issue_time_ = 0.0;
    other.request_time_ = 0.0;
    other.expiry_ = 0.0;
    other.calendar_generation_ = 0;
    other.fault_generation_ = 0;
    other.advertised_fault_generation_ = 0;
    other.state_ = MergeGrantState::kRolledBack;
    other.request_snapshot_ = {};
  }

  std::uint64_t grant_id_ = 0;
  std::uint64_t request_id_ = 0;
  std::uint64_t lineage_ = 0;
  std::uint64_t request_generation_ = 0;
  int owner_runtime_bag_id_ = -1;
  MergeDirectedEdge exact_directed_edge_;
  int destination_node_ = -1;
  double slot_start_ = 0.0;
  double slot_end_ = 0.0;
  double issue_time_ = 0.0;
  double request_time_ = 0.0;
  double expiry_ = 0.0;
  std::uint64_t calendar_generation_ = 0;
  int fault_generation_ = 0;
  int advertised_fault_generation_ = 0;
  MergeGrantState state_ = MergeGrantState::kCommitted;
  DestinationMergeRequest request_snapshot_;
};

static_assert(!std::is_default_constructible_v<MergeGrantCapability>);
static_assert(!std::is_copy_constructible_v<MergeGrantCapability>);
static_assert(!std::is_copy_assignable_v<MergeGrantCapability>);
static_assert(std::is_nothrow_move_constructible_v<MergeGrantCapability>);
static_assert(std::is_nothrow_move_assignable_v<MergeGrantCapability>);

struct DestinationMergeGrantLifecycleRow {
  double time = 0.0;
  std::uint64_t request_id = 0;
  std::uint64_t grant_id = 0;
  std::uint64_t lineage = 0;
  std::uint64_t request_generation = 0;
  std::uint64_t junction_queue_generation = 0;
  int runtime_bag_id = -1;
  int task_id = -1;
  std::shared_ptr<const std::string> segment_id;
  int upstream_node = -1;
  int destination_node = -1;
  MergeDirectedEdge edge;
  double request_time = 0.0;
  double fifo_request_time = 0.0;
  double earliest_edge_entry = 0.0;
  double exact_edge_travel_seconds = 0.0;
  double projected_arrival = 0.0;
  int goal = -1;
  double route_score = 0.0;
  double static_remaining = 0.0;
  double destination_service_seconds = 0.0;
  int downstream_queue_pressure = 0;
  double deadline_slack = 0.0;
  double wait_age = 0.0;
  int task_class_code = 4;
  int task_class = 0;
  bool storage_leg = false;
  double source_release_age = 0.0;
  double local_queue_age = 0.0;
  std::uint64_t enqueue_sequence = 0;
  double request_expiry = 0.0;
  double slot_start = 0.0;
  double slot_end = 0.0;
  double issue_time = 0.0;
  double grant_expiry = 0.0;
  std::uint64_t calendar_generation = 0;
  int fault_generation = 0;
  int advertised_fault_generation = 0;
  std::uint64_t observed_claimed_request_generation = 0;
  std::uint64_t observed_claimed_junction_queue_generation = 0;
  std::uint64_t observed_claimed_calendar_generation = 0;
  int observed_claimed_owner_runtime_bag_id = -1;
  MergeDirectedEdge observed_claimed_edge;
  int observed_claimed_destination_node = -1;
  int observed_event_owner_runtime_bag_id = -1;
  MergeDirectedEdge observed_event_edge;
  int observed_event_destination_node = -1;
  std::uint64_t observed_junction_queue_generation = 0;
  std::uint64_t observed_calendar_generation = 0;
  int observed_physical_fault_generation = 0;
  int observed_advertised_fault_generation = 0;
  bool observed_physical_fault_active = false;
  bool observed_exact_calendar_reservation_present = false;
  MergeGrantState state = MergeGrantState::kRequested;
  MergeGrantReason reason = MergeGrantReason::kSubmitted;
};

static_assert(
    std::is_nothrow_move_constructible_v<
        DestinationMergeGrantLifecycleRow>);
static_assert(
    std::is_nothrow_move_assignable_v<
        DestinationMergeGrantLifecycleRow>);

struct DestinationMergeGrantCounters {
  std::uint64_t request_count = 0;
  std::uint64_t issued_count = 0;
  std::uint64_t prepared_count = 0;
  std::uint64_t committed_count = 0;
  std::uint64_t issued_transition_count = 0;
  std::uint64_t prepared_transition_count = 0;
  std::uint64_t committed_transition_count = 0;
  std::uint64_t consumed_count = 0;
  // A strict subset of consumed_count.  The stale generation capability is
  // terminalized, while its exact owner/slot service lease remains in place
  // for a bag that was already physically in flight.
  std::uint64_t inflight_fault_generation_recovery_count = 0;
  std::uint64_t expired_count = 0;
  std::uint64_t request_expired_count = 0;
  std::uint64_t grant_expired_count = 0;
  std::uint64_t revoked_count = 0;
  std::uint64_t revoked_fault_count = 0;
  std::uint64_t revoked_stale_state_count = 0;
  std::uint64_t revoked_replan_current_edge_count = 0;
  std::uint64_t rolled_back_count = 0;
  std::uint64_t post_commit_revoked_count = 0;
  std::uint64_t post_commit_expired_count = 0;
  std::uint64_t post_commit_rollback_count = 0;
  std::uint64_t exact_slot_busy_count = 0;
  std::uint64_t active_grant_rejection_count = 0;
  std::uint64_t queue_capacity_block_count = 0;
  std::uint64_t contended_loser_retry_count = 0;
  std::uint64_t lifecycle_transition_count = 0;
  std::uint64_t lifecycle_stored_count = 0;
  std::uint64_t lifecycle_dropped_count = 0;
  std::size_t peak_pending_count = 0;
  std::size_t peak_active_unconsumed_count = 0;
};

// Offline-only value records for exact state-clone checkpoints.  They do not
// make the live grant capability or destination controller copyable.  Only
// DestinationMergeGrantCheckpointCodec can mint a live capability/controller
// from these records, and restore validates the active-controller bijection
// before the runtime is allowed to process another event.
struct MergeGrantCapabilityCheckpoint {
  std::uint64_t grant_id = 0;
  std::uint64_t request_id = 0;
  std::uint64_t lineage = 0;
  std::uint64_t request_generation = 0;
  int owner_runtime_bag_id = -1;
  MergeDirectedEdge exact_directed_edge;
  int destination_node = -1;
  double slot_start = 0.0;
  double slot_end = 0.0;
  double issue_time = 0.0;
  double request_time = 0.0;
  double expiry = 0.0;
  std::uint64_t calendar_generation = 0;
  int fault_generation = 0;
  int advertised_fault_generation = 0;
  MergeGrantState state = MergeGrantState::kCommitted;
  DestinationMergeRequest request_snapshot;
};

struct DestinationMergeActiveGrantCheckpoint {
  std::uint64_t grant_id = 0;
  std::uint64_t request_id = 0;
  std::uint64_t lineage = 0;
  std::uint64_t request_generation = 0;
  std::uint64_t junction_queue_generation = 0;
  int owner_runtime_bag_id = -1;
  MergeDirectedEdge edge;
  double slot_start = 0.0;
  double slot_end = 0.0;
  double issue_time = 0.0;
  double grant_expiry = 0.0;
  std::uint64_t calendar_generation = 0;
  int physical_fault_generation = 0;
  int advertised_fault_generation = 0;
  DestinationMergeRequest request_snapshot;
};

struct DestinationMergeGrantControllerCheckpoint {
  int destination_node = -1;
  std::size_t max_pending_requests = 0;
  std::size_t lifecycle_limit = 0;
  std::vector<DestinationMergeRequest> pending;
  std::vector<DestinationMergeActiveGrantCheckpoint> active;
  std::vector<DestinationMergeGrantLifecycleRow> lifecycle;
  DestinationMergeGrantCounters counters;
  std::uint64_t next_request_id = 1;
  std::uint64_t next_grant_id = 1;
  std::uint64_t generation = 0;
};

class DestinationMergeGrantCheckpointCodec {
 public:
  [[nodiscard]] static MergeGrantCapabilityCheckpoint capture(
      const MergeGrantCapability& capability);
  [[nodiscard]] static MergeGrantCapability restore(
      const MergeGrantCapabilityCheckpoint& checkpoint);
  [[nodiscard]] static DestinationMergeGrantControllerCheckpoint capture(
      const DestinationMergeGrantController& controller);
  [[nodiscard]] static DestinationMergeGrantController restore(
      const DestinationMergeGrantControllerCheckpoint& checkpoint);

 private:
  [[nodiscard]] static DestinationMergeRequest clone_request(
      const DestinationMergeRequest& request);
  [[nodiscard]] static DestinationMergeGrantLifecycleRow clone_lifecycle(
      const DestinationMergeGrantLifecycleRow& row);
};

class DestinationMergeGrantController {
 public:
  explicit DestinationMergeGrantController(
      int destination_node,
      std::size_t max_pending_requests = 64,
      std::size_t lifecycle_limit = 1024)
      : destination_node_(destination_node),
        max_pending_requests_(max_pending_requests),
        lifecycle_limit_(lifecycle_limit) {
    if (destination_node < 0 || max_pending_requests == 0) {
      throw std::invalid_argument(
          "destination merge controller requires a node and bounded queue");
    }
    // Every terminal transition is published from a noexcept commit/exit
    // tail. Reserve the configured hard bound up front; a later consumed,
    // expired, or revoked row must never be the allocation that terminates
    // the process after physical/calendar state already changed.
    lifecycle_.reserve(lifecycle_limit_);
    assert(lifecycle_.capacity() >= lifecycle_limit_);
    pending_.reserve(max_pending_requests_);
    active_.reserve(max_pending_requests_);
  }
  DestinationMergeGrantController(
      const DestinationMergeGrantController&) = delete;
  DestinationMergeGrantController& operator=(
      const DestinationMergeGrantController&) = delete;
  DestinationMergeGrantController(
      DestinationMergeGrantController&&) noexcept = default;
  DestinationMergeGrantController& operator=(
      DestinationMergeGrantController&&) noexcept = default;

  [[nodiscard]] int destination_node() const noexcept {
    return destination_node_;
  }
  [[nodiscard]] std::size_t pending_count() const noexcept {
    return pending_.size();
  }
  [[nodiscard]] bool has_active_unconsumed_grant() const noexcept {
    return !active_.empty();
  }
  [[nodiscard]] std::size_t active_unconsumed_count() const noexcept {
    return active_.size();
  }
  [[nodiscard]] std::uint64_t generation() const noexcept {
    return generation_;
  }
  [[nodiscard]] const DestinationMergeGrantCounters& counters() const noexcept {
    return counters_;
  }
  [[nodiscard]] const std::vector<DestinationMergeGrantLifecycleRow>&
  lifecycle() const noexcept {
    return lifecycle_;
  }
  [[nodiscard]] double oldest_pending_age(double now) const noexcept {
    double result = 0.0;
    for (const auto& pending : pending_) {
      result = std::max(
          result,
          std::max(0.0, now - pending.request.fifo_request_time));
    }
    return result;
  }
  [[nodiscard]] int recent_incoming_grants(
      double now, double window_seconds = 60.0) const noexcept {
    int result = 0;
    const double lower = now - window_seconds;
    for (auto row = lifecycle_.rbegin(); row != lifecycle_.rend(); ++row) {
      if (row->time < lower) {
        break;
      }
      if (row->state == MergeGrantState::kCommitted) {
        ++result;
      }
    }
    return result;
  }
  [[nodiscard]] int recent_incoming_grant_imbalance(
      double now, double window_seconds = 60.0) const {
    std::vector<std::pair<int, int>> by_upstream;
    const double lower = now - window_seconds;
    for (auto row = lifecycle_.rbegin(); row != lifecycle_.rend(); ++row) {
      if (row->time < lower) {
        break;
      }
      if (row->state != MergeGrantState::kCommitted) {
        continue;
      }
      auto found = std::find_if(
          by_upstream.begin(), by_upstream.end(), [&](const auto& item) {
            return item.first == row->upstream_node;
          });
      if (found == by_upstream.end()) {
        by_upstream.emplace_back(row->upstream_node, 1);
      } else {
        ++found->second;
      }
    }
    if (by_upstream.size() < 2U) {
      return 0;
    }
    const auto bounds = std::minmax_element(
        by_upstream.begin(), by_upstream.end(), [](const auto& left,
                                                   const auto& right) {
          return left.second < right.second;
        });
    return bounds.second->second - bounds.first->second;
  }
  [[nodiscard]] bool conservation_holds() const noexcept {
    return counters_.request_count ==
               counters_.committed_count +
                   counters_.expired_count +
                   counters_.revoked_count +
                   counters_.rolled_back_count +
                   pending_.size() &&
           counters_.committed_count ==
               counters_.consumed_count +
                   active_.size() &&
           counters_.inflight_fault_generation_recovery_count <=
               counters_.consumed_count &&
           counters_.lifecycle_transition_count ==
               counters_.lifecycle_stored_count +
                   counters_.lifecycle_dropped_count;
  }

#ifdef CZR005_EVENT_RUNTIME_TESTING
  [[nodiscard]] MergeGrantCapability test_issue_capability(
      DestinationMergeRequest request,
      double slot_start,
      double slot_end,
      std::uint64_t calendar_generation,
      int physical_fault_generation) {
    reserve_lifecycle_for_transaction(4);
    const auto submitted = submit(std::move(request));
    if (!submitted.accepted) {
      throw std::logic_error(
          "test capability request was rejected");
    }
    return commit_selected_noexcept(
        submitted.request_id,
        slot_start,
        slot_end,
        slot_start,
        calendar_generation,
        physical_fault_generation);
  }

  [[nodiscard]] bool test_validates_capability_claim(
      const MergeGrantCapability* grant,
      int owner_runtime_bag_id,
      MergeDirectedEdge edge,
      int destination_node,
      std::uint64_t request_generation,
      std::uint64_t calendar_generation,
      int physical_fault_generation) const noexcept {
    return grant != nullptr &&
           validates_active_capability(*grant) &&
           grant->owner_runtime_bag_id() ==
               owner_runtime_bag_id &&
           grant->exact_directed_edge() == edge &&
           grant->destination_node() == destination_node &&
           grant->request_generation() ==
               request_generation &&
           grant->calendar_generation() ==
               calendar_generation &&
           grant->fault_generation() ==
               physical_fault_generation;
  }

  bool test_consume_capability(
      MergeGrantCapability& grant,
      double now) noexcept {
    DestinationMergeGrantConsumeContext context;
    context.expected = grant.expectation();
    context.event_owner_runtime_bag_id =
        grant.owner_runtime_bag_id();
    context.event_edge = grant.exact_directed_edge();
    context.event_destination_node =
        grant.destination_node();
    context.now = now;
    context.current_junction_queue_generation =
        grant.request_snapshot()
            .junction_queue_generation;
    context.current_calendar_generation =
        grant.calendar_generation();
    context.current_physical_fault_generation =
        grant.fault_generation();
    context.current_advertised_fault_generation =
        grant.advertised_fault_generation();
    context.exact_destination_calendar_reservation_present =
        true;
    return consume_noexcept(&grant, context) ==
           DestinationMergeGrantConsumeResult::kConsumed;
  }
#endif

 private:
  friend class DestinationMergeGrantCheckpointCodec;
  friend class EventDrivenJunctionRuntime;

  struct SubmitResult {
    bool accepted = false;
    std::uint64_t request_id = 0;
  };

  struct PendingRecord {
    DestinationMergeRequest request;
  };

  struct ActiveGrantRecord {
    std::uint64_t grant_id = 0;
    std::uint64_t request_id = 0;
    std::uint64_t lineage = 0;
    std::uint64_t request_generation = 0;
    std::uint64_t junction_queue_generation = 0;
    int owner_runtime_bag_id = -1;
    MergeDirectedEdge edge;
    double slot_start = 0.0;
    double slot_end = 0.0;
    double issue_time = 0.0;
    double grant_expiry = 0.0;
    std::uint64_t calendar_generation = 0;
    int physical_fault_generation = 0;
    int advertised_fault_generation = 0;
    std::shared_ptr<const DestinationMergeRequest>
        request_snapshot;
  };

  static_assert(
      std::is_nothrow_move_constructible_v<
          ActiveGrantRecord>);
  static_assert(
      std::is_nothrow_move_assignable_v<
          ActiveGrantRecord>);

  SubmitResult submit(
      DestinationMergeRequest request) {
    if (request.destination_merge_node != destination_node_ ||
        request.requested_directed_edge.to_node != destination_node_ ||
        request.requested_directed_edge.from_node != request.upstream_node ||
        request.runtime_bag_id < 0 || request.lineage == 0 ||
        request.request_generation == 0 ||
        request.junction_queue_generation == 0 ||
        !std::isfinite(request.request_time) ||
        !std::isfinite(request.fifo_request_time) ||
        request.fifo_request_time >
            request.request_time + 1.0e-9 ||
        !std::isfinite(request.exact_edge_travel_seconds) ||
        request.exact_edge_travel_seconds <= 0.0 ||
        !std::isfinite(request.projected_arrival) ||
        std::abs(request.projected_arrival -
                 (request.request_time +
                  request.exact_edge_travel_seconds)) >
            1.0e-9 ||
        !std::isfinite(request.expiry) ||
        request.expiry < request.request_time ||
        pending_.size() >= max_pending_requests_) {
      return {};
    }
    if (!request.lifecycle_segment_id) {
      request.lifecycle_segment_id =
          std::make_shared<const std::string>(
              request.segment_id);
    }
    if (request.request_id == 0) {
      request.request_id = next_request_id_++;
    } else {
      next_request_id_ =
          std::max(next_request_id_,
                   request.request_id + 1);
    }
    // Copy while lifecycle_request_snapshot is still empty, avoiding a
    // self-referential ownership cycle.
    request.lifecycle_request_snapshot =
        std::make_shared<const DestinationMergeRequest>(
            request);
    pending_.push_back(PendingRecord{std::move(request)});
    ++generation_;
    ++counters_.request_count;
    counters_.peak_pending_count =
        std::max(counters_.peak_pending_count, pending_.size());
    append_lifecycle_noexcept(
        pending_.back().request,
        0,
        MergeGrantState::kRequested,
        MergeGrantReason::kSubmitted,
        pending_.back().request.request_time,
        0.0,
        0.0,
        0,
        pending_.back().request.physical_fault_generation);
    return {true, pending_.back().request.request_id};
  }

  [[nodiscard]] PendingRecord* select(
      DestinationMergeGrantRule rule,
      double now,
      double starvation_threshold) noexcept {
    PendingRecord* best = nullptr;
    for (auto& record : pending_) {
      if (record.request.expiry + 1.0e-9 < now) {
        continue;
      }
      if (best == nullptr ||
          destination_merge_request_less(
              rule,
              record.request,
              best->request,
              now,
              starvation_threshold)) {
        best = &record;
      }
    }
    return best;
  }

  [[nodiscard]] PendingRecord* select_fifo(double now) noexcept {
    return select(DestinationMergeGrantRule::kM1Fifo,
                  now,
                  std::numeric_limits<double>::infinity());
  }

  [[nodiscard]] bool active_capacity_available() const noexcept {
    return active_.size() < max_pending_requests_;
  }

  [[nodiscard]] bool has_overlapping_active_slot(
      double slot_start,
      double slot_end) const noexcept {
    return std::any_of(
        active_.begin(),
        active_.end(),
        [&](const ActiveGrantRecord& active) {
          return slot_start <
                     active.slot_end - 1.0e-9 &&
                 active.slot_start <
                     slot_end - 1.0e-9;
        });
  }

  [[nodiscard]] bool validates_active_capability(
      const MergeGrantCapability& grant) const noexcept {
    if (grant.state_ != MergeGrantState::kCommitted ||
        grant.destination_node_ != destination_node_) {
      return false;
    }
    const auto active = std::find_if(
        active_.begin(),
        active_.end(),
        [&](const ActiveGrantRecord& record) {
          return record.grant_id == grant.grant_id_;
        });
    return active != active_.end() &&
           active->request_id == grant.request_id_ &&
           active->lineage == grant.lineage_ &&
           active->request_generation ==
               grant.request_generation_ &&
           active->junction_queue_generation ==
               grant.request_snapshot_
                   .junction_queue_generation &&
           active->owner_runtime_bag_id ==
               grant.owner_runtime_bag_id_ &&
           active->edge == grant.exact_directed_edge_ &&
           std::abs(active->slot_start - grant.slot_start_) <=
               1.0e-9 &&
           std::abs(active->slot_end - grant.slot_end_) <=
               1.0e-9 &&
           std::abs(active->issue_time -
                    grant.issue_time_) <= 1.0e-9 &&
           std::abs(active->grant_expiry -
                    grant.expiry_) <= 1.0e-9 &&
           active->calendar_generation ==
               grant.calendar_generation_ &&
           active->physical_fault_generation ==
               grant.fault_generation_ &&
           active->advertised_fault_generation ==
               grant.advertised_fault_generation_;
  }

  [[nodiscard]] const std::vector<PendingRecord>& pending() const noexcept {
    return pending_;
  }

  void reserve_lifecycle_for_transaction(std::size_t additional) {
    const std::size_t bounded_target =
        std::min(lifecycle_limit_, lifecycle_.size() + additional);
    if (bounded_target > lifecycle_.capacity()) {
      lifecycle_.reserve(bounded_target);
    }
  }

  [[nodiscard]] std::size_t
  dynamic_storage_accounted_bytes() const noexcept {
    std::size_t accounted =
        pending_.capacity() * sizeof(PendingRecord) +
        active_.capacity() * sizeof(ActiveGrantRecord) +
        lifecycle_.capacity() *
            sizeof(DestinationMergeGrantLifecycleRow);
    for (const auto& record : pending_) {
      accounted +=
          record.request.segment_id.capacity();
    }
    return accounted;
  }

  [[nodiscard]] MergeGrantCapability commit_selected_noexcept(
      std::uint64_t request_id,
      double slot_start,
      double slot_end,
      double issue_time,
      std::uint64_t calendar_generation,
      int fault_generation) noexcept {
    auto found = std::find_if(
        pending_.begin(),
        pending_.end(),
        [&](const PendingRecord& record) {
          return record.request.request_id == request_id;
        });
    DestinationMergeRequest request =
        std::move(found->request);
    const std::uint64_t local_grant_id =
        next_grant_id_++;
    const std::uint64_t grant_id =
        ((static_cast<std::uint64_t>(
              static_cast<std::uint32_t>(
                  destination_node_)) +
          1ULL)
         << 32) |
        local_grant_id;
    append_lifecycle_noexcept(request,
                              grant_id,
                              MergeGrantState::kIssued,
                              MergeGrantReason::kExactSlotCommitted,
                              issue_time,
                              slot_start,
                              slot_end,
                              calendar_generation,
                              fault_generation,
                              issue_time,
                              slot_end);
    append_lifecycle_noexcept(request,
                              grant_id,
                              MergeGrantState::kPrepared,
                              MergeGrantReason::kExactSlotCommitted,
                              issue_time,
                              slot_start,
                              slot_end,
                              calendar_generation,
                              fault_generation,
                              issue_time,
                              slot_end);
    append_lifecycle_noexcept(request,
                              grant_id,
                              MergeGrantState::kCommitted,
                              MergeGrantReason::kExactSlotCommitted,
                              issue_time,
                              slot_start,
                              slot_end,
                              calendar_generation,
                              fault_generation,
                              issue_time,
                              slot_end);
    ++counters_.issued_count;
    ++counters_.prepared_count;
    ++counters_.committed_count;
    ++counters_.issued_transition_count;
    ++counters_.prepared_transition_count;
    ++counters_.committed_transition_count;
    active_.push_back(
        ActiveGrantRecord{
            grant_id,
            request.request_id,
            request.lineage,
            request.request_generation,
            request.junction_queue_generation,
            request.runtime_bag_id,
            request.requested_directed_edge,
            slot_start,
            slot_end,
            issue_time,
            slot_end,
            calendar_generation,
            fault_generation,
            request.advertised_fault_generation,
            request.lifecycle_request_snapshot});
    counters_.peak_active_unconsumed_count =
        std::max<std::size_t>(
            counters_.peak_active_unconsumed_count,
            active_.size());
    pending_.erase(found);
    ++generation_;
    return MergeGrantCapability(grant_id,
                                std::move(request),
                                slot_start,
                                slot_end,
                                issue_time,
                                calendar_generation,
                                fault_generation);
  }

  void reject_noexcept(std::uint64_t request_id,
                       MergeGrantState state,
                       MergeGrantReason reason,
                       double now,
                       const DestinationMergeGrantObservedState*
                           observed = nullptr) noexcept {
    auto found = std::find_if(
        pending_.begin(),
        pending_.end(),
        [&](const PendingRecord& record) {
          return record.request.request_id == request_id;
        });
    if (found == pending_.end()) {
      return;
    }
    append_lifecycle_noexcept(found->request,
                              0,
                              state,
                              reason,
                              now,
                              found->request.projected_arrival,
                              found->request.projected_arrival,
                              0,
                              found->request.physical_fault_generation,
                              0.0,
                              0.0,
                              observed);
    if (state == MergeGrantState::kExpired) {
      ++counters_.expired_count;
      ++counters_.request_expired_count;
    } else if (state == MergeGrantState::kRevokedFault ||
               state == MergeGrantState::kRevokedStaleState ||
               state == MergeGrantState::kRevokedReplanCurrentEdge) {
      ++counters_.revoked_count;
      if (state == MergeGrantState::kRevokedFault) {
        ++counters_.revoked_fault_count;
      } else if (state ==
                 MergeGrantState::kRevokedStaleState) {
        ++counters_.revoked_stale_state_count;
      } else {
        ++counters_
              .revoked_replan_current_edge_count;
      }
    } else {
      ++counters_.rolled_back_count;
    }
    if (reason == MergeGrantReason::kExactSlotBusy) {
      ++counters_.exact_slot_busy_count;
    }
    if (reason == MergeGrantReason::kActiveGrantExists) {
      ++counters_.active_grant_rejection_count;
    }
    if (reason == MergeGrantReason::kQueueCapacityBlock) {
      ++counters_.queue_capacity_block_count;
    }
    if (reason == MergeGrantReason::kContendedLoserRetry) {
      ++counters_.contended_loser_retry_count;
    }
    pending_.erase(found);
    ++generation_;
  }

  DestinationMergeGrantConsumeResult consume_noexcept(
      MergeGrantCapability* grant,
      const DestinationMergeGrantConsumeContext& context) noexcept {
    auto active = std::find_if(
        active_.begin(),
        active_.end(),
        [&](const ActiveGrantRecord& record) {
          return record.grant_id ==
                 context.expected.grant_id;
        });
    if (active == active_.end() && grant != nullptr) {
      active = std::find_if(
          active_.begin(),
          active_.end(),
          [&](const ActiveGrantRecord& record) {
            return record.grant_id == grant->grant_id_;
          });
    }
    if (active == active_.end()) {
      active = std::find_if(
          active_.begin(),
          active_.end(),
          [&](const ActiveGrantRecord& record) {
            return record.request_id ==
                       context.expected.request_id &&
                   record.lineage ==
                       context.expected.lineage &&
                   record.owner_runtime_bag_id ==
                       context.expected
                           .owner_runtime_bag_id &&
                   record.edge == context.expected.edge &&
                   std::abs(
                       record.slot_start -
                       context.expected.slot_start) <=
                       1.0e-9 &&
                   std::abs(
                       record.slot_end -
                       context.expected.slot_end) <=
                       1.0e-9;
          });
    }
    if (active == active_.end()) {
      return DestinationMergeGrantConsumeResult::
          kActiveGrantMissing;
    }
    assert(active->request_snapshot != nullptr);
    DestinationMergeGrantObservedState observed;
    observed.claimed_request_generation =
        context.expected.request_generation;
    observed.claimed_junction_queue_generation =
        context.expected.junction_queue_generation;
    observed.claimed_calendar_generation =
        context.expected.calendar_generation;
    observed.claimed_owner_runtime_bag_id =
        context.expected.owner_runtime_bag_id;
    observed.claimed_edge = context.expected.edge;
    observed.claimed_destination_node =
        context.expected.destination_node;
    observed.event_owner_runtime_bag_id =
        context.event_owner_runtime_bag_id;
    observed.event_edge = context.event_edge;
    observed.event_destination_node =
        context.event_destination_node;
    observed.junction_queue_generation =
        context.current_junction_queue_generation;
    observed.calendar_generation =
        context.current_calendar_generation;
    observed.physical_fault_generation =
        context.current_physical_fault_generation;
    observed.advertised_fault_generation =
        context.current_advertised_fault_generation;
    observed.physical_fault_active =
        context.physical_fault_active;
    observed.exact_calendar_reservation_present =
        context
            .exact_destination_calendar_reservation_present;

    // Queue and calendar generations are aggregate/local epochs. A normal
    // winner dequeue advances the former, while another non-overlapping
    // reservation may advance the latter. They are therefore audit
    // observations at consume time, not stable capability claims. The
    // stable hard gates below are active-record/capability identity plus the
    // exact(owner, slot) lease, actual event identity, expiry, and live fault
    // generations.
    const auto terminalize =
        [&](DestinationMergeGrantConsumeResult result,
            MergeGrantState state,
            MergeGrantReason reason)
            -> DestinationMergeGrantConsumeResult {
      const DestinationMergeRequest& request =
          *active->request_snapshot;
      append_lifecycle_noexcept(
          request,
          active->grant_id,
          state,
          reason,
          context.now,
          active->slot_start,
          active->slot_end,
          active->calendar_generation,
          active->physical_fault_generation,
          active->issue_time,
          active->grant_expiry,
          &observed);
      if (grant != nullptr) {
        grant->state_ = state;
      }
      active_.erase(active);
      --counters_.issued_count;
      --counters_.prepared_count;
      --counters_.committed_count;
      if (state == MergeGrantState::kExpired) {
        ++counters_.expired_count;
        ++counters_.grant_expired_count;
        ++counters_.post_commit_expired_count;
      } else {
        ++counters_.revoked_count;
        ++counters_.post_commit_revoked_count;
        if (state == MergeGrantState::kRevokedFault) {
          ++counters_.revoked_fault_count;
        } else if (state ==
                   MergeGrantState::kRevokedStaleState) {
          ++counters_.revoked_stale_state_count;
        } else if (
            state ==
            MergeGrantState::kRevokedReplanCurrentEdge) {
          ++counters_
                .revoked_replan_current_edge_count;
        }
      }
      ++generation_;
      return result;
    };
    const auto consume =
        [&](DestinationMergeGrantConsumeResult result,
            MergeGrantReason reason,
            bool inflight_fault_recovery)
            -> DestinationMergeGrantConsumeResult {
      append_lifecycle_noexcept(
          *active->request_snapshot,
          active->grant_id,
          MergeGrantState::kConsumed,
          reason,
          context.now,
          active->slot_start,
          active->slot_end,
          active->calendar_generation,
          active->physical_fault_generation,
          active->issue_time,
          active->grant_expiry,
          &observed);
      grant->state_ = MergeGrantState::kConsumed;
      active_.erase(active);
      ++counters_.consumed_count;
      if (inflight_fault_recovery) {
        ++counters_.inflight_fault_generation_recovery_count;
      }
      ++generation_;
      return result;
    };

    if (!context.expected.required) {
      return terminalize(
          DestinationMergeGrantConsumeResult::
              kIdentityMismatch,
          MergeGrantState::kRevokedStaleState,
          MergeGrantReason::kOwnerStateChanged);
    }
    if (grant == nullptr) {
      return terminalize(
          DestinationMergeGrantConsumeResult::
              kCapabilityMissing,
          MergeGrantState::kRevokedStaleState,
          MergeGrantReason::kOwnerStateChanged);
    }
    const bool active_matches_expected =
        active->grant_id ==
            context.expected.grant_id &&
        active->request_id ==
            context.expected.request_id &&
        active->lineage ==
            context.expected.lineage &&
        active->request_generation ==
            context.expected.request_generation &&
        active->junction_queue_generation ==
            context.expected
                .junction_queue_generation &&
        active->owner_runtime_bag_id ==
            context.expected.owner_runtime_bag_id &&
        active->edge == context.expected.edge &&
        std::abs(
            active->slot_start -
            context.expected.slot_start) <= 1.0e-9 &&
        std::abs(
            active->slot_end -
            context.expected.slot_end) <= 1.0e-9 &&
        std::abs(
            active->grant_expiry -
            context.expected.expiry) <= 1.0e-9 &&
        active->calendar_generation ==
            context.expected.calendar_generation &&
        active->physical_fault_generation ==
            context.expected
                .physical_fault_generation &&
        active->advertised_fault_generation ==
            context.expected
                .advertised_fault_generation;
    const bool capability_matches_expected =
        grant->state_ == MergeGrantState::kCommitted &&
        grant->grant_id_ ==
            context.expected.grant_id &&
        grant->request_id_ ==
            context.expected.request_id &&
        grant->lineage_ ==
            context.expected.lineage &&
        grant->request_generation_ ==
            context.expected.request_generation &&
        grant->request_snapshot_
                .junction_queue_generation ==
            context.expected
                .junction_queue_generation &&
        grant->owner_runtime_bag_id_ ==
            context.expected.owner_runtime_bag_id &&
        grant->exact_directed_edge_ ==
            context.expected.edge &&
        grant->destination_node_ ==
            context.expected.destination_node &&
        std::abs(
            grant->slot_start_ -
            context.expected.slot_start) <= 1.0e-9 &&
        std::abs(
            grant->slot_end_ -
            context.expected.slot_end) <= 1.0e-9 &&
        std::abs(
            grant->expiry_ -
            context.expected.expiry) <= 1.0e-9 &&
        grant->calendar_generation_ ==
            context.expected.calendar_generation &&
        grant->fault_generation_ ==
            context.expected
                .physical_fault_generation &&
        grant->advertised_fault_generation_ ==
            context.expected
                .advertised_fault_generation;
    if (!active_matches_expected ||
        !capability_matches_expected ||
        context.expected.destination_node !=
            destination_node_) {
      return terminalize(
          DestinationMergeGrantConsumeResult::
              kIdentityMismatch,
          MergeGrantState::kRevokedStaleState,
          MergeGrantReason::kOwnerStateChanged);
    }
    if (context.event_owner_runtime_bag_id !=
        context.expected.owner_runtime_bag_id) {
      return terminalize(
          DestinationMergeGrantConsumeResult::
              kOwnerMismatch,
          MergeGrantState::kRevokedStaleState,
          MergeGrantReason::kOwnerStateChanged);
    }
    if (context.event_edge != context.expected.edge) {
      return terminalize(
          DestinationMergeGrantConsumeResult::
              kEdgeMismatch,
          MergeGrantState::kRevokedReplanCurrentEdge,
          MergeGrantReason::kCurrentEdgeChanged);
    }
    if (context.event_destination_node !=
        context.expected.destination_node) {
      return terminalize(
          DestinationMergeGrantConsumeResult::
              kDestinationMismatch,
          MergeGrantState::kRevokedReplanCurrentEdge,
          MergeGrantReason::kCurrentEdgeChanged);
    }
    if (context.now >
        context.expected.expiry + 1.0e-9) {
      return terminalize(
          DestinationMergeGrantConsumeResult::kExpired,
          MergeGrantState::kExpired,
          MergeGrantReason::
              kGrantExpiredAtDestinationEntry);
    }
    // The exact owner/slot lease is a hard gate for both ordinary consume
    // and in-flight fault recovery.  Check it before the live generation
    // comparison so a missing calendar reservation can never be hidden by a
    // simultaneous fault-generation change.
    if (!context
             .exact_destination_calendar_reservation_present) {
      return terminalize(
          DestinationMergeGrantConsumeResult::
              kCalendarReservationMissing,
          MergeGrantState::kRevokedStaleState,
          MergeGrantReason::kCalendarGenerationChanged);
    }
    if (context.physical_fault_active ||
        context.current_physical_fault_generation !=
            context.expected
                .physical_fault_generation ||
        context.current_advertised_fault_generation !=
            context.expected
                .advertised_fault_generation) {
      // A physical fault that begins only after the exact EDGE_ENTER does not
      // retroactively make that physical traversal illegal.  Retire the stale
      // generation capability, but consume its still-exact destination lease
      // so the already in-flight bag may continue into local service.  Both
      // proof bits are runtime-local and neither can be inferred from a raw
      // generation mismatch.
      if (context.exact_grant_edge_entry_observed &&
          context.local_inflight_fault_instance_observed &&
          context.current_physical_fault_generation !=
              context.expected.physical_fault_generation) {
        return consume(
            DestinationMergeGrantConsumeResult::
                kConsumedAfterInflightFaultGenerationChange,
            MergeGrantReason::
                kConsumedAtDestinationEntryAfterInflightFaultGenerationChange,
            true);
      }
      return terminalize(
          DestinationMergeGrantConsumeResult::
              kFaultGenerationChanged,
          MergeGrantState::kRevokedFault,
          MergeGrantReason::kFaultGenerationChanged);
    }
    return consume(
        DestinationMergeGrantConsumeResult::kConsumed,
        MergeGrantReason::kConsumedAtDestinationEntry,
        false);
  }

  bool rollback_committed_noexcept(
      MergeGrantCapability& grant,
      const DestinationMergeRequest& request,
      double now,
      MergeGrantReason reason) noexcept {
    if (!validates_active_capability(grant) ||
        request.request_id != grant.request_id_ ||
        request.lineage != grant.lineage_ ||
        request.request_generation !=
            grant.request_generation_ ||
        request.junction_queue_generation !=
            grant.request_snapshot_
                .junction_queue_generation ||
        request.runtime_bag_id !=
            grant.owner_runtime_bag_id_ ||
        request.requested_directed_edge !=
            grant.exact_directed_edge_) {
      return false;
    }
    const auto active = std::find_if(
        active_.begin(),
        active_.end(),
        [&](const ActiveGrantRecord& record) {
          return record.grant_id == grant.grant_id_;
        });
    append_lifecycle_noexcept(
        request,
        grant.grant_id_,
        MergeGrantState::kRolledBack,
        reason,
        now,
        grant.slot_start_,
        grant.slot_end_,
        grant.calendar_generation_,
        grant.fault_generation_,
        grant.issue_time_,
        grant.expiry_);
    grant.state_ = MergeGrantState::kRolledBack;
    active_.erase(active);
    --counters_.issued_count;
    --counters_.prepared_count;
    --counters_.committed_count;
    ++counters_.rolled_back_count;
    ++counters_.post_commit_rollback_count;
    if (reason == MergeGrantReason::kQueueCapacityBlock) {
      ++counters_.queue_capacity_block_count;
    }
    ++generation_;
    return true;
  }

  void append_lifecycle(const DestinationMergeRequest& request,
                        std::uint64_t grant_id,
                        MergeGrantState state,
                        MergeGrantReason reason,
                        double time,
                        double slot_start,
                        double slot_end,
                        std::uint64_t calendar_generation,
                        int fault_generation,
                        double issue_time = 0.0,
                        double grant_expiry = 0.0,
                        const DestinationMergeGrantObservedState*
                            observed = nullptr) {
    ++counters_.lifecycle_transition_count;
    if (lifecycle_.size() == lifecycle_limit_) {
      ++counters_.lifecycle_dropped_count;
      return;
    }
    assert(lifecycle_.capacity() >= lifecycle_limit_);
    lifecycle_.push_back(make_lifecycle(request,
                                        grant_id,
                                        state,
                                        reason,
                                        time,
                                        slot_start,
                                        slot_end,
                                        calendar_generation,
                                        fault_generation,
                                        issue_time,
                                        grant_expiry,
                                        observed));
    ++counters_.lifecycle_stored_count;
  }

  void append_lifecycle_noexcept(
      const DestinationMergeRequest& request,
      std::uint64_t grant_id,
      MergeGrantState state,
      MergeGrantReason reason,
      double time,
      double slot_start,
      double slot_end,
      std::uint64_t calendar_generation,
      int fault_generation,
      double issue_time = 0.0,
      double grant_expiry = 0.0,
      const DestinationMergeGrantObservedState*
          observed = nullptr) noexcept {
    ++counters_.lifecycle_transition_count;
    if (lifecycle_.size() == lifecycle_limit_) {
      ++counters_.lifecycle_dropped_count;
      return;
    }
    assert(lifecycle_.capacity() >= lifecycle_limit_);
    lifecycle_.push_back(make_lifecycle(request,
                                        grant_id,
                                        state,
                                        reason,
                                        time,
                                        slot_start,
                                        slot_end,
                                        calendar_generation,
                                        fault_generation,
                                        issue_time,
                                        grant_expiry,
                                        observed));
    ++counters_.lifecycle_stored_count;
  }

  static DestinationMergeGrantLifecycleRow make_lifecycle(
      const DestinationMergeRequest& request,
      std::uint64_t grant_id,
      MergeGrantState state,
      MergeGrantReason reason,
      double time,
      double slot_start,
      double slot_end,
      std::uint64_t calendar_generation,
      int fault_generation,
      double issue_time,
      double grant_expiry,
      const DestinationMergeGrantObservedState*
          observed) noexcept {
    DestinationMergeGrantLifecycleRow row;
    row.time = time;
    row.request_id = request.request_id;
    row.grant_id = grant_id;
    row.lineage = request.lineage;
    row.request_generation = request.request_generation;
    row.junction_queue_generation =
        request.junction_queue_generation;
    row.runtime_bag_id = request.runtime_bag_id;
    row.task_id = request.task_id;
    row.segment_id = request.lifecycle_segment_id;
    row.upstream_node = request.upstream_node;
    row.destination_node = request.destination_merge_node;
    row.edge = request.requested_directed_edge;
    row.request_time = request.request_time;
    row.fifo_request_time = request.fifo_request_time;
    row.earliest_edge_entry =
        request.earliest_edge_entry;
    row.exact_edge_travel_seconds =
        request.exact_edge_travel_seconds;
    row.projected_arrival = request.projected_arrival;
    row.goal = request.goal;
    row.route_score = request.route_score;
    row.static_remaining = request.static_remaining;
    row.destination_service_seconds =
        request.destination_service_seconds;
    row.downstream_queue_pressure =
        request.downstream_queue_pressure;
    row.deadline_slack = request.deadline_slack;
    row.wait_age = request.wait_age;
    row.task_class_code = request.task_class_code;
    row.task_class = request.task_class;
    row.storage_leg = request.storage_leg;
    row.source_release_age =
        request.source_release_age;
    row.local_queue_age = request.local_queue_age;
    row.enqueue_sequence = request.enqueue_sequence;
    row.request_expiry = request.expiry;
    row.slot_start = slot_start;
    row.slot_end = slot_end;
    row.issue_time = issue_time;
    row.grant_expiry = grant_expiry;
    row.calendar_generation = calendar_generation;
    row.fault_generation = fault_generation;
    row.advertised_fault_generation =
        request.advertised_fault_generation;
    row.observed_claimed_request_generation =
        observed == nullptr
            ? request.request_generation
            : observed->claimed_request_generation;
    row.observed_claimed_junction_queue_generation =
        observed == nullptr
            ? request.junction_queue_generation
            : observed
                  ->claimed_junction_queue_generation;
    row.observed_claimed_calendar_generation =
        observed == nullptr
            ? calendar_generation
            : observed->claimed_calendar_generation;
    row.observed_claimed_owner_runtime_bag_id =
        observed == nullptr
            ? request.runtime_bag_id
            : observed->claimed_owner_runtime_bag_id;
    row.observed_claimed_edge =
        observed == nullptr
            ? request.requested_directed_edge
            : observed->claimed_edge;
    row.observed_claimed_destination_node =
        observed == nullptr
            ? request.destination_merge_node
            : observed->claimed_destination_node;
    row.observed_event_owner_runtime_bag_id =
        observed == nullptr
            ? request.runtime_bag_id
            : observed->event_owner_runtime_bag_id;
    row.observed_event_edge =
        observed == nullptr
            ? request.requested_directed_edge
            : observed->event_edge;
    row.observed_event_destination_node =
        observed == nullptr
            ? request.destination_merge_node
            : observed->event_destination_node;
    row.observed_junction_queue_generation =
        observed == nullptr
            ? request.junction_queue_generation
            : observed->junction_queue_generation;
    row.observed_calendar_generation =
        observed == nullptr
            ? calendar_generation
            : observed->calendar_generation;
    row.observed_physical_fault_generation =
        observed == nullptr
            ? fault_generation
            : observed->physical_fault_generation;
    row.observed_advertised_fault_generation =
        observed == nullptr
            ? request.advertised_fault_generation
            : observed->advertised_fault_generation;
    row.observed_physical_fault_active =
        observed != nullptr &&
        observed->physical_fault_active;
    row.observed_exact_calendar_reservation_present =
        observed != nullptr &&
        observed->exact_calendar_reservation_present;
    row.state = state;
    row.reason = reason;
    return row;
  }

  int destination_node_ = -1;
  std::size_t max_pending_requests_ = 64;
  std::size_t lifecycle_limit_ = 1024;
  std::vector<PendingRecord> pending_;
  std::vector<ActiveGrantRecord> active_;
  std::vector<DestinationMergeGrantLifecycleRow> lifecycle_;
  DestinationMergeGrantCounters counters_;
  std::uint64_t next_request_id_ = 1;
  std::uint64_t next_grant_id_ = 1;
  std::uint64_t generation_ = 0;
};

inline DestinationMergeRequest
DestinationMergeGrantCheckpointCodec::clone_request(
    const DestinationMergeRequest& request) {
  DestinationMergeRequest copy = request;
  if (request.lifecycle_segment_id != nullptr) {
    copy.lifecycle_segment_id =
        std::make_shared<const std::string>(
            *request.lifecycle_segment_id);
  }
  copy.lifecycle_request_snapshot.reset();
  if (request.lifecycle_request_snapshot != nullptr) {
    DestinationMergeRequest identity =
        *request.lifecycle_request_snapshot;
    identity.lifecycle_request_snapshot.reset();
    if (identity.lifecycle_segment_id != nullptr) {
      identity.lifecycle_segment_id =
          std::make_shared<const std::string>(
              *identity.lifecycle_segment_id);
    }
    copy.lifecycle_request_snapshot =
        std::make_shared<const DestinationMergeRequest>(
            std::move(identity));
  }
  return copy;
}

inline DestinationMergeGrantLifecycleRow
DestinationMergeGrantCheckpointCodec::clone_lifecycle(
    const DestinationMergeGrantLifecycleRow& row) {
  DestinationMergeGrantLifecycleRow copy = row;
  if (row.segment_id != nullptr) {
    copy.segment_id =
        std::make_shared<const std::string>(*row.segment_id);
  }
  return copy;
}

inline MergeGrantCapabilityCheckpoint
DestinationMergeGrantCheckpointCodec::capture(
    const MergeGrantCapability& capability) {
  MergeGrantCapabilityCheckpoint checkpoint;
  checkpoint.grant_id = capability.grant_id_;
  checkpoint.request_id = capability.request_id_;
  checkpoint.lineage = capability.lineage_;
  checkpoint.request_generation = capability.request_generation_;
  checkpoint.owner_runtime_bag_id =
      capability.owner_runtime_bag_id_;
  checkpoint.exact_directed_edge =
      capability.exact_directed_edge_;
  checkpoint.destination_node = capability.destination_node_;
  checkpoint.slot_start = capability.slot_start_;
  checkpoint.slot_end = capability.slot_end_;
  checkpoint.issue_time = capability.issue_time_;
  checkpoint.request_time = capability.request_time_;
  checkpoint.expiry = capability.expiry_;
  checkpoint.calendar_generation =
      capability.calendar_generation_;
  checkpoint.fault_generation = capability.fault_generation_;
  checkpoint.advertised_fault_generation =
      capability.advertised_fault_generation_;
  checkpoint.state = capability.state_;
  checkpoint.request_snapshot =
      clone_request(capability.request_snapshot_);
  return checkpoint;
}

inline MergeGrantCapability
DestinationMergeGrantCheckpointCodec::restore(
    const MergeGrantCapabilityCheckpoint& checkpoint) {
  const auto& request = checkpoint.request_snapshot;
  if (checkpoint.grant_id == 0 ||
      checkpoint.request_id == 0 ||
      checkpoint.lineage == 0 ||
      checkpoint.request_generation == 0 ||
      checkpoint.owner_runtime_bag_id < 0 ||
      checkpoint.destination_node < 0 ||
      checkpoint.exact_directed_edge.from_node < 0 ||
      checkpoint.exact_directed_edge.to_node !=
          checkpoint.destination_node ||
      !std::isfinite(checkpoint.slot_start) ||
      !std::isfinite(checkpoint.slot_end) ||
      !std::isfinite(checkpoint.issue_time) ||
      !std::isfinite(checkpoint.request_time) ||
      !std::isfinite(checkpoint.expiry) ||
      checkpoint.slot_end <= checkpoint.slot_start ||
      checkpoint.expiry != checkpoint.slot_end ||
      checkpoint.state != MergeGrantState::kCommitted ||
      request.request_id != checkpoint.request_id ||
      request.lineage != checkpoint.lineage ||
      request.request_generation !=
          checkpoint.request_generation ||
      request.runtime_bag_id !=
          checkpoint.owner_runtime_bag_id ||
      request.requested_directed_edge !=
          checkpoint.exact_directed_edge ||
      request.destination_merge_node !=
          checkpoint.destination_node ||
      request.request_time != checkpoint.request_time ||
      request.advertised_fault_generation !=
          checkpoint.advertised_fault_generation) {
    throw std::invalid_argument(
        "merge capability checkpoint is inconsistent");
  }
  auto capability = MergeGrantCapability(
      checkpoint.grant_id,
      clone_request(request),
      checkpoint.slot_start,
      checkpoint.slot_end,
      checkpoint.issue_time,
      checkpoint.calendar_generation,
      checkpoint.fault_generation);
  if (capability.grant_id_ != checkpoint.grant_id ||
      capability.request_id_ != checkpoint.request_id ||
      capability.lineage_ != checkpoint.lineage ||
      capability.request_generation_ !=
          checkpoint.request_generation ||
      capability.owner_runtime_bag_id_ !=
          checkpoint.owner_runtime_bag_id ||
      capability.exact_directed_edge_ !=
          checkpoint.exact_directed_edge ||
      capability.destination_node_ !=
          checkpoint.destination_node ||
      capability.expiry_ != checkpoint.expiry ||
      capability.calendar_generation_ !=
          checkpoint.calendar_generation ||
      capability.fault_generation_ !=
          checkpoint.fault_generation) {
    throw std::invalid_argument(
        "merge capability checkpoint failed exact reconstruction");
  }
  return capability;
}

inline DestinationMergeGrantControllerCheckpoint
DestinationMergeGrantCheckpointCodec::capture(
    const DestinationMergeGrantController& controller) {
  DestinationMergeGrantControllerCheckpoint checkpoint;
  checkpoint.destination_node = controller.destination_node_;
  checkpoint.max_pending_requests =
      controller.max_pending_requests_;
  checkpoint.lifecycle_limit = controller.lifecycle_limit_;
  checkpoint.pending.reserve(controller.pending_.size());
  for (const auto& pending : controller.pending_) {
    checkpoint.pending.push_back(
        clone_request(pending.request));
  }
  checkpoint.active.reserve(controller.active_.size());
  for (const auto& active : controller.active_) {
    if (active.request_snapshot == nullptr) {
      throw std::logic_error(
          "active merge grant lacks its immutable request identity");
    }
    DestinationMergeActiveGrantCheckpoint item;
    item.grant_id = active.grant_id;
    item.request_id = active.request_id;
    item.lineage = active.lineage;
    item.request_generation = active.request_generation;
    item.junction_queue_generation =
        active.junction_queue_generation;
    item.owner_runtime_bag_id =
        active.owner_runtime_bag_id;
    item.edge = active.edge;
    item.slot_start = active.slot_start;
    item.slot_end = active.slot_end;
    item.issue_time = active.issue_time;
    item.grant_expiry = active.grant_expiry;
    item.calendar_generation = active.calendar_generation;
    item.physical_fault_generation =
        active.physical_fault_generation;
    item.advertised_fault_generation =
        active.advertised_fault_generation;
    item.request_snapshot =
        clone_request(*active.request_snapshot);
    checkpoint.active.push_back(std::move(item));
  }
  checkpoint.lifecycle.reserve(controller.lifecycle_.size());
  for (const auto& row : controller.lifecycle_) {
    checkpoint.lifecycle.push_back(clone_lifecycle(row));
  }
  checkpoint.counters = controller.counters_;
  checkpoint.next_request_id = controller.next_request_id_;
  checkpoint.next_grant_id = controller.next_grant_id_;
  checkpoint.generation = controller.generation_;
  return checkpoint;
}

inline DestinationMergeGrantController
DestinationMergeGrantCheckpointCodec::restore(
    const DestinationMergeGrantControllerCheckpoint& checkpoint) {
  if (checkpoint.destination_node < 0 ||
      checkpoint.max_pending_requests == 0 ||
      checkpoint.lifecycle.size() > checkpoint.lifecycle_limit ||
      checkpoint.pending.size() >
          checkpoint.max_pending_requests ||
      checkpoint.active.size() >
          checkpoint.max_pending_requests ||
      checkpoint.next_request_id == 0 ||
      checkpoint.next_grant_id == 0) {
    throw std::invalid_argument(
        "merge controller checkpoint bounds are invalid");
  }
  DestinationMergeGrantController controller(
      checkpoint.destination_node,
      checkpoint.max_pending_requests,
      checkpoint.lifecycle_limit);
  std::set<std::uint64_t> request_ids;
  std::set<std::uint64_t> grant_ids;
  for (const auto& pending : checkpoint.pending) {
    if (pending.destination_merge_node !=
            checkpoint.destination_node ||
        pending.request_id == 0 ||
        !request_ids.insert(pending.request_id).second) {
      throw std::invalid_argument(
          "merge controller pending checkpoint is inconsistent");
    }
    controller.pending_.push_back(
        DestinationMergeGrantController::PendingRecord{
            clone_request(pending)});
  }
  for (const auto& active : checkpoint.active) {
    const auto& request = active.request_snapshot;
    if (active.grant_id == 0 ||
        active.request_id == 0 ||
        active.lineage == 0 ||
        active.request_generation == 0 ||
        active.owner_runtime_bag_id < 0 ||
        active.edge.to_node != checkpoint.destination_node ||
        active.slot_end <= active.slot_start ||
        active.grant_expiry != active.slot_end ||
        request.request_id != active.request_id ||
        request.lineage != active.lineage ||
        request.request_generation !=
            active.request_generation ||
        request.junction_queue_generation !=
            active.junction_queue_generation ||
        request.runtime_bag_id !=
            active.owner_runtime_bag_id ||
        request.requested_directed_edge != active.edge ||
        request.destination_merge_node !=
            checkpoint.destination_node ||
        !request_ids.insert(active.request_id).second ||
        !grant_ids.insert(active.grant_id).second) {
      throw std::invalid_argument(
          "merge controller active checkpoint is inconsistent");
    }
    auto request_snapshot =
        std::make_shared<const DestinationMergeRequest>(
            clone_request(request));
    controller.active_.push_back(
        DestinationMergeGrantController::ActiveGrantRecord{
            active.grant_id,
            active.request_id,
            active.lineage,
            active.request_generation,
            active.junction_queue_generation,
            active.owner_runtime_bag_id,
            active.edge,
            active.slot_start,
            active.slot_end,
            active.issue_time,
            active.grant_expiry,
            active.calendar_generation,
            active.physical_fault_generation,
            active.advertised_fault_generation,
            std::move(request_snapshot)});
  }
  controller.lifecycle_.clear();
  controller.lifecycle_.reserve(checkpoint.lifecycle_limit);
  for (const auto& row : checkpoint.lifecycle) {
    controller.lifecycle_.push_back(clone_lifecycle(row));
  }
  controller.counters_ = checkpoint.counters;
  controller.next_request_id_ = checkpoint.next_request_id;
  controller.next_grant_id_ = checkpoint.next_grant_id;
  controller.generation_ = checkpoint.generation;
  if (!controller.conservation_holds() ||
      controller.counters_.peak_pending_count <
          controller.pending_.size() ||
      controller.counters_.peak_active_unconsumed_count <
          controller.active_.size()) {
    throw std::invalid_argument(
        "merge controller checkpoint violates conservation");
  }
  for (const auto request_id : request_ids) {
    if (request_id >= controller.next_request_id_) {
      throw std::invalid_argument(
          "merge controller next request id is stale");
    }
  }
  for (const auto grant_id : grant_ids) {
    const auto local_grant_id =
        grant_id & 0xffffffffULL;
    if (local_grant_id == 0 ||
        local_grant_id >= controller.next_grant_id_) {
      throw std::invalid_argument(
          "merge controller next grant id is stale");
    }
  }
  return controller;
}

}  // namespace czr005::ics
