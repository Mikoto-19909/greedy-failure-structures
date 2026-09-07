import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from r3_feasibility import construct, evaluate, exposure
from validate_r3_feasibility import replay, exact_values, local_intersections
from validate_greedy_failure_paths import compare


class R3FeasibilityTests(unittest.TestCase):
    def test_valid_switches_and_damaged_endpoints(self):
        original = [[0, 1], [0, 2], [0, 3], [1, 2]]
        for direction in (-1, 1):
            actual = construct(original, 4, 876, direction, [16, 128])
            for endpoint in actual["endpoints"]:
                endpoint["values"] = evaluate(endpoint["sets"], 4, 2)
            expected = replay(original, 4, 876, direction, [16, 128], 2)
            compare(actual, expected, "valid chain")
            for change in ("exposure", "sets", "forced_optimum", "accepted"):
                damaged = copy.deepcopy(actual)
                end = damaged["endpoints"][-1]
                if change == "sets":
                    end["sets"][0] = []
                elif change == "forced_optimum":
                    end["values"]["forced_optimum"] += 1
                else:
                    end[change] += 1
                with self.subTest(direction=direction, change=change), self.assertRaises(ValueError):
                    compare(damaged, expected, "damaged chain")

    def test_equal_column_degrees_cannot_change_exposure(self):
        original = [[0, 1], [1, 2], [2, 3], [0, 3]]
        self.assertEqual(exposure(original, [2, 2, 2, 2]), 2)
        for direction in (-1, 1):
            chain = construct(original, 4, 999, direction, [64, 256])
            self.assertTrue(all(e["exposure"] == 2 for e in chain["endpoints"]))

    def test_first_loss_is_distinct_from_final_failure(self):
        original = [[0, 1], [0, 2], [1, 3]]
        self.assertEqual(evaluate(original, 4, 2), exact_values(original, 2))
        self.assertEqual(evaluate(original, 4, 2)["forced_optimum"], 3)
        self.assertEqual(evaluate(original, 4, 2)["optimum"], 4)
        later_failure = evaluate([[0, 1], [2, 4], [2, 3], [4, 5]], 6, 3)
        self.assertFalse(later_failure["first_loss"])
        self.assertLess(later_failure["greedy"], later_failure["optimum"])
        with self.assertRaises(ValueError):
            construct(original, 4, 1, 0, [10])
