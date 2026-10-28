# Global Utility Scanner

Find public pain/workaround signals via Hacker News Algolia and GitHub issue search. Configure `HN_QUERIES`, `GITHUB_QUERIES`, optional `GITHUB_TOKEN`, and `SCANNER_MAX_ITEMS`. Discovery signals are not proof of paid demand.

## Run locally
`pip install -r requirements.txt` then `python app.py`. Set a strong `API_TOKEN` before exposing write endpoints. Set `DATABASE_PATH=/var/data/service.sqlite3` for a Render disk mounted at `/var/data`.

All writes are auditable in SQLite. Configure `NEXT_STAGE_URL` to forward eligible outputs to the next service. Forwarding is disabled by default. All services expose `/health`, `/records`, and `/records/<id>`.
