"""Post-hoc saved-file inspection. No experiment imports, fitting or simulation."""
from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
from statistics import mean

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
SOURCE = ROOT / "phase4_w3_horizon_repaired_20261009"
MECHANISMS = ROOT / "phase4_w3_horizon_mechanisms_20261009" / "mechanisms.json"
WEIGHTS = {"tray_wait": 1, "nonprotected_tardiness": 1, "empty_distance": .1,
           "terminal_backlog": 10, "terminal_inflight": 2}
INPUT_HASHES = {}
GZIP_CACHE = {}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    INPUT_HASHES[str(path.relative_to(ROOT))] = sha(path)
    return json.loads(path.read_text(encoding="utf-8"))


def physical(path, expected):
    if path not in GZIP_CACHE:
        assert sha(path) == expected
        INPUT_HASHES[str(path.relative_to(ROOT))] = expected
        GZIP_CACHE[path] = json.loads(gzip.decompress(path.read_bytes()))
    return GZIP_CACHE[path]


def link(path, title):
    return f"[{title}](<{path.as_posix()}>)"


def same(a, b):
    assert abs(a - b) < 1e-8, (a, b)


def extract(case_id, record, chosen_future):
    label_path = SOURCE / record["label"]
    labels = read(label_path)
    sample = read(label_path.parent / "sample.json")
    assert len(labels["raw_branches"]) == 128 and not labels["failures"]
    assert labels["groups"] == 4 and labels["futures_per_group"] == 8
    assert sample["state"]["trays"][sample["tray_id"]]["node"] == sample["state"]["bags"][sample["bag_id"]]["destination"]
    options = sample["proposals"]
    assert not options[0]["legs"] and not options[0]["prefix_only"]
    rows = {(x["group"], x["future_index"], x["candidate"]): x for x in labels["raw_branches"]}
    endpoints = {}
    for key, row in rows.items():
        assert not row["failed"] and not row["not_executed"] and row["twenty_matches_historical"]
        data = physical(label_path.parent / row["evidence"], row["evidence_sha256"])
        for h in ("20", "40", "80"):
            p, saved = data[h], row["endpoints"][h]
            assert p["final_snapshot"]["now"] == sample["time"] + int(h)
            same(p["total_cost"], saved["total_cost"])
            same(p["total_cost"], sum(p["cost_components"][k] * w for k, w in WEIGHTS.items()))
            assert p["completed"] == saved["completed"]
            assert p["uncompleted_bag_ids"] == saved["uncompleted"]
            for k in WEIGHTS:
                same(p["cost_components"][k], saved["cost_components"][k])
            if h == "80":
                assert not p["uncompleted_bag_ids"]
                assert not p["cost_components"]["terminal_backlog"] and not p["cost_components"]["terminal_inflight"]
        endpoints[key] = data
    summaries = {}
    for h in ("20", "40", "80"):
        candidate_means = []
        for c in range(4):
            branches = [endpoints[g, f, c][h] for g in range(4) for f in range(8)]
            value = {"total_cost": mean(b["total_cost"] for b in branches),
                     "raw_components": {k: mean(b["cost_components"][k] for b in branches) for k in WEIGHTS}}
            same(value["total_cost"], record["points"][h]["means"][c])
            for k in WEIGHTS:
                same(value["raw_components"][k], record["points"][h]["component_means"][c][k])
            candidate_means.append(value)
        summaries[h] = {
            "candidate_means": candidate_means,
            "c1_minus_c0": candidate_means[1]["total_cost"] - candidate_means[0]["total_cost"],
            "weighted_component_deltas": {k: WEIGHTS[k] * (candidate_means[1]["raw_components"][k] - candidate_means[0]["raw_components"][k]) for k in WEIGHTS},
        }
    paired = []
    for g in range(4):
        for f in range(8):
            assert rows[g, f, 0]["future_sha256"] == rows[g, f, 1]["future_sha256"]
            item = {"group": g, "future_index": f, "future_sha256": rows[g, f, 0]["future_sha256"],
                    "future_tape_offline_only": labels["future_groups_offline_only"][g]["tapes"][f], "points": {}}
            for h in ("20", "40", "80"):
                a, b = endpoints[g, f, 0][h], endpoints[g, f, 1][h]
                item["points"][h] = {"c0_cost": a["total_cost"], "c1_cost": b["total_cost"],
                                      "delta_cost": b["total_cost"] - a["total_cost"],
                                      "raw_component_deltas": {k: b["cost_components"][k] - a["cost_components"][k] for k in WEIGHTS}}
            paired.append(item)
    distribution = {}
    for h in ("20", "40", "80"):
        values = [p["points"][h]["delta_cost"] for p in paired]
        distribution[h] = {
            "negative": sum(v < -1e-8 for v in values), "zero": sum(abs(v) <= 1e-8 for v in values),
            "positive": sum(v > 1e-8 for v in values), "minimum": min(values), "maximum": max(values),
            "group_means": [mean(p["points"][h]["delta_cost"] for p in paired if p["group"] == g) for g in range(4)],
        }
    all_nonzero_costs_equal = all(
        endpoints[g, f, c][h]["cost_components"] == endpoints[g, f, 1][h]["cost_components"]
        for g in range(4) for f in range(8) for c in (2, 3) for h in ("20", "40", "80"))
    assert all_nonzero_costs_equal
    g, f = chosen_future
    trajectories = {}
    for c in (0, 1):
        row, result = rows[g, f, c], endpoints[g, f, c]["80"]
        state = result["final_snapshot"]
        per_bag = []
        for bag_id, bag in state["bags"].items():
            load, completed = state["load_times"][bag_id], result["completed"][bag_id]
            per_bag.append({"bag": bag, "load": load, "complete": completed,
                            "wait": load - bag["arrival"], "tardy": max(0, completed - bag["deadline"]) if not bag["protected"] else 0})
        same(sum(x["wait"] for x in per_bag), result["cost_components"]["tray_wait"])
        same(sum(x["tardy"] for x in per_bag), result["cost_components"]["nonprotected_tardiness"])
        trajectories[str(c)] = {
            "gzip": str((label_path.parent / row["evidence"]).relative_to(ROOT)),
            "gzip_sha256": row["evidence_sha256"], "result_endpoint": "80", "absolute_time": state["now"],
            "components": result["cost_components"], "total_cost": result["total_cost"], "per_bag": per_bag,
            "trace_from_decision": [{"trace_index": i, **x} for i, x in enumerate(result["trace"])
                                    if x["time"] >= sample["time"] and x["event"] != "tick"],
            "final_trays": result["final_trays"],
        }
    counts = Counter("better" if p["points"]["80"]["delta_cost"] < -1e-8 else "worse" if p["points"]["80"]["delta_cost"] > 1e-8 else "equal" for p in paired)
    return {"case_id": case_id, "identity": record["identity"], "owner": record["owner"], "stream": record["stream"],
            "label_path": str(label_path.relative_to(ROOT)), "sample_path": str((label_path.parent / "sample.json").relative_to(ROOT)),
            "sample_time": sample["time"], "state_sha256": sample["state_sha256"],
            "state": sample["state"], "cursor": sample["cursor"], "next_slow_trigger_at": sample["next_slow_trigger_at"],
            "continuation_contract": sample["continuation_contract"], "candidates": options,
            "summaries": summaries, "paired_32": paired, "candidate1_outcomes80": dict(counts),
            "distribution_by_horizon": distribution,
            "all_nonzero_candidate_components_equal_per_future": all_nonzero_costs_equal,
            "future_tape_multiplicity": dict(Counter(p["future_sha256"] for p in paired)),
            "unique_future_tapes_of32": len({p["future_sha256"] for p in paired}),
            "selected_physical_future": {"group": g, "future_index": f,
                                          "tape": labels["future_groups_offline_only"][g]["tapes"][f], "trajectories": trajectories}}


