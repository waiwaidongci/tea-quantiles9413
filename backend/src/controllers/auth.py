from fastapi import HTTPException
from sqlalchemy import select
from src.models.user import User
from src.utils.security import verify_password,token
from src.services.audits import log

def login(db,data):
    user=db.scalar(select(User).where(User.email==data.email))
    if not user or not verify_password(data.password,user.password_hash): raise HTTPException(401,'账号或密码错误')
    log(db,user,'auth.login','signed in');db.commit();return {'token':token(user),'role':user.role,'email':user.email}
