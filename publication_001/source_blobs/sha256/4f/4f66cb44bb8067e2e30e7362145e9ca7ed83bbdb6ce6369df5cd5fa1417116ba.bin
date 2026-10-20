"""Experimental finite first-hop continuation after real observed physical proof.

No controller installs this class. It inherits all admission/candidate/route
logic, and only omits full observations after that same instance has recorded
an actual hop through the unchanged public-view path. This is not a route
maintenance contract; the immutable ACK, retry, drain and output stay required.
"""
from __future__ import annotations
from copy import deepcopy
import ast
import hashlib
import inspect
import json
import math
import textwrap

from . import probe_original_route_update_internal_deadline as reference

ADMISSION,HORIZON,ROOT_ID,JOB=reference.ADMISSION,reference.HORIZON,reference.ROOT_ID,reference.JOB
require=reference.require
VERSION="finite_first_hop_pending_ack_v1"


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()


class PendingAckRouteUpdate(reference.RouteUpdate):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._observed_hop_proof=None
        self._last_ack_only_at=None
        self.full_view_reads=0
        self.ack_only_steps=0

    def _view(self,initial):
        # Count only successful actual public calls; never fabricate a view.
        view=super()._view(initial)
        self.full_view_reads+=1
        return view

    def _pin_observed_hop(self):
        edge,decision=self.intent.edge,self.intent.decision
        require(edge is not None and decision is not None,"pending_ack_missing_actual_proof")
        require(edge["owner"]==decision["owner"]==self.owner and edge["from"]==112 and
            decision["request"]["business_bag_id"]==decision["local_job"]["business_bag_id"]==JOB,
            "pending_ack_proof_scope")
        require(edge["evidence"] in {"matched_observed_entry_inflight","completed_committed_prefix"} and
            type(edge["observed_at"]) in (int,float) and math.isfinite(edge["observed_at"]) and
            edge["observed_at"]==self.session.physical_time and
            edge["local_tray"]["tray_id"]==decision["local_tray"]["tray_id"] and
            edge["local_tray"]["business_bag_id"]==JOB and
            edge["local_tray"]["generation"]==decision["local_tray"]["generation"],
            "pending_ack_proof_identity")
        self._observed_hop_proof={"request_id":decision["request_id"],"observed_at":edge["observed_at"],
            "decision_sha256":canonical_digest(decision),"edge_sha256":canonical_digest(edge),
            "actual_view_count":self.full_view_reads,"source":"same_instance_unchanged_public_observe_path"}

    def _can_refresh_only(self,initial):
        proof=self._observed_hop_proof
        if initial or proof is None:return False
        require(self.intent.edge is not None and self.intent.decision is not None and
            canonical_digest(self.intent.edge)==proof["edge_sha256"] and
            canonical_digest(self.intent.decision)==proof["decision_sha256"] and
            self.intent.decision["request_id"]==proof["request_id"],"pending_ack_sticky_proof_changed")
        require(proof["observed_at"]<=self.session.physical_time and
            (self._last_ack_only_at is None or self._last_ack_only_at<=self.session.physical_time),
            "pending_ack_clock_regressed")
        # Retain the eligibility class's second-observation guard verbatim by
        # using its full path until that actual wake has already completed.
        return self.eligibility_schedule is not None and self.eligibility_schedule["fired_at"] is not None

    def _step(self,*,initial):
        if self._can_refresh_only(initial):
            self._step_after_observed_hop(initial=False)
            self.ack_only_steps+=1
            return
        prior_edge=self.intent.edge; views_before=self.full_view_reads
        super()._step(initial=initial)
        if not self.closed and prior_edge is None and self.intent.edge is not None:
            require(self.full_view_reads==views_before+1,"pending_ack_proof_without_new_public_view")
            self._pin_observed_hop()

    def _refresh_sticky_ack(self,now):
        self._last_ack_only_at=now
        # Exactly the old terminal short circuit and delivered-ACK rules.
        # last_now/observation_count/reservation describe actual observations,
        # so they deliberately remain unchanged when no observation occurred.
        if self.intent.status in reference.old.TERMINAL:return
        require(now>=self.intent.last_now,"observation_clock_regressed")
        decision=self.intent.decision
        row=self.client.state["outbox"][decision["request_id"]]
        ack=row.get("client_view",{}).get("last_delivered_ack",{})
        if ack:
            require(ack["delivered_at"]<=now,"future_ack")
            self.intent.ack=deepcopy(ack)
        if self.intent.ack and self.intent.ack.get("status") in {"rejected","expired","failed","cancelled"}:
            self.intent.status="delivered_rejection"
        elif self.intent.ack and self.intent.ack.get("status")=="updated" and self.intent.edge:
            self.intent.status="updated_ack_and_actual_edge" if self.intent.edge["to"]==113 else "updated_but_other_edge"

    def _step_after_observed_hop(self,*,initial):
        now = self.session.physical_time
        require(ADMISSION <= now <= HORIZON, "step_outside_window")
        if not initial: self.bridge.refresh()
        self._refresh_sticky_ack(now)
        self.next_probe = now + 60.
        disposition = None
        if self.intent.status == "updated_ack_and_actual_edge": disposition = "completed"
        elif self.intent.status in {"delivered_rejection", "updated_but_other_edge"}: disposition = "terminal_failure"
        if disposition is not None:
            response = {"root": ROOT_ID, "job": JOB, "disposition": disposition, "intent": self.intent.snapshot()}
            returned = self.bridge.finish(ROOT_ID, response, disposition=disposition,
                classification_complete=True, event_budget=100000)
            if returned["status"] == "returned":
                self.returned = json.dumps(returned, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                self.returned_ns = self.clock()
        self.steps.append({"at": now, "initial": initial, "status": self.intent.status,
            "closed": self.closed, "next_probe": self.next_probe})

    def snapshot(self):
        return {**super().snapshot(),"pending_ack_path":{"version":VERSION,
            "full_view_reads":self.full_view_reads,"ack_only_steps":self.ack_only_steps,
            "sticky_observed_hop":deepcopy(self._observed_hop_proof),"last_ack_only_at":self._last_ack_only_at,
            "changed_diagnostics":["intent.observation_count","intent.last_now","intent.reservation",
                "returned response encodes those actual observation diagnostics"],
            "long_term_route_maintenance_certified":False,"complete_100ms_certified":False}}


def prove_unchanged_closure_tail():
    original=ast.parse(textwrap.dedent(inspect.getsource(reference.base.RouteUpdate._step))).body[0]
    candidate=ast.parse(textwrap.dedent(inspect.getsource(PendingAckRouteUpdate._step_after_observed_hop))).body[0]
    def dump(rows):return [ast.dump(r,include_attributes=False) for r in rows]
    require(ast.unparse(original.body[3])=="view = self._view(initial)" and
        ast.unparse(original.body[4])=="self.intent.observe(view, SubmissionBridge(self.bridge))",
        "pending_ack_reference_ast_changed")
    require(dump(original.body[:3])==dump(candidate.body[:3]) and
        ast.unparse(candidate.body[3])=="self._refresh_sticky_ack(now)" and
        dump(original.body[5:])==dump(candidate.body[4:]),"pending_ack_closure_or_refresh_changed")
    return {"status":"exact_refresh_and_terminal_drain_codec_tail_except_observation_block",
        "root_admission_and_initial_candidate_path":"inherited unchanged",
        "retry_period_seconds":60.,"wire_delay_seconds":2.,"no_native_execution":True}
