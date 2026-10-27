
"""
SolveEase Micro-Utility Engine — Scanner v4.0.0

Purpose:
- Discover recurring public task needs across broad opportunity domains.
- Rank findings by discovery priority.
- Calculate a separate evidence-aware value-to-money score.
- Preserve unknown commercial facts instead of inventing them.
- Store findings and scan history in SQLite.

Free/public sources:
- Configured RSS, Atom and JSON feeds
- Hacker News Algolia API
- Stack Exchange API
- GitHub Search API

Environment variables:
  SCANNER_DB_PATH              Optional DB path; DB_PATH is fallback
  SCANNER_FEED_URLS            Semicolon-separated HTTPS feed URLs
  SCANNER_ENABLE_STACKEXCHANGE true/false (default true)
  SCANNER_ENABLE_GITHUB        true/false (default true)
  SCANNER_MAX_ITEMS_PER_SOURCE Max results/source (default 50)
  SCANNER_TIMEOUT              Request timeout seconds (default 15)
  SCANNER_USER_AGENT           Optional user agent

Scores are prioritization heuristics, not proof of revenue or ROI.
"""

from __future__ import annotations

import datetime as dt
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
from typing import Any, Optional


VERSION = "4.0.0"
DEFAULT_DB_PATH = os.getenv(
    "SCANNER_DB_PATH",
    os.getenv("DB_PATH", "data/solveease.sqlite3"),
)
REQUEST_TIMEOUT = max(3, int(os.getenv("SCANNER_TIMEOUT", "15")))
MAX_ITEMS = max(5, min(100, int(os.getenv("SCANNER_MAX_ITEMS_PER_SOURCE", "50"))))
USER_AGENT = os.getenv(
    "SCANNER_USER_AGENT",
    "SolveEase-MicroUtilityScanner/4.0 (+public research; contact: solveease.leads@gmail.com)",
)

ENABLE_STACKEXCHANGE = (
    os.getenv("SCANNER_ENABLE_STACKEXCHANGE", "true").lower() not in
    {"0", "false", "no", "off"}
)
ENABLE_GITHUB = (
    os.getenv("SCANNER_ENABLE_GITHUB", "true").lower() not in
    {"0", "false", "no", "off"}
)

# Broad discovery categories. These are discovery labels, not approved niches.
DOMAINS = {
    "data_documents": [
        "spreadsheet", "csv", "xlsx", "excel", "pdf", "document",
        "file conversion", "duplicate rows", "data cleaning",
        "formatting", "data extraction", "ocr", "merge files",
        "split files", "bulk rename",
    ],
    "ecommerce_online_selling": [
        "shopify", "woocommerce", "product feed", "product listing",
        "catalog", "inventory", "sku", "marketplace", "product import",
        "product export", "merchant center", "listing error",
    ],
    "seo_web_marketing": [
        "seo", "search console", "metadata", "meta description",
        "structured data", "schema markup", "redirect", "sitemap",
        "broken link", "keyword mapping", "website audit",
        "accessibility", "page speed",
    ],
    "business_operations_automation": [
        "workflow", "automation", "manual process", "repetitive task",
        "zapier", "make.com", "n8n", "integration", "report generation",
        "reconciliation", "form processing", "copy and paste",
    ],
    "software_api_troubleshooting": [
        "api", "webhook", "integration error", "bug", "exception",
        "deployment", "configuration", "migration", "python",
        "authentication error", "rate limit", "debugging",
    ],
    "finance_commerce_admin": [
        "invoice", "expense", "bookkeeping", "payment reconciliation",
        "transaction export", "financial report", "receipt",
        "billing", "accounting spreadsheet",
    ],
    "scheduling_productivity": [
        "calendar", "scheduling", "reminder", "task management",
        "recurring report", "time tracking", "appointment",
        "availability", "workflow coordination",
    ],
    "education_career": [
        "resume", "cv formatting", "job application", "job listing",
        "study materials", "course notes", "document formatting",
        "academic references", "learning materials",
    ],
    "content_creator_workflows": [
        "social media", "caption", "content repurposing",
        "publishing workflow", "creator", "transcription",
        "subtitle", "video metadata", "content calendar",
    ],
    "digital_asset_management": [
        "file organization", "image resizing", "image conversion",
        "metadata cleanup", "digital assets", "document indexing",
        "file naming", "cloud storage", "bulk image",
    ],
    "customer_service_reputation": [
        "support ticket", "customer support", "review response",
        "customer feedback", "sentiment analysis", "help desk",
        "ticket classification", "customer data",
    ],
    "research_information_discovery": [
        "research", "public data", "monitoring", "comparison report",
        "opportunity discovery", "information extraction",
        "data aggregation", "price monitoring", "tender",
        "grant", "public records",
    ],
    "other_or_unclassified": [],
}

