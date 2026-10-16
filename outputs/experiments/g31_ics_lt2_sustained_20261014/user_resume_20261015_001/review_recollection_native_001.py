"""Root source and immutable evidence review; no native or model calls."""
from pathlib import Path
from datetime import datetime, timezone
import json, xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import launch_live_obligation_recollection as launcher
c = launcher.campaign
out = c.OUT/'live_obligation_recollection_native_prepare_001'
expected = '9b5d2cc047a0c75cdde4d916542728b491dccc71c09cf026720aad9c135dea98'
assert c.sha(out/'preregistered_protocol.json') == expected
plan = c.read(out/'preregistered_protocol.json')
c.verify(out, plan)
assert len(plan['source_sha256']) == 82 and len(plan['rows']) == 96
assert c.sha(c.SOURCE_PREP) == c.SOURCE_PREP_SHA
old = c.read(c.SOURCE_PREP)
assert len(old['sources']) == 81
for path, digest in old['sources'].items():
    assert c.sha(path) == c.sha(c.SOURCE_PREP.parent/old['source_archive'][path]) == digest
assert c.sha(c.TEST_XML) == '0090178848150edd73dc8b33facaa000e786a55966df765412c574d7920d1d2f'
counts = {key: sum(int(s.get(key, 0)) for s in ET.parse(c.TEST_XML).getroot().iter('testsuite'))
          for key in ('tests', 'failures', 'errors', 'skipped')}
assert counts == dict(tests=39, failures=0, errors=0, skipped=0)
parent = c.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert c.sha(parent) == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert not (out/'launch_claim.json').exists() and not (out/'receipt.json').exists()
wrapper = Path(__file__).parent/'invoke_recollection_native_001_measured.ps1'
report = {
    'schema': 'g31.recollection_native.root_prelaunch_review.v1',
    'recorded_utc': datetime.now(timezone.utc).isoformat(),
    'status': 'passed_fixed96_attempt_ready', 'plan_sha256': expected,
    'source_count': 82, 'old_stageAB_sources_unchanged': 81, 'pure_tests': counts,
    'reviewed_source_rules': [
        'Private FunctionType namespace changes adapter and OwnerPolicy only; original branch and initial helper bytecode retained.',
        'Same three physical inputs and all32 fixed vectors per input; all96 denominator retained, no saved outcome policy selection.',
        'One actual fresh pair only after sealed failed read with supported change or elapsed service bound; final own target, immutable actions, ACK union and strict service/wire bounds retained.',
        'Successful and failed collection attempts exported; exception capture does not result_at or advance physics.',
        'Saved replay binds every attempt to actual endpoints, prefix requests, current view and retained acceptance; new publication and actual bounded peer replies verified.',
        'Whole call history, exact one terminal UNLOAD_COMPLETE per completed job, full five-job H40 and physical action assessment rebuilt.',
        'Full16 family and full32 finite optimum require every family member assessed; no previous model conformance or optimizer selection reused.',
        'One600s owned process tree covers entry/exit acceptance,96 native attempts, all save/audit and source checks; external parent measured separately.',
    ],
    'limits': ['Functional native validation only; concurrent source/pure work is permitted and no100ms performance claim.',
               'Old34assessed/62unknown remain immutable.', 'No original-day, generic model, online optimizer, joint-novelty or two-machine certificate.'],
    'wrapper': c.reference(wrapper), 'producer': c.reference(__file__),
    'native_executions': 0, 'model_evaluations': 0,
}
review = out/'root_prelaunch_review_001.json'
with review.open('x', encoding='utf8') as f: json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
ready = out/'root_ready_001.json'
with ready.open('x', encoding='utf8') as f:
    json.dump({'status': 'ready_for_one_bounded_actual_attempt', 'plan_sha256': expected,
               'root_review': c.reference(review), 'wrapper_sha256': c.sha(wrapper),
               'native_branches': 96, 'owned_seconds': 600, 'native_dispatched': False}, f, indent=2)
print(json.dumps({'review_sha256': c.sha(review), 'ready_sha256': c.sha(ready), 'wrapper_sha256': c.sha(wrapper)}))
