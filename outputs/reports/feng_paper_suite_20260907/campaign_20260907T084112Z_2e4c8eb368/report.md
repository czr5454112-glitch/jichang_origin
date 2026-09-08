# Feng 论文实验套件：状态与结果快照

生成于 2026-09-07T09:13:32.866295+00:00；状态 **PARTIAL_NOT_A_FINAL_CONCLUSION**。

范围：基础实验 480 格＝两地图 × 1×/2× × 1.5/2.5/3 m/s × 十个共同种子 × 四方法；全天断线实验 1280 格＝两地图 × 1×/2× × 16 情景 × 十种子 × G31/HCA，速度仅 2.5 m/s。动态/静态速度偏差已取消；CIE-DH、Tarau 不在此次故障矩阵。

全部 1760 格均列入 [cells.csv](cells.csv)：终态且后处理结束 15；缺失 1744；运行中 0；后处理/清理中 0；失败 1；证据字段不一致 0。已接受终态中，人口全完 13，人口未全完 2。

**部分进度不能当作全矩阵结论。** 每个组必须齐备预定十种子才显示组平均；THT 比较还要求双方十种子均全人口完成。不会删除不利种子、使用幸存者队列，或将 2× 一律置 NA。有任一缺格/失败/证据不一致时，不宣称全矩阵优势。即使全部完成，也须逐指标判断，保留负收益、持平与劣势。

主口径 THT(D)＝每个原始袋所有规范段的 Σ(E−canonical scheduled D)。这是双方共同计划释放时钟的操作定义；Feng 原文同名 THT 的入网事件与此起点尚未证明完全相同，不能称论文 exact-THT 复现。另一计时口径 THT(native) 用原生 admitted/first-admission，HCA 用成功 planning 后 processed 时间；这些事件也不完全等义，因此两口径均可见，不能据单列认定同一物理 THT 全面优劣。EBS 两段保持共同输入中的独立计划任务，未另加前后依赖。

TH＝固定 98259 s 时域内全段完成的原始袋数；完成率及两种成功率均除以全部原始袋数。STD 成功率使用原始业务 STD；论文文字截止另列 STD−2700 s。后者与现有 EBS 出库计划存在已披露矛盾，不能把两种截止混称准时率。故障影响线路数来自共同输入的 closure，是情景属性，不能算方法传播或性能优势。

此处的终态接受只复核小型结果、状态、冻结 spec/输入身份和指标资格。本脚本不启动模拟、不重算原生轨迹，也不替代独立档案校验或连续几何安全证明。CIE-DH V6 为已披露假设的 V5 适配；Tarau 为路由适配而非原始完整控制器。G31 故障修复使用已通知拓扑的全图势重建；基础正常路径保持原势。两图拓扑、物理执行器和作者修订稿/正式出版全文的证据边界仍然保留。

C++ 的 active-state 执行核验与 bounded lifecycle 日志完整性分列。日志截断时不宣称 full trace。墙钟是各原生运行记录，受并发、宿主负载、实现语言及归档边界影响，不作纯路由算法复杂度排名。
“运行中”指所存运行记录，并非此刻进程存活证明；若匹配执行身份的外层记录明确超时、中止或验证失败，该格列为失败，即使原生状态仍停留在 RUNNING/COMPLETE。外层记录和原生状态均在逐格 CSV 保留。

统计粒度：先计算每种子的袋级 min/mean/max，再对预定十种子的对应统计量取算术平均；下表的 min/max 因而是“种子级 min/max 的平均”，并非把十种子所有袋合并后的极值。配对收益百分比＝(baseline 组均值−G31 组均值)/baseline 组均值（THT），TH 则方向相反；分母为零时百分比 NA，绝对差仍保留。成功率差单位为百分点。未计算置信区间。

## 每组十种子的同口径观测

尚未齐备十种子的组只列状态，全部逐格观测保留在 CSV。D/native 同行显示；NA 不代表零。

