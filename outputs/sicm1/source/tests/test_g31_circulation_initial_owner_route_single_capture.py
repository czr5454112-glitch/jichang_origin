"""Synthetic authority scaffolding, not a real NativeSession or model run."""
import ast
import copy
import hashlib
from importlib.machinery import ExtensionFileLoader, ModuleSpec
import inspect
import json
from types import ModuleType, SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_single_capture as c
from scripts.experiments.g31_ics_circulation import initial_owner_route_campaign_v3 as old
from test_g31_circulation_preexisting_online_model import initial_pair


def fixture(tmp_path, case=0):
    view, ack, received = initial_pair('A', case)
    view['node_records'] = [tuple(x) for x in view['node_records']]
    view['edge_records'] = [tuple(x) for x in view['edge_records']]
    path = tmp_path/'synthetic_only_not_loaded.pyd'
    path.write_bytes(b'pure identity scaffold; not an executable extension')
    native = ModuleType('czr005_circulation')
    native.__file__ = str(path)
    native.__spec__ = ModuleSpec(native.__name__, ExtensionFileLoader(native.__name__, str(path)))
    native._g31_native_artifact_identity = {'resolved_path': str(path.resolve()),
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    class Session:
        physical_time = .11
        def __init__(self):
            self.calls = []; self.failure = None; self.values = {'view': copy.deepcopy(view),
                'command': {'last_delivered_ack': copy.deepcopy(ack)}, 'received': copy.deepcopy(received)}
        def get(self, name, args):
            self.calls.append((name, args))
            if self.failure and self.failure[0] == name:
                raise self.failure[1]
            return copy.deepcopy(self.values[name])
        def observe_protocol(self, owner): return self.get('view', (owner,))
        def protocol_command(self, owner, identity): return self.get('command', (owner, identity))
        def protocol_planning_snapshots(self, owner): return self.get('received', (owner,))
    Session.__module__ = 'czr005_circulation'
    native.NativeSession = Session
    return native, Session


def test_only_bound_check_factory(capture):
    # TEST ONLY: replace the outer accepted-run handle check in a private
    # function. Inline module/path and both downstream original checks remain.
    # The production public collector below is separately tested to reject it.
    fn = c.collector(capture)
    return c.clone(fn, {**fn.__globals__, '_valid_handle': lambda *args: True})


test_only_bound_check_factory.__test__ = False


def pure_candidate():
    return c.clone(c.captured_collection,
        {**c.captured_collection.__globals__, 'collector': test_only_bound_check_factory})


def pure_old():
    bound = c.clone(c._BOUND, {**c._BOUND.__globals__, '_valid_handle': lambda *args: True})
    return c.clone(old.captured_collection, {**old.captured_collection.__globals__,
        'request': SimpleNamespace(adapter=SimpleNamespace(collect_initial_ledger=bound))})


def mutable_ids(value):
    result = set()
    if type(value) in (dict, list, tuple):
        if type(value) is not tuple:
            result.add(id(value))
        for member in value.values() if type(value) is dict else value:
            result.update(mutable_ids(member))
    return result


@pytest.mark.parametrize('case', range(6))
def test_exact_old_success_values_order_and_one_actual_triplet(tmp_path, case):
    native, Session = fixture(tmp_path, case)
    before, after = Session(), Session()
    old_records, new_records = [], []
    expected, expected_ledger = pure_old()(old_records, native, before, 'A', 'pure-request', accepted=object())
    actual, actual_ledger = pure_candidate()(new_records, native, after, 'A', 'pure-request', accepted=object())
    encode = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    assert encode(actual) == encode(expected)
    assert encode(new_records) == encode(old_records)
    assert actual_ledger.audit_copy() == expected_ledger.audit_copy()
    assert type(actual_ledger) is c.rolling.NativeJobLedger
    assert len(before.calls) == 6 and len(after.calls) == 3
    assert after.calls == before.calls[:3]
    assert mutable_ids(actual).isdisjoint(mutable_ids(new_records))
    assert mutable_ids(new_records[0]['information']).isdisjoint(mutable_ids(new_records[0]['endpoints']))
    actual['bundle']['jobs']['loaded']['allow_suffix_reroute'] = False
    assert new_records[0]['information']['bundle']['jobs']['loaded']['allow_suffix_reroute'] is True


def test_real_public_boundary_rejects_scaffold_and_mints_no_ledger(tmp_path):
    native, Session = fixture(tmp_path)
    session = Session(); records = []
    result, ledger = c.captured_collection(records, native, session, 'A', 'pure', accepted=object())
    assert result['native_delivery_verified'] is False and ledger is None
    assert session.calls == []
    assert records[0]['capture_failure']['status'] == 'unknown_incomplete_endpoint_collection'


@pytest.mark.parametrize('index', range(3))
def test_each_native_query_failure_preserves_exact_returned_prefix_and_primary(tmp_path, index):
    native, Session = fixture(tmp_path)
    session = Session(); records = []; error = RuntimeError('original query failure')
    session.failure = (c._FIELDS[index], error)
    with pytest.raises(RuntimeError) as saved:
        pure_candidate()(records, native, session, 'A', 'pure', accepted=object())
    assert saved.value is error
    evidence = records[0]['capture_failure']
    assert evidence['completed'] == list(c._FIELDS[:index])
    assert evidence['active'] == c._FIELDS[index]
    assert [row['endpoint'] for row in evidence['started']] == list(c._FIELDS[:index+1])
    assert 'typed_returned_prefix' in evidence
    assert records[0]['information'] is None and records[0]['ledger'] is None
    assert len(session.calls) == index+1
    session.failure = None
    result, ledger = pure_candidate()(records, native, session, 'A', 'next', accepted=object())
    assert result['native_delivery_verified'] is True and ledger is not None
    assert 'capture_failure' not in records[1]
    assert evidence['active'] == c._FIELDS[index]


def test_downstream_json_guard_retains_all_returned_endpoints_and_no_fake_complete(tmp_path):
    native, Session = fixture(tmp_path)
    native._g31_native_artifact_identity['synthetic_nonfinite'] = float('nan')
    session = Session(); records = []
    with pytest.raises(ValueError, match='Out of range float values'):
        pure_candidate()(records, native, session, 'A', 'pure', accepted=object())
    failure = records[0]['capture_failure']
    assert failure['completed'] == ['view', 'command', 'received'] and failure['active'] is None
    assert 'typed_returned_prefix' in failure
    assert records[0]['information'] is None and records[0]['ledger'] is None


def test_failed_normalization_after_collector_preserves_original_exception(tmp_path):
    native, Session = fixture(tmp_path); session = Session(); records = []
    original = ValueError('injected normalization rejection')
    def reject(value):
        assert value['native_delivery_verified'] is True  # Synthetic scaffold only.
        raise original
    function = c.clone(c.captured_collection, {**pure_candidate().__globals__, '_NORMALIZE': reject})
    with pytest.raises(ValueError) as failure:
        function(records, native, session, 'A', 'pure', accepted=object())
    assert failure.value is original and len(session.calls) == 3
    saved = records[0]['capture_failure']
    assert saved['completed'] == ['view', 'command', 'received'] and saved['active'] is None
    assert 'typed_returned_prefix' in saved
    assert records[0]['information'] is None and records[0]['ledger'] is None


def test_failure_export_cannot_mask_native_failure(tmp_path):
    native, Session = fixture(tmp_path)
    session = Session(); error = RuntimeError('primary'); session.failure = ('command', error)
    def bad_snapshot(value): raise ValueError('secondary capture failure')
    ns = {**pure_candidate().__globals__, 'normalization': SimpleNamespace(typed_failure_snapshot=bad_snapshot)}
    function = c.clone(c.captured_collection, ns)
    records = []
    with pytest.raises(RuntimeError) as raised:
        function(records, native, session, 'A', 'pure', accepted=object())
    assert raised.value is error
    assert 'secondary capture failure' in records[0]['capture_failure']['prefix_export_error']


def test_subsequent_collection_is_fresh_and_changed_state_rejected(tmp_path):
    native, Session = fixture(tmp_path); session = Session(); records = []
    first, first_ledger = pure_candidate()(records, native, session, 'A', 'first', accepted=object())
    assert first['native_delivery_verified'] is True
    session.values['command']['last_delivered_ack']['status'] = 'pending_delivery'
    second, second_ledger = pure_candidate()(records, native, session, 'A', 'second', accepted=object())
    assert second['native_delivery_verified'] is False and second_ledger is None
    assert len(session.calls) == 6 and first_ledger is not None
    assert records[0]['endpoints']['command']['last_delivered_ack']['status'] == 'delivered'
    assert records[1]['endpoints']['command']['last_delivered_ack']['status'] == 'pending_delivery'


def test_complete_original_namespace_code_and_ledger_binding():
    capture = c._Capture('A', 'pure'); bound = c.collector(capture)
    assert bound.__code__ is c._BOUND.__code__ and bound.__closure__ is c._BOUND.__closure__
    assert set(bound.__globals__) == set(c._BOUND.__globals__)
    assert {key for key in bound.__globals__ if bound.__globals__[key] is not c._BOUND.__globals__[key]} == {'previous'}
    intermediate = bound.__globals__['previous'].collect_initial_ledger
    assert intermediate.__code__ is c._ROLLING.__code__
    assert intermediate.__globals__['NativeJobLedger'] is c.rolling.NativeJobLedger
    assert intermediate.__globals__['_LEDGER_TOKEN'] is c.rolling._LEDGER_TOKEN
    native = intermediate.__globals__['initial_adapter'].collect_native
    assert set(native.__globals__) == set(c._NATIVE.__globals__) | {'_capture'}
    assert native.__globals__['validate_pair'] is c.initial.validate_pair
    assert native.__globals__['_capture'] is capture
    assert c.source_proof()['inverse_AST_exact'] is True


def test_no_per_collection_AST_compile_and_no_global_mutation(monkeypatch):
    old_namespace = dict(c._NATIVE.__globals__)
    def forbidden(): raise AssertionError('per-request compilation')
    monkeypatch.setattr(c, '_compile_native_template', forbidden)
    first = c.collector(c._Capture('A', '1')); second = c.collector(c._Capture('A', '2'))
    assert first is not second
    assert all(c._NATIVE.__globals__[k] is v for k, v in old_namespace.items())
    assert c.rolling.initial_adapter is c.initial and c.adapter.previous is c.rolling


@pytest.mark.parametrize('name', ('_BOUND', '_ROLLING', '_NATIVE', '_VALIDATE', '_NORMALIZE'))
def test_frozen_code_identity_changes_fail_before_collection(monkeypatch, name):
    monkeypatch.setattr(c, name, object())
    with pytest.raises(ValueError, match='source_identity_drift'):
        c.source_proof()


@pytest.mark.parametrize('defect', ('reorder', 'duplicate', 'missing'))
def test_capture_internal_sequence_is_closed(defect):
    trace = c._Capture('A', 'pure')
    with pytest.raises(ValueError):
        if defect == 'reorder': trace.before('command')
        elif defect == 'duplicate': trace.before('view'); trace.before('view')
        else: trace.after('view', {})
