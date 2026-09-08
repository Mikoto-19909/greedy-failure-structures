"""Write the bounded independent-verifier optimization report from actual results."""
from pathlib import Path
import json
import pstats

HERE=Path(__file__).resolve().parent
OUT=HERE/'verification_v1'
summary=json.loads((OUT/'summary.json').read_text())
checks=json.loads((OUT/'checks.json').read_text())
rows=json.loads((OUT/'measurements.json').read_text())
assert summary['status']=='complete' and checks['passed'] and len(rows)==9
modes=summary['modes']
original=modes['original4']['total_seconds']['median']
fast=modes['compiled1']['total_seconds']['median']
stats=pstats.Stats(str(OUT/'verification.prof'))
completion=next(v for k,v in stats.stats.items() if k[2]=='best_completion')
lines=['# 独立验证热点优化试验','',
    '2026-09-08。本地适配器已完成实际运行；正式仓库算法、验证器和默认设置未修改。','',
    '## 结果','',
    f'固定 9 张 R2 图的端到端耗时中位数从 **{original:.3f} s** 降至 **{fast:.3f} s**，约 **{original/fast:.2f} 倍**，减少 **{(1-fast/original)*100:.2f}%**。生产端沿用上一轮混合 CPU/CUDA 后端；本轮只改变独立验证的补全枚举与验证进程数。','',
    '每种方式 3 次运行；以下单位为秒：','']
for key,label in [('original4','原验证器，四进程'),('compiled1','编译验证器，单进程'),('compiled4','编译验证器，四进程')]:
    v=modes[key]
    t=v['total_seconds']
    lines.append(f"- {label}：总耗时 {t['median']:.3f}（{t['min']:.3f}–{t['max']:.3f}）；生产中位数 {v['production_seconds']['median']:.3f}；验证与分析/CSV 中位数 {v['analysis_seconds']['median']:.3f}；汇总独立验证中位数 {v['summary_verification_seconds']['median']:.3f}。")
lines += ['',
    '本轮同进程数对比也支持枚举优化有效：编译验证器四进程快于原验证器四进程。单进程又进一步缩短了这批小任务的时间；这与新建进程、导入及编译缓存载入的固定开销相符，但本轮没有单独量化这些开销，不能推广为所有批量规模都应使用单进程。','',
    '## 热点与改动','',
    f'- 对未经修改的 9 张图验证做 cProfile：best_completion 调用 {completion[1]} 次，累计 {completion[3]:.3f} s，占分析器总运行时间约 {completion[3]/stats.total_tt*100:.1f}%。这是热点定位数据；分析器会改变运行时间，不能与无分析器计时直接比较。',
    '- 原验证器对每个前缀枚举可补全组合，反复创建、合并 Python 集合。新实现将输入集合转换成布尔关联矩阵，使用单独编写的 Numba CPU 循环按字典序枚举组合。',
    '- 原来的前缀合法性、枚举数量上限、最优覆盖量、字典序最小最优解、检查过的组合数、最优解总数全部保留；没有剪掉候选解或用近似值替代精确验证。',
    '- 原 validate_r2_budget_grid.reference 仍使用 Python sets/combinations 重算各预算的最优值；Greedy、交换路径、结构、种子、身份、类型敏感比较和汇总验证继续调用原代码。',
    '- 新计算模块 independent_completion.py 不导入生产端求解器或 CUDA 内核，不复用生产端的位掩码、原子最大值或最优值缓存。独立性针对数值计算实现；输入生成、对象身份和原有验证框架仍按项目既有设计共享。','',
    '## 检查结果','',
    f"- {checks['small_prefix_cases']} 个小规模前缀对照：穷尽 2 元素全集上的 3 集合族、全部预算、全部合法前缀，并检查正序/逆序前缀；返回的四个字段与原枚举完全一致。",
    '- 空集合族元素、全零覆盖、重复集合、多重最优解、超过 64 位位置的元素，以及全部 9 张实际图的完整预期路径均通过对照。',
    f"- {checks['invalid_inputs']} 类非法预算/前缀/枚举上限输入被拒绝；{len(checks['corruptions_rejected'])} 类记录篡改被拒绝："+'、'.join(checks['corruptions_rejected'])+'。',
    '- 9 次实际流程执行的非 timing 图字段全部等于上一轮原始验证通过的基线；三个 CSV 在每次运行中逐字节一致。',
    '- 新增 2 项行为测试通过：现有全部 R1 固定样例的完整路径对照、不同交换预算下的完整状态/计数对照。启用新补全枚举后，现有 8 项 R2 测试也全部通过，涵盖恢复、资源边界、输入篡改与汇总。日志见 behavior_tests.log。','',
    '## 计时范围与限制','',
    '- 沿用同一批固定任务、种子、预算和诊断成员；不增加样本、不改变研究停止条件。plan.json 在测量前固定，三种方式按轮次轮换顺序。',
    '- 计入实例生成、GPU/CPU 生产、诊断、检查点 I/O、独立图验证、分析、CSV 和汇总独立验证。每次调用实际 run、analyze(plot=False)、verify_summaries；未绘图。',
    f"- 父进程依赖导入与预热不计入正式计时。本次额外记录的后端/枚举预热为 {summary['warmup_seconds']:.3f} s；新建子进程及其缓存载入计入相应运行。",
    '- 本机负载会变化，原验证器第一次运行明显较慢；全部观测均保留，报告中位数和完整范围，不剔除该次。与上一轮的绝对耗时不直接拼接成累计加速倍数。',
    '- 九张图、三次重复用于工程试验，不足以确定普遍最优进程数或更大样本的收益。新模块目前依赖独立试验环境中的 NumPy/Numba，尚未实现正式可选依赖接口或生产默认切换。','',
    '## 复现','',
    '在仓库根目录运行：','',
    '```powershell',
    '& results/cuda_trial_v1/.venv/Scripts/python.exe results/cuda_trial_v1/verification_trial.py check',
    '& results/cuda_trial_v1/.venv/Scripts/python.exe results/cuda_trial_v1/test_independent_completion.py',
    '& results/cuda_trial_v1/.venv/Scripts/python.exe results/cuda_trial_v1/verification_report.py',
    '```','',
    '测量入口为 verification_trial.py run。它在 verification_v1/runs 已存在时拒绝覆盖；重跑前需归档该轮结果，再准备 plan。固定计划、每次原始计时、完整运行输出和 .prof 原始分析数据均在 verification_v1/ 中。依赖沿用 requirements-pipeline.txt。','',
    '建议下一阶段将这一独立 CPU 枚举整理为可选快速验证路径，保留原始 Python 验证器作为回退和抽查对照，并再评估更大批量的进程策略。本轮在热点定位、单项优化、兼容检查与固定端到端测量完成后停止。',
]
(OUT/'REPORT.zh-CN.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Wrote verification_v1/REPORT.zh-CN.md')
