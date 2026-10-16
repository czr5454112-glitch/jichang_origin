#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace czr005::ics {

// Opt-in physical contract, shared by every policy in circulation mode.
// All times are native G31 seconds. Storage is explicitly on-carrier.
struct CirculationNodeContract {
  int node = -1;
  std::string zone;
  int capacity = 1;  // includes parked, held and incoming carriers
  int export_min_stock = 0;
  bool allow_export = true;
  bool allow_receive = true;
  std::string control_partition;
  std::string resource_owner;
};
struct CirculationEdgeContract {
  int from = -1;
  int to = -1;
  int capacity = 1;  // simultaneous traversals, independent of entry headway
  double entry_headway = 0.001;
};
struct CirculationTrayInput {
  std::string tray_id;
  int node = -1;
};
struct CirculationJob {
  std::string business_bag_id;
  int origin = -1;
  int destination = -1;
  double arrival = 0;
  double deadline = -1;
  int storage_node = -1;
  double storage_release_at = 0;
  double storage_min_dwell = 0;
  double load_seconds = 0;
  double unload_seconds = 1;
  double hold_seconds = 0;
  bool protected_service = true;
  bool allow_suffix_reroute = false;
};
struct CirculationTransfer {
  std::string request_id;
  std::string tray_id;
  int source = -1;
  int destination = -1;
  double issued_at = 0;
  double message_delay = 0;
  double earliest_departure = 0;
  double expiry = 1.0e9;  // departure lease, reception berth stays held in transit
};
struct CirculationOwnerOutage {
  std::string owner;
  double start = 0, end = 0;
};
struct CirculationOwnerProtocol {
  bool enabled = false;
  double ack_delay = 0, timeout = 1, duplicate_ack_delay = 0;
  int drop_ack_packets = 0;
  bool duplicate_acks = false;
  std::vector<CirculationOwnerOutage> outages;
};
struct CirculationInput {
  std::vector<CirculationNodeContract> nodes;
  std::vector<CirculationEdgeContract> edges;
  std::vector<CirculationTrayInput> trays;
  std::vector<CirculationJob> jobs;
  std::vector<CirculationTransfer> transfers;
  CirculationOwnerProtocol owner_protocol;
  bool owner_notifications_enabled = false;
};
// Owner-local revision, never a global heap/event/traversal counter. Bits:
// arrival=1, physical=2, demand=4, forecast=8, ACK=16, timeout=32, known fault=64,
// explicit planning snapshot delivery=128.
struct CirculationOwnerNotification {
  std::uint64_t sequence = 0, change_mask = 0;
  double observed_at = -1;
};
struct CirculationNotificationAdvance {
  std::string status;
  bool timestamp_complete = false, horizon_complete = false;
};
struct CirculationTrayState {
  std::string tray_id;
  int node = -1;
  std::string mode = "empty";
  int job = -1;
  int active_leg = -1;
  int edge_from = -1;
  int edge_to = -1;
  int reception_node = -1;
  int transfer = -1;
  double available_at = 0;
  double storage_arrived_at = -1;
  std::uint64_t generation = 0;
  std::uint64_t traversal_id = 0;
  // Public prefix version is local to this tray; the offline traversal ID is
  // globally unique and must not reveal unrelated owners' physical activity.
  std::uint64_t public_traversal_version = 0;
  bool edge_entry_observed = false;
};
struct CirculationJobState {
  std::string status = "unreleased";
  int tray = -1;
  double loaded_at = -1;
  double storage_entered_at = -1;
  double storage_released_at = -1;
  double completed_at = -1;
  bool deadline_met = false;
};
struct CirculationTransferState {
  std::string status = "undelivered";
  std::string reason;
  int tray = -1;
  double delivered_at = -1;
  double departed_at = -1;
  double received_at = -1;
};
struct CirculationLeg {
  int runtime_id = -1;
  std::string transport_leg_id;
  int tray = -1;
  int job = -1;  // -1 denotes a real empty-carrier movement
  std::string kind;  // storage_in, storage_out, direct, empty_return
};
struct CirculationReceipt {
  double time = 0;
  std::string event;
  std::string business_bag_id;
  std::string transport_leg_id;
  std::string tray_id;
  std::uint64_t traversal_id = 0;
  int node = -1;
  int from = -1;
  int to = -1;
  std::string reason;
};

