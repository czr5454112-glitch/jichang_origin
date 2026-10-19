"""Source-derived beacon/calendar and recovery semantics for the finite domain.

This is a new conditional model revision; historical models remain unchanged.
No saved native outcome, clock offset or branch key enters prediction. The
native recovery comparison below is an event rule, never a protection tolerance.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import FunctionType

from . import public_live_obligation_projection as previous

VERSION = 'public_live_obligation_event_projection_v2'
EXPECTED_PREVIOUS = 'acaa7948bcc8742cfc338ca76f187431078f631fef1c4c8fe82e44dc81e0b544'
NATIVE_RECOVERY_EPSILON = 1.0e-9


def same_recovery_timestamp(left, right):
    """Accepted027 recovery uses same_timestamp, unlike exact event ordering."""
    return left == right or abs(left - right) <= NATIVE_RECOVERY_EPSILON


class Projection(previous.Projection):
    def begin_leg(self, key, goal, *, ready=None):
        super().begin_leg(key, goal, ready=ready)
        # circulation_create_leg publishes circulation_leg_initial_snapshot
        # for EVERY downstream node, even when that node's queue is unchanged.
        for downstream in self.outgoing[self.trays[key]['node']]:
            self.schedule(self.time, 'beacon', downstream)

    def beacon(self, node):
        # process_congestion_beacon_update first purges the native service
        # calendar, then reads reserved_until(now). The numerical purge rule
        # belongs to the accepted native contract; it is not applied to jobs.
        self.calendars[node] = [interval for interval in self.calendars[node]
                                if interval[1] > self.time + NATIVE_RECOVERY_EPSILON]
        reserved_until = max([self.time] + [end for _, end in self.calendars[node]])
        snapshot = (
            sum(t['node'] == node and t['edge_to'] < 0 and t['queued'] for t in self.trays.values()),
            sum(t['scheduled_incoming_node'] == node for t in self.trays.values()),
            reserved_until,
        )
        prior = self.beacon_state.get(node)
        self.beacon_state[node] = snapshot
        changed = (prior is None or prior[:2] != snapshot[:2] or
                   (max(prior[2], snapshot[2]) > self.time and prior[2] != snapshot[2]))
        self.phase_trace.append({'at': self.time, 'phase': 'beacon_snapshot', 'node': node,
                                 'previous': prior, 'current': snapshot, 'ranking_notification': changed})
        if changed:
            for key, nodes in list(self.ranking_subscriptions.items()):
                if node in nodes:
                    self.wake_one(key, 'candidate_score_state_changed')

    def wake_one(self, key, reason):
        if key not in self.waiting:
            return
        self.wait_targets.pop(key, None)
        self.ranking_subscriptions.pop(key, None)
        last = self.last_arbitration.get(self.trays[key]['node'])
        delay = self.minimum if last is not None and same_recovery_timestamp(last, self.time) else 0.
        # Both minimum_service and dispatch_headway are .001 in the accepted
        # closed native semantics. Keep exact try_depart/event ordering intact.
        self.phase_trace.append({'at': self.time, 'phase': 'resource_wake', 'tray': key,
                                 'reason': reason, 'next_arbitration': self.time + delay})
        self.schedule(self.time + delay, 'ready', key)


def check_sources():
    previous.check_sources()
    if hashlib.sha256(Path(previous.__file__).read_bytes()).hexdigest() != EXPECTED_PREVIOUS:
        raise ValueError('live_event_v2:unreviewed_previous_projection')


# Reuse the exact closed input/action/domain/expiry validation with a private
# function namespace. Neither old module globals nor old class methods mutate.
_namespace = dict(previous.predict.__globals__)
_namespace.update(Projection=Projection, check_sources=check_sources)
_predict = FunctionType(previous.predict.__code__, _namespace, 'predict_event_v2',
                        previous.predict.__defaults__, previous.predict.__closure__)


def predict(bundle, action):
    result = _predict(bundle, action)
    result['model_version'] = VERSION
    result['event_revision'] = {
        'leg_start_downstream_beacons': True,
        'purged_service_calendar_ranking_notifications': True,
        'recovery_same_timestamp_rule': True,
        'exact_event_order_and_job_protection_unchanged': True,
        'saved_outcomes_used_as_predictor_input': False,
    }
    return result
