import io
p="app.py"; s=io.open(p,encoding="utf-8").read()
s = s.replace("""                self.g(qs, 'course_no'), self.g(qs, 'no'), self.g(qs, 'name'),
                self.g(qs, 'q'), self.g(qs, 'sort'), self.g(qs, 'order'))})""",
"""                self.g(qs, 'course_no'), self.g(qs, 'no'), self.g(qs, 'name'),
                self.g(qs, 'q'), self.g(qs, 'sort'), self.g(qs, 'order'), self.g(qs, 'token'))})""")
s = s.replace("""                self.g(qs, 'course_no'), self.g(qs, 'no'), self.g(qs, 'name'))})""",
"""                self.g(qs, 'course_no'), self.g(qs, 'no'), self.g(qs, 'name'), self.g(qs, 'token'))})""")
s = s.replace("""                payload.get('course_no'), payload.get('employee_no'), payload.get('name'),
                ids, payload.get('note', ''))})""",
"""                payload.get('course_no'), payload.get('employee_no'), payload.get('name'),
                ids, payload.get('note', ''), payload.get('token'))})""")
s = s.replace("""                payload.get('course_no'), payload.get('employee_no'), payload.get('name'), ids)})""",
"""                payload.get('course_no'), payload.get('employee_no'), payload.get('name'), ids,
                payload.get('token'))})""")
s = s.replace("""                payload.get('course_no'), payload.get('employee_no'), payload.get('name'),
                int(payload.get('class_id')), payload.get('note', ''))})""",
"""                payload.get('course_no'), payload.get('employee_no'), payload.get('name'),
                int(payload.get('class_id')), payload.get('note', ''), payload.get('token'))})""")
io.open(p,"w",encoding="utf-8").write(s)
print("ok")
