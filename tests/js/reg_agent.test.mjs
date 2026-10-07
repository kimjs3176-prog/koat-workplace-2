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

// ── 공문서 표기(행정업무운영편람): 이유서·사전예고문·공고 ──
function docCtx(c) {
  const RA = c.__RA();
  RA.amend = Object.assign(RA.amend, { title: '여비규정', purpose: '일비를 현실화하려는 것임.', main: ['일비를 3만원으로 상향함(안 제15조)'],
    changes: [{ type: 'modify', no: '15', title: '일비', body: '일비는 3만원으로 한다.' }], addenda: '이 규정은 발령한 날부터 시행한다.' });
  return c.raDocsBuild('amend');
}

test('공문서 문서: 붙임은 쌍점 없이 두 칸, 기간은 물결표 붙여 씀', () => {
  const c = load(); const B = docCtx(c);
  for (const k of ['reason', 'notice', 'staff']) {
    assert.ok(!/붙임\s*:/.test(B[k]), k);
    assert.match(B[k], /붙임 {2}신구조문대비표 1부\. {2}끝\.$/);
  }
  assert.match(B.notice, /\d+\. \d+\. \d+\.∼\d+\. \d+\. \d+\./);
  assert.ok(!/[—–―]/.test(B.reason + B.notice + B.staff));
});

test('raAmendSentences: 바뀐 곳만 짚는 일부개정 문형', () => {
  const c = load();
  const S = (o, n) => { const r = c.raAmendSentences(o, n); return r.head + (r.lines.length ? ' | ' + r.lines.join(' / ') : ''); };
  const base = { no: '5', title: '여비', body: '① 숙박비는 3만원을 한도로 한다.\n② 식비는 실비로 한다.' };
  assert.equal(S(base, { ...base, body: '① 숙박비는 5만원을 한도로 한다.\n② 식비는 실비로 한다.' }), '제5조제1항 중 “3만원”을 “5만원”으로 한다.');
  assert.equal(S(base, { ...base, title: '여비의 지급', body: base.body + '\n③ 교통비는 실비로 한다.' }),
    '제5조의 제목 “여비”를 “여비의 지급”으로 하고, 같은 조에 제3항을 다음과 같이 신설한다. | ③ 교통비는 실비로 한다.');
  // 받침에 따라 바뀌는 조사(으로/로)는 따옴표 밖으로
  assert.equal(S({ no: '7', title: '신청', body: '신청서를 서면으로 제출한다.' }, { no: '7', title: '신청', body: '신청서를 전자결재로 제출한다.' }),
    '제7조 중 “서면”을 “전자결재”로 한다.');
  // 같은 바꿈은 “각각”으로 묶는다
  assert.equal(S({ no: '9', title: 'a', body: '① 원장은 정한다.\n② 원장은 승인한다.\n③ x' }, { no: '9', title: 'a', body: '① 기관장은 정한다.\n② 기관장은 승인한다.\n③ x' }),
    '제9조제1항 및 제2항 중 “원장”을 각각 “기관장”으로 한다.');
  // 호가 있으면 “각 호 외의 부분”, 끝에 덧붙인 호는 신설
  assert.equal(S({ no: '8', title: '대상', body: '다음 사람에게 지급한다.\n1. 임원\n2. 직원' }, { no: '8', title: '대상', body: '다음 사람에게 준다.\n1. 임원\n2. 직원\n3. 계약직' }),
    '제8조 각 호 외의 부분 중 “지급한다”를 “준다”로 하고, 같은 조에 제3호를 다음과 같이 신설한다. | 3. 계약직');
  assert.equal(S({ no: '9', title: 'a', body: '① aa\n② bb\n③ cc' }, { no: '9', title: 'a', body: '① aa\n② bb' }), '제9조제3항을 삭제한다.');
  // 중간에 항을 끼우면(번호가 밀림) 조 전체를 다시 쓴다
  assert.match(S({ no: '4', title: 'a', body: '① 가.\n② 나.' }, { no: '4', title: 'a', body: '① 가.\n② 새 항.\n③ 나.' }), /^제4조를 다음과 같이 한다\./);
  assert.equal(S({ no: '3', title: 'a', body: 'x' }, { type: 'delete', no: '3' }), '제3조를 삭제한다.');
  assert.match(S(null, { type: 'insert', no: '3의2', title: '특례', body: '내용' }), /^제3조의2를 다음과 같이 신설한다\. \| 제3조의2\(특례\) 내용$/);
});

test('raRo·raEul: 받침·숫자 읽기에 따른 조사', () => {
  const c = load();
  assert.equal(c.raRo('16일'), '로');      // ㄹ 받침
  assert.equal(c.raRo('3만원'), '으로');
  assert.equal(c.raRo('5'), '로');
  assert.equal(c.raRo('3'), '으로');
  assert.equal(c.raEul('규정'), '을');
  assert.equal(c.raEul('규칙서'), '를');
});

