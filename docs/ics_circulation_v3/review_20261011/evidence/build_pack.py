"""Package existing experiment receipts without executing archived code or pickle.

Run --plan first; --build binds all locally available Phase2/3/4 output files by
SHA256 and copies only the explicitly selected compact receipts. Original files
are read-only inputs. This is a publication helper, not a new experiment.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "outputs/experiments/ics_circulation_v3"
DEST = Path(__file__).resolve().parent
LIMIT = 192 * 1024
SKIP_COMPONENTS = {
    "__pycache__", "source_snapshot", "source_before", "source_after", "frozen_source",
    "source", "sources", "round10_frozen", "round8_frozen", "pytest_tmp", "raw",
    "raw_runs", "checkpoints", "snapshots", "cases", "cache", "models", "visuals",
    "plots", "figures", "tapes", "public_tapes", "private_tapes", "rollouts",
}
KNOWN = {
    "result.json", "results.json", "resource.json", "resources.json", "manifest.json",
    "summary.json", "ledger.json", "protocol.json", "scope.json", "before.json",
    "after.json", "baseline.json", "closure.json", "validation.json", "audit.json",
    "stdout.txt", "stderr.txt", "junit.xml", "runtime_contract.json",
    "projection_declaration.json", "projection_run_contract.json",
    "frozen_projection_inputs.json", "input_contract.json", "source_manifest.json",
}
REPORT_TOKEN = re.compile(r"(?:audit|validation|closure|comparison|ledger|resource|protocol|contract|failure|review|diagnosis|manifest|provenance|result|summary|analysis|census|coverage)", re.I)
REVIEW_EXCEPTIONS = {
    "phase4_w3_round8_independent_review_20261010/stability_full_artifact_audit.json",
    "phase4_w3_round8_independent_review_20261010/performance_formal_artifact_audit.json",
    "phase4_w3_round8_independent_review_20261010/boundary_mechanism_artifact_audit.json",
}


def relative(path: Path) -> str:
    return path.relative_to(BASE).as_posix()


def group(rel: str) -> str:
    top = rel.split("/", 1)[0]
    for phase in ("phase2", "phase3"):
        if top.startswith(phase + "_"):
            return phase
    match = re.search(r"round(\d+)", top)
    return f"phase4_round{int(match[1]):02}" if match else "phase4_unnumbered_series"


def reason(path: Path, size: int) -> str:
    rel = path.relative_to(BASE)
    lower = [x.lower() for x in rel.parts]
    if rel.as_posix() in REVIEW_EXCEPTIONS:
        return "selected_explicit_large_independent_audit_exception"
    if path.suffix.lower() in {".pickle", ".pkl", ".pyc"}:
        return "omitted_executable_serialization_or_bytecode_never_loaded"
    if any(x in SKIP_COMPONENTS for x in lower[1:-1]) or "source_20" in lower[0]:
        return "omitted_frozen_source_or_raw_fixture_tree"
    if len(rel.parts) > 3:
        return "omitted_nested_per_case_or_raw_artifact"
    if size > LIMIT:
        return "omitted_above_compact_receipt_limit"
    if path.suffix.lower() == ".md":
        return "selected_original_narrative_or_protocol"
    if path.suffix.lower() == ".py" and len(rel.parts) == 2:
        return "selected_original_top_level_runner_or_auditor"
    if path.suffix.lower() == ".json" and (path.name.lower() in KNOWN or REPORT_TOKEN.search(path.name)):
        return "selected_original_receipt_or_identity"
    if path.name.lower() in KNOWN:
        return "selected_original_test_log"
    return "omitted_raw_data_or_non_receipt"


def enumerate_files():
    for top in sorted(BASE.iterdir()):
        if not top.is_dir() or not top.name.startswith(("phase2_", "phase3_", "phase4_")):
            continue
        for directory, dirs, names in os.walk(top):
            dirs.sort()
            for name in sorted(names):
                path = Path(directory) / name
                if path.is_symlink():
                    raise RuntimeError(f"Refusing symlink: {path}")
                stat = path.stat()
                yield path, stat.st_size, stat.st_mtime_ns


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(2**20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def plan(files):
    chosen = []
    totals = collections.defaultdict(lambda: {"files": 0, "bytes": 0, "selected_files": 0, "selected_bytes": 0})
    for path, size, _ in files:
        rel = relative(path)
        why = reason(path, size)
        row = totals[group(rel)]
        row["files"] += 1
        row["bytes"] += size
        if why.startswith("selected_"):
            row["selected_files"] += 1
            row["selected_bytes"] += size
            chosen.append({"original_path": "outputs/experiments/ics_circulation_v3/" + rel, "bytes": size, "selection_reason": why})
    value = {"schema": "ics_compact_evidence_selection_v1", "receipt_limit_bytes": LIMIT, "groups": dict(sorted(totals.items())), "selected": chosen}
    write_json(DEST / "SELECTION_PLAN.json", value)
    return value


def build(files, selection):
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    copy_root = DEST / "receipts"
    inventory_root = DEST / "inventory"
    if copy_root.exists() or inventory_root.exists():
        raise RuntimeError("Refusing to overwrite a sealed pack; use a new destination/version")
    copy_root.mkdir()
    inventory_root.mkdir()
    inventories = {}
    selected = []
    changes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        hashes = pool.map(lambda row: sha(row[0]), files)
        for (path, size, mtime), digest in zip(files, hashes):
            rel = relative(path)
            why = reason(path, size)
            name = group(rel)
            if name not in inventories:
                inventories[name] = (inventory_root / (name + ".tsv")).open("w", encoding="utf-8", newline="")
                inventories[name].write("original_relative_path\tbytes\tsha256\tpublication_status\tlocal_availability\n")
            inventories[name].write(f"{rel}\t{size}\t{digest}\t{why}\tpresent_at_packaging\n")
            if why.startswith("selected_"):
                out = copy_root / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, out)
                if sha(out) != digest:
                    raise RuntimeError(f"Copy does not match hash: {rel}")
                selected.append({"path": "receipts/" + rel, "original_path": "outputs/experiments/ics_circulation_v3/" + rel, "bytes": size, "sha256": digest, "reason": why})
            current = path.stat()
            if current.st_size != size or current.st_mtime_ns != mtime:
                changes.append(rel)
    for stream in inventories.values():
        stream.close()
    if changes:
        raise RuntimeError(f"Sources changed during packaging: {changes}")
    inventory = [{"path": p.relative_to(DEST).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in sorted(inventory_root.iterdir())]
    manifest = {
        "schema": "ics_compact_evidence_pack_v1",
        "source_workspace_base_head": "a23cf1c066d1087571b31733f0577c602040aa8d",
        "scope": "Every regular local file in outputs/experiments/ics_circulation_v3/phase2_*, phase3_*, phase4_* existing at packaging, including omitted raw/checkpoint/source artifacts.",
        "copy_policy": "Original receipt bytes only; no original changes; no archive, experiment script or pickle executed.",
        "verification_limit": "This pack supports code/report review and SHA identity checks. It does not contain all raw evidence and is not a substitute for independent full raw replay or audit.",
        "file_count": len(files), "original_bytes": sum(row[1] for row in files),
        "selected_file_count": len(selected), "selected_bytes": sum(row["bytes"] for row in selected),
        "omitted_file_count": len(files) - len(selected),
        "omitted_bytes": sum(row[1] for row in files) - sum(row["bytes"] for row in selected),
        "groups": selection["groups"], "inventory": inventory, "selected": selected,
        "source_stat_changed": changes,
        "packaging_cpu_seconds": time.process_time() - started_cpu,
        "packaging_wall_seconds": time.perf_counter() - started_wall,
        "resource_qualification": "Only this build process measured here; planning, reading, documentation and other auxiliary work are not fully measured. Not a simulation or routing-query invocation. Do not rewrite sealed historical resource ledgers.",
    }
    write_json(DEST / "manifest.json", manifest)
    return {k: manifest[k] for k in ("file_count", "original_bytes", "selected_file_count", "selected_bytes", "omitted_file_count", "packaging_cpu_seconds", "packaging_wall_seconds")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    files = list(enumerate_files())
    selection = plan(files)
    if args.build:
        print(json.dumps(build(files, selection), indent=2))
    else:
        print(json.dumps(selection["groups"], indent=2))
