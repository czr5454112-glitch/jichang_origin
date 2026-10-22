"""Execute the finite, registered terminal-flow development sequence serially.

No automatic TEST, native retries, budget reset, or parameter search. Resume
reuses closed receipts and stops on the first nonclosed native task.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_campaign as campaign
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_budget as budget
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_campaign as flow
from scripts.experiments.g31_ics_circulation.foundation_airport_inventory_spi_campaign import bound, read_bound
from scripts.experiments.g31_ics_circulation.foundation_airport_terminal_flow_audit import baseline_equivalence, closed_run
from scripts.experiments.g31_ics_circulation.foundation_airport_terminal_full_training import (
    run_training, PRODUCER_FILES, SCHEMA as TRAINING_SCHEMA)
from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_forecast as demand
from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_support_predictor as supported


def require(value, reason):
    if not value:
        raise ValueError('terminal_flow_workflow:'+reason)


def save_once(path, value):
    path = Path(path)
    if path.exists():
        require(flow.read(path) == value, 'immutable_output_changed:'+str(path))
    else:
        flow.write_once(path, value)
    return bound(path)


def emit(event, **fields):
    print(json.dumps(dict(event=event, **fields), ensure_ascii=False), flush=True)


def validate_source(source):
    manifest = read_bound(source)
    require(manifest['schema'] == campaign.SCHEMA+'.sources' and bool(manifest['files']), 'source_schema_and_files')
    require(manifest['worker_evidence_contract'] == campaign.EVIDENCE_EXPORT, 'export_contract')
    require(manifest['source_manifest_sha256'] == campaign.common.digest(manifest['files']), 'source_manifest')
    frozen_root = Path(manifest['root']).resolve()
    for name, sha in manifest['files'].items():
        for root in (ROOT.resolve(), frozen_root):
            path = (root/name).resolve()
            require(path.is_relative_to(root), 'source_path_outside_root:'+name)
            require(campaign.common.sha(path) == sha, 'working_or_frozen_source_changed:'+name)
    return manifest


def validate_registration(registration):
    stages = registration['stages']
    require([x['phase'] for x in stages] == ['export_gate','train_demand','bridge','bins','period','predictor'],
            'fixed_stage_order')
    require(stages[0]['parents'] == [2101] and stages[1]['parents'] == [2101,2102]
            and all(x['parents'] == [2201,2202,2203,2204] for x in stages[2:]), 'fixed_parent_roster')
    names = [entry['name'] for entry in stages]
    require(len(set(names)) == len(names) and all(isinstance(name, str) and name not in ('', '.', '..')
        and Path(name).name == name and '/' not in name and '\\' not in name for name in names), 'unique_local_block_names')
    require(set(registration['export_equivalence_references']) == {'C00', 'TF-B1-300'},
            'both_export_equivalence_references_required')
    for method, previous in registration['export_equivalence_references'].items():
        plan, _, _ = closed_run(previous)
        require(plan['method'] == method and plan['horizon'] == 18000.
            and plan['parent']['parent_seed'] == 2101 and plan['parent']['split'] == 'train',
            'registered_export_reference:'+method)
    allowance = registration['fit_active_seconds_allowance']
    estimate = registration['fit_estimated_evidence_bytes']
    require(type(allowance) in (int, float) and math.isfinite(allowance) and allowance > 0,
            'positive_fit_active_seconds_allowance')
    require(type(estimate) is int and estimate > 0, 'positive_fit_evidence_estimate')
    for key, filename in (('runtime_calibration', 'runtime_calibration_001.json'),
                          ('campaign_budget', 'campaign_budget.json')):
        require(registration[key] == bound(campaign.CYCLE/filename), 'registered_'+key+'_binding')
    supplemental_root = Path(registration['supplemental_evidence_root']).resolve()
    require(supplemental_root == (ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021').resolve(),
            'supplemental_evidence_root_binding')
    model_directory = Path(registration['model_output']).resolve()
    require(model_directory != supplemental_root and model_directory.is_relative_to(supplemental_root),
            'model_output_within_accounted_evidence_root')


def registered_batch(phase):
    return 'bridge' if phase == 'export_gate' else 'development' if phase in ('bridge', 'bins') else 'initial'


def model_reference(model):
    """Artifact-size metadata is not part of a campaign's file identity."""
    return None if model is None else dict(path=str(Path(model['path']).resolve()), sha256=model['sha256'])


