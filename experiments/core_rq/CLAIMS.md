# Core research claims

No quantitative research claim is published here yet.

## Review order

1. Start with the external [research analysis](../../analysis/README.md).
2. Return here for the authoritative mapping behind each claim ID.
3. Inspect the named result rows or filters, configuration, and manifest.
4. Check the recorded validator command and PASS result.

The content-boundary workflow permits quantitative prose but does not verify
this mapping. Contributors and reviewers perform that check directly.

## Required claim entry

Add one section per public claim using this format:

```markdown
## C1

Claim: A single testable statement.

Result: [`generated-statistics.csv`](generated-statistics.csv), with the exact
rows, columns, or filters that support the statement.

Figure: [`reader-facing-figure.svg`](../../analysis/reader-facing-figure.svg),
including the generated source filename and matching manifest hash when renamed.

Configuration: [`config.json`](config.json).

Manifest: [`manifest.json`](manifest.json).

Validation: PASS — `python .github/scripts/validate_benchmark_output.py ...`
```
