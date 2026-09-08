"""Generate the first production backend acceptance report from saved runs."""
from pathlib import Path
import csv
import json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def read(p): return json.loads(p.read_text(encoding='utf-8'))
plan=read(HERE/'plan.json');summary=read(HERE/'acceptance_summary.json')
assert summary['status']=='complete'
rows=[read(HERE/'runs'/c['id']/'result.json') for c in plan['cases']]
assert len(rows)==12 and all(r['status']=='passed' for r in rows)
for backend,stats in summary['groups'].items():
    selected=[r for r in rows if r['case']['backend']==backend and r['case']['size']==1800]
    for stage,v in stats.items():
        values=sorted(r['total_seconds'] if stage=='total' else r['stages'][stage]['seconds'] for r in selected)
        assert (v['min'],v['median'],v['max'])==tuple(values)
for r in rows:
    assert r['total_seconds']>=sum(v['seconds'] for v in r['stages'].values())
    assert all(v['returncode']==0 for v in r['stages'].values())
with (HERE/'timings.csv').open('w',encoding='utf-8',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['id','size','repeat','backend','workers','production','analysis','summary','total'])
    writer.writeheader()
    for r in rows: writer.writerow({**r['case'],**{k:v['seconds'] for k,v in r['stages'].items()},'total':r['total_seconds']})
g=summary['groups'];winner=min(g,key=lambda k:g[k]['total']['median'])
lines=['# R2 首版可选生产后端验收','',
    '2026-09-08。逐图 Python/Numba/CUDA 生产已实现；跨图批处理与自动 GPU 调度不属于本版。','',
    f"正式源码固定为 `{plan['code_commit']}`。九图先导三组通过后，全量三种方式各执行三次新输出；全量总耗时中位数最小的是 `{winner}`。",'',
    '## 实测结果','',
    '全部方式使用同一 CUDA 依赖环境，验证后端统一 NumBa 四进程；Python/NumBa 生产四进程，CUDA 使用单一隔离拥有者并串行执行 CPU 诊断。各阶段分别取中位数，阶段中位数之和不一定等于总中位数。','']
for backend in ('python','numba','cuda'):
    x=g[backend]
    lines.append(f"- {backend}：生产 {x['production']['median']:.3f} s；验证与分析 {x['analysis']['median']:.3f} s；汇总校验 {x['summary']['median']:.3f} s；总中位数 **{x['total']['median']:.3f} s**（{x['total']['min']:.3f}–{x['total']['max']:.3f} s）。")
for backend in ('numba','cuda'):
    ratio=g['python']['total']['median']/g[backend]['total']['median']
    lines.append(f"- {backend} 相对本轮 Python 基线：{ratio:.3f} 倍，总耗时减少 {(1-1/ratio)*100:.2f}%。")
lines += ['',
    '九图先导是单次正确性/启动成本检查，不能作为重复性能统计：','']
for r in rows[:3]: lines.append(f"- {r['case']['backend']}：总 {r['total_seconds']:.3f} s，生产 {r['stages']['production']['seconds']:.3f} s。")
lines += ['', '## 修正与契约','',
    '- 真正的求解和阻塞回传位于枚举计时内；首次编译/初始化不再被缓存查表时间代替。CUDA 另用设备事件记录内核时间，仍以主机总墙钟验收。',
    '- cuda 严格执行；参数、非法地址及计算错误不会回退为 CPU 成功。auto 只做 CPU 依赖选择，求解错误仍失败。',
    '- CUDA 使用 spawn Process/Pipe 的单一拥有者，异常和预算退出显式终止、有界回收；原等待式关闭缺陷已被独立复现并修正。',
    '- 已完成恢复不初始化可选后端，部分恢复只求未完成图，可在固定配置下切换后端；已保存图不变。',
    '- 所有模式的数值/身份字段不变，执行信息在独立 sidecar；成功事件在检查点保存后写入。',
    '- GPU 内存池上限 64 MiB、额外空闲余量 128 MiB，CPU RSS 与显存分开。ASCII 编译路径局限于拥有者，含中文输出路径通过专门测试。','',
    '## 验收证据','',
    '- CPU 新增 6 项测试通过；完整检查 520 项通过，4 项为明确可选跳过（OR-Tools、Matplotlib、两项 GPU）。mypy 既有 38 个源码文件通过。',
    '- 显式 CUDA profile 两项真实硬件检查通过：独立 CPU 对照、M=20/空内容/64位高位/重复集合、实际线程计数、截断启动拒绝、严格 CUDA 错误、隔离 owner、恢复和 CSV 一致性。',
    '- 独立代理复核发现并确认修正预算停止问题；其最小真实 GPU、混合恢复和损坏输入拒绝复测通过。',
    '- 另在关闭 site-packages 的真实新进程中验证 auto 的 Python 回退，以及严格 numba/cuda 的失败；不是仅用 mock 模拟依赖缺失。',
    '- 三个先导和九个全量运行都新建输出、没有复用生产检查点；每个非计时图字段与原 R2 归档一致，同规模的三个 CSV 逐字节一致。实际 CUDA 完成事件和单一 owner PID 也已核对。',
    '- 固定全量为 1,800 张图、13,000 个预算结果、288 张诊断图。每种执行方式三次，轮换顺序，没有删除慢值或更换样本。',
    f"- 累计测量墙钟 {summary['total_seconds']/60:.2f} 分钟。边界是 run → analyze --no-plot → summaries-only，包含每阶段进程/依赖启动、JIT 缓存载入及文件 I/O；先导预热了磁盘缓存。跨运行额外比对不计入。",'',
    '## 限制与使用','',
    '- 这是本机固定负载的执行方式比较，CPU 四进程与 CUDA 单拥有者资源不同，不是纯硬件倍率；不能承诺 GPU 在完整流程里优于编译 CPU。',
    '- 不与先前不同时间、环境状态下的绝对耗时拼接计算累计倍数。这里的改进只相对本轮 Python 生产基线，所有方式均启用了相同的快速验证。',
    '- GPU 首版没有跨图批处理、CPU 诊断并行或自动 GPU 选择，不放宽 M<=20/64位掩码限制。预检/F2 使用原 Python 成本策略。',
    '- 生产与验证独立；加速验证并未复用生产器的计算结果。原配置、种子、旧测量和默认 Python 路径保留。',
    '- 命令及环境要求见 docs/r2_production_backends.zh-CN.md。CPU/CUDA 环境安装已实际测试；标准 CPU CI 不代表真实 GPU 检查。',
    '- plan.json、environment.json、timings.csv 和 runs/ 保留完整条件与原始命令日志。benchmark入口 acceptance.py，已成功案例不会覆盖；失败尝试保留。',
]
(HERE/'REPORT.zh-CN.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
(HERE/'readback.json').write_text(json.dumps({'passed':True,'runs':12,'full_runs':9,'all_medians_recomputed':True},indent=2),encoding='utf-8')
print('Report and raw timing CSV written')
