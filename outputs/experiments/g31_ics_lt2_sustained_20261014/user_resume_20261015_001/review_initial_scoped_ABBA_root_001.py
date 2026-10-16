from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent;OUT=HERE.parent
DEST=OUT/'initial_scoped_inputs_six_cost_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='20522f420b69367c2cd09ebc1d9a6774b5b4853970cdde363ac637b3cfe3bf31'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes());assert len(plan['source_sha256'])==171
for p,d in plan['source_sha256'].items():assert sha(p)==d==sha(DEST/plan['source_archive'][p])
for p,d in plan['evidence_sha256'].items():assert sha(p)==d
assert sha(plan['environment']['python'])==plan['environment']['sha256']
assert plan['hard_application_seconds']==120 and plan['maximum_model_calls']==24 and len(plan['order'])==6
for folder,n in [('initial_scoped_public_inputs_pure_001',22),('initial_scoped_inputs_cost_pure_001',30)]:
    xml=ET.parse(OUT/folder/'tests.xml');assert len(xml.findall('.//testcase'))==n
    assert not any(xml.findall('.//'+k) for k in ('failure','error','skipped'))
assert not any((DEST/n).exists() for n in ('execution_claim','external_application_wall.json','stdout.log'))
body=(HERE/'invoke_scoped_v2_ABBA_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'scoped_public_inputs_v2_six_cost_prepare_001':'initial_scoped_inputs_six_cost_prepare_001',
 'b1e5a14e4362c84f79b16ca22607086b29db3213b0ff588248ec9461816292c0':expected,
 'ready_for_one_scoped_v2_fixed6_ABBA24':'ready_for_one_initial_scope_fixed6_ABBA24',
 'measure_scoped_public_inputs_v2_six --execute':'measure_initial_scoped_public_inputs_six --execute',
 'g31.scoped_v2_fixed6_ABBA24.external_wall.v1':'g31.initial_scope_fixed6_ABBA24.external_wall.v1',
 'A_v1_predictions=12;B_v2_predictions=12':'declared_A_original_initial_plus_v2=12;declared_B_same_scope_initial_predict=12',
 'Fixed6 ABBA24 v1 versus v2 predictions. Each call includes fresh scope construction/private bindings, every unchanged guard/model call; v2 copies only selected public case, identify read-only borrows private table, historical helper base rebound. Generic inputs still full fresh deepcopy, no endpoint/validation/result cache. Initial context caller unchanged, separately timed insidewhole. All24 full outputs saved before lazy targets; additionalv1 full comparison after all model calls.157source/evidence/runtime guards/defaultGC retained. Original worker_seconds taken before addedv1 readback is partial; only wholeclock includes setup/allcomparisons/export/processcleanup/exit within120. No per-sample cycle cleanup/native/full32/complete100ms certificate.':'Fixed6ABBA24 complete initial-construction andprediction. A=originaltwoowner build_initial/factcomparison thenv2; B=freshv2scope thenexact same originalbuild_initial injected scope.context andsame scope.predict. SameAthenBguards/types/fourfactequality, no observation/validation/resultcache. Originalcaller code unchanged, worker inverseAST movesonlyinitialconstruction intoeachcallback withcorrectlabels, finalv2comparator andreceiptcounts. All24completepredictions saved beforetargets, fullbytes/type/order/floathex/chronology.171source/evidence/runtime/defaultGC; worker_seconds predates extraaudit soexternalwhole coversall. Inputdecode outside sampleinsidewhole120; no per-samplecyclecleanup/native/complete100ms claim.',
 'Whole Python scoped v2 fixed6ABBA24 budget exceeded':'Whole Python initial scope fixed6ABBA24 budget exceeded'}
for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
wrapper=HERE/'invoke_initial_scoped_ABBA_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.initial_scope_ABBA.root_review.v1','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review_script_sha256':sha(__file__),'source_count':171,'component_pure':22,'harness_pure':30,
 'actual_model_calls':0,'raw_decodes':0,'notes':[
 'Rootread completecomponent22tests anddriver30tests. Exact originalbuild_initial explicitproviderparameter, ownerAthenB exactcontexttypes andjobs/trays/contract/now equality retained; Bfreshscope allocatedbeforebothguards andsamecontext reused onlywithinonecall.',
 'Inverseworker AST only removes outside-sample initialbuild in favorpublic andlabel; bothcallbacks containoriginalbuild+prediction. Extra originalsavedcomparator reused/relabelv2, finalsourcepins, receiptcountfromfinalreport. Allotherworker globals unchanged.',
 'Failureinitialguards/export/comparator retain24denominator andno timingstatistics unlessall24pass. Fullsavedoutput+chronology checkslazy andv2 retained; targetnotinput.',
 'Accept passed_fixed_six_ABBA24_complete_prediction/24exact0unknown/source[]/12each/defaultGC,outerexit0whole<=120. Wholeincludesinputdecode/setup/hash/export/readback/cleanup. CompareA/Bonlysamecombinedboundary, neverpreviousbarepredict.',
 'Allocationtiming differs fromA; resourcefailure remainsunknown. This is supplied model work, notnativecomplete100ms oronlineprotection.']}
path=DEST/'root_source_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump({
 'status':'ready_for_one_initial_scope_fixed6_ABBA24','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(path),'sha256':sha(path)}},f,indent=2)
print(json.dumps({'review':sha(path),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
