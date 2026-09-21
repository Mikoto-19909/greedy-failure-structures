"""Run native contract tests; missing kernels, empty discovery and skips fail."""
from __future__ import annotations

from importlib import import_module
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    try:
        native = import_module("maxcover_structure_native")
        for name in ("counts", "counts_packed", "greedy", "lazy_greedy"):
            if not callable(getattr(native, name, None)):
                raise ImportError(f"installed native extension lacks {name}; rebuild ./native/structure")
    except ImportError as error:
        print(f"Rust verification unavailable: {error}", file=sys.stderr)
        return 1
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*rust.py")
    if suite.countTestCases() == 0:
        print("Rust verification discovered no tests", file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.skipped:
        print("Rust verification requires zero skipped tests", file=sys.stderr)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
