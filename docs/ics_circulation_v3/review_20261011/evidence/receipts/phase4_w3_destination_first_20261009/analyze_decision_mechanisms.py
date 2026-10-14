"""Read saved records only; write independent post-hoc diagnostics, never replay.

Run from any directory: python /absolute/path/to/this/file.py
The frozen protocol, manifests, source snapshots and unit folders are inputs.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEIGHTS = {"tray_wait": 1, "nonprotected_tardiness": 1,
           "empty_distance": .1, "terminal_backlog": 10, "terminal_inflight": 2}
CASES = (
    ("A_on_time_regression", "stream_L2_D1_slack3", "stress_1", "shared__physical31__paired_direct_seed17"),
    ("B_cost_regression_other_seed", "stream_L4_D3_slack0", "stress_3", "shared__physical31__paired_direct_seed29"),
    ("C_positive_loop_interruption", "stream_L4_D1_slack3", "nominal", "r0__paired23__paired_direct_seed43"),
    ("D_repeated_cost_regression", "stream_L2_D3_slack0", "stress_6", "shared__physical31__paired_direct_seed17"),
)
READ_HASHES: dict[str, str] = {}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    READ_HASHES[path.relative_to(ROOT).as_posix()] = sha(path)
    return json.loads(path.read_text(encoding="utf-8"))


def link(path: Path, label: str) -> str:
    return f"[{label}](<{path.as_posix()}>)"


def alias(policy: str) -> str:
    if policy in ("baseline", "timed"):
        return policy
    stage, schema, method = policy.split("__")
    kind, seed = method.rsplit("_seed", 1)
    return f"{stage.upper()}-{schema.removeprefix('paired').removeprefix('physical')}-{'D' if kind == 'paired_direct' else 'R'}{seed}"


def build_case(case):
    name, stream, realization, policy = case
    folder = ROOT / "units" / f"{stream}__{realization}"
    inputs = read(folder / "inputs.json")
    episodes = {v: read(folder / f"{policy}__{v}.json") for v in ("original", "destination_first")}
    a, b = episodes.values()
    assert a["metrics"]["input_sha256"] == b["metrics"]["input_sha256"] == inputs["input_sha256"]
    overrides = [i for i, d in enumerate(b["destination_first_history"]) if d["overridden"]]
    assert overrides
    first = overrides[0]
    old, new = (episodes[v]["destination_first_history"][first] for v in episodes)
    assert old["delegate_records"] == new["delegate_records"]
    assert a["route_history"][first]["candidates"] == b["route_history"][first]["candidates"]
    assert old["delegate_choice"] == new["delegate_choice"]
    assert new["chosen"]["legs"] == [] and not new["chosen"]["prefix_only"]
    assert any(r["index"] == new["chosen_index"] and r["accepted"] for r in new["unload_validation"])
    bags = dict(inputs["initial"]["bags"])
    bags.update({x["bag_id"]: x for x in inputs["actual_tape_event_engine_only"]})
    per_bag = []
    for bag_id, bag in bags.items():
        item = {"bag": bag}
        for variant, d in episodes.items():
            load = d["result"]["final_snapshot"]["load_times"].get(bag_id)
            complete = d["result"]["completed"].get(bag_id)
            item[variant] = {
                "load_at": load, "complete_at": complete,
                "preload_wait": max(0, (inputs["horizon"] if load is None else load) - bag["arrival"]),
                "tardiness_at_horizon": 0 if bag["protected"] else max(0, (inputs["horizon"] if complete is None else complete) - bag["deadline"]),
                "on_time": complete is not None and complete <= bag["deadline"],
            }
        per_bag.append(item)
    extracted = {}
    for variant, d in episodes.items():
        c = d["metrics"]["cost_components"]
        assert abs(sum(c[k] * w for k, w in WEIGHTS.items()) - d["metrics"]["total_cost"]) < 1e-8
        assert sum(x[variant]["preload_wait"] for x in per_bag) == c["tray_wait"]
        assert sum(x[variant]["tardiness_at_horizon"] for x in per_bag) == c["nonprotected_tardiness"]
        extracted[variant] = {
            "artifact": (folder / f"{policy}__{variant}.json").relative_to(ROOT).as_posix(),
            "artifact_sha256": sha(folder / f"{policy}__{variant}.json"),
            "metrics": d["metrics"],
            "decisions": [{"decision_index": i, **x} for i, x in enumerate(d["destination_first_history"])],
            "event_trace": [{"trace_index": i, **x} for i, x in enumerate(d["result"]["trace"]) if x["event"] != "tick"],
            "slow_proposals": [{"slow_history_index": i, **x} for i, x in enumerate(d["slow_history"]) if x["proposals"]],
            "final_trays": d["result"]["final_trays"],
        }
    return {
        "case_id": name, "stream": stream, "realization": realization, "policy": policy,
        "selection": "post_hoc_explanatory_example_not_an_independent_confirmation_or_method_selection",
        "input_sha256": inputs["input_sha256"], "horizon": inputs["horizon"],
        "first_override_index": first, "all_override_indices": overrides,
        "first_override_same_prior_observation_and_pool": True,
        "delta_total_cost": round(b["metrics"]["total_cost"] - a["metrics"]["total_cost"], 8),
        "delta_raw_components": {k: b["metrics"]["cost_components"][k] - a["metrics"]["cost_components"][k] for k in WEIGHTS},
        "per_bag": per_bag, "episodes": extracted,
    }


def table(aggregate) -> str:
    order = ["baseline", "timed"] + [p for p in aggregate if p not in ("baseline", "timed")]
    lines = ["| 策略 | 完成/任务：原→规则 | 准时：原→规则 | ΣJ 原→规则 | ΔΣJ | 成本好/同/差 | 实际覆盖 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for policy in order:
        r = aggregate[policy]
        a, b = r["original"], r["destination_first"]
        assert not r["failed_pairs"] and r["successful_pairs"] == r["planned_pairs"]
        delta = r["completed_pair_cost_delta_sum"]
        assert abs(delta - (b["cost_sum_successful_runs"] - a["cost_sum_successful_runs"])) < 1e-7
        assert abs(delta - sum(r["completed_pair_component_delta_sums"][k] * w for k, w in WEIGHTS.items())) < 1e-7
        count = r["completed_pair_cost_better_equal_worse"]
        lines.append(f"| {alias(policy)} | {a['completed']}→{b['completed']}/{a['scheduled_bags_all_runs']} | {a['on_time']}→{b['on_time']} | {a['cost_sum_successful_runs']:.1f}→{b['cost_sum_successful_runs']:.1f} | {delta:+.1f} | {count['better']}/{count['equal']}/{count['worse']} | {b['overrides']} |")
    return "\n".join(lines)


def bag_table(case) -> str:
    lines = ["| 任务（实际 origin→destination） | 到达/截止 | 装载：原→规则 | 卸载完成：原→规则 | 缺盘等待Δ | 迟到tick Δ |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in case["per_bag"]:
        bag = row["bag"]
        a, b = row["original"], row["destination_first"]
        def fmt(v):
            return "未完成" if v is None else str(v)
        lines.append(f"| `{bag['bag_id']}` ({bag['origin']}→{bag['destination']}) | {bag['arrival']}/{bag['deadline']} | {fmt(a['load_at'])}→{fmt(b['load_at'])} | {fmt(a['complete_at'])}→{fmt(b['complete_at'])} | {b['preload_wait']-a['preload_wait']:+} | {b['tardiness_at_horizon']-a['tardiness_at_horizon']:+} |")
    return "\n".join(lines)


def episode_links(case) -> str:
    return "；".join(link(ROOT / case["episodes"][v]["artifact"], label) for v, label in (("original", "原版 episode"), ("destination_first", "规则版 episode")))


def main():
    summary = read(ROOT / "summary.json")
    paired = read(ROOT / "paired_summary.json")
    remaining = read(ROOT / "remaining_tasks_diagnostic.json")
    read(ROOT / "manifest.json")
    assert paired["input_summary_sha256"] == sha(ROOT / "summary.json") == remaining["input_summary_sha256"]
    assert summary["episodes"] == 1872 and len(summary["records"]) == 1872
    assert not summary["failures"] and not summary["original_physics_mismatches"]
    records = {}
    for r in summary["records"]:
        records.setdefault((r["stream"], r["realization"], r["policy"]), {})[r["variant"]] = r
    assert len(records) == 936 and all(set(v) == {"original", "destination_first"} for v in records.values())
    outcomes = Counter()
    for row in records.values():
        a, b = row["original"], row["destination_first"]
        delta = b["total_cost"] - a["total_cost"]
        outcomes["better" if delta < -1e-8 else "worse" if delta > 1e-8 else "equal"] += 1
    assert dict(outcomes) == {"equal": 541, "better": 236, "worse": 159}
    cases = [build_case(case) for case in CASES]
    nominal_table, stress_table = (table(paired["aggregates"][regime]) for regime in ("nominal", "stress"))
    unfinished = ["| 场景 / tape | 策略 | 未完成任务 / 实际 OD | 该袋决策次数 | 到目的地决策/覆盖次数 |",
                  "|---|---|---|---:|---:|"]
    for row in remaining["details"]:
        b = row["bag"]
        assert row["at_destination_calls"] == row["unload_eligible_calls"] == row["overrides_for_this_bag"] == 0
        unfinished.append(f"| {row['stream'].removeprefix('stream_')} / {row['realization']} | {link(ROOT/row['source_artifact'],alias(row['policy']))} | `{b['bag_id']}` {b['origin']}→{b['destination']} | {row['calls']} | 0 / 0 |")
    evidence = {
        "read_only_saved_record_analysis": True, "new_simulations": 0, "new_fits": 0,
        "paired_outcomes": dict(outcomes), "cases": cases, "source_input_hashes": READ_HASHES,
        "limits": ["Examples selected after seeing outcomes; no rule tuning or method selection.",
                   "All 36 reused development tapes; not a new generalization evaluation.",
                   "First override has equal prior observation/pool; later differences are closed-loop trajectories, not isolated one-step causal effect estimates.",
                   "Candidate witnesses are not entire executed routes in next-edge mode; event traces determine actual motion."]}
    (ROOT / "decision_mechanism_evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    A, B, C, D = cases
    report = f"""# Destination-first：完整分母与事后机制诊断

