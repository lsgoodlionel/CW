#!/usr/bin/env node
/**
 * 把 shared/contract 同步到各端的 src/shared 目录。
 *
 *   node scripts/sync-shared.mjs          # 同步(改了 shared/contract 后跑一次)
 *   node scripts/sync-shared.mjs --check  # 只校验,不一致则以退出码 1 结束
 *
 * 为什么是「复制」而不是软链或 monorepo workspace:
 *   · frontend 的 Docker 构建只 COPY frontend/ 目录,仓库外的路径拿不到;
 *   · Taro 的 babel-loader 默认只处理 sourceRoot 内的文件,引用 ../shared 需要改构建配置;
 *   · 复制产物随 git 提交,服务器 upgrade.sh 拉代码后即为最新,无需额外构建步骤。
 */
import { readdirSync, readFileSync, writeFileSync, mkdirSync, existsSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const SOURCE_DIR = join(ROOT, 'shared', 'contract')

/**
 * 微信小程序在独立仓库 lsgoodlionel/CW-WX 里,位置不固定:
 * 可能与本仓库并列(../CW-WX),也可能仍放在本仓库内(WX/)。
 * 找不到就跳过 —— 小程序那边也能用自己的 `npm run contract:sync` 反向拉取。
 */
function findWeappRoot() {
  const candidates = [
    process.env.WEAPP_REPO,
    resolve(ROOT, '..', 'CW-WX'),
    join(ROOT, 'WX'),
  ]
  return candidates.find((dir) => dir && existsSync(join(dir, 'src', 'app.config.ts'))) || null
}

const weappRoot = findWeappRoot()

/** 各端的落地目录。新增端只要在这里加一行。 */
const TARGETS = [
  { name: 'Web 前端', dir: join(ROOT, 'frontend', 'src', 'shared') },
  ...(weappRoot ? [{ name: '微信小程序', dir: join(weappRoot, 'src', 'shared') }] : []),
]

const HEADER = `/**
 * ⚠️ 本文件由 scripts/sync-shared.mjs 自动生成,请勿直接修改。
 * 源文件:shared/contract/<NAME>
 * 修改流程:改 shared/contract/<NAME> → 跑 node scripts/sync-shared.mjs
 */
`

const isCheck = process.argv.includes('--check')

function sourceFiles() {
  if (!existsSync(SOURCE_DIR)) {
    console.error(`[sync-shared] 找不到源目录:${SOURCE_DIR}`)
    process.exit(1)
  }
  return readdirSync(SOURCE_DIR).filter((f) => f.endsWith('.ts')).sort()
}

function render(name) {
  return HEADER.replaceAll('<NAME>', name) + readFileSync(join(SOURCE_DIR, name), 'utf8')
}

const files = sourceFiles()
const drift = []
let written = 0

if (!weappRoot) {
  console.log('[sync-shared] 未找到小程序仓库(CW-WX),本次只同步 Web 前端。')
  console.log('    如需一并同步:把 CW-WX 放到本仓库同级目录,或设 WEAPP_REPO=/path/to/CW-WX;')
  console.log('    也可以在 CW-WX 里跑 npm run contract:sync 反向拉取。')
}

for (const target of TARGETS) {
  // 目标端不存在时跳过(例如只克隆了部分目录),不当作错误
  if (!existsSync(dirname(target.dir))) {
    console.log(`[sync-shared] 跳过 ${target.name}:${dirname(target.dir)} 不存在`)
    continue
  }

  if (!isCheck) mkdirSync(target.dir, { recursive: true })

  for (const name of files) {
    const expected = render(name)
    const dest = join(target.dir, name)
    const actual = existsSync(dest) ? readFileSync(dest, 'utf8') : null

    if (actual === expected) continue

    if (isCheck) {
      drift.push(`${target.name}: ${dest.replace(`${ROOT}/`, '')} ${actual === null ? '缺失' : '内容不一致'}`)
    } else {
      writeFileSync(dest, expected)
      written += 1
    }
  }

  // 清掉源里已删除、目标里残留的文件
  if (existsSync(target.dir)) {
    for (const stale of readdirSync(target.dir).filter((f) => f.endsWith('.ts') && !files.includes(f))) {
      const dest = join(target.dir, stale)
      if (isCheck) drift.push(`${target.name}: ${dest.replace(`${ROOT}/`, '')} 为多余文件`)
      else {
        rmSync(dest)
        written += 1
      }
    }
  }
}

if (isCheck) {
  if (drift.length === 0) {
    console.log('[sync-shared] ✅ 各端共享契约与 shared/contract 一致')
    process.exit(0)
  }
  console.error('[sync-shared] ❌ 共享契约不同步:')
  drift.forEach((d) => console.error(`  · ${d}`))
  console.error('  修复:node scripts/sync-shared.mjs')
  process.exit(1)
}

console.log(
  written === 0
    ? '[sync-shared] 已是最新,无需改动'
    : `[sync-shared] ✅ 已同步 ${written} 个文件到 ${TARGETS.length} 个端`,
)
