# Maximum Coverage Study

[English](README.md) | **简体中文**

本仓库包含面向研究的 Python 代码，用于对最大覆盖（Maximum Coverage）问题进行确定性实验。项目提供算法实现、实例生成器、配置校验、基准测试执行、报告以及重放工具。

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

显示一个小型确定性示例：

```console
python run_project.py demo
```

该命令会构造一个在源码中定义的固定实例，并打印各个算法在该实例上的返回结果，包括覆盖差距（coverage gap）。这些数字由你的机器根据这个硬编码实例现场计算得出。它们用于演示贪心算法可能陷入失败结构；它们不是对任何语料或实验集合的测量结果，本仓库也不会把它们作为研究结果发布。参见[范围](#范围)。

运行入门工作流：

```console
python run_project.py quick
```

在不执行基准测试的情况下校验配置：

```console
python run_project.py benchmark --config configs/sweeps.json --dry-run
```

运行配置好的基准测试并写入本地输出：

```console
python run_project.py benchmark --config configs/full.json --output results/full
```

上面两个命令都会产生一个 `LegacyConfigWarning`：`configs/quick.json` 和 `configs/full.json` 使用 schema v1，加载器会在每次运行时于内存中将它们迁移到 schema 3。这个警告是预期行为。这两个文件会刻意保留在 v1，而不会直接重写——因为 `config_hash` 是基于规范化后的配置计算的，重写文件会改变该哈希，并使已经依据它记录的运行身份失去对应关系；`CONTRIBUTING.md` 将这种变化归类为破坏性变更。`configs/sweeps.json` 使用 schema 2；`configs/p3_*` 到 `configs/p5_*` 的配置使用 schema 3，因此不会产生警告。

`results/` 下生成的文件都是本地产物，不属于仓库快照的一部分。

在不依赖输出自身校验和的情况下验证已完成的运行：

```console
python .github/scripts/validate_benchmark_output.py --config configs/quick.json --output results/quick
```

`manifest.json` 带有校验和，验证该校验和可以证明文件在写出后没有被修改。但它无法证明文件最初就是正确生成的——如果一次运行错误地计算了某个统计量，其输出仍然可能拥有完全匹配的校验和。这个验证器会重新读取产物，并仅根据配置重新计算它们所声称的数据；只要出现任何不一致就以非零状态退出。CI 会在每次入门工作流完成后运行该验证器。

## 测试

```console
python -m unittest discover -s tests -v
```

也可以运行类型检查器：

```console
python -m pip install -e ".[typecheck]"
python -m mypy
```

需要谨慎理解它的输出。`pyproject.toml` 对 `maxcover.benchmark` 和 `maxcover.reporting` 设置了 `ignore_errors = true`——按源码行数计算，这两部分大约占 40%。因此，`Success: no issues found in 19 source files` 的含义只是其余模块通过了检查，而不是整个包都没有类型问题。这两个模块确实还存在尚未解决的类型错误积压；保留豁免可以让其他区域的类型检查继续保持可执行和可强制，而不是让整个检查长期处于红灯状态。欢迎逐步减少这部分积压，豁免列表就是确认当前哪些模块尚未纳入覆盖范围的位置。

在 Windows 上，可以使用便捷包装脚本执行等价命令：

```powershell
./project.ps1 test
./project.ps1 typecheck
./project.ps1 quick
```

## 可复现性说明

- 使用已提交的配置文件和显式随机种子。
- 在诊断运行时，将全新执行与恢复执行分开处理。
- 将超时视为未完成的工作，而不是最优性的证明。
- 运行时间相关观察可能随机器和可选求解器而变化。
- 入门工作流属于功能检查，不构成性能声明。

## 范围

这是一个以代码为中心的快照。它发布可运行代码、测试和配置，但**不发布任何定量研究结论**：不发布实验结果、不发布性能比较、不发布测量数据。这是一个有意设定的边界，而不是遗漏——具体规则见 [`CONTRIBUTING.md`](CONTRIBUTING.md)，本仓库建立之前的开发情况见 [`docs/history/PRE_PUBLIC_DEVELOPMENT_HISTORY.md`](docs/history/PRE_PUBLIC_DEVELOPMENT_HISTORY.md)。

这里的边界针对的是本仓库“发布什么”。这一点值得明确，因为代码本身确实会计算数字。`demo` 会打印覆盖差距，基准测试也会把包含测量数据的 CSV 文件写入 `results/`。但它们都没有越过上述边界：这些结果是在你的机器上运行时，根据本仓库提交的输入现场生成的；它们既没有被提交到仓库，也没有被当作研究发现加以断言。这个边界真正排除的是“由仓库本身承载的结论”——例如 README 中的结果图、文档中的结果表，或被纳入版本控制的实验结果语料。任何此类内容都必须具备 [`CONTRIBUTING.md`](CONTRIBUTING.md) 所描述的冻结证据链，并且 CI 会对每一个被跟踪的文件执行该规则，而不是仅依赖约定。

## 项目结构

- `src/maxcover/`：算法、生成器、基准测试执行与报告
- `configs/`：可复现的实验配置
- `tests/`：确定性的单元测试与契约测试
- `run_project.py`：主要命令行入口
- `project.ps1`：Windows 便捷包装脚本
- `LICENSE_MANIFEST.json`：封闭的许可证允许列表，由 CI 校验
- `PUBLIC_SNAPSHOT_MANIFEST.json`：创建本仓库时那次一次性导出的迁移归档
- `docs/history/`：迁移来源说明与公开前开发历史

## 贡献与支持

- [`CONTRIBUTING.md`](CONTRIBUTING.md)：范围、基本规则以及如何提交贡献
- [`AGENTS.md`](AGENTS.md)：供 AI 编码代理使用的额外约束
- [`SECURITY.md`](SECURITY.md)：哪些问题属于安全问题，以及如何报告
- [`SUPPORT.md`](SUPPORT.md)：本项目会回答和不会回答的问题范围

## 许可证

代码使用 MIT License。该快照中的文档和其他非代码内容使用 Creative Commons Attribution 4.0。封闭的逐文件许可证映射见 [`LICENSES/README.md`](LICENSES/README.md)。
