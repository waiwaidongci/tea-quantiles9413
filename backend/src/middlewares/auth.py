import jwt
from fastapi import Depends,HTTPException
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from src.config.database import get_db
from src.models.user import User
from src.utils.security import SECRET
bearer=HTTPBearer(auto_error=False)
def current_user(credentials:HTTPAuthorizationCredentials=Depends(bearer),db=Depends(get_db)):
    if not credentials: raise HTTPException(401,'请先登录')
    try:
        payload=jwt.decode(credentials.credentials,SECRET,algorithms=['HS256'])
        user=db.get(User,int(payload['sub']))
        if not user: raise ValueError('unknown user')
        return user
    except Exception:
        raise HTTPException(401,'登录已过期，请重新登录')
def writer(user=Depends(current_user)):
    if user.role not in ('admin','analyst'): raise HTTPException(403,'观察员仅可读取')
    return user
def admin(user=Depends(current_user)):
    if user.role!='admin': raise HTTPException(403,'此动作需要负责人')
    return user
