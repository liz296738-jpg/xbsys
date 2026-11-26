# -*- coding: utf-8 -*-
"""严格双字段登录 + 单个添加关联 自测（跑在真实库上，结束后清理测试教师）"""
import json
import sqlite3
import urllib.request
from urllib.parse import quote

BASE = 'http://127.0.0.1:8765'
COURSE = 'ZJ240010'
DB = '选班系统.db'
TMP_NO = '9999990001'
TMP_NAME = '测试教师甲'

ok_cnt = 0
fail = []

_conn = sqlite3.connect(DB)
T_BEFORE = _conn.execute('SELECT COUNT(*) FROM teachers').fetchone()[0]
SEL_BEFORE = _conn.execute("SELECT COUNT(*) FROM selections WHERE course_id="
                           "(SELECT id FROM courses WHERE course_no=?)", (COURSE,)).fetchone()[0]
_conn.close()


def check(desc, cond, extra=''):
    global ok_cnt
    if cond:
        ok_cnt += 1
        print('  [OK]', desc)
    else:
        fail.append(desc)
        print('  [FAIL]', desc, extra)


def msg(d):
    return str(d.get('message') or d.get('error') or '')


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode('utf-8'),
                                headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode('utf-8'))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))


print('== 1. 严格匹配：正确工号+姓名 ==')
d = post('/api/teacher/login', {'employee_no': '1020030090', 'name': '唐赫渊'})
check('正确工号+姓名可登录', d.get('ok') and d.get('teacher', {}).get('employee_no') == '1020030090', d)
check('登录后带课程列表', d.get('ok') and len(d.get('courses', [])) >= 1, d.get('courses'))

print('== 2. 规范化容错（全角/空格/撇号）==')
d = post('/api/teacher/login', {'employee_no': '１０２００３００９０', 'name': '唐赫渊'})
check('全角工号可登录', d.get('ok'), d)
d = post('/api/teacher/login', {'employee_no': " '1020030090", 'name': ' 唐赫渊 '})
check('工号带撇号空格、姓名带空格可登录', d.get('ok'), d)
d = post('/api/teacher/login', {'employee_no': '1020030090', 'name': '唐 赫 渊'})
check('姓名中间带空格可登录', d.get('ok'), d)

print('== 3. 严格拒绝 ==')
d = post('/api/teacher/login', {'employee_no': '', 'name': '唐赫渊'})
check('只填姓名被拒绝', (not d.get('ok')) and ('工号' in msg(d)), d)
d = post('/api/teacher/login', {'employee_no': '1020030090', 'name': ''})
check('只填工号被拒绝', (not d.get('ok')) and ('姓名' in msg(d)), d)
d = post('/api/teacher/login', {'employee_no': '1020030090', 'name': '唐赫'})
check('姓名不完整被拒绝', (not d.get('ok')) and ('登记的姓名是' in msg(d)), d)
d = post('/api/teacher/login', {'employee_no': '1020030091', 'name': '唐赫渊'})
check('工号错一位被拒绝并提示正确工号', (not d.get('ok')) and ('1020030090' in msg(d)), d)
d = post('/api/teacher/login', {'employee_no': '1020030090', 'name': '李代波'})
check('工号与姓名不属于同一人被拒绝', (not d.get('ok')) and ('1620190014' in msg(d)), d)

print('== 4. 单个添加即建立课程关联 ==')
d = post('/api/admin/add_teacher', {'course_no': COURSE, 'employee_no': TMP_NO, 'name': TMP_NAME})
check('单个添加成功', d.get('ok'), d)
d = get('/api/admin/overview?course_no=' + COURSE)
names = [t['name'] for t in d.get('teachers', [])]
check('添加后立即出现在本课程名单', TMP_NAME in names, names[-5:])
d = post('/api/teacher/login', {'employee_no': TMP_NO, 'name': TMP_NAME})
check('新增教师用工号+姓名可登录', d.get('ok') and d.get('teacher', {}).get('name') == TMP_NAME, d)
check('新增教师只关联本课程', d.get('ok') and [c['course_no'] for c in d.get('courses', [])] == [COURSE],
      d.get('courses'))
d = get('/api/teacher/classes?course_no=%s&no=%s&name=%s' % (COURSE, TMP_NO, quote(TMP_NAME)))
check('新增教师能看到可选班级', d.get('ok') and len(d.get('classes', [])) > 0, len(d.get('classes', [])))

print('== 5. 缺少工号被拒绝（单个添加与导入一致）==')
d = post('/api/admin/add_teacher', {'course_no': COURSE, 'employee_no': '', 'name': '无工号老师'})
check('单个添加缺工号被拒绝', (not d.get('ok')) and ('工号' in msg(d)), d)

print('== 6. 登录日志 ==')
d = get('/api/admin/login_log')
items = d.get('items', [])
check('登录日志可读取', d.get('ok') and len(items) >= 6, len(items))
check('日志记录失败原因', any((not i['ok']) and i['detail'] for i in items), items[:1])
check('日志记录输入内容', any(i['input_no'] == '1020030090' for i in items), items[:2])

print('== 7. 清理测试数据 ==')
d = get('/api/admin/overview?course_no=' + COURSE)
tid = next((t['id'] for t in d['teachers'] if t['name'] == TMP_NAME), None)
if tid:
    r = post('/api/admin/remove_teacher', {'course_no': COURSE, 'teacher_id': tid})
    check('移出测试教师', r.get('ok'), r)
c = sqlite3.connect(DB)
c.execute('DELETE FROM teachers WHERE employee_no=?', (TMP_NO,))
c.commit()
check('删除测试教师记录', c.execute('SELECT COUNT(*) FROM teachers WHERE employee_no=?', (TMP_NO,)).fetchone()[0] == 0)
left = c.execute('SELECT COUNT(*) FROM teachers').fetchone()[0]
sel = c.execute("SELECT COUNT(*) FROM selections WHERE course_id=(SELECT id FROM courses WHERE course_no=?)",
                (COURSE,)).fetchone()[0]
c.close()
check('教师总数未被测试改动', left == T_BEFORE, '%d -> %d' % (T_BEFORE, left))
check('选班记录未被测试改动', sel == SEL_BEFORE, '%d -> %d' % (SEL_BEFORE, sel))

print('\n通过 %d 项，失败 %d 项' % (ok_cnt, len(fail)))
if fail:
    print('失败：', fail)
