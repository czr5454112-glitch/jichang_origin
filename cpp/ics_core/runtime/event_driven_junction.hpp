#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <limits>
#include <map>
#include <queue>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"

namespace czr005::ics {

// G4IRSF11's runtime deliberately owns no A* planner and no global reservation
// table.  A decision reads one junction, its outgoing corridors, and (when
// enabled) a diagnostic summary of the next junction.  Reservations are made
// only for the selected corridor and its destination junction.

enum class JunctionEventType {
  kBagRelease,
  kArriveJunction,
  kJunctionServiceComplete,
  kEdgeEnter,
  kEdgeExit,
  kFault,
  kRepair,
  kLocalQueueUpdate,
  kCongestionBeaconUpdate,
};

inline const char* junction_event_name(JunctionEventType type) {
  switch (type) {
    case JunctionEventType::kBagRelease:
      return "BAG_RELEASE";
    case JunctionEventType::kArriveJunction:
      return "ARRIVE_JUNCTION";
    case JunctionEventType::kJunctionServiceComplete:
      return "JUNCTION_SERVICE_COMPLETE";
    case JunctionEventType::kEdgeEnter:
      return "EDGE_ENTER";
    case JunctionEventType::kEdgeExit:
      return "EDGE_EXIT";
    case JunctionEventType::kFault:
      return "FAULT";
    case JunctionEventType::kRepair:
      return "REPAIR";
    case JunctionEventType::kLocalQueueUpdate:
      return "LOCAL_QUEUE_UPDATE";
    case JunctionEventType::kCongestionBeaconUpdate:
      return "CONGESTION_BEACON_UPDATE";
  }
  return "UNKNOWN";
}

struct EventRuntimeBagRequest {
  std::string segment_id;
  int task_id = -1;
  double release_time = 0.0;
  double deadline = -1.0;
  int start = -1;
  int goal = -1;
  std::string source;
  int runtime_bag_id = -1;  // assigned by run(); original task_id is never rewritten
};

struct EventRuntimeFaultWindow {
  int start = -1;
  int end = -1;
  double fault_time = 0.0;
  double repair_time = 0.0;
  double message_delay = 0.0;
  bool drop_notification = false;
};

struct EventDrivenJunctionConfig {
  std::string queue_discipline = "aging";  // fifo, deadline, aging
  double retry_interval = 0.25;
  double minimum_service_seconds = 1.0e-3;
  double dispatch_headway_seconds = 1.0e-3;
  double pressure_weight = 2.0;
  double calendar_wait_weight = 1.0;
  double history_penalty = 20.0;
  double backtrack_penalty = 40.0;
  double aging_weight = 1.0;
  double starvation_threshold = 120.0;
  int history_limit = 8;
  int max_decisions_per_bag = 512;
  int max_events = 2000000;
  double max_simulation_time = -1.0;
  int trace_limit = 20000;
  int trace_shard_count = 1;
  int trace_shard_index = 0;
  int local_queue_capacity = 0;  // zero means no configured queue cap
  int deadlock_retry_threshold = 8;
  int diagnostic_hops = 2;  // read-only; reservation depth remains exactly one
  bool enable_source_admission = true;
  bool enable_backpressure = true;
  bool enable_pibt_lite = true;
  bool enable_deadlock_escape = true;
  // Controls proactive use of locally advertised fault state.  The physical
  // edge-entry interlock is independent and cannot be disabled.
  bool enable_fault_policy = true;
};

struct EventCandidateRecord {
  int next_node = -1;
  double static_potential = 0.0;
  double travel_time = 0.0;
  int target_queue_length = 0;
  int target_scheduled_incoming = 0;
  double corridor_next_available = 0.0;
  double target_next_available = 0.0;
  bool advertised_fault = false;
  double fault_message_age_seconds = 0.0;
  int recent_visit_count = 0;
  int two_hop_queue_pressure = 0;
  double model_score = 0.0;
  double pre_fault_policy_score = 0.0;
  bool shield_allowed = false;
  std::string shield_reason;
};

struct EventDecisionTraceRow {
  std::uint64_t decision_id = 0;
  std::uint64_t arrive_event_seq = 0;
  double event_time = 0.0;
  int task_id = -1;
  int runtime_bag_id = -1;
  std::string segment_id;
  int current_node = -1;
  int goal_node = -1;
  std::vector<EventCandidateRecord> candidates;
  int model_prediction = -1;
  double model_margin = 0.0;
  bool risk_gate_triggered = false;
  int fallback_selected_next = -1;
  int selected_next = -1;
  std::string decision_source;
  std::string rule_reason;
  int junction_queue_length = 0;
  double junction_next_dispatch_time = 0.0;
  int advertised_faulted_outgoing_count = 0;
  double max_fault_message_age_seconds = 0.0;
  std::vector<int> short_history;
  bool full_astar_used = false;
};

struct EventRuntimeTraceRow {
  std::uint64_t seq = 0;
  std::string event;
  double time = 0.0;
  int task_id = -1;
  int runtime_bag_id = -1;
  std::string segment_id;
  int node = -1;
  int from_node = -1;
  int to_node = -1;
  std::string reason;
  int selected_edge_count = 0;
};

struct EventRuntimeBagResult {
  std::string segment_id;
  int task_id = -1;
  int runtime_bag_id = -1;
  int start = -1;
  int goal = -1;
  int final_node = -1;
  double release_time = 0.0;
  double arrival_time = 0.0;
  double deadline = -1.0;
  std::string source;
  double admitted_time = -1.0;
  double finish_time = -1.0;
  double source_queue_delay = 0.0;
  double total_local_wait = 0.0;
  int decision_count = 0;
  int retry_count = 0;
  int loop_count = 0;
  bool completed = false;
  bool starved = false;
  std::string failure_reason;
  std::vector<int> short_history;
};

struct EventRuntimeSummary {
  int requested_count = 0;
  int completed_count = 0;
  int failed_count = 0;
  int decision_count = 0;
  int event_count = 0;
  int bag_release_event_count = 0;
  int arrive_junction_event_count = 0;
  int junction_service_complete_event_count = 0;
  int edge_enter_event_count = 0;
  int edge_exit_event_count = 0;
  int fault_event_count = 0;
  int repair_event_count = 0;
  int local_queue_update_event_count = 0;
  int congestion_beacon_update_event_count = 0;
  int fault_notification_drop_count = 0;
  // Bags already inside an edge when a fault activates are grandfathered:
  // they are audited, but are not an unsafe-entry violation.
  int physical_fault_window_traversal_count = 0;
  // A true safety violation is a new EDGE_ENTER while the directed edge's
  // physical fault state is active.  The physical shield should keep this 0.
  int physical_fault_edge_entry_violation_count = 0;
  int fault_affected_bag_count = 0;
  int fault_target_edge_candidate_exposure_count = 0;
  int fault_target_edge_attempt_count = 0;
  int physical_fault_interlock_rejection_count = 0;
  int physical_fault_interlock_hold_count = 0;
  int physical_fault_interlock_reroute_count = 0;
  int local_fault_policy_action_count = 0;
  int local_fault_policy_hold_count = 0;
  int local_fault_policy_reroute_count = 0;
  int reservation_conflicts = 0;
  int shield_rejection_count = 0;
  int stale_fault_shield_rejection_count = 0;
  int pibt_lite_handoff_count = 0;
  int deadlock_count = 0;
  int resolved_deadlock_count = 0;
  int unresolved_deadlock_count = 0;
  int deadlock_escape_activation_count = 0;
  int starvation_count = 0;
  int loop_count = 0;
  int runtime_full_astar_calls = 0;
  int global_reservation_scan_count = 0;
  int max_edges_selected_per_arrive = 0;
  int release_selected_edge_count = 0;
  int max_history_observed = 0;
  int max_junction_queue_length = 0;
  int max_source_queue_length = 0;
  int max_local_calendar_intervals = 0;
  int max_corridor_calendar_intervals = 0;
  int max_candidate_count = 0;
  int two_step_reservation_count = 0;
  int diagnostic_hops = 0;
  int decision_trace_seen_count = 0;
  int decision_trace_shard_seen_count = 0;
  int decision_trace_stored_count = 0;
  int hold_trace_stored_count = 0;
  int trace_limit = 0;
  int trace_shard_count = 1;
  int trace_shard_index = 0;
  std::size_t cpp_internal_accounted_bytes = 0;
  double max_individual_wait = 0.0;
  double max_source_queue_delay = 0.0;
  double fairness_jain = 1.0;
  double max_deadlock_duration = 0.0;
  double end_time = 0.0;
  double runtime_seconds = 0.0;
  double decision_latency_us_p50 = 0.0;
  double decision_latency_us_p95 = 0.0;
  double decision_latency_us_p99 = 0.0;
  double event_throughput_per_second = 0.0;
  bool event_limit_reached = false;
  bool time_limit_reached = false;
  bool sensor_loss_mode_used = false;
  bool fault_policy_enabled = true;
  bool decision_trace_truncated = false;
  bool event_trace_truncated = false;
};

struct EventRuntimeJunctionResult {
  int node = -1;
  int final_source_queue_length = 0;
  int final_junction_queue_length = 0;
  int final_service_calendar_intervals = 0;
  int scheduled_incoming = 0;
  double next_dispatch_time = 0.0;
};

struct EventRuntimeFaultAuditRow {
  std::uint64_t seq = 0;
  std::string event;
  std::string phase;
  double time = 0.0;
  int from_node = -1;
  int to_node = -1;
  int physical_active_count = 0;
  int physical_generation = 0;
  int inflight_traversal_count = 0;
  bool notification_dropped = false;
  int task_id = -1;
  int runtime_bag_id = -1;
  std::string segment_id;
  int current_node = -1;
  int intended_next_node = -1;
  int selected_next_node = -1;
  bool fault_policy_enabled = true;
};

struct EventDrivenJunctionResult {
  EventRuntimeSummary summary;
  std::vector<EventRuntimeBagResult> bags;
  std::vector<EventRuntimeTraceRow> events;
  std::vector<EventDecisionTraceRow> decisions;
  std::vector<EventDecisionTraceRow> hold_attempts;
  std::vector<EventRuntimeJunctionResult> junctions;
  std::vector<EventRuntimeFaultAuditRow> fault_events;
};

namespace event_runtime_detail {

constexpr double kEpsilon = 1.0e-9;

inline long long directed_key(int start, int end) {
  return (static_cast<long long>(start) << 32) ^ static_cast<unsigned int>(end);
}

inline long long corridor_key(int left, int right) {
  const int low = std::min(left, right);
  const int high = std::max(left, right);
  return directed_key(low, high);
}

struct CalendarInterval {
  int task_id = -1;
  double start = 0.0;
  double end = 0.0;
};

class LocalCalendar {
 public:
  void purge(double now) {
    intervals_.erase(
        std::remove_if(intervals_.begin(), intervals_.end(), [now](const CalendarInterval& item) {
          return item.end <= now + kEpsilon;
        }),
        intervals_.end());
  }

