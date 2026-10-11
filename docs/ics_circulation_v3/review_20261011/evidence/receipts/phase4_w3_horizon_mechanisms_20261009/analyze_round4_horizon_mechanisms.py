"""Read-only endpoint mechanism analysis; no simulations, fitting or source edits."""
from collections import Counter, defaultdict
from hashlib import sha256
import argparse
import json
from pathlib import Path
import shutil

WEIGHTS = {"tray_wait": 1.0, "nonprotected_tardiness": 1.0, "empty_distance": 0.1,
           "terminal_backlog": 10.0, "terminal_inflight": 2.0}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def mean(values):
    values = list(values)
    return sum(values) / len(values)


def main(source, output):
    summary = read(source / "analysis/summary.json")
    if summary["failures"] or summary["not_executed_requests"] or summary["completed_samples"] != 208:
        raise ValueError("Full 208-state physical outcomes required before mechanism summary")
    entries = read(source / "input_manifest.json")["selected"]
    labels = {}
    for path in (source / "owners").rglob("labels.json"):
        label = read(path)
        labels[label["identity"]] = (path, label)
    if len(entries) != 208 or len(labels) != 208 or {r['identity'] for r in entries} != set(labels):
        raise ValueError("Unique state identity denominator differs")
    indexed = {(r["identity"], r["horizon"], r["metric"]): r for r in summary["decisions"]}
    records, provenance = [], {}
    branch_totals = defaultdict(Counter)
    for entry in entries:
        identity = entry["identity"]
        path, label = labels[identity]
        expected = {(g, c, f) for g in range(4) for c in range(label['candidate_count']) for f in range(8)}
        actual = {(r['group'], r['candidate'], r['future_index']) for r in label['raw_branches']}
        if label['candidate_count'] != 4 or actual != expected or len(label['raw_branches']) != len(expected):
            raise ValueError('Raw request alignment differs from complete 4x4x8')
        if any(r["failed"] or not r["twenty_matches_historical"] for r in label["raw_branches"]):
            raise ValueError("Incomplete or unmatched label")
        provenance[path.relative_to(source).as_posix()] = digest(path)
        points = {}
        for h in (20, 40, 80):
            rows = label["raw_branches"]
            # Monte Carlo request weighting is deliberate, including exact
            # duplicate tapes. Counts here are not independent source groups.
            for row in rows:
                value = row["endpoints"][str(h)]
                components = value['cost_components']
                if set(components) != set(WEIGHTS):
                    raise ValueError('Cost component schema differs')
                free_value = sum(components[k] * WEIGHTS[k] for k in components if not k.startswith('terminal_'))
                terminal_value = sum(components[k] * WEIGHTS[k] for k in components if k.startswith('terminal_'))
                if (abs(free_value - value['nonterminal_cost_same_trajectory']) > 1e-8
                        or abs(terminal_value - value['terminal_cost']) > 1e-8
                        or abs(free_value + terminal_value - value['total_cost']) > 1e-8):
                    raise ValueError('Raw weighted component identity differs')
                branch_totals[h]["requests"] += 1
                branch_totals[h]["any_uncompleted"] += bool(value["uncompleted"])
                branch_totals[h]["uncompleted_bag_instances"] += len(value["uncompleted"])
                branch_totals[h]["observed_bag_instances"] += value["observed_bags"]
                branch_totals[h]["completed_bag_instances"] += len(value["completed"])
                branch_totals[h]["on_time_bag_instances"] += value["on_time"]
                branch_totals[h]["positive_terminal_cost"] += value["terminal_cost"] > 1e-9
            candidate_rows = [[r["endpoints"][str(h)] for r in rows if r["candidate"] == c]
                              for c in range(label["candidate_count"])]
            full = indexed[identity, h, "total_cost"]
            free = indexed[identity, h, "nonterminal_cost_same_trajectory"]
            rebuilt = [mean(r["total_cost"] for r in group) for group in candidate_rows]
            rebuilt_free = [mean(sum(r['cost_components'][k] * WEIGHTS[k] for k in WEIGHTS if not k.startswith('terminal_'))
                                 for r in group) for group in candidate_rows]
            best = [i for i, v in enumerate(rebuilt) if abs(v-min(rebuilt)) <= 1e-9]
            best_free = [i for i, v in enumerate(rebuilt_free) if abs(v-min(rebuilt_free)) <= 1e-9]
            if (len(full['means']) != 4 or len(free['means']) != 4
                    or any(abs(a-b) > 1e-8 for a, b in zip(rebuilt, full["means"]))
                    or any(abs(a-b) > 1e-8 for a, b in zip(rebuilt_free, free["means"]))
                    or best != full['optimal_indices'] or best_free != free['optimal_indices']
                    or (0 in best) != full['reference_is_optimal']
                    or (0 in best_free) != free['reference_is_optimal']):
                raise ValueError("Author summary cost differs from raw rows")
            points[str(h)] = {
                "means": rebuilt, "optimal_indices": full["optimal_indices"],
                "unload_optimal": full["reference_is_optimal"],
                "terminal_free_means": rebuilt_free,
                "terminal_free_optimal_indices": free["optimal_indices"],
                "terminal_free_unload_optimal": free["reference_is_optimal"],
                "terminal_means": [mean(r["terminal_cost"] for r in group) for group in candidate_rows],
                "component_means": [{k: mean(r["cost_components"][k] for r in group)
                                     for k in group[0]["cost_components"]} for group in candidate_rows],
                "completed_means": [mean(len(r["completed"]) for r in group) for group in candidate_rows],
                "uncompleted_means": [mean(len(r["uncompleted"]) for r in group) for group in candidate_rows],
                "on_time_means": [mean(r["on_time"] for r in group) for group in candidate_rows],
            }
        choice20 = min(points["20"]["optimal_indices"])
        choice40 = min(points["40"]["optimal_indices"])
        choice80 = min(points["80"]["optimal_indices"])
        records.append({"identity": identity, "owner": entry["owner"], "stream": entry["stream"],
                        "node": label["source_node"], "label": path.relative_to(source).as_posix(),
                        "choice20_first_index": choice20, "choice80_first_index": choice80,
                        "choice40_first_index": choice40,
                        "points": points,
                        "old_detour_better": not points["20"]["unload_optimal"],
                        "choice20_regret80": points["80"]["means"][choice20] - min(points["80"]["means"]),
                        "choice40_regret80": points["80"]["means"][choice40] - min(points["80"]["means"]),
                        "optimal_set40_agrees80": points['40']['optimal_indices'] == points['80']['optimal_indices'],
                        "unload_regret80": points["80"]["means"][0] - min(points["80"]["means"]),
                        "old_choice_advantage_over_unload": {
                            str(h): {"total": points[str(h)]["means"][0] - points[str(h)]["means"][choice20],
                                     "terminal": points[str(h)]["terminal_means"][0] - points[str(h)]["terminal_means"][choice20],
                                     "nonterminal": points[str(h)]["terminal_free_means"][0] - points[str(h)]["terminal_free_means"][choice20]}
                            for h in (20, 40, 80)}})
    grouped = []
    for field in ("all", "stream", "owner", "node"):
        groups = defaultdict(list)
        for r in records:
            groups["all" if field == "all" else r[field]].append(r)
        for name, group in sorted(groups.items()):
            grouped.append({"grouping": field, "group": name, "states": len(group),
                "detour_better_at_twenty": sum(r["old_detour_better"] for r in group),
                "old_detour_to_unload80": sum(r["old_detour_better"] and r["points"]["80"]["unload_optimal"] for r in group),
                "old_detour_state_has_detour_better80": sum(r["old_detour_better"] and not r["points"]["80"]["unload_optimal"] for r in group),
                "same_choice20_still_beats_unload80": sum(r["old_detour_better"] and r['old_choice_advantage_over_unload']['80']['total'] > 1e-9 for r in group),
                "unload20_to_detour80": sum(not r["old_detour_better"] and not r["points"]["80"]["unload_optimal"] for r in group),
                "unload_optimal80": sum(r["points"]["80"]["unload_optimal"] for r in group),
                "choice20_regret80_positive": sum(r["choice20_regret80"] > 1e-9 for r in group),
                "choice20_regret80_mean": mean(r["choice20_regret80"] for r in group),
                "choice20_regret80_max": max(r["choice20_regret80"] for r in group),
                "choice40_regret80_mean": mean(r["choice40_regret80"] for r in group),
                "choice40_regret80_positive": sum(r["choice40_regret80"] > 1e-9 for r in group),
                "optimal_set40_agrees80": sum(r["optimal_set40_agrees80"] for r in group)})
    # Deterministic illustration selection after results, explicitly descriptive.
    # This does not select training data, policies, seeds or experimental rows.
    illustrative = {}
    predicates = {
        "old_detour_reverses_at80": lambda r: r["old_detour_better"] and r["points"]["80"]["unload_optimal"],
        "old_detour_state_still_has_detour_at80": lambda r: r["old_detour_better"] and not r["points"]["80"]["unload_optimal"],
        "new_detour_at80": lambda r: not r["old_detour_better"] and not r["points"]["80"]["unload_optimal"],
    }
    for key, predicate in predicates.items():
        eligible = [r for r in records if predicate(r)]
        illustrative[key] = sorted(eligible, key=lambda r: (-max(r["choice20_regret80"], r["unload_regret80"]), r["identity"]))[:2]
    output.mkdir()
    shutil.copyfile(__file__, output / Path(__file__).name)
    result = {"schema": "ics_v3_round4_horizon_mechanisms_v1", "source": str(source.resolve()),
        "source_analysis_sha256": digest(source / "analysis/summary.json"),
        "input_manifest_sha256": digest(source / "input_manifest.json"),
        "labels_sha256": provenance, "cost_weights": WEIGHTS, "states": len(records), "records": records,
        "grouped": grouped, "request_weighted_branch_completion": branch_totals,
        "illustrations_posthoc_not_training_selection": illustrative,
        "limitations": ["All repeated owners and tapes remain correlated reused development data.",
                        "Terminal-free arithmetic values omit unfinished service and are not a replacement objective.",
                        "The fixed timed continuation differs from learned deployment; this is label sensitivity, not learned policy evaluation.",
                        "Finite horizon80 is not an infinite-horizon convergence certificate."]}
    (output / "mechanisms.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# 同一物理轨迹的时域敏感性", "", "只读全208状态原件；无新仿真、训练或策略选择。所有计数保留owner相关性，分支完成数按原32未来请求权重统计。", "",
             "| 时域 | 请求 | 有未完成任务的请求 | 正终端成本请求 | 完成任务实例 | 已观察任务实例 |", "|---|---:|---:|---:|---:|---:|"]
    for h, counts in sorted(branch_totals.items()):
        lines.append(f"| {h} | {counts['requests']} | {counts['any_uncompleted']} | {counts['positive_terminal_cost']} | {counts['completed_bag_instances']} | {counts['observed_bag_instances']} |")
    lines += ["", "| 流 | 状态 | 20时绕行更优 | 其中80时卸载最优 | 其中80时仍有绕行更优 | 新出现绕行优势 | 20选择在80的平均损失 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for g in grouped:
        if g["grouping"] in {"all", "stream"}:
            lines.append(f"| {g['group']} | {g['states']} | {g['detour_better_at_twenty']} | {g['old_detour_to_unload80']} | {g['old_detour_state_has_detour_better80']} | {g['unload20_to_detour80']} | {g['choice20_regret80_mean']:.6f} |")
    lines += ["", "全部owner/节点分层、逐状态成本分项、服务计数、事后示例和原件SHA见 `mechanisms.json`。去终端视图只是原轨迹算术，不是改目标后的优化；80tick也不证明无限时域收敛。"]
    (output / "MECHANISMS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files = {p.name: digest(p) for p in output.iterdir() if p.is_file()}
    (output / "manifest.json").write_text(json.dumps({"files_sha256": files}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"states": len(records), "all": grouped[0], "branch_completion": branch_totals}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    main(args.source, args.output)
