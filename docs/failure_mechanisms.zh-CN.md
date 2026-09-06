# 结构压力因子与 Greedy 失败机制

先看固定的 `high_overlap` 对 `uniform` pilot，再按具体的构造与搜索问题
选用下面的补充工作流。[已完成的 pilot](../analysis/overlap_pilot_v1.md)
没有提供充分的配对证据来支持 Greedy 失效率存在差异。
[实验数据](../experiments/core_rq/overlap_pilot_v1/)

## 高重叠与匹配的 uniform 对照

pilot 检验的问题是：共核式生成机制是否让 Greedy 比 uniform 对照更容易
错过最优解。其[固定配置](../configs/core_overlap_pilot.json)对齐了维度和
理论期望集合大小，按配置的种子批次配对案例，并用已完成的穷举参考与
Greedy 比较。

```console
python run_project.py benchmark --config configs/core_overlap_pilot.json --output results/core_overlap_pilot_reproduction --workers 1
```

换一个新的输出目录运行。[pilot 命令](cli.zh-CN.md#核心重叠-pilot)包含
验证和离线分析；[研究计划](core_overlap_checkpoint_plan.zh-CN.md)定义了
比较方式和停止条件。

**待检验的机制。** 共核让候选集合覆盖大量相同元素。边缘部分和后续的
边际增益决定了 Greedy 能到达哪些组合。收益相等时按下标较小的平局裁决。
共享种子不会自动对齐不同生成器的每一次随机抽取，见
[`paired_seed_audit.md`](paired_seed_audit.md)。

**看什么。** `pairwise_overlap_mean_jaccard` 要和 `actual_density`、
`mean_set_size`、`covered_element_count`、`coverage_skew_gini` 放在一起读。
对齐期望集合大小并不能把这些性质都固定住，所以比较结果不能单独归因于
重叠。观察到的结果既不证明等效，也不证明存在重叠强度趋势或在其他
规模上成立的结论。[实验数据](../experiments/core_rq/overlap_pilot_v1/)

原有的参数扫描仍然可用，对应一个更宽的描述性重叠问题；它的结果与
固定 pilot 相互独立：

```console
python run_project.py benchmark --config configs/p6_overlap_scan.json --output results/p6_overlap_scan
```

`controlled_high_overlap` 服务于另一项构造检查。它的共享核心加互不相交、
等大的边缘，使得任何同等规模的选择覆盖的元素数都相同，因此它不是
pilot 的处理组生成器。对照的细节见
[`generator_isolation.md`](generator_isolation.md)。

## 对抗性 Greedy 陷阱

带证书的 version-2 构造把诱饵集合放在互补块之前。当
`trap_count < block_size` 时，诱饵一开始提供的覆盖量比任一块都大，
但在两块中都留下未覆盖元素。选下它之后，Greedy 无法在剩余预算内
配平互补块；受限的干扰集合也补不回损失。

在允许的端点 `trap_count=block_size` 上，诱饵已经覆盖全集——所以这个
族名并不意味着每个参数取值都会失败。两种情形下 version 2 都提供
已知最优证书。下面的工作流同时保留了旧版构造用于对比。

```console
python run_project.py demo
python run_project.py benchmark --config configs/p6_trap_construction.json --output results/p6_trap_construction
```

demo 的数值算自一个固定的源码内置实例。构造工作流比较的是声明的各
变体和带证书的参考。这个已知构造解释的是一种可能的失败机制；
随机化高重叠假说由它自己的匹配 pilot 评估。

## 补充的结构与搜索工作流

### 重复重型结构

完全相同的副本增加冗余。选中一个副本之后，另一个不再提供新增益，
而更有价值的候选还在。该工作流考察去重和精确搜索的工作量；
用 `duplicate_set_ratio` 识别目标结构。

```console
python run_project.py benchmark --config configs/p4_duplicate_heavy.json --output results/p4_duplicate_heavy
```

### 被支配集合

在相同当前覆盖下，严格子集的边际增益不大于其超集。该工作流研究
支配消除和精确搜索，包括解是否仍引用原始集合索引。
看 `dominated_set_ratio` 和子集关系。

```console
python run_project.py benchmark --config configs/p4_dominated_heavy.json --output results/p4_dominated_heavy
```

### 长尾覆盖集中

集中覆盖可能带来较大的早期增益和较弱的残余增益。这是否造成 Greedy
差距是个实证问题。配对扫描在固定名义集合大小下改变集中度；
看实际得到的 `coverage_skew_gini` 和精确参考的可得性。

```console
python run_project.py benchmark --config configs/p4_long_tail.json --output results/p4_long_tail
```

### 聚集结构

集合聚集在若干簇内时，早期选择可能过度代表全集的某个区域。该扫描
通过 `clusters`、`within_probability` 和 `outside_probability` 检验这个
假说；配置本身并不保证每个生成的实例都失败。

```console
python run_project.py benchmark --config configs/p6_clustered_scan.json --output results/p6_clustered_scan
```

### 受控压力因子审计

对受控构造，检查目标单调性、匹配对照、维度与关联数是否固定，以及
其他指标的移动：

```console
python run_project.py audit-stressors
python run_project.py benchmark --config configs/p7_controlled_stressors.json --output results/p7_controlled_stressors
```

审计契约见 [`generator_isolation.md`](generator_isolation.md)。
较旧的 P4/P6 配置保留各自的维度和参数语义，不要假设它们的关联数
在扫描中不变。

## 解读输出

上面的 benchmark 命令都包含精确参考候选。一条以 `status=optimal` 完成的
精确运行，或一份经独立验证的构造证书，才能提供参考最优值；只有可行或
超时的 incumbent 不行。除了状态还要看停止元数据：`feasible` 本身不代表
执行已完成。

`configs/sweeps.json` 只含 Greedy 和 Local Search，没有精确参考。
它支持配置展开、结构指标和原始覆盖量查看；仅靠它的输出无法确立
精确参考下的近似比或 Greedy 失效率。

CSV、报告和图表的语义见 [`output_schema.md`](output_schema.zh-CN.md)，
验证和回放见 [`cli.md`](cli.zh-CN.md)。研究流程和文档大纲维护在
[`CONTRIBUTING.md`](../CONTRIBUTING.md)。
