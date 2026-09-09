# R4 L5 DUAL 使用说明

本入口实现 [固定比较设计](r4_dual_design.zh-CN.md)中的 Method 4 + Method 3。
完整 1,800 图/13,000 预算比较已完成，实际结果和成本见[比较报告](r4_dual_comparison_report.zh-CN.md)。
使用 Python 3.12；此机器可执行文件为 `.venv\Scripts\python.exe`。不依赖 LP 求解器。
生产器扫描交点，独立验证器显式重建每个残余并计算每轮最大值。

## 预检与固定比较

先执行独立预检。参数、资源预测和实际通过状态保存在预检输出；它不启动正式比较。

```powershell
& .\.venv\Scripts\python.exe analysis/r4_dual_preflight.py --output results/r4_dual_preflight_v1
```

预检默认使用独立生成的本地输入，不需要已发布证据仓库。只有显式传入
`--source-repository <本地证据仓库路径>` 时，才额外测量固定 Git 配置对象的读取成本；
指定的仓库缺失或不含所需固定对象时仍会报错。省略此选项时，报告中的
`immutable_config_transport_setup_seconds` 为空列表，不代表已测量 Git 传输成本。

正式来源目录必须是包含固定提交 `1a8b1899d927cba202cf7931fe992ecd2b5a1807` 的本地 Git
证据仓库。入口直接读取提交对象，不接受修改后的同名工作树文件替代旧输入/参考。
独立配置 `analysis/r4_dual_config.json` 在预检通过并完成源码提交后定版。

完整 [DUAL 配置](https://github.com/Mikoto-19909/greedy-failure-structures/blob/b0c274f6be0d810b873184f0e81af41039f1a300/analysis/r4_dual_config.json)
已随固定证据发布，源码分支不再重复跟踪展开的任务列表。完整克隆保留原设计提交，
仅在本地配置缺失时恢复到已忽略的原路径；已有配置和批次不要覆盖。
该命令只恢复工作区文件，不改索引。浅克隆须先取得该完整提交历史。

```powershell
git restore --source=0bf8a588c22f8b0cf238ee879bc6377187a4c605 --worktree -- analysis/r4_dual_config.json
```

```powershell
& .\.venv\Scripts\python.exe analysis/r4_dual.py run --config analysis/r4_dual_config.json --source results/frozen-r4-calibration-v1 --output results/r4_dual_comparison_v1
& .\.venv\Scripts\python.exe analysis/validate_r4_dual.py --source results/frozen-r4-calibration-v1 --output results/r4_dual_comparison_v1
& .\.venv\Scripts\python.exe analysis/r4_dual.py analyze --source results/frozen-r4-calibration-v1 --output results/r4_dual_comparison_v1
& .\.venv\Scripts\python.exe analysis/validate_r4_dual.py --output results/r4_dual_comparison_v1 --summaries-only
```

若生产中断，在第一条命令末尾增加 `--resume`，使用原配置、来源和输出目录。
`--stop-after N` 可在完成 N 张待生产原图后安全保存阶段检查点；它不是缩减正式语料。
完整验证和汇总命令可以原样重跑，重新计算当前证书及派生结果，计入累计预算。
恢复时先核验已有检查点且保留其字节，损坏/不完整/错来源的数据拒绝继续。

## 输出与解释

`graphs/<base_graph_id>.json` 保存原始来源关联和全部预算的新证书。每个条件保留原索引
排序、s、F、q 和条件界，q 始终覆盖完整 k。`run_status.json` 只记录生产状态；完整性
以配置预定图/预算、实际文件和独立核验为准。

`verification.json` 保存逐图独立核验与来源/证书/参考成本；`analysis_status.json`
记录当前数据重查、汇总和写表成本。`budget_results.csv` 为逐图/预算配对表，
`cell_summary.csv` 为 `(N,d,k)` 单元汇总，`summary_verification.json` 只证明派生一致性。
完整完成要求独立证书检查与派生核对同时通过，不能只看某个 passed。
`summary_verification.json` 记录最近一次派生核验结果。之后若表被改动或分析重建失败，
旧 `passed` 不是当前表有效的证明；分析完成状态以 `analysis_status.json` 为准，
必须重新执行 `--summaries-only` 核验当前表。预检恢复也会重新核对派生数据，
不会仅凭旧验证状态放行。保留该历史记录不表示失败的重建已经完成。
`execution.jsonl` 保存累计入口时间；预检及外部进程墙钟另存，用于区分分量和总成本。
`active_operation.json` 与操作系统独占锁保护正在运行的阶段。硬退出后仅在进程确已退出时
恢复；已测 `wall_seconds` 和用于限制的 `charged_wall_seconds` 分开，未知尾段保守计费
可包含停机时间，不能当作实际运行时间。不要手工删除这些状态来绕过限制。
正式入口核对执行代码与配置的 `code_revision`，后续文档提交可以保留，计算或输入代码
变化须另说明并重新核验，不能让改后的实现沿用原源码标签。

三种界满足 `G≤O≤DUAL≤prefix≤initial≤B`。G/U 是质量下界，U>G 不证明 Greedy 失效。
等长集合上三种界认证集合相同，所以新增认证不是本方法的收益指标。
零分母比例为空，保留缺失计数。完整固定比较是旧语料回顾，不能解释成新样本确认。
正式参考来自已发布独立穷举结果；本次重新核对见证覆盖及来源，不重新求解全部精确 O。

有意缩短前缀、将完整 k 换成 k−t、仅提供可行而非最大 q、改动来源或伪造完成状态都会
被拒绝。资源耗尽会保留已保存图，不能通过更换目录或改预算偷偷继续原批。
本轮完整证据已发布并完成远端回读，见
[固定快照 b0c274f6](https://github.com/Mikoto-19909/greedy-failure-structures/tree/b0c274f6be0d810b873184f0e81af41039f1a300)
及其中的[恢复说明](https://github.com/Mikoto-19909/greedy-failure-structures/blob/b0c274f6be0d810b873184f0e81af41039f1a300/results/r4_dual_backup_v1/RESTORE.md)。
本机仍保留工作副本；功能提交本身不代替上述固定证据备份。
