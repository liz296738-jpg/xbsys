const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, { value: '', textContent: '', innerHTML: '', files: [], disabled: false,
    style: {}, dataset: {}, handlers: {}, classList: { add() {}, remove() {}, toggle() {} },
    addEventListener(name, fn) { this.handlers[name] = fn; }, focus() {}, appendChild() {}, remove() {} });
  return elements.get(id);
}
const context = vm.createContext({ console, Date, FormData, window: {},
  document: { querySelector: element, querySelectorAll: () => [], createElement: () => element('toast') },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, confirm: () => true });
vm.runInContext(fs.readFileSync(__dirname + '/web/admin.js', 'utf8'), context);
vm.runInContext(`this.test = { matchesTeacher, renderTeacherSummary, clearImportResults, upload,
  setCourse(course) { state.course = course; }, setTeachers(teachers) { state.data.teachers = teachers; },
  setApi(fn) { api = fn; }, setRefresh(fn) { refresh = fn; } };`, context);
const t = context.test;
const roster = [{name:'张老师',employee_no:'001',n:0,note:'本学期不承担'},
  {name:'李老师',employee_no:'002',n:2,note:''}, {name:'王老师',employee_no:'003',n:0,note:''}];
t.setTeachers(roster);
assert(t.matchesTeacher(roster[0], '张 未选班', 'explained'));
assert(!t.matchesTeacher(roster[0], '张', 'selected'));
assert(t.matchesTeacher(roster[1], '002 已选班', 'selected'));
assert(t.matchesTeacher(roster[2], '未说明', 'unexplained'));
element('#teacherFilter').value='explained';element('#teacherSearch').value='张';t.renderTeacherSummary();
assert(element('#teacherBody').innerHTML.includes('张老师'));
assert(!element('#teacherBody').innerHTML.includes('李老师'));
element('#teacherSearch').value='不存在';t.renderTeacherSummary();assert.equal(element('#teacherEmpty').style.display,'block');
(async () => {
  t.setCourse({course_no:'A'});t.setRefresh(async()=>{});
  const input=element('#fileInput'), result=element('#importResult');
  result.innerHTML='旧结果';input.files=[new Blob(['data'])];input.files[0].name='本次名单.csv';
  let finish;t.setApi(()=>new Promise(resolve=>{finish=resolve;}));
  const request=t.upload('/api/admin/import',input,{value:'skip'},result);
  assert.equal(element('#importBtn').disabled,true);
  t.clearImportResults();result.innerHTML='';t.setCourse({course_no:'B'});
  finish({message:'来自旧课程的结果'});await request;assert.equal(result.innerHTML,'');
  input.files=[new Blob(['data'])];input.files[0].name='新文件.csv';
  t.setApi(async()=>({message:'本次导入：新增 0 个班，跳过 2 行'}));
  await t.upload('/api/admin/import',input,{value:'skip'},result);
  assert(result.innerHTML.includes('新增 0 个班'));assert(result.innerHTML.includes('新文件.csv'));
  assert(!result.innerHTML.includes('旧课程'));assert.equal(element('#importBtn').disabled,false);
  console.log('PASS: teacher search/status combinations, empty results, current-file import messages and stale-response rejection');
})().catch(e=>{console.error(e);process.exitCode=1;});
