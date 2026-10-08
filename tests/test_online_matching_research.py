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
