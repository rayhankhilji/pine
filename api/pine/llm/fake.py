"""Deterministic offline LLM for tests/evals (ARCHITECTURE §10, ADR-006).

Two scripting layers, checked in order:

1. **Scripts** — explicit `scripts=[{purpose, match, response}]` passed to the
   constructor, then every `*.yaml`/`*.yml`/`*.json` file under
   `fixtures_dir` (env `PINE_FAKE_LLM_DIR`, default `tests/fixtures/llm`).
   `match` is a regex applied to the last user message (DOTALL).
2. **Purpose fallbacks** — `rerank` returns a stable permutation and
   `extract_facts` runs a small rule-based extractor over the
   `---BEGIN TEXT---`/`---END TEXT---` block so the demo eval and pipeline
   tests produce real, evidence-quoting facts offline.

Anything else raises — an unscripted purpose is a test bug, not a guess.
"""

import json
import logging
import os
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from pine.facts.periods import parse_period
from pine.llm.base import Message, StructuredResult
from pine.schemas.entities import normalize_entity_name

logger = logging.getLogger(__name__)

_CANDIDATES_RE = re.compile(r"^Candidates:\s*(\d+)\s*$", re.M)
_TEXT_BLOCK_RE = re.compile(r"---BEGIN TEXT---\n(.*?)\n---END TEXT---", re.S)
_DEFAULT_PERIOD_RE = re.compile(r"^Default period:\s*(.+?)\s*$", re.M)
_DOC_DATE_RE = re.compile(r"^Document date:\s*(.+?)\s*$", re.M)
_COMPANY_RE = re.compile(r"^Company:\s*(.+?)\s*$", re.M)
# counterparty of a contract-style document: "between <company> and <party>",
# or a title line like "ORDER FORM — Kestrel Bank"
_BETWEEN_RE = re.compile(
    r"between\s+(?P<p1>[^\n]{2,80}?)\s+and\s+"
    r"(?P<p2>[^\n]{2,80}?)\s*(?:\(|,|\.|—|\s+under\s|\s+dated\s|$)",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(
    r"(?:order form|statement of work|sow|agreement)\s*[—–-]\s*"
    r"(?P<party>[^\n]{2,80})",
    re.IGNORECASE,
)
# metrics whose subject is the counterparty when one is identified
_PARTY_METRICS = {"contract_value", "litigation_exposure"}

# money: "$12.0M" | "~$300k" | "$312,000" | "40B" | "450k" — a bare "3x"/"2025"
# never counts: a value needs a "$" prefix or a k/m/b suffix.
_M = (
    r"(?:(?:~\s*)?\$\s*(?P<v>\d[\d,]*(?:\.\d+)?)\s*(?P<s>[kmbKMB])?"
    r"|(?P<v2>\d[\d,]*(?:\.\d+)?)\s*(?P<s2>[kmbKMB]))"
)
_N = r"(?P<n>\d[\d,]*(?:\.\d+)?)"
_PCT = r"(?P<p>\d+(?:\.\d+)?)\s*%"
_GAP = r"[^.;\n]{0,80}?"  # at most one sentence between keyword and value

_SCALE = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
_YEARS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


class _Rule:
    """(pattern, metric, unit, default): default = 'point'|'reference'|'none'."""

    def __init__(self, pattern: str, metric: str, unit: str, default: str) -> None:
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.metric = metric
        self.unit = unit
        self.default = default


_RULES = [
    _Rule(rf"\bARR\b{_GAP}{_M}", "arr", "currency", "reference"),
    _Rule(rf"\bTAM\b{_GAP}{_M}", "tam", "currency", "reference"),
    _Rule(rf"\bSAM\b{_GAP}{_M}", "sam", "currency", "reference"),
    _Rule(rf"\bSOM\b{_GAP}{_M}", "som", "currency", "reference"),
    _Rule(
        rf"\brecurring revenue\b{_GAP}{_M}",
        "recurring_revenue", "currency", "reference",
    ),
    _Rule(
        rf"{_M}{_GAP}\brecurring revenue\b",
        "recurring_revenue", "currency", "reference",
    ),
    _Rule(rf"\bnet burn\b{_GAP}{_M}", "net_burn", "currency", "reference"),
    _Rule(rf"\brunway\b{_GAP}{_N}\s*months\b", "runway_months", "months", "point"),
    _Rule(rf"{_N}\s*months\s+of\s+runway\b", "runway_months", "months", "point"),
    _Rule(rf"\bNRR\b{_GAP}{_PCT}", "net_revenue_retention", "percent", "reference"),
    _Rule(
        rf"\bnet revenue retention\b{_GAP}{_PCT}",
        "net_revenue_retention", "percent", "reference",
    ),
    _Rule(rf"\bGRR\b{_GAP}{_PCT}", "gross_revenue_retention", "percent", "reference"),
    _Rule(rf"\bgross margin\b{_GAP}{_PCT}", "gross_margin", "percent", "reference"),
    _Rule(rf"\bheadcount\b{_GAP}{_N}", "headcount", "count", "reference"),
    _Rule(rf"{_N}\s*employees\b", "headcount", "count", "reference"),
    _Rule(rf"{_N}\s*customers\b", "customers_count", "count", "reference"),
    _Rule(rf"{_N}\s*logos\b", "customers_count", "count", "reference"),
    _Rule(rf"\blogo churn\b{_GAP}{_N}", "logo_churn", "count", "reference"),
    _Rule(rf"\bcash\b{_GAP}{_M}", "cash_balance", "currency", "point"),
    _Rule(
        rf"\b(?:total\s+)?contract\s+value\b{_GAP}{_M}",
        "contract_value", "currency", "none",
    ),
    _Rule(rf"\bTCV\b{_GAP}{_M}", "contract_value", "currency", "none"),
    _Rule(rf"\bfees?\b{_GAP}{_M}", "contract_value", "currency", "none"),
    _Rule(rf"\border value\b{_GAP}{_M}", "contract_value", "currency", "none"),
    _Rule(
        rf"\blitigation\b{_GAP}{_M}",
        "litigation_exposure", "currency", "reference",
    ),
    _Rule(
        rf"(?<!recurring )\brevenue\b{_GAP}{_M}",
        "revenue", "currency", "reference",
    ),
    _Rule(
        rf"(?:\bCOGS\b|\bcost of (?:goods|revenue)\b){_GAP}{_M}",
        "cogs", "currency", "reference",
    ),
    _Rule(
        rf"\bgross profit\b{_GAP}{_M}", "gross_profit", "currency", "reference"
    ),
    _Rule(rf"\bEBITDA\b{_GAP}{_M}", "ebitda", "currency", "reference"),
]

_TERM_RE = re.compile(
    r"(?P<years>\w+)\s*(?:\(\s*\d+\s*\)\s*)?years?\b[^.;\n]{0,60}?"
    r"commenc\w+\s+(?P<day>.+?)(?:[.;]|$)",
    re.IGNORECASE,
)
# a verbatim period label inside a sentence (as-of first; 4-digit years only)
_SENT_PERIOD_RE = re.compile(
    r"(as of\s+.{0,40}?\d{4})"
    r"|(Q[1-4]\s*'?\s*(?:FY\s*)?\d{2,4})"
    r"|([1-4]Q\s*'?\d{2,4})"
    r"|(FY\s*'?\d{2,4})"
    r"|((?:TTM|LTM)[^.;\n]{0,20})"
    r"|(\b(?:19|20)\d{2}-\d{2}(?:-\d{2})?\b)"
    r"|(\b(?:19|20)\d{2}\b)",
    re.IGNORECASE,
)
_AS_OF_ANYWHERE_RE = re.compile(r"as of\s+(.{0,40}?\d{4})", re.IGNORECASE)


def _money(m: re.Match[str]) -> float | None:
    groups = m.groupdict()
    raw = groups.get("v") or groups.get("v2")
    scale = groups.get("s") or groups.get("s2")
    if raw is None:
        return None
    num = raw.replace("$", "").replace("~", "").replace(",", "").strip()
    try:
        value = float(num)
    except ValueError:
        return None
    if scale:
        value *= _SCALE[scale.lower()]
    return value


def _plain_number(m: re.Match[str]) -> float | None:
    groups = m.groupdict()
    raw = groups.get("n") or groups.get("p")
    if raw is None:
        return None
    return float(raw.replace(",", ""))


def _sentence_at(text: str, start: int) -> str:
    """Sentence/line containing offset `start` — a verbatim quote span."""
    left = max(text.rfind("\n", 0, start), text.rfind(". ", 0, start)) + 1
    candidates = [
        i for i in (text.find("\n", start), text.find(". ", start)) if i >= 0
    ]
    right = min(candidates) if candidates else len(text)
    return text[left:right].strip()


def _period_label(
    sentence: str, text: str, default: str, ref: str | None, doc_date: str | None
) -> str | None:
    term = _TERM_RE.search(sentence)
    if term is not None:
        spec = parse_period(term["day"])
        raw_years = term["years"]
        years = _YEARS.get(raw_years.lower()) or (
            int(raw_years) if raw_years.isdigit() else None
        )
        if spec is not None and spec.as_of is not None and years:
            start = spec.as_of
            try:
                end = start.replace(year=start.year + years) - timedelta(days=1)
            except ValueError:  # Feb 29 → land on Feb 28 of the last year
                end = start.replace(year=start.year + years, day=28) - timedelta(
                    days=1
                )
            return f"{start.isoformat()} to {end.isoformat()}"
    match = _SENT_PERIOD_RE.search(sentence)
    if match is not None:
        return match[0].strip()
    as_of = _AS_OF_ANYWHERE_RE.search(text)
    if as_of is not None and default == "point":
        return f"as of {as_of[1].strip()}"
    if default == "point" and doc_date and doc_date != "unknown":
        return f"as of {doc_date}"
    if default == "reference":
        return ref
    return None


def _counterparty(raw_text: str, company_norm: str) -> str | None:
    """The non-company party named by the document, if any (verbatim)."""
    norm_text = " ".join(raw_text.split())
    match = _BETWEEN_RE.search(norm_text)
    if match is not None:
        for key in ("p2", "p1"):
            party = match[key].strip()
            if normalize_entity_name(party) != company_norm:
                return party
    title = _TITLE_RE.search(raw_text)
    if title is not None:
        party = title["party"].strip().rstrip(".")
        if normalize_entity_name(party) != company_norm:
            return party
    return None


def _last_user(messages: list[Message]) -> str:
    return next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )


