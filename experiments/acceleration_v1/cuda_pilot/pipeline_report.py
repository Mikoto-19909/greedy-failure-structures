"""Render recorded R2 pipeline results, with no manually transcribed numbers."""
from pathlib import Path
import json
import statistics

HERE = Path(__file__).resolve().parent
OUT = HERE / 'pipeline_v1'
summary = json.loads((OUT/'summary.json').read_text())
measurements = json.loads((OUT/'measurements.json').read_text())
checks = json.loads((OUT/'checks.json').read_text())
plan = json.loads((OUT/'plan.json').read_text())
assert summary['status'] == 'complete' and checks['passed'] and len(measurements) == 12
names = {'python1':'原始 Python 单进程', 'python4':'原始 Python 四进程',
         'compiled':'编译 CPU 单进程', 'hybrid':'混合 CPU/CUDA（m=20 使用 GPU）'}
modes = summary['modes']
hybrid = modes['hybrid']['total_seconds']['median']
lines = ['# R2 CPU/CUDA 端到端试验', '',
    '2026-09-08。本地试验适配器完成；未修改或发布正式生产执行器。', '',
    '## 结果', '',
    'CUDA 已成功接入实际 R2 生产、诊断与产物流程，所有完整结果通过原有独立验证器。与单独穷举函数相比，端到端收益明显受剩余诊断和独立验证工作限制。', '',
    '以下单位为秒，每种方式为 3 次固定工作量运行的中位数与最小/最大值：', '']
for name in plan['modes']:
    item = modes[name]
    total = item['total_seconds']
    lines.append(f"- {names[name]}：总耗时 **{total['median']:.3f} s**（{total['min']:.3f}–{total['max']:.3f}）；生产 {item['production_seconds']['median']:.3f} s；独立图验证与分析/CSV {item['analysis_seconds']['median']:.3f} s；汇总独立验证 {item['summary_verification_seconds']['median']:.3f} s。")
lines += ['', '混合方案的端到端比较：', '']
for name in ('python1','python4','compiled'):
    baseline = modes[name]['total_seconds']['median']
    lines.append(f"- 相对{names[name]}：{baseline/hybrid:.3f} 倍，按总耗时中位数计算减少 {(1-hybrid/baseline)*100:.2f}%。负数表示混合方式更慢。")
detail = [r['detail']['backend_seconds'] for r in measurements if r['mode']=='hybrid']
lines += ['', f"混合方案 9 张图的预计算穷举后端总耗时中位数为 {statistics.median(detail)*1000:.3f} ms；这是生产阶段内部的小部分，不能当作完整流程耗时。", '',
    '## 固定范围与计时边界', '',
    '- 复用上一轮同样的 9 张图：n=m 为 12、16、20；d 为 2、3、4；repetition=0，种子、预算和诊断成员完全一致。局部配置通过现有 make_design/validate_design 生成，仅将本地样本范围设为每个单元 1 张图。原始大样本配置没有修改。',
    '- 保留全部 9 张图原有的 Greedy、结构指标、前缀/交换诊断。样本用于性能和兼容性检查，不用于新统计推断。',
    '- 每次真正调用 r2_budget_grid.run，然后 analyze(plot=False)，最后调用 verify_summaries。analyze 内部对全部图执行独立 verify_graph，包含精确最优值、平局解、结构和诊断重算；三个 CSV 全部写出并独立核对。',
    '- 计时从生产调用前到汇总独立验证完成，包含生成实例、分批准备、CPU/GPU 计算、GPU 传输和同步、检查点写入、子进程创建/回收、诊断、独立验证、统计汇总与 CSV I/O。',
    '- 父进程依赖导入与 JIT/CUDA 预热单独进行，不计入上述总耗时。独立分析验证对四种方式均使用新建的四进程池；原始四进程生产也每次重建进程池。',
    '- 无绘图，没有额外重复调用 validate_batch，因为 analyze 已经重新验证所有图。它代表所声明的 R2 命令组合，不能替代用户可能采用的其他工作流。',
    '- 为避免全局生产接口变更，本地适配器只在单个测量进程的 production 调用期间替换 R2 的任务分发与穷举函数引用，离开调用立即恢复。它先按尺寸批量预计算，再调用原有 evaluate_task 完成其余计算；额外的一次实例生成成本也包含在计时中。',
    '- 图记录里的 enumeration_seconds 在适配器运行时只计查表时间。真实批量准备和后端耗时位于 pipeline_timing.json 的 detail；报告仅使用外层计时作加速判断，不能把查表时间解释为穷举成本。',
    '- 三次重复按固定规则轮换方式顺序，不针对结果调参。样本少、共享笔记本的负载变化与亚秒差异，均限制了对小幅差距的解释；没有做显著性结论。', '',
    '## 正确性、恢复和回退', '',
    '- 12 次完整执行中的非 timing 图字段全部相等，包括 seeds、instance_id、覆盖量、完整最优索引元组、subset_count、结构和全部诊断。cell_summary.csv、budget_results.csv、mechanism_summary.csv 在全部执行中逐字节相等。',
]
lines += ['- ' + x for x in checks['checks']]
for name, label in [('existing_r2_tests.log', '现有 R2 行为测试'), ('backend_error_tests.log', '后端故障路径测试')]:
    log = OUT / name
    if log.exists():
        text = log.read_text(encoding='utf-8-sig')
        count = next((line.strip() for line in text.splitlines() if line.startswith('Ran ')), '')
        if count and '\nOK' in text:
            lines.append(f'- {label}通过：{count}；日志 {name}。')
lines += ['',
    'CUDA 回退仅处理缺少依赖、操作系统/驱动/编译/显存等可用性错误。非法输入先拒绝，普通计算错误继续抛出；没有把任意失败都伪装成正常回退。超出 64 位的合法掩码使用原始 Python 任意精度实现。', '',
    '## 复现和文件', '',
    '精确依赖版本保存在 requirements-pipeline.txt。在仓库根目录：', '',
    '```powershell',
    '& results/cuda_trial_v1/.venv/Scripts/python.exe -u results/cuda_trial_v1/pipeline_trial.py run',
    '& results/cuda_trial_v1/.venv/Scripts/python.exe results/cuda_trial_v1/pipeline_report.py',
    '```', '',
    '为保留本次测量，run 在 runs/ 已存在时会拒绝覆盖。重复测量需要把 pipeline_v1/ 归档到另一个本地目录，再运行 prepare 和 run；prepare 也拒绝覆盖已有 plan.json。', '',
    'pipeline_trial.py 是流程适配器；pipeline_backends.py 复用 trial.py 的 CUDA 内核和原始 CPU 动态规划实现。pipeline_v1/ 下保存固定 plan.json、measurements.json、summary.json、checks.json、12 份完整运行输出以及恢复/回退检查输出。', '',
    '当前证据支持保留可选后端供批量穷举使用，但不足以支持将 CUDA 设为本项目默认。若继续优化完整流程，应先针对占时最多的诊断与独立验证做单独分析，并保持验证实现的独立性。本轮在约定的接入、计时、兼容性与回退检查完成后停止。',
]
(OUT/'REPORT.zh-CN.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
print('Wrote pipeline_v1/REPORT.zh-CN.md')
