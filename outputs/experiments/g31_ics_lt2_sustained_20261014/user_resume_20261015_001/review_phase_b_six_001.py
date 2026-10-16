"""Root source review and wrapper preparation; no model or raw target reads."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import validate_live_phase_b_pause as a
from scripts.experiments.g31_ics_circulation import public_live_obligation_phase_b_pause as model

here = Path(__file__).resolve().parent
out = a.OUT/'live_phase_b_pause_prepare_001'
expected = 'be90c0042ac1073e7c880275c2fc412a0d11242bc06189bfc93a52eb309a8fbb'
assert a.sha(out/'plan.json') == expected
plan = a.read(out/'plan.json')
assert len(plan['source_sha256']) == 105 and plan['order'] == list(a.ORDER)
assert plan['maximum_model_calls'] == 6 and plan['expected_hook_points'] == 14
assert plan['hard_application_seconds'] == 120 and plan['source_proof'] == model.source_proof()
assert a.sha(a.__file__) == '7a334d4cc7223e430670c467eac311e2318e58b1084e4115c520bff9276b3b63'
assert plan['environment']['sha256'] == a.sha(plan['environment']['python']) == '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
for name, digest in plan['source_sha256'].items():
    assert a.sha(name) == a.sha(out/plan['source_archive'][name]) == digest
pure = []
for folder, count in (('live_phase_b_pause_pure_001', 16), ('live_phase_b_pause_driver_pure_001', 10)):
    path = a.OUT/folder/'tests.xml'
    assert a.sha(path) == plan['evidence_sha256'][str(path)]
    counts = {k: sum(int(s.get(k, 0)) for s in ET.parse(path).getroot().iter('testsuite'))
              for k in ('tests', 'failures', 'errors', 'skipped')}
    assert counts == dict(tests=count, failures=0, errors=0, skipped=0)
    pure.append({'path': str(path), 'sha256': a.sha(path), 'counts': counts})
assert not (out/'execution_claim.json').exists()
body = (here/'invoke_communication_lazy_001_measured.ps1').read_text(encoding='utf8')
changes = {
    'live_communication_lazy_prepare_001': 'live_phase_b_pause_prepare_001',
    'afdcf5741fd835d7d9d4cb9f922bde7d7475b7bd4787ae6f6207a525652b9497': expected,
    'validate_live_communication_lazy --execute': 'validate_live_phase_b_pause --execute',
    'g31.communication_lazy.external_wall.v1': 'g31.passive_phase_b_six.external_wall.v1',
    'whole_python_within_360_seconds=($taskWall -le 360)': 'whole_python_within_120_seconds=($taskWall -le 120)',
    'shared_owned_seconds=360;fixed_rows=96;maximum_model_evaluations=96;native_calls=0':
        'shared_owned_seconds=120;fixed_rows=6;maximum_model_evaluations=6;expected_hook_points=14;native_calls=0',
    'Fresh fixed3x32 lazy-view communication conformance. All96 recomputed with original guard/chronology/endpoint checks; saved73 full prediction bytes must remain equal. Only unused full-view construction changes. Whole launch/import/pins/model/targets/equality/export/cleanup/exit included. Offline360s based on measured cost does not change the100ms product target; no online efficacy claim.':
        'Fixed6 passive model runs,14 snapshot points, full prediction bytes against frozen lazy comparands, complete alias graph and isolation checks. Independent actual supplied inventories do not establish model-point relations. Whole launch/import/pins/model/copy/check/export/cleanup/exit included. No resumability, native authority, hidden-state coverage, online efficacy or100ms certificate.'
}
for before, after in changes.items():
    assert body.count(before) == 1, before
    body = body.replace(before, after)
body += "\nif ($taskWall -gt 120) {throw 'Whole Python six-input budget exceeded'}\n"
wrapper = here/'invoke_phase_b_six_root_001_measured.ps1'
with wrapper.open('x', encoding='utf8', newline='\n') as stream:
    stream.write(body)
review = out/'root_source_review_001.json'
report = {'schema': 'g31.passive_phase_b_six.root_review.v1', 'plan_sha256': expected,
    'sources': 105, 'pure': pure, 'raw_or_prediction_reads_in_review': 0,
    'maximum_model_calls': 6, 'native_calls': 0, 'owned_seconds': 120,
    'review': [
        'Full hook, support inventory, six-input driver and26pure source read. Single postcollect hook; no runloop/collect/action changes. Defining globals preserved.',
        'Only minimal lawful initial owners and selected action enter predict_with_points; target prediction and future actual attempts are read afterward for comparison and independent inventory only.',
        'Fixed6/14 chronology, complete ordered prediction bytes, typed alias graph, world backref/pending identity/recorder detached and clone mutation isolation all checked.',
        'Known/unknown/fresh collections remain represented. Inventory uses original guards and has no relation to a model snapshot; no opaqueID mapping or filtering implied.',
        'Prediction archive is written before point audits but after target read/decompression and prediction encoding. Failures in those preceding steps may leave no prediction archive; unknown row and all attempt counts remain, no stronger failure-retention promise.',
        'Six prior model calls total2.3896373s;42graph copies are unmeasured. One120 bounded diagnostic with unknowns retained, not a speed benchmark.',
        'Worker exit0 alone is not conformance: require exact_six_passive_conformance receipt,6exact/0unknown,14points,6calls,entryexit identity and external <=120 afterward.',
    ], 'resumable': False, 'coverage_certified': False, 'source': a.ref(__file__),
    'wrapper_sha256': a.sha(wrapper)}
with review.open('x', encoding='utf8') as stream:
    json.dump(report, stream, indent=2, allow_nan=False)
with (out/'root_ready_001.json').open('x', encoding='utf8') as stream:
    json.dump({'status': 'ready_for_one_bounded_conformance_attempt', 'plan_sha256': expected,
        'root_review': a.ref(review), 'wrapper_sha256': a.sha(wrapper),
        'dispatched': False, 'owned_seconds': 120}, stream, indent=2)
print(json.dumps({'review_sha256': a.sha(review), 'ready_sha256': a.sha(out/'root_ready_001.json'),
                  'wrapper_sha256': a.sha(wrapper)}))
