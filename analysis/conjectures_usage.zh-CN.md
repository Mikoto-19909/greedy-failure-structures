# 猜想反驳器

日常实验先看 [实验操作指南](../docs/counterexample_experiments.zh-CN.md)。
统一入口支持参数化生成设计、仅覆盖本次比例/预算、自动创建结果目录，
以及核验后查看实例和轨迹；下面保留底层命令与格式定义。

给定明确的结构前提与 Greedy 覆盖值要求，在指定有限实例域中寻找违反要求的实例。
第一版使用确定性枚举，支持等长集合、不重复集合、元素最大覆盖频数与覆盖比例阈值。
不解析任意自然语言或执行用户表达式；先将猜想写成下面的 JSON 设计。

## 跑通一个例子

示例猜想：“集合等长且互不重复时，Greedy 总能达到最优。”
这里只搜索全集大小 4、集合数 3、每个集合大小 2、预算 `k=2` 的有限域。
这个域中的一个反例就足以反驳上述普遍命题；没有找到则不能推广到其他域。

在工作树根目录运行（Python 3.11+，无第三方运行依赖）：

```console
python analysis/refute_conjecture.py --design designs/conjecture_equal_size.json --output results/conjecture_equal_size
python analysis/validate_conjecture.py --input results/conjecture_equal_size/search.json
python run_project.py replay --instance results/conjecture_equal_size/counterexample.json --algorithm greedy
python run_project.py replay --instance results/conjecture_equal_size/counterexample.json --algorithm brute_force
```

Windows 若当前工作树没有虚拟环境，可以将 `python` 换成已有解释器的完整路径。
本项目当前环境可在 PowerShell 用 `& '..\..\.venv\Scripts\python.exe'` 替换它，
命令从 `.worktrees/counterexample-miner` 运行；仅复用解释器，输入和输出仍在当前工作树。
输出目录必须不存在；失败的输入验证不会创建结果目录。

示例按第 3 个候选停止，得到：

```text
S0 = {0,1}, S1 = {0,2}, S2 = {1,3}, k = 2
Greedy: S0 + S1，覆盖 3
最优解: S1 + S2，覆盖 4
```

三个集合均为 2 个元素且互不相同。首轮平局按最小索引选择 `S0`，从而得到反例。
这反驳的是包含该平局规则的标准 Greedy 最优性猜想，不说明所有平局路径都失败。

## 设计文件

```json
{
  "schema_version": 1,
  "name": "equal_size_greedy_optimal",
  "domain": {
    "universe_size": 4,
    "set_count": 3,
    "k": 2,
    "set_size": 2,
    "unique_sets": true,
    "max_frequency": null
  },
  "claim": {"min_ratio": [1, 1]},
  "search": {"max_instances": 10000, "max_combinations": 200000}
}
```

- `universe_size`：固定全集大小，第一版支持 1–12；元素编号为 `0..n-1`，允许未被覆盖元素。
- `set_count`：固定集合数，支持 1–16；`k` 必须在 1 到集合数之间。
- `set_size`：所有集合都恰好有这么多元素；省略或 `null` 表示大小不限。
  允许大小 0，即空集合。
- `unique_sets`：是否禁止重复集合，默认 `false`；禁止重复不代表忽略集合索引顺序。
- `max_frequency`：每个元素最多属于多少个集合；省略或 `null` 表示不限，0 表示元素不能出现。
  设为 1 可以限定集合两两不相交。
- `min_ratio: [p,q]`：要求 `G*q >= O*p`，其中 `0 <= p <= q`、`q > 0`，必须为整数。
  `[1,1]` 表示要求最优；`[4,5]` 表示至少达到最优覆盖的 80%。等于阈值不算反例。
  使用整数交叉相乘判定，避免浮点边界；`O=0` 时要求也成立，不计算 `G/O`。
- `max_instances`：最多检查多少个候选，默认 10,000；0 表示不访问候选。
- `max_combinations`：每个候选允许枚举的 `k` 元集合组合数，默认 200,000。
  若 `C(set_count,k)` 超过限制，在搜索前拒绝设计，不把不完整参考当作最优。

所有前提同时成立才对结论作判定。未知字段、类型错误和非法范围会被拒绝。
当前只支持上述条件；例如“每个元素恰好出现两次”不能用最大频数 2 代替。

## 枚举范围和停止状态

候选集合以整数位掩码升序排列，再按字典序枚举长度为 `set_count` 的有序列表。
允许重复时枚举笛卡尔积；禁止重复时枚举不放回的有序排列，保留所有集合索引排列。
不做同构去重，不随机采样，因此没有随机种子。

设满足集合大小要求的单集合数量为 `q`，候选空间为 `q^m`（允许重复）或
`q!/(q-m)!`（不重复且 `m<=q`）；不重复且 `m>q` 时为空域。
元素频数是后续过滤条件，所以 `candidate_space` 包含可能被频数条件拒绝的候选。
`max_instances` 计数发生在频数过滤之前，避免大量拒绝造成预算外循环。

- `counterexample_found`：发现第一个满足全部前提且违反结论的实例，立即停止。
- `domain_exhausted`：全部候选均检查完，指定有限域内没有反例。不表示一般猜想成立。
  若 `eligible=0`，明确报告没有满足前提的实例，不能作为经验支持。
- `budget_exhausted`：预算用完且候选域尚未穷尽，没有找到反例也不能确认该有限域。

候选数恰好等于预算且全部检查完时归为 `domain_exhausted`；
在预算最后一个候选找到反例时仍为 `counterexample_found`。
上限限制候选数和精确枚举组合数，不是墙钟时间。搜索空间随尺寸迅速增长；
先运行小域，查看状态和计数，再调整设计。独立验证需要再次计算已搜索前缀。

## 输出和核验

`README.md` 解释前提、结论、状态、计数及见证；`search.json` 保存规范化设计、
候选计数、停止状态以及反例的实际集合、Greedy 轨迹、精确最优值和见证。
找到反例时额外写出标准实例格式的 `counterexample.json`，否则不生成该文件。

写出前自动调用独立验证器。验证器从元素组合生成集合，以普通集合运算重新枚举
整个已搜索前缀，核对结构过滤、首个反例、计数、停止状态、覆盖值与最优见证。
它共享 `conjecture_spec.py` 的格式解析，并复用已有独立集合验证器的计算，
不调用 `refute_conjecture.py` 的枚举或判定函数，也不调用生产 Greedy/穷举实现。
验证的是给定设计与实际实例，不证明自然语言猜想已被正确翻译，也不核验外部实验。

此入口不自动缩小反例。普通反例缩小器只保持 `k` 和 `G<O`，可能破坏等长等前提，
或跨越本次固定的全集/集合数范围；其输出不能未经重新核对就用作当前猜想的反例。

有效设计、已知反例、空域、预算边界与损坏输出拒绝已纳入必需研究检查：

```console
python -m unittest discover -s tests -p test_conjectures.py -v
python scripts/check.py
```
