from copy import deepcopy
import gzip
import inspect
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import probe_original_route_update_spool as p
from scripts.experiments.g31_ics_circulation import verify_original_route_update_spool as v
from scripts.experiments.g31_ics_circulation import launch_original_route_update_spool as launch
from scripts.experiments.g31_ics_circulation import spooled_service_tape as sink


def row(index=0):
    return {'ordinal': index, 'endpoint': 'protocol_command', 'role': 'request', 'args': ['A', 'id'],
        'kwargs': {}, 'before': 1., 'after': 1., 'start_ns': 10, 'end_ns': 11, 'result': {'status': 'pending'}}


def tape(path, rows):
    with gzip.open(path, 'wt', encoding='utf8') as stream:
        for item in rows: stream.write(json.dumps(item)+'\n')


def test_worker_private_globals_and_invocation_unchanged():
    reference = p.reference.inherited_worker()
    current = p.inherited_worker()
    assert current.__code__ is reference.__code__ and current.__closure__ is reference.__closure__
    changed = {key for key in reference.__globals__ if current.__globals__[key] is not reference.__globals__[key]}
    assert changed == {'SCHEMA', 'verify_pins', 'ServiceTape'}
    assert current.__globals__['RouteUpdate'] is p.reference.RouteUpdate
    assert current.__globals__['ServiceTape'].__getattr__ is p.policy.ServiceTape.__getattr__


def test_original_verifier_globals_unchanged_and_exact_new_comparator():
    before = dict(v.original.verify_case.__globals__)
    function = v.case_function()
    assert v.original.verify_case.__globals__ == before
    assert function.__globals__['p'] is p and function.__globals__['verify_scheduled_reference'] is v.verify_reference


def test_assessor_shape_change_fails_closed(monkeypatch):
    source = inspect.getsource(v.original.verify_case); real = v.inspect.getsource
    monkeypatch.setattr(v.inspect, 'getsource', lambda value: source.replace('p.old.assess(root["intent"], root["client_calls"])',
        'p.old.assess(root["intent"], [])') if value is v.original.verify_case else real(value))
    with pytest.raises(ValueError, match='assessor_call_changed'): v.case_function()


@pytest.mark.parametrize('mutation', ['none', 'missing', 'extra', 'value', 'role', 'order', 'ordinal', 'observe_omitted'])
def test_exact_api_denominator_and_values(tmp_path, mutation):
    reference = [row(0), row(1)]; reference[1]['endpoint'] = 'observe_protocol'
    candidate = deepcopy(reference)
    if mutation in {'missing', 'observe_omitted'}: candidate.pop()
    elif mutation == 'extra': candidate.append(row(2))
    elif mutation == 'value': candidate[0]['result']['status'] = 'delivered'
    elif mutation == 'role': candidate[0]['role'] = 'controller'
    elif mutation == 'order': candidate.reverse()
    elif mutation == 'ordinal': candidate[0]['ordinal'] = True
    path = tmp_path/'rows.gz'; tape(path, reference)
    if mutation == 'none': assert v.compare_api_stream(path, candidate)['remaining_api_rows'] == 2
    else:
        with pytest.raises(ValueError): v.compare_api_stream(path, candidate)


@pytest.mark.parametrize('clock', [True, -1., float('inf'), float('nan')])
def test_clock_exclusion_domain(clock):
    item = row(); item['endpoint'] = 'advance_to'; item['result']['wall_seconds'] = clock
    with pytest.raises(ValueError): v.api_semantics(item)


def capture_fixture(tmp_path):
    output = tmp_path/'candidate'; directory = output/'baseline'; directory.mkdir(parents=True)
    class Native:
        physical_time = 1.
        def protocol_command(self): return {'status': 'pending'}
    tape = sink.SpoolServiceTape(Native()); tape.begin(directory/'service_tape.jsonl.gz'); tape.protocol_command(); tape.close()
    capture = tape.capture_report
    raw = {'api_rows': 1, 'api_sha256': sink.sha(directory/'service_tape.jsonl.gz'),
        'root': {'returned_ns': capture['close_started_ns']-1, 'censored_ns': None},
        'result_capture_before_seal_ns': capture['close_hashes_finished_ns']+1}
    p.old.gzwrite(directory/'raw.json.gz', raw)
    parent = {'cases': {'baseline': {'parent_child_end_ns': capture['close_hashes_finished_ns']+2,
        'artifact_sha256': {name: sink.sha(directory/name) for name in
            ('service_tape.jsonl.gz', 'service_tape.jsonl.gz.spool.jsonl', 'diagnostic_capture.json')}}}}
    p.old.write(output/'receipt.json', parent)
    return output, directory, capture, parent


