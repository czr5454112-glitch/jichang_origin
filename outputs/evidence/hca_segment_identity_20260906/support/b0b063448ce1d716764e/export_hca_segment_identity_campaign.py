"""Archive and compare newly executed HCA with the frozen G31/V5 observations."""
from __future__ import annotations

import argparse
import ast
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_cie_external_baseline_robustness as external
from scripts.eval import run_hca_segment_identity_campaign as campaign
from scripts.eval import export_feng_v5_campaign as previous

HCA = campaign.METHOD
G31 = external.REFERENCE_METHOD
V5 = previous.METHOD
METHODS = (G31, V5, HCA)
EVIDENCE = ROOT / 'outputs/evidence/hca_segment_identity_20260906'
FINAL_RUNTIME = ROOT / 'outputs/runtime/hca_segment_identity_20260906_fast_cleanup'
TABLES = ROOT / 'outputs/tables'
OLD_TABLE = TABLES / 'feng_dh_v5_cells_20260905.csv'
OLD_TABLE_SHA = '702d20c22a639c7b5e1f8143dda7bf44158e9b3cae1627d3d6c1c8a49b7eda09'
EQUIVALENCE_AUDITOR = 'scripts/eval/audit_hca_postprocessing_equivalence.py'
EQUIVALENCE_TEST = 'tests/test_hca_postprocessing_equivalence.py'
EQUIVALENCE_NAME = 'postprocessing_equivalence.json'
EQUIVALENCE_FILES = ('segment_execution_identity.csv', 'release.csv', 'routes.csv', 'output.txt',
                     'outputstarttime.txt', 'execution_terminal.csv', 'summary.csv', 'population_audit.json',
                     'segment_lifecycle.csv', 'raw_bag_timings.csv')
require, sha, read, write = campaign.require, campaign.sha, campaign.read, campaign.write


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def relocated(path):
    """Resolve an archived repository path without requiring the original host."""
    text = str(path).replace('\\', '/')
    for marker in ('outputs/', 'data/', 'benchmarks/', 'legacy/', 'scripts/', 'docs/', 'build/', 'tests/'):
        if text.startswith(marker):
            result = ROOT / text
            break
        if '/' + marker in text:
            result = ROOT / (marker + text.split('/' + marker, 1)[1])
            break
    else:
        raise ValueError('not a repository evidence path: ' + text)
    require(result.resolve().is_relative_to(ROOT), 'path escapes repository')
    return result.resolve()


def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def csv_write(path, rows):
    fields = sorted(set().union(*(r.keys() for r in rows)))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def cell_key(row):
    return row['map'], float(row['load_factor']), int(row['seed']), row['method']


def numerically_equal(left, right):
    if left in (None, '') or right in (None, ''):
        return left in (None, '') and right in (None, '')
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-8)


def archive_file(source, target, *, compress=False):
    record = previous.archive_file(Path(source), Path(target), compress=compress)
    record['archive_path'] = relative(record['archive_path'])
    record['source_path'] = relative(source)
    return record


def support_destination(path, digest=None):
    """Keep paths short and preserve content versions; retain source_path in the manifest."""
    key = relative(path) + '\0' + (sha(path) if digest is None else digest)
    namespace = hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]
    return Path('support') / namespace / Path(path).name


def validate_equivalence_shape(value, old_runtime, new_runtime):
    expected = set(campaign.PREFLIGHT)
    require(value.get('schema') == 'czr005.hca_postprocessing_equivalence.v1' and value.get('status') == 'PASS',
            'five-cell postprocessing equivalence must PASS')
    require(value.get('expected_paired_cells') == value.get('passed_paired_cells') == 5
            and not value.get('missing_cells') and not value.get('failures'), 'postprocessing equivalence is incomplete')
    cells = value['cells']
    require(len(cells) == 5 and {(c['map'], float(c['load_factor']), int(c['seed'])) for c in cells} == expected
            and all(c['status'] == 'PASS' for c in cells), 'postprocessing equivalence coordinates differ')
    require(value.get('old_preflight_cells_in_final_matrix') == 0 and value.get('duplicate_selection_by_performance') is False
            and value.get('protocol_difference_allowed') is False, 'postprocessing control selection/protocol policy differs')
    require(relocated(value['old_root']) == Path(old_runtime).resolve()
            and relocated(value['new_root']) == Path(new_runtime).resolve()
            and Path(old_runtime).resolve() != Path(new_runtime).resolve(), 'postprocessing runtime roots differ')
    for cell in cells:
        require(set(cell['scientific_files']) == set(EQUIVALENCE_FILES), 'postprocessing scientific file coverage differs')
        require(cell['metrics_equal'] is True and cell['population_audit_bytes_equal'] is True
                and cell['java_build_bytes_equal'] is True and cell['python_runner_identity_changed'] is True,
                'postprocessing scientific equality or runner revision is absent')
        # The frozen Java summary contains no wall-clock columns.
        require(cell['summary_excluded_wall_columns'] == [], 'frozen summary must be compared byte-for-byte')
        for name, record in cell['scientific_files'].items():
            require(record['comparison'] == 'BYTES_EQUAL' and record['old_sha256'] == record['new_sha256'],
                    'postprocessing file equality differs: ' + name)
    return value


