/* 管理端逻辑：课程号+课程名登录 → 课程内总览/教师情况/导入/上下限/导出 */
const $ = (s) => document.querySelector(s);
const STORE_KEY = 'jxb_admin';
const PAGE_SIZE = 40;
const state = {
  course: null,
  token: '',
  data: { classes: [], teachers: [], stats: {} },
  page: 1,
  capPicked: new Set(),
  curTeacherId: null,
  tab: 'overview'
};

function toast(msg, kind) {
  const el = document.createElement('div');
  el.className = 'toast ' + (kind || '');
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

const NO_TOKEN_EXACT = ['/api/admin/login', '/api/admin/courses'];
const NO_TOKEN_PREFIX = ['/api/teacher/'];

function withToken(url) {
  if (!url.startsWith('/api/') || !state.token) return url;
  const path = url.split('?')[0];
  if (NO_TOKEN_EXACT.indexOf(path) >= 0) return url;
  if (NO_TOKEN_PREFIX.some(p => path.startsWith(p))) return url;
  return url + (url.indexOf('?') >= 0 ? '&' : '?') + 'admin_token=' + encodeURIComponent(state.token);
}

function withTokenBody(body) {
  if (!state.token) return body;
  if (body instanceof FormData) { body.append('admin_token', state.token); return body; }
  if (typeof body === 'string') {
    try { const j = JSON.parse(body); j.admin_token = state.token; return JSON.stringify(j); } catch (e) { return body; }
  }
  return body;
}

async function api(url, opt) {
  const o = Object.assign({ cache: 'no-store' }, opt || {});
  o.headers = o.headers || {};
  if (o.body) o.body = withTokenBody(o.body);
  const res = await fetch(withToken(url), o);
  let data;
  try { data = await res.json(); } catch (e) { throw new Error('服务返回异常'); }
  if (!data.ok) throw new Error(data.error || '操作失败');
  return data;
}

const postJSON = (url, body) => api(url, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
});

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const courseNo = () => (state.course ? state.course.course_no : '');

/* ---------------- 登录 / 课程 ---------------- */
function showLogin() {
  clearImportResults();
  $('#loginBox').style.display = 'block';
  $('#mainBox').style.display = 'none';
  $('#switchCourseBtn').style.display = 'none';
  $('#logoutBtn').style.display = 'none';
  $('#who').textContent = '';
  $('#courseNoInput').value = '';
  $('#courseNameInput').value = '';
  $('#courseNoInput').focus();
  loadCourses();
}

async function loadCourses() {
  try {
    const d = await api('/api/admin/courses');
    const hint = $('#pwdHint');
    if (hint) {
      hint.textContent = d.password_set
        ? '管理端已启用密码保护，请输入管理员密码。'
        : '首次使用：管理员密码还没设置，本次输入的密码（至少 8 位）将作为管理员密码，请记牢。';
    }
  } catch (e) { /* 忽略 */ }
}

async function doLogin(no, name) {
  const pwd = $('#adminPwdInput').value;
  if (!pwd) { toast('请输入管理员密码', 'err'); $('#adminPwdInput').focus(); return; }
  try {
    const d = await postJSON('/api/admin/login', { course_no: no, course_name: name, password: pwd });
    state.token = d.admin_token || '';
    localStorage.setItem(STORE_KEY, JSON.stringify({ course_no: d.course.course_no, name: d.course.name }));
    $('#adminPwdInput').value = '';
    if (d.password_first_set) toast('已把本次输入的密码设为管理员密码，请记住', 'ok');
    if (d.created) toast('已创建课程「' + d.course.name + '」', 'ok');
    enterCourse(d.course);
  } catch (e) { toast(e.message, 'err'); }
}

