# SolveEase Micro-Utility Engine — refined MVP 2.0

A mobile-first, low-cost utility that solves one real task immediately: cleaning copied text by normalizing tabs, spaces, line endings and excessive blank lines. The free endpoint is deterministic, does not require an AI key, and does not persist submitted text.

## Why this is a better value-to-money MVP
- **Actual working utility first:** no placeholder “AI complete” result, fake leads, or fictional revenue metrics.
- **Low running cost:** Flask + SQLite + Requests; no paid AI API required. SQLite is suitable for an MVP/single instance.
- **Mobile-first:** responsive page, paste/clean/copy/clear controls.
- **Privacy:** the free route does not save source text; paid task stores only a SHA-256 input hash and output required to return the result. Avoid sensitive content.
- **No premature checkout:** there is no payment gate until a paid feature and willingness-to-pay are validated.
- **Observable:** `/health`, structured scanner output, optional Telegram alert, and CI tests.
- **Honest growth:** scanner checks service health. It does not fabricate B2B leads, claim search ranking, or create thin auto-generated SEO pages.

## Run locally
Python 3.11 recommended.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`. The free cleaner works without environment variables.

## API
- `GET /health` — health and database status.
- `GET /api` — API overview.
- `POST /api/clean` with JSON `{"text":"messy  text"}` — returns `cleaned_text`, character counts.
- `POST /api/payments/verify-and-process` with JSON `{"reference":"verified_paystack_reference","text":"..."}` — optional paid flow. Requires Paystack keys and matching configured amount/currency.
- `POST /api/admin/scan` — requires `X-Admin-Secret` header; records a health scan. No prospect scraping or fabricated leads.

## Render deployment
1. Push this repository to your own GitHub repository.
2. Create a Render web service from the repo, or use the included `render.yaml`.
3. Set `ADMIN_SECRET` to a long random value. Do not use a value from the repository.
4. The free-tier filesystem can be ephemeral, so SQLite data may be lost on redeploy/restart. If durable records are needed, configure a persistent disk or managed database on a plan that supports it.
5. Optional: add Telegram credentials.
6. Deploy and test `/health`, then use the free text cleaner.

## Monetization rule
The free cleaner is deliberately open and useful. Do not charge for the same output while it is freely available. A paid add-on should be added only after real user evidence identifies a costly repeat task—e.g., validated bulk processing, structured export, or workflow-specific output—and a small willingness-to-pay test. Build server-side payment initialization, verification, idempotency, support and refund handling only after the paid deliverable is defined.

## Current limitations / next evidence gates
- The utility is a focused text cleaner, not a PDF compressor, OCR tool, tax calculator, legal service, or immigration compliance tool.
- No demand, SEO traffic, conversion, or revenue is claimed. Validate with real users before expanding.
- Do not add a niche just because a keyword looks high-CPC. Interview/observe real users, check competitor reviews/workarounds, measure repeated usage, and test willingness to pay.
- Paid endpoint is not wired to checkout UI yet; this is deliberate so the release does not charge people without a complete and tested purchase flow.

## Tests
```bash
python -m unittest discover -s tests -v
```
