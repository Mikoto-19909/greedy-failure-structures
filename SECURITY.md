# Security policy

This is research code for studying the Maximum Coverage problem. It is a
command-line tool that reads local configuration files and writes local output
files. It opens no network connections, runs no server, and handles no
credentials or personal data.

That shapes what a security issue here looks like. The realistic cases are
input-handling problems: a configuration or replay file that causes unbounded
memory allocation, a path that escapes its intended output directory, or a
parser that can be driven into a crash by a malformed input.

## Reporting

Please do not open a public issue for a suspected vulnerability.

GitHub's private vulnerability reporting will be the reporting channel for this
repository. It is available only for public repositories, so it will be enabled
when this repository becomes public; until then, there is no private channel
here and no report is expected.

## What to expect

This project is maintained by one person alongside other work. There is no
response-time commitment, no service-level agreement, and no security support
for older versions — only the current default branch is considered.

A report that is confirmed will be fixed on the default branch. Credit is given
in the commit message if you want it.

## Scope

In scope: memory-exhaustion or crash conditions reachable from a configuration
file, a replay input, or a command-line argument; output paths that can escape
the directory the user specified; dependency vulnerabilities that are actually
reachable from this code.

Out of scope: anything requiring the attacker to already control the machine or
the Python environment; resource use that is inherent to solving a hard
combinatorial problem, such as an exact solver taking a long time on a large
instance; the optional OR-Tools dependency's own internals, which belong
upstream.
