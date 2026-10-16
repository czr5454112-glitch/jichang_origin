#include "cpp/ics_core/runtime/request_timing_recorder.hpp"
#include <cassert>
#include <cstdlib>
#include <iostream>
#include <new>

static std::size_t allocations = 0;
void* operator new(std::size_t size) {
  ++allocations;
  if (void* memory = std::malloc(size ? size : 1)) return memory;
  throw std::bad_alloc();
}
void operator delete(void* memory) noexcept { std::free(memory); }
void operator delete(void* memory, std::size_t) noexcept { std::free(memory); }

using namespace czr005::ics::diagnostic;
struct Clock {
  inline static std::uint64_t value = 0;
  inline static std::uint64_t reads = 0;
  static std::uint64_t now() noexcept { ++reads; value += 10; return value; }
};
using Recorder = BasicRequestTimingRecorder<Clock>;
using Phase = RequestTimingPhase;
using Method = RequestTimingMethod;

static void disabled_is_inert() {
  Recorder recorder;
  const auto reads = Clock::reads, allocs = allocations;
  { auto scope = recorder.scoped(Phase::native_call, {}, Method::submit_transfer); }
  assert(Clock::reads == reads && allocations == allocs);
  const auto batch = recorder.take();
  assert(!batch.enabled && batch.rows.empty() && batch.completed_outer_calls == 0);
}

static void nested_exclusive_no_allocation_and_take() {
  Recorder recorder;
  recorder.start(10, 17);
  const auto allocs = allocations;
  {
    auto call = recorder.scoped(Phase::native_call, {}, Method::advance_notification);
    {
      auto source = recorder.scoped(Phase::source_validate,
          {RequestTimingIdentity::transfer, 3, 2}, Method::none, 51, 2.5);
    }
    {
      auto receiver = recorder.scoped(Phase::receiver_validate,
          {RequestTimingIdentity::transfer, 3, 2}, Method::none, 51, 2.5);
    }
  }
  assert(allocations == allocs);
  auto batch = recorder.take();
  assert(batch.errors == timing_ok && batch.session_identity == 17);
  assert(batch.rows.size() == 3 && batch.completed_outer_calls == 1);
  const auto& call = batch.rows[0];
  assert(call.parent_span_id == -1 && call.ended);
  std::uint64_t children = 0;
  for (std::size_t i = 1; i < batch.rows.size(); ++i) {
    const auto& row = batch.rows[i];
    assert(row.parent_span_id == static_cast<std::int64_t>(call.span_id));
    assert(row.call_ordinal == call.call_ordinal && row.ended);
    assert(row.start_ns >= call.start_ns && row.end_ns <= call.end_ns);
    assert(row.association.index == 3 && row.association.attempt == 2);
    children += row.end_ns-row.start_ns;
  }
  const auto exclusive = call.end_ns-call.start_ns-children;
  assert(exclusive + children == call.end_ns-call.start_ns);
  { auto next = recorder.scoped(Phase::native_call, {}, Method::query_transfer); }
  auto next = recorder.take();
  assert(next.rows[0].span_id == 3 && next.rows[0].call_ordinal == 2);
}

static void nested_binding_calls_are_one_outer_call() {
  Recorder recorder; recorder.start(5, 18);
  {
    auto result = recorder.scoped(Phase::native_call, {}, Method::result_at);
    { auto advance = recorder.scoped(Phase::native_call, {}, Method::advance_to); }
  }
  const auto batch = recorder.take();
  assert(batch.errors == timing_ok && batch.completed_outer_calls == 1);
  assert(batch.rows[0].call_ordinal == batch.rows[1].call_ordinal);
}

static void unwind_ends_span() {
  Recorder recorder; recorder.start(4, 19);
  try {
    auto call = recorder.scoped(Phase::native_call, {}, Method::submit_command);
    auto inner = recorder.scoped(Phase::admission);
    throw 7;
  } catch (int) {}
  const auto batch = recorder.take();
  assert(batch.errors == timing_ok && batch.rows.size() == 2);
  assert(batch.rows[0].ended && batch.rows[0].exception_exit);
  assert(batch.rows[1].ended && batch.rows[1].exception_exit);
}

static void overflow_and_depth_are_sticky_unknown() {
  Recorder recorder; recorder.start(1, 20);
  {
    auto call = recorder.scoped(Phase::native_call, {}, Method::advance_notification);
    { auto discarded = recorder.scoped(Phase::ack_delivery); }
  }
  assert(recorder.take().errors & timing_overflow);
  assert(recorder.take().errors & timing_overflow);
  BasicRequestTimingRecorder<Clock, 1> shallow; shallow.start(4, 21);
  {
    auto call = shallow.scoped(Phase::native_call, {}, Method::advance_notification);
    { auto discarded = shallow.scoped(Phase::ack_delivery); }
  }
  assert(shallow.take().errors & timing_depth_exceeded);
}

static void unread_restart_and_active_export_are_rejected() {
  Recorder recorder; recorder.start(4, 22);
  {
    auto call = recorder.scoped(Phase::native_call, {}, Method::submit_transfer);
    bool failed = false;
    try { (void)recorder.take(); } catch (const std::logic_error&) { failed = true; }
    assert(failed);
    failed = false;
    try { recorder.stop(); } catch (const std::logic_error&) { failed = true; }
    assert(failed);
  }
  bool failed = false;
  try { recorder.start(4, 22); } catch (const std::logic_error&) { failed = true; }
  assert(failed);
  (void)recorder.take(); recorder.start(4, 22);
  assert(recorder.errors() == timing_ok);
}

