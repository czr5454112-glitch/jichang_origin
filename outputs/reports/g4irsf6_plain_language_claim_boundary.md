# G4IRSF6 中文结论边界

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
artifact_generation_head: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
committed_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
remote_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

1. 这次没有改 legacy Java，也没有改真实主地图。
2. no-A* 在同一天输入和同一个 THT 口径下可以复现接近论文 2.5 m/s 主指标的结果，但它不是论文里的 IoT-DRPA/HCA* 或完整 Java/CIE 运行时。
3. 静态 A* 只能当最短路下界，不能当 Java/CIE 基线，也不能拿来宣布胜过论文方法。
4. 348824 高流量结果是扩展实验，不是论文 28506 件行李主协议。
5. 故障和动态/静态表已经按袋级成功率或协议字段拆开，但因为运行时责任和扰动机制不同，不能混合成胜利结论。
6. G4J 继续关闭；只有在同输入、同指标、同速度、同时间范围、同故障设置、同运行时责任全部满足时，才允许谈 winner。
