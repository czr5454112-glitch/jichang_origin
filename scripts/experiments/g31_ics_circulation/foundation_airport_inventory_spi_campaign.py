"""Finite, source-frozen inventory/SPI experiment with one shared source bundle."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import secrets
import shutil
import sys
import threading
import time
import traceback

from . import foundation_airport_action_campaign as common
from .foundation_airport_batch_patch import digest
from .foundation_airport_evidence_export import write_gzip_json

ROOT = Path(__file__).resolve().parents[3]
CYCLE = ROOT / "outputs/experiments/g31_ics_inventory_spi_20261020/cycle_001"
MODULE = "scripts.experiments.g31_ics_circulation.foundation_airport_inventory_spi_campaign"
PI0 = "airport_common_inventory_pi0_v1"
SCHEMA = "g31.inventory_spi_native_campaign.v1"
METHODS = ("R0_current_stock_v1", "C00", "C10", "C01", "C11")
SOURCE_PLAN = Path("outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/"
                   "B1_training_001/public/static_flight_plan.json")
LOCK = threading.Lock()


def bound(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": common.sha(path)}


def read_bound(ref):
    if common.sha(ref["path"]) != ref["sha256"]:
        raise ValueError("inventory_spi:bound_file_changed:" + ref["path"])
    return common.read(ref["path"])


class JsonArrayStream:
    """Persist evaluator records incrementally without retaining a full day."""

    def __init__(self, path):
        self.raw = Path(path).open("xb")
        self.stream = gzip.GzipFile(fileobj=self.raw, mode="wb", compresslevel=1, mtime=0)
        self.stream.write(b"[")
        self.count = 0
        self.closed = False

    def extend(self, records):
        if self.closed:
            raise ValueError("inventory_spi:closed_evidence_stream")
        for record in records:
            encoded = json.dumps(record, separators=(",", ":"), allow_nan=False).encode()
            if self.count:
                self.stream.write(b",")
            self.stream.write(encoded)
            self.count += 1
        self.stream.flush()

    def close(self):
        if not self.closed:
            self.stream.write(b"]\n")
            self.stream.close()
            self.raw.close()
            self.closed = True


def freeze_sources(name):
    directory = CYCLE / "sources" / name
    if directory.exists():
        raise ValueError("inventory_spi:fresh_source_bundle")
    from .foundation_airport_campaign import source_dependency_closure
    files = sorted(set([*ROOT.joinpath("scripts/experiments/g31_ics_circulation").glob("*.py"),
                        *source_dependency_closure(roots=(MODULE,)).values(),
                        *ROOT.joinpath("src").rglob("*.py"), ROOT / SOURCE_PLAN]))
    pins = {}
    for path in files:
        relative = path.relative_to(ROOT)
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        pins[relative.as_posix()] = common.sha(target)
    manifest = {"schema": SCHEMA + ".sources", "root": str(directory),
                "files": pins, "source_manifest_sha256": digest(pins),
                "private_future_tapes_in_source_bundle": False}
    common.write(directory / "source_manifest.json", manifest)
    return bound(directory / "source_manifest.json")


def controller(*, method, recovery=True):
    options = dict(common.CONTROLLER, inventory_snapshots=True,
        inventory_snapshot_validity=120., inventory_snapshot_refresh_period=60.,
        recover_failed_empty=recovery, _consume_state=True)
    if method == "R0_current_stock_v1":
        options.update(stock_return=True, stock_return_activate_at=7200.,
                       actual_only_activate_at=7200.)
    return options


def validate_formal_unlock(reference):
    """Validate bound selections before even reading a cached held-out input."""
    if not reference or not {"path", "sha256"} <= set(reference):
        raise ValueError("inventory_spi:bound_formal_unlock_required")
    unlocked = read_bound(reference)
    if (unlocked.get("schema") != SCHEMA + ".formal_unlock"
            or unlocked.get("status") != "all_champions_frozen_test_unlocked"
            or unlocked.get("test_parent_ids") != list(range(1301, 1309))):
        raise ValueError("inventory_spi:formal_unlock_contract")
    from .foundation_airport_pair_training_campaign import validate_spi_freeze
    from .foundation_airport_spi_rule_selection import validate_rule_selection
    frozen = validate_spi_freeze(unlocked["spi_freeze"])
    validate_rule_selection(unlocked["rule"])
    for key in ("source_bundle", "native_acceptance", "preregistration"):
        read_bound(unlocked[key])
    collection = read_bound(unlocked["round1_collection"])
    if (collection.get("batch") != "pi1_train_dev_pairs"
            or collection.get("registered_pairs") != 12
            or collection.get("registered_arms") != 24
            or collection.get("closed_attempt_receipts") != 24):
        raise ValueError("inventory_spi:second_round_collection_before_test")
    models = {r["information_variant"]: r["checkpoint"] for r in frozen["models"]}
    if unlocked.get("models") != models:
        raise ValueError("inventory_spi:unlocked_champions_match_selection")
    return unlocked


def _method_dependencies(method, *, pair, model, rule):
    if pair is None and method in ("C01", "C11") and model is None:
        raise ValueError("inventory_spi:explicit_frozen_model_required")
    if pair is None and method == "C10" and rule is None:
        raise ValueError("inventory_spi:explicit_frozen_rule_required")


def materialize_parent(seed, *, rollout_round=0, fleet=22, unlock=None, global_event_budget=750000):
    unlocked = validate_formal_unlock(unlock) if seed in range(1301, 1309) else None
    directory = CYCLE / "parents" / f"P{seed}_r{rollout_round}_N{fleet}_E{global_event_budget}"
    if directory.exists():
        return common.read(directory / "parent.json"), bound(directory / "input.json")
    if seed in (901, 902):
        data, parent = common.parent_input(seed, fleet)
        generation = {"schema": SCHEMA + ".old_diagnostic_parent",
                      "never_new_heldout_evidence": True, "parent": parent}
    else:
        from .foundation_airport_spi_parents import make_parent
        if fleet != 22:
            raise ValueError("inventory_spi:resource_curve_not_unlocked")
        data, parent, generation = make_parent(seed, rollout_round=rollout_round, formal_unlock=unlocked)
    # Shared initial cap. Any calibration must be separately registered before
    # all new paired/formal runs; a budget stop is never a successful endpoint.
    data["options"]["max_events"] = global_event_budget
    directory.mkdir(parents=True)
    common.write(directory / "input.json", data)
    common.write(directory / "parent.json", parent)
    common.gz(directory / "offline_generation.json.gz", generation)
    return parent, bound(directory / "input.json")


def prepare(name, *, binary, source_bundle, native_acceptance, seed, method="C00",
            batch, fleet=22, recovery=True, rollout_round=0, pair=None,
            model=None, behavior_model=None, rule=None, unlock=None,
            global_event_budget=750000, soft_seconds=1200., hard_seconds=1260.,
            calibration=None):
    if method not in METHODS:
        raise ValueError("inventory_spi:registered_method")
    _method_dependencies(method, pair=pair, model=model, rule=rule)
    directory = CYCLE / "runs" / name
    if directory.exists():
        raise ValueError("inventory_spi:fresh_attempt_directory")
    acceptance = read_bound(native_acceptance)
    if (acceptance.get("schema") != "g31.native030.inventory_spi_accepted_contract.v1"
            or acceptance.get("status") != "passed_with_retained_fixture_failure"
            or common.sha(binary) != acceptance["binary"]["sha256"]):
        raise ValueError("inventory_spi:accepted_binary_required")
    source = read_bound(source_bundle)
    if not all(math.isfinite(x) for x in (soft_seconds, hard_seconds)) or not 0 < soft_seconds < hard_seconds:
        raise ValueError("inventory_spi:finite_ordered_wall_limits")
    if global_event_budget != 750000 or (soft_seconds, hard_seconds) != (1200., 1260.):
        calibrated = read_bound(calibration)
        if (calibrated["global_event_budget"] != global_event_budget
                or not calibrated["before_first_training_pair"]
                or calibrated.get("soft_seconds") != soft_seconds
                or calibrated.get("hard_seconds") != hard_seconds):
            raise ValueError("inventory_spi:explicit_pretraining_budget_calibration")
    if behavior_model:
        behavior = read_bound(behavior_model)
        if behavior["information_variant"] != "C01":
            raise ValueError("inventory_spi:second_round_behavior_must_not_import_plan_information")
        if behavior["contract"]["policy_alignment"]["continuation_policy_id"] != PI0:
            raise ValueError("inventory_spi:first_round_behavior_contract")
    if model:
        selected = read_bound(model)
        if (selected["information_variant"] != method
                or selected["contract"]["policy_alignment"]["continuation_policy_id"] != PI0):
            raise ValueError("inventory_spi:formal_first_round_model_contract")
    if seed in range(1301, 1309):
        unlocked = validate_formal_unlock(unlock)
        if (pair is not None or rollout_round != 0 or not recovery
                or source_bundle != unlocked["source_bundle"]
                or native_acceptance != unlocked["native_acceptance"]
                or method in ("C01", "C11") and model != unlocked["models"][method]
                or method == "C10" and rule != unlocked["rule"]):
            raise ValueError("inventory_spi:formal_frozen_deployment_contract")
    parent, input_ref = materialize_parent(seed, rollout_round=rollout_round, fleet=fleet,
        unlock=unlock, global_event_budget=global_event_budget)
    directory.mkdir(parents=True)
    forecast_ref = None
    if pair is not None or method in ("C10", "C11"):
        from .foundation_airport_calendar_forecast import load_calendar_binding
        common.write(directory / "calendar_binding.json", load_calendar_binding(parent))
        forecast_ref = bound(directory / "calendar_binding.json")
    horizon = pair["window"][1] + 1800. if pair else 59400.
    plan = {"schema": SCHEMA, "name": name, "batch": batch, "cycle": str(CYCLE),
            "output": str(directory), "parent": parent, "input": input_ref,
            "input_semantic_sha256": digest(read_bound(input_ref)),
            "binary": bound(binary), "native_acceptance": native_acceptance,
            "source_bundle": source_bundle, "source_manifest_sha256": source["source_manifest_sha256"],
            "forecast_binding": forecast_ref, "method": method, "pair": pair,
            "model": model, "behavior_model": behavior_model, "rule": rule,
            "formal_unlock": unlock,
            "controller": controller(method=method, recovery=recovery),
            "controller_identity": PI0, "activate_at": 7200., "horizon": horizon,
            "cost_window": [7200., 59400.] if not pair else None,
            "soft_seconds": soft_seconds, "hard_seconds": hard_seconds, "event_budget": 100000,
            "global_event_budget": global_event_budget, "event_calibration": calibration,
            "K_max": 13, "P_per_root": 2,
            "strict_per_job_nonharm_certified": False,
            "old_parent_diagnostic_only": seed in (901, 902)}
    common.write(directory / "plan.json", plan)
    return directory


def verify(plan):
    _method_dependencies(plan["method"], pair=plan["pair"], model=plan["model"], rule=plan["rule"])
    for key in ("input", "native_acceptance", "source_bundle"):
        read_bound(plan[key])
    if common.sha(plan["binary"]["path"]) != plan["binary"]["sha256"]:
        raise ValueError("inventory_spi:binary_changed")
    for key in ("forecast_binding", "model", "behavior_model", "rule", "event_calibration"):
        if plan.get(key):
            read_bound(plan[key])
    source = read_bound(plan["source_bundle"])
    if source["source_manifest_sha256"] != digest(source["files"]):
        raise ValueError("inventory_spi:source_manifest_identity")
    for relative, expected in source["files"].items():
        if common.sha(Path(source["root"]) / relative) != expected:
            raise ValueError("inventory_spi:frozen_source_changed:" + relative)
    if plan["parent"].get("parent_seed") in range(1301, 1309):
        unlocked = validate_formal_unlock(plan.get("formal_unlock"))
        if (plan["source_bundle"] != unlocked["source_bundle"]
                or plan["native_acceptance"] != unlocked["native_acceptance"]
                or plan["method"] in ("C01", "C11") and plan["model"] != unlocked["models"][plan["method"]]
                or plan["method"] == "C10" and plan["rule"] != unlocked["rule"]):
            raise ValueError("inventory_spi:formal_plan_selection_binding")


def _make_planners(plan, forecast_at, sink):
    from .analytic_control import transfer_candidates
    from .foundation_airport_prospective_control import make_prospective_planner, make_ranker_planner
    shared = dict(parent=plan["parent"], activate_at=7200., continuation_version=PI0,
                  k_max=13, record_sink=sink, retain_records=False, capture_all_callbacks=True)
    if plan["pair"]:
        from .foundation_airport_paired_continuation import make_paired_planner
        spec = plan["pair"]
        base = transfer_candidates
        if plan["behavior_model"]:
            base = make_ranker_planner(read_bound(plan["behavior_model"]), **shared)
        paired = make_paired_planner(base, branch=spec["branch"], window=spec["window"],
            parent=plan["parent"], continuation_version=spec["policy_alignment"]["continuation_policy_id"],
            anchor_rank=spec["anchor_rank"], patch_rank=spec["patch_rank"], k_max=13,
            policy_alignment=spec["policy_alignment"])
        return paired, paired
    if plan["method"] == "R0_current_stock_v1":
        from .foundation_airport_inventory_rule import make_r0_priority_planner
        return make_r0_priority_planner(activate_at=7200.), None
    if plan["method"] in ("C01", "C11"):
        return make_ranker_planner(read_bound(plan["model"]), forecast_at=forecast_at, **shared), None
    rule = read_bound(plan["rule"]) if plan["rule"] else {"selected": "reference"}
    reference = plan["method"] == "C00" or rule["selected"] == "reference"
    selector = None
    if not reference:
        from .foundation_airport_strong_rule import explain_pair
        weight = rule["forecast_weight"]
        selector = lambda a, b: explain_pair(a, b, forecast_weight=weight)["predicted_patch_advantage"]
    return make_prospective_planner(information_variant=plan["method"],
        policy_id=digest(rule) + ":" + plan["method"], selector=selector,
        forecast_at=forecast_at, reference_champion=reference,
        score_all_candidates=True,
        deployment_contract={"max_policy_replacements": 1, "continuation_policy_id": PI0,
                             "label_horizon_seconds": 1800.}, **shared), None


def worker(plan_path, expected):
    from .native_host import load_native
    from .foundation_airport_protocol_v2 import run_airport_bounded_protocol_control
    from .foundation_airport_calendar_forecast import record_controller_preload
    from .foundation_airport_calendar_prepared import prepare_forecast_provider
    from .foundation_airport_prospective_campaign import AuditStream, indexed_execution
    from .foundation_airport_pair_dataset import branch_evidence, window_cost
    plan = common.read(plan_path)
    output = Path(plan["output"])
    report = {"schema": SCHEMA, "status": "failed_before_native", "native_constructor_attempts": 0}
    began = time.monotonic()
    audit = None
    evidence_streams = {}
    try:
        if common.sha(plan_path) != expected:
            raise ValueError("inventory_spi:plan_changed")
        verify(plan)
        data = read_bound(plan["input"])
        binding = read_bound(plan["forecast_binding"]) if plan["forecast_binding"] else None
        owners = sorted({r["resource_owner"] for r in data["node_contracts"]})
        report["native_constructor_attempts"] = 1
        session = load_native(plan["binary"]["path"]).NativeSession(data)
        receipts = record_controller_preload(binding, session, owners=owners) if binding else {}
        common.write(output / "actual_plan_preload_receipts.json", receipts)
        forecast_at = prepare_forecast_provider(binding, receipts) if binding else None
        audit = AuditStream(output / "callback_audit.jsonl.gz")
        evidence_streams = {name: JsonArrayStream(output / (name + ".json.gz"))
                            for name in ("control_records", "inventory_snapshot_reads")}
        pending_record = {}

        def capture(record):
            pending_record.clear()
            pending_record.update(record)

        planner, paired = _make_planners(plan, forecast_at, capture)
        first_prefix, warmup_prefix = None, None
        observed_counts = Counter()

        def tick_start(**kwargs):
            nonlocal warmup_prefix
            if warmup_prefix is None and kwargs["tick_at"] == 7200.:
                state = {**kwargs["controller_state"], "client": kwargs["client_state"]}
                neutral = copy.deepcopy(state)
                for key in ("stock_return", "stock_return_activate_at", "actual_only_activate_at"):
                    neutral["config"].pop(key, None)
                warmup_prefix = {"native_state_sha256": session.offline_state_sha256(),
                    "controller_history_sha256": digest(neutral),
                    "raw_controller_state_sha256": digest(state),
                    "at": 7200.,
                    "stage": "closed_timestamp_before_refresh_and_any_current_tick_publication",
                    "only_ignored_config_fields": ["stock_return", "stock_return_activate_at", "actual_only_activate_at"]}
                common.gz(output / "warmup_prefix.json.gz", {
                    "prefix": warmup_prefix, "controller_state": state})

        def precommit(**kwargs):
            nonlocal first_prefix
            observation, decision = kwargs["observation"], kwargs["decision"]
            controller_state = {**kwargs["controller_state"], "client": kwargs["client_state"]}
            if first_prefix is None and observation["now"] >= 7200.:
                first_prefix = {"native_state_sha256": session.offline_state_sha256(),
                    "controller_state_sha256": digest(controller_state),
                    "public_state_digest": digest(observation),
                    "observed_at": observation["now"], "owner_id": observation["owner_id"]}
                common.gz(output / "activation_prefix.json.gz", {
                    "prefix": first_prefix, "controller_state": controller_state,
                    "observation": observation, "preload_receipts": receipts})
            if paired is not None and paired.needs_prefix:
                paired.bind_prefix(native_state_sha256=session.offline_state_sha256(),
                    controller_state=controller_state, observation=observation)
                row = paired.selected if observation["now"] == paired.selected["observed_at"] else paired.successor
                row["forecast_evidence"] = forecast_at(observation=observation, parent=plan["parent"])
            record = dict(pending_record) if pending_record.get("observation") is observation else {}
            if not record:
                record = {"owner_id": observation["owner_id"], "observed_at": observation["now"],
                          "status": "actual_protocol_precommit", "selected_action_id": "a_ref",
                          "planning_wall_ms": 0., "planning_timing_not_captured_here": True,
                          "baseline_decision": decision, "chosen_decision": decision,
                          "observation": observation}
            record["protocol_phase"] = "inventory_return" if decision.get("inventory_return") else "priority"
            audit(record)
            observed_counts[record["status"]] += 1
            pending_record.clear()

        state, calls = None, []
        final = None
        target = min(3600., plan["horizon"])
        progress_path = output / "progress.jsonl"
        with progress_path.open("x", encoding="utf-8") as progress:
            while True:
                run = run_airport_bounded_protocol_control(session, owners, horizon=target, state=state,
                    event_budget=plan["event_budget"], planner=planner,
                    planner_identity=plan["controller_identity"], precommit_observer=precommit,
                    tick_start_observer=tick_start,
                    soft_deadline=began + plan["soft_seconds"], **plan["controller"])
                state = run["controller_state"]
                calls.extend(run["client_calls"])
                for name, stream in evidence_streams.items():
                    stream.extend(run.get(name, []))
                if run["result"] is not None:
                    final = run["result"]
                row = {"target": target, "at": session.physical_time, "status": run["status"],
                       "elapsed": time.monotonic() - began}
                progress.write(json.dumps(row) + "\n")
                progress.flush()
                if run["status"] != "reached":
                    report["status"] = "censored_" + run["status"]
                    break
                endpoint = paired.label_end if paired is not None and paired.label_end is not None else plan["horizon"]
                if session.physical_time >= endpoint:
                    report["status"] = ("no_eligible_opportunity" if paired is not None and paired.selected is None
                                        else "complete")
                    break
                target = min(target + 3600., endpoint)
                if paired is not None and paired.selected is None and target > paired.window[0]:
                    target = min(target, max(session.physical_time + 60., paired.window[0]))
        audit.close()
        for stream in evidence_streams.values():
            stream.close()
        exports = {}
        exports["controller_final_state"] = write_gzip_json(
            output / "controller_final_state.json.gz", state)
        # The complete state is now closed on disk. Drop both owning references
        # before materializing the native ACK history; later evaluators use only
        # calls, final, planner traces, and the delivered ACK views.
        state = None
        run = None
        ack_views = {owner: session.observe_protocol(owner) for owner in owners}
        for name, value in (("client_calls", calls), ("final_result", final), ("ack_views", ack_views)):
            exports[name] = write_gzip_json(output / (name + ".json.gz"), value)
        report["complete_evidence_exports"] = exports
        report["controller_released_before_ack_observation"] = True
        common.write(output / "callback_audit_receipt.json", audit.report())
        if final is not None:
            common.gz(output / "execution_evidence.json.gz", indexed_execution(audit.index, final, calls, ack_views))
        if paired is not None:
            common.gz(output / "pair_trace.json.gz", paired.report())
            evidence = branch_evidence(data=data, planner_report=paired.report(), result=final,
                client_calls=calls, delivered_ack_views=ack_views, stop_reason=report["status"],
                input_sha256=plan["input_semantic_sha256"])
            common.gz(output / "branch_evidence.json.gz", evidence)
        elif hasattr(planner, "report"):
            common.write(output / "planner_summary.json", planner.report())
        cost = (window_cost(data, final, start=7200., end=59400.)
                if report["status"] == "complete" and paired is None else None)
        common.write(output / "evaluation.json", {"schema": SCHEMA, "status": report["status"],
            "method": plan["method"], "parent": plan["parent"], "cost": cost,
            "activation_prefix": first_prefix, "warmup_prefix": warmup_prefix,
            "input_semantic_sha256": plan["input_semantic_sha256"],
            "strict_nonharm_certified": False, "incomplete_endpoint_has_advantage": False})
        report.update(final_physical_time=session.physical_time, cost=cost,
            summary=common.summary(data, final, final["physical_clock"]) if final else None,
            activation_prefix=first_prefix, warmup_prefix=warmup_prefix,
            observed_callback_counts=dict(observed_counts),
            final_native_state_sha256=session.offline_state_sha256())
        verify(plan)
    except Exception:
        report.update(status="failed", exception=traceback.format_exc())
        if audit is not None and not audit.raw.closed:
            audit.close()
    for stream in evidence_streams.values():
        stream.close()
    report["streamed_evaluator_records"] = {name: stream.count for name, stream in evidence_streams.items()}
    report["wall_seconds"] = time.monotonic() - began
    import psutil
    process = psutil.Process()
    memory, cpu, io = process.memory_info(), process.cpu_times(), process.io_counters()
    report["process_resources"] = {
        "cpu_seconds": cpu.user + cpu.system,
        "peak_working_set_bytes": getattr(memory, "peak_wset", memory.rss),
        "read_bytes": io.read_bytes, "write_bytes": io.write_bytes,
        "includes_offline_audit_io": True}
    common.write(output / "worker_report.json", report)
    return report


def launch(directory):
    from .bounded_windows_job import run
    directory = Path(directory).resolve()
    plan = common.read(directory / "plan.json")
    verify(plan)
    cycle = Path(plan["cycle"])
    budget = common.read(cycle / "campaign_budget.json")
    with LOCK:
        records = [json.loads(line) for line in (cycle / "native_attempts.jsonl").read_text().splitlines()]
        attempts = [r for r in records if r["kind"] == "long_branch"]
        age = datetime.now(timezone.utc) - datetime.fromisoformat(budget["created_at_utc"])
        remaining = budget["wall_hours_limit"] * 3600 - age.total_seconds()
        if len(attempts) >= budget["long_branch_limit"] or remaining < plan["hard_seconds"]:
            raise ValueError("inventory_spi:finite_budget_exhausted")
        if any(r["name"] == plan["name"] for r in attempts) or (directory / "receipt.json").exists():
            raise ValueError("inventory_spi:no_silent_relaunch")
        same_batch = sum(r.get("batch") == plan["batch"] for r in attempts)
        if same_batch >= budget["long_allocations"][plan["batch"]]:
            raise ValueError("inventory_spi:batch_budget_exhausted")
        admission = secrets.token_hex(24)
        plan_sha = common.sha(directory / "plan.json")
        with (cycle / "native_attempts.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"kind": "long_branch", "name": plan["name"], "batch": plan["batch"],
                "owner": "root", "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "plan_sha256": plan_sha, "binary_sha256": plan["binary"]["sha256"]}) + "\n")
    source = read_bound(plan["source_bundle"])
    with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
        process = run([sys.executable, "-m", MODULE, "--worker", str(directory / "plan.json"),
            "--expected", plan_sha, "--admission", admission], timeout=plan["hard_seconds"],
            stdout=stdout, stderr=stderr, admission=admission, cwd=source["root"])
    path = directory / "worker_report.json"
    report = common.read(path) if path.exists() else {"status": "unknown_hard_stop"}
    common.write(directory / "receipt.json", {"schema": SCHEMA, "status": report["status"],
        "process": process, "worker": report, "plan_sha256": plan_sha})
    return {"name": plan["name"], "status": report["status"],
            "wall_seconds": process["wall_seconds"], "summary": report.get("summary"),
            "exception": report.get("exception")}


def execute(paths, *, concurrency=2):
    if concurrency not in (1, 2):
        raise ValueError("inventory_spi:at_most_two_native")
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        work = {pool.submit(launch, path): path for path in paths}
        for future in as_completed(work):
            print(json.dumps(future.result()), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--expected")
    parser.add_argument("--admission")
    args = parser.parse_args()
    if not args.worker or not args.admission or sys.stdin.readline().strip() != args.admission:
        raise SystemExit("inventory_spi:parent_admission_required")
    worker(args.worker, args.expected)


if __name__ == "__main__":
    main()
