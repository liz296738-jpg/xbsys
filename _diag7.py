import sqlite3
from collections import Counter
c = sqlite3.connect("选班系统.db")
rows = c.execute("select employee_no,name from teachers where employee_no<>'' order by employee_no").fetchall()
print("n", len(rows))
print("len_dist", Counter(len(r[0]) for r in rows))
short = [r for r in rows if len(r[0]) < 8]
print("short_nos", short)
zero_lead = [r for r in rows if r[0].startswith('0')]
print("zero_lead", zero_lead)
