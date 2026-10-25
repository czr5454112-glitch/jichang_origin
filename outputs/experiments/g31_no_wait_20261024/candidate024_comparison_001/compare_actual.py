"""0241x small evidence: primary candidate,023 contexts,optional same-binary off."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import parent_comparison as parent

HERE = Path(__file__).resolve().parent
C = HERE.parent
base = parent.base
require = parent.require
FLAG = 'prefer_nonexpired_source_attempts'
SOURCE = '60ab9b2438659791c9df6581205a1fe7ba591f3988aa91e37922d0a65b01b44c'
PARENT_SHA = '3c748b84c573ddd6961627e7e86905d7e81f643bc86f22659dcc68696431b468'
PRIOR_SHA = 'd6bd299db093ba70a4aeffe266808f49b48c6937d16a80490ce5547b52ecdd63'
base.SMALL_NAMES.update({'SOURCE_FREEZE_024_001.json', 'FROZEN_BINDING_001.json', 'comparison_001.json'})


def check_controls(candidate, reference, *, same_binary=False):
    require(type(candidate.get(FLAG)) is bool and candidate[FLAG] is True, 'candidate class switch must be true bool')
    require(type(candidate.get(parent.FLAG)) is bool and candidate[parent.FLAG] is True, 'class rule requires EDF enabled')
    other = dict(reference)
    if same_binary:
        require(type(other.get(FLAG)) is bool and other[FLAG] is False, 'same-binary reference class switch must explicitly be false')
    else:
        other.setdefault(FLAG, False)
        require(type(other[FLAG]) is bool and other[FLAG] is False, 'parent reference must have class disabled')
    require(type(other.get(parent.FLAG)) is bool and other[parent.FLAG] is True, 'reference must be EDF on')
    require(base.different_control_keys(candidate, other) == {FLAG}, 'class comparison changes other controls')
    require(candidate.get('end_time') == 98259 and candidate.get('source_fifo') is True
            and candidate.get('source_fifo_order') == 'canonical'
            and candidate.get('enable_ebs_predecessor_gate') is True, 'window/source/EBS contract changed')
    return {'passed': True, 'sole_control_change': FLAG,
            'same_binary': same_binary, 'missing_parent_flag_interpreted_as_registered_false_default': not same_binary,
            'boundary': 'Same-binary policy pair.' if same_binary else 'Different024/023 binary/source; default-false micro parity supports inheritance but is not full-population same-binary policy isolation.'}


def verify_binding(value):
    require(value.get('schema') == 'g31.candidate024.comparison_binding.v1' and value.get('passed') is True
            and value.get('default_false_parity_passed') is True and value.get('build_micro_five_gates_passed') is True, 'final024/default-false parity binding required')
    require(value.get('source_sha256') == SOURCE, '024 source changed')
    sha = value.get('binary_sha256')
    require(isinstance(sha, str) and len(sha) == 64 and all(c in '0123456789abcdef' for c in sha), 'missing final024 binary identity')


def enrich(row, reader):
    parent.require_full_row(row)
    path = Path(row['path'])
    tht = reader.read(path / 'tht_audit.json')
    native = reader.read(path / 'native_summary.json')
    require(native.get('event_budget_exhausted') is False and native.get('executed_horizon') == 98259, 'native truncated')
    row['metrics']['activation_to_first_planning'] = base.statistics(base.get(tht, 'secondary', 'business_sum_activation_to_first_planning'))
    row['metrics']['canonical_to_activation'] = base.statistics(base.get(tht, 'secondary', 'business_sum_canonical_to_activation'))
    row['metrics']['supplemental_ready_mean_derived'] = parent.derived_ready(tht, True)
    row['edf_counter_check'] = parent.check_counters(native, True)
    row['original_window_evidence'] = 'Actual Nanning1x original98259 run; no drain projection.'
    return row


def refresh_prior(row, reader, evidence):
    require(row['usable_reported_result'] is True and row['metrics']['full_population_available'] is True, 'prior reference unavailable')
    path = Path(row['path'])
    for name in ('manifest.json', *base.GATES.values()):
        p = path / name
        value = reader.read(p)
        require(value is not None and reader.evidence[str(p.resolve())]['sha256'] == evidence[str(p.resolve())]['sha256'], 'prior023 evidence changed')
        if name == 'manifest.json':
            require(value['status'] == 'complete' and value['audits_passed'], 'prior023 incomplete')
        else:
            require(value['passed'] is True, 'prior023 audit failed')


def run(candidate_path, binding_path, same_binary_off=None):
    require(hashlib.sha256((HERE / 'parent_comparison.py').read_bytes()).hexdigest() == PARENT_SHA, 'frozen023 scalar helper changed')
    require(hashlib.sha256((HERE / 'summary_base.py').read_bytes()).hexdigest() == parent.BASE_SHA, 'frozen small-summary helper changed')
    reader = base.SmallReader()
    binding = reader.read(binding_path)
    verify_binding(binding)
    freeze = parent.read_bound(reader, binding['freeze']['path'], binding['freeze']['sha256'])
    require(freeze['passed'] is True and freeze['source']['sha256'] == SOURCE
            and freeze['binary']['sha256'] == binding['binary_sha256'], 'final024freeze mismatch')
    contract = parent.read_bound(reader, binding['contract']['path'], binding['contract']['sha256'])
    controls = {mode: parent.read_bound(reader, value['path'], value['sha256']) for mode, value in binding['controls'].items()}
    require(base.different_control_keys(controls['on'], controls['off']) == {FLAG}, 'bound raw controls differ beyond class switch')
    paths = [('on', Path(candidate_path), '024_nonexpired_EDF_on_1x')]
    if same_binary_off is not None:
        paths.append(('off', Path(same_binary_off), '024_class_off_EDF_on_1x'))
    manifests = [reader.read(path / 'manifest.json') for _, path, _ in paths]
    require(all(x is not None and x.get('status') == 'complete' for x in manifests), 'wait for terminal024 results')
    rows = []
    for (mode, path, label), manifest in zip(paths, manifests):
        row = enrich(base.native(path, label, reader, controls[mode], expected_scale=1), reader)
        require(manifest.get('full_population_performance_available') is True, 'manifest full-pop gate unavailable')
        require(all(base.get(row['identity'], key, 'sha256') == value for key, value in
            [('native_source', SOURCE), ('binary', binding['binary_sha256']), ('canonical', parent.CANONICAL), ('profile', parent.PROFILE)]), '024 source/binary/input mismatch')
        require(manifest['selection']['contract']['sha256'] == binding['contract']['sha256'], '024 contract identity mismatch')
        rows.append(row)
    require(contract['end_time'] == 98259 and contract['positive_node_service_seconds'] == 2
            and contract['edge_entry_headway_seconds'] == 2 and contract['time_grid_seconds'] == 1e-6, 'physical2s contract changed')
    prior = parent.read_bound(reader, C / 'candidate023_comparison_plan_001/comparison_001.json', PRIOR_SHA)
    require(prior['passed'] is True, '023 paired comparison failed')
    ref_off, ref_on = [copy.deepcopy(prior['runs'][i]) for i in (0, 1)]
    for row in (ref_off, ref_on):
        refresh_prior(row, reader, prior['source_files'])
    hca = copy.deepcopy(prior['runs'][3])
    require(hca['kind'] == 'hca' and hca['usable_reported_result'], 'HCA context unavailable')
    hca['context_identity_boundary'] = 'Pinned023 comparison inherits repairedHCA prior audits/identity; no fresh HCA population scan.'
    checks = {'024_vs023_EDF_on_controls': check_controls(rows[0]['controls'], ref_on['controls']),
              'same_binary_reference_executed': same_binary_off is not None,
              'full_population_and_five_gates': True, 'default_false_micro_parity_binding': binding['freeze']}
    comparisons = []
    if same_binary_off is not None:
        checks['024_same_binary_controls'] = check_controls(rows[0]['controls'], rows[1]['controls'], same_binary=True)
        comparisons.append(base.contrast(rows[0], rows[1], 'Primary same024 binary nonexpired class ON versus classOFF, EDF ON in both'))
    comparisons.extend([base.contrast(rows[0], ref_on, '024 classON versus023 EDFON; different binary/source, default-false micro inheritance only'),
        base.contrast(rows[0], ref_off, '024 classON+EDFON versus023 EDFOFF main reference; two ordering controls differ'),
        base.contrast(rows[0], hca, 'Context repairedHCA1x')])
    return {'schema': 'g31.candidate024.nanning1x.small_comparison.v1', 'passed': True,
        'status': 'actual_completed_small_results_only', 'runs': rows + [ref_on, ref_off, hca],
        'checks': checks, 'comparisons': comparisons, 'source_files': reader.evidence,
        'helper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'boundaries': [
            'FullpopulationTHT remains primary; preplanning/derivedready/throughput/tails/STD andSTD-2700 are retained. No completed-subset fallback.',
            'Unless an actual024classOFF run is supplied, the023 references use a different binary/source. Defaultfalse micro parity is not a real-population samebinary contrast.',
            'Compare024 to023EDFON for the additional class rule;023EDFOFF differs in bothEDF andclass ordering. Neither comparison proves per-request causation.',
            'EDFvalid/overdue counters are repeated valid attempts, not distinct bags or wins. No extra class competition telemetry is invented.',
            'Readymean is only the unchangedactivation/fullpop sum identity; no new per-bag causal-ready audit or derived tail quantiles.',
            'Existing fiveaudits establish physical/source safety. No bags/ledger/native execution occurs in this helper.',
            'CPU/wall scopes remain separate single-run observations, without statistical or cross-language speed claims. EBSreadyfirst,022realmap and011timingv2 remain deferred.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--binding', type=Path, default=HERE / 'FROZEN_BINDING_001.json')
    parser.add_argument('--same-binary-off', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists() and not args.output.with_suffix('.txt').exists(), 'append-only output exists')
    result = run(args.candidate, args.binding, args.same_binary_off)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    with args.output.with_suffix('.txt').open('x', encoding='utf-8') as stream:
        stream.write(base.render(result).replace('南宁 2x：', '南宁 1x：', 1) + '\n' + '\n'.join(result['boundaries']) + '\n')
    print(json.dumps({'passed': True, 'output': str(args.output.resolve()), 'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
