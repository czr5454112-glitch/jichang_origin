"""Read saved failure metadata only; no predictor, test, profile or native call."""
from pathlib import Path
import ast
import hashlib
import json

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
FOLDER = OUT / 'json_prediction_shards_RPC_prepare_001'
SOURCE = 'scripts/experiments/g31_ics_circulation/measure_json_prediction_shards.py'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(name):
    return json.loads((FOLDER / name).read_bytes())

failure, ledger, bounded, external = [read(name) for name in
    ('failure.json', 'ledger.json', 'bounded_execution.json', 'external_application_wall.json')]
plan = read('preregistered_protocol.json')
assert sha(ROOT / SOURCE) == sha(FOLDER / 'source' / SOURCE) == plan['source_sha256'][SOURCE]
assert failure['error'] == 'TypeError("\'WindowsPath\' object is not subscriptable")'
assert ledger == [{'round': i, 'arm': arm, 'status': 'unknown_unexecuted'}
                  for i, arm in enumerate(('single', 'split', 'split', 'single'))]
tree = ast.parse((FOLDER / 'source' / SOURCE).read_text(encoding='utf-8-sig'))
campaign = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'campaign')
assignment = next(node for node in campaign.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == 'images' for target in node.targets))
assert isinstance(assignment.value, ast.DictComp)
badpath = assignment.value.value.values[0]
assert isinstance(badpath, ast.Subscript) and isinstance(badpath.value, ast.Name) and badpath.value.id == 'output'
loop = next(node for node in campaign.body if isinstance(node, ast.For))
assert assignment.lineno < loop.lineno
assert not list(FOLDER.glob('*.json.gz')) and not list(FOLDER.glob('*.failed_prefix.json'))
assert not any(FOLDER.glob('[0-3].*.stderr.log'))
assert bounded['status'] == 'unknown_or_failed' and bounded['process']['exitcode'] == 1
assert external['exit_code'] == 1 and external['evidence_unchanged'] is True
names = ('failure.json', 'ledger.json', 'bounded_execution.json', 'external_application_wall.json',
         'stderr.log', 'stdout.log', 'preregistered_protocol.json', 'ready.json')
report = {
    'schema': 'g31.json_shards_failure_diagnosis.v1',
    'status': 'saved_pre_worker_campaign_wiring_failure',
    'evidence': {name: {'path': str(FOLDER / name), 'sha256': sha(FOLDER / name)} for name in names},
    'source': {'path': str(FOLDER / 'source' / SOURCE), 'sha256': sha(FOLDER / 'source' / SOURCE),
               'failure_line': assignment.lineno},
    'root_cause': "output[value['directory']] indexes a WindowsPath; required join is output / value['directory'].",
    'execution_point': 'After four unknown_unexecuted ledger rows, before the first round loop and any LogicalClient construction.',
    'actual_prediction_work': {'predictor_workers': 0, 'logical_requests': 0, 'physical_full_baselines': 0,
                               'candidate_queries': 0, 'unknown_unexecuted_rounds': 4},
    'denominator_basis': 'Saved traceback, exact source execution order and missing per-worker/request artifacts; not an independent OS process census. Parent/campaign processes did execute.',
    'parent_pre_final_export_wall_seconds': bounded['parent_pre_final_export_wall_seconds'],
    'whole_python_application_seconds': external['whole_python_application_seconds'],
    'test_gap': 'Prior60 functional cases exercised LogicalClient but did not traverse campaign plan-to-image-path wiring.',
    'proposed_fix': 'One path-join expression plus a campaign-to-first-constructor regression using real Path and fixed plan; no model/policy/query change.',
    'scope': '001 remains failed. No parallel speed, output equivalence or100ms result exists from this attempt.',
    'new_native_calls': 0, 'new_predictions': 0, 'new_profile_or_benchmark': False,
    'diagnostic_source_sha256': sha(__file__),
    'diagnostic_first_attempt': 'Metadata helper first used exitcode instead of actual external exit_code and raised KeyError before writing a report; corrected schema access only. No predictor ran.',
}
target = OUT / 'json_prediction_shards_failure_diagnosis_001.json'
with target.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps({'path': str(target), 'sha256': sha(target), 'actual_prediction_work': report['actual_prediction_work']}))
