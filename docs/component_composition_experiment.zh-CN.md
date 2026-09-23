# 比较功能的组件组合试验

## 问题与结果

在 `codex/component-composition-design-20260921` 工作树上，以本地 `main` 的 `3de1200` 为基线，尝试让比较预览与快照保存通过可复用组件组合实现。

已将现有两个功能接入同一分析编排，分页与全量快照分别消费完整分析结果。与基线比较，432 组响应、8 组快照内容、28 份导出文件字节一致；7 组非法请求和 4 组空数据 SVG 导出的拒绝行为一致。新增 4 个内存组合/错误连接测试通过。

这些结果说明选定功能可以分解并重新组合，同时保持所覆盖行为；没有测量性能、开发耗时或更多功能接入成本，不能据此宣称全项目可任意编排。

## 实际组件与调用关系

- [`comparison.py`](../src/maxcover/comparison.py)：总体选择、分组统计、案例筛选、稳定排序、分页，以及相互区分的 `PopulationRows`、`SelectedRows` 和 `RecordPage`。
- [`comparison_workflows.py`](../src/maxcover/comparison_workflows.py)：`analyze_comparison` 组合纯计算；`preview_comparison` 生成分页响应；`assemble_snapshot` 接收完整分析、明确的 ID/时间和备注，生成全量快照。
- [`dashboard_workbench.py`](../src/maxcover/dashboard_workbench.py)：保留旧 compare 接口与缓存；`analyze` 提供来源变化检查后的完整分析。两者共享 `_analyze`，后者转调纯分析编排。
- [`dashboard_exports.py`](../src/maxcover/dashboard_exports.py)：原保存入口改为“读取完整分析 → 构造快照 → `ComparisonSnapshotStore.save`”；存储适配器独立处理文件写入与读取，不再访问 Workbench 的私有路径方法。既有渲染代码保持原位。
- [`dashboard_paths.py`](../src/maxcover/dashboard_paths.py)：从原 Workbench 提取相同路径策略，供读取与快照存储复用；`WorkbenchError` 仍可从原模块导入。

两个功能的共同部分是“选择总体 → 总体统计 + 案例选择”。统计接收总体记录；案例选择结果用于分页或全量快照。总体统计明确拒绝误接的 `SelectedRows`，快照构造明确拒绝分页字典，存储还检查 total 与保存行数一致。

四个新增测试使用 123 条内存记录：41 条失败、41 条零差距、41 条缺失参考。预期有效 gap 分母是 82，失败率是 0.5；选择失败后仍保留这个分母。分页展示 10 条时，另一分支保存全部 123 条。修改返回预览中的嵌套数据不会改变分析对象或快照。

另外执行了[历史数据组合示例](../results/component_composition/demo.py)：从 pilot 的 120 条保存记录中选择 60 条 Greedy 记录，同一个分析对象生成 10 条预览和包含全部 60 条的快照、CSV、Markdown、SVG。独立读取 JSON/CSV 确认导出均有 60 条，两个统计组共覆盖 60 条。示例经过现有 `read_artifacts` 协调后读取，未启动新实验。

## 与原设计的取舍

首轮没有引入 Reader/Coordinator Protocol 或新的调度层。纯编排只接受已解析内存记录；文件读取和缓存留在原服务，HTTP 的 `read_artifacts` 与 `reading_outputs` 协调保持原样。没有新增可绕过协调的 CLI/Notebook 文件读取入口。

阶段类型已经显式区分，记录字段继续复用现有 `dict[str, Any]`，尚未逐字段 TypedDict 化。冻结 dataclass 只固定容器字段，不保证内部字典深度不可变；组件遵循输入只读约定，对外响应和快照复制内容。当前边界适用于经过既有解析器校验的 Benchmark/R1 记录，不接受任意 CSV 或 R2–R4 研究记录。

渲染继续由旧导出服务负责，不为不变的 Markdown/SVG/CSV 代码另建接口。Dashboard 服务装配无需修改，R2–R4 配对语义和 Benchmark 的任务、暂停、恢复、输出重建均未迁移。

## 验证记录

修改前运行 `test_dashboard*.py`，132 项通过，78.501 秒。组件测试 4 项通过；单独 mypy 检查 54 个源码文件通过。

