# 下一轮业务／EBS／头距设计的只读审阅

2026-10-10，full_cycle agent。未修改 canonical、旧原件或主实验，没有新增物理回放。代码阅读、定位、推理和本笔记写作没有完整 CPU 计量；不能把工具 wall 当 CPU，未知辅助成本保留。

审阅范围为 root 分析目录的 `projection_domains.py`，主 `PHASE4_CONDITIONAL_FUTURES_AND_COST.md` 第 5 节，以及其引用的 `PROJECTION_BRANCH_DESIGN.md`、`BUSINESS_INPUT_DESIGN.md`、`EBS_CARRIER_SEMANTICS_SOURCES.md` 和 `ENTRY_HEADWAY_DESIGN.md`。这是设计和源码阅读，不重复运行投射核算；独立数值重算由 control_method 负责。

## 当前判断

- 投射程序保留全部 28506 业务袋和 360 个航班代理组，断言原 source 绑定、无 synthetic 插入、无 time shift，每组完整求交。它没有选择新目的地、改图、改输入、删除袋或启动物理模型。
- 所有正容量有向边在两种 carrier mode 共用，只是显式宽松代理；容量为 0 的边保持关闭。真实 mode、owner、接收和 EBS 能力未被代码确认，文档也保留这些缺口。
- `unloader → 任一 loader` 的静态存在性没有被当成全系统持续供盘保证。有限盘量、各源流量平衡、共享容量、owner admission 和动态回压在设计中仍独立要求。组内候选域非空也没有被当成有业务配额的全局联合分配可行证书。
- on-carrier 与 off-carrier 的袋、盘、库存、释放因果关系明确分开。公开固定 release 的 waypoint 代理适用范围已经收窄，未冒称动态 release、专用检索设备或完整现场 EBS；原袋最终完成和保护分母仍保留。
- 头距设计已经识别 arrival/unload 清预约、后缀 anchor 截断、同盘自身排除、old-in-transit 历史缺失、进入标记的同 tick 阶段、no-wait 前推、owner 原子提交、私有缓存签名及有限参考状态合并问题。入口尾窗与整盘忙状态分离，关闭模式的旧行为桥接也明确。

## 两项具体文档补强建议

1. 主文“48 组原目的不在其合法域”建议称“宽松静态结构候选域”。程序字段 `feasible_destination_domain` 只代表当前代理图的必要条件，没有证明真实业务许可。该措辞建议不影响已算结果，也不要求重跑或改变目的域。
2. on-carrier 第一批反例应显式同时核 `known_supply` 与条件供给预测：到达 EBS、库内持盘、出库授权未到时均不能增加空盘信用；最终空盘 ETA 不得早于公开 release 加合法余程、最终卸载和 hold。仅把 stage/release 放入 checkpoint/cache/forecast hash 不足以保证旧供给 ETA 代码符合新时序。off-carrier 的真实转存完成／hold 后供给与此分开检查。

未发现需要停止当前已冻结 Round8 结果分析的阻断问题。上述建议面向下一轮建模，不能把模型补齐本身作为控制算法收益，也不能用它替代原两项需求、正常服务保护或 W2/W4 权限与数据要求。
