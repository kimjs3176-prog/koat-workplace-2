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
  // 단서가 있는 항은 고친 곳이 본문인지 단서인지 밝힌다
  const pv = { no: '8', title: '휴가', body: '① 연차휴가는 15일로 한다. 다만, 신규 직원은 10일로 한다.\n② x' };
  assert.equal(S(pv, { ...pv, body: '① 연차휴가는 15일로 한다. 다만, 신규 직원은 11일로 한다.\n② x' }), '제8조제1항 단서 중 “10일”을 “11일”로 한다.');
  assert.equal(S(pv, { ...pv, body: '① 연차휴가는 20일로 한다. 다만, 신규 직원은 10일로 한다.\n② x' }), '제8조제1항 본문 중 “15일”을 “20일”로 한다.');
  // 같은 바꿈은 “각각”으로 묶는다
  assert.equal(S({ no: '9', title: 'a', body: '① 원장은 정한다.\n② 원장은 승인한다.\n③ x' }, { no: '9', title: 'a', body: '① 기관장은 정한다.\n② 기관장은 승인한다.\n③ x' }),
    '제9조제1항 및 제2항 중 “원장”을 각각 “기관장”으로 한다.');
  // 호가 있으면 “각 호 외의 부분”, 끝에 덧붙인 호는 신설
  assert.equal(S({ no: '8', title: '대상', body: '다음 사람에게 지급한다.\n1. 임원\n2. 직원' }, { no: '8', title: '대상', body: '다음 사람에게 준다.\n1. 임원\n2. 직원\n3. 계약직' }),
    '제8조 각 호 외의 부분 중 “지급한다”를 “준다”로 하고, 같은 조에 제3호를 다음과 같이 신설한다. | 3. 계약직');
  assert.equal(S({ no: '9', title: 'a', body: '① aa\n② bb\n③ cc' }, { no: '9', title: 'a', body: '① aa\n② bb' }), '제9조제3항을 삭제한다.');
  // 중간에 항을 끼우면(번호가 밀림) 밀린 번호를 고치고 신설한다
  assert.equal(S({ no: '4', title: 'a', body: '① 가.\n② 나.' }, { no: '4', title: 'a', body: '① 가.\n② 새 항.\n③ 나.' }), '제4조제2항을 제3항으로 하고, 같은 조에 제2항을 다음과 같이 신설한다. | ② 새 항.');
  // 밀림과 내용 수정이 섞이면 조 전체를 다시 쓴다
  assert.match(S({ no: '4', title: 'a', body: '① 가.\n② 나.' }, { no: '4', title: 'a', body: '① 가가.\n② 새 항.\n③ 나.' }), /^제4조를 다음과 같이 한다\./);
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
  assert.equal(o[1], '제2조(다른 내규의 개정) 국외여비지침 일부를 다음과 같이 개정한다.');
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

test('알리오: 규정 체계 비교 주제어·이유서 다른 기관 사례', () => {
  const c = load();
  const orgs = ['한국농어촌공사'];
  assert.equal(c.raBenchKey('여비규정(2023년 1월 개정)', orgs), '여비');
  assert.equal(c.raBenchKey('한국농어촌공사 인사규정 시행세칙', orgs), '인사');
  assert.equal(c.raBenchKey('임직원 행동강령 운영지침', orgs), '행동강령');
  assert.ok(c.raBenchHas(['개인정보보호'], '개인정보보호') && !c.raBenchHas(['여비'], '인사'));
  const RA = c.__RA();
  RA.enact.refs = { 'alio|C1|9|5': { reg: '드론 운영규정', org: '한국농어촌공사', no: '5', title: '비행 승인', body: '…', src: 'alio' } };
  RA.enact.title = '드론 운영지침';
  const o = c.raOutReason(c.raDocCtx('enact'));
  const it = o.items.find(x => /다른 공공기관 사례/.test(x.t));
  assert.ok(it && it.s[0] === '한국농어촌공사 「드론 운영규정」 제5조(비행 승인)');
});

