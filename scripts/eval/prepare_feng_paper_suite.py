"""Freeze the requested 480 base + 1280 all-day outage cells before outcomes."""
from __future__ import annotations
import argparse
from collections import defaultdict
from functools import cache
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts.eval import run_cie_component_activation as activation
from scripts.eval import run_g31_tarau_paper_suite as cpp
from scripts.eval import run_cie_external_baseline_robustness as external

BASE = ROOT / "configs/eval/feng_paper_suite_base_20260907.json"
FAULT = ROOT / "configs/eval/feng_paper_suite_fault_20260907.json"
SOURCE = ROOT / "docs/baselines/feng_paper_suite_source_contract_20260907.json"
NANNING = ROOT / "configs/eval/g4irsf31_nanning_fault_scenarios.json"
PLAN = ROOT / "outputs/evidence/paper_suite_20260907/frozen_plan_v4"
RESULTS = ROOT / "outputs/runtime/feng_paper_suite_20260907/cells"
NEW_BINARY = ROOT / "outputs/evidence/g31_fault_potential_repair_20260907/builds/38b07ddfbc661c5243ab62a4963d84514405a87b11afa41538a94a42d2665b20/czr005_cpp.cp311-win_amd64.pyd"
OLD_BINARY = ROOT / "build/nanning_ablation_gate_f_pybind/python/Release/czr005_cpp.cp311-win_amd64.pyd"
METHODS = {
    cpp.NEW_G31_METHOD: ("g31", "run_g31_tarau_paper_suite.py"),
    "HCA_TIME_LABEL_REPAIR_V3": ("hca", "run_hca_paper_suite.py"),
    "FENG_DH_PAPER_SUITE_V6": ("dh", "run_feng_dh_paper_suite.py"),
    "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY": ("tarau", "run_g31_tarau_paper_suite.py"),
}


@cache
def bound_sha(path):
    return cpp.sha256(Path(path))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def freeze(path, value):
    path = Path(path)
    content = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("refusing to change a frozen file: " + str(path))
    else:
        with path.open("xb") as stream:
            stream.write(content)
    return {"path": str(path.resolve()), "sha256": cpp.sha256(path)}


def closure(edges, initial):
    incoming, outgoing = defaultdict(set), defaultdict(set)
    for edge in edges:
        outgoing[edge[0]].add(edge)
        incoming[edge[1]].add(edge)
    disabled = set(initial)
    if not disabled <= edges:
        raise ValueError("initial failure is not an actual directed map edge")
    while True:
        expanded = set(disabled)
        for u, v in disabled:
            if outgoing[u] <= disabled:
                expanded.update(incoming[u])
            if incoming[v] <= disabled:
                expanded.update(outgoing[v])
        if expanded == disabled:
            return [list(edge) for edge in sorted(disabled)]
        disabled = expanded