def postprocessing_gate(result_root, freeze, *, required):
    path = Path(result_root) / 'preflight' / EQUIVALENCE_NAME
    if not path.exists():
        require(not required, 'final export requires five-cell postprocessing_equivalence.json PASS')
        return {'status': 'INCOMPLETE', 'reason': 'EQUIVALENCE_NOT_YET_AVAILABLE'}
    value = read(path)
    if value.get('status') != 'PASS':
        require(not required, 'final export requires five-cell postprocessing equivalence PASS')
        return {'status': value.get('status', 'INCOMPLETE'), **campaign.bound_file(path)}
    old_runtime = (ROOT / freeze['microtests']['path']).parent.parent
    validate_equivalence_shape(value, old_runtime, result_root)
    require(value['auditor_sha256'] == sha(ROOT / EQUIVALENCE_AUDITOR), 'postprocessing auditor source changed')
    return {'status': 'PASS', **campaign.bound_file(path)}


def archived_payload(record):
    path = relocated(record['archive_path'])
    require(sha(path) == record['archive_sha256'], 'archived payload digest differs')
    data = path.read_bytes()
    if record['gzip']:
        data = gzip.decompress(data)
    require(hashlib.sha256(data).hexdigest() == record['source_sha256'], 'archived original bytes differ')
    return data


def verify_postprocessing_equivalence(manifest, support, freeze, freeze_file):
    """Recheck the five comparisons using only archived bytes, without either runner."""
    old_root = Path(freeze['microtests']['path']).parent.parent
    new_root = Path(freeze_file['source_path']).parent
    key = (new_root / 'preflight' / EQUIVALENCE_NAME).as_posix()
    gate = manifest['postprocessing_equivalence']
    require(gate['status'] == 'PASS' and gate['path'] == key and gate['sha256'] == support[key]['source_sha256'],
            'final postprocessing equivalence support differs')
    value = json.loads(archived_payload(support[key]))
    validate_equivalence_shape(value, ROOT / old_root, ROOT / new_root)
    require(value['auditor_sha256'] == support[EQUIVALENCE_AUDITOR]['source_sha256'], 'archived equivalence auditor differs')
    archived_payload(support[EQUIVALENCE_AUDITOR])
    archived_payload(support[EQUIVALENCE_TEST])
    old_freeze_key = (old_root / 'campaign_freeze.json').as_posix()
    old_freeze = json.loads(archived_payload(support[old_freeze_key]))
    require(old_freeze['method'] == freeze['method'] == HCA and old_freeze['protocol'] == freeze['protocol']
            and old_freeze['build_identity'] == freeze['build_identity'], 'cleanup changed Java build or protocol')
    # The old freeze's runner path now names the current file. Resolve its
    # explicitly preserved source, never the mutable original path.
    saved_key = (old_root / 'preflight/superseded_slow_cleanup_tools/run_hca_segment_identity.py').as_posix()
    old_source = archived_payload(support[saved_key])
    new_source = archived_payload(support[freeze['runner']['path']])
    old_sha, new_sha = hashlib.sha256(old_source).hexdigest(), hashlib.sha256(new_source).hexdigest()
    require(old_sha == old_freeze['runner']['sha256'] and new_sha == freeze['runner']['sha256'] and old_sha != new_sha,
            'saved old/current Python runner identities differ from their freezes')
    validation_key = (old_root / 'preflight/cleanup_revision_validation.json').as_posix()
    validation = json.loads(archived_payload(support[validation_key]))
    require(validation['status'] == 'PASS' and validation['old_runner_sha256'] == old_sha
            and validation['new_runner_sha256'] == new_sha
            and validation['only_changed_production_function'] == 'cleanup_epoch_scratch'
            and validation['non_cleanup_module_AST_identical'] is True, 'cleanup revision source evidence differs')
    def unchanged_ast(data):
        module = ast.parse(data.decode('utf-8-sig'))
        changed = [n for n in module.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'cleanup_epoch_scratch']
        require(len(changed) == 1, 'cleanup function missing or duplicated in archived runner')
        module.body = [n for n in module.body if n is not changed[0]]
        return ast.dump(module, include_attributes=False)
    require(unchanged_ast(old_source) == unchanged_ast(new_source), 'archived runner changed outside cleanup')
    for path, digest in validation['tests']['files'].items():
        require(support[path]['source_sha256'] == digest, 'cleanup regression test identity differs')
        archived_payload(support[path])
    old_cells = {(c['map'], float(c['load_factor']), int(c['seed'])): c for c in old_freeze['cells']}
    new_cells = {(c['map'], float(c['load_factor']), int(c['seed'])): c for c in freeze['cells']}
    formal = {cell_key(c): c for c in manifest['cells'] if c['method'] == HCA}
    verified = []
    for pair in value['cells']:
        coordinate = pair['map'], float(pair['load_factor']), int(pair['seed'])
        old_cell, new_cell = old_cells[coordinate], new_cells[coordinate]
        require(old_cell['identity'] == new_cell['identity'], 'paired freezes name different input identities')
        old_native = Path(old_cell['output'])
        new_native = Path(new_cell['output'])
        require(old_native.is_relative_to(old_root) and new_native.is_relative_to(new_root), 'paired output root differs')
        cell = formal[(*coordinate, HCA)]
        require(cell['origin'] == 'NEW_EXECUTION', 'old preflight substituted for a formal cell')
        native_index = {f['source_path']: f for f in cell['files']}
        require(len(native_index) == len(cell['files']), 'duplicate formal archive source path')
        old_manifest_key = (old_native / 'native_archive/manifest.json').as_posix()
        old_archive = json.loads(archived_payload(support[old_manifest_key]))
        require(old_archive['method'] == HCA, 'old native archive method differs')
        old_index = {f['source_name']: f for f in old_archive['files']}
        require(len(old_index) == len(old_archive['files']), 'duplicate old archive source name')
        cache = {}
        def old_bytes(name):
            if name not in cache:
                entry = old_index[name]
                require(not entry.get('absent') and entry['path'] == 'native_archive/' + name + '.gz', 'wrong old native archive path')
                container = archived_payload(support[(old_native / entry['path']).as_posix()])
                require(hashlib.sha256(container).hexdigest() == entry['sha256'], 'old native gzip digest differs')
                data = gzip.decompress(container)
                require(hashlib.sha256(data).hexdigest() == entry['uncompressed_sha256']
                        and len(data) == entry['uncompressed_size_bytes'], 'old native restored bytes differ')
                cache[name] = data
            return cache[name]
        def new_bytes(name):
            return archived_payload(native_index[(new_native / name).as_posix()])
        for name in EQUIVALENCE_FILES:
            before, after = old_bytes(name), new_bytes(name)
            record = pair['scientific_files'][name]
            require(hashlib.sha256(before).hexdigest() == record['old_sha256']
                    and hashlib.sha256(after).hexdigest() == record['new_sha256'] and before == after,
                    'portable cleanup scientific file differs: ' + name)
        old_status, new_status = (json.loads(get('runner_status.json')) for get in (old_bytes, new_bytes))
        old_value, new_value = (json.loads(get('normalized_result.json')) for get in (old_bytes, new_bytes))
        require(old_bytes('build_identity.json') == new_bytes('build_identity.json')
                and hashlib.sha256(new_bytes('build_identity.json')).hexdigest() == freeze['build_identity']['sha256'],
                'portable cleanup Java build differs')
        for label, status, normalized, get, runner_digest in (('old', old_status, old_value, old_bytes, old_sha),
                                                               ('new', new_status, new_value, new_bytes, new_sha)):
            provenance = pair['provenance'][label]
            require(status['status'] == 'complete' and status['returncode'] == 0 and status['method'] == HCA
                    and status['python_runner_sha256'] == provenance['python_runner_sha256'] == runner_digest,
                    'portable cleanup runtime identity differs')
            require(status['protocol_sha256'] == provenance['protocol_sha256'] == freeze['protocol']['sha256']
                    and status['build_identity_sha256'] == provenance['build_identity_sha256'] == freeze['build_identity']['sha256'],
                    'portable cleanup protocol/build binding differs')
            require(provenance['runner_status_sha256'] == hashlib.sha256(get('runner_status.json')).hexdigest()
                    and provenance['normalized_result_sha256'] == hashlib.sha256(get('normalized_result.json')).hexdigest(),
                    'equivalence provenance does not bind archived observations')
            require(status['source_sha256'] == provenance['source_sha256'] == manifest['source_sha256']
                    and status['class_sha256'] == provenance['class_sha256'] == manifest['class_sha256'], 'portable cleanup Java identity differs')
            require(status['workload_identity_sha256'] == normalized['workload_identity_sha256'] == pair['inputs']['identity']
                    == new_cell['identity']['sha256'], 'portable cleanup workload identity differs')
            for field in ('raw', 'canonical', 'map'):
                require(status['inputs'][field]['sha256'] == normalized['workload_' + field + '_sha256'] == pair['inputs'][field]
                        == new_cell[field + '_sha256'], 'portable cleanup input bytes differ: ' + field)
            require(normalized['population_audit'] == json.loads(get('population_audit.json')), 'portable cleanup audit payload differs')
            bound = {Path(r['path'].replace('\\', '/')).name: r['sha256'] for r in normalized['native_evidence']}
            for name in (*EQUIVALENCE_FILES, 'runner_status.json', 'build_identity.json'):
                require(bound[name] == hashlib.sha256(get(name)).hexdigest(), 'old/new normalized native evidence binding differs: ' + name)
        omitted = {'native_evidence', 'workload_identity_path', 'generated_at', 'normalized_at'}
        require({k: v for k, v in old_value.items() if k not in omitted} == {k: v for k, v in new_value.items() if k not in omitted},
                'portable cleanup metrics or normalized science differs')
        verified.append(dict(zip(('map', 'load_factor', 'seed'), coordinate)))
    return {'status': 'PASS', 'paired_cells_verified': len(verified), 'cells': verified,
            'old_preflight_cells_in_final_matrix': 0, 'old_runner_source_resolved_from_saved_copy': saved_key,
            'non_cleanup_module_AST_independently_equal': True, 'simulations_started': 0}


