"""Full first source-hour development window, including every early bag.

Budget exits remain censored and preserve all expected task IDs. Read-only
source normalization is completed before selecting this predeclared time rule.
"""
from collections import Counter
from dataclasses import asdict
from decimal import Decimal
import gzip
from hashlib import sha256
import json
import pickle
from pathlib import Path
import sys
from time import process_time, perf_counter
import traceback

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
INPUTS = BASE.parent / "phase4_round9_business_inputs_20261011"
OLD = BASE.parent / "phase4_w3_round8_business_input_research_repaired_20261010"
TASKS = ROOT / ".g4irsf24_worktree/artifacts/tasks/g4irsf31_nanning"
PROFILE = ROOT / "scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json"
cpu, wall = process_time(), perf_counter()
from scripts.experiments.ics_circulation_v3.business_inputs import load_business_workload
from scripts.experiments.ics_circulation_v3.business_runtime import build_business_runtime
from scripts.experiments.ics_circulation_v3.runtime import Simulation
from scripts.experiments.ics_circulation_v3.storage_lifecycle import lifecycle_report
from scripts.experiments.ics_circulation_v3.network_full_cycle import physical_result
from scripts.experiments.ics_circulation_v3.experiment_resources import memory_snapshot


def source_inputs(input_contract):
    return dict(normalized=OLD / "business_tasks_1x.jsonl.gz",
        normalization_manifest=OLD / "manifest.json", raw=TASKS / "nanning_1x_raw.txt",
        canonical=TASKS / "nanning_1x_canonical.jsonl",
        source_timetable=ROOT / "legacy/jichang_origin_readonly/inputdata.txt",
        source_manifest=TASKS / "nanning_1x_manifest.json", graph_profile=PROFILE, contract=input_contract)


def build_explicit_projected_runtime(workload, runtime_contract, input_contract, output):
    from scripts.experiments.ics_circulation_v3.business_projection import project_business_destinations
    from scripts.experiments.ics_circulation_v3.business_projection_runtime import (
        RUN_POLICIES, build_projected_business_runtime)
    from scripts.experiments.ics_circulation_v3.business_runtime import parse_runtime_proxy_contract
    locked = json.loads((BASE / "frozen_projection_inputs.json").read_bytes())
    for name, digest in locked["files"].items():
        assert sha256((ROOT / name).read_bytes()).hexdigest() == digest, "frozen Round10 projection artifact changed"
    declaration = json.loads((BASE.parent / "phase4_round10_business_projection_20261011/full_audit_002/projection_contract_1x.json").read_bytes())
    assert workload.content_sha256 == locked["source_workload_sha256"]
    projection = project_business_destinations(workload, PROFILE, declaration)
    assert projection.content_sha256 == locked["projection_content_sha256"]
    assert projection.contract.canonical_sha256 == locked["projection_contract_sha256"]
    runtime = parse_runtime_proxy_contract(runtime_contract, workload)
    run = dict(RUN_POLICIES, run_id="round11-window-h" + str(runtime.search_horizon),
        title="Fixed whole-parent destination runtime proxy",
        source_workload_sha256=locked["source_workload_sha256"],
        input_contract_sha256=workload.contract.canonical_sha256,
        projection_sha256=locked["projection_content_sha256"],
        projection_contract_sha256=locked["projection_contract_sha256"],
        runtime_contract_sha256=runtime.canonical_sha256,
        graph_sha256=workload.contract.graph_sha256,
        assumption_id="round11-full-family-runtime-v1",
        source_ref="Round11 PROTOCOL.md; fixed Round10 full_audit_002")
    # Commit the explicit input agreement before constructing the runtime.
    (output / "projection_run_contract.json").write_text(json.dumps(run, indent=2))
    (output / "projection_declaration.json").write_text(json.dumps(declaration, indent=2))
    adapted = build_projected_business_runtime(workload, projection,
        source_inputs=source_inputs(input_contract), projection_declaration=declaration,
        runtime_contract=runtime_contract, run_contract=run, profile_path=PROFILE)
    first = min(t.arrival_seconds for t in workload.tasks)
    selected = [r for r in projection.records if first <= r.original.arrival_seconds < first + Decimal(3600)]
    evidence = dict(source_workload_sha256=workload.content_sha256,
        projection_sha256=projection.content_sha256,
        projection_contract_sha256=projection.contract.canonical_sha256,
        run_contract_sha256=adapted.environment_projection.run_contract.canonical_sha256,
        full_source_count=len(projection.records), full_parent_group_count=len(projection.groups),
        full_changed_count=sum(r.original_destination != r.projected_destination for r in projection.records),
        window_records=[asdict(r) for r in selected],
        qualification="Original fields retained; different input version; full mapping is environment-private")
    return adapted, evidence

