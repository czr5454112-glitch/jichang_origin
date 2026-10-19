import copy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import foundation_initial_selector as subject
from scripts.experiments.g31_ics_circulation import live_obligation_online_initial_dispatch as dispatch


def report(owner='B'):
    actions = subject.provider.teacher.future.core.lazy.original.physics.previous.actions()
    rows = [{'candidate_index': i, 'action': copy.deepcopy(action), 'status': 'not_requested',
             'completion': None} for i, action in enumerate(actions)]
    for i in (4, 12):
        rows[i].update(status='conditional_forecast',
            completion={job: 10. if i == 4 else 9. for job in subject.provider.teacher.JOBS})
    scores = [None] * 32
    scores[4], scores[12] = 3., 2.
    return {'owner': owner, 'status': 'conditional_forecasts_complete', 'requested_indices': [4, 12],
        'rows': rows, 'scores': scores, 'public_compatibility_filter': {'enabled': True}}


def test_model_controls_choice_among_protected_rows_not_mpc_objective():
    evidence = report()
    proposal = subject.select_report(evidence, mode='learned', model_version='frozen')
    assert proposal['selected_index'] == 4  # 12 has lower forecast cost, but a lower learned score.
    assert proposal['protected_compatible_indices'] == [4, 12]
    assert proposal['allowed_candidate_indices'] == [4]
    assert subject.provider.compatibility.select_component(proposal, 'B', 4)['selected_index'] == 4
    evidence['scores'][12] = 4.
    proposal = subject.select_report(evidence, mode='learned', model_version='frozen')
    assert proposal['selected_index'] == 12
    assert subject.provider.compatibility.select_component(proposal, 'B', 4)['selected_index'] == 12


@pytest.mark.parametrize('reason', ['worse_job', 'unqueried', 'unknown', 'failed_source'])
def test_high_score_never_overrides_original_per_job_or_query_guard(reason):
    evidence = report()
    evidence['scores'][12] = 100.
    if reason == 'worse_job':
        evidence['rows'][12]['completion']['loaded'] = 11.
    elif reason == 'unqueried':
        evidence['requested_indices'] = [4]
    elif reason == 'unknown':
        evidence['rows'][12]['status'] = 'unknown_projection'
    else:
        evidence['status'] = 'unknown_origin_or_provider'
    proposal = subject.select_report(evidence, mode='learned', model_version='frozen')
    assert proposal['selected_index'] == (None if reason == 'failed_source' else 4)
    assert proposal['native_authority'] is False


def test_owner_A_and_fixed_proposals_remain_explicit():
    assert subject.select_report(report('A'), mode='learned', model_version='frozen')['selected_index'] == 4
    assert subject.select_report(report(), mode='fixed12', model_version=None)['selected_index'] == 12
    assert subject.select_report(report(), mode='incumbent', model_version=None)['selected_index'] == 4


def test_unloaded_and_wrong_feature_models_rejected(monkeypatch):
    monkeypatch.setattr(subject.ranker, '_MODELS', {})
    with pytest.raises(ValueError, match='loaded_frozen'):
        subject.make_selector('learned', 'missing')
    subject.ranker._MODELS['wrong'] = {'feature_schema': 'later', 'feature_names': [], 'native_execution_authority': False}
    with pytest.raises(ValueError, match='43_feature'):
        subject.make_selector('learned', 'wrong')


def test_dispatch_keeps_current_recheck_after_explicit_selector(monkeypatch):
    events = []
    evidence = report('A')
    proposal = subject.select_report(evidence, mode='incumbent', model_version=None)
    class Decision:
        _digest, _at, _ledger = 'own-current', .11, object()
        def audit_copy(self):
            return {'owner': 'A', 'public_sha256': self._digest, 'at': self._at}
    decision = Decision()
    session = SimpleNamespace(physical_time=.11, offline_state_sha256=lambda: 'unchanged')
    client = SimpleNamespace(context={'root_id': 'own'}, rows={}, creations={'publication': {'creating_root': 'pub'}})
    def current(actual):
        assert actual is decision
        events.append('current')
    def revalidate(actual, action):
        events.append('recollect')
        assert actual is decision and action == evidence['rows'][4]['action']
        return {'status': 'fresh_local_component_proposal', 'owner': 'A', 'public_sha256': 'own-current', 'at': .11,
            'component': {'kind': 'no_command_native_default', 'actual_next_unknown': True}}
    monkeypatch.setattr(dispatch, 'origin', SimpleNamespace(InitialDecision=Decision,
        collect_initial_decision=lambda *args: decision, require_current=current, revalidate_first_component=revalidate))
    monkeypatch.setattr(dispatch, 'search', SimpleNamespace(propose_initial=lambda *a, **k: pytest.fail('full32 not requested')))
    def choose(actual):
        assert actual is decision
        events.append('selector')
        return proposal
    progress, ledger = dispatch.choose_and_submit(None, session, client, 'A', 'publication', None,
        arm='incumbent', incumbent_index=4, progress={}, initial_selector=choose)
    assert events == ['selector', 'current', 'recollect', 'current']
    assert progress['native_default_no_command'] and ledger is decision._ledger
    assert progress['compatibility']['selected_index'] == 4
    assert client.rows == {}

