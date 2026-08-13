"""把 OpenAPI 规范打到标准输出,供前端生成 TypeScript 契约。

    docker compose exec -T backend python -m app.openapi_dump

不连数据库、不启服务,只做 schema 反射,可在任意环境安全执行。
"""
import json

from .main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))
