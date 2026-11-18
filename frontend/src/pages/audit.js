import {request} from '../api/client.js';
import {table} from '../components/common/table.js';
export async function render(){const rows=await request('/audits');return `<div class="eyebrow">05 / TRACE REGISTER</div><h1>操作留痕</h1><p>登录、数据修改、任务提交、复核与下载均留有可查询记录。显示最近100条。</p>${table(['时间 (UTC)','账号','动作','对象 / 说明'],rows.map(x=>[x.created_at,x.actor,x.action,x.detail]))}`;}
export function bind(){}
