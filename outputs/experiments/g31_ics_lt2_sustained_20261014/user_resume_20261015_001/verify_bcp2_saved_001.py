"""Independent saved-only readback; no project imports or tests executed."""
import hashlib
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

START = time.perf_counter()
ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014/bcp2'
PINS = {
    'plan.json': '9fd532c6051eefa0c1446fbe958a413e320a73f6dfec98e0ddd5e4a63987b780',
    'receipt.json': '174838c6c05a7893f5b8f600ba623c84e72c49126b315c9a9384c7e19f1b9392',
    'worker.json': '93bcb28489bf3ae218b55ff3413abe317e1132dbac54d8c5f19cb408f5fec15e',
    'tests.xml': '041bcf7871cafeb097cc1dec76330ab8804ac9e8de982f99db760d744b18575c',
    'bounded_execution.json': '194fa100971e8be6075e941cff2ff446e0e706da2ee94aee7165f7c49e28f7f8',
    'external_application_wall.json': 'af80bdd5c93b9db0507bf8c043ba17e7c6f7803ea5b029a9d51f58738a3f1918',
}
def require(ok, message):
    if not ok:
        raise ValueError(message)
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(name):
    return json.loads((OUT/name).read_text(encoding='utf8'))
for name, expected in PINS.items():
    require(sha(OUT/name) == expected, 'saved pin:' + name)
plan, receipt, worker, bounded, outer = map(read, ('plan.json', 'receipt.json', 'worker.json', 'bounded_execution.json', 'external_application_wall.json'))
require(plan['schema'] == receipt['schema'] == 'g31.bridge.saved_C_digest.synthetic_pure.v2', 'schema')
require(plan['tests'] == receipt['tests'] == receipt['expected_tests'] == 37 and plan['limit_seconds'] == 120., 'fixed domain')
require(receipt['status'] == 'passed_synthetic_routing' and receipt['bad_tests'] == [] and receipt['error'] is None, 'receipt')
require(type(worker['pytest_exitcode']) is int and worker['pytest_exitcode'] == 0 and worker['source_entry_exit_exact'] is True, 'worker')
require(receipt['process'] == bounded and bounded['status'] == 'exited' and type(bounded['exitcode']) is int and bounded['exitcode'] == 0, 'owned result')
require(bounded['windows_job_kill_on_close'] is True and bounded['child_released_only_after_job_assignment'] is True, 'owned lifetime')
require(receipt['XML_sha256'] == PINS['tests.xml'] and receipt['worker_sha256'] == PINS['worker.json'], 'result links')
cases = ET.parse(OUT/'tests.xml').getroot().findall('.//testcase')
require(len(cases) == 37 and not any(n.tag in ('failure', 'error', 'skipped') for c in cases for n in c), 'XML37')
for record in (receipt, worker):
    require(all(type(record[k]) is int and record[k] == 0 for k in ('native_calls', 'extension_loads', 'actual_fixture_reads')), 'no actual execution declaration')
require(receipt['benchmark_executed'] is False, 'no benchmark')
require(outer['schema'] == 'g31.bridge.saved_C_digest.pure_external.v1' and outer['started'] is True and outer['accepted_launch_and_clock'] is True, 'external status')
require(type(outer['exit_code']) is int and outer['exit_code'] == 0 and outer['outer_timeout'] is False and outer['exception'] is None and outer['cleanup_errors'] == [], 'external execution')
freq, ticks = outer['tick_frequency'], outer['elapsed_ticks']
require(type(freq) is int and freq > 0 and type(ticks) is int and 0 <= ticks <= 120*freq == outer['budget_ticks'], 'typed clock')
require(outer['end_ticks'] - outer['start_ticks'] == ticks and outer['whole_python_seconds'] == ticks/freq, 'clock arithmetic')
require(outer['working_directory'] == str(ROOT) and outer['expected_tests'] == 37, 'external domain')
command = [outer['python']['path'], '-m', 'scripts.experiments.g31_ics_circulation.run_bridge_saved_c_digest_pure_v2', '--output', str(OUT)]
require(outer['command'] == command and plan['command'] == command + ['--worker', '--admission', plan['admission']], 'commands')
require(outer['environment_explicit'] == {'PYTHONPATH':'src;.;tests', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1', 'PYTHONIOENCODING':'utf-8'}, 'environment')
for kind in ('python', 'wrapper'):
    require(sha(outer[kind]['path']) == outer[kind]['sha256'], kind + ' identity')
require(outer['python']['sha256'] == '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec' and outer['wrapper']['sha256'] == '9150c283af1df06c502b81a79e98d05ab1336923110d1482a54f6738f9816ff7', 'fixed external pins')
require(outer['source_changed'] == outer['missing_outputs'] == [], 'unchanged and complete')
for name, digest in outer['output_sha256'].items():
    require(sha(OUT/name) == digest, 'external output:' + name)
sources = plan['source_sha256']
require(len(sources) == 115 and sources == receipt['source_sha256'], 'source domain')
for name, digest in outer['source_sha256'].items():
    require(sources[name] == digest, 'external source:' + name)
targets = set()
max_path = 0
for name, digest in sources.items():
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and relative.as_posix() == name and '..' not in relative.parts, 'canonical source')
    current, archived = (ROOT/name).resolve(), (OUT/'source'/name).resolve()
    require(current.is_relative_to(ROOT) and archived.is_relative_to(OUT/'source') and current != archived, 'contained independent paths')
    require(archived not in targets and len(str(archived)) < 260, 'archive uniqueness/length')
    targets.add(archived); max_path = max(max_path, len(str(archived)))
    require(sha(current) == sha(archived) == digest, 'source/archive:' + name)
for loaded in (receipt['loaded_parent_exit'], worker['loaded_entry'], worker['loaded_exit']):
    require(len(loaded) == len(set(loaded)) and set(loaded) <= set(sources), 'loaded closure')
result = {'schema':'g31.bcp2.root_saved_review.v1', 'status':'passed_saved_only_readback',
    'pins':PINS, 'tests':37, 'source_count':115, 'max_archive_path':max_path,
    'whole_python_seconds':outer['whole_python_seconds'], 'shared_limit_seconds':120,
    'scope':'Saved bytes, XML, source/archive/loaded-domain, owned-process and external clock checks only; no second tests, C, native, raw replay or performance execution.',
    'no_all_day_or_100ms_acceptance':True, 'elapsed_seconds':time.perf_counter()-START}
target = OUT/'root_saved_review_001.json'
with target.open('x', encoding='utf8', newline='\n') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
print(json.dumps({'status':result['status'], 'tests':37, 'sources':115, 'whole_python_seconds':outer['whole_python_seconds'], 'path':str(target), 'sha256':sha(target)}))
