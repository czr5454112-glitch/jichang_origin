"""Focused new wiring/namespace regressions, no native or model execution."""
from copy import deepcopy
from types import FunctionType, SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_entry_codec_campaign as c
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_entry_codec_campaign as v
from scripts.experiments.g31_ics_circulation import initial_owner_route_entry_codec_integration as i
from test_g31_circulation_initial_owner_route_entry_campaign import synthetic_root


def test_scope_same18_faults_inputs_finite2_budget_and_scheduler():
    proof = c.source_proof()
    assert proof['original_worker_inverse_AST_exact'] and proof['changed_import_sites'] == 1
    assert proof['same18_inputs_and_faults'] and proof['finite2_budget_100ms_unchanged']
    assert len(c.declarations()) == 18 and c.LIMIT == 600.
    assert c.scene is c.previous.scene and c.FAULTS is c.previous.FAULTS
    assert c.contract is i.entry.contract
    assert c.run_branch.__globals__['CapturedRequest'] is i.CapturedRequest
    assert c.run_branch.__globals__['FixedDefaultRequest'] is i.FixedDefaultRequest
    assert c.run_branch.__globals__['run_continuation'] is i.run_continuation
    assert c.run_branch.__globals__['_make_client'] is i.make_client
    assert c.worker.__globals__['run_branch'] is c.run_branch
    assert c.main.__globals__['worker'] is c.worker


def test_repaired_namespace_reaches_real_plan_guard_after_Path_resolution(tmp_path):
    seen = []
    def guard(path, expected):
        seen.append((path, expected))
        raise ValueError('new_plan_guard_reached')
    check = v.shared(v.verify_saved, {**v.verify_saved.__globals__, 'c': SimpleNamespace(verify_plan=guard)})
    with pytest.raises(ValueError, match='new_plan_guard_reached'):
        check(tmp_path, 'not-plan')
    assert seen == [(tmp_path.resolve(), 'not-plan')]


@pytest.mark.parametrize('name', v.NAMES)
def test_every_check_code_defaults_closure_retained_in_shared_repaired_namespace(name):
    current, original = getattr(v, name), getattr(v.previous, name)
    assert current.__code__ is original.__code__
    assert current.__defaults__ == original.__defaults__
    assert current.__kwdefaults__ == original.__kwdefaults__
    assert current.__closure__ == original.__closure__
    assert current.__globals__ is v._namespace
    assert not v.previous.missing_globals(current)
    assert original.__globals__ is not v._namespace


def test_recursive_global_inventory_detects_missing_Path_and_nested_helpers():
    broken = v.shared(v.verify_saved, {k: x for k, x in v._namespace.items() if k != 'Path'})
    assert 'Path' in v.previous.missing_globals(broken)
    def function(items):
        return [absent_helper(item) for item in items]
    assert v.previous.missing_globals(function) == ['absent_helper']
    assert all(not missing for missing in v.source_proof()['recursive_LOAD_GLOBAL_missing'].values())


def test_both_root_levels_and_all_branch_dependencies_use_new_campaign():
    assert v.verify_saved.__globals__['verify_branch'] is v.verify_branch
    assert v.verify_branch.__globals__['_original_verify_branch'] is v._original_verify_branch
    assert v._original_verify_branch.__globals__['root_replay'] is v.root_replay
    assert v.root_replay.__globals__['old'].root_replay is v._root_original
    assert v.root_replay.__globals__['c'] is c
    assert v._root_original.__globals__['c'] is c
    assert v.complete_query_replay.__globals__['integration'] is i.entry


def replay_root(raw, source, old_predicate=False):
    contract = SimpleNamespace(**vars(c.contract))
    contract.validate_final_local = lambda *args: {'status': 'fresh_local_precondition_checked', 'source': deepcopy(source)}
    if old_predicate:
        contract.observed_first_hop = i.entry.entry.old.observed_first_hop
    campaign = SimpleNamespace(**vars(c)); campaign.contract = contract
    inner = v.shared(v._root_original, {**v._root_original.__globals__, 'c': campaign})
    facade = SimpleNamespace(**vars(v.original)); facade.root_replay = inner
    outer = v.shared(v.root_replay, {**v.root_replay.__globals__, 'c': campaign, 'old': facade})
    return outer(raw)


def test_twolevel_saved_entry_replay_executes_positive_and_old_exit_predicate_rejects():
    raw, source, _ = synthetic_root()
    assert replay_root(raw, source)['closed']
    with pytest.raises(ValueError, match='physical_proof_not_observed'):
        replay_root(raw, source, True)


