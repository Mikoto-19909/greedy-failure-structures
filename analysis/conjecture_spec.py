"""Input schema for bounded conjecture searches; no search or claim evaluation."""
from __future__ import annotations


def fields(value, allowed, required, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    if set(value) - set(allowed) or set(required) - set(value):
        raise ValueError(f"{name}: unknown or missing fields")


def integer(value, name, minimum, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name}: integer required in [{minimum}, {maximum or 'unbounded'}]")
    return value


def parse_design(value):
    fields(value, ("schema_version", "name", "domain", "claim", "search"),
           ("schema_version", "domain", "claim"), "design")
    integer(value["schema_version"], "schema_version", 1, 1)
    name = value.get("name", "greedy_ratio_conjecture")
    if not isinstance(name, str) or not name.strip() or "\n" in name or "\r" in name:
        raise ValueError("name must be a nonempty single-line string")
    domain = value["domain"]
    fields(domain, ("universe_size", "set_count", "k", "set_size", "unique_sets", "max_frequency"),
           ("universe_size", "set_count", "k"), "domain")
    n = integer(domain["universe_size"], "universe_size", 1, 12)
    m = integer(domain["set_count"], "set_count", 1, 16)
    k = integer(domain["k"], "k", 1, m)
    d = domain.get("set_size")
    if d is not None:
        integer(d, "set_size", 0, n)
    unique = domain.get("unique_sets", False)
    if type(unique) is not bool:
        raise ValueError("unique_sets must be a boolean")
    frequency = domain.get("max_frequency")
    if frequency is not None:
        integer(frequency, "max_frequency", 0, m)
    claim = value["claim"]
    fields(claim, ("min_ratio",), ("min_ratio",), "claim")
    ratio = claim["min_ratio"]
    if not isinstance(ratio, list) or len(ratio) != 2:
        raise ValueError("min_ratio must be [numerator, denominator]")
    denominator = integer(ratio[1], "ratio denominator", 1)
    numerator = integer(ratio[0], "ratio numerator", 0, denominator)
    search = value.get("search", {})
    fields(search, ("max_instances", "max_combinations"), (), "search")
    instances = integer(search.get("max_instances", 10000), "max_instances", 0)
    combinations = integer(search.get("max_combinations", 200000), "max_combinations", 1)
    return {"schema_version": 1, "name": name,
            "domain": {"universe_size": n, "set_count": m, "k": k, "set_size": d,
                       "unique_sets": unique, "max_frequency": frequency},
            "claim": {"min_ratio": [numerator, denominator]},
            "search": {"max_instances": instances, "max_combinations": combinations}}
