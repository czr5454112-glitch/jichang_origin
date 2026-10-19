"""Bounded calibration of a new complete 28,506-job airport OD contract.

The original airport C00/C10 outcomes remain untouched. Preparation loads no
native. Every branch starts at physical zero and keeps the original continuous
warmup/windows. A C10 preparation requires a closed new-domain C00 reference.
"""
from __future__ import annotations

import sys
if __name__ == '__main__' and '--worker' in sys.argv:
    if '--admission' not in sys.argv or sys.stdin.readline().strip() != sys.argv[sys.argv.index('--admission') + 1]:
        raise SystemExit('airport_feasible_campaign:missing_parent_job_admission')

import argparse
import copy
import gzip
import json
from pathlib import Path

from . import foundation_airport_campaign as legacy
from . import foundation_airport_feasible_domain as domain
from .foundation_airport_observations import Recorder, CONTRACT as OBSERVATION_CONTRACT

ROOT = legacy.ROOT
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_airport_feasible_campaign'
SCHEMA = 'g31.foundation.airport_cyclic_od_calibration.v1'
HARD_SECONDS, SOFT_SECONDS = 300, 240
SOURCE_ROOTS = (MODULE, 'scripts.experiments.g31_ics_circulation.foundation_airport_feasible_domain', *legacy.SOURCE_ROOTS)
BRANCHES = {name: {**row, 'business_contract_version': domain.VERSION} for name, row in legacy.BRANCHES.items()}
read, sha, reference, write_new, gz_new = legacy.read, legacy.sha, legacy.reference, legacy.write_new, legacy.gz_new


def require(value, reason):
    if not value:
        raise ValueError('airport_feasible_campaign:' + reason)


def source_pins():
    return {str(path): sha(path) for path in sorted(set(legacy.source_dependency_closure(roots=SOURCE_ROOTS).values()))}


def calibration_reference(path):
    """A closed calibration is a prerequisite, never an improvement witness."""
    path = Path(path).resolve()
    receipt = read(path); plan = read(path.parent / 'plan.json')
    require(receipt['schema'] == SCHEMA and plan['schema'] == SCHEMA and plan['branch'] == 'C00'
        and plan['business_contract_version'] == domain.VERSION
        and plan['protocol_input_semantic_sha256'] == domain.PROTOCOL_INPUT_SHA,
        'new_domain_C00_reference')
    require(receipt['status'] == 'requested_calibration_end_reached'
        and receipt['process']['status'] == 'exited' and receipt['process']['exitcode'] == 0
        and receipt['plan_sha256_at_launch'] == sha(path.parent / 'plan.json'), 'closed_C00_calibration_required')
    require(set(plan['source_archive']) == set(plan['source_sha256']), 'C00_archive_domain')
    for source, archived in plan['source_archive'].items():
        require(sha(path.parent / archived) == plan['source_sha256'][source], 'C00_archived_source_bytes')
    require(sha(plan['input']['path']) == plan['input']['sha256']
        and domain.digest(read(plan['input']['path'])) == domain.PROTOCOL_INPUT_SHA, 'C00_actual_input_binding')
    worker = receipt['worker_report']
    require(worker['acceptance_status'] == 'closed_run_acceptance_passed'
        and worker['acceptance'] == reference(path.parent / 'C00/acceptance.json'), 'C00_acceptance_binding')
    accepted = read(worker['acceptance']['path'])
    require(accepted['status'] == 'closed_run_acceptance_passed' and accepted['branch_keys'] == ['C00']
        and accepted['run_reference'] == reference(path.parent / 'plan.json'), 'C00_acceptance_chain')
    require(sha(worker['raw']['path']) == worker['raw']['sha256'], 'C00_raw_binding')
    raw = json.loads(gzip.decompress(Path(worker['raw']['path']).read_bytes()))
    require(raw['input_sha256'] == domain.PROTOCOL_INPUT_SHA and raw['final_physical_time'] == legacy.BOUNDARIES[-1]
        and raw['offered_count'] == 28506 and raw['warmup_native_state_sha256']
        and raw['status'] == 'requested_calibration_end_reached', 'C00_complete_window_identity')
    return {'receipt': reference(path), 'plan': reference(path.parent / 'plan.json'),
        'raw': worker['raw'], 'acceptance': worker['acceptance'],
        'warmup_native_state_sha256': raw['warmup_native_state_sha256'],
        'scope': 'prerequisite calibration only; all-job improvement remains unproven'}


