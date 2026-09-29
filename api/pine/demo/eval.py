"""Offline demo evaluation (PRD F-14, P3.T13).

`run_demo_eval()` builds the Northwind room into a temporary directory,
ingests it into an isolated SQLite database, drains the full job chain
synchronously (parse → classify → index → extract_facts → build_graph →
detect_contradictions) and scores extracted facts/entities against
`ground_truth.json`.
"""

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.table import Table
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

import pine.contradictions.jobs  # noqa: F401 — registers detect_contradictions
import pine.facts.jobs  # noqa: F401 — registers extract_facts
import pine.graph.jobs  # noqa: F401 — registers build_graph
import pine.index.jobs  # noqa: F401 — registers index_deal
import pine.ingest.jobs  # noqa: F401 — registers parse/classify handlers
from pine.api.schemas.deal import DealCreate
from pine.config import get_settings
from pine.db import Base
from pine.demo.build import build_demo
from pine.demo.schema import GroundTruth, GroundTruthFact
from pine.jobs.worker import _HANDLERS
from pine.models.deal import DealStage
from pine.models.document import Document
from pine.models.entity import Entity, EntityAlias
from pine.models.evidence import Evidence, EvidenceTarget
from pine.models.fact import Fact
from pine.models.job import Job, JobKind, JobStatus
from pine.repos import deals as deals_repo
from pine.schemas.entities import normalize_entity_name
from pine.services.demo import DEMO_COMPANY, DEMO_DEAL_NAME
from pine.services.uploads import ingest_upload
from pine.storage.blobstore import BlobStore

RECALL_THRESHOLD = 0.90
DRAIN_LIMIT = 600


@dataclass
class FactResult:
    metric: str
    expected: float
    found: float | None
    source_file: str
    ok: bool


@dataclass
class EntityResult:
    type: str
    canonical_name: str
    found: bool
    missing_aliases: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    deal_id: str
    documents: int
    facts: list[FactResult]
    entities: list[EntityResult]
    failed_jobs: list[str]

    @property
    def fact_recall(self) -> float:
        if not self.facts:
            return 0.0
        return sum(1 for f in self.facts if f.ok) / len(self.facts)

    @property
    def entities_ok(self) -> bool:
        return all(e.found and not e.missing_aliases for e in self.entities)

    @property
    def passed(self) -> bool:
        return self.fact_recall >= RECALL_THRESHOLD and self.entities_ok


# ---------------------------------------------------------------------------
# ingest + drain


def _drain_jobs(session: Session, limit: int = DRAIN_LIMIT) -> None:
    """Run every queued job synchronously until the queue is empty."""
    for _ in range(limit):
        job = session.scalar(
            select(Job)
            .where(Job.status == JobStatus.queued)
            .order_by(Job.created_at)
            .limit(1)
        )
        if job is None:
            return
        try:
            _HANDLERS[JobKind(job.kind)](session, job)
        except Exception as exc:
            raise RuntimeError(
                f"{job.kind} job {job.id} failed during eval drain: {exc}"
            ) from exc
        job.status = JobStatus.succeeded
        session.commit()
    raise RuntimeError(f"job queue did not drain after {limit} jobs")


# ---------------------------------------------------------------------------
# scoring


def _period_overlap(fact: Fact, gt: GroundTruthFact) -> bool:
    f_start = fact.period_start or fact.as_of
    f_end = fact.period_end or fact.as_of or f_start
    g_start = gt.period.start
    g_end = gt.period.end or gt.period.start
    if f_start is None or f_end is None or g_start is None or g_end is None:
        return False
    return f_start <= g_end and g_start <= f_end


def _value_ok(fact: Fact, gt: GroundTruthFact) -> bool:
    if fact.value is None:
        return False
    tol = (gt.tolerance_pct / 100.0) * abs(float(gt.value))
    return abs(float(fact.value) - float(gt.value)) <= tol + 1e-9


def _fact_source_names(session: Session, deal_id: str) -> dict[str, set[str]]:
    """fact id → {basename(document.path), document.filename} via evidence."""
    rows = session.execute(
        select(Evidence.target_id, Document.path, Document.filename)
        .join(Document, Evidence.document_id == Document.id)
        .where(Evidence.deal_id == deal_id)
        .where(Evidence.target_kind == EvidenceTarget.fact.value)
    ).all()
    names: dict[str, set[str]] = {}
    for target_id, path, filename in rows:
        if target_id is None:
            continue
        bucket = names.setdefault(target_id, set())
        if path:
            bucket.add(Path(path).name)
        if filename:
            bucket.add(filename)
    return names


