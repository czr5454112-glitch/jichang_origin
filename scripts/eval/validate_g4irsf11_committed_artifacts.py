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


MANIFEST = ROOT / "artifacts" / "datasets" / "g4irsf11_decision_trace_manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
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


def validate_committed_artifacts(root: Path = ROOT) -> dict[str, Any]:
    manifest_path = root / MANIFEST.relative_to(ROOT)
    manifest = _object(manifest_path)
    failures: list[str] = []
    if manifest.get("schema_id") != SCHEMA_ID:
        failures.append("decision manifest schema_id is unexpected")
    for section in ("validation", "coverage", "trace_completeness"):
        value = manifest.get(section)
        if not isinstance(value, Mapping) or value.get("status") != "PASS":
            failures.append(f"manifest {section}.status is not PASS")
    if manifest.get("sampling_minimum_quota_status") != "PASS":
        failures.append("sampling minimum quota status is not PASS")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("manifest artifacts section must be an object")
    checked = 0
    for name, descriptor in artifacts.items():
        if not isinstance(descriptor, Mapping):
            failures.append(f"artifact descriptor {name} is not an object")
            continue
        relative = str(descriptor.get("path") or "")
        path = root / relative
        if not relative or not path.is_file():
            failures.append(f"artifact {name} is missing: {relative}")
            continue
        expected_hash = str(descriptor.get("sha256") or "")
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            failures.append(f"artifact {name} SHA-256 mismatch")
        if "row_count" in descriptor:
            actual_count = _row_count(path)
            if actual_count != int(descriptor["row_count"]):
                failures.append(f"artifact {name} row_count mismatch")
        checked += 1

    schema_path = root / str(artifacts.get("schema", {}).get("path", ""))
    if schema_path.is_file() and _object(schema_path) != decision_trace_schema():
        failures.append("committed decision schema differs from executable schema")
    sample_path = root / str(artifacts.get("trace_sample", {}).get("path", ""))
    outcome_path = root / str(artifacts.get("outcome_sample", {}).get("path", ""))
    map_path = root / "data" / "processed" / "maps" / "map2.json"
    validated: list[dict[str, Any]] = []
    if sample_path.is_file() and map_path.is_file():
        try:
            validated = validate_decision_rows(
                load_jsonl(sample_path),
                load_adjacency(map_path),
                require_all_outgoing=True,
            )
        except ValueError as exc:
            failures.append(f"decision sample semantic validation failed: {exc}")
    outcomes = load_jsonl(outcome_path) if outcome_path.is_file() else []
    decision_ids = [str(row["decision_id"]) for row in validated]
    outcome_ids = [str(row.get("decision_id", "")) for row in outcomes]
    if (
        len(set(decision_ids)) != len(decision_ids)
        or len(set(outcome_ids)) != len(outcome_ids)
        or set(decision_ids) != set(outcome_ids)
    ):
        failures.append("trace and outcome sample decision-ID populations differ or contain duplicates")
    sample_count = int((manifest.get("sampling") or {}).get("sample_count", -1))
    if len(validated) != sample_count:
        failures.append("validated decision count differs from manifest sample_count")

    lineage_path = root / str(artifacts.get("feature_lineage_table", {}).get("path", ""))
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


def main() -> int:
    result = validate_committed_artifacts(ROOT)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
