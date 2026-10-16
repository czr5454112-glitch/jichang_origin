from copy import deepcopy
import gzip
import json
import os
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import deferred_service_tape as d


@pytest.mark.parametrize('mode', d.MODES)
def test_unicode_complete_lines_exact_reference_and_idempotent_close(tmp_path, mode):
    rows = [{'中文': '行\n尾\r😀', 'ordered': {'b': 2, 'a': 1}, 'v': -0.0}, {'x': '\u2028\u2029'}]
    original=tmp_path/'reference.gz'; candidate=tmp_path/'candidate.gz'
    with gzip.open(original,'wt',encoding='utf8',compresslevel=1) as stream:
        for row in rows: stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');stream.flush()
    sink=d.EncodedSink(candidate,mode=mode)
    for row in rows:
        text=json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n'
        assert sink.write(text)==len(text);sink.flush()
    report=sink.close(); assert sink.close()==report and report['evidence_complete']
    assert gzip.decompress(original.read_bytes())==gzip.decompress(candidate.read_bytes())
    assert report['rows']==report['flushed_rows']==2
    if mode=='spool': assert sink.spool_path.read_bytes()==gzip.decompress(candidate.read_bytes())


@pytest.mark.parametrize('mode',d.MODES)
@pytest.mark.parametrize('limit',['bytes','rows'])
def test_exact_capacity_then_overflow_keeps_prefix_unknown(tmp_path,mode,limit):
    text='{"字":1}\n'; encoded=text.replace('\n',os.linesep).encode('utf8')
    sink=d.EncodedSink(tmp_path/'capture.gz',mode=mode,max_bytes=len(encoded) if limit=='bytes' else 10000,max_rows=1 if limit=='rows' else 100)
    sink.write(text);sink.flush()
    with pytest.raises(d.CaptureFailure,match='fixed_capacity'):sink.write(text)
    with pytest.raises(d.CaptureFailure,match='sticky'):sink.flush()
    with pytest.raises(d.CaptureFailure,match='sticky'):sink.write(text)
    report=sink.close()
    assert not report['evidence_complete'] and report['failure']['failed_call_row_not_retained']
    assert report['rows']==1 and report['write_attempts']==2
    assert gzip.decompress(sink.path.read_bytes())==encoded


@pytest.mark.parametrize('mode',d.MODES)
@pytest.mark.parametrize('text',['{}','{}\n{}\n','{}\r\n',b'{}\n','\ud800\n'])
def test_bad_line_or_utf8_fails_closed(tmp_path,mode,text):
    sink=d.EncodedSink(tmp_path/'capture.gz',mode=mode)
    with pytest.raises((d.CaptureFailure,UnicodeError)):sink.write(text)
    report=sink.close()
    assert report['failure'] is not None and not report['evidence_complete']
    assert report['rows']==0 and gzip.decompress(sink.path.read_bytes())==b''


class Native:
    physical_time=1.
    def __init__(self):self.result={'nested':{'items':[{'x':'中文'}]}};self.error=None
    def protocol_command(self,*args,**kwargs):
        if self.error:raise self.error
        return self.result


@pytest.mark.parametrize('mode',d.MODES)
def test_original_invocation_alias_isolation_endpoint_and_role(tmp_path,mode):
    native=Native();tape=d.DeferredServiceTape(native,mode=mode);path=tmp_path/'capture.gz';tape.begin(path)
    args={'a':[1]};kwargs={'extra':{'b':[2]}}
    with tape.role('request'):
        result=tape.protocol_command(args,**kwargs)
    assert result is native.result
    result['nested']['items'][0]['x']='changed';args['a'].append(9);kwargs['extra']['b'].append(9)
    assert tape.role_name=='controller';tape.close()
    row=json.loads(gzip.decompress(path.read_bytes()))
    assert row['result']['nested']['items'][0]['x']=='中文'
    assert row['args']==[{'a':[1]}] and row['kwargs']=={'extra':{'b':[2]}}
    assert row['role']=='request' and row['ordinal']==0 and row['before']==row['after']==1.
    assert row['start_ns']<=row['end_ns'] and tape.capture_report['evidence_complete']
    assert d.unchanged_invocation_proof()['inherited_getattr_identical_function_and_bytecode']
    with pytest.raises(ValueError,match='unclassified_native_endpoint'):tape.unlisted()


@pytest.mark.parametrize('mode',d.MODES)
def test_native_exception_still_captured_then_original_error_rethrown(tmp_path,mode):
    native=Native();native.error=ValueError('native failed');tape=d.DeferredServiceTape(native,mode=mode);path=tmp_path/'capture.gz';tape.begin(path)
    with pytest.raises(ValueError,match='native failed'):
        try:tape.protocol_command('x')
        except BaseException:tape.close();raise
    row=json.loads(gzip.decompress(path.read_bytes()))
    assert 'error' in row and 'result' not in row and tape.capture_report['rows']==1


