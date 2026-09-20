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

    # 部署模式:private=私有化单租户(默认,行为同单机版,隐藏租户/平台管理)
    #           saas=多租户(登录选租户、平台管理后台、按租户隔离)
    deploy_mode: str = "private"

    # 自助注册(仅 saas 生效):开放后访客可自助开通租户并进入试用
    allow_self_registration: bool = False
    # 新注册租户试用天数
    trial_days: int = 30

    # 运行诊断:出错自动打包日志并上传到共享 GitHub 仓库(供开发拉取排查)
    error_report_enabled: bool = True            # 总开关(仍需提供 token 才会真正上传)
    paper_repo: str = "lsgoodlionel/paper"       # owner/repo(多应用共用)
    paper_repo_token: str = ""                   # GitHub PAT(contents 写权限);空则功能禁用
    paper_repo_branch: str = "main"
    log_app_slug: str = "CW"                     # 仓库内本应用顶层目录:<slug>/logs/<时间戳>.zip
    error_report_cooldown: int = 600             # 同类错误上传冷却秒数(节流去重)


settings = Settings()

DEFAULT_TENANT_ID = 1   # 私有化/存量数据的默认租户

def is_saas() -> bool:
    return settings.deploy_mode == "saas"
