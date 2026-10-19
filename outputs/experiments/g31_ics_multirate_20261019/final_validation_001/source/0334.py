"""Unexecuted preparation draft for the same18/600 static-inventory trial.

Requires a separately reviewed owned120 focused-pure receipt. No native, model
or C load is performed here. All inherited keys are canonicalized before union;
every archive/input/metadata target is checked before the first archive write.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from . import initial_owner_route_static_inventory_campaign as c
from . import verify_initial_owner_route_static_inventory_campaign as v
from . import prepare_single_capture_owned_codec_campaign as previous
from . import run_static_root_inventory_pure as archive

MODULE = __package__ + '.prepare_initial_owner_route_static_inventory_campaign'
TEST = 'tests/test_g31_circulation_static_inventory_campaign.py'
PURE_MODULE = __package__ + '.run_static_inventory_campaign_pure'
PURE_RUNNER = 'scripts/experiments/g31_ics_circulation/run_static_inventory_campaign_pure.py'
PURE_WRAPPER = 'outputs/invoke_sicp1.ps1'
PURE_FIXED_SOURCES = (
    'scripts/experiments/g31_ics_circulation/single_capture_static_inventory_runtime.py',
    'scripts/experiments/g31_ics_circulation/initial_owner_route_static_inventory_campaign.py',
    'scripts/experiments/g31_ics_circulation/verify_initial_owner_route_static_inventory_campaign.py',
    'scripts/experiments/g31_ics_circulation/launch_initial_owner_route_static_inventory_campaign.py',
    'scripts/experiments/g31_ics_circulation/prepare_initial_owner_route_static_inventory_campaign.py',
    PURE_RUNNER, TEST)
BASE = c.OUT/'single_owned_C18_prepare_002/campaign.json'
BASE_SHA = '4ac4569ad5145ccf62e83a39d29ad238077bf00fa0657c130fb12916cfb91bdc'
STATIC = c.ROOT/'outputs/sinv1/plan.json'
STATIC_SHA = 'd0b4f0748883bdc71f5205db3b8bd326348503ff306bb93491c88a52d3427a81'
STATIC_RECEIPT = c.ROOT/'outputs/sinv1/receipt.json'
STATIC_RECEIPT_SHA = '070ede5d12a02534b70ea5cbb4759c3651d0d1dd4fc8e10bbea045baecb677ea'
STATIC_REVIEW = c.ROOT/'outputs/sinv1/root_saved_review_001.json'
STATIC_REVIEW_SHA = '7f3a5b27b48e3e2877902167c2ed1a070252410b53a6c7032c07d580d6368fed'


def pure_outer_gate(directory, plan, receipt, parent, outer):
    directory = Path(directory).resolve()
    expected = [sys.executable, '-m', PURE_MODULE, '--output', str(directory)]
    environment = {'PYTHONPATH': 'src;.;tests', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
        'PYTHONIOENCODING': 'utf-8'}
    c.require(plan['output_directory'] == str(directory) and plan['command'] == expected
        and plan['test_file'] == TEST and plan['shared_seconds'] == 120.
        and plan['environment'] == environment
        and plan['python'] == {'path': sys.executable, 'sha256': archive.PYTHON_SHA},
        'static_prepare_pure_plan_execution')
    c.require(parent['command'] == expected and parent['output_directory'] == str(directory)
        and parent['receipt_sha256'] == c.sha(directory/'receipt.json')
        and parent['status'] == 'passed' and parent['shared_seconds'] == 120.
        and parent['process']['status'] == 'exited'
        and type(parent['process']['exitcode']) is int and parent['process']['exitcode'] == 0
        and parent['process']['windows_job_kill_on_close'] is True
        and parent['process']['child_released_only_after_job_assignment'] is True,
        'static_prepare_pure_parent_chain')
    c.require(outer['schema'] == 'g31.static_inventory_campaign_pure.external.v1'
        and outer['status'] == 'exited_zero' and outer['command'] == expected
        and outer['cwd'] == str(c.ROOT.resolve()) and outer['output_directory'] == str(directory)
        and type(outer['exitcode']) is int and outer['exitcode'] == 0
        and type(outer['wrapper_exitcode']) is int and outer['wrapper_exitcode'] == 0
        and outer.get('exception') is None and outer['python_launch_attempted'] is True
        and outer['fixed_source_entry_passed'] is outer['fixed_source_exit_passed'] is True
        and outer['environment'] == environment, 'static_prepare_pure_external_execution')
    frequency, ticks, seconds = (outer[name] for name in
        ('stopwatch_frequency', 'elapsed_ticks', 'external_application_seconds'))
    c.require(type(frequency) is int and frequency > 0 and type(ticks) is int
        and 0 < ticks <= 120*frequency and type(seconds) in (int, float)
        and math.isfinite(seconds) and seconds == float(ticks)/float(frequency)
        and outer['clock_scope'] == 'immediately_before_python_launch_through_process_return_including_python_startup_and_exit',
        'static_prepare_pure_typed_whole_clock')
    for value in (parent['process']['wall_seconds'], parent['process']['hard_timeout_seconds'],
                  parent['post_interpreter_before_parent_export_seconds'],
                  outer['wrapper_before_final_receipt_seconds']):
        c.require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 120.,
            'static_prepare_pure_all_clock_bounds')
    c.require(parent['process']['wall_seconds'] <= seconds
        and parent['post_interpreter_before_parent_export_seconds'] <= seconds
        and seconds <= outer['wrapper_before_final_receipt_seconds'],
        'static_prepare_pure_nested_whole_clocks')
    names = ('plan.json', 'collection.json', 'receipt.json', 'tests.xml',
        'bounded_parent_receipt.json', 'worker.stdout.log', 'worker.stderr.log')
    c.require(outer['outputs'] == {name: c.reference(directory/name) for name in names},
        'static_prepare_pure_complete_outputs')
    c.require(outer['python_sha256'] == outer['python_after_sha256'] == c.sha(sys.executable)
        == archive.PYTHON_SHA and outer['wrapper'] == plan['wrapper'] == c.reference(c.ROOT/PURE_WRAPPER)
        and outer['wrapper_after_sha256'] == outer['wrapper']['sha256']
        and outer['runner'] == c.reference(c.ROOT/PURE_RUNNER)
        and outer['runner_after_sha256'] == outer['runner']['sha256'],
        'static_prepare_pure_interpreter_wrapper_runner')
    c.require(set(outer['fixed_source_pins']) == set(PURE_FIXED_SOURCES),
        'static_prepare_pure_fixed_pin_domain')
    for name in PURE_FIXED_SOURCES:
        pin = outer['fixed_source_pins'][name]
        c.require(pin == {'path': str(c.ROOT/name), 'expected_sha256': plan['source_sha256'][name],
            'entry_sha256': plan['source_sha256'][name], 'entry_matches': True,
            'exit_sha256': plan['source_sha256'][name], 'exit_matches': True},
            'static_prepare_pure_fixed_entry_exit:' + name)
    c.require(plan['source_sha256'][PURE_WRAPPER] == outer['wrapper']['sha256']
        and plan['source_sha256'][PURE_RUNNER] == outer['runner']['sha256'],
        'static_prepare_pure_archived_wrapper_runner')
    for name in ('native_calls', 'model_predictions', 'custom_C_loads', 'actual_raw_reads'):
        c.require(type(outer[name]) is int and outer[name] == 0 and type(parent[name]) is int
            and parent[name] == 0 and type(receipt[name]) is int and receipt[name] == 0,
            'static_prepare_pure_external_scope')


def checked_pure(directory):
    directory = Path(directory).resolve()
    receipt, plan = c.read(directory/'receipt.json'), c.read(directory/'plan.json')
    collected = c.read(directory/'collection.json')
    cases = ET.parse(directory/'tests.xml').getroot().findall('.//testcase')
    c.require(receipt['status'] == 'passed' and receipt['pytest_exitcode'] == 0
        and receipt['source_changed'] == receipt['final_source_changed'] == []
        and collected['recorded_before_execution'] is True
        and collected['test_file'] == TEST and len(collected['nodeids']) > 0
        and len(set(collected['nodeids'])) == len(collected['nodeids'])
        and collected['count'] == receipt['collected_tests'] == receipt['XML_tests'] == len(cases)
        and not any(n.tag in ('failure', 'error', 'skipped') for row in cases for n in row),
        'static_prepare_focused_pure')
    for name, field in [('plan.json', 'plan_sha256'), ('tests.xml', 'XML_sha256'),
                        ('collection.json', 'collection_sha256')]:
        c.require(c.sha(directory/name) == receipt[field], 'static_prepare_pure_reference')
    for name in ('native_calls', 'model_predictions', 'custom_C_loads', 'actual_raw_reads', 'performance_runs'):
        c.require(receipt[name] == 0, 'static_prepare_pure_scope')
    pins, saved = plan['source_sha256'], plan['source_archive']
    c.require(set(pins) == set(saved), 'static_prepare_pure_source_domain')
    for name, digest in pins.items():
        current, target = (c.ROOT/name).resolve(), (directory/saved[name]).resolve()
        c.require(not Path(name).is_absolute() and current.is_relative_to(c.ROOT)
            and name == current.relative_to(c.ROOT).as_posix()
            and saved[name] == 'source/' + name
            and target.is_relative_to((directory/'source').resolve())
            and current != target and c.sha(current) == c.sha(target) == digest,
            'static_prepare_pure_sources')
    for field in ('loaded_entry', 'loaded_exit'):
        c.require(all(name in pins and pins[name] == digest
            for name, digest in receipt[field].items()), 'static_prepare_pure_loaded')
    outer = c.read(directory/'external_application_wall.json')
    parent = c.read(directory/'bounded_parent_receipt.json')
    pure_outer_gate(directory, plan, receipt, parent, outer)
    return receipt, plan


def source_files(pure_directory):
    pure_plan = Path(pure_directory)/'plan.json'
    # The inherited union routine only READS old archives. It explicitly
    # resolves absolute and relative keys to one ROOT-relative identity.
    refs = ((BASE, BASE_SHA), (STATIC, STATIC_SHA), (pure_plan, c.sha(pure_plan)))
    files = previous.union_sources(refs)
    closure = c.image.source_closure(c.ROOT, (MODULE,
        __package__+'.initial_owner_route_static_inventory_campaign',
        __package__+'.single_capture_static_inventory_runtime',
        __package__+'.verify_initial_owner_route_static_inventory_campaign',
        __package__+'.launch_initial_owner_route_static_inventory_campaign',
        TEST[:-3].replace('/', '.')))
    for name, data in archive.canonical_sources(closure).items():
        c.require(name not in files or files[name] == data, 'static_prepare_union_conflict')
        files[name] = data
    return archive.canonical_sources(files)


def all_targets(output, files, original):
    output = Path(output).resolve()
    targets = archive.archive_targets(c.ROOT, output, files)
    names = ['campaign.json', 'branch_ledger.json', 'source_preparation.json', 'preparation_failure.json',
        'C_provider_lifetime.json', 'static_inventory_lifetime.json', 'verification.json', 'receipt.json',
        'external_launch_receipt.json', 'actual_external_application_wall.json']
    names += ['inputs/' + key + '.json' for key in original['row_order']]
    seen = set(targets.values())
    for name in names:
        target = (output/name).resolve()
        c.require(target.is_relative_to(output) and len(str(target)) < 260
            and target not in seen and not target.exists(), 'static_prepare_all_target_preflight')
        seen.add(target)
    return targets


def prepare(output, pure_directory):
    output, pure_directory = Path(output).resolve(), Path(pure_directory).resolve()
    c.require(output.is_relative_to((c.ROOT/'outputs').resolve()), 'static_prepare_output')
    output.mkdir(parents=True, exist_ok=False)
    try:
        focused, _ = checked_pure(pure_directory)
        for path, digest in ((STATIC_RECEIPT, STATIC_RECEIPT_SHA), (STATIC_REVIEW, STATIC_REVIEW_SHA)):
            c.require(c.sha(path) == digest, 'static_prepare_frozen_static_evidence')
        files = source_files(pure_directory)
        original = c.read(BASE)
        targets = all_targets(output, files, original)
        # All input contents are also pinned before creating the first archive.
        input_bytes = {}
        for key in original['row_order']:
            value = (BASE.parent/'inputs'/(key+'.json')).read_bytes()
            c.require(hashlib.sha256(value).hexdigest() == original['input_file_sha256'][key],
                'static_prepare_input_pin')
            input_bytes[key] = value
        archives = archive.archive_sources(c.ROOT, output, files)
        sources = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
        C_contract = c.runtime.metadata()
        C_before = c.runtime.verify_files(C_contract)
        plan = copy.deepcopy(original)
        plan.update(schema=c.SCHEMA, source_sha256=sources, source_archive=archives,
            static_inventory_campaign_source_proof=c.source_proof(),
            static_inventory_saved_source_proof=v.source_proof(),
            frozen_owned_C18_campaign=c.reference(BASE), static_inventory_pure_plan=c.reference(STATIC),
            static_inventory_pure_receipt=c.reference(STATIC_RECEIPT),
            static_inventory_root_saved_review=c.reference(STATIC_REVIEW),
            static_inventory_campaign_pure_receipt=c.reference(pure_directory/'receipt.json'),
            static_inventory_campaign_pure_plan=c.reference(pure_directory/'plan.json'),
            static_inventory_campaign_pure_XML=c.reference(pure_directory/'tests.xml'),
            static_inventory_campaign_pure_outer=c.reference(pure_directory/'external_application_wall.json'),
            environment={'interpreter': sys.executable, 'interpreter_sha256': c.sha(sys.executable),
                'version': sys.version}, status='prepared_for_root_review_no_execution')
        c.require(plan['C_provider'] == C_contract, 'static_prepare_C_contract_changed')
        plan['static_inventory_amendment'] = {
            'change': 'Only cold static inventory reuse plus a private constructor-call timer; the exact reviewed static class still runs every root dynamic guard.',
            'constructor_sidecar': 'static_inventory_lifetime.json',
            'timing': 'Cold binding remains in original C setup/full600. Constructor call span is nested full wall, not CPU or isolated inventory. Metadata/clock/append overhead remains in root; sidecar writes at original provider save sites remain in whole.',
            'unchanged': 'Same18/600, original60ms selection/100ms root, exact current/native/session/ledger/ACK/firsthop/drain/RPC/fullphysical/evidence and unknown denominator.',
            'C_checks': 'Original module/spec/loader/actualDLL entry/exit and three runtime6124 checks retained. Original fallback remains; actual direct/fallback counts unknown.',
            'cleanup': 'Private code/class cycles may survive samples; no per-root reclamation or unload certificate.',
            'failure': 'Malformed/missing constructor proof fails saved audit after the complete original per-row checks. Earlier actual branch failures retain missing-constructor unknown, never zero cost.',
            'external_receipt': 'Use a new actual receipt name and bind both C_provider_lifetime.json and static_inventory_lifetime.json in addition to original launcher artifacts.'}
        for key, value in input_bytes.items():
            target = output/'inputs'/(key+'.json'); target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream: stream.write(value)
        c.write(output/'campaign.json', plan)
        c.write(output/'branch_ledger.json', {key: {**plan['rows'][key], 'status': 'unknown_unexecuted'}
            for key in plan['row_order']})
        expected = c.sha(output/'campaign.json'); c.verify_plan(output, expected)
        c.require(c.runtime.verify_files(C_contract) == C_before, 'static_prepare_C_exit')
        for name, digest in sources.items():
            c.require(c.sha(c.ROOT/name) == c.sha(targets[name]) == digest, 'static_prepare_exit_source')
        checked_pure(pure_directory)
        result = {'schema': c.SCHEMA, 'status': 'prepared_source_review_pending',
            'campaign': c.reference(output/'campaign.json'), 'sources': len(sources),
            'compiled_native_sources': 67, 'C_toolchain_files': 6124,
            'focused_synthetic_tests': focused['collected_tests'], 'native_calls': 0,
            'C_loads': 0, 'model_calls': 0, 'performance_runs': 0, 'not_dispatched': True,
            'execute_command': [sys.executable, '-m', __package__+'.launch_initial_owner_route_static_inventory_campaign',
                '--output', str(output), '--campaign-sha256', expected],
            'external_measured_wrapper_required': True}
        c.write(output/'source_preparation.json', result)
        return result
    except BaseException as error:
        c.write(output/'preparation_failure.json', {'status': 'failed_preparation', 'error': repr(error),
            'native_calls': 0, 'C_loads': 0, 'model_calls': 0, 'partial_artifacts_retained': True})
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pure-directory', type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.output, args.pure_directory))


if __name__ == '__main__': main()
