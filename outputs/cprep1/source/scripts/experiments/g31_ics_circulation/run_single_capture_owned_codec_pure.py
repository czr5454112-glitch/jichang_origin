"""Owned120 synthetic binding gate, no C load/model/native/saved raw read."""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET

from . import bounded_windows_job
from . import initial_owner_route_image as image

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
MODULE = 'scripts.experiments.g31_ics_circulation.run_single_capture_owned_codec_pure'
CANDIDATE = 'scripts.experiments.g31_ics_circulation.initial_owner_route_single_capture_owned_codec'
TEST = 'tests/test_g31_circulation_single_capture_owned_codec.py'
COUNT = 45
REFERENCES = (
    ('initial_owner_route_single_capture_campaign_prepare_001/campaign.json',
     '5ac870bdd01f09eefdf4b5e552238abc3a730745daeb04590acbb6ac3a539ddc', 190),
    ('complete_root_owned_decode_C_pair_prepare_001/plan.json',
     '947f7c33f012f4b4b3248cbbfe1cc037537340c3da89971160ec732d91bae00d', 153))


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok, reason):
    if not ok: raise ValueError('single_capture_owned_pure:' + reason)


def canonical_sources(files, root=ROOT):
    """Canonicalize before writing. Absolute and relative duplicate keys reject."""
    root = Path(root).resolve()
    result = {}
    for name, content in files.items():
        source = Path(name)
        source = (source if source.is_absolute() else root/source).resolve()
        require(source.is_relative_to(root), 'source_outside_root')
        relative = source.relative_to(root).as_posix()
        require(relative not in result, 'duplicate_canonical_source')
        result[relative] = content
    return result


def archive_target(output, relative):
    source_root = (Path(output)/'source').resolve()
    item = Path(relative)
    require(not item.is_absolute() and not item.drive and '..' not in item.parts,
        'archive_requires_canonical_relative_key')
    target = (source_root/item).resolve()
    require(target.is_relative_to(source_root) and target != (ROOT/item).resolve(),
        'archive_outside_output_or_live_source')
    return target


def frozen_references():
    result = []
    for name, digest, count in REFERENCES:
        path = OUT/name
        require(sha(path) == digest, 'frozen_reference_plan')
        plan = json.loads(path.read_text(encoding='utf8'))
        require(len(plan['source_sha256']) == count, 'frozen_reference_count')
        canonical = canonical_sources(plan['source_sha256'])
        require(len(canonical) == count, 'frozen_reference_unique_count')
        for original, value in plan['source_sha256'].items():
            source = Path(original)
            source = (source if source.is_absolute() else ROOT/source).resolve()
            saved = Path(plan['source_archive'][original])
            saved = (saved if saved.is_absolute() else path.parent/saved).resolve()
            require(saved.is_relative_to(path.parent.resolve()) and saved != source,
                'frozen_archive_not_independent')
            require(sha(source) == sha(saved) == value, 'frozen_current_or_archive_changed')
        result.append({'path': str(path), 'sha256': digest, 'sources': count})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args()
    output = args.output.resolve()
    if args.worker:
        require(sys.stdin.readline() == args.admission + '\n', 'worker_admission')
        import pytest
        return pytest.main(['-q', TEST, '--basetemp=' + str(output/'tmp'),
                           '--junitxml=' + str(output/'tests.xml')])
    output.mkdir(parents=True, exist_ok=False)
    frozen_before = frozen_references()
    # No bare helper imports. The complete defining-source import closure is
    # stored using canonical relative names, NEVER joined with absolute keys.
    files = canonical_sources(image.source_closure(ROOT, (MODULE, CANDIDATE, TEST[:-3].replace('/', '.'))))
    before = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    archive = {}
    for name, data in files.items():
        saved = archive_target(output, name)
        saved.parent.mkdir(parents=True, exist_ok=True)
        with saved.open('xb') as stream: stream.write(data)
        archive[name] = saved.relative_to(output).as_posix()
    token = uuid.uuid4().hex
    command = [sys.executable, '-m', MODULE, '--output', str(output), '--worker', '--admission', token]
    plan = {'schema': 'g31.single_capture.owned_codec.pure.v1', 'fixed_tests': COUNT,
        'source_sha256': before, 'source_archive': archive, 'frozen_references': frozen_before,
        'command': command, 'hard_seconds': 120., 'native_calls': 0, 'model_calls': 0,
        'C_loads': 0, 'saved_raw_reads': 0, 'bare_helper_imports': []}
    (output/'plan.json').write_text(json.dumps(plan, indent=2), encoding='utf8')
    remaining = 120. - (time.monotonic() - BOOT) - 1.
    if remaining <= 0:
        process = {'status': 'budget_exhausted_before_worker', 'exitcode': None}
    else:
        with (output/'worker.stdout.log').open('x', encoding='utf8') as out, \
             (output/'worker.stderr.log').open('x', encoding='utf8') as err:
            process = bounded_windows_job.run(command, timeout=remaining, admission=token,
                stdout=out, stderr=err, cwd=ROOT)
    xml = output/'tests.xml'
    rows = ET.parse(xml).getroot().findall('.//testcase') if xml.is_file() else []
    changed = [name for name, digest in before.items()
        if sha(ROOT/name) != digest or sha(archive_target(output, name)) != digest]
    original_same = frozen_references() == frozen_before
    bad = any(n.tag in ('failure', 'error', 'skipped') for row in rows for n in row)
    elapsed = time.monotonic() - BOOT
    passed = (process['status'] == 'exited' and process['exitcode'] == 0
        and len(rows) == COUNT and not bad and not changed and original_same and elapsed < 120.)
    report = {'status': 'passed' if passed else 'failed_or_unknown', 'process': process,
        'tests': len(rows), 'expected_tests': COUNT, 'XML_sha256': sha(xml) if xml.is_file() else None,
        'plan_sha256': sha(output/'plan.json'), 'source_changed': changed,
        'original190_and_sameC153_current_archive_unchanged': original_same,
        'source_count': len(before), 'native_calls': 0, 'model_calls': 0, 'C_loads': 0,
        'saved_raw_reads': 0, 'performance_runs': 0,
        'post_interpreter_before_receipt_seconds': elapsed,
        'outer_launcher_wall_required': True, 'synthetic_bindings_are_not_C_support_evidence': True}
    (output/'receipt.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report))
    return 0 if passed else 1


if __name__ == '__main__': raise SystemExit(main())
