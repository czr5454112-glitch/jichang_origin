"""Independent saved-data integrity/denominator readback; no project imports."""
from pathlib import Path
import gzip, hashlib, json, math, statistics, time

START = time.perf_counter()
HERE = Path(__file__).resolve().parent
ROOT, OUT = HERE.parents[3], HERE.parent
DEST = ROOT/'outputs/sicm1'
SHA = '8aa7f63c50310532fa97b0b6251ec118aeae247ff6b072ddbc73edb7f9d3018e'
hashes = 0
def sha(path):
    global hashes
    hashes += 1
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def pairs(items):
    result = {}
    for key, value in items:
        assert key not in result, 'duplicate JSON key'
        result[key] = value
    return result
def bad(value):
    raise ValueError(value)
def loads(data):
    return json.loads(data, object_pairs_hook=pairs, parse_constant=bad)
def read(name):
    return loads((DEST/name).read_bytes())
def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode('utf8')
def ref(item):
    assert sha(item['path']) == item['sha256']

assert sha(DEST/'campaign.json') == SHA
assert sha(DEST/'root_prelaunch_review_001.json') == 'cd7bbb44f7929a5df82874c298f95f8964f9e293688e49ef2dd1946acccb0fed'
assert sha(DEST/'actual_external_application_wall.json') == 'f33d1debdde90b47c59f6db13b1c432bb571546a37d499aca2fe46895333298a'
plan, outer, producer, verifier, ledger = (read(n) for n in (
    'campaign.json', 'actual_external_application_wall.json', 'receipt.json', 'verification.json', 'branch_ledger.json'))
assert outer['exitcode'] == 0 and outer['status'] == 'completed_original18_once'
assert type(outer['python_launch_to_exit_seconds']) in (int, float) and math.isfinite(outer['python_launch_to_exit_seconds'])
assert 0 < outer['python_launch_to_exit_seconds'] <= 600 and outer['automatic_retries'] == 0
frequency,ticks=outer['stopwatch_frequency'],outer['elapsed_ticks']
assert type(frequency) is int and frequency>0 and type(ticks) is int and 0<ticks<=600*frequency
assert outer['python_launch_to_exit_seconds']==ticks/frequency and outer['wrapper_exitcode']==0
assert outer['missing_artifacts']==[] and outer['automatic_retries']==0
assert outer['source_changed'] == producer['source_changed'] == []
assert outer['source_before'] == outer['source_after']
for path, digest in outer['source_before'].items(): assert sha(path) == digest
assert sha(outer['wrapper']['path']) == outer['wrapper']['sha256'] == 'cd06e16b5f7ad4f24ac42d4f4d4ed8f773bc092434a729bbd5fed8bdb12191a5'
for name, item in outer['artifacts'].items():
    assert Path(item['path']).resolve() == (DEST/name).resolve(); ref(item)
launcher = read('external_launch_receipt.json')
assert launcher['process'] == outer['inner_process']
assert launcher['process']['status'] == 'exited' and launcher['process']['exitcode'] == 0
assert launcher['process']['windows_job_kill_on_close'] is True
assert launcher['process']['child_released_only_after_job_assignment'] is True
for name, digest in launcher['artifacts'].items(): assert sha(DEST/name) == digest
assert producer['status'] == 'completed_finite_request_cohort' and producer['campaign_sha256'] == SHA
ref(producer['verification'])
assert producer['loaded_project_sources_entry'] == producer['loaded_project_sources_exit']
assert len(plan['source_sha256']) == 232 and len(plan['compiled_source_archive_sha256']) == 67
for name, digest in plan['source_sha256'].items():
    current, archive = (ROOT/name).resolve(), (DEST/plan['source_archive'][name]).resolve()
    assert current.is_relative_to(ROOT) and archive.is_relative_to(DEST/'source') and current != archive
    assert sha(current) == sha(archive) == digest
for path, digest in plan['compiled_source_archive_sha256'].items(): assert sha(path) == digest
for name, digest in plan['input_file_sha256'].items(): assert sha(DEST/'inputs'/(name+'.json')) == digest
assert list(ledger) == list(plan['rows']) == list(verifier['rows']) == plan['row_order']
assert len(ledger) == 18 and verifier['status'] == 'passed_saved_with_complete_unknown_denominator'
assert verifier['invalid_or_error_branches'] == {} and verifier['unverified_RPC_branches'] == []
assert verifier['prediction_counts_complete'] is True and verifier['predictor_protocol_closed'] is True

