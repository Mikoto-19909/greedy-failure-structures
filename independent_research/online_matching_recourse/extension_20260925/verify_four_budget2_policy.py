"""Independent permutation checks for the explicit four-request policy."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction as Q
import gzip
from itertools import permutations, product
import json
from pathlib import Path
import time


def require(condition, message='verification check failed'):
    """Keep scientific checks active under -O and PYTHONOPTIMIZE."""
    if not condition:
        raise AssertionError(message)

SERVERS = (-4, -1, 2, 8)
ALPHABET = ('-4', '-5/2', '-1', '1/2', '2', '5', '6', '7', '8')
BOUNDARY_CASES = (
    ('501/100', '251/50', '-4', '8'), ('5', '501/100', '-4', '8'),
    ('501/100', '501/100', '8', '-4'), ('501/100', '5', '-4', '8'),
    ('499/100', '5', '-4', '8'), ('-251/100', '-4', '2', '8'),
    ('-249/100', '-4', '2', '8'), ('51/100', '-1', '2', '-4'),
)


def verify(data):
    require(data['servers'] == list(SERVERS) and data['budget'] == 2)
    require(data['horizon'] == 4 and data['model'] == 'atomic')
    require(data['first_step'] == 'nearest_ties_left')
    requests = tuple(map(Q, data['requests']))
    require(len(requests) == len(data['trace']) == 4, 'incomplete trajectory')
    require(all(-4 <= r <= 8 for r in requests))
    first = min(range(4), key=lambda s: (abs(requests[0] - SERVERS[s]), s))
    anchored = requests[0] > 5 and requests[1] > requests[0]
    previous, counts = (), []
    cumulative = Q(0)
    for t, row in enumerate(data['trace'], 1):
        current = tuple(row['assignment'])
        require(row['arrival'] == t and len(current) == len(set(current)) == t)
        require(all(type(s) is int and 0 <= s < 4 for s in current))
        candidates = [(sum((abs(r - SERVERS[s]) for r, s in zip(requests[:t], p)), Q()), p)
                      for p in permutations(range(4), t)]
        optimum = min(c for c, _ in candidates)
        value = sum((abs(r - SERVERS[s]) for r, s in zip(requests, current)), Q())
        if t == 1:
            require(current == (first,) and row['action'] == 'nearest')
        elif t == 2:
            if anchored:
                require(current == (2, 3) and row['action'] == 'anchor_first_at_2')
            else:
                nearest = min((s for s in range(4) if s != first),
                              key=lambda s: (abs(requests[1] - SERVERS[s]), s))
                require(current == (first, nearest) and row['action'] == 'preserve_first')
        else:
            require(value == optimum, 'late stage is not globally optimal')
            eligible = [(c, p) for c, p in candidates if not anchored or p[0] == 2]
            active = list(range(1 if anchored else 0, t))
            active.sort(key=lambda i: (requests[i], i))
            ordered = [(c, p) for c, p in eligible
                       if all(p[active[i]] < p[active[i + 1]] for i in range(len(active) - 1))]
            require((value, current) == min(ordered), 'wrong deterministic tie rule')
            require(row['action'] == ('anchored_optimum' if anchored else 'prefix_optimum'))
        require(type(row['anchored']) is bool and row['anchored'] == (anchored and t >= 2))
        if anchored and t >= 2:
            require(current[0] == 2 and value == optimum)
        changed = [i for i, (old, new) in enumerate(zip(previous, current)) if old != new]
        counts = [used + (i in changed) for i, used in enumerate(counts)] + [0]
        require(row['changed'] == changed and row['counts'] == counts and max(counts) <= 2)
        excess = value - optimum
        cumulative += excess
        require(Q(row['cost']) == value and Q(row['optimum']) == optimum)
        require(Q(row['excess']) == excess and Q(row['cumulative_excess']) == cumulative)
        require(0 <= cumulative <= 3)
        previous = current
    require(Q(data['excess_sum']) == cumulative and data['maximum_recourse'] == max(counts))
    return dict(verified=True, prefixes=4, anchored=anchored, excess_sum=str(cumulative),
                maximum_recourse=max(counts), independent_method='all injective matchings')


def audit(out):
    # The producer supplies trajectories only; verify() never calls its calculations.
    from four_budget2_policy import run
    out.mkdir(parents=True, exist_ok=False)
    start = time.process_time()
    summary = dict(status='incomplete', alphabet=ALPHABET, boundary_cases=BOUNDARY_CASES,
                   cpu_limit=1800, grid_sequences=0, boundary_sequences=0, prefixes=0,
                   anchored_sequences=0, maximum_excess='0', maximum_recourse=0)
    try:
        with gzip.open(out / 'trajectories.jsonl.gz', 'wt', encoding='utf-8') as stream:
            for group, sequences in [('grid', product(ALPHABET, repeat=4)), ('boundary', BOUNDARY_CASES)]:
                for requests in sequences:
                    if time.process_time() - start > 1800:
                        raise TimeoutError('policy verification CPU cap reached')
                    data = run(requests)
                    checked = verify(data)
                    stream.write(json.dumps(dict(group=group, data=data, verification=checked), separators=(',', ':')) + '\n')
                    summary[group + '_sequences'] += 1
                    summary['prefixes'] += 4
                    summary['anchored_sequences'] += checked['anchored']
                    summary['maximum_recourse'] = max(summary['maximum_recourse'], checked['maximum_recourse'])
                    if Q(checked['excess_sum']) > Q(summary['maximum_excess']):
                        summary['maximum_excess'] = checked['excess_sum']
                        summary['witness_requests'] = list(requests)
        require(summary['grid_sequences'] == 6561 and summary['boundary_sequences'] == 8)
        require(summary['maximum_excess'] == '3')
        for name, requests in [('lower_witness', ('1/2', '-1', '2', '-4')),
                               ('anchor_example', ('6', '7', '8', '-4'))]:
            data = run(requests)
            with (out / (name + '.json')).open('x', encoding='utf-8') as stream:
                json.dump(data, stream, indent=2)
                stream.write('\n')
        summary['status'] = 'verified'
    finally:
        summary['cpu_seconds'] = time.process_time() - start
        summary['finished_utc'] = datetime.now(timezone.utc).isoformat()
        with (out / 'verification.json').open('x', encoding='utf-8') as stream:
            json.dump(summary, stream, indent=2)
            stream.write('\n')
        print(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--audit-output', type=Path)
    args = parser.parse_args()
    if (args.input is None) == (args.audit_output is None):
        parser.error('choose exactly one of --input and --audit-output')
    if args.input:
        print(json.dumps(verify(json.loads(args.input.read_text(encoding='utf-8'))), indent=2))
    else:
        audit(args.audit_output)


if __name__ == '__main__':
    main()
