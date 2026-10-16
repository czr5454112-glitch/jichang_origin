"""Binding/source checks with original Python provider; no extension loaded."""
import copy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import complete_root_evidence_c_normalizer as c
from scripts.experiments.g31_ics_circulation import root_evidence_mock as mock
from scripts.experiments.g31_ics_circulation import single_root_evidence as single
from test_g31_circulation_complete_root_evidence_codec_campaign import fixture_record


def sample(binding, fixture):
    clock = SimpleNamespace(perf_counter_ns=lambda: 300)
    method = mock.clone(binding.EVIDENCE, time=clock,
        root_runtime_proof=lambda root: fixture['value']['evidence']['runtime_query_proof'])
    finish = mock.clone(binding.finish_root, time=clock, evidence=method)
    publish = mock.clone(binding.publish_root, time=clock, finish_root=finish)
    root = mock.root_from_evidence(fixture['value']['evidence'], method)
    holder = []
    result = publish(root, holder)
    assert len(holder) == 1 and holder[0] is result
    return result


def test_same_code_full_namespace_and_original_provider_binding():
    original = c.frozen
    bound = c._bind_provider(c.provider.original.normalize)
    for old, new, name in ((original.EVIDENCE, bound.EVIDENCE, 'normalization'),
            (original.finish_root, bound.finish_root, 'evidence'),
            (original.publish_root, bound.publish_root, 'finish_root')):
        assert old.__code__ is new.__code__ and old.__closure__ is new.__closure__
        assert set(old.__globals__) == set(new.__globals__)
        assert {k for k in old.__globals__ if old.__globals__[k] is not new.__globals__[k]} == {name}
    assert bound.EVIDENCE.__globals__['_codec_check'] is original.EVIDENCE.__globals__['_codec_check']
    assert bound.EVIDENCE.__globals__['root_runtime_proof'] is original.EVIDENCE.__globals__['root_runtime_proof']


def test_complete_record_unchanged_with_one_provider_call_and_isolated_result():
    fixture = fixture_record()
    before = copy.deepcopy(fixture)
    calls = []
    def normalize(value):
        calls.append(list(value))
        return c.provider.original.normalize(value)
    result = sample(c._bind_provider(normalize), fixture)
    expected = sample(c.frozen, fixture)
    assert len(calls) == 1 and calls[0][-1] == 'runtime_query_proof'
    assert single.exact_tree(result, expected)
    assert single.exact_tree(mock.semantic_record(result), mock.semantic_record(fixture))
    result['value']['evidence']['runtime_query_proof']['outbox'].clear()
    assert expected['value']['evidence']['runtime_query_proof']['outbox']
    assert single.exact_tree(fixture, before)


def test_provider_error_is_not_caught_or_replaced():
    failure = ValueError('provider rejected')
    def normalize(value):
        raise failure
    with pytest.raises(ValueError) as caught:
        sample(c._bind_provider(normalize), fixture_record())
    assert caught.value is failure


def test_original_strict_encoder_still_rejects_nonfinite_provider_output():
    def normalize(value):
        value = c.provider.original.normalize(value)
        value['bad'] = float('nan')
        return value
    with pytest.raises(ValueError):
        sample(c._bind_provider(normalize), fixture_record())


@pytest.mark.parametrize('candidate', [None, object(), SimpleNamespace(normalize=lambda x: x)])
def test_public_C_binding_rejects_nonverified_providers(candidate):
    with pytest.raises(ValueError, match='verified_candidate_required'):
        c.bind(candidate)


def test_reference_is_explicitly_historical_and_no_performance_claim():
    proof = c.source_proof()
    assert proof['reference_normalization_unchanged_claim_is_historical_only']
    assert proof['original_fallback_retained'] and proof['direct_C_support_required_separately_for_fixed_inputs']
    assert not proof['performance_or_100ms_claim'] and not proof['new_campaign_or_native_authority']
