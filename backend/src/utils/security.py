import hashlib,hmac,secrets,os
from datetime import datetime,timedelta,timezone
import jwt
SECRET=os.environ['JWT_SECRET']
def hash_password(password):
    salt=secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),180000).hex()
def verify_password(password,value):
    salt,digest=value.split(':')
    return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),180000).hex(),digest)
def token(user):
    return jwt.encode({'sub':str(user.id),'role':user.role,'exp':datetime.now(timezone.utc)+timedelta(hours=8)},SECRET,algorithm='HS256')
