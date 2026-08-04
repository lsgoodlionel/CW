# 开发文档 · 小企业财务记账系统

> 本文档面向**开发接力 / 团队移交 / 反向追溯**,全面记录已实现功能、需求来源、架构决策、数据模型、API、开发历程与待办规划。
> 与 [README.md](../README.md)(面向使用者)互补;报表口径见 [REPORTS.md](REPORTS.md);架构蓝图见 [BLUEPRINT.md](BLUEPRINT.md)。
> 最后更新:随「详细操作日志 + 备份完整性 + 本开发文档」一并提交。

---

## 1. 项目概览

面向小微企业、基于《小企业会计准则》的完整财务记账系统。前后端分离,复式记账,自动生成官方格式报表与全套账簿,支持 Excel/PDF 导出、数据备份恢复、操作日志留痕,以及云服务器一行命令部署与升级。

- 源起数据模型:`小企业会计财务原始记录.xlsx`
- 报表/账簿格式:对齐税务报送模板(会小企01/02/03)与手工账模板(`全套会计账簿.et`)
- 二级科目参考:`docs/二级科目明细表.md`

## 2. 技术栈与架构

| 层 | 技术 |
|---|---|
| 后端 | FastAPI · SQLAlchemy 2.0 · Pydantic v2 · PostgreSQL 16(本地可 SQLite) |
| 导出 | openpyxl(Excel)· reportlab(PDF,内置中文 CID 字体) |
| 前端 | React 18 · Vite · TypeScript · Ant Design 5 · Recharts |
| 部署 | Docker Compose · Nginx(静态托管 + `/api` 反代) |

```
浏览器 ─▶ Nginx(frontend 容器) ─▶ /api ─▶ FastAPI(backend 容器) ─▶ PostgreSQL(db 容器)
                 │                                   │
           静态前端资源                        附件卷 /data/uploads
```

后端启动 `init_db()`:建表 → 幂等迁移(ALTER 补列)→ 预置科目/二级科目/企业信息 → 历史数据回填。所有迁移**幂等**,兼容线上老库。

### 目录结构(关键)
```
backend/app/
  main.py            入口:CORS + 操作日志中间件 + 路由注册
  config.py database.py init_db.py     配置/会话/初始化与迁移
  models.py schemas.py                 ORM 模型 / Pydantic 模式
  seed_accounts.py seed_subaccounts.py 科目与二级科目种子
  subaccounts_svc.py                   二级科目编号/自动建/改名同步
  reports_cn.py report_excel.py        官方三表计算 / Excel 导出
  ledgers.py ledger_excel.py           六类账簿 / Excel 导出
  account_excel.py                     科目导入模板/导入/导出
  oplog.py oplog_pdf.py                操作日志中间件+查询 / PDF
  routers/  company accounts vouchers attachments reports
            ledgers logs data_io customers personnel
frontend/src/
  pages/  Dashboard VoucherList VoucherEdit Accounts Customers
          Personnel Ledgers Reports Logs Settings
  components/  AttachmentPreview VoucherLinks
  api.ts App.tsx
```

## 3. 数据模型(12 张表)

| 表 | 说明 |
|---|---|
| `company_info` | 企业信息单例(名称/税号/地址/开户行/准则/本位币/人员等) |
| `accounts` | 一级会计科目(编码/名称/类别/方向/启用) |
| `sub_accounts` | 二级明细科目(隶属一级,编码=一级4位+顺序2位) |
| `customers` | 往来单位(party_type:企业客户/个人客户/供应商/往来单位) |
| `vouchers` | 记账凭证(凭证号/日期/摘要/借贷合计/状态/客户) |
| `voucher_entries` | 凭证分录(摘要/科目/明细科目+二级id/借/贷,允许负数红字) |
| `voucher_links` | 凭证关联(预收/挂账/核销/应收/冲销/其他) |
| `attachments` | 附件(发票/银行回单/合同/完税证明/其他) |
| `org_units` | 组织架构单元(自引用多级) |
| `employees` | 员工档案(个人信息/持股比例/状态) |
| `employee_positions` | 员工任职(部门+角色+职位,支持一人多岗) |
| `operation_logs` | 操作日志(类型/行为/摘要/**detail 变更详情**/状态码/耗时/IP) |

