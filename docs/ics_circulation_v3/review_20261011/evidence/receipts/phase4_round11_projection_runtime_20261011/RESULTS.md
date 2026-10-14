# Round11 显式投射适配交付

生产入口 `scripts/experiments/ics_circulation_v3/business_projection_runtime.py` 已冻结，SHA `368fc8c2bfd581aabf6df8557c694ace8941f49c7ea3787be7d9c152ebe48fdd`。专属作者测试 SHA `ab77f744eb302009ed11eb0b18a4738661200ff5df948fb860322c63439477b1`。原 business_inputs/business_projection/business_runtime 和用户 C++ 未改，未提交或推送。

`author_tests_001` 44 项通过，CPU **3.515625** 秒、wall **3.714687** 秒、0 物理推进、前后源码无漂移。测试覆盖完整原/派生父族、只改私有最终目的地、原 final 与源身份保留、固定外部六 SHA、缺参数拒绝、全部七原件字节变化、主动重封双对象及所有内存声明仍拒绝与磁盘源不符、全域/成员/分组篡改、精确卸载秒数、验证期间源变更以及旧 adapter 拒绝新类型。

独立 `phase4_round11_independent_review_20261011/attempt_002` 55 项通过；其自建原/派生 fixture 和真实 observe 测试另含 2 次小型物理，属于独审 receipt，不在作者测试 0 物理数字中。该目录 `attempt_003` 全 ICS 回归 **1399 通过 / 0 失败 / 0 错误 / 0 跳过**，87 文件，普通桥精确一致，源码无漂移。其 parent CPU 和 bridge child 分列在总账。

## 调用方式

```python
adapted = build_projected_business_runtime(
    original, projection,
    source_inputs=source_loader_kwargs,       # 原 loader 完整八参数
    projection_declaration=frozen_projection_json,
    runtime_contract=explicit_runtime_json,
    run_contract=frozen_run_json,             # 六 SHA + RUN_POLICIES + 明确证据字段
    profile_path=original_graph_path,
)
engine = Simulation(adapted.initial, adapted.future_bags, **adapted.simulation_kwargs())
```

仅环境接收 future_bags。完整 provenance 位于 `adapted.environment_projection.original/.projection/.run_contract`；不能传给 policy/generator。本例不代表已运行物理。真实四窗口由 root 独立 runner 执行、单独记录。full_adapter_002 的 run_contract_1x.json / run_contract_2x.json 给出可运行的完整显式 run 字段。

## 全源 0 物理适配核验

`full_adapter_002` 已通过，parent CPU **187.984375** 秒、wall **191.6223743** 秒、0 物理推进，生产/测试和审计脚本前后 SHA 无漂移。进入适配器时第二次重读原 loader，随后完整重算投射父族和域；与 Round10 已封投射内容 SHA 完全一致。原目的地 adapter 与新 adapter 的全部 85,518 件私有 Bag/StorageBag 逐一比较，唯一差异是已声明的新 destination。

| 核验分母 | 1× | 2× |
|---|---:|---:|
| 业务袋 | 28,506 | 57,012 |
| 原运输段 | 43,603 | 87,206 |
| 原始/派生袋 | 28,506 / 0 | 28,506 / 28,506 |
| 早包 | 15,097 | 30,194 |
| 完整父航班组 / 实例 | 360 / 360 | 360 / 720 |
| 按原固定映射改变 final | 4,001 | 8,002 |
| 初盘 / 初态公开袋 | 11 / 0 | 11 / 0 |

两档相同父航班的目的地决策完全相同。`private_runtime_tape_1x.jsonl.gz` 与 `private_runtime_tape_2x.jsonl.gz` 每行保存完整原 BusinessTask、新 runtime Bag/StorageBag、原 final、新 final、父族 ID 与 run 合同 SHA。来源、精确时钟、硬截止、保护、库位/公布/释放、旧段、有限盘、原图及关闭边不变；此私有审计表不能暴露给策略。完整输入、运行合同、投射合同/内容、文件字节以及源码散列均在 resource/manifest/run_contract 中可追溯。

1× 阶段 CPU 64.5625、2× 阶段 123.40625 已含在 187.984375 parent，不能再相加。作者子任务已知 CPU **197.4375** 秒 = 测试 3.515625 + 失败首轮 5.9375 + 完整成功 187.984375；辅助编辑/阅读/初始 imports 和末尾封包时间未知。失败 `full_adapter_001` 原件保留，详见 FAILURES.md。

静态投射只能改变输入的结构可达性，不能据 adapter 通过宣称容量可行、真实业务分配或算法收益。2× 仍是同源完整航班插入增密，不是独立第二观测日。本目录不新增任何生产部署；root 四窗口和各独审另列资源，总账见 `../phase4_round11_resource_ledger_20261011/`。
