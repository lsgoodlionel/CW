"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .init_db import init_db
from .oplog import OperationLogMiddleware
from .auth_mw import AuthMiddleware
from .routers import (
    company, accounts, vouchers, attachments, reports, data_io, ledgers, logs,
    customers, personnel, workflow, expense, auth, users,
)


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
# 操作日志中间件(记录数据变更与导入导出/下载行为)
app.add_middleware(OperationLogMiddleware)
# 鉴权中间件(全站强制登录 + 权限校验)——最后添加使其最外层,先于日志运行
app.add_middleware(AuthMiddleware)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok"}


app.include_router(company.router)
app.include_router(accounts.router)
app.include_router(vouchers.router)
app.include_router(attachments.router)
app.include_router(reports.router)
app.include_router(data_io.router)
app.include_router(ledgers.router)
app.include_router(logs.router)
app.include_router(customers.router)
app.include_router(personnel.router)
app.include_router(workflow.router)
app.include_router(expense.router)
app.include_router(auth.router)
app.include_router(users.router)
