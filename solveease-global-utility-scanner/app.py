
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests
from flask import Flask, jsonify, request

APP_NAME = "Global Utility Scanner"
VERSION = "1.1.0"

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "/var/data/global_utility_scanner.sqlite3"
)
API_TOKEN = os.getenv("API_TOKEN", "").strip()

HN_API = "https://hn.algolia.com/api/v1/search"
GITHUB_API = "https://api.github.com/search/issues"

REQUEST_TIMEOUT = 15
MAX_RESULTS_PER_SOURCE = 30
MAX_SCAN_QUERIES = 8
MAX_TEXT_LENGTH = 12000

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


# Signals are discovery clues, not proof of buyer demand.
SIGNAL_TERMS = {
    "manual_work": [
        "manually", "manual work", "spreadsheet", "copy and paste",
        "copy-paste", "repetitive task", "repetitive work",
        "doing this by hand", "too much work"
    ],
    "workflow_friction": [
        "workflow", "time-consuming", "takes hours", "takes forever",
        "complicated", "frustrating", "painful process", "workaround"
    ],
    "quality_problem": [
        "incorrect output", "bad output", "poor quality", "inaccurate",
        "wrong result", "broken", "doesn't work", "does not work",
        "failed", "unreliable", "bug"
    ],
    "automation_request": [
        "automate", "automation", "automatically", "integrate",
        "integration", "batch processing", "bulk processing"
    ],
    "cost_or_access": [
        "too expensive", "expensive", "pricing", "price increase",
        "paywall", "free alternative", "no free", "rate limit"
    ],
    "missing_capability": [
        "feature request", "would be useful", "wish it could",
        "is there a way", "looking for a tool", "need a tool",
        "missing feature", "doesn't support", "does not support"
    ],
}

DEFAULT_QUERIES = [
    "manual workflow automation",
    "spreadsheet repetitive work",
    "tool inaccurate output",
    "workflow workaround",
    "feature request automation",
    "too expensive tool alternative",
    "batch processing tool",
    "time-consuming process",
]

USER_AGENT = "SolveEase-Global-Utility-Scanner/1.1"


