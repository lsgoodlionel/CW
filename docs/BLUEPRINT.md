# 简洁版小企业财务记账系统 — 蓝图与开发计划

> 数据来源:`小企业会计财务原始记录.xlsx`(小企业会计准则)。
> 目标:前后端分离的简洁记账 Web 站点,支持记账、凭证附件关联、财务报表汇总,Docker 本地验证 + Ubuntu 一键部署。

## 1. 业务模型(源自 Excel)

| Excel 表 | 含义 | 系统映射 |
|---|---|---|
| 企业基本信息 | 公司名/负责人/会计/审核/录入 | `company_info` 单例 |
| 凭证输入(AE 列) | 81 个标准会计科目 | `accounts` 科目表(预置种子) |
| N 月份凭证输入 | 记账凭证(摘要/科目/借贷/附单据) | `vouchers` + `voucher_entries` |
| 附单据 | 发票/回单等原始凭证 | `attachments`(关联凭证) |
| 科目汇总表 | 试算平衡 | 报表 API(实时聚合) |
| 资产负债表(会企01) | 期末余额 | 报表 API |
| 利润表(会企02) | 收入-成本费用 | 报表 API |

### 会计科目五大类
- **资产类**(1xxx):库存现金、银行存款、应收账款、固定资产……
- **负债类**(2xxx):短期借款、应付账款、应交税费……
- **权益类**(4xxx):实收资本、本年利润、利润分配……
- **成本类**(5xxx):生产成本、制造费用……
- **损益类**(6xxx):主营业务收入、主营业务成本、管理费用……

科目带**记账方向**(借/贷),用于报表余额计算。

## 2. 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 后端 | FastAPI + SQLAlchemy 2.0 + Pydantic v2 | 类型安全、自带 OpenAPI 文档、开发快 |
| 数据库 | PostgreSQL 16 | 事务可靠、金额用 `NUMERIC` 精确、生产合理 |
| 前端 | React 18 + Vite + TS + Ant Design 5 | 财务表格/表单生态成熟 |
| 文件存储 | 本地卷 `/data/uploads` | 简洁,元数据入库 |
| 部署 | docker-compose + Nginx | 一键起栈,前端静态托管 + API 反代 |

## 3. 数据库设计

```
company_info (单例)
  id, name, legal_person, accountant, auditor, bookkeeper, recorder

accounts  会计科目
  id, code(UNIQUE), name, category(asset/liability/equity/cost/profit),
  direction(debit/credit), is_active

vouchers  记账凭证
  id, voucher_no, voucher_date, note,
  total_debit, total_credit(借贷必相等), status(draft/posted),
  created_at, updated_at

voucher_entries  凭证分录(明细行)
  id, voucher_id(FK→vouchers, CASCADE), line_no,
  summary(摘要), account_id(FK→accounts), sub_account(明细科目),
  debit, credit   -- 一行只填借或贷

attachments  附件(发票/回单)
  id, voucher_id(FK→vouchers, CASCADE), kind(invoice/receipt/other),
  original_name, stored_path, mime_type, size_bytes, uploaded_at
```

**核心不变量**:每张凭证 `Σ借方 = Σ贷方`(复式记账平衡),保存时强校验。

## 4. API 设计(REST)

```
GET    /api/health
GET    /api/company            读取企业信息
PUT    /api/company            更新企业信息

GET    /api/accounts           科目列表(?category= 过滤)
POST   /api/accounts           新增科目
PUT    /api/accounts/{id}      编辑
DELETE /api/accounts/{id}      停用

GET    /api/vouchers           凭证列表(?start=&end=&keyword= 分页)
GET    /api/vouchers/{id}      凭证详情(含分录+附件)
POST   /api/vouchers           新建凭证(借贷平衡校验)
PUT    /api/vouchers/{id}      编辑
DELETE /api/vouchers/{id}      删除

POST   /api/vouchers/{id}/attachments   上传附件
GET    /api/attachments/{id}/download   下载(强制 attachment)
GET    /api/attachments/{id}/preview    在线预览(inline,图片/PDF/文本)
DELETE /api/attachments/{id}            删除附件

GET    /api/data/export                整站数据导出为 zip 备份
POST   /api/data/import                从 zip 备份恢复(整体替换)

GET    /api/reports/trial-balance?start=&end=   科目汇总表(试算平衡)
GET    /api/reports/income?start=&end=          利润表
GET    /api/reports/balance-sheet?as_of=        资产负债表
GET    /api/reports/summary?start=&end=         首页概览(收入/支出/利润/凭证数)
```

统一响应信封:`{ success, data, error }`。

## 5. 前端页面

| 路由 | 页面 | 功能 |
|---|---|---|
| `/` | 仪表盘 | 概览卡片 + 月度收支趋势 |
| `/vouchers` | 凭证列表 | 检索、分页、新建、删除 |
| `/vouchers/new`、`/vouchers/:id` | 凭证编辑 | 多行分录、实时借贷平衡、附件上传 |
| `/accounts` | 科目管理 | 五大类科目维护 |
| `/reports` | 报表 | 科目汇总表 / 利润表 / 资产负债表(可选月份) |
| `/settings` | 企业信息 | 编辑公司信息 |

## 6. 部署

- `docker-compose.yml`:`db`(postgres)+ `backend`(uvicorn)+ `frontend`(nginx 静态 + `/api` 反代)
- `deploy.sh`:Ubuntu 一键 —— 检查 docker → 写 `.env` → `docker compose up -d --build` → 健康检查
- 本地验证:`docker compose up --build` 后访问 `http://localhost:8080`

## 7. 开发阶段(按序)

1. **后端骨架**:项目结构、DB 连接、模型、科目种子(81 个)
2. **凭证 + 附件 API**:CRUD + 借贷平衡 + 文件上传
3. **报表 API**:试算平衡、利润表、资产负债表
4. **前端**:布局 + 凭证录入 + 科目 + 报表 + 仪表盘
5. **容器化**:Dockerfile ×2 + compose + nginx + deploy.sh
6. **本地 Docker 验证**:起栈、冒烟测试关键流程

## 8. 范围约束(YAGNI)
- 单租户、无登录鉴权(简洁版;预留扩展)
- 不做自动结转/月末结账,报表实时聚合
- 附件仅本地存储,不接对象存储
