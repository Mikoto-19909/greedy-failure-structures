"""Recheck the archived study in a new directory without overwriting evidence."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def main():
    evidence = Path(__file__).resolve().parent
    destination = Path(sys.argv[1]).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(evidence / "baseline-source.zip") as archive:
        archive.extractall(destination)
    output = destination / "results/instance_contracts_research"
    output.mkdir(parents=True)
    for name in ("probe.py", "run_checks.py", "inputs.json",
                 "old_instances_protocol4.pickle", "old_instances_protocol5.pickle"):
        shutil.copyfile(evidence / name, output / name)
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    modes = ("baseline", "inplace", "stage1", "stage2", "reordered")
    observed = {}
    for mode in modes:
        subprocess.run([sys.executable, str(output / "probe.py"), mode],
                       cwd=destination, env=env, check=True)
        observed[mode] = json.loads((output / (mode + ".json")).read_text(encoding="utf-8"))
        archived = json.loads((evidence / (mode + ".json")).read_text(encoding="utf-8"))
        # The earlier reordered capture predates the two type-hint diagnostics.
        # Compare every archived field; allow only these documented additions.
        extra = observed[mode].keys() - archived.keys()
        allowed = {"public_type_hints", "private_type_hints_with_namespace"} if mode == "reordered" else set()
        assert extra <= allowed, (mode, extra)
        if any(observed[mode].get(key) != value for key, value in archived.items()):
            keys = [key for key in archived
                    if archived.get(key) != observed[mode].get(key)]
            raise AssertionError(f"{mode}: archived observation differs in {keys}")
    baseline = observed["baseline"]
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    assert len(baseline["outcomes"]) == summary["cases_per_variant"] == 8790
    assert baseline["accepted"] == summary["accepted"] == 979
    assert len(baseline["outcomes"]) - baseline["accepted"] == summary["rejected"] == 7811
    for mode in modes[1:]:
        outcomes = observed[mode]["outcomes"]
        assert outcomes.keys() == baseline["outcomes"].keys()
        differences = sum(value != outcomes[key] for key, value in baseline["outcomes"].items())
        assert differences == summary["variants"][mode]["differences"]
        assert differences == (13 if mode == "reordered" else 0)
    for mode in ("baseline", "inplace", "stage2"):
        subprocess.run([sys.executable, str(output / "run_checks.py"), mode],
                       cwd=destination, env=env, check=True)
        name = mode + "-existing-tests.json"
        actual = json.loads((output / name).read_text(encoding="utf-8"))
        assert actual == json.loads((evidence / name).read_text(encoding="utf-8"))
        assert actual == {"tests": 15, "failures": 0, "errors": 0, "skipped": 0, "success": True}
    print("PASS: five archived observations reproduced; A/B/C differences 0; negative control 13; 3 x 15 tests pass.")


if __name__ == "__main__":
    main()
