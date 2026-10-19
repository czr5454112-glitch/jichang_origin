import copy
import gzip
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_multistep_learning as learn


def events():
    data={'jobs':[{'business_bag_id':'a','arrival':1.}, {'business_bag_id':'b','arrival':4.},
                  {'business_bag_id':'future','arrival':20.}]}
    result={'physical_clock':10.,'jobs':[{'business_bag_id':'a','status':'completed','completed_at':7.},
         {'business_bag_id':'b','status':'waiting','completed_at':-1.},
         {'business_bag_id':'future','status':'unreleased','completed_at':-1.}],
         'receipts':[{'business_bag_id':'a','event':'BAG_ARRIVAL','time':1.},
                     {'business_bag_id':'b','event':'BAG_ARRIVAL','time':4.},
                     {'business_bag_id':'a','event':'UNLOAD_COMPLETE','time':7.}]}
    return data,result


def test_exact_nonconstant_integral_and_additive_intervals():
    audit=learn.audit_business_events(*events())
    whole=learn.interval_reward(audit,2.,9.)
    assert whole['value']==-10.  # a:5 seconds, b:5; future:0
    assert whole['value']==sum(learn.interval_reward(audit,a,b)['value'] for a,b in [(2.,5.),(5.,8.),(8.,9.)])
    assert not audit['all_business_complete']
    assert whole['per_job'][-1]['flow_seconds']==0.


def test_incomplete_job_is_not_a_fake_completion():
    data,result=events(); result['jobs'][1]['status']='completed';result['jobs'][1]['completed_at']=10.
    with pytest.raises(ValueError,match='completion_receipt'):
        learn.audit_business_events(data,result)


def test_reward_cannot_integrate_past_observed_clock():
    with pytest.raises(ValueError,match='outside_observed'):
        learn.interval_reward(learn.audit_business_events(*events()),5.,11.)


def archived_raw():
    path=Path(__file__).resolve().parents[1]/'outputs/experiments/g31_ics_multirate_20261019/owner_transition_001/guarded_default/episode/native/raw.json.gz'
    return json.loads(gzip.decompress(path.read_bytes()))


def route_decision(raw):
    identity,row=next((k,r) for k,r in raw['outbox'].items() if r['kind']=='route' and r['request']['business_bag_id']=='reuse2')
    request=row['request']
    at=min(c['at'] for c in raw['calls'] if c['request']['request_id']==identity)
    return {'command_id':identity,'owner':request['owner_id'],'selected_at':at,'actual_ack':row['ack'],
            'opportunity':{'target':{'tray_id':request['tray_id'],'business_bag_id':request['business_bag_id'],
              'generation':request['expected_generation'],'traversal_id':request['expected_traversal'],'node':request['from']}}}


def test_real_route_binds_two_distinct_traversal_namespaces():
    raw=archived_raw();decision=route_decision(raw);effect=learn.bind_effect(raw,decision)
    assert effect['edge']['business_bag_id']=='reuse2'
    assert effect['protocol_traversal'] != effect['load']['traversal_id']
    assert effect['edge']['traversal_id']==effect['load']['traversal_id']+1
    assert effect['updated']['time']<effect['edge']['time']


def test_wrong_protocol_generation_rejected_even_if_future_tray_edge_exists():
    raw=archived_raw();decision=route_decision(raw);decision['opportunity']['target']['generation']+=1
    with pytest.raises(ValueError,match='generation_traversal'):
        learn.bind_effect(raw,decision)


def test_route_cannot_bind_another_reuse_cycle():
    raw=archived_raw();decision=route_decision(raw)
    for e in raw['result']['receipts']:
        if e['business_bag_id']=='reuse2' and e['event']=='EDGE_ENTER':
            e['business_bag_id']='reuse1'
    with pytest.raises(ValueError,match='no_physical_edge'):
        learn.bind_effect(raw,decision)


def test_real_transfer_exact_request_receipt():
    raw=archived_raw();identity,row=next((k,r) for k,r in reversed(list(raw['outbox'].items())) if r['kind']=='transfer')
    at=min(c['at'] for c in raw['calls'] if c['request']['request_id']==identity)
    decision={'command_id':identity,'owner':row['request']['owner_id'],'selected_at':at,'actual_ack':row['ack'],
              'opportunity':{'target':{'tray_id':row['request']['tray_id'],'generation':0,'traversal_id':0}}}
    effect=learn.bind_effect(raw,decision)
    assert effect['received']['reason']==identity
    effect['received']['reason']='wrong_request'
    with pytest.raises(ValueError,match='receipt_identity'):
        learn.bind_effect(raw,decision)


