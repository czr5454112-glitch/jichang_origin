"""Tiny synthetic functional fixtures; never calls the original digest."""
import copy
import gc
import gzip
import json
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import measure_planning_v2_digest_v2 as m


def envelope(identity='opaque'):
    local = {'schema':'g31.planning_capture.v1','message_id':identity,'source_owner':'domestic',
        'target_owner':'international','captured_at':10.,'jobs':[],'trays':[],'nodes':[],'known_faults':[]}
    extension = {'schema':'g31.planning_extension.v2','source_owner':'domestic',
        'captured_at':10.,'terminal_receipts':[],'submitted_physical_actions':[]}
    return {'schema':'g31.planning_snapshot.v2','kind':'planning_snapshot_v2',
        'digest_format':'g31.planning_capture_digest.v2','capture':{
        'schema':'g31.planning_capture.v2','local_capture':local,'extension':extension},'payload_sha256':'0'*64}


def fixture(ordinal=27212, n=1):
    row = {'ordinal':ordinal,'endpoint':'protocol_planning_snapshots_v2','args':['international'],
        'kwargs':{},'before':10.,'result':[envelope(str(i)) for i in range(n)],'after':10.}
    raw = json.dumps(row,ensure_ascii=False,allow_nan=False).encode('utf8')
    compressed = gzip.compress(raw,mtime=0)
    item = {'side':'new','ordinal':ordinal,'endpoint':row['endpoint'],'sha256':m.sha_bytes(compressed),
        'bytes':len(compressed),'source':'unused','file':f'new_{ordinal:06d}.json.gz'}
    return row, raw, compressed, item


def metadata():
    return [m.decode_fixture(fixture(o)[2],fixture(o)[3])[1] for o in m.ORDINALS]


def saved():
    metas = metadata(); rows = []; batches = []; clock = 1
    for meta in metas:
        for b, arm in enumerate(m.ARMS):
            begin = clock; clock += 1
            for repeat in range(m.REPETITIONS):
                for index, env in enumerate(meta['envelopes']):
                    rows.append({'ordinal':meta['ordinal'],'batch':b,'arm':arm,'repeat':repeat,
                        'envelope_ordinal':index,'started_ns':clock,'digest_started_ns':clock+1,
                        'digest_finished_ns':clock+2,'checked_ns':clock+3,'digest_ns':1,'guard_and_check_ns':2,
                        'digest':env['payload_sha256'],'body_sha256':env['body_sha256'],'guards_passed':True})
                    clock += 4
            batches.append({'ordinal':meta['ordinal'],'batch':b,'arm':arm,'started_ns':begin,
                'finished_ns':clock,'whole_ns':clock-begin,
                'profile_file':f"profile_{meta['ordinal']}_{b}.pstats" if arm=='B' else None})
            clock += 1
    return rows,batches,metas


def test_decode_all_envelopes_order_raw_compressed_and_no_digest(monkeypatch):
    monkeypatch.setattr(m,'_DIGEST',lambda *_:pytest.fail('preparation must not run digest'))
    row,raw,compressed,item = fixture(n=2)
    decoded,meta = m.decode_fixture(compressed,item)
    assert m.encoded(decoded)==m.encoded(row)
    assert meta['raw_sha256']==m.sha_bytes(raw) and meta['compressed_sha256']==m.sha_bytes(compressed)
    assert meta['envelope_count']==2 and [e['message_id'] for e in meta['envelopes']]==['0','1']
    assert meta['digest_calls_during_preparation']==0


@pytest.mark.parametrize('kind',['gzip_cap','raw_cap','envelope_cap','zero_envelopes'])
def test_fixed_caps_fail_closed(monkeypatch,kind):
    _,_,compressed,item=fixture(n=2 if kind=='envelope_cap' else (0 if kind=='zero_envelopes' else 1))
    if kind=='gzip_cap':monkeypatch.setattr(m,'MAX_COMPRESSED',len(compressed)-1)
    elif kind=='raw_cap':monkeypatch.setattr(m,'MAX_RAW',10)
    elif kind=='envelope_cap':monkeypatch.setattr(m,'MAX_ENVELOPES',1)
    with pytest.raises(ValueError):m.decode_fixture(compressed,item)


