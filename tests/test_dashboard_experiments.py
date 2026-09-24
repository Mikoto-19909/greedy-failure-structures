"""Real local configuration edits and experiment annotations preserve inputs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maxcover.config import load_config
from maxcover.dashboard_experiments import ExperimentsConflictError, ExperimentsService
from maxcover.dashboard_jobs import _FileLock


class ExperimentsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "configs").mkdir()
        self.config = {"schema_version": 3, "name": "local study", "base_seed": 18446744073709551615,
                       "repetitions": 2, "algorithms": [{"name": "greedy"}],
                       "cases": [{"name": "small", "family": "uniform", "universe_size": 10,
                                  "set_count": 5, "k": 2, "density": 0.4}]}
        self.template = self.root / "configs/template.json"
        self.template.write_text(json.dumps(self.config, indent=2), encoding="utf-8")
        source = self.root / "experiments/r1/paths.jsonl"
        source.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "experiments/r1_prefix_exchange_v1/paths.jsonl", source)
        self.source_bytes = source.read_bytes()
        self.template_bytes = self.template.read_bytes()
        self.service = ExperimentsService(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def copy(self) -> dict:
        original = self.service.read_config("template.json")
        return self.service.copy_config({"source": "template.json", "expected_revision": original["revision"]})

    def note(self, **values) -> dict:
        return {"source": "experiments/r1", "theme": "前缀诊断", "tags": ["失效", "R1"],
                "notes": "查看第一个失效前缀", "expected_revision": 0, **values}

    def test_copy_edit_preview_diff_preserve_large_seed_and_template(self) -> None:
        original = self.service.read_config("template.json")
        self.assertFalse(original["editable"])
        copied = self.copy()
        self.assertTrue(copied["editable"])
        self.assertRegex(copied["path"], r"^local/[0-9a-f]{32}\.json$")
        preview = self.service.preview_config({"text": copied["text"], "base_path": copied["path"],
            "basics": {"name": "edited study", "base_seed": "18446744073709551614", "repetitions": "4"}})
        self.assertEqual(preview["plan"]["instance_count"], 4)
        self.assertEqual(preview["plan"]["algorithm_run_count"], 4)
        change = next(row for row in preview["changes"] if "base_seed" in row["path"])
        self.assertEqual((change["before"], change["after"]), ("18446744073709551615", "18446744073709551614"))
        self.assertEqual(preview["basics"]["base_seed"], "18446744073709551614")
        saved = self.service.save_config({"path": copied["path"], "text": preview["text"], "expected_revision": copied["revision"]})
        self.assertNotEqual(saved["revision"], copied["revision"])
        self.assertNotEqual(saved["config_hash"], copied["config_hash"])
        self.assertEqual(load_config(self.root / "configs" / saved["path"]).base_seed, 18446744073709551614)
        self.assertEqual(self.template.read_bytes(), self.template_bytes)
        restarted = ExperimentsService(self.root).preview_config({"text": saved["text"], "base_path": saved["path"]})
        self.assertEqual(restarted["changes"], [])
        self.assertEqual(len(restarted["origin_changes"]), 3)

    def test_json_edit_retains_nested_large_seeds(self) -> None:
        data = {**self.config, "algorithms": [{"name": "greedy"}, {"name": "randomized_greedy", "algorithm_seeds": [18446744073709551613]}]}
        # The supported randomized algorithm is discovered from the actual registry.
        from maxcover.algorithms import ALGORITHMS
        random_names = [name for name, spec in ALGORITHMS.items() if spec.uses_random_seed]
        data["algorithms"][1]["name"] = random_names[0]
        preview = self.service.preview_config({"text": json.dumps(data), "basics": {
            "name": "nested", "base_seed": "18446744073709551615", "repetitions": "1"}})
        self.assertEqual(json.loads(preview["text"])["algorithms"][1]["algorithm_seeds"], [18446744073709551613])

    def test_guided_fields_and_enabled_round_trip_preserve_identity_options_and_template(self) -> None:
        data = {**self.config, "algorithms": [{"name": "greedy", "id": "baseline"},
            {"name": "brute_force", "id": "exact_reference", "options": {"max_set_count": 16}}]}
        original = json.dumps(data).encode()
        self.template.write_bytes(original)
        copied = self.copy()
        self.assertTrue(copied["guided"]["supported"])
        fields = {"universe_size": "12", "set_count": "6", "k": "3", "density": "0.3"}
        changed = self.service.preview_config({"text": copied["text"], "base_path": copied["path"],
            "guided": {"case": fields, "enabled": [True, False]}})
        parsed = json.loads(changed["text"])
        self.assertEqual(parsed["schema_version"], 3)
        self.assertEqual(parsed["base_seed"], data["base_seed"])
        self.assertEqual(parsed["algorithms"][1], {**data["algorithms"][1], "enabled": False})
        self.assertEqual([item["id"] for item in parsed["algorithms"]], ["baseline", "exact_reference"])
        self.assertEqual(parsed["cases"][0], {**data["cases"][0], "universe_size": 12, "set_count": 6, "k": 3, "density": 0.3})
        self.assertEqual(changed["plan"]["algorithm_run_count"], 2)
        restored = self.service.preview_config({"text": changed["text"],
            "guided": {"case": copied["guided"]["case"], "enabled": [True, True]}})
        self.assertEqual(restored["config_hash"], copied["config_hash"])
        self.service.save_config({"path": copied["path"], "text": changed["text"], "expected_revision": copied["revision"]})
        self.assertEqual(self.template.read_bytes(), original)

    def test_guided_rejects_unsupported_raw_configs_without_converting_them(self) -> None:
        variants = [
            {**self.config, "schema_version": 1, "algorithms": ["greedy"]},
            {**self.config, "schema_version": 2},
            {**self.config, "cases": [self.config["cases"][0], {**self.config["cases"][0], "name": "other"}]},
            {**self.config, "cases": [{**{key: value for key, value in self.config["cases"][0].items() if key != "k"}, "sweep": {"k": [1, 2]}}]},
            {**self.config, "algorithms": [{"name": "branch_and_bound"}]},
        ]
        fields = {"case": {"universe_size": "10", "set_count": "5", "k": "2", "density": "0.4"}, "enabled": [True]}
        for data in variants:
            text = json.dumps(data)
            with self.subTest(config=data):
                preview = self.service.preview_config({"text": text})
                self.assertFalse(preview["guided"]["supported"])
                self.assertTrue(preview["guided"]["reason"])
                self.assertEqual(preview["text"], text)
                with self.assertRaises(ValueError):
                    self.service.preview_config({"text": text, "guided": fields})

    def test_guided_invalid_inputs_and_all_disabled_never_write_config(self) -> None:
        copied = self.copy()
        valid = {"case": copied["guided"]["case"], "enabled": [True]}
        invalid = [None, {}, {**valid, "extra": 1}, {**valid, "enabled": []},
                   {**valid, "enabled": [1]}, {**valid, "enabled": [False]}]
        for key, value in (("k", "6"), ("set_count", "0"), ("density", "NaN"),
                           ("density", "1.1"), ("universe_size", "12.0")):
            invalid.append({**valid, "case": {**valid["case"], key: value}})
        for fields in invalid:
            with self.subTest(guided=fields), self.assertRaises(ValueError):
                self.service.preview_config({"text": copied["text"], "guided": fields})
        self.assertEqual((self.root / "configs" / copied["path"]).read_bytes(), self.template_bytes)
        self.assertEqual(self.template.read_bytes(), self.template_bytes)
        with self.assertRaisesRegex(ValueError, "basics requires"):
            self.service.preview_config({"text": copied["text"], "basics": {"name": "bad"}})

    def test_visual_starter_has_the_bounded_acceptance_plan(self) -> None:
        data = json.loads((ROOT / "configs/visual_starter.json").read_text(encoding="utf-8"))
        data["repetitions"] = 3
        preview = self.service.preview_config({"text": json.dumps(data)})
        self.assertTrue(preview["guided"]["supported"])
        self.assertEqual(preview["plan"]["instance_count"], 3)
        self.assertEqual(preview["plan"]["algorithm_run_count"], 9)

    def test_saved_copy_conflict_and_external_template_change_are_rejected(self) -> None:
        copied = self.copy()
        other = ExperimentsService(self.root)
        text = copied["text"].replace("local study", "first edit")
        saved = other.save_config({"path": copied["path"], "text": text, "expected_revision": copied["revision"]})
        with self.assertRaises(ExperimentsConflictError):
            self.service.save_config({"path": copied["path"], "text": copied["text"], "expected_revision": copied["revision"]})
        self.assertEqual((self.root / "configs" / copied["path"]).read_bytes().decode("utf-8"), saved["text"])
        template = self.service.read_config("template.json")
        self.template.write_text(template["text"] + "\n", encoding="utf-8")
        with self.assertRaises(ExperimentsConflictError):
            self.service.copy_config({"source": "template.json", "expected_revision": template["revision"]})
        local_path = self.root / "configs" / copied["path"]
        local_path.write_text(saved["text"] + "\n", encoding="utf-8")
        with self.assertRaises(ExperimentsConflictError):
            self.service.save_config({"path": copied["path"], "text": saved["text"], "expected_revision": saved["revision"]})

    def test_only_ui_created_local_copies_are_editable_and_lock_conflicts(self) -> None:
        original = self.service.read_config("template.json")
        with self.assertRaises(ValueError):
            self.service.save_config({"path": "template.json", "text": original["text"], "expected_revision": original["revision"]})
        copied = self.copy()
        fake = "local/" + "f" * 32 + ".json"
        (self.root / "configs" / fake).write_text(copied["text"], encoding="utf-8")
        self.assertFalse(self.service.read_config(fake)["editable"])
        with self.assertRaises(ValueError):
            self.service.save_config({"path": fake, "text": copied["text"], "expected_revision": copied["revision"]})
        lock = _FileLock(self.root / "configs/local/.editing.lock")
        try:
            with self.assertRaises(ExperimentsConflictError):
                self.service.save_config({"path": copied["path"], "text": copied["text"], "expected_revision": copied["revision"]})
        finally:
            lock.close()

    def test_invalid_config_and_paths_never_change_files(self) -> None:
        copied = self.copy()
        for bad in ("{bad", "[]", '{"name":"a","name":"b"}', '{"base_seed":NaN}', '{"base_seed":1e999}',
                    json.dumps({**self.config, "repetitions": 0}), json.dumps({**self.config, "extra": True})):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.service.save_config({"path": copied["path"], "text": bad, "expected_revision": copied["revision"]})
        for path in ("../configs/template.json", "local/../../configs/template.json", "local\\config.json", str(self.template), "template.json:stream"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.service.read_config(path)
        self.assertEqual((self.root / "configs" / copied["path"]).read_bytes(), self.template_bytes)
        self.assertEqual(self.template.read_bytes(), self.template_bytes)

    def test_annotations_persist_group_labels_and_never_change_source(self) -> None:
        self.assertEqual(self.service.annotations()["annotations"], {})
        self.assertFalse((self.root / "results/.dashboard_local/experiments.sqlite3").exists())
        saved = self.service.set_annotation(self.note(tags=["R1", "失效", "R1"]))
        self.assertEqual(saved["revision"], 1)
        result = ExperimentsService(self.root).annotations()
        self.assertEqual(result["annotations"]["experiments/r1"]["notes"], "查看第一个失效前缀")
        self.assertEqual(result["themes"], ["前缀诊断"])
        self.assertEqual(len(result["tags"]), 2)
        self.service.set_annotation(self.note(theme="", tags=[], notes="", expected_revision=1))
        self.assertEqual(self.service.annotations()["themes"], [])
        self.assertEqual((self.root / "experiments/r1/paths.jsonl").read_bytes(), self.source_bytes)

    def test_annotation_concurrent_edit_conflicts_without_lost_update(self) -> None:
        def update(note: str) -> str:
            try:
                ExperimentsService(self.root).set_annotation(self.note(notes=note))
                return "saved"
            except ExperimentsConflictError:
                return "conflict"
        with ThreadPoolExecutor(2) as executor:
            outcomes = list(executor.map(update, ["first", "second"]))
        self.assertEqual(sorted(outcomes), ["conflict", "saved"])
        self.assertEqual(self.service.annotations()["annotations"]["experiments/r1"]["revision"], 1)

    def test_invalid_annotation_and_broken_source_cannot_create_database(self) -> None:
        broken = self.root / "results/broken/paths.jsonl"
        broken.parent.mkdir(parents=True)
        broken.write_text("{bad", encoding="utf-8")
        for values in ({"source": "../outside"}, {"source": "configs"}, {"source": "results/missing"},
                       {"source": "results/broken"}, {"tags": "R1"}, {"tags": [""]},
                       {"expected_revision": True}, {"notes": 5}, {"theme": "x" * 121}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.service.set_annotation(self.note(**values))
        self.assertFalse((self.root / "results/.dashboard_local/experiments.sqlite3").exists())

    def test_corrupt_annotation_database_is_reported_without_overwrite(self) -> None:
        self.service.set_annotation(self.note())
        database = self.root / "results/.dashboard_local/experiments.sqlite3"
        database.write_bytes(b"broken metadata")
        with self.assertRaisesRegex(ValueError, "Cannot read"):
            self.service.annotations()
        with self.assertRaisesRegex(ValueError, "Cannot save"):
            self.service.set_annotation(self.note())
        self.assertEqual(database.read_bytes(), b"broken metadata")
        self.assertTrue(self.service.read_config("template.json")["valid"])

    def test_hard_linked_config_and_annotation_database_are_rejected(self) -> None:
        target = self.root / "configs/hard.json"
        os.link(self.template, target)
        with self.assertRaises(ValueError):
            self.service.read_config("hard.json")
        self.assertEqual(target.read_bytes(), self.template_bytes)
        target.unlink()
        self.service.set_annotation(self.note())
        database = self.root / "results/.dashboard_local/experiments.sqlite3"
        original = database.read_bytes()
        linked = self.root / "annotation-copy.sqlite3"
        os.link(database, linked)
        with self.assertRaises(ValueError):
            self.service.set_annotation(self.note(expected_revision=1))
        self.assertEqual(linked.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
