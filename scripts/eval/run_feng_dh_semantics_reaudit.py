"""Isolated, identity-bound map2-only semantic probes; never launches extensions."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / 'docs/baselines/feng_dh_map2_reaudit_protocol_20260905.md'
EXPECTED = {
    'map': ('legacy/jichang_origin_readonly/map2.txt', '55f578cb4b8fcc61f5b13963fcb8546aca91e517ea6f8ff4a7361670f1b03f8f'),
    'input': ('legacy/jichang_origin_readonly/inputdata.txt', '0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87'),
    'schedule': ('data/processed/feng_table53_segment_schedule.csv', 'a3db0d3f495870437414af0b46a0a140f7cafe8111b40222ca59fcd78e7d4d86'),
}
TARGET = {'min': 213.3, 'mean': 265.592131481, 'p95': 336.9, 'p99': 384.595, 'max': 517.2}
TOLERANCE = {'min': .05, 'mean': .05, 'p95': .10, 'p99': .10, 'max': .10}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(directory: Path, pattern: str) -> dict:
    return {p.relative_to(directory).as_posix(): sha(p) for p in sorted(directory.rglob(pattern))}


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def stats(values: list[float]) -> dict:
    values = sorted(values)
    def percentile(p: float) -> float:
        x = (len(values) - 1) * p
        i = int(x)
        return values[i] + (values[min(i + 1, len(values) - 1)] - values[i]) * (x - i)
    return {'min': values[0], 'mean': sum(values) / len(values),
            'p95': percentile(.95), 'p99': percentile(.99), 'max': values[-1]}


def audit(output: Path) -> dict:
    bags, segments = rows(output / 'bags.csv'), rows(output / 'segments.csv')
    schedule = rows(ROOT / EXPECTED['schedule'][0])
    expected_legs = {(int(r['raw_bag_id']), int(r['segment_id'])): r for r in schedule}
    actual_legs = {(int(r['raw_bag_id']), int(r['segment_id'])): r for r in segments}
    counts = Counter(int(r['raw_bag_id']) for r in segments)
    checks = {
        'exact_bag_population': len(bags) == 28506 and {int(r['raw_bag_id']) for r in bags} == set(range(28506)),
        'exact_segment_population': len(segments) == 43603 and set(actual_legs) == set(expected_legs),
        'all_raw_complete': all(r['complete'] == 'true' for r in bags),
        'all_segments_complete': all(r['status'] == 'COMPLETED' for r in segments),
        'segment_multiplicity': Counter(counts.values()) == {1: 13409, 2: 15097},
    }
    mismatch = []
    tht = defaultdict(float)
    for key, r in actual_legs.items():
        s = expected_legs.get(key)
        if not s or any(r[k] != s[k] for k in ('start', 'goal')) or abs(float(r['release_seconds']) - float(s['scheduled_release_seconds'])) > 1e-7:
            mismatch.append(key)
            continue
        if r['status'] == 'COMPLETED':
            value = float(r['completion_time_seconds']) - float(s['scheduled_release_seconds'])
            tht[key[0]] += value
            if abs(value - float(r['table53_scheduled_interval_seconds'])) > 1e-6:
                mismatch.append(key)
    checks['shared_D_and_leg_THT_exact'] = not mismatch
    checks['bag_THT_equals_sum_E_minus_D'] = all(
        abs(tht[int(r['raw_bag_id'])] - float(r['table53_scheduled_interval_seconds'])) < 1e-6
        for r in bags if r['complete'] == 'true')
    timing = stats(list(tht.values())) if all(checks.values()) else None
    relative = {k: timing[k] / TARGET[k] - 1 for k in TARGET} if timing else None
    numerical = bool(relative and all(abs(relative[k]) <= TOLERANCE[k] for k in TARGET))
    return {'schema': 'feng.dh.map2_reaudit.v1', 'checks': checks,
            'completed_raw_bags': sum(r['complete'] == 'true' for r in bags),
            'completed_segments': sum(r['status'] == 'COMPLETED' for r in segments),
            'THT_seconds_shared_D': timing, 'historical_reference_seconds': TARGET,
            'relative_error': relative, 'tolerances': TOLERANCE,
            'numerical_gate_pass': numerical,
            'numerical_gate_role': 'diagnostic_only_after_user_softened_acceptance',
            'extension_authorized_by_this_runner': False,
            'note': 'User accepts close or moderately slower results; thresholds are diagnostic. Advancement requires combined semantic, fixture, and historical-signature review.'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--source-dir', required=True, type=Path)
    parser.add_argument('--protocol', type=Path, default=PROTOCOL)
    parser.add_argument('--timeout-seconds', type=int, default=1800)
    args = parser.parse_args()
    if not args.name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for c in args.name):
        parser.error('name must be a simple lowercase artifact label')
    source = args.source_dir.resolve()
    source.relative_to(ROOT)
    output = ROOT / 'outputs/runtime/feng_dh_semantics_reaudit_20260905' / args.name
    classes = ROOT / 'build/feng_dh_semantics_reaudit_20260905' / args.name
    if output.exists() or classes.exists():
        raise RuntimeError('isolated run/build already exists; use a new explicit name')
    paths = {k: ROOT / value[0] for k, value in EXPECTED.items()}
    for k, path in paths.items():
        if sha(path) != EXPECTED[k][1]:
            raise RuntimeError(f'protected {k} identity mismatch')
    sources = sorted(source.glob('*.java'))
    if len(sources) != 5:
        raise RuntimeError('expected exactly five isolated production Java classes')
    output.mkdir(parents=True)
    classes.mkdir(parents=True)
    before = identity(source, '*.java')
    metadata = {'started_at': datetime.now(timezone.utc).isoformat(),
                'protocol_path': str(args.protocol.resolve()),
                'protocol_sha256': sha(args.protocol), 'source_dir': str(source),
                'source_files': before, 'inputs': {k: {'path': str(v), 'sha256': sha(v)} for k, v in paths.items()}}
    compile_command = [shutil.which('javac') or 'javac', '-encoding', 'UTF-8', '-d', str(classes), *map(str, sources)]
    subprocess.run(compile_command, check=True, capture_output=True)
    metadata['class_files'] = identity(classes, '*.class')
    command = [shutil.which('java') or 'java', '-Djava.awt.headless=true', '-cp', str(classes),
               'App.FengDhBenchmark', 'run', '--output', str(output), '--alpha', '0.4', '--beta', '0.8',
               '--limit', '0', '--workload-scale', '1', '--seed', '0', '--horizon-seconds', '0',
               '--trace-sample-modulo', '0', '--formal-timing-eligible', 'true']
    for k, path in paths.items():
        command.extend(['--' + k, str(path)])
    metadata.update({'compile_command': compile_command, 'command': command, 'status': 'RUNNING'})
    write_json(output / 'run_identity.json', metadata)
    started = time.monotonic()
    try:
        with (output / 'stdout.txt').open('w', encoding='utf-8') as stdout, (output / 'stderr.txt').open('w', encoding='utf-8') as stderr:
            result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=args.timeout_seconds)
        metadata.update({'returncode': result.returncode, 'status': 'COMPLETE' if result.returncode == 0 else 'FAILED'})
        if result.returncode != 0:
            raise RuntimeError((output / 'stderr.txt').read_text(encoding='utf-8'))
        if identity(source, '*.java') != before or identity(classes, '*.class') != metadata['class_files']:
            raise RuntimeError('source/class changed during execution')
        report = audit(output)
        write_json(output / 'population_and_gate.json', report)
        for filename in ('bags.csv', 'segments.csv'):
            raw = (output / filename).read_bytes()
            (output / (filename + '.gz')).write_bytes(gzip.compress(raw, mtime=0))
        metadata['outputs'] = {p.name: sha(p) for p in output.iterdir() if p.is_file() and p.name != 'run_identity.json'}
        print(json.dumps({'run': args.name, **report}, ensure_ascii=False), flush=True)
    except Exception as error:
        metadata.update({'status': 'FAILED', 'error': str(error)})
        raise
    finally:
        metadata['wall_seconds'] = time.monotonic() - started
        metadata['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output / 'run_identity.json', metadata)


if __name__ == '__main__':
    main()
