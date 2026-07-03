# G4IRSF4 简单中文总结

这次目标是把 G4IRSF3 的“全任务覆盖但分块重置状态”推进到连续状态仿真。

- 连续仿真任务数：348824；成功：348824；失败：0。
- A* 快的结论仍然只属于静态路径下界，不能当完整 Java/CIE runtime。
- 连续仿真没有 `loop_detected` 失败；loop autopsy 表为空，因此没有失败子集变体需要运行。
- 18->22 前避让已经作为 `model_plus_pibt_lite_fault_aware_v1` 接入 C++ runtime，并做了 no_fault / static_fault / repair / multi_fault 子集评估。
- 原 Java/CIE baseline runnable：False。原 Java 已能用发现的 jar 在临时目录编译，但 `RUN.Main` headless 运行触发 `HeadlessException`，所以不能用它做论文级最终对照。
- 不进入 G4J；负结果保留。
