# 共享契约与多端同步

Web 前端(本仓库 `frontend/`)与微信小程序(独立仓库 [CW-WX](https://github.com/lsgoodlionel/CW-WX))
是两套独立的 UI 工程,面对同一个后端。
本文说明:哪些东西共用、共用怎么实现、后端升级后小程序怎么跟着更新。

**一句话:数据类型从后端 OpenAPI 自动生成,不再手写。**

---

## 一、三层耦合关系

```
┌──────────────────────────────────────────────────────────────┐
│  backend/  FastAPI + PostgreSQL                               │  ← 100% 共用
│  数据模型 · 业务规则 · 权限矩阵 · 报表口径 · 账簿生成           │
└───────────┬──────────────────────────────────────────────────┘
            │ app.openapi()          │ HTTP /api/**
            ▼                        │
   shared/contract/models.generated.ts   ← 自动生成,102 个类型
            │ scripts/sync-shared.mjs    │
   ┌────────┴────────┐                   │
   ▼                 ▼                   ▼
frontend/src/shared  CW-WX/src/shared  两端各自的请求层与 UI(不共用)
```

### 1. 完全共用:后端

小程序**没有改动业务逻辑**,复用同一套 API、同一个数据库:

| 共用内容 | 说明 |
|---|---|
| 全部 `/api/**` 接口 | 见 CW-WX 的 `src/services/api.ts`,按 router 分组一一对应 |
| 鉴权与令牌 | 同一个 Bearer Token;`auth_mw.py` 支持 `?token=`,小程序 `downloadFile` 靠它 |
| 权限矩阵 | `<module>:<action>`,后端中间件是唯一拦截点 |
| 业务规则 | 借贷平衡、凭证号生成、审批流转、报表/账簿口径 |
| 导出文件 | Excel / PDF 由后端生成,两端只是下载方式不同 |

### 2. 自动生成:数据类型

`shared/contract/models.generated.ts` —— **102 个类型,全部由后端 OpenAPI 反射得到**,
覆盖凭证、科目、往来单位、人员、审批、费用、报表、账簿、日志、用户权限。

### 3. 手写但共用:枚举文案与权限判定

| 文件 | 内容 | 为什么不生成 |
|---|---|---|
| `shared/contract/labels.ts` | 14 张「值 → 中文名」映射 | 后端只拥有其中 6 张(`/meta` 接口暴露),附件类型、凭证关联关系、审批步骤状态、科目类别的中文名后端根本没有定义 |
| `shared/contract/perm.ts` | `hasPerm()` | 纯逻辑,与 `auth_svc.py` 同口径 |
| `shared/contract/amount.ts` | 金额归一化与格式化 | 见下方「金额是字符串」 |
| `shared/contract/models.ts` | 名称别名 + 表单编辑态 | 见下方「别名层」 |

枚举漂移的影响可控:两端都写成 `LABEL[x] || x`,后端加了新取值只会显示原始值,不会崩。

### 4. 完全不共用:UI 层

| 层面 | frontend | CW-WX |
|---|---|---|
| 组件库 | Ant Design 5 | `src/components/ui` 自建 |
| 路由 | react-router | 小程序页面栈 + 分包 |
| 请求 | axios | `Taro.request` 封装 |
| 图表 | recharts | 纯 CSS 比例条 |
| 颜色映射 | `'green' / 'red'`(antd) | `'success' / 'danger'`(自建色调) |

---

## 二、生成管线怎么跑

```bash
npm run contract:gen      # 取 OpenAPI → 生成类型 → 同步到两端
npm run contract:check    # 只校验:生成物是否过期、两端是否同步
```

背后是两步:

```
backend/app/schemas.py + schemas_read.py
        │  FastAPI app.openapi()
        ▼
scripts/gen-contract.mjs  ──► shared/contract/models.generated.ts
        │  scripts/sync-shared.mjs
        ├──► frontend/src/shared/     (随 git 提交)
        └──► CW-WX/src/shared/        (随 git 提交)
```

**规范来源**按顺序尝试:`--spec 文件` → `docker compose exec backend python -m app.openapi_dump` → 本地 `python -m app.openapi_dump`。
所以只要后端容器在跑就能生成,不需要额外装 Python 依赖。

### 生成器做的两件不显然的事

**① 区分请求体与响应体的可选性。**
Pydantic 里 `sub_accounts: list[...] = []` 有默认值,OpenAPI 的 `required` 就不含它;
但序列化时这个字段**一定会输出**。如果照搬 `required`,前端会拿到一堆假的可选字段,
被迫到处写 `?.` 和非空断言。所以生成器会先扫 `paths`,把只出现在响应里的 schema
标成「全字段必填」,可空性用 `| null` 表达。这一条把类型错误从 ~50 个降到了 13 个。

**② 跳过非契约 schema。**`HTTPValidationError`、`ValidationError`、multipart 的 `Body_*` 不生成。

### 别名层:`shared/contract/models.ts`

生成物用的是后端 schema 名(`AccountOut`、`InstanceOut`、`ExpenseClaimOut`),
两端代码用的是短名(`Account`、`WorkflowInstance`、`ExpenseClaim`)。别名层负责映射:

```ts
export type { InstanceOut as WorkflowInstance } from './models.generated'
```

**后端改字段 → 跑一次生成 → 别名层一行都不用动。后端加新模型 → 加一行别名。**

别名层还定义了 4 个**表单编辑态**类型(`Entry` / `ExpenseItem` / `WorkflowStep` / `Position`)。
它们不是接口契约:新建行还没有 `id`,`account_name` / `org_unit_name` 这些是后端按 id 回填的,
前端造不出来。所以从生成类型派生并放宽:

```ts
export type Position = Editable<PositionOut, 'id' | 'org_unit_name'>
```

这样后端给 `PositionOut` 加字段,编辑态也会自动跟上。

### 为什么是「复制」而不是引用

| 方案 | 否决原因 |
|---|---|
| npm workspace / 私有包 | `frontend/Dockerfile` 只 `COPY frontend/`,构建时拿不到仓库外的包 |
| 直接 `import '../../shared'` | Taro 的 babel-loader 默认只处理 `sourceRoot` 内的文件 |
| 软链接 | Docker `COPY` 不跟随、Windows 下 git 支持差 |
| **复制** | 构建链路一行不用改;`frontend/src/shared/` 进 git,服务器 `upgrade.sh` 拉代码后即最新 ✅ |

### 小程序在独立仓库

小程序已拆成独立仓库 **[lsgoodlionel/CW-WX](https://github.com/lsgoodlionel/CW-WX)**,
本仓库的 `.gitignore` 里保留 `WX/` 以防误提交。推荐目录布局是两个仓库并列:

```
~/Develop/
├── CW/          ← 后端 + Web 前端 + 契约事实源
└── CW-WX/       ← 微信小程序
```

契约在两个仓库里都**随 git 提交**,所以各自单独 clone 都能构建;
更新时两个方向都行,产物字节一致:

```bash
# 方向一:在 CW 里推(自动找同级的 CW-WX)
cd CW && npm run contract:gen

# 方向二:在 CW-WX 里拉(自动找同级的 CW)
cd CW-WX && npm run contract:sync
```

两边的查找逻辑都带兜底:

| 脚本 | 查找顺序 | 找不到时 |
|---|---|---|
| `CW/scripts/sync-shared.mjs` | `$WEAPP_REPO` → `../CW-WX` → `./WX` | 只同步 Web 前端,并提示 |
| `CW-WX/scripts/sync-contract.mjs` | `$CW_REPO` → 上级目录 → `../CW` → `../../CW` | 报错并说明 —— 纯构建不需要它 |

如果两个仓库不方便放在一起,可选的分发方式:

1. 把 `shared/contract` 发成私有 npm 包,两边 `npm install`;
2. 在 CW-WX 的 CI 里从本仓库拉取 `shared/contract` 后再构建;
3. 把生成好的 `models.generated.ts` 作为 release 附件分发。

---

## 三、后端要配合的事:给接口加 response_model

自动生成的前提是 OpenAPI 能描述响应。原本有 18 个接口直接返回裸 dict,
OpenAPI 里是空的 —— 这部分类型就只能手写。现在都补齐了:

- `backend/app/schemas_read.py` 定义只读 / 计算类响应模型(认证、用户角色、报表、账簿、日志、各类 meta)
- `schemas.py` 保持原样,只管增删改查

**两种挂法,按响应形状选:**

| 挂法 | 用于 | 效果 |
|---|---|---|
| `response_model=X` | 形状封闭的响应 | 进 OpenAPI + 运行时校验/序列化 |
| `responses={200: {"model": X}}` | 形状开放的响应 | 只进 OpenAPI,**不参与序列化** |

会计账簿(`GET /api/ledgers`)用的是后者:它的行字段随账簿种类变化
(日记账有对方科目、多栏式有明细科目列),用 `response_model` 会把动态字段裁掉。

### 加模型时必须做的验证

改完 `response_model` 一定要对照真实响应,确认没有字段被裁掉或改型:

```bash
# 加模型前先抓一份基线
curl -H "Authorization: Bearer $TOKEN" "$API/reports/official?..." | python3 -m json.tool --sort-keys > before.json
# 重建后再抓一份对比
docker compose build backend && docker compose up -d backend
curl ... | python3 -m json.tool --sort-keys > after.json
diff before.json after.json
```

本次改造对 24 个接口做了全量对照,**23 个字节一致**;唯一变化是
`GET /api/reports/official` 给原本缺省的行补上了 `"indent": null`(60 处),
没有任何字段被裁掉或改值。两端都是 `indent || 0`,渲染完全等价。

### 还没纳入的 3 个接口

`GET /api/reports/summary`、`/income`、`/balance-sheet` —— 遗留接口,两端 UI 都没有使用。
生成器每次都会把它们列出来提醒;要用的话给它们加 `response_model` 后重新生成即可。
另外 8 个文件下载接口(Excel / PDF / zip)本来就没有 JSON schema,生成器会单独归类,不当作缺口。

---

## 四、金额是字符串,不是数字

后端的金额列是 `Decimal`,FastAPI 序列化成**字符串**:

```json
{ "total_debit": "500.00", "entries": [{ "debit": "500.00" }] }
```

而报表类接口里经过 `float()` 的字段是**数字**。两种形态同时存在。

这件事在手写契约时被写错了(声明成了 `number`),自动生成之后才暴露出来。
后果是 `"39401.47".toLocaleString('zh-CN', {...})` —— `String.prototype.toLocaleString`
会忽略参数、不报错、**静默丢掉千分位**,显示成 `39401.47` 而不是 `39,401.47`。
TypeScript 也抓不到,因为 antd 的 `Table.render` 是 `any` 签名。

所以金额一律走 `shared/contract/amount.ts`:

```ts
toAmount(v)      // 归一成数字,空值按 0
formatAmount(v)  // 1,234.50
formatYuan(v)    // ¥1,234.50
```

已修的两处真实缺陷:凭证列表的「借/贷合计」列、凭证关联的「金额」列。

---

## 五、CW 升级后,小程序怎么同步

| | Web 前端 | 微信小程序 |
|---|---|---|
| 发布方式 | `./upgrade.sh` 重建容器 | 开发者工具上传 → 提交审核 → 发布 |
| 生效时间 | 立刻 | 审核 1~2 天,用户端还有缓存 |

### 场景 A:只改后端业务逻辑 —— 小程序不用动

调整报表口径、修 bug、加校验规则。`./upgrade.sh` 即可,小程序下次打开就是新结果。
**绝大多数升级属于这一类。**

### 场景 B:后端改了字段 / 加了模型 —— 重新生成 + 重发小程序

```bash
# 1. 改后端 schema
vim backend/app/schemas.py          # 或 schemas_read.py
docker compose build backend && docker compose up -d backend

# 2. 重新生成契约并同步(唯一一步,不用手写类型)
npm run contract:gen

# 3. 两端编译器会精确指出所有要改的 UI
cd frontend && npx tsc -b
cd ../CW-WX && npm run typecheck

# 4. 提交 → 服务器 ./upgrade.sh(Web 生效)
# 5. 小程序:npm run build:weapp → 开发者工具上传 → 提交审核
```

新增模型时在 `shared/contract/models.ts` 补一行别名即可。

**向后兼容原则**:新增字段给默认值(Pydantic 有默认值 = 响应里一定有),
旧版小程序不会因为缺字段而崩;删字段 / 改字段含义是破坏性变更,
要等小程序新版审核通过、旧版用户升完再上后端。

### 场景 C:新增后端接口 —— 按需接入

Web 端接了不代表小程序要接。小程序只在 CW-WX 的 `src/services/api.ts` 加对应方法。
比如本次发现仓库新增了 `GET /api/about`(版本 / 反馈 / 手册),
小程序目前还没有「关于」页,不接不影响任何已有功能。

### 场景 D:只改小程序 UI

直接重新构建上传,与 Web 端和后端无关。

### 自检清单

```bash
npm run contract:check                        # 契约是否为最新、两端是否同步
cd frontend && npx tsc -b && npm run build
cd ../CW-WX && npm run typecheck && npm run build:weapp
```

建议挂成 git 钩子:

```bash
printf '#!/bin/sh\nnode scripts/sync-shared.mjs --check\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

(钩子里只跑 `sync-shared --check`,因为 `gen-contract --check` 需要后端在跑。)

---

## 六、还没做到共用的部分

1. **接口调用代码是两份**:`frontend/src/api.ts`(axios)与 CW-WX 的 `src/services/api.ts`(Taro.request)。
   请求库不同没法直接共用,后端新增接口时两端各加一次。
   彻底消除要从 OpenAPI 生成客户端,对当前约 90 个接口的规模收益不明显。

2. **枚举中文名仍是手写**:后端只拥有其中 6 张映射(通过 `/meta` 接口暴露),
   附件类型、凭证关联关系、审批步骤状态、科目类别的中文名后端没有定义。
   要彻底生成,得先让后端拥有这些文案。

3. **`ATTACH_KIND_LABEL` 与 `ATTACHMENT_KIND_LABEL` 并存**(「回单」vs「银行回单」),
   Web 版遗留。已一并搬进契约并加注释,新代码统一用后者。

---

## 七、文件索引

| 路径 | 作用 |
|---|---|
| `backend/app/schemas.py` | 增删改查的请求 / 响应模型 |
| `backend/app/schemas_read.py` | 只读 / 计算类接口的响应模型 |
| `backend/app/openapi_dump.py` | 打印 OpenAPI 规范 |
| `scripts/gen-contract.mjs` | OpenAPI → TypeScript,附覆盖率报告 |
| `scripts/sync-shared.mjs` | 契约同步 / 漂移校验 |
| `shared/contract/models.generated.ts` | **自动生成**,勿手改 |
| `shared/contract/models.ts` | 名称别名 + 表单编辑态 |
| `shared/contract/labels.ts` | 枚举中文文案 |
| `shared/contract/amount.ts` | 金额归一化与格式化 |
| `shared/contract/perm.ts` | 权限判定 |
| `frontend/src/shared/` · CW-WX 的 `src/shared/` | 同步产物,勿手改 |
