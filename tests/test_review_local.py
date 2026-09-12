"""Behavioral tests use local synthetic repositories and a separate reviewer process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import venv
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import review_local as local
from review_process import run_step

STUB = '''import json,sys,time,subprocess
from pathlib import Path
control=Path(__file__).with_suffix('.json')
mode=json.loads(control.read_text())
if '--version' in sys.argv: print('codex-cli test'); raise SystemExit(0)
if sys.argv[1:3]==['login','status']: raise SystemExit(1 if mode.get('login_fail') else 0)
prompt=sys.stdin.read()
out=Path(sys.argv[sys.argv.index('-o')+1]); reader=Path(sys.argv[sys.argv.index('-C')+1])
nonce=(reader/'read-access.txt').read_text()
assert '--ignore-user-config' in sys.argv and '--ephemeral' in sys.argv
assert sys.argv[sys.argv.index('--sandbox')+1]=='read-only'
assert 'CODEX_APP_TOOLS_PIPE_PATH' not in __import__('os').environ
if mode.get('timeout'): time.sleep(30)
if mode.get('stale'):
    subprocess.run(['git','-C',mode['source'],'update-ref','HEAD',mode['base']],check=True)
if mode.get('mutate'): (out.parent/'checkout/src/maxcover/__init__.py').write_text('changed by reviewer')
response={'status':'complete','scope_summary':nonce+' Inspected code and existing check logs.',
          'findings':mode.get('findings',[]),'coverage_gaps':[], 'suggested_checks':[]}
if mode.get('no_read'): response['scope_summary']='Guessing without reading'
if mode.get('incomplete'): response['status']='incomplete'
if mode.get('gap'): response['coverage_gaps']=[{'description':'Cannot read dependency','blocking':True}]
out.write_text('not JSON' if mode.get('malformed') else json.dumps(response),encoding='utf-8')
print(json.dumps('invalid event' if mode.get('bad_event') else {'type':'turn.failed' if mode.get('failed_event') else 'turn.completed'}))
'''


class LocalReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'source'
        self.repo.mkdir()
        local.git(self.repo, 'init', '-q')
        for key, value in (('user.name', 'Local fixture'), ('user.email', 'local@example.invalid'),
                           ('commit.gpgsign', 'false'), ('core.autocrlf', 'false')):
            local.git(self.repo, 'config', key, value)
        self.write('src/maxcover/__init__.py', 'VALUE = 1\n')
        self.write('scripts/check.py', "import sys\nprint('existing check ran', sys.argv[1:])\n")
        self.base = self.commit('base')
        self.write('src/maxcover/__init__.py', 'VALUE = 2\n')
        self.head = self.commit('head')
        self.stub = self.root / 'reviewer.py'
        self.stub.write_text(STUB, encoding='utf-8')
        self.control = self.stub.with_suffix('.json')
        self.control.write_text('{}')
        self.output = self.root / 'output'
        self.addCleanup(patch.stopall)
        patch.object(local, 'REQUIRED_DISTS', ()).start()

    def write(self, path, content):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')

    def commit(self, message):
        local.git(self.repo, 'add', '.')
        local.git(self.repo, 'commit', '-qm', message)
        return local.revision(self.repo, 'HEAD')

    def run_review(self, **kwargs):
        return local.review_local(self.repo, self.base, 'HEAD', kwargs.pop('output', self.output),
                                  kwargs.pop('python', sys.executable), [sys.executable, str(self.stub)], 'test-model', **kwargs)

    def test_relative_python_path_is_resolved_before_entering_the_clone(self):
        previous = Path.cwd()
        try:
            os.chdir(Path(sys.executable).parent)
            result = self.run_review(python='./' + Path(sys.executable).name)
        finally:
            os.chdir(previous)
        self.assertEqual(result['exit_code'], 0, result)
        self.assertEqual(Path(result['checks']['argv'][0]), Path(os.path.abspath(sys.executable)))

    def test_interpreter_directory_alias_is_preserved(self):
        alias = self.root / 'interpreter-alias'
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(Path(sys.executable).parent), str(alias))
            self.addCleanup(alias.rmdir)
        else:
            alias.symlink_to(Path(sys.executable).parent, target_is_directory=True)
        supplied = alias / Path(sys.executable).name
        result = self.run_review(python=str(supplied))
        # A launcher may require a pyvenv.cfg beside this alias. Even on failure,
        # the controller must not silently substitute another executable path.
        self.assertEqual(Path(result['steps']['python-version']['argv'][0]), supplied)

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink-venv runtime regression')
    def test_posix_symlink_venv_remains_the_check_environment(self):
        selected = self.root / 'selected-venv'
        venv.EnvBuilder(with_pip=False, symlinks=True).create(selected)
        self.write('scripts/check.py', f'import sys\nassert sys.prefix == {str(selected)!r}, sys.prefix\n')
        self.commit('assert selected interpreter environment')
        result = self.run_review(python=str(selected / 'bin/python'))
        self.assertEqual(result['exit_code'], 0, result)

    def finding(self, **changes):
        finding = {'title': 'Incorrect constant', 'priority': 2, 'side': 'head',
                   'path': 'src/maxcover/__init__.py', 'line': 1, 'impact': 'Changes returned value.',
                   'evidence': 'VALUE changed from 1 to 2.', 'basis': 'static',
                   'log_reference': None, 'suggested_reproduction': 'Check the intended value.'}
        finding.update(changes)
        return finding

    def test_success_reads_only_commits_and_keeps_source_and_metadata_independent(self):
        self.write('src/maxcover/__init__.py', 'UNCOMMITTED = 99\n')
        state = local.git(self.repo, 'status', '--porcelain')
        index = (self.repo / '.git/index').read_bytes()
        with patch.dict(os.environ, {'GIT_DIR': str(self.root / 'wrong'), 'CODEX_APP_TOOLS_PIPE_PATH': 'forbidden'}):
            result = self.run_review()
        self.assertEqual(result['exit_code'], 0, result)
        self.assertEqual(result['state'], 'no_findings')
        self.assertEqual(result['target']['head'], self.head)
        self.assertEqual((self.output / 'checkout/src/maxcover/__init__.py').read_text(), 'VALUE = 2\n')
        self.assertEqual(local.git(self.repo, 'status', '--porcelain'), state)
        self.assertEqual((self.repo / '.git/index').read_bytes(), index)
        self.assertFalse((self.output / 'checkout/.git/objects/info/alternates').exists())
        self.assertEqual(result['checks']['argv'][-2:], ['--profile', 'core'])
        self.assertNotIn('--omit-research', result['checks']['argv'])
        self.assertEqual(json.loads((self.output / 'summary.json').read_text())['state'], 'no_findings')

    def test_findings_and_failed_checks_need_attention_but_do_not_run_suggested_code(self):
        self.control.write_text(json.dumps({'findings': [self.finding()]}))
        self.assertEqual(self.run_review()['exit_code'], 2)
        self.write('scripts/check.py', "import sys\nprint('genuine check failure')\nsys.exit(3)\n")
        self.commit('failing checks')
        self.control.write_text('{}')
        result = self.run_review(output=self.root / 'failed', checks='full')
        self.assertEqual(result['state'], 'needs_attention')
        self.assertEqual(result['checks']['exit_code'], 3)
        self.assertEqual(result['reviewer']['exit_code'], 0)
        self.assertEqual(result['checks']['argv'][-1], 'full')

    def test_invalid_reviewer_outputs_never_produce_success(self):
        for mode in ({'malformed': True}, {'no_read': True}, {'incomplete': True},
                     {'failed_event': True}, {'bad_event': True}, {'gap': True}, {'mutate': True}):
            with self.subTest(mode=mode):
                self.control.write_text(json.dumps(mode))
                result = self.run_review(output=self.root / next(iter(mode)))
                self.assertEqual(result['state'], 'incomplete', result)
                self.assertEqual(result['exit_code'], 1)
                self.assertTrue(result['reasons'])

    def test_unavailable_login_dependency_and_mutated_check_source_fail_closed(self):
        self.control.write_text('{"login_fail":true}')
        result = self.run_review()
        self.assertEqual(result['exit_code'], 1)
        self.assertFalse((self.output / 'checkout').exists())
        self.control.write_text('{}')
        with patch.object(local, 'REQUIRED_DISTS', ('nonexistent-review-fixture-package',)):
            result = self.run_review(output=self.root / 'dependencies')
        self.assertEqual(result['exit_code'], 1)
        self.assertIsNone(result['checks'])
        self.write('scripts/check.py', "from pathlib import Path\nPath('src/maxcover/__init__.py').write_text('mutated')\n")
        self.commit('mutating check')
        result = self.run_review(output=self.root / 'mutation')
        self.assertEqual(result['exit_code'], 1)
        self.assertIsNone(result['reviewer'])

    def test_moved_source_ref_is_stale_and_excessive_review_time_is_incomplete(self):
        self.control.write_text('{"timeout":true}')
        result = self.run_review(review_timeout=0.3)
        self.assertEqual(result['exit_code'], 1)
        self.assertEqual(result['reviewer']['state'], 'timed_out')
        self.control.write_text(json.dumps({'stale': True, 'source': str(self.repo), 'base': self.base}))
        result = self.run_review(output=self.root / 'stale')
        self.assertEqual(result['exit_code'], 1)
        self.assertIn('stale', ' '.join(result['reasons']))

    def test_existing_output_source_paths_and_missing_revision_are_rejected(self):
        self.output.mkdir()
        (self.output / 'precious').write_text('keep')
        for path in (self.output, self.repo / 'output'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.run_review(output=path)
        with self.assertRaises(ValueError):
            local.review_local(self.repo, 'bad-ref', self.head, self.root / 'missing',
                               sys.executable, [str(self.stub)], 'fixture')
        self.assertFalse((self.root / 'missing').exists())
        self.assertEqual((self.output / 'precious').read_text(), 'keep')

    def test_invalid_locations_and_false_execution_claims_are_rejected(self):
        target = {'base': self.base, 'head': self.head}
        self.output.mkdir()
        (self.output / 'checks.log').write_text('one real log line\n')
        value = {'status': 'complete', 'scope_summary': 'Read code', 'findings': [],
                 'coverage_gaps': [], 'suggested_checks': []}
        for changes in ({'path': '../outside'}, {'line': 99}, {'priority': True},
                        {'basis': 'executed'}, {'basis': 'executed', 'log_reference': 'checks.log:L9'},
                        {'basis': 'executed', 'log_reference': 'invented.log:L1'}):
            value['findings'] = [self.finding(**changes)]
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                local.validate_review(value, self.repo, target, self.output)
        value['findings'] = [self.finding(basis='executed', log_reference='checks.log:L1')]
        local.validate_review(value, self.repo, target, self.output)


class ReviewProcessTests(unittest.TestCase):
    def test_timeout_and_normal_parent_exit_both_terminate_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for exit_parent in (False, True):
                marker = root / f'leaked-{exit_parent}'
                ready = root / f'ready-{exit_parent}'
                child = f"import time;from pathlib import Path;Path({str(ready)!r}).touch();time.sleep(2);Path({str(marker)!r}).touch()"
                parent = ("import subprocess,sys,time;from pathlib import Path;"
                          f"p=subprocess.Popen([sys.executable,'-c',{child!r}]);"
                          f"\nwhile not Path({str(ready)!r}).exists(): time.sleep(.01)\n"
                          + ('' if exit_parent else 'time.sleep(30)'))
                result = run_step([sys.executable, '-c', parent], root, local.environment(), 1,
                                  root / 'stdout', root / 'stderr')
                self.assertEqual(result['state'], 'finished' if exit_parent else 'timed_out', result)
                self.assertTrue(ready.exists())
                time.sleep(2.1)
                self.assertFalse(marker.exists(), 'descendant survived its job/process group')

    def test_cancellation_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = subprocess.Popen.communicate
            marker = root / 'continued-after-cancel'

            def interrupt_once(process, *args, **kwargs):
                subprocess.Popen.communicate = original
                time.sleep(.1)
                raise KeyboardInterrupt

            with patch.object(subprocess.Popen, 'communicate', interrupt_once):
                script = f"import time;time.sleep(1);from pathlib import Path;Path({str(marker)!r}).touch()"
                result = run_step([sys.executable, '-c', script], root,
                                  local.environment(), 20, root / 'stdout', root / 'stderr')
            self.assertEqual(result['state'], 'cancelled')
            # Windows Job cleanup may report exit 0; cancellation must still be explicit.
            self.assertLess(result['seconds'], 5)
            time.sleep(1.1)
            self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
