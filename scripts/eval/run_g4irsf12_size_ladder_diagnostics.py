"""Collect G4IRSF12-D descriptors and write fail-closed diagnostic outputs.

The command never launches a runtime or constructs a scaled workload.  With
no descriptors it initializes truthful, header-only tables and a
``PROTOCOL_READY_NO_ATTEMPTS`` report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.g4irsf12_size_ladder import (  # noqa: E402
    OUTPUT_PATHS,
    write_diagnostic_outputs,
)


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _load_descriptor(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        # Keep malformed attempts in the evidence table instead of silently
        # dropping them.  The sentinel intentionally fails schema validation.
        return {
            "attempt_id": path.stem,
            "candidate_id": "",
            "attempt_index": 0,
            "descriptor_load_error": f"{type(exc).__name__}: {exc}",
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--descriptor",
        type=Path,
        action="append",
        default=[],
        help="Result descriptor JSON; may be repeated.",
    )
    parser.add_argument(
        "--descriptor-dir",
        type=Path,
        help="Read every *.json descriptor in deterministic filename order.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT,
        help="Repository root receiving the four declared D outputs.",
    )
    parser.add_argument(
        "--require-valid-descriptors",
        action="store_true",
        help="Return 2 if any supplied descriptor is invalid; negative valid runs remain evidence.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = list(args.descriptor)
    if args.descriptor_dir is not None:
        paths.extend(sorted(args.descriptor_dir.glob("*.json")))
    resolved: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        key = path.resolve()
        if key not in seen:
            resolved.append(path)
            seen.add(key)
    descriptors = [_load_descriptor(path) for path in resolved]
    evaluations, output_paths = write_diagnostic_outputs(
        descriptors,
        root=args.output_root.resolve(),
    )
    invalid_count = sum(
        row.get("descriptor_status") != "VALID" for row in evaluations
    )
    payload = {
        "status": (
            "PROTOCOL_READY_NO_ATTEMPTS"
            if not evaluations
            else "PARTIAL_WITH_EXPLICIT_BLOCKER"
            if any(row.get("promotion_decision", "").startswith("HOLD") for row in evaluations)
            else "DIAGNOSTIC_EVIDENCE_RECORDED"
        ),
        "attempt_count": len(evaluations),
        "invalid_descriptor_count": invalid_count,
        "outputs": [
            path.relative_to(args.output_root.resolve()).as_posix()
            for path in output_paths
        ],
        "scale_run_launched": False,
        "declared_outputs": dict(OUTPUT_PATHS),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if args.require_valid_descriptors and invalid_count:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
