from pathlib import Path
import json
from scripts.experiments.g31_ics_circulation import run_planning_v2_c_encoder_gate_v3 as gate
HERE=Path(__file__).resolve().parent; OUT=HERE.parent; ROOT=gate.old.ROOT; sha=gate.old.sha
PREP=OUT/'planning_v2_C_encoder_gate_prepare_003'; BUILD=OUT/'planning_v2_C_encoder_build_002'
pins={'plan.json':'d6912d695e36707dbba6bd7a0359e5ec6c6ed1a964323e99c4aae4fecf28579b',
 'root_build_review_001.json':'3f583d629833334cd93470a0f8ce8bfed1ead4a41f7241042980647871f74792',
 'commands.json':'578466aeead2924fc8a44560cf1ff6049070139e31704bdefbeabad30640b8c7'}
for name,digest in pins.items(): assert sha(PREP/name)==digest
build_pins={'receipt.json':'fb2c4ddfabfc0277da6f40d397ecba86e50c4a9cb9f67820ebd11f4346d56979',
 'bounded_execution.json':'7fe746e399f43884a10581bb8394fe6689e6a6d71bec7993a6017270f5f3958c',
 'external_application_wall.json':'c9ae7c89205f72c87734fc60d16a4e9b9c9d59a78031e047e20dbae2422aeaa4',
 'small_readback_001.json':'c33cbce4d01fb0f530a7f7f0c30f063249bee1af3eae4e48341a41afdcfa6838'}
for name,digest in build_pins.items(): assert sha(BUILD/name)==digest
plan=json.loads((PREP/'plan.json').read_bytes());receipt=json.loads((BUILD/'receipt.json').read_bytes())
bounded=json.loads((BUILD/'bounded_execution.json').read_bytes())
assert receipt['status']=='build_passed_unloaded' and receipt['extension_loads']==0
assert receipt['identity_verified_on_exit'] is True
assert json.loads((BUILD/'external_application_wall.json').read_bytes())['source_changed']==[]
assert bounded['status']=='exited' and bounded['exitcode']==0
for name,digest in plan['source_sha256'].items():
    current=(ROOT/name).resolve(); archive=(PREP/'source'/name).resolve()
    assert not Path(name).is_absolute() and not Path(name).drive
    assert current.is_relative_to(ROOT) and archive.is_relative_to(PREP) and current!=archive
    assert sha(current)==digest==sha(archive)
binary=receipt['binary'];assert sha(binary['path'])==binary['sha256']==sha(binary['archive'])=='a690ba550c49cd437afbeb2286e6a2082213ce44d3f1f64840e1b9d41f68a809'
assert Path(binary['path']).stat().st_size==34304
ns=gate.namespace(); assert ns['project_closure']()==plan['source_sha256']
external=ns['external_build_identity'](BUILD,build_pins['external_application_wall.json'],PREP/'plan.json',pins['plan.json'],plan)
command=json.loads((PREP/'commands.json').read_bytes())['functional_template_not_yet_executable']
command=[build_pins['receipt.json'] if x=='ACTUAL_ACCEPTED_BUILD_RECEIPT_SHA256_REQUIRED' else build_pins['external_application_wall.json'] if x=='ACTUAL_EXTERNAL_APPLICATION_WALL_SHA256_REQUIRED' else x for x in command]
assert not (OUT/'planning_v2_C_encoder_functional_002').exists()
result={'schema':'g31.planning_v2.C_encoder.root_functional_review.v2','status':'one_functional002_only_authorized',
 'review_script_sha256':sha(__file__),'plan_sha256':pins['plan.json'],'build_pins':build_pins,
 'actual_build_external_identity':external,'project_current_and_archive_verified':len(plan['source_sha256']),
 'binary':binary,'command':command,'shared_seconds':120,
 'requirements':['159 tests;126 direct full-byte probes and10 fallback probes separately.','Actual module file/spec/loader and actual imported DLL path/hash verification; original full entry/exit source/toolchain/runtime checks.',
 'External launch-through-exit typed ticks and exact command/wrapper/plan/output binding, <=120 seconds; no automatic retry.'],
 'scope':['Root rehashed16 current/archive sources, exact build receipts and binary/archive; original external_build_identity accepted. Root did not repeat7779 toolchain/3082 runtime file hashes; functional must.','First root review stopped before output due to source_changed being in external receipt, not worker receipt. Field lookup corrected after reading actual schema. No functional attempt occurred.','No extension loaded by this review; no actual fixtures, performance, model or native simulation authorized.','Old metadata001 timeout and build001 log collision remain separate failed attempts.']}
path=PREP/'root_functional_review_002.json'
with path.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'root_functional_review_sha256':sha(path),'status':result['status'],'whole_build_seconds':external['whole_python_seconds']}))
