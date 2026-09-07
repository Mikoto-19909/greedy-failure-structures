"""Evidence persistence is checked against disposable local Git remotes."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import freeze_evidence as freeze

class FreezeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        freeze.git(self.source, 'init', '-q')
        freeze.git(self.source, 'config', 'user.name', 'Evidence test')
        freeze.git(self.source, 'config', 'user.email', 'evidence@example.invalid')
        freeze.git(self.source, 'config', 'commit.gpgsign', 'false')
        (self.source / 'design.json').write_text('{"seed": 17}', encoding='utf-8')
        freeze.git(self.source, 'add', 'design.json')
        freeze.git(self.source, 'commit', '-qm', 'Fixture design')
        (self.source / 'results').mkdir()
        (self.source / 'results/raw.csv').write_text('coverage\n7\n', encoding='utf-8')
        self.snapshot = self.root / 'prepared'
        self.remote = self.root / 'remote.git'
        self.remote.mkdir()
        freeze.git(self.remote, 'init', '--bare', '-q')

    def prepare(self, batch='test'):
        return freeze.prepare(self.source, self.snapshot, batch,
                              ['design.json', 'results/raw.csv'], 'Synthetic fixture; no research claim.')

    def test_actual_evidence_is_pushed_read_back_and_retry_is_idempotent(self):
        commit = self.prepare()
        self.assertEqual(freeze.publish(self.snapshot, str(self.remote)), commit)
        self.assertEqual(freeze.publish(self.snapshot, str(self.remote)), commit)
        self.assertEqual(freeze.git(self.remote, 'show', f'{commit}:results/raw.csv'), 'coverage\n7')
        with self.assertRaises(ValueError):
            self.prepare()

    def test_existing_batch_cannot_be_replaced(self):
        self.prepare()
        freeze.publish(self.snapshot, str(self.remote))
        (self.source / 'results/raw.csv').write_text('coverage\n8\n', encoding='utf-8')
        other = self.root / 'other'
        freeze.prepare(self.source, other, 'test', ['results/raw.csv'], 'Different evidence')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            freeze.publish(other, str(self.remote))

    def test_upload_failure_preserves_snapshot_for_retry(self):
        commit = self.prepare()
        with self.assertRaises(subprocess.CalledProcessError):
            freeze.publish(self.snapshot, str(self.root / 'absent.git'))
        self.assertEqual(freeze.git(self.snapshot, 'rev-parse', 'HEAD'), commit)
        self.assertEqual(freeze.publish(self.snapshot, str(self.remote)), commit)

    def test_invalid_paths_large_files_and_dirty_source_are_rejected(self):
        (self.source / 'freeze.md').write_text('IRREPLACEABLE RAW EVIDENCE', encoding='utf-8')
        for files in (['../outside'], ['.git/config'], ['.GIT/config'], ['design.json', 'design.json'], ['freeze.md']):
            with self.subTest(files=files), self.assertRaises(ValueError):
                freeze.prepare(self.source, self.snapshot, 'test', files, 'fixture')
        self.assertEqual((self.source / 'freeze.md').read_text(encoding='utf-8'), 'IRREPLACEABLE RAW EVIDENCE')
        with patch.object(freeze, 'MAX_FILE_BYTES', 1), self.assertRaises(ValueError):
            self.prepare()
        (self.source / 'design.json').write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'commit intended source'):
            self.prepare()
        self.assertFalse(self.snapshot.exists())

    def test_modified_prepared_payload_is_not_published(self):
        self.prepare()
        (self.snapshot / 'results/raw.csv').write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'modified'):
            freeze.publish(self.snapshot, str(self.remote))
