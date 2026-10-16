from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
OUT=HERE.parent
DEST=OUT/'scoped_public_inputs_profile_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='3feceff367cd3f44693444e0e3fe765a593b0738e2c530f0b38a7f588651fd30'
assert sha(DEST/'plan.json')==expected
assert sha(DEST/'independent_narrow_review_legal_001.json')=='f155f62db462d7d059f8b364366515c7a5b819c3636066d8ed9a3f08c25565fd'
plan=json.loads((DEST/'plan.json').read_bytes());assert len(plan['source_sha256'])==154
for p,d in plan['source_sha256'].items():assert sha(p)==d==sha(DEST/plan['source_archive'][p])
for p,d in plan['evidence_sha256'].items():assert sha(p)==d
assert not any((DEST/n).exists() for n in ('execution_claim','external_application_wall.json'))
template=(HERE/'invoke_lazy_six_profile_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'live_lazy_six_profile_prepare_001':'scoped_public_inputs_profile_prepare_001',
 '222b1d66267921229866970bfd00ac843fa740e9e2a2695c786a3809887f7e85':expected,
 'ready_for_one_fixed_lazy_six_profile_diagnostic':'ready_for_one_fixed_scoped_six_profile_diagnostic',
 'profile_live_lazy_six --execute':'profile_scoped_public_inputs_six --execute',
 'g31.lazy_six_profile.external_wall.v1':'g31.scoped_six_profile.external_wall.v1',
 'Fixed6 unchanged lazy predictions with separate lawful initial context and model cProfiles. Full prediction bytes and ordered semantic/chronology equality after saved output.107source archives and input/model identities entryexit, defaultGC. All imports/hash/decode/profiles/exports/audits/cleanup inside120. Profiles diagnose current work only: cumulative times overlap, no speedup/native/full32/100ms claim.':'Fixed6 complete scoped candidate predictions with separate unchanged initial context and model cProfiles. Fresh PublicInputScope construction/private binding and every unchanged guard/model run inside callback. Full prediction saved before comparison to original bytes/types/floathex/chronology.154source/current/archive/input/runtime guards,defaultGC. Scope cycle cleanup may happen after return; whole120includes allimports/hash/decode/profiles/export/audit/processcleanup/exit. One AST model-import replacement and report schema, original worker checks retained. Cumulative times overlap and profiler perturbs work; no uninstrumented speed/native/full32/complete100ms claim.',
 'Whole Python lazy six profile budget exceeded':'Whole Python scoped six profile budget exceeded'}
for old,new in replacements.items():assert template.count(old)==1,old;template=template.replace(old,new)
wrapper=HERE/'invoke_scoped_profile_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(template)
review={'schema':'g31.scoped_profile.root_review.v1','plan_sha256':expected,
 'root_review_script_sha256':sha(__file__),'wrapper_sha256':sha(wrapper),'source_count':154,
 'new_binding_pure_tests':4,'retained_original_profile_tests':12,'model_calls':0,'raw_decodes':0,
 'notes':['Root authored and read complete profile adapter and4tests; original profile driver and12tests previously read and retained unchanged.',
 'Independent legal narrowreview f155f62db462d7d059f8b364366515c7a5b819c3636066d8ed9a3f08c25565fd found no source blocker; reviewed limits retained.',
 'Only one worker model import plus report schema changes; entire candidate.predict creates scope within profiler callback. Both initial contexts retain original6 separate profiles.',
 'Every full output saved before target comparison; fullbytes/types/floathex/chronology exact,unknown remains6denominator. Source/loaded/input guards unchanged.',
 'Shared120 includes profiler artifacts/readback/cleanup/exit, defaultGC. No fullcleanup percallback or uninstrumented performance inference.',
 'Accept exact_six_profiled_diagnostic with exact6unknown0model6/sourceunchanged,outerexit0whole<=120.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_fixed_scoped_six_profile_diagnostic','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
