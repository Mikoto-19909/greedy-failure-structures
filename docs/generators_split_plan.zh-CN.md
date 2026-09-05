# 实例生成器拆分计划

记录日期：2026-09-05。状态：已完成，由 [PR #40](https://github.com/Mikoto-19909/greedy-failure-structures/pull/40) 交付。

本计划以主分支 `ddf6a8a` 的实现为参照；实施前确认 PR #21 和 benchmark 拆分状态。
贡献和检查要求沿用 [CONTRIBUTING](../CONTRIBUTING.md) 与 [AGENTS](../AGENTS.md)。
本轮在验证器整理后、记录类型拆分前实施，遵循
[统一实施顺序](README.md#implementation-plans)。实验先在固定提交完成，
所有源码拆分之前先完成 benchmark B0；实验配置、生成器版本和冻结证据保持不变。

## 实际交付

本批从 `ca5cfd5e2f6d444d76792aaccd79691e006c38dc` 开始，在
[验证器 PR #39](https://github.com/Mikoto-19909/greedy-failure-structures/pull/39)
合并后实施。PR #21 已合并，现有有效 coupling seed 配对测试属于当前主分支。
拆分前的 `generators.py` 与固定旧 `c40658d4cbc16b45fb640b1d97c03688baee16b7`
的 Git blob 相同；后续候选分别记录新的源码哈希。

旧矩阵从真实 Git 源独立导出，冻结各注册家族的直接、registry、`from_spec`、配置
预检/生成调用及边界。每项记录完整有序位掩码、元数据、证书、身份和错误；两种
pickle 协议另保存公开函数和 spec，后续候选读取原字节并重放。原始案例和旧结果
不会从候选实现重新生成，未运行求解算法或追加研究样本。

审计确认 `GeneratorSpec` 没有独立 version 字段；实例记录的生成器版本取自
`construction_version` 参数，省略时按现有逻辑使用默认值。固定大小构造省略 coupling
与显式传入普通 seed 作为 coupling 本来不同，两条路径分别比较。旧 spec pickle 的
必填标记存在原有 sentinel 身份问题，其恢复前后行为已记录；本次不将成功加载
夸大为完整语义往返，也不混入该独立问题的修复。

当前源码已无模块级类型豁免。新模块继续接受默认检查；按授权只运行本批相关本地
验证，重复的全套、内容边界和许可证检查由当前 PR 的必需 CI 覆盖，许可证清单仍更新。

四组分别提交为 `78892b7`、`e5a37de`、`c81b59b`、`f0cf0a2`，合并提交为
`88962896de53d4f0fa9ad8b931747dd8158a0613`。共享工具、对抗、受控和普通随机构造
分别位于对应内部模块；公开入口直接重新导出原函数。唯一受影响的私有测试导入
`_potential_distractor_rankings` 已迁到实际定义模块。

最终旧新版比较通过：257 个调用、58 个旧 pickle 及对应的新 pickle 行为保持基线；
固定规划的 135 个实例和 870 个任务内容及身份一致。独立追踪的 3,234 次随机调用
及 42 个 RNG 对象顺序一致。全部原函数、嵌套作用域、实际全局绑定和注册表保持原样。
外置核验同时绑定旧清单哈希、Git blob 和候选树，旧数据未被重新生成。

相关生成器测试、最终默认 mypy 和独立审查通过；PR #40 当前提交的必需单元测试、
内容边界与许可证、类型和提交检查均实际通过。按用户授权复用已通过且源码未变的
结果，最终集中验收，不再逐阶段重复全矩阵、整套本地检查或独立审查。

## 目标与边界

将 [generators.py](../src/maxcover/generators.py) 按实例构造用途分组，
使修改受控高重叠或对抗实例时能定位到对应实现。
保留公开函数、参数和默认值、`GENERATORS`、`from_spec()`、family 名称和版本。

相同输入必须生成相同的有序集合位掩码、维度和结构元数据。
种子派生、随机数调用次序、集合与元素顺序、空集合处理、配对关系和错误行为均保持原样。
不顺手更换采样方法、生成器版本或配置格式，不新增实例家族和算法。

## 文件与函数迁移

以下新增名称均为计划中的文件，放在 `src/maxcover/`。

| 目标文件 | 迁移内容 |
| --- | --- |
| `generators.py` | `GENERATORS` 注册表、`from_spec()`、公开生成函数的显式重新导出。 |
| `_generators_random.py` | `uniform_random`、`high_overlap`、`clustered`、`fixed_size`、`long_tail`、`duplicate_heavy`、`dominated_heavy`、`mixed_cluster`，以及只被这些函数使用的辅助函数。 |
| `_generators_controlled.py` | `controlled_high_overlap`、`controlled_clustered`、`controlled_duplicate`、`controlled_dominated`，及仅用于这些构造的辅助函数。 |
| `_generators_adversarial.py` | `adversarial_greedy_trap`、旧版与新版实现、`controlled_adversarial_greedy_trap`、`_potential_distractor_rankings`。 |
| `_generator_common.py` | 被多个实现模块使用的参数检查、`_mask`、`_derived_seed`、`_resolve_coupling_seed`、共享组合采样和索引还原函数。 |

按实际使用者决定辅助函数归属：`_paired_cardinality_draws` 留在随机生成模块，
`_controlled_element_order` 留在受控模块，`_proper_subset_elements` 留在随机模块；
共同使用的 `_sample_unique_ranks` 和 `_unrank_combination_lexicographic` 进入共享模块。
`duplicate_heavy` 直接调用 `fixed_size`，两者保留在同一模块。

注册入口导入实现模块；实现模块只导入共享工具、模型和契约。
共享工具不导入入口或实现模块。移动过程中不要通过 `generators.py` 回取辅助函数。

## 实施步骤

### 1. 建立可比较的输入矩阵

记录旧版 commit，以 [test_generators.py](../tests/test_generators.py) 的直接调用和注册表
测试参数为起点，加上 [受控构造测试](../tests/test_controlled_stressors.py)、
[新家族测试](../tests/test_p4_new_families.py) 与
[对抗构造测试](../tests/test_p4_adversarial.py) 中的现有案例。

| 输入组 | 应保存与比较的内容 |
| --- | --- |
| 每个注册家族的最小合法案例 | 参数、种子、有序 `sets`、`universe_size`、`k`、结构元数据。 |
| 支持的概率、容量等边界 | 原先接受或拒绝的结果、异常类型、消息；不发明所有家族都适用的边界。 |
| 直接调用、注册表调用、配置预检 | 参数默认值、派生参数、结果和错误路径一致。 |
| 相同 coupling seed 的多个强度级别 | 原始抽样和实例结果保持基线；分别保留普通 seed 与 coupling seed 不同的案例。 |
| adversarial 旧、新版本及受控版本 | 构造输出、已有证书和结构信息一致。 |

旧版运行后将输出保存到 `results/`，以新实现重跑相同参数并比较。
位掩码数组逐项比较，不能改成集合比较；只比较覆盖数或分布不足以发现随机序列漂移。
浮点元数据沿用现有编码，不在重构期间更换精度或序列化方式。
只为现有测试缺失的关键边界补测试，避免复制整套实验配置作为新测试框架。

### 2. 先抽出共享工具

原样移动多模块实际需要的辅助函数，再由原 `generators.py` 显式导入，
使尚未迁移的构造继续工作。保留函数体中的所有随机调用及参数检查顺序。
此时先运行直接调用与注册表等价测试。

### 3. 按家族原样搬迁

依次移动对抗、受控、普通随机构造。每组迁移后重跑对应输入矩阵。
保留函数签名、默认值、文档中准确的语义说明和内部调用关系。
实现模块中的函数直接作为注册表 factory，入口使用重新导出而不是包装函数。

检查注册表中每个 spec 的名称、参数定义、默认值、factory 和迭代顺序，
并核对实例元数据中的构造版本；不向没有 version 字段的 spec 添加新字段。
固定输入的配置哈希、实例身份及配对身份不应因文件迁移改变。
若实际代码使用函数模块名参与身份计算，先明确兼容方法再搬迁，不能接受身份漂移。

### 4. 核对调用与配对分析

```console
rg -n 'from .*generators|generators\.|GENERATORS|coupling_seed' src tests
```

重点核对 `config.py`、`benchmark_planning.py`、`cli.py`、`stressor_audit.py` 和包根 `__init__.py`。
它们通过保留的入口访问生成器，通常无需改调用签名。
对子模块新增的导入运行一次干净进程检查，避免运行过其他测试后才意外可用。

PR #21 已合并，其有效 coupling、manifest 文件绑定和 schema 校验测试由当前
完整单元测试覆盖；本批固定规划比较另外检查了 coupling 与派生身份。
本拆分不改变配对统计、manifest 校验或 schema 强制行为。

### 5. 同步必要说明

生成器家族的使用方法保持不变，技术文档只更新实际指向实现位置的引用。
按 [报告拆分计划](reporting_split_plan.zh-CN.md) 的测试收口方式，
随文档精简删除源码文件数、豁免代码占比及其配套测试；已删除的统计不再恢复。
保留结果、确定性、CSV、公开接口与错误拒绝检查，不冻结私有工具的文件位置或函数数量。
公开生成入口与注册标识属于实际兼容要求，私有辅助函数导入随调用方更新。

新生成器模块默认进入 mypy 检查，不继承 benchmark/reporting 的整模块豁免。
如实际发现遗留类型问题，将必要修复单独提交；不能以包级忽略代替处理，
也不把全仓类型整治作为本计划的前置条件。文档只说明实际覆盖边界并链接现行配置。
按当前流程更新许可证清单，不修改历史迁移清单和已冻结实验产物。

## 验证与完成条件

从仓库根目录运行：

```console
python -m unittest discover -s tests -p 'test_generators.py' -v
python -m unittest discover -s tests -p 'test_controlled_stressors.py' -v
python -m unittest discover -s tests -p 'test_p4_new_families.py' -v
python -m unittest discover -s tests -p 'test_p4_adversarial.py' -v
python -m unittest discover -s tests -p 'test_p4_instances.py' -v
python -m unittest discover -s tests -p 'test_paired_seed_analysis.py' -v
```

完成条件：

- 输入矩阵中的有序位掩码、结构元数据、证书与身份均与旧实现相同。
- 注册表及直接调用一致，原公开入口可用，配置预检的错误类型和路径未变化。
- 同一 coupling 输入跨强度的行为保持基线；串行、并行和恢复相关测试通过。
- 函数跨模块后能够在干净进程中导入，注册表无重复注册和循环导入。
- 私有布局可调整，正常拆分不再触发无关文档数字更新；新模块的类型覆盖没有倒退。
- AGENTS 要求的完整测试、内容边界、许可证和 mypy 检查实际完成并报告结果。

## PR 与停止条件

作为一个生成器拆分 PR，按“输入基线 → 共享工具 → 家族迁移 → 连带更新”提交。
保持与正在运行的研究实验分开；实验继续使用明确固定的 commit。
出现位掩码、身份或错误路径差异时，恢复对应家族的迁移并定位原因，
不通过改种子、重新生成期望值或提升版本号掩盖差异。
合并后如需回退，回退该 PR，已冻结数据保持原样。

通过以上检查即结束，文件行数不作为硬门禁。
实施完成时只在本文件补充 PR 链接和实际范围。
