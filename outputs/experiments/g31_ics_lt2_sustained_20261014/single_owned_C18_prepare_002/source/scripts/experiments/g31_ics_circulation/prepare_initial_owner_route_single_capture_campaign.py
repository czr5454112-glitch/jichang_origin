"""Freeze actual18 single-triplet proposal only; never dispatch a session."""
from __future__ import annotations
import argparse
import copy
import hashlib
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from . import initial_owner_route_single_capture_campaign as c
from . import verify_initial_owner_route_single_capture_campaign as verifier
from . import run_initial_single_capture_campaign_pure as pure_runner

BASE = c.OUT/'initial_owner_route_entry_codec_campaign_prepare_001'
BASE_SHA = '8884b22d2de102693a8ca3855b0d22ffda10312b2e7806908edd26caaa2dd61a'
REVIEW = c.OUT/'initial_entry_codec_saved_review_001/report.json'
REVIEW_SHA = '283cadcc3ec8ba36b4b33da213c4b6f45ef9d33dd1ee29da690d2b8c703a3cee'


def checked_pure(path, *, expected, identity_fields):
    path = Path(path).resolve(); value = c.read(path); xml = path.parent/'tests.xml'
    cases = ET.parse(xml).getroot().findall('.//testcase')
    c.require(value['status'] == 'passed' and value['source_changed'] == []
        and value['tests'] == expected and len(cases) == expected
        and value['XML_sha256'] == c.sha(xml)
        and all(value[name] == 0 for name in identity_fields)
        and not any(n.tag in ('failure', 'error', 'skipped') for row in cases for n in row),
        'single_capture_unclosed_pure:'+str(path))
    for name, digest in value['source_sha256'].items():
        c.require(c.sha(c.ROOT/name) == c.sha(path.parent/'source'/name) == digest,
            'single_capture_pure_current_or_archive_changed:'+name)
    c.require(value['frozen_entry'] == value['frozen_exit'], 'single_capture_pure_frozen_drift')
    return value, xml


def checked_verifier_source(path):
    path = Path(path).resolve(); value = c.read(path)
    c.require(type(value.get('source_sha256')) is dict and len(value['source_sha256']) >= 131,
        'single_capture_verifier_source_scope')
    c.source_reference(c.reference(path), len(value['source_sha256']))
    receipt = value['pure_receipt']; xml = value['pure_XML']
    c.require(c.sha(receipt['path']) == receipt['sha256'] and c.sha(xml['path']) == xml['sha256'],
        'single_capture_verifier_pure_reference_changed')
    pure, actual_xml = checked_pure(receipt['path'], expected=117,
        identity_fields=('native_calls', 'predictor_calls', 'actual_saved_raw_reads',
            'performance_runs', 'C_extension_loads'))
    c.require(c.sha(actual_xml) == xml['sha256'] and pure['source_proof'] == verifier.source_proof(),
        'single_capture_verifier_source_proof_changed')
    return value, pure


