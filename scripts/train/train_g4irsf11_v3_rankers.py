"""Dry-run Gate C, then publish hash-bound G4IRSF11 v3 releases fail-closed."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping
import uuid


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from czr005.models.g4irsf11_v3 import (  # noqa: E402
    ACTIVE_RELEASE_SCHEMA,
    CANONICAL_ACTIVE_RELEASE,
    CANONICAL_DECISION_MANIFEST,
    CANONICAL_GATE_MANIFEST,
    EXACT_BYTES_HASH,
    MODEL_NAMES,
    RELEASE_MANIFEST_SCHEMA,
    REQUIRED_STAGE_GATES,
    SPLIT_NAMES,
    SPLIT_READINESS_SCHEMA,
    SEMANTIC_TEXT_HASH,
    TEXT_ARTIFACT_SUFFIXES,
    TRAINING_STATUS_SCHEMA,
    V3TrainingError,
    build_split_readiness_audit,
    preflight_training,
    raw_sha256_file,
    sha256_file,
    split_audit_rows,
    train_all_models,
    validate_model_payload,
)


DEFAULT_GATE_MANIFEST = ROOT / CANONICAL_GATE_MANIFEST
DEFAULT_DECISION_MANIFEST = ROOT / CANONICAL_DECISION_MANIFEST
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "models" / "g4irsf11_v3"
DEFAULT_ACTIVE_RELEASE = ROOT / CANONICAL_ACTIVE_RELEASE
DEFAULT_STATUS = ROOT / "outputs" / "reports" / "g4irsf11_v3_training_status.json"
DEFAULT_SPLIT_READINESS = ROOT / "outputs" / "reports" / "g4irsf11_v3_split_readiness.json"
DEFAULT_SPLIT_AUDIT = ROOT / "outputs" / "tables" / "g4irsf11_v3_grouped_split_audit.csv"


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(value)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write_bytes(path, _json_bytes(payload))


def _write_immutable_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(value)
    except FileExistsError:
        if path.read_bytes() != value:
            raise V3TrainingError(f"immutable release collision: {path}")


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> None:
    _write_immutable_bytes(path, _json_bytes(payload))


def _descriptor(path: Path, *, row_count: int | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise V3TrainingError(f"published artifact escapes repository: {resolved}")
    result: dict[str, Any] = {
        "path": _relative(resolved),
        "sha256": sha256_file(resolved),
        "hash_semantics": (
            SEMANTIC_TEXT_HASH
            if resolved.suffix.lower() in TEXT_ARTIFACT_SUFFIXES
            else EXACT_BYTES_HASH
        ),
    }
    if row_count is not None:
        result["row_count"] = row_count
    return result


def _split_audit_bytes(rows: list[dict[str, Any]]) -> bytes:
    fieldnames = [
        "split",
        "train_decisions",
        "test_decisions",
        "train_groups",
        "test_groups",
        "task_repeat_overlap",
        "semantic_duplicate_overlap",
        "train_max_event_time",
        "test_min_event_time",
        "chronological_overlap",
        "active_fault_train_decisions",
        "active_fault_test_decisions",
        "heldout",
        "status",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        value = dict(row)
        value["heldout"] = json.dumps(value["heldout"], sort_keys=True, separators=(",", ":"))
        writer.writerow(value)
    return output.getvalue().encode("utf-8")


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
        "--split-readiness-output",
        _relative(args.split_readiness_output),
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


def _manifest_descriptor(path: Path, digest: str) -> dict[str, str]:
    return {
        "path": _relative(path),
        "sha256": digest,
        "hash_semantics": SEMANTIC_TEXT_HASH,
    }


def _blocked_payload(
    args: argparse.Namespace,
    blockers: list[str] | tuple[str, ...],
    *,
    gate_sha256: str = "",
    decision_sha256: str = "",
    gate_statuses: Mapping[str, str] | None = None,
    split_readiness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": TRAINING_STATUS_SCHEMA,
        "status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "trained": False,
        "models_written": [],
        "required_gates": list(REQUIRED_STAGE_GATES),
        "gate_statuses": dict(gate_statuses or {}),
        "blockers": sorted(set(map(str, blockers))),
        "gate_manifest": _manifest_descriptor(args.gate_manifest, gate_sha256),
        "decision_manifest": _manifest_descriptor(args.decision_manifest, decision_sha256),
        "split_readiness": dict(split_readiness or {}),
        "reproduce_command": _command(args),
        "claim_boundary": (
            "No v3 model was trained. A-H, exact-data, and split-readiness gates are "
            "fail-closed; a blocker is never replaced by smoke evidence or assumed PASS."
        ),
    }


def _revoke_active(
    blockers: list[str] | tuple[str, ...],
    *,
    status_descriptor: Mapping[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema": ACTIVE_RELEASE_SCHEMA,
        "status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "release_id": None,
        "active_release": None,
        "blockers": sorted(set(map(str, blockers))),
    }
    if status_descriptor:
        payload["training_status"] = dict(status_descriptor)
    _atomic_write_json(DEFAULT_ACTIVE_RELEASE, payload)


def _persist_blocked(
    args: argparse.Namespace,
    blockers: list[str] | tuple[str, ...],
    *,
    gate_sha256: str,
    decision_sha256: str,
    gate_statuses: Mapping[str, str],
    readiness_descriptor: Mapping[str, Any] | None,
) -> tuple[int, dict[str, Any]]:
    payload = _blocked_payload(
        args,
        blockers,
        gate_sha256=gate_sha256,
        decision_sha256=decision_sha256,
        gate_statuses=gate_statuses,
        split_readiness=readiness_descriptor,
    )
    _atomic_write_json(args.status_output, payload)
    status_descriptor = (
        _descriptor(args.status_output)
        if args.status_output.resolve().is_relative_to(ROOT.resolve())
        else None
    )
    _revoke_active(list(blockers), status_descriptor=status_descriptor)
    return 2, payload


def _partial_readiness(
    decision_sha256: str, blockers: list[str] | tuple[str, ...], seed: int
) -> dict[str, Any]:
    return {
        "schema": SPLIT_READINESS_SCHEMA,
        "status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "model_weights_initialised": False,
        "bindings": {"decision_manifest_sha256": decision_sha256},
        "metrics": {"seed": seed, "input_decision_count": 0},
        "required_splits": list(SPLIT_NAMES),
        "split_statuses": {
            name: "PARTIAL_WITH_EXPLICIT_BLOCKER" for name in SPLIT_NAMES
        },
        "split_audit": [],
        "dataset_sha256": "",
        "blockers": sorted(set(map(str, blockers))),
    }


def _referenced_training_artifacts(
    decision_manifest: Path,
) -> tuple[dict[str, Path], dict[str, Mapping[str, Any]]]:
    """Resolve manifest paths for a negative audit even when a digest is stale."""

    paths: dict[str, Path] = {}
    descriptors: dict[str, Mapping[str, Any]] = {}
    try:
        payload = json.loads(decision_manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return paths, descriptors
    raw = payload.get("artifacts") if isinstance(payload, Mapping) else None
    if not isinstance(raw, Mapping):
        return paths, descriptors
    for name in ("hard_case_index", "outcome_sample"):
        descriptor = raw.get(name)
        if not isinstance(descriptor, Mapping):
            continue
        value = descriptor.get("path")
        if not isinstance(value, str) or not value.strip():
            continue
        candidate = Path(value)
        resolved = candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()
        if resolved.is_relative_to(ROOT.resolve()) and resolved.is_file():
            paths[name] = resolved
            descriptors[name] = descriptor
    return paths, descriptors


def _approved_gate_c_readiness_blockers(
    args: argparse.Namespace,
    recomputed_readiness: Mapping[str, Any],
) -> list[str]:
    """Bind a PASS Gate C to its immutable canonical readiness evidence.

    Once Gate C says PASS, the evidence it approved is an input to training,
    not an output that this invocation may refresh.  In particular, changing
    the split seed must require a new Gate C evaluation instead of silently
    replacing the already-hashed readiness artifact.
    """

    blockers: list[str] = []
    canonical = DEFAULT_SPLIT_READINESS.resolve()
    if args.split_readiness_output.resolve() != canonical:
        blockers.append(
            "Gate C PASS is bound to the canonical split-readiness output; "
            "the requested output path differs"
        )

    try:
        gate = json.loads(args.gate_manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"Gate C PASS manifest could not be re-read: {exc}"] + blockers
    if not isinstance(gate, Mapping):
        return ["Gate C PASS manifest must be a JSON object"] + blockers
    gates = gate.get("gates")
    gate_c = gates.get("C") if isinstance(gates, Mapping) else None
    if not isinstance(gate_c, Mapping) or gate_c.get("status") != "PASS":
        return ["Gate C approval disappeared during readiness lock validation"] + blockers
    evidence = gate_c.get("evidence")
    if not isinstance(evidence, list):
        return ["Gate C PASS has no evidence list"] + blockers

    matching: list[Mapping[str, Any]] = []
    for descriptor in evidence:
        if not isinstance(descriptor, Mapping):
            continue
        value = descriptor.get("path")
        if not isinstance(value, str) or not value.strip():
            continue
        raw = Path(value)
        resolved = raw.resolve() if raw.is_absolute() else (ROOT / raw).resolve()
        if resolved == canonical:
            matching.append(descriptor)
    if len(matching) != 1:
        blockers.append(
            "Gate C PASS must contain exactly one evidence descriptor for the canonical "
            "split-readiness artifact"
        )
        return blockers
    descriptor = matching[0]
    if not canonical.is_file():
        blockers.append("Gate C-approved canonical split-readiness artifact is missing")
        return blockers

    expected_sha = str(descriptor.get("sha256") or "").lower()
    if len(expected_sha) != 64 or any(
        character not in "0123456789abcdef" for character in expected_sha
    ):
        blockers.append("Gate C split-readiness evidence SHA-256 is missing or invalid")
    semantics = descriptor.get("hash_semantics")
    try:
        if semantics in (None, EXACT_BYTES_HASH):
            actual_sha = raw_sha256_file(canonical)
        elif semantics == SEMANTIC_TEXT_HASH:
            actual_sha = sha256_file(canonical)
        else:
            actual_sha = ""
            blockers.append("Gate C split-readiness evidence hash semantics are unsupported")
    except OSError as exc:
        blockers.append(f"Gate C-approved split readiness could not be hashed: {exc}")
        return blockers
    if expected_sha and actual_sha != expected_sha:
        blockers.append(
            "Gate C split-readiness evidence SHA-256 does not match the current canonical artifact"
        )

    expected_content = _json_bytes(recomputed_readiness)
    try:
        current_content = canonical.read_bytes()
        current_payload = json.loads(current_content.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"Gate C-approved split readiness could not be read exactly: {exc}")
        return blockers
    if not isinstance(current_payload, Mapping) or dict(current_payload) != dict(
        recomputed_readiness
    ):
        blockers.append(
            "Gate C-approved split readiness differs from the newly recomputed readiness"
        )
    if current_content != expected_content:
        blockers.append(
            "Gate C-approved split readiness is not the exact canonical encoding of the "
            "newly recomputed readiness"
        )
    return blockers


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    # Revoke first.  A crash or failed revalidation must never leave yesterday's
    # mutable active pointer consumable while a new publication is attempted.
    _revoke_active(["v3 release validation/training is in progress"])
    approval = preflight_training(ROOT, args.gate_manifest, args.decision_manifest)
    blockers = list(approval.blockers)
    if args.gate_manifest.resolve() != DEFAULT_GATE_MANIFEST.resolve():
        blockers.append("gate manifest is not the canonical current manifest")
    if args.decision_manifest.resolve() != DEFAULT_DECISION_MANIFEST.resolve():
        blockers.append("decision manifest is not the canonical current manifest")
    for path, label in (
        (args.output_dir, "output directory"),
        (args.status_output, "status output"),
        (args.split_readiness_output, "split-readiness output"),
        (args.split_audit_output, "split-audit output"),
    ):
        if not path.resolve().is_relative_to(ROOT.resolve()):
            blockers.append(f"{label} escapes repository")

    readiness_dataset = None
    referenced_paths, manifest_descriptors = _referenced_training_artifacts(
        args.decision_manifest
    )
    audit_paths = dict(referenced_paths)
    audit_paths.update(approval.artifacts)
    if {"hard_case_index", "outcome_sample"}.issubset(audit_paths):
        try:
            readiness, readiness_dataset = build_split_readiness_audit(
                audit_paths["hard_case_index"],
                audit_paths["outcome_sample"],
                decision_manifest_sha256=approval.decision_manifest_sha256,
                seed=args.seed,
            )
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
            readiness = _partial_readiness(
                approval.decision_manifest_sha256,
                [f"split readiness could not be generated: {exc}"],
                args.seed,
            )
    else:
        readiness = _partial_readiness(
            approval.decision_manifest_sha256,
            ["exact hard-case/outcome artifacts are unavailable after manifest verification"],
            args.seed,
        )
    readiness["manifest_artifact_descriptors"] = {
        name: dict(descriptor) for name, descriptor in manifest_descriptors.items()
    }
    readiness_blockers = list(map(str, readiness.get("blockers") or []))
    readiness_bindings = readiness.get("bindings")
    for name, expected in manifest_descriptors.items():
        actual = (
            readiness_bindings.get(name)
            if isinstance(readiness_bindings, Mapping)
            else None
        )
        if not isinstance(actual, Mapping) or (
            str(actual.get("sha256") or "").lower()
            != str(expected.get("sha256") or "").lower()
        ):
            readiness_blockers.append(
                f"{name}: current artifact SHA does not match its decision-manifest descriptor"
            )
    if readiness_blockers:
        readiness["status"] = "PARTIAL_WITH_EXPLICIT_BLOCKER"
        readiness["blockers"] = sorted(set(readiness_blockers))
        readiness_dataset = None
    gate_statuses = dict(approval.gate_statuses)
    if gate_statuses.get("C") == "PASS":
        # A PASS Gate C has already approved and hashed this exact artifact.
        # Revalidate it, but never mutate it from inside the training attempt.
        blockers.extend(_approved_gate_c_readiness_blockers(args, readiness))
        readiness_descriptor = (
            _descriptor(args.split_readiness_output)
            if args.split_readiness_output.resolve().is_file()
            and args.split_readiness_output.resolve().is_relative_to(ROOT.resolve())
            else None
        )
    else:
        # A non-PASS Gate C may receive a fresh no-weights dry-run artifact so
        # the next independent gate evaluation can approve (or reject) it.
        _atomic_write_json(args.split_readiness_output, readiness)
        readiness_descriptor = _descriptor(args.split_readiness_output)
    if readiness.get("status") != "PASS" or readiness_dataset is None:
        gate_statuses["C"] = "PARTIAL_WITH_EXPLICIT_BLOCKER"
        blockers.extend(map(str, readiness.get("blockers") or ["split readiness is not PASS"]))
    if blockers:
        return _persist_blocked(
            args,
            blockers,
            gate_sha256=approval.gate_manifest_sha256,
            decision_sha256=approval.decision_manifest_sha256,
            gate_statuses=gate_statuses,
            readiness_descriptor=readiness_descriptor,
        )

    dataset = readiness_dataset
    assert dataset is not None
    try:
        models, metrics = train_all_models(
            dataset,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            seed=args.seed,
        )
        release_seed = {
            "gate_manifest_sha256": approval.gate_manifest_sha256,
            "decision_manifest_sha256": approval.decision_manifest_sha256,
            "split_readiness_sha256": readiness_descriptor["sha256"],
            "dataset_sha256": dataset.dataset_sha256,
            "epochs": args.epochs,
            "learning_rate": args.learning_rate,
            "seed": args.seed,
            "model_implementation_sha256": sha256_file(
                ROOT / "src" / "czr005" / "models" / "g4irsf11_v3.py"
            ),
            "trainer_sha256": sha256_file(Path(__file__)),
        }
        release_id = hashlib.sha256(
            json.dumps(release_seed, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()[:32]
        binding = {
            "release_id": release_id,
            "gate_manifest_sha256": approval.gate_manifest_sha256,
            "decision_manifest_sha256": approval.decision_manifest_sha256,
            "split_readiness_sha256": readiness_descriptor["sha256"],
            "dataset_sha256": dataset.dataset_sha256,
        }
        release_dir = args.output_dir / "releases" / release_id
        immutable_readiness = release_dir / "split_readiness.json"
        _write_immutable_json(immutable_readiness, readiness)
        split_rows = split_audit_rows(dataset)
        split_bytes = _split_audit_bytes(split_rows)
        _atomic_write_bytes(args.split_audit_output, split_bytes)
        immutable_split = release_dir / "grouped_split_audit.csv"
        _write_immutable_bytes(immutable_split, split_bytes)
        model_artifacts: dict[str, dict[str, Any]] = {}
        for model_name in MODEL_NAMES:
            model = dict(models[model_name])
            model["release_binding"] = binding
            validate_model_payload(model, expected_release_binding=binding)
            path = release_dir / f"{model_name}.json"
            _write_immutable_json(path, model)
            model_artifacts[model_name] = _descriptor(path)
        release_manifest = {
            "schema": RELEASE_MANIFEST_SCHEMA,
            "status": "PASS",
            "release_id": release_id,
            "release_binding": binding,
            "gate_manifest": _descriptor(args.gate_manifest),
            "decision_manifest": _descriptor(args.decision_manifest),
            "split_readiness": _descriptor(immutable_readiness),
            "split_audit": _descriptor(immutable_split, row_count=len(split_rows)),
            "model_artifacts": model_artifacts,
            "training": release_seed,
        }
        release_manifest_path = release_dir / "release_manifest.json"
        _write_immutable_json(release_manifest_path, release_manifest)
        release_manifest_descriptor = _descriptor(release_manifest_path)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        return _persist_blocked(
            args,
            [f"training/release publication: {exc}"],
            gate_sha256=approval.gate_manifest_sha256,
            decision_sha256=approval.decision_manifest_sha256,
            gate_statuses=gate_statuses,
            readiness_descriptor=readiness_descriptor,
        )

    payload = {
        "schema": TRAINING_STATUS_SCHEMA,
        "status": "PASS",
        "trained": True,
        "release_id": release_id,
        "release_binding": binding,
        "required_gates": list(REQUIRED_STAGE_GATES),
        "gate_statuses": gate_statuses,
        "gate_manifest": _descriptor(args.gate_manifest),
        "decision_manifest": _descriptor(args.decision_manifest),
        "split_readiness": _descriptor(immutable_readiness),
        "release_manifest": release_manifest_descriptor,
        "dataset_sha256": dataset.dataset_sha256,
        "decision_count": len(dataset.examples),
        "data_role_audit": {
            "ranker_eligible_decisions": sum(
                len(example.candidate_nodes) >= 2 for example in dataset.examples
            ),
            "rank_supervised_decisions": sum(
                example.target_index is not None for example in dataset.examples
            ),
            "risk_head_only_single_candidate_decisions": sum(
                len(example.candidate_nodes) == 1 for example in dataset.examples
            ),
            "single_candidate_policy": (
                "retained for risk-head supervision; excluded from ranker labels and metrics"
            ),
        },
        "model_artifacts": model_artifacts,
        "split_audit": _descriptor(immutable_split, row_count=len(split_rows)),
        "metrics": metrics,
        "reproduce_command": _command(args),
        "claim_boundary": (
            "Lightweight supervised candidate rankers only. Grouped offline metrics do not "
            "replace event-runtime system A/B, capacity, or fault gates."
        ),
    }
    _atomic_write_json(args.status_output, payload)
    active = {
        "schema": ACTIVE_RELEASE_SCHEMA,
        "status": "PASS",
        "release_id": release_id,
        "gate_manifest": _descriptor(args.gate_manifest),
        "decision_manifest": _descriptor(args.decision_manifest),
        "training_status": _descriptor(args.status_output),
        "release_manifest": release_manifest_descriptor,
    }
    # The single mutable production pointer is switched only after every
    # immutable artifact and the current PASS status are durably present.
    _atomic_write_json(DEFAULT_ACTIVE_RELEASE, active)
    return 0, payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run Gate C and train four v3 rankers after strict A-H approval."
    )
    parser.add_argument("--gate-manifest", type=Path, default=DEFAULT_GATE_MANIFEST)
    parser.add_argument("--decision-manifest", type=Path, default=DEFAULT_DECISION_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-output", type=Path, default=DEFAULT_STATUS)
    parser.add_argument(
        "--split-readiness-output", type=Path, default=DEFAULT_SPLIT_READINESS
    )
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
