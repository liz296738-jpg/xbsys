# -*- coding: utf-8 -*-
import openpyxl, collections
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import unicodedata

CAP = 100
SRC = '测试数据.xlsx'
OUT = '选课教师分组方案.xlsx'

# ---------- 读取 ----------
wb = openpyxl.load_workbook(SRC, data_only=True)
rows = [r for r in wb['班级教学计划'].iter_rows(min_row=2, values_only=True) if any(r)]

# ---------- 打包：校区内，专业优先，尾组跨专业补班 ----------
camp = collections.defaultdict(list)
for r in rows:
    camp[r[5]].append({'班级': r[1], '学院': r[0], '专业': r[3], '年级': r[4], '校区': r[5], '人数': r[2]})


def ffd(items):
    items = sorted(items, key=lambda x: -x['人数'])
    bins = []
    for x in items:
        for b in bins:
            if b['人数'] + x['人数'] <= CAP:
                b['人数'] += x['人数']
                b['班级'].append(x)
                break
        else:
            bins.append({'人数': x['人数'], '班级': [x]})
    return bins


groups = []
for c in ['西区', '西山校区', '东区']:
    if c not in camp:
        continue
    bymaj = collections.defaultdict(list)
    for it in camp[c]:
        bymaj[it['专业']].append(it)
    g = []
    for m in bymaj:
        g += ffd(bymaj[m])
    changed = True
    while changed:
        changed = False
        for s in sorted(g, key=lambda x: x['人数']):
            tgt = None
            for t in g:
                if t is s or len(t['班级']) < 2:
                    continue
                if t['人数'] + s['人数'] > CAP:
                    continue
                if tgt is None or t['人数'] > tgt['人数']:
                    tgt = t
            if tgt:
                tgt['人数'] += s['人数']
                tgt['班级'] += s['班级']
                g.remove(s)
                changed = True
                break
    g.sort(key=lambda x: (x['班级'][0]['专业'], -x['人数']))
    groups += [(c, x) for x in g]

# ---------- 校验 ----------
assert len(groups) == 89, len(groups)
assert sum(len(x['班级']) for _, x in groups) == 254
assert sum(x['人数'] for _, x in groups) == 7714
assert all(x['人数'] <= CAP for _, x in groups)
assert all(len(x['班级']) >= 2 for _, x in groups)
assert all(len({b['校区'] for b in x['班级']}) == 1 for _, x in groups)

# ---------- 编号 ----------
prefix = {'西区': 'XQ', '西山校区': 'XS', '东区': 'DQ'}
cnt = collections.Counter()
recs = []
for c, x in groups:
    cnt[c] += 1
    tid = '%s-%02d' % (prefix[c], cnt[c])
    ms = collections.Counter()
    for b in x['班级']:
        ms[b['专业']] += b['人数']
    main = ms.most_common(1)[0][0]
    x['班级'].sort(key=lambda b: (b['专业'] != main, b['班级']))
    recs.append({'编号': tid, '校区': c, '主专业': main, '人数': x['人数'], '班级': x['班级']})

# ---------- 写表 ----------
out = openpyxl.Workbook()
TH = Font(name='微软雅黑', size=11, bold=True, color='FFFFFF')
BD = Font(name='微软雅黑', size=10)
FILL = PatternFill('solid', fgColor='3370FF')
FILL2 = PatternFill('solid', fgColor='E1EAFF')
LINE = Side(style='thin', color='B8C7D9')
thin = Border(bottom=LINE)
CEN = Alignment(horizontal='center', vertical='center')
LEFT = Alignment(horizontal='left', vertical='center', wrap_text=False)


def style_header(ws, ncol):
    for c in range(1, ncol + 1):
        cell = ws.cell(1, c)
        cell.font = TH
        cell.fill = FILL
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = thin


def width(v):
    return sum(2 if unicodedata.east_asian_width(ch) in ('F', 'W') else 1 for ch in str(v or ''))