def prepare(output, pure_receipt, verifier_source):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    try:
        pure_receipt, verifier_source = Path(pure_receipt).resolve(), Path(verifier_source).resolve()
        pure, xml = checked_pure(pure_receipt, expected=pure_runner.EXPECTED_TESTS,
            identity_fields=('native_calls', 'predictor_evaluations', 'performance_runs',
                'saved_raw_reads', 'C_extension_loads'))
        parent = c.read(pure_receipt.parent/'bounded_parent_receipt.json')
        c.require(parent['status'] == 'passed' and parent['process']['status'] == 'exited'
            and parent['process']['exitcode'] == 0 and parent['receipt_sha256'] == c.sha(pure_receipt),
            'single_capture_pure_parent_not_closed')
        c.require(pure['campaign_source_proof'] == c.source_proof()
            and pure['saved_verifier_source_proof'] == verifier.source_proof(),
            'single_capture_pure_source_proof_changed')
        verifier_plan, verifier_pure = checked_verifier_source(verifier_source)
        c.require(c.sha(BASE/'campaign.json') == BASE_SHA and c.sha(REVIEW) == REVIEW_SHA,
            'single_capture_historical_reference_changed')
        review = c.read(REVIEW)
        c.require(review['status'] == 'passed_complete_saved_endpoint_physical_RPC_entry_gate_outbox_codec_audit'
            and review['new_native_calls'] == review['new_predictor_calls'] == 0
            and review['evidence']['campaign.json'] == c.reference(BASE/'campaign.json'),
            'single_capture_entry_codec_saved_review_scope')
        pure_runner.frozen()
        original = c.read(BASE/'campaign.json')
        files = pure_runner.files()
        for domain in (verifier_plan, verifier_pure):
            for name, digest in domain['source_sha256'].items():
                path = Path(name); path = path if path.is_absolute() else c.ROOT/path
                path = path.resolve(); key = path.relative_to(c.ROOT).as_posix(); data = path.read_bytes()
                c.require(hashlib.sha256(data).hexdigest() == digest
                    and (key not in files or files[key] == data), 'single_capture_source_union_conflict')
                files[key] = data
        sources, archives = {}, {}
        for name, data in sorted(files.items()):
            path = c.ROOT/name; target = output/'source'/name
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
            sources[str(path.resolve())] = hashlib.sha256(data).hexdigest()
            archives[str(path.resolve())] = str(target.relative_to(output))
        # Every file actually used by the pure gate must also be in the new
        # campaign archive; source-only additions cannot hide stale test code.
        for name, digest in pure['source_sha256'].items():
            c.require(sources.get(str((c.ROOT/name).resolve())) == digest,
                'single_capture_pure_source_not_in_campaign:'+name)
        plan = copy.deepcopy(original)
        plan.update(schema=c.SCHEMA, source_sha256=sources, source_archive=archives,
            pure_reference=c.reference(pure_receipt), pure_XML=c.reference(xml),
            single_capture_campaign_pure=c.reference(pure_receipt),
            single_capture_campaign_pure_parent=c.reference(pure_receipt.parent/'bounded_parent_receipt.json'),
            single_capture_verifier_source=c.reference(verifier_source),
            single_capture_verifier_pure=copy.deepcopy(verifier_plan['pure_receipt']),
            single_capture_verifier_XML=copy.deepcopy(verifier_plan['pure_XML']),
            frozen_entry_codec_campaign=c.reference(BASE/'campaign.json'),
            entry_codec_saved_review=c.reference(REVIEW),
            single_capture_integration_proof=c.integrated.integration_proof(),
            single_capture_campaign_source_proof=c.source_proof(),
            single_capture_saved_verifier_source_proof=verifier.source_proof(),
            environment={'interpreter': sys.executable, 'interpreter_sha256': c.sha(sys.executable), 'version': sys.version},
            status='prepared_for_review_no_execution')
        for name, (relative, digest) in pure_runner.REFERENCES.items():
            plan[name] = {'path': str(c.OUT/relative), 'sha256': digest}
        for name, count in c.SOURCE_DOMAINS.items(): c.source_reference(plan[name], count, sources)
        c.source_reference(plan['single_capture_verifier_source'], len(verifier_plan['source_sha256']), sources)
        inputs = {}
        for key in plan['row_order']:
            path = output/'inputs'/(key+'.json'); c.write(path, c.scene(plan['rows'][key])); inputs[key] = c.sha(path)
        c.require(inputs == original['input_file_sha256'], 'single_capture_18_input_bytes_changed')
        plan['input_file_sha256'] = inputs
        c.require(len(plan['compiled_source_archive_sha256']) == 67
            and plan['image'] == original['image'] and plan['expected_READY'] == original['expected_READY']
            and plan['row_order'] == original['row_order'] and plan['rows'] == original['rows'],
            'single_capture_native_image_or_domain_changed')
        plan['single_capture_amendment'] = {
            'change': 'The same actual collector executes one fresh own view/own command/received triplet per invocation; A initial, A final and fixed B share the concrete wrapper. No query result, ledger, session capability or native authorization is reconstructed from JSON.',
            'source': 'Original branch code/defaults/closure and complete globals retained; only four live integration bindings plus SCHEMA differ. Worker changes exactly the verifier import and one status gate after saving verification.',
            'failure': 'All18 attempts retained. Failed endpoint prefixes require explicit attempt-clock envelope; invalid or checker-error reports stay saved and prevent completed receipt. Verified unknown/open roots remain unknown, with cleanup and actual branch costs retained.',
            'historical_proof': 'Frozen prototype source_proof fields are historical. New integration and worker proofs explicitly bind current concrete code; old169/135/153/131 archives remain unchanged.',
            'scope': 'Same18 inputs, finite2 budget, native02767-source authority, predictor image, fixed background, cadence and fullH40/all5 physical audit. Shared600 includes native/RPC/cleanup/export/saved verification with one native worker.',
            'costs': 'No guard/query/ACK/drain/publication/codec/output/cleanup cost removed from request. Complete100ms target remains; all unresolved, overbudget or malformed roots remain unknown.',
            'not_claimed': 'No native query-effect equivalence, performance gain, full32 optimization, rolling method or protection is established by source/pure preparation.'}
        c.write(output/'campaign.json', plan)
        c.write(output/'branch_ledger.json', {key: {**plan['rows'][key], 'status': 'unknown_unexecuted'}
            for key in plan['row_order']})
        expected = c.sha(output/'campaign.json'); c.verify_plan(output, expected)
        for name, digest in sources.items():
            c.require(c.sha(name) == c.sha(output/archives[name]) == digest, 'single_capture_prepare_exit_drift')
        receipt = {'schema': c.SCHEMA, 'status': 'prepared_source_review_pending',
            'campaign': c.reference(output/'campaign.json'), 'sources': len(sources),
            'compiled_sources': 67, 'campaign_pure_tests': pure['tests'], 'verifier_pure_tests': verifier_pure['tests'],
            'historical_domains': c.SOURCE_DOMAINS, 'native_calls': 0, 'predictor_evaluations': 0,
            'C_extension_loads': 0, 'not_dispatched': True,
            'execute_command': [sys.executable, '-m', __package__+'.launch_initial_owner_route_single_capture_campaign',
                '--output', str(output), '--campaign-sha256', expected],
            'external_measured_launch_wrapper_required': True}
        c.write(output/'source_preparation.json', receipt)
        return receipt
    except BaseException as error:
        c.write(output/'preparation_failure.json', {'status': 'failed_preparation', 'error': repr(error),
            'native_calls': 0, 'predictor_evaluations': 0})
        raise


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--pure-receipt', type=Path, required=True)
    p.add_argument('--verifier-source', type=Path, required=True)
    args = p.parse_args(); print(prepare(args.output, args.pure_receipt, args.verifier_source)); return 0


if __name__ == '__main__': raise SystemExit(main())
