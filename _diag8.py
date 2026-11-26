import sqlite3
c = sqlite3.connect("选班系统.db")
print("total", c.execute("select count(*) from teachers").fetchone()[0])
for r in c.execute("select id,employee_no,name,created_at,(select count(*) from course_teachers ct where ct.teacher_id=t.id) from teachers t order by id desc limit 5"):
    print(repr(r))
