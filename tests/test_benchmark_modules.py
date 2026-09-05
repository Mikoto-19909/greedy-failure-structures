"""Check benchmark extraction boundaries and genuine pre-move task pickles."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover import benchmark
from maxcover import benchmark_artifacts, benchmark_manifest, benchmark_planning


PICKLE_CHECK = r"""
import dataclasses
import json
import pickle
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from maxcover import benchmark, benchmark_planning
from maxcover.contracts import AlgorithmRunOptions
from maxcover.model import thaw_json_value
from maxcover.reproducibility import instance_id, instance_payload
fixture = Path(sys.argv[2])
expected = json.loads((fixture / 'expected.json').read_bytes())
for name, shape in expected['class_shapes'].items():
    cls = getattr(benchmark_planning, name)
    assert getattr(benchmark, name) is cls
    assert cls.__qualname__ == shape['qualname']
    assert list(cls.__slots__) == shape['slots']
    assert list(cls.__match_args__) == shape['match_args']
    assert cls.__dataclass_params__.frozen == shape['frozen']
    assert [f.name for f in dataclasses.fields(cls)] == shape['fields']
    for field in dataclasses.fields(cls):
        default = shape['defaults'][field.name]
        assert field.default_factory is dataclasses.MISSING
        if default['kind'] == 'missing':
            assert field.default is dataclasses.MISSING
        else:
            assert field.default == default['value']
for protocol in (4, 5):
    values = pickle.loads((fixture / f'planning_tasks_protocol{protocol}.pickle').read_bytes())
    assert set(values) == set(expected['cases'])
    for label, (planned, task) in values.items():
        old = expected['cases'][label]
        assert type(planned) is benchmark._PlannedInstance is benchmark_planning._PlannedInstance
        assert type(task) is benchmark._RunTask is benchmark_planning._RunTask
        assert type(task.options) is AlgorithmRunOptions
        assert planned.instance is task.instance
        for value, key, omitted in ((planned, 'planned', {'instance'}),
                                    (task, 'task', {'instance', 'options'}),
                                    (task.options, 'options', set())):
            observed = {field.name: thaw_json_value(getattr(value, field.name))
                        for field in dataclasses.fields(value) if field.name not in omitted}
            assert observed == old[key], (label, key, observed, old[key])
        assert list(planned.instance.sets) == old['instance']['ordered_masks']
        assert instance_payload(planned.instance, encoding='bitsets') == old['instance']['instance_payload']
        assert instance_id(planned.instance) == old['instance']['computed_instance_id']
        for value in (planned, task):
            assert not hasattr(value, '__dict__')
            try:
                value.case_id = 'changed'
            except dataclasses.FrozenInstanceError:
                pass
            else:
                raise AssertionError('loaded task must remain frozen')
        roundtrip = pickle.loads(pickle.dumps((planned, task), protocol=protocol))
        assert roundtrip == (planned, task)
        assert roundtrip[0].instance is roundtrip[1].instance
print('PASS: both old protocols preserve task contents, aliases and shared instances')
"""


class BenchmarkModuleTests(unittest.TestCase):
    def test_old_planning_pickles_load_in_a_new_interpreter(self) -> None:
        fixture = ROOT / "tests/fixtures/benchmark_planning"
        provenance = json.loads((fixture / "provenance.json").read_bytes())
        self.assertEqual(provenance["baseline_commit"], "c40658d4cbc16b45fb640b1d97c03688baee16b7")
        for filename, metadata in provenance["files"].items():
            data = (fixture / filename).read_bytes()
            self.assertEqual(len(data), metadata["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), metadata["sha256"])
        completed = subprocess.run(
            [sys.executable, "-c", PICKLE_CHECK, str(ROOT / "src"), str(fixture)],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("PASS:", completed.stdout)

    def test_internal_modules_do_not_import_the_facade(self) -> None:
        for path in (ROOT / "src/maxcover").glob("benchmark_*.py"):
            with self.subTest(module=path.name):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if isinstance(node, ast.ImportFrom):
                        self.assertNotIn(node.module, {"benchmark", "maxcover.benchmark"})
                        if node.module in {None, "maxcover"}:
                            self.assertNotIn("benchmark", [alias.name for alias in node.names])
                    elif isinstance(node, ast.Import):
                        self.assertNotIn("maxcover.benchmark", [alias.name for alias in node.names])

    def test_facade_aliases_and_git_root_remain_correct(self) -> None:
        for module, names in (
            (benchmark_planning, ("_PlannedInstance", "_RunTask", "_STRUCTURAL_COUPLING_INTENSITY",
                                  "_case_seed", "_coupling_pair_id", "_coupling_seed",
                                  "_fixed_size_control_pairs", "_instance_record", "_instances_for_config",
                                  "_resolved_case_parameters", "_structural_coupling_pair_id", "_tasks_for_config")),
            (benchmark_artifacts, ("REPORT_FILENAMES", "RUNNER_OWNED_FILENAMES",
                                   "SEARCH_COMPARISON_FIELDS", "STOCHASTIC_SUMMARY_FIELDS", "_runner_owned_paths")),
            (benchmark_manifest, ("PROJECT_ROOT", "_git_state", "_write_manifest")),
        ):
            for name in names:
                with self.subTest(name=name):
                    self.assertIs(getattr(benchmark, name), getattr(module, name))
        self.assertEqual(benchmark_manifest.PROJECT_ROOT, ROOT)
        with patch.object(benchmark_manifest.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0, "abcdef\n"),
            subprocess.CompletedProcess([], 0, ""),
        ]) as invoke:
            self.assertEqual(benchmark._git_state(), {"commit": "abcdef", "dirty": False})
        self.assertEqual([call.args[0] for call in invoke.call_args_list],
                         [["git", "rev-parse", "HEAD"], ["git", "status", "--porcelain"]])
        self.assertTrue(all(call.kwargs["cwd"] == ROOT for call in invoke.call_args_list))


if __name__ == "__main__":
    unittest.main()
