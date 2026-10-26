import os
import json
import hmac
import hashlib
import requests
from flask import Flask, request, jsonify, render_template_string
from google import genai
from database import get_db_connection, init_db
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Initialize Google GenAI Client
ai_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY")
VIRAL_SHARED_SECRET = os.environ.get("VIRAL_SHARED_SECRET", "SystemViralToken2026")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "123456789")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Initialize database schema on startup
try:
    init_db()
except Exception as e:
    print(f"[DB Init Warning]: {e}")

def send_telegram_alert(message):
    """Sends real-time alerts to your Telegram monitoring channel."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram dispatch error: {e}")

PSEO_LANDING_PAGES = {
    "uscis-pdf-500kb-fixer": {
        "title": "USCIS Document Size Fixer | Under 500KB PDF Instant Tool",
        "heading": "🚨 USCIS Portal Rejected Your PDF Size?",
        "subheading": "Instantly compress and format your immigration documents under 500KB without losing readability. No signup required."
    },
    "uk-visa-grayscale-pdf": {
        "title": "UK Visa Grayscale PDF Converter | Instant Portal Ready",
        "heading": "🇬🇧 UK Visa Portal File Error Fixer",
        "subheading": "Convert scans and photos into clean, portal-compliant grayscale PDFs in 3 seconds flat."
    },
    "default": {
        "title": "Instant Document Utilities | Zero Friction AI Engine",
        "heading": "⚡ Instant Workflow & Document Engine",
        "subheading": "Drop messy files, clean text, or fix broken formats instantly."
    }
}

@app.route('/')
@app.route('/<seo_slug>')
def dynamic_pseo_frontend(seo_slug="default"):
    page_data = PSEO_LANDING_PAGES.get(seo_slug, PSEO_LANDING_PAGES["default"])
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{page_data['title']}</title>
        <script src="https://js.paystack.co/v1/inline.js"></script>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; display: flex; justify-content: center; }}
            .container {{ background: #1e293b; border: 1px solid #334155; max-width: 500px; width: 100%; padding: 25px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); margin-top: 40px; }}
            textarea {{ width: 100%; height: 140px; background: #0f172a; border: 1px solid #475569; color: #fff; border-radius: 6px; padding: 12px; box-sizing: border-box; font-size: 14px; resize: none; }}
            button.action-btn {{ background: #10b981; color: white; border: none; width: 100%; padding: 14px; border-radius: 6px; font-weight: bold; cursor: pointer; margin-top: 15px; font-size: 15px; }}
            button.action-btn:disabled {{ background: #475569; cursor: not-allowed; }}
            .modal {{ display: none; position: fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.7); justify-content: center; align-items: center; }}
            .modal-card {{ background: #1e293b; border: 1px solid #334155; padding: 25px; border-radius: 8px; text-align: center; max-width: 340px; width: 100%; }}
            .modal-card button {{ width: 100%; padding: 12px; border: none; border-radius: 6px; margin-top: 10px; font-weight: bold; cursor: pointer; }}
        </style>
    </head>
    <body>
    <div class="container">
        <h2 style="margin-top:0;">{page_data['heading']}</h2>
        <p style="font-size: 13px; color: #94a3b8; margin-bottom: 20px;">{page_data['subheading']}</p>
        
        <textarea id="mainInput" placeholder="Paste text, document data, or messy raw scan here..."></textarea>
        <button id="processBtn" class="action-btn" onclick="openGatewayModal()">Fix Document Instantly</button>
    </div>

    <div id="gatewayModal" class="modal">
        <div class="modal-card">
            <h4 style="margin-top:0; font-size: 18px;">Unlock Instant Execution</h4>
            <p style="font-size: 13px; color: #94a3b8; margin-bottom: 20px;">Select access tier:</p>
            <button style="background: #10b981; color: white;" onclick="initializeCashPayment()">Pay ₦1,500 via Paystack</button>
            <button style="background: #1da1f2; color: white;" onclick="initializeViralBypass()">Share on X for Free Pass</button>
            <button style="background: #ef4444; color: white;" onclick="closeGatewayModal()">Cancel</button>
        </div>
    </div>

    <script>
        const RENDER_ROBOT_URL = window.location.origin + "/api/process";
        const PAYSTACK_KEY = "pk_live_YOUR_PAYSTACK_PUBLIC_KEY";

        function openGatewayModal() {{
            if(!document.getElementById('mainInput').value.trim()) return alert("Please enter input content.");
            document.getElementById('gatewayModal').style.display = 'flex';
        }}
        function closeGatewayModal() {{ document.getElementById('gatewayModal').style.display = 'none'; }}
        function toggleLoading(isLoading) {{
            const btn = document.getElementById('processBtn');
            btn.disabled = isLoading;
            btn.innerText = isLoading ? "⚡ Robot Processing..." : "Fix Document Instantly";
        }}

        function initializeCashPayment() {{
            closeGatewayModal();
            let handler = PaystackPop.setup({{
                key: PAYSTACK_KEY,
                email: 'user_' + Date.now() + '@utilityengine.com',
                amount: 150000,
                metadata: {{ action_type: 'document_rescue', user_input_text: document.getElementById('mainInput').value }},
                callback: function(response){{
                    toggleLoading(true);
                    executeTaskDirectly(response.reference);
                }}
            }});
            handler.openIframe();
        }}

        async function executeTaskDirectly(reference) {{
            try {{
                const res = await fetch(`${{RENDER_ROBOT_URL}}?reference=${{reference}}`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ action_type: 'document_rescue', data_input: document.getElementById('mainInput').value, paystack_ref: reference }})
                }});
                const data = await res.json();
                if (data.status === "success") {{
                    document.getElementById('mainInput').value = data.result;
                }}
            }} catch(e) {{
                console.error(e);
            }} finally {{
                toggleLoading(false);
            }}
        }}

        function initializeViralBypass() {{
            closeGatewayModal();
            const tweetText = encodeURIComponent("Just fixed portal document errors in 3 seconds using this utility:");
            window.open(`https://twitter.com/intent/tweet?text=${{tweetText}}&url=${{encodeURIComponent(window.location.href)}}`, '_blank');
            
            toggleLoading(true);
            fetch(RENDER_ROBOT_URL, {{
                method: 'POST',
                headers: {{ 
                    'Content-Type': 'application/json', 
                    'X-Viral-Token': '{VIRAL_SHARED_SECRET}' 
                }},
                body: JSON.stringify({{ action_type: 'document_rescue', data_input: document.getElementById('mainInput').value }})
            }}).then(res => res.json()).then(res => {{
                if(res.status === "success") document.getElementById('mainInput').value = res.result;
            }}).finally(() => toggleLoading(false));
        }}
    </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

@app.route('/dashboard')
def live_dashboard():
    """Unified Live Command Center Monitoring Dashboard."""
    dashboard_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Unified Command & Monitoring Center</title>
        <script src="https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"></script>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 30px; }
            .container { max-width: 1200px; margin: auto; }
            h1 { font-size: 26px; margin-bottom: 5px; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin: 25px 0; }
            .stat-card { background: #1e293b; border: 1px solid #334155; padding: 20px; border-radius: 10px; }
            .stat-card h3 { margin: 0; color: #94a3b8; font-size: 13px; text-transform: uppercase; }
            .stat-card p { margin: 10px 0 0 0; font-size: 28px; font-weight: bold; color: #10b981; }
            section { margin-top: 40px; }
            h2 { font-size: 18px; border-bottom: 2px solid #334155; padding-bottom: 8px; }
            .card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-top: 20px; }
            .lead-card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 20px; }
            .badge { background: #3b82f6; color: white; font-size: 11px; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
            .pitch-box { background: #0f172a; border-left: 3px solid #10b981; padding: 12px; margin-top: 15px; font-size: 13px; color: #cbd5e1; white-space: pre-wrap; }
            table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; margin-top: 15px; }
            th, td { padding: 12px 15px; text-align: left; font-size: 13px; border-bottom: 1px solid #334155; }
            th { background: #1e293b; color: #94a3b8; text-transform: uppercase; font-size: 11px; }
        </style>
    </head>
    <body>
    <div class="container">
        <h1>📊 Unified Command & Monitoring Center</h1>
        <p>Live real-time telemetry tracking for automated B2B leads and Paystack utility transactions.</p>
        
        <!-- Live Telemetry Counters -->
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Total Scraped Leads</h3>
                <p id="statLeads">0</p>
            </div>
            <div class="stat-card">
                <h3>Paid Transactions</h3>
                <p id="statTxs">0</p>
            </div>
            <div class="stat-card">
                <h3>Estimated Revenue</h3>
                <p id="statRev">₦0</p>
            </div>
        </div>

        <!-- Section 1: Live B2B Omni-Leads -->
        <section>
            <h2>🎯 Scraped B2B Leads & AI Pitches</h2>
            <div id="leadsContainer" class="card-grid"><p style="color:#94a3b8;">Loading live leads database...</p></div>
        </section>

        <!-- Section 2: Live Paystack & Viral Utility Transactions -->
        <section>
            <h2>💰 Live Utility Transactions</h2>
            <table>
                <thead>
                    <tr>
                        <th>Reference ID</th>
                        <th>Customer Email</th>
                        <th>Amount</th>
                        <th>Access Tier</th>
                        <th>Timestamp</th>
                    </tr>
                </thead>
                <tbody id="txTableBody">
                    <tr><td colspan="5" style="color:#94a3b8;">Loading live transactions...</td></tr>
                </tbody>
            </table>
        </section>
    </div>

    <script>
        async function fetchDashboardData() {
            try {
                const statsRes = await axios.get('/api/get-stats');
                const { total_leads, total_transactions, total_revenue, transactions } = statsRes.data;
                
                document.getElementById('statLeads').innerText = total_leads;
                document.getElementById('statTxs').innerText = total_transactions;
                document.getElementById('statRev').innerText = "₦" + total_revenue.toLocaleString();

                const txTable = document.getElementById('txTableBody');
                if (transactions.length === 0) {
                    txTable.innerHTML = `<tr><td colspan="5" style="color:#94a3b8;">No live transactions yet.</td></tr>`;
                } else {
                    txTable.innerHTML = transactions.map(t => `
                        <tr>
                            <td><code>${t.reference}</code></td>
                            <td>${t.customer_email || 'Anonymous / Viral'}</td>
                            <td>₦${Number(t.amount).toLocaleString()}</td>
                            <td><span style="color:${t.access_tier === 'paid_tier' ? '#10b981' : '#38bdf8'}">${t.access_tier}</span></td>
                            <td>${t.created_at}</td>
                        </tr>
                    `).join('');
                }

                const leadsRes = await axios.get('/api/get-leads');
                const leads = leadsRes.data.leads;
                const leadsContainer = document.getElementById('leadsContainer');
                
                if (leads.length === 0) {
                    leadsContainer.innerHTML = "<p style='color:#94a3b8;'>No live B2B leads scanned yet.</p>";
                } else {
                    leadsContainer.innerHTML = leads.map(l => `
                        <div class="lead-card">
                            <span class="badge">${l.vertical}</span>
                            <h3 style="margin:10px 0 5px 0;">${l.company_name}</h3>
                            <p style="margin:0; color:#38bdf8; font-size:13px;">📍 ${l.location} | 📧 ${l.contact_email}</p>
                            <p style="margin-top:10px; font-size:13px;"><strong>Bottleneck:</strong> ${l.pain_point}</p>
                            <div class="pitch-box"><strong>Generated Pitch:</strong><br>${l.ai_pitch}</div>
                        </div>
                    `).join('');
                }
            } catch (e) {
                console.error("Dashboard telemetry sync error:", e);
            }
        }

        fetchDashboardData();
        setInterval(fetchDashboardData, 10000);
    </script>
    </body>
    </html>
    """
    return render_template_string(dashboard_html)