def endpoints_table(case):
    lines = ["| 相对窗口 | 立即卸载均值 | 离站均值 | ΔJ | 等待Δ | 迟到Δ | 0.1×空驶Δ | 10×积压Δ | 2×在途Δ |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for h, v in case["summaries"].items():
        d = v["weighted_component_deltas"]
        lines.append(f"| {h} | {v['candidate_means'][0]['total_cost']:.6f} | {v['candidate_means'][1]['total_cost']:.6f} | {v['c1_minus_c0']:+.6f} | " + " | ".join(f"{d[k]:+.6f}" for k in WEIGHTS) + " |")
    return "\n".join(lines)


def future_table(case):
    lines = ["| group / future | ΔJ20 | ΔJ40 | ΔJ80 | waitΔ80 | tardyΔ80 | raw emptyΔ80 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for row in case["paired_32"]:
        p = row["points"]
        d = p["80"]["raw_component_deltas"]
        lines.append(f"| {row['group']} / {row['future_index']} | {p['20']['delta_cost']:+.3f} | {p['40']['delta_cost']:+.3f} | {p['80']['delta_cost']:+.3f} | {d['tray_wait']:+.0f} | {d['nonprotected_tardiness']:+.0f} | {d['empty_distance']:+.0f} |")
    return "\n".join(lines)


def distribution_table(case):
    lines = ["| 窗口 | Δ负/零/正 | 最小Δ | 最大Δ | group0均值 | group1均值 | group2均值 | group3均值 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for h, d in case["distribution_by_horizon"].items():
        lines.append(f"| {h} | {d['negative']}/{d['zero']}/{d['positive']} | {d['minimum']:+.5f} | {d['maximum']:+.5f} | " + " | ".join(f"{v:+.5f}" for v in d["group_means"]) + " |")
    return "\n".join(lines)


def bag_table(case):
    rows = case["selected_physical_future"]["trajectories"]
    a = {x["bag"]["bag_id"]: x for x in rows["0"]["per_bag"]}
    b = {x["bag"]["bag_id"]: x for x in rows["1"]["per_bag"]}
    lines = ["| 任务 / 真实OD | 到达/截止 | 装载：卸载→离站 | 完成：卸载→离站 | waitΔ | tardyΔ |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, x in a.items():
        y, bag = b[name], x["bag"]
        lines.append(f"| {name} / {bag['origin']}→{bag['destination']} | {bag['arrival']}/{bag['deadline']} | {x['load']}→{y['load']} | {x['complete']}→{y['complete']} | {y['wait']-x['wait']:+} | {y['tardy']-x['tardy']:+} |")
    return "\n".join(lines)


def sources(case):
    return (f"身份：`{case['identity']}`。\n\n" + link(ROOT/case["label_path"], "全部128请求标签") + "；" +
            link(ROOT/case["sample_path"], "真实checkpoint样本") + "；" + "；".join(
                link(ROOT / row["gzip"], f"候选{c}完整gzip") for c, row in case["selected_physical_future"]["trajectories"].items()))


def main():
    mechanisms = read(MECHANISMS)
    protocol = read(SOURCE / "protocol.json")
    assert protocol["continuation"] == "fixed timed" and protocol["controller_planning_horizon"] == 20
    cases = []
    for name, key, future in (
        ("old_advantage_disappears", "old_detour_reverses_at80", (0, 5)),
        ("old_advantage_remains", "old_detour_state_still_has_detour_at80", (0, 1)),
        ("new_advantage", "new_detour_at80", (0, 0))):
        cases.append(extract(name, mechanisms["illustrations_posthoc_not_training_selection"][key][0], future))
    historical = next(x for x in mechanisms["records"] if ":t28:" in x["identity"] and abs(x["old_choice_advantage_over_unload"]["20"]["terminal"] - 4.25) < 1e-8)
    cases.append(extract("previous_t28_terminal_minus4_25", historical, (0, 0)))
    a, b, c, d = cases
    common_fields = ("now", "network", "trays", "bags", "completed", "load_times", "old_in_transit", "module", "empty_targets")
    A = {r["future_sha256"]: r for r in a["paired_32"]}
    D = {r["future_sha256"]: r for r in d["paired_32"]}
    intersection = sorted(A.keys() & D.keys())
    t28_comparison = {
        "full_states_equal": a["state"] == d["state"],
        "same_current_physical_fields": {k: a["state"][k] == d["state"][k] for k in common_fields},
        "same_plans": a["state"]["plans"] == d["state"]["plans"],
        "same_reservations": a["state"]["reservations"] == d["state"]["reservations"],
        "same_conditional_forecasts": a["state"]["conditional_forecasts"] == d["state"]["conditional_forecasts"],
        "a_loaded_plan": a["state"]["plans"]["loaded"], "d_loaded_plan": d["state"]["plans"]["loaded"],
        "unique_tapes_A_D": [len(A), len(D)], "common_tape_count": len(intersection),
        "common_tape_sha256": intersection,
        "common_saved_c0_c1_costs_and_components_equal_all_endpoints": all(A[k]["points"] == D[k]["points"] for k in intersection),
        "different_multiplicities": [{"sha256": k, "A_count": a["future_tape_multiplicity"].get(k, 0),
                                      "D_count": d["future_tape_multiplicity"].get(k, 0)} for k in sorted(A.keys() | D.keys())],
        "interpretation": "Current entity fields equal, but commitment/forecast state differs. Common saved tapes have equal paired metrics; full means use different future mixtures. No cross-state new simulation or independent scene inference.",
    }
    assert not t28_comparison["full_states_equal"]
    assert all(t28_comparison["same_current_physical_fields"].values())
    assert t28_comparison["common_saved_c0_c1_costs_and_components_equal_all_endpoints"]
    data = {"post_hoc_saved_physics_only": True, "new_simulations": 0, "new_fits": 0,
            "selection_rule": "First saved illustration from each of three categories; plus exact prior t28 terminal -4.25 identity. Representative futures are post-hoc explanatory choices; all32 are retained.",
            "inspected_states": 4, "inspected_requested_branches": 512, "inspected_requested_endpoint_reads": 1536,
            "unique_gzip_read": len(GZIP_CACHE), "horizon_interpretation": "relative to decision time; cumulative past cost retained equally in all candidates",
            "cases": cases, "t28_cross_owner_comparison": t28_comparison, "label_protocol": protocol,
            "input_hashes": INPUT_HASHES}
    (OUT / "physical_mechanisms.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = f"""# 80 tick 终点罚消失后，绕行优势从何而来

本说明是**事后只读物理机制分析**：从既有 `mechanisms.json` 的三类示例各取第一份，另精确定位上一轮 t28 / 终端贡献−4.25 的代表状态。未新增仿真、拟合、候选或规则。代表性未来在看到结果后选择，仅用于解释；四状态各4候选×32未来全数复核并保留，不能把例子视为独立验证或挑选下一策略的证据。

分析脚本 {link(OUT/'read_physical_mechanisms.py','read_physical_mechanisms.py')}；机器可读证据 {link(OUT/'physical_mechanisms.json','physical_mechanisms.json')} 保存4状态、全部128组配对未来的成本分项、8份代表性完整gzip的路径/SHA、逐袋账及带原数组索引的事件。共读取并核验 **512候选请求×3窗口=1536个端点**，其中gzip去重后 **{len(GZIP_CACHE)}** 个；不是新增物理调用。每个端点由完整gzip重算与labels/根机制均值相符；四状态全部80窗口已完成、末端积压和在途均0。

## 先统一口径

80是**相对当前决策的80 tick**，例如t28状态观察到绝对t108，不是全episode截在t80。分支保留共同过去的累计成本，比较时过去相消。继续控制器统一timed；collector名称只是产生checkpoint的历史模型，分支后不继续使用它。每个候选仅干预合法下一安全前缀，其完整路线为可行见证；后续实际走法取自trace。

本文固定 `Δ=离站候选1−立即卸载候选0`，负数表示离站较低。候选0已核验真实loaded盘在其最终destination、`legs=[]`、`prefix_only=false`。四例的候选1先走CS；其他两个离站见证虽后缀不同，各自32未来成本与候选1一致，但仍保留为正常K4请求，没有减少分母。固定成本 `wait+tardy+0.1×empty+10×backlog+2×inflight`：wait只计到达后未装载；已装载后多走路不直接计wait，未超deadline也不增加tardy，带载行程不算empty。**这解释了某些带袋绕行没有直接行驶罚，但不证明其全局有利。**

全量结论来自根分析：208个owner相关状态，20窗口40个离站均值较低；80窗口50个，其中旧39保留、1消失、11新出现。26,624个请求的80端点152,880个已观察袋实例均已完成、终端罚0；这些是请求加权重复实例，含同tape缓存复用，不是独立任务日。以下只详解四份实物，不把它们外推成50份同一原因。

## A：旧优势消失——小幅终点差掩盖了更高的最终空驶与逆向需求代价

{sources(a)}。

{endpoints_table(a)}

20窗口离站的−0.34375由终端−0.5抵消非终端 **+0.15625** 而来；80窗口终端0后，wait+0.0625、tardy−0.09375、空驶加权+0.209375，合计 **+0.178125**，立即卸载略优。这是唯一旧优势消失状态，不意味着其32未来全都偏好卸载：完整未来表显示仍有多数低成本离站结果，少数损失较大。

选取group0/future5的**逆向实际任务 G→S，42到达/52截止**看损失链。候选0在t29完成当前round1:need，把donor留在C；t34慢层用donor去B（trace[85]；CS40、SX41、XB45），而loaded留在G，真实G任务42到达即装载（trace[97]），46完成（[110]）。

候选1在t28离站，CS28→29、SX29→33、XB33→34、BC34→36，当前袋37才卸完（trace[71,75,85,90,95]）。因此t34慢层改选G的loaded去B（trace[89]，GC38、CS40、SX41、XB45）。真实G任务42到达时G无盘：donor需从C经S/Y返回G（trace[106,107,111,122]），50装载、54完成（[130,141]）。这一路不是预测器看到了真实逆向需求：既有公布预测仍按S→G，实际G→S仅42注入后才反应。

{bag_table(a)}

该未来成本 **6.1→17.1，Δ=+11**，来自wait+8、tardy+2、empty原量+10（加权+1）。两条分支在80均全完成。这份不利未来与同32集合中多份S→G受益未来共同决定小幅正均值；不能用一条轨迹替代总体分布。

## B：旧优势保留——迟些释放改变供盘分配，后续真实队列少等，终点项不是必要条件

{sources(b)}。

{endpoints_table(b)}

80均值仍为 **−3.75625**：wait−2.84375、tardy−0.78125、空驶加权−0.13125，终端0。代表group0/future1的首S任务18到达，round1:need的真实OD改为C→B；这里只在到达事件后使用实际信息。

立即卸载时 need:0 于9完成，慢层t14把donor从C派往B（trace[35]；CS20、SX21、XB25）；另盘loaded由G反应式回S，却被CS20→21预约推迟，22才装载首S任务，走SY/YG到30完成（trace[41,45,49,50,53,55,61,71]）。离站则need:0在17完成，t14慢层改派loaded从G去B（trace[39]），donor18从C回S、19装载、27完成（[50,51,54,56,63,71]），首S任务由迟到2变准时。

两种做法随后都在C于30装载逆向round1:need并37在B完成，但**盘身份与所在位置不同**：立即卸载分支此袋使用donor，另一loaded在G；离站分支此袋用loaded，另一donor在G。t42共同反应式调度均选donor服务S：前者从B抽走唯一B盘，后者从G返回、B的loaded仍在。于是44到B的round2:need，前者等loaded从G→C→S→X→B至54才装载（trace[104..133]），后者44直接装载（[109]）。其余实际事件及身份在JSON中保留，并非凭总成本倒推。

{bag_table(b)}

这个未来成本 **23.8→8.0，Δ=−15.8**：wait−13（首S −3、后B −10）、tardy−2、empty原量−8（加权−0.8），末端0。当前被干预袋晚卸8 tick仍在其deadline前；在本目标里带载这段绕行没有直接“载盘里程”罚。它通过后续分配产生真实收益，但32未来中也有反例，不能推断全局支配。

## C：新优势出现——20窗口尚未计完迟到与后续队列影响

{sources(c)}。

{endpoints_table(c)}

20窗口离站 **+0.70625**，80变 **−1.53125**：wait−0.8125、tardy−0.65625、空驶加权−0.0625，终端0。这里并非只把20的同一终端罚删去：继续物理运行产生了新的等待/迟到/空驶，80的非终端差也不同。

代表group0/future0中，卸载让donor12空出，t14接受去B的慢调拨（trace[36]），CS20→21、SX21→25。18到达的S任务使用loaded从G回S，在CS后等至22装载，走SY22→26、YG26→31、32卸完（[43,46,50,51,54,56,62,78]）。离站的donor当前袋20才卸完，t14没有这份出口；loaded回S可在20走CS，21装载，然后SX21→25/XG25→27，28卸完（[47,51,55,58,60,68,74]）。稍后donor22才预调去B，SX须等至25，B任务装载28→30、完成31→33（[62,63,69,78,81,88]）。两种分支后续第二轮时刻一致。

{bag_table(c)}

该未来 J **22.4→19.4，Δ=−3**：S任务少等1、B任务多等2，wait净+1；首S任务完成32→28使迟到7→3，tardy−4；empty不变。20窗口绝对t31尚未覆盖全部这些完成结果，保存的该future ΔJ20=0、ΔJ80=−3。32未来总体的排名反转不是对这一个未来的重新挑选；全部都在附表中。

## D：精确回查上一轮 t28 / terminal−4.25 代表例

{sources(d)}。

这是上一轮 {link(ROOT/'phase4_w3_shared_recovery_20261009/destination_action_review.md','destination_action_review.md')} 表中“L4_D1、t28、collector L2_D1 direct17”同一身份。不要与A的collector L4_D3 direct17混为同状态。

{endpoints_table(d)}

20的 **−4.825** 完整分解仍为wait−0.75、tardy0、空驶加权+0.175、积压−3.4375、在途−0.8125，terminal合计−4.25；历史数值精确复现。40及80均为 **−1.2 = wait−0.59375 + tardy−0.78125 + empty加权0.175**，终端两项0。旧优势被削弱，但**并未消失**，因此“这个代表例主要由终端项贡献”仍是对20窗口的准确描述，不能续写成“延长至全完成后必消失”。

代表group0/future0中真实S任务38到达/48截止，后B任务48到达。立即卸载于29释放donor，t34慢层把donor从C派B（trace[83]）；loaded留G，38反应式回S，却与donor的CS40→41和SX41→45调拨发生竞争：42才装载、选SY42→46/YG46→49、50完成（[89,90,93,97,98,101,103,109,120]）。

离站当前袋37才卸完，t34慢层改派G的loaded去B（trace[87]；GC38、CS40、SX41、XB45）。donor在C37已空出，38只走CS即可39到S装载，走SY39→43/YG43→46，47完成（[93,98,99,102,104,111,119]）。两版B任务均48装载、51完成；不同的是哪只盘留给近处的真实S队列。

{bag_table(d)}

单future成本 **12.4→7.4，Δ=−5**：wait−3、tardy−2，empty相同。32未来并不逐一支配：有G逆向需求的显著损失，也有空驶小损失，完整配对结果和收益/损失数量如下。

### 两个t28 owner是否同一个物理场景

A与D的当前now、拓扑、trays、bags、已完成账、load_times、old flight、固定module、empty_targets逐字段完全相同；仅凭collector名字不能称为新的独立物理场景。但**完整Snapshot并不相同**：A的另一盘loaded只承诺到G的prefix（t30到达，尚需决定卸载），D已有t31完成的完整卸载承诺，并多出`reception:G[30,31)`预约；版本、conditional witness和历史也不同。A的loaded条件usable_at40只是未承诺见证，不能当firm释放；实际共同timed继续在30再卸载，31可用。报告不会把这些字段差异删掉后声称exact checkpoint相同。

两份32请求分别含 **22/19个不同future SHA，共13个相同tape**。这13个共同tape，保存的候选0/1在20/40/80的总成本及全部分项完全相等；但tape出现次数和其余tape不同。因此至少在共有tape上，owner名称和上述承诺记录差异没有形成这些配对成本差；总体均值符号不能脱离future mix解释。不能据本次只读数据证明所有未共有future也会相等，亦未作跨状态新回放。各SHA的出现次数与共有集合在JSON的`t28_cross_owner_comparison`保留。

## 每状态全部32共同未来（索引0-based，不删除重复或不利未来）

raw empty列未乘0.1；上述均值分解表已加权。每条均由原gzip成本核验，不只使用summary数值。各group恰8项，每请求权重1/32；重复tape按原出现次数计权，缓存复用不改变统计权重。4组均值只描述冻结组间差异，不作独立重复或置信区间。
"""
    for case in cases:
        counts = case["candidate1_outcomes80"]
        report += f"\n### {case['case_id']}\n\n80窗口离站更低/相同/更高：{counts.get('better',0)}/{counts.get('equal',0)}/{counts.get('worse',0)}；32请求中不同future SHA为{case['unique_future_tapes_of32']}。\n\n{distribution_table(case)}\n\n{future_table(case)}\n"
    report += """
## 结论边界

这批80窗口已观察袋全完成，绕行优势仍可由实际等待、迟到和空盘重定位差异保留；终端罚不是其必要条件。本地先卸载没有直接保证更好的全局空盘分配，固定慢层和共同timed继续策略也不等于全局最优。反过来，A与每状态的负未来表明延迟卸载同样可能有害。

这不是无限时域定理：所有窗口内只有冻结的有限未来tape，后来没有继续注入新的长期需求；全部完成不代表无限持续运行的稳态。208状态有owner重复，32未来有相关和精确重复，上表是冻结样本均值及轨迹证据，没有声称统计显著性或新来源泛化。

当前目标不直接惩罚载盘距离，未迟到前的载盘绕行可“免费”改变释放时序，但这只是目标定义与实际控制耦合的解释，不授权修改成本或硬约束。本分析不建议把绕行变为强制规则，也不根据这些事后例子选模型/种子。候选1首前缀后统一timed继续，与部署中反复learned选择不同；不能把这里的4候选标签当learned全episode保证。
"""
    (OUT / "PHYSICAL_MECHANISMS.md").write_text(report, encoding="utf-8")
    assert all(sha(ROOT / path) == expected for path, expected in INPUT_HASHES.items())
    manifest = {"input_hashes": INPUT_HASHES, "inputs_unchanged": True,
                "new_simulations": 0, "new_fits": 0,
                "files_sha256": {name: sha(OUT/name) for name in ("read_physical_mechanisms.py", "physical_mechanisms.json", "PHYSICAL_MECHANISMS.md")}}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"states": 4, "requests_checked": 512, "endpoints_checked": 1536,
                      "unique_gzip_read": len(GZIP_CACHE), "saved_inputs_unchanged": len(INPUT_HASHES),
                      "case_outcomes80": {x['case_id']: x['candidate1_outcomes80'] for x in cases}}))


if __name__ == "__main__":
    main()
