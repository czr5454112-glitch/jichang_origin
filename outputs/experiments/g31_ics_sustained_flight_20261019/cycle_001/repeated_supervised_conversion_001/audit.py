"""Actual archived source conversion smoke; no fitting, native, or test split."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_repeated_supervised as converter


def main():
    output = Path(__file__).resolve().parent
    cycle = output.parent
    records = []
    for name, expected_rows, role in (
        ('A1_three_prefer3_001', 0, 'historical_unknown_source_excluded'),
        ('A1_three_prefer3_002', 6, 'registered_training_source_conversion_only'),
    ):
        raw, binding = converter.closed_native_source(cycle / name, case=converter.TRAIN_CASE)
        rows, excluded = converter.extract_rows(raw, split='train', case=converter.TRAIN_CASE, origin=binding)
        assert len(rows) == expected_rows
        assert all(len(converter.value.features(row['observation'], row['action'])) == 123 for row in rows)
        assert all(row['actual_native_return_label'] is False and row['eligible_for_TD'] is False
            and row['native_execution_authority'] is False for row in rows)
        decisions = {}
        for row in rows:
            decisions.setdefault(row['source_decision_id'], []).append(row)
        tied, differentiated = 0, 0
        for group in decisions.values():
            allowed = [row for row in group if row['admissible_under_current_guard']]
            assert len(group) == 3 and len(allowed) == 2
            assert set(row['action_id'] for row in group) == {'native_default', 'prefer_3', 'prefer_8'}
            assert all(len(row['conditional_completion']) == 6 for row in group)
            spread = max(row['target_value'] for row in allowed) - min(row['target_value'] for row in allowed)
            tied += spread <= 1e-9
            differentiated += spread > 1e-9
        if role == 'historical_unknown_source_excluded':
            assert sum('known_full_candidate_report_required' in entry['reason'] for entry in excluded) == 2
        else:
            assert tied == 2 and differentiated == 0
        records.append({'source_directory': name, 'role': role, 'bindings': binding,
            'actual_complete_conditional_rows': len(rows), 'feature_dimensions': 123,
            'guard_admissible_teacher_all_tied_decisions': tied,
            'guard_admissible_teacher_differentiated_decisions': differentiated,
            'rows': [{'decision_id': row['source_decision_id'], 'owner': row['observation']['owner'],
                'at': row['observation']['at'], 'action_id': row['action_id'],
                'target_value': row['target_value'], 'guard_status': row['conditional_protection_status'],
                'admissible_under_current_guard': row['admissible_under_current_guard'],
                'conditional_completion': row['conditional_completion'],
                'evidence_sha256': row['evidence_sha256'], 'conditional_report_sha256': row['conditional_report_sha256']}
                for row in rows], 'excluded': excluded})
    report = {'schema': 'g31.foundation.repeated_supervised_conversion_audit.v1', 'status': 'passed',
        'audit_script': converter.reference(__file__), 'converter_source_pins': converter.source_pins(),
        'protocol': converter.reference(cycle / 'repeated_supervised_protocol_001.json'),
        'native_executed': False, 'models_fitted': 0, 'formal_test_read': False,
        'scope': 'conversion_of_actual_archived_conditional_teacher_labels_not_RL_or_native_policy_improvement',
        'sources': records}
    converter.write_new(output / 'report.json', report)
    print(json.dumps({key: report[key] for key in ('status', 'native_executed', 'models_fitted', 'formal_test_read')}))


if __name__ == '__main__':
    main()
