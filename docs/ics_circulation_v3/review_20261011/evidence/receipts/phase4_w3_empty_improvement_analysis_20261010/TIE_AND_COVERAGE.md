# 平局、实际候选覆盖与旧强对照

全部252原件重读；本追加分析无新仿真。`tie_and_coverage.json`保留36个new-vs-legacy直接配对，包括32成本相等项，及全部三组预算/窗口轨迹核对。

**预算没有饱和。** new12h40、new24h40、new24h80每次最多只评7条序列；未评分已枚举动作、未搜索请求、丢弃合法候选、剩余搜索节点均0。三版没有一个depth2序列得到评分，本开发族实际供需域尚未形成两项联合空调。12→24以及40→80各36对的h80/final完整物理result（仅去policy毫秒字段）、route history与slow实际动作均一致。greedy→new2也36/36全部一致，等待对照没有改善。不得包装为更大搜索预算、长窗或联合depth2的实验成功。

**旧强对照优于新方法的差额集中在4/36，合计16.2成本、4个准时任务。** 两个L2_D3压力例各+6；L2_D1 stress4、L4_D1 stress7各+2.1。其余32对成本相等。四例首slow分歧前的物理trace、当前tick前loaded决策、snapshot version均一致；旧legacy没有完整snapshot hash，故不将该前缀核对伪称直接完整state哈希证明。

1. L2_D3 stress0/stress4在t24/t26：new保留greedy的B盘loaded→C，而legacy的no-transfer与此调拨proxy同分，按动作数优先选空序列。同tickreactive从G选donor→C（两盘ETA同为2，reactive按盘名排序），当前逆向C→B任务完成时刻不变，却交换后续供盘身份。到t34下一轮预测公布，legacy两盘都在B，可把donor预调S于37可用，S任务40装载45完成；new的B盘须守B需求，G盘与S同zone被慢层跨zone候选规则排除，40才reactive返回S，43装载48完成。每例wait+3、tardy+3=+6。这不是把no-transfer误当成实际静止。
2. L2_D1 stress4与L4_D1 stress7在t34：new的delayed/early/no-transfer在其timed+未来greedy proxy下同分，保留delayed incumbent；legacy没有未来慢层，no-transfer更贵，early与delayed同分时按physical key选early。delayed在CS40/SX41形成不可撤销预约，真实逆向G→S任务到达后S盘被迫选SY/YG去G47才可装载；legacy此前已走完SX，S盘走SX/XG于G46装载。该袋51→50完成，deadline50，从逾期变准时；每例wait1+tardy1+加权empty0.1=+2.1。

候选在new池中已存在，增加到24或80未打破这些平局。简单移植legacy tie也不等于legacy：在new proxy中no-transfer往往因后续greedy补调而同分，旧legacy却给它较高成本。接下来的完整36条流2×2开发消融因此固定同一候选构造、K、预算、公开proxy、真实执行，只交叉proxy continuation（timed+未来greedy / earliest+reactive无未来slow）与tie（原incumbent / 少转移后physical key）。所有四配置保留，不能只报最优一格或称独立确认。
