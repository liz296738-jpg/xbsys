"""Deployment check: exercise the real database and roll back test records."""
import io
import uuid
import openpyxl
import app
from postgres_backend import Connection


def main():
    conn = Connection(app.DATABASE_URL)
    conn.commit = lambda: None
    app.db = lambda: conn
    suffix = uuid.uuid4().hex[:12]
    course_no = 'TEST-' + suffix
    try:
        conn.execute("INSERT INTO courses(course_no,name,created_at) VALUES(?,?,?)",
                     (course_no, '部署检查', app.now_str()))
        cid = app.course_of(course_no)['id']
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", ('check-' + suffix, '1'))
        assert conn.execute('SELECT COUNT(*) c FROM courses WHERE id=?', (cid,)).fetchone()['c'] == 1
        tid = conn.execute('INSERT INTO teachers(employee_no,name,created_at,imported) VALUES(?,?,?,1)',
                           (suffix, '部署检查教师', app.now_str())).lastrowid
        conn.execute('INSERT INTO course_teachers(course_id,teacher_id,imported_at) VALUES(?,?,?)',
                     (cid, tid, app.now_str()))
        ids = []
        for index in range(2):
            ids.append(conn.execute('INSERT INTO classes(course_id,college,name,plan_size,major,grade,campus) VALUES(?,?,?,?,?,?,?)',
                                    (cid, '测试学院', f'检查班级{index}', 10, '测试', '2026', '测试校区')).lastrowid)
        # Test fixture settings stay inside this transaction and are rolled back.
        conn.execute("UPDATE settings SET value='2' WHERE key='teacher_min_classes'")
        conn.execute("UPDATE settings SET value='100' WHERE key='teacher_max_students'")
        try:
            app.select_classes(course_no, suffix, '部署检查教师', [])
            raise AssertionError('Empty submission was accepted')
        except app.BizError:
            pass
        explanation = '本学期不承担本课程（部署检查）'
        note_result = app.select_classes(course_no, suffix, '部署检查教师', [], explanation)
        assert note_result['note_only'] and note_result['added'] == 0
        assert app.my_selections(course_no, suffix, '部署检查教师')['teacher_note'] == explanation
        assert app.admin_overview(course_no)['teachers'][0]['note'] == explanation
        workbook = openpyxl.load_workbook(io.BytesIO(app.export_result(course_no)))
        assert workbook['教师汇总'].cell(2, 6).value == explanation
        assert workbook['未选班教师'].cell(2, 4).value == explanation
        teachers_export = openpyxl.load_workbook(io.BytesIO(app.export_teachers_list(course_no)))
        assert teachers_export.active.cell(2, 6).value == explanation
        admin_token = app.issue_admin_token(cid)
        assert app.require_admin('', admin_token)['id'] == cid
        assert app.require_admin(course_no, admin_token)['id'] == cid
        other_id = conn.execute('INSERT INTO courses(course_no,name,created_at) VALUES(?,?,?)',
                                ('OTHER-' + suffix, '其他课程', app.now_str())).lastrowid
        try:
            app.require_admin('OTHER-' + suffix, admin_token)
            raise AssertionError('Cross-course administrator access was accepted')
        except app.BizError:
            pass
        result = app.select_classes(course_no, suffix, '部署检查教师', ids)
        assert result['added'] == 2
        assert app.my_selections(course_no, suffix, '部署检查教师')['teacher_note'] == ''
        overview = app.admin_overview(course_no)
        assert len(overview['classes']) == 2
        assert overview['classes'][0]['teachers'] == '部署检查教师'
        assert app.my_selections(course_no, suffix, '部署检查教师')['stats']['classes'] == 2
        assert app.available_classes(course_no, suffix, '部署检查教师')
        assert openpyxl.load_workbook(io.BytesIO(app.export_result(course_no))).sheetnames
        try:
            app.select_classes(course_no, suffix, '部署检查教师', ids)
            raise AssertionError('Duplicate selection was accepted')
        except app.BizError:
            pass
        app.log_login(suffix, '部署检查教师', True, '临时验证')
        assert app.recent_logins(1)[0]['input_no'] == suffix
        assert app.unselect_classes(course_no, suffix, '部署检查教师', ids)['removed'] == 2
        try:
            app.admin_login('DENIED-' + suffix, '未授权课程', 'invalid-password')
            raise AssertionError('Invalid administrator password was accepted')
        except app.BizError:
            assert conn.execute('SELECT 1 FROM courses WHERE course_no=?', ('DENIED-' + suffix,)).fetchone() is None
        snapshot = app.startup_snapshot()
        assert snapshot.startswith('PostgreSQL 启动快照 #')
        saved = conn.execute('SELECT payload FROM startup_snapshots ORDER BY id DESC LIMIT 1').fetchone()['payload']
        assert any(c['course_no'] == course_no for c in saved['courses'])
        conn.rollback()
        assert conn.execute('SELECT 1 FROM courses WHERE course_no=?', (course_no,)).fetchone() is None
        print('PostgreSQL integration checks passed: note-only submissions and Excel exports, note clearing after selection, course authorization, startup snapshots, selection rules, login history and rollback.', flush=True)
    finally:
        conn.rollback()
        conn.close()


if __name__ == '__main__':
    main()