本文件仅分析已冻结的 1,872 个 episode，未新增仿真、训练、调参或规则修改。所有例子均为**事后解释性选择**，不是新的独立确认、模型选择或支配性证明。生成脚本：{link(ROOT/'analyze_decision_mechanisms.py','analyze_decision_mechanisms.py')}；逐项事件、原始评分、候选、每袋时刻及来源 SHA：{link(ROOT/'decision_mechanism_evidence.json','decision_mechanism_evidence.json')}。

## 整体结果与读法

36 个已使用过的名义/压力 tape × 26 个冻结策略 × 原版/规则版 = **1,872 次运行、936 对**。没有执行异常；936 个原版全部复现各自历史物理结果。规则版不是统一改善：成本 **236 对降低、541 对相同、159 对升高**。两侧各有 5,148 个任务实例，完成数 **4,960→5,137**，准时数 **3,628→3,886**，ΣJ **23,871.4→15,751.2**。规则仍有 11 个未完成任务，详见下表。独立审计已保存于 {link(ROOT.parent/'phase4_w3_diagnostic_audit_20261009/destination_audit_final.json','destination_audit_final.json')}，101,586 项检查没有错误。

固定代价为 `J = tray_wait + nonprotected_tardiness + 0.1×empty_distance + 10×terminal_backlog + 2×terminal_inflight`。`tray_wait` 仅累计尚未装载的已到达任务；途中时间和已装载后的等待不直接计入该项。`nonprotected_tardiness` 是迟到 tick 之和，未完成任务计至 horizon；它不是“不准时任务数”。`empty_distance` 在本离散代理中累计空行驶边的 travel_time。故减少缺盘等待可以伴随更晚的完成，也可能出现 ΣJ 改善但二元准时率下降；本轮不存在另加的准时个数硬罚。所有实际候选仍需正常权限与容量校验。

