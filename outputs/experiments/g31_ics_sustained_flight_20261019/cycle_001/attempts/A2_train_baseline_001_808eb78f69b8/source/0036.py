"""Prepare one declared repeated-domain branch, then run in one bounded job."""
from __future__ import annotations
import sys
if __name__ == '__main__' and '--worker' in sys.argv:
    if '--admission' not in sys.argv or sys.stdin.readline().strip() != sys.argv[sys.argv.index('--admission') + 1]:
        raise SystemExit('repeated_campaign:missing_parent_job_admission')

import argparse
import gzip
import json
from pathlib import Path
import secrets
import traceback
from . import foundation_repeated_native as implementation
from . import foundation_repeated_domain as domain
from . import foundation_native_environment as environment
from . import foundation_later_campaign as campaign
from . import bounded_windows_job
from . import run_sustained_learning as sustained_budget  # Pin the actual bounded outer scheduler in every entry point.

ROOT = environment.ROOT
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_repeated_campaign'
SCHEMA = 'g31.foundation.repeated_campaign.v1'
HARD_SECONDS = 150
require = domain.require


def validate_original_reference(raw_path, case):
    """Closed same-input baseline, including its immutable historical archive."""
    raw_path = Path(raw_path).resolve(); folder = raw_path.parent
    raw = json.loads(gzip.decompress(raw_path.read_bytes()))
    report_path, receipt_path = folder/'worker_report.json', folder/'receipt.json'
    acceptance_path, plan_path = folder/'acceptance.json', folder/'plan.json'
    report, receipt, accepted, baseline = (campaign.read(path)
        for path in (report_path, receipt_path, acceptance_path, plan_path))
    require(receipt['status'] == report['status'] == 'completed_native_branch'
        and receipt['worker_report'] == campaign.reference(report_path)
        and receipt['process']['status'] == 'exited' and receipt['process']['exitcode'] == 0
        and receipt['process']['windows_job_kill_on_close'] is True
        and receipt['process']['child_released_only_after_job_assignment'] is True
        and report['raw'] == campaign.reference(raw_path) and report['source_exit_pins_passed'] is True
        and report['run_acceptance_status'] == accepted['status'] == 'closed_run_acceptance_passed'
        and accepted['active'] is False and accepted['invalid'] == []
        and accepted['run_reference'] == campaign.reference(plan_path), 'closed_original_baseline_origin')
    key = case + '/baseline'
    require(baseline['schema'] == SCHEMA and baseline['branch_order'] == accepted['branch_keys'] == [key]
        and baseline['rows'][key] == raw['specification'] and raw['specification']['mode'] == 'baseline'
        and raw['input'] == domain.scene(case) and report['summary'] == raw['summary']
        and raw['summary']['status'] == 'assessed' and raw['summary']['audit']['status'] == 'passed',
        'complete_same_input_original_baseline')
    input_path = folder/'inputs'/(key+'.json')
    require(campaign.sha(input_path) == baseline['input_file_sha256'][key]
        and campaign.read(input_path) == raw['input'], 'baseline_declared_input_binding')
    for source, relative in baseline['source_archive'].items():
        archive = (folder/relative).resolve()
        require(archive.is_relative_to(folder) and campaign.sha(archive) == baseline['source_sha256'][source]
            and accepted['evidence_sha256'].get(source) == baseline['source_sha256'][source],
            'baseline_historical_source_archive_binding')
    return raw, {name: campaign.reference(path) for name, path in
        (('raw', raw_path), ('worker_report', report_path), ('receipt', receipt_path),
         ('acceptance', acceptance_path), ('plan', plan_path))}


