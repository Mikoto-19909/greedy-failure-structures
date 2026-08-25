from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.algorithms import (
    ALGORITHMS,
    branch_and_bound,
    branch_and_bound_enhanced,
    brute_force,
    greedy,
)
from maxcover.benchmark import _instances_for_config, _rows_for_instance, run_benchmark
from maxcover.certificates import (
    KnownOptimumCertificate,
    known_optimum_certificate,
    validate_known_optimum_certificate,
)
from maxcover.config import ConfigurationError, load_config, parse_config
from maxcover.contracts import AlgorithmRunOptions
from maxcover.generators import (
    _potential_distractor_rankings,
    adversarial_greedy_trap,
)
from maxcover.model import MaximumCoverageInstance, Solution, SolutionStatus
from maxcover.reproducibility import canonical_json, instance_id, run_id


LEGACY_GOLDEN = {
    32026: (
        (
            70367670501375,
            1073741823,
            1152921503533105152,
            864726813268017217,
            704306045093140,
            72155623454689301,
            505622896767664384,
            111466292016367492,
            94872480740671618,
            46727061804426376,
            3527268500881669,
        ),
        "550acda95d7a1f04c39e3bf6e33fef84974f35f025cd3b21b95e78780442a7f9",
        "59f015b6ddb48185a7b9822fdc2cd4bb784fd8fe05e120db73ecc4adef2ff6ce",
    ),
    32027: (
        (
            70367670501375,
            1073741823,
            1152921503533105152,
            13511435658887432,
            5087620824569916,
            166914713084039696,
            380765292245057557,
            36311046217009316,
            2688307945365506,
            9078119150133333,
            4754582542794756,
        ),
        "2bac932c45faf8ef8621693945d71c7e77ac87a1566f05d1239582dacb13bd42",
        "197c4bdd74de3395cd666cd56a5fc4846c3d1c8ecee918019339fb311b7a65ca",
    ),
    32028: (
        (
            70367670501375,
            1073741823,
            1152921503533105152,
            41030621727842434,
            13550591491970112,
            612718463026242181,
            288343628198238368,
            306958134990110849,
            145534659076296880,
            19300075630135344,
            189364558345183236,
        ),
        "efb2e7db487d61e77bf2788ddd3df2c518f70b2eb13338dcbeab9c9e9b797863",
        "779e66413b12445920591b88848a5e17b6a87141eaf09100d3118c4c104085ab",
    ),
}


def _v2(
    *, block_size: int, trap_count: int, seed: int
) -> MaximumCoverageInstance:
    return adversarial_greedy_trap(
        block_size=block_size,
        distractor_count=8,
        construction_version=2,
        trap_count=trap_count,
        seed=seed,
        coupling_seed=seed,
    )


def _config(cases: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 3,
        "name": "P4.2 adversarial contracts",
        "base_seed": 17,
        "repetitions": 2,
        "algorithms": [
            {"name": "greedy"},
            {"name": "brute_force", "options": {"max_set_count": 16}},
        ],
        "cases": cases,
    }


class LegacyAdversarialCompatibilityTests(unittest.TestCase):
    def test_frozen_quick_instances_and_run_ids_remain_exact(self) -> None:
        greedy_spec = ALGORITHMS["greedy"]
        options = greedy_spec.option_values(AlgorithmRunOptions())
        for seed, (sets, expected_instance_id, expected_run_id) in LEGACY_GOLDEN.items():
            with self.subTest(seed=seed):
                omitted = adversarial_greedy_trap(
                    block_size=30, distractor_count=8, seed=seed
                )
                explicit = adversarial_greedy_trap(
                    block_size=30,
                    distractor_count=8,
                    construction_version=1,
                    seed=seed,
                )
                self.assertEqual(omitted, explicit)
                self.assertEqual(omitted.sets, sets)
                self.assertEqual(
                    omitted.parameters,
                    {"block_size": 30, "distractor_count": 8},
                )
                identifier = instance_id(omitted)
                self.assertEqual(identifier, expected_instance_id)
                self.assertEqual(
                    run_id(
                        identifier,
                        "greedy",
                        options,
                        algorithm_version=greedy_spec.version,
                    ),
                    expected_run_id,
                )

    def test_legacy_default_distractor_count_does_not_add_version(self) -> None:
        instance = adversarial_greedy_trap(block_size=8, seed=3)
        self.assertEqual(
            instance.parameters, {"block_size": 8, "distractor_count": 4}
        )