def now():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    directory = os.path.dirname(os.path.abspath(DATABASE_PATH))
    os.makedirs(directory, exist_ok=True)

    db = sqlite3.connect(DATABASE_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=20000")
    db.execute("PRAGMA journal_mode=WAL")
    return db


def init_db():
    with get_connection() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS findings (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                author TEXT,
                published_at TEXT,
                discovered_at TEXT NOT NULL,
                text_excerpt TEXT,
                matched_signals TEXT NOT NULL,
                signal_score INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'DISCOVERED',
                evidence_json TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_findings_source_identity
            ON findings(source, source_id)
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS scan_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                queries_json TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                records_seen INTEGER NOT NULL DEFAULT 0,
                records_saved INTEGER NOT NULL DEFAULT 0,
                errors_json TEXT NOT NULL DEFAULT '[]'
            )
        """)


def authorize():
    """Protect state-changing endpoints when a token is configured."""
    if not API_TOKEN:
        return True

    supplied = request.headers.get("Authorization", "")
    if supplied.lower().startswith("bearer "):
        supplied = supplied[7:].strip()
    else:
        supplied = ""

    return hmac.compare_digest(supplied, API_TOKEN)


@app.before_request
def guard_write_requests():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if not API_TOKEN:
            return jsonify({
                "error": "api_token_not_configured",
                "message": (
                    "Set a strong API_TOKEN environment variable "
                    "before using write endpoints."
                )
            }), 503

        if not authorize():
            return jsonify({"error": "unauthorized"}), 401


def normalize_text(value):
    if not isinstance(value, str):
        return ""
    value = re.sub(r"<[^>]*>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:MAX_TEXT_LENGTH]


def classify_signal(title, body):
    text = (title + " " + body).lower()
    matched = []

    for category, terms in SIGNAL_TERMS.items():
        hits = [term for term in terms if term in text]
        if hits:
            matched.append({
                "category": category,
                "terms": hits[:5]
            })

    # A simple discovery-priority score, not a probability.
    score = min(100, sum(
        12 + min(8, len(item["terms"]) * 2)
        for item in matched
    ))

    return matched, score


def stable_id(source, source_id, url):
    raw = f"{source}|{source_id}|{url}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def extract_hn_record(item):
    title = normalize_text(
        item.get("title") or item.get("story_title") or ""
    )
    body = normalize_text(
        item.get("comment_text") or item.get("story_text") or ""
    )

    url = (
        item.get("url")
        or item.get("story_url")
        or (
            "https://news.ycombinator.com/item?id="
            + str(item.get("objectID", ""))
        )
    )

    object_id = str(item.get("objectID", "")).strip()
    if not object_id or not title or not url.startswith("https://"):
        return None

    return {
        "source": "hacker_news",
        "source_id": object_id,
        "title": title[:1000],
        "url": url,
        "author": normalize_text(item.get("author", ""))[:300],
        "published_at": item.get("created_at"),
        "text_excerpt": body[:4000],
    }


def extract_github_record(item):
    title = normalize_text(item.get("title", ""))
    body = normalize_text(item.get("body", ""))
    url = item.get("html_url", "")
    source_id = str(item.get("id", "")).strip()

    if not source_id or not title or not url.startswith("https://github.com/"):
        return None

    user = item.get("user") or {}

    return {
        "source": "github_issue",
        "source_id": source_id,
        "title": title[:1000],
        "url": url,
        "author": normalize_text(user.get("login", ""))[:300],
        "published_at": item.get("created_at"),
        "text_excerpt": body[:4000],
    }


def fetch_hacker_news(query, errors):
    params = {
        "query": query,
        "tags": "story,comment",
        "hitsPerPage": MAX_RESULTS_PER_SOURCE,
    }

    try:
        response = requests.get(
            HN_API,
            params=params,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        data = response.json()

        if not isinstance(data.get("hits"), list):
            errors.append({
                "source": "hacker_news",
                "query": query,
                "error": "unexpected_response_format",
            })
            return []

        results = []
        for item in data["hits"]:
            record = extract_hn_record(item)
            if record:
                results.append(record)
        return results

    except (requests.RequestException, ValueError) as exc:
        errors.append({
            "source": "hacker_news",
            "query": query,
            "error": str(exc)[:500],
        })
        return []


def fetch_github_issues(query, errors):
    params = {
        "q": f'{query} is:issue',
        "sort": "created",
        "order": "desc",
        "per_page": min(MAX_RESULTS_PER_SOURCE, 100),
    }

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    }

    # Optional public API token increases available rate limits.
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    try:
        response = requests.get(
            GITHUB_API,
            params=params,
            timeout=REQUEST_TIMEOUT,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        if not isinstance(data.get("items"), list):
            errors.append({
                "source": "github_issues",
                "query": query,
                "error": "unexpected_response_format",
            })
            return []

        results = []
        for item in data["items"]:
            record = extract_github_record(item)
            if record:
                results.append(record)
        return results

    except (requests.RequestException, ValueError) as exc:
        errors.append({
            "source": "github_issues",
            "query": query,
            "error": str(exc)[:500],
        })
        return []


def save_finding(record):
    title = record["title"]
    body = record["text_excerpt"]
    matched, score = classify_signal(title, body)

    # Save only records that match at least one signal category.
    if not matched:
        return False

    fid = stable_id(
        record["source"],
        record["source_id"],
        record["url"],
    )
    timestamp = now()

    evidence = {
        "source": record["source"],
        "source_id": record["source_id"],
        "source_url": record["url"],
        "title": title,
        "excerpt": body[:2000],
        "author": record["author"],
        "published_at": record["published_at"],
        "matched_signals": matched,
        "evidence_limitations": [
            "Keyword matching can produce false positives.",
            "A public post does not prove willingness to pay.",
            "Engagement and comments do not prove purchases.",
            "Buyer identity and recurring demand remain unverified.",
        ],
    }

    with get_connection() as db:
        cursor = db.execute("""
            INSERT OR IGNORE INTO findings (
                id, source, source_id, title, url, author,
                published_at, discovered_at, text_excerpt,
                matched_signals, signal_score, status, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fid,
            record["source"],
            record["source_id"],
            title,
            record["url"],
            record["author"],
            record["published_at"],
            timestamp,
            body[:4000],
            json.dumps(matched, ensure_ascii=False),
            score,
            "DISCOVERED",
            json.dumps(evidence, ensure_ascii=False),
        ))

        return cursor.rowcount > 0


def run_scan(queries):
    started = now()
    errors = []
    records_seen = 0
    records_saved = 0
    source_counts = {
        "hacker_news": 0,
        "github_issues": 0,
    }

    with get_connection() as db:
        cursor = db.execute("""
            INSERT INTO scan_runs (
                started_at, status, queries_json, sources_json
            ) VALUES (?, ?, ?, ?)
        """, (
            started,
            "RUNNING",
            json.dumps(queries),
            json.dumps(["hacker_news", "github_issues"]),
        ))
        run_id = cursor.lastrowid

    try:
        for query in queries:
            records = fetch_hacker_news(query, errors)
            records_seen += len(records)
            source_counts["hacker_news"] += len(records)

            for record in records:
                if save_finding(record):
                    records_saved += 1

            # Avoid excessive requests to public services.
            time.sleep(0.25)

            records = fetch_github_issues(query, errors)
            records_seen += len(records)
            source_counts["github_issues"] += len(records)

            for record in records:
                if save_finding(record):
                    records_saved += 1

            time.sleep(0.25)

        status = (
            "COMPLETE_WITH_ERRORS"
            if errors and records_seen
            else "FAILED"
            if errors and not records_seen
            else "COMPLETE"
        )

    except Exception as exc:
        errors.append({
            "source": "scanner",
            "error": str(exc)[:500],
        })
        status = "FAILED"

    finished = now()

    with get_connection() as db:
        db.execute("""
            UPDATE scan_runs
            SET finished_at = ?, status = ?, records_seen = ?,
                records_saved = ?, errors_json = ?
            WHERE id = ?
        """, (
            finished,
            status,
            records_seen,
            records_saved,
            json.dumps(errors, ensure_ascii=False),
            run_id,
        ))

    return {
        "run_id": run_id,
        "status": status,
        "started_at": started,
        "finished_at": finished,
        "queries": queries,
        "sources": source_counts,
        "records_seen": records_seen,
        "new_findings_saved": records_saved,
        "errors": errors,
        "interpretation": (
            "These are discovery signals only. Buyer demand, "
            "willingness to pay, competition gaps, legal suitability, "
            "automation reliability, and unit economics require "
            "separate verification."
        ),
    }


