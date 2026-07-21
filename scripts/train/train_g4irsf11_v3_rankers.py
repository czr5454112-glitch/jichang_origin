"""Train G4IRSF11 v3 rankers only after an exact A--H preflight PASS."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from czr005.models.g4irsf11_v3 import (  # noqa: E402
    MODEL_NAMES,
    REQUIRED_STAGE_GATES,
    SPLIT_NAMES,
    TRAINING_STATUS_SCHEMA,
    V3TrainingError,
    load_training_examples,
    preflight_training,
    prepare_dataset,
    sha256_file,
    split_audit_rows,
    train_all_models,
)


DEFAULT_GATE_MANIFEST = ROOT / "artifacts" / "gates" / "g4irsf11_pretraining_gate_manifest.json"
DEFAULT_DECISION_MANIFEST = ROOT / "artifacts" / "datasets" / "g4irsf11_decision_trace_manifest.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "models" / "g4irsf11_v3"
DEFAULT_STATUS = ROOT / "outputs" / "reports" / "g4irsf11_v3_training_status.json"
DEFAULT_SPLIT_AUDIT = ROOT / "outputs" / "tables" / "g4irsf11_v3_grouped_split_audit.csv"


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_split_audit(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "split",
        "train_decisions",
        "test_decisions",
        "train_groups",
        "test_groups",
        "task_repeat_overlap",
        "semantic_duplicate_overlap",
        "heldout",
        "status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            value = dict(row)
            value["heldout"] = json.dumps(value["heldout"], sort_keys=True, separators=(",", ":"))
            writer.writerow(value)


def _command(args: argparse.Namespace) -> str:
    parts = [
        sys.executable,
        _relative(Path(__file__)),
        "--gate-manifest",
        _relative(args.gate_manifest),
        "--decision-manifest",
        _relative(args.decision_manifest),
        "--output-dir",
        _relative(args.output_dir),
        "--status-output",
        _relative(args.status_output),
        "--split-audit-output",
        _relative(args.split_audit_output),
        "--epochs",
        str(args.epochs),
        "--learning-rate",
        str(args.learning_rate),
        "--seed",
        str(args.seed),
    ]
    return " ".join(json.dumps(item) for item in parts)


def _blocked_payload(
    args: argparse.Namespace,
    blockers: list[str] | tuple[str, ...],
    *,
    gate_sha256: str = "",
    decision_sha256: str = "",
    gate_statuses: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "schema": TRAINING_STATUS_SCHEMA,
        "status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "trained": False,
        "models_written": [],
        "required_gates": list(REQUIRED_STAGE_GATES),
        "gate_statuses": dict(gate_statuses or {}),
        "blockers": sorted(set(map(str, blockers))),
        "gate_manifest": {
            "path": _relative(args.gate_manifest),
            "sha256": gate_sha256,
        },
        "decision_manifest": {
            "path": _relative(args.decision_manifest),
            "sha256": decision_sha256,
        },
        "reproduce_command": _command(args),
        "claim_boundary": (
            "No v3 model was trained. A-H and decision-data gates are fail-closed; "
            "a blocker is never replaced by smoke evidence or an assumed PASS."
        ),
    }


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    approval = preflight_training(ROOT, args.gate_manifest, args.decision_manifest)
    if not approval.allowed:
        payload = _blocked_payload(
            args,
            approval.blockers,
            gate_sha256=approval.gate_manifest_sha256,
            decision_sha256=approval.decision_manifest_sha256,
            gate_statuses=approval.gate_statuses,
        )
        _write_json(args.status_output, payload)
        return 2, payload

    try:
        examples = load_training_examples(
            approval.artifacts["hard_case_index"],
            approval.artifacts["outcome_sample"],
        )
        dataset = prepare_dataset(examples, seed=args.seed)
        models, metrics = train_all_models(
            dataset,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            seed=args.seed,
        )
    except (OSError, ValueError, V3TrainingError) as exc:
        payload = _blocked_payload(
            args,
            [f"training dataset/split validation: {exc}"],
            gate_sha256=approval.gate_manifest_sha256,
            decision_sha256=approval.decision_manifest_sha256,
            gate_statuses=approval.gate_statuses,
        )
        _write_json(args.status_output, payload)
        return 2, payload

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_artifacts: dict[str, dict[str, Any]] = {}
    for model_name in MODEL_NAMES:
        path = args.output_dir / f"{model_name}.json"
        _write_json(path, models[model_name])
        model_artifacts[model_name] = {
            "path": _relative(path),
            "sha256": sha256_file(path),
        }
    split_rows = split_audit_rows(dataset)
    _write_split_audit(args.split_audit_output, split_rows)
    payload = {
        "schema": TRAINING_STATUS_SCHEMA,
        "status": "PASS",
        "trained": True,
        "required_gates": list(REQUIRED_STAGE_GATES),
        "gate_statuses": dict(approval.gate_statuses),
        "gate_manifest": {
            "path": _relative(args.gate_manifest),
            "sha256": approval.gate_manifest_sha256,
        },
        "decision_manifest": {
            "path": _relative(args.decision_manifest),
            "sha256": approval.decision_manifest_sha256,
        },
        "dataset_sha256": dataset.dataset_sha256,
        "decision_count": len(dataset.examples),
        "model_artifacts": model_artifacts,
        "split_audit": {
            "path": _relative(args.split_audit_output),
            "sha256": sha256_file(args.split_audit_output),
            "splits": list(SPLIT_NAMES),
            "task_repeat_overlap_max": 0,
            "semantic_duplicate_overlap_max": 0,
        },
        "metrics": metrics,
        "reproduce_command": _command(args),
        "claim_boundary": (
            "Lightweight supervised candidate rankers only. Metrics are grouped offline "
            "evaluation and do not replace event-runtime system A/B, capacity, or fault gates."
        ),
    }
    _write_json(args.status_output, payload)
    return 0, payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train four lightweight G4IRSF11 v3 rankers after strict A-H approval."
    )
    parser.add_argument("--gate-manifest", type=Path, default=DEFAULT_GATE_MANIFEST)
    parser.add_argument("--decision-manifest", type=Path, default=DEFAULT_DECISION_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-output", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--split-audit-output", type=Path, default=DEFAULT_SPLIT_AUDIT)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--learning-rate", type=float, default=0.03)
    parser.add_argument("--seed", type=int, default=11)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code, payload = run(args)
    print(
        "[g4irsf11-v3]",
        f"status={payload['status']}",
        f"trained={str(payload['trained']).lower()}",
        f"models={len(payload.get('model_artifacts', {}))}",
        f"status_output={args.status_output}",
        flush=True,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
