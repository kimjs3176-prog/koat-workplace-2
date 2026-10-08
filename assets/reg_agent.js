// ══════════════════════════════════════════════════════════════════════════
// ⚖ 규정 제·개정 에이전트 — 제정·개정 초안, 신구조문대비표, 영향 분석, 점검, 절차 안내
// 서버: reg_agent.py (/api/regagent/*). index.html 공용 헬퍼(escHtml·argAttr·_toast·
// _copyText·getAiSettings·openAiModal·_assistCloseBtn·closeAssist)를 사용한다.
// 작업 내용은 이 브라우저(localStorage)에만 저장한다.
// ══════════════════════════════════════════════════════════════════════════
const RA_KEY='koat_regagent_v1';
const RA_HANG='①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳';
// 선 아이콘(24×24, stroke) — 이모지 대신 OS와 무관하게 같은 모양
const RA_IC={
  enact:'<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M12 11v6M9 14h6"/>',
  amend:'<path d="M13 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4"/><path d="M13 3v5h5"/><path d="M18.5 12.5a2.1 2.1 0 0 1 3 3L16 21l-3.5 1 1-3.5z"/>',
  bulk:'<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
  upper:'<path d="M3 21h18M5 21v-9M9.5 21v-9M14.5 21v-9M19 21v-9M2 10l10-6 10 6z"/>',
  check:'<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  proc:'<path d="M3 6l1.5 1.5L7 5M3 12l1.5 1.5L7 11M3 18l1.5 1.5L7 17"/><path d="M11 6h10M11 12h10M11 18h10"/>',
  agent:'<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8zM5 3l.6 1.4L7 5l-1.4.6L5 7l-.6-1.4L3 5l1.4-.6z"/>',
  health:'<path d="M3 12h4l2-5 4 10 2-5h6"/>',
  graph:'<circle cx="5" cy="6" r="2.5"/><circle cx="19" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M7.5 6h9M6.3 8.2l4.4 7.6M17.7 8.2l-4.4 7.6"/>',
  spark:'<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/>',
  search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  doc:'<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  alert:'<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  bad:'<circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/>',
  arrow:'<path d="M5 12h14M13 6l6 6-6 6"/>',
  lock:'<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  tip:'<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/>',
};
function raIc(k,cls){ return `<svg class="ic${cls?' '+cls:''}" viewBox="0 0 24 24" aria-hidden="true">${RA_IC[k]||''}</svg>`; }
const RA_TABS=[
  ['agent','에이전트','한 문장으로 지시하면 끝까지 수행'],
  ['health','건강검진','기관 내규 진단·정비 우선순위'],
  ['enact','제정','새 내규 초안 · 심의 사전검토 · 문서 세트'],
  ['amend','개정','수정안 · 신구조문대비표 · 인용 정정'],
  ['bulk','일괄 정비','바뀐 용어·명칭을 모든 내규에 반영'],
  ['upper','상위법 영향','상위법 개정 → 개정 후보 조문'],
  ['check','전체 점검','인용·명칭·조 번호 오류'],
  ['graph','인용 관계','내규 사이 인용 관계·파급 범위'],
  ['proc','절차 안내','기관 제·개정 절차와 할 일'],
];
// 페이지 머리: 제목 + 작업 흐름(아이콘 칩). 설명 문장 대신 흐름으로 보여 준다
const RA_PAGE={
  agent:['에이전트에게 맡기기',[['spark','한 문장 지시'],['search','대상 찾기'],['amend','초안'],['bulk','인용 영향'],['check','점검·심의'],['doc','문서 세트']]],
  health:['규정 건강검진',[['search','전체 진단'],['health','점수·등급'],['upper','상위법 최신성'],['amend','정비 착수']]],
  enact:['새 내규 제정',[['info','기본 정보'],['upper','위임 조항'],['search','유사 규정'],['spark','조문 초안'],['check','점검·심의'],['doc','문서 세트']]],
  amend:['내규 개정',[['search','조문 선택'],['spark','수정안'],['doc','대비표'],['bulk','인용 영향'],['check','점검·심의'],['doc','문서 세트']]],
  bulk:['용어·명칭 일괄 정비',[['search','용어 검색'],['bulk','조사까지 교정'],['doc','개정문·부칙']]],
  upper:['상위법 개정 영향 분석',[['upper','법령 개정'],['search','인용 조문'],['alert','개정 후보'],['amend','개정 착수']]],
  check:['내규 점검',[['search','없는 조문 인용'],['doc','내규명'],['alert','옛 명칭·직위'],['check','조 번호']]],
  graph:['내규 인용 관계',[['graph','인용 관계도'],['bulk','파급 범위'],['alert','옛 명칭 인용'],['amend','정비 착수']]],
  proc:['제·개정 절차 안내',[['proc','해당 여부'],['check','단계 체크'],['doc','문서 준비']]],
};
// 기관 프로필(org_config.json) — 기관명·기관장·내규관리 규칙·절차·심의기준. 서버 /api/regagent/config
let RA_ORG=null;
async function raLoadOrg(){
  try{ const d=await raGet('/api/regagent/config'); if(d&&d.org){ RA_ORG=d.org; RA_ORG._count=d.reg_count; } }catch(e){}
  if(!RA_ORG) RA_ORG={org_name:'○○기관',org_short:'기관',head:'기관장',deputy:'부기관장',reg_word:'내규',rules_name:'내규관리규칙',email_domain:'example.or.kr',notice_days:20,staff_days:7,rules_summary:[],review_criteria:[],procedure:{questions:[],steps:[]}};
  const sub=document.getElementById('orgSub'); if(sub){ sub.textContent=RA_ORG.org_name; sub.title=`${RA_ORG.org_name} ${RA_ORG.reg_word} 제정·개정 실무 지원`; }
  document.title=`규정 제·개정 에이전트 · ${RA_ORG.org_short}`;
}
function raRules(){ return (RA_ORG&&RA_ORG.rules_name)||'내규관리규칙'; }
function _raBlank(){
  return {tab:'agent',
    agent:{req:'',steps:[],plan:null,done:null,running:false},
    health:{law:{},f:{q:'',g:''}},
    enact:{review:null,title:'',category:'규칙',dept:'',effective:'',purpose:'',contents:'',dels:[],sim:null,refs:{},draft:null,lint:null,docTab:'law',lawQ:'',lawArts:null,lawName:''},
    bulk:{old:'',neu:'',whole:true,res:null,sel:{},reason:''},
    amend:{src:'reg',pasteText:'',pasted:false,moves:'',review:null,slug:'',title:'',sel:{},intent:'',effective:'',refText:'',changes:[],purpose:'',main:[],addenda:'',notes:[],impact:null,lint:null,docTab:'cmp',filter:'',abbr:true,lawStyle:'fine',fullRev:false},
    upper:{law:'',arts:'',old:'',neu:'',res:null},
    check:{res:null,reg:'',one:null},
    graph:{sel:''},
    proc:{ans:{},chk:{},plan:{}},
    ui:{side:false}};
}
function _raLoad(){
  try{ const o=JSON.parse(localStorage.getItem(RA_KEY)||'null'); if(o&&o.enact) return Object.assign(_raBlank(),o); }catch(e){}
  return _raBlank();
}
let RA=_raLoad(); RA.agent=Object.assign({req:'',steps:[],plan:null,done:null},RA.agent||{},{running:false}); (RA.agent.steps||[]).forEach(s=>{ if(s.st==='run') s.st='err'; }); RA.health=Object.assign({law:{},f:{q:'',g:''}},RA.health||{});
let _raArtsErr='', _raArts=null, _raCatalog=null, _raSaveT=null, _raBusy={};
function _raSave(){ clearTimeout(_raSaveT); _raSaveT=setTimeout(()=>{ try{ localStorage.setItem(RA_KEY, JSON.stringify(RA)); }catch(e){ if(typeof _toast==='function') _toast('작업 내용을 저장하지 못했습니다(브라우저 저장 공간 부족).'); } },300); }
function raSet(path, val){ const ks=path.split('.'); let o=RA; for(let i=0;i<ks.length-1;i++) o=o[ks[i]]; o[ks[ks.length-1]]=val; _raSave();
  if(/^enact\.draft\.(text|addenda|purpose|main)$/.test(path)) raDirty('enact');
  if(/^enact\.(title|purpose|contents)$/.test(path)){ raDirty('enact'); raWizSync('enact'); }
  else if(path==='amend.intent') raWizSync('amend');
  else if(path==='enact.title'){ const c=raCatOf(val); if(c&&c!==RA.enact.category&&['규정','규칙','시행세칙','지침','요령','기준','예규'].includes(c)){ RA.enact.category=c; const el=document.querySelector('select[onchange*="enact.category"]'); if(el) el.value=c; } }
  else if(/^amend\.(addenda|purpose)$/.test(path)) raDirty('amend');
  else if(path==='bulk.old'||path==='bulk.neu') RA.bulk.only=null; }
// 조문을 고치면 이전 점검·심의 사전검토·표기 점검(구조가 바뀌면 영향 분석도) 결과를 버리고 다시 실행하라고 알린다
function raDirty(mode, structural){
  const S=RA[mode]; if(!S) return;
  const keys=['lint','review','nota'].concat(structural&&mode==='amend'?['impact']:[]);
  const had=keys.filter(k=>S[k]); if(!had.length) return;
  keys.forEach(k=>{ S[k]=null; }); _raSave();
  const note=`<div class="ra-stale">${typeof raIc==='function'?raIc('info'):''}내용이 바뀌었습니다. 다시 실행하세요.</div>`;
  const ids={lint:'raLint',review:'raReview',impact:'raImpact'};
  had.forEach(k=>{ if(k==='nota'){ const b=document.getElementById('raNota'); if(b) b.innerHTML=raNotaView(mode); return; } const b=document.getElementById(ids[k]); if(b) b.innerHTML=note; });
}
const _e=s=>escHtml(String(s==null?'':s));
const _a=s=>argAttr(String(s==null?'':s));

// ── 공용 유틸 ───────────────────────────────────────────────────────────────
function raKey(no){ const m=String(no||'').match(/(\d+)(?:의(\d+))?/); return m?[+m[1],+(m[2]||0)]:[0,0]; }
function raCmp(a,b){ const x=raKey(a), y=raKey(b); return x[0]-y[0]||x[1]-y[1]; }
function raLbl(no){ const k=raKey(no); return `제${k[0]}조`+(k[1]?`의${k[1]}`:''); }
function raNormNo(s){   // “제7조의2제1항” → “7의2” (항·호 번호는 버린다)
  const t=String(s||'').replace(/\s+/g,'');
  const m=t.match(/(\d+)조(?:의(\d+))?/)||t.match(/^(?:제)?(\d+)(?:의(\d+))?/);
  return m?m[1]+(m[2]?'의'+m[2]:''):'';
}
function raJosa(w,p){ p=p||['은','는']; const c=String(w||'').trim().slice(-1); if(c>='가'&&c<='힣') return ((c.charCodeAt(0)-0xAC00)%28)?p[0]:p[1]; return p[0]; }
function raKind(title){ const t=String(title||'').trim(); for(const s of ['시행세칙','정관','규정','규칙','세칙','지침','요령','기준','매뉴얼','강령']) if(t.endsWith(s)) return s; return '규정'; }
function raToday(add){ const d=new Date(); d.setDate(d.getDate()+(add||0)); return `${d.getFullYear()}. ${d.getMonth()+1}. ${d.getDate()}.`; }
function raAi(){ const s=getAiSettings(); const p=s.provider||''; return p?{provider:p, api_key:s['key_'+p]||'', model:s['model_'+p]||''}:{}; }
function raHasAi(){ const s=getAiSettings(); const p=s.provider||''; return !!(p&&(s['key_'+p]||p==='ollama')); }
async function raPost(url, body){
  const s=getAiSettings(); const h={'Content-Type':'application/json'};
  if(s.key_gemini) h['X-Gemini-Key']=s.key_gemini;     // 유사 규정 의미 검색(헤더로만 전달)
  let r; try{ r=await fetch(url,{method:'POST',headers:h,body:JSON.stringify(body||{})}); }catch(e){ return {success:false,error:'서버에 연결하지 못했습니다. 네트워크를 확인하세요.'}; }
  let d={}; try{ d=await r.json(); }catch(e){ d={success:false,error:`서버 응답 오류(${r.status})`}; }
  if(!r.ok && d.success!==false) d.success=false;
  return d;
}
async function raGet(url){
  let r; try{ r=await fetch(url); }catch(e){ return {success:false,error:'서버에 연결하지 못했습니다. 네트워크를 확인하세요.'}; }
  try{ return await r.json(); }catch(e){ return {success:false,error:`서버 응답 오류(${r.status})`}; }
}
// 같은 작업의 중복 실행(더블클릭 등)을 막는다. 실행 중이면 false
async function raOnce(key, fn){
  if(_raBusy['once:'+key]){ _toast('이미 처리 중입니다. 잠시 기다려 주세요.'); return false; }
  _raBusy['once:'+key]=true;
  try{ await fn(); } finally{ _raBusy['once:'+key]=false; }
  return true;
}
// 작업 세대: 대상 내규를 바꾸거나 새로 시작하면 올라가고, 그 전에 보낸 요청의 응답은 버린다
const _raGen={enact:0, amend:0};
function raGenBump(mode){ _raGen[mode]=(_raGen[mode]||0)+1; }
function raSpin(t){ return `<div class="assist-loading"><div class="spinner"></div><span>${_e(t)}</span></div>`; }
function raErr(msg, needKey){ return `<div class="ra-err">${raIc('alert')}<span>${_e(msg)}</span>${needKey?` <button class="svc-btn sm" onclick="openAiModal()">${raIc('spark')}AI 설정</button>`:''}</div>`; }
// ── 인포그래픽 부품 — 숫자·비율은 그림으로, 설명은 ⓘ 툴팁으로 ─────────────────
// 색조(tone): ok 양호 · warn 주의 · serious 경고 · bad 위험 · acc 강조(파랑) · n 중립 — 색만으로 뜻을 전하지 않도록 항상 글자와 함께 쓴다
function raTip(t){ return `<span class="ra-tip" tabindex="0" role="note" aria-label="${_e(t)}" data-tip="${_e(t)}">${raIc('info')}</span>`; }
function raFlow(f){ return `<ol class="ra-flow">`+f.map(([ic,l])=>`<li>${raIc(ic)}<span>${_e(l)}</span></li>`).join('')+`</ol>`; }
function raStats(items){
  return `<div class="ra-stats">`+items.map(x=>`<div class="ra-stat t-${x.tone||'n'}"${x.tip?` title="${_e(x.tip)}"`:''}><span class="ra-stat-ic">${raIc(x.ic||'info')}</span><div><b>${x.v}</b><span>${_e(x.l)}</span></div></div>`).join('')+`</div>`;
}
function raStack(segs, label){
  const tot=segs.reduce((s,x)=>s+(x.n||0),0);
  return `<div class="ra-stack" role="img" aria-label="${_e((label||'')+' '+segs.map(s=>s.l+' '+s.n).join(', '))}">`+
    `<div class="ra-stack-b">${tot?segs.filter(s=>s.n).map(s=>`<i class="t-${s.tone}" style="flex:${s.n}" title="${_e(s.l)} ${s.n}"></i>`).join(''):'<i class="t-n" style="flex:1"></i>'}</div>`+
    `<div class="ra-stack-l">${segs.map(s=>`<span class="t-${s.tone}"><i></i>${_e(s.l)} <b>${s.n}</b></span>`).join('')}</div></div>`;
}
// 가로 막대: rows=[{l, n, tone} | {l, parts:[{n,tone,l}]}] — 막대 길이는 최댓값 기준
function raBars(rows, unit, label){
  const tot=r=>r.parts?r.parts.reduce((s,p)=>s+p.n,0):r.n;
  const mx=Math.max(1,...rows.map(tot));
  return `<div class="ra-bars" role="img" aria-label="${_e(label||'')}">`+rows.map(r=>{
    const parts=r.parts||[{n:r.n,tone:r.tone||'acc'}];
    return `<div class="ra-bar"${r.go?` role="button" tabindex="0" onclick="${r.go}"`:''}><span class="ra-bar-l" title="${_e(r.l)}">${_e(r.l)}</span>`+
      `<span class="ra-bar-t">${parts.filter(p=>p.n).map(p=>`<i class="t-${p.tone}" style="width:${p.n/mx*100}%"${p.l?` title="${_e(p.l)} ${p.n}"`:''}></i>`).join('')}</span><span class="ra-bar-n">${tot(r)}${unit||''}</span></div>`; }).join('')+`</div>`;
}
// 원형 게이지(점수·진행률)
function raRing(v, max, tone, center, sub){
  const r=34, c=2*Math.PI*r, p=Math.max(0,Math.min(1,(+v||0)/(max||1)));
  return `<svg class="ra-ring" viewBox="0 0 84 84" role="img" aria-label="${_e(sub||'')} ${v}/${max}"><circle cx="42" cy="42" r="${r}" class="ra-ring-bg"/>`+
    `<circle cx="42" cy="42" r="${r}" class="ra-ring-fg t-${tone}" stroke-dasharray="${(c*p).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 42 42)"/>`+
    `<text x="42" y="${sub?44:48}" text-anchor="middle" class="ra-ring-v">${center}</text>${sub?`<text x="42" y="60" text-anchor="middle" class="ra-ring-s">${_e(sub)}</text>`:''}</svg>`;
}
async function raCatalog(){ if(_raCatalog) return _raCatalog; const d=await raGet('/api/regagent/catalog'); _raCatalog=(d&&d.regs)||[]; return _raCatalog; }
function raRegUrl(slug){ return '/regulations/'+encodeURIComponent(slug)+'/index.html'; }

// 조문 객체 ↔ 텍스트
function raArtText(a){
  if(a.deleted||a.type==='delete') return `${raLbl(a.no)} 삭제`;
  const lines=String(a.body||'').split('\n');
  return `${raLbl(a.no)}(${a.title||''}) ${lines[0]||''}`.trimEnd()+(lines.length>1?'\n'+lines.slice(1).join('\n'):'');
}
function raParse(text){
  const out=[], chapters=[]; let cur=null, chap='', zone='body'; const add=[];
  String(text||'').replace(/\r/g,'').split('\n').forEach(raw=>{
    const ln=raw.trim(); if(!ln) return;
    if(zone==='add'){ add.push(ln); return; }
    if(/^부\s*칙\s*(?:$|[<〈(（＜［\[]|\d{4}\s*[.\-년])/.test(ln)){ zone='add'; add.push(ln); return; }
    const mc=ln.match(/^제\s*\d+\s*(장|절|관|편)\s*\S.{0,38}$/);
    if(mc && !/[.。]$/.test(ln) && !/^제\s*\d+\s*조/.test(ln)){ chap=ln; chapters.push(ln); return; }
    const m=ln.match(/^제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*(?:[(（]([^)）]{0,60})[)）])?\s*(.*)$/);
    if(m && (m[3]!=null || /^삭제/.test(m[4]||'')) && !(m[3]!=null && /^(?:에|의|을|를|과|와|로|으로|및|또는|에서|에도|에는)(?=\s|$|[,.])/.test(m[4]||''))){   // “제3조(정의)에 따른…”은 본문
      cur={no:m[1]+(m[2]?'의'+m[2]:''), title:(m[3]||'').trim(), body:(m[4]||'').trim(), chapter:chap, deleted:/^[<＜〔\[]?\s*삭제\s*(?:[<＜〔\[(（][^)）>＞〕\]]{0,40}[)）>＞〕\]]|\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?)?\s*$/.test(m[4]||'')};
      if(cur.deleted) cur.body='';
      out.push(cur); return;
    }
    if(cur) cur.body+=(cur.body?'\n':'')+ln;
  });
  return {articles:out, chapters, addenda:add.join('\n')};
}
function raDraftText(arts){
  let chap='', out=[];
  arts.forEach(a=>{ if(a.chapter && a.chapter!==chap){ chap=a.chapter; out.push('', a.chapter); } out.push(raArtText(a)); });
  return out.join('\n').trim();
}

