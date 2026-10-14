"""Read-only, complete-denominator analysis of frozen empty-control runs.

No experiment imports, simulations, fits, tuning, or changes to input records.
Positive/negative examples are explicitly post-hoc explanations, selected only
after recording every paired episode, never confirmation evidence.
"""
import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path


WEIGHTS = {"tray_wait": 1.0, "nonprotected_tardiness": 1.0,
           "empty_distance": .1, "terminal_backlog": 10., "terminal_inflight": 2.}
POLICIES = ("greedy", "legacy_empty12", "public_fast4", "empty2_h40",
            "empty12_h40", "empty24_h40", "empty24_h80")


def read(path):
    data = path.read_bytes()
    if path.suffix == ".gz":
        return json.loads(gzip.decompress(data)), sha256(data).hexdigest()
    return json.loads(data), sha256(data).hexdigest()


def action_signature(proposals, timing=True):
    return sorted((p["tray_id"], p["destination_node"],
        tuple((l["edge_id"], l["depart"], l["arrive"]) if timing else l["edge_id"] for l in p["legs"]))
        for p in proposals)


def change_kind(old, new):
    if old and not new:
        return "no_current_transfer"
    if new and not old:
        return "additional_prebalance"
    if action_signature(old, False) == action_signature(new, False):
        return "departure_time_change"
    donors_old = sorted((p["tray_id"], p["destination_node"]) for p in old)
    donors_new = sorted((p["tray_id"], p["destination_node"]) for p in new)
    if donors_old == donors_new:
        return "empty_path_change"
    if sorted(p["destination_node"] for p in old) == sorted(p["destination_node"] for p in new):
        return "donor_assignment_change"
    return "combined_transfer_change"