test('단계별 화면: 앞 단계가 끝나야 넘어가고, 저장된 단계가 막히면 앞으로 돌린다', () => {
  const c = load();
  const RA = c.__RA();
  RA.enact.step = 4;                                   // 초안 없이 문서 단계로 저장돼 있으면
  assert.equal(c.raWizStep('enact'), 2);               // 초안 단계로
  assert.match(c.raWizGate('enact', 3), /초안/);
  RA.enact.draft = { text: '제1조(목적) 가.' };
  assert.equal(c.raWizGate('enact', 4), '');
  assert.equal(c.raWizStep('enact'), 4);
  RA.amend.step = 2; RA.amend.slug = ''; RA.amend.pasted = false; RA.amend.changes = [];
  assert.equal(c.raWizStep('amend'), 0);               // 내규를 고르지 않았으면 첫 단계
  RA.amend.slug = '여비규정';
  assert.equal(c.raWizStep('amend'), 1);               // 수정안이 없으면 고치기 단계
  const html = c.raWiz('enact', [0, 1, 2, 3, 4].map(i => () => `<p>${i}</p>`));
  assert.match(html, /aria-current="step"/);
  assert.match(html, /<p>4<\/p>/);
});

test('raSubst: 분수·낫표는 통째로, 공통 조사는 따옴표 밖으로', () => {
  const c = load();
  const r1 = JSON.stringify(c.raSubst('출석위원 2분의 1 이상의 찬성으로 의결한다.', '출석위원 3분의 1 이상의 찬성으로 의결한다.'));
  assert.ok(r1.includes('2분의 1') && r1.includes('3분의 1'), r1);
  const r2 = JSON.stringify(c.raSubst('「공공기관의 운영에 관한 법률」에 따른다.', '「공공기관의 운영에 관한 법률 시행령」에 따른다.'));
  assert.ok(r2.includes('「공공기관의 운영에 관한 법률」') && r2.includes('시행령」'), r2);
  const r3 = JSON.stringify(c.raSubst('여비는 3만원을 지급한다.', '여비는 5만원을 지급한다.'));
  assert.ok(r3.includes('3만원') && !r3.includes('3만원을'), r3);
});

test('raBenchSame: 같은 조 제목 판정', () => {
  const c = load();
  assert.ok(c.raBenchSame('출장비', '출장비'));
  assert.ok(c.raBenchSame('출장비지급', '출장비지급기준'));
  assert.ok(!c.raBenchSame('목적', '목적외사용금지'));
  assert.ok(!c.raBenchSame('', '목적'));
});

test('_raNormalize: 손상된 저장본은 구역별로 기본값을 채운다', () => {
  const c = load();
  const n = c._raNormalize({ enact: { title: 'X', dels: 'bad' }, amend: { slug: '감사규정', changes: null, sel: 3 }, bulk: 1, tab: 5, extra: 1 });
  assert.equal(n.enact.title, 'X');
  assert.ok(Array.isArray(n.enact.dels) || n.enact.dels.length === 0);
  assert.equal(n.amend.slug, '감사규정');
  assert.equal(n.amend.changes.length, 0);
  assert.equal(typeof n.amend.sel, 'object');
  assert.equal(n.bulk.old, '');
  assert.equal(n.tab, 'agent');
  assert.equal(n.extra, 1);
  assert.equal(c._raNormalize(null).tab, 'agent');
});

test('raParse·raDocLaw: 조문 칸의 부칙과 별표를 살린다', () => {
  const c = load();
  const p = c.raParse('제1조(목적) 가.\n제2조(지급) 수당은 별표 1과 같다.\n[별표 1] 수당 지급 기준\n구분 금액');
  assert.equal(p.articles.length, 2);
  assert.ok(!p.articles[1].body.includes('별표 1]'));
  assert.match(p.appendix, /^\[별표 1\]/);
  const RA = c.__RA();
  RA.enact.title = '수당 규칙';
  RA.enact.draft = { text: '제1조(목적) 가.\n부    칙\n이 규칙은 2027년 1월 1일부터 시행한다.\n[별표 1] 수당 지급 기준', addenda: '' };
  const law = c.raDocLaw(c.raDocCtx('enact'));
  assert.match(law, /2027년 1월 1일부터 시행한다/);
  assert.match(law, /부 {4}칙[\s\S]*\[별표 1\] 수당 지급 기준/);
});

