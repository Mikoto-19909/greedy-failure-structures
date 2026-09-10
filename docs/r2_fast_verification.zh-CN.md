# R2 可选 CPU 验证

默认入口 `analysis/validate_r2_budget_grid.py` 保留原 Python 实现。
可选入口 `analysis/validate_r2_budget_grid_fast.py` 加速前缀补全枚举，
不改变原图、预算、规范见证、诊断或 CSV。已有测量及原始资料见
[加速成果整理](../analysis/acceleration_delivery.zh-CN.md)。

## 使用

```console
python -m pip install ".[fast-verification]"
python analysis/validate_r2_budget_grid_fast.py --output results/r2_grid_v1 --workers 4 --verification-backend numba
python analysis/r2_budget_grid.py analyze --output results/r2_grid_v1 --no-plot --verification-backend numba --verification-workers 4
python analysis/validate_r2_budget_grid.py --output results/r2_grid_v1 --summaries-only
```

输出目录必须已经含原批次的 `config.json` 和图检查点，准备与恢复方法见
[R2 使用说明](../analysis/r2_usage.zh-CN.md)。`numba` 严格要求可选依赖；
`auto` 仅在依赖或初始化不可用时明确警告并使用 Python，计算错误不能转成成功。
默认 Python 路径不加载 NumPy/Numba。F2 预检与定版维持原 Python 成本基线，
可选加速验证及分析拒绝用于 `preflight` 批次。

分析先核对当前读取的所有图，完成后才重建汇总；旧 `passed` 不是当前输入有效的证明。
多进程数不能超过原配置上限。验证、分析和恢复仍计入原累计预算，不重置计时或改写原配置。

## 与冻结 DUAL 的兼容边界

`validate_r2_budget_grid.py` 的源文件保持不变，因为它属于已发布 DUAL 的冻结依赖。
加速适配器先核对原任务，再用临时视图复用原验证器的输入、结构和全部预算参考检查，
随后独立重算完整诊断；临时视图不写回输入。计算内核用布尔覆盖矩阵和组合枚举，
不导入生产器、生产缓存或 CUDA 内核。

旧 Python CLI、默认分析与冻结 DUAL 继续使用原验证器；只有显式选择加速的 R2 分析
才调用新适配器。检查包含已知答案、字段损坏、无诊断任务、缺依赖与计算错误、
多进程恢复及 CSV 一致性。历史性能测量属于原交付布局，不能当作新适配器的重新计时。
