"""Root review of separate actual-entry18 package, before any dispatch."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import initial_owner_route_entry_campaign as c
from scripts.experiments.g31_ics_circulation import launch_initial_owner_route_entry_campaign as launcher
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_entry_campaign as verifier
out=c.OUT/'initial_owner_route_entry_campaign_prepare_001';here=Path(__file__).resolve().parent
expected='d37d3e0ea9378974a8a331b97c21be48d6dfe3bab9c18d08b686c68041bd0097'
plan=c.verify_plan(out,expected)
assert len(plan['source_sha256'])==151 and len(plan['compiled_source_archive_sha256'])==67 and len(plan['rows'])==18
loaded=c.check_loaded_sources(plan)
counts={k:sum(int(s.get(k,0)) for s in ET.parse(plan['pure_XML']['path']).getroot().iter('testsuite'))
        for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=186,failures=0,errors=0,skipped=0)
assert plan['pure_XML']['sha256']=='1eccdf028fd47fbc76a76171b348bab0ee14f68ea7be61a33982150373757a49'
older=c.OUT/'initial_owner_route_gate_campaign_prepare_002';previous=c.read(older/'campaign.json')
assert len(previous['source_sha256'])==141
for name,digest in previous['source_sha256'].items():
    assert plan['source_sha256'][name]==c.sha(name)==c.sha(older/previous['source_archive'][name])==digest
assert plan['rows']==previous['rows'] and plan['input_file_sha256']==previous['input_file_sha256']
assert c.contract.closure is c.integrated.entry.old.closure
assert c.run_branch.__globals__['CapturedRequest'] is c.integrated.CapturedRequest
assert c.worker.__globals__['run_branch'] is c.run_branch
assert verifier._root_original.__globals__['c'] is c
assert verifier.root_replay.__globals__['old'].root_replay is verifier._root_original
assert verifier._original_verify_branch.__globals__['root_replay'] is verifier.root_replay
assert verifier.verify_saved.__globals__['verify_branch'] is verifier.verify_branch
assert c.sha(c.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert not (out/'execution_claim.json').exists()
wrapper=here/'invoke_initial_owner_entry_001_measured.ps1'
text=(here/'invoke_initial_owner_gate_002_measured.ps1').read_text(encoding='utf8')
changes={
 'initial_owner_route_gate_campaign_prepare_002':'initial_owner_route_entry_campaign_prepare_001',
 '659685e577db515a56d2229aa546b15b6a0ba7e6c903d014d9f353df4c9614c4':expected,
 'launch_initial_owner_route_gate_campaign_v2':'launch_initial_owner_route_entry_campaign',
 'eaaafb556436f2203f6527ca457672c174e2965ab1997a723701151abccd4151':c.sha(launcher.__file__),
 'g31.initial_owner_route_gate.external_application_wall.v1':'g31.initial_owner_route_entry.external_application_wall.v1',
 'Fresh historical96 native and saved review completed. Before dispatch all agents confirmed no active children and paused new pure, native, compile, benchmark and heavy I/O until this performance window closes.':'Fresh unloading96 and saved review completed. Bridge saved audit ended before dispatch. All agents confirmed no active children and paused new pure, native, compile, benchmark and heavy I/O until this exclusive performance window closes.',
 'saved full refresh/outbox/endpoint/RPC/physical verification':'saved full refresh/outbox/endpoint/RPC/physical verification with new source-bound actual entry predicate in both root replay layers',
}
for before,after in changes.items():assert before in text;text=text.replace(before,after)
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(text)
report={'schema':'g31.initial_owner_entry.root_prelaunch_review.v1',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),'status':'passed_finite_native_attempt_ready',
 'campaign_sha256':expected,'source_preparation':c.reference(out/'source_preparation.json'),
 'live_archive_sources_verified':151,'compiled027_archive_sources_verified':67,
 'loaded_project_sources_verified':len(loaded),'old141_source_package_unchanged':True,
 'pure_tests':counts,'startup_reference':plan['startup_reference'],
 'reviewed_rules':[
  'All18 original rows/input bytes/faults, finite2 action domain, acceptedNativeSession027 and exactLocalTransport, fixed background .05 schedule remain.',
  'Only root observe and postdrain calls use the new private contract facade. Current source0 prefix[0] plus actual accepted027 matching current traversal EDGE_ENTER-derived finite future exit bound prove entry; reservation without the bound cannot.',
  'Original postexit outputs, finalsource/receiver revalidation, real delivered routeACK and complete postquery same-time native drain remain. No earlier root may close solely from an accepted submission or predicted end.',
  'Private subclass retains original chain authority checks with exact new observe/drain identities. Original closure and fixed continuation policy code unchanged. No module/class monkeypatch or native proxy.',
  'Earlier closure can remove later root admissions and change request IDs. Complete later actual endpoint/physical outcome audit remains; no unchangedtape or timing causality claim transfers from gatev2.',
  'All old gate/query/outbox/full evidence remains, with new observation-contract marker before complete normalize/encode. Strict roundtrip/hash/ledger/caller tail and all cold failure costs retained.',
  'Saved verifier original root replay and v3 wrapper both privately bind new c.contract. All original endpoint, physical, RPC, failed-root, full query replay and gate audit codes remain.',
  'One shared600 owned tree/18branches/onepredictor; original100ms complete-root boundary remains and no startup/wholecampaign cost is divided. Exclusive dispatch separately required.',
 ],
 'limits':['Finite2 initial request only; full32 and universal100ms remain open.',
           'No actual result until producer and independent full saved audits finish.',
           'Agent-exclusive window cannot control unrelated user/system load.',
           'No original-day or online strong-method certificate.'],
 'producer':c.reference(__file__),'wrapper':c.reference(wrapper),'native_executions':0,'model_evaluations':0}
review=out/'root_prelaunch_review_001.json';ready=out/'root_ready_001.json'
with review.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
with ready.open('x',encoding='utf8') as f:json.dump({'status':'ready_for_one_bounded_actual_attempt',
 'campaign_sha256':expected,'root_review':c.reference(review),'wrapper_sha256':c.sha(wrapper),
 'native_dispatched':False,'fixed_native_branches':18,'owned_seconds':600},f,indent=2)
print(json.dumps({'review_sha256':c.sha(review),'ready_sha256':c.sha(ready),
 'wrapper_sha256':c.sha(wrapper),'launcher_sha256':c.sha(launcher.__file__)}))
