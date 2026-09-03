"""Tests for the reproducibility matrix compare script.

The declaration-plus-code rule in AGENTS.md applies here directly: the compare
script is the enforcement half of docs/reproducibility_matrix.md, and the
interesting tests are the ones that break one specific declaration-made claim
and require the script to notice.

Each case therefore comes from the declaration, not from reading the compare
implementation: a coverage digit change, a selected-sequence change, a row
order reversal, an instance identity tamper, a manifest identity type change
(bit-exact covers the serialised JSON type, not only the Python value), and
the two declared exemptions (runtime variation for every row, and incumbent
variation for a timeout row) must pass without a false positive.

The fixture is a real quick run, generated once per class and copied per test,
following the pattern of test_output_validation.py: a hand-built fixture would
encode this test's idea of the format rather than the runner's.
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPARE = REPO_ROOT / ".github" / "scripts" / "compare_matrix_outputs.py"
CONFIG = REPO_ROOT / "configs" / "quick.json"
sys.path.insert(0, str(REPO_ROOT / "src"))

from maxcover.contracts import RunRecord  # noqa: E402


def run_compare(*directories: Path) -> subprocess.CompletedProcess[str]:
    arguments = [sys.executable, str(COMPARE)]
    for directory in directories:
        arguments += ["--result", str(directory)]
    return subprocess.run(
        arguments,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _format_gap(coverage: int, optimum: int) -> str:
    return f"{(optimum - coverage) / optimum:.10f}"


class CompareMatrixOutputsTests(unittest.TestCase):
    """Break one declared guarantee per test and require the compare to notice."""

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
                "--workers",
                "1",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"fixture run failed: {completed.stderr[-2000:]}"
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._root.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.baseline = Path(self._tmp.name) / "baseline"
        self.variant = Path(self._tmp.name) / "variant"
        shutil.copytree(self.reference, self.baseline)
        shutil.copytree(self.reference, self.variant)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def mutate_rows(
        self,
        path: Path,
        transform: Callable[[list[dict[str, str]]], None],
    ) -> list[dict[str, str]]:
        rows = read_rows(path)
        transform(rows)
        write_rows(path, rows)
        return rows

    def assertAccepted(self, note: str = "") -> subprocess.CompletedProcess[str]:
        result = run_compare(self.baseline, self.variant)
        self.assertEqual(
            result.returncode,
            0,
            f"compare rejected declared-equal results {note}: {result.stdout[-1500:]}",
        )
        return result

    def assertRejected(
        self, field_substring: str, note: str
    ) -> subprocess.CompletedProcess[str]:
        result = run_compare(self.baseline, self.variant)
        self.assertEqual(
            result.returncode,
            1,
            f"compare accepted {note}: {result.stdout[-1500:]}",
        )
        self.assertIn(
            f"{field_substring}: inconsistent",
            result.stdout,
            f"report did not flag {field_substring} for {note}",
        )
        return result

    @staticmethod
    def _greedy_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return [
            row
            for row in rows
            if row["algorithm"] == "greedy" and row["status"] == "feasible"
        ]

    def test_identical_copy_reproduces(self) -> None:
        result = self.assertAccepted("on an untouched copy")
        self.assertIn("matrix comparison: CONSISTENT", result.stdout)
        self.assertIn("raw_results.instance_id: consistent", result.stdout)

    def test_coverage_tamper_is_detected(self) -> None:
        tampered: dict[str, str] = {}

        def transform(rows: list[dict[str, str]]) -> None:
            candidates = self._greedy_rows(rows)
            self.assertGreater(len(candidates), 0, "fixture has no greedy rows")
            row = candidates[0]
            coverage = int(row["coverage"])
            optimum = int(row["optimum"])
            self.assertGreater(
                coverage, 0, "fixture greedy row has no coverage margin"
            )
            row["coverage"] = str(coverage - 1)
            row["optimality_gap"] = _format_gap(coverage - 1, optimum)
            tampered["run_id"] = row["run_id"]
            tampered["expected"] = row["coverage"]

        self.mutate_rows(self.variant / "raw_results.csv", transform)
        result = self.assertRejected("raw_results.coverage", "a coverage tamper")
        self.assertIn(tampered["run_id"], result.stdout)

    def test_selected_tamper_is_detected(self) -> None:
        tampered: dict[str, str] = {}

        def transform(rows: list[dict[str, str]]) -> None:
            candidates = self._greedy_rows(rows)
            self.assertGreater(len(candidates), 0, "fixture has no greedy rows")
            row = candidates[0]
            selected = [int(value) for value in row["selected"].split()]
            self.assertGreaterEqual(len(selected), 2)
            set_count = int(row["set_count"])
            replacement: int | None = None
            for offset in range(1, set_count):
                candidate = (selected[-1] + offset) % set_count
                if candidate not in selected:
                    replacement = candidate
                    break
            self.assertIsNotNone(replacement)
            selected[-1] = replacement
            row["selected"] = " ".join(str(value) for value in selected)
            tampered["run_id"] = row["run_id"]
            tampered["expected"] = row["selected"]

        self.mutate_rows(self.variant / "raw_results.csv", transform)
        result = self.assertRejected("raw_results.selected", "a selected tamper")
        self.assertIn(tampered["run_id"], result.stdout)

    def test_row_order_reversal_is_detected(self) -> None:
        def transform(rows: list[dict[str, str]]) -> None:
            rows.reverse()

        self.mutate_rows(self.variant / "raw_results.csv", transform)
        self.assertRejected("raw_results.row_order", "a row order reversal")

    def test_run_id_tamper_is_detected(self) -> None:
        # run_id is the content identity of a run and is compared bit-exact;
        # a tampered identifier must be flagged even though instance_id and the
        # logical pairing key are untouched.
        tampered: dict[str, str] = {}

        def transform(rows: list[dict[str, str]]) -> None:
            row = rows[0]
            row["run_id"] = row["instance_id"]

        self.mutate_rows(self.variant / "raw_results.csv", transform)
        self.assertRejected("raw_results.run_id", "a run_id tamper")

    def test_instance_id_tamper_is_detected(self) -> None:
        tampered: dict[str, str] = {}

        def transform(rows: list[dict[str, str]]) -> None:
            row = self._greedy_rows(rows)[0]
            replacement = row["run_id"]
            if replacement == row["instance_id"]:
                replacement = "0" * 64
            row["instance_id"] = replacement
            tampered["run_id"] = row["run_id"]
            tampered["expected"] = replacement

        self.mutate_rows(self.variant / "raw_results.csv", transform)
        result = self.assertRejected(
            "raw_results.instance_id", "an instance_id tamper"
        )
        self.assertIn(tampered["run_id"], result.stdout)
        self.assertIn(tampered["expected"][:12], result.stdout)

    def test_runtime_difference_is_exempt(self) -> None:
        def transform(rows: list[dict[str, str]]) -> None:
            for row in rows:
                shifted = float(row["runtime_seconds"]) + 0.25
                row["runtime_seconds"] = f"{shifted:.10f}"

        self.mutate_rows(self.variant / "raw_results.csv", transform)
        result = self.assertAccepted("when only runtime differs")
        self.assertIn("raw_results.runtime_seconds: consistent", result.stdout)
        self.assertIn("exempt", result.stdout)

    def _make_timeout_rows(
        self,
        path: Path,
        coverage_base: int,
        nodes_base: int,
        selected_text: str,
    ) -> None:
        def transform(rows: list[dict[str, str]]) -> None:
            row = self._greedy_rows(rows)[0]
            optimum = int(row["optimum"])
            coverage = optimum - coverage_base
            self.assertGreaterEqual(coverage, 0)
            self.assertEqual(
                tuple(int(value) for value in selected_text.split()),
                tuple(sorted(set(int(value) for value in selected_text.split()))),
                "test fixture selected sequence must stay valid and unique",
            )
            row["status"] = "timeout"
            row["is_exact"] = "False"
            row["timed_out"] = "True"
            row["coverage"] = str(coverage)
            row["optimality_gap"] = _format_gap(coverage, optimum)
            row["nodes_or_iterations"] = str(nodes_base)
            metadata = json.loads(row["algorithm_metadata"])
            metadata["termination"] = "time_limit"
            metadata["search"] = {"partial_nodes": nodes_base}
            row["algorithm_metadata"] = json.dumps(
                metadata, sort_keys=True, separators=(",", ":")
            )
            row["selected"] = selected_text

        self.mutate_rows(path, transform)

    def test_timeout_incumbent_difference_is_exempt(self) -> None:
        self._make_timeout_rows(
            self.baseline / "raw_results.csv",
            coverage_base=1,
            nodes_base=0,
            selected_text="0 3 6 9",
        )
        self._make_timeout_rows(
            self.variant / "raw_results.csv",
            coverage_base=3,
            nodes_base=7,
            selected_text="3 6 9",
        )
        result = self.assertAccepted(
            "when only the timeout incumbent differs"
        )
        self.assertIn("timeout-exempt", result.stdout)

    def test_manifest_config_hash_tamper_is_detected(self) -> None:
        manifest_path = self.variant / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["configuration"]["config_hash"] = "0" * 64
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        result = self.assertRejected(
            "manifest.configuration.config_hash", "a manifest config hash tamper"
        )
        self.assertIn("0" * 64, result.stdout)

    def test_manifest_seed_range_tamper_is_detected(self) -> None:
        manifest_path = self.variant / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["seeds"]["minimum"] = int(manifest["seeds"]["minimum"]) + 1
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        self.assertRejected(
            "manifest.seeds.minimum", "a manifest seed range tamper"
        )

    def test_manifest_seed_minimum_type_change_is_detected(self) -> None:
        # bit-exact covers the serialised JSON type, not only the Python
        # value: 2026 (int) and 2026.0 (float) compare equal under ==, so a
        # cross-version serialisation regression would be reported as
        # CONSISTENT by a value-only comparison.
        manifest_path = self.variant / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["seeds"]["minimum"] = float(manifest["seeds"]["minimum"])
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        result = self.assertRejected(
            "manifest.seeds.minimum", "a manifest seed minimum type change"
        )
        self.assertIn("(int)", result.stdout)
        self.assertIn("(float)", result.stdout)

    def test_manifest_algorithm_version_type_change_is_detected(self) -> None:
        # algorithms is compared bit-exact as a map, so a value that changes
        # JSON type inside a nested entry is a disagreement.
        manifest_path = self.variant / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = manifest["algorithms"].get("greedy")
        self.assertIsNotNone(entry, "fixture manifest has no greedy entry")
        entry["version"] = float(entry["version"])
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        result = self.assertRejected(
            "manifest.algorithms", "an algorithm version type change"
        )
        self.assertIn("greedy.version: baseline=1 (int)", result.stdout)
        self.assertIn("compare=1.0 (float)", result.stdout)

    def test_manifest_algorithm_enabled_bool_to_int_is_detected(self) -> None:
        # Python treats True == 1, but bit-exact as a map does not: the
        # enabled flag changing JSON type must be rejected.
        manifest_path = self.variant / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = manifest["algorithms"].get("greedy")
        self.assertIsNotNone(entry, "fixture manifest has no greedy entry")
        entry["enabled"] = 1
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        self.assertRejected(
            "manifest.algorithms", "an algorithm enabled type change"
        )

    def test_status_difference_is_detected(self) -> None:
        # The declaration compares status itself: a run stopped by the limit on
        # one platform and completed on another is a disagreement, even though
        # the timeout incumbent fields are exempt.
        self._make_timeout_rows(
            self.variant / "raw_results.csv",
            coverage_base=1,
            nodes_base=0,
            selected_text="0 3 6 9",
        )
        result = self.assertRejected(
            "raw_results.status", "a status difference into timeout"
        )

    def test_derived_flag_conflict_is_a_hard_error(self) -> None:
        # is_exact and timed_out are re-derived from status by the record
        # loader; a row where a derived flag disagrees with status cannot be
        # loaded and must fail the comparison as a hard error, not as a field
        # difference.
        def transform(rows: list[dict[str, str]]) -> None:
            rows[0]["timed_out"] = "True"

        self.mutate_rows(self.variant / "raw_results.csv", transform)
        result = run_compare(self.baseline, self.variant)
        self.assertEqual(result.returncode, 1)
        self.assertIn("matrix comparison failed", result.stderr)

    def test_seed_change_is_detected_and_names_instance_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "quick_seed.json"
            config = json.loads(CONFIG.read_text(encoding="utf-8"))
            config["base_seed"] = int(config["base_seed"]) + 1
            config_path.write_text(
                json.dumps(config, indent=2) + "\n", encoding="utf-8"
            )
            output = root / "run"
            completed = subprocess.run(
                [
                    sys.executable,
                    "run_project.py",
                    "benchmark",
                    "--config",
                    str(config_path),
                    "--output",
                    str(output),
                    "--workers",
                    "1",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"seed-variant fixture run failed: {completed.stderr[-2000:]}",
            )
            result = run_compare(self.baseline, output)
            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "raw_results.instance_id: inconsistent", result.stdout
            )
            self.assertIn(
                "manifest.configuration.config_hash: inconsistent",
                result.stdout,
            )

    def test_missing_artifact_is_a_hard_error(self) -> None:
        (self.variant / "manifest.json").unlink()
        result = run_compare(self.baseline, self.variant)
        self.assertEqual(result.returncode, 1)
        self.assertIn("matrix comparison failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
