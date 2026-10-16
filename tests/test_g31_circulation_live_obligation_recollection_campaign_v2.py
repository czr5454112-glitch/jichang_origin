"""Native-binding-shaped supplied fixtures; no native/predictor execution."""
import copy, gzip, json
from pathlib import Path
from types import FunctionType
import pytest
import test_g31_circulation_live_obligation_recollection_campaign as previous
from scripts.experiments.g31_ics_circulation import research_live_obligation_recollection_v2 as c
from scripts.experiments.g31_ics_circulation import launch_live_obligation_recollection_v2 as launch
from scripts.experiments.g31_ics_circulation import verify_live_obligation_recollection_v2 as saved
from scripts.experiments.g31_ics_circulation import live_obligation_recollection_policy_v2 as policy
from scripts.experiments.g31_ics_circulation import live_obligation_native_view_v2 as representation

# Keep every accepted39 campaign check, executing the new independent modules.
_namespace = {**vars(previous),'c':c,'launch':launch,'saved':saved}
for _name in ('supplied_fixture','assessed_rows',*[n for n in vars(previous) if n.startswith('test_')]):
    _old=getattr(previous,_name)
    _new=FunctionType(_old.__code__,_namespace,_old.__name__,_old.__defaults__,_old.__closure__)
    _new.__kwdefaults__=_old.__kwdefaults__;_new.__dict__.update(_old.__dict__)
    _namespace[_name]=globals()[_name]=_new


def view_fixture():
    return {'owner_id':'B','now':10.179999999999998,
        'node_records':[(0,'service',.2,0.,0.,[1,2])],
        'edge_records':[(0,1,2.,1.)], 'trays':[{'generation':5,'committed_prefix':[7]}]}


def test_only_binding_rows_change_and_exact_float_bits_remain():
    view=view_fixture(); original=copy.deepcopy(view)
    safe,equal=representation.equivalent_views(view,json.loads(json.dumps(view)))
    assert equal and view==original and type(view['node_records'][0]) is tuple
    assert type(safe['node_records'][0]) is list and safe['now'].hex()==view['now'].hex()
    assert list(safe)==list(view) and safe['node_records'][0][-1]==[1,2]
    assert representation.equivalent_views(safe,safe)[1]


@pytest.mark.parametrize('change',['now','bool_now','owner','extra','missing','array_order','int_float',
                                  'signed_zero','generation','prefix'])
def test_real_field_or_timing_change_never_becomes_equal(change):
    view=view_fixture(); other=json.loads(json.dumps(view))
    if change=='now':other['now']+=.001
    elif change=='bool_now':other['now']=True
    elif change=='owner':other['owner_id']='A'
    elif change=='extra':other['unseen']=False
    elif change=='missing':del other['owner_id']
    elif change=='array_order':other['node_records'][0][-1].reverse()
    elif change=='int_float':other['node_records'][0][0]=0.
    elif change=='signed_zero':other['node_records'][0][3]=-0.
    elif change=='generation':other['trays'][0]['generation']+=1
    else:other['trays'][0]['committed_prefix']=[7,8]
    assert representation.equivalent_views(view,other)[1] is False


@pytest.mark.parametrize('change',['nan','inf','foreign_tuple','nested_tuple','table_tuple','short_row',
                                  'scalar_row','missing_table','int_key','custom','cycle'])
def test_unsupported_shape_does_not_expand_to_arbitrary_json_conversion(change):
    view=view_fixture()
    if change=='nan':view['now']=float('nan')
    elif change=='inf':view['now']=float('inf')
    elif change=='foreign_tuple':view['trays'][0]['committed_prefix']=(7,)
    elif change=='nested_tuple':view['node_records'][0]=(0,'service',.2,0.,0.,(1,2))
    elif change=='table_tuple':view['node_records']=tuple(view['node_records'])
    elif change=='short_row':view['edge_records']=[(0,1)]
    elif change=='scalar_row':view['node_records']=[1]
    elif change=='missing_table':del view['edge_records']
    elif change=='int_key':view[1]='unknown'
    elif change=='custom':
        class Custom(dict):
            def items(self):pytest.fail('custom hook must not execute')
        view['trays'][0]=Custom(view['trays'][0])
    else:view['cycle']=view
    with pytest.raises(ValueError):representation.normalized_view(view)


