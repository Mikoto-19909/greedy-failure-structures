"""Plot saved ablation data only; never run another arrival sequence."""
import json
from pathlib import Path
import time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
RUN = ROOT/'output/ablation_20260925T052608642708Z'


def main():
    started = time.process_time()
    traces = json.loads((RUN/'traces.json').read_text())
    groups = json.loads((RUN/'summary.json').read_text())['groups']
    plt.rcParams.update({'font.sans-serif': ['Microsoft YaHei'], 'axes.unicode_minus': False,
                         'svg.fonttype': 'path', 'font.size': 11})
    out = ROOT/'报告/图'
    out.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.4))
    for ax, n in zip(axes, (4, 6)):
        rows = sorted((t for t in traces if t['case_id']==f'alternating_radius_n{n}'
                       and t['chain_limit']==5 and t['weight']=='0'), key=lambda r:r['budget'])
        budgets, values = [r['budget'] for r in rows], [r['prefix_sum'] for r in rows]
        ax.plot(budgets, values, 'o-', color='#25669a', label='当前降本完整链')
        ax.axhline(2**n-1, linestyle='--', color='#666666', label='各前缀精确最优之和')
        for b, v in zip(budgets, values):
            ax.annotate(str(v), (b, v), xytext=(0, 8), textcoords='offset points', ha='center')
        ax.set(xlabel='每个请求的累计改派上限（次）', ylabel='阶段成本和（坐标距离单位）',
               title=f'{n}请求的左右交替压力例', xticks=budgets, ylim=(0, max(values)*1.2))
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y', alpha=.2)
        ax.legend(fontsize=9)
    fig.suptitle('更多预算不保证这条贪心轨迹更省', fontsize=16)
    fig.text(.5,.01,'来源：4条解析压力输入中的两例；每个阶段等权，未混入原24条固定比较。',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,.94))
    for ext in ('png','svg'):
        fig.savefig(out/f'01_budget_counterexample.{ext}', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11.6,4.6))
    configurations = [(1,'0'),(1,'1/2'),(5,'0'),(5,'1/2')]
    labels = ['单次','单次＋价格','完整链','完整链＋价格']
    rows = [next(g for g in groups if (g['split'],g['chain_limit'],g['weight'],g['budget'])==('eval',l,w,1)) for l,w in configurations]
    values = [100*(1221-r['prefix_sum'])/1221 for r in rows]
    axes[0].bar(range(4), values, color=['#71808e','#71808e','#25669a','#25669a'])
    for i,v in enumerate(values):
        axes[0].text(i,v+.4,f'{v:.2f}%',ha='center')
    axes[0].set(xticks=range(4),xticklabels=labels,ylim=(0,20),ylabel='相对不改派的成本降幅（%）',
                xlabel='每阶段动作与价格组合',title='原24条固定比较：价格无额外收益')
    axes[0].tick_params(axis='x', labelrotation=12)
    for (limit,weight),label,marker in zip(configurations,labels,['o','s','^','D']):
        rr = [next(g for g in groups if (g['split'],g['chain_limit'],g['weight'],g['budget'])==('dev',limit,weight,b)) for b in (1,2,4)]
        axes[1].plot([1,2,4],[r['prefix_sum'] for r in rr],marker=marker,label=label)
    axes[1].set(xlabel='每请求累计改派上限（次）',ylabel='阶段成本和（坐标距离单位）',
                title='开发6条：价格可降本，也可增本',xticks=[1,2,4])
    axes[1].legend(fontsize=9)
    for ax in axes:
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y',alpha=.2)
    fig.text(.5,.01,'价格系数固定为1/2；左图预算1、2、4数值相同。来源：拆分实验summary.json。',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.06,1,1))
    for ext in ('png','svg'):
        fig.savefig(out/f'02_ablation.{ext}',dpi=160)
    plt.close(fig)
    (ROOT/'output/plot_runtime.json').write_text(json.dumps({'cpu_seconds':time.process_time()-started,'new_sequences':0,'figures':2})+'\n')
    print(out)


if __name__=='__main__':
    main()
