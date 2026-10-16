"""Exact saved18 and alias/failure gate; no native or prediction calls."""
import copy
import inspect
import json
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import single_root_evidence as s
from scripts.experiments.g31_ics_circulation import root_evidence_mock as m


@pytest.fixture(scope='module')
def saved():return m.load_inputs()


def publish(value,arm='B',stamp=None):
    stamp=stamp or value['root_deadline_ns']+10**9
    method,fn=m.functions(arm,SimpleNamespace(perf_counter_ns=lambda:stamp))
    root=m.root_from_evidence(value,method);holder=[]
    result=fn(root,holder)
    assert holder==[result]
    return root,result


@pytest.mark.parametrize('index',range(18))
def test_all_real_eighteen_complete_ordered_fields_and_frozen_clock_equivalence(saved,index):
    key,stored=saved[index];value=stored['value']['evidence']
    _,a=publish(value,'A');_,b=publish(value,'B')
    assert s.exact_tree(a,b),key
    assert s.exact_tree(m.semantic_record(b),m.semantic_record(stored)),key
    raw=s.image.artifact_encode(value)
    assert b['ledger']['bytes']==len(raw)
    assert b['ledger']['evidence_sha256']==s.hashlib.sha256(raw).hexdigest()
    assert json.loads(b['return_codec'])==b['ledger']


def small(saved):
    value=copy.deepcopy(saved[12][1]['value']['evidence'])
    assert value['state']=='unknown_collection'
    return value


def mutable_ids(value):
    ids=set();stack=[value]
    while stack:
        x=stack.pop()
        if type(x) in (dict,list):
            if id(x) in ids:continue
            ids.add(id(x));stack.extend(x.values() if type(x) is dict else x)
    return ids


def test_return_no_mutable_alias_to_root_input_or_next_return(saved):
    value=small(saved);root,a=publish(value);_,b=publish(value)
    assert not (mutable_ids(a)&mutable_ids(value))
    assert not (mutable_ids(a)&mutable_ids(b))
    a['value']['evidence']['events'][0]['value']['physical_time']='mutated'
    a['ledger']['state']='mutated';a['value']['evidence']['initial_endpoint_records']['A'].clear()
    assert s.exact_tree(b['value']['evidence'],value)
    assert root.events is value['events'] and b['ledger']['state']==value['state']
    value['events'][0]['value']['physical_time']='caller mutation'
    assert b['value']['evidence']['events'][0]['value']['physical_time']!='caller mutation'


def test_body_encodes_complete_evidence_once_plus_small_ledger_once(saved):
    value=small(saved);calls=[]
    original=s.image.artifact_encode
    def encode(v):calls.append(list(v));return original(v)
    facade=SimpleNamespace(**vars(s.image));facade.artifact_encode=encode
    method=m.clone(s.evidence,image=facade)
    root=m.root_from_evidence(value,method)
    finish=m.clone(s.finish_root,image=facade)
    result=finish(root)
    assert len(calls)==2 and 'initial_endpoint_records' in calls[0] and calls[1]==list(result['ledger'])


@pytest.mark.parametrize('a,b',[(1,1.0),(True,1),(-0.0,0.0),({'a':1,'b':2},{'b':2,'a':1}),
    ([1,2],[2,1]),([1],(1,)),(float('nan'),float('nan'))])
def test_exact_tree_does_not_blur_order_or_scalar_bits(a,b):assert not s.exact_tree(a,b)


def test_tuple_and_homogeneous_int_resource_boundary_stays_identical(saved):
    value=small(saved)
    value['events'].append({'stage':'representation_regression','wall_ns':value['root_started_ns'],
        'value':{'rows':[(1,2.0,-0.0)],'status':'conditional_model_input','contract':{},
                 'resources':{0:{'node':0}}}})
    _,a=publish(value,'A');_,b=publish(value,'B')
    assert s.exact_tree(a,b)


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),object(),{0:'unsupported key'}])
def test_bad_evidence_never_appends_closed_result_or_poisons_next_call(saved,bad):
    value=small(saved);value['events'].append(bad)
    method,fn=m.functions('B',s.time);root=m.root_from_evidence(value,method);holder=[]
    with pytest.raises((ValueError,TypeError)):fn(root,holder)
    assert holder==[]
    _,good=publish(small(saved));assert good['closed'] is False


