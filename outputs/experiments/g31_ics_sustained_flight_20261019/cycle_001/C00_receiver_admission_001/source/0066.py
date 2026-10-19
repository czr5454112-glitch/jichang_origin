"""Executed R2 baseline and finite-reference campaign; native physics only."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

from .analytic_control import run_online_matching, transfer_candidates
from .finite_reference import Intervention, enumerate_interventions, headroom, outcome_cost, service_dominates
from .native_host import audit_result, load_native, prepare_input, tiny_cycle


def write(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def replay_input(data, submitted):
    replay = copy.deepcopy(data)
    replay["transfers"] = [dict(r["request"]) for r in submitted
                           if r["reply"].get("status") not in ("rejected", "timeout_unknown", "failed_no_safe_continuation")]
    return replay


def scenarios():
    original = tiny_cycle()
    original["transfers"] = []
    result = {"command_delay_2": (original, 2.0, .5)}
    zero = copy.deepcopy(original)
    result["zero_delay"] = zero, 0.0, 0.0
    delayed = copy.deepcopy(original)
    delayed["jobs"][0]["storage_release_at"] = 20
    result["storage_delay_20"] = delayed, 2.0, .5
    stock = copy.deepcopy(original)
    stock["node_contracts"][4]["export_min_stock"] = 1
    result["source_reserve_refusal"] = stock, 2.0, .5
    deny = copy.deepcopy(original)
    deny["node_contracts"][0]["allow_receive"] = False
    result["receiver_refusal"] = deny, 2.0, .5
    future = copy.deepcopy(original)
    future["jobs"][1]["arrival"] = 25
    result["unpublished_future_demand"] = future, 2.0, .5
    plentiful = copy.deepcopy(original)
    plentiful["node_contracts"][0]["capacity"] = 2
    plentiful["trays"].append({"tray_id": "T1", "node": 0})
    result["two_trays_terminal_pressure"] = plentiful, 2.0, .5
    spare = copy.deepcopy(plentiful)
    spare["node_contracts"][4]["capacity"] = 2
    result["two_trays_spare_terminal_no_benefit"] = spare, 2.0, .5
    long = copy.deepcopy(original)
    long["edge_records"] = [(u, v, 10 if (u, v) == (4, 5) else length, speed)
                            for u, v, length, speed in long["edge_records"]]
    result["longer_return_research_factor"] = prepare_input(long), 2.0, .5
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    files = [Path(__file__), Path(__file__).with_name("analytic_control.py"),
             Path(__file__).with_name("finite_reference.py"),
             Path(__file__).with_name("native_host.py")]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    receipt = {"schema": "g31.analytic_native_campaign.v1", "status": "running", "cases": [],
               "source_before": before, "binary_sha256": hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(),
               "information": "owner projection plus delayed observed-demand snapshots; no input transfers",
               "research_scope": "synthetic mechanism development; not original-map confirmation",
               "acceptance_scope": "independent native physical replay and full-population paired service; no main-method or 100ms claim"}
    write(args.output / "receipt.json", receipt)
    started = time.perf_counter()
    try:
        native = load_native(args.binary)
        for name, (data, delay, demand_delay) in scenarios().items():
            folder = args.output / name
            folder.mkdir()
            write(folder / "input.json", data)
            metrics = {}
            for predictive in (False, True):
                policy = "predictive" if predictive else "reactive"
                run = run_online_matching(native.NativeSession(data), ["A", "B"], horizon=80,
                                          predictive=predictive, message_delay=delay, demand_delay=demand_delay)
                # Independent replay uses requests actually produced at runtime,
                # not a hand-written successful return schedule.
                replay = replay_input(data, run["submitted"])
                write(folder / f"{policy}_raw.json", run)
                write(folder / f"{policy}_replay_input.json", replay)
                if run["status"] != "reached":
                    raise RuntimeError(f"{name}/{policy}:native_event_budget_exhausted")
                audit = audit_result(replay, run["result"])
                value = outcome_cost(run["result"], data["jobs"], 80)
                write(folder / f"{policy}_audit.json", audit)
                write(folder / f"{policy}_metrics.json", value)
                if name == "unpublished_future_demand":
                    assert all(r["request"]["issued_at"] >= data["jobs"][1]["arrival"]
                               for r in run["submitted"])
                metrics[policy] = value
            row = {"case": name, "metrics": metrics,
                   "cost_difference_predictive_minus_reactive": metrics["predictive"]["cost"] - metrics["reactive"]["cost"],
                   "paired_service_preserved": service_dominates(metrics["predictive"], metrics["reactive"])}
            receipt["cases"].append(row)
            assert row["paired_service_preserved"], (name, "paired service regression")
            if name == "two_trays_spare_terminal_no_benefit":
                assert metrics["reactive"]["completed"] == metrics["predictive"]["completed"] == 2
                assert abs(row["cost_difference_predictive_minus_reactive"]) < 1e-8
            write(args.output / "receipt.json", receipt)
        # Actual common checkpoint, no prewritten transfers; one intervention.
        data = scenarios()["command_delay_2"][0]
        # Native state alone is insufficient for controller continuation: the
        # publication cache and periodic phase are checkpointed separately as
        # trusted JSON, and each sibling receives a deep copy.
        parent = native.NativeSession(data)
        prefix = run_online_matching(parent, ["A", "B"], horizon=8, predictive=True,
                                     message_delay=2, demand_delay=.5)
        saved = json.loads(json.dumps(prefix["controller_state"]))
        parent_identity = parent.offline_state_sha256()
        siblings = [run_online_matching(parent.fork(), ["A", "B"], horizon=80, predictive=True,
                                        message_delay=2, demand_delay=.5, controller_state=copy.deepcopy(saved))
                    for _ in range(2)]
        uninterrupted = json.loads((args.output / "command_delay_2" / "predictive_raw.json").read_text(encoding="utf-8"))
        compared = ["receipts", "jobs", "trays", "transfers", "leg_identities"]
        for key in compared:
            assert siblings[0]["result"][key] == siblings[1]["result"][key] == uninterrupted["result"][key], key
        assert parent.offline_state_sha256() == parent_identity
        write(args.output / "controller_continuation.json", {
            "status": "passed", "checkpoint_time": 8, "controller_state": saved,
            "parent_state_unchanged": True, "equal_fields": compared,
            "sibling_controller_states_equal": siblings[0]["controller_state"] == siblings[1]["controller_state"],
            "scope": "one real pending-message boundary; native fork plus JSON controller state; no duplicate current control tick"})
        session = native.NativeSession(data)
        session.advance_to(.5)
        session.publish_demand("A", "B", .5)
        session.advance_to(8.0)
        public = session.observe("B")
        proposed = transfer_candidates(public, predictive=True, message_delay=2)
        actions = [Intervention("WAIT", "wait")]
        for i, request in enumerate(proposed["intents"]):
            actions.append(Intervention(f"transfer-{i}", "transfer", request))
            later = dict(request, request_id=request["request_id"] + ":later", earliest_departure=15)
            actions.append(Intervention(f"transfer-later-{i}", "transfer", later))

        def validate(result, action):
            replay = copy.deepcopy(data)
            if action.kind == "transfer":
                replay["transfers"].append(action.request)
            return audit_result(replay, result)

        strong_baseline = "transfer-0" if len(actions) > 1 else "WAIT"
        reference = enumerate_interventions(session, actions, horizon=80, job_contracts=data["jobs"],
                                            baseline_action_id=strong_baseline, validate=validate)
        write(args.output / "reference_observation.json", public)
        best = reference["best_action_id"]
        write(args.output / "headroom.json", headroom(reference, [a.action_id for a in actions], best, strong_baseline))
        reference["strong_baseline_action_id"] = strong_baseline
        wait_cost = next(r["metrics"]["cost"] for r in reference["rows"] if r["action"]["action_id"] == "WAIT")
        reference["wait_control_gap_only"] = wait_cost - reference["best_cost"]
        write(args.output / "finite_reference.json", reference)
        # Actual pending -> rejection must not masquerade as an executed WAIT
        # alternative. Also keep a request unresolved beyond H as unknown.
        blocked_data = copy.deepcopy(data)
        blocked_data["node_contracts"][4]["export_min_stock"] = 1
        blocked = native.NativeSession(blocked_data)
        blocked.advance_to(8)
        denied_request = dict(proposed["intents"][0], request_id="live:reference-source-reserve",
                              expected_version=blocked.observe("B")["version"])

        def blocked_validate(result, action):
            replay = copy.deepcopy(blocked_data)
            if action.kind == "transfer":
                replay["transfers"].append(action.request)
            return audit_result(replay, result)

        denied = enumerate_interventions(blocked, [Intervention("WAIT", "wait"),
            Intervention("source-reserve", "transfer", denied_request)], horizon=80,
            job_contracts=blocked_data["jobs"], validate=blocked_validate)
        denied_row = next(r for r in denied["rows"] if r["action"]["action_id"] == "source-reserve")
        assert denied_row["reply"]["status"] == "pending"
        assert denied_row["status"] == "asynchronous_rejected"
        assert denied_row["execution_resolution"]["reason"] == "source_module_min_stock"
        write(args.output / "finite_async_rejection.json", denied)
        late_request = dict(proposed["intents"][0], request_id="live:reference-outside-horizon",
                            earliest_departure=100, expiry=150)
        unresolved = enumerate_interventions(session, [Intervention("WAIT", "wait"),
            Intervention("after-horizon", "transfer", late_request)], horizon=80,
            job_contracts=data["jobs"], validate=validate)
        assert unresolved["optimality"] == "unknown" and not unresolved["exhaustive"]
        assert any(r["status"] == "unresolved_at_horizon" for r in unresolved["rows"])
        write(args.output / "finite_unresolved.json", unresolved)
        # Preserve the independently discovered prefix/result wrapper bug as
        # an actual native regression, not only a status-only unit test.
        censored_data = tiny_cycle()
        censored_data["transfers"] = []
        censored_data["options"]["max_events"] = 5
        censored_source = native.NativeSession(censored_data)
        def censored_continue(branch, horizon):
            return run_online_matching(branch, ["A", "B"], horizon=horizon, predictive=False,
                                       publish=False)["result"]
        censored_reference = enumerate_interventions(censored_source,
            [Intervention("WAIT", "wait"), Intervention("second", "wait")], horizon=20,
            job_contracts=censored_data["jobs"], continuation=censored_continue,
            validate=lambda result, action: audit_result(censored_data, result))
        assert not censored_reference["exhaustive"] and censored_reference["optimality"] == "unknown"
        assert all(row["status"] == "incomplete_horizon" and "metrics" not in row
                   for row in censored_reference["rows"])
        write(args.output/"finite_censored_continuation.json", censored_reference)
        receipt["finite_reference"] = {key: value for key, value in reference.items() if key != "rows"}
        receipt["status"] = "passed"
    except Exception:
        receipt["status"] = "failed"
        receipt["traceback"] = traceback.format_exc()
        raise
    finally:
        receipt["source_after"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        receipt["source_changed"] = [p for p in before if before[p] != receipt["source_after"][p]]
        receipt["elapsed_seconds"] = time.perf_counter() - started
        write(args.output / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "cases": len(receipt["cases"]),
                      "reference": receipt["finite_reference"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
