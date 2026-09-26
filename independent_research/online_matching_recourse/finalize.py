"""Render a result note and retain source snapshots after verification."""
import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    out = args.directory
    verification = json.loads((out / 'verification.json').read_text(encoding='utf-8'))
    summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
    assert verification['status'] == 'automatic_verification_passed_user_review_pending'
    shutil.copyfile(out / 'protocol.md', out / 'protocol_snapshot.md')
    for name in ['verify.py', 'test_matching.py', 'fixtures.py', 'analyze.py', 'finalize.py', 'run.ps1']:
        shutil.copyfile(ROOT / name, out / name)
    lines = ['# 本次固定比较结果', '', '已保存自动核验通过记录；用户本人审阅尚未完成。此步骤仅整理报告，不重新核验文件。', '',
             '阶段成本和是六个到达阶段的距离总和。时长为所有序列的策略墙钟时间之和。', '',
             '|策略|每请求预算|阶段成本和|最终成本合计|降幅|总改派|单请求最大|墙钟毫秒|',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    names = dict(nearest='最近空位', single='单次腾位', priced_chain='预算定价链', prefix_optimum='前缀精确参照')
    for row in summary['aggregates']:
        if row['family'] != 'all':
            continue
        display = lambda x: '不适用' if x is None else str(x)
        lines.append(f"|{names[row['policy']]}|{display(row['budget'])}|{row['prefix_sum']}|{row['final_cost']}|{row['reduction_pct']:.2f}%|{display(row['total_recourse'])}|{display(row['max_request_recourse'])}|{1000*row['wall_seconds']:.3f}|")
    lines.extend(['', '所有数字对应 [summary.json](summary.json) 的 family=all；逐序列值见 [metrics.csv](metrics.csv)。',
                  '每步分配和改派记录见 [traces.json](traces.json)。',
                  '精确参照的改派计数不适用，因为只计算当前最优成本，不执行该匹配。',
                  '预算 1/2/4 只在本组实例持平，不证明一般输入只需一次改派。',
                  'CPU 时间为零的短调用低于 Windows 计时粒度，不表示没有计算。',
                  '输入复用、数学说明、文献缺口和解释详见 [研究报告](../../报告/研究报告.md)。'])
    (out / '结果说明.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('Final result package:', out)


if __name__ == '__main__':
    main()
