"""Two fixed saved v2 queries: original digest with/without cProfile.

This is an attribution experiment, not a candidate optimization or policy
replay. Preparation decodes the fixed files but NEVER calls the digest. Both
preparation and eventual execution require their own explicit owned120 launch.
"""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import argparse
import cProfile
import gc
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import pstats
import statistics
import sys
import xml.etree.ElementTree as ET
from . import planning_capture_v2_digest as original
from . import initial_owner_route_image as image

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
PRIOR = OUT/'bridge_saved_kernel_cost_prepare_001/plan.json'
PRIOR_SHA = '0f69d7b25e750a73134506dca70c54a40d3d894c719a4a6ba9075d647a371fbc'
MODULE = 'scripts.experiments.g31_ics_circulation.measure_planning_v2_digest_v2'
LAUNCHER = 'scripts.experiments.g31_ics_circulation.launch_planning_v2_digest_v2'
PURE = 'scripts.experiments.g31_ics_circulation.run_planning_v2_digest_v2_pure'
TEST = 'tests/test_g31_circulation_planning_v2_digest_diagnostic_v2.py'
SCHEMA = 'g31.planning_v2_digest.fixed_two_attribution.v2'
ORDINALS = (27212, 27215)
ARMS = ('A', 'B', 'B', 'A')
REPETITIONS = 4
LIMIT = 120.
MAX_COMPRESSED = 1024*1024
MAX_RAW = 32*1024*1024
MAX_ARTIFACT = 16*1024*1024
MAX_ENVELOPES = 8
PURE_TESTS = 58
_DIGEST, _WRITER = original.capture_digest_v2, original._write_local_capture
_DIGEST_CODE, _WRITER_CODE = _DIGEST.__code__, _WRITER.__code__


def require(value, reason):
    if not value: raise ValueError('v2_digest_diagnostic:' + reason)


def sha_bytes(data): return hashlib.sha256(data).hexdigest()
def sha(path): return sha_bytes(Path(path).read_bytes())


def tree(value):
    active = set(); count = 0
    def visit(v, depth):
        nonlocal count
        count += 1; require(depth <= 64 and count <= 2_000_000, 'tree_limit')
        t = type(v)
        if t in (str, int, bool, type(None)): return
        if t is float: require(math.isfinite(v), 'nonfinite'); return
        require(t in (dict, list) and id(v) not in active, 'builtin_or_cycle')
        active.add(id(v))
        try:
            if t is dict:
                require(all(type(k) is str for k in v), 'string_keys')
                for k, member in v.items(): visit(k, depth+1); visit(member, depth+1)
            else:
                for member in v: visit(member, depth+1)
        finally: active.remove(id(v))
    visit(value, 0)


def encoded(value):
    tree(value)
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')
    require(len(data) <= MAX_RAW, 'encoded_limit')
    return data


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate_key'); result[key] = value
    return result


def loads(data):
    require(type(data) is bytes and len(data) <= MAX_RAW, 'raw_limit')
    value = json.loads(data.decode('utf8'), object_pairs_hook=_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('v2_digest_diagnostic:nonfinite')))
    tree(value); return value


def write(path, value):
    data = encoded(value)+b'\n'; require(len(data) <= MAX_ARTIFACT, 'artifact_limit')
    with Path(path).open('xb') as stream: require(stream.write(data) == len(data), 'short_write')


