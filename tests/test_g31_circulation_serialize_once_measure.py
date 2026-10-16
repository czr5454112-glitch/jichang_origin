from copy import deepcopy
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import measure_serialize_once_tape as m


def fixture():
    return [dict(ordinal=99,endpoint='protocol_request',args=['A','r'],kwargs={},before=1.,
        result={'nested':{'1':'value'},'last_delivered_ack':{'status':'received'}},after=1.),
        dict(ordinal=100,endpoint='advance_to',args=[2.],kwargs={'max_events':100000},before=1.,
        result={'status':'reached','horizon_complete':True,'physical_time':2.},after=2.)]


@pytest.mark.parametrize('arm',['legacy','serialize_once'])
def test_real_batch_wiring_and_ordered_readback_without_native(tmp_path,arm):
    rows=fixture();before=deepcopy(rows)
    record=m.batch(tmp_path/'batch',rows,arm)
    m.verify_batch(tmp_path/'batch',rows,record)
    assert rows==before and record['calls']==2 and record['native_calls']==0
    assert record['wall_ns']>0


@pytest.mark.parametrize('tamper',['missing_row','clock_owner','clock_outside','clock_ordinal','persisted_bytes','clock_overlap','result','sum_wall'])
def test_saved_output_clock_and_data_tampering_rejected(tmp_path,tamper):
    out=tmp_path/'batch';rows=fixture();record=m.batch(out,rows,'serialize_once')
    if tamper=='missing_row':
        p=out/'api/manifest.jsonl';p.write_text(p.read_text().splitlines()[0]+'\n')
    elif tamper in ('clock_owner','clock_outside','clock_ordinal','persisted_bytes'):
        p=out/'clocks.jsonl';clocks=[json.loads(x) for x in p.read_text().splitlines()]
        if tamper=='clock_owner':clocks[0]['endpoint']='protocol_command'
        elif tamper=='clock_outside':clocks[0]['capture_started_ns']=record['started_ns']-1
        elif tamper=='persisted_bytes':clocks[0]['persisted_bytes']+=1
        else:clocks[0]['ordinal']=9
        p.write_text(''.join(json.dumps(x)+'\n' for x in clocks))
    elif tamper=='clock_overlap':
        record['outside_call_envelopes'][1]['started_ns']=record['outside_call_envelopes'][0]['started_ns']
        m.base.write(out/'batch.json',record)
    elif tamper=='result':
        p=out/'api/000000.json.gz';row=m.base.gzread(p);row['result']['nested']['1']='tamper';m.base.gzwrite(p,row)
        p=out/'api/manifest.jsonl';items=[json.loads(x) for x in p.read_text().splitlines()]
        items[0]['sha256']=m.base.sha(out/'api/000000.json.gz');p.write_text(''.join(json.dumps(x)+'\n' for x in items))
    else:
        record['wall_ns']+=1;m.base.write(out/'batch.json',record)
    with pytest.raises(ValueError):m.verify_batch(out,rows,record)


def test_fixture_session_rejects_wrong_endpoint_arguments_and_censoring():
    s=m.FixtureSession(fixture())
    with pytest.raises(ValueError,match='fixture_invocation'):s.protocol_command('A','r')
    with pytest.raises(ValueError,match='fixture_invocation'):s.protocol_request('B','r')
    result=s.protocol_request('A','r');result['nested']['1']='mutated'
    assert s.rows[0]['result']['nested']['1']=='value'
    s.advance_to(2.,max_events=100000)
    with pytest.raises(ValueError,match='fixture_exhausted'):s.protocol_request('A','r')


def test_source_closure_includes_new_entry_tests_and_owned_job():
    paths={str(p.relative_to(m.ROOT)).replace('\\','/') for p in m.source_paths()}
    assert {'scripts/experiments/g31_ics_circulation/measure_serialize_once_tape.py',
        'scripts/experiments/g31_ics_circulation/serialize_once_low_wip_tape.py',
        'scripts/experiments/g31_ics_circulation/bounded_windows_job.py',
        'scripts/experiments/g31_ics_circulation/research_original_low_wip.py',
        'tests/test_g31_circulation_serialize_once_tape.py',
        'tests/test_g31_circulation_serialize_once_measure.py'}<=paths


def test_worker_requires_real_stdin_admission_before_batch(tmp_path,monkeypatch):
    class Wrong:
        def readline(self):return 'wrong\n'
    monkeypatch.setattr(m.sys,'stdin',Wrong())
    with pytest.raises(ValueError,match='job_admission'):m.worker(tmp_path,'expected')
    assert list(tmp_path.iterdir())==[]


def test_execute_duplicate_claim_refuses_before_verification_or_dispatch(tmp_path,monkeypatch):
    (tmp_path/'execution_claim.json').write_text('{}')
    monkeypatch.setattr(m.bounded_windows_job,'run',lambda *a,**k:pytest.fail('no dispatch'))
    with pytest.raises(FileExistsError):m.execute(tmp_path,'x')


def test_prelaunch_identity_failure_is_preserved_without_dispatch(tmp_path,monkeypatch):
    (tmp_path/'plan.json').write_text('{}')
    monkeypatch.setattr(m.bounded_windows_job,'run',lambda *a,**k:pytest.fail('no dispatch'))
    assert m.execute(tmp_path,'wrong')==1
    receipt=m.base.read(tmp_path/'launch_receipt.json')
    assert receipt['status']=='unknown_failed_or_timeout' and 'plan_identity' in receipt['error']
    assert receipt['process'] is None and not (tmp_path/'result.json').exists()
    assert (tmp_path/'execution_claim.json').exists()


def test_fixed_ABBA_and_last_eight_domain_are_not_configurable():
    assert m.ARMS==('legacy','serialize_once','serialize_once','legacy') and m.LIMIT==120.
    review=m.base.read(m.PARTIAL_REVIEW)
    assert m.base.sha(m.PARTIAL_REVIEW)==m.PARTIAL_SHA
    assert [r['ordinal'] for r in review['complete_tail_rows_individually_hashed_and_decoded']]==list(range(27210,27218))
    assert review['unmanifested_files'][0]['path']=='027218.json.gz'