最终 `scripts/check.py` 退出码 0：670 项测试中 646 项通过、24 项按既有条件跳过，耗时 251.552 秒；必需研究验证成功执行，随后 mypy 对 54 个源码文件检查通过。跳过范围是可选 Rust 扩展、Matplotlib、OR-Tools、显式 CUDA 硬件检查与 POSIX 特有场景，不代表这些能力得到本轮验证。日常 profile 不是 full profile，也不包含所有平台专项测试。

检查期间复查并保留了保存入口的旧参数校验顺序，此后一并重跑 8 项导出测试通过，并对最终代码再次执行 432 组基线比较，结果一致。源码之外的最后变更仅为补充本记录。

首次日常检查使用 canonical 工作树的既有环境，670 项运行结束但失败：3 个 failure、3564 个 error 记录（含大量参数化子用例）、4 个 skip。失败集中在已安装旧 Rust 扩展缺少 `greedy`/`lazy_greedy`/`counts_packed`，以及缺失 Numba 导致的研究验证失败。保留原日志，随后切换到已具备要求依赖的环境重跑；没有用删测试或修改后端代码来绕过失败。

基线比较使用 `git show 3de1200:...` 加载旧 Workbench/Exports 实现，以不同临时目录中的同一份已保存 Benchmark/R1 数据作为输入。来源组合、population、outcome、algorithm、分页和 include_all 共 432 组；固定快照 ID/时间后比较输出。8 组快照包含空选择，空选择的 SVG 拒绝也作为预期行为比较。首次比较脚本未捕获这个预期拒绝，修正比较脚本后通过，生产代码没有因此改动。

比较复用了当前未改变的底层解析/索引依赖，不是两个完整环境的独立运行。已有回归测试另外覆盖来源变化、缓存失效、保存后源替换及重新读取、路径拒绝和后台写入协调。

本地过程证据保留于忽略目录：

- [`baseline.log`](../results/component_composition/baseline.log)：修改前的 Dashboard 测试。
- [`parity.py`](../results/component_composition/parity.py) 与 [`parity.json`](../results/component_composition/parity.json)：可再次执行的旧/新比较及计数。
- [`check.log`](../results/component_composition/check.log)：仓库日常检查输出。
- [`check-initial-environment.log`](../results/component_composition/check-initial-environment.log)：首次环境不匹配的完整失败记录。
- [`demo-preview.json`](../results/component_composition/demo-preview.json)、[`demo.json`](../results/component_composition/demo.json)、[`demo.csv`](../results/component_composition/demo.csv)、[`demo.md`](../results/component_composition/demo.md)、[`demo.svg`](../results/component_composition/demo.svg)：相同历史数据的分页和完整输出。

以上 results 文件是本地记录，不随 Git 文档自动发布；2026-09-23 整合时已迁入主检出的同名目录。未新增研究样本或更新科学结论；常规检查会执行仓库规定的测试及研究验证。

## 复查方式与下一步

以下命令从主检出根目录运行，使用该目录已配置依赖的 Python 环境：

```console
python -m unittest discover -s tests -p test_comparison_components.py -v
python results/component_composition/parity.py
python results/component_composition/demo.py
python scripts/check.py
```

历史验收中，基线、组件测试和行为比较使用主检出既有 `.venv` 的 Python 3.12.14；修正验证环境后，日常检查使用当时的 `wt-fast-verification/.venv/Scripts/python.exe`（Python 3.12.14、Numba 0.67.0、SciPy 1.18.1、mypy 2.3.0）。后者未安装可选 Rust 扩展，对应测试按既有规则跳过；该旧环境不再是当前使用入口。

运行时将 `PYTHONPATH` 指向本工作树的 `src`，没有修改其他工作树的虚拟环境。日常检查的两个缺失历史配置按 CONTRIBUTING 从固定提交恢复，未覆盖已有配置。

首轮到此限定在两个现有功能。后续已开展[共享扩展试验](component_composition_expansion.zh-CN.md)，接入内存渲染、R1–R4 回放文档和失败案例包；新增消费者没有修改本轮共同统计代码。两轮成果于 2026-09-23 纳入主检出整合，当前验收与发布状态见[整合记录](branch_integration_status.zh-CN.md)。
