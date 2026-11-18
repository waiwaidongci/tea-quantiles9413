from src.models.audit import Audit
from src.utils.serializers import now
def log(db,user,action,detail,study_id=None):
    db.add(Audit(actor=user.email if hasattr(user,'email') else str(user),action=action,detail=str(detail),study_id=study_id,created_at=now()))
