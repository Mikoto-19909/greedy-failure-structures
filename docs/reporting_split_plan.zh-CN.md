# 报告模块拆分计划

记录日期：2026-09-05。状态：待实施。

本计划以主分支 `ddf6a8a` 的实现为参照。文档存档不表示源码已经拆分。
实施前重新核对主分支和 benchmark 拆分的进度，以实际代码确定迁移位置。
贡献和检查要求沿用 [CONTRIBUTING](../CONTRIBUTING.md) 与 [AGENTS](../AGENTS.md)。

## 目标与边界

将 [reporting.py](../src/maxcover/reporting.py) 的 Markdown、SVG 和文件写入职责分开，
使调整一个报告章节时只需阅读对应函数。保留 `write_report_artifacts()` 的完整签名、
默认值和返回行为，以及现有报告文件名、章节顺序、格式和输出内容。

本次不调整统计方法、结论阈值、图表设计、标签翻译或报告措辞，不新增模板引擎、
绘图库、插件机制或配置层。排版改进留作后续有明确需求的变更。

## 文件与函数迁移

以下新增名称均为计划中的文件，放在 `src/maxcover/`，保持目录扁平。

| 目标文件 | 迁移内容 |
| --- | --- |
| `reporting.py` | 保留 `write_report_artifacts()`，按原顺序安排各产物的生成；私有调用方随迁移调整导入。 |
| `_report_markdown.py` | `_write_markdown()`、`_headline_lines()`、`_automatic_conclusion_status()`，以及从 Markdown 拼装中提取的章节函数。 |
| `_report_charts.py` | `_bar_chart()`、`_write_gap_chart()`、`_write_runtime_chart()`、全部 `_render_*` 函数、`_association_chart_rows()` 和 `ChartRow`。 |
| `_report_labels.py` | `COLORS`、现有标签和参考状态颜色映射、`_readable_identifier()` 及各标签转换函数。 |

入口模块调用 Markdown 和图表模块；两者读取标签模块。
子模块直接导入配置或记录类型，不反向导入 `reporting.py`。
`_REFERENCE_STATUS_LABELS` 被 Markdown 和图表共同使用，放入标签模块，避免复制两份。

## 实施步骤

### 1. 冻结比较基线

1. 在干净基线上记录 commit，列出 `reporting` 的导出、调用方和写出的产物集合。
2. 使用固定的类型化记录建立报告输入。可以从一次小型运行的 `BenchmarkResult`
   提取参数后固定下来；之后比较时只调用报告函数，不再运行算法。
3. 固定 `config_path` 的绝对值，因为它会写入 Markdown。固定所有时间、统计值、
   记录顺序和可选序列；输出目录可以不同。
4. 在 `results/` 下保存修改前的 Markdown/SVG 及输入，作为本次迁移的比较基线。
   补充主路径中没有覆盖的空样本、缺少参考值、结论暂缓和关联不可估计输入。

基线必须来自修改前的实现，不能在拆分后用同一个新实现生成期望值。
这些开发检查不是研究结果，不进入 `experiments/core_rq/` 或研究结论清单。

### 2. 先搬迁，再分解长函数

先原样移动标签、图表与 Markdown 函数，并接好导入。
此阶段保持函数体和调用顺序，先完成一次输出比较。

随后在 `_report_markdown.py` 内提取章节函数：

| 函数建议名 | 覆盖内容 |
| --- | --- |
| `_descriptive_section()` | 描述统计表及对应说明。 |
| `_reference_section()` | 参考最优值状态、覆盖、删失偏差与截断敏感性。 |
| `_quality_section()` | Greedy 失败、局部搜索恢复、剩余 gap 和 Pareto。 |
| `_runtime_section()` | 时间比、节点缩减、置信区间和删失运行时间中相应的展示段落。 |
| `_association_section()` | gap 与结构，以及运行时间、节点数关联的展示段落。 |

上述是职责分组，不是重新安排章节顺序。若原有段落交错，按原顺序提取更小的函数，
例如单独的 `_confidence_interval_section()`；不把交错的章节强行合并后搬到另一处。
章节函数只接收所需记录并返回 `list[str]`，不写文件、不重算统计、不修改输入。
`_write_markdown()` 保留原入口参数，负责依次拼接与一次写入。
章节作为函数维护，不为每张表再建模块。

### 3. 调整调用方，保留公开入口

