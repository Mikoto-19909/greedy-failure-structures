# Rust kernel profiling experiment

This is a diagnostic extension, not a production backend. It copies the frozen
counting and Lazy Greedy loops and adds stage timers, a prepared-input control,
and a packed-pair transport control. Production `maxcover` never imports it.
The driver checks every measured non-timing output against the production raw
kernel and the original Python reference. Use an isolated Python environment.

```console
python -m pip install ./native/structure ./experiments/rust_profile
python scripts/profile_rust.py --verify-only
python scripts/profile_rust.py --output results/rust_profile
python scripts/profile_rust.py --inputs results/rust_profile/inputs.json --output results/rust_packed --confirm-packed
```

The first profiling run measures the fixed 24+4 corpus. The `--confirm-packed`
run uses those exact inputs to compare the frozen `7387f43` structure adapter with diagnostic pair
counts transported as little-endian `u64` pairs. The original Python division,
Jaccard list, `math.fsum` order, Gini and result construction remain in use.
The patch is local to that measurement process and restored after every call.
These historical controls use the installed wheel's legacy `counts` function;
they are not an old-wheel/new-wheel release comparison. Freezing the adapter
prevents a new production `counts_packed` path from silently bypassing the patch.

The driver saves inputs, answers, configuration, source copies, raw timings and
medians. Ten rounds alternate operation order; cheap conversion probes use
batches of 50. Verification and file writes are outside timed calls. Do not run
other CPU-heavy checks alongside timing. Memory is measured in fresh processes
with Python allocation tracing and OS process peaks in separate invocations.

Interpretation limits:

- Stage residuals include input extraction/copy, return conversion, local
  destruction, clock overhead and the Python call boundary; they are not pure
  output-conversion measurements.
- Prepared calls exclude one-time construction and still have diagnostic
  clocks. They are a steady-state bound, not an implemented public API.
- Traced Python peaks exclude Rust allocations. OS values are whole-process
  lifetime peaks, including loading the inputs. Small calls can remain below
  the earlier process peak; a zero increase does not mean zero allocation.
- The diagnostic copy must be rechecked if production kernels change. It is
  not a correctness oracle and its timing need not equal the production build.

Build products, temporary environments and probe scripts may be removed after
validation; keep the maintained sources, exact inputs, raw records and reports.
CI builds these diagnostics and runs the short parity check; it does not
establish portable performance results from variable hosted-runner timings.

## Production packed acceptance

`accept_packed.py` compares actual 0.2.0 and 0.3.0 wheels in independent,
serially sampled processes pinned to the same available logical CPU. Each
request checks all metrics and whether it called `counts` or `counts_packed`.
It uses 10 alternating pairs and batches of 50 calls for small cases. Memory
uses separate fresh processes for Python tracing and natural OS peaks.

Install the frozen 0.2.0 wheel into a separate environment; if the saved wheel
is unavailable, build `native/structure` from commit `7387f43`. Install the
candidate into the regular environment. Supply the saved 28-input/answer files
or obtain that corpus using the benchmark entry with `--large`.

Example for the existing Windows workspace (output directories must be new):

```console
.venv/Scripts/python.exe -m venv results/native-0.2-env
results/native-0.2-env/Scripts/python.exe -m pip install results/rust_correctness_audit_20260919/wheels/maxcover_structure_native-0.2.0-cp311-abi3-win_amd64.whl
.venv/Scripts/python.exe experiments/rust_profile/accept_packed.py --inputs results/rust_algorithms_large_isolated_20260919/inputs.json --expected results/rust_algorithms_large_isolated_20260919/expected.json --baseline-python results/native-0.2-env/Scripts/python.exe --output results/packed_round1
```

Repeat with another output directory for confirmation. An optional
`--list-adapter` points to the saved intermediate packed-plus-list source;
each stage is paired against its own contemporaneous baseline. Do not compare
absolute medians from different stages as if they were paired measurements.
The driver requires the exact wheel versions and rejects existing outputs.
