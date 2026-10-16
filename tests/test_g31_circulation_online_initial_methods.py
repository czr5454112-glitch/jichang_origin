"""Synthetic orchestration only; no native/model/actual fixture execution."""
import copy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import research_live_obligation_initial_methods as subject


def vector(owner):
    return {'initial_action': 'prefer_2' if owner == 'A' else 'native_default',
            'empty_departure': 0.5 if owner == 'A' else 1.0,
            'return_delay': .5 if owner == 'A' else 0.,
            'later_action': 'native_default' if owner == 'A' else 'prefer_8'}


def record(owner):
    return {'owner': owner, 'arm': 'finite_MPC', 'selected_action': vector(owner),
        'native_request_id': owner + '-issued', 'native_default_no_command': False,
        'status': 'local_component_submitted_ACK_and_physical_outcome_pending',
        'instrumentation_complete': True,
        'immediate_component': {'status': 'fresh_local_component_proposal'},
        'collection': {'owner': owner}}


def install(monkeypatch, *, transform=lambda x: x, ledger=True, error=None):
    captured = []
    token = object() if ledger else None
    def choose(native, session, client, owner, publication, accepted, *, arm, incumbent_index, progress):
        progress.update(transform(record(owner)))
        if error is not None:
            client.rows[owner + '-issued'] = {'request': {'owner_id': owner}}
            raise error
        return progress, token
    def policy(native, session, client, owner, actual_ledger, channel, selected, accepted, supply):
        captured.append((owner, actual_ledger, channel, selected, supply))
        return object()
    monkeypatch.setattr(subject.dispatch, 'choose_and_submit', choose)
    monkeypatch.setattr(subject.retained, 'OwnerPolicy', policy)
    return captured, token


class OwnOnly(dict):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
    def __getitem__(self, key):
        assert key == self.owner, 'peer proposal access'
        return super().__getitem__(key)
    def __iter__(self):
        raise AssertionError('global proposal scan')
    def values(self):
        raise AssertionError('global proposal scan')
    def items(self):
        raise AssertionError('global proposal scan')


def step(owner, progress, ledgers, policies, client=None):
    subject.start_owner(None, None, client, owner, owner + '-publication', owner + '-channel',
        object(), arm='finite_MPC', incumbent=4, progress=progress, ledgers=ledgers, policies=policies)


def test_declared21_uses_stronger_original_incumbent():
    rows = subject.rows()
    assert len(rows) == 21
    assert list(rows) == [case + '/' + arm for case in subject.CASES for arm in subject.ARMS]
    assert {row['incumbent_index'] for row in rows.values()} == {subject.incumbent_index()}
    actions = subject.old.construction.actions()
    assert actions[subject.incumbent_index()] == subject.protocol.incumbent_action()
    assert actions[subject.incumbent_index()]['return_delay'] == 0.
    assert all(row['fault'] is None and 'vector' not in row for row in rows.values())


@pytest.mark.parametrize('owner', ['A', 'B'])
def test_each_owner_can_start_without_peer_record(monkeypatch, owner):
    captured, token = install(monkeypatch)
    progress, ledgers, policies = OwnOnly(owner), {}, {}
    step(owner, progress, ledgers, policies)
    assert captured == [(owner, token, owner + '-channel', vector(owner),
                         owner + '-issued' if owner == 'B' else None)]
    assert set(policies) == {owner} and ledgers == {owner: token}
    progress[owner]['selected_action']['return_delay'] = 77
    assert captured[0][3] == vector(owner)


def test_different_owner_proposals_both_create_local_policy(monkeypatch):
    captured, _ = install(monkeypatch)
    progress, ledgers, policies = {}, {}, {}
    for owner in ('A', 'B'):
        step(owner, progress, ledgers, policies)
    assert set(policies) == {'A', 'B'}
    assert [item[3] for item in captured] == [vector('A'), vector('B')]
    assert progress['A']['selected_action'] != progress['B']['selected_action']


@pytest.mark.parametrize('change,has_ledger', [
    ({'status': 'unknown_final_local_guard'}, True),
    ({'selected_action': None}, True),
    ({}, False),
])
def test_missing_origin_does_not_create_policy_or_destroy_other(monkeypatch, change, has_ledger):
    captured, _ = install(monkeypatch, transform=lambda x: {**x, **change}, ledger=has_ledger)
    other = object()
    progress, ledgers, policies = {}, {}, {'B': other}
    step('A', progress, ledgers, policies)
    assert not captured and policies == {'B': other}
    assert progress['A']['continuation_policy_created'] is False


@pytest.mark.parametrize('change', [
    {'owner': 'A'}, {'arm': 'incumbent'}, {'instrumentation_complete': False},
    {'native_request_id': None},
])
def test_wrong_own_origin_rejects_before_policy(monkeypatch, change):
    captured, _ = install(monkeypatch, transform=lambda x: {**x, **change})
    with pytest.raises(ValueError):
        step('B', {}, {}, {})
    assert captured == []


def test_default_A_can_retain_own_suffix_without_command(monkeypatch):
    def default(value):
        value['selected_action']['initial_action'] = 'native_default'
        value.update(status='selected_native_default_no_command', native_default_no_command=True,
                     native_request_id=None)
        return value
    captured, _ = install(monkeypatch, transform=default)
    step('A', {}, {}, {})
    assert captured[0][3]['initial_action'] == 'native_default' and captured[0][4] is None


