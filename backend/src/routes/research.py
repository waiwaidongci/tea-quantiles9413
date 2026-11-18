from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from src.config.database import get_db
from src.config.domain import DOMAIN
from src.middlewares.auth import current_user,writer,admin
from src.schemas.study import StudyInput
from src.schemas.observation import ObservationInput
from src.schemas.run import RunInput
from src.schemas.review import ReviewInput
from src.schemas.protection import ProtectionPolicyInput,ProtectionReleaseInput
from src.controllers import research
from src.services import runs,studies,protection
from src.models.audit import Audit
from src.models.protected import ProtectedPolicy
from src.models.observation import Observation
from src.services.audits import log
from src.utils.serializers import record
router=APIRouter()
@router.get('/domain')
def domain(user=Depends(current_user)): return DOMAIN
@router.get('/overview')
def overview(db=Depends(get_db),user=Depends(current_user)): return research.overview(db,user)
@router.get('/studies')
def list_studies(db=Depends(get_db),user=Depends(current_user)): return studies.list_studies(db,user)
@router.post('/studies')
def create_study(data:StudyInput,db=Depends(get_db),user=Depends(writer)): return research.create_study(db,data,user)
@router.get('/studies/{id}/observations')
def rows(id:int,db=Depends(get_db),user=Depends(current_user)): return research.list_rows(db,id,user)
@router.post('/studies/{id}/observations')
def add(id:int,data:ObservationInput,db=Depends(get_db),user=Depends(writer)): return research.save_row(db,id,data,user)
@router.put('/studies/{id}/observations/{row_id}')
def update(id:int,row_id:int,data:ObservationInput,db=Depends(get_db),user=Depends(writer)): return research.save_row(db,id,data,user,row_id)
@router.delete('/studies/{id}/observations/{row_id}')
def remove(id:int,row_id:int,db=Depends(get_db),user=Depends(writer)):
    row=db.get(Observation,row_id)
    if not row or row.study_id!=id: raise HTTPException(404,'记录不存在')
    study_id=row.study_id;db.delete(row);log(db,user,'observation.delete',row_id,study_id);db.commit();return {'deleted':True}
@router.get('/runs')
def list_runs(db=Depends(get_db),user=Depends(current_user)): return runs.list_runs(db,user)
@router.post('/runs')
def create_run(data:RunInput,db=Depends(get_db),user=Depends(writer)): return research.create_run(db,data,user)
@router.get('/runs/{id}')
def get_run(id:int,db=Depends(get_db),user=Depends(current_user)): return runs.get(db,id,user)
@router.post('/runs/{id}/review')
def review(id:int,data:ReviewInput,db=Depends(get_db),user=Depends(admin)): return research.review_run(db,id,data,user)
@router.get('/runs/{id}/export')
def export(id:int,db=Depends(get_db),user=Depends(current_user)):
    return Response(content=runs.export(db,id,user).encode('utf-8'),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="research-{id}.csv"'})
# ---- protected distribution releases -------------------------------------
@router.get('/studies/{id}/protection')
def protection_info(id:int,db=Depends(get_db),user=Depends(current_user)): return protection.info(db,id,user)
@router.post('/studies/{id}/protection')
def create_protection(id:int,data:ProtectionPolicyInput,db=Depends(get_db),user=Depends(admin)): return protection.create_policy(db,id,data,user)
@router.get('/studies/{id}/protected-releases')
def protected_releases(id:int,db=Depends(get_db),user=Depends(current_user)): return protection.list_releases(db,id,user)
@router.post('/studies/{id}/protected-releases')
def create_protected_release(id:int,data:ProtectionReleaseInput,db=Depends(get_db),user=Depends(writer)): return protection.create_release(db,id,data,user)
@router.get('/protected-releases/{id}')
def protected_release(id:int,db=Depends(get_db),user=Depends(current_user)): return protection.get_release(db,id,user)
@router.post('/protected-releases/{id}/retry')
def retry_protected_release(id:int,db=Depends(get_db),user=Depends(writer)): return protection.retry(db,id,user)
@router.get('/protected-releases/{id}/export')
def export_protected_release(id:int,db=Depends(get_db),user=Depends(current_user)):
    return Response(content=protection.export_csv(db,id,user).encode('utf-8'),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="protected-release-{id}.csv"'})
@router.get('/audits')
def audits(db=Depends(get_db),user=Depends(current_user)):
    rows=list(db.scalars(select(Audit).order_by(Audit.id.desc()).limit(100)))
    if user.role=='viewer':
        # Observation edits and exact-run traces for a protected batch would
        # reveal its size or exact results, so observers only see the
        # protected-release events (which carry no exact values).
        protected=set(db.scalars(select(ProtectedPolicy.study_id)))
        rows=[x for x in rows if x.study_id not in protected or x.action.startswith('protection.')]
    return [record(x) for x in rows]
