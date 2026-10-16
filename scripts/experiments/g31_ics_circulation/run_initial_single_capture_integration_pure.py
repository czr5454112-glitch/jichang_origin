"""Owned120 functional integration gate; no native/model/actual fixture scan."""
import time
BOOT = time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job as bounded
from . import initial_owner_route_image as image

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
MODULE = 'scripts.experiments.g31_ics_circulation.run_initial_single_capture_integration_pure'
TESTS = ('tests/test_g31_circulation_initial_owner_route_single_capture_integration.py',
    'tests/test_g31_circulation_initial_owner_route_single_capture.py')
REFERENCES = (
    (OUT/'initial_owner_route_entry_codec_campaign_prepare_001/campaign.json',
     '8884b22d2de102693a8ca3855b0d22ffda10312b2e7806908edd26caaa2dd61a'),
    (OUT/'complete_root_evidence_codec_pair_prepare_001/plan.json',
     '11451e03fd2ff9ccda080b82a5fa2497b55f37463f0c30b07fd7467fda31d9ff'),
)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen():
    reports = []
    for path, expected in REFERENCES:
        if sha(path) != expected: raise ValueError('single_capture_reference_hash:' + str(path))
        plan = json.loads(path.read_text(encoding='utf8'))
        for name, digest in plan['source_sha256'].items():
            source = Path(name); source = source if source.is_absolute() else ROOT/source
            if sha(source) != digest or sha(path.parent/plan['source_archive'][name]) != digest:
                raise ValueError('single_capture_frozen_source_changed:' + name)
        reports.append({'path': str(path), 'sha256': expected, 'source_count': len(plan['source_sha256'])})
    return reports


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--admission')
    args = parser.parse_args(); output = args.output.resolve()
    if args.worker:
        if sys.stdin.readline() != args.admission+'\n': raise ValueError('single_capture_pure_admission')
        import pytest
        result = pytest.main(['-q', *TESTS, '--basetemp='+str(output/'tmp'), '--junitxml='+str(output/'tests.xml')])
        if any('_g31_complete_tree_normalizer' in name or 'czr005_circulation' in name for name in sys.modules):
            raise ValueError('single_capture_pure_extension_loaded')
        return result
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'status': 'failed_or_unknown', 'native_calls': 0, 'predictor_calls': 0,
        'actual_saved_raw_reads': 0, 'performance_runs': 0, 'C_extension_loads': 0}
    before = {}
    try:
        receipt['frozen_entry'] = frozen()
        modules = (MODULE, 'scripts.experiments.g31_ics_circulation.initial_owner_route_single_capture_integration',
            *(path[:-3].replace('/', '.') for path in TESTS),
            'tests.test_g31_circulation_initial_owner_route_entry_codec_integration',
            'tests.test_g31_circulation_initial_owner_route_entry_integration',
            'tests.test_g31_circulation_initial_owner_route_entry_hop',
            'tests.test_g31_circulation_preexisting_online_model',
            'tests.test_g31_circulation_public_rolling_reuse_model')
        files = image.source_closure(ROOT, modules)
        before = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        for name, data in files.items():
            path = output/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        receipt['source_sha256'] = before
        token = uuid.uuid4().hex
        command = [sys.executable, '-m', MODULE, '--output', str(output), '--worker', '--admission', token]
        remaining = 120-(time.monotonic()-BOOT)-1
        if remaining <= 0: raise TimeoutError('single_capture_pure_prework_budget')
        with (output/'stdout.log').open('x', encoding='utf8') as stdout, (output/'stderr.log').open('x', encoding='utf8') as stderr:
            process = bounded.run(command, timeout=remaining, admission=token,
                stdout=stdout, stderr=stderr, cwd=ROOT)
        receipt['process'] = process
        xml = output/'tests.xml'
        cases = ET.parse(xml).getroot().findall('.//testcase') if xml.is_file() else []
        receipt['tests'] = len(cases)
        receipt['XML_sha256'] = sha(xml) if xml.is_file() else None
        receipt['source_changed'] = [name for name, digest in before.items() if sha(ROOT/name) != digest]
        receipt['frozen_exit'] = frozen()
        passed = (process['status'] == 'exited' and process['exitcode'] == 0 and len(cases) == 59
            and not receipt['source_changed'] and receipt['frozen_entry'] == receipt['frozen_exit']
            and not any(child.tag in ('failure', 'error', 'skipped') for row in cases for child in row))
        if passed:
            from . import initial_owner_route_single_capture_integration as integration
            receipt['integration_proof'] = integration.integration_proof()
            receipt['status'] = 'passed'
    except BaseException as error:
        receipt['error'] = repr(error)
    receipt['post_interpreter_before_receipt_seconds'] = time.monotonic()-BOOT
    (output/'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf8')
    print(json.dumps({key: value for key, value in receipt.items() if key not in ('source_sha256', 'integration_proof')}))
    return 0 if receipt['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
