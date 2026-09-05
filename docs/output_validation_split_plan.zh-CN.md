# 输出验证脚本整理计划

记录日期：2026-09-05。状态：待实施。

本计划以主分支 `ddf6a8a` 的实现为参照。PR #21 的 `4ba3b74` 涉及配对分析，
本次核对时仍属未合并参考；实施前重新确认状态，不能视为主分支已有行为。
贡献和检查要求沿用 [CONTRIBUTING](../CONTRIBUTING.md) 与 [AGENTS](../AGENTS.md)。

## 目标与边界

分解 [validate_benchmark_output.py](../.github/scripts/validate_benchmark_output.py)
中的长 `validate()`，使每种失败能定位到一组检查。
第一轮只在原文件内提取函数，保留脚本路径、`validate(config_path, output)`、
`main()`、命令行参数、成功和失败状态，以及有明确约定的错误类型和参数路径。

整理不新增验证规则、不修补现有盲点、不改变 schema、容差、记录顺序或缺失值处理。
发现独立缺陷时记录输入与现象，作为另一个修复处理。
本轮在报告和 benchmark 拆分完成、导入边界稳定后实施；总顺序见
[实施计划索引](README.md#implementation-plans)。所有源码拆分之前先完成 benchmark B0。

## 函数边界

保留 `_fail()`、`_load_records()`、manifest 基础检查、运行身份检查和 Lazy Greedy
重放等已有函数。新增函数只接收其使用的配置、manifest 或类型化记录。

| 提取单元 | 来源与职责 |
| --- | --- |
| manifest 声明检查函数 | 将 `validate()` 内每个 `expected_*_contract` 及紧邻的比较语句一起移出，按现有契约命名，例如 `_validate_confidence_interval_contract()`。 |
| `_validate_record_consistency()` | 原始记录的数量、重复、身份、配置哈希、状态与分组一致性。 |
| `_validate_basic_statistics()` | 原始记录规范化、描述统计、置信区间与删失运行时间的现有比较；按原数据依赖决定是否继续细分。 |
| `_validate_reference_statistics()` | 参考状态、覆盖、删失偏差与截断敏感性。 |
| 质量、关联结果检查函数 | 按当前连续代码块提取恢复、失败、时间比、节点缩减、Pareto 和关联记录比较。 |
| `_validate_report_headlines()` / `_validate_report_charts()` | 既有 Markdown 指定章节与图表重建比较。 |

第一阶段以连续代码块为迁移单位，沿用原检查顺序以降低搬迁风险。
当前部分报告检查与质量统计检查交错，提取时先保持位置；后续可以在证明数据依赖和
拒绝能力未变的情况下调整顺序。内部检查次序本身不新增为永久兼容承诺。
manifest 声明按各自契约提取，避免新建另一个装下全部声明的巨型函数。
一次性变量留在使用处；多个阶段共享的记录由 `validate()` 加载并显式传入。
不创建混装所有状态的字典、验证上下文框架、检查注册器或插件接口。

## 实施步骤

### 1. 保存现有接受与拒绝行为

记录旧版 commit，用已有输出验证测试的 fixture 建立有效输出目录。
复用 [test_output_validation.py](../tests/test_output_validation.py)、
[test_fault_injection.py](../tests/test_fault_injection.py) 中的损坏方式，
保存旧验证器的退出码、标准输出和标准错误用于定位差异。
比较旧、新验证器时使用同一配置与产物路径；验收重点是接受与拒绝行为及必要错误信息，
不将所有诊断措辞或多故障时首先出现哪条消息都冻结成测试要求。

最少覆盖以下真实边界：

| 输入 | 对比目标 |
| --- | --- |
| 有效输出 | 接受，成功退出。 |
| 缺失或损坏的 manifest、CSV | 拒绝，错误类别和必要文件定位清楚。 |
| schema 或 manifest 声明错误 | 拒绝，有约定的错误类型与路径保持。 |
| 重复运行身份、错误统计值、Lazy Greedy 计数器篡改 | 保留当前已有的拒绝能力。 |
| 刷新校验和后的统计或图表篡改 | 继续触发相应语义检查，不能仅靠旧校验和失败。 |
| 两处同时损坏 | 仍然拒绝，不能因阶段提取、提前返回或异常处理遗漏而通过；不额外锁定一般首报顺序。 |
| 测试中已标记的盲点 | 如实保留当前接受或拒绝结果，不把重构混成规则修复。 |

基线数据保存在 `results/` 或临时目录，不成为研究证据。
复用已有测试覆盖，仅为重构暴露出的拒绝行为缺口增加少量回归测试。
若某项先后关系承担数据可信边界，应保留并验证该关系，例如按当前要求完成必要的
manifest 基础检查后再使用相应元数据；将原因写清，而不是冻结全部内部调用顺序。

### 2. 按原顺序提取 manifest 声明

将每份预期声明及比较原样放入对应函数，在原位置调用。
保留字典键、值、错误信息和比较方式，包括现有类型判断的强弱边界。
manifest 文件及哈希检查仍在原位置执行。
各预期声明继续由验证侧维护，不从写入器导入同一份对象作为期望值。

### 3. 提取记录与产物检查

按函数边界表逐个提取，完成一个阶段即运行相关拒绝测试。
保留 `_load_records(..., allow_empty=...)` 对每类文件的原参数。
规范化和复算使用原算法、输入和顺序，不更换排序键、不调整容差。
函数局部使用所需类型，不增加全局可变状态。

第一轮完成后，脚本仍可被现有 `importlib` 测试加载，也可由命令行直接运行。
没有必要为了行数继续新增 `.github/scripts/` 子包或修改 Python 搜索路径。

### 4. 对齐相邻拆分的导入

通过以下搜索列出依赖和动态加载点：

```console
rg -n 'maxcover.benchmark|maxcover.reporting|validate_benchmark_output|spec_from_file_location' .github tests src
```

若报告拆分已实施，沿用迁移后的实际导入。若本次需要更换私有导入位置，
同步修改调用方并运行整个验证器测试集，不为旧位置建立永久兼容要求。
benchmark 的私有统计导入及测试替换入口按
[B0 兼容清单](benchmark_modularization_plan.md#compatibility-ledger) 在本轮保留，
不能套用报告私有路径的迁移规则。公开接口始终保持兼容。

本验证器复用了生产统计和绘图函数。整理后仍只能说明已有检查范围，
不能声称重新独立实现了统计或求解器验证。
涉及说明文字时，同步修正脚本 docstring 与
[输出语义文档](output_schema.md) 中实际受影响的引用。

文档测试与类型覆盖遵循 [报告拆分计划](reporting_split_plan.zh-CN.md) 的收口方式：
删除无必要源码数字及配套检查，保留实际行为和必要覆盖说明。
本项通常不新增 `src` 模块；若有确切理由迁入新模块，新模块默认接受 mypy 检查，
不继承 benchmark/reporting 的整模块豁免，遗留类型修复单独提交。

## 验证与完成条件

从仓库根目录运行：

```console
python -m unittest discover -s tests -p 'test_output_validation.py' -v
python -m unittest discover -s tests -p 'test_fault_injection.py' -v
python -m unittest discover -s tests -p 'test_lazy_greedy.py' -v
python -m unittest discover -s tests -p 'test_compare_matrix_outputs.py' -v
```

完成条件：

- 同一有效、损坏和多故障输入的接受与拒绝结果、退出码及必要错误类型或路径保持兼容。
- CLI、直接函数调用、现有动态导入三种入口均可用。
- `allow_empty`、必要先验检查、规范化与比较规则保持一致；测试不额外冻结纯内部调用布局。
- 生产写入逻辑和验证预期声明保持各自维护；未以共享声明削弱现有检查。
- 运行 AGENTS 要求的完整测试、内容边界、许可证和 mypy 检查，并报告实际范围。
  默认 mypy 面向 `src/maxcover`，通过不能表述为本脚本已经受完整类型检查。

## PR 与停止条件

作为一个独立 PR，按“行为基线 → manifest 函数提取 → 记录与产物函数提取 → 导入调整”提交。
本项涉及验证代码，实施时按 AGENTS 从声明构造反例并进行独立审查，
不要只以重构者自己的测试作为合并依据。

若原先拒绝的坏输入通过，或公开错误约定受损，先恢复对应提取步骤；
仅诊断措辞或一般首报顺序变化时，核对依赖后处理，不自动视为兼容破坏。
若发现需要改规则才能继续，另开缺陷修复。合并后回退通过回退该 PR，不修改历史产物来适配代码。
完成函数分解和兼容检查后停止，不因文件仍长而继续建设验证框架。
实施完成时只在本文件补充 PR 链接和实际范围。
