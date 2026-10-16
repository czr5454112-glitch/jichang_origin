from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DEST=OUT/'planning_v2_C_encoder_source_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='f644e09943a967e9daf43ff377c6e8ba8a57416186e8ad1c966fa2ac7b6f2592'
assert sha(DEST/'source_plan.json')==expected
plan=json.loads((DEST/'source_plan.json').read_bytes());assert len(plan['sources'])==7
for name,digest in plan['sources'].items():assert sha(ROOT/name)==sha(DEST/'source'/name)==digest
independent=DEST/'independent_narrow_review_legal_001.json'
assert sha(independent)=='cf6ed935705dff5395d18b191ae60d6df5bd5a7228da6f0cbdee65d92100fea9'
review={'schema':'g31.planning_v2.C_encoder.root_source_review.v1','source_plan_sha256':expected,
 'root_review_script_sha256':sha(__file__),'source_files_checked':7,
 'independent_review_sha256':sha(independent),'builds':0,'C_loads':0,'tests':0,
 'actual_fixture_reads':0,'native_calls':0,'model_calls':0,'performance_runs':0,
 'conclusion':'No concrete source blocker found in the declared stable exact-builtin CPython3.11.9 domain. Not executable/build/functional or performance acceptance.',
 'notes':[
 'Root read entire C traversal, original Python writer, candidate wrapper, all compiled boundary-test source and CMake. Field/group/list ordering checked against original including both coverage groups and ACK is-not-None.',
 'Exact dict/list/scalar paths avoid supplied hooks. Visited mapping key types checked before lookup. Unsupported marker only leads to original once, no catch-and-retry on Unicode or resource exception. No whole supplied value preflight.',
 'uint64 arbitrary integer mask, bool integer and floating, signed zero/NaN/Inf via same PyFloat_Pack8, strict Unicode UTF8 retained. Large integer double deliberately unsupported, original struct retains overflow/error ordering.',
 'Fullbytes oracle changes only final hashlib on original function code/globals; original local writer retained. Functional gate must separately require direct C bytes and record unsupported fallback; passing fallback is not C support.',
 'No normalization/native authority, validation shortcut, hiddenstate access, input mutation, crosscall result cache or automatic production installation. Allocation/interrupt failure timing explicitly not equivalent.',
 'Seven-file snapshot is not the execution closure. Separate source/toolchain/runtime closure and stage-budget acceptance needed before build/load.',
 'New gate runner separately reviewed with pending corrections: bind successfulbuild external whole<=120 beforefunctional load, inspect explicit C module provenance outside sys.modules, and resolve only evidenced standard C++ DLL imports. Not a build dispatch authorization by this report alone.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
print(json.dumps({'root_source_review':sha(DEST/'root_source_review_001.json')}))
