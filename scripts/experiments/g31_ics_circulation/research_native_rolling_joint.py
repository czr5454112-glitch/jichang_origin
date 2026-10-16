"""Preregistered native025 two-stage rolling proposal with actual v2 delivery.

Each policy reads only its own observation, delivered messages and outbox. The
host schedules owner activations; results/checkpoints never enter decisions.
This is the existing synthetic finite fixture, not a novel solver or proof of
model protection. Every unsupported input and failed branch remains visible.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import traceback
from . import native_rolling_planning_adapter as adapter
from . import native_planning_adapter as initial_adapter
from . import planning_capture_v2_contract as extension
from . import planning_capture_v2_digest as encoding
from . import public_rolling_reuse_model as model
from . import research_native_public_joint as initial
from . import research_synthetic_reuse_chain as v1
from . import research_synthetic_reuse_v2 as v2
from . import native_host
from .native_host import load_native

METHODS = ("frozen_later", "coordinate_strict", "coordinate_plateau", "resource_pair_repair")
COLLECTION_LIMIT = .08
CAPTURE_VALIDITY = .2
MAX_ACTIVATIONS = 10000


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path, value): path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def protocol():
    return {"schema": "g31.lt2.native_public_rolling_joint.v2", "native_branch_budget": 12,
        "rows": {f"gate{int(gate)}/{method}": {"gate": gate, "method": method, "status": "unknown_unexecuted"}
            for gate in v1.GATES for method in METHODS},
        "source_fixture": "unchanged synthetic two trays/four jobs, gates0/6/12, native025; owner notifications enabled",
        "initial_policy": "each owner independently selects initial joint_model from actually delivered v1 capture pair at.11",
        "initial_ledger": "each owner retains full four-job source-authored contracts from its actual initial capture pair",
        "first_return_trigger": "A current local L empty/available at6 and delivered B demand includes7; first actual return only",
        "first_route_trigger": "B current local L loaded with reuse1 at7; first actual loaded reuse only",
        "preflight_ack_refresh": "Before that route trigger, actual B local L loading reuse1 at7 publishes one v2 preflight. A reacts only to its actual delivered source facts, retransmits its matching immutable unresolved L6to7 return ID once, waits delivered receivedACK, then replies. Normal fresh loaded-service capture pair still required. This does not reduce the.5 ordinary retry timer or.05 capture-age guard.",
        "publication": {"message_delay": .01, "publication_delay": .01, "ack_delay": .02,
            "validity": CAPTURE_VALIDITY, "maximum_collection_wait": COLLECTION_LIMIT},
        "collection": "initiator publishes v2; peer replies once per eligible source-local L phase upon actual delivery; reply body lacks initiator-local L and never triggers another reply; exact selected peer ID/capture>=collection start bound; no shared readiness gate",
        "activation": "native owner notifications plus unchanged public .05 ordinary tick and .5 immutable request retry; all methods use identical communication and activation rule",
        "action": "execute only R2 return_delay at A first_return; later fresh B solve executes only reuse_next. Future proposed action remains nonbinding.",
        "common_later": "second return immediate on lawful local supply+delivered demand; second reuse explicit next3; same receiving_full recovery for initial E transfer",
        "policy_information": "owner-local current view, actual delivered v2/selfACK, retained actual initial contracts, public durations; no native fork/result/checkpoint/outcome tables",
        "objective": "minimize predicted sum of all four completion epochs subject to every predicted job <= same-input incumbent; no model error bound",
        "search": {"budget_per_solve": 32, "methods": list(METHODS), "candidate_order": "public model exact deterministic tuple order",
            "frozen_later": {"reuse_next": 3, "return_delay": 0.}},
        "fallback": "after delivered invalid pair or fixed collection limit, A return_delay0; B explicit next3 only if still local loaded at7; retain unknown proposal and any stale ACK",
        "population_protection": "all four physical native completion epochs <= same-gate frozen_later arm; exact zero tolerance; missing/incomplete is unknown",
        "lineage_scope": "owner-activation proxy admissions before local policy observation, explicit request creation/continuation/rejection/message causes; no exhaustive business-request or compute-span certificate",
        "source_quiescence": "common finite controller makes no other L physical admission during pending pair; native coverage cannot certify unsubmitted future Python plans",
        "limits": ["same synthetic old domain, no outcome-selected new fixture", "conditional model, not certified prediction",
            "no atomic distributed agreement", "no solver novelty", "not complete-request100ms evidence"],
        "failures": "retain all12 branches, source drift, asymmetric readiness, missing receipts, unsupported model states, late/rejected action, unfinished native jobs"}


def choose(information, method):
    if method not in METHODS: raise ValueError("rolling_joint:undeclared_method")
    if information.get("status") != "conditional_native_delivered_later_model_input" or information.get("native_delivery_verified") is not True:
        return {"status": "unknown_unverified_or_unsupported_input", "selected_action": None}
    bundle = information["bundle"]
    if method == "frozen_later":
        action = {"reuse_next": 3, "return_delay": 0.}
        return {"status": "declared_frozen_later", "selected_action": action,
            "selected_prediction": model.predict(bundle, action), "native_protection_certified": False}
    return model.propose(bundle, method=method, evaluation_budget=32)


def invitation_phase(envelope, owner, now):
    """Finite fixture invitation from actual source facts, no synthetic tag.

    A reply capture cannot contain the initiating peer's locally held L. Each
    phase is answered at most once, including after a collection timeout.
    """
    try:
        local = envelope["capture"]["local_capture"]
        source = {"A": "B", "B": "A"}[owner]
        if (envelope.get("schema") != "g31.planning_snapshot.v2" or envelope.get("kind") != "planning_snapshot_v2"
                or envelope.get("status") != "conditional" or local["source_owner"] != source or local["target_owner"] != owner
                or not 0 <= local["captured_at"] <= envelope["delivered_at"] <= now < local["valid_until"]): return None
        trays = [t for t in local["trays"] if t["tray_id"] == "L" and t["edge_to"] < 0]
        if len(trays) != 1: return None
        tray = trays[0]
        if source == "A" and (tray["node"], tray["mode"], tray["business_bag_id"]) == (6, "empty", "") and tray["available_at"] <= local["captured_at"]:
            return "first_return"
        if source == "B" and (tray["node"], tray["mode"], tray["business_bag_id"]) == (7, "loaded", "reuse1"):
            return "first_reuse_route"
        if (source == "B" and (tray["node"], tray["mode"], tray["business_bag_id"]) == (7, "loading", "reuse1")
                and tray.get("service_ready_known") is True and tray.get("load_complete_at", -1) > local["captured_at"]):
            return "reuse1_loading_ack_refresh"
    except (KeyError, TypeError, ValueError): pass
    return None


class LocalTransport(v1.Transport):
    """Shared storage is an audit sink; each endpoint refresh is owner-filtered."""
    def __init__(self, session):
        super().__init__(session)
        self.roots, self.creations = [], {}
        self.context = None
        self.ack_handling = []

    def activate(self, owner, trigger):
        root = {"root_id": f"activation:{len(self.roots)}:{owner}", "owner": owner,
            "accepted_at": self.session.physical_time, "accepted_wall_ns": time.perf_counter_ns(),
            "scope": "owner_activation_proxy", "trigger": copy.deepcopy(trigger), "protocol_ids": []}
        self.roots.append(root); self.context = root
        return root["root_id"]

    def submit(self, owner, kind, label, *, causal=None, **payload):
        if self.context is None or self.context["owner"] != owner:
            raise ValueError("rolling_joint:submission_without_owned_admission")
        identity = super().submit(owner, kind, label, **payload)
        self.context["protocol_ids"].append(identity)
        self.creations[identity] = {"creating_root": self.context["root_id"], "kind": kind,
            "causal": copy.deepcopy(causal or {"relation": "independent_offer", "continuation_parent_roots": []})}
        return identity

    def refresh_owner(self, owner, *, retry=True):
        for identity, row in self.rows.items():
            if row["request"]["owner_id"] != owner: continue
            value = (self.session.protocol_request(owner, identity) if row["kind"] == "transfer"
                     else self.session.protocol_command(owner, identity))
            ack = value.get("last_delivered_ack", {})
            if ack and ack != row.get("ack"):
                self.ack_handling.append({"at": self.session.physical_time, "owner": owner,
                    "request_id": identity, "ack": copy.deepcopy(ack), "handling_root": self.context["root_id"] if self.context else None,
                    "continuation_parent_roots": [self.creations[identity]["creating_root"]]})
            row["ack"] = ack
            row["terminal"] = row["terminal"] or ack.get("status") in v1.TERMINAL
            if retry and not row["terminal"] and self.session.physical_time >= row["next_retry"]:
                self.send(identity, retry=True)

    def refresh(self, *, retry=True):
        raise ValueError("rolling_joint:global_refresh_forbidden")

    def owned(self, owner): return {k: r for k, r in self.rows.items() if r["request"]["owner_id"] == owner}


class OwnerPolicy:
    def __init__(self, native, session, client, owner, ledger, channel, method, supply=None):
        self.native, self.session, self.client, self.owner = native, session, client, owner
        self.peer = "B" if owner == "A" else "A"
        self.ledger, self.channel, self.method = ledger, channel, method
        self.pending = None; self.seen_messages = set(); self.started = set()
        self.answered_phases = set()
        self.pending_reply = None
        self.decisions, self.exchanges, self.returns, self.choices, self.recovery = [], [], [], [], []
        self.supplies = [supply] if supply else []
        self.route_keys = set(); self.serial = 0

    def publication(self, label, causal):
        self.serial += 1
        return self.client.submit(self.owner, "planning_snapshot_v2", f"rolling-{label}-{self.serial}",
            causal=causal, target_owner=self.peer, message_delay=.01, publication_delay=.01,
            expiry=self.session.physical_time + CAPTURE_VALIDITY)

    def begin(self, phase, tray, root):
        self.started.add(phase)
        identity = self.publication(phase, {"relation": "independent_offer", "continuation_parent_roots": [],
            "local_trigger": {"phase": phase, "tray": copy.deepcopy(tray)}})
        self.pending = {"phase": phase, "at": self.session.physical_time, "deadline": self.session.physical_time + COLLECTION_LIMIT,
            "request_id": identity, "root": root, "trigger_tray": copy.deepcopy(tray), "peer_message": None}

    def exchange(self, view):
        for envelope in self.session.protocol_planning_snapshots_v2(self.owner):
            local = envelope["capture"]["local_capture"]; identity = local["message_id"]
            if identity in self.seen_messages: continue
            self.seen_messages.add(identity)
            if self.pending:
                if local["captured_at"] >= self.pending["at"]:
                    self.pending["peer_message"] = identity
                self.exchanges.append({"at": view["now"], "kind": "received_for_pending_collection", "message": copy.deepcopy(envelope)})
            else:
                # A reply is triggered only by an actually delivered source
                # message, never by host knowledge of the peer's pending work.
                phase = invitation_phase(envelope, self.owner, view["now"])
                if phase is None or phase in self.answered_phases:
                    self.exchanges.append({"at": view["now"], "kind": "not_an_unanswered_phase_invitation", "message": copy.deepcopy(envelope)})
                    continue
                self.answered_phases.add(phase)
                causal = {"relation": "result_handling", "continuation_parent_roots": [],
                    "delivered_parent_message": {"message_id": identity, "source_owner": local["source_owner"],
                        "captured_at": local["captured_at"], "delivered_at": envelope["delivered_at"]},
                    "cross_owner_creating_request_root": "unknown_not_transmitted"}
                refresh = []
                if phase == "reuse1_loading_ack_refresh" and self.owner == "A":
                    for identity, row in self.client.owned("A").items():
                        request = row["request"]
                        if (row["kind"] == "transfer" and request.get("tray_id") == "L" and request.get("source") == 6
                                and request.get("destination") == 7 and not row["terminal"]):
                            self.client.send(identity, retry=True)
                            refresh.append(identity)
                if refresh:
                    causal["continuation_parent_roots"] = [self.client.creations[i]["creating_root"] for i in refresh]
                    causal["immutable_retry_request_ids"] = refresh
                    self.pending_reply = {"phase": phase, "causal": causal, "envelope": copy.deepcopy(envelope), "waiting": refresh}
                    self.exchanges.append({"at": view["now"], "kind": "immutable_ack_refresh_before_reply",
                        "message": copy.deepcopy(envelope), "request_ids": refresh, "causal": copy.deepcopy(causal)})
                else:
                    reply = self.publication("reply", causal)
                    self.exchanges.append({"at": view["now"], "kind": "reply", "message": copy.deepcopy(envelope), "request_id": reply})

    def finish_deferred_reply(self, view):
        pending = self.pending_reply
        if not pending: return
        if view["now"] >= pending["envelope"]["capture"]["local_capture"]["valid_until"]:
            self.exchanges.append({"at": view["now"], "kind": "unknown_expired_preflight_reply", "pending": copy.deepcopy(pending)})
            self.pending_reply = None; return
        if not all(self.client.rows[i].get("ack", {}).get("status") == "received"
            and self.client.rows[i]["ack"].get("delivered_at", math.inf) <= view["now"] for i in pending["waiting"]): return
        causal = copy.deepcopy(pending["causal"])
        causal["delivered_terminal_acknowledgements"] = {i: copy.deepcopy(self.client.rows[i]["ack"]) for i in pending["waiting"]}
        reply = self.publication("reply-after-ack", causal)
        self.exchanges.append({"at": view["now"], "kind": "reply_after_delivered_received_ack", "request_id": reply,
            "causal": causal, "message": pending["envelope"]})
        self.pending_reply = None

    def decide_pending(self, view):
        pending = self.pending
        if not pending: return
        own = self.client.rows[pending["request_id"]].get("ack", {})
        pair_ready = own.get("status") == "delivered" and pending["peer_message"] is not None
        if not pair_ready and view["now"] < pending["deadline"]: return
        information = adapter.collect_native(self.native, self.session, self.owner, pending["request_id"],
            ledger=self.ledger, owned_client_rows=self.client.owned(self.owner), phase=pending["phase"],
            peer_message_id=pending["peer_message"], collection_started_at=pending["at"])
        decision = choose(information, self.method)
        selected = decision.get("selected_action")
        fallback = selected is None
        action = selected or {"reuse_next": 3, "return_delay": 0.}
        causal = {"relation": "fallback" if fallback else "result_handling",
            "continuation_parent_roots": [pending["root"]], "predecessor_protocol_id": pending["request_id"],
            "delivered_peer_message_id": pending["peer_message"], "collection_started_at": pending["at"]}
        actual = None
        if pending["phase"] == "first_return":
            tray = next((t for t in view["trays"] if t["tray_id"] == "L" and t["node"] == 6 and t["mode"] == "empty"
                         and t["edge_to"] < 0 and t["available_at"] <= view["now"]), None)
            demand = v1.latest_demand(view, "B")
            if tray and demand and any(j["origin"] == 7 for j in demand["jobs"]):
                actual = self.return_tray(view, tray, demand, action["return_delay"], causal)
        else:
            tray = next((t for t in view["trays"] if t["tray_id"] == "L" and t["node"] == 7 and t["mode"] == "loaded"
                         and t["edge_to"] < 0 and t["business_bag_id"] == "reuse1"), None)
            if tray: actual = self.route_tray(view, tray, action["reuse_next"], causal)
        self.decisions.append({"at": view["now"], "phase": pending["phase"], "collection": copy.deepcopy(pending),
            "information": information, "decision": decision, "fallback_used": fallback, "executed_first_action": action,
            "native_request_id": actual, "actual_local_view": copy.deepcopy(view),
            "future_proposal_component_executed_without_replan": False})
        self.pending = None

    def return_tray(self, view, tray, demand, delay, causal):
        identity = self.client.submit("A", "transfer", f"return-{len(self.returns)}", causal=causal,
            tray_id="L", source=6, destination=7, earliest_departure=view["now"] + delay,
            expiry=v1.HORIZON - 1., message_delay=.01)
        self.returns.append({"at": view["now"], "request_id": identity, "tray": copy.deepcopy(tray),
            "delivered_demand": copy.deepcopy(demand), "selected_delay": delay})
        return identity

    def route_tray(self, view, tray, next_node, causal):
        identity = self.client.submit("B", "route", f"later-route-{len(self.choices)}", causal=causal,
            business_bag_id=tray["business_bag_id"], tray_id="L", **{"from": 7, "next": next_node},
            expected_generation=tray["generation"], expected_traversal=tray["traversal_id"],
            expiry=view["now"] + 5., message_delay=.01)
        self.choices.append({"at": view["now"], "request_id": identity, "job": tray["business_bag_id"],
            "next": next_node, "local_tray": copy.deepcopy(tray), "known_delivered_preference": None})
        self.route_keys.add((tray["business_bag_id"], tray["generation"], tray["traversal_id"]))
        return identity

    def activate(self, trigger):
        root = self.client.activate(self.owner, trigger)
        self.client.refresh_owner(self.owner)
        view = self.session.observe_protocol(self.owner)
        signature = self.session.protocol_demand_signature(self.owner)
        old = self.client.rows[self.channel]
        if old["terminal"] and old["ack"].get("captured_demand_signature") != signature:
            self.channel = self.client.submit(self.owner, "demand", f"demand-{len(self.client.roots)}",
                target_owner=self.peer, message_delay=.01, publication_delay=.01)
        self.exchange(view)
        self.finish_deferred_reply(view)
        self.decide_pending(view)
        if self.owner == "A":
            tray = next((t for t in view["trays"] if t["tray_id"] == "L" and t["node"] == 6
                and t["mode"] == "empty" and t["edge_to"] < 0 and t["available_at"] <= view["now"]), None)
            demand = v1.latest_demand(view, "B")
            waiting = self.returns and not self.client.rows[self.returns[-1]["request_id"]]["terminal"]
            if tray and not waiting and len(self.returns) < 2 and demand and any(j["origin"] == 7 for j in demand["jobs"]):
                if "first_return" not in self.started: self.begin("first_return", tray, root)
                elif self.pending is None and self.returns:
                    self.return_tray(view, tray, demand, 0., {"relation": "independent_offer", "continuation_parent_roots": [],
                        "local_trigger": "second_available_empty_return", "delivered_demand_id": demand["message_id"]})
        else:
            if self.supplies:
                basis = v2.recovery_basis(view, self.client.rows[self.supplies[-1]], len(self.supplies))
                if basis:
                    previous = self.supplies[-1]
                    identity = self.client.submit("B", "transfer", f"supply-recovery-{len(self.supplies)}",
                        causal={"relation": "replacement_replan", "predecessor_protocol_id": previous,
                            "continuation_parent_roots": [self.client.creations[previous]["creating_root"]],
                            "delivered_rejection": basis["delivered_rejection"]}, tray_id="E", source=5, destination=1,
                        earliest_departure=view["now"], expiry=v1.HORIZON - 1., message_delay=.01)
                    self.supplies.append(identity); self.recovery.append({**basis, "request_id": identity})
            for tray in view["trays"]:
                if (tray["tray_id"] == "L" and tray["node"] == 7 and tray["mode"] == "loading"
                        and tray["edge_to"] < 0 and tray["business_bag_id"] == "reuse1" and "reuse1_loading_ack_refresh" not in self.started):
                    self.started.add("reuse1_loading_ack_refresh")
                    identity = self.publication("preflight", {"relation": "independent_offer", "continuation_parent_roots": [],
                        "local_trigger": {"phase": "reuse1_loading_ack_refresh", "tray": copy.deepcopy(tray)}})
                    self.exchanges.append({"at": view["now"], "kind": "preflight_from_local_loading", "request_id": identity,
                        "local_tray": copy.deepcopy(tray)})
                if tray["tray_id"] != "L" or tray["node"] != 7 or tray["mode"] != "loaded" or tray["edge_to"] >= 0: continue
                key = (tray["business_bag_id"], tray["generation"], tray["traversal_id"])
                if key in self.route_keys: continue
                if tray["business_bag_id"] == "reuse1" and "first_reuse_route" not in self.started:
                    self.begin("first_reuse_route", tray, root)
                elif tray["business_bag_id"] == "reuse2":
                    self.route_tray(view, tray, 3, {"relation": "independent_offer", "continuation_parent_roots": [],
                        "local_trigger": "second_loaded_reuse"})


def run_branch(native, row):
    data = v1.scene(row["gate"]); data["owner_notifications"] = {"enabled": True}
    session = native.NativeSession(data); session.advance_to(.05)
    client = LocalTransport(session); channels, planning = {}, {}
    for owner, peer in (("A", "B"), ("B", "A")):
        client.activate(owner, {"kind": "initial_public_epoch", "at": .05})
        channels[owner] = client.submit(owner, "demand", "seed-demand", target_owner=peer, message_delay=.01, publication_delay=.01)
        planning[owner] = client.submit(owner, "planning_snapshot", "initial-planning", target_owner=peer,
            message_delay=.01, publication_delay=.01, expiry=.21)
    session.advance_to(v1.START)
    ledgers, initial_owners = {}, {}
    for owner in ("A", "B"):
        client.activate(owner, {"kind": "initial_decision_epoch", "at": v1.START})
        client.refresh_owner(owner, retry=False)
        _, ledgers[owner] = adapter.collect_initial_ledger(native, session, owner, planning[owner])
        initial_owners[owner] = initial.owner_first_action(native, session, client, owner, planning[owner], "joint_model")
    selections = {o: v["decision"].get("selected_action") for o, v in initial_owners.items()}
    if any(ledgers[o] is None or selections[o] is None for o in ("A", "B")) or selections["A"] != selections["B"]:
        return {"specification": row, "input": data, "initial_owners": initial_owners,
            "summary": {"status": "unknown_initial_asymmetry_or_missing_ledger"}}
    policies = {o: OwnerPolicy(native, session, client, o, ledgers[o], channels[o], row["method"],
        initial_owners[o]["native_request_id"] if o == "B" else None) for o in ("A", "B")}
    cursors = {o: 0 for o in policies}; tick = 0; batches = []; activations = 0
    status = "finished"
    while session.physical_time < v1.HORIZON and activations < MAX_ACTIVATIONS:
        deadline = min(v1.HORIZON, v1.START + tick * v1.PERIOD,
            *(p.pending["deadline"] for p in policies.values() if p.pending))
        if deadline < session.physical_time: raise ValueError("rolling_joint:missed_deadline")
        response = session.advance_until_owner_notification(["A", "B"], cursors, deadline, max_events=100000)
        batches.append({"deadline": deadline, "response": copy.deepcopy(response)})
        if response["status"] not in {"notified", "horizon_reached"} or response.get("timestamp_complete") is not True:
            status = "unknown_native_boundary"; break
        now = session.physical_time
        due_tick = now == v1.START + tick * v1.PERIOD
        if due_tick: tick += 1
        notices = response.get("notifications", {})
        due = {o for o in policies if due_tick or o in notices or policies[o].pending and now >= policies[o].pending["deadline"]}
        for owner, notice in notices.items(): cursors[owner] = notice["sequence"]
        for owner in sorted(due):
            policies[owner].activate({"native_notification": copy.deepcopy(notices.get(owner)), "periodic_tick": due_tick,
                "collection_deadline": bool(policies[owner].pending and now >= policies[owner].pending["deadline"])})
            activations += 1
    if activations >= MAX_ACTIVATIONS: status = "unknown_activation_budget"
    if status == "finished": session.advance_to(v1.HORIZON)
    for owner in policies:
        client.activate(owner, {"kind": "final_outbox_collection", "at": session.physical_time})
        client.refresh_owner(owner, retry=False)
    continuation = {"status": status, "route_choices": policies["B"].choices, "returns": policies["A"].returns,
        "supply_lineage": policies["B"].supplies, "recovery_decisions": policies["B"].recovery}
    result = session.result_at(session.physical_time)
    summary = v2.assess_cell(data, result, client, continuation, {**selections["A"], "later_mode": "rolling"})
    decisions = {o: p.decisions for o, p in policies.items()}
    flat = [d for rows in decisions.values() for d in rows]
    summary["rolling_model_inputs_verified"] = len(flat) == 2 and all(d["information"]["native_delivery_verified"] for d in flat)
    summary["rolling_fallback_count"] = sum(d["fallback_used"] for d in flat)
    summary["rolling_action_count"] = sum(d["native_request_id"] is not None for d in flat)
    summary["prediction_errors"] = [{"phase": d["phase"], "status": d["decision"].get("status"),
        "native_minus_selected_prediction": {j: summary["completion"][j] - t for j, t in d["decision"].get("selected_prediction", {}).get("completion", {}).items()}
            if summary["business_complete"] else None} for d in flat]
    return {"specification": copy.deepcopy(row), "input": data, "initial_owners": initial_owners,
        "retained_ledgers": {o: l.audit_copy() for o, l in ledgers.items()}, "decisions": decisions,
        "exchanges": {o: p.exchanges for o, p in policies.items()}, "calls": client.calls, "outbox": client.rows,
        "request_creations": client.creations, "owner_activation_admissions": client.roots, "ack_handling": client.ack_handling,
        "lineage_status": "experimental_proxy_causes_only_cross_owner_roots_not_transmitted_no_business_denominator_certificate",
        "continuation": continuation, "native_batches": batches, "result": result, "summary": summary}


def assess(rows):
    comparisons = {}
    for gate in v1.GATES:
        group = {m: rows[f"gate{int(gate)}/{m}"] for m in METHODS}
        if any(r["status"] != "assessed" for r in group.values()):
            comparisons[str(gate)] = {"status": "unknown_incomplete_comparison", "rows": group}; continue
        base = group["frozen_later"]["summary"]["completion"]
        comparisons[str(gate)] = {"status": "assessed", "all_offered_count": 4, "methods": {
            method: {"completion": r["summary"]["completion"],
                "strict_protected": all(r["summary"]["completion"][j] <= base[j] for j in model.JOBS),
                "gain_vs_matched_frozen": sum(base.values()) - r["summary"]["completion_sum"],
                "all_later_inputs_verified": r["summary"]["rolling_model_inputs_verified"],
                "fallback_count": r["summary"]["rolling_fallback_count"]} for method, r in group.items()}}
    return comparisons


def prepare(output):
    output.mkdir(parents=True, exist_ok=False); plan = protocol()
    modules = (adapter, initial_adapter, extension, encoding, model, model.initial, initial, v1, v2, native_host)
    sources = sorted({Path(m.__file__).resolve() for m in modules} | {Path(__file__).resolve()})
    plan["source_sha256"] = {str(p): sha(p) for p in sources}
    archive = output/"source"; archive.mkdir()
    for p in sources: (archive/p.name).write_bytes(p.read_bytes())
    write(output/"preregistered_protocol.json", plan); write(output/"branch_ledger.json", plan["rows"])
    return plan


def worker(args):
    plan = json.loads((args.output/"preregistered_protocol.json").read_text())
    if any(sha(p) != h for p, h in plan["source_sha256"].items()) or sha(args.binary) != args.expected_binary_sha256:
        raise ValueError("rolling_joint:frozen_identity_changed")
    native = load_native(args.binary); rows = copy.deepcopy(plan["rows"]); start = time.perf_counter()
    for key, row in rows.items():
        row["status"] = "unknown_in_progress"; write(args.output/"branch_ledger.json", rows)
        try:
            raw = run_branch(native, row); path = args.output/(key+".json.gz"); path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(path, "wt", encoding="utf-8", compresslevel=1) as stream: json.dump(raw, stream, allow_nan=False)
            row.update(status=raw["summary"]["status"], summary=raw["summary"])
        except Exception: row.update(status="unknown_failed", exception=traceback.format_exc())
        write(args.output/"branch_ledger.json", rows)
    changed = [p for p, h in plan["source_sha256"].items() if sha(p) != h]
    receipt = {"schema": "g31.lt2.native_public_rolling_joint_receipt.v1", "status": ("executed" if all(r["status"] == "assessed" for r in rows.values()) else "completed_with_unknowns") if not changed else "invalidated_source_drift",
        "source_changed": changed, "binary_sha256": sha(args.binary), "branch_count": len(rows),
        "branch_status_counts": {s: sum(r["status"] == s for r in rows.values()) for s in sorted({r["status"] for r in rows.values()})},
        "comparisons": assess(rows), "wall_seconds": time.perf_counter()-start, "native_forks_used": 0,
        "native_results_used_for_policy": False, "model_protection_certified": False,
        "atomic_agreement_certified": False, "complete_request_100ms_certified": False}
    write(args.output/"receipt.json", receipt); print(json.dumps(receipt, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path); parser.add_argument("--expected-binary-sha256")
    parser.add_argument("--execute", action="store_true"); parser.add_argument("--worker", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=120.)
    args = parser.parse_args()
    if args.worker: worker(args); return
    plan = prepare(args.output)
    if not args.execute: print(json.dumps({"status": "prepared_no_native_calls", "branches": len(plan["rows"])})); return
    if not args.binary or not args.expected_binary_sha256: parser.error("exact binary identity required")
    command = [sys.executable, "-m", __spec__.name, "--worker", "--output", str(args.output), "--binary", str(args.binary),
        "--expected-binary-sha256", args.expected_binary_sha256]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout_seconds)
        (args.output/"worker.stdout.log").write_text(done.stdout, encoding="utf-8")
        (args.output/"worker.stderr.log").write_text(done.stderr, encoding="utf-8")
        if done.returncode: write(args.output/"worker_failure.json", {"status": "unknown_failed", "exitcode": done.returncode})
    except subprocess.TimeoutExpired:
        write(args.output/"worker_failure.json", {"status": "unknown_timeout", "seconds": args.timeout_seconds})


if __name__ == "__main__": main()
