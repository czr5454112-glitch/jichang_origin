"""Preregister one bounded C00/C10 run on the complete fixed airport flow.

No native is loaded by preparation. The single worker starts at physical zero
and retains one session/controller through warmup and all three windows. This
calibration does not claim a four-cell experiment, learned policy, or benefit.
"""
from __future__ import annotations

import sys
if __name__ == '__main__' and '--worker' in sys.argv:
    if '--admission' not in sys.argv or sys.stdin.readline().strip() != sys.argv[sys.argv.index('--admission') + 1]:
        raise SystemExit('airport_campaign:missing_parent_job_admission')

import argparse
import ast
from collections import Counter, defaultdict
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import secrets
import time
import traceback

from . import bounded_windows_job
from .foundation_airport_flight import static_mapping, make_rule_planner

ROOT = Path(__file__).resolve().parents[3]
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_airport_campaign'
SCHEMA = 'g31.foundation.airport_calibration.v1'
PHYSICAL_INPUT_SHA = 'd9e065f51c4eb056e18fdbc7abb7dcacec938ff1e1e38010101de751ad52a30d'
WARMUP = 57600.
BOUNDARIES = (57600., 58200., 58800., 59400.)
HARD_SECONDS = 150
SOFT_SECONDS = 120
FORECAST_DIR = ROOT / 'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/B1_training_001'
BRANCHES = {'C00': {'information': 'no_plan', 'policy': 'existing_public_analytic_rule'},
            'C10': {'information': 'static_plan', 'policy': 'existing_rule_plus_idle_only_forecast_preposition'}}
CONTROLLER = {'control_period': 60., 'command_delay': 2., 'publication_delay': .5,
    'retry_period': 60., 'compact': True, 'lease_seconds': 120.,
    'predictive': True, 'routes': False, 'forecasts': True, 'prebalance': True}


