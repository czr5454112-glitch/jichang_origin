"""Preserve the completed Feng suite as byte-verified GitHub release volumes.

This exporter never edits frozen inputs/results. Each archive is independently
readable; files.jsonl maps original repository-relative paths to volume and SHA.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


SCHEMA = "czr005.feng_suite.release.v1"
INVENTORY = "outputs/evidence/paper_suite_20260907/publication_inventory_20260908/inventory.json"
PLAN = "outputs/evidence/paper_suite_20260907/frozen_plan_v6/plan.json"
PLAN_SHA = "7a4369b09efb8b2935a7197d6919375be730ffb5ee17a8cad55718fcdb262daf"
REPORT = "outputs/reports/feng_paper_suite_20260907/campaign_20260907T103048Z_87ca6ab5b9/snapshot.json"
AUDIT = "outputs/evidence/paper_suite_20260907/final576_completion_review_20260908/verification.json"
EXCLUDED = {"artifacts/tasks/cie_component_activation/load_manifest.json", "feng_cie_dh_microtests.jsonl"}
OUTPUT_ROOTS = (
    "outputs/evidence/feng_java_consistency_recheck_20260906",
    "outputs/evidence/g31_fault_potential_repair_20260907",
    "outputs/evidence/hca_time_label_repair_v2_20260906",
    "outputs/evidence/paper_suite_20260907",
    "outputs/reports/feng_paper_suite_20260907",
    "outputs/runtime/feng_dh_paper_suite_v6_20260907",
    "outputs/runtime/feng_paper_suite_20260907",
    "outputs/runtime/g31_fault_paper_suite_validation_20260907",
    "outputs/runtime/g31_fault_potential_repair_20260907",
    "outputs/runtime/g31_paper_suite_fault_preflight_20260907",
    "outputs/runtime/g31_tarau_paper_suite_20260907",
    "outputs/runtime/hca_paper_suite_v3_20260907",
    "outputs/runtime/hca_time_label_repair_v2_20260906",
)
STORED_EXTENSIONS = {".gz", ".zip", ".zst", ".png", ".jpg", ".jpeg", ".pdf"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def git_files(root: Path, *args: str) -> list[str]:
    raw = subprocess.check_output(["git", *args, "-z"], cwd=root)
    return [x.decode("utf-8") for x in raw.split(b"\0") if x]


def collect(root: Path) -> tuple[list[dict], dict]:
    inventory = json.loads((root / INVENTORY).read_text(encoding="utf-8"))
    snapshot = json.loads((root / REPORT).read_text(encoding="utf-8"))
    audit = json.loads((root / AUDIT).read_text(encoding="utf-8"))
    if sha(root / PLAN) != PLAN_SHA or snapshot["status"] != "COMPLETE" or audit["status"] != "PASS":
        raise ValueError("The frozen complete suite and independent acceptance must match")
    if inventory["expected_cells"] != 576 or snapshot["observed_cell_rows"] != 576:
        raise ValueError("Expected exactly 576 registered cells")
    selected: set[str] = set()
    expected: dict[str, str] = {}

    def add(rel: str, expected_sha: str | None = None) -> None:
        path = root / rel
        resolved = path.resolve()
        resolved.relative_to(root)
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or nonregular publication file: {rel}")
        name = path.relative_to(root).as_posix()
        if name in EXCLUDED:
            return
        selected.add(name)
        if expected_sha:
            prior = expected.setdefault(name, expected_sha)
            if prior != expected_sha:
                raise ValueError(f"Conflicting recorded file identities: {name}")

    for item in inventory["all_cell_files_for_optional_exact_directory_restore"]:
        add(item["path"])
    for item in inventory["selected_cell_files"]:
        add(item["path"], item.get("declared_archive_sha256"))
    for item in inventory["support"]:
        add(item["path"], item.get("sha256"))
    for item in inventory["inputs"]:
        add(item["source_path"], item["source_sha256"])
    production_builds: set[str] = set()
    plan = json.loads((root / PLAN).read_text(encoding="utf-8"))
    for cell in plan["cells"]:
        spec = json.loads(Path(cell["spec_path"]).read_text(encoding="utf-8"))
        if spec.get("classes_dir") and spec["classes_dir"] not in production_builds:
            production_builds.add(spec["classes_dir"])
            build_identity = Path(spec["classes_dir"]) / "build_identity.json"
            add(build_identity.relative_to(root).as_posix(), spec["build_identity_sha256"])

    # Keep the full related preflight, provenance and orchestration history too.
    for prefix in OUTPUT_ROOTS:
        for path in (root / prefix).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                add(path.relative_to(root).as_posix())
    for rel in git_files(root, "ls-files", "--others", "--exclude-standard"):
        if not rel.startswith("outputs/") or rel.startswith(("outputs/reports/feng_four_", "outputs/reports/hca_time_label_")):
            add(rel)
    for rel in git_files(root, "diff", "--name-only", "HEAD"):
        if rel not in EXCLUDED:
            add(rel)

    # Keep original bytes for the entire previously frozen source snapshot.
    source_zip = root / "outputs/evidence/g31_fault_potential_repair_20260907/final_build_v1/source_snapshot.zip"
    with zipfile.ZipFile(source_zip) as zf:
        for name in zf.namelist():
            if not name.endswith("/"):
                original = hashlib.sha256(zf.read(name)).hexdigest()
                add(name, original)

    rows = []
    for rel in sorted(selected):
        stat = (root / rel).stat()
        rows.append({"path": rel, "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                     "expected_sha256": expected.get(rel)})
    formal = {item["path"] for item in inventory["all_cell_files_for_optional_exact_directory_restore"]}
    if not formal.issubset(selected):
        raise ValueError("Publication selection omitted registered cell files")
    coverage = {"registered_cells": 576, "formal_cell_file_count": len(formal),
                "formal_cell_bytes": sum((root / x).stat().st_size for x in formal),
                "formal_cell_directories_restorable": True,
                "native_archives_with_recorded_sha": sum(bool(x.get("declared_archive_sha256")) for x in inventory["selected_cell_files"]),
                "input_source_files": len({x["source_path"] for x in inventory["inputs"]}),
                "scope": "base480 plus fault96; also preserves related preflights and original provenance",
                "excluded_unrelated_or_unversioned_files": sorted(EXCLUDED)}
    return rows, coverage


def groups(rows: list[dict], maximum_bytes: int) -> list[list[dict]]:
    # A conservative uncompressed bound keeps every ZIP safely below 2 GB.
    batches: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for row in rows:
        if row["bytes"] > maximum_bytes:
            raise ValueError(f"Single file exceeds configured volume bound: {row['path']}")
        if current and size + row["bytes"] > maximum_bytes:
            batches.append(current)
            current, size = [], 0
        current.append(row)
        size += row["bytes"]
    if current:
        batches.append(current)
    return batches


def build_part(root: Path, out: Path, index: int, rows: list[dict]) -> tuple[dict, list[dict]]:
    name = f"feng-suite-20260908-part-{index:03d}.zip"
    target = out / name
    manifest_rows = []
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=4, allowZip64=True) as archive:
        for row in rows:
            path = root / row["path"]
            before = path.stat()
            if before.st_size != row["bytes"] or before.st_mtime_ns != row["mtime_ns"]:
                raise ValueError(f"Source changed after selection: {row['path']}")
            info = zipfile.ZipInfo(row["path"], date_time=(2026, 9, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if path.suffix.lower() in STORED_EXTENSIONS else zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info._compresslevel = 4
            h = hashlib.sha256()
            count = 0
            with path.open("rb") as src, archive.open(info, "w", force_zip64=True) as dst:
                while block := src.read(4 * 1024 * 1024):
                    h.update(block)
                    dst.write(block)
                    count += len(block)
            after = path.stat()
            actual = h.hexdigest()
            if count != row["bytes"] or after.st_mtime_ns != before.st_mtime_ns:
                raise ValueError(f"Source changed while archiving: {row['path']}")
            if row["expected_sha256"] and actual != row["expected_sha256"]:
                raise ValueError(f"Frozen archive/source identity mismatch: {row['path']}")
            manifest_rows.append({"path": row["path"], "bytes": count, "sha256": actual, "part": name})
    part = {"name": name, "sha256": sha(target), "bytes": target.stat().st_size,
            "file_count": len(rows), "uncompressed_bytes": sum(x["bytes"] for x in rows)}
    print(json.dumps({"event": "part_complete", **part}), flush=True)
    return part, manifest_rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--volume-mib", type=int, default=1400)
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()
    root = args.root.resolve()
    out = args.output.resolve()
    if not out.is_relative_to(root / ".local_archives"):
        raise ValueError("Export output must be a new directory beneath workspace .local_archives")
    if not 1 <= args.workers <= 8 or not 100 <= args.volume_mib <= 1800:
        raise ValueError("Invalid worker or safe volume bound")
    rows, coverage = collect(root)
    batches = groups(rows, args.volume_mib * 1024 * 1024)
    overview = {"files": len(rows), "source_bytes": sum(x["bytes"] for x in rows),
                "parts": len(batches), "coverage": coverage}
    print(json.dumps({"event": "selection", **overview}), flush=True)
    if args.plan_only:
        return
    out.mkdir(parents=True, exist_ok=False)
    (out / "selection.json").write_text(json.dumps({"overview": overview, "files": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(build_part, root, out, i, batch) for i, batch in enumerate(batches, 1)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    parts = sorted((x[0] for x in results), key=lambda x: x["name"])
    files = sorted((row for _, rows in results for row in rows), key=lambda x: x["path"])
    files_path = out / "files.jsonl"
    with files_path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in files:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    manifest = {"schema": SCHEMA, "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "original_workspace_root": str(root),
                "source_git_head_before_publication": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                "source_identity_policy": "Actual archived bytes are authoritative; ordinary Git text checkout can normalize EOL. Frozen original absolute provenance is retained.",
                "plan": {"path": PLAN, "sha256": sha(root / PLAN)},
                "final_snapshot": {"path": REPORT, "sha256": sha(root / REPORT)},
                "independent_acceptance": {"path": AUDIT, "sha256": sha(root / AUDIT)},
                "files_manifest": {"name": files_path.name, "sha256": sha(files_path), "count": len(files)},
                "parts": parts, "coverage": coverage,
                "source_bytes": sum(x["bytes"] for x in files), "archive_bytes": sum(x["bytes"] for x in parts),
                "external_execution_dependencies": ["Python 3.11 / CPython Windows x64 for retained .pyd", "JDK 18 for original Java execution"],
                "status": "PACKAGED_FROZEN_IDENTITIES_MATCH; independent ZIP verification and remote upload still required"}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"event": "packaged", "manifest": str(out / "manifest.json"), "archive_bytes": manifest["archive_bytes"]}), flush=True)


if __name__ == "__main__":
    main()