def hexsha(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def source_proof():
    require(original.capture_digest_v2 is _DIGEST and original._write_local_capture is _WRITER
        and _DIGEST.__code__ is _DIGEST_CODE and _WRITER.__code__ is _WRITER_CODE,
        'original_function_changed')
    return {'original_digest_code': True, 'original_local_writer_code': True,
            'profile_changes_function': False, 'full_policy_validation': False}


def envelope_metadata(envelope, owner, ordinal):
    """Input/encoding guards only, not a delivered-policy authority certificate."""
    tree(envelope)
    require(type(envelope) is dict and envelope.get('schema') == 'g31.planning_snapshot.v2'
        and envelope.get('kind') == 'planning_snapshot_v2'
        and envelope.get('digest_format') == 'g31.planning_capture_digest.v2'
        and hexsha(envelope.get('payload_sha256')), 'envelope_schema_or_digest')
    body = envelope['capture']; local = body['local_capture']; extension = body['extension']
    require(type(body) is dict and body['schema'] == 'g31.planning_capture.v2'
        and type(local) is dict and local['schema'] == 'g31.planning_capture.v1'
        and type(extension) is dict and extension['schema'] == 'g31.planning_extension.v2',
        'capture_schema')
    require(type(local['source_owner']) is str and bool(local['source_owner'])
        and local['target_owner'] == owner and extension['source_owner'] == local['source_owner']
        and type(local['captured_at']) in (int, float)
        and type(extension['captured_at']) is type(local['captured_at'])
        and extension['captured_at'] == local['captured_at'], 'capture_channel')
    fields = ((local, 'jobs'), (local, 'trays'), (local, 'nodes'), (local, 'known_faults'),
              (extension, 'terminal_receipts'), (extension, 'submitted_physical_actions'))
    require(all(type(container.get(name)) is list for container, name in fields), 'capture_lists')
    return {'envelope_ordinal': ordinal, 'source_owner': local['source_owner'], 'target_owner': owner,
            'message_id': local['message_id'], 'payload_sha256': envelope['payload_sha256'],
            'body_sha256': sha_bytes(encoded(body)),
            'counts': {name: len(container[name]) for container, name in fields}}


def decode_fixture(compressed, item):
    require(type(compressed) is bytes and len(compressed) <= MAX_COMPRESSED, 'compressed_limit')
    require(sha_bytes(compressed) == item['sha256'] and len(compressed) == item['bytes'], 'compressed_identity')
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode='rb') as stream:
        raw = stream.read(MAX_RAW+1)
        require(len(raw) <= MAX_RAW, 'decompression_limit')
    row = loads(raw)
    require(type(row) is dict and type(row.get('ordinal')) is int and row['ordinal'] == item['ordinal']
        and row.get('endpoint') == 'protocol_planning_snapshots_v2' and 'error' not in row, 'row_identity')
    require(type(row.get('args')) is list and len(row['args']) == 1
        and type(row['args'][0]) is str and bool(row['args'][0])
        and type(row.get('kwargs')) is dict and not row['kwargs'], 'query_arguments')
    require(type(row.get('result')) is list and 1 <= len(row['result']) <= MAX_ENVELOPES, 'envelope_denominator')
    meta = [envelope_metadata(env, row['args'][0], n) for n, env in enumerate(row['result'])]
    return row, {'compressed_sha256': sha_bytes(compressed), 'raw_sha256': sha_bytes(raw),
        'raw_bytes': len(raw), 'owner': row['args'][0], 'ordinal': row['ordinal'],
        'envelopes': meta, 'envelope_count': len(meta), 'digest_calls_during_preparation': 0}


def select_inputs(prior):
    require(type(prior) is dict and type(prior.get('files')) is list, 'prior_shape')
    rows = [r for r in prior['files'] if r.get('side') == 'new' and r.get('ordinal') in ORDINALS]
    require([r['ordinal'] for r in rows] == list(ORDINALS) and all(
        r['endpoint'] == 'protocol_planning_snapshots_v2' and hexsha(r['sha256'])
        and type(r['bytes']) is int and 0 < r['bytes'] <= MAX_COMPRESSED for r in rows), 'fixed_inputs')
    return rows


def source_files():
    return image.source_closure(ROOT, (MODULE, LAUNCHER, PURE, 'tests.'+Path(TEST).stem))


def counts_for(metadata):
    require(type(metadata) is list and [r['ordinal'] for r in metadata] == list(ORDINALS), 'metadata_order')
    require(all(type(r['envelope_count']) is int and 1 <= r['envelope_count'] <= MAX_ENVELOPES
        and r['envelope_count'] == len(r['envelopes']) for r in metadata), 'metadata_counts')
    calls = len(ARMS)*REPETITIONS*sum(r['envelope_count'] for r in metadata)
    return {'query_rows': 2, 'batches': 8, 'repetitions_per_batch': REPETITIONS,
        'row_passes': 32, 'digest_calls': calls, 'A_digest_calls': calls//2, 'B_digest_calls': calls//2,
        'profile_batches': 4, 'additional_reference_digest_calls': 0}


