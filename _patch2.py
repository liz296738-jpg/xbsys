import io
p = "_verify_strict_login.py"
s = io.open(p, encoding="utf-8").read()
s = s.replace("check('姓名不完整被拒绝', (not d.get('ok')) and ('不一致' in msg(d)), d)",
              "check('姓名不完整被拒绝', (not d.get('ok')) and ('登记的姓名是' in msg(d)), d)")
s = s.replace("d = post('/api/teacher/login', {'employee_no': '1020030090', 'name': '李代波'})\ncheck('工号与姓名不属于同一人被拒绝', not d.get('ok'), d)",
              "d = post('/api/teacher/login', {'employee_no': '1020030090', 'name': '李代波'})\ncheck('工号与姓名不属于同一人被拒绝', (not d.get('ok')) and ('1020170058' in msg(d)), d)")
io.open(p, "w", encoding="utf-8").write(s)
print("patched")