def check_pins(plan):
    branch = plan['branch']
    require(plan['schema'] == SCHEMA and branch in BRANCHES and plan['branch_order'] == [branch]
        and plan['rows'] == {branch: BRANCHES[branch]} and plan['hard_process_seconds'] == HARD_SECONDS
        and plan['soft_stop_seconds'] == SOFT_SECONDS and plan['automatic_retries'] == 0
        and plan['native_branch_budget'] == 1 and plan['controller'] == legacy.CONTROLLER
        and plan['warmup_end'] == legacy.WARMUP and plan['window_boundaries'] == list(legacy.BOUNDARIES)
        and plan['physical_start'] == 0. and plan['planner_activate_at'] == 57660.
        and plan['observed_counts'] is None and plan['business_contract_version'] == domain.VERSION
        and plan['protocol_input_semantic_sha256'] == domain.PROTOCOL_INPUT_SHA
        and plan['business_semantic_sha256'] == domain.BUSINESS_SHA
        and plan['non_business_semantic_sha256'] == domain.NON_BUSINESS_SHA
        and plan['policy_observation_contract'] == OBSERVATION_CONTRACT,
        'fixed_new_business_calibration_protocol')
    require(plan['source_dependency_roots'] == list(SOURCE_ROOTS) and source_pins() == plan['source_sha256'], 'source_set_or_bytes_changed')
    require(set(plan['source_archive']) == set(plan['source_sha256']), 'source_archive_domain')
    output = Path(plan['output']).resolve()
    for source, archive in plan['source_archive'].items():
        path = (output / archive).resolve()
        require(path.is_relative_to(output / 'source') and sha(path) == plan['source_sha256'][source], 'source_archive_bytes')
    refs = [plan[key] for key in ('input', 'mapping', 'business_contract', 'business_audit', 'crosswalk', 'legacy_manifest', 'binary',
        'native_contract_reference', 'semantic_gate_reference')] + plan['runtime_references'] + plan['forecast_references']
    for item in refs:
        require(sha(item['path']) == item['sha256'], 'pinned_artifact:' + item['path'])
    require(plan['input_file_sha256'] == {branch: plan['input']['sha256']}, 'input_file_binding')
    data = read(plan['input']['path'])
    require(domain.digest(data) == domain.PROTOCOL_INPUT_SHA
        and domain.digest(data['jobs']) == domain.BUSINESS_SHA
        and domain.digest({k: v for k, v in data.items() if k != 'jobs'}) == domain.NON_BUSINESS_SHA,
        'full_registered_input_identity')
    require(read(plan['business_contract']['path']) == domain.contract(), 'business_contract_identity')
    domain.validate_mapping(read(plan['mapping']['path']))
    audit = json.loads(gzip.decompress(Path(plan['business_audit']['path']).read_bytes()))
    crosswalk = json.loads(gzip.decompress(Path(plan['crosswalk']['path']).read_bytes()))
    require(domain.digest(audit) == domain.AUDIT_SHA and domain.digest(crosswalk) == domain.CROSSWALK_SHA
        and audit['contract'] == domain.contract() and audit['new_crosswalk_sha256'] == domain.digest(crosswalk)
        and len(audit['exact_changed_jobs']) == 6673 and len(audit['whole_parent_audit']) == 360,
        'business_audit_binding')
    if branch == 'C00':
        require(plan['forecast_references'] == [] and plan['public_contexts'] == {}
            and plan['calibration_reference'] is None, 'C00_information_scope')
    else:
        require(plan['forecast_references'] and plan['public_contexts'] and plan['calibration_reference'], 'C10_resources_and_calibration')
        require(calibration_reference(plan['calibration_reference']['receipt']['path']) == plan['calibration_reference'],
            'calibration_reference_changed')


