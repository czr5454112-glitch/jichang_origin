# 公告 release 引起的同界搜索平原：复现与修复

2026-10-11。完整第一小时原图窗口发现可行候选搜索连续耗尽。此修复只修改 storage_routing.py 的同 f 展开次序，不改任务、时钟、K、horizon、工作预算、容量、保护约束或权重。普通袋/空盘仍走原 delegate，无新缓存。

## 先保留旧原件，再定位

baseline_001保存旧路由源码及测试、源checkpoint_8400、旧代码实际推进到8876的checkpoint和完整query state/generator。源checkpoint SHA为 f4abaf7f735b8bcbe41c86fe943fcf8752a716ebe09cd38621d18ece565c4a18，旧代码 SHA为 f438f178ba123d6cb002babc7f9ae50d6d918f28e83d9969846f26731288e116。原正式窗口文件未改。

目标是同一实际状态中的 projected:1x:2、真实盘 proxy-initial-26；horizon=21600、expansion_limit=10000、K=4、release=19500。旧代码返回0候选、10000展开耗尽。其预处理为227图边+341反向距离工作，实际 product pops=9317。这个保存边界由指定旧checkpoint推进并observe获得，是可复现的原物理边界；展开分解与root早先日志有少量差异，不冒称是日志中另一次query的逐字节复刻。

独立 instrumentation 仅包裹旧模块的 heappop，不改优先级：**9317次 pop 的 f 全部是19749**，其中9205尚未经过EBS，112已经过。说明根因是已公告 release 让 max(arrival_to_storage, release)+remaining_to_final 在大段等待区间内恒定，FIFO 在同界标签间广搜大量时间/回路状态，未推进到完整终点。

## 实现及同输入验证

新heap键是 (最终到达下界 f, 剩余必经静态旅行时间, 是否尚未经过EBS, FIFO序号)。f主序完全保持。经过EBS之前的次键为 d(node,EBS)+d(EBS,final)，之后为 d(node,final)。它只决定同f标签的探索顺序，不删除路径、任务或必经点。原state-label K上限、所有预约及完整ExecutionValidator都保留；候选仍是有界启发式集合，没有新增全局最优或完整性声明。

comparison_001在保存的同一query state上，新代码返回 **4个候选、670展开**，每个完整witness均通过硬校验。图227+反向距离341与旧代码相同，product标签68、event projection30、完整校验4；没有隐形冷热缓存优势。单次query elapsed约4.07ms，CPU读数0是Windows process_time量化，**不表示没有成本**。旧query elapsed约138.75ms；两次请求受并发环境影响，此处只作为诊断原件，不称严格性能基准或100ms保障。

新增100条正旅行时间回路的手算反例：合法EBS入口在稳定边序最后，release=10000、原预算500。旧代码500耗尽无候选，新代码413展开返回完整合法路线；没有把回路变成0成本或取消原资源。27项路由测试通过，旧26项继续通过，代码SHA更新为431f4e4a1baf2a20e27561ac4ef722b67223b118dda9819aa3b96fa69340b4ea。

## 保留仍未解决的反例

同一合成图若EBS节点占用到10002，存在晚到库的合法witness（已由原validator确认），但忽略日历的低f回路仍可压住更高f可行路线。旧/新在500预算内都耗尽。该结果完整保存在synthetic_comparison_001；当前修复没有声称解决所有容量导致的下界松弛。后续可研究资源时窗下界或更强的标签支配，但必须证明不会排除合法等待/循环解，不能简单删回路或把预算未知说成不可行。

## 资料与推断范围

研究同f平原的第一方文献：[Asai & Fukunaga, AAAI 2016](https://ojs.aaai.org/index.php/AAAI/article/view/10071)讨论tie-breaking对大平原搜索成本的影响；[Corrêa、Pereira、Ritt, IJCAI 2018](https://www.ijcai.org/proceedings/2018/655)说明常用tie-breaking没有普适最优展开保障。这些文献支持分析同f排序，而本文的release平原来自正旅行时间加公共release下界，是对本代码的实测机制解释；没有把文献中的零成本动作假设直接冒用到ICS。

## 资源与分母

| 项目 | CPU秒 | 物理推进 | 独立query |
|---|---:|---:|---:|
| baseline_001：旧checkpoint推进与query | 2.796875 | 1个8400→8876局部continuation | 1 |
| 旧heap instrumentation | 0.234375 | 0 | 1 |
| 同state新query与校验 | 0.0625 | 0 | 1 |
| 两合成图×旧/新 | 0.375 | 0 | 4 |
| 路由run_004，27tests | 0.828125 | 无原图业务批次 | 单元测试内部 |

本次已计量CPU合计 **4.296875秒**。baseline中continuation CPU2.53125与query CPU0.125已包含在2.796875中，不再相加。资料检索、阅读、代码/文档和编排属于未统一计量auxiliary。新增局部continuation用于故障复现，不作为新的完整业务日或独立确认样本。最终完整测试和新窗口由root统一执行。
