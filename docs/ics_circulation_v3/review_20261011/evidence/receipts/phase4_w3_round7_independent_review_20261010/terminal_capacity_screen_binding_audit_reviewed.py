"""Independent sufficient-screen edge cases; no original-network replay."""
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json

import pytest

from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, InFlight, Leg, Network, Node, Reservation,
    RouteCandidate, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, INFINITY
from scripts.experiments.ics_circulation_v3.terminal_capacity_screen import (
    ScreenAccounting, TerminalScreenGenerator, terminal_capacity_certificate,
)


def state(capacity=1):
    nodes = {name: Node(name, 'zone', 'owner', capacity if name == 'D' else 5) for name in ('A', 'D', 'P')}
    graph = Network(nodes, {'AD': Edge('AD', 'A', 'D', 1), 'PD': Edge('PD', 'P', 'D', 20)})
    return Snapshot(0, graph, {'query': Tray('query', 'A', 'loaded', 'bag'), 'other': Tray('other', 'P')},
                    {'bag': Bag('bag', 'A', 'D', 0, 100)})


def certificate(snapshot, horizon=5, **kwargs):
    return terminal_capacity_certificate(snapshot, 'query', 'D', horizon, **kwargs)


def test_late_future_occupancy_is_a_conflict_even_when_cutoff_is_empty():
    s = state()
    s.reservations = (Reservation('node:D', 20, 23, 'other'),)
    result = certificate(s)
    assert result['certified'] and result['conflict_at'] == 20
    assert result['cutoff'] == 5


@pytest.mark.parametrize('end, expected', [(4, False), (5, False), (6, True)])
def test_release_at_cutoff_uses_half_open_end(end, expected):
    s = state()
    s.reservations = (Reservation('node:D', 1, end, 'other'),)
    assert certificate(s)['certified'] is expected


def test_start_at_cutoff_counts_but_infinity_empty_interval_does_not():
    s = state()
    s.reservations = (Reservation('node:D', 5, INFINITY, 'other'),)
    assert certificate(s)['certified']
    s.reservations = (Reservation('node:D', INFINITY, INFINITY, 'other'),)
    assert not certificate(s)['certified']


def test_same_owner_overlap_and_turnover_do_not_double_count():
    s = state(capacity=2)
    s.reservations = (Reservation('node:D', 4, 9, 'other'), Reservation('node:D', 5, 7, 'other'))
    assert not certificate(s)['certified']
    s.trays['third'] = Tray('third', 'P')
    s.reservations = (Reservation('node:D', 4, 6, 'other'), Reservation('node:D', 6, 9, 'third'))
    assert not certificate(s)['certified']
    s.reservations = (Reservation('node:D', 4, 7, 'other'), Reservation('node:D', 6, 9, 'third'))
    result = certificate(s)
    assert result['certified'] and result['conflict_at'] == 6 and result['other_occupancy'] == 2


def test_idle_stock_and_its_duplicate_explicit_description_consume_one_unit():
    s = state(capacity=2)
    s.trays['other'] = Tray('other', 'D')
    s.reservations = (Reservation('node:D', 0, INFINITY, 'other'),)
    assert not certificate(s)['certified']
    s.network.nodes['D'] = replace(s.network.nodes['D'], capacity=1)
    assert certificate(s)['certified']


def test_future_old_transit_arrival_counts_without_explicit_slot():
    s = state()
    s.trays['other'] = Tray('other', None, 'in_transit')
    s.old_in_transit = (InFlight('other', 'PD', 0, 20),)
    result = certificate(s)
    assert result['certified'] and result['conflict_at'] == 20
    assert result['witness_slots'] == [{'tray_id': 'other', 'start': 20, 'end': INFINITY}]


def test_query_owner_is_excluded_from_explicit_and_old_transit_slots():
    s = state()
    s.reservations = (Reservation('node:D', 0, INFINITY, 'query'),)
    s.old_in_transit = (InFlight('query', 'PD', 0, 20),)
    assert not certificate(s)['certified']


def test_zero_leg_self_stock_is_excluded_even_at_no_wait_destination_with_hold():
    s = state()
    s.trays['query'] = replace(s.trays['query'], node='D')
    s.network.nodes['D'] = replace(s.network.nodes['D'], can_wait=False)
    s.module = FixedLocalModule(unload_ticks=2, hold_by_node={'D': 50})
    assert not certificate(s, horizon=0)['certified']
    s.trays['other'] = Tray('other', 'D')
    assert certificate(s, horizon=0)['certified']


def test_reception_conflict_is_not_misreported_as_node_certificate():
    s = state()
    s.reservations = (Reservation('reception:D', 0, INFINITY, 'other'),)
    assert not certificate(s)['certified']


