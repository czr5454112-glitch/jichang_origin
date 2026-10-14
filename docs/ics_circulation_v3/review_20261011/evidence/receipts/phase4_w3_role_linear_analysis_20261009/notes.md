# 同角色数据的固定成对线性参照

正式数据：`../phase4_w3_role_linear_20261009`。这里只读聚合并核对已有产物，不重训、不重新仿真或选择模型。

16 次拟合全部冻结后完成 216 个 episode：144 个线性模型部署，72 个 baseline/timed 对照。使用同一 R0 的 24 个 checkpoint、96 行正常候选标签，整条 stream 留一；每折只用另外三条训练流。四种线性配置没有种子，分别为 23/31 特征 × paired-direct/residual。共同未来由与 MLP 完全相同的 `deployment_scenes` 产生，每 stream 名义 1 条、压力 8 条。合计 1188/1188 袋完成、0 执行失败。源码、标签输入及冻结模型的运行前后哈希均未变化。

| 方法 | 36 episode 累计成本 | 名义 4 episode | 压力 32 episode | 相比 timed 改善/相同/变差 | 按时/198 袋 |
|---|---:|---:|---:|---|---:|
| baseline | 559.7 | 58.4 | 501.3 | 0 / 36 / 0 | 160 |
| timed | 559.7 | 58.4 | 501.3 | 0 / 36 / 0 | 160 |
| 23 paired-direct | 569.7 | 62.4 | 507.3 | 0 / 29 / 7 | 160 |
| 23 residual | 681.0 | 92.4 | 588.6 | 10 / 0 / 26 | 155 |
| 31 paired-direct | 569.7 | 62.4 | 507.3 | 0 / 29 / 7 | 160 |
| 31 residual | 538.2 | 51.4 | 486.8 | 22 / 3 / 11 | 163 |

这里没有根据结果选模型或改 alpha。31 特征残差线性参照在这批有限开发 episode 上累计成本低 21.5，同时有 11 个变差场景；这既不证明非线性必要，也不证明线性普遍优越。后续应与预声明的全部 MLP 种子和 R1 结果一起比较，不能只挑最优模型。四条相关合成流与压力复制不是独立运营日。

固定 ridge 定义为 `mean((w·(z_candidate-z_reference)-target)^2) + alpha*sum(w^2)`，alpha=1。直接模型 target=ΔJ；残差模型 target=ΔJ−Δtimed，推理加回 Δtimed。训练折均值、标准差和常数列阈值与角色 MLP 一致。成对差中的截距严格消去，参考候选得分恒为零。23/31 个线性权重与 MLP 的 801/1057 参数及 l2=.001 不匹配，正则约定也必须一起披露，不能声称纯粹只改变非线性。对同一调用所有候选取相同值的特征在成对线性模型中会抵消，模型没有非线性交互。

独立复核结果位于 `summary.json`：与 MLP R0 使用的标签 manifest 及逐文件哈希完全相同；36 个场景的初态、已发布预测、真实事件带和 horizon 与公开回放实验完全相同；72 对 baseline/timed 的成本组成、完整物理事件轨迹、最终 Snapshot、任务完成字典、slow trigger 时刻逐项相同。真实未来带只传入外层事件引擎，在线线性打分复用已经审过的 `RecoverySelector` 可见特征与 publication gate。

8 项专项通过：解析项为零时两种模型完全相同、组绝对成本平移不影响拟合、heldout 特征/标签极值不改变训练或归一化、闭式解满足声明损失梯度、序列化、非空输出拒绝，以及模型先冻结和 216 完整失败分母。正式 wall=188.493 秒，process CPU=184.750 秒，其中拟合 CPU=0.172 秒；共机时间只作描述，不作生产性能结论。

```powershell
python -m pytest tests/test_ics_circulation_v3_role_linear.py -q --basetemp .tmp/ics_v3_role_linear_tests_new
python -m scripts.experiments.ics_circulation_v3.run_role_linear --labels outputs/experiments/ics_circulation_v3/phase4_w3_role_coverage_20261009 --output outputs/experiments/ics_circulation_v3/role_linear_new
python outputs/experiments/ics_circulation_v3/phase4_w3_role_linear_analysis_20261009/analyze.py --output .tmp/role_linear_analysis_new.json
```

正式源文件及输出保持冻结。没有修改旧结果、C++ 或 Git。
