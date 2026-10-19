"""Prepare immutable training inputs only; does not register or run training."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_repeated_supervised as supervised


def main():
    cycle = Path(__file__).resolve().parent
    protocol = cycle / 'repeated_supervised_protocol_001.json'
    plan_path = cycle / 'repeated_supervised_plan_001.json'
    task_path = cycle / 'repeated_supervised_task_001.json'
    output = cycle / 'repeated_supervised_training_001'
    plan = supervised.make_plan(cycle / 'A1_three_prefer3_002', cycle / 'A1_four_prefer3_001', protocol)
    audit_path = cycle / 'repeated_supervised_conversion_001' / 'report.json'
    historical = supervised.read(audit_path)['sources'][0]
    assert historical['source_directory'] == 'A1_three_prefer3_001' and historical['actual_complete_conditional_rows'] == 0
    plan['historical_exclusions'] = {'audit_reference': supervised.reference(audit_path),
        'source_directory': historical['source_directory'], 'bindings': historical['bindings'],
        'training_rows': 0, 'reason': 'unknown conditional reports retained as exclusions; never zero-labelled'}
    pinned = set(plan['source_sha256_pins']) | {str(protocol), str(plan_path), str(audit_path)}
    frozen_summaries = []
    for source, expected in zip(plan['sources'], (6, 9), strict=True):
        directory = Path(source['directory'])
        raw, binding = supervised.closed_native_source(directory, case=source['case'])
        rows, exclusions = supervised.extract_rows(raw, split=source['split'], case=source['case'], origin=binding)
        assert len(rows) == expected and all(len(supervised.value.features(row['observation'], row['action'])) == 123 for row in rows)
        collection = supervised.read(directory / 'plan.json')
        pinned.update(bound['path'] for bound in binding.values())
        pinned.update(str(directory / relative) for relative in collection['source_archive'].values())
        pinned.update(bound['path'] for bound in collection['original_reference_provenance'].values())
        pinned.add(str(directory / 'inputs' / (source['case'] + '/guarded.json')))
        frozen_summaries.append({'split': source['split'], 'case': source['case'], 'rows': len(rows),
            'decision_count': len({row['source_decision_id'] for row in rows}), 'independent_parent_groups': 1,
            'guard_admissible_teacher_differentiated_decisions': 0,
            'excluded': exclusions, 'bindings': binding})
    supervised.write_new(plan_path, plan)
    task = {'task_id': 'repeated_supervised_training_001',
        'module': 'scripts.experiments.g31_ics_circulation.foundation_repeated_supervised',
        'args': ['--plan', str(plan_path), '--output', str(output), '--admission', 'g31_repeated_supervised_001'],
        'inner_admission': 'g31_repeated_supervised_001', 'sources': sorted(pinned),
        'native_branches': 0, 'hard_seconds': 180,
        'requires': ['A1_three_prefer3_002', 'A1_four_prefer3_001'],
        'assessment': {'path': str(output / 'receipt.json'),
            'allowed_statuses': ['completed_supervised_conditional_pretraining']},
        'next_action': 'Audit all three seeds as conditional-teacher distillation; fixed deployment seed 1701, no RL or native benefit claim.'}
    state = supervised.read(cycle / 'manifest.json')
    assert all(state['tasks'][identity]['status'] == 'completed' for identity in task['requires'])
    assert all(Path(path).is_file() for path in pinned)
    supervised.write_new(task_path, task)
    summary = {'schema': 'g31.foundation.repeated_supervised_preparation.v1', 'status': 'prepared_not_executed',
        'plan': supervised.reference(plan_path), 'task': supervised.reference(task_path),
        'sources': frozen_summaries, 'pin_count_excluding_launcher': len(pinned),
        'source_sha256_pins': plan['source_sha256_pins'], 'seeds': [1701, 1702, 1703],
        'epochs': 200, 'per_seed_wall_seconds': 45, 'hard_seconds': 180,
        'native_branches': 0, 'formal_test_read': False, 'model_selection': False,
        'warning': 'All permitted teacher action targets tie within each decision; ranking agreement does not show choice improvement.'}
    supervised.write_new(cycle / 'repeated_supervised_preparation_001.json', summary)
    print(json.dumps({'status': summary['status'], 'plan': str(plan_path), 'task': str(task_path),
        'pin_count_excluding_launcher': len(pinned), 'rows_train': 6, 'rows_development': 9}))


if __name__ == '__main__':
    main()
