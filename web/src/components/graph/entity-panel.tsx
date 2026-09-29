"use client";

import { ArrowRight, Quote } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useEntity, type EntityDetail, type Relation } from "@/lib/api/hooks";
import { formatFactValue, metricLabel, periodLabel } from "@/lib/facts";
import { relationTypeLabel } from "@/lib/graph";

function PanelSection({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="flex items-center gap-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
        {title}
        {count !== undefined && (
          <span className="font-mono tnum">{count}</span>
        )}
      </h3>
      {children}
    </section>
  );
}

function RelationRow({
  relation,
  entityId,
  nameFor,
}: {
  relation: Relation;
  entityId: string;
  nameFor: (id: string) => string;
}) {
  const outbound = relation.source_entity_id === entityId;
  const otherId = outbound
    ? relation.target_entity_id
    : relation.source_entity_id;
  return (
    <li className="flex items-center gap-1.5 text-sm">
      <Badge variant="outline" className="font-mono text-xs">
        {relationTypeLabel(relation.type)}
      </Badge>
      <ArrowRight
        className={`size-3 text-muted-foreground ${outbound ? "" : "rotate-180"}`}
      />
      <span className="truncate">{nameFor(otherId)}</span>
    </li>
  );
}

function EntityDetailBody({
  entity,
  dealId,
  currency,
  nameFor,
}: {
  entity: EntityDetail;
  dealId: string;
  currency: string;
  nameFor: (id: string) => string;
}) {
  return (
    <div className="flex flex-col gap-5 overflow-y-auto px-4 pb-6">
      <PanelSection title="Aliases" count={entity.aliases.length}>
        {entity.aliases.length === 0 ? (
          <p className="text-sm text-muted-foreground">No aliases recorded.</p>
        ) : (
          <div className="flex flex-wrap gap-1">
            {entity.aliases.map((alias) => (
              <Badge
                key={alias.id}
                variant="secondary"
                className="font-mono text-xs"
              >
                {alias.alias}
              </Badge>
            ))}
          </div>
        )}
      </PanelSection>

      <PanelSection title="Evidence" count={entity.evidence.length}>
        {entity.evidence.length === 0 ? (
          <p className="text-sm text-muted-foreground">No evidence rows.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {entity.evidence.map((ev) => (
              <li
                key={ev.id}
                className="flex flex-col gap-1 border-l-2 border-accent pl-2"
              >
                <p className="flex items-start gap-1.5 text-xs leading-snug">
                  <Quote className="mt-0.5 size-3 shrink-0 text-muted-foreground" />
                  <span className="line-clamp-2">“{ev.quote}”</span>
                </p>
                <Link
                  href={`/deals/${dealId}/documents/${ev.document_id}?page=${ev.page_no}`}
                  className="font-mono text-xs text-primary hover:underline"
                >
                  {ev.filename ?? "document"} · p{ev.page_no}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </PanelSection>

      <PanelSection title="Relations" count={entity.relations.length}>
        {entity.relations.length === 0 ? (
          <p className="text-sm text-muted-foreground">No relations.</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {entity.relations.map((rel) => (
              <RelationRow
                key={rel.id}
                relation={rel}
                entityId={entity.id}
                nameFor={nameFor}
              />
            ))}
          </ul>
        )}
      </PanelSection>

      <PanelSection title="Facts" count={entity.facts.length}>
        {entity.facts.length === 0 ? (
          <p className="text-sm text-muted-foreground">No facts on this entity.</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {entity.facts.map((fact) => (
              <li
                key={fact.id}
                className="flex items-baseline justify-between gap-2 text-sm"
              >
                <span className="text-muted-foreground">
                  {metricLabel(fact.metric)}
                </span>
                <span className="font-mono text-xs tnum">
                  {formatFactValue(fact, currency)}
                  <span className="text-muted-foreground">
                    {" · "}
                    {periodLabel(fact)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </PanelSection>
    </div>
  );
}

export function EntityPanelBody({
  entityId,
  dealId,
  currency,
  nameFor,
}: {
  entityId: string;
  dealId: string;
  currency: string;
  nameFor: (id: string) => string;
}) {
  const entity = useEntity(entityId);

  if (entity.isPending) {
    return (
      <div className="flex flex-col gap-3 px-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }

  if (entity.isError) {
    return (
      <div className="flex flex-col items-start gap-3 px-4">
        <p className="text-sm text-destructive">
          Could not load entity — {entity.error.message}
        </p>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void entity.refetch()}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <EntityDetailBody
      entity={entity.data}
      dealId={dealId}
      currency={currency}
      nameFor={nameFor}
    />
  );
}

