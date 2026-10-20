# 历史报告与证据入口

2026-10-20 整理。阅读研究结论从[研究索引](README.md)进入；查找本地原始输出、
补充审计或退役工作树材料时使用本页。以下“本地”链接按本机现有目录布局解析，
不会随普通 Git 克隆出现，也不表示已做异地备份。

## 优先访问本地材料

- **CPU / Numba / CUDA**：[成果说明](acceleration_delivery.zh-CN.md)；
  本地归档中的 [CPU 配对测量报告](../results/archived_worktrees/consolidation-20260923-fast-verification-residual/experiments/acceleration_v1/e2e_ab/REPORT.zh-CN.md)、
  [生产后端报告](../results/archived_worktrees/consolidation-20260923-fast-verification-residual/experiments/r2_production_v1/REPORT.zh-CN.md)；
  [完整原始输出](../../archive/worktree-results-20260921/wt-fast-verification/results/)。
  报告和选定压缩包还保存在成果说明中的固定 Git 提交；完整本地输出按原目录保留。
- **R4 综合报告补充材料**：[最终报告](r4_final_research_report.zh-CN.md)；
  [配对数字审计](../results/r4_final_report_work/data_audit.json)、
  [历史发布回执](../results/r4_dual_backup_v1/publication_receipt.json)、
  [离线恢复说明](../results/r4_dual_backup_v1/RESTORE.md)。
  前两项仅在本机，不属于下方的冻结证据快照。
- **Rust 性能研究**：[小实例报告及数据](../results/rust_python_small_20260921/report.zh-CN.md)、
  [稀疏输入报告及数据](../results/rust_python_sparse_20260921/report.zh-CN.md)；
  [原工作树恢复包说明](../../archive/rust-pr69-20260921/README.zh-CN.md)。
- **在线匹配的局部冻结与分块修复**：
  [研究报告](../independent_research/online_matching_recourse/extension_20260925/报告/局部冻结与分块修复.md)、
  [固定输入](../results/online_matching_local_20260927/revised/inputs.json)、
  [比较结果](../results/online_matching_local_20260927/revised/comparison.json)、
  [逐步轨迹与审计目录](../results/online_matching_local_20260927/revised/)。
  [四请求精确值的小型证据](../experiments/online_matching_exact_v1/README.md)已随源码收录，
  与本地完整运行材料分开保存。
- **早期 Lazy Greedy 研究**：[工作报告](../../greedy-failure-evidence/lazy-greedy/work_report.md)、
  [原始输入与结果](../../greedy-failure-evidence/lazy-greedy/inputs/)、
  [Phase 3 报告](../../greedy-failure-evidence/lazy-greedy/phase3/crossover_findings.md)和
  [计时数据](../../greedy-failure-evidence/lazy-greedy/phase3/timing_trials.csv)、
  [Phase 4 报告](../../greedy-failure-evidence/lazy-greedy/phase4/sweep_findings.md)和
  [计时数据](../../greedy-failure-evidence/lazy-greedy/phase4/timing_trials.csv)。
  [旧索引](../../greedy-failure-evidence/INDEX.md)停留在 Phase 4 准备期；后来保存的报告明确写有
  部分验收条件未满足，不能据文件存在改称研究通过。此处只恢复导航，不重新计算结论。
- **工程验收**：[实例家族校验](../docs/instance_family_validation_plan.zh-CN.md)、
  [Dashboard 验收](../docs/dashboard_ux_repair_report.zh-CN.md)、
  [组件比较](../docs/component_composition_experiment.zh-CN.md)、
  [组件共享扩展](../docs/component_composition_expansion.zh-CN.md)均保留各自的本地证据链接；
  后续整合和修复日志集中在 [maintenance](../results/maintenance/)，日期与用途见
  [整合记录](../docs/branch_integration_status.zh-CN.md)。

## 随仓库或固定提交保存的研究证据