// ── 비교(신구조문대비표) ────────────────────────────────────────────────────
function raLcs(A,B,eq){
  const n=A.length, m=B.length;
  if(n*m>250000) return null;
  const dp=Array.from({length:n+1},()=>new Uint16Array(m+1));
  for(let i=n-1;i>=0;i--) for(let j=m-1;j>=0;j--) dp[i][j]=eq(A[i],B[j])?dp[i+1][j+1]+1:Math.max(dp[i+1][j],dp[i][j+1]);
  const ops=[]; let i=0,j=0;
  while(i<n&&j<m){ if(eq(A[i],B[j])){ ops.push(['=',A[i],B[j]]); i++; j++; } else if(dp[i+1][j]>=dp[i][j+1]) ops.push(['-',A[i++],null]); else ops.push(['+',null,B[j++]]); }
  while(i<n) ops.push(['-',A[i++],null]); while(j<m) ops.push(['+',null,B[j++]]);
  return ops;
}
function raTok(s){ return String(s||'').split(/(\s+|[,.·()「」“”"'<>])/).filter(x=>x!==''); }
function raWordDiff(a,b){
  const ops=raLcs(raTok(a),raTok(b),(x,y)=>x===y);
  if(!ops) return [`<u class="ra-d">${_e(a)}</u>`,`<u class="ra-i">${_e(b)}</u>`];
  let L='',R='';
  ops.forEach(([o,x,y])=>{ if(o==='='){ L+=_e(x); R+=_e(y); } else if(o==='-') L+=/^\s+$/.test(x)?_e(x):`<u class="ra-d">${_e(x)}</u>`; else R+=/^\s+$/.test(y)?_e(y):`<u class="ra-i">${_e(y)}</u>`; });
  return [L.replace(/<\/u>(\s*)<u class="ra-d">/g,'$1').replace(/<\/u>(\s*)<u class="ra-i">/g,'$1'), R.replace(/<\/u>(\s*)<u class="ra-i">/g,'$1').replace(/<\/u>(\s*)<u class="ra-d">/g,'$1')];
}
function raPrefix(line){ const m=String(line).match(/^(제\s*\d+\s*조(?:의\s*\d+)?\s*(?:\([^)]*\))?\s*)?([①-⑳]\s*)?(\d{1,2}\.\s*|[가-하]\.\s*)?/); return (m&&m[0])||''; }
// 바뀐 줄 묶음에서 현행 줄과 개정 줄을 짝짓는다. 줄 수가 같으면 차례대로,
// 다르면(항 신설·삭제로 번호가 밀린 경우) 항·호 기호를 뺀 낱말이 가장 많이 겹치는 줄끼리 순서를 지켜 짝짓는다
function raPairLines(dels, ins){
  if(dels.length===ins.length) return dels.map((d,i)=>[d,ins[i]]);
  const words=x=>new Set(raTok(String(x).slice(raPrefix(x).length)).filter(t=>t.trim()));
  const sim=(a,b)=>{ const A=words(a), B=words(b); if(!A.size||!B.size) return 0; let n=0; A.forEach(t=>{ if(B.has(t)) n++; }); return n/Math.max(A.size,B.size); };
  const out=[]; let j=0;
  dels.forEach(d=>{ let best=-1, bs=0.34;
    for(let k=j;k<ins.length;k++){ const v=sim(d,ins[k]); if(v>bs){ bs=v; best=k; } }
    if(best<0){ out.push([d,null]); return; }
    for(;j<best;j++) out.push([null,ins[j]]);
    out.push([d,ins[best]]); j=best+1; });
  for(;j<ins.length;j++) out.push([null,ins[j]]);
  return out;
}
// 한 조문의 현행/개정 → [oldHtml, newHtml, oldPlain, newPlain]
function raCmpCell(oldA, newA, abbr){
  if(!oldA){ const t=raArtText(newA); return ['&lt;신 설&gt;', `<u class="ra-i">${_e(t).replace(/\n/g,'<br>')}</u>`, '<신 설>', t]; }
  const ot=raArtText(oldA);
  if(!newA || newA.type==='delete'){ return [`<u class="ra-d">${_e(ot).replace(/\n/g,'<br>')}</u>`, `${_e(raLbl(oldA.no))} &lt;삭 제&gt;`, ot, `${raLbl(oldA.no)} <삭 제>`]; }
  const nt=raArtText(newA);
  const OL=ot.split('\n'), NL=nt.split('\n');
  const ops=raLcs(OL,NL,(x,y)=>x.trim()===y.trim())||[...OL.map(x=>['-',x,null]),...NL.map(y=>['+',null,y])];
  const L=[],R=[],LP=[],RP=[];
  for(let k=0;k<ops.length;){
    const op=ops[k];
    if(op[0]==='='){
      L.push(_e(op[1])); LP.push(op[1]);
      const same=abbr?(raPrefix(op[2])+'(현행과 같음)').trim():op[2];
      R.push(_e(same)); RP.push(same); k++; continue;
    }
    const dels=[], ins=[];
    while(k<ops.length&&ops[k][0]!=='='){ if(ops[k][0]==='-') dels.push(ops[k][1]); else ins.push(ops[k][2]); k++; }
    raPairLines(dels, ins).forEach(([d,s])=>{
      if(d!=null&&s!=null){ const [x,y]=raWordDiff(d,s); L.push(x); R.push(y); LP.push(d); RP.push(s); }
      else if(d!=null){ L.push(`<u class="ra-d">${_e(d)}</u>`); LP.push(d); R.push('&lt;삭 제&gt;'); RP.push('<삭 제>'); }
      else { L.push('&lt;신 설&gt;'); LP.push('<신 설>'); R.push(`<u class="ra-i">${_e(s)}</u>`); RP.push(s); }
    });
  }
  return [L.join('<br>'), R.join('<br>'), LP.join('\n'), RP.join('\n')];
}

// ══════════════════════════════════════════════════════════════════════════
// 진입·틀
// ══════════════════════════════════════════════════════════════════════════
function openRegAgent(tab){
  if(!RA_ORG){ const p0=document.getElementById('assistantPanel'); if(p0) p0.innerHTML=raSpin('기관 설정을 불러오는 중...'); raLoadOrg().then(()=>openRegAgent(tab)); return; }
  if(typeof wsBackToList==='function') wsBackToList();
  document.querySelector('.main-content').classList.add('assist-on');
  document.querySelectorAll('.sm-item.active').forEach(el=>el.classList.remove('active'));
  const t=document.getElementById('smRegAgent'); if(t) t.classList.add('active');
  _assistMode='regagent';
  if(tab) RA.tab=tab;
  const p=document.getElementById('assistantPanel');
  const tabs=RA_TABS.map(([k,l,h])=>`<button class="ra-tab${RA.tab===k?' on':''}" role="tab" aria-selected="${RA.tab===k}" title="${_e(h)}" onclick="raTab('${k}')">${raIc(k)}<span class="ra-tab-t"><b>${l}</b><small>${_e(h)}</small></span></button>`).join('');
  const nav=document.getElementById('raNav');
  if(nav) nav.innerHTML=tabs;
  let [pt,pf]=RA_PAGE[RA.tab]||['',[]]; if(RA.tab==='enact'||RA.tab==='amend') pf=[];
  const ph=(RA_TABS.find(x=>x[0]===RA.tab)||[])[2]||'';
  const ai=raHasAi()?`<span class="ra-pill ok">${raIc('spark')}AI 연결됨</span>`:`<button class="ra-pill" onclick="openAiModal()" title="AI 키를 넣으면 초안·수정안·검토의견을 AI가 씁니다">${raIc('spark')}AI 미설정</button>`;
  p.innerHTML=(nav?'':`<div class="ra-tabs" role="tablist">${tabs}</div>`)+
    `<header class="ra-page"><div class="ra-page-ic">${raIc(RA.tab)}</div><div class="ra-page-t"><h1 title="${_e(ph)}">${_e(pt)}</h1>${raFlow(pf)}</div><div class="ra-page-a">${ai}<span class="ra-pill subtle" title="절차·심의기준의 근거">「${_e(raRules())}」</span></div></header>`+
    `<div id="raBody" class="ra-body"></div>`;
  raOrgCard();
  raRender();
}
function raTab(k){ RA.tab=k; _raSave(); openRegAgent(); window.scrollTo({top:0}); const on=document.querySelector('.ra-nav .ra-tab.on'); if(on&&on.scrollIntoView) on.scrollIntoView({block:'nearest',inline:'center'}); }
// 좌측 기관 카드: 기관명·등록 내규 수·서버/AI 상태
function raOrgCard(){
  const c=document.getElementById('orgCard'); if(!c||!RA_ORG) return;
  const srv=(typeof _srvOk==='undefined'||_srvOk===null)?'<span class="badge">서버 확인 중</span>':_srvOk?'<span class="badge ok">서버 연결됨</span>':'<span class="badge no">서버 연결 실패</span>';
  c.innerHTML=`<div class="oc-n">${_e(RA_ORG.org_name)}</div><div class="oc-m">등록 ${_e(RA_ORG.reg_word)} ${RA_ORG._count!=null?RA_ORG._count+'건':'—'} · 「${_e(raRules())}」</div>`+
    `<div class="oc-row">${srv}</div><div class="oc-row">${raHasAi()?'<span class="badge ok">AI 연결됨</span>':'<span class="badge">AI 미설정</span>'}</div>`+
    `<div class="oc-row oc-bk"><button class="ra-link" onclick="raBackup()" title="제정·개정·절차 작업 내용을 파일로 저장(이 브라우저에만 저장되어 있음)">작업 백업</button><span>·</span><button class="ra-link" onclick="raRestore()" title="백업 파일에서 작업 내용을 되살림">복원</button></div>`;
}
// 작업 내용은 이 브라우저(localStorage)에만 있으므로 파일로 백업·복원할 수 있게 한다
function raBackup(){
  clearTimeout(_raSaveT); try{ localStorage.setItem(RA_KEY, JSON.stringify(RA)); }catch(e){}
  const data={app:'koat-regagent', version:1, saved:new Date().toISOString(), org:(RA_ORG||{}).org_name||'', state:RA};
  const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([JSON.stringify(data)],{type:'application/json'}));
  a.download=`규정에이전트_작업백업_${raYmd(new Date())}.json`; document.body.appendChild(a); a.click(); setTimeout(()=>{ URL.revokeObjectURL(a.href); a.remove(); },500);
  _toast('작업 내용을 백업 파일로 저장했습니다.');
}
function raRestore(){
  const inp=document.createElement('input'); inp.type='file'; inp.accept='.json,application/json';
  inp.onchange=()=>{ const f=inp.files&&inp.files[0]; if(!f) return;
    if(f.size>20*1024*1024){ _toast('파일이 너무 큽니다.'); return; }
    const rd=new FileReader();
    rd.onload=()=>{ let d; try{ d=JSON.parse(rd.result); }catch(e){ _toast('백업 파일을 읽지 못했습니다.'); return; }
      const st=d&&d.app==='koat-regagent'&&d.state;
      if(!st||typeof st!=='object'||!st.enact||!st.amend){ _toast('이 도구의 백업 파일이 아닙니다.'); return; }
      if(!confirm(`${d.saved?String(d.saved).slice(0,10)+'에 ':''}백업한 작업으로 지금 작업 내용을 바꿀까요?`)) return;
      try{ localStorage.setItem(RA_KEY, JSON.stringify(st)); }catch(e){ _toast('브라우저 저장 공간이 부족합니다.'); return; }
      location.reload(); };
    rd.readAsText(f); };
  inp.click();
}
function raRender(){
  if(!_raCatalog) raCatalog().then(()=>{ if(RA.tab==='enact') raRerender('enact'); });
  const b=document.getElementById('raBody'); if(!b) return;
  const t=RA.tab;
  const side=m=>RA.ui&&RA.ui.side?raProcSide(m):'';
  if(t==='enact') b.innerHTML=raLayout(raEnactView(), side('enact'));
  else if(t==='amend'){ b.innerHTML=raLayout(raAmendView(), side('amend')); if(RA.amend.slug && !_raArts && !_raBusy.arts) raLoadArts(RA.amend.slug, true); }
  else if(t==='bulk') b.innerHTML=raBulkView();
  else if(t==='agent') b.innerHTML=raAgentView();
  else if(t==='health') b.innerHTML=raHealthView();
  else if(t==='upper') b.innerHTML=raUpperView();
  else if(t==='check') b.innerHTML=raCheckView();
  else if(t==='graph') b.innerHTML=raGraphView();
  else b.innerHTML=raProcView();
  if(t==='amend'||t==='upper'||t==='check') raFillCatalog();
}
// 짧은 섹션 두 개를 나란히(좁은 화면에서는 위아래)
function raPair(a,b){ return `<div class="ra-pair">${a}${b}</div>`; }
function raLayout(main, side){ return side?`<div class="ra-layout"><div class="ra-main">${main}</div><aside class="ra-side">${side}</aside></div>`:`<div class="ra-layout one"><div class="ra-main">${main}</div></div>`; }
async function raFillCatalog(){
  const dl=document.getElementById('raRegList'); if(!dl || dl.dataset.ok) return;
  const regs=await raCatalog(); dl.innerHTML=regs.map(r=>`<option value="${_e(r.title)}">${_e(r.category||'')} · ${_e(r.revision||'')}</option>`).join(''); dl.dataset.ok='1';
}
function raSec(n, title, sub, body, id){
  const inl=sub&&/^<span class="ra-(tip|leg)"/.test(sub);   // ⓘ·범례는 제목 옆에
  return `<section class="ra-sec"${id?` id="${id}"`:''}><div class="ra-sec-h"><span class="ra-num">${n}</span><div class="ra-sec-t"><h2>${title}${inl?' '+sub:''}</h2>${sub&&!inl?`<span class="ra-sub">${sub}</span>`:''}</div></div><div class="ra-sec-b">${body}</div></section>`;
}
function raIn(path, val, ph, extra){ return `<input class="ra-in" value="${_e(val)}" placeholder="${_e(ph||'')}" oninput="raSet('${path}',this.value)" ${extra||''}>`; }
function raTa(path, val, ph, rows, extra){ return `<textarea class="ra-ta" rows="${rows||3}" placeholder="${_e(ph||'')}" oninput="raSet('${path}',this.value)" ${extra||''}>${_e(val)}</textarea>`; }

// ══════════════════════════════════════════════════════════════════════════
// 제정
// ══════════════════════════════════════════════════════════════════════════
function raEnactView(){
  const E=RA.enact;
  const cats=['규정','규칙','시행세칙','지침','요령','기준','예규'];
  const s1=`<div class="ra-grid">`+
    `<label class="ra-f"><span>내규명</span>${raIn('enact.title',E.title,'예) 업무용 드론 운영지침')}</label>`+
    `<label class="ra-f"><span>종류</span><select class="ra-in" onchange="raSet('enact.category',this.value)">${cats.map(c=>`<option${E.category===c?' selected':''}>${c}</option>`).join('')}</select></label>`+
    `<label class="ra-f"><span>소관부서</span>${raIn('enact.dept',E.dept,'예) 경영지원팀')}</label>`+
    `<label class="ra-f"><span>시행일</span>${raIn('enact.effective',E.effective,'비우면 “발령한 날”')}</label></div>`+
    `<div class="ra-grid2"><label class="ra-f"><span>제정 목적</span>${raTa('enact.purpose',E.purpose,'왜 이 내규가 필요한지 — 예) 업무용 드론의 안전한 운영과 사고 예방',4)}</label>`+
    `<label class="ra-f"><span>주요 내용 ${raTip('한 줄에 하나씩 — “제목: 내용” 형식이면 조 제목으로 씁니다')}</span>${raTa('enact.contents',E.contents,'운영책임자: 부서별 드론 운영책임자를 지정\n비행승인: 비행 3일 전까지 운영책임자 승인\n보험: 배상책임보험 가입 의무',4)}</label></div>`;
  const s2=raDelegView();
  const refTab=E.refTab||(E.simSrc==='alio'?'alio':'law');
  const nRef=Object.values(E.refs||{}), nAl=nRef.filter(r=>r.src==='alio').length;
  const refSeg=`<div class="ra-seg ra-wiz-seg" role="tablist">`+[['law','상위법 근거',(E.dels||[]).length],['own','우리 기관 비슷한 규정',nRef.length-nAl],['alio','다른 기관(알리오)',nAl]]
    .map(([k,l,n])=>`<button role="tab" class="${refTab===k?'on':''}" onclick="raSet('enact.refTab','${k}');raSet('enact.simSrc','${k==='alio'?'alio':'own'}');raRerender('enact')">${l}${n?` <b class="ra-cnt">${n}</b>`:''}</button>`).join('')+`</div>`;
  const s4=`<div class="ra-row"><button class="svc-btn yes" onclick="raEnactDraft()">${raIc('spark')}조문 초안 작성</button>`+
    `${raTip(`${raHasAi()?'AI가 위 내용·위임 조항·참고 조문으로 조문 체계와 표준 조문을 씁니다.':'AI 키가 없으면 표준 조문 골격(목적·정의·적용범위·본칙·세부사항·부칙)을 만들어 드립니다.'}`)}</div><div id="raDraft">${raEnactDraftView()}</div>`;
  const s3own=`<div class="ra-row"><button class="svc-btn" onclick="raFindSimilar()">${raIc('search')}비슷한 규정 찾기</button>${raTip(`목적·주요 내용으로 기관 ${RA_ORG.reg_word}${_raCatalog?' '+_raCatalog.length+'건':''}에서 비슷한 조문을 찾습니다. 체크한 조문은 초안 작성 때 참고합니다.`)}</div><div id="raSim">${raSimView()}</div>`;
  const refHelp={law:'이 내규를 만들 근거가 되는 법령 조문을 고르면 제1조(목적)에 반영됩니다.',own:'우리 기관 내규에서 비슷한 조문을 찾아 문체·구성을 맞춥니다.',alio:'다른 공공기관이 같은 주제를 어떻게 정했는지 찾아 참고합니다.'}[refTab];
  const body=[
    ()=>s1,
    ()=>refSeg+`<p class="ra-wiz-hint">${raIc('info')}${refHelp}</p>`+(refTab==='law'?s2:refTab==='alio'?raAlioView('enact'):s3own)+
      (nRef.length&&refTab!=='own'?`<div class="ra-meta">참고로 고른 조문 <b id="raRefCnt">${nRef.length}</b>개${nAl?` (다른 기관 ${nAl}개)`:''} <button class="ra-link" onclick="RA.enact.refs={};_raSave();raRerender('enact')">모두 빼기</button></div>`:''),
    ()=>raStaleNote('enact')+`<div id="raSecDraft">${s4}</div>`,
    ()=>raRunBar('enact')+raSub('형식 점검',`<div class="ra-row"><button class="svc-btn" onclick="raLint('enact')">${raIc('check')}점검 실행</button>${raTip('조 번호·항호 순서·인용·용어 정의·부칙·표기를 점검합니다.')}</div><div id="raLint">${raLintView(E.lint)}</div>`)+
      raSub('심의 사전검토',raReviewSec('enact')),
    ()=>`<div id="raSecDocs">${raDocsView('enact')}</div>`,
  ];
  return raWiz('enact', body);
}
// ── 단계별 화면(제정·개정 공통) — 한 번에 한 단계만 보이고, 위의 단계 표시로 어디까지 왔는지 알 수 있다 ──
const RA_WIZ={
  enact:[
    {t:'기본 정보', d:'만들 내규의 이름과 목적, 담을 내용을 적습니다.'},
    {t:'참고 자료', d:'상위법 근거·비슷한 규정을 고르면 초안이 더 정확해집니다. 건너뛰어도 됩니다.', opt:1},
    {t:'조문 초안', d:'버튼 하나로 조문 초안을 만들고 바로 고쳐 씁니다.'},
    {t:'점검·검토', d:'형식 오류와 심의기준을 미리 점검합니다.'},
    {t:'문서 받기', d:'규정안·이유서·공고문을 한글·Word로 저장합니다.'},
  ],
  amend:[
    {t:'대상 고르기', d:'개정할 내규를 불러와 고칠 조문을 체크합니다.'},
    {t:'고치기', d:'개정 의도를 적고 수정안을 만들거나 직접 고칩니다.'},
    {t:'확인·검토', d:'신구조문대비표, 인용 영향, 점검, 심의 사전검토를 확인합니다.'},
    {t:'문서 받기', d:'개정문·대비표·이유서·공고문을 한글·Word로 저장합니다.'},
  ],
};
// 단계마다 들어갈 수 있는지(빈 문자열이면 가능, 아니면 그 이유)·끝났는지
function raWizGate(mode, i){
  if(mode==='enact'){ const E=RA.enact;
    if(i>=3&&!(E.draft&&String(E.draft.text||'').trim())) return '먼저 “조문 초안” 단계에서 초안을 만드세요.';
    return ''; }
  const A=RA.amend;
  if(i>=1&&!_raArts&&!A.slug&&!A.pasted) return `먼저 개정할 ${RA_ORG.reg_word}를 불러오세요.`;
  if(i>=2&&!raEffChanges().length) return '먼저 “고치기” 단계에서 수정안을 만드세요.';
  return '';
}
function raWizDone(mode, i){
  if(mode==='enact'){ const E=RA.enact;
    return [!!(E.title&&String(E.purpose||'').trim()), !!((E.dels||[]).length||Object.keys(E.refs||{}).length), !raWizGate('enact',3)&&!raStale('enact'), !!(E.lint&&E.review), false][i]; }
  const A=RA.amend;
  return [!!_raArts&&(Object.keys(A.sel||{}).length>0||A.changes.length>0), raEffChanges().length>0, !!(A.lint&&A.review), false][i];
}
// 초안(수정안)을 만든 뒤 그 바탕이 된 입력(기본 정보·참고 자료 / 개정 의도·고른 조문)이 바뀌었는지
function raBasis(mode){
  if(mode==='enact'){ const E=RA.enact; return [E.title,E.purpose,E.contents,(E.dels||[]).map(raDelArt).join(','),Object.keys(E.refs||{}).sort().join(',')].join('|'); }
  const A=RA.amend; return [A.intent,Object.keys(A.sel||{}).sort().join(','),Object.keys(A.alioRefs||{}).sort().join(',')].join('|');
}
function raStale(mode){ const S=RA[mode], b=mode==='enact'?(S.draft||{}).basis:S.basis; return !!b&&b!==raBasis(mode); }
function raStaleNote(mode){
  if(!raStale(mode)) return '';
  return `<div class="ra-stale">${raIc('info')}${mode==='enact'?'초안을 만든 뒤 기본 정보나 참고 자료가 바뀌었습니다. 초안을 다시 만들거나 조문이 맞는지 확인하세요.':'수정안을 만든 뒤 개정 의도나 고른 조문이 바뀌었습니다. 수정안을 다시 만들거나 확인하세요.'}`+
    ` <button class="ra-link" onclick="raBasisOk('${mode}')">이대로 쓰기</button></div>`;
}
function raBasisOk(mode){ if(mode==='enact'){ if(RA.enact.draft) RA.enact.draft.basis=raBasis('enact'); } else RA.amend.basis=raBasis('amend'); _raSave(); raRerender(mode); }
function raWizStep(mode){ const S=RA[mode], n=RA_WIZ[mode].length; let i=+S.step||0; if(i<0||i>=n) i=0; while(i>0&&raWizGate(mode,i)) i--; return i; }
function raWizGo(mode, i){
  const why=raWizGate(mode,i); if(why){ _toast(why); return; }
  RA[mode].step=i; _raSave(); raRerender(mode); raWizTop();
}
function raWizTop(){
  const card=document.querySelector('.ra-wiz-card'); if(!card) return;
  const bar=document.getElementById('raWiz'), bh=bar&&getComputedStyle(bar).position==='sticky'?bar.offsetHeight:0;
  const top=card.getBoundingClientRect().top;
  if(top<bh+8) window.scrollTo({top:window.scrollY+top-bh-8, behavior:'smooth'});
  const h=card.querySelector('.ra-wiz-head h2'); if(h&&h.focus) h.focus({preventScroll:true});
}
// 점검·검토 단계: 인용 영향(개정)·형식 점검·심의 사전검토를 한 번에
function raRunBar(mode){
  const S=RA[mode], n=[mode==='amend'?!!S.impact:null, !!S.lint, !!S.review].filter(x=>x!==null), done=n.filter(Boolean).length;
  return `<div class="ra-runbar"><button class="svc-btn yes" onclick="raRunChecks('${mode}')" ${_raBusy.runAll?'disabled':''}>${raIc('check')}${_raBusy.runAll?'점검 중…':done===n.length?'모두 다시 점검':'모두 점검하기'}</button>`+
    `<span class="ra-sub">${mode==='amend'?'인용 영향 · ':''}형식 점검 · 심의 사전검토를 차례로 실행합니다 (${done}/${n.length} 완료)</span></div>`;
}
async function raRunChecks(mode){
  if(_raBusy.runAll) return; _raBusy.runAll=true; raRerender(mode);
  try{ if(mode==='amend') await raImpact(); await raLint(mode); await raReview(mode); }
  finally{ _raBusy.runAll=false;
    const card=document.querySelector('.ra-wiz-card'); if(card) card.classList.remove('running');
    const rb=document.querySelector('.ra-runbar'); if(rb) rb.outerHTML=raRunBar(mode); raWizSync(mode); }
}
function raSub(title, body){ return `<section class="ra-sub-sec"><h3>${title}</h3>${body}</section>`; }
function raWizBar(mode, i){
  const W=RA_WIZ[mode];
  return `<nav class="ra-wiz" id="raWiz" aria-label="진행 단계"><ol>`+W.map((w,k)=>{ const g=raWizGate(mode,k), done=raWizDone(mode,k);
      const sr=k===i?'현재 단계':done?'완료':g?`잠김: ${g}`:'';
      return `<li class="${k===i?'on':''}${done?' done':''}${g?' lock':''}"><button onclick="raWizGo('${mode}',${k})" ${k===i?'aria-current="step"':''}${g?' aria-disabled="true"':''} title="${_e(g||w.d)}">`+
        `<span class="ra-wiz-n" aria-hidden="true">${done&&k!==i?raIc('check'):k+1}</span><span class="ra-wiz-t"><span class="ra-wiz-l">${w.t}</span>${w.opt?'<small>선택</small>':''}</span><span class="ra-sr">${k+1}단계${sr?', '+_e(sr):''}</span></button></li>`; }).join('')+`</ol>`+
    `<button class="ra-wiz-side${RA.ui&&RA.ui.side?' on':''}" onclick="raSideToggle()" title="절차 진행 보기" aria-pressed="${!!(RA.ui&&RA.ui.side)}">${raIc('proc')}<span>절차</span></button></nav>`;
}
function raWizNav(mode, i){
  const W=RA_WIZ[mode], cur=W[i], nx=W[i+1], gate=nx?raWizGate(mode,i+1):'';
  return `<div class="ra-wiz-nav">${i>0?`<button class="svc-btn ghost" onclick="raWizGo('${mode}',${i-1})">← ${W[i-1].t}</button>`:'<span></span>'}`+
    (nx?`<span class="ra-wiz-why">${gate?_e(gate):''}</span><button class="svc-btn ${gate?'':'yes'}" ${gate?'disabled':''} onclick="raWizGo('${mode}',${i+1})">${cur.opt&&!raWizDone(mode,i)?'건너뛰고 ':''}다음: ${nx.t} →</button>`
       :`<button class="svc-btn ghost sm" onclick="raReset('${mode}')">↺ ${mode==='enact'?'제정':'개정'} 작업 새로 시작</button>`)+`</div>`;
}
// 입력·체크로 조건이 바뀌면 단계 표시와 아래 이동 버튼만 고쳐 그린다(입력 중인 칸은 그대로)
function raWizSync(mode){
  if(RA.tab!==mode) return; const i=raWizStep(mode);
  const b=document.getElementById('raWiz'); if(b) b.outerHTML=raWizBar(mode,i);
  const n=document.querySelector('.ra-wiz-nav'); if(n) n.outerHTML=raWizNav(mode,i);
  const h=document.getElementById('raSelHint'); if(h) h.innerHTML=raSelHint();
}
function raWiz(mode, body){
  const W=RA_WIZ[mode], i=raWizStep(mode), cur=W[i];
  return raWizBar(mode,i)+`<section class="ra-sec ra-wiz-card${_raBusy.runAll?' running':''}"><div class="ra-wiz-head"><span class="ra-num">${i+1}</span><div><h2 tabindex="-1">${cur.t}${cur.opt?' <span class="ra-chip">선택</span>':''}</h2><p>${cur.d}</p></div></div>`+
    `<div class="ra-sec-b">${body[i]()}</div>${raWizNav(mode,i)}</section>`;
}
function raSideToggle(){ RA.ui=RA.ui||{}; RA.ui.side=!RA.ui.side; _raSave(); raRender();
  if(RA.ui.side&&window.innerWidth<900){ const sd=document.querySelector('.ra-side'); if(sd) sd.scrollIntoView({behavior:'smooth',block:'start'}); } }
function raDelegView(){
  const E=RA.enact;
  const list=(E.dels||[]).map((d,i)=>`<div class="ra-del"><div class="ra-del-h"><b>「${_e(d.law)}」 ${_e(raDelArt(d))}</b>${d.title?`<span class="ra-sub">${_e(d.title)}</span>`:''}<button class="ra-x" title="빼기" onclick="raDelRemove(${i})">✕</button></div><div class="ra-del-t">${_e(d.text).slice(0,600)}</div></div>`).join('');
  let pick='';
  if(_raBusy.law) pick=raSpin('법령 조문 불러오는 중...');
  else if(E.lawArts){
    const q=(E.lawQ||'').replace(/\s+/g,'');
    const arts=E.lawArts.filter(a=>!q||(a.label+a.title+a.text).replace(/\s+/g,'').includes(q)).slice(0,80);
    pick=`<div class="ra-pick"><div class="ra-pick-h">「${_e(E.lawName)}」 ${E.lawArts.length}개 조문 <input class="ra-in sm" placeholder="조문 검색(예: 위임, 정한다)" value="${_e(E.lawQ||'')}" oninput="RA.enact.lawQ=this.value;raRenderPick()"></div><div id="raPickList" class="ra-pick-l">`+
      arts.map(a=>`<label class="ra-pick-i"><input type="checkbox" ${E.dels.some(d=>d.law===E.lawName&&raDelArt(d)===a.label)?'checked':''} onchange="raDelToggle('${_a(a.label)}',this.checked)"><span><b>${_e(a.label)}</b>${a.title?`(${_e(a.title)})`:''} <em>${_e(a.text.slice(0,140))}</em></span></label>`).join('')+
      `</div></div>`;
  }
  return `<div class="ra-row"><input id="raLawName" class="ra-in" style="max-width:280px" placeholder="법령명 (예: 농촌진흥법)" value="${_e(E.lawName||'')}" onkeydown="if(event.key==='Enter')raLawLoad()"><button class="svc-btn" onclick="raLawLoad()">조문 불러오기</button><button class="svc-btn ghost" onclick="raDelManual()">직접 입력</button></div>`+
    `<div id="raPick">${pick}</div><div class="ra-dels">${list||`<div class="ra-empty sm">${raIc('upper')}선택한 위임 조항 없음 ${raTip('상위법 근거를 고르면 제1조(목적)에 반영됩니다.')}</div>`}</div>`;
}
function raRenderPick(){
  const E=RA.enact, box=document.getElementById('raPickList'); if(!box||!E.lawArts) return;
  const q=(E.lawQ||'').replace(/\s+/g,'');
  box.innerHTML=E.lawArts.filter(a=>!q||(a.label+a.title+a.text).replace(/\s+/g,'').includes(q)).slice(0,80)
    .map(a=>`<label class="ra-pick-i"><input type="checkbox" ${E.dels.some(d=>d.law===E.lawName&&raDelArt(d)===a.label)?'checked':''} onchange="raDelToggle('${_a(a.label)}',this.checked)"><span><b>${_e(a.label)}</b>${a.title?`(${_e(a.title)})`:''} <em>${_e(a.text.slice(0,140))}</em></span></label>`).join('');
}
async function raLawLoad(){
  const nm=(document.getElementById('raLawName')||{}).value||''; if(!nm.trim()){ _toast('법령명을 입력하세요.'); return; }
  const E=RA.enact; _raBusy.law=true; E.lawName=nm.trim(); raRerender('enact');
  try{
    const d=await raGet('/api/law/articles?name='+encodeURIComponent(nm.trim()));
    if(d.error||!d.articles||!d.articles.length){ E.lawArts=null; _toast(d.error||d.message||'조문을 불러오지 못했습니다.'); }
    else{ E.lawName=d.law_name||nm.trim(); E.lawArts=d.articles.map(a=>({label:a['조문표시번호']||('제'+a['조문번호']+'조'), title:a['조문제목']||'', text:String(a['조문내용']||'').trim()})); }
  }catch(e){ E.lawArts=null; _toast('법제처 연결에 실패했습니다.'); }
  _raBusy.law=false; E.lawQ=''; raRerender('enact');
}
function raDelToggle(label, on){
  const E=RA.enact; const a=(E.lawArts||[]).find(x=>x.label===label); if(!a) return;
  E.dels=E.dels.filter(d=>!(d.law===E.lawName&&raDelArt(d)===label));
  if(on) E.dels.push({law:E.lawName, art:label, title:a.title||'', text:a.text.slice(0,1500)});
  raDirty('enact');
  _raSave(); const box=document.querySelector('.ra-dels'); if(box) raRerender('enact');
}
// 위임 조항 표시: 조 번호만(예전에 저장한 “제33조(기술지원)”도 제목을 뗀다)
function raDelArt(d){ return String(d.art||'').replace(/\s*\([^)]*\)\s*$/,'').trim(); }
function raDelManual(){
  const law=prompt('상위 법령명 (예: 농촌진흥법)'); if(!law) return;
  const art=prompt('조항 (예: 제33조제2항)')||''; const text=prompt('조문 내용(요지)')||'';
  RA.enact.dels.push({law:law.replace(/[「」]/g,'').trim(), art:art.trim(), text:text.trim()}); _raSave(); raRerender('enact');
}
function raDelRemove(i){ RA.enact.dels.splice(i,1); raDirty('enact'); _raSave(); raRerender('enact'); }
function raRerender(tab){ if(RA.tab!==tab) return; const y=window.scrollY; raRender(); window.scrollTo(0,y); }

// 유사 규정
async function raFindSimilar(){
  const E=RA.enact; const q=[E.title,E.purpose,E.contents].join(' ').trim();
  if(q.length<2){ _toast('내규명·목적·주요 내용 중 하나를 입력하세요.'); return; }
  const box=document.getElementById('raSim'); if(box) box.innerHTML=raSpin('기관 내규에서 비슷한 조문을 찾는 중...');
  const d=await raPost('/api/regagent/similar',{query:q.slice(0,600), limit:8});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'검색 실패'); return; }
  E.sim={regs:d.regs, semantic:d.semantic, tokens:d.tokens}; _raSave();
  if(box) box.innerHTML=raSimView();
}
function raSimView(){
  const E=RA.enact, S=E.sim; if(!S) return '';
  if(!S.regs.length) return '<div class="ra-empty">비슷한 조문을 찾지 못했습니다. 주요 내용을 더 구체적으로 적어 보세요.</div>';
  const nref=Object.keys(E.refs||{}).length;
  return `<div class="ra-meta">검색어: ${S.tokens.map(t=>`<span class="ra-chip">${_e(t)}</span>`).join('')}${S.semantic?' <span class="ra-chip sem">의미 검색 포함</span>':''} · 참고로 고른 조문 <b id="raRefCnt">${nref}</b>개</div>`+
    S.regs.map((g,gi)=>`<div class="ra-simc"><div class="ra-simc-h"><b>${_e(g.title)}</b><span class="ra-sub">${_e(g.category)} · ${_e(g.revision)} · ${g.n_articles}개 조</span>`+
      `<a class="ra-link" href="${raRegUrl(g.slug)}" target="_blank" rel="noopener">원문↗</a><button class="ra-link" onclick="this.closest('.ra-simc').classList.toggle('toc')">조문 체계</button></div>`+
      `<div class="ra-toc">${g.toc.map(t=>_e(t)).join(' · ')}</div>`+
      g.articles.map(a=>{ const k=g.slug+'|'+a.no; return `<label class="ra-sima"><input type="checkbox" ${E.refs[k]?'checked':''} onchange="raRefToggle('${_a(g.slug)}','${_a(a.no)}',${gi},this.checked)">`+
        `<span><b>${_e(raLbl(a.no))}(${_e(a.title)})</b>${a.src.includes('sem')?' <span class="ra-chip sem">의미</span>':''}<br><em>${_e(a.body.slice(0,260))}${a.body.length>260?'…':''}</em></span></label>`; }).join('')+`</div>`).join('');
}
function raRefToggle(slug, no, gi, on){
  const E=RA.enact, g=E.sim.regs[gi], a=g.articles.find(x=>x.no===no); const k=slug+'|'+no;
  if(on) E.refs[k]={reg:g.title, no, title:a.title, body:a.body}; else delete E.refs[k];
  _raSave(); const c=document.getElementById('raRefCnt'); if(c) c.textContent=Object.keys(E.refs).length;
}

// 초안
function raEnactDraft(){ return raOnce('enactDraft', _raEnactDraft); }
async function _raEnactDraft(){
  const E=RA.enact;
  if(!(E.title||E.purpose).trim()){ _toast('내규명이나 제정 목적을 입력하세요.'); return; }
  const box=document.getElementById('raDraft'); if(box) box.innerHTML=raSpin(raHasAi()?'AI가 조문 체계와 초안을 작성하는 중... (20~40초)':'표준 조문 골격을 만드는 중...');
  const gen=_raGen.enact;
  const d=await raPost('/api/regagent/draft',{mode:'enact', title:E.title, category:E.category, dept:E.dept, effective:E.effective,
    purpose:E.purpose, contents:E.contents, delegations:E.dels, refs:Object.values(E.refs||{}), ...raAi()});
  if(gen!==_raGen.enact||E!==RA.enact) return;          // 그사이 새로 시작함
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'초안 작성 실패', d.need_key); return; }
  const r=d.draft;
  if(E.draft&&String(E.draft.text||'').trim()&&!confirm('지금 조문 초안을 새 초안으로 바꿀까요? (직접 고친 내용은 사라집니다)')){ raRerender('enact'); return; }
  if(r.title && !E.title) E.title=r.title;
  E.draft={text:raDraftText(r.articles), addenda:(r.addenda||[]).join('\n'), purpose:(r.reason||{}).purpose||'', main:((r.reason||{}).main||[]).join('\n'),
    notes:r.notes||[], model:r.model||'', template:!!r.template, notice:d.notice||'', basis:raBasis('enact')};
  E.lint=null; E.review=null; E.nota=null; _raSave(); raRerender('enact');
  setTimeout(()=>{ const s=document.getElementById('raSecDraft'); if(s) s.scrollIntoView({behavior:'smooth',block:'start'}); },60);
  raLint('enact', true);
}
function raEnactDraftView(){
  const D=RA.enact.draft; if(!D) return '';
  return (D.notice?`<div class="ra-note ra-note-i">${raIc('info')}<span>${_e(D.notice)}</span></div>`:'')+(D.model?`<div class="ra-meta"><span class="ra-chip sem">${raIc('spark')}${_e(D.model)}</span>${raTip('AI 초안은 반드시 검토 후 사용하세요.')}</div>`:'')+
    raDraftMap(D.text)+`<label class="ra-f"><span>조문 ${raTip('“제N조(제목) 본문” 형식 유지 · 항은 줄을 바꿔 ①②, 호는 1. 2.')}</span><textarea class="ra-ta mono" rows="${Math.min(20,Math.max(6,String(D.text||'').split('\n').length+1))}" oninput="raSet('enact.draft.text',this.value)">${_e(D.text)}</textarea></label>`+
    `<div class="ra-row">${raClausePick('enact')}${raTip('위원회·비밀 유지·세부사항 위임 등 자주 쓰는 조문을 끝에 덧붙입니다. ○○ 자리를 채우세요.')}</div>`+
    `<label class="ra-f"><span>부칙</span><textarea class="ra-ta mono" rows="${Math.min(8,Math.max(2,String(D.addenda||'').split('\n').length))}" oninput="raSet('enact.draft.addenda',this.value)">${_e(D.addenda)}</textarea></label>`+raAbView('enact')+
    `<div class="ra-grid2"><label class="ra-f"><span>제정 이유</span><textarea class="ra-ta" rows="3" oninput="raSet('enact.draft.purpose',this.value)">${_e(D.purpose)}</textarea></label>`+
    `<label class="ra-f"><span>주요 내용 ${raTip('한 줄에 하나')}</span><textarea class="ra-ta" rows="3" oninput="raSet('enact.draft.main',this.value)">${_e(D.main)}</textarea></label></div>`+
    (D.notes&&D.notes.length?`<div class="ra-note"><b>입안 시 확인할 점</b><ul>${D.notes.map(n=>`<li>${_e(n)}</li>`).join('')}</ul></div>`:'')+
    '';
}

// 조문 구성도 — 장별로 조 번호·제목을 타일로 보여 준다(마우스를 올리면 조문 미리보기)
function raDraftMap(text){
  const p=raParse(text); if(!p.articles.length) return '';
  const groups=[]; p.articles.forEach(a=>{ const c=a.chapter||''; let g=groups[groups.length-1]; if(!g||g.c!==c){ g={c,arts:[]}; groups.push(g); } g.arts.push(a); });
  const nh=p.articles.reduce((s,a)=>s+((String(a.body).match(/[①-⑳]/g)||[]).length||1),0);
  return `<div class="ra-map"><div class="ra-map-s"><span><b>${p.articles.length}</b>개 조</span>${p.chapters.length?`<span><b>${p.chapters.length}</b>개 장</span>`:''}<span><b>${nh}</b>개 항</span></div>`+
    groups.map(g=>`<div class="ra-map-g">${g.c?`<div class="ra-map-c">${_e(g.c)}</div>`:''}<div class="ra-map-a">`+
      g.arts.map(a=>`<span class="ra-map-i${a.deleted?' del':''}" title="${_e(raArtText(a).slice(0,240))}"><b>${_e(raLbl(a.no).replace(/^제|조/g,''))}</b>${_e(a.title||'삭제')}</span>`).join('')+`</div></div>`).join('')+`</div>`;
}

// ── 점검 ────────────────────────────────────────────────────────────────────
async function raLint(mode, silent){
  const box=document.getElementById('raLint');
  let body;
  if(mode==='enact'){ const D=RA.enact.draft; if(!D) return; body={text:D.text, addenda:raDocCtx('enact').addenda, title:RA.enact.title}; }
  else { const t=raAmendFullText(); if(!t){ _toast('먼저 내규를 불러오세요.'); return; } body={text:t.text, addenda:raDocCtx('amend').addenda, title:RA.amend.title}; }
  if(box && !silent) box.innerHTML=raSpin('점검 중...');
  const gen=_raGen[mode], S=RA[mode];
  const d=await raPost('/api/regagent/lint', body);
  if(gen!==_raGen[mode]||S!==RA[mode]) return;
  S.lint=d.success?d.issues:null; _raSave();
  if(box) box.innerHTML=d.success?raLintView(d.issues):raErr(d.error||'점검 실패');
}
function raLintView(iss, onlyNos, compact){
  if(!iss) return '';
  let list=iss; if(onlyNos) list=iss.filter(i=>!i.no||onlyNos.has(i.no));
  if(!list.length) return `<div class="ra-ok">${raIc('check')}발견된 문제 없음</div>`;
  const cnt=l=>list.filter(i=>i.level===l).length;
  const ic={error:raIc('bad'),warn:raIc('alert'),info:raIc('tip')};
  return (compact?'':raStack([{n:cnt('error'),l:'오류',tone:'bad'},{n:cnt('warn'),l:'주의',tone:'warn'},{n:cnt('info'),l:'표기 제안',tone:'acc'}],'점검 결과'))+`<ul class="ra-lint">`+
    list.map(i=>`<li class="lv-${i.level}"><span>${ic[i.level]||''}</span><span>${_e(i.msg)}${i.fix?` <em class="ra-fix">${_e(i.fix)}</em>`:''}</span></li>`).join('')+`</ul>`;
}

