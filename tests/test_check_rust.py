"""Native acceptance must fail instead of reporting absent execution as success."""
from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_check_entry", ROOT / "scripts/check_rust.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class RustAcceptanceTests(unittest.TestCase):
    def test_missing_extension_fails_without_site_packages(self):
        result = subprocess.run([sys.executable, "-I", "-S", str(ROOT / "scripts/check_rust.py")],
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Rust verification unavailable", result.stderr)

    def test_stale_extension_empty_discovery_and_skips_fail(self):
        fake = SimpleNamespace(counts=lambda: None)
        with contextlib.redirect_stderr(io.StringIO()), patch.object(check, "import_module", return_value=fake):
            self.assertEqual(check.main(), 1)
            fake.greedy = fake.lazy_greedy = lambda: None
            with patch.object(unittest.defaultTestLoader, "discover", return_value=unittest.TestSuite()):
                self.assertEqual(check.main(), 1)
            class Skipped(unittest.TestCase):
                @unittest.skip("deliberate missing execution")
                def runTest(self):
                    pass
            with patch.object(unittest.defaultTestLoader, "discover", return_value=unittest.TestSuite([Skipped()])):
                self.assertEqual(check.main(), 1)


if __name__ == "__main__":
    unittest.main()
