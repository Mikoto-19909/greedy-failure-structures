# 统计模块职责拆分

2026-09-10；源码基线 `0d37e6f`。本批独立于 `codex/stabilization-docs` 的通用文档整理。
新功能和新研究实验仍暂停。首批只拆参考处理；后续授权的关联与质量统计拆分见末尾两节。
其余统计、报告和公共记录类保持原状。

## 实现与兼容边界

[参考模块](../src/maxcover/_benchmark_reference.py)承载六个原函数和
`_REFERENCE_BIAS_METRICS`：证书界检查、最优值归一化、参考状态、参考覆盖、
参考删失偏差及参考阈值敏感性。函数正文、常量、公式、排序和异常语义保持一致。
[统计模块](../src/maxcover/benchmark_statistics.py)继续显式导出原名，
`benchmark.py` 继续使用原导入；产物读取与验证脚本无需改变调用路径。

三个模块位置指向同一函数对象，共享原 `ALGORITHMS` 注册表。
新模块不反向依赖 benchmark、统计入口或产物模块；原依赖检查已显式覆盖这个以下划线
开头的文件。记录类、公共签名、CSV 字段、实例身份、检查点和恢复契约不变。
不伪造函数定义模块，也不增加没有实际调用需求的反射兼容层。

## 固定结果比较

在源码修改前，仅生成一次五个小批次、共八个实例，覆盖混合求解状态、双参考一致、
已知最优证书、集合数阈值与缺少参考。原始 CSV 中的耗时随后固定。
feasible/timeout 优先级通过固定记录直接调用核对；B&B 执行注册表拒绝 feasible 的约束保留。

旧新版分别在独立进程读取同一份配置和记录，调用六个函数、summarize 和完整检查点恢复。
重建阶段禁止执行算法，配置绝对路径相同；原始记录与已完成检查点内容保持一致。
比较覆盖六种参考状态、空输入、五种非法参考，以及全部生成的表和报告。
166 个文件逐字节一致，六个函数 AST 与基线一致；没有忽略任何结果字段。
输出验证脚本复用这些统计函数，因此仅作为辅助检查，不替代旧新版比较及已知答案检查。

临时输入、两版输出、比较脚本和实际结果保留在本工作树的
`results/statistics_reference_split/`，不进入源码提交。夹具准备中的失败记录也保留：
补齐 feasible 覆盖、清除非最优记录的原最优界，并改用已有真实证书构造矛盾参考。
最终断言核对目标错误信息，避免把构造器拒绝误算成统计函数拒绝；全过程复用已生成数据。

## 冻结 DUAL 复现

已按[原恢复说明](../analysis/r4_dual_usage.zh-CN.md)从本地 bundle 恢复隔离源码与基线证据。
源码 HEAD 为 `f144418eb09bb61d9b9b28f866f8c91ededbe7ad`，计算版本为 `d31cf2e…`，
基线证据 HEAD 为 `1a8b1899d927cba202cf7931fe992ecd2b5a1807`。
原 `check_code_revision` 与 `SourceAccess` 首图/七个预算的来源关联检查通过。
本地隔离入口位于 `results/statistics_reference_split/frozen-dual/`；原 bundle 与证据不改动。

`src/maxcover` 在旧 DUAL 的冻结范围内，因此本批维护源码不再匹配旧计算版本。
历史实验使用上述隔离入口；不修改旧 `code_revision`、不缩小检查范围、不绕过拒绝。
没有重跑正式语料、全量证书检查或更新历史资源记录。

## 验收与停止条件

复用参考覆盖、benchmark 兼容、模块别名、恢复和 CLI 生命周期测试；补充三方导出身份、
新模块依赖方向，以及矛盾参考、错误界、缺失参考与输入不变的行为检查。
最终执行现有默认检查 `python scripts/check.py`，并由独立审阅者实际核对有效及无效输入。
不改 CI、依赖或检查配置，不以全量性能实验作为纯搬迁的验收。

验收已完成：默认检查运行 468 项（145.849 秒），464 项通过、4 项明确可选跳过，
mypy 的 39 个源码文件通过。使用已有 Python 3.12.14、NumPy 2.3.5、Numba 0.67.0、
SciPy 1.18.1、mypy 2.3.0 环境；没有安装或更改依赖。首次检查在恢复缺失配置时被
沙箱 Git 锁权限阻止，恢复新工作树配置后重试通过；首次日志保留。
独立审阅另执行 25 项相关测试，复核 AST、166 文件等价性和两种源码版本检查，无遗留问题。
检查日志为 `results/statistics_reference_split/default-check.log`；未重跑正式实验或 GPU 验收。

完成等价性、行为检查和独立审阅后只做本地提交。本批结束，不自动继续其他统计分组。

## 第二批：质量关联与性能关联

基线 `ad13f19`，独立分支 `codex/associations-split`，依赖首批参考处理提交；
这两批可分别审查和回退。原 `benchmark_associations.py` 的六个函数按职责迁移：

- [质量关联](../src/maxcover/_benchmark_quality_associations.py)：gap 与密度、重叠、聚类的关联。
- [性能关联](../src/maxcover/_benchmark_performance_associations.py)：运行时间与集合数/预算的关联，
  以及搜索节点与被支配集合比例的关联。

原模块保留兼容导出，`benchmark.py` 和验证脚本不用改导入。
预算投影 `_RuntimeKInstanceProjection`、预算关联与集合数关联留在同一个性能模块，
保持投影单位及 `constant_set_count → constant_k` 映射。私有投影类型的定义模块随之变化，
原路径仍导出同一类型；保存于迁移前的真实 protocol-4 pickle 已验证可以加载和再次往返。
公共记录类型与 CSV 契约没有变化。

