# -*- coding: utf-8 -*-
"""教师选班系统 —— 本地服务（仅用 Python 标准库，导出用 openpyxl）"""
import io
import json
import os
import re
import sqlite3
import unicodedata
import threading
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('JXB_DB') or os.path.join(BASE_DIR, '选班系统.db')
DB_PREEXISTED = os.path.isfile(DB_PATH)     # 本次启动前数据库是否已存在（决定是否允许自动播种）
BACKUP_DIR = os.environ.get('JXB_BACKUP') or os.path.join(BASE_DIR, '备份')
SEED_XLSX = os.path.join(BASE_DIR, '测试数据.xlsx')
# 部署成网站时：JXB_HOST=0.0.0.0 让所有网卡/内网都能访问；JXB_PORT 改端口
HOST = os.environ.get('JXB_HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT') or os.environ.get('JXB_PORT', '8765'))
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL:
    HOST = '0.0.0.0'
    DB_PREEXISTED = True

LOCK = threading.Lock()
_LOCAL = threading.local()
_SCHEMA_READY = False

DEFAULT_COURSE_NO = '2025'
DEFAULT_COURSE_NAME = '2025级专业班级选班'


# ---------------------------------------------------------------- 数据库
SCHEMA = """
CREATE TABLE IF NOT EXISTS courses(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_no TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS classes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    college TEXT NOT NULL,
    name TEXT NOT NULL,
    plan_size INTEGER NOT NULL,
    major TEXT NOT NULL DEFAULT '',
    grade TEXT NOT NULL DEFAULT '',
    campus TEXT NOT NULL DEFAULT '',
    cap INTEGER NOT NULL DEFAULT 1,
    min_need INTEGER NOT NULL DEFAULT 1,
    UNIQUE(course_id, name)
);
CREATE TABLE IF NOT EXISTS teachers(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_no TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    imported INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS course_teachers(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL,
    imported_at TEXT NOT NULL,
    UNIQUE(course_id, teacher_id),
    FOREIGN KEY(course_id) REFERENCES courses(id),
    FOREIGN KEY(teacher_id) REFERENCES teachers(id)
);
CREATE TABLE IF NOT EXISTS selections(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    class_id INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(class_id, teacher_id),
    FOREIGN KEY(class_id) REFERENCES classes(id),
    FOREIGN KEY(teacher_id) REFERENCES teachers(id)
);
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS teacher_notes(
    course_id INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY(course_id, teacher_id)
);
CREATE TABLE IF NOT EXISTS sessions(
    token TEXT PRIMARY KEY,
    teacher_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_sessions(
    token TEXT PRIMARY KEY,
    course_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sel_class ON selections(class_id);
CREATE INDEX IF NOT EXISTS idx_sel_teacher ON selections(teacher_id);
CREATE INDEX IF NOT EXISTS idx_cls_course ON classes(course_id);
CREATE INDEX IF NOT EXISTS idx_ct_course ON course_teachers(course_id);
"""

DEFAULT_SETTINGS = {
    'teacher_max_students': '100',   # 每位教师最多可选学生数，0=不限
    'teacher_min_classes': '2',      # 每位教师至少选几个班，0=不限
}


def db():
    """每个线程一个数据库连接：多人并发在线时互不干扰"""
    conn = getattr(_LOCAL, 'conn', None)
    if conn is None:
        if DATABASE_URL:
            from postgres_backend import Connection
            conn = Connection(DATABASE_URL)
        else:
            conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA busy_timeout=30000')
            conn.execute('PRAGMA synchronous=NORMAL')
        _LOCAL.conn = conn
        init_schema(conn)
    elif not getattr(_LOCAL, 'ready', False):
        init_schema(conn)
    _LOCAL.ready = True
    return conn


def init_schema(conn):
    """建表 + 默认设置；多线程并发首次调用时加锁只执行一次"""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with LOCK:
        if _SCHEMA_READY:
            return
        try:
            if DATABASE_URL:
                conn.execute('SELECT 1 FROM settings LIMIT 1')
            else:
                conn.executescript(SCHEMA)
            for k, v in DEFAULT_SETTINGS.items():
                conn.execute('INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)', (k, v))
            conn.commit()
            _SCHEMA_READY = True
        except Exception:
            conn.rollback()
            raise


def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def get_setting(key):
    row = db().execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return int(row['value']) if row else 0


def seed_default_course(force=False):
    """建默认课程并从 测试数据.xlsx 导入班级。缺种子文件时什么都不做（不会建空课程）。
    只允许在“真正首次安装”或显式 --seed-test 时执行，已有数据的库不会被覆盖或重复导入。
    返回导入班级数；-1 表示没有种子文件。"""
    if not force and db().execute('SELECT COUNT(*) c FROM courses').fetchone()['c'] > 0:
        return 0
    if not os.path.exists(SEED_XLSX):
        return -1
    try:
        import openpyxl
    except ImportError:
        return -1
    wb = openpyxl.load_workbook(SEED_XLSX, data_only=True)
    ws = wb['班级教学计划'] if '班级教学计划' in wb.sheetnames else wb.worksheets[0]
    rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if any(r)]
    if not rows:
        wb.close()
        return -1
    with LOCK:
        cur = db().execute('INSERT INTO courses(course_no, name, created_at) VALUES(?,?,?)',
                           (DEFAULT_COURSE_NO, DEFAULT_COURSE_NAME, now_str()))
        cid = cur.lastrowid
        db().commit()
    n = 0
    with LOCK:
        for r in rows:
            college, name, size, major, grade, campus = r[0], r[1], r[2], r[3], r[4], r[5]
            if not name:
                continue
            try:
                size = int(size)
            except (TypeError, ValueError):
                continue
            db().execute('INSERT OR IGNORE INTO classes(course_id,college,name,plan_size,major,grade,campus) '
                         'VALUES(?,?,?,?,?,?,?)',
                         (cid, str(college or ''), str(name), size, str(major or ''),
                          str(grade or ''), str(campus or '')))
            n += 1
        db().commit()
    try:
        wb.close()
    except Exception:
        pass
    return n


# ---------------------------------------------------------------- 数据保护
def startup_snapshot(keep=15):
    """每次启动前把现有数据库热备一份到 备份/，防止重启或误操作把上一次的选班结果弄丢"""
    if DATABASE_URL:
        conn = db()
        payload = {table: [dict(row) for row in conn.execute('SELECT * FROM ' + table).fetchall()]
                   for table in ('courses', 'classes', 'teachers', 'course_teachers',
                                 'selections', 'settings', 'teacher_notes')}
        cur = conn.execute('INSERT INTO startup_snapshots(created_at,payload) VALUES(?,?)',
                           (now_str(), json.dumps(payload, ensure_ascii=False)))
        snapshot_id = cur.lastrowid
        conn.execute('DELETE FROM startup_snapshots WHERE id NOT IN '
                     '(SELECT id FROM startup_snapshots ORDER BY id DESC LIMIT ?)', (keep,))
        conn.commit()
        return 'PostgreSQL 启动快照 #%s' % snapshot_id
    if not os.path.isfile(DB_PATH):
        return None
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        dst = os.path.join(BACKUP_DIR, '启动快照-%s.db' % datetime.now().strftime('%Y%m%d-%H%M%S'))
        src = sqlite3.connect(DB_PATH, timeout=30)
        try:
            src.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            out = sqlite3.connect(dst)
            try:
                src.backup(out)
            finally:
                out.close()
        finally:
            src.close()
        files = sorted((f for f in os.listdir(BACKUP_DIR) if f.startswith('启动快照-') and f.endswith('.db')),
                       reverse=True)
        for f in files[keep:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, f))
            except OSError:
                pass
        return dst
    except Exception:
        traceback.print_exc()
        return None


def data_summary():
    counts = {}
    for key, sql in (('课程', 'SELECT COUNT(*) c FROM courses'),
                     ('班级', 'SELECT COUNT(*) c FROM classes'),
                     ('教师', 'SELECT COUNT(*) c FROM teachers'),
                     ('选班记录', 'SELECT COUNT(*) c FROM selections')):
        try:
            counts[key] = db().execute(sql).fetchone()['c']
        except Exception:
            counts[key] = -1
    return counts


