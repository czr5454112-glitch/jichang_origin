#!/usr/bin/env python3
"""Build a small complete local Route action-set dataset for G21.

The native G20 profile remains Source A0 + Route S4 + Merge J2 + E2.  This
runner samples a few existing I3 boundaries, executes every non-S4 legal edge
and one native I4 WAIT from the identical pre-action state, then persists only
groups for which every real treatment completed safely.  It does not train or
export a model and never persists native pair rows.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import run_g4irsf20_route_counterfactuals as g20


RESEARCH_PROFILE = "G20_S4_J2"
TARGET_SCHEMA = "czr005.g4irsf21.route_action_target.v1"
DATASET_SCHEMA = "czr005.g4irsf21.route_action_set.v1"
SUMMARY_SCHEMA = "czr005.g4irsf21.route_action_set_summary.v1"
COMPLETE_PAIR_STATUS = "ACTION_CHANGED_HORIZON_COMPLETE"
ACTION_KINDS = ("NEXT_EDGE", "WAIT")
UTILITY_UNIT = "seconds"
UTILITY_SEMANTICS = "BASELINE_MINUS_TREATMENT_COMPLETION_SECONDS"

DEFAULT_DATASET = ROOT / "artifacts/datasets/g4irsf21_route_action_sets.jsonl"
DEFAULT_TABLE = ROOT / "outputs/tables/g4irsf21_route_action_sets.json"
DEFAULT_REPORT = ROOT / "outputs/reports/g4irsf21_route_action_sets.md"


class RouteActionSetError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RouteActionSetError(message)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_text(path, json.dumps(_plain(value), indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    _atomic_text(
        path,
        "".join(json.dumps(_plain(row), sort_keys=True) + "\n" for row in rows),
    )


def _text(row: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if isinstance(value, str) and value:
            return value
    raise RouteActionSetError(f"missing {'/'.join(names)}")


def normalize_i3_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the compact G21 additions to one G20 I3 census row."""

    _require(row.get("kind") in {"I3", "I3_NEXT_EDGE"}, "expected I3 census row")
    baseline = row.get("baseline_next_node")
    legal = row.get("legal_next_edges")
    _require(type(baseline) is int, "I3 baseline_next_node missing")
    _require(
        isinstance(legal, list)
        and len(legal) >= 2
        and all(type(node) is int for node in legal),
        "I3 legal_next_edges must contain at least two integer nodes",
    )
    _require(len(set(legal)) == len(legal), "I3 legal_next_edges contains duplicates")
    _require(baseline in legal, "S4 baseline is absent from legal_next_edges")
    _require(row.get("wait_available") is True, "I3 row lacks its legal I4 WAIT sibling")
    wait_age = row.get("wait_age_seconds")
    _require(
        isinstance(wait_age, (int, float))
        and not isinstance(wait_age, bool)
        and math.isfinite(float(wait_age)),
        "I3 wait_age_seconds must be finite",
    )
    event_ordinal = row.get("event_ordinal")
    runtime_bag_id = row.get("runtime_bag_id")
    _require(type(event_ordinal) is int and event_ordinal >= 0, "invalid event_ordinal")
    _require(type(runtime_bag_id) is int and runtime_bag_id >= 0, "invalid runtime_bag_id")
    return {
        "population_group_id": _text(row, "population_group_id", "population_group_sha256"),
        "population_selection_id": _text(
            row,
            "population_selection_id",
            "skeleton_selection_sha256",
            "skeleton_id",
        ),
        "event_ordinal": event_ordinal,
        "runtime_bag_id": runtime_bag_id,
        "baseline_next_node": baseline,
        "legal_next_edges": list(legal),
        "wait_available": True,
        "wait_age_seconds": float(wait_age),
        "normal_flow": row.get("normal_flow") if type(row.get("normal_flow")) is bool else None,
    }