def test_actual44_saved_failures_have_same_screen_with_real_binding_tuple_shape():
    report=c.read(c.DIAGNOSIS)
    assert c.sha(c.DIAGNOSIS)==c.DIAGNOSIS_SHA
    failed=c.read(c.FAILED_PLAN);authority=c.read(failed['native_contract_reference']['path'])
    binding=Path(authority['source_archive'])/'cpp/ics_core/bindings/circulation_session_binding.hpp'
    assert c.reference(binding)==report['accepted_binding']
    source=binding.read_text()
    assert 'nodes.append(py::make_tuple(n.location,n.node_type,n.service_time,n.x,n.y,n.outgoing));' in source
    assert 'edges.append(py::make_tuple(e.from,e.to,physical.length,physical.speed));' in source
    counts={}; total=0
    for key,row in report['rows'].items():
        if row['preserved_status']!='unknown_failed':continue
        assert c.sha(row['raw']['path'])==row['raw']['sha256']
        raw=json.loads(gzip.decompress(Path(row['raw']['path']).read_bytes()))
        for owner,entries in raw['collection_attempts'].items():
            for entry in entries:
                if entry['retry_admission']['reason']!='not_the_collected_current_view':continue
                _,requests,owned=saved.replay_information(raw,owner,entry)
                view=copy.deepcopy(entry['actual_local_view'])
                for field in ('node_records','edge_records'):view[field]=[tuple(r) for r in view[field]]
                assert policy.old.retry_admission(entry['information'],entry['collection'],view,owned)==entry['retry_admission']
                result=policy.retry_admission(entry['information'],entry['collection'],view,owned)
                assert result==policy.old.retry_admission(entry['information'],entry['collection'],entry['actual_local_view'],owned)
                assert result['status']=='conditional_retry_admissible'
                assert policy.adapter.is_native_attempt(entry['information']) is False
                counts[result['reason']]=counts.get(result['reason'],0)+1;total+=1
    assert total==44 and counts=={'actual_owned_tray_changed_after_capture':30,'known_stationary_service_crossed_collection':14}


def test_live_seal_and_all_other_methods_are_unchanged_and_no_capability_is_minted():
    assert policy.OwnerPolicy.decide_pending.__code__ is policy.old.OwnerPolicy.decide_pending.__code__
    assert policy.OwnerPolicy.decide_pending.__globals__['retry_admission'] is policy.retry_admission
    assert policy.old.OwnerPolicy.decide_pending.__globals__['retry_admission'] is policy.old.retry_admission
    for name in ('begin','exchange','_begin_recollection','activate','return_tray','route_tray'):
        assert getattr(policy.OwnerPolicy,name) is getattr(policy.old.OwnerPolicy,name)
    data={'status':'unknown','raw_endpoints':{'view':view_fixture()}}
    assert not policy.adapter.is_native_attempt(data)
    assert not policy.adapter.is_native_collected(data)
    assert saved.verify_attempts.__code__ is saved.old.verify_attempts.__code__
    assert saved.verify_attempts.__globals__['policy'] is policy


def test_original82_live_and_archive_sources_remain_unchanged():
    assert c.sha(c.FAILED_PLAN)==c.FAILED_PLAN_SHA
    plan=c.read(c.FAILED_PLAN)
    assert len(plan['source_sha256'])==82
    for path,digest in plan['source_sha256'].items():
        assert c.sha(path)==c.sha(c.FAILED_PLAN.parent/plan['source_archive'][path])==digest
