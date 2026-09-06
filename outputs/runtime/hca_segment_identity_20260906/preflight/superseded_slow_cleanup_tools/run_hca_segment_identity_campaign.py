"""Freeze and execute the complete HCA execution-identity repair campaign."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_cie_external_baseline_robustness as external

METHOD = "HCA_SEGMENT_IDENTITY_V1"
OUT = ROOT / "outputs/runtime/hca_segment_identity_20260906"
PROTOCOL = ROOT / "docs/baselines/hca_segment_identity_campaign_protocol_20260906.md"
SINGLE = ROOT / "scripts/eval/run_hca_segment_identity.py"
OLD_MANIFEST = ROOT / "outputs/evidence/feng_dh_boundary_clearance_v5_20260905/campaign_manifest.json"
OLD_MANIFEST_SHA = "133808d1c2fb94149f2ec5e717d14f7384faea957ab3386deedabfef5c8f8f40"
PREFLIGHT = (('nanning', 1.0, 155921), ('nanning', 1.0, 181081),
             ('nanning', 1.0, 232003), ('map2', 1.75, 104729), ('nanning', 2.0, 104729))


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    external._atomic_json(Path(path), value)


def now():
    return datetime.now(timezone.utc).isoformat()


def keys():
    return [(m, l, s) for m in external.MAPS for l in external.LOAD_FACTORS for s in external.SEEDS]


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def bound_file(path):
    return {'path': relative(path), 'sha256': sha(path)}


def prepare(args):
    require(not (args.result_root / 'campaign_freeze.json').exists(), 'freeze already exists; use existing plan')
    require(sha(OLD_MANIFEST) == OLD_MANIFEST_SHA, 'previous complete matrix changed')
    micro = read(args.microtests)
    require(micro['status'] == 'PASS', 'native microtests must pass first')
    build = read(args.build_identity)
    require(micro['method'] == build['method'] == METHOD, 'microtest/production method differs')
    require({f['path']: f['sha256'] for f in build['source_files']} == micro['production_identity']['source_files'],
            'production source bytes differ from tested implementation')
    require({f['path']: f['sha256'] for f in build['class_files']} == micro['production_identity']['class_files'],
            'production classes differ from tested implementation')
    controls_path = args.result_root / 'preflight/control_reuse_audit.json'
    controls = read(controls_path)
    require(controls['status'] == 'PASS' and controls['reused_G31_V5_cells'] == 120
            and controls['previous_manifest_sha256'] == OLD_MANIFEST_SHA, 'control reuse is not validated')
    cells = []
    for m, l, s in keys():
        ip = external.cell_dir(external.DEFAULT_WORKLOAD_ROOT, l, s, map_name=m) / 'identity.json'
        external.audit_cell(ip)
        identity = read(ip)
        output = external.cell_dir(args.result_root, l, s, map_name=m) / 'hca_segment_identity'
        command = [sys.executable, str(SINGLE), 'run', '--identity', str(ip), '--output', str(output),
                   '--classes-dir', str(args.classes_dir), '--java', args.java, '--javac', args.javac,
                   '--skip-compile']
        cells.append({'map': m, 'load_factor': l, 'seed': s, 'identity': bound_file(ip),
                      'raw_sha256': identity['raw_sha256'], 'canonical_sha256': identity['canonical_sha256'],
                      'map_sha256': identity['map_sha256'], 'output': relative(output), 'command': command})
    value = {'schema': 'czr005.hca_segment_identity_campaign_freeze.v1', 'created_at': now(),
             'method': METHOD, 'cell_count': 60, 'workers': args.workers, 'host': platform.platform(),
             'protocol': bound_file(PROTOCOL), 'runner': bound_file(SINGLE),
             'orchestrator': bound_file(Path(__file__)), 'build_identity': bound_file(args.build_identity),
             'microtests': bound_file(args.microtests), 'previous_manifest': bound_file(OLD_MANIFEST),
             'control_reuse_audit': bound_file(controls_path),
             'classes_dir': relative(args.classes_dir), 'java': args.java, 'javac': args.javac,
             'fixed_horizon_seconds': external.FIXED_HORIZON_SECONDS,
             'new_hca_cells': 60, 'reused_g31_v5_cells': 120,
             'preflight_keys': list(PREFLIGHT), 'cells': cells,
             'selection_rule': 'IDENTITY_AND_ACCOUNTING_CORRECTNESS_NOT_RELATIVE_PERFORMANCE',
             'ebs_contract': 'INDEPENDENT_CANONICAL_SCHEDULED_SEGMENTS_NO_NEW_PRECEDENCE_WAIT'}
    write(args.result_root / 'campaign_freeze.json', value)
    return value


def check_freeze(args):
    freeze = read(args.result_root / 'campaign_freeze.json')
    require(freeze['method'] == METHOD and freeze['cell_count'] == 60, 'wrong freeze')
    require(len(freeze['cells']) == 60 and {(c['map'], c['load_factor'], c['seed']) for c in freeze['cells']} == set(keys()),
            'incomplete/duplicate freeze coordinates')
    for name in ('protocol', 'runner', 'orchestrator', 'build_identity', 'microtests', 'previous_manifest', 'control_reuse_audit'):
        item = freeze[name]
        require(sha(ROOT / item['path']) == item['sha256'], name + ' changed after freeze')
    return freeze


def load_completed(cell):
    path = ROOT / cell['output'] / 'normalized_result.json'
    value = read(path)
    require(value['status'] == 'COMPLETE' and value['method'] == METHOD, 'not a completed repaired HCA record')
    for name in ('map', 'load_factor', 'seed'):
        require(value[name] == cell[name], 'cell coordinate mismatch: ' + name)
    require(value['population_audit']['status'] == 'PASS', 'population audit did not pass')
    require(value['workload_identity_sha256'] == cell['identity']['sha256'], 'input identity drift')
    require(value['fixed_horizon_seconds'] == external.FIXED_HORIZON_SECONDS, 'horizon drift')
    return value


def run_cell(cell):
    output = ROOT / cell['output']
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.parent / 'hca_campaign.lock'
    with lock.open('x', encoding='utf-8') as handle:
        handle.write(str(os.getpid()))
    try:
        require(sha(ROOT / cell['identity']['path']) == cell['identity']['sha256'], 'workload changed before launch')
        started = now()
        with (output.parent / 'orchestration_stdout.txt').open('ab') as stdout, \
                (output.parent / 'orchestration_stderr.txt').open('ab') as stderr:
            process = subprocess.run(cell['command'], cwd=ROOT, stdout=stdout, stderr=stderr)
        require(process.returncode == 0, f"native runner failed {process.returncode}: {output}")
        value = load_completed(cell)
        return {'map': cell['map'], 'load_factor': cell['load_factor'], 'seed': cell['seed'],
                'status': 'COMPLETE', 'started_at': started, 'finished_at': now(),
                'full_population_complete': value['full_population_complete'],
                'normalized': bound_file(output / 'normalized_result.json')}
    finally:
        lock.unlink()


def run(args):
    freeze = check_freeze(args)
    if args.phase == 'remaining':
        gate = read(args.result_root / 'preflight_gate.json')
        require(gate['status'] == 'PASS' and gate['freeze_sha256'] == sha(args.result_root / 'campaign_freeze.json'),
                'full-population preflight must pass before remaining cells')
        for cell in freeze['cells']:
            if (cell['map'], cell['load_factor'], cell['seed']) in PREFLIGHT:
                load_completed(cell)
    selected = [c for c in freeze['cells'] if ((c['map'], c['load_factor'], c['seed']) in PREFLIGHT) == (args.phase == 'preflight')]
    selected.sort(key=lambda c: (0 if c['map'] == 'map2' else 1, c['load_factor'], c['seed']))
    status_path = args.result_root / (args.phase + '_execution_status.json')
    value = {'schema': 'czr005.hca_segment_identity_campaign_execution.v1', 'status': 'RUNNING',
             'phase': args.phase, 'started_at': now(), 'cell_count': len(selected),
             'workers': args.workers, 'freeze_sha256': sha(args.result_root / 'campaign_freeze.json'),
             'results': [], 'failures': []}
    write(status_path, value)
    pending = iter(selected)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {}
        for _ in range(args.workers):
            cell = next(pending, None)
            if cell:
                futures[pool.submit(run_cell, cell)] = cell
        while futures:
            finished, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in finished:
                cell = futures.pop(future)
                try:
                    result = future.result()
                    value['results'].append(result)
                    print(json.dumps(result), flush=True)
                except Exception as exc:
                    error = {'map': cell['map'], 'load_factor': cell['load_factor'], 'seed': cell['seed'],
                             'error': type(exc).__name__ + ': ' + str(exc)}
                    value['failures'].append(error)
                    print(json.dumps(error), flush=True)
            if not value['failures']:
                for _ in finished:
                    cell = next(pending, None)
                    if cell:
                        futures[pool.submit(run_cell, cell)] = cell
            write(status_path, value)
    value['status'] = 'COMPLETE' if len(value['results']) == len(selected) and not value['failures'] else 'FAILED'
    value['finished_at'] = now()
    write(status_path, value)
    if args.phase == 'preflight' and value['status'] == 'COMPLETE':
        write(args.result_root / 'preflight_gate.json', {'status': 'PASS', 'passed_at': now(),
              'freeze_sha256': value['freeze_sha256'], 'execution_status': bound_file(status_path),
              'cases': value['results'], 'gate_basis': 'IDENTITY_AND_SEGMENT_ACCOUNTING_NOT_WINNING_OR_FULL_COMPLETION'})
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=('prepare', 'run'))
    p.add_argument('--phase', choices=('preflight', 'remaining'), default='preflight')
    p.add_argument('--result-root', type=Path, default=OUT)
    p.add_argument('--classes-dir', type=Path, default=ROOT / 'build/hca_segment_identity_v1')
    p.add_argument('--build-identity', type=Path, default=ROOT / 'build/hca_segment_identity_v1/build_identity.json')
    p.add_argument('--microtests', type=Path, default=OUT / 'preflight/microtests.json')
    p.add_argument('--java', default='C:/PROGRAMING/jdk-18/bin/java.exe')
    p.add_argument('--javac', default='C:/PROGRAMING/jdk-18/bin/javac.exe')
    p.add_argument('--workers', type=int, default=4)
    args = p.parse_args()
    args.result_root = args.result_root.resolve()
    args.classes_dir = args.classes_dir.resolve()
    require(1 <= args.workers <= 4, 'workers must be 1..4')
    require(args.result_root.is_relative_to(ROOT / 'outputs/runtime') and args.result_root.name.startswith('hca_segment_identity_'),
            'use an isolated HCA repair output directory')
    result = prepare(args) if args.stage == 'prepare' else run(args)
    print(json.dumps({'stage': args.stage, 'status': result.get('status', 'FROZEN'), 'cells': result['cell_count']}), flush=True)
    return 0 if result.get('status') != 'FAILED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
