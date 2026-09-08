# F4：固定 R2 语料上的整数前缀上界校准

状态：2026-09-07，18 张独立预检原图完成后、全量 R4 证书生成前定版。
正式设计为 [F4 配置](r4_f4_config.json)。**正式校准已完成**，见 [研究报告](r4_calibration_report.zh-CN.md)。
本页保留 F4 定版内容与预检记录；不自动进入大实例研究。
数学定义与最优认证能力限制见 [准备方案](../docs/r4_preparation_plan.zh-CN.md)，
可运行命令见 [使用说明](r4_usage.zh-CN.md)。

## 固定输入、计算与报告

完整使用 R2 [证据提交 `4a419f3`](https://github.com/Mikoto-19909/greedy-failure-structures/tree/4a419f338d70068fa988fa97027734cdcda0a036)
的正式语料：N=M=12/16/20、d=2/3/4，各 200 张原图，共 1,800 张、13,000 条预算记录。
各图种子、索引顺序与预算逐项列于配置；不新增生成种子、不筛除失败或证书较松的图。
来源读取按原冻结种子重算有序集合，仅作比对，不保存替代输入。
这属于已见 R2 资料上的回顾性校准，不是独立新样本确认；不混入 R3 变体或预检图。

每图共用一条低索引平局裁决的 Greedy 路径；每预算取 `t=0,…,k` 的全部前缀，
计算 `U=min(B, min_t[f(P_t)+kΔ_t])`，并与 `U_initial=min(B,kΔ_0)` 比较。
最大边际见证取最小索引，无候选记空；终点若有剩余候选仍计算最大边际。
O 与最优见证由独立验证器逐预算枚举：恰好 k 个升序不同索引，多个最优解取字典序最小者。

已知 `U=G` 当且仅当 `U_initial=G`，认证数量只作描述与正确性核对；
前缀方法的额外价值用收紧量和 `G/U` 改善衡量，不把新增认证实例作为目标。
零并集允许认证最优，但所有零分母比例写空并明确计数。

逐行保存 G、O、U、初始界、认证状态、平凡端点标志及收紧量；按 `(N,d,k)` 汇总
`U_initial−U`、`U/O`、`(U−O)/O`、`G/O`、`G/U`、`1−G/U`。
每项给出算术均值、中位数和 nearest-rank P90（升序第 `ceil(0.9n)` 个非缺失值），
另列缺失数量；偶数中位数取中间两项均值。单列 `k=1` 与 `k=M`。
不作显著性检验、置信区间或 bootstrap，不新增随机统计种子；同图预算不是独立样本。

## 预检结果与资源决定

预检采用 R2 独立预检语料每单元重复号 0、1，共 18 原图、130 预算记录、65 个汇总单元。
生产、独立证书/穷举参考检查、汇总前当前输入重查及派生验证均完成。
定版入口再次复核当前预检记录及派生表，未根据紧度或认证结果选择方法。

预检各入口内部累计墙钟 **4.8288738 秒**，包含定版时的额外复核。
最近一次独立核对的证书检查约 0.004962 秒、穷举参考重算约 1.459431 秒；
汇总前重查分别约 0.004708 秒和 1.392010 秒，两类成本分别保存。
这些是当前机器的单次预检记录；模块导入等入口外启动时间不在该墙钟内，另有余量。

逐单元最慢原图的生产与两次独立复核成本外推约 316.924020 秒；
按完整预检内部墙钟的每图成本外推约 482.887380 秒。取较大者乘 2，
再加已用预检时间及 600 秒汇总/I/O/启动余量，保守总估计为
**1,570.603634 秒（26.18 分钟）**。输出余量估计 71,538,816 字节（68.22 MiB），
峰值内存余量估计 63,447,040 字节（60.51 MiB）；具体逐单元值存于配置。

据此固定 **单进程、累计 1 小时、总内存 6 GiB、输出 2 GiB**，完整语料不缩减。
未测多进程加速，因此没有按进程数折算。预检耗时计入正式批次的累计时间限制。
输出估计为逐单元最大检查点大小外推的 2 倍再加 16 MiB 派生文件余量；
峰值内存估计为预检观测最大值的 2 倍。估计只支持本批资源决策，不是容量保证。

计时分量为来源读取、标准 Greedy、证书生产（含离线路径重建）、证书独立检查、
穷举参考重算、汇总及派生核对。全部计入首轮预算；扩规模判断另看不含穷举参考的
证书生产与检查成本。批次墙钟与各计算分量分别保存，不相加后重复计算总耗时。

## 完成、停止及复现

生产按原图保存检查点，恢复运行验证已完成图的来源与证书后只补未生产的图。
独立验证每次重新检查当前批次的全部证书与 O/规范见证；汇总写入前也重查当前数据。
缺失参考、错误来源、非规范见证、缺图/预算或无效界均拒绝完整认证，保留输入供修复。
时间在任务边界及最后完成状态写出前检查；内存与输出限制同样在完成前核对。
不因超时删图、补抽、改预算或换方法。实质修订另存设计并说明原因，原 F4 不覆盖。
完成固定校准、独立验证和可重建报告即停止，再判断是否有明确扩规模需要。

预检产物为 [原图与证书](https://github.com/Mikoto-19909/greedy-failure-structures/tree/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_preflight_v1/graphs/)、
[独立验证](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_preflight_v1/verification.json)、
[派生核对](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_preflight_v1/summary_verification.json)、
[分阶段墙钟](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_preflight_v1/execution.jsonl)及
[汇总重查计时](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_preflight_v1/analysis_timing.json)。这些产物已随 R4 证据快照发布，远端回读信息见研究报告。
执行基线 `cef5b92` 加新增 R4 离线实现，副本保存在 [执行源码快照](https://github.com/Mikoto-19909/greedy-failure-structures/tree/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_source_v1/analysis/)；
环境 Python 3.12.14、NumPy 2.3.5、SciPy 1.18.1，详见 [运行环境](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_preflight_v1/run_context.json)。

新增三个分析文件均登记到 `r4`，入口有效/无效输入和恢复运行已实际验证。
默认检查 429 项、完整检查 489 项，均只有 1 项可选 OR-Tools 跳过，
38 个公共源码文件类型检查通过；最后的局部修正另通过 9 项 R4 专项测试。
日志为 [默认检查](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_default_check.log)、[完整检查](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_full_check.log)和
[专项检查](https://github.com/Mikoto-19909/greedy-failure-structures/blob/1a8b1899d927cba202cf7931fe992ecd2b5a1807/results/r4_focused_check.log)。另一代理已实际执行有效/无效案例、来源替换拒绝、
恢复和末尾越限检查，并核对 F4 的资源算术；这不等同于外部同行评议。
