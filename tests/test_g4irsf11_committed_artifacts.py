from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.eval.validate_g4irsf11_committed_artifacts import ROOT, validate_committed_artifacts
from scripts.eval.run_g4irsf11_decision_trace_sampling import _sha256 as manifest_sha256


def test_repository_decision_artifacts_pass_hash_and_semantic_validation() -> None:
    result = validate_committed_artifacts(ROOT)
    assert result["status"] == "PASS", result["failures"]
    assert result["validated_decision_count"] > 0
    assert result["validated_decision_count"] == result["validated_outcome_count"]


def test_changed_artifact_hash_fails_closed(tmp_path: Path) -> None:
    # Copy only the committed artifact graph addressed by the manifest; map2 is
    # shared read-only to keep this corruption test compact.
    manifest_source = ROOT / "artifacts" / "datasets" / "g4irsf11_decision_trace_manifest.json"
    manifest = json.loads(manifest_source.read_text(encoding="utf-8"))
    for descriptor in manifest["artifacts"].values():
        source = ROOT / descriptor["path"]
        target = tmp_path / descriptor["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    target_manifest = tmp_path / "artifacts" / "datasets" / manifest_source.name
    target_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(manifest_source, target_manifest)
    trace_path = tmp_path / manifest["artifacts"]["trace_sample"]["path"]
    trace_path.write_text(trace_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = validate_committed_artifacts(tmp_path)
    assert result["status"] == "FAIL"
    assert any("SHA-256 mismatch" in failure for failure in result["failures"])


def test_manifest_text_hash_is_cross_platform_newline_stable(tmp_path: Path) -> None:
    lf = tmp_path / "lf.jsonl"
    crlf = tmp_path / "crlf.jsonl"
    lf.write_bytes(b'{"a":1}\n{"b":2}\n')
    crlf.write_bytes(b'{"a":1}\r\n{"b":2}\r\n')
    assert manifest_sha256(lf) == manifest_sha256(crlf)


def test_changed_trace_map_identity_fails_even_when_descriptor_hash_is_updated(
    tmp_path: Path,
) -> None:
    manifest_source = ROOT / "artifacts" / "datasets" / "g4irsf11_decision_trace_manifest.json"
    manifest = json.loads(manifest_source.read_text(encoding="utf-8"))
    for descriptor in manifest["artifacts"].values():
        source = ROOT / descriptor["path"]
        target = tmp_path / descriptor["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    target_manifest = tmp_path / "artifacts" / "datasets" / manifest_source.name
    target_manifest.parent.mkdir(parents=True, exist_ok=True)
    trace_path = tmp_path / manifest["artifacts"]["trace_sample"]["path"]
    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line]
    rows[0]["metadata"]["canonical_map_sha256"] = "0" * 64
    trace_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest["artifacts"]["trace_sample"]["sha256"] = manifest_sha256(trace_path)
    target_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_committed_artifacts(tmp_path)

    assert result["status"] == "FAIL"
    assert any("canonical fixed-map metadata" in failure for failure in result["failures"])


def test_manifest_cannot_omit_the_required_artifact_set(tmp_path: Path) -> None:
    manifest_source = ROOT / "artifacts" / "datasets" / "g4irsf11_decision_trace_manifest.json"
    manifest = json.loads(manifest_source.read_text(encoding="utf-8"))
    manifest["artifacts"] = {}
    target = tmp_path / "artifacts" / "datasets" / manifest_source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_committed_artifacts(tmp_path, require_completion=False)

    assert result["status"] == "FAIL"
    assert any("exact required set" in failure for failure in result["failures"])


def test_manifest_artifact_path_cannot_escape_repository_root(tmp_path: Path) -> None:
    manifest_source = ROOT / "artifacts" / "datasets" / "g4irsf11_decision_trace_manifest.json"
    manifest = json.loads(manifest_source.read_text(encoding="utf-8"))
    manifest["artifacts"]["schema"]["path"] = "../outside.json"
    target = tmp_path / "artifacts" / "datasets" / manifest_source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_committed_artifacts(tmp_path, require_completion=False)

    assert result["status"] == "FAIL"
    assert any("escapes the repository root" in failure for failure in result["failures"])
