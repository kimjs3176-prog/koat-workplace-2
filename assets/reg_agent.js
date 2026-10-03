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
  spark:'<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/>',
  search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  doc:'<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  alert:'<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  bad:'<circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/>',
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
  ['proc','절차 안내','기관 제·개정 절차와 할 일'],
];
const RA_PAGE={
  agent:['에이전트에게 맡기기','하고 싶은 일을 한 문장으로 적으면, 에이전트가 대상 내규와 조문을 찾아 초안부터 영향 분석·점검·심의 사전검토·문서 세트까지 이어서 수행합니다.'],
  health:['규정 건강검진','기관 내규 전체를 진단해 건강 점수와 등급을 매기고, 먼저 정비해야 할 내규를 이유와 함께 알려 줍니다.'],
  enact:['새 내규 제정','목적과 주요 내용을 정리하면 유사 규정·상위법을 참고해 조문 초안을 쓰고, 심의 사전검토와 제정 문서 세트까지 만듭니다.'],
  amend:['내규 개정','고칠 조문과 개정 의도를 정하면 수정안과 신구조문대비표를 만들고, 이 조문을 인용하는 곳까지 찾아 정정합니다.'],
  bulk:['용어·명칭 일괄 정비','직제 개편이나 명칭 변경 때 모든 내규에서 해당 용어를 찾아 조사까지 맞춰 바꾸고, 개정문·부칙을 만듭니다.'],
  upper:['상위법 개정 영향 분석','상위 법령이 바뀌면 그 법령을 인용하는 내규 조문을 찾아 개정 후보로 보여 주고, 바로 개정 작업으로 넘깁니다.'],
  check:['내규 점검','없는 조문 인용, 현행 목록에 없는 내규명, 옛 기관명·직위, 조 번호 중복을 찾습니다.'],
  proc:['제·개정 절차 안내','해당 여부에 답하면 기관 내규관리 규칙에 맞춰 필요한 단계와 문서를 순서대로 보여 줍니다.'],
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
    amend:{src:'reg',pasteText:'',pasted:false,moves:'',review:null,slug:'',title:'',sel:{},intent:'',effective:'',refText:'',changes:[],purpose:'',main:[],addenda:'',notes:[],impact:null,lint:null,docTab:'cmp',filter:'',abbr:true},
    upper:{law:'',arts:'',old:'',neu:'',res:null},
    check:{res:null,reg:'',one:null},
    proc:{ans:{},chk:{}}};
}
function _raLoad(){
  try{ const o=JSON.parse(localStorage.getItem(RA_KEY)||'null'); if(o&&o.enact) return Object.assign(_raBlank(),o); }catch(e){}
  return _raBlank();
}
let RA=_raLoad(); RA.agent=Object.assign({req:'',steps:[],plan:null,done:null},RA.agent||{},{running:false}); (RA.agent.steps||[]).forEach(s=>{ if(s.st==='run') s.st='err'; }); RA.health=Object.assign({law:{},f:{q:'',g:''}},RA.health||{});
let _raArts=null, _raCatalog=null, _raSaveT=null, _raBusy={};
function _raSave(){ clearTimeout(_raSaveT); _raSaveT=setTimeout(()=>{ try{ localStorage.setItem(RA_KEY, JSON.stringify(RA)); }catch(e){ if(typeof _toast==='function') _toast('작업 내용을 저장하지 못했습니다(브라우저 저장 공간 부족).'); } },300); }
function raSet(path, val){ const ks=path.split('.'); let o=RA; for(let i=0;i<ks.length-1;i++) o=o[ks[i]]; o[ks[ks.length-1]]=val; _raSave(); }
const _e=s=>escHtml(String(s==null?'':s));
const _a=s=>argAttr(String(s==null?'':s));

// ── 공용 유틸 ───────────────────────────────────────────────────────────────
function raKey(no){ const m=String(no||'').match(/(\d+)(?:의(\d+))?/); return m?[+m[1],+(m[2]||0)]:[0,0]; }
function raCmp(a,b){ const x=raKey(a), y=raKey(b); return x[0]-y[0]||x[1]-y[1]; }
function raLbl(no){ const k=raKey(no); return `제${k[0]}조`+(k[1]?`의${k[1]}`:''); }
function raNormNo(s){ return String(s||'').replace(/제|조/g,'').replace(/\s+/g,'').replace(/[^0-9의]/g,''); }
function raJosa(w,p){ p=p||['은','는']; const c=String(w||'').trim().slice(-1); if(c>='가'&&c<='힣') return ((c.charCodeAt(0)-0xAC00)%28)?p[0]:p[1]; return p[0]; }
function raKind(title){ const t=String(title||'').trim(); for(const s of ['시행세칙','정관','규정','규칙','세칙','지침','요령','기준','매뉴얼','강령']) if(t.endsWith(s)) return s; return '규정'; }
function raToday(add){ const d=new Date(); d.setDate(d.getDate()+(add||0)); return `${d.getFullYear()}. ${d.getMonth()+1}. ${d.getDate()}.`; }
function raAi(){ const s=getAiSettings(); const p=s.provider||''; return p?{provider:p, api_key:s['key_'+p]||'', model:s['model_'+p]||''}:{}; }
function raHasAi(){ const s=getAiSettings(); const p=s.provider||''; return !!(p&&(s['key_'+p]||p==='ollama')); }
async function raPost(url, body){
  const s=getAiSettings(); const h={'Content-Type':'application/json'};
  if(s.key_gemini) h['X-Gemini-Key']=s.key_gemini;     // 유사 규정 의미 검색(헤더로만 전달)
  const r=await fetch(url,{method:'POST',headers:h,body:JSON.stringify(body||{})});
  let d={}; try{ d=await r.json(); }catch(e){ d={success:false,error:`서버 응답 오류(${r.status})`}; }
  if(!r.ok && d.success!==false) d.success=false;
  return d;
}
async function raGet(url){ const r=await fetch(url); try{ return await r.json(); }catch(e){ return {success:false,error:`서버 응답 오류(${r.status})`}; } }
function raSpin(t){ return `<div class="assist-loading"><div class="spinner"></div><span>${_e(t)}</span></div>`; }
function raErr(msg, needKey){ return `<div class="ra-err">${raIc('alert')}<span>${_e(msg)}</span>${needKey?` <button class="svc-btn sm" onclick="openAiModal()">${raIc('spark')}AI 설정</button>`:''}</div>`; }
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
    if(/^부\s*칙/.test(ln)){ zone='add'; add.push(ln); return; }
    const mc=ln.match(/^제\s*\d+\s*(장|절|관|편)\s*\S.{0,38}$/);
    if(mc && !/[.。]$/.test(ln) && !/^제\s*\d+\s*조/.test(ln)){ chap=ln; chapters.push(ln); return; }
    const m=ln.match(/^제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*(?:[(（]([^)）]{0,60})[)）])?\s*(.*)$/);
    if(m && (m[3]!=null || /^삭제/.test(m[4]||''))){
      cur={no:m[1]+(m[2]?'의'+m[2]:''), title:(m[3]||'').trim(), body:(m[4]||'').trim(), chapter:chap, deleted:!m[3]&&/^삭제/.test(m[4]||'')};
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
    const n=Math.max(dels.length,ins.length);
    for(let i=0;i<n;i++){
      const d=dels[i], s=ins[i];
      if(d!=null&&s!=null){ const [x,y]=raWordDiff(d,s); L.push(x); R.push(y); LP.push(d); RP.push(s); }
      else if(d!=null){ L.push(`<u class="ra-d">${_e(d)}</u>`); LP.push(d); }
      else { R.push(`<u class="ra-i">${_e(s)}</u>`); RP.push(s); }
    }
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
  const [pt,pd]=RA_PAGE[RA.tab]||['',''];
  const ai=raHasAi()?`<span class="ra-pill ok">${raIc('spark')}AI 연결됨</span>`:`<button class="ra-pill" onclick="openAiModal()" title="AI 키를 넣으면 초안·수정안·검토의견을 AI가 씁니다">${raIc('spark')}AI 미설정 · 템플릿/직접 작성</button>`;
  p.innerHTML=(nav?'':`<div class="ra-tabs" role="tablist">${tabs}</div>`)+
    `<header class="ra-page"><div class="ra-page-ic">${raIc(RA.tab)}</div><div class="ra-page-t"><h1>${_e(pt)}</h1><p>${_e(pd)}</p></div><div class="ra-page-a">${ai}<span class="ra-pill subtle">「${_e(raRules())}」 기준</span></div></header>`+
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
    `<div class="oc-row">${srv}</div><div class="oc-row">${raHasAi()?'<span class="badge ok">AI 연결됨</span>':'<span class="badge">AI 미설정</span>'}</div>`;
}
function raRender(){
  if(!_raCatalog) raCatalog().then(()=>{ if(RA.tab==='enact') raRerender('enact'); });
  const b=document.getElementById('raBody'); if(!b) return;
  const t=RA.tab;
  if(t==='enact') b.innerHTML=raLayout(raEnactView(), raProcSide('enact'));
  else if(t==='amend'){ b.innerHTML=raLayout(raAmendView(), raProcSide('amend')); if(RA.amend.slug && !_raArts && !_raBusy.arts) raLoadArts(RA.amend.slug, true); }
  else if(t==='bulk') b.innerHTML=raBulkView();
  else if(t==='agent') b.innerHTML=raAgentView();
  else if(t==='health') b.innerHTML=raHealthView();
  else if(t==='upper') b.innerHTML=raUpperView();
  else if(t==='check') b.innerHTML=raCheckView();
  else b.innerHTML=raProcView();
  if(t==='amend'||t==='upper'||t==='check') raFillCatalog();
}
function raLayout(main, side){ return `<div class="ra-layout"><div class="ra-main">${main}</div><aside class="ra-side">${side}</aside></div>`; }
async function raFillCatalog(){
  const dl=document.getElementById('raRegList'); if(!dl || dl.dataset.ok) return;
  const regs=await raCatalog(); dl.innerHTML=regs.map(r=>`<option value="${_e(r.title)}">${_e(r.category||'')} · ${_e(r.revision||'')}</option>`).join(''); dl.dataset.ok='1';
}
function raSec(n, title, sub, body, id){ return `<section class="ra-sec"${id?` id="${id}"`:''}><div class="ra-sec-h"><span class="ra-num">${n}</span><div class="ra-sec-t"><h2>${title}</h2>${sub?`<span class="ra-sub">${sub}</span>`:''}</div></div><div class="ra-sec-b">${body}</div></section>`; }
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
    `<label class="ra-f"><span>제정 목적</span>${raTa('enact.purpose',E.purpose,'왜 이 내규가 필요한지 — 예) 업무용 드론의 안전한 운영과 사고 예방',2)}</label>`+
    `<label class="ra-f"><span>주요 내용 <em>한 줄에 하나씩 — “제목: 내용” 형식이면 조 제목으로 씁니다</em></span>${raTa('enact.contents',E.contents,'운영책임자: 부서별 드론 운영책임자를 지정\n비행승인: 비행 3일 전까지 운영책임자 승인\n보험: 배상책임보험 가입 의무',4)}</label>`;
  const s2=raDelegView();
  const s3=`<div class="ra-row"><button class="svc-btn" onclick="raFindSimilar()">${raIc('search')}유사 규정 찾기</button><span class="ra-hint">목적·주요 내용으로 기관 내규${_raCatalog?' '+_raCatalog.length+'건':''}에서 비슷한 조문을 찾습니다. 체크한 조문은 초안 작성 때 참고합니다.</span></div><div id="raSim">${raSimView()}</div>`;
  const s4=`<div class="ra-row"><button class="svc-btn yes" onclick="raEnactDraft()">${raIc('spark')}조문 초안 작성</button>`+
    `<span class="ra-hint">${raHasAi()?'AI가 위 내용·위임 조항·참고 조문으로 조문 체계와 표준 조문을 씁니다.':'AI 키가 없으면 표준 조문 골격(목적·정의·적용범위·본칙·세부사항·부칙)을 만들어 드립니다.'}</span></div><div id="raDraft">${raEnactDraftView()}</div>`;
  return raSec(1,'기본 정보','',s1)+raSec(2,'상위법 위임 조항','법령을 불러와 근거 조문을 고르세요(선택)',s2)+raSec(3,'유사 규정 참고','',s3)+raSec(4,'조문 초안','직접 고쳐 쓸 수 있습니다',s4,'raSecDraft')+
    (E.draft?raSec(5,'점검','조 번호·항 순서·인용·구 명칭·표기',`<div class="ra-row"><button class="svc-btn" onclick="raLint('enact')">점검 실행</button></div><div id="raLint">${raLintView(E.lint)}</div>`)+
      raSec(6,'심의 사전검토',`「${_e(raRules())}」 심의기준별 점검·검토의견`,raReviewSec('enact'))+
      raSec(7,'문서 세트','내규안·제정 이유서·신구조문대비표·사전예고문·의견수렴 공고·사전검토 의견서',raDocsView('enact'),'raSecDocs'):'')+
    `<div class="ra-foot"><button class="svc-btn ghost sm" onclick="raReset('enact')">↺ 제정 작업 새로 시작</button></div>`;
}
function raDelegView(){
  const E=RA.enact;
  const list=(E.dels||[]).map((d,i)=>`<div class="ra-del"><div class="ra-del-h"><b>「${_e(d.law)}」 ${_e(d.art)}</b><button class="ra-x" title="빼기" onclick="raDelRemove(${i})">✕</button></div><div class="ra-del-t">${_e(d.text).slice(0,600)}</div></div>`).join('');
  let pick='';
  if(_raBusy.law) pick=raSpin('법령 조문 불러오는 중...');
  else if(E.lawArts){
    const q=(E.lawQ||'').replace(/\s+/g,'');
    const arts=E.lawArts.filter(a=>!q||(a.label+a.title+a.text).replace(/\s+/g,'').includes(q)).slice(0,80);
    pick=`<div class="ra-pick"><div class="ra-pick-h">「${_e(E.lawName)}」 ${E.lawArts.length}개 조문 <input class="ra-in sm" placeholder="조문 검색(예: 위임, 정한다)" value="${_e(E.lawQ||'')}" oninput="RA.enact.lawQ=this.value;raRenderPick()"></div><div id="raPickList" class="ra-pick-l">`+
      arts.map(a=>`<label class="ra-pick-i"><input type="checkbox" ${E.dels.some(d=>d.law===E.lawName&&d.art===a.label)?'checked':''} onchange="raDelToggle('${_a(a.label)}',this.checked)"><span><b>${_e(a.label)}</b>${a.title?`(${_e(a.title)})`:''} <em>${_e(a.text.slice(0,140))}</em></span></label>`).join('')+
      `</div></div>`;
  }
  return `<div class="ra-row"><input id="raLawName" class="ra-in" style="max-width:280px" placeholder="법령명 (예: 농촌진흥법)" value="${_e(E.lawName||'')}" onkeydown="if(event.key==='Enter')raLawLoad()"><button class="svc-btn" onclick="raLawLoad()">조문 불러오기</button><button class="svc-btn ghost" onclick="raDelManual()">직접 입력</button></div>`+
    `<div id="raPick">${pick}</div><div class="ra-dels">${list||'<div class="ra-empty">선택한 위임 조항이 없습니다. 상위법 근거가 있으면 제1조(목적)에 반영됩니다.</div>'}</div>`;
}
function raRenderPick(){
  const E=RA.enact, box=document.getElementById('raPickList'); if(!box||!E.lawArts) return;
  const q=(E.lawQ||'').replace(/\s+/g,'');
  box.innerHTML=E.lawArts.filter(a=>!q||(a.label+a.title+a.text).replace(/\s+/g,'').includes(q)).slice(0,80)
    .map(a=>`<label class="ra-pick-i"><input type="checkbox" ${E.dels.some(d=>d.law===E.lawName&&d.art===a.label)?'checked':''} onchange="raDelToggle('${_a(a.label)}',this.checked)"><span><b>${_e(a.label)}</b>${a.title?`(${_e(a.title)})`:''} <em>${_e(a.text.slice(0,140))}</em></span></label>`).join('');
}
async function raLawLoad(){
  const nm=(document.getElementById('raLawName')||{}).value||''; if(!nm.trim()){ _toast('법령명을 입력하세요.'); return; }
  const E=RA.enact; _raBusy.law=true; E.lawName=nm.trim(); raRerender('enact');
  try{
    const d=await raGet('/api/law/articles?name='+encodeURIComponent(nm.trim()));
    if(d.error||!d.articles||!d.articles.length){ E.lawArts=null; _toast(d.error||d.message||'조문을 불러오지 못했습니다.'); }
    else{ E.lawName=d.law_name||nm.trim(); E.lawArts=d.articles.map(a=>({label:a['조문표시번호']||('제'+a['조문번호']+'조'), title:a['조문제목']||'', text:String(a['조문내용']||'').trim()})); }
  }catch(e){ _toast('법제처 연결에 실패했습니다.'); }
  _raBusy.law=false; E.lawQ=''; raRerender('enact');
}
function raDelToggle(label, on){
  const E=RA.enact; const a=(E.lawArts||[]).find(x=>x.label===label); if(!a) return;
  E.dels=E.dels.filter(d=>!(d.law===E.lawName&&d.art===label));
  if(on) E.dels.push({law:E.lawName, art:label+(a.title?`(${a.title})`:''), text:a.text.slice(0,1500)});
  _raSave(); const box=document.querySelector('.ra-dels'); if(box) raRerender('enact');
}
function raDelManual(){
  const law=prompt('상위 법령명 (예: 농촌진흥법)'); if(!law) return;
  const art=prompt('조항 (예: 제33조제2항)')||''; const text=prompt('조문 내용(요지)')||'';
  RA.enact.dels.push({law:law.replace(/[「」]/g,'').trim(), art:art.trim(), text:text.trim()}); _raSave(); raRerender('enact');
}
function raDelRemove(i){ RA.enact.dels.splice(i,1); _raSave(); raRerender('enact'); }
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
async function raEnactDraft(){
  const E=RA.enact;
  if(!(E.title||E.purpose).trim()){ _toast('내규명이나 제정 목적을 입력하세요.'); return; }
  const box=document.getElementById('raDraft'); if(box) box.innerHTML=raSpin(raHasAi()?'AI가 조문 체계와 초안을 작성하는 중... (20~40초)':'표준 조문 골격을 만드는 중...');
  const d=await raPost('/api/regagent/draft',{mode:'enact', title:E.title, category:E.category, dept:E.dept, effective:E.effective,
    purpose:E.purpose, contents:E.contents, delegations:E.dels, refs:Object.values(E.refs||{}), ...raAi()});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'초안 작성 실패', d.need_key); return; }
  const r=d.draft;
  if(r.title && !E.title) E.title=r.title;
  E.draft={text:raDraftText(r.articles), addenda:(r.addenda||[]).join('\n'), purpose:(r.reason||{}).purpose||'', main:((r.reason||{}).main||[]).join('\n'),
    notes:r.notes||[], model:r.model||'', template:!!r.template, notice:d.notice||''};
  E.lint=null; _raSave(); raRerender('enact');
  setTimeout(()=>{ const s=document.getElementById('raSecDraft'); if(s) s.scrollIntoView({behavior:'smooth',block:'start'}); },60);
  raLint('enact', true);
}
function raEnactDraftView(){
  const D=RA.enact.draft; if(!D) return '';
  return (D.notice?`<div class="ra-note ra-note-i">${raIc('info')}<span>${_e(D.notice)}</span></div>`:'')+(D.model?`<div class="ra-meta">작성: ${_e(D.model)} · AI 초안은 반드시 검토 후 사용하세요.</div>`:'')+
    `<label class="ra-f"><span>조문 <em>“제N조(제목) 본문” 형식 유지 · 항은 줄을 바꿔 ①②, 호는 1. 2.</em></span><textarea class="ra-ta mono" rows="18" oninput="raSet('enact.draft.text',this.value)">${_e(D.text)}</textarea></label>`+
    `<label class="ra-f"><span>부칙</span><textarea class="ra-ta mono" rows="2" oninput="raSet('enact.draft.addenda',this.value)">${_e(D.addenda)}</textarea></label>`+
    `<div class="ra-grid2"><label class="ra-f"><span>제정 이유</span><textarea class="ra-ta" rows="3" oninput="raSet('enact.draft.purpose',this.value)">${_e(D.purpose)}</textarea></label>`+
    `<label class="ra-f"><span>주요 내용 <em>한 줄에 하나</em></span><textarea class="ra-ta" rows="3" oninput="raSet('enact.draft.main',this.value)">${_e(D.main)}</textarea></label></div>`+
    (D.notes&&D.notes.length?`<div class="ra-note"><b>입안 시 확인할 점</b><ul>${D.notes.map(n=>`<li>${_e(n)}</li>`).join('')}</ul></div>`:'')+
    `<div class="ra-row"><button class="svc-btn" onclick="raRerender('enact');setTimeout(()=>{const s=document.getElementById('raSecDocs');if(s)s.scrollIntoView({behavior:'smooth'})},60)">문서 세트 새로고침</button></div>`;
}

