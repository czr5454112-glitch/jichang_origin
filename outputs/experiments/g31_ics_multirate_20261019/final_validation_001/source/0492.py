"""Saved-only ACK chronology for the experimental sticky-hop continuation.

The last physical observation remains truthful.  A later ACK is instead bound
to its actual owner query and enclosing request step.  This module neither
executes a native call nor changes the original waiting-route assessor.
"""
from __future__ import annotations

import ast
import inspect
import json
import math
import textwrap

from . import research_original_waiting112 as original


def require(ok, why):
    if not ok:
        raise ValueError("pending_ack_evidence:" + why)


def ordered(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def finite_time(value):
    return type(value) in (int, float) and math.isfinite(value)


def actual_ack_query(root, rows, events):
    """Bind the retained ACK to an actual response, without freshening a view."""
    intent = root["intent"]
    ack, decision = intent.get("ack"), intent.get("decision")
    if not ack:
        return None
    require(decision is not None and decision["owner"] == root["owner"], "missing_ack_owner")
    require(finite_time(ack.get("delivered_at")) and finite_time(decision["at"]), "ack_clock_type")
    require(len(events) == len(root["steps"]), "step_denominator")
    matches = []
    previous_end = 0
    for step_index, (event, step) in enumerate(zip(events, root["steps"], strict=True)):
        start, end, at = event["first_api"], event["after_api"], event["at"]
        require(type(start) is int and type(end) is int and
                previous_end <= start < end <= len(rows), "event_interval")
        require(finite_time(at) and finite_time(step["at"]) and step["at"] == at and
                type(event["initial"]) is bool and step["initial"] is event["initial"], "step_binding")
        previous_end = end
        for index in range(start, end):
            row = rows[index]
            require(row["role"] == "request", "foreign_api_in_step")
            if row["endpoint"] != "protocol_command":
                continue
            if row.get("args") != [root["owner"], decision["request_id"]]:
                continue
            require(row.get("kwargs") == {} and type(row.get("ordinal")) is int and row["ordinal"] == index and
                    "error" not in row and finite_time(row["before"]) and finite_time(row["after"]) and
                    row["before"] == row["after"] == at,
                    "query_clock_or_identity")
            response = row.get("result", {})
            if "last_delivered_ack" not in response or ordered(response["last_delivered_ack"]) != ordered(ack):
                continue
            require(response.get("request_id") == decision["request_id"] and
                    response.get("kind") == "route" and response.get("status") == "acknowledged",
                    "query_response_identity")
            require(decision["at"] <= ack["delivered_at"] <= at, "future_or_predecision_ack")
            require(type(row["start_ns"]) is int and type(row["end_ns"]) is int and
                    type(root["started_ns"]) is int and
                    root["started_ns"] <= row["start_ns"] <= row["end_ns"], "query_wall_clock")
            root_end = root["returned_ns"] if root["returned_ns"] is not None else root["censored_ns"]
            require(type(root_end) is int and row["end_ns"] <= root_end, "query_after_root_end")
            matches.append({"query_ordinal": index, "step_index": step_index, "queried_at": at,
                "query_start_ns": row["start_ns"], "query_end_ns": row["end_ns"],
                "delivered_at": ack["delivered_at"], "request_id": decision["request_id"]})
    require(matches, "retained_ack_without_actual_query")
    return matches[0]


def assessor_with_query_bound():
    """Compile the original assessor with only its ACK observation upper bound changed."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(original.assess)))
    function = tree.body[0]
    wanted = ast.dump(ast.parse('intent["last_now"]', mode="eval").body, include_attributes=False)
    count = 0
    for node in ast.walk(function):
        if isinstance(node, ast.Compare) and len(node.comparators) == 2 and \
                ast.dump(node.comparators[-1], include_attributes=False) == wanted:
            require(ast.unparse(node) == "decision['at'] <= ack['delivered_at'] <= intent['last_now']",
                    "original_ack_guard_changed")
            node.comparators[-1] = ast.Name(id="ack_query_at", ctx=ast.Load())
            count += 1
    require(count == 1, "original_ack_guard_denominator")
    function.args.kwonlyargs.append(ast.arg(arg="ack_query_at"))
    function.args.kw_defaults.append(None)
    ast.fix_missing_locations(tree)
    namespace = dict(original.assess.__globals__)
    exec(compile(tree, "<query-bound-original-assessor>", "exec"), namespace)
    return namespace["assess"]


def assess(root, rows, events):
    proof = actual_ack_query(root, rows, events)
    result = assessor_with_query_bound()(root["intent"], root["client_calls"],
        ack_query_at=None if proof is None else proof["queried_at"])
    return {"assessment": result, "actual_ack_query": proof,
        "physical_observation_last_now": root["intent"]["last_now"],
        "observation_time_rewritten": False, "native_execution": False}