def require(condition, reason):
    if not condition:
        raise ValueError('airport_campaign:' + reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def read(path):
    return json.loads(Path(path).read_bytes())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def gz_new(path, value):
    with Path(path).open('xb') as stream:
        stream.write(gzip.compress(json.dumps(value, allow_nan=False).encode(), compresslevel=1, mtime=0))


SOURCE_ROOTS = (
    MODULE, 'scripts.experiments.g31_ics_circulation.foundation_airport_flight',
    'scripts.experiments.g31_ics_circulation.foundation_airport_protocol',
    'scripts.experiments.g31_ics_circulation.bounded_windows_job',
)


def _local_module(module, root):
    relative = Path(*module.split('.'))
    for base in (root, root / 'src'):
        for path in (base / relative.with_suffix('.py'), base / relative / '__init__.py'):
            if path.is_file():
                return path.resolve()
    return None


def _import_names(module, path):
    """All syntactic imports, including function-local and TYPE_CHECKING ones.

From-import names may be symbols or child modules; nonexistent local modules
are ignored by the resolver. Package initializers are separately traversed.
"""
    package = module.split('.') if path.name == '__init__.py' else module.split('.')[:-1]
    result = set()
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                require(node.level <= len(package), 'relative_import_above_package:' + str(path))
                parts = package[:len(package) - node.level + 1]
                if node.module:
                    parts += node.module.split('.')
                base = '.'.join(parts)
            else:
                base = node.module or ''
            if base:
                result.add(base)
                result.update(base + '.' + alias.name for alias in node.names if alias.name != '*')
    return result


def source_dependency_closure(*, root=None, roots=SOURCE_ROOTS):
    """Resolve repository Python imports without importing any target module.

The binary, accepted saved gates, input data and frozen forecast files have
their own exact references. This graph excludes unrelated work in other lines.
"""
    root = ROOT if root is None else Path(root).resolve()
    pending, visited, resolved = list(roots), set(), {}
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        path = _local_module(module, root)
        if path is None:
            continue  # stdlib/third-party runtime, not an invented local source
        require(path.is_relative_to(root), 'source_dependency_escape')
        resolved[module] = path
        parts = module.split('.')
        pending.extend('.'.join(parts[:count]) for count in range(1, len(parts)))
        pending.extend(_import_names(module, path))
    require(all(module in resolved for module in roots), 'source_root_missing')
    return resolved


def source_pins():
    return {str(path): sha(path) for path in sorted(set(source_dependency_closure().values()))}


def build_full_input():
    from .original_workload import build_input, ProxyContract, json_digest
    from .run_original_protocol import add_protocol_contract
    data, manifest, crosswalk = build_input(scale=1, contract=ProxyContract(
        'nanning-on-carrier-proxy-v1-n4-s4-t2', 4, 4, 2, 1., 1., 0., 'finite_berth_waiting_research_proxy'),
        horizon=86400., max_events=100000, trace_limit=0)
    require(json_digest(data) == PHYSICAL_INPUT_SHA and len(data['jobs']) == 28506
        and len(data['trays']) == 22 and len(data['node_records']) == 151
        and len(data['edge_records']) == 227, 'unchanged_registered_complete_input')
    return add_protocol_contract(data), manifest, crosswalk


def check_pins(plan):
    branch = plan['branch']
    require(branch in BRANCHES and plan['schema'] == SCHEMA and plan['branch_order'] == [branch]
        and plan['rows'] == {branch: BRANCHES[branch]}
        and plan['hard_process_seconds'] == HARD_SECONDS and plan['soft_stop_seconds'] == SOFT_SECONDS
        and plan['automatic_retries'] == 0 and plan['native_branch_budget'] == 1
        and plan['warmup_end'] == WARMUP and plan['window_boundaries'] == list(BOUNDARIES)
        and plan['controller'] == CONTROLLER and plan['physical_input_sha256'] == PHYSICAL_INPUT_SHA,
        'fixed_calibration_protocol')
    require(source_pins() == plan['source_sha256'], 'source_set_or_bytes_changed')
    require(set(plan['source_archive']) == set(plan['source_sha256']), 'archive_domain')
    for source, archived in plan['source_archive'].items():
        require(sha(Path(plan['output']) / archived) == plan['source_sha256'][source], 'archive_bytes')
    for item in [plan['input'], plan['mapping'], plan['binary'], plan['native_contract_reference'],
                 plan['semantic_gate_reference'], *plan['runtime_references'], *plan['forecast_references']]:
        require(sha(item['path']) == item['sha256'], 'pinned_artifact:' + item['path'])
    require(plan['planner_activate_at'] == 57660. and plan['observed_counts'] is None, 'shared_warmup_and_no_truth_count_join')
    require((branch == 'C00' and plan['forecast_references'] == [] and plan['public_contexts'] == {})
        or (branch == 'C10' and bool(plan['forecast_references']) and bool(plan['public_contexts'])), 'information_variant_resources')


def prepare(output, *, branch='C00', checkpoint=FORECAST_DIR / 'flight_forecaster_checkpoint.json',
            flight_plan=FORECAST_DIR / 'public/static_flight_plan.json'):
    from .original_workload import DEFAULT_MAP, json_digest
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT) and output != ROOT and not output.exists(), 'fresh_workspace_output')
    require(branch in BRANCHES, 'registered_branch')
    data, manifest, crosswalk = build_full_input()
    contract_path = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014/native027_accepted_contract_001.json'
    semantic_path = contract_path.parent / 'native027_semantic_native_002/receipt.json'
    contract = read(contract_path)
    require(sha(contract['binary']) == contract['binary_sha256'], 'accepted_native_binary')
    output.mkdir(parents=True)
    write_new(output / 'inputs' / (branch + '.json'), data)
    write_new(output / 'physical_input_manifest.json', manifest)
    mapping = static_mapping(read(DEFAULT_MAP))
    write_new(output / 'airport_mapping.json', mapping)
    # Only this offline diagnostic knows actual whole-day parent projection.
    actual = defaultdict(set)
    for row in crosswalk:
        actual['legacy_start_' + str(row['original_start'])].add(row['projected_origin'])
    write_new(output / 'offline_actual_projection.json', {'actual_region_nodes': {k: sorted(v) for k, v in actual.items()},
        'scope': 'offline historical physical projection; not legal forecast weights or actor input',
        'actor_uses_this_artifact': False, 'crosswalk_sha256': manifest['crosswalk_sha256']})
    gz_new(output / 'business_crosswalk.json.gz', crosswalk)
    forecast_refs, public_contexts = [], {}
    checkpoint_copy = None
    if branch == 'C10':
        from . import foundation_flight_forecaster as forecaster
        from .foundation_flight_context import adapt_context
        model = forecaster.validate_checkpoint(read(checkpoint))
        require(model['frozen_at'] <= WARMUP and model['training_labels_closed_at'] <= WARMUP, 'model_available_before_window')
        checkpoint_copy = output / 'flight_forecaster_checkpoint.json'
        checkpoint_copy.write_bytes(Path(checkpoint).read_bytes())
        public_plan = read(flight_plan)
        require(public_plan['availability_basis'] == 'static_predeclared' and public_plan['received_at'] == 0., 'explicit_static_plan_assumption')
        require(all(row['planned_injection_region'] is None for row in public_plan['entries']), 'no_retrospective_flight_loader_assignment')
        # Explicitly register the same static experimental plan as pre-supplied
        # to each owner. No runtime parent labels or balanced workload join.
        for index, owner in enumerate(sorted({n['resource_owner'] for n in data['node_contracts']})):
            context = copy.deepcopy(public_plan); context['owner_scope'] = owner
            adapted = adapt_context(context, owner=owner, now=WARMUP, expected_time_basis=model['time_basis'])
            require(adapted is not None, 'valid_public_plan')
            path = output / 'public' / f'owner_{index:02d}.json'
            write_new(path, adapted.to_dict())
            public_contexts[owner] = reference(path)
        forecast_refs = [reference(checkpoint), reference(flight_plan), reference(checkpoint_copy), *public_contexts.values()]
    pins = source_pins()
    archive = {}
    for index, source in enumerate(pins):
        target = output / 'source' / f'{index:04d}.py'
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(Path(source).read_bytes())
        archive[source] = str(target.relative_to(output))
    plan = {'schema': SCHEMA, 'status': 'prepared_not_executed', 'output': str(output),
        'branch': branch, 'rows': {branch: copy.deepcopy(BRANCHES[branch])},
        'branch_order': [branch], 'native_branch_budget': 1, 'automatic_retries': 0,
        'hard_process_seconds': HARD_SECONDS, 'soft_stop_seconds': SOFT_SECONDS,
        'warmup_end': WARMUP, 'window_boundaries': list(BOUNDARIES), 'physical_start': 0.,
        'warmup_segment_seconds': 3600., 'physical_input_horizon': 86400., 'controller': copy.deepcopy(CONTROLLER),
        'source_sha256': pins, 'source_archive': archive, 'input_file_sha256': {branch: sha(output / 'inputs' / (branch + '.json'))},
        'source_dependency_scope': 'all-AST local import closure including delayed imports and package initializers',
        'source_dependency_roots': list(SOURCE_ROOTS),
        'input': reference(output / 'inputs' / (branch + '.json')), 'physical_input_sha256': PHYSICAL_INPUT_SHA,
        'protocol_input_semantic_sha256': json_digest(data), 'mapping': reference(output / 'airport_mapping.json'),
        'native_contract_reference': reference(contract_path), 'semantic_gate_reference': reference(semantic_path),
        'binary': reference(contract['binary']), 'runtime_references': [reference(sys.executable),
            *[reference(path) for path in manifest['source_sha256']]],
        'forecast_references': forecast_refs, 'public_contexts': public_contexts,
        'forecaster_checkpoint': reference(checkpoint_copy) if checkpoint_copy else None,
        'planner_activate_at': 57660., 'observed_counts': None,
        'static_plan_owner_availability': 'explicit common pre-supplied research assumption; no real publication timing claim',
        'offered_business_count': 28506, 'inventory': 22, 'node_count': 151, 'edge_count': 227,
        'same_live_session_across_boundaries': True, 'reset_at_window_boundary': False,
        'native_checkpoint_serializable_after_exit': False, 'all_unfinished_preserved': True,
        'complete_request_100ms_certified': False, 'four_cell_comparison_completed': False,
        'multistep_RL_established': False, 'strict_nonharm_certified': False,
        'scope': 'One preregistered full-flow rule branch; timeout/gridlock retained, no outcome-driven window selection. C00 calibrates; C10 requires its paired comparison.'}
    write_new(output / 'plan.json', plan)
    check_pins(plan)
    return plan