  [[nodiscard]] bool available(double start, double end, int ignore_task = -1) const {
    if (end <= start) {
      return true;
    }
    for (const auto& item : intervals_) {
      if (ignore_task >= 0 && item.task_id == ignore_task) {
        continue;
      }
      if (start < item.end - kEpsilon && item.start < end - kEpsilon) {
        return false;
      }
    }
    return true;
  }

  [[nodiscard]] double earliest_start(double earliest, double duration) const {
    double candidate = earliest;
    for (const auto& item : intervals_) {
      if (candidate + duration <= item.start + kEpsilon) {
        break;
      }
      if (candidate < item.end - kEpsilon && item.start < candidate + duration - kEpsilon) {
        candidate = item.end;
      }
    }
    return candidate;
  }

  void reserve(int task_id, double start, double end) {
    if (end <= start) {
      return;
    }
    intervals_.push_back(CalendarInterval{task_id, start, end});
    std::sort(intervals_.begin(), intervals_.end(), [](const auto& left, const auto& right) {
      return std::tie(left.start, left.end, left.task_id) <
             std::tie(right.start, right.end, right.task_id);
    });
  }

  [[nodiscard]] int size() const { return static_cast<int>(intervals_.size()); }

 private:
  std::vector<CalendarInterval> intervals_;
};

enum class BagStatus {
  kPendingRelease,
  kSourceQueue,
  kInService,
  kJunctionQueue,
  kInTransit,
  kCompleted,
  kFailed,
};

struct BagState {
  EventRuntimeBagRequest request;
  BagStatus status = BagStatus::kPendingRelease;
  int current = -1;
  int transit_from = -1;
  int transit_to = -1;
  double admitted_time = -1.0;
  double finish_time = -1.0;
  double source_enqueued_at = -1.0;
  double junction_enqueued_at = -1.0;
  double total_wait = 0.0;
  int decision_count = 0;
  int retry_count = 0;
  int loop_count = 0;
  double deadlock_started_at = -1.0;
  std::string failure_reason;
  std::deque<int> history;
};

struct JunctionState {
  std::deque<int> source_queue;
  std::deque<int> queue;
  LocalCalendar service_calendar;
  double next_dispatch_time = 0.0;
  int scheduled_incoming = 0;
  std::uint64_t source_wakeup_generation = 0;
  std::uint64_t junction_wakeup_generation = 0;
  bool source_wakeup_pending = false;
  bool junction_wakeup_pending = false;
  int escape_token_task = -1;
};

struct FaultState {
  int active_count = 0;
  int physical_generation = 0;
};

struct AdvertisedFaultState {
  bool faulted = false;
  int generation = 0;
  double received_at = 0.0;
};

struct RuntimeEvent {
  JunctionEventType type = JunctionEventType::kBagRelease;
  double time = 0.0;
  std::uint64_t seq = 0;
  int task_id = -1;
  int node = -1;
  int from_node = -1;
  int to_node = -1;
  double service_end = 0.0;
  double message_delay = 0.0;
  int message_generation = 0;
  std::uint64_t wakeup_generation = 0;
  bool notification = false;
  bool drop_notification = false;
  bool retry = false;
  std::string reason;
};

inline int event_priority(const RuntimeEvent& event) {
  if ((event.type == JunctionEventType::kFault || event.type == JunctionEventType::kRepair) &&
      !event.notification) {
    return 0;
  }
  if (event.type == JunctionEventType::kFault || event.type == JunctionEventType::kRepair) {
    return 1;
  }
  if (event.type == JunctionEventType::kEdgeExit) {
    return 2;
  }
  if (event.type == JunctionEventType::kJunctionServiceComplete) {
    return 3;
  }
  if (event.type == JunctionEventType::kBagRelease) {
    return 4;
  }
  if (event.type == JunctionEventType::kArriveJunction) {
    return 5;
  }
  if (event.type == JunctionEventType::kEdgeEnter) {
    return 6;
  }
  if (event.type == JunctionEventType::kLocalQueueUpdate) {
    return 7;
  }
  return 8;
}

struct RuntimeEventLater {
  bool operator()(const RuntimeEvent& left, const RuntimeEvent& right) const {
    if (std::abs(left.time - right.time) > kEpsilon) {
      return left.time > right.time;
    }
    const int left_priority = event_priority(left);
    const int right_priority = event_priority(right);
    if (left_priority != right_priority) {
      return left_priority > right_priority;
    }
    return left.seq > right.seq;
  }
};

}  // namespace event_runtime_detail

class EventDrivenJunctionRuntime {
 public:
  explicit EventDrivenJunctionRuntime(const Graph& graph, EventDrivenJunctionConfig config = {})
      : graph_(graph), config_(std::move(config)) {
    validate_config();
  }

  EventDrivenJunctionResult run(const std::vector<EventRuntimeBagRequest>& requests,
                                const std::vector<EventRuntimeFaultWindow>& fault_windows = {}) {
    const auto runtime_started = std::chrono::steady_clock::now();
    reset();
    result_.summary.requested_count = static_cast<int>(requests.size());
    result_.summary.diagnostic_hops = config_.diagnostic_hops;
    result_.summary.trace_limit = config_.trace_limit;
    result_.summary.trace_shard_count = config_.trace_shard_count;
    result_.summary.trace_shard_index = config_.trace_shard_index;
    result_.summary.fault_policy_enabled = config_.enable_fault_policy;

    double latest_release = 0.0;
    int next_runtime_bag_id = 0;
    for (const auto& request : requests) {
      validate_request(request);
      if (segment_runtime_ids_.find(request.segment_id) != segment_runtime_ids_.end()) {
        throw std::invalid_argument("event runtime segment_id values must be unique");
      }
      event_runtime_detail::BagState state;
      state.request = request;
      state.request.runtime_bag_id = next_runtime_bag_id;
      state.current = request.start;
      segment_runtime_ids_.emplace(request.segment_id, next_runtime_bag_id);
      bags_.emplace(next_runtime_bag_id, std::move(state));
      schedule(JunctionEventType::kBagRelease,
               request.release_time,
               next_runtime_bag_id,
               request.start,
               -1,
               -1);
      ++next_runtime_bag_id;
      latest_release = std::max(latest_release, request.release_time);
    }

    for (const auto& window : fault_windows) {
      validate_fault_window(window);
      event_runtime_detail::RuntimeEvent fault;
      fault.type = JunctionEventType::kFault;
      fault.time = window.fault_time;
      fault.from_node = window.start;
      fault.to_node = window.end;
      fault.message_delay = window.message_delay;
      fault.drop_notification = window.drop_notification;
      push_event(std::move(fault));

      event_runtime_detail::RuntimeEvent repair;
      repair.type = JunctionEventType::kRepair;
      repair.time = window.repair_time;
      repair.from_node = window.start;
      repair.to_node = window.end;
      repair.message_delay = window.message_delay;
      repair.drop_notification = window.drop_notification;
      push_event(std::move(repair));
    }

    const double time_limit = config_.max_simulation_time >= 0.0
                                  ? config_.max_simulation_time
                                  : latest_release + 86400.0;
    while (!events_.empty()) {
      if (result_.summary.event_count >= config_.max_events) {
        result_.summary.event_limit_reached = true;
        break;
      }
      auto event = events_.top();
      events_.pop();
      if (event.time > time_limit + event_runtime_detail::kEpsilon) {
        result_.summary.time_limit_reached = true;
        break;
      }
      now_ = event.time;
      ++result_.summary.event_count;
      process_event(event);
    }

    finalize_incomplete();
    build_bag_results();
    build_junction_results();
    finish_summary();
    const std::chrono::duration<double> runtime_elapsed =
        std::chrono::steady_clock::now() - runtime_started;
    result_.summary.runtime_seconds = runtime_elapsed.count();
    result_.summary.event_throughput_per_second =
        runtime_elapsed.count() > 0.0
            ? static_cast<double>(result_.summary.event_count) / runtime_elapsed.count()
            : 0.0;
    return result_;
  }

