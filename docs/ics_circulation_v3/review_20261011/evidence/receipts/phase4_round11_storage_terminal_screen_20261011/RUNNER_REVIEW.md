# 新 screen 窗口仪器只读审查

2026-10-11。审查对象 `phase4_round11_validation_20261011/run_screen_window.py`，SHA `8ba50ab758c53dde60b41e085341c5978ffa0e83a5aefea433798c9964b65ab1`。未编辑 runner、production 或测试，未增加查询或物理执行；阅读/静态推理 CPU 未单独计量。

正常返回路径未发现一一对应缺口：

- 每次实际 `_generate` 后递增 query_id，由所有 status 累计计数产生，query 行及 screen 行使用同一 ID。
- 161 行断言当前 live accounting 恰好一行，避免多行遗留或遗漏；163 行可将 RouteCandidate dataclass 正确转 JSON。
- certified 行在 164–168 行另存完整实际 `asdict(self.state)`，以与 wrapper 同样的 canonical JSON 算法复算 SHA，断言等于查询时 public snapshot hash。runtime 的候选过滤仅更新 policy_stats，不改变公共 state；因此可用所存 actual state 独立重算证书。
- 169 行在写出之后清 rows，未清累计 screen_work、screen_cpu、observation_cpu。工厂不共享 mutable accounting，当前持久 generator 的累积不会因每 query 清行而丢失。
- 三个 gzip 在同一 with 作用域，正常或 Python 异常退出都会关闭。正在写入的文件不是完整证据，最终验收须使用 sealed 原件，对 query ID、certified 行、state hash 和证书逐项交叉验证。
- 完整状态哈希、序列化和压缩处于 physical_cpu 区间内，报告可称完整仪器下的物理运行 CPU，不能全部称纯搜索 CPU；screen 和 observation 计时是嵌套项，不额外相加。

边界已立即告知 root：如果 `super()._generate` 抛出异常，函数不会到达 query/screen/state 写出点，该错误账本仍可能在 final checkpoint 的 generator 中，但三个流不会包含最后这次错误。届时应以 execution_failure、异常和 final checkpoint 处理，不声称所有尝试已一一流式保存；当前代码并未把失败写成成功。

runner 的 MeteredSimulation 方法闭包捕获局部 screen_accounting。若未来直接用这个 MeteredSimulation 类 from_checkpoint 继续同一仪器，需要重绑恢复后的 generator accounting；当前 runner 不执行这种恢复。普通 `Simulation.from_checkpoint` 的物理恢复及独立 factory/ledger 行为已有作者和独审验证，不能把本项静态提醒误写成当前运行已发生的恢复错误。

本审查只确认源码路径和观测协议，不替代 root 委派的 sealed 流/真实证书全量独审，亦不预告尚未结束的业务试验结果。