def verify_pins(output, plan, *, runtime=False):
    require(plan['schema'] == SCHEMA and plan['arms'] == list(ARMS)
        and type(plan['shared_seconds']) is float and plan['shared_seconds'] == LIMIT
        and encoded(plan['counts']) == encoded(counts_for(plan['fixture_metadata'])), 'plan_scope')
    require(sha(PRIOR) == PRIOR_SHA == plan['prior_plan_sha256'], 'prior_pin')
    require(encoded(select_inputs(loads(PRIOR.read_bytes()))) == encoded(plan['files']), 'fixed_source_rows')
    files = source_files(); require(set(files) == set(plan['sources']), 'source_domain')
    for rel, data in files.items():
        require(sha_bytes(data) == sha(output/'source'/rel) == plan['sources'][rel], 'source_pin:'+rel)
    for row in plan['files']:
        require(sha(row['source']) == sha(output/'fixtures'/row['file']) == row['sha256'], 'input_pin')
    for ref in plan['pure'].values():
        require(sha(ref['path']) == ref['sha256'], 'pure_pin')
    require(sha(sys.executable) == plan['interpreter_sha256'], 'interpreter_pin')
    require(source_proof() == plan['source_proof'], 'source_proof')
    if runtime:
        loaded = {str(Path(m.__file__).resolve().relative_to(ROOT)).replace('\\', '/')
            for m in list(sys.modules.values()) if getattr(m, '__file__', None)
            and Path(m.__file__).suffix == '.py' and Path(m.__file__).resolve().is_relative_to(ROOT)}
        require(loaded <= set(plan['sources']), 'runtime_loaded_domain')


def load_frozen(output, plan):
    rows, metadata = [], []
    for item in plan['files']:
        row, meta = decode_fixture((output/'fixtures'/item['file']).read_bytes(), item)
        rows.append(row); metadata.append(meta)
    require(encoded(metadata) == encoded(plan['fixture_metadata']), 'raw_or_envelope_pin')
    return rows


def prepare(output, pure):
    require(output.is_dir() and not (output/'plan.json').exists(), 'prepare_directory')
    receipt, xml = pure/'receipt.json', pure/'tests.xml'
    r = loads(receipt.read_bytes()); tests = ET.parse(xml).getroot().findall('.//testcase')
    require(r['status'] == 'passed' and r['source_changed'] == [] and r['digest_calls'] == 0
        and r['actual_raw_reads'] == r['native_calls'] == 0
        and len(tests) == PURE_TESTS and not any(c.tag in ('failure','error','skipped') for t in tests for c in t)
        and r['XML_sha256'] == sha(xml), 'pure_gate')
    files = source_files(); require(set(files) == set(r['source_sha256']), 'tested_source_domain')
    for rel, data in files.items():
        require(sha_bytes(data) == r['source_sha256'][rel], 'tested_source_drift')
        target = output/'source'/rel; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    require(sha(PRIOR) == PRIOR_SHA, 'prior_pin')
    inputs = select_inputs(loads(PRIOR.read_bytes())); (output/'fixtures').mkdir()
    metadata = []; load_started = time.perf_counter_ns()
    for item in inputs:
        compressed = Path(item['source']).read_bytes()
        _, meta = decode_fixture(compressed, item)  # Deliberately no digest call.
        (output/'fixtures'/item['file']).write_bytes(compressed); metadata.append(meta)
    load_finished = time.perf_counter_ns()
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'arms': list(ARMS), 'shared_seconds': LIMIT,
        'files': inputs, 'fixture_metadata': metadata, 'counts': counts_for(metadata),
        'prior_plan_sha256': PRIOR_SHA, 'sources': {rel: sha_bytes(data) for rel, data in files.items()},
        'interpreter_sha256': sha(sys.executable), 'source_proof': source_proof(),
        'pure': {'receipt': {'path': str(receipt.resolve()), 'sha256': sha(receipt)},
                 'xml': {'path': str(xml.resolve()), 'sha256': sha(xml)}},
        'preparation': {'digest_calls': 0, 'input_load_started_ns': load_started,
            'input_load_finished_ns': load_finished, 'input_load_elapsed_ns': load_finished-load_started},
        'scope': 'Two fixed actual historical query rows; no policy replay, no native/model, no representativeness or whole600 conclusion.',
        'arms_explanation': 'A original unprofiled; B same original under cProfile. B is not an optimization. Default GC remains enabled.',
        'clocks': 'Whole includes input/source reads, guards/fingerprints, all original calls, profiles/export/readback and cleanup. Isolated digest is nested; cumulative pstats overlap must not be added.',
        'guards': 'Finite exact builtin JSON and envelope/channel/digest format checks only. Actual full delivered_peer ownership/freshness/action validation is NOT replayed.',
        'failure': 'Any digest mismatch, count/order loss, exception, drift or timeout remains unknown; no filtering/retry/capacity expansion.',
        'native_calls': 0, 'policy_replays': 0, 'optimization_or_100ms_claim': False}
    write(output/'plan.json', plan); verify_pins(output, plan, runtime=True)
    write(output/'ready.json', {'schema': SCHEMA+'.ready', 'status': 'prepared_unexecuted',
        'output': str(output.resolve()), 'plan_sha256': sha(output/'plan.json'),
        'execute_command': [sys.executable, '-m', LAUNCHER, '--execute', '--output', str(output.resolve()),
                            '--plan-sha256', sha(output/'plan.json')],
        'external_launch_to_exit_required': True, 'performance_executed': False})


