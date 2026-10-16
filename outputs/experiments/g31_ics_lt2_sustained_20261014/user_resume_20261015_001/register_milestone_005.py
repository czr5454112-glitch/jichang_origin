"""Register observed results without changing the original experimental receipts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
HERE = Path(__file__).resolve().parent
STATE = ROOT / 'docs/g31_ics_circulation/RESEARCH_STATE.json'
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, v): p.write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')

backup = HERE / 'RESEARCH_STATE_before_milestone_005.json'
report = HERE / 'milestone_005.json'
assert not backup.exists() and not report.exists()
audit_path = OUT / 'full1x_saved_horizon_audit_001.json'
audit = read(audit_path)
assert sha(audit_path) == '424b27acb33bf71870602bf536db825cabc04f3ec1436bde8affaf6d08fbaa10'
assert audit['status'] == 'passed_saved_physical_horizon' and audit['offered'] == 28506 and audit['completed'] == 0
delivery = read(OUT / 'native_preexisting_v3_delivery_prepare_003/receipt.json')
assert delivery['status'] == 'executed' and delivery['comparisons']['status'] == 'passed'
evidence_names = [
    'full1x_saved_horizon_audit_001.json', 'saved_horizon_audit_prepare_001/bounded_execution.json',
    'full024_resumed_1x_20261015_001/receipt.json', 'full024_resumed_2x_20261015_001/receipt.json',
    'user_resume_20261015_001/full1x_termination_observation_001.json',
    'user_resume_20261015_001/full2x_termination_observation_001.json',
    'full024_chained_cut_2x_20261015_001/cut_manifest.json',
    'full024_chained_cut_2x_20261015_001/source_stop_receipt.json',
    'user_resume_20261015_001/active_process_identity_005.json',
    'native027_accepted_contract_001.json', 'native027_accepted_reference_001.json',
    'native027_semantic_native_002/receipt.json', 'native027_timing_prepare_002/independent_verification.json',
    'native_preexisting_v3_delivery_prepare_003/receipt.json',
    'native_preexisting_delivery_003/receipt.json', 'native_preexisting_business_003/receipt.json',
    'native_preexisting_business_003_failure_diagnosis.json',
    'original_waiting112_prepare_003/parent_receipt.json',
    'original_notification_native_002/independent_verification.json',
    'original_notification_parity_review_001.json',
    'original_notification_native_002_independent_summary_001.json',
    'original_low_wip_prepare_004/receipt.json',
    'original_low_wip_prepare_005/preregistered_protocol.json',
    'original_low_wip_prepare_005_independent_source_review.json',
]
evidence = {name: sha(OUT / name) for name in evidence_names}
before = STATE.read_bytes(); state = json.loads(before); active = state['active_experiment']
state['current_stage'] = 'Original1x saved full86400 horizon independently audited: all28506 offered,0completed. Original2x terminal7200s attempt preserved; same024 chained knownH64800 reconstruction running.027 actual21semantic/44timing/9delivery passed.02560business10assessed/50unknown; physical preference semantics mismatch diagnosed. LowWIP005 actual running after bounded IO retry review.100ms and joint efficacy remain unmet.'
active['full024_status'] = '1x original worker hard_timeout7200.317308s; separate read-only full451shard audit passed in1452.642251s, H86400/all28506/0complete/18in_transit/28488waiting. Producer-reported finalseal2afe5ca...87475; no independent native replay claim.2x oldworker hard_timeout7200.3213332s, lastH66393.22646; next attempt reconstructs latestsealedH64800, retaining all prior costs.'
active['native027_status'] = 'Actual21semantic002 and44legacy/v3timing002 independently passed with exact accepted binary. Accepted contractdb7c4bd...269dc6 published. Failed semantic001 fixtures preserved; no native C++ patch. Finite semantics/instrumentation acceptance only.'
active['planning_v3_status'] = '107pure integration; actual nine initial delivery cases003 passed in94.4773572s,6normal/3negative,60source closure unchanged. Laterv3 business60 pending; runtime contract reread cost under diagnosis. No current/atomic/model protection certification.'
active['preexisting_delivery_gate'] = '025nine delivery003 passed after exact body-row coverage order correction; failed002 preserved.02560business003 actual86.246893s:10assessed/50unknown. All60 completed5jobs/audit, but50 initialR1receiving_full and14 selectedreuse3/actual8 mismatches. PreferenceACK is not hard path reservation; old pure forced-wait projection needs correction.'
active['original_waiting_gate'] = '003 actual10.2340174s passed executability only; H9922.702 and1000activations, updatedACK plus actual112to113EDGE_ENTER. Separate allR1authorized28506 research input; no original business benefit/protection claim.'
active['original_notification_status'] = 'Native0026cells independently passed notification-operation campaign with raw semantic service parity; only measured advance_to.wall_seconds excluded from behavioral equality, all original timing retained. Full setup charged to roots. Original business admission/100ms remain uncertified; failed parity001 retained.'
active['chained_resume_status'] = 'full024_chained_2x_20261015_001 launched after exact parent/worker absence; same024, latest397shardH64800seal4fd9d542...4e2f must match before continuation.7200s cap includes reconstruction and audit, ancestor reconstruction294.1024068s and excluded-tail costs retained. Actual processidentity005 saved.'
active['startup_low_wip_candidate'] = '004 actual91.7936s interrupted by PermissionError heartbeat atomic replacement atH14060; lastsavedH14050 all22parked/one supply submitted.005 only bounded PermissionError retry7attempts/0.56s requested sleep;72pure and independent source review passed. Same28506/R1false/22trays/H22200/600s cap; actual005 running, completion unclaimed.'
state['next_actions'] = [
    'Finish same024 2x knownH64800 reconstruction and actual continuation within7200s, at most2 native workers; all frozen original sources preserved.',
    'Finish lowWIP005 actual bounded experiment and independently audit first real unload/hold/empty token; preserve failures without skipping offered jobs or FIFO heads.',
    'Correct pure route-preference semantics against actual shield dispatch. Keep rejected routes and unsupported later captures unknown. Compare executable revised joint candidates against equally informed strong references.',
    'Avoid repeating costly44branch file verification in every v3 projection only with exact lifecycle identity guards and retained cost; then execute original60 v3 business branches within180s.',
    'Implement isolated opt-in regional path-cache candidate with exact ordering/float/occupancy semantics and pure differential tests, then actual paired replay. Complete request accounting includes setup, retries, validation and ACK.',
    'Update problem/solution evidence, perform current zero-skip regression when a coherent source milestone freezes. No commit/push/GPTPro send without user instruction.',
]
active['pending'] = state['next_actions']
state['lt2_sustained_progress']['full0241x_saved_horizon_audit'] = {k:audit[k] for k in [
    'status','producer_receipt_status','physical_horizon_completed','offered','completed','unfinished',
    'max_owner_activation_ms','owner_activation_over100ms_count','complete_request_100ms_certified']}
backup.write_bytes(before); write(STATE,state)
write(report, {'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
    'previous_state_sha256':sha(backup),'new_state_sha256':sha(STATE),'immutable_evidence':evidence,
    'active_chain_receipt_snapshot':read(OUT/'full024_chained_2x_20261015_001/receipt.json'),
    'active_chain_reconstruction_snapshot':read(OUT/'full024_chained_2x_20261015_001/reconstruction_heartbeat.json'),
    'scope':'Actual finite gates and independently audited full1x negative result; no full original business,100ms or joint efficacy acceptance.'})
print(json.dumps({'state_updated':True,'milestone_sha256':sha(report)}))
