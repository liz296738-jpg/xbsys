import sqlite3
c = sqlite3.connect("选班系统.db")
for r in c.execute("""select s.course_id, t.employee_no, t.name, c.name, c.plan_size, s.created_at
  from selections s join teachers t on t.id=s.teacher_id join classes c on c.id=s.class_id
  order by s.created_at"""):
    print(repr(r))
print("course2 selected:", c.execute("select count(*) from selections where course_id=2").fetchone()[0])
