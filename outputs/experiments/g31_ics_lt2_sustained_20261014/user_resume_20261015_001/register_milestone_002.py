"""Record observed resume milestones, preserving the previous research state."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
HERE = Path(__file__).resolve().parent
STATE = ROOT / "docs/g31_ics_circulation/RESEARCH_STATE.json"

def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

before = STATE.read_bytes()
backup = HERE / "RESEARCH_STATE_before_milestone_002.json"
report_path = HERE / "milestone_002.json"
assert not backup.exists() and not report_path.exists()
gate_path = OUT / "native026_acceptance_001/receipt.json"
gate = read(gate_path)
assert gate["status"] == "passed" and gate["source_changed"] == gate["input_changed"] == []
one_path = OUT / "full024_resumed_1x_20261015_001/reconstruction.json"
one = read(one_path)
assert one["status"] == "verified_against_known_native_seal"
assert one["native_state_sha256"] == "ba49c0393be8041544a122bb7da45aab57be8419c04c907b950943b6bd18134d"
two_path = OUT / "full024_resumed_2x_20261015_001/receipt.json"
two = read(two_path)
assert two["status"] in {"running", "completed"}
probe_path = OUT / "installed_operation_native_001/receipt.json"
probe = read(probe_path)
state = json.loads(before)
state["current_stage"] = "User comprehensive resume active. Actual1x269part reconstruction matched originalH54000 seal and continued;2x launched fromH28800. Native026 full late acceptance passed. Finite installed-operation native probe completed; setup-gap and cold-start scope amendment in progress. Full-day business, original complete100ms and joint effectiveness remain unmet."
next_actions = [
    "Complete both preregistered7200s full-input attempts; retain prior measured costs, all28506/57012 jobs, H86400 and independent full-day verification.",
    "Keep024 binary and all imported policy/resume sources frozen while both full-day workers run;026 was accepted separately and is not a live binary substitution.",
    "Amend finite-operation accounting using saved native evidence, disclose setup gaps and cold/diagnostic wall sensitivity, then prepare original full-population real-request probe.",
    "Prepare first-lawful-stationary112to113 original one-command gate with unchanged2s wire delay and actual ACK/edge proof; execute only after a native slot is free.",
    "Freeze and review3tray5job legal-message gates and strong baselines; keep in-flight unknown guards, no hidden future completion evidence.",
    "Freeze current sources for unified zero-skip regression and register all successes/failures; no commit/push."
]
state["next_actions"] = next_actions
active = state["active_experiment"]
active["pending"] = next_actions
active["full024_status"] = "Both new resumed attempts launched.1x originalH54000 seal verified after269parts/130906updates,842.8983s reconstruction, now continuing.2x reconstructing originalH28800. Original processes absent and costs/partial outputs retained. No full-day completion claim yet."
active["native026_sha256"] = "c7eab9d81e3e930a3e7f2f3a320b4c92b1c1c2e5a0c07db9c4050b536d821943"
active["native026_status"] = "Standalone allocation/TTL/backward-time tests,12focused,20legacy branches and actual known024H54000+next500 ordered reference/indexed/full-view/final-seal gate passed. One concurrent pair15.404048->8.196101s is not stable speed or100ms certification. Originalnextshard had no finalnative seal."
active["installed_operation_status"] = "Native001 completed7cases/9roots;8closed,1intentional missingACK unknown. Independent review found small setup bookkeeping gaps and requires separate initialized-service/diagnostic/full-process accounting. Original business100ms not certified."
active["native022_status"] = "16runtime and021/off022/on022 parity passed. Retained/stream5000 actualpair passed11 independent orderedraw/phase/finalseal checks; complete100ms unproven."
active["original_waiting_gate"] = "Original negative occupancy cascade independently reconstructed; current-source waiting112to113 executability gate in preparation, no actual new route execution."
state["execution_status"] = "Local LT2 research actively continuing after explicit user resume. Two full-day024 attempts active;026 accepted separately. Overall research incomplete; no new commit/push."
backup.write_bytes(before)
dump(STATE, state)
dump(report_path, {"schema": "g31.resume_milestone.v1", "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "previous_state_sha256": sha(backup), "new_state_sha256": sha(STATE),
    "observed_artifacts": {str(p.relative_to(ROOT)): sha(p) for p in (gate_path, one_path, two_path, probe_path)},
    "scope": "One observed milestone; running receipts may later change. No full-day/business100ms/joint success claimed.",
    "native026_status": gate["status"], "one_reconstruction_status": one["status"],
    "two_receipt_status_at_observation": two["status"], "finite_probe_receipt": probe})
print(json.dumps({"state_updated": True, "milestone_sha256": sha(report_path)}))
