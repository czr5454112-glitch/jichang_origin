"""Supplemental four-parent C10 -> TF-B1-60 per-bag service audit.

Default: check-only. --execute requires all 28 workflow005 DEV runs closed.
This separate report does not modify final_science's original 24 pairs or figures.
No native process, policy dispatch, raw observation, or owner ACK file is opened.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

SOURCE_SHA = '22201c59569d2c2a67460ebff7be249432e25fc6a3f42941d4d15ddac8113bef'
WORKFLOW_SHA = '1509684b0eaa8433795343d508142654f90927ef70553783c272f343205aa30d'
SHARED_SHA = '4fd82640b0701468a3016d558fe958d93548fc44e864a7ab5f92cbd6abf03aed'
PARENTS = (2201, 2202, 2203, 2204)
METHODS = ('C00', 'C10', 'TF-current', 'TF-B1-60', 'TF-B1-300', 'TF-B1-300-replan300', 'TF-predictor')
PAIR = ('C10', 'TF-B1-60')
ALLOWED_AXES = ('selector_algorithm', 'allocator')
MAX_OUTPUT_BYTES = 134217728
SUGGESTED_HARD_SECONDS = 300
RUN_FILES = ('plan.json', 'receipt.json', 'worker_report.json', 'trajectory.json.gz')

def need(ok, reason):
    if not ok:
        raise ValueError('strong_baseline_service:' + reason)

def load_shared():
    path = Path(__file__).with_name('final_science_audit_004.py')
    need(hashlib.sha256(path.read_bytes()).hexdigest() == SHARED_SHA, 'shared_driver_changed')
    spec = importlib.util.spec_from_file_location('strong_baseline_shared_science', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def collect_inputs(paths, shared):
    """Bind bytes before closure checks consume any run or physical log file."""
    refs = {}
    def add(path, expected=None):
        ref = shared.bind(path)
        need(expected is None or ref['sha256'] == expected, 'registered_binding_changed:' + ref['path'])
        need(ref['path'] not in refs or refs[ref['path']] == ref, 'input_changed_during_collection')
        refs[ref['path']] = ref
        return ref
    for path in paths:
        if not Path(path).exists():
            continue
        block = shared.bound_read(add(path))
        for plan_ref in block['task_plans']:
            plan = shared.bound_read(add(plan_ref['path'], plan_ref['sha256']))
            directory = Path(plan_ref['path']).parent
            for name in RUN_FILES:
                if (directory / name).exists():
                    add(directory / name)
            if plan['method'] in PAIR and (directory / 'terminal_evidence.json.gz').exists():
                add(directory / 'terminal_evidence.json.gz')
            # Includes physical parent input, source, binary, forecast/mapping,
            # and frozen model dependencies. No raw observation or ACK binding.
            for ref in plan.values():
                if isinstance(ref, dict) and {'path', 'sha256'} <= ref.keys():
                    add(ref['path'], ref['sha256'])
    return refs

def require_ready(rows, status):
    need(status.get('status') == 'ready' and not status.get('pending'), 'all_28_closed_required')
    need(status.get('registered_runs') == status.get('expected_runs') == 28, '28_registered_runs_required')
    need(set(rows) == {(p, m) for p in PARENTS for m in METHODS}, 'exact_28_run_roster')
    need(status.get('all_four_parents_share_one_historical_template') is True, 'same_template_required')

def validate_result(result, parent, rows):
    need((result.get('reference_method'), result.get('candidate_method')) == PAIR, 'fixed_pair_required')
    need(result['reference_task'] == rows[parent, PAIR[0]]['plan']['task_id']
         and result['candidate_task'] == rows[parent, PAIR[1]]['plan']['task_id'], 'task_identity')
    need(result['physical_contract']['parent']['parent_seed'] == parent, 'parent_identity')
    need(result.get('population') == 28506 and result.get('population_exclusions') == 0,
         'complete_28506_population')
    bags = result['per_bag']
    need(len(bags) == 28506 and len({r['business_bag_id'] for r in bags}) == 28506, 'unique_complete_per_bag_rows')
    need(result.get('cost_window') == [7200., 59400.], 'registered_cost_window')
    need(result.get('completion_times_imputed') is False
         and result.get('both_unfinished_never_declared_equal') is True, 'censoring_contract')
    direction = result['completion_direction']
    counts = direction['categories']
    need(sum(counts.values()) == direction['population'] == 28506, 'completion_denominator')
    need(direction['known_direction_harm'] == counts['exact_harmed'] + counts['reference_only_finished'], 'completion_harm_definition')
    need(result.get('strict_per_bag_nonharm_certified') is False and result.get('test_unlocked') is False,
         'no_automatic_promotion')

def size_guard(output):
    need(sum(path.stat().st_size for path in Path(output).iterdir() if path.is_file()) < MAX_OUTPUT_BYTES,
         'supplemental_evidence_budget_exceeded')

def execute(rows, status, source_ref, workflow_ref, paths, helpers, shared, input_refs, producer_refs, output):
    require_ready(rows, status)
    shared.verify_bindings(producer_refs + list(input_refs.values()), 'changed_before_execution')
    output = Path(output)
    need(not output.exists(), 'fresh_output_directory_required')
    # Verify the pair's sole allowed axes before creating an incomplete output.
    axes = {}
    for parent in PARENTS:
        left, right = (rows[parent, method]['plan'] for method in PAIR)
        axes[parent] = shared.pair_contract(left, right, ALLOWED_AXES, helpers['campaign'].comparison_contract)
    output.mkdir(parents=True)
    shared.fresh(output / 'pending.json', dict(status='in_progress', source_bundle=source_ref,
        workflow=workflow_ref, analysis_producers=producer_refs, not_a_completed_science_report=True))
    pair_refs, summaries = [], []
    for parent in PARENTS:
        print(json.dumps(dict(stage='supplemental_per_bag_pair', parent=parent, reference=PAIR[0], candidate=PAIR[1])), flush=True)
        result = helpers['service'].compare_runs(*(rows[parent, method]['directory'] for method in PAIR))
        validate_result(result, parent, rows)
        for evidence in result['evidence']:
            for ref in evidence.values():
                need(input_refs.get(str(Path(ref['path']).resolve())) == ref, 'service_consumed_unbound_input')
        result.update(parent=parent, registered_pair_axis=axes[parent],
            independent_airport_day_claim=False, supplemental_same_B1_strong_baseline=True)
        pair_refs.append(shared.fresh(output / f'P{parent}_C10_to_TF-B1-60_per_bag.json.gz', result))
        summaries.append({k: v for k, v in result.items() if k not in ('per_bag', 'physical_contract', 'evidence', 'physical_progress')})
        del result
        size_guard(output)
    need(len(pair_refs) == len(summaries) == 4 and {r['parent'] for r in summaries} == set(PARENTS), 'four_parent_pairs_required')
    aggregate = shared.aggregate_pairs(summaries)
    # Recheck original bytes, not a fresh binding taken after computation.
    shared.verify_bindings(producer_refs + [source_ref, workflow_ref] + list(input_refs.values()), 'input_or_producer_changed_during_audit')
    shared.verify_sources(source_ref)
    end_rows, end_status = shared.inspect_blocks(paths, source_ref, helpers)
    need(end_status == status and set(end_rows) == set(rows), 'closure_or_registration_changed_during_audit')
    shared.verify_bindings(pair_refs, 'generated_pair_changed')
    shared.verify_bindings(producer_refs + list(input_refs.values()), 'input_or_producer_changed_at_completion')
    report = dict(schema='g31.terminal_flow.strong_baseline_service.v1', status='complete',
        source_bundle=source_ref, workflow=workflow_ref, registered_runs=28, scientific_per_bag_pairs=4,
        reference_method=PAIR[0], candidate_method=PAIR[1], allowed_comparison_axes=ALLOWED_AXES,
        per_bag_pair_evidence=pair_refs, pair_summaries=summaries, aggregate=aggregate,
        closure_check=status, input_evidence=list(input_refs.values()), analysis_producers=producer_refs,
        producer_bound_at_entry_and_rechecked=True, evidence_bound_before_consumption=True,
        original_final_science_24_pairs_unchanged=True, original_figures_unchanged=True,
        sampling_scope='four same-template-derived DEV parents; not independent airport days',
        repeated_business_ids_counted_as_parent_bag_cases=True, native_starts=0,
        full_owner_ACK_opened=False, raw_observations_opened=False, promotion_approved=False,
        test_unlocked=False, R1_enabled=False, strict_per_bag_nonharm_certified=False)
    report_ref = shared.fresh(output / 'strong_baseline_service_report.json', report)
    size_guard(output)
    shared.verify_bindings(producer_refs + [report_ref], 'producer_or_report_changed_before_marker')
    shared.fresh(output / 'COMPLETE.json', dict(schema='g31.terminal_flow.strong_baseline_service.complete.v1',
        status='complete', final_report=report_ref, scientific_per_bag_pairs=4,
        all_28_DEV_runs_closed=True, source_bytes_checked_at_start_and_end=True,
        producer_bytes_checked_at_start_and_end=True, evidence_bytes_bound_before_consumption=True))
    print(json.dumps(dict(final_report=report_ref, scientific_pairs=4, native_starts=0)), flush=True)

def main():
    producer_entry_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest', required=True, type=Path)
    parser.add_argument('--workflow', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    shared = load_shared()
    producers = [shared.bind(__file__), shared.bind(shared.__file__)]
    need(producers[0]['sha256'] == producer_entry_sha and producers[1]['sha256'] == SHARED_SHA,
         'producer_changed_during_import')
    source_ref = shared.bind(args.source_manifest)
    need(source_ref['sha256'] == SOURCE_SHA and args.source_manifest.parent.name == 'terminal_flow_runtime_005', 'frozen_source005_required')
    need(shared.bind(args.workflow)['sha256'] == WORKFLOW_SHA and args.workflow.parent.name == 'workflow_005', 'registered_workflow005_required')
    root = shared.verify_sources(source_ref)
    paths, workflow_ref = shared.workflow_blocks(args.workflow, source_ref)
    inputs = collect_inputs(paths, shared)
    helpers = shared.load_helpers(root)  # All actor/service imports confined to frozen005.
    rows, status = shared.inspect_blocks(paths, source_ref, helpers)
    if not args.execute:
        shared.verify_bindings(producers + [source_ref, workflow_ref] + list(inputs.values()), 'changed_during_check')
        print(json.dumps(dict(status, supplemental_pairs_expected=4, science_executed=False,
            native_starts=0, analysis_producers=producers), ensure_ascii=False, indent=2))
        return
    need(args.output_dir is not None, 'execute_requires_fresh_output_dir')
    execute(rows, status, source_ref, workflow_ref, paths, helpers, shared, inputs, producers, args.output_dir)

if __name__ == '__main__':
    main()
