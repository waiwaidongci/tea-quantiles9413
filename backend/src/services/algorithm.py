import math
import numpy as np
from scipy import stats

def finite_rows(snapshot,keys):
    if not snapshot: raise ValueError('空批次无法分析')
    result=[]
    for row in snapshot:
        values=row['values']
        if any(k not in values for k in keys): raise ValueError('观测字段不完整')
        x=[float(values[k]) for k in keys]
        if not all(math.isfinite(v) for v in x): raise ValueError('观测必须为有限数值')
        result.append(x)
    return np.asarray(result,dtype=float)

def quantile(values,q):
    values=sorted(float(x) for x in values)
    if not values: raise ValueError('无样本')
    h=(len(values)-1)*q;i=int(math.floor(h));j=int(math.ceil(h))
    return values[i]+(values[j]-values[i])*(h-i)

def calculate(snapshot,params):
    field=params.get('field','moisture');B=int(params.get('resamples',2000))
    if field not in ('moisture','extract'): raise ValueError('未知指标')
    x=finite_rows(snapshot,[field])[:,0]
    if len(x)<3: raise ValueError('至少3份独立茶样才能估计分布')
    if len(x)>5000 or not 200<=B<=20000: raise ValueError('样本/重采样超出上限')
    rng=np.random.default_rng(42)
    # Each selected TeaLot is one independent batch. Resampling stays within batch.
    boot=[]
    for start in range(0,B,100):
        draws=rng.choice(x,size=(min(100,B-start),len(x)),replace=True)
        boot.extend(np.median(draws,axis=1).tolist())
    lower,upper=quantile(boot,.025),quantile(boot,.975)
    q={label:quantile(x,p) for label,p in [('最小值',0),('P25',.25),('中位数',.5),('P75',.75),('最大值',1)]}
    unique=np.unique(x);ecdf=[[float(v),float(np.count_nonzero(x<=v)/len(x))] for v in unique]
    # Plot a sampled ECDF for large batches; full ECDF is retained in result JSON.
    step=max(1,len(ecdf)//24)
    return {'metrics':{'样本量':len(x),'均值':float(np.mean(x)),'样本标准差':float(np.std(x,ddof=1)),**q,'中位数95%区间':[lower,upper],'IQR':q['P75']-q['P25'],'重采样次数':B,'随机种子':42},'interpretation':f"本批{len(x)}份茶样的{ {'moisture':'含水率(%)','extract':'水浸出率(%)'}[field]}中位数为{q['中位数']:.3f}，95% percentile bootstrap置信区间为[{lower:.3f}, {upper:.3f}]。",'caveat':'本区间描述本批总体中位数估计的不确定性，不是单份茶样预测区间；独立同分布的批内抽样假设需人工核对。常量批次区间会退化。','columns':['分位点','线性插值结果'],'rows':[[k,v] for k,v in q.items()],'table_title':'分布位置与离散程度','ecdf':ecdf,'chart':{'title':'经验累积分布 ECDF · 横条为累计比例','points':ecdf[::step]}}
