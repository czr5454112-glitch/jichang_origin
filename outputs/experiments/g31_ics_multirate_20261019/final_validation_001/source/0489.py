"""Unexecuted independent arithmetic/readback path; no gzip or policy imports.

The producer's author wrote this second implementation. It is not a third-party
audit and does not repeat endpoint/physical validation. Those claims remain
bound to the separate root review. Run only after source review/authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = ROOT / 'outputs/sicc1'
ACTUAL = ROOT / 'outputs/sicm1'
CODE = ROOT / 'scripts/experiments/g31_ics_circulation'
PYTHON = Path('C:/PROGRAMING/python3.11.9/python.exe')
MODULE = 'scripts.experiments.g31_ics_circulation.analyze_static_inventory_C18_cost'
ANALYSIS_SHA = 'c103c50c654b70aaf3e7dbd53b81961a066ad4acd6f03c5a242db6970fde3ec4'
OLD = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014/single_owned_C18_cost_analysis_002/report.json'
INPUTS = {
    'campaign.json': '8aa7f63c50310532fa97b0b6251ec118aeae247ff6b072ddbc73edb7f9d3018e',
    'verification.json': 'd6bbe42acb7597d58298d9fc79da2730bfcfe237f3baa877bd1aee4ce0111c3c',
    'receipt.json': '2e831eb1e5f3f5845c1be823f8f88ba7b32e959943204e00a9043d431fd4d84f',
    'actual_external_application_wall.json': 'f33d1debdde90b47c59f6db13b1c432bb571546a37d499aca2fe46895333298a',
    'branch_ledger.json': '32b657aff86cf813c9ab22d3c6e8991c2c94877ef78fdac50caa4b422412e544',
    'static_inventory_lifetime.json': '7e515d40de80e7c942fa5b018d22f93cc9d8d0b102484999756dbef8d5627050',
    'C_provider_lifetime.json': '91080a901fc81d87c53b0501dcdb817eb1d342760a52c11caf5ff310a65fa281',
    'predictor_lifetime.json': '2b5937732789d617997d5e5bea6f853a9bbed69a93c942ab5aeec0d3907f8563',
    'actual_scalar_summary_001.json': 'c79fa1fc427b92a0e4b42d955f7c414b3cca59f97abbd6d5c4d8bb6abb9b0984',
}
FIXED = {
    PYTHON: '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec',
    CODE / '__init__.py': '495b29212f548915ec02a3c29999151b9ba4a24e455fc8df58fca68473e23f38',
    CODE / 'bounded_windows_job.py': '798ae87c19d5fa61569b1c9301cebe7ef6a5885302f32f42380cf53fd6363cde',
    CODE / 'analyze_static_inventory_C18_cost.py': ANALYSIS_SHA,
    CODE / 'analyze_single_owned_C18_cost_v2.py': '1219b5e961fae554683f921429ea6c00be99f949aa18c19099fb98e989cde987',
    OLD: 'a5ac730be202fd8b3452bfd5935965d967d1d034f9ad15b400896bcf83a0c7ad',
    ACTUAL / 'root_saved_review_001.json': '2998f1def4ecb95de857cf7ebc3d0267e5223abd4d1ca2a649879b5dd0f295e5',
    ROOT / 'outputs/invoke_sicc1.ps1': '855c5c99c718f558faf46bea9fa59aaae51c02e302087304a07a9b44ecb635bd',
    **{ACTUAL / name: digest for name, digest in INPUTS.items()},
}
ARTIFACTS = {
    HERE / 'report.json': '5164f3aca2ad888bcc27e1527c204c791d74db38871115e1ac6c323649524229',
    HERE / 'execution.json': '37f90fd6be216b38853cc0ed55572dff240cd8381201ae97bc3eede19f197f24',
    HERE / 'external_application_wall.json': 'ffca8b769ccfd3d92fbe35a7d10481f001e356d5904a9952d1704969a102f1be',
}
PHASES = ('admission_through_A_collection', 'collection_through_final_check',
    'postcheck_through_last_event', 'last_event_to_finalization',
    'complete_evidence_build_through_first_encode', 'strict_roundtrip_hash_ledger_return_tail')
KNOWN = ('recorded_native_advance_with_response_copy',
    'original_refresh_with_trace_and_queries', 'RPC_attempt_with_validation')
REFINED = (*KNOWN, 'constructor_outside_other_recorded_envelopes',
    'unclassified_prefinalization_after_constructor', 'complete_finalization')


def require(condition, reason):
    if not condition:
        raise ValueError('sicc1_readback:' + reason)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exact(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return list(a) == list(b) and all(exact(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    if type(a) is float:
        return math.isfinite(a) and math.isfinite(b) and a.hex() == b.hex()
    return a == b


def integer(value):
    require(type(value) is int and value >= 0, 'nonnegative_exact_integer')
    return value


def nanoseconds(value):
    require(type(value) is float and math.isfinite(value) and value >= 0, 'milliseconds_type')
    result = round(value * 1_000_000)
    require(result / 1_000_000 == value, 'milliseconds_exact_integer_projection')
    return result


def stats(values):
    return {'count': len(values), 'sum': sum(values), 'median': statistics.median(values),
        'min': min(values), 'max': max(values)}


def verify():
    begin = time.perf_counter_ns()
    pinned = {**FIXED, **ARTIFACTS}
    entry = {str(path): digest(path) for path in pinned}
    require(entry == {str(path): sha for path, sha in pinned.items()}, 'fixed_entry_pins')
    own = {'path': str(Path(__file__).resolve()), 'sha256': digest(__file__)}
    read = lambda path: json.loads(Path(path).read_bytes())
    report, execution, outer = (read(HERE / name) for name in
        ('report.json', 'execution.json', 'external_application_wall.json'))
    source = {name: read(ACTUAL / name) for name in INPUTS}
    old = read(OLD)
    require(report['status'] == 'saved18_integer_partition_complete', 'report_status')
    expected = {str(path): sha for path, sha in FIXED.items()}
    require(outer['fixed_pins'] == outer['source_entry'] == outer['source_exit'] == expected,
        'complete_external_pin_domain')
    require(outer['source_changed'] == outer['missing_outputs'] == []
        and outer['status'] == 'saved18_analysis_completed'
        and type(outer['exitcode']) is int and outer['exitcode'] == outer['wrapper_exitcode'] == 0,
        'external_terminal')
    require(outer['command'] == [str(PYTHON), '-m', MODULE]
        and outer['cwd'] == str(ROOT) and outer['output_directory'] == str(HERE)
        and outer['source_directory'] == str(ACTUAL) and outer['automatic_retries'] == 0
        and outer['shared_seconds'] == 120 and outer['python_launch_attempted'] is True,
        'external_command_scope')
    require(outer['environment'] == {'PYTHONPATH': 'src;.;tests',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONIOENCODING': 'utf-8'}, 'external_environment')
    absent = [ROOT / 'scripts/__init__.py', ROOT / 'scripts/experiments/__init__.py']
    require(outer['absent_namespace_files'] == list(map(str, absent))
        and all(not p.exists() for p in absent), 'namespace_boundary')
    for ticks, freq, seconds in (('elapsed_ticks', 'stopwatch_frequency', 'external_application_seconds'),
            ('wrapper_through_preexport_ticks', 'wrapper_stopwatch_frequency', 'wrapper_through_preexport_seconds')):
        count, frequency = integer(outer[ticks]), integer(outer[freq])
        require(frequency > 0 and count <= 120 * frequency
            and type(outer[seconds]) is float and outer[seconds] == count / frequency, 'typed_external_clock')
    require(execution['status'] == 'passed' and execution['limit_seconds'] == 120
        and execution['command'] == [str(PYTHON), '-m', MODULE, '--worker', '--admission', ANALYSIS_SHA]
        and 0 <= execution['before_final_export_seconds'] < 120, 'owned_admission_budget')
    process = execution['process']
    require(exact(process, outer['owned_process']) and process['status'] == 'exited'
        and type(process['exitcode']) is int and process['exitcode'] == 0
        and process['windows_job_kill_on_close'] is True
        and process['child_released_only_after_job_assignment'] is True
        and 0 <= process['wall_seconds'] <= process['hard_timeout_seconds'] <= 120,
        'owned_terminal')
    require(outer['actual_rows'] == 18 and outer['execution_status'] == 'passed'
        and outer['report_status'] == report['status'], 'outer_summary')
    output_paths = {name: HERE / name for name in
        ('report.json', 'execution.json', 'worker.stdout.log', 'worker.stderr.log')}
    output_paths.update({name: ROOT / ('outputs/sicc1.' + name) for name in ('outer.stdout.log', 'outer.stderr.log')})
    require(set(outer['outputs']) == set(output_paths), 'all_output_domain')
    for name, path in output_paths.items():
        require(outer['outputs'][name] == {'path': str(path), 'sha256': digest(path)}, 'output_binding:' + name)
    require(execution['report'] == outer['outputs']['report.json']
        and execution['reader'] == report['reader'] == {'path': str(CODE / 'analyze_static_inventory_C18_cost.py'), 'sha256': ANALYSIS_SHA},
        'report_execution_reader')
    require(report['inputs'] == {name: {'path': str(ACTUAL / name), 'sha256': sha} for name, sha in INPUTS.items()}
        and report['old_observational_report'] == {'path': str(OLD), 'sha256': FIXED[OLD]}
        and report['old_analyzer'] == {'path': str(CODE / 'analyze_single_owned_C18_cost_v2.py'),
            'sha256': FIXED[CODE / 'analyze_single_owned_C18_cost_v2.py']}, 'report_source_binding')
    order = source['campaign.json']['row_order']
    rows, checked, ledger = report['rows'], source['verification.json']['rows'], source['branch_ledger.json']
    require(len(order) == len(set(order)) == 18 and list(rows) == order
        and set(order) == set(checked) == set(ledger) == set(report['raw_inputs_read_once']) == set(old['rows']), 'full18_domain')
    require(source['verification.json']['status'] == 'passed_saved_with_complete_unknown_denominator'
        and source['verification.json']['branches'] == 18 and source['receipt.json']['source_changed'] == [], 'original_saved_status')
    constructors = source['static_inventory_lifetime.json']['constructors']
    require(len(constructors) == 18, 'constructor18')
    for ordinal, key in enumerate(order):
        row, constructor = rows[key], constructors[ordinal]
        require(exact(row['root'], checked[key]['root']), 'original_root:' + key)
        start, end = integer(row['root_started_ns']), integer(row['outside_return_ns'])
        parts, values = row['warm_partition_ns'], row['refined_exclusive_ns']
        require(tuple(parts) == PHASES and tuple(values) == REFINED, 'integer_partition_keys')
        require(sum(map(integer, parts.values())) == sum(map(integer, values.values())) == end - start,
            'two_complete_integer_partitions:' + key)
        require(row['root']['warm_ms'] == (end - start) / 1e6
            and exact(row['warm_partition_ms'], {k: v / 1e6 for k, v in parts.items()})
            and exact(row['refined_exclusive_ms'], {k: v / 1e6 for k, v in values.items()}), 'integer_ms_projections')
        final = start + sum(parts[k] for k in PHASES[:4])
        require(values['complete_finalization'] == end - final, 'finalization_partition')
        ctor = row['constructor']
        a, b = integer(ctor['started_ns']), integer(ctor['finished_ns'])
        require(start <= a <= b <= final <= end and ctor['ordinal'] == ordinal
            and constructor['ordinal'] == ordinal and constructor['started_ns'] == a
            and constructor['finished_ns'] == b and constructor['status'] == 'constructor_returned'
            and constructor['error_type'] is None and constructor['root']['started_ns'] == start
            and constructor['root']['deadline_ns'] == start + 100_000_000
            and constructor['root']['cutoff_ns'] == start + 60_000_000, 'constructor_identity_clock')
        fragments, overlap = ctor['exclusive_fragments'], ctor['overlap_ns_by_original_category']
        require(tuple(overlap) == KNOWN, 'constructor_overlap_domain')
        previous, exclusive = a, 0
        for left, right in fragments:
            require(previous <= integer(left) <= integer(right) <= b, 'exclusive_fragment_order')
            exclusive += right - left
            previous = right
        require(exclusive == integer(ctor['exclusive_ns']) == values[REFINED[3]]
            and exclusive + sum(map(integer, overlap.values())) == b - a == ctor['nested_full_call_ns']
            and ctor['root_minus_full_constructor_ns_diagnostic'] == end - start - (b - a), 'constructor_conservation')
        require(all(overlap[k] <= values[k] for k in KNOWN), 'overlap_known_bound')
        original = {k: values[k] / 1e6 for k in KNOWN}
        original['unclassified_prefinalization'] = (values[REFINED[3]] + values[REFINED[4]]) / 1e6
        original['complete_finalization'] = values[REFINED[5]] / 1e6
        require(exact(row['exclusive_known_and_residual_ms'], original), 'residual_debit_only')
        query = nanoseconds(row['nested_query_ms'])
        require(query <= values[KNOWN[1]] and row['refresh_excluding_query_envelope_ms'] == (values[KNOWN[1]] - query) / 1e6,
            'query_is_nested_not_added')
        coverage = row['phase_clock_coverage_ms']
        require(tuple(coverage) == PHASES and all(tuple(coverage[k]) == KNOWN for k in PHASES), 'coverage_domain')
        require(all(sum(nanoseconds(coverage[p][k]) for p in PHASES) == values[k] for k in KNOWN)
            and all(sum(nanoseconds(v) for v in coverage[p].values()) <= parts[p] for p in PHASES), 'coverage_conservation')
        require(row['prior_run_observation'] == {
            'same_choice_label': row['choice'] == old['rows'][key]['choice'],
            'prior_warm_ms': old['rows'][key]['root']['warm_ms'],
            'prior_original_partition_ms': old['rows'][key]['warm_partition_ms'],
            'prior_constructor_wall_ms': None, 'constructor_savings_attribution': 'unknown; old run has no constructor clock'}, 'old_observation_only')
        raw = report['raw_inputs_read_once'][key]
        require({k: raw[k] for k in ('path', 'sha256')} == ledger[key]['raw']
            and Path(raw['path']).is_relative_to(ACTUAL) and Path(raw['path']).suffix == '.gz'
            and integer(raw['compressed_bytes']) > 0 and integer(raw['decoded_bytes']) > 0, 'raw_reference_only_not_read')
    closed = [r for r in rows.values() if r['root']['closed'] is True]
    unknown = [r for r in rows.values() if r['root']['closed'] is False]
    require(len(closed) == 16 and len(unknown) == 2 and all(r['root']['observed_within_100ms'] is False
        and r['root']['complete_100ms_certified'] is False for r in rows.values()), '16closed2unknown0under100')
    summaries = {}
    for name, group in (('all18', list(rows.values())), ('closed16', closed), ('unknown2', unknown)):
        summaries[name] = {'warm_ms': stats([r['root']['warm_ms'] for r in group]),
            'refined_exclusive_ms': {k: stats([r['refined_exclusive_ms'][k] for r in group]) for k in REFINED},
            'nested_constructor_ms': stats([r['constructor']['nested_full_call_ns'] / 1e6 for r in group]),
            'warm_adjacent_partitions_ms': {k: stats([r['warm_partition_ms'][k] for r in group]) for k in PHASES}}
    require(exact(summaries, report['summaries']), 'all_saved_statistics_exact')
    cold = source['verification.json']
    require(exact(report['cold'], {'C_provider': cold['C_provider_lifetime'],
        'static_binding_ms_nested': cold['static_inventory_lifetime']['cold_binding_ms'],
        'RPC_startup_ms': cold['predictor_startup_ms'], 'RPC_cleanup_ms': cold['predictor_close_with_cleanup_ms']}), 'cold_preserved')
    exit_pins = {str(path): digest(path) for path in pinned}
    require(entry == exit_pins and digest(__file__) == own['sha256'], 'entry_exit_unchanged')
    totals = {k: sum(r['refined_exclusive_ns'][k] for r in closed) for k in REFINED}
    denominator = sum(totals.values())
    return {'schema': 'g31.sicc1.saved_readback.v1', 'status': 'passed_saved_report_arithmetic_and_pins',
        'reader': own, 'source_entry': entry, 'source_exit': exit_pins, 'source_changed': [],
        'rows': 18, 'closed': 16, 'unknown': 2, 'observed_under100': 0,
        'closed_integer_total_ns': denominator, 'closed_exclusive_ns': totals,
        'closed_exclusive_percent': {k: v * 100 / denominator for k, v in totals.items()},
        'closed_warm_ms': summaries['closed16']['warm_ms'],
        'analysis_external_seconds': outer['external_application_seconds'],
        'analysis_owned_seconds': process['wall_seconds'],
        'elapsed_before_export_ns': time.perf_counter_ns() - begin,
        'gzip_reads': 0, 'new_native_model_C_calls': 0, 'new_performance_runs': 0,
        'limits': ['Second arithmetic implementation, same author; not third-party independence.',
            'Raw references only; original gzip/endpoint/physical checks are not rerun.',
            'Root saved review remains separately pinned. No old constructor attribution.',
            'Function envelopes are wall, not CPU; event gaps are not function costs.',
            'Medians and nested categories must not be added; unknown roots stay unknown.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'new_output_required')
    result = verify()
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    print(json.dumps({'path': str(args.output), 'sha256': digest(args.output), 'status': result['status']}))


if __name__ == '__main__':
    main()
