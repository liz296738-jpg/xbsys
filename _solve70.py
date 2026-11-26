# -*- coding: utf-8 -*-
import openpyxl, collections, random, math

MIN, MAX = 70, 100
wb = openpyxl.load_workbook('测试数据.xlsx', data_only=True)
src = [r for r in wb['班级教学计划'].iter_rows(min_row=2, values_only=True) if any(r)]

camp = collections.defaultdict(list)
for r in src:
    camp[r[5]].append({'班级': r[1], '学院': r[0], '专业': r[3], '年级': r[4], '校区': r[5], '人数': r[2]})

random.seed(20261118)


def cost(bins):
    c = 0
    for b in bins:
        s = sum(x['人数'] for x in b)
        if s > MAX:
            c += (s - MAX) * 50
        elif s < MIN:
            c += (MIN - s)
        if len(b) < 2:
            c += 200
    return c


def solve(items, G, rounds=8, iters=60000):
    for r in range(rounds):
        it = sorted(items, key=lambda x: -x['人数'])
        bins = [[] for _ in range(G)]
        for x in it:
            cand = [(sum(y['人数'] for y in b), i) for i, b in enumerate(bins)]
            cand = [(s, i) for s, i in cand if s + x['人数'] <= MAX]
            if not cand:
                return None
            s, i = max(cand)          # worst-fit：塞进当前最空的
            bins[i].append(x)
        best = cost(bins)
        for step in range(iters):
            if best == 0:
                break
            i = random.randrange(G)
            if not bins[i]:
                continue
            j = random.randrange(G)
            if i == j:
                continue
            k = random.randrange(len(bins[i]))
            x = bins[i][k]
            s_j = sum(y['人数'] for y in bins[j])
            if s_j + x['人数'] > MAX:
                continue
            bins[i].pop(k)
            bins[j].append(x)
            new = cost(bins)
            if new <= best:
                best = new
            else:
                bins[j].remove(x)
                bins[i].append(x)
        if best == 0:
            return bins
    return None


res = {}
for c in ['东区', '西山校区', '西区']:
    items = camp[c]
    total = sum(x['人数'] for x in items)
    lo_g = math.ceil(total / MAX)
    hi_g = math.floor(total / MIN)
    found = None
    for G in range(lo_g, hi_g + 1):
        b = solve(items, G)
        if b:
            found = (G, b)
            break
    if found:
        G, b = found
        res[c] = b
        sums = sorted(sum(y['人数'] for y in x) for x in b)
        print('%s: %d 班 %d 人 -> %d 组 (理论区间 %d-%d) 组人数 %d-%d 平均 %.1f' % (
            c, len(items), total, G, lo_g, hi_g, sums[0], sums[-1], total / G))
    else:
        print('%s: 在 %d-%d 区间内未找到可行解' % (c, lo_g, hi_g))

tot = sum(len(b) for b in res.values())
print('合计教师:', tot, '| 覆盖班级:', sum(len(x) for b in res.values() for x in b),
      '| 覆盖学生:', sum(y['人数'] for b in res.values() for x in b for y in x))