 private:
  using BagState = event_runtime_detail::BagState;
  using BagStatus = event_runtime_detail::BagStatus;
  using JunctionState = event_runtime_detail::JunctionState;
  using LocalCalendar = event_runtime_detail::LocalCalendar;
  using RuntimeEvent = event_runtime_detail::RuntimeEvent;

  void validate_config() const {
    if (config_.queue_discipline != "fifo" && config_.queue_discipline != "deadline" &&
        config_.queue_discipline != "aging") {
      throw std::invalid_argument("queue_discipline must be fifo, deadline, or aging");
    }
    if (config_.retry_interval <= 0.0 || config_.minimum_service_seconds <= 0.0 ||
        config_.dispatch_headway_seconds < 0.0) {
      throw std::invalid_argument("event runtime time constants must be positive");
    }
    if (config_.history_limit <= 0 || config_.history_limit > 8 ||
        config_.max_decisions_per_bag <= 0 ||
        config_.max_events <= 0 || config_.deadlock_retry_threshold <= 0) {
      throw std::invalid_argument(
          "event runtime integer limits must be positive and history_limit must be <= 8");
    }
    if (config_.diagnostic_hops < 0 || config_.diagnostic_hops > 2) {
      throw std::invalid_argument("diagnostic_hops must be in [0, 2]");
    }
    if (config_.trace_shard_count <= 0 || config_.trace_shard_index < 0 ||
        config_.trace_shard_index >= config_.trace_shard_count) {
      throw std::invalid_argument(
          "trace_shard_count must be positive and trace_shard_index must be in range");
    }
  }

  void validate_request(const EventRuntimeBagRequest& request) const {
    if (request.task_id < 0 || request.start < 0 || request.goal < 0) {
      throw std::invalid_argument("event runtime bag identifiers/nodes must be non-negative");
    }
    if (request.release_time < 0.0) {
      throw std::invalid_argument("event runtime release_time must be non-negative");
    }
    (void)graph_.node(request.start);
    (void)graph_.node(request.goal);
  }

  void validate_fault_window(const EventRuntimeFaultWindow& window) const {
    if (!graph_.has_edge(window.start, window.end)) {
      throw std::invalid_argument("fault window references a missing directed edge");
    }
    if (window.repair_time < window.fault_time || window.message_delay < 0.0) {
      throw std::invalid_argument("fault window times are invalid");
    }
  }

  void reset() {
    result_ = {};
    bags_.clear();
    segment_runtime_ids_.clear();
    junctions_.clear();
    corridors_.clear();
    physical_faults_.clear();
    advertised_faults_.clear();
    fault_affected_bags_.clear();
    events_ = {};
    next_event_seq_ = 1;
    next_decision_id_ = 1;
    now_ = 0.0;
    waits_.clear();
    decision_latencies_us_.clear();
  }

  void schedule(JunctionEventType type,
                double time,
                int task_id,
                int node,
                int from_node,
                int to_node,
                bool retry = false,
                std::uint64_t wakeup_generation = 0,
                double service_end = 0.0) {
    RuntimeEvent event;
    event.type = type;
    event.time = time;
    event.task_id = task_id;
    event.node = node;
    event.from_node = from_node;
    event.to_node = to_node;
    event.retry = retry;
    event.wakeup_generation = wakeup_generation;
    event.service_end = service_end;
    push_event(std::move(event));
  }

  void push_event(RuntimeEvent event) {
    event.seq = next_event_seq_++;
    events_.push(std::move(event));
  }

  void process_event(const RuntimeEvent& event) {
    switch (event.type) {
      case JunctionEventType::kBagRelease:
        ++result_.summary.bag_release_event_count;
        process_release(event);
        break;
      case JunctionEventType::kArriveJunction:
        ++result_.summary.arrive_junction_event_count;
        process_arrive(event);
        break;
      case JunctionEventType::kJunctionServiceComplete:
        ++result_.summary.junction_service_complete_event_count;
        process_service_complete(event);
        break;
      case JunctionEventType::kEdgeEnter:
        ++result_.summary.edge_enter_event_count;
        process_edge_enter(event);
        break;
      case JunctionEventType::kEdgeExit:
        ++result_.summary.edge_exit_event_count;
        process_edge_exit(event);
        break;
      case JunctionEventType::kFault:
        ++result_.summary.fault_event_count;
        process_fault_message(event);
        break;
      case JunctionEventType::kRepair:
        ++result_.summary.repair_event_count;
        process_fault_message(event);
        break;
      case JunctionEventType::kLocalQueueUpdate:
        ++result_.summary.local_queue_update_event_count;
        process_local_queue_update(event);
        break;
      case JunctionEventType::kCongestionBeaconUpdate:
        ++result_.summary.congestion_beacon_update_event_count;
        process_passive_event(event, "bounded_local_congestion_summary");
        break;
    }
  }

  void process_release(const RuntimeEvent& event) {
    auto& controller = junctions_[event.node];
    if (event.retry) {
      if (!controller.source_wakeup_pending ||
          controller.source_wakeup_generation != event.wakeup_generation) {
        return;
      }
      controller.source_wakeup_pending = false;
    } else {
      auto found = bags_.find(event.task_id);
      if (found == bags_.end() || found->second.status != BagStatus::kPendingRelease) {
        return;
      }
      auto& bag = found->second;
      bag.status = BagStatus::kSourceQueue;
      bag.source_enqueued_at = event.time;
      controller.source_queue.push_back(event.task_id);
      update_queue_maxima(controller);
      schedule_passive(JunctionEventType::kLocalQueueUpdate,
                       event.time,
                       event.task_id,
                       event.node,
                       -1,
                       event.node,
                       "source_enqueue");
    }

    const int admitted_task = try_admit_source(event.node, event.time);
    append_event_trace(event,
                       admitted_task,
                       event.node,
                       -1,
                       -1,
                       event.retry ? "source_admission_retry" : "source_release",
                       0);
    if (!controller.source_queue.empty()) {
      const double duration = service_duration(event.node);
      const double calendar_ready = controller.service_calendar.earliest_start(event.time, duration);
      schedule_source_wakeup(event.node,
                             std::max(event.time + config_.retry_interval, calendar_ready));
    }
  }

  int try_admit_source(int node, double time) {
    auto& controller = junctions_[node];
    controller.service_calendar.purge(time);
    if (controller.source_queue.empty()) {
      return -1;
    }
    const std::size_t queue_index = choose_bag(controller.source_queue, time, controller.escape_token_task);
    const int task_id = controller.source_queue[queue_index];
    auto& bag = bags_.at(task_id);
    const double duration = service_duration(node);
    const bool queue_has_room = config_.local_queue_capacity <= 0 ||
                                static_cast<int>(controller.queue.size()) < config_.local_queue_capacity;
    if (!queue_has_room || !controller.service_calendar.available(time, time + duration, task_id)) {
      return -1;
    }

    controller.service_calendar.reserve(task_id, time, time + duration);
    update_calendar_maxima(controller, nullptr);
    controller.source_queue.erase(controller.source_queue.begin() + static_cast<std::ptrdiff_t>(queue_index));
    bag.status = BagStatus::kInService;
    bag.current = node;
    bag.admitted_time = time;
    bag.total_wait += std::max(0.0, time - bag.source_enqueued_at);
    schedule(JunctionEventType::kJunctionServiceComplete,
             time + duration,
             task_id,
             node,
             -1,
             node);
    schedule_passive(JunctionEventType::kLocalQueueUpdate,
                     time,
                     task_id,
                     node,
                     -1,
                     node,
                     "source_dequeue");
    return task_id;
  }

