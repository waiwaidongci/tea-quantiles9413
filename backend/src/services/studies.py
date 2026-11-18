from fastapi import HTTPException
from sqlalchemy import select,func
from src.models.study import Study
from src.models.observation import Observation
from src.services.domain_validation import validate_values
from src.services.audits import log
from src.utils.serializers import record

def list_studies(db):
    data=[]
    for s in db.scalars(select(Study).order_by(Study.id)):
        x=record(s);x['row_count']=db.scalar(select(func.count()).select_from(Observation).where(Observation.study_id==s.id));data.append(x)
    return data

def create(db,data,user):
    if db.scalar(select(Study).where(Study.name==data.name)): raise HTTPException(409,'批次名称已存在')
    s=Study(**data.model_dump());db.add(s);log(db,user,'study.create',data.name);db.commit();return record(s)

def require(db,id):
    s=db.get(Study,id)
    if not s: raise HTTPException(404,'业务批次不存在')
    return s

def observations(db,id):
    require(db,id);return [record(x) for x in db.scalars(select(Observation).where(Observation.study_id==id).order_by(Observation.id))]

def save_observation(db,id,data,user,row_id=None):
    require(db,id)
    try: values=validate_values(data.values)
    except (ValueError,TypeError) as e: raise HTTPException(422,str(e))
    other=db.scalar(select(Observation).where(Observation.study_id==id,Observation.source_key==data.source_key))
    if other and other.id!=row_id: raise HTTPException(409,'源记录编号重复')
    if row_id:
        row=db.get(Observation,row_id)
        if not row or row.study_id!=id: raise HTTPException(404,'记录不存在')
        row.source_key=data.source_key;row.values=values
    else:
        if len(observations(db,id))>=5000: raise HTTPException(422,'小型研究最多5000行')
        row=Observation(study_id=id,source_key=data.source_key,values=values);db.add(row)
    log(db,user,'observation.save',f'{id}/{data.source_key}');db.commit();return record(row)
