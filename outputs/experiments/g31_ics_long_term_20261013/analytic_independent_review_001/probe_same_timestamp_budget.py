import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).absolute().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle

binary = ROOT / "build_lt_session_005/python/czr005_circulation.cp311-win_amd64.pyd"
native = load_native(binary)
data = tiny_cycle()
data["transfers"] = []
a = native.NativeSession(data)
a.advance_to(0)
first = a.advance_to(.1, 1)
unfinished = a.offline_state_sha256()
remaining = a.advance_to(.1, 10000)
receipt = {"schema": "g31.independent.same_timestamp_budget_probe.v1",
           "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "input": data,
           "first_advance": first, "followup_at_same_horizon": remaining,
           "state_changed_after_followup": unfinished != a.offline_state_sha256()}
Path(__file__).with_name("same_timestamp_budget_before_002.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps({k:v for k,v in receipt.items() if k!="input"}, indent=2))
