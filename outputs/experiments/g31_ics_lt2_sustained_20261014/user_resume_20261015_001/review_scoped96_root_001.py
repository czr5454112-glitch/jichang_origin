from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DEST=OUT/'live_communication_scoped_inputs_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='68024f30b1cc262a7162b67b8a9828885ed5d5c738316cfd44585fb40b1ad7f8'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes());assert len(plan['source_sha256'])==155
for p,d in plan['source_sha256'].items():assert sha(p)==sha(DEST/plan['source_archive'][p])==d,p
for p,d in plan['fixed_evidence_sha256'].items():assert sha(p)==d,p
pure=OUT/'live_communication_scoped_inputs_pure_001'
assert sha(pure/'receipt.json')=='3aa29b152bde17122a2a4258067107b9f09eba6e952c763f0c7f9cdddb603dce'
assert sha(pure/'tests.xml')=='704f4b40eaddd59fece86f1db35a9964a523f6f436613a550c7040bb1400ad4c'
receipt=json.loads((pure/'receipt.json').read_bytes());cases=ET.parse(pure/'tests.xml').getroot().findall('.//testcase')
assert receipt['status']=='passed' and receipt['source_changed']==[] and len(cases)==receipt['tests']==53
assert not any(x.tag in ('failure','error','skipped') for r in cases for x in r)
assert not any((DEST/n).exists() for n in ('execution_claim','external_application_wall.json'))
template=(HERE/'invoke_communication_lazy_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'live_communication_lazy_prepare_001':'live_communication_scoped_inputs_prepare_001',
 'afdcf5741fd835d7d9d4cb9f922bde7d7475b7bd4787ae6f6207a525652b9497':expected,
 'validate_live_communication_lazy':'validate_live_communication_scoped_inputs',
 'g31.communication_lazy.external_wall.v1':'g31.communication_scoped_inputs.external_wall.v1',
 "'execution_claim.json'":"'execution_claim'",
 'Fresh fixed3x32 lazy-view communication conformance. All96 recomputed with original guard/chronology/endpoint checks; saved73 full prediction bytes must remain equal. Only unused full-view construction changes. Whole launch/import/pins/model/targets/equality/export/cleanup/exit included. Offline360s based on measured cost does not change the100ms product target; no online efficacy claim.':'Fresh fixed3x32 scoped-public-input communication conformance. Entire original worker code/defaults/closure/fullglobals retained except model facade; every candidate.predict builds a fresh scope. Early complete output/hash/journal saved before return to original target-check code; only a complete96/226later/192known run binds ordinals to fixed branches. All96 early/late/old output bytes/types/floathex/chronology must agree; exceptions and allunknown rows retained. Original raw future values already loaded by offline verifier but not passed to predictor. Modelspan includes early export, not comparable with ABBA24 bare prediction span. DefaultGC retained, per-sample cycle cleanup not certified. Allsource/runtime/input/audit/export/cleanup/exit share360; no full32 online solver,100ms or joint efficacy claim.'}
for old,new in replacements.items():assert template.count(old)==1,old;template=template.replace(old,new)
template+="\nif ($taskWall -gt 360) {throw 'Whole Python scoped96 budget exceeded'}\n"
wrapper=HERE/'invoke_scoped96_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(template)
review={'schema':'g31.scoped96.root_review.v1','plan_sha256':expected,'root_review_script_sha256':sha(__file__),
 'wrapper_sha256':sha(wrapper),'source_count':155,'pure_tests':53,'raw_decodes':0,'model_calls':0,'native_calls':0,
 'notes':['Root read complete driver and53 focused tests; source union retains original100 and scoped151 current/archive sources.',
 'All originalworker code/globals checks retained except model facade; fresh scope each invocation, no saved result substitution.',
 'Early prediction saved with invocation ordinal before facade returns. Map ordinals only after96 successful calls and original96/226/192 allpassed; partial failure never guessed into branch keys.',
 'Same96fixed rows and old96 complete bytes+types/floathex/chronology plus all original checks. Loaded sources and all fixed evidence checked entryexit.',
 'DefaultGC retained. Original modelspan now includes earlysave/hash/journal; do not compare directly with bare ABBA24 modeltime.',
 'Accept only final exact_all96_original_checks_and_full_outputs,early96mapped,full_output_exact96,unknown0,all originalchecks exact,entryexit unchanged,outerexit0whole<=360.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_bounded_conformance_attempt','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
