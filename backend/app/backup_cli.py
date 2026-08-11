"""命令行备份:直接读库生成整站备份 zip 并写入 stdout,无需 HTTP/登录。

用途:一键升级/运维脚本在容器内执行,避免强制登录导致 HTTP 导出被 401。
用法:  python -m app.backup_cli > finance-backup.zip
"""
import sys

from .database import SessionLocal
from .routers.data_io import build_backup_zip


def main() -> int:
    db = SessionLocal()
    try:
        data = build_backup_zip(db)
    finally:
        db.close()
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
