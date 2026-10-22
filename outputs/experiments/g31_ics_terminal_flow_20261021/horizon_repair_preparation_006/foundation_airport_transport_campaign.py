"""Terminal-flow paired stages sharing the existing native and resource ledger.

prepare-block freezes concrete plans; run-block executes only those plans;
evaluate retains failures and per-parent differences. No work runs on import.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import secrets

from . import foundation_airport_joint_campaign as campaign
from . import foundation_airport_joint_budget as budget
from .foundation_airport_inventory_spi_campaign import bound, read_bound
from .foundation_airport_transport_allocation import DEFAULT_CONFIG
from .foundation_airport_terminal_forecast import bin_edges

SCHEMA = "g31.terminal_flow.campaign.v1"
ROOT = campaign.CYCLE / "terminal_flow"
BLOCKS = {
    "gate": (2101,), "confirm": (2101,), "export_gate": (2101,), "bridge": (2201, 2202, 2203, 2204),
    "bins": (2201, 2202, 2203, 2204), "period": (2201, 2202, 2203, 2204),
    "predictor": (2201, 2202, 2203, 2204), "train_demand": (2101, 2102),
}
METHODS = {
    "gate": ("C00", "C10", "TF-current", "TF-B1-60", "TF-B1-300"),
    "confirm": ("TF-current", "TF-B1-60", "TF-B1-300"),
    "export_gate": ("C00", "TF-B1-300"),
    "bridge": ("C00", "C10", "TF-current", "TF-B1-60"),
    "bins": ("TF-B1-300",), "period": ("TF-B1-300-replan300",),
    "predictor": ("TF-predictor",), "train_demand": ("TF-B1-300",),
}
NATIVE_GATE_PHASES = ("gate", "confirm", "export_gate")
REFERENCES = {"TF-B1-60-H1800": "TF-B1-60", "TF-B1-300": "TF-B1-60", "TF-B1-600": "TF-B1-60",
    "TF-B1-near-fine": "TF-B1-60", "TF-B1-300-replan300": "TF-B1-300",
    "TF-predictor": "TF-B1-300", "TF-B1-60": "C10", "TF-current": "C00", "C10": "C00"}
ALLOWED_COMPARISON_DIFFERENCES = {
    "TF-B1-60-H1800": ("projection_horizon",),
    "C10": ("demand_information",),
    "TF-current": ("selector_algorithm", "allocator"),
    "TF-B1-60": ("selector_algorithm", "allocator"),
    "TF-B1-300": ("forecast_bin_edges_seconds",),
    "TF-B1-600": ("forecast_bin_edges_seconds",),
    "TF-B1-near-fine": ("forecast_bin_edges_seconds",),
    "TF-B1-300-replan300": ("recompute_period_seconds",),
    "TF-predictor": ("demand_model",),
}


def method_contract_errors(plan):
    """Method names bind the exact experiment axis, not merely a display label."""
    method = plan["method"]
    if not method.startswith("TF-"):
        return []
    mode = ("near_fine" if method == "TF-B1-near-fine" else "600" if method == "TF-B1-600"
            else "300" if "300" in method or method == "TF-predictor" else "60")
    expected = {"forecast_bin_edges_seconds": bin_edges(mode), "forecast_horizon_seconds": 1800.,
        "recompute_period_seconds": 300. if method == "TF-B1-300-replan300" else 60.,
        "projection_horizon_seconds": 1800. if method == "TF-B1-60-H1800" else 600.,
        "supply_mode": "committed_only"}
    errors = [key for key, value in expected.items() if plan.get(key) != value]
    if (method == "TF-predictor") != bool(plan.get("demand_model")):
        errors.append("demand_model_method_binding")
    if plan.get("model") or plan.get("action_value_override", False):
        errors.append("action_value_model_forbidden")
    controller, allocator = plan.get("controller", {}), plan.get("transport_config", {})
    if controller.get("control_period") != 60. or controller.get("command_delay") != 2.:
        errors.append("native_control_timing")
    if allocator.get("dispatch_slot_seconds") != 60. or allocator.get("command_delay_seconds") != 2.:
        errors.append("dispatch_timing")
    return errors


def comparison_contract(plan):
    """Include all deliberate axes; pair comparisons remove only an allowlist."""
    method = plan["method"]
    def sha(key):
        return (plan.get(key) or {}).get("sha256")
    return dict(input=sha("input"), binary=sha("binary"), sources=sha("source_bundle"),
        worker_evidence_contract=plan.get("worker_evidence_contract", campaign.LEGACY_EVIDENCE_EXPORT),
        controller=plan.get("controller"), mapping=sha("mapping"), model=sha("model"),
        forecast_binding=sha("forecast_binding"), arrival_support=sha("arrival_support_contract"),
        projection_horizon=plan.get("projection_horizon_seconds"), supply_mode=plan.get("supply_mode"),
        activation=plan.get("activation"), allocator=plan.get("transport_config"),
        forecast_bin_edges_seconds=plan.get("forecast_bin_edges_seconds", bin_edges("60")),
        forecast_horizon_seconds=plan.get("forecast_horizon_seconds", 1800.),
        recompute_period_seconds=plan.get("recompute_period_seconds", 60.), demand_model=sha("demand_model"),
        demand_information="current_only" if method in ("C00", "TF-current") else "public_flight_forecast",
        selector_algorithm="terminal_flow" if method.startswith("TF-") else "joint_rule",
        behavior_seed=plan.get("behavior_seed"), event_budget=plan.get("event_budget"),
        global_event_budget=plan.get("global_event_budget"), cost_scope=plan.get("cost_scope"))


def _dependency_phase(phase):
    return (None if phase in NATIVE_GATE_PHASES else "bridge" if phase == "bins"
            else "bins" if phase in ("period", "predictor") else "native_gate")


def _validate_block_manifest(block):
    phase = block.get("phase")
    if block.get("schema") != SCHEMA or phase not in BLOCKS:
        raise ValueError("terminal_flow:block_schema_or_phase")
    parents = block.get("parents", [])
    if (not parents or len(parents) != len(set(parents)) or not set(parents) <= set(BLOCKS[phase])
            or block.get("methods") != list(METHODS[phase])):
        raise ValueError("terminal_flow:block_registered_methods_parents")
    training_calibration = None
    if phase == "train_demand":
        if block.get("batch") != "initial":
            raise ValueError("terminal_flow:training_collection_initial_quota_required")
        training_calibration = bound(campaign.CYCLE/"runtime_calibration_001.json")
    pairs, tasks, parent_contracts = set(), set(), {}
    for ref in block["task_plans"]:
        plan = read_bound(ref)
        pair = plan["parent"]["parent_seed"], plan["method"]
        if pair in pairs or plan["task_id"] in tasks:
            raise ValueError("terminal_flow:duplicate_block_task")
        pairs.add(pair); tasks.add(plan["task_id"])
        if plan.get("source_bundle") != block["source_bundle"]:
            raise ValueError("terminal_flow:task_source_differs_from_registered_block")
        if plan["horizon"] != (18000. if phase in NATIVE_GATE_PHASES else 59400.):
            raise ValueError("terminal_flow:registered_phase_horizon")
        if phase == "train_demand":
            if plan["parent"].get("split") != "train":
                raise ValueError("terminal_flow:training_collection_TRAIN_only")
            if plan.get("batch") != "initial" or plan.get("calibration") != training_calibration:
                raise ValueError("terminal_flow:training_collection_fixed_runtime_calibration")
            campaign.verify_calibration(plan)
        if method_contract_errors(plan):
            raise ValueError("terminal_flow:task_method_contract:"+",".join(method_contract_errors(plan)))
        if plan["method"].startswith("TF-") and plan.get("transport_config") != block["fixed_allocator"]:
            raise ValueError("terminal_flow:task_allocator_differs_from_registered_block")
        invariant = comparison_contract(plan)
        for key in ("selector_algorithm", "allocator", "demand_information", "forecast_bin_edges_seconds",
                    "recompute_period_seconds", "demand_model"):
            invariant.pop(key)
        old = parent_contracts.setdefault(pair[0], invariant)
        if old != invariant:
            raise ValueError("terminal_flow:within_block_physical_or_information_contract_mismatch")
    if pairs != {(parent, method) for parent in parents for method in METHODS[phase]}:
        raise ValueError("terminal_flow:incomplete_registered_comparison_block")


def _validate_dependencies(block):
    needed = _dependency_phase(block["phase"])
    if needed is None:
        return
    coverage, valid = set(), 0
    for reference in block.get("dependencies", []):
        previous = read_bound(reference)
        _validate_block_manifest(previous)
        phase_ok = previous["phase"] in NATIVE_GATE_PHASES if needed == "native_gate" else previous["phase"] == needed
        if not phase_ok or previous["source_bundle"] != block["source_bundle"]:
            raise ValueError("terminal_flow:dependency_phase_or_source_mismatch")
        if not evaluate([reference["path"]])["all_registered_closed"]:
            raise ValueError("terminal_flow:registered_dependency_no_longer_closed")
        valid += 1
        coverage.update(previous["parents"])
    if not valid or needed != "native_gate" and not set(block["parents"]) <= coverage:
        raise ValueError("terminal_flow:closed_dependency_required:"+needed)


def read(path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf8") as stream:
            return json.load(stream)
    return campaign.common.read(path)


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return bound(path)


def prepare_block(name, *, phase, source, parents=None, demand_model=None):
    """No additional campaign budget; unused old phase quotas remain bounded."""
    if phase not in BLOCKS:
        raise ValueError("terminal_flow:unknown_phase")
    if demand_model is not None and phase != "predictor":
        raise ValueError("terminal_flow:demand_model_only_in_predictor_phase")
    selected = tuple(parents or BLOCKS[phase])
    if not selected or len(selected) != len(set(selected)) or not set(selected) <= set(BLOCKS[phase]):
        raise ValueError("terminal_flow:registered_parent_block")
    status = budget.status(campaign.CYCLE)
    if status["open_runners"] or status["unfinished_native_tasks"]:
        raise ValueError("terminal_flow:active_or_unresolved_old_work")
    directory = ROOT / name
    if directory.exists():
        raise ValueError("terminal_flow:fresh_block_name")
    source_ref = bound(source)
    read_bound(source_ref)
    dependencies = []
    if phase not in NATIVE_GATE_PHASES:
        needed_phase = _dependency_phase(phase)
        covered = set()
        for path in sorted(ROOT.glob("*/block.json")):
            previous = read(path)
            phase_ok = (previous["phase"] in NATIVE_GATE_PHASES if needed_phase == "native_gate"
                        else previous["phase"] == needed_phase)
            if not phase_ok or previous["source_bundle"] != source_ref:
                continue
            if needed_phase != "native_gate" and not set(selected) & set(previous["parents"]):
                continue
            _validate_block_manifest(previous)
            if evaluate([path])["all_registered_closed"]:
                dependencies.append(bound(path))
                covered.update(previous["parents"])
        if not dependencies or needed_phase != "native_gate" and not set(selected) <= covered:
            raise ValueError("terminal_flow:closed_dependency_required:"+needed_phase)
    if phase in NATIVE_GATE_PHASES:
        calibration = dict(before_training=True, horizon=18000., soft_seconds=660.,
            hard_seconds=720., estimated_evidence_bytes=128*1024**2,
            basis=("same_native030_closed_18000s_export_equivalence_gate; existing_bridge_quota"
                if phase == "export_gate" else
                "same_native030_eight_closed_18000s_gates_max61.94s; conservative_new_solver_allowance"))
        calibration_ref = write_once(directory/"calibration.json", calibration)
        batch = "bridge" if phase == "export_gate" else "reserve"
    else:
        calibration_ref = bound(campaign.CYCLE/"runtime_calibration_001.json")
        calibration = read_bound(calibration_ref)
        batch = "development" if phase in ("bridge", "bins") else "initial"
    if phase == "train_demand" and (calibration.get("before_training") is not True
                                    or calibration.get("horizon") != 59400.):
        raise ValueError("terminal_flow:training_collection_full_registered_horizon_required")
    mapping = bound(campaign.CYCLE/"training/mapping_fit_001/mapping.json")
    model_ref = bound(demand_model) if demand_model else None
    if phase == "predictor" and model_ref is None:
        raise ValueError("terminal_flow:predictor_model_required")
    needed = len(selected)*len(METHODS[phase])
    limits = read(campaign.CYCLE/"campaign_budget.json")
    if status["by_batch"][batch]+needed > limits["allocations"][batch]:
        raise ValueError("terminal_flow:whole_block_batch_budget")
    if status["native_starts"]+needed > limits["native_start_limit"]:
        raise ValueError("terminal_flow:whole_block_native_budget")
    if status["active_seconds"]+needed*calibration["hard_seconds"] > limits["active_seconds_limit"]:
        raise ValueError("terminal_flow:whole_block_active_time_budget")
    evidence = needed*calibration["estimated_evidence_bytes"]
    if (status["evidence_bytes"]+evidence >= limits["new_evidence_bytes_limit"]
            or status["free_bytes"]-evidence < limits["free_space_floor_bytes"]):
        raise ValueError("terminal_flow:whole_block_disk_budget")
    tasks = []
    for seed in selected:
        for method in METHODS[phase]:
            task = campaign.prepare(f"TF_{name}_{method}_P{seed}", method=method, seed=seed, batch=batch,
                source_bundle=source_ref, mapping=mapping, calibration=calibration_ref,
                demand_model=model_ref, transport_config=DEFAULT_CONFIG,
                **{k: calibration[k] for k in ("horizon", "soft_seconds", "hard_seconds", "estimated_evidence_bytes")})
            tasks.append(bound(task/"plan.json"))
    result = dict(schema=SCHEMA, name=name, phase=phase, parents=list(selected), methods=list(METHODS[phase]),
        task_plans=tasks, source_bundle=source_ref, prior_budget=status, batch=batch,
        fixed_allocator=DEFAULT_CONFIG, demand_model=model_ref,
        old_action_Q_stages="not_dispatched; preserved_unchanged_historical_registration",
        dependencies=dependencies,
        formal_test_locked=True, R1_enabled=False, no_claim_of_service_improvement=True)
    if phase == "train_demand":
        result.update(purpose="training_demand_label_collection", scientific_comparison=False,
            label_scope="mature observed TRAIN windows only; closure does not certify labels or predictor quality")
    _validate_block_manifest(result)
    _validate_dependencies(result)
    write_once(directory/"block.json", result)
    budget.append(campaign.CYCLE, "terminal_flow_block_registered", block=bound(directory/"block.json"),
        rationale="new demand-only prediction and transport allocation; reuse unspent existing quotas")
    return result


def run_block(path):
    block = read(path)
    _validate_block_manifest(block)
    _validate_dependencies(block)
    status = budget.status(campaign.CYCLE)
    if status["open_runners"] or status["unfinished_native_tasks"]:
        raise ValueError("terminal_flow:recover_existing_runner_first")
    identity = "terminal-flow-"+secrets.token_hex(12)
    budget.append(campaign.CYCLE, "runner_open", runner_id=identity, purpose=block["name"])
    try:
        for reference in block["task_plans"]:
            plan = read_bound(reference)
            result = campaign.launch(Path(reference["path"]).parent)
            print(json.dumps(dict(task_id=plan["task_id"], status=result["worker"]["scientific_status"])), flush=True)
            if result["worker"]["scientific_status"] != "closed":
                break
    finally:
        budget.append(campaign.CYCLE, "runner_close", runner_id=identity)
    return evaluate([path])


def evaluate(paths):
    rows = []
    for path in paths:
        block = read(path)
        label_collection = block.get("phase") == "train_demand"
        if label_collection:
            _validate_block_manifest(block)
        for ref in block["task_plans"]:
            plan = read_bound(ref)
            directory = Path(ref["path"]).parent
            receipt = read(directory/"receipt.json") if (directory/"receipt.json").exists() else None
            row = dict(parent=plan["parent"]["parent_seed"], method=plan["method"], task_id=plan["task_id"],
                block_path=str(Path(path).resolve()),
                purpose="training_demand_label_collection" if label_collection else "paired_development_evidence",
                comparison_eligible=not label_collection,
                horizon=plan["horizon"], status="not_started" if receipt is None else receipt["worker"]["scientific_status"],
                receipt=None if receipt is None else bound(directory/"receipt.json"))
            row["comparison_contract"] = comparison_contract(plan)
            row["method_contract_errors"] = method_contract_errors(plan)
            row["closure_errors"] = []
            if receipt is not None:
                row.update(cost=receipt["worker"].get("cost"), funnel=receipt["worker"].get("funnel"),
                    timing=receipt["worker"].get("policy_timing"), wall_seconds=receipt["worker"].get("wall_seconds"),
                    peak_memory_bytes=receipt["worker"].get("peak_memory_bytes"))
            trajectory = directory/"trajectory.json.gz"
            if row["status"] == "closed":
                if (receipt.get("plan_sha256") != ref["sha256"] or receipt.get("process", {}).get("exitcode") != 0
                        or receipt["worker"].get("process_status") != "completed"
                        or receipt["worker"].get("final_physical_time") != plan["horizon"]):
                    row["closure_errors"].append("receipt_process_plan_or_horizon_binding")
                worker_path = directory/"worker_report.json"
                if not worker_path.exists() or read(worker_path) != receipt["worker"]:
                    row["closure_errors"].append("worker_report_binding")
                if not trajectory.exists():
                    row["closure_errors"].append("trajectory_missing")
            if row["status"] == "closed" and trajectory.exists():
                data = read(trajectory)
                if (data.get("physical_clock") != plan["horizon"] or data.get("logs_complete") is not True
                        or data.get("scientific_status") != "closed_finite_horizon"
                        or data.get("process_status") != "completed"):
                    row["closure_errors"].append("trajectory_not_complete_registered_horizon")
                acts = [r for r in data["rows"] if r["requested_action"]["kind"] != "noop"]
                row.update(system_J=data["system_J"], proposed=len(acts),
                    submitted=sum(bool(r.get("actual_submission")) for r in acts),
                    accepted=sum(any(a.get("status") in ("accepted", "granted", "dispatching", "departed", "in_transit", "received")
                                     for a in (r.get("ack") or [])) for r in acts),
                    received=sum(r.get("received_event") is not None for r in acts),
                    physical_failure=sum(bool(r.get("physical_failure")) for r in acts),
                    planned_quantity=sum(r.get("planned_quantity", 0) for r in data["rows"]),
                    plan_quantity_denominator="rolling_suggestions_including_replans; not_unique_orders",
                    cache_hits=sum(r.get("flow_cache", {}).get("hit", False) for r in data["rows"]),
                    policy_decisions=len(data["rows"]))
            row["closure_verified"] = row["status"] == "closed" and not row["closure_errors"] and not row["method_contract_errors"]
            rows.append(row)
    pairs, missing = [], []
    for row in rows:
        reference_method = REFERENCES.get(row["method"])
        if not row["comparison_eligible"]:
            missing.append(dict(task_id=row["task_id"], reference=reference_method,
                reason="training_label_collection_not_a_scientific_comparison"))
            continue
        if reference_method is None:
            continue
        baselines = sorted((r for r in rows if r["parent"] == row["parent"] and r["method"] == reference_method
                            and r["horizon"] == row["horizon"] and r["closure_verified"] and r["comparison_eligible"]),
            key=lambda r: (r["block_path"] != row["block_path"], r["task_id"]))
        allowed = ALLOWED_COMPARISON_DIFFERENCES[row["method"]]
        def same_fixed_contract(candidate):
            return {k: v for k, v in row["comparison_contract"].items() if k not in allowed} == {
                k: v for k, v in candidate["comparison_contract"].items() if k not in allowed}
        # Select by frozen inputs, never by the most favorable realized result.
        baseline = next((r for r in baselines if same_fixed_contract(r)), baselines[0] if baselines else None)
        if baseline and row["closure_verified"] and "system_J" in row:
            left, right = dict(row["comparison_contract"]), dict(baseline["comparison_contract"])
            differences = {key: {"candidate": left.get(key), "reference": right.get(key)}
                for key in sorted(set(left) | set(right)) if left.get(key) != right.get(key)}
            for key in allowed:
                left.pop(key, None); right.pop(key, None)
            if left != right:
                missing.append(dict(task_id=row["task_id"], reference=reference_method, reason="comparison_contract_mismatch",
                    differences=differences, allowed_differences=list(allowed)))
                continue
            pairs.append(dict(parent=row["parent"], method=row["method"], reference=reference_method,
                task_id=row["task_id"], reference_task_id=baseline["task_id"],
                backlog_gain_bag_seconds=baseline["system_J"]-row["system_J"], horizon=row["horizon"],
                allowed_differences=list(allowed), observed_differences=differences))
        else:
            missing.append(dict(task_id=row["task_id"], reference=reference_method, reason="missing_closed_paired_baseline_or_candidate"))
    comparison_rows = [r for r in rows if r["comparison_eligible"] and r["method"] in REFERENCES]
    return dict(schema=SCHEMA+".evaluation", runs=rows, paired=pairs,
        missing_pair_reasons=missing,
        all_registered_closed=bool(rows) and all(r["closure_verified"] for r in rows),
        all_registered_closed_scope="execution closure only; not label validation or scientific comparison completion",
        paired_comparison_complete=bool(comparison_rows) and len(pairs) == len(comparison_rows),
        training_label_collection_runs=sum(not r["comparison_eligible"] for r in rows),
        formal_test_locked=True, strict_per_bag_nonharm_certified=False,
        conclusions=("TRAIN label collection only; no paired service or predictor-quality conclusion"
            if rows and all(not r["comparison_eligible"] for r in rows) else
            "mechanism and development evidence only; no TEST or R1 combination claim"))


def offline_granularity(run_dirs):
    """Isolate 600/near-fine bin effects on saved public opportunities, not service.

    Current snapshots, accepted supply, source menu, 600-second projection,
    command timing and 60-second recomputation stay identical across variants.
    Uncredited cross-owner claims cannot be reconstructed from counts alone;
    those recorded opportunities are excluded explicitly, never set to zero.
    """
    from . import foundation_airport_inventory_rule as r0
    from . import foundation_airport_joint_opportunities as opportunities
    from .foundation_airport_inventory_projection import prepare_inventory_projection, demand_mass
    from .foundation_airport_terminal_forecast import rebin_forecast
    from .foundation_airport_transport_control import TransportPolicy
    modes = ("60", "300", "600", "near_fine")
    totals, sources, examples = Counter(), [], []
    per_mode = {mode: Counter() for mode in modes}
    eta_mass_errors = {mode: [] for mode in modes if mode != "60"}
    for run_dir in run_dirs:
        directory = Path(run_dir)
        plan, receipt = read(directory/"plan.json"), read(directory/"receipt.json")
        if (plan["parent"]["split"] not in ("train", "dev")
                or receipt.get("plan_sha256") != bound(directory/"plan.json")["sha256"]
                or receipt["worker"].get("scientific_status") != "closed"
                or receipt["worker"].get("process_status") != "completed"
                or receipt["process"].get("exitcode") != 0
                or receipt["worker"].get("final_physical_time") != plan["horizon"]):
            raise ValueError("terminal_flow:closed_non_TEST_offline_source_required")
        decisions = read(directory/"decisions.json.gz")
        observations = {row["digest"]: row["observation"] for row in read(directory/"observations.json.gz")}
        support, receipts = read(directory/"arrival_support_contract.json"), read(directory/"arrival_support_receipts.json")
        sources.append({"parent": plan["parent"], "plan": bound(directory/"plan.json"),
            "receipt": bound(directory/"receipt.json"), "decisions": bound(directory/"decisions.json.gz"),
            "observations": bound(directory/"observations.json.gz"),
            "arrival_support_contract": bound(directory/"arrival_support_contract.json")})
        for decision in decisions:
            totals["recorded_decisions"] += 1
            forecast_binding = decision.get("forecast_binding")
            if not forecast_binding or "forecast" not in forecast_binding:
                totals["missing_consumed_forecast"] += 1
                continue
            saved_plan = decision.get("selection", {}).get("flow_plan", {})
            if any(saved_plan.get("receiver_claims_deducted", {}).values()):
                totals["excluded_uncredited_claim_opportunities"] += 1
                continue
            forecast = forecast_binding["forecast"]
            if forecast["bin_edges_seconds"] != bin_edges("60"):
                raise ValueError("terminal_flow:offline_fine_source_required")
            observation = observations[decision["public_observation_ref"]]
            baseline = r0.r0_priority_planner(observation)
            if baseline["intents"]:
                totals["excluded_priority_not_exhausted"] += 1
                continue
            prepared = opportunities.prepare_current(observation, baseline, message_delay=2.)
            catalog = opportunities.build_joint_catalog(prepared)
            totals["replayed_opportunities"] += 1
            selections, projections = {}, {}
            config = saved_plan.get("config", DEFAULT_CONFIG)
            for mode in modes:
                representation = rebin_forecast(forecast, bin_edges_seconds=bin_edges(mode))
                projection = prepare_inventory_projection(observation, forecast=representation,
                    prepared_current=prepared, supply_mode="committed_only", horizon_seconds=600.,
                    arrival_support_contract=support, arrival_support_receipt=receipts[decision["owner_id"]])
                projections[mode] = projection
                selections[mode] = TransportPolicy(config=config, recompute_period_seconds=60.).select(
                    prepared, catalog, projection, policy_state={},
                    decision_context={"decision_id": decision["decision_id"], "tick": 0})
                per_mode[mode]["nonzero_plan_opportunities"] += bool(selections[mode]["flow_plan"]["chosen"])
                per_mode[mode]["selected_transfers"] += selections[mode]["action_id"] != "a_noop"
            reference = selections["60"]
            for mode in modes[1:]:
                choice = selections[mode]
                changed = choice["action_id"] != reference["action_id"]
                per_mode[mode]["first_action_changes_vs_60"] += changed
                per_mode[mode]["quantity_changes_vs_60"] += len(choice["flow_plan"]["chosen"]) != len(reference["flow_plan"]["chosen"])
                if changed and len(examples) < 20:
                    candidates = {row["action_id"]: row for row in catalog["candidates"]}
                    examples.append({"parent": plan["parent"]["parent_seed"], "decision_time": observation["now"],
                        "owner_id": observation["owner_id"], "mode": mode,
                        "reference": {k: candidates[reference["action_id"]][k] for k in ("action_type", "source", "destination", "tray_id")},
                        "alternative": {k: candidates[choice["action_id"]][k] for k in ("action_type", "source", "destination", "tray_id")},
                        "native_service_change_measured": False})
                for node in projections["60"].loaders:
                    for horizon in (600., 1800.):
                        a, b = demand_mass(projections["60"], node, 0., horizon), demand_mass(projections[mode], node, 0., horizon)
                        if a is not None and b is not None and abs(a-b) > 1e-9:
                            raise ValueError("terminal_flow:coarsening_changed_common_horizon_mass")
                od = {}
                for candidate in catalog["candidates"]:
                    if candidate["action_type"] == "transfer":
                        od[candidate["source"], candidate["destination"]] = candidate
                for candidate in od.values():
                    at = min(600., candidate["nominal_arrival_time"]-projection.now)
                    a = demand_mass(projections["60"], candidate["destination"], 0., at)
                    b = demand_mass(projections[mode], candidate["destination"], 0., at)
                    if a is not None and b is not None:
                        eta_mass_errors[mode].append(abs(a-b))
    def summarize(values):
        return dict(count=len(values), mean_absolute_mass_difference=(sum(values)/len(values) if values else None),
            maximum_absolute_mass_difference=max(values, default=None))
    return dict(schema=SCHEMA+".offline_granularity", sources=sources, opportunities=dict(totals),
        modes={mode: dict(value) for mode, value in per_mode.items()},
        eta_cumulative_demand_sensitivity={mode: summarize(values) for mode, values in eta_mass_errors.items()},
        first_action_change_examples=examples, fixed_projection_horizon_seconds=600.,
        fixed_forecast_horizon_seconds=1800., fixed_recompute_period_seconds=60., fixed_command_delay_seconds=2.,
        information="recorded_public_observations_and_consumed_frozen_forecast_only",
        no_finer_CDF_access=True, native_starts=0, native_service_gain_measured=False,
        observations_from_original_policy_not_counterfactual_closed_loop=True,
        repeated_opportunities_not_independent_airport_days=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    p = sub.add_parser("prepare-block")
    p.add_argument("name"); p.add_argument("--phase", choices=tuple(BLOCKS), required=True)
    p.add_argument("--source", type=Path, required=True); p.add_argument("--parents", nargs="+", type=int)
    p.add_argument("--demand-model", type=Path)
    p = sub.add_parser("run-block"); p.add_argument("block", type=Path)
    p = sub.add_parser("evaluate"); p.add_argument("blocks", nargs="+", type=Path); p.add_argument("--output", type=Path)
    p = sub.add_parser("offline-granularity"); p.add_argument("--run-dir", nargs="+", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "status":
        result = budget.status(campaign.CYCLE)
    elif args.command == "prepare-block":
        result = prepare_block(args.name, phase=args.phase, source=args.source,
                               parents=args.parents, demand_model=args.demand_model)
    elif args.command == "run-block":
        result = run_block(args.block)
    elif args.command == "offline-granularity":
        result = offline_granularity(args.run_dir)
        write_once(args.output, result)
    else:
        result = evaluate(args.blocks)
        if args.output:
            write_once(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
