"""Narrow terminal report/root-clock check; does not repeat the large API replay."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
DIR = OUT / 'original_route_pending_ack_prepare_001'
TARGET = OUT / 'original_route_pending_ack_independent_report_review_001.json'
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    report, receipt = read(DIR / 'independent_verification.json'), read(DIR / 'receipt.json')
    external, launch = read(DIR / 'powershell_launch_receipt.json'), read(DIR / 'external_launch_receipt.json')
    assert report['status'] == 'passed_saved_pending_ack_candidate' and report['declared_roots'] == 3
    assert report['closed_roots'] == 2 and report['open_roots'] == 1
    assert receipt['status'] == 'completed_finite_pending_ack_cohort' and receipt['source_changed'] == []
    assert receipt['verification']['exit_code'] == 0 and external['exit_code'] == 0
    assert launch['process']['status'] == 'exited' and launch['process']['exitcode'] == 0
    assert launch['process']['windows_job_kill_on_close'] is True
    rows, pins = [], {name: sha(DIR / name) for name in ('independent_verification.json', 'receipt.json',
        'external_launch_receipt.json', 'powershell_launch_receipt.json', 'campaign.json', 'preregistered_protocol.json')}
    for name, summary in report['cases'].items():
        path = DIR / name / 'raw.json.gz'; pins[f'{name}/raw.json.gz'] = sha(path)
        assert sha(path) == summary['raw_sha256'] == receipt['cases'][name]['artifact_sha256']['raw.json.gz']
        raw = json.loads(gzip.decompress(path.read_bytes())); root = raw['root']
        assert raw['case'] == name and raw['source_changed'] == [] and raw['physical_time'] == 9900.
        assert raw['native_state_sha256'] == summary['producer_native_seal'] == summary['pending_ack_actual_reference']['native_state_sha256']
        closed = root['returned_ns'] is not None
        end = root['returned_ns'] if closed else root['censored_ns']
        warm = (end-root['started_ns'])/1e6
        assert warm == summary['warm_elapsed_upper_ms' if closed else 'warm_elapsed_prefix_ms']
        assert (root['started_ns']-raw['worker_started_ns'])/1e6 == summary['worker_setup_prefix_ms']
        assert summary['complete_100ms_certified'] is False
        omitted = summary['pending_ack_actual_reference']['omitted_full_view_ordinals_in_reference']
        assert omitted == sorted(set(omitted)) and len(omitted) == root['pending_ack_path']['ack_only_steps']
        if closed:
            assert root['intent']['ack']['status'] == 'updated' and root['intent']['edge']['to'] == 113
        else:
            assert root['lineage'][root['root']]['decision_seal'] is None
        rows.append({'case': name, 'closed': closed, 'warm_elapsed_upper_or_open_prefix_ms': warm,
            'last_actual_physical_observation_at': root['intent']['last_now'],
            'retained_ack_delivered_at': (root['intent'].get('ack') or {}).get('delivered_at'),
            'omitted_postproof_full_reads': len(omitted), 'immutable_submit_attempts': summary['attempts'],
            'child_plus_parent_setup_ms': summary['child_plus_measured_parent_setup_ms']})
    result = {'status': 'passed_narrow_report_and_root_clock_review', 'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'evidence_sha256': pins, 'cases': rows, 'whole_application_campaign_wall_seconds': external['whole_application_campaign_wall_seconds'],
        'scope': 'Read terminal receipts and three small raw root snapshots; recomputed root/cold clock arithmetic and omission counters. Did not independently repeat the147171-row API replay or native execution. That evidence remains the pinned already-reviewed saved verifier report.',
        'limits': 'Normal64.3337ms is one selected initialized-prefix finite first-hop root upper envelope; fault root970.5869ms and open prefix27365.3727ms remain. Cold setup remains charged. This is not an original-business all-request100ms certificate, physical job completion or hard-real-time guarantee.',
        'native_executions': 0, 'complete_business_request_100ms_certified': False}
    with TARGET.open('x', encoding='utf8') as stream: json.dump(result, stream, indent=2)
    print(json.dumps({'path': str(TARGET), 'sha256': sha(TARGET), 'cases': rows}))


if __name__ == '__main__': main()
