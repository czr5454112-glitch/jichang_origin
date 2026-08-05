from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from scripts.prepare_g4irsf16_predecessor_worktree import (
    ReconstructionError,
    reconstruct_source_identity,
)


ROOT = Path(__file__).resolve().parents[1]
G4IRSF15_SEAL = "8f3106b116f2648b6fa2e30bc8960659739d3a58"


def _binding(path: str, payload: bytes) -> dict[str, object]:
    return {
        "byte_count": len(payload),
        "path": path,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def test_reconstructs_only_exact_sealed_eol_bytes(tmp_path: Path) -> None:
    all_crlf = b"alpha\r\nbeta\r\n"
    mixed = b"one\r\ntwo\nthree\r\n"
    (tmp_path / "all.txt").write_bytes(all_crlf.replace(b"\r\n", b"\n"))
    (tmp_path / "mixed.txt").write_bytes(
        mixed.replace(b"\r\n", b"\n")
    )
    identity = {
        "files": [
            _binding("all.txt", all_crlf),
            _binding("mixed.txt", mixed),
        ],
        "source_bundle_sha256": "synthetic",
    }

    result = reconstruct_source_identity(
        tmp_path,
        identity,
        expected_bundle_sha256=None,
        mixed_lf_ranges={"mixed.txt": ((2, 2),)},
    )

    assert result["status"] == "PASS_G4IRSF15_SEALED_EOL_RECONSTRUCTION"
    assert result["restored_file_count"] == 2
    assert (tmp_path / "all.txt").read_bytes() == all_crlf
    assert (tmp_path / "mixed.txt").read_bytes() == mixed


def test_exact_file_is_not_rewritten(tmp_path: Path) -> None:
    expected = b"already\nexact\n"
    path = tmp_path / "exact.txt"
    path.write_bytes(expected)
    before = path.stat().st_mtime_ns

    result = reconstruct_source_identity(
        tmp_path,
        {
            "files": [_binding("exact.txt", expected)],
            "source_bundle_sha256": "synthetic",
        },
        expected_bundle_sha256=None,
        mixed_lf_ranges={},
    )

    assert result["exact_file_count"] == 1
    assert result["restored_file_count"] == 0
    assert path.stat().st_mtime_ns == before


def test_non_eol_source_drift_is_rejected(tmp_path: Path) -> None:
    expected = b"alpha\r\nbeta\r\n"
    (tmp_path / "source.txt").write_bytes(b"alpha\nchanged\n")

    with pytest.raises(
        ReconstructionError, match="NON_EOL_SOURCE_DRIFT:source.txt"
    ):
        reconstruct_source_identity(
            tmp_path,
            {
                "files": [_binding("source.txt", expected)],
                "source_bundle_sha256": "synthetic",
            },
            expected_bundle_sha256=None,
            mixed_lf_ranges={},
        )


def test_path_escape_and_unexpected_bundle_are_rejected(
    tmp_path: Path,
) -> None:
    payload = b"sealed\n"
    with pytest.raises(ReconstructionError, match="UNEXPECTED_SOURCE_BUNDLE"):
        reconstruct_source_identity(
            tmp_path,
            {
                "files": [_binding("source.txt", payload)],
                "source_bundle_sha256": "wrong",
            },
            mixed_lf_ranges={},
        )


def test_real_sealed_git_blobs_reconstruct_all_historical_bindings(
    tmp_path: Path,
) -> None:
    manifest = json.loads(
        (ROOT / "artifacts/datasets/g4irsf15_causal_descriptor_manifest.json")
        .read_text(encoding="utf-8")
    )
    identity = manifest["source_identity"]
    for binding in identity["files"]:
        relative = binding["path"]
        payload = subprocess.check_output(
            ["git", "show", f"{G4IRSF15_SEAL}:{relative}"],
            cwd=ROOT,
        )
        target = tmp_path / Path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    result = reconstruct_source_identity(tmp_path, identity)

    assert result["source_file_count"] == 14
    assert result["restored_file_count"] == 8
    assert result["exact_file_count"] == 6
    for binding in identity["files"]:
        payload = (tmp_path / Path(binding["path"])).read_bytes()
        assert len(payload) == binding["byte_count"]
        assert hashlib.sha256(payload).hexdigest() == binding["sha256"]

    with pytest.raises(ReconstructionError, match="UNSAFE_SOURCE_PATH"):
        reconstruct_source_identity(
            tmp_path,
            {
                "files": [_binding("../escape.txt", payload)],
                "source_bundle_sha256": "synthetic",
            },
            expected_bundle_sha256=None,
            mixed_lf_ranges={},
        )
