"""Source-only construction screen for one new five-job synthetic mechanism.

No simulator, native session, saved outcome or search over parameter values.
Rational arithmetic is an analytic duration model, not native double-time
equality or a per-job protection certificate. Old fixture/model files stay put.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math

from . import research_preexisting_occupancy_domain as source_domain
from .native_host import prepare_input

VERSION = "live_obligation_interval_v1"
JOBS = {"loaded", "receiver", "reuse1", "reuse2", "blocker"}
CASE_IDS = ("mechanism", "no_overlap", "insufficient_advance")
SOURCE_CASE = {"case_id": "block1_load0", "blocker_load": 3., "receiver_load": 3.}


def rational(value):
    if type(value) not in (int, float, Fraction) or isinstance(value, bool):
        raise ValueError("interval:non_numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("interval:nonfinite")
    # Public decimal durations, explicitly separate from native binary clocks.
    return value if isinstance(value, Fraction) else Fraction(str(value))


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def scalar(value):
    value = rational(value)
    return {"rational": str(value), "seconds": float(value)}


def source_contract():
    """Public original three-tray fixture, corrected derived matrix, zero native."""
    return prepare_input(copy.deepcopy(source_domain.make_bundle(SOURCE_CASE)["contract"]))


def interval_screen(*, t0, x, hq, hx, advance, fixed_advance, detour,
                    resource_id, x_resource_id, capacity):
    """An isolated reservation-interval lemma, not whole-system prediction."""
    try:
        if type(capacity) is not int or capacity != 1:
            raise ValueError("unsupported_capacity")
        if type(resource_id) is not int or type(x_resource_id) is not int or resource_id != x_resource_id:
            raise ValueError("different_or_invalid_resource")
        t0, x, hq, hx, advance, fixed_advance, detour = map(
            rational, (t0, x, hq, hx, advance, fixed_advance, detour))
        if min(t0, x, fixed_advance) < 0 or min(hq, hx, detour) <= 0 or advance < 0:
            raise ValueError("invalid_duration")
    except (TypeError, ValueError) as exc:
        return {"status": "unknown_invalid_interval_contract", "reason": str(exc),
                "native_protection_certified": False}
    gap = t0 - x
    predicates = {
        "baseline_X_clears_before_Q": gap >= hx,
        "detour_exceeds_order_gap_and_fixed_initial_advance": detour > max(gap, fixed_advance),
        "early_supply_can_pay_detour": advance > detour,
        "even_earliest_default_Q_cannot_clear_before_X": advance < gap + hq,
        "bypass_beats_best_safe_timing_only_bound": advance - detour > gap - hx,
    }
    return {"status": "conditional_isolated_interval_witness" if all(predicates.values())
            else "rejected_isolated_interval_hypothesis", "predicates": predicates,
        "failed_predicates": [key for key, ok in predicates.items() if not ok],
        "reservation_time_semantics": "first irreversible capacity-counting reservation through actual release, not physical arrival",
        "D": scalar(gap), "safe_default_advance_upper": scalar(gap - hx),
        "bypass_advance": scalar(advance - detour),
        "assumptions": ["same capacity-one resource", "fixed positive reservation durations",
            "X remains an unfinished protected obligation", "bypass excludes this resource",
            "no other protected-job or downstream conflict", "native_default does not independently take the bypass",
            "real source-owned transfer and later route both executable"],
        "whole_population_protection": "unknown", "native_protection_certified": False,
        "online_delivery_verified": False}


def derive(data):
    """Derive a single candidate, no fitted output or case-result argument."""
    if digest(data) != digest(source_contract()):
        raise ValueError("interval:unsupported_source_contract")
    service = {row[0]: rational(row[2]) for row in data["node_records"]}
    travel = {(u, v): rational(length) / rational(speed) for u, v, length, speed in data["edge_records"]}
    jobs = {j["business_bag_id"]: j for j in data["jobs"]}
    wire, ack, period, return_wait = map(rational, (.01, .02, .05, .5))
    quantum = rational(.001)
    loaded_ready = rational(jobs["loaded"]["load_seconds"]) + service[0]
    p_leaves_one = rational(jobs["blocker"]["load_seconds"]) + service[1]
    default_depart = max(loaded_ready, p_leaves_one)
    # Paths end at mandatory Storage4, then use the real storage-out leg4->6.
    def release(start, path):
        at = start
        for a, b in zip(path, path[1:]):
            at = at + travel[a, b]
            at = at + service[b]
        at += service[4]  # new storage-out leg's source service
        at += travel[4, 6]
        at += service[6]
        at += rational(jobs["loaded"]["unload_seconds"])
        at += rational(jobs["loaded"]["hold_seconds"])
        return at
    slow = release(default_depart, (0, 1, 3, 4))
    fast = release(loaded_ready, (0, 2, 3, 4))
    # Both collection messages are actually required; this is the public
    # normal-delivery arithmetic, not a claim that delivery has occurred.
    exchange = max(wire + wire + ack, wire + wire + wire + wire)
    b = slow + exchange + return_wait
    return_suffix = wire + service[6] + travel[6, 7] + service[7]
    return_suffix += rational(jobs["reuse1"]["load_seconds"]) + service[7]
    t0 = b + return_suffix
    advance = t0 - (fast + exchange + return_suffix)
    fixed = t0 - (slow + exchange + return_suffix)
    hq = travel[7, 3] + service[3]
    # New9->3 uses the existing7->3 public length/speed and headway.
    hx = hq
    # Feasible D interval: HX <= D < (s+HX)/2. No iterative tuning.
    d_lo, d_hi = hx, (advance + hx) / 2
    if not d_lo < d_hi:
        return {"status": "failed_construction_empty_order_interval", "advance": scalar(advance),
                "r1_release_gain_upper": scalar(max(Fraction(0), slow + quantum - fast))}
    gap = (d_lo + d_hi) / 2
    delta_lo, delta_hi = max(gap, fixed), min(advance, advance - gap + hx)
    if not delta_lo < delta_hi:
        return {"status": "failed_construction_empty_detour_interval", "advance": scalar(advance)}
    detour = (delta_lo + delta_hi) / 2
    x = t0 - gap
    normal_suffix = travel[7, 3] + service[3] + travel[3, 4]
    old_bypass_suffix = travel[7, 8] + service[8] + travel[8, 4]
    added_bypass = detour - (old_bypass_suffix - normal_suffix)
    if added_bypass <= 0:
        return {"status": "failed_construction_nonpositive_new_edge_extension"}
    return {"status": "constructed_conditional_intervals", "arithmetic": "exact public decimal rationals; native float/event equivalence unproved",
        "values": {key: str(value) for key, value in {
            "slow_release": slow, "fast_release": fast, "release_gain": slow-fast,
            "r1_release_gain_upper_with_one_wake_quantum": slow+quantum-fast,
            "first_return_not_before": b, "exchange": exchange,
            "return_suffix": return_suffix, "t0": t0, "x": x, "hq": hq, "hx": hx,
            "advance": advance, "fixed_advance": fixed, "detour": detour,
            "added_bypass_travel": added_bypass, "return_wait": return_wait,
            "P_release": x-service[9], "no_overlap_x": t0-advance-hx-service[3],
            "no_overlap_P_release": t0-advance-hx-service[3]-service[9],
            "negative_R1_extra_travel": return_wait,
            "route_service_window": service[7],
            "later_collect_and_route_wire": exchange+wire,
        }.items()},
        "prefix_scope": ["existing directed source paths0-1-3-4-6 and0-2-3-4-6",
            "P initially holds1 until its load plus source service",
            "source1 departure release can precede source_berth_departed notification; one .001 same-time wake remains explicit",
            "no hidden additional carrier or substituted completed job",
            "bounds conditional on native S4 choosing these paths and no extra resource delay",
            "release gain1.0 (at most1.001 with the one named wake) is not a general native or original-map upper bound",
            "advance1.5 combines this isolated release gain1.0 with the existing first-return wait.5; it is not1.5 of R1 gain",
            "fixed_advance.5 assumes the same slow loaded path for the entire comparator; actual native_default may choose differently",
            "E occupancy, permission rejection/recovery and autonomous alternative paths are unresolved for the full fixed-initial family"],
        "source_sha256": digest(data)}


def static_permissions(data):
    reasons = []
    nodes = {n["node"]: n for n in data["node_contracts"]}
    jobs = {j["business_bag_id"]: j for j in data["jobs"]}
    edges = {(e["from"], e["to"]): e for e in data["edge_contracts"]}
    if len(jobs) != len(data["jobs"]) or set(jobs) != JOBS: reasons.append("population_identity")
    if [t["tray_id"] for t in data["trays"]] != ["L", "E", "P"]: reasons.append("three_tray_identity")
    for identity in ("loaded", "reuse1", "reuse2"):
        if jobs.get(identity, {}).get("allow_suffix_reroute") is not True: reasons.append("suffix_permission:"+identity)
    if (nodes[6]["resource_owner"], nodes[7]["resource_owner"]) != ("A", "B"): reasons.append("cross_owner_transfer")
    if not nodes[6]["allow_export"] or not nodes[7]["allow_receive"] or nodes[6]["export_min_stock"] != 0:
        reasons.append("static_export_receive_contract")
    if nodes[3]["capacity"] != 1 or nodes[9]["capacity"] != 1 or nodes[10]["capacity"] != 1:
        reasons.append("finite_conflict_capacity")
    for edge in ((0,2), (6,7), (7,8), (8,4), (1,9), (9,3), (3,10)):
        if edges.get(edge, {}).get("capacity", 0) <= 0: reasons.append("closed_or_missing_edge:"+str(edge))
    if data["faults"] or data["transfers"]: reasons.append("undeclared_exogenous_events")
    return {"status": "static_contract_permissions_present" if not reasons else "unsupported_static_permissions",
        "reasons": reasons, "current_owner_generation_and_receiving_capacity": "unknown_until_actual_local_decision",
        "native_action_executable": None}


def fixed_contracts():
    source = source_contract(); construction = derive(source)
    if construction["status"] != "constructed_conditional_intervals":
        return {"status": construction["status"], "construction": construction, "cases": []}
    v = {key: Fraction(value) for key, value in construction["values"].items()}
    outputs = []
    for identity in CASE_IDS:
        data = copy.deepcopy(source)
        data.pop("heuristic_time", None); data.pop("potential_contract", None)
        # Every new edge is globally part of the public directed graph.
        data["node_records"] = [list(row) for row in data["node_records"]]
        for row in data["node_records"]:
            row[5] = list(row[5])
            if row[0] == 9: row[5].append(3)
            if row[0] == 3: row[5].append(10)
        data["node_records"].append([10, 1, .1, 10, 0, []])
        data["node_contracts"].append({"node":10, "zone":"B", "resource_owner":"B",
            "control_partition":"partition_B", "capacity":1, "allow_export":False,
            "allow_receive":True, "export_min_stock":0})
        data["edge_records"] = [list(row) for row in data["edge_records"]]
        for row in data["edge_records"]:
            if row[:2] == [7,8]: row[2] += float(v["added_bypass_travel"]) * row[3]
            if identity == "insufficient_advance" and row[:2] == [0,2]:
                row[2] += float(v["negative_R1_extra_travel"]) * row[3]
        data["edge_records"].extend([[9,3,1.,1.], [3,10,1.,1.]])
        data["edge_contracts"].extend([{"from":a,"to":b,"capacity":1,"entry_headway":.5} for a,b in ((9,3),(3,10))])
        release = v["no_overlap_P_release"] if identity == "no_overlap" else v["P_release"]
        for job in data["jobs"]:
            if job["business_bag_id"] == "blocker":
                job.update(destination=10, storage_node=9, storage_release_at=float(release), storage_min_dwell=0.)
        data["model_scope"] = "NEW fixed live-obligation mechanism; five jobs/three trays; source-only, unexecuted"
        data = prepare_input(data)
        advance = v["advance"] - (v["negative_R1_extra_travel"] if identity == "insufficient_advance" else 0)
        x = v["no_overlap_x"] if identity == "no_overlap" else v["x"]
        screen = interval_screen(t0=v["t0"], x=x, hq=v["hq"], hx=v["hx"], advance=advance,
            fixed_advance=v["fixed_advance"], detour=v["detour"], resource_id=3, x_resource_id=3, capacity=1)
        outputs.append({"case_id": identity, "input": data, "input_sha256": digest(data),
            "interval_inputs": {key: scalar(value) for key,value in {"t0":v["t0"],"x":x,"hq":v["hq"],"hx":v["hx"],
                "advance":advance,"fixed_advance":v["fixed_advance"],"detour":v["detour"]}.items()},
            "interval_screen": screen, "static_permissions": static_permissions(data),
            "native_embedding_status": "unknown_all_five_job_calendar_and_dispatch_not_simulated",
            "whole_population_protection": "unknown", "native_executions":0})
    return {"schema":"g31.live_obligation_interval_construction.v1", "version":VERSION,
        "status":"three_fixed_source_only_contracts", "construction":construction, "cases":outputs,
        "initial_candidate_count_per_method":32, "later_candidate_count_per_method":4,
        "all_five_job_protection_required":True, "complete_request_100ms":"unassessed",
        "complete_fixed_initial_family_bound":"unknown_until_full_native_default_and_E_calendar_model",
        "new_projection_or_native_execution_count":0,
        "policy_contract": {"E_windows": source_domain.domain(SOURCE_CASE)["public_derivation"]["supply_windows"],
            "initial_R1":["native_default","prefer_2"],
            "first_return":["after fresh own empty observation and verified pair, not before public absolute b",
                            "after fresh own empty observation and verified pair, request immediately"],
            "b_seconds":float(v["first_return_not_before"]), "later_R1":["native_default","prefer_8"],
            "execute_first_action_only":True, "no_forced_route_claim":True,
            "no_message_age_or_wire_delay_relaxation":True,
            "strong_baselines": ["strict coordinate","plateau coordinate","pair repair","MPC enumeration",
                "ordinary boundary-aware LNS may internally explore unprotected proposals; deploy only whole-job-protected candidate"],
            "fixed_initial_reference":"all4 E windows x both first-return rules x both later choices, same information and budget",
            "later_default_reference":"all16 initial/E/return combinations with actual native_default, not one chosen ablation"},
        "required_new_predictor_semantics": [
            "Generic per-job mandatory Storage, including P9->3->10, instead of the old hard-coded loaded-only storage handler.",
            "Full11-node/14-edge native scorer, service-aware potential and every autonomous legal alternative for every tray, including1->9; no P-only edge restriction.",
            "Actual reservation-publication occupancy from edge_to/reception OR counting, node capacity, edge capacity, headway, FIFO and destination calendar; retained public traversal identities.",
            "Receiver E remains in all5 jobs. For latest E window4.201 its unobstructed reservation clearance at3 is8.811, overlapping the hypothetical early-Q normal entry8.75; this cannot be dropped. Rejected/retried earlier E windows need their full true chronology.",
            "Evaluate P/Q/E mutual contention, downstream capacity4 and6, P exit10 and both subsequent L returns. Interval witness alone does not supply any five-job completion vector.",
            "Exact first-return absolute window and same normal-message exchange, command wire and ACK epochs; current local owner/tray/generation/committed-prefix and receiving permissions revalidated at actual actions.",
            "Later input domain must include still-live P in Storage or transit. Old terminal-P receipt guard cannot be removed without complete new source-capture coverage and expiry/current-owner checks.",
            "Source-prefix and native-float/event-priority conformance must be established independently; decimal rational timing is not an epsilon or a native timestamp certificate."],
        "stop_rule":"No grid or tuning. If the full public predictor/source proof rejects the fixed construction, retain it as failed; do not enlarge release/route parameters to obtain a win. Validation must be separately preregistered; old validation256 is not read or reused."}