**核心不变量**:每张凭证 `Σ借方 = Σ贷方`(前后端双重校验,允许红字负数);报表/账簿由分录实时聚合,不做月末结转。

## 4. 已实现功能模块(附需求来源与关键实现)

### 4.1 记账凭证
- 多行分录、科目下拉、实时借贷平衡、自动凭证号(`记-YYYYMM-NNN`)
- **红字(负数)冲销**:分录允许负数;`POST /vouchers/{id}/reverse` 一键生成金额取负的红字凭证并建立「冲销」关联
- **凭证关联**:人工建立预收/挂账/核销/应收/冲销关系,双向可见
- **关联往来单位**;二级明细科目录入(选一级显示对应二级,可输入自动建)

### 4.2 附件
- 类型:发票/银行回单/合同/完税证明/其他,已上传可改类型(`PATCH`)
- 在线预览(图片/PDF/文本 inline)、下载;随凭证级联、随备份导出

### 4.3 会计科目(多级)
- 81 个准则一级科目 + 参考模板预置二级科目
- 二级科目 CRUD、Excel 批量导入(带模板+一级参照页)、整表导出
- **一人多岗式复用**:录入不存在的二级自动新建(编号延续);二级改名同步所有引用凭证明细
- 编号规则 4+2(见 `subaccounts_svc.py`)

### 4.4 财务报表(会小企01/02/03)
- 资产负债表 / 利润表 / 现金流量表 / 科目汇总表,月/季/年切换
- 官方模板 1:1 Excel 导出(标题/表号/抬头/行次/列宽/边框/层级缩进)
- **利润表「其中」明细行**按二级科目名称关键字归集(印花税/税收滞纳金/广告费/利息费用/政府补助等);一级取账户合计进计算,二级仅披露,**不重复计入**
- **现金流量表**:对方科目归类法,按借贷方向归类使红字冲销同行抵减;期初/期末/净额取账面现金
- 资产负债表「存货」含在产品(生产成本等),保证 资产=负债+权益 恒等

### 4.5 会计账簿(六类)
总分类账 / 三栏式明细账 / 多栏式明细账 / 数量金额式明细账 / 现金日记账 / 银行存款日记账;按种类+年月季导出 Excel(单类或全套六 sheet)。多栏式按科目分别成账(避免季/年只显示单一科目)。

### 4.6 往来单位
企业客户/个人客户/供应商/往来单位(银行/平台/租赁对象等)分类维护、往来业务历史、与凭证联动。

### 4.7 人员管理
- 灵活多级组织架构(树)
- 员工档案 + **一人多岗兼职**(`employee_positions`:员工×部门×角色×职位)
- 部门可「选已有员工添加兼职」或新建员工;按部门/角色筛选走任职表

### 4.8 操作日志(详细)
- 中间件记录全系统数据变更与导入导出/下载行为
- **detail 变更详情**:创建记「提交内容」,更新记逐字段「改前/改后」差异,删除记「删除前」快照(脱敏 password/token,截断 4000 字)
- 按类型+年月季查询,展开查看详情,导出 PDF(内置中文字体)

### 4.9 仪表盘
货币资金(现金/银行/其他)余额、日/月/季/年周期切换、周期收支利润、应收/应付/应交税费、支出构成、近 6 月趋势。

