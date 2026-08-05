#!/usr/bin/env python3
"""Reconstruct the host-bound EOL bytes of the sealed G4IRSF15 source bundle.

The G4IRSF15 descriptor manifest was generated from a Windows working tree and
binds raw working-tree bytes.  Git stores the same text with normalized LF
bytes, so a fresh Linux checkout cannot otherwise satisfy that historical raw
byte identity.  This helper is deliberately narrow: it permits EOL-only
reconstruction, pins the sealed source bundle, and requires every reconstructed
file to match the historical byte count and SHA-256 exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any, Mapping, Sequence


DESCRIPTOR_MANIFEST = Path(
    "artifacts/datasets/g4irsf15_causal_descriptor_manifest.json"
)
SEALED_SOURCE_BUNDLE_SHA256 = (
    "38f4ab3dc4cf45b67499e1da0e46208c63e55288f32fb9ae5f877c168172a7a5"
)
G4IRSF15_SEAL = "8f3106b116f2648b6fa2e30bc8960659739d3a58"
OFFLINE_SAMPLING_PATH = "outputs/tables/g4irsf13_per_bag_delta.csv"
SEALED_OFFLINE_SAMPLING_SHA256 = (
    "7dc77dcf5ff44b067a1cb4a04169a466b9de0fafa5d27bc73aca0f2333db7167"
)
SEALED_OFFLINE_SAMPLING_BYTE_COUNT = 29_121_147

# These are the only files whose historical Windows working-tree bytes mixed
# CRLF and LF.  Values are inclusive 1-based line-ending ordinals that remain
# LF; every other LF in the normalized Git text is reconstructed as CRLF.
MIXED_LF_RANGES: Mapping[str, tuple[tuple[int, int], ...]] = {
    "cpp/ics_core/bindings/czr005_cpp.cpp": (
        (34, 36),
        (5314, 5317),
    ),
    "cpp/ics_core/runtime/event_driven_junction.hpp": (
        (34, 36),
        (90, 93),
        (98, 403),
        (2293, 2338),
        (2585, 2753),
        (2841, 2846),
        (2869, 2916),
        (3011, 3047),
        (4417, 4426),
        (4454, 4461),
        (4523, 4538),
        (9907, 9912),
        (10232, 10235),
        (10261, 10264),
        (10323, 10365),
        (10412, 10422),
        (10505, 10526),
    ),
    "pyproject.toml": ((10, 13),),
}


class ReconstructionError(RuntimeError):
    """Raised when a source cannot be restored by the sealed EOL contract."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalized_lf(payload: bytes, *, label: str) -> bytes:
    normalized = payload.replace(b"\r\n", b"\n")
    if b"\r" in normalized:
        raise ReconstructionError(f"NON_EOL_CR:{label}")
    return normalized


def _lf_ordinals(
    ranges: Sequence[tuple[int, int]], *, line_count: int, label: str
) -> set[int]:
    ordinals: set[int] = set()
    previous_end = 0
    for start, end in ranges:
        if start <= previous_end or end < start or end > line_count:
            raise ReconstructionError(f"INVALID_LF_RANGE:{label}:{start}:{end}")
        ordinals.update(range(start, end + 1))
        previous_end = end
    return ordinals


def _rebuild_eol(
    normalized: bytes,
    *,
    keep_lf_ranges: Sequence[tuple[int, int]],
    label: str,
) -> bytes:
    line_count = normalized.count(b"\n")
    keep_lf = _lf_ordinals(
        keep_lf_ranges, line_count=line_count, label=label
    )
    result = bytearray()
    start = 0
    ordinal = 0
    for index, value in enumerate(normalized):
        if value != 10:
            continue
        ordinal += 1
        result.extend(normalized[start:index])
        result.extend(b"\n" if ordinal in keep_lf else b"\r\n")
        start = index + 1
    result.extend(normalized[start:])
    return bytes(result)


