'use strict';
const $ = id => document.getElementById(id);
const terminal = new Set(['completed', 'partial', 'failed', 'interrupted']);
const states = {queued:'排隊中',planning:'規劃中',executing:'執行中',verifying:'確認中',completed:'已完成',partial:'部分完成',failed:'失敗',interrupted:'已中斷',running:'執行中',done:'完成',skipped:'略過',confirmed:'可重現',not_reproduced:'未再現',inconclusive:'無法確認'};
let config, current, timer, generation = 0;
function el(tag, text, cls) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; }
async function api(path, options) { const res = await fetch(path, options); const data = await res.json(); if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`); return data; }
function badge(state) { return el('span', states[state] || state, 'badge ' + state); }
function render(r) {
  current = r;
  const done = terminal.has(r.state);
  $('run-state').textContent = states[r.state] || r.state;
  $('start').disabled = !done;
  $('start').textContent = done ? '開始檢查 →' : '任務執行中…';
  $('summary').textContent = r.summary || '正在收集證據，結果將在獨立確認後顯示。';
  $('finding-count').textContent = `${r.findings.filter(f => f.status === 'confirmed').length} 項可重現`;
  const phase = ['planning','executing','verifying'].indexOf(r.state);
  document.querySelectorAll('.step').forEach((s,i) => { s.classList.toggle('current', i === phase); s.classList.toggle('done', i < phase || r.state === 'completed'); });
  $('tasks').replaceChildren(...r.tasks.map(t => {const box = el('div',undefined,'task'); const head = el('div',undefined,'task-top'); head.append(el('span',`${String(t.id).padStart(2,'0')}　${t.title}`),badge(t.state)); box.append(head,el('p',t.reason),el('p',t.note)); if(t.ai_note) box.append(el('p','AI：'+t.ai_note)); return box;}));
  $('events').replaceChildren(...r.events.map(e => {const li=el('li');li.append(el('time',new Date(e.time).toLocaleTimeString('zh-TW',{hour12:false})),el('span',e.message));return li;}));
  $('events').scrollTop = $('events').scrollHeight;
  $('findings').replaceChildren(...r.findings.map(f => {const box=el('article',undefined,'finding');const h=el('h3');h.append(el('span',f.title),badge(f.status));box.append(h,el('p',f.detail),el('p','建議：'+f.fix,'fix'),el('small','證據：'+f.evidence_ids.join(' · ')));return box;}));
  $('warnings').replaceChildren(...r.warnings.map(w => el('p',w)));
  $('ai-summary').textContent = r.ai_summary ? 'AI 總結：'+r.ai_summary : '';
  $('evidence').replaceChildren(...r.evidence.map(e => {const details=el('details');const label=e.kind==='http'?`GET ${e.url} · HTTP ${e.status}`:'固定 TLS 子程序'; details.append(el('summary',`${e.id}　${label}`),el('pre',JSON.stringify(e,null,2)));return details;}));
  $('json').disabled = !done; $('md').disabled = !done;
}
async function history() {
  const rows = await api('/api/runs');
  $('history').replaceChildren(...rows.map(r => {const b=el('button',undefined,'history-item');let host=r.target;try{host=new URL(r.target).host;}catch{} b.append(el('span',host),el('small',`${states[r.state]} · ${new Date(r.started_at).toLocaleString('zh-TW',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}`));b.onclick=()=>select(r.id);return b;}));
  return rows;
}
async function select(id) {
  clearTimeout(timer); const gen = ++generation;
  async function poll() {
    try {const r=await api('/api/runs/'+id);if(gen!==generation)return;render(r);if(!terminal.has(r.state))timer=setTimeout(poll,800);else await history();}
    catch(e){$('error').textContent='讀取任務失敗：'+e.message+'。請重新整理。';}
  }
  await poll();
}
$('demo').onclick=()=>{$('target').value=config.demo_url;$('goal').value='檢查本機示範網站的安全標頭與 Cookie 設定';};
$('form').onsubmit=async e=>{
  e.preventDefault();$('error').textContent='';$('start').disabled=true;
  try{const selected=$('mode').value;const result=await api('/api/runs',{method:'POST',headers:{'Content-Type':'application/json','X-Sentinel-Token':config.token},body:JSON.stringify({target:$('target').value.trim(),goal:$('goal').value.trim(),mode:selected==='rules'?'rules':'ai',backend:selected==='compatible'?'compatible':'codex',authorized:$('authorized').checked})});await history();await select(result.id);}
  catch(err){$('error').textContent=err.message;$('start').disabled=false;}
};
async function download(format) {
  if(!current)return;
  try{const res=await fetch('/api/runs/'+current.id+(format==='md'?'/markdown':''));if(!res.ok)throw new Error('匯出失敗');const blob=await res.blob();const url=URL.createObjectURL(blob);const a=el('a');a.href=url;a.download=`sentinel-${current.id.slice(0,8)}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  catch(err){$('error').textContent=err.message;}
}
$('json').onclick=()=>download('json');$('md').onclick=()=>download('md');
async function init(){try{config=await api('/api/config');$('model-info').textContent=config.codex?'已偵測到 Codex CLI · 沿用本機登入。AI 分析不傳送網頁本文；實際工具由 Python 執行。':'找不到 Codex CLI；請先安裝並登入，或使用規則模式。';$('mode').querySelector('[value="codex"]').disabled=!config.codex;$('mode').querySelector('[value="compatible"]').disabled=!config.model;if(!config.codex)$('mode').value='rules';const rows=await history();if(rows.length)await select(rows[0].id);}catch(e){$('error').textContent=e.message;$('start').disabled=true;}}
init();
