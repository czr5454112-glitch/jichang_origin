"""Read-only posthoc metrics from frozen G31 and physical-HCA populations.

The original run directories are never modified. User THT requires an explicit
first_planning_attempt_time: finish-minus-successful-admission is a separate
network_elapsed component and never fills a missing user THT timestamp.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_no_wait.tht_metrics import audit_tht

DEFAULT_CONTRACT = ROOT / "outputs/experiments/g31_nonstop_contract_20261024_draft001/contract_manifest.json"


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _business_components(rows, bags):
    actual = {str(b["segment_id"]): b for b in bags}
    values = defaultdict(lambda: [[], [], [], [], [], []])
    for row in rows:
        bag = actual[str(row["segment_id"])]
        result = values[str(row["task_id"])]
        result[0].append(bag["finish"] - bag["admission"])
        result[1].append(bag["admission"] - row["pass_time"])
        result[2].append(bag["finish"] - row["pass_time"])
        attempt = bag.get("first_planning_attempt_time")
        result[3].append(bag["finish"] - attempt if attempt is not None else None)
        result[4].append(bag["admission"] - attempt if attempt is not None else None)
        result[5].append(attempt - row["pass_time"] if attempt is not None else None)
    return {task: tuple(math.fsum(v) if all(x is not None for x in v) else None for v in parts) for task, parts in values.items()}


def paired_summary(g31, hca):
    """Pair exact original businesses; refuse missing/censored or changed cells."""
    reasons = []
    for key in ("cell", "canonical_sha256", "horizon"):
        if g31[key] != hca[key]:
            reasons.append(f"different_{key}")
    if not g31["comparison_population_complete"] or not hca["comparison_population_complete"]:
        reasons.append("incomplete_or_invalid_population")
    if reasons:
        return {"comparable": False, "reasons": reasons}
    a, b = g31["business_values"], hca["business_values"]
    if a.keys() != b.keys():
        return {"comparable": False, "reasons": ["different_business_identity"]}
    result = {"comparable": True, "count": len(a),
              "direction": "G31 minus HCA; these are descriptive components, not a user-THT winner claim",
              "g31": g31["id"], "hca": hca["id"], "cell": g31["cell"]}
    for column, name in enumerate(("network_elapsed", "canonical_to_admission", "canonical_elapsed",
                                   "user_tht", "planning_retry_wait", "canonical_preplanning")):
        if any(len(a[task]) <= column or len(b[task]) <= column or a[task][column] is None or b[task][column] is None for task in a):
            result[name] = {"available": False, "reason": "missing_verified_first_planning_anchor"}
            continue
        differences = [a[task][column] - b[task][column] for task in a]
        total = math.fsum(differences)
        result[name] = {"available": True, "sum_difference_seconds": total,
                        "mean_difference_seconds": total / len(a) if a else None,
                        "g31_lower_count": sum(v < 0 for v in differences),
                        "equal_count": sum(v == 0 for v in differences),
                        "g31_higher_count": sum(v > 0 for v in differences)}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--g31-dir", type=Path, nargs="+", default=[])
    parser.add_argument("--hca-dir", type=Path, nargs="+", default=[],
                        help="Cell directories containing physical_bags.jsonl, or parent directories of such cells")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--hca-bags-name", default="physical_bags.jsonl",
                        help="Explicit annotated HCA filename when first-attempt timestamps were independently added")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("output already exists; choose a new report directory")
    contract = _read(args.contract)
    inputs = [("g31", p.resolve()) for p in args.g31_dir]
    for parent in args.hca_dir:
        paths = [parent] if (parent / args.hca_bags_name).is_file() else [
            parent / cell for cell in contract["cells"] if (parent / cell / args.hca_bags_name).is_file()]
        if not paths:
            raise ValueError(f"no HCA physical population found: {parent}")
        inputs.extend(("hca", p.resolve()) for p in paths)
    if not inputs or len(set(inputs)) != len(inputs):
        raise ValueError("provide nonduplicate G31/HCA inputs")
    args.output.mkdir(parents=True)
    report = {"schema": "g31.nowait.posthoc_components.v1", "status": "running",
              "contract": str(args.contract.resolve()), "contract_sha256": _sha(args.contract),
              "metrics_source_sha256": _sha(Path(__file__).with_name("tht_metrics.py")),
              "report_source_sha256": _sha(Path(__file__)),
              "user_tht_status": "requires_explicit_verified_first_planning_attempt_time_per_leg",
              "interpretation": "User THT includes all failed planning retries. Network elapsed excludes pre-admission retries. Canonical-to-admission includes pre-generation and scheduling hold. Missing first-attempt telemetry leaves user THT unavailable, never inferred from successful admission.",
              "runs": [], "pairs": []}
    _write(args.output / "manifest.json", report)
    cached = {}
    private_runs = []
    for algorithm, directory in inputs:
        if algorithm == "g31":
            manifest = _read(directory / "manifest.json")
            if manifest["status"] != "complete":
                raise ValueError(f"G31 run is not complete: {directory}")
            cell = f"{manifest['map']}_{manifest['scale']}x"
            native = _read(directory / "native_summary.json")
            horizon = native.get("executed_horizon", manifest["config"]["end_time"])
            bags_path = directory / "bags.jsonl"
            bag_hash = _sha(bags_path)
            if bag_hash != manifest["bags_sha256"]:
                raise ValueError(f"frozen bag hash changed: {directory}")
            budget_exhausted = native.get("event_budget_exhausted", False)
            name = directory.name
        else:
            cell = directory.name
            horizon = _read(directory / "continuous_analysis.json")["horizon"]
            bags_path = directory / args.hca_bags_name
            bag_hash = _sha(bags_path)
            budget_exhausted = False
            name = directory.parent.name + "__" + directory.name
        if cell not in cached:
            details = contract["cells"][cell]
            canonical = Path(details["canonical"]["path"])
            canonical_hash = _sha(canonical)
            if canonical_hash != details["canonical"]["sha256"]:
                raise ValueError(f"canonical hash changed: {canonical}")
            rows = _jsonl(canonical)
            if len(rows) != details["segment_denominator"] or len({r["task_id"] for r in rows}) != details["business_denominator"]:
                raise ValueError(f"canonical denominator changed: {cell}")
            cached[cell] = (canonical, canonical_hash, rows)
        canonical, canonical_hash, rows = cached[cell]
        bags = _jsonl(bags_path)
        metrics = audit_tht(rows, bags, horizon=horizon)
        destination = args.output / name
        destination.mkdir()
        _write(destination / "metrics.json", metrics)
        complete = metrics["passed"] and metrics["completed_businesses"] == metrics["business_denominator"] and not budget_exhausted
        stored_reports = {}
        for filename in ("manifest.json", "audit.json", "headway_audit.json", "rolling_replay.json", "native_summary.json",
                         "analysis.json", "continuous_analysis.json", "physical_headway_audit.json", "first_planning_eligibility_receipt.json",
                         "annotated_physical_bags_receipt.json"):
            source = directory / filename
            if source.is_file():
                target = destination / ("original_" + filename)
                shutil.copyfile(source, target)
                stored_reports[filename] = _sha(source)
        summary = {"id": name, "algorithm": algorithm, "cell": cell, "input_directory": str(directory),
                   "bags": str(bags_path), "bags_sha256": bag_hash,
                   "canonical": str(canonical), "canonical_sha256": canonical_hash,
                   "horizon": horizon, "event_budget_exhausted": budget_exhausted,
                   "metrics_passed": metrics["passed"], "comparison_population_complete": complete,
                   "segment_denominator": metrics["segment_denominator"], "business_denominator": metrics["business_denominator"],
                   "completed_segments": metrics["completed_segments"], "completed_businesses": metrics["completed_businesses"],
                   "user_tht_full_population_available": metrics["user_tht_full_population_available"],
                   "user_tht_per_business": metrics["user_tht"]["full_population"],
                   "planning_retry_wait_per_business": metrics["secondary"]["business_sum_planning_wait"]["full_population"],
                   "canonical_preplanning_per_business": metrics["secondary"]["business_sum_canonical_preplanning"]["full_population"],
                   "network_elapsed_per_business": metrics["paper_tht"]["full_population"],
                   "canonical_to_admission_per_business": metrics["secondary"]["business_sum_source_hold"]["full_population"],
                   "canonical_elapsed_per_business": metrics["secondary"]["business_sum_canonical_elapsed"]["full_population"],
                   "canonical_elapsed_per_segment": metrics["secondary"]["segment_canonical_elapsed"]["full_population"],
                   "original_report_hashes": stored_reports}
        _write(destination / "provenance_and_summary.json", summary)
        report["runs"].append(summary)
        private_runs.append({**summary, "business_values": _business_components(rows, bags) if complete else {}})
        print(json.dumps({"id": name, "complete": complete,
                          "user_tht_mean": summary["user_tht_per_business"]["mean"],
                          "network_elapsed_mean": summary["network_elapsed_per_business"]["mean"],
                          "canonical_to_admission_mean": summary["canonical_to_admission_per_business"]["mean"],
                          "canonical_elapsed_mean": summary["canonical_elapsed_per_business"]["mean"]}), flush=True)
    for a in private_runs:
        if a["algorithm"] != "g31":
            continue
        for b in private_runs:
            if b["algorithm"] != "hca" or a["cell"] != b["cell"]:
                continue
            paired = paired_summary(a, b)
            report["pairs"].append(paired)
            if paired["comparable"]:
                path = args.output / (a["id"] + "__versus__" + b["id"] + ".csv")
                with path.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["task_id", "network_elapsed_g31_minus_hca", "canonical_to_admission_g31_minus_hca", "canonical_elapsed_g31_minus_hca", "user_tht_g31_minus_hca", "planning_retry_wait_g31_minus_hca", "canonical_preplanning_g31_minus_hca"])
                    for task in sorted(a["business_values"]):
                        writer.writerow([task] + [(a["business_values"][task][i] - b["business_values"][task][i])
                                                  if a["business_values"][task][i] is not None and b["business_values"][task][i] is not None else None
                                                  for i in range(6)])
    report["status"] = "complete"
    if _sha(Path(__file__).with_name("tht_metrics.py")) != report["metrics_source_sha256"]:
        raise ValueError("metric source changed during posthoc evaluation")
    _write(args.output / "manifest.json", report)
    return report


if __name__ == "__main__":
    main()
