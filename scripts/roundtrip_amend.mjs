// 개정문 왕복 시험 — 등록된 내규 전체에 무작위 개정을 가해 개정문을 만들고, 그 개정문을 현행에 다시 적용해 수정안과 같은지 센다.
// 사용: python scripts/roundtrip_amend.py  (내규를 JSON 으로 넘겨 이 스크립트를 부른다)
//       node scripts/roundtrip_amend.mjs regs.json [seed] [rounds]
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cfg = JSON.parse(fs.readFileSync(path.join(root, 'org_config.json'), 'utf8'));
const regs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const seed = +(process.argv[3] || 7), rounds = +(process.argv[4] || 2);

function load() {
  const store = {};
  const ctx = {
    console, Date, Math, JSON, setTimeout, clearTimeout,
    localStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
    sessionStorage: { getItem: () => null, setItem() {} },
    document: { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], title: '' },
    window: { scrollY: 0, scrollTo() {} },
    escHtml: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'),
    argAttr: s => String(s), getAiSettings: () => ({}), _toast() {}, _copyText() {}, openAiModal() {},
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(root, 'assets/reg_agent.js'), 'utf8') + '\n;globalThis.__RA=()=>RA; globalThis.__setOrg=o=>{RA_ORG=o;}; globalThis.__setArts=a=>{_raArts=a;};', ctx);
  const fmt = o => typeof o === 'string' ? o.replace(/\{head\}/g, cfg.head).replace(/\{deputy\}/g, cfg.deputy).replace(/\{notice_days\}/g, cfg.notice_days).replace(/\{staff_days\}/g, cfg.staff_days)
    : Array.isArray(o) ? o.map(fmt) : o && typeof o === 'object' ? Object.fromEntries(Object.entries(o).map(([k, v]) => [k, fmt(v)])) : o;
  ctx.__setOrg(fmt(cfg));
  return ctx;
}
const c = load(), RA = c.__RA();
const HANG = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳';