test('raSwapTerm: 낱말을 바꾸고 뒤 조사를 맞춘다', () => {
  const c = load();
  assert.equal(c.raSwapTerm('재단은 재단이사장을 둔다. 재단의 장', '재단', '농진원', true).text, '농진원은 재단이사장을 둔다. 농진원의 장');
  assert.equal(c.raSwapTerm('위원회를 둔다', '위원회', '심의단', true).text, '심의단을 둔다');
  assert.equal(c.raSwapTerm('「구 지침」으로 정한다', '구 지침', '새 지침서', false).text, '「새 지침서」으로 정한다');
});

test('raQtyDiff: 금액·기간·분수 바뀜을 찾는다', () => {
  const c = load();
  const d = c.raQtyDiff('숙박비는 3만원, 기간은 30일로 한다.', '숙박비는 5만원, 기간은 30일로 한다.');
  assert.equal(JSON.stringify(d), JSON.stringify({ from: ['3만원'], to: ['5만원'] }));
  assert.equal(c.raQtyDiff('2분의 1 이상', '3분의 2 이상').to[0], '3분의2');
  assert.equal(c.raQtyDiff('원장이 정한다', '기관장이 정한다'), null);
});

test('raAmendSentences: 삭제 문형·단서·순서·끝에 덧붙인 항·별표 괄호', () => {
  const c = load();
  const S = (o, n) => c.raAmendSentences(o, n).head;
  const b = { no: '7', title: 't', body: '① 가는 한다.\n② 나는 한다.\n③ 다는 한다.' };
  assert.equal(S(b, { ...b, body: '① 가는 한다.\n② 삭제\n③ 다는 한다.' }), '제7조제2항을 삭제한다.');
  const d = { no: '25', title: 't', body: '① 가.\n② 여비를 지급할 수 있다. 다만, 해당 여비는 받을 수 없다.' };
  assert.equal(S(d, { ...d, body: '① 가.\n② 여비를 지급할 수 있다.' }), '제25조제2항 단서를 삭제한다.');
  assert.equal(S({ ...d, body: '① 가.\n② 여비를 지급할 수 있다.' }, d), '제25조제2항에 단서를 다음과 같이 신설한다.');
  const t = { no: '28', title: 't', body: '① 가는 3일로 한다.\n② 나는 2만원으로 한다.' };
  assert.equal(S(t, { ...t, body: t.body + '\n③ 다.\n④ 라.' }), '제28조에 제3항 및 제4항을 각각 다음과 같이 신설한다.');
  const r = c.raAmendSentences(t, { ...t, body: '① 가는 5일로 한다.\n② 나는 3만원으로 한다.' }).head;
  assert.ok(r.indexOf('“3일”') < r.indexOf('“2만원”'), r);
  const x = { no: '11', title: 't', body: '수수료는 〔별표 2〕와 같다. 기타 사항은 따로 정한다.' };
  assert.equal(S(x, { ...x, body: '수수료는 〔별표 3〕와 같다. 기타 사항은 따로 정한다.' }), '제11조 중 “〔별표 2〕”를 “〔별표 3〕”으로 한다.');
});

