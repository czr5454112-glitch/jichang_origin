"""Unprofiled saved-evidence parity; no native execution or model training."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_repeated_domain as current
from scripts.experiments.g31_ics_circulation import foundation_repeated_native as native

HERE = Path(__file__).resolve().parent
plan = json.loads((HERE.parent/'A5_train_async_001/plan.json').read_text())
key = next(key for key in plan['source_archive'] if Path(key).name == 'foundation_repeated_domain.py')
archive = HERE.parent/'A5_train_async_001'/plan['source_archive'][key]
assert hashlib.sha256(archive.read_bytes()).hexdigest() == '3bf1f2d520362eda81be1110b01a1698bacf677b7b5507222bac98d1e021afa2'
spec = importlib.util.spec_from_file_location('scripts.experiments.g31_ics_circulation.R1_archived_domain', archive)
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
initialization = current.initialize_static_registry()
seen = {}; references = {}
for path in sorted(HERE.parent.glob('*/raw.json.gz')):
    folder = path.parent
    if not all((folder/name).exists() for name in ('acceptance.json', 'receipt.json', 'worker_report.json')):
        continue
    accepted = json.loads((folder/'acceptance.json').read_text())
    if accepted['status'] != 'closed_run_acceptance_passed' or accepted['active'] is not False:
        continue
    raw = json.loads(gzip.decompress(path.read_bytes()))
    for attempts in raw.get('repeated_attempts', {}).values():
        for attempt in attempts:
            evidence = attempt['evidence']; identity = current.digest(evidence)
            item = seen.setdefault(identity, {'evidence': evidence, 'origins': [], 'reference': raw['specification'].get('reference')})
            item['origins'].append(folder.name)
    references[folder.name] = hashlib.sha256(path.read_bytes()).hexdigest()

rows = []
for index, (identity, item) in enumerate(seen.items()):
    evidence = item['evidence']; actions = old.ACTIONS[evidence['phase']]
    begin = time.perf_counter_ns(); previous = old.evaluate(evidence, actions); old_ms = (time.perf_counter_ns()-begin)/1e6
    begin = time.perf_counter_ns(); actual = current.evaluate(evidence, actions); new_ms = (time.perf_counter_ns()-begin)/1e6
    assert previous == actual, ('R1_full_prediction_mismatch', item['origins'], evidence['at'], previous, actual)
    deltas = {}
    for action in actions:
        before = native.protected(previous['candidate_results'].get(action, {}), item['reference'])
        after = native.protected(actual['candidate_results'].get(action, {}), item['reference'])
        assert before == after, ('R1_per_job_guard_mismatch', identity, action)
        deltas[action] = before
    rows.append({'evidence_sha256': identity, 'origins': item['origins'], 'phase': evidence['phase'],
        'at_sim_s': evidence['at'], 'status': actual['status'], 'reasons': actual.get('reasons'),
        'complete_result_digest': current.digest(actual), 'all_candidate_results_exact_equal': True,
        'zero_tolerance_guard_exact_equal': True, 'candidate_guards': deltas,
        'offline_replay_wall_ms': {'old': old_ms, 'R1': new_ms}})
    print(json.dumps({'index': index+1, 'of': len(seen), 'status': actual['status'], 'exact_equal': True}), flush=True)

result = {'schema': 'g31.foundation.R1_saved_evidence_parity.v1', 'status': 'passed_exact_all_candidates_and_guards',
    'old_domain': {'path': str(archive.resolve()), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()},
    'new_domain': {'path': current.__file__, 'sha256': hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest()},
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'static_initialization': initialization,
    'closed_raw_sha256': references, 'deduplicated_evidence_count': len(rows),
    'supported_evidence_count': sum(row['status'] == 'conditional_current_seed' for row in rows),
    'refused_evidence_count': sum(row['status'] != 'conditional_current_seed' for row in rows), 'evidence': rows,
    'timing_scope': 'Sequential unprofiled pure evaluate replay on saved detached evidence, original first then R1; not native complete current path or SLA. Other nonnative host work may be active.',
    'native_started': False, 'full_request_100ms_certified': False, 'training_or_reselection': False}
output = HERE/'R1_saved_evidence_parity_001.json'; assert not output.exists()
output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf8')
print(json.dumps({key: result[key] for key in ('status', 'deduplicated_evidence_count', 'supported_evidence_count', 'refused_evidence_count')}))