  void process_service_complete(const RuntimeEvent& event) {
    auto found = bags_.find(event.task_id);
    if (found == bags_.end() || found->second.status != BagStatus::kInService) {
      return;
    }
    schedule(JunctionEventType::kArriveJunction,
             event.time,
             event.task_id,
             event.node,
             event.from_node,
             event.to_node);
    append_event_trace(event,
                       event.task_id,
                       event.node,
                       event.from_node,
                       event.to_node,
                       "junction_service_complete",
                       0);
  }

  void process_arrive(const RuntimeEvent& event) {
    auto& controller = junctions_[event.node];
    if (event.retry) {
      if (!controller.junction_wakeup_pending ||
          controller.junction_wakeup_generation != event.wakeup_generation) {
        return;
      }
      controller.junction_wakeup_pending = false;
    } else {
      auto found = bags_.find(event.task_id);
      if (found == bags_.end() || found->second.status != BagStatus::kInService) {
        return;
      }
      auto& bag = found->second;
      if (controller.scheduled_incoming > 0 && event.from_node >= 0) {
        --controller.scheduled_incoming;
      }
      bag.current = event.node;
      remember_node(bag, event.node);
      if (event.node == bag.request.goal) {
        complete_bag(bag, event.time);
        append_event_trace(event,
                           bag.request.runtime_bag_id,
                           event.node,
                           event.from_node,
                           event.node,
                           "goal_reached",
                           0);
        if (!controller.queue.empty()) {
          schedule_junction_wakeup(event.node, event.time);
        }
        return;
      }
      bag.status = BagStatus::kJunctionQueue;
      bag.junction_enqueued_at = event.time;
      controller.queue.push_back(event.task_id);
      update_queue_maxima(controller);
      schedule_passive(JunctionEventType::kLocalQueueUpdate,
                       event.time,
                       event.task_id,
                       event.node,
                       event.from_node,
                       event.node,
                       "junction_enqueue");
    }

    const DispatchResult dispatch = try_dispatch_one(event.node, event.time, event.seq);
    result_.summary.max_edges_selected_per_arrive =
        std::max(result_.summary.max_edges_selected_per_arrive, dispatch.selected_edge_count);
    append_event_trace(event,
                       dispatch.task_id >= 0 ? dispatch.task_id : event.task_id,
                       event.node,
                       event.from_node,
                       dispatch.selected_next,
                       event.retry ? "junction_retry" : "junction_arrival",
                       dispatch.selected_edge_count);
    if (!controller.queue.empty() && !controller.junction_wakeup_pending) {
      schedule_junction_wakeup(event.node, event.time + config_.retry_interval);
    }
  }

  struct DispatchResult {
    int task_id = -1;
    int selected_next = -1;
    int selected_edge_count = 0;
  };

  DispatchResult try_dispatch_one(int node, double time, std::uint64_t arrive_event_seq) {
    auto& controller = junctions_[node];
    if (controller.queue.empty()) {
      return {};
    }
    if (time + event_runtime_detail::kEpsilon < controller.next_dispatch_time) {
      schedule_junction_wakeup(node, controller.next_dispatch_time);
      return {};
    }

    const std::size_t queue_index = choose_bag(controller.queue, time, controller.escape_token_task);
    const auto decision_started = std::chrono::steady_clock::now();
    const int task_id = controller.queue[queue_index];
    auto& bag = bags_.at(task_id);
    if (bag.decision_count >= config_.max_decisions_per_bag) {
      fail_bag(bag, "max_decisions_exceeded", time);
      controller.queue.erase(controller.queue.begin() + static_cast<std::ptrdiff_t>(queue_index));
      schedule_passive(JunctionEventType::kLocalQueueUpdate,
                       time,
                       task_id,
                       node,
                       node,
                       -1,
                       "junction_failure_dequeue");
      if (controller.escape_token_task == task_id) {
        controller.escape_token_task = -1;
      }
      record_decision_latency(decision_started);
      return DispatchResult{task_id, -1, 0};
    }

    controller.service_calendar.purge(time);
    std::vector<int> outgoing = graph_.outgoing(node);
    std::sort(outgoing.begin(), outgoing.end());
    result_.summary.max_candidate_count =
        std::max(result_.summary.max_candidate_count, static_cast<int>(outgoing.size()));

    EventDecisionTraceRow trace;
    trace.decision_id = next_decision_id_++;
    trace.arrive_event_seq = arrive_event_seq;
    trace.event_time = time;
    trace.task_id = bag.request.task_id;
    trace.runtime_bag_id = bag.request.runtime_bag_id;
    trace.segment_id = bag.request.segment_id;
    trace.current_node = node;
    trace.goal_node = bag.request.goal;
    trace.junction_queue_length = static_cast<int>(controller.queue.size());
    trace.junction_next_dispatch_time = controller.next_dispatch_time;
    trace.short_history.assign(bag.history.begin(), bag.history.end());
    trace.full_astar_used = false;

    const bool escape_active = config_.enable_deadlock_escape &&
                               controller.escape_token_task == task_id;
    for (const int candidate : outgoing) {
      trace.candidates.push_back(candidate_record(bag, node, candidate, time, escape_active));
      const auto& record = trace.candidates.back();
      if (record.advertised_fault) {
        ++trace.advertised_faulted_outgoing_count;
      }
      trace.max_fault_message_age_seconds =
          std::max(trace.max_fault_message_age_seconds, record.fault_message_age_seconds);
      const long long physical_key = event_runtime_detail::directed_key(node, candidate);
      const auto physical = physical_faults_.find(physical_key);
      if (physical != physical_faults_.end() && physical->second.active_count > 0) {
        ++result_.summary.fault_target_edge_candidate_exposure_count;
        fault_affected_bags_.insert(bag.request.runtime_bag_id);
        result_.summary.fault_affected_bag_count =
            static_cast<int>(fault_affected_bags_.size());
        append_fault_decision_audit(arrive_event_seq,
                                    "target_edge_candidate_exposure",
                                    time,
                                    bag,
                                    node,
                                    candidate,
                                    -1);
      }
    }

    std::vector<std::size_t> ranking(trace.candidates.size());
    for (std::size_t index = 0; index < ranking.size(); ++index) {
      ranking[index] = index;
    }
    std::sort(ranking.begin(), ranking.end(), [&](std::size_t left, std::size_t right) {
      const auto& left_record = trace.candidates[left];
      const auto& right_record = trace.candidates[right];
      if (left_record.model_score != right_record.model_score) {
        return left_record.model_score < right_record.model_score;
      }
      return left_record.next_node < right_record.next_node;
    });

    std::vector<std::size_t> pre_policy_ranking(ranking.size());
    for (std::size_t index = 0; index < pre_policy_ranking.size(); ++index) {
      pre_policy_ranking[index] = index;
    }
    std::sort(pre_policy_ranking.begin(),
              pre_policy_ranking.end(),
              [&](std::size_t left, std::size_t right) {
                const auto& left_record = trace.candidates[left];
                const auto& right_record = trace.candidates[right];
                if (left_record.pre_fault_policy_score !=
                    right_record.pre_fault_policy_score) {
                  return left_record.pre_fault_policy_score <
                         right_record.pre_fault_policy_score;
                }
                return left_record.next_node < right_record.next_node;
              });
    int pre_policy_prediction = -1;
    std::size_t pre_policy_prediction_index = 0;
    if (!pre_policy_ranking.empty()) {
      pre_policy_prediction_index = pre_policy_ranking.front();
      pre_policy_prediction =
          trace.candidates[pre_policy_prediction_index].next_node;
      const long long intended_key =
          event_runtime_detail::directed_key(node, pre_policy_prediction);
      const auto physical = physical_faults_.find(intended_key);
      if (physical != physical_faults_.end() && physical->second.active_count > 0) {
        ++result_.summary.fault_target_edge_attempt_count;
        append_fault_decision_audit(arrive_event_seq,
                                    "target_edge_attempt",
                                    time,
                                    bag,
                                    node,
                                    pre_policy_prediction,
                                    -1);
      }
    }

    if (!ranking.empty()) {
      trace.model_prediction = trace.candidates[ranking.front()].next_node;
      if (ranking.size() > 1) {
        trace.model_margin = trace.candidates[ranking[1]].model_score -
                             trace.candidates[ranking[0]].model_score;
      } else {
        trace.model_margin = 999.0;
      }
    }

    int selected = -1;
    std::string selected_reason = "no_outgoing_candidate";
    bool physical_interlock_rejected = false;
    int physical_interlock_intended_next = -1;
    bool local_fault_policy_acted = false;
    if (!ranking.empty()) {
      const auto& predicted = trace.candidates[ranking.front()];
      const bool advertised_policy_block =
          config_.enable_fault_policy && predicted.advertised_fault;
      if (predicted.shield_allowed && !advertised_policy_block) {
        selected = predicted.next_node;
        selected_reason = "predicted_candidate_allowed";
      } else {
        trace.risk_gate_triggered = true;
        if (!predicted.shield_allowed) {
          ++result_.summary.shield_rejection_count;
          if (predicted.shield_reason == "physical_fault" && !predicted.advertised_fault) {
            ++result_.summary.stale_fault_shield_rejection_count;
          }
        }
        if (predicted.shield_reason == "physical_fault") {
          physical_interlock_rejected = true;
          physical_interlock_intended_next = predicted.next_node;
          ++result_.summary.physical_fault_interlock_rejection_count;
          append_fault_decision_audit(arrive_event_seq,
                                      "physical_fault_interlock_rejection",
                                      time,
                                      bag,
                                      node,
                                      predicted.next_node,
                                      -1);
          selected_reason = "physical_fault_interlock_hold";
        } else {
          selected_reason = advertised_policy_block ? "advertised_fault_hold"
                                                    : predicted.shield_reason;
        }
        const bool may_reroute_fault =
            !physical_interlock_rejected || config_.enable_fault_policy;
        if (config_.enable_pibt_lite && may_reroute_fault) {
          for (std::size_t rank = 1; rank < ranking.size(); ++rank) {
            const auto& alternative = trace.candidates[ranking[rank]];
            const bool alternative_advertised_block =
                config_.enable_fault_policy && alternative.advertised_fault;
            if (alternative.shield_allowed && !alternative_advertised_block) {
              selected = alternative.next_node;
              trace.fallback_selected_next = selected;
              selected_reason = physical_interlock_rejected
                                    ? "physical_fault_interlock_pibt_handoff"
                                    : "pibt_lite_safe_handoff";
              ++result_.summary.pibt_lite_handoff_count;
              break;
            }
          }
        }
      }
    }

    if (physical_interlock_rejected) {
      if (selected >= 0) {
        ++result_.summary.physical_fault_interlock_reroute_count;
        append_fault_decision_audit(arrive_event_seq,
                                    "physical_fault_interlock_reroute",
                                    time,
                                    bag,
                                    node,
                                    physical_interlock_intended_next,
                                    selected);
      } else {
        ++result_.summary.physical_fault_interlock_hold_count;
        append_fault_decision_audit(arrive_event_seq,
                                    "physical_fault_interlock_hold",
                                    time,
                                    bag,
                                    node,
                                    physical_interlock_intended_next,
                                    -1);
      }
    }

    if (config_.enable_fault_policy && pre_policy_prediction >= 0) {
      const auto& pre_policy_candidate =
          trace.candidates[pre_policy_prediction_index];
      if (pre_policy_candidate.advertised_fault && selected != pre_policy_prediction) {
        local_fault_policy_acted = true;
        ++result_.summary.local_fault_policy_action_count;
        if (selected >= 0) {
          ++result_.summary.local_fault_policy_reroute_count;
          append_fault_decision_audit(arrive_event_seq,
                                      "local_fault_policy_reroute",
                                      time,
                                      bag,
                                      node,
                                      pre_policy_prediction,
                                      selected);
        } else {
          ++result_.summary.local_fault_policy_hold_count;
          append_fault_decision_audit(arrive_event_seq,
                                      "local_fault_policy_hold",
                                      time,
                                      bag,
                                      node,
                                      pre_policy_prediction,
                                      -1);
        }
      }
    }

    ++bag.decision_count;
    ++result_.summary.decision_count;
    trace.selected_next = selected;
    if (selected >= 0) {
      trace.decision_source = local_fault_policy_acted
                                  ? "local_fault_policy"
                              : physical_interlock_rejected
                                  ? "physical_fault_interlock"
                              : escape_active
                                  ? "deadlock_escape"
                              : (selected == trace.model_prediction
                                     ? "local_static_potential"
                                     : "local_pibt_lite_shield");
      trace.rule_reason = selected_reason;
      dispatch_selected_edge(bag, node, selected, time);
      controller.queue.erase(controller.queue.begin() + static_cast<std::ptrdiff_t>(queue_index));
      schedule_passive(JunctionEventType::kLocalQueueUpdate,
                       time,
                       task_id,
                       node,
                       node,
                       selected,
                       "junction_dequeue");
      controller.next_dispatch_time = time + config_.dispatch_headway_seconds;
      if (bag.deadlock_started_at >= 0.0) {
        ++result_.summary.resolved_deadlock_count;
        result_.summary.max_deadlock_duration =
            std::max(result_.summary.max_deadlock_duration, time - bag.deadlock_started_at);
        bag.deadlock_started_at = -1.0;
      }
      if (controller.escape_token_task == task_id) {
        controller.escape_token_task = -1;
      }
    } else {
      ++bag.retry_count;
      trace.decision_source = local_fault_policy_acted
                                  ? "local_fault_policy_hold"
                              : physical_interlock_rejected
                                  ? "physical_fault_interlock_hold"
                              : escape_active ? "deadlock_escape_hold" : "local_hold";
      trace.rule_reason = selected_reason;
      if (bag.retry_count >= config_.deadlock_retry_threshold && bag.deadlock_started_at < 0.0) {
        bag.deadlock_started_at = time;
        ++result_.summary.deadlock_count;
        if (config_.enable_deadlock_escape) {
          controller.escape_token_task = task_id;
          ++result_.summary.deadlock_escape_activation_count;
        }
      }
      double earliest_resource_retry = std::numeric_limits<double>::infinity();
      for (const auto& candidate : trace.candidates) {
        const double corridor_ready = candidate.corridor_next_available;
        const double target_departure_ready = candidate.target_next_available - candidate.travel_time;
        const double resource_ready = std::max(corridor_ready, target_departure_ready);
        if (resource_ready > time + event_runtime_detail::kEpsilon) {
          earliest_resource_retry = std::min(earliest_resource_retry, resource_ready);
        }
      }
      const double retry_time = std::isfinite(earliest_resource_retry)
                                    ? std::max(time + config_.retry_interval,
                                               earliest_resource_retry)
                                    : time + config_.retry_interval;
      schedule_junction_wakeup(node, retry_time);
    }

    append_decision_trace(std::move(trace), selected >= 0);
    record_decision_latency(decision_started);
    return DispatchResult{task_id, selected, selected >= 0 ? 1 : 0};
  }