def select_screening_groups(
    scan: Mapping[str, Any],
    *,
    target_groups: int = 16,
    long_wait_target: int = 8,
    long_wait_seconds: float = 30.0,
    screening_multiplier: float = 1.5,
) -> list[dict[str, Any]]:
    _require(scan.get("census_complete") is True, "native I3 census did not complete")
    _require(type(target_groups) is int and target_groups > 0, "target_groups must be positive")
    _require(0 <= long_wait_target <= target_groups, "invalid long_wait_target")
    _require(
        math.isfinite(long_wait_seconds) and long_wait_seconds >= 0.0,
        "invalid long_wait_seconds",
    )
    _require(
        math.isfinite(screening_multiplier) and 1.0 <= screening_multiplier <= 1.5,
        "screening_multiplier must be in [1.0, 1.5]",
    )
    skeletons = scan.get("skeletons")
    _require(isinstance(skeletons, list), "native census omitted skeletons")
    rows = [
        normalize_i3_row(row)
        for row in skeletons
        if isinstance(row, Mapping) and row.get("kind") in {"I3", "I3_NEXT_EDGE"}
    ]
    rows.sort(key=lambda row: (row["event_ordinal"], row["runtime_bag_id"]))
    seen: set[tuple[str, str, int]] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = (
            row["population_group_id"],
            row["population_selection_id"],
            row["event_ordinal"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)
    screened_limit = min(len(unique), math.ceil(target_groups * screening_multiplier))
    short_wait_target = target_groups - long_wait_target
    long_limit = min(screened_limit, math.ceil(long_wait_target * screening_multiplier))
    short_limit = min(
        screened_limit - long_limit,
        math.ceil(short_wait_target * screening_multiplier),
    )
    long_rows = [row for row in unique if row["wait_age_seconds"] >= long_wait_seconds]
    short_rows = [row for row in unique if row["wait_age_seconds"] < long_wait_seconds]
    chosen = long_rows[:long_limit] + short_rows[:short_limit]
    chosen_keys = {
        (row["population_group_id"], row["population_selection_id"], row["event_ordinal"])
        for row in chosen
    }
    chosen.extend(
        row
        for row in unique
        if (
            row["population_group_id"],
            row["population_selection_id"],
            row["event_ordinal"],
        )
        not in chosen_keys
    )
    chosen = chosen[:screened_limit]
    chosen.sort(key=lambda row: (row["event_ordinal"], row["runtime_bag_id"]))
    for index, row in enumerate(chosen):
        row["screening_group_index"] = index
    return chosen


def build_action_targets(group: Mapping[str, Any]) -> list[dict[str, Any]]:
    common = {
        "schema": TARGET_SCHEMA,
        "population_group_id": str(group["population_group_id"]),
        "population_selection_id": str(group["population_selection_id"]),
        "event_ordinal": int(group["event_ordinal"]),
        "horizon": "H_bag",
    }
    baseline = int(group["baseline_next_node"])
    targets = [
        {**common, "action_kind": "NEXT_EDGE", "selected_next_node": int(node)}
        for node in group["legal_next_edges"]
        if int(node) != baseline
    ]
    targets.append({**common, "action_kind": "WAIT"})
    return targets


def _target_identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    action_kind = row.get("action_kind")
    _require(action_kind in ACTION_KINDS, "target action_kind drifted")
    selected = row.get("selected_next_node")
    if action_kind == "NEXT_EDGE":
        _require(type(selected) is int, "NEXT_EDGE target lacks selected_next_node")
    else:
        _require("selected_next_node" not in row or selected is None, "WAIT fabricated an edge")
        selected = None
    return (
        row.get("target_schema", row.get("schema")),
        row.get("population_group_id"),
        row.get("population_selection_id"),
        row.get("event_ordinal"),
        row.get("horizon"),
        action_kind,
        selected,
    )


def _pair_failure(pair: Mapping[str, Any]) -> str | None:
    checks = (
        (pair.get("pair_status") == COMPLETE_PAIR_STATUS, str(pair.get("pair_status") or "PAIR_STATUS_MISSING")),
        (pair.get("same_state_start") is True, "SAME_STATE_START_FAILED"),
        (pair.get("action_changed") is True, "ACTION_NOT_CHANGED"),
        (pair.get("pair_complete") is True, "HORIZON_INCOMPLETE"),
        (pair.get("live_safety_pass") is True, "LIVE_SAFETY_FAILED"),
    )
    return next((reason for passed, reason in checks if not passed), None)


def _completion_delta(pair: Mapping[str, Any]) -> float:
    direct = pair.get("direct_completion_delta_seconds")
    if isinstance(direct, (int, float)) and not isinstance(direct, bool):
        value = float(direct)
        _require(math.isfinite(value), "non-finite direct completion delta")
        return value
    deltas = pair.get("affected_bag_deltas")
    _require(isinstance(deltas, list) and deltas, "pair omitted affected completion delta")
    values = [
        float(row["completion_delta_seconds"])
        for row in deltas
        if isinstance(row, Mapping)
        and isinstance(row.get("completion_delta_seconds"), (int, float))
        and not isinstance(row.get("completion_delta_seconds"), bool)
        and math.isfinite(float(row["completion_delta_seconds"]))
    ]
    _require(values, "pair has no finite affected completion delta")
    return sum(values) / len(values)


def _route_observation(pair: Mapping[str, Any]) -> Mapping[str, Any]:
    observation = pair.get("route_observation")
    if not isinstance(observation, Mapping):
        descriptor = pair.get("resolved_execution_descriptor")
        if isinstance(descriptor, Mapping):
            observation = descriptor.get("route_observation")
    _require(isinstance(observation, Mapping), "NEXT_EDGE pair omitted Route observation")
    return observation


def _intervened_task_id(pair: Mapping[str, Any]) -> int:
    descriptor = pair.get("resolved_execution_descriptor")
    _require(isinstance(descriptor, Mapping), "complete pair omitted its descriptor")
    runtime_bag_id = descriptor.get("runtime_bag_id")
    _require(type(runtime_bag_id) is int, "complete pair omitted runtime_bag_id")
    baseline = pair.get("baseline")
    outcomes = baseline.get("affected_bag_outcomes") if isinstance(baseline, Mapping) else None
    _require(isinstance(outcomes, list), "complete pair omitted baseline outcomes")
    matching = [
        outcome.get("task_id")
        for outcome in outcomes
        if isinstance(outcome, Mapping)
        and outcome.get("runtime_bag_id") == runtime_bag_id
        and type(outcome.get("task_id")) is int
    ]
    _require(len(matching) == 1, "intervened segment task_id is not unique")
    return int(matching[0])


def compact_action_group(
    group: Mapping[str, Any],
    pair_by_identity: Mapping[tuple[Any, ...], Mapping[str, Any]],
) -> tuple[dict[str, Any] | None, list[str]]:
    targets = build_action_targets(group)
    failures: list[str] = []
    resolved: list[tuple[dict[str, Any], Mapping[str, Any]]] = []
    for target in targets:
        pair = pair_by_identity.get(_target_identity(target))
        if pair is None:
            failures.append("PAIR_MISSING")
            continue
        failure = _pair_failure(pair)
        if failure is not None:
            failures.append(failure)
            continue
        resolved.append((target, pair))
    if failures or len(resolved) != len(targets):
        return None, failures or ["PAIR_SET_INCOMPLETE"]

    legal = [int(node) for node in group["legal_next_edges"]]
    baseline = int(group["baseline_next_node"])
    common_features: list[Mapping[str, Any]] | None = None
    common_normal_flow: bool | None = None
    utilities: dict[tuple[str, int | None], float] = {}
    task_ids: set[int] = set()
    for target, pair in resolved:
        task_ids.add(_intervened_task_id(pair))
        action_kind = str(target["action_kind"])
        selected = target.get("selected_next_node")
        utilities[(action_kind, int(selected) if type(selected) is int else None)] = -_completion_delta(pair)
        if action_kind == "WAIT":
            continue
        observation = _route_observation(pair)
        nodes = observation.get("candidate_next_nodes")
        candidates = observation.get("candidate_observations")
        baseline_index = observation.get("baseline_candidate_index")
        treatment_index = observation.get("treatment_candidate_index")
        _require(nodes == legal, "Route observation legal edge order drifted")
        _require(
            isinstance(candidates, list)
            and len(candidates) == len(legal)
            and all(isinstance(row, Mapping) for row in candidates),
            "Route observation candidate mappings drifted",
        )
        _require(
            type(baseline_index) is int
            and legal[baseline_index] == baseline,
            "Route observation S4 index drifted",
        )
        _require(
            type(treatment_index) is int
            and legal[treatment_index] == int(selected),
            "Route observation treatment index drifted",
        )
        normalized = [dict(_plain(row)) for row in candidates]
        normal_flow = observation.get("normal_flow")
        _require(type(normal_flow) is bool, "Route observation normal_flow missing")
        if common_features is None:
            common_features = normalized
            common_normal_flow = normal_flow
        else:
            _require(common_features == normalized, "same-state edge observations disagree")
            _require(common_normal_flow == normal_flow, "normal_flow differs within group")
    _require(common_features is not None, "complete group has no edge observation")
    _require(len(task_ids) == 1, "same-state actions disagree on original task_id")

    candidates_out: list[dict[str, Any]] = []
    s4_index = legal.index(baseline)
    for index, node in enumerate(legal):
        candidates_out.append(
            {
                "action_kind": "NEXT_EDGE",
                "selected_next_node": node,
                "legal": True,
                "native_features": common_features[index],
                "utility": 0.0 if node == baseline else utilities[("NEXT_EDGE", node)],
            }
        )
    candidates_out.append(
        {
            "action_kind": "WAIT",
            "selected_next_node": None,
            "legal": True,
            "native_features": None,
            "utility": utilities[("WAIT", None)],
        }
    )
    return {
        "schema_id": DATASET_SCHEMA,
        "choice_group_id": f"g21-route-{int(group['screening_group_index'])}",
        "split_group": task_ids.pop(),
        "normal_flow": common_normal_flow,
        "wait_age_seconds": float(group["wait_age_seconds"]),
        "source_scale": 1,
        "horizon": "H_bag",
        "utility_unit": UTILITY_UNIT,
        "utility_semantics": UTILITY_SEMANTICS,
        "s4_index": s4_index,
        "primary_pair_labeled": True,
        "full_legal_action_set_labeled": True,
        "wait_action_labeled": True,
        "label_scope": "AFFECTED_RUNTIME_SEGMENT_COMPLETION_FULL_LOCAL_ACTION_SET",
        "candidates": candidates_out,
    }, []


def _choose_final_groups(
    groups: Sequence[dict[str, Any]],
    *,
    target_groups: int,
    long_wait_target: int,
    long_wait_seconds: float,
) -> tuple[list[dict[str, Any]], bool]:
    ordered = sorted(groups, key=lambda row: int(row["choice_group_id"].rsplit("-", 1)[1]))
    long_rows = [row for row in ordered if row["wait_age_seconds"] >= long_wait_seconds]
    short_rows = [row for row in ordered if row["wait_age_seconds"] < long_wait_seconds]
    chosen = long_rows[:long_wait_target]
    chosen.extend(short_rows[: target_groups - long_wait_target])
    chosen.sort(key=lambda row: int(row["choice_group_id"].rsplit("-", 1)[1]))
    target_met = (
        len(chosen) == target_groups
        and sum(row["wait_age_seconds"] >= long_wait_seconds for row in chosen)
        == long_wait_target
    )
    return chosen, target_met


def render_report(summary: Mapping[str, Any]) -> str:
    next_edge_labels = summary["persisted_action_label_counts_by_kind"].get(
        "NEXT_EDGE", {}
    )
    wait_labels = summary["persisted_action_label_counts_by_kind"].get("WAIT", {})
    next_edge_text = ", ".join(
        f"{label}={count}" for label, count in sorted(next_edge_labels.items())
    )
    wait_text = ", ".join(
        f"{label}={count}" for label, count in sorted(wait_labels.items())
    )
    return "\n".join(
        [
            "# G4IRSF21 complete local Route action sets",
            "",
            f"Status: **{summary['status']}**",
            "",
            "The controller is unchanged: `Source A0 + Route S4 + Merge J2 + E2`.",
            "Each retained group labels S4, every other shield-legal one-hop edge,",
            "and one native I4 WAIT from the same pre-action state.",
            "",
            f"- requested complete H_bag groups: {summary['targets']['groups']}",
            f"- screened groups: {summary['counts']['screened_groups']}",
            f"- fully complete groups before quota: {summary['counts']['fully_complete_groups']}",
            f"- persisted complete groups: {summary['counts']['persisted_groups']}",
            f"- distinct original tasks: {summary['counts']['unique_split_group_count']}",
            f"- executed real treatments: {summary['counts']['executed_treatments']}",
            f"- NEXT_EDGE labels: `{next_edge_text}`",
            f"- WAIT labels: `{wait_text}`",
            "",
            "Utilities are measured in seconds as baseline completion minus treatment",
            "completion; positive values are better.",
            "",
            "WAIT has no fabricated edge feature vector. No native pair rows, full-system",
            "outcomes, learned model, or runtime policy are persisted or promoted.",
            (
                f"The {summary['counts']['persisted_groups']} groups cover "
                f"{summary['counts']['unique_split_group_count']} distinct original tasks. "
                "The `split_group` metadata enables"
            ),
            "a later grouped split to keep one task's runtime segments together.",
            "Selection keeps the earliest eligible events within each wait stratum, so this",
            "is a small 1x H_bag contract check, not a representative performance sample.",
            "Any future learning campaign must use grouped-even sampling by original task;",
            "these rows do not support a learned-policy or performance claim.",
            "",
        ]
    )


def run_campaign(
    *,
    root: Path = ROOT,
    binary: Path | None = None,
    target_groups: int = 16,
    long_wait_target: int = 8,
    long_wait_seconds: float = 30.0,
    screening_multiplier: float = 1.5,
    dataset_path: Path = DEFAULT_DATASET,
    table_path: Path = DEFAULT_TABLE,
    report_path: Path = DEFAULT_REPORT,
    module: Any | None = None,
    native_arguments: Sequence[Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if module is None:
        _require(binary is not None, "binary is required without an injected native module")
        module = g20._load_native(binary)
    if native_arguments is None:
        native_arguments = g20._native_arguments(root)
    scan = g20.scan_full_census(module, native_arguments)
    screened = select_screening_groups(
        scan,
        target_groups=target_groups,
        long_wait_target=long_wait_target,
        long_wait_seconds=long_wait_seconds,
        screening_multiplier=screening_multiplier,
    )
    plans = [(group, build_action_targets(group)) for group in screened]
    targets = [target for _group, action_targets in plans for target in action_targets]
    _require(targets, "screening produced no G21 action targets")
    payload = module.g4irsf15_run_causal_target_pairs_from_records(
        *native_arguments,
        targets,
        RESEARCH_PROFILE,
    )
    pairs = payload.get("pairs") if isinstance(payload, Mapping) else None
    _require(isinstance(pairs, list), "native action-set run omitted pairs")
    pair_by_identity: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for pair in pairs:
        _require(isinstance(pair, Mapping), "native pair row is not an object")
        identity = _target_identity(pair)
        _require(identity not in pair_by_identity, "native pair identity is duplicated")
        pair_by_identity[identity] = pair

    complete_groups: list[dict[str, Any]] = []
    drop_reasons: Counter[str] = Counter()
    for group, _action_targets in plans:
        compact, failures = compact_action_group(group, pair_by_identity)
        if compact is None:
            drop_reasons.update(set(failures))
        else:
            complete_groups.append(compact)
    selected, target_met = _choose_final_groups(
        complete_groups,
        target_groups=target_groups,
        long_wait_target=long_wait_target,
        long_wait_seconds=long_wait_seconds,
    )
    action_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    labels_by_kind = {kind: Counter() for kind in ACTION_KINDS}
    for group in selected:
        for candidate in group["candidates"]:
            action_kind = str(candidate["action_kind"])
            action_counts[action_kind] += 1
            utility = float(candidate["utility"])
            label = (
                "BENEFICIAL"
                if utility > 1e-9
                else "HARMFUL"
                if utility < -1e-9
                else "NEUTRAL"
            )
            label_counts[label] += 1
            labels_by_kind[action_kind][label] += 1
    summary = {
        "schema": SUMMARY_SCHEMA,
        "status": "COMPLETE_ACTION_SET_TARGET_MET" if target_met else "ACTION_SET_SHORTFALL",
        "decision": "DATA_ONLY_NO_MODEL_TRAINED",
        "design": {
            "controller": "Source A0 + Route S4 + Merge J2 + E2",
            "target_schema": TARGET_SCHEMA,
            "source_scale": 1,
            "horizon": "H_bag",
            "screening_multiplier": screening_multiplier,
            "raw_native_pairs_persisted": False,
            "wait_feature_semantics": "NONE_ACTION_KIND_ONLY",
            "utility_unit": UTILITY_UNIT,
            "utility_semantics": UTILITY_SEMANTICS,
        },
        "targets": {
            "groups": target_groups,
            "long_wait_groups": long_wait_target,
            "long_wait_seconds": long_wait_seconds,
        },
        "counts": {
            "i3_census_groups": sum(
                isinstance(row, Mapping) and row.get("kind") in {"I3", "I3_NEXT_EDGE"}
                for row in scan.get("skeletons", [])
            ),
            "screened_groups": len(screened),
            "executed_treatments": len(targets),
            "returned_pairs": len(pairs),
            "fully_complete_groups": len(complete_groups),
            "persisted_groups": len(selected),
            "persisted_long_wait_groups": sum(
                group["wait_age_seconds"] >= long_wait_seconds for group in selected
            ),
            "persisted_short_wait_groups": sum(
                group["wait_age_seconds"] < long_wait_seconds for group in selected
            ),
            "unique_split_group_count": len(
                {group["split_group"] for group in selected}
            ),
        },
        "dropped_group_reason_counts": dict(sorted(drop_reasons.items())),
        "persisted_action_kind_counts": dict(sorted(action_counts.items())),
        "persisted_action_label_counts": dict(sorted(label_counts.items())),
        "persisted_action_label_counts_by_kind": {
            kind: dict(sorted(counts.items()))
            for kind, counts in labels_by_kind.items()
        },
        "claim_boundary": (
            "Complete local one-hop action labels only; no H_system, model, closed loop, "
            "full 4x completion, or v2-safe gap-closure claim."
        ),
    }
    _write_jsonl(dataset_path, selected)
    _write_json(table_path, summary)
    _atomic_text(report_path, render_report(summary))
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--target-groups", type=int, default=16)
    parser.add_argument("--long-wait-target", type=int, default=8)
    parser.add_argument("--long-wait-seconds", type=float, default=30.0)
    parser.add_argument("--screening-multiplier", type=float, default=1.5)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args(argv)


def _rooted(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    try:
        summary = run_campaign(
            root=root,
            binary=_rooted(root, args.binary),
            target_groups=args.target_groups,
            long_wait_target=args.long_wait_target,
            long_wait_seconds=args.long_wait_seconds,
            screening_multiplier=args.screening_multiplier,
            dataset_path=_rooted(root, args.dataset),
            table_path=_rooted(root, args.table),
            report_path=_rooted(root, args.report),
        )
        print(json.dumps({"status": summary["status"], **summary["counts"]}, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError, RouteActionSetError) as exc:
        print(f"G21 Route action-set campaign failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
