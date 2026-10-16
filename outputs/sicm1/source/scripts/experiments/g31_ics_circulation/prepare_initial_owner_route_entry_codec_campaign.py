"""Freeze new actual18 codec+entry proposal; prepare only, no native dispatch."""
from __future__ import annotations
import argparse
import copy
import hashlib
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from . import initial_owner_route_entry_codec_campaign as c
from . import verify_initial_owner_route_entry_codec_campaign as verifier
from . import run_initial_entry_codec_campaign_pure as pure_runner

ENTRY = c.OUT/'initial_owner_route_entry_campaign_prepare_001'
CODEC = c.OUT/'complete_root_evidence_codec_pair_prepare_001'
ENTRY_PLAN = 'd37d3e0ea9378974a8a331b97c21be48d6dfe3bab9c18d08b686c68041bd0097'
CODEC_PLAN = '11451e03fd2ff9ccda080b82a5fa2497b55f37463f0c30b07fd7467fda31d9ff'
SUPPORTING = {
    'failed_entry_producer_external': ('initial_owner_route_entry_campaign_prepare_001/external_application_wall.json',
        '665be69f6ffdf7c673c887568feb9b1f9d7420fce9f5298a2fed6d4bd8179239'),
    'recovered_entry_audit': ('initial_owner_route_entry_independent_actual_review_001/report.json',
        '4f552bfddaaaa8e9f981438e63e9a9a84f1971c45e6e7389d60ab27084325792'),
    'recovered_entry_verification': ('initial_owner_route_entry_independent_actual_review_001/recovered_verification.json',
        '6643d1531c5679443b23b47a99f2459602825830ea23d62a81acb7f12de4bcea'),
    'recovered_entry_external': ('initial_owner_route_entry_independent_actual_review_001/external_application_wall.json',
        'ef156e642a888a4a48f4cda28239d73307f4aa1c0529b7dee2db1a9d8ca53803'),
    'codec_saved_audit': ('complete_root_evidence_codec_independent_actual_review_001/report.json',
        '1ba8d09cffa0ca7c81407e4c6eadc8d18d9783942eadc4a097215f3b98415304'),
    'codec_saved_audit_external': ('complete_root_evidence_codec_independent_actual_review_001/external_application_wall.json',
        '59a66ea08a9b1f2084c40e2d9d5a4a3f9fc75daa6ab05f7bc5fbbd5e013537ee'),
    'entry_codec_integration_pure': ('initial_entry_codec_integration_pure_001/receipt.json',
        'f4683662727ac391f6354452749b8779da38299cfe84b2dde7a373a1f3f8841c'),
}


def supporting_references():
    references = {}
    for key, (name, digest) in SUPPORTING.items():
        path = c.OUT/name
        c.require(c.sha(path) == digest, 'entry_codec_evidence_identity:'+key)
        references[key] = c.reference(path)
    failed = c.read(references['failed_entry_producer_external']['path'])
    recovered = c.read(references['recovered_entry_audit']['path'])
    saved72 = c.read(references['codec_saved_audit']['path'])
    c.require(failed['exit_code'] == 1 and recovered['original_producer_failure_preserved'] is True and
        recovered['branches'] == 18 and recovered['original_producer_receipt'] == 'missing_not_retroactively_created' and
        not (ENTRY/'receipt.json').exists() and not (ENTRY/'verification.json').exists(),
        'entry_codec_failed_producer_must_stay_failed')
    c.require(recovered['status'] == 'passed_complete_saved_endpoint_physical_RPC_gate_outbox_audit' and
        recovered['repaired_verification'] == references['recovered_entry_verification'],
        'entry_codec_recovered18_scope')
    c.require(saved72['status'] == 'passed_complete_saved18_ABBA72_readback' and
        saved72['saved_calls'] == 72 and saved72['historical_roots'] == 18 and
        saved72['producer_source_count'] == 135 and saved72['source_entry_exit_unchanged'] is True and
        saved72['complete_native_request_100ms_certified'] is False,
        'entry_codec_saved72_scope')
    for name in ('recovered_entry_external', 'codec_saved_audit_external'):
        external = c.read(references[name]['path'])
        c.require(external['status'] == 'application_exited_zero' and external['exit_code'] == 0 and
            external['evidence_unchanged'] is True, 'entry_codec_audit_external')
    return references


