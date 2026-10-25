"""Read-only source-delay attribution by observed clock components.

Counts describe observed delay; they are not counterfactual causal savings.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import shutil


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bags", type=Path, required=True)
    p.add_argument("--canonical", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    rows = {str(r["segment_id"]): r for r in
            (json.loads(line) for line in a.canonical.read_text(encoding="utf-8").splitlines() if line.strip())}
    groups = defaultdict(lambda: {"segments": 0, "known_first_attempt": 0,
                                  "preplanning_seconds": 0., "retry_seconds": 0.,
                                  "network_seconds": 0., "max_retry_seconds": 0.})
    heads = []
    with a.bags.open(encoding="utf-8") as stream:
        for line in stream:
            bag = json.loads(line)
            row = rows[str(bag["segment_id"])]
            group = groups[(row["start"], row["leg"])]
            group["segments"] += 1
            first, admission, finish = (bag.get(k) for k in ("first_planning_attempt_time", "admission", "finish"))
            if first is None:
                continue
            group["known_first_attempt"] += 1
            group["preplanning_seconds"] += first - row["pass_time"]
            if admission is None:
                continue
            retry = admission - first
            group["retry_seconds"] += retry
            group["max_retry_seconds"] = max(group["max_retry_seconds"], retry)
            if finish is not None:
                group["network_seconds"] += finish - admission
            heads.append(dict(segment_id=bag["segment_id"], task_id=row["task_id"], leg=row["leg"],
                              source=row["start"], goal=row["goal"], canonical_release=row["pass_time"],
                              first_attempt=first, admission=admission, retry_seconds=retry,
                              attempts=bag.get("attempts"), finish=finish,
                              route_nodes=[p[0] for p in bag.get("route", [])]))
    result = dict(schema="g31.observed_source_delay.v1", source_leg_groups=[
        dict(source=source, leg=leg, **metrics) for (source, leg), metrics in
        sorted(groups.items(), key=lambda item: -item[1]["preplanning_seconds"])],
        longest_observed_head_retries=sorted(heads, key=lambda h: -h["retry_seconds"])[:20],
        interpretation="Observed clocks, not a causal counterfactual. Preplanning includes FIFO and EBS eligibility delays; these must not all be labelled avoidable service queues.",
        inputs={str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in (a.bags, a.canonical)})
    a.output.mkdir(parents=True)
    (a.output/"diagnosis.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    shutil.copyfile(__file__, a.output/Path(__file__).name)
    print(json.dumps({"top_groups": result["source_leg_groups"][:3],
                      "longest_head": result["longest_observed_head_retries"][:1]}))


if __name__ == "__main__":
    main()