// ══════════════════════════════════════════════════════════════════════════
// 개정
// ══════════════════════════════════════════════════════════════════════════
function raAmendView(){
  const A=RA.amend;
  const src=`<div class="ra-seg" style="margin-bottom:10px"><button class="${A.src!=='paste'?'on':''}" onclick="raAmendSrc('reg')">등록된 ${_e(RA_ORG.reg_word)}에서 고르기</button><button class="${A.src==='paste'?'on':''}" onclick="raAmendSrc('paste')">원문 붙여넣기</button></div>`;
  const s1=src+(A.src==='paste'
    ?`<label class="ra-f"><span>${_e(RA_ORG.reg_word)}명</span><input class="ra-in" id="raPasteTitle" value="${_e(A.title)}" placeholder="예) ○○ 운영규칙" oninput="raSet('amend.title',this.value)"></label>`+
      `<label class="ra-f"><span>현행 원문 ${raTip(`“제1조(목적) …” 형식 그대로 붙여 넣으세요. 등록되지 않은 ${RA_ORG.reg_word}나 다른 기관 규정도 됩니다.`)}</span><textarea class="ra-ta mono" id="raPasteText" rows="8" oninput="raSet('amend.pasteText',this.value)">${_e(A.pasteText)}</textarea></label>`+
      `<div class="ra-row"><button class="svc-btn" onclick="raPasteLoad()">조문 읽기</button></div><div id="raArts">${A.pasted?raArtsView():''}</div>`
    :`<div class="ra-row"><input id="raRegIn" class="ra-in" list="raRegList" style="max-width:340px" placeholder="${_e(RA_ORG.reg_word)}명 (예: 여비규정)" value="${_e(A.title)}" onkeydown="if(event.key==='Enter')raPickReg()"><datalist id="raRegList"></datalist>`+
      `<button class="svc-btn" onclick="raPickReg()">불러오기</button>${A.slug?`<a class="ra-link" href="${raRegUrl(A.slug)}" target="_blank" rel="noopener">원문↗</a>`:''}</div><div id="raArts">${raArtsView()}</div>`);
  const s2=`<div class="ra-grid2"><label class="ra-f"><span>개정 의도</span>${raTa('amend.intent',A.intent,'예) 숙박비 상한을 실비 기준으로 바꾸고, 출장 신청을 전자결재로 하도록 정비',5)}</label>`+
    `<div><label class="ra-f"><span>시행일</span>${raIn('amend.effective',A.effective,'비우면 “발령한 날”')}</label>`+
    `<label class="ra-f"><span>참고 자료 ${raTip('상위법 개정 내용 등(선택)')}</span>${raTa('amend.refText',A.refText,'예) 「공무원 여비 규정」 별표 개정(2026.1.1.)',2)}</label></div></div>`+
    `<div class="ra-row"><button class="svc-btn ${raHasAi()?'yes':''}" onclick="raAmendDraft()">${raIc('spark')}${raHasAi()?'수정안 작성':'AI 수정안(키 필요)'}</button><button class="svc-btn ${raHasAi()?'':'yes'}" onclick="raAmendManual()">선택 조문 직접 고치기</button><button class="svc-btn ghost" onclick="raAddInsert()">＋ 조문 신설</button>${raClausePick('amend')}`+
    `${raTip(`${raHasAi()?'체크한 조문(없으면 AI가 목차를 보고 고름)에 개정 의도를 반영합니다.':'AI 키가 없으면 체크한 조문을 직접 고쳐 쓰세요.'}`)}</div>`+
    `<details class="ra-det"${A.alioOpen?' open':''} ontoggle="RA.amend.alioOpen=this.open;_raSave();if(this.open&&!document.getElementById('raAlio'))this.querySelector('.ra-det-b').innerHTML=raAlioView('amend')"><summary>${raIc('bulk')}다른 기관 사규 참고(알리오) · 고른 조문 <b id="raAlioCnt">${Object.keys(A.alioRefs||{}).length}</b>개 ${raTip('같은 종류 규정을 다른 공공기관은 어떻게 정했는지 보고, 고른 조문을 AI 수정안 작성 때 참고합니다.')}</summary><div class="ra-det-b">${A.alioOpen?raAlioView('amend'):''}</div></details>`;
  const s3=`<div id="raChanges">${raChangesView()}</div>`;
  const nSel=Object.keys(A.sel||{}).length;
  const body=[
    ()=>s1+(_raArts?`<p class="ra-wiz-hint" id="raSelHint">${raSelHint()}</p>`:''),
    ()=>s2+raStaleNote('amend')+`<div id="raSecChg">${s3}</div>`,
    ()=>raRunBar('amend')+raSub(`신구조문대비표 <span class="ra-leg"><u class="ra-d">삭제</u><u class="ra-i">추가</u></span>`,`<label class="ra-chk"><input type="checkbox" ${A.abbr?'checked':''} onchange="raSet('amend.abbr',this.checked);raRefreshCmp()"> 바뀌지 않은 항·호는 “(현행과 같음)”으로 줄이기</label><div id="raCmp">${raCmpView()}</div>`)+
      raPair(raSub('인용 영향',`<div class="ra-row"><button class="svc-btn" onclick="raImpact()">${raIc('search')}영향 범위 찾기</button>${raTip(`조 번호를 옮기는 경우 이동표(예: 7→8)를 넣으면 고칠 인용 표기를 함께 보여 줍니다.`)}<input id="raMoves" class="ra-in sm" style="max-width:180px" placeholder="이동표 예: 7→8, 9→10" value="${_e(A.moves||'')}" oninput="raSet('amend.moves',this.value)"></div><div id="raImpact">${raImpactView()}</div>`),
        raSub('형식 점검',`<div class="ra-row"><button class="svc-btn" onclick="raLint('amend')">${raIc('check')}점검 실행</button><label class="ra-chk"><input type="checkbox" id="raLintOnly" checked onchange="raLintRedraw()"> 고친 조문 관련만 보기</label></div><div id="raLint">${raLintView(A.lint, raLintOnlySet())}</div>`))+
      raSub('심의 사전검토',raReviewSec('amend')),
    ()=>`<div id="raSecDocs">${raDocsView('amend')}</div>`,
  ];
  return raWiz('amend', body);
}
function raLintOnlySet(){ const el=document.getElementById('raLintOnly'); if(el&&!el.checked) return null; return new Set(RA.amend.changes.map(c=>c.no)); }
function raLintRedraw(){ const b=document.getElementById('raLint'); if(b) b.innerHTML=raLintView(RA.amend.lint, raLintOnlySet()); }
function raAmendWorkMsg(){ const A=RA.amend, n=raEffChanges().length; return n||String(A.intent||'').trim()?`지금 개정 작업(${n?`수정안 ${n}건`:'개정 의도'})을 지우고 다른 ${RA_ORG.reg_word}로 새로 시작할까요?`:''; }
function raAmendSrc(v){ const A=RA.amend; if(A.src===v) return; const m=raAmendWorkMsg(); if(m&&!confirm(m)){ raRerender('amend'); return; } raGenBump('amend'); A.src=v; if(v==='reg'){ A.pasted=false; } else { A.slug=''; } _raArts=null; Object.assign(A,{title:'',sel:{},changes:[],impact:null,lint:null,review:null,nota:null,moves:'',ab:null}); _raSave(); raRerender('amend'); }
async function raPasteLoad(restore){
  const A=RA.amend; const t=restore?A.pasteText:((document.getElementById('raPasteText')||{}).value||A.pasteText);
  if(!t.trim()){ _toast('원문을 붙여 넣으세요.'); return; }
  if(restore){ if(_raBusy.paste) return; _raBusy.paste=true; }
  let d; try{ d=await raPost('/api/regagent/parse',{text:t, clean:true}); } finally{ _raBusy.paste=false; }
  if(!d.success||!(d.articles||[]).length){ _toast('“제1조(목적)” 형식의 조문을 찾지 못했습니다.'); return; }
  if(restore){                                            // 새로고침 후 복원: 작업 내용은 그대로 둔다
    if(!A.pasted||(A.pasteLoaded||A.pasteText)!==t) return;
    _raArts={title:A.title, revision:'붙여넣은 원문', articles:d.articles, pasted:true}; raRerender('amend'); return;
  }
  const same=A.pasted&&A.pasteLoaded===t;
  A.pasteText=t; A.pasteLoaded=t;
  const ttl=((document.getElementById('raPasteTitle')||{}).value||'').trim();
  if(!same) A.title=ttl&&ttl!==A.title?ttl:((d.preamble||'').split('\n')[0].trim().slice(0,40)||ttl||'붙여넣은 규정');
  _raArts={title:A.title, revision:'붙여넣은 원문', articles:d.articles, pasted:true};
  if(!same){ raGenBump('amend'); Object.assign(A,{pasted:true,slug:'',sel:{},changes:[],impact:null,lint:null,review:null,nota:null,moves:'',purpose:'',main:[],addenda:'',notes:[],ab:null}); }
  _raSave(); raRerender('amend');
}
function raRegPayload(){ const A=RA.amend; return A.pasted?{text:A.pasteLoaded||A.pasteText, reg:A.title}:{slug:A.slug, reg:A.title}; }
async function raPickReg(){
  const v=((document.getElementById('raRegIn')||{}).value||'').trim(); if(!v){ _toast('내규명을 입력하세요.'); return; }
  const regs=await raCatalog(); const nk=s=>s.replace(/[\s·_]/g,'');
  const r=regs.find(x=>nk(x.title)===nk(v))||regs.find(x=>nk(x.title).includes(nk(v)));
  if(!r){ _toast('내규를 찾지 못했습니다. 목록에서 골라 주세요.'); return; }
  if(RA.amend.slug!==r.slug){ const m=raAmendWorkMsg(); if(m&&!confirm(m)) return; raGenBump('amend'); Object.assign(RA.amend,{step:0,basis:'',src:'reg',pasted:false,slug:r.slug,title:r.title,sel:{},changes:[],impact:null,lint:null,review:null,nota:null,moves:'',ab:null,purpose:'',main:[],addenda:'',notes:[]}); }
  _raArts=null; _raSave(); raLoadArts(r.slug);
}
async function raLoadArts(slug, quiet){
  const box=document.getElementById('raArts'); if(box && !quiet) box.innerHTML=raSpin('조문 불러오는 중...');
  _raBusy.arts=true; let d;
  try{ d=await raGet('/api/regagent/articles?slug='+encodeURIComponent(slug)); } finally{ _raBusy.arts=false; }
  if(RA.amend.slug!==slug) return;                        // 그사이 다른 내규를 고름
  if(!d.success){ _raArtsErr=d.error||'불러오기 실패'; if(box) box.innerHTML=raErr(_raArtsErr); const c=document.getElementById('raChanges'); if(c) c.innerHTML=raChangesView(); return; }
  _raArtsErr=''; _raArts=d; RA.amend.title=d.title; _raSave(); raRerender('amend');
}
function raArtsView(){
  const A=RA.amend;
  if(!A.slug && !A.pasted) return `<div class="ra-empty sm">${raIc('search')}개정할 내규를 고르세요 ${raTip('「상위법 영향」·「건강검진」·「전체 점검」 결과에서 바로 넘어올 수도 있습니다.')}</div>`;
  if(!_raArts){ if(A.pasted && A.pasteText) setTimeout(()=>raPasteLoad(true),0); return raSpin('조문 불러오는 중...'); }
  const q=(A.filter||'').replace(/\s+/g,'');
  let chap='', html='';
  _raArts.articles.forEach(a=>{
    if(q && !(a.no+a.title+a.body).replace(/\s+/g,'').includes(q)) return;
    if(a.chapter&&a.chapter!==chap){ chap=a.chapter; html+=`<div class="ra-chap">${_e(chap)}</div>`; }
    html+=`<label class="ra-art${a.deleted?' del':''}"><input type="checkbox" ${A.sel[a.no]?'checked':''} ${a.deleted?'disabled':''} onchange="raSel('${_a(a.no)}',this.checked)">`+
      `<span class="ra-art-n">${_e(raLbl(a.no))}</span><span class="ra-art-t">${a.deleted?'삭제':_e(a.title)}</span><span class="ra-art-b">${_e(a.body.replace(/\n/g,' ').slice(0,90))}</span></label>`;
  });
  const nsel=Object.values(A.sel).filter(Boolean).length;
  return `<div class="ra-meta">「${_e(_raArts.title)}」 ${_e(_raArts.revision||'')} · ${_raArts.articles.length}개 조 · 선택 <b id="raSelCnt">${nsel}</b>개 <input class="ra-in sm" style="max-width:200px" placeholder="조문 검색" value="${_e(A.filter||'')}" oninput="RA.amend.filter=this.value;document.getElementById('raArtList').innerHTML=raArtsList()"></div><div class="ra-arts" id="raArtList">${html}</div>`;
}
function raArtsList(){ const t=document.createElement('div'); t.innerHTML=raArtsView(); const l=t.querySelector('#raArtList'); return l?l.innerHTML:''; }
function raSel(no,on){ if(on) RA.amend.sel[no]=true; else delete RA.amend.sel[no]; _raSave(); const c=document.getElementById('raSelCnt'); if(c) c.textContent=Object.keys(RA.amend.sel).length; raWizSync('amend'); }
function raSelHint(){ const n=Object.keys(RA.amend.sel||{}).length; return `${raIc('info')}${n?`조문 <b>${n}</b>개를 골랐습니다. “다음”을 눌러 고치세요.`:'고칠 조문을 체크하세요. 신설만 하거나 AI에게 맡기려면 체크하지 않아도 됩니다.'}`; }
function raOld(no){ return _raArts?_raArts.articles.find(a=>a.no===no):null; }
// 실제로 바뀐 수정안인지(체크만 하고 고치지 않은 조문은 개정문·대비표·이유서·규모에서 뺀다)
function raChanged(c){
  if(c.type!=='modify') return true;
  const o=raOld(c.no); if(!o||o.deleted) return true;
  const n=x=>String(x||'').replace(/\s+/g,' ').trim();
  return n(o.title)!==n(c.title)||n(o.body)!==n(c.body);
}
function raEffChanges(){ return RA.amend.changes.filter(raChanged); }
function raAmendDraft(){ return raOnce('amendDraft', _raAmendDraft); }
async function _raAmendDraft(){
  const A=RA.amend; if(!_raArts){ _toast('먼저 내규를 불러오세요.'); return; }
  if(!A.intent.trim()){ _toast('개정 의도를 입력하세요.'); return; }
  if(!raHasAi()){ _toast('AI 키가 없습니다. [✦ AI 설정]에서 키를 넣거나 “선택 조문 직접 고치기”를 쓰세요.'); return; }
  const box=document.getElementById('raChanges'); if(box) box.innerHTML=raSpin('AI가 수정안을 작성하는 중... (20~40초)');
  const targets=Object.keys(A.sel).map(no=>raOld(no)).filter(Boolean).map(a=>({no:a.no,title:a.title,body:a.body}));
  const dels=A.refText.trim()?[{law:'참고',art:'',text:A.refText}]:[];
  const gen=_raGen.amend;
  const d=await raPost('/api/regagent/draft',{mode:'amend', ...raRegPayload(), intent:A.intent, effective:A.effective, targets, delegations:dels, refs:Object.values(A.alioRefs||{}), ...raAi()});
  if(gen!==_raGen.amend||A!==RA.amend) return;            // 그사이 다른 내규로 바꿈
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'수정안 작성 실패', d.need_key); return; }
  const r=d.draft;
  if(A.changes.some(raChanged)&&!confirm('지금 수정안을 AI 수정안으로 바꿀까요? (직접 고친 내용은 사라집니다)')){ raRerender('amend'); return; }
  A.changes=r.changes.map(c=>{ const o=raOld(c.no), live=o&&!o.deleted;     // AI가 고른 유형을 현행과 맞춘다
    const type=c.type==='insert'&&live?'modify':c.type!=='insert'&&!live?'insert':c.type;
    return {type,no:c.no,title:c.title,body:c.body,why:c.why}; }).filter(c=>!(c.type==='delete'&&!raOld(c.no)));
  A.purpose=(r.reason||{}).purpose||''; A.main=(r.reason||{}).main||[]; A.addenda=(r.addenda||[]).join('\n'); A.notes=r.notes||[]; A.model=r.model||'';
  A.basis=raBasis('amend'); A.impact=null; A.lint=null; A.review=null; A.nota=null; _raSave(); raRerender('amend');
  setTimeout(()=>{ const s=document.getElementById('raSecChg'); if(s) s.scrollIntoView({behavior:'smooth',block:'start'}); },60);
  raLint('amend', true);
}
function raAmendManual(){
  const A=RA.amend; if(!_raArts){ _toast('먼저 내규를 불러오세요.'); return; }
  const nos=Object.keys(A.sel).sort(raCmp); if(!nos.length){ _toast('고칠 조문을 체크하세요.'); return; }
  nos.forEach(no=>{ if(A.changes.some(c=>c.no===no)) return; const o=raOld(no); if(!o){ delete A.sel[no]; return; } A.changes.push({type:'modify',no,title:o.title,body:o.body,why:''}); });
  A.changes.sort((x,y)=>raCmp(x.no,y.no)); _raSave(); raRerender('amend');
}
function raAddInsert(){
  const A=RA.amend; if(!_raArts){ _toast('먼저 내규를 불러오세요.'); return; }
  const after=prompt('어느 조 다음에 신설할까요? (예: 7 → 제7조의2로 신설)'); if(!after) return;
  const base=raKey(raNormNo(after)); if(!base[0]){ _toast('조 번호를 숫자로 입력하세요.'); return; }
  const used=new Set([..._raArts.articles.map(a=>a.no),...A.changes.map(c=>c.no)]);
  let k=Math.max(2, base[1]+1), no=`${base[0]}의${k}`; while(used.has(no)){ k++; no=`${base[0]}의${k}`; }
  A.changes.push({type:'insert',no,title:'',body:'',why:''}); A.changes.sort((x,y)=>raCmp(x.no,y.no)); raDirty('amend', true); _raSave(); raRerender('amend');
}
function raChangesView(){
  const A=RA.amend;
  if(A.changes.length&&!_raArts&&!A.pasted&&_raArtsErr) return raErr(`현행 조문을 불러오지 못해(${_raArtsErr}) 수정안을 현행과 비교할 수 없습니다. 내규를 다시 불러오세요.`);
  if(!A.changes.length) return `<div class="ra-empty sm">${raIc('amend')}수정안 없음 ${raTip('위에서 “수정안 작성” 또는 “선택 조문 직접 고치기”를 누르세요.')}</div>`;
  const tl={modify:'개정',insert:'신설',delete:'삭제'};
  const nt=k=>A.changes.filter(c=>c.type===k).length;
  const sc=raAmendScale();
  return raStack([{n:nt('modify'),l:'개정',tone:'acc'},{n:nt('insert'),l:'신설',tone:'ok'},{n:nt('delete'),l:'삭제',tone:'bad'}],'수정안 구성')+
    `<div class="ra-scale"><span class="ra-scale-m">${raIc('amend')}개정 규모 <b>${sc.n}</b>/${sc.total}개 조 <i class="ra-scale-b"><i style="width:${Math.min(100,Math.round(sc.ratio*100))}%"></i></i> ${Math.round(sc.ratio*100)}%</span>`+
    `<span class="ra-seg sm"><button class="${A.lawStyle!=='art'?'on':''}" onclick="raSet('amend.lawStyle','fine');raRerender('amend')">바뀐 부분만</button><button class="${A.lawStyle==='art'?'on':''}" onclick="raSet('amend.lawStyle','art');raRerender('amend')">조 단위</button></span>${raTip('개정문 문형. “바뀐 부분만”은 “제5조제2항 중 “A”를 “B”로 한다.”처럼 바뀐 곳만 짚고, 고친 곳이 많은 조는 조 전체를 씁니다.')}`+
    `<label class="ra-chk"><input type="checkbox" ${A.fullRev?'checked':''} onchange="raSet('amend.fullRev',this.checked);raRerender('amend')"> 전부개정으로 쓰기</label>`+
    (sc.full&&!A.fullRev?`<span class="ra-chip warn">${raIc('info')}고친 조가 절반 이상입니다. 전부개정을 검토하세요</span>`:'')+`</div>`+
    (A.model?`<div class="ra-meta"><span class="ra-chip sem">${raIc('spark')}${_e(A.model)}</span>${raTip('AI 수정안은 반드시 검토 후 사용하세요.')}</div>`:'')+A.changes.map((c,i)=>{
    const o=raOld(c.no);
    return `<div class="ra-chg t-${c.type}"><div class="ra-chg-h"><select class="ra-in sm" onchange="raChg(${i},'type',this.value)">${Object.entries(tl).map(([k,v])=>`<option value="${k}"${c.type===k?' selected':''}>${v}</option>`).join('')}</select>`+
      `<b>${_e(raLbl(c.no))}</b><input class="ra-in sm" style="max-width:220px" placeholder="조 제목" value="${_e(c.title)}" oninput="raChg(${i},'title',this.value,1)" ${c.type==='delete'?'disabled':''}>`+
      (c.why?`<span class="ra-sub">${_e(c.why)}</span>`:'')+`<span class="ra-chip warn" id="raNc${i}"${raChanged(c)?' hidden':''}>변경 없음</span>`+`<button class="ra-x" title="이 수정안 빼기" onclick="raChgDel(${i})">✕</button></div>`+`<div id="raSen${i}">${raSenPreview(c)}</div>`+
      `<div class="ra-chg-b"><div class="ra-old"><div class="ra-lab">현행</div>${o?_e(raArtText(o)).replace(/\n/g,'<br>'):'<span class="ra-mu">&lt;신 설&gt;</span>'}</div>`+
      `<div class="ra-new"><div class="ra-lab">개정안</div>${c.type==='delete'?'<span class="ra-mu">이 조를 삭제합니다(번호는 남기고 “삭제” 표시).</span>':`<textarea class="ra-ta mono" rows="${Math.min(14,Math.max(4,(c.body||'').split('\n').length+1))}" oninput="raChg(${i},'body',this.value,1)">${_e(c.body)}</textarea>`}</div></div></div>`;
  }).join('')+
  `<div class="ra-grid2" style="margin-top:12px"><label class="ra-f"><span>개정 이유</span><textarea class="ra-ta" rows="3" oninput="raSet('amend.purpose',this.value)">${_e(A.purpose)}</textarea></label>`+
  `<label class="ra-f"><span>주요 내용 ${raTip('한 줄에 하나')}</span><textarea class="ra-ta" rows="3" oninput="RA.amend.main=this.value.split('\\n');_raSave()">${_e((A.main||[]).join('\n'))}</textarea></label></div>`+
  `<label class="ra-f"><span>부칙</span><textarea class="ra-ta mono" rows="${Math.min(8,Math.max(2,String(A.addenda||'').split('\n').length))}" placeholder="비우면 “이 ${_e(raKind(A.title))}${raJosa(raKind(A.title))} 발령한 날부터 시행한다.”" oninput="raSet('amend.addenda',this.value)">${_e(A.addenda)}</textarea></label>`+raAbView('amend')+
  (A.notes&&A.notes.length?`<div class="ra-note"><b>함께 확인할 점</b><ul>${A.notes.map(n=>`<li>${_e(n)}</li>`).join('')}</ul></div>`:'')+
  `<div class="ra-row"><button class="svc-btn" onclick="raRerender('amend')">대비표·문서 새로고침</button></div>`;
}
function raChg(i,k,v,soft){ const c=RA.amend.changes[i]; if(!c) return;
  if(k==='type'){ const o=raOld(c.no);
    if(v==='insert'&&o&&!o.deleted){ _toast(`${raLbl(c.no)}${raJosa(raLbl(c.no),['은','는'])} 이미 있는 조입니다. 신설은 “＋ 조문 신설”로 새 번호(제N조의2)를 쓰세요.`); raRerender('amend'); return; }
    if(v!=='insert'&&(!o||o.deleted)&&_raArts){ _toast(`${raLbl(c.no)}${raJosa(raLbl(c.no),['은','는'])} 현행에 없는 조라 신설로 둡니다.`); raRerender('amend'); return; }
    if(v!=='delete'&&c.type==='delete'&&!c.body&&o){ c.title=o.title; c.body=o.body; }
  }
  c[k]=v; raDirty('amend', k==='type'); _raSave(); if(!soft) raRerender('amend'); else raRefreshCmp(); }
function raChgDel(i){ RA.amend.changes.splice(i,1); raDirty('amend', true); _raSave(); raRerender('amend'); }
let _raCmpT=null;
function raRefreshCmp(){ clearTimeout(_raCmpT); _raCmpT=setTimeout(()=>{ const b=document.getElementById('raCmp'); if(b) b.innerHTML=raCmpView();
  RA.amend.changes.forEach((c,i)=>{ const e=document.getElementById('raSen'+i); if(e) e.innerHTML=raSenPreview(c); const n=document.getElementById('raNc'+i); if(n) n.hidden=raChanged(c); }); raWizSync('amend'); },250); }
