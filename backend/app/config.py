"""应用配置:从环境变量读取,带合理默认值。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 数据库连接;默认值便于本地不带 Docker 直接跑(SQLite 兜底见 database.py)
    database_url: str = "postgresql+psycopg://finance:finance@localhost:5432/finance"

    # 附件上传根目录
    upload_dir: str = "/data/uploads"

    # 单个附件大小上限(字节),默认 20MB
    max_upload_bytes: int = 20 * 1024 * 1024

    # 允许跨域来源(逗号分隔)
    cors_origins: str = "*"

    # 鉴权:是否全站强制登录、令牌签名密钥与有效期、初始超管密码
    require_auth: bool = True
    auth_secret: str = "change-me-please-set-AUTH_SECRET"
    token_ttl_hours: int = 12
    admin_password: str = "admin123"


settings = Settings()
