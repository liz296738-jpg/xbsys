# -*- coding: utf-8 -*-
"""复现与验证：只填姓名能否登录 / 能否正常提交选班 / 提交后撤销不残留"""
import json, urllib.request, urllib.error, sys

BASE = 'http://127.0.0.1:8765'
PASS = FAIL = 0


def call(method, path, payload=None):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode('utf-8'))


def check(name, cond, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  OK  ', name)
    else:
        FAIL += 1
        print('  FAIL', name, extra)


COURSE = 'ZJ240010'
NAME = '丁梓'
NO = '1020180078'

print('== 1 只填姓名登录 ==')
r = call('POST', '/api/teacher/login', {'employee_no': '', 'name': NAME})
check('姓名登录成功', r.get('ok') and len(r.get('courses', [])) == 1, str(r)[:160])
r2 = call('POST', '/api/teacher/login', {'employee_no': NO, 'name': NAME})
check('工号+姓名仍正常', r2.get('ok') and len(r2.get('courses', [])) == 1, '')

print('== 2 姓名不全/不存在 ==')
x = call('POST', '/api/teacher/login', {'employee_no': '', 'name': NAME + '某'})
check('错误姓名有清晰提示', (not x.get('ok')) and '完全一致' in (x.get('error') or ''), str(x)[:160])

print('== 3 姓名登录后提交选班 ==')
cls = call('GET', '/api/teacher/classes?course_no=%s&no=%s&name=%s' % (COURSE, '', urllib.parse.quote(NAME)))
check('可选班级 254 个', cls.get('ok') and len(cls['classes']) == 254, str(len(cls.get('classes', []))))
two = [c for c in cls['classes'] if c['plan_size'] <= 40][:2]
sel = call('POST', '/api/teacher/select', {'course_no': COURSE, 'employee_no': '', 'name': NAME,
                                          'ids': [c['id'] for c in two], 'note': '联调测试'})
check('提交选班成功', sel.get('ok') and sel['stats']['classes'] == 2, str(sel)[:160])
mine = call('GET', '/api/teacher/mine?course_no=%s&no=%s&name=%s' % (COURSE, '', urllib.parse.quote(NAME)))
check('我的选班 2 个班', mine.get('ok') and len(mine['classes']) == 2, str(mine.get('stats')))
ov = call('GET', '/api/admin/overview?course_no=' + COURSE)
check('管理端看到该教师已选班', [t for t in ov['teachers'] if t['name'] == NAME][0]['n'] == 2, '')

print('== 4 撤销，恢复原状 ==')
un = call('POST', '/api/teacher/unselect', {'course_no': COURSE, 'employee_no': '', 'name': NAME,
                                           'ids': [c['id'] for c in two]})
ov = call('GET', '/api/admin/overview?course_no=' + COURSE)
check('撤销成功且无残留', un.get('ok') and ov['stats']['selected'] == 0
      and [t for t in ov['teachers'] if t['name'] == NAME][0]['n'] == 0, str(ov['stats']))

print('== 5 关系校验 ==')
check('课程教师数仍为 80', ov['stats']['teachers'] == 80, str(ov['stats']))
check('未选班教师 80', ov['stats']['teachers_unselected'] == 80, str(ov['stats']))

print('\n通过 %d 项，失败 %d 项' % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
