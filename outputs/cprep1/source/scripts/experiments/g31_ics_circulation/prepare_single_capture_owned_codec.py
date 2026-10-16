"""Prepare the source-only live publisher binding; never load C or run a case."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from . import initial_owner_route_single_capture_owned_codec as candidate
from . import run_single_capture_owned_codec_pure as gate

MODULE = 'scripts.experiments.g31_ics_circulation.prepare_single_capture_owned_codec'
PURE = gate.OUT/'single_capture_owned_codec_pure_001'
PURE_PINS = {
    'plan.json': '0d1949e0de078a9b1c322c17007fbde333c468780baf7e71214af8635f4bd88e',
    'receipt.json': '6842d7a940ff617fcc552c4a0d4537bf36b9e3f8fb7566af2c03ece540b55000',
    'tests.xml': '4588013e3dad02ad613a3a7c337414cd0fc82b02d3f7f56519c767941b252da9',
}
WRAPPER = gate.OUT/'invoke_single_capture_owned_codec_pure_001.ps1'
WRAPPER_SHA = '92e11038389f1093dbbe5e91d005edb478ec9cf30c0c3fac60f958149e1727a7'


def write_new(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def pure_evidence():
    for name, digest in PURE_PINS.items():
        gate.require(gate.sha(PURE/name) == digest, 'prepare_pure_pin_' + name)
    gate.require(gate.sha(WRAPPER) == WRAPPER_SHA, 'prepare_wrapper_pin')
    plan = json.loads((PURE/'plan.json').read_text(encoding='utf8'))
    receipt = json.loads((PURE/'receipt.json').read_text(encoding='utf8'))
    external = json.loads((PURE/'external_application_wall.json').read_text(encoding='utf8'))
    rows = ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    gate.require(len(rows) == 45 and not any(n.tag in ('failure', 'error', 'skipped')
        for row in rows for n in row), 'prepare_exact_45_pure')
    gate.require(receipt['status'] == 'passed' and receipt['source_count'] == 155
        and receipt['tests'] == receipt['expected_tests'] == 45
        and receipt['source_changed'] == []
        and receipt['original190_and_sameC153_current_archive_unchanged'] is True
        and receipt['XML_sha256'] == PURE_PINS['tests.xml']
        and receipt['plan_sha256'] == PURE_PINS['plan.json'], 'prepare_pure_receipt')
    gate.require(external['exitcode'] == 0 and external['exception'] is None
        and 0 < external['whole_python_wall_seconds'] < 120
        and external['wrapper_sha256'] == WRAPPER_SHA
        and external['expected_tests'] == 45
        and external['binding_cases'] == 40 and external['archive_path_cases'] == 5,
        'prepare_pure_external')
    gate.require(all(receipt[name] == 0 for name in
        ('native_calls', 'model_calls', 'C_loads', 'saved_raw_reads', 'performance_runs')),
        'prepare_pure_scope')
    canonical = gate.canonical_sources(plan['source_sha256'])
    gate.require(len(canonical) == 155 and canonical == plan['source_sha256'],
        'prepare_pure_canonical_inventory')
    for name, digest in canonical.items():
        saved = (PURE/plan['source_archive'][name]).resolve()
        gate.require(saved == gate.archive_target(PURE, name), 'prepare_pure_archive_path')
        gate.require(gate.sha(gate.ROOT/name) == gate.sha(saved) == digest,
            'prepare_pure_current_archive')
    return plan, receipt, external


def prepare(output):
    began = time.monotonic()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        pure_plan, pure_receipt, external = pure_evidence()
        references = gate.frozen_references()
        files = gate.canonical_sources(gate.image.source_closure(gate.ROOT, (
            MODULE, gate.MODULE, gate.CANDIDATE, gate.TEST[:-3].replace('/', '.'))))
        before = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        gate.require(all(before.get(name) == digest
            for name, digest in pure_plan['source_sha256'].items()), 'prepare_pure_subset')
        # Resolve EVERY archive target before any source copy. No inherited
        # absolute key is ever joined with an output path or rewritten.
        targets = {name: gate.archive_target(output, name) for name in files}
        gate.require(len(set(targets.values())) == len(targets), 'prepare_archive_unique')
        archive = {}
        for name, data in files.items():
            saved = targets[name]
            saved.parent.mkdir(parents=True, exist_ok=True)
            with saved.open('xb') as stream:
                stream.write(data)
            archive[name] = saved.relative_to(output).as_posix()
        evidence = {}
        for path in (PURE/'plan.json', PURE/'receipt.json', PURE/'tests.xml',
                     PURE/'external_application_wall.json', WRAPPER):
            saved = output/'evidence'/path.name
            saved.parent.mkdir(parents=True, exist_ok=True)
            with saved.open('xb') as stream:
                stream.write(path.read_bytes())
            evidence[str(path)] = {'sha256': gate.sha(path),
                'archive': saved.relative_to(output).as_posix()}
        proof = candidate.source_proof()
        write_new(output/'source_proof.json', proof)
        plan = {'schema': 'g31.single_capture.owned_codec.source_prepare.v1',
            'scope': 'explicit verified Candidate binding; source/synthetic evidence only',
            'source_sha256': before, 'source_archive': archive,
            'source_keys': 'unique ROOT-relative POSIX; contained archive distinct from current source',
            'frozen_references': references, 'evidence': evidence,
            'source_proof_sha256': gate.sha(output/'source_proof.json'),
            'pure': {'tests': 45, 'binding_tests': 40, 'archive_path_tests': 5,
                'whole_python_wall_seconds': external['whole_python_wall_seconds'],
                'receipt_sha256': PURE_PINS['receipt.json']},
            'public_entry': gate.CANDIDATE + '.bind(verified_candidate)',
            'optional_branch_clone': gate.CANDIDATE + '.branch_function(binding)',
            'preserved': ['single-capture A initial/A final/B wrapper and collection normalization',
                'exact ActualAdvanceChain, constructor classcell, actual root drain and observer',
                'source/current/native authority, model, ACK, firsthop, scheduler and admission IDs',
                'original complete root runtime proof; full evidence, clocks, hash, ledger, return'],
            'changed': ['private complete publisher normalization facade and owned roundtrip',
                'request evidence and both scheduler/direct-failure publisher bindings'],
            'synthetic_private_compose_is_C_support_evidence': False,
            'C_support_or_native_performance_measured_in_this_package': False,
            'actual_campaign_ready': False,
            'future_campaign_requirements': [
                'bind the exact verified Candidate loader, ABI, binary, DLL/runtime and source pins',
                'check direct C support of actual payloads without treating fallback as C support',
                'preserve failure-aware endpoint/physical/RPC/root/outbox/gate/lifetime saved checks',
                'include binding/setup, all complete publication and cleanup costs in full clock'],
            'complete_100ms_certified': False, 'per_sample_cycle_cleanup_certified': False,
            'resource_failure_points_equivalent': False,
            'native_calls': 0, 'model_calls': 0, 'C_loads': 0, 'saved_raw_reads': 0,
            'performance_runs': 0, 'preparation_is_not_a_benchmark': True}
        write_new(output/'plan.json', plan)
        changed = [name for name, digest in before.items()
            if gate.sha(gate.ROOT/name) != digest or gate.sha(targets[name]) != digest]
        gate.require(not changed, 'prepare_entry_exit_source_changed')
        gate.require(gate.frozen_references() == references, 'prepare_frozen_reference_exit')
        pure_evidence()
        receipt = {'status': 'prepared_source_only', 'plan_sha256': gate.sha(output/'plan.json'),
            'source_count': len(before), 'source_changed': changed,
            'all_archive_paths_contained_and_distinct_from_current': True,
            'pure_155_and_original_190_153_current_archive_entry_exit_equal': True,
            'pure_tests': 45, 'binding_tests': 40, 'archive_path_tests': 5,
            'native_calls': 0, 'model_calls': 0, 'C_loads': 0, 'performance_runs': 0,
            'actual_campaign_ready': False,
            'preparation_seconds_after_import': time.monotonic() - began}
        write_new(output/'source_preparation.json', receipt)
        return receipt
    except BaseException as error:
        write_new(output/'preparation_failure.json', {
            'status': 'failed_source_preparation', 'error_type': type(error).__name__,
            'error': str(error), 'elapsed_seconds_after_import': time.monotonic() - began,
            'partial_artifacts_retained': True, 'actual_campaign_ready': False})
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output)))


if __name__ == '__main__': main()
