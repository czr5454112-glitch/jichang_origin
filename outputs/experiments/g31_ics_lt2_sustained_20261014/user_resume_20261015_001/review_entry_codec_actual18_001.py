"""Root review before fresh finite actual18 with complete codec composition."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import initial_owner_route_entry_codec_campaign as c
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_entry_codec_campaign as v
from scripts.experiments.g31_ics_circulation import launch_initial_owner_route_entry_codec_campaign as launch
out=c.OUT/'initial_owner_route_entry_codec_campaign_prepare_001';here=Path(__file__).resolve().parent
expected='8884b22d2de102693a8ca3855b0d22ffda10312b2e7806908edd26caaa2dd61a'
plan=c.verify_plan(out,expected);loaded=c.check_loaded_sources(plan)
assert len(plan['source_sha256'])==169 and len(plan['compiled_source_archive_sha256'])==67
assert len(plan['rows'])==18 and plan['hard_timeout_seconds']==600.
counts={k:sum(int(s.get(k,0)) for s in ET.parse(plan['pure_XML']['path']).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=41,failures=0,errors=0,skipped=0)
assert plan['pure_XML']['sha256']=='a36001896b0356014a0fb8d87521acb90ae4f3f3c94ef2ebf6657441607f6886'
for directory,name,count in (('initial_owner_route_entry_campaign_prepare_001','campaign.json',151),('complete_root_evidence_codec_pair_prepare_001','plan.json',135)):
    folder=c.OUT/directory;old=c.read(folder/name);assert len(old['source_sha256'])==count
    for path,digest in old['source_sha256'].items():assert plan['source_sha256'][path]==c.sha(path)==c.sha(folder/old['source_archive'][path])==digest
old=c.read(c.OUT/'initial_owner_route_entry_campaign_prepare_001/campaign.json')
assert plan['rows']==old['rows'] and plan['input_file_sha256']==old['input_file_sha256']
assert all(not missing for missing in v.source_proof()['recursive_LOAD_GLOBAL_missing'].values())
assert v.verify_saved.__globals__['verify_branch'] is v.verify_branch
assert v.root_replay.__globals__['c'] is v._root_original.__globals__['c'] is c
assert c.sha(c.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert not (out/'execution_claim.json').exists()
wrapper=here/'invoke_entry_codec_actual18_001_measured.ps1'
body=(here/'invoke_initial_owner_entry_001_measured.ps1').read_text(encoding='utf8')
changes={
 'initial_owner_route_entry_campaign_prepare_001':'initial_owner_route_entry_codec_campaign_prepare_001',
 'd37d3e0ea9378974a8a331b97c21be48d6dfe3bab9c18d08b686c68041bd0097':expected,
 'launch_initial_owner_route_entry_campaign':'launch_initial_owner_route_entry_codec_campaign',
 'f82942bb5f590bf855d4d2ef9b57ecfa2fc03baeefd7b67a0e2b98def17952d4':c.sha(launch.__file__),
 'g31.initial_owner_route_entry.external_application_wall.v1':'g31.initial_owner_entry_complete_codec.external_wall.v1',
 'Fresh unloading96 and saved review completed. Bridge saved audit ended before dispatch.':'All prior native/saved jobs closed. Offline communication conformance002 ended at its hard cap and is preserved. Fixed bridge kernel diagnostic completed before this fresh native dispatch.',
 'with new source-bound actual entry predicate in both root replay layers':'with actual entry predicate in both root replay layers, repaired complete verifier globals and full strict evidence codec'
}
for before,after in changes.items():assert before in body,before;body=body.replace(before,after)
with wrapper.open('x',encoding='utf8',newline='\n') as stream:stream.write(body)
review=out/'root_prelaunch_review_001.json'
report={'schema':'g31.initial_entry_codec.actual18.root_review.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'status':'passed_finite_native_attempt_ready','campaign_sha256':expected,'sources':169,'compiled_sources':67,
 'loaded_project_sources':len(loaded),'pure_tests':counts,'prior151_and_codec135_unchanged':True,
 'reviewed_rules':[
  'Read full campaign/verifier/launcher/prepare/tests plus previously reviewed composition. Same18 input bytes/faults/finite2 choices/fullH40/five-business targets. Original100ms and60ms cutoffs remain.',
  'Only complete evidence codec is composed with exact original entry observation/native handle/transport/drain/ACK/finalvalidate and scheduler. Actual query proof/entry marker/full typed data remain inside root; strict decode/reencode before return.',
  'Worker changes exactly one saved-verifier import with inverse AST proof. Correct defining-v3 namespace is inherited from successful repairedv2, not failedv1. Every nine check code/default/closure unchanged, recursiveLOAD_GLOBAL resolved.',
  'Both original and wrapper root replays privately bind this campaign; complete physical/endpoint/RPC/gate/outbox/marker guards retained.41 focused tests include real worker final import path smoke and Path-to-plan execution plus negative actual-entry guards.',
  'Original151 producer exit1 and missing receipt/verification/import-exit proof preserved; independent saved recovery identity and exact72 codec audit pinned. No retroactive producer success.',
  'Cold setup, native/RPC work, full normalization/codec/hash/ledger/publication/return, export/full saved checks/cleanup charged. One native/one pure predictor within600; no division by18 or physical clock subtraction.',
  'Descriptive comparison only to prior actual rounds. Every unknown/default/negative retained, including decision cutoff fallback. Neither100ms nor full32 nor all-day efficacy preregistered as passed.',
  'Dispatch requires previous kernel job closed and all-agent exclusive performance window. Unrelated system load is not controlled.'
 ],'source':c.reference(__file__),'wrapper':c.reference(wrapper),'native_dispatched':False}
with review.open('x',encoding='utf8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as stream:json.dump({'status':'ready_for_one_bounded_actual_attempt','campaign_sha256':expected,
 'root_review':c.reference(review),'wrapper_sha256':c.sha(wrapper),'owned_seconds':600,'native_dispatched':False},stream,indent=2)
print(json.dumps({'review_sha256':c.sha(review),'ready_sha256':c.sha(ready),'wrapper_sha256':c.sha(wrapper),'launcher_sha256':c.sha(launch.__file__)}))
