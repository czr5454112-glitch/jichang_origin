"""Independent saved-data integrity/denominator readback; no project imports."""
from pathlib import Path
import gzip, hashlib, json, math, statistics, time

START = time.perf_counter()
HERE = Path(__file__).resolve().parent
ROOT, OUT = HERE.parents[3], HERE.parent
DEST = OUT/'single_owned_C18_prepare_002'
SHA = '4ac4569ad5145ccf62e83a39d29ad238077bf00fa0657c130fb12916cfb91bdc'
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
assert sha(DEST/'root_review_001.json') == 'de24dfe036794e4e9a83378ccbd99e6ff421a7456d0dabbb8ffda3cf50d0b278'
assert sha(DEST/'actual_external_application_wall.json') == '1a80c1e0e9cf82cd2bb1704ea917b51d0c7dc77c12aff9d8a30764dc3703c3e2'
plan, outer, producer, verifier, ledger = (read(n) for n in (
    'campaign.json', 'actual_external_application_wall.json', 'receipt.json', 'verification.json', 'branch_ledger.json'))
assert outer['exitcode'] == 0 and outer['status'] == 'completed_original18_once'
assert type(outer['python_launch_to_exit_seconds']) in (int, float) and math.isfinite(outer['python_launch_to_exit_seconds'])
assert 0 < outer['python_launch_to_exit_seconds'] <= 600 and outer['automatic_retries'] == 0
assert outer['source_changed'] == producer['source_changed'] == []
assert outer['source_before'] == outer['source_after']
for path, digest in outer['source_before'].items(): assert sha(path) == digest
assert sha(outer['wrapper']) == outer['wrapper_sha256'] == 'ea0dd0c425f32f7c28f0988e35951a9b0b12cd5e4a2160d78c64d9d15f087099'
for name, digest in outer['artifacts'].items(): assert sha(DEST/name) == digest
launcher = read('external_launch_receipt.json')
assert launcher['process'] == outer['inner_process']
assert launcher['process']['status'] == 'exited' and launcher['process']['exitcode'] == 0
assert launcher['process']['windows_job_kill_on_close'] is True
assert launcher['process']['child_released_only_after_job_assignment'] is True
for name, digest in launcher['artifacts'].items(): assert sha(DEST/name) == digest
assert producer['status'] == 'completed_finite_request_cohort' and producer['campaign_sha256'] == SHA
ref(producer['verification'])
assert producer['loaded_project_sources_entry'] == producer['loaded_project_sources_exit']
assert len(plan['source_sha256']) == 218 and len(plan['compiled_source_archive_sha256']) == 67
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
for key, declared in plan['rows'].items():
    row, checked = ledger[key], verifier['rows'][key]
    assert row['status'] == 'raw_saved' and {n: row[n] for n in ('case', 'method', 'fault')} == declared
    ref(row['raw']); raw = loads(gzip.decompress(Path(row['raw']['path']).read_bytes()))
    assert raw['key'] == key and raw['specification'] == declared
    assert raw['outcome'] == checked['business']
    raw_outcomes[key] = raw['outcome']
    assert raw['native_state_sha256'] == checked['native_state_sha256']
    assert checked['audit_status'] == 'passed' and checked['original_root_replay_verified'] is True
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
assert len(normal) == 6 and sum(row['strictly_improved'] for row in normal.values()) == 1
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
report = {'schema': 'g31.owned_C18.root_saved_readback.v1', 'status': 'passed_independent_saved_integrity_and_denominator',
    'script_sha256': sha(__file__), 'campaign_sha256': SHA, 'rows': observed, 'normal_pairs': normal,
    'complete_root_canonical_bytes_verified': complete_bytes, 'raw_gzip_rows_read': 18,
    'source_current_and_archive_count': 218, 'compiled_archive_files': 67, 'hash_reads': hashes,
    'closed_roots': 16, 'unknown_roots': 2, 'observed_under100': 0,
    'closed_ms': {'min': min(closed), 'median': statistics.median(closed), 'max': max(closed)},
    'whole_python_actual_seconds': outer['python_launch_to_exit_seconds'],
    'elapsed_saved_review_seconds_before_export': time.perf_counter()-START,
    'limits': ['Saved normalized evidence canonical bytes/hash/ledger/clocks independently reconstructed for all18. Full raw outcomes and strict normal pairs matched saved audit.',
        'No native/model/C invocation. Original endpoint/physics/RPC replay acceptance is producer audit evidence, not a second independently implemented physics checker.',
        'Current project sources/archive, actual binary/DLL files rehashed. Full6124 toolchain domain not rehashed here; original actual entry/exit/saved checks are retained.',
        'Direct C/fallback counts unknown. Finite2 original cohort; no causal speed/full32/all-day/joint-effectiveness or100ms certificate.']}
with (DEST/'root_saved_review_001.json').open('x', encoding='utf8') as stream: json.dump(report, stream, indent=2)
print(json.dumps({'status': report['status'], 'sha256': sha(DEST/'root_saved_review_001.json'), 'closed_ms': report['closed_ms'], 'rows': 18, 'whole_saved_review_seconds': time.perf_counter()-START}))
