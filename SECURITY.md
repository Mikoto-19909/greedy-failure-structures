# Security policy

This project studies the Maximum Coverage problem. The CLI reads local
configuration and replay files and writes local artifacts. The optional
Dashboard provides these operations through a local HTTP server at
`127.0.0.1:8501` by default and rejects non-loopback bindings.

## Reporting

Use [GitHub private vulnerability reporting](https://github.com/Mikoto-19909/greedy-failure-structures/security/advisories/new)
for suspected vulnerabilities. Include the affected command or Dashboard
operation, required input, reproduction steps and observed impact. Do not
publish vulnerability details in a public issue.

## What to expect

Security fixes target the current default branch; older versions are not
supported. The project has no guaranteed response time.

A report that is confirmed will be fixed on the default branch. Credit is given
in the commit message if you want it.

## Scope

In scope: memory-exhaustion or crash conditions reachable from a configuration
file, replay input, command-line argument or Dashboard request; output paths
that can escape the directory the user specified; dependency vulnerabilities
that are reachable from this code.

Out of scope: anything requiring the attacker to already control the machine or
the Python environment; resource use that is inherent to solving a hard
combinatorial problem, such as an exact solver taking a long time on a large
instance; the optional OR-Tools dependency's own internals, which belong
upstream.
