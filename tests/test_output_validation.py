"""Tests for the independent output validator.

The point of this validator is that it catches faults a checksum cannot: output
that was written wrongly rather than altered afterwards. So a test that only
confirms "valid output passes" would test almost nothing — the interesting half
is whether corrupted output actually fails.

Cases break requirements from the validator's docstring or the project's
contracts and assert rejection, including faults combined across stages. The
cases come from those declarations, not from reading the recomputation code:
deriving them from the implementation is what let earlier defects through, since
the test then shares the implementation's blind spots.

The fixture is a real `quick` run, generated once per class and copied per test.
That is slower than a synthetic directory but it is the only way to know the
validator agrees with what the runner actually writes; a hand-built fixture
would encode this test's idea of the format rather than the runner's.
"""

from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / ".github" / "scripts" / "validate_benchmark_output.py"
CONFIG = REPO_ROOT / "configs" / "quick.json"
LAZY_CONFIG = REPO_ROOT / "configs" / "p3_lazy_greedy.json"
sys.path.insert(0, str(REPO_ROOT / "src"))

from maxcover.config import load_config  # noqa: E402
from maxcover.contracts import RunRecord  # noqa: E402


def run_validator(output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--config",
            str(CONFIG),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


class OutputValidatorTests(unittest.TestCase):
    """Reject broken contracts, including combinations of independent faults."""

    reference: Path
    _root: tempfile.TemporaryDirectory[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls._root = tempfile.TemporaryDirectory()
        cls.reference = Path(cls._root.name) / "reference"
        completed = subprocess.run(
            [
                sys.executable,
                "run_project.py",
                "benchmark",
                "--config",
                str(CONFIG),
                "--output",
                str(cls.reference),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise AssertionError(f"fixture run failed: {completed.stderr[-2000:]}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._root.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / "output"
        shutil.copytree(self.reference, self.output)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def assertAccepted(self, note: str = "") -> None:
        result = run_validator(self.output)
        self.assertEqual(
            result.returncode,
            0,
            f"validator rejected valid output {note}: {result.stdout[-1500:]}",
        )

    def assertRejected(self, note: str) -> None:
        result = run_validator(self.output)
        self.assertEqual(
            result.returncode,
            1,
            f"validator accepted broken output ({note}); "
            f"stdout: {result.stdout[-800:]}",
        )

    def refreshManifestEntry(self, filename: str) -> None:
        artifact = self.output / filename
        payload = artifact.read_bytes()
        manifest_path = self.output / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["outputs"][filename] = {
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # -- the baseline ----------------------------------------------------

    def test_a_real_run_validates(self) -> None:
        # Without this, every rejection below could come from a broken fixture
        # rather than from the fault the test introduced.
        self.assertAccepted("straight from the runner")

    def test_exit_status_is_usable_as_a_gate(self) -> None:
        # The docstring promises 0 and 1 specifically, because CI depends on it.
        self.assertIn(run_validator(self.output).returncode, (0, 1))

    # -- faults a checksum cannot catch ----------------------------------

    def test_a_wrong_coverage_value_is_rejected(self) -> None:
        # The exact fault the validator exists for: a plausible number that the
        # configuration does not produce. `coverage` is the objective column.
        path = self.output / "raw_results.csv"
        rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
        self.assertTrue(rows)
        for row in rows:
            if row.get("coverage") not in (None, ""):
                row["coverage"] = str(int(row["coverage"]) + 1)
                break
        else:
            self.fail("raw_results.csv has no coverage column")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        self.assertRejected("a coverage value was altered")

    def test_reference_coverage_is_recomputed_after_checksum_refresh(self) -> None:
        path = self.output / "reference_coverage_statistics.csv"
        rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
        target = next(row for row in rows if row["status"] == "feasible")
        denominator = int(target["generated_instance_count"])
        target["status_instance_count"] = "1"
        target["status_rate"] = f"{1 / denominator:.10f}"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        self.refreshManifestEntry(path.name)
        self.assertRejected("reference coverage disagrees with instance statuses")

    def test_reference_missingness_chart_is_recomputed_after_checksum_refresh(self) -> None:
        path = self.output / "reference_coverage_by_case.svg"
        path.write_text(
            path.read_text(encoding="utf-8").replace("缺失 0", "缺失 1", 1),
            encoding="utf-8",
        )
        self.refreshManifestEntry(path.name)
        self.assertRejected("reference missingness chart disagrees with typed statuses")

    def test_a_dropped_run_row_is_rejected(self) -> None:
        path = self.output / "raw_results.csv"
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(lines), 2)
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        self.assertRejected("a result row was removed")

    def test_duplicate_run_identity_is_rejected_without_changing_row_count(self) -> None:
        path = self.output / "raw_results.csv"
        rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
        original_count = len(rows)
        self.assertGreater(original_count, 1)
        self.assertNotEqual(rows[0]["run_id"], rows[-1]["run_id"])
        rows[-1] = dict(rows[0])
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        self.refreshManifestEntry(path.name)
        self.assertEqual(len(list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))), original_count)
        self.assertRejected("duplicate and missing run identities with an unchanged row count")

    def test_invalid_schema_and_output_inventory_are_rejected_together(self) -> None:
        path = self.output / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["schema_version"] += 99
        manifest["outputs"] = []
        path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertRejected("invalid schema and untrusted output inventory")

    def test_headline_and_chart_tampering_is_rejected_after_checksum_refresh(self) -> None:
        report = self.output / "results_summary.md"
        text = report.read_text(encoding="utf-8")
        self.assertIn("## Headline checks", text)
        report.write_text(text.replace("## Headline checks", "## Broken headline checks", 1), encoding="utf-8")
        chart = self.output / "runtime_scaling.svg"
        chart.write_text(chart.read_text(encoding="utf-8") + "\n<!-- tampered -->\n", encoding="utf-8")
        self.refreshManifestEntry(report.name)
        self.refreshManifestEntry(chart.name)
        self.assertRejected("both the checked report section and a canonical chart differ")

    def test_a_wrong_schema_version_is_rejected(self) -> None:
        # Schema versions are contracts; a CSV claiming the wrong one is exactly
        # the case a checksum agrees with.
        path = self.output / "manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "schema_version" not in payload:
            self.skipTest("manifest carries no schema_version")
        payload["schema_version"] = int(payload["schema_version"]) + 99
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.assertRejected("the manifest schema version was changed")

    def test_a_missing_artifact_is_rejected(self) -> None:
        (self.output / "raw_results.csv").unlink()
        self.assertRejected("raw_results.csv was deleted")

    def test_a_missing_manifest_is_rejected(self) -> None:
        (self.output / "manifest.json").unlink()
        self.assertRejected("manifest.json was deleted")

    def test_an_empty_output_directory_is_rejected(self) -> None:
        for child in sorted(self.output.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
        self.assertRejected("every artifact was removed")

    def test_a_truncated_csv_is_rejected(self) -> None:
        (self.output / "raw_results.csv").write_text("", encoding="utf-8")
        self.assertRejected("raw_results.csv was emptied")

    def test_a_corrupt_manifest_is_rejected(self) -> None:
        (self.output / "manifest.json").write_text("{ not json", encoding="utf-8")
        self.assertRejected("manifest.json is not parseable")

    def test_a_mismatched_config_hash_is_rejected(self) -> None:
        # Output produced by a different configuration must not validate against
        # this one, or the check says nothing about which config it belongs to.
        # The hash lives under `configuration`, not at the top level.
        path = self.output / "manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        configuration = payload.get("configuration")
        self.assertIsInstance(configuration, dict)
        assert isinstance(configuration, dict)
        digest = configuration["config_hash"]
        configuration["config_hash"] = ("0" if digest[0] != "0" else "1") + digest[1:]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.assertRejected("the recorded config hash was altered")

    def test_a_nonexistent_output_directory_is_rejected(self) -> None:
        self.output = self.output.parent / "does-not-exist"
        self.assertRejected("the output directory does not exist")

    def test_the_expected_schema_version_matches_what_the_runner_writes(self) -> None:
        # The validator declares MANIFEST_SCHEMA_VERSION itself, because
        # the runner writes the value inline and exposes no constant. That
        # duplication is only safe while the two agree, so this compares the
        # validator's expectation against a manifest the runner actually wrote.
        # A future bump then fails here rather than making every run invalid.
        import importlib.util

        spec = importlib.util.spec_from_file_location("_validator", VALIDATOR)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["_validator"] = module
        spec.loader.exec_module(module)

        written = json.loads(
            (self.output / "manifest.json").read_text(encoding="utf-8")
        )["schema_version"]
        self.assertEqual(
            module.MANIFEST_SCHEMA_VERSION,
            written,
            "the validator expects a different manifest schema version than the "
            "runner writes; update MANIFEST_SCHEMA_VERSION in the validator",
        )


class LazyGreedyValidatorTests(unittest.TestCase):
    """Reverse-verify the independently recomputed Lazy Greedy facts."""

    config = None
    rows: list[RunRecord] = []
    validator = None
    _root: tempfile.TemporaryDirectory[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls._root = tempfile.TemporaryDirectory()
        output = Path(cls._root.name) / "output"
        completed = subprocess.run(
            [
                sys.executable,
                "run_project.py",
                "benchmark",
                "--config",
                str(LAZY_CONFIG),
                "--output",
                str(output),
                "--workers",
                "2",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise AssertionError(f"lazy fixture run failed: {completed.stderr[-2000:]}")

        cls.config = load_config(LAZY_CONFIG)
        with (output / "raw_results.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            cls.rows = [RunRecord.from_csv_row(row) for row in csv.DictReader(handle)]

        spec = importlib.util.spec_from_file_location(
            "lazy_validator_under_test", VALIDATOR
        )
        assert spec is not None and spec.loader is not None
        cls.validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.validator)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._root.cleanup()

    def test_a_valid_lazy_fixture_is_accepted(self) -> None:
        assert self.config is not None
        assert self.validator is not None
        self.validator._validate_lazy_greedy_rows(self.config, list(self.rows))

    def test_coverage_must_match_the_selected_sets(self) -> None:
        assert self.config is not None
        assert self.validator is not None
        mutated: list[RunRecord] = []
        for row in self.rows:
            if row.algorithm in {"greedy", "lazy_greedy"}:
                self.assertIsNotNone(row.optimum)
                assert row.optimum is not None
                mutated.append(
                    replace(
                        row,
                        coverage=0,
                        optimality_gap=(
                            None
                            if row.optimum == 0
                            else row.optimum / row.optimum
                        ),
                    )
                )
            else:
                mutated.append(row)

        with self.assertRaisesRegex(ValueError, "coverage does not match"):
            self.validator._validate_lazy_greedy_rows(self.config, mutated)

    def test_heap_counters_must_match_an_independent_replay(self) -> None:
        assert self.config is not None
        assert self.validator is not None
        mutated: list[RunRecord] = []
        for row in self.rows:
            if row.algorithm != "lazy_greedy":
                mutated.append(row)
                continue
            metadata = json.loads(row.algorithm_metadata)
            search = metadata["search"]
            search["priority_queue_pops"] += 1
            search["marginal_evaluations"] += 1
            metadata["trajectory"][-1]["marginal_evaluations"] += 1
            mutated.append(
                replace(
                    row,
                    nodes_or_iterations=row.nodes_or_iterations + 1,
                    algorithm_metadata=json.dumps(
                        metadata, sort_keys=True, separators=(",", ":")
                    ),
                )
            )

        with self.assertRaisesRegex(ValueError, "independent heap replay"):
            self.validator._validate_lazy_greedy_rows(self.config, mutated)


if __name__ == "__main__":
    unittest.main()
