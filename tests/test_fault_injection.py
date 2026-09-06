"""Fault-injection tests for benchmark result validation.

The benchmark validator checks supported identities, record relationships,
statistics and selected charts. Markdown wording and layout are outside its
scope; research prose is reviewed against the underlying data.

These cases mutate copies of a real quick run and assert the rejection or known
acceptance. They preserve measured
blind spots as regression cases rather than implying every mutation is detected.
The fixture is cached under results/ (gitignored). Results for this configuration
do not establish coverage for every generator or algorithm combination.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / ".github" / "scripts" / "validate_benchmark_output.py"
CONFIG = REPO_ROOT / "configs" / "quick.json"
FIXTURE_DIR = REPO_ROOT / "results" / "_fixture_quick"

def _run_validator(output: Path) -> subprocess.CompletedProcess[str]:
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


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    reader = csv.DictReader(lines)
    return list(reader.fieldnames or ()), list(reader)


def _write_rows(
    path: Path, fieldnames: list[str], rows: list[dict[str, str]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _different_selection(current: str, universe_size: int) -> str:
    """Return a selection guaranteed to differ from ``current``.

    Every index is rotated by one slot modulo the universe size, which maps
    any proper subset of the indices onto another selection of the same size;
    a selection that already covers the whole universe is the only fixed
    point, so the last index is dropped instead.
    """
    indices = [int(part) for part in current.split()]
    if not indices:
        raise ValueError(f"cannot mutate an empty selected set: {current!r}")
    if len(indices) >= universe_size:
        return " ".join(str(i) for i in indices[:-1])
    return " ".join(str((i + 1) % universe_size) for i in indices)


def _benchmark_fixture() -> Path:
    """Return one real quick run, generating it into results/ when absent.

    The cache directory is gitignored, and the fixture is transparent: the
    baseline test revalidates it before any mutation test runs, so a stale or
    corrupted cache fails loudly instead of feeding the mutations.
    """
    if FIXTURE_DIR.is_dir() and _run_validator(FIXTURE_DIR).returncode == 0:
        return FIXTURE_DIR
    if FIXTURE_DIR.exists():
        shutil.rmtree(FIXTURE_DIR)
    completed = subprocess.run(
        [
            sys.executable,
            "run_project.py",
            "benchmark",
            "--config",
            str(CONFIG),
            "--output",
            str(FIXTURE_DIR),
            "--workers",
            "1",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"failed to build fixture: {completed.stderr[-2000:]}"
        )
    return FIXTURE_DIR


class FaultInjectionGateTests(unittest.TestCase):
    """One mutated copy of a real run per test, against the validator gate."""

    reference: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.reference = _benchmark_fixture()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / "output"
        shutil.copytree(self.reference, self.output)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def assertRejected(self, note: str, message: str) -> None:
        result = _run_validator(self.output)
        self.assertEqual(
            result.returncode,
            1,
            f"validator accepted broken output ({note}); "
            f"stdout: {result.stdout[-800:]}",
        )
        self.assertIn(
            message,
            result.stderr,
            f"validator rejected for a different reason ({note}): "
            f"{result.stderr[-800:]}",
        )

    def assertAccepted(self, note: str) -> None:
        result = _run_validator(self.output)
        self.assertEqual(
            result.returncode,
            0,
            f"validator rejected output that should pass ({note}): "
            f"{result.stderr[-800:]}",
        )

    # -- baseline --------------------------------------------------------

    def test_the_fixture_itself_validates(self) -> None:
        # Without this, a rejection below could come from a broken fixture.
        self.assertAccepted("unmutated fixture copy")

    # -------------------------------------------------------------------
    # 1. coverage tampering
    # -------------------------------------------------------------------
    def test_coverage_tamper_is_rejected(self) -> None:
        fields, rows = _read_rows(self.output / "raw_results.csv")
        for row in rows:
            if (
                row["algorithm"] == "greedy"
                and row["status"] == "feasible"
                and row["coverage"] != row["optimum"]
            ):
                row["coverage"] = str(int(row["coverage"]) + 1)
                break
        else:
            self.fail("no greedy row with a positive gap in the fixture")
        _write_rows(self.output / "raw_results.csv", fields, rows)
        self.assertRejected(
            "a coverage value was raised while the gap column stayed put",
            "optimality_gap does not match optimum and coverage",
        )

    # -------------------------------------------------------------------
    # 2. selected-set tampering
    # -------------------------------------------------------------------
    def test_selected_tamper_on_a_non_lazy_run_is_a_measured_blind_spot(self) -> None:
        fields, rows = _read_rows(self.output / "raw_results.csv")
        for row in rows:
            if row["algorithm"] == "greedy" and row["status"] == "feasible":
                original = row["selected"]
                row["selected"] = _different_selection(
                    original, int(row["set_count"])
                )
                self.assertNotEqual(
                    row["selected"],
                    original,
                    "the selection mutation changed nothing in the fixture",
                )
                break
        else:
            self.fail("no greedy row in the fixture")
        _write_rows(self.output / "raw_results.csv", fields, rows)
        # The validator only re-checks coverage against the selected sets when
        # a Lazy Greedy pairing exists (validator._validate_lazy_greedy_rows);
        # quick.json has no Lazy Greedy variant, so the link is never replayed.
        self.assertAccepted(
            "selected changed on a greedy row with no Lazy Greedy pairing"
        )

    def test_selected_tamper_on_an_exact_run_is_a_measured_blind_spot(self) -> None:
        fields, rows = _read_rows(self.output / "raw_results.csv")
        for row in rows:
            if row["algorithm"] == "brute_force":
                original = row["selected"]
                row["selected"] = _different_selection(
                    original, int(row["set_count"])
                )
                self.assertNotEqual(
                    row["selected"],
                    original,
                    "the selection mutation changed nothing in the fixture",
                )
                break
        else:
            self.fail("no brute_force row in the fixture")
        _write_rows(self.output / "raw_results.csv", fields, rows)
        self.assertAccepted(
            "selected changed on an exact run whose coverage was left in place"
        )

    # -------------------------------------------------------------------
    # 3. gap tampering
    # -------------------------------------------------------------------
    def test_gap_tamper_is_rejected(self) -> None:
        fields, rows = _read_rows(self.output / "raw_results.csv")
        for row in rows:
            if row["algorithm"] == "greedy" and row["coverage"] != row["optimum"]:
                row["optimality_gap"] = "0.0500000000"
                break
        else:
            self.fail("no greedy row with a positive gap in the fixture")
        _write_rows(self.output / "raw_results.csv", fields, rows)
        self.assertRejected(
            "the gap column no longer equals the recomputed value",
            "optimality_gap does not match optimum and coverage",
        )

    # -------------------------------------------------------------------
    # -------------------------------------------------------------------

    # -------------------------------------------------------------------
    # 5. seed tampering
    # -------------------------------------------------------------------
    def test_raw_result_seed_tamper_is_rejected(self) -> None:
        fields, rows = _read_rows(self.output / "raw_results.csv")
        rows[0]["seed"] = str(int(rows[0]["seed"]) + 1000)
        _write_rows(self.output / "raw_results.csv", fields, rows)
        self.assertRejected(
            "a raw row was given a seed the execution plan does not contain",
            "field 'seed' does not match",
        )

    def test_instance_seed_tamper_is_a_measured_blind_spot(self) -> None:
        fields, rows = _read_rows(self.output / "instances.csv")
        rows[0]["seed"] = "9999"
        _write_rows(self.output / "instances.csv", fields, rows)
        # The validator re-derives the plan for raw rows only. Instance records
        # are compared by config hash, composite key uniqueness and presence of
        # their derived evidence; seed is not part of that chain.
        self.assertAccepted("an instance record was given a fabricated seed")

    def test_seed_and_run_id_tampers_are_rejected(self) -> None:
        fields, rows = _read_rows(self.output / "raw_results.csv")
        rows[0]["seed"] = "9999"
        rows[0]["run_id"] = "0" * 64
        _write_rows(self.output / "raw_results.csv", fields, rows)
        self.assertRejected(
            "seed and run_id changed together, so run_id no longer matches the plan",
            "run_id values do not match the execution plan",
        )

    # -------------------------------------------------------------------
    # 6. canonical row ordering
    # -------------------------------------------------------------------
    def test_raw_row_order_tamper_is_a_measured_blind_spot(self) -> None:
        fields, rows = _read_rows(self.output / "raw_results.csv")
        rows = list(reversed(rows))
        _write_rows(self.output / "raw_results.csv", fields, rows)
        # Every recomputation in the validator keys on run_id or sorts by group
        # key, so row order is not part of the checked contract.
        self.assertAccepted("raw_result rows were written in reverse order")

    def test_instance_row_order_tamper_is_a_measured_blind_spot(self) -> None:
        fields, rows = _read_rows(self.output / "instances.csv")
        rows = list(reversed(rows))
        _write_rows(self.output / "instances.csv", fields, rows)
        self.assertAccepted("instance records were written in reverse order")

    # -------------------------------------------------------------------
    # 7. feasible-to-optimal disguise without a certificate
    # -------------------------------------------------------------------
    def test_status_only_disguise_is_rejected(self) -> None:
        fields, rows = _read_rows(self.output / "raw_results.csv")
        for row in rows:
            if row["algorithm"] == "greedy" and row["case_id"] == "greedy_trap":
                row["status"] = "optimal"
                break
        else:
            self.fail("no greedy_trap greedy row in the fixture")
        _write_rows(self.output / "raw_results.csv", fields, rows)
        self.assertRejected(
            "status flipped to optimal while is_exact still says false",
            "CSV field 'is_exact' conflicts with status",
        )

    def test_complete_feasible_to_optimal_disguise_is_rejected(self) -> None:
        fields, rows = _read_rows(self.output / "raw_results.csv")
        for row in rows:
            if row["algorithm"] == "greedy" and row["case_id"] == "greedy_trap":
                row["status"] = "optimal"
                row["coverage"] = row["optimum"]
                row["optimality_gap"] = "0.0000000000"
                row["is_exact"] = "True"
                row["best_bound"] = row["optimum"]
                break
        else:
            self.fail("no greedy_trap greedy row in the fixture")
        _write_rows(self.output / "raw_results.csv", fields, rows)
        # The flip is internally consistent now; the derived statistics
        # recomputation is what refuses it.
        self.assertRejected(
            "a greedy row fully relabelled as an optimal exact run",
            "descriptive statistics do not match canonical raw results",
        )

    # -------------------------------------------------------------------
    # 8. fake certificate (certificate evidence contradicting results)
    # -------------------------------------------------------------------
    def test_partial_certificate_injection_is_rejected(self) -> None:
        fields, rows = _read_rows(self.output / "instances.csv")
        for row in rows:
            if row["case_id"] == "uniform_sparse" and row["repetition"] == "0":
                row["known_optimum"] = "46"
                break
        else:
            self.fail("no uniform_sparse repetition zero row in the fixture")
        _write_rows(self.output / "instances.csv", fields, rows)
        self.assertRejected(
            "only the optimum value of a certificate was injected",
            "known optimum certificate fields must be all present or all absent",
        )

    def test_certificate_injection_on_a_stochastic_family_is_rejected(self) -> None:
        fields, rows = _read_rows(self.output / "instances.csv")
        for row in rows:
            if row["case_id"] == "uniform_sparse" and row["repetition"] == "0":
                row["known_optimum"] = "80"
                row["optimum_source"] = "constructed_certificate"
                row["optimum_selected"] = "[0, 1, 2, 3]"
                row["proof_kind"] = "covers_universe"
                break
        else:
            self.fail("no uniform_sparse repetition zero row in the fixture")
        _write_rows(self.output / "instances.csv", fields, rows)
        self.assertRejected(
            "a complete fabricated certificate on a stochastic instance",
            "certificate fields must remain unknown",
        )

    def test_certificate_injection_on_a_legacy_adversarial_instance_is_rejected(self) -> None:
        fields, rows = _read_rows(self.output / "instances.csv")
        for row in rows:
            if row["case_id"] == "greedy_trap":
                row["known_optimum"] = "60"
                row["optimum_source"] = "constructed_certificate"
                row["optimum_selected"] = "[1, 2]"
                row["proof_kind"] = "covers_universe"
                break
        else:
            self.fail("no greedy_trap row in the fixture")
        _write_rows(self.output / "instances.csv", fields, rows)
        self.assertRejected(
            "a complete fabricated certificate on a legacy built instance",
            "legacy adversarial certificate fields must remain unknown",
        )

    # -------------------------------------------------------------------
    # 9. Markdown text is outside numeric validation
    # -------------------------------------------------------------------
    def test_report_rewriting_does_not_change_numeric_validation(self) -> None:
        summary = self.output / "results_summary.md"
        original = summary.read_text(encoding="utf-8")
        for text in (
            original.replace("## Headline checks", "## Main findings", 1),
            "# 研究报告\n\n## 方法与数据\n\n按研究需要重新组织的说明。\n",
        ):
            with self.subTest(report=text[:40]):
                summary.write_text(text, encoding="utf-8")
                self.assertAccepted("report headings and prose were rewritten")


if __name__ == "__main__":
    unittest.main()