@pytest.mark.parametrize('stage',['encode','decode','ledger_encode'])
def test_codec_or_capacity_failure_propagates_without_success(saved,stage):
    value=small(saved);calls=[0]
    def encode(v):
        calls[0]+=1
        if stage=='encode' or stage=='ledger_encode' and calls[0]==2:raise ValueError('injected_artifact_limit')
        return s.image.artifact_encode(v)
    def decode(raw):
        if stage=='decode':raise ValueError('injected_strict_decode')
        return s.image.artifact_decode(raw)
    facade=SimpleNamespace(**vars(s.image));facade.artifact_encode=encode;facade.artifact_decode=decode
    method=m.clone(s.evidence,image=facade)
    finish=m.clone(s.finish_root,image=facade)
    fn=m.clone(s.publish_root,finish_root=finish)
    root=m.root_from_evidence(value,method);holder=[]
    with pytest.raises(ValueError,match='injected'):fn(root,holder)
    assert holder==[]


def test_reordered_decoded_evidence_rejected(saved):
    def decode(raw):
        result=s.image.artifact_decode(raw)
        return dict(reversed(list(result.items())))
    facade=SimpleNamespace(**vars(s.image));facade.artifact_decode=decode
    root=m.root_from_evidence(small(saved),s.evidence)
    with pytest.raises(ValueError,match='roundtrip_order_or_type'):
        m.clone(s.finish_root,image=facade)(root)


def test_private_clock_and_publication_bytecode_no_global_patch(saved):
    original_time=s.time.perf_counter_ns;original_method=m.old.request.InitialOwnerRequest.evidence
    publish(small(saved),'A');publish(small(saved),'B')
    assert s.time.perf_counter_ns is original_time and m.old.request.InitialOwnerRequest.evidence is original_method
    assert s.publish_root.__code__ is m.old.publish_root.__code__
    assert 'super().evidence' not in inspect.getsource(s.evidence)
    assert 'deepcopy' not in inspect.getsource(s.finish_root)


def test_old130_sources_remain_byte_identical():
    plan=m.old.read(m.SOURCE/'campaign.json')
    assert len(plan['source_sha256'])==130
    for path,digest in plan['source_sha256'].items():
        assert m.old.sha(path)==digest
        assert m.old.sha(m.SOURCE/plan['source_archive'][path])==digest


def test_mock_fixed_order_and_no_candidate_denominator_reduction():
    from scripts.experiments.g31_ics_circulation import measure_single_root_evidence as measure
    keys=[str(i) for i in range(18)]
    rows=measure.rows(keys)
    assert len(rows)==72 and [x['key'] for x in rows[::4]]==keys
    assert ''.join(x['arm'] for x in rows)=='ABBA'*18
    assert [x['position'] for x in rows]==[0,1,2,3]*18 and measure.LIMIT==240


@pytest.mark.parametrize('bad_clock',[True,1.0,-1])
def test_current_mock_measurement_clock_rejects_malformed_values(saved,bad_clock):
    value=small(saved);stamp=value['root_deadline_ns']+10**9
    _,record=publish(value,stamp=stamp)
    record['outside_return_ns']=bad_clock
    with pytest.raises(ValueError,match='clock_bound'):m.current_clock_bounds(record,stamp,stamp)


@pytest.mark.parametrize('where',['outer_extra','outer_order','value_extra','value_order'])
def test_saved_mock_rejects_unlisted_outer_fields_or_order(saved,where):
    _,record=publish(small(saved))
    if where=='outer_extra':record['hidden']='not declared'
    elif where=='outer_order':record=dict(reversed(list(record.items())))
    elif where=='value_extra':record['value']['hidden']='not declared'
    else:record['value']=dict(reversed(list(record['value'].items())))
    with pytest.raises(ValueError,match='topology'):m.semantic_record(record)


@pytest.mark.parametrize('field',['body_elapsed_ns','warm_caller_elapsed_ns','closed','within_100ms_observed'])
def test_historical_clock_and_status_fields_remain_verified_data(saved,field):
    value=small(saved);stamp=value['root_deadline_ns']+10**9
    _,record=publish(value,stamp=stamp)
    if field=='body_elapsed_ns':record['value'][field]+=1
    elif field=='warm_caller_elapsed_ns':record[field]+=1
    else:record[field]=not record[field]
    with pytest.raises(ValueError,match='formula'):m.current_clock_bounds(record,stamp,stamp)


def test_saved_mock_rejects_missing_or_extra_rows_before_promoting(monkeypatch,tmp_path):
    from scripts.experiments.g31_ics_circulation import measure_single_root_evidence as measure
    monkeypatch.setattr(measure,'verify_pins',lambda *a:{'row_order':[]})
    monkeypatch.setattr(m,'load_inputs',lambda:[])
    for count in (0,71,73):
        monkeypatch.setattr(measure.c,'read',lambda *a,n=count:[{}]*n)
        with pytest.raises(ValueError,match='saved_denominator'):measure.verify_saved(tmp_path,'fixture')
