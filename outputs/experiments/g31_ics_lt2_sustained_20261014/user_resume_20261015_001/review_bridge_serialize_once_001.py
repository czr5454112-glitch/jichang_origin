"""Root review of logging-only original bridge; never native execution."""
from pathlib import Path
from datetime import datetime, timezone
import json, xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import launch_original_bridge_serialize_once as launcher
from scripts.experiments.g31_ics_circulation import verify_original_bridge_serialize_once as saved
r=launcher.r; base=r.base; here=Path(__file__).parent
out=r.OUT/'original_bridge_serialize_once_prepare_001'
expected='d976e7f2d473e64ddb4e11895c06bfb9f21a11b43133babb71cd02491bb94464'
assert base.sha(out/'campaign.json')==expected
campaign=r.isolated_runner().verify_campaign(out)
plan=base.read(out/'bridge/preregistered_protocol.json')
r.verify_pins(out/'bridge',plan,runtime=True)
assert len(plan['source_before'])==82 and len(plan['compiled_source_sha256'])==67
assert plan['offered']==28506 and plan['trays']==22 and plan['horizon']==86400
assert plan['max_physical_requests']==100 and plan['original_r1_permission'] is False
assert r.PREFIX_ROWS==27218 and r.LIMIT==2400
counts={k:sum(int(s.get(k,0)) for s in ET.parse(campaign['tests']['path']).getroot().iter('testsuite'))
        for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=93,failures=0,errors=0,skipped=0)
old=r.reference_pins(); assert len(old['source_before'])==76
assert r.MeasuredSerializedTape.__init__ is r.original.MeasuredTape.__init__
assert r.MeasuredSerializedTape.__getattr__ is r.original.MeasuredTape.__getattr__
assert r.MeasuredSerializedTape.clock is r.original.MeasuredTape.clock
private=r.runner_namespace()
for name in ('worker','campaign_worker','measured_run','isolated_base','assess'):
    assert private[name].__code__ is getattr(r.original,name).__code__
assert private['policy'] is r.policy
assert launcher.launcher_namespace()['main'].__code__ is launcher.original.main.__code__
assert base.sha(r.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert not (out/'external_launch_claim.json').exists()
wrapper=here/'invoke_bridge_serialize_once_001_measured.ps1'
assert not wrapper.exists()
text=(here/'invoke_original_cooperative_bridge_001_measured.ps1').read_text(encoding='utf8')
changes={
 'original_cooperative_bridge_prepare_001':'original_bridge_serialize_once_prepare_001',
 '406c5e2ef785805888be33e0d6e79812cc4d0a64f3c18d1bcaea33eb7cbc3655':expected,
 'launch_original_cooperative_bridge':'launch_original_bridge_serialize_once',
 'g31.original_cooperative_bridge.external_application_wall.v1':'g31.original_bridge.serialize_once.external_application_wall.v1',
 'full saved policy and physical replay, all28506 job-state export':'full saved policy and physical replay plus every ordered row/hash of the old27218 complete API prefix, all28506 job-state export',
}
for before,after in changes.items():
    assert before in text; text=text.replace(before,after)
line="$taskWrapperSha=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()"
text=text.replace(line,line+"\n$taskReady=Get-Content -LiteralPath (Join-Path $taskFolder 'root_ready_001.json') -Raw | ConvertFrom-Json\nif ($taskReady.status -ne 'ready_for_one_bounded_actual_attempt' -or $taskReady.campaign_sha256 -ne $taskCampaignSha -or $taskReady.wrapper_sha256 -ne $taskWrapperSha) {throw 'Reviewed wrapper or campaign changed'}")
text=text.replace("    exclusions='PowerShell/tool startup", "    concurrent_experiment_policy='Launch only after initial-request timing window closes. This full-day functional trial may overlap source/pure development; no isolated latency benchmark or application speedup ratio is claimed.'\n    logging_amendment='Only serialize-once Tape. Same BridgeOwner,10s cadence,all raw fields,39/78/100 caps,original026 physical semantics; old timeout remains failure. Fixed8 Tape ratio is not an application forecast.'\n    exclusions='PowerShell/tool startup")
with wrapper.open('x',encoding='utf8',newline='\n') as f: f.write(text)
review=out/'root_prelaunch_review_001.json'
report={'schema':'g31.original_bridge.serialize_once.root_review.v1',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),'status':'passed_logging_only_source_review',
 'campaign_sha256':expected,'case_plan_sha256':base.sha(out/'bridge/preregistered_protocol.json'),
 'live_archive_sources_verified':82,'compiled026_archive_sources_verified':67,'old76_unchanged':True,
 'pure_tests':counts,'native_executions':0,'model_evaluations':0,
 'checks':[
  'Original BridgeOwner,run_policy,worker,campaign,assessor,launcher and MeasuredTape methods retain exact code; private globals change only declared Tape/schema/source bindings.',
  'SerializedOnceTape preserves decoded ordered arguments before call and results before return; all fixed32 mock outputs and clocks independently verified.',
  'Entire original saved policy/physical verifier reused; old27218 complete manifest rows hashed and compared at the matching new replay read, only finite nonnegative advance wall_seconds normalized.',
  'All28506 offered jobs,22 trays,mandatoryStorage/FIFO/cap0/R1false/10s/H86400 and39/78/100 limits unchanged.',
  'One fresh accepted026 process,full save/replay and old prefix audit share2400; prepared package never restarted.',
 ],
 'limits':['Old001 timed out;26delivered facts only lower bound, no fullH certificate.',
           'Local8row Tape68.1% saving does not promise whole application speedup/fullH/100ms.',
           'FullH finite observation and actual cap closure are separate from alloffered success and strict perjob protection.'],
 'producer':{'path':str(Path(__file__).resolve()),'sha256':base.sha(__file__)},
 'wrapper':{'path':str(wrapper.resolve()),'sha256':base.sha(wrapper)}}
with review.open('x',encoding='utf8') as f: json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as f:
    json.dump({'status':'ready_for_one_bounded_actual_attempt','campaign_sha256':expected,
      'root_review_sha256':base.sha(review),'wrapper_sha256':base.sha(wrapper),
      'dispatch_condition':'Initial-request exclusive latency window completed before launch.',
      'native_dispatched':False,'shared_owned_seconds':2400},f,indent=2)
print(json.dumps({'review_sha256':base.sha(review),'ready_sha256':base.sha(ready),'wrapper_sha256':base.sha(wrapper)}))
