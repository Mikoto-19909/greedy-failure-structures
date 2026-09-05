"""Shared report labels and colors."""

from __future__ import annotations




COLORS = {
    "brute_force": "#6b7280",
    "branch_and_bound": "#7c3aed",
    "branch_and_bound_enhanced": "#2563eb",
    "cp_sat_oracle": "#4f46e5",
    "greedy": "#dc2626",
    "lazy_greedy": "#65a30d",
    "local_search": "#059669",
    "multi_start_local_search": "#0891b2",
    "randomized_greedy": "#d97706",
}


_ALGORITHM_LABELS = {
    "brute_force": "穷举搜索",
    "branch_and_bound": "分支定界",
    "branch_and_bound_enhanced": "增强分支定界",
    "cp_sat_oracle": "CP-SAT 精确求解",
    "greedy": "贪心算法",
    "lazy_greedy": "惰性贪心",
    "local_search": "局部搜索",
    "multi_start_local_search": "多起点局部搜索",
    "randomized_greedy": "随机贪心",
}
_CASE_LABELS = {
    "uniform_sparse": "均匀分布 · 稀疏",
    "uniform_dense": "均匀分布 · 稠密",
    "overlap_core": "高重叠 · 核心",
    "overlap_moderate": "高重叠 · 中等",
    "overlap_extreme": "高重叠 · 极端",
    "four_clusters": "四簇聚类",
    "eight_clusters": "八簇聚类",
    "greedy_trap": "贪心陷阱",
    "greedy_trap_small": "贪心陷阱 · 小型",
    "greedy_trap_large": "贪心陷阱 · 大型",
}
_FAMILY_LABELS = {
    "uniform": "均匀分布",
    "high_overlap": "高重叠",
    "clustered": "聚类",
    "adversarial": "对抗构造",
    "fixed_size_uniform": "固定大小 · 均匀分布",
    "mixed_cluster": "混合聚类",
    "long_tail": "长尾分布",
}
_PREDICTOR_LABELS = {
    "density": "密度",
    "overlap": "重叠度",
    "clustering": "聚类程度",
    "set_count": "集合数量",
    "k": "选择预算 k",
    "dominated_set_ratio": "被支配集合比例",
}
_UNIT_LABELS = {
    "instance_seed": "实例种子",
    "coupling_seed_block": "耦合种子区块",
}
_STATUS_LABELS = {
    "estimable": "可估计",
    "no_samples": "无可用样本",
    "not_evaluable": "不可评估",
    "withheld_insufficient_samples": "样本不足，暂不汇总",
    "withheld_unestimable_interval": "区间不可估计，暂不汇总",
}
_REFERENCE_STATUS_LABELS = {
    "known_optimum_certificate": "已知最优证书",
    "optimal": "求解器证明最优",
    "feasible": "仅有可行解",
    "timeout": "超时",
    "error": "错误",
    "not_run": "未运行",
}
_REFERENCE_STATUS_COLORS = {
    "known_optimum_certificate": "#047857",
    "optimal": "#16a34a",
    "feasible": "#d97706",
    "timeout": "#dc2626",
    "error": "#7f1d1d",
    "not_run": "#9ca3af",
}


def _readable_identifier(value: str) -> str:
    """Return a visible fallback without exposing an underscored identifier."""

    words = value.replace("-", "_").split("_")
    return " ".join(word.capitalize() for word in words if word)


def _algorithm_label(value: str) -> str:
    return _ALGORITHM_LABELS.get(value, _readable_identifier(value))


def _case_label(value: str) -> str:
    return _CASE_LABELS.get(value, _readable_identifier(value))


def _family_label(value: str) -> str:
    return _FAMILY_LABELS.get(value, _readable_identifier(value))


def _predictor_label(value: str) -> str:
    return _PREDICTOR_LABELS.get(value, _readable_identifier(value))


def _unit_label(value: str) -> str:
    return _UNIT_LABELS.get(value, _readable_identifier(value))


def _status_label(value: str) -> str:
    return _STATUS_LABELS.get(value, _readable_identifier(value))
