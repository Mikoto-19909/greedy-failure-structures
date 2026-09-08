"""Render fixed-plan command timings after every required case has passed."""
from pathlib import Path
import csv
import json

HERE=Path(__file__).resolve().parent
plan=json.loads((HERE/'plan.json').read_text())
summary=json.loads((HERE/'summary.json').read_text())
environment=json.loads((HERE/'environment.json').read_text())
assert summary['status']=='complete' and summary['cases']==36
raw=[json.loads((HERE/'runs'/c['id']/'result.json').read_text()) for c in plan['cases']]
assert len(raw)==36 and all(r['status']=='passed' for r in raw)
with (HERE/'timings.csv').open('w',encoding='utf-8',newline='') as handle:
    writer=csv.DictWriter(handle,fieldnames=['size','backend','workers','repeat','position','process_wall_seconds',
        'validation_wall_seconds','verified_graphs','sum_base_seconds','sum_diagnostic_seconds',
        'peak_process_bytes','conservative_process_memory_bytes'])
    writer.writeheader()
    for r in raw:
        writer.writerow({key:r['case'][key] if key in r['case'] else r[key] for key in writer.fieldnames})
flat=[]
for group in summary['summaries']:
    for mode,t in group['modes'].items():
        backend,workers=mode.split('-')
        flat.append({'graphs':group['size'],'diagnostic_graphs':group['diagnostic_graphs'],
            'budget_rows':group['budget_rows'],'backend':backend,'workers':int(workers),
            'median_seconds':t['median'],'min_seconds':t['min'],'max_seconds':t['max'],
            'graphs_per_second':group['size']/t['median'],'peak_process_bytes':t['peak_process_bytes']})
with (HERE/'summary.csv').open('w',encoding='utf-8',newline='') as handle:
    writer=csv.DictWriter(handle,fieldnames=list(flat[0]))
    writer.writeheader();writer.writerows(flat)
largest=summary['summaries'][-1]
best=min((m for m in largest['modes'] if m.startswith('numba-')),key=lambda m:largest['modes'][m]['median'])
best_workers=best.split('-')[1]
best_time=largest['modes'][best]['median']
one_time=largest['modes']['numba-1']['median']
python_time=largest['modes']['python-4']['median']
lines=['# 大批量 R2 独立验证进程数试验','',
    '日期：2026-09-08。状态：36 次预定测量全部完成，结论仅针对独立验证命令。','',
    f"在完整 1,800 张原图上，三个快速后端选项中实测中位数最小的是 **{best_workers} 个进程**：{best_time:.3f} 秒。快速后端单进程为 {one_time:.3f} 秒，原始 Python 四进程为 {python_time:.3f} 秒。",'',
    f"所选快速后端相对快速单进程为 {one_time/best_time:.3f} 倍，相对原始 Python 四进程为 {python_time/best_time:.3f} 倍。这里没有测量超过 4 个进程，也没有声称该选择适用于其他机器或任务分布。",'',
    '## 固定样本与测量规则','',
    '- 复用本地 R2 证据归档的原图；来源记录指向提交 4a419f338d70068fa988fa97027734cdcda0a036。本轮未重新生成图或替换困难样本。',
    '- 在九个 n,d 单元内分别取原始 repetition=0..9、0..39、0..199，形成 90、360、1,800 张图。任务标识、种子、预算、诊断成员及原图内容与归档一致。',
    '- 三个批量的诊断图比例为 100%、80%、16%。较小批量不是完整批次的随机缩样；这是不同实际工作量的执行比较，不能把跨批量差异单独归因于图数。',
    '- 每个批量固定比较 Numba 1/2/4 进程及 Python 4 进程，各重复 3 次，按预定轮换顺序执行。样本、方法、重复次数及停止规则在结果产生前写入 plan.json。',
    '- 每次实际执行 validate_r2_budget_grid.py。主指标从创建子进程计时到成功退出，包含解释器及依赖导入、JIT 磁盘缓存载入、全新工作进程池、读取检查点、全部独立图/诊断验证和报告写入。',
    '- 正式计时前只预编译一个已知答案的小例子。操作系统文件缓存和 JIT 磁盘缓存可能已热；进程每次新建。本结果不是首次安装/首次编译的冷启动测量。',
    '- 输入副本准备不计入命令时间；未执行生产、bootstrap、图表或整个 R2 流水线，因此以下倍率不能写为项目端到端加速倍率。',
    '- 预设上限：总计 2 小时、单命令 20 分钟、最多 4 个工作进程、6 GiB 保守进程内存估计和 2 GiB 输出。失败/超时保留日志，不替换样本。','',
    '## 三次重复的中位数与范围','']