def test_dispatch_exception_retains_actual_sink_and_row(monkeypatch):
    error = RuntimeError('issued then failed')
    captured, _ = install(monkeypatch, error=error)
    progress, client = {}, SimpleNamespace(rows={})
    with pytest.raises(RuntimeError) as raised:
        step('B', progress, {}, {}, client)
    assert raised.value is error and not captured
    assert progress['B']['native_request_id'] == 'B-issued'
    assert 'B-issued' in client.rows


def test_duplicate_owner_never_dispatches_again(monkeypatch):
    captured, _ = install(monkeypatch)
    with pytest.raises(ValueError, match='fresh_owner_step'):
        step('A', {'A': {}}, {}, {})
    assert not captured


@pytest.mark.parametrize('owners', [('A',), ('B',), ('A', 'B'), ()])
def test_original_continuation_schedules_only_present_policies(monkeypatch, owners):
    monkeypatch.setattr(subject.old.v1, 'HORIZON', .12)
    monkeypatch.setattr(subject.old.v1, 'START', .11)
    monkeypatch.setattr(subject.old.v1, 'PERIOD', .01)
    events = []
    class Session:
        physical_time = .11
        def advance_until_owner_notification(self, requested, cursors, deadline, max_events):
            assert requested == ['A', 'B'] and max_events == 100000
            assert set(cursors) == set(requested), 'notification_cursor_keys_mismatch'
            self.physical_time = deadline
            return {'status': 'horizon_reached', 'timestamp_complete': True, 'notifications': {}}
        def advance_to(self, at):
            self.physical_time = at
        def result_at(self, at):
            assert at == self.physical_time
            return {'synthetic_result': at}
    class Policy:
        pending = None
        peer_quiet_until = 0.
        choices, returns, supplies, recovery = [], [], [], []
        def __init__(self, owner): self.owner = owner
        def activate(self, trigger): events.append((self.owner, trigger['periodic_tick']))
    client = SimpleNamespace(activate=lambda owner, trigger: events.append(('close', owner)),
        refresh_owner=lambda owner, retry: events.append(('refresh', owner, retry)))
    progress = {}
    continuation, result = subject._CONTINUE(Session(), client, {o: Policy(o) for o in owners}, progress)
    assert [event for event in events if event[0] in ('A', 'B')] == [(o, True) for _ in range(2) for o in sorted(owners)]
    assert continuation['missing_owner_policies'] == [o for o in ('A', 'B') if o not in owners]
    assert continuation['status'] == 'finished' and result == {'synthetic_result': .12}
    assert len(progress['native_batches']) == 2


def test_posthoc_composite_uses_only_respective_owner_components(monkeypatch):
    initial = {o: {**record(o), 'continuation_policy_created': True} for o in ('A', 'B')}
    before = copy.deepcopy(initial)
    seen = []
    def assess(*args):
        seen.append(copy.deepcopy(args[-1]))
        return {'status': 'assessed', 'business_complete': True}
    monkeypatch.setattr(subject.old, 'assess_cell', assess)
    decisions = {o: [{'information': {'native_delivery_verified': True},
        'selected_action_admitted': True, 'fallback_used': False}] for o in ('A', 'B')}
    result = subject.completed_summary({}, {}, None, {'missing_owner_policies': []}, initial, decisions)
    assert seen == [{'initial_action': 'prefer_2', 'empty_departure': 1.,
                     'return_delay': .5, 'later_action': 'prefer_8'}]
    assert initial == before and result['status'] == 'assessed'
    assert result['owner_proposals_agreed_posthoc'] is False
    assert result['strict_protected'] is None and result['complete_request_100ms_certified'] is False


def test_missing_owner_cannot_be_filled_by_peer_estimate(monkeypatch):
    monkeypatch.setattr(subject.old, 'assess_cell', lambda *args: pytest.fail('invented missing owner'))
    initial = {'A': {**record('A'), 'continuation_policy_created': True}}
    result = subject.completed_summary({}, {}, None, {'missing_owner_policies': ['B']}, initial, {})
    assert result['status'] == 'unknown_missing_owner_initial_proposal'
    assert result['business_metrics'] is None and result['strict_protected'] is None


def test_partial_branch_uses_const_diagnostics_and_keeps_dispatch(monkeypatch):
    class Session:
        physical_time = .11
        def offline_diagnostics(self): return {'const_only': True}
        def result_at(self, *args): pytest.fail('advanced after failure')
    def fail(*args, progress, **kwargs):
        progress.update(session=Session(), client=SimpleNamespace(calls=[], rows={'B-issued': {}},
            creations={}, roots=[], ack_handling=[]), initial_owners={'B': record('B')}, stage='initial')
        raise RuntimeError('partial dispatch')
    monkeypatch.setattr(subject, '_run_branch', fail)
    result = subject.run_branch(None, {}, {}, {}, accepted_run=None, branch_key='x')
    assert result['partial'] is True and result['summary']['status'] == 'unknown_failed_partial'
    assert result['initial_owners']['B']['native_request_id'] == 'B-issued'
    assert 'B-issued' in result['outbox'] and result['physical_time_after_diagnostics'] == .11