// ── 점검 ────────────────────────────────────────────────────────────────────
async function raLint(mode, silent){
  const box=document.getElementById('raLint');
  let body;
  if(mode==='enact'){ const D=RA.enact.draft; if(!D) return; body={text:D.text, addenda:D.addenda, title:RA.enact.title}; }
  else { const t=raAmendFullText(); if(!t){ _toast('먼저 내규를 불러오세요.'); return; } body={text:t.text, addenda:t.addenda, title:RA.amend.title}; }
  if(box && !silent) box.innerHTML=raSpin('점검 중...');
  const d=await raPost('/api/regagent/lint', body);
  RA[mode].lint=d.success?d.issues:null; _raSave();
  if(box) box.innerHTML=d.success?raLintView(d.issues):raErr(d.error||'점검 실패');
}
function raLintView(iss, onlyNos){
  if(!iss) return '';
  let list=iss; if(onlyNos) list=iss.filter(i=>!i.no||onlyNos.has(i.no));
  if(!list.length) return '<div class="ra-ok">✅ 발견된 문제가 없습니다.</div>';
  const cnt=l=>list.filter(i=>i.level===l).length;
  const ic={error:raIc('bad'),warn:raIc('alert'),info:raIc('tip')};
  return `<div class="ra-meta">오류 <b class="lv-error">${cnt('error')}</b> · 주의 <b class="lv-warn">${cnt('warn')}</b> · 제안 <b class="lv-info">${cnt('info')}</b></div><ul class="ra-lint">`+
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
      `<label class="ra-f"><span>현행 원문 <em>“제1조(목적) …” 형식 그대로 붙여 넣으세요. 등록되지 않은 ${_e(RA_ORG.reg_word)}나 다른 기관 규정도 됩니다.</em></span><textarea class="ra-ta mono" id="raPasteText" rows="8" oninput="raSet('amend.pasteText',this.value)">${_e(A.pasteText)}</textarea></label>`+
      `<div class="ra-row"><button class="svc-btn" onclick="raPasteLoad()">조문 읽기</button></div><div id="raArts">${A.pasted?raArtsView():''}</div>`
    :`<div class="ra-row"><input id="raRegIn" class="ra-in" list="raRegList" style="max-width:340px" placeholder="${_e(RA_ORG.reg_word)}명 (예: 여비규정)" value="${_e(A.title)}" onkeydown="if(event.key==='Enter')raPickReg()"><datalist id="raRegList"></datalist>`+
      `<button class="svc-btn" onclick="raPickReg()">불러오기</button>${A.slug?`<a class="ra-link" href="${raRegUrl(A.slug)}" target="_blank" rel="noopener">원문↗</a>`:''}</div><div id="raArts">${raArtsView()}</div>`);
  const s2=`<label class="ra-f"><span>개정 의도</span>${raTa('amend.intent',A.intent,'예) 숙박비 상한을 실비 기준으로 바꾸고, 출장 신청을 전자결재로 하도록 정비',3)}</label>`+
    `<div class="ra-grid2"><label class="ra-f"><span>시행일</span>${raIn('amend.effective',A.effective,'비우면 “발령한 날”')}</label>`+
    `<label class="ra-f"><span>참고 자료 <em>상위법 개정 내용 등(선택)</em></span>${raTa('amend.refText',A.refText,'예) 「공무원 여비 규정」 별표 개정(2026.1.1.)',1)}</label></div>`+
    `<div class="ra-row"><button class="svc-btn yes" onclick="raAmendDraft()">${raIc('spark')}수정안 작성</button><button class="svc-btn" onclick="raAmendManual()">선택 조문 직접 고치기</button><button class="svc-btn ghost" onclick="raAddInsert()">＋ 조문 신설</button>`+
    `<span class="ra-hint">${raHasAi()?'체크한 조문(없으면 AI가 목차를 보고 고름)에 개정 의도를 반영합니다.':'AI 키가 없으면 체크한 조문을 직접 고쳐 쓰세요.'}</span></div>`;
  const s3=`<div id="raChanges">${raChangesView()}</div>`;
  return raSec(1,'대상 내규·조문','개정할 조문을 체크하세요',s1)+raSec(2,'개정 의도','',s2)+raSec(3,'조문 수정안','현행과 비교해 고쳐 쓰세요',s3,'raSecChg')+
    (A.changes.length?raSec(4,'신구조문대비표','밑줄: 바뀐 부분',`<label class="ra-chk"><input type="checkbox" ${A.abbr?'checked':''} onchange="raSet('amend.abbr',this.checked);raRefreshCmp()"> 바뀌지 않은 항·호는 “(현행과 같음)”으로 줄이기</label><div id="raCmp">${raCmpView()}</div>`)+
      raSec(5,'영향 분석','이 조문을 인용하는 다른 조문·별표·내규',`<div class="ra-row"><button class="svc-btn" onclick="raImpact()">${raIc('search')}영향 범위 찾기</button><span class="ra-hint">조 번호를 옮기는 경우 이동표(예: 7→8)를 넣으면 고칠 인용 표기를 함께 보여 줍니다.</span><input id="raMoves" class="ra-in sm" style="max-width:180px" placeholder="이동표 예: 7→8, 9→10" value="${_e(A.moves||'')}" oninput="raSet('amend.moves',this.value)"></div><div id="raImpact">${raImpactView()}</div>`)+
      raSec(6,'점검','개정 후 전체 조문 기준',`<div class="ra-row"><button class="svc-btn" onclick="raLint('amend')">점검 실행</button><label class="ra-chk"><input type="checkbox" id="raLintOnly" checked onchange="raLintRedraw()"> 고친 조문 관련만 보기</label></div><div id="raLint">${raLintView(A.lint, raLintOnlySet())}</div>`)+
      raSec(7,'심의 사전검토',`「${_e(raRules())}」 심의기준별 점검·검토의견`,raReviewSec('amend'))+
      raSec(8,'문서 세트','개정문·개정 이유서·신구조문대비표·사전예고문·의견수렴 공고·사전검토 의견서',raDocsView('amend'),'raSecDocs'):'')+
    `<div class="ra-foot"><button class="svc-btn ghost sm" onclick="raReset('amend')">↺ 개정 작업 새로 시작</button></div>`;
}
function raLintOnlySet(){ const el=document.getElementById('raLintOnly'); if(el&&!el.checked) return null; return new Set(RA.amend.changes.map(c=>c.no)); }
function raLintRedraw(){ const b=document.getElementById('raLint'); if(b) b.innerHTML=raLintView(RA.amend.lint, raLintOnlySet()); }
function raAmendSrc(v){ const A=RA.amend; if(A.src===v) return; A.src=v; if(v==='reg'){ A.pasted=false; } else { A.slug=''; } _raArts=null; Object.assign(A,{sel:{},changes:[],impact:null,lint:null,review:null}); _raSave(); raRerender('amend'); }
async function raPasteLoad(){
  const A=RA.amend; const t=(document.getElementById('raPasteText')||{}).value||A.pasteText;
  if(!t.trim()){ _toast('원문을 붙여 넣으세요.'); return; }
  A.pasteText=t; const d=await raPost('/api/regagent/parse',{text:t, clean:true});
  if(!d.success||!d.articles.length){ _toast('“제1조(목적)” 형식의 조문을 찾지 못했습니다.'); return; }
  if(!A.title) A.title=(d.preamble||'').split('\n')[0].slice(0,40)||'붙여넣은 규정';
  _raArts={title:A.title, revision:'붙여넣은 원문', articles:d.articles, pasted:true};
  Object.assign(A,{pasted:true,slug:'',sel:{},changes:[],impact:null,lint:null,review:null}); _raSave(); raRerender('amend');
}
function raRegPayload(){ const A=RA.amend; return A.pasted?{text:A.pasteText, reg:A.title}:{slug:A.slug, reg:A.title}; }
async function raPickReg(){
  const v=((document.getElementById('raRegIn')||{}).value||'').trim(); if(!v){ _toast('내규명을 입력하세요.'); return; }
  const regs=await raCatalog(); const nk=s=>s.replace(/[\s·_]/g,'');
  const r=regs.find(x=>nk(x.title)===nk(v))||regs.find(x=>nk(x.title).includes(nk(v)));
  if(!r){ _toast('내규를 찾지 못했습니다. 목록에서 골라 주세요.'); return; }
  if(RA.amend.slug!==r.slug){ Object.assign(RA.amend,{src:'reg',pasted:false,slug:r.slug,title:r.title,sel:{},changes:[],impact:null,lint:null,review:null,purpose:'',main:[],addenda:'',notes:[]}); }
  _raArts=null; _raSave(); raLoadArts(r.slug);
}
async function raLoadArts(slug, quiet){
  const box=document.getElementById('raArts'); if(box && !quiet) box.innerHTML=raSpin('조문 불러오는 중...');
  _raBusy.arts=true;
  const d=await raGet('/api/regagent/articles?slug='+encodeURIComponent(slug));
  _raBusy.arts=false;
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'불러오기 실패'); return; }
  _raArts=d; RA.amend.title=d.title; _raSave(); raRerender('amend');
}
function raArtsView(){
  const A=RA.amend;
  if(!A.slug && !A.pasted) return '<div class="ra-empty">개정할 내규를 고르세요. 「상위법 영향」 탭의 후보에서 바로 넘어올 수도 있습니다.</div>';
  if(!_raArts){ if(A.pasted && A.pasteText) setTimeout(raPasteLoad,0); return raSpin('조문 불러오는 중...'); }
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
function raSel(no,on){ if(on) RA.amend.sel[no]=true; else delete RA.amend.sel[no]; _raSave(); const c=document.getElementById('raSelCnt'); if(c) c.textContent=Object.keys(RA.amend.sel).length; }
function raOld(no){ return _raArts?_raArts.articles.find(a=>a.no===no):null; }
async function raAmendDraft(){
  const A=RA.amend; if(!_raArts){ _toast('먼저 내규를 불러오세요.'); return; }
  if(!A.intent.trim()){ _toast('개정 의도를 입력하세요.'); return; }
  if(!raHasAi()){ _toast('AI 키가 없습니다. [✦ AI 설정]에서 키를 넣거나 “선택 조문 직접 고치기”를 쓰세요.'); return; }
  const box=document.getElementById('raChanges'); if(box) box.innerHTML=raSpin('AI가 수정안을 작성하는 중... (20~40초)');
  const targets=Object.keys(A.sel).map(no=>raOld(no)).filter(Boolean).map(a=>({no:a.no,title:a.title,body:a.body}));
  const dels=A.refText.trim()?[{law:'참고',art:'',text:A.refText}]:[];
  const d=await raPost('/api/regagent/draft',{mode:'amend', ...raRegPayload(), intent:A.intent, effective:A.effective, targets, delegations:dels, ...raAi()});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'수정안 작성 실패', d.need_key); return; }
  const r=d.draft;
  A.changes=r.changes.map(c=>({type:c.type,no:c.no,title:c.title,body:c.body,why:c.why}));
  A.purpose=(r.reason||{}).purpose||''; A.main=(r.reason||{}).main||[]; A.addenda=(r.addenda||[]).join('\n'); A.notes=r.notes||[]; A.model=r.model||'';
  A.impact=null; A.lint=null; _raSave(); raRerender('amend');
  setTimeout(()=>{ const s=document.getElementById('raSecChg'); if(s) s.scrollIntoView({behavior:'smooth',block:'start'}); },60);
  raLint('amend', true);
}
function raAmendManual(){
  const A=RA.amend; if(!_raArts){ _toast('먼저 내규를 불러오세요.'); return; }
  const nos=Object.keys(A.sel).sort(raCmp); if(!nos.length){ _toast('고칠 조문을 체크하세요.'); return; }
  nos.forEach(no=>{ if(A.changes.some(c=>c.no===no)) return; const o=raOld(no); A.changes.push({type:'modify',no,title:o.title,body:o.body,why:''}); });
  A.changes.sort((x,y)=>raCmp(x.no,y.no)); _raSave(); raRerender('amend');
}
function raAddInsert(){
  const A=RA.amend; if(!_raArts){ _toast('먼저 내규를 불러오세요.'); return; }
  const after=prompt('어느 조 다음에 신설할까요? (예: 7 → 제7조의2로 신설)'); if(!after) return;
  const base=raKey(raNormNo(after)); if(!base[0]){ _toast('조 번호를 숫자로 입력하세요.'); return; }
  const used=new Set([..._raArts.articles.map(a=>a.no),...A.changes.map(c=>c.no)]);
  let k=Math.max(2, base[1]+1), no=`${base[0]}의${k}`; while(used.has(no)){ k++; no=`${base[0]}의${k}`; }
  A.changes.push({type:'insert',no,title:'',body:'',why:''}); A.changes.sort((x,y)=>raCmp(x.no,y.no)); _raSave(); raRerender('amend');
}
function raChangesView(){
  const A=RA.amend;
  if(!A.changes.length) return '<div class="ra-empty">아직 수정안이 없습니다. 위에서 “수정안 작성” 또는 “선택 조문 직접 고치기”를 누르세요.</div>';
  const tl={modify:'개정',insert:'신설',delete:'삭제'};
  return (A.model?`<div class="ra-meta">작성: ${_e(A.model)} · AI 수정안은 반드시 검토 후 사용하세요.</div>`:'')+A.changes.map((c,i)=>{
    const o=raOld(c.no);
    return `<div class="ra-chg t-${c.type}"><div class="ra-chg-h"><select class="ra-in sm" onchange="raChg(${i},'type',this.value)">${Object.entries(tl).map(([k,v])=>`<option value="${k}"${c.type===k?' selected':''}>${v}</option>`).join('')}</select>`+
      `<b>${_e(raLbl(c.no))}</b><input class="ra-in sm" style="max-width:220px" placeholder="조 제목" value="${_e(c.title)}" oninput="raChg(${i},'title',this.value,1)" ${c.type==='delete'?'disabled':''}>`+
      (c.why?`<span class="ra-sub">${_e(c.why)}</span>`:'')+`<button class="ra-x" title="이 수정안 빼기" onclick="raChgDel(${i})">✕</button></div>`+
      `<div class="ra-chg-b"><div class="ra-old"><div class="ra-lab">현행</div>${o?_e(raArtText(o)).replace(/\n/g,'<br>'):'<span class="ra-mu">&lt;신 설&gt;</span>'}</div>`+
      `<div class="ra-new"><div class="ra-lab">개정안</div>${c.type==='delete'?'<span class="ra-mu">이 조를 삭제합니다(번호는 남기고 “삭제” 표시).</span>':`<textarea class="ra-ta mono" rows="${Math.min(14,Math.max(4,(c.body||'').split('\n').length+1))}" oninput="raChg(${i},'body',this.value,1)">${_e(c.body)}</textarea>`}</div></div></div>`;
  }).join('')+
  `<div class="ra-grid2" style="margin-top:12px"><label class="ra-f"><span>개정 이유</span><textarea class="ra-ta" rows="3" oninput="raSet('amend.purpose',this.value)">${_e(A.purpose)}</textarea></label>`+
  `<label class="ra-f"><span>주요 내용 <em>한 줄에 하나</em></span><textarea class="ra-ta" rows="3" oninput="RA.amend.main=this.value.split('\\n');_raSave()">${_e((A.main||[]).join('\n'))}</textarea></label></div>`+
  `<label class="ra-f"><span>부칙</span><textarea class="ra-ta mono" rows="2" placeholder="비우면 “이 ${_e(raKind(A.title))}${raJosa(raKind(A.title))} 발령한 날부터 시행한다.”" oninput="raSet('amend.addenda',this.value)">${_e(A.addenda)}</textarea></label>`+
  (A.notes&&A.notes.length?`<div class="ra-note"><b>함께 확인할 점</b><ul>${A.notes.map(n=>`<li>${_e(n)}</li>`).join('')}</ul></div>`:'')+
  `<div class="ra-row"><button class="svc-btn" onclick="raRerender('amend')">대비표·문서 새로고침</button></div>`;
}
function raChg(i,k,v,soft){ RA.amend.changes[i][k]=v; _raSave(); if(!soft) raRerender('amend'); else raRefreshCmp(); }
function raChgDel(i){ RA.amend.changes.splice(i,1); _raSave(); raRerender('amend'); }
let _raCmpT=null;
function raRefreshCmp(){ clearTimeout(_raCmpT); _raCmpT=setTimeout(()=>{ const b=document.getElementById('raCmp'); if(b) b.innerHTML=raCmpView(); },250); }
function raCmpRows(){
  const A=RA.amend;
  return [...A.changes].sort((x,y)=>raCmp(x.no,y.no)).map(c=>{
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
  const moves={}; ((document.getElementById('raMoves')||{}).value||'').split(/[,\s]+/).forEach(p=>{ const m=p.match(/(\d+(?:의\d+)?)\s*(?:→|->|=>|>)\s*(\d+(?:의\d+)?)/); if(m) moves[m[1]]=m[2]; });
  const nos=A.changes.filter(c=>c.type!=='insert').map(c=>c.no);
  const box=document.getElementById('raImpact'); if(box) box.innerHTML=raSpin('인용 조문을 찾는 중...');
  const d=await raPost('/api/regagent/impact',{...raRegPayload(), nos, moves});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'분석 실패'); return; }
  A.impact=d; _raSave(); if(box) box.innerHTML=raImpactView();
}
function raImpactView(){
  const I=RA.amend.impact; if(!I) return '';
  const s=I.summary;
  const hit=(h)=>`<li><b>${_e(raLbl(h.no))}${h.title?`(${_e(h.title)})`:''}</b> — “${_e(h.text)}”${h.suggest?` <em class="ra-fix">${_e(h.suggest)}</em>`:''}<div class="ra-snip">${_e(h.snippet)}</div></li>`;
  let html=`<div class="ra-meta">같은 내규 안 <b>${s.inner}</b>건 · 별표·서식 <b>${s.appendix}</b>건 · 다른 내규의 조문 인용 <b>${s.outer}</b>건 · 내규명 인용 <b>${s.mention_regs}</b>개 내규</div>`;
  if(!s.inner&&!s.appendix&&!s.outer) html+='<div class="ra-ok">✅ 고친 조문을 직접 인용하는 곳이 없습니다.</div>';
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
  A.changes.sort((x,y)=>raCmp(x.no,y.no)); _raSave(); raRerender('amend');
  _toast(`인용 정정 ${add}개 조문을 수정안에 넣었습니다.`+(skip.length?` 이미 고친 ${skip.join(', ')}는 직접 확인하세요.`:''), 5000);
}

