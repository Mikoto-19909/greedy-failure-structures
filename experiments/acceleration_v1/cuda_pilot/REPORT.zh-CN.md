# CUDA 批量穷举试验

日期：2026-09-08。状态：本地原型完成，未接入正式实验执行器。

在本次固定样本中，CUDA 对 20 个候选集合的全预算穷举有明显收益；12 个候选集合时，编译后的 CPU 更快。

## 方法与范围

- 输入来自当前 `analysis/r2_f2_config.json`：n=m 为 12、16、20，d 为 2、3、4，各取 repetition=0；9 张图的任务、种子与位掩码已在运行前保存到 `design.json`。
- 每张图计算全部 k=0..m 的最优覆盖量，并保留字典序最小的最优索引元组。CPU Python 基线直接调用仓库原有 `all_budget_optima`。
- 编译 CPU 使用单线程 Numba 子集动态规划；它改变了遍历实现并增加了状态数组。因此对比反映完整实现差异，不能全部归因于硬件。它也不是已穷尽优化的 CPU 基线。
- CUDA 使用自定义 CuPy RawKernel：批量计算子集覆盖量，以整数打包覆盖量与反向索引位，实现确定性平局选择；先在线程块内再全局取最大值。
- 每个尺寸测 batch=1（d=2）和 batch=3（d=2,3,4）。先预热，再各运行 5 次；每轮轮换后端顺序。
- 计时边界：主机上的位掩码输入，到主机上的 Python 最优值与解。CUDA 包括主机打包、分配请求、H2D、内核、同步 D2H 和结果解码；CuPy 分配池及编译缓存已经预热。
- 所有后端均不计入输入生成、独立验证、文件读写、首次导入/编译。CPU 基线没有启用现有多进程执行器；本试验不声称优于某个 CPU 多进程配置。

## 实测中位数与范围

- m=12，batch=1：原始 Python 1.476 ms（范围 1.339–2.032 ms）；编译 CPU 0.057 ms（范围 0.039–0.095 ms）；CUDA 0.325 ms（范围 0.157–0.439 ms）。CUDA 相对原始 Python 为 4.55 倍，相对编译 CPU 为 0.17 倍（小于 1 表示 CUDA 更慢）。
- m=12，batch=3：原始 Python 3.819 ms（范围 3.714–3.942 ms）；编译 CPU 0.127 ms（范围 0.093–0.163 ms）；CUDA 0.334 ms（范围 0.204–0.484 ms）。CUDA 相对原始 Python 为 11.42 倍，相对编译 CPU 为 0.38 倍（小于 1 表示 CUDA 更慢）。
- m=16，batch=1：原始 Python 22.544 ms（范围 20.482–25.317 ms）；编译 CPU 0.244 ms（范围 0.172–0.382 ms）；CUDA 0.490 ms（范围 0.172–0.849 ms）。CUDA 相对原始 Python 为 45.99 倍，相对编译 CPU 为 0.50 倍（小于 1 表示 CUDA 更慢）。
- m=16，batch=3：原始 Python 62.659 ms（范围 60.623–65.055 ms）；编译 CPU 0.538 ms（范围 0.473–0.594 ms）；CUDA 0.619 ms（范围 0.266–0.939 ms）。CUDA 相对原始 Python 为 101.23 倍，相对编译 CPU 为 0.87 倍（小于 1 表示 CUDA 更慢）。
- m=20，batch=1：原始 Python 318.637 ms（范围 312.493–334.159 ms）；编译 CPU 5.286 ms（范围 4.861–6.400 ms）；CUDA 0.468 ms（范围 0.461–1.052 ms）。CUDA 相对原始 Python 为 680.27 倍，相对编译 CPU 为 11.28 倍（小于 1 表示 CUDA 更慢）。
- m=20，batch=3：原始 Python 1426.566 ms（范围 1044.926–1531.058 ms）；编译 CPU 20.868 ms（范围 17.386–26.130 ms）；CUDA 0.718 ms（范围 0.676–0.760 ms）。CUDA 相对原始 Python 为 1986.86 倍，相对编译 CPU 为 29.06 倍（小于 1 表示 CUDA 更慢）。

## 正确性与实际限制

- 独立校验调用 `validate_r2_budget_grid.reference`，使用 Python set 与 itertools.combinations：14 个实例/边界样例，每个后端共 174 个预算结果，覆盖量和完整最优索引元组全部一致。
- 边界样例覆盖全零、重复集合、多个等价最优解、无重叠集合、64 位最高位和全 64 位覆盖。每个后端均拒绝 7 类非法输入；正式计时的每一次结果也都与原始 CPU 结果核对。
- 原型仅支持 1<=m<=20、64 位无符号集合掩码、同批相同 m；没有超时、断点续跑和生产资源预算接口。
- 显卡为 RTX 4060 Laptop GPU，桌面其他程序仍运行。五次重复和九张图不足以代表所有负载；尤其亚毫秒测量与单次极值易受调度影响。
- 未测试 Greedy、CP-SAT、诊断全过程、独立验证、磁盘输出或完整 R2/R4 流水线的 CUDA 迁移。不能把本报告的穷举函数倍率写成项目总加速倍率。
- 第一次尝试因 NVRTC 无法打开包含中文用户名的临时源码路径而失败；最终原型仅在当前进程中把编译临时目录放到本目录的 tmp，随后运行完成。CuPy 仍可能报告找不到系统 CUDA 路径的提示，但已通过 wheel 提供的运行时成功编译和执行。
- 实际记录的首次调用：共享依赖导入 0.726 s，编译 CPU 首次调用 0.713 s，CUDA 首次调用 0.226 s。它们按顺序测量，不能视为三个独立冷启动程序的完整耗时；后续重跑可能命中缓存。

## 复现

在仓库根目录运行，沿用已经固定的 design.json：

```powershell
& results/cuda_trial_v1/.venv/Scripts/python.exe -u results/cuda_trial_v1/trial.py run
& results/cuda_trial_v1/.venv/Scripts/python.exe results/cuda_trial_v1/write_report.py
```

运行会重新验证并覆盖本试验的计时/报告文件。若需保留本次测量，应先复制这些小型结果文件；无需复制虚拟环境。`prepare` 仅用于首次固定输入，发现 design.json 已存在就拒绝覆盖。

重建独立环境：先用 Python 3.12 创建本目录 `.venv`，再执行该解释器的 `-m pip install -r results/cuda_trial_v1/requirements.txt`。不需要系统级安装 CUDA Toolkit；仍需可用 NVIDIA 驱动。

产物：`trial.py` 原型、`design.json` 固定输入、`timings.json` 90 条计时、`validation.json` 校验结果、`cold_start.json` 首次调用时间、`summary.json` 汇总与环境、`requirements.txt` 精确依赖版本。

下一步若要接入生产，应单独评估完整流水线：保留 CPU 回退，小实例优先编译 CPU，大批量穷举候选使用 CUDA，并验证执行器的结果顺序、工作量统计与恢复行为。本次不自动进行该迁移。
