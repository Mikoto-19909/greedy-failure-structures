"""Exercise the independent R1 verifier on saved evidence and corrupted copies."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'analysis'), str(ROOT / 'src')]
import greedy_failure_paths as producer
import validate_greedy_failure_paths as verifier

class ResearchVerificationTests(unittest.TestCase):
    def test_saved_r1_evidence_recomputes_without_producer(self):
        with patch.object(producer, 'analyze_instance', side_effect=AssertionError('producer must not be used')):
            self.assertEqual(verifier.validate(ROOT / 'analysis/r1_prefix_exchange_design.json', ROOT / 'experiments/r1_prefix_exchange_v1'), 66)

    def test_false_r1_optimum_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'evidence'
            shutil.copytree(ROOT / 'experiments/r1_prefix_exchange_v1', output)
            path = output / 'paths.jsonl'
            rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            rows[0]['optimum'] += 1
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
            with self.assertRaises(ValueError):
                verifier.validate(ROOT / 'analysis/r1_prefix_exchange_design.json', output)
