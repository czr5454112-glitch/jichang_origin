from pathlib import Path
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import validate_owned_full32_runtime as c
HERE=Path(__file__).resolve().parent;OUT=HERE.parent;ROOT=c.ROOT;sha=c.sha
DEST=OUT/'owned_full32_runtime_prepare_001';expected='6f4434bcf87d8e35d709eabfed5561b6461adde71389b92c8042072a9e6c4bc5'
assert sha(DEST/'plan.json')==expected and sha(DEST/'ready.json')=='23e2f1d8f53f15538b6a0de3a1c789881b49f2ffa5d50728cc5def1c0e716731'
plan=c.read(DEST/'plan.json');ready=c.read(DEST/'ready.json')
c.check_plan(plan);c.ready.verify_archive(ROOT,DEST,plan)
assert len(plan['source_sha256'])==191
for name,digest in plan['source_sha256'].items():
    current=(ROOT/name).resolve();archive=(DEST/plan['source_archive'][name]).resolve()
    assert not Path(name).is_absolute() and not Path(name).drive
    assert current.is_relative_to(ROOT) and archive.is_relative_to(DEST/'source') and current!=archive
    assert sha(current)==digest==sha(archive)
for name,digest in plan['evidence_sha256'].items():assert sha(name)==digest,name
assert {n:c.hashlib.sha256(v).hexdigest() for n,v in c.source_files().items()}==plan['source_sha256']
c.pure_gate();proof=c.source_proof()
assert proof['worker_inverse_AST']['inverse_AST_exact'] and proof['save_inverse_AST']['inverse_AST_exact']
pure=OUT/'owned_full32_runtime_driver_pure_001'
assert sha(pure/'receipt.json')=='311a9e7ee3cf08707534ee55afc797b5a81ddb41302347239029a64fecc7010b'
assert sha(pure/'tests.xml')=='c039ef50fc54acf31e660f6fb805a74ad880f1da981c8bcb44704f4e6f57e54c'
assert sha(pure/'external_application_wall.json')=='e79451d197277bea31829b7e21c3d42b065479defc0737221220f70e8b8e3f32'
outer=c.read(pure/'external_application_wall.json');assert outer['exitcode']==0 and 0<outer['external_application_seconds']<=120
xml=ET.parse(pure/'tests.xml');assert len(xml.findall('.//testcase'))==20
assert not any(xml.findall('.//'+n) for n in ('failure','error','skipped'))
assert not (DEST/'execution_claim.json').exists()
assert ready['execute_command']==[str(c.sys.executable),'-m',c.MODULE,'--execute','--output',str(DEST),'--expected-plan',expected]
result={'schema':'g31.owned_full96.root_review.v1','status':'one_original_full96_conformance_authorized',
 'review_script_sha256':sha(__file__),'plan_sha256':expected,'source_count_verified':191,
 'evidence_count_verified':len(plan['evidence_sha256']),'command':ready['execute_command'],'hard_application_seconds':360,
 'root_read':['full driver','20 tests','pure runner','original worker/execute/check_plan','owned runtime saver'],
 'source_proof':proof,'requirements':['Original48 groups/96suffixes, entire predictions durably saved before targets; every retained point/terminal/action/count compared; unknowns remain in denominator.','Original shared360 including imports/pins/context/clone/suffix/export/audit; external launch-through-exit clock and closed process required. Default GC; no per-request cleanup or native/C.'],
 'limits':['Historical graph diagnostics are reference only and not remeasured; no fabricated graph flags.','Offline conformance, not paired speed, native hidden-state coverage, online utility or complete100ms certification.','No static source-proof cache or scoped initial context optimization is included.']}
path=DEST/'root_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'root_review_sha256':sha(path),'sources':191,'evidence':len(plan['evidence_sha256']),'status':result['status']}))
