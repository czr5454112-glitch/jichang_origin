"""Verify that paired G31 arms vary only the declared scoring/release factors."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts.experiments.g31_feng_alignment import experiment, metrics


def request(path):
    with gzip.open(path / "request.json.gz", "rt", encoding="utf-8") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--own", action="append", default=[])
    parser.add_argument("--aligned", action="append", default=[])
    parser.add_argument("--release-trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, default=experiment.CANONICAL,
                        help="explicit map workload; defaults to the original Nanning campaign")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    canonical = metrics.read_jsonl(args.canonical)
    releases = metrics.generator_releases(canonical, metrics.java_segments(args.release_trace))
    base = request(args.reference)
    base_manifest = experiment.read(args.reference / "manifest.json")
    if base_manifest["canonical"]["sha256"] != experiment.sha(args.canonical):
        raise ValueError("reference belongs to a different canonical map workload")
    if base["s4_wait_estimator"] != "legacy":
        raise ValueError("reference must be current-binary legacy mode")
    source_by_id = {row["segment_id"]: row for row in canonical}
    if len(base["bag_records"]) != len(canonical) or {row[0] for row in base["bag_records"]} != set(source_by_id):
        raise ValueError("reference population mismatch")
    if any(row[2] != source_by_id[row[0]]["pass_time"] for row in base["bag_records"]):
        raise ValueError("reference must use canonical own-source release")
    records = []
    for same_release, arguments in ((False, args.own), (True, args.aligned)):
        for argument in arguments:
            name, rawpath = argument.split("=", 1)
            path = Path(rawpath)
            current = request(path)
            manifest = experiment.read(path / "manifest.json")
            if set(base) != set(current):
                raise ValueError(f"request key-set changed: {name}")
            allowed = {"s4_wait_estimator", "bag_records", "expected_binary_path", "search_path"}
            different = [key for key in base if base[key] != current[key]]
            if set(different) - allowed:
                raise ValueError(f"unintended native option changes: {name}: {different}")
            if manifest["binary"]["sha256"] != base_manifest["binary"]["sha256"]:
                raise ValueError(f"comparison binary differs: {name}")
            if manifest["canonical"]["sha256"] != base_manifest["canonical"]["sha256"]:
                raise ValueError(f"canonical evidence differs: {name}")
            if current["s4_wait_estimator"] not in ("legacy", "eta_calendar", "eta_flow"):
                raise ValueError("unknown wait estimator")
            if manifest["score_overrides"] != {"s4_wait_estimator": current["s4_wait_estimator"]}:
                raise ValueError(f"manifest mode differs from request: {name}")
            if len(current["bag_records"]) != len(base["bag_records"]):
                raise ValueError(f"segment denominator differs: {name}")
            release_changes = 0
            for original, actual in zip(base["bag_records"], current["bag_records"]):
                if original[:2] + original[3:] != actual[:2] + actual[3:]:
                    raise ValueError(f"non-release bag field changed: {name}, {original[0]}")
                expected_release = releases[actual[0]] if same_release else original[2]
                if actual[2] != expected_release:
                    raise ValueError(f"wrong release epoch: {name}, {actual[0]}")
                release_changes += actual[2] != original[2]
            if same_release and (manifest["release_trace"] or {}).get("sha256") != experiment.sha(args.release_trace):
                raise ValueError(f"release trace evidence differs: {name}")
            if not same_release and manifest["release_contract"] != base_manifest["release_contract"]:
                raise ValueError(f"own-source release contract differs: {name}")
            records.append({"arm": name, "directory": str(path.resolve()), "mode": current["s4_wait_estimator"],
                            "same_HCA_generator_release": same_release, "segments_checked": len(current["bag_records"]),
                            "release_changes_from_reference": release_changes, "all_other_bag_fields_exact": True,
                            "all_execution_options_exact": True, "same_binary_sha256": True, "changed_request_keys": different,
                            "request": experiment.evidence(path / "request.json.gz"), "manifest": experiment.evidence(path / "manifest.json")})
    experiment.write(args.output / "audit.json", {
        "schema": "g31.feng_alignment.request_audit.v1", "argv": sys.argv, "script": experiment.evidence(Path(__file__)),
        "canonical": experiment.evidence(args.canonical), "release_trace": experiment.evidence(args.release_trace),
        "reference": experiment.evidence(args.reference / "request.json.gz"), "reference_binary": base_manifest["binary"],
        "comparisons": records, "all_passed": True,
        "boundary": "Java execution remains its original implementation. This gate proves factor isolation among the G31 arms only."})
    print(json.dumps({"output": str(args.output), "comparisons": len(records), "all_passed": True}))


if __name__ == "__main__":
    main()
