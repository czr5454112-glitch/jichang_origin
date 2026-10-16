from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DEST=OUT/'scoped_inputs_saved_review_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='ef87204e578282274b04605f781ffe7750ac647395aebca503f68ea3cabd3b48'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes());assert len(plan['source_sha256'])==154
for path,digest in plan['source_sha256'].items():assert sha(path)==sha(DEST/plan['source_archive'][path])==digest
for path,digest in plan['producer_metadata_sha256'].items():assert sha(path)==digest
pure=OUT/'scoped_inputs_saved_pure_001'
assert sha(pure/'receipt.json')=='108c731d41d5f000f1166708407119d2e33fe00de019c0c5259bcb570c6937b3'
receipt=json.loads((pure/'receipt.json').read_bytes());cases=ET.parse(pure/'tests.xml').getroot().findall('.//testcase')
assert receipt['status']=='passed' and receipt['source_changed']==[] and len(cases)==receipt['tests']==49
assert receipt['XML_sha256']==sha(pure/'tests.xml')
assert not any(n.tag in ('failure','error','skipped') for c in cases for n in c)
assert not any((DEST/n).exists() for n in ('execution_claim','external_application_wall.json'))
template=(HERE/'invoke_C_publisher_saved_root_001_measured.ps1').read_text(encoding='utf8')
oldscope='Independent saved-only72 complete publisher records against18 original fixtures. Original145/169/135source and6124toolchain/raw/runtime guards; strict types/order/floathex and regenerated clocks; original event/deadline fields retained;36samples perarm and all18paired outcomes recomputed. Producer direct18C support and alias facts remain producer observations. No C loading/model/native/performance or complete100ms claim.'
replacements={
 'C_publisher_saved_review_prepare_001':'scoped_inputs_saved_review_prepare_001',
 '510ee1590e4c871eff6f25dd2ef5bf69262850575aaf50fb42e5cb1b086ce1d9':expected,
 'ready_for_one_independent_C_publisher_saved_review':'ready_for_one_independent_scoped_saved24_review',
 'review_complete_root_c_publisher_saved --execute --output $taskFolder --expected-plan $taskPlanSha':'review_scoped_public_inputs_saved --execute --output $taskFolder --expected-plan $taskPlanSha',
 'g31.C_publisher.independent_saved.external_wall.v1':'g31.scoped_inputs.independent_saved.external_wall.v1',
 'shared_owned_seconds=120;fixed_inputs=18;saved_publisher_rows=72;C_extension_loads=0;model_calls=0;native_simulation_calls=0':'shared_owned_seconds=120;fixed_inputs=6;saved_prediction_rows=24;C_extension_loads=0;model_calls=0;native_simulation_calls=0',
 oldscope:'Independent saved-only24 complete predictions against6 original targets. Original151 and auditor154 sources/current/archive/runtime, exact bytes/order/types/floathex/chronology and12perarm/6paired statistics. All unknowns retained. Prediction-save-before-target is frozen source proof only, no runtime target-read journal. No model/C/native call or speed measurement; concurrent light source and focused pure work permitted. DefaultGC producer observation retained; per-sample scope-cycle cleanup unproved. Full audit120includes guards/load/compare/export/exit; no complete100ms/full32 claim.',
 'Whole Python independent C publisher saved review budget exceeded':'Whole Python independent scoped saved24 review budget exceeded'}
for old,new in replacements.items():assert template.count(old)==1,old;template=template.replace(old,new)
wrapper=HERE/'invoke_scoped_saved24_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(template)
review={'schema':'g31.scoped_saved24.root_review.v1','plan_sha256':expected,'root_review_script_sha256':sha(__file__),
 'wrapper_sha256':sha(wrapper),'source_count':154,'pure_tests':49,'raw_reads':0,'model_calls':0,'native_calls':0,
 'notes':['Root read full independent reader and49 focused tests. Auditor imports no producer model.',
 'All24 full bytes/types/floathex and complete chronology compared to6 originals;12perarm/6paired statistics and negative cases recomputed.',
 'Shared120 owned tree includes all guards/decompressions/readback/export/exit. Exact observed source entry/exit/current/archive and runtime domains checked.',
 'Source-only early-save proof distinguished from absent runtime target-read journal; no alias/model execution/complete100ms assertion.',
 'Accept passed_saved24 with exact24 unknown0, unchanged sources, defaultGC producer observation, outerexit0whole<=120.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_independent_scoped_saved24_review','plan_sha256':expected,
 'wrapper_sha256':sha(wrapper),'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
