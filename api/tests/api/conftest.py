"""API tests share the facts fixtures (demo_deal, mk_* helpers)."""

from tests.facts.conftest import (  # noqa: F401 — fixture re-export
    demo_deal,
    drain_jobs,
    mk_chunk,
    mk_deal,
    mk_document,
)
