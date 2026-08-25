from __future__ import annotations

import importlib.util
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import (
    _cp_sat_outcome,
    branch_and_bound,
    branch_and_bound_enhanced,
    brute_force,
    cp_sat_oracle,
)
from maxcover.benchmark import run_benchmark
from maxcover.config import ConfigurationError, parse_config
from maxcover.generators import uniform_random
from maxcover.model import SolutionStatus


HAS_ORTOOLS = importlib.util.find_spec("ortools") is not None


def _oracle_config() -> dict[str, object]:
    return {
        "schema_version": 3,
        "name": "optional oracle",
        "base_seed": 1,
        "repetitions": 1,
        "algorithms": [
            {
                "id": "oracle",
                "name": "cp_sat_oracle",
                "options": {"time_limit_seconds": 2.0},
            }
        ],
        "cases": [
            {
                "name": "tiny",
                "family": "uniform",
                "universe_size": 20,
                "set_count": 8,
                "k": 3,
                "density": 0.2,
            }
        ],
    }


class OptionalOracleTests(unittest.TestCase):
    def test_standard_import_does_not_import_ortools(self) -> None:
        script = (
            "import sys; "
            f"sys.path.insert(0, {str(ROOT / 'src')!r}); "
            "import maxcover; "
            "print(any(name == 'ortools' or name.startswith('ortools.') "
            "for name in sys.modules))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.stdout.strip(), "False")

    @unittest.skipIf(HAS_ORTOOLS, "missing-dependency preflight only")
    def test_enabled_oracle_has_clear_preflight_install_hint(self) -> None:
        with self.assertRaisesRegex(
            ConfigurationError, r"pip install -e .*\[oracle\]"
        ):
            parse_config(_oracle_config())

    def test_status_mapping_covers_all_cp_sat_outcomes(self) -> None:
        self.assertEqual(
            _cp_sat_outcome("OPTIMAL", coverage=7, universe_size=10),
            (SolutionStatus.OPTIMAL, 7, True),
        )
        self.assertEqual(
            _cp_sat_outcome(
                "FEASIBLE", coverage=6, universe_size=10, solver_bound=8.0000000001
            ),
            (SolutionStatus.TIMEOUT, 8, True),
        )
        self.assertEqual(
            _cp_sat_outcome("UNKNOWN", coverage=6, universe_size=10),
            (SolutionStatus.TIMEOUT, 10, False),
        )
        self.assertEqual(
            _cp_sat_outcome("UNKNOWN", coverage=10, universe_size=10),
            (SolutionStatus.OPTIMAL, 10, False),
        )
        for status in ("MODEL_INVALID", "INFEASIBLE", "UNRECOGNIZED"):
            self.assertEqual(
                _cp_sat_outcome(status, coverage=0, universe_size=10),
                (SolutionStatus.ERROR, None, False),
            )

    @unittest.skipIf(HAS_ORTOOLS, "missing-dependency behavior only")
    def test_direct_call_without_optional_dependency_is_explicit(self) -> None:
        instance = uniform_random(
            universe_size=20, set_count=8, k=3, density=0.2, seed=1
        )
        with self.assertRaisesRegex(RuntimeError, "requires OR-Tools"):
            cp_sat_oracle(instance)

    @unittest.skipUnless(HAS_ORTOOLS, "requires optional OR-Tools dependency")
    def test_oracle_matches_branch_and_bound_on_200_random_instances(self) -> None:
        generator = random.Random(20260720)
        for sample in range(200):
            set_count = generator.randint(4, 11)
            instance = uniform_random(
                universe_size=generator.randint(8, 28),
                set_count=set_count,
                k=generator.randint(1, set_count),
                density=generator.uniform(0.05, 0.7),
                seed=generator.randrange(10_000_000),
            )
            solutions = (
                brute_force(instance, time_limit_seconds=None),
                branch_and_bound(instance, time_limit_seconds=None),
                branch_and_bound_enhanced(instance, time_limit_seconds=None),
                cp_sat_oracle(instance, time_limit_seconds=5.0),
            )
            self.assertTrue(
                all(solution.status is SolutionStatus.OPTIMAL for solution in solutions),
                sample,
            )
            self.assertEqual(len({solution.coverage for solution in solutions}), 1, sample)

    @unittest.skipUnless(HAS_ORTOOLS, "requires optional OR-Tools dependency")
    def test_manifest_records_ortools_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(_oracle_config()), encoding="utf-8")
            run_benchmark(config_path, root / "output")
            manifest = json.loads(
                (root / "output" / "manifest.json").read_text(encoding="utf-8")
            )
        self.assertRegex(manifest["environment"]["ortools"], r"^9\.15\.")


if __name__ == "__main__":
    unittest.main()