def segment_targets():
    return [0., *[float(t) for t in range(3600, int(WARMUP) + 1, 3600)], *BOUNDARIES[1:]]


def registered_controller(plan):
    from .protocol_control import run_protocol_control
    if plan['branch'] == 'C00':
        return run_protocol_control
    from .foundation_airport_protocol import run_airport_protocol_control
    from .foundation_flight_forecaster import predict, validate_checkpoint
    from functools import partial
    model = validate_checkpoint(read(plan['forecaster_checkpoint']['path']))
    contexts = {owner: read(item['path']) for owner, item in plan['public_contexts'].items()}
    def forecast_at(*, now, owner):
        require(owner in contexts, 'registered_public_owner_context')
        return predict(contexts[owner], model, now=now, owner=owner, observed_counts=None)
    planner = make_rule_planner(forecast_at, read(plan['mapping']['path']), activate_at=plan['planner_activate_at'])
    identity = 'airport_C10:' + plan['forecaster_checkpoint']['sha256'] + ':' + plan['mapping']['sha256']
    return partial(run_airport_protocol_control, planner=planner, planner_identity=identity)


def execute_continuous(session, data, plan, directory, *, controller=None, clock=time.monotonic):
    """No physical reset and no result_at repair after a truncated event tick."""
    from .original_workload import summarize_execution
    controller = registered_controller(plan) if controller is None else controller
    require(session.physical_time == 0., 'physical_zero_required')
    owners = sorted({row['resource_owner'] for row in data['node_contracts']})
    state, records, final, calls = None, [], None, []
    start, warmup_hash = clock(), None
    status = 'censored_before_requested_window_end'
    with (directory / 'progress.jsonl').open('x', encoding='utf8') as progress:
        for index, target in enumerate(segment_targets()):
            if clock() - start >= plan['soft_stop_seconds']:
                break
            before = session.physical_time
            run = controller(session, owners, horizon=target, state=state, event_budget=100000, **plan['controller'])
            state = run['controller_state']
            calls.extend(run['client_calls'])
            raw_path = directory / f'segment_{index:02d}.json.gz'
            gz_new(raw_path, run)
            current = {'index': index, 'start_at': before, 'target': target,
                'actual_clock': session.physical_time, 'status': run['status'], 'raw': reference(raw_path),
                'elapsed_wall_seconds': clock() - start}
            if run['result'] is not None:
                require(len(run['result']['jobs']) == len(data['jobs']), 'offered_denominator_lost')
                final = run['result']
                current['summary'] = summarize_execution(data, final)
            records.append(current)
            progress.write(json.dumps(current, allow_nan=False) + '\n'); progress.flush()
            if run['status'] != 'reached':
                status = 'native_event_budget_censored'; break
            if target == WARMUP:
                warmup_hash = session.offline_state_sha256()
                write_new(directory / 'warmup_boundary.json', {'physical_time': target,
                    'native_state_sha256': warmup_hash, 'raw': reference(raw_path),
                    'continuation': 'same live native session and controller; no reset'})
            if target == BOUNDARIES[-1]:
                status = 'requested_calibration_end_reached'
    # Offline export only after all online decisions; delivered ACKs are not
    # silently promoted from pending submission replies.
    from .run_original_protocol import request_ledger
    ack_views = {owner: session.observe_protocol(owner) for owner in owners}
    ledger = request_ledger(calls, ack_views)
    gz_new(directory / 'client_calls.json.gz', calls)
    gz_new(directory / 'delivered_ack_views.json.gz', ack_views)
    gz_new(directory / 'request_ledger.json.gz', ledger)
    return {'status': status, 'segments': records, 'final_result': final,
        'input_sha256': plan['protocol_input_semantic_sha256'], 'warmup_native_state_sha256': warmup_hash,
        'final_physical_time': session.physical_time, 'offered_count': len(data['jobs']),
        'session_instance_count': 1, 'physical_reset_count': 0, 'request_ledger_summary': {
            k: v for k, v in ledger.items() if k not in ('requests', 'delivered_transfer_acks', 'delivered_command_acks')},
        'strict_nonharm_certified': False, 'complete_request_100ms_certified': False,
        'continuation_after_process_exit': 'not_available; a future experiment must preregister a new common warmup'}