run_name, horizon, variant = sys.argv[1], int(sys.argv[2]), sys.argv[3]
assert horizon in (80, 21600) and variant in ("original", "projected")
output = BASE / run_name
output.mkdir()
protocol = {"scale": 1, "window_rule": "first exact source arrival <= arrival_seconds < first + 3600 seconds",
    "burn_in": "advance from source epoch 0 with no clock jump; all earlier tasks retained (none by this window rule)",
    "tail_cap_rule": "max included deadline tick + 3600", "cpu_cap_seconds": 600,
    "wall_cap_seconds": 900, "search_horizon": horizon, "route_mode": "whole_route",
    "scope": "fixed research proxy development; source 1x only; no independent day or throughput claim",
    "input_contract": "runtime_input_contract_002.json", "runtime_contract": "runtime_proxy_contract_002.json",
    "only_variant": variant, "design": "Round11 original vs explicit fixed projection, same full source hour",
    "matched_stop_ticks": [10080, 11760, 24180, 28500], "actual_default_generator_request_k": 1,
    "remove_unreachable": False, "initial_carriers": 11, "storage_slots": 1,
    "physics_started": False, "physical_runs_started": 0, "physical_runs_completed": 0, "outer_advance_chunk_ticks": 60, "budget_check_boundary": "between chunks; at most 60 physical ticks overshoot"}
(output / "protocol.json").write_text(json.dumps(protocol, indent=2))
(output / "frozen_projection_inputs.json").write_bytes((BASE / "frozen_projection_inputs.json").read_bytes())
paths = sorted((ROOT / "scripts/experiments/ics_circulation_v3").glob("*.py"))
paths += [ROOT / "cpp/ics_core/runtime/bounded_local_pibt.hpp", Path(__file__), BASE / "PROTOCOL.md", BASE / "frozen_projection_inputs.json"]
def bindings():
    return {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in paths}
before = bindings()
for source_path in paths:
    target = output / "source_snapshot" / source_path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source_path.read_bytes())