def transition(identity, obs, nxt, action, reward, terminal=False):
    candidate={'action_id':'chosen','semantic':action,'enabled':True,'guard_status':'original_fixed_rule'}
    return {'split':'train','training_eligible':True,'owner':'B','peer_policy_id':'fixed-A',
        'parent_group':'case1','decision_id':identity,'observation':obs,'action':action,
        'next_observation':nxt,'next_candidate_mask':[candidate], 'terminated':terminal,'truncated':False,
        'gamma':1.,'reward':{'value':reward}}


def test_bellman_uses_actual_supported_next_action_and_real_interval_reward():
    action={'operation_kind':'route','destination':3}; a={'at':1.};b={'at':3.}
    rows=[transition('first',a,b,action,-6.),transition('second',b,None,action,-2.,True)]
    targets=learn.bellman_targets(rows,{'frozen':'model'},scorer=lambda m,o,a:[-4.]*len(o))
    assert [r['target_value'] for r in targets]==[-10.,-2.]
    assert targets[0]['supported_next_action_count']==1


def test_unvisited_action_cannot_be_bootstrapped_by_semantic_name():
    action={'operation_kind':'route','destination':3}
    rows=[transition('first',{'at':1.},{'at':3.},action,-6.),
          transition('different_state',{'at':4.},None,action,-2.,True)]
    with pytest.raises(ValueError,match='unsupported_or_censored'):
        learn.bellman_targets(rows)


def test_truncation_is_not_terminal_zero_bootstrap():
    row=transition('censored',{'at':1.},None,{},-1.);row['truncated']=True
    with pytest.raises(ValueError,match='unsupported_or_censored'):
        learn.bellman_targets([row])


def test_training_semantic_must_match_real_command_and_effect():
    raw=archived_raw();decision=route_decision(raw);effect=learn.bind_effect(raw,decision)
    selected={'semantic':{'tray_id':'L','source':7,'destination':8,'operation_kind':'route'}}
    with pytest.raises(ValueError,match='semantic_route_destination'):
        learn.validate_selected_semantic(raw,decision,selected,effect)


def test_same_decision_ids_in_two_behavior_branches_cannot_mix_returns():
    rows=[]
    for source,scale in [('branch-a',1.),('branch-b',10.)]:
        for identity,next_id,reward in [('first','second',-scale),('second',None,-2*scale)]:
            r=transition(identity,{'at':1.},None,{},reward,terminal=next_id is None)
            r.update(source={'sha256':source},next_decision_id=next_id)
            rows.append(r)
    assert [r['target_value'] for r in learn.monte_carlo_labels(rows)]==[-3.,-2.,-30.,-20.]


def test_counter_only_difference_is_not_a_different_physical_effect():
    raw=archived_raw();effect=learn.bind_effect(raw,route_decision(raw));other=copy.deepcopy(effect)
    other['edge']['traversal_id']+=5;other['protocol_generation']+=1;other['request_id']='another-label'
    assert learn.physical_signature(effect)==learn.physical_signature(other)


def partitions():
    return {'train_parent_groups':['train'], 'development_parent_groups':['dev'],
            'evaluation_plan':{'held_out_parent_groups':['test_positive','test_negative']}}


def test_formal_test_and_wrongly_relabelled_heldout_rejected_before_raw_read(tmp_path):
    for row in [{'split':'test','parent_group':'test_positive'},
                {'split':'development','parent_group':'test_negative'}]:
        row['directory']=str(tmp_path/'nonexistent')
        with pytest.raises(ValueError,match='before_raw_read'):
            learn.validate_training_partitions(partitions(),[row],inspect_registered_plans=True)


def test_heldout_overlap_cannot_be_hidden_in_development():
    c=partitions();c['development_parent_groups']=['test_negative']
    with pytest.raises(ValueError,match='heldout_partition_overlap'):
        learn.validate_training_partitions(c,[])


def test_spoofed_parent_is_rejected_from_plan_before_reading_raw(tmp_path):
    (tmp_path/'plan.json').write_text(json.dumps({'rows':{'key':{'case':'test_positive'}}}))
    with pytest.raises(ValueError,match='registered_case_partition_before_raw_read'):
        learn.validate_training_partitions(partitions(),[{'directory':str(tmp_path),'parent_group':'train','split':'train'}],
                                           inspect_registered_plans=True)
