"""Bounded, discoverable entry points for the G31 foundation learning pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import time
import traceback


ROOT = Path(__file__).resolve().parents[3]
MODULE = "scripts.experiments.g31_ics_circulation.run_learning_pipeline"
SCHEMA = "g31.foundation_learning.pilot.v1"
ADMISSION = "g31_foundation_learning_worker_v1"
COMMANDS = ("smoke", "baseline", "collect", "train-ranker", "train-later-value", "train-rl", "evaluate")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_input(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def validate_config(config):
    if config.get("schema") != SCHEMA:
        raise ValueError("foundation_pipeline:unsupported_config_schema")
    if config.get("runtime_mode") != "offline_sync":
        raise ValueError("foundation_pipeline:only_declared_offline_sync_is_implemented")
    if config.get("information_scope") != "owner_local_delivered":
        raise ValueError("foundation_pipeline:owner_local_information_required")
    if config.get("baseline") != "retained_incumbent_04" or config.get("scenario") not in (
            "mechanism", "no_overlap", "insufficient_advance"):
        raise ValueError("foundation_pipeline:unsupported_baseline_or_scenario")
    if config.get("horizon_seconds") != 40 or config.get("message_tape") != "normal":
        raise ValueError("foundation_pipeline:only_registered_H40_normal_domain")
    if config.get("refresh", {}).get("implemented_mode") != "retained_initial_reference":
        raise ValueError("foundation_pipeline:refresh_modes_not_yet_implemented")
    if config.get("compute_delay_mode") != "offline_sync_no_realtime_claim":
        raise ValueError("foundation_pipeline:delay_mode_not_yet_implemented")
    expected_contract = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014/native027_accepted_contract_001.json"
    if resolve_input(config.get("native_contract", "")) != expected_contract.resolve():
        raise ValueError("foundation_pipeline:only_registered_native027_contract")
    protection = config.get("protection", {})
    if protection.get("tolerance") != 0 or protection.get("incumbent_index") != 4:
        raise ValueError("foundation_pipeline:unchanged_strict_reference_required")
    budget = config.get("candidate_budget")
    if type(budget) is not int or not 1 <= budget <= 32:
        raise ValueError("foundation_pipeline:candidate_budget_out_of_range")
    if config.get("complete_request_target_ms") != 100:
        raise ValueError("foundation_pipeline:historical_100ms_target_unchanged")
    limits = config.get("limits", {})
    for field in ("command_wall_seconds", "training_wall_seconds"):
        value = limits.get(field)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 7200:
            raise ValueError("foundation_pipeline:invalid_" + field)
    for field in ("maximum_training_rows", "maximum_transitions"):
        value = limits.get(field)
        if type(value) is not int or not 0 < value <= 20000:
            raise ValueError("foundation_pipeline:invalid_" + field)
    learner = config.get("learner", {})
    if config.get("pipeline_stage") == "later_value":
        if learner.get("models") != ["ridge_continuation_value"] or learner.get("device") != "cpu" or learner.get("alpha") != 1:
            raise ValueError("foundation_pipeline:registered_later_value_learner_required")
    else:
        if learner.get("models") != ["linear", "mlp"] or learner.get("device") != "cpu":
            raise ValueError("foundation_pipeline:registered_cpu_linear_and_mlp_required")
        if learner.get("hidden_width") != 64 or learner.get("hidden_layers") != 2:
            raise ValueError("foundation_pipeline:registered_MLP_shape_required")
        if type(learner.get("epochs")) is not int or not 1 <= learner["epochs"] <= 1000:
            raise ValueError("foundation_pipeline:invalid_epochs")
    if type(learner.get("seed")) is not int or learner["seed"] < 0:
        raise ValueError("foundation_pipeline:invalid_seed")
    output = resolve_input(config["output_root"])
    if not output.is_relative_to(ROOT) or output == ROOT:
        raise ValueError("foundation_pipeline:output_must_be_inside_research_workspace")
    run_id = config.get("run_id", "")
    if not run_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in run_id):
        raise ValueError("foundation_pipeline:invalid_run_id")
    return config


def load_config(path):
    return validate_config(read_json(path))


def registered_config(path, output, command):
    registration = read_json(Path(output) / "preregistered.json")
    if registration["command"] != command or hashlib.sha256(Path(path).read_bytes()).hexdigest() != registration["config_sha256"]:
        raise ValueError("foundation_pipeline:configuration_changed_after_registration")
    return validate_config(registration["config"])


def _stage_directory(config, name):
    run = resolve_input(config["output_root"]) / config["run_id"]
    direct = run / name
    if direct.exists():
        return direct
    receipt = run / "smoke" / "receipt.json"
    if receipt.is_file() and read_json(receipt).get("status") == "completed_first_round_smoke":
        return run / "smoke" / name
    return direct


def _dataset_path(config, explicit=None):
    if explicit:
        return resolve_input(explicit)
    manifest = _stage_directory(config, "collect") / "manifest.json"
    if not manifest.is_file():
        raise ValueError("foundation_pipeline:run_collect_first_or_supply_dataset")
    return Path(read_json(manifest)["dataset_path"]).resolve(strict=True)


def _check_dataset_budget(path, limit):
    count = 0
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                count += 1
            if count > limit:
                raise ValueError("foundation_pipeline:training_row_budget_exceeded")
    if count == 0:
        raise ValueError("foundation_pipeline:empty_training_dataset")
    return count


def collect(config, output):
    from .foundation_learning_data import export_saved_smoke

    result = export_saved_smoke(resolve_input(config["saved_campaign"]), Path(output) / "data")
    count = _check_dataset_budget(result["dataset_path"], config["limits"]["maximum_training_rows"])
    write_json(Path(output) / "manifest.json", result)
    return {"status": "completed", "stage": "L0_saved_data_only", "training_rows": count, "manifest": result}


def train_ranker(config, output, dataset=None):
    from .foundation_ranker import train_rankers

    dataset_path = _dataset_path(config, dataset)
    count = _check_dataset_budget(dataset_path, config["limits"]["maximum_training_rows"])
    report = train_rankers(dataset_path, Path(output) / "models", seed=config["learner"]["seed"],
        epochs=config["learner"]["epochs"], max_wall_seconds=config["limits"]["training_wall_seconds"])
    return {"status": "completed", "stage": "L0_ranking_smoke_only", "training_rows": count,
        "dataset_path": str(dataset_path), "report": report, "closed_loop_RL_trained": False}


def train_later_value(config, output, dataset=None):
    from . import foundation_later_learning as learning

    if not dataset:
        raise ValueError("foundation_pipeline:later_native_episode_manifest_required")
    manifest = resolve_input(dataset)
    rows, sources = learning.load_manifest(manifest, config["limits"]["maximum_training_rows"])
    report = learning.train(rows, Path(output) / "models", max_wall_seconds=config["limits"]["training_wall_seconds"])
    write_json(Path(output) / "episode_sources.json", sources)
    return {"status": "completed", "stage": "later_actual_native_supervised_value_only",
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "training_rows": len(rows), "report": report, "closed_loop_RL_trained": False,
        "scope": "New real later trajectories, not the old initial ranking table or protected RL takeover."}


def baseline(config, output):
    from .foundation_native_environment import run_baseline

    report = run_baseline(Path(output) / "native", case=config["scenario"], method="incumbent")
    completed = (report.get("status") == "assessed"
        and report.get("run_acceptance_status") == "closed_run_acceptance_passed"
        and report.get("saved_baseline_comparison", {}).get("all_fields_exact") is True)
    return {"status": "completed" if completed else "unknown_native_baseline", "report": report,
        "scope": "Retained-policy native lifecycle, not newly learned later R1/R2 choices.", "L1_certified": False}


def rl_readiness(config):
    return {"status": "blocked_L1_not_certified", "training_started": False,
        "runtime_mode": config["runtime_mode"], "L1_certified": False,
        "missing_capabilities": [
            "Current-event observations and genuinely new guarded R1/R2 choices after the initial decision.",
            "Paired native multi-step transitions across repeated tray reuse, not initial-only clone evaluations.",
            "A validated learner integration through the existing protection and native submission chain."],
        "scope": "The ranking smoke and retained-policy baseline do not authorize closed-loop RL or learned takeover.",
        "complete_request_100ms_certified": False}


def execute(command, config, output, *, dataset=None, model_dir=None):
    output = Path(output)
    if config.get("pipeline_stage") == "later_value" and command not in ("train-later-value", "train-rl"):
        raise ValueError("foundation_pipeline:later_value_config_command_scope")
    if command == "collect":
        return collect(config, output)
    if command == "train-ranker":
        return train_ranker(config, output, dataset)
    if command == "train-later-value":
        return train_later_value(config, output, dataset)
    if command == "baseline":
        return baseline(config, output)
    if command == "train-rl":
        if config.get("pipeline_stage") == "later_value":
            from . import foundation_later_learning as learning

            if not dataset:
                raise ValueError("foundation_pipeline:later_native_episode_manifest_required")
            rows, _ = learning.load_manifest(resolve_input(dataset), config["limits"]["maximum_training_rows"])
            return learning.rl_support(rows)
        return rl_readiness(config)
    if command == "evaluate":
        from .foundation_ranker import evaluate_models

        dataset_path = _dataset_path(config, dataset)
        _check_dataset_budget(dataset_path, config["limits"]["maximum_training_rows"])
        models = resolve_input(model_dir) if model_dir else _stage_directory(config, "train-ranker") / "models"
        return {"status": "completed", "report": evaluate_models(dataset_path, models),
            "scope": "Replay of held-out scenario ranking, not a new independent dataset or native takeover."}
    if command == "smoke":
        outcomes = {}
        for name, action in (("baseline", lambda: baseline(config, output / "baseline")),
                             ("collect", lambda: collect(config, output / "collect"))):
            try:
                outcomes[name] = action()
            except Exception as error:
                outcomes[name] = {"status": "failed", "error": str(error), "traceback": traceback.format_exc()}
            write_json(output / "partial.json", outcomes)
        if outcomes["collect"].get("status") == "completed":
            dataset_path = outcomes["collect"]["manifest"]["dataset_path"]
            try:
                outcomes["train-ranker"] = train_ranker(config, output / "train-ranker", dataset_path)
            except Exception as error:
                outcomes["train-ranker"] = {"status": "failed", "error": str(error), "traceback": traceback.format_exc()}
        outcomes["train-rl"] = rl_readiness(config)
        passed = all(outcomes.get(name, {}).get("status") == "completed" for name in ("baseline", "collect", "train-ranker"))
        return {"status": "completed_first_round_smoke" if passed else "partial_failure", "stages": outcomes,
            "full_plan_complete": False, "L1_certified": False, "complete_request_100ms_certified": False}
    raise ValueError("foundation_pipeline:unknown_command")


def _source_snapshot():
    paths = sorted(Path(__file__).parent.glob("foundation_*.py")) + [Path(__file__)]
    return {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def aggregate_result(process, result):
    if process.get("status") != "exited":
        return "unknown_process_" + str(process.get("status"))
    if process.get("exitcode") != 0:
        if process.get("exitcode") == 1 and isinstance(result, dict) and result.get("status") in ("failed", "partial_failure"):
            return result["status"]
        return "unknown_process_exited"
    if not isinstance(result, dict):
        return "unknown_missing_result"
    return result.get("status", "unknown_missing_status")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset", help="Initial JSONL, or a closed native episode manifest for train-later-value.")
    parser.add_argument("--model-dir", help="Explicit trained fold models directory for evaluate.")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        if sys.stdin.readline().strip() != ADMISSION or args.output is None:
            raise RuntimeError("foundation_pipeline:worker_requires_bounded_parent")
        started = time.perf_counter()
        cpu_started = time.process_time()
        try:
            config = registered_config(args.config, args.output, args.command)
            result = execute(args.command, config, args.output, dataset=args.dataset, model_dir=args.model_dir)
        except Exception as error:
            result = {"status": "failed", "error_type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc()}
        result["worker_wall_seconds"] = time.perf_counter() - started
        result["worker_cpu_seconds"] = time.process_time() - cpu_started
        result["source_sha256_after"] = _source_snapshot()
        write_json(args.output / "result.json", result)
        return 0 if result["status"] in ("completed", "completed_first_round_smoke", "blocked_L1_not_certified") else 1
    config = load_config(args.config)
    if os.name != "nt":
        raise RuntimeError("foundation_pipeline:current_hard_bounded_launcher_requires_Windows")
    from .bounded_windows_job import run

    output = resolve_input(config["output_root"]) / config["run_id"] / args.command
    output.mkdir(parents=True, exist_ok=False)
    before = _source_snapshot()
    config_sha256 = hashlib.sha256(args.config.read_bytes()).hexdigest()
    write_json(output / "preregistered.json", {"schema": SCHEMA, "command": args.command, "config": config,
        "config_path": str(args.config.resolve()), "config_sha256": config_sha256,
        "dataset_argument": args.dataset, "model_dir_argument": args.model_dir, "source_sha256_before": before,
        "python": sys.version, "platform": platform.platform(), "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(), "clock_scope": "Full child lifecycle, separately from worker wall and CPU.",
        "source_scope": "Foundation Python sources only; native and dataset identities are recorded by their stages."})
    command = [sys.executable, "-m", MODULE, args.command, "--config", str(args.config.resolve()),
        "--worker", "--output", str(output)]
    for name, value in (("--dataset", args.dataset), ("--model-dir", args.model_dir)):
        if value:
            command.extend((name, str(resolve_input(value))))
    with (output / "stdout.log").open("w", encoding="utf-8") as stdout, (output / "stderr.log").open("w", encoding="utf-8") as stderr:
        process = run(command, timeout=config["limits"]["command_wall_seconds"], stdout=stdout,
            stderr=stderr, admission=ADMISSION, cwd=ROOT)
    write_json(output / "process.json", process)
    result_path = output / "result.json"
    result = read_json(result_path) if result_path.exists() else None
    status = aggregate_result(process, result)
    after = _source_snapshot()
    source_unchanged = before == after and (result is None or result.get("source_sha256_after") == before)
    if not source_unchanged:
        status = "unknown_source_changed"
    config_unchanged = args.config.is_file() and hashlib.sha256(args.config.read_bytes()).hexdigest() == config_sha256
    if not config_unchanged:
        status = "unknown_configuration_changed"
    receipt = {"status": status, "process": process, "output_dir": str(output),
        "source_unchanged": source_unchanged, "config_unchanged": config_unchanged, "full_plan_complete": False,
        "complete_request_100ms_certified": False}
    write_json(output / "receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, allow_nan=False))
    return 0 if status in ("completed", "completed_first_round_smoke") else 2


if __name__ == "__main__":
    raise SystemExit(main())
