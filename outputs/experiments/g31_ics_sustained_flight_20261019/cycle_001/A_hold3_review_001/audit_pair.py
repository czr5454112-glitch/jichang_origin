"""Independent persisted hold3 baseline/prefer8 audit. Standard library only."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def load(folder):
    folder = OUT.parent / folder
    rawpath = folder / 'raw.json.gz'
    raw = json.loads(gzip.decompress(rawpath.read_bytes()))
    plan, report, receipt, acceptance = (read(folder / n) for n in
        ('plan.json', 'worker_report.json', 'receipt.json', 'acceptance.json'))
    assert receipt['process']['status'] == 'exited' and receipt['process']['exitcode'] == 0
    assert receipt['process']['windows_job_kill_on_close'] and receipt['process']['child_released_only_after_job_assignment']
    assert receipt['worker_report'] == ref(folder / 'worker_report.json')
    assert receipt['status'] == report['status'] == 'completed_native_branch'
    assert report['raw'] == ref(rawpath) and report['source_exit_pins_passed']
    assert report['run_acceptance_status'] == acceptance['status'] == 'closed_run_acceptance_passed'
    assert not acceptance['active'] and acceptance['invalid'] == []
    assert acceptance['run_reference'] == ref(folder / 'plan.json')
    assert acceptance['branch_keys'] == plan['branch_order'] and len(plan['branch_order']) == 1
    key = plan['branch_order'][0]
    inputpath = folder / 'inputs' / (key + '.json')
    assert raw['input'] == read(inputpath) and sha(inputpath) == plan['input_file_sha256'][key]
    assert raw['specification'] == plan['rows'][key]
    for source, relative in plan['source_archive'].items():
        assert sha(folder / relative) == plan['source_sha256'][source] == acceptance['evidence_sha256'][source]
    data, result = raw['input'], raw['result']
    ids = {j['business_bag_id'] for j in data['jobs']}
    assert len(ids) == len(data['jobs']) == len(result['jobs']) == 6
    assert len(data['trays']) == len(result['trays']) == 3
    completed = {}
    for job in result['jobs']:
        identity = job['business_bag_id']
        assert identity in ids and identity not in completed and job['status'] == 'completed'
        arrivals = [e for e in result['receipts'] if e['event'] == 'BAG_ARRIVAL' and e['business_bag_id'] == identity]
        finishes = [e for e in result['receipts'] if e['event'] == 'UNLOAD_COMPLETE' and e['business_bag_id'] == identity]
        offered = next(j for j in data['jobs'] if j['business_bag_id'] == identity)
        assert len(arrivals) == len(finishes) == 1 and arrivals[0]['time'] == offered['arrival']
        assert finishes[0]['time'] == job['completed_at'] <= result['physical_clock']
        completed[identity] = job['completed_at']
    assert all(row['terminal'] and row['ack']['delivered_at'] <= result['physical_clock'] for row in raw['outbox'].values())
    return raw, {'raw': ref(rawpath), 'plan': ref(folder / 'plan.json'),
        'acceptance': ref(folder / 'acceptance.json'), 'input': ref(inputpath),
        'source_archive_count': len(plan['source_archive']), 'all_source_archive_bytes_verified': True,
        'completion_from_native_receipts': completed,
        'terminal_ACK_status_counts': dict(Counter(r['ack']['status'] for r in raw['outbox'].values()))}


def main():
    baseline, base_audit = load('A2_train_baseline_001')
    candidate, candidate_audit = load('A2_train_prefer8_001')
    assert baseline['input'] == candidate['input']
    assert base_audit['input']['sha256'] == candidate_audit['input']['sha256']
    delta = {k: candidate_audit['completion_from_native_receipts'][k] - v
        for k, v in base_audit['completion_from_native_receipts'].items()}
    assert all(v <= 0 for v in delta.values())
    choices = [d for d in candidate['repeated_decisions'] if d['owner'] == 'B'
        and d['current_admission']['execution_mode'] == 'protected_current']
    assert len(choices) == 2
    records = []
    for decision in choices:
        identity = decision['command_id']; outbox = candidate['outbox'][identity]
        request, ack = outbox['request'], outbox['ack']
        assert decision['selected_action_id'] == 'prefer_8' and decision['actual_ack'] == ack and ack['status'] == 'updated'
        assert request['owner_id'] == 'B' and request['from'] == 7 and request['next'] == 8
        target = decision['opportunity']['target']
        assert request['expected_generation'] == target['generation'] and request['expected_traversal'] == target['traversal_id']
        calls = [c for c in candidate['calls'] if c['request']['request_id'] == identity]
        assert calls and min(c['at'] for c in calls) == decision['selected_at']
        edges = [e for e in candidate['result']['receipts'] if e['event'] == 'EDGE_ENTER'
            and e['business_bag_id'] == request['business_bag_id'] and e['tray_id'] == request['tray_id']]
        edge = min(edges, key=lambda e: e['time'])
        assert (edge['from'], edge['to']) == (7, 8) and decision['selected_at'] < ack['executed_at'] < edge['time']
        intent = [e for e in candidate['result']['receipts'] if e['event'] == 'ROUTE_INTENT_updated'
            and e['business_bag_id'] == request['business_bag_id'] and e['time'] == ack['executed_at']]
        assert len(intent) == 1 and intent[0]['to'] == 8
        masks = {}
        for c in decision['candidate_mask']:
            assert set(c['per_job_delta']) == set(delta)
            masks[c['action_id']] = {'enabled': c['enabled'], 'guard_status': c['guard_status'],
                'reported_conditional_per_job_delta': c['per_job_delta']}
        records.append({'decision_id': decision['decision_id'], 'at': decision['selected_at'],
            'target_generation': target['generation'], 'target_traversal': target['traversal_id'],
            'request': request, 'ACK': ack, 'first_native_edge': edge, 'candidate_mask': masks})
    old, second = records
    inactive = {'expired': old['request']['expiry'] < second['at'],
        'generation_mismatch': old['request']['expected_generation'] != second['target_generation'],
        'traversal_mismatch': old['request']['expected_traversal'] != second['target_traversal']}
    assert all(inactive.values())
    assert second['candidate_mask']['native_default']['enabled'] and second['candidate_mask']['prefer_8']['enabled']
    assert not second['candidate_mask']['prefer_3']['enabled']
    native = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014/native027_build_001/source/cpp/ics_core/runtime'
    report = {'schema': 'g31.independent_hold3_pair.v1', 'status': 'closed_actual_pair_audited',
        'baseline': base_audit, 'candidate': candidate_audit, 'all_input_bytes_equal': True,
        'all_six_native_completion_deltas': delta, 'strict_all_job_nonharm': True,
        'protected_B_choices': records, 'first_preference_inactive_at_second': inactive,
        'native_preference_semantics_source': ref(native / 'event_driven_junction.hpp'),
        'native_lifecycle_source': ref(native / 'circulation_runtime_impl.hpp'),
        'claims_not_established': ['The second native_default branch was not executed in this pair.',
            'Original baseline is not a protected-current paired early-choice witness.',
            'This audit does not establish training eligibility, FQI support, or learned improvement.',
            'Conditional candidate guard rows are recorded, not substituted for native event evidence.']}
    with (OUT / 'report.json').open('x', encoding='utf8') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    text = f"""# Independent hold3 native pair audit

