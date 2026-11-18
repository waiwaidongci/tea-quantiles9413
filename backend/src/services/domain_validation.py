import math
from src.config.domain import DOMAIN

def validate_values(values):
    expected={f[0] for f in DOMAIN['fields']}
    if set(values)!=expected: raise ValueError('字段必须为 '+', '.join(expected))
    out={}
    for key,label,kind in DOMAIN['fields']:
        v=values[key]
        if kind=='text':
            if v not in ('A','B'): raise ValueError('工艺组必须为A或B')
        else:
            if isinstance(v,bool): raise ValueError(label+'必须是数值')
            v=float(v)
            if not math.isfinite(v) or abs(v)>1e9: raise ValueError(label+'必须为有限业务数值')
            if v<0: raise ValueError(label+'不得为负')
        out[key]=v
    i=DOMAIN['index']
    if i==0 and any(v>100 for v in out.values()): raise ValueError('百分比必须在0到100之间')
    if i==1:
        if any(out[k]!=int(out[k]) or out[k]>100000 for k in ('success','failure')): raise ValueError('计数必须为0到100000的整数')
        if out['success']+out['failure']==0: raise ValueError('组内总数必须大于0')
    if i==4:
        if not 0<out['p0']<1 or not 0<out['p1']<1 or out['p0']==out['p1']: raise ValueError('两概率须在0和1之间且不同')
        if out['cost_per_contact']<=0 or out['budget']<=0: raise ValueError('成本与预算须为正')
    return out

def validate_parameters(params):
    defaults=DOMAIN['defaults']
    if not isinstance(params,dict) or set(params)-set(defaults): raise ValueError('存在未知分析参数')
    p=defaults|params
    if 'field' in p and p['field'] not in [f[0] for f in DOMAIN['fields']]: raise ValueError('未知指标')
    for key in ('resamples','simulations'):
        if key in p:
            v=p[key]
            if isinstance(v,bool) or not isinstance(v,(int,float)) or int(v)!=v or not 200<=v<=20000: raise ValueError('重采样次数必须是200到20000的整数')
            p[key]=int(v)
    for key in ('alpha','power'):
        if key in p:
            p[key]=float(p[key])
            if not math.isfinite(p[key]) or not (0.001<=p[key]<=0.2 if key=='alpha' else 0.5<=p[key]<=0.99): raise ValueError('显著性或功效超出范围')
    return p
