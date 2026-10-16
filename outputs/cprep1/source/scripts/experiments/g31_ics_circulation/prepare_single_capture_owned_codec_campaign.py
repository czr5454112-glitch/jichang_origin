"""Canonical contained source preparation only; no C load or actual18 run."""
from __future__ import annotations
import argparse
import copy
import hashlib
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from . import initial_owner_route_single_capture_owned_codec_campaign as c
from . import verify_initial_owner_route_single_capture_owned_codec_campaign as v
from . import run_single_capture_owned_codec_campaign_pure as pure

MODULE = __package__+'.prepare_single_capture_owned_codec_campaign'
BASE = c.OUT/'initial_owner_route_single_capture_campaign_prepare_001'
BASE_SHA = '5ac870bdd01f09eefdf4b5e552238abc3a730745daeb04590acbb6ac3a539ddc'
NEW_BINDING = c.OUT/'single_capture_owned_codec_source_prepare_001/plan.json'
BINDING_SHA = '63c2aab25f133ba72df76533a4f53b9fa0cfb962ca748c9dd970117d1479cb00'
PAIR = c.OUT/'complete_root_owned_decode_C_pair_prepare_001/plan.json'
PAIR_SHA = '947f7c33f012f4b4b3248cbbfe1cc037537340c3da89971160ec732d91bae00d'


def checked_pure(directory):
    directory = Path(directory).resolve()
    receipt, plan = c.read(directory/'receipt.json'), c.read(directory/'plan.json')
    rows = ET.parse(directory/'tests.xml').getroot().findall('.//testcase')
    c.require(receipt['status'] == 'passed' and receipt['source_changed'] == []
        and receipt['tests'] == receipt['expected_tests'] == pure.COUNT == len(rows)
        and not any(n.tag in ('failure','error','skipped') for row in rows for n in row)
        and receipt['XML_sha256'] == c.sha(directory/'tests.xml')
        and receipt['plan_sha256'] == c.sha(directory/'plan.json')
        and receipt['child_sha256'] == c.sha(directory/'child.json')
        and receipt['frozen_entry'] == receipt['frozen_exit'], 'owned_prepare_pure')
    child = c.read(directory/'child.json')
    c.require(child['campaign_source_proof'] == c.source_proof()
        and child['saved_verifier_source_proof'] == v.source_proof(), 'owned_prepare_pure_proof')
    for name in ('native_calls','C_loads','model_calls','actual_saved_raw_reads','performance_runs'):
        c.require(receipt[name] == 0, 'owned_prepare_pure_scope')
    canonical = c.runtime.paths.canonical_sources(plan['source_sha256'])
    c.require(canonical == plan['source_sha256'], 'owned_prepare_pure_canonical')
    for name, digest in canonical.items():
        target = c.runtime.paths.archive_target(directory, name)
        c.require((directory/plan['source_archive'][name]).resolve() == target
            and c.sha(c.ROOT/name) == c.sha(target) == digest, 'owned_prepare_pure_archive')
    external = c.read(directory/'external_application_wall.json')
    c.require(external['exitcode'] == 0 and external['exception'] is None
        and 0 < external['whole_python_wall_seconds'] < 120
        and external['expected_tests'] == pure.COUNT, 'owned_prepare_pure_outer')
    return receipt, plan


def union_sources(reference_plans):
    files = c.runtime.paths.canonical_sources(c.image.source_closure(c.ROOT, (
        MODULE, pure.MODULE, __package__+'.run_single_capture_owned_codec_prepare',
        __package__+'.launch_initial_owner_route_single_capture_owned_codec_campaign',
        pure.TEST[:-3].replace('/', '.'))))
    for path, expected in reference_plans:
        path = Path(path).resolve()
        c.require(c.sha(path) == expected, 'owned_prepare_reference_hash')
        plan = c.read(path)
        # Keys are resolved BEFORE merging. Exact duplicate identities are
        # one source; conflicting bytes fail. Archives are read-only and must
        # lie inside their old package, distinct from every current source.
        sources = c.runtime.paths.canonical_sources(plan['source_sha256'])
        for raw_name, digest in plan['source_sha256'].items():
            source = Path(raw_name); source = (source if source.is_absolute() else c.ROOT/source).resolve()
            name = source.relative_to(c.ROOT).as_posix()
            target = Path(plan['source_archive'][raw_name])
            target = (target if target.is_absolute() else path.parent/target).resolve()
            c.require(target.is_relative_to(path.parent) and target != source,
                'owned_prepare_reference_archive_containment')
            data = source.read_bytes()
            c.require(hashlib.sha256(data).hexdigest() == c.sha(target) == digest == sources[name],
                'owned_prepare_reference_current_archive')
            c.require(name not in files or files[name] == data, 'owned_prepare_union_conflict')
            files[name] = data
    return dict(sorted(files.items()))


