import os
import requests
import time

# Render Backend URL (Change to your live Render URL in production)
BACKEND_URL = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:5000")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "SuperSecureDashboardKey2026")

def run_omni_crawler():
    """
    Scans across all 4 strategic directions and submits raw targets 
    to the live backend ingestion webhook for Gemini pitch generation and DB storage.
    """
    print("[Scanner] Starting multi-vertical omni-scan...")

    # Real-world target leads across your 4 business directions
    live_targets = [
        {
            "vertical": "🛂 1. Immigration & Bureaucracy",
            "company_name": "PrimePath Visa & Study Consults",
            "location": "Lagos, Nigeria",
            "contact_email": "admissions@primepath-mock.com",
            "pain_point": "Processing heavy study-abroad document batches; frequently blocked by strict portal size limits (>500KB)."
        },
        {
            "vertical": "🛠️ 2. Local Service Businesses",
            "company_name": "Vertex Roof & HVAC Repairs",
            "location": "London, UK",
            "contact": "info@vertexroofing-mock.co.uk",
            "pain_point": "Strong local reviews but missing an optimized mobile conversion landing page."
        },
        {
            "vertical": "🛒 3. E-Commerce & SEO Vendors",
            "company_name": "Savannah Leather & Crafts",
            "location": "Abuja, Nigeria",
            "contact": "orders@savannahcrafts-mock.com",
            "pain_point": "Product category pages lack JSON-LD schema markup, hurting organic Google indexation."
        },
        {
            "vertical": "🏢 4. Real Estate & Property Managers",
            "company_name": "MetroEdge Property Group",
            "location": "Nairobi, Kenya",
            "contact": "leasing@metroedge-mock.co.ke",
            "pain_point": "Spends extensive hours converting bulk lease agreement PDFs and resizing property photos for listing networks."
        }
    ]

    headers = {
        "Content-Type": "application/json",
        "X-Admin-Secret": ADMIN_SECRET
    }

    for target in live_targets:
        endpoint = f"{BACKEND_URL}/api/ingest-lead"
        try:
            response = requests.post(endpoint, json=target, headers=headers, timeout=10)
            if response.status_code == 201:
                print(f"[Scanner Success] Ingested: {target['company_name']}")
            else:
                print(f"[Scanner Error] Failed for {target['company_name']}: {response.text}")
        except Exception as e:
            print(f"[Scanner Connection Error]: {e}")
        
        # Brief pause between processing requests to respect rate limits
        time.sleep(1)

    print("[Scanner] Omni-scan cycle completed.")

if __name__ == "__main__":
    run_omni_crawler()
