"""Static-cache semantics and scalar-only timing; no native process is started."""
import copy
from dataclasses import FrozenInstanceError
import pytest
from scripts.experiments.g31_ics_circulation import foundation_repeated_domain as domain
from scripts.experiments.g31_ics_circulation import foundation_repeated_native as native
from scripts.experiments.g31_ics_circulation import foundation_repeated_registry as registry
from scripts.experiments.g31_ics_circulation import foundation_repeated_timing as timing


def old_identify(contract, jobs):
    domain.require(domain.old_guard.canonical(contract) == domain.old_guard.canonical(domain.old_guard.supported_contract(later=True)),
        'repeated_fixed_physical_contract_changed')
    matches = []
    for case in domain.CASES:
        expected = {row['business_bag_id']: {**row, 'protected_service': True} for row in domain.scene(case)['jobs']}
        if set(jobs) == set(expected) and all(all(jobs[key][field] == expected[key][field]
            for field in domain.old_guard.CONTRACT_FIELDS) for key in jobs):
            matches.append(case)
    domain.require(len(matches) == 1, 'repeated_business_contract_not_registered')
    return matches[0]


def jobs(case):
    return {row['business_bag_id']: {**row, 'protected_service': True} for row in domain.scene(case)['jobs']}


def test_all_ten_registered_cases_have_exact_static_match_and_no_rebuild(monkeypatch):
    contract = domain.old_guard.supported_contract(later=True)
    observations = {case: jobs(case) for case in domain.CASES}
    assert len(observations) == 10
    for case, population in observations.items():
        assert old_identify(contract, population) == case
    audit = domain.initialize_static_registry()
    assert audit['case_count'] == 10 and audit['dynamic_state_cached'] is False
    def forbidden(*args, **kwargs):
        raise AssertionError('static scene rebuilt in actual identify')
    monkeypatch.setattr(domain, 'scene', forbidden)
    monkeypatch.setattr(domain.old_guard, 'supported_contract', forbidden)
    for case, population in observations.items():
        assert domain.identify(contract, population) == case


def test_compiled_registry_is_immutable_and_owns_its_static_inputs():
    declared = {'case': [1, 2]}; original = {'one': {'field': 2.}}
    compiled = registry.compile_registry(physical_canonical='physical', registry_declaration=declared,
        contract_fields=('field',), case_names=('case',), build_jobs=lambda _: original)
    signature = registry.immutable(declared)
    declared['case'].append(3); original['one']['field'] = 5.
    assert compiled.identify('physical', {'one': {'field': 2}}, declaration=signature, contract_fields=('field',)) == 'case'
    with pytest.raises(FrozenInstanceError):
        compiled.fields = ('other',)
    with pytest.raises(ValueError, match='declaration_changed'):
        compiled.identify('physical', {'one': {'field': 2}}, declaration=registry.immutable(declared), contract_fields=('field',))


@pytest.mark.parametrize('failure', ['missing', 'extra', 'field', 'physical', 'registry', 'field_order'])
def test_compiled_registry_refuses_contract_or_registry_changes(failure, monkeypatch):
    contract = domain.old_guard.supported_contract(later=True)
    population = jobs('hold3_11_65_release27_5'); domain.initialize_static_registry()
    if failure == 'missing':
        population.pop('blocker')
    elif failure == 'extra':
        population['unknown'] = dict(population['blocker'])
    elif failure == 'field':
        population['blocker']['storage_release_at'] += .001
    elif failure == 'physical':
        contract['node_contracts'][0]['capacity'] += 1
    elif failure == 'registry':
        monkeypatch.setitem(domain.CASES, 'hold3_11_65_release27_5', 11.65001)
    else:
        monkeypatch.setattr(domain.old_guard, 'CONTRACT_FIELDS', tuple(reversed(domain.old_guard.CONTRACT_FIELDS)))
    with pytest.raises(ValueError):
        domain.identify(contract, population)


def test_every_business_contract_field_remains_compared():
    contract = domain.old_guard.supported_contract(later=True)
    population = jobs('hold3_11_65_release27_5'); domain.initialize_static_registry()
    for field in domain.old_guard.CONTRACT_FIELDS:
        altered = copy.deepcopy(population); value = altered['blocker'][field]
        altered['blocker'][field] = not value if type(value) is bool else value+'-changed' if type(value) is str else value+.12345
        with pytest.raises(ValueError, match='business_contract_not_registered'):
            domain.identify(contract, altered)


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now
    def advance(self, milliseconds): self.now += int(milliseconds*1e6)


