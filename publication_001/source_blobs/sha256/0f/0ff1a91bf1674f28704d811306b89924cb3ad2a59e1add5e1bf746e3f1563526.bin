"""Execute and archive the first G31 circulation acceptance campaign.

python -m scripts.experiments.g31_ics_circulation.validate_native_cycle \
  --binary build_g31_circulation/python/czr005_circulation.cp311-win_amd64.pyd \
  --output outputs/experiments/g31_ics_circulation_20261013/native_acceptance_001
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback

from .native_host import audit_result, load_native, tiny_cycle


def scenarios():
    base = tiny_cycle()
    yield "same_tray_two_services", base
    s = deepcopy(base)
    s["transfers"] = []
    yield "no_return_control", s
    s = deepcopy(base)
    s["jobs"][0]["storage_release_at"] = 20
    yield "delayed_storage", s
    s = deepcopy(base)
    s["node_contracts"][4]["export_min_stock"] = 1
    yield "source_protection_refusal", s
    s = deepcopy(base)
    s["node_contracts"][0]["allow_receive"] = False
    yield "destination_module_refusal", s
    s = deepcopy(base)
    s["transfers"][0].update(message_delay=60, expiry=30)
    yield "late_expired_message", s
    s = deepcopy(base)
    s["trays"].append({"tray_id": "parked-storage", "node": 2})
    s["options"].update(max_simulation_time=15, max_decisions_per_bag=32)
    yield "storage_receiving_full", s
    s = deepcopy(base)
    s["trays"].append({"tray_id": "reserve-at-source", "node": 5})
    s["node_contracts"][5]["zone"] = "B"
    s["jobs"][1]["arrival"] = 25
    s["transfers"].append({"request_id": "occupy-receiving", "tray_id": "reserve-at-source",
                           "source": 5, "destination": 0, "issued_at": 1.0,
                           "message_delay": 0.0, "earliest_departure": 1.0, "expiry": 5.0})
    yield "empty_receiving_full", s
    s = deepcopy(base)
    s["transfers"][0]["expiry"] = 11
    s["faults"] = [{"from": 4, "to": 5, "start": 0.0, "end": 30.0,
                     "message_delay": 4.0}]
    s["options"]["max_simulation_time"] = 40
    yield "fault_before_departure_lease", s
    s = deepcopy(base)
    for e in s["edge_contracts"]:
        if e["from"] == 0:
            e["entry_headway"] = 30.0
    # Both outbound choices have long tail windows; use a single outbound edge
    # to make the same-edge repeated-entry condition unavoidable in this witness.
    s["edge_records"] = [e for e in s["edge_records"] if e[:2] != (0, 6)]
    s["edge_contracts"] = [e for e in s["edge_contracts"] if (e["from"], e["to"]) != (0, 6)]
    s["node_records"][0] = (0, 1, 0.05, 0, 0, [1])
    from .native_host import prepare_input
    yield "headway_survives_unload_and_return", prepare_input(s)
    for control in (False, True):
        s = deepcopy(base)
        s["trays"].append({"tray_id": "T1", "node": 0})
        # Same finite physical model for the two members of this comparison.
        for n in s["node_contracts"]:
            n["capacity"] = 2
        s["jobs"][1]["storage_release_at"] = 6
        s["jobs"][1]["unload_seconds"] = 0.5
        if control:
            s["transfers"] = []
        yield "sufficient_trays_no_return" if control else "sufficient_trays_with_return", s
    s = deepcopy(base)
    s["options"]["scorer_mode"] = "S3_shortest_potential_only"
    yield "same_model_S3_reference", s


def check_campaign(rows):
    r = rows["same_tray_two_services"]
    assert all(j["status"] == "completed" and j["deadline_met"] for j in r["jobs"])
    assert {j["tray"] for j in r["jobs"]} == {0}
    assert r["jobs"][1]["loaded_at"] >= r["transfers"][0]["received_at"] > r["jobs"][0]["completed_at"]
    assert any(d["scorer_effective_id"].startswith("S4") for d in r["decisions"])
    assert len(r["leg_identities"]) == 5
    assert len({e["traversal_id"] for e in r["receipts"] if e["event"] == "EDGE_ENTER"}) == 10
    assert rows["no_return_control"]["jobs"][1]["loaded_at"] < 0
    assert rows["no_return_control"]["trays"][0]["node"] == 4
    assert rows["delayed_storage"]["jobs"][1]["loaded_at"] > r["jobs"][1]["loaded_at"] + 13.9
    for name, reason in (("source_protection_refusal", "source_module_min_stock"),
                         ("destination_module_refusal", "destination_module_refused"),
                         ("empty_receiving_full", "receiving_full"),
                         ("late_expired_message", "departure_lease_expired")):
        assert rows[name]["transfers"][0]["status"] == "rejected", name
        assert rows[name]["transfers"][0]["reason"] == reason, name
    full = rows["storage_receiving_full"]
    assert full["jobs"][0]["completed_at"] < 0
    assert full["jobs"][0]["storage_entered_at"] < 0
    assert full["trays"][1]["node"] == 2
    failure = rows["fault_before_departure_lease"]
    assert failure["transfers"][0]["status"] == "failed"
    assert failure["transfers"][0]["departed_at"] < 0
    assert failure["trays"][0]["node"] == 4
    assert failure["trays"][0]["mode"] == "quarantined"
    assert failure["trays"][0]["reception_node"] == -1
    assert not any(e["event"] == "EDGE_ENTER" and e["from"] == 4 for e in failure["receipts"])
    tail = rows["headway_survives_unload_and_return"]
    entries = [e["time"] for e in tail["receipts"] if e["event"] == "EDGE_ENTER" and e["from"] == 0]
    assert len(entries) == 2 and entries[1] >= entries[0] + 30 - 1e-8
    assert all(j["status"] == "completed" for j in tail["jobs"])
    no_benefit = [[j["completed_at"] for j in rows[key]["jobs"]]
                  for key in ("sufficient_trays_no_return", "sufficient_trays_with_return")]
    assert all(t >= 0 for t in no_benefit[0] + no_benefit[1])
    assert no_benefit[0] == no_benefit[1]
    assert all(j["status"] == "completed" for j in rows["same_model_S3_reference"]["jobs"])
    return {"status": "passed", "scenario_count": len(rows),
            "same_tray_two_service_completion": [j["completed_at"] for j in r["jobs"]],
            "no_benefit_completion_times": no_benefit[0],
            "same_model_reference": "S3 feasible executed witness; optimality unknown",
            "method_claim": "engineering_only; no predictive controller or learning claim"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    receipt = {"command": sys.argv, "python": sys.version, "platform": platform.platform(),
               "binary": str(args.binary.absolute()), "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
               "status": "running", "scenarios": []}
    source_paths = [Path("cpp/ics_core/runtime/event_driven_junction.hpp"),
                    Path("cpp/ics_core/runtime/circulation.hpp"),
                    Path("cpp/ics_core/runtime/circulation_runtime_impl.hpp"),
                    Path("cpp/ics_core/bindings/circulation.cpp"),
                    Path(__file__), Path(__file__).with_name("native_host.py")]
    receipt["source_sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    start = time.perf_counter()
    try:
        native = load_native(args.binary)
        rows = {}
        for name, data in scenarios():
            case_dir = out / name
            case_dir.mkdir()
            (case_dir / "input.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            result = native.run(data)
            (case_dir / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
            audit = audit_result(data, result)
            (case_dir / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
            (case_dir / "events.jsonl").write_text("".join(json.dumps(e)+"\n" for e in result["receipts"]), encoding="utf-8")
            receipt["scenarios"].append({"name": name, "audit": audit})
            rows[name] = result
        receipt["acceptance"] = check_campaign(rows)
        receipt["status"] = "passed"
    except Exception:
        receipt["status"] = "failed"
        receipt["exception"] = traceback.format_exc()
    receipt["wall_seconds"] = time.perf_counter() - start
    receipt["source_changed"] = [str(p) for p in source_paths if hashlib.sha256(p.read_bytes()).hexdigest() != receipt["source_sha256"][str(p)]]
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt.get("acceptance", receipt), indent=2))
    return 0 if receipt["status"] == "passed" and not receipt["source_changed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