@pytest.mark.parametrize('mode',d.MODES)
def test_json_failure_caught_by_api_denominator_and_prefix_preserved(tmp_path,mode):
    native=Native();tape=d.DeferredServiceTape(native,mode=mode);path=tmp_path/'capture.gz';tape.begin(path)
    tape.protocol_command('ok');native.result={'nan':float('nan')}
    with pytest.raises(ValueError):
        try:tape.protocol_command('bad')
        except BaseException:tape.close();raise
    assert tape.capture_report['failure']['reason']=='api_row_denominator_mismatch'
    assert not tape.capture_report['evidence_complete'] and tape.capture_report['rows']==1 and tape.count==2
    assert len(gzip.decompress(path.read_bytes()).splitlines())==1


@pytest.mark.parametrize('mode',d.MODES)
def test_swallowed_capture_failure_cannot_become_success(tmp_path,mode):
    tape=d.DeferredServiceTape(Native(),mode=mode,max_rows=1);tape.begin(tmp_path/'capture.gz');tape.protocol_command()
    with pytest.raises(d.CaptureFailure):tape.protocol_command()
    with pytest.raises(d.CaptureFailure,match='incomplete'):tape.close()
    tape.close();assert not tape.capture_report['evidence_complete']


class ShortFile:
    def __init__(self,base):self.base=base
    def write(self,data):return self.base.write(data[:3])
    def flush(self):return self.base.flush()
    def close(self):return self.base.close()


def test_short_spool_write_preserves_incomplete_tail_unknown(tmp_path):
    sink=d.EncodedSink(tmp_path/'capture.gz',mode='spool');sink._file=ShortFile(sink._file)
    with pytest.raises(d.CaptureFailure,match='short'):sink.write('{"long":2}\n')
    report=sink.close();assert not report['evidence_complete'] and report['rows']==0
    assert sink.spool_path.read_bytes()==b'{"l'
    assert gzip.decompress(sink.path.read_bytes())==b'{"l'


def test_flush_exception_is_sticky_and_spool_is_retained(tmp_path):
    sink=d.EncodedSink(tmp_path/'capture.gz',mode='spool');raw=sink._file
    class FlushError:
        write=raw.write
        def flush(self):raise OSError('flush failed')
        close=raw.close
    sink._file=FlushError();sink.write('{}\n')
    with pytest.raises(OSError):sink.flush()
    with pytest.raises(d.CaptureFailure):sink.write('{}\n')
    with pytest.raises(OSError):sink.close()
    raw.close();assert sink.spool_path.exists() and not sink.snapshot()['evidence_complete']


@pytest.mark.parametrize('mode',d.MODES)
def test_export_failure_does_not_delete_prefix_or_claim_complete(tmp_path,mode,monkeypatch):
    sink=d.EncodedSink(tmp_path/'capture.gz',mode=mode);sink.write('{}\n');sink.flush()
    def fail(*args,**kwargs):raise OSError('gzip failed')
    monkeypatch.setattr(d.gzip,'GzipFile',fail)
    with pytest.raises(OSError):sink.close()
    assert not sink.snapshot()['evidence_complete'] and sink.snapshot()['failure']['reason']=='gzip_export_failed'
    if mode=='ram':assert sink._chunks==[('{}'+os.linesep).encode()]
    else:assert sink.spool_path.read_bytes()==('{}'+os.linesep).encode()


@pytest.mark.parametrize('field,value',[('max_bytes',True),('max_rows',0),('max_bytes',1.2),('mode','other')])
def test_invalid_limits_rejected(tmp_path,field,value):
    args={'mode':'ram'};args[field]=value
    with pytest.raises(ValueError):d.EncodedSink(tmp_path/'capture.gz',**args)


def test_spool_visible_prefix_before_close_is_not_compressed(tmp_path):
    sink=d.EncodedSink(tmp_path/'capture.gz',mode='spool');sink.write('{"x":1}\n');sink.flush()
    assert not sink.path.exists() and json.loads(sink.spool_path.read_bytes())=={'x':1}
    assert not sink.snapshot()['evidence_complete'];sink.close()


def test_no_overwrite_and_must_flush_between_api_rows(tmp_path):
    path=tmp_path/'capture.gz';path.write_bytes(b'prior')
    with pytest.raises(FileExistsError):d.EncodedSink(path,mode='ram')
    assert path.read_bytes()==b'prior'
    sink=d.EncodedSink(tmp_path/'other.gz',mode='ram');sink.write('{}\n')
    with pytest.raises(d.CaptureFailure,match='not_flushed'):sink.write('{}\n')
    assert not sink.close()['evidence_complete']
