# Greedy 反例挖掘与缩小

从已有实例中筛选标准 Greedy 的失败案例，再通过删除集合、元素和成员关系缩小案例。
入口使用实际集合重新计算 `G` 和穷举最优值 `O`，只将 `G < O` 判为反例。
用途是选例、解释和后续测试；经过筛选、缩小的案例不用于估计随机模型失效率。

## 运行

在仓库根目录使用 Python 3.11 或更高版本；不需要第三方运行依赖。
Windows 若 `python` 不在 PATH，可将命令中的 `python` 换成 `.\.venv\Scripts\python.exe`。

```console
python analysis/mine_counterexamples.py --input experiments/r1_prefix_exchange_v1/paths.jsonl --output results/counterexamples_r1 --top 5
python analysis/validate_counterexamples.py --input results/counterexamples_r1/counterexamples.json
python run_project.py replay --instance results/counterexamples_r1/counterexample_001.json --algorithm greedy
```

也可以输入 `experiments/r1c_confirmation_v1/paths.jsonl`，或项目标准的单实例 JSON
（包括含 `instance` 对象的导出文件）。JSONL 每个非空行是一条实例，至少包含
`universe_size`、`k`、`sets`；未指定编码时 `sets` 是元素编号数组的数组，从 0 编号。
集合顺序决定平局时的选择，必须保留。当前不直接读取只有统计值的 CSV，也不根据配置生成新样本。

R1 文件同时包含 pilot 实验样本和功能夹具（`population=fixture`）；两者都参与选例。
报告逐例标明来源，夹具也可能排在前列，不能把混合输入的计数当作 pilot 实验计数。

输出目录必须不存在，避免覆盖已有结果。非法实例或损坏 JSON 会拒绝整个输入。
历史轨迹中的得分、最优值和失败分类不会用于判定；本工具重新计算，不是历史结果校验器。
来源 `instance_id` 等字段仅保留为原始标签，不能据此声称核验过完整源实验身份。

## 选择和缩小规则

先评估所有输入，按原始 `(O-G)/O` 降序排序；同分时依次按集合数、全集大小、成员关系数、
输入顺序升序。保留原始记录，不去重；因此输入重复时也可能重复入选。
默认只缩小前 5 个，可用 `--top` 调整。`O=0` 时相对损失为空，实例不属于反例。

每轮按如下顺序检查所有单步候选，接受第一个仍满足 `G < O` 的删减后重新开始：

1. 按索引删除一个集合，集合数不能小于 `k`。
2. 按编号删除一个全集元素，并按原顺序压紧元素编号，全集至少保留一个元素。
3. 按集合索引、元素编号删除一个成员关系。

整个过程保持 `k` 和剩余集合的相对顺序。删减后的索引以当前实例为准。
只保持反例性质，不保持原来的损失大小、平局机制、等长条件、度序列或生成家族。
发生删减后使用 `custom` 家族，不附带原始生成器参数；原实例与来源另行保留。

- `deletion_minimal`：完整一轮没有任何单步删减可以保留反例。不是全局最小，
  也没有排除同时删多个对象后仍为反例的可能。
- `budget_exhausted`：候选评估次数达到上限，保存当前已认证的反例，缩小未完成。

默认每次精确评估最多枚举 200,000 个 `k` 元集合组合，可用 `--max-combinations` 调整。
超过上限的原始实例标为 `combination_limit`，不判为成功或失败；全部超限时仍正常输出状态。
每个入选反例默认最多评估 10,000 个删减候选，可用 `--max-evaluations` 调整；0 表示只选例不缩小。
上限是组合数和候选次数，不是墙钟时间。独立验证还需要额外计算。

## 输出与验证

- `README.md`：输入、精确评估、反例和入选数量；缩小前后尺寸与 `G/O`，以及停止状态。
- `counterexamples.json`：所有原始实例、来源行号、重新评估结果、入选实例、接受的删减操作
  及其候选评估序号。原始和最终结果均含实际 Greedy 选择顺序、每步边际收益与平局候选，
  以及穷举最优选择见证。
- `counterexample_001.json` 等：项目标准实例格式，可用现有 replay 命令独立重放。
  无反例时不生成这些单实例文件。

写出前自动调用独立验证器；验证器使用普通集合运算和完整组合枚举，
不调用生产算法或缩小器的关键计算函数。共享部分仅为项目实例格式解析。
验证器重算输入与输出的覆盖值、最优见证、选择轨迹、排名和数量，并逐步重放接受的删减，
对 `deletion_minimal` 另行检查所有单步邻居。它不校验外部源文件的完整性，
不重跑全部被拒绝的中间候选，也不验证未记录的历史得分。

有效输入、已知答案、损坏结果和预算未完成场景已登记为必需研究检查：

```console
python -m unittest discover -s tests -p test_counterexamples.py -v
python scripts/check.py
```
