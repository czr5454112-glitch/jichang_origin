"""Actual native forecast revision/withdrawal; prediction is not a tray grant."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import traceback

from .analytic_control import conditional_service_windows, run_online_matching
from .native_host import audit_result, load_native
from .validate_analytic_control import replay_input, write
from .validate_known_service_control import known_service_input, prefix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    files = [Path(__file__), Path(__file__).with_name("analytic_control.py"),
             Path(__file__).with_name("validate_known_service_control.py")]
    snap = lambda: {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    receipt = {"status": "running", "schema": "g31.native_forecast_lifecycle.v1", "source_before": snap(),
               "binary_sha256": hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(), "cases": [],
               "scope": "synthetic correctness/conditional-message baseline; no innovation or universal service guarantee"}
    try:
        native = load_native(args.binary)
        data = known_service_input()
        write(args.output/"input.json", data)
        session = native.NativeSession(data); session.advance_to(.61)
        original = session.publish_service_forecast("A", "B", "T1", 1, 2.)
        withdrawal = session.withdraw_service_forecast("A", original["message_id"], .1)
        duplicate = session.withdraw_service_forecast("A", original["message_id"], .1)
        assert duplicate["status"] == "duplicate", duplicate
        before = session.observe("B")
        assert conditional_service_windows(before) == []
        session.advance_to(.8)
        early = session.observe("B")
        assert len(early["delivered_messages"]) == 1 and early["delivered_messages"][0]["status"] == "withdrawn"
        assert conditional_service_windows(early) == []
        checkpoint = session.fork()
        for branch in (session, checkpoint):
            branch.advance_to(2.7)
            assert conditional_service_windows(branch.observe("B")) == []
        assert session.offline_state_sha256() == checkpoint.offline_state_sha256()
        write(args.output/"overtaking_withdrawal.json", {"original": original, "withdrawal": withdrawal,
            "duplicate": duplicate, "before": before, "withdrawal_arrived_first": early, "both_delivered": session.observe("B")})
        receipt["cases"].append({"name": "withdrawal_overtakes_original_and_survives_fork", "status": "passed"})

        # Same-clock announcements are ordered by source-target publication
        # sequence; receiver delivery order is deliberately reversed.
        session = native.NativeSession(data); session.advance_to(6.31)
        old = session.publish_service_forecast("A", "B", "T1", 1, .5)
        tray = next(t for t in session.observe("A")["trays"] if t["tray_id"] == "T1")
        route = {"request_id": "forecast-revision-route", "owner_id": "A", "business_bag_id": "B2",
                 "tray_id": "T1", "from": 0, "next": 2, "expected_generation": tray["generation"],
                 "expected_traversal": tray["traversal_id"], "expiry": 7., "message_delay": 0.}
        route_reply = session.submit_route_intent(route); session.advance_to(6.31)
        assert session.observe("A")["route_requests"][-1]["status"] == "updated"
        revised = session.publish_service_forecast("A", "B", "T1", 2, .1)
        withdrawal = session.withdraw_service_forecast("A", old["message_id"], .05)
        session.advance_to(6.9)
        final = session.observe("B")
        windows = conditional_service_windows(final)
        assert len(windows) == 1 and windows[0]["message_id"] == revised["message_id"] and windows[0]["next"] == 2
        result = session.result_at(7.)
        first_hop = next(r["to"] for r in result["receipts"] if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == "B2")
        assert first_hop == 2
        write(args.output/"same_clock_revision.json", {"old": old, "revised": revised, "withdrawal": withdrawal,
            "route_reply": route_reply, "observation": final, "windows": windows, "result": result,
            "audit": audit_result(data, result)})
        receipt["cases"].append({"name": "same_clock_route_revision_late_old_tombstone", "status": "passed"})

        session, pre = prefix(native, data, predictive=True, windows=True)
        mid = run_online_matching(session, ["A", "B", "C"], horizon=7., predictive=True, message_delay=1.,
            demand_delay=.2, respect_service_forecasts=True, controller_state=pre["controller_state"])
        submissions = pre["submitted"] + mid["submitted"]
        state = mid["controller_state"]
        transfer = next(t for t in mid["result"]["transfers"] if t["status"] == "departed")
        baseline = session.fork()
        original_id = pre["forecast_publication"]["delivered"][0]["message_id"]
        withdrawal = session.withdraw_service_forecast("A", original_id, 0.)
        refusal = session.cancel_transfer_intent(transfer["request_id"], "B")
        assert refusal["status"] == "rejected" and refusal["reason"] == "already_committed", refusal
        run = run_online_matching(session, ["A", "B", "C"], horizon=40., predictive=True, message_delay=1.,
            demand_delay=.2, respect_service_forecasts=True, controller_state=copy.deepcopy(state))
        unchanged = run_online_matching(baseline, ["A", "B", "C"], horizon=40., predictive=True, message_delay=1.,
            demand_delay=.2, respect_service_forecasts=True, controller_state=copy.deepcopy(state))
        assert run["result"]["jobs"] == unchanged["result"]["jobs"]
        assert run["result"]["trays"] == unchanged["result"]["trays"]
        assert next(t for t in run["result"]["transfers"] if t["request_id"] == transfer["request_id"])["status"] == "received"
        assert conditional_service_windows(session.observe("B")) == []
        write(args.output/"withdrawal_is_not_physical_cancellation.json", {"withdrawal": withdrawal,
            "cancel_refusal": refusal, "before_transfer": transfer, "result": run["result"], "baseline_result": unchanged["result"],
            "audit": audit_result(replay_input(data, submissions+run["submitted"]), run["result"])})
        receipt["cases"].append({"name": "withdrawal_keeps_departed_tray_and_forbids_transfer_cancel", "status": "passed"})
        receipt["status"] = "passed"
    except Exception:
        receipt["status"] = "failed"; receipt["traceback"] = traceback.format_exc()
    finally:
        receipt["source_after"] = snap()
        receipt["source_changed"] = [p for p,v in receipt["source_before"].items() if receipt["source_after"][p] != v]
        write(args.output/"receipt.json", receipt)
    print(json.dumps(receipt))
    return int(receipt["status"] != "passed" or bool(receipt["source_changed"]))


if __name__ == "__main__":
    raise SystemExit(main())
