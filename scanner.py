"""Low-cost scheduled health scanner. Does not fabricate prospects or claim SEO deployment."""
import os, json, sys
from datetime import datetime, timezone
import requests

BASE_URL = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("RENDER_BASE_URL", "http://127.0.0.1:5000")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")

def run():
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "base_url": BASE_URL, "checks": {}}
    try:
        r = requests.get(BASE_URL.rstrip("/") + "/health", timeout=15)
        report["checks"]["health"] = {"http_status": r.status_code, "body": r.json() if r.headers.get("content-type","").startswith("application/json") else r.text[:300]}
        if r.status_code != 200:
            report["status"] = "degraded"
            print(json.dumps(report, indent=2)); return 1
    except (requests.RequestException, ValueError) as exc:
        report["status"] = "failed"; report["error"] = str(exc)
        print(json.dumps(report, indent=2)); return 1
    if ADMIN_SECRET:
        try:
            r = requests.post(BASE_URL.rstrip("/") + "/api/admin/scan", headers={"X-Admin-Secret":ADMIN_SECRET}, timeout=15)
            report["checks"]["scan"] = {"http_status":r.status_code, "body":r.json()}
        except (requests.RequestException, ValueError) as exc:
            report["checks"]["scan"] = {"error":str(exc)}
    else:
        report["checks"]["scan"] = {"skipped":"ADMIN_SECRET not configured"}
    report["status"] = "ok"
    print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(run())
