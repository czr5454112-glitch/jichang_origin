"""Atomic, fail-closed publication records for G4IRSF11 evidence cohorts."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Mapping, Sequence
import uuid

from scripts.eval.g4irsf11_result_validation import atomic_write_json, read_json_object


COMPLETION_SCHEMA = "czr005.g4irsf11.cohort_completion.v1"
SEMANTIC_TEXT_HASH = "sha256 of text bytes after CRLF/CR newline normalization to LF"
_TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cmake",
    ".cpp",
    ".csv",
    ".h",
    ".hpp",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".txt",
    ".yml",
    ".yaml",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _semantic_bytes(path: Path) -> bytes:
    payload = path.read_bytes()
    if path.suffix.lower() in _TEXT_SUFFIXES:
        payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return payload


def semantic_file_sha256(path: Path) -> str:
    return hashlib.sha256(_semantic_bytes(path)).hexdigest()


def source_bundle_sha256(paths: Iterable[Path], root: Path) -> str:
    """Hash a checkout-independent, newline-stable set of implementation sources."""

    resolved_root = root.resolve()
    indexed: list[tuple[str, Path]] = []
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_relative_to(resolved_root):
            raise ValueError(f"implementation source escapes repository root: {path}")
        relative = resolved.relative_to(resolved_root).as_posix()
        indexed.append((relative, resolved))
    relatives = [relative for relative, _ in indexed]
    if len(relatives) != len(set(relatives)):
        raise ValueError("implementation source bundle contains duplicate paths")
    missing = [path for _, path in indexed if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"implementation source evidence missing: {missing}")
    digest = hashlib.sha256()
    for relative, path in sorted(indexed):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(semantic_file_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _relative_artifact_path(root: Path, value: str | Path) -> tuple[str, Path]:
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"publication artifact path must be repository-relative: {value}")
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"publication artifact escapes repository root: {value}")
    return resolved.relative_to(resolved_root).as_posix(), resolved


def artifact_bindings(
    root: Path, relative_paths: Sequence[str | Path]
) -> dict[str, dict[str, Any]]:
    bindings: dict[str, dict[str, Any]] = {}
    for value in relative_paths:
        relative, path = _relative_artifact_path(root, value)
        if relative in bindings:
            raise ValueError(f"duplicate publication artifact: {relative}")
        if not path.is_file():
            raise FileNotFoundError(f"publication artifact missing: {relative}")
        payload = _semantic_bytes(path)
        bindings[relative] = {
            "path": relative,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "hash_semantics": SEMANTIC_TEXT_HASH,
            "normalized_size_bytes": len(payload),
        }
    return dict(sorted(bindings.items()))


def create_staging_root(root: Path, scope: str) -> Path:
    if not scope or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in scope):
        raise ValueError(f"invalid publication scope: {scope!r}")
    stage = (
        root
        / ".pytest_cache"
        / "g4irsf11"
        / "publication"
        / scope
        / uuid.uuid4().hex
    )
    stage.mkdir(parents=True, exist_ok=False)
    return stage


def promote_staged_artifacts(
    stage_root: Path,
    root: Path,
    artifact_paths: Sequence[str | Path],
    expected_bindings: Mapping[str, Mapping[str, Any]],
    *,
    after_replace: Callable[[int, str], None] | None = None,
) -> None:
    """Atomically replace each file; the caller owns the completion commit point."""

    staged = artifact_bindings(stage_root, artifact_paths)
    if staged != {name: dict(value) for name, value in expected_bindings.items()}:
        raise ValueError("staged publication bindings changed before promotion")
    for index, value in enumerate(artifact_paths, start=1):
        relative, source = _relative_artifact_path(stage_root, value)
        _, destination = _relative_artifact_path(root, value)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
        promoted = artifact_bindings(root, [relative])
        if promoted.get(relative) != staged.get(relative):
            raise RuntimeError(f"promoted publication artifact differs from stage: {relative}")
        if after_replace is not None:
            after_replace(index, relative)


def _completion_document(
    metadata: Mapping[str, Any],
    *,
    status: str,
    artifacts: Mapping[str, Mapping[str, Any]],
    publication_id: str,
) -> dict[str, Any]:
    reserved = {"schema", "status", "artifacts", "publication_id"}
    overlap = reserved.intersection(metadata)
    if overlap:
        raise ValueError(f"completion metadata uses reserved keys: {sorted(overlap)}")
    return {
        "schema": COMPLETION_SCHEMA,
        "status": status,
        "publication_id": publication_id,
        **dict(metadata),
        "artifacts": {name: dict(value) for name, value in sorted(artifacts.items())},
    }


def begin_completion(
    path: Path,
    metadata: Mapping[str, Any],
    *,
    expected_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Invalidate any prior completion before shared artifacts are rewritten."""

    publication_id = uuid.uuid4().hex
    bindings = {
        name: dict(value) for name, value in sorted(expected_bindings.items())
    }
    document = _completion_document(
        metadata,
        status="IN_PROGRESS",
        artifacts=bindings,
        publication_id=publication_id,
    )
    atomic_write_json(path, document)
    return document


