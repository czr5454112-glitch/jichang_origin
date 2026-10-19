"""Optional, owner-local flight plan snapshots; never jobs or execution authority.

The caller supplies a separate plan feed with trustworthy publication/receipt
provenance. This adapter checks its contract, not the truth of that provenance.
Versions are monotonically increasing full snapshots of one source. Missing
plans stay None, and no existing actor feature or checkpoint is changed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable


SCHEMA = 'g31.foundation.flight_context.v1'
EVENT_PAIRS = {'STD': 'ETD', 'STA': 'ETA', 'SOBT': 'EOBT', 'SIBT': 'EIBT'}
CONTEXT_FIELDS = {'schema_version', 'source_id', 'version', 'published_at',
    'received_at', 'owner_scope', 'time_basis', 'validity_policy', 'entries',
    'availability_basis', 'static_assumption'}
ENTRY_REQUIRED = {'flight_ref', 'identity_kind', 'scheduled_event_type', 'scheduled_event_at'}
ENTRY_OPTIONAL = {'estimated_event_type', 'estimated_event_at',
    'available_bag_count_estimate', 'estimate_source', 'estimate_kind',
    'planned_injection_region', 'mapping_version', 'plan_status'}


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError('flight_context:' + reason)


def _text(value: Any, field: str) -> str:
    _require(type(value) is str and bool(value.strip()), field + '_text_required')
    return value


def _number(value: Any, field: str) -> float:
    _require(type(value) in (int, float) and math.isfinite(value), field + '_finite_number_required')
    return float(value)


@dataclass(frozen=True)
class TimeBasis:
    """All times already converted to seconds using this declared mapping."""

    unit: str
    origin: str
    timezone: str
    conversion_version: str


def _time_basis(value: Any) -> TimeBasis:
    _require(type(value) is dict and set(value) == {
        'unit', 'origin', 'timezone', 'conversion_version'}, 'time_basis_schema')
    _require(value['unit'] == 'seconds', 'time_unit_seconds_required')
    return TimeBasis(**{key: _text(item, 'time_basis_' + key) for key, item in value.items()})


@dataclass(frozen=True)
class ValidityPolicy:
    mode: str
    valid_until: float | None


@dataclass(frozen=True)
class FlightEntry:
    flight_ref: str
    identity_kind: str
    scheduled_event_type: str
    scheduled_event_at: float
    estimated_event_type: str | None = None
    estimated_event_at: float | None = None
    available_bag_count_estimate: float | None = None
    estimate_source: str | None = None
    estimate_kind: str | None = None
    planned_injection_region: str | None = None
    mapping_version: str | None = None
    plan_status: str = 'scheduled'


def _entry(value: Any) -> FlightEntry:
    _require(type(value) is dict and ENTRY_REQUIRED <= set(value)
        and set(value) <= ENTRY_REQUIRED | ENTRY_OPTIONAL, 'entry_schema')
    data = {key: value.get(key) for key in ENTRY_REQUIRED | ENTRY_OPTIONAL}
    data['flight_ref'] = _text(data['flight_ref'], 'flight_ref')
    _require(data['identity_kind'] in ('real_flight', 'historical_group'), 'identity_kind')
    _require(type(data['scheduled_event_type']) is str
        and data['scheduled_event_type'] in EVENT_PAIRS, 'scheduled_event_type')
    data['scheduled_event_at'] = _number(data['scheduled_event_at'], 'scheduled_event_at')
    estimated = data['estimated_event_at'] is not None
    _require(estimated == (data['estimated_event_type'] is not None), 'estimated_event_pair')
    if estimated:
        _require(data['estimated_event_type'] == EVENT_PAIRS[data['scheduled_event_type']],
            'estimated_event_semantics')
        data['estimated_event_at'] = _number(data['estimated_event_at'], 'estimated_event_at')
    count = data['available_bag_count_estimate']
    _require((count is not None) == (data['estimate_source'] is not None)
        == (data['estimate_kind'] is not None), 'estimate_provenance_required')
    if count is not None:
        data['available_bag_count_estimate'] = _number(count, 'bag_count_estimate')
        _require(data['available_bag_count_estimate'] >= 0., 'negative_bag_count_estimate')
        data['estimate_source'] = _text(data['estimate_source'], 'estimate_source')
        _require(data['estimate_kind'] in ('forecast', 'confirmed_advance_record'), 'estimate_kind')
    mapped = data['planned_injection_region'] is not None
    _require(mapped == (data['mapping_version'] is not None), 'mapping_version_required')
    if mapped:
        for field in ('planned_injection_region', 'mapping_version'):
            data[field] = _text(data[field], field)
    data['plan_status'] = value.get('plan_status', 'scheduled')
    _require(data['plan_status'] in ('scheduled', 'cancelled'), 'plan_status')
    return FlightEntry(**data)


@dataclass(frozen=True)
class FlightContext:
    """An immutable plan snapshot, independent of physical observations.

