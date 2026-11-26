import io
p="app.py"; s=io.open(p,encoding="utf-8").read()
s = s.replace("""def available_classes(course_no, employee_no, name, q='', sort='name', order='asc'):
    c = require_course(course_no)
    t = find_teacher(employee_no, name)""",
"""def available_classes(course_no, employee_no, name, q='', sort='name', order='asc', token=''):
    c = require_course(course_no)
    t = resolve_teacher({'token': token, 'employee_no': employee_no, 'name': name})""")
s = s.replace("""def my_selections(course_no, employee_no, name):
    c = require_course(course_no)
    t = find_teacher(employee_no, name)""",
"""def my_selections(course_no, employee_no, name, token=''):
    c = require_course(course_no)
    t = resolve_teacher({'token': token, 'employee_no': employee_no, 'name': name})""")
s = s.replace("""def select_classes(course_no, employee_no, name, ids, note=''):
    c = require_course(course_no)
    t = find_teacher(employee_no, name)""",
"""def select_classes(course_no, employee_no, name, ids, note='', token=''):
    c = require_course(course_no)
    t = resolve_teacher({'token': token, 'employee_no': employee_no, 'name': name})""")
s = s.replace("""def unselect_classes(course_no, employee_no, name, ids):
    c = require_course(course_no)
    t = find_teacher(employee_no, name)""",
"""def unselect_classes(course_no, employee_no, name, ids, token=''):
    c = require_course(course_no)
    t = resolve_teacher({'token': token, 'employee_no': employee_no, 'name': name})""")
s = s.replace("    st = my_selections(course_no, employee_no, name)",
              "    st = my_selections(course_no, employee_no, name, token)")
s = s.replace("""def save_note(course_no, employee_no, name, class_id, note):
    c = require_course(course_no)
    t = find_teacher(employee_no, name)""",
"""def save_note(course_no, employee_no, name, class_id, note, token=''):
    c = require_course(course_no)
    t = resolve_teacher({'token': token, 'employee_no': employee_no, 'name': name})""")
io.open(p,"w",encoding="utf-8").write(s)
print("ok")
