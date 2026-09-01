# 常见问题

<!-- faq:id=problem-definition -->

## 什么是最大覆盖问题？

给定一个有限的元素全集、一组候选集合以及选择预算 `k`，最大覆盖问题要求
至多选择 `k` 个集合，使它们的并集覆盖尽可能多的元素。在本仓库中，
`universe_size`、`set_count` 和 `k` 描述实例；coverage 表示所选集合并集中的
不同元素数量。

<!-- faq:id=why-study -->

## 为什么研究最大覆盖问题？

最大覆盖是一个具有经典贪心基线的单调子模优化问题。本项目关注的是：在同一
实例上，将贪心算法与精确参考进行比较时，受控的结构变化与观测到的差距之间有
什么关系。这个问题研究的是实例结构和算法行为，而不是替代理论上的经典保证。

<!-- faq:id=theoretical-bound -->

## 为什么不只使用理论保证？

经典贪心保证描述的是一大类目标函数中，贪心值与最优值之间的最坏情况关系。它
不会告诉我们，在一次具体实验中，哪些实例结构与较大或较小的差距相关。理论保
证和经验性的结构分析回答的是不同问题。

<!-- faq:id=algorithm-roles -->

## 为什么需要这么多算法？

每个算法承担不同的角色：

- **Greedy** 是主要基线，也是研究对象。
- **Lazy Greedy** 是一种确定性实现，目标是在保留仓库规定的贪心选取顺序的同
  时减少边际增益评估次数。这不是普遍适用的运行时间结论。
- **Randomised Greedy** 和 **Multi-start Local Search** 提供显式设定种子的随机
  方案，用于检验不同的早期选择或增加搜索起点是否会改变结果。
- **Local Search** 用于检验邻域改进能否弥补一次性贪心选择造成的损失。
- **Brute Force**、**Branch-and-Bound** 和 **CP-SAT** 是候选精确方法。只有以
  `optimal` 状态结束的运行才能提供最优值参考；超时可能有 incumbent，但不能
  证明最优。CP-SAT 还需要可选的 OR-Tools 依赖。

<!-- faq:id=reference-status -->

## 什么才算有效的精确参考？

只有闭合界限并返回 `optimal` 的精确运行，才能提供供最优值相关指标使用的参考
最优值。`feasible` 表示已经得到可行 incumbent，但没有最优性证明。`timeout` 表示
达到配置的时间限制；`error` 表示没有产生有效算法结果。产物级状态规则见
[`output_schema.md`](output_schema.md)。

<!-- faq:id=instance-families -->

## 当前包含哪些实例族？

生成器注册表包括 `uniform`、`high_overlap`、`clustered`、`fixed_size`、
`long_tail`、`duplicate_heavy`、`dominated_heavy`、`mixed_cluster` 和
`adversarial`。它们用于施加不同的结构压力。重复密集和支配密集实例也用于
测试预处理及精确搜索行为；没有任何实例族保证每个生成实例都会导致 Greedy
失败。可运行的实例族工作流见 [`failure_mechanisms.md`](failure_mechanisms.md)。

注册表还包括 `controlled_high_overlap`、`controlled_clustered`、
`controlled_duplicate`、`controlled_dominated` 和
`controlled_adversarial`。这些新名称保留所有旧生成器的身份，同时提供固定维度、
固定 incidence 的结构压力扫描。

<!-- faq:id=synthetic-families -->

## 为什么使用参数化实例族，而不使用真实世界数据？

真实世界数据可能同时沿多个维度变化，因此很难隔离某一个结构属性的作用。受控
合成实例族可以改变指定参数，并在配置支持时固定共同的随机流。这样有助于检验
候选机制并估计描述性关联；但它本身不能建立因果关系，也不能证明对真实世界的
泛化能力。

<!-- faq:id=no-results -->

## 为什么仓库中没有冻结的实验结果？

本仓库是一个以代码为中心的可复现实验引擎。它发布算法、生成器、配置、验证器
和报告逻辑，而基准测试产物会在本地写入 `results/`。任何公开的定量陈述都需要
独立的冻结证据链，其中包括输入、确切 commit、环境元数据、分析过程和独立验证。
当前快照有意不包含这套研究结果包。

<!-- faq:id=content-boundary -->

## 为什么要强制执行内容边界？

本仓库发布可运行代码，但不发布定量研究结论。内容边界可以避免把文字中的数字、
结果表或保存的输出语料与验证它们所需的证据分离开来。这个强制规则确保本仓库是
用于产生证据的工具，而不是冻结且经过独立验证的研究的替代品。

<!-- faq:id=determinism -->

## 这里的确定性是什么意思？

在规范化配置、算法版本和显式种子相同的情况下，已完成的运行会复现实例身份、
选中的集合索引、覆盖值以及规范行排序。实际运行时间、时间戳和环境元数据可能
因机器而异。被墙钟限制中止的运行报告其在限制触发时已达成的 incumbent；由于
进度按墙钟检查，该 incumbent 及其覆盖率可能因机器而异，不受此保证约束。因此，
随机算法必须显式提供算法种子，而确定性算法会拒绝算法种子。

<!-- faq:id=reproduction -->

## 如何复现实验流程？

先阅读 [`cli.md`](cli.md)，其中介绍配置校验、benchmark 执行、恢复、汇总、回放
以及独立产物验证。使用 [`output_schema.md`](output_schema.md) 理解生成的 CSV、
报告、回放文件和 manifest。README 与 [`CONTRIBUTING.md`](../CONTRIBUTING.md)
定义当前的发布范围。
