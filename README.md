# 小企业财务记账系统

基于《小企业会计准则》的简洁版财务记账 Web 站点,前后端分离。支持**记账凭证录入**、**附件(发票/回单)关联**、**财务报表汇总**。

> 数据模型来源:`小企业会计财务原始记录.xlsx`。架构详见 [docs/BLUEPRINT.md](docs/BLUEPRINT.md)。

## 功能

- **记账凭证**:多行分录、会计科目下拉、实时借贷平衡校验、自动凭证号
- **附件管理**:每张凭证可上传发票/回单等原始单据,**在线预览**(图片/PDF/文本)与下载
- **会计科目**:预置 81 个标准科目(资产/负债/权益/成本/损益),支持自定义
- **财务报表(小企业会计准则官方格式)**:资产负债表(会小企01)、利润表(会小企02)、现金流量表(会小企03)、科目汇总表;支持**月报/季报/年报**切换,并可**一键导出符合税务报送模板的 Excel**
- **仪表盘**:收入/支出/净利润概览 + 近 6 月趋势图
- **企业信息**:公司名称、负责人、会计、审核、记账、录入
- **数据备份/恢复**:整站数据(企业信息、科目、凭证、附件)一键导出为 zip,可一键导入恢复

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + SQLAlchemy 2.0 + PostgreSQL |
| 前端 | React 18 + Vite + TypeScript + Ant Design 5 |
| 部署 | Docker Compose + Nginx |

## 目录结构

```
CW/
├── backend/            FastAPI 后端
│   ├── app/
│   │   ├── main.py         应用入口
│   │   ├── models.py       ORM 模型
│   │   ├── schemas.py      Pydantic 校验(含借贷平衡)
│   │   ├── seed_accounts.py 81 个科目种子
│   │   └── routers/        company/accounts/vouchers/attachments/reports
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/           React 前端
│   ├── src/pages/          Dashboard/VoucherList/VoucherEdit/Accounts/Reports/Settings
│   ├── nginx.conf          静态托管 + /api 反代
│   └── Dockerfile
├── docker-compose.yml
├── deploy.sh           Ubuntu 一键部署
└── .env.example
```

## 快速开始(Docker,推荐)

```bash
cp .env.example .env        # 按需修改端口/密码
docker compose up -d --build
# 访问 http://localhost:8080
```

## Ubuntu 云端一键下载并部署(推荐)

在全新的 Ubuntu 云服务器上,**只需一行命令**即可自动完成「安装 Docker/git → 从 GitHub 下载代码 → 构建启动」:

```bash
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | bash
```

自定义端口/安装目录(可选):

```bash
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | HTTP_PORT=80 APP_DIR=/opt/cw bash
```

`install.sh` 会自动:
1. 安装 `git` 与 `Docker`(含 compose 插件,若尚未安装)
2. 克隆本仓库到 `~/CW`(或 `APP_DIR`)
3. 生成 `.env`(随机数据库密码)并调用 `deploy.sh` 构建启动
4. 健康检查;**再次运行同一命令即可拉取最新代码并自动更新**

部署完成后访问 `http://<服务器IP>:<端口>`(默认 8080)。

> 非 root 用户需具备 `sudo`;脚本会按需提权安装系统依赖。

## 一键升级到最新版本

在已部署的 Ubuntu 服务器上,**任意目录直接执行一行命令**即可升级(无需进入安装目录):

```bash
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/upgrade.sh | bash
```

脚本会**自动定位**已部署目录(通过运行中的 Docker 栈 / 常见路径 / 仓库搜索),然后:
1. **升级前自动备份**当前数据到 `<部署目录>/backups/finance-backup-<时间>.zip`
2. 从 GitHub 拉取最新代码(已是最新则直接退出)
3. 重建镜像并重启(`docker compose up -d --build`,**保留数据卷,数据不丢失**)
4. 健康检查,并打印本次更新的提交内容

若自动定位失败(如安装在非常见路径),显式指定目录:

```bash
APP_DIR=/opt/cw bash -c "$(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/upgrade.sh)"
```

也可在仓库目录内直接运行 `./upgrade.sh`。

> 升级仅重建容器、保留数据卷;只有显式 `docker compose down -v` 才会清空数据。

## 已克隆代码后的本地部署

若已 `git clone` 仓库到本地,在仓库目录执行:

```bash
./deploy.sh
```

脚本会自动:检查 Docker → 生成 `.env`(随机数据库密码)→ 构建启动 → 健康检查。

> 生产建议:在前置反向代理(如 Nginx/Caddy)上配置 HTTPS 与域名,并在 `.env` 收紧 `CORS_ORIGINS`。

## 本地开发(不用 Docker)

后端(需 Python 3.10+):
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 本地用 SQLite 快速试跑:
DATABASE_URL="sqlite:///./dev.db" UPLOAD_DIR="./uploads" uvicorn app.main:app --reload
```

前端:
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173,/api 自动代理到 :8000
```

## 常用运维

```bash
docker compose logs -f backend   # 查看后端日志
docker compose down              # 停止(保留数据卷)
docker compose down -v           # 停止并清空数据(慎用)
```

## 数据持久化

- 数据库:Docker 卷 `db_data`
- 附件文件:Docker 卷 `uploads`(后端容器 `/data/uploads`)

## 核心约束

- 每张凭证强制 **Σ借方 = Σ贷方**(复式记账),前后端双重校验
- 报表为基于凭证分录的**实时聚合**,无需月末结转
- 简洁版:单租户、无登录鉴权(可后续扩展)
