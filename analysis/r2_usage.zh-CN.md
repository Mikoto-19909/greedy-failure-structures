# R2：运行、恢复与独立验证

R2 用独立定长原图扫描多个预算，输出穷举参考、规范最优见证和机制诊断。
研究边界见[一体化计划](../docs/r2_r3_integrated_plan.zh-CN.md)。R3 确认实验不属于此入口。

## 环境与执行顺序

使用 Python 3.12、NumPy 2.3.5、SciPy 1.18.1、Matplotlib 3.11.1，以及仓库检查依赖。
只重建与验证数据表时可用 `analyze --no-plot`，无需安装可选 Matplotlib；默认分析命令仍生成曲线。
先核对解释器与 `maxcover.__file__` 指向预定工作树；下列命令均从工作树根目录执行。
独立验证器共享输入设计、种子、生成器及实例身份；覆盖、穷举、结构和统计均独立重算。
诊断验证复用已有的独立 R1 验证器，不导入 R2 生产计算。

```console
python analysis/r2_budget_grid.py preflight --output results/r2_preflight_v1 --workers 4
python analysis/validate_r2_budget_grid.py --output results/r2_preflight_v1 --workers 4
python analysis/r2_budget_grid.py freeze --preflight results/r2_preflight_v1 --output analysis/r2_f2_config.json
python analysis/r2_budget_grid.py run --config analysis/r2_f2_config.json --output results/r2_grid_v1 --workers 4
python analysis/validate_r2_budget_grid.py --output results/r2_grid_v1 --workers 4
python analysis/r2_budget_grid.py analyze --output results/r2_grid_v1
python analysis/validate_r2_budget_grid.py --output results/r2_grid_v1 --summaries-only
```

F2 配置若选用少于 4 个工作进程，后续命令使用配置中较小的数值。
冻结只选择已授权网格并写设计，不生成正式原图，也不发布证据；已有 F2 文件不会覆盖。
两个候选网格都超预算时，冻结失败，正式生成不得开始。

## 可选的快速 CPU 验证

默认仍使用原始 Python 验证器。安装可选依赖后，可在独立验证和重建汇总时选择：

```console
python -m pip install ".[fast-verification]"
python analysis/validate_r2_budget_grid.py --output results/r2_grid_v1 --workers 1 --verification-backend numba
python analysis/r2_budget_grid.py analyze --output results/r2_grid_v1 --no-plot --verification-backend numba --verification-workers 1
```

`numba` 要求快速后端能初始化；缺少依赖或初始化失败时命令失败。`auto` 尝试相同后端，
不可用时发出警告并回退到原始 Python 枚举。`python` 不导入 NumPy/Numba 快速后端。
自动回退只处理依赖和编译初始化问题，非法输入、计算错误和验证不一致仍会失败。

快速后端仅加速独立诊断验证中的前缀补全枚举，使用布尔关联矩阵和完整组合枚举，
不调用生产端求解器。各预算的原始精确参考、Greedy、交换、结构、身份和汇总检查继续重算。
它不是 CUDA 后端，也不改变生产阶段。`--summaries-only` 不接受非默认后端选项。

分析默认使用保存配置中的进程上限；`--verification-workers` 可降低实际分析进程数，
不修改保存配置。小批量可先比较 1 个进程；不要将某一小样本的最优进程数推广到全量。
首次 JIT 编译和新工作进程的缓存加载有成本，比较性能时应明确是否计入。

后端和分析进程数是本次执行选项，不进入种子、实例身份和结果 CSV；恢复原始验证可直接
省略这些选项。需要抽查时，可对同一份结果另行执行默认 Python 验证命令。
## 输出与恢复运行

`graphs/` 中每张原图有一个 JSON 检查点，保存完整有序集合、预算结果、结构、诊断与耗时。
`run_status.json` 的 `complete` 仅表示生产完成；`verification.json` 的 `passed` 表示
原图和诊断独立验证通过。`summary_verification.json` 单独表示三张派生表重算通过。
三个状态不能互相替代。原图缺失、预算缺失或未完成的检查点不能作为完整样本分析。

`budget_results.csv` 保存每个原图/预算的结果；`cell_summary.csv` 包含失效率精确区间、
四个连续指标及其原图级 bootstrap 逐点区间；`mechanism_summary.csv` 汇总预定诊断，
`budget_curves.svg` 展示预算曲线。
所有区间都是逐点区间，不支持事后挑峰的同时推断。

```console
python analysis/r2_budget_grid.py preflight --output results/r2_preflight_v1 --workers 4 --resume
python analysis/r2_budget_grid.py run --config analysis/r2_f2_config.json --output results/r2_grid_v1 --workers 4 --resume
```

恢复运行要求保存的配置与指定配置相同，复用已完成原图，重新计算没有完成检查点的原图。
分析命令先用独立验证器复算当前读入的原图、穷举参考和轨迹，再从同一份内存数据重建汇总；
不调用生产入口或增加研究样本，但会重新核对种子生成的输入并计算独立参考，因此耗时增加。
旧 `verification.json` 的 `passed` 是历史记录，不能证明修改后的数据仍正确。
`--summaries-only` 仅核对派生表与保存数据的一致性，不证明原图的最优值；两种覆盖必须区分。
诊断中的 `budget_exhausted` 表示有限交换检查未完成，不等于局部最优。

12 小时计算预算累计生产、原图验证、分析及汇总验证的墙钟时间，正式批次还计入预检耗时。
`execution.jsonl` 保存实际操作耗时和中断状态；不要删除它来重新获得预算。
达到上限后停止提交新任务，已运行的单图任务安全退出可能产生短暂超出；不替换难图或删减样本。
内存按工作进程峰值与进程数量保守检查，输出上限为 2 GiB。资源失败保留已保存输入和结果。

运行命令将检查点和结果写入本机 `results/`，不自动发布。已完成批次的远端证据见[R2 报告](r2_exploration_report.zh-CN.md)。

上列命令保留原始阶段顺序。复现已完成批次时直接使用已提交的 F2 配置，从 `run` 开始，
并选择新的结果目录；无需重新冻结已存在的配置。只重建汇总时，可先从证据快照恢复对应目录。