function raCmpRows(){
  const A=RA.amend;
  return raEffChanges().sort((x,y)=>raCmp(x.no,y.no)).map(c=>{
    const o=c.type==='insert'?null:raOld(c.no);
    const n=c.type==='delete'?{type:'delete',no:c.no}:{no:c.no,title:c.title,body:c.body};
    return raCmpCell(o, n, A.abbr);
  });
}
function raCmpView(){
  const rows=raCmpRows();
  if(!rows.length) return '';
  return `<table class="ra-cmp"><thead><tr><th>현 행</th><th>개 정 안</th></tr></thead><tbody>`+rows.map(r=>`<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('')+`</tbody></table>`;
}
// 개정 반영 전체 조문(점검용)
function raAmendFullText(){
  if(!_raArts) return null; const A=RA.amend;
  const map=new Map(_raArts.articles.map(a=>[a.no,{...a}]));
  A.changes.forEach(c=>{ if(c.type==='delete') map.set(c.no,{no:c.no,title:'',body:'',deleted:true,chapter:(map.get(c.no)||{}).chapter||''});
    else map.set(c.no,{no:c.no,title:c.title,body:c.body,chapter:(map.get(c.no)||{}).chapter||''}); });
  const arts=[...map.values()].sort((x,y)=>raCmp(x.no,y.no));
  return {text:arts.map(raArtText).join('\n'), addenda:A.addenda||'시행한다', arts};
}

// 영향 분석
async function raImpact(){
  const A=RA.amend; if(!A.changes.length) return;
  const mvText=((document.getElementById('raMoves')||{}).value||'').trim(), moves={};
  mvText.split(/[,，;\n]+/).forEach(p=>{ const m=p.split(/→|->|=>|>/); if(m.length===2){ const a=raNormNo(m[0]), b=raNormNo(m[1]); if(a&&b) moves[a]=b; } });
  if(mvText&&!Object.keys(moves).length){ _toast('이동표를 읽지 못했습니다. 예) 7→8, 제9조→제10조'); return; }
  const nos=A.changes.filter(c=>c.type!=='insert').map(c=>c.no);
  const box=document.getElementById('raImpact'); if(box) box.innerHTML=raSpin('인용 조문을 찾는 중...');
  const gen=_raGen.amend;
  const d=await raPost('/api/regagent/impact',{...raRegPayload(), nos, moves});
  if(gen!==_raGen.amend||A!==RA.amend) return;
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'분석 실패'); return; }
  A.impact=d; _raSave(); if(box) box.innerHTML=raImpactView();
}
function raImpactView(){
  const I=RA.amend.impact; if(!I) return '';
  const s=I.summary;
  const hit=(h)=>`<li><b>${_e(raLbl(h.no))}${h.title?`(${_e(h.title)})`:''}</b> — “${_e(h.text)}”${h.suggest?` <em class="ra-fix">${_e(h.suggest)}</em>`:''}<div class="ra-snip">${_e(h.snippet)}</div></li>`;
  const tn=n=>n?'warn':'ok';
  let html=raStats([{v:s.inner,l:'같은 내규 안 인용',ic:'doc',tone:tn(s.inner)},{v:s.appendix,l:'별표·서식',ic:'doc',tone:tn(s.appendix)},
    {v:s.outer,l:'다른 내규의 조문 인용',ic:'bulk',tone:tn(s.outer)},{v:s.mention_regs,l:'내규명 인용(개 내규)',ic:'search',tone:s.mention_regs?'acc':'ok',tip:'명칭을 바꾸거나 폐지할 때 확인'}]);
  if(!s.inner&&!s.appendix&&!s.outer) html+=`<div class="ra-ok">${raIc('check')}고친 조문을 직접 인용하는 곳 없음</div>`;
  if(I.inner.length) html+=`<div class="ra-ih">「${_e(I.reg)}」 안에서 인용</div><ul class="ra-hits">${I.inner.map(hit).join('')}</ul>`;
  if(I.appendix.length) html+=`<div class="ra-ih">별표·서식의 관련 조문 표기</div><ul class="ra-hits">${I.appendix.map(x=>`<li>${_e(x.form)} — ${_e(raLbl(x.cites))} 관련</li>`).join('')}</ul>`;
  I.outer.forEach(o=>{ html+=`<div class="ra-ih">「${_e(o.reg)}」 <a class="ra-link" href="${raRegUrl(o.slug)}" target="_blank" rel="noopener">원문↗</a></div><ul class="ra-hits">${o.hits.map(hit).join('')}</ul>`; });
  if(I.mentions.length) html+=`<details class="ra-det"><summary>내규명을 인용하는 다른 내규 ${I.mentions.length}개 (명칭을 바꾸거나 폐지할 때 확인)</summary><ul class="ra-hits">${I.mentions.map(m=>`<li><b>「${_e(m.reg)}」</b> ${m.count}곳 — ${m.hits.slice(0,3).map(h=>_e(raLbl(h.no))).join(', ')}</li>`).join('')}</ul></details>`;
  if(I.children&&I.children.length) html+=`<div class="ra-note">하위 내규도 함께 검토하세요: ${I.children.map(c=>'「'+_e(c)+'」').join(', ')}</div>`;
  if(I.fixes&&I.fixes.length) html+=`<div class="ra-fixbox"><div class="ra-ih">인용 정정안 ${I.fixes.length}개 조문 — 이동표대로 같은 ${_e(RA_ORG.reg_word)} 안의 조 번호 인용을 고쳤습니다(다른 법령·내규 인용은 그대로)</div>`+
    I.fixes.map(f=>{ const [o,n]=raWordDiff(f.old_body,f.new_body); return `<div class="ra-fixrow"><b>${_e(raLbl(f.no))}(${_e(f.title)})</b> ${f.count}곳<div class="ra-fixd"><div>${o.replace(/\n/g,'<br>')}</div><div>${n.replace(/\n/g,'<br>')}</div></div></div>`; }).join('')+
    `<button class="svc-btn yes" onclick="raApplyFixes()">수정안에 반영</button></div>`;
  return html;
}

function raApplyFixes(){
  const A=RA.amend, I=A.impact; if(!I||!I.fixes) return;
  let add=0, skip=[];
  I.fixes.forEach(f=>{ const c=A.changes.find(x=>x.no===f.no);
    if(!c){ A.changes.push({type:'modify',no:f.no,title:f.title,body:f.new_body,why:'조 번호 이동에 따른 인용 정정'}); add++; }
    else if(c.type==='modify' && c.body===f.old_body){ c.body=f.new_body; add++; }
    else skip.push(raLbl(f.no)); });
  A.changes.sort((x,y)=>raCmp(x.no,y.no)); raDirty('amend'); _raSave(); raRerender('amend');
  _toast(`인용 정정 ${add}개 조문을 수정안에 넣었습니다.`+(skip.length?` 이미 고친 ${skip.join(', ')}는 직접 확인하세요.`:''), 5000);
}

// ══════════════════════════════════════════════════════════════════════════
// 심의 사전검토 — 기관 심의기준(org_config.json review_criteria)
// ══════════════════════════════════════════════════════════════════════════
function raReviewPayload(mode){
  if(mode==='enact'){ const E=RA.enact, D=E.draft||{};
    return {mode, alio_refs:raAlioRefList('enact'), title:E.title, text:D.text||'', addenda:raDocCtx('enact').addenda, purpose:D.purpose||E.purpose, main:String(D.main||'').split('\n'), delegations:E.dels};
  }
  const A=RA.amend, t=raAmendFullText()||{};
  return {mode, focus:raEffChanges().map(c=>c.no), alio_refs:raAlioRefList('amend'), title:A.title, slug:A.slug, text:t.text||'', addenda:raDocCtx('amend').addenda, purpose:A.purpose||A.intent, main:A.main||[], delegations:A.refText?[{law:'참고',art:'',text:A.refText}]:[]};
}
function raReview(mode){ return raOnce('review:'+mode, ()=>_raReview(mode)); }
async function _raReview(mode){
  const body={...raReviewPayload(mode), ans:RA.proc.ans||{}, ai:raHasAi(), ...raAi()};
  if(!body.text.trim()){ _toast('검토할 조문이 없습니다.'); return; }
  const box=document.getElementById('raReview'); if(box) box.innerHTML=raSpin(raHasAi()?'심의기준별로 점검하고 AI 검토의견을 받는 중... (20~40초)':'심의기준별로 점검하는 중...');
  const gen=_raGen[mode], S=RA[mode];
  const d=await raPost('/api/regagent/review', body);
  if(gen!==_raGen[mode]||S!==RA[mode]) return;
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'검토 실패'); return; }
  RA[mode].review=d; _raSave(); if(box) box.innerHTML=raReviewView(d);
}
const RA_ST={ok:['적합','ok'],check:['확인 필요','check'],warn:['보완 필요','warn']};
const RA_ST_IC={ok:'check',check:'info',warn:'alert'};
const RA_ST_TONE={ok:'ok',check:'warn',warn:'bad'};
function raReviewView(d){
  if(!d) return '';
  const cnt=k=>d.rows.filter(r=>r.status===k).length;
  return raStack([{n:cnt('warn'),l:'보완 필요',tone:'bad'},{n:cnt('check'),l:'확인 필요',tone:'warn'},{n:cnt('ok'),l:'적합',tone:'ok'}],'심의기준 판정')+
    (d.model?`<div class="ra-meta"><span class="ra-chip sem">${raIc('spark')}AI 의견 · ${_e(d.model)}</span></div>`:'')+
    (d.notice?`<div class="ra-note ra-note-i">${raIc('info')}<span>${_e(d.notice)}</span></div>`:'')+
    `<div class="ra-revg">`+d.rows.map(r=>`<div class="ra-revc s-${r.status}"><div class="ra-revc-h"><span class="ra-revc-ic t-${RA_ST_TONE[r.status]}">${raIc(RA_ST_IC[r.status])}</span><div><b>${_e(r.t)}</b> ${raTip(r.d||'')}<div class="ra-ref">${_e(r.ref)}</div></div>`+
      `<span class="ra-st st-${RA_ST[r.status][1]}">${RA_ST[r.status][0]}</span></div>`+
      (r.items.length?`<ul class="ra-revc-l">${r.items.map(i=>`<li>${_e(i.msg)}</li>`).join('')}</ul>`:'')+
      (r.ai?`<div class="ra-aiop">${raIc('spark')}${_e(r.ai)}</div>`:'')+`</div>`).join('')+`</div>`+
    (d.delegation?`<div class="ra-note"><b>위임 범위·상위법 저촉 검토</b><br>${_e(d.delegation)}</div>`:'')+
    (d.overall?`<div class="ra-note"><b>종합의견</b><br>${_e(d.overall)}</div>`:'');
}
function raReviewSec(mode){
  return `<div class="ra-row"><button class="svc-btn" onclick="raReview('${mode}')">${raIc('check')}심의 사전검토</button>${raTip(`필요성·적합성·통일성·명료성·체제·공개 등 ${_e(RA_ORG.reg_word)}심의 기준으로 미리 점검합니다${raHasAi()?'(AI 검토의견·위임 범위 검토 포함)':''}. 결과는 「사전검토 의견서」로 저장됩니다.`)}</div><div id="raReview">${raReviewView(RA[mode].review)}</div>`;
}
function raDocReview(c, mode){
  const o=raOutReview(c, mode);
  return o?raOutText(o):'심의 사전검토를 먼저 실행하세요(위의 「심의 사전검토」).';
}

// ══════════════════════════════════════════════════════════════════════════
// 문서 세트
// ══════════════════════════════════════════════════════════════════════════
const RA_DOCS={
  enact:[['law','내규안'],['reason','제정 이유서'],['cmp','신구조문대비표'],['notice','대국민 사전예고문'],['staff','직원 의견수렴 공고'],['review','사전검토 의견서']],
  amend:[['law','개정문'],['reason','개정 이유서'],['cmp','신구조문대비표'],['notice','대국민 사전예고문'],['staff','직원 의견수렴 공고'],['review','사전검토 의견서']],
};
const RA_DOC_IC={law:'doc',reason:'tip',cmp:'amend',notice:'info',staff:'proc',review:'check',amend:'doc',addenda:'bulk'};
function raDocCtx(mode){
  if(mode==='enact'){
    const E=RA.enact, D=E.draft||{}; const p=raParse(D.text||'');
    const title=E.title||'○○규칙'; const kind=raKind(title);
    return {mode, title, kind, word:'제정', dept:E.dept||'○○팀', purpose:D.purpose||'', main:String(D.main||'').split('\n').map(s=>s.trim()).filter(Boolean),
      addenda:(D.addenda||'').trim()||`이 ${kind}${raJosa(kind)} ${E.effective||'발령한 날'}부터 시행한다.`, arts:p.articles, dels:E.dels||[]};
  }
  const A=RA.amend; const title=A.title||'○○규정'; const kind=raKind(title);
  return {mode, title, kind, word:'개정', dept:'○○팀', purpose:A.purpose||'', main:(A.main||[]).map(s=>String(s).trim()).filter(Boolean),
    addenda:(A.addenda||'').trim()||`이 ${kind}${raJosa(kind)} ${A.effective||'발령한 날'}부터 시행한다.`, changes:raEffChanges().sort((x,y)=>raCmp(x.no,y.no)), dels:[], fine:A.lawStyle!=='art', full:!!A.fullRev&&!!_raArts};
}
function raAddendaLines(t){ const s=String(t||'').trim(); return s.split('\n').map(x=>x.trim()).filter(Boolean); }
function raDocLaw(c){
  const L=[];
  if(c.mode==='enact'){
    L.push(`${c.title}(안)`,'');
    let chap='';
    c.arts.forEach(a=>{ if(a.chapter&&a.chapter!==chap){ chap=a.chapter; L.push('',chap); } L.push(...raArtText(a).split('\n')); });
  }else if(c.full){
    // 전부개정: 개정 반영 전체 조문을 새로 쓴다(삭제한 조는 빼고, 조 번호 정리는 입안자가 확인)
    L.push(`${c.title} 전부개정(안)`,'',`${c.title} 전부를 다음과 같이 개정한다.`,'');
    const F=raAmendFullText(); let chap='';
    ((F&&F.arts)||[]).filter(a=>!a.deleted).forEach(a=>{ if(a.chapter&&a.chapter!==chap){ chap=a.chapter; L.push('',chap); } L.push(...raArtText(a).split('\n')); });
  }else{
    L.push(`${c.title} 일부개정(안)`,'',`${c.title} 일부를 다음과 같이 개정한다.`,'');
    c.changes.forEach(ch=>{
      if(c.fine){ const r=raAmendSentences(ch.type==='insert'?null:raOld(ch.no), ch); if(r.head) L.push(r.head, ...r.lines, ''); return; }
      if(ch.type==='delete') L.push(`${raLbl(ch.no)}${raEul(raLbl(ch.no))} 삭제한다.`,'');
      else L.push(`${raLbl(ch.no)}${raEul(raLbl(ch.no))} 다음과 같이 ${ch.type==='insert'?'신설한다':'한다'}.`, ...raArtText(ch).split('\n'), '');
    });
  }
  L.push('','부    칙',...raAddendaLines(c.addenda));
  return L.join('\n').replace(/\n{3,}/g,'\n\n');
}
// ── 정밀 개정문 — 법제 실무의 일부개정 문형 ───────────────────────────────────
// 바뀐 곳만 “제5조제2항 중 “A”를 “B”로 한다.”처럼 짚고, 항·호를 끝에 덧붙이면 “같은 조에 제4항을 다음과 같이 신설한다.”,
// 구조가 크게 바뀌었거나 고친 곳이 많으면 조 전체를 “다음과 같이 한다.”로 쓴다. 한 조의 문장은 “…하고,”로 잇는다.
function raBat(w){   // 끝 글자 받침: 0 없음, 1 있음, 2 ㄹ(‘로’를 씀)
  let t=String(w||'').trim().replace(/[”"’'\]」』>]+$/,'');
  while(/\)$/.test(t)){ const k=t.lastIndexOf('('); if(k<=0) break; t=t.slice(0,k).trimEnd(); }   // “원장(부원장을 포함한다)” → “원장”
  const c=t.slice(-1);
  if(c>='\u4e00'&&c<='\u9fff') return 1;                       // 한자는 받침이 있는 것으로 본다
  if(c>='가'&&c<='힣'){ const j=(c.charCodeAt(0)-0xAC00)%28; return !j?0:j===8?2:1; }
  if(/[0-9]/.test(c)) return {'0':1,'1':2,'3':1,'6':1,'7':2,'8':2}[c]||0;   // 영·일·삼·육·칠·팔
  return 0;
}
function raEul(w){ return raBat(w)?'을':'를'; }
function raRo(w){ return raBat(w)===1?'으로':'로'; }
// 조 본문 → 항·호·목 단위 [{lv:'b'|'h'|'ho'|'mk', h, ho, mk, text}]
function raUnits(body){
  const out=[]; let h=0, ho=0;
  String(body||'').replace(/\r/g,'').replace(/ⓛ/g,'①').replace(/[\u2780-\u2789]/g,c=>String.fromCharCode(c.charCodeAt(0)-0x2780+0x2460)).split('\n').forEach(raw=>{
    const ln=raw.trim(); if(!ln) return;
    const mh=ln.match(/^([①-⑳])/);
    if(mh){ h=RA_HANG.indexOf(mh[1])+1; ho=0; out.push({lv:'h',h,ho:0,mk:'',text:ln}); return; }
    const m1=ln.match(/^(\d{1,2})\.\s/); if(m1){ ho=+m1[1]; out.push({lv:'ho',h,ho,mk:'',text:ln}); return; }
    const m2=ln.match(/^([가-하])\.\s/); if(m2&&ho){ out.push({lv:'mk',h,ho,mk:m2[1],text:ln}); return; }
    if(!out.length){ out.push({lv:'b',h:0,ho:0,mk:'',text:ln}); return; }
    out[out.length-1].text+='\n'+ln;            // 단서·이어지는 줄
  });
  return out;
}
function raUKey(u){ return u.lv+'|'+u.h+'|'+u.ho+'|'+u.mk; }
function raUBody(u){ return u.text.replace(/^(?:[①-⑳]\s*|\d{1,2}\.\s+|[가-하]\.\s+)/,''); }
// 단위 이름: 제5조제2항제3호가목, 아래에 호가 있는 항(또는 조 본문)은 “각 호 외의 부분”
function raULbl(no, u, all){
  let s=raLbl(no);
  if(u.h) s+=`제${u.h}항`;
  if(u.ho) s+=`제${u.ho}호`;
  if(u.mk) s+=`${u.mk}목`;
  if((u.lv==='b'||u.lv==='h') && all.some(x=>x.lv==='ho'&&x.h===u.h)) s+=' 각 호 외의 부분';
  else if(u.lv==='ho' && all.some(x=>x.lv==='mk'&&x.h===u.h&&x.ho===u.ho)) s+=' 각 목 외의 부분';
  return s;
}
// 한 단위 안에서 바뀐 한 구간 → {a, b} (어절 단위로 넓히고, 현행에서 한 번만 나오게). 못 짚으면 null
function raSubst(o, n){
  if(o===n) return null;
  let p=0; while(p<o.length&&p<n.length&&o[p]===n[p]) p++;
  let s=0; while(s<o.length-p&&s<n.length-p&&o[o.length-1-s]===n[n.length-1-s]) s++;
  let l=p, rO=o.length-s, rN=n.length-s;
  const sp=c=>/\s/.test(c||' ');
  while(l>0&&!sp(o[l-1])) l--;                                   // 어절 머리까지
  while(rO<o.length&&!sp(o[rO])&&!/[,.]/.test(o[rO])){ rO++; rN++; }   // 어절 끝까지(쉼표·마침표 앞)
  // “2분의 1”처럼 ‘의’ 뒤에 수가 오면 그 수까지
  if(/의$/.test(o.slice(l,rO))&&/^\s\d/.test(o.slice(rO))){ let e=rO+1; while(e<o.length&&!sp(o[e])&&!/[,.]/.test(o[e])) e++; rN+=e-rO; rO=e; }
  // 공통 조사는 따옴표 밖으로 뺀다: “3만원”을 → “5만원”으로
  const JS=/(으로|에서|에게|까지|부터|이나|이며|이고|과|와|을|를|이|가|은|는|에|로|도|만)$/;   // ‘의’는 빼지 않는다(“2분의 1”)
  const fam=x=>({'으로':'로','를':'을','가':'이','는':'은','와':'과'})[x]||x;     // 받침에 따라 바뀌는 같은 조사
  const jo=(o.slice(l,rO).match(JS)||[])[1], jn=(n.slice(l,rN).match(JS)||[])[1];
  if(jo&&jn&&fam(jo)===fam(jn) && rO-jo.length>l && rO-jo.length>=p && rN-jn.length>=p){ rO-=jo.length; rN-=jn.length; }
  const cnt=t=>t?o.split(t).length-1:0;
  for(let k=0;k<3&&(rO-l<2||cnt(o.slice(l,rO))!==1);k++){        // 짧거나 여러 번 나오면 앞 어절을 붙인다
    if(l===0) break;
    l--; while(l>0&&sp(o[l-1])) l--; while(l>0&&!sp(o[l-1])) l--;
  }
  // 낫표(「…」) 안에서 끊기면 낫표 전체로 넓힌다(“법률」” → “「공공기관의 운영에 관한 법률」”)
  const nq=(t,c)=>(t.match(new RegExp(c,'g'))||[]).length;
  if(nq(o.slice(l,rO),'」')>nq(o.slice(l,rO),'「')){ const k=o.lastIndexOf('「',l); if(k>=0) l=k; }
  if(nq(o.slice(l,rO),'「')>nq(o.slice(l,rO),'」')){ const e=o.indexOf('」',rO); if(e>=0&&nq(n.slice(l,rN+e+1-rO),'「')===nq(n.slice(l,rN+e+1-rO),'」')){ rN+=e+1-rO; rO=e+1; } }
  let a=o.slice(l,rO), b=n.slice(l,rN);
  if(!a.trim()||cnt(a)!==1) return null;
  if(!b.trim()){ if(sp(o[rO])&&o[rO]!=='\n') a+=' '; else if(l>0&&sp(o[l-1])) a=' '+a; }   // 지울 때는 띄어쓰기 한 칸도 함께
  if(a.length>60||a.includes('\n')||b.includes('\n')) return null;
  if(a.trim()===o.trim()||(o.length>=12&&!/^「.*」$/.test(a.trim())&&a.trim().length>=o.trim().length*0.7)) return null;   // 거의 다 바뀌면 단위째 고쳐 쓴다
  return {a, b:b.trim()};
}
// 한 조의 개정 → {head:문장, lines:뒤에 붙일 조문 줄}
function raAmendSentences(oldA, ch){
  const L=raLbl(ch.no), LE=L+raEul(L), full=t=>({head:`${LE} 다음과 같이 ${t}.`, lines:raArtText(ch).split('\n')});
  if(ch.type==='delete') return {head:`${LE} 삭제한다.`, lines:[]};
  if(!oldA||ch.type==='insert'||oldA.deleted) return full('신설한다');
  const O=raUnits(oldA.body), N=raUnits(ch.body);
  const whole=()=>full('한다');
  const S=[], add=(s,lines)=>S.push({s, lines:lines||[]});
  const ot=String(oldA.title||'').trim(), nt=String(ch.title||'').trim();
  if(ot!==nt){ if(!nt) return whole(); add(`${L}의 제목 “${ot}”${raEul(ot)} “${nt}”${raRo(nt)} 한다.`); }
  const ok=new Map(O.map(u=>[raUKey(u),u])), nk=new Map(N.map(u=>[raUKey(u),u]));
  // 현행 단위가 개정안에 그대로 있어야 한다(끝에서 지운 단위만 허용)
  const removed=O.filter(u=>!nk.has(raUKey(u))), added=N.filter(u=>!ok.has(raUKey(u)));
  const tailOf=(arr,u,sib)=>!arr.some(x=>sib(x,u)&&arr.indexOf(x)>arr.indexOf(u));
  const sibOf=(x,u)=>x.lv===u.lv&&(u.lv==='h'||x.h===u.h)&&(u.lv!=='mk'||x.ho===u.ho);
  if(removed.some(u=>u.lv==='b'||!tailOf(O,u,sibOf))) return whole();
  if(added.some(u=>u.lv==='b'||!tailOf(N,u,sibOf))) return whole();
  if(O.length===1&&O[0].lv==='b'&&N.length>1&&N[0].lv==='h') return whole();
  if(added.some(u=>O.some(o=>raUBody(o)===raUBody(u)))) return whole();   // 중간에 끼워 넣어 번호가 밀림(현행 내용이 새 번호로 옮겨 감)   // 단일 조문 → 항으로 나눔
  const subs=[];                              // [{lbl, a, b}] 같은 a→b는 “각각”으로 묶는다
  O.forEach(u=>{ const v=nk.get(raUKey(u)); if(!v||v.text===u.text) return;
    const lbl=raULbl(ch.no,u,O); const r=raSubst(raUBody(u), raUBody(v));
    if(r) subs.push({lbl, ...r}); else add(`${lbl}${raEul(lbl)} 다음과 같이 한다.`, v.text.split('\n')); });
  const groups=[];
  subs.forEach(x=>{ const g=groups.find(g=>g.a===x.a&&g.b===x.b); if(g) g.lbls.push(x.lbl); else groups.push({a:x.a,b:x.b,lbls:[x.lbl]}); });
  const join=ls=>{ const r=ls.map((x,i)=>i&&x.startsWith(L+'제')?x.slice(L.length):x); return r.length<2?r[0]:r.slice(0,-1).join('·')+' 및 '+r[r.length-1]; };
  groups.forEach(g=>{ const each=g.lbls.length>1?'각각 ':'';
    add(g.b?`${join(g.lbls)} 중 “${g.a.trim()}”${raEul(g.a)} ${each}“${g.b}”${raRo(g.b)} 한다.`:`${join(g.lbls)} 중 “${g.a.trim()}”${raEul(g.a)} 삭제한다.`); });
  removed.forEach(u=>{ const lbl=raULbl(ch.no,u,O).replace(/ 각 [호목] 외의 부분$/,''); add(`${lbl}${raEul(lbl)} 삭제한다.`); });
  // 덧붙인 단위: 부모별로 묶어 “같은 조에 제4항 및 제5항을 각각 다음과 같이 신설한다.”
  const par=u=>u.lv==='h'?L:u.lv==='ho'?(L+(u.h?`제${u.h}항`:'')):(L+(u.h?`제${u.h}항`:'')+`제${u.ho}호`);
  const own=u=>u.lv==='h'?`제${u.h}항`:u.lv==='ho'?`제${u.ho}호`:`${u.mk}목`;
  const ag=[]; added.forEach(u=>{ const p=par(u); const g=ag.find(x=>x.p===p); if(g) g.us.push(u); else ag.push({p,us:[u]}); });
  ag.forEach(g=>{ const names=g.us.map(own); const nm=names.length<2?names[0]:names.slice(0,-1).join('·')+' 및 '+names[names.length-1];
    add(`${g.p}에 ${nm}${raEul(nm)} ${g.us.length>1?'각각 ':''}다음과 같이 신설한다.`, g.us.flatMap(u=>u.text.split('\n'))); });
  if(!S.length) return {head:'', lines:[]};
  const touched=O.filter(u=>{ const v=nk.get(raUKey(u)); return !v||v.text!==u.text; }).length;   // 고치거나 지운 현행 단위
  if(S.length>4 || (O.length>2 && S.length>1 && touched>=Math.ceil(O.length*0.6))) return whole();
  // 한 문장으로 잇기: “…하고, 같은 조 제3항 중 …”
  const head=S.map((x,i)=>{ let t=x.s; if(i) t=t.replace(new RegExp('^'+L+'(?=제|에|의| )'),m=>'같은 조').replace(/^같은 조(?=제)/,'같은 조 ');
    return i<S.length-1?t.replace(/한다\.$/,'하고,'):t; }).join(' ');
  return {head, lines:S.flatMap(x=>x.lines)};
}
// 개정 규모 → 일부개정/전부개정 권고(고친 조가 전체의 절반 이상이면 전부개정을 검토)
function raAmendScale(){
  const A=RA.amend; const total=_raArts?_raArts.articles.filter(a=>!a.deleted).length:0;
  const n=raEffChanges().length; const ratio=total?n/total:0;
  return {total, n, ratio, full:total>=4&&ratio>=0.5};
}
// 개정문 미리보기(수정안 카드 아래 한 줄)
function raSenPreview(c){
  if(RA.amend.lawStyle==='art') return '';
  const r=raAmendSentences(c.type==='insert'?null:raOld(c.no), c);
  return r.head?`<div class="ra-sen">${raIc('doc')}<span>${_e(r.head)}</span></div>`:'';
}

// ── 부칙 도우미 — 시행일·적용례·경과조치·다른 내규의 개정 ─────────────────────────
function raAb(mode){ const S=RA[mode]; if(!S.ab) S.ab={eff:'issue',date:'',months:'3',apply:false,applyWhat:'',trans:false,other:false}; return S.ab; }
function raAbSet(mode,k,v){ raAb(mode)[k]=v; _raSave(); const b=document.getElementById('raAbPrev'); if(b) b.textContent=raAbBuild(mode); }
// 영향 분석에서 나온 다른 내규의 조 인용 정정 → [{reg, lines:[“…”를 “…”로 한다.]}]
function raAbOther(){
  const I=RA.amend.impact; if(!I||!I.outer) return [];
  return I.outer.map(o=>{
    const lines=[];
    o.hits.forEach(h=>{ if(!h.suggest) return; const to=raNormNo((h.suggest.split('→')[1]||'')); if(!to) return;
      const k=raKey(h.cites); const re=new RegExp('제\\s*'+k[0]+'\\s*조'+(k[1]?'\\s*의\\s*'+k[1]:'(?!\\s*의\\s*\\d)'));
      const nt=h.text.replace(re, raLbl(to)); if(nt===h.text) return;
      const s=`${raLbl(h.no)} 중 “${h.text}”${raEul(h.text)} “${nt}”${raRo(nt)} 한다.`; if(!lines.includes(s)) lines.push(s); });
    return {reg:o.reg, lines};
  }).filter(x=>x.lines.length);
}
function raAbBuild(mode){
  const S=RA[mode], B=raAb(mode);
  const title=S.title||(mode==='enact'?'○○규칙':'○○규정'); const kind=raKind(title), jo=raJosa(kind);
  const when=B.eff==='date'&&String(B.date).trim()?`${String(B.date).trim()}부터`:B.eff==='after'?`발령 후 ${Math.max(1,+B.months||3)}개월이 경과한 날부터`:'발령한 날부터';
  const items=[['시행일',[`이 ${kind}${jo} ${when} 시행한다.`]]];
  if(B.apply){
    const first=mode==='amend'?(S.changes.find(c=>c.type!=='delete')||{}).no:'';
    const subj=first?`${raLbl(first)}의 개정규정은`:`이 ${kind}${jo}`;
    items.push(['적용례',[`${subj} 이 ${kind} 시행 이후 최초로 ${String(B.applyWhat||'').trim()||'○○하는 경우'}부터 적용한다.`]]);
  }
  if(B.trans) items.push(['경과조치',[mode==='enact'
    ?`이 ${kind} 시행 전에 종전의 지침·관행에 따라 한 행위는 이 ${kind}에 따라 한 것으로 본다.`
    :`이 ${kind} 시행 당시 종전의 규정에 따라 한 처분·절차, 그 밖의 행위는 이 ${kind}의 개정규정에 따라 한 것으로 본다.`]]);
  if(B.other&&mode==='amend'){
    const O=raAbOther();
    if(O.length) items.push([`다른 ${RA_ORG.reg_word||'내규'}의 개정`, O.flatMap((o,i)=>[`${O.length>1?RA_HANG[i]+' ':''}「${o.reg}」 일부를 다음과 같이 개정한다.`, ...o.lines])]);
  }
  if(items.length===1) return items[0][1][0];
  return items.map(([t,ls],i)=>`제${i+1}조(${t}) ${ls[0]}`+(ls.length>1?'\n'+ls.slice(1).join('\n'):'')).join('\n');
}
function raAbView(mode){
  const B=raAb(mode), nOther=mode==='amend'?raAbOther().length:0;
  const r=(v,l)=>`<label class="ra-chk"><input type="radio" name="raAbEff${mode}" ${B.eff===v?'checked':''} onchange="raAbSet('${mode}','eff','${v}')"> ${l}</label>`;
  const c=(k,l,dis)=>`<label class="ra-chk${dis?' dis':''}"><input type="checkbox" ${B[k]&&!dis?'checked':''} ${dis?'disabled':''} onchange="raAbSet('${mode}','${k}',this.checked)"> ${l}</label>`;
  return `<details class="ra-det ra-ab"${B.open?' open':''} ontoggle="raAb('${mode}').open=this.open;_raSave()"><summary>${raIc('bulk')}부칙 도우미 ${raTip('시행일·적용례·경과조치·다른 내규의 개정을 표준 문형으로 만듭니다. 항목이 둘 이상이면 “제1조(시행일)”처럼 조로 나눕니다.')}</summary>`+
    `<div class="ra-ab-g"><div><div class="ra-lab">시행일</div>${r('issue','발령한 날')}${r('date','날짜 지정')}<input class="ra-in sm" style="max-width:140px" placeholder="2027년 1월 1일" value="${_e(B.date)}" oninput="raAbSet('${mode}','date',this.value)">`+
    `${r('after','발령 후')}<input class="ra-in sm" style="max-width:56px" type="number" min="1" max="24" value="${_e(B.months)}" oninput="raAbSet('${mode}','months',this.value)"> 개월</div>`+
    `<div><div class="ra-lab">덧붙일 조항</div>${c('apply','적용례')}<input class="ra-in sm" style="max-width:200px" placeholder="예) 출장을 명하는 경우" value="${_e(B.applyWhat)}" oninput="raAbSet('${mode}','applyWhat',this.value)">`+
    `${c('trans','경과조치')}${mode==='amend'?c('other',`다른 ${_e(RA_ORG.reg_word||'내규')}의 개정${nOther?` (${nOther}개)`:''}`,!nOther)+(nOther?'':raTip('영향 분석에서 이동표로 다른 내규의 조 인용 정정이 나오면 쓸 수 있습니다.')):''}</div></div>`+
    `<pre class="ra-ab-p" id="raAbPrev">${_e(raAbBuild(mode))}</pre><div class="ra-row"><button class="svc-btn sm yes" onclick="raAbApply('${mode}')">부칙에 넣기</button></div></details>`;
}
function raAbApply(mode){
  const t=raAbBuild(mode);
  if(mode==='enact'){ const D=RA.enact.draft; if(!D) return; if(D.addenda.trim()&&D.addenda.trim()!==t&&!confirm('지금 부칙을 도우미 내용으로 바꿀까요?')) return; D.addenda=t; }
  else{ const A=RA.amend; if(String(A.addenda||'').trim()&&A.addenda.trim()!==t&&!confirm('지금 부칙을 도우미 내용으로 바꿀까요?')) return; A.addenda=t; }
  raDirty(mode); _raSave(); raRerender(mode); _toast('부칙을 넣었습니다.');
}

// ── 표준 조문 — 위원회·비밀 유지·세부사항 위임 등 자주 쓰는 조문 문형(org_config.json clauses로 바꿀 수 있음) ──
const RA_CLAUSES=[
  {t:'위원회의 설치', b:'① ○○에 관한 사항을 심의하기 위하여 {org} 소속으로 ○○위원회(이하 “위원회”라 한다)를 둔다.\n② 위원회는 다음 각 호의 사항을 심의한다.\n1. ○○에 관한 사항\n2. 그 밖에 위원장이 필요하다고 인정하는 사항'},
  {t:'위원회의 구성', b:'① 위원회는 위원장 1명을 포함하여 ○명 이내의 위원으로 구성한다.\n② 위원장은 {deputy:이} 되고, 위원은 ○○ 중에서 {head:이} 지명하는 사람이 된다.\n③ 위원회의 사무를 처리하기 위하여 간사 1명을 두며, 간사는 소관부서의 장이 된다.'},
  {t:'위원회의 운영', b:'① 위원장은 위원회의 회의를 소집하고 그 의장이 된다.\n② 위원회의 회의는 재적위원 과반수의 출석으로 개의하고, 출석위원 과반수의 찬성으로 의결한다.\n③ 위원장은 긴급하거나 부득이한 사유가 있으면 서면으로 심의·의결할 수 있다.'},
  {t:'위원의 제척·기피·회피', b:'① 위원은 다음 각 호의 어느 하나에 해당하는 경우에는 해당 안건의 심의·의결에서 제척된다.\n1. 위원이 해당 안건의 당사자이거나 당사자와 친족 관계에 있는 경우\n2. 위원이 해당 안건에 관하여 자문·용역 등을 한 경우\n② 당사자는 위원에게 공정한 심의를 기대하기 어려운 사정이 있으면 기피 신청을 할 수 있다.\n③ 위원은 제1항 각 호에 해당하면 스스로 해당 안건의 심의·의결에서 회피하여야 한다.'},
  {t:'비밀 유지', b:'이 {kind}에 따른 업무에 종사하거나 종사하였던 사람은 업무상 알게 된 비밀을 누설하거나 목적 외의 용도로 사용해서는 아니 된다.'},
  {t:'서식', b:'이 {kind}의 시행에 필요한 서식은 별지와 같다.'},
  {t:'세부사항', b:'이 {kind}에서 정한 사항 외에 ○○에 필요한 세부사항은 {head:이} 따로 정한다.'},
  {t:'재검토기한', b:'{head:은} 이 {kind}에 대하여 ○○○○년 ○월 ○일을 기준으로 매 3년이 되는 시점마다 그 타당성을 검토하여 개선 등의 조치를 하여야 한다.'},
];
function raClauses(){ return Array.isArray(RA_ORG.clauses)&&RA_ORG.clauses.length?RA_ORG.clauses.filter(x=>x&&x.t&&x.b):RA_CLAUSES; }
function raClauseFmt(b, kind){
  const P={'이':['이','가'],'은':['은','는'],'을':['을','를']};
  const V={org:RA_ORG.org_name||'○○', head:RA_ORG.head||'기관장', deputy:RA_ORG.deputy||'부기관장', kind};
  return String(b).replace(/\{(org|head|deputy|kind)(?::(이|은|을))?\}/g,(m,k,p)=>V[k]+(p?raJosa(V[k],P[p]):''));
}
function raClausePick(mode){
  return `<select class="ra-in sm" style="max-width:190px" onchange="if(this.value!=='')raClauseIns('${mode}',+this.value);this.value=''"><option value="">＋ 표준 조문 넣기</option>${raClauses().map((c,i)=>`<option value="${i}">${_e(c.t)}</option>`).join('')}</select>`;
}
function raClauseIns(mode, i){
  const c=raClauses()[i]; if(!c) return;
  if(mode==='enact'){
    const E=RA.enact, D=E.draft; if(!D) return;
    const body=raClauseFmt(c.b, raKind(E.title)); const p=raParse(D.text);
    if(p.articles.some(a=>a.title===c.t)&&!confirm(`“${c.t}” 조가 이미 있습니다. 하나 더 넣을까요?`)) return;
    // 맨 끝의 세부사항·재검토기한 조는 그대로 맨 끝에 두고 그 앞에 넣는다(뒤 조는 번호를 하나씩 미룬다, 붙인 조는 인용이 없어 안전)
    const tailRe=/^(세부사항|재검토기한|위임)$/; let k=p.articles.length;
    while(k>0&&tailRe.test(p.articles[k-1].title)&&!tailRe.test(c.t)) k--;
    const pos=k<p.articles.length&&p.articles.slice(k).every(a=>!raKey(a.no)[1]);
    const n=pos?raKey(p.articles[k].no)[0]:p.articles.reduce((m,a)=>Math.max(m,raKey(a.no)[0]),0)+1;
    const arts=p.articles.map(a=>({...a}));
    if(pos) arts.slice(k).forEach(a=>{ a.no=String(raKey(a.no)[0]+1); });
    arts.splice(pos?k:arts.length,0,{no:String(n), title:c.t, body, chapter:(arts[(pos?k:arts.length)-1]||{}).chapter||''});
    D.text=raDraftText(arts); raDirty('enact');
    _raSave(); raRerender('enact'); _toast(`제${n}조(${c.t})를 넣었습니다. ○○ 자리를 채우세요.`);
  }else{
    const A=RA.amend; if(!_raArts){ _toast('먼저 내규를 불러오세요.'); return; }
    const body=raClauseFmt(c.b, raKind(A.title));
    const n=[..._raArts.articles.map(a=>a.no),...A.changes.map(x=>x.no)].reduce((m,no)=>Math.max(m,raKey(no)[0]),0)+1;
    A.changes.push({type:'insert', no:String(n), title:c.t, body, why:'표준 조문'}); A.changes.sort((x,y)=>raCmp(x.no,y.no));
    raDirty('amend', true); _raSave(); raRerender('amend'); _toast(`제${n}조(${c.t})를 신설안으로 넣었습니다. 위치를 옮기려면 조 번호를 바꾸세요.`);
  }
}
// ── 공문서 문서(이유서·사전예고문·의견수렴 공고·사전검토 의견서) ─────────────────────────
// 내용은 하나의 개요(outline)로 만들고 화면·복사·문서 파일용 글을 그 개요에서 만든다.
// 표기는 행정업무운영편람 기준: 날짜 “2026. 10. 6.”, 기간 “∼” 붙여 씀, “붙임  … 1부.  끝.”(쌍점 없음, 두 칸)
function raOutText(o){
  const L=[o.title,''];
  if(o.lead) L.push(o.lead,'');
  o.items.forEach((it,i)=>{ L.push(`${i+1}. ${it.t}`); (it.s||[]).forEach((x,j)=>L.push(`  ${'가나다라마바사아자차카타파하'[j]||'-'}. ${x}`)); L.push(''); });
  L.push(o.tail||'끝.');
  return L.join('\n');
}
const RA_BUNIM='붙임  신구조문대비표 1부.  끝.';
function raBunim(c){ return c.mode==='enact'?'붙임  제정안 1부.  끝.':RA_BUNIM; }
function raOutReason(c){
  const main=c.main.length?c.main:(c.mode==='enact'?c.arts.slice(2).map(a=>`${a.title}에 관한 사항을 정함(안 ${raLbl(a.no)})`):c.changes.map(ch=>`${ch.title||raLbl(ch.no)} ${ch.type==='insert'?'신설':ch.type==='delete'?'삭제':'정비'}(안 ${raLbl(ch.no)})`));
  return {title:`「${c.title}」 ${c.word} 이유서`, items:[
    {t:`${c.word} 이유`, s:[c.purpose||`○○에 필요한 사항을 정하기 위하여 「${c.title}」${raEul(c.title)} ${c.word}하려는 것임.`]},
    {t:'주요 내용', s:main.length?main:['○○']},
    {t:'관련 근거', s:c.dels.length?c.dels.map(d=>`「${d.law}」 ${raDelArt(d)}`.trim()):[`「${raRules()}」 제14조(입안)`]},
    ...(raAlioRefList(c.mode).length?[{t:'다른 공공기관 사례(알리오 공시 내부규정)', s:raAlioRefList(c.mode).slice(0,6).map(raAlioRefLine)}]:[]),
    {t:'행정사항', s:[`시행일: ${(raAddendaLines(c.addenda)[0]||'').replace(/^제\d+조\([^)]*\)\s*/,'')}`,'관련 부서 협의: ○○팀(협의 완료/예정)',`사전예고·직원 의견수렴: 「${raRules()}」 제15조의3·제15조의4에 따라 실시(해당 시)`]},
  ], tail:raBunim(c)};
}
function raOutNotice(c, staff){
  const days=staff?(+RA_ORG.staff_days||7):(+RA_ORG.notice_days||20);
  return {title:staff?`「${c.title}」 ${c.word}(안) 직원 의견수렴 공고`:`「${c.title}」 ${c.word}(안) 사전예고`,
    lead:staff?`「${c.title}」${raEul(c.title)} ${c.word}하기에 앞서 임직원의 의견을 듣고자 「${raRules()}」 제15조의4에 따라 다음과 같이 알립니다.`
              :`${RA_ORG.org_name}${raJosa(RA_ORG.org_name)} 「${c.title}」${raEul(c.title)} ${c.word}함에 있어 국민·기관·단체의 의견을 듣고자 「${raRules()}」 제15조의3에 따라 다음과 같이 예고합니다.`,
    items:[
      {t:`${RA_ORG.reg_word}명: ${c.title}`},
      {t:`${c.word} 이유`, s:[c.purpose||'○○']},
      {t:'주요 내용', s:c.main.length?c.main:['○○']},
      {t:'의견 제출', s:[`기간: ${raToday(0)}∼${raToday(days)}(${days}일 이상)`,
        `제출처: ${c.dept}(전화 ○○○-○○○○-○○○○, 전자우편 ○○○@${RA_ORG.email_domain||'example.or.kr'})`,
        `제출 방법: 의견서에 ${staff?'소속·':''}성명, 전화번호, 전자우편 주소를 적어 전자우편 또는 ${staff?'내부포털로':'서면으로'} 제출하시기 바랍니다.`]},
    ], tail:raBunim(c)};
}
function raOutReview(c, mode){
  const d=RA[mode].review; if(!d) return null;
  const items=d.rows.map(r=>({t:`${r.t}(${r.ref}): ${RA_ST[r.status][0]}`, s:[...r.items.map(x=>x.msg), ...(r.ai?[`검토의견: ${r.ai}`]:[])]}));
  if(d.delegation) items.push({t:'위임 범위·상위법 저촉 검토', s:[d.delegation]});
  if(d.overall) items.push({t:'종합의견', s:[d.overall]});
  return {title:`「${c.title}」 ${c.word}(안) 심의 사전검토 의견서`, lead:`검토 기준: 「${raRules()}」 심의사항, 검토일: ${raToday(0)}`, items, tail:'끝.'};
}
function raDocReason(c){ return raOutText(raOutReason(c)); }
function raDocNotice(c, staff){ return raOutText(raOutNotice(c, staff)); }
function raDocCmpRows(c){
  if(c.mode==='enact') return c.arts.map(a=>{ const t=raArtText(a); return ['&lt;신 설&gt;', `<u class="ra-i">${_e(t).replace(/\n/g,'<br>')}</u>`, '<신 설>', t]; });
  return raCmpRows();
}
function raDocsBuild(mode){
  const c=raDocCtx(mode);
  const cmp=raDocCmpRows(c);
  return {c, law:raDocLaw(c), reason:raDocReason(c), notice:raDocNotice(c,false), staff:raDocNotice(c,true), review:raDocReview(c,mode), cmp};
}
function raPicks(mode){ const S=RA[mode]; if(!Array.isArray(S.picks)) S.picks=RA_DOCS[mode].map(x=>x[0]).filter(k=>!(mode==='enact'&&k==='cmp')); return S.picks; }
function raPickSet(mode,k,on){ const P=raPicks(mode).filter(x=>x!==k); if(on) P.push(k); RA[mode].picks=RA_DOCS[mode].map(x=>x[0]).filter(x=>P.includes(x)); _raSave(); }
function raDocsView(mode){
  const S=RA[mode]; const tab=S.docTab||'law';
  const B=raDocsBuild(mode);
  const tabs=RA_DOCS[mode].map(([k,l])=>`<button class="ra-dtab${tab===k?' on':''}" onclick="raSet('${mode}.docTab','${k}');raRerender('${mode}')">${raIc(RA_DOC_IC[k]||'doc')}${l}</button>`).join('');
  let body;
  if(tab==='cmp') body=`<div class="ra-doc-t">「${_e(B.c.title)}」 ${B.c.word}안 신구조문대비표</div><table class="ra-cmp"><thead><tr><th>현 행</th><th>${B.c.word} 안</th></tr></thead><tbody>${B.cmp.map(r=>`<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('')||'<tr><td colspan="2">조문이 없습니다.</td></tr>'}</tbody></table>`;
  else body=`<pre class="ra-doc">${_e(B[tab])}</pre>`;
  const picks=raPicks(mode);
  const all=`<span class="ra-picks" title="저장할 문서">`+RA_DOCS[mode].map(([k,l])=>{ const off=k==='review'&&!S.review;
    return `<label class="ra-pk-c${off?' dis':''}"${off?' title="심의 사전검토를 실행하면 넣을 수 있습니다"':''}><input type="checkbox" class="ra-docpick" value="${k}" ${picks.includes(k)&&!off?'checked':''} ${off?'disabled':''} onchange="raPickSet('${mode}','${k}',this.checked)"><span>${raIc(RA_DOC_IC[k]||'doc')}${l}</span></label>`; }).join('')+`</span>`;
  return `<div class="ra-dtabs">${tabs}</div><div class="ra-docbox">${body}</div>`+
    `<div id="raNota">${raNotaView(mode)}</div>`+
    `<div class="ra-save">${all}<div class="ra-row"><button class="svc-btn ghost" onclick="raCopyDoc('${mode}')">복사</button><button class="svc-btn ghost" onclick="raPrintDoc('${mode}')">인쇄</button>`+
    `<span class="ra-sep"></span><button class="svc-btn yes" onclick="raExport('${mode}','hwpx')">한글(.hwpx)</button><button class="svc-btn" onclick="raExport('${mode}','docx')">Word(.docx)</button></div></div>`+
    `<div class="ra-meta"><span class="ra-days">사전예고 ${RA_ORG.notice_days}일↑</span><span class="ra-days">직원 의견수렴 ${RA_ORG.staff_days}일↑</span>${raTip(`사전예고는 국민 권리·의무 관련 ${RA_ORG.reg_word}(「${raRules()}」 제15조의3제2항)일 때, 직원 의견수렴은 제15조의4 — 절차 안내를 확인하세요.`)}</div>`;
}
// ── 공문서 표기 점검(행정업무운영편람) — 서버 notation.py 규칙: 날짜·기간·시각·금액·쌍점·붙임·끝·낫표·줄표·외래어 ──
const RA_NOTA_DOCS=['law','reason','notice','staff','review'];
async function raNotaLint(mode){
  const B=raDocsBuild(mode), texts={}, kinds={};
  RA_NOTA_DOCS.forEach(k=>{ if(k==='review'&&!RA[mode].review) return; texts[k]=B[k]; if(k==='law') kinds[k]='law'; });
  const box=document.getElementById('raNota'); if(box) box.innerHTML=raSpin('공문서 표기를 점검하는 중...');
  const d=await raPost('/api/regagent/notation',{texts, kinds});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'점검 실패'); return; }
  RA[mode].nota={at:raToday(0), res:d.results}; _raSave(); if(box) box.innerHTML=raNotaView(mode);
}
function raNotaView(mode){
  const L=RA[mode].nota, names=Object.fromEntries(RA_DOCS[mode]), tab=RA[mode].docTab||'law';
  const btn=`<button class="svc-btn sm" onclick="raNotaLint('${mode}')">${raIc('check')}공문서 표기 점검</button>`;
  const tip=raTip('행정업무운영편람 기준으로 날짜(2026. 10. 6.)·기간(∼)·시각(09:00)·금액(금30,000원(금삼만원))·쌍점·“붙임  … 1부.  끝.”·법령명 낫표, 줄표와 외래어를 점검합니다. 문서를 고친 뒤에는 다시 점검하세요.');
  if(!L||!L.res) return `<div class="ra-row ra-nota">${btn}${tip}</div>`;
  const chips=Object.entries(L.res).map(([k,f])=>{ const e=f.filter(x=>x.level==='error').length, w=f.filter(x=>x.level==='warn').length;
    return `<button class="ra-chip btn ${e?'hi':w?'warn':''}" onclick="raSet('${mode}.docTab','${k}');raRerender('${mode}')">${_e(names[k]||k)} ${f.length?f.length+'건':'✓'}</button>`; }).join('');
  const cur=L.res[tab], ic={error:'bad',warn:'alert',info:'tip'};
  const list=cur&&cur.length?`<ul class="ra-lint">`+cur.map(f=>`<li class="lv-${f.level}"><span>${raIc(ic[f.level]||'tip')}</span><span><b>${_e(f.label)}</b> ${f.line?`${f.line}행 `:''}“${_e(f.match)}”: ${_e(f.message)}${f.suggest?` <em class="ra-fix">${_e(f.suggest)}</em>`:''}</span></li>`).join('')+`</ul>`
    :cur?`<div class="ra-ok">${raIc('check')}${_e(names[tab]||'')} 표기 문제 없음</div>`:'';
  return `<div class="ra-row ra-nota">${btn}${tip}<span class="ra-sub">${_e(L.at)} 점검</span>${chips}</div>${list}`;
}
function raCopyDoc(mode){
  const B=raDocsBuild(mode), tab=RA[mode].docTab||'law';
  const t=tab==='cmp'?B.cmp.map(r=>`[현행]\n${r[2]}\n[${B.c.word}안]\n${r[3]}`).join('\n\n'):B[tab];
  _copyText(t, ()=>_toast('복사했습니다.'));
}
function raPrintDoc(mode){
  const B=raDocsBuild(mode), tab=RA[mode].docTab||'law';
  const inner=tab==='cmp'?`<h3>「${_e(B.c.title)}」 ${B.c.word}안 신구조문대비표</h3><table><tr><th>현 행</th><th>${B.c.word} 안</th></tr>${B.cmp.map(r=>`<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('')}</table>`:`<pre>${_e(B[tab])}</pre>`;
  const w=window.open('','_blank'); if(!w){ _toast('팝업이 차단되었습니다.'); return; }
  w.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${_e(B.c.title)}</title><style>body{font-family:'Malgun Gothic',sans-serif;font-size:13px;line-height:1.7;padding:24px;}pre{white-space:pre-wrap;font-family:inherit;}table{width:100%;border-collapse:collapse;}td,th{border:1px solid #444;padding:8px;vertical-align:top;width:50%;}th{background:#eee;}u.ra-d{text-decoration:underline;color:#b91c1c;}u.ra-i{text-decoration:underline;color:#1d4ed8;font-weight:600;}</style></head><body>${inner}</body></html>`);
  w.document.close(); w.focus(); setTimeout(()=>w.print(),300);
}
// 대비표 셀 HTML(<u class="ra-d|ra-i">·<br>) → 문서 서식 구간 [{s, u}] — 한글·Word 파일에도 밑줄을 살린다
function raHtmlRuns(html){
  const un=x=>String(x).replace(/<br\s*\/?>/g,'\n').replace(/<[^>]+>/g,'').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&amp;/g,'&');
  const out=[], re=/<u class="ra-([di])">([\s\S]*?)<\/u>/g; let last=0, m;
  while((m=re.exec(String(html||'')))){ if(m.index>last) out.push({s:un(html.slice(last,m.index)),u:''}); out.push({s:un(m[2]),u:m[1]}); last=re.lastIndex; }
  if(last<String(html||'').length) out.push({s:un(String(html).slice(last)),u:''});
  return out.filter(x=>x.s);
}
function raDocBlocks(B, picks){
  const blocks=[];
  picks.forEach((k,i)=>{
    if(i) blocks.push({t:'break'});
    if(k==='cmp'){
      blocks.push({t:'p',text:`「${B.c.title}」 ${B.c.word}안 신구조문대비표`,titleBold:1},{t:'p',text:''});
      blocks.push({t:'table',colWidths:[23814,23814],rows:[[{t:'현 행',hd:1},{t:`${B.c.word} 안`,hd:1}],...B.cmp.map(r=>[{t:r[2],r:raHtmlRuns(r[0])},{t:r[3],r:raHtmlRuns(r[1])}])]});
    } else blocks.push({t:'p',text:B[k],titleBold:1});
  });
  return blocks;
}
async function raSaveFile(fmt, name, blocks, label){
  _toast(fmt==='docx'?'Word 파일을 만드는 중...':'한글 파일을 만드는 중...');
  try{
    const r=await fetch('/api/regagent/'+fmt,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:name, blocks})});
    if(!r.ok){ let m='저장 실패'; try{ m=(await r.json()).error||m; }catch(e){} _toast(m); return; }
    const blob=await r.blob(); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=`${name}.${fmt}`;
    document.body.appendChild(a); a.click(); setTimeout(()=>{ URL.revokeObjectURL(a.href); a.remove(); },500);
    _toast(`${label||name}${raEul(label||name)} ${fmt==='docx'?'Word':'한글'} 파일로 저장했습니다.`);
  }catch(e){ _toast('서버 연결에 실패했습니다.'); }
}
function raExport(mode, fmt){
  const picks=raPicks(mode).filter(k=>k!=='review'||RA[mode].review);
  if(!picks.length){ _toast('저장할 문서를 고르세요.'); return; }
  const B=raDocsBuild(mode), names=Object.fromEntries(RA_DOCS[mode]);
  raSaveFile(fmt, `${B.c.title}_${B.c.word}안`, raDocBlocks(B,picks), picks.map(k=>names[k]).join('·'));
}