全表保留全部策略及 seed。R0 是原始训练，R1 是各自策略回收，SHARED 是每折六 owner 共同回收数据；23/31 为特征数，D/R 分别为 paired_direct/residual，尾数为 seed。`原→规则` 是同策略同 tape 的配对值，`ΔΣJ=规则−原`，负数较好；好/同/差是逐 episode 成本比较。完成与准时分母使用全部计划任务，失败不从分母排除（本轮没有执行异常）。baseline/timed 的合法卸载本已在第一动作完成，所以没有实际覆盖。

### 名义（每策略 4 对、24 个任务实例）

{nominal_table}

### 压力（每策略 32 对、174 个任务实例；复用旧 8 个 stress tape/stream）

{stress_table}

这些总数不能把较弱 R0-23 的大收益外推给更强模型。例如 SHARED-31-D17 压力 ΣJ 增加 **32.7**、准时 **135→134**；SHARED-31-D29 压力 ΣJ 增加 **54.3**，但准时 **128→130**。准时数与总代价是不同统计量；全部 seed 均保留，没有挑最好 seed。

## A：一次真实卸载覆盖，随后空盘调拨竞争导致少一个准时任务

**SHARED-31-D17，L2_D1_slack3 / stress_1**。{episode_links(A)}。所有数组索引均为 **0-based JSON 数组索引**。

