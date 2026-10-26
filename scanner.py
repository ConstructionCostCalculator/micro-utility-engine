import os
import requests
import time

# Render Production Backend URL
RENDER_BASE_URL = os.environ.get("RENDER_BASE_URL", "https://micro-utility-engine.onrender.com")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "123456789")

HEADERS = {
    "Content-Type": "application/json",
    "X-Admin-Secret": ADMIN_SECRET
}

# --- 1. HIGH-CPM GLOBAL PSEO SEARCH TARGETS ---
GLOBAL_PSEO_TARGETS = [
    {
        "keyword": "uscis document pdf compressor under 500kb online",
        "slug": "uscis-pdf-500kb-compressor"
    },
    {
        "keyword": "uk visa digital photo size formatter online",
        "slug": "uk-visa-photo-formatter"
    },
    {
        "keyword": "eu cross border saas vat compliance calculator",
        "slug": "eu-saas-vat-compliance-calculator"
    },
    {
        "keyword": "canada express entry pdf size reducer",
        "slug": "canada-express-entry-pdf-reducer"
    }
]

# --- 2. GLOBAL B2B HIGH-VALUE TARGETS ---
GLOBAL_B2B_LEADS = [
    {
        "vertical": "Global SaaS & Compliance",
        "company_name": "Apex Cloud Systems Inc.",
        "location": "San Francisco, CA",
        "contact_email": "executives@apexcloud.io",
        "pain_point": "Managing complex multi-jurisdiction tax nexus and unformatted compliance data pipelines."
    },
    {
        "vertical": "Remote Operations & Logistics",
        "company_name": "Berlin Cloud Logistics GmbH",
        "location": "Berlin, Germany",
        "contact_email": "ops@berlincloud.de",
        "pain_point": "Processing heavy cross-border customs documents and PDF dumps efficiently."
    },
    {
        "vertical": "Fintech & Identity Verification",
        "company_name": "London Secure Auth Ltd",
        "location": "London, UK",
        "contact_email": "security@londonauth.co.uk",
        "pain_point": "Strict government portal file size limits causing upload failures for international clients."
    }
]

def run_global_scanner():
    print("🚀 Starting Autonomous Global Growth Scanner...")
    
    # 1. Deploy Global PSEO Landing Pages
    print("\n--- Deploying Global PSEO Target Batch ---")
    for target in GLOBAL_PSEO_TARGETS:
        try:
            res = requests.post(
                f"{RENDER_BASE_URL}/api/generate-pseo",
                json=target,
                headers=HEADERS,
                timeout=15
            )
            if res.status_code == 201:
                print(f"✅ Deployed PSEO: /{target['slug']}")
            else:
                print(f"⚠️ Failed PSEO [{target['slug']}]: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"❌ Error deploying PSEO [{target['slug']}]: {e}")
        time.sleep(2) # Prevent rate-limiting

    # 2. Ingest Global B2B Leads & Trigger AI Outreach
    print("\n--- Ingesting Global B2B Lead Batch ---")
    for lead in GLOBAL_B2B_LEADS:
        try:
            res = requests.post(
                f"{RENDER_BASE_URL}/api/ingest-lead",
                json=lead,
                headers=HEADERS,
                timeout=15
            )
            if res.status_code == 201:
                print(f"✅ Ingested Lead & AI Pitch: {lead['company_name']} ({lead['location']})")
            else:
                print(f"⚠️ Failed Lead [{lead['company_name']}]: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"❌ Error ingesting Lead [{lead['company_name']}]: {e}")
        time.sleep(2)

    print("\n🎉 Global Autonomous Scan Complete. Telemetry dispatched to Telegram.")

if __name__ == "__main__":
    run_global_scanner()
