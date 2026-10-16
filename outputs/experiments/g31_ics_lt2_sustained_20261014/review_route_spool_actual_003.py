"""Small terminal receipt review. No native, tape parsing or policy replay.

Run only after the measured wrapper exits. The existing complete saved verifier
owns raw API/controller replay and spool-byte equality; this review binds its
completed report, parent process receipts, small capture metadata and sources.
"""
from pathlib import Path
import hashlib
import json
import math
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
FOLDER = OUT/'original_route_spool_prepare_002'
CASES = ('baseline','drop_first_ack','ack_withheld_in_window')
READY_SHA = '921b9b8bc3f1ad5079fc8f45f5eaba7d58fb5a569dc49540a4bdbaed662e6cd5'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): digest.update(chunk)
    return digest.hexdigest()


def read(path): return json.loads(Path(path).read_bytes())
def check(ok, reason):
    if not ok: raise ValueError(reason)


def main():
    start = time.perf_counter(); ready_path = FOLDER/'ready.json'
    check(sha(ready_path) == READY_SHA, 'ready_changed')
    ready = read(ready_path); plan = read(FOLDER/'preregistered_protocol.json')
    parent = read(FOLDER/'receipt.json'); launch = read(FOLDER/'external_launch_receipt.json')
    outer = read(FOLDER/'powershell_launch_receipt.json'); report = read(FOLDER/'independent_verification.json')
    check(parent['status'] == 'completed_finite_spool_cohort' and parent['source_changed'] == [] and
        parent['wall_seconds'] <= 600 and tuple(parent['cases']) == CASES, 'campaign_not_complete')
    check(parent['verification']['status'] == 'child_finished' and parent['verification']['exit_code'] == 0,
        'saved_verifier_not_completed')
    check(parent['verification']['command'] == [ready['execute_command'][0], '-m',
        'scripts.experiments.g31_ics_circulation.verify_original_route_update_spool', '--output', str(FOLDER), '--write-report'],
        'wrong_saved_verifier')
    check(launch['status'] == 'campaign_process_exited' and launch['process']['status'] == 'exited' and
        launch['process']['exitcode'] == 0 and launch['process']['windows_job_kill_on_close'] is True and
        launch['process']['child_released_only_after_job_assignment'] is True and launch['shared_seconds'] == 600,
        'owned_job_not_completed')
    check(launch['artifact_sha256']['receipt.json'] == sha(FOLDER/'receipt.json') and
        outer['status'] == 'application_exited_zero' and outer['exit_code'] == 0 and
        outer['evidence_identities_unchanged'] is True and outer['command'] == ready['execute_command'], 'external_exit_not_bound')
    check(outer['ready']['sha256'] == outer['ready']['final_sha256'] == READY_SHA and
        outer['preregistered_plan']['sha256'] == outer['preregistered_plan']['final_sha256'] == ready['campaign_sha256'] ==
        parent['campaign_sha256'] == sha(FOLDER/'campaign.json'), 'campaign_or_ready_changed')
    check(outer['wrapper']['sha256'] == outer['wrapper']['final_sha256'] == ready['external_wrapper']['sha256'] ==
        sha(ready['external_wrapper']['path']), 'wrapper_changed')
    check(report['status'] == 'passed_saved_spool_candidate' and report['declared_roots'] == 3 and
        report['native_executions_in_verifier'] == 0 and report['complete_100ms_certified'] is False and
        tuple(report['cases']) == CASES and report['campaign_sha256'] == ready['campaign_sha256'], 'saved_report_scope')
    check(sha(FOLDER/'preregistered_protocol.json') == ready['protocol_plan']['sha256'] and
        plan['input_business_count'] == 28506 and plan['trays'] == 22 and plan['native_branch_budget'] == 3 and
        plan['horizon'] == 9900 and plan['admission'] == 9600, 'original_denominators_changed')
    check(len(plan['source_before']) == 95 and len(plan['compiled_source_sha256']) == 67, 'source_denominator')
    for path, digest in plan['source_before'].items():
        check(sha(path) == digest == sha(FOLDER/'source_archive'/Path(path).relative_to(ROOT)), 'python_source_changed')
    for path, digest in plan['compiled_source_sha256'].items():
        check(sha(FOLDER/'compiled_source_archive'/path) == digest, 'compiled026_archive_changed')
    check(sha(plan['native_binary']) == plan['native_binary_sha256'] == ready['native_binary_sha256'], 'native026_changed')
    for path,digest in plan['authority_pins'].items(): check(sha(path) == digest, 'native026_authority_changed')
    previous = Path(plan['spool_reference']); old = read(previous/'independent_verification.json')
    check(sha(previous/'independent_verification.json') == plan['spool_reference_pins'][str(previous/'independent_verification.json')],
        'previous_report_changed')
    checks = {}; closed = 0
    for name in CASES:
        item = report['cases'][name]; process = parent['cases'][name]; capture = read(FOLDER/name/'diagnostic_capture.json')
        check(process['status'] == 'child_finished' and process['exit_code'] == 0 and
            process['command'] == [ready['execute_command'][0], '-m',
                'scripts.experiments.g31_ics_circulation.probe_original_route_update_spool', '--output', str(FOLDER), '--worker', name],
            'worker_not_complete')
        check(item['raw_sha256'] == process['artifact_sha256']['raw.json.gz'] == sha(FOLDER/name/'raw.json.gz'), 'raw_binding')
        check(sha(FOLDER/name/'diagnostic_capture.json') == process['artifact_sha256']['diagnostic_capture.json'] ==
            item['diagnostic_capture']['artifact_sha256']['diagnostic_capture.json'], 'capture_binding')
        check(capture['evidence_complete'] is True and capture['failure'] is None and
            capture['max_bytes'] == 268435456 and capture['max_rows'] == 160000 and
            capture['rows'] == capture['flushed_rows'] == capture['api_count'] == item['all_warm_native_api_rows'], 'capture_denominator')
        # Full byte equality was already performed by the completed verifier.
        # Bind the hashes without another read of the 30–213MB tapes/spools.
        for artifact,digest in capture['artifact_sha256'].items():
            check(process['artifact_sha256'][artifact] == digest == item['diagnostic_capture']['artifact_sha256'][artifact], 'tape_hash_binding')
        comparison = item['spool_actual_reference']
        check(comparison['status'] == 'exact_all_actual_api_rows_and_common9900_seal' and
            comparison['omitted_full_view_ordinals_in_reference'] == [] and comparison['changed_observation_diagnostics'] == [] and
            comparison['remaining_api_rows'] == capture['rows'] and
            comparison['native_state_sha256'] == item['producer_native_seal'] == old['cases'][name]['producer_native_seal'], 'exact_parity_gate')
        is_closed = item['status'] == 'closed_finite_request'; closed += is_closed
        check(item['status'] in ('closed_finite_request','open_censored_request') and
            item['status'] == old['cases'][name]['status'], 'closure_changed')
        key = 'warm_elapsed_upper_ms' if is_closed else 'warm_elapsed_prefix_ms'
        warm = item[key]; old_warm = old['cases'][name][key]
        check(type(warm) in (int,float) and math.isfinite(warm) and warm >= 0, 'bad_warm_clock')
        checks[name] = {'status':item['status'], 'attempts':item['attempts'], 'warm_kind':key,
            'warm_ms':warm, 'prior_pending_ack_warm_ms':old_warm, 'single_pair_change_ms':warm-old_warm,
            'diagnostic_close_export_ms':item['diagnostic_capture']['close_export_ms'],
            'diagnostic_close_hash_ms':item['diagnostic_capture']['close_hash_ms'],
            'whole_child_wall_seconds':item['whole_child_wall_seconds'],
            'child_cold_ms':item.get('child_cold_elapsed_upper_ms',item.get('child_cold_elapsed_prefix_ms')),
            'whole_campaign_charged_in_full_to_root_ms':outer['whole_application_campaign_wall_seconds']*1000,
            'api_rows':capture['rows'],'encoded_bytes':capture['encoded_bytes'],
            'row_headroom':160000-capture['rows'],'byte_headroom':268435456-capture['encoded_bytes'],
            'actual_common9900_seal':item['producer_native_seal'],'capture_artifact_pins':capture['artifact_sha256']}
    check(report['closed_roots'] == closed and report['open_roots'] == 3-closed, 'root_denominator')
    evidence = [ready_path,FOLDER/'preregistered_protocol.json',FOLDER/'campaign.json',FOLDER/'receipt.json',
        FOLDER/'external_launch_receipt.json',FOLDER/'powershell_launch_receipt.json',FOLDER/'independent_verification.json',
        OUT/'user_resume_20261015_001/process_identity_012.json',Path(__file__)]
    result = {'schema':'g31.original_route_spool.small_actual_review.v1','status':'passed_completed_saved_report_binding',
        'cases':checks,'closed_roots':closed,'open_roots':3-closed,'source_count':95,'compiled026_archive_count':67,
        'parent_campaign_wall_seconds':parent['wall_seconds'], 'external_full_campaign_seconds':outer['whole_application_campaign_wall_seconds'],
        'native_executions_by_reviewer':0,'additional_large_tape_replay':False,'additional_native_seal_replay':False,'concurrent_load':'Not isolated; concurrent pure research work in shared workspace. No stable-speed or causal claim.',
        'complete_100ms_certified':False,'review_wall_seconds':time.perf_counter()-start,
        'evidence_sha256':{str(path):sha(path) for path in evidence},
        'limits':'One diagnostic-pipeline sample; no algorithmic speedup claim. Warm JSON/UTF8/write/flush unchanged; deferred gzip/hash/export is retained in child and full campaign. Open request remains censored. This small review binds the completed full verifier, not a second tape replay. Current C++027 is not used as026 authority.'}
    target = OUT/'original_route_spool_actual_review_001.json'
    with target.open('x',encoding='utf8') as stream: json.dump(result,stream,ensure_ascii=False,allow_nan=False,indent=2)
    print(json.dumps({'path':str(target),'sha256':sha(target),'cases':checks,'external_seconds':result['external_full_campaign_seconds']}))


if __name__ == '__main__': main()