// ══════════════════════════════════════════════════════════════════════════
// ✦ 에이전트 모드 — 한 문장 지시 → 계획 → 단계별 자동 수행(진행 과정을 그대로 보여 줌)
// 서버는 계획만 세우고(/api/regagent/plan), 각 단계는 기존 API를 차례로 호출한다.
// ══════════════════════════════════════════════════════════════════════════
const RA_AG_EX=[
  ['개정','여비규정 제15조의 일비를 3만원으로 올려줘'],
  ['개정','출장 숙박비 상한을 실비 기준으로 바꾸고 싶어'],
  ['제정','업무용 드론 운영지침을 새로 만들어줘'],
  ['일괄 정비','기획운영본부를 경영기획본부로 모든 내규에서 바꿔줘'],
  ['상위법','「공공기관의 운영에 관한 법률」 제31조가 개정됐어'],
  ['다른 기관','다른 기관은 재택근무를 어떻게 규정했어?'],
];
const RA_MODE_L={amend:'개정',enact:'제정',bulk:'일괄 정비',upper:'상위법 영향',compare:'다른 기관 사례'};
function raAgentView(){
  const G=RA.agent;
  const mic={'개정':'amend','제정':'enact','일괄 정비':'bulk','상위법':'upper','다른 기관':'search'};
  const ex=RA_AG_EX.map(([k,t])=>`<button class="ra-ag-ex" onclick="raAgentEx('${_a(t)}')"><span class="ra-ag-ex-k">${raIc(mic[k]||'spark')}${_e(k)}</span><span class="ra-ag-ex-t">${_e(t)}</span></button>`).join('');
  const tip=`요청을 제정·개정·일괄 정비·상위법 영향 중 하나로 판단하고, 대상 ${RA_ORG.reg_word}와 조문을 찾아 초안 → 인용 영향 → 점검 → 심의 사전검토 → 절차 판단 → 문서 세트까지 이어서 수행합니다. `+(raHasAi()?'AI가 계획과 초안을 씁니다.':'AI 키가 없으면 규칙 기반으로 계획하고, 조문 문장은 결과 화면에서 직접 고칩니다.')+' (Ctrl+Enter로 실행)';
  return `<div class="ra-wide">`+
    `<section class="ra-ag-hero"><div class="ra-ag-label"><label for="raAgIn">무엇을 하고 싶으세요?</label>${raTip(tip)}</div>`+
    `<div class="ra-ag-box"><textarea id="raAgIn" class="ra-ag-in" rows="2" placeholder="예) 여비규정 제15조의 일비를 3만원으로 올려줘" oninput="raSet('agent.req',this.value)" onkeydown="if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();raAgentRun();}">${_e(G.req)}</textarea>`+
    `<button class="svc-btn yes ra-ag-go" onclick="raAgentRun()" ${G.running?'disabled':''}>${raIc('spark')}${G.running?'진행 중…':'에이전트 실행'}</button></div>`+
    `<div class="ra-ag-exs">${ex}</div></section>`+
    `<div id="raAgOut">${raAgentOut()}</div></div>`;
}
function raAgentEx(t){ RA.agent.req=t; _raSave(); const el=document.getElementById('raAgIn'); if(el){ el.value=t; el.focus(); } }
const RA_AG_ST={run:['진행 중','run'],ok:['완료','ok'],warn:['확인 필요','warn'],err:['중단','err'],skip:['건너뜀','skip']};
function raAgentOut(){
  const G=RA.agent; if(!G.steps.length) return '';
  const P=G.plan;
  const head=P?`<div class="ra-ag-plan"><span class="ra-pill ok">${raIc(P.mode==='amend'?'amend':P.mode==='enact'?'enact':P.mode==='bulk'?'bulk':P.mode==='compare'?'search':'upper')}${_e(RA_MODE_L[P.mode]||P.mode)}</span>`+
    (P.reg?`<span class="ra-pill">「${_e(P.reg.title)}」${(P.articles||[]).length?' '+P.articles.map(a=>raLbl(a.no)).join('·'):''}</span>`:'')+
    (P.mode==='bulk'?`<span class="ra-pill">“${_e(P.old)}” → “${_e(P.new)}”</span>`:'')+(P.mode==='upper'?`<span class="ra-pill">「${_e(P.law)}」 ${_e((P.arts||[]).join(', '))}</span>`:'')+
    (P.mode==='enact'&&P.title?`<span class="ra-pill">「${_e(P.title)}」</span>`:'')+(P.mode==='compare'?`<span class="ra-pill">알리오 “${_e(P.keyword||'')}”</span>`:'')+`<span class="ra-pill subtle">${P.ai?'AI 계획':'규칙 기반 계획'}</span></div>`:'';
  const steps=`<ol class="ra-ag-steps">`+G.steps.map((s,i)=>`<li class="st-${RA_AG_ST[s.st][1]}"><span class="ra-ag-dot">${s.st==='run'?'<span class="spinner"></span>':s.st==='ok'?'✓':s.st==='err'?'!':s.st==='warn'?'!':'–'}</span>`+
    `<div class="ra-ag-b"><div class="ra-ag-t"><b>${i+1}. ${_e(s.t)}</b><span class="ra-ag-s">${RA_AG_ST[s.st][0]}</span></div>${s.d?`<div class="ra-ag-d">${s.d}</div>`:''}</div></li>`).join('')+`</ol>`;
  const done=G.done?`<div class="ra-ag-done"><div><b>${_e(G.done.title)}</b><div class="ra-hint">${_e(G.done.sub)}</div></div><div class="ra-row" style="margin:0">`+
    G.done.acts.map(([l,f,yes])=>`<button class="svc-btn${yes?' yes':''}" onclick="${f}">${_e(l)}</button>`).join('')+`</div></div>`:'';
  const nst=k=>G.steps.filter(x=>x.st===k).length;
  const sum=raStack([{n:nst('ok'),l:'완료',tone:'ok'},{n:nst('warn'),l:'확인 필요',tone:'warn'},{n:nst('err'),l:'중단',tone:'bad'},{n:nst('run')+nst('skip'),l:G.running?'진행 중':'건너뜀',tone:'n'}],'단계 상태');
  return raSec('✦','에이전트 작업 내역',_e(G.req),head+sum+steps+done,'raAgSec');
}
function raAgentDraw(){ const o=document.getElementById('raAgOut'); if(o) o.innerHTML=raAgentOut(); }
// 내규명 끝말 → 종류(제정 화면의 종류 목록과 같은 이름)
function raCatOf(title){ const t=String(title||'').trim(); for(const c of ['시행세칙','정관','규정','규칙','지침','요령','기준','예규','매뉴얼']) if(t.endsWith(c)) return c; return ''; }
function raAgProc(category){
  // 에이전트 작업마다 새 절차로 본다: 단계(level)를 이번 내규 종류로 정하고 이전 작업의 완료 표시는 지운다
  const prev=RA.proc.ans||{};
  const level=(category==='규정'||category==='정관')?'reg':['예규','매뉴얼','지침','요령','기준'].includes(category)?'ye':'rule';
  if(prev.level!==level){ RA.proc.ans={level}; RA.proc.chk={}; }
  const a=RA.proc.ans;
  const st=raProcSteps();
  return `${_e(RA_ORG.reg_word)} 단계 <b>${a.level==='reg'?'규정(이사회 의결)':a.level==='ye'?'예규':'규칙·시행세칙(내규심의)'}</b>로 보고 ${st.length}단계 절차를 구성: `+st.map(s=>_e(s.t)).join(' → ');
}
async function raAgentRun(){
  const G=RA.agent; const el=document.getElementById('raAgIn'); if(el) G.req=el.value.trim();
  if(!G.req||G.req.length<4){ _toast('무엇을 하고 싶은지 한 문장으로 적어 주세요.'); return; }
  if(G.running) return;
  Object.assign(G,{steps:[],plan:null,done:null,running:true}); _raSave(); raRerender('agent');
  const step=t=>{ const s={t,st:'run',d:''}; G.steps.push(s); raAgentDraw(); return s; };
  const fin=(s,d,st)=>{ s.st=st||'ok'; s.d=d||''; raAgentDraw(); };
  const stop=(s,msg)=>{ fin(s,_e(msg),'err'); throw 'stop'; };
  try{
    let s=step('요청 분석·작업 계획');
    const d=await raPost('/api/regagent/plan',{request:G.req,...raAi()});
    if(!d.success) stop(s,d.error||'계획을 세우지 못했습니다.');
    const P=G.plan=d.plan;
    fin(s,(P.reasoning||[]).map(_e).join('<br>'));
    if(P.mode==='amend') await raAgAmend(P,step,fin,stop);
    else if(P.mode==='enact') await raAgEnact(P,step,fin,stop);
    else if(P.mode==='bulk') await raAgBulk(P,step,fin,stop);
    else if(P.mode==='compare') await raAgCompare(P,step,fin,stop);
    else await raAgUpper(P,step,fin,stop);
  }catch(e){ if(e!=='stop'){ console.error(e); const last=G.steps[G.steps.length-1]; if(last&&last.st==='run') fin(last,'처리 중 오류가 났습니다.','err'); } }
  G.running=false; _raSave(); raRerender('agent');
  setTimeout(()=>{ const x=document.getElementById('raAgSec'); if(x) x.scrollIntoView({behavior:'smooth',block:'start'}); },60);
}
async function raAgCheck(mode, step, fin){
  let s=step('조문 점검');
  let body;
  if(mode==='enact'){ const D=RA.enact.draft; body={text:D.text,addenda:D.addenda,title:RA.enact.title}; }
  else { const t=raAmendFullText(); body={text:t.text,addenda:t.addenda,title:RA.amend.title}; }
  const li=await raPost('/api/regagent/lint',body);
  if(li.success){
    let iss=li.issues; if(mode==='amend'){ const nos=new Set(RA.amend.changes.map(c=>c.no)); iss=iss.filter(i=>!i.no||nos.has(i.no)); }
    RA[mode].lint=li.issues;
    const c=l=>iss.filter(i=>i.level===l).length;
    fin(s,`오류 ${c('error')} · 주의 ${c('warn')} · 표기 제안 ${c('info')}`+(iss.length?'<br>'+iss.slice(0,3).map(i=>_e(i.msg)).join('<br>'):''), c('error')?'warn':'ok');
  } else fin(s,_e(li.error||'점검 실패'),'warn');
  s=step('심의 사전검토');
  const rv=await raPost('/api/regagent/review',{...raReviewPayload(mode),ans:RA.proc.ans||{},ai:raHasAi(),...raAi()});
  if(rv.success){ RA[mode].review=rv; const n=k=>rv.rows.filter(r=>r.status===k).length;
    fin(s,`적합 ${n('ok')} · 확인 필요 ${n('check')} · 보완 필요 ${n('warn')}`+(rv.overall?'<br>'+_e(rv.overall):''), n('warn')?'warn':'ok'); }
  else fin(s,_e(rv.error||'검토 실패'),'warn');
}
async function raAgAmend(P, step, fin, stop){
  const A=RA.amend; raGenBump('amend');
  if(!P.reg||!P.reg.slug) stop(step('대상 내규 찾기'),'개정할 내규를 찾지 못했습니다. 요청에 내규명을 넣어 다시 시도하세요(예: “여비규정 제15조…”).');
  let s=step(`「${P.reg.title}」 조문 불러오기`);
  const d=await raGet('/api/regagent/articles?slug='+encodeURIComponent(P.reg.slug));
  if(!d.success) stop(s,d.error||'불러오기 실패');
  _raArts=d;
  Object.assign(A,{src:'reg',pasted:false,slug:d.slug,title:d.title,sel:{},changes:[],impact:null,lint:null,review:null,purpose:'',main:[],addenda:'',notes:[],intent:P.intent||RA.agent.req,refText:'',model:''});
  const tg=(P.articles||[]).map(a=>raOld(a.no)).filter(Boolean);
  tg.forEach(a=>A.sel[a.no]=true);
  fin(s,`${d.articles.length}개 조 중 ${tg.length?tg.map(a=>`${raLbl(a.no)}(${_e(a.title)})`).join(', '):'대상 조문 없음 — AI가 목차를 보고 고릅니다'}`+((P.missing||[]).length?`<br>요청한 ${P.missing.map(raLbl).join(', ')}는 이 ${_e(RA_ORG.reg_word)}에 없어 내용이 가까운 조문을 골랐습니다.`:''), (P.missing||[]).length?'warn':'ok');
  A.alioRefs=await raAgAlioStep('amend', raAlioGuess('amend'), [A.intent,...tg.map(a=>a.title)].join(' '), step, fin);
  s=step('수정안 작성');
  let ok=false;
  if(raHasAi()){
    const r=await raPost('/api/regagent/draft',{mode:'amend',slug:A.slug,reg:A.title,intent:A.intent,targets:tg.map(a=>({no:a.no,title:a.title,body:a.body})),delegations:[],refs:Object.values(A.alioRefs||{}),...raAi()});
    if(r.success){ const x=r.draft; A.changes=x.changes.map(c=>({type:c.type,no:c.no,title:c.title,body:c.body,why:c.why}));
      A.purpose=(x.reason||{}).purpose||''; A.main=(x.reason||{}).main||[]; A.addenda=(x.addenda||[]).join('\n'); A.notes=x.notes||[]; A.model=x.model||''; ok=true;
      fin(s,`${A.changes.length}개 조문 수정안: `+A.changes.map(c=>`${raLbl(c.no)} ${({modify:'개정',insert:'신설',delete:'삭제'})[c.type]}`).join(', ')+(A.purpose?'<br>'+_e(A.purpose):'')); }
    else fin(s,_e(r.error||'AI 오류')+' — 대상 조문을 수정안 칸에 담았습니다.','warn');
  }
  if(!ok){
    A.changes=tg.map(a=>({type:'modify',no:a.no,title:a.title,body:a.body,why:'에이전트가 고른 대상 조문 — 내용을 고쳐 쓰세요'}));
    A.purpose=tg.length?`「${A.title}」 ${tg.map(a=>`${raLbl(a.no)}(${a.title})`).join('·')}의 내용을 정비하려는 것임.`:''; A.main=[];   // 주요 내용은 실제 수정안에서 만든다
    if(!raHasAi()) fin(s,'AI 키가 없어 대상 조문을 수정안 칸에 담았습니다. 결과 화면에서 문장을 고쳐 쓰면 대비표·문서가 바로 바뀝니다.','warn');
  }
  if(!raEffChanges().length){                // 아직 고친 곳이 없으면 점검·문서는 의미가 없다
    s=step('조문 고치기'); fin(s,'대상 조문을 수정안 칸에 담았습니다. 문장을 고친 뒤 확인·검토 단계로 넘어가세요.','warn');
    A.step=1; RA.agent.done={title:`「${A.title}」 개정 대상 조문을 준비했습니다`,sub:'결과 화면의 “고치기” 단계에서 조문 문장을 고치면 대비표·개정문·문서가 바로 만들어집니다.',
      acts:[['고치기 단계 열기',"RA.amend.step=1;raTab('amend')",1]]};
    return;
  }
  s=step('인용 영향 분석');
  const nos=A.changes.filter(c=>c.type!=='insert').map(c=>c.no);
  const im=await raPost('/api/regagent/impact',{slug:A.slug,nos,moves:{}});
  if(im.success){ A.impact=im; const m=im.summary;
    fin(s,`같은 ${_e(RA_ORG.reg_word)} 안 인용 ${m.inner}건 · 다른 ${_e(RA_ORG.reg_word)}의 조문 인용 ${m.outer}건 · ${_e(RA_ORG.reg_word)}명 인용 ${m.mention_regs}개`+
      (im.inner.length?'<br>'+[...new Set(im.inner.map(h=>`${raLbl(h.no)}에서 ${h.text} 인용`))].slice(0,3).map(_e).join(', '):''), (m.inner||m.outer)?'warn':'ok'); }
  else fin(s,_e(im.error||'분석 실패'),'warn');
  await raAgCheck('amend',step,fin);
  s=step('절차 판단'); fin(s,raAgProc(P.reg.category));
  s=step('문서 세트 준비'); fin(s,'개정문 · 개정 이유서 · 신구조문대비표 · 대국민 사전예고문 · 직원 의견수렴 공고 · 사전검토 의견서');
  RA.agent.done={title:`「${A.title}」 개정안이 준비됐습니다`,sub:'결과 화면에서 문장을 다듬고 한글·Word로 저장하세요.',
    acts:[['개정 결과 열기',"RA.amend.step=1;raTab('amend')",1],['문서 세트로 바로 가기',"raTab('amend');setTimeout(()=>raGoDoc('amend','cmp'),80)"]]};
}
async function raAgEnact(P, step, fin, stop){
  const E=RA.enact; raGenBump('enact');
  Object.assign(E,{step:2,title:P.title||'',purpose:P.purpose||'',contents:P.contents||'',dels:[],sim:null,refs:{},draft:null,lint:null,review:null,nota:null,ab:null,picks:null});
  E.category=raCatOf(E.title)||E.category||'규칙';
  let s=step('유사 규정 조사');
  const sm=await raPost('/api/regagent/similar',{query:[E.title,E.purpose,E.contents].join(' ').slice(0,600),limit:6});
  if(sm.success&&sm.regs.length){ E.sim={regs:sm.regs,semantic:sm.semantic,tokens:sm.tokens};
    sm.regs.slice(0,2).forEach(g=>g.articles.slice(0,2).forEach(a=>{ E.refs[g.slug+'|'+a.no]={reg:g.title,no:a.no,title:a.title,body:a.body}; }));
    fin(s,'참고 조문: '+Object.values(E.refs).map(r=>`「${_e(r.reg)}」 ${raLbl(r.no)}(${_e(r.title)})`).join(', ')); }
  else fin(s,'비슷한 조문을 찾지 못했습니다.','skip');
  Object.assign(E.refs, await raAgAlioStep('enact', raAlioGuess('enact')||E.title, [E.purpose,E.contents].join(' '), step, fin));
  s=step(raHasAi()?'조문 체계·초안 작성':'표준 조문 골격 작성');
  const d=await raPost('/api/regagent/draft',{mode:'enact',title:E.title,category:E.category,purpose:E.purpose,contents:E.contents,delegations:[],refs:Object.values(E.refs),...raAi()});
  if(!d.success) stop(s,d.error||'초안 작성 실패');
  const r=d.draft; if(r.title&&!E.title) E.title=r.title;
  E.draft={text:raDraftText(r.articles),addenda:(r.addenda||[]).join('\n'),purpose:(r.reason||{}).purpose||'',main:((r.reason||{}).main||[]).join('\n'),notes:r.notes||[],model:r.model||'',template:!!r.template,notice:d.notice||''};
  fin(s,`「${_e(E.title||'새 내규')}」 ${r.articles.length}개 조: `+r.articles.slice(0,8).map(a=>_e(a.title)).join(' · ')+(r.template?'<br>AI 키가 없어 표준 골격으로 작성했습니다.':''), r.template?'warn':'ok');
  await raAgCheck('enact',step,fin);
  s=step('절차 판단'); fin(s,raAgProc(E.category==='규정'?'규정':E.category));
  s=step('문서 세트 준비'); fin(s,'내규안 · 제정 이유서 · 신구조문대비표 · 대국민 사전예고문 · 직원 의견수렴 공고 · 사전검토 의견서');
  RA.agent.done={title:`「${E.title||'새 내규'}」 제정안이 준비됐습니다`,sub:'결과 화면에서 조문을 다듬고 문서 세트를 저장하세요.',
    acts:[['제정 결과 열기',"RA.enact.step=2;raTab('enact')",1],['문서 세트로 바로 가기',"raTab('enact');setTimeout(()=>raGoDoc('enact','law'),80)"]]};
}
async function raAgBulk(P, step, fin, stop){
  const U=RA.bulk; Object.assign(U,{old:P.old,neu:P.new,whole:true,res:null,sel:{},reason:''});
  let s=step(`모든 ${RA_ORG.reg_word}에서 “${P.old}” 찾기`);
  const d=await raPost('/api/regagent/bulk',{old:P.old,new:P.new,whole:true});
  if(!d.success) stop(s,d.error||'검색 실패');
  U.res=d; d.regs.forEach(g=>U.sel[g.slug]=true);
  if(!d.regs.length){ fin(s,`“${_e(P.old)}”${raEul(P.old)} 쓰는 ${_e(RA_ORG.reg_word)}가 없습니다.`,'skip'); RA.agent.done={title:'정비할 곳이 없습니다',sub:'다른 표현으로 다시 시도해 보세요.',acts:[]}; return; }
  fin(s,`${d.reg_count}개 ${_e(RA_ORG.reg_word)} · ${d.total}곳: `+d.regs.slice(0,5).map(g=>`「${_e(g.reg)}」 ${g.count}`).join(', ')+(d.regs.length>5?' 외':''));
  s=step('조사 교정·개정문 작성'); fin(s,_e(d.regs[0].amend_text).replace(/\n/g,'<br>')+(d.regs.length>1?`<br>… 외 ${d.regs.length-1}개 ${_e(RA_ORG.reg_word)}`:''));
  s=step('문서 세트 준비'); fin(s,'내규별 개정문 · “다른 내규의 개정” 부칙 · 통합 신구조문대비표 · 정비 이유서');
  RA.agent.done={title:`“${P.old}” → “${P.new}” 일괄 정비안이 준비됐습니다`,sub:`${d.reg_count}개 ${RA_ORG.reg_word}, ${d.total}곳`,acts:[['일괄 정비 결과 열기',"raTab('bulk')",1]]};
}
async function raAgUpper(P, step, fin, stop){
  const U=RA.upper; Object.assign(U,{law:P.law||'',arts:(P.arts||[]).join(', '),old:'',neu:'',res:null});
  let s=step(`「${P.law}」${raEul(P.law)} 인용하는 ${RA_ORG.reg_word} 찾기`);
  const d=await raPost('/api/regagent/upper',{law:U.law,arts:(P.arts||[]).map(raNormNo).filter(Boolean)});
  if(!d.success) stop(s,d.error||'분석 실패');
  U.res=d;
  if(!d.count){ fin(s,'인용하는 조문이 없습니다.','skip'); RA.agent.done={title:'영향받는 내규가 없습니다',sub:'',acts:[]}; return; }
  fin(s,`${d.reg_count}개 ${_e(RA_ORG.reg_word)} · ${d.count}개 조문 · 우선 검토 ${d.high}건`);
  const top=d.candidates.slice(0,3);
  s=step('개정 후보 선정');
  if(!d.high&&(P.arts||[]).length){                       // 개정된 조문을 직접 인용한 곳이 없으면 1순위를 정하지 않는다
    fin(s,`개정 조문(${_e((P.arts||[]).join(', '))})을 직접 인용한 곳은 없고, 법령명만 인용한 조문입니다.<br>`+top.map(c=>`「${_e(c.reg)}」 ${raLbl(c.no)}(${_e(c.title)})`).join('<br>'),'warn');
    RA.agent.done={title:`법령명을 인용한 ${d.count}개 조문을 찾았습니다`,sub:'개정된 조문을 직접 인용한 곳은 없습니다. 후보를 보고 반영할 곳을 고르세요.',acts:[['후보 전체 보기',"raTab('upper')",1]]};
    return;
  }
  fin(s,top.map(c=>`「${_e(c.reg)}」 ${raLbl(c.no)}(${_e(c.title)})${c.specific.length?' — '+_e(c.specific.join(', ')):''}`).join('<br>'), d.high?'warn':'ok');
  RA.agent.done={title:`개정 후보 ${d.count}개 조문을 찾았습니다`,sub:'1순위 후보로 바로 개정 작업을 시작할 수 있습니다.',
    acts:[['후보 전체 보기',"raTab('upper')",1],[`1순위 「${top[0].reg}」 ${raLbl(top[0].no)} 개정하기`,`raUpperToAmend('${_a(top[0].slug)}','${_a(top[0].no)}')`]]};
}

// ══════════════════════════════════════════════════════════════════════════
// 규정 건강검진 — 내규별 점수·등급·정비 우선순위, 상위법 최신성(법제처) 확인
// ══════════════════════════════════════════════════════════════════════════
const RA_GRADE={A:['양호','good'],B:['관심','good'],C:['주의','warning'],D:['경고','serious'],E:['위험','critical']};
async function raHealthLoad(){
  if(_raBusy.health) return; _raBusy.health=true;
  try{ await _raHealthLoad(); } finally{ _raBusy.health=false; }
}
async function _raHealthLoad(){
  const H=RA.health; const box=document.getElementById('raHealth'); if(box) box.innerHTML=raSpin(`${RA_ORG.reg_word} ${RA_ORG._count||''}건을 진단하는 중...`);
  const d=await raPost('/api/regagent/health',{law_info:H.law||{}});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'진단 실패'); return; }
  _raHealth=d; raRerender('health');
}
let _raHealth=null;
function raHealthLaws(){ return raOnce('healthLaws', _raHealthLaws); }
async function _raHealthLaws(){
  const H=RA.health; if(!_raHealth) return;
  H.law=H.law||{}; const old=Date.now()-7*864e5;
  let names=_raHealth.laws.filter(n=>!H.law[n]||!(H.law[n].at>old));
  if(!names.length) names=_raHealth.laws.slice();          // 모두 최근에 확인했어도 누르면 다시 확인한다
  const bar=document.getElementById('raLawProg'); let done=0, fail=0;
  for(let i=0;i<names.length;i+=6){
    const chunk=names.slice(i,i+6);
    if(bar) bar.innerHTML=`<div class="ra-prog"><i style="width:${Math.round((i)/names.length*100)}%"></i></div><div class="ra-meta">법제처에서 상위법 시행일 확인 중 ${i}/${names.length}</div>`;
    const d=await raPost('/api/regagent/health/laws',{names:chunk});
    if(!d.success){ if(bar) bar.innerHTML=raErr(d.error||'법령 조회 실패'); return; }
    Object.entries(d.laws).forEach(([k,v])=>{ if(v.error) fail++; else { H.law[k]={ef:v.ef,found:v.found,status:v.status,at:Date.now()}; done++; } });
  }
  _raSave(); _toast(`상위법 ${done}건 확인`+(fail?`, ${fail}건 실패(법제처 연결 확인)`:''),4500); raHealthLoad();
}
function raHealthView(){
  if(!_raHealth){ setTimeout(raHealthLoad,0); return `<div class="ra-wide" id="raHealth">${raSpin('진단 준비 중...')}</div>`; }
  const d=_raHealth, H=RA.health, f=H.f||{q:'',g:''};
  const gradeOf=s=>s>=95?'A':s>=85?'B':s>=75?'C':s>=60?'D':'E';
  const ag=gradeOf(d.avg);
  const lawN=Object.keys(H.law||{}).length;
  const tiles=`<div class="ra-kpis">`+
    `<div class="ra-kpi hero ra-kpi-ring">${raRing(d.avg,100,RA_GRADE[ag][1],d.avg,'/ 100')}<div><div class="ra-kpi-l">평균 건강 점수</div><div class="ra-kpi-big"><span class="ra-gr g-${RA_GRADE[ag][1]}">${ag}</span>${RA_GRADE[ag][0]}</div><div class="ra-kpi-s">${d.count}개 ${_e(RA_ORG.reg_word)} 진단</div></div></div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">문제가 발견된 ${_e(RA_ORG.reg_word)}</div><div class="ra-kpi-v">${d.with_issues}<small>건</small></div>${raMeter(d.with_issues/d.count,'serious')}<div class="ra-kpi-s">전체의 ${Math.round(d.with_issues/d.count*100)}%</div></div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">인용·명칭·번호 문제</div><div class="ra-kpi-v">${d.issue_total}<small>곳</small></div><div class="ra-kpi-s">오류가 있는 ${_e(RA_ORG.reg_word)} ${d.with_errors}건</div></div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">3년 이상 개정 없음</div><div class="ra-kpi-v">${d.old_regs}<small>건</small></div>${raMeter(d.old_regs/d.count,'warning')}<div class="ra-kpi-s">전체의 ${Math.round(d.old_regs/d.count*100)}%</div></div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">상위법 개정 미반영 의심</div><div class="ra-kpi-v">${lawN?d.stale_regs:'—'}<small>${lawN?'건':''}</small></div>${raMeter(lawN/Math.max(1,d.laws.length),'acc')}<div class="ra-kpi-s">${lawN?`법령 ${lawN}/${d.laws.length}개 확인`:'법제처 확인 전'}</div></div></div>`;
  const mx=Math.max(1,...Object.values(d.grades));
  const dist=`<div class="ra-dist" role="img" aria-label="등급 분포">`+'ABCDE'.split('').map(g=>{ const n=d.grades[g]||0;
    return `<button class="ra-dist-r${f.g===g?' on':''}" onclick="raHealthF('g','${g}')" title="${g}등급(${RA_GRADE[g][0]}) ${n}건 — 눌러서 목록 거르기"><span class="ra-dist-k"><span class="ra-gr g-${RA_GRADE[g][1]}">${g}</span>${RA_GRADE[g][0]}</span>`+
      `<span class="ra-dist-t"><i class="g-${RA_GRADE[g][1]}" style="width:${n?Math.max(2,n/mx*100):0}%"></i></span><span class="ra-dist-n">${n}</span></button>`; }).join('')+`</div>`;
  const top=d.rows.filter(r=>r.reasons.length).slice(0,10);
  const prio=top.length?`<ol class="ra-prio">`+top.map((r,i)=>`<li><span class="ra-prio-n">${i+1}</span><div class="ra-prio-b"><div class="ra-prio-t"><b>「${_e(r.title)}」</b><span class="ra-gr g-${RA_GRADE[r.grade][1]}">${r.grade}</span>${raMini(r.score,RA_GRADE[r.grade][1])}<span class="ra-prio-s">${r.score}점</span><span class="ra-sub">${_e(r.revision)}</span></div>`+
    `<div class="ra-prio-r">${r.reasons.map(x=>`<span class="ra-chip">${_e(x)}</span>`).join('')}</div>`+
    (r.stale_laws.length?`<div class="ra-snip">상위법: ${r.stale_laws.slice(0,3).map(l=>`「${_e(l.law)}」 ${l.ef.slice(0,4)}.${l.ef.slice(4,6)}.${l.ef.slice(6)} 시행`).join(', ')}</div>`:'')+
    `</div><div class="ra-prio-a"><button class="svc-btn sm" onclick="raCheckToAmend('${_a(r.slug)}','${_a(r.title)}')">개정 작업</button><a class="ra-link" href="${raRegUrl(r.slug)}" target="_blank" rel="noopener">원문↗</a></div></li>`).join('')+`</ol>`:'<div class="ra-ok">정비가 필요한 내규가 없습니다.</div>';
  const q=(f.q||'').replace(/\s+/g,'');
  const rows=d.rows.filter(r=>(!f.g||r.grade===f.g)&&(!q||r.title.replace(/\s+/g,'').includes(q)));
  const table=`<div class="ra-row"><input class="ra-in sm" style="max-width:220px" placeholder="${_e(RA_ORG.reg_word)}명 검색" value="${_e(f.q||'')}" oninput="raHealthF('q',this.value)">`+
    (f.g?`<button class="ra-chip btn" onclick="raHealthF('g','')">${f.g}등급만 보는 중 ✕</button>`:'')+`<span class="ra-hint">${rows.length}건</span></div>`+
    `<div class="ra-tbl-w"><table class="ra-tbl"><thead><tr><th>${_e(RA_ORG.reg_word)}</th><th>등급</th><th>점수</th><th>최종 개정</th><th>진단</th></tr></thead><tbody>`+
    rows.map(r=>`<tr><td><a class="ra-link" href="${raRegUrl(r.slug)}" target="_blank" rel="noopener">${_e(r.title)}</a><div class="ra-sub">${_e(r.category)} · ${r.n_articles}개 조 · 인용 법령 ${r.laws.length}</div></td>`+
      `<td><span class="ra-gr g-${RA_GRADE[r.grade][1]}">${r.grade}</span></td><td class="num"><span class="ra-sc">${raMini(r.score,RA_GRADE[r.grade][1])}${r.score}</span></td><td>${_e(r.revision)}</td><td>${r.reasons.map(x=>_e(x)).join(', ')||'<span class="ra-mu">이상 없음</span>'}</td></tr>`).join('')+`</tbody></table></div>`;
  const rule=d.rules?`<details class="ra-det"><summary>점수 기준</summary><div class="ra-hint">100점에서 감점: 없는 조문 인용 건당 -10(최대 -30) · 조 번호 중복·순서 오류 -8 · 현행 목록에 없는 내규명 인용 -6 · 옛 기관명·직위 -5 · 개정 경과 ${_e(d.rules.age)} · ${_e(d.rules.law)}<br>등급: A 95점 이상(양호) · B 85(관심) · C 75(주의) · D 60(경고) · E 60점 미만(위험)</div></details>`:'';
  const lawSec=`<div class="ra-row"><button class="svc-btn" onclick="raHealthLaws()">${raIc('upper')}상위법 최신성 확인</button>${raTip(`${_e(RA_ORG.reg_word)}가 인용한 법령 ${d.laws.length}개의 현행 시행일을 법제처에서 조회해, ${_e(RA_ORG.reg_word)} 개정일보다 나중에 시행된 법령을 찾습니다.${lawN?` (확인 ${lawN}개)`:''}`)}</div><div id="raLawProg"></div>`+
    raStats([{v:d.laws.length,l:'인용 법령',ic:'upper',tone:'acc'},{v:lawN,l:'시행일 확인',ic:'check',tone:lawN?'ok':'n'},{v:lawN?d.stale_regs:'—',l:'미반영 의심 내규',ic:'alert',tone:lawN&&d.stale_regs?'warn':'n'}])+
    raMeter(lawN/Math.max(1,d.laws.length),'acc')+`<div class="ra-meta" style="margin-top:6px">법제처 확인 ${Math.round(lawN/Math.max(1,d.laws.length)*100)}%</div>`;
  return `<div class="ra-wide" id="raHealth">${tiles}`+
    `<div class="ra-grid2 ra-h2">${raSec(1,'등급 분포',raTip('막대를 누르면 아래 목록을 거릅니다'),dist+rule)}${raSec(2,'상위법 최신성','법제처 현행 법령 기준',lawSec)}</div>`+
    raSec(3,'정비 우선순위 Top 10','점수 낮은 순',prio)+
    raSec(4,`전체 ${_e(RA_ORG.reg_word)} 진단표`,'',table)+
    raSec(5,'유관 기관 규정 체계 비교',raTip('알리오에 공시된 유관 기관(같은 주무부처 등)의 내부규정 목록과 우리 기관 내규를 견줍니다. 여러 기관이 두고 있는데 우리에게 없는 규정은 제정을 검토할 만합니다.'),`<div id="raBench">${raBenchView()}</div>`)+
    `<div class="ra-foot"><button class="svc-btn ghost sm" onclick="_raHealth=null;raHealthLoad()">다시 진단</button></div></div>`;
}
function raMeter(p, tone){ return `<div class="ra-meter"><i class="t-${tone}" style="width:${Math.round(Math.max(0,Math.min(1,p||0))*100)}%"></i></div>`; }
function raMini(v, tone){ return `<span class="ra-mini" aria-hidden="true"><i class="t-${tone}" style="width:${Math.max(0,Math.min(100,v))}%"></i></span>`; }
function raHealthF(k,v){ const H=RA.health; H.f=H.f||{q:'',g:''}; H.f[k]=(k==='g'&&H.f.g===v)?'':v; _raSave();
  if(k==='q'){ clearTimeout(raHealthF._t); raHealthF._t=setTimeout(()=>{ const y=window.scrollY; raRerender('health'); window.scrollTo(0,y); const i=document.querySelector('#raHealth .ra-tbl-w')?.previousElementSibling?.querySelector('input'); if(i){ i.focus(); i.setSelectionRange(i.value.length,i.value.length); } },250); }
  else { const y=window.scrollY; raRerender('health'); window.scrollTo(0,y); } }

