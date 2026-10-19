# Airport receiver admission v1 变更依据和边界

证据：`outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/C00_cyclic_od_review_001/report.md` 及同目录标准库审计。C00 cyclic OD 新业务合同使全部静态 OD 可达，但在最后边移动 21386.479 后停滞，直到 59400 只完成 7 件。node49 物理空、四项已 departed 的远端 empty-return 接收预留占满其容量；storage53 的唯一出口恰好是 49。不能把静态可达或原生运行闭合作为持续循环验收。

## 接收授权策略

拟新增 node control 字段 `empty_receive_transit_reserve`，默认 0。新研究策略只在 node49 设置 1，字段属于接收端 admission policy，不改变 node physical capacity=4。

原生已有的 source/receiver 权限、空盘状态、minimum stock、有效租约和 receiving capacity 检查继续执行。在 receiver_validate 与 `reception_node` 不可逆提交之间增加检查：若 reserve 非零且 `occupancy(destination, exporting_tray) >= capacity - reserve`，拒绝本次 empty-transfer，保留独立 reason `receiver_transit_reserve`。同一 timestamp 的请求依序检查真实状态，因此第二个请求会看到第一个请求已经提交的预留；sender 的旧快照不产生授权。

物理 `can_enter`、FIFO、edge headway/capacity、节点服务、ACK、immutable retry、已有接收预留、departure expiry、业务装载全部不变。loaded carrier 仍能使用第四个物理名额。拒绝不产生 lease、不改变 tray、不挪走业务、不释放其他托盘义务。只有合法收到或已有明确生命周期事件能结束已提交义务；已 departed 请求不能取消。

默认 0 的观察和 typed digest 不增加字节；非零策略必须以明确版本化段同时绑定 checkpoint seal 和 planning static-contract digest。公共观察仅在启用时暴露静态 reserve 字段，让 owner 知道策略；这不是未来占用信息。invalid reserve、非整数、reserve>=capacity 必须拒绝，不能截断或饱和。

## 为什么需要原生接收端检查

普通 sender observation 只含自己 owner 的实际节点 occupancy。`planning_snapshot_v2/v3` 可以合法传递 receiver 捕获时刻的 occupancy 与 unrepresented occupancy，但它是带时间的旧事实，不是即时 headroom 票据；多个请求之间也不能靠旧 snapshot 防止并发占满。该两 owner 场景可另做 sender 的保守 own-outbox quota 来减少无效请求，但它不是原生授权替代品，也不是一般多 owner 无环证明。

reserve1 保留空盘预留不能占用的最后一个名额，阻止已证实的“四个远端预留持有 49、又等待上游 53”的条件。若第四名额被真实载货占用，下游仍需可进展；因此这个局部策略不证明整个固定图永不死锁。先收集新版本 C00，保留所有失败和未完成，再决定是否值得 C10。

## 源和预算边界

旧 native027 二进制、source archive、contract、所有旧 raw 不修改。新 native028 使用独立 build directory、source archive、build receipt、语义 gate、accepted contract 和运行 acceptance。共同 C++ 源修改等待并行 formal10 结束后协调，不触 `bounded_local_pibt.hpp`。

必须核验：默认0/省略字段与旧027相同输入的实际逐事件与ACK；reserve1在接收提交时生效；loaded可使用保留的第四物理槽；请求幂等；self-reservation只计一次；已departed lease不能取消；invalid值拒绝；非零checkpoint及静态digest绑定；旧planning v3语义回归保留。编译、C++可执行测试、Python原生测试和机场运行分别预登记预算，根代理统一启动，不能把准备或测试收集称为原生通过。

完整 28506 identities/arrivals/storage/releases/deadlines、图、盘、初始化继续固定。共同 warmup 必须从0保留全流和跨边界未完成业务。B1 `model_frozen_at=43200` 不允许在早期8267..21386窗口消费；如果新 admission 保持运行，可预登记43200之后窗口。更早模型需要另立合法训练数据/冻结合同，不能改时间标签。