|科目|地图/负荷/速度/情景|方法|终态/10；全完/10|TH|完成率 %|STD %|STD−2700 %|THT(D) min/mean/max s|THT(native) min/mean/max s|记录墙钟 s|
|---|---|---|---|---:|---:|---:|---:|---|---|---:|
|基础|map2/1×/1.5/q00|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/1×/1.5/q00|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/1×/1.5/q00|CIE-DH V6|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/1×/1.5/q00|Tarau 适配|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/1×/2.5/q00|G31|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/1×/2.5/q00|HCA V3|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/1×/2.5/q00|CIE-DH V6|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/1×/2.5/q00|Tarau 适配|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/1×/3/q00|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/1×/3/q00|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/1×/3/q00|CIE-DH V6|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/1×/3/q00|Tarau 适配|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/2×/1.5/q00|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/2×/1.5/q00|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/2×/1.5/q00|CIE-DH V6|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/2×/1.5/q00|Tarau 适配|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/2×/2.5/q00|G31|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/2×/2.5/q00|HCA V3|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/2×/2.5/q00|CIE-DH V6|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/2×/2.5/q00|Tarau 适配|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/2×/3/q00|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/2×/3/q00|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/2×/3/q00|CIE-DH V6|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|map2/2×/3/q00|Tarau 适配|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/1×/1.5/q00|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/1×/1.5/q00|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/1×/1.5/q00|CIE-DH V6|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/1×/1.5/q00|Tarau 适配|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/1×/2.5/q00|G31|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/1×/2.5/q00|HCA V3|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/1×/2.5/q00|CIE-DH V6|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/1×/2.5/q00|Tarau 适配|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/1×/3/q00|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/1×/3/q00|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/1×/3/q00|CIE-DH V6|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/1×/3/q00|Tarau 适配|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/2×/1.5/q00|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/2×/1.5/q00|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/2×/1.5/q00|CIE-DH V6|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/2×/1.5/q00|Tarau 适配|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/2×/2.5/q00|G31|1/10；1/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/2×/2.5/q00|HCA V3|1/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/2×/2.5/q00|CIE-DH V6|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/2×/2.5/q00|Tarau 适配|1/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/2×/3/q00|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/2×/3/q00|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/2×/3/q00|CIE-DH V6|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|基础|nanning/2×/3/q00|Tarau 适配|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q01|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q01|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q02|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q02|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q03|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q03|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q04|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q04|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q05|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q05|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q06|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q06|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q07|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q07|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q08|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q08|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q09|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q09|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q10|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q10|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q11|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q11|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q12|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q12|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q13|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q13|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q14|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q14|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q15|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q15|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q16|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/1×/2.5/q16|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q01|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q01|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q02|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q02|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q03|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q03|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q04|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q04|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q05|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q05|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q06|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q06|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q07|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q07|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q08|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q08|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q09|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q09|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q10|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q10|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q11|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q11|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q12|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q12|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q13|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q13|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q14|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q14|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q15|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q15|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q16|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|map2/2×/2.5/q16|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q01|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q01|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q02|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q02|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q03|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q03|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q04|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q04|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q05|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q05|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q06|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q06|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q07|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q07|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q08|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q08|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q09|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q09|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q10|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q10|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q11|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q11|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q12|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q12|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q13|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q13|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q14|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q14|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q15|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q15|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q16|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/1×/2.5/q16|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q01|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q01|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q02|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q02|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q03|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q03|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q04|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q04|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q05|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q05|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q06|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q06|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q07|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q07|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q08|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q08|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q09|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q09|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q10|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q10|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q11|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q11|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q12|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q12|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q13|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q13|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q14|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q14|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q15|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q15|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q16|G31|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|
|全天故障|nanning/2×/2.5/q16|HCA V3|0/10；0/10|NA|NA|NA|NA|NA / NA / NA|NA / NA / NA|NA|

## G31 对各 baseline 的配对结果

正值表示 G31 在该指标较好，负值表示较差；胜/平/负按十个逐种子绝对差计算。主表并列 D 与 native 的均值和最大值收益；最小值收益、双方实数、全部资格和逐种子差值均在 [paired.csv](paired.csv) 与 [snapshot.json](snapshot.json) 中保留。最小值并非自动全面领先。

