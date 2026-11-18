import {DOMAIN} from '../constants/domain.js';
import {store,load} from '../stores/research.js';
import {runs} from '../api/research.js';
import {studySelect} from '../components/common/study-select.js';
import {runList} from '../components/common/run-list.js';
import {bindForm} from '../hooks/forms.js';
import {esc} from '../utils/format.js';
const labels={field:'指标列',resamples:'重采样次数 (200–20000)',alpha:'显著性 α (0.001–0.2)',power:'目标功效 (0.5–0.99)',simulations:'Monte Carlo 次数 (200–20000)'};
export function render(){const writable=localStorage.getItem('research-role')!=='viewer';return `<div class="eyebrow">02 / METHOD WORKSHEET</div><h1>${DOMAIN.field_label}</h1><p class="lead">${DOMAIN.algorithm}</p><div class="method-note">${DOMAIN.note}</div>${writable?`<form id="run-form" class="worksheet">${studySelect()}<label>本次研究名称<input name="name" required minlength="2" value="${esc(DOMAIN.names[0])} · 核算"></label><div class="inline-form">${Object.entries(DOMAIN.defaults).map(([key,value])=>key==='field'?`<label>${labels[key]}<select name="${key}">${DOMAIN.fields.map(f=>`<option value="${f[0]}">${f[1]}</option>`).join('')}</select></label>`:`<label>${labels[key]}<input name="${key}" type="number" step="any" value="${value}" required></label>`).join('')}</div><p>提交时冻结全部观测与参数，生成 SHA256。后台 worker 独立执行。</p><button type="submit">冻结输入并排队计算 →</button></form>`:'<p class="method-note">观察员可阅读研究记录，分析师与负责人可以发起计算。</p>'}<h2>计算记录</h2>${runList()}`;}
export function bind(refresh){bindForm('run-form',async data=>{const parameters=Object.fromEntries(Object.keys(DOMAIN.defaults).map(k=>[k,k==='field'?data[k]:+data[k]]));const r=await runs.create({study_id:+data.study_id,name:data.name,parameters});store.runId=r.id;await load();location.hash='results/'+r.id;});const sel=document.getElementById('study-select');if(sel)sel.onchange=()=>store.studyId=+sel.value;}
