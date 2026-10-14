# 原图全部实际决策：供盘时序机制

完整693分支均已排空，覆盖174非空状态和另6个无候选尝试。25池的完整周期成本非平坦，12池中实际Timed选择并非事后最优；旧18抽样没有覆盖这12池。全部12均在counterflow，实际选择index0且该候选标is_baseline，但它不是知道未来的oracle。

这些是固定后续控制和单条已复用nominal任务流下的一次当前动作偏离。沿同一路径的状态互相关联；不能把12个局部regret相加称作可部署episode节省，更不能据此按收益挑训练样本。

|d|scene / node / t|bag|role|完整成本向量 c0,c1,c2,c3|全部最优index|最优实际前缀|当前袋完成 延迟|Δqueue wait / Δempty distance|终态改变盘|
|---:|---|---|---|---|---|---|---|---|---|
|19|counterflow / 112 / 46|counterflow:round0:flow1:0|continuation|192.4, 169.7, 169.7, 169.7|1,2,3|112->53|49→86 (+37)|-17 / -57|warm_tray, initial:134:0, initial:26:0, initial:49:0|
|20|counterflow / 113 / 47|counterflow:round0:flow1:0|continuation|192.4, 169.7, 169.7, 169.7|1,2,3|113->115|49→94 (+45)|-17 / -57|warm_tray, initial:134:0, initial:26:0, initial:49:0|
|21|counterflow / 112 / 47|counterflow:round0:flow2:0|continuation|192.4, 165.7, 165.7, 165.7|1,2,3|112->53|51→88 (+37)|-21 / -57|warm_tray, initial:134:0, initial:26:0, initial:49:0|
|22|counterflow / 113 / 48|counterflow:round0:flow2:0|continuation|192.4, 165.7, 165.7, 165.7|1,2,3|113->114|51→97 (+46)|-21 / -57|warm_tray, initial:134:0, initial:26:0, initial:49:0|
|23|counterflow / 115 / 49|counterflow:round0:flow2:0|continuation|192.4, 165.7, 165.7, 165.7|1,2,3|115->117 ; 117->118|51→97 (+46)|-21 / -57|warm_tray, initial:134:0, initial:26:0, initial:49:0|
|40|counterflow / 26 / 126|counterflow:round1:flow1:0|origin|192.4, 146.7, 146.7, 146.7|1,2,3|26->27 ; 27->2|139→157 (+18)|-40 / -57|warm_tray, initial:49:0|
|41|counterflow / 112 / 129|counterflow:round1:flow2:0|continuation|192.4, 153.8, 153.8, 153.8|1,2,3|112->53|133→170 (+37)|-33 / -56|warm_tray, initial:26:0, initial:49:0|
|42|counterflow / 113 / 130|counterflow:round1:flow2:0|continuation|192.4, 153.8, 153.8, 153.8|1,2,3|113->114|133→178 (+45)|-33 / -56|warm_tray, initial:26:0, initial:49:0|
|43|counterflow / 115 / 131|counterflow:round1:flow2:0|continuation|192.4, 153.8, 153.8, 153.8|1,2,3|115->117 ; 117->118|133→178 (+45)|-33 / -56|warm_tray, initial:26:0, initial:49:0|
|46|counterflow / 29 / 133|counterflow:round1:flow1:0|continuation|192.4, 146.7, 146.7, 146.7|1,2,3|29->30 ; 30->31|139→157 (+18)|-40 / -57|warm_tray, initial:49:0|
|48|counterflow / 112 / 136|counterflow:round1:flow1:0|continuation|192.4, 146.7, 146.7, 146.7|1,2,3|112->53|139→176 (+37)|-40 / -57|warm_tray, initial:49:0|
|50|counterflow / 113 / 137|counterflow:round1:flow1:0|continuation|192.4, 146.7, 146.7, 146.7|1,2,3|113->115|139→184 (+45)|-40 / -57|warm_tray, initial:49:0|

最强反例按完整局部regret降序、时间升序确定为d40（并列45.7中最早）。t126的round1:flow1原走26→27→28，后续到114，139完成；最优当前合法前缀改为26→27→2，后续原控制继续绕行，157完成，比原来晚18但仍早于deadline211。原执行在139立即将114的initial:49:0承诺空返26，路程70，209才装载t156到达的round2:flow1，222完成。替代分支在t156由reactive empty_dispatch调用原先停在46的warm_tray，经46→39→40→52→26，169装载，182完成。当前袋变慢18，后续袋提前40；全期queue wait下降40，empty distance下降57，J下降45.7。

此共享资源链是实体空盘可用性与承诺，不是已证实的某条边容量瓶颈。26和46同属international，114属domestic。原PredictivePrebalancer跳过同zone供盘，reactive dispatch可响应同zone可见任务；原分支的既有承诺阻止重复供盘。因而路径偏离通过改变卸载时刻间接改变后续供盘。成本没有独立的loaded travel项；本例当前袋虽变慢仍准时，所以解释必须附带成本权重和固定slow continuation。

普通反例取全部正regret中最小值并按时间确定d19（22.7）。t46在112，当前前缀由112→113改112→53；当前round0:flow1完成49→86，晚37但仍早于deadline151。原initial:26:0于49提前承诺空返，替代分支改由round0:flow2的initial:49:0在51空返；round1:flow1在96到达后由46的initial:134:0响应，109装载/122完成，原126装载/139完成。此后也有代价：round2:flow0完成157→172（晚15），同时round2:flow2完成216→205，round2:flow1完成222→217。所有到达、实际装载和完成时间均保留，不能仅展示提前的袋。全期queue wait净下降17、empty distance下降57，J下降22.7。

25非平坦分类：{'origin|timed_prefix_only': 1, 'continuation|timed_prefix_only': 2, 'continuation|spatial_prefix': 21, 'origin|spatial_prefix': 1}。另51个cost-flat但完成时间向量或终态盘位置不同的池分类：{'continuation|spatial_prefix': 47, 'origin|timed_prefix_only': 1, 'continuation|timed_prefix_only': 2, 'origin|spatial_prefix': 1}。成本平坦不等于物理轨迹相同。mechanisms.json保留全部25/12/51身份，以及12对分支完整装载账、空载/载袋逐边移动、控制事件、完成变化、盘终态和原始文件SHA。

独立逐事件复算12对分支：queue wait等于各load time−arrival之和，empty distance等于空载depart所用边travel_time之和；74 checks，0 errors，无新仿真。
