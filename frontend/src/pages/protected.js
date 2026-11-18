import {DOMAIN} from '../constants/domain.js';
import {store,loadProtection} from '../stores/research.js';
import {protection} from '../api/research.js';
import {studySelect} from '../components/common/study-select.js';
import {table} from '../components/common/table.js';
import {esc,fmt} from '../utils/format.js';
import {bindForm} from '../hooks/forms.js';
import {download} from '../utils/download.js';

const meta=DOMAIN.protection||{};
const STATE={pending:'待生成 / 排队中',generating:'生成中',available:'可用',failed:'失败'};
const isAdmin=()=>localStorage.getItem('research-role')==='admin';
const canWrite=()=>localStorage.getItem('research-role')!=='viewer';

export async function render(id){
 if(!store.studyId)return `<div class="eyebrow">03 / PROTECTED RELEASE</div><h1>受保护分布发布</h1><p>先在来源录入页创建${DOMAIN.study_label}，再由负责人冻结口径。</p>`;
 await loadProtection();
 const info=store.protection||{protected:false,releases:[]};
 const policy=info.policy;
 const selected=id?await protection.get(+id):(info.releases[0]?await protection.get(info.releases[0].id):null);
 if(selected)store.releaseId=selected.id;
 const bins=(policy?.bins||meta.bins||[]).join(', ');
 const remaining=policy?policy.remaining_epsilon:null;
 const policyBlock=!policy
  ? (isAdmin()?`<h2>设定受保护发布口径 <small>仅负责人 · 设定后不可修改</small></h2><form id="policy-form" class="worksheet"><label>指标<select name="field">${(meta.fields||[]).map(f=>`<option value="${f}">${esc(f)}</option>`).join('')}</select></label><label>固定分箱边界（逗号分隔）<input name="bins" value="${esc((meta.bins||[]).join(', '))}" required></label><label>本批次总隐私预算 ε<input name="total_epsilon" type="number" step="any" min="0.000001" value="${esc(meta.total_epsilon)}" required></label><p>固定分箱与总预算后，每次发布按“增删一份茶样”口径加拉普拉斯噪声，并从同一份非负箱计数推导 ECDF 与分位数。</p><button type="submit">冻结口径</button></form>`
    :`<div class="method-note">该${DOMAIN.study_label}尚未由负责人设定受保护分箱与总隐私预算，暂无可用的受保护分布。</div>`)
  :`<div class="method-note"><strong>受保护口径已冻结</strong><p>指标 ${esc(policy.field)} · 分箱 ${esc(bins)} · 总预算 ε=${fmt(policy.total_epsilon)} · 已用 ε=${fmt(policy.spent_epsilon)} · 剩余 ε=${fmt(policy.remaining_epsilon)}</p><small>分箱、指标与总预算均不可修改；每次发布单独扣费并在同一事务内完成。</small></div>`;

 const releaseForm=policy&&canWrite()?`<h2>申请受保护发布 <small>扣费与留档齐全后才开放查看与下载</small></h2><form id="release-form" class="worksheet"><label>发布名称<input name="name" required minlength="2" value="${esc(DOMAIN.names[0])} · 受保护分布"></label><label>本次隐私预算 ε<input name="epsilon" type="number" step="any" min="0.000001" value="${esc(meta.epsilon_per_release)}" required></label><p>冻结当前输入、固定分箱与本次预算；改名或并发重试复用同一发布，不重抽噪声、不重复扣费。剩余预算不足时拒绝。</p><button type="submit" ${remaining<=0?'disabled':''}>提交受保护发布 →</button></form>`:'';

 const rows=(info.releases||[]).map(r=>[{html:`<a href="#protected/${r.id}">#${r.id} ${esc(r.name)}</a>`},STATE[r.status]||r.status,`ε=${fmt(r.epsilon)}`,esc(r.created_at),r.downloadable?'可下载':'不可下载']);
 const list=`<h2>受保护发布记录</h2>${table(['发布','状态','本次 ε','创建时间','下载'],rows)}`;

 let detail='';
 if(selected){
  const r=selected;
  const failures=r.status==='failed'?`<div class="error">生成失败：${esc(r.error||'未知错误')}。受保护发布不可篡改；请修复数据后重新提交。</div>`:'';
  const pendingNote=r.status==='available'?'':`<div class="method-note">${esc(STATE[r.status]||r.status)}。扣费、扰动结果与留档齐全前不展示数值、不可下载；此页每2秒刷新。</div>`;
  const failedArchive=r.error&&r.status!=='failed'?`<div class="error">${esc(r.error)}</div>${canWrite()?`<div class="toolbar"><button id="retry-release">重试留档（复用原结果，不重新扣费）</button></div>`:''}`:'';
  const body=r.status==='available'&&r.result?`
   <section class="result-intro"><strong>受保护分布 · 指标 ${esc(r.result.field_label)} · 本次 ε=${fmt(r.result.epsilon)}</strong><p>${esc(r.result.caveat)}</p></section>
   <h2>${esc(r.result.table_title)}</h2>${table(r.result.columns,r.result.rows)}
   <h2>分位数（由同一份非负箱计数推导）</h2>${table(['分位点','分组估计值'],Object.entries(r.result.quantiles).map(([k,v])=>[k,fmt(v)]))}
   <h2>${esc(r.result.chart.title)}</h2><div class="chart">${r.result.chart.points.map(([x,y])=>`<div class="chart-row"><span>${esc(fmt(x))}</span><i style="width:${Math.max(1,Math.min(100,Number(y)*100))}%"></i><b>${esc(fmt(y))}</b></div>`).join('')}</div>
   <div class="toolbar"><button id="export-release">下载受保护发布 CSV</button></div>`:'';
  detail=`<h2>#${r.id} ${esc(r.name)} <small>${esc(STATE[r.status]||r.status)} · 本次 ε=${fmt(r.epsilon)}</small></h2><div class="checksum">已扣费 ε=${fmt(r.spent_after_epsilon ?? r.epsilon)} · 剩余 ε=${fmt(r.remaining_epsilon_after)} ${r.downloadable?'· 留档已完成，可下载':'· 留档未完成或不可下载'}</div>${failures}${failedArchive}${pendingNote}${body}`;
 }

 return `<div class="eyebrow">03 / PROTECTED RELEASE</div><h1>受保护分布发布</h1><p>${esc(meta.note||'')} 观察员只读取受保护分布；原值、精确计数与历史精确研究不对其开放。</p><div class="toolbar">${studySelect()}</div>${policyBlock}${releaseForm}${list}${detail}`;
}

export function bind(refresh){
 const sel=document.getElementById('study-select');
 if(sel)sel.onchange=()=>{store.studyId=+sel.value;store.releaseId=0;refresh();};
 bindForm('policy-form',async data=>{const bins=String(data.bins).split(',').map(x=>x.trim()).filter(Boolean).map(Number);await protection.policy(store.studyId,{field:data.field,bins,total_epsilon:+data.total_epsilon});await loadProtection();refresh();});
 bindForm('release-form',async data=>{const r=await protection.create(store.studyId,{name:data.name,epsilon:+data.epsilon});store.releaseId=r.id;location.hash='protected/'+r.id;refresh();});
 const retry=document.getElementById('retry-release');
 if(retry)retry.onclick=async()=>{try{await protection.retry(store.releaseId);refresh();}catch(e){document.getElementById('notice').textContent=e.message;}};
 const exp=document.getElementById('export-release');
 if(exp)exp.onclick=async()=>{try{download(await protection.export(store.releaseId),'protected-release-'+store.releaseId+'.csv');}catch(e){document.getElementById('notice').textContent=e.message;}};
}