// ══════════════════════════════════════════════════════════════════════════
// 심의 사전검토 — 기관 심의기준(org_config.json review_criteria)
// ══════════════════════════════════════════════════════════════════════════
function raReviewPayload(mode){
  if(mode==='enact'){ const E=RA.enact, D=E.draft||{};
    return {mode, title:E.title, text:D.text||'', addenda:D.addenda||'', purpose:D.purpose||E.purpose, main:String(D.main||'').split('\n'), delegations:E.dels};
  }
  const A=RA.amend, t=raAmendFullText()||{};
  return {mode, title:A.title, slug:A.slug, text:t.text||'', addenda:A.addenda||'', purpose:A.purpose||A.intent, main:A.main||[], delegations:A.refText?[{law:'참고',art:'',text:A.refText}]:[]};
}
async function raReview(mode){
  const body={...raReviewPayload(mode), ans:RA.proc.ans||{}, ai:raHasAi(), ...raAi()};
  if(!body.text.trim()){ _toast('검토할 조문이 없습니다.'); return; }
  const box=document.getElementById('raReview'); if(box) box.innerHTML=raSpin(raHasAi()?'심의기준별로 점검하고 AI 검토의견을 받는 중... (20~40초)':'심의기준별로 점검하는 중...');
  const d=await raPost('/api/regagent/review', body);
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'검토 실패'); return; }
  RA[mode].review=d; _raSave(); if(box) box.innerHTML=raReviewView(d);
}
const RA_ST={ok:['적합','ok'],check:['확인 필요','check'],warn:['보완 필요','warn']};
function raReviewView(d){
  if(!d) return '';
  const cnt=k=>d.rows.filter(r=>r.status===k).length;
  return `<div class="ra-meta">보완 필요 <b class="lv-error">${cnt('warn')}</b> · 확인 필요 <b class="lv-warn">${cnt('check')}</b> · 적합 <b>${cnt('ok')}</b>${d.model?` · AI 의견: ${_e(d.model)}`:''}</div>`+
    (d.notice?`<div class="ra-note ra-note-i">${raIc('info')}<span>${_e(d.notice)}</span></div>`:'')+
    `<table class="ra-rev"><thead><tr><th>심의기준</th><th>판정</th><th>점검 결과${d.model?' · AI 검토의견':''}</th></tr></thead><tbody>`+
    d.rows.map(r=>`<tr><td><b>${_e(r.t)}</b><div class="ra-ref">${_e(r.ref)}</div><div class="ra-snip">${_e(r.d)}</div></td><td><span class="ra-st st-${RA_ST[r.status][1]}">${RA_ST[r.status][0]}</span></td>`+
      `<td><ul class="ra-hits">${r.items.map(i=>`<li>${_e(i.msg)}</li>`).join('')||'<li class="ra-mu">자동 점검 항목 없음</li>'}</ul>${r.ai?`<div class="ra-aiop">✦ ${_e(r.ai)}</div>`:''}</td></tr>`).join('')+`</tbody></table>`+
    (d.delegation?`<div class="ra-note"><b>위임 범위·상위법 저촉 검토</b><br>${_e(d.delegation)}</div>`:'')+
    (d.overall?`<div class="ra-note"><b>종합의견</b><br>${_e(d.overall)}</div>`:'');
}
function raReviewSec(mode){
  return `<div class="ra-row"><button class="svc-btn" onclick="raReview('${mode}')">${raIc('check')}심의 사전검토</button><span class="ra-hint">필요성·적합성·통일성·명료성·체제·공개 등 ${_e(RA_ORG.reg_word)}심의 기준으로 미리 점검합니다${raHasAi()?'(AI 검토의견·위임 범위 검토 포함)':''}. 결과는 「사전검토 의견서」로 저장됩니다.</span></div><div id="raReview">${raReviewView(RA[mode].review)}</div>`;
}
function raDocReview(c, mode){
  const d=RA[mode].review;
  if(!d) return '심의 사전검토를 먼저 실행하세요(위의 「심의 사전검토」).';
  const L=[`「${c.title}」 ${c.word}(안) 심의 사전검토 의견서`,'',`검토 기준: 「${raRules()}」 심의사항`, `검토일: ${raToday(0)}`,''];
  d.rows.forEach((r,i)=>{ L.push(`${i+1}. ${r.t}(${r.ref}) — ${RA_ST[r.status][0]}`); r.items.forEach(x=>L.push(`  - ${x.msg}`)); if(r.ai) L.push(`  ※ 검토의견: ${r.ai}`); L.push(''); });
  if(d.delegation) L.push('■ 위임 범위·상위법 저촉 검토', `  ${d.delegation}`, '');
  if(d.overall) L.push('■ 종합의견', `  ${d.overall}`);
  return L.join('\n');
}

