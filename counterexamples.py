"""Run counterexample experiments from a checkout without installing the package."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "analysis"), str(ROOT / "src")]
from counterexample_workflow import main

if __name__ == "__main__":
    raise SystemExit(main())
