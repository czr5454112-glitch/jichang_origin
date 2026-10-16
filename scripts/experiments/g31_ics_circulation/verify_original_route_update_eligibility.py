"""Saved-file verifier for the finite caller-admitted original route probe.

Replays every request-side API decision from raw native replies, not native
state. All controller shards and warm native API records remain hash-bound.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import gzip
import json
import math
from pathlib import Path

from . import probe_original_route_update_eligibility as p


def require(ok, why):
    if not ok: raise ValueError("original_route_verify:" + why)


def ordered(value): return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def strip_nonnegative_clock(row, key):
    value = row.pop(key)
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "invalid_prefix_diagnostic")


def prefix_semantics(part):
    """Only the fixed wall/CPU measurements are excluded; all policy data stay."""
    value = deepcopy(part)
    strip_nonnegative_clock(value, "wall_seconds")
    for row in value["control_records"]:
        for key in ("compute_wall_ms", "compute_cpu_ms"): strip_nonnegative_clock(row, key)
    for row in value["native_batches"]:
        for key in ("wall_ms", "cpu_ms"): strip_nonnegative_clock(row, key)
    for row in value["client_calls"]: strip_nonnegative_clock(row, "submit_compute_ms")
    if value["result"] is not None:
        strip_nonnegative_clock(value["result"]["advance"], "wall_seconds")
    return value


def verify_original_prefix(plan, name, parts):
    folder = Path(plan["baseline_reference"]) / name
    require(p.old.sha(folder / "shards.json") == plan["baseline_prefix_pins"][str(folder / "shards.json")], "baseline_manifest_changed")
    refs = [row for row in p.old.read(folder / "shards.json") if row["target"] == p.ADMISSION]
    require(len(refs) == len(parts), "pre_admission_prefix_denominator")
    for actual, ref in zip(parts, refs, strict=True):
        path = folder / ref["path"]
        require(p.old.sha(path) == ref["sha256"] == plan["baseline_prefix_pins"][str(path)], "baseline_prefix_changed")
        require(ordered(prefix_semantics(actual)) == ordered(prefix_semantics(p.old.gzread(path))), "pre_admission_prefix_semantics_changed")
    return {"parts": len(parts), "status": "ordered_exact_except_listed_clock_fields",
        "excluded": ["wall_seconds", "control_records[].compute_wall_ms", "control_records[].compute_cpu_ms",
            "native_batches[].wall_ms", "native_batches[].cpu_ms", "client_calls[].submit_compute_ms", "result.advance.wall_seconds"]}


def validate_warm_target(item, part, root, state):
    schedule = root["eligibility_schedule"]
    due = min(p.HORIZON, schedule["deadline"]) if schedule is not None else p.HORIZON
    expected = p.HORIZON if state["done"] else due
    require(item["target"] == expected and part["control_continuation"]["requested_horizon"] == expected, "unexpected_real_controller_horizon")
    require(all(row["start_at"] <= row["end_at"] <= row["requested_public_deadline"] <= expected
        for row in part["native_batches"]), "native_boundary_outside_actual_target")
    if part["status"] == "reached":
        require(item["physical_time"] == expected and part["controller_state"]["native_timestamp_complete"] is True,
            "eligibility_boundary_incomplete")
        state["done"] = True
    elif part["status"] != "control_budget_exhausted":
        require(part["status"] == "native_budget_exhausted", "unknown_controller_boundary_status")


def projected_root(root):
    result = deepcopy(root)
    for row in result["client_calls"]:
        value = row["submit_compute_ms"]
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "invalid_submit_diagnostic")
        del row["submit_compute_ms"]
    return result


def validate_tape(rows):
    previous_end = None; previous_at = p.ADMISSION
    for index, row in enumerate(rows):
        require(row["ordinal"] == index and row["endpoint"] in p.ENDPOINTS and row["role"] in {"controller", "request"}, "api_domain_or_order")
        require("error" not in row and "result" in row, "native_exception_or_missing_response")
        require(type(row["start_ns"]) is int and type(row["end_ns"]) is int and
            0 <= row["start_ns"] <= row["end_ns"] and (previous_end is None or previous_end <= row["start_ns"]), "api_wall_clock")
        require(all(type(row[k]) in (int, float) and math.isfinite(row[k]) for k in ("before", "after")) and
            previous_at == row["before"] <= row["after"] <= p.HORIZON, "api_physical_clock")
        previous_end, previous_at = row["end_ns"], row["after"]
    require(rows, "empty_api_tape")


class Replay:
    def __init__(self, rows): self.rows, self.index, self.now = rows, 0, p.ADMISSION
    @property
    def physical_time(self): return self.now
    def __getattr__(self, endpoint):
        require(endpoint in p.ENDPOINTS, "unclassified_replay_endpoint")
        def invoke(*args, **kwargs):
            require(self.index < len(self.rows), "missing_request_api")
            row = self.rows[self.index]
            require(row["endpoint"] == endpoint and ordered(row["args"]) == ordered(list(args)) and
                ordered(row["kwargs"]) == ordered(kwargs) and row["before"] == self.now, "request_api_difference")
            self.index += 1; self.now = row["after"]
            return deepcopy(row["result"])
        return invoke


def replay_request(raw, rows):
    root = raw["root"]
    require(root["job"] == p.JOB and root["root"] == p.ROOT_ID and raw["events"], "root_identity_or_events")
    clocks = root["clock_trace"]
    require(clocks and all(type(v) is int and v >= 0 for v in clocks) and clocks == sorted(clocks), "root_clock_sequence")
    require(raw["worker_started_ns"] <= clocks[0] <= clocks[-1] <= raw["result_capture_before_seal_ns"], "root_outside_capture")
    position = [0]
    def clock():
        require(position[0] < len(clocks), "missing_root_clock")
        result = clocks[position[0]]; position[0] += 1; return result
    selected = [r for r in rows if r["role"] == "request"]
    replay = Replay(selected); update = p.RouteUpdate(replay, root["owner"], clock=clock)
    intervals = []
    for i, event in enumerate(raw["events"]):
        start, end = event["first_api"], event["after_api"]
        require(type(start) is int and type(end) is int and 0 <= start < end <= len(rows), "event_api_interval")
        require(not intervals or intervals[-1][1] <= start, "overlapping_event_intervals")
        require(all(row["role"] == "request" for row in rows[start:end]), "event_includes_foreign_api")
        if i == 0:
            require(event["initial"] is True and start == 0 and event["at"] == p.ADMISSION, "admission_not_before_fresh_view")
        else:
            require(event["initial"] is False and start > 0, "second_admission")
            trigger = rows[start-1]
            require(trigger["role"] == "controller" and trigger["endpoint"] == "advance_until_owner_notification"
                and trigger["after"] == event["at"] and trigger["result"].get("timestamp_complete") is True,
                "step_without_complete_native_trigger")
            require(event["at"] >= update.next_probe or update.intent.decision is not None and
                update.owner in trigger["result"].get("notifications", {}), "unregistered_poll_trigger")
        replay.now = event["at"]
        before = replay.index
        update.start() if i == 0 else update.step()
        require(replay.index-before == end-start and selected[before:replay.index] == rows[start:end], "request_api_coverage")
        intervals.append((start, end))
    require(sum(end-start for start, end in intervals) == len(selected) == replay.index, "unattributed_request_api")
    if root["censored_ns"] is not None:
        require(not update.closed, "censor_after_success")
        update.censor()
    require(position[0] == len(clocks), "extra_root_clock")
    require(ordered(projected_root(update.snapshot())) == ordered(projected_root(root)), "root_replay_difference")
    lineage = root["lineage"][p.ROOT_ID]
    first_view = selected[0]
    require(first_view["endpoint"] == "observe_protocol" and root["started_ns"] <= lineage["accepted"]["wall_ns"]
        <= lineage["observation"]["wall_ns"] <= first_view["start_ns"] <= first_view["end_ns"]
        <= root["report"]["observation"]["returned_wall_ns"], "admission_observation_wall_binding")
    end = root["returned_ns"] if root["returned_ns"] is not None else root["censored_ns"]
    require(end is not None and all(root["started_ns"] <= row["start_ns"] <= row["end_ns"] <= end for row in selected),
        "request_api_outside_root")
    return update


def verify_case(output, plan, name):
    directory = output / name; raw = p.old.gzread(directory / "raw.json.gz")
    require(raw["schema"] == p.SCHEMA and raw["case"] == name and raw["source_changed"] == [] and
        raw["native_binary_sha256"] == p.old.BINARY_SHA and raw["input_sha256"] == plan["case_inputs"][name], "raw_identity")
    parent = p.old.read(output / "receipt.json")
    process = parent["cases"][name]
    expected_command = [plan["interpreter"]["path"], "-m", p.__package__ + ".probe_original_route_update_eligibility",
        "--output", str(output.resolve()), "--worker", name]
    require(process["status"] == "child_finished" and process["exit_code"] == 0 and process["command"] == expected_command
        and all(type(process[k]) is int for k in ("parent_child_start_ns", "parent_child_end_ns"))
        and process["parent_child_start_ns"] <= raw["worker_started_ns"] <= raw["result_capture_before_seal_ns"] <= process["parent_child_end_ns"]
        and process["whole_child_wall_seconds"] == (process["parent_child_end_ns"]-process["parent_child_start_ns"])/1e9,
        "actual_child_process_window")
    shared_setup = parent["shared_parent_setup_ns"]
    require(type(shared_setup) is int and shared_setup >= 0 and shared_setup ==
        parent["cases"][next(iter(p.CASES))]["parent_child_start_ns"]-parent["parent_measured_start_ns"], "shared_parent_setup_window")
    require(p.old.sha(directory / "service_tape.jsonl.gz") == raw["api_sha256"] and
        p.old.sha(directory / "shards.json") == raw["shards_sha256"], "raw_manifest_hash")
    with gzip.open(directory / "service_tape.jsonl.gz", "rt", encoding="utf8") as f:
        rows = [json.loads(line) for line in f]
    require(len(rows) == raw["api_rows"], "api_denominator")
    validate_tape(rows)
    offset = acts = 0; prefix_complete = False; last = None
    target_state = {"done": False}; previous_controller = None; prefix_parts = []
    shards = p.old.read(directory / "shards.json")
    require(len(list((directory / "segments").glob("*.json.gz"))) == len(shards), "shard_omission")
    for index, item in enumerate(shards):
        require(Path(item["path"]).as_posix() == f"segments/{index:04d}.json.gz", "shard_path_order")
        path = directory / item["path"]; require(p.old.sha(path) == item["sha256"], "shard_hash")
        part = p.old.gzread(path)
        seq = sorted(r["trace_sequence"] for key in ("control_records", "native_batches") for r in part[key])
        require(seq == list(range(offset, offset+len(seq))), "controller_trace_gap")
        offset += len(seq); acts += len(part["control_records"])
        require(part["status"] == item["status"] and part["control_continuation"]["physical_time"] == item["physical_time"], "shard_summary")
        if item["target"] == p.ADMISSION:
            require(not prefix_complete, "prefix_revisited")
            if part["status"] == "reached":
                require(item["physical_time"] == p.ADMISSION and part["controller_state"]["native_timestamp_complete"] is True, "prefix_not_drained")
                prefix_complete = True
            prefix_parts.append(part)
        else:
            require(prefix_complete, "warm_before_prefix")
            validate_warm_target(item, part, raw["root"], target_state)
        state = part["controller_state"]
        require(state["start"] == 0. and state["config"]["control_period"] == 60., "background_phase_reset")
        if previous_controller is not None:
            require(state["config"] == previous_controller["config"] and state["next_tick"] >= previous_controller["next_tick"], "background_configuration_or_tick_changed")
        previous_controller = state
        last = part
    require(prefix_complete and last is not None and acts == raw["owner_activations"] <= p.old.MAX_ACTIVATIONS,
        "prefix_or_activation_denominator")
    require(last["control_continuation"]["physical_time"] == raw["physical_time"] == rows[-1]["after"], "final_physical_time")
    require(type(raw["native_state_sha256"]) is str and len(raw["native_state_sha256"]) == 64 and
        all(c in "0123456789abcdef" for c in raw["native_state_sha256"]), "invalid_producer_seal")
    prefix_comparison = verify_original_prefix(plan, name, prefix_parts)
    update = replay_request(raw, rows); root = raw["root"]
    require(update.owner == plan["source_owner"], "root_owner_changed")
    for row in rows:
        if row["role"] != "request": continue
        if row["endpoint"] in {"observe_protocol", "protocol_command"}:
            require(row["args"][0] == update.owner, "foreign_request_view")
    if update.closed:
        require(root["report"]["status"] == "complete_declared_lineage" and root["report"]["job_scope_verified"] is True,
            "returned_without_full_lineage")
        p.old.assess(root["intent"], root["client_calls"])
    else:
        require(root["report"]["status"] == "unknown_incomplete_lineage" and root["censored_ns"] is not None, "open_root_removed")
    ended = root["returned_ns"] if update.closed else root["censored_ns"]
    warm = ended - root["started_ns"]
    setup = root["started_ns"] - raw["worker_started_ns"]
    child_cold = ended-process["parent_child_start_ns"]
    native_calls = [r for r in rows if root["started_ns"] <= r["start_ns"] and r["end_ns"] <= ended]
    return {"status": "closed_finite_request" if update.closed else "open_censored_request", "job": p.JOB,
        "disposition": root["lineage"][p.ROOT_ID]["decision_seal"], "intent_status": update.intent.status,
        "warm_elapsed_upper_ms" if update.closed else "warm_elapsed_prefix_ms": warm/1e6,
        "worker_setup_prefix_ms": setup/1e6,
        "child_cold_elapsed_upper_ms" if update.closed else "child_cold_elapsed_prefix_ms": child_cold/1e6,
        "shared_measured_parent_setup_charged_fully_ms": shared_setup/1e6,
        "child_plus_measured_parent_setup_ms": (child_cold+shared_setup)/1e6,
        "full_cold_upper_ms": None, "parent_startup_import_cost": "unmeasured; require externally pinned launch-to-exit bound for full campaign charge",
        "native_call_envelopes_within_root_ms": sum(r["end_ns"]-r["start_ns"] for r in native_calls)/1e6,
        "native_call_count_within_root": len(native_calls), "request_api_rows": sum(r["role"] == "request" for r in rows),
        "all_warm_native_api_rows": len(rows), "controller_trace_rows": offset, "owner_activations": acts,
        "exact_pre_admission_original_prefix": prefix_comparison,
        "eligibility_schedule": root["eligibility_schedule"],
        "root_request_ids": list(root["client_state"]["outbox"]), "attempts": len(root["client_calls"]),
        "raw_sha256": p.old.sha(directory / "raw.json.gz"), "producer_native_seal": raw["native_state_sha256"],
        "whole_child_wall_seconds": process["whole_child_wall_seconds"],
        "post_capture_seal_export_and_process_tail_upper_ms": (process["parent_child_end_ns"]-raw["result_capture_before_seal_ns"])/1e6,
        "scope": "Exact saved REQUEST-SIDE API replay. Background controller/native transcript is retained, hash/order/clock/denominator checked, but controller policy is not recomputed. No new native seal reconstruction, exclusive phase subtraction or long-term maintenance proof.",
        "complete_100ms_certified": False}


def verify(output):
    plan = p.old.read(output / "preregistered_protocol.json"); p.verify_pins(output, plan)
    report = {"schema": p.SCHEMA, "status": "passed_saved_finite_request_verification", "case_count": 3,
        "declared_roots": 3, "cases": {}, "complete_100ms_certified": False,
        "source_sha256": {str(Path(__file__).resolve()): p.old.sha(__file__), str(Path(p.__file__).resolve()): p.old.sha(p.__file__)}}
    for name in p.CASES: report["cases"][name] = verify_case(output, plan, name)
    report["closed_roots"] = sum(c["status"] == "closed_finite_request" for c in report["cases"].values())
    report["open_roots"] = 3-report["closed_roots"]
    p.verify_pins(output, plan)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args(); report = verify(args.output.resolve())
    if args.write_report:
        path = args.output / "independent_verification.json"
        require(not path.exists(), "report_already_exists"); p.old.write(path, report)
    print(json.dumps(report))


if __name__ == "__main__": main()
