"""Meaningful hand-calculation checks; all examples reuse the frozen development cases."""
import json
from pathlib import Path
import unittest
from matching import exact_prefix, simulate

CASES = {c['id']: c for c in json.loads(Path(__file__).with_name('inputs.json').read_text())['cases']}


class MatchingChecks(unittest.TestCase):
    def history(self, name, policy, budget):
        c = CASES[name]
        return simulate(c['servers'], [c['requests'][i] for i in c['order']], policy, budget)

    def test_first_assignment_free_and_pair_exact(self):
        h = self.history('dev_pair', 'single', 1)
        self.assertEqual([x['cost'] for x in h], [4, 7, 11, 14, 18, 21])
        self.assertEqual(h[-1]['counts'], [1, 0, 1, 0, 1, 0])
        self.assertEqual(h[0]['moves'], [])

    def test_budget_lock_and_reservation(self):
        one = self.history('dev_budget', 'single', 1)
        two = self.history('dev_budget', 'single', 2)
        priced = self.history('dev_budget', 'priced_chain', 1)
        self.assertEqual([h['cost'] for h in one[:3]], [1, 2, 7])
        self.assertEqual([h['cost'] for h in two[:3]], [1, 2, 3])
        self.assertEqual([h['cost'] for h in priced[:3]], [1, 3, 3])
        self.assertEqual(two[2]['counts'], [2, 0, 0])

    def test_long_chain_unlocks_line(self):
        one = self.history('dev_uniform', 'single', 4)
        chain = self.history('dev_uniform', 'priced_chain', 1)
        self.assertEqual(one[-1]['cost'], 61)
        self.assertEqual(chain[-1]['cost'], 31)
        self.assertEqual(len(chain[-1]['moves']), 5)

    def test_prefix_optimum_hand_values(self):
        c = CASES['dev_budget']
        self.assertEqual([exact_prefix(c['servers'], c['requests'][:t]) for t in range(1, 4)], [1, 2, 3])


if __name__ == '__main__':
    unittest.main()
