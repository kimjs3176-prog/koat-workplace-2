// assets/reg_agent.js 의 순수 로직 — 브라우저 없이 node:test 로 확인 (node --test tests/js)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const cfg = JSON.parse(fs.readFileSync(path.join(root, 'org_config.json'), 'utf8'));

function load() {
  const store = {};
  const ctx = {
    console, Date, Math, JSON, setTimeout, clearTimeout,
    localStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
    sessionStorage: { getItem: () => null, setItem() {} },
    document: { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], title: '' },
    window: { scrollY: 0, scrollTo() {} },
    escHtml: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'),
    argAttr: s => String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;'),
    getAiSettings: () => ({}), _toast() {}, _copyText() {}, openAiModal() {},
  };
  vm.createContext(ctx);
  const src = fs.readFileSync(path.join(root, 'assets/reg_agent.js'), 'utf8');
  // const/let 최상위 선언을 컨텍스트에서 꺼내 쓰도록 노출
  vm.runInContext(src + '\n;globalThis.__RA=()=>RA; globalThis.__setOrg=o=>{RA_ORG=o;};', ctx);
  // org_config 자리표시자 치환(서버 ofmt 대용)
  const fmt = o => typeof o === 'string' ? o.replace(/\{head\}/g, cfg.head).replace(/\{deputy\}/g, cfg.deputy).replace(/\{notice_days\}/g, cfg.notice_days).replace(/\{staff_days\}/g, cfg.staff_days)
    : Array.isArray(o) ? o.map(fmt) : o && typeof o === 'object' ? Object.fromEntries(Object.entries(o).map(([k, v]) => [k, fmt(v)])) : o;
  ctx.__setOrg(fmt(cfg));
  return ctx;
}

test('raParse: 조·장·부칙 구분', () => {
  const c = load();
  const p = c.raParse('제1장 총칙\n제1조(목적) 가.\n① 나.\n제1조의2(특례) 다.\n제2조 삭제\n부칙\n이 규칙은 발령한 날부터 시행한다.');
  assert.equal(JSON.stringify(p.articles.map(a => a.no)), JSON.stringify(['1', '1의2', '2']));   // vm 컨텍스트 배열은 realm이 달라 deepEqual 불가
  assert.equal(p.articles[0].chapter, '제1장 총칙');
  assert.ok(p.articles[2].deleted);
  assert.match(p.addenda, /^부칙/);
});

test('raCmpCell: 신설·삭제·변경 표시와 (현행과 같음) 축약', () => {
  const c = load();
  const ins = c.raCmpCell(null, { no: '3', title: '신설', body: '내용' }, true);
  assert.equal(ins[2], '<신 설>');
  const del = c.raCmpCell({ no: '3', title: 't', body: 'b' }, { type: 'delete', no: '3' }, true);
  assert.match(del[3], /삭 제/);
  const mod = c.raCmpCell({ no: '2', title: '정의', body: '① 가.\n② 나는 3만원.' }, { no: '2', title: '정의', body: '① 가.\n② 나는 5만원.' }, true);
  assert.match(mod[3], /현행과 같음/);
  assert.match(mod[1], /<u class="ra-i">5만원/);
});

test('raCmpCell: HTML 특수문자 이스케이프', () => {
  const c = load();
  const r = c.raCmpCell({ no: '1', title: 'a', body: '<script>' }, { no: '1', title: 'a', body: '<img onerror=x>' }, false);
  assert.ok(!r[0].includes('<script>') && !r[1].includes('<img'));
});

test('raProcEval: 답하지 않은 조건은 미정, 해당 없음은 사유 포함', () => {
  const c = load();
  let items = c.raProcEval();
  assert.ok(items.some(s => s.st === 'tbd'));
  const RA = c.__RA();
  RA.proc.ans = { level: 'rule', minor: 'n', public: 'n', multi: 'n', impact: 'n', burden: 'n' };
  items = c.raProcEval();
  assert.ok(!items.some(s => s.st === 'tbd'));
  const notice = items.find(s => s.id === 'notice');
  assert.equal(notice.st, 'out');
  assert.ok(notice.why.some(w => w.includes('국민 권리')));
  // 같은 id 의 대안 경로는 하나만 남는다
  assert.equal(items.filter(s => s.id === 'review').length, 1);
});

