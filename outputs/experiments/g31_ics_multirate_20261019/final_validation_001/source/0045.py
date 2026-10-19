"""Offline saved-evidence regression; never creates native execution authority."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
import types
import zipfile
from pathlib import Path

from . import live_obligation_initial_candidate_provider as provider
from . import live_obligation_same_information_search as search
from .native_host import audit_result

CASES = ('mechanism', 'no_overlap', 'insufficient_advance')
JOBS = ('loaded', 'receiver', 'reuse1', 'reuse2', 'blocker')
FIELDS = ('initial_action', 'empty_departure', 'return_delay', 'later_action')
SOURCE = 'scripts/experiments/g31_ics_circulation/live_obligation_initial_candidate_provider.py'
BASE = Path('outputs/experiments/g31_ics_lt2_sustained_20261014')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def snapshot_difference(repo, snapshot):
    rows = []
    matched = 0
    with zipfile.ZipFile(snapshot) as archive:
        manifest = json.loads(archive.read('PACKAGE_MANIFEST.json'))
        for item in manifest['files']:
            if not item['path'].startswith('repo/'):
                continue
            relative = item['path'][5:]
            current = repo / relative
            actual = digest(current.read_bytes()) if current.is_file() else None
            if actual == item['sha256']:
                matched += 1
            else:
                rows.append({'path': relative, 'snapshot_sha256': item['sha256'], 'current_sha256': actual})
    return {'snapshot_sha256': digest(snapshot.read_bytes()), 'matched_files': matched,
            'differences': rows, 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
            'scope': 'Current files compared to the reviewed ZIP, not an assertion that ZIP equals HEAD.'}


def load_evidence(repo):
    forecast_rows = read(repo / BASE / 'owned_full32_runtime_prepare_001/rows.json')
    batches, cases, raw_hashes = {}, {}, {}
    for case in CASES:
        batch = {'rows': [], 'counts': {'scope': 'saved forecasts; no provider recomputation'}, 'provider_preseal_seconds': None}
        completions, actions = [], []
        for index in range(32):
            key = f'{case}/vector_{index:02d}'
            path = repo / BASE / 'live_obligation_unloading_native_prepare_001' / (key + '.json.gz')
            raw = read(path)
            actual = {job['business_bag_id']: job['completed_at'] for job in raw['result']['jobs']}
            assert len(actual) == 5 and set(actual) == set(JOBS)
            assert all(job['status'] == 'completed' for job in raw['result']['jobs'])
            assert actual == raw['summary']['completion']
            unloads = {event['business_bag_id']: event['time'] for event in raw['result']['receipts'] if event['event'] == 'UNLOAD_COMPLETE'}
            assert actual == unloads
            assert len(raw['result']['trays']) == 3
            data = copy.deepcopy(raw['input'])
            data['transfers'] = [{**call['request'], 'issued_at': call['at']} for call in raw['calls'] if call['kind'] == 'transfer' and not call['retry']]
            assert audit_result(data, raw['result'])['status'] == 'passed'
            saved = forecast_rows[key]
            prediction_path = repo / 'outputs' / saved['prediction']['path'].replace('\\', '/').split('/outputs/', 1)[1]
            assert digest(prediction_path.read_bytes()) == saved['prediction']['sha256']
            prediction = read(prediction_path)
            assert prediction['completion'] == actual
            action = raw['specification']['vector']
            assert action == saved['action']
            batch['rows'].append({'candidate_index': index, 'action': action, 'status': 'conditional_forecast', 'completion': actual, 'prediction': prediction})
            completions.append(actual)
            actions.append(action)
            raw_hashes[key] = {'raw_sha256': digest(path.read_bytes()), 'prediction_sha256': saved['prediction']['sha256']}
        assert actions[4] == {'initial_action': 'native_default', 'empty_departure': 2.2100000000000004, 'return_delay': 0.0, 'later_action': 'native_default'}
        safe = [index for index in range(32) if all(completions[index][job] <= completions[4][job] for job in JOBS)]
        optimum = min(safe, key=lambda index: (sum(completions[index][job] for job in JOBS), index))
        mixed = {field: actions[12 if field in ('initial_action', 'return_delay') else 25][field] for field in FIELDS}
        assert actions.index(mixed) == 9
        cases[case] = {'incumbent': 4, 'finite32_optimum': optimum, 'protected_indices': safe,
                       'four_vectors': {str(index): {'action': actions[index], 'completion': completions[index],
                           'strict_deltas': {job: completions[index][job] - completions[4][job] for job in JOBS}} for index in (4, 12, 25, 9)},
                       'composition': {'owner_A': 12, 'owner_B': 25, 'composed': 9}}
        batches[case] = batch
    assert 12 in cases['mechanism']['protected_indices'] and 25 in cases['mechanism']['protected_indices']
    assert 9 not in cases['mechanism']['protected_indices']
    return batches, cases, raw_hashes


def replay(module, data, method):
    previous = search.provider
    counts = {'full_batch_json_decodes': 0}
    encoded_size = len(provider.encoding(data))
    def profile(frame, event, arg):
        if event == 'call' and frame.f_code is json.loads.__code__:
            payload = frame.f_locals.get('s')
            if isinstance(payload, (str, bytes)) and len(payload) == encoded_size:
                counts['full_batch_json_decodes'] += 1
    search.provider = module
    started = time.perf_counter_ns()
    sys.setprofile(profile)
    try:
        batch = module.CandidateBatch(module._TOKEN, data, None)
        result = search.select(batch, method=method, incumbent_index=4)
        exported = batch.audit_copy()
        encoded = provider.encoding({'selection': result, 'audit': exported})
    finally:
        sys.setprofile(None)
        search.provider = previous
    elapsed = time.perf_counter_ns() - started
    stable = {key: value for key, value in result.items() if key != 'selection_before_return_seconds'}
    return {'selected_index': result['selected_index'], 'query_indices': result['accounting']['query_indices'],
            'visited': result['visited_indices'], 'full_batch_json_decodes': counts['full_batch_json_decodes'],
            'elapsed_ns': elapsed, 'export_bytes': len(encoded.encode()), 'stable_sha256': digest(provider.encoding(stable).encode())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('audit/review_20261017'))
    args = parser.parse_args()
    repo = Path.cwd()
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / '20261016_review_regressions.json').exists():
        raise FileExistsError('Preserve the existing regression evidence; use a new registered output directory.')
    save(args.output / 'snapshot_difference.json', snapshot_difference(repo, args.snapshot))
    batches, cases, hashes = load_evidence(repo)
    legacy_source = subprocess.check_output(['git', 'show', 'a7f7821f:' + SOURCE], cwd=repo)
    legacy = types.ModuleType(provider.__package__ + '.offline_review_legacy_provider')
    legacy.__package__ = provider.__package__
    exec(compile(legacy_source, '<offline_review_legacy_provider>', 'exec'), legacy.__dict__)
    selectors = {}
    for case in CASES:
        selectors[case] = {}
        for method in search.METHODS:
            result = replay(provider, batches[case], method)
            selectors[case][method] = result
        assert selectors[case]['coordinate_strict']['selected_index'] == cases[case]['finite32_optimum']
        assert len(selectors[case]['coordinate_strict']['query_indices']) == 14
    abba = []
    for block in range(4):
        for position, arm in enumerate(('A', 'B', 'B', 'A')):
            entries = {case: replay(legacy if arm == 'A' else provider, batches[case], 'finite_MPC') for case in CASES}
            abba.append({'block': block, 'position': position, 'arm': arm, 'cases': entries,
                         'elapsed_ns': sum(row['elapsed_ns'] for row in entries.values())})
    for case in CASES:
        assert len({row['cases'][case]['stable_sha256'] for row in abba}) == 1
        assert all(row['cases'][case]['full_batch_json_decodes'] <= 1 for row in abba if row['arm'] == 'B')
    clocks = []
    for path in sorted((repo / 'outputs/sicm1/raw').rglob('*.json.gz')):
        record = read(path)['root_records'][0]
        elapsed = record['outside_return_ns'] - record['value']['evidence']['root_started_ns']
        assert elapsed == record['warm_caller_elapsed_ns']
        clocks.append({'raw': path.relative_to(repo).as_posix(), 'closed': record['closed'], 'milliseconds': elapsed / 1e6})
    assert len(clocks) == 18 and sum(row['closed'] for row in clocks) == 16
    output = {'schema': 'g31.review_saved_regressions.v1', 'scope': 'Saved data only; no native handle, predictions recomputed or execution authority.',
              'python': sys.version, 'platform': platform.platform(), 'cases': cases, 'selectors': selectors,
              'timing_instrumentation': 'sys.setprofile is enabled for structural JSON decode counts in every replay; these are instrumented saved-construction timings, not uninstrumented latency or isolated whole-request speedup.',
              'evidence_hashes': hashes, 'native_branches_checked': 96, 'exact_prediction_endpoints': 480,
              'logical_queries_are_not_model_savings': True,
              'original18': {'rows': clocks, 'closed_median_ms': statistics.median(row['milliseconds'] for row in clocks if row['closed']),
                             'all_observations_median_ms': statistics.median(row['milliseconds'] for row in clocks), 'unknown': 2},
              'abba': abba, 'abba_totals_ms': {arm: sum(row['elapsed_ns'] for row in abba if row['arm'] == arm) / 1e6 for arm in ('A', 'B')},
              'legacy_source_sha256': digest(legacy_source), 'current_source_sha256': digest((repo / SOURCE).read_bytes()),
              'complete_request_100ms_certified': False}
    save(args.output / '20261016_review_regressions.json', output)
    print(json.dumps({'saved96': 96, 'exact_endpoints': 480, 'coordinate_queries': 14,
                      'abba_totals_ms': output['abba_totals_ms'], 'complete_request_100ms_certified': False}))


if __name__ == '__main__':
    main()
