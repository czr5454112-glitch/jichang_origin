"""Independent source review for one fresh96 lazy-view conformance run."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE.parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
out=OUT/'live_communication_lazy_prepare_001'
expected='afdcf5741fd835d7d9d4cb9f922bde7d7475b7bd4787ae6f6207a525652b9497'
assert sha(out/'plan.json')==expected
plan=read(out/'plan.json')
assert len(plan['source_sha256'])==100 and len(plan['saved73_equivalence'])==73
assert plan['order']==[case+f'/vector_{i:02d}' for case in ('mechanism','no_overlap','insufficient_advance') for i in range(32)]
assert list(plan['rows'])==plan['order'] and plan['maximum_model_evaluations']==96 and plan['native_executions']==0
assert plan['hard_timeout_seconds']==plan['budget']['fixed_application_seconds']==360.
assert not (out/'execution_claim.json').exists()
for path,digest in plan['source_sha256'].items():
    assert sha(path)==sha(out/plan['source_archive'][path])==digest
for row in plan['rows'].values():
    assert plan['fixed_evidence_sha256'][row['actual_raw']['path']]==row['actual_raw']['sha256']
for xmlname,count in (('live_communication_pure_004.xml',38),('live_communication_driver_pure_001.xml',10),
                      ('live_communication_lazy_pure_001.xml',8),('live_communication_lazy_driver_pure_001.xml',4)):
    path=OUT/xmlname;assert sha(path)==plan['fixed_evidence_sha256'][str(path)]
    suites=list(ET.parse(path).getroot().iter('testsuite'))
    assert {k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}==dict(tests=count,failures=0,errors=0,skipped=0)
assert sha(OUT/'live_communication_partial_review_001/report.json')=='671f67f1831b9c1e43a0d3c1f879f0cdda06ead50253102f1b66cb1fcd430656'
old=OUT/'live_communication_conformance_prepare_002'
assert sha(old/'rows.json')=='11831be39a3a225a2fde2489a797fb71313485d1c75c1b0719d665215c431397'
assert sha(old/'external_application_wall.json')=='76787446c51c08b327adc8fa9f5441cc9bc68eaac27beddffac58d111eb20502'
assert read(old/'bounded_execution.json')['status']=='unknown_failed_or_budget_exceeded'
original=HERE/'invoke_communication_conformance_002_measured.ps1'
assert sha(original)=='ecff4786e21db8b638defb24dcc3883e750119da0834228d33915eb86417029f'
body=original.read_text(encoding='utf8')
changes={
 'live_communication_conformance_prepare_002':'live_communication_lazy_prepare_001',
 '029d5c97114651e348a2b66a4c3509e5d4bd10f5bbdd576cf738620100c2d08f':expected,
 'launch_live_communication_conformance_v2':'validate_live_communication_lazy',
 'g31.communication_conformance.external_wall.v2':'g31.communication_lazy.external_wall.v1',
 'whole_python_within_180_seconds=($taskWall -le 180)':'whole_python_within_360_seconds=($taskWall -le 360)',
 'shared_owned_seconds=180':'shared_owned_seconds=360',
 'First fixed3x32 communication projection conformance. One owner initial delivered endpoint data only enters the model; actual future endpoints and completions are verifier targets after prediction. All unknown/failed rows retained. Full launch/import/pins/model/target checks/export/cleanup/exit included. No native or online superiority claim.':
 'Fresh fixed3x32 lazy-view communication conformance. All96 recomputed with original guard/chronology/endpoint checks; saved73 full prediction bytes must remain equal. Only unused full-view construction changes. Whole launch/import/pins/model/targets/equality/export/cleanup/exit included. Offline360s based on measured cost does not change the100ms product target; no online efficacy claim.'
}
for before,after in changes.items():
    assert body.count(before)==1,before
    body=body.replace(before,after)
wrapper=HERE/'invoke_communication_lazy_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as stream:stream.write(body)
report={'schema':'g31.communication_lazy.root_review.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'status':'ready_for_one_bounded_conformance_attempt','plan':ref(out/'plan.json'),
 'source_count':100,'focused_pure_tests':12,'inherited_pure_tests':48,'fixed_rows':96,'saved_complete_outputs':73,
 'owned_seconds':360,'new_model_or_native_calls_in_review':0,
 'reviewed_rules':[
  'Read full lazy module, driver, original worker and12 focused tests. Exact inverseAST restores original activate; all original physics/events/guards/collection methods and predict entry code remain.',
  'Only two L trigger reads consume view; deferred view is readonly. B E request before one trigger only queues future wire and does not change L. No event interleaves inside activation. Tests include this branch.',
  'All96 actual raws are fixed entry/exit evidence; predictor still receives deciding-owner initial delivered context and declared action only, actual future targets only after prediction.',
  'Full original worker uses private model facade with samecode/default/closure. All initial/later originalguards, five floathex endpoints, ordered attempts, unknown denominator and226 targetchecks remain.',
  'All96 are fresh computations. Independently saved73 full decompressed JSON bytes are compared, preserving every field/order/type; old23 rows are never substituted. Final exitpins include old predictionfiles.',
  'First180s failure remains with73exact23unknown and missingexitproof. New360 is finite offline verification based on measured235.68 to274.66s extrapolations, not a promise or product deadline relaxation.',
  'Success needs original exact96 receipt plus73equivalence, final_receipt exact_all96_and_saved73, bounded completed and outerwall<=360. Exit0 alone is insufficient. No causal speedup claim from separate rounds.'
 ],'source':ref(__file__),'wrapper':ref(wrapper)}
review=out/'root_source_review_001.json'
with review.open('x',encoding='utf8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as stream:json.dump({'status':report['status'],'plan_sha256':expected,
 'root_review':ref(review),'wrapper_sha256':sha(wrapper),'owned_seconds':360,'dispatched':False},stream,indent=2)
print(json.dumps({'review_sha256':sha(review),'ready_sha256':sha(ready),'wrapper_sha256':sha(wrapper)}))
