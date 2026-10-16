"""Separate data-only entry predicate, never an actual native authorization."""
from copy import deepcopy
from pathlib import Path
import gzip,hashlib,json,math
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_entry_hop as m

def fixture():
    source={'tray_id':'L','business_bag_id':'loaded','node':0,'mode':'loaded','generation':1,
            'traversal_id':0,'committed_prefix':[0],'edge_from':-1,'edge_to':-1,'reception_node':-1}
    tray={**deepcopy(source),'edge_from':0,'edge_to':1,'traversal_id':1,'edge_exit_at':5.171}
    return {'owner_id':'A','now':4.171,'trays':[tray]},source

def test_source_binding_and_actual_first_entry_saved_shape():
    proof=m.source_proof();assert proof['native_dispatched'] is False
    path=m.ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/initial_owner_route_campaign_v3_prepare_001/raw/normal/block0_load0/fixed_default.json.gz'
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='84633d9fa8c503c6b92a2e88f814e914b083bac72850c4ef91a86ccb5da247dd'
    raw=json.loads(gzip.decompress(path.read_bytes()))
    events=raw['root_records'][0]['value']['evidence']['events']
    candidates=[e['value']['view'] for e in events if e['stage']=='continuation' and e['value']['view']['now']==4.171]
    assert len(candidates)==1
    view=candidates[0]
    # The original precondition event is an actual source snapshot, not a
    # synthetic replacement or a source reconstructed from the later receipt.
    source_events=[e for e in events if e['stage']=='final_local_and_receiver_check']
    assert len(source_events)==1
    source=source_events[0]['value']['verdict']['source']
    assert m.old.observed_first_hop(view,source) is None
    hop=m.observed_first_hop(view,source)
    assert hop['from']==0 and hop['to']==1 and hop['observed_at']==4.171
    assert hop['evidence']=='observed_entry_future_exit' and hop['tray']['edge_exit_at']==5.171
    for event in events:
        if event['stage'] not in ('continuation','post_drain_observation'):continue
        old=m.old.observed_first_hop(event['value']['view'],source)
        if old is not None:assert m.observed_first_hop(event['value']['view'],source)==old

@pytest.mark.parametrize('defect',['reservation','equal_exit','past_exit','nan','inf','bool_exit',
    'wrong_owner','duplicate','foreign_tray','wrong_job','wrong_generation','bool_generation',
    'bool_traversal','negative_traversal','wrong_mode','wrong_node','bool_node','wrong_from',
    'wrong_to','bool_to','tuple_prefix','changed_prefix','bool_prefix','bool_now','before_start',
    'source_generation_bool','source_prefix_changed','source_traversal_bool','source_edge_pending'])
def test_new_entry_branch_rejects_missing_or_malformed_fact(defect):
    view,source=fixture();tray=view['trays'][0]
    if defect=='reservation':tray.pop('edge_exit_at')
    elif defect=='equal_exit':tray['edge_exit_at']=view['now']
    elif defect=='past_exit':tray['edge_exit_at']=math.nextafter(view['now'],-math.inf)
    elif defect in ('nan','inf','bool_exit'):tray['edge_exit_at']={'nan':math.nan,'inf':math.inf,'bool_exit':True}[defect]
    elif defect=='wrong_owner':view['owner_id']='B'
    elif defect=='duplicate':view['trays'].append(deepcopy(tray))
    elif defect=='foreign_tray':tray['tray_id']='E'
    elif defect=='wrong_job':tray['business_bag_id']='receiver'
    elif defect=='wrong_generation':tray['generation']=2
    elif defect=='bool_generation':tray['generation']=True
    elif defect=='bool_traversal':tray['traversal_id']=True
    elif defect=='negative_traversal':tray['traversal_id']=-1
    elif defect=='wrong_mode':tray['mode']='empty'
    elif defect=='wrong_node':tray['node']=1
    elif defect=='bool_node':tray['node']=False
    elif defect=='wrong_from':tray['edge_from']=2
    elif defect=='wrong_to':tray['edge_to']=3
    elif defect=='bool_to':tray['edge_to']=True
    elif defect=='tuple_prefix':tray['committed_prefix']=(0,)
    elif defect=='changed_prefix':tray['committed_prefix']=[3]
    elif defect=='bool_prefix':tray['committed_prefix']=[False]
    elif defect=='bool_now':view['now']=True
    elif defect=='before_start':view['now']=0.
    elif defect=='source_generation_bool':source['generation']=True
    elif defect=='source_prefix_changed':source['committed_prefix']=[0,1]
    elif defect=='source_traversal_bool':source['traversal_id']=False
    else:source['edge_to']=1
    assert m.observed_first_hop(view,source) is None

def test_entry_is_copied_and_requires_original_complete_drain_and_updated_ACK():
    view,source=fixture();before=deepcopy(view);hop=m.observed_first_hop(view,source)
    assert view==before and hop['tray'] is not view['trays'][0]
    hop['tray']['committed_prefix'].append(99);assert view==before
    hop=m.observed_first_hop(view,source)
    command={'request_id':'route1','kind':'route','last_delivered_ack':{'status':'updated','delivered_at':4.0}}
    def closed(choice,cmd,complete):
        return m.old.closure(choice,hop,cmd,queried_owner='A',request_id='route1',now=view['now'],timestamp_complete=complete)
    assert not closed('native_default',None,False)['closed']
    assert closed('native_default',None,True)['closed']
    assert not closed('prefer_2',None,True)['closed']
    assert not closed('prefer_2',command,False)['closed']
    result=closed('prefer_2',command,True)
    assert result['closed'] and result['requested_hop_executed'] is False
    command['last_delivered_ack']['status']='rejected'
    assert closed('prefer_2',command,True)['status']=='closed_delivered_terminal_failure'

def test_post_exit_original_output_is_unchanged():
    view,source=fixture();tray=view['trays'][0]
    tray.update(node=1,edge_from=-1,edge_to=-1,committed_prefix=[0,1])
    assert m.observed_first_hop(view,source)==m.old.observed_first_hop(view,source)
