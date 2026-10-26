# Micro-Utility Engine & Omni Lead Command Center

Production-ready serverless engine combining:
1. **Zero-Friction pSEO Landing Pages** (`/`, `/uscis-pdf-500kb-fixer`, `/uk-visa-grayscale-pdf`)
2. **Paystack Webhook & Viral Bypass State Router** (`/api/process`)
3. **Gemini 1.5 Flash Document rescue processing**
4. **Live PostgreSQL Lead Ingestion Engine** (`/api/ingest-lead`)
5. **Real-time Live Lead Command Center Dashboard** (`/dashboard`)

## Deployment Instructions (Render)

1. Push this code to your **GitHub** repository.
2. Log into **Render** and click **New + -> Blueprint**.
3. Select your `micro-utility-engine` repository.
4. Fill in secret environment variables in the Render Dashboard:
   - `GEMINI_API_KEY`
   - `PAYSTACK_SECRET_KEY`
   - `DATABASE_URL` (from Supabase / Managed PostgreSQL)
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
5. Click **Deploy**.
