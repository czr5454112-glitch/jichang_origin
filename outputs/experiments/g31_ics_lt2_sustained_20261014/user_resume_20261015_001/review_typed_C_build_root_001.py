from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import run_planning_v2_c_encoder_gate_v2 as gate
HERE=Path(__file__).resolve().parent;OUT=HERE.parent;ROOT=gate.old.ROOT
DEST=OUT/'planning_v2_C_encoder_gate_prepare_002'
sha=gate.old.sha
expected='4df2e3fa3f122effb56b0468d685b58b9f742232eb714123ce31013f23732b7a'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes())
assert len(plan['source_sha256'])==13 and len(plan['toolchain_sha256'])==7779 and len(plan['runtime_sha256'])==3082
for p,d in plan['source_sha256'].items():assert sha(ROOT/p)==d==sha(DEST/'source'/p)
ns=gate.namespace();assert ns['project_closure']()==plan['source_sha256']
for k in ('main','worker','build','functional','verify_plan','direct_probe','external_build_identity','actual_extension_identity'):
    assert ns[k].__code__ is getattr(gate.old,k).__code__ and ns[k].__globals__ is ns
assert gate.source_proof()['only_stdlib_enumeration_changed']
commands=json.loads((DEST/'commands.json').read_bytes())
assert commands==ns['commands'](DEST/'plan.json',expected,OUT/'planning_v2_C_encoder_build_001',OUT/'planning_v2_C_encoder_functional_001')
assert all(plan['budgets'][k]==120 for k in ('prepare_seconds','build_seconds','functional_seconds'))
assert plan['functional']['exact_test_count']==159 and plan['functional']['expected_direct_probe_count']==126
assert plan['functional']['expected_fallback_probe_count']==10
assert sha(DEST/'receipt.json')=='0619f4d512d845f80ec5596794930803dda13b30794077f0ffab66e7c4fc0403'
assert sha(DEST/'bounded_execution.json')=='bdb9873cb13db193b423c757e6321533c955626a1aa3742f0384eb60181ee0c5'
pure=OUT/'planning_v2_C_encoder_enumeration_pure_001'
assert sha(pure/'tests.xml')=='c34548a30b134922cc298d90bb56976b3dbd4defe84c563065a36ea2b28c15c7'
xml=ET.parse(pure/'tests.xml');assert len(xml.findall('.//testcase'))==22
assert not any(xml.findall('.//'+k) for k in ('failure','error','skipped'))
assert not ns['BUILD'].exists() and not (OUT/'planning_v2_C_encoder_build_001').exists()
result={'schema':'g31.planning_v2.C_encoder.root_build_review.v1','status':'one_build_only_authorized',
 'plan_sha256':expected,'review_script_sha256':sha(__file__),'command':commands['build'],
 'project_sources_verified':13,'toolchain_members_declared':7779,'runtime_members_declared':3082,
 'external_toolchain_and_runtime_rehashed_in_this_root_review':False,
 'notes':[
 'Root read old complete orchestration and new v2 enumeration/private binding plus22tests. Original seven core sources and narrow legal/root source reviews unchanged.',
 'Only stdlib subtree walk is pruned by the same exclusion/file predicate. Full project/toolchain/runtime before and after hash verification retained; original main/build/functional code and full defining namespaces kept.',
 'Build-only owned120 includes entry, fresh build, imports/deps inspection, archive and exit checks. Exact external Stopwatch ticks command/plan/runner/wrapper/output binding is required.',
 'The full external dependency inventories are not rehashed here; actual build and functional entry and exit require them. Metadata-only count evidence is not execution evidence.',
 'No extension may load during build. Actual module origin and concrete loaded DLL hashes required after functional tests. MSVCP140 explicit extra import remains pinned.',
 'Functional execution needs separate acceptance of successful build receipt, bounded receipt and external whole<=120; not authorized by build success alone. No actual fixtures/native/model/performance.']}
path=DEST/'root_build_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'root_build_review_sha256':sha(path),'status':result['status']}))
