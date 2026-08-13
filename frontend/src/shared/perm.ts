/**
 * ⚠️ 本文件由 scripts/sync-shared.mjs 自动生成,请勿直接修改。
 * 源文件:shared/contract/perm.ts
 * 修改流程:改 shared/contract/perm.ts → 跑 node scripts/sync-shared.mjs
 */
/**
 * 权限判定:必须与 backend/app/auth_svc.py 的 user_has / classify_perm 保持同一口径。
 * 前端判定只用于隐藏入口,真正的拦截在后端中间件(auth_mw.py)。
 */
import type { AuthUser } from './models'

/**
 * 判断当前用户是否拥有 `<module>:<action>` 权限。
 * 超级管理员、或权限表里含通配符 `*` 的,一律放行。
 */
export function hasPerm(user: AuthUser | null, module: string, action: string): boolean {
  if (!user) return false
  if (user.is_super_admin || user.permissions.includes('*')) return true
  return user.permissions.includes(`${module}:${action}`)
}
