"""Append-only snapshots of verified native and matched physical HCA results.

No simulator is loaded. Missing, running, censored or invalid populations never
produce full-population means/quantiles. Re-run into a NEW output directory as
results arrive. This report describes all supplied variants; it selects no winner.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_no_wait.tht_metrics import audit_tht
from scripts.experiments.g31_no_wait.source_policy_audit import audit_source_policy

CAMPAIGN = ROOT / "outputs/experiments/g31_no_wait_20261024"
CONTRACT = ROOT / "configs/eval/g31_continuous/contract.json"
CORE005 = "c997415fe060833da35712b6179ab24a99c122811e1364dd1f1344f098674537"
CELLS = ("map2_1x", "nanning_1x", "map2_2x", "nanning_2x")
METRICS = {
    "user_tht": ("user_tht",),
    "planning_retry_wait": ("secondary", "business_sum_planning_wait"),
    "canonical_to_first_attempt": ("secondary", "business_sum_canonical_preplanning"),
    "canonical_elapsed": ("secondary", "business_sum_canonical_elapsed"),
    "network_elapsed": ("paper_tht",),
    "activation_to_first_attempt": ("secondary", "business_sum_activation_to_first_planning"),
}
STATS = ("sum", "mean", "min", "p50", "p95", "p99", "max")
FIELDS = {"segment_id", "task_id", "leg", "start", "goal", "completed", "admission", "finish",
          "first_planning_attempt_time", "activation_time", "reported_finish_epoch", "observed_finish",
          "attempts", "retries", "actual_finish"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite JSON: " + x)))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def null_stats(n):
    return {"count": n, **dict.fromkeys(STATS)}


def stats(values, n):
    if len(values) != n or any(v is None for v in values):
        return null_stats(n)
    values = sorted(values)
    def q(p):
        pos = (n - 1) * p
        low = int(pos)
        high = min(low + 1, n - 1)
        return values[low] + (pos - low) * (values[high] - values[low])
    if not n:
        return null_stats(n)
    total = math.fsum(values)
    return dict(count=n, sum=total, mean=total/n, min=values[0], p50=q(.5), p95=q(.95), p99=q(.99), max=values[-1])


def rooted(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


class Snapshot:
    """Record the exact bytes consumed, and detect a file changing mid-read."""
    def __init__(self):
        self.files = {}
        self.stamps = {}

    def stamp(self, path):
        s = Path(path).stat()
        return (s.st_size, s.st_mtime_ns)

    def json(self, path, optional=False):
        path = Path(path).resolve()
        if optional and not path.is_file():
            return None
        before = self.stamp(path)
        raw = path.read_bytes()
        self.record(path, raw, before)
        return json.loads(raw.decode("utf-8-sig"))

    def record(self, path, raw, before):
        if self.stamp(path) != before:
            raise ValueError("file changed while reading: " + str(path))
        self.files[str(path)] = dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        self.stamps[str(path)] = before

    def bags(self, path):
        path = Path(path).resolve()
        before = self.stamp(path)
        h = hashlib.sha256()
        bags = []
        with path.open("rb") as stream:
            for raw in stream:
                h.update(raw)
                if raw.strip():
                    row = json.loads(raw)
                    bags.append({key: value for key, value in row.items() if key in FIELDS})
        if self.stamp(path) != before:
            raise ValueError("bag file changed while reading")
        self.files[str(path)] = dict(sha256=h.hexdigest(), bytes=before[0])
        self.stamps[str(path)] = before
        return bags, h.hexdigest()

    def unchanged(self):
        return all(self.stamp(path) == before for path, before in self.stamps.items())


def effective_retry_policy(config):
    """Normalize the frozen005 parser alias before interpreting attempt()."""
    mode = config.get("retry_mode", "futurecalendar_jump")
    normalized = "futurecalendar_jump" if mode == "calendar_jump" else mode
    step = 1.0 if mode == "1s" else config.get("retry_step", 1.0)
    return dict(configured=mode, effective=("futurecalendar_jump" if normalized == "futurecalendar_jump" else
                 "1s" if step == 1 else "fixed_step"), step_seconds=step,
                parser_alias_applied=mode!=normalized,
                warning=None,release_quantum=config.get("release_quantum", 1),
                source="frozen005 core.cpp parse_config() then attempt(); verified on immutable005 binary")


def movement_audit_status(movement):
    safety=movement.get("safety", {})
    counts=movement.get("business", {}).get("counts", {})
    # The raw double subtraction sum can be 1e-7 seconds from roundoff. Exact
    # integer-grid timing is independently required by the headway audit.
    return all(safety.get(k)==0 for k in ("route_violations","routes_with_repeated_nodes",
               "internal_internal_interval_overlaps")) and counts.get("causally_invalid_admitted")==0


def load_cell(contract, cell, snapshot):
    detail = contract["cells"][cell]
    record = detail["canonical"]
    path = rooted(record["path"]).resolve()
    before = snapshot.stamp(path)
    raw = path.read_bytes()
    snapshot.record(path, raw, before)
    if hashlib.sha256(raw).hexdigest() != record["sha256"]:
        raise ValueError("registered canonical storage hash mismatch")
    if record.get("encoding") == "gzip_jsonl":
        raw = gzip.decompress(raw)
    content_hash = hashlib.sha256(raw).hexdigest()
    if content_hash != record.get("content_sha256", record["sha256"]):
        raise ValueError("canonical content hash mismatch")
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if len(rows) != detail["segment_denominator"] or len({r["task_id"] for r in rows}) != detail["business_denominator"]:
        raise ValueError("registered population mismatch")
    return rows, content_hash


def summarize_population(rows, bags, horizon, *, run_finished, window_start=0, window_end=None):
    window_end = horizon if window_end is None else window_end
    if not all(math.isfinite(t) for t in (horizon, window_start, window_end)) or not 0 <= window_start < window_end:
        raise ValueError("system window must be finite, nonnegative and nonempty")
    tht = audit_tht(rows, bags, horizon=horizon)
    source = audit_source_policy(rows, bags)
    n = tht["business_denominator"]
    complete = (run_finished and tht["passed"] and tht["completed_businesses"] == n
                and tht["user_tht_full_population_available"])
    result = dict(completed_businesses=tht["completed_businesses"], completed_segments=tht["completed_segments"],
                  business_denominator=n, segment_denominator=len(rows), full_population_available=complete,
                  missing_first_planning_attempt_segments=tht["missing_first_planning_attempt_segments"], metrics={})
    for name, keys in METRICS.items():
        item = tht
        for key in keys:
            item = item.get(key, {})
        result["metrics"][name] = item.get("full_population", null_stats(n)) if complete else null_stats(n)
    actual = {str(b["segment_id"]): b for b in bags}
    groups = defaultdict(list)
    for row in rows:
        groups[row["task_id"]].append(row)
    std = early = 0
    retry_sums = []
    completed_at = []
    business_released_at = []
    for group in groups.values():
        business_released_at.append(min(r["pass_time"] for r in group))
        final = next((r for r in group if r["leg"] in ("direct", "storage_out")), None)
        all_done = all(actual.get(str(r["segment_id"]), {}).get("completed") is True and
                       isinstance(actual[str(r["segment_id"])].get("finish"), (int, float)) and
                       actual[str(r["segment_id"])] ["finish"] <= horizon for r in group)
        if final is not None and all_done:
            finish = actual[str(final["segment_id"])] ["finish"]
            completed_at.append(max(actual[str(r["segment_id"])] ["finish"] for r in group))
            std += finish <= final["std"]
            early += finish <= final["std"] - 2700
        values = [actual.get(str(r["segment_id"]), {}).get("retries") for r in group]
        retry_sums.append(sum(values) if all(type(v) is int and v >= 0 for v in values) else None)
    result["metrics"]["retry_count"] = stats(retry_sums, n) if complete else null_stats(n)
    result["retry_count_definition"] = "Sum of explicit per-segment retries per business; absent HCA telemetry remains null, never inferred from elapsed seconds."
    std_final=run_finished and tht["passed"] and all(r["std"]<=horizon for r in rows)
    early_final=run_finished and tht["passed"] and all(r["std"]-2700<=horizon for r in rows)
    result["deadlines"] = dict(denominator=n, std_count=std if complete or std_final else None,
                               std_rate=std/n if n and (complete or std_final) else None,
                               std_minus_2700_count=early if complete or early_final else None,
                               std_minus_2700_rate=early/n if n and (complete or early_final) else None,
                               std_status_final=complete or std_final,early_status_final=complete or early_final,
                               deadline_status_final=complete or (std_final and early_final),
                               observed_std_count_diagnostic=std, observed_early_count_diagnostic=early)
    # Fixed-window throughput remains meaningful when eventual all-bag THT is censored.
    # Times below are physical continuous goal arrivals, never planned future finish.
    observed_end = min(horizon, window_end)
    window_fully_observed = run_finished and tht["passed"] and horizon >= window_end
    times = [window_start] if observed_end >= window_start else []
    while times and times[-1] + 3600 < observed_end:
        times.append(times[-1] + 3600)
    if times and observed_end > times[-1]:
        times.append(observed_end)
    completed_at.sort();business_released_at.sort()
    import bisect
    curve = []
    for time in times:
        done = bisect.bisect_right(completed_at,time)
        released = bisect.bisect_right(business_released_at,time)
        curve.append(dict(time=time,hours_since_window_start=(time-window_start)/3600,
                          cumulative_completed_businesses=done,cumulative_released_businesses=released,
                          released_backlog_businesses=released-done))
    observed_window_done = sum(window_start <= t <= observed_end for t in completed_at)
    done_by_window_end = bisect.bisect_right(completed_at, window_end)
    released_by_window_end = bisect.bisect_right(business_released_at, window_end)
    duration = window_end-window_start
    result["system"] = dict(window_start=window_start,window_end=window_end,continuous_duration_seconds=duration,
        observed_horizon=horizon,window_fully_observed=window_fully_observed,
        business_completions_in_window=observed_window_done if window_fully_observed else None,
        completion_fraction=done_by_window_end/n if n and window_fully_observed else None,
        business_throughput_per_simulated_hour=observed_window_done*3600/duration if window_fully_observed else None,
        original_population_backlog_businesses=n-done_by_window_end if window_fully_observed else None,
        released_backlog_businesses=released_by_window_end-done_by_window_end if window_fully_observed else None,
        unreleased_businesses=n-released_by_window_end if window_fully_observed else None,
        observed_window_completions_lower_bound=observed_window_done,
        observed_total_completed_businesses=len(completed_at),
        observed_after_window_completions=sum(t>window_end for t in completed_at),
        hourly_cumulative_business_completion=curve,
        boundary="Window counts use only physical completions within the separately declared fixed window; later drain completions never increase its throughput. Final window counts require observation through window_end, even when eventual full-population THT is null. Rate divides by continuous window_end-window_start, not inclusive integer epoch count.")
    return result, tht, source


def infer_cell(directory):
    match = re.search(r"(map2|nanning)_([12])x", Path(directory).name)
    if not match:
        path=Path(directory)/"manifest.json"
        if path.is_file():
            manifest=read(path)
            metadata=manifest.get("selection",manifest)
            if metadata.get("map") in ("map2","nanning") and metadata.get("scale") in (1,2):
                return f"{metadata['map']}_{metadata['scale']}x"
        raise ValueError("cannot identify cell from directory: " + str(directory))
    return f"{match[1]}_{match[2]}x"


def empty_record(algorithm, directory, cell, contract):
    detail = contract["cells"][cell]
    n = detail["business_denominator"]
    return dict(id=(directory.name if algorithm == "g31" else directory.parent.name + "__" + directory.name),
        algorithm=algorithm, cell=cell, directory=str(directory.resolve()), status="missing", issues=[],
        business_denominator=n, segment_denominator=detail["segment_denominator"], completed_businesses=None,
        completed_segments=None, full_population_available=False, comparable=False,
        metrics={key:null_stats(n) for key in (*METRICS, "retry_count")},
        deadlines=dict(denominator=n,std_count=None,std_rate=None,std_minus_2700_count=None,std_minus_2700_rate=None),
        audit_status={}, provenance={})


def summarize_run(algorithm, directory, contract, output, cache, window_start=8260, accepted_core_hashes=None, window_end=None):
    cell = infer_cell(directory)
    result = empty_record(algorithm, directory, cell, contract)
    snapshot = Snapshot()
    if not directory.is_dir():
        return result
    try:
        if algorithm == "g31":
            manifest = snapshot.json(directory/"manifest.json", optional=True)
            if not manifest:
                result["status"] = "awaiting_manifest"
                return result
            result["status"] = manifest["status"]
            formal = manifest.get("schema") == "g31.continuous.run.v1"
            selection = manifest.get("selection", {})
            result["source_sha256_declared"] = manifest.get("source_sha256", {})
            result["binary_sha256_declared"] = selection.get("binary",{}).get("sha256") if formal else manifest.get("binary_sha256")
            cfg = selection.get("effective_controls",{}) if formal else manifest.get("config", {})
            result["config"] = cfg
            result["effective_retry_policy"] = effective_retry_policy(cfg)
            if result["status"] != "complete":
                return result
            native = snapshot.json(directory/"native_summary.json")
            horizon = native.get("executed_horizon")
            if horizon is None:
                raise ValueError("missing actual execution horizon")
            if native.get("event_budget_exhausted"):
                raise ValueError("event budget exhausted")
            if manifest.get("source_sha256", {}).get("core.cpp") not in (accepted_core_hashes or {CORE005}):
                raise ValueError("unregistered native core; supply its verified --build-receipt")
            if cfg.get("source_fifo_order") != "canonical":
                raise ValueError("not canonical source FIFO")
            fixed = dict(interval_mode="half_open",strict_endpoint_resources=True,
                         enable_ebs_predecessor_gate=True,enable_inroute_replanning=True,
                         edge_entry_headway_seconds=2,source_fifo=True,
                         source_generation_interval=1,release_quantum=1,completion_quantum=1)
            if any(cfg.get(key) != value for key,value in fixed.items()) or cfg.get("time_grid_seconds",1e-6) != 1e-6:
                raise ValueError("not the shared physical/source policy")
            profile_hash = selection.get("profile",{}).get("sha256") if formal else manifest.get("profile_sha256")
            if profile_hash != contract["maps"][cell.rsplit("_",1)[0]]["profile"]["sha256"]:
                raise ValueError("normalized physical profile differs from registered graph")
            for name, expected in manifest["source_sha256"].items():
                path = directory/("standard_sources" if formal else "source")/name
                if not path.is_file() or sha(path) != expected:
                    raise ValueError("frozen source mismatch: " + name)
            bags_path = directory/"bags.jsonl"
            expected_bags = manifest.get("bags_sha256")
            if formal:
                canonical_record=contract["cells"][cell]["canonical"]
                if selection.get("canonical",{}).get("sha256") != canonical_record["sha256"]:
                    raise ValueError("standard selected canonical storage hash changed")
                expected_canonical=canonical_record.get("content_sha256",canonical_record["sha256"])
            else:
                expected_canonical = manifest.get("canonical_sha256")
            for name in ("headway_audit", "rolling_replay", "source_policy_audit", "tht_audit"):
                audit = snapshot.json(directory/(name+".json"), optional=True)
                result["audit_status"][name] = audit.get("passed") if audit else None
            movement = snapshot.json(directory/"audit.json", optional=True)
            if movement:
                safety = movement.get("safety", {})
                result["audit_status"]["continuous_motion_and_causal"] = movement_audit_status(movement)
                result["raw_double_wait_diagnostic"] = {key:safety.get(key) for key in
                    ("internal_extra_wait_sum_seconds","internal_extra_wait_max_seconds")}
            else:
                business = snapshot.json(directory/"business_audit.json", optional=True) if formal else None
                result["audit_status"]["continuous_motion_and_causal"] = business.get("passed") if business else None
            result["cost"] = dict(native_wall_seconds=manifest.get("native_wall_seconds"),
                native_process_cpu_seconds=manifest.get("native_process_cpu_seconds"),
                memory=manifest.get("memory_after_native_api",manifest.get("memory_after_native")),
                planning_attempts=native.get("planning_attempts"),failed_attempts=native.get("failed_attempts"),
                planning_profile=None, scope="Native API including conversion/preprocessing; not HCA whole Java wall scope.")
        else:
            manifest = snapshot.json(directory.parent/"manifest.json", optional=True)
            if manifest:
                result["source_sha256_declared"] = manifest.get("adapted_core_files", [])
                adapter_path = manifest.get("physical_adapter", {}).get("path")
                if adapter_path:
                    for name in ("manifest.json", "SOURCE_FREEZE.json"):
                        snapshot.json(Path(adapter_path)/name, optional=True)
            run_status = snapshot.json(directory/"run_01/run_status.json", optional=True)
            result["status"] = run_status.get("status", "awaiting_run_status") if run_status else "awaiting_run_status"
            if result["status"] != "complete":
                return result
            if run_status.get("returncode") != 0:
                raise ValueError("HCA process did not exit successfully")
            bags_path = directory/"annotated_physical_bags.jsonl"
            receipt = snapshot.json(directory/"annotated_physical_bags_receipt.json", optional=True)
            analysis = snapshot.json(directory/"continuous_analysis.json", optional=True)
            if not bags_path.is_file() or not receipt or not analysis:
                result["status"] = "awaiting_verified_annotation"
                return result
            expected_bags = receipt.get("evidence", {}).get("output_sha256")
            expected_canonical = receipt.get("evidence", {}).get("canonical_sha256")
            horizon = analysis["horizon"]
            physical = snapshot.json(directory/"physical_headway_audit.json", optional=True)
            result["audit_status"]["physical_headway"] = physical.get("passed") if physical else None
            result["audit_status"]["annotation_original_fields_exact"] = receipt.get("original_fields_exact")
            business = analysis.get("business", {})
            # Not-yet-attempted outbound legs are valid censored observations;
            # the source-policy replay checks every actual attempt/admission.
            result["audit_status"]["causal_ebs"] = business.get("ebs_causality_violations") == 0
            result["ebs_causality_unobserved_diagnostic"] = business.get("ebs_causality_unobserved")
            profile = snapshot.json(directory/"run_01/planning_profile.json", optional=True)
            result["cost"] = dict(java_wall_seconds=run_status.get("wall_seconds"),planning_profile=profile,
                                  scope="Java whole-run wall includes per-epoch I/O; optional explicit A* profiling has a narrower scope.")
            result["effective_retry_policy"] = dict(configured="Java no-fault epoch loop",effective="1s",step_seconds=1,
                                                    warning="No per-bag retry counter; do not infer counts from clock differences.")
        if cell not in cache:
            cache[cell] = load_cell(contract, cell, snapshot)
        rows, canonical_hash = cache[cell]
        result["canonical_content_sha256"] = canonical_hash
        if expected_canonical != canonical_hash:
            raise ValueError("run canonical hash differs from registered population")
        bags, bag_hash = snapshot.bags(bags_path)
        if expected_bags != bag_hash:
            raise ValueError("bag hash differs from finished-run receipt")
        result["bags_sha256"] = bag_hash
        result["horizon"] = horizon
        population, tht, source = summarize_population(rows,bags,horizon,run_finished=True,
                                                       window_start=window_start,window_end=window_end)
        result.update(population)
        result["audit_status"]["recomputed_tht"] = tht["passed"]
        result["audit_status"]["recomputed_source_policy"] = source["passed"]
        subdir = output/result["id"]
        subdir.mkdir()
        write(subdir/"recomputed_tht.json",tht)
        write(subdir/"recomputed_source_policy.json",source)
        result["comparable"] = result["full_population_available"] and all(v is True for v in result["audit_status"].values())
        if not result["full_population_available"]:
            result["status"] = "incomplete_population"
        elif not result["comparable"]:
            result["status"] = "audit_failed_or_missing"
        if not snapshot.unchanged():
            raise ValueError("input changed during comparison snapshot")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["status"] = "unavailable_or_invalid"
        result["issues"].append(str(exc))
        result["comparable"] = result["full_population_available"] = False
        result["metrics"] = {key:null_stats(result["business_denominator"]) for key in (*METRICS,"retry_count")}
        result["deadlines"] = dict(denominator=result["business_denominator"],std_count=None,std_rate=None,
                                   std_minus_2700_count=None,std_minus_2700_rate=None)
        result["system"] = None
    finally:
        result["provenance"] = snapshot.files
    return result


def pair_summary(candidate, baseline):
    reasons = []
    for key in ("cell","canonical_content_sha256","horizon","business_denominator","segment_denominator"):
        if candidate.get(key) is None or candidate.get(key) != baseline.get(key):
            reasons.append("different_or_missing_" + key)
    if not candidate["comparable"] or not baseline["comparable"]:
        reasons.append("unfinished_invalid_or_missing_audit")
    result = dict(candidate=candidate["id"],baseline=baseline["id"],cell=candidate["cell"],
                  comparable=not reasons,reasons=reasons,metrics={})
    for name in (*METRICS,"retry_count"):
        a,b=candidate["metrics"][name],baseline["metrics"][name]
        result["metrics"][name] = {
            field:dict(difference=(a[field]-b[field]) if not reasons and a[field] is not None and b[field] is not None else None,
                       ratio=(a[field]/b[field]) if not reasons and a[field] is not None and b[field] not in (None,0) else None)
            for field in ("mean","p95","p99")}
    result["criterion"] = "Descriptive G31 minus HCA only; no selection, ranking or winner is produced."
    # Unlike eventual THT, fixed-window completion counts may be compared with a censored population.
    a,b=candidate.get("system"),baseline.get("system")
    same_system_window = (a is not None and b is not None and a["window_start"]==b["window_start"] and
                          a["window_end"]==b["window_end"] and
                          a.get("window_fully_observed") is True and b.get("window_fully_observed") is True and
                          candidate.get("cell")==baseline.get("cell") and
                          candidate.get("business_denominator")==baseline.get("business_denominator") and
                          candidate.get("canonical_content_sha256")==baseline.get("canonical_content_sha256") and
                          all(v is True for v in candidate["audit_status"].values()) and
                          all(v is True for v in baseline["audit_status"].values()))
    result["system_window"] = dict(comparable=same_system_window,
        completions_difference=(a["business_completions_in_window"]-b["business_completions_in_window"]) if same_system_window else None,
        backlog_difference=(a["original_population_backlog_businesses"]-b["original_population_backlog_businesses"]) if same_system_window else None)
    return result


def discover(campaign, explicit):
    if explicit:
        return sorted({p.resolve() for p in explicit},key=str)
    existing = {p for p in campaign.glob("g31_*_005") if p.is_dir()}
    predeclared = campaign/"predeclared_canonical_fifo_screen_005.json"
    if predeclared.is_file():
        spec = read(predeclared)
        for cell in spec["cells"]:
            for variant in spec["screen_order"]:
                existing.add(campaign/f"g31_{cell}_rolling_{variant}_005")
    return sorted(existing,key=str)


def verified_core_hash(receipt_path):
    receipt_path=Path(receipt_path).resolve()
    receipt=read(receipt_path)
    if receipt.get("status")!="complete" or not receipt.get("binaries"):
        raise ValueError("additional build is not complete")
    for name,expected in receipt["source_sha256"].items():
        if sha(receipt_path.parent/"source"/name)!=expected:
            raise ValueError("additional immutable build source changed")
    for binary,expected in receipt["binaries"].items():
        if sha(binary)!=expected:
            raise ValueError("additional immutable binary changed")
    return receipt["source_sha256"]["core.cpp"]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign",type=Path,default=CAMPAIGN)
    parser.add_argument("--contract",type=Path,default=CONTRACT)
    parser.add_argument("--g31-dir",type=Path,nargs="*",default=[])
    parser.add_argument("--hca-1x-parent",type=Path)
    parser.add_argument("--hca-2x-parent",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--build-receipt",type=Path,action="append",default=[],
                        help="Explicit complete immutable build receipt to permit e.g. native006. Default discovery remains005.")
    parser.add_argument("--window-start",type=float,default=8260,
                        help="Original benchmark start; hours use continuous end minus start, not inclusive epoch count.")
    parser.add_argument("--window-end",type=float,default=98259,
                        help="Fixed throughput window end, independent of each run's execution/drain horizon.")
    args=parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError("choose a new append-only output directory")
    contract=read(args.contract)
    if not all(math.isfinite(t) for t in (args.window_start,args.window_end)) or not 0<=args.window_start<args.window_end:
        raise ValueError("system window must be finite, nonnegative and nonempty")
    accepted_core_hashes={CORE005}
    additional_builds=[]
    for path in args.build_receipt:
        core=verified_core_hash(path);accepted_core_hashes.add(core)
        additional_builds.append(dict(path=str(path.resolve()),sha256=sha(path),core_sha256=core))
    args.output.mkdir(parents=True)
    inputs=[("g31",p) for p in discover(args.campaign,args.g31_dir)]
    hca1=args.hca_1x_parent or args.campaign/"hca_repaired_uniform_headway2_002"
    hca2=args.hca_2x_parent or args.campaign/"hca_repaired_uniform_profile_004"
    inputs += [("hca",(hca1 if cell.endswith("1x") else hca2)/cell) for cell in CELLS]
    source_paths=[Path(__file__),Path(__file__).with_name("tht_metrics.py"),Path(__file__).with_name("source_policy_audit.py")]
    report=dict(schema="g31.nowait.current_comparison.v1",created_at=datetime.now(timezone.utc).isoformat(),
        status="snapshot_complete",selected_controls=None,winner=None,
        contract=dict(path=str(args.contract.resolve()),sha256=sha(args.contract)),
        comparison_window=dict(start=args.window_start,end=args.window_end),
        source_sha256={p.name:sha(p) for p in source_paths},runs=[],pairs=[],
        accepted_core_sha256=sorted(accepted_core_hashes),additional_verified_builds=additional_builds,
        definitions={"primary":"Per business sum over transport legs of continuous finish minus first actual planning attempt; retries included, EBS storage excluded.",
                     "canonical_elapsed":"Per business sum of leg finish minus canonical pass_time: segmented elapsed including nominal-release backlog. If an outbound nominal release precedes actual inbound completion, the two leg windows overlap; this is not unique business wall-clock elapsed.",
                     "incomplete":"All full-population duration/count-distribution metrics null. Observed completion counts and explicitly labelled deadline observations are diagnostics.",
                     "retry_counts":"Only explicit counters; HCA missing per-bag counters remain null. Planning wait seconds are separately reported.",
                     "system_objective":"Report separately fixed-window completions/backlog and actual-horizon full-population THT. Later drain completions do not increase original-window throughput; no per-bag winner selection.",
                     "timing":"Native API and Java whole-run wall times have different scopes; no speed ratio is computed."})
    cache={}
    for algorithm,directory in inputs:
        report["runs"].append(summarize_run(algorithm,directory,contract,args.output,cache,args.window_start,
                                             accepted_core_hashes,window_end=args.window_end))
    for a in report["runs"]:
        if a["algorithm"]=="g31":
            for b in report["runs"]:
                if b["algorithm"]=="hca" and a["cell"]==b["cell"]:
                    report["pairs"].append(pair_summary(a,b))
    for p in source_paths:
        if sha(p)!=report["source_sha256"][p.name]:
            raise ValueError("report/auditor source changed during snapshot")
        shutil.copyfile(p,args.output/p.name)
    write(args.output/"comparison.json",report)
    columns=["id","algorithm","cell","status","comparable","completed_businesses","business_denominator",
             "user_tht_mean","user_tht_p95","user_tht_p99","planning_retry_wait_mean","retry_count_mean",
             "canonical_to_first_attempt_mean","canonical_elapsed_mean","std_rate","std_minus_2700_rate"]
    columns += ["window_start","window_end","observed_horizon","window_fully_observed",
                "window_completions","original_population_backlog","business_throughput_per_simulated_hour",
                "observed_after_window_completions"]
    with (args.output/"comparison.csv").open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        for r in report["runs"]:
            row={key:r.get(key) for key in columns[:7]}
            for name,field in (("user_tht","mean"),("user_tht","p95"),("user_tht","p99"),
                               ("planning_retry_wait","mean"),("retry_count","mean"),
                               ("canonical_to_first_attempt","mean"),("canonical_elapsed","mean")):
                row[name+"_"+field]=r["metrics"][name][field]
            row.update({key:r["deadlines"].get(key) for key in ("std_rate","std_minus_2700_rate")})
            system=r.get("system") or {}
            row.update({key:system.get(key) for key in ("window_start","window_end","observed_horizon",
                                                       "window_fully_observed","observed_after_window_completions")})
            row.update(window_completions=system.get("business_completions_in_window"),
                       original_population_backlog=system.get("original_population_backlog_businesses"),
                       business_throughput_per_simulated_hour=system.get("business_throughput_per_simulated_hour"))
            writer.writerow(row)
    with (args.output/"completion_curves.csv").open("w",newline="",encoding="utf-8") as stream:
        columns=["id","algorithm","cell","time","hours_since_window_start",
                 "cumulative_completed_businesses","cumulative_released_businesses","released_backlog_businesses"]
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        for run in report["runs"]:
            for point in (run.get("system") or {}).get("hourly_cumulative_business_completion",[]):
                writer.writerow({**{key:run[key] for key in ("id","algorithm","cell")},**point})
    print(json.dumps(dict(output=str(args.output.resolve()),runs=len(report["runs"]),
                          comparable_runs=sum(r["comparable"] for r in report["runs"]),winner=None)))
    return report


if __name__=="__main__":
    main()
