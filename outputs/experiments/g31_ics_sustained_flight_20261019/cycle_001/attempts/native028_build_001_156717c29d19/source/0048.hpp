#pragma once

// Diagnostic-only serial timing storage. Do not embed this in physical state,
// config, events, observations, checkpoints or deterministic state hashes.
// start()/take() may allocate only at an offline safe boundary. Scope entry and
// exit use preallocated trivial rows and cannot throw or invoke user callbacks.
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <limits>
#include <stdexcept>
#include <type_traits>
#include <vector>

namespace czr005::ics::diagnostic {

enum class RequestTimingPhase : std::uint16_t {
  native_call, event_dispatch, admission, source_execution, transfer_progress,
  source_validate, receiver_validate, permission_validate, reservation_commit,
  physical_dispatch, publication_delivery, outcome_update, ack_create,
  ack_delivery, timeout, retry, cancellation, withdrawal, recovery,
  shared_scan, observation, serialization, unclassified, leg_creation
};

enum class RequestTimingMethod : std::uint16_t {
  none, submit_transfer, submit_command, query_transfer, query_command,
  observe_protocol, observe_control, observe_policy, observe_policy_recent,
  demand_signature, planning_snapshots, advance_notification, advance_to, result_at
};

enum class RequestTimingIdentity : std::uint8_t {
  none, transfer, command, leg, job, binding_submission,
  route, demand, service_forecast, planning_snapshot, planning_snapshot_v2,
  planning_snapshot_v3
};

struct RequestTimingAssociation {
  RequestTimingIdentity kind = RequestTimingIdentity::none;
  std::int64_t index = -1;
  std::uint64_t attempt = 0;
  RequestTimingIdentity related_kind = RequestTimingIdentity::none;
  std::int64_t related_index = -1;
};

enum RequestTimingError : std::uint32_t {
  timing_ok = 0,
  timing_overflow = 1u << 0,
  timing_depth_exceeded = 1u << 1,
  timing_invalid_nesting = 1u << 2,
  timing_clock_reversed = 1u << 3,
  timing_stale_scope = 1u << 4,
  timing_reset_with_unread_records = 1u << 5,
  timing_counter_exhausted = 1u << 6,
  timing_invalid_identity = 1u << 7
};

struct RequestTimingRow {
  std::uint64_t trace_epoch = 0;
  std::uint64_t call_ordinal = 0;
  std::uint64_t span_id = 0;
  std::int64_t parent_span_id = -1;
  std::uint64_t start_ns = 0;
  std::uint64_t end_ns = 0;
  std::uint64_t event_sequence = 0;
  double logical_time = 0.;
  RequestTimingPhase phase = RequestTimingPhase::unclassified;
  RequestTimingMethod method = RequestTimingMethod::none;
  RequestTimingAssociation association;
  bool ended = false;
  bool exception_exit = false;
};
static_assert(std::is_trivially_copyable<RequestTimingRow>::value,
              "commit diagnostics require trivial preallocated records");

struct RequestTimingBatch {
  std::uint64_t session_identity = 0;
  std::uint64_t trace_epoch = 0;
  std::uint64_t completed_outer_calls = 0;
  std::uint64_t emitted_span_count = 0;
  std::uint32_t errors = timing_ok;
  bool enabled = false;
  std::vector<RequestTimingRow> rows;
};

struct RequestSteadyClock {
  static std::uint64_t now() noexcept {
    return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
  }
};

// Clock is a compile-time test seam, not a runtime callback. The production
// alias below fixes it to steady_clock. No clock is sampled when disabled.
template<class Clock = RequestSteadyClock, std::size_t MaximumDepth = 128>
class BasicRequestTimingRecorder {
 public:
  static_assert(MaximumDepth > 0, "timing depth must be positive");
  static_assert(noexcept(Clock::now()), "timing clock must be noexcept");

  struct Token {
    const BasicRequestTimingRecorder* owner = nullptr;
    std::uint64_t epoch = 0;
    std::uint64_t span_id = 0;
    std::size_t index = 0;
    bool active = false;
  };

