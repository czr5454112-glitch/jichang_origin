from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from czr005.io.legacy_map import parse_legacy_map, write_map_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert legacy map2.txt to normalized JSON.")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "legacy" / "jichang_origin_readonly" / "map2.txt",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "processed" / "maps" / "map2.json",
    )
    args = parser.parse_args()

    parsed = parse_legacy_map(args.input)
    write_map_json(parsed, args.output)
    print(
        f"wrote {args.output} "
        f"nodes={parsed.header.node_count} edges={len(parsed.edges)} starts={len(parsed.start_nodes)}"
    )


if __name__ == "__main__":
    main()