def expected_order(metadata):
    return [(m['ordinal'], batch, arm, repeat, env) for m in metadata
        for batch, arm in enumerate(ARMS) for repeat in range(REPETITIONS)
        for env in range(m['envelope_count'])]


def measure_one(envelope, owner, meta, arm, profiler=None):
    started = time.perf_counter_ns()
    require(arm in ('A','B') and (profiler is not None if arm == 'B' else profiler is None), 'measurement_arm')
    require(envelope_metadata(envelope, owner, meta['envelope_ordinal']) == meta, 'per_call_guard_or_mutation')
    before = time.perf_counter_ns()
    result = (_DIGEST(envelope['capture']) if arm == 'A' else profiler.runcall(_DIGEST, envelope['capture']))
    after = time.perf_counter_ns()
    require(result == meta['payload_sha256'], 'original_native_digest_mismatch')
    require(envelope_metadata(envelope, owner, meta['envelope_ordinal']) == meta, 'digest_input_mutation')
    checked = time.perf_counter_ns()
    return {'started_ns': started, 'digest_started_ns': before, 'digest_finished_ns': after,
            'checked_ns': checked, 'digest_ns': after-before, 'guard_and_check_ns': (before-started)+(checked-after),
            'digest': result, 'body_sha256': meta['body_sha256'], 'guards_passed': True}


