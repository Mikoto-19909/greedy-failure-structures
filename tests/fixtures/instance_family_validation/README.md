# Pre-extraction InstanceRecord pickle

`baseline_protocol4.pickle` contains the first uniform and adversarial records
from `../benchmark_compatibility/instances.csv`, serialized with Python 3.12.14
using the unmodified source at `ca5499c7bf0eb8a1393bda4ba373697a07679c12`.
The fixture is 972 bytes. It checks historical class lookup and restored state;
pickle restoration intentionally does not rerun constructor validation.

To reproduce, export that revision's `src` to an isolated directory, place it
first on Python's import path, load the CSV using `InstanceRecord.from_csv_row`,
select the first record of each of those two families in the stated order,
and serialize the list with `pickle.dumps(records, protocol=4)`. Do not replace
the historical fixture with bytes produced by the current implementation.
