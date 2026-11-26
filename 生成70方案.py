# -*- coding: utf-8 -*-
import openpyxl, collections, random, math, unicodedata
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

MIN, MAX = 70, 100
SRC = '测试数据.xlsx'
OUT = '选课教师分组方案_每组不低于70人.xlsx'

wb = openpyxl.load_workbook(SRC, data_only=True)
src = [r for r in wb['班级教学计划'].iter_rows(min_row=2, values_only=True) if any(r)]
camp = collections.defaultdict(list)
for r in src:
    camp[r[5]].append({'班级': r[1], '学院': r[0], '专业': r[3], '年级': r[4], '校区': r[5], '人数': r[2]})
random.seed(20261118)


def ssum(b):
    return sum(x['人数'] for x in b)


def deficit(bins):
    c = 0
    for b in bins:
        s = ssum(b)
        if s > MAX:
            c += (s - MAX) * 50
        elif s < MIN:
            c += MIN - s
        if len(b) < 2:
            c += 200
    return c


def pack(items, G, rounds=10, iters=80000):
    for _ in range(rounds):
        it = sorted(items, key=lambda x: -x['人数'])
        bins = [[] for _ in range(G)]
        for x in it:
            cand = [(ssum(b), i) for i, b in enumerate(bins) if ssum(b) + x['人数'] <= MAX]
            if not cand:
                return None
            s, i = max(cand)
            bins[i].append(x)
        best = deficit(bins)
        for _ in range(iters):
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
            if ssum(bins[j]) + x['人数'] > MAX:
                continue
            bins[i].pop(k)
            bins[j].append(x)
            new = deficit(bins)
            if new <= best:
                best = new
            else:
                bins[j].remove(x)
                bins[i].append(x)
        if best == 0:
            return bins
    return None


def diversity(bins):
    return sum(len({x['专业'] for x in b}) - 1 for b in bins)


def purify(bins, iters=40000):
    cur = diversity(bins)
    for _ in range(iters):
        if cur == 0:
            break
        i = random.randrange(len(bins))
        j = random.randrange(len(bins))
        if i == j or not bins[i] or not bins[j]:
            continue
        a = random.choice(bins[i])
        b = random.choice(bins[j])
        si, sj = ssum(bins[i]), ssum(bins[j])
        if not (MIN <= si - a['人数'] + b['人数'] <= MAX):
            continue
        if not (MIN <= sj - b['人数'] + a['人数'] <= MAX):
            continue
        bins[i].remove(a)
        bins[i].append(b)
        bins[j].remove(b)
        bins[j].append(a)
        new = diversity(bins)
        if new <= cur:
            cur = new
        else:
            bins[i].remove(b)
            bins[i].append(a)
            bins[j].remove(a)
            bins[j].append(b)
    return bins


res = {}
for c in ['东区', '西山校区', '西区']:
    items = camp[c]
    total = sum(x['人数'] for x in items)
    g0 = None
    for G in range(math.ceil(total / MAX), math.floor(total / MIN) + 1):
        b = pack(items, G)
        if b:
            g0 = purify(b)
            break
    assert g0, c
    res[c] = g0

# 校验
allb = []
for c, bins in res.items():
    for b in bins:
        assert MIN <= ssum(b) <= MAX, (c, ssum(b))
        assert len(b) >= 2
        assert len({x['校区'] for x in b}) == 1
        allb.append((c, b))
assert sum(len(b) for _, b in allb) == 254
assert sum(ssum(b) for _, b in allb) == 7714

# 编号
prefix = {'西区': 'XQ', '西山校区': 'XS', '东区': 'DQ'}
cnt = collections.Counter()
recs = []
for c, b in allb:
    cnt[c] += 1
    tid = '%s-%02d' % (prefix[c], cnt[c])
    ms = collections.Counter()
    for x in b:
        ms[x['专业']] += x['人数']
    main = ms.most_common(1)[0][0]
    b.sort(key=lambda x: (x['专业'] != main, x['班级']))
    recs.append({'编号': tid, '校区': c, '主专业': main, '人数': ssum(b), '班级': b,
                 '专业数': len(ms)})
recs.sort(key=lambda r: (['西区', '西山校区', '东区'].index(r['校区']), r['编号']))
# 重新编号保证顺序
cnt = collections.Counter()
for r in recs:
    cnt[r['校区']] += 1
    r['编号'] = '%s-%02d' % (prefix[r['校区']], cnt[r['校区']])

# 写表
out = openpyxl.Workbook()
TH = Font(name='微软雅黑', size=11, bold=True, color='FFFFFF')
BD = Font(name='微软雅黑', size=10)
FILL = PatternFill('solid', fgColor='3370FF')
FILL2 = PatternFill('solid', fgColor='E1EAFF')
LINE = Side(style='thin', color='B8C7D9')
thin = Border(bottom=LINE)
CEN = Alignment(horizontal='center', vertical='center')
LEFT = Alignment(horizontal='left', vertical='center')


def style_header(ws, n):
    for c in range(1, n + 1):
        cell = ws.cell(1, c)
        cell.font = TH
        cell.fill = FILL
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = thin


def dw(v):
    return sum(2 if unicodedata.east_asian_width(ch) in ('F', 'W') else 1 for ch in str(v or ''))


def fit(ws, n):
    for c in range(1, n + 1):
        vals = [ws.cell(r, c).value for r in range(1, ws.max_row + 1)]
        ws.column_dimensions[get_column_letter(c)].width = max(8, min(max((dw(v) for v in vals), default=0) + 3, 50))


