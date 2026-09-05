# 常见问题

核心实验在 `high_overlap` 与匹配的 `uniform` 实例上比较 Greedy 和穷举参考。
已完成的[对照实验分析](../analysis/overlap_pilot_v1.md)介绍了结果及其解释范围。

<!-- faq:id=problem-definition -->

## 什么是最大覆盖问题？

给定有限的元素全集、候选集合和预算 `k`，至多选择 `k` 个集合，使并集覆盖尽可能
多的元素。这里用 `universe_size`、`set_count` 和 `k` 描述实例；coverage 是所选
集合并集中不同元素的数量。

<!-- faq:id=why-study -->

## 这个项目研究什么？

最大覆盖具有经典的 Greedy 基线。本项目研究实例结构与 Greedy 相对同一实例
最优值的差距有什么关系。当前[固定配置](../configs/core_overlap_pilot.json)
比较共核式生成机制与维度、理论期望集合大小匹配的 uniform 对照。

<!-- faq:id=theoretical-bound -->

## 为什么不只使用理论保证？

经典 Greedy 保证描述算法覆盖量与最优值之间的最坏情况关系，不能直接指出某次
实验中哪些结构会产生更大的 gap。经验比较描述所采样的实例和生成机制，不改变
原有理论保证。

<!-- faq:id=algorithm-roles -->

## 当前实验主要使用哪些算法？

**Greedy** 是研究对象：每轮选择边际增益最大的集合，增益相同时优先选择较小
索引。**Brute Force** 为这次小实例实验提供穷举参考，配置中不设时间限制。
比较两者的整数覆盖量可以判断 Greedy 是否失手，相对 gap 则说明损失幅度。

其他工作流用 **Lazy Greedy** 在保留选择规则的同时减少边际增益评估，用
**Local Search** 检查邻域改进能否恢复损失，用显式设种子的
**Randomised Greedy** 和 **Multi-start Local Search** 探索其他选择。
**Branch-and-Bound** 和可选的 **CP-SAT** 提供其他精确参考候选。
CP-SAT 需要 OR-Tools，核心实验不需要该依赖。惰性评估本身不保证普遍的运行时间优势。

<!-- faq:id=reference-status -->

## 什么才算有效的精确参考？

核心实验要求穷举运行完成并返回 `status=optimal`，所选集合的实际覆盖量与记录值
一致。其他工作流也可以使用经独立校验的构造证书。

`feasible` 表示已有可行 incumbent，但没有最优性证明；它本身不能说明执行已经
完成，停止原因要看 `algorithm_metadata.termination`。`timeout` 表示达到时间
限制，`error` 表示没有有效算法结果，两者都不能提供参考最优值。
字段约定见 [`output_schema.md`](output_schema.md)。

<!-- faq:id=instance-families -->

## 当前包含哪些实例族？

核心比较使用 `high_overlap` 和 `uniform`。补充工作流改变聚类、集合大小、覆盖
集中程度、重复、支配关系和对抗陷阱。`controlled_*` 实例族提供独立的结构扫描，
明确控制维度和 incidence（集合成员关系总数）。

设计某种结构压力不等于已经观察到 Greedy 失手，需要检查实际实例及其参考值。
已知对抗构造有各自的参数条件。机制与命令见
[`failure_mechanisms.md`](failure_mechanisms.md)，受控扫描保持哪些量不变则见
[`generator_isolation.md`](generator_isolation.md)。

<!-- faq:id=synthetic-families -->

## 为什么使用参数化实例族，而不使用真实世界数据？

参数化实例族让指定的变化更清楚，有助于检验候选机制并估计描述性关联；但它
本身不能建立因果关系，也不能证明对真实世界的泛化能力。匹配期望集合大小后，
其他结构属性仍可能同时变化。

配置允许时，不同 case 共享有效 seed。相同 seed 不保证不同生成器逐次抽样对齐，
也不保证降低方差；随机数的消费规则见 [`paired_seed_audit.md`](paired_seed_audit.md)。

<!-- faq:id=no-results -->

## 已完成的结果在哪里？

高重叠对照实验未获得足够的 Greedy 失效率差异证据，这不证明两个总体等价，
也不说明重叠度本身的影响。[C1](../experiments/core_rq/CLAIMS.md#c1) 将这一结论
对应到冻结证据，[实验分析](../analysis/overlap_pilot_v1.md)解释比较方法与适用
边界。[研究索引](../analysis/README.md)列出已发布的工作。

<!-- faq:id=content-boundary -->

## 如何检查公开结论？

每条结论通过 claim 台账连接到对应证据。发布与审查要求统一维护在
[`CONTRIBUTING.md`](../CONTRIBUTING.md)。

<!-- faq:id=determinism -->

## 这里的确定性是什么意思？

在规范化配置、生成器及算法版本、显式种子相同的情况下，已完成的运行会复现
实例身份、选中的集合索引、覆盖值以及规范行排序。实际运行时间、时间戳和
环境元数据可能因机器而异。被墙钟限制中止的运行报告其在限制触发时已达成的 incumbent；
该 incumbent 及其覆盖量可能因机器而异，不受此保证约束。随机算法必须显式提供
算法种子，确定性算法会拒绝算法种子。

<!-- faq:id=reproduction -->

## 如何复现实验流程？

按[核心实验命令](cli.md#core-overlap-pilot)重建完整输出，再运行验证器与离线
分析。完整的 [`CLI 参考`](cli.md)介绍配置检查、benchmark、恢复、summarize
和回放；[`output_schema.md`](output_schema.md)解释产物及验证范围。