def check_records(records, batches, metadata):
    require(type(records) is list and [(r['ordinal'],r['batch'],r['arm'],r['repeat'],r['envelope_ordinal'])
        for r in records] == expected_order(metadata), 'measurement_order_or_count')
    require(type(batches) is list and [(b['ordinal'],b['batch'],b['arm']) for b in batches] ==
        [(m['ordinal'], n, a) for m in metadata for n, a in enumerate(ARMS)], 'batch_order_or_count')
    metas = {m['ordinal']: m for m in metadata}; previous = -1
    for row in records:
        require(all(type(row[k]) is int and row[k] >= 0 for k in
            ('ordinal','batch','repeat','envelope_ordinal')), 'measurement_index_type')
        clocks = [row[k] for k in ('started_ns','digest_started_ns','digest_finished_ns','checked_ns')]
        require(all(type(c) is int and c >= 0 for c in clocks)
            and previous <= clocks[0] <= clocks[1] <= clocks[2] <= clocks[3], 'measurement_clock')
        require(type(row['digest_ns']) is int and row['digest_ns'] == clocks[2]-clocks[1]
            and type(row['guard_and_check_ns']) is int and row['guard_and_check_ns'] ==
                clocks[1]-clocks[0]+clocks[3]-clocks[2], 'measurement_duration')
        m = metas[row['ordinal']]['envelopes'][row['envelope_ordinal']]
        require(row['digest'] == m['payload_sha256'] and row['body_sha256'] == m['body_sha256']
            and row['guards_passed'] is True, 'saved_digest_binding')
        previous = clocks[3]
    previous = -1
    for b in batches:
        require(all(type(b[k]) is int and b[k] >= 0 for k in ('ordinal','batch','started_ns','finished_ns','whole_ns'))
            and previous <= b['started_ns'] <= b['finished_ns']
            and b['whole_ns'] == b['finished_ns']-b['started_ns'], 'batch_clock')
        members = [r for r in records if r['ordinal'] == b['ordinal'] and r['batch'] == b['batch']]
        require(b['started_ns'] <= members[0]['started_ns'] and members[-1]['checked_ns'] <= b['finished_ns'], 'batch_containment')
        require(b['profile_file'] == (f"profile_{b['ordinal']}_{b['batch']}.pstats" if b['arm']=='B' else None), 'profile_denominator')
        previous = b['finished_ns']
    return {'counts': counts_for(metadata), 'median_digest_ms': {
        arm: statistics.median(r['digest_ns'] for r in records if r['arm']==arm)/1e6 for arm in ('A','B')},
        'interpretation': 'Profile perturbation of the same original function, not an optimized-arm speed comparison; no whole-policy attribution.'}


def check_profile(path, expected_calls):
    stats = pstats.Stats(str(path))
    keys = [(fn.__code__.co_filename, fn.__code__.co_firstlineno, fn.__name__) for fn in (_DIGEST, _WRITER)]
    counts = {}
    for key in keys:
        require(key in stats.stats, 'profile_missing_original_function')
        primitive, total, self_seconds, cumulative, callers = stats.stats[key]
        require(type(primitive) is int and type(total) is int and primitive == total == expected_calls,
                'profile_original_call_count')
        require(all(type(v) in (int,float) and math.isfinite(v) and v >= 0
            for v in (self_seconds,cumulative)), 'profile_time')
        counts[key[2]] = total
    return counts


def execute(output, plan_sha):
    require(sha(output/'plan.json') == plan_sha, 'execute_plan_sha')
    with (output/'execution_claim.json').open('x') as f: json.dump({'plan_sha256': plan_sha}, f)
    plan = loads((output/'plan.json').read_bytes()); records = []; batches = []; error = None
    try:
        verify_pins(output, plan, runtime=True); source_proof()
        require(gc.isenabled(), 'default_GC_disabled')
        entry = time.perf_counter_ns(); rows = load_frozen(output, plan); loaded = time.perf_counter_ns()
        with (output/'measurements.jsonl').open('xb') as journal:
            for row, metadata in zip(rows, plan['fixture_metadata']):
                for batch, arm in enumerate(ARMS):
                    begin = time.perf_counter_ns(); profiler = cProfile.Profile() if arm == 'B' else None
                    for repeat in range(REPETITIONS):
                        for env_index, (env, meta) in enumerate(zip(row['result'], metadata['envelopes'])):
                            sample = {'ordinal': row['ordinal'], 'batch': batch, 'arm': arm,
                                'repeat': repeat, 'envelope_ordinal': env_index,
                                **measure_one(env, metadata['owner'], meta, arm, profiler)}
                            records.append(sample); data = encoded(sample)+b'\n'
                            require(journal.write(data) == len(data), 'short_journal'); journal.flush()
                    profile_file = None
                    if profiler is not None:
                        profile_file = f"profile_{row['ordinal']}_{batch}.pstats"
                        profiler.dump_stats(str(output/profile_file))
                        with (output/(profile_file+'.txt')).open('x', encoding='utf8') as stream:
                            pstats.Stats(profiler, stream=stream).sort_stats('cumulative').print_stats()
                    end = time.perf_counter_ns()
                    batches.append({'ordinal': row['ordinal'], 'batch': batch, 'arm': arm,
                        'started_ns': begin, 'finished_ns': end, 'whole_ns': end-begin, 'profile_file': profile_file})
        summary = check_records(records, batches, plan['fixture_metadata'])
        # End input load verifies both original compressed and full decoded raw
        # hashes; it is charged to the same120, with no further digest calls.
        verify_pins(output, plan, runtime=True); load_frozen(output, plan)
        profile_pins = {p.name: sha(p) for p in output.glob('profile_*') if p.is_file()}
        result = {'schema': SCHEMA+'.result', 'status': 'completed_original_digest_attribution',
            'plan_sha256': plan_sha, 'records': records, 'batches': batches, 'summary': summary,
            'profile_files': profile_pins, 'entry_fixture_load_ns': loaded-entry,
            'GC_enabled': gc.isenabled(), 'native_calls': 0, 'policy_replays': 0,
            'post_BOOT_before_result_seconds': time.perf_counter()-BOOT}
        write(output/'result.json', result)
        write(output/'saved_verification.json', verify_saved(output, plan))
        require(time.perf_counter()-BOOT <= LIMIT, 'whole_budget')
    except BaseException as exc:
        error = repr(exc)
        write(output/'failure.json', {'schema': SCHEMA+'.failure', 'error': error,
            'completed_measurements': len(records), 'completed_batches': len(batches),
            'partial_records': records, 'partial_batches': batches, 'success': False})
    return 0 if error is None else 1