function enterCourse(course) {
  clearImportResults();
  $('#teacherSearch').value = '';
  $('#teacherFilter').value = 'all';
  state.course = course;
  state.page = 1;
  state.curTeacherId = null;
  $('#loginBox').style.display = 'none';
  $('#mainBox').style.display = 'block';
  $('#switchCourseBtn').style.display = 'inline-block';
  $('#logoutBtn').style.display = 'inline-block';
  $('#courseTitle').textContent = course.name;
  $('#courseNoTag').textContent = course.course_no;
  $('#who').textContent = '当前课程：' + course.course_no;
  refresh().catch(e => toast(e.message, 'err'));
}

/* ---------------- 总览数据 ---------------- */
async function refresh() {
  const d = await api('/api/admin/overview?course_no=' + encodeURIComponent(courseNo()));
  state.data = d;
  if (d.settings) {
    $('#maxStudents').value = d.settings.teacher_max_students;
    $('#minClasses').value = d.settings.teacher_min_classes;
  }
  renderStats();
  renderCourseMeta();
  renderTeacherSummary();
  renderClasses();
  renderCaps();
  renderTeacherList();
  if (state.curTeacherId) renderTeacherDetail(state.curTeacherId);
}

function renderCourseMeta() {
  const s = state.data.stats;
  $('#courseMeta').textContent = '班级 ' + s.classes + ' 个 · 学生 ' + s.students +
    ' 人 · 名单教师 ' + s.teachers + ' 人';
}

function renderStats() {
  const s = state.data.stats;
  $('#s-classes').textContent = s.classes;
  $('#s-selected').textContent = s.selected;
  $('#s-left').textContent = s.left;
  $('#s-students').textContent = s.students;
  $('#s-selstud').textContent = s.selected_students;
  $('#s-below').textContent = s.below_min;
  $('#s-teachers').textContent = s.teachers;
  $('#s-unsel').textContent = s.teachers_unselected;
}

function statusTag(t) {
  if (t.n > 0) return '<span class="tag green">已选班 ' + t.n + ' 个</span>';
  if (t.note) return '<span class="tag blue">未选班·已说明</span>';
  return '<span class="tag orange">未选班</span>';
}

function teacherRows(list) {
  return list.map(t => `<tr>
    <td>${esc(t.employee_no || '-')}</td>
    <td>${esc(t.name)}</td>
    <td class="num">${t.n}</td>
    <td class="num">${t.students}</td>
    <td>${statusTag(t)}</td>
    <td>${esc(t.note || '')}</td>
  </tr>`).join('');
}

function matchesTeacher(t, query, filter) {
  if (filter === 'unselected' && t.n > 0) return false;
  if (filter === 'selected' && t.n === 0) return false;
  if (filter === 'explained' && (t.n > 0 || !t.note)) return false;
  if (filter === 'unexplained' && (t.n > 0 || t.note)) return false;
  const status = t.n > 0 ? '已选班' : ('未选班 ' + (t.note ? '已说明' : '未说明'));
  const text = [t.name, t.employee_no || '', status].join(' ').toLowerCase();
  return query.trim().toLowerCase().split(/\s+/).filter(Boolean).every(term => text.includes(term));
}

function renderTeacherSummary() {
  const filter = $('#teacherFilter').value;
  const query = $('#teacherSearch').value;
  const all = state.data.teachers;
  const list = all.filter(t => matchesTeacher(t, query, filter));
  $('#teacherBody').innerHTML = teacherRows(list);
  $('#teacherEmpty').style.display = list.length ? 'none' : 'block';
  $('#teacherEmpty').textContent = all.length ? '没有符合搜索或状态筛选条件的教师' : '本课程还没有名单教师，请先导入选班教师名单';
}

/* ---------------- 班级明细 ---------------- */
function classRows() {
  const filter = $('#filter').value;
  const q = $('#aq').value.trim().toLowerCase();
  return state.data.classes.filter(c => {
    if (filter === 'selected' && c.taken === 0) return false;
    if (filter === 'free' && c.taken > 0) return false;
    if (filter === 'below' && c.taken >= c.min_need) return false;
    if (q) {
      const s = (c.name + ' ' + c.major + ' ' + c.college).toLowerCase();
      if (s.indexOf(q) < 0) return false;
    }
    return true;
  });
}