def complete_publication(
    path: Path,
    metadata: Mapping[str, Any],
    *,
    root: Path,
    artifact_paths: Sequence[str | Path],
    expected_bindings: Mapping[str, Mapping[str, Any]],
    publication_id: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{32}", publication_id):
        raise ValueError("publication_id must be a 32-character lowercase hex UUID")
    try:
        in_progress = read_json_object(path)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise RuntimeError("publication has no readable IN_PROGRESS commit record") from exc
    bindings = artifact_bindings(root, artifact_paths)
    expected = {
        name: dict(value) for name, value in sorted(expected_bindings.items())
    }
    expected_in_progress = _completion_document(
        metadata,
        status="IN_PROGRESS",
        artifacts=expected,
        publication_id=publication_id,
    )
    if in_progress != expected_in_progress:
        raise RuntimeError("publication IN_PROGRESS record differs from this transaction")
    if bindings != expected:
        raise RuntimeError(
            "final publication artifacts differ from the validated staging bindings"
        )
    document = _completion_document(
        metadata,
        status="COMPLETE",
        artifacts=expected,
        publication_id=publication_id,
    )
    atomic_write_json(path, document)
    return document


def completion_validation_errors(
    root: Path,
    manifest_path: Path,
    *,
    expected_scope: str,
    expected_source_bundle_sha256: str,
    expected_protocol_manifest_sha256: str,
    expected_artifact_paths: Sequence[str | Path],
    expected_metadata: Mapping[str, Any] | None = None,
) -> list[str]:
    """Re-hash every promoted artifact and reject incomplete/stale publications."""

    if not manifest_path.is_file():
        return [f"completion manifest is missing: {manifest_path}"]
    try:
        manifest = read_json_object(manifest_path)
    except (OSError, TypeError, ValueError) as exc:
        return [f"completion manifest cannot be decoded: {type(exc).__name__}: {exc}"]

    errors: list[str] = []
    if manifest.get("schema") != COMPLETION_SCHEMA:
        errors.append("completion manifest schema is unexpected")
    if manifest.get("status") != "COMPLETE":
        errors.append("completion manifest status is not COMPLETE")
    publication_id = str(manifest.get("publication_id") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", publication_id):
        errors.append("completion publication_id is invalid")
    if manifest.get("scope") != expected_scope:
        errors.append("completion manifest scope is unexpected")
    if not _SHA256_RE.fullmatch(expected_source_bundle_sha256):
        raise ValueError("expected source bundle SHA-256 is invalid")
    if manifest.get("implementation_source_bundle_sha256") != expected_source_bundle_sha256:
        errors.append("completion implementation source bundle differs from current sources")
    if manifest.get("protocol_manifest_sha256") != expected_protocol_manifest_sha256:
        errors.append("completion protocol manifest SHA-256 is unexpected")
    for key, expected in (expected_metadata or {}).items():
        if manifest.get(key) != expected:
            errors.append(f"completion metadata {key} is unexpected")

    expected_paths: list[str] = []
    for value in expected_artifact_paths:
        try:
            relative, _ = _relative_artifact_path(root, value)
        except ValueError as exc:
            raise ValueError(f"invalid expected publication artifact: {exc}") from exc
        expected_paths.append(relative)
    if len(expected_paths) != len(set(expected_paths)):
        raise ValueError("expected publication artifact list contains duplicates")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        errors.append("completion artifacts section is not an object")
        artifacts = {}
    if set(artifacts) != set(expected_paths):
        errors.append("completion artifact path set is not exact")

    for relative in expected_paths:
        descriptor = artifacts.get(relative)
        if not isinstance(descriptor, Mapping):
            errors.append(f"completion artifact descriptor is missing: {relative}")
            continue
        if descriptor.get("path") != relative:
            errors.append(f"completion artifact path binding differs: {relative}")
        if descriptor.get("hash_semantics") != SEMANTIC_TEXT_HASH:
            errors.append(f"completion artifact hash semantics differ: {relative}")
        try:
            _, path = _relative_artifact_path(root, relative)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"completion artifact is missing: {relative}")
            continue
        payload = _semantic_bytes(path)
        if descriptor.get("sha256") != hashlib.sha256(payload).hexdigest():
            errors.append(f"completion artifact SHA-256 mismatch: {relative}")
        if descriptor.get("normalized_size_bytes") != len(payload):
            errors.append(f"completion artifact normalized size mismatch: {relative}")
    return errors
