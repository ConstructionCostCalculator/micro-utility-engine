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

# --- 20 HIGH-CPM GLOBAL PSEO KEYWORD TARGETS (US, UK, EU, CA) ---
GLOBAL_PSEO_TARGETS = [
    # US Immigration & Portal Formatting
    {
        "keyword": "uscis document pdf compressor under 500kb online",
        "slug": "uscis-pdf-500kb-compressor"
    },
    {
        "keyword": "us visa photo 2x2 inch digital cropper free",
        "slug": "us-visa-photo-cropper"
    },
    {
        "keyword": "nvc civil documents pdf size reducer tool",
        "slug": "nvc-document-size-reducer"
    },
    {
        "keyword": "urgent uscis translation and certification template 2026",
        "slug": "urgent-uscis-translation-template"
    },

    # UK & EU Immigration & Travel Compliance
    {
        "keyword": "uk visa digital photo size formatter online",
        "slug": "uk-visa-photo-formatter"
    },
    {
        "keyword": "uk home office pdf upload size limit fixer",
        "slug": "uk-home-office-pdf-fixer"
    },
    {
        "keyword": "eu schengen visa cover letter generator instant",
        "slug": "eu-schengen-cover-letter-generator"
    },
    {
        "keyword": "spain digital nomad visa income calculator 2026",
        "slug": "spain-digital-nomad-calculator"
    },

    # Canada Portal & Express Entry
    {
        "keyword": "canada express entry pdf size reducer tool",
        "slug": "canada-express-entry-pdf-reducer"
    },
    {
        "keyword": "ircc portal file size compressor 4mb fix",
        "slug": "ircc-file-size-compressor"
    },

    # Cross-Border B2B Tax & SaaS Compliance
    {
        "keyword": "eu cross border saas vat compliance calculator",
        "slug": "eu-saas-vat-compliance-calculator"
    },
    {
        "keyword": "us state sales tax nexus calculator remote saas",
        "slug": "us-remote-saas-tax-calculator"
    },
    {
        "keyword": "uk digital services vat threshold estimator 2026",
        "slug": "uk-vat-threshold-estimator"
    },
    {
        "keyword": "cross border freelancer invoice tax template pdf",
        "slug": "cross-border-invoice-tax-template"
    },

    # High-Value Document Polish & Rescue Utilities
    {
        "keyword": "executive resume pdf unformatter plain text clean",
        "slug": "executive-resume-unformatter"
    },
    {
        "keyword": "b2b contract legal plain English summarizer online",
        "slug": "b2b-contract-legal-summarizer"
    },
    {
        "keyword": "bank statement pdf text extractor for tax audit",
        "slug": "bank-statement-tax-extractor"
    },
    {
        "keyword": "commercial lease agreement pdf formatting tool",
        "slug": "commercial-lease-formatting-tool"
    },
    {
        "keyword": "confidentiality agreement nda clean text formatter",
        "slug": "nda-clean-text-formatter"
    },
    {
        "keyword": "corporate board resolution generator template instant",
        "slug": "corporate-board-resolution-generator"
    }
]

# --- HIGH-VALUE GLOBAL B2B LEADS FOR ENGINE DISPATCH ---
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

def warm_up_render():
    """Wake up Render instance if it is currently sleeping."""
    print("⏳ Sending warm-up request to Render...")
    try:
        requests.get(f"{RENDER_BASE_URL}/api/get-stats", timeout=35)
        print("⚡ Render service awake and active.")
    except Exception as e:
        print(f"⚠️ Render warm-up ping completed: {e}")

def run_global_scanner():
    warm_up_render()
    print("\n🚀 Starting Autonomous Global Growth Scanner (20 Target Batch)...")
    
    # 1. Deploy Global PSEO Landing Pages
    print(f"\n--- Deploying {len(GLOBAL_PSEO_TARGETS)} Global PSEO Targets ---")
    for index, target in enumerate(GLOBAL_PSEO_TARGETS, 1):
        try:
            res = requests.post(
                f"{RENDER_BASE_URL}/api/generate-pseo",
                json=target,
                headers=HEADERS,
                timeout=30
            )
            if res.status_code == 201:
                print(f"[{index}/{len(GLOBAL_PSEO_TARGETS)}] ✅ Deployed PSEO: /{target['slug']}")
            else:
                print(f"[{index}/{len(GLOBAL_PSEO_TARGETS)}] ⚠️ Failed [{target['slug']}]: {res.status_code}")
        except Exception as e:
            print(f"[{index}/{len(GLOBAL_PSEO_TARGETS)}] ❌ Error deploying [{target['slug']}]: {e}")
        time.sleep(1.5) # Smooth execution spacing

    # 2. Ingest Global B2B Leads & Trigger AI Outreach
    print("\n--- Ingesting Global B2B Lead Batch ---")
    for lead in GLOBAL_B2B_LEADS:
        try:
            res = requests.post(
                f"{RENDER_BASE_URL}/api/ingest-lead",
                json=lead,
                headers=HEADERS,
                timeout=30
            )
            if res.status_code == 201:
                print(f"✅ Ingested Lead & AI Pitch: {lead['company_name']} ({lead['location']})")
            else:
                print(f"⚠️ Failed Lead [{lead['company_name']}]: {res.status_code}")
        except Exception as e:
            print(f"❌ Error ingesting Lead [{lead['company_name']}]: {e}")
        time.sleep(2)

    print("\n🎉 All 20 Global Targets Deployed. Real-time telemetry sent to Telegram.")

if __name__ == "__main__":
    run_global_scanner()
