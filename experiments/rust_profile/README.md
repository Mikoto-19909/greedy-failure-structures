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
run uses those exact inputs to compare the unchanged public structure adapter with diagnostic pair
counts transported as little-endian `u64` pairs. The original Python division,
Jaccard list, `math.fsum` order, Gini and result construction remain in use.
The patch is local to that measurement process and restored after every call.

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
