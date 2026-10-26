
"""
SolveEase Broad Discovery Scanner
=================================

Purpose:
    Discover, normalize, deduplicate, rank, and persist public signals
    that may be useful to SolveEase's downstream components.

Design:
    - Modular source adapters
    - RSS/Atom and JSON feed discovery
    - Optional configured seed URLs
    - Persistent SQLite findings and scan history
    - Evidence-aware scoring; no invented leads or demand claims
    - Source health, bounded HTTP requests, and scan summaries
    - No automatic publishing, prospect outreach, or spending

Python: 3.10+
Standard library only.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable


APP_NAME = "SolveEase Broad Discovery Scanner"
SCANNER_VERSION = "2.0.0"

DATABASE_PATH = Path(
    os.getenv("SCANNER_DB_PATH", "solveease_scanner.sqlite3")
)

REQUEST_TIMEOUT = max(2, min(
    int(os.getenv("SCANNER_TIMEOUT_SECONDS", "12")), 30
))
MAX_RESPONSE_BYTES = max(16_384, min(
    int(os.getenv("SCANNER_MAX_RESPONSE_BYTES", "1500000")),
    5_000_000,
))
MAX_ITEMS_PER_SOURCE = max(5, min(
    int(os.getenv("SCANNER_MAX_ITEMS_PER_SOURCE", "100")), 500
))
MAX_SOURCES_PER_RUN = max(1, min(
    int(os.getenv("SCANNER_MAX_SOURCES_PER_RUN", "30")), 200
))
MAX_RUN_SECONDS = max(10, min(
    int(os.getenv("SCANNER_MAX_RUN_SECONDS", "180")), 1800
))
USER_AGENT = "SolveEaseScanner/2.0 (+public-feed discovery)"

# Optional newline-separated public feed URLs.
# Example: SCANNER_FEED_URLS=https://example.org/feed.xml
# Only add sources you are permitted to access.
CONFIGURED_FEEDS = [
    value.strip()
    for value in os.getenv("SCANNER_FEED_URLS", "").splitlines()
    if value.strip()
]

# These are discovery themes, not claims that demand has been proven.
DEFAULT_THEMES: dict[str, list[str]] = {
    "workflow_friction": [
        "manual process", "spreadsheet", "repetitive task",
        "time consuming", "workaround", "duplicate entry",
        "data conversion", "batch processing",
    ],
    "quality_and_reliability": [
        "incorrect output", "inaccurate", "failed export",
        "broken workflow", "missing feature", "formatting issue",
        "inconsistent results", "data validation",
    ],
    "access_and_complexity": [
        "too expensive", "complicated setup", "difficult to use",
        "no free option", "limited access", "time-consuming setup",
    ],
    "commercial_intent": [
        "looking for a tool", "need a solution", "alternative to",
        "recommend a service", "pay for", "business workflow",
        "automation service",
    ],
    "document_and_data_tasks": [
        "convert document", "extract data", "clean csv",
        "format spreadsheet", "merge pdf", "parse invoice",
        "normalize data", "generate report",
    ],
}

# General search/feed discovery terms for sources that accept query parameters.
# These are seeds to discover signals, not pre-approved opportunities.
DEFAULT_SEARCH_TERMS = [
    '"looking for a tool" workflow',
    '"manual process" automation business',
    '"alternative to" spreadsheet workflow',
    '"data conversion" repetitive task',
    '"formatting issue" document tool',
    '"too expensive" software workflow',
    '"missing feature" automation tool',
    '"need a solution" data processing',
]


@dataclass
class Finding:
    title: str
    url: str
    source: str
    summary: str = ""
    published_at: str | None = None
    discovered_at: str = ""
    category: str = "unclassified"
    evidence_type: str = "public_source_record"
    source_verified: bool = False
    evidence_notes: list[str] = field(default_factory=list)
    score: float = 0.0
    finding_id: str = ""
    status: str = "unverified"
    metadata: dict[str, Any] = field(default_factory=dict)

    def prepare(self) -> "Finding":
        self.title = clean_text(self.title)[:500]
        self.summary = clean_text(self.summary)[:4000]
        self.url = normalize_url(self.url)
        self.source = clean_text(self.source)[:300]
        self.discovered_at = self.discovered_at or utc_now()

        if not self.finding_id:
            identity = self.url or (
                self.title.lower() + "|" + self.source.lower()
            )
            self.finding_id = hashlib.sha256(
                identity.encode("utf-8")
            ).hexdigest()[:32]

        self.category = classify_text(
            self.title + " " + self.summary
        )
        self.score = score_finding(self)
        return self


@dataclass
class SourceResult:
    source: str
    status: str
    fetched: int = 0
    stored: int = 0
    duplicates: int = 0
    error: str | None = None
    elapsed_seconds: float = 0.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    value = html.unescape(str(value))
    value = re.sub(r"<[^>]*>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_url(url: str) -> str:
    """Normalize a URL without changing its destination."""
    url = html.unescape((url or "").strip())
    if not url:
        return ""

    try:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme.lower() not in ("http", "https"):
            return ""
        if not parts.hostname:
            return ""

        host = parts.hostname.lower()
        if parts.port:
            default_port = (
                parts.scheme.lower() == "http" and parts.port == 80
            ) or (
                parts.scheme.lower() == "https" and parts.port == 443
            )
            if not default_port:
                host = f"{host}:{parts.port}"

        # Remove common tracking parameters only.
        query_items = urllib.parse.parse_qsl(
            parts.query, keep_blank_values=True
        )
        query_items = [
            (k, v) for k, v in query_items
            if not k.lower().startswith("utm_")
            and k.lower() not in {
                "fbclid", "gclid", "mc_cid", "mc_eid"
            }
        ]
        query = urllib.parse.urlencode(query_items, doseq=True)
        path = parts.path or "/"

        return urllib.parse.urlunsplit((
            parts.scheme.lower(), host, path, query, ""
        ))
    except (ValueError, UnicodeError):
        return ""


def classify_text(text: str) -> str:
    text = text.lower()
    category_hits: dict[str, int] = {}

    for category, terms in DEFAULT_THEMES.items():
        category_hits[category] = sum(
            1 for term in terms if term in text
        )

    best = max(category_hits, key=category_hits.get)
    return best if category_hits[best] else "unclassified"


def score_finding(finding: Finding) -> float:
    """
    Heuristic relevance score from 0 to 100.

    This is NOT a probability of demand, willingness to pay, or success.
    The score prioritizes records for review only.
    """
    text = (finding.title + " " + finding.summary).lower()
    score = 0.0

    category_bonus = {
        "commercial_intent": 25,
        "workflow_friction": 20,
        "quality_and_reliability": 18,
        "document_and_data_tasks": 17,
        "access_and_complexity": 15,
        "unclassified": 0,
    }
    score += category_bonus.get(finding.category, 0)

    explicit_need_terms = (
        "looking for", "need a", "recommend", "alternative to",
        "problem with", "can't", "cannot", "failed", "manual",
        "workaround", "too expensive",
    )
    score += min(
        25, sum(5 for term in explicit_need_terms if term in text)
    )

    repeat_terms = (
        "every day", "daily", "weekly", "recurring", "repeated",
        "every month", "batch", "multiple files",
    )
    score += min(
        15, sum(5 for term in repeat_terms if term in text)
    )

    task_terms = (
        "convert", "extract", "format", "clean", "merge",
        "validate", "generate", "compare", "automate",
    )
    score += min(
        15, sum(3 for term in task_terms if term in text)
    )

    if finding.url:
        score += 5
    if finding.source_verified:
        score += 5

    return round(min(100.0, score), 2)


def open_database(path: Path = DATABASE_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    create_schema(conn)
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS findings (
        finding_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        source TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        published_at TEXT,
        discovered_at TEXT NOT NULL,
        category TEXT NOT NULL,
        evidence_type TEXT NOT NULL,
        source_verified INTEGER NOT NULL DEFAULT 0,
        evidence_notes_json TEXT NOT NULL DEFAULT '[]',
        score REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'unverified',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        seen_count INTEGER NOT NULL DEFAULT 1
    );

    CREATE INDEX IF NOT EXISTS idx_findings_score
        ON findings(score DESC);
    CREATE INDEX IF NOT EXISTS idx_findings_category
        ON findings(category);
    CREATE INDEX IF NOT EXISTS idx_findings_status
        ON findings(status);
    CREATE INDEX IF NOT EXISTS idx_findings_last_seen
        ON findings(last_seen_at DESC);

    CREATE TABLE IF NOT EXISTS scan_runs (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        sources_attempted INTEGER NOT NULL DEFAULT 0,
        records_fetched INTEGER NOT NULL DEFAULT 0,
        records_inserted INTEGER NOT NULL DEFAULT 0,
        duplicates INTEGER NOT NULL DEFAULT 0,
        errors INTEGER NOT NULL DEFAULT 0,
        report_json TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS source_health (
        source TEXT PRIMARY KEY,
        last_attempt_at TEXT,
        last_success_at TEXT,
        last_status TEXT,
        consecutive_failures INTEGER NOT NULL DEFAULT 0,
        total_attempts INTEGER NOT NULL DEFAULT 0,
        total_successes INTEGER NOT NULL DEFAULT 0,
        last_error TEXT
    );

    CREATE TABLE IF NOT EXISTS finding_outcomes (
        outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
        finding_id TEXT NOT NULL,
        outcome TEXT NOT NULL,
        notes TEXT NOT NULL DEFAULT '',
        recorded_at TEXT NOT NULL,
        FOREIGN KEY(finding_id) REFERENCES findings(finding_id)
    );
    """)
    conn.commit()


