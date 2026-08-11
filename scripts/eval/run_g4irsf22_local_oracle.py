from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


HORIZONS = (5, 15, 30, 60)
SUMMARY_FIELDS = (
    "queue_area_bag_seconds",
    "scheduled_incoming_area_bag_seconds",
    "next_service_deficit_area_seconds_squared",
    "queued_wait_seconds_at_horizon",
)


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _horizon_row(summary: Mapping[str, Any], horizon: int) -> Mapping[str, Any]:
    rows = summary.get("horizons")
    if not isinstance(rows, list):
        raise ValueError("local future summary omitted horizons")
    matches = [
        row
        for row in rows
        if isinstance(row, Mapping) and row.get("horizon_seconds") == horizon
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one {horizon}s local future row")
    row = matches[0]
    if row.get("coverage_complete") is not True:
        raise ValueError(f"{horizon}s local future coverage is incomplete")
    for field in SUMMARY_FIELDS:
        value = _finite(row.get(field), field)
        if value < 0.0:
            raise ValueError(f"{field} must be non-negative")
    return row


def local_information_cost(summary: Mapping[str, Any], horizon: int) -> float:
    """Score an action for the fixed local-information heuristic screen.

    Queue and scheduled-incoming areas are the primary pressure signal.  The
    service-calendar deficit is converted from seconds squared back to
    bag-seconds by dividing by the horizon. Reservation/completion counters
    remain diagnostics because a cancelled reservation is not a completed
    service. Realized completion utility is deliberately not accepted by this
    function.
    """

    row = _horizon_row(summary, horizon)
    queue_area = _finite(row["queue_area_bag_seconds"], "queue_area_bag_seconds")
    incoming_area = _finite(
        row["scheduled_incoming_area_bag_seconds"],
        "scheduled_incoming_area_bag_seconds",
    )
    service_deficit = _finite(
        row["next_service_deficit_area_seconds_squared"],
        "next_service_deficit_area_seconds_squared",
    )
    queued_wait = _finite(
        row["queued_wait_seconds_at_horizon"],
        "queued_wait_seconds_at_horizon",
    )
    return (
        queue_area
        + incoming_area
        + service_deficit / float(horizon)
        + queued_wait
    )


def _action_identity(candidate: Mapping[str, Any]) -> tuple[str, int | None]:
    kind = str(candidate.get("action_kind"))
    selected = candidate.get("selected_next_node")
    if kind == "NEXT_EDGE" and type(selected) is int:
        return kind, int(selected)
    if kind == "WAIT" and selected is None:
        return kind, None
    raise ValueError("candidate action identity is invalid")


def rank_group(
    group: Mapping[str, Any],
    *,
    horizons: Sequence[int] = HORIZONS,
    consensus_required: int = 3,
) -> dict[str, Any]:
    candidates = group.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise ValueError("choice group must contain at least two candidates")
    s4_index = group.get("s4_index")
    if type(s4_index) is not int or not 0 <= s4_index < len(candidates):
        raise ValueError("choice group has an invalid s4_index")

    winners: list[int] = []
    score_rows: list[dict[str, Any]] = []
    for horizon in horizons:
        scored: list[tuple[float, int]] = []
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, Mapping):
                raise ValueError("candidate must be a mapping")
            summary = candidate.get("local_future_summary")
            if not isinstance(summary, Mapping):
                raise ValueError("candidate omitted local_future_summary")
            scored.append((local_information_cost(summary, int(horizon)), index))
        best_cost = min(value for value, _ in scored)
        tied = [index for value, index in scored if math.isclose(value, best_cost)]
        winner = s4_index if s4_index in tied else min(tied)
        winners.append(winner)
        score_rows.append(
            {
                "horizon_seconds": int(horizon),
                "winner_index": winner,
                "costs": [value for value, _ in scored],
            }
        )

    consensus = Counter(winners).most_common()
    selected_index = s4_index
    if consensus and consensus[0][1] >= consensus_required:
        selected_index = consensus[0][0]
    selected = candidates[selected_index]
    s4 = candidates[s4_index]
    selected_utility = _finite(selected.get("utility"), "utility")
    s4_utility = _finite(s4.get("utility"), "utility")
    perfect_utility = max(_finite(row.get("utility"), "utility") for row in candidates)
    horizon_gains = [
        _finite(candidates[index].get("utility"), "utility") - s4_utility
        for index in winners
    ]
    return {
        "choice_group_id": group.get("choice_group_id"),
        "s4_index": s4_index,
        "selected_index": selected_index,
        "selected_action": _action_identity(selected),
        "fallback_to_s4": selected_index == s4_index,
        "horizon_winners": winners,
        "horizon_scores": score_rows,
        "horizon_realized_utility_gains_vs_s4_seconds": horizon_gains,
        "realized_utility_gain_vs_s4_seconds": selected_utility - s4_utility,
        "perfect_action_gain_vs_s4_seconds": perfect_utility - s4_utility,
    }


