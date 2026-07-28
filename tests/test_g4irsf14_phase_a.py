from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import g4irsf14_phase_a as phase_a


@pytest.fixture(scope="module")
def inherited_evidence() -> dict[str, Any]:
    return phase_a.collect_inherited_evidence(phase_a.ROOT)


def _copy_freeze_inputs(destination: Path) -> Path:
    paths = tuple(dict.fromkeys(phase_a.IMMUTABILITY_SNAPSHOT_PATHS))
    for relative in paths:
        source = phase_a.ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def test_real_repository_inherited_evidence_passes(
    inherited_evidence: dict[str, Any],
) -> None:
    assert phase_a.validate_inherited_evidence(inherited_evidence) == []


def test_phase_start_is_ancestor_and_protected_paths_pass() -> None:
    identity = phase_a.collect_git_identity(phase_a.ROOT)
    # Unit tests may run while a later G4IRSF14 phase has tracked worktree
    # edits.  The CLI still fails closed on that condition; here we isolate
    # ancestry/protected-path validation from unrelated in-progress files.
    validation_identity = dict(identity)
    validation_identity["tracked_status"] = []
    assert phase_a.validate_git_identity(
        validation_identity,
        require_exact_start=False,
    ) == []
    assert identity["start_is_ancestor_of_head"] is True
    assert identity["start_is_ancestor_of_upstream"] is True
    assert identity["protected_status"] == []
    assert identity["protected_commit_diff"] == []


def test_phase_start_source_blobs_use_worktree_filters() -> None:
    rows = phase_a._source_descriptors(phase_a.ROOT)
    assert [
        {"path": row["path"], "sha256": row["sha256"]}
        for row in rows
    ] == [
        {"path": path.as_posix(), "sha256": digest}
        for path, digest in phase_a.FINAL_SOURCE_FILES
    ]
    assert all(
        row["identity_source"].startswith("git_blob_")
        for row in rows
    )


def test_hash_conventions_match_canonical_predecessor() -> None:
    payload = b'{"a":1}\r\n{"b":2}\r'
    assert phase_a.normalised_text_sha256(payload) == phase_a.sha256_bytes(
        b'{"a":1}\n{"b":2}\n'
    )
    left = {"z": 2, "a": [1, "x"]}
    right = {"a": [1, "x"], "z": 2}
    assert phase_a.canonical_sha256(left) == phase_a.canonical_sha256(right)


def test_map_drift_in_temp_copy_fails_closed(tmp_path: Path) -> None:
    root = _copy_freeze_inputs(tmp_path / "map_drift")
    map_path = root / phase_a.MAP_PATH
    map_path.write_bytes(map_path.read_bytes() + b"\n")
    evidence = phase_a.collect_inherited_evidence(root)
    failures = phase_a.validate_inherited_evidence(evidence)
    assert "canonical map raw SHA-256 drift" in failures
    assert "canonical map semantic SHA-256 drift" in failures
    with pytest.raises(phase_a.FreezeError, match="FAIL_CLOSED"):
        phase_a.build_payloads(evidence)


def test_task_drift_in_temp_copy_fails_closed(tmp_path: Path) -> None:
    root = _copy_freeze_inputs(tmp_path / "task_drift")
    task_path = root / phase_a.TASK_PATH
    task_path.write_bytes(task_path.read_bytes() + b"\n")
    evidence = phase_a.collect_inherited_evidence(root)
    failures = phase_a.validate_inherited_evidence(evidence)
    assert "canonical task raw SHA-256 drift" in failures
    assert "canonical task semantic SHA-256 drift" in failures


def test_inherited_artifact_drift_in_temp_copy_fails_closed(
    tmp_path: Path,
) -> None:
    root = _copy_freeze_inputs(tmp_path / "artifact_drift")
    fault_path = root / phase_a.G13_FAULT_BUNDLE_PATH
    fault_path.write_bytes(fault_path.read_bytes() + b"\n")
    evidence = phase_a.collect_inherited_evidence(root)
    failures = phase_a.validate_inherited_evidence(evidence)
    assert any(
        failure.startswith("inherited artifact physical SHA-256 drift:")
        and phase_a.G13_FAULT_BUNDLE_PATH.as_posix() in failure
        for failure in failures
    )


def test_publication_writes_exactly_five_outputs_and_preserves_inputs(
    tmp_path: Path,
) -> None:
    root = _copy_freeze_inputs(tmp_path / "publication")
    evidence = phase_a.collect_inherited_evidence(root)
    before = phase_a.snapshot_files(root)
    payloads = phase_a.build_payloads(evidence)
    written = phase_a.publish_payloads(payloads, root)
    after = phase_a.snapshot_files(root)

    assert before == after
    assert {path.relative_to(root) for path in written} == set(
        phase_a.OUTPUT_PATHS
    )
    assert phase_a.validate_committed_outputs(root, evidence) == []


def test_frozen_outputs_bind_runtime_decision_and_no_scale(
    inherited_evidence: dict[str, Any],
) -> None:
    payloads = phase_a.build_payloads(inherited_evidence)
    assert phase_a.validate_output_payloads(payloads, inherited_evidence) == []

    f2 = phase_a.json.loads(
        payloads[phase_a.F2_FROZEN_CONTROL_PATH].decode("utf-8")
    )
    registry = phase_a.json.loads(
        payloads[phase_a.BASELINE_REGISTRY_PATH].decode("utf-8")
    )
    assert (
        f2["final_runtime_identity"]["binary"]["file_sha256"]
        == phase_a.FINAL_BINARY_SHA256
    )
    assert (
        f2["final_runtime_identity"]["source_bundle_sha256"]
        == phase_a.FINAL_SOURCE_BUNDLE_SHA256
    )
    assert (
        f2["final_runtime_identity"]["model"]["file_sha256"]
        == phase_a.FROZEN_MODEL_SHA256
    )
    assert (
        f2["final_runtime_identity"]["case_config_sha256"]
        == phase_a.F2_CONFIG_SHA256
    )
    assert (
        registry["g4irsf13_final_decision"]["decision_status"]
        == "HISTORICAL_ONLY_PASS"
    )
    assert registry["no_scale_gate"]["g4j_status"] == "CLOSED"
    assert registry["no_scale_gate"]["phase_l_status"] == "NOT_RUN"
    assert registry["no_scale_gate"]["scale_execution_count"] == 0


def test_missing_binary_is_a_fail_closed_collection_error(tmp_path: Path) -> None:
    root = _copy_freeze_inputs(tmp_path / "missing_binary")
    (root / phase_a.FROZEN_BINARY_PATH).unlink()
    with pytest.raises(phase_a.FreezeError, match="missing required file"):
        phase_a.collect_inherited_evidence(root, require_binary=True)
