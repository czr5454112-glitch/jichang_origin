from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DEST=OUT/'planning_v2_batched_digest_cost_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='4288d316218b81f9ef743301ba0e9da9add3e909328c496eb40428ed0032d49d'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes())
assert len(plan['sources'])==12
for p,d in plan['sources'].items():assert sha(ROOT/p)==d==sha(DEST/'source'/p)
for item in plan['files']:assert sha(item['source'])==item['sha256']==sha(DEST/'fixtures'/item['file'])
for ref in plan['pure'].values():assert sha(ref['path'])==ref['sha256']
assert sha('C:/PROGRAMING/python3.11.9/python.exe')==plan['interpreter_sha256']
xml=ET.parse(plan['pure']['xml']['path'])
assert len(xml.findall('.//testcase'))==123
assert not xml.findall('.//failure') and not xml.findall('.//error') and not xml.findall('.//skipped')
assert plan['counts']==dict(query_rows=2,envelopes=2,batches=8,repetitions_per_batch=4,measured_digest_calls=32,A_digest_calls=16,B_digest_calls=16,additional_complete_byte_encoder_calls=4,total_typed_encoder_runs=36,profiles=0)
assert not any((DEST/n).exists() for n in ('execution_claim.json','campaign_outer_claim.json','external_application_wall.json'))
body=(HERE/'invoke_planning_v2_digest_diagnostic_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'planning_v2_digest_prepare_002':'planning_v2_batched_digest_cost_prepare_001',
 'f9b74d4f92b247a228fa891d000bae1bd00f8d038253562adec31e9e272e1187':expected,
 'ready_for_one_planning_v2_digest_diagnostic':'ready_for_one_batched_digest_fixed_two_comparison',
 'launch_planning_v2_digest_v2 --execute':'launch_planning_v2_batched_digest_cost --execute',
 'g31.planning_v2_digest_diagnostic.external_wall.v1':'g31.planning_v2_batched_digest_cost.external_wall.v1',
 'digest_calls=32;C_extension_loads=0':'measured_digest_calls=32;full_byte_encoder_calls=4;total_encoder_runs=36;C_extension_loads=0',
 'Fixed two historical v2 query rows,new27212/new27215,allone-envelope denominators.32 original digest calls in8ABBA batches,A16 original and B16 same original under cProfile,not optimization. Same saved native payload digest,complete original compressed/raw hashes and all bounded builtin/schema guards. Four profiles verified against original function counts. All source/input/guard/hash/export/readback/exit inside120. No fullpolicy or600 attribution and no100ms claim.':'Fixed two historical v2 captures,new27212/new27215,allone-envelope denominator.32 measured digest calls in8ABBA batches,A16 original and B16 batched including full builtin preflight and grouping guards. Four additional complete typed encodings, exact full bytes and saved native SHA before measurement; four binary files reread within120. No profiler/forced GC. Complete original compressed/raw input and source/runtime guards, all setup/36encoders/journal/export/readback/exit inside120. Isolated callable and diagnostic guard costs separated; no full policy, whole600 attribution or100ms claim.',
 'Whole Python planning_v2_digest_diagnostic budget exceeded':'Whole Python batched digest fixed two budget exceeded'}
for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
wrapper=HERE/'invoke_batched_digest_cost_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.batched_digest_cost.root_review.v1','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review_script_sha256':sha(__file__),'source_count':12,'pure_tests':123,'real_raw_decodes':0,
 'notes':['Root read complete candidate/original writer and75 cases previously, now full measure/launcher and48 focused harness cases, plus inherited decode/metadata/count/write guards.',
 'Exact2 actual fixed compressed rows and metadata, no inferred trimming.32 unprofiled ABBA calls and4 additional full byte encodings. Complete bytes precede SHA reliance; actual B oracle requires fast path.',
 'B nested span includes full recursive builtin preflight and grouping; all guards/metadata/raw readback/export also inside common owned120. Default GC unchanged.',
 'Per-sample immutable bodyhash/mutation guard; original native payload SHA required. Saved reader rechecks every32/8/2 count and chronology,4 binary artifacts, source/runtime inputs; no extra encoding.',
 'First123pure run failed one overly broad hash stub; test-only correction preserves failure archive and new123pure002 passes. Original75 candidate unchanged.',
 'Accept completed_fixed_batched_comparison plus passed_saved_complete_bytes_and_measurements,32records8batches2pairs/4oracles,exit0whole<=120. No delivered policy authority/native simulation/whole600 or100ms inference.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_batched_digest_fixed_two_comparison','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
