import os,json,sqlite3,uuid,hmac
from datetime import datetime,timezone
from flask import Flask,request,jsonify
import requests
APP_NAME="Value-to-Money Filter"; VERSION="1.0.0"
DB=os.getenv("DATABASE_PATH","./data/service.sqlite3")
TOKEN=os.getenv("API_TOKEN",""); NEXT=os.getenv("NEXT_STAGE_URL",""); NEXT_TOKEN=os.getenv("NEXT_STAGE_TOKEN","")
app=Flask(__name__)
def now(): return datetime.now(timezone.utc).isoformat()
def conn():
 os.makedirs(os.path.dirname(os.path.abspath(DB)),exist_ok=True)
 d=sqlite3.connect(DB,timeout=20); d.row_factory=sqlite3.Row; d.execute("PRAGMA journal_mode=WAL"); return d
def init_db():
 with conn() as d:
  d.execute("CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,status TEXT,payload TEXT,created TEXT,updated TEXT)")
  d.execute("CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,record_id TEXT,event TEXT,detail TEXT,at TEXT)")
def audit(r,e,x):
 with conn() as d:d.execute("INSERT INTO audit(record_id,event,detail,at) VALUES(?,?,?,?)",(r,e,json.dumps(x),now()))
def auth():
 if not TOKEN:return True
 v=request.headers.get("Authorization",""); v=v[7:].strip() if v.lower().startswith("bearer ") else v
 return hmac.compare_digest(v,TOKEN)
@app.before_request
def guard():
 if request.method in ("POST","PUT","PATCH","DELETE") and not auth():return jsonify(error="unauthorized"),401
def save(r,s,p):
 t=now()
 with conn() as d:
  old=d.execute("SELECT created FROM records WHERE id=?",(r,)).fetchone(); c=old["created"] if old else t
  d.execute("INSERT INTO records VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,payload=excluded.payload,updated=excluded.updated",(r,s,json.dumps(p,ensure_ascii=False),c,t))
 audit(r,"saved",{"status":s});return {"id":r,"status":s,"payload":p,"created_at":c,"updated_at":t}
def forward(p):
 if not NEXT:return {"forwarded":False,"reason":"NEXT_STAGE_URL_not_configured"}
 h={"Content-Type":"application/json"}
 if NEXT_TOKEN:h["Authorization"]="Bearer "+NEXT_TOKEN
 try:
  r=requests.post(NEXT,json=p,headers=h,timeout=12);return {"forwarded":r.ok,"http_status":r.status_code,"response":r.text[:500]}
 except requests.RequestException as e:return {"forwarded":False,"error":str(e)}
@app.get("/")
def index():return jsonify(service=APP_NAME,version=VERSION,health="/health")
@app.get("/health")
def health():
 init_db()
 with conn() as d:n=d.execute("SELECT COUNT(*) FROM records").fetchone()[0]
 return jsonify(service=APP_NAME,version=VERSION,status="ok",records=n,at=now())
@app.get("/records")
def records():
 init_db();limit=min(max(int(request.args.get("limit","50")),1),200)
 with conn() as d:rows=d.execute("SELECT id,status,created,updated FROM records ORDER BY created DESC LIMIT ?",(limit,)).fetchall()
 return jsonify(records=[dict(x) for x in rows])
@app.get("/records/<rid>")
def get_record(rid):
 init_db()
 with conn() as d:x=d.execute("SELECT * FROM records WHERE id=?",(rid,)).fetchone()
 if not x:return jsonify(error="not_found"),404
 return jsonify(id=x["id"],status=x["status"],payload=json.loads(x["payload"]),created_at=x["created"],updated_at=x["updated"])

GATES=["payment_evidence","repeated_paid_demand","independent_buyers","independent_sellers","exact_task_alignment","competitor_gap","measurable_deliverable","automation_feasible","lawful_data_access","acquisition_path","unit_economics"]
def assess(p):
 e=p.get("evidence",{});checks={g:e.get(g) is True for g in GATES};missing=[g for g,v in checks.items() if not v]
 net=p.get("estimated_net_value_usd")
 if not isinstance(net,(int,float)) or net<=0:missing.append("positive_verified_net_value_usd")
 if not isinstance(p.get("citations"),list) or not p["citations"]:missing.append("source_citations")
 status="QUALIFIED" if not missing else ("REJECTED" if p.get("reject_reason") else "INVESTIGATE")
 return {"candidate_id":p.get("candidate_id") or str(uuid.uuid4()),"status":status,"gates":checks,"missing_evidence":missing,"candidate":p,"note":"Only checked evidence should set gates true."}
@app.post("/qualify")
def qualify():
 p=request.get_json(silent=True) or {}
 if not isinstance(p,dict):return jsonify(error="json_object_required"),400
 x=assess(p);rid=str(x["candidate_id"]);save(rid,x["status"],x);audit(rid,"qualification",{"status":x["status"]})
 if x["status"]=="QUALIFIED":x["handoff"]=forward(x)
 return jsonify(x)
@app.post("/batch")
def batch():
 p=request.get_json(silent=True) or {};items=p.get("candidates",[])
 if not isinstance(items,list):return jsonify(error="candidates_must_be_array"),400
 return jsonify(results=[assess(x) for x in items[:100] if isinstance(x,dict)])

if __name__=="__main__":
 init_db();app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
