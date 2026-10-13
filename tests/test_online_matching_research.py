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
import os
from pathlib import Path
import shutil
import subprocess
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

    def ablation_run(self):
        producer = load_script('extension_20260925/ablation.py')
        verifier = load_script('extension_20260925/verify_ablation.py')
        extension = self.root / 'extension'
        (extension / '过程').mkdir(parents=True)
        (extension / '过程/分支3与4协议.md').write_text('Temporary small-input protocol.', encoding='utf-8')
        cases = [dict(id=split+'_tiny', split=split, family='tiny', servers=[0, 3, 5],
                      requests=[2, 3, 0], order=[0, 1, 2]) for split in ('dev', 'eval')]
        write_json(self.root / 'inputs.json', {'cases': cases})
        write_json(self.root / 'input_manifest.json', {
            'input_sha256': hashlib.sha256((self.root / 'inputs.json').read_bytes()).hexdigest()})
        for split, name in [('dev', '20260924T175730918352Z-dev'), ('eval', '20260924T175731049376Z-eval')]:
            folder = self.root / 'output' / name
            folder.mkdir(parents=True)
            case = next(c for c in cases if c['split'] == split)
            rows = [dict(case_id=case['id'], policy=policy, budget=budget,
                         history=producer.simulate(case, budget, limit, weight))
                    for policy, limit, weight in [('single', 1, Q(0)), ('priced_chain', 5, Q(1, 2))]
                    for budget in (1, 2, 4)]
            write_json(folder / 'traces.json', rows)
        with patch.object(producer, 'ROOT', extension):
            self.invoke(producer)
        out, = (extension / 'output').iterdir()
        payload = {name: json.loads((out / (name+'.json')).read_text())
                   for name in ('inputs', 'oracle', 'traces', 'summary')}
        payload['metrics'] = [{k: v for k, v in row.items() if k != 'history'} for row in payload['traces']]
        # The formal producer declares 6/24 fixed cases; this temporary fixture
        # substitutes one case per split while retaining all stress/config rows.
        payload['summary'].update(development_count=1, fixed_comparison_count=1)
        self.save_ablation(out, payload)
        return extension, out, verifier, payload

    def save_ablation(self, out, payload):
        for name in ('inputs', 'oracle', 'traces', 'summary'):
            write_json(out / (name+'.json'), payload[name])
        with (out / 'metrics.csv').open('w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(payload['metrics'][0]))
            writer.writeheader()
            writer.writerows(payload['metrics'])

    def filter_ablation(self, payload, keep):
        payload['traces'] = [row for row in payload['traces'] if keep(row)]
        payload['metrics'] = [row for row in payload['metrics'] if keep(row)]
        groups = []
        for group in payload['summary']['groups']:
            rows = [row for row in payload['traces'] if all(row[k] == group[k]
                    for k in ('split', 'chain_limit', 'weight', 'budget'))]
            if rows:
                group['count'] = len(rows)
                for field in ('prefix_sum', 'total_recourse', 'cpu_seconds'):
                    group[field] = sum(row[field] for row in rows)
                groups.append(group)
        payload['summary']['groups'] = groups

    def four_game_summary(self, alphabet=(0,)):
        producer = load_script('extension_20260925/four_request_game.py')
        summary = dict(servers=list(producer.SERVERS), future_alphabet=list(alphabet), horizon=4,
                       results=[producer.solve(budget, model, alphabet=alphabet)
                                for model in ('atomic', 'chain') for budget in (1, 2, 4)],
                       hindsight_fixed_sequence=[producer.solve(budget, 'atomic', known_sequence=(0, -1, 2, -4))
                                                  for budget in (1, 2, 4)])
        return producer, load_script('extension_20260925/verify_four_game.py'), summary

    def verify_game(self, verifier, summary):
        source = self.root / 'summary.json'
        write_json(source, summary)
        with patch.object(verifier, 'ALPHABET', tuple(summary['future_alphabet'])), redirect_stdout(io.StringIO()):
            verifier.verify(source, cpu_limit=120)

    def optimized_verify(self, mode, script, source, passed, message=None):
        environment = dict(os.environ)
        environment.pop('PYTHONOPTIMIZE', None)
        flags = ['-O', '-B'] if mode == 'flag' else ['-B']
        if mode == 'environment': environment['PYTHONOPTIMIZE'] = '1'
        certificate = source / 'verification.json' if source.is_dir() else source.parent / 'verification.json'
        certificate.unlink(missing_ok=True)
        result = subprocess.run([sys.executable, *flags, str(script), str(source)],
                                env=environment, capture_output=True, text=True, timeout=180)
        if passed:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(certificate.exists())
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertFalse(certificate.exists(), result.stdout)
            if message: self.assertIn(message, result.stderr)

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

    def test_primary_manifest_accepts_line_endings_but_rejects_changed_fields(self):
        verifier = load_script('verify.py')
        for split, name, traces in [('dev', '20260924T175730918352Z-dev', 48),
                                    ('eval', '20260924T175731049376Z-eval', 192)]:
            out = self.root / name; out.mkdir()
            for file in ('inputs.json', 'input_manifest.json', 'traces.json', 'summary.json', 'metrics.csv'):
                shutil.copyfile(STUDY / 'output' / name / file, out / file)
            self.assertIn(b'\r\n', (out / 'input_manifest.json').read_bytes())
            self.invoke(verifier, out)
            checked = json.loads((out / 'verification.json').read_text())
            self.assertEqual((checked['split'], checked['counts']['traces']), (split, traces))
        folder, out, verifier = self.tiny_run()
        baseline = json.loads((out / 'input_manifest.json').read_text())
        (out / 'input_manifest.json').write_bytes((folder / 'input_manifest.json').read_bytes().replace(b'\n', b'\r\n'))
        with patch.object(verifier, 'ROOT', folder):
            self.invoke(verifier, out)
            for field in ('input_sha256', 'seed', 'cases', 'development', 'evaluation', 'extra'):
                bad = deepcopy(baseline); bad[field] = 'wrong'
                write_json(out / 'input_manifest.json', bad)
                (out / 'verification.json').unlink(missing_ok=True)
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'frozen input_manifest'):
                    self.invoke(verifier, out)
                self.assertFalse((out / 'verification.json').exists())
        shutil.copyfile(STUDY / 'verify.py', folder / 'verify.py')
        for mode in ('flag', 'environment'):
            (out / 'input_manifest.json').write_bytes((folder / 'input_manifest.json').read_bytes().replace(b'\n', b'\r\n'))
            self.optimized_verify(mode, folder / 'verify.py', out, True)
            bad = deepcopy(baseline); bad['input_sha256'] = 'wrong'
            write_json(out / 'input_manifest.json', bad)
            self.optimized_verify(mode, folder / 'verify.py', out, False, 'frozen input_manifest')
        write_json(out / 'input_manifest.json', baseline)
        (out / 'inputs.json').write_bytes((folder / 'inputs.json').read_bytes() + b' ')
        with patch.object(verifier, 'ROOT', folder), self.assertRaisesRegex(ValueError, 'frozen inputs'):
            self.invoke(verifier, out)

    def test_primary_verifier_rejects_boolean_and_float_budget_identities(self):
        folder, out, verifier = self.tiny_run()
        traces = json.loads((out / 'traces.json').read_text())
        summary = json.loads((out / 'summary.json').read_text())
        for kind in ('nearest_false', 'trace_true', 'trace_float', 'group_true', 'group_float'):
            bad_traces, bad_summary = deepcopy(traces), deepcopy(summary)
            rows = bad_summary['aggregates'] if kind.startswith('group') else bad_traces
            row = next(r for r in rows if r['budget'] == (0 if kind == 'nearest_false' else 1))
            row['budget'] = False if kind == 'nearest_false' else (1.0 if kind.endswith('float') else True)
            write_json(out / 'traces.json', bad_traces); write_json(out / 'summary.json', bad_summary)
            (out / 'verification.json').unlink(missing_ok=True)
            with self.subTest(kind=kind), patch.object(verifier, 'ROOT', folder), self.assertRaisesRegex(ValueError, 'budget identity type'):
                self.invoke(verifier, out)
            self.assertFalse((out / 'verification.json').exists())
        shutil.copyfile(STUDY / 'verify.py', folder / 'verify.py')
        for mode in ('flag', 'environment'):
            write_json(out / 'traces.json', traces); write_json(out / 'summary.json', summary)
            self.optimized_verify(mode, folder / 'verify.py', out, True)
            for section in ('trace', 'group'):
                bad_traces, bad_summary = deepcopy(traces), deepcopy(summary)
                rows = bad_traces if section == 'trace' else bad_summary['aggregates']
                next(r for r in rows if r['budget'] == 1)['budget'] = True
                write_json(out / 'traces.json', bad_traces); write_json(out / 'summary.json', bad_summary)
                self.optimized_verify(mode, folder / 'verify.py', out, False, 'budget identity type')

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
        extension, out, verifier, payload = self.ablation_run()
        row = next(r for r in payload['traces'] if (r['case_id'], r['chain_limit'], r['weight'], r['budget'])
                   == ('dev_tiny', 5, '0', 2))
        self.assertEqual([step['cost'] for step in row['history']], [1, 2, 3])
        oracle = [dict(t=1, optimum=1, possible_first_servers=[3]),
                  dict(t=2, optimum=2, possible_first_servers=[0]),
                  dict(t=3, optimum=3, possible_first_servers=[3, 5])]
        self.assertEqual(payload['oracle']['dev_tiny'], oracle)
        with patch.object(verifier, 'ROOT', extension):
            self.invoke(verifier, out)
            checked = json.loads((out / 'verification.json').read_text())
            self.assertEqual(checked['trajectories'], 82)
            self.assertEqual(checked['stages'], sum(len(row['history']) for row in payload['traces']))
            corrupt = deepcopy(payload); corrupt['traces'][0]['history'][1]['cost'] += 1
            self.save_ablation(out, corrupt)
            with self.assertRaises(AssertionError):
                self.invoke(verifier, out)
            short = deepcopy(payload); short['traces'][0]['history'].pop()
            self.save_ablation(out, short)
            with self.assertRaisesRegex(AssertionError, 'incomplete trajectory'):
                self.invoke(verifier, out)
            corrupt = deepcopy(payload); corrupt['traces'][0]['history'][1]['t'] = 99
            self.save_ablation(out, corrupt)
            with self.assertRaisesRegex(AssertionError, 'nonconsecutive stage'):
                self.invoke(verifier, out)

    def test_ablation_rejects_missing_duplicate_or_altered_matrix_records(self):
        extension, out, verifier, baseline = self.ablation_run()
        with patch.object(verifier, 'ROOT', extension):
            self.invoke(verifier, out)
        for kind in ('missing_config', 'missing_dev_weight', 'missing_stress_budget5', 'missing_case',
                     'duplicate_case', 'altered_case', 'duplicate_trace', 'missing_metric', 'duplicate_metric',
                     'extra_config', 'missing_group', 'duplicate_group', 'extra_group', 'case_count',
                     'case_metadata', 'missing_oracle_case', 'extra_oracle_case', 'extra_oracle_stage'):
            bad = deepcopy(baseline)
            if kind == 'missing_config':
                self.filter_ablation(bad, lambda r: (r['chain_limit'], r['weight'], r['budget']) != (1, '1/2', 1))
            elif kind == 'missing_dev_weight':
                self.filter_ablation(bad, lambda r: r['weight'] != '1/4')
            elif kind == 'missing_stress_budget5':
                self.filter_ablation(bad, lambda r: r['budget'] != 5)
            elif kind == 'missing_case':
                bad['inputs']['cases'].pop(0); bad['oracle'].pop('dev_tiny')
                self.filter_ablation(bad, lambda r: r['case_id'] != 'dev_tiny')
                bad['summary']['development_count'] = 0
            elif kind == 'duplicate_case': bad['inputs']['cases'].append(deepcopy(bad['inputs']['cases'][0]))
            elif kind == 'altered_case': bad['inputs']['cases'][0]['requests'][0] += 1
            elif kind == 'duplicate_trace':
                bad['traces'].append(deepcopy(bad['traces'][0])); bad['metrics'].append(deepcopy(bad['metrics'][0]))
                self.filter_ablation(bad, lambda r: True)
            elif kind == 'missing_metric': bad['metrics'].pop()
            elif kind == 'duplicate_metric': bad['metrics'][1] = deepcopy(bad['metrics'][0])
            elif kind == 'extra_config':
                bad['traces'][0]['chain_limit'] = bad['metrics'][0]['chain_limit'] = 2
            elif kind == 'missing_group': bad['summary']['groups'].pop()
            elif kind == 'duplicate_group': bad['summary']['groups'].append(deepcopy(bad['summary']['groups'][0]))
            elif kind == 'extra_group': bad['summary']['groups'][0]['budget'] = 99
            elif kind == 'case_count': bad['summary']['development_count'] += 1
            elif kind == 'case_metadata': bad['traces'][0]['split'] = bad['metrics'][0]['split'] = 'eval'
            elif kind == 'missing_oracle_case': bad['oracle'].pop('dev_tiny')
            elif kind == 'extra_oracle_case': bad['oracle']['extra'] = bad['oracle']['dev_tiny']
            else: bad['oracle']['dev_tiny'].append(bad['oracle']['dev_tiny'][-1])
            with self.subTest(kind=kind), patch.object(verifier, 'ROOT', extension), self.assertRaises(AssertionError):
                self.save_ablation(out, bad)
                self.invoke(verifier, out)

    def test_four_arrival_known_values_and_corrupt_or_incomplete_witness(self):
        _, verifier, summary = self.four_game_summary()
        self.assertEqual((summary['results'][0]['value'], summary['hindsight_fixed_sequence'][0]['value']), (0, 2))
        self.verify_game(verifier, summary)
        checked = json.loads((self.root / 'verification.json').read_text())
        self.assertEqual([row['witness_stages_verified'] for row in checked['results']], [4]*9)
        corrupt = deepcopy(summary); corrupt['hindsight_fixed_sequence'][0]['witness'][1]['cost'] += 1
        short = deepcopy(summary); short['results'][0]['witness'].pop()
        empty = dict(summary, results=[], hindsight_fixed_sequence=[])
        for bad in (corrupt, short, empty):
            with self.subTest(kind=bad), self.assertRaises(AssertionError):
                self.verify_game(verifier, bad)

    def test_ablation_rejects_missing_identity_headers_and_malformed_csv_rows(self):
        extension, out, verifier, baseline = self.ablation_run()
        with patch.object(verifier, 'ROOT', extension):
            self.invoke(verifier, out)
        fields = list(baseline['metrics'][0])
        for kind in ('missing_identity', 'missing_time', 'duplicate_header', 'extra_header',
                     'missing_value', 'extra_value', 'shifted_row'):
            header, rows = list(fields), [[row[field] for field in fields] for row in baseline['metrics']]
            if kind in ('missing_identity', 'missing_time'):
                field = 'case_id' if kind == 'missing_identity' else 'wall_seconds'
                index = header.index(field); header.pop(index)
                for row in rows: row.pop(index)
            elif kind == 'duplicate_header': header[-1] = header[0]
            elif kind == 'extra_header':
                header.append('extra')
                for row in rows: row.append('extra')
            elif kind == 'missing_value': rows[0].pop()
            elif kind == 'extra_value': rows[0].append('extra')
            else: rows[1] = list(rows[0])
            self.save_ablation(out, baseline)
            with (out / 'metrics.csv').open('w', newline='', encoding='utf-8-sig') as handle:
                writer = csv.writer(handle); writer.writerow(header); writer.writerows(rows)
            with self.subTest(kind=kind), patch.object(verifier, 'ROOT', extension), self.assertRaisesRegex(AssertionError, 'metric'):
                self.invoke(verifier, out)

    def test_four_arrival_rejects_missing_duplicate_and_extra_configurations(self):
        _, verifier, baseline = self.four_game_summary()
        for section in ('results', 'hindsight_fixed_sequence'):
            for index in range(len(baseline[section])):
                bad = deepcopy(baseline); bad[section].pop(index)
                with self.subTest(section=section, missing=index), self.assertRaisesRegex(AssertionError, 'configuration'):
                    self.verify_game(verifier, bad)
            for kind in ('duplicate', 'extra', 'wrong_future', 'wrong_budget_type'):
                bad = deepcopy(baseline)
                if kind == 'duplicate': bad[section].append(deepcopy(bad[section][0]))
                elif kind == 'extra': bad[section][0]['budget'] = 3
                elif kind == 'wrong_future': bad[section][0]['known_future'] = not bad[section][0]['known_future']
                else: bad[section][0]['budget'] = True
                with self.subTest(section=section, kind=kind), self.assertRaisesRegex(AssertionError, 'configuration'):
                    self.verify_game(verifier, bad)
        bad = deepcopy(baseline); bad['hindsight_fixed_sequence'][0]['witness'][-1]['request'] = 8
        with self.assertRaisesRegex(AssertionError, 'hindsight sequence'):
            self.verify_game(verifier, bad)

    def test_four_arrival_rejects_tied_extra_moves_and_lexicographic_assignment(self):
        verifier = load_script('extension_20260925/verify_four_game.py')
        archived = EXTENSION / 'output/four_game_20260925T053018894723Z/summary.json'
        baseline = json.loads(archived.read_text())
        self.verify_game(verifier, baseline)
        bad = deepcopy(baseline)
        row = next(r for r in bad['results'] if (r['model'], r['budget']) == ('atomic', 2))['witness'][-1]
        row['assignment'], row['counts'] = [2, -1, 8, -4], [1, 1, 1, 0]
        with self.assertRaisesRegex(AssertionError, 'action tie'):
            self.verify_game(verifier, bad)
        _, verifier, baseline = self.four_game_summary(alphabet=(2,))
        self.verify_game(verifier, baseline)
        bad = deepcopy(baseline)
        witness = next(r for r in bad['results'] if (r['model'], r['budget']) == ('atomic', 4))['witness']
        witness[2]['assignment'], witness[3]['assignment'] = [2, -1, 8], [2, -1, 8, -4]
        with self.assertRaisesRegex(AssertionError, 'action tie'):
            self.verify_game(verifier, bad)

    def test_four_arrival_rejects_tied_nature_request(self):
        producer, verifier, baseline = self.four_game_summary(alphabet=(0, 2))
        self.verify_game(verifier, baseline)
        alternative = producer.solve(4, 'atomic', known_sequence=(2, 2, 2, 2))
        self.assertEqual(alternative['value'], 0)
        alternative['known_future'] = False
        bad = deepcopy(baseline)
        bad['results'][2] = alternative
        with self.assertRaisesRegex(AssertionError, 'request tie'):
            self.verify_game(verifier, bad)

    def test_ablation_checks_survive_optimization_flag_and_environment(self):
        extension, out, _, baseline = self.ablation_run()
        script = extension / 'verify_ablation.py'
        shutil.copyfile(EXTENSION / 'verify_ablation.py', script)
        for mode in ('flag', 'environment'):
            with self.subTest(mode=mode, kind='valid'):
                self.save_ablation(out, baseline)
                self.optimized_verify(mode, script, out, True)
            for kind in ('missing_config', 'incorrect_cost', 'missing_identity'):
                bad = deepcopy(baseline)
                if kind == 'missing_config':
                    self.filter_ablation(bad, lambda r: (r['chain_limit'], r['weight'], r['budget']) != (1, '1/2', 1))
                elif kind == 'incorrect_cost': bad['traces'][0]['history'][0]['cost'] += 1
                else:
                    for row in bad['metrics']: row.pop('case_id')
                with self.subTest(mode=mode, kind=kind):
                    self.save_ablation(out, bad)
                    self.optimized_verify(mode, script, out, False)

    def test_ablation_fixed_input_identity_and_exact_config_types(self):
        extension, out, verifier, baseline = self.ablation_run()
        original = (self.root / 'inputs.json').read_bytes()
        for kind in ('input_tag', 'summary_tag', 'altered_fixed_source', 'trace_budget_bool',
                     'trace_limit_bool', 'group_budget_bool', 'group_limit_bool', 'trace_budget_float'):
            bad = deepcopy(baseline)
            (self.root / 'inputs.json').write_bytes(original)
            if kind == 'input_tag': bad['inputs']['original_sha256'] = 'wrong'
            elif kind == 'summary_tag': bad['summary']['original_sha256'] = 'wrong'
            elif kind == 'altered_fixed_source':
                source = json.loads(original); source['cases'][0]['family'] = 'changed'
                write_json(self.root / 'inputs.json', source)
                bad['inputs']['cases'][0]['family'] = 'changed'
                for rows in (bad['traces'], bad['metrics']):
                    for row in rows:
                        if row['case_id'] == 'dev_tiny': row['family'] = 'changed'
            else:
                section = 'groups' if kind.startswith('group') else 'traces'
                rows = bad['summary']['groups'] if section == 'groups' else bad['traces']
                field = 'chain_limit' if 'limit' in kind else 'budget'
                row = next(r for r in rows if r[field] == 1)
                row[field] = 1.0 if kind.endswith('float') else True
                if section == 'traces':
                    index = rows.index(row); bad['metrics'][index][field] = row[field]
            with self.subTest(kind=kind), patch.object(verifier, 'ROOT', extension), self.assertRaisesRegex(AssertionError, 'identity'):
                self.save_ablation(out, bad)
                self.invoke(verifier, out)
        (self.root / 'inputs.json').write_bytes(original)

    def test_ablation_producer_and_verifier_bind_inputs_under_optimization(self):
        extension, out, _, baseline = self.ablation_run()
        for name in ('ablation.py', 'verify_ablation.py'):
            shutil.copyfile(EXTENSION / name, extension / name)
        original = (self.root / 'inputs.json').read_bytes()
        for mode in ('flag', 'environment'):
            source = json.loads(original); source['cases'][0]['family'] = 'changed'
            write_json(self.root / 'inputs.json', source)
            bad = deepcopy(baseline); bad['inputs']['cases'][0]['family'] = 'changed'
            for rows in (bad['traces'], bad['metrics']):
                for row in rows:
                    if row['case_id'] == 'dev_tiny': row['family'] = 'changed'
            self.save_ablation(out, bad)
            for script in ('ablation.py', 'verify_ablation.py'):
                with self.subTest(mode=mode, script=script):
                    self.optimized_verify(mode, extension / script, out, False, 'fixed input identity mismatch')
        (self.root / 'inputs.json').write_bytes(original)

    def test_remaining_scientific_checks_survive_optimization(self):
        program = '''
import runpy, sys
from fractions import Fraction as Q
from types import SimpleNamespace
from pathlib import Path
root=Path(sys.argv[1])
three=runpy.run_path(str(root/'verify_three_point.py'))
if three['audit_prefix']((0,3,5),2,3,range(6))[0] != 1: raise RuntimeError('wrong valid three-point value')
try: three['audit_prefix']((0,3,5),2,3,[])
except AssertionError: pass
else: raise RuntimeError('empty future accepted')
chain=runpy.run_path(str(root/'extension_20260925/chain_first.py'))
if chain['first_value']((0,3,6),Q(7,4),0)['value'] != 1: raise RuntimeError('wrong valid chain value')
chain['first_value'].__globals__['prefix']=lambda *args: ((Q(-1),(0,1),Q(0)),[])
try: chain['first_value']((0,3,6),Q(7,4),0)
except AssertionError: pass
else: raise RuntimeError('inconsistent chain result accepted')
raw=runpy.run_path(str(root/'extension_20260925/random_raw.py'))
matrix=raw['np'].array([[58.,64.],[62.,56.]])
if abs(raw['game'](matrix)['value']-60)>1e-8: raise RuntimeError('wrong valid LP value')
invalid=SimpleNamespace(success=True,message='controlled inconsistent certificate',x=raw['np'].array([-.5,1.5,60.]),
                        fun=60.,ineqlin=SimpleNamespace(marginals=raw['np'].array([-2/3,-1/3])))
raw['game'].__globals__['linprog']=lambda *args,**kwargs: invalid
try: raw['game'](matrix)
except AssertionError: pass
else: raise RuntimeError('inconsistent LP certificate accepted')
'''
        for mode in ('flag', 'environment'):
            environment = dict(os.environ); environment.pop('PYTHONOPTIMIZE', None)
            flags = ['-O', '-B'] if mode == 'flag' else ['-B']
            if mode == 'environment': environment['PYTHONOPTIMIZE'] = '1'
            with self.subTest(mode=mode):
                result = subprocess.run([sys.executable, *flags, '-c', program, str(STUDY)], env=environment,
                                        capture_output=True, text=True, timeout=180)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_optimized_fixture_runner_and_finalizer_preserve_input_guards(self):
        for mode in ('flag', 'environment'):
            environment = dict(os.environ); environment.pop('PYTHONOPTIMIZE', None)
            flags = ['-O', '-B'] if mode == 'flag' else ['-B']
            if mode == 'environment': environment['PYTHONOPTIMIZE'] = '1'
            folder = self.root / mode; folder.mkdir()
            for name in ('fixtures.py', 'run.py', 'matching.py', 'protocol.md'):
                shutil.copyfile(STUDY / name, folder / name)
            command = [sys.executable, *flags]
            with self.subTest(mode=mode, kind='valid_fixture'):
                result = subprocess.run([*command, str(folder / 'fixtures.py')], env=environment,
                                        capture_output=True, text=True, timeout=180)
                self.assertEqual(result.returncode, 0, result.stderr)
            changed = json.loads((folder / 'inputs.json').read_text()); changed['cases'][0]['family'] = 'changed'
            write_json(folder / 'inputs.json', changed)
            changed_bytes = (folder / 'inputs.json').read_bytes()
            with self.subTest(mode=mode, kind='protect_existing_fixture'):
                result = subprocess.run([*command, str(folder / 'fixtures.py')], env=environment,
                                        capture_output=True, text=True, timeout=180)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((folder / 'inputs.json').read_bytes(), changed_bytes)
            with self.subTest(mode=mode, kind='runner_identity'):
                result = subprocess.run([*command, str(folder / 'run.py'), '--split', 'dev'], env=environment,
                                        capture_output=True, text=True, timeout=180)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((folder / 'output').exists())
            out = folder / 'failed'; out.mkdir()
            write_json(out / 'verification.json', {'status': 'failed'})
            write_json(out / 'summary.json', {'aggregates': []})
            shutil.copyfile(STUDY / 'protocol.md', out / 'protocol.md')
            with self.subTest(mode=mode, kind='finalizer_status'):
                result = subprocess.run([*command, str(STUDY / 'finalize.py'), str(out)], env=environment,
                                        capture_output=True, text=True, timeout=180)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((out / '结果说明.md').exists())

    def test_four_arrival_checks_survive_optimization_flag_and_environment(self):
        archived = EXTENSION / 'output/four_game_20260925T053018894723Z/summary.json'
        baseline = json.loads(archived.read_text())
        script, source = EXTENSION / 'verify_four_game.py', self.root / 'summary.json'
        for mode in ('flag', 'environment'):
            with self.subTest(mode=mode, kind='valid'):
                write_json(source, baseline)
                self.optimized_verify(mode, script, source, True)
            for kind in ('missing_config', 'incorrect_cost', 'tied_extra_move', 'continuous_certificate'):
                bad = deepcopy(baseline)
                if kind == 'missing_config': bad['results'].pop()
                elif kind == 'incorrect_cost': bad['results'][0]['witness'][0]['cost'] += 1
                elif kind == 'tied_extra_move':
                    row = next(r for r in bad['results'] if (r['model'], r['budget']) == ('atomic', 2))['witness'][-1]
                    row['assignment'], row['counts'] = [2, -1, 8, -4], [1, 1, 1, 0]
                else:
                    archived_continuous = EXTENSION / 'output/continuous_four_20260925T054559888763Z/summary.json'
                    bad = json.loads(archived_continuous.read_text())
                    bad['rounding']['additive_certificate'] += 1
                with self.subTest(mode=mode, kind=kind):
                    write_json(source, bad)
                    self.optimized_verify(mode, script, source, False)

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
            return dict(model=model, budget=budget, value=values[model, budget], states=1, known_future=False)

        # Exercise bound assembly with controlled solver answers, not the full 13-point game.
        with patch.object(continuous, 'ROOT', self.root), patch.object(continuous, 'solve', side_effect=solved):
            self.invoke(continuous)
        source, = (self.root / 'output').glob('*/summary.json')
        summary = json.loads(source.read_text())
        verifier.verify_rounding(summary)
        self.assertEqual([row['upper'] for row in summary['continuous_intervals']], [21, 14, 23, 16])
        for field in ('upper', 'certificate', 'missing', 'missing_result', 'duplicate_result',
                      'duplicate_interval', 'extra_hindsight', 'wrong_future'):
            bad = deepcopy(summary)
            if field == 'upper': bad['continuous_intervals'][0]['upper'] += 1
            elif field == 'certificate': bad['rounding']['additive_certificate'] += 1
            elif field == 'missing': bad['continuous_intervals'].pop()
            elif field == 'missing_result': bad['results'].pop()
            elif field == 'duplicate_result': bad['results'][1] = deepcopy(bad['results'][0])
            elif field == 'duplicate_interval': bad['continuous_intervals'][1] = deepcopy(bad['continuous_intervals'][0])
            elif field == 'extra_hindsight': bad['hindsight_fixed_sequence'] = [dict(model='atomic', budget=1, known_future=True)]
            else: bad['results'][0]['known_future'] = True
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

    def local_study_fixture(self, case=None):
        study = load_script('extension_20260925/local_freeze_study.py')
        if case is None:
            case = dict(id='tiny', servers=[-4, -1, 2, 8], requests=['1/2', -1, 2, -4])
        self.enterContext(patch.object(study, 'fixed_cases', return_value=[case]))
        # Phase-publication checks substitute the expensive formal alphabet audit.
        self.enterContext(patch.object(study, 'finite_audit'))
        with redirect_stdout(io.StringIO()):
            study.run_phase('initial', self.root)
        return study, case

    def test_local_study_rejects_changed_inputs_before_reserving_output(self):
        study, case = self.local_study_fixture()
        inputs = self.root / 'initial/inputs.json'
        changed = deepcopy(case); changed['requests'][0] = '2/3'
        write_json(inputs, [changed])
        with self.assertRaisesRegex(AssertionError, 'fixed initial design'):
            study.run_phase('revised', self.root)
        self.assertFalse((self.root / 'revised').exists())
        write_json(inputs, [case])
        record = self.root / 'initial/tiny_b2_fixed4.json'
        saved = json.loads(record.read_text()); saved['requests'][0] = '2/3'
        write_json(record, saved)
        with self.assertRaisesRegex(AssertionError, 'trajectory differs'):
            study.run_phase('revised', self.root)
        self.assertFalse((self.root / 'revised').exists())

    def test_local_study_rejects_changed_coordinate_types(self):
        case = dict(id='tiny', servers=[0, 3, 6, 12], requests=['9/2', 3, 6, 0])
        study, case = self.local_study_fixture(case)
        for coordinate in (False, 0.0):
            changed = deepcopy(case); changed['servers'][0] = coordinate
            write_json(self.root / 'initial/inputs.json', [changed])
            with self.subTest(coordinate=coordinate), self.assertRaisesRegex(AssertionError, 'fixed initial design'):
                study.run_phase('revised', self.root)
            self.assertFalse((self.root / 'revised').exists())

    def test_local_study_prerequisite_failures_allow_retry(self):
        study = load_script('extension_20260925/local_freeze_study.py')
        with self.assertRaises(FileNotFoundError):
            study.run_phase('revised', self.root)
        self.assertFalse((self.root / 'revised').exists())
        study, _ = self.local_study_fixture()
        source = self.root / 'initial/summary.json'
        original = json.loads(source.read_text())
        for kind in ('incomplete', 'no_trigger', 'missing', 'duplicate', 'budget_type'):
            bad = deepcopy(original)
            if kind == 'incomplete':
                bad['status'] = 'incomplete'
            elif kind == 'no_trigger':
                for row in bad['comparisons']:
                    row['verification']['maximum_frozen_loss'] = '0'
            elif kind == 'missing':
                bad['comparisons'].pop(0)
            elif kind == 'duplicate':
                bad['comparisons'].append(deepcopy(bad['comparisons'][0]))
            else:
                bad['comparisons'][0]['budget'] = True
            write_json(source, bad)
            with self.subTest(kind=kind), self.assertRaises(AssertionError):
                study.run_phase('revised', self.root)
            self.assertFalse((self.root / 'revised').exists())
        write_json(source, original)
        with redirect_stdout(io.StringIO()):
            result = study.run_phase('revised', self.root)
        self.assertEqual(result['status'], 'complete')
        comparison = json.loads((self.root / 'revised/comparison.json').read_text())
        self.assertEqual(comparison['cpu_seconds'], original['cpu_seconds'] + result['cpu_seconds'])
        changed = json.loads((self.root / 'revised/inputs.json').read_text())
        changed[0]['requests'][0] = '2/3'
        write_json(self.root / 'revised/inputs.json', changed)
        with self.assertRaisesRegex(AssertionError, 'fixed initial design'):
            study.compare(self.root)

    def test_local_study_comparison_failures_leave_incomplete_summary(self):
        study, _ = self.local_study_fixture()
        write_original = study.write
        for kind in ('comparison', 'write'):
            root = self.root / kind
            shutil.copytree(self.root / 'initial', root / 'initial')

            def fail_comparison_write(path, value):
                if path.name == 'comparison.json':
                    raise OSError('controlled comparison write failure')
                write_original(path, value)

            target = (patch.object(study, 'compare', side_effect=AssertionError('controlled comparison failure'))
                      if kind == 'comparison' else patch.object(study, 'write', side_effect=fail_comparison_write))
            with self.subTest(kind=kind), target, redirect_stdout(io.StringIO()), self.assertRaises((AssertionError, OSError)):
                study.run_phase('revised', root)
            saved = json.loads((root / 'revised/summary.json').read_text())
            self.assertEqual(saved['status'], 'incomplete')
            self.assertFalse((root / 'revised/comparison.json').exists())

    def test_added_research_checks_survive_optimization(self):
        program = '''
from copy import deepcopy
import json, runpy, sys, tempfile
from pathlib import Path
root = Path(sys.argv[1])
extension = root / 'independent_research/online_matching_recourse/extension_20260925'
sys.path.insert(0, str(extension))
def load(name):
    return runpy.run_path(str(extension / (name + '.py')))
policy = load('four_budget2_policy')
long = load('long_sequence')
local = load('local_freeze')
lower = json.loads((root / 'tests/fixtures/online_matching/four_exact_lower.json').read_text())[0]
records = [
    ('verify_four_budget2_policy', policy['run'](['1/2', -1, 2, -4])),
    ('verify_long_sequence', long['run']([0, 3, 5], [2, 3, 0], 1, [2])),
    ('verify_local_freeze', local['run']([0, 2, 100, 102], [1, 0, 101, 100], 1)),
    ('verify_four_exact', lower),
]
for name, data in records:
    verify = load(name)['verify']
    if not verify(data)['verified']:
        raise RuntimeError(name + ' rejected valid input')
    bad = deepcopy(data)
    if name == 'verify_four_exact':
        bad['bound'] = '100'
    else:
        bad['trace'][1]['cost'] = '999'
    try:
        verify(bad)
    except AssertionError:
        pass
    else:
        raise RuntimeError(name + ' accepted corrupt input')
matcher = policy['FourBudgetTwo']()
matcher.excess = 4
try:
    matcher.arrive(0)
except AssertionError:
    pass
else:
    raise RuntimeError('policy invariant disabled')
with tempfile.TemporaryDirectory() as folder:
    folder = Path(folder)
    for phase in ('initial', 'revised'):
        (folder / phase).mkdir()
        (folder / phase / 'summary.json').write_text(json.dumps(dict(
            status='incomplete', comparisons=[], input_cases=0, cpu_seconds=0)))
    try:
        load('local_freeze_study')['compare'](folder)
    except AssertionError:
        pass
    else:
        raise RuntimeError('incomplete local study accepted')
'''
        for mode in ('flag', 'environment'):
            environment = dict(os.environ)
            environment.pop('PYTHONOPTIMIZE', None)
            flags = ['-O', '-B'] if mode == 'flag' else ['-B']
            if mode == 'environment':
                environment['PYTHONOPTIMIZE'] = '1'
            with self.subTest(mode=mode):
                result = subprocess.run([sys.executable, *flags, '-c', program, str(ROOT)],
                                        env=environment, capture_output=True, text=True, timeout=180)
                self.assertEqual(result.returncode, 0, result.stderr)

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
