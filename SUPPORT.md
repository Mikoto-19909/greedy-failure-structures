# Support

This is research code, not a product. It is published so the experiments it
performs can be inspected and reproduced, and it is maintained by one person
alongside other work.

There is no support commitment: no guaranteed response time, no help desk, and
no long-term maintenance promise.

## Getting started on your own

The [README](README.md) covers installation, running the starter workflow, and
the test command. Two things in it are worth repeating because they cause most
confusion:

- The base package needs only Python 3.11 or newer and no third-party
  dependency. OR-Tools is required only for the optional exact cross-validator.
- Files under `results/` are local artifacts. They are not part of the
  repository and are not expected to match anyone else's run byte for byte
  unless the configuration and seeds match.

For what the code does and why it is structured as it is, read the modules under
`src/maxcover/` alongside the tests in `tests/`. The tests are the executable
specification: where documentation and code disagree, the tests say which is
current.

## Asking a question

Open a GitHub issue. A question that includes the exact command you ran, the
configuration file, and the full output can usually be answered; one that does
not usually cannot.

Please do not use issues to report a suspected vulnerability — see
[SECURITY.md](SECURITY.md).

## What this project will not answer

**How well the algorithms perform.** This repository deliberately contains no
experiment results, no performance comparisons and no measurements, so questions
of the form "how much worse is greedy on X" have no answer here. That is a
scope decision, not an omission: any such claim requires a complete frozen
evidence chain, and publishing one is separate work. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the rule.

**Whether it fits your production use case.** The code solves a well-defined
research problem on synthetic instances. Nothing here is tuned, hardened or
benchmarked for production use.

**Contributions beyond the current scope.** Requests for new features are
welcome as discussion, but see [CONTRIBUTING.md](CONTRIBUTING.md) — larger
changes interact with the reproducibility contracts and need agreement first.
