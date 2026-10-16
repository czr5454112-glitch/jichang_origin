from pathlib import Path
import hashlib,json,sys,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import research_live_initial_six_seam as campaign
HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DEST=OUT/'live_initial_six_seam_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='29452ac24d205fbd516700a7af051a19805d239dd75f96e091b7f57304e83085'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes())
assert len(plan['source_sha256'])==173
campaign.verify_plan(DEST,plan);evidence=campaign.evidence_pins(DEST,plan)
assert plan['hard_application_seconds']==120 and len(plan['branch_order'])==3 and len(plan['initial_domain_order'])==6
assert plan['binary']['sha256']=='845486b745bc6e65a9988d1ef5429336b60fd472eb73c39e133e19ec93a7e7be'
assert plan['interpreter']['sha256']=='5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
assert plan['source_proof']==campaign.recorded.source_proof()
pure=OUT/'live_initial_six_seam_pure_001'
assert sha(pure/'receipt.json')=='0afca3b7bfcb637cec1488d33bd56424d9f19ece652ae61db65bc02217288040'
assert sha(pure/'tests.xml')=='c30f040ba1856657bf3084b3b8286395e0b23f8b44d3939bb104d5b9b231e04a'
xml=ET.parse(pure/'tests.xml')
assert len(xml.findall('.//testcase'))==36 and not any(xml.findall('.//'+k) for k in ('failure','error','skipped'))
assert not any((DEST/n).exists() for n in ('execution_claim.json','stdout.log','stderr.log','external_application_wall.json'))
body=(HERE/'invoke_initial_scope_full96_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'live_communication_initial_scoped_inputs_prepare_001':'live_initial_six_seam_prepare_001',
 '8036d19b2f397551df1fe593f45b17097ef6cf314a6521319ad33b772cfb491c':expected,
 'ready_for_one_initial_scope_full96_conformance':'ready_for_one_actual_initial_six_seam',
 'validate_live_communication_initial_scoped_inputs --execute':'launch_live_initial_six_seam',
 "'execution_claim'":"'execution_claim.json'",
 'g31.initial_scope_full96.external_wall.v1':'g31.initial_six_seam.external_wall.v1',
 'whole_python_within_360_seconds=($taskWall -le 360)':'whole_python_within_120_seconds=($taskWall -le 120)',
 'shared_owned_seconds=360;fixed_rows=96;fixed_cases=3;maximum_model_evaluations=96;expected_actual_collection_checks=226;expected_known_collections=192;native_calls=0':'shared_owned_seconds=120;fixed_domains=6;fixed_cases=3;declared_sessions=3;declared_collection_triplets=12;model_predictions=0;physical_requests_submitted=0',
 "if ($taskWall -gt 360) {throw 'Whole Python initial scope full96 budget exceeded'}":"if ($taskWall -gt 120) {throw 'Whole Python initial six native seam budget exceeded'}"}
for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
start=body.index("    scope='");end=body.index("\n",start)
body=body[:start]+"    scope='Three actual accepted027 sessions and six independent owner domains, original case input vector16 exactly. Four seed demand/planning publications percase, advance .05/.11 only, own actual session withoutproxy and original threegetters recorded at initial and immediate freshcurrent. Reversible passive collector wrappers preserve native exceptionidentity; monitor failure isunknown. All6domains retained. Full44legacy+21semantic entry/exit acceptance,173sources,rawsave before offlineguard replay,pins/export/close allshare120. Zero provider/model/physicalsubmit; no dispatchauthority, actualprotection, onlineutility or100ms certification.'"+body[end:]
wrapper=HERE/'invoke_live_initial_six_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.initial_six_seam.root_review.v1','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review_script_sha256':sha(__file__),'source_count':173,'focused_pure_tests':36,
 'evidence_pin_count':len(evidence),'model_calls':0,'actual_fixture_decodes':0,'native_calls':0,'notes':[
 'Root read entire recordedcollector,runner,launcher,pure and36 tests. Only three getter expressions wrapped by reversibleAST, original fullglobals/private facade; real native session never proxied.',
 'Original getter return/exception identity retained; timing/export/exception-string monitoring faults sticky unknown. Savedexception prefix remains and adapter-caught unknown explicitly supported; savedmonitor fault cannot countcomplete.',
 'Original fixed threecase vector16 inputs and6ownerdenominator; owneradmission/currentphysicaltime/immutableownledger and fullsupplied guards preserved. NativeRunAcceptance+exact027bind required.',
 'Raw saved before offline verify. SavedJSON has no nativeauthority. Actual model/provider/32search/physicalcommands and H40businessresult absent, so this gate is only deliveredinitial information provenance/executability.',
 'Accept six_actual_initial_seams_validated/6known0unknown,closed_run_acceptance_passed,pinsunchanged,0model/physical and whole<=120; exit0 alone can retain unknowns.',
 'Stage execute logs absent. Shared owned120 includes imports/full44+21entryexit,all3sessions,guardreadback,export and cleanup. No complete100ms claim.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_actual_initial_six_seam','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
