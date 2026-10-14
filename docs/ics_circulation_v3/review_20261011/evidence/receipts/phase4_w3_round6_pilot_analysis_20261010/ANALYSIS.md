# 第六轮完整供盘对照：纯原件分析

检查 2103 项，错误 0；没有调用仿真或策略。

全部预声明方法、场景、tape均保留。三个合成开发源重复使用，未新增独立运营日。机制差值不能相加为部署收益。

|阶段|范围|方法|运行数|J（完整时可比较）|完成/任务|准时|对old32 好/同/差|invocation CPU秒|
|---|---|---|---:|---:|---:|---:|---|---:|
|mechanism|all|old32|2|339.100|20/20|20|0/0/0|47.000|
|mechanism|all|old64|2|339.100|20/20|20|0/2/0|46.891|
|mechanism|all|same_zone32plus32|2|294.800|20/20|20|1/1/0|45.562|
|mechanism|counterflow|old32|2|339.100|20/20|20|0/0/0|47.000|
|mechanism|counterflow|old64|2|339.100|20/20|20|0/2/0|46.891|
|mechanism|counterflow|same_zone32plus32|2|294.800|20/20|20|1/1/0|45.562|
|nominal_pilot|all|old32|3|235.800|24/24|24|0/0/0|127.500|
|nominal_pilot|all|old64|3|235.800|24/24|24|0/3/0|127.344|
|nominal_pilot|all|same_zone32plus32|3|93.800|24/24|24|1/2/0|129.438|
|nominal_pilot|cross_cycle|old32|1|29.700|7/7|7|0/0/0|29.875|
|nominal_pilot|cross_cycle|old64|1|29.700|7/7|7|0/1/0|30.016|
|nominal_pilot|cross_cycle|same_zone32plus32|1|29.700|7/7|7|0/1/0|30.266|
|nominal_pilot|counterflow|old32|1|192.400|10/10|10|0/0/0|62.109|
|nominal_pilot|counterflow|old64|1|192.400|10/10|10|0/1/0|61.656|
|nominal_pilot|counterflow|same_zone32plus32|1|50.400|10/10|10|1/0/0|63.156|
|nominal_pilot|near_full|old32|1|13.700|7/7|7|0/0/0|35.516|
|nominal_pilot|near_full|old64|1|13.700|7/7|7|0/1/0|35.672|
|nominal_pilot|near_full|same_zone32plus32|1|13.700|7/7|7|0/1/0|36.016|

## 机制6格

|方法|c0 J|c1 J|c1−c0|
|---|---:|---:|---:|
|old32|192.400|146.700|-45.700|
|old64|192.400|146.700|-45.700|
|same_zone32plus32|148.100|146.700|-1.400|

逐tape全部配对、逐袋完成变化、同区实际承诺、guard拒因、预算与源绑定均在 analysis.json；未将成本下降自动解释为每袋服务改善。

## 全部非零配对结果

|阶段|场景/tape|c|方法|ΔJ|Δ准时|
|---|---|---|---|---:|---:|
|mechanism|counterflow/checkpoint_nominal|0|same_zone32plus32|-44.300|0|
|nominal_pilot|counterflow/nominal|None|same_zone32plus32|-142.000|0|
