"""Synthetic controls only. No actual context, model, target or native load."""
import copy
import inspect
import itertools
import json
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_full32_suffix_partition as p
from scripts.experiments.g31_ics_circulation import live_obligation_full32_suffix_evaluator as e
from scripts.experiments.g31_ics_circulation import validate_full32_future_suffix as d


def actions():
    return [dict(zip(p.FIELDS,row)) for row in itertools.product(p.INITIAL,(.11,1.,2.,3.),p.RETURN,p.LATER)]


def detail(action):
    return {'status':'unknown_in_progress','prefix':{'status':'supported_known_B_cut'},'points':[],
        'counts':{'initial_engines':1,'initial_advances':1,'prefix_same_resumes':1,'future_forks':2,'future_resumes':2},
        'suffixes':{choice:{'status':'returned','prediction':{'synthetic':choice}} for choice in p.LATER}}


@pytest.fixture
def stub(monkeypatch):
    events=[]
    def run(context,action,limit,model,future,save):
        assert limit==4 and context['initial_only'] is True
        events.append(('run',action.copy()));return detail(action)
    monkeypatch.setattr(e.paired,'run_case',run)
    return events


def test_full32_sixteen_contexts_original_order(stub):
    calls=[]
    def context(index,action):calls.append((index,action));return {'initial_only':True}
    value=e.evaluate(actions(),context,lambda *args:None,model=None,future=None)
    assert len(calls)==len(stub)==16 and [c[0] for c in calls]==list(range(16))
    assert list(value['rows'])==[f'vector_{i:02d}' for i in range(32)]
    assert value['context_constructions']==16 and all(c[1]['later_action']=='native_default' for c in calls)
    assert all(r['status']=='unknown_prediction_returned_audit_pending' for r in value['rows'].values())


def test_one_context_failure_keeps_two_unknown_and_other_thirty(stub):
    def context(index,action):
        if index==5:raise ValueError('synthetic_initial_rejected')
        return {'initial_only':True}
    value=e.evaluate(actions(),context,lambda *args:None,model=None,future=None)
    assert len(value['rows'])==32 and len(stub)==15 and value['context_constructions']==16
    assert [k for k,r in value['rows'].items() if r['status']=='unknown_group_error']==['vector_10','vector_11']


def test_unsupported_cut_is_not_restarted_or_advanced(monkeypatch):
    calls=[]
    def run(*args):
        calls.append(args);v=detail(args[1]);v['prefix']['status']='unknown_prefix_or_fork_error'
        for row in v['suffixes'].values():row['status']='unknown_unexecuted'
        return v
    monkeypatch.setattr(e.paired,'run_case',run)
    value=e.evaluate(actions(),lambda *args:{'initial_only':True},lambda *args:None,model=None,future=None)
    assert len(calls)==16 and len(value['rows'])==32
    assert all(r['status']=='unknown_unexecuted' for r in value['rows'].values())


def test_group_callback_and_output_are_isolated(stub):
    original=actions();baseline=copy.deepcopy(original);seen=[]
    def callback(group):seen.append(group['prefix_index']);group['rows'][next(iter(group['rows']))]['action']['later_action']='mutated'
    value=e.evaluate(original,lambda *args:{'initial_only':True},lambda *args:None,model=None,future=None,on_group=callback)
    assert original==baseline and seen==list(range(16))
    # Mutable diagnostic results are not authority; distinct other candidates
    # and the admitted input domain cannot share an action dictionary.
    assert value['rows']['vector_01']['action']==original[1]


def test_evaluator_interface_has_no_future_target_parameter():
    for f in (e.evaluate,e.execute_group):
        assert not any('target' in name or 'outcome' in name or 'raw' in name for name in inspect.signature(f).parameters)


def public(action):return {'initial_owners':{'A':{'only_initial':1.},'B':{'only_initial':2.}},'action':copy.deepcopy(action)}


def test_pair_requires_complete_exact_initial_endpoint_equality():
    aa=actions()[:2];pp=[public(a) for a in aa];d.qualify_pair(pp,aa)
    pp[1]['initial_owners']['B']['only_initial']=3.
    with pytest.raises(ValueError,match='paired_initial_endpoint_bytes'):d.qualify_pair(pp,aa)


