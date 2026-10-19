"""Fresh single cap8 attempt with one terminal cap snapshot per owner."""
from __future__ import annotations
import argparse
import ast
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import time
from . import research_original_low_wip_repeat as reference
from . import repeat_cap_barrier_relay as candidate

SCHEMA = 'g31.original_low_wip_cap_relay.v1'
MODULE = 'scripts.experiments.g31_ics_circulation.research_original_low_wip_cap_relay'
CAPS = {'cap8': 8}
LIMIT = 2400.
PRIOR = reference.OUT / 'original_low_wip_quiescent_prepare_001'
_original = {k: getattr(reference, k) for k in ('RepeatOwner', 'SCHEMA', 'MODULE', 'CAPS', 'contract', 'source_paths')}
_active = False


def source_paths():
    pending = [Path(__file__), Path(__file__).with_name('verify_original_low_wip_cap_relay.py'),
        Path(__file__).with_name('launch_original_low_wip_cap_relay.py'),
        reference.ROOT / 'tests/test_g31_circulation_cap_barrier_relay.py',
        reference.ROOT / 'tests/test_g31_circulation_low_wip_cap_relay.py', *_original['source_paths']()]
    found = set()
    def enqueue(target):
        for path in (target.with_suffix('.py'), target / '__init__.py'):
            if path.is_file() and path.resolve().is_relative_to(reference.ROOT):
                pending.append(path)
                for parent in path.parents:
                    if parent == reference.ROOT: break
                    if (parent / '__init__.py').is_file(): pending.append(parent / '__init__.py')
    while pending:
        path = pending.pop().resolve()
        if path in found: continue
        reference.require(path.is_file(), 'relay_source_missing'); found.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node, ast.ImportFrom):
                for root in ([path.parent] if node.level else [reference.ROOT, reference.ROOT / 'src']):
                    for _ in range(max(0, node.level - 1)): root = root.parent
                    if node.module: root = root.joinpath(*node.module.split('.')); enqueue(root)
                    for alias in node.names:
                        if alias.name != '*': enqueue(root / alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for root in (reference.ROOT, reference.ROOT / 'src'): enqueue(root.joinpath(*alias.name.split('.')))
    return sorted(found)


def prior_reference():
    names = ('ready.json', 'campaign.json', 'external_launch_receipt.json', 'powershell_launch_receipt.json',
             'branch_ledger.json', 'cap3/raw_final.json.gz', 'cap3/independent_verification.json',
             'cap3/api/manifest.jsonl', 'cap8/api/manifest.jsonl', 'cap8/heartbeat.json')
    return {'directory': str(PRIOR), 'artifacts': {name: reference.base.sha(PRIOR / name) for name in names},
        'scope': 'Prior quiescent cap3 is already verified historical evidence, not an execution of this new relay policy. Prior cap8 and its whole2400s attempt remain unknown. No new cap3/cap8 same-policy pair or completion-gain comparison is asserted.'}


def contract():
    value = deepcopy(_original['contract']())
    value['caps'] = dict(CAPS)
    value['limits'] = ('One fresh cap8 arm; all28506 jobs,22 trays,H86400,one circulating token, '
        '30 maximum physical requests,original ten-second activation and512 repeat publications perowner. '
        'One new2400s owned WindowsJob includes setup,worker,diagnostics and complete saved verifier; no budget extension or cap3 rerun.')
    value['cap_relay'] = candidate.scope()
    value['prior_attempt_reference'] = prior_reference()
    value['acceptance'] = ('Complete actual horizon and physical audit; alljob identities/states retained; '
        'exact saved-policy/API replay; both actual fresh cap proofs followed by exactly one own typed relay each '
        'and actual deliveredACK/selfcopy. Loss/rejection/expiry or one missing proof remains unknown. '
        'No strict-protection,deadline,whole-day-throughputoptimality or100ms claim.')
    return value


@contextmanager
def installed():
    global _active
    reference.require(not _active, 'cap_relay_context_overlap')
    prior = {key: getattr(reference, key) for key in _original}
    values = {'RepeatOwner': candidate.RepeatOwner, 'SCHEMA': SCHEMA, 'MODULE': MODULE,
              'CAPS': dict(CAPS), 'contract': contract, 'source_paths': source_paths}
    _active = True
    try:
        for key, value in values.items(): setattr(reference, key, value)
        yield
    finally:
        for key, value in prior.items(): setattr(reference, key, value)
        _active = False


def prepare(output):
    outer = reference.base.read(PRIOR / 'external_launch_receipt.json')
    reference.require(outer['status'] in {'unknown_campaign_process', 'unknown_shared_budget_overrun'}
        and outer['process']['status'] == 'hard_timeout', 'old_attempt_not_terminal_timeout')
    with installed(): return reference.prepare(output)


def campaign_worker(output, admission):
    reference.require(sys.stdin.readline().rstrip('\n') == admission, 'cap_relay_job_admission')
    reference.require(reference.base.sha(output / 'campaign.json') == admission and
        reference.base.read(output / 'external_launch_claim.json')['campaign_sha256'] == admission,
        'cap_relay_campaign_identity')
    began = time.monotonic()
    with installed():
        reference.verify_campaign(output)
        case = output / 'cap8'; plan = reference.base.read(case / 'preregistered_protocol.json')
        reference.base.claim_execution(case, plan)
        ledger = {'cap8': {'status': 'unknown_in_progress'}}
        reference.base.write(output / 'branch_ledger.json', ledger)
        def child(args, log):
            remaining = LIMIT - (time.monotonic() - began)
            if remaining <= 0: return {'status': 'unknown_shared_budget', 'exit_code': None}
            command = [sys.executable, '-m', MODULE, '--output', str(output), *args]
            start = time.monotonic()
            with log.open('xb') as stream:
                try:
                    code = subprocess.run(command, cwd=reference.ROOT, stdout=stream,
                        stderr=subprocess.STDOUT, timeout=remaining).returncode
                    status = 'child_finished' if code == 0 else 'unknown_child_nonzero'
                except subprocess.TimeoutExpired: code, status = None, 'unknown_shared_timeout'
            return {'status': status, 'exit_code': code, 'command': command,
                    'wall_seconds': time.monotonic() - start, 'allowed_seconds': remaining}
        execution = child(['--worker', 'cap8'], case / 'worker.log')
        verification = child(['--verify', 'cap8'], case / 'verification.log') if execution['exit_code'] == 0 \
            else {'status': 'unknown_worker_incomplete', 'exit_code': None}
        verified = reference.base.read(case / 'independent_verification.json') if verification['exit_code'] == 0 else None
        closure = verified.get('cap_relay_assessment', {}) if verified else {}
        complete = closure.get('status') == 'complete_cap8_with_bidirectional_cap_relay'
        ledger['cap8'] = {'status': 'completed_saved_case' if verification['exit_code'] == 0 else 'unknown_incomplete_case',
                         'execution': execution, 'verification': verification}
        reference.base.write(output / 'branch_ledger.json', ledger)
        reference.verify_campaign(output)
        elapsed = time.monotonic() - began
        receipt = {'schema': SCHEMA, 'status': 'completed_finite_campaign' if complete and elapsed <= LIMIT else 'unknown_incomplete_campaign',
            'campaign_sha256': admission, 'cases': ledger, 'wall_seconds': elapsed, 'source_changed': [],
            'assessment': closure, 'single_fresh_policy_case': True, 'new_same_policy_cap3_pair': False,
            'prior_attempt_reference': prior_reference(), 'strict_protection': 'unknown_unfinished_offered_jobs',
            'complete_100ms_certified': False}
        names = ('raw_final.json.gz', 'assessment.json', 'api/manifest.jsonl', 'independent_verification.json',
                 'all_job_states.json.gz', 'worker.log', 'verification.log', 'error_prefix.json.gz')
        receipt['artifact_sha256'] = {str(path.relative_to(output)): reference.base.sha(path)
            for path in [output / 'branch_ledger.json', *[case / name for name in names]] if path.is_file()}
        reference.base.write(output / 'receipt.json', receipt)
        return 0 if receipt['status'] == 'completed_finite_campaign' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--worker', choices=tuple(CAPS)); parser.add_argument('--verify', choices=tuple(CAPS))
    parser.add_argument('--campaign', action='store_true'); parser.add_argument('--admission')
    args = parser.parse_args(); output = args.output.resolve()
    reference.require(sum((args.prepare, bool(args.worker), bool(args.verify), args.campaign)) == 1, 'cap_relay_mode')
    if args.prepare: prepare(output); return
    if args.campaign: raise SystemExit(campaign_worker(output, args.admission))
    if args.worker:
        with installed(), reference.installed(): reference.base.worker(output / args.worker)
        return
    from .verify_original_low_wip_cap_relay import verify_case
    result = verify_case(output / args.verify)
    path = output / args.verify / 'independent_verification.json'
    reference.require(not path.exists(), 'cap_relay_verification_exists')
    reference.base.write(path, result)


if __name__ == '__main__': main()
