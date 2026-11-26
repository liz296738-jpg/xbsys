import io
p="teacher.js"; s=io.open(p,encoding="utf-8").read()
s = s.replace("""const state = {
  teacher: { no: '', name: '' },""","""const state = {
  teacher: { no: '', name: '' },
  token: '',""")
s = s.replace("""function ident() {
  return { course_no: state.course ? state.course.course_no : '',
           no: state.teacher.no, name: state.teacher.name };
}""","""function ident() {
  return { course_no: state.course ? state.course.course_no : '',
           no: state.teacher.no, name: state.teacher.name, token: state.token };
}""")
s = s.replace("""function saveSaved(lastCourseNo) {
  localStorage.setItem(STORE_KEY, JSON.stringify({
    no: state.teacher.no, name: state.teacher.name,""","""function saveSaved(lastCourseNo) {
  localStorage.setItem(STORE_KEY, JSON.stringify({
    no: state.teacher.no, name: state.teacher.name, token: state.token,""")
s = s.replace("""    state.teacher = { no: d.teacher.employee_no, name: d.teacher.name };""",
"""    state.teacher = { no: d.teacher.employee_no, name: d.teacher.name };
    state.token = d.token || '';""")
s = s.replace("""    '&name=' + encodeURIComponent(state.teacher.name) +
    '&q=' +""","""    '&name=' + encodeURIComponent(state.teacher.name) +
    '&token=' + encodeURIComponent(state.token) +
    '&q=' +""")
s = s.replace("""    '&name=' + encodeURIComponent(state.teacher.name));""",
"""    '&name=' + encodeURIComponent(state.teacher.name) +
    '&token=' + encodeURIComponent(state.token));""")
io.open(p,"w",encoding="utf-8").write(s)
print("patched")
