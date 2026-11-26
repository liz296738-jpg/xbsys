import sqlite3, re
from collections import Counter
c = sqlite3.connect("选班系统.db")
rows = c.execute("select id,employee_no,name from teachers order by id").fetchall()
print("total", len(rows))
bad = [r for r in rows if r[1] is None or str(r[1]).strip()=="" or not re.fullmatch(r"[0-9A-Za-z]+", str(r[1]))]
print("bad_no", len(bad))
for r in bad[:20]: print(repr(r))
print("--- sample ---")
for r in rows[:8]: print(repr(r))
print("--- name anomalies ---")
for r in rows:
    n = str(r[2])
    if n != n.strip() or "  " in n or any(ch in n for ch in ["\u3000", "\u200b", "\ufeff", "*"]): print("NAME", repr(r))
cnt = Counter(str(r[2]).strip() for r in rows)
print("dup_name", [k for k,v in cnt.items() if v>1][:10])
cnt2 = Counter(str(r[1]).strip() for r in rows if r[1])
print("dup_no", [k for k,v in cnt2.items() if v>1][:10])
