"""One-time record of reconstructed2x and corrected evidence boundaries."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
HERE = Path(__file__).resolve().parent
STATE = ROOT / "docs/g31_ics_circulation/RESEARCH_STATE.json"
def read(path): return json.loads(path.read_text(encoding="utf-8-sig"))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")

backup, report = HERE/"RESEARCH_STATE_before_milestone_003.json", HERE/"milestone_003.json"
assert not backup.exists() and not report.exists()
observed = {}
for name in ("full024_resumed_1x_20261015_001", "full024_resumed_2x_20261015_001"):
    run = OUT/name
    reconstruction = read(run/"reconstruction.json")
    assert reconstruction["status"] == "verified_against_known_native_seal"
    observed[name] = {"reconstruction": reconstruction, "receipt_status": read(run/"receipt.json")["status"],
        "heartbeat_at_observation": read(run/"heartbeat.json"), "reconstruction_sha256": sha(run/"reconstruction.json")}
assert observed["full024_resumed_2x_20261015_001"]["reconstruction"]["native_state_sha256"] == "51aeeb7879336c40ce0b369f870bee5c0f3e38e863c251ce52cb0a8e7e1ced76"
audit = OUT/"inflight_capture_bounds_audit_002.json"
value = read(audit)
assert value["status"] == "passed" and value["checks"] == value["checks_passed"] == 67
assert value["branch_count"] == 12 and value["decision_count"] == 24 and value["moving_decision_count"] == 4
waiting = OUT/"original_waiting112_prepare_003/preregistered_protocol.json"
if not waiting.exists(): waiting = OUT/"original_waiting112_prepare_003/plan.json"
delivery = OUT/"native_preexisting_delivery_002/preregistered_protocol.json"
assert sha(delivery) == "0d02c272da6361eeb0e6676209d7d9f8205198fc502bad9a633b9b364c119a22"
assert sha(waiting) == "8efaf997df6673b74ff918967294e39d60022cd32a7fc1cf6e304300b77e28e0"
before = STATE.read_bytes(); state = json.loads(before)
state["current_stage"] = "Comprehensive resume continues. Both original024 full streams reconstructed against historical native seals and are running. Native026 acceptance passed separately. Waiting112 and3tray5job delivery gates frozen after evidence corrections. Opt-in native027 observed-entry messages and conditional stable-domain predictor under implementation, not native-accepted."
active = state["active_experiment"]
active["full024_status"] = "1x269parts/H54000/842.8983s and2x137parts/H28800/294.1024s actual reconstruction exactly matched historical native seals; both continue unchanged to86400. Full-day metrics remain null until final independent verification."
active["original_waiting_gate"] = "Prepared003,48 pure tests. First lawful stationary112to113 action requires delivered updated ACK and observed entry/finished crossing, not edge reservation alone. No native execution yet; first released slot."
active["preexisting_delivery_gate"] = "Prepared002,9branches,91 pure tests; exact raw/input/archive/digest/fault checks and pinned180s bounded launcher. Still unexecuted;60business branches require actual independent gate success."
active["inflight_bounds_correction"] = "Generic capture+travel upper bound withdrawn because reservation may precede entry. Audit002 retained12branches/24decisions;4public-only cases unknown, ownobservedexit conditional,67checks passed. Old4fallbacks unchanged."
active["planning_v3_status"] = "Pure source-observed-entry contract reviewed; native027 implementation and separate conditional stable-interval predictor underway. Same timestamps/consistent counts do not prove atomic or simultaneous state. Native tests drafted, not executed. Existingv1/v2 unaffected."
active["installed_operation_status"] = "Native0017cases/9roots;8closed/1missingACK unknown. Separate setup amendment corrects small gaps: initialized service2.3491-8.7324ms, diagnostic-inclusive309.5863-440.8651ms, wholeworker5.6883s conservative bounds. Archive omitted2 startup src imports; provenance limitation/supplement pending, no retrospective pre-run pin. Original business100ms remains uncertified."
state["next_actions"] = [
    "Continue both frozen024 full28506/57012 attempts to86400 within existing7200s caps; independent final all-offered audit required.",
    "First freed native slot: waiting112 prepared003600s gate, then nine delivery gate and conditional60business branches, then full-input notification-operation probe; maximum2nativeworkers.",
    "Finish opt-in027 observed-entry native contract, explicit versioned timing acceptance and actual source/peer/ACK/digest/checkpoint/legacy parity before policy use.",
    "Finish separate conditional stable capture-interval predictor with all declared jobs/resources and strong matched methods; no atomic/current/protection certificate from supplied data.",
    "Complete original notification probe with actual import closure, saved-call independent verifier and setup/whole-worker accounting; finite operation bounds do not redefine originalbusiness admission.",
    "Freeze a meaningful current milestone for unified zero-skip regression and immutable evidence registration. Retain failed/unknowns and no new commit/push."]
active["pending"] = state["next_actions"]
backup.write_bytes(before); write(STATE, state)
write(report, {"schema": "g31.resume_milestone.v1", "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "previous_state_sha256": sha(backup), "new_state_sha256": sha(STATE), "full_stream_observation": observed,
    "immutable_evidence": {str(p.relative_to(ROOT)): sha(p) for p in (audit, waiting, delivery)},
    "scope": "Observed running state and corrected claims; no full-day, original complete100ms or joint efficacy success."})
print(json.dumps({"state_updated": True, "milestone_sha256": sha(report)}))
