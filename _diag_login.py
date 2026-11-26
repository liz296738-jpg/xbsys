# -*- coding: utf-8 -*-
import json, urllib.request, urllib.error

BASE = 'http://127.0.0.1:8765'


def post(path, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=data, method='POST',
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode('utf-8'))


print('1) 工号+姓名:', post('/api/teacher/login', {'employee_no': '1020180078', 'name': '丁梓'})['ok'])
r = post('/api/teacher/login', {'employee_no': '1020180078', 'name': '丁梓'})
print('   courses:', r.get('courses'))
print('2) 只填姓名:', post('/api/teacher/login', {'employee_no': '', 'name': '丁梓'}))
print('3) 工号带空格:', post('/api/teacher/login', {'employee_no': ' 1020180078 ', 'name': '丁梓'})['ok'])
print('4) 姓名带空格:', post('/api/teacher/login', {'employee_no': '1020180078', 'name': ' 丁梓 '})['ok'])
