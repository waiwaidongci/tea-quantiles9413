from src.models.audit import Audit
from src.utils.serializers import now
def log(db,user,action,detail):
    db.add(Audit(actor=user.email if hasattr(user,'email') else str(user),action=action,detail=str(detail),created_at=now()))