function renderClasses() {
  const rows = classRows();
  const total = rows.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (state.page > pages) state.page = pages;
  const start = (state.page - 1) * PAGE_SIZE;
  const pageRows = rows.slice(start, start + PAGE_SIZE);
  $('#classBody').innerHTML = pageRows.map(c => `<tr class="${c.taken < c.min_need ? 'sel' : ''}">
    <td>${esc(c.campus)}</td>
    <td>${esc(c.name)}</td>
    <td><span class="tag blue">${esc(c.major)}</span></td>
    <td>${esc(c.college)}</td>
    <td>${esc(c.grade)}</td>
    <td class="num">${c.plan_size}</td>
    <td class="num">${c.taken}/${c.cap}</td>
    <td>${esc(c.teachers || '-')}</td>
    <td>${esc(c.notes || '')}</td>
  </tr>`).join('');
  $('#pager').innerHTML = total
    ? `共 ${total} 个班级　第 ${state.page}/${pages} 页
       <button class="btn sm" id="prevPage" ${state.page <= 1 ? 'disabled' : ''}>上一页</button>
       <button class="btn sm" id="nextPage" ${state.page >= pages ? 'disabled' : ''}>下一页</button>`
    : '没有符合条件的班级';
  const prev = $('#prevPage'), next = $('#nextPage');
  if (prev) prev.onclick = () => { state.page--; renderClasses(); };
  if (next) next.onclick = () => { state.page++; renderClasses(); };
}

/* ---------------- 教师选班情况 ---------------- */
function renderTeacherList() {
  const q = $('#tSearch').value.trim().toLowerCase();
  const filter = $('#tFilter').value;
  const list = state.data.teachers.filter(t => matchesTeacher(t, q, filter));
  $('#tListBody').innerHTML = list.map(t => `<tr class="pickable ${state.curTeacherId === t.id ? 'active-row' : ''}" data-id="${t.id}">
    <td>${esc(t.employee_no || '-')}</td>
    <td>${esc(t.name)}</td>
    <td class="num">${t.n}</td>
    <td class="num">${t.students}</td>
    <td>${statusTag(t)}</td>
  </tr>`).join('');
  $('#tListEmpty').style.display = list.length ? 'none' : 'block';
  $('#tListEmpty').textContent = state.data.teachers.length ? '没有符合条件的教师' : '本课程还没有名单教师';
}

function teacherClasses(tid) {
  return state.data.classes.filter(c => {
    const ids = (c.teacher_ids || '').split(',').filter(Boolean).map(Number);
    return ids.indexOf(tid) >= 0;
  });
}

function noteOf(c, tid) {
  const ids = (c.teacher_ids || '').split(',').filter(Boolean).map(Number);
  const notes = (c.notes || '').split('||');
  const i = ids.indexOf(tid);
  return i >= 0 && notes[i] ? notes[i] : '';
}

function renderTeacherDetail(tid) {
  const t = state.data.teachers.find(x => x.id === tid);
  if (!t) {
    $('#tDetailTitle').textContent = '教师选班明细';
    $('#tDetailStats').textContent = '';
    $('#tDetail').innerHTML = '';
    $('#tDetailEmpty').style.display = 'block';
    $('#tRemoveBtn').style.display = 'none';
    return;
  }
  $('#tRemoveBtn').style.display = 'inline-block';
  $('#tRemoveBtn').textContent = t.n > 0 ? '先撤销选班才能移出' : '移出本课程名单';
  $('#tDetailTitle').textContent = t.name + (t.employee_no ? '（' + t.employee_no + '）' : '');
  $('#tDetailStats').textContent = '已选 ' + t.n + ' 个班 / ' + t.students + ' 人';
  const list = teacherClasses(tid);
  if (!list.length) {
    $('#tDetail').innerHTML = '<div class="hint">该教师尚未选班（名单内，未提交任何班级）。</div>';
    $('#tDetailEmpty').style.display = 'none';
    return;
  }
  $('#tDetailEmpty').style.display = 'none';
  $('#tDetail').innerHTML = list.map(c => `<div class="tdetail-item">
    <div class="t"><strong>${esc(c.name)}</strong><span class="tag blue">${c.plan_size} 人</span></div>
    <div class="meta">${esc(c.college)} · ${esc(c.major)} · ${esc(c.grade)}级 · ${esc(c.campus)}</div>
    ${noteOf(c, tid) ? '<div class="meta">排课备注：' + esc(noteOf(c, tid)) + '</div>' : ''}
  </div>`).join('');
}

