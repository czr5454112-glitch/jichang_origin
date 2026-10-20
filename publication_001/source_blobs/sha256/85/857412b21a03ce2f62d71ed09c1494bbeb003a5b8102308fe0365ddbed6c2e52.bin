"""Independent quiescent-cap campaign, one new2400s Windows Job; no old extension."""
import time
BOOT = time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
from . import bounded_windows_job

LIMIT = 2400.


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path); p.add_argument('--campaign-sha256', required=True)
    a = p.parse_args(); output = a.output.resolve(); campaign = output/'campaign.json'
    digest = hashlib.sha256(campaign.read_bytes()).hexdigest()
    if digest != a.campaign_sha256: raise ValueError('quiescent_launch:campaign_changed')
    if (output/'receipt.json').exists() or (output/'external_launch_receipt.json').exists(): raise ValueError('quiescent_launch:already_attempted')
    with (output/'external_launch_claim.json').open('x', encoding='utf8') as f:
        json.dump({'campaign_sha256': digest, 'shared_seconds': LIMIT}, f)
    command = [sys.executable, '-m', 'scripts.experiments.g31_ics_circulation.research_original_low_wip_quiescent',
        '--output', str(output), '--campaign', '--admission', digest]
    remaining = LIMIT-(time.monotonic()-BOOT)
    receipt = {'status': 'unknown_before_dispatch', 'command': command, 'campaign_sha256': digest,
        'shared_seconds': LIMIT, 'pre_job_wall_seconds': LIMIT-remaining,
        'outer_python_startup_before_BOOT_unmeasured': True, 'complete_100ms_certified': False}
    result = None
    try:
        if remaining <= 0: raise TimeoutError('quiescent_launch:budget_before_job')
        with (output/'campaign.stdout.log').open('x', encoding='utf8') as stdout, (output/'campaign.stderr.log').open('x', encoding='utf8') as stderr:
            result = bounded_windows_job.run(command, timeout=remaining, stdout=stdout, stderr=stderr,
                admission=digest, cwd=Path(__file__).resolve().parents[3])
        receipt['process'] = result
        receipt['status'] = 'campaign_process_exited' if result['status'] == 'exited' and result['exitcode'] == 0 else 'unknown_campaign_process'
        if receipt['status'] == 'campaign_process_exited':
            internal = json.loads((output/'receipt.json').read_bytes())
            if (internal.get('status') != 'completed_finite_campaign' or internal.get('campaign_sha256') != digest
                    or set(internal.get('cases', {})) != {'cap3', 'cap8'} or internal.get('source_changed') != []):
                raise ValueError('quiescent_launch:internal_receipt_unconfirmed')
    except BaseException as error:
        receipt.update(status='unknown_launcher_error', error=repr(error)); raise
    finally:
        receipt['whole_dispatch_wall_seconds'] = time.monotonic()-BOOT
        if receipt['whole_dispatch_wall_seconds'] > LIMIT: receipt['status'] = 'unknown_shared_budget_overrun'
        for name in ('receipt.json','branch_ledger.json','campaign.stdout.log','campaign.stderr.log'):
            path = output/name
            if path.is_file(): receipt.setdefault('artifact_sha256', {})[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        with (output/'external_launch_receipt.json').open('x', encoding='utf8') as f: json.dump(receipt, f, ensure_ascii=False, indent=2)
    return 0 if receipt['status'] == 'campaign_process_exited' else 1


if __name__ == '__main__': raise SystemExit(main())
