"""Independent saved-event/FIFO review; no new native execution."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from . import research_original_low_wip as base


def reference(path):
    return {"path": str(Path(path).resolve()), "sha256": base.sha(path)}


def review(directory):
    directory = Path(directory)
    receipt = base.read(directory / "receipt.json")
    assert receipt["status"] == "worker_finished" and receipt["exit_code"] == 0 and not receipt["source_changed"]
    assert receipt["wall_seconds"] < 600
    verified = base.verify_saved(directory)
    raw = base.gzread(directory / "raw_final.json.gz")
    data = base.gzread(directory / "input.json.gz")
    plan = base.read(directory / "preregistered_protocol.json")
    source_path = base.OUT / "full_stream_native024_001/full1x/input.json.gz"
    assert base.sha(source_path) == plan["input_sha256"] == base.INPUT_SHA
    source = base.gzread(source_path)
    assert base.canonical(data) == base.canonical(source)
    assert len(data["jobs"]) == len(raw["result"]["jobs"]) == 28506
    assert [j["business_bag_id"] for j in data["jobs"]] == [j["business_bag_id"] for j in raw["result"]["jobs"]]
    assert sum(bool(j.get("allow_suffix_reroute", False)) for j in data["jobs"]) == 0
    result = raw["result"]
    assert raw["physical_time"] == result["horizon"] == result["physical_clock"] == 22200.
    assert result["advance"]["horizon_complete"] is True
    supplies = [o["supply"] for o in raw["owners"] if o["supply"]]
    assert len(supplies) == 1
    supply = supplies[0]
    chosen = supply["choice"]["job"]
    job_id, token = chosen["business_bag_id"], plan["parking_plan"]["token_tray_id"]
    jobs = {j["business_bag_id"]: j for j in data["jobs"]}
    contract = jobs[job_id]
    events = [r for r in result["receipts"] if r["business_bag_id"] == job_id and r["tray_id"] == token]
    named = {name: [r for r in events if r["event"] == name] for name in
             ("LOAD_START", "LOAD_COMPLETE", "STORAGE_ENTER", "STORAGE_RELEASE", "UNLOAD_COMPLETE", "HOLD_COMPLETE")}
    assert all(len(v) == 1 for v in named.values())
    named = {k: v[0] for k, v in named.items()}
    assert [named[k]["time"] for k in named] == sorted(named[k]["time"] for k in named)
    assert named["LOAD_START"]["node"] == contract["origin"]
    assert named["STORAGE_ENTER"]["node"] == named["STORAGE_RELEASE"]["node"] == contract["storage_node"]
    assert named["STORAGE_RELEASE"]["time"] >= max(contract["storage_release_at"], named["STORAGE_ENTER"]["time"] + contract["storage_min_dwell"])
    assert named["UNLOAD_COMPLETE"]["node"] == named["HOLD_COMPLETE"]["node"] == contract["destination"]
    assert named["HOLD_COMPLETE"]["time"] - named["UNLOAD_COMPLETE"]["time"] == contract["hold_seconds"]
    loaded = [r for r in result["receipts"] if r["event"] == "LOAD_START"]
    assert loaded == [named["LOAD_START"]]
    eligible = [j for j in data["jobs"] if j["origin"] == contract["origin"] and j["arrival"] <= named["LOAD_START"]["time"]]
    head = min(eligible, key=lambda j: (j["arrival"], j["business_bag_id"]))
    assert head["business_bag_id"] == job_id
    capture = supply["choice"]["delivered_message"]
    local = capture["capture"]["local_capture"]
    peer_heads = {}
    for job in sorted(local["jobs"], key=lambda j: (j["arrival"], j["business_bag_id"])):
        if job["status"] == "waiting_for_tray":
            peer_heads.setdefault(job["origin"], job)
    assert peer_heads[contract["origin"]]["business_bag_id"] == job_id
    assert contract["arrival"] <= local["captured_at"] <= capture["delivered_at"] <= supply["at"] < named["LOAD_START"]["time"]
    physical = [r for o in raw["owners"] for r in o["outbox"]["outbox"].values() if r["kind"] == "transfer"]
    assert len(physical) == 23 and all(r["client_view"]["last_delivered_ack"]["status"] == "received" for r in physical)
    terminal = [t for t in result["trays"] if t["tray_id"] == token]
    assert len(terminal) == 1 and terminal[0]["mode"] == "empty" and terminal[0]["job"] == terminal[0]["edge_to"] == -1
    assert terminal[0]["node"] == contract["destination"] and terminal[0]["available_at"] == named["HOLD_COMPLETE"]["time"]
    assert verified["assessment"]["status"] == "observed_complete_and_empty"
    assert result["population"]["offered_by_horizon"] == sum(j["arrival"] <= 22200. for j in data["jobs"]) == 3998
    pins = {name: reference(directory / name) for name in
            ("receipt.json", "preregistered_protocol.json", "raw_final.json.gz", "assessment.json", "independent_verification.json", "input.json.gz", "api/manifest.jsonl")}
    return {
        "schema": "g31.original_low_wip_independent_saved_review.v1", "status": "passed_actual_single_completion_review",
        "created_utc": datetime.now(timezone.utc).isoformat(), "reviewer_source": reference(__file__),
        "existing_verifier_source": reference(base.__file__), "evidence": pins, "original_input": reference(source_path),
        "rederived_saved_verification": verified, "input_jobs_retained": 28506, "jobs_arrived_by_gate_horizon": 3998,
        "r1_authorized_jobs": 0, "physical_request_count": 23, "completed_parking_count": 22,
        "supply": {k: supply[k] for k in ("request_id", "request", "at")}, "business_contract": contract,
        "source_capture": {"source_owner": local["source_owner"], "captured_at": local["captured_at"], "delivered_at": capture["delivered_at"]},
        "delivered_peer_fifo_heads": [{"origin": n, "job": j["business_bag_id"], "arrival": j["arrival"]} for n, j in peer_heads.items()],
        "actual_input_fifo_head_at_load": job_id, "actual_named_events": named,
        "final_token": terminal[0], "business_status_counts": dict(Counter(j["status"] for j in result["jobs"])),
        "physical_audit": raw["physical_audit"], "reviewer_native_executions": 0,
        "limits": [
            "One declared original business completes and returns its carrier empty; no second reuse is demonstrated.",
            "All28506 input jobs remain, but only3998 arrived byH22200; this is not a full-day completion result.",
            "Within-source FIFO is preserved. Choosing among different source heads does not authorize skipping an unreachable head within a source.",
            "No paired all-offered strict protection, total improvement, deadlock freedom or complete-request100ms proof.",
            "Native state seal is read from saved output; this review runs no new NativeSession or seal reconstruction.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review(args.directory)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": reference(args.output), "status": result["status"]}))


if __name__ == "__main__":
    main()
