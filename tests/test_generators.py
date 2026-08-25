from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.contracts import GeneratorSpec, ParameterSpec
from maxcover.generators import (
    GENERATORS,
    adversarial_greedy_trap,
    clustered,
    dominated_heavy,
    duplicate_heavy,
    fixed_size,
    from_spec,
    high_overlap,
    long_tail,
    mixed_cluster,
    uniform_random,
)
from maxcover.model import MaximumCoverageInstance


class GeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_specs = {
            "uniform": {
                "family": "uniform",
                "universe_size": 30,
                "set_count": 8,
                "k": 3,
                "density": 0.2,
            },
            "high_overlap": {
                "family": "high_overlap",
                "universe_size": 30,
                "set_count": 8,
                "k": 3,
                "core_fraction": 0.3,
                "core_probability": 0.8,
                "peripheral_probability": 0.05,
            },
            "clustered": {
                "family": "clustered",
                "universe_size": 30,
                "set_count": 8,
                "k": 3,
                "clusters": 3,
                "within_probability": 0.7,
                "outside_probability": 0.02,
            },
            "adversarial": {
                "family": "adversarial",
                "block_size": 20,
                "distractor_count": 5,
            },
            "fixed_size": {
                "family": "fixed_size",
                "universe_size": 30,
                "set_count": 8,
                "k": 3,
                "set_size": 5,
                "unique_sets": True,
            },
            "long_tail": {
                "family": "long_tail",
                "universe_size": 30,
                "set_count": 8,
                "k": 3,
                "set_size": 5,
                "gamma": 1.0,
            },
            "duplicate_heavy": {
                "family": "duplicate_heavy",
                "universe_size": 30,
                "base_set_count": 8,
                "k": 3,
                "set_size": 5,
                "copy_factor": 2,
            },
            "dominated_heavy": {
                "family": "dominated_heavy",
                "anchor_count": 6,
                "anchor_size": 5,
                "k": 3,
                "child_count": 2,
            },
            "mixed_cluster": {
                "family": "mixed_cluster",
                "universe_size": 40,
                "set_count": 8,
                "k": 3,
                "clusters": 4,
                "set_size": 5,
                "bridge_fraction": 0.5,
            },
        }

    def test_uniform_generator_is_deterministic(self) -> None:
        kwargs = dict(
            universe_size=30, set_count=8, k=3, density=0.2, seed=42
        )
        self.assertEqual(uniform_random(**kwargs), uniform_random(**kwargs))

    def test_generators_produce_valid_nonempty_sets(self) -> None:
        instances = [
            high_overlap(
                universe_size=50,
                set_count=10,
                k=3,
                core_fraction=0.3,
                core_probability=0.8,
                peripheral_probability=0.05,
                seed=4,
            ),
            clustered(
                universe_size=50,
                set_count=10,
                k=3,
                clusters=5,
                within_probability=0.7,
                outside_probability=0.02,
                seed=4,
            ),
        ]
        for instance in instances:
            self.assertTrue(all(candidate > 0 for candidate in instance.sets))
            self.assertTrue(all(mask.bit_length() <= instance.universe_size for mask in instance.sets))

    def test_registry_keys_match_spec_names_and_results(self) -> None:
        self.assertEqual(
            set(GENERATORS),
            {
                "uniform",
                "high_overlap",
                "clustered",
                "adversarial",
                "fixed_size",
                "long_tail",
                "duplicate_heavy",
                "dominated_heavy",
                "mixed_cluster",
            },
        )
        for family, specification in GENERATORS.items():
            with self.subTest(family=family):
                self.assertEqual(specification.name, family)
                instance = from_spec(self.valid_specs[family], seed=17)
                self.assertEqual(instance.family, family)
                self.assertEqual(instance.seed, 17)

    def test_registry_and_direct_calls_are_equivalent(self) -> None:
        seed = 23
        direct_instances = {
            "uniform": uniform_random(
                universe_size=30,
                set_count=8,
                k=3,
                density=0.2,
                seed=seed,
            ),
            "high_overlap": high_overlap(
                universe_size=30,
                set_count=8,
                k=3,
                core_fraction=0.3,
                core_probability=0.8,
                peripheral_probability=0.05,
                seed=seed,
            ),
            "clustered": clustered(
                universe_size=30,
                set_count=8,
                k=3,
                clusters=3,
                within_probability=0.7,
                outside_probability=0.02,
                seed=seed,
            ),
            "adversarial": adversarial_greedy_trap(
                block_size=20,
                distractor_count=5,
                seed=seed,
            ),
            "fixed_size": fixed_size(
                universe_size=30,
                set_count=8,
                k=3,
                set_size=5,
                unique_sets=True,
                seed=seed,
            ),
            "long_tail": long_tail(
                universe_size=30,
                set_count=8,
                k=3,
                set_size=5,
                gamma=1.0,
                seed=seed,
            ),
            "duplicate_heavy": duplicate_heavy(
                universe_size=30,
                base_set_count=8,
                k=3,
                set_size=5,
                copy_factor=2,
                seed=seed,
            ),
            "dominated_heavy": dominated_heavy(
                anchor_count=6,
                anchor_size=5,
                k=3,
                child_count=2,
                seed=seed,
            ),
            "mixed_cluster": mixed_cluster(
                universe_size=40,
                set_count=8,
                k=3,
                clusters=4,
                set_size=5,
                bridge_fraction=0.5,
                seed=seed,
            ),
        }
        for family, expected in direct_instances.items():
            with self.subTest(family=family):
                self.assertEqual(from_spec(self.valid_specs[family], seed), expected)

    def test_adversarial_optional_default_is_preserved(self) -> None:
        instance = from_spec(
            {"family": "adversarial", "block_size": 20}, seed=5
        )
        expected = adversarial_greedy_trap(
            block_size=20, distractor_count=4, seed=5
        )
        self.assertEqual(instance, expected)
        self.assertEqual(instance.parameters["distractor_count"], 4)

    def test_from_spec_does_not_mutate_input(self) -> None:
        specification = copy.deepcopy(self.valid_specs["uniform"])
        original = copy.deepcopy(specification)
        from_spec(specification, seed=8)
        self.assertEqual(specification, original)

    def test_configuration_shape_errors_are_explicit(self) -> None:
        invalid_specs = [
            ({}, "missing required field 'family'"),
            ({"family": "missing"}, "unknown instance family"),
            ({"family": 7}, "field 'family' must be a string"),
            (
                {
                    **self.valid_specs["uniform"],
                    "unexpected": 1,
                },
                "unknown parameter",
            ),
            (
                {
                    key: value
                    for key, value in self.valid_specs["uniform"].items()
                    if key != "density"
                },
                "missing required parameter",
            ),
            (
                {**self.valid_specs["uniform"], "density": "0.2"},
                "parameter 'density' must be number",
            ),
            (
                {**self.valid_specs["uniform"], "universe_size": True},
                "parameter 'universe_size' must be integer",
            ),
        ]
        for specification, message in invalid_specs:
            with self.subTest(specification=specification):
                with self.assertRaisesRegex(ValueError, message):
                    from_spec(specification, seed=1)

        with self.assertRaisesRegex(ValueError, "specification must be a mapping"):
            from_spec([], seed=1)
        with self.assertRaisesRegex(ValueError, "parameter 'seed' must be integer"):
            from_spec(self.valid_specs["uniform"], seed=True)

    def test_standard_dimension_boundaries_are_rejected(self) -> None:
        invalid_dimensions = [
            {"universe_size": 0, "set_count": 8, "k": 3},
            {"universe_size": 30, "set_count": 0, "k": 1},
            {"universe_size": 30, "set_count": 8, "k": 0},
            {"universe_size": 30, "set_count": 8, "k": 9},
            {"universe_size": 30, "set_count": 8, "k": True},
        ]
        for dimensions in invalid_dimensions:
            with self.subTest(dimensions=dimensions):
                with self.assertRaises(ValueError):
                    uniform_random(**dimensions, density=0.2, seed=1)
        with self.assertRaises(ValueError):
            uniform_random(
                universe_size=30,
                set_count=8,
                k=3,
                density=0.2,
                seed=True,
            )

    def test_probability_boundaries_are_enforced(self) -> None:
        with self.assertRaises(ValueError):
            uniform_random(
                universe_size=20, set_count=6, k=2, density=0, seed=1
            )
        with self.assertRaises(ValueError):
            uniform_random(
                universe_size=20, set_count=6, k=2, density=1.01, seed=1
            )
        with self.assertRaises(ValueError):
            high_overlap(
                universe_size=20,
                set_count=6,
                k=2,
                core_fraction=0,
                core_probability=0.5,
                peripheral_probability=0.1,
                seed=1,
            )
        for field, value in (
            ("core_probability", -0.01),
            ("peripheral_probability", 1.01),
        ):
            parameters = {
                "universe_size": 20,
                "set_count": 6,
                "k": 2,
                "core_fraction": 0.3,
                "core_probability": 0.5,
                "peripheral_probability": 0.1,
                "seed": 1,
            }
            parameters[field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    high_overlap(**parameters)

        # Ordinary probabilities accept the JSON integer boundaries 0 and 1.
        high_overlap(
            universe_size=20,
            set_count=6,
            k=2,
            core_fraction=1,
            core_probability=0,
            peripheral_probability=1,
            seed=1,
        )
        clustered(
            universe_size=20,
            set_count=6,
            k=2,
            clusters=2,
            within_probability=0,
            outside_probability=1,
            seed=1,
        )

    def test_cluster_and_adversarial_boundaries_are_rejected(self) -> None:
        for clusters in (1, 21, True):
            with self.subTest(clusters=clusters):
                with self.assertRaises(ValueError):
                    clustered(
                        universe_size=20,
                        set_count=6,
                        k=2,
                        clusters=clusters,
                        within_probability=0.5,
                        outside_probability=0.1,
                        seed=1,
                    )
        with self.assertRaises(ValueError):
            adversarial_greedy_trap(block_size=3, seed=1)
        with self.assertRaises(ValueError):
            adversarial_greedy_trap(
                block_size=20, distractor_count=-1, seed=1
            )

    def test_generator_contract_detects_wrong_family_and_seed(self) -> None:
        def wrong_family(*, seed):
            return MaximumCoverageInstance(
                universe_size=1,
                sets=(1,),
                k=1,
                family="wrong",
                seed=seed,
            )

        family_spec = GeneratorSpec(
            name="expected", factory=wrong_family, parameters={}
        )
        with self.assertRaisesRegex(RuntimeError, "returned family"):
            family_spec.generate({}, seed=1)

        def wrong_seed(*, seed):
            return MaximumCoverageInstance(
                universe_size=1,
                sets=(1,),
                k=1,
                family="expected",
                seed=seed + 1,
            )

        seed_spec = GeneratorSpec(
            name="expected", factory=wrong_seed, parameters={}
        )
        with self.assertRaisesRegex(RuntimeError, "returned seed"):
            seed_spec.generate({}, seed=1)

    def test_derived_generator_parameters_require_preflight_defaults(self) -> None:
        def factory(*, context, seed):
            return MaximumCoverageInstance(
                universe_size=1,
                sets=(1,),
                k=1,
                family="expected",
                seed=seed,
                parameters={"context": context},
            )

        with self.assertRaisesRegex(ValueError, "derived parameters must have defaults"):
            GeneratorSpec(
                name="expected",
                factory=factory,
                parameters={},
                derived_parameters={"context": ParameterSpec((int,), "integer")},
            )


if __name__ == "__main__":
    unittest.main()