def test_logical_wait_current_stages_submit_and_ack_are_separate_wall_intervals():
    clock = Clock(); recorder = timing.Recorder(clock=clock)
    activation = recorder.activation_start('B', 12.)
    request = recorder.request_start(owner='B', phase='cycle_route', root_id='root', target_job='reuse2',
        generation=8, traversal_id=9, sim_at=12.)
    recorder.bind(request, 'collection')
    clock.advance(10); recorder.mark(request, 'ready_entry', sim_at=12.04)
    recorder.mark(request, 'collect_start'); clock.advance(5); recorder.mark(request, 'collect_end')
    recorder.mark(request, 'route_dispatch_start'); clock.advance(2)
    recorder.submit(request_id='route', kind='route', owner='B', retry=False, started_ns=15_500_000,
        ended_ns=16_500_000, sim_at=12.04, status='pending')
    recorder.mark(request, 'route_dispatch_end'); clock.advance(3)
    recorder.request_end(request, status='protected_current', sim_at=12.04, command_id='route', decision_id='decision')
    recorder.activation_end(activation, root_id='later_root', sim_at=12.04, status='returned')
    recorder.ack_read(request_id='route', owner='B', sequence=1, status='updated', delivered_sim_s=12.07,
        started_ns=25_000_000, ended_ns=26_000_000)
    report = recorder.audit(); row = report['requests'][0]
    assert row['logical_wait_to_ready_wall_ms'] == 10. and row['open_to_controller_done_wall_ms'] == 20.
    assert row['ready_to_controller_done_wall_ms'] == 10. and row['actual_native_submit_wall_ms'] == 1.
    assert row['open_to_native_submit_return_wall_ms'] == 16.5 and row['open_to_route_dispatch_return_wall_ms'] == 17.
    assert row['stage_wall_ms']['collect'] == 5. and row['stage_wall_ms']['route_dispatch_envelope'] == 2.
    assert row['submit_to_ack_read_envelopes'][0]['submit_return_to_read_end_wall_ms'] == 9.5
    assert row['open_sim_s'] == 12. and row['close_sim_s'] == 12.04
    assert report['physical_effect_exact_wall_time_measured'] is False
    assert report['overlapping_envelopes_must_not_be_summed'] is True


def test_timing_keeps_refusal_no_command_exception_and_open_denominator():
    recorder = timing.Recorder(clock=Clock())
    for status in ('original_fallback', 'protected_current', 'exception', 'open'):
        record = recorder.request_start(owner='B', phase='cycle_route', root_id='r', target_job='reuse2',
            generation=1, traversal_id=1, sim_at=1.)
        if status != 'open': recorder.request_end(record, status=status, sim_at=1.)
    rows = recorder.audit()['requests']
    assert [row['status'] for row in rows] == ['original_fallback', 'protected_current', 'exception', 'open']
    assert all(row['actual_native_submit_wall_ms'] is None for row in rows)
    assert rows[-1]['open_to_controller_done_wall_ms'] is None


class FakeSession:
    physical_time = .1
    def submit_protocol_command(self, request): return {'status': 'pending', 'reason': 'command_enqueued'}
    def submit_protocol_transfer(self, request): return {'status': 'pending', 'reason': 'request_enqueued'}
    def protocol_command(self, owner, identity):
        return {'last_delivered_ack': {'sequence': 1, 'status': 'updated', 'delivered_at': .2}}
    def protocol_request(self, owner, identity):
        return {'last_delivered_ack': {'sequence': 1, 'status': 'received', 'delivered_at': .2}}


def test_audit_sink_keeps_exact_original_transport_type_methods_and_ledger_gate():
    original = native.bound.LocalTransport(FakeSession())
    instrumented = native.bound.LocalTransport(FakeSession())
    instrumented.path_timing = timing.Recorder()
    instrumented.native_submit_timings = instrumented.path_timing.submits
    for client in (original, instrumented):
        client.activate('B', {'kind': 'fixture'})
        for kind in ('route', 'transfer'):
            identity = client.submit('B', kind, kind, tray_id='L')
            client.send(identity, retry=True)
        client.session.physical_time = .2
        client.refresh_owner('B')
    assert original.calls == instrumented.calls and original.rows == instrumented.rows
    assert original.creations == instrumented.creations and original.ack_handling == instrumented.ack_handling
    assert type(instrumented) is native.historical.fixture.LocalTransport
    assert 'send' not in vars(instrumented) and 'owned' not in vars(instrumented)
    assert not hasattr(original, 'native_submit_timings')
    measured = instrumented.path_timing.audit()['native_submits']
    assert len(measured) == 4 and all(row['end_wall_ns'] >= row['start_wall_ns'] for row in measured)
    assert all(row['scope'] == 'actual_native_submit_call_only' for row in measured)
    instrumented.activate('B', {'kind': 'current_collection'})
    actual, _, evidence = native.historical.client_owned_snapshot(instrumented, instrumented.session, 'B', instrumented.owned('B'))
    assert set(actual) == set(original.rows) and evidence['owner'] == 'B'


