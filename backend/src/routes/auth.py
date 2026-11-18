from fastapi import APIRouter,Depends
from src.config.database import get_db
from src.schemas.auth import Login
from src.controllers.auth import login
router=APIRouter()
@router.post('/auth/login')
def sign_in(data:Login,db=Depends(get_db)): return login(db,data)