// Online messages are native events. Forecasts never constitute inventory or
// owner grants. The environment tape remains internal to the physical host.
struct CirculationRouteIntent {
  std::string request_id, owner_id, business_bag_id, tray_id;
  int from = -1, next = -1;
  std::uint64_t expected_generation = 0;
  std::uint64_t expected_traversal = 0;
  double delivered_at = 0, expiry = 0;
  std::string status = "pending", reason;
};
struct CirculationDemandItem {
  std::string business_bag_id;
  int origin = -1;
  double arrival = 0, deadline = -1;
};
struct CirculationDemandMessage {
  std::string message_id, source_owner, target_owner;
  std::uint64_t publication_sequence = 0;
  double observed_at = 0, delivered_at = 0;
  // Source-time membership in immutable input.jobs, in original input order.
  // Indices survive checkpoint/fork copies; never re-filter current state.
  // Renderers and the canonical checkpoint still emit the original fields.
  std::vector<std::size_t> jobs;
  bool delivered = false;
};
struct CirculationServiceForecast {
  std::string message_id, source_owner, target_owner, business_bag_id, tray_id;
  int from = -1, next = -1;
  std::uint64_t generation = 0, traversal_id = 0;
  std::uint64_t publication_sequence = 0;
  double observed_at = 0, delivered_at = 0;
  double entry_estimate = 0, release_estimate = 0;
  // Conditional next-node service completion, never empty inventory or a grant.
  std::string status = "conditional";
  std::string supersedes;
  bool delivered = false;
};
// Explicit research message: native source-time facts, never caller estimates.
// Public traversal versions are local to each carrier; runtime IDs stay private.
struct CirculationPlanningJob {
  CirculationJob contract;
  std::string status;
  double loaded_at=-1,storage_entered_at=-1,storage_released_at=-1;
};
struct CirculationPlanningTray {
  std::string tray_id,business_bag_id,mode,ready_kind="unknown";
  int node=-1,edge_from=-1,edge_to=-1,reception_node=-1;
  std::uint64_t generation=0,traversal_id=0;
  double available_at=0,service_ready_at=-1,load_complete_at=-1;
  bool service_ready_known=false;
  std::vector<int> committed_prefix;
};
struct CirculationPlanningNode {
  int node=-1,occupancy=0,actual_available=0,unrepresented_occupancy=0;
};
struct CirculationPlanningFault {
  int from=-1,to=-1;
  bool active=false;
  double received_at=-1;
};
struct CirculationPlanningSnapshot {
  std::string message_id,source_owner,target_owner,static_contract_sha256,payload_sha256;
  std::uint64_t publication_sequence=0;
  double captured_at=0,delivered_at=-1,valid_until=0;
  bool delivered=false;
  std::string queue_discipline,resource_semantics,event_semantics,scorer_mode,merge_grant_rule,merge_grant_timing_mode;
  double minimum_service_seconds=0;
  std::vector<CirculationPlanningJob> jobs;
  std::vector<CirculationPlanningTray> trays;
  std::vector<CirculationPlanningNode> nodes;
  std::vector<CirculationPlanningFault> known_faults;
};
struct CirculationPlanningCompletion {
  std::string receipt_id,source_owner,business_bag_id,tray_id;
  std::uint64_t source_local_sequence=0;
  int destination=-1;
  double completed_at=-1;
};
struct CirculationPlanningAction {
  std::string request_id,kind,source_owner,ack_status;
  std::uint64_t ack_sequence=0;
  double ack_delivered_at=-1;
  bool has_delivered_ack=false,terminal=false;
};
struct CirculationPlanningSnapshotV2 : CirculationPlanningSnapshot {
  std::vector<CirculationPlanningCompletion> terminal_receipts;
  std::vector<CirculationPlanningAction> submitted_physical_actions;
};
struct CirculationPlanningInflight {
  std::string source_owner,tray_id,business_bag_id;
  std::uint64_t generation=0,traversal_id=0; // public per-tray version only
  int edge_from=-1,edge_to=-1;
  double entered_at=-1,static_edge_travel_seconds=0,derived_edge_exit_at=-1;
};
struct CirculationPlanningSnapshotV3 : CirculationPlanningSnapshotV2 {
  std::vector<CirculationPlanningInflight> source_observed_inflight;
  // Committed destinations without a matching already-observed entry remain
  // in the denominator. They are not future-event estimates or usable rows.
  std::vector<std::string> unmatched_inflight_tray_ids;
};
struct CirculationRecoveryIntent {
  std::string request_id, owner_id, tray_id;
  std::uint64_t expected_generation = 0;
  double delivered_at = 0;
  std::string status = "pending", reason;
};

