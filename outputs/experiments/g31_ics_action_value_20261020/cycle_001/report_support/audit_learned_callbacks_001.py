"""Read closed named artifacts once; no polling, fitting, native or source edits."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

OUT = Path(__file__).resolve().parent
CYCLE = OUT.parent
ROOT = OUT.parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_ranker as ranker
from scripts.experiments.g31_ics_circulation import foundation_airport_prospective_control as control


def read(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith(".gz") else raw)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ref(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf8")).hexdigest()


def bound(reference):
    assert sha(reference["path"]) == reference["sha256"], reference["path"]
    return read(reference["path"])


def quantiles(values):
    a = np.asarray(values, dtype=float)
    assert np.isfinite(a).all() and (a >= 0).all()
    if not len(a):
        return {"count": 0, "sum_ms": 0., "mean_ms": None, "p50_ms": None,
            "p90_ms": None, "p95_ms": None, "p99_ms": None, "max_ms": None}
    return {"count": len(a), "sum_ms": float(a.sum()), "mean_ms": float(a.mean()),
        **{f"p{q}_ms": float(np.percentile(a, q)) for q in (50, 90, 95, 99)},
        "max_ms": float(a.max())}


def rescore(record, model, predictor):
    reconstructed = control.current_candidate_rows(record["observation"],
        record["baseline_decision"], record["opportunity"], parent=record["inference_parent"],
        information_variant=record["information_variant"],
        forecast_evidence=record.get("forecast_evidence"), copy_inputs=False)
    shared = {"parent", "observation", "opportunity", "baseline_decision", "forecast_evidence"}
    assert [{k: v for k, v in row.items() if k not in shared}
        for row in reconstructed] == record["inference_rows"]
    assert not any(key in row for row in reconstructed
        for key in ("target_return", "paired_advantage_bag_seconds", "transition", "actual_execution"))
    predicted = predictor(*reconstructed)
    assert math.isclose(predicted, record["predicted_patch_advantage"], rel_tol=1e-12, abs_tol=1e-7)
    assert (predicted > 0) == (record["selected_action_id"] == "a_patch")
    assert record["selected_semantic_action"] == reconstructed[int(predicted > 0)]["semantic_action"]
    result = {"audit_sequence": record["audit_sequence"], "record_sha256": digest(record),
        "observed_at": record["observed_at"], "owner_id": record["owner_id"],
        "public_state_sha256": record["public_state_digest"],
        "online_predicted_patch_advantage": record["predicted_patch_advantage"],
        "recomputed_predicted_patch_advantage": predicted,
        "absolute_score_error": abs(predicted - record["predicted_patch_advantage"]),
        "selected_action_id": record["selected_action_id"], "current_validation_retained": True,
        "outcome_or_target_fields_used": False, "fit_calls": 0}
    if model is not None:
        features = ranker._pair_features(*reconstructed, model["information_variant"])
        names = model["feature_names"]
        params = model["parameters"]
        x = np.array([[row[name] for name in names] for row in features])
        x = (x - np.asarray(params["center"])) / np.asarray(params["scale"])
        for i, layer in enumerate(params["layers"]):
            x = x @ np.asarray(layer["weight"]).T + np.asarray(layer["bias"])
            if i < len(params["layers"]) - 1:
                x = np.tanh(x)
        scores = x[:, 0] * params["target_scale"]
        delta = float(scores[1] - scores[0])
        assert math.isclose(predicted, delta, rel_tol=1e-12, abs_tol=1e-7)
        result.update(model_id=model["model_id"], architecture=model["architecture"],
            feature_dimension=len(names), independently_recomputed_reference_score=float(scores[0]),
            independently_recomputed_patch_score=float(scores[1]),
            independent_numpy_forward_advantage=delta)
    forecast = record.get("forecast_evidence")
    if forecast:
        result.update(forecast_model_id=forecast["model_id"],
            forecast_sha256=forecast["forecast_sha256"],
            actual_plan_receipt_sha256=forecast["plan_receipt"]["receipt_sha256"])
    return result


def verify_execution(execution, result, calls, ack_views):
    """Independent raw joins; G1 stops at first edge, receive/load are additional."""
    calls_by_key, acks, legs, events, loads = (defaultdict(list) for _ in range(5))
    for call in calls:
        if call.get("kind") == "transfer" and not call.get("retry"):
            request = call["request"]
            calls_by_key[(request["owner_id"], call["at"], request["tray_id"])].append(call)
    for owner, view in ack_views.items():
        for ack in view.get("delivered_transfer_acks", []):
            acks[(owner, ack["request_id"])].append(ack)
    for leg in result["leg_identities"]:
        if leg["kind"] == "empty_return":
            request, separator, suffix = leg["transport_leg_id"].rpartition(":empty_return:")
            assert separator and suffix == str(leg["runtime_id"])
            legs[request].append(leg)
    transfers = {t["request_id"]: t for t in result["transfers"]}
    assert len(transfers) == len(result["transfers"])
    tray_index = {t["tray_id"]: i for i, t in enumerate(result["trays"])}
    for number, event in enumerate(result["receipts"]):
        for key in {event.get("transport_leg_id"), event.get("reason")} - {None}:
            events[key].append((number, event))
        if event["event"] == "LOAD_START":
            loads[event["tray_id"]].append(event)
    for values in loads.values():
        values.sort(key=lambda x: x["time"])
    total = Counter()
    compact = []
    for row in execution["rows"]:
        actual = calls_by_key[(row["owner_id"], row["observed_at"], row["tray_id"])]
        assert len(actual) <= 1 and len(row["attempts"]) == len(actual)
        assert row["decision_differs"] == (row["chosen_intent"] != row["baseline_intent"])
        assert row["actual_submission_observed"] == bool(actual)
        total["proposed_decision_differences"] += row["decision_differs"]
        total["different_decision_with_actual_submission"] += row["decision_differs"] and bool(actual)
        verified_attempts = []
        for attempt, call in zip(row["attempts"], actual, strict=True):
            request = call["request"]
            rid = request["request_id"]
            assert request == attempt["actual_request"] and call["at"] == attempt["submitted_at"]
            assert call["reply"] == attempt["submission_reply"]
            intended = row["chosen_intent"]
            effective = lambda r: max(r["earliest_departure"], call["at"] + r["message_delay"])
            matches = intended is not None and all(request[k] == intended[k]
                for k in ("tray_id", "source", "destination"))
            matches = bool(matches and request.get("transfer_scope", "cross_zone_transfer")
                == intended.get("transfer_scope", "cross_zone_transfer")
                and effective(request) == effective(intended)
                and request["owner_id"] == row["owner_id"])
            assert matches == attempt["selected_intent_matches_actual_submission"]
            total["mismatched_actual_submission_count"] += not matches
            assert len(legs[rid]) <= 1
            leg = legs[rid][0] if legs[rid] else None
            assert leg == attempt["native_leg"]
            transfer = transfers.get(rid)
            assert transfer == attempt["native_transfer_at_export"]
            relevant = dict(events[rid])
            if leg:
                relevant.update(events[leg["transport_leg_id"]])
            ev = list(relevant.values())
            starts = [e for e in ev if e["event"] == "LEG_START"]
            edges = [e for e in ev if e["event"] == "EDGE_ENTER"]
            receives = [e for e in ev if e["event"] == "EMPTY_RECEIVED"]
            entity = (transfer["tray"] == tray_index[row["tray_id"]]
                and transfer.get("transfer_scope", "cross_zone_transfer")
                == request.get("transfer_scope", "cross_zone_transfer")) if transfer else None
            leg_matches = (leg["tray"] == tray_index[row["tray_id"]] and leg["job"] == -1
                and len(starts) == 1 and starts[0]["tray_id"] == row["tray_id"]
                and starts[0]["from"] == request["source"] and starts[0]["to"] == request["destination"]
                and call["at"] <= starts[0]["time"] <= result["physical_clock"]) if leg and starts else None
            assert entity == attempt["request_matches_native_transfer_entity"]
            assert leg_matches == attempt["native_leg_matches_entity_and_endpoints"]
            delivered = acks[(row["owner_id"], rid)]
            assert delivered == attempt["delivered_acks"]
            valid = [a for a in delivered if all(type(a.get(k)) in (int, float)
                and math.isfinite(a[k]) for k in ("observed_at", "delivered_at"))
                and call["at"] <= a["observed_at"] <= a["delivered_at"] <= result["physical_clock"]]
            assert len(valid) == attempt["ack_owner_and_clock_verified_count"]
            positive = [a for a in valid if a["status"] in
                ("granted", "dispatching", "departed", "in_transit", "received")]
            assert bool(positive) == attempt["positive_delivered_ack"]
            first_edge = min((e["time"] for e in edges), default=None)
            received = min((e["time"] for e in receives), default=None)
            assert first_edge == attempt["first_edge_at"] and received == attempt["received_at"]
            next_load = next((e for e in loads[row["tray_id"]]
                if received is not None and e["time"] >= received), None)
            assert next_load == attempt["next_load"]
            valid_edge = any(e["tray_id"] == row["tray_id"]
                and call["at"] <= e["time"] <= result["physical_clock"] for e in edges)
            g1 = matches and entity is True and leg_matches is True and bool(positive) and valid_edge
            assert g1 == attempt["complete_G1_execution_chain"]
            assert [e for e in ev if "REJECT" in e["event"] or "FAIL" in e["event"]] == attempt["rejection_events"]
            received_identity = bool(receives) and all(e["tray_id"] == row["tray_id"]
                and e["node"] == request["destination"] and e["to"] == request["destination"]
                for e in receives)
            if received_identity:
                assert first_edge is not None and first_edge <= received <= result["physical_clock"]
                assert transfer["received_at"] == received
            load_at_destination = bool(next_load and next_load["node"] == request["destination"])
            item = {"request_id": rid, "submitted_at": call["at"],
                "source": request["source"], "destination": request["destination"],
                "transfer_scope": request.get("transfer_scope", "cross_zone_transfer"),
                "effective_departure": effective(request), "selected_intent_matches_submission": matches,
                "native_leg": leg, "native_transfer": transfer,
                "positive_delivered_ack_count": len(positive),
                "first_positive_delivered_ack": min(positive, key=lambda a: a["delivered_at"]) if positive else None,
                "native_leg_start": starts[0] if len(starts) == 1 else None,
                "first_edge": min(edges, key=lambda e: e["time"]) if edges else None,
                "received": min(receives, key=lambda e: e["time"]) if receives else None,
                "received_entity_and_destination_verified": received_identity,
                "next_load_same_tray": next_load, "next_load_at_requested_destination": load_at_destination,
                "complete_G1_through_first_edge": bool(g1)}
            verified_attempts.append(item)
        total["different_decision_with_unique_leg"] += row["decision_differs"] and any(
            a["native_leg"] and a["selected_intent_matches_actual_submission"]
            and a["request_matches_native_transfer_entity"] is True
            and a["native_leg_matches_entity_and_endpoints"] is True
            and a["positive_delivered_ack"] for a in row["attempts"])
        total["different_decision_with_complete_G1_chain"] += row["decision_differs"] and any(
            a["complete_G1_through_first_edge"] for a in verified_attempts)
        if row["decision_differs"]:
            total["changed_rows_received_verified"] += any(a["received_entity_and_destination_verified"]
                for a in verified_attempts)
            total["changed_rows_next_load_same_tray"] += any(a["next_load_same_tray"] is not None
                for a in verified_attempts)
            total["changed_rows_next_load_at_requested_destination"] += any(
                a["next_load_at_requested_destination"] for a in verified_attempts)
            compact.append({k: row[k] for k in ("audit_sequence", "record_sha256", "owner_id",
                "observed_at", "tray_id", "selected_action_id", "baseline_intent", "chosen_intent")}
                | {"verified_attempts": verified_attempts})
    for key in ("proposed_decision_differences", "different_decision_with_actual_submission",
                "different_decision_with_unique_leg", "mismatched_actual_submission_count",
                "different_decision_with_complete_G1_chain"):
        assert total[key] == execution[key], key
    return dict(total), compact


def audit(name, parser_check=False):
    started = time.perf_counter()
    directory = CYCLE / name
    assert directory.parent == CYCLE and "/" not in name and "\\" not in name
    receipt_path = directory / "receipt.json"
    if not receipt_path.exists():
        return {"name": name, "status": "not_closed_no_audit_attempted"}
    receipt, plan = read(receipt_path), read(directory / "plan.json")
    worker = read(directory / "worker_report.json")
    assert receipt["worker"] == worker and receipt["plan_sha256"] == sha(directory / "plan.json")
    assert receipt["status"] == worker["status"] == "complete"
    assert receipt["process"]["exitcode"] == 0 and receipt["process"]["status"] == "exited"
    assert worker["native_constructor_attempts"] == 1
    if parser_check:
        assert name == "E_N18_C10_P801_001" and plan["information_variant"] == "C10"
        from scripts.experiments.g31_ics_circulation.foundation_airport_strong_rule import prepare_scorer
        model, predictor = None, prepare_scorer(plan["rule_freeze"])
    else:
        assert plan["batch"] in ("D", "G") and plan["information_variant"] in ("C01", "C11")
        assert plan["parent"]["split"] == "test"
        frozen = bound(plan["model_freeze"])
        assert plan["selected_model"] in frozen["models"]
        model = bound(plan["selected_model"]["checkpoint"])
        assert model["model_id"] == plan["selected_model"]["model_id"]
        assert model["model_id"] == digest({k: v for k, v in model.items() if k != "model_id"})
        assert model["seed"] == plan["model_seed"]
        assert model["information_variant"] == plan["information_variant"]
        predictor = ranker.prepare_predictor(model)
    for logical, expected in plan["sources"].items():
        assert sha(directory / "source" / logical) == expected, logical
    runtime_sources = ranker.source_pins()
    control_path = "scripts/experiments/g31_ics_circulation/foundation_airport_prospective_control.py"
    runtime_sources[control_path] = sha(ROOT / control_path)
    normalized_plan_sources = {k.replace("\\", "/"): v for k, v in plan["sources"].items()}
    for logical, expected in runtime_sources.items():
        assert sha(ROOT / logical) == expected == normalized_plan_sources[logical], logical
    for key in ("input", "binary", "native_acceptance", "rule_freeze", "grid_freeze"):
        assert sha(plan[key]["path"]) == plan[key]["sha256"], key
    summary = read(directory / "planner_summary.json")
    audit_receipt = read(directory / "callback_audit_receipt.json")
    assert sha(directory / "callback_audit.jsonl.gz") == audit_receipt["sha256"]
    preloads = read(directory / "actual_plan_preload_receipts.json")
    execution = read(directory / "execution_evidence.json.gz")
    indexes = {row["audit_sequence"]: row for row in execution["rows"]}
    assert len(indexes) == len(execution["rows"])
    result = read(directory / "final_result.json.gz")
    calls, ack_views = read(directory / "client_calls.json.gz"), read(directory / "ack_views.json.gz")
    assert result["physical_clock"] == worker["final_physical_time"] == plan["horizon"]
    execution_counts, changed = verify_execution(execution, result, calls, ack_views)
    chosen_witness = next((r for r in changed if any(a["complete_G1_through_first_edge"]
        and a["received_entity_and_destination_verified"] and a["next_load_at_requested_destination"]
        for a in r["verified_attempts"])), changed[0] if changed else None)
    sample_ids = ({changed[0]["audit_sequence"]} if changed else set())
    if chosen_witness:
        sample_ids.add(chosen_witness["audit_sequence"])
    previous, count, raw_bytes = "0" * 64, 0, 0
    statuses, reasons, forecasts = Counter(), Counter(), Counter()
    selectors, planning, samples = [], [], []
    indexed_seen = set()
    first_scored = None
    with gzip.open(directory / "callback_audit.jsonl.gz", "rt", encoding="utf8") as stream:
        for line in stream:
            raw_bytes += len(line.encode("utf8"))
            envelope = json.loads(line)
            row = envelope["record"]
            assert row["audit_sequence"] == count and row["previous_record_sha256"] == previous
            assert digest(row) == envelope["record_sha256"]
            previous, count = envelope["record_sha256"], count + 1
            statuses[row["status"]] += 1
            planning.append(row["planning_wall_ms"])
            assert row["planning_wall_ms"] == audit_receipt["timings_ms"][row["audit_sequence"]]["planning"]
            assert row["information_variant"] == plan["information_variant"]
            if model is not None:
                assert row["policy_id"] == model["model_id"]
            if row["status"] == "reference_fallback":
                reasons[row["reason"]] += 1
            if "public_state_digest" in row:
                assert row["public_state_digest"] == digest(row["observation"])
                assert row["baseline_batch_digest"] == digest(row["baseline_decision"]["intents"])
            assert row["owner_id"] == row["observation"]["owner_id"]
            assert row["observed_at"] == row["observation"]["now"]
            sequence = row["audit_sequence"]
            if sequence in indexes:
                index = indexes[sequence]
                tray = row["opportunity"]["candidates"][1]["tray_id"]
                chosen = next((r for r in row["chosen_decision"]["intents"] if r["tray_id"] == tray), None)
                baseline = next((r for r in row["baseline_decision"]["intents"] if r["tray_id"] == tray), None)
                assert index["record_sha256"] == envelope["record_sha256"]
                assert index["chosen_intent"] == chosen and index["baseline_intent"] == baseline
                assert index["decision_differs"] == (chosen != baseline)
                assert index["owner_id"] == row["owner_id"] and index["observed_at"] == row["observed_at"]
                assert index["tray_id"] == tray and index["selected_action_id"] == row["selected_action_id"]
                indexed_seen.add(sequence)
            if "inference_rows" not in row:
                continue
            selectors.append(row["selector_wall_ms"])
            assert row["selected_action_id"] == ("a_patch" if row["predicted_patch_advantage"] > 0 else "a_ref")
            if first_scored is None:
                first_scored = sequence
                sample_ids.add(sequence)
            forecast = row.get("forecast_evidence")
            if plan["information_variant"] in ("C10", "C11"):
                assert forecast and forecast["plan_receipt"] == preloads[row["owner_id"]]
                assert forecast["actual_callback_consumption"] is True
                assert forecast["forecast_provenance"] == "actual_callback_received"
                assert forecast["public_state_sha256"] == row["public_state_digest"]
                assert forecast["forecast_sha256"] == digest(forecast["forecast"])
                forecasts[forecast["model_id"]] += 1
            else:
                assert forecast is None
            if sequence in sample_ids:
                samples.append(rescore(row, model, predictor))
    assert indexed_seen == set(indexes)
    assert count == audit_receipt["records"] == summary["counts"]["recorded_callbacks"]
    assert previous == audit_receipt["tail_record_sha256"]
    assert len(selectors) == summary["counts"].get("actual_scored_callbacks", 0)
    assert len(samples) == len(sample_ids)
    if chosen_witness:
        chosen_witness["fixed_selector_replay"] = next(
            s for s in samples if s["audit_sequence"] == chosen_witness["audit_sequence"])
    audit_io = [r["audit_persistence"] for r in audit_receipt["timings_ms"]]
    assert len(audit_io) == count
    suffix = "callback_chain_parser_audit_001" if parser_check else "learned_callback_audit_001"
    output_path = OUT / f"{name}_{suffix}.json"
    output = {"schema": "g31.foundation.actual_learned_callback_independent_audit.v1",
        "name": name, "status": "passed_closed_callback_weight_and_raw_execution_audit",
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "audit_script": ref(__file__), "parser_check_on_E": parser_check,
        "information_variant": plan["information_variant"], "parent": plan["parent"],
        "selected_model": plan["selected_model"], "model_freeze": plan["model_freeze"],
        "source_archive_files_hash_verified": len(plan["sources"]),
        "offline_replay_runtime_sources_match_frozen_worker": runtime_sources,
        "artifacts": {n: ref(directory / n) for n in ("plan.json", "receipt.json",
            "worker_report.json", "planner_summary.json", "callback_audit.jsonl.gz",
            "callback_audit_receipt.json", "client_calls.json.gz", "ack_views.json.gz",
            "execution_evidence.json.gz", "final_result.json.gz")},
        "callback_hash_chain_complete": True, "callback_records": count,
        "callback_status_counts": dict(statuses), "fallback_reasons": dict(reasons),
        "actual_scored_callbacks": len(selectors), "forecast_model_counts": dict(forecasts),
        "fixed_weight_replays": samples, "first_scored_callback": first_scored,
        "first_different_callback": changed[0]["audit_sequence"] if changed else None,
        "execution_counts_independently_joined": execution_counts,
        "compact_changed_witness": chosen_witness,
        "changed_witness_selection": "First changed row with complete G1, verified receipt and a subsequent load at the requested destination; otherwise first changed row with explicit missing links.",
        "changed_callback_count": len(changed),
        "changed_callbacks_compact": [{"audit_sequence": r["audit_sequence"], "observed_at": r["observed_at"],
            "tray_id": r["tray_id"], "attempts": len(r["verified_attempts"]),
            "complete_G1": any(a["complete_G1_through_first_edge"] for a in r["verified_attempts"])}
            for r in changed],
        "timing": {"selector_current_features_and_fixed_forward": quantiles(selectors),
            "planner_before_audit_stream": quantiles(planning),
            "callback_audit_persistence": quantiles(audit_io),
            "planner_plus_recorded_audit_sum_ms": math.fsum(planning) + math.fsum(audit_io),
            "native_branch_process_wall_seconds": receipt["process"]["wall_seconds"],
            "worker_cumulative_elapsed_at_last_segment_seconds": worker["segments"][-1]["elapsed"],
            "audit_read_and_verification_wall_seconds": time.perf_counter() - started,
            "scopes": {
                "selector": "Per scored callback: current validation, action features and frozen selector forward. Excludes candidate building, forecast generation, native submission and audit IO.",
                "planner": "All recorded initial callbacks, including warmup and no-candidate calls: base planner, candidate/forecast preparation and selector; excludes subsequent audit sink and native submission. Residual calls are not captured in this distribution.",
                "audit": "Recorded callback hashing, JSON encoding, gzip write/flush and index append. Stream close and receipt-file write are not separately timed.",
                "sum": "Measured planner plus callback audit persistence only; not a claim of full controller or end-to-end latency.",
                "worker_elapsed": "Worker segment elapsed is cumulative since worker start. Use the last value; never sum cumulative segment elapsed values.",
                "replay": "Offline verification timing is separate from original online selector measurements."}},
        "storage": {"callback_compressed_bytes": (directory / "callback_audit.jsonl.gz").stat().st_size,
            "callback_uncompressed_jsonl_bytes": raw_bytes, "full_observation_once_per_callback": True},
        "limitations": ["G1 certifies chosen request/entity, delivered positive ACK and first edge, not full task success.",
            "Receive and next-load links are checked against raw native evidence; a later same-tray load is not an isolated causal benefit estimate.",
            "No full-population cost comparison or learned-policy benefit inference is performed here.",
            "Fixed-weight replays sample first scored, first changed and chosen witness callbacks; all stream hashes and all saved execution joins are checked.",
            "Recorded timing scopes are distinct; none alone certifies a 100ms controller SLA."],
        "fit_calls": 0, "native_jobs_started": 0, "runtime_sources_modified": False,
        "protected_takeover_eligible": False, "strict_nonharm_certified": False}
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf8")
    return {"name": name, "status": output["status"], "artifact": ref(output_path),
        "scored_callbacks": len(selectors), "changed_callbacks": len(changed),
        "execution": execution_counts, "timing": output["timing"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="+")
    parser.add_argument("--parser-check-E", action="store_true")
    options = parser.parse_args()
    for name in options.names:
        print(json.dumps(audit(name, options.parser_check_E), ensure_ascii=False), flush=True)