test('raFullRenumber: 전부개정은 조 번호를 다시 매기고 내부 인용도 고친다', () => {
  const c = load();
  const F = { arts: [
    { no: '1', title: '목적', body: '이 규칙은 …' },
    { no: '2', title: '', body: '', deleted: true },
    { no: '3', title: '위원회', body: '제4조에 따른 위원과 「상법」 제4조를 본다.' },
    { no: '3의2', title: '간사', body: '제3조의 위원회에 간사를 둔다.' },
    { no: '4', title: '위원', body: '가.' }] };
  const r = c.raFullRenumber(F);
  assert.equal(r.arts.map(a => a.no).join(','), '1,2,3,4');
  assert.equal(r.arts[1].body, '제4조에 따른 위원과 「상법」 제4조를 본다.');
  assert.equal(r.arts[2].body, '제2조의 위원회에 간사를 둔다.');
});

test('경과조치·조사 교체: ①② 부칙 변환, 최대 조 번호, 금액 쉼표·연도, 괄호 붙은 내규명', () => {
  const c = load();
  vm.runInContext(`raTransItems=()=>[{no:'5',txt:'x'}]; raDirty=()=>{}; _raSave=()=>{}; raRerender=()=>{};`, c);
  const add = (title, addenda) => vm.runInContext(`RA.amend.title=${JSON.stringify(title)}; RA.amend.addenda=${JSON.stringify(addenda)}; raTransAdd(); RA.amend.addenda`, c);
  assert.equal(add('업무처리 규칙(구 직무발명 보상규칙)', '①(시행일) 이 규칙은 2024. 1. 1.부터 시행한다.\n②(적용례) 가.'),
    '제1조(시행일) 이 규칙은 2024. 1. 1.부터 시행한다.\n제2조(적용례) 가.\n제3조(경과조치) 이 규칙 시행 당시 종전의 제5조에 따라 진행 중인 사항에 대해서는 종전의 규정에 따른다.');
  assert.match(add('여비규정', '제1조(시행일) 가.\n제3조(경과) 나.\n제5조는 다.'), /\n제4조\(경과조치\)/);
  assert.equal(c.raQtyDiff('1,000원 2024년', '1000원 2025년'), null);
  assert.equal(c.raSwapTerm('재단으로서 재단이었다', '재단', '농진원', false).text, '농진원으로서 농진원이었다');
});

test('개정문 문형: 어미를 조사로 떼지 않음·낱말 삭제·안쪽 따옴표·같은 항', () => {
  const c = load();
  const S = (no, ob, nb) => c.raAmendSentences({ no, title: 't', body: ob }, { no, title: 't', body: nb, type: 'modify' }).head;
  assert.equal(S('4', '원장은 수당을 지급하는 경우 통보한다.', '원장은 수당을 지급할 수 있는 경우 통보한다.'), '제4조 중 “지급하는”을 “지급할 수 있는”으로 한다.');
  assert.equal(S('9', '원장은 예산의 범위에서 수당을 지급할 수 있다.', '원장은 수당을 지급할 수 있다.'), '제9조 중 “예산의 범위에서 ”를 삭제한다.');
  assert.ok(!/““/.test(S('11', '용어는 다음과 같다.\n1. “직원”이란 정규직을 말한다.\n2. “부서”란 팀을 말한다.', '용어는 다음과 같다.\n1. “직원”이란 정규직을 말한다.\n2. “부서”란 팀과 실을 말한다.')));
  assert.equal(S('8', '① 가.\n② 다음 각 호.\n1. 갑\n2. 을\n3. 병', '① 가.\n② 다음 각 호.\n1. 갑\n2. 삭제\n3. 병\n4. 정'), '제8조제2항제2호를 삭제하고, 같은 항에 제4호를 다음과 같이 신설한다.');
  const B = '① 위원회는 7명으로 구성한다.\n② 위원장은 원장이 된다.';
  const r = c.raCmpCell({ no: '5', title: '위원회', body: B }, { no: '5', title: '위원회의 구성', body: B }, true);
  assert.equal(r[3], '제5조(위원회의 구성) ① (현행과 같음)\n② (현행과 같음)');
  assert.equal(r[2], '제5조(위원회) ① (생 략)\n② (생 략)');
});

