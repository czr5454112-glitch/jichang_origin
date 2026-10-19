"""Scoped reuse of unchanged delivered-protocol projections.

This adapter requires exclusive serial access to the native session through the
adapter. It uses only returned owner notifications, submitted local payloads and
previous public query results. It is not wired into the production controller.

The current native contract changes a query projection only on local submit,
delivered ACK (notification bit16), or local timeout (bit32). The latest mask is
NOT a cumulative cursor: reuse is allowed only while consuming every complete
all-owner notification boundary without a cursor gap. Any uncertainty clears
the cache. Cache values, counters and cursor proof are outside checkpoint state.
"""
from __future__ import annotations

import copy
import math


PROJECTION_CHANGE_MASK = 16 | 32
KNOWN_NOTIFICATION_MASK = 255
READ_ONLY = frozenset({"observe_protocol", "observe_protocol_control", "protocol_demand_signature",
    "protocol_planning_snapshots", "owner_notifications", "offline_state_sha256", "offline_diagnostics"})


class ProtocolQueryCache:
    def __init__(self, session, owners):
        owners = tuple(owners)
        if not owners or any(not isinstance(o, str) or not o for o in owners) or len(set(owners)) != len(owners):
            raise ValueError("protocol_query_cache:invalid_owners")
        self._session, self._owners = session, owners
        self._cached = {}
        self._cursor = None
        self._certified = False
        self._counters = {"native_queries": 0, "reused_queries": 0, "invalidations": 0}

    @property
    def physical_time(self):
        return self._session.physical_time

    def _invalidate(self, owner=None, request_id=None):
        self._counters["invalidations"] += 1
        if owner is None:
            self._cached.clear()
        else:
            for key in tuple(self._cached):
                if key[1] == owner and (request_id is None or key[2] == request_id):
                    del self._cached[key]

    def _uncertain(self):
        self._invalidate()
        self._certified = False
        self._cursor = None

    def _query(self, kind, owner, request_id):
        key = kind, owner, request_id
        if self._certified and key in self._cached:
            self._counters["reused_queries"] += 1
            return copy.deepcopy(self._cached[key])
        result = getattr(self._session, kind)(owner, request_id)
        self._counters["native_queries"] += 1
        if self._certified and owner in self._owners:
            self._cached[key] = copy.deepcopy(result)
        return result

    def protocol_request(self, owner, request_id):
        return self._query("protocol_request", owner, request_id)

    def protocol_command(self, owner, request_id):
        return self._query("protocol_command", owner, request_id)

    def _submit(self, name, request):
        # Even rejected/exceptional calls invalidate: never assume which native
        # admission path ran. The next query must read its actual local result.
        owner, identity = (request.get("owner_id"), request.get("request_id")) if isinstance(request, dict) else (None, None)
        if owner in self._owners and isinstance(identity, str):
            self._invalidate(owner, identity)
        else:
            self._uncertain()
        return getattr(self._session, name)(request)

    def submit_protocol_transfer(self, request):
        return self._submit("submit_protocol_transfer", request)

    def submit_protocol_command(self, request):
        return self._submit("submit_protocol_command", request)

    def advance_until_owner_notification(self, owners, after, horizon, *, max_events=1000000):
        # A missing subscriber can hide ACK changes over multiple timestamps;
        # its latest mask alone can never repair that missing interval.
        subscribed = (len(owners) == len(self._owners) and set(owners) == set(self._owners)
                      and isinstance(after, dict) and set(after) == set(self._owners)
                      and all(type(v) is int and v >= 0 for v in after.values()))
        continuous = subscribed and self._certified and after == self._cursor
        if not continuous:
            self._uncertain()
        try:
            response = self._session.advance_until_owner_notification(owners, after, horizon, max_events=max_events)
        except BaseException:
            self._uncertain()
            raise
        now = self.physical_time
        notices = response.get("notifications")
        valid = (subscribed and response.get("timestamp_complete") is True
                 and response.get("status") in {"notified", "horizon_reached"}
                 and isinstance(notices, dict) and set(notices) <= set(self._owners)
                 and isinstance(now, (int, float)) and math.isfinite(now) and now >= 0)
        if valid:
            valid = all(isinstance(n, dict)
                and type(n.get("sequence")) is int and n["sequence"] > after[o]
                and type(n.get("change_mask")) is int and n["change_mask"] >= 0
                and not n["change_mask"] & ~KNOWN_NOTIFICATION_MASK
                and type(n.get("observed_at")) in (int, float)
                and math.isfinite(n["observed_at"]) and 0 <= n["observed_at"] <= now
                for o, n in notices.items())
        if not valid:
            self._uncertain()
            return response
        # After a gap, all values were discarded before this call. Establish a
        # new empty baseline; no earlier cached result survives the gap.
        for owner, notice in notices.items():
            if notice["change_mask"] & PROJECTION_CHANGE_MASK:
                self._invalidate(owner)
        self._cursor = dict(after)
        self._cursor.update({o: n["sequence"] for o, n in notices.items()})
        self._certified = True
        return response

    def checkpoint(self):
        self._uncertain()
        return self._session.checkpoint()

    def restore(self, state):
        self._uncertain()
        return self._session.restore(state)

    def fork(self):
        self._uncertain()
        return cache_protocol_queries(self._session.fork(), self._owners)

    def __getattr__(self, name):
        endpoint = getattr(self._session, name)
        if not callable(endpoint):
            self._uncertain()
            return endpoint
        if name in READ_ONLY:
            return endpoint
        # Includes advance_to/result_at/step and future unknown methods. Even a
        # read-only diagnostic is conservatively uncached unless listed above.
        def uncertain(*args, **kwargs):
            self._uncertain()
            try:
                return endpoint(*args, **kwargs)
            finally:
                self._uncertain()
        return uncertain


class PolicyProtocolQueryCache(ProtocolQueryCache):
    def observe_protocol_control_policy(self, owner):
        return self._session.observe_protocol_control_policy(owner)


class RecentProtocolQueryCache(PolicyProtocolQueryCache):
    def observe_protocol_control_policy_recent(self, owner, forecast_validity):
        return self._session.observe_protocol_control_policy_recent(owner, forecast_validity)


def cache_protocol_queries(session, owners):
    # Preserve the controller's explicit class-capability contract.
    if getattr(type(session), "observe_protocol_control_policy_recent", None) is not None:
        cls = RecentProtocolQueryCache
    elif getattr(type(session), "observe_protocol_control_policy", None) is not None:
        cls = PolicyProtocolQueryCache
    else:
        cls = ProtocolQueryCache
    return cls(session, owners)
