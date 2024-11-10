from fastapi import FastAPI
from contextlib import asynccontextmanager

from db import init_db
from settings import settings

from transaction.routes import transaction_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)

app.include_router(transaction_router)