// ══════════════════════════════════════════════════════════════════════════
// 문서 세트
// ══════════════════════════════════════════════════════════════════════════
const RA_DOCS={
  enact:[['law','내규안'],['reason','제정 이유서'],['cmp','신구조문대비표'],['notice','대국민 사전예고문'],['staff','직원 의견수렴 공고'],['review','사전검토 의견서']],
  amend:[['law','개정문'],['reason','개정 이유서'],['cmp','신구조문대비표'],['notice','대국민 사전예고문'],['staff','직원 의견수렴 공고'],['review','사전검토 의견서']],
};
function raDocCtx(mode){
  if(mode==='enact'){
    const E=RA.enact, D=E.draft||{}; const p=raParse(D.text||'');
    const title=E.title||'○○규칙'; const kind=raKind(title);
    return {mode, title, kind, word:'제정', dept:E.dept||'○○팀', purpose:D.purpose||'', main:String(D.main||'').split('\n').map(s=>s.trim()).filter(Boolean),
      addenda:(D.addenda||'').trim()||`이 ${kind}${raJosa(kind)} ${E.effective||'발령한 날'}부터 시행한다.`, arts:p.articles, dels:E.dels||[]};
  }
  const A=RA.amend; const title=A.title||'○○규정'; const kind=raKind(title);
  return {mode, title, kind, word:'개정', dept:'○○팀', purpose:A.purpose||'', main:(A.main||[]).map(s=>String(s).trim()).filter(Boolean),
    addenda:(A.addenda||'').trim()||`이 ${kind}${raJosa(kind)} ${A.effective||'발령한 날'}부터 시행한다.`, changes:[...A.changes].sort((x,y)=>raCmp(x.no,y.no)), dels:[]};
}
function raAddendaLines(t){ const s=String(t||'').trim(); return s.split('\n').map(x=>x.trim()).filter(Boolean); }
function raDocLaw(c){
  const L=[];
  if(c.mode==='enact'){
    L.push(`${c.title}(안)`,'');
    let chap='';
    c.arts.forEach(a=>{ if(a.chapter&&a.chapter!==chap){ chap=a.chapter; L.push('',chap); } L.push(...raArtText(a).split('\n')); });
  }else{
    L.push(`${c.title} 일부개정(안)`,'',`${c.title} 일부를 다음과 같이 개정한다.`,'');
    c.changes.forEach(ch=>{
      if(ch.type==='delete') L.push(`${raLbl(ch.no)}를 삭제한다.`,'');
      else L.push(`${raLbl(ch.no)}를 다음과 같이 ${ch.type==='insert'?'신설한다':'한다'}.`, ...raArtText(ch).split('\n'), '');
    });
  }
  L.push('','부    칙',...raAddendaLines(c.addenda));
  return L.join('\n').replace(/\n{3,}/g,'\n\n');
}
function raDocReason(c){
  const L=[`「${c.title}」 ${c.word} 이유서`,'',`1. ${c.word} 이유`, `  ${c.purpose||`○○에 필요한 사항을 정하기 위하여 「${c.title}」을(를) ${c.word}하려는 것임.`}`,'',`2. 주요 내용`];
  const main=c.main.length?c.main:(c.mode==='enact'?c.arts.slice(2).map(a=>`${a.title}에 관한 사항을 정함(안 ${raLbl(a.no)})`):c.changes.map(ch=>`${ch.title||raLbl(ch.no)} ${ch.type==='insert'?'신설':ch.type==='delete'?'삭제':'정비'}(안 ${raLbl(ch.no)})`));
  main.forEach((m,i)=>L.push(`  ${'가나다라마바사아자차카타파하'[i]||'-'}. ${m}`));
  L.push('','3. 관련 근거');
  if(c.dels.length) c.dels.forEach(d=>L.push(`  - 「${d.law}」 ${d.art}`)); else L.push(`  - 「${raRules()}」 제14조(입안)`);
  L.push('','4. 행정사항',`  - 시행일: ${raAddendaLines(c.addenda)[0]||''}`,'  - 관련 부서 협의: ○○팀(협의 완료/예정)',`  - 사전예고·직원 의견수렴: 「${raRules()}」 제15조의3·제15조의4에 따라 실시(해당 시)`,'  - 붙임: 신구조문대비표 1부.');
  return L.join('\n');
}
function raDocNotice(c, staff){
  const days=staff?(+RA_ORG.staff_days||7):(+RA_ORG.notice_days||20); const from=raToday(0), to=raToday(days);
  const L=[ staff?`「${c.title}」 ${c.word}(안) 직원 의견수렴 공고`:`「${c.title}」 ${c.word}(안) 사전예고`, '',
    staff?`「${c.title}」을(를) ${c.word}하기에 앞서 임직원의 의견을 듣고자 「${raRules()}」 제15조의4에 따라 다음과 같이 알립니다.`
         :`${RA_ORG.org_name} 「${c.title}」을(를) ${c.word}함에 있어 국민·기관·단체의 의견을 듣고자 「${raRules()}」 제15조의3에 따라 다음과 같이 예고합니다.`,
    '', `1. ${RA_ORG.reg_word}명: ${c.title}`, '', `2. ${c.word} 이유`, `  ${c.purpose||'○○'}`, '', '3. 주요 내용'];
  (c.main.length?c.main:['○○']).forEach((m,i)=>L.push(`  ${'가나다라마바사아자차카타파하'[i]||'-'}. ${m}`));
  L.push('', `4. 의견 제출`, `  가. 기간: ${from} ~ ${to} (${days}일 이상)`, `  나. 제출처: ${c.dept} (전화 ○○○-○○○○-○○○○, 전자우편 ○○○@${RA_ORG.email_domain||'example.or.kr'})`,
    `  다. 제출 방법: 의견서에 ${staff?'소속·':''}성명, 전화번호, 전자우편 주소를 적어 전자우편 또는 ${staff?'내부포털':'서면'}으로 제출`,
    '', '5. 붙임: 신구조문대비표 1부.  끝.');
  return L.join('\n');
}
function raDocCmpRows(c){
  if(c.mode==='enact') return c.arts.map(a=>{ const t=raArtText(a); return ['&lt;신 설&gt;', `<u class="ra-i">${_e(t).replace(/\n/g,'<br>')}</u>`, '<신 설>', t]; });
  return raCmpRows();
}
function raDocsBuild(mode){
  const c=raDocCtx(mode);
  const cmp=raDocCmpRows(c);
  return {c, law:raDocLaw(c), reason:raDocReason(c), notice:raDocNotice(c,false), staff:raDocNotice(c,true), review:raDocReview(c,mode), cmp};
}
function raDocsView(mode){
  const S=RA[mode]; const tab=S.docTab||'law';
  const B=raDocsBuild(mode);
  const tabs=RA_DOCS[mode].map(([k,l])=>`<button class="ra-dtab${tab===k?' on':''}" onclick="raSet('${mode}.docTab','${k}');raRerender('${mode}')">${l}</button>`).join('');
  let body;
  if(tab==='cmp') body=`<div class="ra-doc-t">「${_e(B.c.title)}」 ${B.c.word}안 신구조문대비표</div><table class="ra-cmp"><thead><tr><th>현 행</th><th>${B.c.word} 안</th></tr></thead><tbody>${B.cmp.map(r=>`<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('')||'<tr><td colspan="2">조문이 없습니다.</td></tr>'}</tbody></table>`;
  else body=`<pre class="ra-doc">${_e(B[tab])}</pre>`;
  const all=RA_DOCS[mode].map(([k,l])=>`<label class="ra-chk"><input type="checkbox" class="ra-docpick" value="${k}" checked> ${l}</label>`).join('');
  return `<div class="ra-dtabs">${tabs}</div><div class="ra-docbox">${body}</div>`+
    `<div class="ra-row"><button class="svc-btn" onclick="raCopyDoc('${mode}')">복사</button><button class="svc-btn" onclick="raPrintDoc('${mode}')">인쇄</button>`+
    `<span class="ra-sep"></span>${all}<button class="svc-btn yes" onclick="raExport('${mode}','hwpx')">한글(.hwpx)</button><button class="svc-btn" onclick="raExport('${mode}','docx')">Word(.docx)</button></div>`+
    `<div class="ra-hint">사전예고는 국민 권리·의무 관련 ${_e(RA_ORG.reg_word)}(「${_e(raRules())}」 제15조의3제2항)일 때 ${RA_ORG.notice_days}일 이상, 직원 의견수렴은 ${RA_ORG.staff_days}일 이상(제15조의4) — 오른쪽 절차 안내를 확인하세요.</div>`;
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
function raDocBlocks(B, picks){
  const blocks=[];
  picks.forEach((k,i)=>{
    if(i) blocks.push({t:'break'});
    if(k==='cmp'){
      blocks.push({t:'p',text:`「${B.c.title}」 ${B.c.word}안 신구조문대비표`},{t:'p',text:''});
      blocks.push({t:'table',colWidths:[23814,23814],rows:[[{t:'현 행',hd:1},{t:`${B.c.word} 안`,hd:1}],...B.cmp.map(r=>[{t:r[2]},{t:r[3]}])]});
    } else blocks.push({t:'p',text:B[k]});
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
    _toast(`${label||name}을(를) ${fmt==='docx'?'Word':'한글'} 파일로 저장했습니다.`);
  }catch(e){ _toast('서버 연결에 실패했습니다.'); }
}
function raExport(mode, fmt){
  const picks=[...document.querySelectorAll('.ra-docpick:checked')].map(x=>x.value);
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
];
const RA_MODE_L={amend:'개정',enact:'제정',bulk:'일괄 정비',upper:'상위법 영향'};
function raAgentView(){
  const G=RA.agent;
  const ex=RA_AG_EX.map(([k,t])=>`<button class="ra-ag-ex" onclick="raAgentEx('${_a(t)}')"><span>${_e(k)}</span>${_e(t)}</button>`).join('');
  return `<div class="ra-wide">`+
    `<section class="ra-ag-hero"><label class="ra-ag-label" for="raAgIn">무엇을 하고 싶으세요?</label>`+
    `<div class="ra-ag-box"><textarea id="raAgIn" class="ra-ag-in" rows="2" placeholder="예) 여비규정 제15조의 일비를 3만원으로 올려줘" oninput="raSet('agent.req',this.value)" onkeydown="if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();raAgentRun();}">${_e(G.req)}</textarea>`+
    `<button class="svc-btn yes ra-ag-go" onclick="raAgentRun()" ${G.running?'disabled':''}>${raIc('spark')}${G.running?'진행 중…':'에이전트 실행'}</button></div>`+
    `<div class="ra-ag-exs">${ex}</div>`+
    `<p class="ra-hint">에이전트가 요청을 <b>제정·개정·일괄 정비·상위법 영향</b> 중 하나로 판단하고, 대상 ${_e(RA_ORG.reg_word)}와 조문을 찾아 초안 → 인용 영향 → 점검 → 심의 사전검토 → 절차 판단 → 문서 세트까지 이어서 수행합니다. ${raHasAi()?'AI가 계획과 초안을 씁니다.':'AI 키가 없으면 규칙 기반으로 계획하고, 조문 문장은 결과 화면에서 직접 고칩니다.'}</p></section>`+
    `<div id="raAgOut">${raAgentOut()}</div></div>`;
}
function raAgentEx(t){ RA.agent.req=t; _raSave(); const el=document.getElementById('raAgIn'); if(el){ el.value=t; el.focus(); } }
const RA_AG_ST={run:['진행 중','run'],ok:['완료','ok'],warn:['확인 필요','warn'],err:['중단','err'],skip:['건너뜀','skip']};
function raAgentOut(){
  const G=RA.agent; if(!G.steps.length) return '';
  const P=G.plan;
  const head=P?`<div class="ra-ag-plan"><span class="ra-pill ok">${raIc(P.mode==='amend'?'amend':P.mode==='enact'?'enact':P.mode==='bulk'?'bulk':'upper')}${_e(RA_MODE_L[P.mode]||P.mode)}</span>`+
    (P.reg?`<span class="ra-pill">「${_e(P.reg.title)}」${(P.articles||[]).length?' '+P.articles.map(a=>raLbl(a.no)).join('·'):''}</span>`:'')+
    (P.mode==='bulk'?`<span class="ra-pill">“${_e(P.old)}” → “${_e(P.new)}”</span>`:'')+(P.mode==='upper'?`<span class="ra-pill">「${_e(P.law)}」 ${_e((P.arts||[]).join(', '))}</span>`:'')+
    (P.mode==='enact'&&P.title?`<span class="ra-pill">「${_e(P.title)}」</span>`:'')+`<span class="ra-pill subtle">${P.ai?'AI 계획':'규칙 기반 계획'}</span></div>`:'';
  const steps=`<ol class="ra-ag-steps">`+G.steps.map((s,i)=>`<li class="st-${RA_AG_ST[s.st][1]}"><span class="ra-ag-dot">${s.st==='run'?'<span class="spinner"></span>':s.st==='ok'?'✓':s.st==='err'?'!':s.st==='warn'?'!':'–'}</span>`+
    `<div class="ra-ag-b"><div class="ra-ag-t"><b>${i+1}. ${_e(s.t)}</b><span class="ra-ag-s">${RA_AG_ST[s.st][0]}</span></div>${s.d?`<div class="ra-ag-d">${s.d}</div>`:''}</div></li>`).join('')+`</ol>`;
  const done=G.done?`<div class="ra-ag-done"><div><b>${_e(G.done.title)}</b><div class="ra-hint">${_e(G.done.sub)}</div></div><div class="ra-row" style="margin:0">`+
    G.done.acts.map(([l,f,yes])=>`<button class="svc-btn${yes?' yes':''}" onclick="${f}">${l}</button>`).join('')+`</div></div>`:'';
  return raSec('✦','에이전트 작업 내역',_e(G.req),head+steps+done,'raAgSec');
}
function raAgentDraw(){ const o=document.getElementById('raAgOut'); if(o) o.innerHTML=raAgentOut(); }
function raAgProc(category){
  const a=RA.proc.ans=RA.proc.ans||{};
  if(!a.level) a.level=(category==='규정'||category==='정관')?'reg':(category==='예규'||category==='매뉴얼')?'ye':'rule';
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
  const A=RA.amend;
  let s=step(`「${P.reg.title}」 조문 불러오기`);
  const d=await raGet('/api/regagent/articles?slug='+encodeURIComponent(P.reg.slug));
  if(!d.success) stop(s,d.error||'불러오기 실패');
  _raArts=d;
  Object.assign(A,{src:'reg',pasted:false,slug:d.slug,title:d.title,sel:{},changes:[],impact:null,lint:null,review:null,purpose:'',main:[],addenda:'',notes:[],intent:P.intent||RA.agent.req,refText:'',model:''});
  const tg=(P.articles||[]).map(a=>raOld(a.no)).filter(Boolean);
  tg.forEach(a=>A.sel[a.no]=true);
  fin(s,`${d.articles.length}개 조 중 ${tg.length?tg.map(a=>`${raLbl(a.no)}(${_e(a.title)})`).join(', '):'대상 조문 없음 — AI가 목차를 보고 고릅니다'}`);
  s=step('수정안 작성');
  let ok=false;
  if(raHasAi()){
    const r=await raPost('/api/regagent/draft',{mode:'amend',slug:A.slug,reg:A.title,intent:A.intent,targets:tg.map(a=>({no:a.no,title:a.title,body:a.body})),delegations:[],...raAi()});
    if(r.success){ const x=r.draft; A.changes=x.changes.map(c=>({type:c.type,no:c.no,title:c.title,body:c.body,why:c.why}));
      A.purpose=(x.reason||{}).purpose||''; A.main=(x.reason||{}).main||[]; A.addenda=(x.addenda||[]).join('\n'); A.notes=x.notes||[]; A.model=x.model||''; ok=true;
      fin(s,`${A.changes.length}개 조문 수정안: `+A.changes.map(c=>`${raLbl(c.no)} ${({modify:'개정',insert:'신설',delete:'삭제'})[c.type]}`).join(', ')+(A.purpose?'<br>'+_e(A.purpose):'')); }
    else fin(s,_e(r.error||'AI 오류')+' — 대상 조문을 수정안 칸에 담았습니다.','warn');
  }
  if(!ok){
    A.changes=tg.map(a=>({type:'modify',no:a.no,title:a.title,body:a.body,why:'에이전트가 고른 대상 조문 — 내용을 고쳐 쓰세요'}));
    A.purpose=`${A.intent.replace(/[.。]?$/,'')}하려는 것임.`; A.main=tg.map(a=>`${a.title} 정비(안 ${raLbl(a.no)})`);
    if(!raHasAi()) fin(s,'AI 키가 없어 대상 조문을 수정안 칸에 담았습니다. 결과 화면에서 문장을 고쳐 쓰면 대비표·문서가 바로 바뀝니다.','warn');
  }
  s=step('인용 영향 분석');
  const nos=A.changes.filter(c=>c.type!=='insert').map(c=>c.no);
  const im=await raPost('/api/regagent/impact',{slug:A.slug,nos,moves:{}});
  if(im.success){ A.impact=im; const m=im.summary;
    fin(s,`같은 ${_e(RA_ORG.reg_word)} 안 인용 ${m.inner}건 · 다른 ${_e(RA_ORG.reg_word)}의 조문 인용 ${m.outer}건 · ${_e(RA_ORG.reg_word)}명 인용 ${m.mention_regs}개`+
      (im.inner.length?'<br>'+im.inner.slice(0,3).map(h=>`${raLbl(h.no)}에서 ${_e(h.text)} 인용`).join(', '):''), (m.inner||m.outer)?'warn':'ok'); }
  else fin(s,_e(im.error||'분석 실패'),'warn');
  await raAgCheck('amend',step,fin);
  s=step('절차 판단'); fin(s,raAgProc(P.reg.category));
  s=step('문서 세트 준비'); fin(s,'개정문 · 개정 이유서 · 신구조문대비표 · 대국민 사전예고문 · 직원 의견수렴 공고 · 사전검토 의견서');
  RA.agent.done={title:`「${A.title}」 개정안이 준비됐습니다`,sub:'결과 화면에서 문장을 다듬고 한글·Word로 저장하세요.',
    acts:[['개정 결과 열기',"raTab('amend')",1],['문서 세트로 바로 가기',"raTab('amend');setTimeout(()=>raGoDoc('amend','cmp'),80)"]]};
}
async function raAgEnact(P, step, fin, stop){
  const E=RA.enact;
  Object.assign(E,{title:P.title||'',purpose:P.purpose||RA.agent.req,contents:P.contents||'',dels:[],sim:null,refs:{},draft:null,lint:null,review:null});
  let s=step('유사 규정 조사');
  const sm=await raPost('/api/regagent/similar',{query:[E.title,E.purpose,E.contents].join(' ').slice(0,600),limit:6});
  if(sm.success&&sm.regs.length){ E.sim={regs:sm.regs,semantic:sm.semantic,tokens:sm.tokens};
    sm.regs.slice(0,2).forEach(g=>g.articles.slice(0,2).forEach(a=>{ E.refs[g.slug+'|'+a.no]={reg:g.title,no:a.no,title:a.title,body:a.body}; }));
    fin(s,'참고 조문: '+Object.values(E.refs).map(r=>`「${_e(r.reg)}」 ${raLbl(r.no)}(${_e(r.title)})`).join(', ')); }
  else fin(s,'비슷한 조문을 찾지 못했습니다.','skip');
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
    acts:[['제정 결과 열기',"raTab('enact')",1],['문서 세트로 바로 가기',"raTab('enact');setTimeout(()=>raGoDoc('enact','law'),80)"]]};
}
async function raAgBulk(P, step, fin, stop){
  const U=RA.bulk; Object.assign(U,{old:P.old,neu:P.new,whole:true,res:null,sel:{},reason:''});
  let s=step(`모든 ${RA_ORG.reg_word}에서 “${P.old}” 찾기`);
  const d=await raPost('/api/regagent/bulk',{old:P.old,new:P.new,whole:true});
  if(!d.success) stop(s,d.error||'검색 실패');
  U.res=d; d.regs.forEach(g=>U.sel[g.slug]=true);
  if(!d.regs.length){ fin(s,`“${_e(P.old)}”을(를) 쓰는 ${_e(RA_ORG.reg_word)}가 없습니다.`,'skip'); RA.agent.done={title:'정비할 곳이 없습니다',sub:'다른 표현으로 다시 시도해 보세요.',acts:[]}; return; }
  fin(s,`${d.reg_count}개 ${_e(RA_ORG.reg_word)} · ${d.total}곳: `+d.regs.slice(0,5).map(g=>`「${_e(g.reg)}」 ${g.count}`).join(', ')+(d.regs.length>5?' 외':''));
  s=step('조사 교정·개정문 작성'); fin(s,_e(d.regs[0].amend_text).replace(/\n/g,'<br>')+(d.regs.length>1?`<br>… 외 ${d.regs.length-1}개 ${_e(RA_ORG.reg_word)}`:''));
  s=step('문서 세트 준비'); fin(s,'내규별 개정문 · “다른 내규의 개정” 부칙 · 통합 신구조문대비표 · 정비 이유서');
  RA.agent.done={title:`“${P.old}” → “${P.new}” 일괄 정비안이 준비됐습니다`,sub:`${d.reg_count}개 ${RA_ORG.reg_word}, ${d.total}곳`,acts:[['일괄 정비 결과 열기',"raTab('bulk')",1]]};
}
async function raAgUpper(P, step, fin, stop){
  const U=RA.upper; Object.assign(U,{law:P.law||'',arts:(P.arts||[]).join(', '),old:'',neu:'',res:null});
  let s=step(`「${P.law}」을(를) 인용하는 ${RA_ORG.reg_word} 찾기`);
  const d=await raPost('/api/regagent/upper',{law:U.law,arts:(P.arts||[]).map(raNormNo).filter(Boolean)});
  if(!d.success) stop(s,d.error||'분석 실패');
  U.res=d;
  if(!d.count){ fin(s,'인용하는 조문이 없습니다.','skip'); RA.agent.done={title:'영향받는 내규가 없습니다',sub:'',acts:[]}; return; }
  fin(s,`${d.reg_count}개 ${_e(RA_ORG.reg_word)} · ${d.count}개 조문 · 우선 검토 ${d.high}건`);
  const top=d.candidates.slice(0,3);
  s=step('개정 후보 선정'); fin(s,top.map(c=>`「${_e(c.reg)}」 ${raLbl(c.no)}(${_e(c.title)})${c.specific.length?' — '+_e(c.specific.join(', ')):''}`).join('<br>'), d.high?'warn':'ok');
  RA.agent.done={title:`개정 후보 ${d.count}개 조문을 찾았습니다`,sub:'1순위 후보로 바로 개정 작업을 시작할 수 있습니다.',
    acts:[['후보 전체 보기',"raTab('upper')",1],[`1순위 「${top[0].reg}」 ${raLbl(top[0].no)} 개정하기`,`raUpperToAmend('${_a(top[0].slug)}','${_a(top[0].no)}')`]]};
}

// ══════════════════════════════════════════════════════════════════════════
// 규정 건강검진 — 내규별 점수·등급·정비 우선순위, 상위법 최신성(법제처) 확인
// ══════════════════════════════════════════════════════════════════════════
const RA_GRADE={A:['양호','good'],B:['관심','good'],C:['주의','warning'],D:['경고','serious'],E:['위험','critical']};
async function raHealthLoad(){
  const H=RA.health; const box=document.getElementById('raHealth'); if(box) box.innerHTML=raSpin(`${RA_ORG.reg_word} ${RA_ORG._count||''}건을 진단하는 중...`);
  const d=await raPost('/api/regagent/health',{law_info:H.law||{}});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'진단 실패'); return; }
  _raHealth=d; raRerender('health');
}
let _raHealth=null;
async function raHealthLaws(){
  const H=RA.health; if(!_raHealth) return;
  const names=_raHealth.laws.filter(n=>!(H.law||{})[n]); H.law=H.law||{};
  const bar=document.getElementById('raLawProg'); let done=0, fail=0;
  for(let i=0;i<names.length;i+=6){
    const chunk=names.slice(i,i+6);
    if(bar) bar.innerHTML=`<div class="ra-prog"><i style="width:${Math.round((i)/names.length*100)}%"></i></div><div class="ra-meta">법제처에서 상위법 시행일 확인 중 ${i}/${names.length}</div>`;
    const d=await raPost('/api/regagent/health/laws',{names:chunk});
    if(!d.success){ if(bar) bar.innerHTML=raErr(d.error||'법령 조회 실패'); return; }
    Object.entries(d.laws).forEach(([k,v])=>{ if(v.error) fail++; else { H.law[k]={ef:v.ef,found:v.found,status:v.status}; done++; } });
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
    `<div class="ra-kpi hero"><div class="ra-kpi-l">평균 건강 점수</div><div class="ra-kpi-v">${d.avg}<small>/100</small></div><div class="ra-kpi-s"><span class="ra-gr g-${RA_GRADE[ag][1]}">${ag}</span>${RA_GRADE[ag][0]} · ${d.count}개 ${_e(RA_ORG.reg_word)}</div></div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">문제가 발견된 ${_e(RA_ORG.reg_word)}</div><div class="ra-kpi-v">${d.with_issues}<small>건</small></div><div class="ra-kpi-s">전체의 ${Math.round(d.with_issues/d.count*100)}%</div></div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">인용·명칭·번호 문제</div><div class="ra-kpi-v">${d.issue_total}<small>곳</small></div><div class="ra-kpi-s">오류가 있는 ${_e(RA_ORG.reg_word)} ${d.with_errors}건</div></div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">3년 이상 개정 없음</div><div class="ra-kpi-v">${d.old_regs}<small>건</small></div><div class="ra-kpi-s">정비 시기 점검 대상</div></div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">상위법 개정 미반영 의심</div><div class="ra-kpi-v">${lawN?d.stale_regs:'—'}<small>${lawN?'건':''}</small></div><div class="ra-kpi-s">${lawN?`법령 ${lawN}/${d.laws.length}개 확인`:'아래에서 법제처 확인'}</div></div></div>`;
  const mx=Math.max(1,...Object.values(d.grades));
  const dist=`<div class="ra-dist" role="img" aria-label="등급 분포">`+'ABCDE'.split('').map(g=>{ const n=d.grades[g]||0;
    return `<button class="ra-dist-r${f.g===g?' on':''}" onclick="raHealthF('g','${g}')" title="${g}등급(${RA_GRADE[g][0]}) ${n}건 — 눌러서 목록 거르기"><span class="ra-dist-k"><span class="ra-gr g-${RA_GRADE[g][1]}">${g}</span>${RA_GRADE[g][0]}</span>`+
      `<span class="ra-dist-t"><i class="g-${RA_GRADE[g][1]}" style="width:${n?Math.max(2,n/mx*100):0}%"></i></span><span class="ra-dist-n">${n}</span></button>`; }).join('')+`</div>`;
  const top=d.rows.filter(r=>r.reasons.length).slice(0,10);
  const prio=top.length?`<ol class="ra-prio">`+top.map((r,i)=>`<li><span class="ra-prio-n">${i+1}</span><div class="ra-prio-b"><div class="ra-prio-t"><b>「${_e(r.title)}」</b><span class="ra-gr g-${RA_GRADE[r.grade][1]}">${r.grade}</span><span class="ra-prio-s">${r.score}점</span><span class="ra-sub">${_e(r.revision)}</span></div>`+
    `<div class="ra-prio-r">${r.reasons.map(x=>`<span class="ra-chip">${_e(x)}</span>`).join('')}</div>`+
    (r.stale_laws.length?`<div class="ra-snip">상위법: ${r.stale_laws.slice(0,3).map(l=>`「${_e(l.law)}」 ${l.ef.slice(0,4)}.${l.ef.slice(4,6)}.${l.ef.slice(6)} 시행`).join(', ')}</div>`:'')+
    `</div><div class="ra-prio-a"><button class="svc-btn sm" onclick="raCheckToAmend('${_a(r.slug)}','${_a(r.title)}')">개정 작업</button><a class="ra-link" href="${raRegUrl(r.slug)}" target="_blank" rel="noopener">원문↗</a></div></li>`).join('')+`</ol>`:'<div class="ra-ok">정비가 필요한 내규가 없습니다.</div>';
  const q=(f.q||'').replace(/\s+/g,'');
  const rows=d.rows.filter(r=>(!f.g||r.grade===f.g)&&(!q||r.title.replace(/\s+/g,'').includes(q)));
  const table=`<div class="ra-row"><input class="ra-in sm" style="max-width:220px" placeholder="${_e(RA_ORG.reg_word)}명 검색" value="${_e(f.q||'')}" oninput="raHealthF('q',this.value)">`+
    (f.g?`<button class="ra-chip btn" onclick="raHealthF('g','')">${f.g}등급만 보는 중 ✕</button>`:'')+`<span class="ra-hint">${rows.length}건</span></div>`+
    `<div class="ra-tbl-w"><table class="ra-tbl"><thead><tr><th>${_e(RA_ORG.reg_word)}</th><th>등급</th><th>점수</th><th>최종 개정</th><th>진단</th></tr></thead><tbody>`+
    rows.map(r=>`<tr><td><a class="ra-link" href="${raRegUrl(r.slug)}" target="_blank" rel="noopener">${_e(r.title)}</a><div class="ra-sub">${_e(r.category)} · ${r.n_articles}개 조 · 인용 법령 ${r.laws.length}</div></td>`+
      `<td><span class="ra-gr g-${RA_GRADE[r.grade][1]}">${r.grade}</span></td><td class="num">${r.score}</td><td>${_e(r.revision)}</td><td>${r.reasons.map(x=>_e(x)).join(', ')||'<span class="ra-mu">이상 없음</span>'}</td></tr>`).join('')+`</tbody></table></div>`;
  const rule=d.rules?`<details class="ra-det"><summary>점수 기준</summary><div class="ra-hint">100점에서 감점: 없는 조문 인용 건당 -10(최대 -30) · 조 번호 중복·순서 오류 -8 · 현행 목록에 없는 내규명 인용 -6 · 옛 기관명·직위 -5 · 개정 경과 ${_e(d.rules.age)} · ${_e(d.rules.law)}<br>등급: A 95점 이상(양호) · B 85(관심) · C 75(주의) · D 60(경고) · E 60점 미만(위험)</div></details>`:'';
  const lawSec=`<div class="ra-row"><button class="svc-btn" onclick="raHealthLaws()">${raIc('upper')}상위법 최신성 확인</button><span class="ra-hint">${_e(RA_ORG.reg_word)}가 인용한 법령 ${d.laws.length}개의 현행 시행일을 법제처에서 조회해, ${_e(RA_ORG.reg_word)} 개정일보다 나중에 시행된 법령을 찾습니다.${lawN?` (확인 ${lawN}개)`:''}</span></div><div id="raLawProg"></div>`;
  return `<div class="ra-wide" id="raHealth">${tiles}`+
    `<div class="ra-grid2 ra-h2">${raSec(1,'등급 분포','막대를 누르면 아래 목록을 거릅니다',dist+rule)}${raSec(2,'상위법 최신성','법제처 현행 법령 기준',lawSec)}</div>`+
    raSec(3,'정비 우선순위 Top 10','점수가 낮은 순 — 바로 개정 작업으로 넘길 수 있습니다',prio)+
    raSec(4,`전체 ${_e(RA_ORG.reg_word)} 진단표`,'',table)+
    `<div class="ra-foot"><button class="svc-btn ghost sm" onclick="_raHealth=null;raHealthLoad()">다시 진단</button></div></div>`;
}
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
    `<label class="ra-chk"><input type="checkbox" ${U.whole!==false?'checked':''} onchange="raSet('bulk.whole',this.checked)"> 다른 낱말의 일부는 제외(예: “원장”을 바꿀 때 “부원장”은 그대로)</label>`+
    `<label class="ra-f" style="margin-top:8px"><span>정비 사유 <em>개정 이유서에 들어갑니다</em></span>${raTa('bulk.reason',U.reason,'예) 「직제규정」 개정(2026. 1. 1.)으로 부서 명칭이 바뀜에 따라 관련 내규를 일괄 정비하려는 것임.',2)}</label>`+
    `<div class="ra-row"><button class="svc-btn yes" onclick="raBulkRun()">${raIc('search')}영향 내규 찾기</button><span class="ra-hint">직제 개편·기관명 변경·내규명 변경 때 모든 ${_e(RA_ORG.reg_word)}를 한 번에 정비합니다. 뒤따르는 조사(은/는·이/가·을/를·으로/로)도 맞춰 고칩니다.</span></div>`;
  return `<div class="ra-wide">${raSec(1,'바뀐 용어·명칭','',form)}${raSec(2,'정비 대상','체크한 내규만 문서에 넣습니다',`<div id="raBulk">${raBulkResView()}</div>`)}`+
    (U.res&&U.res.regs.length?raSec(3,'문서 세트','일괄 개정문·“다른 내규의 개정” 부칙·통합 신구조문대비표·정비 이유',raBulkDocsView(),'raSecDocs'):'')+`</div>`;
}
async function raBulkRun(){
  const U=RA.bulk; if(!U.old.trim()||!U.neu.trim()){ _toast('바뀌기 전·후 용어를 입력하세요.'); return; }
  const box=document.getElementById('raBulk'); if(box) box.innerHTML=raSpin(`모든 ${RA_ORG.reg_word}에서 찾는 중...`);
  const d=await raPost('/api/regagent/bulk',{old:U.old, new:U.neu, whole:U.whole!==false});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'검색 실패'); return; }
  U.res=d; U.sel={}; d.regs.forEach(g=>U.sel[g.slug]=true); U.docTab=U.docTab||'amend'; _raSave(); raRerender('bulk');
}
function raBulkSel(slug,on){ RA.bulk.sel[slug]=on; _raSave(); const b=document.getElementById('raSecDocs'); if(b){ const y=window.scrollY; raRerender('bulk'); window.scrollTo(0,y); } }
function raBulkResView(){
  const R=RA.bulk.res; if(!R) return '<div class="ra-empty">용어를 넣고 “영향 내규 찾기”를 누르세요.</div>';
  if(!R.regs.length) return `<div class="ra-ok">“${_e(R.old)}”을(를) 쓰는 ${_e(RA_ORG.reg_word)} 조문이 없습니다.</div>`;
  const sel=RA.bulk.sel||{};
  return `<div class="ra-meta">“${_e(R.old)}” → “${_e(R.new)}” · <b>${R.reg_count}</b>개 ${_e(RA_ORG.reg_word)} · <b>${R.total}</b>곳 <button class="ra-link" onclick="Object.keys(RA.bulk.sel).forEach(k=>RA.bulk.sel[k]=true);raRerender('bulk')">모두 선택</button><button class="ra-link" onclick="Object.keys(RA.bulk.sel).forEach(k=>RA.bulk.sel[k]=false);raRerender('bulk')">모두 해제</button></div>`+
    R.regs.map(g=>`<details class="ra-det"><summary><label onclick="event.stopPropagation()"><input type="checkbox" ${sel[g.slug]?'checked':''} onchange="raBulkSel('${_a(g.slug)}',this.checked)"></label> <b>「${_e(g.reg)}」</b> <span class="ra-chip">${g.count}곳</span> <a class="ra-link" href="${raRegUrl(g.slug)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">원문↗</a></summary>`+
      `<div class="ra-note mono">${_e(g.amend_text).replace(/\n/g,'<br>')}</div>`+
      g.articles.map(a=>{ const [o,n]=raWordDiff(a.old_body,a.new_body); return `<div class="ra-fixrow"><b>${_e(raLbl(a.no))}(${_e(a.title)})</b> <span class="ra-sub">${_e(a.locs.join(', '))}</span><div class="ra-fixd"><div>${o.replace(/\n/g,'<br>')}</div><div>${n.replace(/\n/g,'<br>')}</div></div></div>`; }).join('')+`</details>`).join('');
}
const RA_BULK_DOCS=[['amend','내규별 개정문'],['addenda','“다른 내규의 개정” 부칙'],['cmp','통합 신구조문대비표'],['reason','정비 이유서']];
function raBulkDocs(){
  const U=RA.bulk, R=U.res, regs=R.regs.filter(g=>U.sel[g.slug]);
  const amend=regs.map(g=>g.amend_text).join('\n\n');
  const addenda=`제○조(다른 ${RA_ORG.reg_word}의 개정) `+(regs.length===1?regs[0].amend_text:regs.map((g,i)=>`${RA_HANG[i]||(i+1)+'.'} ${g.amend_text.replace('\n','\n   ')}`).join('\n'));
  const reason=[`${RA_ORG.reg_word} 일괄 정비 이유서`,'','1. 정비 이유',`  ${U.reason||`“${R.old}”이(가) “${R.new}”(으)로 바뀜에 따라 이를 인용하는 ${RA_ORG.reg_word}를 일괄 정비하려는 것임.`}`,'',
    '2. 정비 대상',...regs.map((g,i)=>`  ${'가나다라마바사아자차카타파하'[i]||'-'}. 「${g.reg}」 ${g.articles.map(a=>raLbl(a.no)).join(', ')} (${g.count}곳)`),'',
    '3. 정비 방식',`  각 ${RA_ORG.reg_word}의 해당 조문 중 “${R.old}”을(를) “${R.new}”(으)로 고침(조사 포함). 근거 ${RA_ORG.reg_word} 개정 시 부칙 “다른 ${RA_ORG.reg_word}의 개정”으로 함께 개정하거나 각 ${RA_ORG.reg_word}별로 개정함.`,'',
    `4. 관련: 「${raRules()}」 제16조제1항(법령·상위 내규 변경에 따른 개폐는 심의 생략 가능)`].join('\n');
  const cmp=[]; regs.forEach(g=>{ cmp.push({reg:g.reg}); g.articles.forEach(a=>{ const o={no:a.no,title:a.title,body:a.old_body}, n={no:a.no,title:a.new_title||a.title,body:a.new_body}; cmp.push(raCmpCell(o,n,true)); }); });
  return {regs, amend, addenda, reason, cmp};
}
function raBulkDocsView(){
  const U=RA.bulk, tab=U.docTab||'amend', D=raBulkDocs();
  if(!D.regs.length) return '<div class="ra-empty">정비할 내규를 체크하세요.</div>';
  const tabs=RA_BULK_DOCS.map(([k,l])=>`<button class="ra-dtab${tab===k?' on':''}" onclick="raSet('bulk.docTab','${k}');raRerender('bulk')">${l}</button>`).join('');
  const body=tab==='cmp'?`<table class="ra-cmp"><thead><tr><th>현 행</th><th>개 정 안</th></tr></thead><tbody>${D.cmp.map(r=>r.reg?`<tr><td colspan="2" class="ra-cmp-reg">「${_e(r.reg)}」</td></tr>`:`<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('')}</tbody></table>`:`<pre class="ra-doc">${_e(D[tab])}</pre>`;
  return `<div class="ra-dtabs">${tabs}</div><div class="ra-docbox">${body}</div><div class="ra-row"><button class="svc-btn" onclick="raBulkCopy()">복사</button><span class="ra-sep"></span>`+
    `<button class="svc-btn yes" onclick="raBulkExport('hwpx')">한글(.hwpx)로 저장</button><button class="svc-btn" onclick="raBulkExport('docx')">Word(.docx)로 저장</button></div>`;
}
function raBulkCopy(){ const D=raBulkDocs(), tab=RA.bulk.docTab||'amend'; _copyText(tab==='cmp'?D.cmp.map(r=>r.reg?`■ 「${r.reg}」`:`[현행]\n${r[2]}\n[개정안]\n${r[3]}`).join('\n\n'):D[tab], ()=>_toast('복사했습니다.')); }
function raBulkExport(fmt){
  const D=raBulkDocs(), R=RA.bulk.res; if(!D.regs.length){ _toast('정비할 내규를 체크하세요.'); return; }
  const rows=[[{t:'현 행',hd:1},{t:'개 정 안',hd:1}]]; D.cmp.forEach(r=>rows.push(r.reg?[{t:`「${r.reg}」`,cs:2,hd:1}]:[{t:r[2]},{t:r[3]}]));
  const blocks=[{t:'p',text:D.reason},{t:'break'},{t:'p',text:D.amend},{t:'break'},{t:'p',text:D.addenda},{t:'break'},{t:'p',text:`“${R.old}” → “${R.new}” 일괄 정비 신구조문대비표`},{t:'table',colWidths:[23814,23814],rows}];
  raSaveFile(fmt, `일괄정비_${R.old}→${R.new}`.replace(/[\\/:*?"<>|→]/g,'_'), blocks, '일괄 정비 문서');
}

// ══════════════════════════════════════════════════════════════════════════
// 상위법 영향
// ══════════════════════════════════════════════════════════════════════════
function raUpperView(){
  const U=RA.upper;
  const form=`<div class="ra-grid2"><label class="ra-f"><span>상위 법령명</span>${raIn('upper.law',U.law,'예) 공공기관의 운영에 관한 법률')}</label>`+
    `<label class="ra-f"><span>개정된 조문 <em>쉼표로 구분(선택)</em></span>${raIn('upper.arts',U.arts,'예) 제31조, 제32조의2')}</label></div>`+
    `<div class="ra-grid2"><label class="ra-f"><span>개정 전 조문 <em>선택 — 바뀐 용어를 찾아 영향 조문을 넓힙니다</em></span>${raTa('upper.old',U.old,'개정 전 조문을 붙여 넣으세요',4)}</label>`+
    `<label class="ra-f"><span>개정 후 조문</span>${raTa('upper.neu',U.neu,'개정 후 조문을 붙여 넣으세요',4)}</label></div>`+
    `<div class="ra-row"><button class="svc-btn yes" onclick="raUpperRun()">${raIc('search')}영향 조문 찾기</button><span class="ra-hint">기관 내규 전체에서 이 법령(시행령·시행규칙 포함)을 인용하는 조문을 찾아 개정 후보로 보여 줍니다.</span></div>`;
  return `<div class="ra-wide">${raSec(1,'상위법 개정 내용','',form)}${raSec(2,'개정 후보 조문','',`<div id="raUpper">${raUpperResView()}</div>`)}</div>`;
}
async function raUpperRun(){
  const U=RA.upper; if(!U.law.trim()){ _toast('상위 법령명을 입력하세요.'); return; }
  const box=document.getElementById('raUpper'); if(box) box.innerHTML=raSpin('내규 전체에서 인용 조문을 찾는 중...');
  const arts=U.arts.split(/[,\s]+/).map(raNormNo).filter(Boolean);
  const d=await raPost('/api/regagent/upper',{law:U.law, arts, old:U.old, new:U.neu});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'분석 실패'); return; }
  U.res=d; _raSave(); if(box) box.innerHTML=raUpperResView();
}
function raUpperResView(){
  const R=RA.upper.res; if(!R) return '<div class="ra-empty">법령명을 넣고 “영향 조문 찾기”를 누르세요.</div>';
  if(!R.count) return `<div class="ra-ok">「${_e(R.law)}」을(를) 인용하는 내규 조문이 없습니다.</div>`;
  const groups={}; R.candidates.forEach(c=>{ (groups[c.reg]=groups[c.reg]||{slug:c.slug,items:[]}).items.push(c); });
  return `<div class="ra-meta">「${_e(R.law)}」 인용 <b>${R.count}</b>개 조문 · <b>${R.reg_count}</b>개 내규 · 우선 검토 <b class="lv-error">${R.high}</b>건${R.removed_terms.length?` · 바뀐 용어: ${R.removed_terms.map(t=>`<span class="ra-chip">${_e(t)}</span>`).join('')}`:''}</div>`+
    Object.entries(groups).map(([reg,g])=>`<div class="ra-simc"><div class="ra-simc-h"><b>「${_e(reg)}」</b><span class="ra-sub">${g.items.length}개 조문</span><a class="ra-link" href="${raRegUrl(g.slug)}" target="_blank" rel="noopener">원문↗</a></div>`+
      g.items.map(c=>`<div class="ra-cand${(c.specific.length||c.terms.length)?' hi':''}"><div><b>${_e(raLbl(c.no))}(${_e(c.title)})</b> `+
        `${c.specific.map(s=>`<span class="ra-chip hi">${_e(s)}</span>`).join('')}${c.terms.map(s=>`<span class="ra-chip warn">용어: ${_e(s)}</span>`).join('')}${!c.specific.length&&!c.terms.length?c.cites.slice(0,2).map(s=>`<span class="ra-chip">${_e(s)}</span>`).join(''):''}`+
        `<button class="svc-btn sm" style="margin:0 0 0 6px" onclick="raUpperToAmend('${_a(c.slug)}','${_a(c.no)}')">✏️ 개정안 만들기</button></div><div class="ra-snip">${_e(c.snippet)}</div></div>`).join('')+`</div>`).join('');
}
function raUpperToAmend(slug, no){
  const U=RA.upper, A=RA.amend;
  const reg=(U.res.candidates.find(c=>c.slug===slug)||{}).reg||'';
  if(A.slug!==slug) Object.assign(A,{src:'reg',pasted:false,slug,title:reg,sel:{},changes:[],impact:null,lint:null,review:null,purpose:'',main:[],addenda:'',notes:[]});
  A.sel[no]=true;
  const arts=U.arts?` ${U.arts}`:'';
  A.intent=A.intent||`상위법 「${U.law}」${arts} 개정 내용을 반영하여 인용 조문과 관련 내용을 정비`;
  A.refText=[U.old?`[개정 전] ${U.old}`:'', U.neu?`[개정 후] ${U.neu}`:''].filter(Boolean).join('\n').slice(0,3000);
  _raArts=null; RA.tab='amend'; _raSave(); openRegAgent();
}

// ══════════════════════════════════════════════════════════════════════════
// 전체 점검
// ══════════════════════════════════════════════════════════════════════════
function raCheckView(){
  const C=RA.check;
  const one=`<div class="ra-row"><input id="raChkReg" class="ra-in" list="raRegList" style="max-width:320px" placeholder="내규명 (예: 인사규정)" value="${_e(C.reg||'')}"><datalist id="raRegList"></datalist><button class="svc-btn" onclick="raCheckOne()">이 내규 점검</button></div><div id="raChkOne">${C.one?raLintView(C.one.issues):''}</div>`;
  const all=`<div class="ra-row"><button class="svc-btn yes" onclick="raCheckAll()">${raIc('check')}기관 내규 전체 점검</button><span class="ra-hint">모든 내규에서 없는 조문 인용·현행 목록에 없는 내규명·구 명칭(재단·이사장 등)·조 번호 중복을 찾습니다.</span></div><div id="raChkAll">${raCheckAllView()}</div>`;
  return `<div class="ra-wide">${raSec(1,'전체 점검','인용·명칭·충돌 오류',all)}${raSec(2,'내규 하나 자세히 점검','항·호 순서, 표기, 부칙, 별표 인용까지',one)}</div>`;
}
async function raCheckAll(){
  const box=document.getElementById('raChkAll'); if(box) box.innerHTML=raSpin('기관 내규 전체를 점검하는 중...');
  const d=await raPost('/api/regagent/lint',{all:true});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'점검 실패'); return; }
  RA.check.res=d; _raSave(); if(box) box.innerHTML=raCheckAllView();
}
function raCheckAllView(){
  const R=RA.check.res; if(!R) return '';
  return `<div class="ra-meta">${R.checked}개 내규 점검 · 문제 있는 내규 <b>${R.regs.length}</b>개 · 오류 <b class="lv-error">${R.total.error||0}</b> · 주의 <b class="lv-warn">${R.total.warn||0}</b></div>`+
    R.regs.map(r=>`<details class="ra-det"${r.errors?' open':''}><summary><b>「${_e(r.reg)}」</b> ${r.errors?`<span class="ra-chip hi">오류 ${r.errors}</span>`:''}<span class="ra-chip">${r.count}건</span> <a class="ra-link" href="${raRegUrl(r.slug)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">원문↗</a> <button class="ra-link" onclick="event.preventDefault();raCheckToAmend('${_a(r.slug)}','${_a(r.reg)}')">개정 작업으로</button></summary>${raLintView(r.issues)}</details>`).join('');
}
async function raCheckOne(){
  const v=((document.getElementById('raChkReg')||{}).value||'').trim(); if(!v){ _toast('내규명을 입력하세요.'); return; }
  RA.check.reg=v; const box=document.getElementById('raChkOne'); if(box) box.innerHTML=raSpin('점검 중...');
  const d=await raPost('/api/regagent/lint',{reg:v});
  if(!d.success){ if(box) box.innerHTML=raErr(d.error||'점검 실패'); return; }
  RA.check.one=d; _raSave(); if(box) box.innerHTML=`<div class="ra-ih">「${_e(d.reg)}」</div>`+raLintView(d.issues);
}
function raCheckToAmend(slug, title){
  const A=RA.amend; if(A.slug!==slug) Object.assign(A,{src:'reg',pasted:false,slug,title,sel:{},changes:[],impact:null,lint:null,review:null,purpose:'',main:[],addenda:'',notes:[],intent:''});
  _raArts=null; RA.tab='amend'; _raSave(); openRegAgent();
}

