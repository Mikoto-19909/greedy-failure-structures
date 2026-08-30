# Lazy Greedy Functional Test Report

This document records the verification process for the deterministic
`lazy_greedy` algorithm. It is a functional and contract report, not a
performance result or a research conclusion.

## Scope

The test process covers five layers:

1. The implementation must reproduce the dense classical Greedy sequence,
   including fixed index tie-breaking.
2. The returned solution must satisfy the common `Solution` contract and the
   metadata envelope.
3. The registry, package-root export, configuration parser and bundled
   configuration must expose the algorithm as a deterministic, option-free
   variant.
4. The benchmark runner must execute Greedy and Lazy Greedy on the same
   instance units and preserve their result correspondence in canonical CSV
   output and the generated report.
5. Repository-level tests, content-boundary checks, license-manifest checks and
   type checks must continue to pass.

## Test procedure

Run the focused algorithm tests first:

```console
python -m unittest tests.test_lazy_greedy -v
```

Validate the bundled experiment plan without creating output:

```console
python run_project.py benchmark --config configs/p3_lazy_greedy.json --dry-run
```

Run the complete paired workflow locally when an output artifact is wanted:

```console
python run_project.py benchmark \
  --config configs/p3_lazy_greedy.json \
  --output results/p3-lazy-greedy \
  --workers 2 \
  --force
```

Validate an existing output independently of its own checksum:

```console
python .github/scripts/validate_benchmark_output.py \
  --config configs/p3_lazy_greedy.json \
  --output results/p3-lazy-greedy
```

Run the repository gates before review:

```console
python -m unittest discover -s tests -v
python .github/scripts/check_content_boundary.py --claim-mode no_quantitative_claims
python .github/scripts/build_license_manifest.py --check
python -m mypy
```

On Windows, `project.ps1 test` and `project.ps1 typecheck` provide the
corresponding wrapper commands when a supported Python installation is found.

## Acceptance criteria

- The focused tests pass without changing the dense Greedy selection sequence.
- Repeated Lazy Greedy calls on the same immutable instance have identical
  selected indices and metadata.
- The reported work value equals the metadata marginal-evaluation count.
- Lazy Greedy rejects unsupported common options through the registry.
- The bundled configuration dry-run expands successfully and includes a paired
  exact reference, Greedy baseline and Lazy Greedy variant.
- An integration run produces the normal canonical artifacts and preserves
  Greedy/Lazy Greedy correspondence for every shared instance unit.
- The full repository gates pass.

## Work-accounting definition

The lazy marginal-evaluation counter includes the initial queue construction:

    marginal_evaluations = initial_candidate_count + priority_queue_pops

where `initial_candidate_count` equals the number of sets in the instance.
The `priority_queue_pops` counter only counts actual `heapq.heappop` calls.
This definition is verified by the contract test
`test_metadata_and_work_accounting_are_deterministic`.

## Interpretation

A passing report establishes that Lazy Greedy is a deterministic, compatible
algorithm variant with an independently tested result contract. It does not
publish a runtime comparison, a general performance claim or a result about
any external corpus. Any such study must use a separately frozen evidence
package and an independently validated analysis.

## Verification snapshot

This snapshot was recorded on 2026-08-30 for the documentation-and-test working
tree on `codex/minimal-doc-delivery`, based on executable-code commit
`b0fa4610f5ef1f1956720fa0d4b2d3ec0e8240c9`. The changes under verification do
not modify package source or experiment configurations.

Environment:

- Python 3.12.13
- mypy 2.3.0
- Windows 11 (`Windows-11-10.0.26200-SP0`)
- OR-Tools not installed

Observed checks:

- The focused Lazy Greedy suite passed all 13 tests.
- The bundled dry-run expanded successfully.
- The paired workflow completed and its independent artifact validator passed.
- The complete repository suite passed all 407 tests; the two optional CP-SAT
  integration tests were skipped because OR-Tools was not installed.
- The content-boundary check, license-manifest check, and configured mypy gate
  passed.

The focused suite covers tie-breaking, zero-gain and full-coverage cases,
`k = set_count`, result correspondence, validator replay, and serial/parallel
metadata consistency. The paired workflow output remains ignored under
`results/` and is not part of the published snapshot.