# These signals indicate a task or friction, not necessarily a paying customer.
DEMAND_TERMS = [
    "need help", "looking for", "can someone", "anyone know",
    "how do i", "how can i", "recommend a tool", "is there a tool",
    "need a way", "trying to", "want to automate", "help me",
    "looking for someone", "looking for a tool", "hire someone",
]

PAIN_TERMS = [
    "problem", "issue", "broken", "fails", "failed", "error",
    "frustrating", "painful", "difficult", "hard to", "can't",
    "cannot", "unable to", "doesn't work", "does not work",
    "time-consuming", "tedious", "repetitive", "manual",
    "workaround", "inaccurate", "unreliable", "missing feature",
    "poor results", "bad output", "waste of time", "too complex",
]

WORKAROUND_TERMS = [
    "manually", "copy and paste", "spreadsheet workaround",
    "work around", "workaround", "every week", "every day",
    "each month", "over and over", "repeat this", "multiple tools",
    "switch between", "export then import", "doing this by hand",
]

COMMERCIAL_TERMS = [
    "paid", "payment", "budget", "price", "pricing", "cost",
    "hire", "hiring", "freelancer", "contract", "contractor",
    "client", "customer", "order", "project", "fixed price",
    "per task", "per month", "subscription", "invoice",
    "job posting", "gig", "service listing",
]

PAYMENT_EVIDENCE_TERMS = [
    "paid for", "we paid", "payment received", "completed order",
    "paid order", "purchased", "purchase confirmed",
    "contract awarded", "invoice paid",
]

SELLER_TERMS = [
    "i offer", "we offer", "my service", "our service",
    "freelance service", "available for hire", "service listing",
    "fixed-price service", "fixed price", "gig",
]

FAILED_WORKFLOW_TERMS = [
    "doesn't work", "does not work", "failed", "failure",
    "broken", "incorrect output", "wrong output", "bad preview",
    "poor preview", "rejected", "unresolved", "still not working",
]

# Relevance searches are deliberately broad and are not proof of demand.
HACKER_NEWS_QUERIES = [
    '"need help" automation',
    '"manual" workflow tool',
    '"looking for" tool repetitive',
    '"does not work" integration',
    '"time-consuming" spreadsheet',
    '"alternative to" workflow',
    '"how do I" data cleaning',
    '"frustrating" API',
]

STACKEXCHANGE_SITES = [
    "stackoverflow",
    "webapps",
    "superuser",
    "serverfault",
    "wordpress",
]

GITHUB_QUERIES = [
    '"bug" "workflow" is:issue is:open',
    '"feature request" automation is:issue is:open',
    '"does not work" integration is:issue is:open',
    '"incorrect output" is:issue is:open',
]