def test_capture_saved_roundtrip(tmp_path):
    output, _, _, _ = capture_fixture(tmp_path)
    assert v.verify_capture(output, 'baseline')['status'] == 'complete_lossless_spool_and_gzip'


@pytest.mark.parametrize('mutation', ['limit', 'rows', 'failure', 'false_complete', 'close_clock', 'spool_byte',
    'gzip_byte', 'receipt_hash', 'spool_hash', 'missing_spool', 'bool_count', 'path', 'active_error'])
def test_bad_saved_capture_rejected(tmp_path, mutation):
    output, directory, capture, parent = capture_fixture(tmp_path)
    if mutation == 'limit': capture['max_rows'] += 1
    elif mutation == 'rows': capture['rows'] += 1
    elif mutation == 'failure': capture['failure'] = {'reason': 'short_spool_write'}
    elif mutation == 'false_complete': capture['evidence_complete'] = False
    elif mutation == 'close_clock': capture['close_started_ns'] = capture['close_hashes_finished_ns']+1
    elif mutation == 'bool_count': capture['rows'] = True
    elif mutation == 'path': capture['spool_path'] = 'foreign'
    elif mutation == 'active_error': capture['original_inflight_error'] = 'native failed'
    elif mutation == 'spool_byte':
        with (directory/'service_tape.jsonl.gz.spool.jsonl').open('ab') as stream: stream.write(b'{}\n')
    elif mutation == 'gzip_byte': (directory/'service_tape.jsonl.gz').write_bytes(b'broken')
    elif mutation == 'missing_spool': (directory/'service_tape.jsonl.gz.spool.jsonl').unlink()
    elif mutation == 'receipt_hash': parent['cases']['baseline']['artifact_sha256']['diagnostic_capture.json'] = '0'*64
    elif mutation == 'spool_hash': capture['accepted_encoded_sha256'] = '0'*64
    p.old.write(directory/'diagnostic_capture.json', capture)
    if mutation != 'receipt_hash': parent['cases']['baseline']['artifact_sha256']['diagnostic_capture.json'] = sink.sha(directory/'diagnostic_capture.json')
    p.old.write(output/'receipt.json', parent)
    with pytest.raises((ValueError, FileNotFoundError)): v.verify_capture(output, 'baseline')


def test_fixed_scope_and_no_native_ram_candidate():
    assert launch.LIMIT == p.PARENT_SECONDS == 600. and launch.CASES == set(p.CASES)
    assert p.HORIZON == 9900. and p.ADMISSION == 9600. and len(p.CASES) == 3
    assert p.contract()['max_bytes'] == 256*1024*1024 and p.contract()['max_rows'] == 160000
    assert p.contract()['mode'] == 'spool_only' and p.old.BINARY_SHA == p.reference.old.BINARY_SHA


def test_actual_pending_baseline_request_replay_no_native():
    directory = p.REFERENCE/'baseline'
    raw = p.old.gzread(directory/'raw.json.gz')
    with gzip.open(directory/'service_tape.jsonl.gz', 'rt', encoding='utf8') as stream: rows = [json.loads(line) for line in stream]
    function = v.case_function()
    update = function.__globals__['replay_request'](raw, rows)
    assert update.closed and v.compare_api_stream(directory/'service_tape.jsonl.gz', rows)['remaining_api_rows'] == len(rows)


def test_source_closure_covers_new_and_old_modules():
    paths = set(p.source_paths())
    assert {Path(module.__file__).resolve() for module in (p, v, launch, sink, sink.prior, p.reference)} <= paths
    assert p.ROOT/'scripts/eval/run_g4irsf28_service_potential.py' in paths


def test_prepare_uses_saved_full_plan_not_reference_campaign_return(tmp_path, monkeypatch):
    output = tmp_path/'fresh'
    def inherited_prepare(path):
        path.mkdir()
        p.old.write(path/'preregistered_protocol.json', {'native_binary': 'saved-authority',
            'input_business_count': 28506, 'interpreter': {'path': 'test-interpreter'}})
        return {'status': 'campaign-only-return'}
    monkeypatch.setattr(p.reference, 'prepare', inherited_prepare)
    monkeypatch.setattr(p.reference, 'verify_pins', lambda *args, **kwargs: None)
    monkeypatch.setattr(p, 'reference_pins', lambda: {})
    monkeypatch.setattr(p, 'source_paths', lambda: [Path(p.__file__).resolve()])
    seen = []
    monkeypatch.setattr(p, 'verify_pins', lambda path, plan: seen.append(deepcopy(plan)))
    p.prepare(output)
    assert seen[0]['native_binary'] == 'saved-authority' and seen[0]['input_business_count'] == 28506
    assert 'status' not in seen[0]
