"""Tiny fabricated rows only; strict byte-oracle/denominator/clock guards."""
import copy
import gzip
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import measure_planning_v2_batched_digest_cost as m
from test_g31_circulation_planning_v2_batched_digest import body


def fixture(ordinal=27212):
    capture=body()
    env={'schema':'g31.planning_snapshot.v2','kind':'planning_snapshot_v2',
        'digest_format':'g31.planning_capture_digest.v2','capture':capture,
        'payload_sha256':m.base.original.capture_digest_v2(capture)}
    row={'ordinal':ordinal,'endpoint':'protocol_planning_snapshots_v2','args':['B'],'kwargs':{},
        'before':10.,'result':[env],'after':10.}
    raw=m.encoded(row);packed=gzip.compress(raw,mtime=0)
    item={'side':'new','ordinal':ordinal,'endpoint':row['endpoint'],'sha256':m.base.sha_bytes(packed),
        'bytes':len(packed),'source':'unused','file':f'new_{ordinal:06d}.json.gz'}
    _,meta=m.base.decode_fixture(packed,item)
    return row,meta,item,packed


def metadata():return [fixture(o)[1] for o in (27212,27215)]


def records(metadata, clock=1):
    rows=[];batches=[]
    for meta in metadata:
        for batch,arm in enumerate(m.ARMS):
            begin=clock;clock+=1
            for repeat in range(4):
                e=meta['envelopes'][0]
                rows.append({'ordinal':meta['ordinal'],'batch':batch,'arm':arm,'repeat':repeat,
                    'envelope_ordinal':0,'started_ns':clock,'digest_started_ns':clock+1,
                    'digest_finished_ns':clock+2,'checked_ns':clock+3,'digest_ns':1,
                    'guard_and_check_ns':2,'digest':e['payload_sha256'],'body_sha256':e['body_sha256'],
                    'guards_passed':True});clock+=4
            batches.append({'ordinal':meta['ordinal'],'batch':batch,'arm':arm,
                'started_ns':begin,'finished_ns':clock,'whole_ns':clock-begin});clock+=1
    return rows,batches


def make_oracles(path):
    result=[];metas=[]
    for o in (27212,27215):
        row,meta,_,_=fixture(o);metas.append(meta)
        result.append(m.oracle(path,row['result'][0],meta['owner'],meta['envelopes'][0],o))
    return result,metas


def test_fixed_32_plus_four_encoder_denominator_and_no_profiles():
    counts=m.counts_for(metadata())
    assert counts=={'query_rows':2,'envelopes':2,'batches':8,'repetitions_per_batch':4,
        'measured_digest_calls':32,'A_digest_calls':16,'B_digest_calls':16,
        'additional_complete_byte_encoder_calls':4,'total_typed_encoder_runs':36,'profiles':0}


@pytest.mark.parametrize('kind',['omit','duplicate','order','extra_envelope','bool_count'])
def test_metadata_fixed_domain_rejects(kind):
    meta=metadata()
    if kind=='omit':meta.pop()
    elif kind=='duplicate':meta[1]=copy.deepcopy(meta[0])
    elif kind=='order':meta.reverse()
    elif kind=='extra_envelope':meta[0]['envelope_count']=2;meta[0]['envelopes']*=2
    else:meta[0]['envelope_count']=True
    with pytest.raises(ValueError):m.counts_for(meta)


def test_all_complete_bytes_saved_and_reread(tmp_path):
    oracles,meta=make_oracles(tmp_path)
    assert m.check_oracles(tmp_path,oracles,meta)=={'complete_byte_pairs':2,'encoder_runs':4,'all_full_bytes_equal':True}
    for row in oracles:
        assert (tmp_path/row['files']['A']['name']).read_bytes()==(tmp_path/row['files']['B']['name']).read_bytes()


@pytest.mark.parametrize('kind',['missing','duplicate','order','bool_index','bool_clock','clock_order','duration',
    'fallback','body_hash','file_name','byte_size','byte_content','not_equal_flag'])
def test_oracle_tamper_rejected(tmp_path,kind):
    rows,meta=make_oracles(tmp_path)
    if kind=='missing':rows.pop()
    elif kind=='duplicate':rows.append(copy.deepcopy(rows[0]))
    elif kind=='order':rows.reverse()
    elif kind=='bool_index':rows[0]['envelope_ordinal']=False
    elif kind=='bool_clock':rows[0]['started_ns']=True
    elif kind=='clock_order':rows[0]['B_started_ns']=rows[0]['A_started_ns']-1
    elif kind=='duration':rows[0]['whole_ns']+=1
    elif kind=='fallback':rows[0]['candidate_fast_path']=False
    elif kind=='body_hash':rows[0]['body_sha256']='0'*64
    elif kind=='file_name':rows[0]['files']['B']['name']='../outside'
    elif kind=='byte_size':rows[0]['files']['B']['bytes']=True
    elif kind=='byte_content':
        path=tmp_path/rows[0]['files']['B']['name'];path.write_bytes(path.read_bytes()+b'x')
    else:rows[0]['complete_bytes_equal']=False
    with pytest.raises(ValueError):m.check_oracles(tmp_path,rows,meta)


