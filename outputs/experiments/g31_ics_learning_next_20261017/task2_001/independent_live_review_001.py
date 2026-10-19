"""Read saved artifacts only; no project imports, prediction or native calls."""
import gzip
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent / 'live_001'
OUTPUT = Path(__file__).with_suffix('.json')
ORDER = ('compatible8', 'rule4', 'prefix_cost4', 'linear4', 'mlp4')
JOBS = ('loaded', 'receiver', 'reuse1', 'reuse2', 'blocker')


def encoding(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':'))


def exact(left, right):
    return encoding(left) == encoding(right)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def reference(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def known(row):
    return row['status'] == 'conditional_forecast' and set(row['completion']) == set(JOBS) and all(
        type(value) in (int, float) and math.isfinite(value) for value in row['completion'].values())


def protected(row, incumbent):
    return known(row) and all(row['completion'][job] <= incumbent['completion'][job] for job in JOBS)


def total(row):
    return sum(row['completion'][job] for job in JOBS)


def main():
    assert not OUTPUT.exists()
    receipt = read(BASE / 'receipt.json')
    worker = read(BASE / 'worker_report.json')
    plan = read(BASE / 'plan.json')
    native_receipt = read(BASE / 'native/receipt.json')
    assert sha(BASE / 'worker_report.json') == receipt['worker_report']['sha256']
    assert sha(BASE / 'plan.json') == worker['plan']['sha256']
    assert sha(BASE / 'native/receipt.json') == worker['native_receipt']['sha256']
    assert sha(BASE / 'native/raw.json.gz') == native_receipt['raw_artifact']['sha256']
    assert receipt['process']['status'] == 'exited' and receipt['process']['exitcode'] == 0
    assert receipt['process']['hard_timeout_seconds'] == 150 and receipt['automatic_retries'] == 0
    assert native_receipt['status'] == 'assessed'
    assert native_receipt['run_acceptance_status'] == 'closed_run_acceptance_passed'
    for path, expected in plan['source_sha256'].items():
        assert sha(path) == expected
        assert sha(BASE / 'source' / Path(path).relative_to(ROOT)) == expected
    for artifact in plan['artifact_pins']:
        assert sha(artifact['path']) == artifact['sha256']
    raw = json.loads(gzip.decompress((BASE / 'native/raw.json.gz').read_bytes()))
    advice = raw['initial_evaluator_advice']['B']
    assert exact(advice, read(BASE / 'callback_complete.json'))
    assert advice['order'] == list(ORDER) and advice['teacher_available_to_actor'] is False
    teacher_owner = raw['initial_owners']['B']
    teacher = teacher_owner['selection']['provider_evidence']
    teacher_rows = {row['candidate_index']: row for row in teacher['rows']}
    assert set(teacher_rows) == set(range(32))
    incumbent = teacher_rows[4]
    fields = ('initial_action', 'return_delay')
    compatible = [index for index, row in teacher_rows.items() if all(
        exact(row['action'][field], incumbent['action'][field]) for field in fields)]
    assert compatible == [0, 1, 4, 5, 8, 9, 12, 13]
    legal_protected = [index for index in compatible if protected(teacher_rows[index], incumbent)]
    optimum = min(legal_protected, key=lambda index: (total(teacher_rows[index]), index))
    assert optimum == 12
    variants = {}
    for name in ORDER:
        measured = advice['variants'][name]
        report = measured['report']
        requested = report['requested_indices']
        rows = {row['candidate_index']: row for row in report['rows']}
        assert report['owner'] == 'B' and report['initial_public_sha256'] == advice['public_sha256']
        assert report['actual_collection_at'] == advice['at'] == teacher_owner['collection']['at']
        assert advice['public_sha256'] == teacher_owner['collection']['public_sha256']
        parity = {}
        for index in requested:
            assert known(rows[index]) and known(teacher_rows[index])
            assert all(exact(rows[index][field], teacher_rows[index][field])
                for field in ('action', 'completion', 'prediction'))
            parity[str(index)] = hashlib.sha256(encoding(rows[index]['prediction']).encode()).hexdigest()
        for index, row in rows.items():
            if index not in requested:
                assert row.get('prediction') is None and row.get('completion') is None
                assert row['status'] == 'not_requested'
        groups = report['groups']
        assert set(index for group in groups for index in group['candidate_indices']) == set(requested)
        assert len({group['prefix_index'] for group in groups}) == len(groups)
        counted = {key: sum(group['detail']['counts'][key] for group in groups)
            for key in ('initial_engines', 'initial_advances', 'prefix_same_resumes', 'future_forks', 'future_resumes')}
        assert all(report['counts'][key] == value for key, value in counted.items())
        assert report['counts']['context_constructions'] == len(groups)
        for group in groups:
            assert group['binding_error'] is None
            assert set(group['predictions']) == {rows[index]['action']['later_action'] for index in group['candidate_indices']}
        assert len(requested) == (8 if name == 'compatible8' else 4)
        assert len(groups) == (4 if name == 'compatible8' else 2)
        binding = report['source_binding']
        proof = binding['before_close']['proof_binding']
        assert binding['status'] == 'closed' and binding['close_completed'] is True
        assert proof['proof_uses'] == 1 + 2 * len(requested)
        selected = report['selection']['selected_index']
        assert selected in requested and selected in legal_protected
        assert report['selection']['current_revalidation']['status'] == 'fresh_local_component_proposal'
        assert report['selection']['current_revalidation']['native_request_submitted'] is False
        regret = total(teacher_rows[selected]) - total(teacher_rows[optimum])
        assert exact(selected, worker['variants'][name]['selected_compatible_index'])
        assert math.isclose(regret, worker['variants'][name]['component_compatible_regret_s'], abs_tol=1e-12)
        variants[name] = {'requested_indices': requested, 'actual_prefix_count': len(groups),
            'actual_counts_recomputed_from_groups': counted, 'source_proof_uses': proof['proof_uses'],
            'strict_full_prediction_sha256': parity, 'selected_compatible_index': selected,
            'conditional_compatible_regret_s': regret,
            'selected_per_job_delta_s': {job: rows[selected]['completion'][job] - incumbent['completion'][job] for job in JOBS},
            'unrequested_global_count': 32 - len(requested), 'unrequested_compatible_count': 8 - len(requested),
            'through_seal_wall_ms': measured['compute_wall_ms'],
            'seal_wall_ms': measured['seal_wall_ms'],
            'through_export_and_current_check_wall_ms': measured['through_export_and_current_check_wall_ms'],
            'through_export_and_current_check_cpu_ms': measured['through_export_and_current_check_cpu_ms'],
            'exclusive_outer_stage_ns': report['timing']['exclusive_outer_stage_ns']}
    baseline_path = Path(raw['saved_baseline_comparison']['reference']['path'])
    assert sha(baseline_path) == raw['saved_baseline_comparison']['reference']['sha256']
    baseline = json.loads(gzip.decompress(baseline_path.read_bytes()))
    assert exact(raw['input'], baseline['input'])
    assert all(exact(raw['result'][field], baseline['result'][field]) for field in ('jobs', 'trays', 'receipts'))
    assert all(raw['initial_owners'][owner]['selection']['selected_index'] == 4 for owner in ('A', 'B'))
    result = {'status': 'passed_independent_saved_artifact_review', 'model_or_native_calls': 0,
        'strict_parity_encoding': 'sorted JSON preserving bool/int/float/negative-zero; no tolerance',
        'inputs': [reference(BASE / name) for name in ('receipt.json', 'worker_report.json', 'plan.json', 'native/raw.json.gz')],
        'frozen_source_count': len(plan['source_sha256']), 'artifact_pin_count': len(plan['artifact_pins']),
        'context': {'owner': 'B', 'at': advice['at'], 'public_sha256': advice['public_sha256']},
        'variants': variants, 'compatible_domain': compatible, 'compatible_protected_indices': legal_protected,
        'compatible_optimum_index': optimum, 'native_initial_selected_indices': {'A': 4, 'B': 4},
        'native_baseline_jobs_trays_receipts_and_input_strict_equal': True,
        'process_wall_seconds': receipt['process']['wall_seconds'], 'hard_process_seconds': 150,
        'teacher': {'actual_counts': teacher['counts'],
            'through_seal_wall_ms': teacher_owner['selection']['accounting']['provider_measured_through_seal_seconds'] * 1000,
            'full_initial_call_wall_ms': teacher_owner['call_wall_ms']},
        'timing_boundary': {
            'through_seal': 'Current origin/ranking, static bind, fresh contexts, guarded prefix/suffix work, final origin, close, protected selection/current revalidation, immutable batch seal.',
            'through_export': 'Through-seal plus batch audit copy and immediate current capability recheck; excludes callback evidence writes after measurement.',
            'excluded_from_variant': 'Precallback live collection, process/module/model load, callback evidence serialization after timing, full32 teacher, native submission/ACK/physical lifecycle.',
            'nested_attribution': 'Guarded prefix/clone/rollout includes source guards; not a pure prediction timer.',
            'process': 'All native lifecycle plus five fixed-order advice paths and later teacher; not a single request or physical simulation duration.'},
        'strict_speed_superiority_claim': False, 'native_business_gain_measured': False,
        'complete_request_100ms_certified': False,
        'conclusion': 'Single mechanism live-B context supports structural K/P reduction and full-prediction parity. Compatible8 and frozen linear4 retain candidate12; rule/cost/MLP retain04. Advice only; no selection of a learned winner for deployment.'}
    with OUTPUT.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'output': str(OUTPUT), 'sha256': sha(OUTPUT),
        'variants': {name: {'selected': row['selected_compatible_index'],
            'regret_s': row['conditional_compatible_regret_s'], 'prefixes': row['actual_prefix_count']}
            for name, row in variants.items()}}))


if __name__ == '__main__':
    main()
