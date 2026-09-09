# R3 正式确认：执行与验证

按 [F3 设计](r3_confirmation_design.zh-CN.md)及[冻结配置](https://github.com/Mikoto-19909/greedy-failure-structures/blob/8663e0dcf576ab156535ff7403bb7e4715091357/analysis/r3_confirmation_config.json)执行。
配置中的 `execution_status: not_run` 是 F3 定版时的历史状态，运行状态另存于结果目录；
不得通过修改配置字段改变样本、协议或统计决定。

## 环境与命令

使用 Python 3.12 和[仓库检查依赖](../CONTRIBUTING.md)，执行前核对解释器、版本及
`maxcover.__file__` 指向的源码。先确认冻结的 15,000 个原图/链种子互不重复，并与
R2、R3 探测及历史研究输入分离。正式入口不接受单元测试使用的独立 fixture 配置。

完整配置保存在固定证据快照，源码不再重复跟踪展开的任务列表。仅在本地配置缺失时，
从原提交恢复到已忽略的原路径；已有配置和批次不要覆盖。该命令不改索引，
浅克隆须先取得原提交历史。

```console
git restore --source=cef5b92954571423b10a0c3b56947a4b26400d3c --worktree -- analysis/r3_confirmation_config.json
```

```console
python analysis/r3_confirmation.py run --config analysis/r3_confirmation_config.json --output results/r3_confirmation_v1 --workers 4
python analysis/validate_r3_confirmation.py --output results/r3_confirmation_v1 --workers 4
python analysis/r3_confirmation.py analyze --output results/r3_confirmation_v1 --workers 4
python analysis/validate_r3_confirmation.py --output results/r3_confirmation_v1 --summaries-only
```

每张原图保留四个端点。构造只依据 E0 接受或拒绝，全部构造结束后才计算结果。
独立验证器使用既有的独立交换重放和集合枚举，不调用生产构造、求解或统计函数。
分析入口复算当前加载的同一批记录后再生成表，不以历史 `passed` 放行。

## 输出与恢复运行

`graphs/` 保存每个原图、四条链、接受记录、端点、O/O1、见证、实例身份和耗时。
`base_graph_summary.csv` 一图一行，计算两链平均后的 high−low 差值；
`endpoint_results.csv` 保留 12,000 个端点；`primary_summary.json` 给出预定主估计与区间。
原图验证记录为 `verification.json`，派生一致性检查为 `summary_verification.json`，不能互相替代。

```console
python analysis/r3_confirmation.py run --config analysis/r3_confirmation_config.json --output results/r3_confirmation_v1 --workers 4 --resume
```

恢复运行只计算没有完成检查点的原图，已完成原图保持不变；缺链或不匹配配置会被拒绝。
1 小时累计计算预算覆盖生产、恢复、独立验证、分析与派生验证；预算在任务边界检查，
停止提交新任务后正在运行的单图安全退出。内存上限 6 GiB，结果上限 2 GiB。
缺失或损坏记录不筛除、不补抽替换，不将端点数当作独立原图数。

正式确认不按已见效果增删样本、换主指标、改链长或调整方向判断。
数据发布只选择与报告直接相关的证据，并核对远端提交；不自动上传其他本地文件。