def _safe_source_path(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if (
        not relative
        or pure.is_absolute()
        or ".." in pure.parts
        or pure.as_posix() != relative
    ):
        raise ReconstructionError(f"UNSAFE_SOURCE_PATH:{relative}")
    resolved_root = root.resolve()
    target = (resolved_root / Path(*pure.parts)).resolve()
    try:
        target.relative_to(resolved_root)
    except ValueError as exc:
        raise ReconstructionError(f"SOURCE_PATH_ESCAPE:{relative}") from exc
    return target


def _reconstruct_bound_file(
    root: Path,
    *,
    relative: str,
    expected_sha256: str,
    expected_byte_count: int,
    keep_lf_candidates: Sequence[Sequence[tuple[int, int]]],
) -> bool:
    path = _safe_source_path(root, relative)
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise ReconstructionError(f"SOURCE_READ_FAILED:{relative}") from exc
    if (
        len(current) == expected_byte_count
        and _sha256(current) == expected_sha256
    ):
        return False

    normalized = _normalized_lf(current, label=relative)
    candidates = [
        _rebuild_eol(
            normalized,
            keep_lf_ranges=keep_lf_ranges,
            label=relative,
        )
        for keep_lf_ranges in keep_lf_candidates
    ]
    replacement = next(
        (
            candidate
            for candidate in candidates
            if len(candidate) == expected_byte_count
            and _sha256(candidate) == expected_sha256
        ),
        None,
    )
    if replacement is None:
        raise ReconstructionError(f"NON_EOL_SOURCE_DRIFT:{relative}")
    if _normalized_lf(replacement, label=relative) != normalized:
        raise ReconstructionError(f"SEMANTIC_RECONSTRUCTION_DRIFT:{relative}")
    path.write_bytes(replacement)
    persisted = path.read_bytes()
    if (
        len(persisted) != expected_byte_count
        or _sha256(persisted) != expected_sha256
    ):
        raise ReconstructionError(f"POST_RECONSTRUCTION_DRIFT:{relative}")
    return True


def reconstruct_source_identity(
    root: Path,
    source_identity: Mapping[str, Any],
    *,
    expected_bundle_sha256: str | None = SEALED_SOURCE_BUNDLE_SHA256,
    mixed_lf_ranges: Mapping[
        str, Sequence[tuple[int, int]]
    ] = MIXED_LF_RANGES,
) -> dict[str, Any]:
    if (
        expected_bundle_sha256 is not None
        and source_identity.get("source_bundle_sha256")
        != expected_bundle_sha256
    ):
        raise ReconstructionError("UNEXPECTED_SOURCE_BUNDLE")
    files = source_identity.get("files")
    if not isinstance(files, list) or not files:
        raise ReconstructionError("SOURCE_FILES_MISSING")

    restored: list[str] = []
    exact: list[str] = []
    seen: set[str] = set()
    for binding in files:
        if not isinstance(binding, dict):
            raise ReconstructionError("SOURCE_BINDING_NOT_OBJECT")
        relative = str(binding.get("path", ""))
        if relative in seen:
            raise ReconstructionError(f"SOURCE_PATH_DUPLICATE:{relative}")
        seen.add(relative)
        expected_sha256 = binding.get("sha256")
        expected_byte_count = binding.get("byte_count")
        if (
            not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or not isinstance(expected_byte_count, int)
            or expected_byte_count < 0
        ):
            raise ReconstructionError(f"INVALID_SOURCE_BINDING:{relative}")

        keep_lf_candidates: list[Sequence[tuple[int, int]]] = []
        if relative in mixed_lf_ranges:
            keep_lf_candidates.append(mixed_lf_ranges[relative])
        keep_lf_candidates.append(())
        changed = _reconstruct_bound_file(
            root,
            relative=relative,
            expected_sha256=expected_sha256,
            expected_byte_count=expected_byte_count,
            keep_lf_candidates=keep_lf_candidates,
        )
        (restored if changed else exact).append(relative)

    unused_mixed = set(mixed_lf_ranges).difference(seen)
    if unused_mixed:
        raise ReconstructionError(
            "MIXED_EOL_BINDING_MISSING:" + ",".join(sorted(unused_mixed))
        )

    for binding in files:
        relative = str(binding["path"])
        payload = _safe_source_path(root, relative).read_bytes()
        if (
            len(payload) != binding["byte_count"]
            or _sha256(payload) != binding["sha256"]
        ):
            raise ReconstructionError(f"POST_RECONSTRUCTION_DRIFT:{relative}")

    return {
        "exact_file_count": len(exact),
        "restored_file_count": len(restored),
        "restored_paths": restored,
        "source_file_count": len(files),
        "status": "PASS_G4IRSF15_SEALED_EOL_RECONSTRUCTION",
    }


def prepare(root: Path) -> dict[str, Any]:
    resolved_root = root.resolve()
    try:
        head = subprocess.run(
            ["git", "-C", str(resolved_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReconstructionError("SEALED_HEAD_READ_FAILED") from exc
    if head != G4IRSF15_SEAL:
        raise ReconstructionError(f"UNEXPECTED_SEALED_HEAD:{head}")

    manifest_path = resolved_root / DESCRIPTOR_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReconstructionError("DESCRIPTOR_MANIFEST_READ_FAILED") from exc
    source_identity = manifest.get("source_identity")
    if not isinstance(source_identity, dict):
        raise ReconstructionError("SOURCE_IDENTITY_MISSING")
    result = reconstruct_source_identity(root, source_identity)

    offline = manifest.get("offline_sampling_input")
    if (
        not isinstance(offline, dict)
        or offline.get("path") != OFFLINE_SAMPLING_PATH
        or offline.get("sha256") != SEALED_OFFLINE_SAMPLING_SHA256
        or offline.get("runtime_feature_allowed") is not False
    ):
        raise ReconstructionError("UNEXPECTED_OFFLINE_SAMPLING_BINDING")
    offline_restored = _reconstruct_bound_file(
        resolved_root,
        relative=OFFLINE_SAMPLING_PATH,
        expected_sha256=SEALED_OFFLINE_SAMPLING_SHA256,
        expected_byte_count=SEALED_OFFLINE_SAMPLING_BYTE_COUNT,
        keep_lf_candidates=((),),
    )
    result["offline_sampling_restored"] = offline_restored
    result["offline_sampling_status"] = "EXACT_SEALED_BYTES"
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", type=Path, required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = prepare(args.root)
    except ReconstructionError as exc:
        print(f"G4IRSF16_PREDECESSOR_EOL_ERROR:{exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