本批保留 `_ten_decimal` 的原统计模块依赖与唯一实现，不另建通用关联引擎，
不调整样本资格、耦合分组、算法种子、舍入、数值计算、异常语义或图表。
新增模块不得反向导入 benchmark、关联入口或产物模块，已有依赖方向检查显式覆盖它们。

比较直接使用仓库已有兼容检查点：75 个实例、750 条保存的运行记录。
两版在独立进程中读取相同输入和配置路径，重建报告及完整检查点恢复时禁止执行算法。
36 个文件逐字节一致；六函数和投影类的 AST 一致，输入未改变。
另外覆盖六个入口的空输入、12 种重复/缺失记录拒绝，以及斜率为 3 的已知预算关联和
固定预算下的状态映射。本批没有生成新的研究实例或重新计时。

临时比较脚本、两版输出与实际检查日志位于本工作树 `results/associations_split/`。
首批隔离的 DUAL 源码仍保留在相邻 `statistics-reference-split` 工作树的
`results/statistics_reference_split/frozen-dual/`；维护版本继续拒绝旧计算标签，
历史配置、源码检查范围和证据不改动。代码提交不包含比较输出或历史实验档案。

第二批验收通过：22 项相关测试通过；默认检查运行 473 项（136.676 秒），
469 项通过、4 项可选跳过，mypy 的 41 个源码文件通过。
可选跳过为 Matplotlib、OR-Tools 和两项显式 GPU 检查，使用与首批相同的既有环境。
独立审阅另执行 18 项检查，并自行核对 AST、36 文件等价性、旧 pickle 和冻结入口，无遗留问题。
本批仅形成本地提交，其他统计分组和报告模块未继续拆分。

## 第三批：Greedy 失效与 Local Search 质量分析

基线 `2c4c3de`，独立分支 `codex/quality-statistics-split`，接续前两批本地提交。
本批将 Greedy 失效、Local Search 配对、恢复率和剩余差距四个函数，配对中间类型及其
两个专用辅助函数机械迁移到[质量统计模块](../src/maxcover/_benchmark_quality.py)。保留统计入口及 benchmark 的
全部旧名导出，不改函数正文、记录类、统计口径、异常消息、排序或舍入。
其余描述统计、区间、删失运行时间、性能统计和关联模块留在原处。

先从未修改源码保存固定输出及真实旧版配对对象 pickle，再搬迁实现。沿用已有
75 个实例、750 条运行记录；两版独立进程读取同一配置路径，重建报告和完成态恢复时
禁止执行算法。比较全部产物字节、函数/类型 AST、空输入、已知答案、无资格/零分母、
算法注册表资格和错误拒绝，检查输入不变与旧 pickle 可读。

验证脚本和输出保留在本工作树 `results/quality_statistics_split/`。复用相邻
`statistics-reference-split` 中的冻结 DUAL 入口，核对旧源码可用且维护版仍拒绝旧标签。
受影响测试通过后运行默认检查，记录实际结果；本批只形成本地提交，不推送或合并。

迁移比较通过：六个函数和一个类型的正文及 AST 一致，留在统计模块中的导入和其他
语句也完全一致。35 个生成产物与一份直接调用快照逐字节相同，summarize 与完成态恢复
结果相同，原始输入不变，重建过程没有执行算法。
已知答案使用八组人工记录，区分恢复率、剩余相对差距和各自分母；三个合法空资格场景、
两种随机算法注册替换、33 次配对拒绝和四种 Greedy 拒绝均通过。

私有 `_LocalSearchPairAnalysis` 的定义模块变为 `_benchmark_quality`，原统计模块和
benchmark 路径仍指向同一类型；没有修改 `__module__`。迁移前保存的 209 字节
[protocol-4 对象](../tests/fixtures/benchmark_quality/README.md)可以读取，全部字段、
不可变/slots 行为及 protocol-4/5 往返通过。公共记录类及其 CSV/序列化路径保持原状。

冻结 DUAL 源码检查及首图七个预算读取通过；维护版本仍拒绝旧计算标签。
首次只读检查遇到沙箱账户与冻结仓库所有者不同，以仅限本进程、两条明确仓库路径的
`safe.directory` 设置完成核对；未修改全局 Git 配置、冻结源码或证据。

第三批本地验收完成：29 项相关测试通过；默认检查运行 480 项（126.555 秒），
476 项通过、4 项明确可选跳过，mypy 的 42 个源码文件通过。四项跳过分别是
Matplotlib、OR-Tools 和两项显式 CUDA 硬件检查。复用前两批的 Python 3.12.14、
NumPy 2.3.5、Numba 0.67.0、SciPy 1.18.1、mypy 2.3.0 环境，未安装依赖。
原统计模块从 1,705 行变为 1,293 行，新模块 441 行；主要差异为原文搬迁。

复查命令在本工作树执行，Python 使用上述既有环境：

```console
python results/quality_statistics_split/check_parity.py compare
python -m unittest discover -s tests -p test_benchmark_quality.py -v
python scripts/check.py
```

两次重建快照、直接调用比较及检查日志分别保存在 `before/`、`after/`、
`parity_result.json`、`targeted-check.log` 和 `default-check.log`。
本批没有重跑正式语料或性能测量；未执行推送、合并或合并前的独立审阅。
