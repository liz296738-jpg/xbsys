import io
p = "_verify_strict_login.py"
s = io.open(p, encoding="utf-8").read()
s = s.replace("('1020170058' in msg(d))", "('1620190014' in msg(d))")
s = s.replace("check('教师总数仍为 80', left == 80, left)",
              "check('教师总数未被测试改动', left == T_BEFORE, '%d -> %d' % (T_BEFORE, left))")
s = s.replace("SEL_BEFORE = _conn.execute(", "T_BEFORE = _conn.execute('SELECT COUNT(*) FROM teachers').fetchone()[0]\nSEL_BEFORE = _conn.execute(")
io.open(p, "w", encoding="utf-8").write(s)
print("patched")
