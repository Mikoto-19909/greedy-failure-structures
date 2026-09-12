# 本地审查首版实施

2026-09-12，起点为 prepare 合并提交 `a31dd746891e1741c4876dbff63725c2fc1dc9e6`，
实施工作树为 `wt-local-review`，分支 `codex/local-review`。
依据工作区 `local-review-design-20260912/PLAN.zh-CN.md`；该原设计保留不改。

本轮实现一次手动触发的本地流程：固定提交、独立克隆、prepare、既有检查、
独立只读模型审阅和明确的完成状态。暂不发布，不接入 CI、Git hook 或定时任务。
prepare 与既有检查入口保持原职责，不运行模型建议的新复现代码，不自动修复。

实施步骤：先核对真实 CLI 的配置隔离/登录与进程取消，再实现调度、响应字段及文档；
使用合成仓库和替代进程验证失败、状态、路径和子进程边界，然后做真实模型及固定提交验收。
运行必要的项目检查，保存实际结果及未完成项。

完成条件：正常流程可运行；不修改源工作树；检查保持必需研究与 mypy 语义；
缺依赖、失败、过期版本、超时、无效输出均不误报为通过；真实审阅调用与只读限制已经检查。
合并前独立审阅及项目完整检查仍适用。后续三次真实 PR 的效果评估属于实际试用，不能提前宣称完成。

## 已完成的运行前提与初步验证

Codex 0.153.4 的现有 ChatGPT 登录和用户选定模型 `gpt-6-astra` 已实际调用。
最初忽略用户配置时连读取也被策略拒绝；补回本机已配置的 Windows 专用沙箱后端，
保持 read-only/never，后续实际读取成功、文件写入被拒绝、sentinel 内容不变。
未绕过执行规则或改全局配置。子进程不再继承父任务的工具管道、Git 重定向和连接器环境。

Windows 的进程树超时、取消和父进程提前退出清理已实测；OS 清理可能返回退出码 0，
实现仍按 cancelled/timed_out 判定未完成。类型检查已覆盖 Windows/Linux 两种平台视图，
但这不等于已进行 Linux 运行验收。

替代审阅进程及合成仓库已覆盖主要状态、定位、日志引用、版本偏移、脏源码隔离和环境失败。
两个真实模型端到端样例均使用独立合成平均值函数：已有空输入检查通过，但模型对有分母错误的
候选报告静态 P1，流程返回 needs_attention；修正后的提交未报告问题，返回 no_findings。
这证明本次调用与分类可工作，不证明整体发现率或零误报。prepare 的两项旧 Git 缺陷仍由原回归测试覆盖；
采用新的小型缺陷样例避免把先前聊天中的结论提供给审阅模型。

详细本地产物保留在 `results/local-review-live/`、`results/local-review-preflight/`，不进入源码提交。
对本工具提交 `bdc2b31eb979b95f583563a44102f44ca26b01fe` 的首次完整流程已执行：
507 项中 503 项通过、4 项既有可选跳过，必需研究验证与 42 个源码文件的类型检查通过。
独立静态审阅发现解释器路径 resolve 会解开 POSIX venv 符号链接，流程正确返回 needs_attention。
已在 Windows 用真实目录 junction 复现“用户选择的路径被替换”，先确认回归测试在旧实现失败，
再改为保留链接的绝对路径。另增 POSIX 原生符号链接 venv 回归，Windows 下明确跳过，不宣称实跑。
该问题原报告及日志保留在工作区 `local-review-self-trial-20260912/`；修正版完整复验另存新目录。

## 首版验收结果

修正版行为提交为 `175a785a23eb755010163d9994f1a309ef130395`。
工作区 `local-review-final-trial-20260912/summary.md` 为最终端到端阅读入口，
本次以 `bdc2b31` 为比较基线，完整流程返回 no_findings / 退出 0。
项目默认检查 509 项中 504 项通过、5 项按条件跳过；必需研究验证及 42 个源码文件的 mypy 通过。
五项跳过为 Matplotlib、OR-Tools、两项真实 CUDA 检查和新增 POSIX venv 回归。
12 项工具测试中 11 项在 Windows 通过，POSIX 专用项跳过。
新增两个脚本分别按 Windows/Linux 平台视图通过 mypy；Linux 视图检查不是 Linux 运行证明。

