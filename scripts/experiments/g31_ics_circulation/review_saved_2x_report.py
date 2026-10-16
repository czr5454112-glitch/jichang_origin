"""Limited independent metadata review; never open raw/input gzip or native."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review(base):
    directory = base / 'full024_chained_2x_20261015_002'; pins = {}
    def read(path):
        path = Path(path)
        if path.suffix != '.json' or path.stat().st_size > 2_000_000:
            raise ValueError('metadata_only_size_or_extension')
        raw = path.read_bytes(); pins[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    report_path = base / 'full024_chained_2x_20261015_002_saved_audit_001.json'
    report = read(report_path); launch = read(base / 'full024_chained_2x_20261015_002_saved_audit_launch_001.json')
    external = read(base / 'full024_chained_2x_20261015_002_saved_audit_external_001.json')
    producer = read(directory / 'receipt.json'); heartbeat = read(directory / 'heartbeat.json')
    manifest = read(directory / 'run_shards.json'); reconstruction = read(directory / 'reconstruction.json')
    assert launch['status'] == 'audit_process_completed' and launch['audit_report_sha256'] == pins[str(report_path)]
    assert launch['recheck_error'] is None and launch['native_executions'] == external['native_executions'] == report['new_native_executions'] == 0
    assert launch['process']['status'] == 'exited' and launch['process']['exitcode'] == external['exit_code'] == 0
    assert launch['process']['windows_job_kill_on_close'] is True and launch['process']['child_released_only_after_job_assignment'] is True
    assert external['status'] == 'audit_application_exited_zero' and external['launcher_unchanged'] is True
    assert 0 <= report['audit_wall_seconds'] <= launch['process']['wall_seconds'] <= launch['whole_measured_seconds'] <= external['whole_python_application_wall_seconds'] < launch['shared_deadline_seconds'] == 3600.
    launcher = Path(external['launcher']); pins[str(launcher)] = sha(launcher)
    assert external['launcher_sha256'] == launch['before']['launcher_sha256'] == pins[str(launcher)]
    for name, field in [('receipt.json', 'producer_receipt_sha256'), ('heartbeat.json', 'heartbeat_sha256'), ('run_shards.json', 'manifest_sha256')]:
        assert launch['before'][field] == pins[str(directory / name)]
        if name in report['evidence_sha256']: assert report['evidence_sha256'][name] == pins[str(directory / name)]
    assert producer['status'] == report['producer_receipt_status'] == 'hard_timeout'
    assert producer['source_changed'] == [] and producer['exit_code'] is None and report['producer_exit_code'] is None
    assert report['producer_process_success'] is False and report['producer_summary_present'] is False and not (directory / 'summary.json').exists()
    assert producer['wall_seconds'] > producer['hard_timeout_seconds'] == 7200.
    assert producer['source_before'] == report['source_archive_sha256'] and len(producer['source_before']) == 49
    assert producer['binary_sha256'] == producer['binary_after_sha256'] == report['native_sha256']
    assert report['status'] == 'passed_saved_physical_horizon' and report['physical_horizon_completed'] == heartbeat['physical_time'] == 86400.
    assert report['offered'] == report['unfinished'] == report['strict_deadline_violations_by_horizon'] == heartbeat['offered_total'] == heartbeat['offered_by_current_time'] == 57012
    assert report['completed'] == report['failed'] == 0 and sum(report['business_status_counts'].values()) == 57012
    assert report['all_business_completed'] is report['unpaired_zero_regression_certified'] is report['complete_request_100ms_certified'] is False
    assert report['original_r1_authorized_jobs'] == 0 and report['tray_count'] == report['physical_audit']['tray_count'] == 22
    assert report['physical_audit']['status'] == 'passed' and report['physical_audit']['open_traversals'] == 0
    assert manifest['status'] == 'reached' and manifest['all_raw_records_retained'] is True
    assert len(manifest['shards']) == len(manifest['segments']) == 526
    assert manifest['final_state_shard'] == 'segments\\0525.json.gz' and heartbeat['segment'] == 525
    assert manifest['segments'][-1]['horizon'] == manifest['segments'][-1]['physical_time'] == 86400.
    paths = [row['path'] for row in manifest['shards']]
    assert paths == [f'segments\\{index:04}.json.gz' for index in range(526)]
    assert all(row['sha256'] == report['evidence_sha256'][row['path']] for row in manifest['shards'])
    sums = {key: sum(row['counts'][key] for row in manifest['shards']) for key in report['counts']}
    assert sums == report['counts'] == manifest['counts']
    assert report['counts']['control_records'] == heartbeat['owner_activations'] == 256756
    assert sum(report['initial_requests_by_kind'].values()) == report['immutable_request_count'] == 63915
    assert report['immutable_request_count'] + report['retry_attempt_count'] == report['counts']['client_calls'] == 72816
    assert heartbeat['latest_native_seal']['shard'] == 525 and heartbeat['latest_native_seal']['physical_time'] == 86400.
    assert heartbeat['latest_native_seal']['native_state_sha256'] == report['native_state_sha256'] == launch['command'][-1]
    proof = report['resume_proof']; links = proof['chain_links']
    assert len(links) == proof['chain_link_count'] == 3 and proof['any_ancestor_source_drift_finalization_unknown'] is True
    assert report['chain_ancestor_boundary_checks'] == [row['cut_manifest_sha256'] for row in links]
    cut_names = ['full024_sealed_cut_2x_20261015_001', 'full024_chained_cut_2x_20261015_001', 'full024_chained_cut_2x_20261015_002']
    cumulative = 0.; ancestry = []
    for index, (name, link) in enumerate(zip(cut_names, links, strict=True)):
        cut_dir = base / name; cut_path = cut_dir / 'cut_manifest.json'; cut = read(cut_path)
        stopped = read(cut_dir / 'source_stop_receipt.json'); source = read(cut_dir / 'source_receipt_snapshot.json')
        assert pins[str(cut_path)] == link['cut_manifest_sha256'] == stopped['cut_manifest_sha256']
        assert stopped['source_worker_stopped'] is True and stopped['unchanged_policy'] is True
        assert pins[str(cut_dir / 'source_receipt_snapshot.json')] == cut['source_receipt_sha256']
        assert pins[str(cut_dir / 'source_stop_receipt.json')] == report['evidence_sha256'][str(cut_dir / 'source_stop_receipt.json')]
        assert cut['source_cut'] + 1 == len(cut['shards']) == link['prefix_parts']
        assert cut['physical_time'] == link['physical_time'] == manifest['shards'][cut['source_cut']]['physical_time']
        assert cut['known_native_seal'] == link['known_prefix_seal'] and cut['controller_config'] == link['controller_config'] == proof['controller_config']
        assert link['trace_records'] == link['prefix_counts']['control_records'] + link['prefix_counts']['native_batches']
        assert link['inherited_reconstruction_wall_seconds'] == cumulative
        cumulative += link['own_reconstruction_wall_seconds']; assert cumulative == link['cumulative_reconstruction_wall_seconds']
        if index == 0:
            assert source['status'] == 'running' and 'source_changed' not in source and link['source_drift_finalization_unknown'] is True
        else:
            assert source['status'] == 'hard_timeout' and source['source_changed'] == [] and link['source_drift_finalization_unknown'] is False
        ancestry.append({'prefix_parts': link['prefix_parts'], 'physical_time': link['physical_time'], 'known_prefix_seal': link['known_prefix_seal'],
            'source_status_retained': source['status'], 'source_drift_finalization_unknown': link['source_drift_finalization_unknown']})
    assert reconstruction['status'] == 'verified_against_known_native_seal' and reconstruction['parts'] == proof['prefix_parts'] == 497
    assert reconstruction['native_state_sha256'] == proof['known_prefix_seal'] and reconstruction['physical_time'] == proof['physical_time'] == 79200.
    assert reconstruction['wall_seconds'] == proof['own_reconstruction_wall_seconds'] and reconstruction['prior_reconstruction_wall_seconds'] == proof['inherited_reconstruction_wall_seconds']
    assert cumulative == proof['cumulative_reconstruction_wall_seconds']
    for path, digest in pins.items(): assert sha(path) == digest
    return {'status': 'passed_limited_saved_2x_report_binding_review', 'metadata_sha256': pins,
        'raw_gzip_files_read': 0, 'input_gzip_files_read': 0, 'native_executions': 0, 'new_physical_replay': False,
        'shards_reported_and_manifest_bound': 526, 'offered': 57012, 'completed': 0, 'unfinished': 57012,
        'producer_status_retained': 'hard_timeout', 'producer_process_success': False,
        'first_ancestor_source_drift_finalization_unknown': True, 'ancestor_boundaries': ancestry,
        'final_physical_horizon_reported': 86400., 'final_seal_reported': report['native_state_sha256'],
        'cumulative_reconstruction_wall_seconds': cumulative, 'counts_recomputed_from_manifest': sums,
        'saved_audit_whole_python_wall_seconds': external['whole_python_application_wall_seconds'],
        'business_success_or_protection_certified': False, 'complete_request_100ms_certified': False,
        'scope': 'Read only report/launch/external/producer/manifest/heartbeat/reconstruction and three ancestry metadata sets. Verified file hashes, manifest arithmetic, all526 referenced shard-hash claims, retained unknowns and seal boundaries. Did not reread raw shards, recompute per-job objectives, replay physics, verify final hidden native state independently or repair producer termination. Intermediate controller JSON remains opaque under the original saved-audit scope.'}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--base', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); result = review(a.base.resolve()); result['reviewer_source_sha256'] = sha(__file__)
    with a.output.open('x', encoding='utf-8') as f: json.dump(result, f, indent=2, allow_nan=False)
if __name__ == '__main__': main()