(output / "before.json").write_text(json.dumps(before, indent=2))
report = {"success": False, "physics_started": False, "physical_runs_started": 0, "physical_runs_completed": 0, "outer_advance_chunk_ticks": 60, "budget_check_boundary": "between chunks; at most 60 physical ticks overshoot"}
engine = None
try:
    input_contract = json.loads((INPUTS / protocol["input_contract"]).read_bytes())
    runtime_contract = json.loads((INPUTS / protocol["runtime_contract"]).read_bytes())
    runtime_contract["routing"]["search_horizon"] = horizon
    runtime_contract["contract_id"] += f"-window-h{horizon}"
    workload = load_business_workload(**source_inputs(input_contract))
    projection_info = None
    if variant == "original":
        adapted = build_business_runtime(workload, PROFILE, runtime_contract)
    else:
        adapted, projection_info = build_explicit_projected_runtime(workload, runtime_contract, input_contract, output)
    first = min(t.arrival_seconds for t in workload.tasks)
    selected = [t for t in workload.tasks if first <= t.arrival_seconds < first + Decimal(3600)]
    expected = {t.business_bag_id for t in selected}
    tape = tuple(b for b in adapted.future_bags if b.bag_id in expected)
    assert len(tape) == len(expected) == len(selected)
    assert len(tape) == 44 and len(workload.tasks) == 28506
    cap = max(b.deadline for b in tape) + 3600
    assert cap == 28500
    def json_value(v):
        if isinstance(v, Decimal):
            return str(v)
        raise TypeError(type(v).__name__)
    (output / "full_window_source_tasks.json").write_text(json.dumps([asdict(t) for t in selected], indent=2, default=json_value))
    (output / "environment_tape.json").write_text(json.dumps([asdict(b) for b in tape], indent=2))
    (output / "runtime_contract.json").write_text(json.dumps(runtime_contract, indent=2))
    (output / "initial_snapshot.json").write_text(json.dumps(asdict(adapted.initial), indent=2))
    (output / "scope.json").write_text(json.dumps({"full_source_count": len(workload.tasks),
        "included_count": len(tape), "excluded_later_count": len(workload.tasks)-len(tape),
        "first_source_second": str(first), "exclusive_end_second": str(first+Decimal(3600)),
        "all_window_ids": sorted(expected), "tail_cap_tick": cap,
        "input_binding": dict(workload.input_sha256)}, indent=2))
    if projection_info is not None:
        (output / "projection_runtime_evidence.json").write_text(json.dumps(projection_info, indent=2, default=json_value))
    counts = Counter()
    with gzip.open(output / "queries.jsonl.gz", "wt", encoding="utf-8") as query_file:
        class MeteredSimulation(Simulation):
            def _generate(self, tray, destination=None):
                candidates = super()._generate(tray, destination)
                status = self._generator.last_search_status
                counts[status] += 1
                query_file.write(json.dumps({"now": self.state.now, "tray_id": tray.tray_id,
                    "bag_id": tray.bag_id, "destination": destination, "status": status,
                    "candidate_count": len(candidates), "expansions": self._generator.last_expansions,
                    "diagnostics": self._generator.last_diagnostics})+"\n")
                return candidates
        report["physics_started"] = True
        report["physical_runs_started"] = 1
        engine = MeteredSimulation(adapted.initial, tape, **adapted.simulation_kwargs())
        physical_cpu, physical_wall = process_time(), perf_counter()
        status = "fixed_tick_cap_censored"
        while engine.state.now < cap:
            if process_time()-physical_cpu > protocol["cpu_cap_seconds"]:
                status = "cpu_cap_censored"
                break
            if perf_counter()-physical_wall > protocol["wall_cap_seconds"]:
                status = "wall_cap_censored"
                break
            engine.advance(min(cap, engine.state.now + 60))
            if engine.state.now in protocol["matched_stop_ticks"]:
                with gzip.open(output / f"matched_{engine.state.now}.json.gz", "wt", encoding="utf-8") as matched_file:
                    json.dump(physical_result(engine.result()), matched_file)
                (output / f"matched_{engine.state.now}_lifecycle.json").write_text(json.dumps(lifecycle_report(engine, sorted(expected)), indent=2))
            if engine.state.now % 600 == 0:
                (output / f"checkpoint_{engine.state.now}.pickle").write_bytes(pickle.dumps(engine.checkpoint()))
                print(json.dumps({"now": engine.state.now, "observed": len(engine.state.bags),
                    "completed": len(engine.state.completed), "cpu_s": process_time()-physical_cpu}), flush=True)
            if (not engine._arrivals and len(engine.state.completed) == len(expected)
                    and not engine.state.plans and not engine.state.empty_targets
                    and all(t.mode == "empty" and t.bag_id is None for t in engine.state.trays.values())):
                status = "transport_drained"
                break
        report.update(success=True, physical_runs_completed=1, status=status, lifecycle=lifecycle_report(engine, sorted(expected)),
            search_status_counts=dict(counts), physics_cpu_seconds=process_time()-physical_cpu,
            physics_wall_seconds=perf_counter()-physical_wall,
            no_independent_operating_day=True, no_task_thinning=True)
except Exception:
    report.update(status="execution_failure", exception=traceback.format_exc())
finally:
    if engine is not None:
        try:
            (output / "final_checkpoint.pickle").write_bytes(pickle.dumps(engine.checkpoint()))
            with gzip.open(output / "final_result.json.gz", "wt", encoding="utf-8") as f:
                json.dump(physical_result(engine.result()), f)
        except Exception:
            report["final_result_failure"] = traceback.format_exc()
    after = bindings()
    report.update(source_changed=[p for p in before if before[p] != after[p]],
        cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall, memory=memory_snapshot(),
        resource_scope="Current process interval incl imports/input/full source validation/physics/raw serialization; nested physics CPU not additional; final report/source-after writes excluded")
    (output / "after.json").write_text(json.dumps(after, indent=2))
    (output / "results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ("lifecycle", "search_status_counts")}, indent=2))
sys.exit(0 if report["success"] and not report["source_changed"] else 1)