def prepare(output, pure_receipt):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    try:
        pure_receipt = Path(pure_receipt).resolve()
        pure = c.read(pure_receipt); xml = pure_receipt.parent/'tests.xml'
        tests = ET.parse(xml).getroot().findall('.//testcase')
        c.require(pure['status'] == 'passed' and pure['source_changed'] == [] and
            pure['native_calls'] == pure['predictor_evaluations'] == pure['performance_runs'] == pure['saved_raw_reads'] == 0 and
            pure['original151_and_codec135_current_and_archive_unchanged'] is True and
            len(tests) == pure['tests'] >= 40 and pure['XML_sha256'] == c.sha(xml) and
            not any(n.tag in ('failure', 'error', 'skipped') for row in tests for n in row),
            'entry_codec_unclosed_focused_pure')
        for name, digest in pure['source_sha256'].items():
            c.require(c.sha(c.ROOT/name) == c.sha(pure_receipt.parent/'source'/name) == digest,
                      'entry_codec_pure_source_changed:'+name)
        c.require(c.sha(ENTRY/'campaign.json') == ENTRY_PLAN and c.sha(CODEC/'plan.json') == CODEC_PLAN,
                  'entry_codec_frozen_campaign_identity')
        pure_runner.integration_pure.frozen()
        entry_plan, codec_plan = c.read(ENTRY/'campaign.json'), c.read(CODEC/'plan.json')
        supporting = supporting_references()
        files = c.image.source_closure(c.ROOT, pure_runner.modules())
        sources, archive = {}, {}
        for name, data in files.items():
            path = c.ROOT/name; target = output/'source'/name
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
            sources[str(path)] = hashlib.sha256(data).hexdigest()
            archive[str(path)] = str(target.relative_to(output))
        for original, count in ((entry_plan, 151), (codec_plan, 135)):
            c.require(len(original['source_sha256']) == count and
                all(sources.get(name) == digest for name, digest in original['source_sha256'].items()),
                'entry_codec_frozen_source_domain_not_preserved')
        plan = copy.deepcopy(entry_plan)
        plan.update(schema=c.SCHEMA, source_sha256=sources, source_archive=archive,
            pure_reference=c.reference(pure_receipt), pure_XML=c.reference(xml),
            entry_codec_campaign_pure=c.reference(pure_receipt), **supporting,
            frozen_entry_campaign=c.reference(ENTRY/'campaign.json'), frozen_codec_plan=c.reference(CODEC/'plan.json'),
            entry_codec_source_proof=c.integrated.integration_proof(),
            saved_verifier_source_proof=verifier.source_proof(), campaign_source_proof=c.source_proof(),
            environment={'interpreter': sys.executable, 'interpreter_sha256': c.sha(sys.executable), 'version': sys.version},
            status='prepared_for_review_no_execution')
        inputs = {}
        for key, row in plan['rows'].items():
            path = output/'inputs'/(key+'.json'); c.write(path, c.scene(row)); inputs[key] = c.sha(path)
        c.require(inputs == entry_plan['input_file_sha256'], 'entry_codec_all18_input_bytes_changed')
        plan['input_file_sha256'] = inputs
        plan['amendment'] = {
            'prior_entry_campaign': c.reference(ENTRY/'campaign.json'),
            'prior_entry_producer_status': 'exit1_Path_namespace_failure_preserved_missing_receipt',
            'separate_recovery': supporting['recovered_entry_audit'],
            'codec_saved72': supporting['codec_saved_audit'],
            'change': 'Only privately compose full complete-evidence codec with already source-bound actual ENTRY observer. All query/outbox/advance proof and entry marker remain encoded.',
            'saved_verifier': 'Use repaired v2 shared defining namespace, recursively inventory LOAD_GLOBAL, bind both root replay levels to new campaign, retain every original endpoint/physical/RPC/gate/outbox check.',
            'scope': 'Same18 inputs/faults, finite2 choices, original100ms target, original background IDs/cadence and fullH40/all5 physical audit; fixed shared600 with1native worker.',
            'not_claimed': 'Saved72 data-only speed is not a new native request latency; prior ENTRY comparisons were separate rounds, not ABBA. No all18 success or100ms result is preregistered.',
            'costs': 'Every dynamic guard, actual query/ACK/drain, complete trace proof, normalization/codec/strictcheck/hash/publication/return remains inside root; cold/RPC/export/saved verification included in full campaign, no subtraction/amortization.'}
        plan['scope']['new_mechanisms'] = {
            'inherited': 'Entry observer, exact native handle and transport, actual advance chain, complete query representation, fixed background policy unchanged from source-bound entry integration.',
            'codec': 'Original one-fresh normalize and strict decoder retained. Remove only already-validated redundant encoder tree walk; same strict UTF8 compact encoding readback validates all ordered keys and scalar bits before evidence returns.',
            'verifier': 'Repaired defining-module globals plus two-level root predicate binding; fulloriginal code/closures, no weakened checks.',
            'failure': 'Every branch remains in18 denominator. Failures/open/RPC shutdown errors retain unknown; original failed151 producer not rewritten.',
            'comparison': 'Descriptive against independently recovered entry18; full5job strict comparisons within each new normal pair remain required. No causal ABBA native speed claim.'}
        c.write(output/'campaign.json', plan)
        c.write(output/'branch_ledger.json', {key: {**row, 'status': 'unknown_unexecuted'} for key, row in plan['rows'].items()})
        expected = c.sha(output/'campaign.json'); c.verify_plan(output, expected)
        receipt = {'schema': c.SCHEMA, 'status': 'prepared_source_review_pending',
            'campaign': c.reference(output/'campaign.json'), 'sources': len(sources),
            'compiled_sources': len(plan['compiled_source_archive_sha256']), 'pure_tests': len(tests),
            'native_calls': 0, 'predictor_evaluations': 0, 'not_dispatched': True,
            'execute_command': [sys.executable, '-m', __package__+'.launch_initial_owner_route_entry_codec_campaign',
                '--output', str(output), '--campaign-sha256', expected],
            'external_measured_launch_wrapper_required': True}
        c.write(output/'source_preparation.json', receipt)
        return receipt
    except BaseException as error:
        c.write(output/'preparation_failure.json', {'status': 'failed_preparation', 'error': repr(error), 'native_calls': 0})
        raise


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--pure-receipt', type=Path, required=True); args = p.parse_args()
    print(prepare(args.output, args.pure_receipt)); return 0


if __name__ == '__main__': raise SystemExit(main())
