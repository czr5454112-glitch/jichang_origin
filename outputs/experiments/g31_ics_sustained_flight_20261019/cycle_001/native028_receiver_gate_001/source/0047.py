"""Declared small native028 receiver-admission fixture; imports no native module."""
from copy import deepcopy

POLICY = 'g31.receiver_empty_transit_admission.v1'
FIELD = 'empty_receive_transit_reserve'


def scene(reserve=None):
    from .native_host import prepare_input
    nodes = [{'node': n, 'zone': 'A' if n in (0, 2) else 'B',
              'resource_owner': 'A' if n in (0, 2) else 'B', 'capacity': 4} for n in range(4)]
    if reserve is not None:
        nodes[1][FIELD] = reserve
    edges = [(0, 1, 10., 1.), (2, 1, 10., 1.), (3, 1, 1., 1.)]
    return prepare_input({'schema': 'g31.circulation.input.v1',
        'model_scope': 'native028 finite receiver policy fixture; no airport claim',
        'node_records': [(n, 1, 5. if n == 0 else .001, 0, 0,
                          [v for u, v, _, _ in edges if u == n]) for n in range(4)],
        'edge_records': edges, 'node_contracts': nodes,
        'edge_contracts': [{'from': u, 'to': v, 'capacity': 4, 'entry_headway': .1} for u,v,_,_ in edges],
        'trays': [{'tray_id': t, 'node': n} for t,n in (('E1',0),('E2',2),('L',3),('P0',1),('P1',1))],
        'jobs': [{'business_bag_id':'loaded','origin':3,'destination':1,'arrival':0.,'deadline':30.,
                  'load_seconds':0.,'unload_seconds':0.,'hold_seconds':100.}],
        'transfers':[], 'faults':[], 'options':{'max_simulation_time':30.,'trace_limit':1000},
        'owner_protocol':{'enabled':True,'ack_delay':.01,'timeout':.2}})


def requests():
    return [{'request_id':f'live:1:A:return:{tray}', 'owner_id':'A','tray_id':tray,
             'source':source,'destination':1,'issued_at':0.,'message_delay':0.,
             'earliest_departure':0.,'expiry':25.} for tray,source in (('E1',0),('E2',2))]


def tape():
    a,b = requests()
    planning = {'request_id':'live:1:B:planning:one','owner_id':'B','kind':'planning_snapshot_v3',
                'target_owner':'A','message_delay':0.,'publication_delay':.01,'expiry':30.}
    cancel = {'request_id':'live:1:A:cancel:one','owner_id':'A','kind':'cancel_transfer',
              'transfer_request_id':a['request_id'],'message_delay':0.}
    def call(endpoint, *args):
        return {'endpoint':endpoint,'args':list(args),'kwargs':{}}
    return [call('submit_protocol_transfer',a),call('submit_protocol_transfer',a),
        call('submit_protocol_transfer',b),call('advance_to',.1),call('observe_protocol','A'),
        call('observe_protocol','B'),call('protocol_request','A',a['request_id']),
        call('protocol_request','A',b['request_id']),call('submit_protocol_command',planning),
        call('advance_to',.2),call('protocol_planning_snapshots_v3','A'),
        call('advance_to',6.),call('submit_protocol_command',cancel),call('advance_to',6.1),
        call('protocol_command','A',cancel['request_id']),call('result_at',20.)]


def run(native, reserve, *, restore=False):
    """One constructor; optional in-place checkpoint restore adds no session."""
    data = scene(reserve)
    session = native.NativeSession(data)
    initial_seal = session.offline_state_sha256()
    checkpoint = session.checkpoint()
    restore_evidence = None
    if restore:
        session.advance_to(.0005)
        session.restore(checkpoint)
        restore_evidence = {'initial': initial_seal, 'restored': session.offline_state_sha256(),
                            'clock': session.physical_time}
    outputs=[]
    for spec in tape():
        row=deepcopy(spec)
        row['returned']=deepcopy(getattr(session,spec['endpoint'])(*spec['args'],**spec['kwargs']))
        outputs.append(row)
    return {'input':data,'outputs':outputs,'initial_seal':initial_seal,
            'checkpoint_initial_seal':checkpoint.offline_state_sha256,
            'final_seal':session.offline_state_sha256(), 'restore':restore_evidence,
            'checkpoint_final_seal':session.checkpoint().offline_state_sha256}


def stable(value):
    # Remove only measured CPU/wall diagnostics, preserving all semantic order.
    if isinstance(value,dict):
        return {k:stable(v) for k,v in value.items() if k not in
                {'wall_seconds','compute_wall_ms','compute_cpu_ms','submit_compute_ms','wall_ms','cpu_ms'}}
    if isinstance(value,(list,tuple)):
        return [stable(x) for x in value]
    return value


def validate(row, reserve):
    assert row['input'] == scene(reserve)
    assert [{k:x[k] for k in ('endpoint','args','kwargs')} for x in row['outputs']] == tape()
    assert row['initial_seal'] == row['checkpoint_initial_seal']
    assert row['final_seal'] == row['checkpoint_final_seal']
    if row['restore'] is not None:
        assert row['restore'] == {'initial':row['initial_seal'],'restored':row['initial_seal'],'clock':0.}
    result=row['outputs'][-1]['returned']
    assert result['physical_clock'] == 20. and len(result['jobs']) == 1 and len(result['trays']) == 5
    transfers={x['request_id']:x for x in result['transfers']}
    a,b=requests()
    assert len(transfers)==2  # immutable retry cannot create another reservation
    receipts=result['receipts']
    grants=[r for r in receipts if r['event']=='EXPORT_GRANTED']
    entered=[r for r in receipts if r['event']=='EDGE_ENTER']
    cancel=row['outputs'][-2]['returned']['last_delivered_ack']
    if reserve in (None,0):
        assert transfers[a['request_id']]['status']==transfers[b['request_id']]['status']=='received'
        assert len(grants)==2 and result['jobs'][0]['status']!='completed'
        assert cancel['status']=='rejected'
    elif reserve==1:
        assert transfers[a['request_id']]['status']=='received'
        assert transfers[b['request_id']]['status']=='rejected'
        assert transfers[b['request_id']]['reason']=='receiver_transit_reserve'
        assert len(grants)==1 and result['jobs'][0]['status']=='completed'
        assert [r['tray_id'] for r in entered]==['L','E1']
        assert cancel['status']=='rejected'  # E1 departed by t6, lease survives.
        assert len([r for r in receipts if r['event']=='EMPTY_RECEIVED' and r['tray_id']=='E1'])==1
        assert {t['tray_id'] for t in result['trays'] if t['node']==1}=={'L','E1','P0','P1'}
    else:
        assert reserve==2 and len(grants)==0 and result['jobs'][0]['status']=='completed'
        assert all(x['reason']=='receiver_transit_reserve' for x in transfers.values())
    envelope=row['outputs'][10]['returned'][0]
    return {'static_contract_sha256':envelope['capture']['capture_v2']['local_capture']['static_contract_sha256'],
            'result':result,'empty_grants':len(grants)}