def verify_saved(output, plan):
    result = loads((output/'result.json').read_bytes())
    require(result['schema'] == SCHEMA+'.result' and result['status'] == 'completed_original_digest_attribution'
        and result['plan_sha256'] == sha(output/'plan.json') and result['GC_enabled'] is True, 'saved_result_identity')
    journal = [loads(line) for line in (output/'measurements.jsonl').read_bytes().splitlines()]
    require(encoded(journal) == encoded(result['records']), 'journal_binding')
    summary = check_records(journal, result['batches'], plan['fixture_metadata'])
    require(encoded(summary) == encoded(result['summary']), 'saved_summary')
    expected = {b['profile_file'] for b in result['batches'] if b['arm']=='B'}
    expected |= {name+'.txt' for name in expected}
    require(set(result['profile_files']) == expected, 'profile_file_count')
    for name in expected: require(sha(output/name) == result['profile_files'][name], 'profile_hash')
    profile_counts = {}
    for batch in result['batches']:
        if batch['arm'] == 'B':
            meta = next(m for m in plan['fixture_metadata'] if m['ordinal'] == batch['ordinal'])
            profile_counts[batch['profile_file']] = check_profile(output/batch['profile_file'],
                REPETITIONS*meta['envelope_count'])
    verify_pins(output, plan, runtime=True)
    return {'schema': SCHEMA+'.saved_review', 'status': 'passed_saved_attribution', 'summary': summary,
        'result_sha256': sha(output/'result.json'), 'journal_sha256': sha(output/'measurements.jsonl'),
        'profile_original_function_counts': profile_counts,
        'scope': 'Re-read every measurement/order/count/digest binding and profile artifact hash. No extra digest/model/native calls.'}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepare-child',action='store_true'); p.add_argument('--campaign-child',action='store_true')
    p.add_argument('--pure',type=Path); p.add_argument('--plan-sha256'); p.add_argument('--admission',required=True)
    a = p.parse_args(); require(sys.stdin.readline().strip() == a.admission, 'owned_admission')
    output = a.output.resolve()
    if a.prepare_child:
        require(not a.campaign_child and a.pure is not None and a.admission == PRIOR_SHA, 'prepare_mode')
        prepare(output, a.pure.resolve()); return 0
    require(a.campaign_child and a.plan_sha256 == a.admission, 'campaign_mode')
    return execute(output, a.plan_sha256)


if __name__ == '__main__': raise SystemExit(main())