def previous_controls():
    require(sha(campaign.OLD_MANIFEST) == campaign.OLD_MANIFEST_SHA and sha(OLD_TABLE) == OLD_TABLE_SHA,
            'previous complete observations changed')
    old = read(campaign.OLD_MANIFEST)
    table = {cell_key(r): r for r in csv_rows(OLD_TABLE)}
    rows, records, checked = [], [], set()
    for cell in old['cells']:
        if cell['method'] not in (G31, V5):
            continue
        row = dict(table[cell_key(cell)])
        require(cell['diagnostic']['status'] == 'PASS', 'previous population audit absent')
        for field, metric in cell['exported_metrics'].items():
            require(numerically_equal(row.get(field), metric), 'previous table/manifest metric mismatch: ' + field)
            row[field] = metric
        row['load_factor'], row['seed'] = float(row['load_factor']), int(row['seed'])
        row['full_population_complete'] = str(row['full_population_complete']).lower() == 'true'
        row['historical_shared_D'] = False
        files = []
        for file in cell['files']:
            path = relocated(file['archive_path'])
            if path not in checked:
                require(sha(path) == file['archive_sha256'], 'reused archive byte drift: ' + str(path))
                checked.add(path)
            file = dict(file)
            file['archive_path'] = relative(path)
            files.append(file)
        rows.append(row)
        records.append({'map': cell['map'], 'load_factor': cell['load_factor'], 'seed': cell['seed'],
                        'method': cell['method'], 'origin': 'REUSED_PREVIOUS_FROZEN_ARCHIVE',
                        'exported_metrics': cell['exported_metrics'], 'diagnostic': cell['diagnostic'],
                        'files': files, 'table_row': row})
    require(len(rows) == 120, 'expected all 60 G31 and 60 V5 controls')
    return rows, records


