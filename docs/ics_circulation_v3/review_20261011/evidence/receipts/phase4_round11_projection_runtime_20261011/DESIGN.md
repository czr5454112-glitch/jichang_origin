# Round11：显式投射运行边界

2026-10-11。只有新增 `business_projection_runtime.py` 和专属作者测试；原输入、投射、运行适配模块以及用户 C++ 均未更改。此设计承接 Round8 BUSINESS_INPUT_DESIGN、归档外审 W2/W4 的完整业务分母/两需求要求，以及 Round11 固定四格协议。文档要求作为研究规格使用，不作为外部操作授权。

运行入口显式接收原 BusinessWorkload、独立 BusinessProjection、完整原 loader 参数、固定外部投射声明、运行时合同、单独 run 合同及 graph profile。run 合同绑定原业务内容、原操作合同、投射内容、投射合同、运行时合同和图六个 SHA。缺项不默认填充。之前已封的 Round10 内容 SHA 可以直接绑定。

进入运行前重新调用原 loader，核验 raw/canonical/父时刻表/规范化文件/两份 manifest/图；重建结果必须完整等于原 BusinessWorkload。随后完整重算投射，核验所有原字段、全父航班及派生族、角色限定目的地与回任一合法 loader 的正容量有向域、精确秒与逐边 ceil tick 截止必要界和固定 salt 排序。投射与 runtime 的最终卸载精确秒必须相等，即使两个不同秒数会取整到同一 tick，也拒绝混用。

适配复用未改变的旧 runtime 对原业务的核验和共同物理构造。仅对私有到达带中 Bag/StorageBag 的 destination 做显式替换，StorageBag 公布时刻与同盘存储合同不变。返回独立 ProjectedBusinessRuntime，绝不生成一份伪装原源的 BusinessWorkload。旧 runtime 仍拒绝投射类型。

原袋全部 source、原 final、新 final 和父族记录保存在 environment_projection，仅供环境/实验来源账。initial 没有未来袋或存储进度；generator_factory 与 simulation_kwargs 只承载旧的公共运行参数，不引用完整投射或未来表。调用方只把 initial、私有 future_bags 和 simulation_kwargs 给 Simulation，投射来源元数据不能传给 policy。窗口必须在完整源适配通过后显式选定。

源文件和图在末尾再次散列，以拒绝重算期间变更。graph profile 可以是同 SHA 不同路径文件；不靠文件名认证。SHA 是调用方固定输入的内容承诺，不是身份或权限签名。如果全部磁盘原件和外部声明同时换成另一组自洽输入，就是另一研究输入；本模块不把它证明为先前审核源。

全量核验预先绑定 Round10 full_audit_002 的 1×/2× 合同和投射内容，不重选 salt 或目的地。1× 28,506 袋、2× 57,012 袋原完整分母都保留；2× 仍不是独立第二观测日。本目录所有作者测试和完整适配审核均为 0 物理推进。root 独立的四部署和 reviewer 的 observe 测试资源在各自目录计数，不在本目录冒认。

资源计量：每次作者测试保存 pytest 原输出、代码快照、前后 SHA、同进程 CPU/wall；parent 已含 pytest，不重复相加。原始导入、编辑/阅读/辅助 shell、初始快照和最终封包未全量计时，归为 unknown auxiliary，不能记作 0。任何失败目录保留，不覆盖。
