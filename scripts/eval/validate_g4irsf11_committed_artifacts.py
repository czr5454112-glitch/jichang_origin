"""Validate committed G4IRSF11 decision artifacts, hashes, and semantics."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from czr005.datasets.decision_trace import (  # noqa: E402
    SCHEMA_ID,
    decision_trace_schema,
    load_adjacency,
    load_jsonl,
    validate_decision_rows,
    validate_feature_lineage,
)
from scripts.eval.g4irsf11_fixed_map import (  # noqa: E402
    CANONICAL_MAP_HASH_SEMANTICS,
    CANONICAL_MAP_PATH,
    CANONICAL_MAP_RELATIVE_PATH,
    CANONICAL_MAP_SHA256,
    assert_canonical_map,
)


MANIFEST = ROOT / "artifacts" / "datasets" / "g4irsf11_decision_trace_manifest.json"
REQUIRED_ARTIFACT_PATHS = {
    "schema": "artifacts/datasets/g4irsf11_decision_trace_schema.json",
    "trace_sample": "artifacts/datasets/g4irsf11_decision_trace_sample.jsonl",
    "outcome_sample": "artifacts/datasets/g4irsf11_decision_outcome_sample.jsonl",
    "hard_case_index": "outputs/tables/g4irsf11_stratified_hard_case_index.csv",
    "sampling_balance": "outputs/tables/g4irsf11_sampling_balance.csv",
    "sampling_report": "outputs/reports/g4irsf11_sampling_balance_report.md",
    "feature_lineage_table": "outputs/tables/g4irsf11_feature_lineage_audit.csv",
    "feature_lineage_report": "outputs/reports/g4irsf11_feature_lineage_audit.md",
    "source_release_mapping": "outputs/tables/g4irsf11_source_release_decision_mapping.csv",
    "source_identity_table": "outputs/tables/g4irsf11_source_identity_audit.csv",
    "source_identity_report": "outputs/reports/g4irsf11_source_identity_audit.md",
}
ROW_COUNT_ARTIFACTS = {
    "trace_sample",
    "outcome_sample",
    "hard_case_index",
    "sampling_balance",
    "feature_lineage_table",
    "source_release_mapping",
    "source_identity_table",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    payload = path.read_bytes()
    if path.suffix.lower() in {".csv", ".json", ".jsonl", ".md", ".py", ".txt", ".yml", ".yaml"}:
        payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    digest.update(payload)
    return digest.hexdigest()


def _row_count(path: Path) -> int:
    if path.suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            return sum(bool(line.strip()) for line in handle)
    if path.suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    raise ValueError(f"row_count is unsupported for {path}")


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _validate_committed_artifacts_unlocked(
    root: Path = ROOT,
    *,
    canonical_map_path: Path = CANONICAL_MAP_PATH,
    require_completion: bool = True,
) -> dict[str, Any]:
    canonical_path = assert_canonical_map(canonical_map_path)
    manifest_path = root / MANIFEST.relative_to(ROOT)
    manifest = _object(manifest_path)
    failures: list[str] = []
    completion: dict[str, Any] = {}
    if require_completion:
        from scripts.eval.run_g4irsf11_event_runtime_evaluation import (
            FORMAL_COMPLETION_PATH,
            formal_completion_validation_errors,
        )

        failures.extend(
            f"formal completion: {failure}"
            for failure in formal_completion_validation_errors(root)
        )
        completion_path = root / FORMAL_COMPLETION_PATH.relative_to(ROOT)
        if completion_path.is_file():
            try:
                completion = _object(completion_path)
            except (OSError, TypeError, ValueError):
                completion = {}
    if manifest.get("schema_id") != SCHEMA_ID:
        failures.append("decision manifest schema_id is unexpected")
    if manifest.get("artifact_hash_semantics") != (
        "sha256 of UTF-8 text after CRLF/CR newline normalization to LF"
    ):
        failures.append("artifact hash semantics are missing or unexpected")
    for section in ("validation", "coverage", "trace_completeness"):
        value = manifest.get(section)
        if not isinstance(value, Mapping) or value.get("status") != "PASS":
            failures.append(f"manifest {section}.status is not PASS")
    if manifest.get("sampling_minimum_quota_status") != "PASS":
        failures.append("sampling minimum quota status is not PASS")
    if manifest.get("fixed_real_map_only") is not True:
        failures.append("decision manifest fixed_real_map_only is not true")
    producer = manifest.get("producer")
    if not isinstance(producer, Mapping) or producer.get("scope") != "formal":
        failures.append("decision manifest producer is not the formal cohort")
    if require_completion and producer != completion.get("producer"):
        failures.append("decision manifest producer differs from formal completion")
    if manifest.get("canonical_map_sha256") != CANONICAL_MAP_SHA256:
        failures.append("decision manifest canonical_map_sha256 is not canonical map2")
    graph = manifest.get("graph") if isinstance(manifest.get("graph"), Mapping) else {}
    if graph.get("path") != CANONICAL_MAP_RELATIVE_PATH.as_posix():
        failures.append("decision manifest graph.path is not canonical map2")
    if graph.get("sha256") != CANONICAL_MAP_SHA256:
        failures.append("decision manifest graph.sha256 is not canonical map2")
    if graph.get("sha256_semantics") != CANONICAL_MAP_HASH_SEMANTICS:
        failures.append("decision manifest graph.sha256_semantics is not canonical")
    if graph.get("fixed_real_map_only") is not True:
        failures.append("decision manifest graph fixed_real_map_only is not true")
    if graph.get("topology_mutation_allowed") is not False:
        failures.append("decision manifest permits topology mutation")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("manifest artifacts section must be an object")
    if set(artifacts) != set(REQUIRED_ARTIFACT_PATHS):
        failures.append("manifest artifact name set is not the exact required set")
    checked = 0
    resolved_artifacts: dict[str, Path] = {}
    resolved_root = root.resolve()
    for name, required_relative in REQUIRED_ARTIFACT_PATHS.items():
        descriptor = artifacts.get(name)
        if not isinstance(descriptor, Mapping):
            failures.append(f"artifact descriptor {name} is not an object")
            continue
        relative = str(descriptor.get("path") or "")
        if relative != required_relative:
            failures.append(
                f"artifact {name} path is not the exact required path: {relative}"
            )
        relative_path = Path(relative)
        if relative_path.is_absolute():
            failures.append(f"artifact {name} path must be repository-relative")
            continue
        path = (resolved_root / relative_path).resolve()
        if not path.is_relative_to(resolved_root):
            failures.append(f"artifact {name} path escapes the repository root")
            continue
        if relative != required_relative:
            continue
        resolved_artifacts[name] = path
        if not path.is_file():
            failures.append(f"artifact {name} is missing: {required_relative}")
            continue
        expected_hash = str(descriptor.get("sha256") or "")
        try:
            actual_hash = _sha256(path)
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(
                f"artifact {name} cannot be hashed: {type(exc).__name__}: {exc}"
            )
            continue
        if actual_hash != expected_hash:
            failures.append(f"artifact {name} SHA-256 mismatch")
        if name in ROW_COUNT_ARTIFACTS and "row_count" not in descriptor:
            failures.append(f"artifact {name} row_count is missing")
        elif "row_count" in descriptor:
            declared_count = descriptor["row_count"]
            if (
                isinstance(declared_count, bool)
                or not isinstance(declared_count, int)
                or declared_count <= 0
                or (name == "source_identity_table" and declared_count != 1)
            ):
                failures.append(f"artifact {name} row_count is not a valid positive integer")
                continue
            try:
                actual_count = _row_count(path)
            except (OSError, UnicodeError, ValueError) as exc:
                failures.append(
                    f"artifact {name} row_count cannot be read: {type(exc).__name__}: {exc}"
                )
                continue
            if actual_count != declared_count:
                failures.append(f"artifact {name} row_count mismatch")
        checked += 1

    schema_path = resolved_artifacts.get("schema", root / "__missing_schema__")
    if schema_path.is_file() and _object(schema_path) != decision_trace_schema():
        failures.append("committed decision schema differs from executable schema")
    sample_path = resolved_artifacts.get("trace_sample", root / "__missing_trace__")
    outcome_path = resolved_artifacts.get("outcome_sample", root / "__missing_outcomes__")
    validated: list[dict[str, Any]] = []
    if sample_path.is_file():
        try:
            validated = validate_decision_rows(
                load_jsonl(sample_path),
                load_adjacency(canonical_path),
                require_all_outgoing=True,
            )
        except ValueError as exc:
            failures.append(f"decision sample semantic validation failed: {exc}")
    outcomes = load_jsonl(outcome_path) if outcome_path.is_file() else []
    invalid_map_metadata = sum(
        1
        for row in validated
        if not isinstance(row.get("metadata"), Mapping)
        or row["metadata"].get("fixed_real_map_only") is not True
        or row["metadata"].get("canonical_map_sha256") != CANONICAL_MAP_SHA256
    )
    if invalid_map_metadata:
        failures.append(
            f"{invalid_map_metadata} decision sample rows lack canonical fixed-map metadata"
        )
    decision_ids = [str(row["decision_id"]) for row in validated]
    outcome_ids = [str(row.get("decision_id", "")) for row in outcomes]
    if (
        len(set(decision_ids)) != len(decision_ids)
        or len(set(outcome_ids)) != len(outcome_ids)
        or set(decision_ids) != set(outcome_ids)
    ):
        failures.append("trace and outcome sample decision-ID populations differ or contain duplicates")
    sampling = manifest.get("sampling") if isinstance(manifest.get("sampling"), Mapping) else {}
    sample_count_value = sampling.get("sample_count")
    if (
        isinstance(sample_count_value, bool)
        or not isinstance(sample_count_value, int)
        or sample_count_value <= 0
    ):
        failures.append("manifest sampling.sample_count is not a positive integer")
        sample_count = -1
    else:
        sample_count = sample_count_value
    if len(validated) != sample_count:
        failures.append("validated decision count differs from manifest sample_count")
    for name in ("trace_sample", "outcome_sample", "hard_case_index"):
        descriptor = artifacts.get(name)
        if isinstance(descriptor, Mapping) and descriptor.get("row_count") != sample_count:
            failures.append(f"artifact {name} row_count differs from manifest sample_count")

    lineage_path = resolved_artifacts.get(
        "feature_lineage_table", root / "__missing_lineage__"
    )
    if lineage_path.is_file():
        try:
            with lineage_path.open("r", encoding="utf-8-sig", newline="") as handle:
                lineage_rows: list[dict[str, Any]] = []
                for raw in csv.DictReader(handle):
                    row: dict[str, Any] = dict(raw)
                    row["sources"] = json.loads(str(row.get("sources") or "[]"))
                    for field in (
                        "available_at_decision",
                        "model_input_allowed",
                        "prohibited_as_runtime_feature",
                    ):
                        row[field] = str(row.get(field, "")).strip().lower() == "true"
                    lineage_rows.append(row)
                validate_feature_lineage(lineage_rows)
        except ValueError as exc:
            failures.append(f"feature lineage validation failed: {exc}")
    return {
        "status": "PASS" if not failures else "FAIL",
        "manifest": manifest_path.relative_to(root).as_posix(),
        "artifact_descriptor_count": len(artifacts),
        "artifact_checked_count": checked,
        "validated_decision_count": len(validated),
        "validated_outcome_count": len(outcomes),
        "failures": failures,
    }


def validate_committed_artifacts(
    root: Path = ROOT,
    *,
    canonical_map_path: Path = CANONICAL_MAP_PATH,
    require_completion: bool = True,
) -> dict[str, Any]:
    if not require_completion:
        return _validate_committed_artifacts_unlocked(
            root,
            canonical_map_path=canonical_map_path,
            require_completion=False,
        )
    from scripts.eval.run_g4irsf11_event_runtime_evaluation import (
        CONSOLIDATION_LOCK,
        ROOT as RUNNER_ROOT,
        _acquire_case_lock,
        _release_case_lock,
    )

    lock_path = root / CONSOLIDATION_LOCK.relative_to(RUNNER_ROOT)
    token = _acquire_case_lock(
        lock_path,
        "committed_artifact_reader_snapshot",
        wait_seconds=60.0,
    )
    if token is None:
        return {
            "status": "FAIL",
            "manifest": MANIFEST.relative_to(ROOT).as_posix(),
            "artifact_descriptor_count": 0,
            "artifact_checked_count": 0,
            "validated_decision_count": 0,
            "validated_outcome_count": 0,
            "failures": [
                "formal publication is being consolidated; no stable reader snapshot was available"
            ],
        }
    try:
        return _validate_committed_artifacts_unlocked(
            root,
            canonical_map_path=canonical_map_path,
            require_completion=True,
        )
    finally:
        _release_case_lock(token)


def main() -> int:
    result = validate_committed_artifacts(ROOT)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
