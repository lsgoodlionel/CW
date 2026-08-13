/**
 * 金额归一化与格式化。
 *
 * 后端的金额列是 `Decimal`,FastAPI 序列化成**字符串**(如 "500.00"),
 * 而报表类接口里经过 `float()` 的字段是数字。两端都得同时应付这两种形态 ——
 * 直接对字符串调 `toLocaleString('zh-CN', …)` 不会报错,但千分位会静默丢失,
 * 所以统一走这里,不要各自手写。
 */

/** 接口可能给出的金额形态 */
export type AmountLike = number | string | null | undefined

/** 归一成数字;空值与非法值一律按 0 处理 */
export function toAmount(value: AmountLike): number {
  if (value === null || value === undefined || value === '') return 0
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : 0
}

/** 两位小数 + 千分位,如 1,234.50;不带货币符号 */
export function formatAmount(value: AmountLike): string {
  const n = toAmount(value)
  const [int, dec] = Math.abs(n).toFixed(2).split('.')
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${n < 0 ? '-' : ''}${grouped}.${dec}`
}

/** 带 ¥ 前缀,如 ¥1,234.50 */
export function formatYuan(value: AmountLike): string {
  return `¥${formatAmount(value)}`
}
