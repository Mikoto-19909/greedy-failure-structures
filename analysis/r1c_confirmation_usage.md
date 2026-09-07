# R1c 新样本分析与独立验证

这组命令读取完整 benchmark 原始结果，重建 Greedy 前缀和交换轨迹，并输出
[冻结设计](r1c_confirmation_design.md)规定的条件比例与差值区间。
支持正式配置和独立预检配置；原 pilot 仍使用原有 R1 命令。
适配已经通过预检和功能验证，正式 3,000 对样本尚未生成或运行。

## 环境与输入

R1c 离线统计使用 **Python 3.12 或更新版本、SciPy 1.18.1**。
SciPy 是本组离线分析的依赖，不加入核心算法的默认安装依赖。
已有 `.venv` 时，在仓库根目录安装：

```powershell
& .venv/Scripts/python.exe -m pip install scipy==1.18.1
```

输入目录必须包含完整的 `instances.csv` 和 `raw_results.csv`。
程序按已冻结的规范化配置身份识别正式或预检批次，重建所有预定实例和运行身份，
检查集合索引、种子、配对、选集覆盖、算法选项、完成状态和精确参考。
任一 `optimal` 记录的覆盖须等于参考最优值，任何声明的上界不得低于参考最优值；
实际最优值仍由后续完整枚举重算，不能仅凭 CSV 的 `optimal` 声明接受。
改动样本量、seed 或其他配置参数会被拒绝，不能把预检输出冒充正式批次。

## 先验证独立预检批次

下面只运行固定的 32 对预检种子。已有完整 benchmark 时可直接从第二条开始。

```powershell
& .venv/Scripts/python.exe run_project.py benchmark --config analysis/r1c_preflight_config.json --output results/r1c-adapter-smoke/benchmark --workers 1
& .venv/Scripts/python.exe -B analysis/r1c_confirmation.py --config analysis/r1c_preflight_config.json --results results/r1c-adapter-smoke/benchmark --output results/r1c-adapter-smoke/analysis
& .venv/Scripts/python.exe -B analysis/validate_r1c_confirmation.py --config analysis/r1c_preflight_config.json --results results/r1c-adapter-smoke/benchmark --output results/r1c-adapter-smoke/analysis
```

预期分析命令显示 `64 instances` 并完成独立验证；最后一条验证命令返回
`PASS: 64 R1c instances, complete trajectories and three summaries`。
预检输出的 `population` 全部为 `resource_preflight`；其中的统计只用于功能核验，
不作为正式证据，不据此更改已经固定的样本和统计规则。

分析目标目录必须不存在。分析先写入同一父目录下的临时目录，由独立验证器重算
并核对全部轨迹及统计后才发布到指定目录；失败时该目标目录不会出现。
已存在的结果目录会被拒绝而非覆盖。独立验证命令只读输入与分析输出。

## 怎样读取输出

- `paths.jsonl`：每实例保存完整集合、前缀、全部平局候选、交换轨迹与停止状态；
  同时保存 `population/config_hash/pair_id/repetition/seed/instance_id` 和两条来源 run ID。
- `instance_summary.csv`：上述连接字段、`F`（Greedy 是否失败）、`A`（首次失效是否
  可由同一步替代平局选择避免）、首次失效步、交换恢复值、评估数和相对 gap。
  `missing_reason=zero_optimum_relative_gap` 表示 `O=0`，仅相对 gap 不可定义。
- `group_summary.csv`：两行，分别给出 `N/M/X`、`theta`、97.5% 区间、失效率、
  全实例中平局可避免比例、步骤分布、交换恢复数/率、停滞数和平均 gap 的有效分母。
- `primary_summary.csv`：一行，包含差值 `delta`、至少 95% 覆盖的区间 `lower/upper`、
  总宽度 `width`、`target_width=0.20`、是否达到精度及预定方向判断。

比例字段使用 `0..1`，差值和差值区间使用 `-1..1`；展示百分点时乘 100。
缺失数值保存为空 CSV 单元格。任一失败分母为零，`delta` 为空、
`estimate_status=not_estimable`、`direction=not_estimable`，该组保留 `[0,1]` 无信息范围。
其余 `direction` 为 `higher/lower/inconclusive`；包含零不表示两组等效。
`precision_met` 为 `True/False`，独立于方向判断。
每组平均 gap 保留最优实例的零值，仅排除相对 gap 未定义的零最优值实例。

所有正式实例都必须完成，程序不对缺失记录作完整案例删减，不生成部分样本的主结论。
独立验证器复用集合并集和受限枚举方法，另行加载并核对原始输入；统计用 Beta 分位数
重新计算，不导入分析程序的轨迹或汇总函数。浮点 CSV 允许有限的舍入误差，
整数、标签、身份、轨迹结构和候选完整性须准确一致。

## 正式运行入口

以下命令供下一轮正式执行使用，本次适配没有执行它们。先记录实际源码提交、
Python/SciPy 版本和完整命令，按设计保留在运行日志或研究报告中。

```powershell
git rev-parse HEAD
& .venv/Scripts/python.exe --version
& .venv/Scripts/python.exe -c "import scipy; print(scipy.__version__)"
& .venv/Scripts/python.exe run_project.py benchmark --config analysis/r1c_confirmation_config.json --output results/r1c_confirmation_v1/benchmark --workers 1
& .venv/Scripts/python.exe -B analysis/r1c_confirmation.py --config analysis/r1c_confirmation_config.json --results results/r1c_confirmation_v1/benchmark --output results/r1c_confirmation_v1/analysis
& .venv/Scripts/python.exe -B analysis/validate_r1c_confirmation.py --config analysis/r1c_confirmation_config.json --results results/r1c_confirmation_v1/benchmark --output results/r1c_confirmation_v1/analysis
```

正式批次预期为 6,000 个实例，`population=confirmation`。遇到中断时，benchmark
可按已有默认 resume 行为续跑原目录；离线分析用新的目标目录重算同批数据。
不要改 seed、样本量或只重算不利实例。来源矛盾或独立验证失败时先修复原因，
不要跳过检查或把部分结果解释为完整研究。

功能测试：

```powershell
& .venv/Scripts/python.exe -m unittest discover -s tests -p test_r1c_confirmation.py -v
```

未安装 SciPy 的环境仍运行输入校验测试，统计相关测试会明确跳过；
必跑的 Ubuntu/Python 3.12 CI 会安装该依赖以执行完整适配测试。