def paired_aggregate(rows, replicates=10000):
    indexed = {cell_key(r): r for r in rows}
    require(len(indexed) == len(rows), 'duplicate matrix cell')
    for map_name, load, seed in campaign.keys():
        group = [indexed[(map_name, load, seed, method)] for method in METHODS if (map_name, load, seed, method) in indexed]
        require(len({r['workload_identity_sha256'] for r in group}) == 1, 'methods differ in workload identity')
    higher = external.HIGHER_IS_BETTER | {'completed_raw_bags_per_fixed_horizon_hour'}
    metrics = sorted(higher | external.LOWER_IS_BETTER | set(previous.PRIMARY + previous.ADMISSION) | {'unfinished_raw_bag_count'})
    result = []
    for map_name in external.MAPS:
        for load in external.LOAD_FACTORS:
            for baseline, reference in ((HCA, G31), (V5, G31), (V5, HCA)):
                for metric in metrics:
                    record = {'map': map_name, 'load_factor': load, 'baseline': baseline, 'reference': reference,
                              'metric': metric, 'preferred_direction': 'higher' if metric in higher else 'lower'}
                    missing, pairs = [], []
                    for seed in external.SEEDS:
                        left, right = indexed.get((map_name, load, seed, baseline)), indexed.get((map_name, load, seed, reference))
                        if left is None or right is None or left.get(metric) in (None, '') or right.get(metric) in (None, ''):
                            missing.append(seed)
                        else:
                            pairs.append((seed, float(left[metric]), float(right[metric])))
                    record.update(paired_seed_count=len(pairs), missing_seed_count=len(missing), missing_seeds=','.join(map(str, missing)))
                    if metric in previous.FORMAL_TIMING and load == 2.0:
                        record['status'] = 'FORMAL_2X_TIMING_NA_BY_PROTOCOL'
                    elif missing:
                        record['status'] = 'INCOMPLETE_TEN_SEED_COMPARISON_NO_SUBSET_ESTIMATE'
                    else:
                        deltas = [b - a for _, a, b in pairs]
                        oriented = deltas if metric in higher else [-d for d in deltas]
                        prefix = 'v5' if (baseline, reference) == (V5, G31) else 'hca-segment-id'
                        low, high = external.paired_bootstrap_ci(deltas, replicates=replicates,
                            seed_key=f'{prefix}|{map_name}|{load}|{baseline}|{reference}|{metric}')
                        record.update(status='COMPLETE', baseline_mean=statistics.fmean(p[1] for p in pairs),
                            reference_mean=statistics.fmean(p[2] for p in pairs), mean_delta_reference_minus_baseline=statistics.fmean(deltas),
                            bootstrap_ci_low=low, bootstrap_ci_high=high,
                            reference_win_count=sum(d > 1e-12 for d in oriented), tie_count=sum(abs(d) <= 1e-12 for d in oriented),
                            reference_loss_count=sum(d < -1e-12 for d in oriented))
                    result.append(record)
    return {'schema': 'czr005.hca_segment_identity_paired.v1', 'status': 'COMPLETE' if len(rows) == 180 else 'INCOMPLETE',
            'expected_cells': 180, 'observed_cells': len(rows), 'bootstrap_replicates': replicates,
            'confidence_level': .95, 'bootstrap_unit': 'MATCHED_WORKLOAD_SEED_NOT_INDIVIDUAL_BAG',
            'partial_seed_estimates_suppressed': True, 'rows': result}


def flat_hca(value):
    row = {k: value[k] for k in ('map', 'load_factor', 'seed', 'method', 'fixed_horizon_seconds',
                                'workload_identity_sha256', 'full_population_complete', 'formal_timing_status')}
    row.update(value['metrics'])
    row.update(reporting_method=HCA, raw_bag_count=value['raw_bag_denominator'], segment_count=value['segment_denominator'],
               input_sha256=value['workload_raw_sha256'], canonical_sha256=value['workload_canonical_sha256'],
               map_sha256=value['workload_map_sha256'], TH_completed_raw_bags=value['metrics']['completed_raw_bag_count'],
               TH_definition='COMPLETED_RAW_BAG_COUNT_BY_FIXED_ABSOLUTE_EPOCH_98259', historical_shared_D=False,
               primary_timing_definition='SUM_PER_BAG_SEGMENT_COMPLETION_MINUS_COMMON_CANONICAL_SCHEDULED_RELEASE',
               population_evidence_level='UNIQUE_EXECUTION_ID_NATIVE_EVENTS_AND_ALL_CANONICAL_TERMINAL_STATES',
               control_reuse_provenance_tier='NEW_EXECUTION_WITH_FROZEN_SOURCE_AND_CLASSES')
    contract, audit = value['normalization_contract'], value['population_audit']
    row.update(source_sha256=contract['reconstruction_java_source_sha256'], class_sha256=contract['compiled_java_class_sha256'],
               native_terminal_status=contract['native_terminal_status'], terminal_accounting_residual=audit['terminal_accounting_residual'],
               canonical_id_OD_and_scheduled_D_match=True, canonical_segment_count=value['segment_denominator'],
               completed_segments=audit['completed_segment_count'], observed_lifecycle_count=value['segment_denominator'],
               primary_clock='CANONICAL_SCHEDULED_RELEASE',
               release_epoch_minus_canonical_D_min_seconds=audit['native_release_minus_canonical_D_min_seconds'],
               release_epoch_minus_canonical_D_max_seconds=audit['native_release_minus_canonical_D_max_seconds'])
    return row


