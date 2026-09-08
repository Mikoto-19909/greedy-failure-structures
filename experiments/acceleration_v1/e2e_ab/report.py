"""Read back six complete runs and render the A/B acceptance report."""
from pathlib import Path
import csv
import json

HERE=Path(__file__).resolve().parent
def read(path):
    return json.loads(path.read_text(encoding='utf-8'))
plan=read(HERE/'plan.json')
summary=read(HERE/'summary.json')
environment=read(HERE/'environment.json')
assert summary['status']=='complete' and summary['runs']==6
rows=[]
for case in plan['cases']:
    r=read(HERE/'runs'/case['id']/'result.json')
    assert r['case']==case and r['status']=='passed'
    assert r['pipeline_wall_seconds']>=sum(s['wall_seconds'] for s in r['stages'].values())
    assert all(s['returncode']==0 for s in r['stages'].values())
    events=[json.loads(line) for line in (Path(r['output'])/'execution.jsonl').read_text().splitlines()]
    assert [e['operation'] for e in events]==['production','analysis','summary_verification']
    assert all(e['status']=='complete' for e in events)
    assert read(Path(r['output'])/'summary_verification.json')['status']=='passed'
    rows.append(r)
for backend,data in summary['modes'].items():
    chosen=[r for r in rows if r['case']['backend']==backend]
    for field,stats in data.items():
        values=sorted(r['pipeline_wall_seconds'] if field=='total' else r['stages'][field]['wall_seconds'] for r in chosen)
        assert (stats['min'],stats['median'],stats['max'])==tuple(values)
with (HERE/'timings.csv').open('w',encoding='utf-8',newline='') as handle:
    fields=['id','backend','repeat','position','production_seconds','analysis_seconds','summary_verification_seconds','total_seconds']
    writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
    for r in rows:
        writer.writerow({**r['case'],'production_seconds':r['stages']['production']['wall_seconds'],
            'analysis_seconds':r['stages']['analysis']['wall_seconds'],
            'summary_verification_seconds':r['stages']['summary_verification']['wall_seconds'],
            'total_seconds':r['pipeline_wall_seconds']})
with (HERE/'paired_comparison.csv').open('w',encoding='utf-8',newline='') as handle:
    writer=csv.DictWriter(handle,fieldnames=list(summary['pairs'][0]));writer.writeheader();writer.writerows(summary['pairs'])
a=summary['modes']['python']['total']['median']
b=summary['modes']['numba']['total']['median']
lines=['# 全量 R2 端到端 A/B 验收','',
    '日期：2026-09-08。两组各 3 次全新运行，全部通过图结果、CSV 和汇总校验。','',
    f'完整流程总耗时中位数：Python 验证组 **{a:.3f} s**，Numba 验证组 **{b:.3f} s**；按两组中位数计算为 **{a/b:.3f} 倍**，耗时减少 **{(1-b/a)*100:.2f}%**。','',
    '## 固定设计与计时','',
    '- 相同 1,800 张图、13,000 个预算结果、288 张诊断图。配置和种子沿用上一轮全量测试；每次生产均重新计算，未复用完成检查点。',
    '- 两组生产都使用原始 CPU 四进程；验证都使用四进程，唯一配置差别是 python 或 numba 验证后端。没有使用 CUDA 生产原型。',
    '- 顺序固定为 Python→Numba、Numba→Python、Python→Numba，每组 3 次，独立输出目录，不根据中间结果调参或选择样本。',
    '- 每次调用实际 CLI：run → analyze --no-plot（内含完整独立图/诊断验证）→ --summaries-only。没有重复执行独立图验证命令。',
    '- 主指标从首个生产阶段的启动序列开始，到汇总校验进程退出为止；包含三次进程启动、依赖导入、JIT 缓存载入、新工作进程池、实例生成、求解、诊断、验证、统计、CSV I/O 和阶段间少量调度开销。',
    '- 两组都不绘图。预先只编译一个已知答案的微型 Numba 例子；操作系统和 JIT 磁盘缓存可能已热，但每阶段都启动新解释器。额外的跨组/源数据比对在计时结束后执行。',
    '- 上限：2 小时总预算、每阶段 20 分钟、4 个工作进程、6 GiB 保守进程内存检查、2 GiB 本轮输出。失败时保留日志与检查点，不替换难图。','',
    '## 三次重复的中位数与范围','']