def compare_all_jobs(baseline, candidate):
    """Offline exact terminal comparison; any unfinished item stays unknown."""
    require(baseline['input_sha256'] == candidate['input_sha256'], 'different_external_flow')
    require(baseline['warmup_native_state_sha256'] is not None
        and baseline['warmup_native_state_sha256'] == candidate['warmup_native_state_sha256'], 'different_common_warmup')
    require(baseline['final_physical_time'] == candidate['final_physical_time'], 'different_comparison_clock')
    require(all(run['status'] == 'requested_calibration_end_reached'
        and run['final_result'] is not None
        and run['final_result']['physical_clock'] == run['final_physical_time']
        for run in (baseline, candidate)), 'complete_comparable_window_boundaries')
    jobs = [{row['business_bag_id']: row for row in run['final_result']['jobs']} for run in (baseline, candidate)]
    require(set(jobs[0]) == set(jobs[1]) and len(jobs[0]) == baseline['offered_count'] == candidate['offered_count'], 'complete_business_domain')
    rows = []
    for identity in sorted(jobs[0]):
        old, new = jobs[0][identity], jobs[1][identity]
        a, b = old['completed_at'], new['completed_at']
        complete = (old['status'] == new['status'] == 'completed'
            and all(type(v) in (float, int) and math.isfinite(v) and v >= 0 for v in (a, b)))
        rows.append({'business_bag_id': identity, 'baseline_status': old['status'], 'candidate_status': new['status'],
            'baseline_completed_at': a, 'candidate_completed_at': b, 'delta_s': b-a if complete else None,
            'comparison': 'unknown_incomplete' if not complete else 'harmed' if b > a else 'improved' if b < a else 'equal'})
    counts = dict(Counter(row['comparison'] for row in rows))
    protected = not counts.get('harmed') and not counts.get('unknown_incomplete')
    return {'all_jobs': rows, 'counts': counts, 'comparison_tolerance_s': 0.,
        'strict_all_job_nonharm': protected, 'strict_improvement': protected and bool(counts.get('improved')),
        'online_guard_had_reference_completion_access': False, 'uncompleted_jobs_excluded': 0}