def fault_protocol():
    base, source, nanning = read(BASE), read(SOURCE), read(NANNING)
    maps = {}
    for name in base["maps"]:
        profile = activation._profile_for_map(name, activation.DEFAULT_NANNING_PROFILE)
        edges = {(int(e[0]), int(e[1])) for e in profile.edge_records}
        lines = {int(line["line_id"]): tuple(line["edge"]) for line in nanning["lines"]} if name == "nanning" else None
        scenarios = []
        for entry in source["fault_scenarios"]:
            initial = [tuple(e) for e in entry["initial_edges"]] if name == "map2" else [lines[i] for i in entry["paper_line_ids"]]
            disabled = closure(edges, initial)
            if name == "map2" and disabled != sorted(entry["map2_affected_edges"]):
                raise ValueError("recomputed map2 closure differs from frozen source audit")
            scenarios.append({"scenario_index": entry["scenario_index"], "paper_line_ids": entry["paper_line_ids"],
                              "initial_failed_edges": [list(e) for e in initial], "failed_edges": disabled,
                              "affected_edges": disabled, "affected_count": len(disabled)})
        maps[name] = {"map_profile_path": str(profile.source_path.resolve()),
                      "map_profile_sha256": cpp.sha256(profile.source_path), "directed_edge_count": len(edges),
                      "scenarios": scenarios}
    value = {"schema": "czr005.feng_paper_suite_fault_protocol.v1", "family": "all_day_fault",
             "maps": base["maps"], "load_factors": base["load_factors"], "seeds": base["seeds"],
             "methods": [cpp.NEW_G31_METHOD, "HCA_TIME_LABEL_REPAIR_V3"], "speeds_mps": [2.5], "cell_count": 1280,
             "horizon_seconds": base["horizon_seconds"], "timing_policy": base["timing_policy"],
             "primary_timing": base["primary_timing"], "success_metrics": base["success_metrics"],
             "information_contract": "KNOWN_SURVIVING_TOPOLOGY_NO_SOURCE_PREFILTER",
             "fault_onset_contract": "All disabled directed edges known before each method's first routing; C++ time0 notification, Java first-round8260 notification. No repair before fixed horizon.",
             "propagation_contract": "Common parent computes least fixed point on each actual directed graph; all methods disable the identical resulting edge set. If all outgoing(u) fail, add incoming(u); if all incoming(v) fail, add outgoing(v).",
             "affected_line_count_definition": "Number of directed map edges in the disabled closure, including initial failures; identical exogenous input to both methods, not an algorithm outcome.",
             "source_contract": {"path": str(SOURCE), "sha256": cpp.sha256(SOURCE)},
             "nanning_selection": {"path": str(NANNING), "sha256": cpp.sha256(NANNING), "algorithm_outcomes_used": False},
             "scenario_maps": maps,
             "population_policy": "All raw bags and canonical legs remain; no reachability prefilter. Unreachable bags count unfinished at the same fixed horizon.",
             "claim_boundary": "Paper-shaped all-day known-outage comparison; not a full matrix of surprise mid-run failures or an exact publisher-final replication. Separate bounded G31 tests establish causal mid-run rerouting.",
             "paper_mismatch_policy": "Keep reconstructed source edge IDs and actual graph closure; disclose paper count inconsistencies, do not tune failure edges using outcomes.",
             "excluded": ["dynamic_static_speed_deviations", "CIE_DH_fault_cells", "Tarau_fault_cells", "fault_speeds_1.5_3.0"]}
    freeze(FAULT, value)
    return value


