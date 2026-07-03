from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DEFAULT = ROOT / "artifacts" / "tasks" / "g4irsf2_high_flow_manifest.json"
OUTPUT_DEFAULT = ROOT / "artifacts" / "tasks" / "g4irsf2_high_flow_tasks.jsonl"
REPORT_DIR = ROOT / "outputs" / "reports"
TABLE_DIR = ROOT / "outputs" / "tables"
GOVERNANCE_DOC = ROOT / "docs" / "czr005_project_governance.md"

HASH_TABLE = TABLE_DIR / "g4irsf3_high_flow_file_hash_audit.csv"
REPRO_REPORT = REPORT_DIR / "g4irsf3_high_flow_reproducibility_report.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return value


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _line_count(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            count += chunk.count(b"\n")
    return count


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _regenerate(manifest: dict[str, Any], manifest_path: Path, output_path: Path, seed: int) -> dict[str, Any]:
    _prepare_imports()
    from scripts.data.g4irsf2_generate_high_flow_from_original_rules import run_generation

    class Args:
        ics_origin_root = manifest.get("ics_origin_root")
        generation_level = manifest["generation_level"]
        flow_scale = int(manifest["flow_scale"])
        time_compression = float(manifest["time_compression"])
        rolling_days = int(manifest["rolling_days"])
        output = str(output_path)
        manifest = str(manifest_path)

    args = Args()
    args.seed = int(seed)
    return run_generation(args)


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = _resolve(args.manifest)
    output_path = _resolve(args.output)
    manifest = _load_manifest(manifest_path)
    expected_sha = str(manifest.get("task_output_sha256", ""))
    expected_count = int(manifest.get("task_count", 0))
    command = (
        "python scripts/data/g4irsf3_reproduce_high_flow_tasks.py "
        f"--manifest {manifest_path.relative_to(ROOT).as_posix()} "
        f"--output {output_path.relative_to(ROOT).as_posix()} --verify-sha256"
    )

    regenerated = False
    skip_reason = ""
    before_sha = ""
    if output_path.exists():
        before_sha = _sha256(output_path)
        if expected_sha and before_sha == expected_sha and not args.force_regenerate:
            skip_reason = "existing_file_sha256_matches_manifest"
        else:
            regenerated = True
            manifest = _regenerate(manifest, manifest_path, output_path, args.seed)
    else:
        regenerated = True
        manifest = _regenerate(manifest, manifest_path, output_path, args.seed)

    actual_sha = _sha256(output_path)
    line_count = _line_count(output_path)
    size_bytes = output_path.stat().st_size
    status = "PASS" if (not expected_sha or actual_sha == expected_sha) and line_count == expected_count else "FAIL"
    if args.verify_sha256 and status != "PASS":
        verify_message = (
            f"hash/count verification failed: expected_sha={expected_sha} actual_sha={actual_sha} "
            f"expected_count={expected_count} line_count={line_count}"
        )
    else:
        verify_message = ""

    rows = [
        {
            "artifact": output_path.relative_to(ROOT).as_posix(),
            "manifest": manifest_path.relative_to(ROOT).as_posix(),
            "expected_sha256": expected_sha,
            "actual_sha256": actual_sha,
            "file_size_bytes": size_bytes,
            "line_count": line_count,
            "task_count_from_manifest": expected_count,
            "regenerated_this_run": regenerated,
            "skip_reason": skip_reason,
            "generation_level": manifest.get("generation_level", ""),
            "topology_changed": manifest.get("topology_changed", ""),
            "verification_status": status,
            "regeneration_command": command,
        }
    ]
    _write_csv(
        HASH_TABLE,
        rows,
        [
            "artifact",
            "manifest",
            "expected_sha256",
            "actual_sha256",
            "file_size_bytes",
            "line_count",
            "task_count_from_manifest",
            "regenerated_this_run",
            "skip_reason",
            "generation_level",
            "topology_changed",
            "verification_status",
            "regeneration_command",
        ],
    )
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPRO_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF3 High-Flow Reproducibility Report",
                "",
                f"governance_doc: {GOVERNANCE_DOC.relative_to(ROOT).as_posix()}",
                "topology_changed: false",
                f"data_generation_rule_source: {manifest.get('generation_level', '')}",
                "runtime_full_cie_astar_fallback: false",
                "",
                "## Result",
                "",
                f"verification_status: `{status}`",
                f"expected_sha256: `{expected_sha}`",
                f"actual_sha256: `{actual_sha}`",
                f"file_size_bytes: `{size_bytes}`",
                f"line_count: `{line_count}`",
                f"task_count_from_manifest: `{expected_count}`",
                f"regenerated_this_run: `{regenerated}`",
                f"regeneration_command: `{command}`",
                "",
                "The large JSONL task stream stays out of Git. This script either verifies the local copy against the tracked manifest or regenerates it through the audited G4IRSF2 rule-preserving generator.",
                "",
                f"note: `{verify_message or skip_reason or 'generated_or_verified'}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if args.verify_sha256 and status != "PASS":
        raise SystemExit(verify_message)
    return rows[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reproduce and verify the G4IRSF2 high-flow JSONL task stream for G4IRSF3.")
    parser.add_argument("--manifest", default=str(MANIFEST_DEFAULT))
    parser.add_argument("--output", default=str(OUTPUT_DEFAULT))
    parser.add_argument("--verify-sha256", action="store_true")
    parser.add_argument("--force-regenerate", action="store_true")
    parser.add_argument("--seed", type=int, default=20260703)
    return parser


if __name__ == "__main__":
    result = run(build_parser().parse_args())
    print(
        "g4irsf3 high-flow reproducibility: "
        f"status={result['verification_status']} sha={str(result['actual_sha256'])[:12]} "
        f"lines={result['line_count']}"
    )
