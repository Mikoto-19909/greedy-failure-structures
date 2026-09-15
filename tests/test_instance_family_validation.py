from __future__ import annotations

import copy
import csv
import dataclasses
import json
import pickle
from pathlib import Path
import subprocess
import sys
import typing
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover import contracts
from maxcover import _instance_contracts
from maxcover.contracts import InstanceRecord


class InstanceFamilyValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = {}
        with (ROOT / "tests/fixtures/benchmark_compatibility/instances.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                record = InstanceRecord.from_csv_row(row)
                cls.records.setdefault(record.family, record)

    def test_first_error_is_preserved_for_constructor_and_csv(self) -> None:
        cases = (
            ("uniform", {"schema_version": 99, "config_hash": ""}, ValueError,
             "unsupported instance record schema version 99; expected 2"),
            ("uniform", {"parameters": "bad json", "actual_density": -1}, ValueError,
             "parameters must be a JSON object string"),
            ("uniform", {"known_optimum": 1, "generator_version": 99}, ValueError,
             "known optimum certificate fields must be all present or all absent"),
            ("adversarial", {"optimum_selected": [-1], "generator_version": 99}, ValueError,
             "optimum_selected contains an invalid index"),
            ("adversarial", {"generator_version": 99, "parameters": "{}"}, ValueError,
             "unsupported adversarial generator version"),
        )
        for family, changes, error_type, message in cases:
            record = self.records[family]
            kwargs = dataclasses.asdict(record)
            kwargs.update(changes)
            row = {key: str(value) for key, value in record.to_csv_row().items()}
            row.update({key: json.dumps(value) if isinstance(value, list) else str(value)
                        for key, value in changes.items()})
            for entry, payload in ((InstanceRecord, kwargs), (InstanceRecord.from_csv_row, row)):
                with self.subTest(family=family, changes=changes, entry=entry):
                    with self.assertRaises(error_type) as caught:
                        if entry is InstanceRecord:
                            entry(**payload)
                        else:
                            entry(payload)
                    self.assertEqual(str(caught.exception), message)

    def test_integer_type_error_precedes_family_rules(self) -> None:
        record = self.records["adversarial"]
        with self.assertRaises(TypeError) as caught:
            dataclasses.replace(record, repetition=True, generator_version=99)
        self.assertEqual(str(caught.exception), "repetition must be an integer")

    def test_normalization_preserves_caller_inputs(self) -> None:
        expected = self.records["adversarial"]
        kwargs = dataclasses.asdict(expected)
        kwargs["parameters"] = json.dumps(json.loads(expected.parameters), indent=3)
        kwargs["optimum_selected"] = list(expected.optimum_selected)
        before = copy.deepcopy(kwargs)
        record = InstanceRecord(**kwargs)
        self.assertEqual(kwargs, before)
        self.assertEqual(record, expected)
        self.assertEqual(record.to_csv_row(), expected.to_csv_row())
        self.assertIsInstance(record.optimum_selected, tuple)
        row = {key: str(value) for key, value in record.to_csv_row().items()}
        row["parameters"] = kwargs["parameters"]
        before_row = dict(row)
        self.assertEqual(InstanceRecord.from_csv_row(row), expected)
        self.assertEqual(row, before_row)

    def test_replace_validates_but_old_pickle_restoration_does_not(self) -> None:
        record = self.records["adversarial"]
        replaced = dataclasses.replace(record, optimum_selected=list(record.optimum_selected))
        self.assertEqual(replaced, record)
        self.assertIsNot(replaced, record)
        with self.assertRaisesRegex(ValueError, "unsupported adversarial generator version"):
            dataclasses.replace(record, generator_version=99)
        payload = (ROOT / "tests/fixtures/instance_family_validation/baseline_protocol4.pickle").read_bytes()
        with patch.object(InstanceRecord, "__post_init__", side_effect=AssertionError("revalidated")):
            restored = pickle.loads(payload)
        self.assertEqual(restored, [self.records["uniform"], record])
        self.assertTrue(all(type(item) is InstanceRecord for item in restored))

    def test_old_pickle_loads_in_a_fresh_process(self) -> None:
        fixture = ROOT / "tests/fixtures/instance_family_validation/baseline_protocol4.pickle"
        script = (
            "import json,pickle,sys; from pathlib import Path; "
            "sys.path.insert(0,sys.argv[1]); from maxcover.contracts import InstanceRecord; "
            "rows=pickle.loads(Path(sys.argv[2]).read_bytes()); "
            "assert all(type(row) is InstanceRecord for row in rows); "
            "print(json.dumps([row.to_csv_row() for row in rows],sort_keys=True))"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", script, str(ROOT / "src"), str(fixture)],
            check=True, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(result.stdout), [
            self.records[family].to_csv_row() for family in ("uniform", "adversarial")
        ])

    def test_existing_type_annotations_remain_resolvable(self) -> None:
        self.assertIs(contracts.InstanceRecord, _instance_contracts.InstanceRecord)
        for helper in (
            _instance_contracts._validate_p4_3_record_parameters,
            _instance_contracts._validate_paired_uniform_record_parameters,
        ):
            self.assertIs(typing.get_type_hints(helper)["record"], InstanceRecord)
        self.assertIs(typing.get_type_hints(InstanceRecord.from_csv_row)["return"], InstanceRecord)


if __name__ == "__main__":
    unittest.main()
