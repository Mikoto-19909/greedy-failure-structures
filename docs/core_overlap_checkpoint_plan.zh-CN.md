# 高重叠结构对照实验执行计划

记录日期：2026-09-05。

状态：配置与离线分析已实现，正式实验尚未执行。本文中的样本数、参数和阈值都是
预定设计，不是测量结果。实验准备包含固定配置、输入校验、配对统计、Matplotlib
图和合成输入测试；正式运行与证据冻结作为后续独立批次。

本轮实施起点为 `5ae4e8574dc0c50349e754d9462480168d132de2`，包含已合并的
PR #21 配对修复，以及 [准备 PR #27](https://github.com/Mikoto-19909/greedy-failure-structures/pull/27)
统一后的计划。第 2 节保留最初核对时的历史状态；正式运行另记实际完整提交 SHA。

## 1. 本次要回答的问题

在元素数、候选集合数、选择预算和理论期望集合大小匹配时，共核式高重叠
生成机制是否比 uniform 对照更容易让 Greedy 出现非零 optimality gap
（算法覆盖量与最优覆盖量之间的差距）？

完成一次预先固定的单点配对实验，得到失效率差、配对计数和辅助 gap 指标。
正向、反向和证据不足的结果都可以完成检查点；不以得到显著正效应作为完成条件。

本轮只比较 `high_overlap` 与 `uniform`，使用 Greedy 和小实例穷举参考。
不扫描强度，不增加算法或生成器，不研究运行时间，不扩展 dashboard、
cartography、公共 schema 或 CI。文档精简和源码拆分不构成本实验的前置条件。

## 2. 现有实现与执行起点

