"""Read-only actual second-supply evidence review; never constructs native state."""
from __future__ import annotations

import argparse
from collections import deque
from copy import deepcopy
import json
import math
from pathlib import Path

from . import research_original_low_wip_reuse as m


def require(condition, reason):
    if not condition:
        raise ValueError("reuse_saved_review:" + reason)


def reachable(data, start, finish):
    nodes = {n["node"]: n for n in data["node_contracts"]}
    caps = {(e["from"], e["to"]): e["capacity"] for e in data["edge_contracts"]}
    graph = {}
    for a, b, _, _ in data["edge_records"]:
        if caps[a, b] > 0 and nodes[a]["capacity"] > 0 and nodes[b]["capacity"] > 0:
            graph.setdefault(a, []).append(b)
    seen, queue = {start}, deque([start])
    while queue:
        node = queue.popleft()
        if node == finish: return True
        for nxt in graph.get(node, ()):
            if nxt not in seen: seen.add(nxt); queue.append(nxt)
    return False


def independent_fifo_choice(data, envelope, token_node):
    local = envelope["capture"]["local_capture"]
    nodes = {n["node"]: n for n in data["node_contracts"]}
    heads = {}
    for job in sorted(local["jobs"], key=lambda j: (j["arrival"], j["business_bag_id"])):
        if job["status"] != "waiting_for_tray" or nodes[job["origin"]]["resource_owner"] != local["source_owner"]:
            continue
        require(job["arrival"] <= local["captured_at"], "future_waiting_job")
        heads.setdefault(job["origin"], job)
    considered = []
    for job in sorted(heads.values(), key=lambda j: (j["arrival"], j["business_bag_id"])):
        origin = job["origin"]
        stages = [origin] + ([job["storage_node"]] if job["storage_node"] >= 0 else []) + [job["destination"]]
        allowed = (nodes[token_node]["zone"] != nodes[origin]["zone"] and nodes[token_node]["allow_export"]
            and nodes[origin]["allow_receive"] and reachable(data, token_node, origin)
            and all(reachable(data, a, b) for a, b in zip(stages, stages[1:])))
        considered.append({"job": job["business_bag_id"], "origin": origin, "positive_necessary_paths": allowed})
        if allowed: return job, considered
    return None, considered


def semantic_api_row(row):
    """Remove only the native advance's validated measured wall diagnostic."""
    row = deepcopy(row)
    if row["endpoint"] == "advance_to":
        duration = row["result"]["wall_seconds"]
        require(type(duration) in (int, float) and math.isfinite(duration) and duration >= 0,
            "invalid_native_advance_wall_seconds")
        del row["result"]["wall_seconds"]
    return row