def main(source, output):
    if output.exists():
        raise ValueError("analysis output is immutable; choose a new directory")
    if not (source / "summary.json").exists():
        raise ValueError("complete formal summary is required")
    evidence = {}
    summary, evidence["summary.json"] = read(source / "summary.json")
    protocol, evidence["protocol.json"] = read(source / "protocol.json")
    inputs, evidence["inputs.json"] = read(source / "inputs.json")
    errors, checks = [], 0

    def check(ok, message):
        nonlocal checks
        checks += 1
        if not ok:
            errors.append(message)

    check(not protocol["pilot"], "formal comparison must not be a pilot")
    check(protocol["planned_episodes"] == 252, "expected 252 predeclared episodes")
    check(len(inputs) == 36, "expected all 36 tapes")
    check(len(summary["rows"]) == 252, "expected all 252 outcome rows")
    check(tuple(protocol["policies"]) == POLICIES, "policy set/order mismatch")
    for name, expected in protocol["source_sha256"].items():
        actual = sha256((source / "source_snapshot" / name).read_bytes()).hexdigest()
        evidence["source_snapshot/" + name] = actual
        check(actual == expected, "source snapshot hash mismatch: " + name)
    cases, accounting, changed = {}, {}, []
    inputs_by_key = {(r["scene"], r["tape"]): r for r in inputs}
    for row in summary["rows"]:
        key = (row["scene"], row["tape"], row["policy"])
        check(key not in cases, "duplicate case: " + str(key))
        item, file_hash = read(source / "cases" / row["file"])
        if "metrics" not in item:
            item = {**item, "metrics": dict(row)}
        evidence["cases/" + row["file"]] = file_hash
        check(row["sha256"] == file_hash, "case hash mismatch: " + row["identity"])
        check(not item.get("source_changed_during_case"), "source drift: " + row["identity"])
        cases[key] = item
        input_row = inputs_by_key[(row["scene"], row["tape"])]
        bags = dict(input_row["initial"]["bags"])
        bags.update((b["bag_id"], b) for b in input_row["actual_tasks_event_engine_only"])
        if "endpoints" not in item:
            accounting[key] = {"execution_failure": True, "cpu_seconds": row.get("invocation_cpu_seconds") or 0,
                "wall_seconds": row.get("invocation_wall_seconds") or 0,
                "invocation_accounting_missing": row.get("invocation_cpu_seconds") is None}
            continue
        for endpoint in ("h80", "final"):
            raw = item["endpoints"][endpoint]
            result, metrics = raw["result"], raw["metrics"]
            check(metrics == row[endpoint], "summary endpoint mismatch: " + row["identity"] + endpoint)
            check(abs(sum(WEIGHTS[k] * v for k, v in result["cost_components"].items()) - metrics["total_cost"]) < 1e-8,
                  "cost decomposition mismatch: " + row["identity"] + endpoint)
            check(metrics["completed"] == len(result["completed"]), "completion count mismatch")
            check(metrics["scheduled"] == len(bags), "scheduled denominator mismatch")
            on_time = sum(k in result["completed"] and result["completed"][k] <= b["deadline"] for k, b in bags.items())
            check(on_time == metrics["on_time"], "on-time ledger mismatch")
            check(sorted(set(bags) - set(result["completed"])) == metrics["unfinished"], "unfinished ledger mismatch")
        slow = item["slow_history"]
        rows = [r for h in slow for r in h["diagnostics"].get("scored_actions", ())]
        record = {"cpu_seconds": row["invocation_cpu_seconds"], "wall_seconds": row["invocation_wall_seconds"],
            "slow_proxy_rollouts": len(rows), "fast_proxy_rollouts": sum(len(r["rollouts"]) for r in item["public_rollouts"]),
            "outer_generation_calls": item["endpoints"]["final"]["result"]["policy_stats"]["generation_calls"],
            "outer_slow_calls": item["endpoints"]["final"]["result"]["policy_stats"]["slow_calls"]}
        check(record["slow_proxy_rollouts"] == row["physical_slow_proxy_rollouts"], "slow proxy count mismatch")
        check(record["fast_proxy_rollouts"] == row["physical_fast_proxy_rollouts"], "fast proxy count mismatch")
        if row["policy"].startswith("empty"):
            record.update(internal_queries=0, internal_work=0, omitted_identical_requests=0,
                incomplete_projections=0, fallback_calls=0, changed_actions=0,
                proposal_unsearched_requests=0, proposal_pool_discarded_valid=0, unscored_enumerated_actions=0)
            for h in slow:
                d = h["diagnostics"]
                score = d["scored_actions"]
                record["internal_queries"] += d["greedy_diagnostics"]["search_calls"] + d["proposal_search_calls"] + sum(r["search_calls"] for r in score)
                record["internal_work"] += d["greedy_diagnostics"]["search_expansions"] + d["proposal_search_work"] + sum(r["search_work"] for r in score)
                record["omitted_identical_requests"] += d.get("mandatory_identical_actions_not_simulated", 0)
                record["incomplete_projections"] += sum(r["status"] != "complete" for r in score)
                record["fallback_calls"] += d["fallback_to_greedy"]
                for field in ("proposal_unsearched_requests", "proposal_pool_discarded_valid", "unscored_enumerated_actions"):
                    record[field] += d[field]
                check(all(f["published_at"] <= h["trigger_time"] for f in d["published_forecasts"]), "unpublished forecast in decision")
                check(d["next_slow_trigger_at"] > h["trigger_time"], "next slow clock is not in future")
                if not score:
                    check(d["status"] == "identical_no_demand_action" and d["proposal_count"] == 0,
                          "unexplained projection omission")
                    continue
                check(score[0]["kind"] == "greedy_incumbent" and score[1]["kind"] == "no_transfer", "mandatory branch order")
                if d["fallback_to_greedy"]:
                    check(d["selected_action_index"] == 0 and d["selected_proxy_cost"] is None, "invalid fallback cost/action")
                else:
                    selected = score[d["selected_action_index"]]
                    check(selected["status"] == "complete", "partial projection used for action selection")
                    complete = [r for r in score if r["status"] == "complete"]
                    check(selected["proxy_cost"] <= min(r["proxy_cost"] for r in complete) + 1e-8,
                          "selected proxy action is not minimum among complete branches")
                    check(selected["proxy_cost"] <= score[0]["proxy_cost"] + 1e-8,
                          "selected proxy is worse than mandatory incumbent")
                if d["actual_sequence_changed"]:
                    record["changed_actions"] += 1
                    selected = score[d["selected_action_index"]]
                    check(action_signature(score[0]["proposals"]) != action_signature(selected["proposals"]), "false change flag")
                    check(action_signature(h["proposals"]) == action_signature(selected["proposals"]), "selected vs actually committed mismatch")
                    changed.append({"case": row["identity"], "scene": row["scene"], "tape": row["tape"], "policy": row["policy"],
                        "time": h["trigger_time"], "kind": change_kind(score[0]["proposals"], selected["proposals"]),
                        "greedy": score[0]["proposals"], "selected": selected["proposals"],
                        "greedy_proxy_cost": score[0]["proxy_cost"], "selected_proxy_cost": selected["proxy_cost"],
                        "proxy_delta": selected["proxy_cost"] - score[0]["proxy_cost"], "selected_ordinal": selected["ordinal"],
                        "snapshot_sha256": d["snapshot_sha256"], "proxy_bags": d["proxy_bags"]})
            check(record["internal_queries"] == row["new_method_internal_search_calls"], "internal query ledger mismatch")
            check(record["internal_work"] == row["new_method_internal_search_work"], "internal work ledger mismatch")
            check(record["changed_actions"] == row["changed_greedy_actions"], "changed action count mismatch")
        accounting[key] = record

    pairs, group_rows = [], []
    for input_row in inputs:
        for policy in POLICIES[1:]:
            base = cases[(input_row["scene"], input_row["tape"], "greedy")]
            item = cases[(input_row["scene"], input_row["tape"], policy)]
            row = {"scene": input_row["scene"], "tape": input_row["tape"], "policy": policy,
                "case": item["identity"], "baseline_case": base["identity"],
                "both_complete_runs": "endpoints" in base and "endpoints" in item}
            if row["both_complete_runs"]:
                for end in ("h80", "final"):
                    a, b = item["endpoints"][end]["metrics"], base["endpoints"][end]["metrics"]
                    row[end] = {"delta": a["total_cost"] - b["total_cost"],
                        "cost": a["total_cost"], "baseline_cost": b["total_cost"],
                        "completed_delta": a["completed"] - b["completed"], "on_time_delta": a["on_time"] - b["on_time"],
                        "components_delta": {k: a["cost_components"][k] - b["cost_components"][k] for k in WEIGHTS}}
            pairs.append(row)
    for policy in POLICIES:
        selected = [(key, c) for key, c in cases.items() if key[2] == policy]
        for scope in ("all", "nominal", "stress"):
            subset = [(key, c) for key, c in selected if scope == "all" or (key[1] == "nominal") == (scope == "nominal")]
            row = {"policy": policy, "scope": scope, "runs": len(subset),
                "quiescent": sum(c["metrics"]["status"] == "controller_quiescent" for _, c in subset),
                "statuses": dict(Counter(c["metrics"]["status"] for _, c in subset)),
                "accounting": {k: sum(accounting[key].get(k, 0) for key, _ in subset)
                    for k in ("cpu_seconds", "wall_seconds", "slow_proxy_rollouts", "fast_proxy_rollouts", "internal_queries", "internal_work",
                              "omitted_identical_requests", "incomplete_projections", "fallback_calls", "changed_actions")}}
            for end in ("h80", "final"):
                complete = [c["endpoints"][end]["metrics"] for _, c in subset if "endpoints" in c]
                matched = [p[end] for p in pairs if p["policy"] == policy and p["both_complete_runs"]
                    and (scope == "all" or (p["tape"] == "nominal") == (scope == "nominal"))]
                row[end] = {"observed_runs": len(complete), "cost": sum(m["total_cost"] for m in complete),
                    "scheduled": sum(m["scheduled"] for m in complete), "completed": sum(m["completed"] for m in complete),
                    "on_time": sum(m["on_time"] for m in complete), "pairs": len(matched),
                    "better": sum(p["delta"] < -1e-8 for p in matched), "equal": sum(abs(p["delta"]) <= 1e-8 for p in matched),
                    "worse": sum(p["delta"] > 1e-8 for p in matched), "paired_delta": sum(p["delta"] for p in matched)}
            group_rows.append(row)

    # Explanatory examples are chosen AFTER the entire matrix is retained.
    # Extremes per policy are visibly post-hoc, never new validation episodes.
    examples = []
    for policy in POLICIES[3:]:
        available = [p for p in pairs if p["policy"] == policy and p["both_complete_runs"]]
        for label, subset in (("largest_final_gain", [p for p in available if p["final"]["delta"] < -1e-8]),
                              ("largest_final_loss", [p for p in available if p["final"]["delta"] > 1e-8])):
            if not subset:
                examples.append({"policy": policy, "selection": label, "available": False})
                continue
            pair = sorted(subset, key=lambda p: ((p["final"]["delta"] if label == "largest_final_gain" else -p["final"]["delta"]), p["case"]))[0]
            item = cases[(pair["scene"], pair["tape"], policy)]
            base = cases[(pair["scene"], pair["tape"], "greedy")]
            event = next((r for r in changed if r["case"] == pair["case"]), None)
            inp = inputs_by_key[(pair["scene"], pair["tape"])]
            bags = dict(inp["initial"]["bags"])
            bags.update((b["bag_id"], b) for b in inp["actual_tasks_event_engine_only"])
            result, old_result = item["endpoints"]["final"]["result"], base["endpoints"]["final"]["result"]
            ledger = [{"bag_id": k, "origin": b["origin"], "destination": b["destination"], "arrival": b["arrival"], "deadline": b["deadline"],
                "greedy_load": old_result["final_snapshot"]["load_times"].get(k), "new_load": result["final_snapshot"]["load_times"].get(k),
                "greedy_complete": old_result["completed"].get(k), "new_complete": result["completed"].get(k)} for k, b in sorted(bags.items())]
            differences, same_prefix = [], None
            if event:
                for proxy in event["proxy_bags"]:
                    actual = bags.get(proxy["bag_id"])
                    keys = ("origin", "destination", "arrival", "deadline")
                    diff = [k for k in keys if actual is None or proxy[k] != actual[k]]
                    if diff:
                        differences.append({"proxy": proxy, "actual": actual, "different_fields": diff,
                            "meaning": "posthoc_prediction_disagreement_not_a_causal_ablation"})
                old_at_tick = next((r for r in base["slow_history"] if r["trigger_time"] == event["time"]), None)
                same_prefix = {"incumbent_matches_greedy_actual_at_tick": old_at_tick is not None and old_at_tick["proposals"] == event["greedy"],
                    "past_physical_trace_equal": [r for r in old_result["trace"] if r["time"] < event["time"]]
                        == [r for r in result["trace"] if r["time"] < event["time"]],
                    "loaded_decisions_through_current_tick_equal": [r for r in base["route_history"] if r["time"] <= event["time"]]
                        == [r for r in item["route_history"] if r["time"] <= event["time"]]}
            examples.append({"policy": policy, "selection": label, "available": True, "pair": pair,
                "first_changed_action": event, "first_change_prefix_checks": same_prefix,
                "public_proxy_actual_differences": differences, "task_ledger": ledger,
                "greedy_trace": old_result["trace"], "new_trace": result["trace"],
                "causal_limit": "trajectory chain comparison; repeated downstream decisions can change; no independent single-edge/forecast-error ablation"})

    budget_pairs = []
    for a, b in (("empty2_h40", "empty12_h40"), ("empty12_h40", "empty24_h40"), ("empty24_h40", "empty24_h80")):
        deltas = []
        for inp in inputs:
            x, y = cases[(inp["scene"], inp["tape"], a)], cases[(inp["scene"], inp["tape"], b)]
            if "endpoints" in x and "endpoints" in y:
                deltas.append({"scene": inp["scene"], "tape": inp["tape"],
                    **{end: y["endpoints"][end]["metrics"]["total_cost"] - x["endpoints"][end]["metrics"]["total_cost"] for end in ("h80", "final")}})
        budget_pairs.append({"base": a, "alternative": b, "pairs": deltas,
            "final_delta": sum(r["final"] for r in deltas), "better": sum(r["final"] < -1e-8 for r in deltas),
            "equal": sum(abs(r["final"]) <= 1e-8 for r in deltas), "worse": sum(r["final"] > 1e-8 for r in deltas)})
    stream_pairs = []
    for scene in sorted({r["scene"] for r in inputs}):
        for policy in POLICIES[1:]:
            subset = [p for p in pairs if p["scene"] == scene and p["policy"] == policy]
            stream_pairs.append({"scene": scene, "policy": policy, "planned_pairs": len(subset),
                "complete_pairs": sum(p["both_complete_runs"] for p in subset),
                **{end: {"delta": sum(p[end]["delta"] for p in subset if p["both_complete_runs"]),
                    "better": sum(p["both_complete_runs"] and p[end]["delta"] < -1e-8 for p in subset),
                    "equal": sum(p["both_complete_runs"] and abs(p[end]["delta"]) <= 1e-8 for p in subset),
                    "worse": sum(p["both_complete_runs"] and p[end]["delta"] > 1e-8 for p in subset)} for end in ("h80", "final")}})
    categories = []
    for p in pairs:
        if not p["policy"].startswith("empty"):
            continue
        kinds = sorted({r["kind"] for r in changed if r["case"] == p["case"]})
        categories.append({"case": p["case"], "policy": p["policy"], "scene": p["scene"], "tape": p["tape"],
            "kinds_observed": kinds, "final_delta": p.get("final", {}).get("delta"),
            "interpretation": "episode-level association; multiple downstream effects and changed actions are not isolated"})
    # Recheck all inputs after analysis. This module never writes to source.
    for relative, expected in evidence.items():
        check(sha256((source / relative).read_bytes()).hexdigest() == expected, "input changed during analysis: " + relative)
    payload = {"schema": "ics_round5_empty_mechanisms_v1", "source": str(source.resolve()),
        "checks": checks, "errors": errors, "input_sha256": evidence, "groups": group_rows,
        "pairs": pairs, "changed_actions": changed, "change_kinds": dict(Counter(r["kind"] for r in changed)),
        "stream_pairs": stream_pairs, "trajectory_change_categories": categories,
        "case_accounting": [{"scene": k[0], "tape": k[1], "policy": k[2], **v} for k, v in accounting.items()],
        "budget_horizon_pairs": budget_pairs, "examples": examples,
        "limits": ["same reused development streams/tapes; no fit or independent confirmation",
            "new chosen proxy cost is conditional on timed/greedy continuation; repeated deployment differs",
            "public forecasts are imperfect; posthoc disagreement is not proof of causal loss",
            "new method/legacy have different proxy continuation and conservative unadmitted guard domain",
            "sum worker CPU differs from parallel wall; process lifetime peaks are not aggregate concurrent RAM"]}
    output.mkdir(parents=True)
    (output / "analysis.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "analyze.py").write_bytes(Path(__file__).read_bytes())
    lines = ["# 直接空盘控制：完整252次开发对照的只读分析", "",
        f"重读全部原件及来源，{checks}项记录核对，错误{len(errors)}。未新增仿真、拟合或改参；所有252次结果纳入，以下不是独立确认。", "",
        "| 策略 | 运行 | final J | ΔJ vs greedy | 改善/相同/变差 | 完成/任务 | 准时 | CPU秒 | 空调proxy调用 |", "|---|---:|---:|---:|---|---|---:|---:|---:|"]
    for r in group_rows:
        if r["scope"] != "all":
            continue
        f, a = r["final"], r["accounting"]
        lines.append(f"| {r['policy']} | {r['runs']} | {f['cost']:.3f} | {f['paired_delta']:+.3f} | {f['better']}/{f['equal']}/{f['worse']} | {f['completed']}/{f['scheduled']} | {f['on_time']} | {a['cpu_seconds']:.2f} | {a['slow_proxy_rollouts']} |")
    lines.extend(["", "final指runner预声明的任务全到达、已完成、空盘运输排空、全部预测过TTL并经历真实慢层触发后的端点；若未满足则保留截断。h80和final全部216对、名义/压力分层、所有分项和预算细账在analysis.json。", "",
        "## 预算与评价窗口", "", "| 基础→增量 | final ΔJ | 改善/相同/变差 |", "|---|---:|---|"])
    for r in budget_pairs:
        lines.append(f"| {r['base']}→{r['alternative']} | {r['final_delta']:+.3f} | {r['better']}/{r['equal']}/{r['worse']} |")
    lines.extend(["", "逻辑work包括新方法greedy构造、增强候选构造、每个proxy内fast/reactive/greedy查询；实际外层执行query另列。所有部分proxy禁止参加成本排名。no-demand省略只证明当前声明候选域只有同一空序列，未将其计为已执行回放或缓存命中。", "",
        "## 实际动作与机制限制", "", f"完整changed-action类别计数：{dict(Counter(r['kind'] for r in changed))}。", "",
        "以下每种新策略取final收益最大和损失最大的已完成配对作事后解释；不存在该符号时明确为空。它们不参与budget/参数选择，也不替代完整分母。预测偏差只按已保存公开proxy与真实tape对读，不能据此独立归因。"])
    for e in examples:
        lines.extend(["", f"### {e['policy']} / {e['selection']}", ""])
        if not e["available"]:
            lines.append("完整分母中没有此符号的配对。")
            continue
        p, event = e["pair"], e["first_changed_action"]
        lines.append(f"{p['scene']} / {p['tape']}，final ΔJ={p['final']['delta']:+.3f}，h80 ΔJ={p['h80']['delta']:+.3f}。")
        lines.append("分项Δ（空驶为原量，目标权重0.1）：" + str(p["final"]["components_delta"]) + "。")
        if event:
            lines.append(f"首个增强动作发生于t{event['time']}，类别{event['kind']}，proxy ΔJ={event['proxy_delta']:+.3f}。首变化前核对：{e['first_change_prefix_checks']}。")
            lines.append(f"该点保存proxy中与实际tape不一致的任务{len(e['public_proxy_actual_differences'])}个；动作的盘身份/目的地/每段预约以及完整trace均保存在JSON。")
        lines.extend(["", "| 任务 | OD | 到达/截止 | 装载：greedy→新 | 完成：greedy→新 |", "|---|---|---|---|---|"])
        for b in e["task_ledger"]:
            lines.append(f"| {b['bag_id']} | {b['origin']}→{b['destination']} | {b['arrival']}/{b['deadline']} | {b['greedy_load']}→{b['new_load']} | {b['greedy_complete']}→{b['new_complete']} |")
    lines.extend(["", "原greedy无额外unadmitted-protected阻断；旧Bounded在该状态只允许no-transfer；新方法保留mandatory greedy/no-transfer而禁止增强序列，三者保守动作域差异显式存在。最终硬许可仍由同一个ExecutionValidator检查。不得将这次开发集收益称为真实未来支配、递归MPC最优或原图已验证改善。", ""])
    (output / "MECHANISMS.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"checks": checks, "errors": errors, "case_count": len(cases), "paired_count": len(pairs),
                      "changed_actions": len(changed), "output": str(output)}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.source, args.output)