test('raProcState: 선행 단계가 끝나야 다음 단계가 열린다(선택 단계는 막지 않음)', () => {
  const c = load();
  const RA = c.__RA();
  RA.proc.ans = { level: 'rule', minor: 'n', public: 'y', multi: 'n', impact: 'n', burden: 'n' };
  RA.proc.chk = {};
  let st = c.raProcState();
  const get = id => st.live.find(s => s.id === id);
  assert.equal(st.next.id, 'draft');
  assert.ok(get('check').locked);
  RA.proc.chk = { draft: '2026-10-01' };
  st = c.raProcState();
  assert.ok(!get('check').locked);
  assert.ok(get('notice').locked);                 // 앞 국면 미완료
  RA.proc.chk = { draft: 1, check: 1 };            // pre(선택)는 건너뛰어도 된다
  st = c.raProcState();
  assert.ok(!get('notice').locked);
});

test('raSchedule: 병행 국면은 가장 긴 기간, 나머지는 합산', () => {
  const c = load();
  const RA = c.__RA();
  RA.proc.ans = { level: 'rule', minor: 'n', public: 'y', multi: 'n', impact: 'n', burden: 'n' };
  RA.proc.plan = { start: '2026-10-03', target: '2026-11-15' };
  const st = c.raProcState(), sc = c.raSchedule(st.flow);
  assert.equal(sc.total, cfg.notice_days + 7);
  assert.equal(sc.end, c.raAddD('2026-10-03', sc.total));
  assert.equal(sc.slack, c.raDiffD(sc.end, '2026-11-15'));
});

test('날짜 도우미: 월말·윤년·잘못된 값', () => {
  const c = load();
  assert.equal(c.raAddD('2028-02-28', 1), '2028-02-29');
  assert.equal(c.raAddD('2026-12-31', 1), '2027-01-01');
  assert.equal(c.raDiffD('2026-03-01', '2026-03-31'), 30);
  const RA = c.__RA();
  RA.proc.plan = { start: 'garbage' };
  assert.match(c.raSchedule([]).start, /^\d{4}-\d{2}-\d{2}$/);
});

test('raNormNo: 항·호 번호는 버리고 조 번호만', () => {
  const c = load();
  assert.equal(c.raNormNo('제 7 조 제2항'), '7');
  assert.equal(c.raNormNo('제31조제2항'), '31');
  assert.equal(c.raNormNo('제7조의2'), '7의2');
  assert.equal(c.raNormNo('7의2'), '7의2');
  assert.equal(c.raNormNo('abc'), '');
});

test('raCmpCell: 항 신설로 번호가 밀려도 같은 내용끼리 짝짓는다', () => {
  const c = load();
  const r = c.raCmpCell({ no: '2', title: 't', body: '① 가는 x이다.\n② 나는 y이다.' }, { no: '2', title: 't', body: '① 가는 x이다.\n② 새로 넣은 항이다.\n③ 나는 y이다.' }, false);
  const rows = r[3].split('\n');
  assert.equal(rows.length, 3);
  assert.match(r[1], /<u class="ra-i">② 새로 넣은 항이다\.<\/u>/);   // 신설 항은 통째로 추가 표시
  assert.ok(!/<u class="ra-i">③ 나는 y이다/.test(r[1]));           // 기존 항은 번호만 바뀐 것으로 비교
});

test('raParse: “부칙으로”·“제3조(정의)에 따른”은 본문으로 본다', () => {
  const c = load();
  const p = c.raParse('제1조(목적) 가.\n부칙으로 정하는 사항은 따로 정한다.\n제2조(정의) 나.\n제3조(정의)에 따른 용어는 같다.\n제4조(기타) 다.');
  assert.equal(JSON.stringify(p.articles.map(a => a.no)), JSON.stringify(['1', '2', '4']));
  assert.equal(p.addenda, '');
});

test('raProcEval: unless 조건이 미답변이면 확정하지 않는다(요약 목록에는 포함)', () => {
  const c = load();
  const RA = c.__RA();
  RA.proc.ans = {};
  const confirm = c.raProcEval().find(s => s.id === 'confirm');
  assert.equal(confirm.st, 'tbd');
  RA.proc.ans = { level: 'rule' };
  const staff = c.raProcEval().find(s => s.id === 'staff');
  assert.equal(staff.st, 'tbd');                                    // 경미한 변경 여부 미답변
  assert.ok(c.raProcSteps().some(s => s.id === 'staff'));           // 에이전트 요약에는 포함
});

test('raProcState: 앞 국면의 미정 단계도 관문을 막는다', () => {
  const c = load();
  const RA = c.__RA();
  RA.proc.ans = { level: 'rule', minor: 'n', multi: 'n', impact: 'n', burden: 'n' };   // public 미답변 → 사전예고 미정
  RA.proc.chk = { draft: 1, check: 1, staff: 1 };
  const st = c.raProcState();
  assert.ok(st.live.find(s => s.id === 'review').locked);
});