def archive_native(cell, normalized, evidence):
    native = ROOT / cell['output']
    dest = external.cell_dir(evidence, cell['load_factor'], cell['seed'], map_name=cell['map'])
    files = []
    for path in sorted(native.iterdir()):
        if not path.is_file() or path.name.endswith(('.lock', '.tmp')):
            continue
        compressed = path.suffix in ('.csv', '.txt') and path.stat().st_size > 200000
        files.append(archive_file(path, dest / 'native' / (path.name + '.gz' if compressed else path.name), compress=compressed))
    identity = read(ROOT / cell['identity']['path'])
    paths = [('identity.json', ROOT / cell['identity']['path']), ('inputdata.txt', relocated(identity['raw_path'])),
             ('canonical.jsonl', relocated(identity['canonical_path'])), ('map.txt', relocated(identity['map_path']))]
    for name, path in paths:
        compressed = name in ('inputdata.txt', 'canonical.jsonl')
        files.append(archive_file(path, dest / 'workload' / (name + '.gz' if compressed else name), compress=compressed))
    return {'map': cell['map'], 'load_factor': cell['load_factor'], 'seed': cell['seed'], 'method': HCA,
            'origin': 'NEW_EXECUTION', 'exported_metrics': normalized['metrics'],
            'diagnostic': normalized['population_audit'], 'files': files, 'table_row': flat_hca(normalized)}


