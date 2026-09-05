"""Independently verify portable DH evidence and bind local-only paths to archives."""
from __future__ import annotations

import csv
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
REPAIR = ROOT / "outputs/runtime/feng_cie_dh_zero_through_repair_20260905"
OUT = REPAIR / "publication_traceability"
CORE = ROOT / "benchmarks/java/feng_cie_dh/App"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def record(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": relative(path), "sha256": sha(data), "size_bytes": len(data)}


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_gzip(path: Path, content: bytes) -> dict:
    path.write_bytes(gzip.compress(content, mtime=0))
    assert gzip.decompress(path.read_bytes()) == content
    return {**record(path), "uncompressed_sha256": sha(content), "uncompressed_size_bytes": len(content)}


def aggregate(records: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(records):
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big")); digest.update(encoded)
        digest.update(len(content).to_bytes(8, "big")); digest.update(content)
    return digest.hexdigest()


def bundle_json_files(paths: list[Path], name: str) -> dict:
    # UTF-8 text is retained verbatim, including original whitespace/newlines;
    # re-encoding each member reconstructs its original SHA exactly.
    members = [{**record(path), "utf8": path.read_bytes().decode("utf-8")} for path in paths]
    for member in members:
        assert sha(member["utf8"].encode("utf-8")) == member["sha256"]
    content = json.dumps({"members": members}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {**write_gzip(OUT / name, content), "member_count": len(members),
            "members": [{k: v for k, v in member.items() if k != "utf8"} for member in members]}


def archived(path: Path, expected_archive: str, expected_native: str) -> dict:
    data = path.read_bytes()
    restored = gzip.decompress(data) if path.suffix == ".gz" else data
    assert sha(data) == expected_archive, f"archive SHA mismatch: {path}"
    assert sha(restored) == expected_native, f"uncompressed SHA mismatch: {path}"
    return {**record(path), "uncompressed_sha256": sha(restored), "verified": True}


def archive_reused_normalized(coverage_sha: dict[str, str]) -> dict:
    origin = ROOT / "outputs/runtime/cie_external_baseline_zero_through_optimized_v1/reused_evidence.json"
    measured = origin.read_bytes()
    reuse = json.loads(measured)
    assert reuse["count"] == 150 and reuse["legacy_nanning_dh_reused"] is False
    assert len(reuse["records"]) == 150
    paths, mappings, coordinates = [], [], set()
    counts = Counter()
    for row in reuse["records"]:
        source, target = Path(row["source"]), Path(row["target"])
        original, copied = source.read_bytes(), target.read_bytes()
        assert original == copied and sha(copied) == row["sha256"], source
        value = json.loads(copied)
        coordinate = (row["map"], row["load"], row["seed"], row["method"])
        assert coordinate not in coordinates
        coordinates.add(coordinate)
        assert coordinate == (value["map"], value["load_factor"], value["seed"], value["method"])
        assert not (value["map"] == "nanning" and value["method"] == "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION")
        identity = Path(value["workload_identity_path"])
        assert value["workload_identity_sha256"] == coverage_sha[relative(identity)]
        counts[value["map"] + "/" + value["method"]] += 1
        paths.append(target)
        mappings.append({"map": value["map"], "load_factor": value["load_factor"],
            "seed": value["seed"], "method": value["method"],
            "source_path": relative(source), "target_path": relative(target),
            "normalized_sha256": sha(copied), "source_target_byte_identical": True,
            "workload_identity_path": relative(identity),
            "workload_identity_sha256": value["workload_identity_sha256"],
            "full_population_complete": value["full_population_complete"]})
    assert len(counts) == 5 and set(counts.values()) == {30}
    copied_manifest = OUT / "reused_evidence.json"
    copied_manifest.write_bytes(measured)
    bundle = bundle_json_files(paths, "reused_150_normalized_records.json.gz")
    manifest = {"schema": "czr005.feng_reused_normalized_portable_evidence.v1",
        "count": 150, "legacy_nanning_dh_reused": False,
        "map_method_counts": dict(sorted(counts.items())),
        "original_reuse_manifest": record(origin), "exact_published_manifest_copy": record(copied_manifest),
        "normalized_records_bundle": bundle, "records": mappings,
        "native_large_data_duplicated": False,
        "interpretation": "These unchanged 150 normalized records retain the old native evidence hashes, contracts, source/class/binary identities and metrics. Original native large files remain local; this bundle closes normalized identity review without claiming their complete republishing."}
    write_json(OUT / "reused_150_normalized_archive_manifest.json", manifest)
    return record(OUT / "reused_150_normalized_archive_manifest.json")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = ROOT / "outputs/runtime/feng_cie_dh_reconstruction/primary"
    variants = {"original_99bf": baseline,
                "correctness_3b47": REPAIR / "regression_final/map2_full_population_repaired",
                "optimized_809d": REPAIR / "regression_optimized/map2_full_population_repaired"}
    shared = []
    for name in ("bags.csv", "segments.csv", "trace.csv"):
        content = (baseline / name).read_bytes()
        for path in variants.values():
            assert (path / name).read_bytes() == content
        shared.append({"native_filename": name,
            "all_three_versions_byte_identical": True,
            "native_paths": [relative(path / name) for path in variants.values()],
            "archive": write_gzip(OUT / ("map2_shared_" + name + ".gz"), content)})
    write_json(OUT / "map2_shared_archive_manifest.json", {
        "schema": "czr005.feng_map2_three_version_shared_population.v1",
        "raw_bag_count": 28506, "segment_count": 43603, "files": shared,
        "variant_runner_statuses": {name: record(path / "runner_status.json") for name, path in variants.items()}})

    identities = sorted((ROOT / "data/processed/workloads/cie_external_robustness").glob("*/seed_*/identity.json"))
    assert len(identities) == 60
    coverage = json.loads((REPAIR / "regression_final/formal_od_coverage.json").read_text())
    coverage_sha = {r["identity_path"]: r["identity_sha256"] for r in coverage["source_cells"]}
    for path in identities: assert sha(path.read_bytes()) == coverage_sha[relative(path)]
    identity_bundle = bundle_json_files(identities, "formal_60_workload_identities.json.gz")
    reuse_manifest = archive_reused_normalized(coverage_sha)

    old_root = ROOT / "outputs/runtime/cie_external_baseline_robustness"
    sidecar_path = old_root / "scientific_validity_20260905.json"
    sidecar = json.loads(sidecar_path.read_text())
    old_records = []
    for cell in sidecar["cells"]:
        status = ROOT / cell["directory"] / "feng_env_dh/runner_status.json"
        expected = next(row["sha256"] for row in cell["native_files"] if row["path"].endswith("runner_status.json"))
        assert sha(status.read_bytes()) == expected
        old_records.append(status)
        if cell["normalized_evidence"]:
            normalized = ROOT / cell["normalized_evidence"]["path"]
            assert sha(normalized.read_bytes()) == cell["normalized_evidence"]["sha256"]
            old_records.append(normalized)
    assert len(old_records) == 46
    old_bundle = bundle_json_files(old_records, "invalidated_30_statuses_and_16_terminal_records.json.gz")

    # Recover exact run-input bytes from tracked Git blobs without assuming a
    # contributor's core.autocrlf setting. No input is rewritten by this audit.
    tracked_inputs = [ROOT / name for name in (
        "legacy/jichang_origin_readonly/map2.txt", "legacy/jichang_origin_readonly/inputdata.txt",
        "data/processed/maps/nanning_legacy.txt", "data/processed/maps/nanning_airport_profile.json",
        "data/processed/feng_table53_segment_schedule.csv")]
    tracked_inputs += sorted((ROOT / "legacy/jichang_origin_readonly/src").rglob("*.java"))
    git_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    input_records = []
    for path in tracked_inputs:
        blob = subprocess.run(["git", "show", f"{git_head}:{relative(path)}"], cwd=ROOT, capture_output=True, check=True).stdout
        measured = path.read_bytes()
        normalized = blob.replace(b"\r\n", b"\n")
        if measured == blob: transformation = "IDENTITY"
        elif measured == normalized: transformation = "NORMALIZE_CRLF_TO_LF"
        elif measured == normalized.replace(b"\n", b"\r\n"): transformation = "NORMALIZE_TO_LF_THEN_EXPAND_TO_CRLF"
        else: raise AssertionError(f"input differs from Git beyond line endings: {path}")
        input_records.append({**record(path), "git_commit": git_head, "git_blob_sha256": sha(blob),
            "restore_frozen_bytes": transformation, "crlf_count": measured.count(b"\r\n"),
            "bare_lf_count": measured.count(b"\n") - measured.count(b"\r\n")})
    legacy = ROOT / "legacy/jichang_origin_readonly"
    legacy_sha = aggregate([(p.relative_to(legacy).as_posix(), p.read_bytes()) for p in sorted((legacy / "src").rglob("*.java"))])
    assert legacy_sha == "b0c7545abad1705eba9255527d39a864007bd576c9edbc9cb872a51e6acc9c25"
    source_sha = aggregate([("App/" + p.name, p.read_bytes()) for p in sorted(CORE.glob("*.java"))])
    assert source_sha == "809d069832da3fec5a2aa6302a99a9ede24fcd5a1fb28c4a53c3cc3c139ff86f"
    production_classes = ROOT / "build/feng_cie_dh_zero_through_optimized_v1"
    class_sha = aggregate([(p.relative_to(production_classes).as_posix(), p.read_bytes())
                           for p in sorted(production_classes.rglob("*.class"))])
    assert class_sha == "ad828f533bc34abb3527d92f0f476e69412fc14c0024cbf2694bf0f82b382fd0"
    source_recovery = []
    for label, commit, eol, expected in (
        ("original", "f101c2f6c21bd4a147e060ba09bf95b26b48b50c", "LF", "99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8"),
        ("correctness", "8da1844", "CRLF", "3b47ffcefa558365e55e27508fc8904608026fd3235102eee6c305539999a208"),
        ("optimized", "0ca1f45", "CRLF", "809d069832da3fec5a2aa6302a99a9ede24fcd5a1fb28c4a53c3cc3c139ff86f")):
        commit = subprocess.run(["git", "rev-parse", commit], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        files = []
        for path in sorted(CORE.glob("*.java")):
            data = subprocess.run(["git", "show", f"{commit}:{relative(path)}"], cwd=ROOT, capture_output=True, check=True).stdout
            data = data.replace(b"\r\n", b"\n")
            if eol == "CRLF": data = data.replace(b"\n", b"\r\n")
            files.append(("App/" + path.name, data))
        assert aggregate(files) == expected, label
        source_recovery.append({"version": label, "git_commit": commit, "newline_encoding": eol,
            "source_aggregate_sha256": expected, "git_recovery_verified": True})
    write_json(OUT / "frozen_input_and_source_identity.json", {
        "schema": "czr005.feng_frozen_git_byte_recovery.v1", "inputs": input_records,
        "legacy_source_aggregate_sha256": legacy_sha, "production_sources": source_recovery,
        "independently_hashed_current_production_class_aggregate_sha256": class_sha,
        "workload_identity_bundle": identity_bundle,
        "generated_raw_source": {"path": "artifacts/tasks/g4irsf31_nanning/nanning_1x_raw.txt",
            "sha256": sha((ROOT / "artifacts/tasks/g4irsf31_nanning/nanning_1x_raw.txt").read_bytes()),
            "producer": "scripts/eval/run_g4irsf31_nanning_workload.py:build_workload(scale=1)",
            "inputs": ["legacy/jichang_origin_readonly/inputdata.txt", "data/processed/maps/nanning_airport_profile.json"]}})

    checked = []
    for name in ("regression_final", "regression_optimized"):
        manifest = json.loads((REPAIR / name / "single_bag_equivalence_and_archives.json").read_text())
        for row in manifest["archives"]:
            checked.append(archived(ROOT / row["path"], row["sha256"], row["uncompressed_sha256"]))
    shared_root = REPAIR / "optimization_equivalence_v1/nanning_128_trace1"
    shared_manifest = shared_root / "shared_archive_manifest.json"
    for row in json.loads(shared_manifest.read_text())["files"]:
        checked.append(archived(shared_root / row["archive_path"], row["archive_sha256"], row["uncompressed_sha256"]))
    evidence_root = ROOT / "outputs/evidence/feng_cie_dh_repair_20260905"
    population_manifest = evidence_root / "archive_manifest.json"
    population_manifest_bytes = population_manifest.read_bytes()
    population = json.loads(population_manifest_bytes)
    for cell in population["cells"]:
        for row in cell["files"].values():
            checked.append(archived(ROOT / row["archive_path"], row["archive_sha256"], row["native_sha256"]))
    control_manifest = evidence_root / "correctness_unoptimized_nanning_1x_seed104729/archive_manifest.json"
    for row in json.loads(control_manifest.read_text())["files"].values():
        checked.append(archived(ROOT / row["archive_path"], row["archive_sha256"], row["native_sha256"]))
    tracked = set(subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0"))
    mandatory = [OUT / "map2_shared_archive_manifest.json", OUT / "frozen_input_and_source_identity.json",
                 OUT / "formal_60_workload_identities.json.gz", OUT / "invalidated_30_statuses_and_16_terminal_records.json.gz",
                 OUT / "reused_evidence.json", OUT / "reused_150_normalized_records.json.gz",
                 OUT / "reused_150_normalized_archive_manifest.json",
                 sidecar_path, shared_manifest, population_manifest, control_manifest]
    mandatory += [ROOT / row["path"] for row in checked]
    mandatory += [ROOT / row["archive"]["path"] for row in shared]
    write_json(OUT / "publication_traceability_audit.json", {
        "schema": "czr005.feng_publication_traceability_audit.v1", "status": "PASS",
        "verified_existing_archive_or_native_files": len(checked), "checks": checked,
        "population_manifest_at_audit": {"path": relative(population_manifest),
            "sha256": sha(population_manifest_bytes), "size_bytes": len(population_manifest_bytes)},
        "population_manifest_unchanged_during_audit": population_manifest.read_bytes() == population_manifest_bytes,
        "population_cells_archived_at_audit": population["cell_count"],
        "invalidated_campaign_sidecar": record(sidecar_path),
        "old_campaign_records_bundle": old_bundle,
        "reused_150_normalized_archive_manifest": reuse_manifest,
        "old_scientific_sidecar_is_published_at_original_path": True,
        "publication_action": "Force-add the original ignored scientific sidecar; add all pending evidence and this directory before push.",
        "pending_git_publication_at_audit": sorted({relative(p) for p in mandatory if relative(p) not in tracked}),
        "absolute_path_handling": "Original absolute paths are provenance. Resolve archived objects with the repository-relative keys in these manifests, and verify bytes before rebasing paths.",
        "local_large_raw_retained": "Original native CSVs remain local. Shared gzip objects supply all map2 rows and all published corrected Nanning rows; invalidated raw trajectories are not used for valid performance claims."})
    print(json.dumps({"status": "PASS", "verified_files": len(checked), "archived_population_cells": population["cell_count"],
                      "input_identity_members": len(identities), "old_status_and_normalized_members": len(old_records)}))


if __name__ == "__main__": main()
