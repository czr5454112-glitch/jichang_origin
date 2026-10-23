#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include "ics_core/runtime/event_driven_junction.hpp"
#include "ics_core/runtime/s4_wait_estimator.hpp"

using namespace czr005::ics;

namespace {

void require(bool value, const std::string& message) {
  if (!value) throw std::runtime_error(message);
}

void near(double actual, double expected, const std::string& message) {
  if (!std::isfinite(actual) || std::abs(actual - expected) > 1.0e-8)
    throw std::runtime_error(message + ": expected " + std::to_string(expected) +
                             ", got " + std::to_string(actual));
}

Graph merge_graph() {
  Graph graph;
  graph.add_node(Node{0, 1, 0.1, 0, 0, {2}});
  graph.add_node(Node{1, 1, 0.1, 0, 1, {2}});
  graph.add_node(Node{2, 4, 5.0, 1, 0, {3}});
  graph.add_node(Node{3, 2, 0.0, 2, 0, {}});
  graph.add_edge(Edge{0, 2, 1.0, 1.0});
  graph.add_edge(Edge{1, 2, 1.0, 1.0});
  graph.add_edge(Edge{2, 3, 1.0, 1.0});
  graph.set_heuristic({
      {0.0, 1000.0, 1.1, 7.1},
      {1000.0, 0.0, 1.1, 7.1},
      {1000.0, 1000.0, 0.0, 6.0},
      {1000.0, 1000.0, 1000.0, 0.0},
  });
  return graph;
}

EventDrivenJunctionConfig config() {
  EventDrivenJunctionConfig value;
  value.scorer_mode = "S4_queue_aware_rule_only";
  value.resource_semantics = "R3";
  value.event_semantics = "E4_batch_plus_destination_merge_request";
  value.merge_grant_timing_mode = "jit_fair_aging_deadline";
  value.merge_grant_rule = "M3";
  value.queue_discipline = "fifo";
  value.enable_source_admission = false;
  value.admission_mode = "off";
  value.enable_backpressure = false;
  value.pressure_mode = "C0";
  value.pibt_mode = "P0";
  value.priority_mode = "Q0";
  value.enable_s4_local_potential_descent_guard = true;
  value.enable_s4_direct_neighbor_merge_calendar_visibility = true;
  value.complete_on_goal_arrival = true;
  value.retry_interval = 0.25;
  value.minimum_service_seconds = 0.001;
  value.dispatch_headway_seconds = 0.0;
  value.entry_headway_seconds = 0.001;
  value.starvation_threshold = 1000.0;
  value.max_decisions_per_bag = 1000;
  value.max_events = 100000;
  value.max_simulation_time = 100.0;
  value.trace_limit = 100000;
  value.event_trace_limit = 100000;
  value.enable_opportunity_telemetry = true;
  value.opportunity_trace_limit = 10000;
  value.merge_grant_lifecycle_limit = 10000;
  return value;
}

std::vector<EventRuntimeBagRequest> requests() {
  return {
      {"blocker", 1, 0.0, 100.0, 2, 3, "eta-regression"},
      {"earlier", 2, 1.0, 100.0, 0, 3, "eta-regression"},
      {"urgent", 3, 2.0, 6.0, 1, 3, "eta-regression"},
  };
}

const EventRuntimeBagResult& bag(const EventDrivenJunctionResult& result, int id) {
  const auto found = std::find_if(result.bags.begin(), result.bags.end(),
      [id](const auto& row) { return row.task_id == id; });
  require(found != result.bags.end(), "expected bag must remain in the complete output cohort");
  return *found;
}

void unchanged_execution(const EventDrivenJunctionResult& a,
                         const EventDrivenJunctionResult& b) {
  require(a.bags.size() == b.bags.size(), "score-only mode must retain all business identities");
  for (const auto& left : a.bags) {
    const auto& right = bag(b, left.task_id);
    require(left.segment_id == right.segment_id &&
                left.completed == right.completed &&
                left.failure_reason == right.failure_reason &&
                left.short_history == right.short_history,
            "unique-route run must preserve identities, routes and terminal states");
    near(right.admitted_time, left.admitted_time, "source operation timing is unchanged");
    near(right.finish_time, left.finish_time, "unique-route completion timing is unchanged");
    near(right.node_service_time_seconds, left.node_service_time_seconds,
         "predicted wait must not change real completed service");
    near(right.edge_travel_time_seconds, left.edge_travel_time_seconds,
         "predicted wait must not change constant-speed transport");
    near(right.junction_queue_wait_seconds, left.junction_queue_wait_seconds,
         "unique-route score changes must not alter J2 waiting");
  }
  require(a.events.size() == b.events.size(), "score-only observation adds no execution events");
  for (std::size_t i = 0; i < a.events.size(); ++i) {
    const auto& x = a.events[i]; const auto& y = b.events[i];
    require(std::tie(x.seq, x.event, x.time, x.task_id, x.runtime_bag_id,
                     x.node, x.from_node, x.to_node, x.reason, x.selected_edge_count) ==
                std::tie(y.seq, y.event, y.time, y.task_id, y.runtime_bag_id,
                     y.node, y.from_node, y.to_node, y.reason, y.selected_edge_count),
            "score-only unique-route run must preserve the complete event ordering");
  }
}

void calendar_wait_uses_arrival_and_real_gaps() {
  event_runtime_detail::LocalCalendar calendar;
  calendar.reserve(1, 100.0, 105.0);
  near(calendar.earliest_start(110.0, 2.0) - 110.0, 0.0,
       "calendar busy now can be free when the bag arrives");
  near(calendar.earliest_start(102.0, 2.0) - 102.0, 3.0,
       "near arrival sees only the unelapsed busy interval");
  event_runtime_detail::LocalCalendar gaps;
  gaps.reserve(1, 5.0, 7.0); gaps.reserve(2, 20.0, 22.0);
  near(gaps.earliest_start(8.0, 2.0) - 8.0, 0.0,
       "a later booking must not hide a sufficiently long current gap");
  near(gaps.earliest_start(6.0, 2.0) - 6.0, 1.0,
       "arrival inside one booking waits only to its end");
}

void post_service_projection_has_seconds_and_no_extra_node_service() {
  // Four already-serviced bags, with a measured one departure per two
  // seconds, require eight seconds of exit work. A candidate ready in three
  // seconds sees five seconds remaining. Its own base service is separate.
  near(s4_projected_post_service_wait(4, 0, 3.0, 2.0), 5.0,
       "post-service work is measured in departure seconds");
  near(s4_projected_post_service_wait(4, 0, 10.0, 2.0), 0.0,
       "current post-service queue can drain before the candidate is ready");
  near(s4_projected_post_service_wait(0, 2, 1.0, 2.0), 3.0,
       "already committed completions participate in the declared fluid estimate");
  near(s4_projected_post_service_wait(0, 0, 0.0, 50.0), 0.0,
       "an empty post-service queue does not invent another base service");
  near(s4_projected_post_service_wait(-1, -2, -1.0, -2.0), 0.0,
       "defensive clamps cannot create negative predicted waiting");
}

void causal_departure_statistics_exclude_idle_time_and_notice_stalls() {
  S4QueueFlowEstimate flow;
  near(flow.headway(100.0, -1.0, 0.25, 0.001), 0.25,
       "cold-start output uses its explicit estimate without observations");
  flow.observe_departure(102.0, 100.0, 0.001);
  near(flow.headway(102.0, -1.0, 0.25, 0.001), 2.0,
       "first sample measures only time after this bag actually enqueued");
  // The queue was empty between 102 and 200. That 98-second idle gap is
  // not a slow-flow sample. New waiting is four seconds, giving EWMA 2.5.
  flow.observe_departure(204.0, 200.0, 0.001);
  near(flow.headway(204.0, -1.0, 0.25, 0.001), 2.5,
       "idle time does not contaminate the observed departure headway");
  near(flow.headway(212.0, 203.0, 0.25, 0.001), 8.0,
       "unfinished current queue interval exposes a stopped exit");
  near(flow.headway(212.0, 211.0, 0.25, 0.001), 2.5,
       "a newly enqueued front does not inherit idle time since last departure");
  require(flow.departure_count == 2, "prediction queries do not fabricate flow observations");
}

void legacy_default_and_actual_j2_service_are_unchanged() {
  const auto original_config = config();
  require(original_config.s4_wait_estimator == "legacy", "new prediction must be exact-off by default");
  const auto original = EventDrivenJunctionRuntime(merge_graph(), original_config).run(requests());
  auto explicit_legacy = original_config; explicit_legacy.s4_wait_estimator = "legacy";
  const auto off = EventDrivenJunctionRuntime(merge_graph(), explicit_legacy).run(requests());
  unchanged_execution(original, off);
  require(original.decisions.size() == off.decisions.size(), "explicit legacy retains every decision");
  for (std::size_t i = 0; i < original.decisions.size(); ++i) {
    const auto& x = original.decisions[i]; const auto& y = off.decisions[i];
    require(x.selected_next == y.selected_next && x.event_time == y.event_time &&
                x.candidates.size() == y.candidates.size(), "legacy decision and candidate sets are identical");
    for (std::size_t k = 0; k < x.candidates.size(); ++k)
      near(y.candidates[k].model_score, x.candidates[k].model_score, "legacy keeps the exact S4 candidate score");
  }
  // Independently derived timetable: blocker owns [0,5], then the urgent
  // arrival wins J2's [5,10], then the earlier nonurgent bag owns [10,15].
  // Each final edge needs one second and the terminal adds no service.
  near(bag(original, 1).finish_time, 6.0, "fixed baseline blocker timetable");
  near(bag(original, 3).finish_time, 11.0, "fixed baseline urgent J2 timetable");
  near(bag(original, 2).finish_time, 16.0, "fixed baseline retained J2 loser timetable");
  for (const auto& mode : {"eta_calendar", "eta_flow"}) {
    auto value = original_config; value.s4_wait_estimator = mode;
    const auto result = EventDrivenJunctionRuntime(merge_graph(), value).run(requests());
    require(result.summary.completed_count == 3 && result.summary.failed_count == 0,
            "ETA score run must complete the whole tiny cohort");
    require(result.summary.reservation_conflicts == 0 &&
                result.summary.runtime_full_astar_calls == 0 &&
                result.summary.global_reservation_scan_count == 0,
            "ETA scoring preserves local calendar authority and one-hop execution");
    unchanged_execution(original, result);
    near(bag(result, 1).node_service_time_seconds, 5.0, "source blocker has one five-second service");
    near(bag(result, 2).node_service_time_seconds, 5.1, "earlier bag has .1+5 seconds of real service");
    near(bag(result, 3).node_service_time_seconds, 5.1, "urgent bag has .1+5 seconds of real service");
    near(bag(result, 2).edge_travel_time_seconds, 2.0, "constant-speed travel is one plus one second");
    const auto& metrics = result.summary.s4_wait_metrics;
    near(metrics.at("commit_forecast_count"), 2.0,
         "forecast evaluation includes only the two nonterminal committed destinations");
    near(metrics.at("resolved_forecast_count"), 2.0,
         "each committed destination forecast resolves at one actual departure");
    near(metrics.at("censored_forecast_count"), 0.0,
         "completed tiny run leaves no unresolved destination forecast");
    near(metrics.at("actual_post_wait_mean"), 0.0,
         "pre-merge J2 waits and five-second service are not counted as post-service waits");
    for (const auto& row : result.decisions) for (const auto& candidate : row.candidates) {
      require(candidate.s4_wait_prediction_enabled, "ETA mode exposes each candidate's forecast components");
      require(candidate.predicted_entry_wait >= 0.0 && candidate.predicted_merge_wait >= 0.0 &&
                  candidate.predicted_post_service_wait >= 0.0,
              "candidate wait forecasts must be finite nonnegative durations");
      require(std::isfinite(candidate.projected_arrival), "candidate ETA must be finite");
      if (std::string(mode) == "eta_calendar")
        near(candidate.predicted_post_service_wait, 0.0,
             "calendar-only ablation must not silently include queue-count penalties");
    }
  }
}

void served_queue_is_not_charged_as_node_service_again() {
  Graph graph;
  graph.add_node(Node{0, 1, 0.1, 0, 0, {2}});
  graph.add_node(Node{1, 1, 0.1, 0, 1, {2}});
  graph.add_node(Node{2, 4, 0.1, 1, 0, {3}});
  graph.add_node(Node{3, 4, 10.0, 2, 0, {4}});
  graph.add_node(Node{4, 2, 0.0, 3, 0, {}});
  graph.add_edge(Edge{0, 2, 1.0, 1.0});
  graph.add_edge(Edge{1, 2, 1.0, 1.0});
  graph.add_edge(Edge{2, 3, 1.0, 1.0});
  graph.add_edge(Edge{3, 4, 1.0, 1.0});
  graph.set_heuristic({
      {0, 1000, 1.1, 2.2, 13.2},
      {1000, 0, 1.1, 2.2, 13.2},
      {1000, 1000, 0, 1.1, 12.1},
      {1000, 1000, 1000, 0, 11.0},
      {1000, 1000, 1000, 1000, 0},
  });
  const std::vector<EventRuntimeBagRequest> rows{
      {"downstream-service", 11, 0.0, 100.0, 3, 4, "eta-post-service"},
      {"already-serviced", 12, 0.0, 100.0, 2, 4, "eta-post-service"},
      {"candidate", 13, 1.0, 100.0, 0, 4, "eta-post-service"},
  };
  auto old_config = config();
  const auto legacy = EventDrivenJunctionRuntime(graph, old_config).run(rows);
  auto eta_config = old_config; eta_config.s4_wait_estimator = "eta_calendar";
  const auto calendar = EventDrivenJunctionRuntime(graph, eta_config).run(rows);
  auto flow_config = old_config; flow_config.s4_wait_estimator = "eta_flow";
  const auto flow = EventDrivenJunctionRuntime(graph, flow_config).run(rows);
  unchanged_execution(legacy, calendar); unchanged_execution(legacy, flow);
  const auto first_candidate = [](const EventDrivenJunctionResult& result) -> const EventCandidateRecord& {
    for (const auto& row : result.decisions)
      if (row.task_id == 13 && row.current_node == 0 && std::abs(row.event_time - 1.1) < 1.0e-8)
        for (const auto& candidate : row.candidates) if (candidate.next_node == 2) return candidate;
    throw std::runtime_error("the candidate's first direct-neighbour observation must be traced");
  };
  const auto& old_score = first_candidate(legacy);
  const auto& new_score = first_candidate(calendar);
  require(old_score.target_queue_length == 1 && new_score.target_queue_length == 1,
          "counterexample must actually observe a bag waiting after its node service");
  near(old_score.model_score, 14.1, "legacy S4 includes one unit of served-queue pressure");
  near(new_score.model_score, 13.1,
       "calendar mode replaces served-queue count instead of adding another penalty");
  near(new_score.predicted_merge_wait, 0.0, "target's own .1-second operation is already free");
  near(new_score.predicted_post_service_wait, 0.0, "calendar ablation has no post-service estimate");
  near(bag(flow, 13).finish_time, 31.0, "actual downstream ten-second windows remain unchanged");
  near(bag(flow, 13).node_service_time_seconds, 10.2,
       "actual services remain .1 plus .1 plus 10 seconds");
  near(flow.summary.s4_wait_metrics.at("commit_forecast_count"), 3.0,
       "three nonterminal hops create three evaluable destination forecasts");
  near(flow.summary.s4_wait_metrics.at("actual_post_wait_mean"), 5.6,
       "the 16.8-second post-service wait is counted once across three forecasts");
}

void eta_flow_checkpoint_preserves_observations_and_pending_forecasts() {
  auto value = config(); value.s4_wait_estimator = "eta_flow";
  const auto graph = merge_graph();
  EventDrivenJunctionRuntime original(graph, value);
  original.initialize(requests());
  bool reached = false;
  for (int i = 0; i < value.max_events; ++i) {
    const auto boundary = original.peek_safe_boundary();
    require(boundary.has_value(), "checkpoint fixture must retain pending future events");
    if (boundary->next_event_time >= 6.0) { reached = true; break; }
    require(original.process_one_event(), "checkpoint fixture must advance");
  }
  require(reached, "checkpoint occurs after committed departures, before the next service finishes");
  const auto& partial = original.current_result();
  const auto departed = std::count_if(partial.events.begin(), partial.events.end(),
      [](const auto& row) { return row.event == "EDGE_ENTER"; });
  require(departed >= 2, "checkpoint must include real flow observations, not a cold estimator");
  const auto checkpoint = original.capture_state_checkpoint();
  EventDrivenJunctionRuntime restored(graph, value);
  restored.restore_state_checkpoint(checkpoint);
  require(original.deterministic_state_sha256() == restored.deterministic_state_sha256(),
          "checkpoint binds ETA flow and pending prediction state before continuation");
  original.drain(); restored.drain();
  const auto& a = original.finalize(); const auto& b = restored.finalize();
  unchanged_execution(a, b);
  require(a.summary.s4_wait_metrics == b.summary.s4_wait_metrics,
          "restored flow forecasts and their resolved error totals must match exactly");
  require(original.deterministic_replay_hashes().exactly_matches(
              restored.deterministic_replay_hashes()),
          "all deterministic replay hashes must survive an ETA-enabled restore");
}

}  // namespace

int main() {
  try {
    calendar_wait_uses_arrival_and_real_gaps();
    post_service_projection_has_seconds_and_no_extra_node_service();
    causal_departure_statistics_exclude_idle_time_and_notice_stalls();
    legacy_default_and_actual_j2_service_are_unchanged();
    served_queue_is_not_charged_as_node_service_again();
    eta_flow_checkpoint_preserves_observations_and_pending_forecasts();
    std::cout << "G31 wait score: calendar, served queue, J2 execution and flow checkpoint passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "FAIL: " << error.what() << '\n';
    return 1;
  }
}
