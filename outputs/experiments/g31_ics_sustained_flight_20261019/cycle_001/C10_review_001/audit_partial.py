"""Independent partial-C10 inspection. Standard library only; no native imports."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
RUN = OUT.parent / 'C10_rule_001'
BASE = OUT.parent / 'C00_calibration_001'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unpack(path):
    return json.loads(gzip.decompress(Path(path).read_bytes()))


def write(name, value):
    with (OUT / name).open('x', encoding='utf8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def main():
    plan, receipt = read(RUN / 'plan.json'), read(RUN / 'receipt.json')
    assert receipt['process']['status'] == 'hard_timeout'
    assert receipt['worker_report'] is None
    assert not any((RUN / 'C10' / n).exists() for n in ('worker_report.json', 'acceptance.json', 'raw.json.gz'))
    data, base_data = read(RUN / 'inputs/C10.json'), read(BASE / 'inputs/C00.json')
    assert data == base_data
    assert sha(RUN / 'inputs/C10.json') == sha(BASE / 'inputs/C00.json') == plan['input']['sha256']
    archive_failures = [p for p, a in plan['source_archive'].items() if sha(RUN / a) != plan['source_sha256'][p]]
    assert not archive_failures
    progress = [json.loads(line) for line in (RUN / 'C10/progress.jsonl').read_text().splitlines()]
    forecasts, transfers, files, segment_summary = [], [], [], []
    for row in progress:
        path = RUN / 'C10' / f"segment_{row['index']:02d}.json.gz"
        assert sha(path) == row['raw']['sha256']
        files.append({'path': str(path), 'sha256': sha(path)})
        saved = unpack(path)
        assert saved['result']['physical_clock'] == row['actual_clock']
        segment_summary.append({'index': row['index'], 'clock': row['actual_clock'],
                                'elapsed_wall_seconds': row['elapsed_wall_seconds']})
        for call in saved['client_calls']:
            if call['kind'] == 'transfer':
                transfers.append({'at': call['at'], 'retry': call['retry'], 'request': call['request']})
        for record in saved['control_records']:
            for own in record['owner_decisions']:
                decision = own['decision']
                flight = decision.get('flight_planning')
                if flight is None:
                    continue
                f = flight['forecast']
                assert f['forecast_origin'] == record['at'] and f['owner_scope'] == own['owner_id']
                assert f['information_cutoffs']['model_frozen_at'] <= record['at']
                assert f['information_cutoffs']['training_labels_closed_at'] <= record['at']
                assert not f['predicted_inventory_is_actual'] and flight['future_jobs_created'] == 0
                assert f['information_cutoffs']['observed_arrivals_through'] is None
                assert f['projection_audit']['mean_mass_conserved']
                forecasts.append({'at': record['at'], 'owner': own['owner_id'],
                    'status': flight['status'], 'candidate_count': flight['candidate_count'],
                    'supplies': len(decision['supplies']), 'attempts': own['attempts'],
                    'compute_ms': own['compute_ms'], 'model_sha256': f['model_sha256'],
                    'context_sha256': f['context_sha256'], 'information_cutoffs': f['information_cutoffs'],
                    'mapping_version': f['mapping_version'],
                    'max_mass_residual': max(map(abs, f['projection_audit']['floating_point_residual_per_bin']))})
    final = saved['result']
    warmup = read(RUN / 'C10/warmup_boundary.json')
    base_warmup = read(BASE / 'C00/warmup_boundary.json')
    assert warmup['native_state_sha256'] == base_warmup['native_state_sha256']
    # Independently compare persisted result fields too: a reported state hash alone is not the result.
    warm_a = unpack(RUN / 'C10/segment_16.json.gz')['result']
    warm_b = unpack(BASE / 'C00/segment_16.json.gz')['result']
    warm_differences = {k: True for k in warm_a if warm_a[k] != warm_b[k]}
    assert set(warm_differences) <= {'advance'}
    assert {k: v for k, v in warm_a['advance'].items() if k != 'wall_seconds'} == {
        k: v for k, v in warm_b['advance'].items() if k != 'wall_seconds'}
    base_at_last = unpack(BASE / 'C00/segment_18.json.gz')['result']
    assert base_at_last['physical_clock'] == final['physical_clock'] == 58800.
    same_fields = {k: final[k] == base_at_last[k] for k in ('jobs', 'trays', 'transfers', 'receipts')}
    actual_new = [c for c in transfers if not c['retry'] and c['at'] > 57600.]
    planned = [c for c in actual_new if c['request'].get('control_reason') == 'flight_expected_demand_preposition']
    counts = Counter(j['status'] for j in final['jobs'])
    summary = {'schema': 'g31.independent_airport_partial_audit.v1',
        'status': 'partial_only_no_native_acceptance',
        'hard_timeout_seconds': receipt['process']['hard_timeout_seconds'],
        'last_persisted_clock': final['physical_clock'], 'planned_final_clock': plan['window_boundaries'][-1],
        'closed_native_acceptance': False, 'strict_final_paired_comparison_established': False,
        'source_archive_count': len(plan['source_archive']), 'source_archive_failures': archive_failures,
        'input_bytes_equal': True, 'all_28506_jobs_retained': len(data['jobs']) == 28506,
        'warmup_native_state_sha256': warmup['native_state_sha256'],
        'warmup_persisted_result_equal_except_advance_wall_seconds': True,
        'warmup_measured_advance_wall_seconds': [warm_a['advance']['wall_seconds'], warm_b['advance']['wall_seconds']],
        'common_saved_clock_comparison_only': same_fields,
        'forecast_records': len(forecasts), 'forecast_first_at': min(f['at'] for f in forecasts),
        'forecast_last_at': max(f['at'] for f in forecasts),
        'forecast_owner_counts': dict(Counter(f['owner'] for f in forecasts)),
        'flight_planner_status_counts': dict(Counter(f['status'] for f in forecasts)),
        'flight_candidate_count_sum': sum(f['candidate_count'] for f in forecasts),
        'flight_planner_compute_ms_sum': sum(f['compute_ms'] for f in forecasts),
        'flight_planner_compute_ms_range': [min(f['compute_ms'] for f in forecasts), max(f['compute_ms'] for f in forecasts)],
        'flight_records_without_supplies': sum(f['supplies'] == 0 for f in forecasts),
        'post_warmup_new_transfer_calls': len(actual_new), 'post_warmup_flight_transfer_calls': len(planned),
        'post_warmup_transfer_retry_calls': sum(c['retry'] and c['at'] > 57600. for c in transfers),
        'job_status_counts': dict(counts), 'true_completed_business_count': counts['completed'],
        'tray_mode_counts': dict(Counter(t['mode'] for t in final['trays'])),
        'native_summary_completed_count_is_leg_count': final['native_summary']['completed_count'],
        'edge_enter_count': sum(e['event'] == 'EDGE_ENTER' for e in final['receipts']),
        'edge_exit_count': sum(e['event'] == 'EDGE_EXIT' for e in final['receipts']),
        'last_edge_exit_at': max(e['time'] for e in final['receipts'] if e['event'] == 'EDGE_EXIT'),
        'transfer_status_counts': dict(Counter(t['status'] for t in final['transfers'])),
        'segment_progress': segment_summary, 'segment_refs': files,
        'caveats': ['No statement about activity in unsaved segment 19.',
            'Saved common-clock result equality is not completed run acceptance or a final paired comparison.',
            'Planner compute_ms includes planner preparation; not an isolated model inference benchmark.',
            'C00_review_001 establishes 4001 statically unreachable jobs under the unchanged physical contract.',
            'No capacities, graph directions, business destinations, inventory, or admissions were changed by this audit.']}
    write('forecast_records.json', forecasts)
    write('post_warmup_transfer_calls.json', [c for c in transfers if c['at'] > 57600.])
    write('report.json', summary)
    body = f"""# C10 independent partial audit