def summarize(groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [rank_group(group) for group in groups]
    gains = [float(row["realized_utility_gain_vs_s4_seconds"]) for row in rows]
    ceilings = [float(row["perfect_action_gain_vs_s4_seconds"]) for row in rows]
    count = len(rows)
    per_horizon: list[dict[str, Any]] = []
    for horizon_index, horizon in enumerate(HORIZONS):
        horizon_gains = [
            float(row["horizon_realized_utility_gains_vs_s4_seconds"][horizon_index])
            for row in rows
        ]
        non_s4 = sum(
            row["horizon_winners"][horizon_index] != row["s4_index"]
            for row in rows
        )
        beneficial = sum(value > 0.0 for value in horizon_gains)
        harmful = sum(value < 0.0 for value in horizon_gains)
        per_horizon.append(
            {
                "horizon_seconds": horizon,
                "non_s4_selection_count": non_s4,
                "beneficial_count": beneficial,
                "harmful_count": harmful,
                "beneficial_precision_when_non_s4": (
                    beneficial / non_s4 if non_s4 else None
                ),
                "mean_gain_vs_s4_seconds": (
                    sum(horizon_gains) / count if count else 0.0
                ),
            }
        )
    useful_horizons = [
        row["horizon_seconds"]
        for row in per_horizon
        if row["non_s4_selection_count"] > 0
        and row["beneficial_count"] > row["harmful_count"]
        and row["mean_gain_vs_s4_seconds"] > 0.0
    ]
    return {
        "schema": "czr005.g4irsf22.local_information_heuristic_screen.v2",
        "screen_kind": "FIXED_LOCAL_COST_PLUS_THREE_OF_FOUR_CONSENSUS",
        "not_a_perfect_information_upper_bound": True,
        "held_out_validation": False,
        "group_count": count,
        "consensus_non_s4_count": sum(not row["fallback_to_s4"] for row in rows),
        "beneficial_count": sum(value > 0.0 for value in gains),
        "harmful_count": sum(value < 0.0 for value in gains),
        "mean_gain_vs_s4_seconds": sum(gains) / count if count else 0.0,
        "per_horizon": per_horizon,
        "minimum_positive_mean_horizon_seconds": (
            min(useful_horizons) if useful_horizons else None
        ),
        "perfect_action_ceiling_mean_gain_seconds": (
            sum(ceilings) / count if count else 0.0
        ),
        "heuristic_inputs": list(SUMMARY_FIELDS),
        "perfect_action_ceiling_is_not_a_heuristic_input": True,
        "rows": rows,
    }


def _read_groups(path: Path) -> list[Mapping[str, Any]]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping) and isinstance(payload.get("groups"), list):
        return payload["groups"]
    raise ValueError("input must be JSONL, a JSON list, or {'groups': [...]}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the fixed G22 local-information heuristic screen"
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = summarize(_read_groups(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
