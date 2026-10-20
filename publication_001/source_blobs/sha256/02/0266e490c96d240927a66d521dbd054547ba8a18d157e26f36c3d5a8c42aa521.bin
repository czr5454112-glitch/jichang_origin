"""Separate native027 two-stage rolling proposal with source-observed v3 facts.

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
from . import native_preexisting_v3_adapter as adapter
from . import native027_request_timing as native_acceptance
from . import native027_timing_gate as accepted_raw_gate
from . import run_native027_semantic_gate as semantic_acceptance
from . import native_preexisting_initial_adapter as initial_adapter
from . import planning_capture_v2_contract as extension
from . import planning_capture_v2_digest as encoding
from . import public_preexisting_model as initial_model
from . import public_preexisting_v3_model as model
from . import research_preexisting_occupancy_domain as domain
from . import research_synthetic_reuse_chain as v1
from . import research_synthetic_reuse_v2 as v2
from . import native_host
from . import verify_preexisting_delivery as delivery_evidence
from .native_host import load_native

METHODS = ("frozen_later", "fixed_window_0", "fixed_window_1", "fixed_window_2", "fixed_window_3", "coordinate_strict", "coordinate_plateau", "resource_pair_repair", "finite_horizon_enumeration", "enumeration_fixed3")
COLLECTION_LIMIT = .08
CAPTURE_VALIDITY = .2
MAX_ACTIVATIONS = 10000


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path, value): path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def verify_semantic_gate(reference, contract):
    result = semantic_acceptance.verify_saved_semantic_gate(reference,
        expected_binary_sha256=contract["binary_sha256"])
    if result.get("status") != "validated_native027_finite_semantic_regression" or result.get("passed") != 21:
        raise ValueError("preexisting_v3:closed_semantic_gate_not_accepted")
    return {"status": "passed_actual_native027_semantic_gate", "reference": copy.deepcopy(reference),
        "verification": result}


def native_scene(case, fault=None):
    """Versioned native input: rebuild the derived matrix after node9 exists.

    The saved192 pure projections retain their original nine-row heuristic.
    This correction changes only derived preprocessing for this new campaign.
    """
    if case not in domain.cases() or fault not in (None, "missing_peer", "expired_capture", "lost_self_ack"):
        raise ValueError("preexisting:undeclared_case_or_fault")
    data = native_host.prepare_input(copy.deepcopy(domain.make_bundle(case)["contract"]))
    data["owner_notifications"] = {"enabled": True}
    if fault == "lost_self_ack": data["owner_protocol"]["drop_ack_packets"] = 3
    size = len(data["node_records"])
    if len(data["heuristic_time"]) != size or any(len(row) != size for row in data["heuristic_time"]):
        raise ValueError("preexisting:derived_potential_dimension_mismatch")
    return data


def config_sha(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def imported_sources():
    """Pin the actual loaded project Python closure, including potential code.

    The worker checks this same set before and after execution. A newly loaded
    project module invalidates the run instead of silently extending authority.
    Stdlib/site-packages are environment dependencies, separately identified by
    the interpreter; they are not described as archived project sources.
    """
    root = Path(__file__).resolve().parents[3]
    paths = {Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        name = getattr(module, "__file__", None)
        if name:
            path = Path(name).resolve()
            if path.suffix == ".py" and path.is_relative_to(root): paths.add(path)
    return sorted(paths)


def protocol(phase="delivery_gate"):
    if phase not in ("delivery_gate", "business"): raise ValueError("undeclared_phase")
    if phase == "business":
        rows = {case["case_id"] + "/" + method: {"case": case, "method": method, "fault": None, "status": "unknown_unexecuted"}
                for case in domain.cases() for method in METHODS}
    else:
        rows = {case["case_id"] + "/delivery": {"case": case, "method": "delivery_only", "fault": None, "status": "unknown_unexecuted"}
                for case in domain.cases()}
        for fault in ("missing_peer", "expired_capture", "lost_self_ack"):
            rows["readiness/" + fault] = {"case": domain.cases()[4], "method": "delivery_only", "fault": fault, "status": "unknown_unexecuted"}
    return {"schema": "g31.lt2.native_preexisting_v3.v1", "phase": phase, "native_branch_budget": len(rows), "rows": rows,
        "all_offered_jobs": sorted(model.JOBS), "all_physical_trays": ["L", "E", "P"], "horizon": 40.,
        "configuration_sha256": {case["case_id"]: config_sha(native_scene(case)) for case in domain.cases()},
        "row_configuration_sha256": {key: config_sha(native_scene(row["case"], row["fault"])) for key, row in rows.items()},
        "derived_contract_correction": "new native inputs recompute 10x10 service-aware potential after adding node9/edge1to9; old192 configs/projections remain immutable and used no heuristic matrix",
        "source": "NEW synthetic3tray5job public pre-existing occupancy; no original inputs modified",
        "initial_information": "each owner independently uses its actual delivered v1 peer capture and own delivered selfACK; case inferred only from the complete captured5job contracts; known L load projection and stationary P load bound",
        "initial_action": "AL0 always sends explicit desired next1/2 with current owner/generation/traversal. Default native queue-aware next cannot stand in for fixedroute1. BE5 sends selected immutable transfer.",
        "fixed_initial_family": "all4 public E timing windows independently executed per case, each fixedinitial1; future return/later choices recomputed with finite model enumeration from same delivered facts",
        "initial_budget": 32, "later_budget": 32, "later_action_domain": [{"return_delay": t, "reuse_next": n} for t in (0., .5) for n in (3, 8)],
        "later_rule": "actual first emptyL6 and then actual loadedreuse1L7; fresh accepted native027 v3 selfACK+selected peer message and source-observed in-flight receipt; terminalP receipt and actual parkedP9 required; execute only current owner first action",
        "preflight": "unchanged bounded actual BloadingL invitation causes A immutable pendingreturn retry; reply only after delivered receivedACK; fresh later pair and unchanged .05age still required",
        "unsupported": "Only E already observed entering1to3/3to4 may extend the stationary domain. Missing identity/receipt/coverage, transitions across the actual capture union, unresolvedactions, missingterminalP, late/expired pair remain unknown with common fallback0/3. No age extension or future event heap.",
        "collection_policy_amendment": "NEW common public policy: initiating owner admits no new physical operation while collection pending; reply owner holds new physical admissions for0.08s after answering a first_return/first_reuse_route invitation. Native physics and immutable retries continue. This cannot prove quiescence: complete source action coverage and unchanged strict capture-union guards remain required.",
        "runtime_admission": "closed native027 saved-raw legacy/v3/timing gate plus independently pinned21-test source/binary/XML semantic receipt required before any NativeSession construction",
        "action_union_guard": "Every source retains the complete submitted physical-action set and terminal delivered ACKs. All such ACKs must be strictly before the earliest source capture; same-time/late/missing ACKs are unknown, with no inverse inference of execution time. Reply hold does not cover its earlier pre-invitation gap.",
        "delivery_gate_scope": "The nine rows exercise initial v1 planning pairs on the accepted027 artifact. They do not validate actual later v3 model input; that occurs only in retained business rows after separate21/44 native gates.",
        "incumbent": "initial1/E2.21, later0/3, same communication traffic and captured information",
        "late_ablation": "enumeration_fixed3 recomputes same Areturn proposal but forcesB firstreuse3; selectedprediction recomputed for executedaction and originalproposal retained",
        "fairness": "same full5jobs/3trays/staticgraph/capacities/FIFO/headways/protocol and recovery within each case; all methods same facts and budget",
        "objective": "strict all5 modeled job protection vs same-input incumbent and completion-sum; no calibrated model error bound",
        "physical_assessment": "commonH40, all5actualcompletions, full3tray audit, allnativeACKs, explicitinitialedge and2reuseedges, two actualsameLreturns; incomplete/failed kept unknown",
        "comparison": "all5 completion deltas<=0 withzero tolerance vs matched incumbent and complete4-arm fixed-initial family; unfinished/censored never0gain",
        "fault_rows": "delivery gate only, no actions/businessmetrics: Apublication delay.1, expiry.08, or first3ACKdrops; actual readiness/asymmetry preserved",
        "delivery_evidence": "retain exact own view/command/recipient inbox at .11 for all9 rows, including failures; independent raw digest, causal time, source-scope, fault-specific reason and input/source archive/hash verification required before business admission",
        "limits": ["SYNTHETIC, not original benefit", "native delivery does not certify model protection", "no atomicagreement", "no search novelty", "not100ms business-request evidence"]}


def choose(information, method):
    if method not in METHODS: raise ValueError("rolling_joint:undeclared_method")
    if (not adapter.is_native_collected(information)
            or information.get("status") != "conditional_native_delivered_later_v3_model_input"
            or information.get("native_delivery_verified") is not True):
        return {"status": "unknown_unverified_or_unsupported_input", "selected_action": None}
    bundle = information["bundle"]
    if method == "frozen_later":
        action = {"reuse_next": 3, "return_delay": 0.}
        return {"status": "declared_frozen_later", "selected_action": action,
            "selected_prediction": model.predict(bundle, action), "native_protection_certified": False}
    algorithm = "finite_horizon_enumeration" if method.startswith("fixed_window_") or method == "enumeration_fixed3" else method
    result = model.propose(bundle, method=algorithm, evaluation_budget=32)
    if method == "enumeration_fixed3" and bundle["phase"] == "first_reuse_route" and result.get("selected_action"):
        result["ablation_original_proposal"] = copy.deepcopy(result["selected_action"])
        result["selected_action"]["reuse_next"] = 3
        result["selected_prediction"] = model.predict(bundle, result["selected_action"])
        result["ablation"] = "explicit_later3_with_same_initial_and_return_policy"
    return result


def invitation_phase(envelope, owner, now):
    """Finite fixture invitation from actual source facts, no synthetic tag.

    A reply capture cannot contain the initiating peer's locally held L. Each
    phase is answered at most once, including after a collection timeout.
    """
    try:
        local = envelope["capture"]["capture_v2"]["local_capture"]
        source = {"A": "B", "B": "A"}[owner]
        if (envelope.get("schema") != "g31.planning_snapshot.v3" or envelope.get("kind") != "planning_snapshot_v3"
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
    def __init__(self, native, session, client, owner, ledger, channel, method, accepted, supply=None):
        self.native, self.session, self.client, self.owner = native, session, client, owner
        self.peer = "B" if owner == "A" else "A"
        self.ledger, self.channel, self.method = ledger, channel, method
        self.accepted = accepted
        self.peer_quiet_until = -1.
        self.quiet_periods = []
        self.pending = None; self.seen_messages = set(); self.started = set()
        self.answered_phases = set()
        self.pending_reply = None
        self.decisions, self.exchanges, self.returns, self.choices, self.recovery = [], [], [], [], []
        self.supplies = [supply] if supply else []
        self.route_keys = set(); self.serial = 0

    def publication(self, label, causal):
        self.serial += 1
        return self.client.submit(self.owner, "planning_snapshot_v3", f"rolling-{label}-{self.serial}",
            causal=causal, target_owner=self.peer, message_delay=.01, publication_delay=.01,
            expiry=self.session.physical_time + CAPTURE_VALIDITY)

    def begin(self, phase, tray, root):
        self.started.add(phase)
        identity = self.publication(phase, {"relation": "independent_offer", "continuation_parent_roots": [],
            "local_trigger": {"phase": phase, "tray": copy.deepcopy(tray)}})
        self.pending = {"phase": phase, "at": self.session.physical_time, "deadline": self.session.physical_time + COLLECTION_LIMIT,
            "request_id": identity, "root": root, "trigger_tray": copy.deepcopy(tray), "peer_message": None}
        self.quiet_periods.append({"at": self.session.physical_time, "through": self.pending["deadline"],
            "reason": "local_collection_pending", "phase": phase, "native_physics_paused": False})

    def hold_new_admissions_after_reply(self, phase, identity, now):
        if phase not in ("first_return", "first_reuse_route"): return
        self.peer_quiet_until = max(self.peer_quiet_until, now + COLLECTION_LIMIT)
        self.quiet_periods.append({"at": now, "through": self.peer_quiet_until,
            "reason": "delivered_peer_phase_reply", "phase": phase, "message_id": identity,
            "native_physics_paused": False})

    def exchange(self, view):
        for envelope in self.session.protocol_planning_snapshots_v3(self.owner):
            local = envelope["capture"]["capture_v2"]["local_capture"]; identity = local["message_id"]
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
                    self.hold_new_admissions_after_reply(phase, identity, view["now"])
                    self.exchanges.append({"at": view["now"], "kind": "reply", "message": copy.deepcopy(envelope), "request_id": reply})

    def finish_deferred_reply(self, view):
        pending = self.pending_reply
        if not pending: return
        if view["now"] >= pending["envelope"]["capture"]["capture_v2"]["local_capture"]["valid_until"]:
            self.exchanges.append({"at": view["now"], "kind": "unknown_expired_preflight_reply", "pending": copy.deepcopy(pending)})
            self.pending_reply = None; return
        if not all(self.client.rows[i].get("ack", {}).get("status") == "received"
            and self.client.rows[i]["ack"].get("delivered_at", math.inf) <= view["now"] for i in pending["waiting"]): return
        causal = copy.deepcopy(pending["causal"])
        causal["delivered_terminal_acknowledgements"] = {i: copy.deepcopy(self.client.rows[i]["ack"]) for i in pending["waiting"]}
        reply = self.publication("reply-after-ack", causal)
        self.hold_new_admissions_after_reply(pending["phase"], pending["envelope"]["capture"]["capture_v2"]["local_capture"]["message_id"], view["now"])
        self.exchanges.append({"at": view["now"], "kind": "reply_after_delivered_received_ack", "request_id": reply,
            "causal": causal, "message": pending["envelope"]})
        self.pending_reply = None

    def decide_pending(self, view):
        pending = self.pending
        if not pending: return
        if view["now"] < self.peer_quiet_until:
            return  # A simultaneous local collection cannot break a peer hold.
        own = self.client.rows[pending["request_id"]].get("ack", {})
        pair_ready = own.get("status") == "delivered" and pending["peer_message"] is not None
        if not pair_ready and view["now"] < pending["deadline"]: return
        information = adapter.collect_native(self.native, self.session, self.owner, pending["request_id"],
            accepted=self.accepted, ledger=self.ledger, owned_client_rows=self.client.owned(self.owner), phase=pending["phase"],
            peer_message_id=pending["peer_message"], collection_started_at=pending["at"], policy_quiet_since=pending["at"])
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
        if self.pending is not None or view["now"] < self.peer_quiet_until:
            return  # Native transitions and immutable retries above still run.
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


def owner_first_action(native, session, client, owner, planning_id, method, accepted):
    information, ledger = adapter.collect_initial_ledger(native, session, owner, planning_id, accepted=accepted)
    decision = {"status": "unknown_unverified_initial_input", "selected_action": None}; identity = None
    view = session.observe_protocol(owner)
    if information.get("native_delivery_verified"):
        bundle = information["bundle"]
        if method == "frozen_later":
            action = domain.domain(bundle["case_from_delivered_contracts"])["incumbent"]
            decision = {"status": "declared_incumbent", "selected_action": action, "selected_prediction": initial_model.initial_predict(bundle, action)}
        else:
            fixed = int(method.rsplit("_", 1)[1]) if method.startswith("fixed_window_") else None
            algorithm = "finite_horizon_enumeration" if fixed is not None or method == "enumeration_fixed3" else method
            decision = initial_model.propose_initial(bundle, algorithm, fixed_window=fixed)
        action = decision.get("selected_action")
        if action and owner == "A":
            tray = next((t for t in view["trays"] if t["tray_id"] == "L" and t["node"] == 0 and t["mode"] == "loaded" and t["business_bag_id"] == "loaded" and t["edge_to"] < 0), None)
            if tray:
                identity = client.submit(owner, "route", "initial-route", business_bag_id="loaded", tray_id="L",
                    **{"from": 0, "next": action["initial_next"]}, expected_generation=tray["generation"], expected_traversal=tray["traversal_id"],
                    expiry=5., message_delay=.01, causal={"relation": "result_handling", "predecessor_protocol_id": planning_id,
                        "continuation_parent_roots": [client.creations[planning_id]["creating_root"]]})
        elif action:
            tray = next((t for t in view["trays"] if t["tray_id"] == "E" and t["node"] == 5 and t["mode"] == "empty" and t["edge_to"] < 0 and t["available_at"] <= view["now"]), None)
            if tray: identity = client.submit(owner, "transfer", "initial-supply", tray_id="E", source=5, destination=1,
                earliest_departure=action["departure"], expiry=39., message_delay=.01,
                causal={"relation": "result_handling", "predecessor_protocol_id": planning_id,
                    "continuation_parent_roots": [client.creations[planning_id]["creating_root"]]})
        if action and identity is None: decision = {"status": "unknown_local_action_precondition", "selected_action": None}
    return {"owner": owner, "at": view["now"], "information": information, "decision": decision,
        "native_request_id": identity, "local_action_view": view}, ledger


def run_branch(native, row, contract_reference, semantic_gate_binding):
    if semantic_gate_binding.get("status") != "passed_actual_native027_semantic_gate":
        raise ValueError("preexisting_v3:semantic_gate_missing")
    # A caller dictionary is insufficient: re-read the closed verifier before
    # constructing this branch's native session, including the pinned XML and
    # actual test fixture binary provenance.
    semantic_gate_binding = verify_semantic_gate(semantic_gate_binding["reference"],
        {"binary_sha256": native._g31_native_artifact_identity["sha256"]})
    runtime = native_acceptance.verify_contract(contract_reference, require_runtime=True)
    if runtime["contract"]["binary_sha256"] != native._g31_native_artifact_identity["sha256"]:
        raise ValueError("preexisting_v3:runtime_gate_loaded_binary_mismatch")
    data = native_scene(row["case"], row.get("fault"))
    session = native.NativeSession(data)
    admission, accepted = adapter.bind_native027(native, session, contract_reference)
    if accepted is None: raise ValueError("preexisting_v3:runtime_acceptance_rejected:" + str(admission))
    session.advance_to(.05)
    client = LocalTransport(session); channels, planning = {}, {}
    for owner, peer in (("A", "B"), ("B", "A")):
        client.activate(owner, {"kind": "initial_public_epoch", "at": .05})
        channels[owner] = client.submit(owner, "demand", "seed-demand", target_owner=peer, message_delay=.01, publication_delay=.01)
        planning[owner] = client.submit(owner, "planning_snapshot", "initial-planning", target_owner=peer,
            message_delay=.01, publication_delay=.1 if row.get("fault") == "missing_peer" and owner == "A" else .01,
            expiry=.08 if row.get("fault") == "expired_capture" else .21)
    session.advance_to(v1.START)
    ledgers, initial_owners = {}, {}
    for owner in ("A", "B"):
        client.activate(owner, {"kind": "initial_decision_epoch", "at": v1.START}); client.refresh_owner(owner, retry=False)
        if row["method"] == "delivery_only":
            endpoints = {"view": session.observe_protocol(owner), "command": session.protocol_command(owner, planning[owner]),
                "received": session.protocol_planning_snapshots(owner)}
            info, ledger = adapter.collect_initial_ledger(native, session, owner, planning[owner], accepted=accepted); ledgers[owner] = ledger
            initial_owners[owner] = {"owner": owner, "information": info, "raw_endpoints": endpoints,
                "decision": {"status": "delivery_probe_only", "selected_action": None}, "native_request_id": None}
        else:
            initial_owners[owner], ledgers[owner] = owner_first_action(native, session, client, owner, planning[owner], row["method"], accepted)
    if row["method"] == "delivery_only":
        return {"specification": row, "input": data, "initial_owners": initial_owners, "calls": client.calls, "outbox": client.rows,
            "summary": {"status": "readiness_observed", "both_inputs_verified": all(r["information"].get("native_delivery_verified") for r in initial_owners.values()),
                "owner_status": {o: r["information"]["status"] for o, r in initial_owners.items()}, "business_metrics": None, "physical_protection": "not_assessed"}}
    selections = {o: value["decision"].get("selected_action") for o, value in initial_owners.items()}
    if any(ledgers[o] is None or selections[o] is None for o in ("A", "B")) or selections["A"] != selections["B"]:
        session.advance_to(v1.HORIZON)
        return {"specification": row, "input": data, "initial_owners": initial_owners, "calls": client.calls, "outbox": client.rows,
            "result": session.result_at(session.physical_time), "summary": {"status": "unknown_initial_asymmetry_or_missing_ledger", "business_metrics": None}}
    policies = {o: OwnerPolicy(native, session, client, o, ledgers[o], channels[o], row["method"], accepted,
        initial_owners[o]["native_request_id"] if o == "B" else None) for o in ("A", "B")}
    cursors = {o: 0 for o in policies}; tick = 0; batches = []; activations = 0
    status = "finished"
    while session.physical_time < v1.HORIZON and activations < MAX_ACTIVATIONS:
        deadline = min(v1.HORIZON, v1.START + tick * v1.PERIOD,
            *(max(p.pending["deadline"], p.peer_quiet_until) for p in policies.values() if p.pending))
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
    summary = assess_cell(data, result, client, continuation, {**selections["A"], "later_mode": "rolling"})
    decisions = {o: p.decisions for o, p in policies.items()}
    flat = [d for rows in decisions.values() for d in rows]
    summary["rolling_model_inputs_verified"] = len(flat) == 2 and all(d["information"]["native_delivery_verified"] for d in flat)
    summary["rolling_fallback_count"] = sum(d["fallback_used"] for d in flat)
    summary["rolling_action_count"] = sum(d["native_request_id"] is not None for d in flat)
    summary["conditional_stability_only"] = True
    summary["current_state_certified"] = False
    summary["native_model_protection_certified"] = False
    summary["joint_policy_evidence_status"] = ("conditional_model_actions_physically_assessed"
        if summary["status"] == "assessed" and summary["rolling_model_inputs_verified"]
        and summary["rolling_action_count"] == 2 and summary["rolling_fallback_count"] == 0
        else "unknown_joint_policy_effect_due_to_missing_input_action_or_physical_assessment")
    summary["prediction_errors"] = [{"phase": d["phase"], "status": d["decision"].get("status"),
        "native_minus_selected_prediction": {j: summary["completion"][j] - t for j, t in d["decision"].get("selected_prediction", {}).get("completion", {}).items()}
            if summary["business_complete"] else None} for d in flat]
    return {"specification": copy.deepcopy(row), "input": data, "initial_owners": initial_owners,
        "retained_ledgers": {o: l.audit_copy() for o, l in ledgers.items()}, "decisions": decisions,
        "exchanges": {o: p.exchanges for o, p in policies.items()}, "collection_policy_intervals": {o: p.quiet_periods for o,p in policies.items()},
        "native027_acceptance": accepted.audit_copy(), "calls": client.calls, "outbox": client.rows,
        "request_creations": client.creations, "owner_activation_admissions": client.roots, "ack_handling": client.ack_handling,
        "lineage_status": "experimental_proxy_causes_only_cross_owner_roots_not_transmitted_no_business_denominator_certificate",
        "continuation": continuation, "native_batches": batches, "result": result, "summary": summary}


def assess_cell(data: dict, result: dict, client, continuation: dict, specification: dict) -> dict:
    complete = (result["advance"]["status"] == "reached" and result["advance"]["horizon_complete"]
                and result["advance"]["physical_time"] == v1.HORIZON)
    jobs = {j["business_bag_id"]: j["completed_at"] for j in result["jobs"]}
    expected = {j["business_bag_id"] for j in data["jobs"]}
    business = (complete and len(result["jobs"]) == len(expected) and set(jobs) == expected
                and all(math.isfinite(t) and 0 <= t <= v1.HORIZON for t in jobs.values()))
    receipts = result["receipts"]
    line = continuation["supply_lineage"]
    supply = [client.rows[i] for i in line]
    returns = [client.rows[r["request_id"]] for r in continuation["returns"]]
    transfer_ids = {i for i, r in client.rows.items() if r["kind"] == "transfer"}
    ack_ok = lambda row, status: row.get("ack", {}).get("status") == status and 0 <= row["ack"].get("delivered_at", math.inf) <= v1.HORIZON
    supply_ok = (1 <= len(line) <= v2.SUPPLY_ATTEMPT_LIMIT and len(set(line)) == len(line)
        and ack_ok(supply[-1], "received") and all(ack_ok(r, "rejected") and r["ack"].get("reason") == "receiving_full" for r in supply[:-1]))
    recovery_ok = len(continuation["recovery_decisions"]) == len(line) - 1
    for index, decision in enumerate(continuation["recovery_decisions"]):
        predecessor = client.rows[line[index]]
        recovery_ok = recovery_ok and (decision["predecessor_request_id"] == line[index]
            and decision["request_id"] == line[index + 1] and decision["delivered_rejection"] == predecessor["ack"]
            and decision["at"] >= predecessor["ack"]["delivered_at"] + v2.REJECTION_COOLDOWN
            and decision["delivered_demand"]["delivered_at"] <= decision["at"]
            and decision["local_tray"]["tray_id"] == "E" and decision["local_tray"]["node"] == 5
            and decision["local_tray"]["mode"] == "empty" and decision["local_tray"]["edge_to"] < 0)
    executed = (supply_ok and recovery_ok and len(returns) == 2 and all(ack_ok(r, "received") for r in returns)
                and transfer_ids == set(line) | {r["request"]["request_id"] for r in returns})
    actual_returns = [r for r in receipts if r["event"] == "EMPTY_RECEIVED" and r["tray_id"] == "L" and r["node"] == 7]
    loads = [r for r in receipts if r["event"] == "LOAD_START" and r["business_bag_id"] in {"reuse1", "reuse2"}]
    same_tray = (len(actual_returns) == 2 and len(loads) == 2 and all(r["tray_id"] == "L" for r in loads)
        and [r["business_bag_id"] for r in loads] == ["reuse1", "reuse2"]
        and all(a["time"] <= b["time"] for a, b in zip(actual_returns, loads)))
    routes = [r for r in client.rows.values() if r["kind"] == "route"]
    route_expected = 1 + sum(c["request_id"] is not None for c in continuation["route_choices"])
    accepted = len(routes) == route_expected and all(ack_ok(r, "updated") for r in routes)
    initial = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == "loaded" and r["from"] == 0]
    route_match = len(initial) == 1 and initial[0]["to"] == specification["initial_next"]
    actual_choices = []
    for choice in continuation["route_choices"]:
        edges = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == choice["job"] and r["from"] == 7]
        if choice["next"] is None:
            route_match = route_match and specification["later_mode"] == "native_keep" and len(edges) == 1 and edges[0]["to"] in (3, 8)
        else:
            route_match = route_match and len(edges) == 1 and edges[0]["to"] == choice["next"]
            if choice["request_id"] is None:
                route_match = route_match and choice["known_delivered_preference"] == choice["next"]
        actual_choices.append({"job": choice["job"], "selected_next": choice["next"],
                               "actual_next": edges[0]["to"] if len(edges) == 1 else None})
    replay = copy.deepcopy(data)
    replay["transfers"] = [{**c["request"], "issued_at": c["at"]} for c in client.calls if c["kind"] == "transfer" and not c["retry"]]
    try:
        audit = native_host.audit_result(replay, result)
    except (AssertionError, ValueError, KeyError) as exc:
        audit = {"status": "failed", "reason": str(exc)}
    stock = len(result["trays"]) == 3 and {t["tray_id"] for t in result["trays"]} == {"L", "E", "P"}
    park = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == "blocker"]
    blocker_path = len(park) == 1 and park[0]["from"] == 1 and park[0]["to"] == 9
    choices_complete = [c["job"] for c in continuation["route_choices"]] == ["reuse1", "reuse2"]
    valid = (business and executed and accepted and route_match and same_tray and stock and choices_complete
             and blocker_path and expected == model.JOBS and audit.get("status") == "passed" and continuation["status"] == "finished")
    return {"status": "assessed" if valid else "unknown_incomplete_or_unexecuted", "completion": jobs,
        "completion_sum": sum(jobs.values()) if business else None, "business_complete": business,
        "common_horizon_complete": complete, "required_transfer_lineages_received": executed,
        "all_routes_updated": accepted, "chosen_routes_match_executed_edges": route_match,
        "blocker_actual_path1to9": blocker_path, "same_L_two_returns_and_two_reloads": same_tray, "stock_preserved": stock, "audit": audit,
        "actual_later_choices": actual_choices, "supply_attempt_count": len(line),
        "recovered_rejection_count": len(line) - 1, "recovery_decisions_valid": recovery_ok,
        "transfer_acks": [r.get("ack", {}) for r in supply + returns], "route_acks": [r.get("ack", {}) for r in routes]}



def assess(rows, phase):
    declared = protocol(phase)["rows"]
    if (set(rows) != set(declared) or any(any(row.get(field) != declared[key][field]
            for field in ("case", "method", "fault")) for key, row in rows.items())):
        return {"status": "unknown_incomplete_or_misbound_denominator", "expected_rows": len(declared), "observed_rows": len(rows)}
    if phase == "delivery_gate":
        normal = [r for r in rows.values() if not r.get("fault")]
        negative = [r for r in rows.values() if r.get("fault")]
        return {"status": "passed" if len(normal) == 6 and all(r.get("summary", {}).get("both_inputs_verified") is True for r in normal)
            and len(negative) == 3 and all(r.get("summary", {}).get("both_inputs_verified") is False for r in negative)
            and all(r.get("raw_validation", {}).get("status") == "passed"
                and r["raw_validation"].get("fault") == r["fault"]
                and r["raw_validation"].get("recomputed_summary") == r.get("summary") for r in rows.values()) else "unknown_or_failed_delivery_gate",
            "normal_count": len(normal), "negative_count": len(negative), "business_metrics": None}
    result = {}
    for case in domain.cases():
        group = {m: rows[case["case_id"] + "/" + m] for m in METHODS}
        def valid(row):
            value = row.get("summary", {}); times = value.get("completion", {})
            return (row.get("status") == "assessed" and value.get("business_complete") is True
                and value.get("common_horizon_complete") is True and value.get("audit", {}).get("status") == "passed"
                and set(times) == model.JOBS and all(type(t) in (int, float) and math.isfinite(t) and 0 <= t <= v1.HORIZON for t in times.values())
                and value.get("completion_sum") == sum(times.values()))
        base = group["frozen_later"]; fixed = [group["fixed_window_" + str(i)] for i in range(4)]
        fixed_known = valid(base) and all(valid(r) for r in fixed)
        candidates = [r for r in fixed if fixed_known and all(r["summary"]["completion"][j] <= base["summary"]["completion"][j] for j in model.JOBS)]
        strongest = min(candidates, key=lambda r: r["summary"]["completion_sum"], default=None)
        comparisons = {}
        for method, row in group.items():
            known = valid(base) and valid(row); a = row.get("summary", {}).get("completion", {})
            comparisons[method] = {"status": "assessed" if known else "unknown", "completion": a,
                "strict_protected_vs_incumbent": all(a[j] <= base["summary"]["completion"][j] for j in model.JOBS) if known else None,
                "gain_vs_incumbent": base["summary"]["completion_sum"] - row["summary"]["completion_sum"] if known else None,
                "strict_protected_vs_complete_finite_fixed_family": all(a[j] <= strongest["summary"]["completion"][j] for j in model.JOBS) if known and strongest else None,
                "all_later_inputs_verified": row.get("summary", {}).get("rolling_model_inputs_verified"),
                "fallback_count": row.get("summary", {}).get("rolling_fallback_count")}
        result[case["case_id"]] = {"all_offered_count": 5, "complete_fixed_family": fixed_known, "methods": comparisons}
    return result


def require_delivery_gate(path, binary_sha, plan):
    if path is None: raise ValueError("preexisting:business_requires_completed_delivery_gate")
    path = Path(path).resolve()
    require = delivery_evidence.require
    def read(relative): return json.loads((path/relative).read_text(encoding="utf-8"))
    receipt, previous, rows = read("receipt.json"), read("preregistered_protocol.json"), read("branch_ledger.json")
    require(previous.get("phase") == "delivery_gate" and receipt.get("status") == "executed"
            and receipt.get("source_changed") == [] and receipt.get("source_closure_changed") == []
            and receipt.get("binary_sha256") == binary_sha
            and previous.get("source_sha256") == plan["source_sha256"]
            and previous.get("configuration_sha256") == plan["configuration_sha256"], "preexisting:delivery_gate_failed_or_identity_mismatch")
    declared = protocol("delivery_gate")
    require(previous["rows"] == declared["rows"] and previous["row_configuration_sha256"] == declared["row_configuration_sha256"]
        and set(rows) == set(declared["rows"]) and receipt["branch_count"] == len(rows), "preexisting:delivery_denominator_changed")
    require(set(previous["source_archive"]) == set(previous["source_sha256"]), "preexisting:source_archive_coverage")
    for source, digest in previous["source_sha256"].items():
        archived = (path/previous["source_archive"][source]).resolve()
        require(archived.is_relative_to(path/"source") and sha(archived) == digest, "preexisting:archived_source_changed")
    require(set(previous["input_file_sha256"]) == set(rows) and set(receipt["raw_artifacts"]) == set(rows), "preexisting:missing_artifact_denominator")
    revalidated = copy.deepcopy(rows)
    for key, specification in declared["rows"].items():
        require(all(rows[key].get(field) == specification[field] for field in ("case", "method", "fault")), "preexisting:misbound_delivery_row")
        raw_path, input_path = path/(key+".json.gz"), path/"inputs"/(key+".json")
        artifact = {"path": key+".json.gz", "sha256": sha(raw_path), "input_path": "inputs/"+key+".json", "input_sha256": sha(input_path)}
        require(artifact == rows[key]["raw_artifact"] == receipt["raw_artifacts"][key]
            and artifact["input_sha256"] == previous["input_file_sha256"][key], "preexisting:raw_or_input_hash_changed")
        data = json.loads(input_path.read_text(encoding="utf-8"))
        require(config_sha(data) == previous["row_configuration_sha256"][key], "preexisting:input_contract_changed")
        with gzip.open(raw_path, "rt", encoding="utf-8") as stream: raw = json.load(stream)
        result = delivery_evidence.verify_branch(raw, specification, data)
        require(result["status"] == "passed", "preexisting:raw_delivery_validation:" + str(result.get("reason")))
        require(result == rows[key]["raw_validation"] and result["recomputed_summary"] == rows[key]["summary"], "preexisting:lying_delivery_ledger")
        require(rows[key]["status"] == "readiness_observed", "preexisting:unexecuted_delivery_row")
        revalidated[key]["raw_validation"] = result
    comparison = assess(revalidated, "delivery_gate")
    require(comparison["status"] == "passed" and comparison == receipt["comparisons"]
        and receipt["branch_status_counts"] == {"readiness_observed": 9}, "preexisting:delivery_assessment_mismatch")
    return {"path": str(Path(path).resolve()), "receipt_sha256": sha(Path(path)/"receipt.json"),
        "ledger_sha256": sha(Path(path)/"branch_ledger.json"), "plan_sha256": sha(Path(path)/"preregistered_protocol.json"),
        "raw_branches_independently_revalidated": len(rows), "status": "passed"}


def prepare(output, phase):
    output.mkdir(parents=True, exist_ok=False); plan = protocol(phase)
    sources = imported_sources()
    plan["source_sha256"] = {str(p): sha(p) for p in sources}
    plan["source_scope"] = "actual loaded project Python module closure; checked before and after run, including service-aware potential preprocessing"
    plan["python_environment"] = {"executable": sys.executable, "version": sys.version}
    archive = output/"source"; archive.mkdir()
    root = Path(__file__).resolve().parents[3]
    plan["source_archive"] = {}
    for p in sources:
        target = archive/p.relative_to(root); target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes()); plan["source_archive"][str(p)] = str(target.relative_to(output))
    plan["input_file_sha256"] = {}
    for key, row in plan["rows"].items():
        target = output/"inputs"/(key+".json"); target.parent.mkdir(parents=True, exist_ok=True)
        write(target, native_scene(row["case"], row["fault"]))
        plan["input_file_sha256"][key] = sha(target)
    write(output/"preregistered_protocol.json", plan); write(output/"branch_ledger.json", plan["rows"])
    return plan


def worker(args):
    plan = json.loads((args.output/"preregistered_protocol.json").read_text())
    if (set(map(str, imported_sources())) != set(plan["source_sha256"])
            or any(sha(p) != h for p, h in plan["source_sha256"].items()) or sha(args.binary) != args.expected_binary_sha256):
        raise ValueError("rolling_joint:frozen_identity_changed")
    contract_reference = {"path": str(args.native_contract.resolve()), "sha256": args.expected_native_contract_sha256}
    verified = native_acceptance.verify_contract(contract_reference, require_runtime=True)
    if verified["contract"]["binary_sha256"] != args.expected_binary_sha256:
        raise ValueError("preexisting_v3:accepted_binary_mismatch")
    semantic = verify_semantic_gate({"path": str(args.semantic_gate.resolve()),
        "sha256": args.expected_semantic_gate_sha256}, verified["contract"])
    if plan["phase"] == "business":
        require_delivery_gate(args.delivery_gate, args.expected_binary_sha256, plan)
    native = load_native(args.binary); rows = copy.deepcopy(plan["rows"]); start = time.perf_counter()
    for key, row in rows.items():
        row["status"] = "unknown_in_progress"; write(args.output/"branch_ledger.json", rows)
        try:
            input_path = args.output/"inputs"/(key+".json")
            if (sha(input_path) != plan["input_file_sha256"][key]
                    or config_sha(native_scene(row["case"], row["fault"])) != plan["row_configuration_sha256"][key]):
                raise ValueError("preexisting:frozen_input_changed")
            raw = run_branch(native, row, contract_reference, semantic); path = args.output/(key+".json.gz"); path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(path, "wt", encoding="utf-8", compresslevel=1) as stream: json.dump(raw, stream, allow_nan=False)
            row.update(status=raw["summary"]["status"], summary=raw["summary"], raw_artifact={"path": key+".json.gz",
                "sha256": sha(path), "input_path": "inputs/"+key+".json", "input_sha256": sha(input_path)})
            if plan["phase"] == "delivery_gate":
                row["raw_validation"] = delivery_evidence.verify_branch(raw, row, json.loads(input_path.read_text(encoding="utf-8")))
                if row["raw_validation"]["status"] != "passed": row["status"] = "unknown_raw_validation_failed"
        except Exception: row.update(status="unknown_failed", exception=traceback.format_exc())
        write(args.output/"branch_ledger.json", rows)
    changed = [p for p, h in plan["source_sha256"].items() if sha(p) != h]
    closure_changed = sorted(set(map(str, imported_sources())) ^ set(plan["source_sha256"]))
    receipt = {"schema": "g31.lt2.native_preexisting_v3_receipt.v1", "status": ("executed" if all(r["status"] in ("assessed", "readiness_observed") for r in rows.values()) else "completed_with_unknowns") if not changed else "invalidated_source_drift",
        "source_changed": changed, "source_closure_changed": closure_changed, "binary_sha256": sha(args.binary), "branch_count": len(rows),
        "branch_status_counts": {s: sum(r["status"] == s for r in rows.values()) for s in sorted({r["status"] for r in rows.values()})},
        "raw_artifacts": {key: row["raw_artifact"] for key, row in rows.items() if "raw_artifact" in row},
        "comparisons": assess(rows, plan["phase"]), "wall_seconds": time.perf_counter()-start, "native_forks_used": 0,
        "native_results_used_for_policy": False, "model_protection_certified": False,
        "atomic_agreement_certified": False, "complete_request_100ms_certified": False,
        "native027_contract_reference": contract_reference, "native027_semantic_gate": semantic,
        "current_state_certified": False, "conditional_stability_only": True}
    if closure_changed: receipt["status"] = "invalidated_import_closure_drift"
    write(args.output/"receipt.json", receipt); print(json.dumps(receipt, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path); parser.add_argument("--expected-binary-sha256")
    parser.add_argument("--execute", action="store_true"); parser.add_argument("--worker", action="store_true")
    parser.add_argument("--prepared", action="store_true"); parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--native-contract", type=Path); parser.add_argument("--expected-native-contract-sha256")
    parser.add_argument("--semantic-gate", type=Path); parser.add_argument("--expected-semantic-gate-sha256")
    parser.add_argument("--timeout-seconds", type=float, default=180.)
    parser.add_argument("--phase", choices=("delivery_gate", "business"), default="delivery_gate")
    parser.add_argument("--delivery-gate", type=Path)
    args = parser.parse_args()
    if args.worker: worker(args); return
    if args.prepared:
        path = args.output/"preregistered_protocol.json"
        if sha(path) != args.expected_plan_sha256: parser.error("prepared plan hash required and must match")
        plan = json.loads(path.read_bytes())
        if plan["phase"] != args.phase: parser.error("prepared phase mismatch")
    else: plan = prepare(args.output, args.phase)
    if not args.execute: print(json.dumps({"status": "prepared_no_native_calls", "branches": len(plan["rows"])})); return
    if (not args.binary or not args.expected_binary_sha256 or not args.native_contract
            or not args.expected_native_contract_sha256 or not args.semantic_gate or not args.expected_semantic_gate_sha256):
        parser.error("exact binary and both actual runtime gate identities are required")
    if not math.isfinite(args.timeout_seconds) or not 0 < args.timeout_seconds <= 180.:
        parser.error("bounded parent timeout must be positive and at most180s")
    verified = native_acceptance.verify_contract({"path": str(args.native_contract.resolve()),
        "sha256": args.expected_native_contract_sha256}, require_runtime=True)
    if verified["contract"]["binary_sha256"] != args.expected_binary_sha256 or sha(args.binary) != args.expected_binary_sha256:
        parser.error("loaded campaign binary must match accepted027 artifact")
    semantic = verify_semantic_gate({"path": str(args.semantic_gate.resolve()),
        "sha256": args.expected_semantic_gate_sha256}, verified["contract"])
    write(args.output/"runtime_admission.json", {"contract": verified["reference"], "semantic_gate": semantic})
    if args.phase == "business":
        write(args.output/"delivery_gate_binding.json", require_delivery_gate(args.delivery_gate, args.expected_binary_sha256, plan))
    command = [sys.executable, "-m", __spec__.name, "--worker", "--output", str(args.output), "--binary", str(args.binary),
        "--expected-binary-sha256", args.expected_binary_sha256, "--native-contract", str(args.native_contract),
        "--expected-native-contract-sha256", args.expected_native_contract_sha256, "--semantic-gate", str(args.semantic_gate),
        "--expected-semantic-gate-sha256", args.expected_semantic_gate_sha256]
    if args.delivery_gate is not None: command.extend(["--delivery-gate", str(args.delivery_gate)])
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout_seconds)
        (args.output/"worker.stdout.log").write_text(done.stdout, encoding="utf-8")
        (args.output/"worker.stderr.log").write_text(done.stderr, encoding="utf-8")
        if done.returncode: write(args.output/"worker_failure.json", {"status": "unknown_failed", "exitcode": done.returncode})
    except subprocess.TimeoutExpired:
        write(args.output/"worker_failure.json", {"status": "unknown_timeout", "seconds": args.timeout_seconds})


if __name__ == "__main__": main()
