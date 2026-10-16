"""Bound a read-only, complete saved 2x horizon audit; never resume native work."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
DIRECTORY = OUT / 'full024_chained_2x_20261015_002'
PREPARED = OUT / 'chained_saved_horizon_prepare_002/receipt.json'
PREPARED_SHA = 'a28b5bb145a4bc5a953630e67db55294186345aaae775574eb4e755fdb1100d3'
REPORT = OUT / 'full024_chained_2x_20261015_002_saved_audit_001.json'
RECEIPT = OUT / 'full024_chained_2x_20261015_002_saved_audit_launch_001.json'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_bytes())

def check(final_seal):
    assert len(final_seal) == 64 and all(c in '0123456789abcdef' for c in final_seal)
    assert sha(PREPARED) == PREPARED_SHA
    prepared = read(PREPARED)
    assert len(prepared['source_closure_sha256']) == 43
    for name, digest in prepared['source_closure_sha256'].items():
        path = (ROOT / name).resolve()
        assert path.is_relative_to(ROOT) and sha(path) == digest, name
    producer = read(DIRECTORY / 'receipt.json')
    assert producer['schema'] == 'g31.chained_sparse_sealed_resume_worker.v1'
    assert producer['status'] in ('completed', 'failed', 'hard_timeout')
    assert producer.get('source_changed') == []
    manifest = read(DIRECTORY / 'run_shards.json')
    assert manifest['status'] == 'reached' and manifest['all_raw_records_retained'] is True
    assert manifest['segments'][-1]['horizon'] == manifest['segments'][-1]['physical_time'] == 86400.
    heartbeat = read(DIRECTORY / 'heartbeat.json')
    assert heartbeat['physical_time'] == 86400.
    if 'latest_native_seal' in heartbeat:
        seal = heartbeat['latest_native_seal']
        assert seal['physical_time'] == 86400. and seal['native_state_sha256'] == final_seal
    else:
        # Successful producer finalization replaces the detailed heartbeat.
        # Its summary retains the actual native seal; the auditor independently
        # binds the sealed final raw shard below, without minting a checkpoint.
        summary = read(DIRECTORY / 'summary.json')
        assert heartbeat['stage'] == 'worker_finished'
        assert summary['physical_time'] == 86400. and summary['native_state_sha256'] == final_seal
    pins = {
        'prepared_sha256': PREPARED_SHA,
        'producer_receipt_sha256': sha(DIRECTORY / 'receipt.json'),
        'manifest_sha256': sha(DIRECTORY / 'run_shards.json'),
        'heartbeat_sha256': sha(DIRECTORY / 'heartbeat.json'),
        'launcher_sha256': sha(__file__),
    }
    if (DIRECTORY / 'summary.json').exists():
        pins['producer_summary_sha256'] = sha(DIRECTORY / 'summary.json')
    return pins

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--final-seal', required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args()
    if args.worker:
        assert args.admission and sys.stdin.readline() == args.admission + '\n'
        check(args.final_seal)
        sys.argv = ['audit_chained_saved_horizon', '--directory', str(DIRECTORY),
            '--output', str(REPORT), '--expected-total', '57012', '--horizon', '86400',
            '--expected-final-seal', args.final_seal]
        runpy.run_module('scripts.experiments.g31_ics_circulation.audit_chained_saved_horizon', run_name='__main__')
        return
    started = time.monotonic()
    utc_start = datetime.now(timezone.utc).isoformat()
    assert not REPORT.exists() and not RECEIPT.exists(), 'Preserve existing audit attempt'
    before = check(args.final_seal)
    from scripts.experiments.g31_ics_circulation import bounded_windows_job
    assert sha(bounded_windows_job.__file__) == '798ae87c19d5fa61569b1c9301cebe7ef6a5885302f32f42380cf53fd6363cde'
    admission = str(uuid.uuid4())
    command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--admission', admission,
               '--final-seal', args.final_seal]
    logbase = OUT / 'full024_chained_2x_20261015_002_saved_audit_001'
    with Path(str(logbase) + '.stdout.log').open('x', encoding='utf8') as stdout, \
         Path(str(logbase) + '.stderr.log').open('x', encoding='utf8') as stderr:
        process = bounded_windows_job.run(command, timeout=3600. - (time.monotonic() - started),
            stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
    error = None
    try:
        after = check(args.final_seal)
        assert after == before, 'Audit evidence changed'
    except Exception as exc:
        error = repr(exc)
    complete = process['status'] == 'exited' and process['exitcode'] == 0 and REPORT.exists() and error is None
    receipt = {'schema': 'g31.bounded_saved_chain_audit_launch.v1',
        'status': 'audit_process_completed' if complete else 'unknown_failed_or_incomplete_audit',
        'started_utc': utc_start, 'ended_utc': datetime.now(timezone.utc).isoformat(),
        'whole_measured_seconds': time.monotonic() - started, 'shared_deadline_seconds': 3600.,
        'command': command, 'process': process, 'before': before, 'recheck_error': error,
        'audit_report_sha256': sha(REPORT) if REPORT.exists() else None,
        'stdout_sha256': sha(str(logbase) + '.stdout.log'), 'stderr_sha256': sha(str(logbase) + '.stderr.log'),
        'native_executions': 0, 'complete_request_100ms_certified': False,
        'scope': 'Saved-record audit only. Does not repair producer timeout or certify independent native replay. Initial ancestor source finalization remains unknown where recorded.',
        'timing_exclusions': 'Python startup before this parent monotonic clock, final receipt serialization and hash. All child startup, checks and raw scan are inside one kill-on-close Windows Job.'}
    with RECEIPT.open('x', encoding='utf8') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'status': receipt['status'], 'wall_seconds': receipt['whole_measured_seconds'], 'receipt_sha256': sha(RECEIPT)}))
    if not complete:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
