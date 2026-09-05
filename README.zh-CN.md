# Maximum Coverage Study

[English](README.md) | **简体中文**

本仓库研究最大覆盖（Maximum Coverage）实例结构与贪心算法（Greedy）最优性差距的关系：
贪心解的覆盖量比精确最优值少多少。项目提供 Python 算法、实例生成器，以及运行和
检查可复现实验的工具。

## 当前研究

下一项研究是：在维度与期望集合大小匹配时，共核式 `high_overlap` 生成器是否比
`uniform` 对照更容易让 Greedy 失手？计划在一个固定参数点比较 Greedy 与穷举参考。
这项设计尚不能将重叠度与生成机制带来的其他结构差异完全分离。

**状态：实现已准备，正式实验待运行。**
[固定配置](configs/core_overlap_pilot.json) 与
[离线分析脚本](analysis/core_overlap_pilot.py) 已按
[执行计划](docs/core_overlap_checkpoint_plan.zh-CN.md) 实现。
准备代码提交后，按[试验命令](docs/cli.md#core-overlap-pilot)在干净的固定版本上正式运行。

[研究分析入口](analysis/README.md) 记录当前进展。公开发现形成后，通过
[核心结论台账](experiments/core_rq/CLAIMS.md) 查找对应证据。

## 环境要求

- Python 3.11 或更高版本
- 基础包不依赖第三方库
- 仅在需要可选的精确求解器时使用 OR-Tools

## 安装

```console
python -m pip install -e .
```

如需安装可选的精确求解器：

```console
python -m pip install -e ".[oracle]"
```

## 运行

按用途选择入口：

| 用途 | 入口 |
| --- | --- |
| 当前研究 | [固定高重叠试验](docs/cli.md#core-overlap-pilot)；实现已准备，正式实验待运行。 |
| 演示与兼容验证 | 下方的 `demo`、`quick` 与较大的旧版 `full.json` 工作流。 |
| 历史探索与附录 | [补充工作流索引](docs/README.md#historical-exploration-and-appendices)，包括较大的结构扫描与附加算法比较。 |

### 演示与兼容验证

查看 Greedy 在一个固定对抗实例上的选择：

```console
python run_project.py demo
```

这些值由本机根据源码中的固定示例计算得出。示例输出与公开研究发现的区别见[范围](#范围)。

运行小型入门基准测试，检查安装和输出流程：

```console
python run_project.py quick
```

CLI 省略命令时也运行 `quick`，PowerShell 包装脚本默认执行相同动作。
仪表盘（Dashboard）没有保留的配置选择时，初始优先选择 `quick.json`。
这些默认入口进入的是示例工作流。

查看 quick 的执行计划，不运行算法：

```console
python run_project.py benchmark --config configs/quick.json --dry-run
```

需要检查兼容性或重新查看多实例族的既有实验时，运行较大的旧版工作流：

```console
python run_project.py benchmark --config configs/full.json --output results/full
```

`full` 指这套已有工作流，不代表当前研究的完整方案。
`configs/quick.json` 和 `configs/full.json` 使用 schema v1，加载器在内存中迁移到
schema 3；因此产生的 `LegacyConfigWarning` 是预期行为。
这些文件继续用于旧版兼容和既有工作流复现。

验证已经完成的 quick 运行：

```console
python .github/scripts/validate_benchmark_output.py --config configs/quick.json --output results/quick
```

验证器检查其支持的产物关系和已记录的校验和。校验和一致只说明文件与记录的哈希
一致，不能证明最初的计算正确。生成的输出继续保存在本地 `results/`。

[惰性贪心（Lazy Greedy）功能工作流](configs/p3_lazy_greedy.json) 也用于 CI 检查，
具体步骤见[功能测试报告](docs/lazy_greedy_test_report.md)。

### 历史探索与附录

已有配置继续按各自用途使用。`configs/sweeps.json` 使用 schema 2；
`configs/p3_*` 到 `configs/p7_*` 的配置使用 schema 3。
版本标签不表示下一步应该运行哪项实验。

较大的结构扫描见 [cartography（结构差距制图）命令](docs/cli.md#cartography)。
旧版[重叠参数扫描](configs/p6_overlap_scan.json) 和[完整配置目录](configs/)
可用于进一步探索，不能直接替代前述固定参数试验。

带阶段前缀的配置并非全部属于历史：`p3_lazy_greedy.json` 用于 CI 检查，
`p7_controlled_stressors.json` 用于生成器审计，配对配置用于随机种子配对方法检查。
相应流程见[文档索引](docs/README.md)，完整命令见 [CLI 使用说明](docs/cli.md)。

## 测试

```console
python -m unittest discover -s tests -v
```

也可以运行类型检查器：

```console
python -m pip install -e ".[typecheck]"
python -m mypy
```

需要谨慎理解它的输出。`pyproject.toml` 对 `maxcover.benchmark` 和 `maxcover.reporting` 设置了 `ignore_errors = true`——按源码行数计算，这两部分大约占 40%。因此，`Success: no issues found in 23 source files` 的含义只是其余模块通过了检查，而不是整个包都没有类型问题。这两个模块确实还存在尚未解决的类型错误积压；保留豁免可以让其他区域的类型检查继续保持可执行和可强制，而不是让整个检查长期处于红灯状态。欢迎逐步减少这部分积压，豁免列表就是确认当前哪些模块尚未纳入覆盖范围的位置。

在 Windows 上，可以使用便捷包装脚本执行等价命令：

```powershell
./project.ps1 test
./project.ps1 typecheck
./project.ps1 quick
```

启动本地实验 dashboard：

```console
python run_project.py dashboard
```

然后在浏览器中打开命令行打印的本地地址。dashboard 可以校验配置、启动或
恢复 `results/` 下的 benchmark、浏览生成的 CSV/报告产物，以及 replay 序列化
的 failure instance。它只是复用 CLI 所使用的同一套本地引擎，不提供账号、远程
执行或托管服务；如果需要改变默认绑定，请给 `dashboard` 命令传入另一个回环地址
的 `--host` 和 `--port`；非回环绑定会在启动时拒绝，因为状态变更请求刻意只允许
本机访问。
浏览器界面提供中文/英文切换按钮，动态的运行状态、结果和回放状态也会随语言切换。

## 可复现性说明

- 使用已提交的配置文件和显式随机种子。
- 在诊断运行时，将全新执行与恢复执行分开处理。
- 将超时视为未完成的工作，而不是最优性的证明。
- 运行时间相关观察可能随机器和可选求解器而变化。
- 入门工作流属于功能检查，不构成性能声明。

## 审查公开研究结论

请先阅读面向外部的[研究分析](analysis/README.md)。每个 claim ID 与结果行、配置、
manifest 和验证记录之间的权威映射位于
[核心结论台账](experiments/core_rq/CLAIMS.md)。这两个文档当前均未发布定量研究结论。

## 范围

这是一个以代码为中心的仓库，同时允许发布少量经过验证的核心研究结论。完整 benchmark 输出继续保存在本地的 `results/` 下。公开结论所需的最小冻结证据放在 `experiments/core_rq/`，面向外部的研究叙述放在 `analysis/`；发布规则见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

区分本地输出和公开结论很重要，因为代码本身会持续计算数字。`demo` 会打印覆盖差距，benchmark 也会把测量 CSV 写入 `results/`，但这些本地输出不会自动成为公开发现。被跟踪的定量陈述只有通过 claim ledger、冻结证据和已记录的独立验证后，才构成公开结论。CI 允许这类文字通过，但不会证明人工维护的证据映射正确。

## 项目结构

- `src/maxcover/`：算法、生成器、基准测试执行与报告
- `src/maxcover/dashboard.py` 和 `src/maxcover/dashboard_ui/`：本地 dashboard
  服务及浏览器前端
- `configs/`：可复现的实验配置
- [`experiments/core_rq/CLAIMS.md`](experiments/core_rq/CLAIMS.md)：公开结论、冻结证据与验证记录之间的权威映射
- [`analysis/README.md`](analysis/README.md)：面向外部的研究分析入口
- `tests/`：确定性的单元测试与契约测试
- `run_project.py`：主要命令行入口
- `project.ps1`：Windows 便捷包装脚本
- `LICENSE_MANIFEST.json`：封闭的许可证允许列表，由 CI 校验
- `PUBLIC_SNAPSHOT_MANIFEST.json`：创建本仓库时那次一次性导出的迁移归档
- [`docs/README.md`](docs/README.md)：文档索引与范围说明
- [`docs/cli.md`](docs/cli.md)：完整命令行工作流
- [`docs/output_schema.md`](docs/output_schema.md)：生成产物的语义说明
- [`docs/failure_mechanisms.md`](docs/failure_mechanisms.md) 和
  [`docs/faq.md`](docs/faq.md)：结构机制说明与项目常见问题
- [`docs/faq.zh-CN.md`](docs/faq.zh-CN.md)：简体中文 FAQ，与英文版本逐节同步维护
- `docs/history/`：迁移来源说明与公开前开发历史
- [`docs/lazy_greedy_test_report.md`](docs/lazy_greedy_test_report.md)：
  lazy-greedy 功能验证流程

## 贡献与支持

- [`CONTRIBUTING.md`](CONTRIBUTING.md)：范围、基本规则以及如何提交贡献
- [`AGENTS.md`](AGENTS.md)：供 AI 编码代理使用的额外约束
- [`SECURITY.md`](SECURITY.md)：哪些问题属于安全问题，以及如何报告
- [`SUPPORT.md`](SUPPORT.md)：本项目会回答和不会回答的问题范围

## 许可证

代码使用 MIT License。该快照中的文档和其他非代码内容使用 Creative Commons Attribution 4.0。封闭的逐文件许可证映射见 [`LICENSES/README.md`](LICENSES/README.md)。
