# 在本地组合检查与独立审阅

`scripts/review_local.py` 为一次固定提交改动运行现有检查和独立静态审阅，生成本地摘要。
它补充 CI 和远端 review bot，不自动批准、修复、推送或合并，也不建立定时任务或 Git hook。

## 前提与命令

需要 Python 3.11+、Git、已登录的原生 Codex CLI，以及本项目已有检查依赖。
指定给 `--python` 的解释器须安装 mypy、NumPy、Numba、SciPy；工具只核对依赖是否存在，
不会安装或改用其他环境。版本要求以 CONTRIBUTING 和 pyproject.toml 为准。
只应用于本人已授权运行的本地仓库。独立克隆避免影响活动工作树，本身不是不可信代码沙箱。

从本工具工作树运行，例如：

```console
python scripts/review_local.py --repo ../greedy-failure-structures --base main --head codex/prepare-review --output ../local-review-001 --python ../wt-fast-verification/.venv/Scripts/python.exe
```

`--base/--head` 可换成分支或完整提交；输出目录必须全新，父目录须已存在，
且位于目标仓库及其登记工作树之外。未提交和暂存编辑不纳入审查。
若需要精确比较区间，使用明确基线，不要默认本地 main 已同步远端。

本机尚未把 Python 加入 PATH 时，可用解释器绝对路径启动；例如在 PowerShell 中：

```powershell
& 'D:\test area\greedy-failure\wt-fast-verification\.venv\Scripts\python.exe' -B scripts/review_local.py --repo '../greedy-failure-structures' --base 'ca5499c7bf0eb8a1393bda4ba373697a07679c12' --head '63b74970f8252df32125cbd8c57fba00ca1db5c8' --output '../local-review-prepare-001' --python 'D:\test area\greedy-failure\wt-fast-verification\.venv\Scripts\python.exe'
```

源仓库应由执行命令的账户拥有；Git 所有权错误应在正确账户下处理，不修改全局信任设置。
Windows 会从 npm 的 Codex 启动器定位原生程序；非标准安装用 `--codex <codex.exe 的绝对路径>`。
不接受 shell 命令、参数拼接或 `.cmd/.ps1` 作为自定义执行程序。
当前已验证 CLI 0.153.4；其他版本要确认所需选项仍支持，失败不会自动放宽权限。

## 执行范围

流程依次固定版本、检查登录、独立本地克隆、prepare、环境预检、现有检查、模型审阅。
克隆不共享可写 Git 对象、索引或 worktree 元数据；禁用 clone/checkout 的钩子、全局配置和过滤器。
目标必须有完整且本地可获取的历史；不自动 fetch。prepare 本身仍只读、不会执行目标代码。

`--checks core` 为默认值，运行 `python -B scripts/check.py --profile core`。
`--checks full` 运行原有 full profile。两者都不省略研究验证和 mypy。
输出 `checks.log` / `checks.stderr.log`，保留实际退出码、命令和耗时。
`summary.json` 中 `steps` 也保存预检与中断步骤。缺失安装包为 incomplete；
已安装包的加载/运行错误仍可能表现为检查失败，需要阅读原始日志判定原因。
原检查入口允许的可选跳过会保留在日志，不能据整体成功宣称这些检查已执行。

检查时设置本次克隆的源码搜索路径并核对 `maxcover` 的解析位置，
避免 editable install 偷用其他工作树代码。缓存和归档配置恢复只落到执行克隆或输出中。
发现克隆的 HEAD、tracked 源码或索引被改动时，流程未完成；允许的未跟踪结果文件不当作源码改动。

模型使用全新临时会话、只读权限和 `approval_policy=never`，
关闭插件、连接器、钩子、多代理、浏览器、图像工具和记忆功能。
不继承父任务的工具管道或 Git 重定向；忽略用户配置并在独立 reader 目录隔离候选项目配置。
保留原有执行规则。模型只负责读取源码/固定 Git 对象，不能执行测试、新复现脚本或安装依赖。
这些执行限制也写入审阅指令；只读沙箱不是对每一条 shell 命令语义的证明。

`--model` 可显式指定；否则只读取用户配置的 `model` 字段，不继承整个配置或主任务对话。
首版使用现有 OpenAI/Codex 登录，不适配自定义提供商配置。
报告记录请求模型；CLI 未给出实际模型信息时保持 unknown，不能据此宣称模型身份已核验。
可获取的用量来自 CLI 事件，不是费用估算。

在 Windows 上显式使用已配置的 `windows.sandbox=elevated` 后端，并保持 read-only 权限。
这是专用低权限账户隔离，不是关闭沙箱。该后端未完成系统安装时应报未完成，
工具不会自行切换弱隔离模式。相关行为见[官方 Windows 沙箱说明](https://learn.chatgpt.com/docs/windows/windows-sandbox)。
非交互及结构化输出参数见[官方说明](https://learn.chatgpt.com/docs/non-interactive-mode)。

## 结果与失败

- `no_findings` / 退出 0：约定检查成功，模型完成审阅且未报告问题或阻断性缺口。
  这不是代码正确、覆盖充分或可以合并的证明。
- `needs_attention` / 退出 2：流程完成，但检查失败或模型提出了问题。
- `incomplete` / 退出 1：版本、环境、权限、登录、响应、超时、取消或源码变化导致流程未完成。
  没有最终 `summary.json` 也按未完成处理。初始路径/版本无效时不会创建输出。

`summary.md` 为阅读入口；`summary.json` 为调度器的运行摘要。
模型原始响应在 `reviewer.json`，其执行事件和诊断分别在 `reviewer.events.jsonl` 与 `reviewer.stderr.log`。
`package/` 为 prepare 的材料；`checkout/` 保留供核对；`reader/` 仅为隔离的审阅工作目录。
失败也保留已得到的证据和日志，不自动删除或复用目录。

每项问题必须有固定版本的有效路径/行号、影响及依据；静态依据与已执行日志分开。
日志引用必须真实存在，程序只能验证定位，不能自动证明日志支持该问题。
模型建议的新复现程序保持未执行状态，应由作者/审阅者随后核对和复现。
即使 JSON 合法或 CLI 退出 0，缺失完成事件、上下文读取失败或阻断性缺口也不能记为成功。
工具要求模型读取一次随机上下文标记，以识别基础读权限失败；该标记不能证明审阅完整或结论正确。

`--check-timeout` 默认 900 秒，`--review-timeout` 默认 600 秒，均可显式调整。
超时或取消会终止该步骤的整个进程树；Windows 使用先挂起、加入 Job Object、再启动的方式，
避免子进程在加入边界前逃离。正常父进程退出时也终止其遗留子进程。
Windows 清理返回原始退出码 0 时仍保留 cancelled/timed_out 状态，不以退出码单独判断成功。

流程结束时重新检查用户给出的符号引用；若已经移动，结果标为过期且未完成。
显式 SHA 的报告仅属于该 SHA。将来接入发布入口时仍须重新比对待发布提交，不能复用旧分支结论。

## 开发验证

```console
python -B -m unittest discover -s tests -p test_review_local.py -v
python -m mypy --no-incremental scripts/review_local.py scripts/review_process.py
```

合成仓库使用替代审阅进程验证调度与错误分类，不消耗真实模型用量。
真实模型样例、平台限制与项目检查结果见[实施记录](local_review_plan.zh-CN.md)。
后续真实 PR 试用应记录有效问题、误报、远端遗漏、耗时和用量；该效果评估尚未完成。
