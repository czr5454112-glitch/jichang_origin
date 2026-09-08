"""Render the completed two-instance diagnostic without invoking simulations."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'outputs/evidence/hca_time_label_repair_v2_20260906'
COMPARISON = EVIDENCE / 'comparison/comparison.json'
REPORT = ROOT / 'outputs/reports/hca_time_label_repair_v2_two_cell_20260906.md'


def link(label, path):
    return f'[{label}]({(ROOT / path).as_posix()})'


def main():
    data = json.loads(COMPARISON.read_text(encoding='utf-8'))
    assert data['status'] == 'TWO_CELL_DIAGNOSTIC_COMPLETE'
    rows = {(r['map'], r['clock'], r['statistic']): r for r in data['rows']}
    route = json.loads((EVIDENCE / 'comparison/route_time_audit.json').read_text(encoding='utf-8'))
    assert route['status'] == 'PASS_NO_TOTAL_ROUTE_TIME_MISMATCH_DETECTED'
    maps = [('map2', 'map2'), ('nanning', '南宁')]
    text = [
        '# HCA 时间标签修复：map2 与南宁各一次 1× 对照（2026-09-06）', '',
        '已在独立副本修复并完成指定的两次实验。按共同计划释放时刻 D 计算，G31 的平均 THT 优势略有缩小，修复后仍分别领先 **27.16%（map2）和 87.59%（南宁）**。按各系统原生起点计算，G31 的平均 THT 分别比修复后 HCA 高 **0.38% 和 74.72%**，这个口径下其劣势扩大。两套起点语义必须分别说明，不能概括为 G31 全面优于 HCA。', '',
        '修复只涉及复制源码中 A* 改进已有开放节点路径时补上 `n.t1=t1; n.t2=t2;`。原始材料项目、只读镜像、旧 HCA 包装器和运行器、旧结果未修改。新方法独立标识为 `HCA_TIME_LABEL_REPAIR_V2`。', '',
        '## 实验范围与完成情况', '',
        '- 仅 map2 1×、南宁 1× 各执行一次完整仿真；均为既有 seed 104729，与旧 HCA/G31 的同一输入配对。没有运行其他负载、种子或算法。',
        '- 每图 28,506 件原始行李、43,602 个规范段，三种结果均全部完成，TH 均为 **28,506 件，持平**。',
        '- 速度 2.5 m/s，无故障，起始 epoch 8260，运行 90,000 个 epoch，末时刻 98259。原输入、地图、EBS 阈值和执行段 ID 规则保持原合同。',
        '- G31 和修复前 HCA 使用冻结结果；仅修复后 HCA 是本次新执行。微测试为短 Java 断言，不是额外完整仿真。',
        '- 本报告中 THT 越小越好，TH 越大越好。以下时间单位均为秒；百分比基于未四舍五入的值计算。', '',
        '## 共同 D 口径：平均优势缩小，但仍领先', '',
        '每件行李按其全部规范段累计 `Σ(E − canonical D)`，包含成功规划/原生接纳前的时间差。', '',
        '| 地图 | 旧 HCA 平均 | 修复 HCA 平均 | G31 平均 | G31 原优势 | G31 新优势 | 变化（百分点） |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for m, label in maps:
        r = rows[m, 'COMMON_CANONICAL_D', 'mean']
        text.append(f"| {label} | {r['old_hca']:.2f} | {r['repaired_hca']:.2f} | {r['g31_fixed']:.2f} | {r['g31_relative_advantage_vs_old_hca_percent']:.2f}% | {r['g31_relative_advantage_vs_repaired_hca_percent']:.2f}% | {r['g31_advantage_change_percentage_points']:+.2f} |")
    text += ['', 'G31 相对降低比例为 `(HCA − G31) / HCA × 100%`。修复使 HCA 的共同 D 平均 THT 在 map2 降低 1.68%、南宁降低 1.59%；G31 的平均绝对优势分别从 97.43 缩至 91.67 秒、从 4489.00 缩至 4407.55 秒。', '',
             '| 地图 | 方法 | TH（件） | 最小 THT | 平均 THT | 最大 THT |', '|---|---|---:|---:|---:|---:|']
    for m, label in maps:
        for field, method in [('old_hca', '旧 HCA V1（有时间标签缺陷）'), ('repaired_hca', 'HCA V2（本次修复）'), ('g31_fixed', 'G31（冻结对照）')]:
            vals = [rows[m, 'COMMON_CANONICAL_D', s][field] for s in ('min', 'mean', 'max')]
            th = rows[m, 'FIXED_HORIZON', 'TH'][field]
            text.append(f'| {label} | {method} | {th:,} | ' + ' | '.join(f'{v:.3f}' for v in vals) + ' |')
    text += ['', '最大值的变化并不与均值完全一致：map2 的 HCA 最大 THT 从 1644.900 增至 1648.978 秒（增加 0.25%），南宁从 58923.529 降至 58847.620 秒（降低 0.13%）。共同 D 下 G31 在这两格的平均和最大值仍低于修复 HCA，但最小值并未领先。', '',
        '## 原生起点口径：G31 平均时间更长，差距扩大', '',
        'HCA 累计 `Σ(E − successful planning)`；G31 累计 `Σ(E − native admission)`。这些是既有原生事件口径，尚不能认定两个事件是完全相同的物理入网起点，也不能省略此差异后直接宣称已严格对应冯论文的 D。', '',
        '| 地图 | 方法 | 最小 THT | 平均 THT | 最大 THT |', '|---|---|---:|---:|---:|']
    for m, label in maps:
        for field, method in [('old_hca', '旧 HCA V1'), ('repaired_hca', 'HCA V2'), ('g31_fixed', 'G31')]:
            vals = [rows[m, 'NATIVE_START', s][field] for s in ('min', 'mean', 'max')]
            text.append(f'| {label} | {method} | ' + ' | '.join(f'{v:.3f}' for v in vals) + ' |')
    text += ['', '以对应 HCA 为分母，G31 平均时间的相对增加：map2 从 **0.046% 增至 0.377%**，南宁从 **67.435% 增至 74.722%**。原生口径下 HCA 修复后的均值分别降低 0.33%、4.17%，南宁最大值从 1098 降至 986 秒。', '',
        '## 两套口径为什么差异很大', '',
        '按已记录事件，`共同 D THT = 原生 THT + Σ(原生起点 − D)`。HCA 的成功规划前时间差没有包含在原生 THT 中；共同 D 把它计入。下表是每件行李的平均分段累计起点差，由两套已复算均值直接相减：', '',
        '| 地图 | 旧 HCA：planning − D | 修复 HCA：planning − D | G31：admission − D |', '|---|---:|---:|---:|']
    for m, label in maps:
        values = [rows[m, 'COMMON_CANONICAL_D', 'mean'][field] - rows[m, 'NATIVE_START', 'mean'][field]
                  for field in ('old_hca', 'repaired_hca', 'g31_fixed')]
        text.append(f'| {label} | ' + ' | '.join(f'{v:.3f}' for v in values) + ' |')
    text += ['', '因此，修复时间标签后，HCA 的成功规划前等待仍然明显，南宁尤其如此。这个分解解释了报告中两个起点口径得出不同相对表现；它本身不把该时间差全部认定为同一种物理队列，也不证明剩余差距的唯一原因。', '',
        '## 修复与证据检查', '',
        '- 小图旧缺陷稳定复现：旧路径 0→2→3→4 的末时刻为 12 秒，修复后为 4 秒，逐节点递推正确。',
        '- 真实南宁 OD 对照、map2 正常 OD 对照通过；调用原生 `update_constrain` 验证修复后的预约窗口确实阻止冲突请求。共 14 条 Java 断言，另有跨版本不变对照。',
        '- 生产编译使用独立副本的 11 份源（9 App、1 GUI、1 wrapper）；生产核心 class 与通过微测试的核心 class 一致。wrapper 仅修改 METHOD 字符串。',
        '- 64 份受保护文件和 103 份冻结文件在运行后全部通过 SHA256 检查，原件及旧实现保持不变。',
        '- 每个规范段的执行 ID、规划、完成、终态与原始行李归属通过全量核对，终态计数残差为 0。独立脚本再从原生日志按执行 ID 重算两套 THT 的最小、平均、最大值，与归一化输出一致。', '',
        '| 地图 | 旧 HCA 路线总时长异常 | 修复 HCA 路线总时长异常 |', '|---|---:|---:|']
    for m, label in maps:
        old = next(r for r in route['old_cells'] if f'/{m}_1p00x/' in r['cell'])
        new = next(r for r in route['new_cells'] if f'/{m}_1p00x/' in r['cell'])
        text.append(f"| {label} | {old['route_formula_mismatch_count']:,} / {old['planned_route_count']:,} | {new['route_formula_mismatch_count']:,} / {new['planned_route_count']:,} |")
    text += ['', '正式路线校验使用返回的实际路径：`goal T2 − planning epoch = 全部路径节点通过时间（含起点和终点）+ 全部路径边长/速度`，容差 1e-7 秒。该全量检查验证路线总时长一致性；结合微测试支持本次两行修复，不声称对所有可能物理冲突作了穷尽证明。', '',
        '## 文件与复核入口', '',
        '- ' + link('独立修复源码', 'benchmarks/java/hca_time_label_repair_v2/App/Astar.java'),
        '- ' + link('限定两格的协议', 'docs/baselines/hca_time_label_repair_v2_two_cell_protocol_20260906.md'),
        '- ' + link('运行前冻结记录（含两条完整 Java 命令及输入/源码/构建 SHA）', 'outputs/runtime/hca_time_label_repair_v2_20260906/preflight/two_cell_freeze.json'),
        '- ' + link('比较明细 CSV', 'outputs/evidence/hca_time_label_repair_v2_20260906/comparison/comparison.csv'),
        '- ' + link('比较与独立重算 JSON', 'outputs/evidence/hca_time_label_repair_v2_20260906/comparison/comparison.json'),
        '- 比较 JSON 中 `limitations` 字段沿用对照快照的 `not_claimed` 列表，列出的正句均表示**本次不作出的声明**，不应当作已成立结论。例如，本次不宣称旧 HCA 的路线时间语义正确，也不宣称仅修复 A* 就证明了无碰撞。',
        '- ' + link('全量路线公式审计', 'outputs/evidence/hca_time_label_repair_v2_20260906/comparison/route_time_audit.json'),
        '- ' + link('map2 新结果', 'outputs/runtime/hca_time_label_repair_v2_20260906/map2_1p00x/seed_104729/hca_time_label_repair_v2/normalized_result.json'),
        '- ' + link('南宁新结果', 'outputs/runtime/hca_time_label_repair_v2_20260906/nanning_1p00x/seed_104729/hca_time_label_repair_v2/normalized_result.json'),
        '- 每个新结果目录保留完整原始日志、逐件统计和逐文件验证的无损 gzip 归档。临时逐 epoch task 文件只在归档通过后清理；清理记录随结果保存。',
        '- 对照快照及新构建的保留副本位于 `outputs/evidence/hca_time_label_repair_v2_20260906/reproducibility/`。原件保留检查仍依赖当前主机记录的原件路径；未宣称该检查可直接在任意主机运行。', '',
        '下列命令只复核现有证据，不启动新的完整仿真：', '',
        '```powershell', 'python -X utf8 scripts/eval/freeze_hca_time_label_repair_v2.py --verify',
        'python -X utf8 scripts/eval/audit_hca_time_label_repair_v2.py', '```', '',
        '**结论范围：仅这两次配对运行。** 本次未扩展为两地图多负载十种子的正式活动，未作显著性检验，也未覆盖或替换旧 180 行结果。', ''
    ]
    output = '\n'.join(text)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if REPORT.exists():
        assert REPORT.read_text(encoding='utf-8') == output, 'refuse to replace a different completed report'
    else:
        REPORT.write_text(output, encoding='utf-8', newline='\n')
    print(REPORT)


if __name__ == '__main__':
    main()