def test_oracle_requires_complete_bytes_even_if_hash_is_stubbed(tmp_path,monkeypatch):
    row,meta,_,_=fixture()
    original_bytes=m.candidate.reference_bytes_v2(row['result'][0]['capture'])
    different_bytes=b'different full bytes';original_sha=m.base.sha_bytes
    monkeypatch.setattr(m.candidate,'_fast_buffer',lambda *_:different_bytes)
    monkeypatch.setattr(m.base,'sha_bytes',lambda data:meta['envelopes'][0]['payload_sha256']
        if data in (original_bytes,different_bytes) else original_sha(data))
    with pytest.raises(ValueError,match='complete_typed_bytes_differ'):
        m.oracle(tmp_path,row['result'][0],meta['owner'],meta['envelopes'][0],27212)
    assert not list(tmp_path.iterdir())


def test_oracle_exactly_two_encodings_without_fallback(tmp_path,monkeypatch):
    row,meta,_,_=fixture();calls=[]
    reference=m.candidate.reference_bytes_v2;fast=m.candidate._fast_buffer
    monkeypatch.setattr(m.candidate,'reference_bytes_v2',lambda value:(calls.append('A'),reference(value))[1])
    monkeypatch.setattr(m.candidate,'_fast_buffer',lambda value:(calls.append('B'),fast(value))[1])
    monkeypatch.setattr(m.candidate,'capture_digest_v2',lambda *_:pytest.fail('no digest oracle'))
    m.oracle(tmp_path,row['result'][0],meta['owner'],meta['envelopes'][0],27212)
    assert calls==['A','B']


@pytest.mark.parametrize('kind',['missing','duplicate','order','bool_index','bool_clock','backward',
    'duration','guard_duration','digest','body_hash','guard_false','missing_batch','batch_span','batch_bool'])
def test_measurement_tamper_rejected(kind):
    meta=metadata();rows,batches=records(meta)
    if kind=='missing':rows.pop()
    elif kind=='duplicate':rows.append(copy.deepcopy(rows[0]))
    elif kind=='order':rows[0],rows[1]=rows[1],rows[0]
    elif kind=='bool_index':rows[0]['envelope_ordinal']=False
    elif kind=='bool_clock':rows[0]['started_ns']=True
    elif kind=='backward':rows[0]['digest_finished_ns']=0
    elif kind=='duration':rows[0]['digest_ns']+=1
    elif kind=='guard_duration':rows[0]['guard_and_check_ns']+=1
    elif kind=='digest':rows[0]['digest']='0'*64
    elif kind=='body_hash':rows[0]['body_sha256']='0'*64
    elif kind=='guard_false':rows[0]['guards_passed']=False
    elif kind=='missing_batch':batches.pop()
    elif kind=='batch_span':batches[0]['started_ns']=batches[0]['finished_ns']
    else:batches[0]['whole_ns']=True
    with pytest.raises(ValueError):m.check_records(rows,batches,meta)


def test_original_and_candidate_use_same_measured_envelope_with_preflight_inside(monkeypatch):
    row,meta,_,_=fixture();events=[];times=iter(range(10,100))
    monkeypatch.setattr(m.time,'perf_counter_ns',lambda:(events.append('clock'),next(times))[1])
    old=m.candidate._builtin_tree
    monkeypatch.setattr(m.candidate,'_builtin_tree',lambda value:(events.append('B_preflight'),old(value))[1])
    a=m.measure_one(row['result'][0],meta['owner'],meta['envelopes'][0],'A')
    assert events==['clock']*4
    events.clear();b=m.measure_one(row['result'][0],meta['owner'],meta['envelopes'][0],'B')
    assert events==['clock','clock','B_preflight','clock','clock']
    assert a['digest']==b['digest'] and a['guards_passed'] and b['guards_passed']


@pytest.mark.parametrize('kind',['wrong_digest','mutation','resource','unsupported'])
def test_candidate_failures_never_become_completed_samples(monkeypatch,kind):
    row,meta,_,_=fixture()
    if kind=='wrong_digest':fn=lambda _: '0'*64
    elif kind=='mutation':
        def fn(value):value['local_capture']['valid_until']+=1;return meta['envelopes'][0]['payload_sha256']
    elif kind=='resource':
        def fn(_):raise MemoryError('retained')
    else:
        def fn(_):raise m.candidate._Unsupported()
    monkeypatch.setattr(m,'_CANDIDATE',fn)
    with pytest.raises((ValueError,MemoryError,m.candidate._Unsupported)):
        m.measure_one(row['result'][0],meta['owner'],meta['envelopes'][0],'B')


