"""SolveEase Micro-Utility Engine: privacy-first text cleanup."""
import os, re, sqlite3, hmac, logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string
import requests

APP_NAME = "SolveEase Micro-Utility Engine"
DB_PATH = os.environ.get("DB_PATH", "data/solveease.sqlite3")
MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "50000"))
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("solveease")
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1_000_000
app.config["JSON_SORT_KEYS"] = False

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def connect_db():
    path = Path(DB_PATH)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn

def init_db():
    with connect_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS scan_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            status TEXT NOT NULL, details TEXT NOT NULL
        )""")
init_db()

def clean_text(value):
    """Deterministic, local text cleanup. No AI or upload required."""
    if not isinstance(value, str):
        raise ValueError("Text must be a string.")
    if len(value) > MAX_TEXT_CHARS:
        raise ValueError(f"Text exceeds the {MAX_TEXT_CHARS:,}-character limit.")
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    lines = [re.sub(r"[\t ]+", " ", line).strip() for line in value.split("\n")]
    # Preserve paragraph boundaries, collapse excessive blank lines, remove trailing spaces.
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out

def notify_telegram(message):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                          json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=5)
        return r.ok
    except requests.RequestException:
        log.exception("Telegram notification failed")
        return False

HOME = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Clean messy copied text instantly on your phone. Free, private, and no sign-up.">
<title>SolveEase | Free Text Cleaner</title>
<style>
:root{color-scheme:dark;--bg:#0b1220;--panel:#131f32;--line:#29384e;--muted:#a8b6c9;--accent:#35d39a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#f4f7fb;font:16px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:850px;margin:auto;padding:24px 16px 56px}.brand{font-weight:800;letter-spacing:.04em;color:var(--accent)}
h1{font-size:clamp(1.8rem,6vw,3rem);line-height:1.1;margin:24px 0 12px}p{color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;margin-top:20px}
textarea{width:100%;min-height:190px;background:#0b1220;color:#f4f7fb;border:1px solid #40516b;border-radius:10px;padding:13px;font:inherit;resize:vertical}
button{border:0;border-radius:10px;background:var(--accent);color:#06251a;font-weight:800;padding:12px 16px;font:inherit;cursor:pointer}
button.secondary{background:#26364d;color:#fff}button:disabled{opacity:.6;cursor:wait}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}.meta{font-size:.88rem}.status{min-height:1.5em;color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
a{color:var(--accent)}footer{font-size:.85rem;color:var(--muted);margin-top:25px}
</style></head><body><main>
<div class="brand">SOLVEEASE · MICRO-UTILITY ENGINE</div>
<h1>Make messy copied text usable in seconds.</h1>
<p>Clean spacing, tabs, line endings and excess blank lines. Free, no account, no AI required. Your text is processed by this service and is not saved by the free tool.</p>
<section class="panel"><label for="source"><strong>Paste your text</strong></label>
<textarea id="source" maxlength="{{ max_chars }}" placeholder="Paste text from a PDF, email, website, or spreadsheet…"></textarea>
<div class="actions"><button id="clean">Clean text free</button><button class="secondary" id="copy">Copy result</button><button class="secondary" id="clear">Clear</button></div>
<p class="meta" id="stats">0 characters</p><label for="result"><strong>Cleaned result</strong></label>
<textarea id="result" readonly placeholder="Your cleaned text will appear here."></textarea><p class="status" id="status" role="status"></p>
</section>
<section class="panel"><h2>How it works</h2><div class="grid"><div><strong>1. Paste</strong><p>Bring text from a document or webpage.</p></div><div><strong>2. Clean</strong><p>Normalize spaces and line breaks while preserving paragraphs.</p></div><div><strong>3. Copy</strong><p>Use the result in your own document or workflow.</p></div></div></section>
<section class="panel"><h2>Built for simple, repeatable jobs</h2><p>This is a formatting helper, not a legal, tax, immigration, or compliance adviser. Always verify official submission requirements.</p><p><a href="/health">Service status</a> · <a href="/api">API information</a></p></section>
<footer>Privacy-first by design. Do not paste passwords, payment-card details, or highly sensitive personal information.</footer>
</main><script>
const source=document.querySelector('#source'),result=document.querySelector('#result'),status=document.querySelector('#status'),stats=document.querySelector('#stats');
source.addEventListener('input',()=>stats.textContent=source.value.length.toLocaleString()+' characters');
document.querySelector('#clean').addEventListener('click',async()=>{status.textContent='Cleaning…';try{const r=await fetch('/api/clean',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:source.value})});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not clean text');result.value=d.cleaned_text;status.textContent='Done. '+d.output_characters.toLocaleString()+' characters.'}catch(e){status.textContent=e.message}});
document.querySelector('#copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(result.value);status.textContent='Copied.'}catch(e){result.focus();result.select();status.textContent='Select and copy the result manually.'}});
document.querySelector('#clear').addEventListener('click',()=>{source.value='';result.value='';stats.textContent='0 characters';status.textContent='Cleared.';source.focus()});
</script></body></html>"""

@app.get("/")
def home():
    return render_template_string(HOME, max_chars=MAX_TEXT_CHARS)

@app.get("/health")
def health():
    try:
        with connect_db() as conn:
            conn.execute("SELECT 1").fetchone()
        db_ok = True
    except sqlite3.Error:
        db_ok = False
    return jsonify({"service":"ok" if db_ok else "degraded","database":"ok" if db_ok else "unavailable",
                    "timestamp":utcnow()}), (200 if db_ok else 503)

@app.get("/api")
def api_info():
    return jsonify({"name":APP_NAME,"version":"2.0.0","endpoints":{
        "GET /health":"Health check","POST /api/clean":"Clean text; JSON {text: string}",
        "POST /api/admin/scan":"Record a lightweight health scan; requires X-Admin-Secret"
    },"privacy":"Free endpoint does not persist submitted text."})

@app.post("/api/clean")
def api_clean():
    data = request.get_json(silent=True) or {}
    try:
        cleaned = clean_text(data.get("text"))
    except ValueError as e:
        return jsonify({"error":str(e)}), 400
    return jsonify({"status":"success","cleaned_text":cleaned,
                    "input_characters":len(data["text"]),"output_characters":len(cleaned)})

@app.post("/api/admin/scan")
def admin_scan():
    if not ADMIN_SECRET or not hmac.compare_digest(request.headers.get("X-Admin-Secret",""), ADMIN_SECRET):
        return jsonify({"error":"Unauthorized"}), 403
    try:
        with connect_db() as conn:
            conn.execute("INSERT INTO scan_runs(created_at,status,details) VALUES(?,?,?)",
                         (utcnow(),"complete","Health endpoint and SQLite connectivity checked. No fabricated leads or SEO pages created."))
    except sqlite3.Error:
        return jsonify({"error":"Database unavailable"}), 503
    notify_telegram("SolveEase scan completed: service health checked; no fabricated leads generated.")
    return jsonify({"status":"complete","created_at":utcnow(),"actions":["database_check","scan_log"],"lead_count":0}), 200

@app.errorhandler(413)
def too_large(_):
    return jsonify({"error":"Request too large."}), 413

@app.errorhandler(500)
def internal_error(_):
    log.exception("Unhandled server error")
    return jsonify({"error":"Unexpected server error."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","5000")))