// ══════════════════════════════════════════════════════════════════════════
// 일괄 정비 — 기관명·직위·부서명·내규명이 바뀌면 모든 내규에서 찾아 바꾸고(조사 교정),
// 내규별 개정문·“다른 내규의 개정” 부칙·통합 신구조문대비표를 만든다
// ══════════════════════════════════════════════════════════════════════════
function raBulkView(){
  const U=RA.bulk;
  const form=`<div class="ra-grid2"><label class="ra-f"><span>바뀌기 전 용어</span>${raIn('bulk.old',U.old,'예) 경영지원팀 · 이사장 · 위임전결규정')}</label>`+
    `<label class="ra-f"><span>바뀐 뒤 용어</span>${raIn('bulk.neu',U.neu,'예) 경영관리팀 · 원장 · 위임전결규칙')}</label></div>`+
    `<label class="ra-chk"><input type="checkbox" ${U.whole!==false?'checked':''} onchange="raSet('bulk.whole',this.checked)"> 낱말 단위로만 ${raTip('다른 낱말의 일부는 제외 — 예: “원장”을 바꿀 때 “부원장”은 그대로')}</label>`+
    `<label class="ra-f" style="margin-top:8px"><span>정비 사유 ${raTip('개정 이유서에 들어갑니다')}</span>${raTa('bulk.reason',U.reason,'예) 「직제규정」 개정(2026. 1. 1.)으로 부서 명칭이 바뀜에 따라 관련 내규를 일괄 정비하려는 것임.',2)}</label>`+
    `<div class="ra-row"><button class="svc-btn yes" onclick="raBulkRun()">${raIc('search')}영향 내규 찾기</button>${raTip(`직제 개편·기관명 변경·내규명 변경 때 모든 ${_e(RA_ORG.reg_word)}를 한 번에 정비합니다. 뒤따르는 조사(은/는·이/가·을/를·으로/로)도 맞춰 고칩니다.`)}</div>`;
  return `<div class="ra-wide">${raSec(1,'바뀐 용어·명칭','',form)}${raSec(2,'정비 대상',raTip('체크한 내규만 문서에 넣습니다'),`<div id="raBulk">${raBulkResView()}</div>`)}`+
    (U.res&&U.res.regs.length?raSec(3,'문서 세트','',raBulkDocsView(),'raSecDocs'):'')+`</div>`;
}
function raBulkRun(){ return raOnce('bulk', _raBulkRun); }
async function _raBulkRun(){
  const U=RA.bulk; if(!U.old.trim()||!U.neu.trim()){ _toast('바뀌기 전·후 용어를 입력하세요.'); return; }
  const box=document.getElementById('raBulk'); if(box) box.innerHTML=raSpin(`모든 ${RA_ORG.reg_word}에서 찾는 중...`);
  const d=await raPost('/api/regagent/bulk',{old:U.old, new:U.neu, whole:U.whole!==false, ...(U.only&&U.only.length?{slugs:U.only}:{})});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'검색 실패'); return; }
  U.res=d; U.sel={}; d.regs.forEach(g=>U.sel[g.slug]=true); U.docTab=U.docTab||'amend'; _raSave(); raRerender('bulk');
}
function raBulkSel(slug,on){ RA.bulk.sel[slug]=on; _raSave(); raBulkDocsRedraw(); }
function raBulkSelAll(on){ Object.keys(RA.bulk.sel).forEach(k=>RA.bulk.sel[k]=on); _raSave(); document.querySelectorAll('.ra-detg input[type=checkbox]').forEach(x=>{ x.checked=on; }); raBulkDocsRedraw(); }
function raBulkDocsRedraw(){ const b=document.querySelector('#raSecDocs .ra-sec-b'); if(b) b.innerHTML=raBulkDocsView(); else raRerender('bulk'); }
function raBulkResView(){
  const R=RA.bulk.res; if(!R) return `<div class="ra-empty sm">${raIc('bulk')}용어를 넣고 “영향 내규 찾기”</div>`;
  if(!R.regs.length) return `<div class="ra-ok">“${_e(R.old)}”${raEul(R.old)} 쓰는 ${_e(RA_ORG.reg_word)} 조문이 없습니다.</div>`;
  const sel=RA.bulk.sel||{};
  const nsel=R.regs.filter(g=>sel[g.slug]).length;
  return `<div class="ra-split"><div><div class="ra-swap"><span class="ra-swap-o">${_e(R.old)}</span>${raIc('arrow')}<span class="ra-swap-n">${_e(R.new)}</span></div>`+
    raStats([{v:R.reg_count,l:`개 ${RA_ORG.reg_word}`,ic:'doc',tone:'acc'},{v:R.total,l:'곳 수정',ic:'amend',tone:'acc'},{v:nsel,l:'문서에 포함',ic:'check',tone:nsel?'ok':'n'}])+`</div><div>`+
    raBars(R.regs.slice(0,8).map(g=>({l:g.reg,n:g.count})),'곳','내규별 수정 위치 수')+(R.regs.length>8?`<div class="ra-meta">외 ${R.regs.length-8}개 ${_e(RA_ORG.reg_word)}</div>`:'')+`</div></div>`+
    `<div class="ra-meta"><button class="ra-link" onclick="raBulkSelAll(true)">모두 선택</button><button class="ra-link" onclick="raBulkSelAll(false)">모두 해제</button></div>`+
    `<div class="ra-detg">`+R.regs.map(g=>`<details class="ra-det"><summary><label onclick="event.stopPropagation()"><input type="checkbox" ${sel[g.slug]?'checked':''} onchange="raBulkSel('${_a(g.slug)}',this.checked)"></label> <b>「${_e(g.reg)}」</b> <span class="ra-chip">${g.count}곳</span> <a class="ra-link" href="${raRegUrl(g.slug)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">원문↗</a></summary>`+
      `<div class="ra-note mono">${_e(g.amend_text).replace(/\n/g,'<br>')}</div>`+
      g.articles.map(a=>{ const [o,n]=raWordDiff(a.old_body,a.new_body); return `<div class="ra-fixrow"><b>${_e(raLbl(a.no))}(${_e(a.title)})</b> <span class="ra-sub">${_e(a.locs.join(', '))}</span><div class="ra-fixd"><div>${o.replace(/\n/g,'<br>')}</div><div>${n.replace(/\n/g,'<br>')}</div></div></div>`; }).join('')+`</details>`).join('')+`</div>`;
}
const RA_BULK_DOCS=[['amend','내규별 개정문'],['addenda','“다른 내규의 개정” 부칙'],['cmp','통합 신구조문대비표'],['reason','정비 이유서']];
function raBulkDocs(){
  const U=RA.bulk, R=U.res, regs=R.regs.filter(g=>U.sel[g.slug]);
  const amend=regs.map(g=>g.amend_text).join('\n\n');
  const addenda=`제○조(다른 ${RA_ORG.reg_word}의 개정) `+(regs.length===1?regs[0].amend_text:regs.map((g,i)=>`${RA_HANG[i]||(i+1)+'.'} ${g.amend_text.replace('\n','\n   ')}`).join('\n'));
  const reason=[`${RA_ORG.reg_word} 일괄 정비 이유서`,'','1. 정비 이유',`  ${U.reason||`“${R.old}”${raJosa(R.old,['이','가'])} “${R.new}”${raRo(R.new)} 바뀜에 따라 이를 인용하는 ${RA_ORG.reg_word}를 일괄 정비하려는 것임.`}`,'',
    '2. 정비 대상',...regs.map((g,i)=>`  ${'가나다라마바사아자차카타파하'[i]||'-'}. 「${g.reg}」 ${g.articles.map(a=>raLbl(a.no)).join(', ')} (${g.count}곳)`),'',
    '3. 정비 방식',`  각 ${RA_ORG.reg_word}의 해당 조문 중 “${R.old}”${raEul(R.old)} “${R.new}”${raRo(R.new)} 고침(조사 포함). 근거 ${RA_ORG.reg_word} 개정 시 부칙 “다른 ${RA_ORG.reg_word}의 개정”으로 함께 개정하거나 각 ${RA_ORG.reg_word}별로 개정함.`,'',
    `4. 관련: 「${raRules()}」 제16조제1항(법령·상위 내규 변경에 따른 개폐는 심의 생략 가능)`].join('\n');
  const cmp=[]; regs.forEach(g=>{ cmp.push({reg:g.reg}); g.articles.forEach(a=>{ const o={no:a.no,title:a.title,body:a.old_body}, n={no:a.no,title:a.new_title||a.title,body:a.new_body}; cmp.push(raCmpCell(o,n,true)); }); });
  return {regs, amend, addenda, reason, cmp};
}
function raBulkDocsView(){
  const U=RA.bulk, tab=U.docTab||'amend', D=raBulkDocs();
  if(!D.regs.length) return '<div class="ra-empty">정비할 내규를 체크하세요.</div>';
  const tabs=RA_BULK_DOCS.map(([k,l])=>`<button class="ra-dtab${tab===k?' on':''}" onclick="raSet('bulk.docTab','${k}');raRerender('bulk')">${raIc(RA_DOC_IC[k]||'doc')}${l}</button>`).join('');
  const body=tab==='cmp'?`<table class="ra-cmp"><thead><tr><th>현 행</th><th>개 정 안</th></tr></thead><tbody>${D.cmp.map(r=>r.reg?`<tr><td colspan="2" class="ra-cmp-reg">「${_e(r.reg)}」</td></tr>`:`<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('')}</tbody></table>`:`<pre class="ra-doc">${_e(D[tab])}</pre>`;
  return `<div class="ra-dtabs">${tabs}</div><div class="ra-docbox">${body}</div><div class="ra-row"><button class="svc-btn" onclick="raBulkCopy()">복사</button><span class="ra-sep"></span>`+
    `<button class="svc-btn yes" onclick="raBulkExport('hwpx')">한글(.hwpx)로 저장</button><button class="svc-btn" onclick="raBulkExport('docx')">Word(.docx)로 저장</button></div>`;
}
function raBulkCopy(){ const D=raBulkDocs(), tab=RA.bulk.docTab||'amend'; _copyText(tab==='cmp'?D.cmp.map(r=>r.reg?`■ 「${r.reg}」`:`[현행]\n${r[2]}\n[개정안]\n${r[3]}`).join('\n\n'):D[tab], ()=>_toast('복사했습니다.')); }
function raBulkExport(fmt){
  const D=raBulkDocs(), R=RA.bulk.res; if(!D.regs.length){ _toast('정비할 내규를 체크하세요.'); return; }
  const rows=[[{t:'현 행',hd:1},{t:'개 정 안',hd:1}]]; D.cmp.forEach(r=>rows.push(r.reg?[{t:`「${r.reg}」`,cs:2,hd:1}]:[{t:r[2],r:raHtmlRuns(r[0])},{t:r[3],r:raHtmlRuns(r[1])}]));
  const blocks=[{t:'p',text:D.reason,titleBold:1},{t:'break'},{t:'p',text:D.amend,titleBold:1},{t:'break'},{t:'p',text:D.addenda,titleBold:1},{t:'break'},{t:'p',text:`“${R.old}” → “${R.new}” 일괄 정비 신구조문대비표`,titleBold:1},{t:'table',colWidths:[23814,23814],rows}];
  raSaveFile(fmt, `일괄정비_${R.old}→${R.new}`.replace(/[\\/:*?"<>|→]/g,'_'), blocks, '일괄 정비 문서');
}

// ══════════════════════════════════════════════════════════════════════════
// 상위법 영향
// ══════════════════════════════════════════════════════════════════════════
function raUpperView(){
  const U=RA.upper;
  const form=`<div class="ra-grid2"><label class="ra-f"><span>상위 법령명</span>${raIn('upper.law',U.law,'예) 공공기관의 운영에 관한 법률')}</label>`+
    `<label class="ra-f"><span>개정된 조문 ${raTip('쉼표로 구분(선택)')}</span>${raIn('upper.arts',U.arts,'예) 제31조, 제32조의2')}</label></div>`+
    `<div class="ra-grid2"><label class="ra-f"><span>개정 전 조문 ${raTip('선택 — 바뀐 용어를 찾아 영향 조문을 넓힙니다')}</span>${raTa('upper.old',U.old,'개정 전 조문을 붙여 넣으세요',4)}</label>`+
    `<label class="ra-f"><span>개정 후 조문</span>${raTa('upper.neu',U.neu,'개정 후 조문을 붙여 넣으세요',4)}</label></div>`+
    `<div class="ra-row"><button class="svc-btn yes" onclick="raUpperRun()">${raIc('search')}영향 조문 찾기</button>${raTip(`기관 내규 전체에서 이 법령(시행령·시행규칙 포함)을 인용하는 조문을 찾아 개정 후보로 보여 줍니다.`)}</div>`;
  return `<div class="ra-wide">${raSec(1,'상위법 개정 내용','',form)}${raSec(2,'개정 후보 조문','',`<div id="raUpper">${raUpperResView()}</div>`)}</div>`;
}
async function raUpperRun(){
  const U=RA.upper; if(!U.law.trim()){ _toast('상위 법령명을 입력하세요.'); return; }
  const box=document.getElementById('raUpper'); if(box) box.innerHTML=raSpin('내규 전체에서 인용 조문을 찾는 중...');
  const arts=raArtList(U.arts);
  const d=await raPost('/api/regagent/upper',{law:U.law, arts, old:U.old, new:U.neu});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'분석 실패'); return; }
  U.res=d; _raSave(); if(box) box.innerHTML=raUpperResView();
}
function raUpperResView(){
  const R=RA.upper.res; if(!R) return `<div class="ra-empty sm">${raIc('upper')}법령명을 넣고 “영향 조문 찾기”</div>`;
  if(!R.count) return `<div class="ra-ok">「${_e(R.law)}」${raEul(R.law)} 인용하는 내규 조문이 없습니다.</div>`;
  const groups={}; R.candidates.forEach(c=>{ (groups[c.reg]=groups[c.reg]||{slug:c.slug,items:[]}).items.push(c); });
  const gl=Object.entries(groups).map(([reg,g])=>{ const hi=g.items.filter(c=>c.specific.length||c.terms.length).length; return {l:reg,parts:[{n:hi,tone:'bad',l:'우선 검토'},{n:g.items.length-hi,tone:'acc',l:'인용'}]}; });
  return `<div class="ra-split"><div>`+raStats([{v:R.count,l:'인용 조문',ic:'doc',tone:'acc'},{v:R.reg_count,l:`개 ${RA_ORG.reg_word}`,ic:'bulk',tone:'acc'},{v:R.high,l:'우선 검토',ic:'alert',tone:R.high?'bad':'ok',tip:'개정된 조문을 직접 인용하거나 바뀐 용어를 쓰는 조문'}])+
    raStack([{n:R.high,l:'우선 검토',tone:'bad'},{n:R.count-R.high,l:'법령명만 인용',tone:'acc'}],'후보 구성')+
    `</div><div>`+(gl.length>1?raBars(gl.slice(0,8),'','내규별 개정 후보'):'')+`</div></div>`+
    (R.removed_terms.length?`<div class="ra-meta">바뀐 용어 ${R.removed_terms.map(t=>`<span class="ra-chip warn">${_e(t)}</span>`).join('')}</div>`:'')+
    `<div class="ra-detg">`+Object.entries(groups).map(([reg,g])=>`<div class="ra-simc"><div class="ra-simc-h"><b>「${_e(reg)}」</b><span class="ra-sub">${g.items.length}개 조문</span><a class="ra-link" href="${raRegUrl(g.slug)}" target="_blank" rel="noopener">원문↗</a></div>`+
      g.items.map(c=>`<div class="ra-cand${(c.specific.length||c.terms.length)?' hi':''}"><div><b>${_e(raLbl(c.no))}(${_e(c.title)})</b> `+
        `${c.specific.map(s=>`<span class="ra-chip hi">${_e(s)}</span>`).join('')}${c.terms.map(s=>`<span class="ra-chip warn">용어: ${_e(s)}</span>`).join('')}${!c.specific.length&&!c.terms.length?c.cites.slice(0,2).map(s=>`<span class="ra-chip">${_e(s)}</span>`).join(''):''}`+
        `<button class="svc-btn sm" style="margin:0 0 0 6px" onclick="raUpperToAmend('${_a(c.slug)}','${_a(c.no)}')">${raIc('amend')}개정</button></div><div class="ra-snip">${_e(c.snippet)}</div></div>`).join('')+`</div>`).join('')+`</div>`;
}
function raAmendStart(slug, title, o){
  o=o||{}; const A=RA.amend;
  if(A.slug!==slug||o.fresh){ raGenBump('amend'); const keep={abbr:A.abbr, lawStyle:A.lawStyle};
    RA.amend=Object.assign(_raBlank().amend, keep, {src:'reg', slug, title}); }
  const B=RA.amend;
  (o.sel||[]).forEach(no=>{ if(no) B.sel[no]=true; });
  if(o.intent&&(!B.intent||o.force)) B.intent=o.intent;
  if(o.refText!=null) B.refText=o.refText;
  if(o.sel||o.intent) B.step=o.intent&&(o.sel||[]).length?1:0;          // 넘겨받은 조문·의도가 보이는 단계로
  _raArts=null; RA.tab='amend'; _raSave(); openRegAgent();
}
// “제31조 제2항, 32조의2” → ['31','32의2'] (항·호 번호는 버린다). 조 표기가 없으면 쉼표로 나눈 숫자만
function raArtList(t){
  const s=String(t||''); const m=s.match(/제?\s*\d+\s*조(?:\s*의\s*\d+)?/g);
  return [...new Set((m||s.split(/[,，\s]+/).filter(x=>/^제?\d+(?:의\d+)?$/.test(x))).map(raNormNo).filter(Boolean))];
}
function raUpperToAmend(slug, no){
  const U=RA.upper;
  const reg=(U.res.candidates.find(c=>c.slug===slug)||{}).reg||'';
  const arts=U.arts?` ${U.arts}`:'';
  raAmendStart(slug, reg, {sel:[no], force:true, intent:`상위법 「${U.law}」${arts} 개정 내용을 반영하여 인용 조문과 관련 내용을 정비`,
    refText:[U.old?`[개정 전] ${U.old}`:'', U.neu?`[개정 후] ${U.neu}`:''].filter(Boolean).join('\n').slice(0,3000)});
}

// ══════════════════════════════════════════════════════════════════════════
// 전체 점검
// ══════════════════════════════════════════════════════════════════════════
function raCheckView(){
  const C=RA.check;
  const one=`<div class="ra-row"><input id="raChkReg" class="ra-in" list="raRegList" style="max-width:320px" placeholder="내규명 (예: 인사규정)" value="${_e(C.reg||'')}" onkeydown="if(event.key==='Enter')raCheckOne()"><datalist id="raRegList"></datalist><button class="svc-btn" onclick="raCheckOne()">이 내규 점검</button></div><div id="raChkOne">${C.one?raCheckOneView(C.one):''}</div>`;
  const all=`<div class="ra-row"><button class="svc-btn yes" onclick="raCheckAll()">${raIc('check')}기관 내규 전체 점검</button>${raTip(`모든 내규에서 없는 조문 인용·현행 목록에 없는 내규명·구 명칭(재단·이사장 등)·조 번호 중복을 찾습니다.`)}</div>`;
  return `<div class="ra-wide">${raPair(raSec(1,'전체 점검','',all),raSec(2,'내규 하나 자세히 점검',raTip('항·호 순서, 표기, 부칙, 별표 인용까지'),one))}<div id="raChkAll">${raCheckAllView()}</div></div>`;
}
function raCheckAll(){ return raOnce('checkAll', _raCheckAll); }
async function _raCheckAll(){
  const box=document.getElementById('raChkAll'); if(box) box.innerHTML=raSpin('기관 내규 전체를 점검하는 중...');
  const d=await raPost('/api/regagent/lint',{all:true});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'점검 실패'); return; }
  RA.check.res=d; _raSave(); if(box) box.innerHTML=raCheckAllView();
}
function raCheckAllView(){
  const R=RA.check.res; if(!R) return '';
  const ok=Math.max(0,R.checked-R.regs.length);
  const top=[...R.regs].sort((x,y)=>(y.errors-x.errors)||(y.count-x.count)).slice(0,10);
  return raSec(3,'전체 점검 결과','',raStats([{v:R.checked,l:'점검한 내규',ic:'doc',tone:'acc'},{v:R.regs.length,l:'문제 있는 내규',ic:'alert',tone:R.regs.length?'warn':'ok'},{v:R.total.error||0,l:'오류',ic:'bad',tone:(R.total.error||0)?'bad':'ok'},{v:R.total.warn||0,l:'주의',ic:'alert',tone:(R.total.warn||0)?'warn':'ok'}])+
    `<div class="ra-grid2 ra-chk2"><div><div class="ra-ih">내규 상태</div>${raStack([{n:ok,l:'이상 없음',tone:'ok'},{n:R.regs.filter(r=>!r.errors).length,l:'주의만',tone:'warn'},{n:R.regs.filter(r=>r.errors).length,l:'오류 있음',tone:'bad'}],'내규 상태')}</div>`+
    `<div><div class="ra-ih">문제가 많은 내규 Top ${top.length}</div>${raBars(top.map(r=>({l:r.reg,parts:[{n:r.errors||0,tone:'bad',l:'오류'},{n:Math.max(0,r.count-(r.errors||0)),tone:'warn',l:'주의·제안'}]})),'건','내규별 문제 수')}</div></div>`+
    `<div class="ra-detg">`+R.regs.map(r=>`<details class="ra-det"${r.errors?' open':''}><summary><b>「${_e(r.reg)}」</b> ${r.errors?`<span class="ra-chip hi">오류 ${r.errors}</span>`:''}<span class="ra-chip">${r.count}건</span> <a class="ra-link" href="${raRegUrl(r.slug)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">원문↗</a> <button class="ra-link" onclick="event.preventDefault();raCheckToAmend('${_a(r.slug)}','${_a(r.reg)}')">개정 →</button></summary>${raLintView(r.issues,null,true)}</details>`).join('')+`</div>`);
}
async function raCheckOne(){
  const v=((document.getElementById('raChkReg')||{}).value||'').trim(); if(!v){ _toast('내규명을 입력하세요.'); return; }
  RA.check.reg=v; const box=document.getElementById('raChkOne'); if(box) box.innerHTML=raSpin('점검 중...');
  const d=await raPost('/api/regagent/lint',{reg:v});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'점검 실패'); return; }
  RA.check.one=d; _raSave(); if(box) box.innerHTML=raCheckOneView(d);
}
function raCheckOneView(d){ return `<div class="ra-ih">「${_e(d.reg)}」</div>`+raLintView(d.issues)+
  ((d.issues||[]).length?`<div class="ra-row"><button class="svc-btn sm" onclick="raCheckToAmend('${_a(d.slug||'')}','${_a(d.reg||'')}')">${raIc('amend')}지적된 조문으로 개정 작업</button></div>`:''); }
// 점검·건강검진·인용 관계 → 개정: 지적된 조문을 미리 체크하고 개정 의도를 채운다
function raCheckToAmend(slug, title){
  const pools=[...((_raHealth&&_raHealth.rows)||[]), ...((RA.check.res&&RA.check.res.regs)||[])];
  let iss=(pools.find(x=>x.slug===slug)||{}).issues||[];
  if(!iss.length&&RA.check.one&&RA.check.one.reg===title) iss=RA.check.one.issues||[];
  iss=iss.filter(i=>i.level!=='info');
  const nos=[...new Set(iss.map(i=>raNormNo(i.no)).filter(Boolean))].slice(0,12);
  const kinds=[...new Set(iss.map(i=>({ref:'없는 조문 인용',dup:'조 번호 중복',order:'조 번호 순서',regname:'내규 명칭',stale:'구 명칭',gap:'결번',title:'조 제목',hang:'항 번호',ho:'호 번호',addenda:'부칙'})[i.code]).filter(Boolean))];
  raAmendStart(slug, title, {sel:nos, intent:kinds.length?`점검 결과 정비: ${kinds.slice(0,4).join('·')}`:''});
}

// ══════════════════════════════════════════════════════════════════════════
// 인용 관계망 — 「내규명」 인용으로 이어진 내규 관계. 많이 인용되는 내규(개정 시 파급 큼)·옛 명칭 인용을 찾는다
// ══════════════════════════════════════════════════════════════════════════
const RA_CAT_ORDER=['정관','규정','규칙','세칙','예규','매뉴얼'];
const RA_CAT_COLOR={'정관':'#c2410c','규정':'#2a78d6','규칙':'#0f8a7a','세칙':'#7c5cd6','예규':'#b7791f','매뉴얼':'#8a93a3'};
let _raGraph=null;
async function raGraphLoad(){
  if(_raBusy.graph) return; _raBusy.graph=true;
  try{ await _raGraphLoad(); } finally{ _raBusy.graph=false; }
}
async function _raGraphLoad(){
  const box=document.getElementById('raGraph'); if(box) box.innerHTML=raSpin('내규 사이의 인용 관계를 분석하는 중...');
  const d=await raGet('/api/regagent/graph');
  if(!d||!d.success){ if(box) box.innerHTML=raErr((d&&d.error)||'분석 실패'); return; }
  const order=n=>{ const i=RA_CAT_ORDER.indexOf(n.category); return i<0?RA_CAT_ORDER.length:i; };
  d.nodes.forEach((n,i)=>{ n.i=i; n.cites=[]; n.citedBy=[]; });
  d.edges.forEach(e=>{ d.nodes[e.s].cites.push({j:e.t,n:e.n}); d.nodes[e.t].citedBy.push({j:e.s,n:e.n}); });
  d.ring=[...d.nodes].sort((a,b)=>order(a)-order(b)||a.title.localeCompare(b.title,'ko'));
  _raGraph=d;
  const G=RA.graph=RA.graph||{sel:''};
  if(!d.nodes.some(n=>n.slug===G.sel)){ const hub=[...d.nodes].sort((a,b)=>b.in-a.in)[0]; G.sel=hub?hub.slug:''; }
  raRerender('graph');
}
function raGraphSel(slug){ RA.graph=RA.graph||{}; RA.graph.sel=slug; _raSave(); const y=window.scrollY; raRerender('graph'); window.scrollTo(0,y); }
// 원형 배치: 범주별로 묶어 원 둘레에 놓고, 인용은 원 안쪽 곡선으로 잇는다
function raGraphSvg(d, sel){
  const W=640, C=W/2, R=250, N=d.ring.length||1;
  const pos={}; d.ring.forEach((n,k)=>{ const a=k/N*2*Math.PI-Math.PI/2; pos[n.i]={x:C+R*Math.cos(a),y:C+R*Math.sin(a),a}; });
  const S=sel?d.nodes.find(n=>n.slug===sel):null;
  const nb=new Set(S?[S.i,...S.cites.map(x=>x.j),...S.citedBy.map(x=>x.j)]:[]);
  const curve=(a,b)=>{ const p=pos[a], q=pos[b]; return `M${p.x.toFixed(1)},${p.y.toFixed(1)} Q${C},${C} ${q.x.toFixed(1)},${q.y.toFixed(1)}`; };
  const base=d.edges.filter(e=>!S||(e.s!==S.i&&e.t!==S.i)).map(e=>`<path d="${curve(e.s,e.t)}" class="ra-gl"/>`).join('');
  const hiIn=S?S.citedBy.map(x=>`<path d="${curve(x.j,S.i)}" class="ra-gl in"><title>${_e(d.nodes[x.j].title)} → ${_e(S.title)}</title></path>`).join(''):'';
  const hiOut=S?S.cites.map(x=>`<path d="${curve(S.i,x.j)}" class="ra-gl out"><title>${_e(S.title)} → ${_e(d.nodes[x.j].title)}</title></path>`).join(''):'';
  const dots=d.ring.map(n=>{ const p=pos[n.i], r=2.6+Math.sqrt(n.in)*1.5, on=S&&n.i===S.i, dim=S&&!nb.has(n.i);
    return `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${r.toFixed(1)}" fill="${RA_CAT_COLOR[n.category]||'#8a93a3'}" class="ra-gn${on?' on':''}${dim?' dim':''}" tabindex="0" role="button" aria-label="${_e(n.title)} — 인용받음 ${n.in}, 인용함 ${n.out}" onclick="raGraphSel('${_a(n.slug)}')" onkeydown="if(event.key==='Enter')raGraphSel('${_a(n.slug)}')"><title>${_e(n.title)} (${_e(n.category)}) — 인용받음 ${n.in} · 인용함 ${n.out}</title></circle>`; }).join('');
  // 이름표: 많이 인용되는 내규와 선택한 내규·이웃만(겹침 방지)
  const lab=d.ring.filter(n=>(S&&nb.has(n.i)&&(n.i===S.i||nb.size<=14))||(!S||!nb.has(n.i))&&n.in>=8).map(n=>{ const p=pos[n.i], right=Math.cos(p.a)>=0, lx=C+(R+12)*Math.cos(p.a), ly=C+(R+12)*Math.sin(p.a);
    const deg=p.a*180/Math.PI+(right?0:180); const t=n.title.length>14?n.title.slice(0,13)+'…':n.title;
    return `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" transform="rotate(${deg.toFixed(1)} ${lx.toFixed(1)} ${ly.toFixed(1)})" text-anchor="${right?'start':'end'}" dominant-baseline="middle" class="ra-gt${S&&n.i===S.i?' on':''}">${_e(t)}</text>`; }).join('');
  return `<svg class="ra-gsvg" viewBox="-96 -40 ${W+192} ${W+80}" role="img" aria-label="내규 인용 관계도: 내규 ${d.nodes.length}개, 인용 관계 ${d.edges.length}개">${base}${hiIn}${hiOut}${dots}${lab}</svg>`;
}
function raGraphPanel(d, sel){
  const S=d.nodes.find(n=>n.slug===sel); if(!S) return '<div class="ra-empty sm">관계도에서 내규를 고르세요</div>';
  const li=(arr,dir)=>arr.length?`<ul class="ra-gp-l">`+[...arr].sort((a,b)=>b.n-a.n).map(x=>{ const n=d.nodes[x.j];
    return `<li><button class="ra-link" onclick="raGraphSel('${_a(n.slug)}')">「${_e(n.title)}」</button>${x.n>1?`<span class="ra-chip">${x.n}회</span>`:''}</li>`; }).join('')+`</ul>`:`<div class="ra-mu ra-gp-0">${dir}</div>`;
  const brk=d.broken.filter(b=>b.from===S.slug);
  return `<div class="ra-gp-h"><span class="ra-gdot" style="background:${RA_CAT_COLOR[S.category]||'#8a93a3'}"></span><div><b>「${_e(S.title)}」</b><div class="ra-sub">${_e(S.category)} · ${_e(S.revision||'')}</div></div></div>`+
    raStats([{v:S.in,l:'인용받음',ic:'bulk',tone:S.in>=10?'warn':S.in?'acc':'n',tip:'이 내규를 개정·폐지하거나 명칭을 바꾸면 함께 검토할 내규'},{v:S.out,l:'인용함',ic:'doc',tone:S.out?'acc':'n'},{v:brk.length,l:'명칭 확인',ic:'alert',tone:brk.length?'bad':'ok'}])+
    `<div class="ra-gp-c"><div><div class="ra-ih"><i class="ra-gk in"></i>이 내규를 인용하는 내규</div>${li(S.citedBy,'없음')}</div><div><div class="ra-ih"><i class="ra-gk out"></i>이 내규가 인용하는 내규</div>${li(S.cites,'없음')}</div></div>`+
    (brk.length?`<div class="ra-ih">명칭 확인 필요</div><ul class="ra-gp-l">${brk.map(b=>`<li>「${_e(b.name)}」${b.near?` → 「${_e(b.near)}」`:''} <span class="ra-chip ${b.kind==='stale'?'warn':'hi'}">${b.kind==='stale'?'옛 명칭':'목록에 없음'}</span></li>`).join('')}</ul>`:'')+
    `<div class="ra-row" style="margin-top:12px"><button class="svc-btn sm" onclick="raCheckToAmend('${_a(S.slug)}','${_a(S.title)}')">${raIc('amend')}개정 작업</button><a class="ra-link" href="${raRegUrl(S.slug)}" target="_blank" rel="noopener">원문↗</a></div>`;
}
function raGraphBulk(oldName, newName){
  const from=((typeof _raGraph!=='undefined'&&_raGraph&&_raGraph.broken)||[]).filter(b=>b.name===oldName).map(b=>b.from);
  Object.assign(RA.bulk,{old:oldName,neu:newName,whole:true,res:null,sel:{},only:from.length?from:null,reason:`「${oldName}」의 명칭이 「${newName}」${raRo(newName)} 바뀜에 따라 이를 인용하는 ${RA_ORG.reg_word}를 일괄 정비하려는 것임.`});
  RA.tab='bulk'; _raSave(); openRegAgent(); setTimeout(raBulkRun,50);
}
function raGraphView(){
  if(!_raGraph){ setTimeout(raGraphLoad,0); return `<div class="ra-wide" id="raGraph">${raSpin('인용 관계 준비 중...')}</div>`; }
  const d=_raGraph, G=RA.graph||{sel:''}, st=d.stats;
  const hubs=[...d.nodes].sort((a,b)=>b.in-a.in).filter(n=>n.in).slice(0,10);
  const top=hubs[0];
  // 명칭 오류: 같은 이름끼리 묶어 일괄 정비로 넘긴다
  const grp={}; d.broken.forEach(b=>{ const g=grp[b.name]=grp[b.name]||{name:b.name,near:b.near,kind:b.kind,regs:0,count:0}; g.regs++; g.count+=b.count; });
  const bl=Object.values(grp).sort((a,b)=>b.regs-a.regs||b.count-a.count);
  const legend=`<div class="ra-stack-l">`+RA_CAT_ORDER.filter(c=>d.nodes.some(n=>n.category===c)).map(c=>`<span><i style="background:${RA_CAT_COLOR[c]}"></i>${c} <b>${d.nodes.filter(n=>n.category===c).length}</b></span>`).join('')+
    `<span><i class="ra-gk in"></i>인용함 → 선택</span><span><i class="ra-gk out"></i>선택 → 인용함</span></div>`;
  return `<div class="ra-wide" id="raGraph">`+
    raStats([{v:st.regs,l:`개 ${RA_ORG.reg_word}`,ic:'doc',tone:'acc'},{v:st.edges,l:'인용 관계',ic:'graph',tone:'acc'},{v:top?top.in:0,l:top?`최다 인용 「${top.title}」`:'최다 인용',ic:'bulk',tone:'warn',tip:'인용이 많을수록 개정 시 함께 검토할 내규가 많습니다'},{v:st.isolated,l:'다른 내규와 연결 없음',ic:'info',tone:'n'},{v:st.broken,l:'옛 명칭·없는 내규명 인용',ic:'alert',tone:st.broken?'bad':'ok'}])+
    `<section class="ra-sec"><div class="ra-sec-h"><span class="ra-num">1</span><div class="ra-sec-t"><h2>인용 관계도 ${raTip('점은 내규(크기 = 인용받은 수, 색 = 종류), 선은 「내규명」 인용입니다. 점을 누르면 그 내규의 인용 관계가 강조됩니다.')}</h2></div></div>`+
      `<div class="ra-gwrap"><div class="ra-gfig">${raGraphSvg(d,G.sel)}${legend}</div><div class="ra-gpanel">${raGraphPanel(d,G.sel)}</div></div></section>`+
    raPair(raSec(2,'많이 인용되는 내규 Top 10',raTip('개정·폐지·명칭 변경 때 파급이 큰 내규입니다. 막대를 누르면 관계도에서 선택됩니다.'),
        raBars(hubs.map(n=>({l:n.title,n:n.in,tone:n.in>=20?'warn':'acc',go:`raGraphSel('${_a(n.slug)}')`})),'','많이 인용되는 내규')),
      raSec(3,'명칭 확인이 필요한 인용',raTip('현행 목록에 없는 내규명 또는 옛 명칭으로 인용한 곳입니다. 옛 명칭은 일괄 정비로 한 번에 고칠 수 있습니다.'),
        bl.length?`<ul class="ra-gb">`+bl.slice(0,12).map(g=>`<li><div><b>「${_e(g.name)}」</b>${g.near?` → 「${_e(g.near)}」`:''}<div class="ra-sub">${g.regs}개 ${_e(RA_ORG.reg_word)} · ${g.count}곳</div></div>`+
          `<span class="ra-chip ${g.kind==='stale'?'warn':'hi'}">${g.kind==='stale'?'옛 명칭':'목록에 없음'}</span>${g.near?`<button class="svc-btn sm" onclick="raGraphBulk('${_a(g.name)}','${_a(g.near)}')">${raIc('bulk')}일괄 정비 검토</button>`:''}</li>`).join('')+`</ul>`+(bl.length>12?`<div class="ra-meta">외 ${bl.length-12}건</div>`:'')
          :`<div class="ra-ok">${raIc('check')}명칭 오류 인용 없음</div>`))+
    `<div class="ra-foot"><button class="svc-btn ghost sm" onclick="_raGraph=null;raGraphLoad()">다시 분석</button></div></div>`;
}

