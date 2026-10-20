"""Independent saved-file gate for the finite original notification campaign."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import re

from . import run_original_notification_probe as campaign
from . import replay_original_notification_probe as replay
from . import original_notification_contract as boundary
from . import native025_request_timing as abi


def semantic_service_tape(rows):
    """Compare native semantics while retaining all clocks in original records.

    advance_to returns its own measured wall_seconds as well as physical facts.
    That one documented measurement can differ across plain/timed executions;
    physical clocks, budgets, arguments and all other result fields remain exact.
    This projection is never used to reduce the charged timing ledger.
    """
    projected = replay.canonical(rows)
    for row in projected:
        row.pop("start_ns", None); row.pop("end_ns", None)
        if row["endpoint"] == "advance_to" and "result" in row:
            duration = row["result"]["wall_seconds"]
            boundary.require(type(duration) in (int, float) and math.isfinite(duration) and duration >= 0,
                "invalid_native_advance_wall_seconds")
            del row["result"]["wall_seconds"]
    return projected


def verify_saved(directory):
    directory = Path(directory); plan = campaign.read(directory/"plan.json"); receipt = campaign.read(directory/"receipt.json")
    paths = campaign.source_paths()
    boundary.require(plan["contract"] == boundary.contract() and plan["cases"] == campaign.CASES and plan["arms"] == list(campaign.ARMS), "declared_domain_changed")
    expected_sources = {str(path.resolve()) for path in paths}
    boundary.require(set(plan["source_sha256"]) == expected_sources and not receipt["source_changed"]
        and campaign.sha(directory/"plan.json") == receipt["plan_sha256"], "source_or_plan_identity_changed")
    for path in paths:
        boundary.require(campaign.sha(path) == plan["source_sha256"][str(path.resolve())]
            == campaign.sha(directory/"source"/path.relative_to(campaign.ROOT)), "source_archive_mismatch")
    boundary.require(not campaign.unchanged(plan), "current_input_or_source_changed")
    profile = Path(plan["profile"])
    manifest = campaign.read(profile/"input_manifest.json")
    expected_inputs = {str((profile/name).resolve()): campaign.sha(profile/name) for name in ("input.json.gz", "input_manifest.json")}
    expected_inputs.update(manifest["source_sha256"])
    boundary.require(plan["input_source_sha256"] == expected_inputs, "input_source_inventory_changed")
    reference = campaign.read(directory/"accepted_reference.json")
    boundary.require(reference == plan["contract_reference"] and campaign.sha(directory/"accepted_reference.json") == plan["accepted_reference_sha256"]
        and campaign.sha(directory/"accepted_contract.json") == reference["sha256"] == plan["accepted_contract_sha256"], "accepted_phase_contract_changed")
    checked = abi.verify_contract(reference, require_runtime=True)
    boundary.require(checked["contract"]["binary_sha256"] == plan["binary_sha256"] and checked["contract"]["binary"] == plan["binary"], "native_binary_changed")
    expected_cells = {case+"/"+arm for case in campaign.CASES for arm in campaign.ARMS}
    boundary.require(len(receipt["declared_cells"]) == len(expected_cells) and
        set(receipt["declared_cells"]) == set(receipt["process_sha256"]) == set(receipt["completion_sha256"]) == expected_cells,
        "missing_declared_cell")
    frozen = campaign.read(Path(plan["profile"])/"input.json.gz")
    reports, records, tapes = {}, {}, {}
    for case in campaign.CASES:
        reports[case] = {}; records[case] = {}; tapes[case] = {}
        for arm in campaign.ARMS:
            key = case+"/"+arm; cell = directory/case/arm
            process_path = directory/(case+"_"+arm+".process.json")
            boundary.require(campaign.sha(process_path) == receipt["process_sha256"][key], "process_receipt_changed")
            process = campaign.read(process_path)
            boundary.require(process["status"] == "process_exited" and process["exit_code"] == 0
                and math.isfinite(process["wall_seconds"]) and process["wall_seconds"] > 0, "failed_or_invalid_worker")
            command = process["command"]
            boundary.require(isinstance(command, list) and len(command) == 10, "invalid_process_command")
            expected_command = [command[0], "-m", campaign.__name__, "--output", command[4], "--worker", "--case", case, "--arm", arm]
            boundary.require(command == expected_command and Path(command[4]).resolve() == directory.resolve(), "process_not_declared_cell")
            boundary.require(campaign.sha(cell/"completion.json") == receipt["completion_sha256"][key], "completion_receipt_changed")
            completion = campaign.read(cell/"completion.json")
            boundary.require(not completion["source_changed"] and not completion["unarchived_loaded_sources"]
                and campaign.sha(cell/"raw.json.gz") == completion["raw_sha256"]
                and campaign.sha(cell/"input.json.gz") == completion["input_sha256"], "raw_or_input_changed")
            raw, data = campaign.read(cell/"raw.json.gz"), campaign.read(cell/"input.json.gz")
            boundary.require(completion["status"] == raw["status"], "completion_status_changed")
            expected = replay.canonical(frozen); expected["owner_protocol"]["drop_ack_packets"] = campaign.CASES[case]
            boundary.require(replay.canonical(data) == expected and raw["source_offered_jobs"] == len(data["jobs"]) == 28506
                and raw["input_sha256"] == campaign.original.json_digest(data), "original_denominator_or_physical_input_changed")
            owners = sorted({n.get("resource_owner", n["zone"]) for n in data["node_contracts"]})
            boundary.require(raw["owners"] == owners and raw["case"] == case and raw["arm"] == arm and not raw["source_changed"]
                and not raw["unarchived_loaded_sources"]
                and raw["native_binary_sha256"] == plan["binary_sha256"] and re.fullmatch("[0-9a-f]{64}", raw["native_state_sha256"]), "cell_identity_changed")
            boundary.require(raw["chunks"] == completion["chunks"], "chunk_inventory_changed")
            chunks = []
            for index, item in enumerate(completion["chunks"]):
                boundary.require(item["index"] == index and item["path"] == ("tape_%04d.json.gz" % index)
                    and campaign.sha(cell/item["path"]) == item["sha256"], "missing_or_unsafe_chunk")
                chunks.append(campaign.read(cell/item["path"]))
            report = replay.verify_raw(raw, owners, chunks, mandatory_setup_start_ns=raw["mandatory_setup_start_ns"])
            report["whole_worker_process_upper_ns"] = math.ceil(process["wall_seconds"]*1e9)
            boundary.require(raw["ended_ns"]-raw["mandatory_setup_start_ns"] <= report["whole_worker_process_upper_ns"], "service_lifetime_exceeds_process_envelope")
            # Both setup interpretations remain visible. The authoritative root
            # bound above includes the capture constructor, without subtraction.
            capture = raw["capture_setup"]
            boundary.require(all(type(capture[k]) is int for k in ("start_ns", "end_ns")) and
                raw["mandatory_setup_start_ns"] <= capture["start_ns"] <= capture["end_ns"] <= raw["engine_start_ns"], "uncontained_capture_setup")
            report["diagnostic_capture_setup_ns"] = capture["end_ns"]-capture["start_ns"]
            rows = [r for chunk in chunks for r in chunk["service_tape"]]+raw["unflushed_service_tape"]
            # Preserve both outer and native-returned clocks in the original
            # tape/timing accounting. Compare the remaining semantic fields.
            tapes[case][arm] = semantic_service_tape(rows)
            if arm == "timed":
                timing = raw["timing"]
                boundary.require(not timing["errors"] and len(timing["envelopes"]) == len(rows), "native_envelope_coverage_gap")
                for row, envelope in zip(rows, timing["envelopes"]):
                    boundary.require(envelope["call_ordinal"] == row["ordinal"] and envelope["api_endpoint"] == row["endpoint"]
                        and row["start_ns"] <= envelope["start_ns"] <= envelope["end_ns"] <= row["end_ns"], "native_envelope_not_actual_service")
                report["native_phase_partition"] = abi.analyze_native025_timing(timing["batches"], timing["envelopes"], reference)
                boundary.require(report["native_phase_partition"]["status"] == "validated_partial_native025_phase_partition", "native_phase_partition_unknown")
            reports[case][arm] = report; records[case][arm] = raw
        boundary.require(replay.canonical(tapes[case]["plain"]) == replay.canonical(tapes[case]["timed"]), "instrumentation_changed_public_tape:"+case)
        for field in ("status", "physical_time", "admitted_notification_boundaries", "native_call_count", "ledger", "decisions", "outbox", "client_calls", "native_state_sha256"):
            boundary.require(replay.canonical(replay.without_clocks(records[case]["plain"][field])) ==
                replay.canonical(replay.without_clocks(records[case]["timed"][field])), "instrumentation_changed_execution:"+case+":"+field)
    return {"status": "validated_original_notification_operation_campaign", "cases": reports,
        "source_offered_jobs_per_cell": 28506, "cell_count": len(expected_cells),
        "all_public_service_tapes_equal_after_outer_clock_removal": True,
        "original_business_request_100ms_certified": False, "unconditional_complete_100ms_certified": False,
        "scope": "Finite experimental original-input notification bundles, full setup and native work charged. Not field business admission or full-day protection."}


def verify_or_unknown(directory):
    try: return verify_saved(directory)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, OSError) as error:
        return {"status": "unknown_invalid_or_incomplete_original_notification_campaign", "error": str(error),
            "declared_cells": [c+"/"+a for c in campaign.CASES for a in campaign.ARMS], "source_offered_jobs_per_cell": 28506,
            "original_business_request_100ms_certified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    campaign.write(args.output, verify_or_unknown(args.directory))


if __name__ == "__main__": main()