@pytest.mark.parametrize('kind',['future','action','owner_order','float_type','float_bits'])
def test_changed_public_pair_fails_closed(kind):
    aa=actions()[:2];pp=[public(a) for a in aa]
    if kind=='future':pp[0]['future_outcome']=1
    elif kind=='action':pp[1]['action']['return_delay']=.5
    elif kind=='owner_order':pp[1]['initial_owners']=dict(reversed(list(pp[1]['initial_owners'].items())))
    elif kind=='float_type':pp[1]['initial_owners']['A']['only_initial']=1
    else:pp[0]['initial_owners']['A']['only_initial']=0.;pp[1]['initial_owners']['A']['only_initial']=-0.
    with pytest.raises(ValueError):d.qualify_pair(pp,aa)


def projected(phase='first_reuse_route',known=True):
    return {'owner':'B' if phase=='first_reuse_route' else 'A','at':1.,'phase':phase,'recollection_index':0,
        'information_status':'conditional_validated_later_v3_data' if known else 'unknown',
        'retry_admission':{'status':'not_admitted'},'disposition':'future_choice'}


def test_target_prefix_stops_at_first_known_B_and_excludes_posttail_disposition():
    target={'projected_collections':[projected('first_return'),projected(),projected()]}
    rows=e.expected_prefix(target)
    assert len(rows)==2 and 'disposition' not in rows[-1]


@pytest.mark.parametrize('kind',['no_known_B','wrong_owner','extra_cuts'])
def test_bad_expected_prefix_cannot_certify(kind):
    target={'projected_collections':[projected()]}
    if kind=='no_known_B':target['projected_collections'][0]['information_status']='unknown'
    elif kind=='wrong_owner':target['projected_collections'][0]['owner']='A'
    else:target['projected_collections']=[projected('first_return')]*4+[projected()]
    with pytest.raises(ValueError):e.expected_prefix(target)


def test_audit_only_changes_status_after_complete_pair(monkeypatch):
    group=p.partition(actions())['groups'][0]
    result={'rows':{str(i):{'status':'unknown'} for i in range(2)},'context_constructions':1,'detail':detail(group['actions'][0])}
    targets={choice:json.dumps({'projected_collections':[projected()]}).encode() for choice in p.LATER}
    monkeypatch.setattr(e.paired,'audit_case',lambda *args:None)
    e.audit_group(result,targets)
    assert result['status']=='exact_two_future_suffixes' and all(v['status']=='exact_conformance' for v in result['rows'].values())


def test_partial_audit_failure_keeps_pair_unknown(monkeypatch):
    result={'rows':{str(i):{'status':'unknown'} for i in range(2)},'context_constructions':1,'detail':detail(actions()[0])}
    targets={choice:json.dumps({'projected_collections':[projected()]}).encode() for choice in p.LATER}
    def fail(*args):raise ValueError('second_suffix_mismatch')
    monkeypatch.setattr(e.paired,'audit_case',fail)
    with pytest.raises(ValueError):e.audit_group(result,targets)
    assert all(v['status']=='unknown' for v in result['rows'].values())


def test_missing_suffix_never_reduces_denominator(monkeypatch):
    def run(*args):v=detail(args[1]);v['suffixes'].pop('prefer_8');return v
    monkeypatch.setattr(e.paired,'run_case',run)
    result=e.evaluate(actions(),lambda *a:{'initial_only':True},lambda *a:None,model=None,future=None)
    assert len(result['rows'])==32 and all(v['status']=='unknown_group_error' for v in result['rows'].values())


def test_shared_budget_includes_parent_setup():
    assert d.remaining(20.)==339.
    with pytest.raises(TimeoutError):d.remaining(359.)
    for value in (True,-1,float('nan'),float('inf')):
        with pytest.raises(ValueError):d.remaining(value)


def test_action_mutation_in_factory_does_not_change_original_domain(stub):
    aa=actions();before=copy.deepcopy(aa)
    def context(index,action):action['initial_action']='mutated';return {'initial_only':True}
    result=e.evaluate(aa,context,lambda *a:None,model=None,future=None)
    assert aa==before and all(v['action']==before[i] for i,v in enumerate(result['rows'].values()))


@pytest.mark.parametrize('kind',['past_coordinate','boolean_index','wrong_indices'])
def test_direct_group_api_cannot_relabel_past_actions_or_indices(stub,kind):
    group=p.partition(actions())['groups'][0]
    if kind=='past_coordinate':group['actions'][1]['return_delay']=.5
    elif kind=='boolean_index':group['prefix_index']=False
    else:group['candidate_indices']=[2,3]
    result=e.execute_group(group,lambda *args:{'initial_only':True},lambda *args:None,model=None,future=None)
    assert result['context_constructions']==0 and not stub
    assert len(result['rows'])==2 and all(v['status']=='unknown_group_error' for v in result['rows'].values())