def export(args):
    freeze = campaign.check_freeze(args)
    equivalence = postprocessing_gate(args.result_root, freeze, required=args.require_complete)
    rows, records = previous_controls()
    missing = []
    for cell in freeze['cells']:
        if not (ROOT / cell['output'] / 'normalized_result.json').exists():
            missing.append({k: cell[k] for k in ('map', 'load_factor', 'seed')})
            continue
        value = campaign.load_completed(cell)
        from scripts.eval import run_hca_segment_identity as native_runner
        native_runner.load_result(ROOT / cell['output'] / 'normalized_result.json')
        records.append(archive_native(cell, value, args.evidence_root))
        records[-1]['table_row']['wall_seconds'] = read(ROOT / cell['output'] / 'runner_status.json').get('wall_seconds')
        rows.append(records[-1]['table_row'])
    require(not args.require_complete or not missing, 'final export requires all 60 repaired HCA cells')
    require(len({cell_key(r) for r in rows}) == len(rows), 'duplicate output coordinates')
    paired = paired_aggregate(rows, args.replicates)
    cells_path = TABLES / 'hca_segment_identity_cells_20260906.csv'
    paired_path = TABLES / 'hca_segment_identity_paired_20260906.csv'
    paired_json = paired_path.with_suffix('.json')
    csv_write(cells_path, rows)
    csv_write(paired_path, paired['rows'])
    write(paired_json, paired)
    support = []
    support_paths = [args.result_root / 'campaign_freeze.json', campaign.PROTOCOL, Path(__file__), campaign.SINGLE, Path(campaign.__file__),
                     campaign.OLD_MANIFEST, OLD_TABLE,
                     ROOT / freeze['microtests']['path'], ROOT / freeze['build_identity']['path'],
                     ROOT / freeze['control_reuse_audit']['path']]
    support_paths.extend(p for p in [args.result_root / 'preflight_gate.json', args.result_root / 'preflight_execution_status.json',
                                   args.result_root / 'remaining_execution_status.json',
                                   ROOT / 'docs/baselines/hca_segment_identity_repair_semantics_20260906.md'] if p.exists())
    micro = read(ROOT / freeze['microtests']['path'])
    micro_parent = (ROOT / freeze['microtests']['path']).parent
    for support_root in {args.result_root / 'preflight', micro_parent}:
        support_paths.extend(p for p in support_root.rglob('*') if p.is_file()
                             and 'superseded_crlf_microtests' not in p.parts)
    # Keep the five slow-cleanup observations as explicitly excluded execution controls.
    old_runtime = micro_parent.parent
    support_paths.extend(p for p in [old_runtime / 'campaign_freeze.json', old_runtime / 'preflight_gate.json',
                                    old_runtime / 'preflight_execution_status.json'] if p.exists())
    for map_name, load, seed in campaign.PREFLIGHT:
        control_native = external.cell_dir(old_runtime, load, seed, map_name=map_name) / 'hca_segment_identity'
        support_paths.extend(p for p in (control_native / 'native_archive').glob('*') if p.is_file())
        support_paths.extend(p for p in [control_native / 'scratch_cleanup.json'] if p.exists())
    support_paths.extend(p for p in (old_runtime / 'diagnostics').rglob('*') if p.is_file())
    support_paths.extend(p for p in [
        ROOT / 'scripts/eval/diagnose_hca_segment_identity_release_delay.py',
        ROOT / 'docs/baselines/hca_segment_identity_release_delay_diagnostic_20260906.md',
        ROOT / 'docs/baselines/hca_segment_identity_paper_metric_clock_audit_20260906.md'
    ] if p.exists())
    support_paths.extend(ROOT / p for p in micro['old_control_identity']['source_files'])
    support_paths.extend([ROOT / 'scripts/eval/test_hca_segment_identity.py', ROOT / 'tests/java/HcaSegmentIdentityAudit.java'])
    support_paths.extend([ROOT / EQUIVALENCE_AUDITOR, ROOT / EQUIVALENCE_TEST])
    cleanup_validation = old_runtime / 'preflight/cleanup_revision_validation.json'
    if cleanup_validation.exists():
        support_paths.extend(ROOT / p for p in read(cleanup_validation)['tests']['files'])
    reservation_path = micro_parent / 'reservation_audit.json'
    if reservation_path.exists():
        reservation = read(reservation_path)
        require(reservation['status'] == 'PASS', 'shared-reservation supplement failed')
        support_paths.extend([ROOT / 'scripts/eval/audit_hca_segment_reservations.py', ROOT / reservation['audit_source']['path']])
        command = reservation['compile_command']
        class_root = relocated(command[command.index('-d') + 1])
        support_paths.extend(class_root / f['path'] for f in reservation['audit_classes'])
    for path in sorted(set(support_paths)):
        support.append(archive_file(path, args.evidence_root / support_destination(path)))
    build = read(ROOT / freeze['build_identity']['path'])
    build_files = []
    for kind, base, items in (('source', ROOT, build['source_files']),
                              ('classes', ROOT / freeze['classes_dir'], build['class_files'])):
        for item in items:
            source = base / item['path']
            require(sha(source) == item['sha256'], 'build file changed before archive')
            file = archive_file(source, args.evidence_root / 'frozen_build' / kind / item['path'])
            file['build_kind'], file['build_relative_path'] = kind, item['path']
            build_files.append(file)
    old_command = micro['old_control_identity']['command']
    old_classes = relocated(old_command[old_command.index('-d') + 1])
    micro_old_classes = []
    for name, digest in micro['old_control_identity']['class_files'].items():
        source = old_classes / name
        require(sha(source) == digest, 'microtest old control class identity changed')
        file = archive_file(source, args.evidence_root / 'microtest_old_classes' / name)
        file['class_relative_path'] = name
        micro_old_classes.append(file)
    manifest = {'schema': 'czr005.hca_segment_identity_campaign_archive.v1',
                'status': 'COMPLETE' if not missing and equivalence['status'] == 'PASS' else 'INCOMPLETE',
                'expected_cells': 180, 'observed_cells': len(rows),
                'new_hca_cells': len(rows) - 120, 'reused_control_cells': 120, 'missing_cells': missing, 'failures': [],
                'generator_sha256': sha(Path(__file__)), 'freeze_sha256': sha(args.result_root / 'campaign_freeze.json'),
                'source_prior_manifest_sha256': campaign.OLD_MANIFEST_SHA,
                'cells': records, 'support_files': support, 'build_files': build_files,
                'microtest_old_classes': micro_old_classes,
                'postprocessing_equivalence': equivalence,
                'source_sha256': build['source_sha256'], 'class_sha256': build['class_sha256'],
                'rejected_preflight_attempts': [{
                    'reason': 'Initial wrapper required exactly five columns; actual raw has two additional metadata columns.',
                    'stage': 'INPUT_PARSING_BEFORE_POPULATION_EXECUTION', 'rejected_cells': 4,
                    'successful_population_results': 0,
                    'evidence_root': relative(micro_parent / 'superseded_five_column_attempt_20260906'),
                    'old_source_and_microtests': relative(micro_parent / 'superseded_five_column_input')
                }],
                'nonfinal_postprocessing_controls': {
                    'runtime_root': relative(micro_parent.parent), 'cells': 5,
                    'reason': 'Replaced only Windows scratch-file cleanup; all 60 formal cells rerun with unchanged Java classes.',
                    'selection': 'No result-based selection; these five observations are excluded from the formal matrix.'},
                'tables': [campaign.bound_file(p) for p in (cells_path, paired_path, paired_json)],
                'evidence_limits': ['EBS legs retain the common independent scheduled-segment contract.',
                    'New HCA execution IDs may change HashMap traversal; this is a separately identified repair.',
                    'Archived G31 controls retain aggregate-only population evidence.',
                    'V5 is the previously user-adopted approximate DH reconstruction.',
                    'Old HCA accounting-anomalous observations are retained separately and not mixed into the main matrix.']}
    write(args.evidence_root / 'campaign_manifest.json', manifest)
    (args.evidence_root / 'README.md').write_text(
        '# HCA 段执行身份修复实验归档\n\n'
        '主矩阵包含新 HCA 60 格与字节绑定的既有 G31/V5 各 60 格。旧 HCA 的 43/60 异常不用于本矩阵。'
        '未完成结果保留，2×及未完成组的正式 THT 为 N/A。EBS 沿用共同独立 scheduled 段合同。\n\n'
        'campaign_manifest.json 将逐格指标绑定到原生事件、输入及源码/构建身份；既有控制引用同仓库上次的完整压缩归档。'
        '运行 `python scripts/eval/export_hca_segment_identity_campaign.py --verify-archive` 可在仓库副本复核，'
        '不启动模拟。归档校验通过的范围由 archive_verification.json 说明。\n', encoding='utf-8', newline='\n')
    return manifest


