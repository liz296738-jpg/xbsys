import sqlite3
c = sqlite3.connect("选班系统.db")
rows = c.execute("""select t.id,t.employee_no,t.name,t.created_at,
  (select count(*) from course_teachers ct where ct.teacher_id=t.id) as ncourse
  from teachers t order by t.id desc limit 12""").fetchall()
for r in rows: print(repr(r))
print("--- newest course_teachers ---")
for r in c.execute("select ct.course_id,ct.teacher_id,ct.imported_at,t.name,t.employee_no from course_teachers ct join teachers t on t.id=ct.teacher_id order by ct.imported_at desc limit 6"):
    print(repr(r))
print("--- courses ---")
for r in c.execute("select id,course_no,name from courses"): print(repr(r))
