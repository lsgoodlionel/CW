#!/usr/bin/env node
/**
 * 从后端 OpenAPI 生成两端共用的 TypeScript 数据模型。
 *
 *   node scripts/gen-contract.mjs                    # 自动取规范并生成
 *   node scripts/gen-contract.mjs --spec spec.json   # 用现成的规范文件
 *   node scripts/gen-contract.mjs --check            # 只校验,生成物过期则退出码 1
 *
 * 规范来源按顺序尝试:
 *   1. --spec 指定的文件
 *   2. docker compose exec -T backend python -m app.openapi_dump
 *   3. python -m app.openapi_dump(需本地装好 backend 依赖)
 *
 * 产物:shared/contract/models.generated.ts
 * 名字沿用后端 schema 名(AccountOut / VoucherDetail …);
 * 前端习惯用的短名在 shared/contract/models.ts 里做别名映射。
 */
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const OUT_FILE = join(ROOT, 'shared', 'contract', 'models.generated.ts')

/** 这些是 FastAPI 内部产物或 multipart 表单体,不属于前端契约 */
const SKIP = /^(HTTPValidationError|ValidationError|Body_)/

const argv = process.argv.slice(2)
const isCheck = argv.includes('--check')
const specArg = argv[argv.indexOf('--spec') + 1]

/* ---------------- 取 OpenAPI 规范 ---------------- */

function loadSpec() {
  if (argv.includes('--spec')) {
    if (!specArg || !existsSync(specArg)) fail(`找不到规范文件:${specArg}`)
    return JSON.parse(readFileSync(specArg, 'utf8'))
  }

  const attempts = [
    { label: 'docker compose', cmd: 'docker', args: ['compose', 'exec', '-T', 'backend', 'python', '-m', 'app.openapi_dump'], cwd: ROOT },
    { label: '本地 python', cmd: 'python3', args: ['-m', 'app.openapi_dump'], cwd: join(ROOT, 'backend') },
  ]

  for (const a of attempts) {
    try {
      const out = execFileSync(a.cmd, a.args, { cwd: a.cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 32 * 1024 * 1024 })
      const json = JSON.parse(out.slice(out.indexOf('{')))
      console.log(`[gen-contract] 规范来源:${a.label}`)
      return json
    } catch {
      /* 换下一种方式 */
    }
  }
  fail('取不到 OpenAPI 规范。请先启动后端(docker compose up -d backend),或用 --spec 指定文件。')
}

function fail(msg) {
  console.error(`[gen-contract] ❌ ${msg}`)
  process.exit(1)
}

/* ---------------- JSON Schema → TypeScript ---------------- */

const refName = (ref) => ref.split('/').pop()

/** 单个 schema 节点转成 TS 类型表达式 */
function toType(node) {
  if (!node || typeof node !== 'object') return 'unknown'
  if (node.$ref) return refName(node.$ref)

  // FastAPI 的 `X | None` 会编成 anyOf: [X, {type: 'null'}]
  for (const key of ['anyOf', 'oneOf']) {
    if (Array.isArray(node[key])) {
      const parts = node[key].map(toType)
      const uniq = [...new Set(parts)]
      // 只有一个非 null 分支时收敛成 `T | null`,可读性更好
      return uniq.length === 1 ? uniq[0] : uniq.join(' | ')
    }
  }
  if (Array.isArray(node.allOf)) {
    const parts = node.allOf.map(toType).filter((t) => t !== 'unknown')
    return parts.length ? parts.join(' & ') : 'unknown'
  }

  if (Array.isArray(node.enum) && node.enum.length) {
    return node.enum.map((v) => (typeof v === 'string' ? `'${v}'` : String(v))).join(' | ')
  }

  switch (node.type) {
    case 'string':
      return 'string'
    case 'integer':
    case 'number':
      return 'number'
    case 'boolean':
      return 'boolean'
    case 'null':
      return 'null'
    case 'array':
      return `${wrap(toType(node.items || {}))}[]`
    case 'object': {
      if (node.additionalProperties && node.additionalProperties !== true) {
        return `Record<string, ${toType(node.additionalProperties)}>`
      }
      if (node.properties) return inlineObject(node)
      return 'Record<string, unknown>'
    }
    default:
      return node.properties ? inlineObject(node) : 'unknown'
  }
}

/** 联合类型作为数组元素时要加括号 */
const wrap = (t) => (t.includes('|') && !t.startsWith('(') ? `(${t})` : t)

function inlineObject(node) {
  const required = new Set(node.required || [])
  const body = Object.entries(node.properties || {})
    .map(([k, v]) => `${quoteKey(k)}${required.has(k) ? '' : '?'}: ${toType(v)}`)
    .join('; ')
  return `{ ${body} }`
}

const IDENT = /^[A-Za-z_$][A-Za-z0-9_$]*$/
const quoteKey = (k) => (IDENT.test(k) ? k : `'${k}'`)

/** 把描述文字转成 JSDoc(后端 docstring / Field description) */
function docComment(node, indent = '  ') {
  const text = [node.title && node.title !== undefined ? null : null, node.description]
    .filter(Boolean)
    .join(' ')
    .trim()
  if (!text) return ''
  const lines = text.split('\n').map((l) => `${indent} * ${l.trim()}`).join('\n')
  return `${indent}/**\n${lines}\n${indent} */\n`
}

