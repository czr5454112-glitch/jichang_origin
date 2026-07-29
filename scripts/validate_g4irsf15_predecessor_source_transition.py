"""Validate G4IRSF14 history through an explicit G4IRSF15 source transition.

The immutable G4IRSF14 validator is not modified because its own bytes are
part of the sealed predecessor identity.  This successor validator first
reconstructs a temporary historical source snapshot from the frozen Git
commit and runs that unchanged validator.  It then independently verifies the
content-addressed transition to the current G4IRSF15 checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Mapping, Sequence

from scripts import validate_g4irsf14_fail_closed_completion as predecessor
from scripts.create_g4irsf15_predecessor_source_transition import (
    DEFAULT_OUTPUT,
    DEFAULT_PREDECESSOR_COMMIT,
    GENERATOR_PATH,
    SCHEMA,
    VALIDATOR_PATH,
)


class SourceTransitionValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceTransitionValidationError(message)


def _git(repo_root: Path, *argv: str) -> bytes:
    result = subprocess.run(
        ["git", *argv],
        cwd=repo_root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    _require(
        result.returncode == 0,
        "SOURCE_TRANSITION_GIT_FAILURE:"
        + result.stderr.decode("utf-8", errors="replace").strip(),
    )
    return result.stdout


def _semantic_sha256_bytes(value: bytes, label: str) -> str:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceTransitionValidationError(
            f"SOURCE_TRANSITION_NOT_UTF8:{label}"
        ) from exc
    normalized = text.replace("\r\n", "\n")
    _require("\r" not in normalized, f"SOURCE_TRANSITION_LONE_CR:{label}")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label}_NOT_OBJECT")
    return value


def _array(value: Any, label: str) -> list[Any]:
    _require(isinstance(value, list), f"{label}_NOT_ARRAY")
    return value


def _exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    label: str,
) -> None:
    _require(set(value) == expected, f"{label}_KEY_DRIFT")


def _load_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise SourceTransitionValidationError(
                    f"SOURCE_TRANSITION_DUPLICATE_JSON_KEY:{key}"
                )
            value[key] = item
        return value

    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=lambda token: (_ for _ in ()).throw(
            SourceTransitionValidationError(
                f"SOURCE_TRANSITION_NONFINITE_JSON:{token}"
            )
        ),
    )
    _require(isinstance(value, dict), "SOURCE_TRANSITION_NOT_OBJECT")
    return value


def _validate_file_row(
    repo_root: Path,
    value: Any,
    expected_path: Path,
    label: str,
) -> None:
    row = _mapping(value, label)
    _exact_keys(row, {"path", "sha256", "byte_count"}, label)
    path = repo_root / expected_path
    payload = path.read_bytes()
    _require(
        row
        == {
            "path": expected_path.as_posix(),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "byte_count": len(payload),
        },
        f"{label}_DRIFT",
    )


def _validate_transition_manifest(
    *,
    repo_root: Path,
    transition_path: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    transition = _load_json(transition_path)
    _exact_keys(
        transition,
        {
            "schema",
            "status",
            "generated_by",
            "predecessor_commit",
            "git_object_format",
            "predecessor_source_bundle",
            "predecessor_git_objects",
            "successor_source_bundle",
            "changed_paths",
            "generator",
            "validator",
            "claim_boundary",
            "self_sha256",
        },
        "SOURCE_TRANSITION",
    )
    self_sha = transition.get("self_sha256")
    projection = dict(transition)
    projection.pop("self_sha256")
    _require(
        isinstance(self_sha, str)
        and self_sha == predecessor.canonical_sha256(projection),
        "SOURCE_TRANSITION_SELF_HASH_DRIFT",
    )
    _require(
        transition.get("schema") == SCHEMA
        and transition.get("status") == "COMPLETE"
        and transition.get("generated_by") == GENERATOR_PATH.as_posix()
        and transition.get("predecessor_commit")
        == DEFAULT_PREDECESSOR_COMMIT,
        "SOURCE_TRANSITION_IDENTITY_DRIFT",
    )
    _validate_file_row(
        repo_root,
        transition.get("generator"),
        GENERATOR_PATH,
        "SOURCE_TRANSITION_GENERATOR",
    )
    _validate_file_row(
        repo_root,
        transition.get("validator"),
        VALIDATOR_PATH,
        "SOURCE_TRANSITION_VALIDATOR",
    )

    census = _load_json(repo_root / predecessor.UPSTREAM_CENSUS)
    stage_e_bundle = _mapping(
        census.get("source_bundle"),
        "STAGE_E_SOURCE_BUNDLE",
    )
    _require(
        transition.get("predecessor_source_bundle") == stage_e_bundle,
        "SOURCE_TRANSITION_PREDECESSOR_BUNDLE_DRIFT",
    )
    expected_paths = [
        path.as_posix()
        for path in sorted(
            predecessor.STAGE_E_SOURCE_PATHS,
            key=lambda item: item.as_posix(),
        )
    ]
    stage_e_records = [
        _mapping(value, f"STAGE_E_SOURCE_{index}")
        for index, value in enumerate(
            _array(stage_e_bundle.get("files"), "STAGE_E_SOURCE_FILES")
        )
    ]
    _require(
        [str(value.get("path")) for value in stage_e_records]
        == expected_paths,
        "SOURCE_TRANSITION_STAGE_E_INVENTORY_DRIFT",
    )
    stage_e_by_path = {
        str(value["path"]): str(value["semantic_sha256"])
        for value in stage_e_records
    }

    object_format = _git(
        repo_root,
        "rev-parse",
        "--show-object-format",
    ).decode().strip()
    _require(
        transition.get("git_object_format") == object_format,
        "SOURCE_TRANSITION_OBJECT_FORMAT_DRIFT",
    )
    commit = str(transition["predecessor_commit"])
    _git(repo_root, "cat-file", "-e", f"{commit}^{{commit}}")
    predecessor_objects = [
        _mapping(value, f"SOURCE_TRANSITION_PREDECESSOR_OBJECT_{index}")
        for index, value in enumerate(
            _array(
                transition.get("predecessor_git_objects"),
                "SOURCE_TRANSITION_PREDECESSOR_OBJECTS",
            )
        )
    ]
    _require(
        [str(value.get("path")) for value in predecessor_objects]
        == expected_paths,
        "SOURCE_TRANSITION_PREDECESSOR_INVENTORY_DRIFT",
    )
    for row in predecessor_objects:
        _exact_keys(
            row,
            {"path", "git_object_oid", "semantic_sha256"},
            "SOURCE_TRANSITION_PREDECESSOR_OBJECT",
        )
        relative = str(row["path"])
        historical = _git(repo_root, "show", f"{commit}:{relative}")
        semantic_sha = _semantic_sha256_bytes(historical, relative)
        object_oid = _git(
            repo_root,
            "rev-parse",
            f"{commit}:{relative}",
        ).decode().strip()
        _require(
            semantic_sha == stage_e_by_path.get(relative)
            and row.get("semantic_sha256") == semantic_sha
            and row.get("git_object_oid") == object_oid,
            f"SOURCE_TRANSITION_PREDECESSOR_GIT_DRIFT:{relative}",
        )

    successor_bundle = _mapping(
        transition.get("successor_source_bundle"),
        "SOURCE_TRANSITION_SUCCESSOR_BUNDLE",
    )
    _exact_keys(
        successor_bundle,
        {
            "hash_mode",
            "files",
            "path_manifest_sha256",
            "bundle_sha256",
        },
        "SOURCE_TRANSITION_SUCCESSOR_BUNDLE",
    )
    _require(
        successor_bundle.get("hash_mode")
        == "sha256_utf8_after_crlf_to_lf_reject_lone_cr",
        "SOURCE_TRANSITION_SUCCESSOR_HASH_MODE_DRIFT",
    )
    successor_records = [
        _mapping(value, f"SOURCE_TRANSITION_SUCCESSOR_{index}")
        for index, value in enumerate(
            _array(
                successor_bundle.get("files"),
                "SOURCE_TRANSITION_SUCCESSOR_FILES",
            )
        )
    ]
    _require(
        [str(value.get("path")) for value in successor_records]
        == expected_paths,
        "SOURCE_TRANSITION_SUCCESSOR_INVENTORY_DRIFT",
    )
    normalized_records: list[dict[str, str]] = []
    for row in successor_records:
        _exact_keys(
            row,
            {"path", "semantic_sha256"},
            "SOURCE_TRANSITION_SUCCESSOR",
        )
        relative = str(row["path"])
        current = (repo_root / relative).resolve(strict=True)
        try:
            current.relative_to(repo_root)
        except ValueError as exc:
            raise SourceTransitionValidationError(
                f"SOURCE_TRANSITION_SUCCESSOR_ESCAPES_ROOT:{relative}"
            ) from exc
        normalized = {
            "path": relative,
            "semantic_sha256": predecessor.semantic_text_sha256(current),
        }
        _require(
            dict(row) == normalized,
            f"SOURCE_TRANSITION_SUCCESSOR_CHECKOUT_DRIFT:{relative}",
        )
        normalized_records.append(normalized)
    _require(
        successor_bundle.get("path_manifest_sha256")
        == predecessor.canonical_sha256(expected_paths)
        and successor_bundle.get("bundle_sha256")
        == predecessor.canonical_sha256(normalized_records),
        "SOURCE_TRANSITION_SUCCESSOR_BUNDLE_HASH_DRIFT",
    )
    changed_paths = [
        row["path"]
        for row in normalized_records
        if row["semantic_sha256"] != stage_e_by_path[row["path"]]
    ]
    _require(
        transition.get("changed_paths") == changed_paths,
        "SOURCE_TRANSITION_CHANGED_PATHS_DRIFT",
    )
    return transition, normalized_records


def _validate_historical_bundle(
    *,
    repo_root: Path,
    predecessor_commit: str,
    changed_paths: set[Path],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="czr005-g4irsf14-history-") as raw:
        snapshot = Path(raw)
        for relative in predecessor.REQUIRED_BUNDLE_FILES:
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative in changed_paths:
                target.write_bytes(
                    _git(
                        repo_root,
                        "show",
                        f"{predecessor_commit}:{relative.as_posix()}",
                    )
                )
            else:
                source = repo_root / relative
                _require(
                    source.is_file(),
                    f"HISTORICAL_REQUIRED_FILE_MISSING:{relative.as_posix()}",
                )
                shutil.copyfile(source, target)
        return predecessor.validate_fail_closed_completion(snapshot)


def validate_predecessor_source_transition(
    *,
    repo_root: Path,
    transition_path: Path,
) -> dict[str, Any]:
    repo_root = repo_root.resolve(strict=True)
    transition_path = (
        transition_path
        if transition_path.is_absolute()
        else repo_root / transition_path
    ).resolve(strict=True)
    try:
        transition_path.relative_to(repo_root)
    except ValueError as exc:
        raise SourceTransitionValidationError(
            "SOURCE_TRANSITION_MANIFEST_ESCAPES_ROOT"
        ) from exc
    transition, successor_records = _validate_transition_manifest(
        repo_root=repo_root,
        transition_path=transition_path,
    )
    historical = _validate_historical_bundle(
        repo_root=repo_root,
        predecessor_commit=str(transition["predecessor_commit"]),
        changed_paths={Path(value) for value in transition["changed_paths"]},
    )
    _require(
        historical.get("status") == "PARTIAL_WITH_EXPLICIT_BLOCKER_VALID",
        "HISTORICAL_G4IRSF14_VALIDATION_NOT_FAIL_CLOSED_VALID",
    )
    return {
        "schema": "czr005.g4irsf15.g4irsf14_source_transition_validation.v1",
        "status": "PASS",
        "transition_self_sha256": transition["self_sha256"],
        "predecessor_commit": transition["predecessor_commit"],
        "predecessor_validation_status": historical["status"],
        "predecessor_causal_label_count": historical["causal_label_count"],
        "successor_source_file_count": len(successor_records),
        "changed_path_count": len(transition["changed_paths"]),
        "claim_boundary": (
            "The predecessor remains a valid zero-label fail-closed result; "
            "the transition only attests successor source identity."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--transition",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    args = parser.parse_args(argv)
    try:
        result = validate_predecessor_source_transition(
            repo_root=args.repo_root,
            transition_path=args.transition,
        )
    except (
        SourceTransitionValidationError,
        predecessor.CompletionValidationError,
        OSError,
        UnicodeError,
        ValueError,
    ) as exc:
        print(f"G4IRSF15 predecessor source transition validation: FAIL: {exc}")
        return 1
    print(
        "G4IRSF15 predecessor source transition validation: PASS\n"
        + json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
