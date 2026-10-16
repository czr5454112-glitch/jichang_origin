from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import research_live_initial_six_seam_v2 as campaign
HERE=Path(__file__).resolve().parent
OUT=HERE.parent
DEST=OUT/'live_initial_six_seam_v2_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='e555fe2ac3b74a87e8bfc5e246b2dc62ef61546a5c6f1b6aca7661e23651d0de'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes())
assert len(plan['source_sha256'])==180
campaign.verify_plan(DEST,plan)
evidence=campaign.evidence_pins(DEST,plan)
assert plan['hard_application_seconds']==120 and len(plan['branch_order'])==3 and len(plan['initial_domain_order'])==6
assert plan['binary']['sha256']=='845486b745bc6e65a9988d1ef5429336b60fd472eb73c39e133e19ec93a7e7be'
assert plan['interpreter']['sha256']=='5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
assert plan['source_proof']==campaign.recorded.source_proof()
assert plan['integration_source_proof']==campaign.source_proof()
pure=OUT/'live_initial_six_seam_v2_pure_001'
assert sha(pure/'receipt.json')=='2fdf0910e49cd16e86f7774caecd272b1949b2eb49a6382e494d3eef79906caf'
assert sha(pure/'tests.xml')=='8b1a947c8db97bb1232904c55922786dbba7befd613330ffae8c9586c3664cca'
assert sha(pure/'external_application_wall.json')=='99725b60292145fdd046e2acfda6c9d4d476798d4caf1bb6f60447d2bc0944b0'
xml=ET.parse(pure/'tests.xml')
assert len(xml.findall('.//testcase'))==81 and not any(xml.findall('.//'+k) for k in ('failure','error','skipped'))
assert not any((DEST/n).exists() for n in ('execution_claim.json','stdout.log','stderr.log','external_application_wall.json'))
body=(HERE/'invoke_live_initial_six_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'live_initial_six_seam_prepare_001':'live_initial_six_seam_v2_prepare_001',
 '29452ac24d205fbd516700a7af051a19805d239dd75f96e091b7f57304e83085':expected,
 'ready_for_one_actual_initial_six_seam':'ready_for_one_actual_initial_six_seam_v2',
 'circulation.launch_live_initial_six_seam --output':'circulation.launch_live_initial_six_seam_v2 --output',
 'g31.initial_six_seam.external_wall.v1':'g31.initial_six_seam.external_wall.v2',
 '173sources':'180sources'}
for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
start=body.index("    scope='");end=body.index('\n',start)
body=body[:start]+"    scope='Same3 accepted027 actual sessions and6 owner domains; current view never fabricated. A service lower bound derived only from exact validated own capture/load transition plus public node0 duration and current loaded job matching; strict now+.01<bound. Other fresh guards, original3getters, passive journal, full44+21 acceptance and all6 outcomes retained. 180source closure. No model, selection or physical request, no protection/online utility/100ms certificate.'"+body[end:]
wrapper=HERE/'invoke_live_initial_six_v2_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.initial_six_seam.root_review.v2','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review_script_sha256':sha(__file__),'source_count':180,'focused_pure_tests':81,
 'evidence_pin_count':len(evidence),'model_calls':0,'native_calls':0,
 'read_scope':'verify_plan decodes six input fixtures; source gate hashes three saved actual schema fixtures and reads their diagnosis; no native execution or model evaluation.',
 'notes':[
 'Root read new adapter, recorded facade, saved verifier, research/launcher/pure/tests and final prewrite prepare hook. Narrow inverse AST replaces only old missing-field service predicate; full defining namespaces retained.',
 'Source-bound earliest service completion is finish+public service duration. Exact owner, capture/current loaded identity, generation/traversal, job status, ACK and current context are required; strict inequality has no epsilon and is not native permission.',
 'Old 3known/3unknown actual evidence stays unchanged. Synthetic actual-shaped schema regression does not upgrade old unknowns. New owned actual6 is independent evidence.',
 '81 pure includes old36,44 actual-schema cases and1 full prepare-order case. Final plan fields added before first write, verification and ready; no post-ready plan mutation.',
 'All6 denominators retained. Require6known0unknown, acceptance closed, unchanged pins, whole<=120. Exit0 may retain unknowns. Model/provider/physical submit absent.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_actual_initial_six_seam_v2','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
