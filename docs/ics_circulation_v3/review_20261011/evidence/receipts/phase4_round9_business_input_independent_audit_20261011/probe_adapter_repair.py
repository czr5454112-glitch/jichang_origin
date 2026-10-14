"""Independent contract-tampering regressions, no simulation execution."""
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import runpy
import sys
import time
import traceback

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
OUT = BASE / "adapter_repair_001"
OUT.mkdir()
cpu, wall = time.process_time(), time.perf_counter()
source_paths = [ROOT / "scripts/experiments/ics_circulation_v3" / name for name in
                ("business_inputs.py", "business_runtime.py")]
before = {str(p): sha256(p.read_bytes()).hexdigest() for p in source_paths}
for path in source_paths:
    (OUT / path.name).write_bytes(path.read_bytes())
result = {"status": "running", "physics_calls": 0, "rows": [], "before": before}
try:
    helpers = runpy.run_path(str(ROOT / "tests/test_ics_v3_business_input_audit.py"))
    fixture = OUT / "fixture"
    fixture.mkdir()
    files = helpers["independent_input"].__wrapped__(fixture)
    profile = json.loads(files["graph_profile"].read_bytes())
    for node in profile["nodes"]:
        node["system_key"] = "audit-proxy"
    profile["edges"] = [
        dict(start=10, end=50, length="1.00000000000000000000000000000000001", speed="1", capacity=1),
        dict(start=50, end=30, length="1", speed="1", capacity=1),
        dict(start=30, end=10, length="1", speed="1", capacity=0)]
    helpers["json_write"](files["graph_profile"], profile)
    files["contract"]["graph_sha256"] = helpers["digest"](files["graph_profile"])
    helpers["bind"](files)
    from scripts.experiments.ics_circulation_v3.business_inputs import (
        BusinessInputError, business_workload_sha256, load_business_workload)
    from scripts.experiments.ics_circulation_v3.business_runtime import build_business_runtime
    workload = load_business_workload(**files)
    contract = dict(schema="ics_business_runtime_proxy_v1", contract_id="independent-repair-proxy",
        evidence_status="proxy_research", input_contract_sha256=workload.contract.canonical_sha256,
        graph_sha256=workload.contract.graph_sha256,
        node_resource_policy="exact_bound_input_node_capacity_and_loaded_wait",
        empty_wait_policy="same_as_declared_loaded_wait_proxy",
        edge_permission_policy="both_modes_all_source_directed_edges_proxy",
        edge_capacity_policy="preserve_source_integer_including_closed_zero",
        travel_policy="exact_length_over_speed_ceil_to_input_tick",
        partition_by_node={n.node_id: "proxy-owner" for n in workload.contract.nodes},
        module=dict(kind="existing_fixed_fifo_proxy", loading_seconds="0", unload_seconds="0.01",
            hold_seconds_by_node={n.node_id: "0.01" for n in workload.contract.nodes},
            reception_capacity=1, export_min_stock=0),
        routing=dict(route_mode="next_edge", search_horizon=80, candidate_count=2, expansion_limit=5000,
            static_path_limit=12, local_label_limit=3, dynamic_local=True, deadline_ms=None,
            cache_contract="isolated_replay_v1"), reactive_empty_dispatch=True,
        coordination_order="route_then_prebalance",
        evidence=[dict(field=name, source_ref="independent hand fixture", assumption_id="audit-" + name)
                  for name in ("permissions", "module", "partition", "travel_capacity", "routing", "coordination")])
    normal = build_business_runtime(workload, files["graph_profile"], contract)
    assert not normal.initial.bags and not normal.initial.storage_progress
    assert len(normal.future_bags) == 3 and len(normal.initial.trays) == 1
    assert normal.initial.network.edges["10->50"].travel_time == 11
    assert normal.initial.network.edges["30->10"].capacity == 0
    index = next(i for i, t in enumerate(workload.tasks) if t.source.raw_task_id == 7)
    early = workload.tasks[index]
    variants = {
        "remove_protection": replace(early, protected=False),
        "relax_final_deadline": replace(early, deadline_seconds=Decimal("9999"), deadline=99990),
        "erase_early_storage": replace(early, lifecycle="direct", storage_node=None,
            scheduled_release_seconds=None, release_at=None, published_at=None),
        "advance_release": replace(early, scheduled_release_seconds=Decimal("2100"), release_at=21000)}
    for reseal in (False, True):
        for name, task in variants.items():
            tasks = list(workload.tasks)
            tasks[index] = task
            altered = replace(workload, tasks=tuple(tasks))
            if reseal:
                altered = replace(altered, content_sha256=business_workload_sha256(altered))
            try:
                build_business_runtime(altered, files["graph_profile"], contract)
            except BusinessInputError as error:
                result["rows"].append({"mutation": name, "resealed": reseal, "rejected": True, "reason": str(error)})
            else:
                raise AssertionError(f"contract mutation accepted: {name}, reseal={reseal}")
    after = {str(p): sha256(p.read_bytes()).hexdigest() for p in source_paths}
    assert after == before
    result.update(status="passed", checks=8, after=after)
except BaseException:
    result.update(status="failed", failure=traceback.format_exc())
finally:
    result.update(cpu_seconds=time.process_time() - cpu, wall_seconds=time.perf_counter() - wall,
                  scope="imports, independent fixture load/build, eight adapter tamper cases; zero physics",
                  prior_gap="pre-fix was identified by static review and confirmed by source author; no independent pre-fix probe was executed")
    (OUT / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
sys.exit(0 if result["status"] == "passed" else 1)
