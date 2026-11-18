import os,time,json,logging
from pathlib import Path
from redis import Redis
from sqlalchemy import select
from src.config.database import Session
from src.models.run import Run
from src.models import user,study,observation,review,audit
from src.services.algorithm import calculate
from src.utils.serializers import checksum
redis=Redis.from_url(os.environ['REDIS_URL'])
Path('/app/artifacts').mkdir(exist_ok=True)
# Recover jobs interrupted after dequeue. A project runs exactly one worker.
with Session() as db:
    pending=list(db.scalars(select(Run).where(Run.status.in_(['queued','running']))))
    for run in pending: redis.rpush('analysis-queue',run.id)
while True:
    Path('/tmp/worker-heartbeat').touch()
    job=redis.blpop('analysis-queue',timeout=2)
    if not job: continue
    id=int(job[1])
    with Session() as db:
        run=db.get(Run,id)
        if not run or run.status in ('completed','failed'): continue
        run.status='running';db.commit()
        try:
            if checksum(run.snapshot)!=run.checksum: raise ValueError('输入快照校验失败')
            result=calculate(run.snapshot,run.parameters)
            result['input_sha256']=run.checksum
            run.result=result;run.status='completed'
            Path(f'/app/artifacts/run-{id}.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
        except Exception as e:
            logging.exception('analysis failed');run.status='failed';run.error=str(e)
        db.commit()
