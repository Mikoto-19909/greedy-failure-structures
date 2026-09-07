# R1：前缀可达性与交换修复实验设计

在查看本轮轨迹结果前固定以下决定。本轮采用已有研究计划的 R1a/R1b，
完成离线工具、功能验证和原 pilot 的探索性重分析。

研究对象为原配置下全部 60 个实例（30 对）。重建沿用原始 seed 和集合索引，
原始数据、原主检验及停止决定均保持原样。这些是已有样本的新分析，不增加样本量。

对每个 Greedy 前缀 `P_t`，穷尽所有包含它的 k 元选择，计算最佳完成值 `O_t`。
首次 `O_t < O` 的步骤为 `t*`。在每个已观察前缀上完整检查最大边际候选，
以首次失效步是否存在仍能完成到 `O` 的替代候选分类。该分类只针对已观察前缀，
不推断所有更早的平局路径。

一换一终点直接使用项目的 `local_search`，另重建严格最佳改善轨迹并核对终点和
评估数。之后执行至多二换二的严格最佳改善，每轮同时包含一换一；等值改善按
`(交换大小, 移除索引元组, 加入索引元组)` 取最小者。完整扫描且无改善才能标为
`local_optimum`，预算用尽标为 `budget_exhausted`。具体预算和六个固定功能样例
见 [设计输入](r1_prefix_exchange_design.json)。

产物为完整集合与轨迹 `paths.jsonl`、逐实例 `instance_summary.csv`、按原组汇总的
`case_summary.csv`，以及图和中文解释。详细轨迹保存前缀、增益、所有最大增益候选、
最佳完成选择、首次失效步、两种交换的每轮选择/评估数/停止原因。功能样例与 pilot
分别标记，不混入研究统计。

主描述量为“失败实例中可由首次失效步替代平局选择避免的比例”，同时报告全体实例
中的比例。补充量为失效步骤、交换修复数和包含零值的平均相对 gap。本轮不作新的
显著性检验，也不根据结果追加 seed。

验收要求：全部实例及所有最大增益候选完成；`O_0=O`、`O_t` 不增、`O_k=G`；
交换轨迹可重放，最终邻域完整检查；独立程序以 Python 集合并集和直接枚举重算
每条轨迹及汇总。保留失败与未修复结果。后续新样本确认研究单独设计。

## 轨迹文件约定

每个 JSONL 对象包含 `instance_id, population, case_id, repetition, seed, config_hash,
universe_size, k, sets, source_greedy_selected, source_optimum`，其中 `sets` 是按原索引
排列的元素列表。分析字段如下：

- `greedy_selected, optimum, optimum_selected, optimal_solution_count, completion_count`。
- `prefixes`：依次从 t=0 到 k，每项包含 `step, prefix, coverage, optimal_completion,
  completion_selected, completion_count`。
- `ties`：按步骤、候选索引排序，每项包含 `step, candidate, marginal_gain, chosen,
  optimal_completion, completion_selected, completion_count, preserves_optimum`。
- `first_failure_step`（无则 null）、`mechanism`（`optimal`、`tie_avoidable` 或
  `one_step_limit`）。
- `one_swap`、`two_swap`：包含 `selected, coverage, evaluations, exchanges, status, rounds`。
  每轮包含 `round, before, before_coverage, removed, added, after, after_coverage,
  evaluations, status`；改善轮为 `improved`，终止轮为 `local_optimum` 或
  `budget_exhausted`。评估数为该轮已检查的邻居数，总预算对二换二阶段累计计算。

最佳完成的平局取字典序最小的索引组合。source 字段仅 pilot 有原始数据，功能样例
为 null。两张 CSV 从这些轨迹生成；独立验证将核对每个字段和汇总数字。

原始 CSV 的 Greedy 选集经过排序，只表示终点。`greedy_selected` 与 `prefix`
使用按原算法规则重建的决策顺序；二者的终点集合须与原 CSV 一致。`O=0` 时
相对 gap 未定义，保存为 null/CSV 空单元格。