class FakeLLM:
    model = "fake-llm"

    def __init__(
        self,
        scripts: list[dict[str, Any]] | None = None,
        fixtures_dir: str | Path | None = None,
    ) -> None:
        self._explicit = list(scripts or [])
        env_dir = os.environ.get("PINE_FAKE_LLM_DIR")
        if fixtures_dir is not None:
            self._fixtures_dir: Path | None = Path(fixtures_dir)
        elif env_dir:
            self._fixtures_dir = Path(env_dir)
        else:
            default = (
                Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "llm"
            )
            self._fixtures_dir = default if default.exists() else None
        self._fixture_scripts: list[dict[str, Any]] | None = None

    def _scripts(self) -> list[dict[str, Any]]:
        if self._fixture_scripts is None:
            self._fixture_scripts = self._load_fixture_dir()
        return [*self._explicit, *self._fixture_scripts]

    def _load_fixture_dir(self) -> list[dict[str, Any]]:
        if self._fixtures_dir is None or not self._fixtures_dir.exists():
            return []
        out: list[dict[str, Any]] = []
        for path in sorted(self._fixtures_dir.iterdir()):
            if path.suffix not in {".yaml", ".yml", ".json"}:
                continue
            if path.suffix == ".json":
                data: Any = json.loads(path.read_text())
            else:
                import yaml

                data = yaml.safe_load(path.read_text())
            scripts = data["scripts"] if isinstance(data, dict) else data
            for script in scripts or []:
                out.append(
                    {
                        "purpose": script["purpose"],
                        "match": script["match"],
                        "response": script["response"],
                    }
                )
        return out

    async def complete_structured(
        self,
        *,
        messages: list[Message],
        schema: type[BaseModel],
        purpose: str,
        model: str | None = None,
        max_output_tokens: int = 4096,
    ) -> StructuredResult:
        last_user = _last_user(messages)
        for script in self._scripts():
            if script["purpose"] != purpose:
                continue
            if re.search(script["match"], last_user, re.S):
                return self._result(schema, script["response"], messages)
        if purpose == "rerank":
            return self._result(schema, self._rerank(messages), messages)
        if purpose == "extract_facts":
            return self._result(
                schema, {"facts": self._extract(last_user)}, messages
            )
        raise RuntimeError(f"FakeLLM: no scripted response for purpose {purpose!r}")

    def _result(
        self,
        schema: type[BaseModel],
        payload: BaseModel | dict[str, Any],
        messages: list[Message],
    ) -> StructuredResult:
        raw = payload if isinstance(payload, dict) else payload.model_dump()
        parsed = schema.model_validate(raw)
        tokens_in = sum(len(m["content"]) for m in messages) // 4
        tokens_out = len(json.dumps(raw, default=str)) // 4
        return StructuredResult(
            parsed=parsed, tokens_in=tokens_in, tokens_out=tokens_out
        )

    def _rerank(self, messages: list[Message]) -> dict[str, Any]:
        last_user = _last_user(messages)
        match = _CANDIDATES_RE.search(last_user)
        n = int(match.group(1)) if match else 0
        # 1-based positions: keep the top 3 stable, reverse the tail
        ranking = [1, 2, 3][:n] + list(range(n, 3, -1))
        return {"ranking": ranking}

    def _extract(self, user_message: str) -> list[dict[str, Any]]:
        block = _TEXT_BLOCK_RE.search(user_message)
        if block is None:
            return []
        text = block[1]
        ref_match = _DEFAULT_PERIOD_RE.search(user_message)
        ref = ref_match[1] if ref_match and ref_match[1] != "none" else None
        date_match = _DOC_DATE_RE.search(user_message)
        doc_date = date_match[1] if date_match else None
        company_match = _COMPANY_RE.search(user_message)
        company_norm = (
            normalize_entity_name(company_match[1]) if company_match else ""
        )
        counterparty = _counterparty(text, company_norm)

        seen: set[tuple[str, float, str]] = set()
        facts: list[dict[str, Any]] = []
        for rule in _RULES:
            for m in rule.pattern.finditer(text):
                value = _money(m) or _plain_number(m)
                if value is None:
                    continue
                quote = _sentence_at(text, m.start())
                if not quote:
                    continue
                label = _period_label(quote, text, rule.default, ref, doc_date)
                key = (rule.metric, value, quote)
                if key in seen:
                    continue
                seen.add(key)
                fact: dict[str, Any] = {
                    "metric": rule.metric,
                    "value": value,
                    "unit": rule.unit,
                    "currency": "USD" if rule.unit == "currency" else None,
                    "period_label": label,
                    "evidence_quote": quote,
                    "confidence": 0.9,
                }
                if counterparty and rule.metric in _PARTY_METRICS:
                    fact["subject_hint"] = counterparty
                facts.append(fact)
        return facts