@pytest.mark.parametrize('horizon', [-1, 1.5, True, INFINITY])
def test_unsupported_horizon_delegates_without_certificate(horizon):
    result = certificate(state(), horizon=horizon)
    assert not result['certified'] and result['status'] == 'unsupported_or_invalid_delegate'


def test_record_budget_is_unknown_not_infeasible_and_snapshot_is_not_cached_or_mutated():
    s = state()
    s.trays['other'] = Tray('other', 'D')
    before = deepcopy(asdict(s))
    result = certificate(s, max_records=1)
    assert not result['certified'] and result['status'] == 'screen_record_budget_unknown_delegate'
    assert certificate(s)['certified']
    assert asdict(s) == before
    s.trays['other'] = Tray('other', 'P')
    assert not certificate(s)['certified']


def test_all_certified_small_intervals_reject_every_within_horizon_full_witness():
    # This oracle is the unchanged execution validator, not screen internals.
    certified_cases = 0
    for horizon in (1, 2, 4):
        for start in range(0, 7):
            for end in range(start + 1, 9):
                s = state()
                s.reservations = (Reservation('node:D', start, end, 'other'),)
                if not certificate(s, horizon)['certified']:
                    continue
                certified_cases += 1
                for arrival in range(1, horizon + 1):
                    candidate = RouteCandidate('candidate', 'bag', 'query', (Leg('AD', arrival - 1, arrival),),
                        arrival + 1, arrival + 1, 0, 'baseline', True, 'D')
                    assert not ExecutionValidator().validate(s, candidate, route_mode='whole_route').accepted
                    assert not ExecutionValidator().validate(s, candidate, route_mode='next_edge').accepted
    assert certified_cases > 50


def test_unknown_bag_preserves_original_empty_invalid_request_behavior():
    s = state()
    original = RegionalCandidateGenerator(horizon=5, deadline_ms=None, cache_contract='isolated_replay_v1')
    wrapper = TerminalScreenGenerator(RegionalCandidateGenerator(horizon=5, deadline_ms=None, cache_contract='isolated_replay_v1'))
    assert original.generate(s, 'missing', 'query', 4) == wrapper.generate(s, 'missing', 'query', 4) == ()
    assert original.last_search_status == wrapper.last_search_status == 'invalid_request'
    assert original.last_expansions == wrapper.last_expansions == 0


def test_delegate_failure_retains_measured_screen_and_partial_search_ledger(monkeypatch):
    original = RegionalCandidateGenerator(horizon=5, deadline_ms=None, cache_contract='isolated_replay_v1')
    def fail(*args):
        original.last_expansions = 7
        original.last_search_status = 'injected_partial'
        original.last_diagnostics = {'work_units_by_stage': {'partial': 7}}
        raise RuntimeError('injected delegate failure')
    monkeypatch.setattr(original, 'generate', fail)
    accounting = ScreenAccounting()
    wrapper = TerminalScreenGenerator(original, accounting)
    with pytest.raises(RuntimeError, match='injected delegate failure'):
        wrapper.generate(state(), 'bag', 'query', 4)
    assert len(accounting.rows) == 1
    row = accounting.rows[0]
    assert row['certificate']['screen_work'] > 0 and row['search_work'] == 7
    assert row['error']['type'] == 'RuntimeError'
    assert accounting.screen_work == row['certificate']['screen_work']


def test_same_identity_and_empty_pool_still_bind_full_pre_query_snapshot():
    first = state()
    first.trays['other'] = Tray('other', 'D')
    second = first.clone()
    second.network.nodes['A'] = replace(second.network.nodes['A'], capacity=6)
    wrapper = TerminalScreenGenerator(RegionalCandidateGenerator(horizon=5, deadline_ms=None, cache_contract='isolated_replay_v1'))
    hashes = [sha256(json.dumps(asdict(s), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest() for s in (first, second)]
    assert wrapper.generate(first, 'bag', 'query', 4) == wrapper.generate(second, 'bag', 'query', 4) == ()
    rows = wrapper.accounting.rows
    assert all(rows[0][key] == rows[1][key] for key in ('time', 'version', 'bag_id', 'tray_id', 'destination', 'requested_k', 'options'))
    assert [row['public_snapshot_sha256'] for row in rows] == hashes
    assert hashes[0] != hashes[1]
    first.completed['later'] = 99
    assert rows[0]['public_snapshot_sha256'] == hashes[0]
    assert wrapper.accounting.observation_cpu_seconds == sum(row['observation_cpu_seconds'] for row in rows)