@app.route('/api/process', methods=['POST', 'OPTIONS'])
def master_robotic_engine():
    if request.method == 'OPTIONS':
        return ('', 204, {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, X-Paystack-Signature, X-Viral-Token'
        })
    
    headers = {'Access-Control-Allow-Origin': '*'}
    
    try:
        viral_token = request.headers.get('X-Viral-Token')
        if viral_token and hmac.compare_digest(viral_token, VIRAL_SHARED_SECRET):
            payload = request.get_json(silent=True) or {}
            output = execute_robotic_task(payload.get("action_type", "document_rescue"), payload.get("data_input"))
            log_transaction(reference="viral_" + hashlib.md5(str(os.urandom(4)).encode()).hexdigest()[:8], email="viral_user@system", amount=0, tier="viral_tier")
            return jsonify({"status": "success", "access": "viral_tier", "result": output}), 200, headers

        paystack_signature = request.headers.get('X-Paystack-Signature')
        if paystack_signature and PAYSTACK_SECRET_KEY:
            request_body = request.get_data()
            computed_sig = hmac.new(bytes(PAYSTACK_SECRET_KEY, 'utf-8'), msg=request_body, digestmod=hashlib.sha512).hexdigest()
            
            if hmac.compare_digest(computed_sig, paystack_signature):
                payload = json.loads(request_body)
                if payload.get("event") == "charge.success":
                    data_block = payload.get("data", {})
                    metadata = data_block.get("metadata", {})
                    output = execute_robotic_task(metadata.get("action_type", "document_rescue"), metadata.get("user_input_text"))
                    
                    ref = data_block.get("reference")
                    email = data_block.get("customer", {}).get("email")
                    amt = data_block.get("amount", 150000) / 100
                    
                    log_transaction(reference=ref, email=email, amount=amt, tier="paid_tier")
                    send_telegram_alert(f"💰 **Live Payment Captured!**\nAmount: ₦{amt:,.2f}\nCustomer: {email}")
                    return jsonify({"status": "success", "access": "paid_tier", "result": output}), 200, headers

        payload = request.get_json(silent=True) or {}
        if payload.get("data_input"):
            output = execute_robotic_task(payload.get("action_type", "document_rescue"), payload.get("data_input"))
            ref = payload.get("paystack_ref", "direct_" + hashlib.md5(str(os.urandom(4)).encode()).hexdigest()[:8])
            
            log_transaction(reference=ref, email="client_direct@paystack", amount=1500, tier="paid_tier")
            return jsonify({"status": "success", "result": output}), 200, headers

        return jsonify({"status": "denied", "message": "Invalid auth or payload."}), 403, headers

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500, headers

