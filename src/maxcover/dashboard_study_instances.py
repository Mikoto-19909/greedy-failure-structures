"""Resolve explicitly registered saved graphs and check display/replay consistency."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import TYPE_CHECKING, Any

from .algorithms import greedy
from .dashboard_studies import StudiesError, _finite_float, _json, _linked, _reject_constant
from .reproducibility import instance_from_payload, instance_id, instance_payload

if TYPE_CHECKING:
    from .dashboard_analysis import StudyAnalysisService


def unlinked(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if (candidate.exists() or candidate.is_symlink()) and _linked(candidate):
            raise StudiesError("linked or reparse graph origins are not supported")
    if str(path).startswith(("\\\\", "//")):
        raise StudiesError("graph origin must be a local directory")
    return path


def graph(service: StudyAnalysisService, source: str, identifier: str) -> tuple[dict[str, Any], str]:
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", identifier):
        raise StudiesError("invalid original graph identifier")
    directory = service.studies._path(source)
    own = unlinked(directory / "graphs" / (identifier + ".json"))
    if own.is_file():
        return _json(own), str(own)
    registration = unlinked(directory / "graph_origin.json")
    if not registration.is_file():
        raise StudiesError("saved graph unavailable: register graph_origin.json or restore graphs/")
    origin = _json(registration)
    if origin.get("kind") == "directory" and set(origin) == {"kind", "path"}:
        target = Path(origin["path"])
        if not target.is_absolute():
            raise StudiesError("registered graph origin directory must be absolute")
        path = unlinked(target / "graphs" / (identifier + ".json"))
        return _json(path), str(path)
    if origin.get("kind") == "git" and set(origin) == {"kind", "commit", "path"}:
        commit, prefix = origin["commit"], origin["path"]
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise StudiesError("registered Git origin needs a fixed 40-character commit")
        if (not isinstance(prefix, str) or not prefix or "\\" in prefix or ":" in prefix
                or PurePosixPath(prefix).is_absolute() or ".." in PurePosixPath(prefix).parts
                or str(PurePosixPath(prefix)) != prefix or "\x00" in prefix):
            raise StudiesError("invalid registered Git artifact prefix")
        ref = f"{commit}:{prefix}/graphs/{identifier}.json"
        try:
            result = subprocess.run(["git", "show", ref], cwd=service.root, capture_output=True,
                                    check=True, timeout=20)
            if len(result.stdout) > 16 * 1024 * 1024:
                raise StudiesError("saved graph exceeds the display limit")
            value = json.loads(result.stdout, parse_constant=_reject_constant, parse_float=_finite_float)
            if not isinstance(value, dict):
                raise StudiesError("saved graph must be an object")
            return value, "git:" + ref
        except (subprocess.SubprocessError, json.JSONDecodeError) as error:
            raise StudiesError(f"registered Git graph cannot be read: {error}") from error
    raise StudiesError("invalid graph_origin.json registration")


def saved_instance(service: StudyAnalysisService, source: str, identifier: str, k: int | None,
                   direction: int | None, replica: int | None) -> dict[str, Any]:
    from .dashboard_analysis import equal
    try:
        data = service._dataset(source)
        kind, config = data["kind"], data["config"]
        if identifier not in {r["base_graph_id"] for r in data["rows"]}:
            raise StudiesError("original graph is not present in this study")
        record, origin = graph(service, source, identifier)
        task = record["task"]
        expected = [t for t in config.get("tasks", []) if t["base_graph_id"] == identifier]
        if record.get("status") != "complete" or task["base_graph_id"] != identifier:
            raise StudiesError("saved graph identity or completion differs")
        if expected and (len(expected) != 1 or task != expected[0]):
            raise StudiesError("saved graph task differs from configured identity")
        chain, certificate = None, None
        choices: list[dict[str, Any]] = []
        if kind == "r3":
            if k is not None and k != config["k"]:
                raise StudiesError("R3 budget differs from its saved design")
            k = config["k"]
            n, d = config["n"], config["d"]
            chains = record["chains"]
            if len(chains) != 4 or {(c["direction"], c["replica"]) for c in chains} != {(-1, 0), (-1, 1), (1, 0), (1, 1)}:
                raise StudiesError("R3 graph requires four unique chains")
            if [{name: c[name] for name in ("direction", "replica", "seed")} for c in chains] != task["chains"]:
                raise StudiesError("R3 chain identities disagree with task")
            choices = [{"label": "原图", "direction": None, "replica": None}]
            choices += [{"label": f"{'low' if c['direction'] == -1 else 'high'} · chain {c['replica']}",
                         "direction": c["direction"], "replica": c["replica"]} for c in chains]
            if direction is None and replica is None:
                sets, values, saved_id = record["sets"], record["values"], record["instance_id"]
                family, seed, parameters = "fixed_size", task["seed"], {"set_size": d, "unique_sets": False}
                row = None
            else:
                if type(direction) is not int or direction not in (-1, 1) or type(replica) is not int or replica not in (0, 1):
                    raise StudiesError("R3 endpoint needs direction -1/1 and replica 0/1")
                chain = next(c for c in chains if (c["direction"], c["replica"]) == (direction, replica))
                if len(chain["endpoints"]) != 1:
                    raise StudiesError("R3 requires one saved endpoint per chain")
                endpoint = chain["endpoints"][0]
                if endpoint["proposals"] != config["proposals"] or endpoint["accepted"] != len(chain["moves"]):
                    raise StudiesError("R3 endpoint proposal or accepted-move count differs")
                changed = [set(s) for s in record["sets"]]
                frequencies = [sum(a in s for s in changed) for a in range(n)]
                exposure = sum(frequencies[a] - 1 for a in changed[0])
                previous = 0
                for proposal, i, j, a, b in chain["moves"]:
                    if (any(type(v) is not int for v in (proposal, i, j, a, b))
                            or not previous < proposal <= endpoint["proposals"] or i == j or a == b
                            or not 0 <= i < n or not 0 <= j < n or not 0 <= a < n or not 0 <= b < n):
                        raise StudiesError("invalid saved R3 exchange")
                    if (a in changed[i], b in changed[i], a in changed[j], b in changed[j]) not in ((True, False, False, True), (False, True, True, False)):
                        raise StudiesError("illegal saved R3 exchange")
                    changed[i].symmetric_difference_update((a, b))
                    changed[j].symmetric_difference_update((a, b))
                    next_exposure = sum(frequencies[a] - 1 for a in changed[0])
                    if direction * (next_exposure - exposure) < 0:
                        raise StudiesError("saved exchange violates R3 exposure direction")
                    exposure = next_exposure
                    previous = proposal
                if [sorted(s) for s in changed] != endpoint["sets"]:
                    raise StudiesError("R3 saved moves disagree with endpoint sets")
                equal(endpoint["exposure"], exposure, "endpoint exposure")
                sets, values, saved_id = endpoint["sets"], endpoint["values"], endpoint["instance_id"]
                family, seed = "custom", chain["seed"]
                parameters = {"r3_version": config["version"], "base_graph_id": identifier, "direction": direction, "replica": replica}
                row = next(r for r in data["rows"] if (r["base_graph_id"], r["direction"], r["replica"]) == (identifier, direction, replica))
                if str(chain["seed"]) != row["chain_seed"]:
                    raise StudiesError("R3 endpoint seed differs from saved row")
                for name in ("exposure", "accepted", "legal", "proposals"):
                    equal(row[name], endpoint[name], name)
        else:
            if direction is not None or replica is not None or type(k) is not int or k not in task["budgets"]:
                raise StudiesError("select a saved study budget")
            original = record if kind == "r2" else record["source"]
            if original["task"] != task:
                raise StudiesError("certificate source task differs")
            if [v["k"] for v in original["values"]] != task["budgets"]:
                raise StudiesError("saved source budget membership differs")
            sets, n, d = original["sets"], task["n"], task["d"]
            values = next(v for v in original["values"] if v["k"] == k)
            if values["reference_status"] != "optimal":
                raise StudiesError("saved optimum is not an exact reference")
            saved_id = values["instance_id"]
            family, seed, parameters = "fixed_size", task["seed"], {"set_size": d, "unique_sets": False}
            row = next(r for r in data["rows"] if (r["base_graph_id"], r["k"]) == (identifier, k))
            choices = [{"label": f"k = {budget}", "k": budget} for budget in task["budgets"]]
            if kind != "r2":
                if [v["k"] for v in record["values"]] != task["budgets"]:
                    raise StudiesError("certificate budget membership differs")
                certificate = next(v for v in record["values"] if v["k"] == k)
                for name in (("greedy", "initial_upper", "upper") if kind == "r4" else ("greedy", "initial_upper", "prefix_upper", "dual_upper")):
                    equal(certificate[name], row[name], name)
        if (len(sets) != n or any(not isinstance(s, list) or len(s) != d or s != sorted(set(s)) for s in sets)):
            raise StudiesError("saved set dimensions or ordering differ")
        instance = instance_from_payload({"schema_version": 1, "encoding": "elements", "sets": sets,
            "universe_size": n, "k": k, "family": family, "seed": seed, "parameters": parameters})
        if instance_id(instance) != saved_id or (row is not None and "instance_id" in row and row["instance_id"] != saved_id):
            raise StudiesError("saved instance identity disagrees with actual sets")
        for name, witness_name in (("greedy", "greedy_selected"), ("optimum", "optimum_selected"), ("forced_optimum", "forced_selected")):
            if name not in values:
                continue
            witness = values[witness_name]
            if (not isinstance(witness, list) or len(witness) != k or witness != sorted(set(witness))
                    or any(type(i) is not int or not 0 <= i < n for i in witness)
                    or (name == "forced_optimum" and 0 not in witness)
                    or instance.coverage(tuple(witness)) != values[name]):
                raise StudiesError(f"saved {name} witness disagrees")
            if row is not None and name in row:
                equal(row[name], values[name], name)
        if not 0 <= values["greedy"] <= values["optimum"] <= n:
            raise StudiesError("invalid saved quality values")
        solution = greedy(instance)
        if solution.coverage != values["greedy"] or list(solution.selected) != values["greedy_selected"]:
            raise StudiesError("saved Greedy result violates deterministic replay")
        covered: set[int] = set()
        selected: list[int] = []
        steps = []
        for step in range(instance.k + 1):
            gains = [len(set(s) - covered) if i not in selected else None for i, s in enumerate(sets)]
            candidates = [i for i, gain in enumerate(gains) if gain == max(g for g in gains if g is not None)] if step < instance.k else []
            steps.append({"step": step, "selected": list(selected), "covered": sorted(covered), "coverage": len(covered),
                          "gains": gains, "candidates": candidates, "next_choice": min(candidates) if candidates else None})
            if candidates:
                selected.append(min(candidates))
                covered.update(sets[selected[-1]])
        if certificate is not None:
            if certificate["path"] != selected or len(certificate["prefixes"]) != instance.k + 1:
                raise StudiesError("saved certificate path differs from Greedy steps")
            for prefix, step_data in zip(certificate["prefixes"], steps):
                equal(prefix["t"], step_data["step"], "certificate step")
                equal(prefix["coverage"], step_data["coverage"], "prefix coverage")
        return {"kind": kind, "base_graph_id": identifier, "instance": instance_payload(instance),
                "values": values, "steps": steps, "choices": choices, "certificate": certificate,
                "moves": chain["moves"] if chain else [], "direction": direction, "replica": replica,
                "provenance": {"source": source, "graph_origin": origin, "base_graph_id": identifier,
                    "instance_id": saved_id, "k": k, "direction": direction, "replica": replica,
                    "note": "Saved graph and witness display consistency; deterministic Greedy replay checked. No new optimum proof."}}
    except (KeyError, TypeError, OSError, ValueError, IndexError, StopIteration) as error:
        if isinstance(error, StudiesError):
            raise
        raise StudiesError(f"invalid saved graph: {error}") from error
