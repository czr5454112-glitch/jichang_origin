"""Run isolated future-reservation candidate010 with the full five audit gates.

Uses the same canonical populations, service2 profiles and THT definitions as
the standard adapter. Does not change the formal G31 registration or defaults.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
spec = importlib.util.spec_from_file_location("candidate010_adapter", HERE / "continuous_adapter.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", required=True, choices=("map2", "nanning"))
    parser.add_argument("--scale", type=int, choices=(1, 2), required=True)
    parser.add_argument("--controls", type=Path, required=True)
    parser.add_argument("--physical-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepared = adapter.prepare(args.map, scale=args.scale, controls_path=args.controls,
                               contract_path=args.physical_contract)
    prepared["selection"]["entrypoint"] = adapter.evidence(__file__)
    prepared["selection"]["selection_label"] = "isolated_future_reservation_candidate010"
    output = adapter.rooted(args.output).resolve()
    result = adapter.execute(prepared, output)
    shutil.copyfile(__file__, output / "standard_sources" / "run_candidate.py")
    prepared["selection"]["execution_status"] = result["status"]
    adapter.write(output / "standard_selection.json", prepared["selection"])
    print(json.dumps(dict(status=result["status"], summary=str(output / "summary.json"),
                         full_population_performance_available=result["full_population_performance_available"],
                         performance_promoted=False), ensure_ascii=False))


if __name__ == "__main__":
    main()
