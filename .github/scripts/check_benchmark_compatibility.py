"""Compare pinned old code and the working implementation on one frozen checkpoint.

The baseline Git object must be available locally; this tool never fetches or
changes a checkout. Both versions summarize identical CSV bytes using the same
absolute configuration path in separate interpreters. No algorithm may execute.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/benchmark_compatibility"
BASELINE_COMMIT = "c40658d4cbc16b45fb640b1d97c03688baee16b7"
SNAPSHOT_PATHS = ("src/maxcover", "run_project.py", "pyproject.toml", ".github/scripts/validate_benchmark_output.py")
CANONICAL_FILES = ("raw_results.csv", "instances.csv")

SUMMARIZE = r'''
import json, sys
from pathlib import Path
source, config, output = map(Path, sys.argv[1:])
sys.path.insert(0, str(source / "src"))
import maxcover.benchmark as benchmark
import maxcover.reporting as reporting
def forbid_execution(task):
    raise AssertionError("summarize attempted to execute an algorithm")
benchmark._execute_task = forbid_execution
result = benchmark.summarize_benchmark(config, output)
print(json.dumps({"benchmark_module": str(Path(benchmark.__file__).resolve()),
                  "reporting_module": str(Path(reporting.__file__).resolve()),
                  "runs": len(result.rows)}))
'''


def export_baseline(destination: Path) -> None:
    """Export exactly the pinned source from Git, without altering worktrees."""
    archive = subprocess.run(
        ["git", "archive", "--format=tar", BASELINE_COMMIT, "--", *SNAPSHOT_PATHS],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        for member in bundle:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("baseline archive has a non-relative path")
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = bundle.extractfile(member)
                assert stream is not None
                target.write_bytes(stream.read())
            else:
                raise ValueError(f"unsupported baseline archive entry: {member.name}")


def verify_fixture() -> dict[str, Any]:
    metadata: dict[str, Any] = json.loads((FIXTURE / "checkpoint.json").read_bytes())
    if metadata["baseline_commit"] != BASELINE_COMMIT:
        raise ValueError("checkpoint source commit differs from the pinned baseline")
    for name in ("config.json", *CANONICAL_FILES):
        payload = (FIXTURE / name).read_bytes()
        expected = metadata["files"][name]
        if len(payload) != expected["bytes"] or hashlib.sha256(payload).hexdigest() != expected["sha256"]:
            raise ValueError(f"frozen checkpoint changed: {name}")
    return metadata


def _run_summarize(source: Path, config: Path, output: Path) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-c", SUMMARIZE, str(source), str(config), str(output)],
        cwd=source, check=True, capture_output=True, text=True, encoding="utf-8",
    )
    observation: dict[str, Any] = json.loads(result.stdout)
    for key, filename in (("benchmark_module", "benchmark.py"), ("reporting_module", "reporting.py")):
        if Path(observation[key]) != (source / "src/maxcover" / filename).resolve():
            raise ValueError(f"summarize imported an unexpected implementation: {key}")
    sources = sorted((source / "src/maxcover").rglob("*.py"))
    sources.append(source / ".github/scripts/validate_benchmark_output.py")
    observation["source_sha256"] = {
        path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sources
    }
    return observation


def stable_manifest(manifest: dict[str, Any]) -> str:
    """Ignore only declared execution metadata, preserving types and all contracts."""
    value = json.loads(json.dumps(manifest))
    value.pop("git", None)
    value.pop("environment", None)
    for key in ("started_at", "ended_at", "duration_seconds"):
        value.get("timing", {}).pop(key, None)
    # JSON serialization distinguishes booleans, integers and floating values.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _inventory(output: Path) -> dict[str, bytes]:
    return {path.relative_to(output).as_posix(): path.read_bytes()
            for path in sorted(output.rglob("*")) if path.is_file()}


def compare_outputs(baseline: Path, candidate: Path) -> list[str]:
    left, right = _inventory(baseline), _inventory(candidate)
    if set(left) != set(right):
        raise ValueError(f"output file set changed: {sorted(set(left) ^ set(right))}")
    for name in sorted(left):
        if name != "manifest.json" and left[name] != right[name]:
            raise ValueError(f"deterministic artifact bytes changed: {name}")
    old_manifest, new_manifest = (json.loads(items["manifest.json"]) for items in (left, right))
    for manifest, files in ((old_manifest, left), (new_manifest, right)):
        if set(manifest["outputs"]) != set(files) - {"manifest.json"}:
            raise ValueError("manifest inventory does not match generated files")
        for name, declaration in manifest["outputs"].items():
            if (declaration["bytes"] != len(files[name])
                    or declaration["sha256"] != hashlib.sha256(files[name]).hexdigest()):
                raise ValueError(f"manifest digest or size disagrees with bytes: {name}")
    if stable_manifest(old_manifest) != stable_manifest(new_manifest):
        raise ValueError("stable Manifest fields, contracts or output declarations changed")
    return sorted(set(left) - {"manifest.json"})


def check_compatibility(output: Path) -> dict[str, Any]:
    metadata = verify_fixture()
    if output.exists() and any(output.iterdir()):
        raise ValueError("compatibility output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    config = (FIXTURE / "config.json").resolve()
    observations = {}
    with tempfile.TemporaryDirectory(prefix="maxcover-pinned-baseline-") as temporary:
        baseline_source = Path(temporary)
        export_baseline(baseline_source)
        for relative, expected in metadata["source_sha256"].items():
            if hashlib.sha256((baseline_source / relative).read_bytes()).hexdigest() != expected:
                raise ValueError(f"exported baseline source differs: {relative}")
        for label, source in (("baseline", baseline_source), ("candidate", ROOT)):
            destination = output / label
            destination.mkdir()
            for filename in CANONICAL_FILES:
                shutil.copyfile(FIXTURE / filename, destination / filename)
            observations[label] = _run_summarize(source, config, destination)
            if observations[label]["runs"] != metadata["run_count"]:
                raise ValueError(f"{label}: run count differs from frozen checkpoint")
            for filename in CANONICAL_FILES:
                if (destination / filename).read_bytes() != (FIXTURE / filename).read_bytes():
                    raise ValueError(f"{label}: summarize changed canonical input {filename}")
            validated = subprocess.run(
                [sys.executable, str(source / ".github/scripts/validate_benchmark_output.py"),
                 "--config", str(config), "--output", str(destination)],
                cwd=source, check=True, capture_output=True, text=True, encoding="utf-8",
            )
            (output / f"{label}_validator.txt").write_text(validated.stdout, encoding="utf-8", newline="\n")
    artifacts = compare_outputs(output / "baseline", output / "candidate")
    if artifacts != metadata["expected_artifacts"]:
        raise ValueError("generated file inventory differs from the frozen baseline inventory")
    report = {
        "status": "PASS", "baseline_commit": BASELINE_COMMIT,
        "candidate_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                           check=True, capture_output=True, text=True).stdout.strip(),
        "candidate_dirty": bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                                               check=True, capture_output=True, text=True).stdout.strip()),
        "shared_config_path": str(config), "observed_implementations": observations,
        "compared_artifacts": artifacts,
        "manifest_policy": "equal except git, environment and timing started_at/ended_at/duration_seconds",
    }
    (output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        report = check_compatibility(arguments.output.resolve())
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f"benchmark compatibility failed: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stdout, error.stderr, file=sys.stderr)
        return 1
    print(f"PASS: {len(report['compared_artifacts'])} artifact files match pinned baseline bytes; stable Manifest matches.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
