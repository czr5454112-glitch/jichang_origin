from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
OUT=HERE.parent
DEST=OUT/'scoped_public_inputs_v2_six_cost_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='b1e5a14e4362c84f79b16ca22607086b29db3213b0ff588248ec9461816292c0'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes());assert len(plan['source_sha256'])==157
for p,d in plan['source_sha256'].items():assert sha(p)==d==sha(DEST/plan['source_archive'][p])
for p,d in plan['evidence_sha256'].items():assert sha(p)==d
assert sha(plan['environment']['python'])==plan['environment']['sha256']
assert plan['hard_application_seconds']==120 and plan['maximum_model_calls']==24 and len(plan['order'])==6
for folder,n in [('scoped_public_inputs_v2_pure_001',36),('scoped_public_inputs_v2_cost_pure_002',32)]:
    xml=ET.parse(OUT/folder/'tests.xml');assert len(xml.findall('.//testcase'))==n
    assert not xml.findall('.//failure') and not xml.findall('.//error') and not xml.findall('.//skipped')
assert not any((DEST/n).exists() for n in ('execution_claim','external_application_wall.json'))
body=(HERE/'invoke_planning_v2_digest_diagnostic_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'planning_v2_digest_prepare_002':'scoped_public_inputs_v2_six_cost_prepare_001',
 'f9b74d4f92b247a228fa891d000bae1bd00f8d038253562adec31e9e272e1187':expected,
 'ready_for_one_planning_v2_digest_diagnostic':'ready_for_one_scoped_v2_fixed6_ABBA24',
 'launch_planning_v2_digest_v2 --execute --output $taskFolder --plan-sha256 $taskPlanSha':'measure_scoped_public_inputs_v2_six --execute --output $taskFolder --expected-plan $taskPlanSha',
 'g31.planning_v2_digest_diagnostic.external_wall.v1':'g31.scoped_v2_fixed6_ABBA24.external_wall.v1',
 "'execution_claim.json'":"'execution_claim'",
 'fixed_query_rows=2;digest_calls=32;C_extension_loads=0;model_calls=0':'fixed_inputs=6;A_v1_predictions=12;B_v2_predictions=12;C_extension_loads=0;model_calls=24',
 'Fixed two historical v2 query rows,new27212/new27215,allone-envelope denominators.32 original digest calls in8ABBA batches,A16 original and B16 same original under cProfile,not optimization. Same saved native payload digest,complete original compressed/raw hashes and all bounded builtin/schema guards. Four profiles verified against original function counts. All source/input/guard/hash/export/readback/exit inside120. No fullpolicy or600 attribution and no100ms claim.':'Fixed6 ABBA24 v1 versus v2 predictions. Each call includes fresh scope construction/private bindings, every unchanged guard/model call; v2 copies only selected public case, identify read-only borrows private table, historical helper base rebound. Generic inputs still full fresh deepcopy, no endpoint/validation/result cache. Initial context caller unchanged, separately timed insidewhole. All24 full outputs saved before lazy targets; additionalv1 full comparison after all model calls.157source/evidence/runtime guards/defaultGC retained. Original worker_seconds taken before addedv1 readback is partial; only wholeclock includes setup/allcomparisons/export/processcleanup/exit within120. No per-sample cycle cleanup/native/full32/complete100ms certificate.',
 'Whole Python planning_v2_digest_diagnostic budget exceeded':'Whole Python scoped v2 fixed6ABBA24 budget exceeded'}
for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
wrapper=HERE/'invoke_scoped_v2_ABBA_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.scoped_v2_ABBA.root_review.v1','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review_script_sha256':sha(__file__),'source_count':157,'functional_pure_tests':36,'harness_pure_tests':32,
 'actual_model_calls':0,'raw_decodes':0,'notes':[
 'Root read complete v2 candidate,36functional cases,full driver32focused tests andv1 scope constructor. Public validation AST unchanged except return selected deepcopy,identify original readonly function/code/fullglobals,history helper clonebase→privateinitial.',
 'Functional historical143KB saved fixture used only original/fullendpointguard parity,nomodel. Firstcostpure31/32 errorwas test AST docstring assumption; test corrected,pure00232passed,v2unchanged,failed001 preserved.',
 'Original sixworker input/context/GC/typedfulloutput/chronology/sourceguards retained; privateA=v1/B=v2 pluspins and finaladditionalv1 comparison. Bothversions newfresh scope percall,initialcontext caller unchanged.',
 '24full denominator preserves model/setup/export/audit failure; no timingsummary unless alllazy+v1 outputsexact. Extra readback is after originalworker_seconds so relywholeexternalclock forcompletebudget.',
 'Accept passed_fixed_six_ABBA24_complete_prediction,24exact0unknown,12eacharm,sourceunchanged,defaultGC,outerexit0whole<=120. Samples only conditionalprediction,notnative100ms/full32.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_scoped_v2_fixed6_ABBA24','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