static void restore_retains_gap_and_fork_namespace_is_separate() {
  Recorder parent; parent.start(4, 23);
  { auto call = parent.scoped(Phase::native_call, {}, Method::query_command); }
  Recorder fork;
  assert(!fork.enabled() && parent.enabled());
  fork.start(4, 24);
  assert(fork.take().session_identity != parent.take().session_identity);
  { auto call = parent.scoped(Phase::native_call, {}, Method::query_command); }
  parent.reset_after_restore();
  const auto batch = parent.take();
  assert(!batch.enabled && batch.rows.size() == 1);
  assert(batch.errors & timing_reset_with_unread_records);
  parent.start(4, 23);
  assert(parent.enabled() && parent.errors() == timing_ok);
  parent.stop();
  bool failed = false;
  try { parent.start(4, 24); } catch (const std::invalid_argument&) { failed = true; }
  assert(failed);
}

static void invalid_clock_nesting_and_stale_token_fail_closed() {
  Recorder recorder; recorder.start(4, 25);
  auto outer = recorder.begin(Phase::native_call, {}, Method::advance_notification);
  auto inner = recorder.begin(Phase::ack_delivery);
  recorder.end(outer);
  assert(recorder.errors() & timing_invalid_nesting);
  Clock::value = 0;
  recorder.end(inner); recorder.end(outer);
  assert(recorder.errors() & timing_clock_reversed);
  (void)recorder.take();
  recorder.start(4, 25);
  auto stale = recorder.begin(Phase::native_call, {}, Method::advance_notification);
  recorder.reset_after_restore();
  recorder.end(stale);
  const auto reset = recorder.take();
  assert(reset.errors & timing_stale_scope);
  assert(!reset.rows[0].ended);
}

static void stale_token_cannot_end_reused_slot_or_another_recorder() {
  Recorder recorder; recorder.start(4, 26);
  const auto old = recorder.begin(Phase::native_call, {}, Method::query_command);
  recorder.end(old); (void)recorder.take();
  const auto live = recorder.begin(Phase::native_call, {}, Method::query_command);
  recorder.end(old);
  assert(recorder.open_scopes() == 1 && (recorder.errors() & timing_stale_scope));
  recorder.end(live);
  assert(recorder.take().rows[0].ended);
  Recorder other; other.start(4, 27);
  const auto other_live = other.begin(Phase::native_call, {}, Method::query_command);
  other.end(live);
  assert(other.open_scopes() == 1 && (other.errors() & timing_stale_scope));
  other.end(other_live);
}

static void invalid_associations_are_flagged() {
  Recorder recorder; recorder.start(4, 28);
  { auto call = recorder.scoped(Phase::native_call,
        {RequestTimingIdentity::transfer, -1}, Method::query_transfer); }
  assert(recorder.take().errors & timing_invalid_identity);
  recorder.start(4, 28);
  { auto call = recorder.scoped(Phase::native_call,
        {RequestTimingIdentity::binding_submission, -1}, Method::submit_transfer); }
  assert(recorder.take().errors == timing_ok);
}

static void explicit_phase_finish_is_idempotent_before_next_sibling() {
  Recorder recorder; recorder.start(6, 29);
  {
    auto call = recorder.scoped(Phase::native_call, {}, Method::advance_notification);
    auto source = recorder.scoped(Phase::source_validate);
    source.finish(); source.finish();
    auto receiver = recorder.scoped(Phase::receiver_validate);
    receiver.finish();
  }
  const auto batch = recorder.take();
  assert(batch.errors == timing_ok && batch.rows.size() == 3);
  assert(batch.rows[1].parent_span_id == batch.rows[2].parent_span_id);
  assert(batch.rows[1].end_ns <= batch.rows[2].start_ns);
}

static void emitted_count_survives_empty_and_nonempty_takes() {
  Recorder recorder; recorder.start(4, 30);
  assert(recorder.take().emitted_span_count == 0);
  { auto call = recorder.scoped(Phase::native_call, {}, Method::query_command); }
  const auto first = recorder.take();
  assert(first.emitted_span_count == 1 && first.rows[0].span_id == 0);
  assert(recorder.take().emitted_span_count == 1);
  { auto call = recorder.scoped(Phase::native_call, {}, Method::query_command); }
  const auto second = recorder.take();
  assert(second.emitted_span_count == 2 && second.rows[0].span_id == 1);
}

int main() {
  disabled_is_inert();
  nested_exclusive_no_allocation_and_take();
  nested_binding_calls_are_one_outer_call();
  unwind_ends_span();
  overflow_and_depth_are_sticky_unknown();
  unread_restart_and_active_export_are_rejected();
  restore_retains_gap_and_fork_namespace_is_separate();
  invalid_clock_nesting_and_stale_token_fail_closed();
  stale_token_cannot_end_reused_slot_or_another_recorder();
  invalid_associations_are_flagged();
  explicit_phase_finish_is_idempotent_before_next_sibling();
  emitted_count_survives_empty_and_nonempty_takes();
  std::cout << "12 recorder tests passed; no NativeSession or physics executed\n";
}
