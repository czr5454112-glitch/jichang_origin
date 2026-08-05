#!/usr/bin/env python3
"""Run sealed G4IRSF15 formal validation with one pinned null fix.

The sealed validator treats an existing ``pilot_round: null`` in the formal
plan as if it were directly convertible to ``int``.  This compatibility entry
loads the exact sealed validator bytes, applies one audited in-memory source
replacement, and then invokes the original formal validation.  It never edits
the sealed worktree, plan, evidence, or validator on disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from typing import Sequence


G4IRSF15_SEAL = "8f3106b116f2648b6fa2e30bc8960659739d3a58"
SEALED_VALIDATOR_SHA256 = (
    "7e43047065f1d9ec253f2ecf1f0c562af51e849e13749120d3df6516cfdf5615"
)
VALIDATOR_RELATIVE_PATH = Path(
    "scripts/validate_g4irsf15_causal_campaign.py"
)
OLD_FRAGMENT = '    pilot_round = int(plan.get("pilot_round", 1))'
NEW_FRAGMENT = "\n".join(
    (
        '    pilot_round_value = plan.get("pilot_round")',
        "    pilot_round = (",
        "        1 if pilot_round_value is None else int(pilot_round_value)",
        "    )",
    )
)


class CompatibilityError(RuntimeError):
    """Raised when the sealed validator is not the exact supported source."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def patched_validator_source(path: Path) -> tuple[str, str]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise CompatibilityError("SEALED_VALIDATOR_READ_FAILED") from exc
    if _sha256(payload) != SEALED_VALIDATOR_SHA256:
        raise CompatibilityError("SEALED_VALIDATOR_SHA256_DRIFT")
    try:
        source = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CompatibilityError("SEALED_VALIDATOR_NOT_UTF8") from exc
    if source.count(OLD_FRAGMENT) != 1 or NEW_FRAGMENT in source:
        raise CompatibilityError("FORMAL_NULL_PATCH_CONTEXT_DRIFT")
    patched = source.replace(OLD_FRAGMENT, NEW_FRAGMENT)
    return patched, _sha256(patched.encode("utf-8"))


def load_patched_validator(path: Path) -> ModuleType:
    source, patched_sha256 = patched_validator_source(path)
    module_name = f"_g4irsf15_formal_compat_{patched_sha256[:16]}"
    module = ModuleType(module_name)
    module.__file__ = str(path.resolve())
    module.__package__ = None
    module.__dict__["__g4irsf16_compatibility__"] = {
        "original_sha256": SEALED_VALIDATOR_SHA256,
        "patch": "FORMAL_NULL_PILOT_ROUND_DEFAULT_ONLY",
        "patched_sha256": patched_sha256,
    }
    sys.modules[module_name] = module
    try:
        exec(compile(source, module.__file__, "exec"), module.__dict__)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def run_formal(*, root: Path, validator: Path) -> int:
    resolved_root = root.resolve()
    expected_validator = (resolved_root / VALIDATOR_RELATIVE_PATH).resolve()
    if validator.resolve() != expected_validator:
        raise CompatibilityError("VALIDATOR_PATH_NOT_SEALED_ROOT")
    try:
        head = subprocess.run(
            ["git", "-C", str(resolved_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CompatibilityError("SEALED_HEAD_READ_FAILED") from exc
    if head != G4IRSF15_SEAL:
        raise CompatibilityError(f"UNEXPECTED_SEALED_HEAD:{head}")

    module = load_patched_validator(expected_validator)
    marker = dict(module.__dict__["__g4irsf16_compatibility__"])
    marker["sealed_head"] = head
    marker["status"] = "PASS_G4IRSF16_FORMAL_NULL_COMPATIBILITY_LOADED"
    print(json.dumps(marker, sort_keys=True))
    result = module.main(
        ["--root", str(resolved_root), "--scope", "formal"]
    )
    return int(result)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", type=Path, required=True)
    result.add_argument("--validator", type=Path, required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return run_formal(root=args.root, validator=args.validator)
    except CompatibilityError as exc:
        print(f"G4IRSF16_FORMAL_COMPATIBILITY_ERROR:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
