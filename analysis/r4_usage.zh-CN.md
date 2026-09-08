# R4 前缀上界：输入、预检与校准

实现 [R4 准备方案](../docs/r4_preparation_plan.zh-CN.md)的整数前缀基线。
使用 Python 3.12 和[仓库检查依赖](../CONTRIBUTING.md)，执行前检查解释器、版本及
`maxcover.__file__`。源码目录不变，公共 Greedy、CSV 与原研究恢复运行契约不变。

## 固定输入

从 R2 [证据提交 `4a419f3`](https://github.com/Mikoto-19909/greedy-failure-structures/tree/4a419f338d70068fa988fa97027734cdcda0a036)
取得 `results/r2_preflight_v1` 与 `results/r2_grid_v1`，保留各自 `config.json` 和 `graphs/`。
下列命令假定它们位于本地 `results/r4_source/results/`。路径可以替换，但来源提交和输入
不能替换。入口按冻结种子重新计算集合只用于来源比对，不保存替代原图。
输入读取、生成器、实例身份和资源/I/O 基础设施共享；生产与验证的路径、上界、穷举
参考和汇总计算相互独立。旧 R1 机制诊断不作为本批计算依赖。

## 18 图预检与 F4

```console
python analysis/r4_prefix_bounds.py preflight --source results/r4_source/results/r2_preflight_v1 --output results/r4_preflight_v1
python analysis/validate_r4_prefix_bounds.py --source results/r4_source/results/r2_preflight_v1 --output results/r4_preflight_v1
python analysis/r4_prefix_bounds.py analyze --source results/r4_source/results/r2_preflight_v1 --output results/r4_preflight_v1
python analysis/validate_r4_prefix_bounds.py --output results/r4_preflight_v1 --summaries-only
python analysis/r4_prefix_bounds.py freeze --source results/r4_source/results/r2_preflight_v1 --output results/r4_preflight_v1 --config analysis/r4_f4_config.json
```

预检选择九个 `(N,d)` 单元各自的重复号 0、1。入口固定单进程，累计时间上限 1 小时，
总内存 6 GiB，输出 2 GiB。`freeze` 重新验证当前预检输入及派生表，以每单元最慢图
外推生产和两次独立复核，并与实测批次墙钟外推取较大者；乘 2 后加已用预检时间和
600 秒汇总/I/O/启动余量。输出和峰值内存也留余量，详见 F4 配置的 `resource_decision`。
资源不足不生成 F4 文件，既有 F4 文件不能覆盖。这里的 freeze 是设计定版，不发布证据。

## 定版后的正式校准

以下命令已用于完成 [首轮校准](r4_calibration_report.zh-CN.md)，也可用于独立复现。
F4 设计定版与执行是不同操作，已有批次须遵循下述恢复规则。

```console
python analysis/r4_prefix_bounds.py run --config analysis/r4_f4_config.json --source results/r4_source/results/r2_grid_v1 --output results/r4_calibration_v1
python analysis/validate_r4_prefix_bounds.py --source results/r4_source/results/r2_grid_v1 --output results/r4_calibration_v1
python analysis/r4_prefix_bounds.py analyze --source results/r4_source/results/r2_grid_v1 --output results/r4_calibration_v1
python analysis/validate_r4_prefix_bounds.py --output results/r4_calibration_v1 --summaries-only
```

生产中断后在同一条 `preflight` 或 `run` 命令末尾加 `--resume`。完成原图先作来源与
证书检查，通过后不重复生产；未生成的原图继续计算。独立验证每次重算当前批次的
证书与精确参考，不依赖历史 `passed`；验证中断后重新运行验证命令。
累计预算包括已消费的预检及该批次各次运行。预算耗尽时保留输入与检查点，不能用
另建目录或缩小样本规避冻结设计。实质调整须记录修订，不能覆盖原定版文件。

## 结果与拒绝行为

`graphs/` 按原图保存来源、跨预算路径/前缀、上界与耗时；`verification.json`
记录独立检查的证书时间和穷举参考时间。`analysis_timing.json` 分开记录汇总前重查的
这两种时间与汇总时间；`execution.jsonl` 保存各阶段累计计算的批次内部墙钟时间。

`budget_results.csv` 每原图/预算一行；`cell_summary.csv` 按 `(N,d,k)` 给出均值、
中位数和 nearest-rank P90、缺失比例数量及认证数量。分母为零的比例写空，保留原图。
`--summaries-only` 只证明派生一致性；完整认证须另完成当前原图、证书与参考验证。
`analyze` 在写表前独立复核当前读取的数据，不把历史状态当作新数据的验证。

`G/U` 是近似比下界；`U>G` 本身不能证明失效。该基线满足 `U=G` 当且仅当
`U_initial=G`，认证数量用于正确性核对，收紧量才衡量前缀项的额外作用。
缺图/预算、错误路径/来源、非规范参考、未完成状态、越限和未定版正式运行均会拒绝，
不会补抽原图或将无效界截断成有效界。正式入口不接受单元测试的 fixture 配置。
