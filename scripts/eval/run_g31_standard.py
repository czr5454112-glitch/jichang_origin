"""Run G31 with the registered continuous-motion physical model by default.

Positive devices and directed edge entries use a two-second half-open safety
interval. Physical registration is separate from performance promotion. Use
--execution-model legacy_waiting to reproduce the historical waiting protocols.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts.experiments.g31_feng_alignment import experiment, map2_experiment, metrics
from scripts.eval import g31_continuous_adapter as continuous

DEFAULT_CONFIG = ROOT / "configs/eval/g31_standard.json"
MODES = ("legacy", "eta_calendar", "eta_flow")
MAPS = ("nanning", "map2")
EXECUTION_MODELS = ("legacy_waiting", continuous.MODEL)
DEFAULT_EXECUTION_MODEL = continuous.MODEL


def rooted(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def load_config(path=DEFAULT_CONFIG):
    config = experiment.read(rooted(path))
    if config.get("schema") != "g31.standard.config.v1":
        raise ValueError("unknown G31 standard configuration schema")
    if config.get("s4_wait_estimator") not in MODES:
        raise ValueError("unknown standard s4_wait_estimator")
    if set(config.get("maps", [])) != set(MAPS):
        raise ValueError("standard configuration must retain both verified maps")
    if (config.get("scale"), config.get("speed_mps"), config.get("fault_schedule")) != (1, 2.0, "none"):
        raise ValueError("this entrypoint supports only verified 1x, 2 m/s, no-fault cases")
    if config.get("empty_trays") is not False or config.get("add_edge_capacity") is not False:
        raise ValueError("empty trays and added edge capacity are outside this standard")
    return config


def select(map_name, *, mode=None, binary=None, same_hca_release=None, config_path=DEFAULT_CONFIG):
    config_path = rooted(config_path).resolve(strict=True)
    config = load_config(config_path)
    if map_name not in MAPS:
        raise ValueError("unknown standard map")
    selected_mode = mode if mode is not None else config["s4_wait_estimator"]
    if selected_mode not in MODES:
        raise ValueError("unknown s4_wait_estimator")
    binary_path = rooted(binary or config["default_binary"]).resolve(strict=True)
    binary_evidence = experiment.evidence(binary_path)
    matches_reference = binary_evidence["sha256"] == config["default_binary_sha256"]
    if binary is None and not matches_reference:
        raise ValueError("configured standard binary hash changed; use an explicit --binary for a recorded rebuild")
    release_path = rooted(same_hca_release).resolve(strict=True) if same_hca_release else None
    is_standard = selected_mode == config["s4_wait_estimator"]
    comparison_labels = {
        "legacy": "historical_legacy_comparison",
        "eta_calendar": "experimental_calendar_comparison",
        "eta_flow": "experimental_flow_comparison",
    }
    label = "historical_legacy_comparison" if is_standard else comparison_labels[selected_mode]
    selection = {
        "schema": "g31.standard.selection.v1", "standard_id": config["standard_id"],
        "adoption_reason": config["adoption_reason"], "previous_standard": config["previous_standard"],
        "reference_review_commit": config["reference_review_commit"], "map": map_name,
        "standard_wait_estimator": config["s4_wait_estimator"], "selected_wait_estimator": selected_mode,
        "mode_explicitly_selected": mode is not None, "is_standard_selection": False,
        "matches_historical_profile": is_standard, "execution_model": "legacy_waiting",
        "physics_default": False, "performance_promoted": False,
        "selection_label": label, "config": experiment.evidence(config_path),
        "entrypoint": experiment.evidence(Path(__file__)), "binary": binary_evidence,
        "binary_matches_verified_reference": matches_reference, "binary_explicitly_selected": binary is not None,
        "same_hca_release": experiment.evidence(release_path) if release_path else None,
        "scale": 1, "speed_mps": 2.0, "fault_schedule": "none", "empty_trays": False,
        "added_edge_capacity": False,
        "boundary": "Explicit historical waiting-model reproduction. Frozen requests, research manifests and generic native API defaults are unchanged; this is not the current default physical model.",
    }
    return selection, binary_path, release_path


def prepare_request(map_name, *, mode=None, binary=None, same_hca_release=None, config_path=DEFAULT_CONFIG,
                    execution_model=DEFAULT_EXECUTION_MODEL, controls=None, scale=1,
                    physical_contract=continuous.DEFAULT_CONTRACT):
    """Construct the complete selected request; never load or execute C++."""
    validate_model_options(execution_model,mode,same_hca_release,controls,scale,config_path,physical_contract)
    if execution_model==continuous.MODEL:
        prepared=continuous.prepare(map_name,scale=scale,controls_path=controls,binary=binary,contract_path=physical_contract)
        return prepared["request"],prepared["selection"]
    selection, binary_path, release_path = select(
        map_name, mode=mode, binary=binary, same_hca_release=same_hca_release, config_path=config_path)
    selected_mode = selection["selected_wait_estimator"]
    if map_name == "map2":
        request, canonical, _ = map2_experiment.prepare_request(binary_path, selected_mode, release_path)
    else:
        native = experiment.native31
        canonical = metrics.read_jsonl(experiment.CANONICAL)
        workload = native.load_workload(1, native.DEFAULT_TASK_DIR)
        if release_path:
            releases = metrics.generator_releases(canonical, metrics.java_segments(release_path))
            workload = replace(workload, rows=tuple(
                {**row, "pass_time": releases[row["segment_id"]]} for row in workload.rows))
        request, rows, rejected, _ = native.prepare_native_request(
            native.case_by_id("t5_2_nanning_1x_speed_2"), workload,
            map_profile_path=native.DEFAULT_MAP_PROFILE, fault_protocol_path=native.DEFAULT_FAULT_PROTOCOL,
            binary=binary_path)
        if rejected or len(rows) != 43603:
            raise ValueError("standard execution must retain every canonical segment")
        request["s4_wait_estimator"] = selected_mode
    request["trace_limit"] = 0
    request["event_trace_limit"] = 0
    if len(canonical) != 43603 or request["local_queue_capacity"] != 0:
        raise ValueError("standard population or queue contract changed")
    return request, selection


def validate_model_options(model,mode,release,controls,scale,config_path,physical_contract):
    if model not in EXECUTION_MODELS: raise ValueError("unknown G31 execution model")
    if model==continuous.MODEL:
        if mode is not None or release is not None:
            raise ValueError("continuous mode cannot use legacy --s4-wait-estimator or --same-hca-release; select --execution-model legacy_waiting explicitly")
        if rooted(config_path).resolve()!=DEFAULT_CONFIG.resolve():
            raise ValueError("continuous mode uses --physical-contract and --controls, not legacy --config")
    elif controls is not None or scale!=1 or rooted(physical_contract).resolve()!=continuous.DEFAULT_CONTRACT.resolve():
        raise ValueError("legacy waiting mode does not support continuous controls, physical contract or scale 2")


def run(args):
    output = rooted(args.output).resolve()
    if output.exists():
        raise FileExistsError("preserve existing results; choose a fresh standard output directory")
    # Frozen research directories remain immutable, even when a new child name
    # would otherwise avoid replacing an individual historical run.
    if any(output.is_relative_to(campaign.resolve()) for campaign in (experiment.CAMPAIGN, map2_experiment.CAMPAIGN)):
        raise ValueError("standard runs require a new campaign outside the frozen research directories")
    # A missing model follows the same physical default as CLI/API calls.
    # Historical programmatic callers must select legacy_waiting explicitly.
    for key,value in (("execution_model",DEFAULT_EXECUTION_MODEL),("controls",None),("scale",1),
                      ("physical_contract",continuous.DEFAULT_CONTRACT)):
        if not hasattr(args,key): setattr(args,key,value)
    validate_model_options(args.execution_model,args.s4_wait_estimator,args.same_hca_release,
                           args.controls,args.scale,args.config,args.physical_contract)
    if args.execution_model==continuous.MODEL:
        prepared=continuous.prepare(args.map,scale=args.scale,controls_path=args.controls,
                                    binary=args.binary,contract_path=args.physical_contract)
        selection=prepared["selection"]
        selection["entrypoint"]=experiment.evidence(Path(__file__))
        try:
            manifest=continuous.execute(prepared,output)
            selection["execution_status"]=manifest["status"]
        except BaseException:
            if output.is_dir():
                selection["execution_status"]="failed_or_interrupted"
                experiment.write(output/"standard_selection.json",selection)
            raise
        shutil.copyfile(__file__,output/"standard_sources"/"run_g31_standard.py")
        experiment.write(output/"standard_selection.json",selection)
        print(json.dumps({"execution_model":continuous.MODEL,"status":manifest["status"],
                          "physics_default":selection["physics_default"],
                          "performance_promoted":False,"summary":str(output/"summary.json")},ensure_ascii=False))
        return
    selection, binary, release = select(
        args.map, mode=args.s4_wait_estimator, binary=args.binary,
        same_hca_release=args.same_hca_release, config_path=args.config)
    delegated = SimpleNamespace(
        arm=args.arm or f"g31_{args.map}_{selection['selected_wait_estimator']}", binary=binary,
        output=output, s4_wait_estimator=selection["selected_wait_estimator"], same_hca_release=release,
        trace_limit=0, event_trace_limit=0, assert_matches_native_payload=None)
    runner = experiment if args.map == "nanning" else map2_experiment
    selection["delegated_runner"] = experiment.evidence(Path(runner.__file__))
    selection["historical_manifest_modified"] = False
    try:
        runner.run_native(delegated)
    except BaseException:
        if output.is_dir():
            selection["execution_status"] = "failed_or_interrupted"
            experiment.write(output / "standard_selection.json", selection)
        raise
    selection["execution_status"] = "completed"
    frozen = output / "standard_sources"
    frozen.mkdir()
    for key in ("config", "entrypoint"):
        source = Path(selection[key]["path"])
        if experiment.sha(source) != selection[key]["sha256"]:
            raise ValueError(f"standard {key} changed while the run was executing")
        shutil.copyfile(source, frozen / source.name)
    selection["request"] = experiment.evidence(output / "request.json.gz")
    experiment.write(output / "standard_selection.json", selection)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("inspect", "run"):
        command = commands.add_parser(name)
        command.add_argument("--map", required=True, choices=MAPS)
        command.add_argument("--execution-model",choices=EXECUTION_MODELS,default=DEFAULT_EXECUTION_MODEL)
        command.add_argument("--scale",type=int,choices=(1,2),default=1)
        command.add_argument("--controls",type=Path,help="override registered continuous controls; physical default is not a performance-winner claim")
        command.add_argument("--physical-contract",type=Path,default=continuous.DEFAULT_CONTRACT)
        command.add_argument("--s4-wait-estimator", choices=MODES)
        command.add_argument("--binary", type=Path)
        command.add_argument("--same-hca-release", type=Path)
        command.add_argument("--config", type=Path, default=DEFAULT_CONFIG,help="legacy waiting-model registration")
        if name == "run":
            command.add_argument("--output", required=True, type=Path)
            command.add_argument("--arm")
    return result


def main():
    args = parser().parse_args()
    if args.command == "run":
        run(args)
        return
    request, selection = prepare_request(
        args.map, mode=args.s4_wait_estimator, binary=args.binary,
        same_hca_release=args.same_hca_release, config_path=args.config,
        execution_model=args.execution_model,controls=args.controls,scale=args.scale,
        physical_contract=args.physical_contract)
    if args.execution_model==continuous.MODEL:
        print(json.dumps({"selection":selection,"native_execution_started":False,
                          "request_summary":{"nodes":len(request["nodes"]),"edges":len(request["edges"]),
                              "segments":len(request["tasks"]),"controls":request["config"]}},ensure_ascii=False,indent=2))
        return
    print(json.dumps({"selection": selection, "native_execution_started": False,
                      "request_summary": {"scorer_mode": request["scorer_mode"],
                          "s4_wait_estimator": request["s4_wait_estimator"],
                          "nodes": len(request["node_records"]), "edges": len(request["edge_records"]),
                          "segments": len(request["bag_records"]), "max_events": request["max_events"],
                          "horizon": request["max_simulation_time"]}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
