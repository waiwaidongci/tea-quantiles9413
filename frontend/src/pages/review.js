import {store,load} from '../stores/research.js';
import {runs} from '../api/research.js';
import {table} from '../components/common/table.js';
import {esc} from '../utils/format.js';
import {bindForm} from '../hooks/forms.js';
export async function render(id){const complete=store.runs.filter(r=>r.status==='completed');const r=id?await runs.get(id):null;return `<div class="eyebrow">04 / BUSINESS RELEASE</div><h1>复核与研究交付</h1><p>负责人记录使用范围和下一步动作。复核记录不可覆盖，观察员只能导出已复核结果。</p>${r?`<h2>#${r.id} ${esc(r.name)}</h2>${r.review?`<div class="method-note"><strong>已复核</strong><p>${esc(r.review.note)}</p><small>${esc(r.review.author)} · ${esc(r.review.created_at)}</small></div>`:localStorage.getItem('research-role')==='admin'?`<form id="review-form"><label>复核意见与后续动作<textarea name="note" minlength="5" maxlength="2000" required placeholder="写明数据范围、方法边界和复测/预算建议"></textarea></label><button type="submit">确认复核并归档</button></form>`:'<div class="method-note">等待负责人复核；分析师可以查看全部计算依据。</div>'}`:''}${table(['运行','复核状态','动作'],complete.map(x=>[x.name,x.review?x.review.note:'待复核',{html:`<a href="#review/${x.id}">查看 / 复核 →</a>`}]))}`;}
export function bind(refresh){bindForm('review-form',async data=>{const id=Number(location.hash.split('/')[1]);await runs.review(id,data.note);await load();refresh();});}
