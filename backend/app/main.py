"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .init_db import init_db
from .routers import company, accounts, vouchers, attachments, reports, data_io


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="小企业财务记账系统", version="1.0.0", lifespan=lifespan)

origins = ["*"] if settings.cors_origins.strip() == "*" else [
    o.strip() for o in settings.cors_origins.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok"}


app.include_router(company.router)
app.include_router(accounts.router)
app.include_router(vouchers.router)
app.include_router(attachments.router)
app.include_router(reports.router)
app.include_router(data_io.router)