def prepare(output, pure_directory):
    output, pure_directory = Path(output).resolve(), Path(pure_directory).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        receipt, pure_plan = checked_pure(pure_directory)
        pure.frozen()
        refs = ((BASE/'campaign.json', BASE_SHA), (NEW_BINDING, BINDING_SHA), (PAIR, PAIR_SHA),
            (pure_directory/'plan.json', c.sha(pure_directory/'plan.json')))
        files = union_sources(refs)
        # Complete target inventory must be safe BEFORE the first archive write.
        targets = {name: c.runtime.paths.archive_target(output, name) for name in files}
        c.require(len(set(targets.values())) == len(files), 'owned_prepare_unique_archive')
        sources, archives = {}, {}
        for name, data in files.items():
            targets[name].parent.mkdir(parents=True, exist_ok=True)
            with targets[name].open('xb') as stream: stream.write(data)
            sources[name] = hashlib.sha256(data).hexdigest()
            archives[name] = targets[name].relative_to(output).as_posix()
        original = c.read(BASE/'campaign.json'); plan = copy.deepcopy(original)
        provider_contract = c.runtime.metadata()
        files_before = c.runtime.verify_files(provider_contract)
        plan.update(schema=c.SCHEMA, source_sha256=sources, source_archive=archives,
            owned_C_campaign_source_proof=c.source_proof(), owned_C_saved_source_proof=v.source_proof(),
            C_provider=provider_contract, frozen_single_capture_campaign=c.reference(BASE/'campaign.json'),
            owned_C_binding_source=c.reference(NEW_BINDING), same_C_owned_decoder_plan=c.reference(PAIR),
            owned_C_campaign_pure=c.reference(pure_directory/'receipt.json'),
            owned_C_campaign_pure_plan=c.reference(pure_directory/'plan.json'),
            owned_C_campaign_pure_XML=c.reference(pure_directory/'tests.xml'),
            owned_C_campaign_pure_outer=c.reference(pure_directory/'external_application_wall.json'),
            environment={'interpreter': sys.executable, 'interpreter_sha256': c.sha(sys.executable), 'version': sys.version},
            status='prepared_for_root_review_no_execution')
        inputs = {}
        for key in plan['row_order']:
            source = BASE/'inputs'/(key+'.json'); target = output/'inputs'/(key+'.json')
            c.require(c.sha(source) == original['input_file_sha256'][key], 'owned_prepare_original_input')
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream: stream.write(source.read_bytes())
            inputs[key] = c.sha(target)
        c.require(inputs == original['input_file_sha256'] and len(inputs) == 18,
            'owned_prepare_input_denominator')
        plan['input_file_sha256'] = inputs
        plan['owned_C_publisher_amendment'] = {
            'change': 'Only the complete publication path is explicitly bound to accepted004 Candidate and owned decoder. A initial/final and B collection wrappers and their Python normalization are unchanged.',
            'runtime': 'Exact actual module file/spec origin/ExtensionFileLoader path and bound C builtin, original source hashes, ABI and process DLL paths are checked at entry and exit. Existing Python loaded-source whitelist remains exact and separate.',
            'fallback': 'The exact accepted Candidate retains its original one-time Python fallback. Actual direct-C support and fallback counts are unknown; no duplicate request preflight or post-normalization inference is performed.',
            'cost': 'Provider cold setup and close identity checks, toolchain/source checks, native/predictor setup and cleanup, all18 complete request publications, export and saved verification remain in shared600 and external launch-to-exit. No per-root amortization or C unload claim.',
            'unchanged': 'Original18 inputs/faults, finite2,60ms decision cutoff,100ms complete target,current/source/native guards, ACK,firsthop,drain,cadence,all5 physical audit and all unknown/error denominators.',
            'failure': 'Original full failure-aware saved audit remains mandatory. Invalid/audit_error stays failure; reported roots and physical facts are retained separately. Provider setup/close failure never permits a completed receipt.',
            'scope': 'Source/synthetic gate preparation is not actual C support, native timing, method improvement or protection evidence.'}
        c.write(output/'campaign.json', plan)
        c.write(output/'branch_ledger.json', {key: {**plan['rows'][key], 'status': 'unknown_unexecuted'}
            for key in plan['row_order']})
        expected = c.sha(output/'campaign.json'); c.verify_plan(output, expected)
        c.require(c.runtime.verify_files(provider_contract) == files_before, 'owned_prepare_C_exit')
        for name, digest in sources.items():
            c.require(c.sha(c.ROOT/name) == c.sha(targets[name]) == digest, 'owned_prepare_exit_source')
        checked_pure(pure_directory); pure.frozen()
        result = {'schema': c.SCHEMA, 'status': 'prepared_source_review_pending',
            'campaign': c.reference(output/'campaign.json'), 'sources': len(sources), 'compiled_native_sources': 67,
            'C_toolchain_files': 6124, 'focused_synthetic_tests': receipt['tests'],
            'archive_keys': 'canonical ROOT-relative, contained independent targets',
            'native_calls': 0, 'C_loads': 0, 'model_calls': 0, 'performance_runs': 0,
            'actual_direct_C_supported': None, 'not_dispatched': True,
            'execute_command': [sys.executable, '-m', __package__+'.launch_initial_owner_route_single_capture_owned_codec_campaign',
                '--output', str(output), '--campaign-sha256', expected],
            'external_measured_wrapper_required': True}
        c.write(output/'source_preparation.json', result); return result
    except BaseException as error:
        c.write(output/'preparation_failure.json', {'status': 'failed_preparation', 'error': repr(error),
            'native_calls': 0, 'C_loads': 0, 'model_calls': 0, 'partial_artifacts_retained': True})
        raise


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pure-directory', type=Path, required=True)
    args = parser.parse_args(); print(prepare(args.output, args.pure_directory))


if __name__ == '__main__': main()
