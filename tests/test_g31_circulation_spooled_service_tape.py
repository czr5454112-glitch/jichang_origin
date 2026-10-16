import gzip
import json
import os
import pytest
from scripts.experiments.g31_ics_circulation import spooled_service_tape as d


class Native:
    physical_time = 1.
    def __init__(self): self.result = {'nested': {'items': ['中文😀']}}; self.error = None
    def protocol_command(self, *args, **kwargs):
        if self.error is not None: raise self.error
        return self.result


class FailingHandle:
    def __init__(self, raw, flush_error=None, close_error=None):
        self.raw, self.flush_error, self.close_error = raw, flush_error, close_error
        self.close_calls = 0
    def write(self, value): return self.raw.write(value)
    def flush(self):
        if self.flush_error: raise self.flush_error
        self.raw.flush()
    def close(self):
        self.close_calls += 1; self.raw.close()
        if self.close_error: raise self.close_error


@pytest.mark.parametrize('second_error', [False, True])
def test_final_flush_always_closes_and_keeps_original_exception(tmp_path, second_error):
    sink = d.SpoolSink(tmp_path/'capture.gz'); sink.write('{}\n'); sink.flush()
    original = OSError('original final flush')
    handle = FailingHandle(sink._file, original, OSError('secondary close') if second_error else None)
    sink._file = handle
    with pytest.raises(OSError) as caught: sink.close()
    assert caught.value is original and handle.close_calls == 1 and handle.raw.closed
    assert sink._file is None and sink.closed and not sink.snapshot()['evidence_complete']
    assert sink.snapshot()['failure']['reason'] == 'spool_final_flush_failed'
    assert not sink.path.exists() and sink.spool_path.read_bytes() == ('{}'+os.linesep).encode()
    assert not sink.close()['evidence_complete']


def test_close_only_error_is_primary_and_unknown(tmp_path):
    sink = d.SpoolSink(tmp_path/'capture.gz'); original = OSError('close failed')
    handle = FailingHandle(sink._file, close_error=original); sink._file = handle
    with pytest.raises(OSError) as caught: sink.close()
    assert caught.value is original and handle.close_calls == 1
    assert sink.snapshot()['failure']['reason'] == 'spool_final_close_failed'
    assert not sink.snapshot()['evidence_complete']


def test_cleanup_error_does_not_replace_active_native_exception(tmp_path):
    native = Native(); native.error = ValueError('native primary')
    tape = d.SpoolServiceTape(native); tape.begin(tmp_path/'capture.gz')
    original_handle = tape.stream._file
    with pytest.raises(ValueError) as caught:
        try: tape.protocol_command('r')
        except BaseException:
            tape.stream._file = FailingHandle(original_handle, OSError('cleanup flush'), OSError('cleanup close'))
            tape.close(); raise
    assert caught.value is native.error and original_handle.closed
    report = json.loads((tmp_path/'diagnostic_capture.json').read_text('utf8'))
    assert not report['evidence_complete'] and report['original_inflight_error'] == repr(native.error)
    assert report['close_error'] == "OSError('cleanup flush')" and tape.stream is None


def test_normal_cleanup_error_raises_and_receipt_is_unknown(tmp_path):
    tape = d.SpoolServiceTape(Native()); tape.begin(tmp_path/'capture.gz'); tape.protocol_command()
    original = OSError('last flush'); handle = FailingHandle(tape.stream._file, original); tape.stream._file = handle
    with pytest.raises(OSError) as caught: tape.close()
    assert caught.value is original and handle.raw.closed
    assert not tape.capture_report['evidence_complete']; tape.close()


