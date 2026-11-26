import sqlite3
c = sqlite3.connect("选班系统.db")
print("sel", c.execute("select count(*) from selections").fetchone()[0])
print("unsel_teachers", c.execute("select count(*) from course_teachers ct where ct.course_id=2 and ct.teacher_id not in (select teacher_id from selections where course_id=2)").fetchone()[0])
