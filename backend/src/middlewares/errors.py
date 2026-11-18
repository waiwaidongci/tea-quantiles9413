from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
class ErrorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request,call_next):
        try: return await call_next(request)
        except Exception:
            logging.exception('request failed')
            return JSONResponse({'detail':'内部错误，请稍后重试；已记录错误日志'},status_code=500)
