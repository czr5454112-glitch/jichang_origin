"""Root source-bound review before the first complete communication projection."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE.parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
out=OUT/'live_communication_conformance_prepare_002'
expected='029d5c97114651e348a2b66a4c3509e5d4bd10f5bbdd576cf738620100c2d08f'
assert sha(out/'plan.json')==expected
plan=read(out/'plan.json')
assert len(plan['source_sha256'])==96 and len(plan['order'])==len(plan['rows'])==96
assert plan['order']==[case+f'/vector_{i:02d}' for case in ('mechanism','no_overlap','insufficient_advance') for i in range(32)]
assert plan['hard_timeout_seconds']==plan['budget']['fixed_application_seconds']==180.
assert plan['native_executions']==0 and plan['maximum_model_evaluations']==96
assert not (out/'execution_claim.json').exists()
for path,digest in plan['source_sha256'].items():
    assert sha(path)==sha(out/plan['source_archive'][path])==digest
for key,tests in (('live_communication_pure_004.xml',38),('live_communication_driver_pure_001.xml',10)):
    xml=OUT/key;assert sha(xml)==plan['fixed_evidence_sha256'][str(xml)]
    suites=list(ET.parse(xml).getroot().iter('testsuite'))
    assert {k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}==dict(tests=tests,failures=0,errors=0,skipped=0)
boundary=OUT/'live_communication_source_boundary_review_002.json'
assert sha(boundary)=='f9ba8f42bf29f193ce3daf05112f362ca5ef9e90c39290ad13b3dd5c7df6dafc'
old=OUT/'live_communication_conformance_prepare_001'
assert sha(old/'plan.json')=='78c3b7883ba048cef78e2fbd49dc0c5c7ff12c3858a3f72711e54e900f591f31'
assert not (old/'execution_claim.json').exists() and not (old/'receipt.json').exists()
for path,digest in read(old/'plan.json')['source_sha256'].items():
    assert sha(path)==sha(old/read(old/'plan.json')['source_archive'][path])==digest
wrapper=HERE/'invoke_communication_conformance_002_measured.ps1'
body=(HERE/'invoke_codec_saved72_001_measured.ps1').read_text(encoding='utf8')
changes={
 'complete_root_evidence_codec_independent_actual_review_001':'live_communication_conformance_prepare_002',
 'b3121910c1d67b46873fc0fe920c1f4797130f3d5fc1816f132b58ba92c92afb':expected,
 'review_complete_root_evidence_codec_saved':'launch_live_communication_conformance_v2',
 '--plan-sha256':'--expected-plan',
 'ready_for_one_separate_saved_audit':'ready_for_one_bounded_conformance_attempt',
 'g31.complete_codec.independent_saved72.external_wall.v1':'g31.communication_conformance.external_wall.v2',
 'fixed_historical_roots=18;saved_codec_calls=72;native_calls=0;predictor_calls=0':'fixed_rows=96;maximum_model_evaluations=96;native_calls=0',
 'new_codec_samples=0;original_producer_failed=$false;complete_native_request_100ms_certified=$false':'model_conformance_not_inferred_from_exit_code=$true;complete_native_request_100ms_certified=$false',
 'Independent unchanged full saved72 codec verifier. All18 historical source roots and72 full publication artifacts, original clocks, negative samples, all135 producer source and134 separate audit source entry/exit hashes remain. Launch/import/pins/readback/export/cleanup/exit included. No retiming, native or predictor.':'First fixed3x32 communication projection conformance. One owner initial delivered endpoint data only enters the model; actual future endpoints and completions are verifier targets after prediction. All unknown/failed rows retained. Full launch/import/pins/model/target checks/export/cleanup/exit included. No native or online superiority claim.'
}
for before,after in changes.items():assert before in body,before;body=body.replace(before,after)
with wrapper.open('x',encoding='utf8',newline='\n') as stream:stream.write(body)
review=out/'root_source_review_001.json'
report={'schema':'g31.communication_conformance.root_source_review.v2',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),'status':'ready_for_one_bounded_conformance_attempt',
 'plan':ref(out/'plan.json'),'boundary_source_review':ref(boundary),'source_count':96,
 'pure_tests':48,'fixed_rows':96,'owned_seconds':180,'full_model_evaluations_in_review':0,
 'reviewed_rules':[
  'Read delivered context, complete message/physics projection, projected capture source and saved conformance worker plus versioned launcher. Context revalidates original endpoint causal-time/digest/identity guards; raw future outcomes do not enter predict.',
  'public_initial extracts only deciding-owner initial endpoint values and unique immutable publication at<=.11. Other-owner consistency is an offline verifier check. Model call receives contexts[A] and declared action only.',
  'Projected messages arise from processed model state, actual-edge-event hooks and source-local capture/ACK/delivery events; no future actual target or event-heap read builds captured facts. Forecasts never grant native authority.',
  'Fixed declared initial tray availability0 and initial loading typed completion bound remain explicit finite-domain assumptions. They are not inferred from future completions.',
  'Uses original historical endpoint guard and original one-fresh retry eligibility. Unknown phase/final local failure cannot become successful model status. Exactly all3x32 compared by exact completion float bits and ordered collection chronology.',
  'Pure48 includes generated run LOAD_GLOBAL recursive resolution, deliberate missing-global failure and one-tick fakeengine final-output smoke. No claim of physical branch coverage; this first96 run can fail and preserves all unknown rows.',
  'Frozen001 child-only180 launcher is retained unexecuted. New BOOT precedes heavy imports; all worker work gets180-parentElapsed-1 with final overrun nonzero. All96 actual raw hashes checked at entry and exit.',
  'Exit0 means bounded worker completion, never conformance passed. Source/action identity drift fails. No native, strong online method, full32 request100ms or joint efficacy certificate.'
 ],'source':ref(__file__),'wrapper':ref(wrapper)}
with review.open('x',encoding='utf8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as stream:json.dump({'status':report['status'],'plan_sha256':expected,
 'root_review':ref(review),'wrapper_sha256':sha(wrapper),'owned_seconds':180,'dispatched':False},stream,indent=2)
print(json.dumps({'review_sha256':sha(review),'ready_sha256':sha(ready),'wrapper_sha256':sha(wrapper)}))
