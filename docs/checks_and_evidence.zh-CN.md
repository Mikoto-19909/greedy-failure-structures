# 日常检查、研究验证与证据冻结

日常开发使用核心测试和研究验证；完整跨平台回归在 main 更新或手动运行时执行。
测试分层改变执行频率，不缩小随机样本，也不改变算法、CSV、身份和续跑契约。

## 本地入口

默认研究检查使用 Python 3.12 或更高版本（SciPy 1.18.1 要求至少 3.12），
CI 的研究任务固定为 Python 3.12。基础算法与非研究回归继续覆盖 Python 3.11。

```console
python -m pip install -e ".[typecheck]" scipy==1.18.1 numpy==2.3.5
python scripts/check.py
python scripts/check.py --profile core --list
python scripts/check.py --profile research --tests-only
python scripts/check.py --profile platform --tests-only
python scripts/check.py --profile full
```

默认命令执行核心（包含研究验证）和 mypy；`--tests-only` 仅省略 mypy。
`--profile full` 执行所有发现的测试，原 `python -m unittest discover -s tests -v`
仍可使用。完整测试允许已声明的可选依赖跳过；必需研究验证的跳过会导致检查失败。
在独立的可选依赖环境安装 `.[oracle]` 和 `matplotlib==3.11.1` 后，
运行 `python scripts/check.py --profile optional --tests-only`，两项真实求解/绘图验证都必须成功。
默认检查环境固定 NumPy 2.3.5，避免新版依赖类型声明与 Python 3.11 类型目标冲突；
OR-Tools 自身类型声明与现有兼容调用有差异，因此可选运行环境与 mypy 环境分开，
不放宽源码类型检查。

新测试默认进入核心，只有 `scripts/check_profiles.py` 中明确列出的场景属于扩展。
不要通过改测试名或合并多个方法来制造测试数量下降。所有研究入口的计算验证归入
必需研究检查；工具脚本明确登记为工具或归属已有研究，文件存在性不等于验证正确。

CI 在 Ubuntu 核心检查中用 `--ci` 从完整 PR 差异选择相关扩展。共享数据契约、
未知源码或无法读取差异时运行全部扩展；仍只运行一个 Ubuntu 环境。
CI 可使用 `--omit-research` 避免与独立的必需研究任务重复；本地默认命令不能省略
研究验证后仍宣称默认检查已完成。

## 远端执行范围

代码 PR 的必需状态为 `unit tests (ubuntu-latest, Python 3.12)`、
`platform tests (windows-latest, Python 3.12)`、`research verification`、
`static type check`。必须先确认状态实际出现且检查通过，再将新状态加入远端规则。

仅根目录说明 Markdown、docs 下 Markdown 和 analysis 下报告 Markdown 可免跑；
夹具、源码、配置、数据和特殊文件模式不免跑。检查仍报告免跑原因。
必须使用整个 PR 的共同祖先到 head 的差异；分类失败时执行检查。

main 和手动运行执行六格非研究测试（Ubuntu/Windows × Python 3.11/3.12/3.13），
研究验证单独实际运行一次，另有真实求解器/绘图环境和跨环境数据比较。
精简后的 PR 不再为同一份 quick/Lazy Greedy 数据单独创建双平台 smoke 任务。

## 研究定义与独立复核

新增研究结果入口必须绑定可执行的独立重算、已知答案和损坏/不完整状态拒绝场景。
审查者要实际执行有效和无效输入，并检查验证器不调用生产器的关键计算函数。
读取配置、生成输入和计算稳定身份的共享基础设施应明确说明。

涉及数学定义或认证方法时，另一代理应从原始文献独立核对适用条件、定义、公式和
反例，再与实现比较。记录复核者为代理还是外部领域人员；代理一致不代表外部同行认可，
也不能消除共同的模型或理解错误。

R4 后续需分别检查有效性与紧度：精确小实例上的 G≤O≤U、失效前缀、无效证书、
未完成验证和零分母；LP 另核验数值可行性及保守修正。L5 DUAL 按其专门的对偶定义
核验，不与一般 LP 对偶混用。紧度异常有诊断价值，紧度正常不证明正确。本改动不实现 R4。

## 仅在冻结时保存证据

探索及尚未冻结的数据仍留在本机；没有自动备份，不声称解决冻结前的丢失风险。
报告冻结前，先完成研究验证，在运行说明中记录源码提交、环境、配置、种子、
实际验证命令、结果、失败记录和局限，再显式选择所需文件：

```console
python scripts/freeze_evidence.py prepare --batch example-v1 --file configs/quick.json --file results/example/raw_results.csv --file results/example/instances.csv --notes results/example/run-notes.md --output results/frozen-example-v1
python scripts/freeze_evidence.py publish --snapshot results/frozen-example-v1
```

示例路径需要替换为真实批次。文件选择至少包含实际设计、原始输入/运行结果以及支撑
结论所需的轨迹或汇总；不上传整个 results。工具保存运行说明，但不替代科学验证，
也不因退出码为零就证明说明里的研究结论。

prepare 生成只包含所选证据和 FREEZE.md 的独立 Git 仓库，不发布。
检查文件清单及大小后再 publish；默认目的地是当前 checkout 的 origin。
远端分支名为 `codex/evidence/<batch-id>`。设置该命名空间的禁止删除和非快进规则后，
再进行首次真实冻结。每批次使用新名称，不能覆盖旧证据；修订使用新批次并说明关系。

publish 正常推送后重新读取远端提交，并从远端获取证据树核对，成功才输出 Frozen。
报告引用返回的提交 ID。网络失败保留准备好的本地快照；对同一提交可安全重试。
单文件超过 50 MiB 会失败，必须另行选择经过确认的存储方法，不会静默漏掉大文件。
Git 的对象完整性保护不能代替独立数值验证；源码 tag 也不会保存被忽略的数据。
