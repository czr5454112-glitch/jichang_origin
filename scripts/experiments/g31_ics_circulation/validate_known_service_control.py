"""Same-information known-service factor on the synthetic coupled graph.

This is a separate physical/information contract from coupled_native_002:
B2 actually arrives at .5 and loads for 5.8 seconds. Its service forecast is
published from that observed native loading state with real message delay.
Point windows are a conventional strong baseline, never hard future grants.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import traceback

from .analytic_control import run_online_matching, transfer_candidates
from .finite_reference import Intervention, enumerate_interventions, headroom, outcome_cost, service_dominates
from .native_host import audit_result, load_native, prepare_input
from .validate_analytic_control import replay_input, write
from .validate_coupled_control import coupled_input


def known_service_input():
    data = coupled_input(source_min_stock=1)
    second = next(j for j in data["jobs"] if j["business_bag_id"] == "B2")
    second.update(arrival=.5, load_seconds=5.8)
    data["model_scope"] = "synthetic coupled graph; separate observed B2 loading contract factor; not original airport map"
    return prepare_input(data)


def prefix(native, data, *, predictive=False, windows=False, horizon=1.6):
    session = native.NativeSession(data)
    session.advance_to(.11)
    first = run_online_matching(session, ["A", "B", "C"], horizon=.61, predictive=predictive,
        message_delay=1., demand_delay=.2, respect_service_forecasts=windows)
    source = session.observe("A")
    tray = next(t for t in source["trays"] if t["business_bag_id"] == "B2")
    assert tray["mode"] == "loading", tray
    reply = session.publish_service_forecast("A", "B", tray["tray_id"], 1, .2)
    assert reply["status"] not in ("rejected", "timeout_unknown"), reply
    assert not any(m.get("kind") == "service_forecast" for m in session.observe("B")["delivered_messages"])
    second = run_online_matching(session, ["A", "B", "C"], horizon=horizon, predictive=predictive,
        message_delay=1., demand_delay=.2, respect_service_forecasts=windows,
        controller_state=first["controller_state"])
    observed = session.observe("B")
    forecasts = [m for m in observed["delivered_messages"] if m.get("kind") == "service_forecast"]
    assert len(forecasts) == 1 and forecasts[0]["business_bag_id"] == "B2", forecasts
    assert abs(forecasts[0]["entry_estimate"] - 6.35) < 1e-8, forecasts
    assert abs(forecasts[0]["release_estimate"] - 7.4) < 1e-8, forecasts
    second["submitted"] = first["submitted"] + second["submitted"]
    second["control_records"] = first["control_records"] + second["control_records"]
    second["forecast_publication"] = {"source_observation": source, "reply": reply, "delivered": forecasts}
    return session, second


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), Path(__file__).with_name("analytic_control.py"),
             Path(__file__).with_name("finite_reference.py"), Path(__file__).with_name("validate_coupled_control.py"),
             Path(__file__).with_name("native_host.py")]
    source_before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    receipt = {"schema": "g31.known_service_control.v1", "status": "running", "cases": {},
        "source_before": source_before, "binary_sha256": hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(),
        "scope": "synthetic separate known-demand contract factor; same observations for all policies; no original-map claim",
        "novelty": "not_established; ordinary public point-window baseline",
        "normal_service_scope": "post-run per-job paired check under one common future; no universal guarantee"}
    write(args.output / "receipt.json", receipt)
    data = known_service_input()
    write(args.output / "input.json", data)
    try:
        native = load_native(args.binary)
        for policy, predictive, windows in (("reactive", False, False), ("predictive", True, False),
                                             ("predictive_public_windows", True, True)):
            folder = args.output / policy
            folder.mkdir()
            session, pre = prefix(native, data, predictive=predictive, windows=windows)
            run = run_online_matching(session, ["A", "B", "C"], horizon=40, predictive=predictive,
                message_delay=1., demand_delay=.2, respect_service_forecasts=windows,
                controller_state=pre["controller_state"])
            run["submitted"] = pre["submitted"] + run["submitted"]
            run["control_records"] = pre["control_records"] + run["control_records"]
            run["forecast_publication"] = pre["forecast_publication"]
            write(folder / "raw.json", run)
            assert run["status"] == "reached", run["status"]
            replay = replay_input(data, run["submitted"])
            audit = audit_result(replay, run["result"])
            write(folder / "replay_input.json", replay)
            write(folder / "audit.json", audit)
            metrics = outcome_cost(run["result"], data["jobs"], 40)
            receipt["cases"][policy] = {"metrics": metrics, "requests": run["submitted"], "audit": audit}
            write(args.output / "receipt.json", receipt)
        for case in receipt["cases"].values():
            case["service_preserved_vs_reactive"] = service_dominates(case["metrics"], receipt["cases"]["reactive"]["metrics"])

        # The finite domain is declared from a public observation. Common real
        # future is used only offline to evaluate the genuine native forks.
        session, pre = prefix(native, data)
        observation = session.observe("B")
        point = transfer_candidates(observation, predictive=True, message_delay=1., request_prefix="finite-point")
        window = transfer_candidates(observation, predictive=True, message_delay=1., respect_service_forecasts=True,
                                     request_prefix="finite-window")
        assert len(point["intents"]) == len(window["intents"]) == 1
        immediate, safe = point["intents"][0], window["intents"][0]
        actions = [Intervention("WAIT", "wait"), Intervention("point", "transfer", immediate),
                   Intervention("public-window", "transfer", safe)]
        # Offsets relative to the observed estimate are declared, not fitted to
        # any result. Equal/negative/protected-harming outcomes are retained.
        for offset in (-1., -.5, -.25, .25, .5, 1., 2.):
            request = dict(safe, request_id=safe["request_id"] + f":offset:{offset}",
                           earliest_departure=max(observation["now"], safe["earliest_departure"] + offset))
            actions.append(Intervention(f"window-offset-{offset}", "transfer", request))
        write(args.output / "finite_public_domain.json", {"observation": observation, "point": point,
            "public_window": window, "actions": [{"action_id": a.action_id, "kind": a.kind, "request": a.request} for a in actions]})
        parent_before = session.offline_state_sha256()

        def continuation(branch, horizon):
            follow = run_online_matching(branch, ["A", "B", "C"], horizon=horizon, predictive=False,
                message_delay=1., demand_delay=.2, controller_state=copy.deepcopy(pre["controller_state"]))
            result = follow["result"]
            result["offline_continuation_submitted"] = follow["submitted"]
            return result

        def validate(result, action):
            submissions = pre["submitted"] + result["offline_continuation_submitted"]
            if action.kind == "transfer":
                submissions = submissions + [{"request": action.request, "reply": {"status": "pending"}}]
            return audit_result(replay_input(data, submissions), result)

        reference = enumerate_interventions(session, actions, horizon=40, job_contracts=data["jobs"],
            baseline_action_id="WAIT", max_seconds=60, continuation=continuation, validate=validate)
        write(args.output / "finite_reference.json", reference)
        assert session.offline_state_sha256() == parent_before, "fork_changed_parent"
        receipt["finite_reference"] = {k: v for k, v in reference.items() if k != "rows"}
        receipt["headroom"] = headroom(reference, ["point", "public-window"], "public-window", "public-window")
        receipt["finite_candidates"] = [{k: v for k, v in row.items() if k not in ("result", "audit")}
                                         for row in reference["rows"]]
        receipt["status"] = "passed"  # records service failures separately; no forced improvement assertion
    except Exception:
        receipt["status"] = "failed"
        receipt["traceback"] = traceback.format_exc()
        raise
    finally:
        receipt["source_after"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        receipt["source_changed"] = [p for p in source_before if source_before[p] != receipt["source_after"][p]]
        write(args.output / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "headroom": receipt.get("headroom"),
        "policies": {k: {"cost": v["metrics"]["cost"], "service_preserved": v["service_preserved_vs_reactive"]}
                     for k, v in receipt["cases"].items()}}))


if __name__ == "__main__":
    main()
