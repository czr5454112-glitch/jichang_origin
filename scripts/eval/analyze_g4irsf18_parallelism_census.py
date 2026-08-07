from __future__ import annotations

import argparse
import gzip
import json
import math
import struct
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO


SCHEMA = "czr005.g4irsf18.bolt_parallelism_census.v1"
METHOD = "exact_bit_timestamp_merge_local_scoring_greedy_pack"


class ParallelismCensusError(RuntimeError):
    pass


def _timestamp_bits(value: float) -> str:
    return struct.pack(">d", value).hex()


@contextmanager
def _open_text(path: Path) -> Iterator[TextIO]:
    if path.suffix == ".zst":
        try:
            import zstandard
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ParallelismCensusError(
                "zstandard is required to read .zst traces"
            ) from exc
        with zstandard.open(path, "rt", encoding="utf-8") as handle:
            yield handle
        return
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            yield handle
        return
    with path.open("r", encoding="utf-8") as handle:
        yield handle


def load_opportunities(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        raise ParallelismCensusError(f"trace does not exist: {path}")
    opportunities: dict[int, dict[str, object]] = {}
    candidate_row_count = 0
    with _open_text(path) as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            candidate_row_count += 1
            try:
                row = json.loads(line)
                opportunity_id = int(row["opportunity_id"])
                event_time = float(row["event_time"])
                destination_node = int(row["destination_node"])
                candidate_count = int(row["candidate_count"])
                upstream_node = int(row["upstream_node"])
                request_id = int(row["candidate_request_id"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ParallelismCensusError(
                    f"invalid candidate row at line {line_number}: {exc}"
                ) from exc
            if candidate_count <= 0:
                raise ParallelismCensusError(
                    f"candidate_count must be positive at line {line_number}"
                )
            if not math.isfinite(event_time):
                raise ParallelismCensusError(
                    f"event_time must be finite at line {line_number}"
                )
            timestamp_bits = _timestamp_bits(event_time)
            opportunity = opportunities.setdefault(
                opportunity_id,
                {
                    "opportunity_id": opportunity_id,
                    "event_time": event_time,
                    "timestamp_bits": timestamp_bits,
                    "destination_node": destination_node,
                    "candidate_count": candidate_count,
                    "upstream_nodes": set(),
                    "candidate_request_ids": set(),
                },
            )
            identity = (
                opportunity["timestamp_bits"],
                opportunity["destination_node"],
                opportunity["candidate_count"],
            )
            if identity != (timestamp_bits, destination_node, candidate_count):
                raise ParallelismCensusError(
                    "candidate rows disagree within opportunity "
                    f"{opportunity_id} at line {line_number}"
                )
            upstream_nodes = opportunity["upstream_nodes"]
            candidate_request_ids = opportunity["candidate_request_ids"]
            assert isinstance(upstream_nodes, set)
            assert isinstance(candidate_request_ids, set)
            upstream_nodes.add(upstream_node)
            candidate_request_ids.add(request_id)

    if not opportunities:
        raise ParallelismCensusError("trace contains no candidate rows")

    result: list[dict[str, object]] = []
    for opportunity_id, opportunity in sorted(opportunities.items()):
        request_ids = opportunity["candidate_request_ids"]
        upstream_nodes = opportunity["upstream_nodes"]
        candidate_count = int(opportunity["candidate_count"])
        assert isinstance(request_ids, set)
        assert isinstance(upstream_nodes, set)
        if len(request_ids) != candidate_count:
            raise ParallelismCensusError(
                f"opportunity {opportunity_id} declares {candidate_count} "
                f"candidates but stores {len(request_ids)} distinct request rows"
            )
        result.append(
            {
                **opportunity,
                "upstream_nodes": sorted(upstream_nodes),
                "candidate_request_ids": sorted(request_ids),
            }
        )
    if sum(int(row["candidate_count"]) for row in result) != candidate_row_count:
        raise ParallelismCensusError(
            "candidate row accounting does not match opportunity cardinalities"
        )
    return result


def resource_keys(opportunity: dict[str, object]) -> frozenset[tuple[object, ...]]:
    destination = int(opportunity["destination_node"])
    upstream_nodes = [int(value) for value in opportunity["upstream_nodes"]]
    request_ids = [
        int(value) for value in opportunity["candidate_request_ids"]
    ]
    # Destination and upstream roles share the same JunctionState namespace in
    # the live runtime.  Keep one role-unified key so cross-role aliasing cannot
    # inflate the local-scoring pack estimate.
    keys: set[tuple[object, ...]] = {("junction", destination)}
    keys.update(("junction", upstream) for upstream in upstream_nodes)
    keys.update(("request", request_id) for request_id in request_ids)
    keys.update(
        ("directed_edge", upstream, destination)
        for upstream in upstream_nodes
    )
    return frozenset(keys)


def _nearest_rank(values: list[int], probability: float) -> int:
    ordered = sorted(values)
    index = math.ceil(len(ordered) * probability) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _histogram(values: list[int]) -> dict[str, int]:
    return {
        str(value): count
        for value, count in sorted(Counter(values).items())
    }


def summarize_timestamp_buckets(
    opportunities: list[dict[str, object]],
) -> dict[str, object]:
    buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    for opportunity in opportunities:
        buckets[str(opportunity["timestamp_bits"])].append(opportunity)

    bucket_rows: list[dict[str, object]] = []
    conflict_pair_count = 0
    for timestamp_bits, members in sorted(buckets.items()):
        members.sort(key=lambda row: int(row["opportunity_id"]))
        member_keys = [resource_keys(member) for member in members]
        local_conflict_pairs = sum(
            not member_keys[left].isdisjoint(member_keys[right])
            for left in range(len(members))
            for right in range(left + 1, len(members))
        )
        conflict_pair_count += local_conflict_pairs
        used_keys: set[tuple[object, ...]] = set()
        selected_ids: list[int] = []
        for member, keys in zip(members, member_keys, strict=True):
            if used_keys.isdisjoint(keys):
                used_keys.update(keys)
                selected_ids.append(int(member["opportunity_id"]))
        bucket_rows.append(
            {
                "timestamp_bits": timestamp_bits,
                "event_time": float(members[0]["event_time"]),
                "timestamp_bucket_size": len(members),
                "distinct_destination_count": len(
                    {int(member["destination_node"]) for member in members}
                ),
                "local_scoring_conflict_pair_count": local_conflict_pairs,
                "greedy_local_scoring_width": len(selected_ids),
                "greedy_selected_opportunity_ids": selected_ids,
            }
        )

    sizes = [int(row["timestamp_bucket_size"]) for row in bucket_rows]
    widths = [int(row["greedy_local_scoring_width"]) for row in bucket_rows]
    multi_scoring_rows = [
        row for row in bucket_rows if int(row["greedy_local_scoring_width"]) > 1
    ]
    top = sorted(
        bucket_rows,
        key=lambda row: (
            -int(row["greedy_local_scoring_width"]),
            -int(row["timestamp_bucket_size"]),
            str(row["timestamp_bits"]),
        ),
    )[:10]
    return {
        "opportunity_count": len(opportunities),
        "timestamp_bucket_count": len(bucket_rows),
        "timestamp_bucket_size": {
            "max": max(sizes),
            "p50": _nearest_rank(sizes, 0.50),
            "p95": _nearest_rank(sizes, 0.95),
            "p99": _nearest_rank(sizes, 0.99),
            "histogram": _histogram(sizes),
            "buckets_gt1": sum(value > 1 for value in sizes),
        },
        "greedy_local_scoring_width": {
            "max": max(widths),
            "p50": _nearest_rank(widths, 0.50),
            "p95": _nearest_rank(widths, 0.95),
            "p99": _nearest_rank(widths, 0.99),
            "histogram": _histogram(widths),
            "buckets_gt1": len(multi_scoring_rows),
        },
        "opportunities_in_multi_scoring_buckets": sum(
            int(row["timestamp_bucket_size"]) for row in multi_scoring_rows
        ),
        "opportunity_share_in_multi_scoring_buckets": sum(
            int(row["timestamp_bucket_size"]) for row in multi_scoring_rows
        )
        / len(opportunities),
        "local_scoring_conflict_pair_count": conflict_pair_count,
        "top_timestamp_buckets": top,
    }


def _default_companion_result(path: Path) -> Path | None:
    name = path.name
    for suffix in (".opportunities.jsonl.zst", ".opportunities.jsonl.gz"):
        if name.endswith(suffix):
            candidate = path.with_name(name[: -len(suffix)] + ".json")
            return candidate if candidate.is_file() else None
    return None


def _trace_completeness(
    companion_result: Path | None,
    *,
    candidate_row_count: int,
    opportunity_count: int,
    eligible_count: int,
) -> dict[str, object]:
    if companion_result is None:
        return {"status": "NOT_CHECKED_NO_COMPANION_RESULT"}
    try:
        payload = json.loads(companion_result.read_text(encoding="utf-8"))
        counters = payload["counters"]
        observed = {
            "trace_total_count": int(
                counters["merge_grant_opportunity_trace_total_count"]
            ),
            "trace_stored_count": int(
                counters["merge_grant_opportunity_trace_stored_count"]
            ),
            "trace_dropped_count": int(
                counters["merge_grant_opportunity_trace_dropped_count"]
            ),
            "model_opportunity_count": int(
                counters["g4irsf18_merge_model_opportunity_count"]
            ),
            "model_eligible_count": int(
                counters["g4irsf18_merge_model_eligible_count"]
            ),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ParallelismCensusError(
            f"invalid companion result counters: {companion_result}"
        ) from exc
    expected = {
        "trace_total_count": candidate_row_count,
        "trace_stored_count": candidate_row_count,
        "trace_dropped_count": 0,
        "model_opportunity_count": opportunity_count,
        "model_eligible_count": eligible_count,
    }
    if observed != expected:
        raise ParallelismCensusError(
            f"companion trace completeness mismatch: observed={observed}, "
            f"expected={expected}"
        )
    return {
        "status": "PASS_COMPLETE_ZERO_DROPPED",
        "companion_result": companion_result.as_posix(),
        **observed,
    }


def build_census(
    path: Path,
    companion_result: Path | None = None,
) -> dict[str, object]:
    opportunities = load_opportunities(path)
    eligible = [
        row for row in opportunities if int(row["candidate_count"]) > 1
    ]
    candidate_row_count = sum(
        int(row["candidate_count"]) for row in opportunities
    )
    companion = companion_result or _default_companion_result(path)
    return {
        "schema": SCHEMA,
        "status": "TRACE_BUCKET_CENSUS_COMPLETE_NOT_EXECUTABLE_FRONTIER",
        "method": METHOD,
        "input_trace": path.as_posix(),
        "trace_completeness": _trace_completeness(
            companion,
            candidate_row_count=candidate_row_count,
            opportunity_count=len(opportunities),
            eligible_count=len(eligible),
        ),
        "local_scoring_resource_key_contract": [
            "role_unified_junction_node_for_destination_and_upstream",
            "candidate_request_id",
            "candidate_directed_edge",
        ],
        "excluded_serial_commit_lanes": [
            "j7_coverage_and_applied_counters",
            "j7_kill_switch_and_policy_epoch",
            "bag_and_calendar_generation_validation",
            "global_event_heap_and_event_sequence",
            "telemetry_and_summary_publication",
        ],
        "candidate_request_id_assumption": (
            "request id proxies one bag lifecycle because the runtime permits "
            "at most one pending merge request per bag"
        ),
        "candidate_row_count": candidate_row_count,
        "all_merge_opportunities": summarize_timestamp_buckets(opportunities),
        "eligible_multi_candidate_opportunities": (
            summarize_timestamp_buckets(eligible) if eligible else None
        ),
        "claim_boundary": [
            "Trace contains merge opportunities only; route and source are not measured.",
            "Timestamp buckets are not executable event frontiers: event sequence, frontier epoch, parent causality and dynamic PIBT footprints are absent.",
            "Resource keys cover local scoring only; global policy state and commit lanes remain canonically serial.",
            "Greedy local-scoring width is not a maximum independent set or a commit width.",
            "Exact-bit grouping is stricter than the runtime's epsilon-based same-timestamp relation.",
            "Exact-bit timestamp co-occurrence does not establish wall-time speedup or physical capacity.",
        ],
    }


def render_markdown(census: dict[str, object]) -> str:
    all_rows = census["all_merge_opportunities"]
    eligible = census["eligible_multi_candidate_opportunities"]
    assert isinstance(all_rows, dict)
    all_size = all_rows["timestamp_bucket_size"]
    all_width = all_rows["greedy_local_scoring_width"]
    assert isinstance(all_size, dict) and isinstance(all_width, dict)
    lines = [
        "# G4IRSF18 BOLT-P trace parallelism census",
        "",
        "Status: **`TRACE_BUCKET_CENSUS_COMPLETE_NOT_EXECUTABLE_FRONTIER`**.",
        "",
        "This is the zero-thread M0 census proposed by the BOLT-P method. It",
        "groups merge opportunity rows by exact IEEE-754 timestamp and builds a",
        "stable local-scoring pack using role-unified junction, request and",
        "directed-edge keys. It is a screening estimate of micro-batch potential,",
        "not an executable event frontier or multi-core execution result.",
        "",
        "| Scope | Opportunities | Exact-bit time buckets | Max bucket | P95 bucket | Max local-scoring pack | P95 pack | Opportunity share in multi-score buckets |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| All merge | {all_rows['opportunity_count']:,} | "
            f"{all_rows['timestamp_bucket_count']:,} | {all_size['max']:,} | "
            f"{all_size['p95']:,} | {all_width['max']:,} | "
            f"{all_width['p95']:,} | "
            f"{100.0 * float(all_rows['opportunity_share_in_multi_scoring_buckets']):.3f}% |"
        ),
    ]
    if isinstance(eligible, dict):
        eligible_size = eligible["timestamp_bucket_size"]
        eligible_width = eligible["greedy_local_scoring_width"]
        assert isinstance(eligible_size, dict) and isinstance(eligible_width, dict)
        lines.append(
            f"| Multi-candidate only | {eligible['opportunity_count']:,} | "
            f"{eligible['timestamp_bucket_count']:,} | {eligible_size['max']:,} | "
            f"{eligible_size['p95']:,} | {eligible_width['max']:,} | "
            f"{eligible_width['p95']:,} | "
            f"{100.0 * float(eligible['opportunity_share_in_multi_scoring_buckets']):.3f}% |"
        )
    completeness = census["trace_completeness"]
    assert isinstance(completeness, dict)
    lines.extend(
        [
            "",
            "Trace completeness: "
            f"**`{completeness['status']}`**"
            + (
                f" (`{completeness.get('trace_stored_count', 0):,}` stored, "
                f"`{completeness.get('trace_dropped_count', 0):,}` dropped)."
                if completeness["status"] == "PASS_COMPLETE_ZERO_DROPPED"
                else "."
            ),
            "",
            "## Interpretation",
            "",
            "- A pack above one means rows in that timestamp bucket have disjoint",
            "  declared local-scoring keys. It does not prove they were simultaneously",
            "  live in the event heap or that their commits commute.",
            "- The narrow p95 offers little merge-only exact-bit batching opportunity",
            "  in this trace; route/source instrumentation, event-loop cost and",
            "  process-isolated rollout throughput should be measured next.",
            "- J7 coverage, kill-switch state, generation validation, telemetry and",
            "  event publication are intentionally excluded from the scoring keys and",
            "  must remain in the canonical serial coordinator.",
            "",
            "## Claim boundary",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in census["claim_boundary"])
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure an exact-bit BOLT-P merge local-scoring proxy."
    )
    parser.add_argument("trace", type=Path)
    parser.add_argument("--companion-result", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--report-output", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    census = build_census(args.trace, args.companion_result)
    payload = json.dumps(census, indent=2, sort_keys=True) + "\n"
    if args.json_output is None:
        print(payload, end="")
    else:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(payload, encoding="utf-8")
    if args.report_output is not None:
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text(render_markdown(census), encoding="utf-8")


if __name__ == "__main__":
    main()
