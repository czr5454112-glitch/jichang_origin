"""Record full1x physical horizon and separately bounded pending evidence."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
HERE = Path(__file__).resolve().parent
STATE = ROOT / "docs/g31_ics_circulation/RESEARCH_STATE.json"

def read(path): return json.loads(path.read_text(encoding="utf-8-sig"))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, data): path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

backup, report = HERE / "RESEARCH_STATE_before_milestone_004.json", HERE / "milestone_004.json"
assert not backup.exists() and not report.exists()
run = OUT / "full024_resumed_1x_20261015_001"
part_path = run / "segments/0450.json.gz"
assert sha(part_path) == read(run / "segment_hashes/0450.json")["sha256"]
with gzip.open(part_path, "rt", encoding="utf-8") as stream: part = json.load(stream)
assert part["status"] == "reached" and part["control_continuation"]["physical_time"] == 86400.
assert part["native_state_sha256"] == "2afe5ca1214a9a6fdd322700622eacbcfc589777af680cdd871ba2d0e1287475"
jobs = part["result"]["jobs"]
assert len(jobs) == 28506 and sum(j["status"] == "in_transit" for j in jobs) == 18
assert sum(j["status"] == "waiting_for_tray" for j in jobs) == 28488
evidence_paths = [part_path, run / "segment_hashes/0450.json",
    OUT / "native027_build_001/receipt.json", OUT / "native027_timing_prepare_001/readiness.json",
    OUT / "native027_semantic_prepare_001/plan.json", OUT / "native027_semantic_wrapper_pure_001.xml",
    OUT / "native_preexisting_v3_delivery_prepare_002/preregistered_protocol.json",
    OUT / "native_preexisting_v3_integration_pure_003.xml",
    OUT / "chained_sealed_resume_review_002/receipt.json",
    OUT / "original_carrier_bound_002_independent_review/review.json",
    OUT / "original_notification_prepare_001/ready_receipt.json"]
evidence = {str(p.relative_to(ROOT)): sha(p) for p in evidence_paths}
before = STATE.read_bytes(); state = json.loads(before); active = state["active_experiment"]
state["current_stage"] = "Full1x reached86400 with28506arrivals and finalnative seal; preliminary finalshard0completed, full independent audit pending. Full2x continues. Native027 compiled only; actual21semantic/44timing gates pending. Waiting112 and0259-delivery remain next actual slots."
state["working_tree_identity"] = "codex/g31-ics-v3-circulation atc3fba566; uncommitted research; production89c2935 and parentPIBT preserved; running02448Python dependencies unchanged; opt-in027 compiled separately."
active["full024_status"] = "1x actualH86400/219576owneractivations/28506arrivals, finalseal2afe5ca1214a9a6fdd322700622eacbcfc589777af680cdd871ba2d0e1287475. Savedfinalshard18in_transit/28488waiting,0complete; final fullaudit pending.2xcontinues unchanged;7200s caps remain."
active["native027_sha256"] = "845486b745bc6e65a9988d1ef5429336b60fd472eb73c39e133e19ec93a7e7be"
active["native027_status"] = "67compiledsource archive unchanged; compileonlypassed.21semantic tests collected with17pure bounded-runner checks;44legacy/v3timing sessions prepared with76pure checks. Neither actualnativegate executed."
active["planning_v3_status"] = "65pure source-entry contract checks. Newconditionalmodel/actual collector/runner107pure integration checks; prepare0029rows/60source imports. Fixed unsupportedstationary lifecycle, floatingstart inverse and physical-action ACK across asynchronous capture union. AllterminalphysicalACK strictly before earliestcapture; equalepochunknown. Noatomic/current/modelprotectioncertificate."
active["original_notification_status"] = "Prepared6cell full28506notification operation probe;57purechecks/91sources. Nativepending; notificationbundle notoriginalbusinessadmission."
active["chained_resume_status"] = "Newseparate same024driver28purechecks+independentreview; ownschemas, allancestorcosts, fallbacktoancestorbeforefirstnewseal, exactCIM identities. Unexecuted; onlyafteractualterminalattempt and processabsence. Existingfullsourcesuntouched."
active["original_static_upper_bound"] = "Independentbitset/prefixDP agrees24505positivecapacityreachable/4001unreachable; underFIFO and permanentunreachableloadedcarriers, relaxedcompletion upper371with<=21badloaded,zero-badprefix39. Conditionalnecessaryboundonly, nofeasiblepolicy/onlinefutureknowledge/protectionclaim."
active["startup_low_wip_candidate"] = "Separate fulloriginalR1false22tray startupcrossownerparking andonesupply feasibility preparation; allofferedretained. Staticnecessaryparkingfitnotnativeexecution; noearlybusiness/protectionclaim."
state["next_actions"] = [
    "Finish original1x independent full-denominator audit; retain0completion if confirmed. Continue2x frozen024 within7200s cap; only after termination consider same024 chained sealed continuation.",
    "First actual slot release: waiting112003600s, then025nine delivery002 and ifpassed60business, then original notification probe. Maximum2nativeworkers; no third runtime session.",
    "Run02721semantic and44rawlegacy/timing gate before anyv3policy; preserve failures and exactsource/binary identity. Thenv3delivery002nine and conditional60business, all5jobs strictdelta<=0.",
    "Diagnose full1xactualresource/StorageFIFO blocking from savedraw; finish independent lowWIPstartup feasibility preparation on all28506/22 unchangedphysicalcontracts, then predeclare actualgate.",
    "Use actualoriginalnotification timing to decide whether unchanged-query reuse matters; do not rewrite request admission or omit setup/retry/ACK/failure costs.",
    "Register actualresults, failed/unknowns and currentzero-skip regression at a meaningful completed milestone. No commit/push or GPTPro send without user instruction."]
active["pending"] = state["next_actions"]
backup.write_bytes(before); write(STATE, state)
write(report, {"schema": "g31.resume_milestone.v1", "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "previous_state_sha256": sha(backup), "new_state_sha256": sha(STATE), "immutable_evidence": evidence,
    "full1x_receipt_at_observation": read(run / "receipt.json"),
    "full2x_heartbeat_at_observation": read(OUT / "full024_resumed_2x_20261015_001/heartbeat.json"),
    "scope": "Full1x physical horizon established by saved native terminal shard; full independent audit pending. No business/100ms/joint efficacy acceptance."})
print(json.dumps({"state_updated": True, "milestone_sha256": sha(report)}))