def worker(output, expected_sha, *, validator=check_pins, executor=execute_continuous):
    from . import native027_run_acceptance as acceptance
    from .native_host import load_native
    output = Path(output).resolve()
    plan, accepted = read(output / 'plan.json'), None
    branch = plan['branch']; directory = output / branch
    report = {'status': 'unknown_failed', 'native_session_attempted': False}
    try:
        require(sha(output / 'plan.json') == expected_sha, 'plan_binding')
        validator(plan)
        campaign_ref = reference(output / 'plan.json')
        accepted = acceptance.open_run(plan['native_contract_reference'], plan['semantic_gate_reference'], campaign_ref)
        accepted.enter_branch(branch, campaign_ref)
        data = read(plan['input']['path'])
        session = load_native(plan['binary']['path']).NativeSession(data)
        report['native_session_attempted'] = True
        raw = executor(session, data, plan, directory)
        gz_new(directory / 'raw.json.gz', raw)
        report.update(status=raw['status'], raw=reference(directory / 'raw.json.gz'),
            final_physical_time=raw['final_physical_time'], warmup_reached=raw['warmup_native_state_sha256'] is not None)
        accepted.finish_branch(branch)
    except Exception:
        report['exception'] = traceback.format_exc()
    finally:
        if accepted is not None:
            closed = accepted.close()
            write_new(directory / 'acceptance.json', closed)
            report['acceptance_status'] = closed['status']
            report['acceptance'] = reference(directory / 'acceptance.json')
            if closed['status'] != 'closed_run_acceptance_passed':
                report['status'] = 'unknown_invalidated_acceptance'
        try:
            validator(plan)
            require(sha(output / 'plan.json') == expected_sha, 'exit_plan_binding')
        except Exception:
            report.update(status='unknown_changed_pins', pin_exception=traceback.format_exc())
        write_new(directory / 'worker_report.json', report)
    return report


