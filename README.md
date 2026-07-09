# 小企业财务记账系统

一套面向小微企业、基于《小企业会计准则》的完整财务记账 Web 系统。前后端分离,复式记账,自动生成官方格式财务报表与全套会计账簿,支持一键 Excel/PDF 导出、数据备份恢复、操作日志留痕,以及 Ubuntu 云服务器一行命令部署与升级。

> 数据模型源自《小企业会计财务原始记录.xlsx》;报表/账簿格式对齐税务报送与手工账官方模板。
> 设计蓝图见 [docs/BLUEPRINT.md](docs/BLUEPRINT.md),报表口径见 [docs/REPORTS.md](docs/REPORTS.md)。

---

## 目录

- [核心特性](#核心特性)
- [功能详解](#功能详解)
- [技术栈与架构](#技术栈与架构)
- [数据模型](#数据模型)
- [页面与路由](#页面与路由)
- [API 一览](#api-一览)
- [部署](#部署)
- [升级](#升级)
- [数据备份与持久化](#数据备份与持久化)
- [本地开发](#本地开发)
- [运维](#运维)
- [设计约束与已知限制](#设计约束与已知限制)
- [项目结构](#项目结构)

---

## 核心特性

| 模块 | 能力 |
|---|---|
| 记账凭证 | 多行分录、科目下拉、实时借贷平衡校验、自动凭证号 |
| 附件管理 | 发票/回单上传、在线预览(图片/PDF/文本)、下载 |
| 会计科目 | 预置 81 个准则科目,可自定义增改停用 |
| 财务报表 | 资产负债表/利润表/现金流量表(官方会小企格式)+ 科目汇总表,月/季/年切换,一键导出 Excel |
| 会计账簿 | 六类账簿(总账、明细账、日记账等)按凭证自动生成,按种类+年月季导出 Excel |
| 操作日志 | 全系统行为留痕,按类型+年月季查询,一键导出 PDF |
| 仪表盘 | 收入/支出/净利润概览 + 近 6 月趋势 |
| 数据备份 | 整站数据(含附件)一键导出 zip / 导入恢复 |
| 部署运维 | Docker 一键部署、云端一行命令安装、一行命令自动升级(升级前自动备份) |

---

## 功能详解

### 1. 记账凭证
- 一张凭证含多条分录(摘要、会计科目、明细科目、借方、贷方)
- **强制复式平衡**:保存时校验 `Σ借方 = Σ贷方`,前后端双重校验
- 凭证号可留空自动生成(`记-YYYYMM-NNN`)
- 按日期区间、凭证号/摘要关键字检索,分页列表

### 2. 附件(原始单据)
- 每张凭证可上传多个附件,分类为发票 / 回单 / 其他
- **在线预览**:图片直接渲染、PDF/文本内嵌预览,其他类型引导下载
- 附件随凭证删除级联清理,随数据备份一并导出/恢复

### 3. 会计科目
- 预置 81 个《小企业会计准则》标准科目,分为资产 / 负债 / 权益 / 成本 / 损益五类,带记账方向
- 支持新增自定义科目;已被凭证引用的科目改为停用(软删除)而非物理删除

### 4. 财务报表(官方格式)
按会小企官方模板生成,支持 **月报 / 季报 / 年报** 切换:

| 报表 | 表号 | 说明 |
|---|---|---|
| 资产负债表 | 会小企01表 | 期末余额 / 年初余额,双栏 53 行 |
| 利润表 | 会小企02表 | 32 行;列随类型切换(月季=本期/本年累计,年=本年累计/上年) |
| 现金流量表 | 会小企03表 | 22 行;对方科目归类法推导,期初/期末/净增加取账面现金 |
| 科目汇总表 | — | 试算平衡(借贷发生额与余额) |

- **一键导出 Excel**:1:1 还原模板版式(标题、表号、纳税人/所属期抬头、行次、列宽、边框),三张表为三个 sheet
- 现金流量表推导口径详见 [docs/REPORTS.md](docs/REPORTS.md)

### 5. 会计账簿(按凭证自动生成)
六类账簿,按 **种类 + 年/月/季** 一键导出 Excel(可导单类或全套六 sheet):

| 账簿 | 说明 |
|---|---|
| 总分类账 | 各科目期初、借贷发生、方向、余额 |
| 金额三栏式明细账 | 按科目 + 明细科目 |
| 金额多栏式明细账 | 某科目按明细科目横向展开借方分析 |
| 数量金额式明细账 | 存货类科目(仅金额,数量列见限制说明) |
| 现金日记账 | 库存资金,含对方科目、收入/付出、结余 |
| 银行存款日记账 | 银行存款,同上 |

### 6. 操作日志
- **中间件自动记录**全系统数据变更(凭证/科目/附件/企业信息的增删改)与导入导出/下载行为
- 记录内容:操作类型、行为描述、摘要、状态码、耗时、来源 IP、时间
- 按 **类型 + 年/季/月** 查询,**一键导出 PDF**(内置中文字体,无需外挂字库)

### 7. 数据备份 / 恢复
- 一键导出整站数据(企业信息、科目、凭证分录、附件文件)为单个 zip
- 一键导入 zip 快照整体恢复;兼容被系统自动解压后再压缩的嵌套目录结构

### 8. 仪表盘与企业信息
- 仪表盘:凭证数、营业收入、总支出、净利润卡片 + 近 6 月收入/净利润趋势图
- 企业信息:公司名称、负责人、会计主管、审核、记账、录入

---

## 技术栈与架构

| 层 | 技术 |
|---|---|
| 后端 | FastAPI · SQLAlchemy 2.0 · Pydantic v2 · PostgreSQL 16 |
| 报表/账簿导出 | openpyxl(Excel)· reportlab(PDF,内置中文 CID 字体) |
| 前端 | React 18 · Vite · TypeScript · Ant Design 5 · Recharts |
| 部署 | Docker Compose · Nginx(静态托管 + `/api` 反向代理) |

```
浏览器 ──▶ Nginx(frontend 容器) ──▶ /api ──▶ FastAPI(backend 容器) ──▶ PostgreSQL(db 容器)
                    │                                    │
              静态前端资源                          附件卷 /data/uploads
```

三个容器:`db`(PostgreSQL)、`backend`(uvicorn)、`frontend`(Nginx 托管前端 + 反代后端)。

---

## 数据模型

| 表 | 说明 |
|---|---|
| `company_info` | 企业基本信息(单例) |
| `accounts` | 会计科目(编码、名称、类别、方向、启用) |
| `vouchers` | 记账凭证(凭证号、日期、摘要、借贷合计、状态) |
| `voucher_entries` | 凭证分录(摘要、科目、明细科目、借方、贷方) |
| `attachments` | 附件(类型、原名、存储路径、MIME、大小) |
| `operation_logs` | 操作日志(类型、行为、摘要、状态码、耗时、IP、时间) |

**核心不变量**:每张凭证 `Σ借方 = Σ贷方`;报表/账簿均由凭证分录实时聚合,不做月末结转。

---

## 页面与路由

| 路由 | 页面 | 功能 |
|---|---|---|
| `/` | 仪表盘 | 概览卡片 + 趋势图 |
| `/vouchers` | 记账凭证 | 检索、分页、新建、删除 |
| `/vouchers/new`、`/vouchers/:id` | 凭证编辑 | 多行分录、实时平衡、附件上传预览 |
| `/accounts` | 会计科目 | 五类科目维护 |
| `/ledgers` | 会计账簿 | 六类账簿查看与导出 |
| `/reports` | 财务报表 | 官方三表 + 科目汇总,导出 Excel |
| `/logs` | 操作日志 | 筛选查询,导出 PDF |
| `/settings` | 企业信息 | 企业资料 + 数据备份/恢复 |

---

## API 一览

统一前缀 `/api`。

```
# 系统
GET    /api/health

# 企业信息
GET    /api/company
PUT    /api/company

# 会计科目
GET    /api/accounts            POST /api/accounts
PUT    /api/accounts/{id}       DELETE /api/accounts/{id}

# 记账凭证
GET    /api/vouchers            GET /api/vouchers/{id}
POST   /api/vouchers            PUT /api/vouchers/{id}     DELETE /api/vouchers/{id}

# 附件
POST   /api/vouchers/{id}/attachments
GET    /api/attachments/{id}/download
GET    /api/attachments/{id}/preview
DELETE /api/attachments/{id}

# 财务报表
GET    /api/reports/trial-balance | /income | /balance-sheet | /summary
GET    /api/reports/official?report_type=month|quarter|year&year=&month=&quarter=
GET    /api/reports/export-excel?report_type=...&year=...

# 会计账簿
GET    /api/ledgers/types
GET    /api/ledgers?ledger_type=&report_type=&year=&month=&quarter=&account_code=
GET    /api/ledgers/export-excel?ledger_type=all|<类型>&report_type=&year=...

# 操作日志
GET    /api/logs?action_type=&year=&month=&quarter=&page=
GET    /api/logs/export-pdf?action_type=&year=&month=&quarter=

# 数据备份
GET    /api/data/export
POST   /api/data/import
```

后端启动后可访问 `http://<host>:8000/docs` 查看交互式 OpenAPI 文档。

---

## 部署

### 云端一行命令部署(推荐)

在全新 Ubuntu 云服务器上,一行命令自动完成「安装 Docker/git → 拉取代码 → 构建启动」:

```bash
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | bash
```

自定义端口 / 安装目录:

```bash
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | HTTP_PORT=80 APP_DIR=/opt/cw bash
```

部署完成后访问 `http://<服务器IP>:<端口>`(默认 8080)。非 root 用户需具备 `sudo`。

### 本地 Docker 部署

```bash
cp .env.example .env        # 按需修改端口/密码
docker compose up -d --build
# 访问 http://localhost:8080
```

或在已克隆的仓库目录执行 `./deploy.sh`(自动生成随机数据库密码的 `.env` 并起栈)。

> 生产建议:前置反向代理(Nginx/Caddy)配置 HTTPS 与域名,并在 `.env` 收紧 `CORS_ORIGINS`。

---

## 升级

在已部署的服务器上,**任意目录**执行一行命令即可升级(自动定位部署目录):

```bash
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/upgrade.sh | bash
```

升级流程:**自动备份当前数据** → 拉取最新代码(已最新则退出)→ 重建重启(**保留数据卷,数据不丢**)→ 健康检查。

自动定位失败时显式指定目录:

```bash
APP_DIR=/opt/cw bash -c "$(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/upgrade.sh)"
```

也可在仓库目录内运行 `./upgrade.sh`。数据库表结构变更在启动时自动建表。

---

## 数据备份与持久化

- **数据库**:Docker 卷 `db_data`
- **附件文件**:Docker 卷 `uploads`(后端容器 `/data/uploads`)
- **应用级备份**:企业信息页「数据备份/恢复」一键导出 zip(含附件),或调用 `GET /api/data/export`
- 升级脚本会在升级前自动导出一份 zip 到 `<部署目录>/backups/`

> 停止服务用 `docker compose down`(**保留数据**);仅 `docker compose down -v` 会清空数据卷。

---

## 本地开发

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

---

## 运维

```bash
docker compose ps                # 查看容器状态
docker compose logs -f backend   # 查看后端日志
docker compose down              # 停止(保留数据卷)
docker compose down -v           # 停止并清空数据(慎用!)
```

---

## 设计约束与已知限制

- **复式平衡**:每张凭证 `Σ借方 = Σ贷方`,前后端强校验
- **实时聚合**:报表/账簿基于凭证分录实时计算,无需月末结转
- **单租户、无登录鉴权**:定位简洁自用,可后续扩展多用户与权限
- **现金流量表**:采用对方科目归类法近似分类,期初/期末/净增加额与账面现金一致(详见 [docs/REPORTS.md](docs/REPORTS.md))
- **数量金额式明细账**:当前分录无「数量/单价」字段,该账簿仅列示金额、数量列留空
- **操作日志范围**:记录数据变更与导入导出/下载等有效行为,不记录纯浏览类 GET

---

## 项目结构

```
CW/
├── backend/                     FastAPI 后端
│   ├── app/
│   │   ├── main.py                  应用入口 + 中间件 + 路由注册
│   │   ├── config.py / database.py  配置与数据库会话
│   │   ├── models.py                ORM 模型
│   │   ├── schemas.py               Pydantic 校验(含借贷平衡)
│   │   ├── seed_accounts.py         81 个科目种子
│   │   ├── reports_cn.py            官方报表计算(会小企01/02/03)
│   │   ├── report_excel.py          报表 Excel 导出
│   │   ├── ledgers.py               六类会计账簿生成
│   │   ├── ledger_excel.py          账簿 Excel 导出
│   │   ├── oplog.py                 操作日志中间件与查询
│   │   ├── oplog_pdf.py             日志 PDF 导出
│   │   └── routers/                 company/accounts/vouchers/attachments/
│   │                                reports/ledgers/logs/data_io
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                    React 前端
│   ├── src/pages/                  Dashboard/VoucherList/VoucherEdit/Accounts/
│   │                               Ledgers/Reports/Logs/Settings
│   ├── src/components/             AttachmentPreview 等
│   ├── nginx.conf                  静态托管 + /api 反代
│   └── Dockerfile
├── docs/                        蓝图、报表说明、官方模板
├── docker-compose.yml
├── install.sh                   云端一键安装
├── deploy.sh                    构建启动
├── upgrade.sh                   一键升级(自动定位+备份)
└── .env.example
```

---

## 许可

内部自用项目。如需商用或二次开发,请自行评估《小企业会计准则》适配性与合规要求。