def prepare(output, *, branch='C00', checkpoint=legacy.FORECAST_DIR / 'flight_forecaster_checkpoint.json',
            flight_plan=legacy.FORECAST_DIR / 'public/static_flight_plan.json', calibration=None):
    from .original_workload import DEFAULT_MAP
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT) and output != ROOT and not output.exists(), 'fresh_workspace_output')
    require(branch in BRANCHES, 'registered_branch')
    require((branch == 'C00' and calibration is None) or (branch == 'C10' and calibration is not None), 'explicit_C10_calibration_reference')
    prerequisite = calibration_reference(calibration) if calibration is not None else None
    data, physical_manifest, crosswalk, audit = domain.build_full_input()
    contract_path = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014/native027_accepted_contract_001.json'
    semantic_path = contract_path.parent / 'native027_semantic_native_002/receipt.json'
    native_contract = read(contract_path)
    require(sha(native_contract['binary']) == native_contract['binary_sha256'], 'accepted_native_binary')
    output.mkdir(parents=True)
    write_new(output / 'inputs' / (branch + '.json'), data)
    write_new(output / 'legacy_input_manifest.json', physical_manifest)
    write_new(output / 'business_contract.json', domain.contract())
    gz_new(output / 'business_audit.json.gz', audit)
    gz_new(output / 'business_crosswalk.json.gz', crosswalk)
    write_new(output / 'airport_mapping.json', domain.static_mapping(read(DEFAULT_MAP)))
    forecast_refs, contexts, checkpoint_copy = [], {}, None
    if branch == 'C10':
        from . import foundation_flight_forecaster as forecaster
        from .foundation_flight_context import adapt_context
        model = forecaster.validate_checkpoint(read(checkpoint))
        require(model['frozen_at'] <= legacy.WARMUP and model['training_labels_closed_at'] <= legacy.WARMUP, 'model_available_before_window')
        checkpoint_copy = output / 'flight_forecaster_checkpoint.json'; checkpoint_copy.write_bytes(Path(checkpoint).read_bytes())
        public_plan = read(flight_plan)
        require(public_plan['availability_basis'] == 'static_predeclared' and public_plan['received_at'] == 0.
            and all(row['planned_injection_region'] is None for row in public_plan['entries']), 'static_public_plan_without_truth_assignment')
        for index, owner in enumerate(sorted({node['resource_owner'] for node in data['node_contracts']})):
            context = copy.deepcopy(public_plan); context['owner_scope'] = owner
            adapted = adapt_context(context, owner=owner, now=legacy.WARMUP, expected_time_basis=model['time_basis'])
            require(adapted is not None, 'valid_public_context')
            path = output / 'public' / f'owner_{index:02d}.json'; write_new(path, adapted.to_dict()); contexts[owner] = reference(path)
        forecast_refs = [reference(checkpoint), reference(flight_plan), reference(checkpoint_copy), *contexts.values()]
    pins, archive = source_pins(), {}
    for index, source in enumerate(pins):
        target = output / 'source' / f'{index:04d}.py'; target.parent.mkdir(exist_ok=True)
        target.write_bytes(Path(source).read_bytes()); archive[source] = str(target.relative_to(output))
    plan = {'schema': SCHEMA, 'status': 'prepared_not_executed', 'output': str(output), 'branch': branch,
        'rows': {branch: copy.deepcopy(BRANCHES[branch])}, 'branch_order': [branch],
        'native_branch_budget': 1, 'automatic_retries': 0, 'hard_process_seconds': HARD_SECONDS, 'soft_stop_seconds': SOFT_SECONDS,
        'physical_start': 0., 'warmup_end': legacy.WARMUP, 'window_boundaries': list(legacy.BOUNDARIES),
        'warmup_segment_seconds': 3600., 'physical_input_horizon': 86400., 'controller': copy.deepcopy(legacy.CONTROLLER),
        'source_sha256': pins, 'source_archive': archive, 'source_dependency_roots': list(SOURCE_ROOTS),
        'source_dependency_scope': 'all-AST local import closure including delayed imports and package initializers',
        'input': reference(output / 'inputs' / (branch + '.json')),
        'input_file_sha256': {branch: sha(output / 'inputs' / (branch + '.json'))},
        'business_contract_version': domain.VERSION, 'business_semantic_sha256': domain.BUSINESS_SHA,
        'non_business_semantic_sha256': domain.NON_BUSINESS_SHA, 'protocol_input_semantic_sha256': domain.PROTOCOL_INPUT_SHA,
        'legacy_protocol_input_sha256': domain.LEGACY_PROTOCOL_SHA,
        'business_contract': reference(output / 'business_contract.json'), 'business_audit': reference(output / 'business_audit.json.gz'),
        'crosswalk': reference(output / 'business_crosswalk.json.gz'), 'mapping': reference(output / 'airport_mapping.json'),
        'legacy_manifest': reference(output / 'legacy_input_manifest.json'),
        'native_contract_reference': reference(contract_path), 'semantic_gate_reference': reference(semantic_path),
        'binary': reference(native_contract['binary']), 'runtime_references': [reference(sys.executable),
            *[reference(path) for path in physical_manifest['source_sha256']]],
        'forecast_references': forecast_refs, 'public_contexts': contexts,
        'forecaster_checkpoint': reference(checkpoint_copy) if checkpoint_copy else None,
        'planner_activate_at': 57660., 'observed_counts': None, 'calibration_reference': prerequisite,
        'policy_observation_contract': copy.deepcopy(OBSERVATION_CONTRACT),
        'static_plan_owner_availability': 'explicit common pre-supplied research assumption; no real publication timing claim',
        'offered_business_count': 28506, 'inventory': 22, 'node_count': 151, 'edge_count': 227,
        'same_live_session_across_boundaries': True, 'reset_at_window_boundary': False, 'all_unfinished_preserved': True,
        'native_checkpoint_serializable_after_exit': False, 'complete_request_100ms_certified': False,
        'four_cell_comparison_completed': False, 'multistep_RL_established': False, 'strict_nonharm_certified': False,
        'old_C00_C10_repaired_or_relabelled': False,
        'scope': 'new registered full-flow OD research contract; same graph/capacity/22 initial trays; C00 calibration only before deciding C10'}
    write_new(output / 'plan.json', plan)
    check_pins(plan)
    return plan