  EventCandidateRecord candidate_record(const BagState& bag,
                                        int current,
                                        int candidate,
                                        double time,
                                        bool escape_active) {
    EventCandidateRecord record;
    record.next_node = candidate;
    const auto& edge = graph_.edge(current, candidate);
    record.travel_time = std::max(edge.travel_time(), config_.minimum_service_seconds);
    record.static_potential = static_potential(candidate, bag.request.goal);

    auto& target = junctions_[candidate];
    auto& corridor = corridors_[event_runtime_detail::corridor_key(current, candidate)];
    corridor.purge(time);
    target.service_calendar.purge(time);
    record.target_queue_length = static_cast<int>(target.queue.size());
    record.target_scheduled_incoming = target.scheduled_incoming;
    record.corridor_next_available = corridor.earliest_start(time, record.travel_time);
    const double service = service_duration(candidate);
    record.target_next_available =
        target.service_calendar.earliest_start(time + record.travel_time, service);

    const long long edge_key = event_runtime_detail::directed_key(current, candidate);
    const auto advertised = advertised_faults_.find(edge_key);
    if (config_.enable_fault_policy && advertised != advertised_faults_.end()) {
      record.advertised_fault = advertised->second.faulted;
      record.fault_message_age_seconds = std::max(0.0, time - advertised->second.received_at);
    }
    record.recent_visit_count = recent_visit_count(bag, candidate);
    if (config_.diagnostic_hops >= 2) {
      for (const int downstream : graph_.outgoing(candidate)) {
        const auto found = junctions_.find(downstream);
        if (found != junctions_.end()) {
          record.two_hop_queue_pressure += static_cast<int>(found->second.queue.size()) +
                                           found->second.scheduled_incoming;
        }
      }
    }

    const double corridor_wait = std::max(0.0, record.corridor_next_available - time);
    const double target_wait =
        std::max(0.0, record.target_next_available - (time + record.travel_time));
    const double pressure = static_cast<double>(record.target_queue_length +
                                                record.target_scheduled_incoming);
    record.pre_fault_policy_score =
        record.static_potential + record.travel_time +
        config_.calendar_wait_weight * (corridor_wait + target_wait) +
        (config_.enable_backpressure ? config_.pressure_weight * pressure : 0.0) +
        config_.history_penalty * static_cast<double>(record.recent_visit_count);
    if (bag.history.size() >= 2 && candidate == bag.history[bag.history.size() - 2]) {
      record.pre_fault_policy_score += config_.backtrack_penalty;
    }
    if (escape_active) {
      // The escape token changes only local priority.  It never bypasses the
      // physical shield or reserves more than one edge.
      record.pre_fault_policy_score -= 0.5 * config_.history_penalty;
    }
    record.model_score = record.pre_fault_policy_score;
    if (config_.enable_fault_policy && record.advertised_fault) {
      record.model_score += 1.0e12;
    }

    record.shield_reason = shield_reason(bag, current, candidate, time);
    record.shield_allowed = record.shield_reason == "allowed";
    return record;
  }