// ══════════════════════════════════════════════════════════════════════════
// 절차 안내 — 기관 프로필(procedure.questions·steps)로 구성. when=모두 일치, unless=하나라도 일치하면 제외
// ══════════════════════════════════════════════════════════════════════════
function raPQ(){ return ((RA_ORG||{}).procedure||{}).questions||[]; }
function raPCfg(){ return (RA_ORG||{}).procedure||{}; }
function raCondMatch(cond, a){ return Object.entries(cond||{}).map(([k,v])=>Array.isArray(v)?v.includes(a[k]):a[k]===v); }
const _raVm=(v,x)=>Array.isArray(v)?v.includes(x):x===v;
function raQLabel(k){ const q=raPQ().find(x=>x.k===k)||{}; return q.s||String(q.q||k).replace(/[?？].*$/,'').slice(0,18); }
function raALabel(k,v){ const q=raPQ().find(x=>x.k===k)||{}; const o=(q.opts||[['y','예'],['n','아니오']]).find(x=>x[0]===v); return o?o[1]:v; }
// 모든 단계를 해당 여부 답변으로 판정 — in(해당) · tbd(답변이 있어야 결정) · out(해당 없음, 사유 포함)
// when=모두 일치, unless=하나라도 일치하면 제외. 같은 id의 대안 경로는 하나만 남긴다(해당 > 미정 > 해당 없음)
function raProcEval(){
  const a=RA.proc.ans||{}, ph=raPhases().map(p=>p.id);
  const raw=(raPCfg().steps||[]).map((s,i)=>{
    const W=Object.entries(s.when||{}), U=Object.entries(s.unless||{});
    const why=[...W.filter(([k,v])=>a[k]&&!_raVm(v,a[k])),...U.filter(([k,v])=>a[k]&&_raVm(v,a[k]))].map(([k])=>`${raQLabel(k)}: ${raALabel(k,a[k])}`);
    const unkW=W.filter(([k])=>!a[k]).map(([k])=>k);
    const unk=[...new Set([...unkW,...U.filter(([k])=>!a[k]).map(([k])=>k)])];
    return {...s, desc:s.d||s.desc||'', docs:s.docs||[], phase:ph.includes(s.phase)?s.phase:ph[0], st:why.length?'out':unk.length?'tbd':'in', soft:!why.length&&!unkW.length, why, unk, ord:i};
  });
  const by={}; raw.forEach(s=>(by[s.id]=by[s.id]||[]).push(s));
  const out=Object.values(by).map(vs=>{ const p=vs.find(x=>x.st==='in')||vs.find(x=>x.st==='tbd'&&x.soft)||vs.find(x=>x.st==='tbd')||vs[0]; p.alts=vs.filter(x=>x!==p&&x.st!=='out').map(x=>x.t); return p; });
  return out.sort((x,y)=>(ph.indexOf(x.phase)-ph.indexOf(y.phase))||(x.ord-y.ord));
}
// 에이전트·요약용 목록: 확정된 단계 + when 조건은 맞고 unless(제외 조건)만 미답변인 단계
function raProcSteps(){ return raProcEval().filter(s=>s.st==='in'||(s.st==='tbd'&&s.soft)); }
// 진행 상태 — 앞 국면의 필수 단계와 after(선행 단계)가 끝나야 열린다. optional 단계는 막지 않는다
function raProcState(){
  const items=raProcEval(), chk=RA.proc.chk||{}, ph=raPhases().map(p=>p.id);
  const live=items.filter(s=>s.st!=='out'), req=live.filter(s=>!s.optional);   // 미정(tbd) 단계도 답할 때까지 관문을 막는다
  live.forEach((s,i)=>{
    const pi=ph.indexOf(s.phase);
    s.no=i+1; s.done=!!chk[s.id]; s.doneAt=typeof chk[s.id]==='string'?chk[s.id]:'';
    s.block=req.filter(x=>x!==s&&!chk[x.id]&&(ph.indexOf(x.phase)<pi||(s.after||[]).includes(x.id)));
    s.locked=!s.done&&s.block.length>0;
  });
  const flow=live.filter(s=>s.st==='in');
  const next=flow.find(s=>!s.done&&!s.locked&&!s.optional)||flow.find(s=>!s.done&&!s.locked)||null;
  return {items, live, flow, next, out:items.filter(s=>s.st==='out')};
}
function raStepState(s, st){ return s.done?'done':s.st==='tbd'?'tbd':st.next&&st.next.id===s.id?'next':s.locked?'locked':'todo'; }
function raProcAnswer(k,v){ RA.proc.ans[k]=v; _raSave(); raProcRedraw(); }
function raProcCheck(id,on){ RA.proc.chk[id]=on?raYmd(new Date()):false; _raSave(); raProcRedraw(); }
function raProcRedraw(){ const t=RA.tab; if(t==='proc'){ const y=window.scrollY; raRender(); window.scrollTo(0,y); } else { const s=document.querySelector('.ra-side'); if(s) s.innerHTML=raProcSide(t); } }
function raProcQs(){
  const a=RA.proc.ans||{};
  return raPQ().map(q=>{
    const opts=q.opts||[['y','예'],['n','아니오']];
    return `<div class="ra-pq"><div class="ra-pq-q">${_e(q.q)} <span class="ra-ref">${_e(q.ref||'')}</span></div><div class="ra-seg">`+
      opts.map(([v,l])=>`<button class="${a[q.k]===v?'on':''}" onclick="raProcAnswer('${_a(q.k)}','${_a(v)}')">${_e(l)}</button>`).join('')+`</div></div>`;
  }).join('')||'<div class="ra-empty">기관 프로필에 절차 질문이 없습니다.</div>';
}
// 측면 패널(제정·개정 화면)의 간단한 진행 목록
function raProcStepsView(mode, compact){
  const st=raProcState(), steps=st.flow;
  if(!steps.length) return '<div class="ra-empty">기관 프로필(org_config.json)에 절차 단계가 없습니다.</div>';
  const done=steps.filter(s=>s.done).length;
  const names=mode?Object.fromEntries(RA_DOCS[mode]):{};
  const ready=mode&&!raWizGate(mode,RA_WIZ[mode].length-1);
  return `<div class="ra-prog"><i style="width:${Math.round(done/steps.length*100)}%"></i></div><div class="ra-meta">${done}/${steps.length} 단계 완료${st.live.length>steps.length?` · 미정 ${st.live.length-steps.length}`:''}</div><ol class="ra-steps">`+
    steps.map(s=>{ const isN=st.next&&st.next.id===s.id;
      return `<li class="${s.done?'done':''}${isN?' next':''}${s.locked?' locked':''}"><label${s.locked?` title="먼저: ${_e(s.block.map(x=>x.t).join(', '))}"`:''}><input type="checkbox" ${s.done?'checked':''} ${s.locked?'disabled':''} onchange="raProcCheck('${_a(s.id)}',this.checked)"><span class="ra-st-t">${s.locked?raIc('lock'):''}${_e(s.t)}</span></label>`+
      `<div class="ra-st-m"><span class="ra-ref">${_e(s.ref||'')}</span> · ${_e(s.who||'')}</div>`+
      (compact&&!isN?'':`<div class="ra-st-d">${_e(s.desc)}</div>`)+
      (ready&&s.docs.length?`<div class="ra-st-docs">${s.docs.filter(d=>names[d]).map(d=>`<button class="ra-chip btn" onclick="raGoDoc('${mode}','${d}')">${raIc('doc')}${_e(names[d])}</button>`).join('')}</div>`:'')+`</li>`; }).join('')+`</ol>`;
}
function raGoDoc(mode, d){ const last=RA_WIZ[mode].length-1, why=raWizGate(mode,last); RA[mode].docTab=d;
  if(why){ _raSave(); _toast(why); return; }
  RA[mode].step=last; _raSave(); raRerender(mode); setTimeout(raWizTop,60); }
function raProcSide(mode){
  const a=RA.proc.ans||{}, Q=raPQ(); const answered=Q.filter(q=>a[q.k]).length;
  return `<div class="ra-side-h">${raIc('proc')}<span>절차 진행</span><button class="ra-link" onclick="raTab('proc')">전체 보기</button></div>`+
    (answered<Q.length?`<details class="ra-q-det"><summary><span class="ra-q-cnt">${answered}/${Q.length}</span><span>해당 여부 답하기</span></summary>${raProcQs()}</details>`:`<div class="ra-q-done">${raIc('check')}해당 여부 완료 <button class="ra-link" onclick="raTab('proc')">고치기</button></div>`)+
    raProcStepsView(mode, true);
}

// ── 기간·일정 ─────────────────────────────────────────────────────────────
const RA_PHASE_FALLBACK=[{id:'prep',t:'입안·점검',d:''},{id:'opinion',t:'의견수렴·평가',d:'',parallel:true},{id:'review',t:'심의·확정',d:''},{id:'enforce',t:'시행·공개',d:''}];
function raPhases(){ const p=raPCfg().phases; return (p&&p.length)?p:RA_PHASE_FALLBACK; }
function raDays(s){ const n=parseInt(s.days,10); return isNaN(n)?0:n; }
function raYmd(d){ return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; }
function raDt(iso){ const [y,m,d]=String(iso||'').split('-').map(Number); return new Date(y||1970,(m||1)-1,d||1); }
function raAddD(iso,n){ const d=raDt(iso); d.setDate(d.getDate()+n); return raYmd(d); }
function raDiffD(a,b){ return Math.round((raDt(b)-raDt(a))/864e5); }
function raMd(iso){ const d=raDt(iso); return `${d.getMonth()+1}.${d.getDate()}(${'일월화수목금토'[d.getDay()]})`; }
// 국면은 차례로, parallel 국면 안의 단계는 같은 날 시작(가장 긴 기간만큼 소요)
function raSchedule(flow){
  const P=RA.proc.plan||{}; const start=/^\d{4}-\d{2}-\d{2}$/.test(P.start||'')?P.start:raYmd(new Date());
  let t=0; const m={}, brk=[];
  raPhases().forEach(ph=>{ const ps=flow.filter(s=>s.phase===ph.id); if(!ps.length) return;
    if(ph.parallel){ let mx=0; ps.forEach(s=>{ const d=raDays(s); m[s.id]={s:t,e:t+d}; mx=Math.max(mx,d); }); if(mx) brk.push(`${ph.t} ${mx}일${ps.filter(s=>raDays(s)>0).length>1?'(병행)':''}`); t+=mx; }
    else ps.forEach(s=>{ const d=raDays(s); m[s.id]={s:t,e:t+d}; if(d) brk.push(`${s.t.replace(/\s*\d+일.*$/,'')} ${d}일`); t+=d; }); });
  const target=/^\d{4}-\d{2}-\d{2}$/.test(P.target||'')?P.target:'';
  const end=raAddD(start,t);
  return {start, total:t, m, brk, end, target, slack:target?raDiffD(end,target):null, tbd:flow.filter(s=>s.st==='tbd').length};
}
function raPlanSet(k,v){ RA.proc.plan=RA.proc.plan||{}; RA.proc.plan[k]=v; _raSave(); raProcRedraw(); }

// ── 행위 주체(레인)·도구 결과 근거 ─────────────────────────────────────────
const RA_ACTOR_FALLBACK=[{id:'dept',t:'주무부서',m:'주무'},{id:'mgmt',t:'내규관리부서',m:'내규관리'},{id:'audit',t:'감사부서',m:'감사'},{id:'decide',t:'심의·결정',m:'위원회|이사회|기관장'}];
function raActors(){ const a=raPCfg().actors; return (a&&a.length)?a:RA_ACTOR_FALLBACK; }
function raStepLanes(s){
  const A=raActors(), hit=x=>A.filter(a=>{ try{ return x&&new RegExp(a.m||a.t).test(x); }catch(e){ return false; } }).map(a=>a.id);
  const [f,t]=String(s.who||'').split('→');
  let from=s.lanes||hit(f); if(!from.length) from=[A[0].id];
  const to=(s.to||hit(t||'')).filter(x=>!from.includes(x));
  return {from, to};
}
function raProcDocMode(){ return RA.amend.changes.length?'amend':RA.enact.draft?'enact':null; }
// auto 단계: 이 도구에서 만든 결과로 완료 근거를 보여 준다
function raEvidence(s, mode){
  if(!s.auto||!mode) return null; const S=RA[mode];
  if(s.auto==='draft') return [{ok:mode==='enact'?!!S.draft:S.changes.length>0, l:mode==='enact'?'제정안 초안':`수정안 ${S.changes.length}개 조`}];
  if(s.auto==='check'){ const rv=S.review, w=rv?rv.rows.filter(r=>r.status==='warn').length:0;
    return [{ok:!!S.lint,l:'조문 점검'},{ok:!!rv&&!w,warn:!!rv&&w>0,l:rv?(w?`사전검토 보완 ${w}`:'심의 사전검토'):'심의 사전검토'}]; }
  return null;
}
function raStepGo(id){ const el=document.getElementById('raStep-'+id); if(!el) return; el.scrollIntoView({behavior:'smooth',block:'center'}); el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); }
function raWho(who){
  const w=String(who||'');
  const k=/감사/.test(w)?'audit':/이사회|원장|기관장/.test(w)&&!/주무부서$/.test(w)?'head':/→/.test(w)?'flow':/내규관리부서/.test(w)&&!/주무/.test(w)?'mgmt':/·/.test(w)?'flow':'dept';
  return `<span class="ra-who w-${k}">${_e(w)}</span>`;
}
const RA_SS={done:'완료',next:'지금 할 일',locked:'선행 대기',tbd:'조건 미정',todo:'대기'};

// ── 프로세스 맵: 행위 주체 × 국면. 수행(●)과 이관받는 곳(↘) ─────────────────
function raProcMap(st){
  const A=raActors(), PH=raPhases(), cell={};
  st.live.forEach(s=>{ const L=raStepLanes(s);
    L.from.forEach(id=>(cell[id+'|'+s.phase]=cell[id+'|'+s.phase]||[]).push({s,k:'do'}));
    L.to.forEach(id=>(cell[id+'|'+s.phase]=cell[id+'|'+s.phase]||[]).push({s,k:'recv'})); });
  const rows=A.filter(a=>PH.some(p=>cell[a.id+'|'+p.id]));
  if(!rows.length) return '<div class="ra-empty">표시할 단계가 없습니다.</div>';
  const node=({s,k})=>{ const ss=raStepState(s,st);
    return `<button class="ra-node n-${ss} k-${k}" onclick="raStepGo('${_a(s.id)}')" title="${_e(`${s.no}. ${s.t} — ${RA_SS[ss]}${k==='recv'?' (이관받음)':''} · ${s.who||''}`)}"><span class="ra-node-n">${ss==='done'?'✓':s.no}</span><span class="ra-node-t">${k==='recv'?raIc('arrow'):''}${_e(s.t)}</span></button>`; };
  return `<div class="ra-map-w"><div class="ra-pmap" style="grid-template-columns:110px repeat(${PH.length},minmax(0,1fr))">`+
    `<div class="ra-pm-h"></div>`+PH.map((p,i)=>`<div class="ra-pm-h"><span>${i+1}</span>${_e(p.t)}${p.parallel?' <em>병행</em>':''}</div>`).join('')+
    rows.map(a=>`<div class="ra-pm-a">${_e(a.t)}</div>`+PH.map(p=>`<div class="ra-pm-c">${(cell[a.id+'|'+p.id]||[]).map(node).join('')}</div>`).join('')).join('')+
    `</div></div><div class="ra-stack-l ra-pm-leg"><span class="t-ok"><i></i>완료</span><span class="t-acc"><i></i>지금 할 일</span><span class="t-n"><i></i>대기</span><span>${raIc('lock')}선행 대기</span><span class="ra-pm-tbd">조건 미정</span><span>${raIc('arrow')}이관받음</span></div>`;
}

// ── 일정표(간트) ─────────────────────────────────────────────────────────
function raGantt(st, sc){
  if(!st.flow.length) return '<div class="ra-empty">해당 단계가 없습니다.</div>';
  const tot=Math.max(sc.total,1), pos=d=>Math.max(0,Math.min(100,d/tot*100));
  const today=raDiffD(sc.start,raYmd(new Date())), tg=sc.target?raDiffD(sc.start,sc.target):null;
  const marks=(today>=0&&today<=tot?`<i class="ra-g-now" style="left:${pos(today)}%"></i>`:'')+(tg!=null&&tg>=0&&tg<=tot?`<i class="ra-g-tg" style="left:${pos(tg)}%"></i>`:'');
  const ticks=[]; for(let d=0; d<=tot; d+=tot>42?14:7) ticks.push(d); if(ticks[ticks.length-1]!==tot) ticks.push(tot);
  return `<div class="ra-gantt"><div class="ra-g-row ra-g-ax"><span class="ra-g-l"></span><span class="ra-g-t">${ticks.map(d=>`<em style="left:${pos(d)}%">${raMd(raAddD(sc.start,d))}</em>`).join('')}</span><span class="ra-g-d"></span></div>`+
    st.flow.map(s=>{ const r=sc.m[s.id], ss=raStepState(s,st), dur=r.e-r.s;
      return `<div class="ra-g-row g-${ss}" role="button" tabindex="0" onclick="raStepGo('${_a(s.id)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();raStepGo('${_a(s.id)}')}"><span class="ra-g-l" title="${_e(s.t)}"><b>${s.no}</b>${_e(s.t)}</span><span class="ra-g-t">${marks}`+
        (dur?`<i class="ra-g-bar" style="left:${pos(r.s)}%;width:${pos(dur)}%"></i>`:`<i class="ra-g-ms" style="left:${pos(r.s)}%"></i>`)+
        `</span><span class="ra-g-d">${dur?`${raMd(raAddD(sc.start,r.s))}–${raMd(raAddD(sc.start,r.e))}`:raMd(raAddD(sc.start,r.s))}</span></div>`; }).join('')+
    `<div class="ra-stack-l"><span class="t-acc"><i></i>기간 단계</span><span><i class="ra-g-ms ra-g-lg"></i>당일 처리</span>${today>=0&&today<=tot?'<span class="ra-g-lnow">오늘</span>':''}${tg!=null?'<span class="ra-g-ltg">목표 시행일</span>':''}</div></div>`;
}