/* ---------------- 上下限 ---------------- */
function renderCaps() {
  $('#capBody').innerHTML = state.data.classes.map(c => `<tr>
    <td><input type="checkbox" class="capPick" data-id="${c.id}" ${state.capPicked.has(c.id) ? 'checked' : ''}></td>
    <td>${esc(c.name)}</td>
    <td>${esc(c.major)}</td>
    <td>${esc(c.campus)}</td>
    <td class="num">${c.plan_size}</td>
    <td class="num"><input type="number" class="capIn" data-id="${c.id}" min="1" max="20" value="${c.cap}" style="width:66px"></td>
    <td class="num"><input type="number" class="minIn" data-id="${c.id}" min="0" max="20" value="${c.min_need}" style="width:66px"></td>
  </tr>`).join('');
  updateCapSelInfo();
}

function updateCapSelInfo() {
  $('#capSelInfo').textContent = state.capPicked.size ? '已勾选 ' + state.capPicked.size + ' 个班' : '';
  $('#capAll').checked = state.data.classes.length > 0 &&
    state.capPicked.size === state.data.classes.length;
}

function collectCaps(ids) {
  const payload = [];
  ids.forEach(id => {
    const capEl = document.querySelector('.capIn[data-id="' + id + '"]');
    const minEl = document.querySelector('.minIn[data-id="' + id + '"]');
    if (!capEl || !minEl) return;
    payload.push({ id: id, cap: Number(capEl.value || 0), min_need: Number(minEl.value || 0) });
  });
  return payload;
}

async function saveCaps(items) {
  if (!items.length) { toast('没有可保存的班级', 'err'); return; }
  await postJSON('/api/admin/caps', { course_no: courseNo(), items: items });
  toast('已保存 ' + items.length + ' 个班的上下限', 'ok');
  await refresh();
}

/* ---------------- 导入 ---------------- */
function clearImportResults() {
  state.importEpoch = (state.importEpoch || 0) + 1;
  ['importResult', 'teacherImportResult'].forEach(id => { $('#' + id).textContent = ''; });
  ['fileInput', 'teacherFile'].forEach(id => { $('#' + id).value = ''; });
}

async function upload(url, fileInput, modeInput, resultBox) {
  const f = fileInput.files[0];
  if (!f) { toast('请先选择文件', 'err'); return; }
  const epoch = state.importEpoch || 0;
  const targetCourse = courseNo();
  const button = $(url === '/api/admin/import' ? '#importBtn' : '#importTeacherBtn');
  if (button.disabled) return;
  button.disabled = true;
  fileInput.disabled = true;
  resultBox.textContent = '正在导入本次文件：' + f.name + '…';
  const fd = new FormData();
  fd.append('file', f);
  fd.append('course_no', targetCourse);
  fd.append('mode', modeInput.value);
  try {
    const d = await api(url, { method: 'POST', body: fd });
    if (epoch !== (state.importEpoch || 0) || targetCourse !== courseNo()) return;
    resultBox.innerHTML = '<div class="hint" style="background:#eefaf2;border-color:#bfe8d0;color:#0d7a41">'
      + '<div>' + esc(d.message || '本次导入完成') + '</div>'
      + '<div class="muted">文件：' + esc(f.name) + ' · 本次完成时间：' + esc(new Date().toLocaleString('zh-CN')) + '</div></div>';
    toast('本次导入完成', 'ok');
    await refresh().catch(e => toast('导入已完成，刷新失败：' + e.message, 'err'));
  } catch (e) {
    if (epoch !== (state.importEpoch || 0) || targetCourse !== courseNo()) return;
    resultBox.innerHTML = '<div class="hint" style="background:#fff3f3;border-color:#f3c9c9;color:#a32020">'
      + esc(e.message) + '</div>';
    toast(e.message, 'err');
  } finally {
    button.disabled = false;
    fileInput.disabled = false;
    if (epoch === (state.importEpoch || 0)) fileInput.value = '';
  }
}