  std::string shield_reason(const BagState& bag,
                            int current,
                            int candidate,
                            double time) {
    // A terminal node is safe only when it is this bag's actual goal.  This
    // is a one-hop topology check on the candidate itself: it needs neither
    // a future route nor a global search, and prevents local backpressure from
    // diverting traffic into another terminal sink under high concurrency.
    if (candidate != bag.request.goal && graph_.outgoing(candidate).empty()) {
      return "dead_end_not_goal";
    }
    const auto& candidate_outgoing = graph_.outgoing(candidate);
    if (candidate != bag.request.goal && !candidate_outgoing.empty() &&
        std::all_of(candidate_outgoing.begin(),
                    candidate_outgoing.end(),
                    [&](int successor) {
                      return successor != bag.request.goal &&
                             graph_.outgoing(successor).empty();
                    })) {
      return "terminal_successor_trap_not_goal";
    }

    const long long directed = event_runtime_detail::directed_key(current, candidate);
    const auto physical = physical_faults_.find(directed);
    if (physical != physical_faults_.end() && physical->second.active_count > 0) {
      return "physical_fault";
    }

    const auto& edge = graph_.edge(current, candidate);
    const double travel = std::max(edge.travel_time(), config_.minimum_service_seconds);
    auto& corridor = corridors_[event_runtime_detail::corridor_key(current, candidate)];
    corridor.purge(time);
    if (!corridor.available(time, time + travel, bag.request.runtime_bag_id)) {
      return "corridor_busy";
    }

    auto& target = junctions_[candidate];
    target.service_calendar.purge(time);
    const double service_start = time + travel;
    const double service_end = service_start + service_duration(candidate);
    if (!target.service_calendar.available(service_start,
                                            service_end,
                                            bag.request.runtime_bag_id)) {
      return "destination_calendar_busy";
    }
    if (config_.local_queue_capacity > 0 && candidate != bag.request.goal &&
        static_cast<int>(target.queue.size()) + target.scheduled_incoming >=
            config_.local_queue_capacity) {
      return "destination_queue_full";
    }
    return "allowed";
  }

  void dispatch_selected_edge(BagState& bag, int current, int selected, double time) {
    const auto& edge = graph_.edge(current, selected);
    const double travel = std::max(edge.travel_time(), config_.minimum_service_seconds);
    const double exit_time = time + travel;
    const double service_end = exit_time + service_duration(selected);
    auto& corridor = corridors_[event_runtime_detail::corridor_key(current, selected)];
    auto& target = junctions_[selected];
    if (!corridor.available(time, exit_time, bag.request.runtime_bag_id) ||
        !target.service_calendar.available(exit_time,
                                           service_end,
                                           bag.request.runtime_bag_id)) {
      ++result_.summary.reservation_conflicts;
      throw std::logic_error("local shield/reservation state diverged");
    }
    corridor.reserve(bag.request.runtime_bag_id, time, exit_time);
    target.service_calendar.reserve(bag.request.runtime_bag_id, exit_time, service_end);
    ++target.scheduled_incoming;
    update_calendar_maxima(target, &corridor);

    bag.total_wait += std::max(0.0, time - bag.junction_enqueued_at);
    bag.status = BagStatus::kInTransit;
    bag.transit_from = current;
    bag.transit_to = selected;
    schedule_passive(JunctionEventType::kEdgeEnter,
                     time,
                     bag.request.runtime_bag_id,
                     current,
                     current,
                     selected,
                     "one_step_reservation_committed");
    schedule(JunctionEventType::kEdgeExit,
             exit_time,
             bag.request.runtime_bag_id,
             selected,
             current,
             selected,
             false,
             0,
             service_end);
  }

  void process_edge_enter(const RuntimeEvent& event) {
    const auto found = bags_.find(event.task_id);
    const bool valid_entry =
        found != bags_.end() && found->second.status == BagStatus::kInTransit &&
        found->second.transit_from == event.from_node &&
        found->second.transit_to == event.to_node;
    if (valid_entry) {
      const long long key =
          event_runtime_detail::directed_key(event.from_node, event.to_node);
      const auto physical = physical_faults_.find(key);
      if (physical != physical_faults_.end() && physical->second.active_count > 0) {
        ++result_.summary.physical_fault_edge_entry_violation_count;
        append_fault_audit(event,
                           "unsafe_edge_entry",
                           physical->second.active_count,
                           physical->second.physical_generation,
                           0,
                           false);
      }
    }
    process_passive_event(event, "one_step_corridor_entry");
  }

  void process_edge_exit(const RuntimeEvent& event) {
    auto found = bags_.find(event.task_id);
    if (found == bags_.end() || found->second.status != BagStatus::kInTransit ||
        found->second.transit_from != event.from_node ||
        found->second.transit_to != event.to_node) {
      return;
    }
    auto& bag = found->second;
    bag.current = event.to_node;
    bag.status = BagStatus::kInService;
    schedule(JunctionEventType::kJunctionServiceComplete,
             event.service_end,
             event.task_id,
             event.to_node,
             event.from_node,
             event.to_node);
    schedule_junction_wakeup(event.from_node, event.time);
    append_event_trace(event,
                       event.task_id,
                       event.to_node,
                       event.from_node,
                       event.to_node,
                       "edge_traversal_complete",
                       0);
  }

  void process_local_queue_update(const RuntimeEvent& event) {
    append_event_trace(event,
                       event.task_id,
                       event.node,
                       event.from_node,
                       event.to_node,
                       event.reason.empty() ? "local_queue_change" : event.reason,
                       0);
    schedule_passive(JunctionEventType::kCongestionBeaconUpdate,
                     event.time,
                     event.task_id,
                     event.node,
                     event.from_node,
                     event.to_node,
                     "queue_change_beacon");
  }

  void process_passive_event(const RuntimeEvent& event, const std::string& default_reason) {
    append_event_trace(event,
                       event.task_id,
                       event.node,
                       event.from_node,
                       event.to_node,
                       event.reason.empty() ? default_reason : event.reason,
                       0);
  }

  void schedule_passive(JunctionEventType type,
                        double time,
                        int task_id,
                        int node,
                        int from_node,
                        int to_node,
                        const std::string& reason) {
    RuntimeEvent event;
    event.type = type;
    event.time = time;
    event.task_id = task_id;
    event.node = node;
    event.from_node = from_node;
    event.to_node = to_node;
    event.reason = reason;
    push_event(std::move(event));
  }

  void process_fault_message(const RuntimeEvent& event) {
    const long long key = event_runtime_detail::directed_key(event.from_node, event.to_node);
    if (event.notification) {
      if (config_.enable_fault_policy) {
        auto& advertised = advertised_faults_[key];
        if (event.message_generation >= advertised.generation) {
          advertised.generation = event.message_generation;
          advertised.faulted = event.type == JunctionEventType::kFault;
          advertised.received_at = event.time;
        }
        schedule_junction_wakeup(event.from_node, event.time);
      }
      append_event_trace(event,
                         -1,
                         event.from_node,
                         event.from_node,
                         event.to_node,
                         "local_message_delivery",
                         0);
      const auto physical = physical_faults_.find(key);
      append_fault_audit(event,
                         "local_message_delivery",
                         physical == physical_faults_.end() ? 0 : physical->second.active_count,
                         event.message_generation,
                         0,
                         false);
      return;
    }

    auto& physical = physical_faults_[key];
    if (event.type == JunctionEventType::kFault) {
      ++physical.active_count;
    } else {
      physical.active_count = std::max(0, physical.active_count - 1);
    }
    ++physical.physical_generation;
    int inflight_traversals = 0;
    if (event.type == JunctionEventType::kFault) {
      for (const auto& entry : bags_) {
        const auto& bag = entry.second;
        if (bag.status == BagStatus::kInTransit && bag.transit_from == event.from_node &&
            bag.transit_to == event.to_node) {
          ++inflight_traversals;
        }
      }
      result_.summary.physical_fault_window_traversal_count += inflight_traversals;
    }
    append_fault_audit(event,
                       "physical_state_change",
                       physical.active_count,
                       physical.physical_generation,
                       inflight_traversals,
                       event.drop_notification);
    if (event.drop_notification) {
      ++result_.summary.fault_notification_drop_count;
      result_.summary.sensor_loss_mode_used = true;
      append_fault_audit(event,
                         "notification_dropped",
                         physical.active_count,
                         physical.physical_generation,
                         0,
                         true);
    } else if (event.message_delay <= event_runtime_detail::kEpsilon) {
      if (config_.enable_fault_policy) {
        auto& advertised = advertised_faults_[key];
        advertised.generation = physical.physical_generation;
        advertised.faulted = physical.active_count > 0;
        advertised.received_at = event.time;
      }
      append_fault_audit(event,
                         "local_message_delivery",
                         physical.active_count,
                         physical.physical_generation,
                         0,
                         false);
    } else {
      RuntimeEvent notification = event;
      notification.time = event.time + event.message_delay;
      notification.notification = true;
      notification.message_generation = physical.physical_generation;
      notification.type = physical.active_count > 0 ? JunctionEventType::kFault
                                                     : JunctionEventType::kRepair;
      push_event(std::move(notification));
    }
    schedule_junction_wakeup(event.from_node, event.time);
    append_event_trace(event,
                       -1,
                       event.from_node,
                       event.from_node,
                       event.to_node,
                       "physical_state_change",
                       0);
  }