/**
 * 判断每个 schema 是「请求体」还是「响应体」。
 *
 * 这一步决定字段该不该带 `?`:
 *   · 请求体:客户端可以不传有默认值的字段 → 可选;
 *   · 响应体:Pydantic 序列化时每个声明过的字段都会输出(没赋值就输出默认值)
 *     → 一律必填,可空性用 `| null` 表达。
 * 若不区分,像 `sub_accounts`、`attachment_count` 这些「后端一定会返回」的字段
 * 会被生成成可选,前端被迫到处写 `?.` 和非空断言。
 */
function classifySchemas(spec) {
  const schemas = spec.components?.schemas || {}
  const request = new Set()
  const response = new Set()

  const collectRefs = (node, into, seen = new Set()) => {
    if (!node || typeof node !== 'object') return
    if (node.$ref) {
      const n = refName(node.$ref)
      if (seen.has(n)) return
      seen.add(n)
      into.add(n)
      collectRefs(schemas[n], into, seen)
      return
    }
    for (const v of Object.values(node)) {
      if (v && typeof v === 'object') collectRefs(v, into, seen)
    }
  }

  for (const ops of Object.values(spec.paths || {})) {
    for (const op of Object.values(ops)) {
      if (!op || typeof op !== 'object') continue
      if (op.requestBody) collectRefs(op.requestBody, request)
      if (op.responses) {
        for (const [code, res] of Object.entries(op.responses)) {
          // 校验错误体不算业务响应
          if (code.startsWith('4') || code.startsWith('5')) continue
          collectRefs(res, response)
        }
      }
    }
  }
  return { request, response }
}

function renderSchema(name, node, responseOnly) {
  // 顶层枚举 → type 别名
  if (Array.isArray(node.enum) && node.enum.length) {
    return `export type ${name} = ${toType(node)}\n`
  }
  if (node.type !== 'object' && !node.properties) {
    return `export type ${name} = ${toType(node)}\n`
  }

  const required = new Set(node.required || [])
  const props = Object.entries(node.properties || {})
    .map(([key, prop]) => {
      const optional = responseOnly || required.has(key) ? '' : '?'
      return `${docComment(prop)}  ${quoteKey(key)}${optional}: ${toType(prop)}`
    })
    .join('\n')

  const head = node.description ? `/** ${node.description.split('\n')[0].trim()} */\n` : ''
  return `${head}export interface ${name} {\n${props}\n}\n`
}

/* ---------------- 覆盖率报告 ---------------- */

/** 文件下载类接口:返回 StreamingResponse,本来就没有 JSON schema */
const FILE_ENDPOINT = /(export-excel|export-pdf|\/template|\/download|\/preview|\/data\/export)/

/**
 * 找出仍然没有响应 schema 的接口,提示还有哪些契约是「看不见」的。
 * 分成两类:文件下载(不需要 schema)与真正的缺口(建议补 response_model)。
 */
function coverageGaps(spec) {
  const files = []
  const gaps = []
  for (const [path, ops] of Object.entries(spec.paths || {})) {
    for (const [method, op] of Object.entries(ops)) {
      if (!['get', 'post', 'put', 'patch', 'delete'].includes(method)) continue
      const ok = op.responses?.['200'] || op.responses?.['201']
      if (!ok || !ok.content?.['application/json']) continue // 204 无内容不算
      const schema = ok.content['application/json'].schema
      if (schema && (schema.$ref || schema.items?.$ref || schema.type)) continue

      const label = `${method.toUpperCase()} ${path}`
      ;(FILE_ENDPOINT.test(path) ? files : gaps).push(label)
    }
  }
  return { files: files.sort(), gaps: gaps.sort() }
}

/* ---------------- 主流程 ---------------- */

const spec = loadSpec()
const schemas = spec.components?.schemas || {}

const names = Object.keys(schemas).filter((n) => !SKIP.test(n)).sort()
if (names.length === 0) fail('规范里没有可用的 components.schemas')

const { request, response } = classifySchemas(spec)
const isResponseOnly = (n) => response.has(n) && !request.has(n)

const body = names.map((n) => renderSchema(n, schemas[n], isResponseOnly(n))).join('\n')

const header = `/**
 * ⚠️ 本文件由 scripts/gen-contract.mjs 从后端 OpenAPI 自动生成,请勿手改。
 *
 * 来源:backend/app/schemas.py + schemas_read.py(经 FastAPI 反射)
 * 重新生成:node scripts/gen-contract.mjs
 *
 * 这里的名字沿用后端 schema 名;前端习惯用的短名见同目录 models.ts 的别名映射。
 * 共 ${names.length} 个类型。
 */
/* eslint-disable */

`

const content = header + body

const { files, gaps } = coverageGaps(spec)

if (isCheck) {
  const actual = existsSync(OUT_FILE) ? readFileSync(OUT_FILE, 'utf8') : null
  if (actual === content) {
    console.log(`[gen-contract] ✅ models.generated.ts 与后端一致(${names.length} 个类型)`)
  } else {
    console.error('[gen-contract] ❌ 生成物与后端 OpenAPI 不一致,请运行:node scripts/gen-contract.mjs')
    process.exit(1)
  }
} else {
  writeFileSync(OUT_FILE, content)
  console.log(`[gen-contract] ✅ 已生成 ${names.length} 个类型 → shared/contract/models.generated.ts`)
}

if (files.length) {
  console.log(`[gen-contract] ℹ️ ${files.length} 个文件下载接口无需 schema(Excel / PDF / zip)`)
}
if (gaps.length) {
  console.warn(`[gen-contract] ⚠️ ${gaps.length} 个接口仍无响应 schema,其类型无法自动生成:`)
  gaps.forEach((g) => console.warn(`    · ${g}`))
  console.warn('    若前端要用,请在后端给它们加 response_model 后重新生成。')
}