独立静态复核已阅读修正提交及原实现，未报告仍需修正的问题，明确指出 POSIX 原生回归尚未执行。
初审已覆盖首版六个文件，复核覆盖解释器路径修正的四个文件。两次模型审阅均未执行新测试或复现。
现有 CI、review bot 和合并前独立行为验证仍保留；本轮未运行 full profile、发布或合并，
也未进行后续三次真实 PR 的效果试用。最终记录追加只改变本实施文档，不改变上述已验收的代码。

## user-trial 报告修复与剩余验收（2026-09-12）

user-trial 独立审阅另报 P2：普通本地 clone 不保证传递仅远端跟踪引用可达的提交。
此前首版复核结论没有覆盖此问题，不应解读为所有已知问题均已关闭。
工作区 `local-review-user-trial-20260912/ref-transfer-probe/verification.json` 的一次性复现
记录了 `clone_missing_requested_base: true` 和 prepare 的 `fatal: Needed a single revision`。
它导致检查前 incomplete，是可用性缺陷，不是误判通过的安全漏洞。

本轮按固定 SHA 从本地源仓库补传请求的 base/head，保留独立对象存储，不更新源引用或访问网络远端。
新增真实 Git 回归覆盖远端跟踪 base、head、两端同时缺失及显式 SHA，并验证传递失败会在检查前停止。
用户文档同步明确候选检查代码以当前用户权限执行、full 的可选跳过和环境错误解释，
以及 actual_model 恒为 unknown、读取 nonce 不等于读完 diff 的证据边界。

本轮工具测试 14 项中 13 项通过，POSIX 专用项在 Windows 跳过；新增回归在旧实现上
先实际失败，再在修复后通过。两个脚本的 Windows/Linux 平台视图 mypy 均通过。
独立复核另跑 4 项有效/无效输入测试，并构造 base、head、共同祖先三者均不可从
本地 heads/tags 到达的 fixture：补传及 prepare 成功，源 refs/index 不变；不存在的 SHA
使真实 fetch 失败并在检查前返回 incomplete / 1。复核未发现需修正的问题。

full 已通过调度器实际运行：在独立克隆中提交包含本轮代码/测试的验收快照
`afcb86531d14e8f3c612720c4906347c3f5f279a`，以 `8f1ac54` 为基线运行 `checks='full'`。
570 项中 564 项通过、5 项跳过、1 项错误，用时约 293 秒；必需研究用例通过。
跳过项为 Matplotlib、OR-Tools、两项真实 CUDA 和 POSIX venv，CUDA 未造成检查失败。
错误来自既有 `test_same_origin_non_json_post_is_rejected`，读取本地 HTTP 响应时发生
`ConnectionAbortedError: [WinError 10053]`。同一快照单独复验该项通过，根因尚未确定。
检查退出 1，调度器保留 needs_attention / 2，未误报成功；不能将本次 full 记为通过。
full 因测试错误未进入内置 mypy；另行对同一快照运行 mypy，42 个源码文件通过。
本次真实执行项目检查，模型环节使用替代审阅进程，仅验收调度与失败分类，不代表真实模型端到端验收。
日志和运行信息保留于工作区 `local-review-repair-20260912/`：`acceptance.json`、
`full/checks.stderr.log`、`full/summary.json`、`http-recheck.log` 和 `source-mypy.log`。
上述验收快照不在工作分支提交历史中；后续本段记录更新只修改文档。

仍未完成：full 整轮成功验收及 HTTP 错误原因核对、Linux 原生 symlink-venv 运行验收，
以及后续三次真实 PR 的效果试用。
Windows 全绿或 Linux 视图 mypy 通过不能替代 Linux 运行记录；full 成功也不能代表跳过项已执行。
