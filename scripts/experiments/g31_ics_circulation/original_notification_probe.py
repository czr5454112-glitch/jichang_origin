"""Separate original-map finite notification-operation engine (not production).

The caller constructs the full frozen native input and records that mandatory
setup separately. This engine has no result/fork/checkpoint capability. Every
service call is copied inside measured root lifetimes; optional raw chunk writes
remain charged while any root is open. No actual runtime acceptance is implied
by importing or exercising this module with test doubles.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import time

from .original_notification_contract import NotificationLedger, TERMINAL, contract, require
from .protocol_control import ProtocolClient, _publish_services
from .event_protocol_control import _publish_owner_demand
from .analytic_control import transfer_candidates


ENDPOINTS = frozenset(("advance_until_owner_notification", "advance_to", "observe_protocol",
    "protocol_demand_signature", "submit_protocol_transfer", "submit_protocol_command",
    "protocol_request", "protocol_command"))


class ServiceTape:
    def __init__(self, session, *, call_budget, clock=time.perf_counter_ns):
        self.session, self.call_budget, self.clock = session, call_budget, clock
        self.rows, self.total_calls = [], 0

    @property
    def physical_time(self): return self.session.physical_time

    def __getattr__(self, name):
        require(name in ENDPOINTS, "unclassified_endpoint:"+name)
        def invoke(*args, **kwargs):
            require(self.total_calls < self.call_budget, "native_call_budget_exhausted")
            started = self.clock(); self.total_calls += 1
            row = {"ordinal": self.total_calls, "endpoint": name, "args": deepcopy(list(args)),
                "kwargs": deepcopy(kwargs), "start_ns": started, "physical_before": self.physical_time}
            try:
                result = getattr(self.session, name)(*args, **kwargs)
                row["result"] = deepcopy(result)
                return result
            except BaseException as error:
                row["error"] = type(error).__name__+":"+str(error); raise
            finally:
                row["physical_after"] = self.physical_time; row["end_ns"] = self.clock(); self.rows.append(row)
        return invoke


class CohortClient(ProtocolClient):
    def __init__(self, session, ledger, *, clock=time.perf_counter_ns):
        super().__init__(session, retry_period=contract()["retry_period_seconds"])
        self.ledger, self.clock = ledger, clock
        self.current_root = None

    def submit(self, owner, kind, payload, *, request_id=None):
        root = self.current_root
        require(root is not None and self.ledger.roots[root]["owner"] == owner, "submission_without_admission")
        request_id = request_id or self.next_id(owner, kind)
        at, started = self.session.physical_time, self.clock()
        try: return super().submit(owner, kind, payload, request_id=request_id)
        finally:
            row = self.state["outbox"].get(request_id)
            if row is not None:
                self.ledger.submit(root, request_id, kind, row["payload"], at=at, wall_ns=started)

    def _send(self, row, *, retry):
        at, started = self.session.physical_time, self.clock()
        try: return super()._send(row, retry=retry)
        finally:
            if retry:
                identity = row["payload"]["request_id"]
                operation = self.ledger.operations[identity]
                self.ledger.submit(operation["root"], identity, row["kind"], row["payload"],
                    retry=True, at=at, wall_ns=started)

    def refresh(self, **kwargs):
        returned = super().refresh(**kwargs)
        for item in returned:
            identity, ack = item["request_id"], item["view"].get("last_delivered_ack")
            if not ack or ack.get("status") not in TERMINAL: continue
            require(identity in self.ledger.operations, "query_without_admitted_operation")
            if self.ledger.operations[identity]["ack"] is not None: continue
            matches = [r for r in self.session.rows if r["endpoint"] in {"protocol_request", "protocol_command"}
                and len(r["args"]) == 2 and r["args"][1] == identity]
            require(bool(matches), "ack_query_not_on_actual_tape")
            self.ledger.handle_ack(identity, {**deepcopy(ack), "request_id": identity}, at=self.session.physical_time,
                wall_ns=self.clock(), query_ordinal=matches[-1]["ordinal"])
        return returned


def propose(client, owner, owners, state, observation):
    """One finite proposal using unchanged public production candidate functions."""
    cfg = contract()
    publications = _publish_owner_demand(client, owner, owners, state,
        cfg["command_delay_seconds"], cfg["publication_delay_seconds"])
    services = _publish_services(client, owner, state, command_delay=cfg["command_delay_seconds"],
        publication_delay=cfg["publication_delay_seconds"], routes=True, forecasts=True,
        lease_seconds=cfg["lease_seconds"], observation=observation)
    observed = client.view(owner, compact=False)
    decision = transfer_candidates(observed, predictive=True, message_delay=cfg["command_delay_seconds"],
        respect_service_forecasts=True, request_prefix="original-notification:"+client.current_root)
    initial, attempts = decision, []
    for _ in range(len(initial["intents"])):
        if not decision["intents"]: break
        identity, reply = client.submit(owner, "transfer", decision["intents"][0])
        attempts.append({"request_id": identity, "reply": reply})
        if reply.get("status") != "pending": break
        observed = client.view(owner, compact=False)
        decision = transfer_candidates(observed, predictive=True, message_delay=cfg["command_delay_seconds"],
            respect_service_forecasts=True, request_prefix="original-notification-residual:"+client.current_root)
    return {"publications": publications, "services": services, "decision": initial, "attempts": attempts}


def run_cohort(session, owners, *, clock=time.perf_counter_ns, proposal=propose, chunk_sink=None):
    """Bounded online engine; tests may inject only the policy and clock.

    The actual campaign must use the defaults and source-pin this module. All
    failures return a ledger prefix, never remove offered roots, or synthesize
    a terminal ACK. A new bundle cannot settle an older outstanding operation.
    """
    cfg = contract(); engine_start = clock()
    tape = ServiceTape(session, call_budget=cfg["native_call_budget"], clock=clock)
    ledger = NotificationLedger(owners); client = CohortClient(tape, ledger, clock=clock)
    state = {"published": {}, "routes": {}, "forecasts": {}}
    decisions, chunks, failures = {}, [], []
    admitted_boundaries, iteration, tail_deadline = 0, 0, None
    status = "unknown_in_progress"

    def close_ready():
        for root, row in ledger.roots.items():
            if row["output"] is not None or row["observation"] is None or row["scope_errors"]: continue
            if not all(ledger.operations[i]["ack"] is not None for i in row["operations"]): continue
            # The ledger independently derives disposition from delivered ACKs.
            from .original_notification_contract import SUCCESS
            disposition = ("no_action" if not row["operations"] else "completed" if all(
                ledger.operations[i]["ack"]["body"]["status"] in SUCCESS[ledger.operations[i]["kind"]]
                for i in row["operations"]) else "terminal_failure")
            drain = tape.advance_to(tape.physical_time, max_events=cfg["event_budget_per_call"])
            call = tape.rows[-1]
            encoded = json.dumps({"root_id": root, "disposition": disposition, "operation_ids": row["operations"]},
                                 allow_nan=False, separators=(",", ":"))
            ledger.finish(root, drain=drain, drain_start_ns=call["start_ns"], drain_end_ns=call["end_ns"],
                output_end_ns=clock(), encoded_output=encoded, drain_ordinal=call["ordinal"])
            # Include the live closure validator/ledger write as well as the
            # encoded output. The earlier argument only bounds validation;
            # this actual post-return clock is the saved service endpoint.
            row["output"]["wall_ns"] = clock()

    try:
        while True:
            admitting = admitted_boundaries < cfg["admitted_notification_boundaries"]
            pending = [r for r in ledger.roots.values() if r["output"] is None]
            if not admitting and not pending:
                status = "finite_cohort_closed"; break
            if not admitting and tape.physical_time >= tail_deadline:
                status = "completion_tail_exhausted"; break
            deadline = cfg["public_horizon"] if admitting else tail_deadline
            retries = [r["next_retry"] for r in client.state["outbox"].values() if not r["terminal"]]
            if retries: deadline = min(deadline, max(tape.physical_time, min(retries)))
            identity = "notification:"+str(iteration); iteration += 1
            ledger.begin(identity, at=tape.physical_time, wall_ns=clock())
            response = tape.advance_until_owner_notification(owners, ledger.cursors, deadline,
                max_events=cfg["event_budget_per_call"])
            roots = ledger.notified(identity, response, wall_ns=clock(), call_ordinal=tape.total_calls, admit=admitting)
            if admitting and response["notifications"]:
                admitted_boundaries += 1
                if admitted_boundaries == cfg["admitted_notification_boundaries"]:
                    tail_deadline = min(cfg["public_horizon"], tape.physical_time+cfg["completion_tail_seconds"])
            # Real returned queries and immutable retries belong to their old
            # operation roots even during a new independent notification.
            client.refresh()
            close_ready()
            for root in roots:
                owner = ledger.roots[root]["owner"]
                view = client.view(owner, compact=False); call = tape.rows[-1]
                ledger.observe(root, view, start_ns=call["start_ns"], end_ns=clock(), call_ordinal=call["ordinal"])
                client.current_root = root
                try: decisions[root] = proposal(client, owner, owners, state, view)
                finally: client.current_root = None
            close_ready()
            # Lossless bounded chunks: subsequent ACK lookup only needs the
            # current batch; old returned views remain in immutable sink files.
            chunk = {"index": len(chunks), "batch_id": identity, "service_tape": tape.rows}
            if chunk_sink is None: chunks.append(deepcopy(chunk))
            else: chunks.append(chunk_sink(chunk))
            tape.rows = []
            if response["status"] == "horizon_reached" and tape.physical_time >= cfg["public_horizon"]:
                status = "public_horizon_reached"; break
    except Exception as error:
        failures.append(type(error).__name__+":"+str(error)); status = "unknown_failed_or_budget_prefix"
    ended = clock()
    return {"schema": "g31.original_notification_operation_run.v1", "contract": cfg, "status": status,
        "engine_start_ns": engine_start, "ended_ns": ended, "physical_time": tape.physical_time,
        "admitted_notification_boundaries": admitted_boundaries, "native_call_count": tape.total_calls,
        "ledger": {"batches": ledger.batches, "roots": ledger.roots, "operations": ledger.operations},
        "decisions": decisions, "outbox": client.state["outbox"], "client_calls": client.calls,
        "chunks": chunks, "unflushed_service_tape": tape.rows, "failures": failures,
        "accounting_without_host_setup": ledger.accounting(mandatory_setup_ns=0, known_end_ns=ended),
        "original_business_request_100ms_certified": False, "native_runtime_accepted": False}
