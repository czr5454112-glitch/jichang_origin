"""Read saved K4/K12 evidence, revalidate proposals; never run simulation."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.ics_circulation_v3 import model
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, actual_action_key, COST_WEIGHTS


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def candidate(value):
    return model.RouteCandidate(**{**value, "legs": tuple(model.Leg(**r) for r in value["legs"])})


def forecast(value):
    return model.ConditionalRouteForecast(**{**value,
        "witness_legs": tuple(model.Leg(**r) for r in value["witness_legs"]),
        "remaining_legs": tuple(model.Leg(**r) for r in value["remaining_legs"]),
        "dependencies": tuple(model.ForecastDependency(**r) for r in value["dependencies"])})


def snapshot(value):
    return model.Snapshot(**{**value,
        "network": model.Network({k: model.Node(**v) for k, v in value["network"]["nodes"].items()},
                                 {k: model.Edge(**v) for k, v in value["network"]["edges"].items()}),
        "trays": {k: model.Tray(**v) for k, v in value["trays"].items()},
        "bags": {k: model.Bag(**v) for k, v in value["bags"].items()},
        "reservations": tuple(model.Reservation(**v) for v in value["reservations"]),
        "old_in_transit": tuple(model.InFlight(**v) for v in value["old_in_transit"]),
        "module": model.FixedLocalModule(**value["module"]),
        "plans": {k: candidate(v) for k, v in value["plans"].items()},
        "conditional_forecasts": {k: forecast(v) for k, v in value["conditional_forecasts"].items()},
        "forecast_history": tuple(forecast(v) for v in value["forecast_history"]),
        "replaceable_trays": tuple(value["replaceable_trays"])})


def main():
    base = ROOT / "outputs/experiments/ics_circulation_v3"
    old = base / "phase4_w3_role_coverage_20261009"
    current = base / "phase4_w3_role_candidate_coverage_repaired_20261009"
    failed = base / "phase4_w3_role_candidate_coverage_20261009"
    summary, prior, protocol = read(current / "summary.json"), read(old / "summary.json"), read(current / "protocol.json")
    checks, artifacts, details = [], {}, []
    def check(name, condition, **context):
        checks.append({"name": name, "passed": bool(condition), **context})
    def take(path):
        artifacts[path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
        return read(path)
    for folder in (old, current):
        take(folder / "summary.json")
    take(current / "protocol.json")
    failure = take(failed / "failure.json")
    check("old_failed_attempt_retained_zero_branches", failure["branch_count"] == failure["completed_states"] == 0
          and failure["status"] == "failed_before_any_label_branch")
    check("four_declared_cells_and_no_branch_failures", summary["planned_states"] == summary["completed_states"] == 4
          and not summary["failures"] and summary["source_changed_during_run"] is False)
    for name, expected in protocol["source_sha256"].items():
        archived = sha256((current / "source_snapshot" / name).read_bytes()).hexdigest()
        live = sha256((ROOT / "scripts/experiments/ics_circulation_v3" / name).read_bytes()).hexdigest()
        check("recorded_dependency_matches_snapshot_and_current", archived == live == expected, file=name)
    for name, expected in summary["input_sha256"].items():
        check("original_input_hash_matches", sha256((old / name).read_bytes()).hexdigest() == expected, file=name)
    total = 0
    for row in summary["rows"]:
        record = next(r for r in prior["samples"] if r["identity"] == row["identity"])
        original, normal = take(old / record["sample_file"]), take(old / record["stress_file"])
        expanded = take(current / (row["scene"] + "_sample.json"))
        labels = take(current / (row["scene"] + "_labels.json"))
        indices = [expanded["normal_keys"].index(k) for k in original["normal_keys"]]
        # Reconstruct only the original view of this saved expanded artifact.
        # Expanded options are an explicit intervention-domain extension; no
        # state, cost, period, module, clock or cursor position is relaxed.
        projection = {k: deepcopy(expanded[k]) for k in original}
        projection["normal_keys"] = expanded["actual_normal_keys"]
        projection["proposals"] = [expanded["proposals"][i] for i in indices]
        projection["features"] = [expanded["features"][i] for i in indices]
        projection["features_physical"] = [expanded["features_physical"][i] for i in indices]
        projection["checkpoint_metadata"]["cursor"]["pending_options"] = expanded["cursor"]["pending_options"]
        ignored = {"checkpoint_sha256", "search_work"}
        mismatch = [k for k in original if k not in ignored and original[k] != projection[k]]
        check("all_saved_original_decision_fields_equal", not mismatch, scene=row["scene"], different_fields=mismatch)
        check("expanded_cursor_changed_only_pending_option_set",
            {k: v for k, v in expanded["checkpoint_metadata"]["cursor"].items() if k != "pending_options"}
            == {k: v for k, v in original["checkpoint_metadata"]["cursor"].items() if k != "pending_options"}, scene=row["scene"])
        check("candidate_keys_unique_and_normal_order_retained", len(set(expanded["normal_keys"])) == len(expanded["normal_keys"])
              and expanded["actual_normal_keys"] == original["normal_keys"], scene=row["scene"])
        state = snapshot(expanded["state"])
        check("state_decode_lossless", json.loads(json.dumps(asdict(state))) == expanded["state"], scene=row["scene"])
        actions, prefixes, rejected = [], [], []
        for index, raw in enumerate(expanded["proposals"]):
            proposal = candidate(raw)
            verdict = ExecutionValidator().validate(state, proposal, route_mode="next_edge")
            if not verdict.accepted:
                rejected.append({"index": index, "reason": verdict.reason})
            actions.append(actual_action_key(state, proposal, route_mode="next_edge"))
            prefix = ExecutionValidator._safe_prefix(state, proposal)
            end = state.network.edges[prefix.legs[-1].edge_id].target if prefix.legs else state.trays[prefix.tray_id].node
            prefixes.append(digest({"tray": prefix.tray_id, "bag": prefix.bag_id, "legs": [asdict(l) for l in prefix.legs],
                "end": end, "unload_complete": prefix.unload_complete, "usable_at": prefix.usable_at, "prefix_only": prefix.prefix_only}))
        check("every_expanded_witness_passes_same_physical_owner", not rejected, scene=row["scene"], rejected=rejected)
        check("actual_action_keys_recomputed_exactly", actions == labels["actual_action_keys"] == expanded["normal_keys"], scene=row["scene"])
        check("all_32_common_future_tapes_equal_R0", labels["future_groups_offline_only"] == normal["future_groups_offline_only"], scene=row["scene"])
        same_costs = all(labels["paired_costs"][g][i] == normal["paired_costs"][g][j]
                         for g in range(4) for j, i in enumerate(indices))
        check("every_normal_cost_exactly_reproduced", same_costs, scene=row["scene"], scalar_comparisons=128)
        counts = {(b["group"], b["candidate"], b["future_index"]) for b in labels["raw_branches"]}
        expected = {(g, c, f) for g in range(4) for c in range(len(actions)) for f in range(8)}
        check("complete_unique_branch_denominator", counts == expected and len(counts) == len(labels["raw_branches"]), scene=row["scene"])
        raw_valid = all(not b["failed"] and b["future_sha256"] == digest(labels["future_groups_offline_only"][b["group"]]["tapes"][b["future_index"]])
                        and abs(sum(COST_WEIGHTS[k] * v for k, v in b["cost_components"].items()) - b["total_cost"]) < 1e-9
                        and b["total_cost"] == labels["paired_costs"][b["group"]][b["candidate"]][b["future_index"]]
                        for b in labels["raw_branches"])
        check("raw_branch_cost_components_and_tapes_valid", raw_valid, scene=row["scene"])
        by_index = {(b["group"], b["candidate"], b["future_index"]): b for b in labels["raw_branches"]}
        fields = ("future_sha256", "total_cost", "cost_components", "completed", "uncompleted", "invariant_checks", "failed")
        outcomes_equal = all(all(b[k] == by_index[b["group"], indices[b["candidate"]], b["future_index"]][k] for k in fields)
                             for b in normal["raw_branches"])
        check("all_normal_recorded_physical_outcomes_equal", outcomes_equal, scene=row["scene"])
        vectors = [tuple(labels["paired_costs"][g][i][f] for g in range(4) for f in range(8)) for i in range(len(actions))]
        means = [sum(v) / len(v) for v in vectors]
        details.append({"scene": row["scene"], "normal_actions": len(indices), "expanded_actions": len(actions),
            "normal_immediate_prefixes": len({prefixes[i] for i in indices}), "expanded_immediate_prefixes": len(set(prefixes)),
            "normal_exact_32_cost_vector_classes": len({vectors[i] for i in indices}),
            "expanded_exact_32_cost_vector_classes": len(set(vectors)), "all_means_tie": max(means) - min(means) <= 1e-12,
            "physical_prefix_keys": prefixes, "checkpoint_audit_id_matches": normal["checkpoint_sha256"] == expanded["actual_decision_checkpoint_sha256"],
            "branch_count": len(labels["raw_branches"]), "bounded_pool_coverage_loss": min(means[i] for i in indices) - min(means)})
        total += len(labels["raw_branches"])
    check("total_1344_recorded_branches", total == summary["branch_count"] == 1344)
    result = {"scope": "independent saved-artifact equality and owner revalidation; zero simulation calls",
        "checks": len(checks), "passed": sum(c["passed"] for c in checks), "failed": [c for c in checks if not c["passed"]],
        "rows": details, "check_results": checks, "input_sha256": artifacts,
        "hash_limit": "checkpoint_fingerprint serializes generator._started and cache/work diagnostics, not just semantic state; unequal cross-run hashes do not establish different physical decisions. This audit checks saved physical/control evidence plus all 32 normal branch costs/outcomes, not unsaved private engine state identity or unenumerated futures.",
        "scope_limit": "Four first B-origin development cells, bounded K12 pool, fixed timed continuation. Value-vector equality does not imply identical immediate actions or global value equivalence."}
    target = Path(__file__).with_name("candidate_coverage_audit.json")
    with target.open("x", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write("\n")
    print(json.dumps({k: result[k] for k in ("checks", "passed", "failed", "rows")}, ensure_ascii=False))
    return int(bool(result["failed"]))


if __name__ == "__main__":
    raise SystemExit(main())
