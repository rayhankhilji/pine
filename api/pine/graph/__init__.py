"""Knowledge graph — entity/relation extraction, resolution, export (F-04)."""

from pine.graph.build import BuildStats, build_graph
from pine.graph.export import export_graphml, export_json
from pine.graph.resolve import (
    FUZZY_THRESHOLD,
    EntityNameConflict,
    ResolveStats,
    merge_entities,
    resolve_entities,
    split_entity,
)

__all__ = [
    "FUZZY_THRESHOLD",
    "BuildStats",
    "EntityNameConflict",
    "ResolveStats",
    "build_graph",
    "export_graphml",
    "export_json",
    "merge_entities",
    "resolve_entities",
    "split_entity",
]
