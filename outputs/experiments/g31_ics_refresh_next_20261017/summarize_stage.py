"""Index verified stage artifacts without inference or native execution."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def read(relative):
    return json.loads((BASE / relative).read_bytes())


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    output = BASE / 'stage_summary_001.json'
    if output.exists():
        raise SystemExit('immutable_stage_summary_already_exists')
    timings = read('incremental_abba_001/report.json')
    native = read('independent_native_001/report.json')
    pair = read('freshpair_001/worker_report.json')
    independent_pair = read('independent_freshpair_003/report.json')
    audit = read('freshpair_001/refresh_audit.json')
    tests = read('final_validation_001/receipt.json')
    checks = (
        timings['status'] == 'completed_exact_incremental_comparison',
        len(timings['rows']) == 24,
        all(row['saved_full_seed_and_predictions_exact'] for row in timings['rows']),
        native['status'] == 'passed_exact_native_and_current_model_parity',
        not native['failed_checks'],
        pair['status'] == 'completed_successful_refresh_probe',
        independent_pair['status'] == 'passed',
        audit['audit']['status'] == 'full_refresh_required',
        tests['status'] == 'passed',
        tests['counts']['failures'] == tests['counts']['errors'] == tests['counts']['skipped'] == 0,
    )
    if not all(checks):
        raise SystemExit('required_stage_gate_failed')
    files = ('profiling_001/report.json', 'validation_catalog_001/receipt.json',
        'targeted_001/receipt.json', 'incremental_abba_001/plan.json', 'incremental_abba_001/report.json',
        'incremental_abba_001/receipt.json', 'native_001/receipt.json', 'independent_native_001/report.json',
        'freshpair_001/receipt.json', 'freshpair_001/worker_report.json', 'freshpair_001/refresh_audit.json',
        'freshpair_001/probe_observations.json', 'independent_freshpair_003/report.json',
        'final_validation_001/receipt.json',
        'final_validation_001/tests.xml')
    result = {
        'schema': 'g31.refresh_next.stage_summary.v1', 'status': 'completed_bounded_stage_not_final_system',
        'artifacts': {name: reference(BASE / name) for name in files},
        'producer': reference(__file__), 'tests': tests['counts'],
        'incremental_abba_contexts': timings['contexts'], 'candidate_predictions_compared': 48,
        'default_native_independent_checks': len(native['checks']),
        'default_native_physical_summary': native['physical_summary'],
        'default_native_cutpoints': [{'owner': row['owner'], 'at': row['at'], 'timings': row['timings']}
                                     for row in native['cutpoints']],
        'fresh_pair_times': pair['observation_times'], 'fresh_pair_physical_parity': pair['physical_parity'],
        'independent_fresh_pair_checks': independent_pair['checks'],
        'fresh_pair_per_job_delta': pair['actual_terminal_comparison']['per_job_delta'],
        'fresh_pair_refresh_reasons': audit['audit']['reasons'],
        'fresh_pair_changed_dependencies': audit['audit']['changed_dependencies'],
        'independent_scene_count': 1, 'complete_request_100ms_certified': False,
        'cross_event_prediction_cache_enabled': False, 'local_suffix_reuse_certified': False,
        'new_business_gain': False, 'new_multi_action_protected_later_choice': False,
        'multi_step_RL_trained': False, 'airport_scale_validated': False,
        'git_commit_or_push_performed': False,
    }
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': result['status'], 'summary': reference(output)}))


if __name__ == '__main__':
    main()
