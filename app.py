import os,json,sqlite3,uuid,hmac
from datetime import datetime,timezone
from flask import Flask,request,jsonify
import requests
APP_NAME="Approved Task Executor"; VERSION="1.0.0"
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

def run_handler(p):
 typ=p.get("task_type");i=p.get("inputs",{})
 if typ=="text_cleanup":
  s=str(i.get("text",""));out=" ".join(s.split());return {"result_text":out,"characters_in":len(s),"characters_out":len(out)}
 if typ=="json_validate":
  try:return {"valid":True,"parsed":json.loads(i.get("json_text",""))}
  except Exception as e:return {"valid":False,"error":str(e)}
 raise ValueError("task_type_not_allowlisted")
@app.post("/tasks")
def create():
 p=request.get_json(silent=True) or {};e=p.get("engagement")
 if not isinstance(e,dict) or e.get("status")!="CLIENT_APPROVED" or e.get("approval",{}).get("approved") is not True:return jsonify(error="client_approval_required"),403
 typ=p.get("task_type");i=p.get("inputs",{})
 if typ not in ("text_cleanup","json_validate") or not isinstance(i,dict):return jsonify(error="allowlisted_task_type_and_inputs_required"),400
 rid=str(p.get("task_id") or uuid.uuid4());x={"task_id":rid,"engagement_id":e.get("engagement_id"),"scope":e["scope"],"task_type":typ,"inputs":i,"attempts":0,"status":"QUEUED","created_at":now()}
 save(rid,"QUEUED",x);return jsonify(x),201
@app.post("/tasks/<rid>/run")
def run(rid):
 init_db()
 with conn() as d:r=d.execute("SELECT status,payload FROM records WHERE id=?",(rid,)).fetchone()
 if not r:return jsonify(error="not_found"),404
 if r["status"] in ("COMPLETE","RUNNING"):return jsonify(error="task_not_runnable",status=r["status"]),409
 x=json.loads(r["payload"]);x["status"]="RUNNING";x["attempts"]+=1;save(rid,"RUNNING",x)
 try:x["output"]=run_handler(x);x["status"]="COMPLETE";x["finished_at"]=now();save(rid,"COMPLETE",x);return jsonify(task=x,handoff=forward(x))
 except Exception as e:x.update(status="FAILED_REVIEW",error=str(e),finished_at=now());save(rid,"FAILED_REVIEW",x);audit(rid,"failed",{"error":str(e)});return jsonify(task=x),422

if __name__=="__main__":
 init_db();app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
