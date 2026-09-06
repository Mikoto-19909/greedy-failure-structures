# 术语表（Glossary）

本表统一仓库中文文档（`*.zh-CN.md`）的译法。新增或修改中文文档时对照此表；
表中没有的术语先补充进表再使用。英文文档不受此表约束。

## 统一译法

| English | 中文 | 备注 |
| --- | --- | --- |
| Maximum Coverage | 最大覆盖 | 问题名 |
| optimality gap | 最优性差距 | 首次出现可括注英文 |
| determinism | 确定性 | |
| overlap | 重叠 | |
| instance | 实例 | |
| instance identity | 实例身份 | 不用 instance ID |
| seed | 种子 | 复合词一并译：coupling seed → 耦合种子 |
| wall-clock (limit) | 墙钟（限制） | |
| canonical ordering | 规范行排序 | canonical 一律译"规范" |
| canonical CSV | 规范 CSV | |
| tie / tie-breaking | 平局 / 平局裁决 | 不用"平局规则" |
| coverage | 覆盖量 | 比率语境可用"覆盖率" |
| configuration | 配置 | normalized configuration → 规范化配置 |
| legacy configuration | 旧版配置 | |
| generator | 生成器 | |
| (instance) family | 实例族 | |
| exhaustive reference | 穷举参考 | |
| evidence | 证据 | |
| reproduce / reproduction | 复现 | |
| resume | 恢复（运行） | |
| checkpoint | 检查点 | |
| validator | 验证器 | 动词"校验/验证"按语境，名词一律"验证器" |
| timeout | 超时 | |
| repetition | 重复 | 指实验重复单位 |
| marginal gain | 边际增益 | |
| selected set indices | 选中的集合索引 | |
| stressor | 压力因子 | 首次出现可括注英文 |
| failure mechanism | 失败机制 | |
| claim ledger | 结论台账 | 机制已于 PR #46 删除，仅历史语境出现 |

## 保留英文不译

| 术语 | 说明 |
| --- | --- |
| Greedy / Lazy Greedy / Brute Force | 算法名 |
| incumbent | 全文保留英文 |
| Dashboard | 指仓库的 Dash 应用 |
| benchmark | |
| schema | |
| Manifest | 指输出产物 `manifest.json` 时 |
| repetition unit 之外的配置族名、文件名、命令、路径、CSV 列名 | 如 `high_overlap`、`uniform`、`quick.json`、`raw_results.csv` |

## 使用规则

1. 中英文之间留一个空格（如"比较 Greedy 和穷举参考"）。
2. 代码、命令、文件路径、CSV 列名一律不译，保持等宽格式。
3. 同一术语在同一文档内译法必须一致；跨文档以本表为准。
4. 历史语境引用已删机制（结论台账、内容边界、许可证清单）时保留原译名并
   注明其已移除，不为已删机制发明新译法。
