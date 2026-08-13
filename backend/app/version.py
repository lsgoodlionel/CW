"""应用版本与关于信息(单一来源,供 main、关于页、用户手册引用)。"""

APP_NAME = "小企业财务记账系统"
APP_VERSION = "1.0.0"
RELEASE_DATE = "2026-08-13"
DESCRIPTION = (
    "面向小微企业、基于《小企业会计准则》的完整财务记账系统:复式记账、"
    "官方格式财务报表与六类账簿、往来单位与人员管理、审批流程、"
    "费用申请与报销、用户与权限(RBAC)、数据备份恢复、操作日志留痕。"
)
DEVELOPER = "lsgoodlionel"
REPO_URL = "https://github.com/lsgoodlionel/CW"
FEEDBACK_URL = "https://github.com/lsgoodlionel/CW/issues"
CONTACT = "通过 GitHub Issues 反馈问题与建议"
MANUAL_URL = "/manual.html"          # 静态托管的用户手册(在线查看)
MANUAL_DOWNLOAD = "/manual.html"     # 同一文件可另存为下载


def about() -> dict:
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "released": RELEASE_DATE,
        "description": DESCRIPTION,
        "developer": DEVELOPER,
        "repo_url": REPO_URL,
        "feedback_url": FEEDBACK_URL,
        "contact": CONTACT,
        "manual_url": MANUAL_URL,
        "manual_download": MANUAL_DOWNLOAD,
        "tech_stack": [
            "FastAPI", "SQLAlchemy 2", "PostgreSQL 16",
            "React 18", "TypeScript", "Ant Design 5", "Docker Compose", "Nginx",
        ],
    }