test('raAbBuild: 부칙 도우미 — 시행일만이면 한 문장, 여럿이면 조로 나눔', () => {
  const c = load();
  const RA = c.__RA();
  RA.amend.title = '여비규정';
  RA.amend.changes = [{ type: 'modify', no: '5', title: '여비', body: 'x' }];
  RA.amend.ab = { eff: 'after', months: '3', apply: false, trans: false, other: false };
  assert.equal(c.raAbBuild('amend'), '이 규정은 발령 후 3개월이 경과한 날부터 시행한다.');
  Object.assign(RA.amend.ab, { eff: 'date', date: '2027년 1월 1일', apply: true, applyWhat: '출장을 명하는 경우', trans: true });
  const t = c.raAbBuild('amend').split('\n');
  assert.equal(t[0], '제1조(시행일) 이 규정은 2027년 1월 1일부터 시행한다.');
  assert.equal(t[1], '제2조(적용례) 제5조의 개정규정은 이 규정 시행 이후 최초로 출장을 명하는 경우부터 적용한다.');
  assert.match(t[2], /^제3조\(경과조치\) /);
  // 다른 내규의 개정: 영향 분석의 조 인용 정정에서 만든다
  RA.amend.ab = { eff: 'issue', other: true };
  RA.amend.impact = { outer: [{ reg: '국외여비지침', hits: [{ no: '3', cites: '5', text: '「여비규정」 제5조', suggest: '「여비규정」 제5조 → 제6조' }] }] };
  const o = c.raAbBuild('amend').split('\n');
  assert.equal(o[1], '제2조(다른 내규의 개정) 「국외여비지침」 일부를 다음과 같이 개정한다.');
  assert.equal(o[2], '제3조 중 “「여비규정」 제5조”를 “「여비규정」 제6조”로 한다.');
});

test('raClauseFmt: 표준 조문 자리표시자와 조사', () => {
  const c = load();
  const t = c.raClauseFmt('{head:이} 정하고 {deputy:은} 돕는다. 이 {kind}에 따른다.', '지침');
  assert.ok(!/[{}]/.test(t));
  assert.match(t, /이 지침에 따른다\.$/);
});

test('완성도: 위임 조항 표시·종류 추정·조 번호 목록', () => {
  const c = load();
  assert.equal(c.raDelArt({ art: '제33조(기술지원)' }), '제33조');
  assert.equal(c.raDelArt({ art: '제33조', title: '기술지원' }), '제33조');
  assert.equal(c.raCatOf('업무용 드론 운영지침'), '지침');
  assert.equal(c.raCatOf('여비규정 시행세칙'), '시행세칙');
  assert.equal(JSON.stringify(c.raArtList('제31조 제2항, 32조의2')), JSON.stringify(['31', '32의2']));
  assert.equal(JSON.stringify(c.raArtList('31, 32')), JSON.stringify(['31', '32']));
});

test('완성도: 개정문 조사(제7조의3을)·대비표 <신 설> 표시·밑줄 구간', () => {
  const c = load();
  assert.equal(c.raAmendSentences(null, { type: 'insert', no: '7의3', title: 't', body: 'b' }).head, '제7조의3을 다음과 같이 신설한다.');
  assert.equal(c.raAmendSentences({ no: '7의6', title: 't', body: 'b' }, { type: 'delete', no: '7의6' }).head, '제7조의6을 삭제한다.');
  const r = c.raCmpCell({ no: '5', title: 'a', body: '① 가.\n② 나.' }, { no: '5', title: 'a', body: '① 가.\n② 나.\n③ 다.' }, false);
  assert.match(r[2], /<신 설>/);
  const runs = c.raHtmlRuns('숙박비 <u class="ra-d">3만원&amp;</u><br>끝');
  assert.equal(JSON.stringify(runs), JSON.stringify([{ s: '숙박비 ', u: '' }, { s: '3만원&', u: 'd' }, { s: '\n끝', u: '' }]));
});

test('완성도: 손대지 않은 조문은 개정 대상에서 뺀다', () => {
  const c = load();
  const RA = c.__RA();
  RA.amend.changes = [{ type: 'modify', no: '1', title: '목적', body: '같음' }, { type: 'insert', no: '1의2', title: 'x', body: 'y' }];
  // _raArts 가 없으면(현행 미상) 모두 바뀐 것으로 본다
  assert.equal(c.raEffChanges().length, 2);
});

test('완성도: 절차 — 대안 단계는 조건이 맞는(soft) 쪽을 고르고, 일정에 미정 단계를 셈한다', () => {
  const c = load();
  const RA = c.__RA();
  RA.proc.ans = { level: 'reg' };
  const ids = c.raProcSteps().map(s => s.id);
  assert.ok(ids.includes('review'), ids.join(','));          // 상급위원회 내규심의가 요약에서 빠지지 않는다
  const st = c.raProcState();
  const sc = c.raSchedule(st.live);
  assert.ok(sc.total > 0);
  assert.equal(typeof sc.tbd, 'number');
});

test('알리오: 검색어 추정·옛 판 괄호 제거', () => {
  const c = load();
  const RA = c.__RA();
  RA.enact.title = '임직원 여비규정'; assert.equal(c.raAlioGuess('enact'), '여비');
  RA.enact.title = '업무용 드론 운영지침'; assert.equal(c.raAlioGuess('enact'), '드론');
  RA.amend.title = '여비규정'; assert.equal(c.raAlioGuess('amend'), '여비');
  assert.equal(c.alioBase('인사규정(2023년 1월 개정)'), '인사규정');
});
