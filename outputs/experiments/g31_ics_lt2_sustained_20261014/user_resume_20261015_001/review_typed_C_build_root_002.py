from pathlib import Path
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import run_planning_v2_c_encoder_gate_v3 as gate
HERE=Path(__file__).resolve().parent;OUT=HERE.parent;ROOT=gate.old.ROOT
DEST=OUT/'planning_v2_C_encoder_gate_prepare_003';sha=gate.old.sha
expected='d6912d695e36707dbba6bd7a0359e5ec6c6ed1a964323e99c4aae4fecf28579b'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes());old=json.loads((OUT/'planning_v2_C_encoder_gate_prepare_002/plan.json').read_bytes())
assert len(plan['source_sha256'])==16 and len(plan['toolchain_sha256'])==7779 and len(plan['runtime_sha256'])==3082
for p,d in plan['source_sha256'].items():
    assert not Path(p).is_absolute() and not Path(p).drive
    current=(ROOT/p).resolve();archive=(DEST/'source'/p).resolve()
    assert current.is_relative_to(ROOT) and archive.is_relative_to(DEST) and current!=archive
    assert sha(current)==d==sha(archive)
assert all(plan['source_sha256'][p]==d for p,d in old['source_sha256'].items())
assert plan['toolchain_sha256']==old['toolchain_sha256'] and plan['runtime_sha256']==old['runtime_sha256']
ns=gate.namespace();assert ns['project_closure']()==plan['source_sha256']
for k in ('run','worker','build','functional','verify_plan','direct_probe','external_build_identity','actual_extension_identity','loaded_sources'):
    assert ns[k].__code__ is getattr(gate.old,k).__code__ and ns[k].__globals__ is ns
proof=gate.parent_main_tree()[1]
assert proof['inverse_AST_equals_frozen_main'] and proof['exact_replacements']==['.stdout.log','.stderr.log']
assert gate.previous.source_proof()['only_stdlib_enumeration_changed']
commands=json.loads((DEST/'commands.json').read_bytes())
assert commands==ns['commands'](DEST/'plan.json',expected,OUT/'planning_v2_C_encoder_build_002',OUT/'planning_v2_C_encoder_functional_002')
assert all(plan['budgets'][k]==120 for k in ('prepare_seconds','build_seconds','functional_seconds'))
assert plan['functional']['exact_test_count']==159 and plan['functional']['expected_direct_probe_count']==126 and plan['functional']['expected_fallback_probe_count']==10
assert sha(DEST/'receipt.json')=='8d6b89ad1f5c62b153042844073fc91d8a39aedd5c62e189a2ae017d8fba1a47'
assert sha(DEST/'bounded_execution.json')=='09023e671f702c1b832fd4be60d61bdd928b9c164f64da19153c67ab5da263b6'
pure=OUT/'planning_v2_C_encoder_parent_logs_pure_001'
assert sha(pure/'tests.xml')=='6dead86598baee2a3bcc02c0a756e1d492cba2c29a5f1369b127ecd46ce4306c'
assert sha(pure/'receipt.json')=='0e87ee399114da296f16bfb2fc78aaafbb4836493f011dc23cc594e974d6cff2'
xml=ET.parse(pure/'tests.xml');assert len(xml.findall('.//testcase'))==39
assert not any(xml.findall('.//'+k) for k in ('failure','error','skipped'))
assert not ns['BUILD'].exists() and not (OUT/'planning_v2_C_encoder_build_002').exists()
assert sha(OUT/'planning_v2_C_encoder_build_001/receipt.json')=='7024bc068d52648deb36236647942cf360dc3a3329db05bcdd4cd9304b703363'
result={'schema':'g31.planning_v2.C_encoder.root_build_review.v2','status':'one_build002_only_authorized',
 'plan_sha256':expected,'review_script_sha256':sha(__file__),'command':commands['build'],'project_sources_verified':16,
 'toolchain_members_declared':7779,'runtime_members_declared':3082,'external_inventory_files_rehashed_in_this_review':False,
 'repair_proof':proof,'notes':[
 'Root read entire v3 and17 new tests. Same old main after inverse two parent-log expression substitutions; original worker/command logs/readers remain. Tests really open parent files then invoke original run with fake subprocess, reproducing old collision and verifying new3modes and command failures.',
 'Fresh builddir002 and build/functional output002 only. Old metadata001 timeout and build001 failure frozen; all13 predecessor sources byte-identical. Current16 sources independently archived within destination and distinct from live paths.',
 'Full toolchain/runtime dictionaries same as prior, not rehashed again by root review; actual build and functional must perform original full entry/exit checks. No lowered120 budget or automatic retry.',
 'Build includes configure/targetcompile/imports/deps/archive, no extension load. Require successful receipt, bounded exit, exact external launch-through-exit ticks <=120 and command/plan/runner/wrapper/output binding.',
 'Functional needs separate review after actual accepted build. No native/model/actual fixtures/performance admitted by this build authorization.']}
path=DEST/'root_build_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'root_build_review_sha256':sha(path),'status':result['status']}))
