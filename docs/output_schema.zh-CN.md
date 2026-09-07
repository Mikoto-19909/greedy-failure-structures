# Benchmark 输出指南

一次完成的 benchmark 会在选定的输出目录下写出规范输入、派生统计量、
图表和报告。`src/maxcover/` 里的记录类和 schema 常量是机器可读的
事实来源；本指南解释这些文件之间的关系。

## 规范实例与运行产物

`instances.csv` 记录每个生成的实例及复现它所需的身份。字段包括案例与
实例族、确定性种子与耦合身份、维度与生成器参数、实测结构性质，以及
任何经过验证的已知最优证书。

`raw_results.csv` 记录每一次计划中的算法运行。它携带运行与实例身份、
算法变体与选项、状态、incumbent 覆盖量、上界与参考字段、实际运行时间、
选中的集合索引、元数据以及任何运行错误。检查点按这个格式写出，
恢复运行时以稳定的运行标识为单位。

这两个文件是 `summarize` 消费的规范输入。派生文件必须能由它们和对应
配置重建出来，不需要执行任何算法。

## 通用聚合

`summary.csv` 是为兼容旧消费者保留的聚合。它的行直接汇总原始运行，
并不是所有分析的规范来源。

`descriptive_statistics.csv` 是覆盖量、最优性差距和已完成运行时间指标的
规范类型化聚合。它记录重复单位、有效样本、超时与错误计数、精确参考
可得性和描述统计量。

`confidence_interval_statistics.csv` 包含有效实例级均值的双侧区间。
区间不可估计时行仍然保留，状态字段说明原因，不可用的数值字段留空。

`censored_runtime_statistics.csv` 把超时删失与已完成的运行时间观测分开
记录。超时时长不会被静默当作已完成的运行时间。

## 精确参考覆盖与删失诊断

`reference_status.csv` 每个生成的实例一行。它记录实际生效的参考状态、
每个启用的精确变体的状态、证明来源、证书可得性和交叉验证状态。
因配置的集合数上限而被排除的求解器记为 `not_run`，不会被静默略去。

`reference_coverage_statistics.csv` 按实例族、规范化生成器参数和状态
对这些行分组。分母是该切片内全部生成的实例，分子是至少有一份经验证
最优证明的实例。状态行区分 `optimal`、`feasible`、`timeout`、`error`、
`known_optimum_certificate` 和 `not_run`。

`reference_censoring_bias_statistics.csv` 在同一族和参数切片内比较
保留实例（已有证明的参考）与被排除实例（无证明）。它报告规模与实测
结构的均值，以及被排除均值减去保留均值。两组都有观测时比较才有值；
没有任何缺失值被替换成零。

`reference_cutoff_sensitivity_statistics.csv` 保留每个启用的精确变体的
时间与集合数上限、状态计数、仅求解器的参考覆盖，以及计入经独立验证
证书后的实际覆盖。用不同上限配置多个变体，就能在同一批生成实例上
直接做敏感性比较。

当 Brute Force 与 Branch-and-Bound 或 CP-SAT 对同一个合格小实例都证明了
最优值，`reference_status.csv` 会标记这次交叉核对。最优精确来源之间、
或与已知最优证书之间的任何不一致，都会以错误中止规范化。

## 配对算法分析

每次完成的 benchmark 都会写出以下类型化文件。行需要相应的变体和合格的
实例级观测或配对；没有适用行时文件只保留表头：

- `greedy_failure_statistics.csv`：与有效最优参考配对的 Greedy 结果
- `local_search_recovery_statistics.csv`：从 Greedy 失败中的恢复
- `local_search_remaining_gap_statistics.csv`：局部搜索后相对精确参考的
  残余差距
- `heuristic_exact_runtime_ratio_statistics.csv`：已完成的启发式/精确
  运行时间对
- `bnb_node_reduction_statistics.csv`：基线/增强 Branch-and-Bound 节点
  比较
- `quality_runtime_pareto_statistics.csv`：合格的质量/运行时间前沿分类

`search_comparison.csv` 只在 `bnb_baseline` 与 `bnb_enhanced` 运行共享
实例时写出。`stochastic_summary.csv` 只在显式给种子的算法运行取得可行
覆盖量时写出。这两个兼容输出是有条件的，与上面列出的类型化文件不同。

## 结构差距 cartography 产物

`cartography` 命令额外产出一个本地分析包：

- `structural_gap_statistics.csv` 按压力因子族、强度、处理/对照角色、
  算法和实例种子报告 `1 - coverage / optimum`，含均值、中位数、样本
  标准差、四分位数、极差和双侧 Student-t 置信区间。
- `paired_control_differences.csv` 报告种子配对的
  `stressor_gap - control_gap` 分布，字段与上面相同。缺失的精确参考
  会计数并排除。
- `precision_diagnostics.csv` 用观测到的配对差标准差，估计达到设计
  固定置信区间半宽目标所需的种子数。
- `stressor_strength_gap.svg` 对每个启发式算法绘制压力强度与均值差距
  及其区间。
- `family_algorithm_gap.svg` 是族×算法图，对配置的各强度档均值取等权
  平均。

