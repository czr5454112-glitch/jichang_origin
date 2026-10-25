"""Completed023 same-binary1x pair: bounded small summaries only, no native."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import summary_base as base

HERE = Path(__file__).resolve().parent
C = HERE.parent
FLAG = 'enable_source_attempt_edf'
SOURCE = 'e832bc62401e8612c14285a905476e531988a88c1967df239c23295babb68d0d'
BASE_SHA = '9952659ac3219cea8491b86738facf024bc32e7f87e0e4e883ddc24566e9a5d2'
PLAN_SHA = 'e2c10c168ece61a15e8ec012fd6046a28ac44db63b5b12a8ea92e41c32606adb'
SNAPSHOT_SHA = 'd01bb190cc24e1fd6bf6790d8e7efbb13bae8abe8c69e10100600c7c38dad7a4'
CANONICAL = '3f2cc8d8e5e2934e2568b299d2d3321eec07f1f47e5fa0750537993eaee1340d'
PROFILE = '9b1a78344ec89aaac377feb05afccd48d9b957174286b29eedfe57a73a93c426'
base.SMALL_NAMES.update({'PREDECLARED_COMPARISON_PLAN_002.json', 'FROZEN_BINDING_001.json',
    'SOURCE_FREEZE_023_001.json', 'physical_contract_original_window.json', 'controls_off_original_window.json',
    'controls_original_window.json', 'snapshot_006.json'})


def require(value, message):
    if not value:
        raise ValueError(message)


def read_bound(reader, path, sha):
    value = reader.read(path)
    require(value is not None and reader.evidence[str(Path(path).resolve())]['sha256'] == sha, 'pinned evidence changed: ' + str(path))
    return value


def check_controls(off, on, *, effective=True):
    require(type(off.get(FLAG)) is bool and off[FLAG] is False and type(on.get(FLAG)) is bool and on[FLAG] is True, 'wrong EDF switch types/direction')
    require(base.different_control_keys(off, on) == {FLAG}, 'controls differ beyond sole EDF flag')
    require(off.get('end_time') == 98259, 'must use actual1x original window')
    if effective:
        require(off.get('source_fifo_order') == 'canonical' and off.get('source_fifo') is True
                and off.get('enable_ebs_predecessor_gate') is True, 'source/EBS policy changed')
    return {'passed': True, 'only_difference': FLAG, 'effective_source_policy_checked': effective}


def check_counters(native, enabled):
    if not enabled:
        require('source_attempt_edf' not in native, 'off run unexpectedly exports enabled EDF telemetry')
        return {'passed': True, 'status': 'disabled_fields_absent'}
    edf = native.get('source_attempt_edf')
    require(isinstance(edf, dict), 'missing EDF counters')
    for key in ('valid_source_attempts', 'already_overdue_valid_attempts'):
        require(type(edf.get(key)) is int and edf[key] >= 0, 'invalid EDF integer count: ' + key)
    require(type(native.get('planning_attempts')) is int and native['planning_attempts'] >= 0, 'invalid planning_attempts')
    require(edf['valid_source_attempts'] == native['planning_attempts'], 'valid EDF attempts differ from planning attempts')
    require(edf['already_overdue_valid_attempts'] <= edf['valid_source_attempts'], 'overdue attempts exceed valid attempts')
    require(isinstance(edf.get('count_scope'), str) and edf['count_scope'], 'missing EDF count scope')
    return {'passed': True, 'counters': edf, 'boundary': 'Counts repeated valid source attempts after guards, not distinct bags, competition victories, or proof that a request ordering changed.'}


def require_full_row(row):
    require(row.get('status') == 'complete' and row.get('usable_reported_result') is True and row.get('all_five_passed') is True, 'pair arm not complete/five-gate-passed')
    metrics = row['metrics']
    require(metrics['business_denominator'] == metrics['completed_businesses'] == 28506
            and metrics['segment_denominator'] == metrics['completed_segments'] == 43603, 'pair not full1x population')
    require(metrics['full_population_available'] is True and metrics['user_tht']['count'] == 28506, 'full-pop primary unavailable')
    for name in ('user_tht', 'network_elapsed', 'planning_retry_wait', 'preplanning', 'canonical_elapsed'):
        require(metrics[name]['count'] == 28506 and all(type(metrics[name][key]) in (int, float)
                and math.isfinite(metrics[name][key]) for key in ('mean', 'p95', 'p99', 'max')), 'incomplete/nonfinite full-pop metric: ' + name)
    for name in ('STD', 'STD_minus_2700'):
        item = metrics[name]
        require(item['status'] == 'available' and item['denominator'] == 28506
                and type(item['count']) is int and 0 <= item['count'] <= 28506, 'invalid deadline population')


def derived_ready(tht, full):
    n = tht.get('business_denominator')
    a = base.get(tht, 'user_tht', 'full_population')
    b = base.get(tht, 'secondary', 'business_sum_activation_to_first_planning', 'full_population')
    valid = full and tht.get('passed') is True and tht.get('user_tht_full_population_available') is True
    valid = valid and n == tht.get('completed_businesses') == 28506 and isinstance(a, dict) and isinstance(b, dict)
    valid = valid and a.get('count') == b.get('count') == n
    if valid:
        valid = all(type(x.get('sum')) in (int, float) and math.isfinite(x['sum'])
                    and type(x.get('mean')) in (int, float) and math.isfinite(x['mean'])
                    and abs(x['sum'] - n*x['mean']) <= 1e-4*n for x in (a, b))
    return {'status': 'derived_same_full_population_no_new_bag_scan' if valid else 'unavailable',
            'count': n if valid else None, 'mean': (a['sum'] + b['sum']) / n if valid else None,
            'sum': a['sum'] + b['sum'] if valid else None, 'p95': None, 'p99': None, 'max': None,
            'boundary': 'Native finish-minus-activation mean is primaryTHT+activation-to-first under unchanged activation semantics. This is a sum identity, not a new per-bag common-G/causal-ready validation; component quantiles cannot be added.'}


def verify_binding(binding):
    require(binding.get('schema') == 'g31.candidate023.comparison_binding.v1' and binding.get('passed') is True
            and binding.get('build_and_micro_passed') is True, 'final build binding required')
    require(binding.get('source_sha256') == SOURCE, 'different source from reviewed023')
    sha = binding.get('binary_sha256')
    require(isinstance(sha, str) and len(sha) == 64 and all(c in '0123456789abcdef' for c in sha), 'binary freeze hash missing')
    require(binding.get('parent_comparison_plan_sha256') == PLAN_SHA, 'different paired plan')


def run(off_path, on_path, binding_path):
    require(hashlib.sha256((HERE / 'summary_base.py').read_bytes()).hexdigest() == BASE_SHA, 'frozen summary helper changed')
    reader = base.SmallReader()
    plan = read_bound(reader, HERE / 'PREDECLARED_COMPARISON_PLAN_002.json', PLAN_SHA)
    binding = reader.read(binding_path)
    verify_binding(binding)
    freeze = read_bound(reader, binding['freeze']['path'], binding['freeze']['sha256'])
    require(freeze.get('source_sha256', base.get(freeze, 'source', 'sha256')) == SOURCE, 'freeze source mismatch')
    binaries = freeze.get('binary')
    require(isinstance(binaries, dict) and (binding['binary_sha256'] in binaries.values()
            or binaries.get('sha256') == binding['binary_sha256']), 'freeze binary mismatch')
    contract = read_bound(reader, binding['contract']['path'], binding['contract']['sha256'])
    controls = {arm: read_bound(reader, binding['controls'][arm]['path'], binding['controls'][arm]['sha256']) for arm in ('off', 'on')}
    require([binding['controls'][arm] for arm in ('off', 'on')] == [row['controls'] for row in plan['execution_order'][:2]], 'controls differ from predeclared pair')
    raw_controls = check_controls(controls['off'], controls['on'], effective=False)
    # Do not open partial output files from either child.
    manifests = [reader.read(Path(path) / 'manifest.json') for path in (off_path, on_path)]
    require(all(m is not None and m.get('status') == 'complete' for m in manifests), 'wait for both terminal complete runs')
    rows = []
    counter_checks = {}
    for arm, path, manifest in zip(('off', 'on'), (off_path, on_path), manifests):
        row = base.native(path, '023_EDF_' + arm + '_1x', reader, controls[arm], expected_scale=1)
        require_full_row(row)
        require(manifest.get('full_population_performance_available') is True, 'manifest full-pop gate absent')
        identity = row['identity']
        require(all(base.get(identity, name, 'sha256') == expected for name, expected in
            [('native_source', SOURCE), ('binary', binding['binary_sha256']), ('canonical', CANONICAL), ('profile', PROFILE)]), 'run input/source/binary identity mismatch')
        selection = manifest['selection']
        require(selection['contract']['sha256'] == binding['contract']['sha256'], 'run registered a different physical contract')
        tht = reader.read(Path(path) / 'tht_audit.json')
        native = reader.read(Path(path) / 'native_summary.json')
        require(native.get('event_budget_exhausted') is False and native.get('executed_horizon') == 98259, 'native run truncated')
        counter_checks[arm] = check_counters(native, arm == 'on')
        row['metrics']['activation_to_first_planning'] = base.statistics(base.get(tht, 'secondary', 'business_sum_activation_to_first_planning'))
        row['metrics']['canonical_to_activation'] = base.statistics(base.get(tht, 'secondary', 'business_sum_canonical_to_activation'))
        row['metrics']['supplemental_ready_mean_derived'] = derived_ready(tht, True)
        row['edf_counter_check'] = counter_checks[arm]
        row['original_window_evidence'] = 'Actual independent1x original98259 execution, no drain projection.'
        rows.append(row)
    effective_controls = check_controls(rows[0]['controls'], rows[1]['controls'])
    require(rows[0]['identity']['binary'] == rows[1]['identity']['binary']
            and rows[0]['identity']['native_source'] == rows[1]['identity']['native_source'], 'pair is not same implementation')
    require(contract.get('end_time') == 98259 and contract.get('positive_node_service_seconds') == 2
            and contract.get('edge_entry_headway_seconds') == 2 and contract.get('time_grid_seconds') == 1e-6, 'physical contract changed')
    context = read_bound(reader, C / 'nanning_campaign_snapshot_001/snapshot_006.json', SNAPSHOT_SHA)
    hca = copy.deepcopy(next(x for x in context['runs'] if x['kind'] == 'hca' and x['scale'] == 1))
    historical = copy.deepcopy(next(x for x in context['runs'] if Path(x['path']).name == 'g31_nanning_1x_future60_cap120_relax1_010c'))
    for row in (historical, hca):
        require(row['usable_reported_result'] is True and row['metrics']['full_population_available'] is True, 'context reference unavailable')
        row['context_identity_boundary'] = 'Inherited pinned snapshot006 prior audit/input identities; no new native/population or large-file verification.'
    comparisons = [base.contrast(rows[1], rows[0], 'Primary: same023 binary EDF on versus off; sole control switch'),
                   base.contrast(rows[1], historical, 'Context: EDF on versus historical010c1x'),
                   base.contrast(rows[1], hca, 'Context: EDF on versus repaired physical HCA1x')]
    return {'schema': 'g31.candidate023.same_binary_nanning1x_comparison.v1', 'passed': True,
            'status': 'completed_pair_small_summary_validation', 'runs': rows + [historical, hca], 'comparisons': comparisons,
            'checks': {'raw_controls': raw_controls, 'effective_controls': effective_controls, 'same_binary_source_input_contract': True,
                       'full_population_and_five_gates': True, 'edf_counters': counter_checks},
            'source_files': reader.evidence, 'helper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'frozen_summary_base_sha256': BASE_SHA, 'boundaries': [
                'Only named small summaries read after both runs complete. Existing physical/source/rolling/THT/business audits remain authoritative; this is not a new bag/ledger EDF-order audit.',
                'Primary THT includes first-attempt retries but excludes preplanning; preplanning, derived-ready mean, actual fixed-window throughput, full tails, and both deadline standards remain visible.',
                'Same-binary on/off isolates the configured scheduling policy. One deterministic run per arm is not a statistical runtime study; CPU/wall scopes stay separate.',
                'Historical010c/HCA are contextual references. No native-event/API versus Java whole-run speed ratio is computed.',
                'EDF telemetry counts repeated actual valid source attempts, including already-overdue attempts. It cannot identify distinct prioritized bags or wins.',
                'EBS ready-first remains deferred. Canonical FIFO, feed, predecessor gates and existing reservation rights remain unchanged.',
                'If either arm is censored or any gate/identity fails, this full-population paired report is rejected; do not substitute completed-only means.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--off-run', type=Path, required=True)
    parser.add_argument('--on-run', type=Path, required=True)
    parser.add_argument('--binding', type=Path, default=HERE / 'FROZEN_BINDING_001.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists() and not args.output.with_suffix('.txt').exists(), 'append-only output already exists')
    result = run(args.off_run, args.on_run, args.binding)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    with args.output.with_suffix('.txt').open('x', encoding='utf-8') as stream:
        stream.write(base.render(result).replace('南宁 2x：', '南宁 1x：', 1) + '\n' + '\n'.join(result['boundaries']) + '\n')
    print(json.dumps({'passed': True, 'output': str(args.output.resolve()), 'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
