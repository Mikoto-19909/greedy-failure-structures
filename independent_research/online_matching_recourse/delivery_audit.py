"""One-off final delivery readback; no algorithm execution or new instances."""
import hashlib
import json
from pathlib import Path
import re
import sys

root = Path(sys.argv[1]).resolve()
primary_dev = root / 'output/20260924T175730918352Z-dev'
primary_eval = root / 'output/20260924T175731049376Z-eval'
replay_dev = root / 'output/20260924T180629379130Z-dev'
replay_eval = root / 'output/20260924T180629716389Z-eval'


def load(p):
    return json.loads(p.read_text(encoding='utf-8'))


def deterministic(folder):
    return [{k: v for k, v in r.items() if k not in ('cpu_seconds', 'wall_seconds')}
            for r in load(folder / 'traces.json')]


assert deterministic(primary_dev) == deterministic(replay_dev)
assert deterministic(primary_eval) == deterministic(replay_eval)
hashes_checked = 0
for folder in [primary_eval, replay_eval]:
    for rel, expected in load(folder / 'artifact_hashes.json').items():
        assert hashlib.sha256((folder / rel).read_bytes()).hexdigest() == expected, rel
        hashes_checked += 1
    assert len(list((folder / 'figures').glob('*.png'))) == 3
links_checked = 0
for document in [root/'README.md', *sorted((root/'报告').glob('*.md'))]:
    for target in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):
            continue
        relative = target.split('#')[0]
        assert (document.parent / relative).exists(), (document.name, target)
        links_checked += 1
runtime = {
    'saved_run_cpu_seconds': sum(load(p)['runtime']['process_cpu_seconds'] for p in (root/'output').glob('*/summary.json')),
    'saved_verification_cpu_seconds': sum(load(p)['cpu_seconds'] for p in (root/'output').glob('*/verification.json')),
    'saved_analysis_cpu_seconds': sum(load(p)['analysis_process_cpu_seconds'] for p in (root/'output').glob('*/analysis_runtime.json')),
}
result = dict(status='automatic_verification_passed_user_review_pending',
              default_repository_entrypoint_passed=True, deterministic_replay_dev=True,
              deterministic_replay_eval=True, checked_artifact_hashes=hashes_checked,
              checked_local_document_links=links_checked, measured_component_cpu=runtime,
              timing_scope='Saved run, verification and plot CPU only; excludes startup, exploratory print, unit checks and paper processing.',
              distinct_sequence_records=30, primary_eval=primary_eval.name, replay_eval=replay_eval.name,
              user_personal_review=False, remote_published=False)
(root/'过程/交付核对.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