def launch(output, *, validator=check_pins, module=MODULE, timeout=HARD_SECONDS, receipt_schema=SCHEMA):
    output = Path(output).resolve(); plan = read(output / 'plan.json')
    validator(plan)
    plan_sha = sha(output / 'plan.json')
    write_new(output / 'launch.json', {'plan': reference(output / 'plan.json'), 'automatic_retries': 0})
    directory = output / plan['branch']; directory.mkdir(exist_ok=False)
    admission = secrets.token_hex(24)
    with (directory / 'stdout.log').open('x') as stdout, (directory / 'stderr.log').open('x') as stderr:
        process = bounded_windows_job.run([sys.executable, '-m', module, '--worker', '--output', str(output),
            '--plan-sha256', plan_sha, '--admission', admission],
            timeout=timeout, stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
    child = read(directory / 'worker_report.json') if (directory / 'worker_report.json').is_file() else None
    status = 'unknown_hard_timeout_or_incomplete'
    if process['status'] == 'exited' and process['exitcode'] == 0 and child is not None:
        validator(plan)
        require(sha(output / 'plan.json') == plan_sha, 'plan_changed_during_launch')
        if child.get('acceptance_status') == 'closed_run_acceptance_passed' and child.get('raw'):
            require(child['acceptance'] == reference(directory / 'acceptance.json'), 'acceptance_artifact_binding')
            accepted = read(directory / 'acceptance.json')
            require(accepted['status'] == 'closed_run_acceptance_passed' and accepted['branch_keys'] == [plan['branch']]
                and accepted['run_reference'] == reference(output / 'plan.json'), 'closed_acceptance_chain')
            require(sha(child['raw']['path']) == child['raw']['sha256'], 'raw_binding')
            raw = json.loads(gzip.decompress(Path(child['raw']['path']).read_bytes()))
            require(raw['status'] == child['status'] and raw['offered_count'] == 28506
                and raw['input_sha256'] == plan['protocol_input_semantic_sha256'], 'raw_chain')
            require(raw['session_instance_count'] == 1 and raw['physical_reset_count'] == 0, 'continuous_session_chain')
            require([row['target'] for row in raw['segments']] == segment_targets()[:len(raw['segments'])], 'registered_segment_prefix')
            for row in raw['segments']:
                require(sha(row['raw']['path']) == row['raw']['sha256'], 'segment_artifact_binding')
            if child['status'] == 'requested_calibration_end_reached':
                require(raw['final_physical_time'] == BOUNDARIES[-1] and raw['warmup_native_state_sha256']
                    and len(raw['segments']) == len(segment_targets())
                    and len(raw['final_result']['jobs']) == 28506, 'requested_window_completion')
            status = child['status']
    receipt = {'schema': receipt_schema, 'status': status, 'process': process, 'worker_report': child,
        'automatic_retries': 0, 'native_branch_count': 1, 'plan_sha256_at_launch': plan_sha,
        'full_1x_completion_established': False,
        'four_cell_comparison_completed': False, 'complete_request_100ms_certified': False}
    write_new(output / 'receipt.json', receipt)
    return receipt


def main():
    # Standalone worker and preparation use the same local package source.
    sys.path.insert(0, str(ROOT / 'src'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true'); mode.add_argument('--launch', action='store_true')
    mode.add_argument('--worker', action='store_true')
    parser.add_argument('--admission'); parser.add_argument('--plan-sha256')
    parser.add_argument('--branch', choices=tuple(BRANCHES), default='C00')
    parser.add_argument('--checkpoint', type=Path, default=FORECAST_DIR / 'flight_forecaster_checkpoint.json')
    parser.add_argument('--flight-plan', type=Path, default=FORECAST_DIR / 'public/static_flight_plan.json')
    args = parser.parse_args()
    result = (prepare(args.output, branch=args.branch, checkpoint=args.checkpoint, flight_plan=args.flight_plan)
        if args.prepare else launch(args.output) if args.launch else worker(args.output, args.plan_sha256))
    print(json.dumps({'status': result['status'], 'output': str(args.output.resolve())}))
    if args.worker and result['status'].startswith('unknown'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