// A physical leg waits on current committed resources, not an environment-tape
// lookahead or a periodic poll. Reverse indexes only contain active waits.
struct CirculationResourceWait {
  int runtime_id = -1;
  int node = -1;
  std::uint64_t generation = 0;
  std::vector<int> edge_indices;
  std::vector<int> receiving_nodes;
  std::vector<int> ranking_nodes;
  bool static_blocked = false;
};
struct CirculationOfflineJunction {
  int node = -1;
  std::vector<int> queue, source_queue;
  int scheduled_incoming = 0;
  double next_dispatch_time = 0;
};

// A controller's knowledge is a delivered immutable ACK, never a read through
// the physical transfer table. The module and physical transfer are native.
struct CirculationProtocolRequest {
  int transfer = -1;
  std::string owner, client_status = "pending";
  std::uint64_t attempt = 1, next_ack_sequence = 1, delivered_ack_sequence = 0;
  std::uint64_t delivered_attempt = 0;
  std::uint64_t waiting_attempt = 0;
  int latest_ack = -1, remaining_ack_drops = 0;
  bool waiting_for_owner = false;
};
struct CirculationProtocolAck {
  int request = -1;
  std::uint64_t sequence = 0, attempt = 0;
  double observed_at = 0, delivered_at = -1;
  std::string status, reason;
  int delivered_copies = 0, dropped_copies = 0;
  double received_at = -1;
};
struct CirculationProtocolCommandInput {
  std::string request_id,owner,kind,target_owner,tray_id,business_bag_id;
  std::string reference_id,reference_request_id;
  int from=-1,next=-1;
  std::uint64_t expected_generation=0,expected_traversal=0;
  double message_delay=0,publication_delay=0,expiry=1.0e9;
};
struct CirculationProtocolCommand {
  CirculationProtocolCommandInput input;
  std::string client_status="pending",execution_status="enqueued",result_status="pending_execution",reason,result_id;
  int native_index=-1,latest_ack=-1,remaining_ack_drops=0;
  double executed_at=-1,completed_at=-1;
  std::uint64_t attempt=1,arrived_attempt=0,waiting_attempt=0,next_ack_sequence=1,delivered_ack_sequence=0,delivered_attempt=0;
  bool waiting_for_owner=false,waiting_for_recipient=false;
};
struct CirculationProtocolCommandAck {
  int command=-1;
  std::uint64_t sequence=0,attempt=0;
  double observed_at=0,delivered_at=-1,executed_at=-1,completed_at=-1;
  std::string status,reason,result_id;
  int delivered_copies=0,dropped_copies=0;
};

struct CirculationState {
  bool enabled = false;
  CirculationInput input;
  std::vector<CirculationTrayState> trays;
  std::vector<CirculationJobState> jobs;
  std::vector<CirculationTransferState> transfers;
  std::vector<CirculationLeg> legs; // indexed by G31 runtime_id
  std::vector<CirculationReceipt> receipts;
  std::vector<double> next_entry;
  std::uint64_t next_traversal = 1;
  std::vector<CirculationRouteIntent> route_intents;
  std::vector<CirculationDemandMessage> demand_messages;
  std::vector<CirculationServiceForecast> service_forecasts;
  std::vector<CirculationPlanningSnapshot> planning_snapshots;
  std::vector<CirculationPlanningSnapshotV2> planning_snapshots_v2;
  std::vector<CirculationPlanningSnapshotV3> planning_snapshots_v3;
  std::vector<CirculationRecoveryIntent> recovery_intents;
  std::uint64_t next_control_id = 1;
  std::map<std::pair<std::string,std::string>,std::uint64_t> next_channel_message_id;
  // Immutable derived topology domain. An empty potential matrix retains the
  // mature declared heuristic; reachability still binds the real topology.
  std::string static_domain_version = "declared_graph_heuristic_with_reachability.v1";
  std::vector<std::vector<double>> static_route_potential;
  std::vector<std::vector<bool>> static_route_reachable;
  std::map<int, CirculationResourceWait> resource_waits;
  std::map<int, std::map<int, std::uint64_t>> edge_waiters;
  std::map<int, std::map<int, std::uint64_t>> receiving_waiters;
  std::map<int, std::map<int, std::uint64_t>> ranking_waiters;
  std::uint64_t next_resource_wait_generation = 1;
  std::vector<CirculationProtocolRequest> protocol_requests;
  std::vector<CirculationProtocolAck> protocol_acks;
  std::map<std::string,int> protocol_owner_down;
  std::vector<CirculationProtocolCommand> protocol_commands;
  std::vector<CirculationProtocolCommandAck> protocol_command_acks;
  std::map<std::string,CirculationOwnerNotification> owner_notifications;