def _score_facts(
    session: Session, deal_id: str, gt_facts: list[GroundTruthFact]
) -> list[FactResult]:
    facts = session.scalars(
        select(Fact)
        .where(Fact.deal_id == deal_id)
        .where(Fact.superseded_by_id.is_(None))
    ).all()
    src_names = _fact_source_names(session, deal_id)
    results: list[FactResult] = []
    for gt in gt_facts:
        wanted = Path(gt.source_file).name
        candidates = [f for f in facts if f.metric == gt.metric]

        hit: Fact | None = None
        for f in candidates:
            if (
                _value_ok(f, gt)
                and _period_overlap(f, gt)
                and wanted in src_names.get(f.id, set())
            ):
                hit = f
                break
        if hit is not None:
            found = float(hit.value) if hit.value is not None else None
            results.append(
                FactResult(gt.metric, float(gt.value), found, gt.source_file, True)
            )
            continue
        # for the report, surface the closest value match on metric+period
        value_ok = [f for f in candidates if _value_ok(f, gt)]
        near = min(
            value_ok or candidates,
            key=lambda f: abs(
                (float(f.value) if f.value is not None else float("inf"))
                - float(gt.value)
            ),
            default=None,
        )
        found = (
            float(near.value) if near is not None and near.value is not None else None
        )
        results.append(
            FactResult(gt.metric, float(gt.value), found, gt.source_file, False)
        )
    return results


def _score_entities(
    session: Session, deal_id: str, gt: GroundTruth
) -> list[EntityResult]:
    entities = session.scalars(
        select(Entity)
        .where(Entity.deal_id == deal_id)
        .where(Entity.merged_into_id.is_(None))
    ).all()
    live_names = {e.normalized_name for e in entities}
    alias_rows = session.scalars(
        select(EntityAlias)
        .join(Entity, EntityAlias.entity_id == Entity.id)
        .where(Entity.deal_id == deal_id)
    ).all()
    alias_norms = {a.normalized for a in alias_rows}
    alias_lits = {a.alias for a in alias_rows}

    results: list[EntityResult] = []
    for ge in gt.entities:
        found = normalize_entity_name(ge.canonical_name) in live_names
        missing = [
            alias
            for alias in ge.aliases
            if alias not in alias_lits
            and normalize_entity_name(alias) not in alias_norms
        ]
        results.append(EntityResult(ge.type, ge.canonical_name, found, missing))
    return results


def _score(session: Session, deal_id: str, room: Path) -> EvalResult:
    gt = GroundTruth.model_validate(
        json.loads((room / "ground_truth.json").read_text())
    )
    documents = session.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.deal_id == deal_id)
    )
    failed = session.scalars(
        select(Job).where(Job.deal_id == deal_id).where(
            Job.status == JobStatus.failed
        )
    ).all()
    return EvalResult(
        deal_id=deal_id,
        documents=int(documents or 0),
        facts=_score_facts(session, deal_id, gt.facts),
        entities=_score_entities(session, deal_id, gt),
        failed_jobs=[f"{j.kind}:{j.id}" for j in failed],
    )


# ---------------------------------------------------------------------------
# entry point


def run_demo_eval(base_dir: Path | None = None) -> EvalResult:
    """Build, ingest, drain and score the Northwind demo — fully offline."""
    with tempfile.TemporaryDirectory(dir=base_dir, prefix="pine-eval-") as tmp:
        root = Path(tmp)
        room = build_demo(root / "room")
        storage = root / "storage"
        engine = create_engine(f"sqlite:///{root / 'eval.db'}")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        settings = get_settings()
        prev_storage = settings.STORAGE_DIR
        settings.STORAGE_DIR = str(storage)
        try:
            with factory() as session:
                deal = deals_repo.create_deal(
                    session,
                    DealCreate(
                        name=DEMO_DEAL_NAME,
                        company_name=DEMO_COMPANY,
                        stage=DealStage.series_b,
                    ),
                )
                store = BlobStore(storage)
                files: list[tuple[str, bytes]] = []
                paths: list[str] = []
                for path in sorted(room.rglob("*")):
                    if not path.is_file() or path.name == "ground_truth.json":
                        continue
                    files.append((path.name, path.read_bytes()))
                    paths.append(path.relative_to(room).as_posix())
                ingest_upload(session, store, deal, files, paths)
                _drain_jobs(session)
                result = _score(session, deal.id, room)
        finally:
            settings.STORAGE_DIR = prev_storage
            engine.dispose()
    return result


# ---------------------------------------------------------------------------
# report


def _fmt_value(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def print_report(result: EvalResult, console: Console) -> None:
    table = Table(title="Demo fact recall")
    table.add_column("Metric", style="bold")
    table.add_column("Expected", justify="right")
    table.add_column("Found", justify="right")
    table.add_column("Source file")
    table.add_column("Status")
    for f in result.facts:
        status = "[green]ok[/green]" if f.ok else "[red]missed[/red]"
        table.add_row(
            f.metric, _fmt_value(f.expected), _fmt_value(f.found),
            f.source_file, status,
        )
    console.print(table)
    console.print(f"FACT RECALL: {result.fact_recall:.0%}")

    etable = Table(title="Entities")
    etable.add_column("Type")
    etable.add_column("Canonical name", style="bold")
    etable.add_column("Status")
    for e in result.entities:
        if not e.found:
            status = "[red]missing[/red]"
        elif e.missing_aliases:
            status = f"[red]missing aliases: {', '.join(e.missing_aliases)}[/red]"
        else:
            status = "[green]ok[/green]"
        etable.add_row(e.type, e.canonical_name, status)
    console.print(etable)

    if result.failed_jobs:
        console.print(f"[red]failed jobs:[/red] {', '.join(result.failed_jobs)}")
    console.print("CONTRADICTIONS: pending (P4)")
