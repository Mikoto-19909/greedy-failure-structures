"""Exercise static preparation against disposable Git histories, not research data."""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_review as review


class PrepareReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'source'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Prepare fixture')
        self.git('config', 'user.email', 'prepare@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'core.autocrlf', 'false')
        self.write('src/pkg/contract.py', 'LIMIT = 10\n')
        self.write('src/pkg/facade.py', 'from .contract import LIMIT\n')
        self.write('src/pkg/old.py', 'from .facade import LIMIT\ndef f(x):\n    return min(x, LIMIT)\n')
        self.write('src/pkg/caller.py', 'from .old import f\nanswer = f(1)\n')
        self.write('tests/test_call.py', 'import unittest\nfrom pkg.old import f\n'
                   'class CallTests(unittest.TestCase):\n'
                   '    def test_valid(self):\n        self.assertEqual(f(1), 1)\n'
                   '    def test_invalid(self):\n        self.assertRaises(TypeError, f, None)\n')
        self.write('tests/test_exports.py', 'import unittest\nfrom pkg import old\n'
                   'class ExportTests(unittest.TestCase):\n'
                   '    def test_export(self):\n        self.assertTrue(hasattr(old, "f"))\n')
        self.write('CONTRIBUTING.md', 'Use unittest after preparing dependencies.\n')
        self.base = self.commit('base')
        self.write('src/pkg/new.py', 'from .facade import LIMIT\ndef f(x):\n    return min(x, LIMIT)\n')
        self.write('src/pkg/old.py', 'from .new import f\n')
        self.head = self.commit('move')
        self.output = self.root / 'review'

    def git(self, *args):
        return review.git(self.repo, *args).decode('utf-8').strip()

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def prepare(self, base=None, head=None, output=None):
        return review.prepare(self.repo, base or self.base, head or self.head, output or self.output)

    def test_fixed_snapshot_callers_leaf_contract_tests_and_links(self):
        self.write('src/pkg/new.py', 'UNCOMMITTED = True\n')
        status = self.git('status', '--porcelain')
        index_path = Path(self.git('rev-parse', '--path-format=absolute', '--git-path', 'index'))
        index = index_path.read_bytes()
        report = self.prepare().read_text(encoding='utf-8')
        self.assertIn(self.base, report)
        self.assertIn(self.head, report)
        self.assertIn('src/pkg/caller.py', report)
        self.assertIn('head: src/pkg/contract.py', report)
        self.assertIn('test_call.CallTests.test_valid', report)
        self.assertIn('test_call.CallTests.test_invalid', report)
        self.assertIn('test_exports.ExportTests.test_export', report)
        snapshots = b'\n'.join(p.read_bytes() for p in (self.output / 'snapshot').iterdir())
        self.assertNotIn(b'UNCOMMITTED', snapshots)
        self.assertIn(b'LIMIT = 10', snapshots)
        for link in re.findall(r'\]\(([^)]+)\)', report):
            self.assertTrue((self.output / link).is_file(), link)
        self.assertEqual(self.git('status', '--porcelain'), status)
        self.assertEqual(index_path.read_bytes(), index)

    def test_equal_revisions_emit_empty_patch(self):
        self.prepare(head=self.base)
        self.assertEqual((self.output / 'diff.patch').read_bytes(), b'')

    def test_subdirectory_and_relative_config_preserve_whole_repository_package(self):
        self.write('README.md', 'A change outside src.\n')
        head = self.commit('root document')
        expected = self.prepare(head=head)
        expected_report = expected.read_bytes()
        expected_patch = (self.output / 'diff.patch').read_bytes()
        for setting in ('false', 'true'):
            with self.subTest(relative=setting):
                self.git('config', 'diff.relative', setting)
                output = self.root / f'from-subdirectory-{setting}'
                actual = review.prepare(self.repo / 'src', self.base, head, output)
                self.assertEqual(actual.read_bytes(), expected_report)
                self.assertEqual((output / 'diff.patch').read_bytes(), expected_patch)

    def test_submodule_log_config_still_emits_a_gitlink_patch(self):
        self.git('update-index', '--add', '--cacheinfo', f'160000,{self.base},vendor')
        self.git('commit', '-qm', 'old gitlink')
        base = self.git('rev-parse', 'HEAD')
        self.git('update-index', '--cacheinfo', f'160000,{self.head},vendor')
        self.git('commit', '-qm', 'new gitlink')
        head = self.git('rev-parse', 'HEAD')
        self.git('config', 'diff.submodule', 'log')
        self.prepare(base=base, head=head)
        raw = (self.output / 'diff.patch').read_bytes()
        self.assertIn(f'-Subproject commit {self.base}'.encode(), raw)
        self.assertIn(f'+Subproject commit {self.head}'.encode(), raw)
        self.assertIn('vendor', self.git('apply', '--stat', str(self.output / 'diff.patch')))

    def test_bare_repository_retains_committed_snapshots(self):
        bare = self.root / 'bare.git'
        subprocess.run(['git', 'clone', '-q', '--bare', str(self.repo), str(bare)],
                       check=True, capture_output=True)
        expected = self.prepare().read_bytes()
        actual = review.prepare(bare, self.base, self.head, self.root / 'bare-output')
        self.assertEqual(actual.read_bytes(), expected)

    def test_advanced_base_uses_common_ancestor(self):
        original_tree = self.git('rev-parse', f'{self.base}^{{tree}}')
        advanced = self.git('commit-tree', original_tree, '-p', self.base, '-m', 'advanced base')
        report = self.prepare(base=advanced).read_text(encoding='utf-8')
        self.assertIn(f'Actual diff start (unique merge-base): `{self.base}`', report)
        self.assertIn(advanced, report)

    def test_invalid_revisions_no_common_and_multiple_ancestors_leave_no_output(self):
        for revision in ('missing-ref', '--help', 'HEAD:src/pkg/new.py'):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                self.prepare(base=revision)
            self.assertFalse(self.output.exists())
        tree = self.git('rev-parse', 'HEAD^{tree}')
        orphan = self.git('commit-tree', tree, '-m', 'orphan')
        with self.assertRaises(ValueError):
            self.prepare(base=orphan)
        left = self.git('commit-tree', tree, '-p', self.base, '-m', 'left')
        right = self.git('commit-tree', tree, '-p', self.base, '-m', 'right')
        merge1 = self.git('commit-tree', tree, '-p', left, '-p', right, '-m', 'merge1')
        merge2 = self.git('commit-tree', tree, '-p', right, '-p', left, '-m', 'merge2')
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.prepare(base=merge1, head=merge2)
        self.assertFalse(self.output.exists())

    def test_shallow_clone_rejected(self):
        shallow = self.root / 'shallow'
        # The tool itself never enables a transport; fixture creation is explicit.
        subprocess.run(['git', '-c', 'protocol.file.allow=always', 'clone', '-q',
                        '--depth=1', self.repo.as_uri(), str(shallow)], check=True, capture_output=True)
        with self.assertRaisesRegex(ValueError, 'shallow'):
            review.prepare(shallow, 'HEAD', 'HEAD', self.output)
        self.assertFalse(self.output.exists())

    def test_existing_outputs_source_worktree_and_git_dir_rejected(self):
        existing = self.root / 'existing'
        existing.mkdir()
        (existing / 'precious').write_text('keep')
        self.output.write_text('keep file')
        linked = self.root / 'linked'
        self.git('worktree', 'add', '--detach', str(linked), self.head)
        self.addCleanup(lambda: self.git('worktree', 'remove', '--force', str(linked)))
        for target in (existing, self.output, self.repo / 'out', linked / 'out', self.repo / '.git/out'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.prepare(output=target)
        self.assertEqual((existing / 'precious').read_text(), 'keep')
        self.assertEqual(self.output.read_text(), 'keep file')

    def test_linked_output_parent_resolves_to_source(self):
        alias = self.root / 'alias'
        if os.name == 'nt':
            # Native junctions need no administrator privilege. This helper only
            # creates the junction; deletion stays in Python, without recursion.
            import _winapi
            _winapi.CreateJunction(str(self.repo), str(alias))
            self.addCleanup(alias.rmdir)
        else:
            alias.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.prepare(output=alias / 'out')
        self.assertFalse((self.repo / 'out').exists())

    def test_rename_delete_binary_and_symlink_are_not_executed_or_materialized(self):
        self.git('mv', 'src/pkg/caller.py', 'src/pkg/调用 caller.py')
        self.git('rm', 'src/pkg/contract.py')
        (self.repo / 'data.bin').write_bytes(b'\0\1\xff')
        # A symlink in the Git tree, without asking Windows to create one.
        self.write('target.txt', '../outside\n')
        oid = self.git('hash-object', 'target.txt')
        self.git('add', '.')
        self.git('update-index', '--add', '--cacheinfo', f'120000,{oid},link.py')
        self.git('commit', '-qm', 'file types')
        head = self.git('rev-parse', 'HEAD')
        report = self.prepare(head=head).read_text(encoding='utf-8')
        raw = (self.output / 'diff.patch').read_bytes()
        self.assertIn('R100', report)
        self.assertIn('调用 caller.py', report)
        self.assertIn('120000', report)
        self.assertIn(b'GIT binary patch', raw)
        self.assertIn(b'deleted file mode', raw)
        self.assertFalse(any(p.is_symlink() for p in self.output.rglob('*')))
        self.assertFalse((self.output / 'link.py').exists())

    def test_import_diff_textconv_hooks_and_git_environment_have_no_side_effects(self):
        marker = self.root / 'executed'
        payload = f'from pathlib import Path\nPath({str(marker)!r}).write_text("BAD")\n'
        self.write('src/pkg/new.py', payload + 'def f(x):\n    return x\n')
        self.write('tests/test_evil.py', payload + 'def test_f():\n    assert f(1) == 1\n')
        self.write('.gitattributes', '*.py diff=marker\n')
        head = self.commit('side effects')
        external = self.root / 'external.py'
        external.write_text(payload, encoding='utf-8')
        command = f'"{sys.executable}" "{external}"'
        self.git('config', 'diff.marker.command', command)
        self.git('config', 'diff.marker.textconv', command)
        self.git('config', 'core.fsmonitor', command)
        with patch.dict(os.environ, {'GIT_EXTERNAL_DIFF': command, 'GIT_DIR': str(self.root / 'missing')}):
            self.prepare(head=head)
        self.assertFalse(marker.exists())

    def test_snapshot_limits_and_parse_failures_are_explicit(self):
        self.write('src/pkg/broken.py', 'def broken(:\n')
        self.write('src/pkg/large.py', 'x = 1\n' * 20)
        head = self.commit('limits')
        with patch.object(review, 'MAX_FILE_BYTES', 100), patch.object(review, 'MAX_SNAPSHOTS', 2):
            report = self.prepare(head=head).read_text(encoding='utf-8')
        self.assertLessEqual(len(list((self.output / 'snapshot').iterdir())), 2)
        self.assertIn('SyntaxError', report)
        self.assertIn('snapshot omitted', report)
        self.assertIn('snapshot limit', report)

    def test_cli_reports_failure_without_success_artifact(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_review.py'),
                                 '--repo', str(self.repo), '--base', 'bad-ref', '--head', self.head,
                                 '--output', str(self.output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Preparation failed', result.stderr)
        self.assertNotIn('Prepared static review', result.stdout)
        self.assertFalse(self.output.exists())

    def test_failed_report_write_never_leaves_completion_report(self):
        original = Path.write_text

        def failing_write(path, *args, **kwargs):
            if path.name == 'review.md.partial':
                original(path, 'interrupted report', encoding='utf-8')
                raise OSError('simulated disk failure')
            return original(path, *args, **kwargs)

        with patch.object(Path, 'write_text', failing_write), self.assertRaises(OSError):
            self.prepare()
        self.assertTrue((self.output / 'diff.patch').exists())
        self.assertFalse((self.output / 'review.md').exists())

    def test_new_cases_are_selected_by_existing_core_profile(self):
        import check
        cases = list(unittest.defaultTestLoader.loadTestsFromTestCase(type(self)))
        self.assertEqual(check.selected(cases, 'core'), cases)


if __name__ == '__main__':
    unittest.main()