// ══════════════════════════════════════════════════════════════════════════
// 절차 안내 — 기관 프로필(procedure.questions·steps)로 구성. when=모두 일치, unless=하나라도 일치하면 제외
// ══════════════════════════════════════════════════════════════════════════
function raPQ(){ return ((RA_ORG||{}).procedure||{}).questions||[]; }
function raCondMatch(cond, a){ return Object.entries(cond||{}).map(([k,v])=>Array.isArray(v)?v.includes(a[k]):a[k]===v); }
function raProcSteps(){
  const a=RA.proc.ans||{};
  return (((RA_ORG||{}).procedure||{}).steps||[]).filter(s=>{
    if(s.when && !raCondMatch(s.when,a).every(Boolean)) return false;
    if(s.unless && raCondMatch(s.unless,a).some(Boolean)) return false;
    return true;
  }).map(s=>({...s, desc:s.d||s.desc||'', docs:s.docs||[]}));
}
function raProcAnswer(k,v){ RA.proc.ans[k]=v; _raSave(); const t=RA.tab; if(t==='proc'){ const y=window.scrollY; raRender(); window.scrollTo(0,y); } else { const s=document.querySelector('.ra-side'); if(s) s.innerHTML=raProcSide(t); } }
function raProcCheck(id,on){ RA.proc.chk[id]=on; _raSave(); const t=RA.tab; if(t==='proc'){ const y=window.scrollY; raRender(); window.scrollTo(0,y); } else { const s=document.querySelector('.ra-side'); if(s) s.innerHTML=raProcSide(t); } }
function raProcQs(){
  const a=RA.proc.ans||{};
  return raPQ().map(q=>{
    const opts=q.opts||[['y','예'],['n','아니오']];
    return `<div class="ra-pq"><div class="ra-pq-q">${_e(q.q)} <span class="ra-ref">${_e(q.ref||'')}</span></div><div class="ra-seg">`+
      opts.map(([v,l])=>`<button class="${a[q.k]===v?'on':''}" onclick="raProcAnswer('${_a(q.k)}','${_a(v)}')">${_e(l)}</button>`).join('')+`</div></div>`;
  }).join('')||'<div class="ra-empty">기관 프로필에 절차 질문이 없습니다.</div>';
}
function raProcStepsView(mode, compact){
  const steps=raProcSteps(), chk=RA.proc.chk||{};
  if(!steps.length) return '<div class="ra-empty">기관 프로필(org_config.json)에 절차 단계가 없습니다.</div>';
  const next=steps.find(s=>!chk[s.id]);
  const done=steps.filter(s=>chk[s.id]).length;
  const names=mode?Object.fromEntries(RA_DOCS[mode]):{};
  const ready=mode&&(mode==='enact'?RA.enact.draft:RA.amend.changes.length);
  return `<div class="ra-prog"><i style="width:${Math.round(done/steps.length*100)}%"></i></div><div class="ra-meta">${done}/${steps.length} 단계 완료</div><ol class="ra-steps">`+
    steps.map(s=>`<li class="${chk[s.id]?'done':''}${next&&next.id===s.id?' next':''}"><label><input type="checkbox" ${chk[s.id]?'checked':''} onchange="raProcCheck('${_a(s.id)}',this.checked)"><span class="ra-st-t">${_e(s.t)}</span></label>`+
      `<div class="ra-st-m"><span class="ra-ref">「${_e(raRules())}」 ${_e(s.ref||'')}</span> · ${_e(s.who||'')}</div>`+
      (compact&&!(next&&next.id===s.id)?'':`<div class="ra-st-d">${_e(s.desc)}</div>`)+
      (ready&&s.docs.length?`<div class="ra-st-docs">${s.docs.filter(d=>names[d]).map(d=>`<button class="ra-chip btn" onclick="raGoDoc('${mode}','${d}')">${raIc('doc')}${_e(names[d])}</button>`).join('')}</div>`:'')+`</li>`).join('')+`</ol>`;
}
function raGoDoc(mode, d){ RA[mode].docTab=d; _raSave(); raRerender(mode); setTimeout(()=>{ const s=document.getElementById('raSecDocs'); if(s) s.scrollIntoView({behavior:'smooth',block:'start'}); },60); }
function raProcSide(mode){
  const a=RA.proc.ans||{}, Q=raPQ(); const answered=Q.filter(q=>a[q.k]).length;
  return `<div class="ra-side-h">${raIc('proc')}<span>절차 진행</span><button class="ra-link" onclick="raTab('proc')">전체 보기</button></div>`+
    (answered<Q.length?`<details class="ra-q-det"><summary><span class="ra-q-cnt">${answered}/${Q.length}</span><span>해당 여부에 답하면 필요한 단계만 남습니다</span></summary>${raProcQs()}</details>`:`<div class="ra-q-done">${raIc('check')}해당 여부 답변 완료 <button class="ra-link" onclick="raTab('proc')">고치기</button></div>`)+
    raProcStepsView(mode, true);
}
// 절차 안내 대시보드 — 지표 카드 · 해당 여부 격자 · 국면별 로드맵 · 작성 기준 카드
const RA_PHASE_FALLBACK=[{id:'prep',t:'입안·점검',d:''},{id:'opinion',t:'의견수렴·평가',d:''},{id:'review',t:'심의·확정',d:''},{id:'enforce',t:'시행·공개',d:''}];
function raPhases(){ const p=((RA_ORG||{}).procedure||{}).phases; return (p&&p.length)?p:RA_PHASE_FALLBACK; }
function raDays(s){ const n=parseInt(s.days,10); return isNaN(n)?0:n; }
function raWho(who){
  const w=String(who||'');
  const k=/감사/.test(w)?'audit':/이사회|원장|기관장/.test(w)&&!/주무부서$/.test(w)?'head':/→/.test(w)?'flow':/내규관리부서/.test(w)&&!/주무/.test(w)?'mgmt':/·/.test(w)?'flow':'dept';
  return `<span class="ra-who w-${k}">${_e(w)}</span>`;
}
function raProcDocMode(){ return RA.amend.changes.length?'amend':RA.enact.draft?'enact':null; }
function raProcView(){
  const steps=raProcSteps(), chk=RA.proc.chk||{}, a=RA.proc.ans||{}, Q=raPQ();
  const done=steps.filter(s=>chk[s.id]).length, pct=steps.length?Math.round(done/steps.length*100):0;
  const next=steps.find(s=>!chk[s.id]);
  const answered=Q.filter(q=>a[q.k]).length;
  // 최소 소요기간: 의견수렴 국면은 병행 가능 → 가장 긴 기간, 나머지 국면은 합산
  const op=steps.filter(s=>s.phase==='opinion').map(raDays), rv=steps.filter(s=>s.phase!=='opinion').map(raDays);
  const opMax=op.length?Math.max(0,...op):0, rvSum=rv.reduce((x,y)=>x+y,0), minDays=opMax+rvSum;
  const brk=[]; if(opMax) brk.push(`의견수렴 ${opMax}일${op.filter(x=>x>0).length>1?'(병행)':''}`);
  steps.filter(s=>s.phase!=='opinion'&&raDays(s)>0).forEach(s=>brk.push(`${s.phase==='review'?'심의 제출':_e(s.t)} ${raDays(s)}일`));
  const mode=raProcDocMode(), names=Object.fromEntries(RA_DOCS[mode||'enact']);
  const docs=[...new Set(steps.flatMap(s=>s.docs||[]))].filter(d=>names[d]);
  const kpis=`<div class="ra-kpis ra-pk">`+
    `<div class="ra-kpi"><div class="ra-kpi-l">진행률</div><div class="ra-kpi-v">${pct}<small>%</small></div><div class="ra-meter" role="meter" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100" aria-label="절차 진행률"><i style="width:${pct}%"></i></div><div class="ra-kpi-s">${steps.length}단계 중 ${done}단계 완료</div></div>`+
    `<div class="ra-kpi ra-kpi-next"><div class="ra-kpi-l">다음 할 일</div>`+(next?`<div class="ra-kpi-t">${_e(next.t)}</div><div class="ra-kpi-s">${raWho(next.who)}<span class="ra-ref">${_e(next.ref||'')}</span></div>`:`<div class="ra-kpi-t">모든 단계 완료</div><div class="ra-kpi-s">수고하셨습니다</div>`)+`</div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">예상 최소 소요기간</div><div class="ra-kpi-v">${minDays||'—'}<small>${minDays?'일':''}</small></div><div class="ra-kpi-s">${brk.length?brk.join(' + '):'기간이 정해진 단계 없음'}</div></div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">준비할 문서</div><div class="ra-kpi-v">${docs.length}<small>종</small></div><div class="ra-kpi-s" title="${_e(docs.map(d=>names[d]).join(' · '))}">${docs.slice(0,3).map(d=>_e(names[d])).join(' · ')||'—'}${docs.length>3?` 외 ${docs.length-3}종`:''}</div></div>`+
    `<div class="ra-kpi"><div class="ra-kpi-l">해당 여부 답변</div><div class="ra-kpi-v">${answered}<small>/${Q.length}</small></div><div class="ra-kpi-s">${answered<Q.length?'답할수록 필요한 단계만 남습니다':'답변 완료 — 맞춤 절차'}</div></div></div>`;
  const qs=`<div class="ra-pq-grid">`+Q.map(q=>{ const opts=q.opts||[['y','예'],['n','아니오']];
    return `<div class="ra-pq-c${a[q.k]?' on':''}"><div class="ra-pq-q">${_e(q.q)}</div><div class="ra-pq-f"><div class="ra-seg">`+
      opts.map(([v,l])=>`<button class="${a[q.k]===v?'on':''}" onclick="raProcAnswer('${_a(q.k)}','${_a(v)}')">${_e(l)}</button>`).join('')+`</div><span class="ra-ref">${_e(q.ref||'')}</span></div></div>`; }).join('')+`</div>`;
  const lanes=`<div class="ra-lanes">`+raPhases().map((ph,pi)=>{
    const ps=steps.filter(s=>(s.phase||'prep')===ph.id); const pd=ps.filter(s=>chk[s.id]).length;
    const st=!ps.length?'none':pd===ps.length?'done':ps.some(s=>next&&s.id===next.id)?'now':'todo';
    return `<div class="ra-lane l-${st}"><div class="ra-lane-h"><span class="ra-lane-n">${st==='done'?'✓':pi+1}</span><div><b>${_e(ph.t)}</b><small>${_e(ph.d||'')}</small></div><span class="ra-lane-c">${pd}/${ps.length}</span></div>`+
      `<div class="ra-lane-p"><i style="width:${ps.length?Math.round(pd/ps.length*100):0}%"></i></div>`+
      (ps.length?ps.map(s=>{ const isNext=next&&next.id===s.id, dn=!!chk[s.id], dd=raDays(s);
        return `<div class="ra-card${dn?' done':''}${isNext?' next':''}"><label class="ra-card-h"><input type="checkbox" ${dn?'checked':''} onchange="raProcCheck('${_a(s.id)}',this.checked)"><span>${_e(s.t)}</span></label>`+
          `<div class="ra-card-m">${raWho(s.who)}${dd&&!/\d+일/.test(s.t)?`<span class="ra-days" title="${_e(s.days_note||'')}">${dd}일${s.days_note?'':' 이상'}</span>`:''}<span class="ra-ref">${_e(s.ref||'')}</span></div>`+
          `<div class="ra-card-d">${_e(s.desc)}</div>`+
          ((s.docs||[]).filter(d=>names[d]).length?`<div class="ra-card-docs">${s.docs.filter(d=>names[d]).map(d=>mode?`<button class="ra-chip btn" onclick="raGoDoc('${mode}','${d}')">${raIc('doc')}${_e(names[d])}</button>`:`<span class="ra-chip">${raIc('doc')}${_e(names[d])}</span>`).join('')}</div>`:'')+
          (isNext?'<div class="ra-card-now">지금 할 일</div>':'')+`</div>`; }).join(''):`<div class="ra-lane-empty">해당 단계 없음</div>`)+`</div>`; }).join('')+`</div>`;
  const sum=(RA_ORG.rules_summary||[]).map(([h,t])=>`<div class="ra-rule"><b>${_e(h)}</b><p>${_e(t)}</p></div>`).join('');
  return `<div class="ra-wide ra-procdash">${kpis}`+
    raSec(1,'해당 여부','답에 따라 아래 로드맵의 단계·기간·문서가 바뀝니다',qs)+
    raSec(2,`${_e(RA_ORG.reg_word)} 제·개정 로드맵`,`카드를 체크하면 진행 상황이 이 브라우저에 저장됩니다${mode?' · 문서 칩을 누르면 해당 문서로 이동':''}`,lanes)+
    raSec(3,`작성 기준 요약 — 「${_e(raRules())}」`,'절차·심의기준·기관 명칭은 기관 프로필(org_config.json)에서 바꿀 수 있습니다',`<div class="ra-rules">${sum||'<div class="ra-empty">기관 프로필에 작성 기준 요약이 없습니다.</div>'}</div>`)+
    `<div class="ra-foot"><button class="svc-btn ghost sm" onclick="if(confirm('해당 여부 답변과 진행 체크를 모두 지울까요?')){RA.proc={ans:{},chk:{}};_raSave();raRender();}">절차 초기화</button></div></div>`;
}

function raReset(mode){
  if(!confirm(mode==='enact'?'제정 작업 내용을 지우고 새로 시작할까요?':'개정 작업 내용을 지우고 새로 시작할까요?')) return;
  RA[mode]=_raBlank()[mode]; if(mode==='amend') _raArts=null; _raSave(); raRender();
}
