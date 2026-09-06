# Maximum Coverage Study

[English](README.md) | **简体中文**

本项目研究最大覆盖（Maximum Coverage）实例结构与贪心算法（Greedy）最优性差距的关系：
贪心解的覆盖量比精确最优值少多少。项目提供算法、实例生成器和可复现实验工具。

## 当前研究

已完成的试验使用 Greedy 与穷举参考，比较共核式 `high_overlap` 实例和维度、
期望集合大小匹配的 `uniform` 对照。本轮未获得足够的失效率差异证据；报告保留
观察到的方向，并列出两种生成机制之间的其他结构差异。结果对应
[实验数据](experiments/core_rq/overlap_pilot_v1/)。

可直接阅读[试验报告](analysis/overlap_pilot_v1.md)，从
[研究索引](analysis/README.md)了解进展，或查看
[实验配置与数据](experiments/core_rq/overlap_pilot_v1/)。

## 最短运行方式

基础包需要 Python 3.11 或更高版本，没有第三方运行依赖。在仓库根目录执行：

```console
python -m pip install -e .
python run_project.py quick
```

`quick` 用于检查安装和示例输出流程。保留配置使用较旧的 schema，因此出现
`LegacyConfigWarning` 属于预期行为。[CLI 指南](docs/cli.md)集中说明配置兼容、
完整命令、可选 OR-Tools 安装和输出验证。

省略 CLI 命令或不带参数运行 PowerShell 包装脚本，都会执行 quick。
Dashboard 在没有保留配置选择时也优先选择 `quick.json`。这些默认入口用于示例流程。

## 按用途选择

| 用途 | 入口 |
| --- | --- |
| 当前研究 | [固定试验命令](docs/cli.md#core-overlap-pilot)、[报告](analysis/overlap_pilot_v1.md)和[原始设计](docs/core_overlap_checkpoint_plan.zh-CN.md)。 |
| 演示与兼容验证 | `python run_project.py demo`、`quick`，以及 CLI 指南中的较大旧版 `full.json` 工作流。`full` 这一名称不表示当前研究的完整方案。 |
| 方法检查与更广探索 | [文档索引](docs/README.md)区分配对检查、生成器审计、功能检查和较大的结构扫描。 |

试验的离线绘图需要 Matplotlib。其他可选算法和配置保留其原有用途；不能仅凭阶段
前缀将配置归为历史。

## 本地 Dashboard

```console
python run_project.py dashboard
```

打开命令打印的本地地址，可校验配置、启动或恢复运行、查看产物和回放实例。
界面支持中英文，使用与 CLI 相同的实验引擎。服务器绑定回环地址；运行边界见
[Dashboard 命令](docs/cli.md#dashboard)和[安全说明](SECURITY.md)。

## 读取输出与验证

使用[输出 schema](docs/output_schema.md)理解 CSV 和报告，使用
[复现指南](docs/reproducibility_matrix.md)区分稳定结果与可能变化的运行时间、环境字段。
可选验证器直接从配置与 CSV 重算结果；CLI 指南说明其检查范围。

运行测试：

```console
python -m unittest discover -s tests -v
```

[CONTRIBUTING.md](CONTRIBUTING.md#verification)集中维护完整检查命令和实际 mypy
覆盖范围。Windows 用户也可使用 `./project.ps1 test`、
`./project.ps1 typecheck` 和 `./project.ps1 quick`。

## 范围

`demo` 打印本地计算的覆盖量，benchmark 将测量结果写入 `results/`。
完整探索输出留在本地；研究报告位于 `analysis/`，直接链接
`experiments/core_rq/` 中的配置和数据。保留种子、原始结果和分析脚本，
不再要求结论台账、manifest 或文件摘要。研究流程见 CONTRIBUTING。

## 文档与支持

- [文档索引](docs/README.md)、[英文 FAQ](docs/faq.md)和[中文 FAQ](docs/faq.zh-CN.md)。
- [结构机制](docs/failure_mechanisms.md)与[Lazy Greedy 功能报告](docs/lazy_greedy_test_report.md)。
- [贡献规则](CONTRIBUTING.md)、[额外代理执行约束](AGENTS.md)、[支持说明](SUPPORT.md)和[安全报告渠道](SECURITY.md)。

代码使用 MIT 许可证，文档及其他非代码内容使用 CC BY 4.0。
包括第三方例外在内的内容类别归属见[许可证映射](LICENSES/README.md)。
