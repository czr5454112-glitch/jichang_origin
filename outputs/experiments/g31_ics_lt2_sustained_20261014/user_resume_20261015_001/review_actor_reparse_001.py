"""Root review of fixed16 same-text second-parse copy diagnostic."""
from pathlib import Path
from datetime import datetime,timezone
import json
from scripts.experiments.g31_ics_circulation import measure_bridge_actor_reparse as m
here=Path(__file__).resolve().parent;out=m.OUT/'bridge_actor_reparse_prepare_001'
expected='c56c64f5ecdd0aa3cd71f23eb9ef2bb6d9c65c7e9d0e2071a52890a74fcf234e'
assert m.sha(out/'plan.json')==expected
plan=m.frozen.strict_loads((out/'plan.json').read_text(encoding='utf8'))
m.verify_pins(out,plan,runtime=True)
assert len(plan['sources'])==80 and plan['pure']['counts']=={'tests':50,'failures':0,'errors':0,'skipped':0}
assert m.sha(m.__file__)=='37a27d521cbf52734bf8ddd3a587502ec7f1cebe700d108725a9e49e73ad67d6'
assert not (out/'execution_claim.json').exists()
original=here/'invoke_bridge_kernels_001_measured.ps1'
assert m.sha(original)=='6c8f96a054e6e34ca437a3afab2a0c2223a18f21af57630d0a7c92cf493eb8c0'
body=original.read_text(encoding='utf8')
changes={
 'bridge_saved_kernel_cost_prepare_001':'bridge_actor_reparse_prepare_001',
 '0f69d7b25e750a73134506dca70c54a40d3d894c719a4a6ba9075d647a371fbc':expected,
 'measure_bridge_saved_kernels':'measure_bridge_actor_reparse',
 'g31.bridge.saved_kernel_cost.external_wall.v1':'g31.bridge.actor_second_parse.external_wall.v1',
 'comparison_calls=32;copy_calls=64':'comparison_calls=0;copy_calls=64;first_observer_parses=16;second_actor_parses=32;actor_deepcopies=32',
 'Fixed old/new tail8 only:32 comparisons and64 copies in two ABBA sequences, domain validation and all hash/decode/copy isolation/ordered typed verification/exports/cleanup inside whole wall. No raw_final, native, policy replay, full audit or business improvement claim.':
 'Fixed old/new tail8 only. ABBA64 actor copies:32deepcopy versus32 standard json.loads of same original private decompressed text, no reencode. Initial16 observer decompressions/parses and all domain/exact type-order-floathex/isolation/hash/export/cleanup retained in wholewall. No new data, native, policy, fullaudit or business100ms certification.'
}
for before,after in changes.items():assert body.count(before)==1,before;body=body.replace(before,after)
wrapper=here/'invoke_actor_reparse_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as stream:stream.write(body)
ref=lambda p:{'path':str(Path(p).resolve()),'sha256':m.sha(p)}
review=out/'root_source_review_001.json'
report={'schema':'g31.bridge.actor_second_parse.root_review.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'status':'ready_for_one_bounded_kernel_diagnostic','plan':ref(out/'plan.json'),'sources':80,'pure_tests':50,
 'fixed_inputs':16,'owned_seconds':120,'new_native_or_policy_calls':0,
 'reviewed_rules':[
  'Read entire diagnostic and50 synthetic tests. Same fixed16 raw bytes as prior tail8 diagnostic; original standard JSON default semantics retained, including duplicate-key handling and text newline translation.',
  'A is deepcopy(result), B is exact json.loads(text)[result] with no hooks/encode/newread. Full B parse and disposal of non-result fields occur inside its measured call.',
  'First16 decompression/parse/domain costs remain in whole clock. Successful parsed domain is exact finite builtin string-key no-cycle/no-mutable-alias/no-surrogate; no generic copy substitution claimed.',
  'All64 outputs checked for full type/order/floathex and container disjointness from allobserver rows; original input/text fingerprints and source/input hashes checked entry/exit.',
  'Both per-call wall and CPU measured. Independent validation, result release, hashes, journals/export and cleanup outside inner spans remain inside whole Python.',
  'Previous encode+decode result1.91percent does not measure this decode-only hypothesis. No policy/default audit change or full600 guarantee from this diagnostic.',
  'Legal/R1/control reported no active children and held heavy work before dispatch. Parent shared120 plus outerlaunch-to-exit120 enforced; every failure retained.'
 ],'source':ref(__file__),'wrapper':ref(wrapper)}
with review.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,allow_nan=False)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as stream:json.dump({'status':report['status'],'plan_sha256':expected,
 'root_review':ref(review),'wrapper_sha256':m.sha(wrapper),'owned_seconds':120,'dispatched':False},stream,indent=2)
print(json.dumps({'review_sha256':m.sha(review),'ready_sha256':m.sha(ready),'wrapper_sha256':m.sha(wrapper)}))
