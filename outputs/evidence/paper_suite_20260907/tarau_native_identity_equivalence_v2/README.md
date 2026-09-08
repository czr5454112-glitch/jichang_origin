# Tarau 新旧原生二进制有界对照

8 组配对通过：map2/南宁 × 1.5、2.5、3.0 m/s 的完整单袋，以及两地图各一个处于已提交 merge grant 内的固定时域截断。对照二进制为原 b00 与最终 38b，均为 Tarau adaptation / M1 / JIT FIFO，G31 故障修复开关关闭。所有 bags、decisions、hold attempts、events、merge lifecycle 的科学字段逐值相同，仅比较时排除性能计时。

12 个完整时长原生记录无改动复用 `../tarau_native_identity_equivalence_v1/native/`；4 个持 grant 的新原生记录位于本目录 `native/`。每格保留完整请求、原生 gzip、二进制/地图/工具身份与 SHA。`verification.json` 给出逐例值和四个结构不变量。

原 horizon=1.1 的探针只截住未使用 merge grant 的第一条边，因此不覆盖所需状态。原件留在 v1。改为从完整轨迹中已知首个 COMMITTED lease 内部截断：map2 的 6→12 在 4.201 到 14.201 秒之间，取 10 秒；南宁的 1→27 在 10.972 到 15.012 秒之间，取 13 秒。该选择用于覆盖状态，未改变算法、拓扑或使用相对性能筛选场景。

两个截断例在新旧二进制中均保留 1 个合法 active grant、0 个 pending，四个结构不变量及 postcommit compensation 通过，无日志截断。原 native `active_state_integrity`/`protocol_integrity` 都为 false，因为它们还要求最后没有 active/pending。不能称这是物理违规，也不能把原标记改成 true。此证据支持基础 Tarau 使用新二进制保持行为；不代表全人口等价、Tarau 原论文精确实现或连续几何碰撞证明。