def prepare():
    base, fault = read(BASE), fault_protocol()
    assert cpp.sha256(NEW_BINARY) == "38b07ddfbc661c5243ab62a4963d84514405a87b11afa41538a94a42d2665b20"
    assert cpp.sha256(OLD_BINARY) == "b00fd178dca5b3f201d50ddfc6446959272baa4cc45b4ee01a2f08e0c85a91f5"
    protocols = [{"path": str(path), "sha256": cpp.sha256(path), "family": value["family"]}
                 for path, value in ((BASE, base), (FAULT, fault))]
    cells, workload_bindings = [], []
    identities = {}
    for name in base["maps"]:
        for load in base["load_factors"]:
            for seed in base["seeds"]:
                path = ROOT / f"data/processed/workloads/cie_external_robustness/{name}_{int(load)}p00x/seed_{seed}/identity.json"
                external.audit_cell(path)
                identities[(name, load, seed)] = {"path": str(path), "sha256": cpp.sha256(path)}
                workload_bindings.append(identities[(name, load, seed)])
    for protocol_path, protocol in ((BASE, base), (FAULT, fault)):
        family = protocol["family"]
        for name in protocol["maps"]:
            profile = activation._profile_for_map(name, activation.DEFAULT_NANNING_PROFILE)
            for load in protocol["load_factors"]:
                for speed in protocol["speeds_mps"]:
                    scenarios = [{"scenario_index": 0}] if family == "base" else fault["scenario_maps"][name]["scenarios"]
                    for scenario in scenarios:
                        for seed in protocol["seeds"]:
                            for method in protocol["methods"]:
                                short, runner_name = METHODS[method]
                                cid = f"{'b' if family=='base' else 'f'}_{name}_{int(load)}x_v{str(speed).replace('.', 'p')}_s{seed}_q{scenario['scenario_index']:02}_{short}"
                                binding = identities[(name, load, seed)]
                                spec = {"schema": cpp.SPEC_SCHEMA, "cell_id": cid, "family": family, "method": method,
                                        "map": name, "load_factor": load, "seed": seed, "speed_mps": speed,
                                        "horizon_seconds": protocol["horizon_seconds"], "timing_policy": protocol["timing_policy"],
                                        "workload_identity_path": binding["path"], "workload_identity_sha256": binding["sha256"],
                                        "protocol_path": str(protocol_path), "protocol_sha256": bound_sha(protocol_path)}
                                if short in ("g31", "tarau"):
                                    binary = NEW_BINARY
                                    spec.update(binary_path=str(binary), binary_sha256=bound_sha(binary),
                                                map_profile_path=str(profile.source_path.resolve()), map_profile_sha256=bound_sha(profile.source_path),
                                                trace={"decision_limit": 1000, "event_limit": 1000})
                                    if short == "tarau":
                                        spec["executor_contract"] = "Shared38b executor, M1/jit_fifo, fault repair disabled. Fixes horizon active-state audit ordering; retained b00 remains a bounded behavior control."
                                else:
                                    classes = ROOT / f"build/{'hca_paper_suite_v3' if short == 'hca' else 'feng_dh_paper_suite_v6'}_20260907"
                                    spec.update(classes_dir=str(classes), build_identity_sha256=bound_sha(classes / "build_identity.json"),
                                                java=r"C:\PROGRAMING\jdk-18\bin\java.exe", javac=r"C:\PROGRAMING\jdk-18\bin\javac.exe", heap_mb=1536)
                                if family == "all_day_fault":
                                    mapping = SOURCE if name == "map2" else FAULT
                                    spec.update(scenario, scenario_id=f"{name}_paper_{scenario['scenario_index']:02}",
                                                fault_notification_epoch=8260, fault_mapping_path=str(mapping), fault_mapping_sha256=bound_sha(mapping),
                                                scenario={"information_contract": fault["information_contract"], "fault_edges": scenario["failed_edges"]})
                                spec_path = PLAN / "specs" / (cid+".json")
                                frozen = freeze(spec_path, spec)
                                runner = ROOT / "scripts/eval" / runner_name
                                cells.append({"cell_id": cid, "family": family, "method": method, "map": name,
                                              "load_factor": load, "speed_mps": speed, "seed": seed, "scenario_index": scenario["scenario_index"],
                                              "spec_path": frozen["path"], "spec_sha256": frozen["sha256"],
                                              "output_dir": str(RESULTS / cid), "runner_path": str(runner), "runner_sha256": bound_sha(runner)})
    assert len(cells) == 1760 and len({c["cell_id"] for c in cells}) == 1760
    plan = {"schema": "czr005.feng_paper_suite.plan.v1", "status": "FROZEN_SPECS_NOT_ALL_EXECUTED", "result_root": str(RESULTS),
            "protocols": protocols, "cell_count": len(cells), "family_counts": {"base": 480, "all_day_fault": 1280},
            "workload_bindings": workload_bindings, "preparer_sha256": cpp.sha256(Path(__file__)), "cells": cells}
    frozen = freeze(PLAN / "plan.json", plan)
    print(json.dumps({**frozen, "cells": len(cells), "families": plan["family_counts"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fault-protocol", "plan"))
    args = parser.parse_args()
    if args.command == "fault-protocol":
        result = fault_protocol()
        print(json.dumps({"path": str(FAULT), "sha256": cpp.sha256(FAULT), "cell_count": result["cell_count"]}))
    else:
        prepare()
