# -*- coding: utf-8 -*-
import openpyxl, collections

wb = openpyxl.load_workbook('测试数据.xlsx', data_only=True)
src = [r for r in wb['班级教学计划'].iter_rows(min_row=2, values_only=True) if any(r)]


def solve(CAP):
    camp = collections.defaultdict(list)
    for r in src:
        camp[r[5]].append({'p': r[2], 'm': r[3]})
    total = 0
    low = 0
    for c in ['西区', '西山校区', '东区']:
        bymaj = collections.defaultdict(list)
        for it in camp[c]:
            bymaj[it['m']].append(it)
        g = []
        for m in bymaj:
            items = sorted(bymaj[m], key=lambda x: -x['p'])
            bins = []
            for x in items:
                for b in bins:
                    if b['p'] + x['p'] <= CAP:
                        b['p'] += x['p']
                        b['n'] += 1
                        break
                else:
                    bins.append({'p': x['p'], 'n': 1})
            g += bins
        changed = True
        while changed:
            changed = False
            for s in sorted(g, key=lambda x: x['p']):
                tgt = None
                for t in g:
                    if t is s or t['n'] < 2 or t['p'] + s['p'] > CAP:
                        continue
                    if tgt is None or t['p'] > tgt['p']:
                        tgt = t
                if tgt:
                    tgt['p'] += s['p']
                    tgt['n'] += s['n']
                    g.remove(s)
                    changed = True
                    break
        total += len(g)
        low += sum(1 for x in g if x['p'] < 70)
    return total, low


for cap in (100, 90, 80, 75, 70):
    n, low = solve(cap)
    print('上限 %3d 人 -> 教师 %3d 人 | 平均 %5.1f 人 | 低于70人的组 %2d 个 | 组数 %d' % (
        cap, n, round(7714 / n, 1), low, n))
