# 共享契约与多端同步

Web 前端(`frontend/`)与微信小程序(`WX/`)是两套独立的 UI 工程,但它们面对的是**同一个后端**。
本文说明:哪些东西是两端共用的、共用是怎么实现的、后端升级后小程序怎么跟着更新。

---

## 一、三层耦合关系

```
┌─────────────────────────────────────────────────────────┐
│  backend/  FastAPI + PostgreSQL                          │  ← 100% 共用,零分叉
│  数据模型 · 业务规则 · 权限矩阵 · 报表口径 · 账簿生成      │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP /api/**  (同一份接口)
        ┌────────────────┴────────────────┐
        │                                 │
┌───────▼─────────┐              ┌────────▼──────────┐
│ shared/contract │◄─── 同步 ───►│  shared/contract  │  ← 源码级共用
│ 数据类型 / 枚举  │              │  数据类型 / 枚举   │
│ 文案 / 权限判定  │              │  文案 / 权限判定   │
├─────────────────┤              ├───────────────────┤
│ frontend/  React│              │ WX/  Taro + React │  ← 完全不共用
│ antd · 路由     │              │ 自建组件 · 分包    │
│ axios · 浏览器  │              │ Taro.request · 小程序 API │
└─────────────────┘              └───────────────────┘
```

### 1. 完全共用:后端

小程序**没有改动 `backend/` 一行代码**,复用同一套 API:

| 共用内容 | 说明 |
|---|---|
| 全部 `/api/**` 接口 | 见 `WX/src/services/api.ts`,按 router 分组一一对应 |
| 鉴权与令牌 | 同一个 Bearer Token 机制;`auth_mw.py` 支持 `?token=` 传参,小程序 `downloadFile` 靠它 |
| 权限矩阵 | `<module>:<action>`,后端中间件是唯一拦截点,两端前端判定只用于隐藏入口 |
| 业务规则 | 借贷平衡、凭证号生成、审批流转、报表/账簿口径,全在后端 |
| 导出文件 | Excel / PDF 由后端生成,两端只是下载方式不同 |
| 数据 | 同一个数据库,Web 端录的凭证小程序立刻可见 |

**含义**:后端改业务逻辑(比如调整现金流量表推导口径),小程序**不用改任何代码**,重新打开就是新结果。

### 2. 源码级共用:`shared/contract/`

这部分原本在两端各写一份,容易漂移,现在抽成了单一事实源:

| 文件 | 内容 | 体量 |
|---|---|---|
| `shared/contract/models.ts` | 与 `backend/app/schemas.py` 对齐的全部数据类型 | ~50 个 interface |
| `shared/contract/labels.ts` | 业务枚举的中文文案(状态、类型、科目类别、账簿种类…) | 14 张映射表 |
| `shared/contract/perm.ts` | `hasPerm()`,与 `auth_svc.py` 同口径 | 1 个函数 |

### 3. 完全不共用:UI 层

| 层面 | frontend | WX |
|---|---|---|
| 组件库 | Ant Design 5 | `WX/src/components/ui` 自建 |
| 路由 | react-router | 小程序页面栈 + 分包 |
| 请求 | axios | `Taro.request` 封装 |
| 图表 | recharts | 纯 CSS 比例条 |
| 文件 | `<input type=file>` / `window.open` | `chooseMessageFile` / `downloadFile` |
| 样式 | CSS + antd token | SCSS + `WX/src/styles/tokens.scss` |

颜色映射也不共用:antd 用 `'green' / 'red'` 这类色名,小程序自建组件用 `'success' / 'danger'` 色调,
所以 `STEP_STATE_COLOR`(frontend)与 `STEP_STATE_TONE`(WX)各自留在自己那一端。

---

## 二、共享是怎么实现的

**单一事实源 + 生成式同步**,而不是 monorepo workspace 或软链:

```
shared/contract/*.ts                 ← 只改这里
        │  node scripts/sync-shared.mjs
        ├──────────────► frontend/src/shared/*.ts   (自动生成,随 git 提交)
        └──────────────► WX/src/shared/*.ts         (自动生成,随 git 提交)
```

两端再各自转出一层,页面不用感知同步机制:

- `frontend/src/api.ts` → `export * from './shared'`,页面照旧 `import { Voucher... } from '../api'`
- `WX/src/types/models.ts` → `export * from '@/shared/models'`
- `WX/src/constants/labels.ts` → `export * from '@/shared/labels'` + 追加小程序自己的色调表
- `WX/src/services/auth.ts` → `export { hasPerm } from '@/shared/perm'`

### 为什么是「复制」而不是引用

| 方案 | 否决原因 |
|---|---|
| npm workspace / 私有包 | `frontend/Dockerfile` 只 `COPY frontend/`,构建时拿不到仓库外的包;要改 Docker 上下文 |
| 直接 `import '../../shared'` | Taro 的 babel-loader 默认只处理 `sourceRoot` 内的文件,跨目录要改构建配置;Vite 侧还要放开 `fs.allow` |
| 软链接 | Docker `COPY` 不跟随、Windows 下 git 支持差 |
| **复制 + 提交** | 生成物进 git,`upgrade.sh` 拉代码后即是最新,构建链路一行不用改 ✅ |

