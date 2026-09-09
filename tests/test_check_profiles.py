"""Selection must preserve new tests and reject missing scientific coverage."""
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import check
from check_profiles import ANALYSIS_OWNERS, GROUPS, RESEARCH_MODULES, REQUIRED_RESEARCH, OPTIONAL_CASES, affected_groups, extended_group

class NamedCase:
    def __init__(self, name): self.name = name
    def id(self): return self.name

class CheckProfilesTests(unittest.TestCase):
    def test_reference_restore_preserves_existing_files_and_rejects_missing_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            git('init', '-q')
            git('config', 'core.autocrlf', 'false')
            git('config', 'user.name', 'Config fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            original = {name: f'{{"fixture": {index}}}\n'.encode()
                        for index, name in enumerate(check.REFERENCE_CONFIG_PATHS)}
            for name, data in original.items():
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes(data)
            git('add', '--', *original)
            git('commit', '-qm', 'Store frozen fixture inputs')
            revision = git('rev-parse', 'HEAD')
            git('rm', '--', *original)
            (root / '.gitignore').write_text('\n'.join(original) + '\n', encoding='utf-8')
            git('add', '.gitignore')
            git('commit', '-qm', 'Keep inputs outside the source tree')
            with patch.object(check, 'REFERENCE_CONFIG_REVISION', revision):
                self.assertEqual(check.restore_reference_configs(root), list(original))
                for name, data in original.items():
                    self.assertEqual((root / name).read_bytes(), data)
                self.assertEqual(git('status', '--porcelain'), '')
                first, second = [root / name for name in original]
                first.write_bytes(b'locally modified; must not be overwritten\n')
                second.unlink()
                self.assertEqual(check.restore_reference_configs(root), [check.REFERENCE_CONFIG_PATHS[1]])
                self.assertEqual(first.read_bytes(), b'locally modified; must not be overwritten\n')
                self.assertEqual(check.restore_reference_configs(root), [])
                second.unlink()
                with patch.object(check, 'REFERENCE_CONFIG_REVISION', '0' * 40):
                    with self.assertRaisesRegex(ValueError, 'complete clone'):
                        check.restore_reference_configs(root)
                self.assertFalse(second.exists())
                self.assertEqual(first.read_bytes(), b'locally modified; must not be overwritten\n')
                self.assertEqual(git('status', '--porcelain'), '')

    def test_new_research_tests_enter_core_without_allowlisting(self):
        for module in ('test_r4', 'test_cartography', 'test_cli_e2e', 'test_fault_injection'):
            case = NamedCase(f'{module}.FutureTests.test_dual_rejection')
            self.assertIsNone(extended_group(case.id()))
            self.assertEqual(check.selected([case], 'core'), [case])

    def test_full_retains_every_case_and_affected_groups_promote_extensions(self):
        cases = [NamedCase('test_fault_injection.FaultInjectionGateTests.test_gap_tamper_is_rejected'), NamedCase('test_new.T.test_x')]
        self.assertEqual(check.selected(cases, 'full'), cases)
        self.assertEqual(check.selected(cases, 'core'), cases[1:])
        self.assertEqual(check.selected(cases, 'core', {'artifacts'}), cases)

    def test_dependency_fallback_and_changed_extension(self):
        self.assertEqual(affected_groups(['src/maxcover/model.py']), GROUPS)
        self.assertIn('cartography', affected_groups(['tests/test_cartography.py']))
        self.assertIn('generators', affected_groups(['src/maxcover/_generators_random.py']))
        self.assertEqual(affected_groups(['analysis/r1c_confirmation.py']), set())

    def test_missing_research_registration_and_missing_tests_fail(self):
        cases = [NamedCase(name) for names in REQUIRED_RESEARCH.values() for name in names]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'analysis').mkdir()
            for filename in ANALYSIS_OWNERS:
                (root / 'analysis' / filename).touch()
            check.validate_research_registration(root, cases)
            with self.assertRaises(ValueError):
                check.validate_research_registration(root, [])
            with self.assertRaisesRegex(ValueError, 'required verification'):
                check.validate_research_registration(root, cases[1:])
            (root / 'analysis/r4.py').touch()
            with self.assertRaisesRegex(ValueError, 'ownership'):
                check.validate_research_registration(root, cases)

    def test_missing_ci_event_falls_back_to_every_extension(self):
        with patch.dict('os.environ', {'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_EVENT_PATH': 'missing-event'}):
            self.assertEqual(check.ci_groups(), GROUPS)

    def test_optional_targets_cannot_disappear(self):
        cases = [NamedCase(name) for name in sorted(OPTIONAL_CASES)]
        check.validate_optional(cases)
        for missing in range(len(cases)):
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                check.validate_optional(cases[:missing] + cases[missing+1:])

    def test_class_skip_method_skip_and_expected_failure_are_not_success(self):
        class ClassSkip(unittest.TestCase):
            @classmethod
            def setUpClass(cls): raise unittest.SkipTest('missing prerequisite')
            def test_required(self): pass
        class MethodSkip(unittest.TestCase):
            def test_required(self): self.skipTest('missing prerequisite')
        class ExpectedFailure(unittest.TestCase):
            @unittest.expectedFailure
            def test_required(self): self.fail('verification did not pass')
        for cls in (ClassSkip, MethodSkip, ExpectedFailure):
            case = cls('test_required')
            result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=check.ExecutionResult).run(unittest.TestSuite([case]))
            with self.subTest(case=cls.__name__):
                self.assertFalse(check.execution_succeeded(result, {case.id()}))
