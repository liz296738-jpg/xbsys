import json, urllib.request, sqlite3
BASE="http://127.0.0.1:8765"
def post(p,pl):
    r=urllib.request.Request(BASE+p,data=json.dumps(pl).encode(),headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(r,timeout=10) as x: return json.loads(x.read().decode())
    except urllib.error.HTTPError as e: return json.loads(e.read().decode())
d=post("/api/teacher/login",{"employee_no":"1020180078","name":"丁梓"})
print("login ok", d.get("ok"), "token", (d.get("token") or "")[:8])
tok=d.get("token")
d2=post("/api/teacher/select",{"course_no":"ZJ240010","token":tok,"employee_no":"","name":"","ids":[],"note":""})
print("token only:", d2.get("error"))
d3=post("/api/teacher/select",{"course_no":"ZJ240010","token":tok,"employee_no":"999","name":"张三","ids":[],"note":""})
print("token beats wrong name:", d3.get("error"))
c=sqlite3.connect("选班系统.db")
print("sessions rows", c.execute("select count(*) from sessions").fetchone()[0])