def test_unchanged_invocation_and_isolation_and_utf8_bytes(tmp_path):
    native = Native(); tape = d.SpoolServiceTape(native); path = tmp_path/'capture.gz'; tape.begin(path)
    args = {'x': [1]}
    with tape.role('request'): result = tape.protocol_command(args, name='行\n尾\r😀')
    result['nested']['items'].append('mutation'); args['x'].append(2)
    tape.close(); row = json.loads(gzip.decompress(path.read_bytes()))
    assert row['args'] == [{'x': [1]}] and row['result'] == {'nested': {'items': ['中文😀']}}
    assert row['role'] == 'request' and tape.role_name == 'controller'
    encoded = gzip.decompress(path.read_bytes())
    assert encoded == PathBytes(path) and encoded.endswith(os.linesep.encode())
    assert d.unchanged_invocation_proof()['inherited_getattr_identical_function_and_bytecode']
    assert tape.capture_report['evidence_complete'] and tape.capture_report['max_bytes'] == 268435456
    assert tape.capture_report['max_rows'] == 160000


def PathBytes(path): return path.with_name(path.name+'.spool.jsonl').read_bytes()


@pytest.mark.parametrize('text', ['{}', '{}\n{}\n', '{}\r\n', b'{}\n', '\ud800\n'])
def test_bad_utf8_or_line_is_unknown(tmp_path, text):
    sink = d.SpoolSink(tmp_path/'capture.gz')
    with pytest.raises((d.CaptureFailure, UnicodeError)): sink.write(text)
    assert not sink.close()['evidence_complete']


@pytest.mark.parametrize('kind', ['rows', 'bytes'])
def test_fixed_limit_overflow_preserves_prefix_unknown(tmp_path, kind):
    sink = d.SpoolSink(tmp_path/'capture.gz'); sink.write('{}\n'); sink.flush()
    # Only inject counters for boundary unit tests, never a runtime knob.
    if kind == 'rows': sink.rows = d.MAX_ROWS
    else: sink.encoded_bytes = d.MAX_BYTES
    with pytest.raises(d.CaptureFailure, match='fixed_capacity'): sink.write('{}\n')
    with pytest.raises(d.CaptureFailure, match='sticky'): sink.flush()
    assert not sink.close()['evidence_complete'] and PathBytes(sink.path) == ('{}'+os.linesep).encode()


def test_no_runtime_capacity_override(tmp_path):
    with pytest.raises(TypeError): d.SpoolSink(tmp_path/'x', max_rows=1)
    with pytest.raises(TypeError): d.SpoolServiceTape(Native(), mode='ram')


def test_serialization_failure_prefix_unknown(tmp_path):
    native = Native(); tape = d.SpoolServiceTape(native); tape.begin(tmp_path/'capture.gz'); tape.protocol_command()
    native.result = {'bad': float('nan')}
    with pytest.raises(ValueError):
        try: tape.protocol_command()
        except BaseException: tape.close(); raise
    assert tape.count == 2 and tape.capture_report['rows'] == 1 and not tape.capture_report['evidence_complete']
    assert tape.capture_report['failure']['reason'] == 'api_row_denominator_mismatch'


def test_export_failure_closes_handle_and_retains_spool(tmp_path, monkeypatch):
    tape = d.SpoolServiceTape(Native()); tape.begin(tmp_path/'capture.gz'); tape.protocol_command(); handle = tape.stream._file
    def fail(*args, **kwargs): raise OSError('gzip export failed')
    monkeypatch.setattr(d.prior.gzip, 'GzipFile', fail)
    with pytest.raises(OSError, match='gzip export'): tape.close()
    assert handle.closed and not tape.capture_report['evidence_complete']
    assert (tmp_path/'capture.gz.spool.jsonl').is_file()


def test_existing_receipt_cannot_be_overwritten(tmp_path):
    path = tmp_path/'diagnostic_capture.json'; path.write_text('old')
    tape = d.SpoolServiceTape(Native()); tape.begin(tmp_path/'capture.gz'); tape.protocol_command()
    with pytest.raises(FileExistsError): tape.close()
    assert path.read_text() == 'old' and not tape.capture_report['evidence_complete']
