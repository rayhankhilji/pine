"""P3.T13 — offline demo evaluation against ground_truth.json.

Builds the Northwind room into a temp dir, ingests into an isolated SQLite
database, drains the full job chain and asserts ≥90% fact recall plus all
expected entities/aliases.
"""

from pine.demo.eval import RECALL_THRESHOLD, run_demo_eval


def test_demo_eval_fact_recall_and_entities() -> None:
    result = run_demo_eval()

    assert result.failed_jobs == []
    assert result.fact_recall >= RECALL_THRESHOLD, result.facts
    for entity in result.entities:
        assert entity.found, f"missing entity: {entity.canonical_name}"
        assert entity.missing_aliases == [], (
            f"{entity.canonical_name}: missing aliases {entity.missing_aliases}"
        )
    assert result.passed
