"""Compatibility exports for benchmark structural associations.

Implementations are grouped by quality and performance responsibilities.
"""

from .benchmark_statistics import _ten_decimal
from ._benchmark_quality_associations import (
    _gap_density_association_statistics,
    _gap_overlap_association_statistics,
    _gap_clustering_association_statistics,
)
from ._benchmark_performance_associations import (
    _runtime_set_count_association_statistics,
    _RuntimeKInstanceProjection,
    _runtime_k_association_statistics,
    _search_nodes_dominated_ratio_association_statistics,
)