@app.route('/api/ingest-lead', methods=['POST'])
def ingest_lead():
    auth_header = request.headers.get('X-Admin-Secret')
    if auth_header != ADMIN_SECRET:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    data = request.get_json() or {}
    vertical = data.get("vertical")
    company_name = data.get("company_name")
    location = data.get("location")
    contact_email = data.get("contact_email")
    pain_point = data.get("pain_point")

    prompt = f"""
    You are a high-conversion B2B growth closer.
    Vertical: {vertical}
    Company: {company_name} ({location})
    Bottleneck: {pain_point}
    Task: Write a cold outreach pitch under 90 words positioning our zero-friction micro-utility SaaS as the fix.
    """
    response = ai_client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
    ai_pitch = response.text

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO leads (vertical, company_name, location, contact_email, pain_point, ai_pitch) VALUES (%s, %s, %s, %s, %s, %s)",
        (vertical, company_name, location, contact_email, pain_point, ai_pitch)
    )
    conn.commit()
    cur.close()
    conn.close()

    send_telegram_alert(f"🎯 **New Live Lead Scanned!**\nCompany: {company_name}\nVertical: {vertical}")
    return jsonify({"status": "success", "message": "Lead saved to DB."}), 201

@app.route('/api/get-leads', methods=['GET'])
def get_leads():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Fixed: Removed non-existent 'status' column from selection
        cur.execute("SELECT id, vertical, company_name, location, contact_email, pain_point, ai_pitch, created_at FROM leads ORDER BY created_at DESC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({"status": "success", "leads": rows}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/get-stats', methods=['GET'])
def get_stats():
    """Returns telemetry metrics and live transaction logs for the dashboard."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT COUNT(*) AS count FROM leads;")
        total_leads = cur.fetchone()['count']
        
        cur.execute("SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS revenue FROM transactions;")
        tx_stats = cur.fetchone()
        total_transactions = tx_stats['count']
        total_revenue = float(tx_stats['revenue'])
        
        cur.execute("SELECT reference, customer_email, amount, access_tier, created_at FROM transactions ORDER BY created_at DESC LIMIT 15;")
        transactions = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({
            "total_leads": total_leads,
            "total_transactions": total_transactions,
            "total_revenue": total_revenue,
            "transactions": transactions
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def log_transaction(reference, email, amount, tier):
    """Safely records a transaction to PostgreSQL."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO transactions (reference, customer_email, amount, access_tier) VALUES (%s, %s, %s, %s) ON CONFLICT (reference) DO NOTHING;",
            (reference, email, amount, tier)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[DB Log Error]: {e}")

def execute_robotic_task(action_type, raw_data):
    if not raw_data:
        return "No input text provided."
    prompt = f"Strip system clutter and format into clean, structured application paragraphs:\n\n{raw_data}"
    response = ai_client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
    return response.text

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
