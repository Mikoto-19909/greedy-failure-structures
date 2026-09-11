"""Prepare a bounded static review package from committed Git objects only."""
from __future__ import annotations

import argparse
import ast
from collections import deque
from dataclasses import dataclass
import html
import io
import os
from pathlib import Path
import subprocess
import sys
import tokenize

MAX_FILE_BYTES = 512 * 1024
MAX_SCAN_BYTES = 8 * 1024 * 1024
MAX_PYTHON_FILES = 500
MAX_SNAPSHOTS = 80
MAX_IMPORT_DEPTH = 3
PREREQUISITES = ('AGENTS.md', 'CONTRIBUTING.md', 'pyproject.toml',
                 'docs/checks_and_evidence.zh-CN.md', 'scripts/check.py',
                 'scripts/check_profiles.py')


def git(repo: Path, *args: str) -> bytes:
    # Inherited repository redirection must not override --repo. No lazy fetches,
    # replace objects, optional index refreshes, or user-supplied diff programs.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update(GIT_OPTIONAL_LOCKS='0', GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0')
    result = subprocess.run(
        ['git', '--no-pager', '--no-replace-objects', '-c', 'core.fsmonitor=false',
         '-c', 'protocol.allow=never', '-C', str(repo), *args],
        env=env, capture_output=True, timeout=60)
    if result.returncode:
        if args[0] == 'merge-base' and result.returncode == 1:
            raise ValueError('no common ancestor found; use related commits with complete history')
        raise ValueError(f'git {args[0]} failed: {result.stderr.decode("utf-8", "replace").strip()}')
    return result.stdout


@dataclass(frozen=True)
class Entry:
    mode: str
    oid: str
    size: int


@dataclass(frozen=True)
class Change:
    status: str
    old: str
    new: str
    added: str
    deleted: str


def tree(repo: Path, revision: str) -> dict[str, Entry]:
    entries = {}
    for record in git(repo, 'ls-tree', '-r', '-l', '-z', revision).split(b'\0'):
        if record:
            meta, path = record.split(b'\t', 1)
            mode, kind, oid, size = meta.decode('ascii').split()
            entries[path.decode('utf-8', 'surrogateescape')] = Entry(
                mode, oid, int(size) if kind == 'blob' else 0)
    return entries


def changes(repo: Path, start: str, head: str) -> tuple[list[Change], bytes]:
    options = ('--no-ext-diff', '--no-textconv', '--ignore-submodules=none',
               '--find-renames', '--no-color')
    names = git(repo, 'diff', *options, '--name-status', '-z', start, head, '--').split(b'\0')
    stats = iter(git(repo, 'diff', *options, '--numstat', '-z', start, head, '--').split(b'\0'))
    result = []
    index = 0
    while names[index]:
        status = names[index].decode('ascii')
        old = names[index + 1].decode('utf-8', 'surrogateescape')
        index += 2
        new = old
        if status[0] in 'RC':
            new = names[index].decode('utf-8', 'surrogateescape')
            index += 1
        added, deleted, path = next(stats).split(b'\t', 2)
        if not path:  # Renames use an empty path followed by two NUL fields.
            next(stats)
            next(stats)
        result.append(Change(status, old, new, added.decode(), deleted.decode()))
    patch = git(repo, 'diff', *options, '--binary', '--full-index', start, head, '--')
    return result, patch


def output_path(repo: Path, requested: Path) -> Path:
    destination = requested.resolve()
    if requested.exists() or requested.is_symlink() or destination.exists():
        raise ValueError('output already exists; choose a new directory')
    forbidden = [repo.resolve()]
    for field in git(repo, 'worktree', 'list', '--porcelain', '-z').split(b'\0'):
        if field.startswith(b'worktree '):
            forbidden.append(Path(os.fsdecode(field[9:])).resolve())
    for option in ('--git-common-dir', '--git-dir'):
        raw = os.fsdecode(git(repo, 'rev-parse', '--path-format=absolute', option).strip())
        forbidden.append(Path(raw).resolve())
    if any(destination.is_relative_to(root) for root in forbidden):
        raise ValueError('output must be outside the source repository, Git directories and registered worktrees')
    if not destination.parent.is_dir():
        raise ValueError('output parent must already be a directory')
    return destination


