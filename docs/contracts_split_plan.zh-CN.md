# 统计与关联记录拆分计划

记录日期：2026-09-05。状态：待实施，优先级后置。

本计划以主分支 `ddf6a8a` 的实现为参照。实施前重新核对入口和调用关系。
贡献和检查要求沿用 [CONTRIBUTING](../CONTRIBUTING.md) 与 [AGENTS](../AGENTS.md)。

## 目标与边界

将 [_statistics_contracts.py](../src/maxcover/_statistics_contracts.py) 和
[_association_contracts.py](../src/maxcover/_association_contracts.py) 按记录用途分组，
使基础统计、解质量、运行性能和结构关联的定义各有明确位置。
记录类本身已经有边界，本计划只在实际需要维护这些类型时启动。

公开入口仍为 [maxcover.contracts](../src/maxcover/contracts.py) 及当前包根导出。
字段、字段顺序、默认值、`CSV_FIELDS`、schema 常量、CSV 解析、异常、不可变性、
pickle 与多进程行为保持原样。不引入通用基类、序列化框架、动态类生成或新 schema。
`_instance_contracts.py` 等其他记录模块不在本次拆分范围内。

## 类型迁移表

以下新增名称均为计划中的文件，放在 `src/maxcover/`。

| 目标文件 | 保留或迁入的类 |
| --- | --- |
| `_statistics_contracts.py` | `DescriptiveStatisticsRecord`、`ConfidenceIntervalRecord`、`CensoredRuntimeRecord`。 |
| `_quality_contracts.py` | `GreedyFailureRecord`、`LocalSearchRecoveryRecord`、`LocalSearchRemainingGapRecord`、`QualityRuntimeParetoRecord`。 |
| `_performance_contracts.py` | `HeuristicExactRuntimeRatioRecord`、`BranchAndBoundNodeReductionRecord`。 |
| `_association_contracts.py` | `GapDensityAssociationRecord`、`GapOverlapAssociationRecord`、`GapClusteringAssociationRecord`。 |
| `_performance_association_contracts.py` | `RuntimeSetCountAssociationRecord`、`RuntimeKAssociationRecord`、`SearchNodesDominatedRatioAssociationRecord`。 |

每个类对应的 schema 常量随定义迁移。基础统计模块保留
`DESCRIPTIVE_STATISTICS_METRICS` 和现有自动结论常量。
各模块继续直接使用现有 `_contract_csv.py`，不复制解析器。

`RuntimeKAssociationRecord` 会使用 `RuntimeSetCountAssociationRecord`，
两者必须放在一起，并保持定义和调用关系。
新实现模块不导入 `contracts.py` 或旧聚合模块，避免兼容导出形成循环依赖。

## 兼容入口安排

1. `contracts.py` 将实现导入指向新定义模块，保留公开名称、构造接口和类对象身份。
2. 包根 `__init__.py` 继续提供既有公开记录类；公开导出集合保持，
   纯导出排列顺序若无实际承诺或使用需求，不新增或保留仅为冻结布局的断言。
3. [_benchmark_result.py](../src/maxcover/_benchmark_result.py) 当前直接导入上述旧私有模块，
   在迁移时同步更新到实际定义模块，其他受影响消费者同样处理。
4. 若并行工作需要短期衔接，可保留必要的旧私有导出，调用方迁移后删除；
   旧私有模块路径不作为永久兼容接口，也不为其建立新的固定布局测试。

每个类只能定义一次。兼容入口使用显式导入，不能通过继承、包装或复制类实现兼容。
保留现有 `RecordClass.__module__ = "maxcover.contracts"`，
并在新定义模块中设置；公开入口仍应能按该名称找到同一个类对象。

## 实施步骤

### 1. 在旧实现上记录兼容基线

复用 [test_contracts_compatibility.py](../tests/test_contracts_compatibility.py)
中的类型与记录 fixture，补足本次迁移类型没有覆盖的合法状态。
至少包括可估计、不可估计、缺失参考值和当前允许的空字段路径。

保存下列信息到 `results/` 或临时目录：