[benchmark.py](../src/maxcover/benchmark.py) 继续从 `maxcover.reporting`
导入 `write_report_artifacts()`。
[输出验证脚本](../.github/scripts/validate_benchmark_output.py) 目前导入
`_headline_lines` 和多个 `_render_*`，这些是内部依赖，应在本次迁移中更新到实际定义模块。
公开的 `write_report_artifacts()` 保持兼容，私有名称不承诺永久留在旧文件。
若并行分支确实需要短期过渡，可保留必要的显式导出，并在调用方迁移后删除；
不为过渡导出新增永久布局测试，也不增加转发包装或动态属性代理。

完成后搜索实际调用点：

```console
rg -n 'maxcover.reporting|from \.reporting|reporting\.' src tests .github
```

本次只调整验证器中受影响的导入，函数分解留给
[验证脚本计划](output_validation_split_plan.zh-CN.md)。
若 benchmark 已经拆分，只修改实际调用所在模块，避免恢复旧布局。

### 4. 收紧文档测试，明确类型覆盖

随文档精简删除中英文 README、CONTRIBUTING 中不再需要展示的源码文件数、
豁免代码行数占比和带固定文件数的 mypy 成功输出，并同步删除
[test_documented_claims.py](../tests/test_documented_claims.py) 中的
`test_the_documented_share_matches_the_measured_share`、
`test_the_documented_file_count_matches_what_mypy_checks` 及仅供它们使用的辅助代码。
若相关文档精简已合并，直接沿用，不重复修改或恢复数字。

对章节、措辞和模块清单测试逐项判断：保留公开命令、链接可达性和实际覆盖说明等事实，
放开固定标题层级、逐字措辞和纯内部布局。现有“文档中出现的全部模块名恰等于豁免集合”
与“含有函数定义就表示存在类型错误”的断言不适合作为事实证明，
应收窄到真正需要维护的声明或随被删除的声明一起移除。
算法结果、确定性、CSV 字段、公开接口和错误拒绝测试保持。
生成报告的固定输入输出比较保护的是产物行为，不用于冻结开发文档的章节布局。

现有 `maxcover.benchmark` 和 `maxcover.reporting` 设置整模块 `ignore_errors = true`，
mypy 通过不能说明它们没有类型错误。新模块默认进入检查，先实际检查迁移后的代码。
必要的遗留类型修复单独提交；暂时无法解决的问题只采用有具体原因的最小抑制，
不批量复制整模块豁免，不扩大到新包，也不把清理全仓类型错误作为拆分前置条件。
准确说明覆盖边界，并指向 [pyproject.toml](../pyproject.toml) 查看现行例外；
移除已无必要的豁免，检查结果仅说明实际受检查的范围。
新增文件和受影响文档按现行要求更新许可证清单，迁移历史清单保持原样。

## 验证与完成条件

在已有测试中补充缺失的报告行为检查；若需要独立测试文件，使用 `tests/test_reporting.py`。
只保留能检查内容、顺序、空值和兼容入口的测试，不断言内部函数数量或文件行数。

针对性检查命令从仓库根目录运行：

```console
python -m unittest discover -s tests -p 'test_benchmark.py' -v
python -m unittest discover -s tests -p 'test_reference_coverage.py' -v
python -m unittest discover -s tests -p 'test_output_validation.py' -v
python -m unittest discover -s tests -p 'test_fault_injection.py' -v
python -m unittest discover -s tests -p 'test_documented_claims.py' -v
```

完成条件：

- 同一固定输入在旧、新实现下产生相同产物集合，每个 Markdown/SVG 文件字节相同。
- 空值、不可估计和暂缓结论路径都有比较，不能只检查正常图表。
- 公开入口与参数兼容，仓库内私有调用方已迁移；导入不产生循环依赖。
- 原有有效输出仍通过验证，已有故障输入的处理结果没有变化。
- 实际运行 AGENTS 要求的完整测试、内容边界、许可证和 mypy 检查，并记录结果。
- 增减内部文件或正常调整开发文档时，不再为源码数字、措辞或旧私有布局修改测试；行为退化仍会失败。

## PR 与停止条件

作为一个报告拆分 PR，内部按“冻结基线 → 原样搬迁 → 提取章节 → 连带更新”提交。
PR 描述记录基线 commit、比较输入范围及检查结果，不把拆分写成研究进展。
任一输出差异先定位到具体章节或图表；无法解释为测试环境差异时，恢复对应迁移步骤，
不更新期望结果来接受变化。合并后回退通过回退该 PR，不改写已有实验产物。

满足完成条件即结束。该计划可独立实施，不依赖生成器或 contracts 拆分完成。
实施完成时只在本文件补充 PR 链接和实际范围。
