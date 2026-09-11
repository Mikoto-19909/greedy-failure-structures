# InstanceRecord 同文件提取

## 目标与范围

实施基线为本地 `main` 提交 `ca5499c7bf0eb8a1393bda4ba373697a07679c12`。
按已完成的可行性研究方案 A，在 `_instance_contracts.py` 内把
`InstanceRecord.__post_init__` 末尾的家族规则提为 `_validate_instance_family`。
函数接收记录、已解析参数和通用证书字段，只读校验；调用保留在原分支位置。

类定义、38 个字段、公开身份、CSV 接口、schema、规范化写入及全部校验顺序保持。
跨文件迁移、规则精简、接受范围调整和正式研究重跑不属于本批。
历史 DUAL 复现仍使用冻结版本源码，不调整旧 `code_revision` 或源码检查范围。

## 实施与验收

1. 固定旧源码及 13 个代表输入，在独立进程记录旧版行为和 protocol 4/5 pickle。
2. 同文件机械提取完整家族分支，核对展开后的构造方法与基线语法结构一致。
3. 比较旧新版 8,790 项确定性调用的接受/拒绝、异常类型与信息、CSV、hash、
   类型形状、类型注解、旧 pickle 和调用者输入不变性。这些调用包含重复情形，
   不是独立随机样本，也不代表科学结论。
4. 补充首错顺序、规范化、旧 pickle 和 replace 语义的聚焦回归；运行相关现有
   记录、实例族、CSV、恢复及 spawn 测试，最后运行 `python scripts/check.py`。
5. 独立审阅者检查实际 diff，并执行有效与无效输入；修正发现后记录验收结果。

本机解释器为 `D:\test area\greedy-failure\wt-fast-verification\.venv\Scripts\python.exe`
（Python 3.12.14）。执行时将本工作树的 `src` 放在 `PYTHONPATH` 首位，避免使用
解释器所在工作树的源码。验证材料保存在忽略目录 `results/instance_family_validation/`；
不提交全部探针观测，也不新增文档措辞或文件行数门禁。

## 当前状态

2026-09-11，同文件提取和作者验收已完成。`__post_init__` 从 381 行缩为 163 行；
家族函数位于类之前，全部通用检查与两处规范化仍在构造方法中。
移回函数体并还原参数名后，整个模块的 AST 与基线一致。

- 旧新版各执行 8,790 项固定调用：接受 979、拒绝 7,811，比较属性差异为 0；
  protocol 4/5 旧 pickle 均可读取并按原协议逐字节重新序列化。
- 新增 6 项回归在提取前后均通过；现有公开契约 7 项、P4 家族 45 项全部通过。
  常驻旧 pickle 仅 972 字节，来源和恢复方法见
  [fixture 说明](../tests/fixtures/instance_family_validation/README.md)。
- 复用既有 75 个实例、750 条运行记录，旧新版分别执行恢复和表格重建，
  24 份 CSV 逐字节一致；执行入口被设为调用即失败，确认没有重新执行算法。
- 默认 `python scripts/check.py` 执行 487 项：483 通过、4 项可选跳过；
  mypy 检查 42 个源码文件通过。跳过项为缺少可选 Matplotlib 的绘图检查、
  缺少可选 OR-Tools 的 oracle 检查，以及需显式启用的两项真实 CUDA 检查。
- 独立审阅通过，无遗留问题。审阅者自行构造 16 个代表记录，通过构造、replace、
  CSV 三类入口执行 432 组旧新版对照：132 接受、300 拒绝，全部一致；另核对
  失败后的规范化状态、调用者输入不变性、完整模块 AST、类型形状和注解。
  审阅者从基线独立重制的 972 字节旧 pickle 与常驻 fixture 完全一致。

原始观测见本地 [差分摘要](../results/instance_family_validation/summary.json)、
[保存结果比较](../results/instance_family_validation/saved_output_summary.json)和
[默认检查日志](../results/instance_family_validation/default_check.log)，以及
[独立审阅结果](../results/instance_family_validation/independent_review/result.json)。这些忽略目录中的
材料未发布；常驻回归与旧 pickle 随源码交付，不依赖该目录才能运行。

在本工作树根目录复查常驻回归和默认检查：

```powershell
$instancePython = 'D:\test area\greedy-failure\wt-fast-verification\.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
& $instancePython -B -m unittest discover -s tests -p test_instance_family_validation.py -v
& $instancePython -B scripts/check.py
```

首次默认检查因隔离账户无法写入 Git 元数据而未启动测试；按 CONTRIBUTING
从规定提交恢复新工作树中缺失的两份 R2/R3 配置后，上述完整检查通过。
本批仅本地实现和验收，尚未发布或合并。
