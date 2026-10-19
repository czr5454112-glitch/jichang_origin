"""One fresh cap8 worker and complete verifier under one owned2400s Job."""
import time
BOOT = time.monotonic()
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from . import bounded_windows_job

LIMIT = 2400.
MODULE = 'scripts.experiments.g31_ics_circulation.research_original_low_wip_cap_relay'


def validate_internal(receipt, digest):
    if (receipt.get('schema') != 'g31.original_low_wip_cap_relay.v1'
        or receipt.get('status') != 'completed_finite_campaign' or receipt.get('campaign_sha256') != digest
        or set(receipt.get('cases', {})) != {'cap8'} or receipt.get('source_changed') != []
        or receipt.get('new_same_policy_cap3_pair') is not False
        or receipt.get('assessment', {}).get('status') != 'complete_cap8_with_bidirectional_cap_relay'):
        raise ValueError('cap_relay_launch:unconfirmed_complete_receipt')
    case = receipt['cases']['cap8']
    elapsed = receipt.get('wall_seconds')
    if (case.get('status') != 'completed_saved_case'
        or any(case.get(key, {}).get('exit_code') != 0 for key in ('execution', 'verification'))
        or type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 <= elapsed <= LIMIT):
        raise ValueError('cap_relay_launch:incomplete_or_over_budget_case')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path); parser.add_argument('--campaign-sha256', required=True)
    args = parser.parse_args(); output = args.output.resolve(); campaign = output / 'campaign.json'
    digest = hashlib.sha256(campaign.read_bytes()).hexdigest()
    if digest != args.campaign_sha256: raise ValueError('cap_relay_launch:campaign_changed')
    if (output / 'receipt.json').exists() or (output / 'external_launch_receipt.json').exists():
        raise ValueError('cap_relay_launch:already_attempted')
    with (output / 'external_launch_claim.json').open('x', encoding='utf8') as stream:
        json.dump({'campaign_sha256': digest, 'shared_seconds': LIMIT}, stream)
    command = [sys.executable, '-m', MODULE, '--output', str(output), '--campaign', '--admission', digest]
    remaining = LIMIT - (time.monotonic() - BOOT)
    receipt = {'schema': 'g31.cap_relay.launch_receipt.v1', 'status': 'unknown_before_dispatch',
        'command': command, 'campaign_sha256': digest, 'shared_seconds': LIMIT,
        'pre_job_wall_seconds': LIMIT - remaining, 'outer_python_startup_before_BOOT_unmeasured': True,
        'complete_100ms_certified': False}
    try:
        if remaining <= 0: raise TimeoutError('cap_relay_launch:budget_before_job')
        with (output / 'campaign.stdout.log').open('x', encoding='utf8') as stdout, \
             (output / 'campaign.stderr.log').open('x', encoding='utf8') as stderr:
            process = bounded_windows_job.run(command, timeout=remaining, stdout=stdout, stderr=stderr,
                admission=digest, cwd=Path(__file__).resolve().parents[3])
        receipt['process'] = process
        receipt['status'] = 'campaign_process_exited' if process['status'] == 'exited' and process['exitcode'] == 0 else 'unknown_campaign_process'
        if receipt['status'] == 'campaign_process_exited':
            validate_internal(json.loads((output / 'receipt.json').read_bytes()), digest)
    except BaseException as error:
        receipt.update(status='unknown_launcher_error', error=repr(error))
    finally:
        receipt['dispatch_through_before_final_evidence_export_wall_seconds'] = time.monotonic() - BOOT
        if receipt['dispatch_through_before_final_evidence_export_wall_seconds'] > LIMIT:
            receipt['status'] = 'unknown_shared_budget_overrun'
        for name in ('receipt.json', 'branch_ledger.json', 'campaign.stdout.log', 'campaign.stderr.log'):
            path = output / name
            if path.is_file(): receipt.setdefault('artifact_sha256', {})[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        with (output / 'external_launch_receipt.json').open('x', encoding='utf8') as stream:
            json.dump(receipt, stream, indent=2)
    return 0 if receipt['status'] == 'campaign_process_exited' else 1


if __name__ == '__main__': raise SystemExit(main())