|科目/地图/负荷/速度/q|baseline|有效/10；THT/10|TH 差（胜/平/负）|TH 收益 %|完成率差 pp|STD 差 pp|STD−2700 差 pp|D mean/max 收益 %|native mean/max 收益 %|D mean 胜/平/负|native mean 胜/平/负|
|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|
|基础/map2/1×/1.5/00|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/1×/1.5/00|CIE-DH V6|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/1×/1.5/00|Tarau 适配|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/1×/2.5/00|HCA V3|1/10；1/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/1×/2.5/00|CIE-DH V6|1/10；1/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/1×/2.5/00|Tarau 适配|1/10；1/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/1×/3/00|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/1×/3/00|CIE-DH V6|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/1×/3/00|Tarau 适配|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/2×/1.5/00|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/2×/1.5/00|CIE-DH V6|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/2×/1.5/00|Tarau 适配|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/2×/2.5/00|HCA V3|1/10；1/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/2×/2.5/00|CIE-DH V6|1/10；1/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/2×/2.5/00|Tarau 适配|1/10；1/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/2×/3/00|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/2×/3/00|CIE-DH V6|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/map2/2×/3/00|Tarau 适配|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/1×/1.5/00|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/1×/1.5/00|CIE-DH V6|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/1×/1.5/00|Tarau 适配|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/1×/2.5/00|HCA V3|1/10；1/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/1×/2.5/00|CIE-DH V6|1/10；1/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/1×/2.5/00|Tarau 适配|1/10；1/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/1×/3/00|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/1×/3/00|CIE-DH V6|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/1×/3/00|Tarau 适配|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/2×/1.5/00|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/2×/1.5/00|CIE-DH V6|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/2×/1.5/00|Tarau 适配|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/2×/2.5/00|HCA V3|1/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/2×/2.5/00|CIE-DH V6|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/2×/2.5/00|Tarau 适配|1/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/2×/3/00|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/2×/3/00|CIE-DH V6|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|基础/nanning/2×/3/00|Tarau 适配|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/01|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/02|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/03|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/04|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/05|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/06|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/07|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/08|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/09|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/10|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/11|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/12|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/13|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/14|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/15|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/1×/2.5/16|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/01|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/02|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/03|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/04|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/05|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/06|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/07|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/08|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/09|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/10|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/11|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/12|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/13|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/14|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/15|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/map2/2×/2.5/16|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/01|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/02|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/03|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/04|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/05|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/06|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/07|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/08|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/09|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/10|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/11|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/12|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/13|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/14|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/15|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/1×/2.5/16|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/01|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/02|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/03|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/04|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/05|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/06|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/07|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/08|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/09|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/10|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/11|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/12|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/13|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/14|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/15|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|
|故障/nanning/2×/2.5/16|HCA V3|0/10；0/10|NA（NA）|NA|NA|NA|NA|NA / NA|NA / NA|NA|NA|

## 证据与重生成

计划 SHA256：`ad400a4363958087625903833fa4730e10c3787864e74180b3f5fa4cfcde4e71`；生成器 SHA256：`f00d7906cb3cd33204f22007e930a6c65ab91bca751b986db2c737ea8fad0210`。
全部 1760 格、1000 个逐种子 G31/baseline 配对、176 个方法组与 100 个配对组均保留。快照逐文件读取，开始/结束时间见 JSON；正在运行的格可能在扫描后改变，因此这是进度观察窗口而非全局原子快照。

```powershell
python scripts/eval/report_feng_paper_suite.py --plan "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\evidence\paper_suite_20260907\frozen_plan_v4\plan.json" --output "新的不存在目录"
```

只写新的报告目录，不覆盖先前快照，也不改变 native、normalized、runner、协议或冻结 plan。JSON 中记录已读取的小型证据文件 SHA，读者可据此复查此时点的具体输入；原生归档是否完整须另行核验。