生成的文件带「请勿直接修改」头注释,`--check` 模式能检出任何手改或漏同步。

### 命令

```bash
node scripts/sync-shared.mjs            # 同步(改完 shared/contract 后跑)
node scripts/sync-shared.mjs --check    # 校验,不一致返回非零
```

也可以用仓库根的 npm 脚本:

```bash
npm run shared:sync
npm run shared:check
```

建议加成 git 钩子,避免忘记同步:

```bash
printf '#!/bin/sh\nnode scripts/sync-shared.mjs --check\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

---

## 三、CW 升级后,小程序怎么同步

关键认知:**Web 端和小程序的发布节奏天然不同**。

| | Web 前端 | 微信小程序 |
|---|---|---|
| 发布方式 | `./upgrade.sh` 重建容器 | 开发者工具上传 → 提交审核 → 发布 |
| 生效时间 | 立刻(用户刷新即可) | 审核 1~2 天,且用户端有缓存 |
| 谁来做 | 服务器上一条命令 | 需要人工在微信后台操作 |

所以升级时要按「后端改了什么」分类处理:

### 场景 A:只改后端业务逻辑 —— 小程序不用动

例:调整报表推导口径、修复凭证号生成、加一条校验规则。

```bash
./upgrade.sh        # 服务器升级即可
```

小程序**无需重新发布**,下次打开自动拿到新结果。这是绝大多数升级的情况。

### 场景 B:后端改了接口字段 / 新增枚举 —— 改契约 + 重发小程序

例:`ExpenseClaim` 加了 `pay_method` 字段、审批状态加了新取值。

```bash
# 1. 改契约(唯一事实源)
vim shared/contract/models.ts       # 或 labels.ts

# 2. 同步到两端
node scripts/sync-shared.mjs

# 3. 两端各自补 UI(编译器会指出所有要改的地方)
cd frontend && npx tsc -b           # 类型不匹配会直接报错
cd ../WX && npm run typecheck

# 4. 提交 → 服务器 ./upgrade.sh(Web 生效)
# 5. 小程序:npm run build:weapp → 开发者工具上传 → 提交审核
```

**向后兼容原则**:新增字段设成可选(`field?: T`),这样旧版本小程序不会因为缺字段而崩;
删字段 / 改字段含义属于破坏性变更,要等小程序新版本审核通过、旧版用户升级完再上线后端。

### 场景 C:新增后端接口 —— 按需接入

Web 端接了不代表小程序要接。小程序只在 `WX/src/services/api.ts` 里加对应方法即可,
不加就是不支持该功能,不影响已有能力。

### 场景 D:小程序独有的改动

改 `WX/` 下的 UI 不影响 Web 端和后端,直接重新构建上传。

### 升级前后的自检清单

```bash
node scripts/sync-shared.mjs --check   # 契约是否同步
cd frontend && npx tsc -b && npm run build
cd ../WX && npm run typecheck && npm run build:weapp
```

---

## 四、还没做到共用的部分

诚实说明当前边界,避免误以为「改一处就全好」:

1. **接口调用代码是两份**:`frontend/src/api.ts`(axios)与 `WX/src/services/api.ts`(Taro.request)。
   请求库不同,没法直接共用。后端新增接口时两端都要各加一次。
   如果要彻底消除,可以从 FastAPI 的 `/openapi.json` 生成客户端,但那会引入代码生成器依赖,
   对当前这个规模(约 90 个接口、一个后端一个团队)收益不明显。

2. **契约靠人工维护,不是从后端自动生成**:`shared/contract/models.ts` 是照着
   `backend/app/schemas.py` 手写的。后端改了 schema,不会自动报错,得靠改契约时的 code review。
   想更强的保证,可以在 CI 里跑一个脚本比对 `/openapi.json` 与契约字段。

3. **枚举文案的历史包袱**:`ATTACH_KIND_LABEL`(「回单」)与 `ATTACHMENT_KIND_LABEL`(「银行回单」)
   两套并存,是 Web 版遗留。已一并搬进契约并加了注释,新代码统一用后者;
   要统一文案的话改一处即可,但会改动现有界面显示。

---

## 五、相关文件索引

| 路径 | 作用 |
|---|---|
| `shared/contract/` | 唯一事实源 |
| `scripts/sync-shared.mjs` | 同步 / 校验脚本 |
| `frontend/src/shared/` | 生成物(勿手改) |
| `WX/src/shared/` | 生成物(勿手改) |
| `frontend/src/api.ts` | Web 请求层 + 契约转出 |
| `WX/src/services/api.ts` | 小程序请求层(按 router 分组) |
| `WX/README.md` | 小程序构建、域名白名单、平台限制 |
