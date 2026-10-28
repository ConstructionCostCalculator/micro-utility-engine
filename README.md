# Approved Task Executor

Execution requires recorded client approval. Only two safe allow-listed task types are included (`text_cleanup`, `json_validate`); arbitrary shell/code execution is deliberately disabled. Failed work goes to manual review.

## Run locally
`pip install -r requirements.txt` then `python app.py`. Set a strong `API_TOKEN` before exposing write endpoints. Set `DATABASE_PATH=/var/data/service.sqlite3` for a Render disk mounted at `/var/data`.

All writes are auditable in SQLite. Configure `NEXT_STAGE_URL` to forward eligible outputs to the next service. Forwarding is disabled by default. All services expose `/health`, `/records`, and `/records/<id>`.
