import os,logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from redis import Redis
from src.config.database import Base,engine
from src.models import user,study,observation,run,review,audit
from src.routes import auth,research
from src.middlewares.errors import ErrorMiddleware
from src.middlewares.rate_limit import RateLimitMiddleware
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    if os.environ.get('SEED_DEMO')=='true':
        try:
            from scripts.seed_demo import seed
            seed()
        except Exception: logging.exception('seed failed; manual seed available')
    yield
app=FastAPI(lifespan=lifespan,title='Research Application')
app.add_middleware(ErrorMiddleware)
app.add_middleware(RateLimitMiddleware)
app.include_router(auth.router);app.include_router(research.router)
@app.get('/health')
def health():
    with engine.connect() as conn: conn.execute(text('SELECT 1'))
    Redis.from_url(os.environ['REDIS_URL']).ping()
    return {'status':'healthy'}