  void append_fault_audit(const RuntimeEvent& event,
                          const std::string& phase,
                          int physical_active_count,
                          int physical_generation,
                          int inflight_traversal_count,
                          bool notification_dropped) {
    EventRuntimeFaultAuditRow row;
    row.seq = event.seq;
    row.event = junction_event_name(event.type);
    row.phase = phase;
    row.time = event.time;
    row.from_node = event.from_node;
    row.to_node = event.to_node;
    row.physical_active_count = physical_active_count;
    row.physical_generation = physical_generation;
    row.inflight_traversal_count = inflight_traversal_count;
    row.notification_dropped = notification_dropped;
    row.current_node = event.node;
    row.intended_next_node = event.to_node;
    row.fault_policy_enabled = config_.enable_fault_policy;
    const auto bag = bags_.find(event.task_id);
    if (bag != bags_.end()) {
      row.task_id = bag->second.request.task_id;
      row.runtime_bag_id = bag->second.request.runtime_bag_id;
      row.segment_id = bag->second.request.segment_id;
    }
    result_.fault_events.push_back(std::move(row));
  }

  void append_fault_decision_audit(std::uint64_t arrive_event_seq,
                                   const std::string& phase,
                                   double time,
                                   const BagState& bag,
                                   int current,
                                   int intended_next,
                                   int selected_next) {
    const long long key = event_runtime_detail::directed_key(current, intended_next);
    const auto physical = physical_faults_.find(key);
    EventRuntimeFaultAuditRow row;
    row.seq = arrive_event_seq;
    row.event = "ARRIVE_JUNCTION";
    row.phase = phase;
    row.time = time;
    row.from_node = current;
    row.to_node = intended_next;
    row.physical_active_count =
        physical == physical_faults_.end() ? 0 : physical->second.active_count;
    row.physical_generation =
        physical == physical_faults_.end() ? 0 : physical->second.physical_generation;
    row.task_id = bag.request.task_id;
    row.runtime_bag_id = bag.request.runtime_bag_id;
    row.segment_id = bag.request.segment_id;
    row.current_node = current;
    row.intended_next_node = intended_next;
    row.selected_next_node = selected_next;
    row.fault_policy_enabled = config_.enable_fault_policy;
    result_.fault_events.push_back(std::move(row));
  }

  void schedule_source_wakeup(int node, double time) {
    auto& controller = junctions_[node];
    if (controller.source_wakeup_pending) {
      return;
    }
    controller.source_wakeup_pending = true;
    const auto generation = ++controller.source_wakeup_generation;
    schedule(JunctionEventType::kBagRelease,
             time,
             -1,
             node,
             -1,
             -1,
             true,
             generation);
  }

  void schedule_junction_wakeup(int node, double time) {
    auto& controller = junctions_[node];
    if (controller.queue.empty()) {
      return;
    }
    if (controller.junction_wakeup_pending) {
      return;
    }
    controller.junction_wakeup_pending = true;
    const auto generation = ++controller.junction_wakeup_generation;
    schedule(JunctionEventType::kArriveJunction,
             time,
             -1,
             node,
             -1,
             node,
             true,
             generation);
  }

  std::size_t choose_bag(const std::deque<int>& queue,
                         double time,
                         int escape_token_task) const {
    if (queue.empty()) {
      throw std::logic_error("cannot choose from an empty local queue");
    }
    for (std::size_t index = 0; index < queue.size(); ++index) {
      if (queue[index] == escape_token_task) {
        return index;
      }
    }

    std::size_t best = 0;
    for (std::size_t index = 1; index < queue.size(); ++index) {
      if (bag_priority(bags_.at(queue[index]), time) < bag_priority(bags_.at(queue[best]), time)) {
        best = index;
      } else if (bag_priority(bags_.at(queue[index]), time) ==
                     bag_priority(bags_.at(queue[best]), time) &&
                 queue[index] < queue[best]) {
        best = index;
      }
    }
    return best;
  }

  double bag_priority(const BagState& bag, double time) const {
    const double enqueued = bag.status == BagStatus::kSourceQueue ? bag.source_enqueued_at
                                                                 : bag.junction_enqueued_at;
    if (config_.queue_discipline == "fifo") {
      return enqueued;
    }
    const double deadline = bag.request.deadline >= 0.0
                                ? bag.request.deadline
                                : std::numeric_limits<double>::max() / 4.0;
    if (config_.queue_discipline == "deadline") {
      return deadline;
    }
    return deadline - config_.aging_weight * std::max(0.0, time - enqueued);
  }

  double service_duration(int node) const {
    return std::max(graph_.service_time(node), config_.minimum_service_seconds);
  }

  double static_potential(int node, int goal) const {
    // Legacy map2 uses a large sentinel on sink-node diagonal cells.  Reaching
    // the actual goal is nevertheless zero remaining cost by definition; not
    // normalising this cell makes a local policy walk past the sink and loop.
    if (node == goal) {
      return 0.0;
    }
    try {
      const double value = graph_.heuristic(node, goal);
      if (std::isfinite(value)) {
        return value;
      }
    } catch (const std::exception&) {
      // A coordinate potential is still static metadata and performs no graph
      // search.  It is used only for hand-built tests without a matrix.
    }
    const auto& from = graph_.node(node);
    const auto& to = graph_.node(goal);
    const double dx = static_cast<double>(from.x - to.x);
    const double dy = static_cast<double>(from.y - to.y);
    return std::sqrt(dx * dx + dy * dy);
  }

  int recent_visit_count(const BagState& bag, int node) const {
    return static_cast<int>(std::count(bag.history.begin(), bag.history.end(), node));
  }

  void remember_node(BagState& bag, int node) {
    if (recent_visit_count(bag, node) > 0) {
      ++bag.loop_count;
      ++result_.summary.loop_count;
    }
    bag.history.push_back(node);
    while (static_cast<int>(bag.history.size()) > config_.history_limit) {
      bag.history.pop_front();
    }
    result_.summary.max_history_observed =
        std::max(result_.summary.max_history_observed, static_cast<int>(bag.history.size()));
  }

  void complete_bag(BagState& bag, double time) {
    bag.status = BagStatus::kCompleted;
    bag.finish_time = time;
    record_wait_outcome(bag, time);
  }

  void fail_bag(BagState& bag, const std::string& reason, double time) {
    if (bag.status == BagStatus::kSourceQueue && bag.source_enqueued_at >= 0.0) {
      bag.total_wait += std::max(0.0, time - bag.source_enqueued_at);
    } else if (bag.status == BagStatus::kJunctionQueue && bag.junction_enqueued_at >= 0.0) {
      bag.total_wait += std::max(0.0, time - bag.junction_enqueued_at);
    }
    bag.status = BagStatus::kFailed;
    bag.failure_reason = reason;
    if (bag.deadlock_started_at >= 0.0) {
      ++result_.summary.unresolved_deadlock_count;
      result_.summary.max_deadlock_duration =
          std::max(result_.summary.max_deadlock_duration, time - bag.deadlock_started_at);
    }
    record_wait_outcome(bag, time);
  }

  void record_wait_outcome(BagState& bag, double time) {
    const double current_queue_wait = bag.status == BagStatus::kSourceQueue && bag.source_enqueued_at >= 0.0
                                          ? std::max(0.0, time - bag.source_enqueued_at)
                                          : (bag.status == BagStatus::kJunctionQueue &&
                                                     bag.junction_enqueued_at >= 0.0
                                                 ? std::max(0.0, time - bag.junction_enqueued_at)
                                                 : 0.0);
    const double wait = bag.total_wait + current_queue_wait;
    waits_.push_back(wait);
    result_.summary.max_individual_wait = std::max(result_.summary.max_individual_wait, wait);
    if (wait > config_.starvation_threshold) {
      ++result_.summary.starvation_count;
    }
  }

  void finalize_incomplete() {
    for (auto& entry : bags_) {
      auto& bag = entry.second;
      if (bag.status == BagStatus::kCompleted || bag.status == BagStatus::kFailed) {
        continue;
      }
      const std::string reason = result_.summary.event_limit_reached
                                     ? "event_limit_reached"
                                     : (result_.summary.time_limit_reached ? "time_limit_reached"
                                                                          : "event_queue_exhausted");
      fail_bag(bag, reason, now_);
    }
  }

