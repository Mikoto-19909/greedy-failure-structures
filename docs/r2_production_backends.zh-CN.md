# R2 可选生产后端

首版只加速全预算精确枚举，保留原来的 Greedy、结构、诊断和独立验证。
默认 `python`，配置、种子、实例身份和数值 CSV 不变。
首版实现、真实 GPU 检查及全量性能结果见[验收记录](../analysis/r2_production_backend_v1_report.zh-CN.md)。

## CPU

```console
python -m pip install ".[production-cpu]"
python analysis/r2_budget_grid.py run --config analysis/r2_f2_config.json --output results/r2_cpu --workers 4 --production-backend numba
```

`numba` 严格要求依赖可用；`auto` 只做 CPU 选择，在 NumBa 依赖无法加载时警告并用
原始 Python。编译/计算错误、非法输入和错误答案不回退。`auto` 对超出加速输入范围的
合法掩码选择任意精度 Python。默认路径不加载可选数值库。

## CUDA

使用 CUDA 12.x wheel 组件及已有兼容 NVIDIA 驱动，不自动安装或更新驱动。本 extra 为
RawKernel、数组传输和运行时 API 固定 CuPy/runtime/NVRTC 组合，不包含其他 CuPy 可选
功能（FFT、BLAS 等）的全部依赖。首版安装和硬件验收在 Windows 上完成。

```console
python -m pip install ".[production-cuda]"
python analysis/r2_budget_grid.py run --config analysis/r2_f2_config.json --output results/r2_cuda --workers 1 --production-backend cuda
```

CUDA 首版使用一个隔离的 spawn 拥有者，逐图求解及诊断，父进程保存结果。非空任务
不能以 CPU 回退冒充 CUDA 成功。默认编译目录为输出目录的 `.cuda/`，须为 ASCII；
含中文路径时，用 `--cuda-cache-dir` 指定可写 ASCII 目录。设置只发生在拥有者进程内。
CuPy 可能提示没有系统 CUDA_PATH，wheel 组件仍可工作；实际初始化、编译、同步和结果
检查必须成功，提示本身不能证明成功。

加速范围为 `1<=M<=20`、非负真正整数及小于 `2**64` 的掩码；空候选的退化答案直接
处理，不宣称执行 GPU。保留重复/全空集合、恰好 k 个索引及字典序最小见证。
CUDA 内存池上限为 64 MiB，额外保留至少 128 MiB 空闲显存余量；context 不在池中。
无设备、驱动错误或显存不足都会失败，CPU RSS 不能代替显存检查。

## 计时、恢复与检查

求解发生在每图 `enumeration_seconds` 内，包括首次初始化/编译、传输、同步和解码；
外层墙钟另包含进程启动、排队和 I/O。不使用查表耗时或批次平均摊分。
非默认运行的 `production_backend.jsonl` 记录请求/实际后端、首次调用、设备、失败原因
及枚举时间，完成事件只在图保存后写入。

原 `--resume` 允许同一配置切换后端，只计算缺失图。已完成恢复不初始化可选后端；
混合恢复不是单一后端性能样本。CUDA 预算失败/中断会终止并有界回收拥有者，保留完整
检查点，未完成图不写成功。加速生产和 F2 预检验证不得改变原 Python 成本基线。

```console
python analysis/validate_r2_budget_grid.py --output results/r2_cpu --workers 4 --verification-backend numba
python analysis/r2_budget_grid.py analyze --output results/r2_cpu --no-plot --verification-backend numba --verification-workers 4
python analysis/validate_r2_budget_grid.py --output results/r2_cpu --summaries-only
```

生产与验证后端独立，验证器不使用生产器缓存或内核取得答案。完整计时可用
`run → analyze --no-plot → --summaries-only`，因为 analyze 已重算图，无需重复单独验证。

CPU 研究检查实际执行 NumBa 与回退。真实 GPU 检查在安装了生产 CPU/CUDA extra、
SciPy 1.18.1 的独立环境运行：

```console
python scripts/check.py --profile cuda --tests-only
```

该命令要求真实 GPU 测试成功，缺设备/依赖会失败。普通 CPU 检查中这两项为明确的
可选跳过，不能据此声称 GPU 已验证。跨图批处理和自动 GPU 调度不属于首版，见
[实施计划](r2_production_backends_plan.zh-CN.md)。
