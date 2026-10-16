import copy
import gzip
import hashlib
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_delivered_context as m

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/live_obligation_unloading_native_prepare_001'


@pytest.fixture(scope='module')
def raw():
    path=SOURCE/'mechanism/vector_00.json.gz'
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='25bdbea40ae8ccb0bab751ea6f837021d3f8d03db259d7ce56df982a9f95acd1'
    return json.loads(gzip.decompress(path.read_bytes()))


def args(raw,owner='A'):
    row=raw['initial_owners'][owner];ep=copy.deepcopy(row['raw_endpoints'])
    req=next(c['request'] for c in raw['calls'] if c['request']['request_id']==ep['command']['request_id'])
    return {**ep,'own_request':copy.deepcopy(req)}


def test_actual_initial_data_revalidated_without_authority(raw):
    for owner in ('A','B'):
        c=m.initial_context(**args(raw,owner));assert type(c) is m.SuppliedContext
        v=m.revalidate(c);assert v['status']=='conditional_validated_data'
        assert not c.audit_copy()['native_delivery_verified']
        bundle=m.initial_projection_bundle(c)
        assert bundle['now']==.11 and len(bundle['jobs'])==5 and len(bundle['trays'])==3
        assert bundle['trays']['P']['load_end']==3.


@pytest.mark.parametrize('change',[
    lambda a:a['own_request'].update(owner_id='B'),
    lambda a:a['own_request'].update(request_id='fabricated'),
    lambda a:a['command'].update(kind='route'),
    lambda a:a['received'].clear(),
    lambda a:a['received'].append(copy.deepcopy(a['received'][0])),
    lambda a:a['view']['trays'][0].update(generation=99),
    lambda a:a['command']['last_delivered_ack'].update(delivered_at=99.),
    lambda a:a['view']['node_contracts'][0].update(occupancy=99),
    lambda a:a['received'][0]['capture']['coverage'].update(tray_ids=[]),
])
def test_actual_initial_negative(raw,change):
    a=args(raw);change(a);assert type(m.initial_context(**a)) is dict


def test_context_integrity_and_plain_flags_never_capability(raw):
    c=m.initial_context(**args(raw));assert m.revalidate(c.audit_copy())['status']=='unknown'
    c._payload=c._payload.replace('"owner":"A"','"owner":"B"',1)
    assert m.revalidate(c)['status']=='unknown'


def test_actual_native_binding_tuples_permitted_only_tables(raw):
    a=args(raw)
    for key in ('node_records','edge_records'):a['view'][key]=[tuple(row) for row in a['view'][key]]
    assert type(m.initial_context(**a)) is m.SuppliedContext
    a['view']['trays']=tuple(a['view']['trays'])
    assert m.initial_context(**a)['status']=='unknown'


def later_args(raw,owner):
    entry=raw['collection_attempts'][owner][-1];p=entry['collection'];ep=entry['information']['raw_endpoints']
    return {**copy.deepcopy(ep),'retained':copy.deepcopy(raw['retained_ledgers'][owner]),
        'own_calls':copy.deepcopy([c for c in raw['calls'][:entry['predecision_call_prefix_count']] if c['request']['owner_id']==owner]),
        'phase':entry['phase'],'own_request_id':p['request_id'],'peer_message_id':p['peer_message'],
        'collection_started_at':p['at'],'policy_quiet_since':p['policy_quiet_since']}


def test_actual_later_data_guards_preserved(raw):
    for owner in ('A','B'):
        c=m.later_context(**later_args(raw,owner));assert type(c) is m.SuppliedContext
        assert m.revalidate(c)['status']=='conditional_validated_later_v3_data'
        assert m.initial_projection_bundle(c)['status']=='unknown'


@pytest.mark.parametrize('change',[
    lambda a:a['own_calls'].clear(),
    lambda a:a.update(peer_message_id='wrong'),
    lambda a:a.update(collection_started_at=a['view']['now']),
    lambda a:a['retained']['contracts'].pop('loaded'),
    lambda a:a['view']['trays'][0].update(generation=99),
    lambda a:a['command']['last_delivered_ack'].update(delivered_at=99.),
])
def test_actual_later_negative(raw,change):
    a=later_args(raw,'B');change(a);assert m.later_context(**a)['status']=='unknown'


def test_foreign_call_is_not_silently_filtered(raw):
    a=later_args(raw,'B');a['own_calls'].append(next(c for c in raw['calls'] if c['request']['owner_id']=='A'))
    assert m.later_context(**a)['status']=='unknown'


def test_nonfinite_custom_payload_rejected(raw):
    a=args(raw);a['own_request']['expiry']=float('nan')
    assert m.initial_context(**a)['status']=='unknown'
    class Fake(dict):pass
    a=args(raw);a['own_request']=Fake(a['own_request'])
    assert m.initial_context(**a)['status']=='unknown'
