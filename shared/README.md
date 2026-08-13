# shared —— Web 端与小程序的共享契约

`contract/` 是**唯一事实源**:数据模型、业务枚举文案、权限判定。
Web 前端(`frontend/`)与微信小程序(`WX/`)都用它,避免两边各写一份导致漂移。

## 改动流程

```bash
vim shared/contract/models.ts      # 1. 只改这里
node scripts/sync-shared.mjs       # 2. 同步到 frontend/src/shared 与 WX/src/shared
```

生成物**随 git 提交**(Docker 构建只 COPY 各自目录,拿不到仓库外的路径)。

校验是否同步:

```bash
node scripts/sync-shared.mjs --check
```

## 什么该放进来

| 放 | 不放 |
|---|---|
| 与后端 schema 对应的数据类型 | 组件、样式、路由 |
| 状态 / 类型的中文文案 | antd 或小程序的颜色映射 |
| 权限判定这类纯逻辑 | axios / Taro.request 等请求实现 |

判断标准:**不依赖任何 UI 框架和运行环境**,两端拿去都能原样跑。

详细说明见 [../docs/SHARED-CONTRACT.md](../docs/SHARED-CONTRACT.md)。