raw_outcomes, observed, complete_bytes = {}, [], 0
root_intervals = {}
for key, declared in plan['rows'].items():
    row, checked = ledger[key], verifier['rows'][key]
    assert row['status'] == 'raw_saved' and {n: row[n] for n in ('case', 'method', 'fault')} == declared
    ref(row['raw']); raw = loads(gzip.decompress(Path(row['raw']['path']).read_bytes()))
    assert raw['key'] == key and raw['specification'] == declared
    assert raw['outcome'] == checked['business']
    raw_outcomes[key] = raw['outcome']
    assert raw['native_state_sha256'] == checked['native_state_sha256']
    expected_audit = 'passed_with_retained_unknown' if key.startswith('initial_ack_drop3/') else 'passed'
    assert checked['audit_status'] == expected_audit and checked['original_root_replay_verified'] is True
    assert checked['root']['closed'] is (expected_audit == 'passed')
    assert checked['original_checks']['original_branch_and_query_gate']['status'] == 'passed'
    assert checked['RPC_audit']['status'] == 'passed'
    assert row['attempt_started_ns'] <= row['export_started_ns'] <= row['export_finished_ns'] <= row['attempt_finished_ns']
    assert len(raw['root_records']) == 1
    root = raw['root_records'][0]; evidence = root['value']['evidence']; encoded = encode(evidence)
    assert hashlib.sha256(encoded).hexdigest() == root['ledger']['evidence_sha256']
    assert len(encoded) == root['ledger']['bytes']; complete_bytes += len(encoded)
    assert encode(root['ledger']).decode('utf8') == root['return_codec']
    assert root['ledger']['root_id'] == evidence['root_id']
    assert root['ledger']['state'] == evidence['state'] and root['ledger']['choice'] == evidence['choice']
    assert evidence['root_deadline_ns'] - evidence['root_started_ns'] == 100_000_000
    assert evidence['decision_cutoff_ns'] - evidence['root_started_ns'] == 60_000_000
    elapsed = root['outside_return_ns'] - evidence['root_started_ns']
    assert elapsed == root['warm_caller_elapsed_ns']
    assert row['attempt_started_ns'] <= evidence['root_started_ns'] <= root['finalization_started_ns'] <= root['value']['body_finished_ns'] <= root['outside_return_ns'] <= row['export_started_ns']
    assert root['value']['body_finished_ns'] - evidence['root_started_ns'] == root['value']['body_elapsed_ns']
    assert checked['root']['warm_ms'] == elapsed/1e6
    assert checked['root']['complete_100ms_certified'] is False and root['complete_100ms_certificate'] is False
    assert root['within_100ms_observed'] == (root['closed'] and elapsed <= 100_000_000)
    root_intervals[key.replace('/', ':')] = (evidence['root_started_ns'], evidence['root_deadline_ns'], evidence['decision_cutoff_ns'], root['outside_return_ns'])
    observed.append({'key': key, 'closed': checked['root']['closed'], 'warm_ms': elapsed/1e6,
        'root_status': checked['root']['status'], 'choice': root['ledger']['choice'],
        'observed_under100': checked['root']['observed_within_100ms'], 'evidence_bytes': len(encoded)})

normal = {}
for key, pair in verifier['pairs'].items():
    if not key.startswith('normal/'): continue
    b = raw_outcomes[key]['completion']; a = raw_outcomes[key.replace('/budget_two', '/fixed_default')]['completion']
    assert set(a) == set(b) == {'blocker', 'loaded', 'receiver', 'reuse1', 'reuse2'}
    delta = {job: b[job]-a[job] for job in sorted(a)}
    assert delta == pair['per_job_delta'] and all(value <= 0 for value in delta.values())
    assert pair['all_five_strict_nonregression'] is True and pair['request_pair_completed'] is True
    normal[key] = {'all_five_nonregression': True, 'strictly_improved': any(value < 0 for value in delta.values()), 'per_job_delta': delta}
