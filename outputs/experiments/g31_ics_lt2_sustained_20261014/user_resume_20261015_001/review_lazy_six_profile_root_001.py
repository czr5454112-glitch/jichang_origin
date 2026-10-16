from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DEST=OUT/'live_lazy_six_profile_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='222b1d66267921229866970bfd00ac843fa740e9e2a2695c786a3809887f7e85'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes())
assert len(plan['source_sha256'])==107 and plan['hard_application_seconds']==120
assert plan['maximum_model_calls']==plan['maximum_initial_context_profiles']==6
assert sha(ROOT/'scripts/experiments/g31_ics_circulation/profile_live_lazy_six.py')=='de761e9d9763e4c0513214cfa08ee9bdaf796f092a825ea02a49567290dade49'
for path,digest in plan['source_sha256'].items():assert sha(path)==digest==sha(DEST/plan['source_archive'][path]),path
assert not (DEST/'execution_claim').exists()
body=(HERE/'invoke_C_publisher_saved_root_001_measured.ps1').read_text(encoding='utf8')
replace={
 'C_publisher_saved_review_prepare_001':'live_lazy_six_profile_prepare_001',
 '510ee1590e4c871eff6f25dd2ef5bf69262850575aaf50fb42e5cb1b086ce1d9':expected,
 'ready_for_one_independent_C_publisher_saved_review':'ready_for_one_fixed_lazy_six_profile_diagnostic',
 'review_complete_root_c_publisher_saved':'profile_live_lazy_six',
 'g31.C_publisher.independent_saved.external_wall.v1':'g31.lazy_six_profile.external_wall.v1',
 'shared_owned_seconds=120;fixed_inputs=18;saved_publisher_rows=72;C_extension_loads=0;model_calls=0;native_simulation_calls=0':'shared_owned_seconds=120;fixed_inputs=6;maximum_initial_context_profiles=6;maximum_model_profiles=6;C_extension_loads=0;model_calls=6;native_simulation_calls=0',
 'Independent saved-only72 complete publisher records against18 original fixtures. Original145/169/135source and6124toolchain/raw/runtime guards; strict types/order/floathex and regenerated clocks; original event/deadline fields retained;36samples perarm and all18paired outcomes recomputed. Producer direct18C support and alias facts remain producer observations. No C loading/model/native/performance or complete100ms claim.':'Fixed6 unchanged lazy predictions with separate lawful initial context and model cProfiles. Full prediction bytes and ordered semantic/chronology equality after saved output.107source archives and input/model identities entryexit, defaultGC. All imports/hash/decode/profiles/exports/audits/cleanup inside120. Profiles diagnose current work only: cumulative times overlap, no speedup/native/full32/100ms claim.',
 'Whole Python independent C publisher saved review budget exceeded':'Whole Python lazy six profile budget exceeded',
}
for old,new in replace.items():assert body.count(old)==1,old;body=body.replace(old,new)
wrapper=HERE/'invoke_lazy_six_profile_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.lazy_six_profile.root_review.v1','plan_sha256':expected,'source_count':107,
 'source_sha256':sha(__file__),'wrapper_sha256':sha(wrapper),'dispatched':False,
 'review':['Driver and12focused tests read in full. Six fixed real inputs/order; one unchanged lazy.predict and one original initial-context construction profile percase.',
  'No candidate timing inference from instrumented wall. Perfunction self/cumulative/calls kept separately; overlap not summed.',
  'Both owner initialcontext guards and identical facts retained. Complete prediction saved before comparison target reads. All6 and all errors retained.',
  'Full byte and exactordered type/float semantics plus allcollections chronology compared with frozen lazy. No actual future observations entermodel.',
  'Parent imports,107live/archive pins and input identities,profileexports,comparison,exports/exit included shared120. DefaultGC and0C/native enforced.',
  'Require exact_six_profiled_diagnostic,6modelcalls0unknown,unchangedpins,externalexit0 andwhole<=120. Diagnostic only, no100ms/coverage/joint efficacy.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_fixed_lazy_six_profile_diagnostic','plan_sha256':expected,
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')},'wrapper_sha256':sha(wrapper)}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review_sha256':sha(DEST/'root_source_review_001.json'),'ready_sha256':sha(DEST/'root_ready_001.json'),'wrapper_sha256':sha(wrapper)}))
