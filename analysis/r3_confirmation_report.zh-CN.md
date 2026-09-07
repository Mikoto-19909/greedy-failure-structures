# R3：两种局部交集总量导向的保度协议产生首步不可恢复率差异

预定的 3,000 张独立新原图及 12,000 个端点全部完成。
E0 非减协议的首步不可恢复事件为 4,165/6,000，非增协议为 76/6,000；
以原图内两链平均后计算的主差值为 **68.15 个百分点**，预定保守 95% 区间为
**[63.19, 73.11] 个百分点**，方向为正。区间半宽 4.959 个百分点，达到 F3 的精度目标。

结论只针对独立定长模型和这两种有限步构造协议，不将差值解释为 E0 的单独因果效应。

## 设计与原始输入

[F3 设计](r3_confirmation_design.zh-CN.md)和[确认配置](r3_confirmation_config.json)在正式样本生成前固定：
N=M=12、d=3、k=4，允许重复候选集合，保持元素标签与集合索引；标准 Greedy 的首步恒选索引 0。
每原图两方向各两条链，每链 2048 次提议，合法且满足 E0 方向时接受，等分交换允许。
构造只读取结构，不读取 Greedy、O 或 O1 来决定接受；所有拒绝提议也计入链长。

`E0=Σ_{j>0}|S0∩Sj|=Σ_{a∈S0}(r_a−1)`。每个集合大小和每个元素频数逐项保持不变，
但其他连接性质和每个变体的最优值仍可能变化。每个端点都分别求自己的 O 与强制包含索引 0 的 O1，
保存恰好 k 个升序不同索引的字典序最小见证。`1[O1<O]` 是首步不可恢复指标，不是整体失效率。