`validate_cartography_output.py` 不把这些哈希当作计算正确的证明。
它从 `raw_results.csv` 独立重建实例种子聚合、配对差、区间和精度诊断，
再对照原始结果和设计核对完整的执行计划身份与存储值。计划运行缺失
一律拒绝，即使派生表已重建；存在错误记录时仍可能贡献一个缺失差距。
生成的实例还会核对实例表和选中集合覆盖量。最优参考来自最优精确运行
记录或重新生成的证书；存储的最优值/差距必须与这些参考一致。
普通的 cartography 恢复也会先删除已退役的 `cartography_manifest.json`，
再刷新分析产物。被拒绝的配置、设计或检查点输入则保持它不动。
配对分析 CLI 同样只在两个输入都通过校验后，才删除旧的
`analysis_manifest.json`，再写出刷新的比较文件。

对有多个 `algorithm_seeds` 的算法，一个实例贡献其全部算法种子差距的
算术平均。因此分布和区间计算的独立单位是生成的实例种子，而不是单次
随机化算法运行。

## 结构关联分析

以下文件把实例级响应值与实测或配置的结构预测量关联起来。它们对缺失
或常数数据保留合格计数和关联状态：

- `gap_density_association_statistics.csv`
- `gap_overlap_association_statistics.csv`
- `gap_clustering_association_statistics.csv`
- `runtime_set_count_association_statistics.csv`
- `runtime_k_association_statistics.csv`
- `search_nodes_dominated_ratio_association_statistics.csv`

这些是描述性关联，不确立因果关系、统计显著性，也不支持更复杂的
生存分析或非线性建模。

## 报告与图表

`results_summary.md` 从类型化统计量渲染一份本地可读报告。SVG 产物
覆盖差距、运行时间、结构关联、局部搜索恢复、质量/运行时间、搜索节点
和超时等视图。文件名清单由 [`benchmark.py`](../src/maxcover/benchmark.py)
里的 `REPORT_FILENAMES` 枚举。

`reference_coverage_by_case.svg` 是 cartography 的缺失情况图层。它的
条形使用全部生成的实例，保留未解决的参考状态，而不是只显示适合做
差距分析的实例。

只有表头的 CSV 或没有适用类型化行的图表都是有效产物。它表示配置的
运行没有提供该分析所需的输入，不表示指标等于零。

## 状态与精确参考语义

- `optimal` 表示某个精确方法闭合了上界，可以提供参考最优值。
- `feasible` 表示有 incumbent 可用，但没有最优性证明。需单独看
  `algorithm_metadata.termination`：这个状态可能伴随时间或迭代限制，
  不代表执行已完成。
- `timeout` 表示工作在配置的限制处停止；可能有 incumbent 或上界，
  但超时运行本身不能证明最优值。规范化行仍可能携带来自经独立验证的
  实例证书、或同一实例另一条精确运行的参考最优值。
- `error` 表示没有产生有效的算法结果。
- `known_optimum_certificate` 表示生成器提供了经独立验证的可行解和
  最优上界证明。
- `not_run` 是派生的参考诊断状态，用于配置的精确变体因集合数上限
  不合格、或未配置任何精确来源的情形。它不是算法 `SolutionStatus`。

失效率、相对差距和其他相对最优值的分析，都需要同一实例的有效最优
参考。空白值表示不合格或数据不可得，不能当作零解读。

## 回放产物

runner 在 `failures/` 下为可回放的超时或错误案例写出自包含 JSON 文件。
每个文件包含序列化的实例、记录的算法身份与选项，以及用于比较的结果
字段。`replay` 命令可以使用记录的算法或显式指定的替换算法，但替换
算法收到的是记录的选项，必须接受这份选项契约；replay 不会在算法之间
翻译选项。

## 可选输出验证

runner 写出的 CSV 结果和报告不带 manifest 或文件校验和。配置、实例和
运行哈希仍是用于结果连接和恢复运行的内部标识。实验配置要和它的结果
一起保存。普通的运行、恢复和 summarize 会先检查现有输入、删除已退役的
`manifest.json`，再写出刷新的输出。被拒绝的输入则保持现有结果和旧版
元数据不动。

对已完成运行做详细检查：

```console
python .github/scripts/validate_benchmark_output.py --config configs/quick.json --output results/quick
```

验证器核对配置与执行计划身份、记录一致性、从 `raw_results.csv` 和
`instances.csv` 重算的受支持统计量、摘要分组和部分图表。
它与生产端共享计算和渲染的辅助函数，不回放每个算法，也不检查旧版
图表。Markdown 的标题、段落和排版不在其范围内，包括手工改过的报告
数字。散文结论要对照源数据评审；通过该验证器不代表报告写下的结论
正确。这个命令要求全部运行完成且每个实例都有最优参考，所以它不是
探索性超时或缺参考输出的通用检查。

[核心重叠分析](../analysis/core_overlap_pilot.py)直接读取那两个 CSV，
对照生成的实例核对样本配对、完成情况、最优参考状态和选中集合覆盖量，
写出配对表、报告和图。不需要台账或单独的验证记录。

`analysis/` 下的报告应直接链接到 `experiments/core_rq/` 中保存的配置
与数据。[文档大纲](../CONTRIBUTING.md#document-structure)提供可读的
默认结构，不强制固定措辞。