def fetch_url(url: str) -> tuple[bytes, str]:
    """
    Fetch a public HTTP(S) resource with bounded time and response size.

    Redirects are limited by urllib defaults. The final URL must still be
    HTTP(S); the scanner never executes downloaded content.
    """
    url = normalize_url(url)
    if not url:
        raise ValueError("Invalid HTTP(S) URL")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/rss+xml, application/atom+xml, "
                "application/json, application/xml, text/xml, "
                "text/plain, */*"
            ),
        },
        method="GET",
    )

    with urllib.request.urlopen(
        request, timeout=REQUEST_TIMEOUT
    ) as response:
        final_url = normalize_url(response.geturl())
        if not final_url:
            raise ValueError("Redirect resolved to an invalid URL")

        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError("Response exceeded configured byte limit")

        return data, final_url


def parse_datetime(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def parse_feed(data: bytes, feed_url: str) -> list[Finding]:
    """Parse common RSS 2.0 and Atom feed structures."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Feed XML parse failed: {exc}") from exc

    results: list[Finding] = []
    root_tag = root.tag.rsplit("}", 1)[-1].lower()

    if root_tag == "rss" or root_tag == "rdf":
        items = [
            node for node in root.iter()
            if node.tag.rsplit("}", 1)[-1].lower() == "item"
        ]
        for item in items[:MAX_ITEMS_PER_SOURCE]:
            fields: dict[str, str] = {}
            for child in list(item):
                key = child.tag.rsplit("}", 1)[-1].lower()
                fields.setdefault(key, "".join(child.itertext()).strip())

            link = fields.get("link", "")
            if not link:
                continue
            results.append(Finding(
                title=fields.get("title", "Untitled feed item"),
                url=urllib.parse.urljoin(feed_url, link),
                source=feed_url,
                summary=(
                    fields.get("description")
                    or fields.get("summary")
                    or fields.get("content", "")
                ),
                published_at=parse_datetime(
                    fields.get("pubdate")
                    or fields.get("published")
                    or fields.get("date")
                ),
                source_verified=True,
                evidence_notes=["Retrieved from a public RSS/RDF feed"],
            ))

    else:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//atom:entry", ns)

        # Fallback for Atom documents with alternate namespaces.
        if not entries:
            entries = [
                node for node in root.iter()
                if node.tag.rsplit("}", 1)[-1].lower() == "entry"
            ]

        for entry in entries[:MAX_ITEMS_PER_SOURCE]:
            fields: dict[str, str] = {}
            for child in list(entry):
                key = child.tag.rsplit("}", 1)[-1].lower()
                fields.setdefault(key, "".join(child.itertext()).strip())

            link = ""
            for child in list(entry):
                if child.tag.rsplit("}", 1)[-1].lower() == "link":
                    href = child.attrib.get("href", "")
                    rel = child.attrib.get("rel", "alternate")
                    if href and rel == "alternate":
                        link = href
                        break
                    if href and not link:
                        link = href

            if not link:
                continue

            results.append(Finding(
                title=fields.get("title", "Untitled feed entry"),
                url=urllib.parse.urljoin(feed_url, link),
                source=feed_url,
                summary=fields.get("summary", fields.get("content", "")),
                published_at=parse_datetime(
                    fields.get("published")
                    or fields.get("updated")
                ),
                source_verified=True,
                evidence_notes=["Retrieved from a public Atom feed"],
            ))

    return results


def parse_json_feed(data: bytes, feed_url: str) -> list[Finding]:
    """Parse a small generic JSON feed when its schema is recognizable."""
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON parse failed: {exc}") from exc

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = None
        for key in ("items", "results", "entries", "data", "records"):
            if isinstance(payload.get(key), list):
                items = payload[key]
                break
        if items is None:
            raise ValueError("JSON response has no recognized item list")
    else:
        raise ValueError("Unsupported JSON feed shape")

    results: list[Finding] = []
    for item in items[:MAX_ITEMS_PER_SOURCE]:
        if not isinstance(item, dict):
            continue

        title = (
            item.get("title") or item.get("name")
            or item.get("headline") or ""
        )
        raw_url = (
            item.get("url") or item.get("link")
            or item.get("html_url") or item.get("web_url") or ""
        )
        if not title or not raw_url:
            continue

        results.append(Finding(
            title=str(title),
            url=urllib.parse.urljoin(feed_url, str(raw_url)),
            source=feed_url,
            summary=str(
                item.get("summary") or item.get("description")
                or item.get("body") or item.get("content") or ""
            ),
            published_at=parse_datetime(
                str(item.get("published_at") or item.get("date") or "")
            ),
            source_verified=True,
            evidence_notes=["Retrieved from a configured public JSON feed"],
        ))

    return results


def configured_sources() -> list[str]:
    """Return unique configured feed URLs in stable order."""
    seen: set[str] = set()
    sources: list[str] = []

    for url in CONFIGURED_FEEDS:
        normalized = normalize_url(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            sources.append(normalized)

    return sources[:MAX_SOURCES_PER_RUN]


def save_finding(
    conn: sqlite3.Connection, finding: Finding
) -> tuple[bool, bool]:
    """
    Persist a finding.

    Returns (inserted, duplicate).
    Duplicate observations update last_seen_at and seen_count.
    """
    finding.prepare()
    if not finding.url or not finding.title:
        return False, False

    now = utc_now()
    existing = conn.execute(
        "SELECT finding_id FROM findings WHERE finding_id = ?",
        (finding.finding_id,),
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE findings
            SET last_seen_at = ?, seen_count = seen_count + 1,
                score = MAX(score, ?),
                source_verified = MAX(source_verified, ?)
            WHERE finding_id = ?
        """, (
            now, finding.score, int(finding.source_verified),
            finding.finding_id,
        ))
        return False, True

    conn.execute("""
        INSERT INTO findings (
            finding_id, title, url, source, summary, published_at,
            discovered_at, category, evidence_type, source_verified,
            evidence_notes_json, score, status, metadata_json,
            first_seen_at, last_seen_at, seen_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        finding.finding_id,
        finding.title,
        finding.url,
        finding.source,
        finding.summary,
        finding.published_at,
        finding.discovered_at,
        finding.category,
        finding.evidence_type,
        int(finding.source_verified),
        json.dumps(finding.evidence_notes, ensure_ascii=False),
        finding.score,
        finding.status,
        json.dumps(finding.metadata, ensure_ascii=False),
        now,
        now,
    ))
    return True, False


def update_source_health(
    conn: sqlite3.Connection,
    source: str,
    success: bool,
    error: str | None = None,
) -> None:
    now = utc_now()
    conn.execute("""
        INSERT INTO source_health (
            source, last_attempt_at, last_success_at, last_status,
            consecutive_failures, total_attempts, total_successes,
            last_error
        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(source) DO UPDATE SET
            last_attempt_at = excluded.last_attempt_at,
            last_success_at = CASE
                WHEN excluded.last_status = 'success'
                THEN excluded.last_success_at
                ELSE source_health.last_success_at
            END,
            last_status = excluded.last_status,
            consecutive_failures = CASE
                WHEN excluded.last_status = 'success' THEN 0
                ELSE source_health.consecutive_failures + 1
            END,
            total_attempts = source_health.total_attempts + 1,
            total_successes = source_health.total_successes
                + excluded.total_successes,
            last_error = excluded.last_error
    """, (
        source, now, now if success else None,
        "success" if success else "error",
        0 if success else 1,
        1 if success else 0,
        (error or "")[:1000] if not success else None,
    ))


def scan_feed(source: str) -> tuple[list[Finding], str]:
    data, final_url = fetch_url(source)
    content_type = ""

    # Prefer XML parsing first, then JSON.
    try:
        findings = parse_feed(data, final_url)
        if findings:
            return findings, final_url
    except ValueError:
        pass

    try:
        findings = parse_json_feed(data, final_url)
        return findings, final_url
    except ValueError as exc:
        raise ValueError(
            f"Source is not a supported RSS/Atom/JSON feed: {exc}"
        ) from exc


def run_scan(
    sources: Iterable[str] | None = None,
    db_path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    """
    Run one bounded scan across configured sources.

    No fixed fake findings are inserted. If no feeds are configured,
    the scanner reports that discovery has no sources rather than
    pretending it found opportunities.
    """
    started = utc_now()
    started_clock = time.monotonic()
    source_list = list(sources) if sources is not None else configured_sources()

    unique_sources: list[str] = []
    seen: set[str] = set()
    for source in source_list:
        normalized = normalize_url(source)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_sources.append(normalized)

    unique_sources = unique_sources[:MAX_SOURCES_PER_RUN]

    conn = open_database(db_path)
    cursor = conn.execute("""
        INSERT INTO scan_runs (started_at, status)
        VALUES (?, 'running')
    """, (started,))
    run_id = cursor.lastrowid
    conn.commit()

    source_reports: list[dict[str, Any]] = []
    total_fetched = 0
    total_inserted = 0
    total_duplicates = 0
    total_errors = 0

    try:
        for source in unique_sources:
            if time.monotonic() - started_clock >= MAX_RUN_SECONDS:
                source_reports.append(asdict(SourceResult(
                    source=source,
                    status="skipped_run_time_limit",
                )))
                continue

            source_start = time.monotonic()
            try:
                findings, resolved_source = scan_feed(source)
                inserted = duplicates = 0

                for finding in findings[:MAX_ITEMS_PER_SOURCE]:
                    # Keep the actual item URL but retain the feed as
                    # the source of the observation.
                    finding.source = resolved_source
                    was_inserted, was_duplicate = save_finding(conn, finding)
                    inserted += int(was_inserted)
                    duplicates += int(was_duplicate)

                conn.commit()
                update_source_health(conn, source, True)
                conn.commit()

                result = SourceResult(
                    source=source,
                    status="success",
                    fetched=len(findings),
                    stored=inserted,
                    duplicates=duplicates,
                    elapsed_seconds=round(
                        time.monotonic() - source_start, 3
                    ),
                )

            except Exception as exc:
                conn.rollback()
                update_source_health(
                    conn, source, False,
                    f"{type(exc).__name__}: {exc}",
                )
                conn.commit()
                total_errors += 1

                result = SourceResult(
                    source=source,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}"[:1000],
                    elapsed_seconds=round(
                        time.monotonic() - source_start, 3
                    ),
                )

            source_reports.append(asdict(result))
            total_fetched += result.fetched
            total_inserted += result.stored
            total_duplicates += result.duplicates

        finished = utc_now()
        status = (
            "complete" if total_errors == 0
            else "partial" if total_inserted or total_fetched
            else "failed"
        )

        report = {
            "application": APP_NAME,
            "version": SCANNER_VERSION,
            "run_id": run_id,
            "started_at": started,
            "finished_at": finished,
            "status": status,
            "sources_configured": len(unique_sources),
            "records_fetched": total_fetched,
            "new_findings": total_inserted,
            "duplicates": total_duplicates,
            "source_errors": total_errors,
            "elapsed_seconds": round(
                time.monotonic() - started_clock, 3
            ),
            "important_note": (
                "A finding is a public-source observation, not proof "
                "of buyer demand, willingness to pay, or revenue."
            ),
            "sources": source_reports,
            "top_findings": top_findings(conn, limit=20),
        }

        conn.execute("""
            UPDATE scan_runs SET
                finished_at = ?, status = ?, sources_attempted = ?,
                records_fetched = ?, records_inserted = ?,
                duplicates = ?, errors = ?, report_json = ?
            WHERE run_id = ?
        """, (
            finished, status, len(unique_sources),
            total_fetched, total_inserted, total_duplicates,
            total_errors, json.dumps(report, ensure_ascii=False),
            run_id,
        ))
        conn.commit()
        return report

    finally:
        conn.close()


def top_findings(
    conn: sqlite3.Connection, limit: int = 20
) -> list[dict[str, Any]]:
    rows = conn.execute("""
        SELECT finding_id, title, url, source, summary, published_at,
               discovered_at, category, source_verified, score, status,
               first_seen_at, last_seen_at, seen_count
        FROM findings
        ORDER BY score DESC, last_seen_at DESC
        LIMIT ?
    """, (max(1, min(limit, 100)),)).fetchall()

    return [dict(row) for row in rows]


def record_outcome(
    finding_id: str, outcome: str, notes: str = "",
    db_path: Path = DATABASE_PATH,
) -> bool:
    """
    Record a downstream outcome to support later learning.

    Examples:
        reviewed, rejected, validated, tool_built, task_completed,
        buyer_confirmed, revenue_confirmed

    This records what the caller says happened; it does not verify
    the claim independently.
    """
    allowed = {
        "reviewed", "rejected", "validated", "tool_built",
        "task_completed", "buyer_confirmed", "revenue_confirmed",
        "needs_more_evidence",
    }
    if outcome not in allowed:
        raise ValueError(f"Unsupported outcome: {outcome}")

    conn = open_database(db_path)
    try:
        exists = conn.execute(
            "SELECT 1 FROM findings WHERE finding_id = ?",
            (finding_id,),
        ).fetchone()
        if not exists:
            return False

        conn.execute("""
            INSERT INTO finding_outcomes (
                finding_id, outcome, notes, recorded_at
            ) VALUES (?, ?, ?, ?)
        """, (finding_id, outcome, notes[:4000], utc_now()))

        status = {
            "rejected": "rejected",
            "validated": "validated",
            "needs_more_evidence": "unverified",
            "buyer_confirmed": "buyer_confirmed",
            "revenue_confirmed": "revenue_confirmed",
        }.get(outcome)

        if status:
            conn.execute(
                "UPDATE findings SET status = ? WHERE finding_id = ?",
                (status, finding_id),
            )

        conn.commit()
        return True
    finally:
        conn.close()


def scanner_status(
    db_path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    conn = open_database(db_path)
    try:
        counts = conn.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'unverified' THEN 1 ELSE 0 END)
                       AS unverified,
                   SUM(CASE WHEN status = 'validated' THEN 1 ELSE 0 END)
                       AS validated,
                   SUM(CASE WHEN status = 'buyer_confirmed' THEN 1 ELSE 0 END)
                       AS buyer_confirmed,
                   SUM(CASE WHEN status = 'revenue_confirmed' THEN 1 ELSE 0 END)
                       AS revenue_confirmed
            FROM findings
        """).fetchone()

        sources = conn.execute("""
            SELECT source, last_attempt_at, last_success_at, last_status,
                   consecutive_failures, total_attempts, total_successes,
                   last_error
            FROM source_health
            ORDER BY source
        """).fetchall()

        last_run = conn.execute("""
            SELECT run_id, started_at, finished_at, status,
                   sources_attempted, records_fetched, records_inserted,
                   duplicates, errors
            FROM scan_runs ORDER BY run_id DESC LIMIT 1
        """).fetchone()

        return {
            "application": APP_NAME,
            "version": SCANNER_VERSION,
            "database": str(db_path),
            "finding_counts": dict(counts) if counts else {},
            "source_health": [dict(row) for row in sources],
            "last_run": dict(last_run) if last_run else None,
        }
    finally:
        conn.close()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="SolveEase modular public-source discovery scanner"
    )
    parser.add_argument(
        "--db", default=str(DATABASE_PATH),
        help="SQLite database path",
    )
    parser.add_argument(
        "--source", action="append", default=[],
        help="Feed URL to scan; repeat for multiple sources",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Print database and source health summary",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print machine-readable JSON",
    )
    args = parser.parse_args()

    db_path = Path(args.db)

    if args.status:
        result = scanner_status(db_path)
    else:
        chosen_sources = args.source or None
        result = run_scan(chosen_sources, db_path)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") not in {"failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