def fit(ws, ncol, min_row=1):
    for c in range(1, ncol + 1):
        vals = [ws.cell(r, c).value for r in range(min_row, ws.max_row + 1)]
        ws.column_dimensions[get_column_letter(c)].width = max(
            8, min(max((width(v) for v in vals), default=0) + 3, 50))


# Sheet1 教师分组
ws1 = out.active
ws1.title = '教师分组'
ws1.append(['序号', '教师编号', '校区', '主专业', '跨专业补班', '班数', '学生合计', '剩余名额', '班级清单'])
for i, r in enumerate(recs, 1):
    mixed = len({b['专业'] for b in r['班级']}) > 1
    ws1.append([i, r['编号'], r['校区'], r['主专业'], '是' if mixed else '否',
                len(r['班级']), r['人数'], CAP - r['人数'],
                '、'.join(b['班级'] for b in r['班级'])])
style_header(ws1, 9)
for row in ws1.iter_rows(min_row=2, max_row=ws1.max_row, max_col=9):
    for cell in row:
        cell.font = BD
        cell.border = Border()
        cell.alignment = CEN if cell.column != 9 else LEFT
fit(ws1, 9)
ws1.freeze_panes = 'A2'
ws1.auto_filter.ref = 'A1:I%d' % ws1.max_row

# Sheet2 班级分配明细
ws2 = out.create_sheet('班级分配明细')
ws2.append(['教师编号', '班级', '专业简称', '学院', '年级', '校区', '人数', '是否主专业'])
for r in recs:
    for b in r['班级']:
        ws2.append([r['编号'], b['班级'], b['专业'], b['学院'], b['年级'], b['校区'], b['人数'],
                    '主专业' if b['专业'] == r['主专业'] else '补班'])
style_header(ws2, 8)
for row in ws2.iter_rows(min_row=2, max_row=ws2.max_row, max_col=8):
    for cell in row:
        cell.font = BD
        cell.border = Border()
        cell.alignment = CEN if cell.column in (1, 3, 5, 6, 7, 8) else LEFT
fit(ws2, 8)
ws2.freeze_panes = 'C2'
ws2.auto_filter.ref = 'A1:H%d' % ws2.max_row

# Sheet3 方案说明
ws3 = out.create_sheet('方案说明')
R = {'r': 1}


ws3.cell(1, 1, '选课教师分组方案说明').font = Font(name='微软雅黑', size=14, bold=True, color='133C9A')
ws3.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
R['r'] = 3


def sec(title):
    c = ws3.cell(R['r'], 1, title)
    c.font = Font(name='微软雅黑', size=11, bold=True, color='3370FF')
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
    '优先选同一专业的班级；该专业填不满 100 人时，可用其他专业班级补足',
    '班级不可拆分，整班归属唯一教师',
    '每位教师所带班级合计人数不超过 100 人',
    '每位教师至少带 2 个班级',
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
kv('人均带班', round(254 / len(recs), 2))
kv('人均学生', round(7714 / len(recs), 1))
kv('平均装载率', round(7714 / (CAP * len(recs)), 4), '0%')
kv('跨专业补班组', sum(1 for r in recs if len({b['专业'] for b in r['班级']}) > 1))

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
    cl = [b for r in recs if r['校区'] == c for b in r['班级']]
    for cc, v in enumerate([c, len(cl), sum(b['人数'] for b in cl)], 1):
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
kv('无超过 100 人的组', '通过')
kv('无只带 1 个班的组', '通过')
kv('无跨校区的组', '通过')
kv('254 个班级覆盖完整且无重复', '通过')

ws3.column_dimensions['A'].width = 30
ws3.column_dimensions['B'].width = 44
ws3.column_dimensions['C'].width = 12
ws3.column_dimensions['D'].width = 10

out.save(OUT)
print('分组数:', len(recs))
print('人数:', sum(r['人数'] for r in recs))
print('跨专业补班组:', sum(1 for r in recs if len({b['专业'] for b in r['班级']}) > 1))
for r in recs[:6]:
    print(r['编号'], r['校区'], r['主专业'], r['人数'], '、'.join(b['班级'] for b in r['班级']))