def checked_block(entry, source, model=None, *, check_model=True):
    path = flow.ROOT/entry['name']/'block.json'
    block = flow.read(path)
    require(block['phase'] == entry['phase'] and block['parents'] == entry['parents']
        and block['source_bundle'] == source and (not check_model or block['demand_model'] == model_reference(model)),
        'existing_block_registration_differs')
    require(block['batch'] == registered_batch(entry['phase']), 'existing_block_batch_differs')
    flow._validate_block_manifest(block)
    flow._validate_dependencies(block)
    for reference in block['task_plans']:
        plan = read_bound(reference)
        require(plan['batch'] == block['batch'], 'registered_task_batch_binding')
        campaign.verify_calibration(plan)
        if entry['phase'] == 'export_gate':
            require((plan['horizon'], plan['soft_seconds'], plan['hard_seconds'], plan['estimated_evidence_bytes'])
                == (18000., 660., 720., 128*1024**2), 'registered_export_gate_limits')
        else:
            require(plan['calibration'] == bound(campaign.CYCLE/'runtime_calibration_001.json'),
                    'registered_full_runtime_calibration')
    evaluation = flow.evaluate([path])
    require(all(row['status'] == 'not_started' or row['closure_verified'] for row in evaluation['runs']),
            'existing_nonclosed_run_requires_explicit_audit:'+entry['name'])
    return block, evaluation


def read_artifact(reference):
    require(campaign.common.sha(reference['path']) == reference['sha256'], 'fit_artifact_hash_binding')
    return flow.read(reference['path'])  # training_rows is gzip, not UTF-8 JSON bytes


def validate_fit(fit, training, source, manifest, model_directory):
    require(fit['schema'] == TRAINING_SCHEMA and fit['row_count'] == 580 and fit['native_starts'] == 0,
            'complete_training_fit_receipt')
    values = {}
    for key, filename in (('model', 'model.json'), ('training_rows', 'training_rows.json.gz'),
                          ('provenance', 'provenance.json')):
        require(Path(fit[key]['path']).resolve() == (model_directory/filename).resolve(), 'fit_output_directory_binding')
        values[key] = read_artifact(fit[key])
    model, rows, provenance = values['model'], values['training_rows'], values['provenance']
    supported.validate_model(model)
    labels_sha256 = demand.digest(rows)
    require(len(rows) == provenance['row_count'] == 580
        and provenance['training_labels_sha256'] == model['base_calibration']['training_labels_sha256'] == labels_sha256
        and model['base_calibration']['training_row_count'] == 580
        and provenance['model_sha256'] == fit['model_sha256'] == model['sha256']
        and provenance['DEV_or_TEST_labels_read'] is False and provenance['native_starts'] == 0,
        'training_fit_content_binding')
    require(provenance['schema'] == TRAINING_SCHEMA and provenance['common_time_support'] == [7200., 59400.]
        and provenance['forecast_bin_seconds'] == 300. and provenance['forecast_horizon_seconds'] == 1800.
        and provenance['prior_exposure'] == 8.
        and model['base_calibration']['bin_edges_seconds'] == demand.bin_edges('300')
        and model['base_calibration']['prior_exposure'] == 8.
        and len(model['support_by_station']) == 10
        and all(windows == [[7200., 59400.]] for windows in model['support_by_station'].values()),
        'fixed_complete_training_fit_contract')
    expected = {str(Path(ref['path']).resolve()): ref for ref in training['task_plans']}
    actual = provenance['sources']
    require(len(actual) == len(expected) == 2, 'two_registered_training_provenances')
    seen = set()
    for item in actual:
        saved = item['provenance']['plan.json']
        key = str(Path(saved['path']).resolve())
        require(key in expected and key not in seen and saved['sha256'] == expected[key]['sha256'],
                'fit_registered_training_plan_binding')
        seen.add(key)
        plan = read_bound(expected[key])
        require(item['parent'] == plan['parent'] and item['parent']['split'] == 'train'
            and item['source_bundle'] == plan['source_bundle'] == source and item['mapping'] == plan['mapping'],
            'fit_training_source_contract')
        for name in ('plan.json', 'worker_report.json', 'receipt.json', 'terminal_evidence.json.gz', 'decision_stream'):
            ref = item['provenance'][name]
            filename = 'decisions.json.gz' if name == 'decision_stream' else name
            require(Path(ref['path']).resolve() == Path(key).parent/filename
                and campaign.common.sha(ref['path']) == ref['sha256'], 'fit_training_evidence_binding:'+name)
    require(sorted(item['parent']['parent_group'] for item in actual) == model['base_calibration']['train_parent_ids'],
            'fit_model_registered_parent_binding')
    producers = provenance['source_files']
    require(set(producers) == set(PRODUCER_FILES) and provenance['producer_sources_unchanged'] is True,
            'fit_producer_roster')
    for name, ref in producers.items():
        relative = 'scripts/experiments/g31_ics_circulation/'+name
        require(Path(ref['path']).resolve() == (ROOT/relative).resolve()
            and ref['sha256'] == manifest['files'][relative]
            and campaign.common.sha(ref['path']) == ref['sha256'], 'fit_frozen_producer_binding:'+name)
    return fit


