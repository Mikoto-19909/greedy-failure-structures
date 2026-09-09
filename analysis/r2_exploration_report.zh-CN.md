# R2：中间预算区域更常见 Greedy 失效

完整定长模型网格的 1,800 张原图、13,000 条预算记录及预定的 288 张机制诊断
均已完成独立验证。九个 `(N,d)` 单元的观测失效率都在中间预算达到较高水平，
较大预算下降；这描述有限网格中的经验区域，不证明极限相变或单一结构因果效应。

## 方法与数据

[F2 设计](r2_exploration_design.zh-CN.md)在正式输入生成前固定了模型、网格、种子、
见证规则、诊断子集及统计方法。[F2 配置](https://github.com/Mikoto-19909/greedy-failure-structures/blob/4a419f338d70068fa988fa97027734cdcda0a036/analysis/r2_f2_config.json)列出全部种子与预算。
采用 `M=N∈{12,16,20}`、`d∈{2,3,4}`，每单元 200 张独立原图；每个集合独立均匀
无放回抽取 d 个元素，集合之间允许重复，不使用生成器耦合种子。
每张图跨预算复用，Greedy 固定低索引平局裁决，穷举参考保存字典序最小的恰好 k 个索引见证。

原始图、每预算结果与完整诊断位于 [graphs](https://github.com/Mikoto-19909/greedy-failure-structures/tree/4a419f338d70068fa988fa97027734cdcda0a036/results/r2_grid_v1/graphs)，
逐预算数据见 [budget_results.csv](https://github.com/Mikoto-19909/greedy-failure-structures/blob/4a419f338d70068fa988fa97027734cdcda0a036/results/r2_grid_v1/budget_results.csv)，
65 个参数单元的估计和区间见 [cell_summary.csv](https://github.com/Mikoto-19909/greedy-failure-structures/blob/4a419f338d70068fa988fa97027734cdcda0a036/results/r2_grid_v1/cell_summary.csv)。
原图是独立抽样单位，不把 13,000 条预算记录当作 13,000 个独立样本。

失效率区间为逐点 95% Clopper–Pearson；比值与差距的区间为 10,000 次原图整体重采样
的百分位 bootstrap 逐点区间，全部预算共享每次抽样。它们不是同时置信带，未作事后挑峰检验。
`sum(G)/sum(O)`、`mean(G/O)` 与失效率分别回答不同问题；平均相对最优性差距包括最优实例的零值。

## 预算区域

下列行使用预定诊断预算 `k=ceil(N/d)`，每行分母均为 200，区间和差距单位为百分比。

| N | d | k | 失败数 | 失效率及逐点 95% 区间 | 平均相对最优性差距 |
| --- | --- | --- | --- | --- | --- |
| 12 | 2 | 6 | 91 | 45.50 [38.46, 52.67] | 4.593 |
| 12 | 3 | 4 | 98 | 49.00 [41.88, 56.15] | 4.903 |
| 12 | 4 | 3 | 113 | 56.50 [49.33, 63.48] | 5.905 |
| 16 | 2 | 8 | 97 | 48.50 [41.39, 55.65] | 4.047 |
| 16 | 3 | 6 | 125 | 62.50 [55.39, 69.23] | 5.025 |
| 16 | 4 | 4 | 124 | 62.00 [54.89, 68.75] | 5.392 |
| 20 | 2 | 10 | 96 | 48.00 [40.90, 55.16] | 3.510 |
| 20 | 3 | 7 | 144 | 72.00 [65.23, 78.10] | 5.443 |
| 20 | 4 | 5 | 144 | 72.00 [65.23, 78.10] | 5.358 |

![R2 预算曲线](https://raw.githubusercontent.com/Mikoto-19909/greedy-failure-structures/4a419f338d70068fa988fa97027734cdcda0a036/results/r2_grid_v1/budget_curves.svg)

作为探索性描述，各单元观测最高失效率的位置处于实际 λ=kd/N 的 0.8–1.125 区间。
这不是预先指定的峰值检验，也不表示区间外均容易。所有 k=1 与 k=M 的端点均达到最优，
与端点的数学性质一致。较高失效率与平均损失不同：例如 N=20,d=3,k=7 的失效率为 72%，
平均相对最优性差距约 5.44%；不能把“失败”解释成总是严重损失。

## 机制与可检验线索

[机制汇总](https://github.com/Mikoto-19909/greedy-failure-structures/blob/4a419f338d70068fa988fa97027734cdcda0a036/results/r2_grid_v1/mechanism_summary.csv)覆盖每单元预定前 32 张原图，
共 288 张；其中 164 张失败，全部在首次失效步存在仍可保留最优的替代平局候选。
其中 80 张首次失效在首步。定长模型首步所有集合平局，而任一最优解内的首选集合都能
保留最优可达性，所以首步的平局可避免是定义与模型共同保证的性质，不能独立充当新的结构证据。
这也不保证改选一次后继续 Greedy 就能到达最优。

一换一修复 64 个原失败实例，包含一换一的至多二换二累计修复 126 个；
本次预定诊断中没有二换二预算耗尽，仍未修复的实例保留在汇总中。
这些机制数字只对应固定 288 张诊断原图，不代表全部 1,800 张原图的机制组成。

用于提出 R3 问题的探索选例是 [n12/d3/r0001](https://github.com/Mikoto-19909/greedy-failure-structures/blob/4a419f338d70068fa988fa97027734cdcda0a036/results/r2_grid_v1/graphs/r2-exploration-n12-d3-r0001.json)。
其 G=10、O=12，强制保留首选集合 0 后最佳覆盖仅为 10。
定义首选集合的局部交集总量 `E0=Σ_{j>0}|S0∩Sj|=Σ_{a∈S0}(r_a−1)`。
集合 0 的值为 8，可保留最优的候选 7、9、10 分别为 7、6、3；
但值为 5 的候选 1 不能保留最优，而值为 8 的候选 6 可以。因此该量不是单调判别器。
它提供“首选集合连接到哪些频数的元素可能影响后续选择”的具体线索，尚无效应方向结论。

据此完成了独立的 [R3 可行性探测](r3_probe_design.zh-CN.md)，并交付
[F3 确认设计](r3_confirmation_design.zh-CN.md)；后续已独立完成[R3 正式确认](r3_confirmation_report.zh-CN.md)。

## 验证、资源与局限

[原图验证](https://github.com/Mikoto-19909/greedy-failure-structures/blob/4a419f338d70068fa988fa97027734cdcda0a036/results/r2_grid_v1/verification.json)重算所有预定 O、规范见证、Greedy、
结构和完整诊断；[汇总验证](https://github.com/Mikoto-19909/greedy-failure-structures/blob/4a419f338d70068fa988fa97027734cdcda0a036/results/r2_grid_v1/summary_verification.json)复算
65 个预算单元、13,000 条预算数据及 9 个机制单元。验证器不调用生产穷举或统计函数。
独立代理另外执行了 4,096 个小系统的全预算比对、恢复运行和损坏输入检查。
代理复核不等于外部同行评议。

完整检查 `python scripts/check.py --profile full` 共运行 441 项测试，440 项通过，
1 项因未安装可选 OR-Tools 而跳过；38 个公共源码文件的类型检查通过。
R2/R3 探测的必需验证均实际执行，没有跳过。日志见[完整检查](https://github.com/Mikoto-19909/greedy-failure-structures/blob/4a419f338d70068fa988fa97027734cdcda0a036/results/r2_r3_full_check.log)。

预检、正式生产、独立验证与汇总计算累计墙钟约 237.56 秒，远低于 12 小时上限。
正式生产约 80.29 秒，原图独立验证约 116.49 秒；这些是该机器和该实现的执行记录，
不是可推广的速度保证。详见 [执行记录](https://github.com/Mikoto-19909/greedy-failure-structures/blob/4a419f338d70068fa988fa97027734cdcda0a036/results/r2_grid_v1/execution.jsonl)和
[环境](https://github.com/Mikoto-19909/greedy-failure-structures/blob/4a419f338d70068fa988fa97027734cdcda0a036/results/r2_execution_context.json)。正式批次文件约 19 MiB，所选证据已发布至受保护证据分支。

R2 原执行采用 `b746124` 加当时未提交的新增实现；[原执行离线源码副本](https://github.com/Mikoto-19909/greedy-failure-structures/tree/4a419f338d70068fa988fa97027734cdcda0a036/results/r2_source_v1)
保存用于复现的离线脚本，公共算法沿用该基线。命令见[使用说明](r2_usage.zh-CN.md)。
汇总使用已保存数据，并在写表前重新独立验证当前读入的原图及轨迹；汇总验证本身只证明派生一致性。
只读审计未发现本批数值错误；汇总入口已修正为不依赖历史 `passed` 状态放行变化后的输入。
该额外审计全量核对输入、Greedy 与汇总，对最优值和机制轨迹作分层抽查，不是第二次全量穷举认证。
汇总修复及 R3 正式入口的后续完整检查共 447 项，446 项通过、1 项可选 OR-Tools 跳过，
见[后续检查日志](https://github.com/Mikoto-19909/greedy-failure-structures/blob/4a419f338d70068fa988fa97027734cdcda0a036/results/r3_confirmation_full_check.log)。修复验证仅使用临时样例，原始 R2 数据保留。
范围限制为独立定长模型、有限规模、固定标签和平局裁决，不外推到共核式 pilot、
其他生成机制或无限规模。R3 只能确认冻结协议的效果，不能单独识别一个结构量的因果作用。

## 已发布证据

所选证据已发布到受保护的 `codex/evidence/r2-grid-v1` 分支，
[不可变提交 `4a419f338d70068fa988fa97027734cdcda0a036`](https://github.com/Mikoto-19909/greedy-failure-structures/tree/4a419f338d70068fa988fa97027734cdcda0a036)
已通过远端提交及完整文件树回读核对。配置、原始输入、轨迹和验证记录均可从该快照获取。
