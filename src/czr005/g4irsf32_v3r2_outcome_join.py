"""Strict V3R2 offline outcome join over normalized ordinary episodes."""

from __future__ import annotations

from collections import Counter, defaultdict
import math
from typing import Any, Mapping, Sequence


SCHEMA = "czr005.g4irsf32.v3r2_outcome_join.v1"
JOINED = "V3R2_OUTCOME_JOINED"
INVALID = "V3R2_OUTCOME_JOIN_INVALID"
REPEAT_DIAGNOSTIC = "V3R2_REPEATED_BAG_DIAGNOSTIC"
EPSILON = 1.0e-9
OUTPUTS = """
actual_L_service_start actual_L_service_complete actual_subsequent_source_wait
actual_subsequent_junction_wait actual_transit_seconds
actual_subsequent_calendar_wait actual_subsequent_wait
""".split()
J2_MAP = (
    ("external_request_id", "request_id"),
    ("external_request_lineage", "request_lineage"),
    ("external_request_generation", "request_generation"),
    ("external_junction_queue_generation", "junction_queue_generation"),
)


class OutcomeJoinError(ValueError):
    """The normalized input shape itself is invalid."""


class _Invalid(Exception):
    """One primary pair cannot be proven from ordinary telemetry."""


def _rows(value: Any, name: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise OutcomeJoinError(f"{name} must be a sequence of objects")
    return list(value)


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OutcomeJoinError(f"{name} must be an integer")
    return value


def _flag(value: Any, name: str) -> int:
    if value is True or value == 1:
        return 1
    if value is False or value == 0:
        return 0
    raise OutcomeJoinError(f"{name} must be bool or numeric 0/1")


def _num(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OutcomeJoinError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise OutcomeJoinError(f"{name} must be finite")
    return result


def _close(left: Any, right: Any, epsilon: float) -> bool:
    return math.isclose(
        _num(left, "left"), _num(right, "right"),
        rel_tol=0.0, abs_tol=epsilon,
    )


def _physical_commit_identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    path = _int(row.get("external_path_code"), "external_path_code")
    case_id = row["case_id"]
    common = (
        _int(row.get("external_runtime_bag_id"), "external_runtime_bag_id"),
        _int(row.get("external_task_id"), "external_task_id"),
        _int(row.get("external_upstream_node"), "external_upstream_node"),
        _int(row.get("node"), "node"),
    )
    if path == 1:
        event_seq = _int(
            row.get("external_direct_episode_event_seq"),
            "external_direct_episode_event_seq",
        )
        if event_seq <= 0:
            raise OutcomeJoinError(
                "DIRECT physical commit identity must be positive"
            )
        return (case_id, "DIRECT", event_seq, *common)
    if path == 2:
        values = tuple(_int(row.get(field), field) for field, _ in J2_MAP)
        if any(value <= 0 for value in values):
            raise OutcomeJoinError("J2 physical commit identity must be positive")
        return (case_id, "J2", *values, *common)
    raise OutcomeJoinError("external_path_code must be 1 or 2")


def _blank(
    row: Mapping[str, Any], status: str, reason: str, primary: bool
) -> dict[str, Any]:
    return {
        "case_id": row["case_id"],
        "observation_ordinal": row["observation_ordinal"],
        "opportunity_id": row["opportunity_id"],
        "primary": primary,
        "status": status,
        "reason": reason,
        "local": None,
        "external": None,
        "Y_realized": None,
        "A_gap": None,
        "X_insert": None,
        "H_gap": None,
    }


def _covered_union(
    episodes: Sequence[Mapping[str, Any]], row: Mapping[str, Any], end: float
) -> float:
    begin = _num(row["event_time"], "event_time")
    intervals: list[tuple[float, float]] = []
    for episode in episodes:
        if episode["case_id"] != row["case_id"] or episode["node"] != row["node"]:
            continue
        start = max(begin, _num(episode["actual_L_service_start"], "episode.start"))
        stop = min(end, _num(episode["actual_L_service_complete"], "episode.end"))
        if stop > start:
            intervals.append((start, stop))
    intervals.sort()
    if not intervals:
        return 0.0
    covered = 0.0
    start, stop = intervals[0]
    for next_start, next_stop in intervals[1:]:
        if next_start <= stop:
            stop = max(stop, next_stop)
        else:
            covered += stop - start
            start, stop = next_start, next_stop
    return covered + stop - start


def _external(
    row: Mapping[str, Any], episodes: Sequence[Mapping[str, Any]], epsilon: float
) -> Mapping[str, Any]:
    path = _int(row["external_path_code"], "external_path_code")
    flags = (
        path,
        _int(row["seam_kind_code"], "seam_kind_code"),
        _flag(row["has_direct_episode_identity"], "has_direct_episode_identity"),
        _flag(row["has_j2_identity"], "has_j2_identity"),
    )
    if flags not in {(1, 1, 1, 0), (2, 2, 0, 1)}:
        raise _Invalid("EXTERNAL_IDENTITY_FLAGS_OR_CODES")
    candidates = [
        episode
        for episode in episodes
        if episode["case_id"] == row["case_id"]
        and episode["runtime_bag_id"] == row["external_runtime_bag_id"]
        and episode["node"] == row["node"]
    ]
    if path == 1:
        if any(_int(row.get(field, 0), field) for field, _ in J2_MAP):
            raise _Invalid("DIRECT_FABRICATES_J2_IDENTITY")
        identity = _int(
            row["external_direct_episode_event_seq"],
            "external_direct_episode_event_seq",
        )
        matches = [
            episode for episode in candidates
            if episode.get("direct_commit_event_seq") == identity
        ]
    else:
        if _int(
            row.get("external_direct_episode_event_seq", 0),
            "external_direct_episode_event_seq",
        ):
            raise _Invalid("J2_FABRICATES_DIRECT_IDENTITY")
        if any(row_key not in row for row_key, _ in J2_MAP):
            raise _Invalid("J2_IDENTITY_MISSING")
        for row_key, _ in J2_MAP:
            _int(row[row_key], row_key)
        matches = [
            episode
            for episode in candidates
            if all(
                episode.get(episode_key) == row[row_key]
                for row_key, episode_key in J2_MAP
            )
            and episode.get("slot_node") == row["node"]
            and _close(episode.get("slot_start"), row["external_slot_start_seconds"], epsilon)
            and _close(episode.get("slot_end"), row["external_slot_end_seconds"], epsilon)
            and episode.get("slot_calendar_generation_before")
            == row["calendar_generation_before"]
        ]
    if len(matches) != 1:
        raise _Invalid("EXTERNAL_EPISODE_NOT_UNIQUE")
    return matches[0]


def _validated_external(
    row: Mapping[str, Any], episodes: Sequence[Mapping[str, Any]], epsilon: float
) -> tuple[Mapping[str, Any], dict[str, float]]:
    """Validate the full external episode before bag-repeat classification."""

    external = _external(row, episodes, epsilon)
    e0 = _num(row["external_slot_start_seconds"], "E0")
    e1 = _num(row["external_slot_end_seconds"], "E1")
    event_time = _num(row["event_time"], "event_time")
    external_out = {field: _num(external[field], field) for field in OUTPUTS}
    if (
        not _close(external_out["actual_L_service_start"], e0, epsilon)
        or not _close(external_out["actual_L_service_complete"], e1, epsilon)
        or not _close(e1 - e0, row["external_service_seconds"], epsilon)
        or not _close(row["external_projected_arrival"], e0, epsilon)
        or external["completion_event_seq"] <= row["event_seq"]
        or e0 < event_time - epsilon
    ):
        raise _Invalid("EXTERNAL_PROVENANCE_SLOT_OR_DURATION")
    return external, external_out


def _join(
    row: Mapping[str, Any], episodes: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], tuple[tuple[str, int, int], tuple[str, int, int]]]:
    epsilon = _num(row["epsilon"], "epsilon")
    if epsilon != EPSILON:
        raise OutcomeJoinError("epsilon must equal frozen 1e-9")
    external, external_out = _validated_external(row, episodes, epsilon)
    future = sorted(
        (
            episode
            for episode in episodes
            if episode["case_id"] == row["case_id"]
            and episode["runtime_bag_id"] == row["local_runtime_bag_id"]
            and episode["node"] == row["node"]
            and episode["completion_event_seq"] > row["event_seq"]
        ),
        key=lambda episode: episode["completion_event_seq"],
    )
    if not future:
        raise _Invalid("LOCAL_NEXT_EPISODE_MISSING")
    sequence = future[0]["completion_event_seq"]
    first = [episode for episode in future if episode["completion_event_seq"] == sequence]
    if len(first) != 1:
        raise _Invalid("LOCAL_NEXT_EPISODE_AMBIGUOUS")
    local = first[0]
    if external["completion_event_seq"] == sequence:
        raise _Invalid("PAIR_REUSES_SERVICE_EPISODE")

    e0 = _num(row["external_slot_start_seconds"], "E0")
    event_time = _num(row["event_time"], "event_time")
    local_start = _num(local["actual_L_service_start"], "local.start")
    local_end = _num(local["actual_L_service_complete"], "local.complete")
    if (
        row["local_runtime_bag_id"] == row["external_runtime_bag_id"]
        or not _close(local_end - local_start, row["local_service_seconds"], epsilon)
    ):
        raise _Invalid("CANDIDATE_IDENTITY_SLOT_OR_DURATION")
    total = local_start - event_time
    covered = _covered_union(episodes, row, local_start)
    source = total - covered
    y_realized = local_start - _num(row["L0"], "L0")
    if min(total, covered, source, y_realized) < -epsilon:
        raise _Invalid("NEGATIVE_LOCAL_WAIT_OR_REALIZED_MARGIN")
    total, covered, source = max(0.0, total), max(0.0, covered), max(0.0, source)
    if not _close(source + covered, total, epsilon):
        raise _Invalid("LOCAL_WAIT_DECOMPOSITION")
    local_out = {
        "actual_L_service_start": local_start,
        "actual_L_service_complete": local_end,
        "actual_subsequent_source_wait": source,
        "actual_subsequent_junction_wait": 0.0,
        "actual_transit_seconds": 0.0,
        "actual_subsequent_calendar_wait": covered,
        "actual_subsequent_wait": total,
    }
    result = {
        **_blank(row, JOINED, "UNIQUE_V3R2_PAIR", True),
        "local": local_out,
        "external": external_out,
        "Y_realized": y_realized,
        "A_gap": local_start - external_out["actual_L_service_start"],
        "X_insert": _num(row["X_insert"], "X_insert"),
        "H_gap": _num(row["H_gap"], "H_gap"),
    }
    keys = (
        (row["case_id"], row["node"], sequence),
        (row["case_id"], row["node"], external["completion_event_seq"]),
    )
    return result, keys


def join_v3r2_outcomes(
    rows: Sequence[Mapping[str, Any]],
    episodes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return strict joins plus outcome-blind repeated-bag diagnostics."""

    normalized_rows = _rows(rows, "rows")
    normalized_episodes = _rows(episodes, "episodes")
    for index, row in enumerate(normalized_rows):
        if not isinstance(row.get("case_id"), str) or not row["case_id"]:
            raise OutcomeJoinError(f"rows[{index}].case_id must be non-empty text")
        for field in (
            "observation_ordinal", "opportunity_id", "event_seq", "node",
            "local_runtime_bag_id", "external_runtime_bag_id",
        ):
            _int(row.get(field), f"rows[{index}].{field}")
        epsilon = _num(row.get("epsilon"), f"rows[{index}].epsilon")
        if epsilon != EPSILON:
            raise OutcomeJoinError(
                f"rows[{index}].epsilon must equal frozen 1e-9"
            )
    for index, episode in enumerate(normalized_episodes):
        if not isinstance(episode.get("case_id"), str) or not episode["case_id"]:
            raise OutcomeJoinError(f"episodes[{index}].case_id must be non-empty text")
        for field in ("runtime_bag_id", "node", "completion_event_seq"):
            _int(episode.get(field), f"episodes[{index}].{field}")
    row_identities: set[tuple[str, int, int]] = set()
    physical_commit_identities: set[tuple[Any, ...]] = set()
    for row in normalized_rows:
        row_identity = (
            row["case_id"], row["observation_ordinal"], row["opportunity_id"]
        )
        if row_identity in row_identities:
            raise OutcomeJoinError("duplicate observation identity")
        row_identities.add(row_identity)
        physical_identity = _physical_commit_identity(row)
        if physical_identity in physical_commit_identities:
            raise OutcomeJoinError("duplicate physical commit identity")
        physical_commit_identities.add(physical_identity)

    external_episode_identities: set[tuple[str, int, int]] = set()
    external_validation: dict[
        tuple[str, int, int], tuple[Mapping[str, Any] | None, str | None]
    ] = {}
    for row in normalized_rows:
        row_identity = (
            row["case_id"], row["observation_ordinal"], row["opportunity_id"]
        )
        try:
            external, _external_out = _validated_external(
                row, normalized_episodes, EPSILON
            )
        except _Invalid as error:
            external_validation[row_identity] = (None, str(error))
            continue
        external_validation[row_identity] = (external, None)
        external_identity = (
            row["case_id"],
            row["node"],
            _int(
                external.get("completion_event_seq"),
                "external.completion_event_seq",
            ),
        )
        if external_identity in external_episode_identities:
            raise OutcomeJoinError(
                "duplicate external service episode across observation seams"
            )
        external_episode_identities.add(external_identity)

    ordered = sorted(
        normalized_rows,
        key=lambda row: (
            _num(row["event_time"], "event_time"),
            row["event_seq"],
            row["observation_ordinal"],
        ),
    )
    seen: set[tuple[str, int]] = set()
    results: list[dict[str, Any]] = []
    claims: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    for row in ordered:
        row_identity = (
            row["case_id"], row["observation_ordinal"], row["opportunity_id"]
        )
        bags = {
            (row["case_id"], row["local_runtime_bag_id"]),
            (row["case_id"], row["external_runtime_bag_id"]),
        }
        repeated = bool(seen & bags)
        seen.update(bags)
        _external, provenance_error = external_validation[row_identity]
        if provenance_error is not None:
            results.append(
                _blank(row, INVALID, provenance_error, not repeated)
            )
            continue
        if repeated:
            results.append(
                _blank(row, REPEAT_DIAGNOSTIC, "EARLIER_PRIMARY_USED_BAG", False)
            )
            continue
        try:
            result, keys = _join(row, normalized_episodes)
            for key in keys:
                claims[key].append(len(results))
        except _Invalid as error:
            result = _blank(row, INVALID, str(error), True)
        results.append(result)
    reused = {index for owners in claims.values() if len(owners) > 1 for index in owners}
    for index in reused:
        results[index] = _blank(results[index], INVALID, "PRIMARY_EPISODE_REUSED", True)
    invalid_cases = {
        result["case_id"]
        for result in results
        if result["status"] == INVALID
    }
    case_status = {
        case: INVALID if case in invalid_cases else JOINED
        for case in sorted({row["case_id"] for row in normalized_rows})
    }
    for result in results:
        result["case_status"] = case_status[result["case_id"]]
    return {
        "schema": SCHEMA,
        "status": INVALID if invalid_cases else JOINED,
        "case_status": case_status,
        "status_counts": dict(Counter(result["status"] for result in results)),
        "pairs": results,
    }


__all__ = [
    "EPSILON", "INVALID", "JOINED", "OutcomeJoinError", "REPEAT_DIAGNOSTIC", "SCHEMA",
    "join_v3r2_outcomes",
]
