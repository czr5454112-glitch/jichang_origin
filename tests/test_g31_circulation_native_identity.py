"""Real extension-cache identity tests, isolated from the pytest host process."""
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
BINARIES = {
    "011": (ROOT / "build_lt_session_011/python/czr005_circulation.cp311-win_amd64.pyd",
            "19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec", 4., False),
    "015": (ROOT / "build_lt_session_015/python/czr005_circulation.cp311-win_amd64.pyd",
            "5919ed48a86aed8302f1c9a813574c161feac93600f998e89e5cdfd385bbc098", 2., True),
}

# Each invocation starts a new interpreter. The parent never imports either
# native module, so collection order cannot determine which DLL is exercised.
CHILD = r'''
import hashlib, json, sys
from pathlib import Path
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle, prepare_input
mode, first = sys.argv[1:3]
module = load_native(first)
report = {"actual": str(Path(module.__file__).resolve()),
          "actual_sha256": hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
          "has_owner_notifications": hasattr(module.NativeSession, "owner_notifications")}
if mode == "repeat":
    again = load_native(first)
    report["same_class"] = again.NativeSession is module.NativeSession
    report["same_artifact"] = Path(again.__file__).resolve() == Path(first).resolve()
elif mode == "switch":
    try:
        load_native(sys.argv[3])
    except ImportError as exc:
        report["rejected"] = True
        report["error"] = str(exc)
    else:
        report["rejected"] = False
else:
    data = tiny_cycle()
    data["jobs"] = [dict(data["jobs"][0], load_seconds=0.)]
    data["transfers"] = []
    data["node_records"] = [(n,k,2. if n==0 else t,x,y,e) for n,k,t,x,y,e in data["node_records"]]
    next(n for n in data["node_contracts"] if n["node"] == 1)["resource_owner"] = "B"
    data["owner_protocol"] = dict(enabled=True, timeout=5., ack_delay=.2)
    session = module.NativeSession(prepare_input(data))
    session.advance_to(0.)
    request = dict(request_id="live:1:A:identity", owner_id="A", kind="service_forecast",
        target_owner="B", tray_id="T0", next=1, message_delay=2., publication_delay=.5)
    session.submit_protocol_command(request)
    session.advance_to(2.8)
    ack = session.protocol_command("A", request["request_id"])["last_delivered_ack"]
    message = next(m for m in session.observe_protocol("B")["delivered_messages"] if m["message_id"] == ack["result_id"])
    result = session.result_at(4.)
    report["forecast_entry_estimate"] = message["entry_estimate"]
    report["actual_first_entry"] = next(r["time"] for r in result["receipts"] if r["event"] == "EDGE_ENTER")
    report["ack_status"] = ack["status"]
print(json.dumps(report))
'''


def child(mode, first, second=None):
    binaries = [BINARIES[first][0]] + ([BINARIES[second][0]] if second else [])
    assert all(path.is_file() for path in binaries), "identity regression requires the pinned native011/native015 artifacts"
    result = subprocess.run([sys.executable, "-c", CHILD, mode, *(str(p) for p in binaries)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_repeated_loading_of_identical_artifact_is_supported():
    result = child("repeat", "015")
    assert result["same_class"] and result["same_artifact"]
    assert result["actual_sha256"] == BINARIES["015"][1]


@pytest.mark.parametrize("first,second", [("015", "011"), ("011", "015")])
def test_cached_native_version_switch_is_rejected_in_both_directions(first, second):
    result = child("switch", first, second)
    assert result["rejected"], result
    assert "native_host:binary_identity_mismatch" in result["error"]
    assert "use a fresh process" in result["error"]
    assert str(BINARIES[first][0]) in result["error"]
    assert str(BINARIES[second][0]) in result["error"]


@pytest.mark.parametrize("version", ["011", "015"])
def test_fresh_process_uses_actual_requested_historical_behavior(version):
    path, expected_sha, expected_estimate, supports_notifications = BINARIES[version]
    result = child("fresh", version)
    assert Path(result["actual"]) == path
    assert result["actual_sha256"] == expected_sha
    assert result["has_owner_notifications"] == supports_notifications
    assert result["ack_status"] == "delivered"
    assert result["forecast_entry_estimate"] == expected_estimate
    assert result["actual_first_entry"] == 2.
