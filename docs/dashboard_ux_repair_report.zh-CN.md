# Dashboard 交互修复完成记录

2026-09-13。依据 [修复计划](dashboard_ux_repair_plan.zh-CN.md) 完成实现、本地验证和独立复核。
原实现分支为 `codex/dashboard-ux-repair-20260913`，验收提交 `5fcecdab`。
本 PR 从已交付主线 `dcfd2221` 整理五个界面提交，保留主线已有的 HTTP 拒绝回归与开发收口文档；以下原验收记录仍对应原实现提交。
旧界面工作区的七个未提交文件已另行比较，入门、三种方案、预览、指标说明与窄屏行为均被本分支覆盖；原文件与验证材料已有本地归档，旧工作区已收尾。新修复尚未合并到主线。

## 修复结果

1. **切换失败显示旧数据**：开始切换即清空光谱、摘要、图表、元信息及旧回放，关闭旧报告/图表弹窗；只允许当前请求提交结果。失败后说明原因和下一步。
2. **成功后残留旧错误**：结果载入成功时清理对应错误；手动刷新、运行完成后的刷新使用相同处理。
3. **默认目录不可用、刷新丢失选择**：索引排除没有规范 CSV 的目录，保留 raw-only/summary-only；按 CSV 产物更新时间排序，优先恢复上次成功选择。保存选择失效时提示并尝试下一结果；全部失败有终止状态。
4. **回放无反馈与含义混淆**：区分运行超时/错误案例文件与贪心差距；空范围禁用回放并解释。当前结果与其他保存案例分开选择，后者保留仅有回放文件的目录。换案例、算法或结果清除旧输出，迟到响应不能写入新的结果区域。
5. **名称规则不透明**：字段旁展示完整命名规则并即时校验，非法名称不发送运行请求；最近任务状态与本次提交错误明确区分。
6. **成果入口过深**：首屏提供查看已有结果，结果选择器位于共同展示区上方；可直接导航到算法对照、图表/报告和回放。保留已有候选补丁的三个示例说明，修正按钮换行与图表名称一致性。
7. **原始 Markdown 难读**：在应用内阅读原报告的标题、列表、段落、代码和表格；摘要复制完整既有 Headline checks 段落及限制，不添加结论。原文件可下载，正文语言明确标识。`report.js` 仅展示项目报告使用的结构，其他语法保留文本，不执行 HTML，也不引入运行依赖。

独立复核还发现并推动修复了两项状态竞态：

- 完成任务的自动刷新等待期间，用户的新选择曾被完成结果覆盖。现在记录用户选择版本，期间有新选择时尊重它。
- 定时轮询响应可能重叠，迟到的 running 曾覆盖 completed。现在同一轮询只允许一个在途请求，并检查当前任务归属；完成状态不会被旧响应改回运行中。

## 验证结果

- **浏览器：23 个场景全部通过**。使用真实 Chrome、独立临时项目、真实小型 benchmark 与真实回放；网络拦截仅用于稳定复现失败和响应乱序。覆盖正常/非法输入、无结果、raw-only、存储禁用、失效选择、全部加载失败、回放空状态/坏文件/跨结果、报告失败与迟到响应、原文下载、语言往返、图表关闭焦点、直接导航及三个视口。
- **项目规定检查：通过**。`scripts/check.py` 执行 469 项测试，4 项按既有可选条件跳过；mypy 检查 38 个源文件无问题。跳过项为可选 Matplotlib、可选 OR-Tools，以及两项需显式 CUDA profile 的硬件检查；必需研究验证没有失败或被跳过。
- **JavaScript 语法检查：通过**。`app.js` 与 `report.js` 均经 `node --check`。
- **独立复核：通过**。复核者实际执行合法实验、非法输入、有效/坏回放及边界脚本。针对上述两项发现再次独立回测：延迟完成刷新后保持用户选择；挂起轮询期间无重叠请求，完成后继续观察仍保持完成。复核没有剩余发现。

