"""Offline stopwatch proxy: observations/results are forwarded unchanged.

Only the declared protocol endpoints are allowed. The caller must take records
outside its measured controller service window; no diagnostic is a policy input.
"""
from __future__ import annotations

import time

from .native_request_timing import METHODS


API_METHODS = {
    "submit_protocol_transfer": "submit_transfer", "submit_protocol_command": "submit_command",
    "protocol_request": "query_transfer", "protocol_command": "query_command",
    "observe_protocol": "observe_protocol", "observe_protocol_control": "observe_control",
    "observe_protocol_control_policy": "observe_policy",
    "observe_protocol_control_policy_recent": "observe_policy_recent",
    "protocol_demand_signature": "demand_signature", "protocol_planning_snapshots": "planning_snapshots",
    "advance_until_owner_notification": "advance_notification", "advance_to": "advance_to", "result_at": "result_at",
}


class CaptureNamespaces:
    """Campaign-local namespaces; retained references prevent object-ID reuse.

    One registry belongs to one evidence campaign. Its lifetime/retained native
    objects are diagnostic overhead; never put it in policy/checkpoint state.
    """
    def __init__(self):
        self._sessions = []

    def identity_for(self, session):
        for identity, existing in enumerate(self._sessions, 1):
            if existing is session:
                return identity
        self._sessions.append(session)
        return len(self._sessions)


class NativeTimingCapture:
    """One trace epoch, one serial session, complete outer call envelopes."""
    def __init__(self, session, *, session_identity, capacity=1_000_000, clock=time.perf_counter_ns):
        if type(session_identity) is not int or not 0 < session_identity < 2**64:
            raise ValueError("native_timing:invalid_session_identity")
        self._session, self._clock = session, clock
        self.session_identity = session_identity
        self.envelopes, self.batches = [], []
        self.errors = []
        self._session.offline_request_timing_start(capacity, session_identity)
        # An empty take establishes the actual native epoch without guessing it.
        initial = self._session.offline_request_timing_take()
        if initial["rows"] or initial["errors"] or initial["completed_outer_calls"] != 0:
            raise ValueError("native_timing:nonempty_new_epoch")
        if initial.get("session_identity") != session_identity:
            raise ValueError("native_timing:session_identity_mismatch")
        self.trace_epoch = initial["trace_epoch"]
        self.batches.append(initial)

    @property
    def physical_time(self):
        return self._session.physical_time

    def __getattr__(self, name):
        if name not in API_METHODS:
            raise ValueError("native_timing:unclassified_endpoint:" + name)
        method = getattr(self._session, name)
        return lambda *a, **kw: self._invoke(name, method, *a, **kw)

    def _invoke(self, name, method, *args, **kwargs):
        envelope = {"session_identity": self.session_identity, "trace_epoch": self.trace_epoch,
            "call_ordinal": len(self.envelopes)+1, "method": METHODS.index(API_METHODS[name])}
        if name.startswith("submit_protocol_"):
            payload = args[0] if args else kwargs.get("request", {})
            envelope["protocol_request_id"] = payload.get("request_id")
        elif name in {"protocol_request", "protocol_command"}:
            envelope["protocol_request_id"] = args[1] if len(args) > 1 else kwargs.get("request_id")
        envelope["start_ns"] = self._clock()
        try:
            return method(*args, **kwargs)
        except BaseException as exc:
            self.errors.append(type(exc).__name__ + ":" + str(exc))
            raise
        finally:
            envelope["end_ns"] = self._clock()
            self.envelopes.append(envelope)

    def take_completed(self):
        """Call only after the controller's returned output has been measured."""
        batch = self._session.offline_request_timing_take()
        self.batches.append(batch)
        return batch


class PolicyNativeTimingCapture(NativeTimingCapture):
    # Explicit type capability preserves ProtocolClient's endpoint selection.
    def observe_protocol_control_policy(self, owner):
        return self._invoke("observe_protocol_control_policy", self._session.observe_protocol_control_policy, owner)


class RecentNativeTimingCapture(PolicyNativeTimingCapture):
    def observe_protocol_control_policy_recent(self, owner, forecast_validity):
        return self._invoke("observe_protocol_control_policy_recent",
            self._session.observe_protocol_control_policy_recent, owner, forecast_validity)


def capture_session(session, **kwargs):
    if getattr(type(session), "observe_protocol_control_policy_recent", None) is not None:
        cls = RecentNativeTimingCapture
    elif getattr(type(session), "observe_protocol_control_policy", None) is not None:
        cls = PolicyNativeTimingCapture
    else:
        cls = NativeTimingCapture
    return cls(session, **kwargs)