@pytest.mark.parametrize('kind',['ordinal','ordinal_bool','endpoint','args','kwargs','error','hash','size',
                               'owner','schema','digest','extension_time_type'])
def test_bound_row_and_envelope_tamper_rejected(kind):
    row,_,compressed,item=fixture()
    if kind=='hash':item['sha256']='f'*64
    elif kind=='size':item['bytes']+=1
    else:
        if kind=='ordinal':row['ordinal']=9
        elif kind=='ordinal_bool':row['ordinal']=True
        elif kind=='endpoint':row['endpoint']='unrelated'
        elif kind=='args':row['args']=[]
        elif kind=='kwargs':row['kwargs']={'extra':1}
        elif kind=='error':row['error']='retained query error'
        elif kind=='owner':row['result'][0]['capture']['local_capture']['target_owner']='foreign'
        elif kind=='schema':row['result'][0]['schema']='wrong'
        elif kind=='digest':row['result'][0]['payload_sha256']='x'*64
        elif kind=='extension_time_type':row['result'][0]['capture']['extension']['captured_at']=10
        compressed=gzip.compress(json.dumps(row).encode(),mtime=0)
        item.update(sha256=m.sha_bytes(compressed),bytes=len(compressed))
    with pytest.raises(ValueError):m.decode_fixture(compressed,item)


@pytest.mark.parametrize('value',[float('nan'),float('inf'),(1,),{0:'bad'},object()])
def test_closed_json_domain(value):
    with pytest.raises(ValueError):m.encoded(value)


def test_duplicate_keys_cycle_surrogate_and_signed_zero():
    with pytest.raises(ValueError):m.loads(b'{"x":1,"x":2}')
    cycle=[];cycle.append(cycle)
    with pytest.raises(ValueError):m.encoded(cycle)
    with pytest.raises(UnicodeEncodeError):m.encoded('\ud800')
    assert m.encoded(0.)!=m.encoded(-0.) and m.encoded(1)!=m.encoded(1.)!=m.encoded(True)
    assert m.encoded({'a':1,'b':2})!=m.encoded({'b':2,'a':1})


@pytest.mark.parametrize('kind',['missing','duplicate','reorder','wrong_endpoint'])
def test_fixed_prior_selection(kind):
    rows=[fixture(o)[3] for o in m.ORDINALS]
    if kind=='missing':rows.pop()
    elif kind=='duplicate':rows.append(copy.deepcopy(rows[0]))
    elif kind=='reorder':rows.reverse()
    else:rows[0]['endpoint']='wrong'
    with pytest.raises(ValueError):m.select_inputs({'files':rows})


def test_selection_ignores_only_predeclared_other_rows():
    selected=[fixture(o)[3] for o in m.ORDINALS]
    old={**selected[0],'side':'old'};extra={**selected[0],'ordinal':27213}
    assert m.select_inputs({'files':[old,selected[0],extra,selected[1]]})==selected


@pytest.mark.parametrize('kind',['bool','zero','wrong_count','wrong_order'])
def test_counts_reject_changed_denominators(kind):
    metas=metadata()
    if kind=='bool':metas[0]['envelope_count']=True
    elif kind=='zero':metas[0]['envelope_count']=0
    elif kind=='wrong_count':metas[0]['envelope_count']=2
    else:metas.reverse()
    with pytest.raises(ValueError):m.counts_for(metas)


def test_complete_measurement_schedule_and_no_optimization_claim():
    rows,batches,metas=saved(); summary=m.check_records(rows,batches,metas)
    assert len(rows)==32 and len(batches)==8 and summary['counts']['A_digest_calls']==16
    assert summary['counts']['B_digest_calls']==16 and summary['counts']['profile_batches']==4
    assert 'not an optimized' in summary['interpretation']


@pytest.mark.parametrize('kind',['missing_row','duplicate_row','reordered','bool_index','bool_clock',
    'duration','wrong_digest','wrong_body','guard_false','missing_batch','batch_containment','profile_missing'])
