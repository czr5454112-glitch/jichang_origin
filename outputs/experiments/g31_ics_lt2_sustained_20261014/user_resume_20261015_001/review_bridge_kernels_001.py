"""Root prelaunch review: fixed16 saved kernel diagnostic, no full audit."""
from pathlib import Path
from datetime import datetime,timezone
import json
from scripts.experiments.g31_ics_circulation import measure_bridge_saved_kernels as m
out=m.OUT/'bridge_saved_kernel_cost_prepare_001';here=Path(__file__).resolve().parent
expected='0f69d7b25e750a73134506dca70c54a40d3d894c719a4a6ba9075d647a371fbc'
assert m.sha(out/'plan.json')==expected
plan=m.strict_loads((out/'plan.json').read_text(encoding='utf8'));m.verify_pins(out,plan,runtime=True)
assert len(plan['source_sha256'])==79 and len(plan['files'])==16
assert m.sha(m.__file__)=='bb9e5a733d54e8aee68c84d6d994ce838765fe23782e6cc4561b15851e3e807b'
independent=out/'independent_source_review_legal_001.json'
assert m.sha(independent)=='1e78fc34c54142ec77f97ca7079ba10b6bd25ddeec052eac5377ae73a741523e'
assert not (out/'execution_claim.json').exists()
wrapper=here/'invoke_bridge_kernels_001_measured.ps1'
body=(here/'invoke_codec_saved72_001_measured.ps1').read_text(encoding='utf8')
changes={
 'complete_root_evidence_codec_independent_actual_review_001':'bridge_saved_kernel_cost_prepare_001',
 'b3121910c1d67b46873fc0fe920c1f4797130f3d5fc1816f132b58ba92c92afb':expected,
 'review_complete_root_evidence_codec_saved':'measure_bridge_saved_kernels',
 'ready_for_one_separate_saved_audit':'ready_for_one_bounded_kernel_diagnostic',
 'g31.complete_codec.independent_saved72.external_wall.v1':'g31.bridge.saved_kernel_cost.external_wall.v1',
 'whole_python_within_180_seconds=($taskWall -le 180)':'whole_python_within_120_seconds=($taskWall -le 120)',
 'shared_owned_seconds=180;fixed_historical_roots=18;saved_codec_calls=72;native_calls=0;predictor_calls=0':'shared_owned_seconds=120;fixed_inputs=16;comparison_calls=32;copy_calls=64;native_calls=0;policy_replay_calls=0',
 'new_codec_samples=0;original_producer_failed=$false;complete_native_request_100ms_certified=$false':'full_saved_audit_certified=$false;complete_native_request_100ms_certified=$false',
 'Independent unchanged full saved72 codec verifier. All18 historical source roots and72 full publication artifacts, original clocks, negative samples, all135 producer source and134 separate audit source entry/exit hashes remain. Launch/import/pins/readback/export/cleanup/exit included. No retiming, native or predictor.':'Fixed old/new tail8 only:32 comparisons and64 copies in two ABBA sequences, domain validation and all hash/decode/copy isolation/ordered typed verification/exports/cleanup inside whole wall. No raw_final, native, policy replay, full audit or business improvement claim.'
}
for before,after in changes.items():assert before in body,before;body=body.replace(before,after)
body=body.replace("if ($taskCode -ne 0) {exit $taskCode}","if ($taskCode -ne 0) {exit $taskCode}\nif ($taskWall -gt 120) {throw 'Whole Python diagnostic budget exceeded'}")
with wrapper.open('x',encoding='utf8',newline='\n') as stream:stream.write(body)
ref=lambda p:{'path':str(Path(p).resolve()),'sha256':m.sha(p)}
review=out/'root_source_review_001.json'
report={'schema':'g31.bridge.kernel.root_review.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'status':'ready_for_one_bounded_kernel_diagnostic','plan':ref(out/'plan.json'),
 'independent_review':ref(independent),'sources':79,'pure_tests':39,'fixed_input_files':16,'owned_seconds':120,
 'reviewed_rules':[
  'Read full module and39 synthetic tests. Exactly old/new ord27210..27217 bound to both complete manifests; no unmanifested27218 or raw_final read.',
  'ABBA32 comparisons preserve original native-wall-only exclusion. ABBA64 copies use independently verified builtin finite string-key decoded no-mutable-alias/surrogate domain; no generic deepcopy substitution claim.',
  'Every output independently checked by exact typed ordered floathex and mutable-container identity disjointness. Input hashes before/after and source/fixture pins remain.',
  'Timed kernel spans exclude independent checking/release; all of those plus source/import/hash/decode/report remain whole lifecycle. Both wall and CPU kept distinct.',
  'Failures preserve written measurement prefix. Hardkill may interrupt the last journal record; no full prefix completeness invented. Result cannot certify full37270 or all28506.',
  'Parent subtracts elapsed from120; explicit wrapper checks full Python launch-to-exit120. Agents confirmed no children/new heavy work before timing.'
 ],'source':ref(__file__),'wrapper':ref(wrapper)}
with review.open('x',encoding='utf8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as stream:json.dump({'status':report['status'],'plan_sha256':expected,
 'root_review':ref(review),'wrapper_sha256':m.sha(wrapper),'owned_seconds':120,'dispatched':False},stream,indent=2)
print(json.dumps({'review_sha256':m.sha(review),'ready_sha256':m.sha(ready),'wrapper_sha256':m.sha(wrapper)}))