def registered_planner(plan):
    if plan['branch'] == 'C00':
        from .analytic_control import transfer_candidates
        return transfer_candidates
    from .foundation_flight_forecaster import predict, validate_checkpoint
    model = validate_checkpoint(read(plan['forecaster_checkpoint']['path']))
    contexts = {owner: read(ref['path']) for owner, ref in plan['public_contexts'].items()}
    def forecast_at(*, now, owner):
        require(owner in contexts, 'registered_owner_context')
        return predict(contexts[owner], model, now=now, owner=owner, observed_counts=None)
    return domain.make_rule_planner(forecast_at, read(plan['mapping']['path']), activate_at=plan['planner_activate_at'])


def execute_continuous(session, data, plan, directory):
    from functools import partial
    from .foundation_airport_protocol import run_airport_protocol_control
    recorder = Recorder(directory / 'policy_observations.jsonl.gz', branch=plan['branch'], business_version=domain.VERSION)
    identity = 'airport_cyclic_recorded:' + plan['branch'] + ':' + domain.VERSION + ':' + plan['mapping']['sha256']
    if plan['forecaster_checkpoint'] is not None:
        identity += ':' + plan['forecaster_checkpoint']['sha256']
    controller = partial(run_airport_protocol_control, planner=recorder.wrap(registered_planner(plan)), planner_identity=identity)
    try:
        raw = legacy.execute_continuous(session, data, plan, directory, controller=controller)
    finally:
        recorder.close()
    observed = recorder.summary()
    write_new(directory / 'policy_observation_receipt.json', observed)
    raw.update(business_contract_version=domain.VERSION, business_semantic_sha256=domain.BUSINESS_SHA,
        non_business_semantic_sha256=domain.NON_BUSINESS_SHA, old_C00_C10_repaired_or_relabelled=False,
        policy_observations=observed)
    return raw


def worker(output, expected_sha):
    return legacy.worker(output, expected_sha, validator=check_pins, executor=execute_continuous)


def launch(output):
    return legacy.launch(output, validator=check_pins, module=MODULE, timeout=HARD_SECONDS, receipt_schema=SCHEMA)


def main():
    sys.path.insert(0, str(ROOT / 'src'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true'); modes.add_argument('--launch', action='store_true'); modes.add_argument('--worker', action='store_true')
    parser.add_argument('--admission'); parser.add_argument('--plan-sha256')
    parser.add_argument('--branch', choices=tuple(BRANCHES), default='C00')
    parser.add_argument('--calibration-reference', type=Path)
    parser.add_argument('--checkpoint', type=Path, default=legacy.FORECAST_DIR / 'flight_forecaster_checkpoint.json')
    parser.add_argument('--flight-plan', type=Path, default=legacy.FORECAST_DIR / 'public/static_flight_plan.json')
    args = parser.parse_args()
    result = (prepare(args.output, branch=args.branch, checkpoint=args.checkpoint, flight_plan=args.flight_plan,
        calibration=args.calibration_reference) if args.prepare else launch(args.output) if args.launch else worker(args.output, args.plan_sha256))
    print(json.dumps({'status': result['status'], 'output': str(args.output.resolve())}))
    if args.worker and result['status'].startswith('unknown'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
