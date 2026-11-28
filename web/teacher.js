/* 教师端逻辑：工号+姓名登录 → 多课程选择 → 课程内选班 */
const $ = (s) => document.querySelector(s);
const STORE_KEY = 'jxb_teacher';
const state = {
  teacher: { no: '', name: '' },
  token: '',
  courses: [],
  course: null,
  classes: [],
  mine: [],
  picked: new Set(),
  rules: { max_students: 100, min_classes: 2 }
};

function toast(msg, kind) {
  const el = document.createElement('div');
  el.className = 'toast ' + (kind || '');
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

async function api(url, opt) {
  const o = Object.assign({ cache: 'no-store' }, opt || {});
  const res = await fetch(url, o);
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

function ident() {
  return { course_no: state.course ? state.course.course_no : '',
           no: state.teacher.no, name: state.teacher.name, token: state.token };
}

/* ---------------- 页面切换 ---------------- */
function showLogin() {
  $('#loginBox').style.display = 'block';
  $('#courseBox').style.display = 'none';
  $('#mainBox').style.display = 'none';
  $('#switchBtn').style.display = 'none';
  $('#switchCourseBtn').style.display = 'none';
  $('#who').textContent = '';
  $('#noInput').value = state.teacher.no || '';
  $('#nameInput').value = '';
  $('#nameInput').focus();
}

function showCoursePicker() {
  $('#loginBox').style.display = 'none';
  $('#courseBox').style.display = 'block';
  $('#mainBox').style.display = 'none';
  $('#switchCourseBtn').style.display = 'none';
  $('#who').textContent = '';
  const last = (loadSaved() || {}).last_course_no;
  $('#courseTip').textContent = state.courses.length > 1
    ? '您在多门课程中承担选班任务，请先选择要进入的课程'
    : '您只有一门课程，可直接进入';
  $('#courseList').innerHTML = state.courses.map(c => `
    <button class="btn ${c.course_no === last ? 'primary' : ''}" data-no="${esc(c.course_no)}"
      style="height:auto;padding:10px 16px;text-align:left">
      <b>${esc(c.name)}</b><br>
      <span class="muted">${esc(c.course_no)}　已选 ${c.picked_classes} 个班 / ${c.picked_students} 人</span>
    </button>`).join('');
  $('#courseList').querySelectorAll('button').forEach(b => {
    b.onclick = () => {
      const c = state.courses.find(x => x.course_no === b.dataset.no);
      if (c) enterCourse(c);
    };
  });
}

function enterCourse(course) {
  state.course = course;
  $('#loginBox').style.display = 'none';
  $('#courseBox').style.display = 'none';
  $('#mainBox').style.display = 'block';
  $('#switchBtn').style.display = 'inline-block';
  $('#switchCourseBtn').style.display = state.courses.length > 1 ? 'inline-block' : 'none';
  $('#who').textContent = '当前课程：' + course.name + '（' + course.course_no + '） · ' +
    state.teacher.name + (state.teacher.no ? '（' + state.teacher.no + '）' : '');
  $('#ruleHint').textContent = ruleText();
  saveSaved(course.course_no);
  refreshAll().catch(e => toast(e.message, 'err'));
}

function ruleText() {
  const max = state.rules.max_students == null ? 100 : state.rules.max_students;
  const min = state.rules.min_classes == null ? 2 : state.rules.min_classes;
  return '本课程规则：每位教师最多 ' + (max > 0 ? max + ' 人' : '不限') + '；至少 ' +
    (min > 0 ? min + ' 个班' : '0 个班（不选班也可提交，请在备注框写明原因）') +
    '；班级不可拆分；已被其他教师选走的班级不会出现在列表中。';
}

/* ---------------- 登录 ---------------- */
function loadSaved() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)); } catch (e) { return null; }
}

function saveSaved(lastCourseNo) {
  localStorage.setItem(STORE_KEY, JSON.stringify({
    no: state.teacher.no, name: state.teacher.name, token: state.token,
    last_course_no: lastCourseNo !== undefined ? lastCourseNo : (state.course ? state.course.course_no : '')
  }));
}