// ── 추진계획표 내보내기(한글·Word) ──────────────────────────────────────────
function raPlanExport(fmt){
  const st=raProcState(), sc=raSchedule(st.live), mode=raProcDocMode();
  const names=Object.fromEntries(RA_DOCS[mode||'enact']), title=(mode&&RA[mode].title)||'○○';
  const a=RA.proc.ans||{};
  const when=s=>{ if(s.st==='tbd') return '조건 확인 필요'; const r=sc.m[s.id]; if(!r) return ''; return r.e>r.s?`${raAddD(sc.start,r.s)} ~ ${raAddD(sc.start,r.e)}`:raAddD(sc.start,r.s); };
  const state=s=>s.done?`완료${s.doneAt?' '+s.doneAt:''}`:s.st==='tbd'?'미정':s.locked?'선행 대기':st.next&&st.next.id===s.id?'진행':'예정';
  const rows=[['순번','단계','담당','근거','예정일','산출 문서','상태'].map(t=>({t,hd:1})),
    ...st.live.map(s=>[{t:String(s.no)},{t:s.t+(s.optional&&!/선택/.test(s.t)?'(선택)':'')},{t:s.who||''},{t:`「${raRules()}」 ${s.ref||''}`},{t:when(s)},{t:s.docs.map(d=>names[d]).filter(Boolean).join(', ')},{t:state(s)}])];
  const head=[`「${title}」 ${mode==='amend'?'개정':mode==='enact'?'제정':'제·개정'} 추진계획표`,'',
    `기준일 ${sc.start} · 예상 시행 가능일 ${sc.end}${sc.tbd?'(잠정)':''} (최소 ${sc.total}일${sc.brk.length?': '+sc.brk.join(' + '):''})`+(sc.target?` · 목표 시행일 ${sc.target} (${sc.slack>=0?`여유 ${sc.slack}일`:`${-sc.slack}일 부족`})`:''),
    `해당 여부: `+raPQ().map(q=>`${raQLabel(q.k)} ${a[q.k]?raALabel(q.k,a[q.k]):'미답변'}`).join(' · '),''].join('\n');
  const outs=st.out.length?['해당 없음 단계',...st.out.map(s=>`  - ${s.t} — ${s.why.join(', ')}`)].join('\n'):'';
  const blocks=[{t:'p',text:head,titleBold:1},{t:'table',colWidths:[2800,11000,7600,7600,7400,7228,4000],rows}];
  if(outs) blocks.push({t:'p',text:''},{t:'p',text:outs});
  raSaveFile(fmt, `${title}_추진계획표`.replace(/[\\/:*?"<>|]/g,'_'), blocks, '추진계획표');
}

// ── 절차 안내 대시보드 ────────────────────────────────────────────────────
function raProcView(){
  const st=raProcState(), sc=raSchedule(st.live), a=RA.proc.ans||{}, Q=raPQ();
  const flow=st.flow, done=flow.filter(s=>s.done).length, pct=flow.length?Math.round(done/flow.length*100):0, next=st.next;
  const answered=Q.filter(q=>a[q.k]).length, tbd=st.live.filter(s=>s.st==='tbd').length;
  const mode=raProcDocMode(), names=Object.fromEntries(RA_DOCS[mode||'enact']);
  const docs=[...new Set(flow.flatMap(s=>s.docs||[]))].filter(d=>names[d]);
  const slackTone=sc.slack==null?'':sc.slack<0?'bad':sc.slack<7?'warn':'ok';
  const kpis=`<div class="ra-kpis ra-pk">`+
    `<div class="ra-kpi"><div class="ra-kpi-l">진행률</div><div class="ra-kpi-v">${pct}<small>%</small></div><div class="ra-meter" role="meter" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100" aria-label="절차 진행률"><i style="width:${pct}%"></i></div><div class="ra-kpi-s">${flow.length}단계 중 ${done} 완료${tbd?` · 미정 ${tbd}`:''}</div></div>`+
    `<div class="ra-kpi ra-kpi-next"><div class="ra-kpi-l">다음 할 일</div>`+(next?`<div class="ra-kpi-t"><button class="ra-link ra-kpi-go" onclick="raStepGo('${_a(next.id)}')">${next.no}. ${_e(next.t)}</button></div><div class="ra-kpi-s">${raWho(next.who)}<span class="ra-ref">${_e(next.ref||'')}</span>${sc.m[next.id]?`<span class="ra-days">${raMd(raAddD(sc.start,sc.m[next.id].s))}</span>`:''}</div>`:`<div class="ra-kpi-t">${flow.length?'모든 단계 완료':'해당 여부에 답하세요'}</div>`)+`</div>`+
    `<div class="ra-kpi" title="${_e(sc.brk.join(' + '))}"><div class="ra-kpi-l">예상 시행 가능일</div><div class="ra-kpi-v ra-kpi-date">${raMd(sc.end)}</div><div class="ra-kpi-s">최소 ${sc.total}일${sc.tbd?` · <b class="sl-warn" title="답하지 않은 질문에 따라 달라집니다">미정 ${sc.tbd}단계 포함(잠정)</b>`:''}${sc.slack!=null?` · <b class="sl-${slackTone}">${sc.slack>=0?`목표까지 여유 ${sc.slack}일`:`목표보다 ${-sc.slack}일 늦음`}</b>`:''}</div></div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">준비할 문서</div><div class="ra-kpi-v">${docs.length}<small>종</small></div><div class="ra-kpi-s" title="${_e(docs.map(d=>names[d]).join(' · '))}">${docs.slice(0,3).map(d=>_e(names[d])).join(' · ')||'—'}${docs.length>3?` 외 ${docs.length-3}종`:''}</div></div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">해당 여부 답변</div><div class="ra-kpi-v">${answered}<small>/${Q.length}</small></div>${raMeter(answered/Math.max(1,Q.length),'acc')}<div class="ra-kpi-s">${answered<Q.length?`미정 단계 ${tbd}개`:'맞춤 절차 확정'}</div></div></div>`;
  const qs=`<div class="ra-pq-grid">`+Q.map(q=>{ const opts=q.opts||[['y','예'],['n','아니오']];
    return `<div class="ra-pq-c${a[q.k]?' on':''}"><div class="ra-pq-q">${_e(q.q)}</div><div class="ra-pq-f"><div class="ra-seg">`+
      opts.map(([v,l])=>`<button class="${a[q.k]===v?'on':''}" onclick="raProcAnswer('${_a(q.k)}','${_a(v)}')">${_e(l)}</button>`).join('')+`</div><span class="ra-ref">${_e(q.ref||'')}</span></div></div>`; }).join('')+`</div>`;
  // 국면별 체크리스트(관문)
  const card=s=>{ const ss=raStepState(s,st), dd=raDays(s), r=sc.m[s.id], ev=raEvidence(s,mode);
    const sb=s.block.filter(x=>x.phase===s.phase);   // 앞 국면 대기는 국면 관문에서 한 번만 알린다
    const sdocs=(s.docs||[]).filter(d=>names[d]);
    return `<div class="ra-card c-${ss}" id="raStep-${_e(s.id)}"><label class="ra-card-h" title="${_e(s.desc)}"><input type="checkbox" ${s.done?'checked':''} ${s.locked||s.st==='tbd'?'disabled':''} onchange="raProcCheck('${_a(s.id)}',this.checked)"><span><b class="ra-card-no">${s.no}</b>${_e(s.t)}${s.optional&&!/선택/.test(s.t)?' <em class="ra-opt">선택</em>':''}</span></label>`+
      `<div class="ra-card-m">${raWho(s.who)}${dd&&!/\d+일/.test(s.t)?`<span class="ra-days" title="${_e(s.days_note||'')}">${dd}일${s.days_note?'':' 이상'}</span>`:''}<span class="ra-ref">${_e(s.ref||'')}</span></div>`+
      (s.st==='tbd'?`<div class="ra-card-g g-tbd">${raIc('info')}답변 필요: ${s.unk.map(raQLabel).map(_e).join(', ')}${s.alts&&s.alts.length?` ${raTip('가능한 경로: '+[s.t,...s.alts].join(' / '))}`:''}</div>`:'')+
      (s.locked&&sb.length?`<div class="ra-card-g g-lock">${raIc('lock')}먼저: ${sb.slice(0,2).map(x=>`<button class="ra-link" onclick="raStepGo('${_a(x.id)}')">${x.no}. ${_e(x.t)}</button>`).join(', ')}${sb.length>2?` 외 ${sb.length-2}`:''}</div>`:'')+
      (ss==='next'&&s.desc?`<div class="ra-card-d">${_e(s.desc)}</div>`:'')+
      (ev?`<div class="ra-card-ev">${ev.map(e=>`<span class="ra-ev ${e.ok?'ok':e.warn?'warn':''}">${raIc(e.ok?'check':e.warn?'alert':'info')}${_e(e.l)}</span>`).join('')}${!s.done&&!s.locked&&ev.every(e=>e.ok)?`<button class="ra-chip btn" onclick="raProcCheck('${_a(s.id)}',true)">완료 처리</button>`:''}</div>`:'')+
      (sdocs.length?`<div class="ra-card-docs">${sdocs.map(d=>mode?`<button class="ra-chip btn" onclick="raGoDoc('${mode}','${d}')">${raIc('doc')}${_e(names[d])}</button>`:`<span class="ra-chip">${raIc('doc')}${_e(names[d])}</span>`).join('')}</div>`:'')+
      `<div class="ra-card-f">${s.done?`<span class="ra-ev ok">${raIc('check')}완료${s.doneAt?' '+raMd(s.doneAt):''}</span>`:r?`<span class="ra-card-dt">예정 ${r.e>r.s?`${raMd(raAddD(sc.start,r.s))}–${raMd(raAddD(sc.start,r.e))}`:raMd(raAddD(sc.start,r.s))}</span>`:''}</div>`+
      (ss==='next'?'<div class="ra-card-now">지금 할 일</div>':'')+`</div>`; };
  const lanes=`<div class="ra-lanes">`+raPhases().map((ph,pi)=>{
    const ps=st.live.filter(s=>s.phase===ph.id), req=ps.filter(s=>s.st==='in'&&!s.optional), pd=req.filter(s=>s.done).length;
    const outs=st.out.filter(s=>s.phase===ph.id);
    const lst=!ps.length?'none':req.length&&pd===req.length&&!ps.some(s=>s.st==='tbd')?'done':ps.some(s=>next&&s.id===next.id)?'now':ps.every(s=>s.locked||s.st==='tbd')?'lock':'todo';
    return `<div class="ra-lane l-${lst}"><div class="ra-lane-h"><span class="ra-lane-n">${lst==='done'?'✓':pi+1}</span><div><b>${_e(ph.t)}</b>${ph.d?' '+raTip(ph.d+(ph.parallel?' · 이 국면의 단계는 같은 기간에 진행할 수 있습니다.':'')):''}</div><span class="ra-lane-c">${pd}/${req.length}</span></div>`+
      `<div class="ra-lane-p"><i style="width:${req.length?Math.round(pd/req.length*100):0}%"></i></div>`+
      (pi>0?(()=>{ const pids=raPhases().slice(0,pi).map(x=>x.id), left=st.live.filter(x=>pids.includes(x.phase)&&!x.optional&&!x.done);
        return `<div class="ra-gate ${left.length?'off':'on'}" title="${_e(left.map(x=>x.no+'. '+x.t).join('\n'))}">${raIc(left.length?'lock':'check')}${left.length?`관문: 앞 단계 ${left.length}개 남음`:'관문 통과'}</div>`; })():'')+
      (ps.length?ps.map(card).join(''):`<div class="ra-lane-empty">해당 단계 없음</div>`)+
      (outs.length?`<details class="ra-outs"><summary>해당 없음 ${outs.length}</summary>${outs.map(s=>`<div class="ra-out"><b>${_e(s.t)}</b><span>${_e(s.why.join(', '))}</span></div>`).join('')}</details>`:'')+`</div>`; }).join('')+`</div>`;
  const P=RA.proc.plan||{};
  const plan=`<div class="ra-plan-f"><label class="ra-f"><span>기준일 ${raTip('입안(내규안 작성)을 마칠 날 또는 오늘. 이 날부터 국면 순서대로 최소 기간을 더합니다.')}</span><input type="date" class="ra-in" value="${_e(sc.start)}" onchange="raPlanSet('start',this.value)"></label>`+
    `<label class="ra-f"><span>목표 시행일 ${raTip('정하면 여유·부족 일수를 계산하고 일정표에 표시합니다.')}</span><input type="date" class="ra-in" value="${_e(P.target||'')}" onchange="raPlanSet('target',this.value)"></label>`+
    `<div class="ra-plan-s">${raStats([{v:`${sc.total}일`,l:'최소 소요',ic:'proc',tone:'acc',tip:sc.brk.join(' + ')},{v:raMd(sc.end),l:'시행 가능일',ic:'check',tone:'acc'},...(sc.slack!=null?[{v:sc.slack>=0?`+${sc.slack}일`:`${sc.slack}일`,l:sc.slack>=0?'목표까지 여유':'목표 대비 부족',ic:sc.slack>=0?'check':'alert',tone:slackTone}]:[])])}</div></div>`+
    raGantt(st,sc)+
    `<div class="ra-save"><div class="ra-row" style="margin:0"><span class="ra-sub">${raIc('doc')} 추진계획표 — 단계·담당·근거·예정일·산출 문서·상태</span><span class="ra-sep"></span><button class="svc-btn yes" onclick="raPlanExport('hwpx')">한글(.hwpx)</button><button class="svc-btn" onclick="raPlanExport('docx')">Word(.docx)</button></div></div>`;
  const sum=(RA_ORG.rules_summary||[]).map(([h,t])=>`<div class="ra-rule"><b>${_e(h)}</b><p>${_e(t)}</p></div>`).join('');
  return `<div class="ra-wide ra-procdash">${kpis}`+
    raSec(1,'해당 여부',raTip('답에 따라 단계·기간·문서가 정해집니다. 답하지 않은 조건에 걸린 단계는 “조건 미정”으로 표시됩니다.'),qs)+
    raSec(2,'프로세스 맵',raTip('행위 주체(행) × 국면(열). 단계를 누르면 아래 체크리스트로 이동합니다.'),raProcMap(st))+
    raSec(3,'단계별 체크리스트',raTip(`앞 국면의 필수 단계와 선행 단계를 마쳐야 다음 단계가 열립니다(관문). 체크하면 완료일이 이 브라우저에 저장됩니다.${mode?' 문서 칩을 누르면 해당 문서로 이동합니다.':''}`),lanes)+
    raSec(4,'일정 계획',raTip('국면 순서대로 최소 기간을 더해 예정일을 계산합니다. 병행 국면은 가장 긴 기간만 셉니다.'),plan)+
    `<details class="ra-sec ra-sec-det"><summary class="ra-sec-h"><span class="ra-num">5</span><div class="ra-sec-t"><h2>작성 기준 요약 — 「${_e(raRules())}」</h2></div>${raTip('절차·심의기준·기관 명칭은 기관 프로필(org_config.json)에서 바꿀 수 있습니다')}</summary><div class="ra-rules">${sum||'<div class="ra-empty">기관 프로필에 작성 기준 요약이 없습니다.</div>'}</div></details>`+
    `<div class="ra-foot"><button class="svc-btn ghost sm" onclick="if(confirm('해당 여부 답변·진행 체크·일정을 모두 지울까요?')){RA.proc={ans:{},chk:{},plan:{}};_raSave();raRender();}">절차 초기화</button></div></div>`;
}

// ══════════════════════════════════════════════════════════════════════════
// 다른 기관 사규(알리오) — 공공기관 경영정보 공개시스템의 내부규정을 찾아 조문을 참고로 쓴다
// 서버(/api/regagent/alio/*)가 알리오에서 기관 목록·규정 검색·현행본 파일을 받아 조문으로 바꾼다.
// 기관이 많으면 화면이 12곳씩 나눠 부르고(진행률·중지), 고른 조문은 제정 초안·개정 수정안 작성 때 참고 자료로 넘긴다.
// ══════════════════════════════════════════════════════════════════════════
let _raAlioOrgs=null, _raAlioRun=0;
// 알리오 검색 상태 — 제정·개정이 따로 갖는다(한쪽 검색이 다른 쪽에 섞이지 않게). 예전 한 덩어리 저장값은 제정 쪽으로 옮긴다
function raAl(mode){
  mode=mode==='amend'?'amend':mode==='enact'?'enact':(RA.tab==='amend'?'amend':'enact');
  if(!RA.alio||RA.alio.q!==undefined) RA.alio={enact:RA.alio&&RA.alio.q!==undefined?RA.alio:null, amend:null};
  if(!RA.alio[mode]) RA.alio[mode]={q:'',cat:'',scope:'peer',picked:[],res:null,open:{},old:false};
  return RA.alio[mode];
}
function raAlioSet(mode, q, R){
  Object.assign(raAl(mode),{q, res:{q, cat:'', total:R.orgs, searched:R.orgs, hits:R.hits, failed:[], timedOut:[], truncated:[]}, open:Object.fromEntries(R.opened.map(x=>[x.h.orgId+'|'+x.h.idx,{data:x.d}])), busy:false});
}
async function raAlioOrgs(){
  if(_raAlioOrgs) return _raAlioOrgs;
  const d=await raGet('/api/regagent/alio/orgs'); if(!d.success) throw new Error(d.error||'알리오 기관 목록을 불러오지 못했습니다.');
  _raAlioOrgs=d; return d;
}
// 검색어 추정: 내규명에서 종류 끝말을 뗀 핵심어(“업무용 드론 운영지침” → “드론”, “여비규정” → “여비”)
function raAlioGuess(mode){
  const t=String(mode==='enact'?RA.enact.title:RA.amend.title||'').replace(/\s*(시행세칙|운영지침|운영규정|운영규칙|관리규정|관리규칙|관리지침|규정|규칙|세칙|지침|요령|기준|예규)$/,'').trim();
  // 끝말이 핵심어인 경우가 많다(“임직원 여비” → “여비”). 꾸밈말·흔한 말은 뺀다
  const w=t.split(/\s+/).map(x=>x.replace(/(에관한|에대한|에|의)$/,'')).filter(x=>x.length>=2&&!/^(업무용|관한|대한|운영|관리|및|등|임직원|직원|기관|한국\S*|공공)$/.test(x));
  // 규정명 검색은 글자 그대로 맞추므로 한 낱말로: 흔한 동작어를 빼고 가장 긴(구체적인) 낱말 — “직장 내 괴롭힘 예방 및 처리” → “괴롭힘”
  const head=w.filter(x=>!/^(예방|처리|운영|관리|시행|업무|지급|등)$/.test(x));
  const pick=(head.length?head:w).slice().sort((a,b)=>b.length-a.length)[0];
  return (pick||t).slice(0,20);
}
function raAlioScopeIds(D, scope, picked){
  const me=D.self, all=D.orgs.filter(o=>o.id!==me);
  if(scope==='pick') return (picked||[]).filter(id=>D.orgs.some(o=>o.id===id));
  if(scope==='type'){ const t=(D.orgs.find(o=>o.id===me)||{}).type; return all.filter(o=>!t||o.type===t).map(o=>o.id); }
  if(scope==='all') return all.map(o=>o.id);
  return D.peers.slice();
}
function raAlioView(mode){
  const S=raAl(mode), D=_raAlioOrgs;
  if(!D&&!_raBusy.alioOrgs){ _raBusy.alioOrgs=true; raAlioOrgs().then(()=>raAlioRedraw(mode)).catch(()=>{}).finally(()=>{ _raBusy.alioOrgs=false; }); }
  if(!S.q) S.q=raAlioGuess(mode);
  const cats=D?Object.entries(D.categories):[['K1100','인사·복무·징계'],['K1200','보수'],['K1300','직제'],['K1400','기타'],['K1500','정관']];
  const n=k=>D?` ${raAlioScopeIds(D,k,S.picked).length}곳`:'';
  const scopes=[['peer','유관 기관'],['type','같은 유형'],['all','전체(오래 걸림)'],['pick','직접 고르기']];
  const head=`<div class="ra-row ra-al-q"><input class="ra-in" style="max-width:200px" placeholder="규정명 검색어 (예: 여비, 드론)" value="${_e(S.q)}" oninput="raAl('${mode}').q=this.value;_raSave()" onkeydown="if(event.key==='Enter')raAlioSearch('${mode}')">`+
    `<select class="ra-in sm" style="max-width:130px" onchange="raAl('${mode}').cat=this.value;_raSave()"><option value="">모든 분류</option>${cats.map(([k,l])=>`<option value="${k}"${S.cat===k?' selected':''}>${_e(l)}</option>`).join('')}</select>`+
    `<select class="ra-in sm" style="max-width:170px" onchange="raAl('${mode}').scope=this.value;_raSave();raAlioRedraw('${mode}')">${scopes.map(([k,l])=>`<option value="${k}"${S.scope===k?' selected':''}>${l}${n(k)}</option>`).join('')}</select>`+
    (S.busy?`<button class="svc-btn ghost" onclick="raAlioStop('${mode}')">중지</button>`:`<button class="svc-btn" onclick="raAlioSearch('${mode}')">${raIc('search')}알리오에서 찾기</button>`)+
    raTip('공공기관 경영정보 공개시스템(알리오)에 공시된 다른 기관 내부규정을 규정명으로 찾습니다. 조문을 열어 체크하면 초안·수정안 작성 때 참고합니다. 기관명·직위는 우리 기관에 맞게 바꿔 쓰세요.')+`</div>`;
  let pick='';
  if(S.scope==='pick'&&D){ const q=(S.pq||'').replace(/\s+/g,'');
    const list=D.orgs.filter(o=>o.id!==D.self&&(!q||(o.name+o.dept).replace(/\s+/g,'').includes(q))).slice(0,60);
    pick=`<div class="ra-pick"><div class="ra-pick-h">기관 고르기 <b>${S.picked.length}</b>곳 <input class="ra-in sm" placeholder="기관명·주무부처" value="${_e(S.pq||'')}" oninput="raAl('${mode}').pq=this.value;raAlioRedraw('${mode}')"></div><div class="ra-pick-l">`+
      list.map(o=>`<label class="ra-pick-i"><input type="checkbox" ${S.picked.includes(o.id)?'checked':''} onchange="raAlioPick('${mode}','${_a(o.id)}',this.checked)"><span><b>${_e(o.name)}</b> <em>${_e(o.dept)} · ${_e(o.type)}</em></span></label>`).join('')+`</div></div>`; }
  return `<div class="ra-al" id="raAlio">`+head+pick+`<div id="raAlioRes">${raAlioResView(mode)}</div></div>`;
}
function raAlioRedraw(mode){ const b=document.getElementById('raAlio'); if(b) b.outerHTML=raAlioView(mode); }
function raAlioPick(mode,id,on){ const S=raAl(mode); S.picked=S.picked.filter(x=>x!==id); if(on) S.picked.push(id); _raSave(); }
function raAlioStop(mode){ _raAlioRun++; raAl(mode).busy=false; _raSave(); raAlioRedraw(mode); }
async function raAlioSearch(mode){
  const S=raAl(mode); if(!String(S.q).trim()&&!S.cat){ _toast('규정명 검색어를 넣으세요.'); return; }
  const box=document.getElementById('raAlioRes'); if(box) box.innerHTML=raSpin('알리오 기관 목록을 불러오는 중...');
  let D; try{ D=await raAlioOrgs(); }catch(e){ if(box) box.innerHTML=raErr(e.message); return; }
  const ids=raAlioScopeIds(D,S.scope,S.picked); if(!ids.length){ if(box) box.innerHTML=raErr('조회할 기관을 고르세요.'); return; }
  const run=++_raAlioRun, B=D.batch||12;
  S.busy=true; S.res={q:S.q.trim(), cat:S.cat, total:ids.length, searched:0, hits:[], failed:[], timedOut:[]}; S.open={}; raAlioRedraw(mode);
  for(let i=0;i<ids.length;i+=B){
    if(run!==_raAlioRun) return;
    const d=await raPost('/api/regagent/alio/search',{q:S.res.q, category:S.cat, orgs:ids.slice(i,i+B)});
    if(run!==_raAlioRun){ raAlioRedraw(mode); return; }
    if(!d.success){ S.res.error=d.error||'알리오 조회 실패'; break; }
    S.res.hits.push(...d.hits); S.res.failed.push(...d.failed); S.res.timedOut.push(...d.timedOut); S.res.searched+=d.searched; (S.res.truncated=S.res.truncated||[]).push(...(d.truncated||[]));
    const b=document.getElementById('raAlioRes'); if(b) b.innerHTML=raAlioResView(mode);
  }
  if(S.res.timedOut.length&&run===_raAlioRun&&!S.res.error){         // 시간 안에 못 본 기관은 한 번 더(나눠서)
    const again=S.res.timedOut.splice(0).map(t=>t.orgId);
    for(let i=0;i<again.length&&run===_raAlioRun;i+=4){
      const d=await raPost('/api/regagent/alio/search',{q:S.res.q, category:S.cat, orgs:again.slice(i,i+4)});
      if(!d.success){ again.slice(i,i+4).forEach(id=>S.res.timedOut.push({orgId:id,org:id,error:'시간 제한'})); continue; }
      S.res.hits.push(...d.hits); S.res.failed.push(...d.failed); S.res.timedOut.push(...d.timedOut); S.res.searched+=d.searched;
    }
  }
  S.busy=false; _raSave(); raAlioRedraw(mode);
}
function raAlioResView(mode){
  const S=raAl(mode), R=S.res; if(!R) return `<div class="ra-empty sm">${raIc('search')}다른 기관 사규를 찾아보세요 ${raTip('예) 제정 “드론 운영지침” → 검색어 “드론”, 개정 “여비규정” → “여비”')}</div>`;
  const hits=R.hits.filter(h=>S.old||!h.superseded);
  const pct=R.total?Math.round(R.searched/R.total*100):0;
  let html=(S.busy?`<div class="ra-prog"><i style="width:${pct}%"></i></div>`:'')+
    `<div class="ra-meta">${R.searched}/${R.total}곳 조회 · 규정 <b>${hits.length}</b>건${R.hits.length>hits.length?` <button class="ra-link" onclick="raAl('${mode}').old=true;raAlioRedraw('${mode}')">옛 판 ${R.hits.length-hits.length}건 보기</button>`:''}`+
    (R.failed.length+R.timedOut.length?` · <span class="ra-chip warn" title="${_e([...R.failed,...R.timedOut].map(f=>f.org+': '+f.error).join('\n'))}">조회 못 한 기관 ${R.failed.length+R.timedOut.length}곳</span>`:'')+
    ((R.truncated||[]).length?` · <span class="ra-chip warn" title="${_e(R.truncated.map(t=>`${t.org}: ${t.total}건 중 ${t.shown}건`).join('\n'))}">일부만 표시 ${R.truncated.length}곳 — 검색어를 넣으세요</span>`:'')+`</div>`;
  if(R.error) html+=raErr(R.error);
  if(!hits.length) return html+(S.busy?'':`<div class="ra-empty sm">찾은 규정이 없습니다. 검색어를 줄이거나(예: “여비규정” → “여비”) 조회 범위를 넓혀 보세요.</div>`);
  const sel=raAlioSel(mode);
  html+=`<ul class="ra-al-l">`+hits.slice(0,80).map(h=>{ const k=h.orgId+'|'+h.idx, O=S.open[k];
    const nsel=Object.keys(sel).filter(x=>x.startsWith('alio|'+k+'|')).length;
    return `<li class="${O?'on':''}"><div class="ra-al-h"><button class="ra-link ra-al-t" onclick="raAlioOpen('${mode}','${_a(k)}')">${_e(h.title)}</button>`+
      `<span class="ra-sub">${_e(h.org)} · ${_e(h.categoryName)} · 시행 ${_e(h.enf||'-')}</span>${h.superseded?'<span class="ra-chip">옛 판</span>':''}${nsel?`<span class="ra-chip sem">참고 ${nsel}</span>`:''}</div>`+
      (O?`<div class="ra-al-b">${raAlioRuleView(mode,k,h,O)}</div>`:'')+`</li>`; }).join('')+`</ul>`+(hits.length>80?`<div class="ra-meta">외 ${hits.length-80}건 — 검색어를 더 구체적으로 넣으세요</div>`:'');
  return html;
}
function raAlioSel(mode){ const S=RA[mode]; if(mode==='enact') return S.refs=S.refs||{}; return S.alioRefs=S.alioRefs||{}; }
async function raAlioOpen(mode, k){
  const S=raAl(mode); if(S.open[k]&&!S.open[k].err){ delete S.open[k]; raAlioResRedraw(mode); return; }
  const h=S.res.hits.find(x=>x.orgId+'|'+x.idx===k); if(!h) return;
  S.open[k]={loading:true}; raAlioResRedraw(mode);
  const ctx=mode==='enact'?[S.res.q,RA.enact.purpose,RA.enact.contents].join(' '):[S.res.q,RA.amend.intent,...Object.keys(RA.amend.sel||{}).map(no=>(raOld(no)||{}).title||'')].join(' ');
  const d=await raPost('/api/regagent/alio/rule',{orgId:h.orgId, idx:h.idx, category:h.category, table:h.table, idxName:h.idxName, mod:h.mod, kw:S.res.q, q:ctx.slice(0,300)});
  if(S.open[k]&&S.open[k].loading) S.open[k]=d.success?{data:d}:{err:d.error||'규정 파일을 읽지 못했습니다.'}; raAlioResRedraw(mode);
}
function raAlioResRedraw(mode){ const b=document.getElementById('raAlioRes'); if(b) b.innerHTML=raAlioResView(mode); }
function raAlioRuleView(mode,k,h,O){
  if(O.loading) return raSpin('알리오에서 현행본 파일을 받아 조문을 읽는 중... (5~15초)');
  if(O.err) return raErr(O.err)+`<button class="ra-link" onclick="raAlioOpen('${mode}','${_a(k)}')">다시 시도</button>`;
  const d=O.data, sel=raAlioSel(mode);
  const rel=x=>x.rel!==undefined?x.rel:x.score>0;
  const arts=(d.articles.some(rel)?d.articles.filter(rel):d.articles).slice(0,8);
  return `<div class="ra-meta">${_e(d.file.fileName)} · ${d.count}개 조${d.versions>1?` · 제·개정 이력 ${d.versions}건 중 현행본`:''} <a class="ra-link" href="${_e(d.url)}" target="_blank" rel="noopener">알리오 원문↗</a></div>`+
    (d.warning?`<div class="ra-note ra-note-i">${raIc('info')}<span>${_e(d.warning)}</span></div>`+(d.excerpt?`<pre class="ra-doc" style="max-height:220px">${_e(d.excerpt)}</pre>`:''):'')+
    arts.map(a=>{ const key=`alio|${k}|${a.no}`;
      return `<label class="ra-sima"><input type="checkbox" ${sel[key]?'checked':''} onchange="raAlioRef('${mode}','${_a(key)}',this.checked)"><span><b>${_e(raLbl(a.no))}(${_e(a.title)})</b>${rel(a)?' <span class="ra-chip sem">관련</span>':''}<br><em>${_e(a.body.slice(0,320))}${a.body.length>320?'…':''}</em></span></label>`; }).join('')+
    (d.toc.length?`<details class="ra-det"><summary>조문 체계 ${d.toc.length}개 조</summary><div class="ra-toc" style="display:block">${d.toc.map(_e).join(' · ')}</div></details>`:'');
}
function raAlioRef(mode, key, on){
  const S=raAl(mode), sel=raAlioSel(mode); const [,org,idx,no]=key.split('|');
  const h=S.res.hits.find(x=>x.orgId===org&&x.idx===idx), O=S.open[org+'|'+idx]; const a=O&&O.data&&O.data.articles.find(x=>x.no===no);
  if(on&&h&&a) sel[key]={reg:alioBase(h.title), org:h.org, no:a.no, title:a.title, body:a.body, src:'alio'}; else delete sel[key];
  _raSave(); const c=document.getElementById('raRefCnt'); if(c) c.textContent=Object.keys(sel).length;
  const t=document.getElementById('raAlioCnt'); if(t) t.textContent=Object.keys(sel).length;
}
function alioBase(t){ return String(t||'').replace(/[(（\[]\s*(?:제정|개정|시행|전부개정|일부개정)?\s*[`'’]?[\d.\s년월일~-]{4,}\s*(?:제정|개정|시행)?\s*[)）\]]/g,'').trim(); }


// 에이전트·검토용: 유관 기관에서 규정을 찾아 현행본 조문 가운데 관련 조문을 골라 온다(알리오)
// → {hits, refs:{key:{reg,org,no,title,body,src}}, opened:[{h,d}], note}. 알리오에 닿지 않으면 note 에 사유를 담고 빈 결과
async function raAlioCollect(q, ctx, o){
  o=Object.assign({maxRules:2, maxArts:2, scope:'peer'},o||{});
  const out={hits:[], refs:{}, opened:[], note:'', orgs:0, failed:[]};
  let D; try{ D=await raAlioOrgs(); }catch(e){ out.note=e.message; return out; }
  const ids=raAlioScopeIds(D,o.scope);
  out.orgs=ids.length; if(!ids.length){ out.note='유관 기관이 설정되어 있지 않습니다(org_config.json alio.peer_depts).'; return out; }
  const B=D.batch||12;
  for(let i=0;i<ids.length;i+=B){
    const d=await raPost('/api/regagent/alio/search',{q, orgs:ids.slice(i,i+B)});
    if(!d.success){ out.note=d.error||'알리오 조회 실패'; break; }
    out.hits.push(...d.hits.filter(h=>!h.superseded)); out.failed.push(...(d.failed||[]),...(d.timedOut||[]));
  }
  if(!out.hits.length&&out.failed.length&&out.failed.length>=ids.length/2&&!out.note)
    out.note=`유관 기관 ${out.failed.length}곳을 조회하지 못했습니다(${(out.failed[0]||{}).error||'알리오 응답 없음'})`;
  const toks=String(q).replace(/\s+/g,'');
  out.hits.sort((a,b)=>(alioBase(a.title).replace(/\s+/g,'').startsWith(toks)?0:1)-(alioBase(b.title).replace(/\s+/g,'').startsWith(toks)?0:1)||String(b.enf).localeCompare(String(a.enf)));
  const seenOrg=new Set(); let tries=0;
  for(const h of out.hits){
    if(out.opened.length>=o.maxRules||tries>=o.maxRules*2) break;   // 실패해도 시도 수는 정해 둔다
    if(seenOrg.has(h.orgId)) continue;                      // 기관마다 하나씩
    tries++;
    const d=await raPost('/api/regagent/alio/rule',{orgId:h.orgId, idx:h.idx, category:h.category, table:h.table, idxName:h.idxName, mod:h.mod, kw:q, q:String(ctx||'').slice(0,300)});
    if(!d.success){ if(/^(SCHEMA|NETWORK)$/.test(d.kind||'')){ out.note=d.error||out.note; break; } continue; }
    seenOrg.add(h.orgId); out.opened.push({h,d});
    d.articles.filter(a=>a.rel!==undefined?a.rel:a.score>0).slice(0,o.maxArts).forEach(a=>{ out.refs[`alio|${h.orgId}|${h.idx}|${a.no}`]={reg:alioBase(h.title), org:h.org, no:a.no, title:a.title, body:a.body, src:'alio'}; });
  }
  return out;
}
function raAlioRefList(mode){ const R=mode==='enact'?RA.enact.refs:RA.amend.alioRefs; return Object.values(R||{}).filter(r=>r&&r.src==='alio'); }
function raAlioRefLine(r){ return `${r.org} 「${r.reg}」 ${raLbl(r.no)}(${r.title})`; }
async function raAgAlioStep(mode, q, ctx, step, fin){
  const s=step('다른 기관 사례 조사(알리오)');
  const R=String(q||'').trim()?await raAlioCollect(q, ctx):{hits:[],refs:{},opened:[],note:'',orgs:0,failed:[]};
  if(R.note&&!R.hits.length){ fin(s,`알리오를 조회하지 못해 건너뜁니다: ${_e(R.note)}`,'skip'); return {}; }
  if(!String(q||'').trim()){ fin(s,'내규명이 정해지지 않아 다른 기관 검색을 건너뜁니다. 결과 화면의 “참고 자료” 단계에서 찾을 수 있습니다.','skip'); return {}; }
  if(!R.hits.length){ fin(s,`유관 기관 ${R.orgs}곳에서 “${_e(q)}” 규정을 찾지 못했습니다.`+(R.failed.length?` (${R.failed.length}곳 조회 못 함)`:''),'skip'); return {}; }
  const n=Object.keys(R.refs).length;
  fin(s,`유관 기관 ${R.orgs}곳에서 ${R.hits.length}건: `+R.hits.slice(0,4).map(h=>`${_e(h.org)} 「${_e(alioBase(h.title))}」`).join(', ')+(R.hits.length>4?' 외':'')+
    (n?`<br>참고 조문 ${n}개: `+Object.values(R.refs).map(r=>_e(raAlioRefLine(r))).join(', '):'<br>관련 조문을 고르지 못했습니다. 결과 화면의 “다른 기관(알리오)”에서 직접 고르세요.'), n?'ok':'warn');
  raAlioSet(mode, q, R);
  return R.refs;
}
async function raAgCompare(P, step, fin, stop){
  const q=P.keyword;
  let s=step(`유관 기관에서 “${q}” 규정 찾기(알리오)`);
  const R=await raAlioCollect(q, RA.agent.req, {maxRules:3, maxArts:3});
  if(R.note&&!R.hits.length) stop(s,`알리오를 조회하지 못했습니다: ${R.note}`);
  if(!R.hits.length){
    fin(s,`유관 기관 ${R.orgs}곳에는 “${_e(q)}” 규정이 없습니다.`+(R.failed.length?` (${R.failed.length}곳은 조회하지 못했습니다)`:''),'warn');
    RA.agent.done={title:'유관 기관에서 찾지 못했습니다',sub:'제정 화면의 “다른 기관(알리오)”에서 범위를 “같은 유형”·“전체”로 넓혀 찾아보세요.',acts:[['다른 기관 검색 열기',"RA.enact.simSrc='alio';RA.enact.refTab='alio';RA.enact.step=1;raAl('enact').q="+JSON.stringify(q).replace(/"/g,"'")+";raTab('enact')",1]]};
    return;
  }
  const orgs=[...new Set(R.hits.map(h=>h.org))];
  fin(s,`유관 기관 ${R.orgs}곳 중 ${orgs.length}곳에 ${R.hits.length}건: `+R.hits.slice(0,6).map(h=>`${_e(h.org)} 「${_e(alioBase(h.title))}」(시행 ${_e(h.enf||'-')})`).join('<br>'));
  s=step('현행본 조문 비교');
  if(!R.opened.length) fin(s,'규정 파일을 읽지 못했습니다(첨부 없음·암호 문서 등). 알리오 원문에서 확인하세요.','warn');
  else fin(s,R.opened.map(({h,d})=>`<b>${_e(h.org)} 「${_e(alioBase(h.title))}」</b> ${d.count}개 조 · `+(d.articles.filter(a=>a.score>0).slice(0,3).map(a=>`${raLbl(a.no)}(${_e(a.title)})`).join(', ')||'관련 조문 없음')).join('<br>'));
  const own=(await raCatalog()).filter(r=>r.title.replace(/\s+/g,'').includes(String(q).replace(/\s+/g,'')));
  s=step(`우리 ${RA_ORG.reg_word}와 견주기`);
  fin(s,own.length?`우리 기관에도 있습니다: ${own.slice(0,3).map(r=>'「'+_e(r.title)+'」').join(', ')} — 개정할 때 다른 기관 조문을 참고하세요.`:`우리 기관에는 “${_e(q)}” ${_e(RA_ORG.reg_word)}가 없습니다 — 제정을 검토할 수 있습니다.`, own.length?'ok':'warn');
  RA.agent.pendingAlio={q, R:{orgs:R.orgs, hits:R.hits, opened:R.opened}};
  RA.agent.pendingRefs=R.refs;
  const acts=[];
  if(own.length) acts.push([`「${own[0].title}」 개정에 참고하기`,`raAgUseRefs('amend','${_a(own[0].slug)}','${_a(own[0].title)}')`,1]);
  acts.push([own.length?'새 내규 제정에 참고하기':`“${q}” ${RA_ORG.reg_word} 제정 시작`,`raAgUseRefs('enact','','${_a(q)}')`,!own.length]);
  RA.agent.done={title:`다른 기관 ${orgs.length}곳의 “${q}” 규정을 찾았습니다`,sub:`참고 조문 ${Object.keys(R.refs).length}개를 골라 두었습니다. 제정·개정 화면으로 가져가 AI 초안에 참고합니다.`,acts};
}
// 에이전트가 고른 다른 기관 조문을 제정·개정 작업으로 가져간다
function raAgUseRefs(mode, slug, title){
  const refs=RA.agent.pendingRefs||{};
  const PA=RA.agent.pendingAlio; if(PA) raAlioSet(mode, PA.q, PA.R);
  if(mode==='amend'){ raAmendStart(slug, title, {}); RA.amend.alioRefs=Object.assign({},refs); RA.amend.alioOpen=true; RA.amend.step=1; _raSave(); raRerender('amend'); return; }
  const want=/(규정|규칙|지침|요령|기준)$/.test(title)?title:`${title} 운영지침`;
  if(RA.enact.title&&RA.enact.title!==want&&(RA.enact.draft||RA.enact.purpose)){
    if(!confirm(`진행 중인 제정 작업(「${RA.enact.title}」)을 지우고 「${want}」 제정을 새로 시작할까요?`)) return;
    raGenBump('enact'); RA.enact=_raBlank().enact; }
  const E=RA.enact; if(!E.title&&title) E.title=want;
  E.category=raCatOf(E.title)||E.category; E.simSrc='alio'; E.refTab='alio'; E.step=1; E.refs=Object.assign(E.refs||{},refs); _raSave(); raTab('enact');
}


// ── 유관 기관 규정 체계 비교(알리오) — 다른 기관은 두고 있는데 우리에게 없는 규정 찾기 ─────────────
// 규정명에서 날짜 괄호·기관명·종류 끝말(규정·규칙·지침…)을 떼어 “주제어”로 견준다(예: “여비 지급규정” → “여비지급”).
function raBenchKey(t, orgNames){
  let k=alioBase(t).replace(/\s+/g,'');
  (orgNames||[]).forEach(n=>{ if(n&&k.startsWith(n)) k=k.slice(n.length); });
  for(let i=0;i<2;i++) k=k.replace(/(시행세칙|운영세칙|세칙|운영규정|운영규칙|운영지침|관리규정|관리규칙|관리지침|업무처리규정|처리규정|규정|규칙|지침|요령|기준|예규|매뉴얼|편람|내규)$/,'');
  return k.replace(/(에관한|에대한|등에관한|및)$/,'').replace(/^(임직원|직원)/,'');
}
// 같은 주제인지: 같거나, 짧은 쪽이 3자 이상이고 긴 쪽의 70% 이상을 덮을 때만(“인사” ⊂ “인사평가”는 다른 규정)
function raBenchSame(a, b){ if(!a||!b) return false; if(a===b) return true; const [s,l]=a.length<b.length?[a,b]:[b,a]; return s.length>=3&&l.includes(s)&&s.length/l.length>=0.7; }
function raBenchHas(keys, k){ return keys.some(x=>raBenchSame(x,k)); }
async function raBenchRun(){
  if(_raBusy.bench) return; _raBusy.bench=true;
  const box=()=>document.getElementById('raBench');
  try{
    let D; try{ D=await raAlioOrgs(); }catch(e){ if(box()) box().innerHTML=raErr(e.message); return; }
    const ids=D.peers.slice(); if(!ids.length){ if(box()) box().innerHTML=raErr('유관 기관이 없습니다. org_config.json 의 alio.peer_depts 를 설정하세요.'); return; }
    const hits=[], miss=[]; const B=D.batch||12;
    const call=async part=>{ const d=await raPost('/api/regagent/alio/search',{q:'', all:true, orgs:part});
      if(!d.success) throw new Error(d.error||'알리오 조회 실패'); hits.push(...d.hits.filter(h=>!h.superseded)); return [...d.failed,...d.timedOut]; };
    for(let i=0;i<ids.length;i+=B){
      if(box()) box().innerHTML=raSpin(`유관 기관 ${ids.length}곳의 규정 목록을 알리오에서 받는 중... ${Math.min(i+B,ids.length)}/${ids.length}`);
      try{ miss.push(...await call(ids.slice(i,i+B))); }catch(e){ if(box()) box().innerHTML=raErr(e.message); return; }
    }
    for(const m of miss.splice(0)){ try{ miss.push(...await call([m.orgId])); }catch(e){ miss.push(m); } }   // 한 번 더(한 곳씩)
    const names=D.orgs.map(o=>o.name.replace(/\s+/g,'')).concat([RA_ORG.org_name,RA_ORG.org_short].map(x=>String(x||'').replace(/\s+/g,'')));
    const byKey={};
    hits.forEach(h=>{ const k=raBenchKey(h.title,names); if(k.length<2) return; const g=byKey[k]=byKey[k]||{k,orgs:{},titles:[]}; if(!g.orgs[h.orgId]){ g.orgs[h.orgId]=h.org; g.titles.push(h); } });
    const own=(await raCatalog()).map(r=>({k:raBenchKey(r.title,names), r}));
    const ownKeys=own.map(x=>x.k).filter(Boolean);
    const rows=Object.values(byKey).map(g=>({k:g.k, n:Object.keys(g.orgs).length, orgs:Object.values(g.orgs), ex:g.titles.slice(0,4).map(h=>({org:h.org,title:alioBase(h.title),orgId:h.orgId,idx:h.idx,category:h.category,table:h.table,idxName:h.idxName,mod:h.mod})),
      mine:(own.find(x=>raBenchSame(x.k,g.k))||{}).r||null}));
    rows.sort((a,b)=>b.n-a.n||a.k.localeCompare(b.k));
    const okN=ids.length-miss.length;
    if(!hits.length||okN<Math.ceil(ids.length/2)){                // 대부분 조회 실패 — 이전 결과를 지우지 않는다
      if(box()) box().innerHTML=raErr(`유관 기관 ${ids.length}곳 중 ${okN}곳만 조회되어 비교하지 않았습니다. 잠시 뒤 다시 시도하세요.`)+(RA.health.bench?raBenchView():'');
      return;
    }
    RA.health.bench={at:raToday(0), peers:ids.length, ok:okN, failed:miss.map(m=>m.org), total:hits.length, rows:rows.slice(0,300)};
    _raSave(); if(box()) box().innerHTML=raBenchView();
  } finally{ _raBusy.bench=false; }
}
function raBenchView(){
  const B=RA.health.bench;
  const btn=`<button class="svc-btn" onclick="raBenchRun()">${raIc('search')}${B?'다시 비교':'유관 기관과 비교'}</button>`;
  if(!B) return `<div class="ra-row">${btn}${raTip('알리오에서 유관 기관의 규정 목록을 받아 견줍니다(1~2분).')}</div>`;
  const min=Math.max(2,Math.ceil(B.ok*0.3));
  const gap=B.rows.filter(r=>!r.mine&&r.n>=min).slice(0,15), common=B.rows.filter(r=>r.mine&&r.n>=min);
  const tone=gap.length?'warn':'ok';
  const card=r=>`<li><div class="ra-al-h"><b>${_e(r.ex[0].title)}</b><span class="ra-chip ${r.mine?'':'warn'}">${r.n}곳</span>${r.mine?` <span class="ra-sub">우리: 「${_e(r.mine.title)}」</span>`:''}</div>`+
    `<div class="ra-sub">${r.ex.map(e=>`${_e(e.org)} 「${_e(e.title)}」`).join(' · ')}${r.n>r.ex.length?` 외 ${r.n-r.ex.length}곳`:''}</div>`+
    `<div class="ra-row" style="margin:6px 0 0">${r.mine?`<button class="svc-btn sm" onclick="raBenchUse('amend','${_a(r.k)}')">${raIc('amend')}다른 기관 조문 보며 개정</button>`:`<button class="svc-btn sm yes" onclick="raBenchUse('enact','${_a(r.k)}')">${raIc('enact')}제정 검토 시작</button>`}</div></li>`;
  return `<div class="ra-row">${btn}<span class="ra-meta">${_e(B.at)} 기준 · 유관 기관 ${B.ok}/${B.peers}곳 · 규정 ${B.total}건${B.failed.length?` · 조회 못 한 기관: ${B.failed.map(_e).join(', ')}`:''}</span></div>`+
    raStats([{v:gap.length,l:`유관 기관 ${min}곳 이상이 두었지만 우리에게 없는 규정`,ic:'alert',tone},{v:common.length,l:'유관 기관과 공통인 규정',ic:'check',tone:'ok'}])+
    (gap.length?`<div class="ra-ih">우리에게 없는 규정 ${raTip('여러 유관 기관이 공통으로 둔 규정입니다. 업무 성격이 맞으면 제정을 검토하세요. 이름이 달라 같은 규정을 놓쳤을 수 있으니 확인하세요.')}</div><ul class="ra-al-l">${gap.map(card).join('')}</ul>`:`<div class="ra-ok">${raIc('check')}유관 기관 다수가 둔 규정은 우리 기관에도 있습니다.</div>`)+
    (common.length?`<details class="ra-det"><summary>공통 규정 ${common.length}개 — 개정할 때 다른 기관 조문을 견줄 수 있습니다</summary><ul class="ra-al-l">${common.slice(0,30).map(card).join('')}</ul></details>`:'');
}
// 비교 결과 → 제정(없는 규정)·개정(공통 규정): 알리오 검색 결과를 미리 채워 다른 기관 조문을 바로 열어 보게 한다
function raBenchUse(mode, k){
  const B=RA.health.bench, r=B&&B.rows.find(x=>x.k===k); if(!r) return;
  const hits=r.ex.map(e=>({org:e.org, orgId:e.orgId, title:e.title, idx:e.idx, category:e.category, table:e.table, idxName:e.idxName, mod:e.mod, enf:'', categoryName:'', superseded:false}));
  const setAl=m=>Object.assign(raAl(m),{q:k, res:{q:k, cat:'', total:B.peers, searched:B.ok, hits, failed:[], timedOut:[]}, open:{}, busy:false});
  if(mode==='enact'){ const E=RA.enact; if(E.draft&&!confirm('진행 중인 제정 작업은 그대로 두고, 이 규정을 “참고 자료” 단계의 다른 기관 검색 결과로 엽니다. 계속할까요?')) return;
    setAl('enact');
    if(!E.draft){ const orgs=(_raAlioOrgs&&_raAlioOrgs.orgs||[]).map(o=>o.name);
      let t=alioBase(r.ex[0].title).trim(); orgs.concat([r.ex[0].org]).forEach(n=>{ if(n&&t.startsWith(n)) t=t.slice(n.length).trim(); });
      E.title=t||r.ex[0].title; E.category=raCatOf(E.title)||E.category; E.purpose=E.purpose||`유관 기관 ${r.n}곳이 운영하는 ${k} 관련 사항을 정하기 위함`; }
    E.simSrc='alio'; E.refTab='alio'; E.step=1; _raSave(); raTab('enact'); return; }
  setAl('amend'); raAmendStart(r.mine.slug, r.mine.title, {}); RA.amend.alioOpen=true; RA.amend.step=1; _raSave(); raRerender('amend');
}

function raReset(mode){
  if(!confirm(mode==='enact'?'제정 작업 내용을 지우고 새로 시작할까요?':'개정 작업 내용을 지우고 새로 시작할까요?')) return;
  raGenBump(mode); RA[mode]=_raBlank()[mode]; if(mode==='amend') _raArts=null; _raSave(); raRender();
}
