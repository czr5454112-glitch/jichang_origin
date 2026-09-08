#include <iostream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include "ics_core/runtime/event_driven_junction.hpp"

// Public production API only: no testing macro, private access, or mock runtime.
namespace {
using namespace czr005::ics;

void require(bool value, const char* message) {
  if (!value) throw std::runtime_error(message);
}

Graph graph(bool sibling = false) {
  Graph value;
  value.add_node({0, 0, 1.0, 0, 0, {}});
  value.add_node({1, 0, 1.0, 1, 0, {}});
  value.add_node({2, 0, 0.0, 2, 0, {}});
  value.add_edge({0, 1, 5.0, 2.5});
  value.add_edge({1, 2, 5.0, 2.5});
  if (sibling) {
    value.add_node({3, 0, 0.0, 2, 1, {}});
    value.add_edge({1, 3, 5.0, 2.5});
    value.set_heuristic({{0, 3, 6, 6}, {100, 0, 3, 3},
                         {100, 100, 0, 100}, {100, 100, 100, 0}});
  } else {
    value.set_heuristic({{0, 3, 6}, {100, 0, 3}, {100, 100, 0}});
  }
  return value;
}

EventDrivenJunctionConfig config() {
  EventDrivenJunctionConfig value;
  value.resource_semantics = "R3";
  value.event_semantics = "E4_batch_plus_destination_merge_request";
  value.queue_discipline = "fifo";
  value.scorer_mode = "S4_queue_aware_rule_only";
  value.enable_source_admission = false;
  value.admission_mode = "off";
  value.local_queue_capacity = 0;
  value.enable_backpressure = false;
  value.pressure_mode = "C0";
  value.pibt_mode = "P2";
  value.merge_grant_rule = "M3";
  value.merge_grant_timing_mode = "jit_fair_aging_deadline";
  value.enable_fault_policy = true;
  value.enable_s4_local_potential_descent_guard = true;
  value.enable_s4_direct_neighbor_merge_calendar_visibility = true;
  value.enable_s4_advertised_fault_potential_repair = true;
  value.complete_on_goal_arrival = true;
  value.max_simulation_time = 40.0;
  value.max_events = 2000;
  value.trace_limit = 2000;
  value.event_trace_limit = 2000;
  return value;
}

EventRuntimeBagRequest bag(int id = 1, int goal = 2) {
  return {std::to_string(id) + ":direct", id, 0.0, 100.0,
          0, goal, "synthetic-reset-fixture"};
}

void same_scientific_result(const EventDrivenJunctionResult& a,
                            const EventDrivenJunctionResult& b) {
  require(a.bags.size() == b.bags.size(), "bag population differs");
  for (std::size_t i = 0; i < a.bags.size(); ++i) {
    const auto& x = a.bags[i];
    const auto& y = b.bags[i];
    require(std::tie(x.segment_id, x.task_id, x.runtime_bag_id, x.start, x.goal,
        x.final_node, x.release_time, x.admitted_time, x.finish_time,
        x.source_queue_delay, x.junction_queue_wait_seconds,
        x.edge_travel_time_seconds, x.node_service_time_seconds,
        x.decision_count, x.retry_count, x.completed, x.failure_reason,
        x.short_history) ==
        std::tie(y.segment_id, y.task_id, y.runtime_bag_id, y.start, y.goal,
        y.final_node, y.release_time, y.admitted_time, y.finish_time,
        y.source_queue_delay, y.junction_queue_wait_seconds,
        y.edge_travel_time_seconds, y.node_service_time_seconds,
        y.decision_count, y.retry_count, y.completed, y.failure_reason,
        y.short_history), "scientific bag fields differ");
  }
  require(a.events.size() == b.events.size(), "event population differs");
  for (std::size_t i = 0; i < a.events.size(); ++i) {
    const auto& x = a.events[i];
    const auto& y = b.events[i];
    require(std::tie(x.seq, x.event, x.time, x.task_id, x.runtime_bag_id,
        x.segment_id, x.node, x.from_node, x.to_node, x.reason,
        x.selected_edge_count) ==
        std::tie(y.seq, y.event, y.time, y.task_id, y.runtime_bag_id,
        y.segment_id, y.node, y.from_node, y.to_node, y.reason,
        y.selected_edge_count), "native event fields differ");
  }
  require(a.decisions.size() == b.decisions.size(), "decision population differs");
  for (std::size_t i = 0; i < a.decisions.size(); ++i) {
    const auto& x = a.decisions[i];
    const auto& y = b.decisions[i];
    require(std::tie(x.decision_id, x.event_time, x.segment_id, x.current_node,
                    x.goal_node, x.selected_next) ==
            std::tie(y.decision_id, y.event_time, y.segment_id, y.current_node,
                    y.goal_node, y.selected_next), "committed decision differs");
  }
}

void reset_reuse() {
  const auto topology = graph();
  EventDrivenJunctionRuntime runtime(topology, config());
  const auto first = runtime.run({bag()}, {{1, 2, 1.0, 100.0, 0.0, false}});
  require(first.summary.completed_count == 0 && first.bags.size() == 1,
          "first run must retain an unfinished native bag");
  require(first.summary.s4_fault_unreachable_park_count == 1 &&
          first.summary.s4_fault_unreachable_active_parked_count == 1,
          "first run must leave one real parked bag");
  const auto second = runtime.run({bag()});  // Same segment and runtime ID reused.
  require(second.summary.completed_count == 1 && second.bags[0].final_node == 2,
          "second run inherited a parked ID or broken H");
  require(second.summary.s4_fault_potential_rebuild_count == 0 &&
          second.summary.s4_fault_potential_restore_original_count == 0 &&
          second.summary.s4_fault_unreachable_park_count == 0 &&
          second.summary.s4_fault_unreachable_active_parked_count == 0 &&
          second.summary.s4_fault_potential_active_advertised_edge_count == 0 &&
          second.summary.s4_fault_potential_rebuild_wall_seconds == 0.0,
          "reset leaked fault state or telemetry");
  EventDrivenJunctionRuntime fresh(topology, config());
  same_scientific_result(second, fresh.run({bag()}));
}

void checkpoint_parked() {
  const auto topology = graph();
  EventDrivenJunctionRuntime original(topology, config());
  original.initialize({bag()}, {{1, 2, 1.0, 10.0, 0.0, false}});
  int steps = 0;
  while (original.current_result().summary.s4_fault_unreachable_park_count == 0) {
    require(++steps < 1000 && original.process_one_event(), "did not reach parked boundary");
  }
  const auto before = original.current_result().summary;
  const auto checkpoint = original.capture_state_checkpoint();
  EventDrivenJunctionRuntime restored(topology, config());
  restored.restore_state_checkpoint(checkpoint);
  require(restored.deterministic_state_digests().aggregate_sha256() ==
          original.deterministic_state_digests().aggregate_sha256(),
          "checkpoint did not preserve exact new state digest");
  require(restored.current_result().summary.s4_fault_potential_rebuild_count ==
          before.s4_fault_potential_rebuild_count &&
          restored.current_result().summary.s4_fault_potential_rebuild_wall_seconds ==
          before.s4_fault_potential_rebuild_wall_seconds,
          "restore performed extra preprocessing");
  original.drain();
  restored.drain();
  const auto a = original.finalize();
  const auto b = restored.finalize();
  require(a.summary.completed_count == 1 && b.summary.completed_count == 1,
          "repair must wake the parked bag in both branches");
  require(a.summary.s4_fault_potential_rebuild_count == 1 &&
          b.summary.s4_fault_potential_rebuild_count == 1 &&
          a.summary.s4_fault_potential_restore_original_count == 1 &&
          b.summary.s4_fault_potential_restore_original_count == 1 &&
          a.summary.s4_fault_unreachable_wakeup_count == 1 &&
          b.summary.s4_fault_unreachable_wakeup_count == 1 &&
          b.summary.s4_fault_unreachable_active_parked_count == 0,
          "checkpoint continuation changed rebuild/park accounting");
  same_scientific_result(a, b);
}

void reachable_sibling() {
  const auto topology = graph(true);
  EventDrivenJunctionRuntime runtime(topology, config());
  const auto result = runtime.run({bag(1, 2), bag(2, 3)},
                                {{1, 2, 1.0, 100.0, 0.0, false}});
  require(result.bags.size() == 2 && result.summary.completed_count == 1 &&
          result.summary.s4_fault_unreachable_active_parked_count == 1,
          "parked front prevented a reachable sibling from completing");
  for (const auto& row : result.bags) {
    require(row.completed == (row.goal == 3), "wrong sibling completion identity");
  }
}

void unsupported_admission_rejected() {
  const auto topology = graph();
  for (int variation = 0; variation < 3; ++variation) {
    auto invalid = config();
    if (variation == 0) invalid.enable_source_admission = true;
    if (variation == 1) invalid.admission_mode = "legacy_unbound";
    if (variation == 2) invalid.local_queue_capacity = 1;
    bool rejected = false;
    try { EventDrivenJunctionRuntime runtime(topology, invalid); }
    catch (const std::invalid_argument&) { rejected = true; }
    require(rejected, "unsupported source admission/capacity accepted");
  }
}
}  // namespace

int main() {
  try {
    reset_reuse();
    checkpoint_parked();
    reachable_sibling();
    unsupported_admission_rejected();
    std::cout << "{\"status\":\"PASS\",\"cases\":4,\"reset_same_object\":true,"
                 "\"checkpoint_park_restore\":true,\"reachable_sibling\":true,"
                 "\"unsupported_source_contract_rejected\":true,"
                 "\"scope\":\"bounded_synthetic_public_production_runtime_api\"}\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