async function doLogin(no, name, auto) {
  if (!no || !name) {
    if (auto) { showLogin(); return; }
    toast(!no ? '请填写工号（工号和姓名需同时匹配）' : '请填写姓名（工号和姓名需同时匹配）', 'err');
    (!no ? $('#noInput') : $('#nameInput')).focus();
    return;
  }
  try {
    const d = await postJSON('/api/teacher/login', { employee_no: no, name: name });
    state.teacher = { no: d.teacher.employee_no, name: d.teacher.name };
    state.token = d.token || '';
    state.courses = d.courses;
    if (d.settings) {
      state.rules = {
        max_students: d.settings.teacher_max_students,
        min_classes: d.settings.teacher_min_classes
      };
    }
    if (d.warning) toast(d.warning, 'err');
    saveSaved();
    if (state.courses.length === 1) {
      enterCourse(state.courses[0]);
    } else {
      showCoursePicker();
    }
  } catch (e) {
    localStorage.removeItem(STORE_KEY);
    if (auto) showLogin(); else toast(e.message, 'err');
  }
}

/* ---------------- 数据 ---------------- */
async function refreshClasses() {
  const q = $('#q').value.trim();
  const url = '/api/teacher/classes?course_no=' + encodeURIComponent(state.course.course_no) +
    '&no=' + encodeURIComponent(state.teacher.no) +
    '&name=' + encodeURIComponent(state.teacher.name) +
    '&token=' + encodeURIComponent(state.token) +
    '&q=' + encodeURIComponent(q) + '&sort=' + $('#sort').value + '&order=' + $('#order').value;
  const d = await api(url);
  state.classes = d.classes;
  state.picked.clear();
  renderClasses();
}

async function refreshMine() {
  const d = await api('/api/teacher/mine?course_no=' + encodeURIComponent(state.course.course_no) +
    '&no=' + encodeURIComponent(state.teacher.no) +
    '&name=' + encodeURIComponent(state.teacher.name) +
    '&token=' + encodeURIComponent(state.token));
  state.mine = d.classes;
  $('#myClasses').textContent = d.stats.classes;
  $('#myPeople').textContent = d.stats.students;
  $('#mineStats').textContent = '共 ' + d.stats.classes + ' 个班 / ' + d.stats.students + ' 人';
  if (d.teacher_note) {
    $('#noteInput').value = d.teacher_note;
    $('#noteHint').textContent = '已向管理员提交情况说明：' + d.teacher_note;
    $('#noteHint').style.display = 'block';
  }
  renderMine();
}

async function refreshAll() {
  await Promise.all([refreshClasses(), refreshMine()]);
}

/* ---------------- 渲染 ---------------- */
function renderClasses() {
  const body = $('#classBody');
  const empty = $('#classEmpty');
  if (!state.classes.length) {
    body.innerHTML = '';
    empty.style.display = 'block';
  } else {
    empty.style.display = 'none';
    body.innerHTML = state.classes.map(c => `
      <tr data-id="${c.id}" class="${state.picked.has(c.id) ? 'sel' : ''}">
        <td><input type="checkbox" class="pick" data-id="${c.id}" ${state.picked.has(c.id) ? 'checked' : ''}></td>
        <td>${esc(c.name)}</td>
        <td><span class="tag blue">${esc(c.major)}</span></td>
        <td>${esc(c.college)}</td>
        <td>${esc(c.grade)}</td>
        <td>${esc(c.campus)}</td>
        <td class="num">${c.plan_size}</td>
        <td class="num">${c.taken}/${c.cap}</td>
      </tr>`).join('');
  }
  updatePickBar();
  syncClassScrollbar();
}