### 4.10 企业信息 + 数据备份
- 企业信息:工商登记/财务设置/人员三组
- **数据备份 v5**:整站数据一键导出 zip(含附件),导入整体恢复;覆盖全部 12 张表(company/accounts/sub_accounts/customers/vouchers+entries+attachments/voucher_links/org_units/employees+positions/**operation_logs**)。兼容 v1–v5 老备份;导入容忍被自动解压后重压缩的嵌套目录。

### 4.11 部署与运维
- 云端一行安装 `install.sh`(装 Docker/git → 克隆 → deploy)
- 一键升级 `upgrade.sh`(自动定位部署目录 + 升级前自动备份 + 拉取重建;`FORCE=1` 强制重建)
- `deploy.sh` 构建启动;数据库变更启动时自动迁移

## 5. API 清单(前缀 `/api`)

```
company    GET/PUT /company
accounts   GET /accounts | /tree ; POST/PUT/DELETE /accounts[/{id}]
           GET/POST /accounts/{id}/subaccounts ; PUT/DELETE /accounts/subaccounts/{sid}
           GET /accounts/export-excel | /subaccounts/template ; POST /subaccounts/import
vouchers   CRUD /vouchers ; POST /{id}/reverse ; POST /{id}/links ; DELETE /links/{id}
attachments POST /vouchers/{id}/attachments ; GET /attachments/{id}/download|preview ; PATCH/DELETE /attachments/{id}
reports    /trial-balance /income /balance-sheet /summary /dashboard
           /official?report_type=&year=&month=&quarter= ; /export-excel
ledgers    /types ; /ledgers?... ; /export-excel
logs       /logs?action_type=&year=&month=&quarter= ; /export-pdf
data       /data/export ; POST /data/import
customers  CRUD /customers?party_type= ; GET /{id}/vouchers
personnel  CRUD /personnel/org-units ; CRUD /personnel/employees ; POST /org-units/{id}/members ; GET /meta
```
交互式文档:后端 `http://<host>:8000/docs`。

## 6. 开发历程(按提交)

| 里程碑 | 内容 |
|---|---|
| 初版 | 记账/附件预览/报表/数据导入导出/一键部署 |
| 部署 | install.sh 云端一键;upgrade.sh 一键升级(自动定位/备份/FORCE);备份嵌套目录兼容 |
| 报表 | 升级会小企01/02/03 官方格式 + Excel;行层级缩进;存货含在产品保证平衡 |
| 账簿 | 六类会计账簿 + Excel;多栏式按科目分别成账 |
| 日志 | 全系统操作日志 + PDF;后续升级为**含变更详情**的详细日志 |
| 往来/凭证 | 客户管理→往来单位分类;凭证关联(预收/挂账/核销/应收/冲销) |
| 凭证增强 | 红字冲销;附件类型扩展;仪表盘增强;企业信息补全 |
| 现金流量 | 红字冲销在现金流量表同行正确抵减(按借贷方向归类) |
| 多级科目 | 一级/二级科目管理 + 二级 Excel 导入导出;录入自动建二级;改名同步凭证 |
| 人员 | 组织架构 + 员工档案;一人多岗兼职 |
| 利润表明细 | 「其中」行按二级科目归集(此前恒为0) |
| 备份完整 | 操作日志纳入备份,覆盖全部 12 表 |

## 7. 需求 #2–#5(#2 已实现,#3–#5 待开发)

> 已确认的架构决策:**#4/#5 采用全站强制登录**;开发顺序 **2→3→4→5**。

### 7.1 流程/审批设计模块 ✅ 已实现
- 专有页面「审批流程」:流程设计(可视化步骤编排)+ 审批中心(发起/我的待办/审批轨迹)。
- 模型:`workflow_definitions`(名称/业务类型/启用)、`workflow_steps`(顺序/审批人类型:指定员工/按角色/部门负责人/任一管理层)、`workflow_instances`(实例:关联单据 biz_type+biz_id/当前步/状态)、`workflow_tasks`(待办:步骤×审批人/结果/意见/时间)。
- 服务 `workflow_svc.py`:审批人解析、发起生成首个待办、审批推进(通过进下一步/末步结束;驳回整单驳回)。
- API `/api/workflow/*`:definitions CRUD、instances 发起/查询、my-tasks 待办、tasks/{id}/approve|reject、meta。
- 审批人可指向**员工/角色/部门负责人**,为 #4 登录后「按登录用户绑定的员工识别待办」预留衔接。
- 备份已纳入(v6,员工按 ref 映射)。
- **待 #4 上线后**:审批中心的「当前审批人身份」由手动选择改为登录用户自动识别。

### 7.2 费用报销申请单 ✅ 已实现
- 模型:`expense_claims`(单号/申请人/部门/事由/合计/状态/流程实例/凭证)+ `expense_items`(费用类别/费用科目 account_id/明细科目/金额/备注)。
- 流程:建单(草稿)→ 提交(按 biz_type=expense 的启用流程发起审批实例)→ 审批(在「审批流程·审批中心」处理)→ 通过后「生成凭证」(借 各费用科目/贷 银行存款,复用二级科目自动建)→ 已生成凭证(paid)。
- 状态与流程实例同步(读时 `_sync_status`)。
- API `/api/expense/claims` CRUD + `/submit` + `/make-voucher`;前端「费用报销」页(建单/明细/提交/详情+审批轨迹/生成凭证)。
- 备份纳入(v7,员工/部门/科目/流程实例/凭证按 ref 映射)。

### 7.3 用户模块 + RBAC 权限 ✅ 已实现(全站强制登录)
- 模型:`users`(用户名/密码哈希/关联员工/超管标志/启用)、`roles`、`role_permissions`(perm='module:action')、`user_roles`。
- 鉴权:`auth_svc`(PBKDF2 密码哈希 + HMAC 签名令牌,均标准库)、`auth_mw.AuthMiddleware`(全站强制登录 + 按路径 `classify_perm` 权限校验,超管放行)。
- 权限目录:模块(凭证/科目/往来/人员/流程/报销/报表/账簿/企业/数据/日志/用户)× 动作(查看/新建/编辑/删除/审批);角色勾选授权。
- API:`/api/auth/login|me|change-password|permission-catalog`;`/api/users`(CRUD+重置密码+分配角色)、`/api/roles`(CRUD+权限)。
- 前端:登录页、令牌注入与 401 跳转、路由守卫、按权限过滤菜单、Header 改密/退出、「用户与权限」管理页(用户/角色两页,权限矩阵勾选)。
- 配置:`REQUIRE_AUTH`(默认 true)、`AUTH_SECRET`(生产必改)、`ADMIN_PASSWORD`(初始超管密码,默认 admin123)。
- 操作日志新增 `operator`(操作人);备份 v8 含用户/角色(密码哈希一并备份)。

### 7.4 超级管理员 ✅ 已实现
- 内置超管 `admin`(首次启动创建),拥有全部权限(`permissions=['*']`,中间件直接放行)。
- 可创建**子管理员**:给用户勾选 `user` 模块权限或授予超管标志(仅超管可授予/取消超管;至少保留一个超管;内置 admin 不可删除)。
- 角色×权限矩阵 + 用户×角色 分配即「单一/批量权限管理」。

## 8. 关键设计决策与已知限制

- **单租户、当前无登录**(引入见 7.3);报表实时聚合、不结转。
- **现金流量表**为对方科目归类法近似,期初/期末/净额与账面现金一致(见 REPORTS.md)。
- **利润表「其中」行**依赖明细科目命名匹配关键字;记账需把税费等记在对应一级科目下。
- **数量金额式明细账**无数量/单价字段,仅列金额。
- **迁移策略**:`init_db._ADDED_COLUMNS` 幂等 ALTER 补列 + 新表 create_all + 历史回填;禁止破坏性 `docker compose down -v`(会清库)。
- 金额用 `NUMERIC(18,2)`;持股比例 `NUMERIC(7,4)`。

## 9. 本地/测试约定

- 后端逻辑测试:容器内 Python 3.12 + 临时 SQLite(`docker run ... -e DATABASE_URL=sqlite:///...`),不触碰生产 Postgres。
- 前端:`npm run build` 做类型检查。
- 每次变更后:重建镜像 → 起栈 → 对运行实例冒烟 → 清理测试数据 → 提交推送。
- 数据安全红线:任何"重置/清空"前先确认是否真实数据,严禁对装有真实数据的实例执行 `down -v`。

## 10. 部署 / 升级 / 备份速查

```bash
# 云端安装
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | bash
# 一键升级(自动备份+迁移)
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/upgrade.sh | bash
# 强制重建
curl -fsSL .../upgrade.sh | FORCE=1 bash
# 本地
docker compose up -d --build     # http://localhost:8080
```
数据卷:`db_data`(库)、`uploads`(附件)。应用级备份:企业信息页导出/导入 zip,或 `GET /api/data/export`。
