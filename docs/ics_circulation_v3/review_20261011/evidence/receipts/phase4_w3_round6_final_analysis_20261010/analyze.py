"""Pure-file round6 comparisons; never constructs a policy or simulation."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import shutil
from time import perf_counter, process_time

WEIGHTS = {"tray_wait": 1.0, "nonprotected_tardiness": 1.0, "empty_distance": 0.1,
           "terminal_backlog": 10.0, "terminal_inflight": 2.0}
POLICIES = ("old32", "old64", "same_zone32plus32")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def compact(raw):
    result = raw["result"]
    if result is None:
        return None
    return {"future_sha256": raw["input_binding"]["future_sha256"],
            "initial_sha256": digest(raw["initial_state"]), "cache_sha256": digest(raw["cache_before"]),
            "expected_task_ids": raw["expected_task_ids"], "completed": result["completed"],
            "cost_components": result["cost_components"], "physical_sha256": digest(raw["physical_tick_trace"]),
            "trace_sha256": digest(result["trace"]), "trays_sha256": digest(result["final_trays"]),
            "event_suffix_sha256": digest(raw["event_trace_suffix"]), "ledger_sha256": digest(raw["evaluation_ledger"]),
            "search_sha256": digest(raw["searches"]), "stopped_at": raw["stopped_at"]}


def analyze(base, out, stages):
    wall, cpu = perf_counter(), process_time()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, out / "analyze.py")
    bound, errors, checks = {}, [], 0

    def load(path):
        bound[str(path.resolve())] = sha(path)
        return read(path)

    def check(ok, context):
        nonlocal checks
        checks += 1
        if not ok:
            errors.append(context)

    protocol = load(base / "protocol.json")
    load(base / "saved_tapes.json")
    check(sha(base / "saved_tapes.json") == protocol["saved_tapes_sha256"], "saved tape binding")
    records, rows, stage_resources = {}, [], []
    for stage in stages:
        summary = load(base / stage / "summary.json")
        requested = load(base / stage / "requested_cases.json")
        check(requested == protocol["stage_planned_cases"][stage], stage + ": complete predeclared domain")
        check({r["case_id"] for r in requested} == {r["case_id"] for r in summary["rows"]}, stage + ": complete cases")
        check(len(summary["rows"]) == len(requested), stage + ": no duplicate cases")
        stage_resources.append({k: summary.get(k) for k in (
            "stage", "planned_cases", "status_counts", "case_invocation_cpu_seconds_recorded",
            "unknown_resource_cases", "parent_cpu_seconds", "wall_makespan_seconds",
            "sources_inputs_tests_unchanged", "immutability_failure")})
        for item in summary["rows"]:
            row = {"stage": stage, **item}
            rows.append(row)
            if not item.get("file"):
                continue
            path = base / item["file"]
            check(sha(path) == item["sha256"], item["case_id"] + ": artifact SHA")
            raw = load(path)
            result, ledger = raw["result"], raw["evaluation_ledger"]
            if result is None:
                records[stage, item["case_id"]] = None
                continue
            prefix = stage + "/" + item["case_id"]
            check(set(WEIGHTS) == set(result["cost_components"]), prefix + ": fixed cost components")
            total = sum(WEIGHTS[k] * result["cost_components"][k] for k in WEIGHTS)
            check(abs(total - result["total_cost"]) < 1e-8, prefix + ": weighted J")
            check(len({b["bag_id"] for b in ledger}) == len(ledger), prefix + ": unique complete ledger")
            check({b["bag_id"] for b in ledger} == set(raw["expected_task_ids"]), prefix + ": task denominator")
            check(sum(b["completed_at"] is not None for b in ledger) == item["completed"], prefix + ": completions")
            check(sum(b["completed_at"] is not None and b["completed_at"] <= b["deadline"] for b in ledger) == item["on_time"], prefix + ": on time")
            if raw["status"] == "controller_quiescent":
                check(all(b["observed"] and b["completed_at"] is not None for b in ledger), prefix + ": full ledger completed")
                check(raw["last_cycle_state"]["transport_drained"] and raw["last_cycle_state"]["forecast_expired"], prefix + ": drain and expiry")
                check(result["cost_components"]["terminal_backlog"] == result["cost_components"]["terminal_inflight"] == 0, prefix + ": zero residual")
                wait = sum(b["load_time"] - b["arrival"] for b in ledger)
                check(wait == result["cost_components"]["tray_wait"], prefix + ": load-arrival wait accounting")
            row["guard_reasons"] = Counter()
            row["candidate_rejections"] = Counter()
            row["commits_by_domain"] = Counter()
            row["slow_queries_by_domain"] = Counter()
            row["slow_query_work_by_domain"] = Counter()
            row["slow_max_queries_by_domain"] = Counter()
            row["slow_quota_reached_calls"] = Counter()
            row["slow_candidate_budget_omissions"] = Counter()
            row["enhancement_blocked_reasons"] = Counter()
            row["max_guard_work_in_one_call"] = 0
            row["guard_work"] = 0
            row["guard_accepted"] = 0
            row["guard_budget_calls"] = 0
            row["demand_identity_deduplication_calls"] = 0
            row["bounded_slow_calls"] = Counter()
            for call in raw["slow_calls"]:
                check(all(f["published_at"] <= call["time"] for f in call["published_forecasts"]), prefix + ": no future publication")
                diagnostic = call.get("diagnostics", {})
                row["candidate_rejections"].update(r["reason"] for r in diagnostic.get("candidate_rejections", []))
                domain_calls = diagnostic.get("search_calls_by_domain", {"cross_zone": diagnostic.get("search_calls", 0)})
                row["slow_queries_by_domain"].update(domain_calls)
                row["slow_query_work_by_domain"].update(diagnostic.get("search_expansions_by_domain", {"cross_zone": diagnostic.get("search_expansions", 0)}))
                limits = diagnostic.get("limits", {})
                for domain, calls in domain_calls.items():
                    row["slow_max_queries_by_domain"][domain] = max(row["slow_max_queries_by_domain"][domain], calls)
                    limit = limits.get("max_candidates" if domain == "cross_zone" else "max_same_zone_candidates")
                    if limit is not None:
                        check(calls <= limit, prefix + ": domain candidate quota")
                        row["slow_quota_reached_calls"][domain] += int(calls >= limit)
                row["slow_candidate_budget_omissions"].update(diagnostic.get("candidate_budget_omissions", {}))
                blocked = diagnostic.get("same_zone_enhancement_blocked")
                if blocked:
                    row["enhancement_blocked_reasons"][blocked] += 1
                row["guard_work"] += diagnostic.get("guard_work", 0)
                row["max_guard_work_in_one_call"] = max(row["max_guard_work_in_one_call"], diagnostic.get("guard_work", 0))
                row["guard_budget_calls"] += int(diagnostic.get("guard_work", 0) >= diagnostic.get("limits", {}).get("max_guard_work", float("inf")))
                row["demand_identity_deduplication_calls"] += bool(diagnostic.get("duplicate_published_unit_ids_removed", []))
                if diagnostic.get("bounded_stop"):
                    row["bounded_slow_calls"][diagnostic["bounded_stop"]] += 1
                for guard in diagnostic.get("same_zone_guards", []):
                    reason = guard.get("reason")
                    row["guard_reasons"][reason or "accepted"] += 1
                    row["guard_accepted"] += reason is None
                    for p in guard["prefixes"]:
                        check(p["target_credit"] == int(p["tick"] >= guard["service_at"]), prefix + ": real target credit")
                        if reason is None:
                            check(p["other_after"] >= p["other_before"] and p["firm_other_after"] >= p["firm_other_before"] and p["after"] >= p["before"], prefix + ": accepted prefix preserved")
                details = {p["tray_id"]: p for p in diagnostic.get("proposal_details", [])}
                for proposal in call.get("proposals", []):
                    row["commits_by_domain"][details.get(proposal["tray_id"], {}).get("domain", "cross_zone")] += 1
            opportunities = raw["opportunities"]
            check(len(opportunities) == item["actual_loaded_generation_attempts"], prefix + ": all loaded attempts preserved")
            check(sum(o["candidate_count"] == 0 for o in opportunities) == item["loaded_zero_candidate_attempts"], prefix + ": zero candidate denominator")
            row["opportunity_candidate_counts"] = Counter(str(o["candidate_count"]) for o in opportunities)
            row["opportunity_roles"] = Counter()
            row["opportunity_public_observation_digests"] = []
            for opportunity in opportunities:
                state = opportunity["visible_state"]
                bag = state["bags"][opportunity["bag_id"]]
                node = opportunity["node"]
                role = "at_destination" if node == bag["destination"] else "at_origin" if node == bag["origin"] else "continuation"
                row["opportunity_roles"][role] += 1
                # Exact observed JSON only. Different continuation policies still
                # need different labels even when this observation is equal.
                row["opportunity_public_observation_digests"].append(digest({
                    k: opportunity[k] for k in ("time", "node", "bag_id", "tray_id", "cursor",
                        "next_slow_trigger_at", "candidates", "visible_state")}))
            records[stage, item["case_id"]] = compact(raw)
            row["physical_projection_sha256"] = records[stage, item["case_id"]]["physical_sha256"]

    pairs = []
    by_key = {(r["stage"], r["scene"], r["tape_id"], r["candidate"], r["policy"]): r for r in rows}
    for key, baseline in by_key.items():
        if key[-1] != "old32":
            continue
        for method in POLICIES[1:]:
            other = by_key.get((*key[:-1], method))
            if other is None:
                continue
            pair = {"stage": key[0], "scene": key[1], "tape_id": key[2], "candidate": key[3], "method": method,
                    "baseline_status": baseline["status"], "method_status": other["status"]}
            if all(r.get("total_cost") is not None and r["status"] == "controller_quiescent" for r in (baseline, other)):
                left = records[key[0], baseline["case_id"]]
                right = records[key[0], other["case_id"]]
                check(left["future_sha256"] == right["future_sha256"], str(key) + ": paired future")
                check(left["initial_sha256"] == right["initial_sha256"], str(key) + ": paired initial physical state")
                check(left["cache_sha256"] == right["cache_sha256"], str(key) + ": paired initial cache")
                check(left["expected_task_ids"] == right["expected_task_ids"], str(key) + ": paired task denominator")
                diffs = {k: right["cost_components"][k] - left["cost_components"][k] for k in WEIGHTS}
                changes = [{"bag_id": b, "baseline": left["completed"][b], "method": right["completed"][b],
                            "delta": right["completed"][b] - left["completed"][b]} for b in left["expected_task_ids"]
                           if right["completed"][b] != left["completed"][b]]
                pair.update(delta_cost=other["total_cost"] - baseline["total_cost"], delta_components=diffs,
                    delta_on_time=other["on_time"] - baseline["on_time"], completion_changes=changes,
                    exact_physical_tick_trace_equal=left["physical_sha256"] == right["physical_sha256"],
                    exact_event_trace_equal=left["trace_sha256"] == right["trace_sha256"],
                    exact_final_trays_equal=left["trays_sha256"] == right["trays_sha256"])
                old_obs = Counter(baseline["opportunity_public_observation_digests"])
                new_obs = Counter(other["opportunity_public_observation_digests"])
                pair["exact_public_observation_overlap"] = sum((old_obs & new_obs).values())
                pair["baseline_observations"] = sum(old_obs.values())
                pair["method_observations"] = sum(new_obs.values())
            pairs.append(pair)

    aggregates = []
    for stage in stages:
        for scope in ("all", "cross_cycle", "counterflow", "near_full"):
            for policy in POLICIES:
                group = [r for r in rows if r["stage"] == stage and r["policy"] == policy and (scope == "all" or r["scene"] == scope)]
                if not group:
                    continue
                aggregate = {"stage": stage, "scope": scope, "policy": policy, "runs": len(group),
                    "status_counts": dict(Counter(r["status"] for r in group)),
                    "cost_complete": all(r.get("total_cost") is not None and r["status"] == "controller_quiescent" for r in group)}
                for field in ("total_cost", "task_ledger_count", "completed", "on_time", "protected_expected", "protected_on_time", "search_calls", "search_work", "guard_work", "invocation_cpu_seconds", "actual_loaded_generation_attempts", "loaded_zero_candidate_attempts", "actual_selector_calls", "demand_identity_deduplication_calls", "guard_budget_calls"):
                    aggregate[field] = sum(r.get(field, 0) or 0 for r in group)
                aggregate["commits_by_domain"] = dict(sum((Counter(r.get("commits_by_domain", {})) for r in group), Counter()))
                aggregate["guard_reasons"] = dict(sum((Counter(r.get("guard_reasons", {})) for r in group), Counter()))
                for field in ("slow_queries_by_domain", "slow_query_work_by_domain", "slow_quota_reached_calls", "slow_candidate_budget_omissions", "bounded_slow_calls", "enhancement_blocked_reasons", "opportunity_candidate_counts", "opportunity_roles"):
                    aggregate[field] = dict(sum((Counter(r.get(field, {})) for r in group), Counter()))
                aggregate["max_guard_work_in_one_call"] = max(r.get("max_guard_work_in_one_call", 0) for r in group)
                aggregate["slow_max_queries_by_domain"] = {d: max(r.get("slow_max_queries_by_domain", {}).get(d, 0) for r in group) for d in ("cross_zone", "same_zone")}
                selected = [p for p in pairs if p["stage"] == stage and p["method"] == policy and (scope == "all" or p["scene"] == scope)]
                aggregate["paired_signs_against_old32"] = dict(Counter("unresolved" if "delta_cost" not in p else "better" if p["delta_cost"] < -1e-8 else "worse" if p["delta_cost"] > 1e-8 else "equal" for p in selected))
                aggregates.append(aggregate)

    mechanism = []
    for policy in POLICIES:
        group = [r for r in rows if r["stage"] == "mechanism" and r["policy"] == policy]
        if len(group) == 2 and all(r.get("total_cost") is not None for r in group):
            group.sort(key=lambda r: r["candidate"])
            mechanism.append({"policy": policy, "c0_cost": group[0]["total_cost"], "c1_cost": group[1]["total_cost"], "c1_minus_c0": group[1]["total_cost"] - group[0]["total_cost"]})
    repeat_checks = []
    if "full" in stages and "nominal_pilot" in stages:
        for r in rows:
            if r["stage"] != "nominal_pilot":
                continue
            pilot = records.get(("nominal_pilot", r["case_id"]))
            full = records.get(("full", r["case_id"]))
            if pilot and full:
                okay = all(pilot[key] == full[key] for key in ("physical_sha256", "event_suffix_sha256", "ledger_sha256", "stopped_at", "search_sha256"))
                check(okay, r["case_id"] + ": full nominal repeats pilot physics and searches")
                repeat_checks.append({"case_id": r["case_id"], "equal": okay})
    drift = [p for p, digest in bound.items() if sha(Path(p)) != digest]
    check(not drift, "input files unchanged during analysis")
    output = {"checks": checks, "errors": errors, "input_drift": drift, "base": str(base.resolve()),
        "stages": stages, "rows": rows, "pairs": pairs, "aggregates": aggregates, "mechanism": mechanism,
        "nominal_repeats": repeat_checks, "stage_resources": stage_resources,
        "analysis_cpu_seconds": process_time() - cpu, "analysis_wall_seconds": perf_counter() - wall,
        "qualifications": ["correlated reused development sources, no new independent operating days",
            "c1-c0 mechanism differences are conditional interventions, not additive deployed gain",
            "cost totals for unresolved groups are partial and must not be ranked", "guard matching preserves static upper bounds, not a jointly executable schedule",
            "public observation overlap is an exact JSON census, not permission to reuse value labels under a different continuation policy",
            "CASE_BUDGET route search_work excludes the separately measured guard work; equal candidate query caps do not mean equal total computation"]}
    write(out / "analysis.json", output)
    write(out / "input_manifest.json", bound)
    lines = ["# 第六轮完整供盘对照：纯原件分析", "", f"检查 {checks} 项，错误 {len(errors)}；没有调用仿真或策略。", "",
        "全部预声明方法、场景、tape均保留。三个合成开发源重复使用，未新增独立运营日。机制差值不能相加为部署收益。", "",
        "|阶段|范围|方法|运行数|J（完整时可比较）|完成/任务|准时|对old32 好/同/差|invocation CPU秒|", "|---|---|---|---:|---:|---:|---:|---|---:|"]
    for a in aggregates:
        s = a["paired_signs_against_old32"]
        lines.append(f"|{a['stage']}|{a['scope']}|{a['policy']}|{a['runs']}|{a['total_cost']:.3f}{'' if a['cost_complete'] else ' (partial)'}|{a['completed']}/{a['task_ledger_count']}|{a['on_time']}|{s.get('better',0)}/{s.get('equal',0)}/{s.get('worse',0)}|{a['invocation_cpu_seconds']:.3f}|")
    lines += ["", "## 机制6格", "", "|方法|c0 J|c1 J|c1−c0|", "|---|---:|---:|---:|"]
    for m in mechanism:
        lines.append(f"|{m['policy']}|{m['c0_cost']:.3f}|{m['c1_cost']:.3f}|{m['c1_minus_c0']:.3f}|")
    lines += ["", "逐tape全部配对、逐袋完成变化、同区实际承诺、guard拒因、预算与源绑定均在 analysis.json；未将成本下降自动解释为每袋服务改善。", "", "## 全部非零配对结果", "", "|阶段|场景/tape|c|方法|ΔJ|Δ准时|", "|---|---|---|---|---:|---:|"]
    for p in pairs:
        if abs(p.get("delta_cost", 0)) > 1e-8:
            lines.append(f"|{p['stage']}|{p['scene']}/{p['tape_id']}|{p['candidate']}|{p['method']}|{p['delta_cost']:.3f}|{p['delta_on_time']}|")
    if errors:
        lines += ["", "## 未通过的核对", ""] + ["- " + e for e in errors]
    (out / "ANALYSIS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write(out / "manifest.json", {p.name: sha(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps({k: output[k] for k in ("checks", "errors", "analysis_cpu_seconds", "analysis_wall_seconds", "mechanism")}, ensure_ascii=False))
    return bool(errors)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stages", nargs="+", default=["mechanism", "nominal_pilot", "full"])
    args = parser.parse_args()
    raise SystemExit(analyze(args.base, args.output, args.stages))
