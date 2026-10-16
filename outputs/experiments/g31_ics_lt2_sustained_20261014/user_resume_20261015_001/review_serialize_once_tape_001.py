"""Source/pure/fixture readback review; no benchmark/native invocation."""
from pathlib import Path
import json,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from scripts.experiments.g31_ics_circulation import measure_serialize_once_tape as m
out=m.OUT/'serialize_once_tape_prepare_001'
assert m.base.sha(out/'plan.json')=='41491a21ab797038ccfa4939b54a5c4666c0bd5840fa68f79797ffe6cded9e2d'
assert m.base.sha(out/'ready.json')=='c6139f56527af3cf8a70125f3f405ad48c0db5307de172f16c0600cbc0dd7ef9'
plan=m.base.read(out/'plan.json');m.verify_pins(out,plan,runtime=True)
counts={k:sum(int(s.attrib.get(k,0)) for s in ET.parse(plan['tests']['path']).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=48,failures=0,errors=0,skipped=0) and len(plan['source_sha256'])==71
old=m.base.read(m.SOURCE_CASE/'campaign.json')
for name,digest in old['source_before'].items():assert m.base.sha(name)==digest,name
wrapper=Path(__file__).resolve().parent/'invoke_serialize_once_tape_001_measured.ps1'
report={'schema':'g31.serialize_once_tape.root_source_review.v1','status':'passed_fixed_saved_fixture_cost_gate_ready',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),'plan_sha256':m.base.sha(out/'plan.json'),
 'live_archive_source_count':71,'old_bridge_sources_unchanged':len(old['source_before']),
 'fixed_fixture_count':8,'pure_counts':counts,'wrapper_sha256':m.base.sha(wrapper),
 'reviewed_rules':[
 'Old Tape unchanged. Candidate captures args/kwargs before native call and serializes result before caller receives it.',
 'Decoded ordered row parity includes integer/string key collision, scalar types, signed zero, alias isolation, surrogate normalization and exceptions. Raw gzip bytes are newly generated.',
 'A final write/hash/manifest failure keeps partial artifacts and makes candidate instance unusable; no success or reuse after unmanifested failure.',
 'Fixed previous terminal-review last8 complete rows27210..27217; truncated27218 explicitly excluded. No measurement-window selection after results.',
 'ABBA four8-call batches include equal mock result deepcopy, complete Tape/level1gzip/hash/manifest and outer clock append. Batch covers all construction/gaps; load/readback/export retained in whole worker/parent.',
 'Source/fixture hashes, full ordered decoded row/clock/count and persisted-byte checks are inside owned120s run. External Stopwatch retains Python startup/cleanup/final receipt.',
 ],
 'limitations':['No native invocation or physical simulation.','Eight saved late mixed endpoints are a local logging-cost diagnostic, not full-stream prediction.','No 100ms, online-cache, two-machine, full-horizon or policy-equivalence certificate.','Unpaired-surrogate write offsets/partial bytes can differ, both fail.','Fail-stop on logging failure is deliberately stronger than legacy and all affected runs stay unknown.'],
 'native_calls':0,'benchmark_calls_in_review':0,'producer':{'path':str(Path(__file__).resolve()),'sha256':m.base.sha(__file__)}}
dest=out/'root_source_review_001.json'
with dest.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'review_sha256':m.base.sha(dest),'wrapper_sha256':m.base.sha(wrapper),'sources':71,'pure':48}))
