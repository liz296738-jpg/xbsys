# -*- coding: utf-8 -*-
import openpyxl, collections, random, math, json

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
        c += (len({x['专业'] for x in b}) - 1) * 1.5
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
            s, i = max(cand)
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
            if sum(y['人数'] for y in bins[j]) + x['人数'] > MAX:
                continue
            bins[i].pop(k)
            bins[j].append(x)
            new = cost(bins)
            if new <= best:
                best = new
            else:
                bins[j].remove(x)
                bins[i].append(x)
        if cost(bins) <= 2:
            return bins
    return None


res = {}
for c in ['东区', '西山校区', '西区']:
    items = camp[c]
    total = sum(x['人数'] for x in items)
    for G in range(math.ceil(total / MAX), math.floor(total / MIN) + 1):
        b = solve(items, G)
        if b:
            res[c] = b
            break

tot = sum(len(b) for b in res.values())
pure = mixed2 = mixed3 = 0
allg = []
for c, bins in res.items():
    for b in bins:
        ms = collections.Counter()
        for x in b:
            ms[x['专业']] += x['人数']
        n_major = len(ms)
        allg.append((c, len(b), sum(x['人数'] for x in b), n_major, ms.most_common(1)[0][0],
                     '、'.join(x['班级'] for x in b)))
        if n_major == 1:
            pure += 1
        elif n_major == 2:
            mixed2 += 1
        else:
            mixed3 += 1
print('教师:', tot, '| 纯专业组:', pure, '| 2 专业组:', mixed2, '| 3 专业及以上:', mixed3)
print('组人数:', min(g[2] for g in allg), '-', max(g[2] for g in allg))
print('带班数分布:', dict(collections.Counter(g[1] for g in allg)))
print('\n多专业组示例:')
for g in allg:
    if g[3] >= 3:
        print('  ', g[0], g[2], g[4], g[5])
json.dump([{'校区': g[0], '班数': g[1], '人数': g[2], '主专业': g[4], '专业数': g[3], '清单': g[5]} for g in allg],
          open('_70groups.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
