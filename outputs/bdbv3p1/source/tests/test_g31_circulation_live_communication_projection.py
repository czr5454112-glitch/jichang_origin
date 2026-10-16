import copy
import gzip
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_delivered_context as c
from scripts.experiments.g31_ics_circulation import public_live_obligation_communication_projection as m
from scripts.experiments.g31_ics_circulation import planning_capture_v3_contract as v3

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def context():
    path=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/live_obligation_unloading_native_prepare_001/mechanism/vector_00.json.gz'
    raw=json.loads(gzip.decompress(path.read_bytes()));ep=raw['initial_owners']['A']['raw_endpoints']
    request=next(x['request'] for x in raw['calls'] if x['request']['request_id']==ep['command']['request_id'])
    result=c.initial_context(**ep,own_request=request)
    assert type(result) is c.SuppliedContext
    return result


@pytest.fixture
def engine(context):
    e=m.Projection(c.initial_projection_bundle(context),m.physics.previous.actions()[0],c.revalidate(context))
    e.begin_leg('L',4,ready=e.jobs['loaded']['loaded_at']+e.service[0])
    return e


def test_source_capture_copies_processed_state_not_future_heap(engine):
    e=engine;row=e.publish('A','test');body=e.world.capture(row)
    first=copy.deepcopy(body['capture']['capture_v2']['local_capture']['trays'])
    e.events.append((.12,0,999,'unload',('P',)))
    again=e.world.capture(row)
    assert first==again['capture']['capture_v2']['local_capture']['trays']
    assert body['payload_sha256']==v3.capture_digest_v3(body['capture'])
    assert body['capture']['capture_v2']['extension']['terminal_receipts']==[]


def test_projected_loading_bound_does_not_become_base_available(engine):
    t=engine.world.tray('P',captured=True)
    assert t['available_at']==t['load_complete_at']==3.
    assert engine.trays['P']['available_at']==0.
    engine.time=3.;engine.before_event('load_end',('P',));engine.trays['P']['mode']='loaded'
    engine.begin_leg('P',9)
    assert engine.world.tray('P',captured=True)['available_at']==0.


def test_irreversible_reservation_is_not_observed_entry(engine):
    e=engine;t=e.trays['P'];t.update(mode='loaded',node=9,job='blocker',edge_from=9,edge_to=3,traversal_id=1)
    e.world.prefix['P']=[9]
    row=e.publish(e.world.owner(9),'test');capture=e.world.capture(row)['capture']
    assert capture['extension']['coverage']['unmatched_tray_ids']==['P']
    assert not capture['extension']['coverage']['complete_for_declared_source_inflight']
    e.world.entry('P',9,3);capture=e.world.capture(row)['capture']
    assert capture['extension']['coverage']['unmatched_tray_ids']==[]
    fact=capture['extension']['source_observed_inflight'][0]
    assert fact['derived_edge_exit_at']==e.time+e.travel[9,3]


def test_goal_service_metadata_remains_clamped(engine):
    e=engine;t=e.trays['P'];t.update(mode='loaded',node=10,job='blocker',goal=10,ready=12.)
    e.world.active['P']=True;e.world.in_service['P']=True;e.time=11.
    projected=e.world.tray('P',captured=True)
    assert projected['service_ready_at']==11. and projected['service_ready_at']!=12.


def test_unload_timer_is_not_completion_receipt(engine):
    e=engine;t=e.trays['E'];t.update(mode='unloading',node=4,job='receiver',goal=None)
    e.world.started['E']=5.;e.time=5.01
    assert e.world.tray('E',captured=True)['available_at']==5.+e.jobs['receiver']['unload_seconds']
    assert not e.world.completions
    e.time=5.1;e.before_event('unload',('E',))
    assert len(e.world.completions)==1 and e.world.completions[0]['completed_at']==5.1


@pytest.mark.parametrize('action',[
    {'initial_action':'native_default','empty_departure':.11,'return_delay':False,'later_action':'native_default'},
    {'initial_action':'native_default','empty_departure':float('nan'),'return_delay':0.,'later_action':'native_default'},
    {'initial_action':'native_default','empty_departure':.11,'return_delay':0.,'later_action':'native_default','outcome':1},
])
def test_undeclared_actions_rejected_without_run(context,action):
    assert m.predict(context,action)['status']=='unknown'


def test_fake_delivery_flags_cannot_enter_predictor(context):
    assert m.predict({'status':'conditional_native_delivered_model_input','native_delivery_verified':True},
                     m.physics.previous.actions()[0])['status']=='unknown'


def test_publication_delivery_and_self_ack_separate(engine):
    e=engine;row=e.publish('B','test');issued=e.time
    e.time=issued+.01;e.protocol_event('projected_capture',(row,))
    assert e.inbox['A'] is None and row['ack'] is None
    e.time=e.time+.01;e.protocol_event('projected_message_delivery',(row,))
    assert e.inbox['A'] is not None and row['ack'] is None
    e.time=e.time+.02;e.protocol_event('projected_message_ack',(row,))
    assert row['ack']['executed_at']==issued+.01 and row['ack']['completed_at']==(issued+.01)+.01
    assert row['ack']['delivered_at']==((issued+.01)+.01)+.02


def test_native_source_classes_not_mutated():
    assert m.physics.previous.original.Projection.run.__module__=='scripts.experiments.g31_ics_circulation.public_native_preference_projection'
    assert m.Projection.run is not m.physics.previous.original.Projection.run


def test_notification_owners_are_sorted_after_native_phases(engine):
    e=engine;e.schedule(2.,'owner_activation','B','test');e.schedule(2.,'owner_activation','A','test')
    rows=sorted(r for r in e.events if r[3]=='owner_activation')
    assert [r[4][0] for r in rows]==['A','B']
    assert all(r[1]>10 for r in rows)


def test_tick_and_notice_same_owner_boundary_coalesce(engine):
    e=engine;e.tick();count=len(e.client_rows)
    e.tick('A');e.tick('B')
    assert len(e.client_rows)==count and e.activated_boundaries=={(.11,'A'),(.11,'B')}