def saved(tmp_path,monkeypatch):
    oracles,meta=make_oracles(tmp_path);rows,batches=records(meta,oracles[-1]['finished_ns']+100)
    plan={'fixture_metadata':meta};m.write(tmp_path/'plan.json',plan);m.write(tmp_path/'oracles.json',oracles)
    result={'schema':m.SCHEMA+'.result','status':'completed_fixed_batched_comparison',
        'plan_sha256':m.sha(tmp_path/'plan.json'),'records':rows,'batches':batches,'oracles':oracles,
        'summary':m.check_records(rows,batches,meta),'GC_enabled':True}
    m.write(tmp_path/'result.json',result)
    (tmp_path/'measurements.jsonl').write_bytes(b''.join(m.encoded(row)+b'\n' for row in rows))
    monkeypatch.setattr(m,'verify_pins',lambda *a,**k:None)
    return plan,result


def test_saved_readback_reuses_full_bytes_not_encoder(tmp_path,monkeypatch):
    plan,_=saved(tmp_path,monkeypatch)
    monkeypatch.setattr(m.candidate,'_fast_buffer',lambda *_:pytest.fail('no saved re-encoding'))
    monkeypatch.setattr(m.candidate,'reference_bytes_v2',lambda *_:pytest.fail('no saved re-encoding'))
    report=m.verify_saved(tmp_path,plan)
    assert report['status']=='passed_saved_complete_bytes_and_measurements'
    assert report['byte_oracles']['complete_byte_pairs']==2 and report['extra_encoder_runs_in_saved_review']==0


@pytest.mark.parametrize('kind',['journal_missing','result_summary','oracle_journal','oracle_after_measurement','GC'])
def test_saved_whole_binding_negatives(tmp_path,monkeypatch,kind):
    plan,result=saved(tmp_path,monkeypatch)
    if kind=='journal_missing':
        path=tmp_path/'measurements.jsonl';path.write_bytes(b'\n'.join(path.read_bytes().splitlines()[:-1])+b'\n')
    elif kind=='result_summary':result['summary']['counts']['total_typed_encoder_runs']=32
    elif kind=='oracle_journal':
        path=tmp_path/'oracles.json';value=m.loads(path.read_bytes());value.reverse();path.write_bytes(m.encoded(value))
    elif kind=='oracle_after_measurement':
        # Keep internally valid record clocks, but move both oracle intervals
        # beyond the first measurement. Saved check must reject chronology.
        delta=result['batches'][-1]['finished_ns']+100
        for o in result['oracles']:
            for key in ('started_ns','A_started_ns','A_finished_ns','B_started_ns','B_finished_ns','finished_ns'):o[key]+=delta
        (tmp_path/'oracles.json').write_bytes(m.encoded(result['oracles']))
    else:result['GC_enabled']=False
    (tmp_path/'result.json').write_bytes(m.encoded(result))
    with pytest.raises(ValueError):m.verify_saved(tmp_path,plan)


def test_prepare_copies_frozen_compressed_metadata_without_decoding_or_digest(tmp_path,monkeypatch):
    folder=tmp_path/'prepare';folder.mkdir();pure=tmp_path/'pure';pure.mkdir()
    items=[];meta=[]
    for o in (27212,27215):
        _,metadata,item,packed=fixture(o);path=tmp_path/f'{o}.gz';path.write_bytes(packed)
        item['source']=str(path);items.append(item);meta.append(metadata)
    source={'synthetic.py':b'# synthetic source only\n'}
    monkeypatch.setattr(m,'source_files',lambda:source)
    monkeypatch.setattr(m,'reference_plan',lambda:{'files':items,'fixture_metadata':meta})
    monkeypatch.setattr(m,'proof',lambda:{'synthetic_binding':True})
    monkeypatch.setattr(m,'verify_pins',lambda *a,**k:None)
    monkeypatch.setattr(m.base,'decode_fixture',lambda *a:pytest.fail('no preparation decode'))
    monkeypatch.setattr(m.candidate,'_fast_buffer',lambda *a:pytest.fail('no preparation encode'))
    monkeypatch.setattr(m,'_ORIGINAL',lambda *a:pytest.fail('no preparation digest'))
    xml='<testsuites><testsuite>'+''.join('<testcase name="x" />' for _ in range(m.PURE_TESTS))+'</testsuite></testsuites>'
    (pure/'tests.xml').write_text(xml,encoding='utf8')
    m.write(pure/'receipt.json',{'status':'passed','source_changed':[],'real_raw_reads':0,'benchmark_runs':0,
        'XML_sha256':m.sha(pure/'tests.xml'),'source_sha256':{k:m.base.sha_bytes(v) for k,v in source.items()}})
    m.prepare(folder,pure)
    plan=m.loads((folder/'plan.json').read_bytes())
    assert plan['preparation']['raw_decodes']==plan['preparation']['digest_calls']==0
    assert plan['counts']['total_typed_encoder_runs']==36
    ready=m.loads((folder/'ready.json').read_bytes())
    assert ready['execute_command'][0]==m.sys.executable and not ready['performance_executed']
