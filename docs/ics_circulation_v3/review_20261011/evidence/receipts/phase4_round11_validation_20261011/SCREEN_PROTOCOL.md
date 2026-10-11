# Round11追加开发实验：存储完整路线的终点容量排除

2026-10-11，在原4格运行中、真实checkpoint10800诊断之后声明，不是初始盲注册实验，不修改原PROTOCOL.md或4格结果。

## 已观测触发与推导

预固定projected长窗在10200→10800出现额外搜索开销。10200快照11盘均有plan；10800有2个loaded/no-plan，在K1/h21600/原cache/work10000各耗尽。final47四只其他盘长期预约占满capacity4。每条合法存储full witness必须final arrival≤now+H，且最终节点预约[arrival,INFINITY)，所以[cutoff=now+H,INFINITY)内他盘满容量足以证明当前查询无合法完整候选。中间storage约束不放松此必要条件。这不是永久业务不可行：真实完成、盘派出或合法改路可能改变日历，必须每次重算，不缓存动态否决。

## 实现与适用范围

新增显式storage screen包装/工厂和安装入口；旧默认不变，直接完整StorageCandidate inner执行所有未获证书的查询。必须保持Simulation自动存储包装、checkpoint、私有缓存和factoryfresh的外层screen，不使普通/空盘路径丢失。未知factory/wrapper、slow控制等未支持组合拒绝。非法请求/存储合同/进度按原inner语义处理，max_records未知时delegate，不把预算未知当无解。

先独立小域oracle/合法候选逐字段桥、真实10800反例、ordinary/storage/empty半开容量、同owner去重、zero-dwell、原预算/cache/恢复对照，通过后冻结新源码及全回归再执行新增部署。原4格在旧源码封盘之后才落新生产代码。

## 新增固定部署

单独projected+h21600+screen，从epoch0，原44袋/11盘/固定Round10投射SHA/所有物理规则和FIFO/reactive/实际K1/inner10000预算不变；额外screen_work和screen CPU明确另列。physics600 CPU/900wall、原28500尾界、chunk60，同原规则保留未完成/截断。不得以额外screen工作称严格相同总work10000。

完整query及证书/accounting流式保存；候选/物理记录、周期与最终checkpoint保留。每次certified另保存完整公开Snapshot（gzip level1），以query_id及规范SHA逐条绑定，供独审重算当时真实预约；记录与压缩成本包含在physics CPU中，不视为免费。比较与原projected长窗已保存的共同tick10080及其最终11640，排除仅_ms计时字段后逐physical_result比对；证书查询在原source同状态必要性证明和有限小域oracle支持，不能据此宣称所有有界搜索一般完备。

这项为问题导向的开发确认。原4格、此格及诊断CPU分列；不与原输入不同OD混成算法质量收益，不将不同停止tick的J相减。采集细节增加，未做同仪器等成本随机次序性能试验，不报加速倍率/100ms验收。若仍截断或有未完成，保留失败并定位，不自动提高搜索K/容量或改deadline。
