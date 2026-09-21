"""Read saved study tables with their original units and explicit pair designs.

No producer, optimum solver or inferential procedure runs in this reader.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import math
from pathlib import Path
import statistics
from typing import Any

from .dashboard_studies import StudiesError, StudiesService, _json


TEXT = {"base_graph_id", "instance_id", "endpoint", "chain_seed"}
NOTICE = "描述性浏览；保存区间属于原完整设计。历史验证状态不是本轮原图最优性证明。"


def number(value: Any, name: str, *, integer: bool = False) -> float | int:
    try:
        if isinstance(value, bool):
            raise ValueError()
        result = float(value)
        if not math.isfinite(result) or (integer and int(result) != result):
            raise ValueError()
        return int(result) if integer else result
    except (ValueError, TypeError, OverflowError) as error:
        raise StudiesError(f"invalid numeric {name}") from error


def equal(actual: Any, expected: Any, name: str) -> None:
    if not math.isclose(float(number(actual, name)), float(number(expected, name)), rel_tol=1e-11, abs_tol=1e-12):
        raise StudiesError(f"saved {name} disagrees with records")


def distribution(values: list[float]) -> dict[str, Any]:
    """Exact frequency distribution; no bin-dependent inference."""
    counts = Counter(values)
    ordered = sorted(values)
    return {"count": len(values), "mean": statistics.fmean(values) if values else None,
            "median": statistics.median(values) if values else None,
            "p90": ordered[math.ceil(.9 * len(values)) - 1] if values else None,
            "points": [{"value": value, "count": counts[value]} for value in sorted(counts)]}


class StudyAnalysisService:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve()
        self.studies = StudiesService(self.root)

    def _table(self, source: str, name: str) -> list[dict[str, Any]]:
        try:
            with self.studies._path(source, name).open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, strict=True)
                fields = reader.fieldnames or []
                if not fields or len(fields) != len(set(fields)) or any(not f for f in fields):
                    raise StudiesError("CSV needs unique nonempty columns")
                rows = []
                for raw in reader:
                    if None in raw or any(value is None for value in raw.values()):
                        raise StudiesError("CSV row width differs")
                    rows.append({key: value if key in TEXT else None if value == "" else number(value, key)
                                 for key, value in raw.items()})
            if not rows:
                raise StudiesError("study table is empty")
            return rows
        except (OSError, csv.Error) as error:
            raise StudiesError(str(error)) from error

    @staticmethod
    def _unique(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> None:
        seen = set()
        for row in rows:
            try:
                identity = tuple(row[key] for key in keys)
            except KeyError as error:
                raise StudiesError(f"missing identity column {error}") from error
            if any(value is None or value == "" for value in identity) or identity in seen:
                raise StudiesError(f"missing or duplicate identity: {identity}")
            seen.add(identity)

    def _dataset(self, source: str) -> dict[str, Any]:
        description = self.studies._description(source)
        kind = description["kind"]
        if kind not in {"r2", "r3", "r4", "r4_dual"}:
            raise StudiesError("unsupported study schema")
        try:
            config = _json(self.studies._path(source, "config.json"))
            rows = self._table(source, "endpoint_results.csv" if kind == "r3" else "budget_results.csv")
            if kind == "r3":
                bases = self._table(source, "base_graph_summary.csv")
                self._unique(rows, ("base_graph_id", "direction", "replica"))
                self._unique(rows, ("instance_id",))
                self._unique(bases, ("base_graph_id",))
                groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for row in rows:
                    self._quality(row)
                    forced = number(row["forced_optimum"], "forced_optimum", integer=True)
                    if row["first_loss"] not in (0, 1) or not row["greedy"] <= forced <= row["optimum"]:
                        raise StudiesError("invalid R3 first-step reference")
                    for name in ("exposure", "accepted", "legal", "proposals"):
                        if number(row[name], name, integer=True) < 0:
                            raise StudiesError(f"R3 {name} must be nonnegative")
                    if not row["accepted"] <= row["legal"] <= row["proposals"]:
                        raise StudiesError("invalid R3 chain counts")
                    equal(row["first_loss"], int(row["forced_optimum"] < row["optimum"]), "first_loss")
                    groups[row["base_graph_id"]].append(row)
                if set(groups) != {row["base_graph_id"] for row in bases}:
                    raise StudiesError("R3 original graph membership differs")
                for base in bases:
                    group = groups[base["base_graph_id"]]
                    if {(r["direction"], r["replica"]) for r in group} != {(-1, 0), (-1, 1), (1, 0), (1, 1)}:
                        raise StudiesError("R3 requires four endpoints per original graph")
                    for side, label in ((-1, "low"), (1, "high")):
                        endpoints = [r for r in group if r["direction"] == side]
                        for metric in ("first_loss", "failure", "relative_gap", "exposure"):
                            equal(base[label + "_" + metric], statistics.fmean(r[metric] for r in endpoints), label + "_" + metric)
                    equal(base["difference"], base["high_first_loss"] - base["low_first_loss"], "difference")
                primary = _json(self.studies._path(source, "primary_summary.json"))
                equal(primary["n"], len(bases), "n")
                equal(primary["endpoints"], len(rows), "endpoints")
                equal(primary["delta"], statistics.fmean(r["difference"] for r in bases), "delta")
                if not -1 <= primary["lower"] <= primary["delta"] <= primary["upper"] <= 1:
                    raise StudiesError("invalid saved R3 primary interval")
                cells: list[dict[str, Any]] = []
            else:
                self._unique(rows, ("base_graph_id", "k"))
                if kind in {"r2", "r4_dual"}:
                    self._unique(rows, ("instance_id",))
                for row in rows:
                    for name in ("n", "d", "k"):
                        if number(row[name], name, integer=True) < 1:
                            raise StudiesError(f"{name} must be positive")
                    self._quality(row)
                    if row["k"] > row["n"] or row["d"] > row["n"] or row["optimum"] > row["n"]:
                        raise StudiesError("study dimensions disagree")
                    if kind in {"r4", "r4_dual"}:
                        methods = ("initial_upper", "upper") if kind == "r4" else ("initial_upper", "prefix_upper", "dual_upper")
                        bounds = [number(row[name], name, integer=True) for name in methods]
                        if bounds != sorted(bounds, reverse=True) or min(bounds) < row["optimum"]:
                            raise StudiesError("saved bounds violate G <= O <= U <= initial")
                        if kind == "r4":
                            equal(row["tightening"], bounds[0] - bounds[1], "tightening")
                            equal(row["certified_ratio"], row["greedy"] / bounds[1], "certified_ratio")
                            equal(row["certified_optimal"], int(row["greedy"] == bounds[1]), "certified_optimal")
                        else:
                            for label, bound in zip(("initial", "prefix", "dual"), bounds):
                                equal(row[label + "_ratio"], row["greedy"] / bound, label + "_ratio")
                                equal(row[label + "_certified"], int(row["greedy"] == bound), label + "_certified")
                            equal(row["tightening_prefix"], bounds[1] - bounds[2], "tightening_prefix")
                cells = self._table(source, "cell_summary.csv")
                self._unique(cells, ("n", "d", "k"))
                grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
                for row in rows:
                    grouped[(row["n"], row["d"], row["k"])].append(row)
                if set(grouped) != {(r["n"], r["d"], r["k"]) for r in cells}:
                    raise StudiesError("summary cell membership differs")
                for cell in cells:
                    group = grouped[(cell["n"], cell["d"], cell["k"])]
                    equal(cell["count"], len(group), "cell count")
                    if kind == "r2":
                        equal(cell["failure_rate"], statistics.fmean(r["failure"] for r in group), "failure_rate")
                        equal(cell["mean_relative_gap"], statistics.fmean(r["relative_gap"] for r in group), "mean_relative_gap")
                        for metric, stem in (("failure_rate", "failure"), ("mean_relative_gap", "mean_relative_gap")):
                            if not 0 <= cell[stem + "_lower"] <= cell[metric] <= cell[stem + "_upper"] <= 1:
                                raise StudiesError("invalid saved interval")
                        calculations = {"mean_greedy": statistics.fmean(r["greedy"] for r in group),
                            "mean_optimum": statistics.fmean(r["optimum"] for r in group),
                            "mean_absolute_loss": statistics.fmean(r["absolute_loss"] for r in group),
                            "mean_ratio": statistics.fmean(r["greedy"] / r["optimum"] for r in group),
                            "ratio_of_means": sum(r["greedy"] for r in group) / sum(r["optimum"] for r in group),
                            "failures": sum(r["failure"] for r in group), "lambda": cell["k"] * cell["d"] / cell["n"]}
                        for metric, wanted in calculations.items():
                            if metric in cell:
                                equal(cell[metric], wanted, metric)
                    else:
                        for column in cell:
                            metric, _, statistic = column.rpartition("_")
                            if statistic not in {"mean", "median", "p90", "missing"} or metric not in group[0]:
                                continue
                            values = [r[metric] for r in group if r[metric] is not None]
                            summary = distribution(values)
                            wanted = len(group) - len(values) if statistic == "missing" else summary[statistic]
                            if wanted is None:
                                if cell[column] is not None:
                                    raise StudiesError(f"saved {column} must be missing")
                            else:
                                equal(cell[column], wanted, column)
                bases, primary = [], None
            tasks = config.get("tasks", [])
            if not isinstance(tasks, list) or not tasks:
                raise StudiesError("study analysis requires the saved graph task configuration")
            self._unique(tasks, ("base_graph_id",))
            if tasks:
                if {t["base_graph_id"] for t in tasks} != {r["base_graph_id"] for r in rows}:
                    raise StudiesError("saved graph membership differs from configuration")
                if kind != "r3":
                    expected = {(t["base_graph_id"], k, t["n"], t["d"]) for t in tasks for k in t["budgets"]}
                    if expected != {(r["base_graph_id"], r["k"], r["n"], r["d"]) for r in rows}:
                        raise StudiesError("missing or unexpected configured budget")
                else:
                    chain_ids = {(t["base_graph_id"], c["direction"], c["replica"]): str(c["seed"])
                                 for t in tasks for c in t["chains"]}
                    if chain_ids != {(r["base_graph_id"], r["direction"], r["replica"]): r["chain_seed"] for r in rows}:
                        raise StudiesError("R3 endpoint chain identity differs from configured design")
            return {"kind": kind, "rows": rows, "cells": cells, "bases": bases, "primary": primary, "config": config}
        except (KeyError, TypeError, OSError, ZeroDivisionError) as error:
            raise StudiesError(f"incomplete study artifacts: {error}") from error

    @staticmethod
    def _quality(row: dict[str, Any]) -> None:
        g, o = (number(row[key], key, integer=True) for key in ("greedy", "optimum"))
        if not 0 <= g <= o or o <= 0:
            raise StudiesError("relative metrics need 0 <= Greedy <= positive optimum")
        gap = (o - g) / o
        if "relative_gap" in row:
            equal(row["relative_gap"], gap, "relative_gap")
        row.update(relative_gap=gap, absolute_loss=o - g, failure=int(g < o))

    @staticmethod
    def _filter(rows: list[dict[str, Any]], filters: dict[str, str] | None) -> list[dict[str, Any]]:
        filters = filters or {}
        if set(filters) - {"n", "d", "k", "loss_only", "base_graph_id"}:
            raise StudiesError("unknown study filter")
        result = rows
        for key, value in filters.items():
            if value == "":
                continue
            if key == "loss_only":
                if value not in ("true", "false", "1", "0"):
                    raise StudiesError("invalid loss_only filter")
                if value in ("true", "1"):
                    result = [r for r in result if r.get("failure") == 1]
            elif key == "base_graph_id":
                result = [r for r in result if r["base_graph_id"] == value]
            else:
                wanted = number(value, key, integer=True)
                result = [r for r in result if r.get(key) == wanted]
        return result

    def overview(self, source: str, filters: dict[str, str] | None = None) -> dict[str, Any]:
        data = self._dataset(source)
        rows = self._filter(data["rows"], filters)
        ids = {r["base_graph_id"] for r in rows}
        result: dict[str, Any] = {"source": source, "kind": data["kind"], "notice": NOTICE,
            "graph_count": len(ids), "record_count": len(rows), "total_records": len(data["rows"]),
            "options": {key: sorted({r[key] for r in data["rows"] if key in r}) for key in ("n", "d", "k")},
            "cells": data["cells"], "primary": data["primary"], "pairs": [], "distributions": {}}
        if data["kind"] == "r3":
            # Outcome filters only narrow the record browser; never break four-endpoint pairs.
            bases = [r for r in data["bases"] if r["base_graph_id"] in ids]
            result["paired_graph_count"] = len(bases)
            for metric in ("first_loss", "failure", "relative_gap", "exposure"):
                result["distributions"]["high_minus_low_" + metric] = distribution(
                    [r["high_" + metric] - r["low_" + metric] for r in bases])
            result["pairs"] = bases
        else:
            fixed = len({(r["n"], r["d"], r["k"]) for r in rows}) <= 1
            result["fixed_cell"] = fixed
            if fixed:
                result["distributions"]["relative_gap"] = distribution([r["relative_gap"] for r in rows])
                result["distributions"]["absolute_loss"] = distribution([r["absolute_loss"] for r in rows])
                if data["kind"] != "r2":
                    for row in rows:
                        prefix = row["upper"] if data["kind"] == "r4" else row["prefix_upper"]
                        result["pairs"].append({"base_graph_id": row["base_graph_id"], "k": row["k"],
                            "initial": row["initial_upper"], "prefix": prefix,
                            "dual": row.get("dual_upper"), "initial_minus_prefix": row["initial_upper"] - prefix,
                            "prefix_minus_dual": prefix - row["dual_upper"] if "dual_upper" in row else None})
                    for metric in ("initial_minus_prefix", "prefix_minus_dual"):
                        samples = [r[metric] for r in result["pairs"] if r[metric] is not None]
                        if samples:
                            result["distributions"][metric] = distribution(samples)
        return result

    def records(self, source: str, filters: dict[str, str] | None = None, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise StudiesError("offset must be nonnegative and limit between 1 and 200")
        data = self._dataset(source)
        rows = self._filter(data["rows"], filters)
        rows.sort(key=lambda r: (r["base_graph_id"], r.get("k", 0), r.get("direction", 0), r.get("replica", 0)))
        return {"kind": data["kind"], "rows": rows[offset:offset + limit], "total": len(rows), "offset": offset,
                "graph_count": len({r["base_graph_id"] for r in rows})}

    def pairs(self, source: str, n: int, d: int, k_a: int, k_b: int, metric: str = "relative_gap") -> dict[str, Any]:
        data = self._dataset(source)
        if data["kind"] != "r2" or metric not in {"relative_gap", "absolute_loss", "greedy", "optimum"}:
            raise StudiesError("this pairing requires an R2 budget design and a supported metric")
        for key, value in (("n", n), ("d", d), ("k_a", k_a), ("k_b", k_b)):
            if type(value) is not int or value < 1:
                raise StudiesError(f"invalid {key}")
        if k_a == k_b:
            raise StudiesError("choose two distinct budgets")
        sides = [{r["base_graph_id"]: r for r in data["rows"] if (r["n"], r["d"], r["k"]) == (n, d, k)} for k in (k_a, k_b)]
        if not sides[0] or set(sides[0]) != set(sides[1]):
            raise StudiesError("budget pairs require identical, nonempty original graph membership")
        pairs = [{"base_graph_id": identifier, "a": sides[0][identifier][metric], "b": sides[1][identifier][metric],
                  "difference": sides[1][identifier][metric] - sides[0][identifier][metric]}
                 for identifier in sorted(sides[0])]
        return {"metric": metric, "k_a": k_a, "k_b": k_b, "pairs": pairs,
                "distribution": distribution([r["difference"] for r in pairs]),
                "notice": "同一来源、原图身份与维度配对；每原图一个 B−A 差值，描述性比较。"}

    def instance(self, source: str, base_graph_id: str, k: int | None = None,
                 direction: int | None = None, replica: int | None = None) -> dict[str, Any]:
        from .dashboard_study_instances import saved_instance
        return saved_instance(self, source, base_graph_id, k, direction, replica)

    def export_instance(self, source: str, base_graph_id: str, k: int | None = None,
                        direction: int | None = None, replica: int | None = None) -> dict[str, Any]:
        detail = self.instance(source, base_graph_id, k, direction, replica)
        return {"instance": detail["instance"], "replay": {"algorithm": "greedy", "options": {},
                "expected": {"coverage": detail["values"]["greedy"], "selected": detail["values"]["greedy_selected"]}},
                "provenance": detail["provenance"]}
