"""Small known answers and independent rejection checks for the live study.

Only temporary miniature runs are produced; the saved formal experiments stay intact.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import csv
from fractions import Fraction as Q
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / 'independent_research/online_matching_recourse'
EXTENSION = STUDY / 'extension_20260925'


def load_script(relative):
    source = STUDY / relative
    spec = importlib.util.spec_from_file_location('matching_check_' + source.stem, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with patch.object(sys, 'path', [str(EXTENSION), str(STUDY), *sys.path]):
        spec.loader.exec_module(module)
    return module


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


class OnlineMatchingResearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def invoke(self, module, *arguments):
        with patch.object(sys, 'argv', [module.__file__, *map(str, arguments)]), redirect_stdout(io.StringIO()):
            module.main()

    def tiny_run(self):
        folder = self.root / 'study'
        folder.mkdir()
        case = dict(id='tiny', split='dev', family='tiny', servers=[0, 3, 5],
                    requests=[2, 3, 0], order=[0, 1, 2])
        write_json(folder / 'inputs.json', dict(seed=7, cases=[case]))
        write_json(folder / 'input_manifest.json', dict(
            input_sha256=hashlib.sha256((folder / 'inputs.json').read_bytes()).hexdigest(),
            seed=7, cases=1, development=1, evaluation=0))
        for name in ('protocol.md', 'matching.py', 'run.py'):
            shutil.copyfile(STUDY / name, folder / name)
        runner = load_script('run.py')
        with patch.object(runner, 'ROOT', folder):
            self.invoke(runner, '--split', 'dev')
        out, = (folder / 'output').iterdir()
        verifier = load_script('verify.py')
        with patch.object(verifier, 'ROOT', folder):
            self.invoke(verifier, out)
        return folder, out, verifier

    def test_matching_policies_and_independent_trace_rejection(self):
        fixtures = load_script('fixtures.py')
        self.assertEqual(fixtures.build(), json.loads((STUDY / 'inputs.json').read_text(encoding='utf-8')))
        hand_checks = unittest.defaultTestLoader.loadTestsFromModule(load_script('test_matching.py'))
        result = unittest.TextTestRunner(stream=io.StringIO()).run(hand_checks)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        folder, out, verifier = self.tiny_run()
        record = json.loads((out / 'verification.json').read_text())
        self.assertEqual(record['counts']['cases'], 1)
        self.assertEqual(record['counts']['traces'], 8)
        traces = json.loads((out / 'traces.json').read_text())
        self.assertEqual(traces[-1]['oracle_costs'], [1, 2, 3])
        traces[0]['history'][0]['cost'] += 1
        write_json(out / 'traces.json', traces)
        with patch.object(verifier, 'ROOT', folder), self.assertRaisesRegex(ValueError, 'cost'):
            self.invoke(verifier, out)

    def test_three_point_known_value_and_missing_future_rejected(self):
        verifier = load_script('verify_three_point.py')
        value, objectives = verifier.audit_prefix((0, 3, 5), 2, 3, range(6))
        self.assertEqual(value, 1)
        self.assertEqual(objectives[(0, 1)], 4)
        with self.assertRaises((AssertionError, ValueError)):
            verifier.audit_prefix((0, 3, 5), 2, 3, [])

    def test_chain_and_free_first_known_values_and_illegal_actions(self):
        chain = load_script('extension_20260925/chain_first.py')
        for mode, expected in [('chain', (Q(5, 2), (0, 1))), ('atomic', (Q(3, 2), (1, 0)))]:
            with self.subTest(mode=mode):
                best, _ = chain.prefix((0, 2, 6), Q(5, 4), 2, mode=mode)
                self.assertEqual(best[:2], expected)
                self.assertEqual(chain.brute_prefix((0, 2, 6), Q(5, 4), Q(2), 1,
                    [Q(i, 4) for i in range(25)], mode), expected)
        first, values = chain.free_first((0, 3, 6), Q(7, 4))
        self.assertEqual(first, 0)
        self.assertEqual([row['value'] for row in values], [1, Q(5, 2), Q(11, 2)])
        self.assertNotIn((0, 1, 2), chain.actions((1, 0), (1, 0), 'atomic'))
        self.assertNotIn((1, 0, 2), chain.actions((0, 1), (0, 0), 'chain'))
        for mode in ('atomic', 'chain'):
            self.assertEqual(set(chain.actions((0, 1), (1, 0), mode)),
                             set(chain.brute_actions((0, 1), (1, 0), mode)))

    def test_randomized_raw_game_known_certificate_and_nonfinite_input(self):
        raw = load_script('extension_20260925/random_raw.py')
        game = raw.game(raw.np.array([[58., 64.], [62., 56.]]))
        self.assertAlmostEqual(game['value'], 60)
        for actual, expected in zip(game['policy'], (0.5, 0.5)):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(game['adversary'], (2/3, 1/3)):
            self.assertAlmostEqual(actual, expected)
        example = raw.example((0, 10, 50), 6, 10)
        self.assertEqual(example['raw_deterministic'], 62)
        self.assertAlmostEqual(example['raw_randomized']['value'], 60)
        self.assertAlmostEqual(example['excess_randomized']['value'], 8)
        with self.assertRaises(ValueError):
            raw.game(raw.np.array([[float('nan'), 1.], [2., 3.]]))

    def test_ablation_tiny_trajectory_and_corrupt_or_incomplete_output(self):
        ablation = load_script('extension_20260925/ablation.py')
        verifier = load_script('extension_20260925/verify_ablation.py')
        case = dict(id='tiny', split='tiny', family='tiny', servers=[0, 3, 5],
                    requests=[2, 3, 0], order=[0, 1, 2])
        history = ablation.simulate(case, 2, 2, Q(0))
        self.assertEqual([step['cost'] for step in history], [1, 2, 3])
        row = dict(case_id='tiny', split='tiny', family='tiny', chain_limit=2, weight='0', budget=2,
                   prefix_sum=6, final_cost=3, optimum_prefix_sum=6, total_recourse=2,
                   max_request_recourse=2, cpu_seconds=0., wall_seconds=0.)
        group = dict(split='tiny', chain_limit=2, weight='0', budget=2,
                     count=1, prefix_sum=6, total_recourse=2, cpu_seconds=0.)
        oracle = [dict(t=1, optimum=1, possible_first_servers=[3]),
                  dict(t=2, optimum=2, possible_first_servers=[0]),
                  dict(t=3, optimum=3, possible_first_servers=[3, 5])]
        self.assertEqual(ablation.oracle_and_signs(case), oracle)
        for name in ('20260924T175730918352Z-dev', '20260924T175731049376Z-eval'):
            folder = self.root / 'output' / name
            folder.mkdir(parents=True)
            write_json(folder / 'traces.json', [])
        out = self.root / 'ablation'
        out.mkdir()

        def save(history, row, group):
            for name, value in {'inputs.json': {'cases': [case]}, 'oracle.json': {'tiny': oracle},
                                'traces.json': [dict(row, history=history)],
                                'summary.json': {'groups': [group]}}.items():
                write_json(out / name, value)
            with (out / 'metrics.csv').open('w', newline='', encoding='utf-8-sig') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader(); writer.writerow(row)

        with patch.object(verifier, 'ROOT', self.root / 'extension'):
            save(history, row, group)
            self.invoke(verifier, out)
            self.assertEqual(json.loads((out / 'verification.json').read_text())['stages'], 3)
            corrupt = deepcopy(history); corrupt[1]['cost'] += 1
            save(corrupt, row, group)
            with self.assertRaises(AssertionError):
                self.invoke(verifier, out)
            save(history[:-1], dict(row, prefix_sum=3, final_cost=2, total_recourse=1, max_request_recourse=1),
                 dict(group, prefix_sum=3, total_recourse=1))
            with self.assertRaisesRegex(AssertionError, 'incomplete trajectory'):
                self.invoke(verifier, out)
            corrupt = deepcopy(history); corrupt[1]['t'] = 99
            save(corrupt, row, group)
            with self.assertRaisesRegex(AssertionError, 'nonconsecutive stage'):
                self.invoke(verifier, out)

    def test_four_arrival_known_values_and_corrupt_or_incomplete_witness(self):
        producer = load_script('extension_20260925/four_request_game.py')
        verifier = load_script('extension_20260925/verify_four_game.py')
        online = producer.solve(1, 'chain', alphabet=(0,))
        known = producer.solve(1, 'atomic', known_sequence=(0, -1, 2, -4))
        self.assertEqual((online['value'], known['value']), (0, 2))
        summary = dict(servers=list(producer.SERVERS), future_alphabet=[0], horizon=4,
                       results=[online], hindsight_fixed_sequence=[known])
        source = self.root / 'summary.json'
        write_json(source, summary)
        with redirect_stdout(io.StringIO()):
            verifier.verify(source, cpu_limit=10)
        checked = json.loads((self.root / 'verification.json').read_text())
        self.assertEqual([row['witness_stages_verified'] for row in checked['results']], [4, 4])
        corrupt = deepcopy(summary); corrupt['hindsight_fixed_sequence'][0]['witness'][1]['cost'] += 1
        short = deepcopy(summary); short['results'][0]['witness'].pop()
        empty = dict(summary, results=[], hindsight_fixed_sequence=[])
        for bad in (corrupt, short, empty):
            with self.subTest(kind=bad), self.assertRaises(AssertionError), redirect_stdout(io.StringIO()):
                write_json(source, bad)
                verifier.verify(source, cpu_limit=10)

    def test_continuous_rounding_known_bounds_and_corrupt_certificate(self):
        continuous = load_script('extension_20260925/continuous_four_bounds.py')
        verifier = load_script('extension_20260925/verify_four_game.py')
        self.assertEqual(continuous.round_request(Q(51, 10), first=True), 6)
        self.assertEqual(continuous.round_request(Q(51, 10)), 5)
        nearest = lambda x: min(continuous.SERVERS, key=lambda s: (abs(x-s), s))
        for x in [Q(i, 10) for i in range(-40, 81)]:
            rounded = continuous.round_request(x, first=True)
            self.assertEqual(nearest(rounded), nearest(x))
            self.assertLessEqual(abs(x-rounded), 1)
            self.assertLessEqual(abs(x-continuous.round_request(x)), Q(1, 2))
        values = {('atomic', 1): 9, ('atomic', 2): 2, ('chain', 1): 11, ('chain', 2): 4}

        def solved(budget, model, alphabet):
            self.assertEqual(alphabet, tuple(range(-4, 9)))
            return dict(model=model, budget=budget, value=values[model, budget], states=1)

        # Exercise bound assembly with controlled solver answers, not the full 13-point game.
        with patch.object(continuous, 'ROOT', self.root), patch.object(continuous, 'solve', side_effect=solved):
            self.invoke(continuous)
        source, = (self.root / 'output').glob('*/summary.json')
        summary = json.loads(source.read_text())
        verifier.verify_rounding(summary)
        self.assertEqual([row['upper'] for row in summary['continuous_intervals']], [21, 14, 23, 16])
        for field in ('upper', 'certificate', 'missing'):
            bad = deepcopy(summary)
            if field == 'upper': bad['continuous_intervals'][0]['upper'] += 1
            elif field == 'certificate': bad['rounding']['additive_certificate'] += 1
            else: bad['continuous_intervals'].pop()
            with self.subTest(field=field), self.assertRaises(AssertionError):
                write_json(source, bad)
                verifier.verify(source, cpu_limit=1)

    def test_long_sequence_reset_and_independent_rejection(self):
        producer = load_script('extension_20260925/long_sequence.py')
        verifier = load_script('extension_20260925/verify_long_sequence.py')
        result = producer.run([-4, -1, 2, 8], [0, -1, 2, -4], 2, [2, 4])
        self.assertEqual([Q(row['cost']) for row in result['trace']], [1, 2, 8, 8])
        # At stage three the transfer bound is tight: residual 6 = optimum 4 + frozen 2.
        third = result['trace'][2]
        self.assertEqual([Q(third[key]) for key in ('residual_optimum', 'optimum', 'frozen_cost')], [6, 4, 2])
        self.assertEqual(verifier.verify(result)['prefixes'], 4)
        self.assertEqual(verifier.verify(producer.run([0, 3, 5], [2, 3, 0], 0))['maximum_recourse'], 0)
        corrupt = deepcopy(result); corrupt['trace'][2]['cost'] = '9'
        counts = deepcopy(result); counts['trace'][1]['recourse'][0] = 0
        short = deepcopy(result); short['trace'].pop()
        for bad in (corrupt, counts, short):
            with self.assertRaises((AssertionError, ValueError)):
                verifier.verify(bad)
        stream = producer.RestartMatcher([0, 3, 5], 1)
        stream.arrive(2)
        stream.arrive(3, reset=True)
        with self.assertRaisesRegex(ValueError, 'budget'):
            stream.arrive(0, reset=True)
        self.assertEqual(len(stream.requests), 2)

        threshold = producer.run([0, 2, 5], [1, 0, 5], 1, trigger_ratio=2)
        self.assertEqual([Q(row['cost']) for row in threshold['trace']], [1, 1, 1])
        self.assertEqual(verifier.verify(threshold)['resets'], 1)

    def test_continuous_four_rational_witnesses_and_action_sets(self):
        producer = load_script('extension_20260925/four_exact.py')
        verifier = load_script('extension_20260925/verify_four_exact.py')
        records = json.loads((ROOT / 'tests/fixtures/online_matching/four_exact_lower.json').read_text())
        for record, expected in zip(records, ('9', '3')):
            self.assertEqual(verifier.verify(record)['guaranteed_excess'], expected)
            missing = deepcopy(record); missing['witness']['third'].pop()
            wrong = deepcopy(record); wrong['bound'] = str(Q(expected) + 1)
            unknown = dict(record, status='unknown')
            for bad in (missing, wrong, unknown):
                with self.assertRaises((AssertionError, ValueError)):
                    verifier.verify(bad)
        # Reachable action sets: path-following and an independent graph check.
        for budget in (1, 2):
            for model in ('atomic', 'chain'):
                states = {((), ())}
                for _ in range(4):
                    following = set()
                    for old, used in states:
                        actions = producer.actions(old, used, budget, model)
                        self.assertEqual(set(actions), set(verifier._legal(old, used, budget, model)))
                        following.update(actions)
                    states = following

    def test_local_blocks_budget_and_independent_rejection(self):
        producer = load_script('extension_20260925/local_freeze.py')
        verifier = load_script('extension_20260925/verify_local_freeze.py')
        study = load_script('extension_20260925/local_freeze_study.py')
        cases = study.fixed_cases()
        self.assertEqual(len(cases), 9)
        self.assertEqual(cases[-1]['requests'], [5, 2, -1, -4, 105, 102, 99, 96])
        data = producer.run([0, 2, 100, 102], [1, 0, 101, 100], 1)
        self.assertEqual([Q(row['cost']) for row in data['trace']], [1, 1, 2, 2])
        self.assertEqual(producer.metrics(data)['repair_arrivals'], 2)
        self.assertEqual(verifier.verify(data)['maximum_recourse'], 1)
        fixed = producer.run([-4, -1, 2, 8], [Q(1, 2), -1, 2, -4], 2, 4)
        self.assertEqual(verifier.verify(fixed)['maximum_frozen_loss'], '9')
        self.assertEqual(producer.metrics(fixed)['excess_sum'], '9')
        repaired = producer.run([-4, -1, 2, 8], [Q(1, 2), -1, 2, -4], 2)
        self.assertEqual(verifier.verify(repaired)['maximum_frozen_loss'], '0')
        for row in repaired['trace']:
            self.assertLessEqual(Q(row['cost']), Q(row['shadow_cost']))
        cost = deepcopy(data); cost['trace'][-1]['cost'] = '999'
        short = deepcopy(data); short['trace'].pop()
        counts = deepcopy(data); counts['trace'][1]['counts'][0] = 0
        route = deepcopy(data); route['trace'][1]['block'] = 1
        shadow = deepcopy(data); shadow['shadow']['trace'][0]['cost'] = '2'
        for bad in (cost, short, counts, route, shadow):
            with self.assertRaises((AssertionError, ValueError)):
                verifier.verify(bad)
        with self.assertRaises(ValueError):
            producer.LocalMatcher([0, 1], 1, 5)

    def test_explicit_four_budget2_policy_and_independent_rejection(self):
        producer = load_script('extension_20260925/four_budget2_policy.py')
        verifier = load_script('extension_20260925/verify_four_budget2_policy.py')
        lower = producer.run([Q(1, 2), -1, 2, -4])
        self.assertEqual(lower['excess_sum'], '3')
        self.assertEqual([Q(row['cost']) for row in lower['trace']], [Q(3, 2), Q(9, 2), Q(9, 2), Q(15, 2)])
        self.assertTrue(verifier.verify(lower)['verified'])
        anchor = producer.run([6, 7, 8, -4])
        self.assertEqual(anchor['excess_sum'], '0')
        self.assertTrue(verifier.verify(anchor)['anchored'])
        self.assertEqual([row['assignment'][0] for row in anchor['trace']], [3, 2, 2, 2])
        for prefix in ((5, 6), (6, 6)):
            boundary = producer.run([*prefix, -4, 8])
            self.assertFalse(verifier.verify(boundary)['anchored'])
        other_future = producer.run([Q(1, 2), -1, 8, 8])
        self.assertEqual(lower['trace'][:2], other_future['trace'][:2])
        same_coordinates = producer.run([8] * 4)
        self.assertEqual(verifier.verify(same_coordinates)['maximum_recourse'], 2)
        # The announced model permits a swap cycle separate from the new arrival.
        cycle = producer.run([Q(1, 2), 0, 8, -4])
        chain = load_script('extension_20260925/four_exact.py').chain
        self.assertFalse(chain(tuple(cycle['trace'][1]['assignment']), tuple(cycle['trace'][2]['assignment'])))
        cost = deepcopy(lower); cost['trace'][1]['cost'] = '999'
        short = deepcopy(lower); short['trace'].pop()
        counts = deepcopy(lower); counts['trace'][-1]['counts'][0] = 3
        scope = dict(lower, model='chain')
        for bad in (cost, short, counts, scope):
            with self.assertRaises((AssertionError, ValueError)):
                verifier.verify(bad)
        stream = producer.FourBudgetTwo()
        stream.arrive(6)
        before = deepcopy(stream.__dict__)
        with self.assertRaisesRegex(ValueError, 'interval|lie'):
            stream.arrive(9)
        self.assertEqual(stream.__dict__, before)
        for request in (7, 8, -4):
            stream.arrive(request)
        with self.assertRaisesRegex(ValueError, 'four'):
            stream.arrive(0)
        with self.assertRaisesRegex(ValueError, 'four'):
            producer.run([1, 2, 3])

    def test_result_note_preserves_data_without_a_package_integrity_gate(self):
        _, out, _ = self.tiny_run()
        before = (out / 'summary.json').read_bytes()
        self.invoke(load_script('finalize.py'), out)
        self.assertTrue((out / '结果说明.md').is_file())
        self.assertTrue((out / 'protocol_snapshot.md').is_file())
        self.assertEqual((out / 'summary.json').read_bytes(), before)
        for name in ('artifact_hashes.json', 'claims.csv', 'delivery_checks.json'):
            self.assertFalse((out / name).exists(), name)


if __name__ == '__main__':
    unittest.main()
