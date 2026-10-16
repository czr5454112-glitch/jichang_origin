"""Logical-cut differential and adversarial checks; never imports native."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_g31_circulation_preference_request_context import bundle, ordered
from scripts.experiments.g31_ics_circulation import public_preference_protection_cut as cut
from scripts.experiments.g31_ics_circulation import public_native_preference_search as search

SAVED_ROWS = []
METHOD_ROWS = []

def actions(value):
    model = cut.original
    case = model.contract.infer_case(value['jobs'])
    return model.vocabulary.domain(model.contract.domain.domain(case)['public_derivation']['supply_windows'])['actions']

@pytest.mark.parametrize('index', range(6))
def test_all32_same_full_output_or_exact_actual_terminal_counterexample(index):
    value = bundle(index); domain = actions(value)
    ctx = cut.ProtectionContext(value, domain[0]); base = ctx.baseline()
    assert base['status'] == 'conditional_prediction' and set(base['completion']) == cut.original.contract.JOBS
    rejected = 0
    for action in domain:
        full = cut.original.predict(value, action); result = ctx.predict(action)
        assert full['status'] == 'conditional_prediction'
        if result['status'] == 'conditional_protection_rejected_prefix':
            rejected += 1; witness = result['witness']; job = witness['job']
            assert full['completion'][job] == witness['candidate_completed_at'] > base['completion'][job]
            assert list(witness['completed_prefix'].items()) == list(full['completion'].items())[:len(witness['completed_prefix'])]
            assert result['completion'] == {} and result['completion_sum'] is None
            assert result['full_candidate_prediction'] is False and result['suffix_status'] == 'unknown_unexecuted'
        else:
            assert ordered(result) == ordered(full)
            assert all(full['completion'][j] <= base['completion'][j] for j in base['completion'])
    counts = ctx.describe()['counts']
    assert counts['baseline_full_simulations'] == 1 and counts['candidate_queries'] == 32
    assert counts['candidate_prefix_rejections'] == rejected and counts['candidate_unknowns'] == 0

@pytest.mark.parametrize('defect', ['status','pending','resource','population','generation'])
def test_unknown_input_reference_disables_cut_and_preserves_original_unknown(defect):
    value=bundle(); action=actions(value)[0]
    if defect=='status': value['status']='unknown'
    elif defect=='pending': value['owner_pending_tray_requests']=['unresolved']
    elif defect=='resource': value['resources'][0]['occupancy']+=1
    elif defect=='population': value['jobs'].pop('receiver')
    else: value['trays']['L']['generation']=False
    ctx=cut.ProtectionContext(value,action)
    assert ctx.describe()['cut_enabled'] is False
    assert ordered(ctx.predict(action))==ordered(cut.original.predict(value,action))

@pytest.mark.parametrize('defect',['missing','nan','inf','bool','extra','wrong_phase','unsupported_window'])
def test_every_action_keeps_full_original_guard(defect):
    value=bundle(); domain=actions(value); action=deepcopy(domain[0])
    if defect=='missing': action.pop('later_action')
    elif defect=='nan': action['empty_departure']=float('nan')
    elif defect=='inf': action['return_delay']=float('inf')
    elif defect=='bool': action['return_delay']=False
    elif defect=='extra': action['extra']=0
    elif defect=='wrong_phase': action['initial_action']='forced_1'
    else: action['empty_departure']+=.001
    ctx=cut.ProtectionContext(value,domain[0])
    assert ordered(ctx.predict(action))==ordered(cut.original.predict(value,action))
    assert ctx.describe()['counts']['candidate_prefix_rejections']==0

@pytest.mark.parametrize('defect',['missing','nan','negative','bool','unknown'])
def test_incomplete_or_nonfinite_baseline_cannot_authorize_cut(defect):
    values={job:1. for job in cut.original.contract.JOBS}; prediction={'status':'conditional_prediction','completion':values}
    if defect=='missing': values.pop('loaded')
    elif defect=='nan': values['loaded']=float('nan')
    elif defect=='negative': values['loaded']=-1.
    elif defect=='bool': values['loaded']=True
    else: prediction['status']='unknown_event_budget'
    assert cut._reference_times(prediction) is None

def test_strict_nextafter_rejects_without_epsilon_and_equality_does_not():
    owner=SimpleNamespace(time=1.); ledger=cut._CompletionLedger(owner,{'loaded':1.,'receiver':1.})
    ledger['loaded']=1.
    owner.time=math.nextafter(1.,math.inf)
    with pytest.raises(cut._Rejected) as exc: ledger['receiver']=owner.time
    assert exc.value.witness['candidate_completed_at'] > 1.

@pytest.mark.parametrize('defect',['duplicate','foreign','nan','clock','bool'])
def test_malformed_completion_is_unknown_error_not_protection_rejection(defect):
    owner=SimpleNamespace(time=1.); ledger=cut._CompletionLedger(owner,{'loaded':2.})
    if defect=='duplicate': ledger['loaded']=1.
    job='other' if defect=='foreign' else 'loaded'
    value=float('nan') if defect=='nan' else .5 if defect=='clock' else True if defect=='bool' else 1.
    with pytest.raises(ValueError): ledger[job]=value

def test_inputs_baseline_and_results_cannot_mutate_context_or_other_candidates():
    value=bundle(); pristine=deepcopy(value); domain=actions(value)
    ctx=cut.ProtectionContext(value,domain[0]); expected=ctx.predict(domain[0])
    value['jobs']['loaded']['destination']=99
    ctx.baseline()['completion']['loaded']=-99
    ctx.describe()['source_proof']['future_actions']='tampered'
    first=ctx.predict(domain[0]); first['completion']['loaded']=-99
    assert ordered(ctx.predict(domain[0]))==ordered(expected)==ordered(cut.original.predict(pristine,domain[0]))
    changed=cut.ProtectionContext(value,domain[0]); assert changed.describe()['cut_enabled'] is False

def test_no_external_reference_vector_or_cross_context_result_injection():
    with pytest.raises(TypeError): cut.ProtectionContext(bundle(),actions(bundle())[0],{'loaded':0.})
    first=cut.ProtectionContext(bundle(0),actions(bundle(0))[0])
    second=cut.ProtectionContext(bundle(1),actions(bundle(1))[0])
    assert first.describe()['supplied_snapshot_sha256']!=second.describe()['supplied_snapshot_sha256']

def test_changed_proof_function_is_rejected(monkeypatch):
    monkeypatch.setattr(cut.original.Projection,'run',lambda self: {})
    with pytest.raises(ValueError,match='changed_proof_function'): cut.ProtectionContext(bundle(),actions(bundle())[0])

def test_custom_input_has_no_execution_hooks():
    class Custom(dict): pass
    with pytest.raises(TypeError): cut.ProtectionContext(Custom(bundle()),actions(bundle())[0])

def test_all_six_saved_actual_supplied_inputs_full32_no_false_rejection():
    root=Path(__file__).resolve().parents[1]
    evidence=root/'outputs/experiments/g31_ics_lt2_sustained_20261014/preference_static_context_pair_001/worker'
    path=evidence/'supplied_inputs.json'; plan=json.loads((evidence/'plan.json').read_bytes())
    assert hashlib.sha256(path.read_bytes()).hexdigest()==plan['input_sha256']
    inputs=[row for row in json.loads(path.read_bytes()) if row['owner']=='A']
    assert len(inputs)==len({row['case'] for row in inputs})==6
    for row in inputs:
        value=row['bundle']; domain=actions(value); ctx=cut.ProtectionContext(value,domain[0]); base=ctx.baseline()
        assert set(base['completion'])==cut.original.contract.JOBS
        witnesses=[]
        for action in domain:
            full=cut.original.predict(value,action); result=ctx.predict(action)
            assert full['status']=='conditional_prediction'
            if result['status']=='conditional_protection_rejected_prefix':
                witness=result['witness']; job=witness['job']
                assert full['completion'][job]==witness['candidate_completed_at']>base['completion'][job]
                witnesses.append(witness)
            else: assert ordered(full)==ordered(result)
        SAVED_ROWS.append({'case':row['case'],'counts':ctx.describe()['counts'],'witnesses':witnesses,
            'baseline':base['completion'],'all32_checked_against_original_full_prediction':True})

@pytest.mark.parametrize('index',range(6))
def test_same_four_methods_keep_query_sequence_and_selected_full_prediction(index):
    value=bundle(index); domain={key:action for key,action in zip(
        ((i,w,r,l) for i in range(2) for w in range(4) for r in range(2) for l in range(2)),actions(value))}
    base=(0,0,0,0)
    for method in search.METHODS:
        old_calls=[]; new_calls=[]
        def full(action): old_calls.append(deepcopy(action)); return cut.original.predict(value,action)
        reference=search.search(domain,base,full,method=method,budget=32)
        ctx=cut.ProtectionContext(value,domain[base])
        def candidate(action):
            new_calls.append(deepcopy(action))
            # The baseline was actually simulated during this same request's
            # construction. It is not external data and its cost is retained.
            return ctx.baseline() if action==domain[base] else ctx.predict(action)
        result=search.search(domain,base,candidate,method=method,budget=32)
        assert new_calls==old_calls
        for field in ('status','selected_action','selected_prediction','evaluations','candidate_denominator','stop_reason'):
            assert ordered(result[field])==ordered(reference[field])
        assert [r['evaluation_status'] for r in result['rows']]==[r['evaluation_status'] for r in reference['rows']]
        for old,new in zip(reference['rows'],result['rows']):
            if new.get('prediction',{}).get('status')=='conditional_protection_rejected_prefix':
                assert old['predicted_all_job_not_worse'] is False
                assert new['predicted_all_job_not_worse'] is None  # old search does not relabel a partial prediction
        counts=ctx.describe()['counts']
        assert counts['candidate_queries']+1==result['evaluations']
        METHOD_ROWS.append({'case_index':index,'method':method,'evaluations':result['evaluations'],
            'selected_action':result['selected_action'],'exact_query_sequence_and_selected_full_output':True,
            'counts':counts})
