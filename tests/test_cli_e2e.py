"""End-to-end tests for the public CLI through real Python processes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CliEndToEndTests(unittest.TestCase):
    """Exercise every public command without importing project modules."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "checkout"
        self.workspace.mkdir()
        shutil.copy2(ROOT / "run_project.py", self.workspace / "run_project.py")
        shutil.copytree(ROOT / "src", self.workspace / "src")
        shutil.copytree(ROOT / "configs", self.workspace / "configs")
        self.environment = os.environ.copy()
        self.environment["PYTHONUTF8"] = "1"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.workspace / "run_project.py"), *arguments],
            cwd=self.workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=self.environment,
            check=False,
            timeout=120,
        )

    def _assert_success(self, completed: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")

    def test_default_quick_explicit_quick_and_demo(self) -> None:
        default_quick = self._run()
        self.assertEqual(default_quick.returncode, 0, default_quick.stderr)
        self.assertIn("LegacyConfigWarning", default_quick.stderr)
        self.assertNotIn("Traceback", default_quick.stderr)
        self.assertIn("Completed 48 algorithm runs.", default_quick.stdout)

        explicit_quick = self._run("quick")
        self.assertEqual(explicit_quick.returncode, 0, explicit_quick.stderr)
        self.assertIn("LegacyConfigWarning", explicit_quick.stderr)
        self.assertNotIn("Traceback", explicit_quick.stderr)
        self.assertIn("Completed 48 algorithm runs.", explicit_quick.stdout)
        manifest = json.loads(
            (self.workspace / "results" / "quick" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["execution"]["resumed_runs"], 48)

        demo = self._run("demo")
        self._assert_success(demo)
        self.assertIn("Adversarial greedy-trap demonstration", demo.stdout)
        self.assertIn("branch_and_bound", demo.stdout)

        audit = self._run(
            "audit-stressors",
            "--config",
            str(self.workspace / "configs" / "p4_long_tail.json"),
            "--strict",
        )
        self._assert_success(audit)
        audit_report = json.loads(audit.stdout)
        self.assertEqual(audit_report["schema_version"], 1)
        self.assertEqual(len(audit_report["scans"]), 1)
        self.assertEqual(audit_report["scans"][0]["assessment"], "pass")

        controlled_audit = self._run("audit-stressors", "--strict")
        self._assert_success(controlled_audit)
        controlled_report = json.loads(controlled_audit.stdout)
        self.assertEqual(len(controlled_report["scans"]), 6)
        self.assertTrue(
            all(
                scan["assessment"] == "pass"
                for scan in controlled_report["scans"]
            )
        )

    def test_config_to_summary_checkpoint_lifecycle(self) -> None:
        config_path = self.workspace / "e2e.json"
        output_dir = self.workspace / "output"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "name": "CLI end-to-end fixture",
                    "base_seed": 37,
                    "repetitions": 2,
                    "algorithms": [{"name": "greedy"}],
                    "cases": [
                        {
                            "name": "small_uniform",
                            "family": "uniform",
                            "universe_size": 8,
                            "set_count": 4,
                            "k": 2,
                            "density": 0.25,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        validation = self._run("validate-config", "--config", str(config_path))
        self._assert_success(validation)
        self.assertIn("Configuration is valid", validation.stdout)
        self.assertIn("Algorithm runs: 2", validation.stdout)
        self.assertFalse(output_dir.exists())

        dry_run = self._run(
            "benchmark", "--config", str(config_path), "--dry-run"
        )
        self._assert_success(dry_run)
        self.assertIn("Algorithm runs: 2", dry_run.stdout)
        self.assertFalse(output_dir.exists())

        fresh = self._run(
            "benchmark",
            "--config",
            str(config_path),
            "--output",
            str(output_dir),
            "--workers",
            "2",
        )
        self._assert_success(fresh)
        self.assertIn("Completed 2 algorithm runs.", fresh.stdout)
        raw_results = output_dir / "raw_results.csv"
        instances = output_dir / "instances.csv"
        self.assertTrue(raw_results.is_file())
        self.assertTrue(instances.is_file())
        self.assertTrue((output_dir / "manifest.json").is_file())

        resumed = self._run(
            "resume",
            "--config",
            str(config_path),
            "--output",
            str(output_dir),
        )
        self._assert_success(resumed)
        resume_manifest = json.loads(
            (output_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(resume_manifest["execution"]["resumed_runs"], 2)

        raw_digest = hashlib.sha256(raw_results.read_bytes()).hexdigest()
        report_path = output_dir / "results_summary.md"
        report_path.write_text("stale report\n", encoding="utf-8")
        summarized = self._run(
            "summarize",
            "--config",
            str(config_path),
            "--output",
            str(output_dir),
        )
        self._assert_success(summarized)
        self.assertIn(
            "Summary rebuilt from canonical benchmark artifacts", summarized.stdout
        )
        self.assertEqual(
            hashlib.sha256(raw_results.read_bytes()).hexdigest(), raw_digest
        )
        self.assertNotEqual(report_path.read_text(encoding="utf-8"), "stale report\n")

    def test_replay_uses_a_serialized_instance_end_to_end(self) -> None:
        instance_path = self.workspace / "replay.json"
        instance_path.write_text(
            json.dumps(
                {
                    "instance": {
                        "schema_version": 1,
                        "encoding": "elements",
                        "universe_size": 3,
                        "sets": [[0, 1], [1, 2]],
                        "k": 1,
                        "family": "e2e",
                        "seed": 11,
                        "parameters": {},
                    },
                    "replay": {
                        "algorithm": "greedy",
                        "options": {},
                        "expected": {"coverage": 2, "selected": [0]},
                    },
                }
            ),
            encoding="utf-8",
        )

        replay = self._run("replay", "--instance", str(instance_path))
        self._assert_success(replay)
        self.assertIn("greedy: status=feasible coverage=2 selected=(0,)", replay.stdout)
        self.assertIn("Replay matches recorded coverage and selection.", replay.stdout)

    def test_replay_rejects_oversized_input_without_echoing_payload(self) -> None:
        instance_path = self.workspace / "oversized-replay.json"
        instance_path.write_text(
            json.dumps(
                {
                    "instance": {
                        "schema_version": 1,
                        "encoding": "elements",
                        "universe_size": 3,
                        "sets": [[0, 1]],
                        "k": 1,
                        "family": "e2e",
                        "seed": 11,
                        "parameters": {},
                    },
                    "replay": {"algorithm": "greedy", "options": {}},
                    "payload_marker": "PAYLOAD_MARKER" + "x" * (1024 * 1024),
                }
            ),
            encoding="utf-8",
        )

        replay = self._run("replay", "--instance", str(instance_path))

        self.assertNotEqual(replay.returncode, 0)
        self.assertIn(
            "instance file exceeds the supported resource limit", replay.stderr
        )
        self.assertNotIn("PAYLOAD_MARKER", replay.stderr)


if __name__ == "__main__":
    unittest.main()
