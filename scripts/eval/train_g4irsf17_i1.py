#!/usr/bin/env python3
"""Train and export the transparent G4IRSF17 I1 Phase-D candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
for _import_root in (ROOT, ROOT / "src"):
    if str(_import_root) not in sys.path:
        sys.path.insert(0, str(_import_root))

from czr005.g4irsf17.training import (  # noqa: E402
    PhaseDTrainingConfig,
    load_effect_feature_rows,
    train_phase_d,
    write_phase_d_artifacts,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Train/calibrate G17 I1 from matched feature/effect rows. The task-group "
            "final-audit partition remains sealed."
        )
    )
    parser.add_argument(
        "--effects",
        "--input",
        dest="effects",
        type=Path,
        required=True,
        help="JSON, JSONL/NDJSON, CSV, or .zst matched feature/effect rows",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT,
        help="Repository/output root (default: repository root)",
    )
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--ensemble-size", type=int, default=5)
    parser.add_argument("--pairwise-epochs", type=int, default=350)
    parser.add_argument("--mlp-epochs", type=int, default=350)
    parser.add_argument("--calibrator-epochs", type=int, default=600)
    parser.add_argument("--time-block-seconds", type=float, default=3_600.0)
    parser.add_argument(
        "--config-json",
        type=Path,
        help=(
            "Optional JSON object overriding PhaseDTrainingConfig fields. CLI training "
            "knobs above take precedence."
        ),
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Evaluate and print the decision without writing artifacts",
    )
    parser.add_argument(
        "--require-authorized",
        action="store_true",
        help="Return exit code 3 when the evidence produces a scientific no-go",
    )
    return parser


def _config(args: argparse.Namespace) -> PhaseDTrainingConfig:
    values: dict[str, Any] = {}
    if args.config_json is not None:
        parsed = json.loads(args.config_json.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("CONFIG_JSON_MUST_BE_OBJECT")
        unknown = sorted(set(parsed) - set(PhaseDTrainingConfig.__dataclass_fields__))
        if unknown:
            raise ValueError("UNKNOWN_CONFIG_FIELDS:" + ",".join(unknown))
        values.update(parsed)
    values.update(
        {
            "seed": args.seed,
            "ensemble_size": args.ensemble_size,
            "pairwise_epochs": args.pairwise_epochs,
            "mlp_epochs": args.mlp_epochs,
            "calibrator_epochs": args.calibrator_epochs,
            "time_block_seconds": args.time_block_seconds,
        }
    )
    if "split_fractions" in values:
        values["split_fractions"] = tuple(float(value) for value in values["split_fractions"])
    return PhaseDTrainingConfig(**values)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        rows = load_effect_feature_rows(args.effects)
        result = train_phase_d(rows, config=_config(args))
        written = {} if args.no_write else write_phase_d_artifacts(result, args.output_root)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INPUT_OR_CONFIGURATION_ERROR", "error": str(exc)}))
        return 2
    summary = result.summary_dict()
    summary["input"] = str(args.effects.resolve())
    summary["written"] = {name: str(path.resolve()) for name, path in written.items()}
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False))
    if args.require_authorized and not result.authorized:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
