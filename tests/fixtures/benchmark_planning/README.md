# Pre-extraction planning and task pickles

These protocol 4 and 5 pickles were generated before B1 from the genuine
`c40658d4cbc16b45fb640b1d97c03688baee16b7` source. The source was exported with
`git archive` and every imported source file was checked against that Git object.
The unchanged [B0 configuration](../benchmark_compatibility/config.json) was
expanded with the old `_instances_for_config()` and `_tasks_for_config()`;
algorithm execution was forbidden. A second old-version interpreter loaded
both files and verified the selected IDs against B0's original CSV records.

Each pickle contains an `ordinary` and a `coupled` pair of planned instance and
run task. The ordinary selection is the first uncoupled uniform instance with
the first unseeded task (Greedy). The coupled selection is the first coupled
instance with the first seeded task (dominated-heavy, randomized Greedy).
This includes distinct ordinary/coupling seeds, nondefault options and a shared
instance object within each pair.

`expected.json` was exported by the same old interpreter: it records fields,
defaults, slots, frozen state, complete instance masks, payload, options and
identities. `provenance.json` records the source/configuration digests and the
exact frozen file digests. The generation script digest identifies the local
pre-move evidence; it is not a production dependency or a test-time generator.

Tests load these bytes in a new interpreter. They compare actual values against
the old JSON and assert that the facade aliases and defining module expose the
same class objects. Private task classes may acquire their new defining module;
the old module names in JSON record provenance. The public `BenchmarkPlan`
module and pickle identity remain covered by the separate B0 fixtures.

These synthetic compatibility fixtures contain no new research observations.
Do not regenerate them with the candidate implementation to accept a mismatch.