def test_submit_instrumentation_never_executes_a_supplied_callback():
    client = native.bound.LocalTransport(FakeSession())
    def forbidden(*args, **kwargs):
        raise AssertionError('timing must be pure data')
    client.native_submit_timings = forbidden
    client.activate('B', {'kind': 'fixture'})
    client.submit('B', 'route', 'default_off', tray_id='L')
    assert len(client.calls) == 1 and client.rows[client.calls[0]['request']['request_id']]['reply']['status'] == 'pending'


def test_all_initial_continuation_and_final_scopes_preserve_original_calls_and_capture_ack_reads():
    original, measured = (native.bound.LocalTransport(FakeSession()) for _ in range(2))
    recorder = timing.Recorder()
    phases = ('initial_public_epoch', 'fixed_original_initial_action', 'owner_policy_continuation', 'final_outbox_collection')
    def work(client, owner, phase):
        client.activate(owner, {'kind': phase})
        if phase == 'initial_public_epoch':
            client.submit(owner, 'route', 'scope_fixture', tray_id='L')
        else:
            client.refresh_owner(owner, retry=phase != 'final_outbox_collection')
    for phase in phases:
        for owner in ('A', 'B'):
            work(original, owner, phase)
            with recorder.owner_scope(measured, owner, phase=phase):
                work(measured, owner, phase)
    assert original.calls == measured.calls and original.rows == measured.rows
    assert original.creations == measured.creations and original.ack_handling == measured.ack_handling
    assert type(measured) is native.historical.fixture.LocalTransport
    audit = recorder.audit()
    assert len(audit['owner_activations']) == len(measured.roots) == 8
    assert [row['root_id'] for row in audit['owner_activations']] == [row['root_id'] for row in measured.roots]
    assert [row['phase'] for row in audit['owner_activations']] == [phase for phase in phases for _ in ('A', 'B')]
    assert len(audit['ack_read_envelopes']) == len(measured.ack_handling) == 2


def test_scope_exception_before_activation_does_not_reuse_a_previous_root():
    client = native.bound.LocalTransport(FakeSession()); client.activate('B', {'kind': 'previous'})
    recorder = timing.Recorder()
    with pytest.raises(RuntimeError, match='before actual activation'):
        with recorder.owner_scope(client, 'B', phase='owner_policy_continuation'):
            raise RuntimeError('before actual activation')
    row = recorder.audit()['owner_activations'][0]
    assert row['status'] == 'exception' and row['root_id'] is None
    assert len(client.roots) == 1 and not recorder.ack_reads


def test_failure_partial_retains_initial_and_final_ack_envelopes_and_open_requests(tmp_path):
    import json
    from scripts.experiments.g31_ics_circulation import foundation_repeated_campaign as campaign
    client = native.bound.LocalTransport(FakeSession()); recorder = timing.Recorder()
    for phase in ('initial_public_epoch', 'final_outbox_collection'):
        try:
            with recorder.owner_scope(client, 'B', phase=phase):
                client.activate('B', {'kind': phase})
                if phase == 'initial_public_epoch':
                    client.submit('B', 'route', 'failure_fixture', tray_id='L')
                else:
                    client.refresh_owner('B', retry=False)
                    recorder.request_start(owner='B', phase='cycle_route', root_id=client.context['root_id'],
                        target_job='reuse2', generation=8, traversal_id=9, sim_at=.2)
                    raise RuntimeError('failed after actual final read')
        except RuntimeError:
            pass
    before = copy.deepcopy((client.calls, client.rows, client.roots, client.ack_handling))
    partial = campaign.capture_repeated_partial({'client': client, 'path_timing': recorder,
        'static_registry_initialization': {'initialization_wall_ns': 42}}, 'fixture exception')
    path = tmp_path/'partial.json'; campaign.environment.write(path, partial)
    saved = json.loads(path.read_text(encoding='utf8'))
    assert saved['path_timing_capture_status'] == 'measured_rows_preserved_without_synthetic_closure'
    assert saved['static_registry_initialization']['initialization_wall_ns'] == 42
    assert saved['path_timing']['owner_activations'][-1]['status'] == 'exception'
    assert len(saved['path_timing']['ack_read_envelopes']) == len(client.ack_handling) == 1
    request = saved['path_timing']['requests'][0]
    assert request['status'] == 'open' and 'close_wall_ns' not in request
    assert request['actual_native_submit_wall_ms'] is None
    assert before == (client.calls, client.rows, client.roots, client.ack_handling)


