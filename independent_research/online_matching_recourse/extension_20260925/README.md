# 六分支继续研究

先读[六分支研究结果](报告/六分支研究结果.md)。本目录对应“尝试完成1—6所有，论文也自行查找”的后续研究。原实验目录的固定输入和历史输出保持不变。

## 专题

- [链动作与自由首步](报告/链动作与自由首步.md)：连续三点决策及首步自由选择。
- [更多请求与策略拆分](报告/更多请求与策略拆分.md)：n−1次数界、四请求有限在线博弈、链长与价格。
- [随机化与原始成本](报告/随机化与原始成本.md)：两种对手、无收益定理、62到60的精确例子。
- [补充文献核查](报告/补充文献核查.md)：三篇新增正文及指定论文的全文缺口。

## 重跑

沿用已有Python环境。链/首步、压力例和四请求只需标准库。随机化需要SciPy，绘图需要Matplotlib和Microsoft YaHei字体。本机现有环境已满足，无须新增依赖。

在本目录分别运行：

```powershell
python -B chain_first.py
python -B random_raw.py
python -B ablation.py
python -B verify_ablation.py 'output\上一步打印的目录名'
python -B four_request_game.py
python -B verify_four_game.py 'output\上一步打印的目录名\summary.json'
python -B continuous_four_bounds.py
python -B verify_four_game.py 'output\上一步打印的目录名\summary.json' 300
```

`chain_first.py` 与 `random_raw.py` 自带独立枚举和证书检查。四请求与拆分的核验器不导入计算程序。每个计算入口都写入新的、被 Git 忽略的目录；`chain_first` 已保存的旧目录使用本地时间，其他主要输出使用UTC时间。所有结果中的时间字段表示相应进程CPU，不能当作全机CPU监测。

`plots.py` 从本轮已保存的拆分结果重画两张图，不计算新到达序列。旧30条输入从上一级读取并核对指纹，所以本目录应保留在原实验目录内。

核验源代码与报告是主要交付。`evidence/` 为本地第三方文献材料，不随版本提交。用户本人审阅状态以各阶段记录为准。

日常回归使用仓库的 `python scripts/check.py --profile research --tests-only`。
它检查各分支的小型已知答案、完整轨迹和损坏输入拒绝，不重跑上面的正式实验。
原一次性交付审计脚本已退役，旧交付记录继续作为历史材料保留。
