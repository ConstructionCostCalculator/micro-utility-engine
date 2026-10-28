import os,json,sqlite3,uuid,hmac
from datetime import datetime,timezone
from flask import Flask,request,jsonify
import requests
APP_NAME="Global Utility Scanner"; VERSION="1.0.0"
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

import re,hashlib,urllib.parse,xml.etree.ElementTree as ET
KEYS={"ecommerce_online_selling":["shopify","woocommerce","product feed","catalog","sku","listing","inventory"],
"seo":["seo","indexing","search console","schema markup","crawl error"],
"business_operations":["spreadsheet","manual process","invoice","reconcile","copy paste"],
"software_api":["api error","webhook","integration","bug","timeout","failed request"],
"content_creator":["transcript","subtitle","caption","thumbnail"],
"customer_service":["support ticket","refund","customer complaint","review"],
"research":["public data","tender","grant","monitor prices"]}
PAIN=["broken","frustrating","doesn't work","failed","error","bug","manual","tedious","missing","poor","unusable","wish"]
REPEAT=["daily","weekly","monthly","every time","repeatedly","again","recurring","each week"]
MONEY=["hire","freelancer","paid","budget","price","client","invoice","contract"]
def score(text):
 t=text.lower(); domains=[k for k,v in KEYS.items() if any(w in t for w in v)]
 signals={"pain":sum(w in t for w in PAIN),"recurrence":sum(w in t for w in REPEAT),"commercial":sum(w in t for w in MONEY)}
 return {"domains":domains or ["unclassified"],"signals":signals,"score":min(100,signals["pain"]*9+signals["recurrence"]*13+signals["commercial"]*10),"evidence_status":"discovery_only_not_demand_proof"}
def collect(url,source):
 r=requests.get(url,timeout=12,headers={"User-Agent":"SolveEaseResearchBot/1.0"});r.raise_for_status();data=r.json() if "json" in r.headers.get("content-type","") or r.text.lstrip().startswith("{") else None;out=[]
 if source=="hn":
  for x in data.get("hits",[]):out.append({"source":source,"url":x.get("url") or "https://news.ycombinator.com/item?id="+str(x.get("objectID","")),"title":x.get("title") or x.get("story_title") or "","text":(x.get("title") or "")+" "+(x.get("comment_text") or x.get("story_text") or "")})
 elif source=="github":
  for x in data.get("items",[]):out.append({"source":source,"url":x.get("html_url",""),"title":x.get("title",""),"text":x.get("title","")+" "+(x.get("body") or "")[:3000]})
 else:
  root=ET.fromstring(r.text)
  for x in root.findall(".//item")[:30]:
   out.append({"source":source,"url":x.findtext("link",""),"title":x.findtext("title",""),"text":x.findtext("title","")+" "+x.findtext("description","")})
 return out
def discover():
 out=[];n=int(os.getenv("SCANNER_MAX_ITEMS","20"))
 for q in [x.strip() for x in os.getenv("HN_QUERIES","broken workflow,manual spreadsheet,Shopify catalog error,SEO indexing problem").split(",") if x.strip()][:6]:
  u="https://hn.algolia.com/api/v1/search_by_date?"+urllib.parse.urlencode({"query":q,"tags":"story,comment","hitsPerPage":n})
  try:out+=collect(u,"hn")
  except Exception as e:audit("scanner","source_error",{"url":u,"error":str(e)[:250]})
 for q in [x.strip() for x in os.getenv("GITHUB_QUERIES","is:issue label:bug webhook,Shopify catalog,SEO indexing").split(",") if x.strip()][:5]:
  u="https://api.github.com/search/issues?"+urllib.parse.urlencode({"q":q,"sort":"updated","per_page":n})
  try:
   h={"Accept":"application/vnd.github+json","User-Agent":"SolveEaseResearchBot/1.0"}
   if os.getenv("GITHUB_TOKEN"):h["Authorization"]="Bearer "+os.getenv("GITHUB_TOKEN")
   r=requests.get(u,headers=h,timeout=12);r.raise_for_status();data=r.json()
   for x in data.get("items",[]):out.append({"source":"github","url":x.get("html_url",""),"title":x.get("title",""),"text":x.get("title","")+" "+(x.get("body") or "")[:3000]})
  except Exception as e:audit("scanner","source_error",{"url":u,"error":str(e)[:250]})
 seen=set();unique=[]
 for x in out:
  key=x.get("url") or hashlib.sha256(x.get("text","").encode()).hexdigest()
  if key in seen:continue
  seen.add(key);x["finding_id"]="f_"+hashlib.sha256(key.encode()).hexdigest()[:20];x.update(score(x.get("text","")));unique.append(x)
 return unique
def stage():
 items=discover();init_db()
 with conn() as d:
  d.execute("CREATE TABLE IF NOT EXISTS scan_runs(id TEXT,at TEXT,count INTEGER)")
  d.execute("INSERT INTO scan_runs VALUES(?,?,?)",(str(uuid.uuid4()),now(),len(items)))
  for x in items:d.execute("INSERT INTO records VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,status=excluded.status,updated=excluded.updated",(x["finding_id"],"DISCOVERED",json.dumps(x),now(),now()))
 return {"status":"complete","count":len(items),"findings":items[:100],"warning":"signals are not verified buyer demand"}
@app.post("/scan")
def scan():return jsonify(stage())
@app.get("/findings")
def findings():
 init_db()
 with conn() as d:rows=d.execute("SELECT id,payload FROM records ORDER BY updated DESC LIMIT 100").fetchall()
 return jsonify(findings=[{"id":x["id"],"payload":json.loads(x["payload"])} for x in rows])

if __name__=="__main__":
 init_db();app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
