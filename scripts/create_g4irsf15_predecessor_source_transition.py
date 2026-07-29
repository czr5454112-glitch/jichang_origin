"""Seal the G4IRSF14-to-G4IRSF15 native-source transition.

G4IRSF14's historical validator intentionally requires the checked-out source
files to match the exact Stage-E source bundle.  A successor may evolve those
files only through this explicit transition: every predecessor byte is
recovered from the frozen baseline commit, and every successor file is
content-addressed.  The historical validator remains strict unless this
manifest is supplied explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from scripts import validate_g4irsf14_fail_closed_completion as predecessor


SCHEMA = "czr005.g4irsf15.g4irsf14_source_transition.v1"
DEFAULT_PREDECESSOR_COMMIT = "966a063573f0419df1324708db75211c521d59db"
DEFAULT_OUTPUT = Path(
    "outputs/manifests/g4irsf15_g4irsf14_source_transition.json"
)
GENERATOR_PATH = Path(
    "scripts/create_g4irsf15_predecessor_source_transition.py"
)
VALIDATOR_PATH = Path(
    "scripts/validate_g4irsf15_predecessor_source_transition.py"
)


def _git(repo_root: Path, *argv: str) -> bytes:
    result = subprocess.run(
        ["git", *argv],
        cwd=repo_root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(argv)} failed: "
            + result.stderr.decode("utf-8", errors="replace")
        )
    return result.stdout


def _semantic_sha256_bytes(value: bytes) -> str:
    text = value.decode("utf-8")
    normalized = text.replace("\r\n", "\n")
    if "\r" in normalized:
        raise ValueError("semantic source contains a lone carriage return")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _file_row(repo_root: Path, relative: Path) -> dict[str, Any]:
    path = repo_root / relative
    payload = path.read_bytes()
    return {
        "path": relative.as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_count": len(payload),
    }


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def create_source_transition(
    *,
    repo_root: Path,
    predecessor_commit: str = DEFAULT_PREDECESSOR_COMMIT,
    output_path: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    census = json.loads(
        (repo_root / predecessor.UPSTREAM_CENSUS).read_text(encoding="utf-8")
    )
    predecessor_bundle = census.get("source_bundle")
    if not isinstance(predecessor_bundle, dict):
        raise ValueError("G4IRSF14 census has no source_bundle object")
    records = predecessor_bundle.get("files")
    if not isinstance(records, list):
        raise ValueError("G4IRSF14 source_bundle has no files array")
    expected_paths = [path.as_posix() for path in predecessor.STAGE_E_SOURCE_PATHS]
    if [row.get("path") for row in records if isinstance(row, dict)] != expected_paths:
        raise ValueError("G4IRSF14 source path inventory is not canonical")

    object_format = _git(
        repo_root,
        "rev-parse",
        "--show-object-format",
    ).decode().strip()
    _git(repo_root, "cat-file", "-e", f"{predecessor_commit}^{{commit}}")

    predecessor_objects: list[dict[str, Any]] = []
    successor_records: list[dict[str, str]] = []
    changed_paths: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("G4IRSF14 source record is not an object")
        relative = str(record["path"])
        declared = str(record["semantic_sha256"])
        historical = _git(repo_root, "show", f"{predecessor_commit}:{relative}")
        historical_sha = _semantic_sha256_bytes(historical)
        if historical_sha != declared:
            raise ValueError(
                f"predecessor Git content does not match Stage-E: {relative}"
            )
        object_oid = _git(
            repo_root,
            "rev-parse",
            f"{predecessor_commit}:{relative}",
        ).decode().strip()
        predecessor_objects.append(
            {
                "path": relative,
                "git_object_oid": object_oid,
                "semantic_sha256": historical_sha,
            }
        )

        successor_path = (repo_root / relative).resolve(strict=True)
        successor_path.relative_to(repo_root)
        successor_sha = predecessor.semantic_text_sha256(successor_path)
        successor_records.append(
            {
                "path": relative,
                "semantic_sha256": successor_sha,
            }
        )
        if successor_sha != historical_sha:
            changed_paths.append(relative)

    successor_bundle = {
        "hash_mode": predecessor_bundle["hash_mode"],
        "files": successor_records,
        "path_manifest_sha256": predecessor.canonical_sha256(expected_paths),
        "bundle_sha256": predecessor.canonical_sha256(successor_records),
    }
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "COMPLETE",
        "generated_by": (
            "scripts/create_g4irsf15_predecessor_source_transition.py"
        ),
        "predecessor_commit": predecessor_commit,
        "git_object_format": object_format,
        "predecessor_source_bundle": predecessor_bundle,
        "predecessor_git_objects": predecessor_objects,
        "successor_source_bundle": successor_bundle,
        "changed_paths": changed_paths,
        "generator": _file_row(repo_root, GENERATOR_PATH),
        "validator": _file_row(repo_root, VALIDATOR_PATH),
        "claim_boundary": (
            "This transition preserves the immutable G4IRSF14 Stage-E source "
            "identity while allowing explicitly hashed G4IRSF15 successor "
            "source. It does not alter or promote any G4IRSF14 result."
        ),
    }
    manifest["self_sha256"] = predecessor.canonical_sha256(manifest)
    if output_path is not None:
        _atomic_write(output_path.resolve(), manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--predecessor-commit",
        default=DEFAULT_PREDECESSOR_COMMIT,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    output = args.output if args.output.is_absolute() else repo_root / args.output
    result = create_source_transition(
        repo_root=repo_root,
        predecessor_commit=args.predecessor_commit,
        output_path=output,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "changed_path_count": len(result["changed_paths"]),
                "successor_source_bundle_sha256": result[
                    "successor_source_bundle"
                ]["bundle_sha256"],
                "self_sha256": result["self_sha256"],
                "output": str(output.resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
