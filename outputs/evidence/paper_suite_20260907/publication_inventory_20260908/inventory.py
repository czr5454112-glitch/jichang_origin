"""Read-only, selected-scope publication inventory; no Git mutations or simulation.

Large native gzip files are statted, not decompressed or rehashed. Inputs, source,
and build files are hashed. Old tracked workload archives are compared to their
manifest byte hashes and Git index blob IDs. Writes only this new inventory.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
PLAN = ROOT / 'outputs/evidence/paper_suite_20260907/frozen_plan_v6/plan.json'
PRIOR = ROOT / 'outputs/evidence/hca_segment_identity_20260906/campaign_manifest.json'
PLAN_SHA = '7a4369b09efb8b2935a7197d6919375be730ffb5ee17a8cad55718fcdb262daf'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def walk(value):
    if isinstance(value, dict):
        if 'archive_path' in value and 'source_sha256' in value:
            yield value
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)


def command(args, data=None):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT)
    assert result.returncode in (0, 1), result.stderr.decode(errors='replace')
    return result.stdout


def main():
    destination = OUT / 'inventory.json'
    assert not destination.exists(), 'do not overwrite inventory'
    assert sha(PLAN.read_bytes()) == PLAN_SHA
    plan = read(PLAN)
    paths, aggregates, cells, declared, all_cell_files = {}, defaultdict(Counter), [], {}, []
    for cell in plan['cells']:
        output = Path(cell['output_dir'])
        norm = read(output / 'normalized_result.json')
        archives = norm.get('archives')
        if isinstance(archives, dict):
            for d in archives.values():
                declared[rel(output / d['path'])] = d['sha256']
        elif isinstance(archives, list):
            for d in archives:
                declared[rel(output / d['file'])] = d['sha256']
        manifest = output / 'native_archive/manifest.json'
        if manifest.exists():
            for d in read(manifest)['files']:
                declared[rel(output / d['path'])] = d['sha256']
        selected = []
        for p in output.rglob('*'):
            if not p.is_file():
                continue
            kind = 'gzip' if p.suffix == '.gz' else 'json' if p.suffix == '.json' else 'duplicate_plaintext_or_other'
            size = p.stat().st_size
            all_cell_files.append({'path': rel(p), 'bytes': size, 'kind': kind, 'cell_id': cell['cell_id']})
            aggregates[cell['method']][kind+'_count'] += 1
            aggregates[cell['method']][kind+'_bytes'] += size
            if kind != 'duplicate_plaintext_or_other':
                rp = rel(p)
                selected.append(rp)
                paths[rp] = {'path': rp, 'bytes': size, 'kind': kind,
                             'declared_archive_sha256': declared.get(rp),
                             'current_archive_bytes_rehashed': False if kind == 'gzip' else None}
        cells.append({'cell_id': cell['cell_id'], 'family': cell['family'], 'method': cell['method'],
                      'spec_path': rel(cell['spec_path']), 'spec_sha256': cell['spec_sha256'],
                      'runner_path': rel(cell['runner_path']), 'runner_sha256': cell['runner_sha256'],
                      'selected_files': selected})
    prior = read(PRIOR)
    descriptors = defaultdict(list)
    for d in walk(prior):
        descriptors[(str(Path(d['source_path']).resolve()), d['source_sha256'])].append(d)
    inputs, support = [], {}
    for bound in plan['workload_bindings']:
        identity = read(bound['path'])
        for role, p, expected in [('identity', bound['path'], bound['sha256']),
                                  *[(k, identity[k+'_path'], identity[k+'_sha256']) for k in ('raw', 'canonical', 'map')]]:
            p = Path(p)
            data = p.read_bytes()
            assert sha(data) == expected, (p, 'current input SHA differs')
            alternatives = descriptors.get((str(p.resolve()), expected), [])
            d = next((x for x in alternatives if 'feng_dh_boundary_clearance_v5_20260905' in x['archive_path']), alternatives[0] if alternatives else None)
            entry = {'role': role, 'map': identity['map'], 'load_factor': identity['load_factor'], 'seed': identity['seed'],
                     'source_path': rel(p), 'source_sha256': expected, 'source_bytes': len(data)}
            if d:
                ap = Path(d['archive_path'])
                if not ap.is_absolute():
                    ap = ROOT / ap
                archive = ap.read_bytes()
                assert sha(archive) == d['archive_sha256'], (ap, 'archive SHA differs')
                entry.update(archive_path=rel(ap), archive_sha256=d['archive_sha256'], archive_bytes=len(archive),
                             archive_manifest_source_sha_matches=True,
                             archive_git_blob_sha1=hashlib.sha1(b'blob '+str(len(archive)).encode()+b'\0'+archive).hexdigest(),
                             archive_decompressed_in_this_inventory=False)
            inputs.append(entry)
    for cell in plan['cells']:
        spec = read(cell['spec_path'])
        for role, p in [('runner', cell['runner_path']), ('spec', cell['spec_path']),
                        ('protocol', spec['protocol_path']), ('map_profile', spec.get('map_profile_path')),
                        ('native_binary', spec.get('binary_path'))]:
            if p:
                fp = Path(p)
                support[rel(fp)] = {'path': rel(fp), 'role': role, 'sha256': sha(fp.read_bytes()), 'bytes': fp.stat().st_size}
        if 'classes_dir' in spec:
            bi = read(Path(cell['output_dir']) / 'build_identity.json')
            assert sha((Path(cell['output_dir']) / 'build_identity.json').read_bytes()) == spec['build_identity_sha256']
            class_files = bi['class_files']
            class_pairs = [(r['path'], r['sha256']) for r in class_files] if isinstance(class_files, list) else class_files.items()
            for name, expected in class_pairs:
                cp = Path(spec['classes_dir']) / name
                rp = rel(cp)
                if rp not in support:
                    data = cp.read_bytes()
                    assert sha(data) == expected
                    support[rp] = {'path': rp, 'role': 'native_class', 'sha256': expected, 'bytes': len(data)}
            source_files = bi['source_files']
            if isinstance(source_files, list):
                source_pairs = [(ROOT / r['path'], r['sha256']) for r in source_files]
            else:
                source_pairs = [(ROOT / 'benchmarks/java/feng_cie_dh_paper_suite_v6/App' / n, h) for n, h in source_files.items()]
            for p, expected in source_pairs:
                rp = rel(p)
                if rp not in support:
                    data = p.read_bytes()
                    assert sha(data) == expected
                    support[rp] = {'path': rp, 'role': 'native_java_source', 'sha256': expected, 'bytes': len(data)}
    candidates = sorted(set(paths) | set(support) | {r['source_path'] for r in inputs} | {r['archive_path'] for r in inputs if 'archive_path' in r})
    ignored = set(command(['git', 'check-ignore', '--no-index', '-z', '--stdin'], b'\0'.join(p.encode() for p in candidates)+b'\0').decode().split('\0'))
    roots = ['outputs/runtime/feng_paper_suite_20260907', 'outputs/evidence/paper_suite_20260907',
             'outputs/evidence/feng_dh_boundary_clearance_v5_20260905', 'outputs/evidence/g31_fault_potential_repair_20260907',
             'data/processed/workloads/cie_external_robustness', 'build/hca_paper_suite_v3_20260907',
             'build/feng_dh_paper_suite_v6_20260907', 'benchmarks/java/hca_paper_suite_v3',
             'benchmarks/java/feng_cie_dh_paper_suite_v6', 'scripts/eval', 'configs/eval',
             'legacy/jichang_origin_readonly', 'data/processed/maps']
    indexed = {}
    for line in command(['git', 'ls-files', '--stage', '-z', '--', *roots]).decode().split('\0'):
        if line:
            info, path = line.split('\t', 1)
            indexed[path] = info.split()[1]
    for row in list(paths.values()) + list(support.values()):
        row.update(ignored_by_current_rules=row['path'] in ignored, tracked_in_index=row['path'] in indexed)
    for row in inputs:
        row.update(source_ignored_by_current_rules=row['source_path'] in ignored, source_tracked_in_index=row['source_path'] in indexed)
        if 'archive_path' in row:
            row['archive_tracked_in_index'] = row['archive_path'] in indexed
            row['archive_current_bytes_equal_index_blob'] = indexed.get(row['archive_path']) == row['archive_git_blob_sha1']
    reused = [r for r in inputs if r['role'] != 'map']
    assert len(reused) == 120 and all(r.get('archive_current_bytes_equal_index_blob') for r in reused), 'workload archive missing/different in index'
    totals = Counter()
    for a in aggregates.values():
        totals.update(a)
    result = {'schema': 'czr005.paper_suite.publication_inventory.v1', 'status': 'INVENTORY_COMPLETE_NOT_PUBLICATION_VERIFICATION',
              'observed_at_utc': datetime.now(timezone.utc).isoformat(), 'plan_path': rel(PLAN), 'plan_sha256': PLAN_SHA,
              'source_sha256': sha(Path(__file__).read_bytes()), 'expected_cells': 576,
              'cell_counts_by_method': dict(Counter(c['method'] for c in cells)), 'totals': dict(totals),
              'aggregates_by_method': {k: dict(v) for k, v in aggregates.items()},
              'selected_cell_file_count': len(paths), 'selected_cell_bytes': sum(r['bytes'] for r in paths.values()),
              'largest_gzip_bytes': max(r['bytes'] for r in paths.values() if r['kind']=='gzip'),
              'reusable_tracked_workload_file_count': 120, 'workload_archive_unique_bytes': sum({r['archive_path']:r['archive_bytes'] for r in reused}.values()),
              'inputs': inputs, 'support': list(support.values()), 'cells': cells, 'selected_cell_files': list(paths.values()),
              'all_cell_files_for_optional_exact_directory_restore': all_cell_files,
              'read_only_git_commands': ['check-ignore --no-index --stdin', 'ls-files --stage'],
              'large_native_archives_decompressed_or_hashed': 0,
              'limitations': ['Selected native gz files were statted; their declared hashes are not a fresh full-archive byte verification.',
                             'Git tracked status is a read-only index snapshot, not confirmation of remote publication.',
                             'Frozen plans/specs/status retain absolute original paths; arbitrary-clone replay needs an explicit SHA-bound relative-path remapping layer.',
                             'All576 cell result directories plus protocol/spec ancestry, outer receipts, preflight/freeze/source build evidence, and prior same-byte workload archives are required; selected_cell_files alone is not a complete dependency closure.',
                             'Source documents and JDK/Python installations are provenance/environment dependencies, not native result files to silently bundle.']}
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','expected_cells','totals','selected_cell_file_count','selected_cell_bytes','reusable_tracked_workload_file_count','workload_archive_unique_bytes')},ensure_ascii=False))


if __name__ == '__main__':
    main()