`destination_first_history[4]` 是首次且唯一覆盖：t=28，`round1:need` 在最终目的地 C、盘 `donor`；两版 `delegate_records[0].state_sha256` 和 K4 池相同。原评分为 `[0, -0.131861, -0.128647, -0.037551]`，原选择 index 1 的离站见证，规则选择经校验的 index 0：`legs=[]`、`prefix_only=false`，t=29 卸载完成。原版在 C→S→B 的实际反复运动后，至 t=41 才完成同一袋。这里不是把 witness 整条当成执行；路径由 `result.trace` 确认。

卸载后的实际耦合链如下：

1. 规则 `slow_history[17]` 在 t=34 接纳 donor 的完整空盘调拨：`CS[40,41), SX[41,43), XB[43,44)`，供应未来 B 队列。原版 donor 此时仍带袋绕行，直到 `slow_history[21]` t=42 才空盘调拨 `CS[42,43), SX[43,45), XB[45,46)`。
2. t=38，另一盘 `loaded` 从 G 反应式返回 S，服务已到达的 `round2:loaded`。原版 `trace[103,107,109,114]` 为 GC 出发38、C到达40、CS出发40、S装载41；规则 `trace[89,93,97,101]` 为 GC出发38、C到达40、CS出发41、S装载42。CS 容量为1，规则 donor 的 `[40,41)` 实际占用导致这一次推迟。
3. 规则 S 的 `destination_first_history[5]` 是正常 delegate 选路，**没有卸载覆盖**：SX 只能在43出发（donor 正占 `[41,43)`），XG45→47，48卸载。原版 `history[10]` 为 SX41→43、XG43→45，46卸载。规则 `trace[96,104,105,112,120]` 保存 donor SX41、donor XB43、loaded SX43、loaded XG45、loaded 卸载48。

{bag_table(A)}

完整成本 **14.8→15.8**：`tray_wait 13→12`（round2:need 早装2 tick，但 round2:loaded 晚装1 tick），`tardiness 0→2`，`empty_distance 18→18`，终端两项均0。因此 **ΔJ=−1+2=+1**，任务 `round2:loaded` 由截止46恰好完成变48，准时数少1。更早卸载的那袋本身改善，并不阻止其可用空盘触发慢层预约后损害另一个任务。

## B：另一 seed 的回退——托盘所在位置改变，接续队列缺盘且 delegate 改选较慢支路

