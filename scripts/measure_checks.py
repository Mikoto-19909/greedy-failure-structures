"""Compare archived baseline unittest+mypy with current default checks, serially."""
from __future__ import annotations
import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pairs', type=int, default=3)
    args = parser.parse_args()
    if args.pairs < 1:
        parser.error('pairs must be positive')
    output = args.output.resolve()
    if output.exists():
        parser.error('use a new output directory; measurements are not overwritten')
    commit = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options', args.baseline+'^{commit}'], cwd=ROOT, text=True).strip()
    output.mkdir(parents=True)
    baseline = output / 'baseline'
    baseline.mkdir()
    archive = subprocess.check_output(['git', 'archive', commit], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(baseline, filter='data')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    rows = []
    for pair in range(args.pairs + 1):
        order = ('baseline', 'core') if pair % 2 == 0 else ('core', 'baseline')
        for label in order:
            cwd = baseline if label == 'baseline' else ROOT
            commands = ([['-m', 'unittest', 'discover', '-s', 'tests', '-v'], ['-m', 'mypy']]
                        if label == 'baseline' else [['scripts/check.py']])
            log = output / f'{pair}-{label}.log'
            started = time.perf_counter()
            with log.open('w', encoding='utf-8') as handle:
                for command in commands:
                    result = subprocess.run([sys.executable, '-B', *command], cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT)
                    if result.returncode:
                        raise RuntimeError(f'{label} failed with {result.returncode}; inspect {log}')
            seconds = time.perf_counter() - started
            text = log.read_text(encoding='utf-8')
            counts = re.findall(r'Ran (\d+) tests?', text)
            rows.append({'pair': pair, 'phase': 'warmup' if pair == 0 else 'measured', 'profile': label,
                         'seconds': seconds, 'tests': int(counts[-1]) if counts else None, 'log': log.name})
            with (output / 'times.csv').open('w', encoding='utf-8', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            print(f'{rows[-1]["phase"]} {pair} {label}: {seconds:.3f}s; {rows[-1]["tests"]} tests', flush=True)
    medians = {label: statistics.median(row['seconds'] for row in rows if row['pair'] and row['profile'] == label) for label in ('baseline', 'core')}
    reduction = 1 - medians['core'] / medians['baseline']
    summary = {'baseline_commit': commit, 'python': sys.version, 'pairs': args.pairs,
               'median_seconds': medians, 'reduction_fraction': reduction, 'target_met': reduction >= 0.4}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return 0 if summary['target_met'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
