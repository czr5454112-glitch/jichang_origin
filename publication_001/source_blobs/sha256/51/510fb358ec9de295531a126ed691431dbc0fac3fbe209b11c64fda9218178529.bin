"""Independent saved-data third-cycle audit. Never instantiate NativeSession."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

from . import research_original_low_wip_third as m
from .review_original_low_wip_reuse_saved import reachable, independent_fifo_choice, semantic_api_row


def require(ok, reason):
    if not ok:
        raise ValueError("third_saved_review:" + reason)


def ordered(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def manifest(output):
    return [json.loads(s) for s in (output / "api/manifest.jsonl").read_text(encoding="utf8").splitlines()]


def api_row(output, item):
    path = output / "api" / item["path"]
    require(m.base.sha(path) == item["sha256"], "api_file_changed")
    return m.base.gzread(path)


def old_prefix(output, second_at):
    old = m.PREDECESSOR
    for name, digest in m.PREDECESSOR_PINS.items():
        require(m.base.sha(old / name) == digest, "old_two_supply_evidence_changed")
    compared = 0
    for left, right in zip(manifest(old), manifest(output), strict=False):
        a, b = api_row(old, left), api_row(output, right)
        require(ordered(semantic_api_row(a)) == ordered(semantic_api_row(b)), "ordered_two_supply_prefix_changed")
        compared += 1
        if a["endpoint"] == "advance_to" and a["before"] == second_at and a["after"] > second_at:
            return {"compared_rows": compared, "through_before": a["before"], "through_after": a["after"],
                "only_removed_field": "advance_to.result.wall_seconds; finite nonnegative numeric required",
                "old_manifest_sha256": m.base.sha(old / "api/manifest.jsonl")}
    raise ValueError("third_saved_review:missing_second_phase_boundary")


def validate_third(data, raw, assessment):
    sources = [o for o in raw["owners"] if o.get("third_supply")]
    require(len(sources) == 1, "unique_third_source")
    source = sources[0]; owner = source["owner"]
    first, second, third = source["supply"], source["second_supply"], source["third_supply"]
    proof = third["return_proof"]; token = third["request"]["tray_id"]
    nodes = {n["node"]: n for n in data["node_contracts"]}
    witness = assessment["completion_witnesses"]
    require(len(witness) == 3 and proof["observed_at"] == third["at"]
        and proof["first_supply_request_id"] == second["request_id"]
        and proof["terminal_receipt"]["business_bag_id"] == second["choice"]["job"]["business_bag_id"]
        and proof["terminal_receipt"]["tray_id"] == proof["current_token"]["tray_id"] == token,
        "second_return_identity")
    ack = source["outbox"]["outbox"][second["request_id"]]["client_view"]["last_delivered_ack"]
    require(proof["first_received_ack"] == ack and ack["status"] == "received"
        and ack["delivered_at"] <= proof["terminal_receipt"]["completed_at"] == witness[1]["unload"]["time"]
        and witness[1]["hold_complete"]["time"] <= proof["current_token"]["available_at"] <= third["at"],
        "second_ack_unload_hold_order")
    current = proof["current_token"]
    require(current["mode"] == "empty" and not current["business_bag_id"] and current["edge_to"] < 0
        and current["reception_node"] < 0 and nodes[current["node"]]["resource_owner"] == owner
        and third["request"]["source"] == current["node"], "actual_owned_empty_source")
    own = proof["own_delivered_self_copy"]
    own_ack = source["outbox"]["outbox"][own["request_id"]]["client_view"]["last_delivered_ack"]
    require(own_ack == own["ack"] and own_ack["planning_snapshot_v2"] == own["envelope"]
        and own_ack["status"] == "delivered" and own_ack["delivered_at"] <= third["at"], "delivered_self_copy")
    own_env = own["envelope"]; local = own_env["capture"]["local_capture"]
    require(own_env["payload_sha256"] == m.base.capture_digest_v2(own_env["capture"])
        and local["source_owner"] == owner and proof["terminal_receipt"] in own_env["capture"]["extension"]["terminal_receipts"],
        "self_copy_digest_or_membership")
    peer = third["choice"]["delivered_message"]; peer_local = peer["capture"]["local_capture"]
    require(peer["payload_sha256"] == m.base.capture_digest_v2(peer["capture"])
        and peer["status"] == "conditional" and peer_local["target_owner"] == owner
        and peer_local["source_owner"] != owner and local["captured_at"] <= peer_local["captured_at"]
        and peer["delivered_at"] <= third["at"] < peer_local["valid_until"], "fresh_delivered_peer")
    chosen, considered = independent_fifo_choice(data, peer, current["node"])
    require(chosen == third["choice"]["job"] and third["request"]["destination"] == chosen["origin"], "independent_third_choice")
    heads = {}
    for job in sorted(peer_local["jobs"], key=lambda j: (j["arrival"], j["business_bag_id"])):
        if job["status"] == "waiting_for_tray" and nodes[job["origin"]]["resource_owner"] == peer_local["source_owner"]:
            heads.setdefault(job["origin"], job)
    diagnostic = []
    for origin, job in sorted(heads.items()):
        stages = [origin] + ([job["storage_node"]] if job["storage_node"] >= 0 else []) + [job["destination"]]
        diagnostic.append({"origin": origin, "head": job["business_bag_id"],
            "mandatory_paths_reachable": all(reachable(data, a, b) for a, b in zip(stages, stages[1:]))})
    # Fixed-case checks are audit assertions after the runtime decision, not policy inputs.
    require(chosen["business_bag_id"] == "projected:1x:8" and chosen["origin"] == 49
        and heads[26]["business_bag_id"] == "projected:1x:14"
        and not reachable(data, heads[26]["storage_node"], heads[26]["destination"]), "actual_case_or_blocked_head_changed")
    final = [t for t in raw["result"]["trays"] if t["tray_id"] == token]
    require(len(final) == 1 and final[0]["node"] == chosen["destination"] == 46 and final[0]["mode"] == "empty"
        and final[0]["job"] == -1 and final[0]["edge_to"] < 0 and final[0].get("reception_node", -1) < 0
        and final[0]["available_at"] >= witness[2]["hold_complete"]["time"], "final_third_return")
    require(nodes[46]["resource_owner"] == peer_local["source_owner"], "destination_resource_authority")
    return source, {"source_owner": owner, "recipient_owner": peer_local["source_owner"],
        "third_request_id": third["request_id"], "third_at": third["at"], "token": token,
        "second_received_ack": ack, "second_completion": proof["terminal_receipt"],
        "current_empty_node": current["node"], "current_empty_available_at": current["available_at"],
        "own_self_copy_request_id": own["request_id"], "own_message_id": local["message_id"],
        "own_captured_at": local["captured_at"], "own_ack_delivered_at": own_ack["delivered_at"],
        "peer_message_id": peer_local["message_id"], "peer_captured_at": peer_local["captured_at"],
        "peer_delivered_at": peer["delivered_at"], "all_actual_peer_fifo_heads": diagnostic,
        "eligible_order_considered": considered, "final_node": 46, "final_resource_owner": nodes[46]["resource_owner"],
        "authority_scope": "Final location/empty are offline native facts; no fourth-round owner observation or permission is inferred."}


def scan_actual_inputs(output, source):
    owner, second, third = source["owner"], source["second_supply"], source["third_supply"]
    token = third["request"]["tray_id"]; peer_owner = third["choice"]["delivered_message"]["capture"]["local_capture"]["source_owner"]
    views, messages, queries = {}, {}, {}
    physical, seen_commands, invitation_counts, first_invites = [], set(), {owner: 0, peer_owner: 0}, {}
    chosen_frame, third_ack_frame = None, None
    for item in manifest(output):
        row = api_row(output, item); name, args = row["endpoint"], row["args"]
        if name == "observe_protocol_control_policy_recent": views[args[0]] = row
        elif name == "protocol_planning_snapshots_v2": messages[args[0]] = row
        elif name in ("protocol_request", "protocol_command"):
            queries[tuple(args)] = row
            if args == [owner, third["request_id"]] and row["result"].get("last_delivered_ack", {}).get("status") == "received":
                third_ack_frame = row
        elif name == "submit_protocol_transfer":
            payload = args[0]
            if payload["request_id"] not in {p["request_id"] for p in physical}: physical.append(payload)
            if payload["request_id"] == third["request_id"] and chosen_frame is None:
                proof = third["return_proof"]; own = proof["own_delivered_self_copy"]
                view, msg = views[owner], messages[owner]
                require(view["before"] == view["result"]["now"] == row["before"] == third["at"], "actual_choice_clock")
                require([t for t in view["result"]["trays"] if t["tray_id"] == token] == [proof["current_token"]], "actual_choice_empty_view")
                require(msg["result"] == [third["choice"]["delivered_message"]], "actual_latest_peer_read")
                require(queries[(owner, second["request_id"])]["result"]["last_delivered_ack"] == proof["first_received_ack"], "actual_second_query")
                require(queries[(owner, own["request_id"])]["result"]["last_delivered_ack"] == own["ack"], "actual_self_query")
                require({k:v for k,v in payload.items() if k not in ("owner_id", "request_id")} == third["request"], "actual_third_payload")
                chosen_frame = {"submit_ordinal": row["ordinal"], "own_view_ordinal": view["ordinal"],
                    "peer_read_ordinal": msg["ordinal"], "second_ack_query_ordinal": queries[(owner, second["request_id"])]["ordinal"],
                    "self_ack_query_ordinal": queries[(owner, own["request_id"])]["ordinal"]}
        elif name == "submit_protocol_command":
            payload = args[0]
            if payload["request_id"] in seen_commands: continue
            seen_commands.add(payload["request_id"])
            if payload["kind"] != "planning_snapshot_v2" or row["before"] <= second["at"]: continue
            who = payload["owner_id"]
            if who == owner:
                view = views[who]["result"]; ack = queries[(owner, second["request_id"])]["result"].get("last_delivered_ack")
                require(view["now"] == row["before"] and m.reuse.current_empty(view, token)
                    and ack and ack["status"] == "received" and ack["delivered_at"] <= row["before"], "actual_third_invitation_before_return")
                evidence = {"at": row["before"], "ordinal": row["ordinal"], "view_ordinal": views[who]["ordinal"]}
            else:
                require(who == peer_owner and len(messages[who]["result"]) == 1, "actual_reply_owner_or_missing_message")
                env = messages[who]["result"][0]; local = env["capture"]["local_capture"]; ext = env["capture"]["extension"]
                require(env["status"] == "conditional" and local["source_owner"] == owner and local["target_owner"] == who
                    and env["delivered_at"] <= row["before"] < local["valid_until"]
                    and m.reuse.current_empty({"trays": local["trays"], "now": local["captured_at"]}, token), "actual_reply_before_delivered_return")
                a = [a for a in ext["submitted_physical_actions"] if a["request_id"] == second["request_id"]]
                require(len(a) == 1 and a[0]["last_delivered_ack"]["status"] == "received", "actual_reply_no_second_received")
                require(any(r["business_bag_id"] == second["choice"]["job"]["business_bag_id"]
                    and r["tray_id"] == token and r["source_owner"] == owner and r["event"] == "UNLOAD_COMPLETE"
                    and a[0]["last_delivered_ack"]["delivered_at"] <= r["completed_at"] <= local["captured_at"]
                    for r in ext["terminal_receipts"]), "actual_reply_wrong_completion")
                evidence = {"at": row["before"], "ordinal": row["ordinal"], "message_id": local["message_id"],
                    "message_delivered_at": env["delivered_at"], "peer_read_ordinal": messages[who]["ordinal"]}
            require(row["before"] <= third["at"] + m.base.VALIDITY, "unbounded_post_third_publication")
            invitation_counts[who] += 1; first_invites.setdefault(who, evidence)
    require(len(physical) == 25 and chosen_frame and third_ack_frame and all(invitation_counts.values()), "missing_full_third_api_chain")
    return {"unique_physical_requests": len(physical), "choice_frame": chosen_frame,
        "actual_third_received_query": {"ordinal": third_ack_frame["ordinal"], "at": third_ack_frame["before"],
            "ack": third_ack_frame["result"]["last_delivered_ack"]},
        "new_invitation_counts": invitation_counts, "first_actual_invitation_and_reply": first_invites}


def review(output, expected_ready):
    require(m.base.sha(output / "ready.json") == expected_ready, "ready_changed")
    ready, receipt = m.base.read(output / "ready.json"), m.base.read(output / "receipt.json")
    require(m.base.sha(output / "preregistered_protocol.json") == ready["plan_sha256"], "plan_changed")
    require(receipt["status"] == "worker_finished" and receipt["exit_code"] == 0 and not receipt["source_changed"]
        and receipt["wall_seconds"] <= 600 and all(receipt[k]["status"] == "child_finished" and receipt[k]["exit_code"] == 0
            for k in ("execution_process", "verification_process")), "bounded_terminal_receipt_required")
    for path, digest in ready["review_artifacts"].items(): require(m.base.sha(path) == digest, "review_source_changed")
    with m.installed(): replay = m.base.verify_saved(output)
    require(replay["assessment"]["third_cycle_proved"] is True, "closed_actual_third_lifecycle_missing")
    data, raw = m.base.gzread(output / "input.json.gz"), m.base.gzread(output / "raw_final.json.gz")
    ids, result_ids = [j["business_bag_id"] for j in data["jobs"]], [j["business_bag_id"] for j in raw["result"]["jobs"]]
    require(len(ids) == len(set(ids)) == len(result_ids) == len(set(result_ids)) == 28506 and set(ids) == set(result_ids), "all_offered_ids")
    require(len(data["trays"]) == len(raw["result"]["trays"]) == 22 and
        {t["tray_id"] for t in data["trays"]} == {t["tray_id"] for t in raw["result"]["trays"]}, "all_finite_trays")
    source, facts = validate_third(data, raw, replay["assessment"])
    api_facts = scan_actual_inputs(output, source)
    prefix = old_prefix(output, source["second_supply"]["at"])
    old = m.base.gzread(m.PREDECESSOR / "raw_final.json.gz")
    old_source = next(o for o in old["owners"] if o.get("second_supply"))
    require(source["supply"] == old_source["supply"] and source["second_supply"] == old_source["second_supply"], "old_supply_decisions_changed")
    first_ids = {source[k]["choice"]["job"]["business_bag_id"] for k in ("supply", "second_supply")}
    select = lambda result: [r for r in result["receipts"] if r.get("business_bag_id") in first_ids]
    require(ordered(select(raw["result"])) == ordered(select(old["result"])), "old_actual_lifecycles_changed")
    completed = [j["business_bag_id"] for j in raw["result"]["jobs"] if j["status"] == "completed"]
    require(len(completed) == 3 and set(completed) == first_ids | {"projected:1x:8"}, "exact_three_completions")
    names = ("ready.json", "preregistered_protocol.json", "receipt.json", "assessment.json", "raw_final.json.gz",
        "independent_verification.json", "api/manifest.jsonl", "input.json.gz")
    return {"schema": "g31.original_low_wip_third.independent_actual_review.v1", "status": "passed_saved_actual_third_cycle_review",
        "reviewer": {"source": str(Path(__file__).resolve()), "sha256": m.base.sha(__file__)},
        "evidence_sha256": {str(output / n): m.base.sha(output / n) for n in names},
        "native_executions_by_reviewer": 0, "new_native_seal_reconstruction": False, "full_api_replay": replay,
        "api_facts": api_facts, "actual_third_chain": facts, "two_supply_prefix": prefix,
        "first_two_supplies_and_all_job_receipts_exact": True, "completed": completed,
        "offered": 28506, "arrived_by_horizon": sum(j["arrival"] <= raw["physical_time"] for j in data["jobs"]),
        "unfinished_offered": 28503, "horizon": raw["physical_time"], "actual_gate_wall_seconds": receipt["wall_seconds"],
        "physical_audit": raw["physical_audit"], "producer_native_state_sha256": raw["native_state_sha256"],
        "strict_protection": "not_assessed", "complete_100ms_certified": False,
        "scope": "Frozen actual saved API/ACK/capture/current-empty/FIFO/receipt audit and old two-cycle comparison. Finite selected case; no general feasibility, fourth-round online authority or per-job protection claim."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True); p.add_argument("--expected-ready-sha256", required=True)
    p.add_argument("--report", type=Path, required=True); args = p.parse_args()
    require(not args.report.exists(), "report_already_exists")
    try:
        result = review(args.output, args.expected_ready_sha256)
    except Exception as error:
        m.base.write(args.report, {"status": "review_failed_or_third_unconfirmed", "error": repr(error),
            "source_sha256": m.base.sha(__file__), "native_executions_by_reviewer": 0})
        raise
    m.base.write(args.report, result)
    print(json.dumps({"status": result["status"], "sha256": m.base.sha(args.report),
        "completed": result["completed"], "api_rows": result["full_api_replay"]["api_rows"]}, ensure_ascii=False))


if __name__ == "__main__": main()
