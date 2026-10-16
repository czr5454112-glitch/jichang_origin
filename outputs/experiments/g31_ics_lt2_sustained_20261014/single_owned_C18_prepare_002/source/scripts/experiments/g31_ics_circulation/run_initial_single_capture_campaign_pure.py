"""Owned120 source/wiring tests only; no native, predictor or C extension."""
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

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
MODULE = __package__+'.run_initial_single_capture_campaign_pure'
TEST = 'tests/test_g31_circulation_initial_owner_route_single_capture_campaign.py'
EXPECTED_TESTS = 27
REFERENCES = {
    'frozen_entry_codec_campaign': ('initial_owner_route_entry_codec_campaign_prepare_001/campaign.json',
        '8884b22d2de102693a8ca3855b0d22ffda10312b2e7806908edd26caaa2dd61a'),
    'frozen_codec_plan': ('complete_root_evidence_codec_pair_prepare_001/plan.json',
        '11451e03fd2ff9ccda080b82a5fa2497b55f37463f0c30b07fd7467fda31d9ff'),
    'single_capture_integration_source': ('initial_single_capture_integration_source_prepare_001/plan.json',
        'b3043d1fc5170da7aa1a139fb0479c8d4f5134a6d3d7c174849482de1cfa81d2'),
    'single_capture_endpoint_source': ('initial_single_capture_endpoint_source_prepare_001/plan.json',
        'ecc78936817d981eb7818e8edc79cade55a1618b159fb023d77b38e2d05e85b8'),
}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf8')


def modules():
    return (MODULE, __package__+'.initial_owner_route_single_capture_campaign',
        __package__+'.launch_initial_owner_route_single_capture_campaign',
        __package__+'.verify_initial_owner_route_single_capture_campaign',
        __package__+'.prepare_initial_owner_route_single_capture_campaign',
        TEST[:-3].replace('/', '.'))


def frozen(campaign_sources=None):
    from . import initial_owner_route_single_capture_campaign as c
    result = {}
    for name, (relative, digest) in REFERENCES.items():
        result[name] = c.source_reference({'path': str(OUT/relative), 'sha256': digest},
            c.SOURCE_DOMAINS[name], campaign_sources)
    return result


def files():
    from . import initial_owner_route_single_capture_campaign as c
    result = c.image.source_closure(ROOT, modules())
    # Retain each historical closed domain even when a test imports a module
    # dynamically; this is identity union, never a replacement image build.
    for relative, digest in REFERENCES.values():
        path = OUT/relative
        c.require(sha(path) == digest, 'single_pure_reference_changed')
        for name, expected in c.read(path)['source_sha256'].items():
            source = Path(name); source = source if source.is_absolute() else ROOT/source
            source = source.resolve(); key = source.relative_to(ROOT).as_posix()
            data = source.read_bytes()
            c.require(hashlib.sha256(data).hexdigest() == expected,
                'single_pure_historical_source_changed:'+name)
            c.require(key not in result or result[key] == data, 'single_pure_source_conflict')
            result[key] = data
    return dict(sorted(result.items()))


def loaded_sources(before):
    actual = {}
    for module in tuple(sys.modules.values()):
        value = getattr(module, '__file__', None)
        if not value: continue
        path = Path(value).resolve()
        if path.suffix == '.py' and path.is_relative_to(ROOT):
            name = path.relative_to(ROOT).as_posix(); digest = sha(path)
            if before.get(name) != digest: raise ValueError('single_pure_unlisted_loaded:'+name)
            actual[name] = digest
    return dict(sorted(actual.items()))


def worker(output, admission):
    if not admission or sys.stdin.readline() != admission+'\n': raise ValueError('single_pure_admission')
    report = {'status': 'failed_or_unknown', 'native_calls': 0, 'predictor_evaluations': 0,
        'performance_runs': 0, 'saved_raw_reads': 0, 'C_extension_loads': 0}
    before = {}
    started = time.perf_counter()
    try:
        report['frozen_entry'] = frozen()
        source_files = files()
        before = {name: hashlib.sha256(data).hexdigest() for name, data in source_files.items()}
        for name, data in source_files.items():
            path = output/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        report['source_sha256'] = before
        report['loaded_entry'] = loaded_sources(before)
        import pytest
        result = pytest.main(['-q', TEST, '--basetemp='+str(output/'tmp'), '--junitxml='+str(output/'tests.xml')])
        xml = output/'tests.xml'
        cases = ET.parse(xml).getroot().findall('.//testcase') if xml.is_file() else []
        report.update(pytest_exitcode=int(result), tests=len(cases), expected_tests=EXPECTED_TESTS,
            XML_sha256=sha(xml) if xml.is_file() else None)
        report['source_changed'] = [name for name, digest in before.items()
            if sha(ROOT/name) != digest or sha(output/'source'/name) != digest]
        report['frozen_exit'] = frozen()
        report['loaded_exit'] = loaded_sources(before)
        forbidden = [name for name in sys.modules if '_g31_complete_tree_normalizer' in name or 'czr005_circulation' in name]
        if forbidden: raise ValueError('single_pure_native_or_C_extension_loaded:'+repr(forbidden))
        from . import initial_owner_route_single_capture_campaign as c
        from . import verify_initial_owner_route_single_capture_campaign as v
        report['campaign_source_proof'] = c.source_proof()
        report['saved_verifier_source_proof'] = v.source_proof()
        if (result == 0 and len(cases) == EXPECTED_TESTS and not report['source_changed']
            and report['frozen_entry'] == report['frozen_exit']
            and not any(n.tag in ('failure', 'error', 'skipped') for row in cases for n in row)):
            report['status'] = 'passed'
    except BaseException as error:
        report['error'] = repr(error)
    report['worker_before_receipt_seconds'] = time.perf_counter()-started
    write(output/'receipt.json', report)
    return 0 if report['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--admission')
    args = parser.parse_args(); output = args.output.resolve()
    if args.worker: return worker(output, args.admission)
    output.mkdir(parents=True, exist_ok=False)
    token = uuid.uuid4().hex
    report = {'status': 'failed_or_unknown', 'shared_seconds': 120.,
        'scope': 'Owned child includes imports, all source/archive checks, pytest and final evidence. External whole-Python clock remains separate.'}
    try:
        remaining = 120.-(time.monotonic()-BOOT)-1.
        if remaining <= 0: raise TimeoutError('single_pure_no_remaining_budget')
        command = [sys.executable, '-m', MODULE, '--output', str(output), '--worker', '--admission', token]
        with (output/'stdout.log').open('x', encoding='utf8') as stdout, (output/'stderr.log').open('x', encoding='utf8') as stderr:
            process = bounded_windows_job.run(command, timeout=remaining, admission=token,
                stdout=stdout, stderr=stderr, cwd=ROOT)
        report['process'] = process
        if (output/'receipt.json').is_file():
            internal = json.loads((output/'receipt.json').read_bytes())
            report['receipt_sha256'] = sha(output/'receipt.json')
            if process['status'] == 'exited' and process['exitcode'] == 0 and internal['status'] == 'passed':
                report['status'] = 'passed'
    except BaseException as error: report['error'] = repr(error)
    report['post_interpreter_before_final_export_seconds'] = time.monotonic()-BOOT
    if report['post_interpreter_before_final_export_seconds'] > 120: report['status'] = 'failed_shared_budget'
    write(output/'bounded_parent_receipt.json', report)
    print(json.dumps(report)); return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