/* ---------------- 登录尝试记录 ---------------- */
async function loadLoginLog() {
  const body = $('#loginLogBody'), empty = $('#loginLogEmpty');
  if (!body) return;
  try {
    const d = await api('/api/admin/login_log?course_no=' + encodeURIComponent(courseNo()));
    const items = d.items || [];
    body.innerHTML = items.map(it => '<tr>'
      + '<td class="muted">' + esc((it.time || '').replace('T', ' ').slice(0, 19)) + '</td>'
      + '<td>' + (it.input_no ? esc(it.input_no) : '<span class="muted">（空）</span>') + '</td>'
      + '<td>' + (it.input_name ? esc(it.input_name) : '<span class="muted">（空）</span>') + '</td>'
      + '<td>' + (it.ok ? '<span class="tag green">成功</span>' : '<span class="tag red">失败</span>') + '</td>'
      + '<td>' + (it.matched ? esc(it.matched) : '<span class="muted">未匹配</span>')
      + (it.ok ? '' : '<div class="muted" style="font-size:12px">' + esc(it.detail || '') + '</div>') + '</td>'
      + '</tr>').join('');
    if (empty) empty.style.display = items.length ? 'none' : 'block';
  } catch (e) {
    toast(e.message, 'err');
  }
}

/* ---------------- 事件绑定 ---------------- */
document.querySelectorAll('.tab').forEach(tab => {
  tab.onclick = () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
    tab.classList.add('active');
    const p = document.getElementById('panel-' + tab.dataset.panel);
    if (p) p.classList.add('active');
    state.tab = tab.dataset.panel;
    if (state.tab === 'teachers') { renderTeacherList(); loadLoginLog(); }
  };
});

$('#enterBtn').onclick = () => doLogin($('#courseNoInput').value.trim(), $('#courseNameInput').value.trim());
$('#courseNameInput').addEventListener('keydown', e => { if (e.key === 'Enter') $('#adminPwdInput').focus(); });
$('#adminPwdInput').addEventListener('keydown', e => { if (e.key === 'Enter') $('#enterBtn').click(); });
$('#courseNoInput').addEventListener('keydown', e => { if (e.key === 'Enter') $('#courseNameInput').focus(); });
$('#switchCourseBtn').onclick = showLogin;
$('#logoutBtn').onclick = () => {
  localStorage.removeItem(STORE_KEY);
  state.course = null;
  state.token = '';
  showLogin();
};

$('#refreshBtn').onclick = () => refresh().catch(e => toast(e.message, 'err'));
$('#loginLogBtn').onclick = () => loadLoginLog();
$('#teacherFilter').onchange = renderTeacherSummary;
$('#teacherSearch').addEventListener('input', renderTeacherSummary);
$('#filter').onchange = () => { state.page = 1; renderClasses(); };
let aqTimer = null;
$('#aq').addEventListener('input', () => {
  clearTimeout(aqTimer);
  aqTimer = setTimeout(() => { state.page = 1; renderClasses(); }, 300);
});

$('#tSearch').addEventListener('input', renderTeacherList);
$('#tFilter').onchange = renderTeacherList;

$('#tListBody').addEventListener('click', e => {
  const tr = e.target.closest('tr[data-id]');
  if (!tr) return;
  state.curTeacherId = Number(tr.dataset.id);
  renderTeacherList();
  renderTeacherDetail(state.curTeacherId);
});

