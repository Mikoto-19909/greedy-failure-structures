# CPU / Numba / CUDA 成果与交付边界

2026-09-09 整理。以下性能数字来自 2026-09-08 已完成的固定工作负载测量，
本次不重跑全量性能实验，也不改变原研究配置和证据。

## 已有结果

- 可选 CPU 验证：原 Python 四进程生产，加速前缀补全验证；六次全新工作流中，
  Python 验证组中位数 291.299 秒，Numba 验证组 216.028 秒，减少 25.84%。
- 首版生产后端：三种方式各三次全新 1,800 图、13,000 预算流程，验证后端统一为
  Numba 四进程。Python 四进程中位数 156.491 秒，Numba 四进程 86.547 秒，
  CUDA 单拥有者 119.175 秒。三种方式的非计时结果与原 R2 归档一致。
- 两组测量的来源、缓存、进程配置与边界不同，不拼接成累计倍率；CUDA 内核优势
  不能代替完整工作流收益，也不作跨机器或更大规模保证。

## 固定资料位置

完整资料保留在现有加速分支的
[固定提交 e1d865b](https://github.com/Mikoto-19909/greedy-failure-structures/tree/e1d865bd90ebd13530515f31c01115fe515df26a)。
它是已推送的普通 Git 历史，不冒称已经发布到受保护证据分支；原分支与本地工作树保留。

- [CPU 验证测量与限制](https://github.com/Mikoto-19909/greedy-failure-structures/blob/e1d865bd90ebd13530515f31c01115fe515df26a/experiments/acceleration_v1/e2e_ab/REPORT.zh-CN.md)
  及[配对时间表](https://github.com/Mikoto-19909/greedy-failure-structures/blob/e1d865bd90ebd13530515f31c01115fe515df26a/experiments/acceleration_v1/e2e_ab/paired_comparison.csv)。
- [生产后端全量验收](https://github.com/Mikoto-19909/greedy-failure-structures/blob/e1d865bd90ebd13530515f31c01115fe515df26a/experiments/r2_production_v1/REPORT.zh-CN.md)
  及[原始计时](https://github.com/Mikoto-19909/greedy-failure-structures/blob/e1d865bd90ebd13530515f31c01115fe515df26a/experiments/r2_production_v1/timings.csv)。
- [完整档案布局及恢复说明](https://github.com/Mikoto-19909/greedy-failure-structures/blob/e1d865bd90ebd13530515f31c01115fe515df26a/experiments/acceleration_v1/README.md)
  和[生产档案恢复说明](https://github.com/Mikoto-19909/greedy-failure-structures/blob/e1d865bd90ebd13530515f31c01115fe515df26a/experiments/r2_production_v1/README.md)。

两份约 31,000 行配置和五个合计约 58.7 MB 的 ZIP 不再复制到源码交付。
原始档案、计时和测量脚本均保留；历史脚本应按其记录的源码版本、环境和目录布局复现。

## 当前交付

第一部分是[可选 CPU 验证入口](../docs/r2_fast_verification.zh-CN.md)。原冻结 R2 验证文件
保持不变，新适配器独立处理加速诊断，因此旧 DUAL 的源码约束仍可检查。
第二部分提供[可选 CPU/CUDA 生产后端](../docs/r2_production_backends.zh-CN.md)，默认仍为 Python，
`auto` 只在 CPU 后端之间选择，不自动选用 GPU。两部分分别提交，便于独立审阅和回退。
本次验收侧重已知答案、失败拒绝、输入不变、恢复和数值输出一致性；不把历史耗时
标为本次新代码的性能测量。
