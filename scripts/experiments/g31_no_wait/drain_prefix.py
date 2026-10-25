"""Verify an independently rerun drain preserves the actual original-run prefix.

This is a streaming comparison of existing records, not another simulation or a
replacement for the real original-window run. Final routes and cumulative retry
counts after the cutoff are deliberately not used to reconstruct that window.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
import math
from pathlib import Path


def normalized(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def decode(raw):
    return json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON: " + value)))


def read(path):
    return decode(Path(path).read_text(encoding="utf-8-sig"))


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_clock(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def only_end_time_changed(original, drained, horizon):
    left, right = dict(original), dict(drained)
    old_end, new_end = left.pop("end_time", None), right.pop("end_time", None)
    if old_end != horizon or not finite_clock(new_end) or new_end <= horizon:
        raise ValueError("original end_time must equal cutoff and drain end_time must be later")
    if normalized(left) != normalized(right):
        raise ValueError("controls/contract differ beyond end_time")
    return new_end


def validate_contract_change(original, drained, horizon):
    """Permit only the predeclared inert observation-window annotation."""
    left, right = dict(original), dict(drained)
    key = "observation_window_extension"
    if key in right:
        if key in left:
            raise ValueError("original contract unexpectedly carries a drain annotation")
        annotation = right.pop(key)
        expected = dict(original_start=8260, original_end=98259, extended_end=200000,
                        new_arrivals_added=False, deadlines_changed=False)
        if not isinstance(annotation, dict) or set(annotation) != set(expected) | {"purpose"}:
            raise ValueError("unrecognized observation-window metadata")
        if normalized({name:annotation[name] for name in expected}) != normalized(expected):
            raise ValueError("observation-window annotation changes the registered cohort/limits")
        if not isinstance(annotation["purpose"], str) or not annotation["purpose"]:
            raise ValueError("missing observation-window purpose")
        if horizon != expected["original_end"] or right.get("end_time") != expected["extended_end"]:
            raise ValueError("observation-window metadata disagrees with actual cutoff/end")
    return only_end_time_changed(left, right, horizon)


def validate_metadata(original, drained, old_summary, new_summary, horizon):
    """Strict identity checks for the formal continuous-motion entry point."""
    for manifest in (original, drained):
        if manifest.get("schema") != "g31.continuous.run.v1" or manifest.get("status") != "complete" or manifest.get("audits_passed") is not True:
            raise ValueError("both formal runs must have completed their audit pipeline")
    a, b = original["selection"], drained["selection"]
    for key in ("execution_model", "map", "scale", "business_denominator", "segment_denominator"):
        if a.get(key) is None or a.get(key) != b.get(key):
            raise ValueError("input identity changed: " + key)
    for key in ("binary", "canonical", "profile", "build_receipt", "native_source"):
        if not a.get(key, {}).get("sha256") or a[key]["sha256"] != b.get(key, {}).get("sha256"):
            raise ValueError("input/binary identity changed: " + key)
    end = only_end_time_changed(a["effective_controls"], b["effective_controls"], horizon)
    source_a, source_b = original["source_sha256"], drained["source_sha256"]
    # These are the two explicitly different frozen artifacts. All executable
    # code, auditors, profile and build-receipt copies must be identical.
    for key in set(source_a) | set(source_b):
        if key not in ("contract.json", "controls.json") and (key not in source_a or source_a[key] != source_b.get(key)):
            raise ValueError("frozen execution source changed: " + key)
    for summary, expected in ((old_summary, horizon), (new_summary, end)):
        if summary.get("event_budget_exhausted") is not False or summary.get("executed_horizon") != expected:
            raise ValueError("run did not execute its declared horizon")
        if summary.get("tasks") != a["segment_denominator"]:
            raise ValueError("native population differs from registered denominator")
    return end


def clock_prefix(bag, field, horizon):
    value = bag.get(field)
    if value is not None and not finite_clock(value):
        raise ValueError("invalid clock: " + field)
    return value if value is not None and value <= horizon else None


def compare_bag_prefix(original, drained, horizon):
    problems = []
    for field in ("segment_id", "task_id", "leg", "start", "goal"):
        if field not in original or normalized(original[field]) != normalized(drained.get(field)):
            problems.append("identity_changed:" + field)
    for field in ("activation_time", "first_planning_attempt_time", "admission"):
        if field not in original or field not in drained:
            problems.append("missing_clock:" + field)
            continue
        if original[field] is not None and (not finite_clock(original[field]) or original[field] > horizon):
            problems.append("original_clock_after_cutoff_or_invalid:" + field)
        try:
            if normalized(clock_prefix(original, field, horizon)) != normalized(clock_prefix(drained, field, horizon)):
                problems.append("clock_prefix_changed:" + field)
        except ValueError:
            problems.append("invalid_clock:" + field)
    def completed_before(bag, *, is_original):
        if type(bag.get("completed")) is not bool or "actual_finish" not in bag:
            problems.append("missing_actual_completion")
            return None
        finish = bag["actual_finish"]
        if bag["completed"]:
            if not finite_clock(finish):
                problems.append("invalid_actual_completion")
                return None
            if is_original and finish > horizon:
                problems.append("original_completion_after_cutoff")
            return finish if finish <= horizon else None
        if finish is not None:
            problems.append("uncompleted_has_actual_finish")
        return None
    old_done = completed_before(original, is_original=True)
    new_done = completed_before(drained, is_original=False)
    if normalized(old_done) != normalized(new_done):
        problems.append("actual_completed_set_or_time_changed")
    return problems


def stream_bags(original_path, drain_path, horizon):
    hashes = [hashlib.sha256(), hashlib.sha256()]
    records = errors = admitted = attempted = completed = 0
    examples = []
    with Path(original_path).open("rb") as left, Path(drain_path).open("rb") as right:
        for line, pair in enumerate(itertools.zip_longest(left, right), 1):
            records += 1
            for digest, raw in zip(hashes, pair):
                if raw is not None:
                    digest.update(raw)
            if None in pair:
                problems = ["population_record_count_changed"]
            else:
                original, drained = (decode(raw) for raw in pair)
                problems = compare_bag_prefix(original, drained, horizon)
                admitted += original.get("admission") is not None
                attempted += original.get("first_planning_attempt_time") is not None
                completed += original.get("completed") is True
            if problems:
                errors += 1
                if len(examples) < 20:
                    examples.append(dict(line=line, problems=problems))
    return dict(passed=errors == 0, records=records, changed_records=errors, examples=examples,
                original_sha256=hashes[0].hexdigest(), drain_sha256=hashes[1].hexdigest(),
                original_admitted=admitted, original_first_attempted=attempted, original_completed=completed)


class LedgerPrefix:
    def __init__(self, path, horizon):
        self.path, self.horizon = Path(path), horizon
        self.full_hash, self.prefix_hash = hashlib.sha256(), hashlib.sha256()
        self.records = self.prefix_records = self.after_cutoff_records = 0
        self.kinds = Counter()

    def __iter__(self):
        last_time, last_order = -1, -1
        with self.path.open("rb") as stream:
            for raw in stream:
                self.full_hash.update(raw)
                row = decode(raw)
                time, order = row.get("time"), row.get("ledger_order")
                if not finite_clock(time) or time < last_time or type(order) is not int or order <= last_order:
                    raise ValueError("ledger is not a chronological sequence: " + str(self.path))
                last_time, last_order = time, order
                self.records += 1
                if time <= self.horizon:
                    self.prefix_hash.update(raw)
                    self.prefix_records += 1
                    self.kinds[row.get("kind")] += 1
                    yield raw, row
                else:
                    self.after_cutoff_records += 1

    def evidence(self):
        return dict(records=self.records, prefix_records=self.prefix_records,
                    after_cutoff_records=self.after_cutoff_records, kinds=dict(self.kinds),
                    sha256=self.full_hash.hexdigest(), prefix_sha256=self.prefix_hash.hexdigest())


def stream_ledger(original_path, drain_path, horizon):
    original, drained = LedgerPrefix(original_path, horizon), LedgerPrefix(drain_path, horizon)
    records = errors = 0
    raw_exact = True
    examples = []
    for line, (left, right) in enumerate(itertools.zip_longest(original, drained), 1):
        records += 1
        raw_exact &= left is not None and right is not None and left[0] == right[0]
        if left is None or right is None or normalized(left[1]) != normalized(right[1]):
            errors += 1
            if len(examples) < 20:
                examples.append(dict(prefix_line=line, original=left[1] if left else None, drain=right[1] if right else None))
    if original.after_cutoff_records:
        raise ValueError("original ledger contains executed events after its horizon")
    return dict(passed=errors == 0, prefix_records=records, changed_records=errors,
                serialized_prefix_bytes_exact=raw_exact, examples=examples,
                original=original.evidence(), drain=drained.evidence())


def run(original_dir, drain_dir, horizon):
    original_dir, drain_dir = Path(original_dir).resolve(), Path(drain_dir).resolve()
    if original_dir == drain_dir or not finite_clock(horizon):
        raise ValueError("require distinct runs and finite nonnegative cutoff")
    files = [directory/name for directory in (original_dir, drain_dir)
             for name in ("manifest.json", "native_summary.json", "bags.jsonl", "rolling_events.jsonl")]
    stamps = {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in files}
    manifests = [read(directory/"manifest.json") for directory in (original_dir, drain_dir)]
    summaries = [read(directory/"native_summary.json") for directory in (original_dir, drain_dir)]
    drain_end = validate_metadata(*manifests, *summaries, horizon)
    contracts, raw_controls = [], []
    for directory, manifest in zip((original_dir, drain_dir), manifests):
        for name, expected in manifest["source_sha256"].items():
            source = directory/"standard_sources"/name
            if file_sha(source) != expected:
                raise ValueError("frozen source hash mismatch: " + str(source))
            stamps[source] = (source.stat().st_size, source.stat().st_mtime_ns)
        frozen_controls = read(directory/"standard_sources/controls.json")
        effective = manifest["selection"]["effective_controls"]
        # The frozen adapter adds omitted defaults. Its bytes and the complete
        # effective dictionaries already match across runs, so only explicit
        # raw keys must appear unchanged in the effective controls.
        if any(key not in effective or normalized(value) != normalized(effective[key])
               for key, value in frozen_controls.items()):
            raise ValueError("explicit frozen controls differ from executed controls")
        raw_controls.append(frozen_controls)
        contracts.append(read(directory/"standard_sources/contract.json"))
    if only_end_time_changed(*raw_controls, horizon) != drain_end:
        raise ValueError("raw and effective control horizons differ")
    if validate_contract_change(*contracts, horizon) != drain_end:
        raise ValueError("contract and control horizons differ")
    bags = stream_bags(original_dir/"bags.jsonl", drain_dir/"bags.jsonl", horizon)
    for manifest, key in zip(manifests, ("original_sha256", "drain_sha256")):
        if manifest.get("bags_sha256") != bags[key]:
            raise ValueError("finished-run bag bytes changed")
    events = stream_ledger(original_dir/"rolling_events.jsonl", drain_dir/"rolling_events.jsonl", horizon)
    if bags["records"] != manifests[0]["selection"]["segment_denominator"]:
        raise ValueError("bag population does not match registered denominator")
    if bags["original_admitted"] != events["original"]["kinds"].get("source_commit", 0):
        raise ValueError("bag admission count and actual source commits differ")
    if any((path.stat().st_size, path.stat().st_mtime_ns) != stamp for path, stamp in stamps.items()):
        raise ValueError("run evidence changed during prefix scan")
    return dict(schema="g31.nowait.original_drain_prefix.v1", passed=bags["passed"] and events["passed"],
                original_run=str(original_dir), drain_run=str(drain_dir), cutoff=horizon, drain_horizon=drain_end,
                bags=bags, rolling_events=events, tool_sha256=file_sha(__file__),
                allowed_contract_metadata_difference="observation_window_extension with registered 8260/98259/200000, no new arrivals/deadline changes; ignored by native controls",
                manifest_sha256=dict(original=file_sha(original_dir/"manifest.json"), drain=file_sha(drain_dir/"manifest.json")),
                boundary="Both are real independent runs. Exact executed ledger prefix includes cutoff-time events. Immutable activation/first-attempt/admission clocks and actual completions through cutoff must agree. Final future routes, planned finishes and cumulative attempts/retries from the drain are never substituted for original-window observations.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--drain", type=Path, required=True)
    parser.add_argument("--cutoff", type=float, default=98259)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("choose a new prefix receipt path")
    result = run(args.original, args.drain, args.cutoff)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps(dict(passed=result["passed"], bags=result["bags"]["records"], events=result["rolling_events"]["prefix_records"])))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
