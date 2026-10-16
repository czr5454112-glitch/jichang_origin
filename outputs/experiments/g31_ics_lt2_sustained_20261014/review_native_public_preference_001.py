"""Independent narrow source and pure guard review; no NativeSession calls."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import xml.etree.ElementTree as ET

from scripts.experiments.g31_ics_circulation import public_native_preference_projection as model
from scripts.experiments.g31_ics_circulation import research_native_public_preference as runner

root=Path(__file__).resolve().parents[3]
out=root/'outputs/experiments/g31_ics_lt2_sustained_20261014'
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
ready_path=out/'native_public_preference_ready_001.json'
ready=json.loads(ready_path.read_text(encoding='utf8'))
assert sha(ready_path)=='4a3dd52905058f1b270c11bfd2299ba146cae8bf8b4fecc78bada4f96ea16ec4'
source_pins=ready['sources']
assert len(source_pins)==73 and all(sha(path)==digest for path,digest in source_pins.items())
plan_checks={}
for phase,ref in ready['plans'].items():
    path=Path(ref['path']);assert sha(path)==ref['sha256']
    plan=json.loads(path.read_text(encoding='utf8'));folder=path.parent
    assert plan['source_sha256']==source_pins
    assert set(plan['source_archive'])==set(source_pins)
    assert all(sha(folder/plan['source_archive'][src])==digest for src,digest in source_pins.items())
    expected=runner.protocol(phase)
    assert plan['rows']==expected['rows'] and plan['initial_budget']==32 and plan['later_budget']==4
    assert plan['hard_timeout_seconds']==180.
    assert set(plan['input_file_sha256'])==set(plan['rows'])
    for key,row in plan['rows'].items():
        inp=folder/'inputs'/(key+'.json')
        assert sha(inp)==plan['input_file_sha256'][key]
        assert json.loads(inp.read_text(encoding='utf8'))==json.loads(json.dumps(runner.native_scene(row['case'],row['fault']),allow_nan=False))
    plan_checks[phase]={'rows':len(plan['rows']),'same_sources_and_archives':True,'exact_predeclared_inputs':True,
                       'initial_budget':32,'later_budget':4,'whole_worker_limit_seconds':180.}
test_path=root/'tests/test_g31_circulation_public_native_preference_projection.py'
spec=importlib.util.spec_from_file_location('review_initial_fixture',test_path)
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
base,action=fixture.data()
checks={}
for kind in ('unavailable_empty','completed_blocker','wrong_occupancy'):
    bundle=copy.deepcopy(base)
    if kind=='unavailable_empty':bundle['trays']['E']['available_at']=99.
    elif kind=='completed_blocker':bundle['jobs']['blocker']['status']='completed'
    else:bundle['resources']={0:{'node':0,'occupancy':999,'actual_available':0}}
    value=model.predict(bundle,action)
    assert value['status'].startswith('unknown') and not value.get('completion')
    checks[kind]=value
xml=out/'public_native_online_policy_pure_001.xml'
suites=ET.parse(xml).getroot().findall('testsuite')
counts={key:sum(int(s.attrib[key]) for s in suites) for key in ('tests','failures','errors','skipped')}
assert counts=={'tests':89,'failures':0,'errors':0,'skipped':0}
assert all(sha(path)==digest for path,digest in source_pins.items())
result={
 'schema':'g31.native_public_preference.independent_source_review.v1',
 'status':'no_concrete_blocker_in_reviewed_initial_guards_and_online_authority',
 'ready':{'path':str(ready_path),'sha256':sha(ready_path)},
 'review_harness_note':'Two read-only harness attempts stopped at a wrong ready key and then tuple/list representation of edge_records. Used actual sources key and exact JSON roundtrip of native_scene (matching stored input format); no field exclusion. No native or production mutation.',
 'review_script_sha256':sha(__file__),'source_pins':source_pins,'plans_checked':plan_checks,
 'previous_three_counterexamples_reexecuted':checks,
 'reported_pure_xml_inspected':{'path':str(xml),'sha256':sha(xml),**counts},
 'source_findings':[
  'Initial projection rechecks typed obligations, exact resource occupancy/available stock, tray identity/generation/prefix and known service epochs. All three prior supplied-fact counterexamples now return unknown.',
  'Later online path requires a live session-bound NativeCollectedV3 object; JSON flags cannot authorize a proposal. Current own facts are derived from its sealed actual full endpoint and include every physical action.',
  'Later current action IDs/kinds must exactly match captured source actions, no pending IDs, and each terminal delivered ACK must be strictly before the earliest capture. Same-time ACK remains unknown; no empty-list override.',
  'Later projection reruns the prior full captured-data validator and compares completed prefix; first_reuse_route cannot choose the already executed first return.',
  'Initial32/later4 domain and all ten method/six-case rows are fixed. Four-window family uses the same later search budget. Unknown or incomplete cases cannot produce zero-gain/protection results.',
  'The new business run requires the exact same-source nine-row delivery gate, rereads raw inputs/results, checks closed run acceptance and verifies source/archive/binary bindings. Whole worker is inside the180s owned job.',
  'Native default issues no preference and promises no edge. Selected route preferences require current local receiving preconditions; actual execution and strict all-five completion deltas remain separate native assessment gates.'
 ],
 'limits':[
  'Source review and three pure counterexample executions only; no native execution or replay, no full retrospective192 reread.',
  'The89-test XML was inspected; this reviewer did not rerun that whole test suite.',
  'Retrospective exact comparisons do not establish model error bounds or prospective physical protection. Missing future collection/atomic-state stability remains conditional.',
  'No timing or100ms claim and no original-map utility claim.'
 ],'native_executions':0
}
target=out/'native_public_preference_independent_source_review_001.json'
assert not target.exists();target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'path':str(target),'sha256':sha(target),'prior_counterexamples':{k:v['status'] for k,v in checks.items()}}))