@pytest.mark.parametrize('mutation', ['reservation_only', 'generation', 'drain_absent', 'incomplete_drain', 'hop'])
def test_saved_physical_and_drain_negatives_still_reject(mutation):
    raw, source, rehash = synthetic_root(); evidence = raw['root_records'][0]['value']['evidence']
    if mutation == 'reservation_only': evidence['events'][2]['value']['view']['trays'][0].pop('edge_exit_at')
    elif mutation == 'generation': evidence['events'][2]['value']['view']['trays'][0]['generation'] += 1
    elif mutation == 'drain_absent': evidence['events'][3]['stage'] = 'not_drain'
    elif mutation == 'incomplete_drain': evidence['events'][3]['value']['horizon_complete'] = False
    else: evidence['hop']['to'] = 2
    rehash()
    with pytest.raises(ValueError): replay_root(raw, source)


def test_marker_is_exact_and_old_complete_query_checker_still_executes():
    from test_g31_circulation_initial_owner_route_gate_campaign_v2 import actual_client_fixture
    _, _, _, raw = actual_client_fixture()
    assert v.complete_query_replay(raw)['status'] == 'passed_complete_actual_refresh_outbox_replay'
    raw['ack_handling'].clear()
    with pytest.raises(ValueError, match='complete_actual_outbox'):
        v.complete_query_replay(raw)
    # A targeted marker check cannot grant live authority or replace above full replay.
    records = {'root_records': [{'value': {'evidence': {'runtime_query_proof': {
        'first_hop_observation_contract': deepcopy(i.entry.MARKER)}}}}]}
    marked = v.shared(v.complete_query_replay, {**v.complete_query_replay.__globals__,
        'previous': SimpleNamespace(complete_query_replay=lambda _: {'checked': True})})
    assert marked(records) == {'checked': True}
    records['root_records'][0]['value']['evidence']['runtime_query_proof']['first_hop_observation_contract']['source_prefix'] = [0, 1]
    with pytest.raises(ValueError, match='entry_observation_contract_missing_or_changed'):
        marked(records)


def test_actual_worker_import_reaches_new_saved_verifier_without_native(tmp_path, monkeypatch):
    # Execute the whole original worker setup/finally/import path using empty
    # synthetic rows and rejecting fake predictor construction. No branch or
    # native session can be entered; the sentinel is the actual new import.
    seen, writes = [], []
    class Accepted:
        _closed = False
        def close(self): return {'test_only': 'closed'}
    plan = {'rows': {}, 'row_order': [], 'native_contract_reference': {}, 'semantic_gate_reference': {},
            'image': {'path': 'unused', 'version': 'unused'}}
    def refuse_predictor(*args, **kwargs): raise ValueError('functional_stub_no_predictor')
    def checked(output, expected):
        seen.append((output, expected))
        raise ValueError('actual_new_saved_import_reached')
    monkeypatch.setattr(v, 'verify_saved', checked)
    fake_public = SimpleNamespace(run_admission=SimpleNamespace(open_run=lambda *args: Accepted()),
                                 load_native=lambda _: object())
    function = c.integrated.private(c.worker, {'verify_plan': lambda *a: plan,
        'check_loaded_sources': lambda *a: [], 'reference': lambda path: {'path': str(path)},
        'read': lambda _: {'binary': 'unused'}, 'write': lambda p, x: writes.append(p.name),
        'public': fake_public, 'InitialOwnerClient': refuse_predictor})
    with pytest.raises(ValueError, match='actual_new_saved_import_reached'):
        function(tmp_path, 'synthetic-plan')
    assert seen == [(tmp_path, 'synthetic-plan')]
    assert 'predictor_lifetime.json' in writes and 'run_acceptance.json' in writes
    assert 'verification.json' not in writes and 'receipt.json' not in writes


def test_original_frozen_bindings_unchanged_and_launcher_keeps_owned_tree():
    from scripts.experiments.g31_ics_circulation import launch_initial_owner_route_entry_codec_campaign as launch
    assert c.previous.run_branch.__globals__['CapturedRequest'] is i.entry.CapturedRequest
    assert v.previous.verify_saved.__globals__['c'] is c.previous
    assert v.previous.root_replay.__globals__['c'] is c.previous
    assert 'Path' not in v.previous.frozen.verify_saved.__globals__
    assert launch.main.__code__ is launch.old.main.__code__ and launch.LIMIT == 600.
    assert launch.main.__globals__['MODULE'].endswith('.initial_owner_route_entry_codec_campaign')
