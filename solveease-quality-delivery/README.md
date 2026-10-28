# Quality Delivery

QA checks require content or a file manifest and a lawful basis declaration if personal data is included. This is a starter checklist, not proof of domain correctness. Record actual delivery references only.

## Run locally
`pip install -r requirements.txt` then `python app.py`. Set a strong `API_TOKEN` before exposing write endpoints. Set `DATABASE_PATH=/var/data/service.sqlite3` for a Render disk mounted at `/var/data`.

All writes are auditable in SQLite. Configure `NEXT_STAGE_URL` to forward eligible outputs to the next service. Forwarding is disabled by default. All services expose `/health`, `/records`, and `/records/<id>`.
