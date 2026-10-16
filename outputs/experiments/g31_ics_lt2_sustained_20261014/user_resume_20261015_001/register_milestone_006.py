"""Register actual original single-token completion and bounded negative findings."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
HERE = Path(__file__).resolve().parent
STATE = ROOT / 'docs/g31_ics_circulation/RESEARCH_STATE.json'
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
backup, report = HERE/'RESEARCH_STATE_before_milestone_006.json', HERE/'milestone_006.json'
assert not backup.exists() and not report.exists()
run = OUT/'original_low_wip_prepare_005'; receipt = read(run/'receipt.json')
assert receipt['status']=='worker_finished' and receipt['exit_code']==0 and receipt['source_changed']==[]
assert receipt['assessment']['status']=='observed_complete_and_empty'
assert receipt['verification']['status']=='passed_saved_raw_replay'
for name,digest in receipt['artifact_sha256'].items(): assert sha(run/name)==digest
names=['original_low_wip_prepare_005/receipt.json','original_low_wip_prepare_005/assessment.json',
       'original_low_wip005_independent_actual_review_001.json','full1x_saved_horizon_independent_review_001.json',
       'native027_acceptance_cost_001/receipt.json','regional_path_pool_micro_002/receipt.json']
evidence={name:sha(OUT/name) for name in names}
before=STATE.read_bytes(); state=json.loads(before); active=state['active_experiment']
active['startup_low_wip_candidate']='005 actual133.534547s and10305API saved replay passed; all22parked plus1supply, jobprojected:1x:2 unloaded19772.592/holdfinished19773.592, sameinitial:0:0 emptyat116. Original28506 input/R1false/22trays retained;3998actuallyarrivedbyH22200. Independent actual review82517889...a046e. All23physicalACKreceived,323physicaltraversals/0open. No secondreuse, strictprotection or100ms claim. New separate two-supply feasibility preparation underway.'
active['full1x_saved_audit_review']='Limited independent review0090b0fa...3028e: rehashed small sources/evidence and finalshard, not whole3GiB; actual producer summary exists and matches final.451shards/full28506/H86400/0complete, physicalaudit238traversals/0open. Original worker remains hard_timeout; no new native seal replay.1e-8 legacy summarydeadline tolerance not used for strict late count or pairedprotection.'
active['regional_path_cache_candidate']='New opt-in module49pure differential cases passed. Puremicro00218 declared saved-graph scenarios exactpaths/sourceunchanged but slower even99%hits (domestic124.82->188.27ms,international108.30->180.60ms per100activations). Negative retained; repeatedwholegraph-key hashing targeted in newcandidate. No actualflow hit-rate/speed/100ms claim or native run.'
state['current_stage']='Original1x saved full-day negative independently audited;2x same024 knownH64800 reconstruction active. Original lowWIP005 establishes one actual complete/empty token under unchanged28506input/22trays, independent10305API replaypassed; secondreuse pending.02721/44/9passed,60v3business pending bounded acceptance-cost optimization. Regionalcache firstmicro slower, correction under test. All three overall requirements remain unmet.'
state['next_actions'][1]='Prepare and execute separate same-token second-supply gate after true delivered completion selfcopy and current ownempty observation; current peer FIFOhead only, all28506 retained. No global peerOwner state, no same-zone fallback or later-job skipping.'
active['pending']=state['next_actions']
backup.write_bytes(before);write(STATE,state)
write(report,{'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'previous_state_sha256':sha(backup),'new_state_sha256':sha(STATE),'immutable_evidence':evidence,
 'single_supply_actual_assessment':receipt['assessment'],
 'scope':'One finite original completion is established; no whole-day business success, paired zero-regression, joint efficacy,100ms or second reuse acceptance.'})
print(json.dumps({'state_updated':True,'milestone_sha256':sha(report)}))
