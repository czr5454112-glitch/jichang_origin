"""One evaluator-only no-plan feature benchmark at an actual precommit hook.

The caller binds native provenance and excludes this diagnostic from actor
latency. This module neither constructs native state nor chooses any action.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback

from . import foundation_action_value as value
from . import foundation_airport_learning_public as public

SCHEMA = "g31.foundation.airport_actual_prepared_feature_gate.v1"


def _require(ok, reason):
    if not ok:
        raise ValueError("airport_prepared_callback_gate:"+reason)


def _reference(path, raw=None):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(
        path.read_bytes() if raw is None else raw).hexdigest()}


def _write_timed(path, item):
    timing = {}
    begin = time.perf_counter()
    raw = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf8") + b"\n"
    timing["serialize_seconds"] = time.perf_counter()-begin
    with Path(path).open("xb") as stream:
        begin = time.perf_counter()
        stream.write(raw)
        timing["write_seconds"] = time.perf_counter()-begin
        begin = time.perf_counter()
        stream.flush()
        timing["flush_seconds"] = time.perf_counter()-begin
        begin = time.perf_counter()
        os.fsync(stream.fileno())
        timing["fsync_seconds"] = time.perf_counter()-begin
    begin = time.perf_counter()
    reference = _reference(path, raw)
    timing["hash_seconds"] = time.perf_counter()-begin
    timing["bytes"] = len(raw)
    return reference, timing


def _load_historical(directory, filename):
    directory = Path(directory)
    plan_path = directory/"plan.json"
    plan = json.loads(plan_path.read_bytes())
    matches = [key for key in plan["source_archive"] if Path(key).name == filename]
    _require(len(matches) == 1, "one_historical_feature_source")
    key = matches[0]
    source = directory/plan["source_archive"][key]
    reference = _reference(source)
    _require(reference["sha256"] == plan["source_sha256"][key], "historical_source_pin")
    name = __package__+"._prepared_gate_"+source.stem+"_"+reference["sha256"][:12]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name], reference, _reference(plan_path)


def _unknown_no_plan_forecast(observation, episode_end):
    """Structural unknowns only: no plan, forecast model or predicted values."""
    now = observation["now"]
    return {"schema": "g31.foundation.new_demand_forecast.v1",
        "owner_scope": observation["owner_id"], "forecast_origin": now,
        "bin_edges_seconds": [0., 60., 300., 900., 1800.],
        "remaining_support_until": episode_end, "new_demand_mean_by_region": {},
        "missing_mask_by_region": {}, "context_sha256": None,
        "mapping_version": "public_nodes_all_unknown_no_plan_feature_benchmark_v1",
        "information_cutoffs": {"training_labels_closed_at": 0., "model_frozen_at": 0.,
            "plan_received_at": None, "observed_arrivals_through": None},
        "cutoff_zero_means": "schema_placeholder_no_training_or_forecast_model_exists",
        "forecast_model_exists": False, "no_predicted_demand_values_created": True}


def make_no_plan_feature_gate(output, *, episode_id, episode_end,
                             minimum_batch_size=3, historical_directory=None):
    """Prepare once before native; returned keyword hook runs at most once.

    The returned receipt contains its own final write timing and total hook
    duration, so the worker must retain that return in its final run report.
    """
    _require(type(minimum_batch_size) is int and minimum_batch_size >= 3,
        "actual_large_batch_threshold")
    if historical_directory is None:
        historical_directory = Path(__file__).resolve().parents[3]/(
            "outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/B2_live_behavior_shadow_003")
    old_value, old_value_ref, plan_ref = _load_historical(historical_directory, "foundation_action_value.py")
    old_public, old_public_ref, _ = _load_historical(historical_directory, "foundation_airport_learning_public.py")
    directory = Path(output).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    setup = {"schema": SCHEMA, "status": "registered_one_off_no_plan_feature_gate",
        "historical_plan": plan_ref, "historical_sources": [old_value_ref, old_public_ref],
        "current_sources": [_reference(module.__file__) for module in (value, public)] + [_reference(__file__)],
        "episode_id": episode_id, "episode_end": episode_end, "minimum_batch_size": minimum_batch_size,
        "selection": "first_actual_precommit_batch_at_least_threshold",
        "maximum_callbacks": 1, "fit_calls": 0, "no_plan": True, "weights_loaded": False,
        "scores_used_for_selection": False, "native_execution_authority": False}
    setup_ref, _ = _write_timed(directory/"setup.json", setup)
    attempted = False

    def gate(*, observation, decision, callback_sequence):
        nonlocal attempted
        if attempted or len(decision["intents"]) < minimum_batch_size:
            return None
        attempted = True
        begin = time.perf_counter()
        report = {"schema": SCHEMA, "status": "failed", "setup": setup_ref,
            "callback_sequence": callback_sequence, "actual_candidate_count": len(decision["intents"]),
            "at": observation["now"], "owner_id": observation["owner_id"],
            "fit_calls": 0, "forward_calls": 0, "forecast_models_consumed": 0,
            "native_execution_authority": False, "scores_used_for_selection": False,
            "candidate_conditional_labels_created": 0, "stage_seconds": {}, "storage": {},
            "native_callback_binding_must_be_attested_by_worker": True,
            "timing_scope": "offline evaluator inside precommit; excluded from actor protocol latency",
            "new_pair_ranker_performance_claimed": False, "deployment_latency_certified": False}
        try:
            stage = time.perf_counter()
            original_sha = value.digest({"observation": observation, "decision": decision})
            record = value.detached({"schema": "g31.foundation.airport_policy_observation.v1",
                "owner_id": observation["owner_id"], "now": observation["now"],
                "sequence": callback_sequence, "observation": observation, "decision": decision,
                "readonly": True, "native_execution_authority": False,
                "candidate_conditional_labels": None})
            forecast = _unknown_no_plan_forecast(record["observation"], episode_end)
            report["stage_seconds"]["detach_current_and_unknown_schema"] = time.perf_counter()-stage
            kwargs = dict(episode_id=episode_id, episode_end=episode_end)
            stage = time.perf_counter()
            wrapped, old_audit = old_public.wrap_record(record, forecast, **kwargs)
            old_candidates = old_public.proposal_actions(record)
            actions = [candidate["semantic"] for candidate in old_candidates]
            report["stage_seconds"]["historical_adapter_and_proposals"] = time.perf_counter()-stage
            stage = time.perf_counter()
            old_features = [old_value.features(wrapped, action) for action in actions]
            report["stage_seconds"]["historical_per_candidate_features"] = time.perf_counter()-stage
            stage = time.perf_counter()
            current, audit, candidates = public.prepare_record(record, forecast, **kwargs)
            report["stage_seconds"]["prepared_current_and_proposals"] = time.perf_counter()-stage
            stage = time.perf_counter()
            matrix = value.prepare_feature_matrix(current, actions)
            features = matrix.feature_rows()
            report["stage_seconds"]["single_prepared_feature_matrix"] = time.perf_counter()-stage
            report.update(feature_count=len(matrix.names), current_context_build_count=1,
                feature_matrix_build_count=1, feature_fields_exactly_equal=features == old_features,
                original_proposals_exactly_equal=candidates == old_candidates,
                original_adapter_exactly_equal=audit == old_audit and current.to_observation() == wrapped)
            _require(report["feature_fields_exactly_equal"] and report["original_proposals_exactly_equal"]
                and report["original_adapter_exactly_equal"], "historical_prepared_exact_equivalence")
            _require(original_sha == value.digest({"observation": observation, "decision": decision}),
                "actual_current_and_full_batch_unchanged")
            report["original_callback_sha256"] = original_sha
            report["full_input"], report["storage"]["full_input"] = _write_timed(
                directory/"complete_actual_callback.json", {"record": record, "forecast": forecast})
            report["comparison"], report["storage"]["comparison"] = _write_timed(
                directory/"feature_comparison.json", {"candidates": candidates,
                    "historical_features": old_features, "prepared_features": features,
                    "old_feature_digest": value.digest(old_features),
                    "prepared_feature_digest": value.digest(features)})
            report["status"] = "passed_actual_current_feature_equivalence"
        except Exception:
            report["exception"] = traceback.format_exc()
        report["hook_seconds_before_receipt_storage"] = time.perf_counter()-begin
        receipt_ref, receipt_timing = _write_timed(directory/"receipt.json", report)
        return {"schema": SCHEMA, "status": report["status"], "artifact": receipt_ref,
            "actual_candidate_count": len(decision["intents"]),
            "receipt_storage": receipt_timing, "hook_total_wall_seconds": time.perf_counter()-begin,
            "actor_latency_excludes_this_diagnostic": True, "fit_calls": 0,
            "feature_count": report.get("feature_count"), "forward_calls": 0}
    return gate