def prepare(output, case, mode, reference_path=None, selection='score', model_path=None):
    output = Path(output).resolve()
    require(not output.exists(), 'fresh_repeated_output')
    reference, binding, provenance = None, None, None
    if mode != 'baseline':
        require(reference_path is not None, 'same_input_original_reference_required')
        reference_path = Path(reference_path).resolve()
        raw, provenance = validate_original_reference(reference_path, case)
        require(raw['input'] == domain.scene(case) and raw['specification']['mode'] == 'baseline'
            and raw['summary']['status'] == 'assessed' and set(raw['summary']['completion']) == set(domain.manifest(case)['business_ids'])
            and all(domain.finite(value) and value >= 0 for value in raw['summary']['completion'].values()),
            'complete_same_input_fixed_original_reference')
        reference = {'completion': raw['summary']['completion'], 'input_sha256': domain.digest(raw['input']),
            'reference_refresh_allowed': False, 'kind': 'frozen_paired_actual_baseline', 'actor_access': False}
        binding = campaign.reference(reference_path)
    require(selection in ('score', 'prefer_3', 'prefer_8', 'native_default'), 'fixed_current_selection')
    row = {'case': case, 'mode': mode, 'domain': domain.manifest(case), 'reference': reference, 'selection': selection}
    if model_path is not None:
        require(mode != 'baseline' and selection == 'score', 'model_ranking_requires_protected_score_mode')
        model_path = Path(model_path).resolve()
        checkpoint = campaign.read(model_path)
        implementation.learned_value.predict(checkpoint, [], [])
        row.update(model_reference=campaign.reference(model_path), model_content_sha256=checkpoint['model_sha256'],
            model_used_as_authority=False)
    old = environment.online.old
    contract_path = old.OUT / 'native027_accepted_contract_001.json'
    semantic_path = old.OUT / 'native027_semantic_native_002/receipt.json'
    contract = old.read(contract_path)
    key = case + '/' + mode
    output.mkdir(parents=True)
    hashes, archives = environment.archive_sources(output, old.bound.imported_sources())
    input_path = output / 'inputs' / (key + '.json')
    environment.write(input_path, domain.scene(case))
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'rows': {key: row}, 'branch_order': [key],
        'native_branch_budget': 1, 'hard_seconds': HARD_SECONDS, 'automatic_retries': 0,
        'source_sha256': hashes, 'source_archive': archives, 'input_file_sha256': {key: old.sha(input_path)},
        'native_contract_reference': old.reference(contract_path), 'semantic_gate_reference': old.reference(semantic_path),
        'binary': old.reference(contract['binary']), 'original_reference': binding,
        'original_reference_provenance': provenance,
        'timing_mode': 'event_clock_resident_process' if mode == 'async' else 'offline_sync', 'realtime_async': False}
    environment.write(output / 'plan.json', plan)
    return plan


def verify(plan):
    require(plan['schema'] == SCHEMA and plan['native_branch_budget'] == 1 and plan['hard_seconds'] == HARD_SECONDS
        and plan['automatic_retries'] == 0 and len(plan['rows']) == 1, 'bounded_repeated_plan')
    require(plan['source_sha256'] == {str(path): campaign.sha(path) for path in implementation.bound.imported_sources()},
        'repeated_source_inventory_or_bytes_changed')
    for item in (plan['native_contract_reference'], plan['semantic_gate_reference'], plan['binary'], plan['original_reference']):
        if item:
            require(campaign.sha(item['path']) == item['sha256'], 'repeated_reference_changed')
    for row in plan['rows'].values():
        domain.validate_scene(domain.scene(row['case']), row['domain'])
        if row.get('model_reference'):
            ref = row['model_reference']
            require(row['mode'] != 'baseline' and row['selection'] == 'score', 'model_ranking_requires_protected_score_mode')
            require(campaign.sha(ref['path']) == ref['sha256'] and row['model_used_as_authority'] is False,
                'frozen_model_file_binding')
            checkpoint = campaign.read(ref['path'])
            implementation.learned_value.predict(checkpoint, [], [])
            require(checkpoint['model_sha256'] == row['model_content_sha256'], 'frozen_model_content_binding')
        if row['mode'] != 'baseline':
            raw, provenance = validate_original_reference(plan['original_reference']['path'], row['case'])
            require(provenance == plan['original_reference_provenance']
                and raw['summary']['completion'] == row['reference']['completion'], 'frozen_original_reference_binding')