def test_saved_denominators_order_clocks_and_values_reject(kind):
    rows,batches,metas=saved()
    if kind=='missing_row':rows.pop()
    elif kind=='duplicate_row':rows.append(copy.deepcopy(rows[0]))
    elif kind=='reordered':rows[0],rows[1]=rows[1],rows[0]
    elif kind=='bool_index':rows[0]['batch']=False
    elif kind=='bool_clock':rows[0]['started_ns']=True
    elif kind=='duration':rows[0]['digest_ns']=2
    elif kind=='wrong_digest':rows[0]['digest']='f'*64
    elif kind=='wrong_body':rows[0]['body_sha256']='f'*64
    elif kind=='guard_false':rows[0]['guards_passed']=False
    elif kind=='missing_batch':batches.pop()
    elif kind=='batch_containment':batches[0]['started_ns']=rows[0]['started_ns']+1
    elif kind=='profile_missing':batches[1]['profile_file']=None
    with pytest.raises(ValueError):m.check_records(rows,batches,metas)


@pytest.mark.parametrize('arm',['A','B'])
def test_measurement_uses_same_original_callable_with_guard_return_and_default_gc(monkeypatch,arm):
    env=envelope();meta=m.envelope_metadata(env,'international',0);seen=[]
    def fake(body):seen.append(body);return '0'*64
    monkeypatch.setattr(m,'_DIGEST',fake)
    class Profile:
        def runcall(self,fn,*args):
            assert fn is fake;return fn(*args)
    enabled=gc.isenabled();before=m.encoded(env)
    result=m.measure_one(env,'international',meta,arm,Profile() if arm=='B' else None)
    assert seen==[env['capture']] and result['digest']=='0'*64 and result['guards_passed']
    assert m.encoded(env)==before and gc.isenabled()==enabled


@pytest.mark.parametrize('kind',['return_mismatch','exception','mutation'])
def test_measurement_failure_not_completed(monkeypatch,kind):
    env=envelope();meta=m.envelope_metadata(env,'international',0)
    def fake(body):
        if kind=='exception':raise MemoryError('resource error')
        if kind=='mutation':body['new']=1
        return 'f'*64 if kind=='return_mismatch' else '0'*64
    monkeypatch.setattr(m,'_DIGEST',fake)
    with pytest.raises((ValueError,MemoryError)):m.measure_one(env,'international',meta,'A')


@pytest.mark.parametrize('kind',['valid','missing','wrong_count','bad_time'])
def test_profile_contains_both_original_functions_exact_call_counts(monkeypatch,kind):
    keys=[(fn.__code__.co_filename,fn.__code__.co_firstlineno,fn.__name__) for fn in (m._DIGEST,m._WRITER)]
    stats={k:(4,4,.001,.002,{}) for k in keys}
    if kind=='missing':del stats[keys[0]]
    elif kind=='wrong_count':stats[keys[1]]=(3,3,.001,.002,{})
    elif kind=='bad_time':stats[keys[0]]=(4,4,float('nan'),.002,{})
    monkeypatch.setattr(m.pstats,'Stats',lambda path:SimpleNamespace(stats=stats))
    if kind=='valid':assert set(m.check_profile('not_read',4))=={'capture_digest_v2','_write_local_capture'}
    else:
        with pytest.raises(ValueError):m.check_profile('not_read',4)


def test_function_identity_proof_rejects_drift(monkeypatch):
    assert m.source_proof()['original_digest_code']
    monkeypatch.setattr(m.original,'capture_digest_v2',lambda body:'0'*64)
    with pytest.raises(ValueError):m.source_proof()


def test_artifact_short_write_and_existing_file_preserved(tmp_path,monkeypatch):
    path=tmp_path/'data.json';m.write(path,{'x':1});before=path.read_bytes()
    with pytest.raises(FileExistsError):m.write(path,{'x':2})
    assert path.read_bytes()==before
    monkeypatch.setattr(m,'MAX_ARTIFACT',2)
    with pytest.raises(ValueError):m.write(tmp_path/'overflow.json',{'x':1})


def test_real_declared_extension_schema_matches_frozen_contract():
    from scripts.experiments.g31_ics_circulation import planning_capture_v2_contract as contract
    env=envelope()
    assert env['capture']['extension']['schema']==contract.SCHEMA=='g31.planning_extension.v2'
    assert m.envelope_metadata(env,'international',0)['envelope_ordinal']==0


def test_previous_synthetic_extension_schema_is_rejected():
    env=envelope();env['capture']['extension']['schema']='g31.planning_capture_extension.v2'
    with pytest.raises(ValueError,match='capture_schema'):m.envelope_metadata(env,'international',0)
