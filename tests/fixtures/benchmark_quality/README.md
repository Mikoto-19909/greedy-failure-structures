# Pre-extraction Local Search pair

`pair_protocol4.pickle` was serialized by the original
`maxcover.benchmark_statistics._LocalSearchPairAnalysis` implementation at
`2c4c3de`, before moving that class. It contains the analysis of the eight fixed
synthetic pairs in `tests/test_benchmark_quality.py`: partial, full and absent
recovery, an optimal tie, missing reference, both timeout directions and errors.

The eligible recoveries are `(0.5, 1.0, 0.0)` and the remaining relative gaps are
`(0.2, 0.0, 0.6)`. The module compatibility test loads this genuine old payload,
checks the original fields, frozen/slotted identity and protocol-4/5 round trips.
Keep the old payload when changing implementation locations.