本计划核对的主分支是
[`ddf6a8a`](https://github.com/Mikoto-19909/greedy-failure-structures/commit/ddf6a8a9a9c2e6928c45aa158fb97da13b24e654)。
核对时 [PR #21](https://github.com/Mikoto-19909/greedy-failure-structures/pull/21)
仍为 open，分支头为 `4ba3b74947a802e63041e786496171a6c5a01547`。
这些是记录时的状态，开始实施时应重新确认。

PR #21 加固的是 `paired_seed_analysis.py` 的输入检查：读取实例记录中的
有效 seed，将实际读取的两份 CSV 绑定到 benchmark manifest 声明的哈希，
并拒绝不支持的 manifest 版本。有效 seed 的定义是：存在 `coupling_seed`
时采用它，否则采用实例 `seed`。校验和一致说明文件与声明一致，不能单独证明
统计计算正确，也不能防止文件和声明一起被修改。

执行前在原 PR 收尾“有效 coupling seed 相同、原始实例 seed 不同的合法配对
仍被后续检查误拒绝”的审查问题，遵循现行审查和提交要求。
正式运行使用包含该收尾修复的固定 commit，记录完整 SHA 和 `dirty=false`。
本计划文档可以先独立提交，不把 PR #21 的代码变更混入本次文档提交。

本轮选择普通 `benchmark`，原因可从现有实现直接核对：

- [`cartography.py`](../src/maxcover/cartography.py) 的设计加载器要求六类结构、
  每类多个强度以及五种启发式算法，不适合这次单点实验。
- [`generators.py`](../src/maxcover/generators.py) 中 `controlled_high_overlap`
  使用共同核心和互不相交、等大的集合专属边缘。按这个构造推导，任意 k 个集合
  的并集大小相同：核心大小加 k 倍边缘大小。因此它不承担本次待检验的处理组。
- [`pairing_paired.json`](../configs/pairing_paired.json) 已有可复用的
  `high_overlap` 与 uniform 参数配对。
- [`paired_seed_analysis.py`](../src/maxcover/paired_seed_analysis.py) 比较 paired
  与 unpaired 两套实验的差值方差。本次研究失效率差，不能直接把那个模块的
  输出当作本研究结果，也不为调用它额外运行一套 unpaired 实验。

## 3. 固定配置

[`configs/core_overlap_pilot.json`](../configs/core_overlap_pilot.json) 采用下面完整内容，
保留已有配置及其身份；开始查看算法结果前提交配置和分析脚本。

```json
{
  "schema_version": 3,
  "name": "Core overlap matched-control pilot",
  "base_seed": 7401,
  "repetitions": 30,
  "algorithms": [
    { "name": "greedy" },
    {
      "id": "exact_reference",
      "name": "brute_force",
      "options": { "max_set_count": 16, "time_limit_seconds": null }
    }
  ],
  "cases": [
    {
      "name": "overlap",
      "seed_group": "core_overlap_pilot",
      "family": "high_overlap",
      "universe_size": 48,
      "set_count": 16,
      "k": 4,
      "core_fraction": 0.5,
      "core_probability": 0.8,
      "peripheral_probability": 0.05
    },
    {
      "name": "overlap_control",
      "seed_group": "core_overlap_pilot",
      "family": "uniform",
      "universe_size": 48,
      "set_count": 16,
      "k": 4,
      "density": 0.425
    }
  ]
}
```

预期执行计划是 30 个种子对、60 个实例、120 条算法运行记录。
每个实例穷举全部 `C(16, 4) = 1820` 个四集合组合；不设置穷举超时。
`max_set_count` 是 runner 的执行上限选项，不是直接传给 `brute_force()` 的参数。

实施时发现原示例省略 `time_limit_seconds` 会继承执行配置的默认超时，
与本节“不设置穷举超时”冲突。因此在查看任何正式算法结果前显式设置为 `null`，
并重新固定配置哈希；实例参数、样本数和种子批次不变。

两组理论期望集合大小约为 `24 × 0.8 + 24 × 0.05 = 20.4`，
uniform 的密度据此取 `20.4 / 48 = 0.425`。
生成器的非空修补带来极小的期望修正，实际集合大小仍有随机波动。
这里没有逐实例强制匹配 incidence（集合成员关系总数）。

`base_seed=7401` 与原配对审计配置的 `4401` 分开；本次不根据结果挑选 seed。
runner 根据 base seed、seed group 和 repetition 派生实例 seed；
不能把 `7401..7430` 当作实际实例 seed 手工填入结果。
每对使用相同有效 seed，不同 repetition 是独立抽样单位。
沿用 Greedy 的低索引 tie-breaking（增益相同时优先选择较小索引），
不置换集合顺序，不为确定性算法配置 `algorithm_seeds`。

## 4. 后续实施的最小文件集合

| 文件或位置 | 需要完成的工作 |
| --- | --- |
| `configs/core_overlap_pilot.json` | 保存上述固定配置。 |
| `analysis/core_overlap_pilot.py` | 一个针对该实验的离线汇总脚本，读取现有 canonical CSV，输出配对表、简短报告和一张图。 |
| `results/core_overlap_pilot_v1/` | 完整 benchmark 输出，继续 gitignored。 |
| `results/core_overlap_pilot_v1/analysis/` | `paired_instances.csv`、`report.md`、`failure_rate.svg`、`validation.md`。 |
| `experiments/core_rq/` 与 `analysis/` | 实验完成后，按第 8 节冻结最小证据及外部说明。 |

分析代码不进入 `src/maxcover/`，不新增 CLI 子命令、注册器或通用报告框架。
数据处理和精确检验使用 Python 标准库；静态图使用 matplotlib，作为离线绘图
依赖，不加入项目运行依赖。计算脚本与绘图可以在同一文件中完成。

## 5. 数据读取、配对和分析口径

### 输入验收

先在完整输出上执行现有 `validate_benchmark_output.py` 并取得 PASS。
随后离线脚本执行以下与本实验直接相关的检查，全部通过后再创建分析输出：

1. 将 `instances.csv`、`raw_results.csv` 读成字节，完成下面的哈希检查后，
   从同一份字节解码并用 `InstanceRecord.from_csv_row` 和
   `RunRecord.from_csv_row` 解析，配置由现有 `load_config` 读取。
   benchmark manifest 当前支持的 `schema_version` 为整数 `1`；
   `true`、浮点数和其他版本均拒绝。它与配置的 schema `3` 是不同层次。
2. 对实际读取的 CSV 字节计算 SHA-256，与
   `manifest.outputs[filename].sha256` 比较；同时确认两份 CSV 的
   `config_hash` 与加载的配置、manifest 一致。记录本次使用的 manifest 哈希。
3. 要求恰好两个预定 case、repetition 完整覆盖 `0..29`。
   `(config_hash, case_id, repetition)` 唯一确定实例；通过 `instance_id`
   将运行行连回实例。每个实例恰好有 Greedy 和 `exact_reference` 各一行，
   算法名分别为 `greedy`、`brute_force`，且无 algorithm seed。
4. 按配置中的 case 角色和 repetition 组成配对，不依赖 CSV 行顺序。
   每对核对维度和有效 seed；本配置没有启用 coupling 参数，
   因而有效 seed 应等于各自实例 seed。共享数值不等于任何生成器组合都逐抽样对齐，
   也不保证配对必然降低方差。
5. `exact_reference` 必须为 `optimal`，具有正的覆盖量；Greedy 必须是完成且
   有效的可行结果。Greedy 的 `feasible` 状态本身不表示失手。
   同一实例的 `optimum` 必须等于其穷举覆盖量，且 Greedy 覆盖量不得超过它。
   按固定 case 和派生 seed 重新生成实例，分别重算 Greedy 与穷举参考的
   `selected` 集合并集，要求它等于各行声明的 `coverage`。这项检查验证选解
   的可行覆盖量，不重新执行算法，也不单独证明参考最优性。

实施补充：PR #28 的后续审查指出，既有完整输出验证器对本配置不核对选择集合
与覆盖量的一致性。发布结果前补上上述可行解检查；保留首次运行目录，修复提交
固定后以同一配置和种子重跑到新目录。统计口径和抽样决定保持不变。

任何实例缺失参考、状态异常、重复或配对不完整，都作为执行问题停止分析。
本规模要求全部 60 个参考完成，不能静默删行后改用较小分母。
现有验证器校验其声明范围内的一致性；不能将 PASS 描述为重新穷举证明了所有最优值。

### 每对保存什么

`paired_instances.csv` 固定为每个 repetition 一行，按 repetition 升序输出。
至少保存：配置哈希、repetition、两边的 case ID、instance ID、有效 seed、
Greedy 覆盖量、穷举最优值、失手标记、相对 gap，以及以下结构字段的两边取值：

- `pairwise_overlap_mean_jaccard`：平均两集合 Jaccard 重叠度；
- `actual_density`、`mean_set_size`：实际密度与平均集合大小；
- `covered_element_count`：所有候选集合的并集大小；
- `coverage_skew_gini`：元素被覆盖频率的集中程度。

原始 CSV 中已经有这些字段，不修改实例 schema，也不新算一套同名结构指标。
报告各组结构指标的均值、最小值、最大值与配对均值差。
核对处理组的平均 Jaccard 是否确实高于对照；若没有，报告处理未形成预期结构差异，
保留这批结果，不换 seed 重试。密度、并集和集中程度的移动一并披露，
不按观测到的密度差删选“更好看”的配对。

### 主指标：失效率差

对每个实例，使用整数覆盖量判定：

```text
failure = int(greedy_coverage < exact_optimum)
relative_gap = (exact_optimum - greedy_coverage) / exact_optimum
```

不要以格式化后的 `optimality_gap` 是否大于某个浮点阈值判定失手。
配对计数定义如下，第一位始终指处理组：

| 计数 | 高重叠组失手 | uniform 对照失手 |
| --- | --- | --- |
| `n00` | 否 | 否 |
| `n10` | 是 | 否 |
| `n01` | 否 | 是 |
| `n11` | 是 | 是 |

四格之和必须等于 30。处理组失效率为 `(n10+n11)/30`，
对照失效率为 `(n01+n11)/30`，主效应为 `delta_failure=(n10-n01)/30`。
独立抽样单位是 30 个种子对，不能把 120 条运行行当作样本数。

预先采用双侧精确 McNemar 检验（比较失手方向不一致的配对是否偏向某一侧），
阈值 `alpha=0.05`。不使用卡方近似，不在看到结果后改为单侧检验。
核心计算可以直接使用标准库：

```python
from math import comb

discordant = n10 + n01
if discordant == 0:
    p_two_sided = 1.0
else:
    tail = sum(comb(discordant, i) for i in range(min(n10, n01) + 1))
    p_two_sided = min(1.0, 2.0 * tail / (2 ** discordant))
```

只有这一项主检验。始终报告四格计数、两组分子与分母、差值和精确 p 值；
不只报告“显著”两个字。30 对是探索性设计，不代表已做功效保证。
没有不一致配对时，p 值为 1，不能据此证明两个总体等价。

### 辅助指标与解释

对全部 30 对计算 `delta_gap = mean(gap_treatment - gap_control)`，
同时报告各组平均相对 gap。包括所有零 gap 实例，不只分析失手子集。
辅助指标用于说明损失幅度，不另做一组显著性搜索。

在输入和结构检查有效的前提下，按以下规则写结论：

| 观察 | 本轮可以写的判断 |
| --- | --- |
| `delta_failure > 0` 且 `p < 0.05` | 该固定参数配置下，处理组失效率较高，配对样本提供方向性证据。 |
| `delta_failure < 0` 且 `p < 0.05` | 该固定参数配置下，处理组失效率较低，观察方向与原假设相反。 |
| `p >= 0.05` | 报告样本差值；本轮未获得足够的失效率差异证据。 |

结论对象是这两种生成机制在固定参数下的比较。期望密度匹配没有固定
集合大小分布、可覆盖并集或集中程度；不能改写成“只有重叠度导致了差异”。
单点比较也不支持“重叠越高越容易失手”的强度趋势或对其他规模的推广。

## 6. 执行顺序与命令

以下命令均在仓库根目录执行，适用于 Bash 和 PowerShell。
阶段 A 是准备工作；阶段 B、C 中的配置与分析脚本应先按本计划实现并提交。

### 阶段 A：固定实现和分析决定

1. 重新确认 PR #21 的收尾状态，选择包含该修复的分支起点。
2. 新建单一职责的实验分支，加入第 3 节配置和第 5 节规定的离线脚本。
3. 实现脚本接口：
   `python analysis/core_overlap_pilot.py --config PATH --results DIR --output DIR`。
   该接口已由 [`analysis/core_overlap_pilot.py`](../analysis/core_overlap_pilot.py) 实现。
   脚本沿用 `run_project.py` 的源码导入方式，将自身所在目录的上一级下的
   `src/` 加入模块搜索路径，确保未安装项目包时也能直接执行。
   绘图环境可用 `python -m pip install matplotlib` 准备，并在运行记录中保存版本。
4. 用小型合成配对表核对四格计数与检验公式；覆盖没有不一致配对、
   两个方向互换、相同失败率但 gap 幅度不同等情况。
   用损坏输入确认缺行、重复实例、有效 seed 不符、哈希不符、版本不支持及
   非 optimal 参考会被拒绝。围绕这些具体风险验证，不新增通用测试框架。
5. 执行现行仓库检查。分析脚本包含输入规则检查，应按 AGENTS 的要求获得
   独立反向核对：从本计划规定的拒绝条件构造输入，并实际验证拒绝。
6. 提交配置、分析脚本及必需的许可证清单更新后，再进行正式运行。
   查看 `git status --porcelain` 确认干净，并保存 `git rev-parse HEAD`。

### 阶段 B：运行并验证完整输出

```console
git branch -a
git worktree list
git rev-parse HEAD
git status --porcelain
python --version
python run_project.py benchmark --config configs/core_overlap_pilot.json --dry-run
python run_project.py benchmark --config configs/core_overlap_pilot.json --output results/core_overlap_pilot_v1 --workers 1
python .github/scripts/validate_benchmark_output.py --config configs/core_overlap_pilot.json --output results/core_overlap_pilot_v1
```

dry-run 应显示 2 个 case、60 个实例和 120 条算法运行。
正式运行使用全新输出目录；如果同名目录已有记录，先核对来源，不能覆盖旧结果。
记录验证命令、退出码和实际输出，只有退出码为零才记 PASS。
本轮不需要安装 OR-Tools。若记录缺失或运行失败，先诊断后使用相同配置和 seed
重跑至另一个目录，保留失败记录；不把出错的配对替换成其他随机实例。

### 阶段 C：汇总和形成一页报告

在离线绘图环境提供 matplotlib 后，执行已实现的分析脚本：

```console
python analysis/core_overlap_pilot.py --config configs/core_overlap_pilot.json --results results/core_overlap_pilot_v1 --output results/core_overlap_pilot_v1/analysis
```

报告先列固定实验范围和输入验收，再列结构诊断、失率与 gap 结果，最后写限定结论。
`failure_rate.svg` 只画两组失效率，纵轴固定为 0 到 1，标注失手数与分母；
配对检验和解释放在旁边的表格中，不由两根柱子的距离代替统计判断。

`validation.md` 记录源代码 SHA、Python 版本、配置哈希、实际执行命令与结果、
benchmark manifest 和输入 CSV 的 SHA-256、分析脚本及分析产物的 SHA-256，
并注明独立核对了哪些统计计算。沿用普通 Markdown 记录，不新建 manifest schema。
新分析表和图不属于现有 benchmark validator 的验证范围，必须明确说明。

## 7. 停止条件

完成 30 对后结束本轮，不根据 p 值或效应方向持续追加样本。
数据有效但差异不明显时，保存“不确定”的结果，并用本轮计数另行制定后续样本量；
后续扩样使用单独预定的种子批次与分析决定。

只有数据或实现错误需要修复重跑。结构指标未按预期移动时，报告本次处理设计的
限制；密度、并集或集中程度发生移动时缩小结论范围。
这些观察都不自动授权增加生成器、回归模型、强度网格或基础设施。

## 8. 证据冻结与提交范围

完整运行和分析先留在 `results/`。得到有效结果后，按
[`CONTRIBUTING.md`](../CONTRIBUTING.md) 的现行规则公开一条有限结论；
证据不足或反向结果也可以成为如实陈述的实验结果。

建议冻结到 `experiments/core_rq/overlap_pilot_v1/`：

- 配置副本 `config.json`；
- 未改写的 `instances.csv`、`raw_results.csv`、`reference_status.csv`、
  `greedy_failure_statistics.csv` 和 benchmark `manifest.json`；
- `paired_instances.csv` 与 `validation.md`。

外部说明放入 `analysis/overlap_pilot_v1.md`，图保存为
`analysis/overlap_pilot_v1.svg`。图复制或更名时记录原始文件名及相同的哈希。
使用 [`CLAIMS.md`](../experiments/core_rq/CLAIMS.md) 中下一个可用 claim ID，
绑定确切行、过滤条件、主指标与辅助指标、配置、图和验证记录；不提前填入结果。

如果生成的 manifest 包含个人绝对配置路径，按 CONTRIBUTING 的现行办法，
在完整本地输出中将 `configuration.path` 改为仓库相对的 `config.json`，
重新执行原验证器，再更新分析记录中的 manifest 哈希后冻结。
除这项已允许的路径处理外，保留证据原始字节；不裁剪 CSV 后继续沿用旧哈希。

冻结的是证据子集，manifest 仍可能列出未复制的其他 benchmark 产物。
现有完整输出验证命令应在原完整目录或重新生成的完整目录上重跑，
不能声称它能直接验证这个精简目录。验证记录写清 PASS 对应的目录与文件范围，
提供第 6 节重跑命令，并区分确定性字段与会随重跑变化的时间、环境和 manifest 字段。

发布时更新 claim 台账与分析入口，按需更新文档链接和许可证清单。
保持 `results/` gitignored，历史迁移清单不变；不在 commit message 或 release note
中写研究数字。实验脚本、证据与正文按单一职责组织提交，不混入其他维护计划。

## 9. 完成检查

- 配置、种子批次、分析口径与代码版本在正式查看结果前固定。
- 60 个实例均有有效最优参考，30 对完整；配对、输入绑定和现有验证均通过。
- 结构诊断、四格计数、失效率差、精确 p 值及包含零值的平均 gap 差可追溯。
- 报告明确区分样本观察、统计证据、生成机制解释与尚未检验的推广。
- 一页报告、配对表和一张图已经产生；如公开结论，冻结证据与 claim 映射已核对。
- 达到上述条件后结束本轮，下一问题由实际结果决定。

现行仓库提交检查以 CONTRIBUTING 和 AGENTS 为准。本计划不增加任何常设门禁。
