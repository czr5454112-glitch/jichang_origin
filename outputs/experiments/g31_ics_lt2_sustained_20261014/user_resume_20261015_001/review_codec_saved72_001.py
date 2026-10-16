"""Root source/pin review for unchanged complete saved72 verifier."""
from pathlib import Path
from datetime import datetime,timezone
import json
from scripts.experiments.g31_ics_circulation import review_complete_root_evidence_codec_saved as reader
c=reader.c
out=c.OUT/'complete_root_evidence_codec_independent_actual_review_001';here=Path(__file__).resolve().parent
expected='b3121910c1d67b46873fc0fe920c1f4797130f3d5fc1816f132b58ba92c92afb'
audit=reader.verify_prepared(out,expected)
producer,evidence,outer,receipt,ledger=reader.producer_state(Path(audit['source_directory']))
loaded=reader.actual_loaded(producer,audit,receipt)
assert len(audit['source_sha256'])==134 and len(producer['source_sha256'])==135 and len(ledger)==72
assert c.sha(reader.__file__)=='028ddffbc12e74d53e0d2f0156b9208b386057bc3a0d9f248964411c7eb8d52e'
assert not (out/'execution_claim.json').exists()
wrapper=here/'invoke_codec_saved72_001_measured.ps1'
body=(here/'invoke_saved_entry_recovery_001_measured.ps1').read_text(encoding='utf8')
changes={
 'initial_owner_route_entry_independent_actual_review_001':'complete_root_evidence_codec_independent_actual_review_001',
 '5363525a3a3203f2d1783ad4b93c856384852b4366faf29c4b1fca698b845a3e':expected,
 'review_initial_owner_route_entry_saved_v2':'review_complete_root_evidence_codec_saved',
 'g31.initial_entry.separate_saved_recovery.external_wall.v1':'g31.complete_codec.independent_saved72.external_wall.v1',
 'fixed_saved_branches=18':'fixed_historical_roots=18;saved_codec_calls=72',
 "original_producer_failed=$true;producer_exit_import_proof='unknown_not_recreated'":"new_codec_samples=0;original_producer_failed=$false;complete_native_request_100ms_certified=$false",
 'Independent full saved endpoint/physical/RPC/gate/outbox audit after repaired verifier globals. Full launch/import/pin/read/decode/check/export/cleanup/exit cost is included. No native rerun. Original producer exit1 and missing receipt remain.':'Independent unchanged full saved72 codec verifier. All18 historical source roots and72 full publication artifacts, original clocks, negative samples, all135 producer source and134 separate audit source entry/exit hashes remain. Launch/import/pins/readback/export/cleanup/exit included. No retiming, native or predictor.'
}
for before,after in changes.items():assert before in body;body=body.replace(before,after)
with wrapper.open('x',encoding='utf8',newline='\n') as stream:stream.write(body)
review=out/'root_source_review_001.json'
report={'schema':'g31.complete_codec.independent_saved72.root_review.v1',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),'status':'ready_for_one_separate_saved_audit',
 'plan':c.reference(out/'plan.json'),'reader':c.reference(reader.__file__),
 'audit_sources':134,'producer_sources':135,'loaded_audit_sources':len(loaded),
 'saved_roots':18,'saved_publications':72,'owned_seconds':180,
 'reviewed_rules':[
  'Read full independent reader. It calls frozen verify_saved directly once, preserving every original ordered/type/clock/query-proof check and both unknown fixture roots.',
  'All recomputed fields compare by exact_tree including finite float bits/order. The sole setup timing field is separately finite-positive and bounded by original whole wall.',
  'Producer command/owned Job/exit0/complete ledger and original exact entry/exit imported-source projection checked. All135 original live/archive and134 audit sources checked separately.',
  'All72 artifacts rehashed before decode by original verifier and on exit. Inputs use original producer pins. No bindings or publication rerun.',
  'Sample/export chronology and entire sample span are checked. Individual losses remain. No whole-request100ms or online physical success can be inferred from mocks.',
  'Parent BOOT through source checks subtracts from fixed180 worker allowance. Outer clock retains startup, exit, export and cleanup without division.'
 ],'source':c.reference(__file__),'wrapper':c.reference(wrapper)}
with review.open('x',encoding='utf8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as stream:json.dump({'status':'ready_for_one_separate_saved_audit',
 'plan_sha256':expected,'root_review':c.reference(review),'wrapper_sha256':c.sha(wrapper),
 'owned_seconds':180,'dispatched':False},stream,indent=2)
print(json.dumps({'review_sha256':c.sha(review),'ready_sha256':c.sha(ready),'wrapper_sha256':c.sha(wrapper)}))
