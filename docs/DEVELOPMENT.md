# 开发文档 · 小企业财务记账系统

> 本文档面向**开发接力 / 团队移交 / 反向追溯**,全面记录已实现功能、需求来源、架构决策、数据模型、API、开发历程与待办规划。
> 与 [README.md](../README.md)(面向使用者)互补;报表口径见 [REPORTS.md](REPORTS.md);架构蓝图见 [BLUEPRINT.md](BLUEPRINT.md)。
> 最后更新:2026-11-10(v1.0.8 之后:SaaS 租户级备份恢复修复 #38、PR 检查 CI #40)。
> 事项追踪:[Issues](https://github.com/lsgoodlionel/CW/issues)、[里程碑](https://github.com/lsgoodlionel/CW/milestones)、[Project](https://github.com/users/lsgoodlionel/projects/2)、[Wiki](https://github.com/lsgoodlionel/CW/wiki)。

---

## 1. 项目概览

面向小微企业、基于《小企业会计准则》的完整财务记账系统。前后端分离,复式记账,自动生成官方格式报表与全套账簿,支持 Excel/PDF 导出、数据备份恢复、操作日志留痕,以及云服务器一行命令部署与升级。

- 源起数据模型:`小企业会计财务原始记录.xlsx`
- 报表/账簿格式:财务报表导出复制税务报送 `.xls` 模板(会小企01/02/03),账簿对齐手工账模板(`全套会计账簿.et`)
- 二级科目参考:`backend/app/seed_subaccounts.py`(预置二级科目种子)
- 部署形态:`DEPLOY_MODE=private`(私有化单租户,默认)/ `saas`(多租户),同一套代码

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

后端启动 `init_db()`:建表 → 幂等迁移(ALTER 补列、`tenant_id` 回填与按租户唯一约束)→ 默认租户 → 预置科目/二级科目/企业信息/系统角色/审批流程 → 历史数据回填。所有迁移**幂等**,兼容线上老库。

请求链路:`AuthMiddleware`(解析令牌 → 设置租户上下文 → 校验成员与订阅 → 按路径校验权限)→ `OperationLogMiddleware`(记录变更)→ 路由。租户隔离由 `tenant.py` 的 SQLAlchemy 全局事件完成(见 §3)。

### 目录结构(关键)
```
backend/app/
  main.py                              入口:CORS + 鉴权/操作日志中间件 + 异常处理 + 路由注册
  config.py database.py init_db.py     配置 / 会话 / 建表、迁移与种子
  version.py                           版本与「关于系统」信息(单一来源)
  models.py schemas.py schemas_read.py ORM 模型 / 增删改查模式 / 只读与计算类响应模式
  tenant.py tenant_provision.py        多租户隔离(上下文 + 全局过滤/回填 + tenant_get)/ 新租户初始化
  subscription.py                      订阅到期、停用、用户配额判定
  auth_svc.py auth_mw.py               密码哈希、令牌、权限目录 / 鉴权中间件
  seed_accounts.py seed_subaccounts.py 科目与二级科目种子
  subaccounts_svc.py account_excel.py  二级科目编号/自动建/改名同步 / 科目 Excel 导入导出
  reports_cn.py report_excel.py        官方三表计算 / 按 report_templates/*.xls 模板导出
  ledgers.py ledger_excel.py           六类账簿 / Excel 导出
  tax_report.py tax_reconcile.py       企业所得税季报/年报及附表、增值税 / 税务联动审查
  workflow_svc.py approval_doc.py      审批人解析与流程推进 / 费用审批记录单 PDF
  attach_svc.py voucher_attachments.py 附件落盘与元数据 / 凭证附件补齐状态
  oplog.py oplog_pdf.py                操作日志中间件与查询 / PDF 导出
  diag.py                              运行日志采集、出错打包上传
  backup_cli.py openapi_dump.py        命令行导出备份 / 导出 OpenAPI(生成共享契约)
  standalone.py                        原生安装包单进程入口(SQLite + 托管前端)
  routers/  about accounts attachments auth company contracts customers data_io diag
            expense expense_apply ledgers logs personnel platform presets reports tax
            users vouchers workflow
backend/tests/                         自包含测试脚本(内存 SQLite,python -m tests.<模块>)
frontend/src/
  pages/  Dashboard VoucherList VoucherEdit Customers Personnel Accounts Ledgers Reports
          Workflow ApprovalCenter ExpenseApply Expense Contracts Tax Logs Users Settings
          PlatformAdmin Diagnostics About Login Register
  components/  AttachmentEditor AttachmentPreview VoucherLinks VoucherContractLinks
  shared/      models.generated.ts(由 OpenAPI 生成,勿手改)models.ts labels.ts perm.ts amount.ts
  api.ts App.tsx
frontend/public/manual.html            用户与管理员操作手册
shared/contract/                       Web 与小程序共享契约(scripts/gen-contract.mjs、sync-shared.mjs)
packaging/                             原生安装包构建(PyInstaller cw.spec、图标、Windows 版本资源)
.github/workflows/                     ci.yml(PR 检查)· docker-images.yml(GHCR 镜像)· native-build.yml(原生包)
```

## 3. 数据模型(38 张表)

**多租户隔离**:除 `tenants`、`tenant_memberships`、`users` 为全局表外,业务表均继承 `TenantMixin`(带 `tenant_id`)。`tenant.py` 的 `do_orm_execute` 事件对 SELECT/UPDATE/DELETE 自动注入当前租户过滤,`before_flush` 自动回填新对象的 `tenant_id`;按主键取对象用 `tenant_get` 二次校验归属。全局表不受过滤,对它们的批量写操作必须显式限定范围(见 #38 修复)。

| 分组 | 表 | 说明 |
|---|---|---|
| 租户(全局) | `tenants` | 租户:名称/编码/启用/套餐 plan/状态 status/到期 expires_at/用户上限 max_users |
| | `tenant_memberships` | 用户↔租户成员,`is_tenant_admin` 标识租户管理员,`(user_id, tenant_id)` 唯一 |
| 账号与权限 | `users`(全局) | 登录账号:用户名/密码哈希/关联员工/超管标志/启用 |
| | `roles` `role_permissions` `user_roles` | 按租户隔离的角色、权限点(`module:action`)、用户角色 |
| | `auth_presets` | 部门 + 职位 → 系统角色的授权预设 |
| 企业与主数据 | `company_info` | 企业信息(每租户一行)、纳税人身份、大额凭证审批阈值等 |
| | `accounts` `sub_accounts` | 一级科目 / 二级明细科目(编码 = 一级 4 位 + 顺序 2 位),按租户唯一 |
| | `customers` | 往来单位(企业客户/个人客户/供应商/往来单位) |
| | `org_units` `employees` `employee_positions` | 组织架构(自引用多级)/ 员工档案(含离职日期)/ 任职(一人多岗) |
| 凭证 | `vouchers` | 凭证号/日期/摘要/借贷合计/状态(`posted` 已入账才进报表)/往来单位/必需附件类型/审批实例 |
| | `voucher_entries` | 分录:摘要/科目/明细科目/借/贷,允许负数红字 |
| | `voucher_links` | 凭证关联(预收/挂账/核销/应收/冲销/其他) |
| | `attachments` | 附件,可归属凭证/费用申请/费用报销/合同/税务申报之一 |
| 审批与费用 | `workflow_definitions` `workflow_steps` | 流程定义(业务类型/启用)与步骤(审批人类型) |
| | `workflow_instances` `workflow_tasks` | 审批实例(关联单据)与待办任务 |
| | `expense_applications` `expense_application_items` | 费用申请(事前)及明细 |
| | `expense_claims` `expense_items` | 费用报销(事后)及明细,可关联申请、合同与生成的凭证 |
| 合同 | `contracts` `contract_voucher_links` | 合同(收支方向/含税金额/税率/税金)与关联凭证 |
| 税务 | `tax_filings` | 税务申报记录(税种/纳税人类型/所属期/应纳/已缴/状态/审批实例) |
| | `tax_adjustments` `tax_loss_carryovers` `tax_asset_depreciations` `tax_rd_deductions` | 年报附表录入:A105000 / A106000 / A105080 / A107012 |
| | `tax_salary_adjusts` `tax_ad_medias` `tax_preferences` `tax_accel_deprs` | A105050 / A105060 / 税收优惠事项 / 季报 A201020 |
| 审计 | `operation_logs` | 操作日志(类型/行为/摘要/操作人/变更详情 detail/状态码/耗时/IP) |

**核心不变量**:每张凭证 `Σ借方 = Σ贷方`(前后端双重校验,允许红字负数);报表/账簿由已入账凭证的分录实时聚合,不做月末结转。

## 4. 已实现功能模块(附需求来源与关键实现)

### 4.1 记账凭证
- 多行分录、科目下拉、实时借贷平衡、自动凭证号(`记-YYYYMM-NNN`)
- **红字(负数)冲销**:分录允许负数;`POST /vouchers/{id}/reverse` 一键生成金额取负的红字凭证并建立「冲销」关联
- **凭证关联**:人工建立预收/挂账/核销/应收/冲销关系,双向可见
- 凭证列表「关联」列同时展示普通凭证关联数量与关联合同数量,便于从列表直接识别追溯关系
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
- 财务报表 Excel 导出使用 `backend/app/report_templates/month_quarter_report.xls` 与 `annual_report.xls` 作为源模板,按报表类型复制模板并填入纳税人识别号、纳税人名称、所属期和行次金额;导出 `.xls` 仅包含外部报送要求的三张表,科目汇总表保留页面/接口预览。
- 官方模板 1:1 Excel 导出(标题/表号/抬头/行次/列宽/边框/层级缩进)
- **取数口径**:官方三表、科目汇总与账簿均只统计 `posted` 已入账凭证;草稿/审批中凭证不进入财务报表数字。现金流量表取“涉及现金科目”的凭证时同样先过滤 `posted`。
- **税务联动审查**:`tax_reconcile.py` 按期末日期汇总 `2221 应交税费` 明细余额,并与税务申报记录交叉检查;仪表盘默认以一行紧凑提示展示摘要,点击展开后显示提示明细,税务管理页展示明细余额和申报记录联动状态,用于发现一级科目为 0 但明细税种互抵等问题。
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
货币资金(现金/银行/其他)余额、日/月/季/年周期切换、周期收支利润、应收/应付/应交税费、税务联动审查紧凑提示、支出构成、近 6 月趋势。金额类 KPI、近 6 月趋势和“本期凭证”均按 `posted` 已入账凭证统计;运营待办里的“凭证总数”保留业务对象全量口径。

### 4.10 企业信息 + 数据备份
- 企业信息:工商登记/财务设置/人员三组
- **数据备份(当前格式 v22)**:`data_io.py` 一键导出 zip(`data.json` + 附件),兼容 v1–v22 老备份;导入容忍被自动解压后重压缩的嵌套目录。
  - 导出:租户上下文下只导出当前租户及其成员,不带出平台超管;无上下文导出全部。租户含订阅字段(plan/status/expires_at/max_users)。
  - 整站恢复(私有化 / 无租户上下文):整体替换全部数据,含用户、租户与成员,恢复后确保有可登录超管。
  - 租户级恢复(SaaS 租户上下文,`_restore_scope`):只替换本租户业务数据;不清空全局表;同名已有账号沿用、不改密码与超管身份;新账号一律非超管;成员只增不删;当前租户订阅保留;多租户全量备份拒绝(400)。见 #38 与 `tests/test_tenant_restore.py`。

### 4.11 部署与运维
- 安装与升级同一条命令 `install.sh`:未部署则安装(Docker/git → 拉取 → `deploy.sh`),已部署则自动定位目录、保留 `.env`、升级前备份、拉取重建;`FORCE=1` 强制重建;`upgrade.sh` 兼容转调
- `deploy.sh` 优先拉取 GHCR 预构建镜像,失败回退本地构建;数据库变更启动时自动迁移
- `uninstall.sh` 卸载前先备份到仓库外;本地客户端 `install-windows.bat` / `install-mac.command`;原生安装包见 `packaging/`

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
以上为早期核心模块。合同、税务、费用申请/报销、审批、鉴权、用户与角色、平台管理、运行诊断等接口见 [README「API 一览」](../README.md#api-一览)。
交互式文档:后端 `http://<host>:8000/docs`。

## 6. 开发历程(按提交)

| 里程碑 | 内容 |
|---|---|
| 初版 | 记账/附件预览/报表/数据导入导出/一键部署 |
| 部署 | install.sh 云端一键;upgrade.sh 一键升级(自动定位/备份/FORCE);备份嵌套目录兼容 |
| 报表 | 升级会小企01/02/03 官方格式 + Excel;导出复制外部报送系统 `.xls` 模板;行层级缩进;存货含在产品保证平衡 |
| 账簿 | 六类会计账簿 + Excel;多栏式按科目分别成账 |
| 日志 | 全系统操作日志 + PDF;后续升级为**含变更详情**的详细日志 |
| 往来/凭证 | 客户管理→往来单位分类;凭证关联(预收/挂账/核销/应收/冲销) |
| 凭证增强 | 红字冲销;附件类型扩展;仪表盘增强;企业信息补全 |
| 现金流量 | 红字冲销在现金流量表同行正确抵减(按借贷方向归类) |
| 多级科目 | 一级/二级科目管理 + 二级 Excel 导入导出;录入自动建二级;改名同步凭证 |
| 人员 | 组织架构 + 员工档案;一人多岗兼职 |
| 利润表明细 | 「其中」行按二级科目归集(此前恒为0) |
| 备份完整 | 操作日志纳入备份,覆盖当时全部 12 表 |
| 审批/费用/权限 | 审批流程引擎、费用申请与报销、用户与 RBAC、超管(#2–#5,见 §7) |
| v1.0.0 | 关于系统与手册、本地客户端、原生安装包 |
| 合同与税务 | 合同管理;企业所得税季报/年报及附表;增值税(小规模);直录/审批双通道 |
| 多租户 SaaS | 四阶段隔离/选租户/平台管理/订阅;首登设置;运行诊断;账套管理模式三级权限 |
| v1.0.1–v1.0.8 | 凭证必需附件;官方 `.xls` 报表模板;已入账口径;税务联动审查 |
| v1.0.9(进行中) | 手册同步;SaaS 租户级恢复修复(#38);PR 检查 CI(#40) |

完整阶段记录(按提交与 Issue)见 Wiki [开发历程](https://github.com/lsgoodlionel/CW/wiki/开发历程) 与 [版本发布记录](https://github.com/lsgoodlionel/CW/wiki/版本发布记录)。

## 7. 需求 #2–#5(均已实现,对应 Issue #2–#5)

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
- **关联费用申请**:`expense_claims.application_id` 可指向事前申请;报销页可选择已通过的申请自动带出事由/明细;生成凭证时把申请及报销的附件挂到凭证上;并把申请置为 `closed`。
- 备份纳入(v7,员工/部门/科目/流程实例/凭证按 ref 映射)。

### 7.2.1 费用申请(事前审批)✅ 已实现
- 模型:`expense_applications`(单号 SQ-/申请人/部门/申请类型 general·contract·routine/事由/预计金额/状态/流程实例)+ `expense_application_items`(与报销明细同构,便于带出)。
- 附件多归属:`attachments` 的 `voucher_id` 放宽为可空,新增 `expense_application_id`/`expense_claim_id`;共享 `attach_svc` 落盘。申请阶段即可上传合同/发票等,报销生成凭证时同步到凭证附件(同一附件行同时挂 `voucher_id`,无重复文件)。
- 流程:建单(草稿)→ 提交(按 biz_type=`expense_apply` 的启用流程发起)→ 审批 → 通过(approved)→ 被报销关联后置 closed。预置「费用申请审批流程」(部门负责人→管理层)。
- 权限模块 `expense_apply`(路径前缀 `/api/expense-apply` 需排在 `/api/expense` 之前);默认「财务操作」「审批人」角色已含。
- API `/api/expense-apply` CRUD + `/submit` + `/{id}/attachments` + `/active-workflow` + `/approved` + `/meta`;前端「费用申请」页(建单/明细/附件上传/提交/详情+审批轨迹)。
- 备份 **v9**:新增 `expense_applications`(含明细)+ 附件改为**扁平附件表**统一导出(记录 voucher/application/claim 三种归属 ref),导入按 ref 还原多归属;兼容 v1–v8 老备份(旧版凭证内嵌附件仍可读)。
- 备份 **v22**:凭证新增 `required_attachment_kinds`(必需附件类型),导出/恢复保留附件补齐状态。
- 凭证附件补齐状态按“本凭证附件 + 双向关联凭证附件 + 关联合同附件”合并计算,不复制关联对象附件到当前凭证。
- 凭证状态:`posted` 保持为“已入账/进入账簿与报表”的系统状态;前端显示为“已入账”。草稿或审批中凭证不进入报表。
- 仪表盘运营待办新增“缺附件凭证”,复用同一套合并附件口径统计仍缺必需附件的凭证数量。

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
- 早期设计的「子管理员」已由账套管理模式取代(#30):**超级管理员**(全局,只在首登设置与「平台管理 → 超级管理员」维护,至少保留一个)/ **租户管理员**(`tenant_memberships.is_tenant_admin`,本账套全权)/ **普通用户**(按 RBAC)。「用户与权限」页不再出现超管设置。
- 角色×权限矩阵 + 用户×角色 分配即「单一/批量权限管理」。
- **授权预设(按部门+职位)**:`auth_presets`(部门×员工职位角色 → 系统角色)。用户关联员工后可「按部门角色预设填充」角色,或「批量应用」把所有关联员工的用户角色按预设覆盖。API `/api/auth-presets`(CRUD + `/resolve` + `/apply`);备份纳入。

## 8. 关键设计决策与已知限制

- **私有化单租户 / SaaS 多租户**由 `DEPLOY_MODE` 切换;全站强制登录(7.3),登录后 30 分钟无操作自动退出;报表实时聚合、不结转。
- **全局表**(`tenants`/`tenant_memberships`/`users`)不受租户过滤:在租户上下文中对它们做批量写操作,必须显式限定范围。
- **订阅续费**未接入支付网关(#43),由平台超管在后台延长到期日。
- **现金流量表**为对方科目归类法近似,期初/期末/净额与账面现金一致(见 REPORTS.md)。
- **利润表「其中」行**依赖明细科目命名匹配关键字;记账需把税费等记在对应一级科目下。
- **数量金额式明细账**无数量/单价字段,仅列金额(#44)。
- **迁移策略**:`init_db._ADDED_COLUMNS` 幂等 ALTER 补列 + 新表 create_all + 历史回填;禁止破坏性 `docker compose down -v`(会清库)。
- 金额用 `NUMERIC(18,2)`;持股比例 `NUMERIC(7,4)`。

## 9. 本地/测试约定

- 后端测试:`backend/tests/test_*.py` 为自包含脚本(内存 SQLite),在 `backend/` 下逐个 `python -m tests.<模块>` 运行;Python 3.12 + 锁定依赖,不触碰生产 Postgres。
- 前端:`npm run build` 做类型检查。
- CI:`ci.yml` 在每个 PR 与推送 main 时运行全部后端测试、前端构建与镜像构建(不推送)。
- 每次变更后:重建镜像 → 起栈 → 对运行实例冒烟 → 清理测试数据 → 提交推送。
- 数据安全红线:任何"重置/清空"前先确认是否真实数据,严禁对装有真实数据的实例执行 `down -v`。

## 10. 部署 / 升级 / 备份速查

```bash
# 云端安装
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | bash
# 一键升级(与安装同一条命令;自动定位目录、保留 .env、升级前备份、迁移)
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | bash
# 强制重建
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | FORCE=1 bash
# 前置 Nginx 的服务器建议 .env 写回环绑定,避免 Docker 直接暴露公网端口
HTTP_PORT=127.0.0.1:18080
# 本地
docker compose up -d --build     # http://localhost:8080
```
数据卷:`db_data`(库)、`uploads`(附件)。应用级备份:企业信息页导出/导入 zip,或 `GET /api/data/export`。

升级已有部署时,`install.sh`/`upgrade.sh` 保留部署目录现有 `.env` 中的 `HTTP_PORT`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` 等关键值;要改端口、数据库凭据或 SaaS 参数,先编辑 `.env`,再运行升级。远程管道执行且 `sudo` 需要密码时使用 `ssh -t` 或先登录交互终端。若本地构建拉 Docker Hub 基础镜像遇到 IPv6 reset,优先改用 GHCR 预构建镜像;必须本地构建时在服务器网络层配置临时 IPv4 优先策略,不要把单台服务器的 `/etc/hosts` workaround 写入通用脚本。