class AdversarialSeverityConstructionTests(unittest.TestCase):
    def assert_v2_invariants(
        self, block_size: int, trap_count: int, seed: int
    ) -> MaximumCoverageInstance:
        instance = _v2(block_size=block_size, trap_count=trap_count, seed=seed)
        repeated = _v2(block_size=block_size, trap_count=trap_count, seed=seed)
        self.assertEqual(instance, repeated)
        self.assertEqual(instance.set_count, 11)
        self.assertEqual(instance.k, 2)
        self.assertEqual(instance.sets[1], (1 << block_size) - 1)
        self.assertEqual(
            instance.sets[2], ((1 << block_size) - 1) << block_size
        )
        trap = instance.sets[0]
        expected_half = (1 << trap_count) - 1
        self.assertEqual(trap, expected_half | (expected_half << block_size))
        residual = block_size - trap_count
        for distractor in instance.sets[3:]:
            self.assertLessEqual(distractor.bit_count(), block_size)
            if residual > 0:
                self.assertLess((distractor & ~trap).bit_count(), residual)
        solution = greedy(instance)
        self.assertEqual(solution.selected, (0, 1))
        self.assertEqual(solution.coverage, block_size + trap_count)
        certificate = known_optimum_certificate(instance)
        self.assertIsNotNone(certificate)
        assert certificate is not None
        self.assertEqual(certificate.value, 2 * block_size)
        self.assertEqual(certificate.selected, (1, 2))
        validate_known_optimum_certificate(instance, certificate)
        return instance

    def test_main_ci_grid(self) -> None:
        for block_size in range(4, 11):
            for trap_count in range(block_size // 2 + 1, block_size + 1):
                for seed in range(5):
                    with self.subTest(b=block_size, t=trap_count, seed=seed):
                        self.assert_v2_invariants(block_size, trap_count, seed)

    def test_extended_grid(self) -> None:
        for block_size in range(4, 33):
            for trap_count in range(block_size // 2 + 1, block_size + 1):
                for seed in range(50):
                    instance = self.assert_v2_invariants(
                        block_size, trap_count, seed
                    )
                    coverage = greedy(instance).coverage
                    severity = (2 * block_size - coverage) / (2 * block_size)
                    self.assertEqual(
                        severity, (block_size - trap_count) / (2 * block_size)
                    )
                    self.assertEqual(severity == 0, trap_count == block_size)

    def test_potential_rankings_are_shared_and_projection_is_exact(self) -> None:
        block_size = 12
        coupling_seed = 991
        rankings = _potential_distractor_rankings(
            2 * block_size, 8, coupling_seed
        )
        self.assertEqual(
            rankings,
            _potential_distractor_rankings(2 * block_size, 8, coupling_seed),
        )
        for trap_count in (7, 8, 9, 12):
            instance = adversarial_greedy_trap(
                block_size=block_size,
                distractor_count=8,
                construction_version=2,
                trap_count=trap_count,
                seed=123 + trap_count,
                coupling_seed=coupling_seed,
            )
            trap_members = {
                *range(trap_count),
                *range(block_size, block_size + trap_count),
            }
            residual = block_size - trap_count
            for ranking, actual in zip(rankings, instance.sets[3:], strict=True):
                if residual == 0:
                    chosen = ranking[:block_size]
                else:
                    new = [item for item in ranking if item not in trap_members][
                        : residual - 1
                    ]
                    covered = [item for item in ranking if item in trap_members]
                    chosen = (*new, *covered[: block_size - len(new)])
                expected = sum(1 << item for item in chosen)
                self.assertEqual(actual, expected)

    def test_sha_smallest_500_exact_cross_check(self) -> None:
        corpus = [
            (block_size, trap_count, seed)
            for block_size in range(4, 33)
            for trap_count in range(block_size // 2 + 1, block_size + 1)
            for seed in range(50)
        ]
        corpus.sort(
            key=lambda item: hashlib.sha256(
                canonical_json(
                    {"b": item[0], "t": item[1], "seed": item[2]}
                ).encode("utf-8")
            ).hexdigest()
        )
        selected_corpus = corpus[:500]
        selected_payload = [
            {"b": block_size, "t": trap_count, "seed": seed}
            for block_size, trap_count, seed in selected_corpus
        ]
        self.assertEqual(
            hashlib.sha256(canonical_json(selected_payload).encode("utf-8")).hexdigest(),
            "097f9ba84f5f8f9631d7df3e3c787a1fea56adec00f0633d6ebf94793d214c6b",
        )
        for block_size, trap_count, seed in selected_corpus:
            instance = _v2(
                block_size=block_size, trap_count=trap_count, seed=seed
            )
            expected = 2 * block_size
            solutions = (
                brute_force(instance, time_limit_seconds=None),
                branch_and_bound(instance, time_limit_seconds=None),
                branch_and_bound_enhanced(instance, time_limit_seconds=None),
            )
            self.assertEqual(
                {solution.status for solution in solutions},
                {SolutionStatus.OPTIMAL},
            )
            self.assertEqual(
                {solution.coverage for solution in solutions}, {expected}
            )


class AdversarialSeverityIntegrationTests(unittest.TestCase):
    def test_preflight_rejects_version_and_trap_errors_at_exact_paths(self) -> None:
        base_case = {
            "name": "trap",
            "family": "adversarial",
            "block_size": 8,
            "distractor_count": 8,
        }
        invalid = (
            ({**base_case, "construction_version": 3}, "construction_version"),
            ({**base_case, "construction_version": 2}, "trap_count"),
            (
                {**base_case, "construction_version": 2, "trap_count": 4},
                "trap_count",
            ),
            (
                {**base_case, "construction_version": 2, "trap_count": 9},
                "trap_count",
            ),
            (
                {
                    **base_case,
                    "construction_version": 2,
                    "trap_count": 6,
                    "coupling_seed": 99,
                },
                "coupling_seed",
            ),
            ({**base_case, "trap_count": 6}, "trap_count"),
        )
        for case, field in invalid:
            with self.subTest(case=case):
                with self.assertRaises(ConfigurationError) as caught:
                    parse_config(_config([case]))
                self.assertTrue(
                    any(
                        path == f"$.cases[0].{field}"
                        for path, _ in caught.exception.issues
                    ),
                    caught.exception.issues,
                )

    def test_scan_config_has_three_blocks_and_four_severities_each(self) -> None:
        config = load_config(ROOT / "configs" / "p4_adversarial_severity.json")
        levels: dict[int, set[int]] = {}
        for case in config.cases:
            block_size = int(case.parameters["block_size"])
            levels.setdefault(block_size, set()).add(
                int(case.parameters["trap_count"])
            )
        self.assertGreaterEqual(len(levels), 3)
        for block_size, trap_counts in levels.items():
            self.assertIn(block_size, trap_counts)
            self.assertGreaterEqual(
                sum(trap_count < block_size for trap_count in trap_counts), 3
            )

    def test_planned_v2_instances_reproduce_through_case_generator(self) -> None:
        cases = [
            {
                "name": "control",
                "family": "adversarial",
                "block_size": 8,
                "distractor_count": 8,
                "construction_version": 2,
                "trap_count": 8,
            },
            {
                "name": "positive",
                "family": "adversarial",
                "block_size": 8,
                "distractor_count": 8,
                "construction_version": 2,
                "trap_count": 5,
            },
        ]
        parsed = parse_config(_config(cases))
        cases_by_id = {case.case_id: case for case in parsed.cases}
        for planned in _instances_for_config(parsed):
            try:
                regenerated = cases_by_id[planned.case_id].generate(
                    planned.instance.seed,
                    derived_parameters={"coupling_seed": planned.coupling_seed},
                )
            except TypeError as error:
                self.fail(f"CaseConfig.generate rejected derived parameters: {error}")
            self.assertEqual(regenerated, planned.instance)

    def test_coupling_certificates_and_four_classifications_round_trip(self) -> None:
        cases = [
            {
                "name": "random",
                "family": "uniform",
                "universe_size": 20,
                "set_count": 8,
                "k": 2,
                "density": 0.2,
            },
            {
                "name": "legacy",
                "family": "adversarial",
                "block_size": 8,
                "distractor_count": 8,
            },
            {
                "name": "control",
                "family": "adversarial",
                "block_size": 8,
                "distractor_count": 8,
                "construction_version": 2,
                "trap_count": 8,
            },
            {
                "name": "positive",
                "family": "adversarial",
                "block_size": 8,
                "distractor_count": 8,
                "construction_version": 2,
                "trap_count": 5,
            },
        ]
        parsed = parse_config(_config(cases))
        planned = _instances_for_config(parsed)
        for repetition in range(parsed.repetitions):
            coupled = [
                item
                for item in planned
                if item.repetition == repetition
                and item.instance.parameters.get("construction_version") == 2
            ]
            self.assertEqual(len(coupled), 2)
            self.assertEqual(len({item.coupling_pair_id for item in coupled}), 1)
            self.assertEqual(len({item.coupling_seed for item in coupled}), 1)
            self.assertEqual(len({item.instance.seed for item in coupled}), 2)
            self.assertEqual(len({item.instance_id for item in coupled}), 2)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(_config(cases)), encoding="utf-8")
            result = run_benchmark(config_path, root / "output")
            restored = {
                (record.case_id, record.repetition): record
                for record in result.instances
            }
            random = restored[("random", 0)]
            legacy = restored[("legacy", 0)]
            control = restored[("control", 0)]
            positive = restored[("positive", 0)]
            self.assertEqual((random.instance_origin, random.is_adversarial), ("stochastic", False))
            self.assertEqual((legacy.instance_origin, legacy.is_adversarial), ("constructed", True))
            self.assertIsNone(legacy.adversarial_severity)
            self.assertEqual((control.instance_origin, control.is_adversarial), ("constructed", False))
            self.assertEqual(control.adversarial_severity, 0)
            self.assertEqual((positive.instance_origin, positive.is_adversarial), ("constructed", True))
            self.assertGreater(positive.adversarial_severity or 0, 0)
            self.assertEqual(positive.known_optimum, 16)
            self.assertEqual(positive.optimum_selected, (1, 2))
            positive_rows = [row for row in result.rows if row.case_id == "positive"]
            self.assertTrue(all(row.optimum == 16 for row in positive_rows))
            report = (result.output_dir / "results_summary.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "Greedy-gap headline withheld: 0/4 Case/variant groups",
                report,
            )
            self.assertNotIn(
                "Largest eligible mean gap on classified adversarial "
                "constructions:",
                report,
            )
            self.assertNotIn(
                "Largest eligible mean gap outside constructed instance "
                "families:",
                report,
            )

    def test_certificate_supplies_timeout_reference_and_rejects_conflict(self) -> None:
        instance = _v2(block_size=8, trap_count=5, seed=7)
        trap_value = instance.coverage((0,))
        timed_out = Solution(
            algorithm="brute_force",
            selected=(0,),
            feasible_value=trap_value,
            runtime_seconds=0.01,
            status=SolutionStatus.TIMEOUT,
            best_bound=16,
        )
        rows = _rows_for_instance(
            case_name="timeout",
            repetition=0,
            instance=instance,
            solutions=[timed_out],
        )
        self.assertEqual(rows[0].status, SolutionStatus.TIMEOUT)
        self.assertEqual(rows[0].optimum, 16)
        self.assertEqual(rows[0].optimality_gap, (16 - trap_value) / 16)

        conflicting = Solution(
            algorithm="brute_force",
            selected=(0,),
            feasible_value=trap_value,
            runtime_seconds=0.01,
            status=SolutionStatus.OPTIMAL,
            best_bound=trap_value,
        )
        with self.assertRaisesRegex(ValueError, "conflicts with the instance certificate"):
            _rows_for_instance(
                case_name="conflict",
                repetition=0,
                instance=instance,
                solutions=[conflicting],
            )

    def test_certificate_rejects_timeout_bound_below_known_optimum(self) -> None:
        instance = _v2(block_size=8, trap_count=5, seed=7)
        timed_out = Solution(
            algorithm="brute_force",
            selected=(0,),
            feasible_value=instance.coverage((0,)),
            runtime_seconds=0.01,
            status=SolutionStatus.TIMEOUT,
            best_bound=15,
        )
        with self.assertRaisesRegex(ValueError, "best bound"):
            _rows_for_instance(
                case_name="invalid-bound",
                repetition=0,
                instance=instance,
                solutions=[timed_out],
            )

    def test_certificate_validator_rechecks_proof_and_selected_sets(self) -> None:
        instance = _v2(block_size=8, trap_count=5, seed=7)
        invalid = (
            KnownOptimumCertificate(16, (0,), "constructed_certificate", "covers_universe"),
            KnownOptimumCertificate(15, (1, 2), "constructed_certificate", "covers_universe"),
            KnownOptimumCertificate(16, (1, 2), "claimed", "covers_universe"),
            KnownOptimumCertificate(16, (1, 2), "constructed_certificate", "claimed"),
        )
        for certificate in invalid:
            with self.subTest(certificate=certificate):
                with self.assertRaises(ValueError):
                    validate_known_optimum_certificate(instance, certificate)

    def test_certificate_validator_rejects_non_integer_fields(self) -> None:
        instance = _v2(block_size=8, trap_count=5, seed=7)
        invalid = (
            KnownOptimumCertificate(
                16.0, (1, 2), "constructed_certificate", "covers_universe"
            ),
            KnownOptimumCertificate(
                True, (1, 2), "constructed_certificate", "covers_universe"
            ),
            KnownOptimumCertificate(
                16, (True, 2), "constructed_certificate", "covers_universe"
            ),
            KnownOptimumCertificate(
                16, (1.0, 2), "constructed_certificate", "covers_universe"
            ),
        )
        for certificate in invalid:
            with self.subTest(certificate=certificate):
                with self.assertRaises((TypeError, ValueError)):
                    validate_known_optimum_certificate(instance, certificate)

    def test_instance_record_rejects_non_integer_construction_version(self) -> None:
        cases = [
            {
                "name": "positive",
                "family": "adversarial",
                "block_size": 8,
                "distractor_count": 8,
                "construction_version": 2,
                "trap_count": 5,
            }
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(_config(cases)), encoding="utf-8")
            record = run_benchmark(config_path, root / "output").instances[0]
            parameters = json.loads(record.parameters)
            parameters["construction_version"] = 2.0
            with self.assertRaisesRegex(ValueError, "construction_version"):
                replace(record, parameters=canonical_json(parameters))


if __name__ == "__main__":
    unittest.main()