  void build_bag_results() {
    std::vector<int> task_ids;
    task_ids.reserve(bags_.size());
    for (const auto& entry : bags_) {
      task_ids.push_back(entry.first);
    }
    std::sort(task_ids.begin(), task_ids.end());
    for (const int task_id : task_ids) {
      const auto& bag = bags_.at(task_id);
      EventRuntimeBagResult row;
      row.segment_id = bag.request.segment_id;
      row.task_id = bag.request.task_id;
      row.runtime_bag_id = bag.request.runtime_bag_id;
      row.start = bag.request.start;
      row.goal = bag.request.goal;
      row.final_node = bag.current;
      row.release_time = bag.request.release_time;
      row.arrival_time = bag.request.release_time;
      row.deadline = bag.request.deadline;
      row.source = bag.request.source;
      row.admitted_time = bag.admitted_time;
      row.finish_time = bag.finish_time;
      row.source_queue_delay = bag.admitted_time >= 0.0
                                   ? bag.admitted_time - bag.request.release_time
                                   : std::max(0.0, now_ - bag.request.release_time);
      row.total_local_wait = bag.total_wait;
      row.decision_count = bag.decision_count;
      row.retry_count = bag.retry_count;
      row.loop_count = bag.loop_count;
      row.completed = bag.status == BagStatus::kCompleted;
      row.starved = bag.total_wait > config_.starvation_threshold;
      row.failure_reason = bag.failure_reason;
      row.short_history.assign(bag.history.begin(), bag.history.end());
      result_.summary.max_source_queue_delay =
          std::max(result_.summary.max_source_queue_delay, row.source_queue_delay);
      result_.bags.push_back(std::move(row));
    }
  }

  void build_junction_results() {
    std::vector<int> nodes;
    nodes.reserve(junctions_.size());
    for (const auto& entry : junctions_) {
      nodes.push_back(entry.first);
    }
    std::sort(nodes.begin(), nodes.end());
    for (const int node : nodes) {
      auto& controller = junctions_.at(node);
      controller.service_calendar.purge(now_);
      result_.junctions.push_back(EventRuntimeJunctionResult{
          node,
          static_cast<int>(controller.source_queue.size()),
          static_cast<int>(controller.queue.size()),
          controller.service_calendar.size(),
          controller.scheduled_incoming,
          controller.next_dispatch_time});
    }
  }

  void finish_summary() {
    for (const auto& entry : bags_) {
      if (entry.second.status == BagStatus::kCompleted) {
        ++result_.summary.completed_count;
      } else {
        ++result_.summary.failed_count;
      }
    }
    if (!waits_.empty()) {
      double sum = 0.0;
      double squared_sum = 0.0;
      for (const double wait : waits_) {
        sum += wait;
        squared_sum += wait * wait;
      }
      result_.summary.fairness_jain = squared_sum <= event_runtime_detail::kEpsilon
                                          ? 1.0
                                          : (sum * sum) /
                                                (static_cast<double>(waits_.size()) * squared_sum);
    }
    result_.summary.end_time = now_;
    if (!decision_latencies_us_.empty()) {
      std::sort(decision_latencies_us_.begin(), decision_latencies_us_.end());
      result_.summary.decision_latency_us_p50 = percentile(decision_latencies_us_, 0.50);
      result_.summary.decision_latency_us_p95 = percentile(decision_latencies_us_, 0.95);
      result_.summary.decision_latency_us_p99 = percentile(decision_latencies_us_, 0.99);
    }
    std::size_t accounted = sizeof(*this);
    accounted += bags_.size() * sizeof(BagState);
    accounted += junctions_.size() * sizeof(JunctionState);
    accounted += corridors_.size() * sizeof(LocalCalendar);
    accounted += physical_faults_.size() * sizeof(event_runtime_detail::FaultState);
    accounted += advertised_faults_.size() * sizeof(event_runtime_detail::AdvertisedFaultState);
    accounted += fault_affected_bags_.size() * sizeof(int);
    accounted += result_.bags.capacity() * sizeof(EventRuntimeBagResult);
    accounted += result_.events.capacity() * sizeof(EventRuntimeTraceRow);
    accounted += result_.decisions.capacity() * sizeof(EventDecisionTraceRow);
    accounted += result_.hold_attempts.capacity() * sizeof(EventDecisionTraceRow);
    accounted += result_.fault_events.capacity() * sizeof(EventRuntimeFaultAuditRow);
    result_.summary.cpp_internal_accounted_bytes = accounted;
  }

  void record_decision_latency(std::chrono::steady_clock::time_point started) {
    const std::chrono::duration<double, std::micro> elapsed =
        std::chrono::steady_clock::now() - started;
    decision_latencies_us_.push_back(elapsed.count());
  }

  static double percentile(const std::vector<double>& sorted_values, double quantile) {
    if (sorted_values.empty()) {
      return 0.0;
    }
    const double position = quantile * static_cast<double>(sorted_values.size() - 1);
    const auto lower = static_cast<std::size_t>(std::floor(position));
    const auto upper = static_cast<std::size_t>(std::ceil(position));
    const double fraction = position - static_cast<double>(lower);
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction;
  }

  void append_event_trace(const RuntimeEvent& event,
                          int task_id,
                          int node,
                          int from,
                          int to,
                          const std::string& reason,
                          int selected_edges) {
    if (!trace_available(result_.events.size())) {
      result_.summary.event_trace_truncated = true;
      return;
    }
    EventRuntimeTraceRow row;
    row.seq = event.seq;
    row.event = junction_event_name(event.type);
    row.time = event.time;
    row.task_id = -1;
    row.runtime_bag_id = task_id;
    const auto bag = bags_.find(task_id);
    if (bag != bags_.end()) {
      row.task_id = bag->second.request.task_id;
      row.segment_id = bag->second.request.segment_id;
    }
    row.node = node;
    row.from_node = from;
    row.to_node = to;
    row.reason = reason;
    row.selected_edge_count = selected_edges;
    result_.events.push_back(std::move(row));
  }

  void append_decision_trace(EventDecisionTraceRow row, bool selected_edge) {
    ++result_.summary.decision_trace_seen_count;
    const int shard = ((row.task_id % config_.trace_shard_count) + config_.trace_shard_count) %
                      config_.trace_shard_count;
    if (shard != config_.trace_shard_index) {
      return;
    }
    ++result_.summary.decision_trace_shard_seen_count;
    const std::size_t total_rows = result_.decisions.size() + result_.hold_attempts.size();
    if (!trace_available(total_rows)) {
      result_.summary.decision_trace_truncated = true;
      return;
    }
    if (selected_edge) {
      result_.decisions.push_back(std::move(row));
      ++result_.summary.decision_trace_stored_count;
    } else {
      result_.hold_attempts.push_back(std::move(row));
      ++result_.summary.hold_trace_stored_count;
    }
  }

  bool trace_available(std::size_t current_size) const {
    return config_.trace_limit < 0 || static_cast<int>(current_size) < config_.trace_limit;
  }

  void update_queue_maxima(const JunctionState& controller) {
    result_.summary.max_junction_queue_length =
        std::max(result_.summary.max_junction_queue_length,
                 static_cast<int>(controller.queue.size()));
    result_.summary.max_source_queue_length =
        std::max(result_.summary.max_source_queue_length,
                 static_cast<int>(controller.source_queue.size()));
  }

  void update_calendar_maxima(const JunctionState& controller, const LocalCalendar* corridor) {
    result_.summary.max_local_calendar_intervals =
        std::max(result_.summary.max_local_calendar_intervals,
                 controller.service_calendar.size());
    if (corridor != nullptr) {
      result_.summary.max_corridor_calendar_intervals =
          std::max(result_.summary.max_corridor_calendar_intervals, corridor->size());
    }
  }

  const Graph& graph_;
  EventDrivenJunctionConfig config_;
  EventDrivenJunctionResult result_;
  std::unordered_map<int, BagState> bags_;
  std::unordered_map<std::string, int> segment_runtime_ids_;
  std::unordered_map<int, JunctionState> junctions_;
  std::unordered_map<long long, LocalCalendar> corridors_;
  std::unordered_map<long long, event_runtime_detail::FaultState> physical_faults_;
  std::unordered_map<long long, event_runtime_detail::AdvertisedFaultState> advertised_faults_;
  std::unordered_set<int> fault_affected_bags_;
  std::priority_queue<RuntimeEvent,
                      std::vector<RuntimeEvent>,
                      event_runtime_detail::RuntimeEventLater>
      events_;
  std::uint64_t next_event_seq_ = 1;
  std::uint64_t next_decision_id_ = 1;
  double now_ = 0.0;
  std::vector<double> waits_;
  std::vector<double> decision_latencies_us_;
};

}  // namespace czr005::ics