$('#capBody').addEventListener('click', e => {
  if (e.target.classList.contains('capPick')) {
    const id = Number(e.target.dataset.id);
    if (e.target.checked) state.capPicked.add(id); else state.capPicked.delete(id);
    updateCapSelInfo();
  }
});
$('#capAll').addEventListener('change', e => {
  state.capPicked.clear();
  if (e.target.checked) state.data.classes.forEach(c => state.capPicked.add(c.id));
  renderCaps();
});
$('#saveCapsBtn').onclick = async () => {
  try {
    await saveCaps(collectCaps(state.data.classes.map(c => c.id)));
  } catch (e) { toast(e.message, 'err'); }
};
$('#applyAllBtn').onclick = async () => {
  const cap = Number($('#allCap').value), min = Number($('#allMin').value);
  try {
    await postJSON('/api/admin/caps', { course_no: courseNo(), cap: cap, min_need: min, ids: [] });
    toast('已应用到全部班级', 'ok');
    await refresh();
  } catch (e) { toast(e.message, 'err'); }
};
$('#applySelBtn').onclick = async () => {
  if (!state.capPicked.size) { toast('请先勾选班级', 'err'); return; }
  try {
    await postJSON('/api/admin/caps', { course_no: courseNo(), cap: Number($('#allCap').value),
      min_need: Number($('#allMin').value), ids: Array.from(state.capPicked) });
    toast('已应用到勾选班级', 'ok');
    await refresh();
  } catch (e) { toast(e.message, 'err'); }
};
$('#saveRuleBtn').onclick = async () => {
  try {
    await postJSON('/api/admin/settings', { course_no: courseNo(), key: 'teacher_max_students', value: $('#maxStudents').value });
    await postJSON('/api/admin/settings', { course_no: courseNo(), key: 'teacher_min_classes', value: $('#minClasses').value });
    toast('教师规则已保存', 'ok');
  } catch (e) { toast(e.message, 'err'); }
};

async function addTeacher() {
  const no = $('#newTeacherNo').value.trim();
  const name = $('#newTeacherName').value.trim();
  if (!no) {
    toast('请填写工号（教师登录需要工号+姓名同时匹配）', 'err');
    $('#newTeacherNo').focus();
    return;
  }
  if (!name) {
    toast('请填写教师姓名', 'err');
    $('#newTeacherName').focus();
    return;
  }
  try {
    const d = await postJSON('/api/admin/add_teacher', { course_no: courseNo(), employee_no: no, name: name });
    $('#addTeacherResult').innerHTML = '<div class="hint" style="background:#eefaf2;border-color:#bfe8d0;color:#0d7a41">'
      + esc(d.message) + '</div>';
    $('#newTeacherNo').value = '';
    $('#newTeacherName').value = '';
    toast('已添加', 'ok');
    await refresh();
  } catch (e) {
    $('#addTeacherResult').innerHTML = '<div class="hint" style="background:#fff3f3;border-color:#f3c9c9;color:#a32020">'
      + esc(e.message) + '</div>';
    toast(e.message, 'err');
  }
}

$('#addTeacherBtn').onclick = addTeacher;
$('#newTeacherName').addEventListener('keydown', e => { if (e.key === 'Enter') addTeacher(); });
$('#newTeacherNo').addEventListener('keydown', e => { if (e.key === 'Enter') $('#newTeacherName').focus(); });

$('#tRemoveBtn').onclick = async () => {
  const tid = state.curTeacherId;
  const t = state.data.teachers.find(x => x.id === tid);
  if (!t) return;
  if (t.n > 0) {
    toast('该教师已选 ' + t.n + ' 个班，请先撤销其选班后再移出名单', 'err');
    return;
  }
  if (!confirm('确定把「' + t.name + '」移出本课程名单吗？')) return;
  try {
    const d = await postJSON('/api/admin/remove_teacher', { course_no: courseNo(), teacher_id: tid });
    toast(d.message, 'ok');
    state.curTeacherId = null;
    await refresh();
    $('#tDetailTitle').textContent = '教师选班明细';
    $('#tDetailStats').textContent = '';
    $('#tDetail').innerHTML = '';
    $('#tDetailEmpty').style.display = 'block';
    $('#tRemoveBtn').style.display = 'none';
  } catch (e) { toast(e.message, 'err'); }
};