- 支持的公开名称与导出集合、公开入口的类对象身份关系；区分有意公开的名称与偶然泄漏的实现名称。
- `dataclasses.fields()` 的字段顺序与默认值、构造签名、`frozen` 和 `slots` 状态。
- `CSV_FIELDS`、`schema_version`、`to_csv_row()` 及经真实 CSV 写入后的字节。
- 每个合法记录的旧版 pickle 字节，以及当前有意保留的序列化失败边界。
- 既有非法 CSV、错误 schema、错误字段或类型输入的异常类型和消息。

pickle 字节由旧实现生成。仅在新实现中做一次自我序列化往返，不能证明旧数据兼容。
不为这次拆分新增广泛支持此前无法序列化的对象。

### 2. 分组迁移并接回旧入口

按“性能关联 → 性能统计 → 解质量”逐组迁移，每组包含类定义、schema 常量、
类自身需要的导入和 `__module__` 设置，再更新公开入口和实际消费者的导入。
一次只搬一个分组，完成后立即运行兼容测试。
保持 `__post_init__()` 检查顺序、数值容差、CSV 空值处理、JSON 编码和报错文字。

提取共同校验逻辑可能影响异常顺序和维护边界，不放在本次机械迁移里。
相似校验可以暂时保留；本次验收针对已有行为兼容。

### 3. 检查消费者与干净进程导入

```console
rg -n '_statistics_contracts|_association_contracts|maxcover.contracts|__module__|pickle' src tests .github
```

确认 `contracts.py`、包根导出、`BenchmarkResult` 和所有记录消费者仍获取同一类型。
在新进程中检查公开入口及实际使用的新导入路径，避免循环依赖或测试顺序掩盖问题。
不枚举已经删除的私有入口作为永久导入矩阵。
还应在新解释器中反序列化旧版 pickle，并通过现有 `spawn` 测试验证多进程传输。

### 4. 核对 CSV 与类型检查

使用旧版记录对应的 CSV 行，经过新解析器读取并重新写出，比较字段和字节。
保持浮点精度、空字段、末尾 schema 列和换行编码，不以字典相等代替完整 CSV 检查。

新增模块默认受 mypy 检查，不复制整模块豁免；必要遗留类型修复单独提交。
按 [报告拆分计划](reporting_split_plan.zh-CN.md) 的收口方式，
随文档精简删除源码文件数、豁免代码占比及其配套断言，不再随拆分重新计算这些展示数字。
审查现有兼容测试时，保留 pickle、CSV、字段、公开名称与实际错误拒绝要求；
只绑定旧私有路径、无用途的导出顺序或偶然实现名称的断言可以移除或改为行为检查。
有意公开的接口不能借此删除，真正需要收缩公开 API 时应另行说明兼容影响。
按当前流程更新许可证清单；历史迁移清单、配置和冻结研究产物保持原样。

## 验证与完成条件

从仓库根目录运行：

```console
python -m unittest discover -s tests -p 'test_contracts_compatibility.py' -v
python -m unittest discover -s tests -p 'test_records.py' -v
python -m unittest discover -s tests -p 'test_p3_contracts.py' -v
python -m unittest discover -s tests -p 'test_p4_instances.py' -v
python -m unittest discover -s tests -p 'test_reference_coverage.py' -v
python -m unittest discover -s tests -p 'test_output_validation.py' -v
```

完成条件：

- 公开名称、字段与默认值、CSV/schema、错误行为均保持基线。
- 公开入口返回同一类对象，公开导出集合不变；内部消费者已迁移到有效路径。
- 旧版 pickle 能在新解释器中加载，`spawn` 传输、不可变性和 `slots` 检查通过。
- 新旧实现的固定记录 CSV 字节一致；默认类型检查不新增豁免。
- 独立进程中的实际导入和反序列化正常，无重复类定义或循环导入；旧私有布局不被永久冻结。
- AGENTS 要求的完整测试、内容边界、许可证和 mypy 检查实际完成并报告结果。

## PR 与停止条件

作为一个记录模块拆分 PR，按“兼容基线 → 类型分组迁移 → 连带更新”提交。
如果报告或 benchmark 拆分也在进行，保留公开入口，只同步本次迁移影响的私有调用方。
若出现字段、CSV 或 pickle 变化，先恢复对应类型组并查明依赖，
不更新 schema 或重新生成旧数据来接受变化。
合并后回退通过回退该 PR，保留旧数据不动。

达到兼容与职责分组目标即结束；不为每个 record 单独建文件。
实施完成时只在本文件补充 PR 链接和实际范围。