def preflight_budget(registration, source, directory, manifest):
    """Reserve the finite remaining matrix; runtime admission still rechecks each task."""
    status = budget.status(campaign.CYCLE)
    require(not status['open_runners'] and not status['unfinished_native_tasks'], 'active_or_unresolved_work')
    limits = read_bound(registration['campaign_budget'])
    calibration = read_bound(registration['runtime_calibration'])
    counts, hard_seconds, evidence_bytes = Counter(), 0., 0
    existing = {}
    for entry in registration['stages']:
        batch = registered_batch(entry['phase'])
        path = flow.ROOT/entry['name']/'block.json'
        if path.exists():
            block, evaluation = checked_block(entry, source, check_model=False)
            existing[entry['phase']] = block
            pending = {row['task_id'] for row in evaluation['runs'] if row['status'] == 'not_started'}
            plans = [read_bound(ref) for ref in block['task_plans']]
            plans = [plan for plan in plans if plan['task_id'] in pending]
        else:
            short = entry['phase'] == 'export_gate'
            plans = [dict(hard_seconds=720. if short else calibration['hard_seconds'],
                          estimated_evidence_bytes=128*1024**2 if short else calibration['estimated_evidence_bytes'])
                     for _ in range(len(entry['parents'])*len(flow.METHODS[entry['phase']]))]
        counts[batch] += len(plans)
        hard_seconds += sum(plan['hard_seconds'] for plan in plans)
        evidence_bytes += sum(plan['estimated_evidence_bytes'] for plan in plans)
    receipt = directory/'training_fit_receipt.json'
    model_directory = Path(registration['model_output']).resolve()
    if receipt.exists():
        require('train_demand' in existing, 'fit_without_registered_training_block')
        validate_fit(flow.read(receipt), existing['train_demand'], source, manifest, model_directory)
    else:
        require(not model_directory.exists(), 'unclosed_fit_requires_explicit_audit')
        hard_seconds += registration['fit_active_seconds_allowance']
        evidence_bytes += registration['fit_estimated_evidence_bytes']
    require(status['native_starts']+sum(counts.values()) <= limits['native_start_limit'], 'whole_workflow_native_budget')
    require(all(status['by_batch'][batch]+count <= limits['allocations'][batch] for batch, count in counts.items()),
            'whole_workflow_batch_budget')
    require(status['active_seconds']+hard_seconds <= limits['active_seconds_limit'], 'whole_workflow_active_time_budget')
    supplemental_root = Path(registration['supplemental_evidence_root']).resolve()
    supplemental_bytes = sum(path.stat().st_size for path in supplemental_root.rglob('*') if path.is_file()
                             and not path.resolve().is_relative_to(campaign.CYCLE.resolve()))
    require(status['evidence_bytes']+supplemental_bytes+evidence_bytes < limits['new_evidence_bytes_limit']
        and status['free_bytes']-evidence_bytes >= limits['free_space_floor_bytes'], 'whole_workflow_disk_budget')
    return dict(remaining_native_starts=sum(counts.values()), remaining_by_batch=dict(counts),
                reserved_active_seconds=hard_seconds, reserved_evidence_bytes=evidence_bytes,
                supplemental_existing_evidence_bytes=supplemental_bytes)


