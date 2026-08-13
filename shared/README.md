# shared —— Web 端与小程序的共享契约

`contract/` 是两端共用的数据契约。**其中数据类型由后端 OpenAPI 自动生成,不要手写。**

```
models.generated.ts   ← 自动生成(102 个类型),勿手改
models.ts             ← 名称别名 + 表单编辑态
labels.ts             ← 枚举中文文案
amount.ts             ← 金额归一化(后端 Decimal 序列化成字符串)
perm.ts               ← 权限判定
```

## 改动流程

**后端改了字段:**

```bash
docker compose build backend && docker compose up -d backend
npm run contract:gen        # 取 OpenAPI → 生成 → 同步到两端
```

**改文案 / 权限逻辑:**

```bash
vim shared/contract/labels.ts
npm run shared:sync
```

校验(生成物是否过期、两端是否同步):

```bash
npm run contract:check
```

生成物**随 git 提交** —— Docker 构建只 COPY 各自目录,拿不到仓库外的路径。

## 什么该放进来

| 放 | 不放 |
|---|---|
| 与后端 schema 对应的数据类型(自动生成) | 组件、样式、路由 |
| 状态 / 类型的中文文案 | antd 或小程序的颜色映射 |
| 权限判定、金额归一化这类纯逻辑 | axios / Taro.request 等请求实现 |

判断标准:**不依赖任何 UI 框架和运行环境**,两端拿去都能原样跑。

详细说明见 [../docs/SHARED-CONTRACT.md](../docs/SHARED-CONTRACT.md)。