**SHARED-31-D29，L4_D3_slack0 / stress_3**。{episode_links(B)}。本例两次覆盖在规则 `history[2]`、`history[6]`，不是对单个动作的隔离实验。

首次覆盖在 t=11，`need:0`/donor 到 C；两版同一状态和 K4 池。原评分 `[0, -1.416463, -1.372232, -0.659709]` 选 index1 离开 C；规则零边卸载12完成，原版绕 C→S→B→C 后20完成。这个提前释放使 `slow_history[7]` t14 选 **donor** 去 B（CS20→21、SX21→25、XB25→26）；原版 donor 还载袋，直到 `slow_history[9]` t18 选 **loaded** 从 G 去 B（GC18→20、CS20→21、SX21→25、XB25→26）。实际 stress tape 没有 round1:need，但14时已经发布过这项预测，两版都按可见预测运行，没有使用该袋实际不会到达这一未来真值。

由此 t32 后两盘位置互换：原版 donor 完成 round1:loaded 在G，loaded 空盘在B；规则 loaded 完成 round1:loaded 在G，donor 空盘在B。t42 服务 round2:loaded 时，两版反应式均派 donor 返回S；原版从G出发，规则从B出发（原 `trace[90,91,94,100,103]`；规则 `[84,85,88,92,96]`），均45装载。但规则把B唯一盘带走了：t44 round2:need 到B时，原版直接用原地loaded盘装载；规则需要让loaded从G经C、S、X返回B（`trace[91,93,100,102,104,106,112,115]`），52才装载，**多等8 tick**。

另一个分歧可直接核验，不能误称为物理上只有慢路可走：t45 两版的正常 K4 候选见证相同，但可见状态与 MLP 评分不同。原版 `history[7]` 的分数 `[0, 0.790186, 3.231925, -2.476360]` 选 index3，实际安全前缀 SX45→49、XG49→51，随后到G再决定卸载52；规则 `history[4]` 的分数 `[0, -2.483425, 2.129369, -1.812885]` 选 index1，实际 SY45→49、YG49→54，卸载55。**规则版同池仍有 SX45→49、XG49→51 的合法候选**，因此这3 tick 完成回退是变化后的 delegate 评分选择，不能写成“拥堵强迫走SY”。规则的第二次零边覆盖 t54 使 round2:need 于55完成，反而早于原版59；但这没有消除先前8 tick 的缺盘等待。

{bag_table(B)}

成本 **18.6→31.2**：等待 **8→17**（round1:loaded +1、round2:need +8），迟到 **8→11**（round2:loaded +3），空行驶 **26→32**（加权+0.6），终端均0。故 **ΔJ=9+3+0.6=12.6**。准时数不变：round2:loaded 在两版都已迟到，仅迟到程度扩大。这条轨迹同时展示了空盘分配变化与后续模型选择变化，不能把全部代价归于首次卸载的局部耗时。

## C：明确正例——打断到站后继续带袋绕行，释放有限盘完成后续任务

**R0-23-D43，L4_D1_slack3 / nominal**。{episode_links(C)}。这是本次保存结果中成本改善最大的单对，特意作为事后机制例，不能作为平均效应或新确认。

首次覆盖 `history[2]`，t8 need:0 到C；原版继续CS8→9并再选S→G→C，之后多次经过C都离开，horizon72仍载有need:0。规则零边卸载t9（`trace[28]`），接着慢层 `slow_history[7]` t14 将同盘送B，26装载round1:need（`trace[63]`），t28第二次零边覆盖，29完成（`trace[73]`）；34时再预调同盘，46装载round2:need（`trace[113]`），t48第三次覆盖，49完成（`trace[123]`）。原版 need:0 一直占 donor，后续 B 队列不能获得这份真实盘供给。另一盘原版带round1:loaded也持续绕行；规则的变化后正常delegate选择经Y到G，并完成后续S任务。没有增加盘或删除积压。

{bag_table(C)}

