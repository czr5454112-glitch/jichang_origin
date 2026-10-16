"""New owned120 synthetic campaign gate; no extension/model/native/raw load."""
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
from . import run_single_capture_owned_codec_pure as original
from . import initial_owner_route_single_capture_owned_codec_campaign as campaign
from . import verify_initial_owner_route_single_capture_owned_codec_campaign as verifier

ROOT, OUT = original.ROOT, original.OUT
MODULE = __package__+'.run_single_capture_owned_codec_campaign_pure'
TEST = 'tests/test_g31_circulation_single_capture_owned_codec_campaign.py'
COUNT = 38
sha, require = original.sha, original.require
REFERENCES = original.REFERENCES + (
    ('single_capture_owned_codec_source_prepare_001/plan.json',
     '63c2aab25f133ba72df76533a4f53b9fa0cfb962ca748c9dd970117d1479cb00', 156),)
frozen = campaign.integrated.private(original.frozen_references, {'REFERENCES': REFERENCES})


def files():
    return original.canonical_sources(original.image.source_closure(ROOT, (
        MODULE, __package__+'.initial_owner_route_single_capture_owned_codec_campaign',
        __package__+'.verify_initial_owner_route_single_capture_owned_codec_campaign',
        __package__+'.launch_initial_owner_route_single_capture_owned_codec_campaign',
        __package__+'.single_capture_owned_codec_runtime', TEST[:-3].replace('/', '.'))))


def write(path, value):
    with Path(path).open('x', encoding='utf8') as stream: json.dump(value, stream, indent=2, allow_nan=False)


def loaded(sources):
    result = {}
    for module in tuple(sys.modules.values()):
        raw = getattr(module, '__file__', None)
        if not raw: continue
        path = Path(raw).resolve()
        if path.is_relative_to(ROOT) and path.suffix == '.py':
            key = path.relative_to(ROOT).as_posix()
            require(sources.get(key) == sha(path), 'owned_campaign_pure_unlisted_import:' + key)
            result[key] = sources[key]
    require(not any(name == '_g31_complete_tree_normalizer' or 'czr005_circulation' in name
        for name in sys.modules), 'owned_campaign_pure_extension_import')
    return result


def child(output, token):
    require(sys.stdin.readline() == token+'\n', 'owned_campaign_pure_admission')
    plan = json.loads((output/'plan.json').read_text(encoding='utf8'))
    entry = loaded(plan['source_sha256'])
    import pytest
    result = pytest.main(['-q', TEST, '--basetemp='+str(output/'tmp'), '--junitxml='+str(output/'tests.xml')])
    exit_loaded = loaded(plan['source_sha256'])
    write(output/'child.json', {'pytest_exitcode': int(result), 'loaded_entry': entry,
        'loaded_exit': exit_loaded, 'campaign_source_proof': campaign.source_proof(),
        'saved_verifier_source_proof': verifier.source_proof(), 'native_calls': 0,
        'C_loads': 0, 'model_calls': 0, 'actual_saved_raw_reads': 0})
    return int(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--admission')
    args = parser.parse_args(); output = args.output.resolve()
    if args.worker: return child(output, args.admission)
    output.mkdir(parents=True, exist_ok=False)
    before_references = frozen(); source_files = files()
    sources = {name: hashlib.sha256(data).hexdigest() for name, data in source_files.items()}
    targets = {name: original.archive_target(output, name) for name in source_files}
    require(len(set(targets.values())) == len(targets), 'owned_campaign_pure_archive_unique')
    for name, data in source_files.items():
        targets[name].parent.mkdir(parents=True, exist_ok=True)
        with targets[name].open('xb') as stream: stream.write(data)
    token = uuid.uuid4().hex
    command = [sys.executable, '-m', MODULE, '--output', str(output), '--worker', '--admission', token]
    write(output/'plan.json', {'schema': 'g31.single_capture.owned_C_campaign.synthetic_pure.v1',
        'fixed_tests': COUNT, 'source_sha256': sources,
        'source_archive': {name: value.relative_to(output).as_posix() for name, value in targets.items()},
        'frozen_references': before_references, 'command': command, 'hard_seconds': 120.,
        'bare_helper_imports': [], 'native_calls': 0, 'model_calls': 0, 'C_loads': 0})
    remaining = 120.-(time.monotonic()-BOOT)-1.
    if remaining <= 0: process = {'status': 'budget_exhausted_before_worker', 'exitcode': None}
    else:
        with (output/'worker.stdout.log').open('x', encoding='utf8') as stdout, \
             (output/'worker.stderr.log').open('x', encoding='utf8') as stderr:
            process = bounded_windows_job.run(command, timeout=remaining, admission=token,
                stdout=stdout, stderr=stderr, cwd=ROOT)
    xml = output/'tests.xml'; rows = ET.parse(xml).getroot().findall('.//testcase') if xml.is_file() else []
    changed = [name for name, digest in sources.items()
        if sha(ROOT/name) != digest or sha(targets[name]) != digest]
    after_references = frozen()
    elapsed = time.monotonic()-BOOT
    passed = process['status'] == 'exited' and process['exitcode'] == 0 and len(rows) == COUNT \
        and not any(n.tag in ('failure','error','skipped') for row in rows for n in row) \
        and not changed and before_references == after_references and elapsed < 120.
    receipt = {'status': 'passed' if passed else 'failed_or_unknown', 'process': process,
        'plan_sha256': sha(output/'plan.json'), 'source_count': len(sources), 'source_changed': changed,
        'frozen_entry': before_references, 'frozen_exit': after_references,
        'tests': len(rows), 'expected_tests': COUNT, 'XML_sha256': sha(xml) if xml.is_file() else None,
        'child_sha256': sha(output/'child.json') if (output/'child.json').is_file() else None,
        'native_calls': 0, 'C_loads': 0, 'model_calls': 0, 'actual_saved_raw_reads': 0,
        'performance_runs': 0, 'post_interpreter_before_receipt_seconds': elapsed,
        'outer_full_startup_to_exit_clock_required': True,
        'synthetic_fixtures_do_not_establish_C_support': True}
    write(output/'receipt.json', receipt); print(json.dumps(receipt)); return 0 if passed else 1


if __name__ == '__main__': raise SystemExit(main())
