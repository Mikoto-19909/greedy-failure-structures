# Evidence snapshot: instance-contracts-study-v1

Source commit: `5c3f44fe035f71daac1ca0664987830a1aa09b6b`

## Run and verification notes

# InstanceRecord extraction study evidence

This snapshot preserves the 2026-09-10 exploratory study cited by PR #63.
The publication checkout is recorded as `Source commit` in FREEZE.md; the actual
study baseline is **2c4c3dec4beb3e6c1f9abe07de6a644c6e4bf49c**.
`baseline-source.zip` contains its `src/`, `tests/`, `configs/`, `pyproject.toml`
and `LICENSES/`, exported with `git archive`. It is sufficient for the commands
below and does not depend on the old commit remaining reachable on another branch.

## Contents and scope

- `inputs.json`: the original 13 representative records and CSV inputs.
- `probe.py`: original deterministic mutations and process-local prototypes.
- `old_instances_protocol4.pickle`, `old_instances_protocol5.pickle`: original
  baseline serialization fixtures used by the probe.
- `baseline.json`, `inplace.json`, `stage1.json`, `stage2.json`, `reordered.json`:
  complete original observations, including all 8,790 outcomes per version.
- `summary.json`: original study summary, preserved unchanged.
- `run_checks.py` and three `*-existing-tests.json` files: the selected existing
  behavior tests and their original execution summaries.
- `stage2-incomplete-name-bindings.json`: historical failed-prototype capture.
  The failed prototype's source was not retained; its 939 differences can be
  inspected against baseline but that intermediate failure is not replayed.
- `reproduce.py`: new restoration/comparison entry point added for PR #63.

The two pickle files are local fixtures produced by this study's baseline code.
The replay loads them as part of the explicit compatibility check.

## Reproduce from the evidence checkout

Use CPython 3.12.14 (64-bit Windows was used for the original and repeated run).
The selected checks use the standard library; no package installation is needed.
From the root of this evidence checkout:

```console
python results/instance_contracts_research/reproduce.py ../instance-study-replay
```

The destination must not exist. The command restores the pinned source and copies
inputs into that new directory. It sets `PYTHONHASHSEED=0`, `PYTHONUTF8=1` and
`PYTHONDONTWRITEBYTECODE=1` in each child process. Original archived observations
are never overwritten. Run without Python's `-O` flag because checks use asserts.

Expected result: 8,790 cases per version, baseline 979 accepted / 7,811 rejected;
inplace/stage1/stage2 have zero outcome differences; reordered has 13. The
baseline, inplace and stage2 modes each pass 15 existing tests, with no skips.
All archived fields are compared. The original reordered capture predates the
two added type-hint diagnostic fields, so only those two extra fields are allowed
in its replay output; all other modes compare the complete field set.

## Verification on 2026-09-15

Executed the command above in a fresh restoration directory with Python 3.12.14:
five full observations reproduced and all three sets of 15 tests passed.
The first comparison attempt exposed the two absent diagnostic fields in the
older reordered capture. Inspection confirmed every shared field was equal;
the comparison now explicitly allows just those two additions for reordered.
The unchanged archived data, scripts, inputs and pickle fixtures remain separate
from regenerated output. Existing destination rejection was also exercised.

This is finite engineering coverage, not a probability estimate or proof of all
future changes. No formal research experiment was rerun. The replay validates
the central outcome/shape/pickle observations and selected tests; it does not
independently repeat every historical manual AST or editorial observation.
Licenses are included with the baseline source: code/data MIT, prose CC BY 4.0.

## Included evidence

- results/instance_contracts_research/README.md (3728 bytes)
- results/instance_contracts_research/baseline-existing-tests.json (72 bytes)
- results/instance_contracts_research/baseline-source.zip (510855 bytes)
- results/instance_contracts_research/baseline.json (2892148 bytes)
- results/instance_contracts_research/inplace-existing-tests.json (72 bytes)
- results/instance_contracts_research/inplace.json (2892157 bytes)
- results/instance_contracts_research/inputs.json (41424 bytes)
- results/instance_contracts_research/old_instances_protocol4.pickle (5425 bytes)
- results/instance_contracts_research/old_instances_protocol5.pickle (5425 bytes)
- results/instance_contracts_research/probe.py (12501 bytes)
- results/instance_contracts_research/reordered.json (2889502 bytes)
- results/instance_contracts_research/reproduce.py (3293 bytes)
- results/instance_contracts_research/run_checks.py (1619 bytes)
- results/instance_contracts_research/stage1.json (2890654 bytes)
- results/instance_contracts_research/stage2-existing-tests.json (72 bytes)
- results/instance_contracts_research/stage2-incomplete-name-bindings.json (1986440 bytes)
- results/instance_contracts_research/stage2.json (2889534 bytes)
- results/instance_contracts_research/summary.json (3042 bytes)

This prepared snapshot is local until publish verifies the remote commit and tree.
Git integrity does not establish scientific correctness.
