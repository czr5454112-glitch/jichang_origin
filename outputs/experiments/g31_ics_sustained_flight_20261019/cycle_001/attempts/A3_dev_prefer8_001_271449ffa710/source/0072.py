"""Owner-local native027 collection with sealed unsuccessful read attempts.

The unchanged collector performs its three real owner-scoped reads. A private
namespace changes only the supplied-data lifecycle validator to staged A.
An unsuccessful collection can authorize only a bounded new information request;
it cannot authorize a physical counterfactual action. Saved JSON is never a
capability. No source capture, current view or mutable validation is cached.
"""
from __future__ import annotations

import json
from types import FunctionType
from . import live_obligation_domain_adapter as old
from . import domain_guard_v2 as guard

_ATTEMPT_TOKEN = object()
_namespace = dict(vars(old))
_namespace['validate_collected_endpoints'] = guard.validate_collected_endpoints
_collect = FunctionType(old.collect_native.__code__, _namespace,
                        old.collect_native.__name__, old.collect_native.__defaults__,
                        old.collect_native.__closure__)
_collect.__kwdefaults__ = old.collect_native.__kwdefaults__
bind_native027 = old.bind_native027
collect_initial_ledger = old.collect_initial_ledger


def json_data(value):
    """Mapping contents only; never clone capability-bearing dict attributes."""
    return json.loads(json.dumps(value, allow_nan=False, sort_keys=True))


class NativeCollectionAttempt(dict):
    def __init__(self, token, result, accepted):
        if token is not _ATTEMPT_TOKEN:
            raise ValueError('recollection:actual_owner_endpoints_required')
        data = json_data(result)
        super().__init__(data)
        self._token, self._accepted = token, accepted
        self._at = data['native_read']['at']
        self._encoded = json.dumps(data, allow_nan=False, sort_keys=True)


def is_native_attempt(value):
    try:
        return (type(value) is NativeCollectionAttempt and value._token is _ATTEMPT_TOKEN
                and old._valid_handle(value._accepted._native, value._accepted._session,
                                      value._accepted)
                and value._accepted._session.physical_time == value._at
                and json.dumps(value, allow_nan=False, sort_keys=True) == value._encoded)
    except (AttributeError, TypeError, ValueError):
        return False


def is_native_collected(value):
    return (is_native_attempt(value)
            and value.get('status') == 'conditional_native_delivered_later_v3_model_input'
            and value.get('native_delivery_verified') is True)


def collect_native(native, session, owner, own_request_id, **kwargs):
    result = _collect(native, session, owner, own_request_id, **kwargs)
    read = result.get('native_read', {})
    accepted = kwargs.get('accepted')
    if (not old._valid_handle(native, session, accepted)
            or read.get('owner') != owner or read.get('own_request_id') != own_request_id
            or read.get('at') != session.physical_time
            or read.get('actual_endpoints') != ['observe_protocol', 'protocol_command',
                                               'protocol_planning_snapshots_v3']
            or set(result.get('raw_endpoints', {})) != {'view', 'command', 'received'}):
        return result
    return NativeCollectionAttempt(_ATTEMPT_TOKEN, result, accepted)
