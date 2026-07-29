#!/usr/bin/env python3
"""Run one real protected-input G4IRSF15 three-stage native smoke."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path


def emit(**values: object) -> None:
    print(json.dumps(values, sort_keys=True), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    sys.path[:0] = [str(root), str(root / "src")]
    from scripts.eval import g4irsf15_causal_campaign as campaign

    binary = arguments.binary.resolve(strict=True)
    specification = importlib.util.spec_from_file_location(
        "czr005_cpp", binary
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load extension: {binary}")
    module = importlib.util.module_from_spec(specification)
    sys.modules["czr005_cpp"] = module
    specification.loader.exec_module(module)
    native_arguments, _, _ = campaign._native_arguments(root)

    started = time.time()
    scan = module.g4irsf15_scan_causal_skeletons_from_records(
        *native_arguments
    )
    emit(
        stage="scan",
        elapsed_seconds=time.time() - started,
        schema=scan["schema"],
        census_complete=scan["census_complete"],
        population_count=scan["primary_population_count"],
        processed_event_count=scan["processed_event_count"],
        terminal_hard_gate_pass=scan["terminal_invariants"][
            "formal_hard_gate_pass"
        ],
    )
    selected = [dict(scan["skeletons"][0])]
    started = time.time()
    materialized = (
        module.g4irsf15_materialize_causal_descriptors_from_records(
            *native_arguments, selected
        )
    )
    emit(
        stage="materialize",
        elapsed_seconds=time.time() - started,
        schema=materialized["schema"],
        descriptor_count=materialized["materialized_descriptor_count"],
    )
    target = dict(materialized["descriptors"][0])
    target["horizon"] = "H_bag"
    target["intervention_sha256"] = target[
        "intervention_sha256_by_horizon"
    ]["H_bag"]
    started = time.time()
    pairs = module.g4irsf15_run_causal_target_pairs_from_records(
        *native_arguments, [target]
    )
    pair = pairs["pairs"][0]
    emit(
        stage="pair",
        elapsed_seconds=time.time() - started,
        schema=pairs["schema"],
        pair_status=pair["pair_status"],
        action_changed=pair.get("action_changed"),
        direct_affected_runtime_bag_ids=pair.get(
            "direct_affected_runtime_bag_ids"
        ),
        externality_observation_status=pair.get(
            "externality_observation_status"
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