# Default weights for transparent discovery prioritization.
DISCOVERY_WEIGHTS = {
    "task_clarity": 20,
    "pain_signal": 15,
    "recurrence_signal": 15,
    "commercial_signal": 15,
    "workaround_signal": 10,
    "failure_signal": 10,
    "freshness": 10,
    "source_completeness": 5,
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def clean_text(value: Any) -> str:
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_date(value: Any) -> Optional[str]:
    if not value:
        return None
    try:
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def age_days(date_string: Optional[str]) -> Optional[float]:
    parsed = normalize_date(date_string)
    if not parsed:
        return None
    try:
        value = dt.datetime.fromisoformat(parsed)
        return max(0.0, (dt.datetime.now(dt.timezone.utc) - value).total_seconds() / 86400)
    except ValueError:
        return None


def matching_terms(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


def stable_id(source: str, url: str, title: str) -> str:
    identity = (source + "|" + (url or "") + "|" + (title or "")).encode("utf-8")
    return hashlib.sha256(identity).hexdigest()[:32]


def connect_db() -> sqlite3.Connection:
    if DEFAULT_DB_PATH != ":memory:":
        parent = os.path.dirname(os.path.abspath(DEFAULT_DB_PATH))
        os.makedirs(parent, exist_ok=True)
    connection = sqlite3.connect(DEFAULT_DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _ensure_columns(
    connection: sqlite3.Connection,
    table: str,
    definitions: dict[str, str],
) -> None:
    present = _columns(connection, table)
    for name, definition in definitions.items():
        if name not in present:
            connection.execute(
                f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'
            )


def init_db() -> None:
    with connect_db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS findings (
                id TEXT PRIMARY KEY,
                source TEXT,
                source_id TEXT,
                url TEXT,
                title TEXT,
                text TEXT,
                domain TEXT,
                score INTEGER DEFAULT 0,
                commercial_intent TEXT,
                created_at TEXT,
                discovered_at TEXT,
                raw_json TEXT
            )
        """)
        # Migrate older scanner tables without dropping existing data.
        _ensure_columns(connection, "findings", {
            "id": "TEXT",
            "source": "TEXT",
            "source_id": "TEXT",
            "url": "TEXT",
            "title": "TEXT",
            "text": "TEXT",
            "domain": "TEXT",
            "score": "INTEGER DEFAULT 0",
            "commercial_intent": "TEXT",
            "created_at": "TEXT",
            "discovered_at": "TEXT",
            "raw_json": "TEXT",
            "discovery_score": "INTEGER DEFAULT 0",
            "value_to_money_score": "INTEGER",
            "value_status": "TEXT",
            "evidence_json": "TEXT",
            "signals_json": "TEXT",
        })
        connection.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_id
            ON findings(id)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_findings_discovery
            ON findings(discovery_score)
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS source_health (
                source TEXT PRIMARY KEY,
                last_checked TEXT,
                status TEXT,
                item_count INTEGER DEFAULT 0,
                error TEXT
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS scan_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                status TEXT,
                item_count INTEGER DEFAULT 0,
                source_count INTEGER DEFAULT 0,
                error TEXT,
                summary_json TEXT
            )
        """)
        _ensure_columns(connection, "scan_runs", {
            "started_at": "TEXT",
            "finished_at": "TEXT",
            "status": "TEXT",
            "item_count": "INTEGER DEFAULT 0",
            "source_count": "INTEGER DEFAULT 0",
            "error": "TEXT",
            "summary_json": "TEXT",
        })
        connection.execute("""
            CREATE TABLE IF NOT EXISTS finding_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                finding_id TEXT,
                outcome TEXT,
                notes TEXT,
                created_at TEXT
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_outcomes_finding
            ON finding_outcomes(finding_id)
        """)


def fetch_url(
    url: str,
    headers: Optional[dict[str, str]] = None,
) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Only HTTPS sources are allowed")
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, application/atom+xml, application/rss+xml, application/xml, text/xml, */*",
    }
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return response.read(5_000_000)


def make_item(
    source: str,
    title: str,
    text: str,
    url: str,
    created_at: Optional[str] = None,
    source_id: Optional[str] = None,
    raw: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    title = clean_text(title)[:500]
    text = clean_text(text)[:12000]
    url = str(url or "").strip()
    return {
        "id": stable_id(source, url, title),
        "source": source,
        "source_id": str(source_id or ""),
        "url": url,
        "title": title,
        "text": text,
        "created_at": normalize_date(created_at),
        "raw": raw or {},
    }


def parse_feed(data: bytes, source: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        # Some public endpoints provide JSON despite a feed-like URL.
        try:
            payload = json.loads(data.decode("utf-8", errors="replace"))
            entries = payload if isinstance(payload, list) else payload.get("items", [])
            for entry in entries[:MAX_ITEMS]:
                if not isinstance(entry, dict):
                    continue
                items.append(make_item(
                    source=source,
                    title=entry.get("title", ""),
                    text=entry.get("summary", entry.get("description", entry.get("content", ""))),
                    url=entry.get("url", entry.get("link", "")),
                    created_at=entry.get("published", entry.get("date", entry.get("published_at"))),
                    source_id=entry.get("id"),
                    raw=entry,
                ))
        except (ValueError, TypeError, AttributeError):
            return []
        return items

    for node in root.iter():
        tag = node.tag.lower().split("}")[-1]
        if tag not in {"item", "entry"}:
            continue

        fields: dict[str, str] = {}
        links: list[str] = []
        for child in list(node):
            child_tag = child.tag.lower().split("}")[-1]
            if child_tag == "link":
                href = child.attrib.get("href")
                if href:
                    links.append(href)
                elif child.text:
                    links.append(child.text.strip())
            elif child.text:
                fields[child_tag] = child.text.strip()

        title = fields.get("title", "")
        description = (
            fields.get("description")
            or fields.get("summary")
            or fields.get("content")
            or fields.get("encoded")
            or ""
        )
        link = links[0] if links else fields.get("link", "")
        created = (
            fields.get("published")
            or fields.get("updated")
            or fields.get("pubdate")
            or fields.get("date")
        )
        if title or description:
            items.append(make_item(
                source, title, description, link, created,
                fields.get("id") or fields.get("guid"),
                {"feed_fields": fields},
            ))
        if len(items) >= MAX_ITEMS:
            break
    return items


def collect_configured_feeds() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    all_items: list[dict[str, Any]] = []
    health: dict[str, dict[str, Any]] = {}
    urls = [
        u.strip() for u in os.getenv("SCANNER_FEED_URLS", "").split(";")
        if u.strip()
    ]
    for url in urls:
        source = "feed:" + urllib.parse.urlparse(url).netloc
        try:
            data = fetch_url(url)
            items = parse_feed(data, source)
            all_items.extend(items)
            health[source] = {"status": "ok", "count": len(items), "error": None}
        except Exception as exc:
            health[source] = {"status": "error", "count": 0, "error": str(exc)[:500]}
    return all_items, health


def collect_hacker_news() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results: list[dict[str, Any]] = []
    errors = []
    for query in HACKER_NEWS_QUERIES:
        url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode({
            "query": query,
            "tags": "story,comment",
            "hitsPerPage": min(MAX_ITEMS, 25),
        })
        try:
            payload = json.loads(fetch_url(url).decode("utf-8"))
            for hit in payload.get("hits", []):
                title = hit.get("title") or hit.get("story_title") or ""
                text = hit.get("comment_text") or hit.get("story_text") or title
                object_id = hit.get("objectID", "")
                item_url = hit.get("url") or (
                    "https://news.ycombinator.com/item?id=" + str(object_id)
                )
                created = hit.get("created_at")
                results.append(make_item(
                    "hackernews", title, text, item_url, created,
                    object_id, hit,
                ))
        except Exception as exc:
            errors.append(str(exc)[:250])

    unique = {item["id"]: item for item in results}
    items = list(unique.values())[:MAX_ITEMS]
    return items, {
        "status": "ok" if items else ("error" if errors else "empty"),
        "count": len(items),
        "error": "; ".join(errors[:3]) or None,
    }


def collect_stack_exchange() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not ENABLE_STACKEXCHANGE:
        return [], {"status": "disabled", "count": 0, "error": None}

    results: list[dict[str, Any]] = []
    errors = []
    queries = ["automation", "spreadsheet", "api error", "data cleaning"]
    for site in STACKEXCHANGE_SITES:
        for query in queries:
            url = "https://api.stackexchange.com/2.3/search/advanced?" + urllib.parse.urlencode({
                "site": site,
                "q": query,
                "sort": "creation",
                "order": "desc",
                "pagesize": min(MAX_ITEMS, 20),
                "filter": "withbody",
            })
            try:
                payload = json.loads(fetch_url(url).decode("utf-8"))
                for post in payload.get("items", []):
                    results.append(make_item(
                        "stackexchange:" + site,
                        post.get("title", ""),
                        post.get("body", ""),
                        post.get("link", ""),
                        dt.datetime.fromtimestamp(
                            post.get("creation_date", 0),
                            tz=dt.timezone.utc,
                        ).isoformat() if post.get("creation_date") else None,
                        post.get("question_id"),
                        post,
                    ))
                time.sleep(0.15)
            except Exception as exc:
                errors.append(f"{site}/{query}: {str(exc)[:120]}")

    unique = {item["id"]: item for item in results}
    items = list(unique.values())[:MAX_ITEMS]
    return items, {
        "status": "ok" if items else ("error" if errors else "empty"),
        "count": len(items),
        "error": "; ".join(errors[:3]) or None,
    }


def collect_github_issues() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not ENABLE_GITHUB:
        return [], {"status": "disabled", "count": 0, "error": None}

    results: list[dict[str, Any]] = []
    errors = []
    for query in GITHUB_QUERIES:
        url = "https://api.github.com/search/issues?" + urllib.parse.urlencode({
            "q": query,
            "sort": "created",
            "order": "desc",
            "per_page": min(MAX_ITEMS, 25),
        })
        try:
            payload = json.loads(fetch_url(url).decode("utf-8"))
            for issue in payload.get("items", []):
                body = issue.get("body") or ""
                labels = [
                    label.get("name", "")
                    for label in issue.get("labels", [])
                    if isinstance(label, dict)
                ]
                results.append(make_item(
                    "github",
                    issue.get("title", ""),
                    body + " Labels: " + ", ".join(labels),
                    issue.get("html_url", ""),
                    issue.get("created_at"),
                    issue.get("id"),
                    issue,
                ))
            time.sleep(0.2)
        except Exception as exc:
            errors.append(str(exc)[:250])

    unique = {item["id"]: item for item in results}
    items = list(unique.values())[:MAX_ITEMS]
    return items, {
        "status": "ok" if items else ("error" if errors else "empty"),
        "count": len(items),
        "error": "; ".join(errors[:3]) or None,
    }


def classify_domain(text: str) -> tuple[str, list[str]]:
    lowered = text.lower()
    matches: list[tuple[int, str, list[str]]] = []
    for domain, terms in DOMAINS.items():
        hits = matching_terms(lowered, terms)
        if hits:
            matches.append((len(hits), domain, hits))
    if not matches:
        return "other_or_unclassified", []
    matches.sort(key=lambda row: (-row[0], row[1]))
    return matches[0][1], matches[0][2]


def commercial_intent(text: str) -> str:
    lowered = text.lower()
    commercial = matching_terms(lowered, COMMERCIAL_TERMS)
    if matching_terms(lowered, PAYMENT_EVIDENCE_TERMS):
        return "payment_language_unverified"
    if commercial:
        return "commercial_language_unverified"
    if matching_terms(lowered, DEMAND_TERMS):
        return "demand_language_unverified"
    return "not_detected"


def discovery_analysis(item: dict[str, Any]) -> dict[str, Any]:
    title = clean_text(item.get("title", ""))
    body = clean_text(item.get("text", ""))
    combined = (title + " " + body).lower()
    domain, domain_hits = classify_domain(combined)

    demand = matching_terms(combined, DEMAND_TERMS)
    pain = matching_terms(combined, PAIN_TERMS)
    workaround = matching_terms(combined, WORKAROUND_TERMS)
    commercial = matching_terms(combined, COMMERCIAL_TERMS)
    payment_terms = matching_terms(combined, PAYMENT_EVIDENCE_TERMS)
    seller = matching_terms(combined, SELLER_TERMS)
    failure = matching_terms(combined, FAILED_WORKFLOW_TERMS)

    recurrence_terms = [
        "daily", "every day", "weekly", "every week", "monthly",
        "every month", "recurring", "repeat", "repeatedly",
        "bulk", "multiple times", "ongoing", "regularly",
    ]
    recurrence = matching_terms(combined, recurrence_terms)

    age = age_days(item.get("created_at"))
    freshness = 0
    if age is not None:
        if age <= 7:
            freshness = 10
        elif age <= 30:
            freshness = 7
        elif age <= 90:
            freshness = 4
        elif age <= 180:
            freshness = 2

    # Independent score components. Counts are capped to avoid keyword stuffing.
    components = {
        "task_clarity": min(20, 8 * bool(title) + 4 * bool(body) + 4 * bool(domain_hits) + 4 * bool(demand)),
        "pain_signal": min(15, len(pain) * 5),
        "recurrence_signal": min(15, len(recurrence) * 5),
        "commercial_signal": min(15, len(commercial) * 5),
        "workaround_signal": min(10, len(workaround) * 5),
        "failure_signal": min(10, len(failure) * 5),
        "freshness": freshness,
        "source_completeness": 5 if item.get("url") and title and body else (
            3 if item.get("url") and title else 0
        ),
    }

    discovery_score = min(100, sum(components.values()))

    evidence = {
        "public_task_request_detected": bool(demand),
        "pain_language_detected": bool(pain),
        "recurrence_language_detected": bool(recurrence),
        "commercial_language_detected": bool(commercial),
        "payment_language_detected_unverified": bool(payment_terms),
        "seller_language_detected_unverified": bool(seller),
        "workflow_failure_detected": bool(failure),
        "workaround_detected": bool(workaround),
        "independent_buyers_verified": None,
        "independent_sellers_verified": None,
        "completed_payments_verified": None,
        "exact_buyer_seller_task_alignment_verified": None,
        "competitor_gap_verified": None,
        "willingness_to_pay_verified": None,
        "delivery_cost_verified": None,
        "acquisition_cost_verified": None,
    }

    signals = {
        "demand_terms": demand,
        "pain_terms": pain,
        "workaround_terms": workaround,
        "commercial_terms": commercial,
        "payment_terms_unverified": payment_terms,
        "seller_terms_unverified": seller,
        "failure_terms": failure,
        "recurrence_terms": recurrence,
        "domain_terms": domain_hits,
        "components": components,
    }

    return {
        "domain": domain,
        "discovery_score": int(discovery_score),
        "commercial_intent": commercial_intent(combined),
        "evidence": evidence,
        "signals": signals,
    }


def value_to_money_analysis(
    analysis: dict[str, Any],
    observed_data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Compute an evidence-aware opportunity score.

    observed_data may contain independently verified, documented values:
      payment_verified: bool
      repeated_paid_demand_verified: bool
      independent_buyers_verified: bool
      independent_sellers_verified: bool
      exact_task_alignment_verified: bool
      competitor_gap_verified: bool
      measurable_output_verified: bool
      automation_feasibility_verified: bool
      legal_data_access_verified: bool
      acquisition_path_verified: bool
      unit_economics_verified: bool
      net_value_per_task: number
      buyer_value_per_task: number
      delivery_cost_per_task: number
      acquisition_cost_per_customer: number

    Scanner text alone cannot establish these facts. Do not populate
    observed_data from keyword matches alone.
    """
    data = observed_data or {}
    evidence = dict(analysis.get("evidence", {}))
    evidence.update({
        key: data[key]
        for key in data
        if key in evidence
    })

    required_checks = [
        "payment_verified",
        "repeated_paid_demand_verified",
        "independent_buyers_verified",
        "independent_sellers_verified",
        "exact_task_alignment_verified",
        "competitor_gap_verified",
        "measurable_output_verified",
        "automation_feasibility_verified",
        "legal_data_access_verified",
        "acquisition_path_verified",
        "unit_economics_verified",
    ]

    # These fields must be independently reviewed, not inferred from text.
    checks = {key: data.get(key) for key in required_checks}
    verified_count = sum(value is True for value in checks.values())
    unknown_count = sum(value is None for value in checks.values())
    failed_count = sum(value is False for value in checks.values())

    net_value = data.get("net_value_per_task")
    buyer_value = data.get("buyer_value_per_task")
    delivery_cost = data.get("delivery_cost_per_task")
    acquisition_cost = data.get("acquisition_cost_per_customer")

    numeric_values_valid = all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and value >= 0
        for value in (buyer_value, delivery_cost, acquisition_cost)
    )

    if numeric_values_valid:
        computed_net = float(buyer_value) - float(delivery_cost)
        # Acquisition cost is per customer, not necessarily per task.
        # Do not subtract it without a documented number of tasks per customer.
        if net_value is None:
            net_value = computed_net

    complete = all(value is True for value in checks.values())
    if failed_count:
        status = "BLOCKED_BY_FAILED_GATE"
    elif complete and isinstance(net_value, (int, float)):
        status = "EVIDENCE_REVIEW_REQUIRED"
    else:
        status = "INVESTIGATE"

    # Never produce a value-to-money score from text-only evidence.
    # A score is available only after all mandatory checks and net value
    # have been independently supplied and reviewed.
    score = None
    if complete and isinstance(net_value, (int, float)):
        # Net value must be positive; map the documented amount to 0–100.
        # This is a transparent value scale, not a probability or ROI forecast.
        score = max(0, min(100, round(100 * float(net_value) / (float(net_value) + 5))))
        if float(net_value) <= 0:
            score = 0

    return {
        "value_to_money_score": score,
        "value_status": status,
        "verified_gate_count": verified_count,
        "unknown_gate_count": unknown_count,
        "failed_gate_count": failed_count,
        "gate_checks": checks,
        "net_value_per_task": net_value,
        "buyer_value_per_task": buyer_value,
        "delivery_cost_per_task": delivery_cost,
        "acquisition_cost_per_customer": acquisition_cost,
        "notes": (
            "The numeric score is a value scale, not a predicted probability "
            "of success, sales, profit, or return on investment."
        ),
    }


def record_source_health(
    source: str,
    status: str,
    item_count: int = 0,
    error: Optional[str] = None,
) -> None:
    with connect_db() as connection:
        connection.execute("""
            INSERT INTO source_health (source, last_checked, status, item_count, error)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                last_checked=excluded.last_checked,
                status=excluded.status,
                item_count=excluded.item_count,
                error=excluded.error
        """, (source, utc_now(), status, item_count, error))


def save_finding(item: dict[str, Any]) -> None:
    analysis = discovery_analysis(item)
    value = value_to_money_analysis(analysis)

    with connect_db() as connection:
        columns = _columns(connection, "findings")
        values = {
            "id": item["id"],
            "source": item.get("source"),
            "source_id": item.get("source_id"),
            "url": item.get("url"),
            "title": item.get("title"),
            "text": item.get("text"),
            "domain": analysis["domain"],
            "score": analysis["discovery_score"],
            "commercial_intent": analysis["commercial_intent"],
            "created_at": item.get("created_at"),
            "discovered_at": utc_now(),
            "raw_json": json.dumps(item.get("raw", {}), ensure_ascii=False)[:100000],
            "discovery_score": analysis["discovery_score"],
            "value_to_money_score": value["value_to_money_score"],
            "value_status": value["value_status"],
            "evidence_json": json.dumps(analysis["evidence"], ensure_ascii=False),
            "signals_json": json.dumps(analysis["signals"], ensure_ascii=False),
        }

        available = [key for key in values if key in columns]
        names = ", ".join('"' + key + '"' for key in available)
        placeholders = ", ".join("?" for _ in available)
        updates = ", ".join(
            '"' + key + '"=excluded."' + key + '"'
            for key in available if key != "id"
        )

        connection.execute(
            f"INSERT INTO findings ({names}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            tuple(values[key] for key in available),
        )


def collect_all_sources() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    all_items: list[dict[str, Any]] = []
    health: dict[str, dict[str, Any]] = {}

    collectors = [
        ("configured_feeds", collect_configured_feeds),
        ("hackernews", collect_hacker_news),
        ("stackexchange", collect_stack_exchange),
        ("github", collect_github_issues),
    ]

    for name, collector in collectors:
        try:
            items, info = collector()
            all_items.extend(items)
            health[name] = info
        except Exception as exc:
            health[name] = {
                "status": "error",
                "count": 0,
                "error": str(exc)[:500],
            }

    unique = {item["id"]: item for item in all_items}
    return list(unique.values()), health


def run_scan() -> dict[str, Any]:
    init_db()
    started = utc_now()
    started_clock = time.monotonic()

    with connect_db() as connection:
        cursor = connection.execute("""
            INSERT INTO scan_runs (started_at, status, item_count, source_count)
            VALUES (?, 'running', 0, 0)
        """, (started,))
        run_id = cursor.lastrowid

    try:
        items, health = collect_all_sources()
        domain_counts: dict[str, int] = {}
        saved_count = 0

        for item in items:
            analysis = discovery_analysis(item)
            domain_counts[analysis["domain"]] = domain_counts.get(analysis["domain"], 0) + 1
            save_finding(item)
            saved_count += 1

        for source, info in health.items():
            record_source_health(
                source,
                info.get("status", "unknown"),
                info.get("count", 0),
                info.get("error"),
            )

        finished = utc_now()
        summary = {
            "version": VERSION,
            "items_collected": len(items),
            "findings_saved": saved_count,
            "domains": domain_counts,
            "sources": health,
            "ranking": {
                "discovery": "heuristic score 0-100",
                "value_to_money": "evidence-gated; null until mandatory checks are verified",
            },
            "elapsed_seconds": round(time.monotonic() - started_clock, 2),
        }

        with connect_db() as connection:
            connection.execute("""
                UPDATE scan_runs
                SET finished_at=?, status=?, item_count=?, source_count=?, summary_json=?
                WHERE id=?
            """, (
                finished, "complete", saved_count, len(health),
                json.dumps(summary, ensure_ascii=False), run_id,
            ))

        return {
            "status": "complete",
            "run_id": run_id,
            "started_at": started,
            "finished_at": finished,
            **summary,
        }

    except Exception as exc:
        finished = utc_now()
        with connect_db() as connection:
            connection.execute("""
                UPDATE scan_runs
                SET finished_at=?, status=?, error=?
                WHERE id=?
            """, (finished, "error", str(exc)[:2000], run_id))
        return {
            "status": "error",
            "run_id": run_id,
            "started_at": started,
            "finished_at": finished,
            "error": str(exc)[:2000],
        }


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    for field in ("evidence_json", "signals_json", "raw_json"):
        raw = result.get(field)
        if raw:
            try:
                result[field.removesuffix("_json")] = json.loads(raw)
            except (ValueError, TypeError):
                pass
    return result


def top_findings(
    limit: int = 20,
    domain: Optional[str] = None,
    ranking: str = "discovery",
) -> list[dict[str, Any]]:
    init_db()
    limit = max(1, min(200, int(limit)))

    with connect_db() as connection:
        columns = _columns(connection, "findings")
        if ranking == "value_to_money" and "value_to_money_score" in columns:
            order_by = "value_to_money_score DESC, discovery_score DESC"
            where = "value_to_money_score IS NOT NULL"
        else:
            order_by = (
                "COALESCE(discovery_score, score, 0) DESC, discovered_at DESC"
            )
            where = "1=1"

        params: list[Any] = []
        if domain:
            where += " AND domain=?"
            params.append(domain)
        params.append(limit)

        rows = connection.execute(
            f"SELECT * FROM findings WHERE {where} ORDER BY {order_by} LIMIT ?",
            params,
        ).fetchall()
        return [_row_to_dict(row) for row in rows]


def scanner_status() -> dict[str, Any]:
    init_db()
    with connect_db() as connection:
        findings_count = connection.execute(
            "SELECT COUNT(*) FROM findings"
        ).fetchone()[0]
        runs_count = connection.execute(
            "SELECT COUNT(*) FROM scan_runs"
        ).fetchone()[0]
        latest = connection.execute("""
            SELECT started_at, finished_at, status, item_count, summary_json, error
            FROM scan_runs ORDER BY id DESC LIMIT 1
        """).fetchone()
        health_rows = connection.execute("""
            SELECT source, last_checked, status, item_count, error
            FROM source_health ORDER BY source
        """).fetchall()

        value_count = 0
        if "value_to_money_score" in _columns(connection, "findings"):
            value_count = connection.execute("""
                SELECT COUNT(*) FROM findings WHERE value_to_money_score IS NOT NULL
            """).fetchone()[0]

    latest_data = dict(latest) if latest else None
    if latest_data and latest_data.get("summary_json"):
        try:
            latest_data["summary"] = json.loads(latest_data["summary_json"])
        except ValueError:
            pass

    return {
        "version": VERSION,
        "database": DEFAULT_DB_PATH,
        "domains": list(DOMAINS.keys()),
        "findings_count": findings_count,
        "scan_runs_count": runs_count,
        "value_to_money_scored_count": value_count,
        "latest_run": latest_data,
        "sources": [dict(row) for row in health_rows],
        "ranking_rules": {
            "discovery_priority": "evidence signals + task clarity + freshness",
            "value_to_money": "requires independent verification; not inferred from keywords",
        },
    }


def record_outcome(
    finding_id: str,
    outcome: str,
    notes: str = "",
) -> dict[str, Any]:
    allowed = {
        "useful", "not_useful", "validated_demand", "no_demand",
        "verified_payment", "no_payment_evidence", "built", "rejected",
        "unknown",
    }
    if outcome not in allowed:
        raise ValueError("Unsupported outcome. Allowed: " + ", ".join(sorted(allowed)))

    with connect_db() as connection:
        exists = connection.execute(
            "SELECT id FROM findings WHERE id=?", (finding_id,)
        ).fetchone()
        if not exists:
            raise ValueError("Finding not found")

        cursor = connection.execute("""
            INSERT INTO finding_outcomes (finding_id, outcome, notes, created_at)
            VALUES (?, ?, ?, ?)
        """, (finding_id, outcome, str(notes or "")[:5000], utc_now()))

    return {
        "status": "recorded",
        "outcome_id": cursor.lastrowid,
        "finding_id": finding_id,
        "outcome": outcome,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="SolveEase Micro-Utility Scanner")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("scan", help="Run discovery scan")
    sub.add_parser("status", help="Show scanner status")

    top_parser = sub.add_parser("top", help="List top findings")
    top_parser.add_argument("--limit", type=int, default=20)
    top_parser.add_argument("--domain", default=None)
    top_parser.add_argument(
        "--ranking",
        choices=["discovery", "value_to_money"],
        default="discovery",
    )

    args = parser.parse_args()
    init_db()

    if args.command == "scan":
        result = run_scan()
    elif args.command == "status":
        result = scanner_status()
    elif args.command == "top":
        result = {
            "ranking": args.ranking,
            "findings": top_findings(args.limit, args.domain, args.ranking),
        }
    else:
        result = {
            "status": scanner_status(),
            "top_findings": top_findings(10),
        }

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