def newest_snapshot():
    """备份目录里最新一份启动快照（用于数据库意外为空时提示回滚）"""
    if not os.path.isdir(BACKUP_DIR):
        return None
    files = sorted((f for f in os.listdir(BACKUP_DIR) if f.startswith('启动快照-') and f.endswith('.db')),
                   reverse=True)
    return os.path.join(BACKUP_DIR, files[0]) if files else None


# ---------------------------------------------------------------- 业务
class BizError(Exception):
    def __init__(self, msg):
        super().__init__(msg)
        self.msg = msg


def course_of(course_no):
    no = (course_no or '').strip()
    row = db().execute('SELECT * FROM courses WHERE course_no=?', (no,)).fetchone()
    if not row:
        raise BizError('课程不存在：%s' % (no or '（未填写课程号）'))
    return row


def require_course(course_no):
    if not (course_no or '').strip():
        raise BizError('缺少课程号')
    return course_of(course_no)


_INVISIBLE = dict.fromkeys(map(ord, '\u200b\u200c\u200d\u2060\ufeff'), None)


def _clean(v):
    """统一清洗：全角转半角、去不可见字符与首尾空白"""
    s = unicodedata.normalize('NFKC', str(v or ''))
    s = s.translate(_INVISIBLE).strip()
    # 去掉从 Excel/系统复制时带的撇号与前导引号
    s = s.lstrip("'‘’\"“”`")
    return s


def norm_no(v):
    """工号规范化：全角转半角、去空格（含全角）、数字型去掉尾部 .0"""
    s = _clean(v).replace('\u3000', '').replace(' ', '')
    if s.endswith('.0') and s[:-2].isdigit():
        s = s[:-2]
    if s.endswith('.') and s[:-1].isdigit():
        s = s[:-1]
    return s


def norm_name(v):
    """姓名规范化：全角转半角、去不可见字符、去空格（含全角）"""
    s = _clean(v)
    for ch in ('\u3000', ' '):
        s = s.replace(ch, '')
    return s


def _teachers_by_name(nm):
    rows = db().execute('SELECT * FROM teachers WHERE name=?', (nm,)).fetchall()
    if rows:
        return rows
    rows = db().execute("SELECT * FROM teachers WHERE replace(replace(name,' ',''),char(12288),'')=?",
                        (nm,)).fetchall()
    return rows


def find_teacher(employee_no, name, note=None):
    """严格校验：工号与姓名必须同时匹配同一条教师记录；报错时尽量给出正确工号"""
    no = norm_no(employee_no)
    nm = norm_name(name)
    if not nm and not no:
        raise BizError('请填写工号和姓名：两项必须同时匹配才能登录')
    if not no:
        same = _teachers_by_name(nm)
        if len(same) == 1 and same[0]['employee_no']:
            raise BizError('请填写工号：姓名「%s」在名单中的工号是「%s」，两项都要填且必须一致'
                           % (nm, same[0]['employee_no']))
        if len(same) > 1:
            nos = '、'.join(r['employee_no'] or '无工号' for r in same[:5])
            raise BizError('请填写工号：姓名「%s」在名单中有 %d 位（工号：%s），请用工号区分'
                           % (nm, len(same), nos))
        if same:
            raise BizError('姓名「%s」在名单中没有登记工号，无法登录，请联系课程管理员补填工号' % nm)
        raise BizError('请填写工号：工号和姓名需同时匹配才能登录')
    if not nm:
        row0 = db().execute('SELECT * FROM teachers WHERE employee_no=?', (no,)).fetchone()
        if row0:
            raise BizError('请填写姓名：工号「%s」在名单中登记的姓名是「%s」，姓名也要填上'
                           % (no, row0['name']))
        raise BizError('请填写姓名：工号和姓名需同时匹配才能登录')
    row = db().execute('SELECT * FROM teachers WHERE employee_no=?', (no,)).fetchone()
    if not row:
        row = db().execute("SELECT * FROM teachers WHERE replace(replace(employee_no,' ',''),char(12288),'')=?",
                           (no,)).fetchone()
    if not row:
        same_name = _teachers_by_name(nm)
        if len(same_name) == 1 and same_name[0]['employee_no']:
            raise BizError('工号「%s」不在名单中，但姓名「%s」在名单里对应的工号是「%s」，请核对工号后重新登录'
                           % (no, nm, same_name[0]['employee_no']))
        if len(same_name) > 1:
            nos = '、'.join(r['employee_no'] or '无工号' for r in same_name[:5])
            raise BizError('工号「%s」不在名单中；姓名「%s」在名单中有 %d 位（工号：%s），请核对工号'
                           % (no, nm, len(same_name), nos))
        raise BizError('工号「%s」不在名单中，请核对工号（数字、字母、长度）后重新登录；'
                       '若确实刚入职，请联系课程管理员在「名单与班级导入」页添加' % no)
    if row['name'] != nm:
        same_name = _teachers_by_name(nm)
        if len(same_name) == 1 and same_name[0]['employee_no']:
            raise BizError('工号「%s」在名单中登记的姓名是「%s」，而「%s」在名单中的工号是「%s」；'
                           '说明工号或姓名有一项填错了，请核对后重新登录'
                           % (no, row['name'], nm, same_name[0]['employee_no']))
        if len(same_name) > 1:
            nos = '、'.join(r['employee_no'] or '无工号' for r in same_name[:5])
            raise BizError('工号「%s」在名单中登记的姓名是「%s」；「%s」在名单中有 %d 位（工号：%s），'
                           '请核对工号与姓名后重新登录' % (no, row['name'], nm, len(same_name), nos))
        raise BizError('工号「%s」在名单中登记的姓名是「%s」，名单里没有姓名「%s」；'
                       '请先联系课程管理员核对姓名，或确认工号是否填错' % (no, row['name'], nm))
    if note is not None:
        note['stored_no'] = row['employee_no']
    return row


def in_roster(course_id, teacher_id):
    row = db().execute('SELECT 1 FROM course_teachers WHERE course_id=? AND teacher_id=?',
                       (course_id, teacher_id)).fetchone()
    return bool(row)


def courses_of_teacher(teacher_id):
    return [dict(r) for r in db().execute(
        'SELECT c.id, c.course_no, c.name, '
        '(SELECT COUNT(*) FROM selections s WHERE s.course_id=c.id AND s.teacher_id=?) AS picked_classes, '
        '(SELECT COALESCE(SUM(cl.plan_size),0) FROM selections s JOIN classes cl ON cl.id=s.class_id '
        ' WHERE s.course_id=c.id AND s.teacher_id=?) AS picked_students '
        'FROM courses c JOIN course_teachers ct ON ct.course_id=c.id '
        'WHERE ct.teacher_id=? ORDER BY c.course_no',
        (teacher_id, teacher_id, teacher_id)).fetchall()]


LOGIN_LOG = os.path.join(BASE_DIR, '登录日志.jsonl')


