import os
from pathlib import Path
from redis import Redis

_redis=None
_redis_url=None

def artifact_dir():
    return Path(os.environ.get('ARTIFACT_DIR','/app/artifacts'))

def release_artifact(release_id):
    return artifact_dir()/f'protected-release-{int(release_id)}.json'

def get_redis():
    """Return the process-wide Redis client. fakeredis:// is test-only."""
    global _redis,_redis_url
    url=os.environ['REDIS_URL']
    if _redis is not None and _redis_url==url:
        return _redis
    if url.startswith('fakeredis://'):
        import fakeredis
        _redis=fakeredis.FakeRedis(decode_responses=False)
    else:
        _redis=Redis.from_url(url)
    _redis_url=url
    return _redis
