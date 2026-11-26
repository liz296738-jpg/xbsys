import json, sqlite3, urllib.request
c = sqlite3.connect("选班系统.db")
print("teachers", c.execute("select count(*) from teachers").fetchone()[0])
print("selections", c.execute("select count(*) from selections").fetchone()[0])
for r in c.execute("select t.name,count(*) from selections s join teachers t on t.id=s.teacher_id group by t.name"):
    print("sel_by", r)
print("dingzi", c.execute("select count(*) from selections s join teachers t on t.id=s.teacher_id where t.name='丁梓'").fetchone()[0])
print("sessions", c.execute("select count(*) from sessions").fetchone()[0])
# 兼容旧页面：不带 token 提交仍可用
BASE="http://127.0.0.1:8765"
def post(p,pl):
    r=urllib.request.Request(BASE+p,data=json.dumps(pl).encode(),headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(r,timeout=10) as x: return json.loads(x.read().decode())
    except urllib.error.HTTPError as e: return json.loads(e.read().decode())
d=post("/api/teacher/select",{"course_no":"ZJ240010","employee_no":"1020180078","name":"丁梓","ids":[],"note":""})
print("legacy no-token:", d.get("error"))
