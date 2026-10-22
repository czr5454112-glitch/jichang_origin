"""Wait for one frozen predecessor block, then execute its bound successor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_budget as budget
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_campaign as flow
from scripts.experiments.g31_ics_circulation.foundation_airport_inventory_spi_campaign import read_bound, bound


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--predecessor-runner', required=True)
    parser.add_argument('--max-wait-seconds', type=int, required=True)
    parser.add_argument('--dispatch', type=Path, required=True)
    args = parser.parse_args()
    ref = dict(path=str(args.registration.resolve()), sha256=args.sha256)
    registration = read_bound(ref)
    previous = read_bound(registration['predecessor_block'])
    assert args.max_wait_seconds > 0
    began = time.monotonic()
    with args.dispatch.open('x', encoding='utf8') as stream:
        def event(name, **fields):
            row = dict(event=name, at=budget.now(), **fields)
            stream.write(json.dumps(row, ensure_ascii=False)+'\n'); stream.flush()
            print(json.dumps(row, ensure_ascii=False), flush=True)
        event('waiting_for_frozen_predecessor', registration=ref, waiter=bound(__file__),
              predecessor=registration['predecessor_block'], max_wait_seconds=args.max_wait_seconds)
        try:
            while True:
                state = budget.status(flow.campaign.CYCLE)
                if any(identity != args.predecessor_runner for identity in state['open_runners']):
                    raise RuntimeError('unexpected_active_runner; predecessor and other work left untouched')
                if not state['open_runners']:
                    if state['unfinished_native_tasks']:
                        raise RuntimeError('unresolved_native_task; explicit audit required')
                    evaluation = flow.evaluate([registration['predecessor_block']['path']])
                    if not evaluation['all_registered_closed']:
                        raise RuntimeError('predecessor_not_closed; successor not started')
                    break
                if time.monotonic()-began >= args.max_wait_seconds:
                    raise TimeoutError('bounded_predecessor_wait_expired; native runner left untouched')
                time.sleep(30.)
            read_bound(ref)
            if bound(registration['driver']['path']) != registration['driver']:
                raise RuntimeError('successor_driver_changed')
            event('successor_started', driver=registration['driver'])
            result = subprocess.run([sys.executable, registration['driver']['path'], str(args.registration)],
                                    cwd=ROOT, check=False)
            event('successor_process_finished', exitcode=result.returncode)
            return result.returncode
        except Exception as exc:
            event('dispatch_failed', exception_type=type(exc).__name__, reason=str(exc))
            raise


if __name__ == '__main__':
    raise SystemExit(main())
