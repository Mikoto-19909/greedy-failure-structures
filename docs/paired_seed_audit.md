# Paired-Seed Scheme Audit

This document audits how the registered instance families consume random-number
streams during generation, and what "paired" versus "unpaired" means for the
two experiments defined in configs/pairing_paired.json and
configs/pairing_unpaired.json. It is a structural audit: it records the seed
sources, call patterns, and granularity of stream consumption. It records no
measured outcome values.

## Audit protocol

1. **Registry enumeration.** Every family is read from the published registry
   rather than from scattered call sites:

   ~~~console
   python -c "from maxcover.generators import GENERATORS; print(*GENERATORS, sep='\n')"
   ~~~

   The registry currently publishes fourteen names: uniform, high_overlap,
   clustered, fixed_size, long_tail, duplicate_heavy, dominated_heavy,
   mixed_cluster, controlled_high_overlap, controlled_clustered,
   controlled_duplicate, controlled_dominated, controlled_adversarial, and
   adversarial.

2. **Static reading.** The generation path of each family is read in
   src/maxcover/generators.py, together with the seed plumbing in
   src/maxcover/benchmark.py (the runner's derived-parameter injection) and
   src/maxcover/config.py (schema-three seed groups).

3. **Dynamic instrumentation.** A probe replaces the module-level RNG
   constructor with a counting factory; each registry spec is then generated
   through the same generate() entry point the runner uses, first without
   derived parameters and then -- for the families that declare a
   coupling_seed derived parameter -- with an explicit coupling seed. The
   probe records every constructed RNG with its constructor argument and the
   ordered sequence of draw methods invoked on it. Two additional probes
   establish seed dominance: generating twice with the same coupling seed but
   different instance seeds, and twice with the same instance seed but
   different coupling seeds. The probe is local evidence and is not tracked by
   this repository.

4. **Seeds are classified by what they are, not by what a comment says.**
   A constructor argument equal to the instance seed is a per-instance
   stream; an argument equal to the supplied coupling seed is a raw shared
   stream; any other argument is a child seed derived by the stable salted
   SHA-256 derivation in the generator module (_derived_seed), which is
   namespaced and therefore distinct per namespace and per index.

## Per-family stream consumption

Coupling support means the generator declares coupling_seed as a derived
parameter and, when the runner supplies one, generation is driven by it rather
than by the instance seed. Granularity describes the scope of one draw:
per instance, per candidate set, or per element.

| Family | RNG instances and seed source | Consumption pattern and granularity |
| --- | --- | --- |
| uniform (plain density mode) | one per instance, base seed | one throwaway draw per element of the universe for each candidate set, in candidate-set-major order; plus, when a set comes out empty, one corrective draw per affected set |
| uniform (paired fixed-size mode) | one per generated instance, child seed derived from the coupling seed under the fixed-size control namespace | one 53-bit draw per element of the universe for each candidate set, in candidate-set-major order; the same stream also orders the paired fixed-size control's selected elements |
| high_overlap | one per instance, base seed; no coupling parameter | one draw per element of the universe for each candidate set, in candidate-set-major order, with a probability threshold chosen by core membership; plus one corrective draw per empty set |
| clustered | one per instance, base seed; no coupling parameter | one draw per element of the universe for each candidate set, in candidate-set-major order, with the threshold chosen by the set's preferred cluster; plus one corrective draw per empty set |
| fixed_size (unique sets) | one per instance, base seed | one sample of distinct combination ranks from the full lexicographic pool, then deterministic unranking |
| fixed_size (repeated sets) | one per instance, base seed | one sample of set-size elements from the universe per candidate set |
| fixed_size (paired control) | one per generated instance, child seed derived from the coupling seed under the fixed-size control namespace | one 53-bit draw per element of the universe for each candidate set, in candidate-set-major order; the top ranks become the set |
| long_tail | one per generated instance, coupling seed used directly (base seed when no coupling seed) | one full shuffle of the universe (rank order), then one draw per element of the universe for each candidate set, in candidate-set-major order; keys are a rank penalty plus a Gumbel-style noise term and are sorted deterministically |
| duplicate_heavy | one per generated instance, constructed by delegating to fixed-size unique-sets generation with the coupling seed used directly (base seed when no coupling seed) | one sample of distinct combination ranks; the block replication that builds the final instance is deterministic |
| dominated_heavy | one child RNG per anchor, seeds derived from the coupling seed (base seed when none) under the children namespace with the anchor index | per anchor, one prefix-stable sample of distinct child-subset ranks, then deterministic unranking; the anchors themselves are fixed positions, not draws |
| mixed_cluster | one partition RNG with a child seed derived from the coupling seed under the partition namespace, plus one candidate RNG per candidate set with a child seed derived under the candidate namespace with the set index | partition RNG: one full shuffle of the universe; candidate RNG: one full-permutation sample of the preferred cluster followed by one of the adjacent cluster; bridge membership is decided by sorting deterministic child keys, with no stream consumption |
| controlled_high_overlap | one per generated instance, child seed derived from the coupling seed under a family-specific pool namespace | one single sample of the pool: a balanced draw of enough elements for one shared core plus one fringe per candidate set; all slicing and masking afterwards is deterministic |
| controlled_clustered | one per generated instance, child seed derived from the coupling seed under a family-specific pool namespace | one single pool sample for the disjoint cluster cores plus one fringe per candidate set; deterministic afterwards |
| controlled_duplicate | one per generated instance, child seed derived from the coupling seed under a family-specific pool namespace | one single pool sample of one distinct base per candidate set; determined by deterministic slicing, and replication is mechanical |
| controlled_dominated | one per generated instance, child seed derived from the coupling seed under a family-specific pool namespace | one single pool sample of disjoint-pair elements; the pairing and the dominance conversion are deterministic |
| controlled_adversarial | one per generated instance, child seed derived from the coupling seed under a family-specific distractor namespace | one single sample of distinct admissible distractor ranks, then deterministic unranking; the trap, cover sets and balancing padding are constructed without draws |
| adversarial (original construction) | one per instance, base seed; coupling is rejected | one full-size sample of the universe per distractor; the trap and cover sets are fixed |
| adversarial (second construction) | one per generated instance, coupling seed used directly (base seed when no coupling seed) | one full permutation of the universe per distractor; the trap, cover sets and balancing padding are deterministic |

Two patterns deserve a call-out. First, the families that consume an RNG
seeded from a raw seed value share the same underlying stream with every other
family that seeds from the same value: the generator module constructs a
separate Mersenne-Twister object in each case, but equal seeds produce equal
state, so equal draw lengths are position-wise equal values. Families differ
in how they slice that stream and in how many draws they take; a corrective
draw added by one family desynchronizes its stream relative to another.
Second, the paired uniform control and the paired fixed-size control are the
only two families deliberately sharing one derived child stream: both draw
from the fixed-size control namespace, which is what makes the two controls
common-random-number aligned.

## Paired versus unpaired semantics

Both experiments share a base seed, the same repetitions, the same two
algorithms, and the same four cases: overlap (high_overlap), its matched
Bernoulli control overlap_control, trap (the second adversarial
construction), and its matched control trap_control. Each control is a
uniform family case with the same universe size, candidate-set count and
budget as its treatment; its density parameter is matched so the control's
expected set size equals the treatment's mean set size. For the constructed
adversarial treatment that mean is exact, and for the Bernoulli overlap
treatment it is the parameter-implied expectation of its per-set incidence.

The configurations differ only in whether the cases declare a schema-three
seed group:

- **Paired.** overlap and overlap_control share one seed group, and trap and
  trap_control share another. A seed group makes the runner assign the same
  per-repetition instance seed to every case in the group, so within a
  repetition the treatment and its control are generated from the same seed
  value. For high_overlap -- which has no coupling parameter -- that is the
  only alignment available: both generators construct their RNG from the
  same seed and consume it with the same per-element pattern, differing only
  in what probability each draw is compared to. For the adversarial treatment
  the runner passes the shared seed as the coupling seed, so the treatment
  draws its distractors from a raw stream started at the same value as the
  control's Bernoulli draws.
- **Unpaired.** No seed group: each case receives a distinct seed derived from
  its position in the configuration, and the treatment stream is therefore
  independent of the control stream. The adversarial treatment still receives
  a coupling seed from the runner -- a deterministic digest of the base seed,
  block size, distractor count and repetition -- but that seed is not shared
  with anything, so it behaves as an independent stream for this experiment.

The intended difference, in one sentence: the paired run aligns the treatment
and control of each family pair on shared randomness within every repetition,
and the unpaired run lets them vary independently. A consequence of the
generator audit matters here: for every family that supports a coupling seed,
the generated instance content is determined entirely by the coupling seed --
the participating instance seed is recorded metadata and enters only the
recorded identity (instance_id), so generating with the same coupling seed and
different instance seeds yields identical instance content but distinct record
identities. Per-repetition sharing of the instance seed therefore aligns actual
content only for the families without coupling support (high_overlap and the
Bernoulli control); for the adversarial pair the alignment is exact only
because the same value is used as the coupling seed for the treatment.

## Qualitative conclusion: stream distinctness

Do the families consume different streams under the same base seed? Not as a
matter of design. Stream sharing occurs in three distinct groups, and the
boundaries between them are explicit:

- Families that construct their RNG from the raw seed (uniform in plain mode,
  high_overlap, clustered, both unpaired fixed-size modes, and the original
  adversarial construction) each build a separate RNG object, but from the
  same value. Under the same base seed their draw-value sequences coincide
  position-wise; only the interpretation of each draw and the number of draws
  consumed differ.
- Families that consume a raw coupling seed (long_tail, duplicate_heavy, and
  the second adversarial construction) are aligned with each other the same
  way under a shared coupling seed.
- Families that derive namespaced child seeds (the fixed-size and uniform
  paired controls, dominated_heavy, mixed_cluster, and all five controlled
  families) each start a stream that is distinct from the raw value streams
  and from every other namespace -- with exactly one deliberate exception:
  the paired uniform control and the paired fixed-size control share one
  derived namespace by design.

So the qualitative answer is: across families there is no unconditional
stream isolation. Isolation depends on whether a family consumes the raw
value or a derived child seed, and the controlled families are the ones that
are strictly isolated from everything else.

## Variance-comparison analysis

The seed-level variance comparison lives in src/maxcover/paired_seed_analysis.py
and reads the canonical raw_results.csv and instances.csv artifacts of the two
runs. It verifies the digests the benchmark manifest records for both files
against the files actually read, accepts only the current manifest schema
version, and checks the effective seed the instances record (the coupling seed
when the runner injected one, otherwise the instance seed): shared between a
treatment and its matched control at every repetition in the paired run, and
independent in the unpaired run. A paired run may therefore have distinct raw
instance seeds when the effective seeds agree. The existing `treatment_seed`,
`control_seed`, `seeds_equal`, and seed-shared count fields continue to describe
the raw seeds in raw_results.csv; they are diagnostics, not the coupling
acceptance condition. Run it from the repository root:

~~~console
PYTHONPATH=src python -m maxcover.paired_seed_analysis --paired-results results/pairing-v1/paired --unpaired-results results/pairing-v1/unpaired --output results/pairing-v1/analysis
~~~

On Windows PowerShell the equivalent is: set the path variable to the source
layout first, then run the module the same way.

For each family pair and each algorithm it forms one treatment-minus-control
difference per repetition, from the paired run and from the unpaired run, and
compares the spread of the two difference distributions. The numeric results
are written under results/, which is local evidence and is not tracked
documentation. The analysis also writes `analysis_manifest.json` with the
input raw-result, instance and benchmark-manifest digests, the verified schema
and effective-coupling constraints, the analysis source commit and dirty state,
and the output CSV digests. This document records the method and nothing
measured.
