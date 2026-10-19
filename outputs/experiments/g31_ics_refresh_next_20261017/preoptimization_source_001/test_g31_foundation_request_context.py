"""Request-local optimization parity and fail-closed checks, without native work."""
import copy
import gzip
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_later_seed as later
from scripts.experiments.g31_ics_circulation import foundation_request_context as local
from scripts.experiments.g31_ics_circulation import planning_capture_v3_contract as inflight

ROOT = Path(__file__).resolve().parents[1]
EPISODES = ROOT / 'outputs/experiments/g31_ics_learning_next_20261017'
RAW_FILES = (
    'later_episodes_001/guarded_default/episode/native/raw.json.gz',
    'later_repair_001/diagnostic_absolute_return/episode/native/raw.json.gz',
)


def test_request_module_is_imported_before_native_source_archiving():
    script = ('import sys; from pathlib import Path; '
        'from scripts.experiments.g31_ics_circulation import foundation_later_seed as model; '
        'from scripts.experiments.g31_ics_circulation import foundation_native_environment as environment; '
        'name="scripts.experiments.g31_ics_circulation.foundation_request_context"; '
        'assert name in sys.modules; '
        'assert Path(sys.modules[name].__file__).resolve() in '
        '{Path(path).resolve() for path in environment.online.old.bound.imported_sources()}')
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope='module')
def transitions():
    return [row for path in RAW_FILES for row in json.loads(
        gzip.decompress((EPISODES / path).read_bytes()))['later_transitions']]


def saved_evidence(transitions, index=1):
    return copy.deepcopy(transitions[index]['model_report']['seed']['evidence'])


def peer(evidence):
    return next(row for row in evidence['information']['raw_endpoints']['received']
        if row['capture']['capture_v2']['local_capture']['message_id'] == evidence['collection']['peer_message'])


