"""Public Gate 6C bounded spatial-query service."""
from caereflex.spatial.query_models import (
    SPATIAL_QUERY_VERSION,
    SpatialBoundsMode,
    SpatialQueryDiagnostic,
    SpatialQueryError,
    SpatialQueryLimits,
    SpatialQueryResult,
    SpatialTraversalDirection,
)
from caereflex.spatial.query_core import SpatialQueryCore
from caereflex.spatial.query_entities import SpatialEntityQueryMixin
from caereflex.spatial.query_relations import SpatialRelationQueryMixin
from caereflex.spatial.query_bounds import SpatialBoundsQueryMixin
from caereflex.spatial.query_traversal import SpatialTraversalQueryMixin


class SpatialQueryService(
    SpatialBoundsQueryMixin,
    SpatialTraversalQueryMixin,
    SpatialEntityQueryMixin,
    SpatialRelationQueryMixin,
    SpatialQueryCore,
):
    """Bounded read-only queries over persisted canonical spatial graphs."""


__all__ = [
    "SPATIAL_QUERY_VERSION",
    "SpatialBoundsMode",
    "SpatialQueryDiagnostic",
    "SpatialQueryError",
    "SpatialQueryLimits",
    "SpatialQueryResult",
    "SpatialQueryService",
    "SpatialTraversalDirection",
]
