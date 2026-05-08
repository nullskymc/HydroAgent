export function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

export function toNumber(value: unknown, fallback = 0) {
  const next = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(next) ? next : fallback
}

export function formatNumber1(value?: number | null, unit = '') {
  if (!isFiniteNumber(value)) return '--'
  return `${value.toFixed(1)}${unit}`
}

export function formatPercent1(value?: number | null) {
  return formatNumber1(value, '%')
}

export function formatInteger(value?: number | null, unit = '') {
  if (!isFiniteNumber(value)) return '--'
  return `${Math.round(value)}${unit}`
}

export function formatCompactId(value?: string | null) {
  if (!value) return '--'
  return value.length > 12 ? `${value.slice(0, 8)}...` : value
}