function renderMine() {
  const box = $('#mineList');
  const empty = $('#mineEmpty');
  if (!state.mine.length) {
    box.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  box.innerHTML = state.mine.map(c => `
    <div class="mine-item" data-id="${c.id}">
      <div class="t">
        <strong>${esc(c.name)}</strong>
        <button class="btn sm danger unselect" data-id="${c.id}">撤销</button>
      </div>
      <div class="meta">${esc(c.college)} · ${esc(c.major)} · ${esc(c.grade)}级 · ${esc(c.campus)} · ${c.plan_size} 人</div>
      <textarea class="note" data-id="${c.id}" placeholder="排课备注">${esc(c.note || '')}</textarea>
    </div>`).join('');
}

function updatePickBar() {
  let people = 0;
  state.classes.forEach(c => { if (state.picked.has(c.id)) people += c.plan_size; });
  $('#pickCount').textContent = state.picked.size;
  $('#pickPeople').textContent = people;
  // 没勾班级但写了情况说明时也允许提交
  $('#submitBtn').disabled = state.picked.size === 0 && !$('#noteInput').value.trim();
  const all = $('#checkAll');
  all.checked = state.classes.length > 0 && state.picked.size === state.classes.length;
}

/* ---------------- 交互 ---------------- */
$('#classBody').addEventListener('click', (e) => {
  const cb = e.target.closest('.pick');
  if (!cb) return;
  const id = Number(cb.dataset.id);
  if (cb.checked) state.picked.add(id); else state.picked.delete(id);
  cb.closest('tr').classList.toggle('sel', cb.checked);
  updatePickBar();
});

$('#checkAll').addEventListener('change', (e) => {
  state.picked.clear();
  if (e.target.checked) state.classes.forEach(c => state.picked.add(c.id));
  renderClasses();
});

$('#mineList').addEventListener('click', async (e) => {
  const btn = e.target.closest('.unselect');
  if (!btn) return;
  if (!confirm('确定撤销该班级吗？撤销后其他教师可选。')) return;
  try {
    await postJSON('/api/teacher/unselect', Object.assign(ident(), { ids: [Number(btn.dataset.id)] }));
    toast('已撤销', 'ok');
    await refreshAll();
  } catch (err) { toast(err.message, 'err'); }
});

$('#mineList').addEventListener('blur', async (e) => {
  const ta = e.target.closest('.note');
  if (!ta) return;
  try {
    await postJSON('/api/teacher/note', Object.assign(ident(),
      { class_id: Number(ta.dataset.id), note: ta.value }));
    toast('备注已保存', 'ok');
  } catch (err) { toast(err.message, 'err'); }
}, true);

$('#submitBtn').addEventListener('click', async () => {
  const ids = Array.from(state.picked);
  const note = $('#noteInput').value.trim();
  $('#submitBtn').disabled = true;
  try {
    const d = await postJSON('/api/teacher/select', Object.assign(ident(), { ids, note }));
    if (d.note_only) {
      toast('已提交情况说明，管理员可在后台「教师选班情况」看到', 'ok');
    } else {
      toast('已选 ' + d.added + ' 个班，当前共 ' + d.stats.classes + ' 个班 / ' + d.stats.students + ' 人', 'ok');
    }
    $('#noteInput').value = '';
    $('#noteHint').style.display = 'none';
    await refreshAll();
  } catch (err) {
    toast(err.message, 'err');
    await refreshClasses();
  } finally {
    updatePickBar();
  }
});

$('#noteInput').addEventListener('input', updatePickBar);

let timer = null;
$('#q').addEventListener('input', () => {
  clearTimeout(timer);
  timer = setTimeout(refreshClasses, 300);
});
$('#sort').addEventListener('change', refreshClasses);
$('#order').addEventListener('change', refreshClasses);
$('#refreshBtn').addEventListener('click', () => { refreshAll().catch(e => toast(e.message, 'err')); });

$('#enterBtn').addEventListener('click', () => doLogin($('#noInput').value.trim(), $('#nameInput').value.trim()));
$('#nameInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') doLogin($('#noInput').value.trim(), $('#nameInput').value.trim());
});
$('#noInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') $('#nameInput').focus();
});
$('#switchBtn').addEventListener('click', () => {
  localStorage.removeItem(STORE_KEY);
  state.teacher = { no: '', name: '' };
  state.token = '';
  state.courses = [];
  state.course = null;
  showLogin();
});
$('#switchCourseBtn').addEventListener('click', () => {
  state.picked.clear();
  showCoursePicker();
});

/* ---------------- 启动 ---------------- */
(function init() {
  const saved = loadSaved();
  if (saved && saved.name) {
    state.teacher = { no: saved.no || '', name: saved.name };
    doLogin(state.teacher.no, state.teacher.name, true);
  } else {
    showLogin();
  }
})();


// Keep a draggable horizontal control available on touch devices with overlay scrollbars.
function syncClassScrollbar() {
  const area = $('#classScroll');
  const slider = $('#classScrollRange');
  const max = Math.max(0, area.scrollWidth - area.clientWidth);
  $('#classScrollControls').hidden = max <= 1;
  slider.max = String(max);
  slider.value = String(Math.min(max, area.scrollLeft));
}
$('#classScrollRange').addEventListener('input', e => {
  $('#classScroll').scrollLeft = Number(e.target.value);
});
$('#classScroll').addEventListener('scroll', syncClassScrollbar, { passive: true });
window.addEventListener('resize', syncClassScrollbar);
if (typeof ResizeObserver !== 'undefined') {
  const classScrollObserver = new ResizeObserver(syncClassScrollbar);
  classScrollObserver.observe($('#classScroll'));
  classScrollObserver.observe($('#classScroll table'));
}
syncClassScrollbar();