  class Scope {
   public:
    Scope(BasicRequestTimingRecorder& recorder, RequestTimingPhase phase,
          RequestTimingAssociation association, RequestTimingMethod method,
          std::uint64_t event_sequence, double logical_time) noexcept
        : recorder_(&recorder), token_(recorder.begin(phase, association, method,
              event_sequence, logical_time)), exceptions_on_entry_(token_.active ? std::uncaught_exceptions() : 0) {}
    ~Scope() noexcept {
      if (!token_.active) return;
      recorder_->end(token_, exception_exit_ || std::uncaught_exceptions() > exceptions_on_entry_);
    }
    Scope(const Scope&) = delete;
    Scope& operator=(const Scope&) = delete;
    Scope(Scope&&) = delete;
    Scope& operator=(Scope&&) = delete;
    // A catch boundary may mark the outcome; end time is still always recorded.
    // Automatic unwinding needs no allocating exception text in the hot path.
    void mark_exception() noexcept { exception_exit_ = true; }
    void finish() noexcept {
      if (!token_.active) return;
      recorder_->end(token_, exception_exit_ || std::uncaught_exceptions() > exceptions_on_entry_);
      token_.active = false;
    }
   private:
    BasicRequestTimingRecorder* recorder_;
    Token token_;
    bool exception_exit_ = false;
    int exceptions_on_entry_ = 0;
  };

  BasicRequestTimingRecorder() = default;
  BasicRequestTimingRecorder(const BasicRequestTimingRecorder&) = delete;
  BasicRequestTimingRecorder& operator=(const BasicRequestTimingRecorder&) = delete;

  bool enabled() const noexcept { return enabled_; }
  std::uint32_t errors() const noexcept { return errors_; }
  std::size_t open_scopes() const noexcept { return depth_; }

  // The offline caller supplies a unique, nonzero session namespace within
  // its capture. A fork is a distinct instance/namespace; it never resets the
  // source recorder. This field is diagnostic, not part of any physical seal.
  void start(std::size_t capacity, std::uint64_t session_identity) {
    if (depth_ != 0) throw std::logic_error("request_timing:start_inside_scope");
    if (capacity == 0 || capacity > static_cast<std::size_t>(std::numeric_limits<std::int64_t>::max()))
      throw std::invalid_argument("request_timing:invalid_capacity");
    if (used_ != 0) throw std::logic_error("request_timing:unread_records_before_start");
    if (session_identity == 0 || (session_identity_ != 0 && session_identity_ != session_identity))
      throw std::invalid_argument("request_timing:invalid_session_identity");
    if (epoch_ == std::numeric_limits<std::uint64_t>::max())
      throw std::overflow_error("request_timing:epoch_exhausted");
    enabled_ = false;
    std::vector<RequestTimingRow> prepared(capacity); // offline allocation only
    rows_.swap(prepared);
    ++epoch_;
    session_identity_ = session_identity;
    used_ = depth_ = 0;
    next_span_id_ = call_ordinal_ = completed_outer_calls_ = 0;
    errors_ = timing_ok;
    origin_ = last_clock_ = Clock::now();
    enabled_ = true;
  }

  void stop() {
    if (depth_ != 0) throw std::logic_error("request_timing:stop_inside_scope");
    enabled_ = false;
  }

  // Explicit restoration boundary. Unread evidence cannot silently survive as
  // a valid continuation. A fresh start() is required after an offline take().
  void reset_after_restore() noexcept {
    enabled_ = false;
    if (used_ != 0 || depth_ != 0) errors_ |= timing_reset_with_unread_records;
    depth_ = 0;
    if (epoch_ != std::numeric_limits<std::uint64_t>::max()) ++epoch_;
    else errors_ |= timing_counter_exhausted;
  }

  RequestTimingBatch take() {
    if (depth_ != 0) throw std::logic_error("request_timing:take_inside_scope");
    RequestTimingBatch result;
    result.session_identity = session_identity_;
    result.trace_epoch = epoch_;
    result.completed_outer_calls = completed_outer_calls_;
    result.emitted_span_count = next_span_id_;
    result.errors = errors_;
    result.enabled = enabled_;
    result.rows.assign(rows_.begin(), rows_.begin() + used_); // offline export
    used_ = 0; // sticky errors and monotonically increasing span/call IDs remain
    return result;
  }

