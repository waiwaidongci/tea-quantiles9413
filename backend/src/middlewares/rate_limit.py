import os
from redis import Redis
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
redis=Redis.from_url(os.environ['REDIS_URL'])
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request,call_next):
        if request.url.path!='/health':
            key='http:'+str(request.client.host)+':'+str(int(__import__('time').time())//60)
            n=redis.incr(key)
            if n==1: redis.expire(key,65)
            if n>240: return JSONResponse({'detail':'每分钟最多240次，请稍后重试'},status_code=429)
        return await call_next(request)
