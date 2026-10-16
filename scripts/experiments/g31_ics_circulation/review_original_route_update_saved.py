"""Pure independent result and external launch linkage for route probe001."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from . import probe_original_route_update as p
from . import verify_original_route_update as v


def require(ok, reason):
    if not ok: raise ValueError("route_saved_review:" + reason)


def validate_launch(external, ready, plan, parent, *, file_sha=p.old.sha):
    require(external["schema"] == "g31.original_route_probe.external_launch_receipt.v1" and
        external["status"] == "application_exited_zero" and external["exit_code"] == 0 and
        external["error"] is None and external["evidence_identities_unchanged"] is True, "external_failed_or_drifted")
    require(external["command"] == ready["execute_command"], "external_command_mismatch")
    expected = {"ready": (str(Path(ready["output"]) / "ready_receipt.json"), None),
        "preregistered_plan": (ready["preregistered_plan_path"], ready["preregistered_plan_sha256"]),
        "wrapper": (ready["external_wrapper"]["path"], ready["external_wrapper"]["sha256"])}
    for kind, (path, digest) in expected.items():
        row = external[kind]
        actual = file_sha(path)
        require(Path(row["path"]).resolve() == Path(path).resolve() and row["sha256"] == row["final_sha256"] == actual
            and (digest is None or actual == digest), "external_" + kind + "_identity")
    require(external["interpreter"] == plan["interpreter"] and file_sha(external["interpreter"]["path"]) ==
        external["interpreter"]["sha256"], "external_interpreter")
    keys = ("stopwatch_frequency", "harness_measured_start_tick", "application_launch_tick", "application_exit_tick")
    require(all(type(external[k]) is int and external[k] > 0 for k in keys), "external_clock_types")
    frequency, first, launch, end = [external[k] for k in keys]
    require(first <= launch <= end, "external_clock_order")
    duration = (end-launch)/frequency
    require(external["whole_application_campaign_wall_seconds"] == duration and
        external["measured_harness_and_campaign_wall_seconds"] == (end-first)/frequency, "external_duration")
    require(parent["status"] == "completed_finite_probe" and parent["source_changed"] == [] and
        parent["plan_sha256"] == ready["preregistered_plan_sha256"] and
        parent["verification"]["status"] == "child_finished" and parent["verification"]["exit_code"] == 0,
        "application_not_complete")
    require(set(parent["cases"]) == set(p.CASES) and all(row["exit_code"] == 0 and row["status"] == "child_finished"
        for row in parent["cases"].values()), "case_denominator")
    require(0 <= parent["wall_seconds"] <= p.PARENT_SECONDS and duration >= parent["wall_seconds"] >=
        sum(row["whole_child_wall_seconds"] for row in parent["cases"].values()) +
        parent["verification"]["whole_child_wall_seconds"], "whole_campaign_not_covering_children")
    return duration*1000


def review(output, expected_ready_sha):
    require(p.old.sha(output / "ready_receipt.json") == expected_ready_sha, "prepared_readiness_changed")
    ready = p.old.read(output / "ready_receipt.json"); plan = p.old.read(output / "preregistered_protocol.json")
    parent = p.old.read(output / "receipt.json"); external = p.old.read(output / "external_launch_receipt.json")
    charge = validate_launch(external, ready, plan, parent)
    replay = v.verify(output)
    require(v.ordered(replay) == v.ordered(p.old.read(output / "independent_verification.json")), "saved_verifier_summary_changed")
    cases = {}
    for name in p.CASES:
        raw = p.old.gzread(output / name / "raw.json.gz")
        root = raw["root"]; intent = root["intent"]
        calls = root["client_calls"]; decision = intent["decision"]
        if decision is not None:
            require(decision["local_job"]["business_bag_id"] == p.JOB and decision["at"] >= p.ADMISSION
                and decision["request"]["message_delay"] == 2., "actual_business_request_scope")
            require(calls and sum(not c["retry"] for c in calls) == 1 and all(c["request"] == calls[0]["request"] for c in calls), "immutable_transport_lineage")
        cases[name] = {**replay["cases"][name], "physical_end": raw["physical_time"],
            "root_closed_at": root["lineage"][p.ROOT_ID]["output_returned"],
            "submitted_at": decision["at"] if decision else None,
            "actual_ack": intent["ack"], "actual_edge": intent["edge"],
            "actual_attempt_times": [c["at"] for c in calls],
            "full_application_campaign_charge_ms": charge,
            "charge_interpretation": "Full application execution charge for each root without division, including all other cases and verification. Closed-root conservative envelope; an open root's eventual service completion remains unknown.",
            "complete_root_cold_upper_ms": charge if root["returned_ns"] is not None else None}
    names = ("ready_receipt.json", "preregistered_protocol.json", "receipt.json", "external_launch_receipt.json", "independent_verification.json")
    return {"schema": "g31.original_route_probe.independent_actual_review.v1", "status": "passed_saved_actual_and_external_launch_review",
        "evidence_sha256": {str(output / name): p.old.sha(output / name) for name in names},
        "review_source": {"path": str(Path(__file__).resolve()), "sha256": p.old.sha(__file__)},
        "declared_roots": 3, "closed_roots": replay["closed_roots"], "open_roots": replay["open_roots"],
        "cases": cases, "native_executions_by_reviewer": 0, "new_native_seal_replay": False,
        "background_controller_recomputed": False, "request_side_saved_api_replayed": True,
        "whole_application_campaign_charge_ms_per_root": charge,
        "exclusions": external["exclusions"], "unbiased_business_sample": False,
        "long_term_route_maintenance_certified": False, "complete_100ms_certified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-ready-sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(); require(not args.report.exists(), "report_exists")
    result = review(args.output.resolve(), args.expected_ready_sha256)
    p.old.write(args.report, result)
    print(json.dumps({"status": result["status"], "sha256": p.old.sha(args.report),
        "closed": result["closed_roots"], "open": result["open_roots"], "campaign_ms": result["whole_application_campaign_charge_ms_per_root"]}))


if __name__ == "__main__": main()
