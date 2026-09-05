# Feng CIE 正式出版身份补齐与全文核对边界（2026-09-05）

**正式出版身份已确认；正式全文的 DH 步骤和 Table 4 仍未核对。** 本次只核实来源，未修改 V5、实验输入、采用记录或已冻结协议，也没有启动模拟。

## 已确认的出版身份

Xiuqing Yang, Ruchen Feng, Pengcheng Xu, Xiaorui Wang, Mingyao Qi. *Internet-of-Things-augmented dynamic route planning approach to the airport baggage handling system*. **Computers & Industrial Engineering, 175 (January 2023), 108802**. DOI **10.1016/j.cie.2022.108802**。[出版社正式页面](https://www.sciencedirect.com/science/article/pii/S0360835222007902)，[DOI](https://doi.org/10.1016/j.cie.2022.108802)。作者次序依据出版社页面的 CRediT 列表；出版年月采用卷期显示，不将 DOI 中的 2022 当作卷期年份。

本地 F2 的第一页题名相同，页脚为提交给该期刊的预印本日期 **May 1, 2022**。F2 是 `CIE/manuscript-ics 一审修改后查验.pdf`，共 37 页，SHA-256 `6c317372affd636ad85011f85c939b5cfbe217b2ef1365280acba1122ede59fa`。本次重新读取其第一页和第 26 页的已提取文本；相关页此前已渲染检查，身份和页码见[一手语义审计](feng_dh_primary_semantics_reaudit_20260905.md)。同题名可以建立文献对应关系，不能证明版本逐字相同。

## 可核对与不可核对

| 项目 | 本地一审修订稿 F2 | 出版社公开可见内容 | 本次结论 |
|---|---|---|---|
| 摘要及引言的主要比较结论 | 平均效率对 DH 约改善 10%；纳入实时信息后平均时间约改善 5% | 官方摘要保留这两个约数；引言仍说明 DH 比较为 adapted comparison | 主要结论一致；不是完整论文文本一致性证明。 |
| DH 状态更新、选路和阻塞步骤 | 第 25–26 页说明 0.2 s、逐袋更新、最短路径上的 moving/stopped 罚时及出口首位阻塞 | 当前能取得的官方内容为摘要、引言及章节片段，未含这组完整步骤 | **不可核对正式版是否改写或补充步骤。** |
| Table 4 | 第 26 页：DH min/mean/max 为 3.56/4.43/8.62 分钟；centralized heuristic 为 3.13/3.96/5.98 分钟 | 可取得的官方片段未含该表 | **不可核对正式版表号、数值、表注或统计定义是否相同。** |
| DH 机械实现的完整身份 | 没有恢复出独立 DH 源码、精确更新顺序和全部物理参数 | 未取得正式全文，不能据摘要补足这些信息 | 保留 partial reconstruction；本次不改变 V5 的证据等级。 |

表中的正式页面比较仅依赖出版社公开内容，不依赖检索到的第三方综述或转述。摘要近似百分比相同，也不足以反推出正式表中的精确数值。

## 获取范围与停止点

2026-09-05 沿本地 F2 精确题名检索出版社和作者公开来源。ScienceDirect 正式记录可由公开搜索内容读取；其正常文章/PDF 入口在本次工具中返回抓取失败，未获得正式 PDF 字节，故没有可登记的正式全文 SHA-256。该技术失败本身不能证明论文不存在合法全文或必然付费。

已检查通讯作者的[清华官方英文主页](https://www.sigs.tsinghua.edu.cn/qmy_en/main.htm)，可见论文列表未提供本篇全文下载。没有使用付费墙绕过、镜像全文、机构凭证或代发索取消息；未检索到公开全文仅描述本次可见范围，不宣称作者从未公开稿件。

当前准确表述为：**已经阅读并对照 Feng 学位论文、CIE 一审修订稿和审稿回复；现已核实 CIE 的正式出版题名、卷期及 DOI，但 publisher-final 的 DH 步骤与 Table 4 尚未核对。** 后续若取得出版社可合法访问的全文或作者公开终稿，应登记实际文件身份并直接比较上述两处；在此之前保持 revision 边界。
