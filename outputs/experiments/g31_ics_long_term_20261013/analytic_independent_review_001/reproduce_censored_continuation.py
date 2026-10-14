from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).absolute().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle, audit_result
from scripts.experiments.g31_ics_circulation.analytic_control import run_online_matching
from scripts.experiments.g31_ics_circulation.finite_reference import Intervention, enumerate_interventions

binary = ROOT / "build_lt_session_005/python/czr005_circulation.cp311-win_amd64.pyd"
native = load_native(binary)
data = tiny_cycle()
data["transfers"] = []
data["options"]["max_events"] = 5
source = native.NativeSession(data)
outer = []

def continuation(branch, horizon):
    run = run_online_matching(branch, ["A", "B"], horizon=horizon, predictive=False, publish=False)
    outer.append({"status": run["status"], "result_horizon": run["result"]["horizon"],
                  "result_advance": run["result"]["advance"],
                  "event_count": run["result"]["native_summary"]["event_count"]})
    return run["result"]

reference = enumerate_interventions(source,
    [Intervention("WAIT", "wait"), Intervention("other-wait", "wait")],
    horizon=20, job_contracts=data["jobs"], continuation=continuation,
    validate=lambda result, action: audit_result(data, result))
receipt = {"schema": "g31.independent.censored_continuation_probe.v1", "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
           "input": data, "requested_horizon": 20, "continuation": outer,
           "reference": reference,
           "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                             [ROOT / "scripts/experiments/g31_ics_circulation/analytic_control.py",
                              ROOT / "scripts/experiments/g31_ics_circulation/finite_reference.py"]}}
Path(__file__).with_name("censored_continuation_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps({"outer": outer, "exhaustive": reference["exhaustive"], "optimality": reference["optimality"],
                  "row_statuses": [r["status"] for r in reference["rows"]]}, indent=2))
