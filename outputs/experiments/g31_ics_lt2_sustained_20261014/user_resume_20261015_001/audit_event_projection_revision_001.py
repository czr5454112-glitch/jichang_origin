"""One fixed pure96 model revision audit against immutable actual receipts."""
import gzip
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from scripts.experiments.g31_ics_circulation import public_live_obligation_projection as old
from scripts.experiments.g31_ics_circulation import public_live_obligation_event_projection_v2 as new

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = HERE.parent
DEST = OUT / 'live_obligation_event_revision_001'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def encoded(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')

def write(path, obj):
    with path.open('xb') as stream:
        stream.write(encoded(obj))

def main():
    started = perf_counter()
    review_path = OUT / 'live_obligation_native_domain_saved_review_001.json'
    review_sha = '76c2c3c9a11c8e7f4a31b9d25dd498e5305b8f041292b30402ca0a81959bbdb7'
    assert sha(review_path) == review_sha
    review = json.loads(review_path.read_bytes())
    assert not DEST.exists()
    sources = [Path(old.__file__), Path(new.__file__), Path(old.original.__file__), Path(old.original.legacy.__file__), Path(__file__),
               OUT / 'native027_build_001/source/cpp/ics_core/runtime/circulation_recovery_impl.hpp',
               OUT / 'native027_build_001/source/cpp/ics_core/runtime/circulation_runtime_impl.hpp',
               OUT / 'native027_build_001/source/cpp/ics_core/runtime/event_driven_junction.hpp']
    pins = {str(p): sha(p) for p in sources}
    case_order = ['mechanism', 'no_overlap', 'insufficient_advance']
    actions = old.actions()
    plan = {'schema': 'g31.live_event_revision.pure96_plan.v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'case_order': case_order, 'actions': actions, 'source_before': pins, 'saved_review_sha256': review_sha,
        'native_executions': 0, 'model_queries': 96, 'excludes': 'No native action or new benchmark. All retrospective unknowns preserved. No error-bound, validation-set, protection,100ms or novelty claim.',
        'prerecorded_success_condition': 'All34 originally assessed physical trajectories agree exactly in all5 completion times; both no_overlap28/29 event windows match saved native wake/wait/wake/commit. Count and retain every96 result, no epsilon.'}
    DEST.mkdir()
    (DEST / 'raw').mkdir()
    write(DEST / 'preregistered_protocol.json', plan)
    rows = {}
    for case in case_order:
        data = old.inputs()[case]
        bundle = old.assemble(data, old.declared_captures(data))
        for index, action in enumerate(actions):
            key = f'{case}/vector_{index:02d}'
            prior = review['rows'][key]
            native_path = Path(prior['raw_artifact']['path'])
            assert sha(native_path) == prior['raw_artifact']['sha256']
            raw = json.loads(gzip.decompress(native_path.read_bytes()))
            assert raw['specification']['vector'] == action
            actual = raw['summary']['completion']
            assert actual == prior['actual_completion']
            result = new.predict(bundle, action)
            output = DEST / 'raw' / f'{case}_{index:02d}.json.gz'
            with output.open('xb') as stream:
                stream.write(gzip.compress(encoded(result), mtime=0))
            times = result['completion']
            row = {'native': prior['raw_artifact'], 'revised_projection': {'path': str(output), 'sha256': sha(output)},
                'original_status_preserved': prior['producer_status_preserved'], 'status': result['status'],
                'actual': actual, 'revised': times, 'previous': prior['saved_pure_completion'],
                'exact_all5': set(times) == set(actual) and times == actual,
                'actual_minus_revised': {j: actual[j] - times[j] for j in actual if j in times},
                'changed_from_previous': times != prior['saved_pure_completion'],
                'business_status_promoted': False}
            if case == 'no_overlap' and index in (28, 29):
                window = [r for r in result['projected_native_phases'] if 8.649 < r['at'] < 8.652 and r.get('tray') == 'E']
                native_window = [r for r in raw['result']['receipts'] if 8.649 < r['time'] < 8.652 and r.get('tray_id') == 'E']
                expected = [('resource_wake', 8.649999999999995), ('source_arbitration', 8.649999999999995),
                            ('resource_wake', 8.65), ('source_arbitration', 8.651), ('destination_merge_commit', 8.651)]
                row.update(revised_event_window=window, native_receipt_window=native_window,
                           corrected_window_exact=[(r['phase'], r['at']) for r in window] == expected)
            rows[key] = row
    assert len(rows) == 96
    assert all(sha(Path(p)) == digest for p, digest in pins.items())
    assert sha(review_path) == review_sha
    assessed = [r for r in rows.values() if r['original_status_preserved'] == 'assessed']
    exact_assessed = sum(r['exact_all5'] for r in assessed)
    windows = all(rows[f'no_overlap/vector_{n}']['corrected_window_exact'] for n in (28, 29))
    report = {'schema': 'g31.live_event_revision.saved_native_comparison.v1',
        'status': 'passed_retrospective34_exact' if len(assessed) == exact_assessed == 34 and windows else 'unknown_model_discrepancies_remain',
        'plan_sha256': sha(DEST / 'preregistered_protocol.json'), 'native_executions': 0, 'model_queries': 96,
        'source_before_after_match': True, 'all96_retained': len(rows), 'original_assessed': len(assessed),
        'original_unknown': 96 - len(assessed), 'exact_assessed': exact_assessed,
        'exact_all96': sum(r['exact_all5'] for r in rows.values()), 'changed_prediction_rows': [k for k,r in rows.items() if r['changed_from_previous']],
        'both_native_error_windows_reproduced': windows, 'rows': rows, 'elapsed_wall_seconds': perf_counter() - started,
        'limits': ['Retrospective source-derived regression only, not held-out validation or a model error bound.',
                   'All62 original unknown branches remain unknown, including physically completed ones.',
                   'Native recovery time comparison does not relax exact per-job protection.',
                   'No original-airport, complete100ms, online optimizer or novelty claim.']}
    write(DEST / 'report.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'native_executions', 'model_queries', 'exact_assessed', 'exact_all96', 'changed_prediction_rows', 'both_native_error_windows_reproduced', 'elapsed_wall_seconds')}))
    print(json.dumps({'report_sha256': sha(DEST / 'report.json')}))

if __name__ == '__main__':
    main()
