# R1c：新样本失效机制验证设计

设计日期：2026-09-07。研究基线：`b0935de4cc22849299538c0ee0aa9aa7e334a3af`。
状态：设计与新样本适配已完成，并通过独立种子的预检及功能验证；
正式样本尚未生成或运行。[使用指南](r1c_confirmation_usage.md)给出完整入口。
正式执行前仍需记录实际执行的源码提交及环境。

## 问题与范围

本批回答：在固定的共核式高重叠模型和匹配 uniform 对照中，Greedy 已失败时，
首次失效能由同一步替代平局选择避免的比例是否不同，差值能估计得多准确？

[R1 探索报告](r1_prefix_exchange_report.md)发现上述计数为 8/12 和 0/10。
它们用于提出问题；原 30 对实例及本轮资源预检均不进入正式统计。
本批保留原实例尺寸、生成机制、集合索引和平局规则，仅使用新的种子与样本量。
这是两个指定生成模型的条件比例比较；两组失败子集本身不同，且并集和元素频率等
结构也有差异。因此不将差值解释为重叠的单独因果效应，也不外推到其他规模。

R1c 本轮交付设计、输入配置、样本量核算和资源预检，不交付新样本实测结论。
R2 网格、保度重连、新平局算法及更大交换邻域不属于本批。

## 唯一主指标与判定

沿用 [R1 定义](r1_prefix_exchange_design.md)：`O` 为精确最优覆盖，`G` 为固定
低索引平局裁决的 Greedy 覆盖。对前缀 `P_t`，`O_t` 是包含此前缀的 k 元选择
能够达到的最好覆盖；首次 `O_t<O` 的步骤为 `t*`。

每个原始实例记录两个指示量：

- `F=1` 当且仅当 `G<O`。
- `A=1` 当且仅当 `F=1`，且在 `P_(t*-1)` 上存在另一个最大边际候选，追加该
  候选后仍有覆盖为 `O` 的合法完成选择。未失败实例的 `A=0`。

对组 `g ∈ {H,U}`，令 `M_g=ΣF`、`X_g=ΣA`、`θ_g=P(A=1 | F=1,g)`。
唯一主估计量为 `Δ=θ_H−θ_U`，点估计 `Δ_hat=X_H/M_H−X_U/M_U`，单位为比例，
报告时乘 100 转为百分点。`θ_H`、`θ_U` 和各自分子、分母必须一起报告。
任一 `M_g=0` 时，该条件比例及差值点估计标为“不可估计”，不填 0，也不作方向判断。

每组分别计算 **97.5% 双侧 Clopper–Pearson 区间** `[L_g,U_g]`：

- `0<X_g<M_g`：`L_g=BetaQuantile(0.0125; X_g,M_g−X_g+1)`，
  `U_g=BetaQuantile(0.9875; X_g+1,M_g−X_g)`。
- `X_g=0` 时下界为 0；`X_g=M_g` 时上界为 1，其余端点仍按上述公式计算。
- `M_g=0` 时使用无信息范围 `[0,1]`，并保留不可估计标签。

主差值区间固定为 `[L_H−U_U, U_H−L_U]`。在各组独立重复抽样的二项模型下，
每个边际区间的覆盖率至少为 97.5%；Bonferroni 不等式使两区间同时覆盖、进而
差值区间覆盖的概率至少为 95%。该构造允许同一对内两组相关，不将两组当作独立
处理，也不需要把两边不相同的失败子集重新配对。代价是区间较保守。

只有完整样本通过验证且两分母均非零，才执行一次预定方向判断：下界 `>0` 支持
高重叠组比例更高；上界 `<0` 支持相反方向；包含 0 表示本批证据不足以确定方向。
不另外运行主 p 值检验，不把“不显著”表述为相同或等效。
目标精度单独按主区间**总宽度不超过 0.20（20 个百分点）**评估，不能与方向证据混为一谈。