The baseline and guarded-prefer8 branch both closed native acceptance. Their input bytes match: six actual jobs, three trays. All archived source bytes in each run match their own prepared and accepted hashes. Completion values were independently bound to BAG_ARRIVAL and UNLOAD_COMPLETE receipts.

Actual per-job deltas: {delta}. Every delta is nonpositive. The selected reuse2 and reuse3 route commands both have updated ACKs and actual first edges7→8. This is an executed fixed guarded preference mechanism; it is not learned-policy improvement.

The first command was issued at{old['at']} with expiry{old['request']['expiry']}, generation{old['target_generation']}, traversal{old['target_traversal']}. The second choice was at{second['at']}, generation{second['target_generation']}, traversal{second['target_traversal']}. The old preference is expired and mismatches both identity versions. Native027 apply_circulation_route_preference checks all three conditions (event_driven_junction.hpp:14697). native_default issues no new command and does not clear a still-applicable hint; here the previous hint is already inapplicable.

The second mask has native_default and prefer8 enabled; prefer3 is correctly disabled by current capacity even though its conditional completion projection passes. Recorded model deltas distinguish waiting/default from bypass8. The second native_default physical result has not been executed by this pair. A separately closed protected-current comparison is still required for an early-choice witness; the original baseline alone does not satisfy that gate.
"""
    (OUT / 'report.md').write_text(text, encoding='utf8')
    print(json.dumps({'status': report['status'], 'delta': delta, 'first_preference_inactive_at_second': inactive}))


if __name__ == '__main__':
    main()