// 결정적 난수
let st = seed >>> 0;
const rnd = () => { st = (st + 0x6D2B79F5) >>> 0; let t = st; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const pick = a => a[Math.floor(rnd() * a.length)];

const units = b => c.raUnits(b);
const join = us => us.map(u => u.text).join('\n');
const hs = us => us.filter(u => u.lv === 'h');
// 수정 종류: 각각 (현행 조) → 바뀐 조 또는 null(적용 불가)
const MUT = {
  numChange(a) {                                   // 7일 → 10일 (그 수가 단위 안에 한 번만 나오는 곳)
    const us = units(a.body); const cand = [];
    us.forEach((u, i) => { const m = [...u.text.matchAll(/(?<![\d,.])(\d{1,3})(?=\s*(?:일|개월|년|회|시간|만원|천원|원|명|%|퍼센트|주)\b|\s*(?:일|개월|년|회|시간|만원|천원|원|명|주)(?![가-힣]))/g)]; m.forEach(x => { if (u.text.split(x[1]).length === 2) cand.push([i, x[1]]); }); });
    if (!cand.length) return null; const [i, n] = pick(cand);
    us[i].text = us[i].text.replace(n, String(+n + 3)); return { ...a, body: join(us) };
  },
  wordSwap(a) {
    const us = units(a.body); const pairs = [['하여야 한다', '할 수 있다'], ['할 수 있다', '하여야 한다'], ['원장', '부원장'], ['승인', '허가'], ['제출', '보고']];
    const cand = []; us.forEach((u, i) => pairs.forEach(([x, y]) => { if (u.text.split(x).length === 2 && !u.text.includes(y)) cand.push([i, x, y]); }));
    if (!cand.length) return null; const [i, x, y] = pick(cand); us[i].text = us[i].text.replace(x, y); return { ...a, body: join(us) };
  },
  delTailHang(a) {
    const us = units(a.body), H = hs(us); if (H.length < 2) return null;
    const k = us.indexOf(H[H.length - 1]); return { ...a, body: join(us.slice(0, k)) };
  },
  markDel(a) {                                     // 가운데 항을 “② 삭제”로
    const us = units(a.body), H = hs(us); if (H.length < 3) return null;
    const t = H[1]; const k = us.indexOf(t); let e = k + 1; while (e < us.length && us[e].lv !== 'h') e++;
    const out = us.slice(0, k).concat([{ ...t, text: HANG[t.h - 1] + ' 삭제' }], us.slice(e)); return { ...a, body: join(out) };
  },
  addHang(a) {
    const us = units(a.body), H = hs(us); if (!H.length || H.length >= 19) return null;
    if (H.some((u, i) => u.h !== i + 1)) return null;
    return { ...a, body: a.body + '\n' + HANG[H.length] + ' 새로 정하는 사항은 원장이 따로 정한다.' };
  },
  insHang(a) {                                     // 제2항 자리에 끼워 넣고 뒤 번호를 민다
    const us = units(a.body), H = hs(us); if (H.length < 2 || H.length >= 19 || us[0].lv !== 'h') return null;
    if (H.some((u, i) => u.h !== i + 1)) return null;
    const out = []; us.forEach(u => { if (u.lv === 'h' && u.h >= 2) { if (u.h === 2) out.push({ lv: 'h', text: '② 새로 끼워 넣는 항의 내용은 따로 정한다.' }); out.push({ ...u, text: u.text.replace(/^[①-⑳]/, HANG[u.h]) }); } else out.push(u); });
    return { ...a, body: join(out) };
  },
  titleChange(a) { return a.title ? { ...a, title: a.title + ' 등' } : null; },
  delDanseo(a) {
    const us = units(a.body); const cand = us.map((u, i) => [u, i]).filter(([u]) => u.text.search(/\s다만[,，]/) > 0 && !u.text.includes('\n'));
    if (!cand.length) return null; const [u, i] = pick(cand); us[i].text = u.text.slice(0, u.text.search(/\s다만[,，]/)).trim(); return { ...a, body: join(us) };
  },
  addDanseo(a) {
    const us = units(a.body); const cand = us.map((u, i) => i).filter(i => !/다만/.test(us[i].text) && us[i].lv !== 'mk' && !us[i].text.includes('\n'));
    if (!cand.length) return null; const i = pick(cand); us[i].text = us[i].text.trimEnd() + ' 다만, 원장이 따로 정하는 경우에는 그러하지 아니하다.'; return { ...a, body: join(us) };
  },
  replaceUnit(a) {
    const us = units(a.body); if (!us.length) return null; const i = Math.floor(rnd() * us.length); const u = us[i];
    const mk = (u.text.match(/^(?:[①-⑳]\s*|\d{1,2}\.\s+|[가-하]\.\s+)/) || [''])[0];
    us[i].text = mk + '이 단위의 내용을 전부 새로 쓴 문장으로 한다.'; return { ...a, body: join(us) };
  },
  hoChange(a) {
    const us = units(a.body); const cand = us.map((u, i) => i).filter(i => us[i].lv === 'ho');
    if (!cand.length) return null; const i = pick(cand); us[i].text = us[i].text.replace(/\s*$/, '') + '(원장이 정하는 경우를 포함한다)'; return { ...a, body: join(us) };
  },
};
const NAMES = Object.keys(MUT);

let total = 0, ok = 0; const fails = []; const byMut = {};
for (const r of regs) {
  const arts = r.articles.map(a => ({ no: a.no, title: a.title, body: a.body, chapter: a.chapter || '', deleted: !!a.deleted }));
  const live = arts.filter(a => !a.deleted && a.body.trim());
  if (live.length < 2) continue;
  if (new Set(arts.map(a => a.no)).size !== arts.length) continue;      // 조 번호가 겹치는 내규(건강검진이 따로 잡는다)는 뺀다
  for (let round = 0; round < rounds; round++) {
    c.__setArts({ title: r.title, revision: '', articles: arts, appendix: [] });
    Object.assign(RA.amend, { slug: r.slug, title: r.title, lawStyle: round % 2 ? 'art' : 'fine', fullRev: false, abbr: true, addenda: '', purpose: '', main: [], appx: [], selx: {} });
    const n = 1 + Math.floor(rnd() * 3); const picked = new Set(); const changes = []; const used = [];
    for (let k = 0; k < n; k++) {
      const a = pick(live); if (picked.has(a.no)) continue; picked.add(a.no);
      let cur = { ...a }, names = [];
      const tries = 1 + Math.floor(rnd() * 2);
      for (let t = 0; t < tries; t++) { const nm = pick(NAMES); const nx = MUT[nm](cur); if (nx) { cur = nx; names.push(nm); } }
      if (!names.length) continue;
      changes.push({ type: 'modify', no: cur.no, title: cur.title, body: cur.body, why: '' }); used.push(names.join('+'));
    }
    if (rnd() < 0.15) { const a = pick(live.filter(x => !picked.has(x.no))); if (a) { changes.push({ type: 'delete', no: a.no, title: a.title, body: '' }); used.push('delArticle'); } }
    if (rnd() < 0.15) { const a = pick(live); const no = a.no + (a.no.includes('의') ? '' : '의9'); if (!arts.some(x => x.no === no)) { changes.push({ type: 'insert', no, title: '특례', body: '① 이 조는 새로 둔다.\n② 세부 사항은 원장이 정한다.' }); used.push('insArticle'); } }
    if (!changes.length) continue;
    RA.amend.changes = changes;
    total++;
    const law = c.raDocLaw(c.raDocCtx('amend'));
    const res = c.raApplyAmend(arts, law, []);
    const exp = c.raAmendFullText().arts;
    const want = new Map(exp.map(a => [c.raNormNo(a.no), a])), got = new Map(res.arts.map(a => [c.raNormNo(a.no), a]));
    const diffs = [];
    new Set([...want.keys(), ...got.keys()]).forEach(no => { const w = want.get(no), g = got.get(no); if (c.raRtNorm(w) !== c.raRtNorm(g)) diffs.push({ no, exp: w ? c.raArtText(w) : '(없음)', got: g ? c.raArtText(g) : '(없음)' }); });
    const mk = used.join(',') + (round % 2 ? ' [조 단위]' : '');
    byMut[mk] = byMut[mk] || { n: 0, ok: 0 }; byMut[mk].n++;
    if (!diffs.length && !res.errors.length) { ok++; byMut[mk].ok++; }
    else if (fails.length < 40) fails.push({ reg: r.title, mut: mk, errors: res.errors.slice(0, 3), diffs: diffs.slice(0, 2).map(d => ({ no: d.no, exp: d.exp.slice(0, 300), got: d.got.slice(0, 300) })), law: law.split('\n').slice(2, 14).join(' | ').slice(0, 600) });
  }
}
const sum = { total, ok, fail: total - ok, rate: total ? +(ok / total * 100).toFixed(1) : 0, seed, rounds, regs: regs.length };
console.log(JSON.stringify({ summary: sum, byMut: Object.fromEntries(Object.entries(byMut).filter(([, v]) => v.ok < v.n)), fails }, null, 1));
