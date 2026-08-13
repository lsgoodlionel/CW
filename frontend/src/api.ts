import axios from 'axios'
import { message } from 'antd'

/**
 * 请求层 + 契约转出。
 *
 * 数据模型、枚举文案、权限判定统一来自共享契约(仓库根目录 shared/contract),
 * 由 scripts/sync-shared.mjs 同步到 src/shared;本文件转出它们,页面继续从
 * '../api' 引入即可。表现层相关的东西(antd 颜色等)留在本文件。
 */
export * from './shared'

import type { AuthUser } from './shared'

export const http = axios.create({ baseURL: '/api', timeout: 30000 })

// ---------- 登录令牌 ----------
const TOKEN_KEY = 'cw_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

http.interceptors.request.use((config) => {
  const t = getToken()
  if (t) config.headers.Authorization = `Bearer ${t}`
  return config
})

http.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err?.response?.status
    if (status === 401) {
      clearToken()
      // 已在登录页(如登录失败):不跳转,继续走下方错误提示显示后端原因
      if (!location.pathname.startsWith('/login')) {
        message.error('登录已过期,请重新登录')
        setTimeout(() => { location.href = '/login' }, 500)
        return Promise.reject(err)
      }
    }
    const detail = err?.response?.data?.detail
    const text =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg: string }) => d.msg).join('; ')
          : err.message || '请求失败'
    message.error(text)
    return Promise.reject(err)
  },
)

// ---------- 下载 / 预览地址 ----------
// 给浏览器直接发起的下载/预览地址(window.open、a、img、iframe)附加令牌,
// 因为这类请求不会带 Authorization 头,强制登录下会 401。
export function withToken(url: string): string {
  const t = getToken()
  if (!t) return url
  return url + (url.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(t)
}

/** 附件预览/下载 URL(带令牌) */
export function fileUrl(attachmentId: number, mode: 'preview' | 'download'): string {
  return withToken(`/api/attachments/${attachmentId}/${mode}`)
}

// ---------- 表现层映射(antd 色板,不进共享契约) ----------
export const STEP_STATE_COLOR: Record<string, string> = {
  approved: 'green', rejected: 'red', current: 'blue', upcoming: 'gray', skipped: 'gray',
}

/** 便于按需窄化的登录用户类型转出 */
export type { AuthUser }
