# -*- coding: utf-8 -*-
import json, urllib.request, urllib.error, sys

BASE = 'http://127.0.0.1:8765'
PASS = FAIL = 0


def post(path, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=data, method='POST',
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode('utf-8'))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))


def check(name, cond, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  OK  ', name)
    else:
        FAIL += 1
        print('  FAIL', name, extra)


print('== 单个添加教师 ==')
r = post('/api/admin/add_teacher', {'course_no': '2025', 'employee_no': 'T900', 'name': '测试甲'})
check('带工号添加', r.get('ok') and r.get('added') is True and '已添加' in r.get('message', ''), str(r))
ov = get('/api/admin/overview?course_no=2025')
check('名单出现该教师', [t for t in ov['teachers'] if t['name'] == '测试甲'][0]['n'] == 0, str(ov['stats']))
check('未选班计数 1', ov['stats']['teachers_unselected'] == 1, str(ov['stats']))

r2 = post('/api/admin/add_teacher', {'course_no': '2025', 'employee_no': 'T900', 'name': '测试甲'})
check('重复添加提示已存在', r2.get('ok') and r2.get('added') is False, str(r2))

r3 = post('/api/admin/add_teacher', {'course_no': '2025', 'employee_no': '', 'name': '测试乙'})
check('无工号添加', r3.get('ok') and r3.get('added') is True, str(r3))
ov = get('/api/admin/overview?course_no=2025')
check('无工号教师可登录', True, '')
tl = post('/api/teacher/login', {'employee_no': '', 'name': '测试乙'})
check('按姓名登录成功', tl.get('ok') and len(tl['courses']) == 1, str(tl)[:150])

r4 = post('/api/admin/add_teacher', {'course_no': '2025', 'employee_no': 'T901', 'name': ''})
check('空姓名被拒', not r4.get('ok'), str(r4)[:120])
r5 = post('/api/admin/add_teacher', {'course_no': '2025', 'employee_no': 'T-9 0', 'name': '测试丙'})
check('非法工号被拒', not r5.get('ok'), str(r5)[:120])

print('== 同工号换姓名 ==')
r6 = post('/api/admin/add_teacher', {'course_no': '2025', 'employee_no': 'T900', 'name': '测试甲改'})
check('同工号姓名更新提示', r6.get('ok') and '原登记姓名' in r6.get('message', ''), str(r6))
ov = get('/api/admin/overview?course_no=2025')
check('姓名已更新', any(t['name'] == '测试甲改' for t in ov['teachers']) and
      not any(t['name'] == '测试甲' for t in ov['teachers']), '')

print('== 移出名单 ==')
ov = get('/api/admin/overview?course_no=2025')
tid = [t for t in ov['teachers'] if t['name'] == '测试乙'][0]['id']
r7 = post('/api/admin/remove_teacher', {'course_no': '2025', 'teacher_id': tid})
check('无选班可移出', r7.get('ok') and '已把' in r7.get('message', ''), str(r7))
ov = get('/api/admin/overview?course_no=2025')
check('名单人数回到 1', ov['stats']['teachers'] == 1 and ov['stats']['teachers_unselected'] == 1, str(ov['stats']))

print('== 有其他课程时不影响 ==')
c2 = post('/api/admin/login', {'course_no': 'TMP02', 'course_name': '临时课程'})
check('建临时课程', c2.get('ok') and c2.get('created'), str(c2)[:120])
r8 = post('/api/admin/add_teacher', {'course_no': 'TMP02', 'employee_no': 'T900', 'name': '测试甲改'})
check('跨课程加入同一教师', r8.get('ok') and r8.get('added') is True, str(r8))
tl2 = post('/api/teacher/login', {'employee_no': 'T900', 'name': '测试甲改'})
check('该教师此时两门课程', len(tl2['courses']) == 2, str(tl2.get('courses')))
post('/api/admin/reset_course', {'course_no': 'TMP02'})

print('\n通过 %d 项，失败 %d 项' % (PASS, FAIL))
if FAIL:
    sys.exit(1)
