"""Fault-injection tests for the benchmark publication gates.

The publication path has three independent gates:

- validate_benchmark_output.py recomputes every derived artifact from the raw
  results and the execution plan, so a fault survives a correctly refreshed
  manifest checksum;
- manifest.json records byte counts and digests over every artifact, so a file
  altered after the run is caught when the record is not refreshed;
- check_content_boundary.py rejects quantitative research claims in every
  tracked prose file, under the active claim mode.

Each case below breaks one thing a declared contract says must hold, on a copy
of a real quick run, and asserts what the gate actually did. Cases that the
gate accepts are measured blind spots, not authorial optimism: they are listed
in docs/fault_injection_matrix.md with the measured mechanism, and each one is
asserted as "the gate passes" so a future fix is a one-line change here.

The fixture is one real benchmark run, cached under results/ (gitignored),
because a hand-built fixture would encode this test's idea of the format rather
than the runner's.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / ".github" / "scripts" / "validate_benchmark_output.py"
CONTENT_CHECKER = REPO_ROOT / ".github" / "scripts" / "check_content_boundary.py"
CONFIG = REPO_ROOT / "configs" / "quick.json"
FIXTURE_DIR = REPO_ROOT / "results" / "_fixture_quick"

# The claim strings below are assembled from fragments rather than written as
# literals, so the reviewer sees the construction next to the rule it probes.
_FRAGMENT_FAILED = "Greedy failed on "
_FRAGMENT_COUNT = "3 of 12 instances."
_FRAGMENT_MEAN = "The mean coverage was "
_FRAGMENT_VALUE = "44.0 across the four families."


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


def _refresh_manifest_entry(output: Path, filename: str) -> None:
    """Rewrite the checksum record to match the altered artifact."""
    artifact = output / filename
    payload = artifact.read_bytes()
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"][filename] = {
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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
        _refresh_manifest_entry(self.output, "raw_results.csv")
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
        _refresh_manifest_entry(self.output, "raw_results.csv")
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
        _refresh_manifest_entry(self.output, "raw_results.csv")
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
        _refresh_manifest_entry(self.output, "raw_results.csv")
        self.assertRejected(
            "the gap column no longer equals the recomputed value",
            "optimality_gap does not match optimum and coverage",
        )

    # -------------------------------------------------------------------
    # 4. manifest checksum tampering
    # -------------------------------------------------------------------
    def test_manifest_checksum_tamper_is_rejected(self) -> None:
        manifest_path = self.output / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        digest = manifest["outputs"]["raw_results.csv"]["sha256"]
        manifest["outputs"]["raw_results.csv"]["sha256"] = (
            ("0" if digest[0] != "0" else "1") + digest[1:]
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.assertRejected(
            "the recorded digest was flipped without touching the artifact",
            "SHA-256 mismatch for raw_results.csv",
        )

    # -------------------------------------------------------------------
    # 5. seed tampering
    # -------------------------------------------------------------------
    def test_raw_result_seed_tamper_is_rejected(self) -> None:
        fields, rows = _read_rows(self.output / "raw_results.csv")
        rows[0]["seed"] = str(int(rows[0]["seed"]) + 1000)
        _write_rows(self.output / "raw_results.csv", fields, rows)
        _refresh_manifest_entry(self.output, "raw_results.csv")
        self.assertRejected(
            "a raw row was given a seed the execution plan does not contain",
            "field 'seed' does not match",
        )

    def test_instance_seed_tamper_is_a_measured_blind_spot(self) -> None:
        fields, rows = _read_rows(self.output / "instances.csv")
        rows[0]["seed"] = "9999"
        _write_rows(self.output / "instances.csv", fields, rows)
        _refresh_manifest_entry(self.output, "instances.csv")
        # The validator re-derives the plan for raw rows only. Instance records
        # are compared by config hash, composite key uniqueness and presence of
        # their derived evidence; seed is not part of that chain.
        self.assertAccepted("an instance record was given a fabricated seed")

    def test_seed_and_run_id_tampers_are_rejected(self) -> None:
        fields, rows = _read_rows(self.output / "raw_results.csv")
        rows[0]["seed"] = "9999"
        rows[0]["run_id"] = "0" * 64
        _write_rows(self.output / "raw_results.csv", fields, rows)
        _refresh_manifest_entry(self.output, "raw_results.csv")
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
        _refresh_manifest_entry(self.output, "raw_results.csv")
        # Every recomputation in the validator keys on run_id or sorts by group
        # key, so row order is not part of the checked contract.
        self.assertAccepted("raw_result rows were written in reverse order")

    def test_instance_row_order_tamper_is_a_measured_blind_spot(self) -> None:
        fields, rows = _read_rows(self.output / "instances.csv")
        rows = list(reversed(rows))
        _write_rows(self.output / "instances.csv", fields, rows)
        _refresh_manifest_entry(self.output, "instances.csv")
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
        _refresh_manifest_entry(self.output, "raw_results.csv")
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
        _refresh_manifest_entry(self.output, "raw_results.csv")
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
        _refresh_manifest_entry(self.output, "instances.csv")
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
        _refresh_manifest_entry(self.output, "instances.csv")
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
        _refresh_manifest_entry(self.output, "instances.csv")
        self.assertRejected(
            "a complete fabricated certificate on a legacy built instance",
            "legacy adversarial certificate fields must remain unknown",
        )

    # -------------------------------------------------------------------
    # 9. quantitative conclusion without an evidence chain
    # -------------------------------------------------------------------
    def test_conclusion_outside_the_headline_section_is_a_measured_blind_spot(self) -> None:
        summary = self.output / "results_summary.md"
        text = summary.read_text(encoding="utf-8")
        claim = _FRAGMENT_FAILED + _FRAGMENT_COUNT
        text = text + "\n\n## Conclusion\n\n" + claim + "\n"
        summary.write_text(text, encoding="utf-8")
        _refresh_manifest_entry(self.output, "results_summary.md")
        # The validator compares exactly the lines between the first
        # "## Headline checks" heading and the next heading. Anything written
        # elsewhere in the summary is never compared.
        self.assertAccepted(
            "a fabricated conclusion appended after the checked section"
        )

    def test_duplicate_headline_section_is_a_measured_blind_spot(self) -> None:
        summary = self.output / "results_summary.md"
        text = summary.read_text(encoding="utf-8")
        marker = "## Next analysis questions"
        inserted = (
            "## Headline checks\n\n"
            + _FRAGMENT_FAILED
            + _FRAGMENT_COUNT
            + "\n\n"
        )
        text = text.replace(marker, inserted + marker, 1)
        summary.write_text(text, encoding="utf-8")
        _refresh_manifest_entry(self.output, "results_summary.md")
        self.assertAccepted(
            "a second headline section announcing a different conclusion"
        )

    def test_headline_value_tamper_is_rejected(self) -> None:
        summary = self.output / "results_summary.md"
        text = summary.read_text(encoding="utf-8")
        self.assertIn("**80.00%**", text)
        text = text.replace("**80.00%**", "**81.00%**", 1)
        summary.write_text(text, encoding="utf-8")
        _refresh_manifest_entry(self.output, "results_summary.md")
        self.assertRejected(
            "a headline value was changed inside the checked section",
            "automatic conclusion headlines do not match",
        )

    def test_headline_section_rename_is_rejected(self) -> None:
        summary = self.output / "results_summary.md"
        text = summary.read_text(encoding="utf-8")
        text = text.replace("## Headline checks", "## Headline check", 1)
        summary.write_text(text, encoding="utf-8")
        _refresh_manifest_entry(self.output, "results_summary.md")
        self.assertRejected(
            "the checked section heading was renamed",
            "results_summary.md is missing section boundary",
        )


class ContentBoundaryFaultInjectionTests(unittest.TestCase):
    """The claim gate, exercised over a temporary git tree."""

    def _repo(self) -> tempfile.TemporaryDirectory[str]:
        tmp = tempfile.TemporaryDirectory()
        subprocess.run(
            ["git", "init", "-q", tmp.name],
            check=True,
            capture_output=True,
        )
        return tmp

    def _check(self, root: Path, mode: str = "no_quantitative_claims"):
        return subprocess.run(
            [
                sys.executable,
                str(CONTENT_CHECKER),
                "--claim-mode",
                mode,
                "--repo-root",
                str(root),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def test_a_tracked_conclusion_without_evidence_is_rejected(self) -> None:
        tmp = self._repo()
        root = Path(tmp.name)
        claim = _FRAGMENT_FAILED + _FRAGMENT_COUNT
        (root / "finding.md").write_text("# Notes\n\n" + claim + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        result = self._check(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("reads as a quantitative result claim", result.stdout)
        self.assertIn("finding.md", result.stdout)
        tmp.cleanup()

    def test_an_untracked_results_artifact_is_not_scanned(self) -> None:
        tmp = self._repo()
        root = Path(tmp.name)
        claim = _FRAGMENT_MEAN + _FRAGMENT_VALUE
        results = root / "results"
        results.mkdir()
        (results / "results_summary.md").write_text(claim + "\n", encoding="utf-8")
        # Never added: the checker enumerates git ls-files only.
        result = self._check(root)
        self.assertEqual(
            result.returncode,
            0,
            f"untracked output was scanned: {result.stdout}",
        )
        self.assertIn("tracked files : 0", result.stdout)
        tmp.cleanup()

    def test_claim_mode_without_quantitative_claims_allows_plain_prose(self) -> None:
        tmp = self._repo()
        root = Path(tmp.name)
        (root / "notes.md").write_text(
            "# Notes\n\nA runnable study of set coverage algorithms.\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        result = self._check(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        tmp.cleanup()

    def test_the_wider_claim_mode_is_currently_a_noop(self) -> None:
        tmp = self._repo()
        root = Path(tmp.name)
        claim = _FRAGMENT_FAILED + _FRAGMENT_COUNT
        (root / "finding.md").write_text("# Notes\n\n" + claim + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        result = self._check(root, mode="evidence_backed_claims")
        # The checker documents that evidence binding belongs to its own
        # workflow, so the wider mode currently verifies nothing.
        self.assertEqual(
            result.returncode,
            0,
            f"evidence-backed mode rejected: {result.stdout}",
        )
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