def run_registered_block(entry, source, model=None):
    validate_source(source)
    model = model_reference(model)
    path = flow.ROOT/entry['name']/'block.json'
    if path.exists():
        block, evaluation = checked_block(entry, source, model)
    else:
        block = flow.prepare_block(entry['name'], phase=entry['phase'], source=source['path'],
            parents=entry['parents'], demand_model=model['path'] if model else None)
        block, evaluation = checked_block(entry, source, model)
    if not evaluation['all_registered_closed']:
        emit('block_started', name=entry['name'], phase=entry['phase'])
        evaluation = flow.run_block(path)
    require(evaluation['all_registered_closed'], 'block_not_closed:'+entry['name'])
    emit('block_closed', name=entry['name'], native_tasks=len(block['task_plans']))
    return block


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('registration', type=Path)
    args = parser.parse_args()
    registration = flow.read(args.registration)
    require(registration['schema'] == 'g31.terminal_flow.finite_development_workflow.v1', 'schema')
    require(bound(__file__) == registration['driver'], 'driver_hash_binding')
    source = registration['source_bundle']
    manifest = validate_source(source)
    validate_registration(registration)
    stages = registration['stages']
    directory = args.registration.resolve().parent
    reservation = preflight_budget(registration, source, directory, manifest)
    budget.append(campaign.CYCLE, 'terminal_flow_finite_workflow_invoked', registration=bound(args.registration),
        no_test_unlock=True, no_budget_reset=True, remaining_reservation=reservation)

    gate = run_registered_block(stages[0], source)
    gate_runs = {read_bound(ref)['method']: Path(ref['path']).parent for ref in gate['task_plans']}
    for method, previous in registration['export_equivalence_references'].items():
        report = baseline_equivalence(previous, gate_runs[method])
        save_once(directory/('export_equivalence_'+method+'.json'), report)
        require(report['same_finite_run_behavior'], 'export_equivalence_failed:'+method)
    emit('export_equivalence_passed', methods=sorted(gate_runs))

    preflight_budget(registration, source, directory, manifest)
    training = run_registered_block(stages[1], source)
    training_dirs = [str(Path(ref['path']).parent) for ref in training['task_plans']]
    model_directory = Path(registration['model_output']).resolve()
    model_receipt = directory/'training_fit_receipt.json'
    manifest = validate_source(source)
    if model_receipt.exists():
        fit = validate_fit(flow.read(model_receipt), training, source, manifest, model_directory)
    else:
        require(not model_directory.exists(), 'unclosed_fit_requires_explicit_audit')
        # Prior native blocks are now charged; recheck allowance immediately before fit.
        preflight_budget(registration, source, directory, manifest)
        identity = 'terminal-flow-fit-'+secrets.token_hex(12)
        budget.append(campaign.CYCLE, 'runner_open', runner_id=identity, purpose='full_TRAIN_demand_fit_004')
        try:
            fit = run_training(training_dirs, model_directory)
            manifest = validate_source(source)
            validate_fit(fit, training, source, manifest, model_directory)
            save_once(model_receipt, fit)
            budget.append(campaign.CYCLE, 'terminal_flow_demand_fit_closed', receipt=bound(model_receipt),
                TRAIN_only=True, native_starts=0)
        finally:
            budget.append(campaign.CYCLE, 'runner_close', runner_id=identity)
    emit('TRAIN_model_frozen', rows=fit['row_count'], model=fit['model'])

    blocks = [flow.ROOT/stages[0]['name']/'block.json', flow.ROOT/stages[1]['name']/'block.json']
    for entry in stages[2:]:
        preflight_budget(registration, source, directory, manifest)
        run_registered_block(entry, source, model=fit['model'] if entry['phase'] == 'predictor' else None)
        blocks.append(flow.ROOT/entry['name']/'block.json')
    evaluation = flow.evaluate(blocks)
    require(evaluation['all_registered_closed'], 'final_matrix_not_closed')
    save_once(directory/'development_evaluation.json', evaluation)
    save_once(directory/'completion.json', dict(schema=registration['schema'],
        registration=bound(args.registration), blocks=[bound(path) for path in blocks],
        training_fit=bound(model_receipt), evaluation=bound(directory/'development_evaluation.json'),
        all_registered_development_tasks_closed=True, TEST_unlocked=False, R1_enabled=False,
        scientific_service_audit_and_claim_review_required=True))
    emit('finite_development_sequence_closed', TEST_unlocked=False, service_claims_pending_audit=True)


if __name__ == '__main__':
    main()
