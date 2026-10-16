"""Saved-only readback for the two exact owned synthetic harnesses."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
PYTHON = Path('C:/PROGRAMING/python3.11.9/python.exe')
SPECS = {
    'lorp1': (22, 'run_live_obligation_online_retained_policy_pure',
        'g31.live_obligation.online_retained_policy.synthetic22.v1',
        'g31.live_obligation.online_retained_policy.synthetic22_external.v1',
        'control_timers_lorp1_pure_001.ps1',
        'c42ff3744daacbc981becaf4bbcfd3861a68c76242469960d87085bd29d5a6d6',
        'b745ad23ebd3d92bc133273446348e265fc69518c6629da597ed379e0987a8dc',
        '6f48514b9640b436370ef8d99069c3d45e031125f97474e5fa8a06c63fdf2d29',
        '03decadadca41308c1dc1134afce69d8a48e2dbc0bcb753aeb9d5e6ed09ba771'),
    'oimp1': (21, 'run_online_initial_methods_pure',
        'g31.live_obligation.online_initial_methods.synthetic21.v1',
        'g31.live_obligation.online_initial_methods.synthetic21_external.v1',
        'root_oimp1_pure_001.ps1',
        '5f7cd0b769ac4b7944c897b0989e0116da5429bf179d1aaec85eea87bf0a3889',
        'a242b3fcbb8c79e5f31331b616684fe2a23512395d874a2f74ed349e1bb66744',
        '5e018d7d2c0af1e5e124df5a8567a21f9ebbbedaffb81a0d3387b3f45ff358f5',
        '5665010ea73b8f3bacb887f0aef7ec4eb152f817d444d2fc522d620f0108f8f4'),
}

def require(ok, reason):
    if not ok: raise ValueError(reason)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def exact_int(value): return type(value) is int

def verify(name):
    started = time.perf_counter()
    count, module, schema, external_schema, wrapper, wrapper_sha, plan_sha, receipt_sha, external_sha = SPECS[name]
    directory = OUT / name
    pins = {'plan.json': plan_sha, 'receipt.json': receipt_sha, 'external_application_wall.json': external_sha}
    for leaf, digest in pins.items(): require(sha(directory / leaf) == digest, 'fixed_pin:' + leaf)
    require(sha(OUT / wrapper) == wrapper_sha, 'wrapper_pin')
    plan, receipt, external = (read(directory / leaf) for leaf in pins)
    command = [str(PYTHON), '-m', 'scripts.experiments.g31_ics_circulation.' + module, '--output', str(directory)]
    require(external['schema'] == external_schema and external['command'] == command
        and external['working_directory'] == str(ROOT), 'external_identity')
    require(external['environment_explicit'] == {'PYTHONPATH': 'src;.;tests',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONIOENCODING': 'utf-8'}, 'explicit_environment')
    require(external['python'] == {'path': str(PYTHON), 'sha256': sha(PYTHON)}
        and sha(PYTHON) == '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec', 'python_pin')
    require(external['wrapper'] == {'path': str(OUT / wrapper), 'sha256': wrapper_sha}, 'wrapper_binding')
    for key, expected in {'started': True, 'exit_code': 0, 'outer_timeout': False,
        'exception': None, 'cleanup_errors': [], 'source_changed': [], 'missing_outputs': [],
        'accepted_launch_and_clock': True, 'expected_tests': count}.items():
        require(type(external[key]) is type(expected) and external[key] == expected, 'external:' + key)
    a, b, ticks, freq = (external[k] for k in ('start_ticks', 'end_ticks', 'elapsed_ticks', 'tick_frequency'))
    require(all(exact_int(x) for x in (a,b,ticks,freq)) and 0 <= a <= b and freq > 0
        and b-a == ticks <= 120*freq and external['budget_ticks'] == 120*freq
        and type(external['whole_python_seconds']) is float and external['whole_python_seconds'] == ticks/freq,
        'typed_whole120')
    outputs = external['output_sha256']
    require(set(outputs) == {'plan.json','receipt.json','worker.json','bounded_execution.json','tests.xml',
        'parent_stdout.log','parent_stderr.log','parent_stages.jsonl','worker_stages.jsonl'}, 'output_domain')
    for leaf, digest in outputs.items(): require(sha(directory / leaf) == digest, 'output:' + leaf)
    require(outputs['plan.json'] == plan_sha and outputs['receipt.json'] == receipt_sha, 'fixed_output_refs')
    require(plan['schema'] == receipt['schema'] == schema and plan['tests'] == receipt['tests'] == count
        and receipt['expected_tests'] == count and receipt['status'] == 'passed_synthetic' + str(count)
        and receipt['bad_tests'] == [] and receipt['error'] is None, 'exact_passed_denominator')
    require(plan['limit_seconds'] == 120. and type(plan['admission']) is str
        and re.fullmatch('[0-9a-f]{32}', plan['admission'])
        and plan['command'] == command + ['--worker','--admission',plan['admission']], 'owned_command')
    process = read(directory / 'bounded_execution.json')
    require(process == receipt['process'] and process['status'] == 'exited'
        and exact_int(process['exitcode']) and process['exitcode'] == 0
        and process['windows_job_kill_on_close'] is True
        and process['child_released_only_after_job_assignment'] is True
        and 0 <= process['wall_seconds'] <= process['hard_timeout_seconds'] <= 120, 'owned_closed')
    worker = read(directory / 'worker.json')
    require(worker['pytest_exitcode'] == 0 and worker['source_entry_exit_exact'] is True
        and receipt['worker_sha256'] == outputs['worker.json']
        and receipt['XML_sha256'] == outputs['tests.xml'], 'worker_XML_binding')
    xml = ET.parse(directory / 'tests.xml').getroot()
    require(len(list(xml.iter('testcase'))) == count
        and sum(int(s.get('tests')) for s in xml.iter('testsuite')) == count
        and all(int(s.get(k)) == 0 for s in xml.iter('testsuite') for k in ('errors','failures','skipped'))
        and all(not list(xml.iter(k)) for k in ('error','failure','skipped')), 'XML_complete')
    sources = plan['source_sha256']
    require(receipt['source_sha256'] == sources and len(external['source_sha256']) == 3
        and all(sources.get(k) == v for k,v in external['source_sha256'].items()), 'source_domain')
    archive = (directory / 'source').resolve()
    identities = set()
    for relative, digest in sources.items():
        path = Path(relative)
        require(not path.is_absolute() and '\\' not in relative
            and all(x not in ('','.','..') for x in relative.split('/')), 'canonical_relative_source')
        current, saved = (ROOT/path).resolve(), (archive/path).resolve()
        require(current.is_relative_to(ROOT) and saved.is_relative_to(archive) and current != saved
            and len(str(saved)) < 260 and current.relative_to(ROOT).as_posix() == relative
            and saved.relative_to(archive).as_posix() == relative, 'archive_containment')
        require(str(current).casefold() not in identities, 'source_alias')
        identities.add(str(current).casefold())
        require(sha(current) == sha(saved) == digest, 'source_current_archive:' + relative)
    for loaded in (receipt['loaded_parent_exit'], worker['loaded_entry'], worker['loaded_exit']):
        require(type(loaded) is list and len(set(loaded)) == len(loaded) and set(loaded) <= set(sources), 'loaded_source_closure')
    require(set(worker['loaded_entry']) <= set(worker['loaded_exit']), 'loaded_monotonic')
    for leaf, expected_rows in (('parent_stages.jsonl',20),('worker_stages.jsonl',10)):
        lines = [json.loads(line) for line in (directory/leaf).read_text(encoding='utf8').splitlines()]
        require(len(lines) == expected_rows <= 64, 'journal_count')
        stack, previous = [], -1
        for i, event in enumerate(lines):
            require(set(event) == {'sequence','phase','event','at_ns'} and event['sequence'] == i
                and exact_int(event['at_ns']) and event['at_ns'] >= previous, 'journal_order')
            previous = event['at_ns']
            if event['event'] == 'started': stack.append(event['phase'])
            else:
                require(event['event'] == 'completed' and stack and stack.pop() == event['phase'], 'journal_balanced')
        require(not stack, 'journal_closed')
    for obj in (receipt, worker):
        require(all(exact_int(obj[k]) and obj[k] == 0 for k in
            ('native_calls','extension_loads','actual_fixture_reads','predictions')), 'synthetic_scope')
    require(receipt['benchmark_executed'] is False and receipt['full_external_acceptance'] is False,
            'inner_scope_requires_outer')
    result = {'schema':'g31.synthetic_owned_saved_root_review.v1','status':'passed_saved_only_readback',
        'pins':pins,'tests':count,'sources':len(sources),'whole_python_seconds':ticks/freq,
        'current_archive_loaded_exact':True,'complete_balanced_journals':True,
        'new_tests_native_model_C_calls':0,'saved_readback_seconds':time.perf_counter()-started,
        'scope':'Synthetic orchestration only; no actual prospective21, physics, robust protection, full32 complete100ms or joint effectiveness claim.'}
    target = directory/'root_saved_review_001.json'
    with target.open('x',encoding='utf8') as stream: json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({'path':str(target),'sha256':sha(target),'tests':count,'sources':len(sources)}))

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('name',choices=tuple(SPECS))
    verify(parser.parse_args().name)