test('항·호 중간 신설: 번호 밀림 문형과 대비표 “(현행 제N항과 같음)”', () => {
  const c = load();
  const S = (no, ob, nb) => c.raAmendSentences({ no, title: 't', body: ob }, { no, title: 't', body: nb, type: 'modify' });
  const O = '① 위원회는 7명으로 구성한다.\n② 위원장은 원장이 된다.\n③ 위원은 원장이 임명한다.';
  const N = '① 위원회는 7명으로 구성한다.\n② 간사 1명을 둔다.\n③ 위원장은 원장이 된다.\n④ 위원은 원장이 임명한다.';
  const r = S('5', O, N);
  assert.equal(r.head, '제5조제3항을 제4항으로, 제2항을 제3항으로 하고, 같은 조에 제2항을 다음과 같이 신설한다.');
  assert.deepEqual([...r.lines], ['② 간사 1명을 둔다.']);
  assert.equal(S('8', '① 가.\n② 다음 각 호와 같다.\n1. 갑\n2. 을\n3. 병', '① 가.\n② 다음 각 호와 같다.\n1. 갑\n2. 새\n3. 을\n4. 병').head,
    '제8조제2항제3호를 제4호로, 제2호를 제3호로 하고, 같은 항에 제2호를 다음과 같이 신설한다.');
  const t = c.raCmpCell({ no: '5', title: 't', body: O }, { no: '5', title: 't', body: N }, true);
  assert.match(t[3], /③ \(현행 제2항과 같음\)\n④ \(현행 제3항과 같음\)$/);
  assert.match(t[2], /<신 설>/);
});

test('심의 제출: 심의안건서·규제심사서·부패영향평가 기초자료·점검표', () => {
  const c = load();
  vm.runInContext(`_raArts={articles:[{no:'15',title:'숙박비',body:'① 숙박비는 실비로 지급한다.\\n② 추가 지급은 10분의 3 범위에서 한다.\\n③ 받으려는 자는 증빙을 제출하여야 한다.'}]};
    RA.amend.title='여비규정'; RA.amend.slug='여비규정'; RA.amend.purpose='추가 지급 한도를 현실화하려는 것임.';
    RA.amend.changes=[{type:'modify',no:'15',title:'숙박비',body:'① 숙박비는 실비로 지급한다.\\n② 추가 지급은 10분의 5 범위에서 한다.\\n③ 받으려는 자는 증빙을 제출하여야 한다.\\n④ 원장의 승인을 받아야 한다.'}];
    RA.proc.ans={level:'rule',minor:'n',public:'n',multi:'y',impact:'y',burden:'y'};
    Object.assign(raSub_('amend'),{dept:'경영지원팀',proposer:'팀장 홍길동',meet:'2026-11-30'});`, c);
  const B = c.raDocsBuild('amend');
  assert.match(B.agenda, /「여비규정」 일부개정\(안\)을 붙임과 같이 의결한다\./);
  assert.match(B.agenda, /한국농업기술진흥원 경영지원팀 팀장 홍길동/);
  assert.match(B.agenda, /숙박비 조정\(10분의3 → 10분의5\)\(안 제15조\)/);
  assert.match(B.regul, /제15조\(숙박비\): ④ 원장의 승인을 받아야 한다\./);   // 바뀐 항만(그대로 둔 ③ 제출 의무는 빼고)
  assert.ok(!/증빙을 제출/.test(B.regul));
  assert.match(B.corrupt, /■ 개정/);
  const ck = c.raSubmitCheck('amend', B).map(x => x.st + ':' + x.t).join('\n');
  assert.match(ck, /warn:여러 부서 소관/);
  assert.match(ck, /제출 기한: 2026\. 11\. 23\./);
  const blocks = c.raDocBlocks(B, ['agenda', 'law', 'cmp', 'regul']);
  assert.ok(blocks.filter(b => b.t === 'table').length >= 3 && blocks.some(b => b.t === 'break'));
});

