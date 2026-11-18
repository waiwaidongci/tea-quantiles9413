import os,time,json,logging
from pathlib import Path
from sqlalchemy import select,update
from src.config.database import Session
from src.config.runtime import get_redis, artifact_dir
from src.models.run import Run
from src.models.protected import ProtectedRelease
from src.models import user,study,observation,review,audit,protected
from src.services.algorithm import calculate
from src.services.protection import process_release
from src.utils.serializers import checksum
redis=get_redis()
artifact_dir().mkdir(parents=True,exist_ok=True)
# Recover jobs interrupted after dequeue. A project runs exactly one worker.
with Session() as db:
    pending=list(db.scalars(select(Run).where(Run.status.in_(['queued','running']))))
    for run in pending: redis.rpush('analysis-queue',run.id)
    # Protected releases interrupted at any stage keep the queue entry too.
    # A single worker owns the queue, so any leftover claim is stale.
    db.execute(update(ProtectedRelease).where(ProtectedRelease.status=='generating').values(status='pending'))
    db.commit()
    for release in db.scalars(select(ProtectedRelease.id).where(ProtectedRelease.status=='pending')):
        redis.rpush('protected-queue',release)
while True:
    Path('/tmp/worker-heartbeat').touch()
    job=redis.blpop(['analysis-queue','protected-queue'],timeout=2)
    if not job: continue
    queue,raw=job
    if queue==b'protected-queue':
        try: process_release(int(raw))
        except Exception: logging.exception('protected release failed')
        continue
    id=int(raw)
    with Session() as db:
        run=db.get(Run,id)
        if not run or run.status in ('completed','failed'): continue
        run.status='running';db.commit()
        try:
            if checksum(run.snapshot)!=run.checksum: raise ValueError('输入快照校验失败')
            result=calculate(run.snapshot,run.parameters)
            result['input_sha256']=run.checksum
            run.result=result;run.status='completed'
            Path(artifact_dir()/f'run-{id}.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
        except Exception as e:
            logging.exception('analysis failed');run.status='failed';run.error=str(e)
        db.commit()
