from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from czr005.io.legacy_tasks import (
    expand_tasks,
    parse_legacy_tasks,
    summarize_tasks,
    write_task_jsonl,
    write_task_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert legacy inputdata.txt to normalized JSONL.")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "legacy" / "jichang_origin_readonly" / "inputdata.txt",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=ROOT / "data" / "processed" / "tasks" / "inputdata_summary.json",
    )
    args = parser.parse_args()

    _, raw_tasks = parse_legacy_tasks(args.input)
    expanded = expand_tasks(raw_tasks)
    write_task_jsonl(expanded, args.output)
    summary = summarize_tasks(raw_tasks, expanded)
    write_task_summary(summary, args.summary_output)
    print(
        f"wrote {args.output} raw={summary['raw_task_count']} "
        f"expanded={summary['expanded_task_count']}"
    )


if __name__ == "__main__":
    main()

