"""Bind the two-cell probe and verify original/source/input preservation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_hca_time_label_repair_v2 as engine

PREFLIGHT = ROOT / 'outputs/runtime/hca_time_label_repair_v2_20260906/preflight'
FREEZE = PREFLIGHT / 'two_cell_freeze.json'
CLASSES = ROOT / 'build/hca_time_label_repair_v2_20260906'
JAVA = r'C:\PROGRAMING\jdk-18\bin\java.exe'
JAVAC = r'C:\PROGRAMING\jdk-18\bin\javac.exe'


def record(path: Path) -> dict:
    path = path.resolve(strict=True)
    return {'path': str(path), 'sha256': engine.sha(path), 'size_bytes': path.stat().st_size}


def verify(value: dict) -> None:
    for group in ('frozen_files', 'protected_files'):
        for row in value[group]:
            engine.require(record(Path(row['path'])) == row, f"changed frozen/protected file: {row['path']}")
    engine.verify_build(CLASSES, JAVA, JAVAC)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        value = engine.read_json(FREEZE)
        verify(value)
        print(json.dumps({'status': 'PASS', 'freeze_sha256': engine.sha(FREEZE),
                          'protected_files': len(value['protected_files']), 'frozen_files': len(value['frozen_files'])}))
        return
    engine.require(not FREEZE.exists(), 'freeze already exists; use --verify')
    micro = engine.read_json(PREFLIGHT / 'microtests.json')
    engine.require(micro['status'] == 'PASS' and micro['java_checks_total'] == 14, 'microtests not passed')
    engine.require(micro['driver_sha256'] == engine.sha(ROOT / 'scripts/eval/test_hca_time_label_repair_v2.py'), 'microtest driver drift')
    engine.require(micro['test_source_sha256'] == engine.sha(ROOT / 'tests/java/hca_time_label_repair_v2/HcaTimeLabelAudit.java'), 'microtest source drift')
    build = engine.verify_build(CLASSES, JAVA, JAVAC)
    for row in micro['runs']['repaired']['core_classes']['files']:
        engine.require(engine.sha(CLASSES / row['path']) == row['sha256'], 'production core differs from tested core')
    copy = engine.read_json(PREFLIGHT / 'source_copy_identity.json')
    original = Path(copy['original_source_directory'])
    legacy = ROOT / 'legacy/jichang_origin_readonly/src'
    protected = [*original.rglob('*.java'), *legacy.rglob('*.java'),
        ROOT / 'benchmarks/java/HcaSegmentIdentityBenchmark.java',
        ROOT / 'scripts/eval/run_hca_segment_identity.py',
        ROOT / 'outputs/tables/hca_segment_identity_cells_20260906.csv',
        ROOT / 'outputs/evidence/hca_segment_identity_20260906/campaign_manifest.json',
        ROOT / 'outputs/evidence/feng_java_consistency_recheck_20260906/manifest.json',
        ROOT / 'build/hca_segment_identity_v1_input_compat/build_identity.json',
        *(ROOT / 'build/hca_segment_identity_v1_input_compat').rglob('*.class')]
    frozen = [*engine.source_files(), *CLASSES.rglob('*.class'), CLASSES / engine.BUILD_NAME,
        Path(__file__), Path(engine.__file__), engine.PROTOCOL,
        ROOT / 'scripts/eval/test_hca_time_label_repair_v2.py',
        ROOT / 'tests/java/hca_time_label_repair_v2/HcaTimeLabelAudit.java',
        *PREFLIGHT.iterdir(), ROOT / 'tmp/hca_time_label_repair_v2_controls_20260906.json']
    # Include every loaded repository Python helper actually imported by the runner.
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename and Path(filename).suffix == '.py' and Path(filename).resolve().is_relative_to(ROOT):
            frozen.append(Path(filename))
    cells = []
    for map_name in ('map2', 'nanning'):
        identity_path = ROOT / 'data/processed/workloads/cie_external_robustness' / (map_name + '_1p00x') / 'seed_104729/identity.json'
        identity_path, identity = engine.external._identity_payload(identity_path)
        engine.require(identity['raw_bag_count'] == 28506 and identity['segment_count'] == 43602, 'population drift')
        frozen.extend([identity_path, *[Path(identity[k + '_path']) for k in ('raw', 'canonical', 'map')]])
        output = ROOT / 'outputs/runtime/hca_time_label_repair_v2_20260906' / (map_name + '_1p00x') / 'seed_104729/hca_time_label_repair_v2'
        engine.require(not output.exists(), 'freeze must precede the first simulation')
        cells.append({'map': map_name, 'load_factor': 1.0, 'seed': 104729,
                      'identity': record(identity_path), 'output': str(output),
                      'command': engine.java_run_command(identity, output, CLASSES, JAVA)})
    value = {'schema': 'czr005.hca_time_label_repair_v2.two_cell_freeze.v1',
        'created_at': datetime.now(timezone.utc).isoformat(), 'method': engine.METHOD,
        'scope': 'EXACTLY_TWO_FULL_SIMULATIONS_NO_EXTRA_LOADS_OR_SEEDS', 'cells': cells,
        'frozen_files': [record(p) for p in sorted(set(frozen)) if p.is_file()],
        'protected_files': [record(p) for p in sorted(set(protected))],
        'build_source_sha256': build['source_sha256'], 'build_class_sha256': build['class_sha256']}
    verify(value)
    engine.write_json(FREEZE, value)
    print(json.dumps({'status': 'FROZEN', 'freeze_sha256': engine.sha(FREEZE),
                      'protected_files': len(value['protected_files']), 'frozen_files': len(value['frozen_files'])}))


if __name__ == '__main__':
    main()
