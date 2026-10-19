"""DRAFT: separate600 saved bridge audit with the accepted private C digest.

No execution is authorized by importing or preparing this module. The original
producer and every earlier saved-audit failure remain unchanged. The C encoder
is not a simulator: this audit creates no native session and no prediction.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import ast
import hashlib
import inspect
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from . import audit_bridge_saved_text_actor as previous
from . import bridge_saved_c_digest as digest_core
from . import planning_v2_c_encoder_authority as authority
from . import run_bridge_saved_c_digest_pure_v2 as routing_gate

ROOT, OUT, base, r, prior, require = (previous.ROOT, previous.OUT, previous.base,
                                    previous.r, previous.prior, previous.require)
flow = previous.previous.old
SCHEMA = 'g31.bridge.saved_C_digest_audit.v1'
MODULE = 'scripts.experiments.g31_ics_circulation.audit_bridge_saved_c_digest'
TEST = 'tests/test_g31_circulation_bridge_saved_c_digest_driver.py'
LIMIT = 600.
FAILED = OUT / 'bridge_saved_text_actor_prepare_001'
FAILED_PLAN = '6a56cee53dc46444a96815210076863e37738f449f73b50e845c48d39e887f4a'
FAILED_EXTERNAL = '8215f25b11efe738bece294b5c9fc98d05a66d28095f5ba2eed44770979940b1'
PURE = OUT / 'bcp2'
DRIVER_PURE = OUT / 'bcdp1'
DRIVER_PURE_MODULE = 'scripts.experiments.g31_ics_circulation.run_bridge_saved_c_digest_driver_pure'
DRIVER_PURE_SCHEMA = 'g31.bridge.saved_C_digest.driver_pure.v1'
PURE_PINS = {
    'receipt.json': '174838c6c05a7893f5b8f600ba623c84e72c49126b315c9a9384c7e19f1b9392',
    'tests.xml': '041bcf7871cafeb097cc1dec76330ab8804ac9e8de982f99db760d744b18575c',
    'worker.json': '93bcb28489bf3ae218b55ff3413abe317e1132dbac54d8c5f19cb408f5fec15e',
    'plan.json': '9fd532c6051eefa0c1446fbe958a413e320a73f6dfec98e0ddd5e4a63987b780',
    'bounded_execution.json': '194fa100971e8be6075e941cff2ff446e0e706da2ee94aee7165f7c49e28f7f8',
    'external_application_wall.json': 'af80bdd5c93b9db0507bf8c043ba17e7c6f7803ea5b029a9d51f58738a3f1918',
    'root_saved_review_001.json': '4db25792478f03dac007cc6466148c4ddc55fce98407ee2f551bb2c974b7df7c',
}
_AUDIT = flow.audit
_AUDIT_CODE = _AUDIT.__code__


def relative_sources(plan):
    """Explicit old-audit plus C/manual/project union; no blanket whitelist."""
    result = {}
    for name, digest in plan['source_before'].items():
        path = Path(name)
        require(path.is_absolute() and path.resolve() == path
                and path.is_relative_to(ROOT), 'C_audit_canonical_source')
        relative = path.relative_to(ROOT).as_posix()
        require(relative not in result, 'C_audit_duplicate_source')
        result[relative] = digest
    return result


def check_routing_pure(receipt_path):
    require(Path(receipt_path).resolve() == (PURE / 'receipt.json').resolve(),
            'C_audit_fixed_routing_gate')
    for name, digest in PURE_PINS.items():
        require(base.sha(PURE / name) == digest, 'C_audit_pure_pin:' + name)
    receipt = base.read(PURE / 'receipt.json')
    worker = base.read(PURE / 'worker.json')
    bounded = base.read(PURE / 'bounded_execution.json')
    external = base.read(PURE / 'external_application_wall.json')
    cases = ET.parse(PURE / 'tests.xml').getroot().findall('.//testcase')
    require(receipt['schema'] == routing_gate.SCHEMA
            and receipt['status'] == 'passed_synthetic_routing'
            and type(receipt['tests']) is int and receipt['tests'] == 37
            and receipt['expected_tests'] == 37 and len(cases) == 37
            and receipt['bad_tests'] == [] and receipt['error'] is None
            and not any(c.tag in ('failure', 'error', 'skipped') for t in cases for c in t),
            'C_audit_routing_pure_outcome')
    require(receipt['process'] == bounded and bounded['status'] == 'exited'
            and type(bounded['exitcode']) is int and bounded['exitcode'] == 0
            and bounded['windows_job_kill_on_close'] is True
            and bounded['child_released_only_after_job_assignment'] is True
            and worker['pytest_exitcode'] == 0 and worker['source_entry_exit_exact'] is True,
            'C_audit_pure_owned_and_worker')
    for value in (receipt, worker):
        require(value['native_calls'] == value['extension_loads'] == value['actual_fixture_reads'] == 0,
                'C_audit_pure_scope')
    ticks, frequency = external['elapsed_ticks'], external['tick_frequency']
    wall = external['whole_python_seconds']
    require(type(ticks) is int and ticks >= 0 and type(frequency) is int and frequency > 0
            and ticks <= 120 * frequency and type(wall) in (int, float)
            and math.isfinite(wall) and abs(wall - ticks / frequency) <= 1e-9
            and external['end_ticks'] - external['start_ticks'] == ticks,
            'C_audit_pure_external_clock')
    require(external['accepted_launch_and_clock'] is True and external['source_changed'] == []
            and type(external['exit_code']) is int and external['exit_code'] == 0
            and external['outer_timeout'] is False and external['exception'] is None
            and external['cleanup_errors'] == [] and external['missing_outputs'] == [],
            'C_audit_pure_external_outcome')
    require(external['command'] == [external['python']['path'], '-m', routing_gate.MODULE,
                                   '--output', str(PURE)]
            and external['environment_explicit'] == {'PYTHONPATH': 'src;.;tests',
                'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONIOENCODING': 'utf-8'},
            'C_audit_pure_exact_command_environment')
    for field in ('python', 'wrapper'):
        item = external[field]
        require(base.sha(item['path']) == item['sha256'], 'C_audit_pure_' + field)
    for name, digest in external['output_sha256'].items():
        require(base.sha(PURE / name) == digest, 'C_audit_pure_output:' + name)
    require(receipt['XML_sha256'] == PURE_PINS['tests.xml']
            and receipt['worker_sha256'] == PURE_PINS['worker.json'], 'C_audit_pure_bindings')
    for name, digest in receipt['source_sha256'].items():
        require(base.sha(ROOT / name) == base.sha(PURE / 'source' / name) == digest,
                'C_audit_pure_source:' + name)
    return {str(PURE / name): digest for name, digest in PURE_PINS.items()}


def latest_failure():
    require(base.sha(FAILED / 'plan.json') == FAILED_PLAN
            and base.sha(FAILED / 'external_application_wall.json') == FAILED_EXTERNAL,
            'C_audit_previous_failure_identity')
    value = base.read(FAILED / 'bounded_execution.json')
    require(value['process']['status'] == 'hard_timeout'
            and value['process']['windows_job_kill_on_close'] is True
            and not (FAILED / 'report.json').exists(), 'C_audit_previous_timeout')
    for name, digest in base.read(FAILED / 'plan.json')['source_before'].items():
        require(base.sha(name) == base.sha(FAILED / 'source' / Path(name).relative_to(ROOT)) == digest,
                'C_audit_previous_frozen_source')
    return {str(FAILED / name): base.sha(FAILED / name) for name in
            ('plan.json', 'bounded_execution.json', 'external_application_wall.json', 'progress.jsonl')}


def closure():
    # The old manual roots (including bare test helpers), all C gate16, bcp2's
    # complete115 and this driver/test are explicit roots. No extension load.
    paths = set(previous.closure())
    paths.update(ROOT / name for name in routing_gate.sources())
    for entry in (Path(__file__), ROOT / TEST,
                  ROOT / (DRIVER_PURE_MODULE.replace('.', '/') + '.py')):
        paths.update(r.original.clone(base.source_paths,
            {**base.source_paths.__globals__, '__file__': str(entry)})())
    return sorted(paths)


def source_files():
    # This collector never reads this driver's future pure receipt or calls
    # contract()/prepare(). The runner can freeze it before that receipt exists.
    return {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in closure()}


def check_driver_pure(receipt_path):
    """Independent12 required in addition to accepted bcp2; never reruns37."""
    directory = Path(receipt_path).resolve().parent
    require(Path(receipt_path).resolve() == DRIVER_PURE / 'receipt.json', 'driver_pure_fixed_output')
    receipt = base.read(directory / 'receipt.json')
    plan = base.read(directory / 'plan.json')
    worker = base.read(directory / 'worker.json')
    process = base.read(directory / 'bounded_execution.json')
    outer = base.read(directory / 'external_application_wall.json')
    cases = ET.parse(directory / 'tests.xml').getroot().findall('.//testcase')
    require(receipt['schema'] == plan['schema'] == DRIVER_PURE_SCHEMA
            and receipt['status'] == 'passed_synthetic_routing'
            and type(receipt['tests']) is int and receipt['tests'] == 12
            and type(receipt['expected_tests']) is int and receipt['expected_tests'] == 12
            and type(plan['tests']) is int and plan['tests'] == 12
            and plan['limit_seconds'] == 120 and len(cases) == 12
            and receipt['bad_tests'] == [] and receipt['error'] is None
            and not any(c.tag in ('failure', 'error', 'skipped') for t in cases for c in t),
            'driver_pure_twelve_complete')
    require(receipt['process'] == process and process['status'] == 'exited'
            and type(process['exitcode']) is int and process['exitcode'] == 0
            and process['windows_job_kill_on_close'] is True
            and process['child_released_only_after_job_assignment'] is True
            and type(worker['pytest_exitcode']) is int and worker['pytest_exitcode'] == 0
            and worker['source_entry_exit_exact'] is True, 'driver_pure_owned_result')
    for value in (receipt, worker):
        for field in ('native_calls', 'extension_loads', 'actual_fixture_reads'):
            require(type(value[field]) is int and value[field] == 0, 'driver_pure_no_actual:' + field)
    require(receipt['benchmark_executed'] is False, 'driver_pure_no_benchmark')
    ticks, frequency, wall = outer['elapsed_ticks'], outer['tick_frequency'], outer['whole_python_seconds']
    require(type(ticks) is int and ticks > 0 and type(frequency) is int and frequency > 0
            and ticks <= 120 * frequency and type(outer['budget_ticks']) is int
            and outer['budget_ticks'] == 120 * frequency
            and type(outer['start_ticks']) is int and type(outer['end_ticks']) is int
            and outer['end_ticks'] - outer['start_ticks'] == ticks
            and type(wall) in (int, float) and math.isfinite(wall)
            and abs(wall - ticks / frequency) <= 1e-9, 'driver_pure_typed_full_clock')
    require(outer['schema'] == 'g31.bridge.saved_C_digest.driver_pure_external.v1'
            and outer['started'] is True and outer['accepted_launch_and_clock'] is True
            and type(outer['exit_code']) is int and outer['exit_code'] == 0
            and outer['source_changed'] == [] and outer['outer_timeout'] is False
            and outer['exception'] is None and outer['cleanup_errors'] == []
            and outer['missing_outputs'] == [] and outer['expected_tests'] == 12,
            'driver_pure_full_external_status')
    python = str(authority.gate.old.PYTHON)
    require(outer['command'] == [python, '-m', DRIVER_PURE_MODULE, '--output', str(directory)]
            and outer['working_directory'] == str(ROOT)
            and outer['python']['path'] == python
            and outer['environment_explicit'] == {'PYTHONPATH': 'src;.;tests',
                'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONIOENCODING': 'utf-8'},
            'driver_pure_exact_application')
    require(plan['command'] == [python, '-m', DRIVER_PURE_MODULE, '--output', str(directory),
                              '--worker', '--admission', plan['admission']],
            'driver_pure_owned_child_command')
    for field in ('python', 'wrapper'):
        item = outer[field]
        require(type(item) is dict and set(item) == {'path', 'sha256'}
                and base.sha(item['path']) == item['sha256'], 'driver_pure_identity:' + field)
    names = ('plan.json', 'receipt.json', 'worker.json', 'bounded_execution.json',
             'tests.xml', 'parent_stdout.log', 'parent_stderr.log')
    require(outer['output_sha256'] == {name: base.sha(directory / name) for name in names},
            'driver_pure_all_outputs')
    require(receipt['XML_sha256'] == base.sha(directory / 'tests.xml')
            and receipt['worker_sha256'] == base.sha(directory / 'worker.json'), 'driver_pure_inner_refs')
    current = source_files()  # No call back into this checker or a future plan.
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in current.items()}
    require(receipt['source_sha256'] == plan['source_sha256'] == hashes, 'driver_pure_exact_source_domain')
    archive = routing_gate.old.reference
    archive.archive_targets(directory, current, False)
    for name, digest in hashes.items():
        require(base.sha(ROOT / name) == base.sha(directory / 'source' / name) == digest,
                'driver_pure_current_archive:' + name)
    new_names = (Path(__file__).resolve().relative_to(ROOT).as_posix(), TEST,
                 DRIVER_PURE_MODULE.replace('.', '/') + '.py')
    require(outer['source_sha256'] == {name: hashes[name] for name in new_names},
            'driver_pure_outer_three_source_domain')
    for loaded in (worker['loaded_entry'], worker['loaded_exit'], receipt['loaded_parent_exit']):
        require(type(loaded) is list and all(type(name) is str for name in loaded)
                and len(loaded) == len(set(loaded)) and set(loaded) <= set(hashes),
                'driver_pure_exact_loaded_domain')
    return {name: {'path': str(directory / name), 'sha256': base.sha(directory / name)}
            for name in (*names, 'external_application_wall.json')}


def audit_source():
    """Four explicit insertions; inverse text/AST proves all old checks remain."""
    require(flow.audit is _AUDIT and _AUDIT.__code__ is _AUDIT_CODE, 'C_audit_original_flow')
    original = inspect.getsource(_AUDIT)
    replacements = (
        ("        redirect = prior.DerivedOutput(prior.SOURCE, output)\n",
         "        with progress.stage('C_encoder_entry_full_dependency_and_load_checks'):\n"
         "            candidate, C_entry = authority.begin(relative_sources(plan))\n"
         "            prior.write_new(output/'C_encoder_entry.json', C_entry)\n"
         "        redirect = prior.DerivedOutput(prior.SOURCE, output)\n"),
        ("checker = core.bind(plan, redirect, progress)",
         "checker = core.bind(plan, redirect, progress, candidate)"),
        ("        with progress.stage('exit_plan_source_artifact_and_runtime_checks'):\n",
         "        with progress.stage('C_encoder_exit_full_dependency_and_identity_checks'):\n"
         "            C_exit = authority.finish(candidate, relative_sources(plan))\n"
         "            prior.write_new(output/'C_encoder_exit.json', C_exit)\n"
         "        with progress.stage('exit_plan_source_artifact_and_runtime_checks'):\n"),
        ("'optimization_evidence':statistics,",
         "'C_encoder':{'entry':C_entry,'exit':C_exit,'extension_loads':1,\n"
         "            'actual_direct_and_fallback_counts':'not_instrumented_unknown',\n"
         "            'scope':'Same accepted Candidate dispatcher; unsupported falls back once. No simulator session.',\n"
         "            'resource_exception_equivalence':False},\n"
         "        'optimization_evidence':statistics,"),
    )
    generated = original
    for before, after in replacements:
        require(generated.count(before) == 1, 'C_audit_unique_insertion')
        generated = generated.replace(before, after)
    inverse = generated
    for before, after in reversed(replacements):
        require(inverse.count(after) == 1, 'C_audit_unique_inverse')
        inverse = inverse.replace(after, before)
    require(inverse == original and ast.dump(ast.parse(inverse), include_attributes=False)
            == ast.dump(ast.parse(original), include_attributes=False), 'C_audit_inverse_original_flow')
    return generated, {'original_source_sha256': hashlib.sha256(original.encode()).hexdigest(),
        'generated_source_sha256': hashlib.sha256(generated.encode()).hexdigest(),
        'inverse_original_text_and_AST_exact': True, 'explicit_modifications': 4,
        'all_old_statements_and_full_globals_preserved': True}


def contract():
    inherited = previous.contract()
    require(base.sha(OUT / digest_core.C32_REVIEW) == digest_core.C32_REVIEW_SHA, 'C_audit_C32_review')
    _, proof = audit_source()
    return {'fixed_seconds': 600, 'new_rows': 37270, 'old_complete_prefix_rows': 27218,
        'offered_jobs': 28506, 'trays': 22, 'audit_flow': proof,
        'routing': digest_core._bundle(digest_core.base.capture_digest_v2).prove(),
        'historical_text_actor_contract': inherited, 'latest_timeout': latest_failure(),
        'routing_pure': check_routing_pure(PURE / 'receipt.json'),
        'C_authority': authority.references(),
        'C32_root_review': {'path': str(OUT / digest_core.C32_REVIEW), 'sha256': digest_core.C32_REVIEW_SHA},
        'change': 'Only the original typed-v2 digest dependency in the proven private policy bundle uses the accepted C Candidate; all validator guards and expiry order still execute.',
        'unchanged': ['All37270 new and27218 old row hashes, ordered arguments/results and clocks',
            'All28506 jobs/22trays, complete policy/FIFO/Storage/ACK/cap/physical checks',
            'Same-text actor parse, original C semantic comparisons, observer identity, readonly shared raw/input',
            'All policy client refresh, own-capture and PossessionGate copies; no extra copy-scope candidate',
            'Original source/archive026/binary/manifest/input pins and single derived output redirect',
            'Original progress1024/256row cadence and sticky first instrumentation failure'],
        'cost': {'fixed': 'One separate600 including startup, authority entry/exit7779+3082 hashes, C loading, all saved checks/exports and exit; external full Python ticks required.',
            'evidence': 'C32 measured only two late absent inputs: original33.2986/56.4458ms versus C8.40715/12.7397ms. This does not establish successful-validator mix, whole-stream frequency or600 completion.',
            'added_dependency_checks': 'C32 entry46.2124s and exit50.0233s were observed separately in that run; not a fixed prediction or deductible cost here.'},
        'limits': ['Previous producer2400 and every saved600 failure stay failed.',
            'Default decoder domain/original guards retained; second parse and C resource/signal failure timing may differ and remain unknown.',
            'No per-digest direct/fallback counters added to the whole audit; actual mix remains unmeasured.',
            'No native replay,100ms claim, whole-offered success or new input permission.'],
        'prelaunch_status': 'Driver source draft; no new saved audit executed.'}


def namespace():
    # previous supplies the full inherited namespace, including Path and every
    # nested function dependency. Mutate only this fresh dictionary.
    values = previous.namespace()
    values.update(BOOT=BOOT, SCHEMA=SCHEMA, MODULE=MODULE, TEST=TEST, LIMIT=LIMIT,
        core=audit_core(), authority=authority, relative_sources=relative_sources,
        closure=closure, contract=contract, namespace=namespace, verify_plan=verify_plan,
        prepare=prepare, audit=audit, pure=reject_unregistered_pure)
    return values


def audit_core():
    # The frozen digest binder deliberately exports no progress class. Add the
    # exact existing progress class to a private facade only.
    return SimpleNamespace(**{**vars(digest_core), 'Progress': digest_core.previous.Progress})


def audit_function():
    source, _ = audit_source()
    values = namespace()
    exec(compile(source, str(Path(__file__).resolve()) + ':generated_audit', 'exec'), values)
    return values['audit']


def verify_plan(output, expected):
    # Original verify_plan still rehashes every large original input/reference
    # on entry and exit, and checks all current/archive and pure references.
    plan = r.original.clone(flow.verify_plan, namespace())(output, expected)
    require(plan['driver_pure'] == check_driver_pure(Path(plan['pure']['path'])),
            'C_audit_driver_pure_recheck')
    return plan


def prepare(output, pure_receipt):
    # Metadata only. Inherit large evidence hashes from the exact failed plan;
    # do not re-read1.34GB or claim that execution's full checks occurred here.
    output = Path(output).resolve()
    require(not output.exists(), 'C_audit_preserve_output')
    driver_pure = check_driver_pure(pure_receipt)
    pure_refs = check_routing_pure(PURE / 'receipt.json')
    failure = latest_failure()
    plan = base.read(FAILED / 'plan.json')
    value = contract()
    files = source_files()
    archive = routing_gate.old.reference
    archive.archive_targets(output, files, True)  # Full-domain check before any write.
    output.mkdir()
    archive.archive_sources(output, files)
    pins = {str(ROOT / name): hashlib.sha256(data).hexdigest() for name, data in files.items()}
    for name, digest in pins.items():
        require(base.sha(name) == base.sha(output / 'source' / Path(name).relative_to(ROOT)) == digest,
                'C_audit_prepare_source_drift')
    plan.update(schema=SCHEMA, source_before=pins, linear_contract=value,
        pure={'path': driver_pure['receipt.json']['path'], 'sha256': driver_pure['receipt.json']['sha256'],
              'XML_path': driver_pure['tests.xml']['path'], 'XML_sha256': driver_pure['tests.xml']['sha256']},
        driver_pure=driver_pure,
        interpreter={'path': sys.executable, 'sha256': base.sha(sys.executable)},
        preparation_scope={'large_evidence_reads': 0, 'large_hash_source': failure,
            'mandatory_full_recheck': 'At actual owned600 entry and exit.',
            'routing_pure_refs': pure_refs, 'driver_gate_separate12_from_routing37': True})
    plan['runtime_scope'] = 'Explicit union of old producer/audit, manual roots, Cgate16, bcp2 and new driver closure; all old checks retained.'
    plan['scope'] += ' New private C digest bundle only; no changes to physical policy or full saved checks.'
    prior.write_new(output / 'plan.json', plan)
    digest = base.sha(output / 'plan.json')
    prior.write_new(output / 'preparation.json', {'status': 'prepared_source_review_pending',
        'plan_sha256': digest, 'source_count': len(pins), 'routing_pure_tests': 37,
        'driver_pure_executed': True, 'driver_pure_tests': 12,
        'native_calls': 0, 'predictions': 0, 'extension_loads': 0,
        'saved_audit_executed': False, 'large_evidence_reads_this_preparation': 0,
        'command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output), '--plan-sha256', digest]})


def audit(output, expected):
    # Exact original v3 wrapper retains first-fatal progress evidence, including
    # errors a policy caught before its later failure. Only old.audit is the
    # inverse-proved generated flow above; all original globals are present.
    old_facade = SimpleNamespace(**{**vars(flow), 'audit': audit_function()})
    wrapper = r.original.clone(previous.previous.audit,
        {**previous.previous.audit.__globals__, 'old': old_facade,
         'namespace': namespace, 'core': audit_core()})
    return wrapper(output, expected)


def reject_unregistered_pure(*args, **kwargs):
    raise ValueError('C_audit_driver_has_no_registered_pure_launcher')


def main():
    # Owned tree, remaining600, worker admission, exclusive logs/claims and
    # unknown failure receipt all retain the original main code/full globals.
    return r.original.clone(prior.main, namespace())()


if __name__ == '__main__':
    raise SystemExit(main())
