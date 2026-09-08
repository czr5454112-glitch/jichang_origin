"""Real-C++ fault-only S4 potential repair checks; never runs a full workload.

Each binary runs in a fresh Python process, so the frozen b00 extension cannot
be confused with the new extension through Python's module cache. Set
G31_FAULT_REPAIR_BINARY to select another isolated repair build. Native output
is preserved below G31_FAULT_REPAIR_EVIDENCE (default: a dedicated runtime dir).
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "src"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from scripts.eval import run_cie_component_activation as activation
from scripts.eval import g4irsf31_map_adapter as adapter
from scripts.eval import run_g31_tarau_paper_suite as encoding

OLD_BINARY = ROOT / "build/nanning_ablation_gate_f_pybind/python/Release/czr005_cpp.cp311-win_amd64.pyd"
OLD_SHA = "b00fd178dca5b3f201d50ddfc6446959272baa4cc45b4ee01a2f08e0c85a91f5"
NEW_BINARY = Path(os.environ.get("G31_FAULT_REPAIR_BINARY", ROOT / "build/g31_fault_potential_repair_20260907/python/Release/czr005_cpp.cp311-win_amd64.pyd"))
EVIDENCE = Path(os.environ.get("G31_FAULT_REPAIR_EVIDENCE", ROOT / "outputs/runtime/g31_fault_potential_repair_20260907/microtests"))
FLAG = "enable_s4_advertised_fault_potential_repair"
SCENARIO = "G31_FAULT_POTENTIAL_REPAIR_BOUNDED_REAL_MAP_MICROTEST"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoding._bytes(value))


def write_gzip(path: Path, value: object) -> None:
    path.write_bytes(gzip.compress(encoding._bytes(value), mtime=0))


def read_gzip(path: Path) -> dict:
    return encoding._decode(json.loads(gzip.decompress(path.read_bytes())))


def _bag(identity: int, start: int, goal: int, release: float = 0) -> dict:
    return dict(segment_id=f"{identity}:direct", task_id=identity, start=start, goal=goal,
                pass_time=release, std=5000.0, original_entry_time=release)


def case_definition(name: str) -> dict:
    """Cases are fixed by topology/notification semantics, not performance."""
    map_name = "nanning" if name.startswith("nanning") else "map2"
    rows = [_bag(1001, 0, 16 if map_name == "nanning" else 47)]
    faults, horizon = [], 1000.0
    if name.endswith("mid_fault"):
        faults = [(1, 2, 2.0, 1001.0, 0.0, False)] if map_name == "nanning" else [(6, 12, 1.0, 1001.0, 0.0, False)]
    elif name == "map2_simultaneous_faults":
        faults = [(6, 12, 1.0, 1001.0, 0.0, False), (11, 13, 1.0, 1001.0, 0.0, False)]
    elif name == "map2_successive_faults":
        faults = [(6, 12, 1.0, 1001.0, 0.0, False), (11, 13, 6.0, 1001.0, 0.0, False)]
    elif name == "map2_delayed_notification":
        faults = [(6, 12, 1.0, 1001.0, 10.0, False)]
    elif name == "map2_dropped_notification":
        faults = [(6, 12, 1.0, 1001.0, 0.0, True)]
    elif name in ("map2_source_temporary_disconnect", "map2_source_permanent_disconnect"):
        rows = [_bag(1001, 0, 47), _bag(1002, 0, 49)]
        faults = [(0, 6, 0.0, 30.0 if name == "map2_source_temporary_disconnect" else 1001.0, 0.0, False)]
    elif name in ("map2_pending_burst_control", "map2_pending_burst_fault"):
        rows = [_bag(1001+i, i % 6, 47, (i // 6) * .05) for i in range(36)]
        if name == "map2_pending_burst_fault":
            # The fixed control has remote requests to nodes 7/17 pending
            # from .051 to 1.001, plus already committed in-flight grants.
            faults = [(6, 12, .5, 1001.0, 0.0, False)]
    elif name in ("map2_temporary_disconnect", "map2_permanent_disconnect"):
        rows = [_bag(1001, 0, 47), _bag(1002, 0, 49)]
        end = 30.0 if name == "map2_temporary_disconnect" else 1001.0
        faults = [(6, 8, 1.0, end, 0.0, False), (6, 12, 1.0, end, 0.0, False)]
    elif name == "map2_repair_then_new_bag":
        rows = [_bag(1001, 0, 47), _bag(1002, 0, 47, 400.0)]
        faults = [(6, 12, 1.0, 30.0, 0.0, False)]
    elif name == "map2_restored_control":
        rows = [_bag(1002, 0, 47, 400.0)]
    elif name in ("map2_no_fault", "nanning_no_fault"):
        goal = 16 if map_name == "nanning" else 47
        rows = [_bag(1001+i, 0, goal, release) for i, release in enumerate((0.0, .1, 3.0, 8.0))]
    else:
        raise ValueError(f"unregistered fixture {name}")
    return dict(name=name, map=map_name, rows=rows, faults=faults, horizon=horizon)


def prepared_request(case: dict, binary: Path, enabled: bool, *, legacy: bool) -> tuple[dict, dict]:
    profile = activation._profile_for_map(case["map"], activation.DEFAULT_NANNING_PROFILE)
    request, contract = adapter.build_s4_request(profile, case["rows"], binary=binary,
        scenario=SCENARIO, max_events=30_000, max_simulation_time=case["horizon"],
        trace_limit=3000, event_trace_limit=6000, summary_only=False, edge_speed_mps=2.5,
        enable_s4_local_potential_descent_guard=True,
        enable_s4_direct_neighbor_merge_calendar_visibility=True, complete_on_goal_arrival=True)
    request.update(scorer_mode="S4_queue_aware_rule_only", merge_grant_rule="M3",
                   merge_grant_timing_mode="jit_fair_aging_deadline", enable_cie_component_activation=True,
                   fault_windows=case["faults"])
    if not legacy:
        request[FLAG] = enabled
    return request, {"profile_path": str(profile.source_path), "profile_sha256": sha(profile.source_path),
                     "potential_contract": contract, "surviving_potential_precomputed": False,
                     "source_population_prefiltered": False}


def worker(binary: Path, case_name: str, enabled: bool, target: Path, legacy: bool) -> None:
    from czr005 import cpp_backend
    binary = binary.resolve(strict=True)
    if legacy:
        assert sha(binary) == OLD_SHA
    case = case_definition(case_name)
    request, contract = prepared_request(case, binary, enabled, legacy=legacy)
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    loaded = Path(payload.get("loaded_cpp_binary_path") or payload["summary"]["loaded_cpp_binary_path"]).resolve()
    assert loaded == binary and sha(loaded) == sha(binary), "native extension identity changed"
    target.mkdir(parents=True, exist_ok=False)
    write_gzip(target / "request.json.gz", request)
    write_gzip(target / "native.json.gz", payload)
    tools = [Path(__file__), ROOT / "src/czr005/cpp_backend.py", ROOT / "scripts/eval/g4irsf31_map_adapter.py"]
    support = target / "tools"; support.mkdir()
    source_rows = []
    for tool in tools:
        copy = support / tool.name; copy.write_bytes(tool.read_bytes())
        source_rows.append({"source_path": str(tool), "sha256": sha(tool), "archive_path": str(copy)})
    write_json(target / "manifest.json", {"schema": "czr005.g31_fault_repair_native_microcase.v1",
        "case": case, "flag": enabled if not legacy else "ABSENT_OLD_ABI", "legacy_control": legacy,
        "binary_path": str(binary), "binary_sha256": sha(binary), "contract": contract,
        "python_executable": sys.executable, "python_version": sys.version, "source_support": source_rows,
        "request_archive_sha256": sha(target / "request.json.gz"), "native_archive_sha256": sha(target / "native.json.gz"),
        "formal_population_simulations_executed": 0})


def run_case(name: str, *, enabled: bool = True, legacy: bool = False) -> dict:
    binary = OLD_BINARY if legacy else NEW_BINARY
    assert binary.is_file(), f"compile the isolated repair binary first: {binary}"
    if legacy:
        assert sha(binary) == OLD_SHA, "do not replace the frozen b00 binary"
    mode = "legacy" if legacy else "enabled" if enabled else "disabled"
    target = EVIDENCE.resolve() / sha(binary)[:16] / f"{name}_{mode}"
    manifest = target / "manifest.json"
    if not manifest.exists():
        command = [sys.executable, str(Path(__file__).resolve()), "--worker", name,
                   "--binary", str(binary.resolve()), "--target", str(target)]
        if legacy:
            command += ["--legacy"]
        if enabled:
            command += ["--enabled"]
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
        assert done.returncode == 0, done.stdout + done.stderr
    record = json.loads(manifest.read_text(encoding="utf-8"))
    assert record["case"] == encoding._encode(case_definition(name))
    assert record["flag"] == ("ABSENT_OLD_ABI" if legacy else enabled)
    assert record["binary_sha256"] == sha(binary)
    assert record["native_archive_sha256"] == sha(target / "native.json.gz")
    assert record["request_archive_sha256"] == sha(target / "request.json.gz")
    expected_request, _ = prepared_request(case_definition(name), binary, enabled, legacy=legacy)
    assert encoding._encode(read_gzip(target / "request.json.gz")) == encoding._encode(expected_request), "cached native request is not this fixture"
    return read_gzip(target / "native.json.gz")


def assert_population(payload: dict, name: str, completed: int | None = None) -> None:
    case = case_definition(name)
    expected = {row["segment_id"]: row for row in case["rows"]}
    bags = payload["bags"]
    assert len(bags) == len(expected) == len({row["segment_id"] for row in bags})
    assert {row["segment_id"] for row in bags} == set(expected)
    assert len({row["runtime_bag_id"] for row in bags}) == len(bags)
    for bag in bags:
        raw = expected[bag["segment_id"]]
        assert bag["start"] == raw["start"] and bag["goal"] == raw["goal"]
        if bag["completed"]:
            assert bag["final_node"] == raw["goal"] and bag["finish_time"] <= case["horizon"]
    summary = payload["summary"]
    assert summary["requested_count"] == len(bags)
    assert summary["completed_count"] == sum(bool(b["completed"]) for b in bags)
    assert summary["physical_fault_edge_entry_violation_count"] == 0
    assert summary["reservation_conflicts"] == 0
    for field in ("safe_execution_pass", "merge_grant_active_bijection_holds",
                  "merge_grant_active_state_integrity_pass", "merge_grant_conservation_holds",
                  "merge_grant_protocol_integrity_pass"):
        assert summary[field] is True, field
    assert summary["scorer_mode"] == "S4_queue_aware_rule_only" and summary["merge_grant_rule"] == "M3"
    assert summary["s4_local_potential_descent_guard_enabled"] is True
    assert summary["runtime_full_astar_calls"] == summary["runtime_full_cie_astar_calls"] == 0
    assert summary["full_future_routes_stored"] == 0 and summary["reservation_depth"] == 1
    assert not summary["event_limit_reached"]
    if completed is not None:
        assert summary["completed_count"] == completed
    for event in payload["events"]:
        if event["event"] != "EDGE_ENTER":
            continue
        # Event schema exposes from_node/to_node for the traversed directed edge.
        pair = (event["from_node"], event["to_node"])
        now = float(event["time"])
        assert not any(pair == (u, v) and start <= now < end for u, v, start, end, _delay, _drop in case["faults"])


def scientific_rows(value: object) -> object:
    """Exclude only profiling/config flags; retain all choice/time/state fields."""
    if isinstance(value, dict):
        return {key: scientific_rows(item) for key, item in value.items()
                if key not in {FLAG, "s4_advertised_fault_potential_repair_enabled", "loaded_cpp_binary_path", "loaded_cpp_binary_sha256", "inference_time_us",
                               "model_inference_us", "decision_latency_us", "runtime_seconds"}}
    if isinstance(value, list):
        return [scientific_rows(item) for item in value]
    return value


@pytest.mark.parametrize("name", ["map2_mid_fault", "nanning_mid_fault"])
def test_mid_transit_fault_restores_legal_routing(name):
    old = run_case(name, legacy=True)
    new = run_case(name)
    assert_population(old, name)
    assert_population(new, name, completed=1)
    if name == "map2_mid_fault":
        assert not old["bags"][0]["completed"], "the frozen control no longer reproduces the registered counterexample"
    # The failure occurs after upstream entry and before exit; not a predeleted graph.
    fault_time = case_definition(name)["faults"][0][2]
    enters = [e for e in new["events"] if e["event"] == "EDGE_ENTER" and e["time"] < fault_time]
    assert enters
    assert any(e["event"] == "EDGE_EXIT" and e["time"] > fault_time for e in new["events"])
    assert new["summary"]["s4_fault_potential_rebuild_count"] > 0
    assert new["summary"]["s4_fault_potential_active_advertised_edge_count"] == 1


@pytest.mark.parametrize("name", ["map2_simultaneous_faults", "map2_successive_faults"])
def test_multiple_faults_keep_every_advertised_failure_excluded(name):
    value = run_case(name)
    assert_population(value, name, completed=1)
    assert value["summary"]["s4_fault_potential_active_advertised_edge_count"] == 2


def test_delayed_notification_does_not_change_decisions_before_delivery():
    enabled = run_case("map2_delayed_notification")
    disabled = run_case("map2_delayed_notification", enabled=False)
    assert_population(enabled, "map2_delayed_notification", completed=1)
    for field in ("decisions", "hold_attempts"):
        left = [row for row in enabled[field] if row["event_time"] < 11.0]
        right = [row for row in disabled[field] if row["event_time"] < 11.0]
        assert left and scientific_rows(left) == scientific_rows(right), field
    updates = [e for e in enabled["events"] if e.get("reason") == "s4_advertised_topology_potential_rebuild"]
    assert updates and all(event["time"] >= 11 for event in updates)
    assert disabled["summary"].get("s4_fault_potential_rebuild_count", 0) == 0


def test_dropped_notification_cannot_rebuild_from_the_physical_fault_schedule():
    enabled = run_case("map2_dropped_notification")
    disabled = run_case("map2_dropped_notification", enabled=False)
    for result in (enabled, disabled):
        assert_population(result, "map2_dropped_notification", completed=0)
        assert result["summary"].get("s4_fault_potential_rebuild_count", 0) == 0
        assert result["summary"].get("s4_fault_potential_active_advertised_edge_count", 0) == 0
        assert result["summary"]["physical_fault_interlock_rejection_count"] > 0
    for field in ("bags", "decisions", "hold_attempts"):
        assert scientific_rows(enabled[field]) == scientific_rows(disabled[field]), field


def test_temporary_disconnect_parks_then_wakes_without_population_loss():
    value = run_case("map2_temporary_disconnect")
    permanent = run_case("map2_permanent_disconnect")
    assert_population(value, "map2_temporary_disconnect", completed=2)
    assert all(bag["finish_time"] > 30 for bag in value["bags"])
    summary = value["summary"]
    assert summary["s4_fault_unreachable_park_count"] >= 2
    assert summary["s4_fault_unreachable_wakeup_count"] >= 2
    assert summary["s4_fault_unreachable_active_parked_count"] == 0
    assert summary["s4_fault_potential_active_advertised_edge_count"] == 0
    assert summary["s4_fault_potential_restore_original_count"] > 0
    # Only the undisclosed future repair time differs. Before t=30, both
    # executions must have exactly the same physical/scheduling observations.
    def before_repair(payload):
        keys = ("time", "event", "node", "from_node", "to_node", "reason", "task_id")
        return [tuple(event[key] for key in keys) for event in payload["events"] if event["time"] < 30]
    assert before_repair(value) == before_repair(permanent)


def test_remote_notification_revokes_real_pending_requests_but_keeps_inflight_grants():
    control = run_case("map2_pending_burst_control")
    value = run_case("map2_pending_burst_fault")
    assert_population(control, "map2_pending_burst_control", completed=36)
    assert_population(value, "map2_pending_burst_fault", completed=36)
    moment = .5
    for result in (control, value):
        assert result["summary"]["merge_grant_lifecycle_complete"]
    left = [r for r in value["merge_grant_lifecycle"] if r["time"] < moment]
    right = [r for r in control["merge_grant_lifecycle"] if r["time"] < moment]
    assert left == right, "undelivered remote fault affected pre-notification grants"
    latest = {(r["destination_node"], r["request_id"]): r for r in left}
    pending = {key: row for key, row in latest.items() if row["state"] == "REQUESTED"}
    committed = {key: row for key, row in latest.items() if row["state"] == "COMMITTED"}
    assert len(pending) >= 2 and len(committed) >= 2
    assert all((r["edge_from_node"], r["edge_to_node"]) != (6, 12) for r in pending.values())
    following = value["merge_grant_lifecycle"][len(left):]
    for key in pending:
        history = [r for r in following if (r["destination_node"], r["request_id"]) == key]
        assert history and history[0]["time"] == moment
        assert history[0]["state"] == "REVOKED_FAULT"
        assert history[0]["reason"] == "fault_generation_changed"
    for key, granted in committed.items():
        history = [r for r in following if (r["destination_node"], r["request_id"]) == key]
        assert history and all(r["state"] == "CONSUMED" for r in history)
        assert history[0]["grant_id"] == granted["grant_id"]
        assert history[0]["time"] > moment


def test_permanent_disconnect_retains_every_goal_at_fixed_horizon():
    value = run_case("map2_permanent_disconnect")
    assert_population(value, "map2_permanent_disconnect", completed=0)
    assert {bag["goal"] for bag in value["bags"]} == {47, 49}
    assert value["summary"]["time_limit_reached"]
    # An unreachable topology should park, not spin thousands of HOLD retries.
    assert len(value["hold_attempts"]) < 30
    assert value["summary"]["s4_fault_unreachable_park_count"] >= 2
    assert value["summary"]["s4_fault_unreachable_wakeup_count"] == 0


@pytest.mark.parametrize("name", ["map2_source_temporary_disconnect", "map2_source_permanent_disconnect"])
def test_unreachable_source_does_not_spin_and_can_resume_after_repair(name):
    value = run_case(name)
    temporary = "temporary" in name
    assert_population(value, name, completed=2 if temporary else 0)
    assert value["summary"]["source_admission_enabled"] is False
    assert value["summary"]["source_admission_attempt_count"] < 30
    assert value["summary"]["s4_fault_unreachable_park_count"] == 2
    assert value["summary"]["s4_fault_unreachable_wakeup_count"] == (2 if temporary else 0)
    assert value["summary"]["s4_fault_unreachable_active_parked_count"] == (0 if temporary else 2)
    assert len(value["hold_attempts"]) < 30
    if temporary:
        assert all(bag["finish_time"] > 30 for bag in value["bags"])
    else:
        assert all(bag["final_node"] == 0 for bag in value["bags"])


def test_repair_restores_original_potential_for_later_bag():
    repaired = run_case("map2_repair_then_new_bag")
    control = run_case("map2_restored_control")
    assert_population(repaired, "map2_repair_then_new_bag", completed=2)
    assert_population(control, "map2_restored_control", completed=1)
    assert repaired["summary"]["s4_fault_potential_restore_original_count"] > 0
    assert repaired["summary"]["s4_fault_potential_active_advertised_edge_count"] == 0
    for field in ("decisions", "hold_attempts"):
        left = [row for row in repaired[field] if row["event_time"] >= 400]
        right = [row for row in control[field] if row["event_time"] >= 400]
        # Task-local runtime IDs differ with the extra first bag; compare the
        # goal-specific scores, candidate features and selected next edge.
        def selected(rows):
            result = []
            for row in rows:
                candidates = deepcopy(row["candidate_records"])
                for candidate in candidates:
                    # An actual past repair legitimately leaves a message-age
                    # observation. It does not alter H, route scores or motion.
                    candidate["features"].pop("fault_message_age_seconds", None)
                result.append((row["event_time"], row["current_node"], row["selected_next"], candidates))
            return result
        assert scientific_rows(selected(left)) == scientific_rows(selected(right)), field


@pytest.mark.parametrize("name", ["map2_no_fault", "nanning_no_fault"])
def test_no_fault_enabled_disabled_and_b00_have_identical_bags_and_decisions(name):
    enabled, disabled, old = run_case(name), run_case(name, enabled=False), run_case(name, legacy=True)
    for result in (enabled, disabled, old):
        assert_population(result, name, completed=4)
    for result in (enabled, disabled):
        assert result["summary"].get("s4_fault_potential_rebuild_count", 0) == 0
        assert result["summary"].get("s4_fault_potential_restore_original_count", 0) == 0
        assert result["summary"].get("s4_fault_unreachable_park_count", 0) == 0
    for field in ("bags", "decisions", "hold_attempts"):
        assert scientific_rows(enabled[field]) == scientific_rows(disabled[field]), field
        assert scientific_rows(disabled[field]) == scientific_rows(old[field]), field


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument("--capture-control", action="store_true")
    parser.add_argument("--audit", action="store_true", help="run all assertions and save a hash-bound microtests.json")
    args = parser.parse_args()
    if args.worker:
        worker(args.binary, args.worker, args.enabled, args.target, args.legacy)
    elif args.capture_control:
        result = {}
        for name in ("map2_mid_fault", "nanning_mid_fault", "map2_no_fault", "nanning_no_fault"):
            payload = run_case(name, legacy=True)
            result[name] = {"completed": payload["summary"]["completed_count"], "requested": payload["summary"]["requested_count"]}
        print(json.dumps(result))
    elif args.audit:
        binary = NEW_BINARY.resolve(strict=True)
        target = EVIDENCE.resolve() / sha(binary)[:16]
        target.mkdir(parents=True, exist_ok=True)
        xml_path = target / "pytest_results.xml"
        command = [sys.executable, "-m", "pytest", str(Path(__file__).resolve()), "-q", f"--junitxml={xml_path}"]
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        log = target / "pytest_output.txt"
        log.write_text(done.stdout + done.stderr, encoding="utf-8", newline="\n")
        cases = ET.parse(xml_path).getroot().findall(".//testcase") if xml_path.exists() else []
        failures = [item for item in cases if item.find("failure") is not None or item.find("error") is not None]
        skipped = [item for item in cases if item.find("skipped") is not None]
        passed = done.returncode == 0 and len(cases) >= 14 and not failures and not skipped
        source_copy = target / "assertion_driver.py"
        source_copy.write_bytes(Path(__file__).read_bytes())
        native_records = []
        for folder in (target, EVIDENCE.resolve() / OLD_SHA[:16]):
            for manifest in sorted(folder.glob("*/manifest.json")):
                record = json.loads(manifest.read_text(encoding="utf-8"))
                native = read_gzip(manifest.parent / "native.json.gz")
                native_records.append({"path": str(manifest), "sha256": sha(manifest),
                    "case": record["case"]["name"], "flag": record["flag"],
                    "binary_sha256": record["binary_sha256"],
                    "native_archive_sha256": record["native_archive_sha256"],
                    "requested": native["summary"]["requested_count"],
                    "completed": native["summary"]["completed_count"]})
        report = {"schema": "czr005.g31_fault_potential_repair_microtests.v1", "status": "PASS" if passed else "FAIL",
            "binary_path": str(binary), "binary_sha256": sha(binary), "control_binary_sha256": OLD_SHA,
            "assertion_driver_path": str(source_copy), "assertion_driver_sha256": sha(source_copy),
            "command": command, "test_count": len(cases), "failed_count": len(failures), "skipped_count": len(skipped),
            "test_names": [item.attrib["name"] for item in cases], "pytest_exit_code": done.returncode,
            "pytest_xml_path": str(xml_path), "pytest_xml_sha256": sha(xml_path) if xml_path.exists() else None,
            "pytest_output_path": str(log), "pytest_output_sha256": sha(log), "native_records": native_records,
            "formal_population_simulations_executed": 0,
            "scope_notes": ["Each native request uses source_admission=false and finite_junction_queue=false.",
                "Only delivered topology notifications may rebuild H; dropped/undelivered notifications remain invisible.",
                "Restore comparison excludes only the legitimate historical fault_message_age candidate feature; no-fault flag on/off/b00 compares all decision features.",
                "Python API constructs a new runtime per call; same-object reset requires the separate native C++ test.",
                "Cached native cases retain their generating tools; final assertion-driver SHA identifies the assertions applied to those exact native bytes."]}
        write_json(target / "microtests.json", report)
        print(done.stdout + done.stderr)
        print(json.dumps({"status": report["status"], "test_count": len(cases), "report": str(target / "microtests.json")}))
        if not passed:
            raise SystemExit(1)
    else:
        raise SystemExit("use pytest for assertions or --capture-control to preserve the frozen control")


if __name__ == "__main__":
    main()
