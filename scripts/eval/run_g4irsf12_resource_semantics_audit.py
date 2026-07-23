"""Generate the static G4IRSF12-C resource-semantics evidence bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.eval.g4irsf12_resource_semantics import (  # noqa: E402
    build_static_audit,
    write_resource_semantics_artifacts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the protected map2 and reviewed legacy/current sources, then "
            "publish static R0--R4 resource-semantics evidence."
        )
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT,
        help="Artifact root; defaults to the repository root.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audit = build_static_audit(ROOT)
    manifest = write_resource_semantics_artifacts(audit, args.output_root)
    print(
        json.dumps(
            {
                "status": audit["status"],
                "map_semantic_sha256": audit["map_identity"]["semantic_sha256"],
                "node_count": audit["topology"]["summary"]["node_count"],
                "directed_edge_count": audit["topology"]["summary"][
                    "directed_edge_count"
                ],
                "reverse_pair_count": audit["topology"]["summary"][
                    "reverse_pair_count"
                ],
                "runtime_ab_executed": manifest["runtime_ab_executed"],
                "written_paths": manifest["written_paths"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
