# 小企业财务记账系统

一套面向小微企业、基于《小企业会计准则》的完整财务记账 Web 系统。前后端分离,复式记账,自动生成官方格式财务报表与全套会计账簿,内置审批流程、费用申请/报销、合同与税务管理、RBAC 权限、数据备份恢复与操作日志留痕,支持一键 Excel/PDF 导出,以及 Ubuntu 云服务器一行命令部署与升级。

**两种部署形态,同一套代码**(由 `DEPLOY_MODE` 切换):

- **私有化(`private`,默认)**:单企业单机版,行为与传统单租户一致,隐藏租户/平台管理。
- **多租户 SaaS(`saas`)**:登录选租户、按租户行级隔离、平台管理后台(开通/停用租户、成员、套餐与到期)、访客自助注册与试用、首登页面设置超级管理员。

另内置**运行诊断**:采集运行日志,出错自动打包上传到共享 GitHub 仓库,便于远程排查。

> 数据模型源自《小企业会计财务原始记录.xlsx》;报表/账簿格式对齐税务报送与手工账官方模板。
> 设计蓝图见 [docs/BLUEPRINT.md](docs/BLUEPRINT.md),报表口径见 [docs/REPORTS.md](docs/REPORTS.md)。
> **开发接力 / 团队移交请看 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)**(全量功能、数据模型、API、开发历程与待办规划)。
> **微信小程序版**在独立仓库 [lsgoodlionel/CW-WX](https://github.com/lsgoodlionel/CW-WX),与本仓库共用同一后端;
> 两端共享契约与升级同步规则见 [docs/SHARED-CONTRACT.md](docs/SHARED-CONTRACT.md)。

---

## 目录

- [核心特性](#核心特性)
- [功能详解](#功能详解)
- [多租户 SaaS 与平台管理](#多租户-saas-与平台管理)
- [权限与角色](#权限与角色)
- [运行诊断(日志采集与上传)](#运行诊断日志采集与上传)
- [登录与部署模式](#登录与部署模式)
- [技术栈与架构](#技术栈与架构)
- [数据模型](#数据模型)
- [页面与路由](#页面与路由)
- [API 一览](#api-一览)
- [环境变量](#环境变量)
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
| 记账凭证 | 多行分录、科目下拉、实时借贷平衡校验、自动凭证号、**红字(负数)冲销**、关联客户、凭证间关联(预收/挂账/核销/应收/冲销) |
| 往来单位 | 企业客户/个人客户/供应商/往来单位(银行、平台、租赁等)分类维护、往来业务历史、与凭证联动 |
| 人员管理 | 灵活多级组织架构 + 员工档案(股东/管理层/普通员工);**支持一人多岗**(跨多部门兼任不同角色),部门可选已有人员添加兼职 |
| 附件管理 | 发票/银行回单/合同/完税证明/其他上传、类型可修改、在线预览(图片/PDF/文本)、下载 |
| 仪表盘 | 货币资金(现金/银行)余额、日/月/季/年周期切换、收支利润、往来款、支出构成、趋势图 |
| 会计科目 | 一级/二级多级管理(展开折叠、增改停用)、二级改名同步凭证、录入时自动新建二级(编号延续)、Excel 导入(带模板)/整表导出 |
| 财务报表 | 资产负债表/利润表/现金流量表(官方会小企格式)+ 科目汇总表,月/季/年切换,一键导出 Excel |
| 会计账簿 | 六类账簿(总账、明细账、日记账等)按凭证自动生成,按种类+年月季导出 Excel |
| 审批流程 | 可视化设计审批流程(多步骤、审批人=员工/角色/部门负责人)、发起审批、我的待办、审批轨迹;作为报销等单据的通用引擎 |
| 费用申请 | **事前审批**:申请单(合同/常规费用/一般申请)+预计明细+**附件上传(合同/发票等)**,走事前审批流程;通过后可据此发起报销 |
| 费用报销 | **事后管理**:报销申请单+费用明细,可**关联事前费用申请**(自动带出事由与明细),提交走审批流程,通过后一键生成记账凭证(借费用/贷银行);**申请附件自动同步到生成的凭证附件** |
| 合同管理 | 录入与管理合同(销售/采购/服务/租赁等)、上传合同附件、**关联记账凭证**(一份合同对应多张分期收付款凭证) |
| 税务管理 | 记录各税种申报结果(**国税/自然人**,印花税·增值税及附加·企业所得税·个人所得税等);**企业所得税月(季)度预缴申报表(A类 A200000)** 按账套自动计算并导出 Excel |
| 用户与权限 | **全站强制登录** + RBAC(角色×权限矩阵、查看/新建/编辑/删除/审批)、**按部门+职位授权预设**(一键填充/批量应用)、超级管理员与子管理员、修改密码 |
| 操作日志 | 全系统行为留痕(含**修改前后差异详情**),按类型+年月季查询、展开看详情、一键导出 PDF |
| 数据备份 | 整站数据(含附件、租户与成员)一键导出 zip / 导入恢复;SaaS 下按当前租户作用域导出 |
| 多租户 SaaS | `DEPLOY_MODE` 切换私有化/多租户;共享库 + `tenant_id` 行级隔离(SQLAlchemy 全局自动过滤,含 SELECT/UPDATE/DELETE);登录选租户、令牌携带并校验租户、科目/角色按租户唯一 |
| 平台管理 | 平台超管跨租户开通/停用/改名租户、管理成员与租户管理员、按租户初始化科目/角色/流程;首登页面设置超管(无默认账号) |
| 订阅 / 计费 | 租户套餐、状态(试用/正式/到期/停用)、到期日与用户数上限;到期/超额登录与写操作拦截;访客自助注册进入试用(真实支付网关留作对接点) |
| 运行诊断 | 采集运行日志;未捕获异常/500 自动打包(traceback+近期日志+元信息)上传共享 GitHub 仓库,节流去重;超管可查看/手动上传 |
| 部署运维 | Docker 一键部署、云端一行命令安装、一行命令自动升级(升级前自动备份);后端优先拉取 GHCR 预构建镜像(免服务器 pip 构建) |

---

## 功能详解

### 1. 记账凭证
- 一张凭证含多条分录(摘要、会计科目、明细科目、借方、贷方)
- **强制复式平衡**:保存时校验 `Σ借方 = Σ贷方`,前后端双重校验
- 凭证号可留空自动生成(`记-YYYYMM-NNN`)
- 按日期区间、凭证号/摘要关键字检索,分页列表

### 2. 附件(原始单据)
- 每张凭证可上传多个附件,分类为**发票 / 银行回单 / 合同 / 完税证明 / 其他**;已上传附件的类型可随时修改
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
- 一键导出整站数据(企业信息、科目、凭证分录、附件文件,以及租户与成员关系)为单个 zip
- 一键导入 zip 快照整体恢复;兼容被系统自动解压后再压缩的嵌套目录结构
- SaaS 下在租户上下文中按当前租户作用域导出;恢复兼容旧版本备份(自动补齐默认租户/成员)

### 8. 客户管理与凭证关联
- 客户:名称、简称、税号、开票地址/电话、开户行/账号、联系人;往来业务历史(关联凭证 + 借方合计)
- 凭证可关联客户;凭证间可人工建立**预收款/挂账/核销/应收款/冲销**关系,双向显示相关凭证

### 9. 红字冲销
- 分录允许负数金额;一键「红字冲销」按原凭证生成金额取负的红字凭证,并自动建立「冲销」关联

### 10. 仪表盘与企业信息
- 仪表盘:货币资金(现金/银行/其他)期末余额、**日/月/季/年**周期切换、周期收支与净利润、应收/应付/应交税费、支出构成、近 6 月趋势
- 企业信息:名称、税号、注册地址、电话、开户行/账号、成立日期、所属行业、会计准则、记账本位币、启用期间、法人及会计/审核/记账/录入人员

---

## 多租户 SaaS 与平台管理

由 `DEPLOY_MODE` 决定形态,**同一套代码**:

- **私有化(`private`,默认)**:只有默认租户(`id=1`),租户过滤对结果无影响,行为与单机版一致;不显示租户/平台管理入口。
- **多租户(`saas`)**:
  - **行级隔离**:业务模型统一挂载 `tenant_id`,SQLAlchemy 全局事件对 **SELECT/UPDATE/DELETE** 自动注入租户过滤;`db.get()` 主键取对象经 `tenant_get` 二次校验归属,防跨租户越权。科目编码、角色名按 `(tenant_id, …)` 复合唯一。
  - **登录选租户**:令牌携带并校验选定租户;用户属多个租户时登录返回可选列表供选择;非本租户成员/到期租户被拒。
  - **平台管理**(仅平台超管,`/platform`):开通/停用/改名租户、管理成员与租户管理员、编辑套餐/状态/到期/用户上限、对租户「重新初始化」补齐基础数据。新建租户自动按租户预置科目/二级科目/系统角色/审批流程/企业信息。
  - **订阅/计费**:租户 `status`(试用/正式/到期/停用)、`expires_at`、`max_users`;到期或超额时登录与写操作被拦截并提示;支付网关未集成,续费由平台超管在后台管理。
  - **自助注册**(`ALLOW_SELF_REGISTRATION=true`):访客可自助开通租户进入试用(`TRIAL_DAYS` 天)。
  - **首登设置**:无预置管理员时,首次访问页面引导创建平台超级管理员(设置后入口失效,防接管)。

## 权限与角色

参考「账套管理模式」(账套 = 租户),**只有两个层级 + 普通用户**,各一个名字、各归其位、互不越界(统一命名,不再有"平台管理员/平台超管"等重复叫法):

| 维度 | 超级管理员 | 租户管理员 | 普通用户 |
|---|:---:|:---:|:---:|
| 定位 | 平台级最高权限 | 本账套内的管理员 | 按授权操作 |
| 开通/停用账套、套餐与到期 | ✅ | ❌ | ❌ |
| 跨账套访问、平台运维、管理其它超管 | ✅ | ❌ | ❌ |
| 本账套全部业务模块(凭证/报表/…) | ✅ | ✅(仅本账套) | 按 RBAC |
| 本账套用户与角色授权管理 | ✅ | ✅(仅本账套) | ❌ |
| 本账套数据备份/恢复 | ✅ | ✅(仅本账套) | 按授权 |
| 设置某人为超级管理员 | ✅ | ❌ | ❌ |
| 受本账套订阅到期/停用约束 | 豁免 | 受约束 | 受约束 |

各主体的**产生与管理入口**(职责不重叠):

- **超级管理员**(`User.is_super_admin`,全局):只由「首登设置」「平台管理 → 超级管理员」维护;**「用户与权限」页不能创建或设置超管**。
- **租户管理员**(`TenantMembership.is_tenant_admin`):由「平台管理 → 成员」设置。
- **普通用户 + 角色**:在「用户与权限」页管理。该页**最高只到租户管理员**——不出现"超级管理员"任何设置;超管进入此页时也按租户管理员身份呈现。

实现要点:

- **超级管理员**:`user_has()` 恒放行;免成员/订阅校验;可登录任意租户。平台管理(`/api/platform/*`,含跨租户用户列表与设/取消超管——保留至少一个)与运行诊断(`/api/diag/*`)仅其可访问。
- **租户管理员**:由 `auth_mw` 按当前租户识别并挂到请求级用户;`user_has()` 对**本租户所有模块**豁免(含用户与授权管理),`me`/登录返回 `permissions: ["*"]` 使前端菜单一致。边界由令牌 `tid` + 成员校验保证:不可跨账套、不可访问平台/诊断、不可创建超管、受订阅到期约束。
- **普通用户**:RBAC 角色 × 权限点(`module:action`,`module:*` 展开为该模块全部动作),角色与权限按租户隔离。
- **私有化模式**(`DEPLOY_MODE=private`):`me.is_saas=false`,**不显示平台管理界面、无"平台"相关概念**;行为与单机版一致,系统管理员即 `is_super_admin`。

## 运行诊断(日志采集与上传)

- 内存环形缓冲采集运行日志(含 uvicorn),供出错时附带上下文。
- **未捕获异常 / 500** 自动打包 `traceback + 近期日志 + 元信息` 为 zip,经 GitHub Contents API 上传到共享仓库 `<PAPER_REPO>/<LOG_APP_SLUG>/logs/<UTC时间戳>_<签名>.zip`;按错误签名**节流去重**(冷却期内同类只传一次),后台线程执行,绝不阻塞或抛出。
- 凭据仅来自环境变量 `PAPER_REPO_TOKEN`(GitHub PAT),缺失则功能自动禁用(私有化默认不外传)。
- 超管在 `/diagnostics` 页查看状态/最近日志、手动打包上传。开发排查:`git clone` 该仓库看 `<slug>/logs/` 下的 zip。
- **注意**:日志可能含敏感信息,该仓库应设为 private。

---

## 登录与部署模式

系统**全站强制登录**。初始管理员因部署模式而异:

- **私有化**:首次启动按 `.env` 的 `ADMIN_PASSWORD` 自动创建超管 `admin`(**请登录后立即改密**);`ADMIN_PASSWORD` 留空则同样进入首登设置。
- **SaaS**:默认**不预置任何账号**,首次访问页面创建平台超级管理员;之后超管在「用户与权限」建用户/角色,在「平台管理」开通租户与成员。
- 生产环境务必在 `.env` 设置随机 `AUTH_SECRET`。
- RBAC:按模块×动作(查看/新建/编辑/删除/审批,及合同/税务/凭证的**直录 direct** 免审批)授权;合同/税务/大额凭证接入审批引擎,授权岗位可直录、未授权需审批。

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
| `company_info` | 企业基本信息(单例:名称/税号/地址/开户行/准则/本位币/人员等) |
| `accounts` | 一级会计科目(编码、名称、类别、方向、启用) |
| `sub_accounts` | 二级明细科目(隶属一级,编码=一级4位+顺序2位) |
| `customers` | 往来单位(类型:企业客户/个人客户/供应商/往来单位 + 开票信息/联系人) |
| `org_units` | 组织架构单元(可自引用多级) |
| `employees` | 员工档案(个人信息、持股比例、状态等) |
| `employee_positions` | 员工任职(部门+角色+职位,支持一人多岗兼职) |
| `vouchers` | 记账凭证(凭证号、日期、摘要、借贷合计、状态、客户) |
| `voucher_entries` | 凭证分录(摘要、科目、明细科目、借方、贷方,允许负数红字) |
| `voucher_links` | 凭证关联(预收/挂账/核销/应收/冲销) |
| `attachments` | 附件(类型、原名、存储路径、MIME、大小) |
| `operation_logs` | 操作日志(类型、行为、摘要、状态码、耗时、IP、时间) |
| `tenants` | 租户(名称/编码/启用/套餐/状态/到期/用户上限);私有化仅默认租户 id=1 |
| `tenant_memberships` | 用户↔租户成员关系(是否租户管理员),唯一约束 `(user_id, tenant_id)` |
| `users` / `roles` / `role_permissions` / `user_roles` | 全局用户 + 按租户隔离的角色与权限点(RBAC) |
| `auth_presets` | 按部门+职位的授权预设 |
| `workflow_definitions` / `_steps` / `_instances` / `_tasks` | 审批流程定义/步骤与运行实例/任务 |
| `expense_applications`(+items) / `expense_claims`(+items) | 费用申请(事前)/ 费用报销(事后) |
| `contracts` / `contract_voucher_links` | 合同与其关联凭证 |
| `tax_filings` + 税务附表(`tax_adjustments` 等) | 税务申报记录与企业所得税附表数据 |

> **多租户隔离**:除 `tenants`/`tenant_memberships`/`users` 为全局表外,业务表均继承 `TenantMixin`(带 `tenant_id`),由全局事件自动过滤与回填;`CompanyInfo` 亦按租户各自一行。

**核心不变量**:每张凭证 `Σ借方 = Σ贷方`;报表/账簿均由凭证分录实时聚合,不做月末结转。

---

## 页面与路由

| 路由 | 页面 | 功能 |
|---|---|---|
| `/` | 仪表盘 | 货币资金余额、周期切换、收支利润、往来款、支出构成、趋势图 |
| `/vouchers` | 记账凭证 | 检索、分页、新建、删除、红字冲销 |
| `/vouchers/new`、`/vouchers/:id` | 凭证编辑 | 多行分录、红字冲销、客户/附件/关联 |
| `/customers` | 往来单位 | 分类维护、往来业务历史 |
| `/personnel` | 人员管理 | 组织架构 + 员工档案 |
| `/accounts` | 会计科目 | 一级/二级多级维护 |
| `/ledgers` | 会计账簿 | 六类账簿查看与导出 |
| `/reports` | 财务报表 | 官方三表 + 科目汇总,导出 Excel |
| `/logs` | 操作日志 | 筛选查询,导出 PDF |
| `/contracts` | 合同管理 | 合同录入、附件、关联凭证、提交审批 |
| `/tax` | 税务管理 | 税种申报记录、附件、企业所得税报表 |
| `/expense-apply` · `/expense` | 费用申请 / 报销 | 事前申请与事后报销,走审批流程 |
| `/workflow` · `/approvals` | 流程设计 / 审批中心 | 设计审批流程、我的待办与审批轨迹 |
| `/users` | 用户与权限 | 用户/角色/权限矩阵、授权预设 |
| `/platform` | 平台管理(超管) | 租户与成员、套餐/到期(仅 SaaS 超管可见) |
| `/diagnostics` | 运行诊断(超管) | 诊断状态、最近日志、手动打包上传 |
| `/settings` | 企业信息 | 企业资料 + 数据备份/恢复 |
| `/login` · `/register` | 登录 / 注册 | 登录(选租户)、访客自助注册(SaaS)、首登设置超管 |

---

## API 一览

统一前缀 `/api`。

```
# 系统
GET    /api/health

# 企业信息
GET    /api/company
PUT    /api/company

# 会计科目(一级/二级)
GET    /api/accounts            POST /api/accounts
PUT    /api/accounts/{id}       DELETE /api/accounts/{id}
GET    /api/accounts/tree                          # 一级+二级树
GET    /api/accounts/{id}/subaccounts              POST /api/accounts/{id}/subaccounts
PUT    /api/accounts/subaccounts/{sid}             DELETE /api/accounts/subaccounts/{sid}
GET    /api/accounts/export-excel                  # 导出完整科目(含一二级)
GET    /api/accounts/subaccounts/template          # 二级导入模板
POST   /api/accounts/subaccounts/import            # 批量导入二级

# 往来单位(企业客户/个人客户/供应商/往来单位)
GET    /api/customers?party_type=&keyword=   POST /api/customers
GET    /api/customers/{id}      PUT /api/customers/{id}   DELETE /api/customers/{id}
GET    /api/customers/{id}/vouchers          # 往来业务历史

# 人员管理(组织架构 + 员工档案)
GET    /api/personnel/org-units              POST /api/personnel/org-units
PUT    /api/personnel/org-units/{id}         DELETE /api/personnel/org-units/{id}
GET    /api/personnel/employees?role_type=&org_unit_id=   POST /api/personnel/employees
PUT    /api/personnel/employees/{id}         DELETE /api/personnel/employees/{id}

# 记账凭证
GET    /api/vouchers            GET /api/vouchers/{id}
POST   /api/vouchers            PUT /api/vouchers/{id}     DELETE /api/vouchers/{id}
POST   /api/vouchers/{id}/reverse            # 红字冲销
POST   /api/vouchers/{id}/links              DELETE /api/vouchers/links/{id}   # 凭证关联

# 附件
POST   /api/vouchers/{id}/attachments
GET    /api/attachments/{id}/download | /preview
PATCH  /api/attachments/{id}                 # 修改附件类型
DELETE /api/attachments/{id}

# 仪表盘
GET    /api/reports/dashboard?period_type=day|month|quarter|year&ref_date=

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

# 鉴权与首登/注册
POST   /api/auth/login                     # 登录(可带 tenant_id 选租户)
GET    /api/auth/me      POST /api/auth/change-password
GET    /api/auth/setup-state   POST /api/auth/setup        # 首登设置超管(零用户时)
GET    /api/auth/register-open POST /api/auth/register      # 自助注册(saas 且开放时)

# 用户与权限(RBAC)
GET/POST/PUT/DELETE /api/users              POST /api/users/{id}/reset-password
GET/POST/PUT/DELETE /api/roles              GET /api/auth/permission-catalog
GET/POST/PUT/DELETE /api/auth-presets

# 合同 / 税务 / 费用 / 审批
GET/POST/PUT/DELETE /api/contracts          POST /api/contracts/{id}/submit
GET/POST/PUT/DELETE /api/tax/filings        POST /api/tax/filings/{id}/submit
GET/POST/PUT/DELETE /api/expense-apply | /api/expense
GET    /api/workflow/definitions | /instances | /my-tasks   POST .../approve | .../reject

# 平台管理(仅平台超管)
GET/POST/PUT /api/platform/tenants          POST /api/platform/tenants/{id}/reprovision
GET/POST     /api/platform/tenants/{id}/members
PUT/DELETE   /api/platform/members/{id}
GET          /api/platform/users            PUT /api/platform/users/{id}/super-admin

# 运行诊断(仅超管)
GET    /api/diag/status | /recent           POST /api/diag/report
```

后端启动后可访问 `http://<host>:8000/docs` 查看交互式 OpenAPI 文档。

---

## 环境变量

在 `.env`(参见 `.env.example`)配置;Docker 通过 `docker-compose.yml` 透传。

| 变量 | 默认 | 说明 |
|---|---|---|
| `HTTP_PORT` | `8080` | 对外访问端口 |
| `POSTGRES_USER/PASSWORD/DB` | finance | 数据库凭据(生产务必改密码;安装脚本会随机化) |
| `CORS_ORIGINS` | `*` | 允许跨域来源(同源部署可保持 `*`) |
| `REQUIRE_AUTH` | `true` | 全站强制登录 |
| `AUTH_SECRET` | 占位 | 令牌签名密钥,**生产务必改成随机串** |
| `ADMIN_PASSWORD` | `admin123` | 私有化初始超管密码;**留空则进入首登设置**(SaaS 一键默认留空) |
| `DEPLOY_MODE` | `private` | `private` 私有化 / `saas` 多租户 |
| `ALLOW_SELF_REGISTRATION` | `false` | 仅 saas:开放访客自助注册 |
| `TRIAL_DAYS` | `30` | 自助注册租户试用天数 |
| `ERROR_REPORT_ENABLED` | `true` | 诊断总开关(仍需 token 才真正上传) |
| `PAPER_REPO` | `lsgoodlionel/paper` | 诊断日志仓库(多应用共用,建议 private) |
| `PAPER_REPO_TOKEN` | 空 | GitHub PAT(该仓库 contents 写权限);**空则不上传** |
| `PAPER_REPO_BRANCH` / `LOG_APP_SLUG` | `main` / `CW` | 诊断上传分支 / 仓库内应用目录 |
| `ERROR_REPORT_COOLDOWN` | `600` | 同类错误上传冷却秒数 |
| `BACKEND_IMAGE` / `FRONTEND_IMAGE` | GHCR latest | 部署使用的镜像(默认拉 GHCR 预构建) |
| `FORCE_BUILD` | `0` | 设 `1` 强制本地构建(自定义代码/离线) |
| `PIP_INDEX_URL` | 空 | 本地构建后端时的 PyPI 镜像源(慢速网络) |

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

> **连不上 GitHub / 报「502 Bad Gateway」或「语法错误 `<head>`」?** 说明 `curl` 取到的是错误页而非脚本(服务器到 raw.githubusercontent 的网络不稳)。改用 **jsDelivr 镜像**并「先下载再执行」:
>
> ```bash
> curl -fsSL https://cdn.jsdelivr.net/gh/lsgoodlionel/CW@main/install.sh -o /tmp/cw-install.sh && bash /tmp/cw-install.sh
> ```
>
> 脚本内部拉取源码也已内置**超时 + 归档下载兜底**,git 不通时会自动改用 HTTPS 归档,不会卡死。

### 多租户 SaaS 一键部署

以多租户 SaaS 模式部署(登录选租户、平台管理后台、按租户隔离、可选自助注册):

```bash
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | DEPLOY_MODE=saas ALLOW_SELF_REGISTRATION=true bash
```

- **无默认管理员**:SaaS 部署不预置任何账号。首次访问 `http://<服务器IP>:<端口>`,登录页会自动进入 **「首次设置超级管理员」**,填写用户名/密码即创建平台超管并自动登录;该入口设置后即失效(防接管)。
- **可选参数**(前置于 `bash`):`HTTP_PORT=80`、`ALLOW_SELF_REGISTRATION=false`(关闭访客自助注册)、`ADMIN_PASSWORD=xxx`(显式预置超管、跳过首登设置)。
- 平台超管登录后可在**平台管理**开通/停用租户、设租户管理员、管理套餐与到期;**运行诊断**页可查看日志并手动打包上传排查仓库。

#### 后端镜像走 GitHub Releases/GHCR(稳定升级,免服务器 pip 构建)

升级时 `deploy.sh` 会**优先拉取云端预构建镜像**(`ghcr.io/lsgoodlionel/cw-backend|cw-frontend`,由 `.github/workflows/docker-images.yml` 在推送 main / 打标签时自动构建发布),拉取成功即直接启动,不在服务器上跑 `pip`;拉取失败(镜像未公开/网络受限)才回退本地构建。

> **一次性设置(启用免鉴权拉取)**:首次 CI 发布后,打开 <https://github.com/lsgoodlionel?tab=packages> → 分别进入 `cw-backend`、`cw-frontend` → **Package settings → Change visibility → Public**。设为公开后,服务器即可免登录拉取预构建镜像。
>
> 若暂不公开镜像:升级会自动回退本地构建;此时可在服务器 `.env` 设置 PyPI 镜像源再重试,规避慢速网络导致的 pip 超时:
>
> ```bash
> cd ~/CW && echo 'PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple' >> .env && FORCE_BUILD=1 ./deploy.sh
> ```

### 本地桌面(Windows / macOS)一键安装客户端

个人电脑上把系统当"本地客户端"用。前置:先安装 **Docker Desktop**(<https://www.docker.com/products/docker-desktop/>)。脚本会自动下载代码 → 构建 → 启动 → 打开浏览器;再次运行即"更新并启动"(数据保留在 Docker 数据卷,不丢)。

**macOS**(终端一行,推荐):

```bash
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install-mac.command | bash
```

或下载 [`install-mac.command`](install-mac.command) 后右键 → 打开(首次需在"系统设置 → 隐私与安全性"允许)。

**Windows**:下载 [`install-windows.bat`](install-windows.bat) 后**双击运行**(Windows 10+ 自带 `curl`/`tar`,无需额外工具)。

启动后自动打开 `http://localhost:8080`,初始账号 **admin / admin123**(请登录后修改)。停止:在 Docker Desktop 停止 CW 容器,或到安装目录执行 `docker compose stop`。

### 无需 Docker 的原生安装包(Windows / macOS / Linux)

把整个系统打包成**单个可执行文件**:一个进程同时提供后端 API、托管前端页面、用 **SQLite** 存数据(放到用户数据目录),运行后自动打开浏览器。**无需安装 Docker、Python 或数据库**。

- **获取**:在 GitHub Releases 下载对应平台的 `CWFinance`(Windows 为 `CWFinance-windows.exe`),双击运行即可。首次运行会在用户数据目录创建 SQLite 库并初始化(初始账号 admin / admin123)。
- **自行构建**(在目标操作系统上,需 Node 18+ 与 Python 3.11+):
  - macOS / Linux:`./packaging/build-native.sh` → 产物 `dist/CWFinance`
  - Windows(PowerShell):`./packaging/build-native.ps1` → 产物 `dist\CWFinance.exe`
- **数据位置**:Windows `%APPDATA%\CWFinance`、macOS `~/Library/Application Support/CWFinance`、Linux `~/.local/share/CWFinance`(含 `cw.db` 与 `uploads/`)。可在「企业信息 → 数据备份」导出迁移。

> 原生版适合**单机/单人**离线使用;多人并发或服务器部署仍推荐 Docker(PostgreSQL)版。二者数据可通过备份 zip 互导。
> 三平台可执行文件由 GitHub Actions(`.github/workflows/native-build.yml`)在打 `v*` 标签时自动构建并发布。

### 本地 Docker 部署(开发/自定义)

```bash
cp .env.example .env        # 按需修改端口/密码
docker compose up -d --build
# 访问 http://localhost:8080
```

或在已克隆的仓库目录执行 `./deploy.sh`(自动生成随机数据库密码的 `.env` 并起栈)。

> 生产建议:前置反向代理(Nginx/Caddy)配置 HTTPS 与域名,并在 `.env` 收紧 `CORS_ORIGINS`。

---

## 升级

**安装与升级是同一条命令**——脚本自动识别:已部署则升级(自动定位目录、升级前备份、保留数据卷),未部署则首次安装。

```bash
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | bash
```

升级流程:**自动定位部署目录 → 升级前自动备份 → 拉取最新代码(git,失败回退 HTTPS 归档)→ 重建重启(保留数据卷,数据不丢)→ 健康检查**。后端优先拉取 GHCR 预构建镜像,不在服务器跑 pip。

> 兼容:旧的 `upgrade.sh` 仍可用,它会转调最新的 `install.sh`。
>
> **务必用管道或先下载执行,不要让脚本读丢自身**:`curl ... | bash` 已修复(备份步骤切断 stdin)。若服务器 raw 报 502/取到错误页,用镜像先下载再执行:
> ```bash
> curl -fsSL https://cdn.jsdelivr.net/gh/lsgoodlionel/CW@main/install.sh -o /tmp/cw.sh && bash /tmp/cw.sh
> ```

自动定位失败时显式指定目录;`FORCE=1` 可在代码已最新时强制重建:

```bash
APP_DIR=/opt/cw bash -c "$(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh)"
```

也可在仓库目录内运行 `./install.sh`(或兼容的 `./upgrade.sh`)。数据库表结构变更在启动时自动迁移。
`HTTP_PORT` 支持写成 `host:port`(如 `127.0.0.1:18080`),健康检查会自动取其中的端口。

### 一键卸载(停用服务 + 删除数据)

在服务器上一行命令卸载(**危险操作,不可恢复**;管道运行需显式确认 `ASSUME_YES=1`):

```bash
ASSUME_YES=1 bash -c "$(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/uninstall.sh)"
```

卸载流程:**卸载前把数据导出到仓库目录之外做一次安全备份**(`$HOME/cw-uninstall-backups/`)→ 停止并删除容器 → 删除数据卷 `db_data`(数据库)与 `uploads`(附件)→ 删除本地构建镜像。

在仓库目录内运行 `./uninstall.sh` 会以交互方式要求输入 `yes` 确认。可选环境变量:

| 变量 | 作用 |
|------|------|
| `ASSUME_YES=1` | 跳过确认(管道/非交互卸载必须设置) |
| `NO_BACKUP=1` | 跳过卸载前备份 |
| `PURGE_DIR=1` | 连同代码目录一起删除(默认保留) |
| `KEEP_IMAGES=1` | 保留本地构建镜像 |
| `APP_DIR=/路径` | 自动定位失败时显式指定部署目录 |

> 重装后可在「数据备份」页导入卸载前保留的备份 zip 恢复数据。

**升级后界面没显示新功能?** 多为容器未重建或浏览器缓存,依次尝试:

```bash
# 1) 强制重建容器(即使代码已是最新)
curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | FORCE=1 bash
# 2) 浏览器强制刷新:Ctrl+Shift+R(Mac 为 Cmd+Shift+R),或用无痕窗口
```

验证后端是否已更新:`curl -s localhost:8080/api/ledgers/types` 有 JSON 输出即为新版。

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
- **鉴权**:全站强制登录 + RBAC;私有化单租户 / 多租户 SaaS 由 `DEPLOY_MODE` 切换
- **多租户隔离**:私有化(单租户)下过滤对结果无影响;SaaS 已覆盖 SELECT/UPDATE/DELETE 与 `db.get` 二次校验。支付网关未集成(续费由平台超管管理);`CompanyInfo` 已按租户各自一行
- **现金流量表**:采用对方科目归类法近似分类,期初/期末/净增加额与账面现金一致(详见 [docs/REPORTS.md](docs/REPORTS.md))
- **数量金额式明细账**:当前分录无「数量/单价」字段,该账簿仅列示金额、数量列留空
- **操作日志范围**:记录数据变更与导入导出/下载等有效行为,不记录纯浏览类 GET

---

## 项目结构

```
CW/
├── backend/                     FastAPI 后端
│   ├── app/
│   │   ├── main.py                  应用入口 + 中间件 + 异常处理 + 路由注册
│   │   ├── config.py / database.py  配置与数据库会话
│   │   ├── models.py                ORM 模型(业务表挂 TenantMixin)
│   │   ├── tenant.py                多租户隔离(上下文 + 全局过滤/回填 + tenant_get)
│   │   ├── tenant_provision.py      新建租户按租户初始化科目/角色/流程
│   │   ├── subscription.py          订阅到期/配额判定
│   │   ├── auth_svc.py / auth_mw.py 令牌/权限目录 与 鉴权中间件(设租户上下文)
│   │   ├── diag.py                  运行日志采集 + 出错打包上传 GHCR/GitHub
│   │   ├── seed_accounts.py         81 个科目种子
│   │   ├── reports_cn.py / report_excel.py    官方报表计算与 Excel 导出
│   │   ├── ledgers.py / ledger_excel.py       六类账簿生成与导出
│   │   ├── tax_report.py            企业所得税季报/年报及附表
│   │   ├── oplog.py / oplog_pdf.py  操作日志中间件/查询与 PDF 导出
│   │   ├── init_db.py               建表 + 迁移 + 种子(含唯一约束/tenant_id 迁移)
│   │   └── routers/                 company/accounts/vouchers/attachments/reports/
│   │                                ledgers/logs/data_io/customers/personnel/workflow/
│   │                                expense/expense_apply/auth/users/presets/about/
│   │                                contracts/tax/platform/diag
│   ├── requirements.txt
│   └── Dockerfile                   pip 超时/重试 + 可选 PIP_INDEX_URL 镜像
├── frontend/                    React 前端
│   ├── src/pages/                  Dashboard/VoucherList/VoucherEdit/Accounts/Ledgers/
│   │                               Reports/Logs/Settings/Contracts/Tax/Personnel/
│   │                               Users/ApprovalCenter/PlatformAdmin/Diagnostics/
│   │                               Login/Register
│   ├── src/shared/                 共享契约(自动生成,勿手改)
│   ├── nginx.conf                  静态托管 + /api 反代
│   └── Dockerfile
├── shared/contract/             Web 与小程序的共享契约(models.generated.ts 由后端 OpenAPI 生成)
├── docs/                        蓝图、报表说明、多端同步、官方模板
├── .github/workflows/           docker-images.yml(构建推送 GHCR)· native-build.yml(原生包)
├── docker-compose.yml           三容器 + 镜像/构建参数透传
├── install.sh                   云端一键安装(透传 DEPLOY_MODE 等)
├── deploy.sh                    优先拉 GHCR 预构建镜像,失败回退本地构建
├── upgrade.sh / uninstall.sh    一键升级(自动定位+备份)/ 卸载
└── .env.example
```

---

## 许可

内部自用项目。如需商用或二次开发,请自行评估《小企业会计准则》适配性与合规要求。
