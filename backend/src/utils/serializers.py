from datetime import datetime,timezone
import hashlib,json
from sqlalchemy import inspect
def now(): return datetime.now(timezone.utc).isoformat()
def record(obj): return {c.key:getattr(obj,c.key) for c in inspect(obj).mapper.column_attrs}
def checksum(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
