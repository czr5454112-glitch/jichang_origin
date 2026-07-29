# G4IRSF14 学习数据报告（Stage H）

- 状态：`INSUFFICIENT_CAUSAL_DATA_NOT_RUN`。
- exact clone/no-op fidelity 已验证，但 completed matched causal labels = 0；screening opportunity 不能代替训练标签。
- Route / Merge / Admission 的 train、validation、audit 都为 0 行。没有执行 split，没有产生任何模型文件。
- B5 需要至少 20,000 个 causal ready-set rows；当前为 0，明确 `INSUFFICIENT_DATA_NOT_RUN`。
- 未计算 accuracy、precision、ECE、harmful rate 或 recovered mean；表中相关字段留空，而不是伪造 0。

生成绑定：`a8db7027c44c66614ac3f7b04f414b10ce7863f066eebcc901177d9cc1ff363a`。
