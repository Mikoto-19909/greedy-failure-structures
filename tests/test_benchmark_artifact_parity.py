"""Exercise B0's declared artifact and stable-Manifest comparison boundary."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "_benchmark_artifact_parity",
    ROOT / ".github/scripts/check_benchmark_compatibility.py",
)
assert SPEC is not None and SPEC.loader is not None
parity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parity)


class BenchmarkArtifactParityTests(unittest.TestCase):
    """Cases derive from the plan's base-versus-head artifact parity section."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.baseline, self.candidate = root / "baseline", root / "candidate"
        self.artifacts = {
            "raw_results.csv": b"run_id,coverage\nr0,7\nr1,8\n",
            "instances.csv": b"instance_id,seed\ni0,31\n",
            "summary.csv": b"algorithm,mean_coverage\ngreedy,7.0000000000\n",
            "greedy_failure_statistics.csv": b"failures,instances\n1,1\n",
            "search_comparison.csv": b"instance_id,node_ratio\ni0,0.5000000000\n",
            "stochastic_summary.csv": b"instance_id,mean_coverage\ni0,7.0000000000\n",
            "results_summary.md": b"# Results\n\nRecorded coverage: 7.\n",
            "runtime_scaling.svg": b'<svg><text x="1">7</text></svg>\n',
        }
        self.manifest: dict[str, Any] = {
            "schema_version": 1,
            "experiment": "synthetic parity checkpoint",
            "configuration": {
                "config_hash": "a" * 64,
                "path": str(root / "shared-config.json"),
            },
            "seeds": {"base_seed": 31, "instance_seeds": [31]},
            "algorithms": {
                "greedy": {
                    "name": "greedy", "version": "1", "enabled": True,
                    "algorithm_seeds": [], "options": {},
                },
            },
            "execution": {"planned_instances": 1, "planned_runs": 2},
            "summary_contract": {
                "schema_version": 1, "aggregation_unit": "instance_seed",
            },
            "git": {"commit": "b" * 40, "dirty": False},
            "environment": {"python": "3.11", "operating_system": "baseline"},
            "timing": {
                "started_at": "2026-01-01T00:00:00+00:00",
                "ended_at": "2026-01-01T00:00:01+00:00",
                "duration_seconds": 1.0,
            },
            "outputs": {
                name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in self.artifacts.items()
            },
        }
        for output in (self.baseline, self.candidate):
            output.mkdir()
            for name, data in self.artifacts.items():
                (output / name).write_bytes(data)
            self._write_manifest(output, self.manifest)

    @staticmethod
    def _write_manifest(output: Path, manifest: dict[str, Any]) -> None:
        (output / "manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))

    def test_identical_outputs_return_the_compared_artifact_names(self) -> None:
        self.assertEqual(
            parity.compare_outputs(self.baseline, self.candidate),
            sorted(self.artifacts),
        )

    def test_only_declared_execution_metadata_and_json_layout_may_change(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        candidate["git"] = {"commit": "c" * 40, "dirty": True}
        candidate["environment"] = {"python": "3.12", "operating_system": "candidate"}
        candidate["timing"] = {
            "started_at": "2026-02-02T02:02:02+00:00",
            "ended_at": "2026-02-02T02:02:04+00:00",
            "duration_seconds": 2.0,
        }
        self.assertEqual(
            parity.stable_manifest(self.manifest), parity.stable_manifest(candidate),
        )
        (self.candidate / "manifest.json").write_text(
            json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        self.assertEqual(
            parity.compare_outputs(self.baseline, self.candidate), sorted(self.artifacts),
        )

    def test_stable_manifest_fields_and_numeric_types_cannot_change(self) -> None:
        changes = (
            (("schema_version",), 2),
            (("experiment",), "different experiment"),
            (("configuration", "config_hash"), "d" * 64),
            (("configuration", "path"), str(self.candidate / "other-config.json")),
            (("seeds", "base_seed"), 32),
            (("seeds", "instance_seeds"), [32]),
            (("algorithms", "greedy", "version"), "2"),
            (("algorithms", "greedy", "options"), {"new_option": True}),
            (("algorithms", "greedy", "enabled"), 1),
            (("execution", "planned_instances"), True),
            (("execution", "planned_runs"), 2.0),
            (("summary_contract", "aggregation_unit"), "run"),
            (("timing", "new_stable_field"), 1),
            (("new_contract",), {"policy": "changed"}),
        )
        for path, value in changes:
            with self.subTest(field=".".join(path), value=value):
                candidate = copy.deepcopy(self.manifest)
                target = candidate
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                self.assertNotEqual(
                    parity.stable_manifest(self.manifest), parity.stable_manifest(candidate),
                )
                self._write_manifest(self.candidate, candidate)
                with self.assertRaises(ValueError):
                    parity.compare_outputs(self.baseline, self.candidate)

    def test_removing_a_contract_is_not_execution_metadata(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        del candidate["summary_contract"]
        self._write_manifest(self.candidate, candidate)
        with self.assertRaises(ValueError):
            parity.compare_outputs(self.baseline, self.candidate)

    def test_artifact_content_formatting_and_csv_row_order_must_match(self) -> None:
        changes = {
            "raw_results.csv": b"run_id,coverage\nr1,8\nr0,7\n",
            "instances.csv": b"instance_id,seed\ni0,32\n",
            "summary.csv": b"algorithm,mean_coverage\ngreedy,7.0\n",
            "greedy_failure_statistics.csv": b"failures,instances\n0,1\n",
            "search_comparison.csv": b"instance_id,node_ratio\ni0,0.6000000000\n",
            "stochastic_summary.csv": b"instance_id,mean_coverage\ni0,8.0000000000\n",
            "results_summary.md": b"# Results\n\nRecorded coverage: 8.\n",
            "runtime_scaling.svg": b'<svg><text x="2">7</text></svg>\n',
        }
        for name, data in changes.items():
            with self.subTest(artifact=name):
                (self.candidate / name).write_bytes(data)
                with self.assertRaises(ValueError):
                    parity.compare_outputs(self.baseline, self.candidate)
                (self.candidate / name).write_bytes(self.artifacts[name])

    def test_added_and_missing_files_are_rejected(self) -> None:
        extra = self.candidate / "nested" / "unexpected.csv"
        extra.parent.mkdir()
        extra.write_bytes(b"extra\n")
        with self.subTest(change="added nested file"), self.assertRaises(ValueError):
            parity.compare_outputs(self.baseline, self.candidate)
        extra.unlink()
        (self.candidate / "summary.csv").unlink()
        with self.subTest(change="missing file"), self.assertRaises(ValueError):
            parity.compare_outputs(self.baseline, self.candidate)

    def test_manifest_inventory_entries_sizes_and_digests_cannot_change(self) -> None:
        for change in ("extra", "missing", "size", "digest", "size numeric type"):
            with self.subTest(change=change):
                candidate = copy.deepcopy(self.manifest)
                outputs = candidate["outputs"]
                declaration = outputs["summary.csv"]
                if change == "extra":
                    outputs["extra.csv"] = dict(declaration)
                elif change == "missing":
                    del outputs["summary.csv"]
                elif change == "size":
                    declaration["bytes"] += 1
                elif change == "digest":
                    declaration["sha256"] = "e" * 64
                else:
                    declaration["bytes"] = float(declaration["bytes"])
                self._write_manifest(self.candidate, candidate)
                with self.assertRaises(ValueError):
                    parity.compare_outputs(self.baseline, self.candidate)

    def test_identical_but_stale_inventory_does_not_establish_parity(self) -> None:
        for field, value in (("bytes", 0), ("sha256", "f" * 64)):
            with self.subTest(field=field):
                stale = copy.deepcopy(self.manifest)
                stale["outputs"]["summary.csv"][field] = value
                for output in (self.baseline, self.candidate):
                    self._write_manifest(output, stale)
                with self.assertRaises(ValueError):
                    parity.compare_outputs(self.baseline, self.candidate)

    def test_refreshed_manifest_cannot_hide_modified_artifact_bytes(self) -> None:
        data = b"# Results\n\nChanged report.\n"
        (self.candidate / "results_summary.md").write_bytes(data)
        refreshed = copy.deepcopy(self.manifest)
        refreshed["outputs"]["results_summary.md"] = {
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        }
        self._write_manifest(self.candidate, refreshed)
        with self.assertRaises(ValueError):
            parity.compare_outputs(self.baseline, self.candidate)


if __name__ == "__main__":
    unittest.main()
