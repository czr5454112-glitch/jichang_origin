"""Read frozen network label evidence; no new simulator or learning calls."""
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.ics_circulation_v3 import model
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, actual_action_key, assert_invariants, COST_WEIGHTS


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def checksum(path):
    return sha256(path.read_bytes()).hexdigest()


def candidate(value):
    return model.RouteCandidate(**{**value, "legs": tuple(model.Leg(**v) for v in value["legs"])})


def forecast(value):
    return model.ConditionalRouteForecast(**{**value,
        "witness_legs": tuple(model.Leg(**v) for v in value["witness_legs"]),
        "remaining_legs": tuple(model.Leg(**v) for v in value["remaining_legs"]),
        "dependencies": tuple(model.ForecastDependency(**v) for v in value["dependencies"])})


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
    folder = base / "phase4_w3_network_role_labels_parallel_20261009"
    pilot = base / "phase4_w3_network_role_pilot_20261009"
    output = Path(__file__).with_name("audit.json")
    if output.exists():
        raise ValueError("audit result already exists")
    summary, protocol, manifest = (read(folder / name) for name in ("summary.json", "protocol.json", "manifest.json"))
    checks, classes, failures = [], [], []
    def check(name, good, **context):
        checks.append({"check": name, "passed": bool(good), **context})
    check("parent_frozen_summary_and_protocol", checksum(folder / "summary.json") == manifest["summary_sha256"]
          and checksum(folder / "protocol.json") == manifest["protocol_sha256"])
    check("all_three_worker_outcomes_received", summary["scene_count_planned"] == summary["scene_summaries_received"] == 3
          and not summary["worker_failures"] and summary["complete_resource_accounting"])
    for name, expected in protocol["source_sha256"].items():
        check("source_snapshot_current_and_protocol_equal", checksum(folder / "source_snapshot" / name)
              == checksum(ROOT / "scripts/experiments/ics_circulation_v3" / name) == expected, file=name)
    pilot_summary = read(pilot / "summary.json")
    requested = actual = reused = omitted = samples = empty = 0
    cache_files = {}
    for scene in protocol["workloads"]:
        local = folder / scene
        own_summary, own_protocol, own_manifest = (read(local / name) for name in ("summary.json", "protocol.json", "manifest.json"))
        check("worker_manifest_hash_matches_parent", checksum(local / "manifest.json") == manifest["scene_manifest_sha256"][scene], scene=scene)
        file_set = {p.relative_to(local).as_posix() for p in local.rglob("*") if p.is_file()}
        check("worker_exact_frozen_file_set", file_set == set(own_manifest) | {"manifest.json"}, scene=scene)
        for name, expected in own_manifest.items():
            check("worker_file_matches_manifest", checksum(local / name) == expected, scene=scene, file=name)
        check("worker_same_source_and_independent_budget", own_protocol["source_sha256"] == protocol["source_sha256"]
              and own_protocol["workloads"] == [scene] and own_protocol["total_cpu_seconds"] == 2400
              and own_protocol["total_wall_seconds"] == 3600 and own_protocol["max_full_simulator_calls"] == 768, scene=scene)
        inputs, previous_inputs = read(local / (scene + "_input.json")), read(pilot / (scene + "_input.json"))
        check("same_reused_original_map_input_as_pilot", inputs == previous_inputs
              and checksum(local / "original_profile.json") == protocol["profile_sha256"], scene=scene)
        check("source_and_profile_unchanged", not own_summary["source_changed_during_run"]
              and not own_summary["profile_changed_during_run"], scene=scene)
        collection = read(local / (scene + "_collection.json"))
        check("actual_collection_roles_and_denominator", collection["metadata"]["attempts"] == len(collection["opportunities"])
              and collection["metadata"]["selector_calls"] == sum(r["selector_called"] for r in collection["opportunities"]), scene=scene)
        original_tasks = {b["bag_id"]: b for b in inputs["future_engine_only"]}
        actual_files = set()
        for record in own_summary["samples"]:
            sample = read(local / record["file"])
            old_record = next(r for r in pilot_summary["samples"] if r["identity"] == record["identity"])
            old = read(pilot / old_record["file"])
            fields = ("state", "proposals", "normal_keys", "time", "source_node", "role", "band", "cursor",
                      "features", "features_physical", "physical_prefix_signatures", "checkpoint_metadata")
            check("strict_saved_physical_decision_same_as_pilot", all(sample[k] == old[k] for k in fields), identity=record["identity"])
            state = snapshot(sample["state"])
            assert_invariants(state)
            tray, bag = state.trays[sample["tray_id"]], state.bags[sample["bag_id"]]
            role = "arrival_at_destination" if tray.node == bag.destination else "origin" if tray.node == bag.origin else "continuation"
            check("role_from_actual_current_tray_and_task", role == sample["role"] and tray.bag_id == bag.bag_id
                  and sample["checkpoint_metadata"]["cursor"]["pending_tray_id"] == tray.tray_id, identity=record["identity"])
            prefixes = []
            for i, raw in enumerate(sample["proposals"]):
                proposal = candidate(raw)
                check("normal_proposal_still_owner_authorized", ExecutionValidator().validate(state, proposal, route_mode="next_edge").accepted
                      and actual_action_key(state, proposal, route_mode="next_edge") == sample["normal_keys"][i], identity=record["identity"], candidate=i)
                prefix = ExecutionValidator._safe_prefix(state, proposal)
                end = state.network.edges[prefix.legs[-1].edge_id].target if prefix.legs else tray.node
                prefixes.append(digest({"tray_id": prefix.tray_id, "bag_id": prefix.bag_id,
                    "legs": [asdict(leg) for leg in prefix.legs], "destination_node": end,
                    "unload_complete": prefix.unload_complete, "usable_at": prefix.usable_at, "prefix_only": prefix.prefix_only}))
            check("immediate_physical_prefix_record_matches_owner", prefixes == sample["physical_prefix_signatures"], identity=record["identity"])
            if not record["selected_for_labels"]:
                raise ValueError("formal18 sample request silently omitted")
            label = read(local / record["labels"][0])
            rows, k = label["raw_branches"], label["candidate_count"]
            indices = {(r["group"], r["candidate"], r["draw"]) for r in rows}
            check("complete_candidate_group_draw_request_grid", indices == {(g, c, f) for g in range(4) for c in range(k) for f in range(8)}
                  and len(rows) == len(indices) == label["requested_branches"] == 32 * k, identity=record["identity"])
            for g, group in enumerate(label["future_groups_offline_only"]):
                for f, tape in enumerate(group["tapes"]):
                    valid = len({b["bag_id"] for b in tape}) == len(tape)
                    for b in tape:
                        original = original_tasks[b["bag_id"]]
                        valid &= (b["bag_id"] not in state.bags and b["arrival"] > state.now
                            and all(b[key] == original[key] for key in ("bag_id", "origin", "destination", "protected"))
                            and b["deadline"] - b["arrival"] == original["deadline"] - original["arrival"]
                            and b["arrival"] in {max(state.now + 1, original["arrival"] + shift) for shift in (-2, 0, 2)})
                    check("future_has_original_valid_fields_and_is_common_to_actions", valid and all(
                        r["future_sha256"] == digest(tape) for r in rows if r["group"] == g and r["draw"] == f),
                        identity=record["identity"], group=g, draw=f)
            for r in rows:
                if r["status"] == "not_executed":
                    omitted += 1
                    check("unexecuted_row_has_no_cost_or_cache_credit", r.get("total_cost") is None and not r["cache_hit"], identity=record["identity"])
                    continue
                path = local / r["file"]
                if path not in cache_files:
                    full = json.loads(gzip.decompress(path.read_bytes()))
                    end_result = full.get("result")
                    if end_result is not None:
                        assert_invariants(snapshot(end_result["final_snapshot"]))
                    cache_files[path] = {**{k: full[k] for k in ("sample", "candidate", "future_sha256", "horizon_ticks")},
                        "cache_before_digest": digest(full.get("cache_before")),
                        "result": None if end_result is None else {"cost_components": end_result["cost_components"],
                            "total_cost": end_result["total_cost"], "final_now": end_result["final_snapshot"]["now"]}}
                    del full, end_result
                evidence = cache_files[path]
                if not r["cache_hit"]:
                    actual_files.add(r["file"])
                good = (evidence["sample"] == r["sample"] and evidence["candidate"] == r["candidate"]
                    and evidence["future_sha256"] == r["future_sha256"] and evidence["horizon_ticks"] == r["horizon_ticks"] == 80)
                check("memo_never_crosses_sample_candidate_tape_horizon", good, identity=record["identity"], file=r["file"])
                check("branch_restores_same_owned_cache", evidence["cache_before_digest"] == digest(sample["routing_cache"]), identity=record["identity"], file=r["file"])
                if r["status"] == "reached_horizon":
                    result = evidence["result"]
                    cost = sum(result["cost_components"][key] * weight for key, weight in COST_WEIGHTS.items())
                    check("finished_branch_endpoint_and_cost_accounting", result["final_now"] == state.now + 80
                          and abs(cost - r["total_cost"]) < 1e-8 and result["total_cost"] == r["total_cost"], identity=record["identity"], file=r["file"])
                else:
                    failures.append({"identity": record["identity"], "status": r["status"], "file": r["file"]})
            req, act, hit = len(rows), sum(not r["cache_hit"] and r["status"] != "not_executed" for r in rows), sum(r["cache_hit"] for r in rows)
            check("label_request_actual_cache_accounting", label["actual_branches"] == act and label["cache_reused_branches"] == hit, identity=record["identity"])
            requested += req
            actual += act
            reused += hit
            samples += 1
            empty += k == 0
            complete = bool(k) and all(r["status"] == "reached_horizon" for r in rows)
            check("complete_label_flag_excludes_zero_or_partial", label["complete_paired_label"] == complete, identity=record["identity"])
            vectors = [tuple(label["paired_costs"][g][c][f] for g in range(4) for f in range(8)) for c in range(k)]
            classes.append({"scene": scene, "identity": record["identity"], "node": sample["source_node"], "role": sample["role"],
                "candidate_count": k, "physical_prefix_count": len(set(prefixes)), "complete_paired_label": complete,
                "sampled_cost_vector_classes": len(set(vectors)) if complete else None,
                "candidate_mean_costs": [sum(v) / len(v) for v in vectors] if complete else None})
        check("actual_branch_files_exactly_accounted", actual_files == {p.name for p in local.glob("*_c*.json.gz")}
              and len(actual_files) == own_summary["actual_full_simulator_calls"], scene=scene)
    check("parent_complete_request_and_reuse_totals", requested == summary["requested_branch_rows"]
          and actual == summary["actual_full_simulator_calls"] and reused == summary["cache_reused_branches"]
          and requested == actual + reused + omitted)
    payload = {"scope": "read-only original-map developer labels; zero new rollout or fit calls", "checks": len(checks),
        "passed": sum(r["passed"] for r in checks), "failed_checks": [r for r in checks if not r["passed"]],
        "checks_detail": checks, "samples": samples, "zero_candidate_samples": empty,
        "requested_branches": requested, "actual_branches": actual, "cache_reused": reused, "not_executed": omitted,
        "recorded_noncompleted_branch_requests": failures, "physical_and_empirical_value_classes": classes,
        "roles": dict(Counter(r["role"] for r in classes)), "new_independent_source_count": 0,
        "limits": ["Role absence is not filled; these remain synthetic workloads on original topology, not observed airport history.",
            "Empirical cost vectors are conditional on the reused source, finite h80 and declared future law, not universal value equivalence.",
            "A zero or incomplete label is never assigned a numerical value or called a complete action comparison.",
            "CPU/wall safeguards are cooperative between queries/branches; no hard wall-clock guarantee."]}
    with output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in payload.items() if k not in {"checks_detail", "physical_and_empirical_value_classes", "recorded_noncompleted_branch_requests"}}))
    return int(bool(payload["failed_checks"]))


if __name__ == "__main__":
    raise SystemExit(main())
