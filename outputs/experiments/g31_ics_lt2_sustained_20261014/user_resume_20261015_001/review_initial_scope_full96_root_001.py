from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
OUT=HERE.parent
DEST=OUT/'live_communication_initial_scoped_inputs_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='8036d19b2f397551df1fe593f45b17097ef6cf314a6521319ad33b772cfb491c'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes())
assert len(plan['source_sha256'])==174
for p,d in plan['source_sha256'].items():assert sha(p)==d==sha(DEST/plan['source_archive'][p])
for p,d in plan['fixed_evidence_sha256'].items():assert sha(p)==d
assert sha(plan['environment']['python'])==plan['environment']['sha256']
assert plan['hard_timeout_seconds']==360 and plan['maximum_model_evaluations']==96
pure=OUT/'live_communication_initial_scoped_inputs_pure_002'
assert sha(pure/'receipt.json')=='ea0aad43fd78d8ffd1e8cbec99d37e625d677e147b3842545f795199154e8e3f'
assert sha(pure/'tests.xml')=='33abef2dae68e5611fcd672fb6f50bdb848ee21dfb6404f51f44909ce1c8f5c5'
xml=ET.parse(pure/'tests.xml')
assert len(xml.findall('.//testcase'))==29 and not any(xml.findall('.//'+k) for k in ('failure','error','skipped'))
assert not any((DEST/n).exists() for n in ('execution_claim','stdout.log','stderr.log','external_application_wall.json'))
body=(HERE/'invoke_scoped_v2_full96_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'live_communication_scoped_inputs_v2_prepare_001':'live_communication_initial_scoped_inputs_prepare_001',
 'd64ab44189e5c7cb3d79b109072a6f29d22c9004cd8da872ceffc65dbc8a9fe9':expected,
 'ready_for_one_scoped_v2_full96_conformance':'ready_for_one_initial_scope_full96_conformance',
 'validate_live_communication_scoped_inputs_v2 --execute':'validate_live_communication_initial_scoped_inputs --execute',
 'g31.scoped_v2_full96.external_wall.v1':'g31.initial_scope_full96.external_wall.v1',
 'Whole Python scoped v2 full96 budget exceeded':'Whole Python initial scope full96 budget exceeded'}
for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
start=body.index("    scope='");end=body.index("\n",start)
body=body[:start]+"    scope='Original96 full predictions, one fresh v2 scope shared only across each row initialcontext and prediction. Original four initial statements plus A/B guards and facts comparison retained through reversible AST; original future-context globals unchanged. Single original SaveBeforeReturn retains cumulative ordinals and all226actual192known/full-output/early-save checks.174 sources. Old modelspan excludes initial construction, includes export; whole360 includes all. No native/model-authority/100ms or bare-ABBA latency claim.'"+body[end:]
wrapper=HERE/'invoke_initial_scope_full96_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.initial_scope_full96.root_review.v1','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review_script_sha256':sha(__file__),'source_count':174,'focused_pure_tests':29,'retained_v1_pure_tests':53,
 'model_calls':0,'raw_decodes':0,'notes':[
 'Root read entire new adapter, pure driver and29 tests; only initial inline four-statement provider and predict context carrier change. Inverse AST restores exact original worker. Both owner guards/facts comparisons stay.',
 'Scope constructor identity and full original defining globals preserved; original future_context remains bound to original context. Private carrier is scope and validated initial only, not targets or raw outcome.',
 'One original SaveBeforeReturn over96, all early saves and late ordinal mapping and original226/192/full bytes/types/order/floathex comparisons retained. Synthetic96 exercises actual transformed inner and original outer.',
 'Prior initial+predictABBA24 complete exact; pure001 import failure preserved with0tests/0models and source snapshot. Pure00229passed; old171 unchanged.',
 'Accept only exact_all96_original_checks_and_full_outputs/full_output_exact96/unknown_or_difference0/226actual192known/earlymappingtrue/sourceunchanged and outer0whole<=360.',
 'Original model_wall excludes initial construction but whole includes it; no speed inference from this instrumented run, no native100ms claim. Stage logs absent before execute.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_initial_scope_full96_conformance','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