for group in summary['summaries']:
    lines += [f"### {group['size']} 张图：{group['budget_rows']} 个预算结果，{group['diagnostic_graphs']} 张含诊断",'']
    for mode in ('numba-1','numba-2','numba-4','python-4'):
        t=group['modes'][mode]
        label=mode.replace('numba-','快速后端，').replace('python-','原始 Python，')+' 进程'
        lines.append(f"- {label}：**{t['median']:.3f} s**，范围 {t['min']:.3f}–{t['max']:.3f} s；吞吐 {group['size']/t['median']:.3f} 图/s。")
    lines.append('')
lines += ['## 完成情况与解释边界','',
    f"- 36 次命令均退出成功，每次 verification.json 的 passed 状态和全部预期图 ID 都得到核对；总共执行 {sum(r['verified_graphs'] for r in raw):,} 次独立图验证。",
    f"- 结束时重新核对三份本地子集配置与固定方案一致；{summary['copied_graph_files_unchanged']:,} 个复制图文件均与归档源文件逐字节一致。代码固定为 {summary['code_commit']}，前后确认无源码差异。",
    f"- 36 次命令总墙钟时间为 {summary['total_command_seconds']/60:.2f} 分钟。最大单进程峰值 {max(r['peak_process_bytes'] for r in raw)/1024**2:.1f} MiB；最大保守进程内存估计 {max(r['conservative_process_memory_bytes'] for r in raw)/1024**2:.1f} MiB。它不是操作系统整体峰值测量。",
    '- 三次重复保留全部观测，不剔除慢值。机器共享负载、调度与热状态可能变化；报告范围与中位数，不声称进行了统计显著性验证。',
    '- 此前 9 张图试验测量的是预热父进程中的生产加分析流程；本轮测量的是新进程启动的独立验证命令。计时边界不同，不将两轮绝对时间相除，也不把跨轮差异全部归因于批量。',
    '- 此前 9 张图试验中的单进程优势不能直接用于大批任务。具体进程数应结合本轮同一批量的三个快速后端结果，而非仅参考 CPU 核心数。',
    f"- 环境：Python {environment['python'].split()[0]}，Numba {environment['packages']['numba']}，NumPy {environment['packages']['numpy']}，{environment['logical_cpus']} 个逻辑 CPU；记录的电源方案为 {environment['power_scheme']}。测试没有修改线程数或电源设置。",'',
    '## 复现与原始证据','',
    'benchmark.py prepare 固定本地输入副本与计划；benchmark.py run 执行或继续未完成的预定命令；benchmark.py summarize 重核输入并汇总；report.py 生成本报告与 CSV。所有命令从工作树根目录使用 .venv/Scripts/python.exe 运行。','',
    '已完成的 run 会复用成功测量，不会自动覆盖。每个命令的实际日志、退出码、时间和完整 verification.json 保存在 runs/<case>/attempt*/；失败尝试也保留。',
    'timings.csv 保存 36 条原始命令测量；summary.csv 保存 12 个配置的中位数、范围、吞吐和峰值；environment.json 与 plan.json 保存环境及预定规则。',
    'per-graph base/diagnostic 时间在多个工作进程中可能重叠；它们的和仅作工作量构成参考，不能与并行总墙钟时间直接相加。',
]
(HERE/'REPORT.zh-CN.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Report and CSVs written')
