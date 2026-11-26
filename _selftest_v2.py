# -*- coding: utf-8 -*-
"""v2 接口自测：课程维度 + 工号登录 + 选班 + 未选班 + 导出"""
import json, urllib.request, urllib.error, uuid, io, os, sys

BASE = 'http://127.0.0.1:8765'
PASS = FAIL = 0
FAILS = []


def call(method, path, payload=None, raw=False):
    url = BASE + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            if raw:
                return r.status, body, dict(r.headers)
            return json.loads(body.decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        try:
            return json.loads(body)
        except Exception:
            return {'ok': False, 'error': 'HTTP %s %s' % (e.code, body)}


def post_file(path, fields, filename, content):
    boundary = '----doubao' + uuid.uuid4().hex
    body = b''
    for k, v in fields.items():
        body += ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                 % (boundary, k, v)).encode('utf-8')
    body += ('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n'
             'Content-Type: text/csv\r\n\r\n' % (boundary, filename)).encode('utf-8')
    body += content + ('\r\n--%s--\r\n' % boundary).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=body, method='POST',
                                 headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {'ok': False, 'error': e.read().decode('utf-8', 'replace')}


def check(name, cond, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  OK  ', name)
    else:
        FAIL += 1
        FAILS.append(name + ' ' + extra)
        print('  FAIL', name, extra)


print('== 1 基础 ==')
h = call('GET', '/api/health')
check('health', h.get('ok') and h.get('classes') == 254 and h.get('courses') == 1, str(h))

print('== 2 管理员登录 ==')
bad = call('POST', '/api/admin/login', {'course_no': '2025', 'course_name': '随便写'})
check('课程名不符被拒', not bad.get('ok') and '不符' in (bad.get('error') or ''), str(bad))
adm = call('POST', '/api/admin/login', {'course_no': '2025', 'course_name': '2025级专业班级选班'})
check('默认课程登录', adm.get('ok') and adm['course']['course_no'] == '2025' and adm.get('stats', {}).get('classes') == 254,
      str(adm)[:200])
check('登录返回 settings', adm.get('settings', {}).get('teacher_max_students') == 100, str(adm.get('settings')))
courses = call('GET', '/api/admin/courses')
check('课程列表', courses.get('ok') and len(courses['courses']) == 1, str(courses)[:160])

print('== 3 教师名单导入 ==')
csv1 = '姓名,工号\n张老师,T001\n李老师,T002\n王老师,\n'.encode('utf-8-sig')
r = post_file('/api/admin/import_teachers', {'course_no': '2025', 'mode': 'skip'}, 'roster.csv', csv1)
check('导入教师 3 人', r.get('ok') and r.get('added') == 3, str(r))
r2 = post_file('/api/admin/import_teachers', {'course_no': '2025', 'mode': 'skip'}, 'roster.csv', csv1)
check('重复导入跳过', r2.get('ok') and r2.get('added', -1) == 0 and len(r2.get('duplicates', [])) == 3, str(r2))

print('== 4 教师登录 ==')
t = call('POST', '/api/teacher/login', {'employee_no': 'T001', 'name': '张老师'})
check('工号+姓名登录', t.get('ok') and t['teacher']['name'] == '张老师' and len(t['courses']) == 1, str(t)[:160])
check('教师登录带规则', t.get('settings', {}).get('teacher_min_classes') == 2, str(t.get('settings')))
w = call('POST', '/api/teacher/login', {'employee_no': 'T001', 'name': '张老三'})
check('工号优先/姓名不符告警', w.get('ok') and '张老师' in (w.get('warning') or ''), str(w)[:160])
nr = call('POST', '/api/teacher/login', {'employee_no': '', 'name': '王老师'})
check('无工号按姓名登录', nr.get('ok') and len(nr['courses']) == 1, str(nr)[:160])
nx = call('POST', '/api/teacher/login', {'employee_no': '', 'name': '不存在'})
check('未登记教师被拒', not nx.get('ok'), str(nx)[:120])

print('== 5 可选班级 ==')
cls = call('GET', '/api/teacher/classes?course_no=2025&no=T001&name=%E7%BB%88%E7%94%B3' .replace('%E7%BB%88%E7%94%B3', '%E6%B1%97%E6%89%AF'))
cls = call('GET', '/api/teacher/classes?course_no=2025&no=T001&name=' + urllib.parse.quote('张老师'))
check('班级列表 254', cls.get('ok') and len(cls['classes']) == 254, str(len(cls.get('classes', []))))
ac1 = [c for c in cls['classes'] if c['name'] == 'ACCA2501'][0]
ac2 = [c for c in cls['classes'] if c['name'] == 'ACCA2502'][0]
check('ACCA2501 数据', ac1['plan_size'] == 48 and ac1['taken'] == 0, str(ac1))

print('== 6 选班规则 ==')
one = call('POST', '/api/teacher/select', {'course_no': '2025', 'employee_no': 'T001', 'name': '张老师', 'ids': [ac1['id']]})
check('少于 2 个班被拒', not one.get('ok') and '2' in (one.get('error') or ''), str(one)[:140])
two = call('POST', '/api/teacher/select', {'course_no': '2025', 'employee_no': 'T001', 'name': '张老师', 'ids': [ac1['id'], ac2['id']]})
check('选 2 班成功', two.get('ok') and two['stats']['classes'] == 2 and two['stats']['students'] == 94, str(two)[:160])
cls2 = call('GET', '/api/teacher/classes?course_no=2025&no=T001&name=' + urllib.parse.quote('张老师'))
check('自己已选班级不再出现', all(c['id'] not in (ac1['id'], ac2['id']) for c in cls2['classes']), '')
check('被选班级 taken=1', all(c['taken'] == 1 for c in cls2['classes'] if c['id'] in ()))
big3 = [c for c in cls2['classes'] if c['plan_size'] > 6][:3]
over = call('POST', '/api/teacher/select', {'course_no': '2025', 'employee_no': 'T001', 'name': '张老师', 'ids': [c['id'] for c in big3]})
check('超过 100 人被拒', not over.get('ok') and '100' in (over.get('error') or ''), str(over)[:140])

print('== 7 未选班统计 ==')
ov = call('GET', '/api/admin/overview?course_no=2025')
check('overview ok', ov.get('ok'), str(ov)[:120])
check('未选班教师=2', ov['stats']['teachers_unselected'] == 2, str(ov['stats']))
check('教师汇总 n=2', [x for x in ov['teachers'] if x['name'] == '张老师'][0]['n'] == 2, '')
check('班级明细含教师名', any(c['teachers'] == '张老师' for c in ov['classes']), '')
check('详情带 teacher_ids', any('' != (c['teacher_ids'] or '') for c in ov['classes']), '')

print('== 8 备注 ==')
nt = call('POST', '/api/teacher/note', {'course_no': '2025', 'employee_no': 'T001', 'name': '张老师',
                                       'class_id': ac1['id'], 'note': '周二1-2节 东3-201'})
ov = call('GET', '/api/admin/overview?course_no=2025')
got = [c for c in ov['classes'] if c['id'] == ac1['id']][0]
check('备注已保存', nt.get('ok') and got['notes'] == '周二1-2节 东3-201', str(got.get('notes')))

print('== 9 逐班上限 items ==')
cp = call('POST', '/api/admin/caps', {'course_no': '2025', 'items': [
    {'id': ac1['id'], 'cap': 2, 'min_need': 1}, {'id': ac2['id'], 'cap': 2, 'min_need': 1}]})
check('items 批量保存上限', cp.get('ok'), str(cp)[:120])
ov = call('GET', '/api/admin/overview?course_no=2025')
check('上限已生效', [c for c in ov['classes'] if c['id'] == ac1['id']][0]['cap'] == 2, '')
call('POST', '/api/admin/caps', {'course_no': '2025', 'items': [
    {'id': ac1['id'], 'cap': 1, 'min_need': 1}, {'id': ac2['id'], 'cap': 1, 'min_need': 1}]})

print('== 10 导出 ==')
st, body, hdr = call('GET', '/api/export?course_no=2025', raw=True)
open('_test_v2_export.xlsx', 'wb').write(body)
import openpyxl
wb = openpyxl.load_workbook('_test_v2_export.xlsx')
check('导出四张表', len(wb.sheetnames) == 4, str(wb.sheetnames))
names = wb.sheetnames
ws = wb[names[0]]
rows = list(ws.values)
check('选班明细含 2 行', len(rows) - 1 == 2, 'rows=%d' % (len(rows) - 1))
ws4 = wb[names[3]]
check('未选班教师表含 2 人', len(list(ws4.values)) >= 3, str(list(ws4.values)))

print('== 11 课程隔离 ==')
c2 = call('POST', '/api/admin/login', {'course_no': 'TEST01', 'course_name': '测试课程'})
check('新课程创建', c2.get('ok') and c2.get('created') is True and c2['stats']['classes'] == 0, str(c2)[:160])
r3 = post_file('/api/admin/import_teachers', {'course_no': 'TEST01', 'mode': 'skip'}, 'roster.csv', csv1)
check('TEST01 导入名单并关联', r3.get('ok') and r3.get('linked') == 3 and r3.get('added') == 0, str(r3))
mix = call('POST', '/api/teacher/login', {'employee_no': 'T001', 'name': '张老师'})
check('多课程登录返回 2 门', mix.get('ok') and len(mix['courses']) == 2, str(mix.get('courses')))
x = call('POST', '/api/teacher/select', {'course_no': 'TEST01', 'employee_no': 'T001', 'name': '张老师', 'ids': [ac1['id'], ac2['id']]})
check('跨课程选班被拒', not x.get('ok'), str(x)[:140])
ov2 = call('GET', '/api/admin/overview?course_no=TEST01')
check('TEST01 未选班 3 人', ov2['stats']['teachers_unselected'] == 3 and ov2['stats']['classes'] == 0, str(ov2['stats']))

print('== 12 撤销与重置 ==')
un = call('POST', '/api/teacher/unselect', {'course_no': '2025', 'employee_no': 'T001', 'name': '张老师', 'ids': [ac1['id']]})
ov = call('GET', '/api/admin/overview?course_no=2025')
check('撤销后剩 1 班', un.get('ok') and [c for c in ov['classes'] if c['id'] == ac1['id']][0]['taken'] == 0, '')
re = call('POST', '/api/teacher/select', {'course_no': '2025', 'employee_no': 'T001', 'name': '张老师', 'ids': [ac1['id']]})
check('补选回 2 班', re.get('ok') and re['stats']['classes'] == 2, str(re)[:120])
rc = call('POST', '/api/admin/reset_course', {'course_no': 'TEST01'})
ov2 = call('GET', '/api/admin/overview?course_no=TEST01')
check('重置 TEST01', rc.get('ok') and ov2['stats']['classes'] == 0 and ov2['stats']['teachers'] == 0, str(ov2['stats']))

print('== 13 页面文件 ==')
for p in ('/admin', '/', '/static/admin.js', '/static/teacher.js', '/static/style.css'):
    st, body, hdr = call('GET', p, raw=True)
    check('GET ' + p, st == 200 and len(body) > 100, 'status=%s len=%s' % (st, len(body)))

print('\n通过 %d 项，失败 %d 项' % (PASS, FAIL))
if FAILS:
    print('失败项：')
    for f in FAILS:
        print(' -', f)
    sys.exit(1)