最初用主工作树 `.venv` 跑日常检查时缺少 numba，产生 2 failures、5 errors，未视作通过。
随后只读复用 `wt-fast-verification/.venv` 的匹配环境重跑成功，没有安装或改动其他环境。
该环境版本：Python 3.12.14、NumPy 2.3.5、SciPy 1.18.1、Numba 0.67.0、mypy 2.3.0。

## 运行与复验

在修复工作树中启动即可试用。此工作树的实验结果与原工作树隔离；首次运行使用新结果名称：

```powershell
Set-Location 'D:\test area\greedy-failure\wt-dashboard-ux-repair'
& '..\greedy-failure-structures\.venv\Scripts\python.exe' run_project.py dashboard
```

日常项目检查使用具备 CONTRIBUTING 所列依赖的解释器：

```powershell
& '..\wt-fast-verification\.venv\Scripts\python.exe' scripts/check.py
node --check src/maxcover/dashboard_ui/app.js
node --check src/maxcover/dashboard_ui/report.js
```

浏览器回归脚本为 `tests/dashboard_browser.cjs`。需要 Node 能找到 Playwright（可通过 `NODE_PATH` 指向现有工具安装），并能启动对应浏览器；不需要新增应用运行依赖。本机复验参数：

```powershell
$env:NODE_PATH = 'C:\Users\梁道\AppData\Local\npm-cache\_npx\e41f203b7505f1fb\node_modules'
$env:DASHBOARD_PYTHON = 'D:\test area\greedy-failure\greedy-failure-structures\.venv\Scripts\python.exe'
$env:DASHBOARD_BROWSER_CHANNEL = 'chrome'
$env:DASHBOARD_HEADED = '1'
node tests/dashboard_browser.cjs
```

工具缓存路径属于本机，应按使用者实际安装调整；不设置 browser channel 时使用 Playwright 自带 Chromium。
脚本自动使用空闲端口、启动隔离服务并在结束后关闭；所有小型实验在其临时项目内执行。

## 本地证据与范围

浏览器检查结果与临时项目路径保存在 [browser-checks.json](../output/playwright/browser-checks.json)。
视觉检查包括 [桌面首屏](../output/playwright/home-1366.png)、[窄屏入口](../output/playwright/home-390.png)、
[窄屏结果选择](../output/playwright/results-390.png)、[真实生成报告](../output/playwright/report-real-benchmark.png)。
项目检查详见 [日志](../output/playwright/project-check-fast-env.log)。这些为忽略的本地证据；跨机器交接应附带此目录，而不是声称已随 Git 发布。

所有改动限定在 dashboard 展示/交互、必要服务元信息、说明与回归；算法、种子、CSV schema、实验身份和恢复语义未修改。
未开展大型实验、CUDA 硬件验收、完整跨平台 full profile 或远端 CI。浏览器里的结果夹具用于交互验证，不作为研究成果。
没有自动翻译科研报告，也没有实现任意 Markdown 扩展；原文下载保留完整输入。

## PR 主线整合验证（2026-09-13）

以 `dcfd2221` 为基线整理界面提交后，默认项目检查运行 514 项：509 项通过、5 项按既有条件跳过，mypy 检查 42 个源码文件通过。跳过项为可选 Matplotlib、OR-Tools、两项显式 CUDA 检查与 POSIX 专用虚拟环境检查；必需研究验证均执行。

既有浏览器脚本的 23 个场景在本候选上再次通过。独立复核另完成 4 项同源/跨源 HTTP 检查、2 项 CSV 索引检查及 5 组真实 Chrome 行为验证，覆盖合法实验、非法名称、有效/坏回放、结果读取失败恢复和报告正文；没有阻塞发现。

候选保留 main 已有的 HTTP 请求辅助测试修订，稳定化和开发收口文档没有回退。原实现分支保持原样；这批检查用于本次 PR 候选，不替代远端 CI，也不扩大原研究或 GPU 验收范围。