def display(value: str) -> str:
    # Repository filenames and source fragments are data, never Markdown/HTML.
    escaped = html.escape(ascii(value)[1:-1] if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF
                                                  for c in value) else value)
    for character in '`[]\\':
        escaped = escaped.replace(character, f'&#{ord(character)};')
    return escaped


def definitions(parsed: ast.Module) -> dict[str, ast.stmt]:
    result: dict[str, ast.stmt] = {}
    for node in parsed.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            result[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    result[target.id] = node
    return result


def module_name(path: str) -> str:
    path = path.removeprefix('src/').removesuffix('.py').replace('/', '.')
    return path.removesuffix('.__init__')


def imports(path: str, parsed: ast.Module) -> set[str]:
    found: set[str] = set()
    package = module_name(path).split('.')
    if not path.endswith('/__init__.py'):
        package.pop()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = package[:len(package) - node.level + 1] if node.level else []
            if node.module:
                prefix += node.module.split('.')
            base = '.'.join(prefix)
            found.add(base)
            found.update(f'{base}.{alias.name}' for alias in node.names if alias.name != '*')
    return found - {''}


def prepare(repo: Path, base: str, head: str, output: Path) -> Path:
    repo = repo.resolve(strict=True)
    destination = output_path(repo, output)
    base_sha, head_sha = [git(repo, 'rev-parse', '--verify', '--end-of-options',
                               ref + '^{commit}').decode('ascii').strip() for ref in (base, head)]
    if git(repo, 'rev-parse', '--is-shallow-repository').strip() != b'false':
        raise ValueError('shallow history is unsupported; use a complete local clone')
    ancestors = git(repo, 'merge-base', '--all', base_sha, head_sha).decode('ascii').splitlines()
    if len(ancestors) != 1:
        raise ValueError('expected exactly one common ancestor')
    start = ancestors[0]
    modified, patch = changes(repo, start, head_sha)
    trees = {'base': tree(repo, start), 'head': tree(repo, head_sha)}
    notes: list[str] = []
    cache: dict[str, bytes] = {}
    sources: dict[tuple[str, str], tuple[bytes, ast.Module | None]] = {}
    snapshots: dict[tuple[str, str], str] = {}

    def source(side: str, path: str) -> tuple[bytes, ast.Module | None] | None:
        key = (side, path)
        if key in sources:
            return sources[key]
        entry = trees[side].get(path)
        if entry is None:
            return None
        if entry.mode not in {'100644', '100755'} or entry.size > MAX_FILE_BYTES:
            notes.append(f'{side}:{path}: snapshot omitted (mode {entry.mode}, {entry.size} bytes)')
            return None
        if entry.oid not in cache:
            cache[entry.oid] = git(repo, 'cat-file', 'blob', entry.oid)
        data = cache[entry.oid]
        if b'\0' in data:
            notes.append(f'{side}:{path}: binary snapshot omitted; inspect diff.patch')
            return None
        parsed = None
        try:
            encoding = tokenize.detect_encoding(io.BytesIO(data).readline)[0] if path.endswith('.py') else 'utf-8'
            data.decode(encoding)
            if path.endswith('.py'):
                parsed = ast.parse(data, filename=path)
        except (UnicodeError, SyntaxError, LookupError, ValueError, RecursionError) as error:
            notes.append(f'{side}:{path}: text/AST unavailable ({type(error).__name__})')
            return None
        sources[key] = data, parsed
        return sources[key]

    def include(side: str, path: str, reason: str) -> bool:
        key = (side, path)
        if key in snapshots:
            return True
        if len(snapshots) >= MAX_SNAPSHOTS:
            notes.append(f'{side}:{path}: snapshot limit reached; {reason}')
            return False
        if source(side, path) is None:
            return False
        snapshots[key] = reason
        return True

    symbols: set[str] = set()
    for change in modified:
        old = source('base', change.old) if change.status[0] != 'A' else None
        new = source('head', change.new) if change.status[0] != 'D' else None
        for side, path, value in (('base', change.old, old), ('head', change.new, new)):
            if value is not None:
                include(side, path, 'changed file')
        before = definitions(old[1]) if old and old[1] else {}
        after = definitions(new[1]) if new and new[1] else {}
        symbols.update(name for name in before.keys() | after.keys()
                       if name not in before or name not in after
                       or ast.dump(before[name]) != ast.dump(after[name]))
    for path in PREREQUISITES:
        if path in trees['head']:
            include('head', path, 'execution prerequisites / existing check entry (not executed)')

    # Bounded AST scan is navigation, not a complete call graph or test selector.
    paths = sorted(p for p in trees['head'] if p.endswith('.py'))
    modules: dict[str, list[str]] = {}
    for path in paths:
        modules.setdefault(module_name(path), []).append(path)
    scanned: dict[str, ast.Module] = {}
    scanned_bytes = 0
    for index, path in enumerate(paths if symbols else []):
        size = trees['head'][path].size
        if index >= MAX_PYTHON_FILES or scanned_bytes + size > MAX_SCAN_BYTES:
            notes.append('Python scan truncated by file/byte budget; further callers and tests may be absent')
            break
        scanned_bytes += size
        value = source('head', path)
        if value and value[1]:
            scanned[path] = value[1]
    references: dict[str, list[tuple[int, str]]] = {}
    for path, scanned_tree in scanned.items():
        hits = set()
        for node in ast.walk(scanned_tree):
            name = (node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute)
                    else node.name if isinstance(node, ast.alias)
                    else node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None)
            if name in symbols and isinstance(node, (ast.Name, ast.Attribute, ast.alias, ast.Constant)):
                hits.add((node.lineno, name))
        if hits:
            references[path] = sorted(hits)
            include('head', path, 'symbol reference candidate')

    queue = deque((p, 0) for side, p in list(snapshots) if side == 'head' and p.endswith('.py'))
    visited = set()
    unresolved: dict[str, set[str]] = {}
    while queue:
        path, depth = queue.popleft()
        if path in visited:
            continue
        visited.add(path)
        value = source('head', path)
        if not value or not value[1]:
            continue
        for name in sorted(imports(path, value[1])):
            candidates = modules.get(name, [])
            if not candidates:
                # "from x import y" can name a symbol, rather than another module.
                parent = name.rpartition('.')[0]
                if parent not in modules and name.split('.')[0] not in sys.stdlib_module_names:
                    unresolved.setdefault(path, set()).add(name)
                continue
            for dependency in candidates:
                if ('head', dependency) in snapshots:
                    continue
                if depth >= MAX_IMPORT_DEPTH:
                    notes.append(f'{path}: dependency {dependency} omitted at import depth limit')
                elif include('head', dependency, f'import from {path}'):
                    queue.append((dependency, depth + 1))
    for path, names in unresolved.items():
        notes.append(f'{path}: unresolved non-stdlib imports: {", ".join(sorted(names))}')

    # Numbered text files avoid recreating untrusted tree paths, symlinks, executable
    # files, Windows reserved names, or case collisions in the review directory.
    links = {key: f'snapshot/{index:03d}.txt' for index, key in enumerate(snapshots, 1)}
    lines = ['# Static review preparation', '',
             f'- Requested base: `{display(base)}` → `{base_sha}`',
             f'- Requested head: `{display(head)}` → `{head_sha}`',
             f'- Actual diff start (unique merge-base): `{start}`',
             '- `base:` snapshot labels below mean the actual diff start, not necessarily the requested base.',
             '- Committed objects only. Uncommitted/staged files and ignored local logs are not included.',
             '- No target project modules, tests, check listing, hooks or diff/textconv programs were executed.',
             '- This package gives static navigation; it gives no approval or behavioral correctness verdict.', '',
             '## Change scope', '', f'{len(modified)} changed files. [Raw binary-capable patch](diff.patch).', '']
    if not modified:
        lines += ['No differences from the actual diff start.', '']
    for change in modified:
        category = ('test' if change.new.startswith('tests/') else 'prose' if change.new.endswith('.md')
                    else 'Python source' if change.new.endswith('.py') else 'other')
        size_label = (f'+{change.added}/-{change.deleted}' if change.added.isdigit() else 'binary')
        lines.append(f'- {change.status} [{category}] `{display(change.old)}`'
                     + (f' → `{display(change.new)}`' if change.old != change.new else '')
                     + f': {size_label}.')
    largest = sorted((c for c in modified if c.added.isdigit() and c.deleted.isdigit()),
                     key=lambda c: int(c.added) + int(c.deleted), reverse=True)[:5]
    lines += ['', 'Largest textual changes (added + deleted lines): ' + ', '.join(
        f'`{display(c.new)}` ({int(c.added) + int(c.deleted)})' for c in largest), '',
        '## Source navigation', '',
        f'Parsed {len(scanned)} head Python files. Snapshot limit: {MAX_SNAPSHOTS}; '
        f'file limit: {MAX_FILE_BYTES} bytes; import depth: {MAX_IMPORT_DEPTH}.', '',
        'Changed top-level definition names (AST comparison; no equivalence claim): '
        + ', '.join(f'`{display(s)}`' for s in sorted(symbols)), '']
    for key, reason in snapshots.items():
        side, path = key
        lines.append(f'- [{side}: {display(path)}]({links[key]}): {display(reason)}.')
        parsed = sources[key][1]
        if parsed:
            for name, node in definitions(parsed).items():
                if name in symbols:
                    lines.append(f'  - Definition `{display(name)}`: L{node.lineno}–L{node.end_lineno}.')
    lines += ['', '## Reference candidates', '',
              'Name and exact string matches can include unrelated names. Aliases, dynamic imports, pickle, `__module__`, '
              'and monkey-patch behavior need human inspection. Unchanged callers are included when found.', '']
    for path, reference_hits in references.items():
        link = links.get(('head', path))
        label = f'[{display(path)}]({link})' if link else f'`{display(path)}` (snapshot omitted)'
        lines.append(f'- {label}: ' + ', '.join(f'L{line} `{display(name)}`' for line, name in reference_hits[:25])
                     + (f'; {len(reference_hits) - 25} more matches omitted' if len(reference_hits) > 25 else ''))
    lines += ['', '## Check candidates and prerequisites', '',
              'These are static definitions in selected test files, not discovered/executed tests or coverage guarantees. '
              'Inspect fixtures and assertions to choose a valid input and an invalid input; confirm the actual scope. '
              'Confirm imports, Python version, dependencies and test data from the prerequisite snapshots before running anything. '
              'Do not automatically apply full-research setup to a targeted test. Even `--list` may import project code.', '']
    for (side, path), link in links.items():
        parsed = sources[(side, path)][1]
        if side != 'head' or not path.startswith('tests/') or parsed is None:
            continue
        for node in parsed.body:
            members = node.body if isinstance(node, ast.ClassDef) else [node]
            for member in members:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name.startswith('test_'):
                    test_id = path.removeprefix('tests/').removesuffix('.py').replace('/', '.') + '.'
                    if isinstance(node, ast.ClassDef):
                        test_id += node.name + '.'
                    test_id += member.name
                    lines.append(f'- `{display(test_id)}`: [{display(path)} L{member.lineno}]({link}).')
    lines += ['', 'Suggested next actions (not executed):', '',
              '1. Read changed definitions, old exports, unchanged reference candidates, and imported contract definitions.',
              '2. Choose targeted valid/invalid input checks from the IDs above using the repository\'s existing test entry. '
              'Inspect the check script and contribution guide for full merge requirements.',
              '3. Trace validator imports. Reuse of the changed calculation only checks consistency; '
              'it is not an independent proof of that calculation.',
              '4. Obtain the original inputs/logs for claims in source documents; reproduce them separately if needed.', '',
              '## Evidence limits and unverified items', '',
              '- Checked here: fixed revisions, unique merge-base, committed diff, bounded source/AST navigation.',
              '- Historical claims in included documents are source statements, not verified results. '
              'Referenced local logs, ignored results and remote availability have not been checked.',
              '- Not checked: behavioral equivalence, runtime imports, minimal sufficient tests, validator independence, '
              'clean-environment execution, performance, or review time savings.',
              '- Snapshots are reading material, not an executable checkout. Binary files, symlinks and submodules '
              'are not materialized; the patch retains their Git changes. Base dependency closure is not collected. '
              'Imports recognized as standard library by the preparing interpreter are omitted from unresolved listings.', '']
    lines += [f'- {display(note)}' for note in sorted(set(notes))]
    # Validate again immediately before writing. review.md is written last; a
    # failed write leaves partial files for diagnosis, never a success report.
    if output_path(repo, output) != destination:
        raise ValueError('output target changed during preparation')
    destination.mkdir()
    (destination / 'snapshot').mkdir()
    (destination / 'diff.patch').write_bytes(patch)
    for key, link in links.items():
        (destination / link).write_bytes(sources[key][0])
    report = destination / 'review.md'
    temporary_report = destination / 'review.md.partial'
    temporary_report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    temporary_report.rename(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = prepare(args.repo, args.base, args.head, args.output)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'Preparation failed: {error}', file=sys.stderr)
        return 1
    print(f'Prepared static review: {report}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
