# -*- coding: utf-8 -*-
import csv, json, io, collections

d = json.load(open('_分组.csv', encoding='utf-8-sig'))
rows = list(csv.reader(io.StringIO(d['csv'])))
data = [r for r in rows[1:] if r and r[0]]
recs = [{'id': r[1], 'campus': r[2], 'major': r[3], 'mixed': r[4], 'n': int(r[5]),
         'p': int(r[6]), 'left': int(r[7]), 'list': r[8]} for r in data]

tot_spare = sum(x['left'] for x in recs)
print('总空位:', tot_spare, '| 平均每组空:', round(tot_spare / len(recs), 1))
for th in (19, 22, 25, 28, 30, 34, 40):
    k = sum(1 for x in recs if x['left'] >= th)
    print('  空位>=%2d 的组: %2d 个（可再塞下一个 %d 人以上的班）' % (th, k, th))
print('低组(<70)缺口合计:', sum(100 - x['p'] for x in recs if x['p'] < 70))

# 2 班组的普遍性
two = [x for x in recs if x['n'] == 2]
print('\n2 班组:', len(two), '组，人数', min(x['p'] for x in two), '-', max(x['p'] for x in two))

# 专业层面：全专业只有 2 个班的专业
wb_rows = []
import openpyxl
wb = openpyxl.load_workbook('测试数据.xlsx', data_only=True)
src = [r for r in wb['班级教学计划'].iter_rows(min_row=2, values_only=True) if any(r)]
m2 = collections.defaultdict(list)
for r in src:
    m2[r[3]].append(r[2])
print('\n全专业仅 2 个班的专业:', sum(1 for k, v in m2.items() if len(v) == 2), '个')
print('这些专业人数区间:', min(sum(v) for v in m2.values() if len(v) == 2), '-', max(sum(v) for v in m2.values() if len(v) == 2))

# 材料专业：8 班 233 人
print('\n材料:', [r[2] for r in src if r[3] == '材料'])
print('中文类:', [r[2] for r in src if r[3] == '中文类'])
print('电气:', [r[2] for r in src if r[3] == '电气'])
print('机械类:', [r[2] for r in src if r[3] == '机械类'])
