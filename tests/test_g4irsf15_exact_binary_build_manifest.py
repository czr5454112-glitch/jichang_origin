from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.create_g4irsf15_exact_binary_build_manifest import (
    DIRTY_STATE_ALGORITHM,
    INVENTORY_METHOD,
    REPOSITORY_BINDING_METHOD,
    _canonical_bytes,
    _decode_tlog,
    _input_snapshot,
    _require_clean_publication_source_state,
    _repo_relative_or_external_absolute,
    _sha256_bytes,
    _target_python_metadata,
    collect_dirty_source_state,
    collect_transitive_source_inventory,
)


def _git(repo: Path, *argv: str) -> None:
    subprocess.run(
        ["git", *argv],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _fixture_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    source = repo / "cpp" / "ics_core"
    source.mkdir(parents=True)
    (repo / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\n",
        encoding="utf-8",
    )
    (source / "binding.cpp").write_text(
        '#include "runtime.hpp"\n',
        encoding="utf-8",
    )
    (source / "runtime.hpp").write_text("#pragma once\n", encoding="utf-8")
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture")
    return repo, source


def test_inventory_unions_dependency_scan_and_explicit_headers(
    tmp_path: Path,
) -> None:
    repo, source = _fixture_repo(tmp_path)
    build = repo / "build"
    tlog = build / "czr005_cpp.dir" / "Release" / "czr005_cpp.tlog"
    tlog.mkdir(parents=True)
    dependency = source / "runtime.hpp"
    (tlog / "CL.read.1.tlog").write_text(
        f"^{source / 'binding.cpp'}\n{dependency}\n",
        encoding="utf-16",
    )

    inventory = collect_transitive_source_inventory(
        repo_root=repo,
        build_dir=build,
    )

    assert inventory["method"] == INVENTORY_METHOD
    paths = [row["path"] for row in inventory["files"]]
    assert paths == sorted(
        ["CMakeLists.txt", "cpp/ics_core/binding.cpp", "cpp/ics_core/runtime.hpp"]
    )
    assert inventory["dependency_scan_local_file_count"] == 2
    assert inventory["repository_binding_method"] == (
        REPOSITORY_BINDING_METHOD
    )
    assert all(
        row["repository_blob"]["method"]
        == REPOSITORY_BINDING_METHOD
        and len(row["repository_blob"]["object_id"]) in {40, 64}
        for row in inventory["files"]
    )
    assert inventory["bundle_sha256"] == _sha256_bytes(
        _canonical_bytes(inventory["files"])
    )


def test_inventory_separates_checkout_bytes_from_repository_blob(
    tmp_path: Path,
) -> None:
    repo, _ = _fixture_repo(tmp_path)
    (repo / ".gitattributes").write_text(
        "CMakeLists.txt text eol=crlf\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".gitattributes")
    _git(repo, "commit", "-m", "bind checkout eol")
    checkout_bytes = b"cmake_minimum_required(VERSION 3.20)\r\n"
    (repo / "CMakeLists.txt").write_bytes(checkout_bytes)
    _git(repo, "diff", "--exit-code", "--", "CMakeLists.txt")

    inventory = collect_transitive_source_inventory(
        repo_root=repo,
        build_dir=repo / "build",
    )
    row = next(
        item
        for item in inventory["files"]
        if item["path"] == "CMakeLists.txt"
    )

    assert row["sha256"] == hashlib.sha256(checkout_bytes).hexdigest()
    assert row["repository_blob"]["sha256"] == hashlib.sha256(
        b"cmake_minimum_required(VERSION 3.20)\n"
    ).hexdigest()
    assert row["sha256"] != row["repository_blob"]["sha256"]


def test_dirty_state_binds_binary_diff_staged_diff_and_untracked_source(
    tmp_path: Path,
) -> None:
    repo, source = _fixture_repo(tmp_path)
    tracked = source / "runtime.hpp"
    tracked.write_text("#pragma once\n// staged\n", encoding="utf-8")
    _git(repo, "add", tracked.relative_to(repo).as_posix())
    tracked.write_text(
        "#pragma once\n// staged\n// worktree\n",
        encoding="utf-8",
    )
    untracked = source / "new.hpp"
    untracked.write_text("#pragma once\n", encoding="utf-8")

    state = collect_dirty_source_state(
        repo_root=repo,
        source_paths=[
            tracked.relative_to(repo).as_posix(),
            untracked.relative_to(repo).as_posix(),
        ],
    )

    assert state["algorithm"] == DIRTY_STATE_ALGORITHM
    source_paths = [
        tracked.relative_to(repo).as_posix(),
        untracked.relative_to(repo).as_posix(),
    ]
    assert state["source_path_count"] == len(source_paths)
    assert state["source_paths_sha256"] == _sha256_bytes(
        _canonical_bytes(sorted(source_paths))
    )
    assert state["tracked_worktree_diff_sha256"] != hashlib.sha256(b"").hexdigest()
    assert state["staged_diff_sha256"] != hashlib.sha256(b"").hexdigest()
    assert state["untracked_source_files"] == [
        {
            "path": "cpp/ics_core/new.hpp",
            "sha256": hashlib.sha256(untracked.read_bytes()).hexdigest(),
            "byte_count": untracked.stat().st_size,
        }
    ]
    without_self = dict(state)
    recorded = without_self.pop("state_sha256")
    assert recorded == _sha256_bytes(_canonical_bytes(without_self))
    with pytest.raises(RuntimeError, match="requires clean"):
        _require_clean_publication_source_state(state)


def test_clean_source_state_is_publication_eligible(tmp_path: Path) -> None:
    repo, source = _fixture_repo(tmp_path)
    source_paths = [
        "CMakeLists.txt",
        (source / "runtime.hpp").relative_to(repo).as_posix(),
    ]
    state = collect_dirty_source_state(
        repo_root=repo,
        source_paths=source_paths,
    )

    _require_clean_publication_source_state(state)
    assert state["source_path_count"] == len(source_paths)
    assert state["source_paths_sha256"] == _sha256_bytes(
        _canonical_bytes(sorted(source_paths))
    )


def test_snapshot_detects_source_change(tmp_path: Path) -> None:
    repo, source = _fixture_repo(tmp_path)
    paths = [repo / "CMakeLists.txt", source / "runtime.hpp"]
    before = _input_snapshot(paths, repo)
    (source / "runtime.hpp").write_text("#pragma once\n// changed\n", encoding="utf-8")
    after = _input_snapshot(paths, repo)
    assert before != after


def test_binary_publication_path_is_relative_inside_and_absolute_outside(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    inside = repo / "build" / "module.pyd"
    outside = tmp_path / "external-build" / "module.pyd"
    inside.parent.mkdir(parents=True)
    outside.parent.mkdir(parents=True)
    inside.write_bytes(b"inside")
    outside.write_bytes(b"outside")

    assert (
        _repo_relative_or_external_absolute(inside, repo)
        == "build/module.pyd"
    )
    assert _repo_relative_or_external_absolute(
        outside, repo
    ) == str(outside.resolve())


def test_tlog_decoder_accepts_utf16_and_utf8(tmp_path: Path) -> None:
    utf16 = tmp_path / "utf16.tlog"
    utf8 = tmp_path / "utf8.tlog"
    utf16.write_text("C:\\source\\x.hpp\n", encoding="utf-16")
    utf8.write_text("/source/x.hpp\n", encoding="utf-8")
    assert "x.hpp" in _decode_tlog(utf16)
    assert "x.hpp" in _decode_tlog(utf8)


def test_canonical_self_hash_excludes_self_field() -> None:
    manifest = {"schema": "example", "status": "COMPLETE"}
    manifest["self_sha256"] = _sha256_bytes(_canonical_bytes(manifest))
    unhashed = dict(manifest)
    recorded = unhashed.pop("self_sha256")
    assert recorded == _sha256_bytes(_canonical_bytes(unhashed))


def test_python_metadata_comes_from_requested_interpreter(
    tmp_path: Path,
) -> None:
    metadata = _target_python_metadata(Path(sys.executable), cwd=tmp_path)
    assert Path(metadata["executable"]).resolve() == Path(sys.executable).resolve()
    assert metadata["implementation"] == sys.implementation.name
    assert metadata["pybind11_version"]
    assert Path(metadata["pybind11_cmake_dir"]).is_dir()


def test_inventory_fails_when_required_native_root_is_missing(
    tmp_path: Path,
) -> None:
    (tmp_path / "CMakeLists.txt").write_text("project(x)\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="native source root"):
        collect_transitive_source_inventory(
            repo_root=tmp_path,
            build_dir=tmp_path / "build",
        )
