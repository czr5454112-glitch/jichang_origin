"""Root review and immutable external measurement wrapper for quiet pair."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = HERE.parent
PAIR = OUT / 'preference_quiet_pair_001'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
plan_path = PAIR / 'preregistered_protocol.json'
plan_sha = '41922041ffe189df3b0a9b4ac7e8612efea79ad6e8e04aaaed45f6324a1b92f9'
module_sha = 'f467eb5f46d3fcad1f7cca5300dd95dc03c6c3fdd9a79b85e8dd33093e599714'
assert sha(plan_path) == plan_sha
assert sha(ROOT / 'scripts/experiments/g31_ics_circulation/measure_public_preference_quiet.py') == module_sha
plan = json.loads(plan_path.read_bytes())
assert len(plan['sources']) == 44 and len(plan['cases']) == 6
assert plan['candidate_denominator'] == 192 and plan['later_candidate_denominator'] == 0
assert plan['historical_native_status_counts'] == {'assessed': 174, 'unknown_missing_input_or_unexecuted_counterfactual': 18}
assert plan['hard_timeout_seconds'] == 120 and plan['native_calls'] == 0
for path, row in plan['sources'].items():
    assert sha(Path(path)) == row['sha256']
    assert sha(PAIR / 'source' / row['archive']) == row['sha256']
wrapper = HERE / 'invoke_quiet_pair_001_measured.ps1'
assert not wrapper.exists()
source = (HERE / 'invoke_prefix_pair_002_measured.ps1').read_text(encoding='utf8')
for old, new in {
    'preference_prefix_pair_002': 'preference_quiet_pair_001',
    'measure_public_preference_prefix': 'measure_public_preference_quiet',
    'fe6f32a02cf078ed289a23f99d06c756284ed48532df633144d8942cacb6ee94': plan_sha,
    '89031c0014486230aaaa78f017fda68b75de5b3ef26261a35bca0c2797648ea7': module_sha,
    'g31.prefix_pair.external_application_wall.v1': 'g31.quiet_pair.external_application_wall.v1',
}.items():
    assert old in source
    source = source.replace(old, new)
with wrapper.open('x', encoding='utf8', newline='\n') as f: f.write(source)
report = OUT / 'preference_quiet_pair_001_prelaunch_review.json'
with report.open('x', encoding='utf8') as f:
    json.dump({'status': 'passed_source_and_prelaunch_binding_review', 'plan_sha256': plan_sha,
               'module_sha256': module_sha, 'source_count': 44, 'native_executions': 0,
               'wrapper_sha256': sha(wrapper), 'checks': [
                   'Six fixed public vector00 bundles; 192 independent original full predictions.',
                   '24 ABBA timed batches, each exactly32 complete outputs, all setup charged.',
                   'Initial only, later denominator zero; native174assessed18unknown unchanged.',
                   'Owned120s child and external wholePython startup-through-exit wall.',
                   'All44 live and archived sources match.'],
               'prelaunch_correction': 'First root precheck stopped before wrapper/experiment creation: expected a shortened unknown label. Corrected to exact stored unknown_missing_input_or_unexecuted_counterfactual; no result reclassification.',
               'complete_100ms_certified': False}, f, indent=2)
print(json.dumps({'review_sha256': sha(report), 'wrapper_sha256': sha(wrapper)}))
