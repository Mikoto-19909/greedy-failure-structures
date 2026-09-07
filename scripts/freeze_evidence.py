"""Prepare an explicit evidence-only Git snapshot, then publish and read it back."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 50 * 1024 * 1024

def git(directory: Path, *arguments: str) -> str:
    return subprocess.run(['git', '-C', str(directory), *arguments], check=True,
                          capture_output=True, text=True, encoding='utf-8').stdout.strip()

def prepare(source: Path, output: Path, batch: str, files: list[str], notes: str) -> str:
    source, output = source.resolve(), output.resolve()
    if not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', batch):
        raise ValueError('batch must contain lowercase letters, digits, dots, underscores or hyphens')
    if output.exists():
        raise ValueError('snapshot destination already exists; use a new batch or publish the prepared snapshot')
    if git(source, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('commit intended source changes before freezing evidence')
    commit = git(source, 'rev-parse', 'HEAD')
    selected: dict[str, Path] = {}
    for value in files:
        raw = Path(value)
        if raw.is_absolute() or '..' in raw.parts or any(part.casefold() in {'.git', '.venv', '.codex', '.agents'} for part in raw.parts):
            raise ValueError(f'file must be an explicit repository-relative evidence path: {value}')
        path = source / raw
        if any(parent.is_symlink() for parent in [path, *path.parents] if parent != source.parent):
            raise ValueError(f'symlink is not evidence: {value}')
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(source) or not resolved.is_file():
            raise ValueError(f'not an evidence file: {value}')
        if resolved.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f'evidence exceeds the 50 MiB per-file limit; choose another reviewed storage method: {value}')
        if raw.as_posix().casefold() in {name.casefold() for name in selected} or raw.as_posix().casefold() == 'freeze.md':
            raise ValueError(f'duplicate or reserved path: {value}')
        selected[raw.as_posix()] = resolved
    if not selected or not notes.strip():
        raise ValueError('explicit files and run/verification notes are required')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.freeze-', dir=output.parent) as directory:
        staged = Path(directory) / 'snapshot'
        staged.mkdir()
        for name, path in selected.items():
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        listing = '\n'.join(f'- {name} ({(staged / name).stat().st_size} bytes)' for name in sorted(selected))
        (staged / 'FREEZE.md').write_text(
            f'# Evidence snapshot: {batch}\n\nSource commit: `{commit}`\n\n'
            f'## Run and verification notes\n\n{notes.strip()}\n\n## Included evidence\n\n{listing}\n\n'
            'This prepared snapshot is local until publish verifies the remote commit and tree.\n'
            'Git integrity does not establish scientific correctness.\n', encoding='utf-8')
        git(staged, 'init', '-q', '--initial-branch', f'codex/evidence/{batch}')
        for key in ('user.name', 'user.email'):
            value = git(source, 'config', '--get', key)
            if not value:
                raise ValueError(f'configure {key} before preparing a snapshot')
            git(staged, 'config', key, value)
        git(staged, 'config', 'core.autocrlf', 'false')
        git(staged, 'config', 'commit.gpgsign', 'false')
        git(staged, 'add', '--all', '--force')
        git(staged, 'commit', '-qm', f'Freeze evidence for {batch}')
        evidence_commit = git(staged, 'rev-parse', 'HEAD')
        staged.rename(output)
    return evidence_commit

def publish(snapshot: Path, remote: str) -> str:
    snapshot = snapshot.resolve(strict=True)
    branch = git(snapshot, 'symbolic-ref', '--short', 'HEAD')
    if not re.fullmatch(r'codex/evidence/[a-z0-9][a-z0-9._-]*', branch):
        raise ValueError('publish accepts only prepared evidence branches')
    if git(snapshot, 'status', '--porcelain'):
        raise ValueError('prepared snapshot was modified; do not overwrite frozen evidence')
    if not (snapshot / 'FREEZE.md').is_file():
        raise ValueError('snapshot is missing FREEZE.md')
    commit = git(snapshot, 'rev-parse', 'HEAD')
    reference = f'refs/heads/{branch}'
    existing = git(snapshot, 'ls-remote', '--heads', remote, reference)
    if existing and existing.split()[0] != commit:
        raise ValueError('remote batch already exists with different evidence; use a new batch')
    if not existing:
        git(snapshot, 'push', remote, f'{commit}:{reference}')
    observed = git(snapshot, 'ls-remote', '--heads', remote, reference)
    if not observed or observed.split()[0] != commit:
        raise ValueError('remote commit readback disagrees; snapshot is not confirmed frozen')
    expected_tree = git(snapshot, 'ls-tree', '-r', commit)
    with tempfile.TemporaryDirectory(prefix='evidence-readback-') as directory:
        check = Path(directory)
        git(check, 'init', '--bare', '-q')
        git(check, 'fetch', '--depth=1', remote, reference)
        if git(check, 'rev-parse', 'FETCH_HEAD') != commit or git(check, 'ls-tree', '-r', 'FETCH_HEAD') != expected_tree:
            raise ValueError('remote evidence tree readback disagrees')
    return commit

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--batch', required=True)
    prep.add_argument('--file', action='append', required=True)
    prep.add_argument('--notes', type=Path, required=True, help='Run environment, seeds, verification commands/results and limitations')
    prep.add_argument('--output', type=Path, required=True)
    pub = commands.add_parser('publish')
    pub.add_argument('--snapshot', type=Path, required=True)
    pub.add_argument('--remote', help='Explicit destination; defaults to this checkout origin')
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            commit = prepare(ROOT, args.output, args.batch, args.file, args.notes.read_text(encoding='utf-8'))
            print(f'Prepared locally (not yet frozen): {commit}; inspect {args.output}')
        else:
            remote = args.remote or git(ROOT, 'remote', 'get-url', 'origin')
            commit = publish(args.snapshot, remote)
            print(f'Frozen: remote commit and evidence tree verified: {commit}')
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'Evidence freeze failed; local prepared files are retained: {error}')
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