def verify_archive(root):
    from scripts.eval import run_hca_segment_identity as native_runner
    root = Path(root).resolve()
    manifest_path = root / 'campaign_manifest.json'
    manifest = read(manifest_path)
    require(manifest['status'] == 'COMPLETE' and manifest['observed_cells'] == 180 and manifest['new_hca_cells'] == 60,
            'portable final verification requires the full matrix')
    expected_keys = {(m, l, s, method) for m, l, s in campaign.keys() for method in METHODS}
    require(len(manifest['cells']) == 180 and {cell_key(c) for c in manifest['cells']} == expected_keys, 'archive coordinates differ')
    all_files = ([f for c in manifest['cells'] for f in c['files']] + manifest['support_files']
                 + manifest['build_files'] + manifest['microtest_old_classes'])
    checked = {}
    for file in all_files:
        path = relocated(file['archive_path'])
        if path not in checked:
            require(sha(path) == file['archive_sha256'], 'archive digest mismatch: ' + str(path))
            checked[path] = file['archive_sha256']
        require(checked[path] == file['archive_sha256'], 'same archive path has conflicting hashes')
    for file in manifest['tables']:
        require(sha(ROOT / file['path']) == file['sha256'], 'final table byte mismatch')
    authoritative_rows, authoritative_controls = previous_controls()
    old = {cell_key(c): c for c in authoritative_controls}
    for cell in manifest['cells']:
        if cell['method'] in (G31, V5):
            require(cell == old[cell_key(cell)], 'reused cell differs from independently bound previous archive')
    support = {f['source_path']: f for f in manifest['support_files']}
    freeze_files = [f for f in manifest['support_files'] if f['source_path'].endswith('/campaign_freeze.json')
                    and f['source_sha256'] == manifest['freeze_sha256']]
    require(len(freeze_files) == 1, 'missing/ambiguous final freeze support')
    freeze_file = freeze_files[0]
    require(freeze_file['source_sha256'] == manifest['freeze_sha256'], 'wrong archived campaign freeze')
    freeze = read(relocated(freeze_file['archive_path']))
    frozen_build = support[freeze['build_identity']['path']]
    build = read(relocated(frozen_build['archive_path']))
    require(freeze['method'] == HCA and freeze['cell_count'] == len(freeze['cells']) == 60
            and {(c['map'], c['load_factor'], c['seed']) for c in freeze['cells']} == set(campaign.keys()), 'invalid frozen coordinates')
    for field in ('protocol', 'runner', 'orchestrator', 'build_identity', 'microtests', 'previous_manifest', 'control_reuse_audit'):
        file = support[freeze[field]['path']]
        require(file['source_sha256'] == file['archive_sha256'] == freeze[field]['sha256'], 'archived freeze binding differs: ' + field)
    require(freeze['build_identity']['sha256'] == frozen_build['source_sha256'], 'microtest freeze refers to another build')
    micro = read(relocated(support[freeze['microtests']['path']]['archive_path']))
    require(micro['status'] == 'PASS' and micro['method'] == HCA and all(c['pass'] for c in micro['checks']), 'microtests did not pass')
    require({f['path']: f['sha256'] for f in build['source_files']} == micro['production_identity']['source_files'],
            'archived production source differs from tested implementation')
    require({f['path']: f['sha256'] for f in build['class_files']} == micro['production_identity']['class_files'],
            'archived production classes differ from tested implementation')
    require(support['scripts/eval/test_hca_segment_identity.py']['source_sha256'] == micro['test_driver_sha256']
            and support['tests/java/HcaSegmentIdentityAudit.java']['source_sha256'] == micro['java_audit_source_sha256'],
            'microtest driver/harness identity differs')
    micro_parent = Path(freeze['microtests']['path']).parent
    for case in micro['native_evidence']:
        for name, digest in case['files'].items():
            file = support[(micro_parent / name).as_posix()]
            require(file['source_sha256'] == file['archive_sha256'] == digest, 'microtest native fixture differs')
    for name, digest in micro['old_control_identity']['source_files'].items():
        require(support[name]['source_sha256'] == digest, 'old micro-control source differs')
    old_class_index = {f['class_relative_path']: f['archive_sha256'] for f in manifest['microtest_old_classes']}
    require(old_class_index == micro['old_control_identity']['class_files'], 'old micro-control classes differ')
    reservation_key = (micro_parent / 'reservation_audit.json').as_posix()
    if reservation_key in support:
        reservation = read(relocated(support[reservation_key]['archive_path']))
        require(reservation['status'] == reservation['observed']['status'] == 'PASS', 'reservation supplement failed')
        require(reservation['production_build_identity_sha256'] == frozen_build['source_sha256']
                and reservation['production_source_sha256'] == build['source_sha256']
                and reservation['production_class_sha256'] == build['class_sha256'], 'reservation supplement used another build')
        require(support[reservation['audit_source']['path']]['source_sha256'] == reservation['audit_source']['sha256']
                and support['scripts/eval/audit_hca_segment_reservations.py']['source_sha256'] == reservation['audit_generator_sha256'],
                'reservation test source differs')
        require(support[reservation['fixture']['path']]['source_sha256'] == reservation['fixture']['sha256'], 'reservation fixture differs')
        command = reservation['compile_command']
        class_root = relative(relocated(command[command.index('-d') + 1]))
        for item in reservation['audit_classes']:
            require(support[(Path(class_root) / item['path']).as_posix()]['source_sha256'] == item['sha256'],
                    'reservation test class differs')
        observed = reservation['observed']
        require(all(observed[k] for k in ('two_reservations_coexist', 'update_isolated_by_execution_id',
                    'unmodified_other_execution_object_and_interval', 'same_id_negative_control_replaces_prior_reservation',
                    'foreign_id_lookup_null')) and observed['collision_feasibility_tested'] is False, 'reservation scope/result differs')
    build_index = {(f['build_kind'], f['build_relative_path']): f for f in manifest['build_files']}
    require(len(build_index) == len(manifest['build_files']), 'duplicate build file')
    for kind, items, digest in (('source', build['source_files'], 'source_sha256'), ('classes', build['class_files'], 'class_sha256')):
        require(native_runner.set_sha(items) == build[digest] == manifest[digest], 'build aggregate mismatch')
        for item in items:
            file = build_index[(kind, item['path'])]
            require(file['source_sha256'] == file['archive_sha256'] == item['sha256'], 'archived build identity mismatch')
    equivalence_verification = verify_postprocessing_equivalence(manifest, support, freeze, freeze_file)
    scratch = ROOT / 'tmp'
    scratch.mkdir(exist_ok=True)
    recomputed = 0
    for cell in manifest['cells']:
        if cell['method'] != HCA:
            continue
        # Only this freshly allocated scratch directory is recursively cleaned.
        with tempfile.TemporaryDirectory(prefix='verify_hca_segment_', dir=scratch) as directory:
            work = Path(directory).resolve()
            require(work.is_relative_to(scratch.resolve()), 'scratch directory escaped workspace')
            native, workload = work / 'native', work / 'workload'
            native.mkdir()
            workload.mkdir()
            for file in cell['files']:
                source = relocated(file['archive_path'])
                name = source.name[:-3] if file['gzip'] else source.name
                target = (native if '/native/' in file['archive_path'] else workload) / name
                if file['gzip']:
                    with gzip.open(source, 'rb') as inp, target.open('wb') as out:
                        shutil.copyfileobj(inp, out)
                else:
                    shutil.copyfile(source, target)
                require(sha(target) == file['source_sha256'], 'restored native bytes differ')
            identity_path = workload / 'identity.json'
            identity = read(identity_path)
            identity_sha = sha(identity_path)
            value, status = read(native / 'normalized_result.json'), read(native / 'runner_status.json')
            require(cell_key(value) == cell_key(cell), 'native archive is from another cell')
            require(value['workload_identity_sha256'] == status['workload_identity_sha256'] == identity_sha,
                    'native run input identity differs')
            require(status['status'] == 'complete' and status['returncode'] == 0, 'native process failed')
            require(status['method'] == value['method'] == HCA, 'native method differs')
            require(status['source_sha256'] == build['source_sha256'] and status['class_sha256'] == build['class_sha256'],
                    'native executable identity differs')
            require(status['protocol_sha256'] == freeze['protocol']['sha256']
                    and status['python_runner_sha256'] == freeze['runner']['sha256'], 'native protocol/runner differs')
            require(sha(native / 'build_identity.json') == status['build_identity_sha256'] == frozen_build['source_sha256'],
                    'native class/source manifest differs')
            contract = value['normalization_contract']
            require(contract['reconstruction_java_source_sha256'] == build['source_sha256']
                    and contract['compiled_java_class_sha256'] == build['class_sha256']
                    and contract['build_identity_sha256'] == frozen_build['source_sha256']
                    and contract['protocol_sha256'] == freeze['protocol']['sha256'], 'normalized build/protocol differs')
            for field, name in (('raw', 'inputdata.txt'), ('canonical', 'canonical.jsonl'), ('map', 'map.txt')):
                identity[field + '_path'] = str(workload / name)
                require(identity[field + '_sha256'] == status['inputs'][field]['sha256'], 'consumed input bytes differ')
            derived = native_runner.recompute_population(identity, native, identity_sha)
            require(derived['metrics'] == value['metrics'] == cell['exported_metrics'], 'portable metrics differ')
            require(derived['full_population_complete'] == value['full_population_complete'], 'population qualification differs')
            audit = dict(derived['population_audit'], source_sha256=build['source_sha256'], class_sha256=build['class_sha256'])
            require(audit == value['population_audit'] == cell['diagnostic'], 'portable population audit differs')
            for key, name in (('segment_lifecycle', 'segment_lifecycle.csv'), ('raw_bag_timings', 'raw_bag_timings.csv')):
                regenerated = work / ('recomputed_' + name)
                native_runner.write_csv(regenerated, derived[key])
                require(sha(regenerated) == sha(native / name), 'portable per-segment/per-bag derivation differs')
            row = flat_hca(value)
            row['wall_seconds'] = status.get('wall_seconds')
            require(row == cell['table_row'], 'flat repaired HCA row differs')
        recomputed += 1
        if recomputed % 10 == 0:
            print(json.dumps({'recomputed_hca_cells': recomputed, 'total': 60}), flush=True)
    rows = [c['table_row'] for c in manifest['cells']]
    table = {cell_key(r): r for r in csv_rows(TABLES / 'hca_segment_identity_cells_20260906.csv')}
    require(len(table) == 180 and set(table) == expected_keys, 'table coordinates differ')
    for row in rows:
        for field, value in row.items():
            require(table[cell_key(row)].get(field, '') == ('' if value is None else str(value)), 'CSV cell differs: ' + field)
    paired_path = TABLES / 'hca_segment_identity_paired_20260906.json'
    paired = read(paired_path)
    require(paired_aggregate(rows, paired['bootstrap_replicates']) == paired, 'paired statistics differ')
    result = {'status': 'PASS', 'observed_cells': 180, 'new_hca_cells_recomputed': recomputed,
              'reused_control_cells_verified': 120, 'checked_unique_files': len(checked),
              'campaign_manifest_sha256': sha(manifest_path), 'verifier_sha256': sha(Path(__file__)),
              'original_absolute_paths_required': False, 'java_execution_required': False,
              'postprocessing_equivalence': equivalence_verification,
              'scope': 'Native HCA population/metrics recomputed; prior G31/V5 bound to previously verified archive hashes.',
              'not_claimed': 'Exhaustive physical safety or precedence-coupled EBS simulation; old G31 per-bag payload unavailable.'}
    write(root / 'archive_verification.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-root', type=Path, default=FINAL_RUNTIME)
    parser.add_argument('--evidence-root', type=Path, default=EVIDENCE)
    parser.add_argument('--require-complete', action='store_true')
    parser.add_argument('--verify-archive', action='store_true')
    parser.add_argument('--replicates', type=int, default=10000)
    args = parser.parse_args()
    result = verify_archive(args.evidence_root) if args.verify_archive else export(args)
    print(json.dumps({k: result.get(k) for k in ('status', 'observed_cells', 'new_hca_cells', 'reused_control_cells')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