lines += ['各阶段分别取中位数，因此阶段中位数之和不一定等于全流程中位数。','']
for backend,label in [('python','Python 验证组'),('numba','Numba 验证组')]:
    lines += [f'### {label}','']
    for field,label2 in [('production','生产与诊断'),('analysis','独立图验证、统计分析与 CSV'),('summary_verification','汇总独立校验'),('total','全流程')]:
        v=summary['modes'][backend][field]
        lines.append(f"- {label2}：{v['median']:.3f} s，范围 {v['min']:.3f}–{v['max']:.3f} s。")
    lines.append('')
lines += ['各轮成对比较（按预定 repeat 对应，不按速度排序）：','']
for pair in summary['pairs']:
    lines.append(f"- 第 {pair['repeat']+1} 轮：Python {pair['python']:.3f} s，Numba {pair['numba']:.3f} s；节省 {pair['saved_seconds']:.3f} s，减少 {pair['reduction_percent']:.2f}%，加速比 {pair['speedup']:.3f}。")
lines += ['', '## 正确性与范围','',
    '- 六次运行均 computed=1800、reused=0；累计重新计算 10,800 张图次、78,000 条预算结果。它们是固定样本的重复执行，不是新增独立研究样本。',
    '- 每次生成的全部非 timing 图字段都与归档原始图记录一致；后续五次也与第一组基线一致，包括任务身份、种子、有序集合、最优解、结构和完整诊断。',
    '- 六次的 budget_results.csv、cell_summary.csv、mechanism_summary.csv 逐字节一致，每次预算表均为 13,000 行，独立汇总校验均 passed。',
    '- 回读各阶段退出码、execution.jsonl 的三个 complete 操作及原始时间，重新按排序中间值核算全部中位数和范围；未以旧 passed 状态跳过重算。',
    f"- 六次流水线总墙钟时间合计 {summary['total_pipeline_seconds']/60:.2f} 分钟；生产阶段保守进程内存估计的最大值为 {summary['max_production_conservative_memory_bytes']/1024**2:.1f} MiB。分析阶段另由现有 R2 资源检查约束；此数字不是整机 RAM 峰值。",
    '- 这是本机、固定数据、三次重复的工程验收，保留所有观测，不声称统计显著性或跨机器通用倍率。与前一轮独立验证命令的 1.94 倍不能直接互换；本报告覆盖的是所声明的无绘图完整流程。',
    f"- 代码固定为 {plan['code_commit']}。环境：Python {environment['python'].split()[0]}、Numba {environment['packages']['numba']}、NumPy {environment['packages']['numpy']}、SciPy {environment['packages']['scipy']}；{environment['logical_cpus']} 个逻辑 CPU，记录的电源方案：{environment['power_scheme']}。",'',
    '## 复现与文件','',
    '在工作树根目录使用 .venv/Scripts/python.exe 运行 benchmark.py prepare 固定计划，benchmark.py run 执行未完成案例，benchmark.py summarize 重新汇总；report.py 回读检查并生成此报告。以上脚本位于 results/e2e-ab-v1/。',
    '已成功案例会复用已保存的测量；失败案例重试时创建新的 attempt 目录并重新生产，不覆盖失败记录。要进行另一组独立测量，应另存当前整个试验目录并准备新计划。',
    'timings.csv 保存 6 条完整原始计时；paired_comparison.csv 保存 3 对比较；runs/<case>/attempt*/ 包含三个命令的日志、时间、退出码和完整 output/。plan.json、config.json 和 environment.json 保存预定条件。',
]
(HERE/'REPORT.zh-CN.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
(HERE/'readback_check.json').write_text(json.dumps({'passed':True,'runs':6,'stages':18,
    'all_medians_and_ranges_recomputed':True,'all_operations_complete':True},indent=2),encoding='utf-8')
print('Report, timing CSVs and readback check written')