  // Preallocated at initialization: safe at irreversible native publication.
  // Callers pass the current execution clock (now_), not an admission/ready
  // parameter, which may be a future reservation bound even at a one-ULP tie.
  void notify_owner(const std::string& owner, double time, std::uint64_t mask) noexcept {
    if(!input.owner_notifications_enabled) return;
    auto found=owner_notifications.find(owner);
    if(found==owner_notifications.end()) return;
    auto& notice=found->second;
    if(notice.observed_at!=time) notice.change_mask=0;
    ++notice.sequence;notice.observed_at=time;notice.change_mask|=mask;
  }
  void notify_node(int node, double time, std::uint64_t mask) noexcept {
    if(!input.owner_notifications_enabled) return;
    for(const auto& contract:input.nodes) if(contract.node==node) {
      notify_owner(contract.resource_owner.empty() ? contract.zone : contract.resource_owner,time,mask);
      return;
    }
  }

  std::string owner(int node) const {
    const auto& n = node_contract(node);
    return n.resource_owner.empty() ? n.zone : n.resource_owner;
  }
  std::string partition(int node) const {
    const auto& n = node_contract(node);
    return n.control_partition.empty() ? n.zone : n.control_partition;
  }

  const CirculationNodeContract& node_contract(int node) const {
    const auto found = std::find_if(input.nodes.begin(), input.nodes.end(),
        [node](const auto& n) { return n.node == node; });
    if (found == input.nodes.end()) throw std::invalid_argument("circulation:missing_node_contract");
    return *found;
  }
  int edge_index(int from, int to) const noexcept {
    for (std::size_t i = 0; i < input.edges.size(); ++i)
      if (input.edges[i].from == from && input.edges[i].to == to) return static_cast<int>(i);
    return -1;
  }
  int occupancy(int node, int exclude_tray = -1) const noexcept {
    int count = 0;
    for (std::size_t i = 0; i < trays.size(); ++i) {
      if (static_cast<int>(i) == exclude_tray) continue;
      const auto& t = trays[i];
      // One carrier is counted once even when its remote reception lease
      // becomes the currently reserved one-hop receiving berth.
      if ((t.edge_to < 0 && t.node == node) || t.edge_to == node ||
          t.reception_node == node) ++count;
    }
    return count;
  }
  int empty_stock(int node, double time) const noexcept {
    int count = 0;
    for (const auto& t : trays)
      if (t.node == node && t.edge_to < 0 && t.mode == "empty" &&
          t.available_at <= time + 1e-9 && t.active_leg < 0) ++count;
    return count;
  }
  std::string can_enter(int runtime_id, int from, int to, double time) const {
    if (!enabled) return "allowed";
    if (runtime_id < 0 || runtime_id >= static_cast<int>(legs.size())) return "circulation:unbound_leg";
    const int ti = legs[runtime_id].tray;
    const auto& tray = trays.at(ti);
    if (tray.node != from || tray.edge_to >= 0 || tray.active_leg != runtime_id)
      return "circulation:carrier_not_at_source";
    if (tray.transfer >= 0 && transfers[tray.transfer].status == "dispatching" &&
        time > input.transfers[tray.transfer].expiry + 1e-9)
      return "circulation:departure_lease_expired";
    const int ei = edge_index(from, to);
    if (ei < 0) return "circulation:missing_edge_contract";
    const auto& edge = input.edges[ei];
    if (edge.capacity == 0) return "circulation:edge_closed";
    if (!std::isfinite(time + edge.entry_headway))
      throw std::invalid_argument("circulation:nonfinite_derived_time");
    if (next_entry[ei] > time + 1e-9) return "circulation:entry_headway";
    int inflight = 0;
    for (const auto& t : trays)
      if (t.edge_from == from && t.edge_to == to) ++inflight;
    if (inflight >= edge.capacity) return "circulation:edge_capacity";
    if (occupancy(to, ti) >= node_contract(to).capacity) return "circulation:receiving_full";
    return "allowed";
  }
  // Called only at the native transaction's irreversible publication point.
  // Fixed-size state only: no allocations, no callbacks and no exceptions.
  void reserve_enter(int runtime_id, int from, int to, double time) noexcept {
    if (!enabled) return;
    auto& tray = trays[legs[runtime_id].tray];
    const int ei = edge_index(from, to);
    next_entry[ei] = time + input.edges[ei].entry_headway;
    tray.edge_from = from;
    tray.edge_to = to;
    tray.traversal_id = next_traversal++;
    ++tray.public_traversal_version;
    tray.edge_entry_observed = false;
  }
};

} // namespace czr005::ics