完整原图、链、交换记录、端点和见证见 [graphs](https://github.com/Mikoto-19909/greedy-failure-structures/tree/8663e0dcf576ab156535ff7403bb7e4715091357/results/r3_confirmation_v1/graphs)。
[端点表](https://github.com/Mikoto-19909/greedy-failure-structures/blob/8663e0dcf576ab156535ff7403bb7e4715091357/results/r3_confirmation_v1/endpoint_results.csv)保留全部 12,000 个端点，
[原图级表](https://github.com/Mikoto-19909/greedy-failure-structures/blob/8663e0dcf576ab156535ff7403bb7e4715091357/results/r3_confirmation_v1/base_graph_summary.csv)有 3,000 行，
[主汇总](https://github.com/Mikoto-19909/greedy-failure-structures/blob/8663e0dcf576ab156535ff7403bb7e4715091357/results/r3_confirmation_v1/primary_summary.json)保存未舍入估计及区间。
15,000 个原图/链种子互不重复，且与 R2、R3 探测和历史输入分离，见[执行前核对](https://github.com/Mikoto-19909/greedy-failure-structures/blob/8663e0dcf576ab156535ff7403bb7e4715091357/results/r3_confirmation_readiness.json)。
配置中的 `execution_status: not_run` 是 F3 定版时的历史字段；实际执行状态见结果目录，不回写科学配置。

## 原图级推断与结果

每张原图先计算 `D_i=(Y_i,1^+ + Y_i,2^+)/2 − (Y_i,1^- + Y_i,2^-)/2`，主估计量为 `mean(D_i)`。
两链和两方向都属于同一个原图，独立样本数为 3,000，不能按 12,000 个端点计算区间。
依 F3 的 Hoeffding 方案，`D_i∈[-1,1]`，双侧 95% 半宽为
`sqrt(2log(40)/3000)=0.0495908557`。未切换检验、调整样本量或依据方向提前停止。

| 描述量 | E0 非增协议 | E0 非减协议 |
| --- | --- | --- |
| 端点数 | 6,000 | 6,000 |
| 首步不可恢复数 | 76 | 4,165 |
| 首步不可恢复率 | 1.2667% | 69.4167% |
| 最终 Greedy 失效数 | 2,139 | 4,569 |
| 最终 Greedy 失效率 | 35.65% | 76.15% |
| 平均相对最优性差距 | 3.3448% | 8.0965% |
| 平均 E0 | 2.5300 | 11.5935 |

表中的单侧比例是描述性汇总，不把每侧 6,000 个端点视为独立二项样本。
唯一正式方向判断来自原图级主差值及其预定区间。
非增协议仍有较多后续 Greedy 失效，因此“首步仍可达到最优”不保证继续 Greedy 就会最优。

原图级差值分布为：D=-1 有 1 张，D=-0.5 有 5 张，D=0 有 353 张，
D=0.5 有 1,186 张，D=1 有 1,455 张。6 张原图的差值方向相反，
说明总体方向不是逐图单调定理。3,000 张原图均出现两方向平均 E0 分离；
未根据分离程度筛样，也不能保证其他样本或度序列一定可操纵。

## 验证与执行

执行源码提交为 `85e6535ecdc319b72439422f8f5fb01dfb10f3c3`。
环境为 Python 3.12.14、NumPy 2.3.5、SciPy 1.18.1，详见[运行环境](https://github.com/Mikoto-19909/greedy-failure-structures/blob/8663e0dcf576ab156535ff7403bb7e4715091357/results/r3_confirmation_v1/run_context.json)。
正式生产约 33.91 秒，原图/交换/最优参考独立验证约 33.38 秒，汇总前当前数据复核约 32.33 秒，
派生表独立核对约 0.17 秒，累计约 **99.79 秒**，在 F3 的 1 小时计算预算内。
这是当前机器的执行记录，不是通用性能保证；实际记录见[执行日志](https://github.com/Mikoto-19909/greedy-failure-structures/blob/8663e0dcf576ab156535ff7403bb7e4715091357/results/r3_confirmation_v1/execution.jsonl)。

[原图验证](https://github.com/Mikoto-19909/greedy-failure-structures/blob/8663e0dcf576ab156535ff7403bb7e4715091357/results/r3_confirmation_v1/verification.json)重放所有提议、接受决定、度序列，
并独立枚举每个原图/端点的 O/O1 和规范见证；[派生验证](https://github.com/Mikoto-19909/greedy-failure-structures/blob/8663e0dcf576ab156535ff7403bb7e4715091357/results/r3_confirmation_v1/summary_verification.json)
复算两张表和主汇总。汇总入口还在写表前对本次读入的同一批记录重新执行原图验证，
历史 `passed` 不能替代当前输入的验证。未修改已验证的 R2 原始数据。

正式运行前使用独立 fixture 种子完成有效/无效输入与 Windows 多进程恢复检查，未提前生成正式样本。
完整检查共 447 项，446 项通过、1 项因缺少可选 OR-Tools 跳过，38 个公共源码文件类型检查通过；
见[检查日志](https://github.com/Mikoto-19909/greedy-failure-structures/blob/4a419f338d70068fa988fa97027734cdcda0a036/results/r3_confirmation_full_check.log)。独立复核者为代理，实际核对损坏输入、
原图推断单位、区间和恢复行为；不等同于外部同行评议。
复现命令见[使用说明](r3_confirmation_usage.zh-CN.md)。

## 解释范围

本实验确认的是已冻结的两种协议在指定有限模型中的首步不可恢复率差异。
保度交换仍会改变多个连接性质；E0 也与固定索引 0 有关，不能外推成与标签无关的普适结构定律。
有限提议次数不保证均匀采样、充分混合或 E0 全局极值。全部证据与预定样本保留，
不以当前结果自动推进 R4 或其他算法研究。

## 已发布证据

所选证据已发布到受保护的 `codex/evidence/r3-first-step-confirm-v1` 分支，
[不可变提交 `8663e0dcf576ab156535ff7403bb7e4715091357`](https://github.com/Mikoto-19909/greedy-failure-structures/tree/8663e0dcf576ab156535ff7403bb7e4715091357)
已通过远端提交及完整文件树回读核对。配置、原始输入、轨迹和验证记录均可从该快照获取。
