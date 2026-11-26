# -*- coding: utf-8 -*-
import csv, json, io, collections

d = json.load(open('_分组.csv', encoding='utf-8-sig'))
rows = list(csv.reader(io.StringIO(d['csv'])))
print('表头:', rows[0])
data = [r for r in rows[1:] if r and r[0]]
print('组数:', len(data))
print('样例:', data[0])
print('样例:', data[-1])
print('列数:', len(data[0]))

recs = []
for r in data:
    recs.append({'id': r[1], 'campus': r[2], 'major': r[3], 'mixed': r[4],
                 'n': int(r[5]), 'p': int(r[6]), 'left': int(r[7]), 'list': r[8]})

bins = collections.Counter()
for x in recs:
    p = x['p']
    k = '>=90' if p >= 90 else ('80-89' if p >= 80 else ('70-79' if p >= 70 else ('60-69' if p >= 60 else '<60')))
    bins[k] += 1
print('\n人数分布:', dict(bins))
print('最低:', min(x['p'] for x in recs), '最高:', max(x['p'] for x in recs))
print('平均:', round(sum(x['p'] for x in recs) / len(recs), 1))

print('\n低于 70 人的组 (%d 组):' % sum(1 for x in recs if x['p'] < 70))
for x in sorted([x for x in recs if x['p'] < 70], key=lambda y: y['p']):
    print('%-7s %-5s %-5s %d班 %3d人 缺口%3d  %s' % (x['id'], x['campus'], x['major'], x['n'], x['p'], 100 - x['p'], x['list']))
