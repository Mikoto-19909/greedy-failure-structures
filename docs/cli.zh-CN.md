# 命令行工作流

命令行是校验配置、运行实验、重建报告和回放序列化案例的正式入口。
安装本包后，所有命令都从仓库根目录运行：

```console
python -m pip install -e .
```

可选的 CP-SAT oracle 只在配置启用它时才需要安装：

```console
python -m pip install -e ".[oracle]"
```

## 选择工作流

| 目的 | 配置或起点 |
| --- | --- |
| 当前研究 | [固定重叠 pilot 计划](https://github.com/Mikoto-19909/greedy-failure-structures/pull/23)。在维度和期望集合大小匹配的 `uniform` 对照下，用 Greedy 与穷举参考比较 `high_overlap`。 |
| 示例与兼容检查 | `demo`、`quick`，以及较大的旧版 `configs/full.json` 工作流。 |
| 历史探索与附录 | 早期探索性配置和 `configs/structural_gap_cartography.json` 等更大范围扫描，各有其文档记载的用途。 |

[pilot 配置](../configs/core_overlap_pilot.json)和
[离线分析脚本](../analysis/core_overlap_pilot.py)均已实现。
正式实验已完成，见[报告](../analysis/overlap_pilot_v1.md)和
[实验数据](../experiments/core_rq/overlap_pilot_v1/)。复现固定设计请用
[专用命令](#核心重叠-pilot)。

不带命令运行 CLI 等价于 `quick`。PowerShell 包装脚本同样默认 quick，
Dashboard 在没有保留选择时也会先选 `quick.json`。这些都只是示例默认值。
`full.json` 是较大的旧版多实例族 benchmark，不代表当前研究的完整方案：

```console
python run_project.py benchmark --config configs/full.json --output results/full
```

旧配置仍然支撑着在用检查：`p3_lazy_greedy.json` 用于 CI，
`p7_controlled_stressors.json` 用于生成器审计，配对配置用于种子配对方法检查。
各自的角色见[工作流索引](README.md)。

## 配置兼容性

`configs/quick.json` 和 `configs/full.json` 是 schema v1。加载器会把它们在
内存中迁移到 schema 3 并发出 `LegacyConfigWarning`；文件本身保持既有身份不变。
`configs/sweeps.json` 是 schema 2，`configs/p3_*` 到 `configs/p7_*` 是 schema 3。
这些版本标签描述的是兼容性，不代表某项研究的用途或完整性。
按实际角色从工作流索引里选配置。

## 核心重叠 pilot

公开证据对应的干净提交是 `27acae5f2ee9f478fba22af98c6694382a0a7100`，
在[准备 PR #28](https://github.com/Mikoto-19909/greedy-failure-structures/pull/28)
和[选择验证修复](https://github.com/Mikoto-19909/greedy-failure-structures/pull/29)
之后。下面的命令在当前检出上运行，使用同一配置和预定的种子批次。
重新运行请换一个新的输出目录；即使结果不确定或方向相反，也保留这批种子。
回放历史源码版本会连带复现当时的旧工具和旧输出格式。
Matplotlib 是可选的离线绘图依赖：

```console
python -m pip install matplotlib
python run_project.py benchmark --config configs/core_overlap_pilot.json --dry-run
python run_project.py benchmark --config configs/core_overlap_pilot.json --output results/core_overlap_pilot_v2 --workers 1
python .github/scripts/validate_benchmark_output.py --config configs/core_overlap_pilot.json --output results/core_overlap_pilot_v2
python analysis/core_overlap_pilot.py --config configs/core_overlap_pilot.json --results results/core_overlap_pilot_v2 --output results/core_overlap_pilot_v2/analysis
```

分析脚本直接读取 `instances.csv` 和 `raw_results.csv`，核对样本配对和
选中集合的覆盖量，并写出 `paired_instances.csv`、`report.md` 和
`failure_rate.svg`。上面那个更细的 benchmark 验证器是可选的，
不需要 manifest 或单独的验证记录。
[检查点计划](core_overlap_checkpoint_plan.zh-CN.md)记录了原始实验设计。
当前的研究流程与检查以 [CONTRIBUTING.md](../CONTRIBUTING.md) 为准。

## 命令

### `quick`

运行小型入门工作流，把本地产物写到 `results/quick`：

```console
python run_project.py quick
```

不带命令效果相同。自带的 `quick.json` 是旧版 schema-v1 配置，
所以看到 `LegacyConfigWarning` 属正常。

### `demo`

打印一个固定的对抗构造及其在本机算出的解：

```console
python run_project.py demo
```

输出只演示这一个源码内置实例上的行为，不是关于任何实验语料的结论。

### `audit-stressors`

审计已提交的生成器扫描是否改变了预定的结构目标，同时暴露维度和
关联数混杂因素：

```console
python run_project.py audit-stressors
```

默认审计 `configs/p7_controlled_stressors.json`，打印 JSON，不运行
benchmark 算法。重复 `--config PATH` 可选择旧版或自定义配置；当总体隔离
检查失败应返回非零状态时加 `--strict`。指标与对照的语义见
[`generator_isolation.md`](generator_isolation.md)。

### `validate-config`

校验 JSON 形状、展开扫描并对算法做预检，不实际运行，也不创建输出目录：

```console
python run_project.py validate-config --config configs/p6_uniform_scale.json
```

### `benchmark`

只查看展开后的计划，不写输出：

```console
python run_project.py benchmark --config configs/p6_uniform_scale.json --dry-run
```

正式执行，独立的算法运行分配到多个 worker：

```console
python run_project.py benchmark --config configs/p6_uniform_scale.json --output results/p6_uniform_scale --workers 2
```

`raw_results.csv` 里已有的兼容行默认会被恢复续用。配置哈希和确定性的
运行标识必须与当前计划匹配。`--force` 删除该结果目录中 runner 自有的
产物并重跑全部计划标识；无关文件保持原样。

### `cartography`

这是跨结构、跨强度、跨算法的大范围补充扫描。当前单点研究检查点请用
上面的 pilot 命令。

在维度匹配的 uniform 对照下，按多个强度档位运行六个文档记载的压力因子族：

```console
python run_project.py cartography --config configs/structural_gap_cartography.json --design designs/structural_gap_cartography.json --output results/structural_gap_cartography --workers 4
```

`seed_group` 是 schema 3 的可选案例字段。同组案例在每次重复中使用相同的
实例生成种子；没有该字段的案例沿用历史上的案例索引种子方案。设计校验器
要求每个声明的压力因子/对照对共享非空的分组，且全集、候选数和预算维度
相等。分析在计算配对差之前还会再核对一次实际种子。

随机化算法的种子嵌套在实例种子之内。它们的差距先在实例内取平均，再计算
跨实例分布和配对区间，因此算法种子重复不算作独立实例。
用 `precision_diagnostics.csv` 判断配置的重复次数是否达到设计的置信区间
半宽目标。cartography runner 每完成 100 个新运行写一次检查点，结束时写出
完整的规范 CSV；中断后从最后一个完成的批次恢复。普通 benchmark 调用保持
默认的逐运行检查点间隔。使用 `--force` 时，cartography 自有的过期 CSV、
SVG、摘要和旧版 manifest 文件会在执行前被删除；输出目录里的无关文件保留。

运行完成后，可以从规范 benchmark 行独立重算 cartography 统计量：

```console
python .github/scripts/validate_cartography_output.py --config configs/structural_gap_cartography.json --design designs/structural_gap_cartography.json --output results/structural_gap_cartography
```

cartography 验证器直接对照 `raw_results.csv` 核对完整的计划运行身份、
cartography CSV 数值和布局。缺失的计划运行会被拒绝；已记录的错误和
不可得的差距仍计入报告中的缺失指标计数。benchmark 输出验证器为带最优
参考的已完成运行提供额外检查。

### `resume`

显式恢复一个中断的兼容检查点：

```console
python run_project.py resume --config configs/p6_uniform_scale.json --output results/p6_uniform_scale --workers 2
```

该命令跳过已完成的运行标识。改用 `--force` 则在同一输出目录下从头执行
配置计划。

### `summarize`

校验一份完整的规范检查点，并重建其类型化 CSV、Markdown 和 SVG 产物，
不运行任何算法：

```console
python run_project.py summarize --config configs/p6_uniform_scale.json --output results/p6_uniform_scale
```

计划行缺失、标识不符、实例不兼容或规范 CSV 输入畸形都会被拒绝。

### `replay`

用记录的算法回放一个序列化案例：

```console
python run_project.py replay --instance results/p6_uniform_scale/failures/<run-id>.json
```

用 `--algorithm NAME` 可指定替换算法。替换算法收到的是回放文件里记录的
选项，所以只有当该算法接受这份选项契约时替换才有效。例如，带时间限制的
精确求解器产物不能用 `greedy` 回放，因为 Greedy 拒绝精确求解器选项；
命令不会为替换算法重映射选项。文件中含有已记录结果时，覆盖量或选择
不一致会产生非零退出码。回放产物是自包含的，不会从生成器重新生成实例。

### `dashboard`

启动本地浏览器前端：

```console
python run_project.py dashboard
```

用 `--host` 和 `--port` 改回环地址或端口，非回环绑定会被拒绝。
Dashboard 读 `configs/`、写 `results/`，调用与 CLI 相同的校验、
benchmark、报告和回放函数。它没有账号、远程队列或托管执行。

点击“研究工作台”或打开同一服务的 `/workbench`，可搜索已有实验、并列比较完整
原始数据、查看 R1 选择轨迹并导出案例。它读取本项目 `results/` 与 `experiments/`，
描述性汇总与分页明细分开；不自动把相同种子当作配对。详见
[第一层研究工作台使用与验证](dashboard_workbench_layer1.zh-CN.md)。

首次打开可点击“选用入门示例”，确认运行规模后点击“运行实验”；选择示例本身不会启动计算。
如果已有结果，可直接点击“查看已有结果”。结果区先展示算法对照和指标解释，再提供图表与
可直接阅读的完整报告。结果选择器位于光谱和算法对照上方，可跳到对照、图表或回放。
优先恢复上次成功选择的结果；没有保存选择时按 CSV 产物更新时间选择最近可读结果。
刷新网页仍保留选择；旧目录已不存在或不可读取时会提示并尝试其他结果。结果时间指 CSV 文件
更新时间，不是实验完成时间。切换失败会清除旧展示，避免把上一份数据当作当前结果。
同名且兼容的运行会复用检查点；高级选项中的“重新计算全部任务”会忽略检查点并重建结果，
首次使用保持未勾选即可。入门示例用于熟悉操作，不代替正式研究结论。

开头按目的提供三种方案：先看懂算法差别（quick）、比较普通与惰性贪心（p3_lazy_greedy）、
观察长尾结构影响（p4_long_tail）。卡片只切换方案，不启动计算；选中后实时读取当前配置，
展示用途、实例数、算法运行次数与算法列表，再由用户点击运行。更大扫描及其他配置在
“自选方案”中选择；自选时同样保留预览和有效性检查，不将 full 文件名当作正式研究复现入口。

结果名称为 1–81 个字符，以英文字母或数字开头，其余可用英文字母、数字、点、下划线或短横线。
字段旁会提示非法输入，非法名称不会启动实验。最近任务状态与本次提交错误分开展示。

“已保存异常案例文件”对应运行超时或错误时保存的文件，不是贪心未达最优的次数。
回放默认列出当前结果的文件；“其他已保存案例”也能访问没有 CSV 报告的目录。
没有文件时回放控件禁用并说明原因。选择案例或结果后，上一案例的回放输出会清除。

完整报告在应用内以标题、段落、列表和表格展示，保留原文语言与结论限制；可返回结果并下载
原始 Markdown。展示支持项目生成报告使用的结构，其他语法保留为文本，不执行正文 HTML。
没有摘要段落时只提供完整报告入口，不额外生成结论。

## 输出验证

做种子配对分析时，每个输入目录各传一份配置。分析会先核对完整的运行
计划、生成的实例、算法选项、选中集合覆盖量以及最优值/差距一致性，
再计算差异：

```console
PYTHONPATH=src python -m maxcover.paired_seed_analysis --paired-config configs/pairing_paired.json --unpaired-config configs/pairing_unpaired.json --paired-results results/pairing-v1/paired --unpaired-results results/pairing-v1/unpaired --output results/pairing-v1/analysis
```

在 PowerShell 里先设 `$env:PYTHONPATH = "src"`，再运行以 `python` 开头的
命令。缺失的计划行会被拒绝；已记录的错误或缺失指标在分析计数中保持可见。
不需要 manifest。参考值来自最优精确运行的记录，或由配置实例重新生成的
证书；不可得的参考保持未知。这些检查不会重跑精确求解器。

对带最优参考的已完成运行，可以可选地从配置和 CSV 重算受支持的结果：

```console
python .github/scripts/validate_benchmark_output.py --config configs/p6_uniform_scale.json --output results/p6_uniform_scale
```

产物角色和状态语义见 [`output_schema.md`](output_schema.md)。
超时运行在存在 incumbent 时会带上它，但超时运行本身不能证明参考最优值。
经独立验证的实例证书，或同一实例的另一条精确运行，仍可为规范化分析
提供该参考。
