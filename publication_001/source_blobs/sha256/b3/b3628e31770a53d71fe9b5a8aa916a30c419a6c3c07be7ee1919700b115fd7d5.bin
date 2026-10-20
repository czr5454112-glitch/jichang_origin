"""Saved candidate replay and exact comparison, allowing only declared reads.

Each candidate request policy is replayed against its actual saved responses.
The old case verifier keeps every guard, except for a query-bound ACK clock and
the explicit candidate command/schema/reference comparison adaptations.
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

from . import probe_original_route_update_pending_ack as p
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


def omitted_reference_indices(raw, current, previous_raw):
    root = raw["root"]; proof = root["pending_ack_path"]["sticky_observed_hop"]
    require(len(raw["events"]) == len(previous_raw["events"]) == len(root["steps"]), "pending_event_denominator")
    omitted = []; views = 0; proof_step = None; ack_only = 0
    for index, (event, prior) in enumerate(zip(raw["events"], previous_raw["events"], strict=True)):
        require(event["at"] == prior["at"] and event["initial"] is prior["initial"], "pending_step_schedule_changed")
        rows = current[event["first_api"]:event["after_api"]]
        count = sum(row["endpoint"] == "observe_protocol" for row in rows)
        require(count in (0, 1), "pending_full_view_denominator")
        if count:
            views += 1
            if proof is not None and views == proof["actual_view_count"]:
                require(proof_step is None and event["at"] == proof["observed_at"], "pending_proof_step")
                proof_step = index
        else:
            require(proof is not None and proof_step is not None and index > proof_step and
                event["initial"] is False and event["at"] >= proof["observed_at"], "pending_omission_before_actual_proof")
            omitted.append((prior["first_api"], prior["after_api"]))
            ack_only += 1
    require(views == root["pending_ack_path"]["full_view_reads"] and
        ack_only == root["pending_ack_path"]["ack_only_steps"], "pending_diagnostic_read_denominator")
    if proof is not None:
        require(proof_step is not None and proof["source"] == "same_instance_unchanged_public_observe_path", "pending_proof_origin")
    return omitted


def compare_api_stream(path, current, omitted_intervals):
    omitted_counts = [0] * len(omitted_intervals)
    skipped = []
    def reference_rows():
        with gzip.open(path, "rt", encoding="utf8") as stream:
            for index, line in enumerate(stream):
                row = json.loads(line)
                require(row["ordinal"] == index, "pending_reference_api_order")
                interval = next((i for i, (start, end) in enumerate(omitted_intervals) if start <= index < end), None)
                if interval is not None and row["endpoint"] == "observe_protocol":
                    require(row["role"] == "request", "pending_omitted_controller_read")
                    omitted_counts[interval] += 1; skipped.append(index)
                    continue
                yield row
    count = 0; missing = object()
    for actual, reference in zip_longest(current, reference_rows(), fillvalue=missing):
        require(actual is not missing and reference is not missing, "pending_remaining_api_denominator")
        require(ordered(api_semantics(actual)) == ordered(api_semantics(reference)), "pending_remaining_api_difference")
        count += 1
    require(all(count == 1 for count in omitted_counts), "pending_each_step_exactly_one_omitted_view")
    return {"remaining_api_rows": count, "omitted_full_view_ordinals_in_reference": skipped}


def returned_semantics(value):
    if value is None: return None
    result = json.loads(value)
    original.strip_nonnegative_clock(result["drain"], "wall_seconds")
    output = json.loads(result["output"])
    output["intent"] = semantic_intent(output["intent"])
    result["output"] = output
    return result


def verify_reference(plan, name, raw, rows):
    folder = Path(plan["pending_ack_reference"]) / name
    previous = p.old.gzread(folder / "raw.json.gz")
    require(raw["physical_time"] == previous["physical_time"] == p.HORIZON and
        raw["control_status"] == previous["control_status"] == "reached", "pending_common_horizon_not_observed")
    require(raw["native_state_sha256"] == previous["native_state_sha256"], "pending_common_horizon_seal_changed")
    root, before = raw["root"], previous["root"]
    for key in ("owner", "root", "job", "client_state", "steps", "eligibility_schedule"):
        require(ordered(root[key]) == ordered(before[key]), "pending_protocol_or_schedule_changed:" + key)
    require(ordered(semantic_intent(root["intent"])) == ordered(semantic_intent(before["intent"])), "pending_immutable_intent_changed")
    require(ordered(client_calls(root["client_calls"])) == ordered(client_calls(before["client_calls"])), "pending_request_or_retry_changed")
    require(ordered(returned_semantics(root["returned"])) == ordered(returned_semantics(before["returned"])), "pending_return_or_drain_changed")
    require((root["returned_ns"] is None) == (before["returned_ns"] is None) and
        (root["censored_ns"] is None) == (before["censored_ns"] is None), "pending_closure_changed")
    comparison = compare_api_stream(folder / "service_tape.jsonl.gz", rows,
        omitted_reference_indices(raw, rows, previous))
    current_folder = Path(plan["candidate_output"]) / name
    candidate_shards = p.old.read(current_folder / "shards.json")
    reference_shards = p.old.read(folder / "shards.json")
    require(len(candidate_shards) == len(reference_shards), "pending_controller_part_denominator")
    for actual, prior in zip(candidate_shards, reference_shards, strict=True):
        require({k: v for k, v in actual.items() if k != "sha256"} ==
            {k: v for k, v in prior.items() if k != "sha256"}, "pending_controller_boundary_changed")
        a = p.old.gzread(current_folder / actual["path"]); b = p.old.gzread(folder / prior["path"])
        require(ordered(original.prefix_semantics(a)) == ordered(original.prefix_semantics(b)), "pending_background_controller_changed")
    return {"status": "exact_actual_tape_except_declared_postproof_reads_and_common9900_seal",
        **comparison, "controller_parts": len(candidate_shards), "native_state_sha256": raw["native_state_sha256"],
        "changed_observation_diagnostics": ["last_now", "observation_count", "reservation", "copies in returned codec"],
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
                command_count += 1; return ast.copy_location(ast.Constant(".probe_original_route_update_pending_ack"), node)
            if node.value == "split_deadline_actual_reference":
                label_count += 1; return ast.copy_location(ast.Constant("pending_ack_actual_reference"), node)
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


def verify(output):
    campaign = p.verify_campaign(output)
    plan = p.old.read(output / "preregistered_protocol.json")
    # This path is evidence location, not policy state; preparation pins it.
    require(plan["candidate_output"] == str(output.resolve()), "pending_output_identity")
    report = {"schema": p.SCHEMA, "status": "passed_saved_pending_ack_candidate", "declared_roots": 3,
        "campaign_sha256": p.old.sha(output / "campaign.json"), "cases": {}, "complete_100ms_certified": False,
        "native_executions_in_verifier": 0, "source_sha256": {str(Path(__file__).resolve()): p.old.sha(__file__)}}
    function = case_function()
    for name in p.CASES: report["cases"][name] = function(output, plan, name)
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