def encoded_prediction(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


@pytest.mark.parametrize('index', range(4))
def test_complete_seed_and_predictions_equal_preoptimization_native_saved_models(transitions, index):
    expected = transitions[index]['model_report']
    evidence = saved_evidence(transitions, index)
    encoded_evidence = later.delivered.encoded(evidence)
    actual = later.evaluate(evidence, list(expected['candidate_results']))
    assert actual['status'] == expected['status'] == 'conditional_current_seed'
    assert later.delivered.encoded(actual['seed']) == later.delivered.encoded(expected['seed'])
    assert encoded_prediction(actual['candidate_results']) == encoded_prediction(expected['candidate_results'])
    assert later.delivered.encoded(evidence) == encoded_evidence
    assert actual['evaluation']['counts'] == {
        'static_catalog_builds': 1, 'static_catalog_reads': 31, 'dynamic_later_context_calls': 2}
    assert actual['evaluation']['cross_request_cache'] is False
    assert actual['evaluation']['dynamic_guards_skipped'] is False
    assert actual['evaluation']['source_pins_are_full_dependency_proof'] is False
    assert actual['evaluation']['campaign_full_source_pins_required'] is True
    assert actual['evaluation']['source_exit_pins_passed'] is True


@pytest.mark.parametrize('index', [0, 1, 3])
def test_legacy_rebuild_and_two_predicts_remain_independent_reference(transitions, index, monkeypatch):
    evidence = saved_evidence(transitions, index)
    original = later.build_seed
    calls = []
    def counted(source):
        calls.append(source)
        return original(source)
    monkeypatch.setattr(later, 'build_seed', counted)
    seed = later.build_seed(evidence)
    actions = later.ACTIONS[seed['phase']]
    predicted = {action: later.predict(seed, action) for action in actions}
    assert len(calls) == 3
    expected = transitions[index]['model_report']
    assert encoded_prediction(predicted) == encoded_prediction(expected['candidate_results'])


def test_private_graph_rebinds_aliases_and_nested_namespaces_without_global_mutation():
    modules = (local.public_live_obligation_projection, local.live_obligation_domain_guard,
        local.live_obligation_lifecycle_state_v2, local.domain_guard_v2,
        local.domain_guard_historical_service, local.live_obligation_historical_service,
        local.live_obligation_delivered_context)
    before = {module: dict(vars(module)) for module in modules}
    registered = dict(sys.modules)
    request = local.RequestContext()
    assert request.lifecycle.identify_public_case is request.guard.identify_public_case
    assert request.lifecycle.public_input is request.guard.public_input
    assert request.lifecycle.construction is request.projection
    assert request.domain.validate_collected_endpoints.__globals__ is request.domain._private
    assert request.domain._private['validate_later_pair'] is request.domain.validate_later_pair
    assert request.domain._private['later_bundle'] is request.lifecycle.later_bundle
    assert request.historical.old.old is request.guard
    assert request.historical.history.base is request.guard
    assert request.delivered.later is request.historical
    assert request.delivered.revalidate.__globals__['later_context'] is request.delivered.later_context
    for module, namespace in before.items():
        assert vars(module).keys() == namespace.keys()
        assert all(vars(module)[name] is value for name, value in namespace.items())
    assert set(sys.modules) == set(registered)
    assert all(sys.modules[name] is module for name, module in registered.items())
    request.close()


def test_static_catalog_is_once_per_request_and_every_read_is_isolated(monkeypatch):
    calls = []
    checks = []
    original = local.public_live_obligation_projection.inputs
    source_check = local.public_live_obligation_event_projection_v2.check_sources
    def counted_inputs():
        calls.append(True)
        return original()
    def counted_check():
        checks.append(True)
        source_check()
    monkeypatch.setattr(local.public_live_obligation_projection, 'inputs', counted_inputs)
    monkeypatch.setattr(local.public_live_obligation_event_projection_v2, 'check_sources', counted_check)
    first = local.RequestContext()
    source = first.projection.inputs()
    expected = copy.deepcopy(source)
    source['mechanism']['jobs'][0]['arrival'] = 999.
    assert first.projection.inputs() == expected
    second = local.RequestContext()
    assert second.projection.inputs() == expected
    assert len(calls) == len(checks) == 2
    assert first.close()['counts']['static_catalog_reads'] == 2
    assert second.close()['counts']['static_catalog_reads'] == 1


@pytest.mark.parametrize('change', ['missing_entry', 'entry_generation', 'expired', 'undelivered',
    'wrong_status', 'peer_owner', 'receiving', 'own_generation', 'own_owner', 'pending', 'calls'])
def test_every_changed_dynamic_fact_matches_legacy_unknown(transitions, change):
    evidence = saved_evidence(transitions)
    envelope = peer(evidence)
    body = envelope['capture']
    capture = body['capture_v2']['local_capture']
    view = evidence['information']['raw_endpoints']['view']
    if change == 'missing_entry':
        body['extension']['source_observed_inflight'] = []
    elif change == 'entry_generation':
        body['extension']['source_observed_inflight'][0]['generation'] += 1
    elif change == 'expired':
        capture['valid_until'] = evidence['at']
    elif change == 'undelivered':
        envelope['delivered_at'] = evidence['at'] + .01
    elif change == 'wrong_status':
        envelope['status'] = 'failed'
    elif change == 'peer_owner':
        capture['source_owner'] = 'B'
    elif change == 'receiving':
        capture['trays'][0]['reception_node'] = 3
    elif change == 'own_generation':
        view['trays'][0]['generation'] += 1
    elif change == 'own_owner':
        view['owner_id'] = 'A'
    elif change == 'pending':
        view['client_requests'][0]['last_delivered_ack'] = None
    elif change == 'calls':
        del evidence['own_calls'][next(index for index, row in enumerate(evidence['own_calls'])
            if row['kind'] == 'transfer')]
    envelope['payload_sha256'] = inflight.capture_digest_v3(body)
    expected = later.build_seed(evidence)
    actual = later.evaluate(evidence, ['native_default', 'prefer_8'])
    assert actual['status'] == expected['status'] == 'unknown'
    assert actual['candidate_results'] == {}
    assert later.delivered.encoded(actual['seed']) == later.delivered.encoded(expected)


@pytest.mark.parametrize('actions', [[], ['native_default', 'native_default'], ['bad'],
    ['native_default', 'prefer_8', 'bad'], [None], {'native_default': True}])
def test_actions_are_explicit_bounded_and_never_silently_fallback(transitions, actions):
    assert later.evaluate(saved_evidence(transitions), actions)['status'] == 'unknown'


def test_external_seed_dictionary_cannot_bypass_fresh_evidence_validation(transitions):
    seed = copy.deepcopy(transitions[1]['model_report']['seed'])
    result = later.evaluate(seed, ['native_default'])
    assert result['status'] == 'unknown'
    assert result['candidate_results'] == {}


def test_mutation_between_candidates_invalidates_whole_request(transitions, monkeypatch):
    class MutatingProjection(later.Projection):
        def run(self):
            result = super().run()
            self.seed['at'] += .01
            return result
    monkeypatch.setattr(later, 'Projection', MutatingProjection)
    result = later.evaluate(saved_evidence(transitions), ['native_default', 'prefer_8'])
    assert result['status'] == 'unknown'
    assert result['candidate_results'] == {}
    assert 'request_local_seed_changed' in str(result['seed']['reasons'])


def test_source_pins_cover_static_generation_and_seed_factory(transitions):
    result = later.evaluate(saved_evidence(transitions), ['native_default'])
    paths = result['evaluation']['source_sha256']
    assert {Path(path).name for path in paths} >= {
        'foundation_later_seed.py', 'foundation_request_context.py', 'public_live_obligation_interval.py',
        'research_preexisting_occupancy_domain.py', 'research_rolling_overlap_domain.py',
        'research_synthetic_reuse_chain.py', 'native_host.py', 'run_g4irsf28_service_potential.py'}
    assert all(local.path_sha(path) == expected for path, expected in paths.items())


def test_changed_pinned_bytes_fail_closed(monkeypatch):
    request = local.RequestContext()
    monkeypatch.setattr(local, 'path_sha', lambda path: '0' * 64)
    with pytest.raises(ValueError, match='request_source_bytes_changed'):
        request.close()


@pytest.mark.parametrize('location', ['source_check', 'read_pins', 'exit'])
def test_filesystem_failures_are_unknown_not_unhandled(transitions, monkeypatch, location):
    def fail(*args, **kwargs):
        raise OSError('unit_source_unavailable')
    if location == 'source_check':
        monkeypatch.setattr(local.public_live_obligation_event_projection_v2, 'check_sources', fail)
    elif location == 'read_pins':
        monkeypatch.setattr(local, 'path_sha', fail)
    else:
        monkeypatch.setattr(local.RequestContext, 'close', fail)
    result = later.evaluate(saved_evidence(transitions), ['native_default', 'prefer_8'])
    assert result['status'] == 'unknown'
    assert result['candidate_results'] == {}
    if location == 'exit':
        assert result['evaluation']['source_exit_pins_passed'] is False
