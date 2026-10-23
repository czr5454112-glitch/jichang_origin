#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace czr005::ics {

// Causal statistics of successful departures from the post-service queue.
// An idle period before the departing bag was enqueued is not a slow service
// observation. This is a routing estimate, never a device service duration.
struct S4QueueFlowEstimate {
  double last_departure = -1.0;
  double ewma_headway = 0.0;
  std::uint64_t departure_count = 0;

  void observe_departure(double now, double enqueued_at,
                         double min_headway) noexcept {
    const double sample = std::max(
        min_headway, now - std::max(last_departure, enqueued_at));
    ewma_headway = departure_count == 0
                       ? sample
                       : 0.75 * ewma_headway + 0.25 * sample;
    last_departure = now;
    ++departure_count;
  }

  double headway(double now, double front_enqueued_at,
                 double cold_prior, double min_headway) const noexcept {
    double estimate = std::max(
        min_headway, departure_count == 0 ? cold_prior : ewma_headway);
    // The currently unfinished busy interval is censored. Do not let an old
    // fast-flow estimate hide the fact that the current front has not moved.
    if (front_enqueued_at >= 0.0) {
      estimate = std::max(
          estimate, now - std::max(last_departure, front_enqueued_at));
    }
    return estimate;
  }
};

// A local fluid approximation at the candidate's service-completion ETA.
// committed_completions contains only already-reserved, nonterminal service
// completions by that ETA, excluding the candidate itself. It is not the
// total scheduled_incoming counter. No new arrivals or future route is read.
inline double s4_projected_post_service_wait(
    int queued, int committed_completions, double seconds_until_ready,
    double headway) noexcept {
  const double work = static_cast<double>(
      std::max(0, queued) + std::max(0, committed_completions));
  return std::max(0.0, work * std::max(0.0, headway) -
                           std::max(0.0, seconds_until_ready));
}

struct S4CommittedWaitForecast {
  bool pending = false;
  int node = -1;
  double commit_time = -1.0;
  double predicted_post_wait = 0.0;
  double legacy_queue_proxy = 0.0;
};

// Scalar-only updates are safe at the runtime's irreversible publication
// boundary. The public metrics map is built later, outside transactions.
struct S4WaitAudit {
  std::uint64_t flow_departure_count = 0;
  std::uint64_t commit_forecast_count = 0;
  std::uint64_t resolved_forecast_count = 0;
  double predicted_absolute_error = 0.0;
  double predicted_squared_error = 0.0;
  double predicted_signed_error = 0.0;
  double legacy_absolute_error = 0.0;
  double legacy_squared_error = 0.0;
  double legacy_signed_error = 0.0;
  double actual_post_wait_sum = 0.0;

  void observe(double predicted, double legacy, double actual) noexcept {
    ++resolved_forecast_count;
    const double error = predicted - actual;
    const double old_error = legacy - actual;
    predicted_absolute_error += std::abs(error);
    predicted_squared_error += error * error;
    predicted_signed_error += error;
    legacy_absolute_error += std::abs(old_error);
    legacy_squared_error += old_error * old_error;
    legacy_signed_error += old_error;
    actual_post_wait_sum += actual;
  }
};

}  // namespace czr005::ics