精确区间按 [NIST 的二项分布反演定义](https://itl.nist.gov/div898/software/dataplot/refman2/auxillar/exacbino.htm)
计算；联立覆盖使用 [Bonferroni 一般不等式](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm)。
可用 [SciPy 的 exact proportion_ci](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html)
交叉核对端点。本设计不使用原 pilot 的 McNemar 检验替代这个不同分母的条件比例问题。

## 固定样本与种子

[正式配置](r1c_confirmation_config.json)固定 **3,000 对、6,000 个实例、12,000 条
Greedy/穷举运行记录**。每个实例仍为 `N=48,M=16,k=4`。
高重叠组：`core_fraction=0.5, core_probability=0.8, peripheral_probability=0.05`；
uniform 对照：`density=0.425`。两者理论期望集合大小均为 20.4，实际集合大小和
并集不强制相等。保留现有生成器语义，不增加 coupling 参数、去重或集合置换。

`base_seed=20260907`，两组 `seed_group=r1c_confirmation_v1`，repetition 为 `0..2999`。
沿用 `_case_seed`：对 `{"base_seed":20260907,"seed_group":"r1c_confirmation_v1"}`
使用项目 `canonical_json`，取 SHA256 前 8 字节的大端整数，再加 repetition。
实际 seed 范围为 **14525675900305775728..14525675900305778727**，两组逐对相同。
这只是既有随机种子派生约定，不引入文件摘要或新的检查清单。

[预检配置](r1c_preflight_config.json)另用 `seed_group=r1c_resource_preflight_v1`，
固定 32 对，seed 为 **1059126727451084199..1059126727451084230**。
原 pilot 为 **16941105954642047133..16941105954642047162**。
三批范围已逐 seed 核对互不相交。每对是联合抽样单位；每组每对只有一个实例。
相同 seed 表示沿用配对随机流约定，不表示两组产生相同集合。
推断基于这些种子所代表的独立重复生成模型；确定性复现本身不证明随机数独立性。

## 样本量与资源依据

样本量依据是估计精度，不是把旧样本的 8/12 对 0/10 当作真实效应来保证检验功效。
在每组恰有 600 个失败实例时，遍历所有可能的 `X=0..600`，97.5% 精确区间的
最大总宽度为 **0.09293211**，两个区间组合后的最大差值宽度为 **0.18586422**。
相比之下，每组 400 个失败时该最坏组合宽度为 **0.22825295**，未达到 0.20 目标。
正式批次最终必须用实际分子、分母计算实际区间宽度。

规划时采用“每组失败概率至少 0.25”的工作假设；它低于原 pilot 的 12/30 和 10/30，
但**不是已证明的下界**。固定 3,000 对时，两组中任一组少于 600 个失败的概率，
在该假设下由 `2×BinomCDF(599;3000,0.25)` 上界为 **8.02555×10⁻¹¹**，
这个上界不要求两组独立。它只描述失败分母的规划概率，不是区间覆盖率或检验功效。
若实际失败更稀少，精度仍可能不足；完成固定样本后照常结束并报告，不追补失败数。

每实例穷举 `C(16,4)=1820` 个选择，`max_completions=200000`。
一换一沿用现有 `local_search`；随后至多二换二的每次扫描有
`4×12+C(4,2)×C(12,2)=444` 个邻居。严格改善整数覆盖至多发生 48 次，
含终止扫描的保守评估上界为 `49×444=21756`，小于固定预算 `100000`。
每轮包含一换一，等值改善按 `(交换大小,移除索引元组,加入索引元组)` 排序。

2026-09-07 在基线源码、Windows、Python 3.12.14 下，以独立的 32 对预检种子
执行单 worker benchmark、输出验证、R1 计算和独立集合枚举；64 个实例全部通过。
四段耗时分别为 **1.6922、0.7929、0.2118、0.6683 秒**，保存输出约 487,319 字节。
按实例数简单外推 93.75 倍，约 **5.3 分钟、46 MB**；不包含正式适配开发、
独立审查及所有后续报告成本，也不假定大批次耗时线性。正式执行预留 **60 分钟
和 1 GiB 可用空间**。这是操作预算；耗尽时暂停并保留记录，不能按已见结果删样本。
设计阶段的资源预检不输出机制比例汇总。后续适配的功能核验会生成预检统计，
统一标为 `resource_preflight`；不以这些结果调整本设计的主指标或样本量。

上述种子和数值可通过 [设计核验脚本](r1c_design_check.py)重算。该脚本默认只推导
种子和计算统计量，不构造正式实例。仅 `--preflight-output` 会运行固定预检批次。

## 辅助结果、缺失与停止

辅助结果固定为各组 `M_g/3000`、`X_g/3000`、首次失效步骤分布、一换一及至多
二换二累计恢复到最优的数量/比例、交换后仍有 gap 的数量，以及各阶段平均相对 gap。
修复比例的分母为本组原始 Greedy 失败数；平均 gap 包含最优实例的零 gap，
仅 `O=0` 时相对 gap 不可定义，单独报告数量和有效分母。
这些结果用于解释，不另作显著性筛选，也不以其中某项替换主结论。
允许某个替代候选保留最优完成方式，不等于继续 Greedy 一定能完成到最优。

所有 3,000 对都保留。重复内容的实例不删除；不因无失败、无平局、修复不了、
方向相反或 gap 小而排除。不把同一实例的多个前缀、平局候选或交换轮次计作新样本。
不查看累计主区间来提前结束，不按方向或精度追加 seed，不改参数网格。

精确参考必须为 `optimal`，穷举 `time_limit_seconds=null`，不接受 incumbent 代替 `O`。
配置、身份、原集合、已选集合覆盖、完整枚举或独立验证有任一错误时暂停正式报告，
保留错误及原样本身份。修复软件或资源问题后，只重跑/续跑同一批种子；涉及算法
或定义变化则修订设计并重新核验全批，不能只重算不利实例。
样本未全完成时可报告“执行未完成”，但不发布本设计的正式方向结论。
预算耗尽的交换记录不能标作局部最优；按上述有限上界，它应触发实现或资源排查。

## 执行入口与完成条件

以下适配已实现并验证，旧 pilot 的固定输入保护保持原样：

1. 新增 R1c 专用离线入口，绑定正式配置及所有 planned instances/run IDs；
   复用 `analyze_instance` 的计算，新增来源 `confirmation`，不将新数据标成 `pilot`。
2. 复用独立 `expected_path` 的集合枚举方法，另实现新样本输入/原始结果校验。
   它必须检查选集覆盖、exact 状态、完整配对、预算和每个声明字段。
3. 输出逐实例 `F,A,t*`、交换结果和缺失原因，以及 `X_g,M_g,N_g,θ_g`、各组区间、
   `Δ_hat`、主差值区间、实际区间宽度和预定方向判断；单独保存完整轨迹。
   原配置身份和 pair/repetition 必须贯穿原始结果、轨迹与统计，不更改公共 CSV schema。
4. 在功能样例和独立预检上核验零失败、零/全可避免事件、多最优解、缺失/重复配对、
   非 optimal 参考、候选遗漏、预算停止和区间端点。由独立复核者实际执行有效与无效输入。

原有 `greedy_failure_paths.py` 仍调用 `core_overlap_pilot.load_inputs` 并拒绝新配置。
R1c 使用 [r1c_confirmation.py](r1c_confirmation.py) 和
[validate_r1c_confirmation.py](validate_r1c_confirmation.py)，绑定全部预定输入后分析，
在独立验证通过后才发布轨迹及三张汇总 CSV；原始 benchmark 接口及公共 CSV schema 不变。

设计核验及非正式预检命令（仓库根目录；`.venv` 是本次本地环境）：

```powershell
& .venv/Scripts/python.exe -m pip install scipy==1.18.1
& .venv/Scripts/python.exe -B analysis/r1c_design_check.py
& .venv/Scripts/python.exe -B analysis/r1c_design_check.py --preflight-output results/r1c-design/preflight-reproduction
```

预检目录必须不存在，已有结果不会被覆盖。复现需要项目及 Matplotlib 已安装。
正式入口已就绪；原始 benchmark 可按以下命令运行，本次未执行：

```powershell
& .venv/Scripts/python.exe run_project.py benchmark --config analysis/r1c_confirmation_config.json --output results/r1c_confirmation_v1/benchmark --workers 1
& .venv/Scripts/python.exe -B analysis/r1c_confirmation.py --config analysis/r1c_confirmation_config.json --results results/r1c_confirmation_v1/benchmark --output results/r1c_confirmation_v1/analysis
& .venv/Scripts/python.exe -B analysis/validate_r1c_confirmation.py --config analysis/r1c_confirmation_config.json --results results/r1c_confirmation_v1/benchmark --output results/r1c_confirmation_v1/analysis
```

原始结果和轨迹放在 `results/r1c_confirmation_v1/`；正式报告与必要配置/数据由后续
执行批次保存到 `analysis/` 和 `experiments/r1c_confirmation_v1/`，目前这些正式产物不存在。
发布前按 [CONTRIBUTING](../CONTRIBUTING.md)运行相关测试、完整 unittest、mypy 及独立复核。
冻结的是本设计中的样本、指标与规则；执行源码提交和实际环境在正式运行前记录。
软件适配不得顺带改变冻结决定，若确有必要则先修订设计，再运行正式新样本。

本次设计的完成条件：主指标和区间确定，配置与种子明确，精度计算可复算，
资源预检通过，实施前置项及停止规则可执行，相关研究索引区分“设计完成”和“实测完成”。
未来实测的完成条件：全部固定样本通过独立重算，按预定规则报告估计及局限；
发现差异、没有差异证据或精度不足都可以如实完成该研究批次。
