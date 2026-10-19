"""Pure preparation/hash/parity audit; never constructs a native session."""
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'scripts').is_dir())
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_observations_v2 as decoder


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main():
    cycle = HERE.parent
    old_dir = cycle / 'C00_receiver_admission_500k_001'
    plan_path = HERE / 'plan.json'
    plan = json.loads(plan_path.read_text())
    old = json.loads((old_dir / 'plan.json').read_text())
    for source, digest in plan['source_sha256'].items():
        assert sha(source) == digest, source
        assert sha(HERE / plan['source_archive'][source]) == digest, source
    for key in ['input', 'mapping', 'business_contract', 'business_audit', 'crosswalk',
                'native_contract_reference', 'semantic_gate_reference', 'binary', 'legacy_manifest']:
        assert sha(plan[key]['path']) == plan[key]['sha256'], key
    for item in plan['runtime_references']:
        assert sha(item['path']) == item['sha256']
    assert Path(plan['input']['path']).read_bytes() == Path(old['input']['path']).read_bytes()
    same_keys = ['business_semantic_sha256', 'non_business_semantic_sha256',
        'protocol_input_semantic_sha256', 'physical_start', 'warmup_end', 'window_boundaries',
        'warmup_segment_seconds', 'physical_input_horizon', 'controller',
        'receiver_admission_policy', 'resource_contract', 'offered_business_count', 'inventory',
        'node_count', 'edge_count', 'binary', 'planner_activate_at', 'same_live_session_across_boundaries',
        'reset_at_window_boundary', 'all_unfinished_preserved']
    for key in same_keys:
        assert plan[key] == old[key], key
    assert (plan['soft_stop_seconds'], plan['hard_process_seconds']) == (420, 480)
    assert plan['native_branch_budget'] == 1 and plan['automatic_retries'] == 0

    bench = cycle / 'C_observation_v2_benchmark_001'
    original = old_dir / 'C00/policy_observations.jsonl.gz'
    decoded = decoder.read_records(bench / 'new.jsonl.gz')
    checked = 0
    with gzip.open(original, 'rt', encoding='utf-8') as f:
        for expected, actual in zip(itertools.islice(f, 24), decoded, strict=True):
            expected = json.loads(expected)
            assert actual['schema'] == decoder.SCHEMA
            actual['schema'] = expected['schema']
            assert decoder.encoded(actual) == decoder.encoded(expected), checked
            checked += 1
    assert checked == 24
    parity = {'status': 'passed', 'native_sessions': 0,
        'exact_JSON_byte_parity_records': checked,
        'only_reconstructed_field_changed': 'schema',
        'comparison': 'Direct original failed-run rows versus decoder; no scope or other field omitted',
        'record_scope': expected['scope'],
        'source_sha256': sha(decoder.__file__),
        'original': {'path': str(original), 'sha256': sha(original)},
        'encoded': {'path': str(bench / 'new.jsonl.gz'), 'sha256': sha(bench / 'new.jsonl.gz')},
        'blobs': {'path': str(bench / 'new.blobs.jsonl.gz'), 'sha256': sha(bench / 'new.blobs.jsonl.gz')}}
    save(bench / 'decoder_freeze_validation.json', parity)

    spec = json.loads((cycle / 'C00_receiver_admission_500k_001_task.json').read_text())
    spec.update(task_id=HERE.name,
        module='scripts.experiments.g31_ics_circulation.foundation_airport_recorded_campaign',
        args=['--launch', '--output', str(HERE)], hard_seconds=540)
    refs = [plan_path] + [Path(plan[k]['path']) for k in ['input', 'mapping', 'business_contract',
        'business_audit', 'crosswalk', 'native_contract_reference', 'semantic_gate_reference']]
    spec['sources'] = list(plan['source_sha256']) + list(map(str, refs))
    spec['assessment']['path'] = str(HERE / 'receipt.json')
    spec['next_action'] = ('Audit complete-window status versus actual and last complete clocks; '
        'verify all28506 business identities, source/archive chain, node49 receiving leases, '
        'continued motion and exact decoded public observations. Decide C10 only after '
        'successful common warmup and real post57660 available supply without baseline intents. '
        'Retain prior100000 censored and500000 hard-timeout attempts unchanged; no automatic retry.')
    spec_path = cycle / (HERE.name + '_task.json')
    save(spec_path, spec)
    audit = {'schema': 'g31.airport_recorded_calibration_preparation_audit.v1',
        'status': 'prepared_not_executed', 'native_sessions': 0,
        'source_files_and_archives_verified': len(plan['source_sha256']),
        'plan_sha256': sha(plan_path), 'task_spec': str(spec_path), 'task_spec_sha256': sha(spec_path),
        'task_source_count': len(spec['sources']), 'native_branch_budget': 1, 'automatic_retries': 0,
        'budgets_seconds': {'soft': 420, 'inner_hard': 480, 'outer_hard': 540},
        'same_input_bytes_as_prior500k': True, 'input_sha256': plan['input']['sha256'],
        'protocol_input_semantic_sha256': plan['protocol_input_semantic_sha256'],
        'same_fields_as_prior500k': same_keys,
        'policy_observation_contract': plan['policy_observation_contract'],
        'soft_checkpoint_contract': plan['soft_checkpoint_contract'],
        'pure_tests': {'path': str(ROOT / 'tests/test_g31_airport_recording_v2.py'),
            'sha256': sha(ROOT / 'tests/test_g31_airport_recording_v2.py'), 'passed': 9,
            'command': 'python -m pytest tests/test_g31_airport_recording_v2.py --basetemp outputs/airport_recording_v2_tests_005 -q -x'},
        'decoder_freeze_validation': {'path': str(bench / 'decoder_freeze_validation.json'),
            'sha256': sha(bench / 'decoder_freeze_validation.json')},
        'recording_cost_benchmark': {'path': str(bench / 'report.json'), 'sha256': sha(bench / 'report.json'),
            'scope': '24 actual records; exact parity, not native throughput or worst-case guarantee'},
        'C10_prepared': False}
    save(HERE / 'preparation_audit.json', audit)
    print(json.dumps({k: audit[k] for k in ['status','plan_sha256','task_source_count','source_files_and_archives_verified','task_spec','budgets_seconds']}))


if __name__ == '__main__':
    main()
