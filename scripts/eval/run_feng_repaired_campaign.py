"""Stage valid evidence and run the frozen, repaired Nanning DH campaign.

The simulator and normalizer remain the existing independent Java pipeline.
This coordinator never copies a legacy Nanning DH cell into the repaired root.
Use stages in order: reuse, smoke, then run for seed 104729 at 1x, 1.75x, 2x,
then the remaining frozen seeds. A smoke run is never normalized as a full cell.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_cie_external_baseline_robustness as external

RESULT_ROOT = ROOT / "outputs/runtime/cie_external_baseline_zero_through_optimized_v1"
AUDIT_ROOT = ROOT / "outputs/runtime/feng_cie_dh_zero_through_repair_20260905"
BINARY = ROOT / "build/nanning_ablation_gate_f_pybind/python/Release/czr005_cpp.cp311-win_amd64.pyd"
METHOD = "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION"


def reuse(result_root: Path) -> None:
    records = []
    for map_name in external.MAPS:
        for load in external.LOAD_FACTORS:
            for seed in external.SEEDS:
                for method in external.METHODS:
                    if map_name == "nanning" and method == METHOD:
                        continue
                    source = external.cell_dir(external.DEFAULT_RESULT_ROOT, load, seed, map_name) / f"{method}.json"
                    value = external.load_normalized_result(source)
                    target = external.cell_dir(result_root, load, seed, map_name) / source.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists() and target.read_bytes() != source.read_bytes():
                        raise ValueError(f"refusing to overwrite different evidence: {target}")
                    shutil.copyfile(source, target)
                    records.append({"map": map_name, "load": load, "seed": seed, "method": method,
                                    "source": str(source), "target": str(target),
                                    "sha256": external._sha256_file(source),
                                    "full_population_complete": value["full_population_complete"]})
    external._atomic_json(result_root / "reused_evidence.json", {
        "schema": "czr005.feng_repaired_reuse.v1", "count": len(records),
        "legacy_nanning_dh_reused": False, "records": records})
    print(json.dumps({"reused_valid_cells": len(records)}))


def smoke(result_root: Path) -> None:
    identity = external.cell_dir(external.DEFAULT_WORKLOAD_ROOT, 1.0, external.SEEDS[0], "nanning")
    external.audit_cell(identity / "identity.json")
    output = AUDIT_ROOT / f"smoke_nanning_128_{external.DEFAULT_DH_CLASSES_DIR.name}"
    if (output / "runner_status.json").exists():
        raise ValueError("smoke evidence already exists; inspect it before selecting a new directory")
    command = [sys.executable, str(ROOT / "scripts/eval/run_feng_paper_env_cie_dh.py"), "run",
               "--map-path", str(external.DEFAULT_NANNING_MAP),
               "--input-path", str(identity / "inputdata.txt"),
               "--allow-external-workload", "--external-workload-identity", str(identity / "identity.json"),
               "--seed", str(external.SEEDS[0]), "--max-raw-bags", "128",
               "--horizon-seconds", str(external.FIXED_HORIZON_SECONDS),
               "--trace-sample-modulo", "1", "--classes-dir", str(external.DEFAULT_DH_CLASSES_DIR),
               "--skip-compile", "--output-dir", str(output)]
    subprocess.run(command, cwd=ROOT, check=True)
    summary = next(csv.DictReader((output / "summary.csv").open(encoding="utf-8", newline="")))
    if int(summary["completed_raw_bags"]) != 128 or summary["status"] != "COMPLETE":
        raise ValueError("Nanning 128-bag smoke did not complete; inspect before formal execution")
    external._atomic_json(output / "smoke_scope.json", {
        "schema": "czr005.feng_repaired_smoke.v1", "scope": "SMOKE_ONLY_NOT_FORMAL_CELL",
        "raw_bag_limit": 128, "full_population_comparison_eligible": False,
        "command": command, "summary": summary})
    print(json.dumps({"status": "SMOKE_COMPLETE", "raw_bags": 128,
                      "wall_seconds": summary["wall_seconds"]}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("reuse", "smoke", "run"))
    parser.add_argument("--result-root", type=Path, default=RESULT_ROOT)
    parser.add_argument("--load-factor", type=float, action="append")
    parser.add_argument("--seed", type=int, action="append")
    args = parser.parse_args()
    if args.result_root.resolve() == external.DEFAULT_RESULT_ROOT.resolve():
        raise ValueError("the repaired campaign must use a separate result directory")
    if args.stage == "reuse":
        reuse(args.result_root)
    elif args.stage == "smoke":
        smoke(args.result_root)
    else:
        if not args.load_factor or not args.seed:
            raise ValueError("select explicit frozen loads and seeds after reviewing the preceding gate")
        loads = external._selection(args.load_factor, external.LOAD_FACTORS)
        seeds = external._selection(args.seed, external.SEEDS)
        label = "_".join([*(external._load_token(x) for x in loads), *(str(x) for x in seeds)])
        summary = external.execute_campaign(
            workload_root=external.DEFAULT_WORKLOAD_ROOT, result_root=args.result_root,
            python=sys.executable, java="java", javac="javac", binary=BINARY,
            methods=(METHOD,), load_factors=loads, seeds=seeds, maps=("nanning",),
            status_output=args.result_root / f"status_repaired_{label}.json")
        print(json.dumps({"status": summary["status"], "failures": summary["failure_count"]}))
        return 0 if summary["failure_count"] == 0 else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
