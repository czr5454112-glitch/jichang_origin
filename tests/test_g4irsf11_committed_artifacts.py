from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.eval.validate_g4irsf11_committed_artifacts import ROOT, validate_committed_artifacts


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
    map_target = tmp_path / "data" / "processed" / "maps" / "map2.json"
    map_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "data" / "processed" / "maps" / "map2.json", map_target)
    trace_path = tmp_path / manifest["artifacts"]["trace_sample"]["path"]
    trace_path.write_text(trace_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = validate_committed_artifacts(tmp_path)
    assert result["status"] == "FAIL"
    assert any("SHA-256 mismatch" in failure for failure in result["failures"])
