"""Pydantic schemas for the knowledge-graph endpoints (§5, F-04)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pine.api.schemas.facts import Evidence, Fact
from pine.schemas.entities import EntityType, RelationType


class Entity(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    type: EntityType | str
    canonical_name: str
    normalized_name: str
    attrs: dict[str, Any]
    confidence: float
    merged_into_id: str | None
    created_at: datetime
    updated_at: datetime


class EntityAlias(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_id: str
    alias: str
    normalized: str
    source_document_id: str | None
    created_at: datetime


class Relation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    type: RelationType | str
    source_entity_id: str
    target_entity_id: str
    attrs: dict[str, Any]
    confidence: float
    created_at: datetime


class GraphResponse(BaseModel):
    nodes: list[Entity]
    edges: list[Relation]


class EntityDetail(Entity):
    aliases: list[EntityAlias] = []
    evidence: list[Evidence] = []
    relations: list[Relation] = []
    facts: list[Fact] = []


class EntityMerge(BaseModel):
    into_entity_id: str = Field(min_length=1)


class EntitySplit(BaseModel):
    alias_ids: list[str] = Field(min_length=1)
