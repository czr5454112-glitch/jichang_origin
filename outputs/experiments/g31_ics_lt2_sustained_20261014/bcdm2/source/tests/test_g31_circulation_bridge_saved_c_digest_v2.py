"""Synthetic routing only: no C load, native, model or actual saved-stream read.

The bare fixture helper below must be an explicit source-closure entry in any
future pure/prepare package. Its fabricated envelopes are not native evidence.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import bridge_saved_c_digest as c
from test_g31_circulation_bridge_replay_copy_scopes import (
    public_fixture, owner, call_values, mutable_ids, exact,
)


class DigestSpy:
    def __init__(self):
        self.bodies = []

    def __call__(self, body):
        self.bodies.append(body)
        return c.base.capture_digest_v2(body)


def fixture():
    view, box, peer, plan = public_fixture()
    nodes = {n['node']: n for n in view['node_contracts']}
    return view, box, peer, plan, nodes


def outcome(function, *args):
    try:
        return ('returned', exact(function(*args)))
    except (ValueError, KeyError, TypeError) as error:
        return ('rejected', type(error), error.args)


def private_owner(bundle, *args, **kwargs):
    value = owner(bundle.BridgeOwner, *args, **kwargs)
    value.possession = bundle.Gate(value.owner, value.plan, ['pa', 'pb'])
    return value


def cap_fixture():
    """Routing fixture only; not a real cap or all-day completion certificate."""
    view, box, peer, parking, nodes = fixture()
    box['snap']['payload'].update(kind='planning_snapshot_v2', expiry=100.)
    ids = ['pa', 'pb', 'a1'] + ['synthetic-' + str(i) for i in range(77)]
    proof = dict(received_action_ids=ids, token_completed_job_ids=[],
        postparking_empty_operations=78, own_captured_at=9., peer_captured_at=9., observed_at=9.)
    summary = dict(owner='A', cap_observed=True, failure=None, outbox={'outbox': box},
        cap_relay=dict(publication_enqueued=True, source_owner='A', target_owner='B',
            request_id='snap', at=9., proof=proof))
    plan = dict(parking_plan=parking, public_contract={'node_contracts': view['node_contracts']})
    raw = dict(owners=[summary], status='horizon_complete', physical_time=c.policy.HORIZON,
        result={'receipts': [], 'advance': {'horizon_complete': True}})
    return summary, plan, raw


def test_complete_code_globals_defaults_cells_mro_and_original_identity():
    bundle = c._bundle(DigestSpy())
    proof = bundle.prove()
    assert len(proof['clones']) == 9
    assert all(p['original_code_defaults_kwdefaults_cells']
               and p['full_global_domain_preserved'] for p in proof['clones'])
    assert bundle.BridgeOwner.activate.__closure__ is c.policy.BridgeOwner.activate.__closure__
    assert bundle.BridgeOwner.__init__.__closure__ is c.policy.BridgeOwner.__init__.__closure__
    assert bundle.BaseOwner.activate.__globals__['delivered_peer'] is bundle.validator
    assert bundle.Gate.consume.__globals__['reuse'] is bundle.reuse
    assert bundle.Gate.consume.__globals__['base'] is bundle.base
    assert bundle.reuse.latest_own_capture.__globals__['base'] is bundle.base
    assert c.base.Owner.activate.__globals__['delivered_peer'] is c.base.delivered_peer
    assert c.possession.PossessionGate.consume.__globals__['reuse'] is c.reuse
    assert not proof['resource_exception_equivalence']


def test_real_constructor_original_super_initialization_and_private_gate():
    bundle = c._bundle(DigestSpy())
    _, _, _, parking, _ = fixture()
    session = SimpleNamespace(physical_time=0.)
    value = bundle.BridgeOwner(session, 'A', parking)
    assert type(value.possession) is bundle.Gate
    assert value.client.session is session and value.session is session
    assert value.rows == [parking['parking'][0]] and value.peer == 'B'
    assert value.index == 0 and not value.quiet and value.failure is None
    assert super(c.policy.BridgeOwner, value).activate.__func__ is bundle.BaseOwner.activate
    assert super(c.policy.BridgeOwner, value).__init__.__func__ is c.base.Owner.__init__


def test_fresh_trial_guard_kept_before_any_session_query():
    bundle = c._bundle(DigestSpy())
    _, _, _, parking, _ = fixture()
    with pytest.raises(ValueError, match='fresh_trial_only'):
        bundle.BridgeOwner(SimpleNamespace(physical_time=1.), 'A', parking)


def test_startup_base_activation_routes_original_peer_validator():
    view, box, peer, plan, _ = fixture()
    spy = DigestSpy(); bundle = c._bundle(spy)
    old = owner(c.base.Owner, *deepcopy((view, box, peer, plan)))
    new = owner(bundle.BaseOwner, *deepcopy((view, box, peer, plan)))
    for value in (old, new):
        value.quiet = False
        value.failure = {'reason': 'synthetic_stop_after_original_peer_guard'}
    old.activate(); new.activate()
    assert len(spy.bodies) == 1
    assert old.session.calls == new.session.calls
    assert exact(old.client.state) == exact(new.client.state)
    assert call_values(old.client.calls) == call_values(new.client.calls)


@pytest.mark.parametrize('defect', ['none', 'owner', 'digest', 'expired', 'future_ack', 'coverage'])
def test_own_selector_guards_exact_and_return_copy_isolation(defect):
    view, box, peer, plan, nodes = fixture()
    row = box['snap']; ack = row['client_view']['last_delivered_ack']
    env = ack['planning_snapshot_v2']; local = env['capture']['local_capture']
    if defect == 'owner': row['payload']['owner_id'] = 'B'
    elif defect == 'digest': env['payload_sha256'] = '0' * 64
    elif defect == 'expired':
        local['valid_until'] = 10.; env['payload_sha256'] = c.base.capture_digest_v2(env['capture'])
    elif defect == 'future_ack': ack['delivered_at'] = 11.
    elif defect == 'coverage':
        local['coverage']['local_node_ids'].pop()
        env['payload_sha256'] = c.base.capture_digest_v2(env['capture'])
    before = exact((view, box, peer, plan)); spy = DigestSpy(); bundle = c._bundle(spy)
    args = (box, 'A', 'B', 10., nodes)
    assert outcome(c.reuse.latest_own_capture, *args) == outcome(bundle.reuse.latest_own_capture, *args)
    assert exact((view, box, peer, plan)) == before
    if defect == 'none':
        result = bundle.reuse.latest_own_capture(*args)
        assert len(spy.bodies) == 2
        assert not mutable_ids(result) & mutable_ids(box)
        saved = exact(result); local['jobs'].clear()
        assert exact(result) == saved


def test_no_capture_cache_and_original_digest_before_expiry():
    _, _, peer, _, nodes = fixture()
    local = peer['capture']['local_capture']; local['valid_until'] = 10.
    peer['payload_sha256'] = c.base.capture_digest_v2(peer['capture'])
    spy = DigestSpy(); bundle = c._bundle(spy)
    assert bundle.validator([peer], 'A', 'B', 10., nodes) is None
    assert len(spy.bodies) == 1
    peer['payload_sha256'] = 'broken'
    with pytest.raises(ValueError, match='message_digest'):
        bundle.validator([peer], 'A', 'B', 10., nodes)
    assert len(spy.bodies) == 2


def test_empty_and_pre_digest_rejections_do_not_manufacture_digest_calls():
    _, _, peer, _, nodes = fixture(); spy = DigestSpy(); bundle = c._bundle(spy)
    assert bundle.validator([], 'A', 'B', 10., nodes) is None
    with pytest.raises(ValueError, match='duplicate_peer_envelope'):
        bundle.validator([peer, peer], 'A', 'B', 10., nodes)
    with pytest.raises(ValueError, match='message_owner'):
        bundle.validator([peer], 'B', 'A', 10., nodes)
    assert spy.bodies == []


@pytest.mark.parametrize('error', [MemoryError('synthetic_resource'), KeyboardInterrupt('synthetic_interrupt')])
def test_resource_or_interrupt_propagates_once_without_retry(error):
    _, _, peer, _, nodes = fixture(); calls = []
    def fail(body):
        calls.append(body); raise error
    bundle = c._bundle(fail)
    with pytest.raises(type(error)) as seen:
        bundle.validator([peer], 'A', 'B', 10., nodes)
    assert seen.value is error and len(calls) == 1


def test_possession_gate_uses_both_private_paths_and_original_consumption_and_copies():
    view, box, peer, plan, _ = fixture(); spy = DigestSpy(); bundle = c._bundle(spy)
    original = c.possession.PossessionGate('A', plan, ['pa', 'pb'])
    private = bundle.Gate('A', plan, ['pa', 'pb'])
    old = original.consume(view, box, [peer]); new = private.consume(view, box, [peer])
    assert old is not None and exact(new) == exact(old)
    assert len(spy.bodies) == 2 and private.checkpoint() == original.checkpoint()
    assert not mutable_ids(new) & mutable_ids((view, box, peer, plan))
    assert private.consume(view, box, [peer]) is None
    assert len(spy.bodies) == 4  # All guards still execute even for consumed watermark.


@pytest.mark.parametrize('mode', ['direct', 'bridge', 'notempty', 'halt', 'cap'])
def test_full_bridge_activation_state_and_api_order_equal(mode):
    view, box, peer, plan, _ = fixture()
    if mode == 'bridge':
        peer['capture']['local_capture']['jobs'] = []
        peer['capture']['local_capture']['coverage']['business_bag_ids'] = []
        peer['payload_sha256'] = c.base.capture_digest_v2(peer['capture'])
    if mode == 'notempty': view['trays'][0]['mode'] = 'loaded'
    spy = DigestSpy(); bundle = c._bundle(spy)
    old = owner(c.policy.BridgeOwner, *deepcopy((view, box, peer, plan)), halt=mode == 'halt')
    new = private_owner(bundle, *deepcopy((view, box, peer, plan)), halt=mode == 'halt')
    if mode == 'cap': old.cap_observed = new.cap_observed = True
    old.activate(); new.activate()
    assert exact(old.controller_checkpoint()) == exact(new.controller_checkpoint())
    assert exact(old.last_barrier) == exact(new.last_barrier) and exact(old.decisions) == exact(new.decisions)
    assert old.session.calls == new.session.calls
    assert call_values(old.client.calls) == call_values(new.client.calls)
    assert not mutable_ids((new.decisions, new.operations, new.last_barrier)) & mutable_ids(new.client.state)
    assert len(spy.bodies) == {'direct': 4, 'bridge': 4, 'notempty': 2, 'halt': 0, 'cap': 0}[mode]


def test_actual_cap_relay_helper_retains_unknown_scope_and_routes_digest():
    summary, plan, _ = cap_fixture(); spy = DigestSpy(); bundle = c._bundle(spy)
    args = (summary, plan['parking_plan'], plan['public_contract'])
    old = c.policy.cap_relay_evidence(*args); new = bundle.policy.cap_relay_evidence(*args)
    assert new == old and new['status'] == 'historical_delivered_cap_relay'
    assert not new['new_actions_authorized'] and not new['full_policy_replay_verified']
    assert len(spy.bodies) == 1
    summary['outbox']['outbox']['snap']['client_view']['last_delivered_ack']['planning_snapshot_v2']['payload_sha256'] = 'bad'
    assert bundle.policy.cap_relay_evidence(*args) == c.policy.cap_relay_evidence(*args)
    assert bundle.policy.cap_relay_evidence(*args)['status'] == 'unknown_cap_relay'


def test_both_assess_layers_resolve_same_fresh_factory_namespace():
    _, plan, raw = cap_fixture(); spy = DigestSpy(); bundle = c._bundle(spy)
    namespace = bundle.runner_namespace()
    assert namespace['assess'].__globals__ is namespace
    assert namespace['isolated_base'].__globals__ is namespace
    private = namespace['isolated_base']()
    assert private.assess is namespace['assess']
    assert private.verify_saved.__globals__['assess'] is namespace['assess']
    assert private.run_policy is bundle.policy.run_policy
    old = c.r.runner_namespace()['assess'](raw, plan)
    assert exact(namespace['assess'](raw, plan)) == exact(old)
    assert exact(private.assess(raw, plan)) == exact(old)
    assert len(spy.bodies) == 2
    assert old['all_physical_received'] is False  # The small fixture is not a 22-tray certificate.


def test_runner_factory_is_fresh_and_retains_all_original_function_globals():
    bundle = c._bundle(DigestSpy()); before = dict(vars(c.r.original))
    a, b = bundle.runner_namespace(), bundle.runner_namespace()
    assert a is not b and a['assess'] is not b['assess']
    assert a['policy'] is b['policy'] is bundle.policy
    assert a['assess'].__globals__ is a and b['assess'].__globals__ is b
    assert set(a) == set(c.r.runner_namespace())
    assert a['assess'].__code__ is c.r.original.assess.__code__
    a['synthetic_private_marker'] = object()
    assert 'synthetic_private_marker' not in b
    assert set(vars(c.r.original)) == set(before)
    assert all(vars(c.r.original)[k] is value for k, value in before.items())


class StopBeforeReplay(Exception):
    pass


def observed_factory(tmp_path, bundle):
    """Execute ORIGINAL full.verify_case through its real local class factory.

    Only archive readers/pins and the nested verify_saved entry are mocked.
    No replacement ObservedOwner is fabricated, and no physical/replay
    acceptance is returned. Execution stops before any saved policy replay.
    """
    old = tmp_path / 'old'; (old / 'api').mkdir(parents=True)
    (old / 'api' / 'manifest.jsonl').write_text('', encoding='utf-8')
    new = tmp_path / 'new'
    plan = {'bootstrap_reference': str(old)}
    raw = {'owners': []}; data = {}; oldraw = {'owners': [{'supply': {'at': 0.}}]}
    reads = {new / 'raw_final.json.gz': raw, new / 'input.json.gz': data,
             old / 'raw_final.json.gz': oldraw}
    fake_base = SimpleNamespace(**{**vars(c.full.base), 'read': lambda path: plan,
                                  'gzread': lambda path: reads[path]})
    namespace = bundle.runner_namespace(); actual_factory = namespace['isolated_base']; captured = {}
    def intercepted_factory(**overrides):
        private = actual_factory(**overrides)
        captured.update(overrides=overrides, private=private, runner_namespace=namespace)
        def stop(directory):
            assert directory == new
            raise StopBeforeReplay('synthetic_stop_before_saved_policy')
        return SimpleNamespace(verify_saved=stop)
    namespace['isolated_base'] = intercepted_factory
    namespace['verify_pins'] = lambda *args, **kwargs: None
    runner = SimpleNamespace(**namespace)
    checker = c.clone(bundle.checker, {**bundle.checker.__globals__, 'base': fake_base, 'r': runner})
    assert checker.__code__ is c.full.verify_case.__code__
    with pytest.raises(StopBeforeReplay, match='synthetic_stop'):
        checker(new)
    return captured


def test_original_checker_creates_real_observed_owner_and_actual_inner_assess(tmp_path):
    spy = DigestSpy(); bundle = c._bundle(spy)
    captured = observed_factory(tmp_path, bundle)
    replay = captured['overrides']['run_policy']
    observed = replay.__globals__['BridgeOwner']
    assert replay.__code__ is c.policy.run_policy.__code__
    assert observed.__bases__ == (bundle.BridgeOwner,)
    assert observed.__init__ is bundle.BridgeOwner.__init__
    assert observed.__qualname__.endswith('verify_case.<locals>.ObservedOwner')
    private = captured['private']; namespace = captured['runner_namespace']
    assert private.assess is namespace['assess']
    assert private.verify_saved.__globals__['assess'] is namespace['assess']
    assert namespace['assess'].__globals__['policy'] is bundle.policy
    view, box, peer, plan, _ = fixture()
    value = owner(observed, view, box, peer, plan)
    value.possession = bundle.Gate('A', plan, ['pa', 'pb']); value.session.index = 0
    value.activate()
    cells = dict(zip(observed.activate.__code__.co_freevars, observed.activate.__closure__))
    assert cells['owner_calls'].cell_contents == [
        {'owner': 'A', 'logical_time': 10., 'first_api': 0, 'after_api': 0}]
    assert len(spy.bodies) == 4 and len(value.operations) == 1


def test_real_observed_owner_finally_retains_failed_call_and_no_retry(tmp_path):
    failure = MemoryError('synthetic_resource'); calls = []
    def digest(body):
        calls.append(body); raise failure
    bundle = c._bundle(digest); captured = observed_factory(tmp_path, bundle)
    observed = captured['overrides']['run_policy'].__globals__['BridgeOwner']
    view, box, peer, plan, _ = fixture(); value = owner(observed, view, box, peer, plan)
    value.possession = bundle.Gate('A', plan, ['pa', 'pb']); value.session.index = 0
    with pytest.raises(MemoryError) as seen: value.activate()
    assert seen.value is failure and len(calls) == 1 and value.operations == []
    cells = dict(zip(observed.activate.__code__.co_freevars, observed.activate.__closure__))
    assert len(cells['owner_calls'].cell_contents) == 1


def test_outer_binder_keeps_exact_previous_code_and_only_two_policy_roots():
    bundle = c._bundle(DigestSpy())
    previous = c.previous.binder_function(); candidate = c.binder_function(bundle)
    proof = c.clone_proof(previous, candidate, {'r': bundle.runner, 'full': bundle.full})
    assert proof['replaced_globals'] == ['full', 'r']
    assert candidate.__globals__['replay_type'] is c.previous.replay_type
    assert candidate.__globals__['semantic_equal'] is previous.__globals__['semantic_equal']
    assert candidate.__globals__['SharedReads'] is previous.__globals__['SharedReads']
    assert candidate.__globals__['observer_result'] is previous.__globals__['observer_result']


@pytest.mark.parametrize('target', ['base_helper', 'selector', 'policy', 'runner', 'checker', 'gate'])
def test_private_drift_rejected_without_modifying_original(target):
    bundle = c._bundle(DigestSpy()); original = c.base.delivered_peer
    if target == 'base_helper': bundle.base.eligible_head = lambda *args: None
    elif target == 'selector': bundle.reuse.latest_own_capture = c.reuse.latest_own_capture
    elif target == 'policy': bundle.policy.cap_relay_evidence = c.policy.cap_relay_evidence
    elif target == 'runner': bundle.runner.runner_namespace = c.r.runner_namespace
    elif target == 'checker': bundle.full.verify_case = c.full.verify_case
    elif target == 'gate': bundle.Gate.consume = c.possession.PossessionGate.consume
    with pytest.raises(ValueError, match='C_digest_'): bundle.prove()
    assert c.base.delivered_peer is original


def test_original_global_drift_fails_before_constructing_bundle(monkeypatch):
    monkeypatch.setattr(c.base, 'eligible_head', lambda *args: None)
    with pytest.raises(ValueError, match='C_digest_original_function_or_globals'):
        c._bundle(DigestSpy())


@pytest.mark.parametrize('attribute,value', [('__defaults__', (None,)),
                                            ('__kwdefaults__', {'synthetic': None})])
def test_original_defaults_replacement_rejected_before_private_clone(monkeypatch, attribute, value):
    monkeypatch.setattr(c.base.delivered_peer, attribute, value)
    with pytest.raises(ValueError, match='C_digest_original_function_or_globals'):
        c._bundle(DigestSpy())


def test_two_bundles_have_no_private_mutable_namespace_sharing():
    a, b = c._bundle(DigestSpy()), c._bundle(DigestSpy())
    assert a.Gate is not b.Gate and a.BridgeOwner is not b.BridgeOwner
    assert a.validator.__globals__ is not b.validator.__globals__
    assert a.base is not b.base and a.policy is not b.policy
    a.base.eligible_head = None
    with pytest.raises(ValueError): a.prove()
    b.prove()


def test_production_bind_rejects_synthetic_callable_authority():
    with pytest.raises(ValueError, match='exact_verified_candidate'):
        c.bind({}, None, None, SimpleNamespace(capture_digest_v2=DigestSpy(), _verify=lambda: None))

