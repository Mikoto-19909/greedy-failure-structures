"""Read back the seven requested research branches; do not rerun solved experiments."""
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def load(relative):
    return json.loads((ROOT/relative).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    chain = load('output/chain_first_20260925T133017/verification.json')
    raw = load('output/random_raw_20260925T052605840780Z/verification.json')
    ablation = load('output/ablation_20260925T052608642708Z/summary.json')
    av = load('output/ablation_20260925T052608642708Z/verification.json')
    four = load('output/four_game_20260925T053018894723Z/summary.json')
    fv = load('output/four_game_20260925T053018894723Z/verification.json')
    continuous = load('output/continuous_four_20260925T054559888763Z/summary.json')
    cv = load('output/continuous_four_20260925T054559888763Z/verification.json')
    lit = load('evidence/literature_verification.json')
    assert chain['all_checks_passed'] and chain['prefix_checks'] == 1690
    assert chain['first_games'] == 23 and chain['off_grid_rational_prefix_checks'] == 48
    assert raw['checks']['prefixes'] == 845 and raw['checks']['lp_solved'] == 1690
    assert raw['checks']['raw_random_strict_improvements'] == 36
    assert raw['max_lp_certificate_residual'] < 1e-8
    assert av['trajectories'] == 448 and av['stages'] == 2613
    assert av['unchanged_historical_trajectories'] == 180
    for model in ('atomic', 'chain'):
        assert [r['value'] for r in four['results'] if r['model']==model] == [4, 2, 0]
    assert fv['all_checks_passed'] and len(fv['results']) == 9
    assert fv['source_sha256'] == digest(ROOT/'output/four_game_20260925T053018894723Z/summary.json')
    assert fv['verifier_sha256'] == digest(ROOT/'output/four_game_20260925T053018894723Z/verify_four_game.py')
    assert cv['all_checks_passed'] and len(cv['results']) == 4
    assert cv['source_sha256'] == digest(ROOT/'output/continuous_four_20260925T054559888763Z/summary.json')
    assert cv['verifier_sha256'] == digest(ROOT/'output/continuous_four_20260925T054559888763Z/verify_four_game.py')
    for model in ('atomic', 'chain'):
        assert [r['value'] for r in continuous['results'] if r['model']==model] == [9, 2]
    assert continuous['rounding']['additive_certificate'] == 12
    from fractions import Fraction
    from continuous_four_bounds import round_request
    nearest = lambda r: min(range(4), key=lambda i:(abs(r-continuous['servers'][i]), continuous['servers'][i]))
    for r in [Fraction(-4)+Fraction(i,8) for i in range(97)]:
        assert abs(round_request(r)-r) <= Fraction(1,2)
        assert abs(round_request(r, first=True)-r) <= 1
        assert nearest(round_request(r, first=True)) == nearest(r)
    assert lit['target_fulltext_obtained'] is False
    assert len(lit['fulltext_files']) == 3
    for f in lit['fulltext_files']:
        assert digest(ROOT/'evidence'/f['file']) == f['sha256'] and f['pdf_magic_valid']
    baseline = json.loads((ROOT.parent/'input_manifest.json').read_text())
    assert digest(ROOT.parent/'inputs.json') == baseline['input_sha256'] == ablation['original_sha256']
    links_checked = 0
    for document in [ROOT/'README.md', *sorted((ROOT/'报告').glob('*.md'))]:
        body = document.read_text(encoding='utf-8')
        assert not any(token in body for token in ('TODO', '待 root 补充', '数值核验待'))
        for link in re.findall(r'\]\(([^)]+)\)', body):
            if '://' in link or link.startswith('#'):
                continue
            assert (document.parent/link.split('#')[0]).exists(), (document, link)
            links_checked += 1
    for source in ROOT.glob('*.py'):
        ast.parse(source.read_text(encoding='utf-8'), filename=source.name)
    assert len(list((ROOT/'报告/图').glob('*.png'))) == 2
    cpu = sum(json.loads(p.read_text(encoding='utf-8'))['cpu_seconds'] for p in (ROOT/'output').glob('chain_first_*/verification.json'))
    cpu += raw['cpu_seconds']+ablation['runtime']['cpu_seconds']+av['cpu_seconds']+four['cpu_seconds']+fv['cpu_seconds']
    cpu += load('output/plot_runtime.json')['cpu_seconds']
    cpu += continuous['cpu_seconds']+cv['cpu_seconds']
    assert cpu < 7200
    evidence = [
        dict(branch=1, outcome='continuous single-chain exact decision, strict timing reversal', evidence='报告/链动作与自由首步.md'),
        dict(branch=2, outcome='continuous free-first minimax procedure, strict nearest counterexample', evidence='报告/链动作与自由首步.md'),
        dict(branch=3, outcome='tight n-1 bound, 4 stress sequences, finite four-request games and convergent continuous bounds', evidence='报告/更多请求与策略拆分.md', limit='continuous four-request budgets 1/2 bounded by intervals, not exact values'),
        dict(branch=4, outcome='two-factor ablation at budgets 1/2/4 and four development price coefficients', evidence='output/ablation_20260925T052608642708Z/verification.json'),
        dict(branch=5, outcome='no random advantage for excess; exact 62-to-60 raw-cost game', evidence='报告/随机化与原始成本.md'),
        dict(branch=6, outcome='general three-point raw-cost formulas and continuous finite-game reduction', evidence='报告/随机化与原始成本.md'),
        dict(branch='literature', outcome='expanded primary-source search and 3 additional fulltexts', evidence='报告/补充文献核查.md', limit='named FSTTCS fulltext not obtained; novelty unresolved')]
    result = dict(status='automatic_verification_passed_user_review_pending', branches=evidence,
                  local_document_links_checked=links_checked, recorded_component_cpu_seconds=cpu,
                  timing_scope='saved compute, verification and plot components; excludes imports, searches and document work',
                  failed_verification_attempt_approximately_cpu_seconds=180,
                  original_input_unchanged=baseline['input_sha256'], figures_visually_checked=2,
                  user_personal_review=False, remote_published=False,
                  hashes={p.relative_to(ROOT).as_posix():digest(p) for p in sorted(ROOT.rglob('*'))
                          if p.is_file() and p.name!='delivery_audit.json' and '__pycache__' not in p.parts})
    (ROOT/'delivery_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='hashes'}, ensure_ascii=False))
    print('Files hashed:', len(result['hashes']))


if __name__=='__main__':
    main()