Cancellation or a new estimate does not remove arrived bags, alter deadlines,
or create stock. Unknown region/count remain None. The snapshot is no current
admission credential, even when its validity policy has no expiry.
"""

    schema_version: str
    source_id: str
    version: int
    published_at: float | None
    received_at: float
    owner_scope: str
    time_basis: TimeBasis
    validity_policy: ValidityPolicy
    entries: tuple[FlightEntry, ...]
    availability_basis: str
    static_assumption: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible representation."""
        result = asdict(self)
        result['entries'] = [asdict(entry) for entry in self.entries]
        return result


def _parse(payload: Any, *, owner: str, expected_time_basis: dict[str, Any]) -> FlightContext:
    _require(type(payload) is dict and set(payload) == CONTEXT_FIELDS, 'context_schema')
    _require(payload['schema_version'] == SCHEMA, 'schema_version')
    source_id = _text(payload['source_id'], 'source_id')
    _require(type(payload['version']) is int and payload['version'] >= 1, 'positive_integer_version')
    _require(_text(payload['owner_scope'], 'owner_scope') == owner, 'owner_scope')
    time_basis = _time_basis(payload['time_basis'])
    _require(time_basis == _time_basis(expected_time_basis), 'time_basis_mismatch')
    received = _number(payload['received_at'], 'received_at')
    availability = payload['availability_basis']
    _require(availability in ('source_publication', 'static_predeclared'), 'availability_basis')
    if availability == 'source_publication':
        published = _number(payload['published_at'], 'published_at')
        _require(published <= received, 'publication_after_receipt')
        _require(payload['static_assumption'] is None, 'unexpected_static_assumption')
        assumption = None
    else:
        _require(payload['published_at'] is None, 'static_publication_must_remain_missing')
        published = None
        assumption = _text(payload['static_assumption'], 'static_assumption')
    policy = payload['validity_policy']
    _require(type(policy) is dict and set(policy) == {'mode', 'valid_until'}, 'validity_policy_schema')
    _require(policy['mode'] in ('until_superseded', 'expires_at'), 'validity_policy')
    expiry = policy['valid_until']
    if policy['mode'] == 'expires_at':
        expiry = _number(expiry, 'valid_until')
        # A packet may arrive after expiry. It must still supersede older plans.
        _require(published is None or published < expiry, 'expiry_before_publication')
    else:
        _require(expiry is None, 'unexpected_expiry')
    _require(type(payload['entries']) is list, 'entries_list_required')
    entries = tuple(_entry(entry) for entry in payload['entries'])
    identities = [(entry.identity_kind, entry.flight_ref) for entry in entries]
    _require(len(identities) == len(set(identities)), 'duplicate_flight_identity')
    return FlightContext(SCHEMA, source_id, payload['version'], published, received,
        owner, time_basis, ValidityPolicy(policy['mode'], expiry), entries, availability, assumption)


def adapt_context(payload: dict[str, Any] | None = None, *, owner: str, now: float,
                  expected_time_basis: dict[str, Any]) -> FlightContext | None:
    """Validate one locally received plan; return None for missing/expired data.

Use select_context for replay histories. Source publication is mandatory unless
an explicit static-predeclared assumption is supplied, preserving None for the
missing publication time. Receipt is always required, including static inputs.
    """
    if payload is None:
        return None
    _text(owner, 'owner')
    current = _number(now, 'now')
    result = _parse(payload, owner=owner, expected_time_basis=expected_time_basis)
    _require(result.received_at <= current, 'not_yet_received')
    if result.validity_policy.valid_until is not None and current >= result.validity_policy.valid_until:
        return None
    return result


def select_context(history: Iterable[dict[str, Any]] | None = None, *, source_id: str,
                   owner: str, now: float,
                   expected_time_basis: dict[str, Any]) -> FlightContext | None:
    """Select the highest received full-snapshot version of one source/owner.

Late old packets cannot roll the plan back. Future or other-owner payloads are
not parsed. Once the newest received version expires, return None rather than
resurrect a superseded plan. No interpolation or future version backfill occurs.
    """
    if history is None:
        return None
    _text(source_id, 'source_id')
    _text(owner, 'owner')
    current = _number(now, 'now')
    versions: dict[int, FlightContext] = {}
    for payload in history:
        _require(type(payload) is dict, 'history_payload_schema')
        if payload.get('source_id') != source_id or payload.get('owner_scope') != owner:
            continue
        if _number(payload.get('received_at'), 'received_at') > current:
            continue
        context = _parse(payload, owner=owner, expected_time_basis=expected_time_basis)
        previous = versions.get(context.version)
        if previous is not None:
            left, right = previous.to_dict(), context.to_dict()
            left.pop('received_at')
            right.pop('received_at')
            _require(left == right, 'conflicting_same_version')
            context = min((previous, context), key=lambda item: item.received_at)
        versions[context.version] = context
    if not versions:
        return None
    ordered = [versions[version] for version in sorted(versions)]
    _require(len({item.availability_basis for item in ordered}) == 1, 'availability_basis_changed')
    publications = [item.published_at for item in ordered if item.published_at is not None]
    _require(publications == sorted(publications), 'publication_version_regression')
    latest = ordered[-1]
    expiry = latest.validity_policy.valid_until
    return None if expiry is not None and current >= expiry else latest
