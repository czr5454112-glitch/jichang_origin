"""CLI for the independent G4IRSF14 Stage 14E artifact validator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.eval.g4irsf14_state_clone_validation import (
    CloneValidationError,
    validate_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository or staged artifact root",
    )
    arguments = parser.parse_args()
    try:
        result = validate_artifacts(arguments.root)
    except (CloneValidationError, OSError, UnicodeError) as error:
        print(f"G4IRSF14 state-clone artifact validation: FAIL: {error}")
        return 1
    print(
        "G4IRSF14 state-clone artifact validation: PASS\n"
        + json.dumps(result, sort_keys=True, separators=(",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
