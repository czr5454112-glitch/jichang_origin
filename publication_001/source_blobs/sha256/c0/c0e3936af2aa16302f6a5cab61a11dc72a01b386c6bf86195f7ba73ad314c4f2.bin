"""Offline exact-rational straight-guideway reference, separate from native physics.

This verifies fully specified motions. It is not an online solver or a physical
airport calibration. Original edge storage counts remain immutable metadata;
explicit hardware closure remains a hard constraint. Bodies can span multiple
segments only under the caller's separately versioned research contract.
"""
from fractions import Fraction
from itertools import pairwise


CONTRACT = "research.straight_supported_finite_body.v1"


def rational(value):
    if isinstance(value, bool):
        raise ValueError("finite_body:non_numeric")
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        raise ValueError("finite_body:nonfinite_or_invalid_number") from None


def _front(motion, at):
    points = motion["points"]
    for (t0, p0), (t1, p1) in pairwise(points):
        if t0 <= at <= t1:
            return p0 + (p1-p0)*(at-t0)/(t1-t0)
    raise ValueError("finite_body:motion_does_not_cover_clock")


def verify_schedule(data):
    """Return a complete interval certificate or a concrete rejection witness.

    Input uses one contiguous straight corridor, fixed positive-length bodies,
    explicit piecewise-linear nondecreasing front motions from0 throughH, and
    explicit permitted spanning. No new motion or physical resource is inferred.
    Acceleration, curvature and guideway support are declared outside this toy.
    """
    if data.get("contract") != CONTRACT or data.get("short_link_semantics") != "explicit_multisegment_body":
        raise ValueError("finite_body:separate_spanning_contract_required")
    horizon = rational(data["horizon"]); gap = rational(data["minimum_gap"])
    if horizon <= 0 or gap < 0:
        raise ValueError("finite_body:invalid_horizon_or_gap")
    segments = []
    for row in data["segments"]:
        lo, hi, speed = (rational(row[k]) for k in ("start", "end", "speed_limit"))
        if (not isinstance(row["segment_id"], str) or not row["segment_id"] or lo >= hi or speed <= 0
            or type(row["original_storage_count"]) is not int or row["original_storage_count"] < 0
            or type(row["hardware_closed"]) is not bool):
            raise ValueError("finite_body:invalid_segment")
        segments.append({**row, "start": lo, "end": hi, "speed_limit": speed})
    if (not segments or len({s["segment_id"] for s in segments}) != len(segments)
        or any(a["end"] != b["start"] for a, b in pairwise(segments))):
        raise ValueError("finite_body:one_contiguous_directed_corridor_required")
    motions = []
    cuts = {Fraction(0), horizon}
    for row in data["trays"]:
        length = rational(row["length"])
        points = [(rational(t), rational(p)) for t, p in row["front_motion"]]
        if (not isinstance(row["tray_id"], str) or not row["tray_id"] or length <= 0 or len(points) < 2
            or points[0][0] != 0 or points[-1][0] != horizon
            or any(t1 <= t0 or p1 < p0 for (t0, p0), (t1, p1) in pairwise(points))):
            raise ValueError("finite_body:invalid_fixed_body_or_forward_motion")
        motion = {"tray_id": row["tray_id"], "length": length, "points": points}
        motions.append(motion); cuts.update(t for t, _ in points)
        # Resource membership changes exactly when front or rear crosses an
        # endpoint. Include those analytic times, not a sampling time step.
        for (t0, p0), (t1, p1) in pairwise(points):
            if p1 == p0:
                continue
            for s in segments:
                for boundary in (s["start"], s["end"], s["start"]+length, s["end"]+length):
                    if p0 < boundary < p1:
                        cuts.add(t0+(boundary-p0)*(t1-t0)/(p1-p0))
    if not motions or len({m["tray_id"] for m in motions}) != len(motions):
        raise ValueError("finite_body:nonempty_fixed_unique_inventory_required")
    cuts = sorted(cuts)
    fifo = sorted(motions, key=lambda m: m["points"][0][1])
    def fail(kind, at, **fields):
        return {"status": "rejected", "contract": CONTRACT,
                "witness": {"kind": kind, "time": str(at), **fields}, "native_physics_changed": False}
    # Whole-body storage counts are retained as an additional constraint;
    # spanning a short link never rewrites its original zero to one.
    checks = sorted(set(cuts) | {(a+b)/2 for a, b in pairwise(cuts)})
    for t in checks:
        for m in motions:
            front = _front(m, t)
            if front-m["length"] < segments[0]["start"] or front > segments[-1]["end"]:
                return fail("unsupported_body_outside_corridor", t, tray_id=m["tray_id"])
        # Fixed initial order, checked at every slope boundary, is stronger
        # than sorting anew: an overtake cannot be hidden by reordering IDs.
        for follower, leader in pairwise(fifo):
            clearance = _front(leader, t)-leader["length"]-_front(follower, t)
            if clearance < gap:
                return fail("body_overlap_or_fifo_gap", t, follower=follower["tray_id"],
                            leader=leader["tray_id"], clearance=str(clearance), required_gap=str(gap))
        for s in segments:
            wholly_inside = sum(_front(m,t)-m["length"] >= s["start"] and _front(m,t) <= s["end"] for m in motions)
            if wholly_inside > s["original_storage_count"]:
                return fail("whole_body_storage_count_exceeded",t,segment_id=s["segment_id"],
                            count=wholly_inside,limit=s["original_storage_count"])
    leases = {(m["tray_id"], s["segment_id"]): [] for m in motions for s in segments}
    for t0, t1 in pairwise(cuts):
        mid = (t0+t1)/2
        for m in motions:
            front = _front(m, mid); rear = front-m["length"]
            speed = (_front(m, t1)-_front(m, t0))/(t1-t0)
            for s in segments:
                if not (front > s["start"] and rear < s["end"]):
                    continue
                if s["hardware_closed"]:
                    return fail("hardware_closed", t0, tray_id=m["tray_id"], segment_id=s["segment_id"])
                if speed > s["speed_limit"]:
                    return fail("body_spans_slower_drive", t0, tray_id=m["tray_id"],
                                segment_id=s["segment_id"], speed=str(speed), limit=str(s["speed_limit"]))
                rows = leases[m["tray_id"], s["segment_id"]]
                if rows and rows[-1][1] == t0:
                    rows[-1][1] = t1
                else:
                    rows.append([t0, t1])
    reservations = []
    for m in motions:
        final_front = _front(m, horizon)
        for s in segments:
            active = final_front > s["start"] and final_front-m["length"] < s["end"]
            for start, end in leases[m["tray_id"], s["segment_id"]]:
                reservations.append({"tray_id": m["tray_id"], "segment_id": s["segment_id"],
                    "start": str(start), "end": str(end), "active_at_horizon": active and end == horizon,
                    "original_storage_count": s["original_storage_count"]})
    return {"status": "verified_reference_schedule", "contract": CONTRACT, "horizon": str(horizon),
            "fixed_tray_ids": [m["tray_id"] for m in motions], "reservations": reservations,
            "reservation_semantics": "body intersection through actual rear clearance; horizon cuts retain live leases",
            "scope": "offline straight supported guideway with prescribed exact motions; no field/online/kinematic certificate",
            "native_physics_changed": False}
