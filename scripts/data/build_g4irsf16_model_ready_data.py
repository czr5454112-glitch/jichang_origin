"""Build the G4IRSF16 Stage-16A model-ready Parquet datasets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from czr005.g4irsf16.data import (  # noqa: E402
    DATASET_OUTPUTS,
    SPLIT_MANIFEST_OUTPUT,
    build_and_write_model_ready_data,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Project the sealed G4IRSF15 formal labels into separated, "
            "leakage-safe G4IRSF16 I3/I4/H_system Parquet datasets."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root (defaults to the root containing this script)",
    )
    parser.add_argument(
        "--runtime-feature-cache",
        type=Path,
        default=None,
        help=(
            "optional exact frozen-F2 runtime feature cache (JSONL, JSONL.zst, "
            "JSON, or Parquet); absent dynamic features stay Arrow null"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    build, written = build_and_write_model_ready_data(
        args.root,
        runtime_feature_cache=args.runtime_feature_cache,
    )
    print("G4IRSF16_STAGE16A_MODEL_READY_DATA_BUILT")
    for name in DATASET_OUTPUTS:
        print(f"{name}_rows={len(build.rows_by_dataset[name])}")
        print(f"{name}_path={written[name]}")
    print(f"split_manifest={written['split_manifest']}")
    print(f"split_rows={build.split_manifest['split_row_counts']}")
    print(
        "final_audit_status="
        f"{build.split_manifest['final_audit']['status']}"
    )
    print(
        "final_audit_row_level_results_consumed_for_selection="
        f"{build.split_manifest['final_audit']['row_level_results_consumed_for_selection']}"
    )
    if written["split_manifest"] != args.root.resolve() / SPLIT_MANIFEST_OUTPUT:
        raise AssertionError("split manifest output drifted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