def log_login(employee_no, name, ok, detail, matched=''):
    """记录每次教师登录尝试，便于管理员排查“为什么进不去”"""
    try:
        rec = {'time': now_str(), 'input_no': str(employee_no or ''),
               'input_name': str(name or ''), 'ok': bool(ok),
               'matched': matched, 'detail': str(detail or '')}
        if DATABASE_URL:
            db().execute('INSERT INTO login_events(payload) VALUES(?)',
                         (json.dumps(rec, ensure_ascii=False),))
            db().commit()
            return
        with open(LOGIN_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        if os.path.getsize(LOGIN_LOG) > 2 * 1024 * 1024:
            with open(LOGIN_LOG, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-3000:]
            with open(LOGIN_LOG, 'w', encoding='utf-8') as f:
                f.writelines(lines)
    except Exception:
        traceback.print_exc()


def _read_jsonl(path):
    """容错读取 JSONL：历史日志可能混入 GBK 编码的行，逐行解码，坏行跳过而不是整份读不出"""
    rows = []
    with open(path, 'rb') as f:
        raw = f.read()
    for line in raw.split(b'\n'):
        line = line.strip()
        if not line:
            continue
        text = None
        for enc in ('utf-8', 'gbk', 'gb18030'):
            try:
                text = line.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            continue
        try:
            rows.append(json.loads(text))
        except Exception:
            continue
    return rows


def recent_logins(limit=30):
    if DATABASE_URL:
        return [json.loads(r['payload']) for r in db().execute(
            'SELECT payload FROM login_events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()]
    if not os.path.exists(LOGIN_LOG):
        return []
    try:
        items = []
        for rec in reversed(_read_jsonl(LOGIN_LOG)):
            items.append(rec)
            if len(items) >= limit:
                break
        return items
    except Exception:
        traceback.print_exc()
        return []


def teacher_login(employee_no, name):
    note = {}
    try:
        t = find_teacher(employee_no, name, note)
    except BizError as e:
        log_login(employee_no, name, False, e.msg)
        raise
    courses = courses_of_teacher(t['id'])
    if not courses:
        msg = ('已找到教师「%s」（工号 %s），但尚未加入任何课程。'
               '请联系课程管理员在该课程的「名单与班级导入」页导入教师名单或单个添加'
               % (t['name'], t['employee_no'] or '无'))
        log_login(employee_no, name, False, msg, t['name'] + '/' + (t['employee_no'] or ''))
        raise BizError(msg)
    warn = ''
    token = issue_token(t['id'])
    log_login(employee_no, name, True, warn or '登录成功',
              t['name'] + '/' + (t['employee_no'] or ''))
    return {'teacher': {'id': t['id'], 'employee_no': t['employee_no'], 'name': t['name']},
            'courses': courses, 'warning': warn, 'settings': current_settings(),
            'token': token, 'matched_by': 'no+name'}


def issue_token(teacher_id):
    """登录成功后发放会话凭证，后续提交选班只认凭证，不再重复校验工号姓名"""
    import uuid
    token = uuid.uuid4().hex
    with LOCK:
        db().execute('INSERT INTO sessions(token, teacher_id, created_at) VALUES(?,?,?)',
                     (token, teacher_id, now_str()))
        db().commit()
    return token


def resolve_teacher(payload):
    """优先用会话凭证认人；没有凭证时回退到工号+姓名（兼容旧页面）"""
    token = str(payload.get('token') or '').strip()
    if token:
        row = db().execute('SELECT t.* FROM sessions s JOIN teachers t ON t.id=s.teacher_id '
                           'WHERE s.token=?', (token,)).fetchone()
        if row:
            return row
    return find_teacher(payload.get('employee_no'), payload.get('name'))


def _hash_password(password, salt=None):
    import hashlib
    salt = salt or os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 120000)
    return 'pbkdf2$%s$%s' % (salt, dk.hex())


def _check_password(password, stored):
    import hmac
    try:
        algo, salt, h = stored.split('$')
    except Exception:
        return False
    calc = _hash_password(password, salt).split('$')[-1]
    return hmac.compare_digest(calc, h)


_FAILD = {}
_FAILD_LOCK = threading.Lock()


def _throttle_check(ip):
    with _FAILD_LOCK:
        rec = _FAILD.get(ip)
        if not rec:
            return
        cnt, ts = rec
        if cnt >= 8 and (datetime.now() - ts).total_seconds() < 300:
            raise BizError('密码错误次数过多，请 5 分钟后再试')


def _throttle_fail(ip):
    with _FAILD_LOCK:
        cnt, _ts = _FAILD.get(ip, (0, datetime.now()))
        _FAILD[ip] = (cnt + 1, datetime.now())


def _throttle_ok(ip):
    with _FAILD_LOCK:
        _FAILD.pop(ip, None)


def admin_password_set():
    row = db().execute("SELECT value FROM settings WHERE key='admin_password'").fetchone()
    return bool(row and row['value'])


def set_admin_password(password):
    db().execute("INSERT INTO settings(key, value) VALUES('admin_password', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (_hash_password(password),))
    db().commit()


def issue_admin_token(course_id):
    import uuid
    token = uuid.uuid4().hex
    with LOCK:
        db().execute('INSERT INTO admin_sessions(token, course_id, created_at) VALUES(?,?,?)',
                     (token, course_id, now_str()))
        db().commit()
    return token


def require_admin(course_no, token):
    """管理端鉴权：只认登录时发放的管理员凭证。
    course_no 允许省略——省略时按凭证里记录的课程授权，避免前端漏传课程号就报错。"""
    tk = str(token or '').strip()
    if not tk:
        raise BizError('管理端登录已失效，请重新登录')
    row = db().execute('SELECT * FROM admin_sessions WHERE token=?', (tk,)).fetchone()
    if not row:
        raise BizError('管理端登录已失效，请重新登录')
    cid = row['course_id']
    no = _clean(course_no)
    if no:
        c = db().execute('SELECT * FROM courses WHERE course_no=?', (no,)).fetchone()
        if not c:
            raise BizError('课程不存在：%s' % no)
        if c['id'] != cid:
            raise BizError('当前管理凭证不属于课程 %s，请重新登录该课程' % no)
        return c
    c = db().execute('SELECT * FROM courses WHERE id=?', (cid,)).fetchone()
    if not c:
        raise BizError('登录的课程已被删除，请重新登录')
    return c


def admin_login(course_no, course_name, password='', ip=''):
    no = (course_no or '').strip()
    nm = (course_name or '').strip()
    pwd = str(password or '')
    if not no:
        raise BizError('请填写课程号')
    if not nm:
        raise BizError('请填写课程名称')
    _throttle_check(ip)
    if admin_password_set():
        if not pwd:
            raise BizError('请输入管理员密码')
        stored = db().execute("SELECT value FROM settings WHERE key='admin_password'").fetchone()['value']
        if not _check_password(pwd, stored):
            _throttle_fail(ip)
            raise BizError('管理员密码不正确')
        first_time = False
    else:
        if len(pwd) < 8:
            raise BizError('这是首次使用，请设置管理员密码（至少 8 位）：本次输入的密码将作为管理员密码')
        set_admin_password(pwd)
        first_time = True
    row = db().execute('SELECT * FROM courses WHERE course_no=?', (no,)).fetchone()
    with LOCK:
        if row:
            if row['name'] != nm:
                raise BizError('课程名称与课程号不符：该课程号对应「%s」' % row['name'])
            db().execute('UPDATE courses SET last_login_at=? WHERE id=?', (now_str(), row['id']))
            db().commit()
            cid = row['id']
        else:
            cur = db().execute('INSERT INTO courses(course_no, name, created_at, last_login_at) VALUES(?,?,?,?)',
                               (no, nm, now_str(), now_str()))
            db().commit()
            cid = cur.lastrowid
    _throttle_ok(ip)
    c = db().execute('SELECT * FROM courses WHERE id=?', (cid,)).fetchone()
    return {'course': {'id': c['id'], 'course_no': c['course_no'], 'name': c['name']},
            **course_stats(cid), 'settings': current_settings(),
            'created': row is None, 'admin_token': issue_admin_token(cid),
            'password_first_set': first_time}


def current_settings():
    return {'teacher_max_students': get_setting('teacher_max_students'),
            'teacher_min_classes': get_setting('teacher_min_classes')}


def course_stats(course_id):
    classes = db().execute('SELECT COUNT(*) c, COALESCE(SUM(plan_size),0) s FROM classes WHERE course_id=?',
                           (course_id,)).fetchone()
    teachers = db().execute('SELECT COUNT(*) c FROM course_teachers WHERE course_id=?',
                            (course_id,)).fetchone()
    return {'stats': {'classes': classes['c'], 'students': classes['s'], 'teachers': teachers['c']}}


def list_courses():
    return [dict(r) for r in db().execute(
        'SELECT c.course_no, c.name, c.created_at, c.last_login_at, '
        '(SELECT COUNT(*) FROM classes cl WHERE cl.course_id=c.id) AS classes, '
        '(SELECT COUNT(*) FROM course_teachers ct WHERE ct.course_id=c.id) AS teachers, '
        '(SELECT COUNT(*) FROM classes cl WHERE cl.course_id=c.id AND EXISTS'
        ' (SELECT 1 FROM selections s WHERE s.class_id=cl.id)) AS picked_classes '
        'FROM courses c ORDER BY c.created_at DESC').fetchall()]


def admin_overview(course_no):
    c = require_course(course_no)
    cid = c['id']
    classes = [dict(r) for r in db().execute(
        'SELECT c.*, (SELECT COUNT(*) FROM selections s WHERE s.class_id=c.id) AS taken, '
        '(SELECT GROUP_CONCAT(t.name, "、") FROM selections s JOIN teachers t ON t.id=s.teacher_id '
        ' WHERE s.class_id=c.id) AS teachers, '
        '(SELECT GROUP_CONCAT(s.teacher_id, ",") FROM selections s WHERE s.class_id=c.id) AS teacher_ids, '
        '(SELECT GROUP_CONCAT(s.note, "||") FROM selections s WHERE s.class_id=c.id) AS notes '
        'FROM classes c WHERE c.course_id=? ORDER BY c.campus, c.major, c.name', (cid,)).fetchall()]
    teachers = [dict(r) for r in db().execute(
        'SELECT t.id, t.employee_no, t.name, t.imported, '
        '(SELECT COUNT(*) FROM selections s WHERE s.course_id=? AND s.teacher_id=t.id) AS n, '
        '(SELECT COALESCE(SUM(cl.plan_size),0) FROM selections s JOIN classes cl ON cl.id=s.class_id '
        ' WHERE s.course_id=? AND s.teacher_id=t.id) AS students, '
        "(SELECT tn.note FROM teacher_notes tn WHERE tn.course_id=? AND tn.teacher_id=t.id) AS note "
        'FROM teachers t JOIN course_teachers ct ON ct.teacher_id=t.id AND ct.course_id=? '
        'ORDER BY n DESC, t.name', (cid, cid, cid, cid)).fetchall()]
    total = len(classes)
    taken = sum(1 for x in classes if x['taken'] > 0)
    below = sum(1 for x in classes if x['taken'] < x['min_need'])
    unsel = sum(1 for t in teachers if t['n'] == 0)
    return {
        'course': {'id': cid, 'course_no': c['course_no'], 'name': c['name']},
        'classes': classes,
        'teachers': teachers,
        'stats': {
            'classes': total,
            'selected': taken,
            'left': total - taken,
            'students': sum(x['plan_size'] for x in classes),
            'selected_students': sum(x['plan_size'] for x in classes if x['taken'] > 0),
            'below_min': below,
            'teachers': len(teachers),
            'teachers_unselected': unsel,
        },
        'settings': current_settings(),
    }


def available_classes(course_no, employee_no, name, q='', sort='name', order='asc', token=''):
    c = require_course(course_no)
    t = resolve_teacher({'token': token, 'employee_no': employee_no, 'name': name})
    if not in_roster(c['id'], t['id']):
        raise BizError('您不在本课程的选班教师名单中，请联系课程管理员')
    rows = db().execute(
        'SELECT c.*, (SELECT COUNT(*) FROM selections s WHERE s.class_id=c.id) AS taken '
        'FROM classes c WHERE c.course_id=?', (c['id'],)).fetchall()
    mine = {r['class_id'] for r in db().execute(
        'SELECT class_id FROM selections WHERE course_id=? AND teacher_id=?',
        (c['id'], t['id'])).fetchall()}
    out = []
    for r in rows:
        d = dict(r)
        if d['id'] in mine:
            continue
        if d['taken'] >= d['cap']:
            continue
        out.append(d)
    if q:
        out = [d for d in out if q in d['name'] or q in d['major'] or q in d['college']]
    key = {'name': lambda d: d['name'], 'major': lambda d: d['major'],
           'grade': lambda d: d['grade'], 'size': lambda d: d['plan_size']}.get(sort, lambda d: d['name'])
    out.sort(key=key, reverse=(order == 'desc'))
    return {'teacher': {'employee_no': t['employee_no'], 'name': t['name']},
            'course': {'course_no': c['course_no'], 'name': c['name']},
            'classes': out}


def my_selections(course_no, employee_no, name, token=''):
    c = require_course(course_no)
    t = resolve_teacher({'token': token, 'employee_no': employee_no, 'name': name})
    items = [dict(r) for r in db().execute(
        'SELECT c.id, c.college, c.name, c.plan_size, c.major, c.grade, c.campus, c.cap, c.min_need, '
        's.note, s.created_at FROM selections s JOIN classes c ON c.id=s.class_id '
        'WHERE s.course_id=? AND s.teacher_id=? ORDER BY c.campus, c.name', (c['id'], t['id'])).fetchall()]
    row = db().execute('SELECT note, updated_at FROM teacher_notes WHERE course_id=? AND teacher_id=?',
                       (c['id'], t['id'])).fetchone()
    return {'classes': items, 'teacher_note': (row['note'] if row else ''), 'teacher_note_at': (row['updated_at'] if row else ''),
            'stats': {'classes': len(items), 'students': sum(i['plan_size'] for i in items)}}


def select_classes(course_no, employee_no, name, ids, note='', token=''):
    c = require_course(course_no)
    t = resolve_teacher({'token': token, 'employee_no': employee_no, 'name': name})
    if not in_roster(c['id'], t['id']):
        raise BizError('您不在本课程的选班教师名单中，请联系课程管理员')
    note = (note or '').strip()
    max_students = get_setting('teacher_max_students')
    min_classes = get_setting('teacher_min_classes')
    # 一个班都不选，但写了说明：允许提交，作为“情况说明”留档，不计入最少班数限制
    if not ids:
        if not note:
            raise BizError('请勾选班级；如果本学期不承担本课程，请在备注框写明原因后再提交')
        with LOCK:
            db().execute('INSERT INTO teacher_notes(course_id, teacher_id, note, updated_at) VALUES(?,?,?,?) '
                         'ON CONFLICT(course_id, teacher_id) DO UPDATE SET note=excluded.note, updated_at=excluded.updated_at',
                         (c['id'], t['id'], note, now_str()))
            db().commit()
        st = my_selections(course_no, employee_no, name, token)
        return {'added': 0, 'note_only': True, 'stats': st['stats']}
    with LOCK:
        if DATABASE_URL:
            db().execute('SELECT pg_advisory_xact_lock(20261126)')
        mine = db().execute(
            'SELECT COUNT(*) n, COALESCE(SUM(cl.plan_size),0) s FROM selections s '
            'JOIN classes cl ON cl.id=s.class_id WHERE s.course_id=? AND s.teacher_id=?',
            (c['id'], t['id'])).fetchone()
        adding = []
        for cid in ids:
            row = db().execute('SELECT * FROM classes WHERE id=? AND course_id=?', (cid, c['id'])).fetchone()
            if not row:
                raise BizError('所选班级不属于本课程')
            if db().execute('SELECT 1 FROM selections WHERE class_id=? AND teacher_id=?',
                            (cid, t['id'])).fetchone():
                raise BizError('「%s」已在您的选班列表中' % row['name'])
            taken = db().execute('SELECT COUNT(*) c FROM selections WHERE class_id=?', (cid,)).fetchone()['c']
            if taken >= row['cap']:
                others = db().execute('SELECT GROUP_CONCAT(t.name, "、") FROM selections s '
                                      'JOIN teachers t ON t.id=s.teacher_id WHERE s.class_id=?',
                                      (cid,)).fetchone()[0]
                raise BizError('「%s」已被其他教师选择（%s），不可重复选择' % (row['name'], others or ''))
            adding.append(row)
        new_total = (mine['s'] or 0) + sum(r['plan_size'] for r in adding)
        if max_students > 0 and new_total > max_students:
            raise BizError('每位教师最多 %d 人，本次提交后为 %d 人，超出上限' % (max_students, new_total))
        new_count = (mine['n'] or 0) + len(adding)
        if min_classes > 0 and new_count < min_classes:
            raise BizError('每位教师至少需要选择 %d 个班级，当前 %d 个' % (min_classes, new_count))
        for r in adding:
            db().execute('INSERT INTO selections(course_id, class_id, teacher_id, note, created_at) '
                         'VALUES(?,?,?,?,?)', (c['id'], r['id'], t['id'], note or '', now_str()))
        # 已实际选班，之前“不承担本课程”的说明自动失效
        db().execute('DELETE FROM teacher_notes WHERE course_id=? AND teacher_id=?', (c['id'], t['id']))
        db().commit()
    return {'added': len(adding), 'stats': {'classes': new_count, 'students': new_total}}


def unselect_classes(course_no, employee_no, name, ids, token=''):
    c = require_course(course_no)
    t = resolve_teacher({'token': token, 'employee_no': employee_no, 'name': name})
    with LOCK:
        removed = 0
        for cid in ids:
            cur = db().execute('DELETE FROM selections WHERE course_id=? AND class_id=? AND teacher_id=?',
                               (c['id'], cid, t['id']))
            removed += cur.rowcount
        db().commit()
    if not removed:
        raise BizError('该班级不在您的选班列表中')
    st = my_selections(course_no, employee_no, name, token)
    return {'removed': removed, 'stats': st['stats']}


def save_note(course_no, employee_no, name, class_id, note, token=''):
    c = require_course(course_no)
    t = resolve_teacher({'token': token, 'employee_no': employee_no, 'name': name})
    with LOCK:
        cur = db().execute('UPDATE selections SET note=? WHERE course_id=? AND class_id=? AND teacher_id=?',
                           ((note or '').strip(), c['id'], class_id, t['id']))
        db().commit()
    if cur.rowcount == 0:
        raise BizError('该班级不在您的选班列表中')
    return {'ok': True}


def set_caps(course_no, ids, cap, min_need, items=None):
    c = require_course(course_no)
    if items:
        with LOCK:
            for it in items:
                cid = int(it.get('id'))
                cp = int(it.get('cap'))
                mn = int(it.get('min_need', 0) or 0)
                if cp < 1:
                    raise BizError('选班上限至少为 1（班级 id=%s）' % cid)
                if mn < 0:
                    raise BizError('下限不能为负数（班级 id=%s）' % cid)
                db().execute('UPDATE classes SET cap=?, min_need=? WHERE id=? AND course_id=?',
                             (cp, mn, cid, c['id']))
            db().commit()
        return {'ok': True}
    cap = int(cap)
    min_need = int(min_need)
    if cap < 1:
        raise BizError('选班上限至少为 1')
    if min_need < 0:
        raise BizError('下限不能为负数')
    with LOCK:
        if ids:
            for cid in ids:
                db().execute('UPDATE classes SET cap=?, min_need=? WHERE id=? AND course_id=?',
                             (cap, min_need, cid, c['id']))
        else:
            db().execute('UPDATE classes SET cap=?, min_need=? WHERE course_id=?', (cap, min_need, c['id']))
        db().commit()
    return {'ok': True}


# ---------------------------------------------------------------- 导入
COL_ALIASES = {
    'college': ['学院', '院系', '学院名称'],
    'name': ['班级', '班级名称', '教学班'],
    'size': ['计划人数', '实际上课人数', '人数', '班级人数'],
    'major': ['专业简称', '专业'],
    'grade': ['年级'],
    'campus': ['校区', '校区名称'],
}

TEACHER_ALIASES = {
    'name': ['姓名', '教师姓名', '教师', '老师', '选课教师'],
    'no': ['工号', '教师工号', '编号', '账号'],
}


def read_grid(filename, data):
    ext = filename.lower().rsplit('.', 1)[-1]
    raw = []
    if ext in ('xlsx', 'xlsm'):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        ws = wb[wb.sheetnames[0]]
        raw = [[c for c in row] for row in ws.iter_rows(values_only=True)]
    elif ext in ('csv', 'txt'):
        text = None
        for enc in ('utf-8-sig', 'gbk', 'utf-8'):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise BizError('文件编码无法识别，请另存为 UTF-8 或 xlsx')
        raw = list(__import__('csv').reader(io.StringIO(text)))
    else:
        raise BizError('只支持 .xlsx 或 .csv 文件')
    if not raw:
        raise BizError('文件内容为空')
    return raw


def parse_classes_table(filename, data):
    raw = read_grid(filename, data)
    header = [str(h or '').strip() for h in raw[0]]
    idx = {}
    for key, names in COL_ALIASES.items():
        for n in names:
            if n in header:
                idx[key] = header.index(n)
                break
    missing = [k for k in ('name', 'size') if k not in idx]
    if missing:
        raise BizError('表头缺少必需列：班级、计划人数（可用模板重新导出）')
    out = []
    for row in raw[1:]:
        if not any(row):
            continue

        def pick(k):
            i = idx.get(k)
            return row[i] if i is not None and i < len(row) else ''
        out.append((pick('college'), pick('name'), pick('size'), pick('major'), pick('grade'), pick('campus')))
    return out


def parse_teachers_table(filename, data):
    raw = read_grid(filename, data)
    header = [str(h or '').strip() for h in raw[0]]
    idx = {}
    for key, names in TEACHER_ALIASES.items():
        for n in names:
            if n in header:
                idx[key] = header.index(n)
                break
    if 'name' not in idx:
        raise BizError('表头缺少必需列：姓名（可用教师名单模板重新导出）')
    out = []
    for row in raw[1:]:
        if not any(row):
            continue
        i = idx['name']
        name = str(row[i] if i < len(row) and row[i] is not None else '').strip()
        if not name:
            continue
        j = idx.get('no')
        no = str(row[j] if j is not None and j < len(row) and row[j] is not None else '').strip()
        out.append((name, no))
    return out


def import_classes(course_no, rows, mode='skip'):
    c = require_course(course_no)
    added, updated, dups, errors = 0, 0, [], []
    seen = set()
    with LOCK:
        for idx, r in enumerate(rows, 2):
            college, name, size, major, grade, campus = r
            name = (name or '').strip()
            if not name:
                continue
            try:
                size = int(float(size))
                if size <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append('第 %d 行「%s」人数不是正整数' % (idx, name))
                continue
            if name in seen:
                dups.append(name)
                continue
            seen.add(name)
            exists = db().execute('SELECT id FROM classes WHERE course_id=? AND name=?',
                                  (c['id'], name)).fetchone()
            if exists:
                if mode == 'overwrite':
                    db().execute('UPDATE classes SET college=?, plan_size=?, major=?, grade=?, campus=? '
                                 'WHERE id=?',
                                 (str(college or ''), size, str(major or ''), str(grade or ''),
                                  str(campus or ''), exists['id']))
                    updated += 1
                else:
                    dups.append(name)
                continue
            db().execute('INSERT INTO classes(course_id,college,name,plan_size,major,grade,campus) '
                         'VALUES(?,?,?,?,?,?,?)',
                         (c['id'], str(college or ''), name, size, str(major or ''),
                          str(grade or ''), str(campus or '')))
            added += 1
        db().commit()
    msg = '导入完成：新增 %d 个班，更新 %d 个班' % (added, updated)
    if dups:
        msg += '，重复跳过 %d 个（%s%s）' % (len(dups), '、'.join(dups[:3]), '…' if len(dups) > 3 else '')
    if errors:
        msg += '；%d 行有问题（%s）' % (len(errors), '；'.join(errors[:3]))
    return {'added': added, 'updated': updated, 'duplicates': dups, 'errors': errors, 'message': msg}


def import_teachers(course_no, rows, mode='skip'):
    c = require_course(course_no)
    added, linked, updated, dups, errors = 0, 0, 0, [], []
    seen = set()
    with LOCK:
        for idx, r in enumerate(rows, 2):
            name = norm_name(r[0])
            no = norm_no(r[1]) if len(r) > 1 else ''
            if not name:
                errors.append('第 %d 行姓名为空' % idx)
                continue
            if not no:
                errors.append('第 %d 行（%s）缺少工号，登录需要工号+姓名同时匹配' % (idx, name))
                continue
            key = (no, name)
            if key in seen:
                dups.append(name)
                continue
            seen.add(key)
            if no:
                row = db().execute('SELECT * FROM teachers WHERE employee_no=?', (no,)).fetchone()
            else:
                row = db().execute("SELECT * FROM teachers WHERE employee_no='' AND name=?", (name,)).fetchone()
            if row:
                tid = row['id']
                if row['name'] != name:
                    # 同一工号换了姓名，按名单为准
                    db().execute('UPDATE teachers SET name=? WHERE id=?', (name, tid))
                    updated += 1
                elif mode == 'overwrite' and not row['imported']:
                    db().execute('UPDATE teachers SET imported=1 WHERE id=?', (tid,))
                    updated += 1
            else:
                cur = db().execute('INSERT INTO teachers(employee_no, name, created_at, imported) '
                                   'VALUES(?,?,?,1)', (no, name, now_str()))
                tid = cur.lastrowid
                added += 1
            existed = db().execute('SELECT 1 FROM course_teachers WHERE course_id=? AND teacher_id=?',
                                   (c['id'], tid)).fetchone()
            db().execute('INSERT OR IGNORE INTO course_teachers(course_id, teacher_id, imported_at) '
                         'VALUES(?,?,?)', (c['id'], tid, now_str()))
            if not existed:
                linked += 1
            elif not row:
                pass
            else:
                dups.append(name)
        db().commit()
    msg = '导入完成：新增教师 %d 人，加入本课程 %d 人，更新 %d 条' % (added, linked, updated)
    if dups:
        msg += '；已在名单中 %d 人（%s%s）' % (len(dups), '、'.join(dups[:3]), '…' if len(dups) > 3 else '')
    if errors:
        msg += '；%d 行有问题（%s）' % (len(errors), '；'.join(errors[:3]))
    return {'added': added, 'linked': linked, 'updated': updated,
            'duplicates': dups, 'errors': errors, 'message': msg}


def add_teacher(course_no, employee_no, name):
    """单个添加教师到本课程名单"""
    c = require_course(course_no)
    no = norm_no(employee_no)
    nm = norm_name(name)
    if not nm:
        raise BizError('请填写教师姓名')
    if not no:
        raise BizError('请填写工号：教师登录需要工号和姓名同时匹配，没有工号将无法登录')
    if no and not no.isalnum():
        raise BizError('工号只能包含字母或数字')
    with LOCK:
        if no:
            row = db().execute('SELECT * FROM teachers WHERE employee_no=?', (no,)).fetchone()
        else:
            row = db().execute("SELECT * FROM teachers WHERE employee_no='' AND name=?", (nm,)).fetchone()
        renamed = ''
        if row:
            tid = row['id']
            if row['name'] != nm:
                renamed = row['name']
                db().execute('UPDATE teachers SET name=? WHERE id=?', (nm, tid))
            db().execute('UPDATE teachers SET imported=1 WHERE id=?', (tid,))
        else:
            cur = db().execute('INSERT INTO teachers(employee_no, name, created_at, imported) '
                               'VALUES(?,?,?,1)', (no, nm, now_str()))
            tid = cur.lastrowid
        existed = db().execute('SELECT 1 FROM course_teachers WHERE course_id=? AND teacher_id=?',
                               (c['id'], tid)).fetchone()
        db().execute('INSERT OR IGNORE INTO course_teachers(course_id, teacher_id, imported_at) '
                     'VALUES(?,?,?)', (c['id'], tid, now_str()))
        db().commit()
    if renamed:
        msg = '工号「%s」原登记姓名为「%s」，已按本次姓名改为「%s」%s' % (
            no, renamed, nm, '（该教师已在课程名单中）' if existed else '，并加入本课程名单')
    elif existed:
        msg = '「%s」已在本次课程名单中，无需重复添加' % nm
    else:
        msg = '已添加教师「%s」（工号 %s），已加入本课程名单' % (nm, no)
    return {'added': not existed, 'message': msg,
            'teacher': {'id': tid, 'employee_no': no, 'name': nm}}


def remove_teacher(course_no, teacher_id):
    """把教师移出本课程名单；已选班的教师不允许直接移出"""
    c = require_course(course_no)
    tid = int(teacher_id)
    t = db().execute('SELECT * FROM teachers WHERE id=?', (tid,)).fetchone()
    if not t:
        raise BizError('教师不存在')
    if not in_roster(c['id'], tid):
        raise BizError('该教师不在本课程名单中')
    n = db().execute('SELECT COUNT(*) c FROM selections WHERE course_id=? AND teacher_id=?',
                     (c['id'], tid)).fetchone()['c']
    if n:
        raise BizError('「%s」在本次课程已选 %d 个班，请先撤销其选班（或在教师端撤销）后再移出名单'
                       % (t['name'], n))
    with LOCK:
        db().execute('DELETE FROM course_teachers WHERE course_id=? AND teacher_id=?', (c['id'], tid))
        db().commit()
    return {'message': '已把「%s」移出本课程名单（其账号信息保留，其他课程不受影响）' % t['name']}


# ---------------------------------------------------------------- 导出
def _style_sheet(sheet, widths):
    from openpyxl.styles import Font, PatternFill, Alignment
    for cell in sheet[1]:
        cell.font = Font(name='微软雅黑', size=11, bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='3370FF')
        cell.alignment = Alignment(horizontal='center', vertical='center')
    sheet.freeze_panes = 'A2'
    for i, w in enumerate(widths):
        sheet.column_dimensions[chr(65 + i)].width = w


def export_result(course_no):
    import openpyxl
    c = require_course(course_no)
    cid = c['id']
    rows = db().execute(
        'SELECT t.name AS teacher, t.employee_no, c.campus, c.college, c.name AS cls, c.major, c.grade, '
        'c.plan_size, s.note, s.created_at FROM selections s JOIN classes c ON c.id=s.class_id '
        'JOIN teachers t ON t.id=s.teacher_id WHERE s.course_id=? '
        'ORDER BY t.name, c.campus, c.name', (cid,)).fetchall()
    left = db().execute(
        'SELECT c.campus, c.college, c.name AS cls, c.major, c.grade, c.plan_size FROM classes c '
        'WHERE c.course_id=? AND NOT EXISTS (SELECT 1 FROM selections s WHERE s.class_id=c.id) '
        'ORDER BY c.campus, c.major, c.name', (cid,)).fetchall()
    teachers = db().execute(
        'SELECT t.name, t.employee_no, '
        '(SELECT COUNT(*) FROM selections s WHERE s.course_id=? AND s.teacher_id=t.id) n, '
        '(SELECT COALESCE(SUM(cl.plan_size),0) FROM selections s JOIN classes cl ON cl.id=s.class_id '
        ' WHERE s.course_id=? AND s.teacher_id=t.id) students, '
        '(SELECT tn.note FROM teacher_notes tn WHERE tn.course_id=? AND tn.teacher_id=t.id) note '
        'FROM teachers t JOIN course_teachers ct ON ct.teacher_id=t.id AND ct.course_id=? '
        'ORDER BY n DESC, t.name', (cid, cid, cid, cid)).fetchall()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '选班明细'
    ws.append(['教师', '工号', '校区', '学院', '班级', '专业简称', '年级', '计划人数', '排课备注', '选班时间'])
    for r in rows:
        ws.append([r['teacher'], r['employee_no'], r['campus'], r['college'], r['cls'], r['major'],
                   r['grade'], r['plan_size'], r['note'] or '', r['created_at']])
    ws2 = wb.create_sheet('未选班级')
    ws2.append(['校区', '学院', '班级', '专业简称', '年级', '计划人数'])
    for r in left:
        ws2.append([r['campus'], r['college'], r['cls'], r['major'], r['grade'], r['plan_size']])
    ws3 = wb.create_sheet('教师汇总')
    ws3.append(['教师', '工号', '已选班级数', '合计人数', '状态', '情况说明'])
    for r in teachers:
        ws3.append([r['name'], r['employee_no'], r['n'], r['students'],
                    '已选班' if r['n'] > 0 else '未选班', r['note'] or ''])
    ws4 = wb.create_sheet('未选班教师')
    ws4.append(['教师', '工号', '状态', '情况说明'])
    unsel = [r for r in teachers if r['n'] == 0]
    for r in unsel:
        ws4.append([r['name'], r['employee_no'], '未选班', r['note'] or ''])
    if not unsel:
        ws4.append(['（无未选班教师）', '', '', ''])
    _style_sheet(ws, [12, 14, 10, 22, 14, 12, 8, 10, 30, 18])
    _style_sheet(ws2, [10, 22, 14, 12, 8, 10])
    _style_sheet(ws3, [12, 14, 14, 12, 10, 36])
    _style_sheet(ws4, [12, 14, 10, 36])
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def export_teachers_list(course_no):
    import openpyxl
    c = require_course(course_no)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '选班教师名单'
    ws.append(['工号', '姓名', '已选班级数', '合计人数', '状态', '情况说明'])
    rows = db().execute(
        'SELECT t.employee_no, t.name, '
        '(SELECT COUNT(*) FROM selections s WHERE s.course_id=? AND s.teacher_id=t.id) n, '
        '(SELECT COALESCE(SUM(cl.plan_size),0) FROM selections s JOIN classes cl ON cl.id=s.class_id '
        ' WHERE s.course_id=? AND s.teacher_id=t.id) students, '
        '(SELECT tn.note FROM teacher_notes tn WHERE tn.course_id=? AND tn.teacher_id=t.id) note '
        'FROM teachers t JOIN course_teachers ct ON ct.teacher_id=t.id AND ct.course_id=? '
        'ORDER BY n DESC, t.name', (c['id'], c['id'], c['id'], c['id'])).fetchall()
    for r in rows:
        ws.append([r['employee_no'], r['name'], r['n'], r['students'],
                   '已选班' if r['n'] > 0 else '未选班', r['note'] or ''])
    _style_sheet(ws, [14, 12, 14, 12, 10, 36])
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def export_classes_template():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '专业班级'
    ws.append(['学院', '班级', '计划人数', '专业简称', '年级', '校区'])
    for r in [['计算机科学与技术学院', '计科2501', 32, '计科类', '2025', '西区'],
              ['材料与化学学院', '材料2501', 28, '材料', '2025', '西区']]:
        ws.append(r)
    _style_sheet(ws, [26, 14, 12, 14, 8, 10])
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def export_teachers_template():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '选班教师名单'
    ws.append(['姓名', '工号'])
    for r in [['张老师', '2025001'], ['李老师', '2025002']]:
        ws.append(r)
    _style_sheet(ws, [18, 16])
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ---------------------------------------------------------------- 重置
def reset_course_selections(course_no):
    c = require_course(course_no)
    with LOCK:
        db().execute('DELETE FROM selections WHERE course_id=?', (c['id'],))
        db().commit()
    return {'ok': True}


def reset_course(course_no):
    """清空该课程的班级、教师名单与选班记录（课程本身保留）"""
    c = require_course(course_no)
    with LOCK:
        db().execute('DELETE FROM selections WHERE course_id=?', (c['id'],))
        db().execute('DELETE FROM course_teachers WHERE course_id=?', (c['id'],))
        db().execute('DELETE FROM classes WHERE course_id=?', (c['id'],))
        db().commit()
    return {'ok': True}


def reset_all():
    with LOCK:
        db().execute('DELETE FROM selections')
        db().execute('DELETE FROM course_teachers')
        db().execute('DELETE FROM classes')
        db().execute('DELETE FROM teachers')
        db().execute('DELETE FROM courses')
        db().commit()
    return {'ok': True}


# ---------------------------------------------------------------- HTTP
def parse_multipart(body, boundary):
    fields, files = {}, {}
    for part in body.split(b'--' + boundary):
        if not part.strip(b'\r\n-'):
            continue
        if b'\r\n\r\n' not in part:
            continue
        head, data = part.split(b'\r\n\r\n', 1)
        data = data.rstrip(b'\r\n')
        m = __import__('re').search(rb'name="([^"]*)"', head)
        fn = __import__('re').search(rb'filename="([^"]*)"', head)
        key = m.group(1).decode('utf-8', 'ignore') if m else ''
        if fn:
            files[key] = (fn.group(1).decode('utf-8', 'ignore'), data)
        else:
            fields[key] = data.decode('utf-8', 'ignore')
    return fields, files


class Handler(BaseHTTPRequestHandler):
    server_version = 'ClassPick/2.0'

    def finish(self):
        try:
            super().finish()
        finally:
            conn = getattr(_LOCAL, 'conn', None)
            if conn is not None:
                conn.rollback()
                conn.close()
                _LOCAL.conn = None


    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype='application/json; charset=utf-8', extra=None):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Referrer-Policy', 'same-origin')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def client_ip(self):
        """nginx 反代时取真实客户端 IP（仅用于登录失败限流，伪造无实际收益）"""
        xff = (self.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
        return xff or (self.client_address[0] if self.client_address else '?')

    def _err(self, msg, code=400):
        self._json({'ok': False, 'error': msg}, code)

    def _xlsx(self, data, filename):
        self._send(200, data, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                   {'Content-Disposition': "attachment; filename=\"export.xlsx\"; filename*=UTF-8''"
                    + quote(filename)})

    def _file(self, name):
        path = os.path.join(BASE_DIR, 'web', name)
        if not os.path.exists(path):
            return self._err('页面不存在', 404)
        ctype = {'html': 'text/html; charset=utf-8', 'js': 'application/javascript; charset=utf-8',
                 'css': 'text/css; charset=utf-8'}.get(name.rsplit('.', 1)[-1], 'application/octet-stream')
        with open(path, 'rb') as f:
            self._send(200, f.read(), ctype)

    def do_GET(self):
        u = urlparse(self.path)
        path, qs = u.path, parse_qs(u.query)
        try:
            if path == '/healthz':
                db().execute('SELECT 1').fetchone()
                return self._json({'ok': True})
            if path in ('/', '/index.html'):
                return self._file('index.html')
            if path == '/admin':
                return self._file('admin.html')
            if path.startswith('/static/'):
                return self._file(path.split('/')[-1])
            if not path.startswith('/api/'):
                return self._err('页面不存在', 404)
            return self._api_get(path, qs)
        except BizError as e:
            if e.msg not in ('未知接口',):
                print('[api-get] %s -> %s' % (path, e.msg), flush=True)
            return self._err(e.msg)
        except Exception:
            traceback.print_exc()
            return self._err('服务器内部错误', 500)

    def do_POST(self):
        u = urlparse(self.path)
        path = u.path
        length = int(self.headers.get('Content-Length') or 0)
        if length > 32 * 1024 * 1024:
            return self._err('上传内容过大（上限 32MB）', 413)
        ctype = self.headers.get('Content-Type') or ''
        body = self.rfile.read(length) if length else b''
        files = {}
        try:
            if ctype.startswith('multipart/form-data'):
                boundary = ctype.split('boundary=')[-1].encode()
                fields, files = parse_multipart(body, boundary)
                payload = fields
            else:
                payload = json.loads(body.decode('utf-8')) if body else {}
            return self._api_post(path, payload, files)
        except BizError as e:
            print('[api-post] %s -> %s' % (path, e.msg), flush=True)
            return self._err(e.msg)
        except Exception:
            traceback.print_exc()
            return self._err('服务器内部错误', 500)

    @staticmethod
    def g(qs, key, default=''):
        return qs.get(key, [default])[0]

    def _api_get(self, path, qs):
        if path == '/api/admin/courses':
            return self._json({'ok': True, 'courses': list_courses(), 'settings': current_settings(),
                               'password_set': admin_password_set()})
        if path == '/api/admin/overview':
            c = require_admin(self.g(qs, 'course_no'), self.g(qs, 'admin_token'))
            return self._json({'ok': True, **admin_overview(c['course_no'])})
        if path == '/api/export':
            c = require_admin(self.g(qs, 'course_no'), self.g(qs, 'admin_token'))
            return self._xlsx(export_result(c['course_no']), '选班结果-%s.xlsx' % c['course_no'])
        if path == '/api/admin/template':
            return self._xlsx(export_classes_template(), '专业班级导入模板.xlsx')
        if path == '/api/admin/teacher_template':
            return self._xlsx(export_teachers_template(), '选班教师名单模板.xlsx')
        if path == '/api/admin/teacher_export':
            c = require_admin(self.g(qs, 'course_no'), self.g(qs, 'admin_token'))
            return self._xlsx(export_teachers_list(c['course_no']), '选班教师名单-%s.xlsx' % c['course_no'])
        if path == '/api/teacher/classes':
            return self._json({'ok': True, **available_classes(
                self.g(qs, 'course_no'), self.g(qs, 'no'), self.g(qs, 'name'),
                self.g(qs, 'q'), self.g(qs, 'sort'), self.g(qs, 'order'), self.g(qs, 'token'))})
        if path == '/api/teacher/mine':
            return self._json({'ok': True, **my_selections(
                self.g(qs, 'course_no'), self.g(qs, 'no'), self.g(qs, 'name'), self.g(qs, 'token'))})
        if path == '/api/admin/login_log':
            require_admin(self.g(qs, 'course_no'), self.g(qs, 'admin_token'))
            return self._json({'ok': True, 'items': recent_logins(30)})
        if path == '/api/health':
            return self._json({'ok': True})
        return self._err('未知接口', 404)

    def _api_post(self, path, payload, files):
        if path == '/api/admin/login':
            return self._json({'ok': True, **admin_login(
                payload.get('course_no'), payload.get('course_name'),
                payload.get('password'), self.client_ip())})
        if path == '/api/admin/password':
            c = require_admin(payload.get('course_no'), payload.get('admin_token'))
            old = str(payload.get('old_password') or '')
            new = str(payload.get('new_password') or '')
            stored = db().execute("SELECT value FROM settings WHERE key='admin_password'").fetchone()['value']
            if not _check_password(old, stored):
                raise BizError('原密码不正确')
            if len(new) < 8:
                raise BizError('新密码至少 8 位')
            set_admin_password(new)
            return self._json({'ok': True, 'message': '管理员密码已更新，其他已登录的管理端会话需重新登录'})
        if path == '/api/teacher/login':
            return self._json({'ok': True, **teacher_login(payload.get('employee_no'), payload.get('name'))})
        if path == '/api/teacher/select':
            ids = [int(i) for i in payload.get('ids', []) if str(i).isdigit()]
            return self._json({'ok': True, **select_classes(
                payload.get('course_no'), payload.get('employee_no'), payload.get('name'),
                ids, payload.get('note', ''), payload.get('token'))})
        if path == '/api/teacher/unselect':
            ids = [int(i) for i in payload.get('ids', []) if str(i).isdigit()]
            return self._json({'ok': True, **unselect_classes(
                payload.get('course_no'), payload.get('employee_no'), payload.get('name'), ids,
                payload.get('token'))})
        if path == '/api/teacher/note':
            return self._json({'ok': True, **save_note(
                payload.get('course_no'), payload.get('employee_no'), payload.get('name'),
                int(payload.get('class_id')), payload.get('note', ''), payload.get('token'))})
        if path == '/api/admin/caps':
            c = require_admin(payload.get('course_no'), payload.get('admin_token'))
            ids = [int(i) for i in payload.get('ids', []) if str(i).isdigit()]
            return self._json({'ok': True, **set_caps(
                c['course_no'], ids, payload.get('cap'), payload.get('min_need', 0),
                items=payload.get('items')) })
        if path == '/api/admin/settings':
            require_admin(payload.get('course_no'), payload.get('admin_token'))
            key = payload.get('key')
            if key not in DEFAULT_SETTINGS:
                raise BizError('未知设置项')
            db().execute('UPDATE settings SET value=? WHERE key=?', (str(int(payload.get('value'))), key))
            db().commit()
            return self._json({'ok': True})
        if path == '/api/admin/import':
            c = require_admin(payload.get('course_no'), payload.get('admin_token'))
            f = files.get('file')
            if not f:
                raise BizError('请选择要导入的文件')
            rows = parse_classes_table(f[0], f[1])
            return self._json({'ok': True, **import_classes(
                c['course_no'], rows, payload.get('mode', 'skip'))})
        if path == '/api/admin/import_teachers':
            c = require_admin(payload.get('course_no'), payload.get('admin_token'))
            f = files.get('file')
            if not f:
                raise BizError('请选择要导入的文件')
            rows = parse_teachers_table(f[0], f[1])
            return self._json({'ok': True, **import_teachers(
                c['course_no'], rows, payload.get('mode', 'skip'))})
        if path == '/api/admin/add_teacher':
            c = require_admin(payload.get('course_no'), payload.get('admin_token'))
            return self._json({'ok': True, **add_teacher(
                c['course_no'], payload.get('employee_no'), payload.get('name'))})
        if path == '/api/admin/remove_teacher':
            c = require_admin(payload.get('course_no'), payload.get('admin_token'))
            return self._json({'ok': True, **remove_teacher(
                c['course_no'], payload.get('teacher_id'))})
        if path == '/api/admin/reset':
            c = require_admin(payload.get('course_no'), payload.get('admin_token'))
            return self._json({'ok': True, **reset_course_selections(c['course_no'])})
        if path == '/api/admin/reset_course':
            c = require_admin(payload.get('course_no'), payload.get('admin_token'))
            return self._json({'ok': True, **reset_course(c['course_no'])})
        if path == '/api/admin/reset_all':
            require_admin(payload.get('course_no'), payload.get('admin_token'))
            return self._json({'ok': True, **reset_all()})
        return self._err('未知接口', 404)


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 128


def lan_ip():
    """取本机在内网/公网可访问的地址，方便把网址发给老师"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return ''


def main():
    import sys
    global HOST, PORT
    if '--set-password' in sys.argv:
        idx = sys.argv.index('--set-password')
        pwd = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else ''
        if len(pwd) < 8:
            print('管理员密码至少 8 位')
            return
        set_admin_password(pwd)
        print('管理员密码已更新')
        return
    for flag, name in (('--host', 'HOST'), ('--port', 'PORT')):
        if flag in sys.argv:
            idx = sys.argv.index(flag)
            val = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else ''
            if name == 'HOST' and val:
                HOST = val
            elif name == 'PORT' and val.isdigit():
                PORT = int(val)
    snap = startup_snapshot()
    # 只有在“本次启动前数据库还不存在”（真正首次安装）或显式 --seed-test 时，才导入测试数据
    if '--seed-test' in sys.argv:
        n = seed_default_course(force=True)
        if n < 0:
            print('[init] 找不到种子文件 测试数据.xlsx，未创建默认课程（请用管理端导入班级）')
        else:
            print('[init] 已按 --seed-test 重建默认课程并导入 %d 个测试班级' % n)
    elif not DB_PREEXISTED:
        n = seed_default_course()
        if n < 0:
            print('[init] 首次启动：没有 测试数据.xlsx，跳过默认课程导入（建课程请用管理端登录）')
        elif n:
            print('[init] 首次安装：已创建默认课程 %s 并导入 %d 个班级' % (DEFAULT_COURSE_NO, n))
    else:
        n = 0      # 数据库已存在：绝不动数据，直接读里面最后一次的状态

    print('')
    print('数据库：%s' % ('Supabase PostgreSQL' if DATABASE_URL else DB_PATH))
    print('启动快照：%s' % (snap or '（首次运行，暂无快照）'))
    s = data_summary()
    print('现有数据：课程 %d · 班级 %d · 教师 %d · 选班记录 %d' % (
        s['课程'], s['班级'], s['教师'], s['选班记录']))
    if s['课程'] == 0:
        old = newest_snapshot()
        print('！警告：数据库里没有任何课程。如果不是首次安装，说明程序读到的不是原来那个数据库文件。')
        if old:
            print('  最近的启动快照可以回滚：%s' % old)
        print('  确认要重新导入测试数据，请用：python app.py --seed-test')
    if not DATABASE_URL and (os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv')):
        print('！注意：当前运行在容器里。若启动命令没有把数据库挂载到宿主机，容器重建后数据会丢。')
        print('  正确做法：docker run -v /宿主机/data:/app/data -e JXB_DB=/app/data/选班系统.db ...')
    if os.environ.get('JXB_DB'):
        print('数据库路径来自环境变量 JXB_DB（请确认指向持久化目录）')
    print('')

    srv = Server((HOST, PORT), Handler)
    local = 'http://127.0.0.1:%d' % PORT
    print('教师选班系统已启动： %s   （管理端 %s/admin）' % (local, local))
    if HOST in ('0.0.0.0', '', '::'):
        ip = lan_ip()
        if ip:
            print('对外访问地址： http://%s:%d   （同一网络的电脑/手机直接输这个地址）' % (ip, PORT))
    print('管理员密码：%s' % ('已设置' if admin_password_set() else '未设置（首次登录时设置）'))
    print('按 Ctrl+C 停止服务')
    if '--open' in sys.argv:
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(local)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
    finally:
        srv.server_close()


if __name__ == '__main__':
    main()