assert len(normal) == 6 and sum(row['strictly_improved'] for row in normal.values()) == 2
closed = [r['warm_ms'] for r in observed if r['closed']]
assert len(closed) == verifier['closed_roots'] == 16
assert len(observed)-len(closed) == verifier['open_or_unknown_roots'] == 2
assert not any(r['observed_under100'] for r in observed)
assert verifier['prediction_counts'] == {'baseline_evaluation_calls': 8, 'complete_baselines': 8, 'additional_candidate_calls': 8}
lifetime = read('C_provider_lifetime.json')
assert lifetime['status'] == 'closed_identity_checked'
assert lifetime['actual_entry'] == lifetime['actual_exit'] and lifetime['files_entry'] == lifetime['files_exit']
actual, contract = lifetime['actual_entry'], plan['C_provider']
assert actual['binary_sha256'] == contract['binary']['sha256']
for name in ('file', 'spec_origin', 'loader_path'): assert Path(actual[name]).resolve() == Path(contract['binary']['path']).resolve()
assert actual['loader_type'] == 'ExtensionFileLoader' and actual['source_sha256'] == contract['original_sources']
ref(contract['binary'])
for item in actual['actual_DLLs'].values(): ref(item)
assert lifetime['actual_direct_C_supported'] is lifetime['actual_fallback_count'] is None
assert lifetime['provider_includes_original_fallback'] is True
assert lifetime['setup_finished_ns'] <= min(row['attempt_started_ns'] for row in ledger.values())
assert max(row['attempt_finished_ns'] for row in ledger.values()) <= lifetime['close_started_ns']
assert sha(DEST/'static_inventory_lifetime.json') == '7e515d40de80e7c942fa5b018d22f93cc9d8d0b102484999756dbef8d5627050'
static = read('static_inventory_lifetime.json')
assert static['status']=='closed_identity_checked' and static['cold_bind_status']=='returned'
assert len(static['constructors'])==18
assert lifetime['setup_started_ns'] <= static['cold_bind_started_ns'] <= static['cold_bind_finished_ns'] <= lifetime['setup_finished_ns']
assert (static['cold_bind_finished_ns']-static['cold_bind_started_ns'])/1e6 == verifier['static_inventory_lifetime']['cold_binding_ms']
constructor_ms=[];seen=set()
for ordinal,row in enumerate(static['constructors']):
    assert row['ordinal']==ordinal and row['status']=='constructor_returned' and row['error_type'] is None
    fields=row['root'];identity=fields['request_id'];assert identity in root_intervals and identity not in seen
    seen.add(identity);start,deadline,cutoff,finish=root_intervals[identity]
    assert (fields['started_ns'],fields['deadline_ns'],fields['cutoff_ns'])==(start,deadline,cutoff)
    assert type(row['started_ns']) is int and type(row['finished_ns']) is int
    assert start <= row['started_ns'] <= row['finished_ns'] <= finish
    elapsed=(row['finished_ns']-row['started_ns'])/1e6;constructor_ms.append(elapsed)
    matched=verifier['static_inventory_lifetime']['rows'][identity.replace(':','/')]
    assert matched=={'status':'constructor_returned','wall_ms':elapsed}
assert seen==set(root_intervals)
assert verifier['static_inventory_lifetime']['missing_before_constructor_failures']==[]
assert verifier['static_inventory_lifetime']['unverified_missing_raw_constructor_rows']=={}
assert verifier['static_inventory_lifetime']['status']=='passed_constructor_sidecar_bound_to_original_saved_checks'
report = {'schema': 'g31.static_inventory_C18.root_saved_readback.v1', 'status': 'passed_independent_saved_integrity_and_denominator',
    'script_sha256': sha(__file__), 'campaign_sha256': SHA, 'rows': observed, 'normal_pairs': normal,
    'complete_root_canonical_bytes_verified': complete_bytes, 'raw_gzip_rows_read': 18,
    'source_current_and_archive_count': 232, 'compiled_archive_files': 67, 'hash_reads': hashes,
    'closed_roots': 16, 'unknown_roots': 2, 'observed_under100': 0,
    'constructor_nested_wall_ms': {'min': min(constructor_ms), 'median': statistics.median(constructor_ms), 'max': max(constructor_ms), 'sum': sum(constructor_ms)},
    'cold_static_bind_ms': verifier['static_inventory_lifetime']['cold_binding_ms'],
    'closed_ms': {'min': min(closed), 'median': statistics.median(closed), 'max': max(closed)},
    'whole_python_actual_seconds': outer['python_launch_to_exit_seconds'],
    'elapsed_saved_review_seconds_before_export': time.perf_counter()-START,
    'limits': ['Saved normalized evidence canonical bytes/hash/ledger/clocks independently reconstructed for all18. Full raw outcomes and strict normal pairs matched saved audit.',
        'No native/model/C invocation. Original endpoint/physics/RPC replay acceptance is producer audit evidence, not a second independently implemented physics checker.',
        'Current project sources/archive, actual binary/DLL files rehashed. Full6124 toolchain domain not rehashed here; original actual entry/exit/saved checks are retained.',
        'Direct C/fallback counts unknown. Finite2 original cohort; no causal speed/full32/all-day/joint-effectiveness or100ms certificate.']}
with (DEST/'root_saved_review_001.json').open('x', encoding='utf8') as stream: json.dump(report, stream, indent=2)
print(json.dumps({'status': report['status'], 'sha256': sha(DEST/'root_saved_review_001.json'), 'closed_ms': report['closed_ms'], 'rows': 18, 'whole_saved_review_seconds': time.perf_counter()-START}))
