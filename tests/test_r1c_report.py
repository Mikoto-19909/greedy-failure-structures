"""Reproduction paths stay executable when reports are written elsewhere."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

from render_r1c_confirmation_report import reproduction_path


class R1cReportPathTests(unittest.TestCase):
    def test_nested_data_paths_resolve_from_repository_not_report_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary).resolve()
            data = repo / "results" / "review output" / "render-data"
            data.mkdir(parents=True)
            config = data / "config.json"
            config.write_text('{"sample": "path-regression"}', encoding="utf-8")
            with patch("render_r1c_confirmation_report.ROOT", repo):
                argument = reproduction_path(config)
                # Exercise opening the produced argument from the documented cwd.
                self.assertEqual((repo / argument).read_bytes(), config.read_bytes())
                self.assertEqual((repo / reproduction_path(data)).resolve(), data)

    def test_external_data_remains_an_absolute_executable_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            repo = parent / "repo"
            data = parent / "external data"
            repo.mkdir()
            data.mkdir()
            config = data / "config.json"
            config.write_text("{}", encoding="utf-8")
            with patch("render_r1c_confirmation_report.ROOT", repo):
                argument = Path(reproduction_path(config))
                self.assertTrue(argument.is_absolute())
                self.assertEqual(argument.read_bytes(), config.read_bytes())


if __name__ == "__main__":
    unittest.main()