test('심의 제출: 절차 미답은 단정하지 않고, 의견 집계·붙임·규제 판단 기본값', () => {
  const c = load();
  vm.runInContext(`_raArts={articles:[{no:'17',title:'근무지내 출장',body:'① 4시간 이상인 자에게는 1만원을 지급한다.'}]};
    RA.amend.title='여비규정'; RA.amend.changes=[{type:'modify',no:'17',title:'근무지내 출장',body:'① 4시간 이상인 자에게는 1만5천원을 지급한다.'}]; RA.proc.ans={};
    Object.assign(raSub_('amend'),{opinions:[{who:'갑',what:'찬성',res:'일부 반영'},{who:'을',what:'반대',res:'검토 중'}]});`, c);
  const B = c.raDocsBuild('amend');
  assert.match(B.agenda, /대국민 사전예고: ○○\(해당 여부 확인\)/);
  assert.match(B.agenda, /일부 반영 1건, 미반영 0건, 검토 중 1건/);
  assert.match(B.agenda, /조정\(1만원 → 1만5천원\)/);
  assert.match(B.agenda, /재정 소요: 연간 ○○원/);                     // 금액이 바뀌면 재정 소요 자리
  assert.match(B.regul, /\| -$/m);                                    // 규제가 없으면 판단 기본값은 “-”
  const ag = c.raAgendaBlocks(B.c, 'amend', ['agenda', 'law']);
  assert.match(c.raBlocksText(ag), /붙임  개정안 1부\.  끝\./);       // 한 건이면 번호 없이
  assert.ok(c.raSubmitCheck('amend', B).some(x => x.st === 'err' && /반영 여부를 정하지 않은 의견 1건/.test(x.t)));
  assert.equal(c.raLawDate('2027. 1. 1.'), '2027년 1월 1일');
});

test('AI 산출물 검토: 원문 대비 수정 집계·검토 확인·문서 표기', () => {
  const c = load();
  const RA = c.__RA();
  RA.amend.model = 'gemini:x';
  RA.amend.changes = [
    { type: 'modify', no: '5', title: '일비', body: '일비는 3만원으로 한다.', ai: '일비는 3만원으로 한다.', aiTitle: '일비' },
    { type: 'modify', no: '6', title: '숙박비', body: '숙박비는 실비로 한다.', ai: '숙박비는 7만원으로 한다.', aiTitle: '숙박비' },
    { type: 'modify', no: '7', title: '식비', body: '식비는 2만원으로 한다.' },          // 사람이 직접 고친 조(AI 원문 없음)
  ];
  const pv = c.raAiProv('amend');
  assert.equal(`${pv.total}/${pv.same}/${pv.edited}`, '2/1/1');
  assert.match(c.raAiChip(RA.amend.changes[0], 0), /AI 원문 그대로/);
  assert.match(c.raAiChip(RA.amend.changes[1], 1), /사람이 고침/);
  assert.equal(c.raAiChip(RA.amend.changes[2], 2), '');
  assert.match(c.raAiMarkText('amend'), /AI가 쓴 조문 2개 중 1개 담당자 수정.*검토 확인 전/);
  c.raMeSet('주임 홍길동'); c.raSub_('amend').aiOk = true;
  assert.match(c.raAiMarkText('amend'), /검토: 주임 홍길동 \(/);
  RA.amend.aiMark = false;
  assert.equal(c.raAiMarkBlocks('amend').length, 0);
  // 제정: 초안 원문과 조별로 견준다
  RA.enact.draft = { text: '제1조(목적) 가.\n제2조(정의) 나를 고침.', ai: '제1조(목적) 가.\n제2조(정의) 나.', model: 'gemini:x' };
  const pe = c.raAiProv('enact');
  assert.equal(`${pe.total}/${pe.same}/${pe.edited}`, '2/1/1');
  RA.enact.draft = { text: '제1조(목적) 가.', ai: '', template: true };
  assert.equal(c.raAiProv('enact'), null);                                   // 표준 골격(규칙 기반)은 AI 산출물이 아니다
});