成本 **301.9→10.4**，完成 **1→6**，准时 **1→4**。分项为等待 **107→6**、迟到 **142→2**、空行驶 **9→24**、末端未完成 **5→0**、末端在途 **1→0**：`ΔJ=−101−140+1.5−50−2=−291.5`。空行驶反而增多，因为释放出的盘确实承担了后续供给；收益来自解除占盘和积压，并非只减少行驶距离。

## D：同一 seed 的较大成本回退，准时个数却没有进一步下降

**SHARED-31-D17，L2_D3_slack0 / stress_6**。{episode_links(D)}。规则覆盖索引2/5/8分别在t8/28/46的C目的地，将need:0、round1:need、round2:need完成时刻15→9、35→29、53→47。第一次释放后，t14慢层改由donor承担B供给，而原版当时用loaded从G去B；t34规则又提交donor的CS40→41、SX41→43、XB43→44空盘调拨。两个S任务因供盘/共享边时序变化，装载各晚3、完成各晚4（24→28、44→48）。对应规则正常决策为 `history[3]` SX23→25和 `history[6]` SX43→45；原版为 `history[5]` SX19→21和 `history[10]` SX39→41。详见证据 JSON 的全部 indexed trace 与 per_bag。

本例 `wait 2→8`、`tardiness 5→13`、`empty_distance 18→18`，因此 **J8.8→22.8，ΔJ=14**。两个S任务原本已迟到，故迟到总 tick 增加8但准时个数不变。这与例A“刚好跨越截止导致准时数下降”是不同机制口径。

## 规则下仍未完成的 11 个任务

{chr(10).join(unfinished)}

这11个实例全部来自 R0-23 paired_direct，seed17/29/43分别5/3/3个。对**这些袋本身**，真实 selector 从未在其实际 destination 调用（0次），所以没有合法零边卸载机会、也没有覆盖。这不是规则绕过了一个已存在的卸载候选。保存的实际节点序列反复经过非目标C/S/G或C/S/B；最终仍由真实盘携带并在途中。这里描述的是horizon72内的未完成，不能证明无限期饥饿。压力tape会改变实际OD，表中的C→B/S→G采用实际bag身份，不能凭任务名字把need一律当B→C。详细时刻、最终盘及来源SHA见 {link(ROOT/'remaining_tasks_diagnostic.json','remaining_tasks_diagnostic.json')}。

## 可以得出的机制结论与边界

1. 合法到站卸载能避免某些带袋离站循环，并把有限盘归还后续调度；在较弱23维模型上这是主要改善来源。
2. 它**不是当前闭环代价下的无条件支配动作**。卸载改变真实空盘何时/何地可用，慢层可据此作新的不可撤预约，正常路由也会在变化后的可见状态选择不同动作。例A给出只有一次覆盖的实际资源冲突链；例B同时保留空盘分配和MLP改选的证据。
3. 当前规则仅覆盖“已经到实际终点且正常池内有合法完整零边卸载”的边界。非目的地循环、无候选、到不了目标等问题仍由原控制器处理；11个未完成实例界定了这个覆盖范围。
4. 全部36 tapes复用既有开发条件，模型/规则有相关性，1872次运行不是1872个独立样本；没有从这些事后例子推断统计显著性、现场表现或新工况泛化。不同seed不筛选。原版936次完整物理复现是这些条件下的兼容证据，不是全局cache无影响定理。
5. 本分析没有重新演算“只改一次然后强迫后续不变”的反事实，也没有用结果修改规则。候选后缀是可行见证，实际next-edge执行以事件trace为准。后续若设计新规则/约束，应单独预声明并保留本次反例，不能将经验直觉写成强制卸载定理。
"""
    (ROOT / "DIAGNOSTICS.md").write_text(report, encoding="utf-8")
    assert all(sha(ROOT / rel) == value for rel, value in READ_HASHES.items()), "saved input changed during analysis"
    print(json.dumps({"cases": len(cases), "tables": "26 nominal + 26 stress", "unfinished": 11,
                      "saved_inputs_unchanged": len(READ_HASHES), "outputs": ["decision_mechanism_evidence.json", "DIAGNOSTICS.md"]}))


if __name__ == "__main__":
    main()