ws1 = out.active
ws1.title = '教师分组'
ws1.append(['序号', '教师编号', '校区', '主专业', '涉及专业', '班数', '学生合计', '剩余名额', '班级清单'])
for i, r in enumerate(recs, 1):
    ws1.append([i, r['编号'], r['校区'], r['主专业'],
                '单一专业' if r['专业数'] == 1 else '跨 %d 个专业' % r['专业数'],
                len(r['班级']), r['人数'], MAX - r['人数'],
                '、'.join(x['班级'] for x in r['班级'])])
style_header(ws1, 9)
for row in ws1.iter_rows(min_row=2, max_row=ws1.max_row, max_col=9):
    for cell in row:
        cell.font = BD
        cell.border = Border()
        cell.alignment = LEFT if cell.column == 9 else CEN
fit(ws1, 9)
ws1.freeze_panes = 'A2'
ws1.auto_filter.ref = 'A1:I%d' % ws1.max_row

ws2 = out.create_sheet('班级分配明细')
ws2.append(['教师编号', '班级', '专业简称', '学院', '年级', '校区', '人数', '是否主专业'])
for r in recs:
    for x in r['班级']:
        ws2.append([r['编号'], x['班级'], x['专业'], x['学院'], x['年级'], x['校区'], x['人数'],
                    '主专业' if x['专业'] == r['主专业'] else '补班'])
style_header(ws2, 8)
for row in ws2.iter_rows(min_row=2, max_row=ws2.max_row, max_col=8):
    for cell in row:
        cell.font = BD
        cell.border = Border()
        cell.alignment = CEN if cell.column in (1, 3, 5, 6, 7, 8) else LEFT
fit(ws2, 8)
ws2.freeze_panes = 'C2'
ws2.auto_filter.ref = 'A1:H%d' % ws2.max_row

ws3 = out.create_sheet('方案说明')
R = {'r': 1}
ws3.cell(1, 1, '选课教师分组方案（每位教师 70–100 人）').font = Font(name='微软雅黑', size=14, bold=True, color='133C9A')
ws3.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
R['r'] = 3


def sec(t):
    ws3.cell(R['r'], 1, t).font = Font(name='微软雅黑', size=11, bold=True, color='3370FF')
    R['r'] += 1


def kv(k, v, fmt=None):
    ws3.cell(R['r'], 1, k).font = BD
    c = ws3.cell(R['r'], 2, v)
    c.font = BD
    c.alignment = CEN
    if fmt:
        c.number_format = fmt
    R['r'] += 1


sec('分组规则')
for i, t in enumerate([
    '一位教师只在一个校区内选班，不跨校区',
    '班级不可拆分，整班归属唯一教师',
    '每位教师所带班级合计人数 70–100 人（上下限同时生效）',
    '每位教师至少带 2 个班级',
    '同专业优先成组，凑不满时用其他专业班级补足',
], 1):
    ws3.cell(R['r'], 1, i).font = BD
    ws3.cell(R['r'], 1).alignment = CEN
    ws3.cell(R['r'], 2, t).font = BD
    R['r'] += 1

R['r'] += 1
sec('汇总')
kv('教师总数', len(recs))
kv('覆盖班级', 254)
kv('覆盖学生', 7714)
kv('组内人数区间', '%d – %d 人' % (min(r['人数'] for r in recs), max(r['人数'] for r in recs)))
kv('人均带班', round(254 / len(recs), 2))
kv('平均装载率', round(7714 / (MAX * len(recs)), 4), '0%')
kv('单一专业组', sum(1 for r in recs if r['专业数'] == 1))
kv('跨专业组', sum(1 for r in recs if r['专业数'] > 1))

R['r'] += 1
sec('分校区')
for c, name in enumerate(['校区', '班数', '学生', '教师'], 1):
    cell = ws3.cell(R['r'], c, name)
    cell.font = TH
    cell.fill = FILL
    cell.alignment = CEN
    cell.border = thin
R['r'] += 1
for c in ['西区', '西山校区', '东区']:
    cl = [x for r in recs if r['校区'] == c for x in r['班级']]
    for cc, v in enumerate([c, len(cl), sum(x['人数'] for x in cl)], 1):
        cell = ws3.cell(R['r'], cc, v)
        cell.font = BD
        cell.alignment = CEN
    cell = ws3.cell(R['r'], 4, sum(1 for r in recs if r['校区'] == c))
    cell.font = BD
    cell.alignment = CEN
    R['r'] += 1
for cc, v in enumerate(['合计', 254, 7714, len(recs)], 1):
    cell = ws3.cell(R['r'], cc, v)
    cell.font = Font(name='微软雅黑', size=10, bold=True)
    cell.fill = FILL2
    cell.alignment = CEN
R['r'] += 2

sec('校验结果')
kv('每组人数 ≥ 70 人', '通过（最低 %d）' % min(r['人数'] for r in recs))
kv('每组人数 ≤ 100 人', '通过（最高 %d）' % max(r['人数'] for r in recs))
kv('每组至少 2 个班', '通过')
kv('无跨校区组', '通过')
kv('254 个班级覆盖完整且无重复', '通过')

ws3.column_dimensions['A'].width = 26
ws3.column_dimensions['B'].width = 46
ws3.column_dimensions['C'].width = 12
ws3.column_dimensions['D'].width = 10

out.save(OUT)
print('教师:', len(recs), '| 人数区间:', min(r['人数'] for r in recs), '-', max(r['人数'] for r in recs))
print('单一专业组:', sum(1 for r in recs if r['专业数'] == 1), '| 跨专业组:', sum(1 for r in recs if r['专业数'] > 1))
print('带班数分布:', dict(sorted(collections.Counter(len(r['班级']) for r in recs).items())))
print('专业数分布:', dict(sorted(collections.Counter(r['专业数'] for r in recs).items())))
