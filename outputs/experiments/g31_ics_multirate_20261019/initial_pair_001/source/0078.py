"""Pure reference transition model for a NEW serial, multiple-carrier policy.

This file is NOT a NativeSession adapter, an online authority token, or a
dispatchable policy. Its global state is only an invariant-checking oracle.
Actual implementation must reconstruct owner-local facts from native current
views, delivered typed captures and own immutable outboxes, as specified in
the accompanying source design. No saved dict can authorize a native command.

The change is carrier substitution after completion, NOT two active loads:
one completed job licenses at most one direct supply, or a bridge followed by
one direct supply. A direct donor may be a different existing local empty
carrier; a bridge must carry the just-completed carrier. No later FIFO head
may replace the original policy's selected head.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

SCHEMA = "g31.completion_baton_relay.pure_reference.v1"


def require(value, reason):
    if not value:
        raise ValueError("completion_baton:" + reason)


def clock(value):
    return type(value) in (int, float) and isfinite(value) and value >= 0


@dataclass(frozen=True)
class Completion:
    receipt_id: str
    job_id: str
    tray_id: str
    owner: str
    destination: int
    completed_at: float


@dataclass(frozen=True)
class Empty:
    tray_id: str
    owner: str
    node: int
    generation: int
    traversal: int
    available_at: float
    observed_at: float
    mode: str = "empty"
    job_id: str = ""
    edge_to: int = -1
    reception_node: int = -1
    role: str = "ordinary"


@dataclass(frozen=True)
class Head:
    job_id: str
    owner: str
    origin: int
    arrival: float
    observed_at: float
    required_stages_reachable: bool


def exact_empty(tray, now):
    require(type(tray) is Empty and clock(now), "empty_fact_type")
    require(type(tray.tray_id) is str and tray.tray_id and type(tray.owner) is str
            and tray.owner and type(tray.node) is int and tray.node >= 0
            and type(tray.generation) is int and tray.generation >= 0
            and type(tray.traversal) is int and tray.traversal >= 0,
            "empty_identity")
    require(clock(tray.available_at) and clock(tray.observed_at)
            and tray.available_at <= now and tray.observed_at == now
            and tray.mode == "empty" and tray.job_id == ""
            and tray.edge_to == -1 and tray.reception_node == -1,
            "current_empty_required")


class ReferenceBaton:
    """Fresh reference trace only; deliberately has no restore or submit API.

    ``physical_barrier`` is a test premise, NOT a sufficient live proof. The
    production adapter must preserve complete per-owner action coverage and
    all received ACK checks from the frozen bridge policy. These assertions
    prove only the abstract transition invariant when those premises hold.
    """
    def __init__(self, inventory, owners):
        require(type(inventory) is tuple and len(inventory) == 22
                and all(type(x) is str and x for x in inventory)
                and len(set(inventory)) == 22, "original_22_inventory")
        require(type(owners) is tuple and len(owners) == 2
                and len(set(owners)) == 2, "two_owners")
        self.inventory = frozenset(inventory)
        self.owners = owners
        self.consumed_completions = set()
        self.consumed_jobs = set()
        self.grant = None
        self.pending = None
        self.phase = "await_completion"
        self.operation_ids = set()
        self.supplies = 0
        self.bridges = 0
        self.invalid = None

    def open_completion(self, receipt, current, *, physical_barrier):
        require(self.invalid is None and self.phase == "await_completion"
                and self.pending is None, "already_active_or_invalid")
        require(physical_barrier is True, "complete_received_barrier")
        require(type(receipt) is Completion and receipt.tray_id in self.inventory
                and receipt.owner in self.owners and type(receipt.receipt_id) is str
                and receipt.receipt_id and type(receipt.job_id) is str and receipt.job_id,
                "completion_identity")
        exact_empty(current, current.observed_at)
        require(receipt.owner == current.owner and receipt.tray_id == current.tray_id
                and receipt.destination == current.node and clock(receipt.completed_at)
                and receipt.completed_at <= current.available_at
                and current.role not in ("loader", "storage"), "completion_current_possession")
        require(receipt.receipt_id not in self.consumed_completions
                and receipt.job_id not in self.consumed_jobs, "completion_reused")
        # The actual adapter consumes the local receipt before any native submit.
        self.consumed_completions.add(receipt.receipt_id)
        self.consumed_jobs.add(receipt.job_id)
        self.grant = receipt
        self.phase = "owner_choice"

    def supply(self, request_id, donor, baseline_head, selected_head, *,
               positive_supply_path, source_export_ok, receiver_capture_ok):
        require(self.invalid is None and self.phase in ("owner_choice", "bridge_choice")
                and self.pending is None, "no_supply_grant")
        exact_empty(donor, donor.observed_at)
        owner = self.grant.owner if self.phase == "owner_choice" else self._bridge_owner
        require(donor.owner == owner and donor.tray_id in self.inventory, "donor_owner_inventory")
        if self.phase == "bridge_choice":
            require(donor.tray_id == self.grant.tray_id, "bridge_followup_same_carrier")
        require(type(baseline_head) is Head and selected_head == baseline_head,
                "same_original_selected_head")
        require(baseline_head.owner in self.owners and baseline_head.owner != owner
                and type(baseline_head.job_id) is str and baseline_head.job_id
                and clock(baseline_head.arrival) and clock(baseline_head.observed_at)
                and baseline_head.arrival <= baseline_head.observed_at <= donor.observed_at
                and baseline_head.required_stages_reachable is True, "reachable_released_peer_head")
        require(positive_supply_path is True and source_export_ok is True
                and receiver_capture_ok is True, "necessary_resource_screen")
        self._begin(request_id, "supply", donor.tray_id, baseline_head.job_id)
        self.supplies += 1

    def bridge(self, request_id, current, *, target_owner, target_role,
               positive_paths, source_export_ok, receiver_capture_ok):
        require(self.invalid is None and self.phase == "owner_choice"
                and self.pending is None, "no_bridge_grant")
        exact_empty(current, current.observed_at)
        require(current.owner == self.grant.owner and current.tray_id == self.grant.tray_id,
                "bridge_completed_carrier_only")
        require(target_owner in self.owners and target_owner != current.owner
                and target_role not in ("loader", "storage")
                and positive_paths is True and source_export_ok is True
                and receiver_capture_ok is True, "bridge_resource_screen")
        self._bridge_owner = target_owner
        self._begin(request_id, "bridge", current.tray_id, None)
        self.bridges += 1

    def _begin(self, request_id, kind, tray_id, job_id):
        require(type(request_id) is str and request_id and request_id not in self.operation_ids,
                "unique_immutable_operation")
        self.operation_ids.add(request_id)
        self.pending = (request_id, kind, tray_id, job_id)
        self.phase = "await_received_ACK"

    def delivered_received(self, request_id, *, ack_status, delivered_at, now):
        require(self.pending is not None and self.phase == "await_received_ACK",
                "no_pending_transfer")
        require(request_id == self.pending[0] and clock(delivered_at) and clock(now)
                and delivered_at <= now, "own_ACK_identity_clock")
        if ack_status in ("pending", "not_delivered", "unknown"):
            return  # Retry remains the same immutable operation, never a new grant.
        if ack_status != "received":
            self.invalid = "unknown_or_failed_transfer"
            return
        self.phase = "await_actual_bridge_empty" if self.pending[1] == "bridge" else "await_job_completion"

    def bridge_arrival(self, current, *, complete_barrier, delivered_completion):
        require(self.invalid is None and self.phase == "await_actual_bridge_empty",
                "no_bridge_arrival_grant")
        exact_empty(current, current.observed_at)
        require(current.owner == self._bridge_owner and current.tray_id == self.grant.tray_id
                and current.role not in ("loader", "storage")
                and delivered_completion == self.grant and complete_barrier is True,
                "bridge_actual_identity_and_delivered_completion")
        self.pending = None
        self.phase = "bridge_choice"

    def job_finished(self, receipt, current, *, physical_barrier):
        require(self.invalid is None and self.phase == "await_job_completion"
                and self.pending is not None, "no_supplied_job")
        require(receipt.job_id == self.pending[3] and receipt.tray_id == self.pending[2],
                "different_actual_job_or_carrier")
        self.pending = None
        self.grant = None
        self.phase = "await_completion"
        self.open_completion(receipt, current, physical_barrier=physical_barrier)


def zero_bad_load_prefix_bound(loader_rows):
    """Conditional FIFO-prefix lemma, NOT a whole-airport infeasibility claim.

    Each input list is complete native FIFO order with strictly increasing
    arrivals at that origin. Values mark positive mandatory-stage reachability.
    If no unreachable job is ever loaded, loaded jobs can only precede the first
    False at every loader, regardless of the number of existing active trays.
    No claim is made for changed graphs, off-carrier release, bypass or ties.
    """
    total = 0
    for rows in loader_rows.values():
        previous = -1.
        stopped = False
        for arrival, reachable in rows:
            require(clock(arrival) and arrival > previous and type(reachable) is bool,
                    "strict_source_arrival_order")
            previous = arrival
            if not reachable:
                stopped = True
            elif not stopped:
                total += 1
    return total
