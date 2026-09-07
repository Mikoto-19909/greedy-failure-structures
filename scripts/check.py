"""Run core + research + mypy by default; full discovery remains supported."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_profiles import ANALYSIS_OWNERS, GROUPS, RESEARCH_MODULES, REQUIRED_RESEARCH, OPTIONAL_CASES, affected_groups, extended_group, is_platform, is_research

def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item

def validate_research_registration(root: Path, cases) -> None:
    files = {p.relative_to(root / 'analysis').as_posix() for p in (root / 'analysis').rglob('*.py')}
    if files != set(ANALYSIS_OWNERS):
        raise ValueError(f'analysis ownership must be reviewed: new={sorted(files-set(ANALYSIS_OWNERS))}, missing={sorted(set(ANALYSIS_OWNERS)-files)}')
    discovered = {case.id() for case in cases}
    modules = {case.id().split('.')[0] for case in cases}
    for owner in set(ANALYSIS_OWNERS.values()) - {'tool'}:
        if owner not in RESEARCH_MODULES or not set(RESEARCH_MODULES[owner]) <= modules:
            raise ValueError(f'missing executable research verification: {owner}')
        required = REQUIRED_RESEARCH.get(owner, ())
        if len(required) < 2 or not set(required) <= discovered:
            raise ValueError(f'missing required verification scenarios for {owner}: {sorted(set(required)-discovered)}')

def ci_groups() -> set[str]:
    if os.environ.get('GITHUB_EVENT_NAME') != 'pull_request':
        return set(GROUPS)
    try:
        spec = importlib.util.spec_from_file_location('ci_change_reader', ROOT / '.github/scripts/classify_ci_changes.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        raw = module._pr_diff(ROOT, json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes()))
        fields = raw[:-1].split(b'\0')
        if not raw or not raw.endswith(b'\0') or len(fields) % 2:
            return set(GROUPS)
        return affected_groups([p.decode('utf-8', errors='strict') for p in fields[1::2]])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return set(GROUPS)

def selected(cases, profile, groups=(), omit_research=False):
    return [case for case in cases if (
        profile == 'full' or
        (profile == 'optional' and case.id() in OPTIONAL_CASES) or
        (profile == 'research' and is_research(case.id())) or
        (profile == 'platform' and is_platform(case.id())) or
        (profile == 'core' and (extended_group(case.id()) is None or extended_group(case.id()) in groups))
    ) and not (omit_research and is_research(case.id()))]

def validate_optional(cases):
    missing = OPTIONAL_CASES - {case.id() for case in cases}
    if missing:
        raise ValueError(f'missing required optional verification: {sorted(missing)}')

class ExecutionResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.successful = set()

    def addSuccess(self, test):
        self.successful.add(test.id())
        super().addSuccess(test)


def execution_succeeded(result, required):
    missing = required - result.successful
    if missing:
        print(f'Required verification did not succeed: {sorted(missing)}', file=sys.stderr)
    return result.wasSuccessful() and not missing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('core', 'platform', 'research', 'full', 'optional'), default='core')
    parser.add_argument('--tests-only', action='store_true')
    parser.add_argument('--omit-research', action='store_true', help='CI only: research has a separate required job')
    parser.add_argument('--ci', action='store_true', help='Add affected extended groups from the complete PR diff')
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    loader = unittest.TestLoader()
    cases = list(flatten(loader.discover(str(ROOT / 'tests'))))
    try:
        if loader.errors:
            raise ValueError('\n'.join(loader.errors))
        validate_research_registration(ROOT, cases)
        if args.profile == 'optional':
            validate_optional(cases)
        groups = ci_groups() if args.ci else set()
        chosen = selected(cases, args.profile, groups, args.omit_research)
        if not chosen:
            raise ValueError('no tests selected')
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(f'Profile {args.profile}: {len(chosen)}/{len(cases)} tests; extra groups={sorted(groups)}', flush=True)
    if args.list:
        print('\n'.join(case.id() for case in chosen))
        return 0
    result = unittest.TextTestRunner(verbosity=2, resultclass=ExecutionResult).run(unittest.TestSuite(chosen))
    required = {case.id() for case in chosen if is_research(case.id()) or (args.profile == 'optional' and case.id() in OPTIONAL_CASES)}
    if not execution_succeeded(result, required):
        return 1
    if not args.tests_only:
        return subprocess.call([sys.executable, '-m', 'mypy'], cwd=ROOT)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
