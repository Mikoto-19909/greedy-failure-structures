# R4：13,000 条预算记录中仅一条上界因前缀项收紧

按 [F4 设计](r4_f4_design.zh-CN.md)完成了全部 **1,800 张原图、13,000 条预算记录**的
生产、原图/证书/穷举参考独立验证及 65 个参数单元的汇总核对。没有缺失、替换或缩减样本。
所有记录满足 `G≤O≤U≤U_initial≤B`，但只有 **1 条记录、1 张原图**的 U 严格小于
初始简单上界，收紧量为 1。初始界与前缀界认证的最优实例逐项一致，新增认证数为 0。

这完成了整数前缀基线的小实例校准。在本批固定语料中，前缀项的额外紧度收益有限；
本轮不据此启动大实例、L5 DUAL 或 LP 研究。

## 方法与数据范围

输入来自 R2 [固定证据提交 `4a419f3`](https://github.com/Mikoto-19909/greedy-failure-structures/tree/4a419f338d70068fa988fa97027734cdcda0a036)，
采用 N=M=12/16/20、d=2/3/4 的定长模型，每单元 200 原图，跨预算复用原图。
完整种子、预算和统计决定见 [F4 配置](r4_f4_config.json)。18 张预检图未并入正式校准。
源数据按冻结种子核对；标准 Greedy 固定低索引平局裁决，零增益仍填满预算。

`B=|⋃ᵢSᵢ|`，`U_initial=min(B,kΔ_0)`，
`U=min(B,min_{t=0,…,k}[f(P_t)+kΔ_t])`。独立验证器用显式集合运算重建路径、
全部前缀及最大边际见证，并逐预算枚举 O 和字典序最小的恰好 k 个不同索引见证。
输入/身份/I/O 基础设施共享，关键路径、上界和汇总计算不调用生产实现。

这是已见 R2 资料上的回顾性校准，不是新样本确认。结果按冻结 `(N,d,k)` 单元给出
均值、中位数和 nearest-rank P90；没有新增检验、区间或 bootstrap。
下文跨单元的数量只描述预算记录，不能把 13,000 条记录当成独立原图数或总体概率估计。

全部数值见 [逐预算表](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_calibration_v1/budget_results.csv)、
[65 单元汇总](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_calibration_v1/cell_summary.csv)及
[报告数值摘录](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_calibration_v1/report_facts.json)。原始输入、证书与见证保存在
[原图检查点](https://github.com/Mikoto-19909/greedy-failure-structures/tree/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_calibration_v1/graphs/)。所有参考均完成，没有零分母或比例缺失。

## 收紧、认证与未决实例

- `k=1`、`k=M` 共 3,600 条平凡端点记录，全部真实最优且获认证，两种上界均无收紧差异。
- 其余 9,400 条中间预算记录中，真实最优 7,298 条，Greedy 失效 2,102 条；
  初始界与前缀界均认证最优 6,755 条。另有 543 条虽然真实最优，却未被该基线认证。
- 全部预算共认证最优 10,355 条。`U=G` 当且仅当 `U_initial=G` 是已有数学限制，
  本次逐行结果与之吻合；这项一致性不是“发现两种方法统计等价”的新实验结论。

唯一收紧例是
[`N=12,d=3,r0150,k=4`](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_calibration_v1/graphs/r2-exploration-n12-d3-r0150.json)：
`G=9`、`O=11`、`U_initial=12`、`U=11`。首选集合 `S0={1,3,7}` 与每个剩余候选
都有交集，所以 `P_1` 后的最大边际为 2，`U_1=3+4×2=11`。
从空前缀到终点的候选界依次为 12、11、13、15、17；取最小后得到 11。
保存的最优见证 `[1,8,9,10]` 的并集覆盖也是 11。

此例的近似比下界由 `9/12=0.75` 提高到 `9/11≈0.81818`，相对最优性差距上界
由 0.25 降至约 0.18182，且 U 恰好达到独立重算的 O。它仍是 Greedy 失效实例，
并没有新增最优认证。该具体轨迹是全量校准后的描述性选例，不扩大其代表性。

65 个单元中只有 `(12,3,4)` 出现收紧：200 条记录的平均收紧量为 0.005，
中位数和 P90 都为 0；其余 64 个单元的收紧量全部为 0。
按观测均值描述，最松单元为 `(20,4,5)`：`mean(U/O)=1.09548`，
U/O 的中位数和 P90 均为 1.11111；`mean(G/U)=0.86439`，而 `mean(G/O)=0.94642`。
这些是指定单元的描述，不是事后峰值检验，也不能把质量下界当成实际近似比。

`U>G` 本身不能证明失效；上述失效数量来自已完成的独立精确参考。
同理，543 条未获认证的真实最优记录不构成无效证书，它们反映上界不够紧。

## 实际成本与资源

四个正式阶段的入口内部墙钟分别为：生产 **204.900 秒**、独立验证 **348.489 秒**、
汇总前重查及汇总 **146.626 秒**、派生验证 **0.710 秒**，合计 **700.725 秒**
（约 11.68 分钟）。[执行记录](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_calibration_v1/execution.jsonl)还单独记录报告计算
及独立审阅计算；含 F4 预检的 4.828874 秒在内，累计 **706.656 秒（11.78 分钟）**，
未触发 1 小时停止条件。
外层命令含启动的四阶段墙钟合计约 702.180 秒，见
[命令运行记录](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_command_runs.jsonl)；它是另一计时口径，不与内部墙钟相加。

计算分量分别保留，避免把小实例的指数枚举成本归给证书方法：

- 生产阶段内，路径和上界计算累计 **0.172977 秒**，公共 Greedy 重算 **0.692025 秒**，
  来源读取与关联检查 **16.250223 秒**。
- 独立证书检查 **0.499813 秒**，穷举 O/规范见证重算 **143.834272 秒**。
- 汇总前再次检查当前数据：证书检查 **0.504529 秒**，穷举参考重算 **143.798765 秒**；
  汇总写表 **0.146578 秒**。

两次穷举参考重算合计约 287.633 秒；四阶段墙钟扣除这部分后仍约 **413.091 秒**。
后者还包含来源核对、Greedy、检查点/JSON 读写、资源检查及汇总，不能称为纯证书计算时间。
生产与独立验证的阶段耗时明显大于计算分量，反映当前离线流程的实际开销。
仅用 0.173 秒宣称整个证书流程很快，会遗漏这些开销。

实际观测到的研究进程峰值约 **94.02 MiB**，出现在派生验证阶段；
高于 F4 预检的 **60.51 MiB** 余量估计，但低于冻结的 6 GiB 上限。
正式批次约 **28.72 MiB**，低于 2 GiB 输出上限。小预检批次低估了全量输入及派生表
加载的内存，保留原估计并如实报告差异，不把估计修写成保证。
峰值记录见 [原图验证进程](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_verification_process.json)、
[汇总进程](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_analysis_process.json)和
[派生验证进程](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_derived_process.json)；生产阶段使用原图记录中的进程峰值。
首次外层测量的 venv 启动器内存不作为研究进程内存，说明见运行环境。
以上均为当前机器、当前数据和单次执行的记录，不外推为大实例性能保证。

## 验证、复现与停止结论

[原图独立验证](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_calibration_v1/verification.json)覆盖全部 1,800 图和 13,000 个预算；
[派生验证](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_calibration_v1/summary_verification.json)覆盖全部逐行指标及 65 个单元。
汇总入口在写表前再次复核当前读取的同一批数据。没有修改冻结配置、替换原图、
跳过缺失参考或因观察结果更换方法。

执行源码为 `cef5b92` 加 F4 已验证的 R4 离线实现，
[源码快照](https://github.com/Mikoto-19909/greedy-failure-structures/tree/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_source_v1/analysis/)与实际运行文件一致；
Python 3.12.14、NumPy 2.3.5、SciPy 1.18.1，完整信息见
[运行环境](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_calibration_v1/run_context.json)。
按 [使用说明](r4_usage.zh-CN.md)的 analyze 与派生验证命令，可从保存数据重建并核对汇总。
报告解释保留在此文档，数量和具体单元值可从所链接 CSV 重算。

F4 前默认检查 428 项通过、1 项可选 OR-Tools 跳过；完整检查 488 项通过、1 项同类跳过，
38 个公共源码文件类型检查通过；最后局部修正通过 9 项专项测试，日志见 F4 设计。
本轮没有改动分析源码或检查配置，因此未重复整套测试。
独立代理另从原图和 CSV 核对数量、唯一收紧轨迹、计时及解释边界，未再次全量枚举 O；
代理复核不等于外部同行评议。

首轮校准已完成。公式与实现有效，初始简单界已承担几乎全部紧度和最优认证作用，
前缀项的新增收紧不足以单独构成本批之后扩规模的理由。
当前结束于这一基线结果；任何大实例或更紧方法都需要新的具体问题和独立设计。
## 已发布证据

2026-09-08，所选证据已发布到受保护的 `codex/evidence/r4-calibration-v1` 分支，
不可变提交 [1a8b1899d927cba202cf7931fe992ecd2b5a1807](https://github.com/Mikoto-19909/greedy-failure-structures/tree/1a8b1899d927cba202cf7931fe992ecd2b5a1807)
已通过远端提交和完整文件树回读。共 3,746 个选定证据文件，约 56.32 MiB，另附 FREEZE.md。
快照包含 F4 配置、预检、全部原图/证书、逐预算表、汇总、运行记录、R2 来源输入及
[完整源码归档](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_publication_source.zip)。
归档源码提交为 `f435286598ca8582164e620fa80331256a254bd0`；三个 R4 计算文件
与实际执行时保存的源码副本逐字节一致。

发布前在正式数据副本上重新独立核验全部 1,800 图，并通过 13,000 行/65 单元的派生核对。
原批次文件和计时未改写；追加重算耗时 468.609 秒、派生核对 0.809 秒，连同历史研究
累计约 1,176.074 秒，仍在 F4 的 3,600 秒限制内。
[本次验证记录](https://github.com/Mikoto-19909/greedy-failure-structures/tree/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_publication_verification_v1)与历史记录分别保留。
[发布前完整检查](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_publication_full_check.log)执行 489 项，
488 项通过、1 项可选 OR-Tools 跳过，38 个源码文件类型检查通过。
以上追加工作用于核验既有证据，未启动新样本或更紧上界实验。
