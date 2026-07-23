"""Current G4IRSF12 implementation/source/config identity gate.

Historical G4IRSF11 evidence is bound to its producing commit by
``g4irsf11_historical_evidence``.  New G4IRSF12 runs use this independent gate:
the exact native module, the complete admitted source set, and the explicitly
selected candidate configs must all still match the pre-run claim.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
CURRENT_IDENTITY_SCHEMA = "czr005.g4irsf12.current_implementation_identity.v1"
TEXT_HASH_SEMANTICS = "sha256_after_crlf_cr_normalization_to_lf_for_text_files"
BINARY_HASH_SEMANTICS = "sha256_of_exact_binary_bytes"
IMPLEMENTATION_HASH_SEMANTICS = (
    "sha256_of_sorted_path_nul_exact_file_sha256_lf_for_sources_plus_binary"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hpp", ".py"}
_TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cmake",
    ".cpp",
    ".h",
    ".hpp",
    ".json",
    ".py",
    ".txt",
    ".yml",
    ".yaml",
}
_CLAIM_KEYS = {
    "schema",
    "implementation_sha256",
    "runtime_binary_sha256",
    "implementation_source_bundle_sha256",
    "candidate_config_sha256",
    "binary_path",
    "binary_hash_semantics",
    "implementation_hash_semantics",
    "source_file_count",
    "source_path_set_sha256",
    "source_hash_semantics",
    "config_paths",
    "config_path_set_sha256",
    "config_hash_semantics",
}


class CurrentIdentityError(ValueError):
    """Raised when a current implementation claim cannot be established."""


def _relative_file(root: Path, path: Path) -> tuple[str, Path]:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise CurrentIdentityError(f"identity input escapes repository root: {path}")
    if not resolved.is_file():
        raise CurrentIdentityError(f"identity input is missing: {path}")
    return resolved.relative_to(resolved_root).as_posix(), resolved


def _semantic_bytes(path: Path) -> bytes:
    payload = path.read_bytes()
    if path.suffix.lower() in _TEXT_SUFFIXES:
        payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return payload


def _file_sha256(path: Path, *, semantic: bool) -> str:
    payload = _semantic_bytes(path) if semantic else path.read_bytes()
    return hashlib.sha256(payload).hexdigest()


def _path_set_sha256(paths: Iterable[str]) -> str:
    return hashlib.sha256(
        "".join(f"{path}\n" for path in sorted(paths)).encode("utf-8")
    ).hexdigest()


def _bundle_sha256(indexed: Sequence[tuple[str, Path]]) -> str:
    relatives = [relative for relative, _ in indexed]
    if len(relatives) != len(set(relatives)):
        raise CurrentIdentityError("identity bundle contains duplicate paths")
    digest = hashlib.sha256()
    for relative, path in sorted(indexed):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_file_sha256(path, semantic=True).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _exact_implementation_sha256(indexed: Sequence[tuple[str, Path]]) -> str:
    relatives = [relative for relative, _ in indexed]
    if len(relatives) != len(set(relatives)):
        raise CurrentIdentityError("implementation bundle contains duplicate paths")
    digest = hashlib.sha256()
    for relative, path in sorted(indexed):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_file_sha256(path, semantic=False).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def current_source_paths(root: Path = ROOT) -> tuple[Path, ...]:
    """Return the complete admitted source set for a G4IRSF12 measurement."""

    root = root.resolve()
    candidates: set[Path] = set()
    cmake = root / "CMakeLists.txt"
    if cmake.is_file():
        candidates.add(cmake)
    for base in (root / "cpp" / "ics_core", root / "src" / "czr005"):
        if base.is_dir():
            candidates.update(
                path
                for path in base.rglob("*")
                if path.is_file() and path.suffix.lower() in _SOURCE_SUFFIXES
            )
    eval_root = root / "scripts" / "eval"
    if eval_root.is_dir():
        for path in eval_root.glob("*.py"):
            name = path.name
            if (
                name == "g4i_runtime.py"
                or name.startswith("g4irsf11")
                or name.startswith("run_g4irsf11")
                or name.startswith("validate_g4irsf11")
                or name.startswith("g4irsf12")
                or name.startswith("run_g4irsf12")
                or name.startswith("validate_g4irsf12")
            ):
                candidates.add(path)
    for base in (root / "scripts" / "data", root / "scripts" / "train"):
        if base.is_dir():
            candidates.update(path for path in base.rglob("*.py") if path.is_file())
    if not candidates:
        raise CurrentIdentityError("current G4IRSF12 implementation source set is empty")
    return tuple(sorted(candidates, key=lambda path: path.relative_to(root).as_posix()))


def _config_index(root: Path, config_paths: Sequence[Path]) -> list[tuple[str, Path]]:
    if not config_paths:
        raise CurrentIdentityError("at least one candidate config is required")
    indexed = [_relative_file(root, path) for path in config_paths]
    for relative, path in indexed:
        if path.suffix.lower() != ".json":
            raise CurrentIdentityError(f"candidate config must be JSON: {relative}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise CurrentIdentityError(
                f"candidate config cannot be decoded: {relative}: {type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise CurrentIdentityError(f"candidate config must contain an object: {relative}")
    relatives = [relative for relative, _ in indexed]
    if len(relatives) != len(set(relatives)):
        raise CurrentIdentityError("candidate config list contains duplicates")
    return sorted(indexed)


def create_current_identity_claim(
    *,
    root: Path = ROOT,
    binary_path: Path,
    config_paths: Sequence[Path],
) -> dict[str, Any]:
    """Compute the claim that must be frozen before a G4IRSF12 run."""

    root = root.resolve()
    binary_relative, binary = _relative_file(root, binary_path)
    source_index = [
        _relative_file(root, path) for path in current_source_paths(root)
    ]
    config_index = _config_index(root, config_paths)
    source_relatives = [relative for relative, _ in source_index]
    config_relatives = [relative for relative, _ in config_index]
    return {
        "schema": CURRENT_IDENTITY_SCHEMA,
        "implementation_sha256": _exact_implementation_sha256(
            [*source_index, (binary_relative, binary)]
        ),
        "runtime_binary_sha256": _file_sha256(binary, semantic=False),
        "implementation_source_bundle_sha256": _bundle_sha256(source_index),
        "candidate_config_sha256": _bundle_sha256(config_index),
        "binary_path": binary_relative,
        "binary_hash_semantics": BINARY_HASH_SEMANTICS,
        "implementation_hash_semantics": IMPLEMENTATION_HASH_SEMANTICS,
        "source_file_count": len(source_index),
        "source_path_set_sha256": _path_set_sha256(source_relatives),
        "source_hash_semantics": TEXT_HASH_SEMANTICS,
        "config_paths": config_relatives,
        "config_path_set_sha256": _path_set_sha256(config_relatives),
        "config_hash_semantics": TEXT_HASH_SEMANTICS,
    }


def current_identity_validation_errors(
    claim: Any,
    *,
    root: Path = ROOT,
    binary_path: Path,
    config_paths: Sequence[Path],
) -> list[str]:
    """Recompute the current identity and reject any pre-run/post-run drift."""

    errors: list[str] = []
    if not isinstance(claim, Mapping):
        return ["current identity claim must be an object"]
    missing = sorted(_CLAIM_KEYS - set(claim))
    extra = sorted(set(claim) - _CLAIM_KEYS)
    if missing:
        errors.append(f"current identity claim missing keys: {missing}")
    if extra:
        errors.append(f"current identity claim has unknown keys: {extra}")
    for field in (
        "implementation_sha256",
        "runtime_binary_sha256",
        "implementation_source_bundle_sha256",
        "candidate_config_sha256",
        "source_path_set_sha256",
        "config_path_set_sha256",
    ):
        if not _SHA256_RE.fullmatch(str(claim.get(field) or "")):
            errors.append(f"current identity {field} is not a SHA-256 digest")
    source_file_count = claim.get("source_file_count")
    if (
        not isinstance(source_file_count, int)
        or isinstance(source_file_count, bool)
        or source_file_count <= 0
    ):
        errors.append("current identity source_file_count must be a positive integer")
    try:
        observed = create_current_identity_claim(
            root=root,
            binary_path=binary_path,
            config_paths=config_paths,
        )
    except (OSError, TypeError, ValueError, CurrentIdentityError) as exc:
        return [*errors, f"current identity cannot be recomputed: {type(exc).__name__}: {exc}"]
    for field in sorted(_CLAIM_KEYS):
        if claim.get(field) != observed.get(field):
            errors.append(
                f"current identity {field} mismatch: "
                f"recorded={claim.get(field)!r} observed={observed.get(field)!r}"
            )
    return errors


def validate_current_identity_claim(
    claim: Any,
    *,
    root: Path = ROOT,
    binary_path: Path,
    config_paths: Sequence[Path],
) -> dict[str, Any]:
    errors = current_identity_validation_errors(
        claim,
        root=root,
        binary_path=binary_path,
        config_paths=config_paths,
    )
    return {
        "status": "PASS" if not errors else "FAIL",
        "schema": CURRENT_IDENTITY_SCHEMA,
        "errors": errors,
    }
