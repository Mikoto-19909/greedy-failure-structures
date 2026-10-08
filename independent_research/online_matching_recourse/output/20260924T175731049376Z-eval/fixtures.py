"""Freeze exactly 6 development and 24 evaluation arrival sequences."""
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parent
SEED = 20260925


def build():
    rng = random.Random(SEED)
    cases = []

    def add(case_id, split, family, servers, requests, order=None):
        order = list(range(6)) if order is None else order
        cases.append(dict(id=case_id, split=split, family=family,
                          servers=servers, requests=requests, order=order))

    add('dev_pair', 'dev', 'paired', [0, 10, 100, 110, 200, 210], [6, 9, 106, 109, 206, 209])
    add('dev_uniform', 'dev', 'uniform', [0, 10, 20, 30, 40, 50], [4, 14, 24, 34, 44, 1])
    add('dev_cluster', 'dev', 'clustered', [0, 2, 4, 40, 42, 44], [3, 1, 5, 43, 41, 39])
    add('dev_alternate', 'dev', 'near_far', [0, 10, 20, 30, 40, 50], [24, 49, 26, 1, 14, 36])
    add('dev_budget', 'dev', 'budget_lock', [0, 3, 5, 100, 110, 120], [2, 3, 0, 101, 111, 119])
    add('dev_nested', 'dev', 'nested', [0, 8, 16, 32, 64, 128], [63, 31, 15, 7, 3, 1])
    layouts = [
        ('uniform', [0, 10, 20, 30, 40, 50], [3, 13, 23, 33, 43, 47]),
        ('clustered', [0, 2, 4, 40, 42, 44], [1, 3, 5, 39, 41, 43]),
        ('near_far', [0, 10, 20, 30, 40, 50], [1, 9, 21, 29, 41, 49]),
        ('paired', [0, 10, 100, 110, 200, 210], [6, 9, 106, 109, 206, 209]),
    ]
    fixed = [list(range(6)), list(reversed(range(6))), [2, 3, 1, 4, 0, 5], [0, 5, 1, 4, 2, 3]]
    for family, servers, requests in layouts:
        orders = list(fixed)
        while len(orders) < 6:
            order = rng.sample(range(6), 6)
            if order not in orders:
                orders.append(order)
        for i, order in enumerate(orders):
            add(f'{family}_{i+1:02d}', 'eval', family, servers, requests, order)
    return dict(seed=SEED, cases=cases)


if __name__ == '__main__':
    target = ROOT / 'inputs.json'
    data = (json.dumps(build(), ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if target.exists():
        assert target.read_bytes() == data, 'Refuse to replace frozen inputs'
    else:
        target.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    manifest = ROOT / 'input_manifest.json'
    obj = dict(input_sha256=digest, seed=SEED, cases=30, development=6, evaluation=24)
    if manifest.exists():
        assert json.loads(manifest.read_text(encoding='utf-8')) == obj
    else:
        manifest.write_text(json.dumps(obj, indent=2) + '\n', encoding='utf-8')
    print(digest)