def test_failure_before_session_keeps_cold_initialization_and_reports_absent_or_failed_capture():
    from scripts.experiments.g31_ics_circulation import foundation_repeated_campaign as campaign
    missing = campaign.capture_repeated_partial({}, 'early exception')
    assert missing['path_timing_capture_status'] == 'unavailable_before_recorder_initialization'
    assert 'path_timing' not in missing
    class FailingRecorder:
        def audit(self): raise ValueError('corrupt recorder')
    failed = campaign.capture_repeated_partial({'path_timing': FailingRecorder(),
        'static_registry_initialization': {'initialization_wall_ns': 99}}, 'session constructor exception')
    assert failed['path_timing_capture_status'] == 'capture_failed'
    assert 'corrupt recorder' in failed['capture_errors']['path_timing']
    assert failed['static_registry_initialization']['initialization_wall_ns'] == 99


@pytest.mark.parametrize('next_node,occupied,submit_fails', [(None, False, False), (3, False, False),
    (8, False, False), (8, True, False), (8, False, True)])
def test_current_dispatch_preserves_full_serialized_transport_and_physical_route_side_effects(next_node, occupied, submit_fails):
    import json
    from types import SimpleNamespace
    class RouteSession(FakeSession):
        physical_time = 15.
        def protocol_planning_snapshots_v3(self, owner): return []
        def submit_protocol_command(self, request):
            if submit_fails: raise RuntimeError('actual submit failed')
            return super().submit_protocol_command(request)
    tray = {'tray_id': 'L', 'business_bag_id': 'reuse2', 'generation': 8, 'traversal_id': 9,
        'node': 7, 'mode': 'loaded', 'edge_to': -1}
    view = {'now': 15., 'owner_id': 'B', 'trays': [tray], 'jobs': [],
        'node_contracts': [{'node': 8, 'resource_owner': 'B', 'occupancy': int(occupied), 'capacity': 1}]}
    seed_client = native.bound.LocalTransport(RouteSession()); seed_client.activate('B', {'kind': 'current_fixture'})
    def make():
        policy = object.__new__(native.OwnerPolicy)
        policy.client = copy.deepcopy(seed_client); policy.session = policy.client.session
        policy.owner, policy.episode, policy.mode, policy.resident = 'B', 'fixture', 'guarded', None
        policy._in_new_collection = True
        policy.ledger = SimpleNamespace(audit_copy=lambda: {'fixture': 'unchanged retained contracts'})
        policy.repeated_decisions, policy.choices, policy.route_keys = [{'earlier': 'retained'}], [], set()
        return policy
    before, after = make(), make()
    causal = {'relation': 'current_guarded_result', 'predecessor_protocol_id': 'actual_collection'}
    old_count = len(before.repeated_decisions)
    identities, failures = [], []
    for policy, dispatch in ((before, before.route_tray), (after, after._dispatch_current_route)):
        try:
            identities.append(dispatch(view, tray, next_node, causal)); failures.append(None)
        except RuntimeError as error:
            identities.append(None); failures.append(str(error))
    del before.repeated_decisions[old_count:]
    def encoded(policy):
        return json.dumps({'calls': policy.client.calls, 'outbox': policy.client.rows,
            'request_creations': policy.client.creations, 'roots': policy.client.roots,
            'ack_handling': policy.client.ack_handling, 'choices': policy.choices,
            'route_keys': sorted(policy.route_keys), 'retained_decisions': policy.repeated_decisions},
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    assert identities[0] == identities[1] and failures[0] == failures[1]
    assert encoded(before) == encoded(after)
    assert type(after.client) is native.historical.fixture.LocalTransport


def test_private_current_dispatch_cannot_be_used_outside_a_current_decision():
    policy = object.__new__(native.OwnerPolicy); policy._in_new_collection = False
    with pytest.raises(ValueError, match='dispatch_only_inside_current_decision'):
        policy._dispatch_current_route({}, {}, 8, {})