def worker(output, expected):
    output = Path(output).resolve(); plan = campaign.read(output / 'plan.json')
    report = {'schema': SCHEMA, 'status': 'unknown_failed', 'native_execution_attempted': False}
    accepted, resident, progress = None, None, {}
    try:
        require(campaign.sha(output / 'plan.json') == expected, 'repeated_plan_changed')
        verify(plan)
        key = plan['branch_order'][0]; row = plan['rows'][key]
        if row['mode'] == 'async':
            resident = implementation.worker.ResidentWorker('B', output / 'resident_B'); resident.start()
        binding = campaign.reference(output / 'plan.json')
        accepted = implementation.physical.run_admission.open_run(plan['native_contract_reference'],
            plan['semantic_gate_reference'], binding)
        native = implementation.physical.native_host.load_native(Path(plan['binary']['path']))
        accepted.enter_branch(key, binding)
        report['native_execution_attempted'] = True
        checkpoint = campaign.read(row['model_reference']['path']) if row.get('model_reference') else None
        raw = implementation.run_branch(native, accepted, key, plan['native_contract_reference'], row,
            resident=resident, progress=progress, learned_model=checkpoint)
        path = output / 'raw.json.gz'
        path.write_bytes(gzip.compress(json.dumps(raw, allow_nan=False).encode(), compresslevel=1, mtime=0))
        report.update(status='completed_native_branch', raw=campaign.reference(path), summary=raw['summary'],
            decision_count=len(raw['repeated_decisions']), guarded_nondefault_count=sum(
                item['current_admission']['execution_mode'] == 'protected_current'
                and item['selected_action_id'] == 'prefer_8' for item in raw['repeated_decisions']))
        accepted.finish_branch(key)
    except Exception:
        report['exception'] = traceback.format_exc()
        partial = implementation.physical.capture_partial(progress, report['exception'])
        partial['repeated_attempts'] = {owner: policy.repeated_attempts for owner, policy in progress.get('policies', {}).items()}
        environment.write(output / 'partial.json', partial)
        report['partial'] = campaign.reference(output / 'partial.json')
    finally:
        if resident:
            resident.close()
            environment.write(output / 'resident_audit.json', {'timing': resident.timing, 'records': resident.records})
            report['resident_audit'] = campaign.reference(output / 'resident_audit.json')
        if accepted:
            closed = accepted.close(); environment.write(output / 'acceptance.json', closed)
            report['run_acceptance_status'] = closed['status']
            if closed['status'] != 'closed_run_acceptance_passed':
                report['status'] = 'unknown_invalidated_runtime_evidence'
        try:
            verify(plan); report['source_exit_pins_passed'] = True
        except Exception:
            report['source_exit_pins_passed'] = False; report['exit_exception'] = traceback.format_exc()
            report['status'] = 'unknown_failed'
    environment.write(output / 'worker_report.json', report)
    return report


def launch(output):
    output = Path(output).resolve(); plan = campaign.read(output / 'plan.json'); verify(plan)
    require(not (output / 'launch_started.json').exists(), 'no_automatic_branch_retry')
    expected = campaign.sha(output / 'plan.json'); token = secrets.token_hex(24)
    environment.write(output / 'launch_started.json', {'plan_sha256': expected, 'native_branch_budget': 1})
    with (output / 'stdout.log').open('x') as stdout, (output / 'stderr.log').open('x') as stderr:
        process = bounded_windows_job.run([sys.executable, '-m', MODULE, '--worker', '--output', str(output),
            '--plan-sha256', expected, '--admission', token], timeout=HARD_SECONDS,
            admission=token, stdout=stdout, stderr=stderr, cwd=ROOT)
    report_path = output / 'worker_report.json'
    report = campaign.read(report_path) if report_path.exists() else {}
    result = {'schema': SCHEMA, 'status': 'completed_native_branch' if process.get('exitcode') == 0
        and report.get('status') == 'completed_native_branch' else 'unknown_failed', 'process': process,
        'worker_report': campaign.reference(report_path) if report_path.exists() else None}
    environment.write(output / 'receipt.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(); options = parser.add_mutually_exclusive_group(required=True)
    for action in ('prepare', 'launch', 'worker'):
        options.add_argument('--' + action, action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=tuple(domain.CASES), default='legacy_mechanism')
    parser.add_argument('--mode', choices=('baseline', 'guarded', 'async'), default='baseline')
    parser.add_argument('--reference', type=Path); parser.add_argument('--plan-sha256'); parser.add_argument('--admission')
    parser.add_argument('--selection', choices=('score', 'prefer_3', 'prefer_8', 'native_default'), default='score')
    parser.add_argument('--model', type=Path)
    args = parser.parse_args()
    if args.worker:
        result = worker(args.output, args.plan_sha256)
    elif args.prepare:
        result = prepare(args.output, args.case, args.mode, args.reference, args.selection, args.model)
    else:
        result = launch(args.output)
    print(json.dumps({'status': result['status']}))
    return 0 if result['status'] in ('prepared_unexecuted', 'completed_native_branch') else 1


if __name__ == '__main__':
    raise SystemExit(main())
