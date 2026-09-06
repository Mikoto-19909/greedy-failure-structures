"""Serial, local comparison of the fixed pre/post gate-removal revisions.

Preparation is excluded from command timings. The five frozen R1 task files are
copied byte-for-byte to both clones. No pushes or source-repository writes occur.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BEFORE = "891c389287bd4fa6adf21a712b8ddab5aa2a4a39"
AFTER = "285c3b09d8e585eb36f7df9dc986728ab4f12550"
TASK_FILES = (
    "analysis/greedy_failure_paths.py",
    "analysis/validate_greedy_failure_paths.py",
    "analysis/r1_prefix_exchange_design.json",
    "analysis/r1_prefix_exchange_design.md",
    "tests/test_greedy_failure_paths.py",
)
DATA_FILES = ("paths.jsonl", "instance_summary.csv", "case_summary.csv")
TIME_FIELDS = (
    "phase", "workload", "repetition", "order", "variant", "elapsed_seconds",
    "exit_code", "output_directory", "log", "command",
)


def write_csv(path: Path, rows: list[dict], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class Measurement:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.output = args.output.resolve()
        self.rows: list[dict] = []
        self.pairs: list[dict] = []
        self.equivalence: list[str] = []
        self.clones = {name: self.output / name for name in ("before", "after")}
        self.env = os.environ.copy()
        for prefix in ("AUTHOR", "COMMITTER"):
            for key in ("NAME", "EMAIL", "DATE"):
                self.env.pop(f"GIT_{prefix}_{key}", None)
        self.env.update({
            "PYTHONPATH": os.pathsep.join((str(ROOT / "results/typecheck-deps"),
                                          str(ROOT / "results/analysis-deps"))),
            "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "MPLCONFIGDIR": str(self.output / "matplotlib-cache"),
            "GIT_CONFIG_GLOBAL": str(self.output / "empty-gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
        })

    def source_git(self, *args: str) -> bytes:
        source = self.args.source.resolve()
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={source.as_posix()}", "-C", str(source), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))
        return completed.stdout

    def prepare(self) -> None:
        if self.args.resume:
            self.resume_measurements()
            return
        if self.output.exists() and any(path.name not in {"logs", "empty-gitconfig"}
                                        for path in self.output.iterdir()):
            raise ValueError("measurement output must be new or empty; do not overwrite a run")
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "logs").mkdir(exist_ok=True)
        (self.output / "empty-gitconfig").write_text("", encoding="utf-8")
        for revision in (BEFORE, AFTER):
            if self.source_git("cat-file", "-t", revision).strip() != b"commit":
                raise ValueError(f"missing fixed revision: {revision}")
        changed = self.source_git("diff", "--name-only", BEFORE, AFTER, "--", "src/maxcover").decode().splitlines()
        protected = [name for name in changed if any(
            term in Path(name).name for term in ("algorithms", "generators", "generator_", "model.py", "config.py")
        )]
        if protected:
            raise ValueError(f"algorithm or input-generator changes: {protected}")
        # Use the contributor's recorded identity, never a synthetic AI identity.
        identity = {}
        for key in ("name", "email"):
            try:
                value = self.source_git("config", "--get", f"user.{key}").decode("utf-8").strip()
            except RuntimeError:
                value = ""
            if not value:
                raise ValueError(f"source repository has no configured user.{key}; local commit cannot proceed")
            identity[key] = value
        self.configure_identity(identity)
        task_bytes = {name: (ROOT / name).read_bytes() for name in TASK_FILES}
        for name, revision in (("before", BEFORE), ("after", AFTER)):
            clone = self.clones[name]
            completed = subprocess.run(
                ["git", "-c", f"safe.directory={self.args.source.resolve().as_posix()}",
                 "-c", f"safe.directory={self.args.source.resolve().as_posix()}/.git",
                 "clone", "--no-hardlinks", "--no-checkout", str(self.args.source.resolve()), str(clone)],
                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            (self.output / "logs" / f"prepare-{name}.log").write_bytes(completed.stdout)
            if completed.returncode:
                raise RuntimeError(f"local clone failed for {name}; see preparation log")
            for command in (
                ["git", "checkout", "-b", "codex/measured-r1-task", revision],
                ["git", "config", "core.autocrlf", "false"],
                ["git", "config", "commit.gpgsign", "false"],
                ["git", "config", "user.name", identity["name"]],
                ["git", "config", "user.email", identity["email"]],
            ):
                subprocess.run(command, cwd=clone, env=self.env, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for filename, payload in task_bytes.items():
                target = clone / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
        for filename in TASK_FILES:
            if (self.clones["before"] / filename).read_bytes() != (self.clones["after"] / filename).read_bytes():
                raise ValueError(f"task file mismatch: {filename}")
        environment = subprocess.run(
            [sys.executable, "-c", "import mypy.version, matplotlib; print('mypy='+mypy.version.__version__); print('matplotlib='+matplotlib.__version__)"],
            env=self.env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout.decode("utf-8")
        text = (f"Python: {sys.version}\nPlatform: {platform.platform()}\n"
                f"Before: {BEFORE}\nAfter: {AFTER}\nPairs per workload: {self.args.pairs}\n"
                "Algorithm/model/config/generator files unchanged between revisions.\n"
                "Five task files copied identically; preparation and dependency imports excluded.\n"
                + environment)
        (self.output / "environment.txt").write_text(text, encoding="utf-8")
        self.equivalence.append("Five frozen task files are byte-identical in both clones.")
        print("Prepared independent clones; Python, dependencies and unchanged algorithm inputs verified.", flush=True)

    def configure_identity(self, identity: dict[str, str]) -> None:
        # A private global config supplies defaults while fixture-local Git
        # identities can override them; author/committer environment cannot.
        contents = "[user]\n" + "".join(
            f"\t{key} = {json.dumps(value, ensure_ascii=False)}\n" for key, value in identity.items()
        )
        Path(self.env["GIT_CONFIG_GLOBAL"]).write_text(contents, encoding="utf-8")

    def resume_measurements(self) -> None:
        with (self.output / "raw_times.csv").open(encoding="utf-8", newline="") as handle:
            self.rows = list(csv.DictReader(handle))
        if any(row["phase"] == "workflow" for row in self.rows):
            raise ValueError("cannot replay a workflow that already started")
        for row in self.rows:
            for field in ("repetition", "order", "exit_code"):
                row[field] = int(row[field])
        paired_path = self.output / "paired_times.csv"
        self.pairs = []
        if paired_path.exists():
            with paired_path.open(encoding="utf-8", newline="") as handle:
                self.pairs = list(csv.DictReader(handle))
        for row in self.pairs:
            row["repetition"] = int(row["repetition"])
            for field in ("before_seconds", "after_seconds", "after_minus_before_seconds", "after_over_before"):
                row[field] = float(row[field])
        for variant, revision in (("before", BEFORE), ("after", AFTER)):
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.clones[variant], env=self.env, text=True).strip()
            if head != revision:
                raise ValueError("clone revision changed since the interrupted measurements")
            for filename in TASK_FILES:
                if (ROOT / filename).read_bytes() != (self.clones[variant] / filename).read_bytes():
                    raise ValueError(f"frozen task changed since measurement: {filename}")
        identity = {}
        for key in ("name", "email"):
            value = subprocess.check_output(["git", "config", "--get", f"user.{key}"],
                                            cwd=self.clones["before"], env=self.env, text=True).strip()
            identity[key] = value
        self.configure_identity(identity)
        for pair in self.pairs:
            outputs = {variant: next(row["output_directory"] for row in self.rows
                                     if row["phase"] == "measurement" and row["workload"] == pair["workload"]
                                     and row["repetition"] == pair["repetition"] and row["variant"] == variant
                                     and row["exit_code"] == 0) for variant in self.clones}
            self.equal_outputs(pair["workload"], outputs, f"retained-pair-{pair['repetition']}/{pair['workload']}")
        print(f"Resuming after {len(self.pairs)} complete pairs; failed/partial attempts remain in raw_times.csv.", flush=True)

    def command(self, variant: str, phase: str, workload: str, repetition: int,
                order: int, command: list[str], output: str = "") -> dict:
        label = f"{phase}-{workload}-{repetition}-{order}-{variant}"
        attempts = sum(row["phase"] == phase and row["workload"] == workload
                       and row["repetition"] == repetition and row["variant"] == variant
                       and row["order"] == order for row in self.rows)
        if attempts:
            label += f"-attempt-{attempts + 1}"
        log = self.output / "logs" / f"{label}.log"
        print(f"START {label}", flush=True)
        with log.open("wb") as handle:
            start = time.perf_counter()
            completed = subprocess.run(command, cwd=self.clones[variant], env=self.env,
                                       stdout=handle, stderr=subprocess.STDOUT)
            elapsed = time.perf_counter() - start
        row = {"phase": phase, "workload": workload, "repetition": repetition,
               "order": order, "variant": variant, "elapsed_seconds": f"{elapsed:.9f}",
               "exit_code": completed.returncode, "output_directory": output,
               "log": str(log.relative_to(self.output)),
               "command": subprocess.list2cmdline(command)}
        self.rows.append(row)
        write_csv(self.output / "raw_times.csv", self.rows, TIME_FIELDS)
        print(f"END {label}: {elapsed:.3f}s exit={completed.returncode}", flush=True)
        return row

    @staticmethod
    def ensure_success(row: dict) -> None:
        if row["exit_code"] != 0:
            raise RuntimeError(f"command failed: {row['phase']}/{row['workload']}/{row['variant']}; see {row['log']}")

    def experimental_command(self, kind: str, directory: str) -> list[str]:
        if kind == "r1":
            return [sys.executable, "analysis/greedy_failure_paths.py", "--design",
                    "analysis/r1_prefix_exchange_design.json", "--output", directory, "--no-plot"]
        return [sys.executable, "run_project.py", "benchmark", "--config", "configs/quick.json",
                "--output", directory, "--workers", "1"]

    def equal_outputs(self, kind: str, outputs: dict[str, str], note: str) -> None:
        roots = {variant: self.clones[variant] / directory for variant, directory in outputs.items()}
        if kind == "r1":
            for name in DATA_FILES:
                if (roots["before"] / name).read_bytes() != (roots["after"] / name).read_bytes():
                    raise ValueError(f"R1 data mismatch: {note}/{name}")
        else:
            tables = {}
            for variant in roots:
                with (roots[variant] / "raw_results.csv").open(encoding="utf-8", newline="") as handle:
                    tables[variant] = [{k: v for k, v in row.items() if k != "runtime_seconds"}
                                       for row in csv.DictReader(handle)]
            if tables["before"] != tables["after"]:
                raise ValueError(f"stable quick records mismatch: {note}")
            if (roots["before"] / "instances.csv").read_bytes() != (roots["after"] / "instances.csv").read_bytes():
                raise ValueError(f"quick instance data mismatch: {note}")
        self.equivalence.append(f"{note}: stable records match.")

    def microbenchmarks(self) -> None:
        for kind in ("fresh", "resume", "r1"):
            warm_outputs = {}
            for order, variant in enumerate(("before", "after"), 1):
                directory = f"results/speed/warm-{kind}"
                previous = next((row for row in self.rows if row["phase"] == "warmup"
                                 and row["workload"] == kind and row["variant"] == variant
                                 and row["exit_code"] == 0), None)
                if previous is not None:
                    warm_outputs[variant] = previous["output_directory"]
                    continue
                if kind == "resume":
                    seed = self.command(variant, "prepare", "resume-checkpoint", 0, order,
                                        self.experimental_command("fresh", directory), directory)
                    self.ensure_success(seed)
                row = self.command(variant, "warmup", kind, 0, order,
                                   self.experimental_command(kind, directory), directory)
                self.ensure_success(row)
                warm_outputs[variant] = directory
            self.equal_outputs(kind, warm_outputs, f"warmup/{kind}")
            for repetition in range(1, self.args.pairs + 1):
                if any(row["workload"] == kind and row["repetition"] == repetition for row in self.pairs):
                    continue
                order_names = ("before", "after") if repetition % 2 else ("after", "before")
                measured = {}
                directories = {}
                attempt = 1 + max((sum(row["phase"] == "measurement" and row["workload"] == kind
                                       and row["repetition"] == repetition and row["variant"] == variant
                                       for row in self.rows) for variant in self.clones), default=0)
                for order, variant in enumerate(order_names, 1):
                    directory = (warm_outputs[variant] if kind == "resume"
                                 else f"results/speed/{kind}-{repetition}-attempt-{attempt}")
                    row = self.command(variant, "measurement", kind, repetition, order,
                                       self.experimental_command(kind, directory), directory)
                    self.ensure_success(row)
                    measured[variant] = float(row["elapsed_seconds"])
                    directories[variant] = directory
                self.equal_outputs(kind, directories, f"pair-{repetition}/{kind}")
                before, after = measured["before"], measured["after"]
                self.pairs.append({"workload": kind, "repetition": repetition,
                                   "before_seconds": before, "after_seconds": after,
                                   "after_minus_before_seconds": after - before,
                                   "after_over_before": after / before})
                write_csv(self.output / "paired_times.csv", self.pairs,
                          ("workload", "repetition", "before_seconds", "after_seconds",
                           "after_minus_before_seconds", "after_over_before"))
        self.save_summary()

    def workflow(self, variant: str) -> dict:
        revision = BEFORE if variant == "before" else AFTER
        steps: list[tuple[str, list[str]]] = [
            ("stage-task", ["git", "add", "--", *TASK_FILES]),
        ]
        if variant == "before":
            steps += [("generate-license", [sys.executable, ".github/scripts/build_license_manifest.py"]),
                      ("stage-license", ["git", "add", "--", "LICENSE_MANIFEST.json"])]
        steps += [
            ("r1-analysis", self.experimental_command("r1", "results/speed/full-task")),
            ("r1-independent-validation", [sys.executable, "analysis/validate_greedy_failure_paths.py",
                                          "--design", "analysis/r1_prefix_exchange_design.json",
                                          "--output", "results/speed/full-task"]),
            ("unittest", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ]
        if variant == "before":
            steps += [
                ("content-check", [sys.executable, ".github/scripts/check_content_boundary.py", "--claim-mode", "evidence_backed_claims"]),
                ("license-check", [sys.executable, ".github/scripts/build_license_manifest.py", "--check"]),
            ]
        steps += [("mypy", [sys.executable, "-m", "mypy"]),
                  ("staged-whitespace", ["git", "diff", "--cached", "--check"])]
        executed = []
        workflow_start = time.perf_counter()
        for index, (name, command) in enumerate(steps, 1):
            executed.append(self.command(variant, "workflow", name, 1, index, command))
        checks_passed = all(row["exit_code"] == 0 for row in executed)
        commit = None
        if checks_passed:
            row = self.command(variant, "workflow", "local-commit", 1, len(executed) + 1,
                               ["git", "commit", "-m", "feat: add prefix and exchange research analysis"])
            executed.append(row)
            if row["exit_code"] == 0:
                commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.clones[variant],
                                                 env=self.env, text=True).strip()
                if variant == "before":
                    executed.append(self.command(
                        variant, "workflow", "commit-policy", 1, len(executed) + 1,
                        [sys.executable, ".github/scripts/check_commits.py", "--base", revision, "--head", "HEAD"],
                    ))
        completed = commit is not None and all(row["exit_code"] == 0 for row in executed)
        result = {"variant": variant, "completed": completed, "local_commit": commit,
                  "step_seconds": sum(float(row["elapsed_seconds"]) for row in executed),
                  "wall_seconds": time.perf_counter() - workflow_start,
                  "steps": len(executed),
                  "failed_steps": ",".join(row["workload"] for row in executed if row["exit_code"] != 0)}
        print(f"WORKFLOW {variant}: completed={completed}; failed={result['failed_steps'] or 'none'}", flush=True)
        return result

    def save_summary(self) -> None:
        rows = []
        for kind in ("fresh", "resume", "r1"):
            pairs = [row for row in self.pairs if row["workload"] == kind]
            if not pairs:
                continue
            rows.append({"workload": kind, "pairs": len(pairs),
                         "before_median_seconds": statistics.median(row["before_seconds"] for row in pairs),
                         "after_median_seconds": statistics.median(row["after_seconds"] for row in pairs),
                         "paired_median_change_seconds": statistics.median(row["after_minus_before_seconds"] for row in pairs),
                         "paired_median_after_over_before": statistics.median(row["after_over_before"] for row in pairs)})
        write_csv(self.output / "summary.csv", rows,
                  ("workload", "pairs", "before_median_seconds", "after_median_seconds",
                   "paired_median_change_seconds", "paired_median_after_over_before"))
        (self.output / "equivalence.txt").write_text("\n".join(self.equivalence) + "\n", encoding="utf-8")

    def run(self) -> int:
        self.prepare()
        if not self.args.workflow_only:
            self.microbenchmarks()
        outcomes = []
        for variant in ("before", "after"):
            outcomes.append(self.workflow(variant))
            write_csv(self.output / "workflow_summary.csv", outcomes,
                      ("variant", "completed", "local_commit", "step_seconds", "wall_seconds", "steps", "failed_steps"))
        completed = all(outcome["completed"] for outcome in outcomes)
        if completed:
            self.equal_outputs("r1", {variant: "results/speed/full-task" for variant in self.clones}, "full-task/r1")
        self.save_summary()
        limitations = (
            "Command timings include Python startup, validation, file IO and result writing.\n"
            "Warm resume reuses one complete checkpoint per variant. Fresh/R1 outputs use distinct directories.\n"
            "Seven serial paired observations per command; alternating order reduces, but cannot remove, machine drift.\n"
            "Complete workflows were run once each, before then after; compare successful completion, not fast failures.\n"
            "Full workflow measures repeatable local execution/checks/commit only, not writing, reasoning, review or CI/network waits.\n"
            "Mypy starts without a cloned cache, whereas shared OS/dependency caches may favor the later workflow.\n"
            "Preparation, clone copying and dependency installation are excluded. No external publishing occurred.\n"
            "The old/new R1 tools are identical; their existing core_overlap input loaders intentionally differ.\n"
            "Aborted paired attempts are retained in raw_times.csv, excluded from paired_times.csv, and both members are remeasured.\n"
        )
        (self.output / "limitations.txt").write_text(limitations, encoding="utf-8")
        if completed:
            print("Measurement finished. See summary.csv, paired_times.csv, raw_times.csv and workflow_summary.csv.", flush=True)
        else:
            print("Measurement incomplete: a workflow failed; see workflow_summary.csv and step logs.", flush=True)
        return 0 if completed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "results/gate_speed_comparison")
    parser.add_argument("--pairs", type=int, default=7)
    parser.add_argument("--resume", action="store_true", help="resume interrupted microbenchmarks without replaying completed pairs")
    parser.add_argument("--workflow-only", action="store_true", help="prepare clean clones and measure complete workflows only")
    args = parser.parse_args()
    if args.pairs < 1:
        parser.error("--pairs must be positive")
    try:
        return Measurement(args).run()
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Measurement stopped: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
