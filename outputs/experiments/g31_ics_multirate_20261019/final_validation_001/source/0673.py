"""Complete saved spool candidate verification, with zero API omissions.
Original request replay/clock/drain/physical/background guards remain intact.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import gzip
import inspect
from itertools import zip_longest
import json
from pathlib import Path
import textwrap
from types import FunctionType

from . import probe_original_route_update_spool as p
from . import verify_original_route_update_pending_ack as pending
from .spooled_service_tape import MAX_BYTES, MAX_ROWS, sha
from . import verify_original_route_update_internal_deadline as original
from . import route_pending_ack_evidence as evidence
from .replay_route_pending_ack import semantic_intent, client_calls

require, ordered = original.require, original.ordered


def api_semantics(row):
    result = {key: deepcopy(row[key]) for key in ("endpoint", "role", "args", "kwargs", "before", "after", "result")}
    if row["endpoint"] in {"advance_to", "advance_until_owner_notification"} and "wall_seconds" in result["result"]:
        original.strip_nonnegative_clock(result["result"], "wall_seconds")
    if row["endpoint"] == "result_at":
        original.strip_nonnegative_clock(result["result"]["advance"], "wall_seconds")
    return result


def compare_api_stream(path, current):
    for index, row in enumerate(current):
        require(type(row["ordinal"]) is int and row["ordinal"] == index, "spool_candidate_api_order")
    result = pending.compare_api_stream(path, current, [])
    require(result["omitted_full_view_ordinals_in_reference"] == [], "spool_no_api_omissions")
    return result


def returned_semantics(value):
    if value is None: return None
    result = json.loads(value)
    original.strip_nonnegative_clock(result["drain"], "wall_seconds")
    output = json.loads(result["output"])
    result["output"] = output
    return result


def verify_reference(plan, name, raw, rows):
    folder = Path(plan["spool_reference"]) / name
    previous = p.old.gzread(folder / "raw.json.gz")
    require(raw["physical_time"] == previous["physical_time"] == p.HORIZON and
        raw["control_status"] == previous["control_status"] == "reached", "pending_common_horizon_not_observed")
    require(raw["native_state_sha256"] == previous["native_state_sha256"], "pending_common_horizon_seal_changed")
    root, before = raw["root"], previous["root"]
    for key in ("owner", "root", "job", "client_state", "steps", "eligibility_schedule", "pending_ack_path"):
        require(ordered(root[key]) == ordered(before[key]), "pending_protocol_or_schedule_changed:" + key)
    require(ordered(root["intent"]) == ordered(before["intent"]), "pending_immutable_intent_changed")
    require(ordered(client_calls(root["client_calls"])) == ordered(client_calls(before["client_calls"])), "pending_request_or_retry_changed")
    require(ordered(returned_semantics(root["returned"])) == ordered(returned_semantics(before["returned"])), "pending_return_or_drain_changed")
    require((root["returned_ns"] is None) == (before["returned_ns"] is None) and
        (root["censored_ns"] is None) == (before["censored_ns"] is None), "pending_closure_changed")
    require(ordered(raw["events"]) == ordered(previous["events"]), "spool_step_api_boundaries_changed")
    comparison = compare_api_stream(folder / "service_tape.jsonl.gz", rows)
    current_folder = Path(plan["candidate_output"]) / name
    candidate_shards = p.old.read(current_folder / "shards.json")
    reference_shards = p.old.read(folder / "shards.json")
    require(len(candidate_shards) == len(reference_shards), "pending_controller_part_denominator")
    for actual, prior in zip(candidate_shards, reference_shards, strict=True):
        require({k: v for k, v in actual.items() if k != "sha256"} ==
            {k: v for k, v in prior.items() if k != "sha256"}, "pending_controller_boundary_changed")
        a = p.old.gzread(current_folder / actual["path"]); b = p.old.gzread(folder / prior["path"])
        require(ordered(original.prefix_semantics(a)) == ordered(original.prefix_semantics(b)), "pending_background_controller_changed")
    return {"status": "exact_all_actual_api_rows_and_common9900_seal",
        **comparison, "controller_parts": len(candidate_shards), "native_state_sha256": raw["native_state_sha256"],
        "changed_observation_diagnostics": [],
        "clock_exclusions": ["outer ordinal (separately contiguous)", "outer start_ns/end_ns", "finite nonnegative advance wall_seconds", "controller fixed prefix_semantics clock list"],
        "independent_native_seal_reconstruction": False}


def case_function():
    namespace = {**vars(original), "p": p}
    # Rebind only the verifier's private functions; do not mutate old globals.
    for name, value in vars(original).items():
        if inspect.isfunction(value) and value.__module__ == original.__name__:
            namespace[name] = FunctionType(value.__code__, namespace, name=value.__name__,
                argdefs=value.__defaults__, closure=value.__closure__)
    namespace.update(verify_scheduled_reference=verify_reference, evidence=evidence)
    tree = ast.parse(textwrap.dedent(inspect.getsource(original.verify_case)))
    command_count = assessor_count = label_count = 0
    class Adapt(ast.NodeTransformer):
        def visit_Constant(self, node):
            nonlocal command_count, label_count
            if node.value == ".probe_original_route_update_internal_deadline":
                command_count += 1; return ast.copy_location(ast.Constant(".probe_original_route_update_spool"), node)
            if node.value == "split_deadline_actual_reference":
                label_count += 1; return ast.copy_location(ast.Constant("spool_actual_reference"), node)
            return node
        def visit_Call(self, node):
            nonlocal assessor_count
            if ast.unparse(node.func) == "p.old.assess":
                require(ast.unparse(node) == "p.old.assess(root['intent'], root['client_calls'])", "pending_original_assessor_call_changed")
                assessor_count += 1
                return ast.copy_location(ast.parse('evidence.assess(root, rows, raw["events"])', mode="eval").body, node)
            return self.generic_visit(node)
    tree = Adapt().visit(tree)
    require((command_count, assessor_count, label_count) == (1, 1, 1), "pending_verifier_adaptation_domain")
    ast.fix_missing_locations(tree)
    exec(compile(tree, "<pending-ack-original-case-verifier>", "exec"), namespace)
    return namespace["verify_case"]


def verify_capture(output, name):
    directory = output / name
    path = directory / "diagnostic_capture.json"
    report = p.old.read(path)
    raw = p.old.gzread(directory / "raw.json.gz")
    parent = p.old.read(output / "receipt.json")["cases"][name]
    gzip_path = directory / "service_tape.jsonl.gz"
    spool_path = directory / "service_tape.jsonl.gz.spool.jsonl"
    require(report["schema"] == "g31.spool_only_service_capture.v2" and report["mode"] == "spool" and
        report["max_bytes"] == MAX_BYTES and type(report["max_bytes"]) is int and
        report["max_rows"] == MAX_ROWS and type(report["max_rows"]) is int, "spool_capture_scope")
    require(report["failure"] is None and report["close_error"] is None and
        report["original_inflight_error"] is None and report["closed"] is True and
        report["export_attempted"] is True and report["evidence_complete"] is True, "spool_incomplete_capture")
    require(all(type(report[key]) is int for key in ("rows", "flushed_rows", "api_count", "write_attempts", "encoded_bytes")) and
        0 < report["rows"] == report["flushed_rows"] == report["api_count"] == report["write_attempts"] == raw["api_rows"] <= MAX_ROWS and
        0 < report["encoded_bytes"] <= MAX_BYTES, "spool_denominator")
    require(report["gzip_path"] == str(gzip_path) and report["spool_path"] == str(spool_path), "spool_capture_paths")
    require(report["hardkill_prefix_durability"] == "flushed_uncompressed_spool_no_fsync_or_powerloss_guarantee", "spool_durability_scope")
    expected = {value.name: sha(value) for value in (gzip_path, spool_path)}
    require(report["artifact_sha256"] == expected and
        parent["artifact_sha256"][path.name] == sha(path) and
        all(parent["artifact_sha256"][key] == value for key, value in expected.items()), "spool_artifact_pins")
    require(raw["api_sha256"] == expected[gzip_path.name] and
        report["accepted_encoded_sha256"] == expected[spool_path.name], "spool_accepted_prefix_hash")
    count = size = 0
    with gzip.open(gzip_path, "rb") as compressed, spool_path.open("rb") as spool:
        missing = object()
        for left, right in zip_longest(compressed, spool, fillvalue=missing):
            require(left is not missing and right is not missing and left == right and left.endswith(b"\n"), "spool_lossless_bytes")
            # Decode every line strictly. Original verifier validates JSON/API.
            left.decode("utf8", errors="strict")
            count += 1; size += len(left)
    require(count == report["rows"] and size == report["encoded_bytes"], "spool_byte_denominator")
    clocks = [report[key] for key in ("close_started_ns", "close_export_finished_ns", "close_hashes_finished_ns")]
    root = raw["root"]; end = root["returned_ns"] if root["returned_ns"] is not None else root["censored_ns"]
    require(all(type(value) is int for value in clocks) and end <= clocks[0] <= clocks[1] <= clocks[2] <=
        raw["result_capture_before_seal_ns"] <= parent["parent_child_end_ns"], "spool_close_outside_measured_child")
    return {"status": "complete_lossless_spool_and_gzip", "rows": count, "encoded_bytes": size,
        "close_export_ms": (clocks[1]-clocks[0])/1e6, "close_hash_ms": (clocks[2]-clocks[1])/1e6,
        "artifact_sha256": {**expected, path.name: sha(path)},
        "cost_scope": "API JSON/UTF8/write/flush stays inside hot return; close/export/hash stays inside child and full campaign. No historical subtraction.",
        "hardkill_prefix": "flushed spool; no fsync/powerloss guarantee; partial rejected row is unknown"}


def verify(output):
    campaign = p.verify_campaign(output)
    plan = p.old.read(output / "preregistered_protocol.json")
    # This path is evidence location, not policy state; preparation pins it.
    require(plan["candidate_output"] == str(output.resolve()), "pending_output_identity")
    report = {"schema": p.SCHEMA, "status": "passed_saved_spool_candidate", "declared_roots": 3,
        "campaign_sha256": p.old.sha(output / "campaign.json"), "cases": {}, "complete_100ms_certified": False,
        "native_executions_in_verifier": 0, "source_sha256": {str(Path(__file__).resolve()): p.old.sha(__file__)}}
    function = case_function()
    for name in p.CASES:
        report["cases"][name] = function(output, plan, name)
        report["cases"][name]["diagnostic_capture"] = verify_capture(output, name)
    report["closed_roots"] = sum(value["status"] == "closed_finite_request" for value in report["cases"].values())
    report["open_roots"] = 3 - report["closed_roots"]
    p.verify_campaign(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args(); report = verify(args.output.resolve())
    if args.write_report:
        path = args.output / "independent_verification.json"
        require(not path.exists(), "pending_report_exists"); p.old.write(path, report)
    print(json.dumps({"status": report["status"], "closed": report["closed_roots"], "open": report["open_roots"]}))


if __name__ == "__main__": main()
