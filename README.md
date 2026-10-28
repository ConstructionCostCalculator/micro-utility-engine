# Professional Engagement

Create proposal records only for qualified candidates. Client approval is a separate explicit action; provide the actual approval reference and approver identity. Never invent acceptance.

## Run locally
`pip install -r requirements.txt` then `python app.py`. Set a strong `API_TOKEN` before exposing write endpoints. Set `DATABASE_PATH=/var/data/service.sqlite3` for a Render disk mounted at `/var/data`.

All writes are auditable in SQLite. Configure `NEXT_STAGE_URL` to forward eligible outputs to the next service. Forwarding is disabled by default. All services expose `/health`, `/records`, and `/records/<id>`.