- **原始 pilot、R1、R1c**：[pilot 报告](overlap_pilot_v1.md)与
  [数据](../experiments/core_rq/overlap_pilot_v1/)；
  [R1 报告](r1_prefix_exchange_report.md)与[数据](../experiments/r1_prefix_exchange_v1/)；
  [R1c 报告](r1c_confirmation_report.md)与[数据](../experiments/r1c_confirmation_v1/)。
- **R2、R3**：[R2 报告](r2_exploration_report.zh-CN.md)与
  [冻结证据 4a419f3](https://github.com/Mikoto-19909/greedy-failure-structures/tree/4a419f338d70068fa988fa97027734cdcda0a036)；
  [R3 报告](r3_confirmation_report.zh-CN.md)与
  [冻结证据 8663e0d](https://github.com/Mikoto-19909/greedy-failure-structures/tree/8663e0dcf576ab156535ff7403bb7e4715091357)。
- **R4**：[基线报告](r4_calibration_report.zh-CN.md)与
  [冻结证据 1a8b189](https://github.com/Mikoto-19909/greedy-failure-structures/tree/1a8b1899d927cba202cf7931fe992ecd2b5a1807)；
  [DUAL 比较报告](r4_dual_comparison_report.zh-CN.md)与
  [冻结证据 b0c274f](https://github.com/Mikoto-19909/greedy-failure-structures/tree/b0c274f6be0d810b873184f0e81af41039f1a300)。
- **其他历史证据**：
  [InstanceRecord 合同研究快照 0709c32](https://github.com/Mikoto-19909/greedy-failure-structures/tree/0709c321153a257e26de278514b22db70748e2a7)；
  [在线匹配报告入口](../independent_research/online_matching_recourse/README.md)与
  [已收录的历史输出](../independent_research/online_matching_recourse/output/)；
  [工作流计时报告](gate_speed_comparison_report.md)与[数据](../experiments/gate_speed_comparison_v1/)。

五条冻结证据分支于整理日重新读取，均与上述固定提交一致；这里核对的是保存位置，
没有重新执行历史研究验证。CPU/CUDA 的固定提交属于普通 Git 历史，见其成果说明。

## 查找退役工作树中的材料

按材料来源选择已有归档，无须重建原开发工作树：

- [2026-09-13 恢复说明](../../archive/branch-retirement-20260913/RESTORE.zh-CN.md)：
  较早分支、未提交修改和分类材料。
- [2026-09-16 归档说明](../../archive/merged-branches-20260916/README.zh-CN.md)：
  R2/R3 执行工作树、拆分研究和界面验收；包含源码 bundle 与对应 ZIP。
- [2026-09-21 归档说明](../../archive/worktree-results-20260921/README.zh-CN.md)：
  加速实验和工作台的本地输出。该说明中的分支状态是当时记录。
- [2026-09-23 完整恢复包](../results/workspace_consolidation_20260923/)与
  [已展开的结果](../results/archived_worktrees/)：集中整合前的历史、设计草图和输出。
  原工作树已退役，当前使用位置以[整合记录](../docs/branch_integration_status.zh-CN.md)为准。

若只需读报告，优先用上方已展开的文件；确需恢复源码时，在新目录使用相应 bundle/ZIP，
不向当前工作目录解压覆盖。旧恢复说明中的绝对路径和环境是历史记录。

Lazy Greedy 的[原始计时来源](../../greedy-failure-evidence/lazy-greedy/phase3/timing_provenance.json)
指定源码 `ae657010046e9da0c4da1b1b5a40adfc114aab22`。整理时发现旧保护引用缺失，
已恢复本地 `refs/keep/lazy-greedy-phase3-baseline` 指向该提交；可在仓库根目录用
`git show refs/keep/lazy-greedy-phase3-baseline:src/maxcover/algorithms.py` 读取历史实现。
该引用仅保护本机源码对象，不会把仓库外的计时数据上传远端。
