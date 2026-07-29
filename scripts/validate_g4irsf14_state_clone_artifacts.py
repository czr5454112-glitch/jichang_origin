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
    validate_artifact_protocol,
    validate_artifacts,
)
from scripts.eval.g4irsf14_opportunity_census import (
    OpportunityCensusError,
    validate_published_blocker_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository or staged artifact root",
    )
    parser.add_argument(
        "--mode",
        choices=("formal", "protocol", "blocker"),
        default="formal",
        help=(
            "formal retains the causal PASS blocker; protocol validates the "
            "content-addressed formal six-artifact contract without "
            "promotion; blocker validates the published fail-closed "
            "opportunity-census bundle against its current binary, source, "
            "and protected inputs"
        ),
    )
    arguments = parser.parse_args()
    try:
        if arguments.mode == "formal":
            result = validate_artifacts(arguments.root)
        elif arguments.mode == "protocol":
            result = validate_artifact_protocol(arguments.root)
        else:
            result = validate_published_blocker_bundle(arguments.root)
    except (
        CloneValidationError,
        OpportunityCensusError,
        OSError,
        UnicodeError,
    ) as error:
        print(f"G4IRSF14 state-clone artifact validation: FAIL: {error}")
        return 1
    if arguments.mode == "blocker":
        print(
            "G4IRSF14 state-clone artifact validation: "
            "PARTIAL_WITH_EXPLICIT_BLOCKER_VALID\n"
            + json.dumps(result, sort_keys=True, separators=(",", ":"))
        )
        return 0
    if arguments.mode == "protocol":
        print(
            "G4IRSF14 state-clone artifact validation: "
            "PROTOCOL_VALID_NOT_FORMAL_PASS\n"
            + json.dumps(result, sort_keys=True, separators=(",", ":"))
        )
        return 0
    print(
        "G4IRSF14 state-clone artifact validation: PASS\n"
        + json.dumps(result, sort_keys=True, separators=(",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
