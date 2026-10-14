# 原始 raw/canonical 对完整航班组目的域的独立交叉核验

362,234 checks / 0 errors；28,506 件袋、360 个完整原航班代理组，360 个域均非空，48 组旧目的地不在共同域，旧去程不可达 4,001 件。逐组全部候选目的集合与 root 库存相等。

独立构造来自原 timetable 的 (STD,end,Unloader)、投射 raw 的固定源/旧目的、旧 canonical 的 direct/storage_in/storage_out；未用规范化 business rows 构造分组或生命周期。用正容量图的反向遍历重算每一目标的前驱集合，与 root 的正向 BFS/bitset 构造交叉核对。

只有现行正容量共网模式代理下的静态必要条件；真实 empty/owner/EBS 权限未获得，未分配新目的、未删除袋、未证明动态容量或供盘可持续。48 组是整体原子组赋值不合条件，不是要丢掉 48 个航班。

本次独立 CPU 1.0s / wall 1.038271s，0 physical calls；imports 与末尾输出不在计时。