def same005_prefix(output, first_at):
    old = m.OUT / "original_low_wip_prepare_005"
    require(m.base.sha(old / "api/manifest.jsonl") == "131f4598404e8199162087faf70beb090a384cfa795e933ec8764616e5540d7e", "predecessor_tape_manifest")
    old_manifest = [json.loads(line) for line in (old / "api/manifest.jsonl").read_text().splitlines()]
    new_manifest = [json.loads(line) for line in (output / "api/manifest.jsonl").read_text().splitlines()]
    compared = 0
    for left, right in zip(old_manifest, new_manifest, strict=False):
        require(m.base.sha(old / "api" / left["path"]) == left["sha256"], "old_api_changed")
        require(m.base.sha(output / "api" / right["path"]) == right["sha256"], "new_api_changed")
        a, b = m.base.gzread(old / "api" / left["path"]), m.base.gzread(output / "api" / right["path"])
        require(json.dumps(semantic_api_row(a), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            == json.dumps(semantic_api_row(b), ensure_ascii=False, separators=(",", ":"), allow_nan=False), "first_phase_ordered_api_difference")
        compared += 1
        if a["endpoint"] == "advance_to" and a["before"] == first_at and a["after"] > first_at:
            return {"compared_api_rows": compared, "through_before": a["before"], "through_after": a["after"],
                "predecessor_manifest_sha256": m.base.sha(old / "api/manifest.jsonl"),
                "timing_fields_removed": ["advance_to.result.wall_seconds"],
                "timing_field_guard": "finite nonnegative int or float, excluding bool; originals retained in pinned raw files"}
    raise ValueError("reuse_saved_review:missing_complete_first_phase_prefix")


def invitation_publications(output, source, peer, token, first, second):
    """Independent scan of recorded public reads preceding actual publication."""
    latest_view, latest_received, last_first_ack = {}, {}, None
    counts = {source: 0, peer: 0}
    first_proofs = {}
    submitted_ids = set()
    with (output / "api/manifest.jsonl").open(encoding="utf8") as manifest:
        for line in manifest:
            item = json.loads(line); path = output / "api" / item["path"]
            require(m.base.sha(path) == item["sha256"], "invitation_api_hash")
            row = m.base.gzread(path); name, args = row["endpoint"], row["args"]
            if name == "observe_protocol_control_policy_recent": latest_view[args[0]] = row["result"]
            elif name == "protocol_planning_snapshots_v2": latest_received[args[0]] = row["result"]
            elif name == "protocol_request" and args == [source, first["request_id"]]:
                last_first_ack = row["result"].get("last_delivered_ack")
            elif name == "submit_protocol_command":
                request = args[0]; owner = request["owner_id"]
                if request["request_id"] in submitted_ids: continue
                submitted_ids.add(request["request_id"])
                if request["kind"] != "planning_snapshot_v2" or row["before"] <= first["at"]: continue
                require(row["before"] <= second["at"] + m.base.VALIDITY, "new_publication_after_last_invitation_expiry")
                if owner == source:
                    view = latest_view[source]
                    require(view["now"] == row["before"] and view["owner_id"] == source
                        and m.current_empty(view, token) and last_first_ack and last_first_ack["status"] == "received"
                        and last_first_ack["delivered_at"] <= row["before"], "source_invitation_not_actually_returned")
                    proof = {"view": view, "received_ack": last_first_ack, "at": row["before"]}
                elif owner == peer:
                    received = latest_received[peer]
                    require(len(received) == 1, "missing_actual_invitation")
                    env = received[0]; local = env["capture"]["local_capture"]
                    require(env["status"] == "conditional" and env["delivered_at"] <= row["before"] < local["valid_until"]
                        and local["source_owner"] == source and local["target_owner"] == peer, "reply_before_actual_invitation")
                    require(m.returned_invitation(env, token, source, {n["node"]: n for n in latest_view[peer]["node_contracts"]}), "reply_invitation_incomplete")
                    proof = {"message_id": local["message_id"], "captured_at": local["captured_at"],
                        "delivered_at": env["delivered_at"], "at": row["before"]}
                else: raise ValueError("reuse_saved_review:foreign_publication_owner")
                counts[owner] += 1
                first_proofs.setdefault(owner, deepcopy(proof))
    require(counts[source] > 0 and counts[peer] > 0, "missing_actual_invitation_or_reply")
    return {"post_first_publication_counts": counts, "first_publication_proofs": first_proofs}


def review(output, expected_ready):
    ready_path = output / "ready_receipt.json"
    require(m.base.sha(ready_path) == expected_ready, "readiness_pin")
    ready = m.base.read(ready_path)
    plan = m.base.read(output / "preregistered_protocol.json")
    require(m.base.sha(output / "preregistered_protocol.json") == ready["plan_sha256"], "plan_pin")
    receipt = m.base.read(output / "receipt.json")
    require(receipt["status"] == "worker_finished" and receipt["exit_code"] == 0
        and receipt["execution_process"]["status"] == "child_finished"
        and receipt["verification_process"]["status"] == "child_finished"
        and receipt["wall_seconds"] <= m.PARENT_SECONDS and receipt["source_changed"] == [], "successful_bounded_gate_required")
    for p, digest in ready["evidence_sha256"].items(): require(m.base.sha(p) == digest, "prepared_evidence_changed")
    with m.installed(): closed_verification = m.base.verify_saved(output)
    require(closed_verification["assessment"]["second_reuse_proved"] is True, "actual_second_lifecycle_missing")
    data = m.base.gzread(output / "input.json.gz")
    raw = m.base.gzread(output / "raw_final.json.gz")
    require(m.base.sha(output / "input.json.gz") == m.base.INPUT_SHA, "original_input_identity")
    ids = [j["business_bag_id"] for j in data["jobs"]]
    result_ids = [j["business_bag_id"] for j in raw["result"]["jobs"]]
    require(len(ids) == len(set(ids)) == len(result_ids) == len(set(result_ids)) == 28506
        and set(ids) == set(result_ids), "whole_offered_denominator")
    require(len(raw["result"]["trays"]) == len(data["trays"]) == 22
        and {t["tray_id"] for t in raw["result"]["trays"]} == {t["tray_id"] for t in data["trays"]}, "finite_tray_identity")
    owners = [o for o in raw["owners"] if o.get("second_supply")]
    require(len(owners) == 1, "one_second_supply_source")
    owner = owners[0]; source = owner["owner"]; peer = next(o for o in plan["parking_plan"]["owners"] if o != source)
    first, second, token = owner["supply"], owner["second_supply"], plan["parking_plan"]["token_tray_id"]
    proof = second["return_proof"]; first_job = first["choice"]["job"]["business_bag_id"]
    require(proof["observed_at"] == second["at"] and proof["current_token"]["tray_id"] == token
        and proof["terminal_receipt"]["business_bag_id"] == first_job, "second_return_proof_identity")
    own = proof["own_delivered_self_copy"]
    saved_ack = owner["outbox"]["outbox"][own["request_id"]]["client_view"]["last_delivered_ack"]
    require(saved_ack == own["ack"] and saved_ack["planning_snapshot_v2"] == own["envelope"]
        and saved_ack["delivered_at"] <= second["at"], "actual_own_self_ack")
    witness = closed_verification["assessment"]["completion_witnesses"]
    require(proof["terminal_receipt"]["completed_at"] == witness[0]["unload"]["time"]
        and witness[0]["hold_complete"]["time"] <= proof["current_token"]["available_at"] <= second["at"], "real_return_before_second_supply")
    peer_env = second["choice"]["delivered_message"]
    require(peer_env["delivered_at"] <= second["at"] < peer_env["capture"]["local_capture"]["valid_until"], "second_peer_delivery_time")
    expected, heads = independent_fifo_choice(data, peer_env, proof["current_token"]["node"])
    require(expected == second["choice"]["job"], "independent_fifo_head_choice")
    supplied_job_ids = [first_job, second["choice"]["job"]["business_bag_id"]]
    complete_ids = [j["business_bag_id"] for j in raw["result"]["jobs"] if j["status"] == "completed"]
    require(set(complete_ids) == set(supplied_job_ids) and len(complete_ids) == 2, "exact_two_business_completions")
    prefix = same005_prefix(output, first["at"])
    invitations = invitation_publications(output, source, peer, token, first, second)
    pins = {str(output / name): m.base.sha(output / name) for name in
        ("ready_receipt.json", "preregistered_protocol.json", "receipt.json", "raw_final.json.gz", "assessment.json",
         "independent_verification.json", "api/manifest.jsonl", "input.json.gz")}
    return {"schema": "g31.original_low_wip_second_supply.independent_actual_review.v1", "status": "passed_saved_actual_two_supply_review",
        "reviewer_source": {"path": str(Path(__file__).resolve()), "sha256": m.base.sha(__file__)}, "evidence_sha256": pins,
        "native_executions_by_reviewer": 0, "new_native_state_replay": False, "closed_saved_api_replay": closed_verification,
        "actual_gate_wall_seconds": receipt["wall_seconds"], "offered": 28506,
        "arrived_by_horizon": sum(j["arrival"] <= raw["physical_time"] for j in data["jobs"]),
        "horizon": raw["physical_time"], "actual_completed_jobs": complete_ids, "unfinished_offered": 28504,
        "same_token": token, "first_supply_at": first["at"], "second_supply_at": second["at"],
        "independent_fifo_heads_considered": heads, "source_return_proof": proof, "actual_invitation_chain": invitations,
        "first_phase_exact005_prefix": prefix, "physical_audit": raw["physical_audit"], "producer_native_seal": raw["native_state_sha256"],
        "strict_protection": "not_assessed", "complete_100ms_certified": False,
        "scope": "Saved actual input, complete API argument/reply/clock replay, source/digest/ACK/own-empty/peer FIFO chain, physical receipt lifecycle and exact predecessor prefix. No new NativeSession or native seal reconstruction; no general feasibility or protected multi-job service proof."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--expected-ready-sha256", required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    require(not args.report.exists(), "report_already_exists")
    try:
        result = review(args.output, args.expected_ready_sha256)
    except Exception as error:
        m.base.write(args.report, {"schema": "g31.original_low_wip_second_supply.independent_actual_review.v1",
            "status": "review_failed_or_actual_second_witness_unconfirmed", "error": repr(error),
            "reviewer_source_sha256": m.base.sha(__file__), "native_executions_by_reviewer": 0,
            "producer_receipt_sha256": m.base.sha(args.output / "receipt.json") if (args.output / "receipt.json").is_file() else None})
        raise
    m.base.write(args.report, result)
    print(json.dumps({"status": result["status"], "report_sha256": m.base.sha(args.report),
        "completed": result["actual_completed_jobs"], "token": result["same_token"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
