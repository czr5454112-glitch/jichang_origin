from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import create_g4irsf15_predecessor_source_transition as creator
from scripts import validate_g4irsf14_fail_closed_completion as predecessor
from scripts import validate_g4irsf15_predecessor_source_transition as validator


ROOT = Path(__file__).resolve().parents[1]
FROZEN_COMMIT = "966a063573f0419df1324708db75211c521d59db"
CHANGED = {
    Path("CMakeLists.txt"),
    Path("cpp/ics_core/bindings/czr005_cpp.cpp"),
    Path("cpp/ics_core/runtime/event_driven_junction.hpp"),
}


def _run(repo: Path, *argv: str) -> bytes:
    return subprocess.run(
        [*argv],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def _transition_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    repo = tmp_path / "bundle"
    for relative in predecessor.REQUIRED_BUNDLE_FILES:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative in CHANGED:
            target.write_bytes(
                _run(
                    ROOT,
                    "git",
                    "show",
                    f"{FROZEN_COMMIT}:{relative.as_posix()}",
                )
            )
        else:
            shutil.copyfile(ROOT / relative, target)
    for relative in (creator.GENERATOR_PATH, creator.VALIDATOR_PATH):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)

    _run(repo, "git", "init")
    _run(repo, "git", "config", "user.name", "transition-test")
    _run(repo, "git", "config", "user.email", "transition@example.invalid")
    _run(
        repo,
        "git",
        "add",
        *[path.as_posix() for path in predecessor.STAGE_E_SOURCE_PATHS],
    )
    _run(repo, "git", "commit", "-m", "frozen predecessor source")
    predecessor_commit = _run(repo, "git", "rev-parse", "HEAD").decode().strip()

    for relative in CHANGED:
        shutil.copyfile(ROOT / relative, repo / relative)
    manifest_path = repo / creator.DEFAULT_OUTPUT
    creator.create_source_transition(
        repo_root=repo,
        predecessor_commit=predecessor_commit,
        output_path=manifest_path,
    )
    return repo, manifest_path, predecessor_commit


def test_transition_reconstructs_and_validates_immutable_predecessor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, manifest_path, predecessor_commit = _transition_fixture(tmp_path)
    monkeypatch.setattr(
        validator,
        "DEFAULT_PREDECESSOR_COMMIT",
        predecessor_commit,
    )

    result = validator.validate_predecessor_source_transition(
        repo_root=repo,
        transition_path=manifest_path,
    )

    assert result["status"] == "PASS"
    assert result["predecessor_causal_label_count"] == 0
    assert result["changed_path_count"] == 3


def test_successor_source_tamper_is_rejected_even_if_manifest_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, manifest_path, predecessor_commit = _transition_fixture(tmp_path)
    monkeypatch.setattr(
        validator,
        "DEFAULT_PREDECESSOR_COMMIT",
        predecessor_commit,
    )
    path = repo / "cpp/ics_core/runtime/event_driven_junction.hpp"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n// forged successor\n",
        encoding="utf-8",
    )

    with pytest.raises(
        validator.SourceTransitionValidationError,
        match="SUCCESSOR_CHECKOUT_DRIFT",
    ):
        validator.validate_predecessor_source_transition(
            repo_root=repo,
            transition_path=manifest_path,
        )


def test_transition_self_hash_tamper_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, manifest_path, predecessor_commit = _transition_fixture(tmp_path)
    monkeypatch.setattr(
        validator,
        "DEFAULT_PREDECESSOR_COMMIT",
        predecessor_commit,
    )
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    value["changed_paths"] = []
    manifest_path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(
        validator.SourceTransitionValidationError,
        match="SELF_HASH_DRIFT",
    ):
        validator.validate_predecessor_source_transition(
            repo_root=repo,
            transition_path=manifest_path,
        )
