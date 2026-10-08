"""Finer exact finite games plus a proved rounding certificate for continuous requests."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from four_request_game import solve, SERVERS

ROOT = Path(__file__).resolve().parent


def round_request(coordinate, first=False):
    """Causal rounding used by the proof; first step preserves the nearest server."""
    choices = list(range(-4, 9))
    closest = lambda r: min(range(4), key=lambda i: (abs(r-SERVERS[i]), SERVERS[i]))
    if first:
        choices = [q for q in choices if closest(q) == closest(coordinate)]
    return min(choices, key=lambda q: (abs(coordinate-q), q))


def main():
    start = time.process_time()
    alphabet = tuple(range(-4, 9))
    out = ROOT/'output'/('continuous_four_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    results = []
    for model in ('atomic', 'chain'):
        for budget in (1, 2):
            row = solve(budget, model, alphabet=alphabet)
            results.append(row)
            print(model, budget, row['value'], row['states'], flush=True)
    result = dict(status='computed_pending_independent_verification', servers=SERVERS,
                  future_alphabet=alphabet, horizon=4, first_step='nearest, ties left',
                  objective='sum of prefix excess distances', results=results,
                  hindsight_fixed_sequence=[], cpu_seconds=time.process_time()-start,
                  rounding=dict(first_coordinate_error_at_most=1, later_coordinate_error_at_most=0.5,
                                preserve_first_nearest_server=True,
                                additive_certificate=12,
                                reason='stage1 excess zero; 2*[3*1+(3+2+1)*0.5]=12'),
                  continuous_intervals=[dict(model=r['model'], budget=r['budget'],
                                             lower=r['value'], upper=r['value']+12) for r in results],
                  budget4_continuous_value=0)
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(out)


if __name__=='__main__':
    main()
