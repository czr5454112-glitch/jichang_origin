from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import measure_owned_initial_bundle_six as campaign
from scripts.experiments.g31_ics_circulation import run_owned_initial_bundle_cost_pure as pure_runner
HERE=Path(__file__).resolve().parent;OUT=HERE.parent
DEST=OUT/'owned_initial_bundle_six_cost_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='c61c19fcf0d5464a8102a368d8f1b86e4f8e8a91980bcd97ab3d71fd6e45fa64'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes());assert len(plan['source_sha256'])==181
for p,d in plan['source_sha256'].items():assert sha(p)==d==sha(DEST/plan['source_archive'][p])
for p,d in plan['evidence_sha256'].items():assert sha(p)==d
assert sha(plan['environment']['python'])==plan['environment']['sha256']
assert plan['source_proof']==campaign.source_proof()
assert pure_runner.source_proof()['closure_addition_before_worker_launch']
assert plan['hard_application_seconds']==120 and plan['maximum_model_calls']==24 and len(plan['order'])==6
for folder,n in [('owned_initial_bundle_pure_001',26),('owned_initial_bundle_cost_pure_002',25)]:
    xml=ET.parse(OUT/folder/'tests.xml');assert len(xml.findall('.//testcase'))==n
    assert not any(xml.findall('.//'+k) for k in ('failure','error','skipped'))
assert sha(OUT/'owned_initial_bundle_cost_pure_002/tests.xml')=='e2a419ea3835fb0c9b9b387d120ea9a6f0e91d90d4c4ca1349d81a032617c5ac'
assert sha(OUT/'owned_initial_bundle_cost_pure_002/receipt.json')=='32e988f3e7c01573c30104092ad4a3fd3329df305083d504c50af078241b0769'
assert not any((DEST/n).exists() for n in ('execution_claim','external_application_wall.json','stdout.log'))
body=(HERE/'invoke_initial_scoped_ABBA_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'initial_scoped_inputs_six_cost_prepare_001':'owned_initial_bundle_six_cost_prepare_001',
 '20522f420b69367c2cd09ebc1d9a6774b5b4853970cdde363ac637b3cfe3bf31':expected,
 'ready_for_one_initial_scope_fixed6_ABBA24':'ready_for_one_owned_bundle_fixed6_ABBA24',
 'measure_initial_scoped_public_inputs_six --execute':'measure_owned_initial_bundle_six --execute',
 'g31.initial_scope_fixed6_ABBA24.external_wall.v1':'g31.owned_initial_fixed6_ABBA24.external_wall.v1',
 'declared_A_original_initial_plus_v2=12;declared_B_same_scope_initial_predict=12':'declared_A_initial_scope_original_copy=12;declared_B_initial_scope_owned_bundle=12',
 'model_calls=24':'declared_model_calls=24',
 'Whole Python initial scope fixed6ABBA24 budget exceeded':'Whole Python owned bundle fixed6ABBA24 budget exceeded'}
for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
start=body.index("    scope='");end=body.index('\n',start)
body=body[:start]+"    scope='Fixed6 ABBA24 whole initial construction and prediction. A=current initial scope; B=same plus only one private redundant bundle deepcopy removal. Fresh scope, original A/B validations, fact equality, model and caller return inside each sample. Retains revalidation deepcopy and protocol copy. All24 fulloutputs saved before lazy targets; initial-scope targets read after all24. 181sources, defaultGC, all checks/export/processcleanup within120. No per-sample cycle destruction, native/full32 or complete100ms certificate.'"+body[end:]
wrapper=HERE/'invoke_owned_initial_ABBA_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.owned_initial_ABBA.root_review.v1','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review_script_sha256':sha(__file__),'source_count':181,'component_pure':26,'harness_pure':25,
 'actual_model_calls':0,'raw_decodes':0,'notes':[
 'Root read candidate, original revalidate/private ownership path, tests, cost driver and final closure/kwdefaults corrections. Original JSON tree fresh; retained revalidation deep copy yields private bundle with no escape. Only projection helper copy removed. Protocol data copy and all guards retained.',
 'Worker code/defaults/kwdefaults/closure/full defining namespace preserved, exactly four globals replaced. Additional full-output comparator follows all24 callback returns. No targets passed to predictions.',
 'Pure001 8passed17failed retained; unused SCHEMA namespace mismatch and fake clone missing keyword defaults corrected only in new driver/test before freezing181. Explicit bare helper is in current, original178, pure150, final181 closure.',
 'All24 outcomes retained. Any unknown, export or comparison failure prevents timing summary. Same current A/B combined component boundary; historical medians are not paired comparisons.',
 'Require24exact0unknown,12samples each,source unchanged/defaultGC and whole<=120. Resource failure timing not equivalent; no complete-native100ms or joint usefulness claim.']}
path=DEST/'root_source_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump({
 'status':'ready_for_one_owned_bundle_fixed6_ABBA24','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(path),'sha256':sha(path)}},f,indent=2)
print(json.dumps({'review':sha(path),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
