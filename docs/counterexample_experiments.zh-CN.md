# 用反例工具做实验

日常操作统一使用 `counterexamples.ps1`。它自动寻找 Python，默认给每次运行新建结果目录，
并调用已有独立验证器。先做一遍下面的小实验，再替换数据或猜想。

## 进入工作树，跑两个已有例子

在 PowerShell 中：

```powershell
Set-Location 'D:\test area\greedy-failure\greedy-failure-structures\.worktrees\counterexample-miner'
.\counterexamples.ps1
.\counterexamples.ps1 mine
.\counterexamples.ps1 refute
```

第一条工具命令显示帮助；`mine` 从已有 R1 数据挑出反例并缩小；`refute` 搜索内置等长集合猜想。
无需记住虚拟环境路径，无需手工选择输出目录。脚本优先使用当前工作树 `.venv`，
再尝试项目主目录的 `.venv`，最后查找 PATH 中的 `python` 或 `py`，要求 Python 3.11+。
其他平台可以用 `python counterexamples.py` 替换 `.\counterexamples.ps1`。

结果写在当前工作树 `results/counterexamples/` 下，每次一个带时间的独立目录。
终端会打印结果目录、`README.md` 路径和一条可复制的 `show` 命令。
显式传 `--output` 时仍要求目录不存在，避免覆盖上一次实验。

## 实验一：从真实样本中找一个能讲清楚的案例

```powershell
.\counterexamples.ps1 mine --top 3
```

默认只读取 R1 文件中 `population=pilot` 的 60 个实验实例，重新计算 Greedy 和精确最优解。
当前这批样本中会找到 22 个反例，按原始相对损失选前 3 个，再尝试缩小。
6 个功能夹具不进入默认计数。

阅读结果时依次看：

1. **来源**：`pilot`、case 和来源记录号，确认它是哪一个原始实验实例。
2. **原始 G/O**：例如 `31/33` 表示原始 Greedy 覆盖 31、最优覆盖 33。
3. **缩小后的尺寸和 G/O**：只用来解释机制。缩小可能改变集合大小、频数和平局情况。
4. **缩小状态**：“单步删减已完成”只排除了指定的单步删除；“预算耗尽”表示还没检查完。

复制终端打印的实际目录，查看编号 1 的集合和选择过程：

```powershell
.\counterexamples.ps1 show 'results/counterexamples/实际的mine目录' --rank 1
```

`show` 会先独立重算，再显示每个集合、Greedy 每步新增覆盖和平局候选、最优选择见证。
若想先快速筛选而不缩小，将删减预算设为 0：

```powershell
.\counterexamples.ps1 mine --max-evaluations 0
```

用自己的输入时显式指定路径；此时默认处理该文件的全部实例，可以额外按来源标签筛选：

```powershell
.\counterexamples.ps1 mine --input 'experiments/r1c_confirmation_v1/paths.jsonl' --top 3
.\counterexamples.ps1 mine --input 'my-data/paths.jsonl' --population pilot --top 3
```

自定义输入也可以是项目标准的单实例 JSON。若文件没有 `population` 字段，就不加来源筛选。
想检查 R1 功能夹具时用 `mine --population fixture`；确实要同时处理实验样本与夹具时用
`mine --population all`，报告会逐例保留来源。筛选标签拼错会报错，不会悄悄生成空报告。

## 实验二：检验一个明确的结构猜想

先把自然语言写成可检验的形式，例如：

> 在全集大小 4、3 个互不相同的集合、每个集合大小 2、选择预算 k=2 的条件下，
> Greedy 是否总能达到最优覆盖？

生成一份自己的设计，然后运行：

```powershell
.\counterexamples.ps1 design 'designs/my_equal_size.json' --n 4 --m 3 --k 2 --size 2 --ratio 1
.\counterexamples.ps1 refute --design 'designs/my_equal_size.json'
```

`design` 默认要求集合互不重复，默认候选预算 10,000；创建已有文件会报错。
若想允许重复，加 `--allow-duplicates`；集合大小不限用 `--size any`；
每个元素最多出现两次用 `--max-frequency 2`（不等于“恰好两次”）。

该例会在第 3 个候选找到：

```text
S0={0,1}, S1={0,2}, S2={1,3}, k=2
Greedy 先按平局规则选 S0，再选 S1，覆盖 3。
最优选择 S1 和 S2，覆盖 4。
```

三个集合确实等长且互不重复，因此这是该猜想的有效反例。
这里使用项目标准 Greedy：边际收益相同时选最小索引；没有穷尽所有平局选择路径。

## 实验三：只改变一个要求，比较结论

保留上面的设计，不改源文件，只改变这次运行的比例要求：

```powershell
.\counterexamples.ps1 refute --design 'designs/my_equal_size.json' --ratio 4/5
.\counterexamples.ps1 refute --design 'designs/my_equal_size.json' --ratio 3/4
.\counterexamples.ps1 refute --design 'designs/my_equal_size.json' --budget 2
```

- `4/5`（也可以写 `0.8`）：要求至少达到最优覆盖的 80%。同一个 `3/4` 案例仍然是反例。
- `3/4`：本例完整检查 120 个有序候选后未找到反例。结论仅覆盖这个固定有限域。
- `--budget 2`：只检查前两个候选，搜索尚未完成；不能据此说猜想成立。

每次结果目录中的 `design.json` 和 `search.json` 都保存了这次实际使用的参数，
包括命令行覆盖后的比例与预算。增加预算会从头枚举，不是从上次断点续跑。
等于比例阈值不算反例；判定使用整数运算，不依赖浮点舍入。

## 怎样把结果用于后续研究

若研究 R3 的 E0 与首步不可恢复性，使用新增的保度成对工具：

```powershell
.\counterexamples.ps1 r3-pair --same-optimum
```

它保持逐项两侧度数，分别报告 G、O、强制保留集合 0 的 O1，
并保存可重放交换路径。完整操作与边界见 [R3 保度反例指南](r3_counterexamples.zh-CN.md)。

**找到反例时**：先用 `show` 核验并阅读轨迹，确认实例满足你真正关心的前提。
再检查失败是否来自平局选择、某个诱饵或后续互补性，形成下一条可检验猜想。
“发现反例”和“解释了某类样本的普遍机制”是不同的结论。

**没有找到时**：先看是否完整搜索了指定域，再看满足前提的实例数量。
预算耗尽意味着未完成；前提筛掉了全部实例意味着空域；两者都不能作为猜想成立的证据。
扩大尺寸或改变约束时另建一份设计，保留旧结果供比较。

**需要缩小时**：普通缩小器只保留 `k` 与 `G<O`。
猜想反例不能直接缩小后继续当作同一个猜想的见证，因为等长、频数或固定尺寸可能已改变。
原始见证保存在猜想结果的 `counterexample.json` 中；核验并查看选择过程可使用：

```powershell
.\counterexamples.ps1 show 'results/counterexamples/实际的refute目录'
```

本工具不生成 R2/R3 正式确认样本，也不把选出的反例数当作新分布上的失效率。
实验输入和正式确认数据是否适合某个研究问题，需要在相应实验设计中决定。

命令参数可用 `mine --help`、`design --help`、`refute --help`、`show --help` 查看。
格式与边界细节见 [挖掘/缩小说明](../analysis/counterexamples_usage.zh-CN.md)
和 [猜想搜索说明](../analysis/conjectures_usage.zh-CN.md)。
