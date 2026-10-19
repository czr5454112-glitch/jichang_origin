"""Post-hoc finite-table information audit; no online solver or native execution.

The restricted team chooses both initial actions at the saved checkpoint,
without a regime label, later signaling, or outcome queries. This is deliberately
narrower than a causal controller that can wait and communicate.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
from types import SimpleNamespace

from .local_context import LocalContextToken, protocol_projection
from .original_workload import digest, write_json
from . import research_synthetic_reuse_chain as study


SCHEMA = "g31.lt2.reuse_information_audit.v1"
CELL_KEYS = {f"route{r}_window{w}" for r in (1, 2) for w in range(4)}
REGIMES = ("0.0", "6.0", "12.0")
JOBS = {"loaded", "receiver", "reuse1", "reuse2"}


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_causal_times(view: dict) -> None:
    """Observed facts cannot arrive from the future; public future gates can."""
    def finite_time(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("invalid_observed_time")
        return value

    def job_times(job, observed):
        if not 0 <= finite_time(job["arrival"]) <= observed:
            raise ValueError("unobserved_future_job")
        for key in ("loaded_at", "storage_entered_at", "storage_released_at", "completed_at"):
            if key in job and finite_time(job[key]) > observed:
                raise ValueError("future_physical_job_fact")

    now = finite_time(view["now"])
    for job in view.get("jobs", []):
        job_times(job, now)
    for message in view.get("delivered_messages", []):
        observed, delivered = finite_time(message["observed_at"]), finite_time(message["delivered_at"])
        if not 0 <= observed <= delivered <= now:
            raise ValueError("future_or_inverted_message_capture")
        for job in message.get("jobs", []):
            job_times(job, observed)
    for key in ("delivered_transfer_acks", "delivered_command_acks"):
        for ack in view.get(key, []):
            observed, delivered = finite_time(ack["observed_at"]), finite_time(ack["delivered_at"])
            if not 0 <= observed <= delivered <= now:
                raise ValueError("future_or_inverted_ack_capture")
            for field in ("executed_at", "completed_at", "captured_demand_observed_at"):
                if field in ack and finite_time(ack[field]) > observed:
                    raise ValueError("future_ack_fact")


def contract() -> dict:
    return {"decision_time": study.START, "route_actions": [1, 2], "window_actions": [0, 1, 2, 3],
        "departure_windows": list(study.departure_windows(study.scene(0.))),
        "public_receiver_load_seconds": study.PUBLIC_RECEIVER_LOAD,
        "protocol": study.protocol(),
        "policy_class": "deterministic one-shot A route=f(A input), B window=g(B input)",
        "information": "full saved owner view, own predecision request history, identical public contract and clock",
        "regime_label_available_to_policy": False,
        "additional_private_memory": "none; identical initialization and the saved seed history only",
        "incumbent": "route1_window1 separately in each regime",
        "protection": "every offered completion delta <= 0 in every regime, no positive tolerance",
        "objective": "unweighted sum of all four completions over all three regimes; report each regime too",
        "objective_is_expected_population_performance": False,
        "study_design": "post-hoc diagnostic of existing evidence, not a preregistered new experiment",
        "continuation": "the common archived continuation still communicates; only initial action selection is one-shot",
        "excluded": ["additional messaging or waiting before selecting initial actions", "signaling by executed initial actions", "shared randomness",
                     "external regime labels", "richer action domains", "unrecorded private histories"]}


def assess(regimes: dict) -> dict:
    """Enumerate every deterministic mapping on the supplied information classes.

    Complete and physically reassessed inputs are required. Hashes are only
    display identifiers: equality classes use canonical contents, not hashes.
    """
    result = {"schema": SCHEMA, "status": "unknown", "contract": contract(),
        "best_team_policy": None, "full_information_reference": None,
        "team_minus_full_information_seconds": None, "new_solver_novelty": False,
        "general_decentralized_impossibility": False}
    try:
        if set(regimes) != set(REGIMES):
            raise ValueError("incomplete_regime_domain")
        observations = {o: {} for o in ("A", "B")}
        completions = {}
        protected = {}
        for gate in REGIMES:
            row = regimes[gate]
            if set(row["cells"]) != CELL_KEYS:
                raise ValueError("incomplete_action_domain")
            for owner in observations:
                inp = row["inputs"][owner]
                view = inp["view"]
                if view["owner_id"] != owner or view["now"] != study.START:
                    raise ValueError("invalid_owner_or_decision_time")
                protocol_projection(view)  # rejects future/wrong-owner messages
                validate_causal_times(view)
                if inp["public_contract"] != contract():
                    raise ValueError("unequal_public_contract")
                for call in inp["own_predecision_calls"]:
                    if (call["request"]["owner_id"] != owner or isinstance(call["at"], bool)
                            or not 0 <= call["at"] < study.START):
                        raise ValueError("invalid_predecision_history")
                observations[owner][gate] = canonical(inp)
            completions[gate] = {}
            for key, cell in row["cells"].items():
                if cell["status"] != "assessed" or cell["audit"]["status"] != "passed":
                    raise ValueError("unknown_or_unaudited_cell")
                times = cell["completion"]
                if set(times) != JOBS or any(isinstance(t, bool) or not isinstance(t, (int, float))
                        or not math.isfinite(t) or not 0 <= t <= study.HORIZON for t in times.values()):
                    raise ValueError("invalid_business_denominator_or_time")
                if cell["completion_sum"] != sum(times.values()):
                    raise ValueError("inconsistent_completion_sum")
                completions[gate][key] = times
            incumbent = completions[gate]["route1_window1"]
            protected[gate] = {key: all(times[j] <= incumbent[j] for j in JOBS)
                               for key, times in completions[gate].items()}
        # Insertion order follows the declared regimes, independent of measured costs.
        classes = {o: list(dict.fromkeys(observations[o].values())) for o in observations}
        indices = {o: {g: classes[o].index(observations[o][g]) for g in REGIMES} for o in observations}
        policies = []
        for routes in itertools.product((1, 2), repeat=len(classes["A"])):
            for windows in itertools.product(range(4), repeat=len(classes["B"])):
                actions = {g: f"route{routes[indices['A'][g]]}_window{windows[indices['B'][g]]}" for g in REGIMES}
                costs = {g: sum(completions[g][actions[g]].values()) for g in REGIMES}
                deltas = {g: {j: completions[g][actions[g]][j] - completions[g]["route1_window1"][j]
                             for j in sorted(JOBS)} for g in REGIMES}
                policies.append({"A_routes_by_class": list(routes), "B_windows_by_class": list(windows),
                    "actions": actions, "cost_by_regime": costs, "completion_sum": sum(costs.values()),
                    "per_job_delta_vs_incumbent": deltas,
                    "protected_in_every_regime": all(protected[g][actions[g]] for g in REGIMES)})
        eligible = [p for p in policies if p["protected_in_every_regime"]]
        best = min(eligible, key=lambda p: (p["completion_sum"], p["A_routes_by_class"], p["B_windows_by_class"]))
        oracle_actions = {g: min((k for k in CELL_KEYS if protected[g][k]),
                                key=lambda k: (sum(completions[g][k].values()), k)) for g in REGIMES}
        oracle_costs = {g: sum(completions[g][oracle_actions[g]].values()) for g in REGIMES}
        oracle = {"actions": oracle_actions, "cost_by_regime": oracle_costs,
                  "completion_sum": sum(oracle_costs.values()), "online_implementability": "not_claimed"}
        witness = {}
        for owner in observations:
            witness[owner] = {"class_count": len(classes[owner]), "class_by_regime": indices[owner],
                "inputs_sha256": {g: sha(regimes[g]["inputs"][owner]) for g in REGIMES},
                "raw_view_sha256": {g: sha(regimes[g]["inputs"][owner]["view"]) for g in REGIMES},
                "token_sha256": {g: LocalContextToken.from_observation(regimes[g]["inputs"][owner]["view"]).identity for g in REGIMES},
                "full_input_contents_equal_across_regimes": len(classes[owner]) == 1}
        result.update(status="assessed", observation_partition=witness, policies=policies,
            enumerated_policy_count=len(policies), protected_policy_count=len(eligible), best_team_policy=best,
            full_information_reference=oracle,
            team_minus_full_information_seconds=best["completion_sum"] - oracle["completion_sum"],
            conclusion_scope="necessary information consistency for this finite one-shot table only")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        result["reason"] = str(exc)
    return result


def read_evidence(directory: Path) -> tuple[dict, dict]:
    """Reassess raw native evidence and pin every input against the saved receipt."""
    assessment_path = directory / "independent_assessment.json"
    old = json.loads(assessment_path.read_text(encoding="utf-8"))
    if old["status"] != "passed":
        raise ValueError("prior_assessment_not_passed")
    if digest(Path(study.__file__)) != old["current_assessor_sha256"]:
        raise ValueError("assessor_identity_changed")
    evidence = {"independent_assessment.json": digest(assessment_path)}
    for name, expected in old["evidence_sha256"].items():
        path = directory / name
        if digest(path) != expected:
            raise ValueError("evidence_hash_changed:" + name)
        evidence[name] = expected
    rows = {}
    for gate in REGIMES:
        folder = directory / f"gate{int(float(gate))}"
        data = json.loads((folder / "input.json").read_text(encoding="utf-8"))
        if canonical(data) != canonical(study.scene(float(gate))):
            raise ValueError("scene_changed")
        cells, inputs, checkpoint = {}, None, None
        for route, window in itertools.product((1, 2), range(4)):
            key = f"route{route}_window{window}"
            with gzip.open(folder / f"{key}.json.gz", "rt", encoding="utf-8") as stream:
                raw = json.load(stream)
            own_inputs = {o: {"view": raw["seed_views"][o], "public_contract": contract(),
                "own_predecision_calls": [c for c in raw["calls"] if c["at"] < study.START and c["request"]["owner_id"] == o]}
                for o in ("A", "B")}
            if inputs is None:
                inputs, checkpoint = own_inputs, raw["checkpoint_identity"]
            if inputs != own_inputs or checkpoint != raw["checkpoint_identity"]:
                raise ValueError("unequal_branch_seed")
            cell = study.assess_cell(data, raw["result"], SimpleNamespace(rows=raw["outbox"], calls=raw["calls"]), raw["continuation"], route)
            if cell != raw["summary"]:
                raise ValueError("raw_reassessment_mismatch")
            cells[key] = cell
        if study.assess_regime(copy.deepcopy(cells)) != old["regimes"][gate]:
            raise ValueError("prior_reassessment_mismatch")
        rows[gate] = {"inputs": inputs, "cells": cells}
    return rows, evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = {str(p): digest(p) for p in [Path(__file__), Path(study.__file__), Path(__file__).with_name("local_context.py")]}
    write_json(args.output / "audit_contract.json", contract())
    rows, evidence = read_evidence(args.evidence)
    report = assess(rows)
    report.update(evidence_root=str(args.evidence.resolve()), evidence_sha256=evidence,
        source_sha256=source, additional_native_branches=0)
    if any(digest(Path(p)) != h for p, h in source.items()):
        report["status"] = "invalidated_source_changed"
    write_json(args.output / "receipt.json", report)
    (args.output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps({k: report.get(k) for k in ("status", "enumerated_policy_count", "protected_policy_count",
        "team_minus_full_information_seconds", "best_team_policy", "full_information_reference")}, indent=2))
    return 0 if report["status"] == "assessed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
