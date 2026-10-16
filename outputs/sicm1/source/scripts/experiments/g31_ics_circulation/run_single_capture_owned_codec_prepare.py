"""Owned120 metadata-only launcher; child waits before imports/preparation."""
import time
BOOT = time.monotonic()
import argparse
import json
from pathlib import Path
import sys
import uuid
from . import bounded_windows_job

ROOT = Path(__file__).resolve().parents[3]
MODULE = __package__+'.run_single_capture_owned_codec_prepare'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pure-directory', type=Path, required=True)
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--admission')
    args = parser.parse_args(); output = args.output.resolve()
    if args.worker:
        if sys.stdin.readline() != args.admission+'\n': raise ValueError('owned_prepare_admission')
        from . import prepare_single_capture_owned_codec_campaign as prepare
        print(json.dumps(prepare.prepare(output, args.pure_directory))); return 0
    if output.exists(): raise ValueError('owned_prepare_already_exists')
    token = uuid.uuid4().hex
    claim = output.with_name(output.name+'.metadata_claim.json')
    with claim.open('x', encoding='utf8') as stream:
        json.dump({'shared_seconds':120., 'output':str(output)}, stream)
    command = [sys.executable, '-m', MODULE, '--output', str(output),
        '--pure-directory', str(args.pure_directory.resolve()), '--worker', '--admission', token]
    stdout_path = output.with_name(output.name+'.metadata_worker.stdout.log')
    stderr_path = output.with_name(output.name+'.metadata_worker.stderr.log')
    with stdout_path.open('x', encoding='utf8') as stdout, stderr_path.open('x', encoding='utf8') as stderr:
        remaining = 120.-(time.monotonic()-BOOT)-1.
        if remaining <= 0: raise TimeoutError('owned_prepare_budget_before_worker')
        process = bounded_windows_job.run(command, timeout=remaining, stdout=stdout, stderr=stderr,
            admission=token, cwd=ROOT)
    receipt = {'process':process, 'command':command, 'shared_seconds':120.,
        'before_parent_receipt_seconds':time.monotonic()-BOOT,
        'native_calls':0, 'C_loads':0, 'model_calls':0, 'performance_runs':0,
        'external_full_startup_exit_clock_required':True}
    path = output.with_name(output.name+'.metadata_parent.json')
    with path.open('x', encoding='utf8') as stream: json.dump(receipt,stream,indent=2)
    print(json.dumps(receipt))
    return 0 if process['status']=='exited' and process['exitcode']==0 and receipt['before_parent_receipt_seconds']<120. else 1


if __name__ == '__main__': raise SystemExit(main())
