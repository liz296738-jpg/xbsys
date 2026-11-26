import json, sqlite3, urllib.request
BASE="http://127.0.0.1:8765"; C="ZJ240010"
def post(path,payload):
    req=urllib.request.Request(BASE+path,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=10) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e: return json.loads(e.read().decode())
c=sqlite3.connect("选班系统.db")
rows=c.execute("select employee_no,name from teachers").fetchall()
bad=[]
for no,nm in rows:
    d=post("/api/teacher/login",{"employee_no":no,"name":nm})
    if not d.get("ok"):
        bad.append((no,nm,"login",d.get("error"))); continue
    d2=post("/api/teacher/select",{"course_no":C,"employee_no":no,"name":nm,"ids":[],"note":""})
    m=str(d2.get("error") or d2.get("message") or "")
    if "工号" in m or "姓名" in m:
        bad.append((no,nm,"select",m))
print("checked",len(rows),"bad",len(bad))
for b in bad[:15]: print(b)
