"""Prespecified original-map R1 -> release -> R2 -> same-tray reuse diagnostic.

Enumerate every next hop at the first post-Storage public choice for the first
three statically round-trip eligible original jobs at the earliest loader.
The continuation is the existing event R2 policy with further R1 updates off.
Thus this can establish one-way causal propagation, never bidirectional joint
optimization. Reactive and predictive R2 have identical physical permissions.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import sys
import time
import traceback

from .event_protocol_control import run_event_protocol_control
from .native_host import audit_result, load_native
from .original_mechanism import select_input
from .original_workload import digest, json_digest, research_r1_authorized, write_json
from .research_r1 import branch_request, find_context
from .validate_protocol_control import replay_input


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--expected-binary-sha256", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    modules = ["research_r1_reuse.py", "research_r1.py", "original_workload.py", "original_mechanism.py",
               "event_protocol_control.py", "protocol_control.py", "analytic_control.py", "native_host.py",
               "regional_control.py", "validate_protocol_control.py"]
    paths = [Path(__file__).with_name(name) for name in modules]
    receipt = {"status": "running", "command": sys.argv,
               "source_before": {str(path): digest(path) for path in paths}, "branches": {}}
    # Source archives make this continuation inspectable after adjacent W1 edits.
    archive = args.output / "source_archive"
    archive.mkdir()
    for path in paths:
        (archive / path.name).write_bytes(path.read_bytes())
    write_json(args.output / "receipt.json", receipt)
    try:
        receipt["binary_sha256"] = digest(args.binary)
        if receipt["binary_sha256"] != args.expected_binary_sha256:
            raise ValueError("research_r1_reuse:binary_identity_mismatch")
        original, selection, lineage = select_input(3)
        data, contract = research_r1_authorized(original)
        data["owner_protocol"] = {"enabled": True, "timeout": 5., "ack_delay": .2}
        data["owner_notifications"] = {"enabled": True}
        write_json(args.output / "input.json", data)
        write_json(args.output / "selection.json", selection)
        write_json(args.output / "contract.json", contract)
        write_json(args.output / "preregistered_protocol.json", {
            "selection": "select_input(3), unchanged original source records; first actual post-Storage choice using legal owner notifications",
            "actions": "control and every positive-capacity simple public next-hop suffix",
            "R2": ["reactive", "predictive"], "further_R1_updates": False,
            "continuation": "event protocol controller, period60/command2/publication0.5/retry60/lease120",
            "route_command_delay": .01, "horizon": 86400.,
            "normal_protection": "zero per-job regression against same R2 control; all violations retained",
            "claim": "one-way causal propagation diagnostic, not full bidirectional coupling"})
        native = load_native(args.binary)
        parent = native.NativeSession(data)
        owners = sorted({n["resource_owner"] for n in data["node_contracts"]})
        context, status = find_context(parent, owners, 86400., stage_filter="post_storage_or_direct")
        if context is None:
            raise ValueError(status)
        write_json(args.output / "context.json", context)
        receipt["checkpoint_identity"] = parent.offline_state_sha256()
        for predictive in [False, True]:
            policy = "predictive" if predictive else "reactive"
            for action, path in [("control", None)] + [(f"next_{x[1]}", x) for x in context["paths"]]:
                label = policy + "_" + action
                branch = parent.fork()
                request = None
                if path is not None:
                    request, encoded = branch_request(context, path, message_delay=.01, expiry=120.)
                    response = branch.submit_protocol_command(request)
                started = time.perf_counter()
                run = run_event_protocol_control(branch, owners, horizon=86400., control_period=60.,
                    command_delay=2., publication_delay=.5, retry_period=60., routes=False,
                    forecasts=predictive, prebalance=True, predictive=predictive, lease_seconds=120.,
                    max_activations=20000)
                with gzip.open(args.output / f"{label}_raw.json.gz", "wt", encoding="utf-8") as stream:
                    json.dump(run, stream, allow_nan=False)
                result = run["result"]
                row = {"status": run["status"], "wall_seconds": time.perf_counter() - started,
                       "R1_request": request, "continuation_sha256": json_digest(run["controller_state"]["config"])}
                if result is None:
                    row["outcome"] = "unknown_continuation_budget"
                else:
                    row["audit"] = audit_result(replay_input(data, run["client_calls"]), result)
                    row["jobs"] = result["jobs"]
                    row["completed"] = sum(j["completed_at"] >= 0 for j in result["jobs"])
                    row["R1_ack"] = (branch.protocol_command(request["owner_id"], request["request_id"]).get("last_delivered_ack")
                                       if request else None)
                    events = [r for r in result["receipts"] if r["event"] in
                              {"UNLOAD_COMPLETE", "HOLD_COMPLETE", "EXPORT_GRANTED", "EMPTY_RECEIVED", "LOAD_START"}]
                    row["causal_lifecycle"] = events
                    row["empty_edges"] = [r for r in result["receipts"] if r["event"] == "EDGE_ENTER" and not r["business_bag_id"]]
                    row["received_transfers"] = sum(r["event"] == "EMPTY_RECEIVED" for r in result["receipts"])
                    row["early_transfer_submissions"] = []
                    releases = [r["time"] for r in events if r["event"] == "HOLD_COMPLETE"]
                    grants = {r["reason"]: r for r in events if r["event"] == "EXPORT_GRANTED"}
                    for call in run["client_calls"]:
                        if call["kind"] == "transfer" and not call["retry"] and call["request"]["request_id"] in grants:
                            grant = grants[call["request"]["request_id"]]
                            release = max((t for t in releases if t <= grant["time"]), default=None)
                            if release is not None and call["at"] < release:
                                row["early_transfer_submissions"].append({"request_id": call["request"]["request_id"],
                                    "issued_at": call["at"], "empty_released_at": release,
                                    "granted_at": grant["time"], "lead_seconds": release - call["at"]})
                receipt["branches"][label] = row
                write_json(args.output / "receipt.json", receipt)
        for label, row in receipt["branches"].items():
            control = receipt["branches"][label.split("_")[0] + "_control"]
            if "jobs" in row and "jobs" in control:
                row["completion_delta_vs_same_R2_control"] = {
                    j["business_bag_id"]: j["completed_at"] - c["completed_at"]
                    for j, c in zip(row["jobs"], control["jobs"], strict=True)
                    if j["completed_at"] >= 0 and c["completed_at"] >= 0}
                row["normal_protection_passed"] = (len(row["completion_delta_vs_same_R2_control"]) == len(data["jobs"])
                    and all(v <= 0 for v in row["completion_delta_vs_same_R2_control"].values()))
        receipt["status"] = "executed"
    except Exception:
        receipt["status"] = "failed"
        receipt["exception"] = traceback.format_exc()
    receipt["source_changed"] = [str(path) for path in paths if digest(path) != receipt["source_before"][str(path)]]
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    receipt["bidirectional_joint_status"] = "unknown; further R1 updates deliberately disabled"
    receipt["complete_100ms_requirement_certified"] = False
    write_json(args.output / "receipt.json", receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k != "branches"}, indent=2))
    return int(receipt["status"] == "failed" or bool(receipt["source_changed"]))


if __name__ == "__main__":
    raise SystemExit(main())