$('#fileInput').addEventListener('change', () => { $('#importResult').textContent = ''; });
$('#teacherFile').addEventListener('change', () => { $('#teacherImportResult').textContent = ''; });
$('#importBtn').onclick = () => upload('/api/admin/import', $('#fileInput'), $('#importMode'), $('#importResult'));$('#importTeacherBtn').onclick = () => upload('/api/admin/import_teachers', $('#teacherFile'), $('#teacherMode'), $('#teacherImportResult'));
$('#templateBtn').onclick = () => { window.location = '/api/admin/template'; };
$('#teacherTemplateBtn').onclick = () => { window.location = '/api/admin/teacher_template'; };
$('#teacherExportBtn').onclick = () => { window.location = withToken('/api/admin/teacher_export?course_no=' + encodeURIComponent(courseNo())); };
$('#exportBtn').onclick = () => { window.location = withToken('/api/export?course_no=' + encodeURIComponent(courseNo())); };

$('#resetBtn').onclick = async () => {
  if (!confirm('确定清空本课程的全部选班记录吗？班级与教师名单会保留。')) return;
  try {
    await postJSON('/api/admin/reset', { course_no: courseNo() });
    clearImportResults();
    toast('已清空本课程选班记录', 'ok');
    await refresh();
  } catch (e) { toast(e.message, 'err'); }
};
$('#resetClassesBtn').onclick = async () => {
  if (!confirm('确定清空本课程的全部班级吗？相关选班记录也会删除，教师名单和情况说明保留。')) return;
  try {
    await postJSON('/api/admin/reset_classes', { course_no: courseNo() });
    clearImportResults();
    toast('已清空本课程班级，教师名单已保留', 'ok');
    await refresh();
  } catch (e) { toast(e.message, 'err'); }
};
$('#resetTeachersBtn').onclick = async () => {
  if (!confirm('确定清空本课程的教师名单吗？相关选班记录和情况说明也会删除，班级保留。其他课程的教师名单不受影响。')) return;
  try {
    await postJSON('/api/admin/reset_teachers', { course_no: courseNo() });
    clearImportResults();
    toast('已清空本课程教师名单，班级已保留', 'ok');
    await refresh();
  } catch (e) { toast(e.message, 'err'); }
};

$('#changePwdBtn').onclick = async () => {
  const oldP = $('#oldPwd').value, newP = $('#newPwd').value;
  const box = $('#pwdResult');
  if (!oldP || !newP) { toast('请填写原密码和新密码', 'err'); return; }
  try {
    await postJSON('/api/admin/password', { course_no: courseNo(), old_password: oldP, new_password: newP });
    box.innerHTML = '<div class="hint" style="background:#eefaf2;border-color:#bfe8d0;color:#0d7a41">管理员密码已更新</div>';
    $('#oldPwd').value = '';
    $('#newPwd').value = '';
    toast('管理员密码已更新', 'ok');
  } catch (e) {
    box.innerHTML = '<div class="hint" style="background:#fff3f3;border-color:#f3c9c9;color:#a32020">' + esc(e.message) + '</div>';
    toast(e.message, 'err');
  }
};

/* ---------------- 启动 ---------------- */
(function init() {
  showLogin();
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(STORE_KEY)); } catch (e) { saved = null; }
  if (saved && saved.course_no && saved.name) {
    $('#courseNoInput').value = saved.course_no;
    $('#courseNameInput').value = saved.name;
    $('#adminPwdInput').focus();
    toast('请补输管理员密码后进入', 'ok');
  }
})();