C10 hit the 150-second hard limit. The last persisted segment reaches 58800, while the planned final boundary is 59400. There is no worker report, final raw, or closed native acceptance. This is an incomplete run; no final same-endpoint comparison or benefit is established.

The complete 28506-job input bytes match C00. All {len(plan['source_archive'])} archived source files match their own prepared hashes. The reported 57600 warmup state hash matches C00, and the independently decoded persisted warmup results match except for measured advance.wall_seconds ({warm_a['advance']['wall_seconds']} versus {warm_b['advance']['wall_seconds']}). At the shared saved 58800 boundary, jobs/trays/transfers/receipts equality is {same_fields}. This limited observation does not close C10 acceptance.

Saved forecast records: {len(forecasts)}, from {summary['forecast_first_at']} through {summary['forecast_last_at']}, across both owners. All records retain legal model cutoffs, current forecast origin and matching owner. All {summary['flight_records_without_supplies']} have zero supplies; candidate count totals {summary['flight_candidate_count_sum']}, and all return local_wait. There are {len(planned)} new forecast-preposition transfer submissions. Existing-rule new transfer calls after warmup: {len(actual_new)}; retry calls: {summary['post_warmup_transfer_retry_calls']}.

Recorded planner compute totals {summary['flight_planner_compute_ms_sum'] / 1000:.3f} seconds across the saved forecast records (includes preparation, not a standalone model benchmark). Computing a full forecast with no available supply adds overhead without enabling an action in these records. A future performance revision can short-circuit at zero supply, but must be a new source/run identity; this audit changes no frozen code.

At 58800: true completed business jobs {counts['completed']}; job statuses {dict(counts)}. Tray modes {summary['tray_mode_counts']}. Edge entries/exits remain {summary['edge_enter_count']}/{summary['edge_exit_count']}, last exit {summary['last_edge_exit_at']}. Native completed_count {final['native_summary']['completed_count']} counts legs, not completed business jobs. The 4001 unreachable jobs and physical bottleneck are detailed in C00_review_001; no input correction was applied.

No claims are made about the unsaved final segment. This partial run remains retained as a failure and cannot justify C01/C11 training or an airport optimization claim.
"""
    (OUT / 'report.md').write_text(body, encoding='utf8')
    print(json.dumps({k: summary[k] for k in ('status', 'last_persisted_clock', 'forecast_records',
        'flight_candidate_count_sum', 'post_warmup_new_transfer_calls', 'post_warmup_flight_transfer_calls',
        'post_warmup_transfer_retry_calls', 'flight_planner_compute_ms_sum', 'true_completed_business_count')}))


if __name__ == '__main__':
    main()
