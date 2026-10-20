"""Explain saved finite native contrasts without selecting any online action."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def diagnose(audit_path):
    audit_path = Path(audit_path).resolve()
    audit = json.loads(audit_path.read_bytes())
    assert audit['status'] == 'saved192_revalidated_no_new_native'
    pins = {str(audit_path): sha(audit_path), str(Path(__file__).resolve()): sha(__file__)}
    rows = audit['rows']
    cases = {}
    selected = {
        'block1_load1': [0, 1, 2, 3, 16, 17, 18, 19],
        'block1_load2': [8, 12, 24, 28],
    }
    for case, indices in selected.items():
        case_rows = {}
        for index in indices:
            key = f'{case}/vector_{index:02d}'
            row = rows[key]
            assert row['status_retained'] == 'assessed'
            path = Path(row['raw_artifact'])
            assert sha(path) == row['raw_sha256']
            pins[str(path)] = row['raw_sha256']
            raw = json.loads(gzip.decompress(path.read_bytes()))
            events = []
            for sequence, event in enumerate(raw['result']['receipts']):
                selected_event = (
                    event['business_bag_id'] in ('loaded', 'receiver', 'reuse1')
                    and event['event'] in ('LOAD_START', 'LOAD_COMPLETE', 'UNLOAD_COMPLETE',
                                           'HOLD_COMPLETE', 'EDGE_ENTER', 'EDGE_EXIT')
                ) or (event['business_bag_id'] == '' and event['time'] < 10
                      and event['event'] in ('EDGE_ENTER', 'EDGE_EXIT'))
                if selected_event:
                    events.append({'receipt_index': sequence, **event})
            decisions = []
            for owner in ('A', 'B'):
                for decision in raw['decisions'][owner]:
                    decisions.append({
                        'owner': owner, 'at': decision['at'], 'phase': decision['phase'],
                        'information_status': decision['information']['status'],
                        'native_request_id': decision['native_request_id'],
                        'declared_action_metadata': decision['executed_first_action'],
                        'local_occupied_nodes': [n for n in decision['actual_local_view']['node_contracts']
                                                 if n.get('occupancy', 0) > 0],
                    })
            case_rows[key] = {
                'vector': row['vector'], 'completion': row['completion'],
                'completion_sum': row['completion_sum'],
                'initial_actual_next': row['initial_actual_next'],
                'first_reuse_actual_next': row['first_reuse_actual_next'],
                'route_operations': row['route_operations'], 'decisions': decisions,
                'receipt_timeline': events,
            }
        cases[case] = case_rows

    def contrast(candidate, control):
        a, b = rows[candidate], rows[control]
        delta = {job: a['completion'][job] - b['completion'][job] for job in a['completion']}
        return {'candidate': candidate, 'control': control, 'per_job_delta': delta,
                'strict_all_five_protection': all(value <= 0 for value in delta.values()),
                'completion_sum_gain': b['completion_sum'] - a['completion_sum']}

    quartet = ['block1_load1/vector_' + n for n in ('00', '16', '01', '17')]
    comparisons = [contrast(quartet[a], quartet[b]) for a, b in ((1, 0), (2, 0), (3, 1), (3, 2), (3, 0))]
    assert all(c['strict_all_five_protection'] and c['completion_sum_gain'] > 0 for c in comparisons)
    sums = [rows[key]['completion_sum'] for key in quartet]
    delayed = contrast('block1_load1/vector_19', 'block1_load1/vector_18')
    assert delayed['completion_sum_gain'] == 0
    assert rows['block1_load1/vector_18']['first_reuse_actual_next'] == 8
    family = audit['family_reviews']['block1_load2']['best_family_contrast']
    assert family['strict_protected'] and family['default_key'].endswith('12') and family['prefer2_key'].endswith('24')
    positive_later = [pair for pair in audit['paired_contrasts']
                      if pair['coordinate'] == 'later_action' and pair['strict_protected']
                      and pair['sum_gain'] is not None and pair['sum_gain'] > 0]
    assert len(positive_later) == 9
    assert all(all(value == 0 for job, value in p['per_job_delta'].items() if job != 'receiver')
               for p in positive_later)
    assert all(sha(path) == digest for path, digest in pins.items())
    return {
        'schema': 'g31.native_preference_matrix.mechanism_diagnosis.v1',
        'status': 'source_bound_saved_event_diagnosis_no_new_native',
        'evidence_sha256': pins,
        'all192_status_counts': audit['counts']['actual_status'],
        'all192_five_jobs_complete': audit['counts']['all192_five_jobs_completed'],
        'all192_physical_audit_passed': audit['counts']['all192_physical_audit_passed'],
        'complete16_family_count': audit['counts']['complete_initial_families'],
        'complete_family_gain_with_later_default': family,
        'protected_initial_and_later_quartet': {
            'row_order_00_10_01_11': quartet, 'completion_sums': sums,
            'comparisons': comparisons,
            'objective_interaction': sums[3] - sums[2] - sums[1] + sums[0],
            'ordinary_coordinate_protected_paths': [[quartet[0], quartet[1], quartet[3]],
                                                     [quartet[0], quartet[2], quartet[3]]],
            'strong_all16_family_reference_complete': False,
            'initial_R1_changed_release_and_same_tray_return': True,
            'R2_return_timing_changes_later_receiving_conflict': True,
            'later_R1_changes_actual_edge_and_improves_receiver': True,
            'rolling_model_chose_actions': False,
        },
        'delayed_R2_negative_control': {
            'comparison': delayed,
            'default_actual_edge_is_7_to_8': True,
            'explanation': 'With requested return delay 0.5, E has entered 1->3 before L reaches the later route opportunity; native default already uses 7->8. The extra preference has zero effect. Delayed return worsens both reuse completions versus immediate return plus explicit prefer_8.',
        },
        'all_nine_positive_later_pairs': positive_later,
        'saved_event_cases': cases,
        'causal_reading': [
            'In block1_load1, actual initial 0->2 advances loaded completion/hold release by 1s and the same L empty return/reuse by 1s. The node1 bypass also permits E supply 1.1s earlier under identical ACK-based recovery.',
            'With immediate L return, native default enters 7->3 before receiver is ready and reserves its receiving slot. Actual prefer_8 instead enters 7->8, allowing receiver 1->3 at8.92 rather than9.851; receiver completes0.931s earlier, other four jobs equal.',
            'This is an actual finite R1-release-R2-timing-later-R1 occupancy mechanism, supported by the registered eight-cell subcube and saved ordered prior-call/physical prefixes. It is not a hidden-native-checkpoint equality certificate.',
            'The strongest complete-family4.1s contrast is a different block1_load2 case and uses later default in both winners. It must not be presented as a later-R1 necessity witness.',
            'Both one-coordinate orders improve while protecting all five jobs in the block1_load1 quartet. Ordinary coordinate search can explain reaching vector17; no new optimizer necessity or online predictive selection is demonstrated.',
        ],
        'limits': [
            'All18 unknowns remain unknown despite physical completion; no historical receipt or assessor status is upgraded.',
            'The block1_load1 full16 reference families are incomplete. This subcube does not establish dominance over all fixed-initial options.',
            'Actions were preregistered counterfactual vectors using lawful delivered inputs, not selected by an online predictor from outcome tables.',
            'No new native execution, full original-flow utility, complete-request100ms or method novelty claim.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    report = diagnose(args.audit)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report_sha256': sha(args.output)}))


if __name__ == '__main__':
    main()
