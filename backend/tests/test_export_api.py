"""新增导出路由的 HTTP 契约与预览/ZIP 一致性。"""
import io
import tempfile
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.routers import ledgers, reports


def test_export_routes():
    engine = create_engine("sqlite+pysqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(ledgers.router)
    app.include_router(reports.router)
    app.dependency_overrides[get_db] = lambda: session()
    with tempfile.TemporaryDirectory() as temp:
        previous = settings.upload_dir
        settings.upload_dir = temp
        try:
            client = TestClient(app)
            payload = {"ledger_type": "all", "report_type": "month", "year": 2026,
                       "month": 7, "mode": "date"}
            preview = client.post("/api/ledgers/archive-preview", json=payload)
            assert preview.status_code == 200
            result = client.post("/api/ledgers/archive-export", json=payload)
            assert result.status_code == 200 and result.headers["content-type"] == "application/zip"
            with zipfile.ZipFile(io.BytesIO(result.content)) as zf:
                assert set(zf.namelist()) == {i["path"] for i in preview.json()["items"]}
            pdf = client.get("/api/reports/export-pdf?report_type=month&year=2026&month=7&preview=true")
            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
            assert pdf.headers["content-disposition"].startswith("inline")
            bad = client.get("/api/reports/export-pdf?report_type=month&year=2026&month=7&orientation=bad")
            assert bad.status_code == 400
        finally:
            settings.upload_dir = previous


if __name__ == "__main__":
    test_export_routes()
    print("结果:全部通过")