  Scope scoped(RequestTimingPhase phase, RequestTimingAssociation association = {},
               RequestTimingMethod method = RequestTimingMethod::none,
               std::uint64_t event_sequence = 0, double logical_time = 0.) noexcept {
    return Scope(*this, phase, association, method, event_sequence, logical_time);
  }

  Token begin(RequestTimingPhase phase, RequestTimingAssociation association = {},
              RequestTimingMethod method = RequestTimingMethod::none,
              std::uint64_t event_sequence = 0, double logical_time = 0.) noexcept {
    if (!enabled_) return {};
    if (!valid_identity(association.kind, association.index) ||
        !valid_identity(association.related_kind, association.related_index) ||
        !std::isfinite(logical_time) || logical_time < 0.) errors_ |= timing_invalid_identity;
    if (depth_ == MaximumDepth) { errors_ |= timing_depth_exceeded; return {}; }
    if (used_ == rows_.size()) { errors_ |= timing_overflow; return {}; }
    if (next_span_id_ == static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()) ||
        (depth_ == 0 && call_ordinal_ == std::numeric_limits<std::uint64_t>::max())) {
      errors_ |= timing_counter_exhausted; return {};
    }
    if (depth_ == 0) {
      if (phase != RequestTimingPhase::native_call || method == RequestTimingMethod::none)
        errors_ |= timing_invalid_nesting;
      ++call_ordinal_;
    }
    auto& row = rows_[used_];
    row = RequestTimingRow{};
    row.trace_epoch = epoch_;
    row.call_ordinal = call_ordinal_;
    row.span_id = next_span_id_++;
    row.parent_span_id = depth_ == 0 ? -1 : static_cast<std::int64_t>(rows_[stack_[depth_-1]].span_id);
    row.start_ns = sample();
    row.phase = phase;
    row.method = method;
    row.association = association;
    row.event_sequence = event_sequence;
    row.logical_time = logical_time;
    stack_[depth_++] = used_;
    return {this, epoch_, row.span_id, used_++, true};
  }

  void end(Token token, bool exception_exit = false) noexcept {
    if (!token.active) return;
    if (token.owner != this || token.epoch != epoch_ || token.index >= used_ ||
        rows_[token.index].span_id != token.span_id) { errors_ |= timing_stale_scope; return; }
    if (depth_ == 0 || stack_[depth_-1] != token.index || token.index >= used_ || rows_[token.index].ended) {
      errors_ |= timing_invalid_nesting; return;
    }
    auto& row = rows_[token.index];
    row.end_ns = sample();
    row.ended = true;
    row.exception_exit = exception_exit;
    --depth_;
    if (depth_ == 0) ++completed_outer_calls_;
  }

 private:
  static bool valid_identity(RequestTimingIdentity kind, std::int64_t index) noexcept {
    switch (kind) {
      case RequestTimingIdentity::none: return index == -1;
      case RequestTimingIdentity::binding_submission: return index == -1;
      case RequestTimingIdentity::transfer:
      case RequestTimingIdentity::command:
      case RequestTimingIdentity::leg:
      case RequestTimingIdentity::job:
      case RequestTimingIdentity::route:
      case RequestTimingIdentity::demand:
      case RequestTimingIdentity::service_forecast:
      case RequestTimingIdentity::planning_snapshot:
      case RequestTimingIdentity::planning_snapshot_v2:
      case RequestTimingIdentity::planning_snapshot_v3: return index >= 0;
    }
    return false;
  }
  std::uint64_t sample() noexcept {
    const auto current = Clock::now();
    if (current < last_clock_ || current < origin_) {
      errors_ |= timing_clock_reversed;
      return last_clock_ - origin_;
    }
    last_clock_ = current;
    return current - origin_;
  }
  bool enabled_ = false;
  std::uint32_t errors_ = timing_ok;
  std::uint64_t epoch_ = 0, origin_ = 0, last_clock_ = 0;
  std::uint64_t session_identity_ = 0;
  std::uint64_t next_span_id_ = 0, call_ordinal_ = 0, completed_outer_calls_ = 0;
  std::size_t used_ = 0, depth_ = 0;
  std::array<std::size_t, MaximumDepth> stack_{};
  std::vector<RequestTimingRow> rows_;
};

using RequestTimingRecorder = BasicRequestTimingRecorder<>;

} // namespace czr005::ics::diagnostic
