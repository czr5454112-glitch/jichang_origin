"""Root source and complete campaign review, no native dispatch."""
from datetime import datetime, timezone
from pathlib import Path
import json
from scripts.experiments.g31_ics_circulation import research_original_cooperative_bridge as r

here=Path(__file__).resolve().parent;folder=here.parent/'original_cooperative_bridge_prepare_001'
assert r.base.sha(folder/'campaign.json')=='406c5e2ef785805888be33e0d6e79812cc4d0a64f3c18d1bcaea33eb7cbc3655'
campaign=r.verify_campaign(folder);plan=r.base.read(folder/'bridge/preregistered_protocol.json')
assert r.base.sha(folder/'bridge/preregistered_protocol.json')=='a8c51ab4062940da0919733b59072f6a9897e69c99d66a7b83423d15aea68d28'
assert campaign['tests']['counts']=={'tests':109,'failures':0,'errors':0,'skipped':0}
assert plan['offered']==28506 and plan['trays']==22 and plan['horizon']==86400. and plan['original_r1_permission'] is False
assert len(plan['compiled_source_sha256'])==67
parent=r.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert r.base.sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
wrapper=here/'invoke_original_cooperative_bridge_001_measured.ps1'
def ref(p):return {'path':str(p.resolve()),'sha256':r.base.sha(p)}
record={'status':'passed_root_fresh_bridge_source_and_pins_review','recorded_utc':datetime.now(timezone.utc).isoformat(),'campaign':ref(folder/'campaign.json'),'plan':ref(folder/'bridge/preregistered_protocol.json'),'wrapper':ref(wrapper),'source_count':len(plan['source_before']),'compiled_archived_sources':67,'pure_tests':109,'native_authority':'accepted026 archived67 sources+build+acceptance+binary; current027 not compared','reviewed':['FullBridgeOwner/currentcompactFIFO selfcopy join, strict actual current-possession/action/completion watermarks and onebridge peractualcompletion.','Private FunctionType fullnamespace injection; frozen005 owner startup; explicit BridgeOwner in native and savedreplay.','All28506 jobs/22tray identities, per-sourceFIFO, mandatoryStorage, actual EMPTY_RECEIVED/LOAD/UNLOAD/HOLD and21 stationaryparked evidence.','Complete86400 observation separate from39/78 cap relay certificate.','Lossless API/tape plus nesteddiagnosticclocks, shared2400 owned subtree, immutable claims/failedprefix/partialhashes and finalalljobstates.'],'native_branches':1,'max_native_workers':1,'shared_owned_job_seconds':2400,'observations':['109pure includes initial actual005 H20 fullAPI wiring; only a fresh actual complete run can verify longerstartup and bridge effects.','Global failurehalt is experimentmanagement, not owner-visible distributed coordination.','Oldcap8 remains historical, not a fairpair or strictprotection baseline.'],'parent_user_file_sha256':r.base.sha(parent),'native_dispatched':0,'alloffered_business_success':False,'complete100ms_certified':False}
dest=folder/'root_prelaunch_review_001.json';assert not dest.exists();r.base.write(dest,record)
print(json.dumps({'review':ref(dest),'wrapper':ref(wrapper),'source_count':len(plan['source_before'])}))
