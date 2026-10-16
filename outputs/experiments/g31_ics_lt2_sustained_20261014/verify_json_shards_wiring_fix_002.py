"""Metadata and AST proof of the narrow campaign wiring correction."""
from pathlib import Path
import ast
import copy
import hashlib
import json
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
OLD = OUT / 'json_prediction_shards_RPC_prepare_001'
NEW = OUT / 'json_prediction_shards_RPC_prepare_002'
PURE = OUT / 'json_prediction_shards_pure_002'
MODULE = 'scripts/experiments/g31_ics_circulation/measure_json_prediction_shards.py'
TEST = 'tests/test_g31_circulation_json_prediction_shards.py'
TEST_NAME = 'test_campaign_real_path_plan_reaches_first_constructor_without_prediction'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def ref(path): return {'path': str(path), 'sha256': sha(path)}
def tree(path): return ast.parse(Path(path).read_text(encoding='utf-8-sig'))
def dump(value): return ast.dump(value, include_attributes=False)

oldplan, plan = read(OLD / 'preregistered_protocol.json'), read(NEW / 'preregistered_protocol.json')
changed = [name for name, digest in oldplan['source_sha256'].items()
           if plan['source_sha256'].get(name) != digest]
assert set(changed) == {MODULE, TEST} and set(oldplan['source_sha256']) == set(plan['source_sha256'])
for name, digest in plan['source_sha256'].items():
    assert sha(ROOT / name) == sha(NEW / 'source' / name) == digest
for name, digest in oldplan['source_sha256'].items():
    assert sha(OLD / 'source' / name) == digest
oldtree, current = tree(OLD / 'source' / MODULE), tree(ROOT / MODULE)
restored = copy.deepcopy(current)
count = next(n for n in restored.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == 'EXPECTED_PURE_TESTS' for t in n.targets))
assert count.value.value == 61
count.value.value = 60
function = next(n for n in restored.body if isinstance(n, ast.FunctionDef) and n.name == 'campaign')
images = next(n for n in function.body if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == 'images' for t in n.targets))
path = images.value.value.values[0]
assert isinstance(path, ast.BinOp) and isinstance(path.op, ast.Div)
assert dump(path.left) == dump(ast.Name(id='output', ctx=ast.Load()))
images.value.value.values[0] = ast.Subscript(value=path.left, slice=path.right, ctx=ast.Load())
assert dump(restored) == dump(oldtree)
oldtest, newtest = tree(OLD / 'source' / TEST), tree(ROOT / TEST)
added = [n for n in newtest.body if isinstance(n, ast.FunctionDef) and n.name == TEST_NAME]
assert len(added) == 1
newtest.body = [n for n in newtest.body if n not in added]
assert dump(newtest) == dump(oldtest)
gate = read(PURE / 'receipt.json')
cases = ET.parse(PURE / 'tests.xml').getroot().findall('.//testcase')
assert gate['status'] == 'passed' and gate['source_changed'] == [] and gate['tests'] == len(cases) == 61
assert not any(c.tag in ('failure', 'error', 'skipped') for row in cases for c in row)
negative = ET.parse(OUT / 'json_shards_wiring_negative_001.xml').getroot().findall('.//testcase')
assert len(negative) == 1 and negative[0].find('failure') is not None
assert plan['images'] == oldplan['images']
for field in ('schema', 'round_order', 'logical_requests', 'physical_worker_processes', 'physical_RPC_requests',
              'physical_full_baselines', 'candidate_queries', 'candidate_queries_per_logical_request',
              'shards', 'hard_timeout_seconds', 'native_calls', 'input', 'cases', 'interpreter'):
    assert plan[field] == oldplan[field]
oldjson = read(OUT / 'json_prediction_RPC_prepare_002' / 'preregistered_protocol.json')
assert all(sha(ROOT / name) == digest for name, digest in oldjson['source_sha256'].items())
assert not any((NEW / name).exists() for name in ('execution_claim.json', 'ledger.json', 'report.json', 'failure.json'))
report = {
    'schema': 'g31.json_shards_wiring_fix_proof.v1', 'status': 'passed_narrow_source_and_functional_gate',
    'old_plan': ref(OLD / 'preregistered_protocol.json'), 'new_plan': ref(NEW / 'preregistered_protocol.json'),
    'changed_source_files': changed, 'only_runtime_AST_change': "output[value['directory']] -> output / value['directory']",
    'bookkeeping_change': 'Expected functional test count60 to61.',
    'only_test_AST_addition': TEST_NAME,
    'negative_regression': ref(OUT / 'json_shards_wiring_negative_001.xml'),
    'functional_gate': ref(PURE / 'receipt.json'), 'functional_XML': ref(PURE / 'tests.xml'),
    'prior_failure_diagnosis': ref(OUT / 'json_prediction_shards_failure_diagnosis_001.json'),
    'current_and_archive_sources': len(plan['source_sha256']), 'old_JSON_sources_unchanged': len(oldjson['source_sha256']),
    'images_unchanged': plan['images'], 'pure_tests': 61,
    'performance_campaign_executed': False, 'native_calls': 0,
    'scope': 'The failed001 attempt is preserved. Functional model comparisons are tests, not an ABBA performance result. No candidate/model/query/budget change.',
    'proof_source_sha256': sha(__file__),
}
target = NEW / 'wiring_fix_proof_001.json'
with target.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps({'path': str(target), 'sha256': sha(target), 'plan_sha256': sha(NEW / 'preregistered_protocol.json'),
                  'module_sha256': sha(ROOT / MODULE), 'pure_tests': 61}))
