from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
OUT=HERE.parent
DEST=OUT/'live_communication_scoped_inputs_v2_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='d64ab44189e5c7cb3d79b109072a6f29d22c9004cd8da872ceffc65dbc8a9fe9'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes())
assert len(plan['source_sha256'])==164
for p,d in plan['source_sha256'].items():assert sha(p)==d==sha(DEST/plan['source_archive'][p])
for p,d in plan['fixed_evidence_sha256'].items():assert sha(p)==d
assert sha(plan['environment']['python'])==plan['environment']['sha256']
assert plan['hard_timeout_seconds']==360 and plan['maximum_model_evaluations']==96
xml=ET.parse(OUT/'live_communication_scoped_inputs_v2_pure_001/tests.xml')
assert len(xml.findall('.//testcase'))==25 and not any(xml.findall('.//'+k) for k in ('failure','error','skipped'))
assert not any((DEST/n).exists() for n in ('execution_claim','external_application_wall.json'))
body=(HERE/'invoke_full32_future_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'full32_future_suffix_prepare_001':'live_communication_scoped_inputs_v2_prepare_001',
 'c48367f67be44aea409369d72f632228d28839fe1580fcda6bdacdabbdf7d811':expected,
 'ready_for_one_full32_future_suffix_conformance':'ready_for_one_scoped_v2_full96_conformance',
 'validate_full32_future_suffix --execute':'validate_live_communication_scoped_inputs_v2 --execute',
 "'execution_claim.json'":"'execution_claim'",
 'g31.full32_future_suffix.external_wall.v1':'g31.scoped_v2_full96.external_wall.v1',
 'shared_owned_seconds=360;fixed_rows=96;fixed_cases=3;maximum_initial_engines=48;maximum_prefix_cutpoints_per_group=4;maximum_suffixes=96;maximum_future_resumes=96;maximum_graph_forks=96;native_calls=0':'shared_owned_seconds=360;fixed_rows=96;fixed_cases=3;maximum_model_evaluations=96;expected_actual_collection_checks=226;expected_known_collections=192;native_calls=0',
 'Complete original3cases times32 Cartesian actions.16prefixes percase include earlier return_delay coordinate;48fresh A/B initial context pairs,atmost48engines96futureforks/resumes. Eachpair initial endpoints exact,only initial suppliedcontext/action enter model. Both laterchoices cloned from same unconsumed firstknownB before any suffix; strictwire/current/pastaction guards,unsupported firstcut retainsbothunknown,noadaptive replacement/restart. Complete returnedoutputs saved before targets; fullbytes/types/order/floathex/chronology andgraph/alias/count audits.162source/current/archive/evidence/runtime guards. All imports,48contextpairs,model/clones/96targets/export/exit within360;225s prior linear reference only. No scopedmodel optimization, nativeauthority,opaqueID relation,hiddenstatecoverage,onlineutility or100ms claim.':'Fixed original3cases times32 predictions using fresh public-input v2 scope. Frozen v1 worker code, full defining globals except four explicit bindings, all early-save/late-ordinal/226actual192known/full-output checks retained.164 sources; original initial context caller unchanged. Every complete prediction saved before original target validation. Modelspan includes save/hash/journal, not comparable to bare ABBA predictor span. All imports/setup/96models/targets/export/cleanup/exit within360. No future-fork combination, nativeauthority, hiddenstatecoverage, onlineutility or complete100ms claim.',
 'Whole Python full32 future suffix budget exceeded':'Whole Python scoped v2 full96 budget exceeded'}
for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
wrapper=HERE/'invoke_scoped_v2_full96_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.scoped_v2_full96.root_review.v1','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review_script_sha256':sha(__file__),'source_count':164,'focused_pure_tests':25,'retained_v1_pure_tests':53,
 'model_calls':0,'raw_decodes':0,'notes':[
 'Root read complete adapter and25 tests; entire frozen v1 worker reused with only candidate/schema/sourceproof/puregate changes, exact code/defaults/closure/full remaining globals preserved.',
 'All early saves, ordinal mapping only after complete original96, original226actual192known checks, full bytes/types/order/floathex output comparisons retained. No future target or old prediction enters candidate.',
 'V2 actual ABBA24 full exact already passed; initial context caller unchanged. Private table read optimization, no validation/endpoints/result caches.',
 'Accept only exact_all96_original_checks_and_full_outputs/full_output_exact96/unknown_or_difference0/actual_collection_data_checks226/actual_known_collection_data192/early mapping true/source unchanged, outer0 whole<=360.',
 'Default GC cleanup included in whole, modelspan includes early save/hash/journal and is not the prior bare predictor ABBA span. No native/full32 online/hiddenstate/100ms claim.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_scoped_v2_full96_conformance','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
