"""Observed source-clock decomposition; never a counterfactual causal estimate.

Each run is streamed once and large route/reservation arrays are discarded.
The additive clock partition gives own eligibility precedence over predecessor
blocking. Their overlap is also reported, outside the additive partition.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import math
from pathlib import Path
import shutil


CLOCK_FIELDS = {
    "segment_id", "task_id", "start", "goal", "leg", "completed", "finish",
    "admission", "first_planning_attempt_time", "observed_finish",
    "reported_finish_epoch", "attempts", "retries", "search_expansions",
    "backtracks", "last_effective_route_excess_seconds",
    "admission_effective_route_excess_seconds", "admission_route_excess_seconds",
}
PARTS = ("release_quantization", "own_ebs_not_ready", "ready_predecessor_block",
         "source_generation_spacing", "unattributed_scheduling_residual")


def ceil_epoch(value):
    return float(Decimal(str(value)).to_integral_value(rounding=ROUND_CEILING))


def statistics(values, denominator):
    values = sorted(values)
    if not values:
        return dict(denominator=denominator, known_count=0, sum=0.0,
                    full_population_mean=None, known_subset_mean=None,
                    known_subset_p95=None, known_subset_max=None)
    index = .95 * (len(values) - 1)
    low, high = math.floor(index), math.ceil(index)
    p95 = values[low] + (values[high] - values[low]) * (index - low)
    total = math.fsum(values)
    return dict(denominator=denominator, known_count=len(values), sum=total,
                full_population_mean=total / denominator if len(values) == denominator else None,
                known_subset_mean=total / len(values), known_subset_p95=p95,
                known_subset_max=values[-1])


def clock_partition(release, eligible, predecessor_admission, end, interval=1.0):
    """Partition [canonical release, first attempt/censor], in stated order.

    Missing eligibility or predecessor admission means still blocked at end.
    For the first task at a source, predecessor_admission is -infinity.
    """
    end = max(float(release), float(end))
    quantum = ceil_epoch(release)
    ready = math.inf if eligible is None else eligible
    previous = math.inf if predecessor_admission is None else predecessor_admission
    cursor = float(release)
    points = (quantum, ready, previous, previous + interval, end)
    result = {}
    for name, point in zip(PARTS, points):
        next_cursor = max(cursor, min(end, point))
        result[name] = next_cursor - cursor
        cursor = next_cursor
    result["preplanning"] = end - release
    result["overlap_own_ebs_and_unadmitted_predecessor"] = max(
        0.0, min(end, ready, previous) - max(float(release), quantum))
    assert abs(math.fsum(result[k] for k in PARTS) - result["preplanning"]) < 1e-6
    return result


def analyze(rows, bags, *, cutoff=98259.0, horizon=200000.0, source_interval=1.0, top=20):
    rows, bags = list(rows), list(bags)
    expected = {str(r["segment_id"]): r for r in rows}
    actual = {str(b["segment_id"]): b for b in bags}
    if len(expected) != len(rows) or len(actual) != len(bags) or set(expected) != set(actual):
        raise ValueError("Exactly one record per canonical segment is required")
    if not (0 <= cutoff <= horizon) or source_interval < 0:
        raise ValueError("Invalid horizon or source interval")
    business, queues = defaultdict(dict), defaultdict(list)
    for ordinal, row in enumerate(rows):
        sid = str(row["segment_id"])
        if row["leg"] in business[str(row["task_id"])]:
            raise ValueError("Duplicate business leg")
        business[str(row["task_id"])][row["leg"]] = sid
        queues[row["start"]].append((row["pass_time"], ordinal, sid))
        for name in ("task_id", "start", "goal", "leg"):
            if name in actual[sid] and actual[sid][name] != row[name]:
                raise ValueError(f"Identity mismatch: {sid}, {name}")
        for name in ("first_planning_attempt_time", "admission", "finish", "observed_finish", "reported_finish_epoch"):
            value = actual[sid].get(name)
            if value is not None and (isinstance(value, bool) or not math.isfinite(value)):
                raise ValueError(f"Invalid clock: {sid}, {name}")

    def report(sid):
        bag = actual[sid]
        if not bag.get("completed") or bag.get("finish") is None:
            return None
        return max([ceil_epoch(bag["finish"])] + [bag[k] for k in
                   ("observed_finish", "reported_finish_epoch") if bag.get(k) is not None])

    def eligibility(row):
        quantum = ceil_epoch(row["pass_time"])
        if row["leg"] != "storage_out":
            return quantum
        incoming = business[str(row["task_id"])].get("storage_in")
        incoming_report = report(incoming) if incoming else None
        return None if incoming_report is None else max(quantum, incoming_report)

    groups = {}
    all_states, heads = Counter(), []
    snapshots = []
    failures = []
    for source, queue in sorted(queues.items()):
        queue.sort()
        predecessor = -math.inf
        predecessor_sid = None
        source_snapshot = None
        for _, ordinal, sid in queue:
            row, bag = expected[sid], actual[sid]
            key = (source, row["leg"])
            if key not in groups:
                groups[key] = dict(count=0, state=Counter(), full=defaultdict(list), restricted=defaultdict(list),
                                   counter_sum=Counter(), counter_known=Counter())
            group = groups[key]
            group["count"] += 1
            first, admission, finish = (bag.get(k) for k in
                                        ("first_planning_attempt_time", "admission", "finish"))
            ready = eligibility(row)
            end_report = report(sid)
            if first is not None:
                if ready is None or first < ready - 1e-6:
                    failures.append([sid, "attempt_before_own_eligibility"])
                if predecessor is None or first < predecessor + source_interval - 1e-6:
                    failures.append([sid, "attempt_before_predecessor_and_spacing"])
                if admission is not None and admission < first:
                    failures.append([sid, "admission_before_attempt"])
                partition = clock_partition(row["pass_time"], ready, predecessor, first, source_interval)
                for name, value in partition.items():
                    group["full"][name].append(value)
            restricted = clock_partition(row["pass_time"], ready, predecessor,
                                         min(cutoff, first) if first is not None else cutoff, source_interval)
            for name, value in restricted.items():
                group["restricted"][name].append(value)
            if first is not None and admission is not None:
                group["full"]["planning_retry"].append(admission - first)
            if admission is not None and end_report is not None and end_report <= horizon:
                group["full"]["network_elapsed"].append(finish - admission)
            retry_to_cutoff = max(0., min(cutoff, admission if admission is not None else cutoff) - first) if first is not None and first <= cutoff else 0.
            group["restricted"]["planning_retry"].append(retry_to_cutoff)
            if end_report is not None and end_report <= cutoff:
                state = "completed"
            elif admission is not None and admission <= cutoff:
                state = "admitted_in_transit"
            elif first is not None and first <= cutoff:
                state = "attempted_not_admitted"
            elif ceil_epoch(row["pass_time"]) > cutoff:
                state = "not_nominally_released"
            elif ready is None or ready > cutoff:
                state = "own_ebs_not_ready"
            elif predecessor is None or predecessor > cutoff:
                state = "ready_but_canonical_predecessor_unadmitted"
            elif predecessor + source_interval > cutoff:
                state = "source_generation_spacing"
            else:
                state = "ready_unattempted_unattributed"
            group["state"][state] += 1
            all_states[state] += 1
            for name in ("attempts", "retries", "search_expansions", "backtracks"):
                if bag.get(name) is not None:
                    group["counter_sum"][name] += bag[name]
                    group["counter_known"][name] += 1
            if admission is None or admission > cutoff:
                if source_snapshot is None:
                    source_snapshot = dict(source=source, head_segment_id=sid, head_leg=row["leg"],
                                           head_state=state, first_attempt=first if first is not None and first <= cutoff else None,
                                           observed_head_retry_seconds=max(0., cutoff-first) if first is not None and first <= cutoff else None,
                                           waiting_segments=0, own_ready_waiting_segments=0,
                                           own_ebs_unready_waiting_segments=0)
                source_snapshot["waiting_segments"] += 1
                if ceil_epoch(row["pass_time"]) <= cutoff:
                    if ready is not None and ready <= cutoff:
                        source_snapshot["own_ready_waiting_segments"] += 1
                    elif row["leg"] == "storage_out":
                        source_snapshot["own_ebs_unready_waiting_segments"] += 1
            if first is not None:
                heads.append(dict(segment_id=sid, task_id=row["task_id"], source=source, leg=row["leg"],
                                  goal=row["goal"], predecessor_segment_id=predecessor_sid,
                                  first_attempt=first, admission=admission,
                                  retry_seconds=admission-first if admission is not None else None,
                                  retry_observed_to_horizon=max(0., min(horizon, admission if admission is not None else horizon)-first),
                                  own_eligibility=ready, finish=finish,
                                  **{k:bag.get(k) for k in ("attempts", "retries", "search_expansions", "backtracks",
                                     "last_effective_route_excess_seconds", "admission_effective_route_excess_seconds",
                                     "admission_route_excess_seconds")}))
            predecessor, predecessor_sid = admission, sid
        if source_snapshot is not None:
            snapshots.append(source_snapshot)
    if failures:
        raise ValueError(f"Source timing validation failed: {failures[:10]}")
    output_groups = []
    for (source, leg), group in sorted(groups.items()):
        n = group["count"]
        output_groups.append(dict(source=source, leg=leg, segments=n,
                                  cutoff_states=dict(group["state"]),
                                  full_run_clocks={k:statistics(v,n) for k,v in group["full"].items()},
                                  cutoff_restricted_clocks={k:statistics(v,n) for k,v in group["restricted"].items()},
                                  full_run_counters={name:dict(known_segments=group["counter_known"][name],
                                      sum=group["counter_sum"][name] if group["counter_known"][name] else None)
                                      for name in ("attempts","retries","search_expansions","backtracks")}))
    completed_business = sum(all(report(sid) is not None and report(sid) <= cutoff for sid in legs.values()) for legs in business.values())
    return dict(schema="g31.source_blocking_diagnosis.v1", cutoff=cutoff, horizon=horizon,
                segment_denominator=len(rows), business_denominator=len(business),
                completed_businesses_at_cutoff=completed_business,
                cutoff_states=dict(all_states), source_leg_groups=output_groups,
                source_heads_at_cutoff=sorted(snapshots,key=lambda x:-x["waiting_segments"]),
                longest_full_run_head_retries=sorted(heads,key=lambda x:-x["retry_observed_to_horizon"])[:top],
                passed=True, boundaries=[
                    "Observed clocks only; the ordered additive partition is not a causal counterfactual or recoverable-time estimate.",
                    "Own EBS eligibility is assigned before canonical predecessor blocking. Their overlap is reported separately and must not be added to the partition.",
                    "A ready task before its predecessor admission is provably blocked by the canonical source contract, but changing this contract is a separate experiment.",
                    "Unattributed scheduling residual is not assigned to a device or algorithm failure.",
                    "Full-run per-bag expansions include source search and in-route replacement search; they are not source-only expansions or per-bag budget-failure counts.",
                    "HCA missing per-bag attempts/expansions remain null. Planner-wide counters cannot identify which task hit a budget.",
                    "Cutoff states and restricted clock sums exclude future attempts/admissions; full-run counters and longest retries are explicitly drain-window diagnostics."])


def read_once(path, *, skim=False):
    digest = hashlib.sha256()
    records = []
    with Path(path).open("rb") as stream:
        for line in stream:
            digest.update(line)
            if line.strip():
                record = json.loads(line)
                records.append({k:v for k,v in record.items() if k in CLOCK_FIELDS} if skim else record)
    return records, digest.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--canonical",type=Path,required=True)
    p.add_argument("--run",action="append",required=True,help="LABEL=path/to/bags.jsonl")
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--cutoff",type=float,default=98259)
    p.add_argument("--horizon",type=float,default=200000)
    args=p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    rows,canonical_hash=read_once(args.canonical)
    runs={}
    for spec in args.run:
        label,path=spec.split("=",1)
        if label in runs:
            raise ValueError("Duplicate label")
        bags,bag_hash=read_once(path,skim=True)
        result=analyze(rows,bags,cutoff=args.cutoff,horizon=args.horizon)
        result["input"]={"bags":str(Path(path).resolve()),"sha256":bag_hash}
        runs[label]=result
        del bags
    args.output.mkdir(parents=True)
    result=dict(schema="g31.source_blocking_comparison.v1",canonical=str(args.canonical.resolve()),
                canonical_sha256=canonical_hash,runs=runs)
    (args.output/"diagnosis.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    shutil.copyfile(__file__,args.output/Path(__file__).name)
    print(json.dumps({label:{"completed_businesses_at_cutoff":r["completed_businesses_at_cutoff"],
                             "cutoff_states":r["cutoff_states"],"longest_retry":r["longest_full_run_head_retries"][:1]}
                      for label,r in runs.items()}))


if __name__=="__main__":
    main()