@app.get("/")
def index():
    return jsonify({
        "service": APP_NAME,
        "version": VERSION,
        "health": "/health",
        "endpoints": {
            "health": "GET /health",
            "findings": "GET /findings",
            "finding_detail": "GET /findings/<id>",
            "scan": "POST /scan",
            "scan_runs": "GET /scan-runs",
        },
    })


@app.get("/health")
def health():
    init_db()

    with get_connection() as db:
        count = db.execute(
            "SELECT COUNT(*) FROM findings"
        ).fetchone()[0]

        latest = db.execute("""
            SELECT id, started_at, finished_at, status,
                   records_seen, records_saved
            FROM scan_runs
            ORDER BY id DESC LIMIT 1
        """).fetchone()

    return jsonify({
        "service": APP_NAME,
        "version": VERSION,
        "status": "ok",
        "findings_count": count,
        "latest_scan": dict(latest) if latest else None,
        "at": now(),
    })


@app.post("/scan")
def scan():
    init_db()
    payload = request.get_json(silent=True) or {}

    requested = payload.get("queries", DEFAULT_QUERIES)

    if not isinstance(requested, list) or not requested:
        return jsonify({
            "error": "queries_must_be_a_nonempty_list"
        }), 400

    if len(requested) > MAX_SCAN_QUERIES:
        return jsonify({
            "error": "too_many_queries",
            "maximum": MAX_SCAN_QUERIES,
        }), 400

    queries = []
    for item in requested:
        if not isinstance(item, str):
            return jsonify({
                "error": "each_query_must_be_a_string"
            }), 400

        item = normalize_text(item)
        if item:
            queries.append(item[:200])

    if not queries:
        return jsonify({"error": "no_valid_queries"}), 400

    result = run_scan(queries)
    http_status = 502 if result["status"] == "FAILED" else 200
    return jsonify(result), http_status


@app.get("/findings")
def findings():
    init_db()

    try:
        limit = int(request.args.get("limit", "50"))
        limit = min(max(limit, 1), 200)
    except ValueError:
        return jsonify({"error": "limit_must_be_an_integer"}), 400

    category = request.args.get("category", "").strip()
    status = request.args.get("status", "DISCOVERED").strip()

    with get_connection() as db:
        rows = db.execute("""
            SELECT id, source, title, url, author, published_at,
                   discovered_at, matched_signals, signal_score, status
            FROM findings
            WHERE status = ?
            ORDER BY discovered_at DESC
            LIMIT ?
        """, (status, limit)).fetchall()

    output = []
    for row in rows:
        item = dict(row)
        item["matched_signals"] = json.loads(
            item["matched_signals"]
        )

        if category and not any(
            signal["category"] == category
            for signal in item["matched_signals"]
        ):
            continue

        output.append(item)

    return jsonify({
        "service": APP_NAME,
        "count": len(output),
        "findings": output,
        "warning": (
            "Discovery signals are not verified demand or proof "
            "of a profitable opportunity."
        ),
    })


@app.get("/findings/<finding_id>")
def finding_detail(finding_id):
    init_db()

    with get_connection() as db:
        row = db.execute(
            "SELECT * FROM findings WHERE id = ?",
            (finding_id,),
        ).fetchone()

    if not row:
        return jsonify({"error": "not_found"}), 404

    item = dict(row)
    item["matched_signals"] = json.loads(item["matched_signals"])
    item["evidence"] = json.loads(item.pop("evidence_json"))
    return jsonify(item)


@app.get("/scan-runs")
def scan_runs():
    init_db()

    try:
        limit = min(
            max(int(request.args.get("limit", "20")), 1),
            100,
        )
    except ValueError:
        return jsonify({"error": "limit_must_be_an_integer"}), 400

    with get_connection() as db:
        rows = db.execute("""
            SELECT * FROM scan_runs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        for key in ("queries_json", "sources_json", "errors_json"):
            item[key.removesuffix("_json")] = json.loads(item.pop(key))
        result.append(item)

    return jsonify({"count": len(result), "runs": result})


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "request_too_large"}), 413


@app.errorhandler(500)
def internal_error(_error):
    app.logger.exception("Unhandled server error")
    return jsonify({"error": "internal_server_error"}), 500


# Initialize schema when the app process starts.
init_db()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000")),
        debug=False,
    )
